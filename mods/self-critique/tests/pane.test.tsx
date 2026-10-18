import { expect, mock, test } from 'claude-code/testing'

const PANE = {
  plugin: 'self-critique',
  component: 'Pane',
  requestId: 'self-critique',
  props: { title: 'Self-Critique', isFocused: false, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const REVIEW = JSON.stringify({
  verdict: 'Weak',
  summary: 'It skipped the tests.',
  strengths: ['Small diff'],
  flaws: [{ flaw: 'The tests were never run', fix: 'Run make test and report the result' }],
})

test('a review with another model fills the panel, and Make this fix sends the fix', async ($, on) => {
  mock.clock(on)
  mock.store(on)
  const asked: string[] = []
  const sent: string[] = []
  on('ui.open', async () => ({ value: { isPlaced: true } }))
  on('session.messages', async () => ({
    value: [
      { role: 'user', text: 'Fix the build', toolUses: [] },
      { role: 'assistant', text: 'Done.', toolUses: [] },
    ],
  }))
  on('model.complete', async (_$, e) => {
    asked.push(e.model)
    return { value: { isAnswered: true, text: REVIEW, usage: { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } } }
  })
  on('prompt.submit', async (_$, e) => {
    sent.push(e.text)
    return { text: e.text }
  })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.select({ key: 'reviewer', value: 'haiku' })
    await ui.press({ key: 'rerun' })
    expect(await ui.find({ type: 'Text', text: /Weak/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /It skipped the tests\./ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Small diff/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Fix: Run make test/ })).toBeDefined()
    await ui.press({ key: 'fix-0' })
    expect(await ui.find({ type: 'Text', text: 'Sent to Claude' })).toBeDefined()
    await ui.unmount()
  }

  expect(asked).toEqual(['haiku', 'haiku'])
  expect(sent.length).toBe(2)
  expect(sent[0]?.includes('The tests were never run')).toBe(true)
})
