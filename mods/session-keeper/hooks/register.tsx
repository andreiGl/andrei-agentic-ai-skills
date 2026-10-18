import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { Phase, Rows } from '../types'
import {
  DEFAULT_WARN_AT,
  HANDOFF_PROMPT,
  coldWarningText,
  detectTtl,
  formatCountdown,
  formatResetIn,
  formatTokens,
  formatUsd,
  levelFor,
  nextMessageCost,
  parseAutoArgs,
  parseRowsArgs,
  parseTtlArg,
  projectDirName,
  resolveTtl,
  shouldAutoHandoff,
  warnLeadMin,
} from './logic'

const anchor = atom({ plugin: 'session-keeper', key: 'anchor' } as const, null)
const ttlDetected = atom({ plugin: 'session-keeper', key: 'ttlDetected' } as const, null)
const ttlOverride = atom({ plugin: 'session-keeper', key: 'ttlOverride' } as const, null)
const model = atom({ plugin: 'session-keeper', key: 'model' } as const, null)
const warnAt = atom({ plugin: 'session-keeper', key: 'warnAt' } as const, DEFAULT_WARN_AT)
const autoAt = atom({ plugin: 'session-keeper', key: 'autoAt' } as const, null)
const isWarned = atom({ plugin: 'session-keeper', key: 'isWarned' } as const, false)
const phase = atom({ plugin: 'session-keeper', key: 'phase' } as const, 'idle' as Phase)
const rows = atom({ plugin: 'session-keeper', key: 'rows' } as const, { cache: true, context: true } as Rows)

const STORE_OVERRIDE = 'ttlOverride'
const STORE_DETECTED = 'ttlDetected'
const STORE_WARN = 'warnAt'
const STORE_AUTO = 'autoAt'
const STORE_ROWS = 'rows'
const TRANSCRIPT_TAIL_BYTES = '2000000'

let warnTimer: Timer | undefined
let tick: Timer | undefined
let isWorking = false

function toast($: EngineInterface, text: string) {
  $.ui.toast(text)
}

// --- Cache ---

async function currentTtl($: EngineInterface) {
  return resolveTtl(await read($, ttlOverride), await read($, ttlDetected))
}

async function scheduleWarning($: EngineInterface) {
  warnTimer?.cancel()
  warnTimer = undefined
  const at = await read($, anchor)
  if (at === null) return
  const { minutes } = await currentTtl($)
  const lead = warnLeadMin(minutes)
  const delay = at + (minutes - lead) * 60_000 - (await $.clock.now())
  if (delay <= 0) return
  warnTimer = $.clock.after(delay, () => void warnCacheCold($, at, lead))
}

async function warnCacheCold($: EngineInterface, forAnchor: number, lead: number) {
  if ((await read($, anchor)) !== forAnchor) return
  const { context } = await $.session.usage()
  const text = coldWarningText(lead, context.percent, await read($, warnAt))
  toast($, text)
  const sent = await $.ui.notify(text, { title: 'Session Keeper' }).catch(() => undefined)
  if (sent?.isSent) return
  // The desktop app and other hosts without a terminal get no engine notification: use macOS directly.
  await $.process
    .run(['osascript', '-e', `display notification "${text}" with title "Session Keeper" sound name "Glass"`])
    .catch(() => undefined)
}

