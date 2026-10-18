// Pure helpers: the checklist from each task-list tool, phases, progress and formatting.
// No `$` here, so tests can call them directly.

import type { Item, ItemStatus, Phase, Plan, SessionSummary } from '../types'

export const PHASES: Phase[] = ['researching', 'planning', 'building', 'testing', 'auditing']

export const EMPTY_PLAN: Plan = {
  goal: null,
  goalSource: null,
  items: [],
  phase: null,
  startedAt: null,
  finishedAt: null,
}

// --- The checklist, from whichever task-list tool Claude uses ---

// The desktop app's task list: `items` replaces the list; `advance`, `done` and `start` move it on.
export type UpdatePlanInput = {
  items?: ReadonlyArray<{ content: string; status: string }>
  advance?: boolean
  done?: readonly number[]
  start?: number
}

function asStatus(status: string): ItemStatus {
  return status === 'completed' || status === 'in_progress' ? status : 'pending'
}

export function applyUpdatePlan(items: readonly Item[], input: UpdatePlanInput): Item[] {
  let next: Item[] = input.items
    ? input.items.map(i => ({ content: i.content, status: asStatus(i.status) }))
    : items.map(i => ({ ...i }))
  if (input.advance) {
    const current = next.findIndex(i => i.status === 'in_progress')
    if (current >= 0) next[current] = { ...next[current]!, status: 'completed' }
    const after = next.findIndex((i, n) => n > current && i.status === 'pending')
    if (after >= 0) next[after] = { ...next[after]!, status: 'in_progress' }
  }
  for (const n of input.done ?? []) {
    if (next[n - 1]) next[n - 1] = { ...next[n - 1]!, status: 'completed' }
  }
  if (input.start !== undefined && next[input.start - 1]) {
    next = next.map((i, n) =>
      n === input.start! - 1 ? { ...i, status: 'in_progress' } : i.status === 'in_progress' ? { ...i, status: 'pending' } : i,
    )
  }
  return next
}

// The app's wrap-up checks off whatever is left.
export function completeAll(items: readonly Item[]): Item[] {
  return items.map(i => ({ ...i, status: 'completed' }))
}

// The terminal's TodoWrite: the whole list each time.
export function applyTodoWrite(todos: ReadonlyArray<{ content: string; status: string }>): Item[] {
  return todos.map(t => ({ content: t.content, status: asStatus(t.status) }))
}

// The terminal's TaskCreate / TaskUpdate: one task at a time, by id.
export function applyTaskCreate(items: readonly Item[], id: string, subject: string): Item[] {
  return [...items.filter(i => i.id !== id), { id, content: subject, status: 'pending' }]
}

export function applyTaskUpdate(
  items: readonly Item[],
  update: { taskId: string; status?: string; subject?: string },
): Item[] {
  if (update.status === 'deleted') return items.filter(i => i.id !== update.taskId)
  return items.map(i =>
    i.id === update.taskId
      ? { ...i, content: update.subject ?? i.content, status: update.status ? asStatus(update.status) : i.status }
      : i,
  )
}

// --- Plan lifecycle ---

export function isPlanVisible(plan: Plan): boolean {
  return plan.goal !== null || plan.items.length >= 2
}

export function isComplete(plan: Plan): boolean {
  return plan.items.length > 0 && plan.items.every(i => i.status === 'completed')
}

// Puts a new checklist on the plan: a finished plan starts over, a running one keeps its clock and goal.
export function withItems(plan: Plan, items: Item[], now: number, lastPrompt: string | null): Plan {
  const restart = plan.finishedAt !== null && items.some(i => i.status !== 'completed')
  const base = restart ? { ...EMPTY_PLAN, goal: plan.goalSource === 'goal' ? plan.goal : null, goalSource: plan.goalSource === 'goal' ? plan.goalSource : null } : plan
  const goal = base.goal ?? (items.length > 0 ? goalFromPrompt(lastPrompt) : null)
  const next: Plan = {
    ...base,
    items,
    goal,
    goalSource: base.goalSource ?? (goal !== null ? 'prompt' : null),
    startedAt: base.startedAt ?? (items.length > 0 ? now : null),
    phase: phaseFromText(items.find(i => i.status === 'in_progress')?.content) ?? base.phase,
  }
  const complete = isComplete(next)
  return { ...next, finishedAt: complete ? (plan.finishedAt ?? now) : null }
}

