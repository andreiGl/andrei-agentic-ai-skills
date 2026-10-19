import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const SID = '0123abcd-0000-0000-0000-000000000000'
const COMPOSER = { kind: 'composer' as const }
const SCREEN = { isFullscreen: false, columns: 120 }

test('prompt.context passes through untouched while no snapshot exists', async ($, on) => {
  on('session.id', () => ({ value: SID }))
  on('prompt.context', () => ({ blocks: [] }))
  const result = await $.prompt.context({ blocks: [] })
  expect(result.blocks.find(b => b.name === 'mailbox')).toBeUndefined()
})

test('mailbox-wire with a malformed name answers usage', async ($, on) => {
  on('session.id', () => ({ value: SID }))
  const bad = await $.command.run({ command: 'mailbox-wire', args: 'BadName 5', origin: COMPOSER, presentation: SCREEN })
  expect(bad.text).toContain('usage: /mailbox-wire')
})

test('mailbox-wire with malformed threads answers usage', async ($, on) => {
  on('session.id', () => ({ value: SID }))
  const bad = await $.command.run({ command: 'mailbox-wire', args: 'testwork 3-5', origin: COMPOSER, presentation: SCREEN })
  expect(bad.text).toContain('usage: /mailbox-wire')
})

test('mailbox-wire with no args answers usage', async ($, on) => {
  on('session.id', () => ({ value: SID }))
  const bad = await $.command.run({ command: 'mailbox-wire', args: '', origin: COMPOSER, presentation: SCREEN })
  expect(bad.text).toContain('usage: /mailbox-wire')
})

test('/mailbox in an fs-less env answers a string (failure surfaced, no crash)', async ($, on) => {
  on('session.id', () => ({ value: SID }))
  const r = await $.command.run({ command: 'mailbox', args: '', origin: COMPOSER, presentation: SCREEN })
  expect(typeof r.text).toBe('string')
  expect(r.text).toContain('mailbox-band: command failed')
})

test('commands the mod does not own fall through to next', async ($, on) => {
  on('command.run', async ($, e, next) => next({ ...e, origin: COMPOSER, presentation: SCREEN }))
  const r = await $.command.run({ command: 'not-a-real-command', args: '', origin: COMPOSER, presentation: SCREEN })
  expect(r).toBeDefined()
})

// fs/process stubs: the kit answers every call from one closure - reads
// pick by path, process.run picks by argv. env.get answers HOME's absence.
function stubEnv(on: On, map: () => string, wrote?: (text: string) => void) {
  on('fs.read', async (_$, e) => {
    if (e.path.endsWith('/sessions')) return { value: map() }
    if (e.path.endsWith('/config')) return { value: 'NICK=work\nPEER=home\nPLAIN_GH=1\n' }
    if (e.path.endsWith('/live-sessions')) return { value: '' }
    throw new Error('not found')
  })
  on('fs.write', async (_$, e) => { wrote?.(e.text); return { value: undefined } })
  on('fs.exists', async () => ({ value: true }))
  on('env.get', async () => ({ value: undefined }))
  on('process.run', async (_$, e) => {
    if (e.argv[0] === 'pgrep') return { value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    return { value: { exitCode: 0, stdout: JSON.stringify([]), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
}

test('a 4-field map line resolves threads=4 and flags=!wake (unread not broken)', async ($, on) => {
  on('session.id', () => ({ value: SID }))
  stubEnv(on, () => 'other:deadbeef:4\nmine:0123abcd:4:!wake\n')
  const r = await $.command.run({ command: 'mailbox', args: '', origin: COMPOSER, presentation: SCREEN })
  expect(r.text).toContain('thread(s) 4, flags !wake')
  expect(r.text).not.toContain('4:!wake')
})

test('mailbox-wire preserves the existing !wake flag on re-wire', async ($, on) => {
  on('session.id', () => ({ value: SID }))
  let map = 'mine:0123abcd:4:!wake\n'
  stubEnv(on, () => map, text => { map = text })
  const r = await $.command.run({ command: 'mailbox-wire', args: 'mine 4,7', origin: COMPOSER, presentation: SCREEN })
  expect(r.text).toContain('wired:')
  expect(map).toContain('mine:0123abcd:4,7:!wake')
  expect(map).not.toMatch(/^mine:0123abcd:4,7\n/m)
})

test('ui.render + prompt.context pass through on a stale-schema snapshot (pre-reload state)', async ($, on) => {
  on('session.id', () => ({ value: SID }))
  // A pre-reload snapshot: no flags, no schema. Readers must skip it, not crash.
  const stale = { installed: true, nick: 'work', peer: 'home', mapped: { name: 'infra', threads: '4' }, live: [], sid8: '0123abcd', liveRegistered: true, daemon: { running: false, pid: null }, lagSeconds: null, responderActive: false, unread: [], unreadError: false }
  on('state.get', async (_$, e) => (e.key === 'snap' ? { value: { value: stale, version: 1 } } : { value: { value: false, version: 0 } }))
  on('prompt.context', () => ({ blocks: [] }))
  on('ui.render', { component: 'AbovePrompt' }, async () => ({ type: 'Box', props: {}, children: [] }))
  const ctx = await $.prompt.context({ blocks: [] })
  expect(ctx.blocks.find(b => b.name === 'mailbox')).toBeUndefined()
  const tree = await $.ui.render({ component: 'AbovePrompt' } as never)
  expect(tree).toBeDefined()
})
