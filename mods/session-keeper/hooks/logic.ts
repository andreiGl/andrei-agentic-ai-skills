// Pure helpers for both rows of the strip: the cache (pricing, TTL, countdown) and the context (thresholds,
// handoff). No `$` here, so tests can call them directly.

// --- Cache ---

export const DEFAULT_TTL_MIN = 60
export const WARN_BEFORE_MIN = 5

// List prices in USD per million tokens. Cache writes are priced from `input`:
// 1.25x for the 5-minute TTL, 2x for the 1-hour TTL.
type Price = { input: number; output: number; cacheRead: number }

// Most specific first: the first entry whose key the model id contains wins.
const PRICES: Array<[string, Price]> = [
  ['fable-5-1', { input: 10, output: 50, cacheRead: 0.25 }],
  ['mythos-5-1', { input: 10, output: 50, cacheRead: 0.25 }],
  ['fable-5', { input: 10, output: 50, cacheRead: 1 }],
  ['mythos-5', { input: 10, output: 50, cacheRead: 1 }],
  ['opus-5-5', { input: 4, output: 20, cacheRead: 0.2 }],
  ['opus-5', { input: 5, output: 25, cacheRead: 0.5 }],
  ['opus-4-1', { input: 15, output: 75, cacheRead: 1.5 }],
  ['opus-4-0', { input: 15, output: 75, cacheRead: 1.5 }],
  ['opus-4', { input: 5, output: 25, cacheRead: 0.5 }],
  ['sonnet-5', { input: 2, output: 10, cacheRead: 0.2 }],
  ['sonnet-4', { input: 3, output: 15, cacheRead: 0.3 }],
  ['haiku-5', { input: 0.1, output: 0.5, cacheRead: 0.01 }],
  ['haiku-4', { input: 1, output: 5, cacheRead: 0.1 }],
  ['opus', { input: 4, output: 20, cacheRead: 0.2 }],
  ['sonnet', { input: 2, output: 10, cacheRead: 0.2 }],
  ['haiku', { input: 0.1, output: 0.5, cacheRead: 0.01 }],
  ['fable', { input: 10, output: 50, cacheRead: 0.25 }],
]

export function priceFor(model: string | null | undefined): Price | undefined {
  if (!model) return undefined
  const id = model.toLowerCase()
  return PRICES.find(([key]) => id.includes(key))?.[1]
}

// What re-sending `tokens` of context costs: cold (re-written to the cache) and warm (read from it).
// Leaves out the new message itself and the reply.
export function nextMessageCost(
  tokens: number,
  model: string | null | undefined,
  ttlMin: number,
): { cold: number; warm: number } | undefined {
  const price = priceFor(model)
  if (!price) return undefined
  const writeMultiplier = ttlMin > 5 ? 2 : 1.25
  return {
    cold: (tokens * price.input * writeMultiplier) / 1e6,
    warm: (tokens * price.cacheRead) / 1e6,
  }
}

// The folder name Claude Code files a project's transcripts under.
export function projectDirName(projectPath: string): string {
  return projectPath.replace(/[^a-zA-Z0-9]/g, '-')
}

// Reads the TTL from the newest main-thread cache write in a transcript tail (JSONL).
// Returns minutes, or undefined when no line in the tail wrote to the cache.
export function detectTtl(jsonlTail: string): number | undefined {
  const lines = jsonlTail.split('\n')
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i] ?? ''
    if (!line.includes('"cache_creation"')) continue
    let entry: any
    try {
      entry = JSON.parse(line)
    } catch {
      continue // the first line of a tail is usually cut
    }
    if (entry?.type !== 'assistant' || entry?.isSidechain) continue
    const creation = entry?.message?.usage?.cache_creation
    if (!creation) continue
    if ((creation.ephemeral_1h_input_tokens ?? 0) > 0) return 60
    if ((creation.ephemeral_5m_input_tokens ?? 0) > 0) return 5
  }
  return undefined
}

export function resolveTtl(
  override: number | null,
  detected: number | null,
): { minutes: number; source: 'set' | 'auto' | 'default' } {
  if (override !== null) return { minutes: override, source: 'set' }
  if (detected !== null) return { minutes: detected, source: 'auto' }
  return { minutes: DEFAULT_TTL_MIN, source: 'default' }
}

// Parses /cache-ttl's argument: "auto" clears the override, a positive number of minutes sets it.
export function parseTtlArg(args: string): number | null | 'invalid' {
  const word = args.trim().toLowerCase().replace(/m(in(utes?)?)?$/, '')
  if (word === 'auto' || word === '') return null
  const n = Number(word)
  return Number.isFinite(n) && n > 0 && n <= 24 * 60 ? n : 'invalid'
}

