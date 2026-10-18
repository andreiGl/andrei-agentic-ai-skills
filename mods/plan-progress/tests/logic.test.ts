import { describe, expect, test } from 'claude-code/testing'

import {
  EMPTY_PLAN,
  applyTaskCreate,
  applyTaskUpdate,
  applyTodoWrite,
  applyUpdatePlan,
  bar,
  formatElapsed,
  phaseFromText,
  phaseFromTool,
  progress,
  visibleOthers,
  withItems,
} from '../hooks/logic'
import type { SessionSummary } from '../types'

const three = [
  { content: 'Read the API', status: 'in_progress' },
  { content: 'Write the mod', status: 'pending' },
  { content: 'Run the tests', status: 'pending' },
]

describe('checklist from the desktop task list', () => {
  test('items replace the list; advance ticks the current step and starts the next', async () => {
    const start = applyUpdatePlan([], { items: three })
    const next = applyUpdatePlan(start, { advance: true })
    expect(next.map(i => i.status)).toEqual(['completed', 'in_progress', 'pending'])
  })

  test('done and start move steps out of order (1-based)', async () => {
    const start = applyUpdatePlan([], { items: three })
    const moved = applyUpdatePlan(start, { done: [1, 2], start: 3 })
    expect(moved.map(i => i.status)).toEqual(['completed', 'completed', 'in_progress'])
  })
})

describe('checklist from the terminal task tools', () => {
  test('TodoWrite is the whole list', async () => {
    expect(applyTodoWrite([{ content: 'a', status: 'completed' }]).map(i => i.status)).toEqual(['completed'])
  })

  test('TaskCreate adds, TaskUpdate changes or deletes by id', async () => {
    let items = applyTaskCreate([], '1', 'First')
    items = applyTaskCreate(items, '2', 'Second')
    items = applyTaskUpdate(items, { taskId: '1', status: 'completed' })
    expect(progress(items)).toEqual({ done: 1, total: 2, percent: 50 })
    items = applyTaskUpdate(items, { taskId: '2', status: 'deleted' })
    expect(items.map(i => i.content)).toEqual(['First'])
  })
})

describe('plan lifecycle', () => {
  test('a new plan takes the prompt as its goal and starts the clock', async () => {
    const p = withItems(EMPTY_PLAN, applyUpdatePlan([], { items: three }), 1000, 'Build a mod called Plan Progress.\nMore.')
    expect(p.goal).toBe('Build a mod called Plan Progress.')
    expect(p.goalSource).toBe('prompt')
    expect(p.startedAt).toBe(1000)
    expect(p.phase).toBe('researching')
  })

  test('finishing stamps the end; a new list after that starts over', async () => {
    const running = withItems(EMPTY_PLAN, applyUpdatePlan([], { items: three }), 1000, 'old task')
    const finished = withItems(running, running.items.map(i => ({ ...i, status: 'completed' as const })), 5000, 'old task')
    expect(finished.finishedAt).toBe(5000)
    const fresh = withItems(finished, applyUpdatePlan([], { items: three }), 9000, 'new task')
    expect(fresh.startedAt).toBe(9000)
    expect(fresh.finishedAt).toBe(null)
    expect(fresh.goal).toBe('new task')
  })

  test('a /goal goal survives a new list', async () => {
    const withGoal = { ...EMPTY_PLAN, goal: 'all tests pass', goalSource: 'goal' as const, startedAt: 10 }
    const p = withItems(withGoal, applyUpdatePlan([], { items: three }), 20, 'some prompt')
    expect(p.goal).toBe('all tests pass')
    expect(p.startedAt).toBe(10)
  })
})

describe('phase', () => {
  test('from the current step', async () => {
    expect(phaseFromText('Run the tests')).toBe('testing')
    expect(phaseFromText('Review the diff')).toBe('auditing')
    expect(phaseFromText('Design the panel')).toBe('planning')
    expect(phaseFromText('Implement the hooks')).toBe('building')
    expect(phaseFromText('Look at how X is set up')).toBe('researching')
  })

  test('from the tool in use', async () => {
    expect(phaseFromTool('Grep', {})).toBe('researching')
    expect(phaseFromTool('Edit', {})).toBe('building')
    expect(phaseFromTool('Bash', { command: 'cargo test --all' })).toBe('testing')
    expect(phaseFromTool('Bash', { command: 'ls' })).toBe(undefined)
    expect(phaseFromTool('Skill', { skill: 'security-review' })).toBe('auditing')
  })
})

describe('formatting and other sessions', () => {
  test('bar and elapsed', async () => {
    expect(bar(50, 10)).toBe('█████░░░░░')
    expect(formatElapsed(65_000)).toBe('1m 05s')
    expect(formatElapsed(3_900_000)).toBe('1h 05m')
  })

  test('All tasks hides this session, stale, long-finished and planless sessions', async () => {
    const now = 10 * 3_600_000
    const base: SessionSummary = {
      sessionId: 'a', project: 'flip', goal: 'g', phase: 'building', done: 1, total: 3,
      startedAt: now - 60_000, finishedAt: null, updatedAt: now - 1000, isWorking: true,
    }
    const all = [
      base,
      { ...base, sessionId: 'self' },
      { ...base, sessionId: 'stale', updatedAt: now - 7 * 3_600_000 },
      { ...base, sessionId: 'old-done', finishedAt: now - 3_600_000 },
      { ...base, sessionId: 'no-plan', goal: null, total: 1 },
    ]
    expect(visibleOthers(all, 'self', now).map(s => s.sessionId)).toEqual(['a'])
  })
})
