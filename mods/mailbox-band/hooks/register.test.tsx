import { expect, test } from 'claude-code/testing'

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
