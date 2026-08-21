# Maintaining These Skills

The skills form a system: one writes what another reads. Most defects found so far were
not in any single file but in the seams between them, and none of them threw an error —
they degraded silently and looked correct in review.

This file is the procedure that catches them. It lives in the repo because it is the
maintenance procedure for the thing it sits next to.

**Every rule below carries its command and that command's expected output.** A rule
written as prose is not a check — it passes review, reads as coverage, and never runs.
Where a rule genuinely can't be a command it says so explicitly, so it's visibly a manual
step rather than something a sweep is assumed to cover.

Run everything from the repo root.

---

## The three failure shapes

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

---

## Rule 1 — every path a skill reads, some skill writes

```bash
grep -rhoE '~/\.claude/knowledge/[A-Za-z0-9_./<>-]+' skills/*/SKILL.md \
  | sed 's#/$##' | sort -u | while read p; do
    case "$p" in *'<'*|*YYYY*) continue;; esac
    [ -e "${p/#\~/$HOME}" ] || echo "READ BUT ABSENT: $p"
  done
```

**Expected:** exactly one line, `~/.claude/knowledge/pages/shared/patterns.md`. It's
created on first synthesis and its reader guards for absence. Anything else is a bug.

## Rule 2 — path targets absolute, prose referents may stay relative

Absolute form means one sweep finds them all. Bare directory names used as prose
("files directly in `experiences/`") aren't targets and shouldn't be normalized.

```bash
grep -rnoE '`(raw|pages|experiences)/[A-Za-z0-9_./<>-]*`' skills/*/SKILL.md
```

**Expected:** exactly two lines — a prose referent in `synthesize-knowledge`'s trigger
list, and a section heading naming its own output file. Anything else is a target that
needs absolutising.

## Rule 3 — sweeps for duplicated definitions anchor on defining syntax

Not on the term. A skill that says "set `Status: stale`" is a consumer doing its job.

```bash
grep -rln "3 tool calls" skills/ knowledge/*.md      # Category A gate
grep -rln '`stale` —' skills/ knowledge/             # Status values
grep -rn "20 entries\|5 or more entries\|5+ entries" skills/ knowledge/*.md CLAUDE.md \
  | grep -v "synthesize-knowledge/SKILL.md"          # thresholds
for s in skills/*/SKILL.md; do                       # descriptions
  sed -n '3p' "$s" | grep -qE "5\+|5 or more|20 entries|3\+ entries" && echo "BUG $s"
done
```

**Expected:** first two print `knowledge/CLAUDE.md` and nothing else. Last two print
nothing. `description:` drives auto-invocation, so a stale threshold there is the copy
being matched.

## Rule 4 — any sweep with a non-empty expected set carries that set inline

Otherwise it decays into noise and gets ignored, which is worse than not having it —
it reads as confirmation. Rules 1 and 2 above are the two with expected output; both
state it.

Scope sweeps to tracked files. An unscoped walk picks up `plugins/` and marketplace
caches, whose broken links are not ours to fix.

## Rule 5 — edit reader and writer in the same change

**Manual: no command covers this.**

When a field is added to both in one pass it holds; when the writer is left for later,
later doesn't come. If you can't do both, leave the half-done state visibly broken rather
than silently degraded.

This applies *within* a file too. A preamble and a numbered step are a reader/writer
pair. So are a step and a cross-reference to it. Both copies of these skills
independently produced the same two intra-file defects in `build-knowledge`.

## Rule 6 — after reordering or moving anything, read the step sequence

**Manual: no command covers this.** "Does step N depend on step M > N" needs the
semantics of the steps.

Read the numbered sequence straight through and ask what each step assumes already
exists. Run it after inserting a step, reordering steps, or moving a file.

Known-good baseline: `synthesize-knowledge` appends to `learnings.md` *after* trimming
it — reverse that and the trim eats the synthesis entry. `check-knowledge` guards for a
repository before using one. `build-knowledge` creates the conventions file before step 4
reads it.

