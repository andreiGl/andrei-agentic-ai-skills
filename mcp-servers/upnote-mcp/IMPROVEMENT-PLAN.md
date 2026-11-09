# UpNote MCP improvement plan - post-incident (2026-11-09)

Prepared by the OPENIDM-23003 session after the CURRENT TICKETS flatten incident. A follow-up session
implements it. Repo: `/Users/andreiglotov/Documents/andrei-agentic-ai-skills/mcp-servers/upnote-mcp/`
(symlinked from `~/.claude/mcp-servers/upnote-mcp`; commits deploy on next server start).

## 1. Incident summary

2026-11-09: inserting an OPENIDM-23399 section into the "CURRENT TICKETS" note (59KB, many
`shine-collapsible-section` blocks) via MCP `replace_note` + `make_section` produced a note where nearly
all collapsible wrappers were gone. Restored the original from Trash (revision 107); the section was then
pasted by hand in the app. Rollback cost: ~40 minutes of session time plus manual user work.

This was the third UpNote data incident (10-11 membership wipe - UpNote-side, reported; 10-22 literal-`\n`
code-block corruption - fixed by guard `_literal_breaks_in_code`, commit 99b9414; 11-09 structural flatten).

## 2. Root cause (source-verified)

Every write tool (`replace_note`, `make_section`, `move_note`, `append_to_note`) rebuilds the note the same
way: the full body is percent-encoded into an `upnote://x-callback-url/note/new` URL, UpNote re-parses it,
and only then - after word/line-coverage checks - is the original trashed.

The failure surface:

1. **UpNote's re-parser flattens nested `shine-collapsible-section` wrappers on re-parse of a large body.**
   Hand-written raw shine HTML survived a single replace on 2026-09-24; the 11-09 body (59KB, 20+ nested
   wrappers) came back with most wrappers dropped. The exact trigger (size? nesting depth? the
   `_tighten_html`/`_nested_lists_to_html` pre-transforms?) is unconfirmed.
2. **Post-write validation is content-level only**: word coverage, line coverage (`keep_lines`), tags,
   notebook membership, revision stability (`_replace` lines 1746-1770). Nothing compares the NEW note's
   HTML structure to the OLD one. A note that loses every collapsible wrapper passes all checks - the
   original is then trashed.
3. **Pre-write checks only warn**: `shine-section-collapsed` in the body → "collapsed sections may open
   expanded"; body >20,000 chars or containing `shine-collapsible-section` → "formatting is complex"
   (`_replace_checks` lines 1414-1417). Warnings do not block, and the agent acknowledged them.
4. **Contributing factor**: the 32KB MCP client input limit means large notes are supposed to go through a
   direct `server.py` import (documented recipe, `~/.claude/projects/.../reference_upnote_large_note_edits.md`),
   but nothing steers an agent there - the MCP tool accepts a 61KB body silently, and `_create_url` has no
   size guard before percent-encoding it into one `open` URL.

## 3. Fixes, in priority order

### F1. Structural round-trip check before trashing the original (the core fix)

In `_replace`, after the new note is confirmed and BEFORE `_set_trashed(original)`:
compare the structural signature of old vs new `notes.html`.

- Signature = counts of the elements UpNote round-trips losslessly when wrappers survive:
  `shine-collapsible-section`, `shine-section-collapsed`, `shine-highlight`,
  `data-upnote-placeholder-key`, `<pre>`, `<code>`, `<blockquote>`, `<table>`, `data-upnote-mcp` markers,
  plus top-level `<ul>/<ol>` counts. Keep it a dict; report the diff.
- Policy: if old note has N>0 collapsible sections and new has fewer, refuse the trash step
  (`done=false`, error names the missing structures and states the original is NOT trashed).
  Word/line coverage already passed - this is the formatting gate that was missing.
- Edge cases to decide during implementation: a legitimate deletion of one section (user removed a block)
  should be allowed - so either require the ratio (new >= old - removed-by-user is unknowable; simplest v1:
  refuse only when new == 0 while old > 0, then tighten), or add an `allow_structural_loss=true` escape
  parameter the caller must pass explicitly and that surfaces as a preview warning.
- This is the same shape as `_lost_members` (the 10-11 fix): check, refuse, report. Follow that pattern.

### F2. Hard block on oversized bodies through MCP