export function formatCountdown(ms: number): string {
  if (ms <= 0) return 'cold'
  const total = Math.ceil(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export function formatUsd(usd: number): string {
  if (usd >= 100) return `$${usd.toFixed(0)}`
  if (usd >= 0.995) return `$${usd.toFixed(2)}`
  return `$${usd.toFixed(3)}`
}

export function formatResetIn(resetsAt: string | undefined, now: number): string {
  if (!resetsAt) return ''
  const ms = Date.parse(resetsAt) - now
  if (!Number.isFinite(ms) || ms <= 0) return ''
  const hours = ms / 3_600_000
  if (hours >= 48) return ` ${Math.round(hours / 24)}d`
  if (hours >= 1) return ` ${Math.floor(hours)}h${String(Math.floor((ms % 3_600_000) / 60_000)).padStart(2, '0')}`
  return ` ${Math.max(1, Math.round(ms / 60_000))}m`
}

// --- Context ---

// Long-context quality tends to slip well before the window is full; 40% is a cautious default.
export const DEFAULT_WARN_AT = 40

export type Level = 'unknown' | 'ok' | 'warn' | 'handoff'

export function levelFor(percent: number | undefined, warnAt: number, autoAt: number | null): Level {
  if (percent === undefined) return 'unknown'
  if (autoAt !== null && percent >= autoAt) return 'handoff'
  if (percent >= warnAt) return 'warn'
  return 'ok'
}

// Whether a finished turn should hand off by itself: auto is on, the fill reached it, no handoff is running.
export function shouldAutoHandoff(percent: number | undefined, autoAt: number | null, isBusy: boolean): boolean {
  return !isBusy && autoAt !== null && percent !== undefined && percent >= autoAt
}

export type AutoCommand =
  | { kind: 'status' }
  | { kind: 'off' }
  | { kind: 'auto'; percent: number }
  | { kind: 'warn'; percent: number }
  | { kind: 'invalid' }

function parsePercent(word: string | undefined): number | undefined {
  if (word === undefined) return undefined
  const n = Number(word.replace(/%$/, ''))
  return Number.isFinite(n) && n >= 1 && n <= 100 ? n : undefined
}

// /autohandoff            -> status
// /autohandoff 70         -> hand off by itself at 70%
// /autohandoff off        -> stop handing off by itself
// /autohandoff warn 40    -> warn at 40%
export function parseAutoArgs(args: string): AutoCommand {
  const words = args.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return { kind: 'status' }
  if (words.length === 1 && (words[0] === 'off' || words[0] === 'disable')) return { kind: 'off' }
  if (words[0] === 'warn') {
    const percent = parsePercent(words[1])
    return words.length === 2 && percent !== undefined ? { kind: 'warn', percent } : { kind: 'invalid' }
  }
  const percent = parsePercent(words[0])
  return words.length === 1 && percent !== undefined ? { kind: 'auto', percent } : { kind: 'invalid' }
}

export function formatTokens(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(n % 1e6 === 0 ? 0 : 2)}M`
  if (n >= 1e3) return `${Math.round(n / 1e3)}k`
  return String(n)
}

export const HANDOFF_PROMPT = `Write a handoff brief so a fresh Claude session, with none of this conversation, can pick up the work where it stands.

Cover, in this order and only where there is something to say:
- Goal: what the person is trying to get done.
- Where it stands: what is finished, what is half-done, what was verified and how.
- Decisions made, and the reasons a newcomer would not guess.
- Files and places that matter: paths, branches, commands, URLs.
- Open questions and known problems.
- Next steps, most important first.

Write it as Markdown, addressed to the next session, with no preamble and no sign-off. Be concrete: names, paths, numbers. Keep it under 500 words. Do not call any tools; answer with the brief alone.`

// Warn ahead of expiry: 5 minutes before on a long window, 1 minute before on the 5-minute one.
export function warnLeadMin(ttlMin: number): number {
  return ttlMin > 2 * WARN_BEFORE_MIN ? WARN_BEFORE_MIN : 1
}

// The cache warning. When the context is already large, a handoff before the cache goes cold is cheaper than
// re-caching it, so the warning says so.
export function coldWarningText(leadMin: number, percent: number | undefined, warnAt: number): string {
  if (percent !== undefined && percent >= warnAt) {
    return `Cache goes cold in ${leadMin} min and context is at ${percent}%. Handing off now is cheaper than re-caching it: press 1 or run /handoff.`
  }
  return `Prompt cache goes cold in ${leadMin} min. Send a message to keep it warm.`
}

// /session-keeper show|hide cache|context
export function parseRowsArgs(args: string): { row: 'cache' | 'context'; isShown: boolean } | undefined {
  const words = args.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length !== 2) return undefined
  const [verb, row] = words
  if ((verb !== 'show' && verb !== 'hide') || (row !== 'cache' && row !== 'context')) return undefined
  return { row, isShown: verb === 'show' }
}
