# save-sessions

Snapshots the IDs of live Claude Code sessions to `~/.claude/saved-sessions.json` so they
can be bulk-resumed after an IDE or machine restart. Run it when you are about to restart
something that would otherwise take your open sessions with it.

## What it captures

Every transcript under `~/.claude/projects/` modified within the window (default 24
hours; pass a different count as the first argument). For each one: the session ID, the
directory to resume it in, and a title picked from the custom title (`/rename`), falling
back to the auto-assigned summary, then the last user prompt.

Three things it deliberately handles:

**Subagent transcripts look like sessions.** An Agent-tool task run gets its own
`<uuid>.jsonl`, identical in shape to a real one. The discriminator is the `entrypoint`
field in the first lines - `sdk-cli` marks a subagent, `cli` a real session. These are
filtered out, including ones an older save captured before the filter existed.

**Re-saving must not lose sessions.** Saved Friday, re-saved Monday with the default
window, the Friday entries would be silently dropped - so the script merges into the
existing file instead of overwriting it.

**The current session is the one you want back first.** `currentSessionId` is read from
`$CLAUDE_CODE_SESSION_ID` (exact, when the script runs inside a Claude session), with the
newest-modified transcript as fallback - and flagged `current: true` so the restore can
skip it and put it first in the report.

## Script first

`save-sessions.sh` implements all of the above; the SKILL.md tells Claude to run it and
treat the manual procedure as a fallback. Requires `python3`, which does the actual scan.

## The restore side

[`resume-sessions`](../resume-sessions) reads the same file and relaunches everything in
tmux windows. Saving is only worth doing if that side exists.
