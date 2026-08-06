# synthesize-knowledge

Finds recurring patterns across past sessions and distills them into
`pages/shared/patterns.md`.

## When to use

- `experiences/` has 5 or more entries
- `learnings.md` shows the same area, bug class, or failure mode in 3+ entries
- You realize mid-session you've solved this exact problem before

Wired into the global `CLAUDE.md` for the first two.

## What it does

1. Reads all of `experiences/`, `learnings.md`, and `active-context.md`
2. Identifies repetition — fragile areas, recurring bug classes, unwritten
   conventions, repeating CI failures — at a threshold of three occurrences
3. Names each pattern with frequency, area, instances, root cause, and a
   **preventive rule**
4. Writes `pages/shared/patterns.md` and adds a row to `INDEX.md`
5. Archives distilled entries and trims `learnings.md` to its 10 most recent

## Why three occurrences

Two is a coincidence. Naming it as a pattern gives it more weight than it has earned,
and a patterns page full of near-misses is one nobody trusts.

## Related

- [`load-knowledge`](../load-knowledge) — loads `patterns.md` automatically when present
- [`update-knowledge`](../update-knowledge) — writes the experience entries this reads
- [`build-knowledge`](../build-knowledge) · [`check-knowledge`](../check-knowledge)
