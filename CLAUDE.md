# Global Claude Code Instructions

## Code

- Follow the generic behavioral guidelines defined in ~/.claude/skills/behavioral-guidelines/SKILL.md when writing, reviewing, or refactoring code in any project.
- When writing commit messages, do not include a Co-Authored-By line or any mention of Claude or Anthropic.

## Models

- Multi-agent tasks (review/analysis/research): sub-agents default to Sonnet; escalate verify/synthesis stages to Opus or high/xhigh effort.
- If the session is running on Sonnet and the task is complex enough to warrant Opus, say so and suggest `/model opus` before proceeding.

## Knowledge base

A cross-project knowledge base lives at ~/.claude/knowledge/, with conventions in ~/.claude/knowledge/CLAUDE.md. It applies to any project that has pages under ~/.claude/knowledge/pages/.

- Before starting a substantial task in a project that has knowledge pages, run the load-knowledge skill.
- After finishing a task that produced a surprise, a correction, or a rule worth keeping, run update-knowledge.
- Before a large task, or when more than 2 weeks have passed since pages were last verified, run check-knowledge.
- When ~/.claude/knowledge/experiences/ has 5+ entries, or ~/.claude/knowledge/learnings.md shows the same theme repeating, run synthesize-knowledge.
- Use build-knowledge only when asked to create or extend a knowledge base. Don't bootstrap one mid-task as a detour.
