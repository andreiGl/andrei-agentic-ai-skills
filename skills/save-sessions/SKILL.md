---
name: save-sessions
description: Snapshot the IDs of currently active Claude Code sessions to a file so they can be bulk-resumed later (e.g., after restarting IntelliJ or the machine). Use when the user asks to save current sessions, checkpoint sessions, or prepare for a restart.
---

# Save active Claude Code sessions

Your job is to find the currently active Claude Code session IDs and write them to a restore file.

## The script is the primary path

Run `save-sessions.sh` (same directory, optional arg = window hours, default 24):

```bash
~/.claude/skills/save-sessions/save-sessions.sh
```

It implements everything below: 24-hour scan, title priority (custom title -> auto summary -> last prompt), merge into the existing save file, `currentSessionId` + `current: true`, and subagent-transcript exclusion. Verify its one-line-per-session output, then report to the user as described in step 6. Follow the manual procedure below only if the script fails.

## Where sessions live

Claude Code stores each session transcript as a JSONL file under:

```
~/.claude/projects/<encoded-project-path>/<session-id>.jsonl
```

`<encoded-project-path>` is the absolute project path with `/` replaced by `-` (e.g. `/Users/me/myapp` -> `-Users-me-myapp`).

A session is "recently active" if its `.jsonl` file was modified within WINDOW_HOURS (default 24). There is no reliable daemon API for "currently open in the IDE", so recency is the proxy we use.

Note: sessions running inside tmux survive an IDE restart - only the terminal dies, and `tmux attach` brings them back without any resume. This save file is what brings sessions back after a machine restart or when the tmux server is gone.

## Steps

1. Determine the cutoff: `$NOW - WINDOW_HOURS` where `WINDOW_HOURS` defaults to 24 (ask the user only if they hint at a different scope, e.g. "just today's sessions").

2. List candidate sessions, newest first. On macOS (BSD stat):

```bash
find ~/.claude/projects -name '*.jsonl' -mmin -$((WINDOW_HOURS*60)) -exec stat -f '%m %N' {} + | sort -rn
```

(On GNU/Linux, use `find ... -printf '%T@ %p\n' | sort -rn` instead.)

3. Identify the current session. Inside a Claude session, `$CLAUDE_CODE_SESSION_ID` holds the exact id (it inherits into Bash-tool shells). Without that env var (script run from a plain terminal), fall back to the newest-modified transcript - the session being written while you run. Record the id as `currentSessionId` at the top level of the save file, and keep it in the sessions list too, marked `"current": true` - after a restart it is usually the first session the user wants back.

Subagent transcripts (Agent-tool task runs) get their own `<uuid>.jsonl` that looks like a real session in content. Distinguish by the `entrypoint` field in the first lines: subagents carry `"entrypoint":"sdk-cli"`, interactive sessions `"entrypoint":"cli"`. Never list subagent transcripts in the save file.

4. For each candidate, extract metadata for a readable restore list. Title priority: custom title -> auto-assigned summary -> last user prompt.

Custom titles (set via `/rename` or `--name`) are NOT in the transcript - they live in a sidecar file next to it:

```
~/.claude/projects/<encoded-project-path>/<session-id>/custom-title.json
```

with shape `{"customTitle": "..."}`. Read it first; only fall back to the transcript if it's missing:

```bash
jq -r '.customTitle // empty' "<dir>/<session-id>/custom-title.json" 2>/dev/null
jq -r 'select(.type=="summary") | .summary' <file> | tail -1   # auto-assigned summary if present
jq -r 'select(.type=="user") | .message.content | if type=="string" then . else (map(select(.type=="text")|.text)|join(" ")) end' <file> 2>/dev/null | grep -v '^\s*$' | tail -1 | cut -c1-120   # last user prompt
```

Also record:

- `cwd` - NOT necessarily on the first line: the first line may be a `mode` record with no `cwd`. Take it from the first line that has one:
  `jq -r 'select(.cwd != null) | .cwd' <file> | head -1`
  (this is the directory the session must be resumed **in**).
- `sessionId` - the filename without `.jsonl`.
- `entrypoint` - first record that carries one; `"sdk-cli"` marks a subagent transcript to skip.

5. Write the result as JSON to `~/.claude/saved-sessions.json` (create `~/.claude/` if needed). If a save file already exists, merge instead of overwriting: new captures replace same-`sessionId` entries, and entries that were NOT re-captured are kept (e.g. sessions saved Friday, re-saving Monday with the default 24h window - without merging they would be silently dropped). Update `savedAt` and `currentSessionId`, and move the `current: true` flag to the new current session. Schema:

```json
{
  "savedAt": "2026-09-12T10:00:00-07:00",
  "windowHours": 24,
  "currentSessionId": "a1b2c3d4-....",
  "sessions": [
    {
      "sessionId": "a1b2c3d4-....",
      "cwd": "/Users/me/myapp",
      "summary": "Refactor auth middleware",
      "lastPrompt": "fix the failing test in session.py",
      "current": true
    }
  ]
}
```

6. Confirm to the user how many sessions were saved and list them one line each (`summary or lastPrompt - cwd`), marking the current one. Remind them: after a restart they can say "resume my saved sessions" (the `resume-sessions` skill reads this same file); if the sessions run inside tmux and only the IDE restarts, `tmux attach` alone is enough.

## Notes

- Skip session files that are empty or contain no `user` entries.
- Skip subagent transcripts (`"entrypoint":"sdk-cli"`), including ones an older save captured before the filter existed.
- If the same session was already saved before, overwrite the entry (dedupe by `sessionId`).
- Never modify the JSONL files themselves.
- Known limitation: a DEAD subagent transcript (task run from a session that has since exited) has `"entrypoint":"sdk-cli"` still, so the filter catches it - but a subagent transcript from a run whose first line lacks the field (future format change) would slip through. If the save list ever shows a session the user does not recognize, check its entrypoint before resuming it.
