# check-knowledge

Detects stale knowledge pages by mapping recent repository changes to the pages that
describe them, then verifying their claims against live code.

## When to use

The trigger lives in [`SKILL.md`](SKILL.md) and only there. In short: before a large
task, once the **Last verified** stamp has gone cold, or the moment you catch a page
claiming something untrue.

## What it does

1. Confirms it's in a git repository, and stops with a clear message if not
2. Lists files changed in the last two weeks in the **current** repo — no hardcoded paths
3. Matches those files against each page's **Covers** globs in `INDEX.md`
4. Spot-checks two or three specific, falsifiable claims per candidate page
5. Updates each page's `Status` and **Last updated**
6. Stamps **Last verified** in `INDEX.md`
7. Reports verified pages, stale pages, and changed areas no page covers

## `Covers: —` means skip

The cross-cutting pages — `gotchas`, `active-context`, `learnings`, `patterns` —
describe no particular paths and have no staleness signal to read. `—` is a real value
telling this skill to leave them alone, not a blank to be filled in. An *empty* cell is
different: that's an omission worth fixing during the pass.

## Why it stamps a date

The "more than two weeks" trigger has to read that date from somewhere. Without the
stamp there's nothing to compare against and the trigger can never fire.

## Related

- [`load-knowledge`](../load-knowledge) · [`update-knowledge`](../update-knowledge) ·
  [`build-knowledge`](../build-knowledge) · [`synthesize-knowledge`](../synthesize-knowledge)