export function goalFromPrompt(prompt: string | null): string | null {
  if (!prompt) return null
  const line = prompt.trim().split('\n')[0]?.trim() ?? ''
  if (line === '') return null
  return line.length > 140 ? `${line.slice(0, 137)}…` : line
}

// --- Phase ---

const TEXT_PHASES: Array<[Phase, RegExp]> = [
  ['auditing', /\b(audit|review|security|lint|polish|clean ?up)\w*/i],
  ['testing', /\b(test|verify|verif|check|validat|ci\b|qa\b|reproduc)\w*/i],
  ['planning', /\b(plan|design|outline|decide|propos|spec)\w*/i],
  ['researching', /\b(research|investigat|explor|read|look|find|search|understand|survey|learn|inspect)\w*/i],
  ['building', /\b(implement|build|write|add|creat|fix|edit|refactor|updat|wire|port|migrat|install|make)\w*/i],
]

export function phaseFromText(text: string | undefined): Phase | undefined {
  if (!text) return undefined
  return TEXT_PHASES.find(([, re]) => re.test(text))?.[0]
}

const TEST_COMMAND = /\b(test|tests|pytest|jest|vitest|cargo (test|nextest)|go test|make (test|check)|ci-local|tsc|clippy|validate)\b/i

export function phaseFromTool(tool: string, input: unknown): Phase | undefined {
  const name = String(tool)
  if (/^(Read|Grep|Glob|LS|WebFetch|WebSearch|ToolSearch)$/.test(name)) return 'researching'
  if (/^(EnterPlanMode|ExitPlanMode)$/.test(name)) return 'planning'
  if (/^(Edit|Write|MultiEdit|NotebookEdit)$/.test(name)) return 'building'
  if (name === 'Bash') {
    const command = String((input as { command?: unknown } | undefined)?.command ?? '')
    return TEST_COMMAND.test(command) ? 'testing' : undefined
  }
  if (name === 'Skill') {
    const skill = String((input as { skill?: unknown } | undefined)?.skill ?? '')
    return /review|audit|security/.test(skill) ? 'auditing' : undefined
  }
  return undefined
}

// --- Progress and formatting ---

export function progress(items: readonly Item[]): { done: number; total: number; percent: number } {
  const total = items.length
  const done = items.filter(i => i.status === 'completed').length
  return { done, total, percent: total === 0 ? 0 : Math.round((done / total) * 100) }
}

export function bar(percent: number, width: number): string {
  const filled = Math.round((Math.max(0, Math.min(100, percent)) / 100) * width)
  return '█'.repeat(filled) + '░'.repeat(width - filled)
}

export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`
  return `${m}m ${String(s).padStart(2, '0')}s`
}

// --- Other sessions ---

const STALE_MS = 6 * 3_600_000
const KEEP_FINISHED_MS = 30 * 60_000

// Which published summaries the All tasks view shows: recent, with a plan, and not long finished.
export function visibleOthers(all: readonly SessionSummary[], selfId: string, now: number): SessionSummary[] {
  return all
    .filter(s => s.sessionId !== selfId)
    .filter(s => now - s.updatedAt < STALE_MS)
    .filter(s => s.goal !== null || s.total >= 2)
    .filter(s => s.finishedAt === null || now - s.finishedAt < KEEP_FINISHED_MS)
    .sort((a, b) => b.updatedAt - a.updatedAt)
}

export function parseSummary(text: string): SessionSummary | undefined {
  try {
    const s = JSON.parse(text)
    return typeof s?.sessionId === 'string' && typeof s?.updatedAt === 'number' ? (s as SessionSummary) : undefined
  } catch {
    return undefined
  }
}
