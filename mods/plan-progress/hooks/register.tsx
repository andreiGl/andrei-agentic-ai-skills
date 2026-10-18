import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Item, Plan, SessionSummary } from '../types'
import {
  EMPTY_PLAN,
  PHASES,
  applyTaskCreate,
  applyTaskUpdate,
  applyTodoWrite,
  applyUpdatePlan,
  bar,
  completeAll,
  formatElapsed,
  isPlanVisible,
  parseSummary,
  phaseFromText,
  phaseFromTool,
  progress,
  visibleOthers,
  withItems,
} from './logic'
import type { UpdatePlanInput } from './logic'

const PANE = 'plan-progress'
const TITLE = 'Plan Progress'
const SOUND = 'assets/done.wav'
const STORE_SOUND = 'isSoundOn'

const plan = atom({ plugin: 'plan-progress', key: 'plan' } as const, EMPTY_PLAN)
const lastPrompt = atom({ plugin: 'plan-progress', key: 'lastPrompt' } as const, null)
const view = atom({ plugin: 'plan-progress', key: 'view' } as const, 'session' as 'session' | 'all')
const others = atom({ plugin: 'plan-progress', key: 'others' } as const, [] as SessionSummary[])
const isWorking = atom({ plugin: 'plan-progress', key: 'isWorking' } as const, false)
const isSoundOn = atom({ plugin: 'plan-progress', key: 'isSoundOn' } as const, true)

let wasVisible = false

async function summaryDir($: EngineInterface) {
  return `${(await $.env.get('HOME')) ?? '/tmp'}/.claude/plan-progress`
}

// Each session writes its own summary file, so sessions never write the same file.
async function publish($: EngineInterface) {
  const [current, working, sessionId, root] = await Promise.all([
    read($, plan),
    read($, isWorking),
    $.session.id(),
    $.session.root(),
  ])
  const { done, total } = progress(current.items)
  const summary: SessionSummary = {
    sessionId,
    project: root.split('/').filter(Boolean).pop() ?? root,
    goal: current.goal,
    phase: current.phase,
    done,
    total,
    startedAt: current.startedAt,
    finishedAt: current.finishedAt,
    updatedAt: await $.clock.now(),
    isWorking: working,
  }
  await $.fs.write(`${await summaryDir($)}/${sessionId}.json`, JSON.stringify(summary))
}

async function unpublish($: EngineInterface, sessionId: string) {
  await $.process.run(['rm', '-f', `${await summaryDir($)}/${sessionId}.json`]).catch(() => undefined)
}

async function refreshOthers($: EngineInterface) {
  const dir = await summaryDir($)
  const entries = await $.fs.list(dir).catch(() => [])
  const all: SessionSummary[] = []
  for (const entry of entries) {
    if (!entry.name.endsWith('.json')) continue
    const summary = parseSummary(await $.fs.read(`${dir}/${entry.name}`).catch(() => ''))
    if (summary) all.push(summary)
  }
  const shown = visibleOthers(all, await $.session.id(), await $.clock.now())
  await update($, others, () => shown)
}

// Applies a change to the plan, opens the panel the first time the plan is worth showing, and republishes.
async function changePlan($: EngineInterface, change: (p: Plan, now: number, prompt: string | null) => Plan) {
  const now = await $.clock.now()
  const prompt = await read($, lastPrompt)
  const before = await read($, plan)
  const after = change(before, now, prompt)
  await update($, plan, () => after)
  const visible = isPlanVisible(after)
  if (visible && !wasVisible) void $.ui.open({ id: PANE, title: TITLE }).catch(() => undefined)
  wasVisible = visible
  if (after.finishedAt !== null && before.finishedAt === null) $.ui.toast('Plan complete: every step is checked off.')
  await publish($).catch(() => undefined)
}

function setItems($: EngineInterface, items: Item[]) {
  return changePlan($, (p, now, prompt) => withItems(p, items, now, prompt))
}

