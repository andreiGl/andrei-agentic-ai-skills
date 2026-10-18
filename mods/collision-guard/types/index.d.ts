export type EditRecord = { path: string; at: number }

export type StepStatus = 'pending' | 'in_progress' | 'completed'

export type Step = { id?: string; content: string; status: StepStatus }

// What each session publishes about itself, one file per session, in a folder per project.
export type SessionRecord = {
  sessionId: string
  root: string
  // The first line of the last prompt the person sent: what the session was asked to do.
  task: string | null
  // The session's task list, when it keeps one.
  steps: Step[]
  isWorking: boolean
  startedAt: number
  updatedAt: number
  isEnded: boolean
  // Files this session changed through Edit, Write or NotebookEdit, newest last, the last 30 minutes kept.
  edits: EditRecord[]
}

declare module 'claude-code' {
  interface PluginState {
    'collision-guard': {
      self: SessionRecord | null
      others: SessionRecord[]
      // Files the person already said to go ahead with, by path: the other session's edit time they saw.
      cleared: Record<string, number>
    }
  }
}
