export type Verdict = 'Strong' | 'Mixed' | 'Weak'

// Who reviews: the session's own model over the whole transcript, or a named model over the last exchange.
export type Reviewer = 'session' | 'opus' | 'sonnet' | 'haiku'

export type Flaw = { flaw: string; fix: string }

export type Critique = {
  verdict: Verdict
  summary: string
  strengths: string[]
  flaws: Flaw[]
}

export type Review =
  | { status: 'empty' }
  | { status: 'running'; reviewer: Reviewer }
  | { status: 'error'; reviewer: Reviewer; message: string }
  | { status: 'done'; reviewer: Reviewer; critique: Critique; reviewedAt: number; sent: number[] }

declare module 'claude-code' {
  interface PluginState {
    'self-critique': {
      review: Review
      reviewer: Reviewer
      isAuto: boolean
    }
  }
}
