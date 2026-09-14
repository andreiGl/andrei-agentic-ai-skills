# resume-sessions

Reads `~/.claude/saved-sessions.json` and relaunches every saved session - one tmux
window each, so a whole restored set lives in one terminal tab. The counterpart to
[`save-sessions`](../save-sessions); that file is the only input.

## The two guards

**Self-skip.** Resuming the session that is running the restore would attach a second
interface to a conversation already being driven. Skipped by both the save file's
`currentSessionId` and `$CLAUDE_CODE_SESSION_ID` - either can be stale, and they can
differ when a save from Friday is restored from a fresh session Monday.

**Live-session detection.** Resuming a session that is still open elsewhere does not
fork - it opens a second TUI on the same transcript, and both processes interleave
writes into one file. Detection reads `ps`: interactive Claude processes expose their
session ID as `--session-id <id>` or `--resume <id-or-path>`, filtered to processes on a
real TTY. It is best-effort: IDE-started sessions run as bare `claude` with no ID in
argv and are invisible to it, so the confirmation prompt, not `ps`, is the real guard.

## How the launch works

One plain-shell tmux window per session, then the resume command typed into each with
`send-keys`. A window whose start command exits instantly closes at once - and can kill
a single-window tmux server before anyone looks at it - which is why the command is
never passed as the window's start command. Without tmux installed, `--plain` prints the
resume commands to paste instead. A typo'd or deleted session ID does not error; it
silently opens a fresh conversation, so panes are spot-checked after launch.

## Script first

`resume-sessions.sh` implements all of the above and is bash 3.2 compatible - macOS
`/bin/bash` lacks `mapfile`, and a bash-4-ism crashes silently inside process
substitution where `set -e` cannot catch it.
