# Global Claude Code Instructions

This file names skills and how to invoke them. Trigger conditions live inside the
skills — in a When to run section, or in the description where the condition is a
single clause. Don't restate them here.

## Doing the work

- Invoke the behavioral-guidelines skill with the Skill tool before starting work of any
  substance. Its description states where it applies. A path reference on its own leaves
  the rules out of context.

## Writing

- Invoke the writing-guidelines skill with the Skill tool before drafting any prose a
  person will read, in any language. If a person will read it, the rules apply. Invoke
  it before drafting, not after.
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

Five skills maintain it, each stating its own trigger in a When to run section:
load-knowledge, update-knowledge, check-knowledge, synthesize-knowledge,
build-knowledge. Invoke them with the Skill tool.
