import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import {
  actionsOf,
  debtToolThresholdOf,
  emptySnapshot,
  matchDate,
  daysSince,
  verdictOf,
} from './lib'
import type { KbSnapshot } from './index.d.ts'

const snapshotAtom = atom({ plugin: 'andrei-personal', key: 'snapshot' } as const, null)
const debtAtom = atom({ plugin: 'andrei-personal', key: 'pendingDebt' } as const, [])
const toolsAtom = atom({ plugin: 'andrei-personal', key: 'toolUses' } as const, 0)

// Poll cadence; the KB only changes when a session writes to it, so this is a
// fallback for writes made outside a turn (another session, a hook) not a ticker.
const POLL_MS = 60_000

async function readDebt($: EngineInterface): Promise<string[]> {
  const home = await $.env.get('HOME')
  if (home === undefined) return []
  const text = await $.fs
    .read(`${home}/.claude/kb-session/experience-debt`)
    .catch(() => undefined)
  if (text === undefined) return []
  return text.split('\n').filter((line) => line.trim().length > 0)
}

// KB files live in two layouts: nested (kb/knowledge/learnings.md) and flat
// (kb/learnings.md). Try nested first, fall back to flat.
async function readKbFile(
  $: EngineInterface,
  kb: string,
  name: string,
): Promise<string | undefined> {
  return await $.fs.read(`${kb}/knowledge/${name}`).catch(() =>
    $.fs.read(`${kb}/${name}`).catch(() => undefined),
  )
}

async function readKb($: EngineInterface, sessionStart: number): Promise<KbSnapshot | null> {
  const home = await $.env.get('HOME')
  if (home === undefined) return null
  const kb = `${home}/.claude/knowledge`
  const marker = `${kb}/experiences`
  const dir = await $.fs.stat(marker).catch(() => undefined)
  if (dir === undefined || dir.kind !== 'dir') return emptySnapshot()

  const entries = await $.fs.list(marker)
  const experienceEntries = entries.filter(
    (entry) => entry.kind === 'file' && entry.name.endsWith('.md'),
  )

  let learnings = 0
  const learningsText = await readKbFile($, kb, 'learnings.md')
  if (learningsText !== undefined) {
    learnings = learningsText.split('\n').filter((line) => line.startsWith('## ')).length
  }

  let verifiedDays: number | null = null
  let synthesizedDays: number | null = null
  const indexText = await readKbFile($, kb, 'INDEX.md')
  if (indexText !== undefined) {
    verifiedDays = daysSince(matchDate(indexText, 'Last verified'))
    synthesizedDays = daysSince(matchDate(indexText, 'Last synthesized'))
  }

  let dirtyFiles = 0
  const status = await $.process
    .run(['git', '-C', kb, 'status', '--porcelain'])
    .catch(() => undefined)
  if (status !== undefined && status.exitCode === 0) {
    dirtyFiles = status.stdout.split('\n').filter((line) => line.length > 0).length
  }

  const sessionEntries = experienceEntries.filter(
    (entry) => entry.mtimeMs > sessionStart,
  ).length

  return {
    experiences: experienceEntries.length,
    learnings,
    verifiedDays,
    synthesizedDays,
    dirtyFiles,
    sessionEntries,
    present: true,
  }
}

// Main-conversation tool uses, transcript-backed - the session total. The
// unbanked figure is this minus the banked floor, computed in refresh.
async function countSessionTools($: EngineInterface): Promise<number> {
  const messages = await $.session.messages().catch(() => [])
  return messages.reduce((total, message) => total + message.toolUses.length, 0)
}

// Live tool calls since the last refresh: fills the gap between refreshes and
// keeps the count when $.session.messages() is not populated. Reset at each refresh.
let liveDelta = 0

async function refresh($: EngineInterface, sessionStart: number): Promise<void> {
  const [snapshot, debt, counted] = await Promise.all([
    readKb($, sessionStart),
    readDebt($),
    countSessionTools($),
  ])
  await update($, snapshotAtom, () => snapshot)
  await update($, debtAtom, () => debt)
  // Two sources, reconciled: the transcript total minus the banked floor is
  // authoritative when $.session.messages() is populated; liveDelta covers the
  // calls since the last refresh (an empty message list must not wipe the count).
  const recompute = Math.max(0, counted - bankedCalls)
  await update($, toolsAtom, () => Math.max(liveDelta, recompute))
  liveDelta = 0
}

