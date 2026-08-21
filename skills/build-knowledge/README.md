# build-knowledge

Builds or extends the personal knowledge base at `~/.claude/knowledge/` for a project.

## When to use

The trigger lives in [`SKILL.md`](SKILL.md) and only there. In short: only when asked -
to create a KB, add a project to one, or turn source material into pages.

Building a KB is a deliberate task, not something to do as a detour mid-work. Finding
that a project has no pages is not a reason to start one.

## What it does

**For a new project:** spawns parallel Explore agents to gather surprises, unwritten
conventions, failure modes, and external constraints; applies the Category A gate to
everything gathered; writes what survives into `pages/<project>/`; then populates
`gotchas.md`, `INDEX.md`, `active-context.md`, `learnings.md`, and an experience entry.

**For an existing KB:** reads `learnings.md` and `INDEX.md` first, saves raw material
in `raw/`, applies the gate, and adds a `gotchas.md` line or a full page.

Tags are never optional - a page without them is never loaded. Covers may be `—` when
the page describes no particular paths, which tells `check-knowledge` to skip it.

## The gate does most of the work

The Category A gate is defined in `knowledge/CLAUDE.md`. Expect to discard most of what
exploration turns up - a KB that restates the codebase goes stale silently and stops
being read.

## Related

- [`load-knowledge`](../load-knowledge) · [`update-knowledge`](../update-knowledge) ·
  [`check-knowledge`](../check-knowledge) · [`synthesize-knowledge`](../synthesize-knowledge)
