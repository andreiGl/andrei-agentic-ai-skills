---
name: build-knowledge
description: Build or extend the personal knowledge base at ~/.claude/knowledge/ for a project. Use when asked to create a knowledge base, add a project to the KB, process source material into knowledge pages, or bootstrap context for a codebase that has none yet.
---

# Build or Extend the Knowledge Base

Read `~/.claude/knowledge/CLAUDE.md` first — it defines the layout, the page header,
and the **Category A gate**. This skill covers the procedure, not the conventions.

Apply that gate ruthlessly here, because this is where the most material arrives at
once. Expect to discard most of what you gather. A KB that restates the codebase is
worse than no KB: it goes stale silently and nobody notices.

---

## Building for a new project

1. **Explore.** Spawn parallel Explore agents to gather:
   - Surprises, gotchas, behavior that contradicts expectations
   - Conventions the project enforces but doesn't state in code
   - Failure modes and past incidents visible in git log, issues, or docs
   - Constraints imposed by systems outside the repo

   Do not gather module lists, class hierarchies, or package structure. If an agent
   returns those, drop them.

2. **Create the directories:**
   ```bash
   mkdir -p ~/.claude/knowledge/pages/<project> ~/.claude/knowledge/pages/shared \
            ~/.claude/knowledge/experiences/archive ~/.claude/knowledge/raw
   ```

   **Then check the files every skill assumes exist**, and write them if they don't:

   - `~/.claude/knowledge/CLAUDE.md` — the conventions. Step 1 above tells you to read
     it, and every other skill defers to it for the page header, the gate, and the link
     rules. On a KB that has never been built, it is absent, and each of those pointers
     resolves to nothing — the ownership scheme quietly becomes "nobody states this."
   - `~/.claude/knowledge/raw/README.md` — the provenance convention `update-knowledge`
     points at when saving source material.
   - `INDEX.md`, `learnings.md`, `gotchas.md`, `active-context.md` — created in steps
     5-8 below, but create them empty now so nothing reads a missing file mid-run.

   Copy these from an existing KB if you have one. Don't invent conventions here: this
   skill is a consumer of that file, not its author.

3. **Apply the gate to everything gathered.** Sort into: page-worthy, one-line gotcha,
   or discard. Most lands in the third bucket.

4. **Write the pages** that survived, into `pages/<project>/`. Every structural fact
   needs a **Why:** sentence — the why survives refactoring, the what doesn't.
   Set `Status: inferred` for anything taken from exploration rather than verified
   against live code.

5. **Populate `gotchas.md`** from the Gotchas section of every page written.

6. **Build `INDEX.md`.** It needs two things:

   - A **KB status** block with `Last verified: never` and `Last synthesized: never`.
     `check-knowledge` and `synthesize-knowledge` stamp those fields and read them to
     decide whether they are due. Omit the block and both triggers have nothing to
     evaluate — they never fire, silently.
   - A **row per page** — Page, Project, Tags, Covers, Status. Tags are never optional:
     a page without them will never be surfaced by `load-knowledge`. Covers may be `—`
     when the page describes no particular paths, which tells `check-knowledge` to skip
     it rather than invent globs.

7. **Update `active-context.md`** with open work and areas currently in flux.

8. **Seed `learnings.md`** with the non-obvious findings from the exploration.

9. **Write an experience entry** in `experiences/YYYY-MM-DD-<topic>.md` with an
   `Updated pages:` list.

---

## Extending an existing KB

1. Read `learnings.md` and `INDEX.md` before writing anything — the fact may already
   be recorded, or contradicted.
2. Save any raw source material in `raw/YYYY-MM-DD-<topic>.<ext>`.
3. Apply the gate.
4. New fact → a line in `gotchas.md`. A full page only if three sentences won't do.
5. Update `INDEX.md` and add `[[links]]` in both directions.
6. Append to `learnings.md` and write an experience entry.

---

## Before you finish

- Every page passes the Category A gate
- Every structural fact has a **Why:**
- Every header has Project, Tags, Covers, Status, Last updated, Related
- Code blocks are annotated with a language
- `[[links]]` resolve, in both directions
- `INDEX.md` has a row per page, every column filled — `—` where Covers doesn't apply,
  never an empty cell
- No module lists, class hierarchies, or restated style rules
