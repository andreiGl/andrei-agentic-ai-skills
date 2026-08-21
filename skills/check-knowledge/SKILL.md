---
name: check-knowledge
description: Detect stale pages in the personal knowledge base by mapping recent repository changes to knowledge pages, then verifying their key claims against live code. Use before a large task, or when pages have gone unverified for a while. The When to run section states the trigger.
---

# Check the Knowledge Base for Staleness

Knowledge pages rot quietly. This maps recent activity in the current repository to
the pages that claim to describe it, and verifies those claims still hold.

## When to run

This section is the single source for this trigger. `CLAUDE.md` and the other skills
point here rather than restating it.

- Before a large task — a new feature or a significant refactor
- When **Last verified** in `INDEX.md` is more than two weeks old, or `never`
- Mid-task, scoped to one page, the moment you catch a KB claim being wrong

## 1. Find what changed

Confirm you're in a repository first — this skill has nothing to work from otherwise:

```bash
git rev-parse --show-toplevel 2>/dev/null || echo "not a git repo"
```

If that fails, stop and say so. Verifying pages by hand against a non-repo directory
isn't this skill's job.

Then list what moved:

```bash
git log --since=2.weeks --no-merges --name-only --pretty=format: | sort -u | grep -v '^$'
```

`--no-merges` avoids double-counting: a merge commit's files already appear via the
commits it brought in. The exception is a merge of work older than the window, whose
commits `--since` filters out — widen the window if a known-busy area shows nothing.

Widen or narrow the window generally: too little returned means it's too short, and
everything matching means it's too long to be useful.

**This two-week lookback is unrelated to the two-week staleness interval below**, even
though the numbers match. This one asks "what changed recently"; that one asks "how
long since anyone checked". Changing one does not imply changing the other — but if
**Last verified** is older than this window, widen the window to reach back at least
that far, or the changes in between are never examined by anything.

## 2. Map changed files to pages

Read `~/.claude/knowledge/INDEX.md`. For each page whose **Project** is the current
repo or `shared`, match its **Covers** globs against the changed files. A page whose
covered paths changed is a candidate for staleness.

**`Covers: —` means skip the page.** The cross-cutting pages — `gotchas`,
`active-context`, `learnings`, `patterns` — describe no particular paths, so they
have no staleness signal to read. Don't invent globs for them.

A page with an *empty* Covers cell is different: that's an omission. Fill it in from
what the page actually discusses, or set it to `—` if it genuinely covers no paths.

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

## 5. Update `INDEX.md`

Set **Last verified** to today's date. That field is what this skill's own
"more than two weeks" trigger reads; without it there's nothing to compare against,
and the trigger can never fire.

## 6. Report

- Pages verified
- Pages marked stale, and why
- Areas with recent activity and no page covering them

If an uncovered area matters, flag it for a `build-knowledge` pass rather than
writing the page here.
