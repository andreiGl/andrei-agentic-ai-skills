---
name: synthesize-knowledge
description: Find recurring patterns across past sessions in the personal knowledge base and distill them into pattern-level knowledge, then archive the raw logs. Use when asked to synthesize the knowledge base, extract recurring patterns, or distill experience entries, or when accumulated experiences and learnings are due for a synthesis pass. The "When to run" section states the thresholds.
---

# Synthesize Knowledge — Pattern Extraction

Individual session notes record what happened. Patterns record what keeps happening,
which is the more useful thing and the part nobody notices without looking across
sessions deliberately.

## When to run

This section is the single source for these thresholds. The other skills and
`knowledge/CLAUDE.md` point here rather than restating them.

Run when any of these holds:

- `~/.claude/knowledge/experiences/` has **5 or more entries** — counting files
  directly in that directory, not the ones already moved to `experiences/archive/`
- `learnings.md` shows the same area, bug class, or failure mode in **3+ entries**
- `learnings.md` has grown past **20 entries**, whether or not a pattern is visible —
  at that length it stops being scannable, which is its only job
- You realize mid-session that you've solved this exact problem before

The archive directory is what makes the first trigger resettable: distilling moves
entries out of the count, so a run actually clears the condition it fired on.

---

## 1. Read the source material

- Every entry directly in `~/.claude/knowledge/experiences/` (skip `archive/` unless
  you're checking whether a pattern was already named)
- `~/.claude/knowledge/learnings.md`
- `~/.claude/knowledge/active-context.md`
- `~/.claude/knowledge/pages/shared/patterns.md`, if it exists — a recurrence may
  belong to a pattern that's already named, in which case bump its **Frequency**
  rather than adding a near-duplicate

## 2. Look for repetition

- The same area touched across many sessions → a fragile area
- The same class of bug more than once → a systemic gap, not bad luck
- The same review feedback repeatedly → a convention that never got written down
- The same CI or test failure recurring → a missing check

Three occurrences is the threshold. Two is a coincidence, and naming it as a pattern
gives it more weight than it has earned.

## 3. Name each pattern

```markdown
## Pattern: <Name>

**Frequency:** N occurrences across sessions
**Area:** module or subsystem
**Instances:** ticket or PR references

**What happens:** the symptom, in one sentence
**Why it keeps happening:** the underlying cause — a gap in the code, a missing
  convention, a misleading API
**Preventive rule:** the check or habit that catches it before it becomes a problem
**Related pages:** [[page1]], [[page2]]
```

The preventive rule is the point of the entry. A pattern without one is an
observation, and observations don't change what happens next time.

## 4. Write `pages/shared/patterns.md`

Create `~/.claude/knowledge/pages/shared/` if it doesn't exist yet. Use the standard
page header from `~/.claude/knowledge/CLAUDE.md`, with `Project: shared`,
`Tags: patterns, recurring, systemic`, and `Covers: —`. One entry per pattern.

`load-knowledge` reads this file whenever it exists — no wiring needed.

## 5. Update `INDEX.md`

- Add a row for `patterns.md` if it isn't listed
- Set **Last synthesized** to today's date

The date is what this skill's first trigger reads. Skip it and the next session can't
tell whether synthesis has ever run.

## 6. Archive what you distilled

- Move distilled experience entries into `~/.claude/knowledge/experiences/archive/`,
  creating it if needed
- Trim `learnings.md` to its 10 most recent entries, appending the rest to
  `~/.claude/knowledge/experiences/archive/YYYY-MM-DD-distillation.md` under
  `# Distilled YYYY-MM-DD — promoted to patterns.md`

Archive, don't delete. A pattern that later turns out to be wrong needs its evidence.

## 7. Append to `learnings.md`

```markdown
## YYYY-MM-DD — synthesis run
**What worked:** N patterns identified from M sessions
**Rule extracted:** (list the pattern names)
```
