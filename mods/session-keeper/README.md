# session-keeper

A strip above the prompt: prompt-cache countdown, usage limits and API-equivalent cost on one row; context fill, a quality warning and one-key handoff on the other.

## What it shows

**Cache row**: `Cache warm 42:13 (60m auto) · 5h 23% 2h10 · wk 41% 3d · API $12.34 · cold msg $2.00 (warm $0.050)`

- The countdown anchor is the start of the last main-thread model request. The cache window (60 or 5 minutes) is detected from the transcript's `cache_creation` entries after each turn; `/cache-ttl` overrides detection.
- `5h` / `wk` are the five-hour and seven-day rate-limit windows with time to reset; `API` is the session cost `/cost` totals.
- `cold msg` prices re-sending the current context with the cache cold (write rate: 2x input on a 1-hour window, 1.25x on a 5-minute one); `warm` prices it as a cache read. List prices, USD per million tokens.
- A timer warns 5 minutes before expiry (1 minute on the 5-minute window) with a toast and a notification (osascript fallback, Glass sound). When the context is already large, the warning suggests handing off instead of re-caching.

**Context row**: `Context 25% (250k/1M) warn 40% · auto off  [1: New session with handoff] [2: Fresh session]`

- Green below the warn level (default 40%), yellow at or above it, red at the auto-handoff level. One toast per conversation the first time it crosses warn.
- Button 1 (or `/handoff`, or reaching the auto level): fork a handoff brief off the conversation, save it to `~/.claude/handoffs/<timestamp>-<session8>.md`, run `/clear`, and put the brief in the fresh prompt box. Nothing is cleared if no brief comes back.
- Button 2: `/clear` only. Both refuse while a turn is running.

## Commands

- `/cache-ttl <minutes>|auto` - pin the cache window in minutes, or return to detection.
- `/autohandoff <percent>|off|warn <percent>` - hand off by itself at a fill level; set the warn level; no argument prints the settings.
- `/handoff` - run the handoff now.
- `/session-keeper show|hide cache|context` - show or hide one row.

Settings persist across sessions in the plugin's `$.store`; uninstalling the plugin deletes them.

## Rebuild from a prompt

Paste this into a fresh Claude Code session; it re-creates the mod end to end (sources, tests, checks, install):

```text
Build a Claude Code mod named "session-keeper". Load the plugin-authoring skill first and follow it: write the mod in the dev folder the skill names, check every call against that build's API types, and run validate, test and strict tsc until all three pass.

The mod draws two rows above the prompt (a ui.render hook on component AbovePrompt), each hideable, settings kept in $.store:

Row 1, cache and usage, reading "Cache warm 42:13 (60m auto) · 5h 23% 2h10 · wk 41% 3d · API $12.34 · cold msg $2.00 (warm $0.050)":
- The countdown anchor is the start of the last main-thread model request: hook turn.step, and when e.agentId is undefined store $.clock.now() and e.model, then reschedule the warning timer. Redraw every second via $.clock.every(1000, () => $.ui.invalidate('ui.render')).
- Cache window, detected after each main turn (turn.complete with no agentId): read the last 2000000 bytes of <config dir>/projects/<project path, non-alphanumerics as dashes>/<session id>.jsonl (try $.session.root() and $.session.cwd() as the project); scanning from the newest line, find the first main-thread assistant entry whose message.usage.cache_creation exists; ephemeral_1h_input_tokens > 0 means 60 minutes, ephemeral_5m_input_tokens > 0 means 5 minutes. Default 60 when nothing written. Save the detection in $.store; /cache-ttl overrides it. The label reads (60m auto), (5m auto) or (Nm set).
- Usage and cost from $.session.usage(): context {tokens, window, percent}; rateLimits entries with kind five_hour and seven_day, each percentUsed plus time until resetsAt; cost.usd as the API total.
- Cold/warm cost of the next message: cold = context tokens x input price x 2 (1-hour TTL) or x 1.25 (5-minute); warm = tokens x cache-read price. Prices are USD per million tokens as input/output/cache-read, matched to the model id by substring, most specific first: fable-5-1 10/50/0.25, fable-5 10/50/1, opus-5-5 4/20/0.20, opus-5 5/25/0.50, opus-4-1 and opus-4-0 15/75/1.50, sonnet-5 2/10/0.20, sonnet-4 3/15/0.30, haiku-5 0.10/0.50/0.01, haiku-4 1/5/0.10, then bare opus, sonnet, haiku and fable fallbacks.
- Warning: a timer at anchor + window minus 5 minutes (1 minute on the 5-minute window), guarded on the anchor still being current: toast plus $.ui.notify, falling back to osascript -e 'display notification "..." with title "Session Keeper" sound name "Glass"' when notify reports isSent false. When context percent >= the warn level the text tells the user to hand off now (re-caching a large context is the expensive moment); otherwise to send a message to keep the cache warm.

Row 2, context and handoff, reading "Context 25% (250k/1M) warn 40% · auto off" with two buttons: [1: New session with handoff] (hotkey "1", variant primary) and [2: Fresh session] (hotkey "2").
- Color: green below the warn level (default 40%), yellow at or above it, red at the auto-handoff level. One toast per conversation the first time it crosses warn (a warned flag reset by /clear).
- Handoff (button 1, /handoff, or auto): write a brief with $.model.fork({ prompt: HANDOFF_PROMPT }) - the prompt asks for a Markdown brief a fresh session can pick up the work from: goal, where it stands, decisions and reasons, files and paths, open questions, next steps, under 500 words, no tools, no preamble. Save it to ~/.claude/handoffs/<ISO timestamp, colons and dots as dashes>-<first 8 of session id>.md. Then run /clear from $.clock.after(100, ...) - never awaited inside a hook, the session must be idle - and fill the fresh prompt box with $.prompt.fill({ text: "Handoff from the previous session (also saved to <path>):\n\n<brief>\n" }); if fill reports isFilled false, append a user row with the brief plus a system notice via $.session.append. Nothing is cleared when no brief comes back. Track phase (writing -> clearing) and show it in the row while running.
- Button 2: /clear only. Both buttons refuse while a turn is running (read isWorking from the AbovePrompt props).
- Auto-handoff: after each main turn, when context percent >= the auto level and no handoff is running, start the same handoff from $.clock.after(500, ...) with a toast.
- On session.end with reason clear: drop the anchor, cancel the warning timer, reset the warned flag.

Commands (settings persist in $.store): /cache-ttl <minutes>|auto; /autohandoff <percent>|off|warn <percent> (no argument prints status); /handoff; /session-keeper show|hide cache|context.

Shape it as hooks/register.tsx (the hooks), hooks/logic.ts (pure helpers: the price table, TTL detect/parse/resolve, formatting, threshold logic, the handoff prompt), types/index.d.ts (the PluginState contract: anchor, ttlDetected, ttlOverride, model, warnAt, autoAt, isWarned, phase, rows), tests/band.test.tsx (mount AbovePrompt on terminal and desktop, mock session.usage and session.model, assert both rows, both hotkeys, and that another mod's band below survives), tests/cache.test.ts and tests/context.test.ts for the helpers. Follow the skill's rules: helpers taking $ are top-level functions, never declare a variable named on, annotate update() arrow return types, put .catch(($, e, next) => next(e)) on observer-only hooks, and every AbovePrompt draw starts with const below = await next(e) and returns its rows above it.

When validate, test and tsc pass, copy the mod to ~/.claude/mods/session-keeper/ (leave out .claude-plugin/types/ and tsconfig.json) and run claude plugin install session-keeper@local-mods.
```
