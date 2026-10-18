export type Phase = 'researching' | 'planning' | 'building' | 'testing' | 'auditing'

export type ItemStatus = 'pending' | 'in_progress' | 'completed'

export type Item = { id?: string; content: string; status: ItemStatus }

export type Plan = {
  goal: string | null
  // Where the goal came from: /goal (or a goal Claude proposed), or the prompt that started the plan.
  goalSource: 'goal' | 'prompt' | null
  items: Item[]
  phase: Phase | null
  startedAt: number | null
  finishedAt: number | null
}

// What a session publishes for the All tasks view of other sessions.
export type SessionSummary = {
  sessionId: string
  project: string
  goal: string | null
  phase: Phase | null
  done: number
  total: number
  startedAt: number | null
  finishedAt: number | null
  updatedAt: number
  isWorking: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'plan-progress': {
      plan: Plan
      // The text of the last prompt the person sent, the goal when no /goal is set.
      lastPrompt: string | null
      view: 'session' | 'all'
      others: SessionSummary[]
      isWorking: boolean
      isSoundOn: boolean
    }
  }
}
