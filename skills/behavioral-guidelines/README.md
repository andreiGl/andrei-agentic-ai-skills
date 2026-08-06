# Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes when writing, reviewing, or refactoring code.

## What it does

Referenced by the global `CLAUDE.md`, so it applies on every coding task without being
invoked. Provides a set of principles Claude follows:

1. **Think before coding** — surface assumptions, push back when warranted, ask rather than guess
2. **Simplicity first** — minimum code that solves the problem, no speculative features or abstractions
3. **Surgical changes** — touch only what the task requires, match existing style
4. **Goal-driven execution** — define verifiable success criteria before starting
5. **Read before you write** — understand existing usage and utilities before adding code
6. **Checkpoint after every significant step** — summarize what was done, verified, and what's next
7. **Fail loud** — surface uncertainty explicitly; never silently skip or assume away
8. **Write for a human reader** — plain language in comments, docs, and PR text; no invented terms; clarity outranks brevity

## Tradeoff

These guidelines bias toward caution over speed. For trivial tasks, use judgment.
