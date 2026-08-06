---
name: synthesize-knowledge
description: Find recurring patterns across past sessions in the personal knowledge base and distill them into pattern-level knowledge, then trim the raw logs. Use when experience entries have accumulated, or when the same module, bug class, or failure mode keeps reappearing in learnings.
---

# Synthesize Knowledge — Pattern Extraction

Individual session notes record what happened. Patterns record what keeps happening,
which is the more useful thing and the part nobody notices without looking across
sessions deliberately.

## When to run

- `~/.claude/knowledge/experiences/` has 5 or more entries, **or**
- `learnings.md` shows the same area, bug class, or failure mode in 3+ entries, **or**
- You realize mid-session that you've solved this exact problem before

---

## 1. Read the source material

- Everything in `~/.claude/knowledge/experiences/`
- `~/.claude/knowledge/learnings.md`
- `~/.claude/knowledge/active-context.md`

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

Use the standard page header from `~/.claude/knowledge/CLAUDE.md`, with
`Project: shared` and `Tags: patterns, recurring, systemic`. One entry per pattern.

`load-knowledge` already loads this file whenever it exists — no wiring needed.

## 5. Add a row to `INDEX.md`

Once the page exists, if it isn't listed already.

## 6. Trim the source material

- Move distilled experience entries into
  `experiences/YYYY-MM-DD-distillation.md`, headed
  `# Distilled YYYY-MM-DD — promoted to patterns.md`
- Trim `learnings.md` to its 10 most recent entries, archiving the rest to the same
  distillation file

Archive, don't delete. A pattern that turns out to be wrong needs its evidence.

## 7. Append to `learnings.md`

```markdown
## YYYY-MM-DD — synthesis run
**What worked:** N patterns identified from M sessions
**Rule extracted:** (list the pattern names)
```
