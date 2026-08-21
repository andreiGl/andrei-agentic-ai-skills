# Global Claude Code Instructions

## Doing the work

- Follow ~/.claude/skills/behavioral-guidelines/SKILL.md on any task where being confidently wrong is the main risk: writing, reviewing, or refactoring code, and equally research, analysis, comparison, or fact-checking. Invoke it with the Skill tool. A path reference on its own leaves the rules out of context, which is how it went unread before.
- When writing commit messages, do not include a Co-Authored-By line or any mention of Claude or Anthropic.

## Writing

- Follow ~/.claude/skills/writing-guidelines/SKILL.md for every piece of prose produced for a human reader, in any language: code comments, READMEs, docs, commit messages, PR and issue text, reports, analyses, plans, emails, forum and social posts, and chat replies. Those are examples. If a person will read it, the rules apply.
- Invoke it before drafting anything longer than a couple of paragraphs, not after. Stripping the tells out afterwards costs more than writing without them.

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
