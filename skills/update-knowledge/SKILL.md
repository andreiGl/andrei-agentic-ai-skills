---
name: update-knowledge
description: Persist learnings from the current task into the personal knowledge base at ~/.claude/knowledge/. Use after finishing a task that produced a surprise, a correction, a non-obvious constraint, or a rule worth carrying into future sessions.
---

# Update the Knowledge Base After a Task

Before the session ends, decide what — if anything — is worth keeping, and write it
into `~/.claude/knowledge/`.

Apply the **Category A gate** from `~/.claude/knowledge/CLAUDE.md` before writing
anything: if the fact can be derived from reading the code in under 3 tool calls, it
does not become a page.

---

## 1. Decide whether anything is worth recording

Routine tasks with no surprises need no KB update. Skip it and say so — writing an
entry for every task is how a knowledge base fills with noise and stops being read.

Worth recording:
- A gotcha that depends on external system behavior the code can't reveal
- A correction to something a page currently gets wrong
- A constraint that exists for reasons invisible in the code
- A build or test behavior that contradicts reasonable expectations

Not worth recording:
- What the task did — the commit message covers it
- Structure you could re-derive by reading the code
- Anything the project's own `CLAUDE.md` or style config already states

---

## 2. Write it to the right place

### A cross-cutting gotcha → `gotchas.md`

One line, plain statement, `[[page-link]]` if a full page exists. If it belongs to a
recurring failure mode, add it under **Fragile areas**.

Create a full page only when the fact needs more than three sentences to be
actionable.

### A correction to an existing page

Read the page, edit in place, bump **Last updated**. If the old content was wrong,
replace it — don't append a contradiction. Set `Status: verified` when you checked
against live code.

### A new page

Follow the header and body conventions in `~/.claude/knowledge/CLAUDE.md`. Write it
to `pages/<project>/`, add a row to `INDEX.md`, and add `[[links]]` in both
directions.

---

## 3. Always: append to `learnings.md`

Use the entry format from `~/.claude/knowledge/CLAUDE.md`. Include **Prevented** only
when a `gotchas.md` bullet visibly caught something during this session — that field
is the evidence that a bullet is earning its place.

## 4. Always: write an experience entry

`~/.claude/knowledge/experiences/YYYY-MM-DD-<topic>.md`, covering:

- What the task was, in one line
- Decisions made and why — especially ones a future session would otherwise re-litigate
- What surprised you
- `Updated pages:` list

These entries are the raw material `synthesize-knowledge` reads to find recurring
patterns. Without them it has nothing to work from, so write one even when the task
produced no page-worthy facts.

## 5. Update `active-context.md`

If the session changed the state of open work, or identified an area now in flux,
update it. Delete entries that are finished rather than marking them closed.

---

## Distillation

When `learnings.md` passes 20 entries or `experiences/` passes 5, run
`synthesize-knowledge`. It owns trimming and archiving — don't do it here.
