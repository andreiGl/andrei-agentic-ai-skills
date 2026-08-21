# Maintaining These Skills

The skills form a system: one writes what another reads. Most defects found so far were
not in any single file but in the seams between them, and none of them threw an error -
they degraded silently and looked correct in review.

This file is the procedure that catches them. It lives in the repo because it is the
maintenance procedure for the thing it sits next to.

**Every rule below carries its command and that command's expected output.** A rule
written as prose is not a check - it passes review, reads as coverage, and never runs.
Where a rule genuinely can't be a command it says so explicitly, so it's visibly a manual
step rather than something a sweep is assumed to cover.

Run everything from the repo root.

---

## The four failure shapes

**One fact, several files.** A rule written in two places drifts, because nothing forces
copies to agree. Every fact has one owner; other files point at it.

| Fact | Owner |
| :--- | :--- |
| Layout, page header, Category A gate, link rules | `knowledge/CLAUDE.md` |
| Which files load at session start | `skills/load-knowledge/SKILL.md` |
| Distillation and trimming thresholds | `skills/synthesize-knowledge/SKILL.md` |
| Page routing data (Tags, Covers) | The page headers; `INDEX.md` is a derived cache |

**A reader with no writer.** For every path or field a skill reads, some skill must write
it. Two sub-forms, and only the first is greppable:

1. The writer never mentions it.
2. The writer mentions it *after* the reader runs. Both halves correct; sequence wrong.

**A check that exists only as prose.** "Confirm that X" in a document is not a check.
Every rule here has a command for this reason.

**A skill that never fires.** Every rule below checks whether the repository agrees with
itself. None checks whether a skill is reachable - whether its `description` matches the
work a person is actually doing, which is what decides if it gets invoked at all. A skill
whose description names only code will sit out a long research task, silently, while the
work gets done without it.

No command covers this, and none is offered, because a sweep that can't see the defect
would read as coverage. The symptom is behavioural: you finish something substantial,
then notice the skill that governs it was never invoked. When that happens, the fix is
almost always in the `description` - it is the only part a model matches against.

---

## Rule 1 - every path a skill reads, some skill writes

```bash
grep -rhoE '~/\.claude/knowledge/[A-Za-z0-9_./<>-]+' skills/*/SKILL.md \
  | sed 's#/$##' | sort -u | while read p; do
    case "$p" in *'<'*|*YYYY*) continue;; esac
    [ -e "${p/#\~/$HOME}" ] || echo "READ BUT ABSENT: $p"
  done
```

**Expected:** exactly one line, `~/.claude/knowledge/pages/shared/patterns.md`. It's
created on first synthesis and its reader guards for absence. Anything else is a bug.

## Rule 2 - path targets absolute, prose referents may stay relative

Absolute form means one sweep finds them all. Bare directory names used as prose
("files directly in `experiences/`") aren't targets and shouldn't be normalized.

```bash
grep -rnoE '`(raw|pages|experiences)/[A-Za-z0-9_./<>-]*`' skills/*/SKILL.md
```

**Expected:** exactly two lines - a prose referent in `synthesize-knowledge`'s trigger
list, and a section heading naming its own output file. Anything else is a target that
needs absolutising.

## Rule 3 - sweeps for duplicated definitions anchor on defining syntax

Not on the term. A skill that says "set `Status: stale`" is a consumer doing its job.

```bash
grep -rln "3 tool calls" skills/ knowledge/*.md      # Category A gate
grep -rln '`stale` -' skills/ knowledge/             # Status values
grep -rn "20 entries\|5 or more entries\|5+ entries\|5+ experience" \
  skills/ knowledge/*.md CLAUDE.md README.md \
  | grep -v "synthesize-knowledge/"                  # synthesis thresholds
grep -rn "two weeks\|2+ weeks" skills/ knowledge/*.md CLAUDE.md README.md \
  | grep -v "check-knowledge/"                       # staleness window
for s in skills/*/SKILL.md; do                       # descriptions
  sed -n '3p' "$s" | grep -qE "5\+|5 or more|20 entries|3\+ entries" && echo "BUG $s"
done
```

**Expected:** first two print `knowledge/CLAUDE.md` and nothing else. Last three print
nothing. `description:` drives auto-invocation, so a stale threshold there is the copy
being matched.

