# load-knowledge

Loads the personal knowledge base at `~/.claude/knowledge/` to prime context before
starting work.

## When to use

At the start of a substantial task in a project that has knowledge pages. Wired into
the global `CLAUDE.md`, so it usually runs without being asked.

## What it loads

**Always:** `learnings.md`, `INDEX.md`, `gotchas.md`, `active-context.md`, and
`pages/shared/patterns.md` if it exists.

**Then by match:** any page whose **Project** is the current repo or `shared`, and
whose **Tags** overlap the task or whose **Covers** globs match files the task will
touch.

## Status field

| Status | Meaning |
| :--- | :--- |
| `verified` | Checked against the live codebase — act on it |
| `inferred` | From exploration — spot-check specific claims before acting |
| `stale` | Known to need updating — read with skepticism |

## Related

- [`update-knowledge`](../update-knowledge) — persists learnings after a task
- [`check-knowledge`](../check-knowledge) — verifies pages are still accurate
- [`build-knowledge`](../build-knowledge) — creates pages for a new project
