export type Phase = 'idle' | 'writing' | 'clearing'

// Which rows of the strip are shown.
export type Rows = { cache: boolean; context: boolean }

declare module 'claude-code' {
  interface PluginState {
    'session-keeper': {
      // Start of the last main-thread model request, ms since the epoch.
      // The cache lifetime counts from a request's start.
      anchor: number | null
      // TTL in minutes read from the transcript's cache writes.
      ttlDetected: number | null
      // TTL in minutes set with /cache-ttl; overrides detection.
      ttlOverride: number | null
      // Model id of the last main-thread request.
      model: string | null
      // Context % at which the context row turns yellow and a one-time toast warns.
      warnAt: number
      // Context % at which a handoff runs by itself after a turn; null when off.
      autoAt: number | null
      // Whether this conversation has already been warned (reset by a clear).
      isWarned: boolean
      phase: Phase
      rows: Rows
    }
  }
}