In the `replace_note`/`append_to_note`/`make_section` tool handlers: if the incoming body exceeds ~30KB
(MCP-safe threshold below the 32KB client limit), return a structured error that says:
"use the direct server.py import recipe - see reference_upnote_large_note_edits.md", with the import
snippet. Optionally add a `server_only=true` parameter that bypasses the block for direct-import calls
(those don't pass through MCP, so they never see the handler check).

Also add the missing size guard in `_create_url`: refuse bodies whose percent-encoded URL exceeds a
conservative cap (macOS `open` tolerance is undocumented; 100KB URL is a sane ceiling) - today a too-large
URL silently relies on OS behavior.

### F3. Structure preview before apply

Extend the preview phase (already two-call) to include the structural signature diff from F1: the preview
response gains a `structure` object (old counts, new projected counts, delta list) computed on the client
side from the old `notes.html` and the submitted body. An agent that reads its previews sees the flatten
BEFORE applying, not after. Cheap to implement - same signature code as F1, no UpNote round-trip needed.

### F4. Safe insertion path for mid-note content (the actual task from 11-09)

The reason the incident happened: there is no partial-insert tool. Byte-splicing already exists in
`_NoteHtml` (`_plan_section` lines 2016-2020 - untouched bytes pass through unchanged). Add:

- `insert_after_heading(note_id, heading, html, position="before"|"after")`: locates the heading with the
  same `_NoteHtml` parser, splices the new fragment at the byte offset, and sends the full body through the
  normal rebuild - BUT combined with F1 this is only as safe as the rebuild itself.
- The stronger version: **degrade gracefully per tool** - document and enforce that for notes with
  collapsible sections, the ONLY sanctioned full-body paths are (a) the direct-import recipe and
  (b) `make_section`, and both now carry F1. Small notes without sections keep the MCP path.

### F5. Post-incident guard in the workflow memory (no code)

Already partly done (MEMORY.md line 57). The follow-up session should also:
- Add a dated 11-09 entry to `reference_upnote_mcp.md` (the incident, the mechanism, the restore recipe).
- Update `reference_upnote_large_note_edits.md` to make the direct-import recipe the DEFAULT instruction
  for any note >20KB or containing collapsible sections, with a copy-paste snippet.
- Record the open question: exact trigger of the flatten (size vs nesting depth vs pre-transforms) - F1's
  guard makes this low-stakes, but a targeted experiment (scratch note, one nested wrapper, growing sizes,
  direct import) would answer it. Run against a scratch notebook per the standing test rules.

## 4. Test plan

- Offline (safe, no UpNote links): unit tests for the signature function (old vs new HTML pairs - including
  the real 11-09 before/after bodies if archived; at minimum a synthetic pair with wrappers), the F2 size
  guard, and the F3 preview diff. Fit next to `test_make_section.py` / `test_nested_lists.py`.
- `test_live.py`: unblock the move step FIRST (separate task - the notebook-wipe guard `459fb86` exists;
  ask Andrei to lift the HOLD), then add a live case: note with nested wrappers through a replace that must
  be REFUSED by F1 when the flatten occurs. Until the HOLD lifts, validate F1 manually against a scratch
  note per the standing rules (scratch notebook, never CURRENT TICKETS).
- Regression: re-run `test_readonly.py`, `test_make_section.py`, `test_nested_lists.py`,
  `test_write_contract.py` (added in c3806a8) after the changes.

## 5. Rollout order

1. F1 (structural gate) - smallest diff, prevents recurrence, pattern already proven (`_lost_members`).
2. F2 (size guard + recipe steering) - trivial, prevents the next agent from walking into it.
3. F3 (preview diff) - same signature code, big ergonomics win.
4. F5 (memory/README updates) - do together with 1-3 in the same commit series.
5. F4 (insert tool) - only after F1 proves out in practice; the incident does not require it.
6. test_live.py unblock - separate decision with Andrei (HOLD exists because of the UpNote-side wipe bug,
   not this server).

## 6. Acceptance criteria

- A replace that would drop a collapsible section refuses with `done=false`, original intact, error names
  the structural diff.
- A >30KB body through MCP replace_note is refused with the direct-import recipe in the error.
- Preview responses carry the structural signature diff.
- All offline suites pass; no new failure in the read-only suite.
- The 11-09 incident and the new guards are recorded in `reference_upnote_mcp.md` (dated entries).
- CURRENT TICKETS has the 23399 section (already satisfied by Andrei's hand-paste).

## 7. References

- Server: `/Users/andreiglotov/Documents/andrei-agentic-ai-skills/mcp-servers/upnote-mcp/server.py`
  (`_replace` 1543-1811, `_replace_checks` 1414-1417, `_NoteHtml` 1869-1914, `_plan_section` 1961-2027,
  `_lost_members`, `_literal_breaks_in_code` 1424-1431)
- Incident timeline: `~/IdeaProjects/openidm/OPENIDM-23003-PROGRESS.md` (UpNote sections, 11-09)
- Memory: `~/.claude/memory/reference_upnote_mcp.md`, `MEMORY.md` line 57,
  `~/.claude/projects/-Users-andreiglotov-IdeaProjects-openidm/memory/reference_upnote_large_note_edits.md`
- Prior incidents: 10-11 wipe (report sent to UpNote; do not re-report), 10-22 `\n` corruption (guard 99b9414),
  recovery artifacts `~/tmp/upnote-recovery/`, `~/tmp/upnote-fix/`
