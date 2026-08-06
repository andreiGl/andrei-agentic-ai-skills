---
name: build-knowledge
description: Build or extend the personal knowledge base at ~/.claude/knowledge/ for a project. Use when asked to create a knowledge base, add a project to the KB, process source material into knowledge pages, or bootstrap context for a codebase that has none yet.
---

# Build or Extend the Knowledge Base

Read `~/.claude/knowledge/CLAUDE.md` first — it defines the layout, the page header,
and the **Category A gate**. This skill covers the procedure, not the conventions.

The gate does most of the work here: **if a fact can be derived from reading the code
in under 3 tool calls, it does not become a page.** Expect to discard most of what
you gather. A KB that restates the codebase is worse than no KB, because it goes
stale silently and nobody notices.

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
   mkdir -p ~/.claude/knowledge/pages/<project> ~/.claude/knowledge/experiences ~/.claude/knowledge/raw
   ```

3. **Apply the gate to everything gathered.** Sort into: page-worthy, one-line gotcha,
   or discard. Most lands in the third bucket.

4. **Write the pages** that survived, into `pages/<project>/`. Every structural fact
   needs a **Why:** sentence — the why survives refactoring, the what doesn't.
   Set `Status: inferred` for anything taken from exploration rather than verified
   against live code.

5. **Populate `gotchas.md`** from the Gotchas section of every page written.

6. **Add rows to `INDEX.md`** — Page, Project, Tags, Covers, Status. A page with no
   Tags and no Covers will never be surfaced by `load-knowledge` or checked by
   `check-knowledge`.

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
- `INDEX.md` has a row per page, with Tags and Covers filled in
- No module lists, class hierarchies, or restated style rules