Each numeric trigger has one owner: synthesis thresholds in `synthesize-knowledge`, the
staleness window in `check-knowledge`, the update trigger in `update-knowledge`'s *When
to run*, the load trigger in `load-knowledge`'s description. `CLAUDE.md` names the
skills and none of their conditions, which is why it appears in both sweeps above.

`README.md` is in the file list because it wasn't, and quietly held both thresholds in a
"When it runs" table - the same omission Rule 7 documents. Shorthand spellings are in the
patterns for the same reason: the table wrote them as `2+ weeks` and `5+ experience
entries`, which the original patterns missed.

The exclusions are directories, not files. A skill owns its trigger across both its
`SKILL.md` and its `README.md` - narrowing the exclusion to `SKILL.md` flags the owner's
own README as a foreign copy, which is how this rule first fired on a clean repo.

## Rule 4 - any sweep with a non-empty expected set carries that set inline

Otherwise it decays into noise and gets ignored, which is worse than not having it -
it reads as confirmation. Every check here states its expected output inline, whether
that is a set of lines, a count, or silence.

Prefer a count to silence where one is available. A sweep that prints nothing on success
prints nothing on a botched invocation too, and the enumeration that used to sit in this
paragraph went stale twice, which is the same defect one level up.

Scope sweeps to tracked files. An unscoped walk picks up `plugins/` and marketplace
caches, whose broken links are not ours to fix.

## Rule 5 - edit reader and writer in the same change

**Manual: no command covers this.**

When a field is added to both in one pass it holds; when the writer is left for later,
later doesn't come. If you can't do both, leave the half-done state visibly broken rather
than silently degraded.

This applies *within* a file too. A preamble and a numbered step are a reader/writer
pair. So are a step and a cross-reference to it. Both copies of these skills
independently produced the same two intra-file defects in `build-knowledge`.

## Rule 6 - after reordering or moving anything, read the step sequence

**Manual: no command covers this.** "Does step N depend on step M > N" needs the
semantics of the steps.

Read the numbered sequence straight through and ask what each step assumes already
exists. Run it after inserting a step, reordering steps, or moving a file.

Known-good baseline: `synthesize-knowledge` appends to `learnings.md` *after* trimming
it - reverse that and the trim eats the synthesis entry. `check-knowledge` guards for a
repository before using one. `build-knowledge` creates the conventions file before step 4
reads it.

## Rule 7 - links resolve, across every tracked file

Scoped to `git ls-files`, not `find`. An earlier version of this walked only `skills/`
and `knowledge/`, silently omitting `README.md`, `CLAUDE.md`, and this file - the three
most-read files in the repo, unchecked. The parallel copy had the same gap and it hid
five links broken by the round-1 flatten.

```bash
git ls-files '*.md' | while read f; do d=$(dirname "$f")
  grep -oE '\]\([^)h#][^)]*\)' "$f" | sed 's/](\(.*\))/\1/' | while read l; do
    [ -e "$d/${l%%#*}" ] || echo "BROKEN $f -> $l"
  done
done
echo "scanned: $(git ls-files '*.md' | wc -l | tr -d ' ') files"
```

**Expected:** no `BROKEN` lines, and a scanned count matching the tracked Markdown files.

The count is the point of the second line. Silence alone cannot tell a clean sweep from
one that listed no files, matched no glob, or ran in the wrong directory. Two of those
fail open.

## Rule 8 - skills sit one level deep, or they are never registered

```bash
find -L ~/.claude/skills -mindepth 3 -name SKILL.md
for s in $(find -L ~/.claude/skills -maxdepth 2 -name SKILL.md); do
  d=$(basename "$(dirname "$s")"); n=$(sed -n 's/^name: *//p' "$s" | head -1)
  [ "$d" = "$n" ] || echo "NAME MISMATCH: dir $d declares name $n"
done
echo "registered: $(find -L ~/.claude/skills -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')"
echo "repo dirs:  $(ls -d skills/*/ | wc -l | tr -d ' ')"
```

**Expected:** nothing from the first two; the two counts equal.

An earlier version asserted a fixed number here. It went stale on every legitimate
addition, and two commits exist for no purpose other than bumping it - `03b9e74` and
`0140b0a`. A check that generates a maintenance commit per addition is one people learn
to edit rather than trust, so it now compares counts instead of naming one.

