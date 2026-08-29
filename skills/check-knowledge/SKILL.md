---
name: check-knowledge
description: Check the personal knowledge base for rot - first that it still obeys its own conventions (headers, INDEX rows, links, raw/ markers), then that pages describing recently changed code still hold. Use before a large task, when pages have gone unverified for a while, or after editing the conventions themselves. The When to run section states the trigger.
---

# Check the Knowledge Base for Staleness

Knowledge rots quietly, in two different ways. The KB drifts from the conventions that
describe it, and pages drift from the code they describe. Neither errors. This checks the
first against the KB itself and the second against the current repository.

## When to run

This section is the single source for this trigger. `CLAUDE.md` and the other skills
point here rather than restating it.

- Before a large task - a new feature or a significant refactor
- When **Last verified** in `INDEX.md` is more than two weeks old, or `never`
- Mid-task, scoped to one page, the moment you catch a KB claim being wrong
- After editing `CLAUDE.md` or `raw/README.md`, for section 1 alone - a conventions change
  is exactly what puts the KB out of step with them

## 1. Check the KB against its own conventions

Run from `~/.claude/knowledge`. Needs no repository, so this section runs even when the
rest of the skill cannot.

Do this before section 3 rather than after. That section reads `INDEX.md` to decide which
pages to verify, and an `INDEX.md` that disagrees with the page headers makes the mapping
unreliable rather than merely untidy.

**Every check below prints nothing on a healthy KB.** Output is the finding.

### Required files, and the fields two triggers read

```bash
for f in CLAUDE.md INDEX.md learnings.md gotchas.md active-context.md raw/README.md; do
  [ -e "$f" ] || echo "MISSING $f"
done
grep -q '^\*\*Last verified:\*\*' INDEX.md || echo "MISSING Last verified"
grep -q '^\*\*Last synthesized:\*\*' INDEX.md || echo "MISSING Last synthesized"
```

Those two dates are what this skill's own staleness trigger and `synthesize-knowledge`'s
read. Absent, both triggers have nothing to compare against and simply never fire.

### Page headers carry all six fields

```bash
echo "inspecting $(ls pages/*/*.md 2>/dev/null | wc -l | tr -d ' ') pages"
for f in pages/*/*.md; do
  for k in Project Tags Covers Status "Last updated" Related; do
    grep -q "^\*\*$k:\*\*" "$f" || echo "$f missing $k"
  done
done
```

A page with no `Tags` is never loaded by anything. A page with an empty `Covers` is
invisible to the mapping in section 3. Both fail by omission, which is why they need a
sweep rather than a habit.

### INDEX.md agrees with the headers

```bash
for f in pages/*/*.md; do n=$(basename "$f" .md)
  grep -q "\[$n\]" INDEX.md || echo "NOT IN INDEX: $n"; done
grep -oE '^\| \[[a-z0-9-]+\]' INDEX.md | tr -d '|[] ' | while read n; do
  [ -n "$n" ] && { find pages -name "$n.md" | grep -q . || echo "ROW WITHOUT PAGE: $n"; }; done
for f in pages/*/*.md; do n=$(basename "$f" .md); row=$(grep "^| \[$n\]" INDEX.md)
  [ -z "$row" ] && continue
  for k in Tags Covers Status; do
    hdr=$(grep "^\*\*$k:\*\*" "$f" | sed "s/^\*\*$k:\*\* *//"); [ -z "$hdr" ] && continue
    echo "$row" | grep -qF "$hdr" || echo "MISMATCH $n $k: header='$hdr'"; done; done
```

`INDEX.md` is a derived cache and the header is the source of truth, so fix the row from
the header rather than reconciling by hand.

### Links resolve and topic pages link both ways

```bash
pages=$(find . -name '*.md' | sed 's#.*/##;s#\.md$##' | sort -u)
for t in $(grep -rhoE '\[\[[a-z0-9-]+\]\]' . 2>/dev/null | sort -u | tr -d '[]'); do
  echo "$pages" | grep -qx "$t" || echo "DANGLING [[$t]]"; done
for f in $(find pages -name '*.md'); do me=$(basename "$f" .md)
  case "$me" in gotchas|active-context|learnings|patterns) continue;; esac
  for t in $(grep -ohE '\[\[[a-z0-9-]+\]\]' "$f" | sort -u | tr -d '[]'); do
    case "$t" in gotchas|active-context|learnings|patterns|INDEX) continue;; esac
    tf=$(find . -name "$t.md" | head -1); [ -z "$tf" ] && continue
    grep -q "\[\[$me\]\]" "$tf" || echo "ONE-WAY $me -> $t"; done; done
```

The four hub pages are exempt from reciprocity by design, so they are skipped in both
directions - as link targets and as the page doing the linking. The second `case` matters
once `patterns.md` exists, because `synthesize-knowledge` writes it under `pages/` where
this loop iterates it; the other three hubs sit at the KB root and never reach the loop at
all, which is why a target-only exemption looked sufficient for as long as it did.

