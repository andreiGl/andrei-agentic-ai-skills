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

A cross-project knowledge base lives at ~/.claude/knowledge/, with conventions in
~/.claude/knowledge/CLAUDE.md.

Each skill owns its trigger and states it in its own description. Invoke them with the
Skill tool. The list below is the roster, not the conditions: load-knowledge,
update-knowledge, check-knowledge, synthesize-knowledge, build-knowledge.

Two preferences of mine that sit outside those triggers:

- Run load-knowledge without first checking whether the project has pages. That check is
  the skill's own first step and costs one line when there's nothing.
- Never bootstrap a knowledge base mid-task as a detour. build-knowledge runs when I ask
  for it.
