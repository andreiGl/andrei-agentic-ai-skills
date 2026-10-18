import { describe, expect, test } from 'claude-code/testing'

import {
  applyUpdatePlan,
  denyReason,
  formatAgo,
  liveOthers,
  newRecord,
  projectKey,
  recentEditBy,
  recordEdit,
  shouldAsk,
  workState,
} from '../hooks/logic'

const MIN = 60_000
const now = 1_000 * MIN

const session = (id: string, edits: Array<[string, number]>, extra = {}) => ({
  ...newRecord(id, '/proj', now - 60 * MIN),
  updatedAt: now - 10_000,
  edits: edits.map(([path, ago]) => ({ path, at: now - ago * MIN })),
  ...extra,
})

describe('recent edits', () => {
  test('finds the newest edit of the file by another session within 30 minutes', async () => {
    const records = [
      session('self', [['/proj/a.ts', 1]]),
      session('old', [['/proj/a.ts', 40]]),
      session('b', [['/proj/a.ts', 20]]),
      session('c', [['/proj/a.ts', 5], ['/proj/b.ts', 1]]),
    ]
    const hit = recentEditBy(records, 'self', '/proj/a.ts', now)
    expect(hit?.record.sessionId).toBe('c')
    expect(hit?.at).toBe(now - 5 * MIN)
    expect(recentEditBy(records, 'self', '/proj/z.ts', now)).toBe(undefined)
  })

  test('an ended session still counts', async () => {
    const hit = recentEditBy([session('gone', [['/proj/a.ts', 3]], { isEnded: true })], 'self', '/proj/a.ts', now)
    expect(hit?.record.sessionId).toBe('gone')
  })

  test('asks again only when the other session edits after the person said proceed', async () => {
    expect(shouldAsk({ at: 100 }, undefined)).toBe(true)
    expect(shouldAsk({ at: 100 }, 100)).toBe(false)
    expect(shouldAsk({ at: 200 }, 100)).toBe(true)
    expect(shouldAsk(undefined, undefined)).toBe(false)
  })

  test('recording an edit keeps one entry per file and drops old ones', async () => {
    const edits = recordEdit([{ path: '/a', at: now - 40 * MIN }, { path: '/b', at: now - MIN }], '/b', now)
    expect(edits).toEqual([{ path: '/b', at: now }])
  })
})

describe('other sessions', () => {
  test('alive: not this one, not ended, heard from in the last 90 seconds', async () => {
    const records = [
      session('self', []),
      session('live', []),
      session('ended', [], { isEnded: true }),
      session('silent', [], { updatedAt: now - 5 * MIN }),
    ]
    expect(liveOthers(records, 'self', now).map(r => r.sessionId)).toEqual(['live'])
  })

  test('in progress, waiting for input, or done', async () => {
    expect(workState(session('a', [], { isWorking: true }))).toBe('in progress')
    const steps = applyUpdatePlan([], { items: [{ content: 'x', status: 'completed' }, { content: 'y', status: 'pending' }] })
    expect(workState(session('a', [], { steps }))).toBe('waiting for input')
    expect(workState(session('a', []))).toBe('done')
  })

  test('formatting', async () => {
    expect(formatAgo(42_000)).toBe('42 s ago')
    expect(formatAgo(5 * MIN)).toBe('5 min ago')
    expect(projectKey('/Users/a/flip')).toBe('-Users-a-flip')
  })

  test('what Claude is told for each answer', async () => {
    expect(denyReason('Move to a worktree', 'X', 'a.ts', '5 min ago').includes('EnterWorktree')).toBe(true)
    expect(denyReason('Cancel', 'X', 'a.ts', '5 min ago').includes('cancelled')).toBe(true)
    expect(denyReason('Wait until it is done', 'X', 'a.ts', '5 min ago').endsWith('said: Wait until it is done')).toBe(true)
  })
})