`MAINTENANCE.md` Rule 10 looks similar and is not a duplicate: it runs from the skills
repository, where `knowledge/` holds only the empty scaffold. It cannot see a live page.
This one runs where the pages actually are.

### Every file in raw/ carries a first-line marker

```bash
echo "inspecting $(ls raw/* 2>/dev/null | grep -v '/README.md$' | wc -l | tr -d ' ') raw files"
for f in raw/*; do [ -f "$f" ] || continue
  case "$(basename "$f")" in README.md) continue;; esac
  case "$(head -1 "$f")" in
    *'processed:'*|*'internal-only: do not extract'*) ;;
    *) echo "UNMARKED (reads as pending): $f";; esac; done
```

An unmarked file reads as awaiting extraction. That is correct for genuinely pending
material and wrong for anything already extracted or never extractable, and the difference
is invisible without this. See `raw/README.md` for what each marker means.

### If the layout differs

These globs assume pages under `pages/`. An install that puts them elsewhere adjusts the
paths, and should say so in its own `CLAUDE.md` rather than leaving the next reader to
infer it from a failing sweep.

## 2. Find what changed

Confirm you're in a repository first - this skill has nothing to work from otherwise:

```bash
git rev-parse --show-toplevel 2>/dev/null || echo "not a git repo"
```

If that fails, say so and stop here. Section 1 has already run and needs no repository;
the rest of this skill has nothing to work from, and verifying pages by hand against a
non-repo directory isn't its job.

Then list what moved:

```bash
[ "$(git rev-parse --is-shallow-repository)" = true ] && echo "SHALLOW: history is truncated, results below are not trustworthy - git fetch --unshallow"
git log --since=2.weeks --no-merges --name-only --pretty=format: | sort -u | grep -v '^$'
```

On a shallow clone the query returns almost nothing and the skill then verifies no pages
and stamps **Last verified** anyway - a silent false clean, and the one failure here that
looks exactly like success. Stop and deepen the clone rather than reading an empty result
as "nothing changed".

`--no-merges` avoids double-counting: a merge commit's files already appear via the
commits it brought in. The exception is a merge of work older than the window, whose
commits `--since` filters out - widen the window if a known-busy area shows nothing.

Widen or narrow the window generally: too little returned means it's too short, and
everything matching means it's too long to be useful.

**This two-week lookback is unrelated to the two-week staleness interval below**, even
though the numbers match. This one asks "what changed recently"; that one asks "how
long since anyone checked". Changing one does not imply changing the other - but if
**Last verified** is older than this window, widen the window to reach back at least
that far, or the changes in between are never examined by anything.

## 3. Map changed files to pages

Read `~/.claude/knowledge/INDEX.md`. For each page whose **Project** is the current
repo or `shared`, match its **Covers** globs against the changed files. A page whose
covered paths changed is a candidate for staleness.

**`Covers: —` means skip the page.** The cross-cutting pages - `gotchas`,
`active-context`, `learnings`, `patterns` - describe no particular paths, so they
have no staleness signal to read. Don't invent globs for them.

A page with an *empty* Covers cell is different: that's an omission. Fill it in from
what the page actually discusses, or set it to `—` if it genuinely covers no paths.

Note any changed area that no page covers. That's a coverage gap, not a staleness
problem, and it belongs in the report rather than being fixed here.

## 4. Verify key claims

For each candidate page, spot-check two or three specific claims - the ones a future
session would act on:

- Class or function names → `grep -r "<name>"` in the relevant directory
- File paths → confirm with `ls` or `find`
- Signatures and call sites → `grep` for the caller, not just the definition

Check specific, falsifiable claims. "The module handles retries" can't be verified;
"`RetryPolicy.maxAttempts` defaults to 3" can.

## 5. Update status

| Outcome | Action |
| :--- | :--- |
| Claim holds | Bump **Last updated**, set `Status: verified` |
| Claim is wrong | Fix the content, set `Status: verified`, and add a line to `gotchas.md` if the change itself was surprising |
| Can't verify now | Set `Status: stale` and note what specifically is in doubt |

`stale` without a note is useless to the next session - always say what changed and
what needs confirming.

## 6. Update `INDEX.md`

Set **Last verified** to today's date. That field is what this skill's own
"more than two weeks" trigger reads; without it there's nothing to compare against,
and the trigger can never fire.

**Only stamp it after sections 3-5 actually ran.** A section-1-only pass - the one
"When to run" allows after a conventions edit - verifies the KB against its conventions,
not against the code. Stamping it claims something that was not checked, and the next
session reads the date as proof the pages were verified. Same for a run that stopped at
section 2 for want of a repository, or one whose changed-file query came back empty
because the clone was shallow: no mapping, no verification, no stamp.

## 7. Report

- Pages verified
- Pages marked stale, and why
- Areas with recent activity and no page covering them

If an uncovered area matters, flag it for a `build-knowledge` pass rather than
writing the page here.
