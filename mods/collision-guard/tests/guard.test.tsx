import { expect, mock, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

type On = Parameters<TestBody>[1]

const ROOT = '/proj'
const FILE = '/proj/src/app.ts'

// Stands for the file system with one other session's record in the project folder.
function otherSession(on: On, nowMs: number) {
  const record = {
    sessionId: 'other-session-1234',
    root: ROOT,
    task: 'Refactor the app module',
    steps: [{ content: 'Split app.ts', status: 'in_progress' }],
    isWorking: true,
    startedAt: nowMs - 20 * 60_000,
    updatedAt: nowMs - 5_000,
    isEnded: false,
    edits: [{ path: FILE, at: nowMs - 4 * 60_000 }],
  }
  on('session.root', async () => ({ value: ROOT }))
  on('session.id', async () => ({ value: 'self-session-5678' }))
  on('fs.list', async () => ({ value: [{ name: 'other-session-1234.json', kind: 'file', size: 1, mtimeMs: 0, isLink: false }] }))
  on('fs.read', async () => ({ value: JSON.stringify(record) }))
  on('fs.write', async () => ({ value: undefined }))
  on('fs.stat', async () => ({ deny: 'no such file' }))
}

// Stands for the tools: the person's answer to the dialog, and the edits that actually run.
function tools(on: On, answer: string) {
  const ran: string[] = []
  on('tool.call', async (_$, e) => {
    if (e.tool === 'AskUserQuestion') {
      const q = (e as unknown as { questions: Array<{ question: string }> }).questions[0]!.question
      return { result: { questions: [], answers: { [q]: answer } } } as never
    }
    ran.push(String(e.tool))
    return { result: {} } as never
  })
  return ran
}

const edit = { tool: 'Edit', file_path: FILE, old_string: 'a', new_string: 'b', replace_all: false } as never

test('Cancel: the edit does not run, and Claude is told why', async ($, on) => {
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home' })
  otherSession(on, clock.now())
  const ran = tools(on, 'Cancel')
  const result = await $.tool.call(edit)
  expect(ran).toEqual([])
  const told = String(result.deny ?? result.text)
  expect(told.includes('cancelled')).toBe(true)
  expect(told.includes('Refactor the app module')).toBe(true)
})

test('Proceed: the edit runs, and the same file is not asked about again', async ($, on) => {
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home' })
  otherSession(on, clock.now())
  const ran = tools(on, 'Proceed')
  await $.tool.call(edit)
  await $.tool.call(edit)
  expect(ran).toEqual(['Edit', 'Edit'])
})

test('Move to a worktree, or the person types something else: Claude gets the instruction', async ($, on) => {
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home' })
  otherSession(on, clock.now())
  const ran = tools(on, 'Move to a worktree')
  const result = await $.tool.call(edit)
  expect(ran).toEqual([])
  expect(String(result.deny ?? result.text).includes('EnterWorktree')).toBe(true)
})

test('the banner names the other session, its task, state, step and files', async ($, on) => {
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home' })
  otherSession(on, clock.now())
  // Stands for whatever is drawn beneath this band.
  on('ui.render', { component: 'AbovePrompt' }, async () => ({ type: 'Box', props: {}, children: [] }))
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({
      plugin: 'collision-guard',
      component: 'AbovePrompt',
      surface,
      props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 200, scroll: { offset: 0, bodyRows: 10 }, view: {} },
    })
    expect(await ui.find({ type: 'Text', text: 'Another session is working in this folder' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /● in progress Refactor the app module/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /now: Split app\.ts · changed src\/app\.ts/ })).toBeDefined()
    await ui.unmount()
  }
})
