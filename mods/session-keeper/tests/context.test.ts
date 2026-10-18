import { describe, expect, test } from 'claude-code/testing'

import {
  coldWarningText,
  formatTokens,
  levelFor,
  parseAutoArgs,
  parseRowsArgs,
  shouldAutoHandoff,
  warnLeadMin,
} from '../hooks/logic'

describe('levels', () => {
  test('ok below warn, warn at or above it, handoff at the auto threshold', async () => {
    expect(levelFor(undefined, 40, null)).toBe('unknown')
    expect(levelFor(39, 40, null)).toBe('ok')
    expect(levelFor(40, 40, null)).toBe('warn')
    expect(levelFor(95, 40, null)).toBe('warn')
    expect(levelFor(70, 40, 70)).toBe('handoff')
    expect(levelFor(69, 40, 70)).toBe('warn')
  })

  test('auto handoff only when on, reached and not already running', async () => {
    expect(shouldAutoHandoff(80, 70, false)).toBe(true)
    expect(shouldAutoHandoff(80, 70, true)).toBe(false)
    expect(shouldAutoHandoff(60, 70, false)).toBe(false)
    expect(shouldAutoHandoff(99, null, false)).toBe(false)
    expect(shouldAutoHandoff(undefined, 70, false)).toBe(false)
  })
})

describe('/autohandoff arguments', () => {
  test('status, off, a threshold, a warn threshold', async () => {
    expect(parseAutoArgs('')).toEqual({ kind: 'status' })
    expect(parseAutoArgs('off')).toEqual({ kind: 'off' })
    expect(parseAutoArgs('70')).toEqual({ kind: 'auto', percent: 70 })
    expect(parseAutoArgs(' 65% ')).toEqual({ kind: 'auto', percent: 65 })
    expect(parseAutoArgs('warn 35')).toEqual({ kind: 'warn', percent: 35 })
  })

  test('rejects nonsense', async () => {
    expect(parseAutoArgs('0')).toEqual({ kind: 'invalid' })
    expect(parseAutoArgs('150')).toEqual({ kind: 'invalid' })
    expect(parseAutoArgs('warn')).toEqual({ kind: 'invalid' })
    expect(parseAutoArgs('soon')).toEqual({ kind: 'invalid' })
    expect(parseAutoArgs('70 80')).toEqual({ kind: 'invalid' })
  })

  test('token format', async () => {
    expect(formatTokens(412_345)).toBe('412k')
    expect(formatTokens(1_000_000)).toBe('1M')
  })
})

describe('the combined pieces', () => {
  test('the cache warning offers a handoff only when the context is large', async () => {
    expect(coldWarningText(5, 20, 40)).toBe('Prompt cache goes cold in 5 min. Send a message to keep it warm.')
    expect(coldWarningText(5, 62, 40).includes('context is at 62%')).toBe(true)
    expect(coldWarningText(5, undefined, 40).includes('handoff')).toBe(false)
    expect(warnLeadMin(60)).toBe(5)
    expect(warnLeadMin(5)).toBe(1)
  })

  test('/session-keeper show|hide', async () => {
    expect(parseRowsArgs('hide cache')).toEqual({ row: 'cache', isShown: false })
    expect(parseRowsArgs('show context')).toEqual({ row: 'context', isShown: true })
    expect(parseRowsArgs('hide')).toBe(undefined)
    expect(parseRowsArgs('toggle cache')).toBe(undefined)
  })
})
