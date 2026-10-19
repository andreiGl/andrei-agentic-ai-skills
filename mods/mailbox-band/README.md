# mailbox-band

Mailbox awareness for any session on a machine with the inter-Claude mailbox
(`~/.claude/scripts/claude-mail`): a status row above the prompt, a
self-briefing context block in the first turn, and two commands. Strictly
read-only against the mailbox: it never consumes a session cursor, never
wakes a session, never sends mail by itself.

## What it shows

**Band** (above the prompt, hideable with its Hide button; when the session
is unmapped it also shows a **Wire...** button that types
`/mailbox-wire <name> <predicted>` into the prompt box (the prediction is
newest issue + 1, per-repo sequential; a failed fetch leaves the bare
prefix)):
`MB work/infra · daemon ok · lag 1m · unread 2 · responder busy`

- `who` - the session's mapped actor (`nick/name`, with `no-wake` when
  the map line flags it `!wake`), or `nick (unmapped)`.
- `daemon` - running with the daemon cursor's lag, or `DOWN`.
- `unread` - read-only count over the session's threads: comments past the
  session's cursor (falling back to the daemon cursor when the session has
  none) minus the machine's own ids. `?` when the fetch failed.
- `responder busy` - a responder turn is in flight.

The snapshot refreshes at `session.start` and after each main turn
(`turn.complete`, main thread only) **in the background** - the hooks
return at once and the row updates when the fetch lands, so turn
completion never waits on the network. Every snapshot carries a schema
version; readers drop snapshots with an older one, because `$.state`
survives a reload and the atom can briefly hold a pre-reload shape. It is deliberately not on a timer:
idle polling would spend API calls for nothing.