async function playChime($: EngineInterface) {
  if (!(await read($, isSoundOn))) return
  await $.audio.play({ asset: SOUND }).catch(() =>
    $.process.run(['afplay', '/System/Library/Sounds/Glass.aiff']).catch(() => undefined),
  )
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const savedSound = await $.store.get(STORE_SOUND)
    await update($, isSoundOn, () => savedSound !== false)
    await $.command.register({
      name: 'plan-progress',
      description: 'Open the Plan Progress panel (all: every session; sound on|off: the turn-end chime)',
      argumentHint: '[all|sound on|sound off]',
    })
    wasVisible = isPlanVisible(await read($, plan))
    // Redraw each second for the elapsed time; refresh the other sessions every five while that view is open.
    let ticks = 0
    $.clock.every(1000, () => {
      $.ui.invalidate('ui.render')
      ticks += 1
      if (ticks % 5 === 0) void read($, view).then(v => (v === 'all' ? refreshOthers($) : undefined))
    })
    return started
  })

  on('command.run', { command: 'plan-progress' }, async ($, e) => {
    const words = e.args.trim().toLowerCase().split(/\s+/).filter(Boolean)
    if (words[0] === 'sound') {
      const isOn = words[1] !== 'off'
      await update($, isSoundOn, () => isOn)
      await $.store.set(STORE_SOUND, isOn)
      return { text: `Plan Progress: turn-end chime ${isOn ? 'on' : 'off'}.` }
    }
    const wanted = words[0] === 'all' ? 'all' : 'session'
    await update($, view, () => wanted)
    if (wanted === 'all') await refreshOthers($)
    await $.ui.open({ id: PANE, title: TITLE })
    return { text: `Plan Progress opened (${wanted === 'all' ? 'All tasks' : 'this session'}).` }
  })

  // /goal <condition> sets the goal; /goal clear drops it.
  on('command.run', { command: 'goal' }, async ($, e, next) => {
    const result = await next(e)
    const args = e.args.trim()
    if (args === '') return result
    await changePlan($, (p, now) =>
      args.toLowerCase() === 'clear'
        ? { ...p, goal: null, goalSource: null }
        : { ...p, goal: args, goalSource: 'goal', startedAt: p.startedAt ?? now, finishedAt: null },
    )
    return result
  }).catch(($, e, next) => next(e))

  on('prompt.submit', async ($, e, next) => {
    if (e.command === undefined && !e.isMeta) await update($, lastPrompt, () => e.text)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || ran.isError) return ran
    const tool = String(e.tool)
    const args = e as unknown as Record<string, unknown>
    try {
      if (tool === 'mcp__ccd_turn__update_plan') {
        const current = await read($, plan)
        await setItems($, applyUpdatePlan(current.items, args as UpdatePlanInput))
      } else if (tool === 'mcp__ccd_turn__wrap_up') {
        const current = await read($, plan)
        if (current.items.length > 0) await setItems($, completeAll(current.items))
      } else if (tool === 'TodoWrite') {
        await setItems($, applyTodoWrite((args.todos as Array<{ content: string; status: string }>) ?? []))
      } else if (tool === 'TaskCreate') {
        const task = (ran.result as { task?: { id?: string; subject?: string } } | undefined)?.task
        if (task?.id) {
          const current = await read($, plan)
          await setItems($, applyTaskCreate(current.items, task.id, task.subject ?? String(args.subject ?? '')))
        }
      } else if (tool === 'TaskUpdate') {
        const current = await read($, plan)
        await setItems($, applyTaskUpdate(current.items, args as { taskId: string; status?: string; subject?: string }))
      } else if (tool === 'ProposeGoal' && typeof args.condition === 'string') {
        const goal = args.condition
        await changePlan($, (p, now) => ({ ...p, goal, goalSource: 'goal', startedAt: p.startedAt ?? now, finishedAt: null }))
      } else {
        const fromTool = phaseFromTool(tool, args)
        const current = await read($, plan)
        const fromStep = phaseFromText(current.items.find(i => i.status === 'in_progress')?.content)
        const phase = fromStep ?? fromTool
        if (phase && phase !== current.phase && isPlanVisible(current) && current.finishedAt === null) {
          await changePlan($, p => ({ ...p, phase }))
        }
      }
    } catch {
      // A task-list shape this build does not know: leave the panel as it was.
    }
    return ran
  }).catch(($, e, next) => next(e))

  on('turn.start', async ($, e, next) => {
    if (e.agentId === undefined) {
      await update($, isWorking, () => true)
      await publish($).catch(() => undefined)
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result
    await update($, isWorking, () => false)
    await publish($).catch(() => undefined)
    if (!e.isAborted) await playChime($)
    return result
  })

  on('session.end', async ($, e, next) => {
    await unpublish($, e.sessionId)
    if (e.reason === 'clear') {
      await update($, plan, () => EMPTY_PLAN)
      wasVisible = false
    }
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const [current, which, list, working, now] = await Promise.all([
      read($, plan),
      read($, view),
      read($, others),
      read($, isWorking),
      $.clock.now(),
    ])
    const width = Math.max(10, Math.min(30, e.props.bodyColumns - 24))

    const tabs = (
      <Box flexDirection="row">
        <Button key="tab-session" variant={which === 'session' ? 'primary' : 'secondary'} label="This session" onPress={() => update($, view, () => 'session')} />
        <Text> </Text>
        <Button
          key="tab-all"
          variant={which === 'all' ? 'primary' : 'secondary'}
          label="All tasks"
          onPress={async () => {
            await update($, view, () => 'all')
            await refreshOthers($)
          }}
        />
      </Box>
    )

    if (which === 'all') {
      return (
        <Box flexDirection="column">
          {tabs}
          <Text> </Text>
          {list.length === 0 && <Text dimColor>No other session is running a goal or a multi-step task.</Text>}
          {list.map(s => {
            const percent = s.total === 0 ? 0 : Math.round((s.done / s.total) * 100)
            const elapsed = s.startedAt === null ? '' : ` · ${formatElapsed((s.finishedAt ?? now) - s.startedAt)}`
            const state = s.finishedAt !== null ? 'done' : s.isWorking ? 'working' : 'idle'
            return (
              <Box key={s.sessionId} flexDirection="column">
                <Text>
                  <Text bold>{s.project}</Text>
                  <Text dimColor> · {state}{s.phase ? ` · ${s.phase}` : ''}{elapsed}</Text>
                </Text>
                <Text wrap="truncate-end">{s.goal ?? 'Multi-step task'}</Text>
                <Text>
                  <Text color={s.finishedAt !== null ? 'success' : 'claude'}>{bar(percent, width)}</Text>
                  <Text dimColor> {percent}% · {s.done}/{s.total}</Text>
                </Text>
                <Text> </Text>
              </Box>
            )
          })}
        </Box>
      )
    }

    if (!isPlanVisible(current)) {
      return (
        <Box flexDirection="column">
          {tabs}
          <Text> </Text>
          <Text dimColor>No goal or multi-step task in this session yet.</Text>
        </Box>
      )
    }

    const { done, total, percent } = progress(current.items)
    const elapsed = current.startedAt === null ? '—' : formatElapsed((current.finishedAt ?? now) - current.startedAt)
    const status = current.finishedAt !== null ? 'done' : working ? 'working' : 'waiting for you'

    return (
      <Box flexDirection="column">
        {tabs}
        <Text> </Text>
        <Text bold wrap="wrap">
          {current.goalSource === 'goal' ? 'Goal: ' : ''}
          {current.goal ?? 'Multi-step task'}
        </Text>
        <Text>
          {PHASES.map((p, n) => (
            <Text key={p} color={p === current.phase ? 'claude' : 'subtle'} bold={p === current.phase}>
              {n > 0 ? ' › ' : ''}
              {p}
            </Text>
          ))}
        </Text>
        <Text>
          <Text color={current.finishedAt !== null ? 'success' : 'claude'}>{bar(percent, width)}</Text>
          <Text> {percent}%</Text>
          <Text dimColor> · {done}/{total} · {elapsed} · {status}</Text>
        </Text>
        <Text> </Text>
        {current.items.map((item, n) => (
          <Text key={`item-${n}`} wrap="wrap" dimColor={item.status === 'completed'} color={item.status === 'in_progress' ? 'claude' : undefined}>
            {item.status === 'completed' ? '✓ ' : item.status === 'in_progress' ? '▶ ' : '○ '}
            {item.content}
          </Text>
        ))}
      </Box>
    )
  })
}
