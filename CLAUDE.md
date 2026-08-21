# Global Claude Code Instructions

## Doing the work

- Invoke the behavioral-guidelines skill with the Skill tool on any task where being
  confidently wrong is the main risk: writing, reviewing, or refactoring code, and
  equally research, analysis, comparison, or fact-checking. A path reference on its own
  leaves the rules out of context.

## Writing

- Invoke the writing-guidelines skill with the Skill tool before drafting any prose a
  person will read, in any language — code comments, docs, commit messages, PR and issue
  text, reports, emails, forum posts, chat replies. Those are examples. If a person will
  read it, the rules apply. Invoke it before drafting, not after.
- Commit messages carry no Co-Authored-By line and no mention of Claude or Anthropic.

## Git

- Commit and push only when I ask.
- These repositories work directly on the default branch. Don't create a branch unless
  I ask for one.

## Models

- Multi-agent tasks (review, analysis, research): sub-agents default to Sonnet; escalate
  verify and synthesis stages to Opus, or to high/xhigh effort.
- If the session runs on Sonnet and the task warrants Opus, say so before proceeding. In
  a terminal session that is `/model opus`; elsewhere just say so, since that command
  isn't available in every client.

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
