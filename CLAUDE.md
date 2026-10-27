# Global Claude Code Instructions

This file names skills and how to invoke them. Trigger conditions live inside the
skills - in a When to run section, or in the description where the condition is a
single clause. Don't restate them here. The two guideline skills and the rebuttal
route below are exceptions. This file sets when they run, and their descriptions
do not narrow those rules.

## Doing the work

- Invoke the behavioral-guidelines skill with the Skill tool at the start of every task
  that edits files, runs commands, or does research, review, or analysis. Invoke it even
  if its description does not list the task. Skip it only for pure conversation -
  a turn with no task behind it (a preference, a fact, small talk) never needs a skill
  call. Task size and effort level are not reasons to skip it.

## Writing

- Invoke the writing-guidelines skill with the Skill tool before drafting any prose a
  person will read, in any language. If a person will read it, the rules apply. Invoke
  it before drafting, not after. A short answer is not a reason to skip it, but a turn
  with no drafted text in it is - a preference, a fact, small talk: just answer. Apply
  ASD-STE100 Simplified Technical English
  principles: one word, one meaning, active voice, simple tenses, short sentences
  (20 words for instructions, 25 for descriptions), one instruction per sentence,
  consistent terminology. Use the mode the skill sets for each text type.
- Commit messages carry no Co-Authored-By line and no mention of Claude or Anthropic.

## Guidance routing

The rebuttal route below is an additional host-level routing exception for
argue-from-sources. Other argument triggers stay with the skill.

For the behavioral-guidelines exception, pure conversation means a turn with
no task behind it, including preferences, facts, greetings, acknowledgments,
thanks, and casual social chat.
A requested calculation, analysis, evaluation, review, or rebuttal is a task,
even when it is short or written conversationally. Do not classify it as pure
conversation because it can be answered directly or in one paragraph.

When the user asks to rebut or refute a claim:
1. Invoke behavioral-guidelines with the Skill tool before analyzing the claim.
2. After behavioral-guidelines is loaded, invoke argue-from-sources.
3. Invoke writing-guidelines before drafting the answer. It may be loaded before
   step 2 when the behavioral guidance requests it.
Reuse skills already loaded in the current context; do not invent extra calls.
This route applies even to a short numerical rebuttal with no named opponent.

For a standalone calculation, invoke behavioral-guidelines under the current
Claude task rule. A request for only a number still requires only that number
as the answer; it does not authorize extra prose.
For pure conversation, do not invoke behavioral-guidelines or argue-from-sources.
Keep the existing writing-guidelines rule for prose. This block does not grant
new tools, authorize writes or messages, or alter higher-priority instructions.

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

## Mailbox

- Inter-Claude mail: new mail from the other lane surfaces at session start (lines like `#N [work] ...` from `claude-mail check`). Read the named threads (`~/.claude/scripts/claude-mail read N`) before acting, reply on the same thread (`claude-mail send --thread N ...`), open topics with `claude-mail new`. Repo and conventions: https://github.com/andreiGl/claude-mailbox (README + ACTORS.md). This mailbox replaces UpNote notes between lanes; UpNote stays for Andrei-facing drafts.

## Knowledge base

A cross-project knowledge base lives at ~/.claude/knowledge/, with conventions in
~/.claude/knowledge/CLAUDE.md.

Five skills maintain it, each stating its own trigger in a When to run section:
load-knowledge, update-knowledge, check-knowledge, synthesize-knowledge,
build-knowledge. Invoke them with the Skill tool.