// The transcript lives at <config dir>/projects/<project path, non-alphanumerics as dashes>/<session id>.jsonl.
async function readTranscriptTail($: EngineInterface): Promise<string | undefined> {
  const configDir = (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${await $.env.get('HOME')}/.claude`
  const sessionId = await $.session.id()
  const projects = new Set([await $.session.root(), await $.session.cwd()])
  for (const project of projects) {
    const path = `${configDir}/projects/${projectDirName(project)}/${sessionId}.jsonl`
    const { exitCode, stdout } = await $.process.run(['tail', '-c', TRANSCRIPT_TAIL_BYTES, path])
    if (exitCode === 0) return stdout
  }
  return undefined
}

async function detectFromTranscript($: EngineInterface) {
  const tail = await readTranscriptTail($)
  if (tail === undefined) return
  const minutes = detectTtl(tail)
  if (minutes === undefined || minutes === (await read($, ttlDetected))) return
  await update($, ttlDetected, () => minutes)
  await $.store.set(STORE_DETECTED, minutes)
  await scheduleWarning($)
}

// After a /clear the old conversation's cache and warning no longer apply.
async function resetForFreshSession($: EngineInterface) {
  warnTimer?.cancel()
  warnTimer = undefined
  await update($, anchor, () => null)
  await update($, isWarned, () => false)
}

// --- Handoff ---

// Writes a brief over the current conversation, saves it, clears, and puts the brief in the fresh prompt box.
// Callers start it from a timer or a press, never from inside a hook a turn or command waits on.
async function runHandoff($: EngineInterface, reason: 'manual' | 'auto') {
  if ((await read($, phase)) !== 'idle') return
  await update($, phase, () => 'writing')
  try {
    if (reason === 'auto') toast($, 'Context reached your /autohandoff threshold: writing a handoff brief.')
    const reply = await $.model.fork({ prompt: HANDOFF_PROMPT })
    if (!reply.isAnswered) {
      toast($, `Handoff stopped before clearing: no brief (${reply.reason}).`)
      return
    }
    const brief = reply.text.trim()
    const home = (await $.env.get('HOME')) ?? '/tmp'
    const sessionId = await $.session.id()
    const stamp = new Date(await $.clock.now()).toISOString().replace(/[:.]/g, '-')
    const path = `${home}/.claude/handoffs/${stamp}-${sessionId.slice(0, 8)}.md`
    await $.fs.write(path, `${brief}\n`)

    await update($, phase, () => 'clearing')
    await $.command.run({ command: 'clear' })
    await resetForFreshSession($)

    const text = `Handoff from the previous session (also saved to ${path}):\n\n${brief}\n`
    const filled = await $.prompt.fill({ text })
    if (filled.isFilled) {
      toast($, 'New session started. The handoff brief is in the prompt box: review it and send.')
      return
    }
    // No prompt box to fill (some hosts): put the brief in the fresh context directly.
    await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
    await $.session.append({
      message: {
        type: 'system',
        content: [
          { type: 'text', text: `Session Keeper: new session started with the handoff brief in its context. Saved to ${path}.` },
        ],
      },
    })
    toast($, 'New session started with the handoff brief in its context.')
  } catch (err) {
    toast($, `Handoff failed: ${err instanceof Error ? err.message : String(err)}`)
  } finally {
    await update($, phase, () => 'idle')
  }
}

async function runFresh($: EngineInterface) {
  if ((await read($, phase)) !== 'idle') return
  await update($, phase, () => 'clearing')
  try {
    await $.command.run({ command: 'clear' })
    await resetForFreshSession($)
    toast($, 'Fresh session started.')
  } catch (err) {
    toast($, `Fresh session failed: ${err instanceof Error ? err.message : String(err)}`)
  } finally {
    await update($, phase, () => 'idle')
  }
}

function pressWhenIdle($: EngineInterface, action: () => Promise<void>) {
  if (isWorking) {
    toast($, 'Wait for the current turn to finish, then press again.')
    return
  }
  void action()
}

async function autoStatus($: EngineInterface) {
  const auto = await read($, autoAt)
  const warn = await read($, warnAt)
  const { context } = await $.session.usage()
  const now = context.percent === undefined ? 'no reading yet' : `${context.percent}% now`
  return `Session Keeper: warns at ${warn}%, ${
    auto === null ? 'auto-handoff off' : `hands off by itself at ${auto}%`
  } (${now}). Use /autohandoff <percent>, /autohandoff off, or /autohandoff warn <percent>.`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const [savedOverride, savedDetected, savedWarn, savedAuto, savedRows] = await Promise.all([
      $.store.get(STORE_OVERRIDE),
      $.store.get(STORE_DETECTED),
      $.store.get(STORE_WARN),
      $.store.get(STORE_AUTO),
      $.store.get(STORE_ROWS),
    ])
    await update($, ttlOverride, () => (typeof savedOverride === 'number' ? savedOverride : null))
    if ((await read($, ttlDetected)) === null && typeof savedDetected === 'number') {
      await update($, ttlDetected, () => savedDetected)
    }
    await update($, warnAt, () => (typeof savedWarn === 'number' ? savedWarn : DEFAULT_WARN_AT))
    await update($, autoAt, () => (typeof savedAuto === 'number' ? savedAuto : null))
    const r = savedRows as Partial<Rows> | undefined
    await update($, rows, () => ({ cache: r?.cache !== false, context: r?.context !== false }))

    await $.command.register({
      name: 'cache-ttl',
      description: 'Set the prompt-cache window Session Keeper counts down (minutes, or auto)',
      argumentHint: '[minutes|auto]',
    })
    await $.command.register({
      name: 'autohandoff',
      description: 'Hand off to a new session by itself at a context percentage (or off; warn <percent>)',
      argumentHint: '[percent|off|warn <percent>]',
    })
    await $.command.register({
      name: 'handoff',
      description: 'Write a handoff brief, start a new session, and put the brief in the prompt box',
    })
    await $.command.register({
      name: 'session-keeper',
      description: 'Show or hide a row of the Session Keeper strip',
      argumentHint: 'show|hide cache|context',
    })
    tick?.cancel()
    tick = $.clock.every(1000, () => $.ui.invalidate('ui.render'))
    await scheduleWarning($)
    return started
  })

  on('command.run', { command: 'cache-ttl' }, async ($, e) => {
    const parsed = parseTtlArg(e.args)
    if (parsed === 'invalid') return { text: 'Usage: /cache-ttl <minutes> or /cache-ttl auto' }
    await update($, ttlOverride, () => parsed)
    if (parsed === null) await $.store.delete(STORE_OVERRIDE)
    else await $.store.set(STORE_OVERRIDE, parsed)
    await scheduleWarning($)
    const { minutes, source } = await currentTtl($)
    return {
      text:
        parsed === null
          ? `Session Keeper: cache window back to automatic (${minutes} min, ${source === 'auto' ? 'detected' : 'default'}).`
          : `Session Keeper: cache window set to ${minutes} min.`,
    }
  })

  on('command.run', { command: 'autohandoff' }, async ($, e) => {
    const parsed = parseAutoArgs(e.args)
    switch (parsed.kind) {
      case 'invalid':
        return { text: 'Usage: /autohandoff <percent> | /autohandoff off | /autohandoff warn <percent>' }
      case 'off':
        await update($, autoAt, () => null)
        await $.store.delete(STORE_AUTO)
        break
      case 'auto':
        await update($, autoAt, () => parsed.percent)
        await $.store.set(STORE_AUTO, parsed.percent)
        break
      case 'warn':
        await update($, warnAt, () => parsed.percent)
        await update($, isWarned, () => false)
        await $.store.set(STORE_WARN, parsed.percent)
        break
    }
    return { text: await autoStatus($) }
  })

  // The handoff runs /clear, which waits for the session to be idle: start it after this command returns.
  on('command.run', { command: 'handoff' }, async $ => {
    if ((await read($, phase)) !== 'idle') return { text: 'Session Keeper: a handoff is already running.' }
    $.clock.after(100, () => void runHandoff($, 'manual'))
    return { text: 'Session Keeper: writing the handoff brief…' }
  })

  on('command.run', { command: 'session-keeper' }, async ($, e) => {
    const parsed = parseRowsArgs(e.args)
    if (!parsed) return { text: 'Usage: /session-keeper show|hide cache|context' }
    const next1 = await update($, rows, r => ({ ...r, [parsed.row]: parsed.isShown }))
    await $.store.set(STORE_ROWS, next1)
    return { text: `Session Keeper: ${parsed.row} row ${parsed.isShown ? 'shown' : 'hidden'}.` }
  })

  // Every main-thread request touches the cache, and its lifetime counts from the request's start.
  on('turn.step', async function* ($, e, next) {
    if (e.agentId === undefined) {
      const now = await $.clock.now()
      await update($, anchor, () => now)
      await update($, model, () => e.model)
      await scheduleWarning($)
    }
    return yield* next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result
    await detectFromTranscript($).catch(() => undefined)

    const { context } = await $.session.usage()
    const percent = context.percent
    const warn = await read($, warnAt)
    if (percent !== undefined && percent >= warn && !(await read($, isWarned))) {
      await update($, isWarned, () => true)
      toast($, `Context is at ${percent}%: answers may start to slip. Consider a handoff to a new session.`)
    }
    const isBusy = (await read($, phase)) !== 'idle'
    if (shouldAutoHandoff(percent, await read($, autoAt), isBusy)) {
      $.clock.after(500, () => void runHandoff($, 'auto'))
    }
    return result
  })

  on('session.end', async ($, e, next) => {
    if (e.reason === 'clear') await resetForFreshSession($)
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    // Keep whatever other mods draw in the band: these rows go on top of it.
    const below = await next(e)
    if (e.props.hasSurvey) return below
    isWorking = e.props.isWorking
    const { Box, Button, Text } = $.ui.resolve(e)

    const [shown, at, ttl, lastModel, warn, auto, current, usage, now] = await Promise.all([
      read($, rows),
      read($, anchor),
      currentTtl($),
      read($, model),
      read($, warnAt),
      read($, autoAt),
      read($, phase),
      $.session.usage(),
      $.clock.now(),
    ])
    const { tokens, window, percent } = usage.context

    let cacheRow = null
    if (shown.cache) {
      let cache: { text: string; color: string }
      if (at === null) {
        cache = { text: 'no cache yet', color: 'subtle' }
      } else {
        const left = at + ttl.minutes * 60_000 - now
        const lead = warnLeadMin(ttl.minutes) * 60_000
        cache = {
          text: left > 0 ? `warm ${formatCountdown(left)}` : 'cold',
          color: left <= 0 ? 'error' : left <= lead ? 'warning' : 'success',
        }
      }
      const limitLabel = (kind: string, short: string) => {
        const limit = usage.rateLimits.find(r => r.kind === kind)
        return limit ? `${short} ${limit.percentUsed}%${formatResetIn(limit.resetsAt, now)}` : `${short} —`
      }
      const limits = `${limitLabel('five_hour', '5h')} · ${limitLabel('seven_day', 'wk')}`
      const spent = usage.cost ? `API ${formatUsd(usage.cost.usd)}` : 'API —'
      const sessionModel = lastModel ?? (await $.session.model())
      const cost = tokens === undefined ? undefined : nextMessageCost(tokens, sessionModel, ttl.minutes)
      const costLabel = cost ? `cold msg ${formatUsd(cost.cold)} (warm ${formatUsd(cost.warm)})` : 'cold msg —'
      cacheRow = (
        <Text wrap="truncate-end">
          <Text color={cache.color}>Cache {cache.text}</Text>
          <Text dimColor>
            {' '}
            ({ttl.minutes}m {ttl.source}) · {limits} · {spent} · {costLabel}
          </Text>
        </Text>
      )
    }

    let contextRow = null
    if (shown.context) {
      const level = levelFor(percent, warn, auto)
      const color = { unknown: 'subtle', ok: 'success', warn: 'warning', handoff: 'error' }[level]
      const fill =
        percent === undefined || tokens === undefined
          ? 'Context —'
          : `Context ${percent}% (${formatTokens(tokens)}/${formatTokens(window)})`
      const note =
        level === 'warn' || level === 'handoff'
          ? ' quality may slip: hand off soon'
          : auto === null
            ? ` warn ${warn}% · auto off`
            : ` warn ${warn}% · auto ${auto}%`
      contextRow =
        current === 'idle' ? (
          <Box flexDirection="row">
            <Text wrap="truncate-end">
              <Text color={color}>{fill}</Text>
              <Text dimColor>{note} </Text>
            </Text>
            <Button
              key="handoff"
              hotkey="1"
              variant="primary"
              label="New session with handoff"
              onPress={() => pressWhenIdle($, () => runHandoff($, 'manual'))}
            />
            <Text> </Text>
            <Button key="fresh" hotkey="2" label="Fresh session" onPress={() => pressWhenIdle($, () => runFresh($))} />
          </Box>
        ) : (
          <Box flexDirection="row">
            <Text color={color}>{fill} </Text>
            <Text dimColor>{current === 'writing' ? 'Writing handoff brief…' : 'Starting a new session…'}</Text>
          </Box>
        )
    }

    if (!cacheRow && !contextRow) return below
    return (
      <Box flexDirection="column">
        {cacheRow}
        {contextRow}
        {below}
      </Box>
    )
  })
}