The name check is the other half. Claude Code registers a skill by directory, and the
frontmatter `name` is what everything else refers to; when they disagree the skill is
reachable under one label and documented under another.

`-L` is load-bearing: the live skill directories are symlinks into this repo, and `find`
won't follow them without it. Without `-L` the first command reports no nested skills -
while the second reports zero skills at all, which is the only signal it's broken rather
than clean. Check the count, not just the silence.

## Rule 9 - frontmatter parses as YAML

```bash
for s in skills/*/SKILL.md; do
  awk -v f="$s" '/^description:/{d=substr($0,13); if (d ~ /: /) print "YAML BREAK " f}' "$s"
done
echo "scanned: $(ls skills/*/SKILL.md | wc -l | tr -d ' ') skills"
```

**Expected:** no `YAML BREAK` lines, and a scanned count equal to the skill directories.

An unquoted YAML scalar cannot contain `: ` - the parser reads it as a nested key and
the whole block fails. Claude Code tolerates this and matches the description anyway, so
the only place it surfaces is GitHub's rendered view of the file, as *mapping values are
not allowed in this context*. Nothing in the local workflow catches it.

The fix is a dash or a semicolon, not quoting: all seven descriptions are unquoted, and
one quoted outlier invites the next editor to quote inconsistently.

## Rule 10 - KB link graph

```bash
pages=$(find knowledge -name '*.md' | sed 's#.*/##;s#\.md$##' | sort -u)
for t in $(grep -rhoE '\[\[[a-z0-9-]+\]\]' knowledge/ | sort -u | tr -d '[]'); do
  echo "$pages" | grep -qx "$t" || echo "DANGLING [[$t]]"
done

for f in $(find knowledge -name '*.md' ! -name 'INDEX.md'); do
  me=$(basename "$f" .md)
  case "$me" in gotchas|active-context|learnings|patterns|CLAUDE|README) continue;; esac
  for t in $(grep -ohE '\[\[[a-z0-9-]+\]\]' "$f" | sort -u | tr -d '[]'); do
    tf=$(find knowledge -name "$t.md" | head -1); [ -z "$tf" ] && continue
    grep -q "\[\[$me\]\]" "$tf" || echo "ONE-WAY $me -> $t"
  done
done
```

**Expected:** no output from either check.

The dangling check used to expect five template placeholders, which meant a rule whose
documented pass state included five failures. A check that expects failures stops being
read. The placeholders now carry angle brackets inside them, `[[<page-name>]]`, so they
read as placeholders to a person and match nothing as a link.

The one-way check prints nothing because hub pages are exempt by design and skipped
above. Dated entries under `experiences/` reference pages by plain name rather than link
syntax, for the same reason: a durable page should not accumulate a back-link to every
session that mentioned it.

## Rule 11 - repository integrity

```bash
git fsck --no-progress --no-dangling
find .git/refs -name 'Icon?' | wc -l   # blocking - one of these stops fetch
find .git -name 'Icon?' | wc -l        # total; anything beyond refs/ is noise
```

**Expected:** no output from the first; `0` from both counts.

macOS Finder creates a file named `Icon` followed by a carriage return in every
directory of a folder carrying a custom icon - including inside `.git`. Git treats every
file under `refs/` as a ref, so `refs/Icon\r` becomes a ref pointing at the null SHA and
**`git fetch` fails outright** with `bad object refs/Icon?`. The same files under
`objects/` make `fsck` report `bad sha1 file` for each one.

Those two outcomes are not the same emergency, which is why the counts are separate.

| Where | Effect | Urgency |
| :--- | :--- | :--- |
| `.git/refs/` | `git fetch` fails outright | fix before anything else |
| `.git/objects/` | one `bad sha1 file` line per file, from `fsck` only | fix when convenient |

Object names under `.git/objects/XX/` are the remaining 38 hex characters of a SHA.
`Icon\r` isn't hex, so nothing ever looks it up; only `fsck`, which walks the directory
whole, notices. Measured on this repo: 27 of them in `objects/` and none in `refs/`,
with `git fetch --dry-run` exiting 0. A single one in `refs/` would have stopped it.

The `Icon?` line in `.gitignore` cannot help here: `.gitignore` governs what gets
committed, not what exists inside `.git`. This is a class of breakage no content sweep
reaches, which is why it gets its own rule.

Clean up with:

