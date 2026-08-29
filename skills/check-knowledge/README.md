# check-knowledge

Checks the knowledge base for rot in the two ways it happens: the KB drifting from the
conventions that describe it, and pages drifting from the code they describe. Neither
errors on its own.

## When to use

The trigger lives in [`SKILL.md`](SKILL.md) and only there. In short: before a large
task, once the **Last verified** stamp has gone cold, or the moment you catch a page
claiming something untrue. Editing the conventions is its own trigger, for the first
half alone.

## What it checks

**Against the conventions**, needing no repository: required files present, every page
header carrying its six fields, `INDEX.md` agreeing with those headers, every `[[link]]`
resolving with topic pages linked both ways, and every `raw/` file carrying its marker.
Each sweep reports how many pages, rows and files it inspected, so an empty target reads
as empty rather than as clean.

**Against the code**, in the current repository: recently changed files are matched to
pages through their **Covers** globs, and two or three falsifiable claims per candidate
page are spot-checked with `grep` and `ls`. Pages come out `verified` or `stale` with a
note saying what is in doubt.

The first half is mechanical and the sweeps do it exactly. The second half is not: which
claims matter, and whether one still holds, is the judgment the skill exists to apply.

## `Covers: —` means skip

The cross-cutting pages - `gotchas`, `active-context`, `learnings`, `patterns` -
describe no particular paths and have no staleness signal to read. `—` is a real value
telling this skill to leave them alone, not a blank to be filled in. An *empty* cell is
different: that's an omission worth fixing during the pass.

Those same four are exempt from link reciprocity, in both directions - as link targets
and as the page doing the linking. A hub aggregates across the KB and points outward;
requiring a back-link from every page it mentions would put a near-identical `Related:`
line on all of them.

## Why it stamps a date, and when it must not

The "more than two weeks" trigger has to read **Last verified** from somewhere. Without
the stamp there is nothing to compare against and the trigger can never fire.

The stamp is earned only when the code half actually ran. A conventions-only pass, a run
that stopped for want of a repository, and a run whose changed-file query came back
almost empty because the clone was shallow all leave the pages unverified - and a date
written over any of those tells the next session the opposite of what happened. The
shallow case is the one to watch, because its output looks exactly like "nothing
changed".

## Related

- [`load-knowledge`](../load-knowledge) · [`update-knowledge`](../update-knowledge) ·
  [`build-knowledge`](../build-knowledge) · [`synthesize-knowledge`](../synthesize-knowledge)