**First-turn context block** (`prompt.context`, block name `mailbox`): lane
nick and peer, this session's mapping or how to get wired, unread summary,
and the standing warning - never `claude-mail check` to browse (it consumes
the cursor); read with `claude-mail read <thread> --tail 30`. The block is
recomputed after compaction, so the briefing survives. Mapped sessions
only - unmapped ones (unrelated projects) get no block, by Andrei's call
(home's review finding); the band and commands still work there.

## Commands

- `/mailbox` - full status text: lane, mapping (flagging `NOT
  live-registered` when the SessionStart hook did not fire, and any map
  flags such as `!wake`), daemon pid and cursor lag, responder, live
  sessions on the machine, unread per thread.
- `/mailbox-wire <name> <threads>` - verifies thread `<threads[0]>` exists on
  the repo first (read-only; a miss answers the `claude-mail new` command
  instead of wiring a dead number), then rewrites
  `~/.claude/mailbox/sessions` as `NAME:session8:threads` (replacing any
  line already matching this session id; the line's existing field-4 flags
  such as `!wake` are kept - a re-wire never silently re-arms wakes),
  verifies the line resolves with the script's own prefix-match rule, then
  prints the ready-to-post peer-half instruction. Validates the name
  (`[a-z][a-z0-9-]*`) and threads (comma-separated numbers) before touching
  anything.

## What it never does

- Consume any cursor (`claude-mail check` is not called anywhere).
- Send mail or wake sessions (the daemon owns both; `/mailbox-wire` only
  prints the post for the user to make).
- Touch anything outside reading `~/.claude/mailbox/*` and, on
  `/mailbox-wire`, rewriting `sessions` (the one write, confirmed by a
  re-read; no lock - the file is human-edited config, and a concurrent edit
  races just as it would with a manual edit).
- Run on machines without the script (everything no-ops).

Unread fetches go through plain `gh` on a `PLAIN_GH=1` lane, otherwise with
`GH_TOKEN` from `gh auth token --user andreiGl` - the same identity rule the
script follows, and the token never appears outside the child env.

## Limits

- The unread count approximates what the session's next check would
  consume: `since=` is time-based (24h window) while cursors are id-based,
  and the fetch (newest-100, `direction=desc` - the unread are the newest)
  caps at one page. Good enough for a status row, not a delivery mechanism.
- The band goes stale while the session is idle; it redraws on the next turn.
- `prompt.context` does not run for installed plugins where an organization
  manages Claude Code (validator warning) - the band and commands still work.

## Rebuild from a prompt

Paste this into a fresh Claude Code session; it re-creates the mod end to end
(sources, tests, checks, install):

```text
Build a Claude Code mod named "mailbox-band". Load the plugin-authoring skill first and follow it: write the mod in the dev folder the skill names, check every call against that build's API types, and run validate, test and strict tsc until all three pass.

The mod is mailbox awareness for a machine that runs the inter-Claude mailbox (~/.claude/scripts/claude-mail, config ~/.claude/mailbox/config with NICK=/PEER=/PLAIN_GH=1, sessions map ~/.claude/mailbox/sessions as NAME:sessionid8:threads, per-session cursors state.<NAME>, machine-global own ids state.shared, live sessions live-sessions as "<sid> <socket>", daemon cursor state.daemon, repo andreiGl/claude-mailbox). It is strictly READ-ONLY against the mailbox: never call `claude-mail check` (it consumes the session cursor), never send mail, never wake sessions.

It draws one hideable row above the prompt (ui.render on AbovePrompt, settings in $.state): `MB work/infra · daemon ok · lag 1m · unread 2 · responder busy` - the session's mapped actor from the sessions map by 8-char id prefix (or `nick (unmapped)`), the daemon's liveness via pgrep -f "claude-mail daemon" with cursor lag from state.daemon's last_seen_created_at, a read-only unread count, and responder.busy presence. The snapshot is taken at session.start and at turn.complete (main thread only, agentId undefined) - never on a timer.

The unread count reads state.<NAME> (fall back to state.daemon when absent) for the cursor, state.shared for own ids, then fetches `gh api repos/andreiGl/claude-mailbox/issues/comments?sort=created&direction=asc&per_page=100&since=<24h ago>` via $.process.run and counts comments past the cursor on the session's threads minus own ids. On a PLAIN_GH=1 lane run plain gh; otherwise pass GH_TOKEN from `gh auth token --user andreiGl` in the child env only - never log or display it. Fetch failure shows `?`, never an error.

At session.start register two commands and keep a snapshot in $.state:
- /mailbox prints full status: lane nick/peer, mapping (with NOT live-registered flagged when live-sessions lacks the id), daemon pid + lag, responder state, live session ids, unread per thread, and the reminder that `claude-mail check` consumes the cursor and reads go through `claude-mail read <thread> --tail 30`.
- /mailbox-wire <name> <threads> maps THIS session: validates name [a-z][a-z0-9-]* and threads as comma-separated numbers, reads ~/.claude/mailbox/sessions, drops any line whose tag matches this session's 8-char id prefix, appends NAME:sid8:threads, re-reads and re-parses to verify (report wire FAILED if not), refreshes the snapshot, and prints the ready-to-post peer-half instruction (claude-mail send --thread <first> --text "session pair setup: ..."). It never posts by itself.

A prompt.context hook (block name `mailbox`) injects a briefing into the conversation's first turn of MAPPED sessions only (unmapped sessions get no block): lane nick and peer, the mapping, the unread summary when nonzero, and the never-check-to-browse warning. Filter out an existing mailbox block before appending so re-computation after compaction stays one copy. Guards: pass through unchanged when the script is missing or the snapshot is null; tolerate e.blocks being undefined.

Type notes: $ is per-dispatch (helpers take $ explicitly); there is no Node - read HOME via $.env.get("HOME") (call-site paths must await it); ~/ paths are not expanded by $.fs - always absolute. Wrap the command.run body in try/catch answering "mailbox-band: command failed: <msg>" and add on(...).catch so the validator sees the gate. Tests (claude plugin test): the kit has no fs/process - stub on('session.id', () => ({ value: SID })) (call hooks answer { value }), stub core prompt.context with on('prompt.context', () => ({ blocks: [] })), and $.command.run args need origin { kind: 'composer' } and presentation { isFullscreen: false, columns: 120 }. Cover: pass-through when no snapshot, all three usage-error paths of mailbox-wire, /mailbox surfacing the failure text in an fs-less env, and foreign commands falling through. Run `npx -y -p typescript@5.9.3 tsc -p <dev>/tsconfig.mailbox-band.json` (target es2023, jsx react with h/Fragment, strict + noUncheckedIndexedAccess, no DOM lib) until clean.
```
