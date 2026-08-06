# synthesize-knowledge

Finds recurring patterns across past sessions and distills them into
`pages/shared/patterns.md`.

## When to use

The thresholds live in [`SKILL.md`](SKILL.md) and only there — the other skills and
`knowledge/CLAUDE.md` point at it rather than restating, because three slightly
different copies of one rule is exactly how this drifted before.

In short: enough undistilled experience entries have piled up, a theme keeps repeating
in `learnings.md`, or that file has grown too long to scan.

## What it does

1. Reads undistilled entries in `experiences/`, plus `learnings.md`,
   `active-context.md`, and any existing `patterns.md`
2. Identifies repetition at a threshold of three occurrences — fragile areas,
   recurring bug classes, unwritten conventions, repeating CI failures
3. Names each pattern with frequency, area, instances, root cause, and a
   **preventive rule**
4. Writes `pages/shared/patterns.md`, adds an `INDEX.md` row, and stamps
   **Last synthesized**
5. Moves distilled entries into `experiences/archive/` and trims `learnings.md`

## Why the archive directory

Distilling used to leave entries in `experiences/`, so the count that triggered the run
never dropped and the trigger stayed permanently true. Moving them out means a run
actually clears the condition it fired on.

## Why three occurrences

Two is a coincidence. Naming it as a pattern gives it more weight than it has earned,
and a patterns page full of near-misses is one nobody trusts.

## Related

- [`update-knowledge`](../update-knowledge) — writes the experience entries this reads
- [`load-knowledge`](../load-knowledge) — loads `patterns.md` automatically when present
- [`build-knowledge`](../build-knowledge) · [`check-knowledge`](../check-knowledge)
