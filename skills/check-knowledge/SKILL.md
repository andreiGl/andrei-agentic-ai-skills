---
name: check-knowledge
description: Detect stale pages in the personal knowledge base by mapping recent repository changes to knowledge pages, then verifying their key claims against live code. Use before a large task, or when it has been more than two weeks since pages were last verified.
---

# Check the Knowledge Base for Staleness

Knowledge pages rot quietly. This maps recent activity in the current repository to
the pages that claim to describe it, and verifies those claims still hold.

## 1. Find what changed

Run in the current repository — do not assume a path:

```bash
git log --since=2.weeks --name-only --pretty=format: | sort -u | grep -v '^$'
```

Widen the window if it returns almost nothing, or narrow it if the repo is busy
enough that everything matches.

## 2. Map changed files to pages

Read `~/.claude/knowledge/INDEX.md`. For each page whose **Project** is the current
repo or `shared`, match its **Covers** globs against the changed files. A page whose
covered paths changed is a candidate for staleness.

If a page has no **Covers** value, it can't be checked this way. Fill it in — that's
part of this pass, not a separate chore.

Note any changed area that no page covers. That's a coverage gap, not a staleness
problem, and it belongs in the report rather than being fixed here.

## 3. Verify key claims

For each candidate page, spot-check two or three specific claims — the ones a future
session would act on:

- Class or function names → `grep -r "<name>"` in the relevant directory
- File paths → confirm with `ls` or `find`
- Signatures and call sites → `grep` for the caller, not just the definition

Check specific, falsifiable claims. "The module handles retries" can't be verified;
"`RetryPolicy.maxAttempts` defaults to 3" can.

## 4. Update status

| Outcome | Action |
| :--- | :--- |
| Claim holds | Bump **Last updated**, set `Status: verified` |
| Claim is wrong | Fix the content, set `Status: verified`, and add a line to `gotchas.md` if the change itself was surprising |
| Can't verify now | Set `Status: stale` and note what specifically is in doubt |

`stale` without a note is useless to the next session — always say what changed and
what needs confirming.

## 5. Report

- Pages verified
- Pages marked stale, and why
- Areas with recent activity and no page covering them

If an uncovered area matters, flag it for a `build-knowledge` pass rather than
writing the page here.

---

## When to run

- Before a large task — a new feature or a significant refactor
- When more than two weeks have passed since any page was marked `verified`
- Mid-task, scoped to one page, the moment you catch a KB claim being wrong
