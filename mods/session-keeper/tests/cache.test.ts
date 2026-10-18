import { describe, expect, test } from 'claude-code/testing'

import {
  detectTtl,
  formatCountdown,
  nextMessageCost,
  parseTtlArg,
  priceFor,
  projectDirName,
  resolveTtl,
} from '../hooks/logic'

const line = (o: unknown) => JSON.stringify(o)
const assistant = (h1: number, m5: number, isSidechain = false) =>
  line({
    type: 'assistant',
    isSidechain,
    message: {
      usage: { cache_creation: { ephemeral_1h_input_tokens: h1, ephemeral_5m_input_tokens: m5 } },
    },
  })

describe('TTL detection', () => {
  test('a 1-hour write in the newest entry reads as 60 minutes', async () => {
    expect(detectTtl([assistant(0, 900), assistant(681, 0)].join('\n'))).toBe(60)
  })

  test('a 5-minute write reads as 5 minutes', async () => {
    expect(detectTtl(['{"cut line', assistant(0, 500)].join('\n'))).toBe(5)
  })

  test('subagent entries and read-only entries are skipped', async () => {
    const tail = [assistant(0, 500), assistant(700, 0, true), assistant(0, 0)].join('\n')
    expect(detectTtl(tail)).toBe(5)
  })

  test('nothing written: undefined', async () => {
    expect(detectTtl(line({ type: 'user' }))).toBe(undefined)
  })

  test('override beats detection beats the 60-minute default', async () => {
    expect(resolveTtl(30, 5)).toEqual({ minutes: 30, source: 'set' })
    expect(resolveTtl(null, 5)).toEqual({ minutes: 5, source: 'auto' })
    expect(resolveTtl(null, null)).toEqual({ minutes: 60, source: 'default' })
  })

  test('/cache-ttl arguments', async () => {
    expect(parseTtlArg('auto')).toBe(null)
    expect(parseTtlArg(' 45 ')).toBe(45)
    expect(parseTtlArg('5m')).toBe(5)
    expect(parseTtlArg('60min')).toBe(60)
    expect(parseTtlArg('-3')).toBe('invalid')
    expect(parseTtlArg('soon')).toBe('invalid')
  })

  test('transcript folder name', async () => {
    expect(projectDirName('/Users/a/IdeaProjects/flip')).toBe('-Users-a-IdeaProjects-flip')
  })
})

describe('cost', () => {
  test('most specific model wins', async () => {
    expect(priceFor('claude-opus-5-5')?.input).toBe(4)
    expect(priceFor('claude-opus-5')?.input).toBe(5)
    expect(priceFor('claude-fable-5-1')?.cacheRead).toBe(0.25)
    expect(priceFor('claude-sonnet-4-6')?.input).toBe(3)
    expect(priceFor('gpt-something')).toBe(undefined)
  })

  test('cold next message re-writes the context at the TTL write rate', async () => {
    // 200k tokens on Opus 5.5: $4/MTok input, 2x for 1-hour writes, $0.20/MTok reads
    const hour = nextMessageCost(200_000, 'claude-opus-5-5', 60)
    expect(Math.abs((hour?.cold ?? NaN) - 1.6) < 1e-9).toBe(true)
    expect(Math.abs((hour?.warm ?? NaN) - 0.04) < 1e-9).toBe(true)
    expect(Math.abs((nextMessageCost(200_000, 'claude-opus-5-5', 5)?.cold ?? NaN) - 1.0) < 1e-9).toBe(true)
  })

  test('countdown format', async () => {
    expect(formatCountdown(0)).toBe('cold')
    expect(formatCountdown(65_000)).toBe('1:05')
    expect(formatCountdown(3_600_000)).toBe('1:00:00')
  })
})
