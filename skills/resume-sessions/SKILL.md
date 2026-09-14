---
name: resume-sessions
description: Bulk-resume Claude Code sessions previously saved with the save-sessions skill. Reads ~/.claude/saved-sessions.json and relaunches each session - inside tmux windows, so all sessions live in one IntelliJ terminal tab. Use when the user asks to restore/resume saved sessions after a restart.
---

# Resume saved Claude Code sessions

Your job is to read `~/.claude/saved-sessions.json` and relaunch every saved session.

## The script is the primary path

Run `resume-sessions.sh` (same directory). It is bash 3.2 compatible (macOS `/bin/bash` - no `mapfile`):

```bash
~/.claude/skills/resume-sessions/resume-sessions.sh           # tmux launch, asks for confirmation
~/.claude/skills/resume-sessions/resume-sessions.sh --yes     # tmux launch, no confirmation
~/.claude/skills/resume-sessions/resume-sessions.sh --plain   # print resume commands to paste
```

It implements everything below: current-session skip, live-session detection via `ps`, tmux windows with `send-keys`, and adding windows to a surviving `claude-restored` session instead of failing. Its output tells you which sessions it skipped and why - relay that to the user. Follow the manual procedure below only if the script fails.

## The resume command

```bash
claude --resume <session-id>
```

`--resume` works with a session ID (or a session name). A session's context lives in its JSONL transcript, so a session can be resumed from any directory - but it should be resumed from its original `cwd` (recorded in the save file) so relative paths and project context behave correctly.

## Skipping the current session

If the restore is running from inside a Claude Code session (a skill invocation), the session running this skill must be skipped: resuming it from within itself would attach a second interface to a conversation it is already driving. If `currentSessionId` in the save file matches the running session, drop it from the list and tell the user (it was likely started by hand after the restart, or is the live one). After a machine restart the user opens one fresh Claude session and runs the restore from there - that fresh session is not in the save file and needs no special handling.

## Live-session overlap (restore without restart)

Restoring while the original sessions are still open is a real case: the user forgot the IDE was running, or saved and restored in one sitting. `claude --resume <id>` does NOT fork in this case - it opens a second interactive TUI on the same conversation and the same transcript file. Two live processes then interleave writes into one JSONL (verified: "hi" from window 1, "hi again" from window 2, both appended to the same file, both TUIs replying). This is confusing at best - type in one window, watch the answer appear in another.

Detection is partial (re-verified 2026-09-13). Sessions expose their id in `ps` argv only as `--session-id <id>` or `--resume <id-or-path>` - daemon-forked runs (both the fork id and the fork's source session are caught). **IDE-started sessions run as bare `claude` with no id in argv and no session-specific open files - they are invisible to this check.** Filter out non-TTY processes (`?`/`??` - task agents, skill subprocesses):

```bash
ps -eo tty=,args= | awk '$1 !~ /^\?/' | grep -oE -- '--(session-id|resume) ' | sort -u   # see script for full pipeline
```

A saved id appearing in that list is genuinely live - skip it. But an id NOT appearing is not proof it is dead: IDE-started sessions never appear. The confirmation prompt is the real guard: ask whether the originals are still open; skip confirmed-live ones and report "already live - skipped N sessions that are still open; restart the IDE first if you want them moved into tmux".

## Launch strategy - tmux (default on this machine)

tmux is installed via Homebrew (`/opt/homebrew/bin/tmux`). IntelliJ's terminal has no CLI to open tabs, and long-running processes launched via an IDE terminal API die when the API call times out - so tmux is the only way to host several interactive sessions and keep them reachable from one IntelliJ terminal tab.

Create the tmux session and one shell window per session (no command in the window - a plain shell pane cannot die on its own), then type the resume command into each pane with `send-keys`:

```bash
tmux new-session -d -s claude-restored -n <short-name> -c <cwd>
tmux send-keys -t claude-restored:<short-name> "claude --resume <session-id>" Enter
# subsequent sessions:
tmux new-window -d -t claude-restored -n <short-name> -c <cwd>
tmux send-keys -t claude-restored:<short-name> "claude --resume <session-id>" Enter
```

Do NOT pass the resume command as the window's start command (`tmux new-window ... "claude --resume ..."`) - if the command exits immediately, the window closes and a single-window session (and the tmux server) can die before you ever look at it. If `claude-restored` already exists (surviving from an earlier restore), add windows to it with `tmux new-window` only - `tmux new-session` would fail on the duplicate name.

- `short-name` = first 8 chars of session ID, or a slug from the summary.
- `-c <cwd>` sets the working directory per window.
- Run the create and send-keys commands from any shell (the skill's Bash tool works). **`tmux attach` must be typed by the user in an IntelliJ terminal tab** - it takes over that terminal's TTY and cannot be run by Claude.
- A typo'd or deleted session ID does not error - `claude --resume` silently falls back to a fresh conversation in that directory. After launching, spot-check each window (`tmux capture-pane -p -t claude-restored:<short-name>`) and flag any that show a trust prompt / empty conversation instead of the resumed one.

Alternative if tmux is missing: iTerm2 AppleScript (below). Plain-background launch is NOT a fallback - a background `claude --resume` has no TTY and cannot be interacted with.

### Sessions already running in tmux (IDE restart only)

If the user restarted only the IDE (tmux server still alive), `tmux ls` shows the sessions - in that case no relaunch is needed: list the surviving tmux sessions and tell the user to `tmux attach -t <name>`. The save file is for when the tmux server is gone too (machine restart, `tmux kill-server`).

## Alternative - iTerm2 (macOS, only if tmux unavailable)

```applescript
tell application "iTerm2"
  create window with default profile
  tell current session of current window
    write text "cd <cwd> && claude --resume <session-id>"
  end tell
  -- repeat: create tab per session with `create window` -> `create tab with default profile`
end tell
```

## Steps

1. Read `~/.claude/saved-sessions.json`. If it doesn't exist, tell the user and suggest running `save-sessions` first.

2. Run the script (see above). It performs steps 3-5 of this procedure. If it succeeded, skip to step 6.

3. Manual fallback only. Check `tmux ls` first (see "Sessions already running in tmux"). Then apply the current-session skip (see above). Then apply the live-session overlap guard (see above) - ps-based detection, falling back to asking the user. Show the remaining list and confirm, e.g.:

```
About to resume 3 sessions in tmux session claude-restored:
  1. Refactor auth middleware        (~/myapp)
  2. Fix flaky payment tests         (~/myapp)
  3. Update API docs                 (~/docs-site)
Proceed?
```

4. Launch each session as a tmux window with its recorded `cwd` - plain shell window + `send-keys` (see Launch strategy).

5. Verify launch: `tmux list-windows -t claude-restored` should show one window per session. Spot-check panes with `tmux capture-pane -p` (a typo'd or deleted session ID resumes as a fresh empty conversation with a trust prompt, no error). Report failures individually (a session ID may be gone if the transcript was deleted or the project was moved - those need `claude -r` interactive picking in that project directory).

6. Tell the user to type `tmux attach -t claude-restored` in an IntelliJ terminal tab. Summarize: which sessions resumed, which were skipped (current / already live) and why, which failed, and how to detach (Ctrl-b d) without killing the sessions.

## Notes

- If a `cwd` no longer exists, still try resuming from the closest existing parent directory, and warn the user.
- Do not resume more than ~8 sessions simultaneously without the user asking; context replay is expensive.
- After successful resume, optionally suggest renaming each session (`/rename`) so future save/restore lists show friendly names.
- Killing the tmux session (or the machine) kills the resumed TUIs, but the conversation transcripts persist - re-running the restore brings them back.
