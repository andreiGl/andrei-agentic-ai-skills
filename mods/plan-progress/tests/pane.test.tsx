import { expect, mock, test } from 'claude-code/testing'

const PANE = {
  plugin: 'plan-progress',
  component: 'Pane',
  requestId: 'plan-progress',
  props: { title: 'Plan Progress', isFocused: false, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

test('the desktop task list drives the checklist, progress bar and phase', async ($, on) => {
  mock.clock(on)
  mock.store(on)
  mock.env(on, { HOME: '/nowhere' })
  // Stands for the tool itself.
  on('tool.call', async () => ({ result: {} }))
  on('ui.open', async () => ({ value: { isPlaced: true } }))

  await $.tool.call({
    tool: 'mcp__ccd_turn__update_plan',
    items: [
      { content: 'Read the pane API', status: 'in_progress' },
      { content: 'Write the mod', status: 'pending' },
    ],
    scope: 'continuation',
  } as never)
  await $.tool.call({ tool: 'mcp__ccd_turn__update_plan', advance: true } as never)

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /50%/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /✓ Read the pane API/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /▶ Write the mod/ })).toBeDefined()
    expect(await ui.find({ key: 'tab-all' })).toBeDefined()
    await ui.unmount()
  }
})
