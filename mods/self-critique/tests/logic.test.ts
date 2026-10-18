import { describe, expect, test } from 'claude-code/testing'

import { fixPrompt, lastExchange, parseCritique, standalonePrompt } from '../hooks/logic'

const user = (text: string, toolResults?: unknown[]) => ({ role: 'user' as const, text, toolUses: [], toolResults })
const assistant = (text: string, tools: string[] = []) => ({
  role: 'assistant' as const,
  text,
  toolUses: tools.map(tool => ({ tool, input: { command: 'make test' } })),
})

describe('the exchange under review', () => {
  test('takes the latest prompt and every answer after it, tool-result rows included', async () => {
    const exchange = lastExchange([
      user('old question'),
      assistant('old answer'),
      user('Fix the build'),
      assistant('Looking.', ['Bash']),
      user('', [{ tool_use_id: 'x' }]),
      assistant('Fixed: the include path was wrong.'),
    ])
    expect(exchange?.request).toBe('Fix the build')
    expect(exchange?.response).toBe('Looking.\n\nFixed: the include path was wrong.')
    expect(exchange?.tools).toEqual(['Bash: make test'])
  })

  test('nothing answered yet: undefined', async () => {
    expect(lastExchange([user('hello')])).toBe(undefined)
    expect(lastExchange([])).toBe(undefined)
  })

  test('the standalone prompt carries the exchange', async () => {
    const prompt = standalonePrompt({ request: 'Q', response: 'A', tools: [] })
    expect(prompt.includes('<request>\nQ\n</request>')).toBe(true)
    expect(prompt.includes('(none)')).toBe(true)
  })
})

describe('reading the review', () => {
  test('plain JSON', async () => {
    const c = parseCritique(
      '{"verdict":"Mixed","summary":"Did most of it.","strengths":["Clear"],"flaws":[{"flaw":"No test","fix":"Add one"}]}',
    )
    expect(c).toEqual({ verdict: 'Mixed', summary: 'Did most of it.', strengths: ['Clear'], flaws: [{ flaw: 'No test', fix: 'Add one' }] })
  })

  test('fenced JSON with prose around it, odd casing, junk entries dropped', async () => {
    const c = parseCritique('Here:\n```json\n{"verdict":"strong","summary":"ok","strengths":["a", 3, ""],"flaws":[{"flaw":""},{"flaw":"b"}]}\n```')
    expect(c?.verdict).toBe('Strong')
    expect(c?.strengths).toEqual(['a'])
    expect(c?.flaws).toEqual([{ flaw: 'b', fix: '' }])
  })

  test('not a review: undefined', async () => {
    expect(parseCritique('I cannot review that.')).toBe(undefined)
    expect(parseCritique('{"verdict":"Great"}')).toBe(undefined)
  })

  test('fix prompt names the flaw and the fix', async () => {
    expect(fixPrompt({ flaw: 'No test', fix: 'Add one' })).toBe(
      'A review of your last response found this problem:\n\nNo test\n\nPlease fix it. Suggested fix: Add one',
    )
  })
})
