---
name: mailbox-session-pair
description: Wire a new pair of named mailbox sessions (one per lane, e.g. TestWork and TestHome) to a mailbox thread so they can exchange session-addressed mail. Use when the user asks to set up, connect, or register new mailbox sessions or a new session pair.
---

# Pair two named mailbox sessions on a thread

Your job is to take a session NAME on this lane and a thread number, wire them
into the sessions map, verify the wiring, and hand the peer lane its half of
the setup through the mailbox itself. Nothing here edits the `claude-mail`
script, settings, or daemon - the skill only touches `~/.claude/mailbox/sessions`
and posts mail.

Decide the NAME and thread first (ask the user if not given). Conventions:
lowercase names; this lane's name and the peer's mirror each other
(`testwork`/`testhome`, `infra`/`infra`, `flip`/`flip`). Infra matters go on
thread #4; open a new thread for a working pair. The user starts the sessions
themselves - this skill wires an already-running session.

## Phase 1 - thread

- Existing thread number given: use it. Verify it exists: `claude-mail status`.
- Otherwise open one: `claude-mail new "<topic>"` and read the number from
  its output (`opened thread #N: <url>`).

## Phase 2 - find the session id

The session must be running on this machine. Find its id WITHOUT asking the
user to paste anything:

```bash
cat ~/.claude/mailbox/live-sessions
```

Lines are `<session_id> <socket>`. A running session registers itself at
SessionStart. Cross out every id whose 8-char prefix already appears in the
sessions map - what remains is unregistered. If more than one remains, ask
the user which one is the target (or match by start time if they know it).
If none remain, the session is not started or its hook did not fire: ask the
user to start it (or check `~/.claude/settings.json` SessionStart), then
re-run this phase.

## Phase 3 - seed the map

Append one line to `~/.claude/mailbox/sessions` (no trailing whitespace;
the file is plain text, one `NAME:prefix:threads` per line):

```
<name>:<first 8 chars of session_id>:<thread>
```

`threads` may be a comma-separated list if one session owns several. Read the
file before and after; never rewrite other lines. Then verify the map line
resolves with the same matching rule the script uses (prefix match against
the 8-char session id head) - set the id into a variable first, because the
`-v s="${sid:0:8}"` expansion happens in the calling shell BEFORE any
`VAR=x cmd` prefix would apply:

```bash
sid=<full session id>; awk -F: -v s="${sid:0:8}" 'index(s, $2) == 1 && $2 != "" {print; exit}' ~/.claude/mailbox/sessions
```

It must print exactly the line you added (and nothing for a wrong id). A
manual `claude-mail check` does NOT prove resolution - it maps only in
`--hook` mode from the SessionStart stdin payload; the real from= resolution
shows in the marker of the session's next send. Registry liveness - whether
the socket is connected - is separate and handled by the SessionStart hook;
confirm `live-sessions` still lists the id.

## Phase 4 - brief and hand off the peer half

The peer lane must add its own map line on its own machine - this lane cannot
and must not. Post the instruction on the SAME thread (not #4, unless this
whole setup is infra matter):

```bash
claude-mail send --thread <N> --text "session pair setup: <this lane's name> is mapped to thread <N> on <lane> (<sid-prefix>). Peer half: start the peer session, then add to ~/.claude/mailbox/sessions: <peer-name>:<its sid prefix>:<N> - get its id from its live-sessions file after it registers. Confirm on this thread when done; first directed post then proves the pair."
```

The peer's infra session (or the responder) picks it up through the normal
delivery path. When the peer confirms, verify the full loop:

1. The peer posts on the thread - `claude-mail check` should show a
   session-qualified `from=<peer>/<name>` line.
2. Reply from this lane's session: its marker must read
   `from=<NICK>/<name> to=<peer>/<name>` (`claude-mail read <N> --tail 2`
   and inspect the marker line).
3. The peer's confirmation that their session was woken closes the loop.

Report each phase's result plainly; if a phase fails, stop and say what is
missing rather than improvising around the mailbox.

## Failure modes

- **Session id changes on resume/compact/fork** - the prefix in the map goes
  stale, the session silently degrades to lane-only. Symptom: mail from the
  lane arrives but the session is never woken. Fix: re-read the id from
  `live-sessions` and update the map line.
- **Two map lines match one id** - the first match wins; delete the stale
  line instead of stacking.
- **Thread not in the map line** - a mapped session ignores every other
  thread's mail; add the number to its comma list when its scope grows.
- **Responder turns never map to a session** - they are lane-only by design;
  do not try to name them.
