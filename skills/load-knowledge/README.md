# load-knowledge

Loads the personal knowledge base at `~/.claude/knowledge/` to prime context before
starting work.

## When to use

The trigger lives in [`SKILL.md`](SKILL.md) and only there. In short: before the first
substantive tool call of a task, rather than whenever the task starts to feel big.

Don't check whether the project has pages before running it — that check is the skill's
first step, and the empty case costs one line.

## What it does

Reads a fixed set of always-load files, then any page whose **Project** matches the
current repo (or `shared`) and whose **Tags** overlap the task or whose **Covers**
globs match files in play.

The exact always-load list lives in [`SKILL.md`](SKILL.md) and only there — it used to
be repeated in `INDEX.md`, and the two drifted.

## Status field

The values are defined in `knowledge/CLAUDE.md`. This skill covers what to *do* with a
page that isn't `verified` — spot-check a claim before acting on it, then promote or fix.

## Related

- [`update-knowledge`](../update-knowledge) — persists learnings after a task
- [`check-knowledge`](../check-knowledge) — verifies pages are still accurate
- [`build-knowledge`](../build-knowledge) — creates pages for a new project
