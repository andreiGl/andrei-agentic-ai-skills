// Pure helpers: the exchange under review, the reviewer's prompt, and reading its answer.
// No `$` here, so tests can call them directly.

import type { Critique, Flaw, Reviewer, Verdict } from '../types'

export const REVIEWERS: Array<{ value: Reviewer; label: string }> = [
  { value: 'session', label: 'Same as session' },
  { value: 'opus', label: 'Opus' },
  { value: 'sonnet', label: 'Sonnet' },
  { value: 'haiku', label: 'Haiku' },
]

export function isReviewer(value: unknown): value is Reviewer {
  return REVIEWERS.some(r => r.value === value)
}

type Message = {
  role: 'user' | 'assistant'
  text: string
  toolUses: ReadonlyArray<{ tool: string; input: Record<string, unknown>; isError?: true }>
  toolResults?: readonly unknown[]
}

export type Exchange = { request: string; response: string; tools: string[] }

// The person's latest prompt and everything Claude answered after it.
// A user row that only carries tool results is part of the response, not a new prompt.
export function lastExchange(messages: readonly Message[]): Exchange | undefined {
  let start = -1
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]!
    if (m.role === 'user' && m.text.trim() !== '' && (m.toolResults?.length ?? 0) === 0) {
      start = i
      break
    }
  }
  if (start < 0) return undefined
  const after = messages.slice(start + 1).filter(m => m.role === 'assistant')
  const response = after.map(m => m.text.trim()).filter(Boolean).join('\n\n')
  const tools = after.flatMap(m => m.toolUses.map(u => describeTool(u)))
  if (response === '' && tools.length === 0) return undefined
  return { request: messages[start]!.text.trim(), response, tools }
}

function describeTool(use: { tool: string; input: Record<string, unknown>; isError?: true }): string {
  const hint = ['command', 'file_path', 'path', 'pattern', 'url', 'query']
    .map(k => use.input[k])
    .find(v => typeof v === 'string') as string | undefined
  const short = hint ? `: ${hint.length > 120 ? `${hint.slice(0, 117)}…` : hint}` : ''
  return `${use.tool}${short}${use.isError ? ' (failed)' : ''}`
}

const RUBRIC = `Judge it as a strict, fair senior reviewer would. Check:
- Did it do what was asked, all of it, and nothing that was not asked?
- Is every claim correct and supported, and does it say plainly what it did not verify?
- Is the work itself sound: correct code, safe actions, no missed edge cases?
- Is it clear and no longer than it needs to be?

Do not flatter. Name a strength only if it is real and specific. List flaws most serious first; each fix must be a concrete instruction Claude could act on. If there are no real flaws, return an empty list rather than inventing some. At most 5 strengths and 6 flaws.

Answer with JSON alone, no prose around it, in exactly this shape:
{"verdict": "Strong" | "Mixed" | "Weak", "summary": "<two sentences at most>", "strengths": ["..."], "flaws": [{"flaw": "...", "fix": "..."}]}`

// For the session's own model: it already has the conversation, so the prompt only points at the last answer.
export const FORK_PROMPT = `Step outside the conversation and review your own last response: everything you answered after the person's latest message, including the tool calls you made. Do not continue the work and do not call any tools.

${RUBRIC}`

// For another model: it has no history, so the prompt carries the exchange.
export function standalonePrompt(exchange: Exchange): string {
  const tools = exchange.tools.length === 0 ? '(none)' : exchange.tools.map(t => `- ${t}`).join('\n')
  return `Below is one exchange between a person and Claude, an AI assistant working in their software project. Review Claude's response. You see only this exchange, not the conversation before it; where judging needs context you lack, say so rather than guessing.

<request>
${clip(exchange.request, 20_000)}
</request>

<tool_calls>
${clip(tools, 10_000)}
</tool_calls>

<response>
${clip(exchange.response, 60_000)}
</response>

${RUBRIC}`
}

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}\n[… ${text.length - max} more characters left out]` : text
}

const VERDICTS: Verdict[] = ['Strong', 'Mixed', 'Weak']

// Reads the reviewer's JSON, tolerating a code fence or stray prose around it.
export function parseCritique(text: string): Critique | undefined {
  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start < 0 || end <= start) return undefined
  let raw: any
  try {
    raw = JSON.parse(text.slice(start, end + 1))
  } catch {
    return undefined
  }
  const verdict = VERDICTS.find(v => v.toLowerCase() === String(raw?.verdict ?? '').toLowerCase())
  if (!verdict) return undefined
  const strings = (v: unknown) => (Array.isArray(v) ? v.filter((s): s is string => typeof s === 'string' && s.trim() !== '') : [])
  const flaws: Flaw[] = Array.isArray(raw?.flaws)
    ? raw.flaws
        .filter((f: any) => typeof f?.flaw === 'string' && f.flaw.trim() !== '')
        .map((f: any) => ({ flaw: f.flaw.trim(), fix: typeof f.fix === 'string' ? f.fix.trim() : '' }))
    : []
  return {
    verdict,
    summary: typeof raw?.summary === 'string' ? raw.summary.trim() : '',
    strengths: strings(raw?.strengths).map(s => s.trim()),
    flaws,
  }
}

export function fixPrompt(flaw: Flaw): string {
  return `A review of your last response found this problem:\n\n${flaw.flaw}\n\nPlease fix it.${
    flaw.fix ? ` Suggested fix: ${flaw.fix}` : ''
  }`
}
