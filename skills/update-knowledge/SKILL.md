---
name: update-knowledge
description: Persist learnings from the current task into the personal knowledge base at ~/.claude/knowledge/. Use after finishing a task that produced a surprise, a correction, a non-obvious constraint, or a rule worth carrying into future sessions.
---

# Update the Knowledge Base After a Task

Before the session ends, decide what — if anything — is worth keeping, and write it
into `~/.claude/knowledge/`. Conventions are in `~/.claude/knowledge/CLAUDE.md`.

## What is conditional and what isn't

| Output | When |
| :--- | :--- |
| A page, or a `gotchas.md` line | Only when the Category A gate passes |
| A `learnings.md` entry | Only when the session produced a rule or a surprise |
| An experience entry | Always |

A routine task with no surprises produces **only** the experience entry. That is the
normal outcome, not a failure — writing a page for every task is how a knowledge base
fills with noise and stops being read.

The experience entry is the exception because `synthesize-knowledge` reads those files
to find recurring patterns, and the useful signal is often that an unremarkable area
keeps coming up. Skip them on quiet sessions and that signal disappears.

---

## 1. Apply the Category A gate

The gate is defined in `~/.claude/knowledge/CLAUDE.md` — apply it as written there.
What it tends to catch in practice:

Worth recording:
- A gotcha that depends on external system behavior the code can't reveal
- A correction to something a page currently gets wrong
- A constraint that exists for reasons invisible in the code
- A build or test behavior that contradicts reasonable expectations

Not worth recording:
- What the task did — the commit message covers it
- Structure you could re-derive by reading the code
- Anything the project's own `CLAUDE.md` or style config already states

## 2. Write what survived to the right place

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

Follow the header and body conventions in `~/.claude/knowledge/CLAUDE.md`. Write it to
`~/.claude/knowledge/pages/<project>/` and add a row to `INDEX.md`, filling in every
column.

Two header fields decide whether the page is ever seen again, so don't leave either to
be filled in later:

- **Tags** — keywords `load-knowledge` matches against a task description
- **Covers** — repo-relative path globs `check-knowledge` matches against changed
  files, or `—` if the page describes no particular paths

A page with an empty `Covers` is invisible to staleness checks. Confirm a glob matches
something real before writing it; an invented one is worse than `—`.

### Source material handed to you this session

If the task involved a pasted document, exported guide, or anything else you didn't
read out of the repo, save it verbatim to
`~/.claude/knowledge/raw/YYYY-MM-DD-<topic>.<ext>` before extracting from it, and mark
it processed per `~/.claude/knowledge/raw/README.md`. The extract is a summary; the
source is the evidence.

## 3. A `learnings.md` entry, when there was something to learn

Use the entry format from `~/.claude/knowledge/CLAUDE.md`. Include **Prevented** only
when a `gotchas.md` bullet visibly caught something during this session — that field is
the evidence a bullet is earning its place.

Nothing surprising happened? No entry. A journal of "went fine" tells the next session
nothing.

## 4. An experience entry, always

`~/.claude/knowledge/experiences/YYYY-MM-DD-<topic>.md`:

- What the task was, in one line
- Decisions made and why — especially ones a future session would otherwise re-litigate
- What surprised you, if anything
- `Updated pages:` list, or `Updated pages: none`

Keep it short on a quiet session. Three lines is a perfectly good entry.

## 5. Update `active-context.md`

If the session changed the state of open work, or identified an area now in flux,
update it. Delete finished entries rather than marking them closed.

---

## Distillation

Don't trim or archive anything here. `synthesize-knowledge` owns that, and its own
"When to run" section is the only place the thresholds live.