```bash
find . -name 'Icon?' -type f -delete
```

`--no-dangling` is not optional. Dangling blobs are normal - staging a file and then
editing it leaves one, and so does any amend or reset. Without the flag the rule fails on
ordinary work and gets ignored, which Rule 4 warns about.

`com.apple.FinderInfo` on the directory is one cause, and clearing it with
`xattr -d com.apple.FinderInfo <dir>` removes both the attribute and the folder's custom
icon. It is not the only cause: these have reappeared here with no such attribute on the
repository or any parent, so treat recurrence as expected and re-run the check rather
than assuming one clean-up settles it.

## Rule 12 - em dashes stay out of prose

```bash
EM=$(printf '\342\200\224')
git ls-files | xargs grep -n "$EM" | grep -v "\`$EM\`" | grep -v "Covers:.*$EM"
echo "scanned: $(git ls-files | wc -l | tr -d ' ') files"
```

**Expected:** no matches, and a scanned count matching the tracked files.

The character is built with `printf` rather than typed. Written literally, the sweep
matches its own command line and reports this file forever.

`writing-guidelines` calls for a spaced hyphen instead, because the em dash now reads as
a machine's default punctuation. This sweep is the only thing that keeps that from
decaying, since a single one slips back in unnoticed.

The two exclusions are not punctuation. `—` is the literal value of a page's `Covers`
field, meaning the page describes no particular paths, and `check-knowledge` reads it to
decide whether to skip that page. Converting those would break the skill, which is why
the rule excludes them by form rather than by file.

Two traps when converting in bulk, both hit on the first pass here:

- A backtick span is not a safe protection pattern. Text sitting between two adjacent
  inline code spans looks like one, so prose dashes get protected by accident. Match the
  data values exactly.
- `MAINTENANCE.md` greps for a literal string that lives in `knowledge/CLAUDE.md`. A
  conversion that touches one side and not the other silently breaks rule 3. Both sides
  moved together here; check that pair after any bulk edit.

Scoped to `git ls-files`, so the live knowledge base is not swept. Its `INDEX.md` is a
real file rather than a symlink, and was converted in the same change to keep the trap
below quiet.

## Rule 13 - test a trigger change at its boundaries

**Manual: no command covers this.** Belongs with rules 5 and 6; it sits here only so
adding it renumbered nothing else.

Changing a skill's `description`, or the conditions in its `When to run`, changes which
tasks reach it. Run four cases before considering the change done:

1. A direct request that must select the skill.
2. A neighbouring request that could plausibly select an adjacent skill instead.
3. A request that must not select it at all.
4. A full run proving the intended workflow actually happened.

The fourth is the one that catches real failures. Selection is not the success
condition. A skill can be chosen and still not change what gets produced, and more
importantly the reverse: the work completes, looks correct, and the skill that governs it
was never invoked. That is the fourth failure shape above, and this rule is the only
thing that looks for it.

Widening a description is the case most in need of case 3. A description broadened until
it matches everything competes with every other skill and wins nothing.

## Rule 14 - stop condition

Stop when every command above matches its documented output and rules 5, 6, and 13 find
nothing. Reopen on the next skill edit - that's when the asymmetry gets created.

---

## Two traps specific to this setup

**`INDEX.md` is part template, part data.** The copy in this repo is an empty template.
The live one at `~/.claude/knowledge/INDEX.md` is a real file, not a symlink, because it
holds accumulated KB state. Edits to its *convention text* go in both; edits to its
*content* go only in the live one.

```bash
diff ~/.claude/knowledge/INDEX.md knowledge/INDEX.md
```

**Expected:** no output, until the live KB accumulates page rows and status dates - after
which only those should differ.

**Live KB content must never be symlinked into this repo.** Skills, the status line, the
KB conventions, and the deck are symlinked here. `INDEX.md`, `learnings.md`,
`gotchas.md`, `active-context.md`, and everything under `pages/`, `experiences/`, and
`raw/` are deliberately not - they accumulate real notes about real work, and this repo
is public. `.gitignore` carries the matching rules, commented out; uncomment them in the
same change if that ever changes.

```bash
find ~/.claude/knowledge -maxdepth 2 -type l
```

**Expected:** exactly three - `CLAUDE.md`, `presentation`, and `raw/README.md`. A symlink
appearing for any content file is a leak waiting to happen.