// Session-total tool count captured when the bank point last moved. The bank point
// itself is an mtime, which cannot be subtracted from a count ($.session.messages()
// carries no timestamps); instead, when a refresh observes the newest entry's mtime
// is NEWER than at the previous refresh, the current session total becomes the new
// floor - everything before it is banked by definition.
let bankedCalls = 0
let lastEntryMtimeMs = 0

async function rederiveBank($: EngineInterface): Promise<void> {
  const home = await $.env.get('HOME')
  if (home !== undefined) {
    const entries = await $.fs
      .list(`${home}/.claude/knowledge/experiences`)
      .catch(() => [] as Awaited<ReturnType<typeof $.fs.list>>)
    let newest = 0
    for (const entry of entries) {
      if (entry.kind === 'file' && entry.name.endsWith('.md') && entry.mtimeMs > newest) {
        newest = entry.mtimeMs
      }
    }
    if (newest > lastEntryMtimeMs) {
      // A new (or first-seen) entry: the session total as of NOW is all banked.
      lastEntryMtimeMs = newest
      bankedCalls = await countSessionTools($)
    }
  }
}

export const register: Register = (on, options) => {
  let sessionStart = 0
  let pollTimer: { cancel: () => void } | null = null
  let debtToolThreshold = debtToolThresholdOf(undefined)

  on('session.start', async ($, e, next) => {
    sessionStart = await $.clock.now()
    const configured = await $.env.get('KB_EXPERIENCE_MIN_TOOL_USES')
    debtToolThreshold = debtToolThresholdOf(configured)
    // Floor = session total as of load when an entry already exists: a mid-session
    // resume must not count pre-resume work as unbanked if it was banked.
    lastEntryMtimeMs = 0
    bankedCalls = 0
    await rederiveBank($)
    await refresh($, sessionStart)
    if (pollTimer !== null) pollTimer.cancel()
    pollTimer = $.clock.every(POLL_MS, () => {
      void (async () => {
        await rederiveBank($)
        await refresh($, sessionStart)
      })()
    })
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    // An entry banked during the turn moves the floor forward, so the displayed
    // count drops to the calls made after it.
    await rederiveBank($)
    await refresh($, sessionStart)
    return next(e)
  })

  on('tool.call', ($, e, next) => {
    // Main-loop tool calls only: kb-session-end.sh counts the transcript's
    // tool_use blocks, which excludes subagent transcripts. The live increment
    // covers mid-turn redraws; refresh recomputes from the authoritative total.
    if (e.agentId === undefined) {
      liveDelta += 1
      void update($, toolsAtom, (n) => n + 1)
    }
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const [snapshot, debt, toolUses] = await Promise.all([
      read($, snapshotAtom),
      read($, debtAtom),
      read($, toolsAtom),
    ])

    if (snapshot === null) return next(e)
    const verdict = verdictOf(snapshot)
    const actions = actionsOf(snapshot, verdict, toolUses, debtToolThreshold, debt.length)
    if (actions.length === 0) return next(e)

    const { Box, Text, Button } = $.ui.resolve(e)

    return (
      <Box>
        <Text dimColor>KB: </Text>
        {actions.map((action) => (
          <Box key={action.key}>
            {/* Button takes no color prop (label styling is dimColor/hover only),
                so the urgency color rides on the Text marker beside it. */}
            <Text color={action.color}>{action.color === 'error' ? '!! ' : '~ '}</Text>
            <Button
              key={action.key}
              plain
              label={`${action.label}  `}
              onPress={() => {
                // Fire-and-forget: the queued turn runs once the session is idle;
                // a rejection (the surface closed, the session ended) is silent.
                void $.prompt.submit({ text: action.prompt }).catch(() => undefined)
              }}
            />
          </Box>
        ))}
      </Box>
    )
  })
}
