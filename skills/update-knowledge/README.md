# update-knowledge

Persists learnings from the current task into `~/.claude/knowledge/`. Wired into the
global `CLAUDE.md`, so it usually runs without being asked.

## What it does

1. Decides whether anything is worth recording at all — routine tasks are skipped
2. Applies the Category A gate: facts derivable from the code in under 3 tool calls
   don't become pages
3. Routes what survives — a line in `gotchas.md`, an edit to an existing page, or a
   new page in `pages/<project>/` with an `INDEX.md` row and bidirectional `[[links]]`
4. Appends to `learnings.md`
5. Writes an experience entry in `experiences/YYYY-MM-DD-<topic>.md`
6. Updates `active-context.md` if open work changed state

## Why the experience entry is unconditional

`synthesize-knowledge` reads `experiences/` to find recurring patterns. If entries are
only written on eventful sessions, the pattern signal disappears — the interesting
part is often that the same area keeps coming up in otherwise unremarkable work.

## Related

- [`load-knowledge`](../load-knowledge) — loads the KB at the start of a task
- [`build-knowledge`](../build-knowledge) — builds pages for a new project
- [`check-knowledge`](../check-knowledge) — verifies existing pages are still accurate
- [`synthesize-knowledge`](../synthesize-knowledge) — distills recurring patterns
