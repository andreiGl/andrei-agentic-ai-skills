# Global Claude Code Instructions

## Code

- Follow the generic behavioral guidelines defined in ~/.claude/skills/behavioral-guidelines/SKILL.md when writing, reviewing, or refactoring code in any project.
- When writing commit messages, do not include a Co-Authored-By line or any mention of Claude or Anthropic.

## Models

- Multi-agent tasks (review/analysis/research): sub-agents default to Sonnet; escalate verify/synthesis stages to Opus or high/xhigh effort.
- If the session is running on Sonnet and the task is complex enough to warrant Opus, say so and suggest `/model opus` before proceeding.

## Knowledge base

A cross-project knowledge base lives at ~/.claude/knowledge/, with conventions in ~/.claude/knowledge/CLAUDE.md. Each skill below states its own trigger conditions — follow those rather than a copy kept here.

- Run load-knowledge at the start of any substantial task. Don't check first whether the project has pages; that check is the skill's own first step, and it costs one line when there's nothing.
- Run update-knowledge after finishing a substantial task.
- Run check-knowledge before a large task, or when INDEX.md shows pages haven't been verified in over two weeks.
- Run synthesize-knowledge when its "When to run" thresholds are met.
- Use build-knowledge only when asked to create or extend a knowledge base. Don't bootstrap one mid-task as a detour.
