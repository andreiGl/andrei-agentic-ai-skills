# check-knowledge

Detects stale knowledge pages by mapping recent repository changes to the pages that
describe them, then verifying their claims against live code.

## When to use

- Before a large task (new feature, significant refactor)
- When more than two weeks have passed since pages were last verified
- Mid-task, scoped to a single page, when you catch a KB claim being wrong

Wired into the global `CLAUDE.md` for the first two cases.

## What it does

1. Lists files changed in the last two weeks in the **current** repo — no hardcoded paths
2. Matches those files against each page's **Covers** globs in `INDEX.md`
3. Spot-checks two or three specific, falsifiable claims per candidate page
4. Updates status:
   - Claim holds → bump `Last updated`, set `Status: verified`
   - Claim is wrong → fix it, set `Status: verified`, add to `gotchas.md` if surprising
   - Can't verify → set `Status: stale` **with a note on what's in doubt**
5. Reports verified pages, stale pages, and changed areas no page covers

## Why `Covers` matters

The file-to-page mapping is data, held in each page's header, not a table inside this
skill. A page with no `Covers` value can never be checked — filling it in is part of
this pass.

## Related

- [`load-knowledge`](../load-knowledge) · [`update-knowledge`](../update-knowledge) ·
  [`build-knowledge`](../build-knowledge) · [`synthesize-knowledge`](../synthesize-knowledge)
