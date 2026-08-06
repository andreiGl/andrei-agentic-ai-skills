---
name: behavioral-guidelines
description: Generic, language- and project-agnostic behavioral guidelines to reduce common LLM coding mistakes. Use when writing, reviewing, or refactoring code in any project to avoid overcomplication, make surgical changes, surface assumptions, define verifiable success criteria, and write comments, docs, and PR text in plain language a human can read.
---

# Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

## 5. Read Before You Write

**Before adding code, read exports, immediate callers, shared utilities.**

- Understand how the thing you're about to change is already used.
- Check for existing utilities that do what you're about to implement.
- If you're unsure why code is structured a certain way, ask - don't guess and overwrite.

## 6. Checkpoint After Every Significant Step

**Summarize what was done, what's verified, what's left.**

After each meaningful step, restate:
- What changed and how it was verified.
- What assumptions are still in play.
- What's next.

Don't continue from a state you can't describe clearly. Stop and restate.

## 7. Fail Loud

**Surface uncertainty. Never silently skip.**

- "Completed" is wrong if anything was skipped or assumed away.
- "Tests pass" is wrong if any were skipped, excluded, or not run.
- If something couldn't be verified, say so explicitly.
- Default to surfacing uncertainty, not hiding it.

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 8. Write for a Human Reader

**Code comments, docstrings/Javadoc, commit messages, PR and Jira text, plans, reports,
and chat replies should all read as if one person wrote them for another to read.**

- Plain language. If a common word says the same thing, use the common word, and use no
  jargon beyond what any engineer would already know.
- No invented terms. Don't coin a phrase to compress an idea - state the idea. If a
  domain term is genuinely unavoidable, say what it refers to in the same sentence.
- Clarity outranks brevity. Where another rule says be terse, it means cut what the
  reader doesn't need - never make what remains harder to follow. Don't compress until
  it turns cryptic; don't pad to sound thorough.

Usually padding, so reach for the plain word first: leverage, orthogonal, holistic,
non-trivial. Ban outright: any noun phrase you just coined.

```
Bad:  // Guards the freshness envelope against stale-read contract violations.
Good: // Rejects the entry if it was read before the last write, returning stale data.
```

Applies to text you write or change - not a license to rewrite comments you're only
reading past (see section 3).

Test: would a colleague understand this on first read, without asking what a word means?

