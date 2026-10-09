import type { KbSnapshot } from './index.d.ts'

// Same thresholds kb-maintenance-check.py applies, so band and hook never disagree.
export const SYNTH_EXPERIENCE_THRESHOLD = 5
export const SYNTH_LEARNINGS_THRESHOLD = 20
export const SYNTH_MAX_AGE_DAYS = 61
export const CHECK_MAX_AGE_DAYS = 14

// Session main-loop tool uses past which the tools segment turns amber, matching
// kb-session-end.sh's KB_EXPERIENCE_MIN_TOOL_USES default.
export const DEBT_TOOL_RED = 40
export const DEFAULT_DEBT_TOOL_THRESHOLD = 20

export type Verdict = { kind: 'ok' | 'check' | 'synthesize' | 'absent'; reasons: string[] }

export function emptySnapshot(): KbSnapshot {
  return {
    experiences: 0,
    learnings: 0,
    verifiedDays: null,
    synthesizedDays: null,
    dirtyFiles: 0,
    sessionEntries: 0,
    present: false,
  }
}

export function matchDate(text: string, label: string): string | null {
  const line = text
    .split('\n')
    .find((candidate) => candidate.startsWith(`**${label}:**`))
  if (line === undefined) return null
  const value = line.slice(`**${label}:**`.length).trim()
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null
}

export function daysSince(iso: string | null): number | null {
  if (iso === null) return null
  const then = Date.parse(`${iso}T00:00:00Z`)
  if (Number.isNaN(then)) return null
  const today = Date.parse(new Date().toISOString().slice(0, 10) + 'T00:00:00Z')
  return Math.round((today - then) / 86_400_000)
}

export function debtToolThresholdOf(rawValue: string | undefined): number {
  if (rawValue === undefined || !/^\d+$/.test(rawValue.trim())) {
    return DEFAULT_DEBT_TOOL_THRESHOLD
  }
  const parsed = Number.parseInt(rawValue.trim(), 10)
  return parsed > 0 ? parsed : DEFAULT_DEBT_TOOL_THRESHOLD
}

export function verdictOf(snapshot: KbSnapshot): Verdict {
  if (!snapshot.present) return { kind: 'absent', reasons: [] }
  const reasons: string[] = []
  if (snapshot.experiences >= SYNTH_EXPERIENCE_THRESHOLD) {
    reasons.push(`${snapshot.experiences} experiences >= ${SYNTH_EXPERIENCE_THRESHOLD}`)
  }
  if (snapshot.learnings > SYNTH_LEARNINGS_THRESHOLD) {
    reasons.push(`${snapshot.learnings} learnings > ${SYNTH_LEARNINGS_THRESHOLD}`)
  }
  if (snapshot.synthesizedDays === null) {
    reasons.push('Last synthesized missing')
  } else if (snapshot.synthesizedDays > SYNTH_MAX_AGE_DAYS) {
    reasons.push(`synthesized ${snapshot.synthesizedDays}d ago`)
  }
  if (reasons.length > 0) return { kind: 'synthesize', reasons }
  if (snapshot.verifiedDays === null || snapshot.verifiedDays > CHECK_MAX_AGE_DAYS) {
    return { kind: 'check', reasons: ['last verified stale'] }
  }
  return { kind: 'ok', reasons: [] }
}

export type Action = {
  key: string
  label: string
  prompt: string
  /** Theme key of the due condition: 'error' or 'warning'. */
  color: 'error' | 'warning'
}

// One action per due segment; none when nothing is owed (the band stays empty).
export function actionsOf(
  snapshot: KbSnapshot,
  verdict: Verdict,
  toolUses: number,
  toolThreshold: number,
  debtCount: number,
): Action[] {
  const actions: Action[] = []
  if (verdict.kind === 'synthesize') {
    actions.push({
      key: 'synthesize',
      label: `KB synthesize due - run synthesize-knowledge`,
      color: 'error',
      prompt:
        'Run the synthesize-knowledge skill now. The KB line reported: '
        + (verdict.reasons.length > 0 ? verdict.reasons.join('; ') : 'synthesis due'),
    })
  } else if (verdict.kind === 'check') {
    actions.push({
      key: 'check',
      label: `KB check due - run check-knowledge`,
      color: 'warning',
      prompt:
        'Run the check-knowledge skill now. The KB line reported: '
        + (verdict.reasons.length > 0 ? verdict.reasons.join('; ') : 'verification stale'),
    })
  }
  if (debtCount > 0) {
    actions.push({
      key: 'debt',
      label: `${debtCount} KB debt - run update-knowledge`,
      color: 'error',
      prompt:
        'Run the update-knowledge skill now: earlier sessions ended without an experience entry; '
        + `apply update-knowledge for the reusable findings or explain why an entry is not needed (${debtCount} pending).`,
    })
  }
  if (snapshot.present && snapshot.dirtyFiles > 0) {
    actions.push({
      key: 'uncommitted',
      label: `${snapshot.dirtyFiles} KB uncommitted - commit`,
      color: 'warning',
      prompt:
        `Commit and push the knowledge base at ~/.claude/knowledge. ${snapshot.dirtyFiles} modified files. `
        + 'Review git status first: commit only real KB content (page updates, new entries, INDEX rows); '
        + 'never commit scratch, temp, or test files - delete or leave those. Terse commit summary, then push origin main.',
    })
  }
  // The tools figure counts UNBANKED work: main-loop tool uses after the newest
  // experience entry (register.tsx computes it; the contract's toolUses carries
  // that number). An entry banked this session resets it toward zero, so no
  // suppression rule is needed - the count itself falls below the threshold.
  if (toolUses >= toolThreshold) {
    actions.push({
      key: 'tools',
      label: `${toolUses} tools, no entry yet - run update-knowledge`,
      color: toolUses >= DEBT_TOOL_RED ? 'error' : 'warning',
      prompt:
        'Run the update-knowledge skill now: this session has passed the experience-entry threshold '
        + `(${toolUses} tool uses); write the experience entry for the current session's work, or explain why one is not needed.`,
    })
  }
  return actions
}
