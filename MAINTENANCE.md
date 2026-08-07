# Maintaining These Skills

The skills form a system: one writes what another reads. Most defects found so far were
not in any single file but in the seams between them, and none of them threw an error —
they degraded silently and looked correct in review.

This is the procedure that catches them. It exists in the repo rather than in a note
somewhere because it is the maintenance procedure for the thing it is stored next to.

---

## The two failure shapes

**One fact, several files.** A rule written in two places drifts, because nothing forces
copies to agree. Every fact has exactly one owner; other files point at it.

| Fact | Owner |
| :--- | :--- |
| Layout, page header, Category A gate, link rules | `knowledge/CLAUDE.md` |
| Which files load at session start | `skills/load-knowledge/SKILL.md` |
| Distillation and trimming thresholds | `skills/synthesize-knowledge/SKILL.md` |
| Page routing data (Tags, Covers) | The page headers; `INDEX.md` is a derived cache |

**A reader with no writer.** For every path or field a skill reads, some skill must
write it. A reader whose writer was never updated fails silently — the symptom is
indistinguishable from "there was nothing to find."

This has two sub-forms, and only the first is greppable:

1. The writer never mentions the field at all.
2. The writer mentions it, but *after* the reader runs. Both halves present and
   correct; the sequence is wrong.

---

## The rules

1. **Edit the reader and the writer in the same change.** This is the one that actually
   prevents the problem. When a field is added to both in one pass it holds; when the
   writer is left for later, later doesn't come. If you can't do both, leave the
   half-done state visibly broken rather than silently degraded.
2. **Path targets are written in absolute form** — `~/.claude/knowledge/...` — so one
   sweep finds them all. Bare directory names used as prose referents ("files directly
   in `experiences/`") are fine; they aren't targets.
3. **Sweeps for duplicated definitions anchor on the syntax of defining**, not on the
   term. A skill that says "set `Status: stale`" is a consumer doing its job, not a
   restated definition.
4. **Test every new sweep against known-good data** and confirm it stays silent. A sweep
   that always fires gets ignored, which is worse than not having it — it reads as
   confirmation.
5. **After reordering steps, inserting one, or moving a file, read the step sequence
   straight through** and ask what each step assumes already exists. No sweep finds an
   unknown ordering bug; that needs the semantics of the steps.
6. **Stop when 1-4 are silent and 5 finds nothing.** Reopen on the next skill edit —
   that's when the asymmetry gets created.

---

## Sweeps

Run from the repo root.

```bash
# Every path a skill reads must exist or be created by some skill.
# patterns.md is expected: created on first synthesis, and its reader guards for it.
grep -rhoE '~/\.claude/knowledge/[A-Za-z0-9_./<>-]+' skills/*/SKILL.md \
  | sed 's#/$##' | sort -u | while read p; do
    case "$p" in *'<'*|*YYYY*) continue;; esac
    [ -e "${p/#\~/$HOME}" ] || echo "READ BUT ABSENT: $p"
  done

# Rule 2: relative path targets that the absolute sweep above cannot see.
# Two hits are expected and correct — a prose referent in synthesize-knowledge's
# trigger list, and a section heading naming its output file. Anything else is a bug.
grep -rnoE '`(raw|pages|experiences)/[A-Za-z0-9_./<>-]*`' skills/*/SKILL.md

# Thresholds outside their owner.
grep -rn "20 entries\|5 or more entries\|5+ entries" skills/ knowledge/*.md CLAUDE.md \
  | grep -v "synthesize-knowledge/SKILL.md"

# A description that restates a threshold. description drives auto-invocation,
# so a stale copy there is the one being matched.
for s in skills/*/SKILL.md; do
  sed -n '3p' "$s" | grep -qE "5\+|5 or more|20 entries|3\+ entries" && echo "BUG $s"
done

# Definitions restated outside their owner.
grep -rln "3 tool calls" skills/ knowledge/*.md     # Category A gate
grep -rln '`stale` —' skills/ knowledge/            # Status values

# Dangling wikilinks. Template placeholders in prose will show; read the list.
pages=$(find knowledge -name '*.md' | sed 's#.*/##;s#\.md$##' | sort -u)
for t in $(grep -rhoE '\[\[[a-z0-9-]+\]\]' knowledge/ | sort -u | tr -d '[]'); do
  echo "$pages" | grep -qx "$t" || echo "DANGLING [[$t]]"
done

# One-way links between topic pages. Hub pages are exempt by design.
for f in $(find knowledge -name '*.md' ! -name 'INDEX.md'); do
  me=$(basename "$f" .md)
  case "$me" in gotchas|active-context|learnings|patterns|CLAUDE|README) continue;; esac
  for t in $(grep -ohE '\[\[[a-z0-9-]+\]\]' "$f" | sort -u | tr -d '[]'); do
    tf=$(find knowledge -name "$t.md" | head -1); [ -z "$tf" ] && continue
    grep -q "\[\[$me\]\]" "$tf" || echo "ONE-WAY $me -> $t"
  done
done

# Skills must sit one level deep or they are never registered.
# -L matters: the live directories are symlinks into this repo.
find -L ~/.claude/skills -name SKILL.md | sed "s#$HOME/.claude/skills/##" \
  | awk -F/ 'NF>2{print "UNREGISTERED: "$0}'

# Relative links in docs.
for f in $(find skills knowledge -name '*.md'); do d=$(dirname "$f")
  grep -oE '\]\([^)h#][^)]*\)' "$f" | sed 's/](\(.*\))/\1/' | while read l; do
    [ -e "$d/${l%%#*}" ] || echo "BROKEN $f -> $l"
  done
done
```

---

## Two traps specific to this setup

**`INDEX.md` is part template, part data.** The copy in this repo is an empty template.
The live one at `~/.claude/knowledge/INDEX.md` is a real file, not a symlink, because it
holds accumulated KB state. Edits to its *convention text* have to be applied in both
places; edits to its *content* belong only in the live one. Diff them after touching
either.

**Live KB content must never be symlinked into this repo.** Skills, the status line, the
KB conventions, and the deck are symlinked here. `INDEX.md`, `learnings.md`,
`gotchas.md`, `active-context.md`, and everything under `pages/`, `experiences/`, and
`raw/` are deliberately not — they accumulate real notes about real work, and this repo
is public. `.gitignore` carries the matching rules, commented out; uncomment them in the
same change if that arrangement ever changes.
