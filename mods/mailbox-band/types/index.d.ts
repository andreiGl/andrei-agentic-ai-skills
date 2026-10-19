export type MailboxSnapshot = {
  /** Snapshot-shape version; readers drop snapshots with another value */
  schema: number
  /** Script present at ~/.claude/scripts/claude-mail */
  installed: boolean
  /** NICK= from ~/.claude/mailbox/config */
  nick: string
  /** PEER= from ~/.claude/mailbox/config */
  peer: string
  /** This session's map line: name + threads + flags (field 4, e.g. !wake) */
  mapped: { name: string; threads: string; flags: string } | null
  /** live-sessions entries: "<sid8> <socket>" */
  live: { sid: string; socket: string }[]
  /** This session's id (8-char head) */
  sid8: string
  /** This session is in live-sessions (the SessionStart hook ran) */
  liveRegistered: boolean
  /** Daemon process found (pgrep claude-mail daemon) */
  daemon: { running: boolean; pid: string | null }
  /** Daemon cursor lag: seconds since last_seen_created_at */
  lagSeconds: number | null
  /** responder turn in flight */
  responderActive: boolean
  /** Unread per thread for this session's threads (read-only; no cursor consumed) */
  unread: { thread: string; count: number }[]
  /** gh fetch failed (token, network) - unread unknown */
  unreadError: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'mailbox-band': { snap: MailboxSnapshot | null; hidden: boolean }
  }
}