## Rule 7 — links resolve, across every tracked file

Scoped to `git ls-files`, not `find`. An earlier version of this walked only `skills/`
and `knowledge/`, silently omitting `README.md`, `CLAUDE.md`, and this file — the three
most-read files in the repo, unchecked. The parallel copy had the same gap and it hid
five links broken by the round-1 flatten.

```bash
git ls-files '*.md' | while read f; do d=$(dirname "$f")
  grep -oE '\]\([^)h#][^)]*\)' "$f" | sed 's/](\(.*\))/\1/' | while read l; do
    [ -e "$d/${l%%#*}" ] || echo "BROKEN $f -> $l"
  done
done
```

**Expected:** no output.

## Rule 8 — skills sit one level deep, or they are never registered

```bash
find -L ~/.claude/skills -mindepth 3 -name SKILL.md
find -L ~/.claude/skills -name SKILL.md | wc -l
```

**Expected:** nothing from the first; `6` from the second (one per directory in
`skills/`).

`-L` is load-bearing: the live skill directories are symlinks into this repo, and `find`
won't follow them without it. Without `-L` the first command reports no nested skills —
while the second reports zero skills at all, which is the only signal it's broken rather
than clean. Check the count, not just the silence.

## Rule 9 — KB link graph

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

**Expected:** the dangling check prints the template placeholders used in prose
(`[[page-name]]`, `[[other-page]]`, `[[another-page]]`, `[[links]]`, `[[page-link]]`) and
nothing else. The one-way check prints nothing — hub pages are exempt by design and are
skipped above.

## Rule 10 — repository integrity

```bash
git fsck --no-progress
find .git -name 'Icon?' | wc -l
```

**Expected:** no output from the first; `0` from the second.

macOS Finder creates a file named `Icon` followed by a carriage return in every
directory of a folder carrying a custom icon — including inside `.git`. Git treats every
file under `refs/` as a ref, so `refs/Icon\r` becomes a ref pointing at the null SHA and
**`git fetch` fails outright** with `bad object refs/Icon?`. The same files under
`objects/` make `fsck` report `bad sha1 file` for each one.

The `Icon?` line in `.gitignore` cannot help here: `.gitignore` governs what gets
committed, not what exists inside `.git`. This is a class of breakage no content sweep
reaches, which is why it gets its own rule.

Clean up with:

```bash
find . -name 'Icon?' -type f -delete
```

It recurs while the directory carries the `com.apple.FinderInfo` attribute. Check with
`xattr <dir>`; clear it with `xattr -d com.apple.FinderInfo <dir>`, which also removes
the folder's custom icon.

## Rule 11 — stop condition

Stop when every command above matches its documented output and rules 5 and 6 find
nothing. Reopen on the next skill edit — that's when the asymmetry gets created.

---

## Two traps specific to this setup

**`INDEX.md` is part template, part data.** The copy in this repo is an empty template.
The live one at `~/.claude/knowledge/INDEX.md` is a real file, not a symlink, because it
holds accumulated KB state. Edits to its *convention text* go in both; edits to its
*content* go only in the live one.

```bash
diff ~/.claude/knowledge/INDEX.md knowledge/INDEX.md
```

**Expected:** no output, until the live KB accumulates page rows and status dates — after
which only those should differ.

**Live KB content must never be symlinked into this repo.** Skills, the status line, the
KB conventions, and the deck are symlinked here. `INDEX.md`, `learnings.md`,
`gotchas.md`, `active-context.md`, and everything under `pages/`, `experiences/`, and
`raw/` are deliberately not — they accumulate real notes about real work, and this repo
is public. `.gitignore` carries the matching rules, commented out; uncomment them in the
same change if that ever changes.

```bash
find ~/.claude/knowledge -maxdepth 2 -type l
```

**Expected:** exactly three — `CLAUDE.md`, `presentation`, and `raw/README.md`. A symlink
appearing for any content file is a leak waiting to happen.
