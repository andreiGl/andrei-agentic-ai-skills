# load-knowledge

Loads the personal knowledge base at `~/.claude/knowledge/` to prime context before
starting work.

## When to use

At the start of any substantial task. Wired into the global `CLAUDE.md`, so it usually
runs without being asked.

Don't check whether the project has pages before running it — that check is the skill's
first step, and the empty case costs one line.

## What it does

Reads a fixed set of always-load files, then any page whose **Project** matches the
current repo (or `shared`) and whose **Tags** overlap the task or whose **Covers**
globs match files in play.

The exact always-load list lives in [`SKILL.md`](SKILL.md) and only there — it used to
be repeated in `INDEX.md`, and the two drifted.

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
