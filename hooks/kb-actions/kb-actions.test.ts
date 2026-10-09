import type { RenderElement } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import {
  SYNTH_EXPERIENCE_THRESHOLD,
  debtToolThresholdOf,
  emptySnapshot,
  matchDate,
  daysSince,
  verdictOf,
  actionsOf,
} from './lib'

function snapshotOf(overrides: Partial<ReturnType<typeof emptySnapshot>> = {}) {
  return { ...emptySnapshot(), present: true, synthesizedDays: 0, verifiedDays: 0, ...overrides }
}

function actionsFor(
  overrides: Partial<ReturnType<typeof snapshotOf>> = {},
  toolUses = 0,
  debtCount = 0,
) {
  const snapshot = snapshotOf(overrides)
  return actionsOf(snapshot, verdictOf(snapshot), toolUses, 20, debtCount)
}

test('nothing owed produces no actions', () => {
  expect(
    actionsFor({ experiences: 1, learnings: 12, synthesizedDays: 0, verifiedDays: 4, dirtyFiles: 0 }),
  ).toHaveLength(0)
})

test('past the tool threshold proposes update-knowledge', () => {
  const actions = actionsFor({}, 34, 0)
  expect(actions).toHaveLength(1)
  expect(actions[0]?.key).toBe('tools')
  expect(actions[0]?.label).toContain('34 tools')
  expect(actions[0]?.prompt).toContain('update-knowledge')
  expect(actions[0]?.color).toBe('warning')
})

test('tool action turns red past the red line', () => {
  const actions = actionsFor({}, 41, 0)
  expect(actions[0]?.color).toBe('error')
})

test('tools action keys on the unbanked count, not the session total', () => {
  // sessionEntries no longer suppresses; the caller passes the already-baselined
  // unbanked figure. 245 unbanked still fires; a banked session (0 unbanked) does not.
  expect(actionsFor({ sessionEntries: 1 }, 0, 0)).toHaveLength(0)
  expect(actionsFor({ sessionEntries: 0 }, 21, 0)).toHaveLength(1)
  expect(actionsFor({ sessionEntries: 1 }, 41, 0)).toHaveLength(1)
})

test('below the threshold no tools action even with an entry written', () => {
  expect(actionsFor({ sessionEntries: 1 }, 5, 0)).toHaveLength(0)
})

test('pending debt proposes update-knowledge', () => {
  const actions = actionsFor({}, 0, 2)
  expect(actions).toHaveLength(1)
  expect(actions[0]?.key).toBe('debt')
  expect(actions[0]?.prompt).toContain('update-knowledge')
  expect(actions[0]?.color).toBe('error')
})

test('uncommitted files propose a KB commit', () => {
  const actions = actionsFor({ dirtyFiles: 3 })
  expect(actions).toHaveLength(1)
  expect(actions[0]?.key).toBe('uncommitted')
  expect(actions[0]?.label).toContain('3 KB uncommitted')
  expect(actions[0]?.prompt).toContain('~/.claude/knowledge')
})

test('synthesize due proposes synthesize-knowledge with reasons', () => {
  const actions = actionsFor({
    experiences: SYNTH_EXPERIENCE_THRESHOLD,
    synthesizedDays: 0,
    verifiedDays: 0,
  })
  expect(actions).toHaveLength(1)
  expect(actions[0]?.key).toBe('synthesize')
  expect(actions[0]?.prompt).toContain('synthesize-knowledge')
  expect(actions[0]?.prompt).toContain('5 experiences')
})

test('check due proposes check-knowledge', () => {
  const actions = actionsFor({ synthesizedDays: 0, verifiedDays: 15 })
  expect(actions).toHaveLength(1)
  expect(actions[0]?.key).toBe('check')
  expect(actions[0]?.prompt).toContain('check-knowledge')
})

test('multiple dues stack in order: verdict, debt, uncommitted, tools', () => {
  const actions = actionsFor(
    {
      experiences: SYNTH_EXPERIENCE_THRESHOLD,
      synthesizedDays: 0,
      verifiedDays: 0,
      dirtyFiles: 2,
    },
    34,
    1,
  )
  expect(actions.map((action) => action.key)).toEqual([
    'synthesize',
    'debt',
    'uncommitted',
    'tools',
  ])
})

test('absent KB still shows the debt action but no commit for a missing repo', () => {
  const actions = actionsFor({ present: false, dirtyFiles: 1 }, 0, 1)
  expect(actions.map((action) => action.key)).toEqual(['debt'])
})

test('matchDate reads INDEX.md status lines', () => {
  const index = ['## KB status', '', '**Last verified:** 2026-10-03', '**Last synthesized:** 2026-10-07'].join('\n')
  expect(matchDate(index, 'Last verified')).toBe('2026-10-03')
  expect(matchDate(index, 'Last synthesized')).toBe('2026-10-07')
  expect(matchDate(index, 'Last missing')).toBeNull()
})

test('daysSince counts whole days', () => {
  // Relative to today, not a fixed date - a hardcoded date goes stale as the
  // calendar advances (2026-10-07 == 1 failed the day it became 2 days ago).
  const today = new Date().toISOString().slice(0, 10)
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10)
  expect(daysSince(yesterday)).toBe(1)
  expect(daysSince(today)).toBe(0)
  expect(daysSince(null)).toBeNull()
  expect(daysSince('not a date')).toBeNull()
})

test('debt tool threshold reads KB_EXPERIENCE_MIN_TOOL_USES', () => {
  expect(debtToolThresholdOf(undefined)).toBe(20)
  expect(debtToolThresholdOf('35')).toBe(35)
  expect(debtToolThresholdOf('abc')).toBe(20)
  expect(debtToolThresholdOf('0')).toBe(20)
})

const BAND = {
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 10,
    bodyColumns: 120,
    scroll: { bodyRows: 10, first: 0, last: 10, offset: 0 },
    view: {},
  },
  viewport: { columns: 120, rows: 40 },
} as const

test('band shows due buttons and queues the skill prompt on press', async ($, on) => {
  const submitted: string[] = []
  mock.env(on, { HOME: '/nonexistent-kb-test-home' })
  on('ui.render', (): RenderElement => h('Box', null) as RenderElement)
  on('prompt.submit', async (_, e, next) => {
    submitted.push(e.text)
    return next(e)
  })
  on('tool.call', () => ({ result: { output: 'ok' } }))
  on('turn.complete', (_$, e) => ({ text: e.answer ?? '' }))

  for (let index = 0; index < 34; index += 1) {
    await $.tool.call({ tool: 'Bash', command: 'true' })
  }
  // Raises the plugin's own turn.complete -> refresh: with HOME missing, readKb
  // lands on its emptySnapshot fallback and the tools action becomes due.
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, reason: 'answer', turnId: 't1' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'andrei-personal', surface, ...BAND })
    const button = await ui.find({ type: 'Button', text: /34 tools/ })
    expect(button).toBeDefined()
    await ui.press({ key: 'tools' })
    expect(submitted[0]).toContain('update-knowledge')
    expect(submitted[0]).toContain('34 tool uses')
    await ui.unmount()
  }
})

test('band draws nothing when nothing is owed', async ($, on) => {
  on('ui.render', (): RenderElement => h('Box', null) as RenderElement)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'andrei-personal', surface, ...BAND })
    expect(await ui.find({ type: 'Button' })).toBeUndefined()
    await ui.unmount()
  }
})
