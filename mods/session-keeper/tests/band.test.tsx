import { expect, mock, test } from 'claude-code/testing'

const BAND = {
  plugin: 'session-keeper',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 10,
    bodyColumns: 200,
    scroll: { offset: 0, bodyRows: 10 },
    view: {},
  },
} as const

test('one strip: the cache row, the context row with both buttons, and the band below kept', async ($, on) => {
  mock.clock(on)
  mock.store(on)
  on('session.usage', async () => ({
    value: {
      startedAt: 0,
      context: { tokens: 250_000, window: 1_000_000, percent: 25 },
      rateLimits: [
        { kind: 'five_hour', percentUsed: 23.5 },
        { kind: 'seven_day', percentUsed: 41 },
      ],
      cost: { usd: 12.345 },
    },
  }))
  on('session.model', async () => ({ value: 'claude-opus-5-5' }))
  // Stands for another mod's band beneath this one.
  on('ui.render', { component: 'AbovePrompt' }, async () => ({ type: 'Text', props: {}, children: ['other band'] }))

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: /no cache yet/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /5h 23\.5% · wk 41% · API \$12\.35/ })).toBeDefined()
    // 250k on Opus 5.5 with the 60-minute default: $4/MTok x 2 to re-cache, $0.20/MTok to read.
    expect(await ui.find({ type: 'Text', text: /cold msg \$2\.00 \(warm \$0\.050\)/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Context 25% \(250k\/1M\)/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /warn 40% · auto off/ })).toBeDefined()
    expect((await ui.find({ key: 'handoff' }))?.props.hotkey).toBe('1')
    expect((await ui.find({ key: 'fresh' }))?.props.hotkey).toBe('2')
    expect(await ui.find({ type: 'Text', text: 'other band' })).toBeDefined()
    // The context size is shown once, on the context row: the cache row no longer carries it.
    expect(await ui.find({ type: 'Text', text: /ctx/ })).toBe(undefined)
    await ui.unmount()
  }
})
