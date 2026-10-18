# self-critique

`/critique` opens a side panel reviewing Claude's last response: a verdict, a summary, strengths, and numbered flaws each with a one-click fix.

## What it shows

The review covers everything Claude answered after the person's latest real prompt, tool calls included; user rows that only carry tool results count as part of the response.

- **Verdict**: Strong (green) / Mixed (yellow) / Weak (red), with a one-to-two-sentence summary.
- **Strengths**: real and specific ones only, at most 5.
- **Flaws**: most serious first, at most 6, each with a concrete suggested fix and a **Make this fix** button.
- The fix button submits the fix prompt as the person's own words ("A review of your last response found this problem: ... Please fix it. Suggested fix: ...") via `$.prompt.submit({ text, asUser: true })`, then shows "Sent to Claude" so one fix can't be sent twice.

## Reviewers

- **Same as session** (default): `$.model.fork` - the session's own model over its own transcript. It sees the whole conversation, and the prompt cache serves the history, so it is the cheap default.
- **Opus / Sonnet / Haiku**: `$.model.complete({ model, prompt, maxTokens: 4000 })` over the last exchange alone. The prompt carries the request, a list of tool calls (name plus command/file_path/pattern/url), and the response, clipped to 20k/10k/60k characters.

The reviewer answers JSON only (`verdict`, `summary`, `strengths`, `flaws` with `flaw`+`fix`); parsing takes the first `{` to the last `}`, tolerates code fences and odd casing, and drops empty entries. The rubric: did it do all that was asked and nothing more; is every claim correct and supported, and does it say what it did not verify; is the work sound; is it clear and no longer than needed. No flattery, an empty flaw list rather than invented ones.

## Controls

- **Rerun** reviews again with the current reviewer.
- **Auto: on/off** - review after every main turn and open the panel. Persists in `$.store`.
- **Reviewer** picker - a Select on surfaces that draw one; a button that steps through the reviewers on surfaces that don't (mobile has no Select). Persists.

## Commands

- `/critique` - open the panel and review now.
- `/critique auto on|off` - the turn-end auto review.
- `/critique model session|opus|sonnet|haiku` - the reviewer (also accepts `same` for session).

## Rebuild from a prompt

Paste this into a fresh Claude Code session; it re-creates the mod end to end (sources, tests, checks, install):

```text
Build a Claude Code mod named "self-critique". Load the plugin-authoring skill first and follow it: write the mod in the dev folder the skill names, check every call against that build's API types, and run validate, test and strict tsc until all three pass.

The mod draws a pane: $.ui.open({ id: 'self-critique', title: 'Self-Critique' }), rendered by a ui.render hook matching { component: 'Pane', requestId: 'self-critique' }.

What it reviews: the person's latest real prompt and everything Claude answered after it, including tool calls. Read the conversation with $.session.messages(); a user row with empty text or only toolResults is part of the response, not a new prompt. For the named reviewers, build a standalone prompt of <request> / <tool_calls> / <response> sections (each clipped: 20000 / 10000 / 60000 characters, the tail replaced with a "[... N more characters left out]" note; each tool call one line: name, then the first string among command, file_path, path, pattern, url, query, then " (failed)" when isError).

Reviewers, chosen by an atom persisted in $.store:
- 'session' (default): $.model.fork({ prompt: FORK_PROMPT }). The fork prompt says: step outside the conversation and review your own last response, do not continue the work, do not call tools. A 'nothing-to-fork' reason means there is no response to review yet.
- 'opus' | 'sonnet' | 'haiku': lastExchange() from $.session.messages(), then $.model.complete({ model, prompt: standalonePrompt(exchange), maxTokens: 4000 }).

The reviewer prompt ends with a rubric and the answer format. Rubric: did it do what was asked, all of it, nothing that was not asked; is every claim correct and supported, and does it say plainly what it did not verify; is the work sound (correct code, safe actions, no missed edge cases); is it clear and no longer than it needs to be. Do not flatter; strengths only when real and specific; flaws most serious first, each fix a concrete instruction; empty list rather than invented flaws; at most 5 strengths and 6 flaws. Answer with JSON alone: {"verdict": "Strong"|"Mixed"|"Weak", "summary": "<two sentences at most>", "strengths": ["..."], "flaws": [{"flaw": "...", "fix": "..."}]}. Parse from the first { to the last }, tolerate code fences and odd verdict casing, drop entries with empty flaw text or non-string strengths.

Panel layout, top to bottom: controls (Rerun button variant primary, labelled "Reviewing..." while running; "Auto: on|off" button; a reviewer picker), then the state. Empty: "Press Rerun, or type /critique, to review Claude's last response." Running: "Reviewing the last response with <reviewer>...". Error: the message in the error color (no response yet, the review did not come back with its reason, the reviewer answered but not in the expected form). Done: the verdict bold in success/warning/error for Strong/Mixed/Weak plus "reviewed by <reviewer>" dimmed, the summary, a Strengths list ("+ " prefix, "None named." when empty), a Flaws list (numbered, error-colored numbers; the fix on a dimmed indented line "Fix: ..."; under each a "Make this fix" Button that becomes dimmed text "Sent to Claude" after it fires).

Make this fix: submit the fix prompt as the person's own words with $.prompt.submit({ text, asUser: true }) - text is "A review of your last response found this problem:\n\n<flaw>\n\nPlease fix it. Suggested fix: <fix>" (the suggested-fix sentence only when a fix exists) - then mark that flaw index sent. One fix per flaw.

Commands: /critique opens the panel and reviews; /critique auto on|off sets the auto review (persists); /critique model session|opus|sonnet|haiku sets the reviewer ('same' accepted for session, persists). Auto: on turn.complete with no agentId and not aborted, open the pane and run the review from $.clock.after(300, ...). On session.end with reason clear, reset the review to empty.

The reviewer picker: use the Select element from $.ui.resolve(e) when the surface's table has one (options: Same as session, Opus, Sonnet, Haiku); on surfaces without Select (mobile), draw a Button labelled "Reviewer: <current>" that cycles through the four.

Shape it as hooks/register.tsx (the hooks), hooks/logic.ts (pure helpers: lastExchange, standalonePrompt, parseCritique, fixPrompt, the reviewer table, FORK_PROMPT), types/index.d.ts (PluginState: review, reviewer, isAuto; exported Review, Critique, Flaw, Reviewer, Verdict), tests/logic.test.ts (lastExchange including the tool-results rule, parseCritique with fences and junk entries, fixPrompt) and tests/pane.test.tsx (mock model.complete and prompt.submit, mount the Pane on terminal and desktop, pick haiku, press rerun, assert the verdict/summary/fix render, press fix-0 and assert "Sent to Claude" and the submitted text). Follow the skill's rules: helpers taking $ are top-level, never declare a variable named on, annotate update() arrow return types, .catch(($, e, next) => next(e)) on observer hooks.

When validate, test and tsc pass, copy the mod to ~/.claude/mods/self-critique/ (leave out .claude-plugin/types/ and tsconfig.json) and run claude plugin install self-critique@local-mods.
```
