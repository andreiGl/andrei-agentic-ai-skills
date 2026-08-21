# Andrei's Agentic AI Skills

> [!NOTE]
> Shared as-is. These work for me but haven't been tested much beyond my own setup,
> so your mileage may vary.

Claude Code skills - a persistent cross-project knowledge base, guidelines for how work
gets carried out, and guidelines for how the result reads - plus a custom status line.

## Contents

- [Installation](#installation)
  - [Copy](#copy)
  - [Symlink (what I run)](#symlink-what-i-run)
  - [What deliberately stays out of the symlinks](#what-deliberately-stays-out-of-the-symlinks)
- [Skills](#skills)
  - [Working and writing](#working-and-writing)
  - [Knowledge base](#knowledge-base)
  - [Where triggers live](#where-triggers-live)
- [How the knowledge base works](#how-the-knowledge-base-works)
- [Status line](#status-line)
- [Skill invocation log](#skill-invocation-log)
- [Experience entry check](#experience-entry-check)
- [License](#license)

## Installation

Clone it wherever you keep repositories - `~/myProjects` below is a placeholder,
substitute your own:

```bash
git clone https://github.com/andreiGl/andrei-agentic-ai-skills.git ~/myProjects/andrei-agentic-ai-skills
```

Then either copy the pieces into `~/.claude/`, or symlink them so this repo stays the
source of truth. Claude Code follows symlinks, and skills registered through one behave
identically.

### Copy

```bash
REPO=~/myProjects/andrei-agentic-ai-skills
cp -R "$REPO"/skills/* ~/.claude/skills/
cp -R "$REPO"/knowledge ~/.claude/knowledge
```

Simple, but edits made while working don't flow back - you have to remember to copy
them across, and in practice you won't.

### Symlink (what I run)

```bash
REPO=~/myProjects/andrei-agentic-ai-skills
for s in "$REPO"/skills/*/; do ln -sfn "$s" ~/.claude/skills/"$(basename "$s")"; done
ln -sfn "$REPO"/statusline-command.sh ~/.claude/statusline-command.sh
ln -sfn "$REPO"/skill-invocation-log.sh ~/.claude/skill-invocation-log.sh
ln -sfn "$REPO"/kb-session-end.sh ~/.claude/kb-session-end.sh
ln -sfn "$REPO"/kb-session-start.sh ~/.claude/kb-session-start.sh
ln -sfn "$REPO"/knowledge/CLAUDE.md ~/.claude/knowledge/CLAUDE.md
ln -sfn "$REPO"/knowledge/raw/README.md ~/.claude/knowledge/raw/README.md
ln -sfn "$REPO"/knowledge/presentation ~/.claude/knowledge/presentation
```

Editing a skill now edits the repo, and `git status` shows the change.

Claude Code discovers skills at `~/.claude/skills/<name>/SKILL.md`, one level deep.
Nesting them in subdirectories stops them being registered.

### What deliberately stays out of the symlinks

`INDEX.md`, `learnings.md`, `gotchas.md`, `active-context.md`, and the contents of
`pages/`, `experiences/`, and `raw/` stay as real files in `~/.claude/knowledge/`.

Those accumulate real notes about real work. Symlinking them would put every recorded
learning straight into this repo's working tree, one `git add -A` away from being
published. The copies here are empty templates for a fresh install - they're meant to
diverge from a live knowledge base, which is why they aren't linked.

The same reasoning applies to [`CLAUDE.md`](CLAUDE.md) at the repo root: it's an example
of the wiring, not a symlink target, because global instructions tend to accumulate
project-specific and private rules over time.

The knowledge skills do nothing until the global `CLAUDE.md` names them, so Claude knows
they exist and reaches for the Skill tool. When each one fires is stated inside the skill,
not there. See [`CLAUDE.md`](CLAUDE.md) in this repo for the wiring I use - copy the
`## Knowledge base` section into your own `~/.claude/CLAUDE.md`.

Editing these? Read [MAINTENANCE.md](MAINTENANCE.md) first. The skills read what each
other write, and the defects that matter live in those seams - they degrade silently
rather than erroring.

## Skills

### Working and writing

| Skill | Description |
| :--- | :--- |
| [`behavioral-guidelines`](skills/behavioral-guidelines) | How to carry out a task: surface assumptions, keep it simple, make surgical changes, define checkable success criteria, ground every claim in a source actually opened |
| [`writing-guidelines`](skills/writing-guidelines) | How the result reads: plain language, no invented terms, register matched to the venue, none of the sentence shapes that mark text as machine-written |

These were one file until its description, which named code in every clause, stopped
matching a long piece of research and argument that had no code in it. Split so each half
carries a description for its own kind of work; they compose, and each points at the other.

The writing half applies to any prose, in any language, whether or not code is involved -
comments and commit messages, and equally reports, emails, and forum posts.

### Knowledge base

Five skills that maintain a knowledge base carrying context across sessions.

| Skill | What it does |
| :--- | :--- |
| [`load-knowledge`](skills/load-knowledge) | Reads the KB into context before work starts |
| [`update-knowledge`](skills/update-knowledge) | Writes back whatever the session produced |
| [`build-knowledge`](skills/build-knowledge) | Creates a KB, or adds a project to one |
| [`check-knowledge`](skills/check-knowledge) | Verifies pages against the code they describe |
| [`synthesize-knowledge`](skills/synthesize-knowledge) | Distills repeated experience into patterns |

Each skill's `## When to run` section states when it fires. This table stays out of that
on purpose - see below.

### Where triggers live

Every skill owns its trigger, and nothing outside it restates the condition. `CLAUDE.md`
names the skills and how to invoke them, and carries no conditions at all.

Where inside the skill depends on the shape of the condition. The five knowledge skills
each have a list of them - counts, dates, whether you asked - so each carries a
`## When to run` section near the top of its `SKILL.md`. The two guideline skills answer
"always", which fits in the description and needs no section. A heading that says
"always" carries nothing and becomes a third copy to keep in sync.

This started as a bug worth recording. `CLAUDE.md` claimed each skill stated its own
trigger and then restated all five, and the copies had already drifted: it told
`update-knowledge` to run after any substantial task, while that skill's description
said to run only when the task produced something memorable. The skill's own body said
the first - the experience entry is unconditional, and `synthesize-knowledge` needs quiet
sessions to produce one - so the description was the copy that was wrong, and the obvious
fix of deferring to it would have starved the synthesis input.

`MAINTENANCE.md` Rule 3 sweeps for restated thresholds, this file included. It was added
to that sweep after this table was found holding two of them.

## How the knowledge base works

Context windows reset between sessions. Some facts aren't recoverable from the code at
all - how an external system actually behaves, why one approach was chosen over
another, which failure mode already burned you twice. The knowledge base is where
those go.

```
knowledge/
├── CLAUDE.md           - conventions and structure (the single source for them)
├── INDEX.md            - every page, with project, tags, and covered paths
├── learnings.md        - chronological journal across projects
├── gotchas.md          - one-line sharp facts
├── active-context.md   - open work and areas in flux
├── pages/<project>/    - curated pages, one directory per repo
├── experiences/        - per-session notes
└── raw/                - source material before extraction
```

The gate that keeps it useful:

> "Can this fact be derived from reading the code in under 3 tool calls?"

If yes, it doesn't become a page. A knowledge base that restates the codebase goes
stale silently and stops being read - the discipline is discarding most of what you
gather.

Two header fields drive everything. `Tags` decides what `load-knowledge` pulls in for
a given task; `Covers` (repo-relative path globs) lets `check-knowledge` map recent
commits onto the pages that claim to describe them. A page with neither will never
surface and never be verified.

There's a [presentation deck](knowledge/presentation/knowledge-base-deck.html)
walking through the system - clone and open it in a browser.

## Skill invocation log

[`skill-invocation-log.sh`](skill-invocation-log.sh) is a `Stop` hook that records, once
per turn, whether the guidance skills were invoked in that session:

```
2026-08-21T18:50:46Z 64654c2f wg=yes bg=yes skills=5 writes=0 sh=131 self=yes
```

Session, whether the writing and work guidance skills were invoked, how many skill
invocations in total, how many `Write`/`Edit` calls, how many shell commands that look
like they changed a file, and whether the session edited this repository.

`sh` exists because `writes` alone is blind. A session driven through heredocs, `sed`, and
inline scripts logs `writes=0` while rewriting twenty five files, and the first version of
this hook recorded exactly that. The line above is real: zero `Write` calls, 131 shell
commands that touched files.

`self=yes` marks a session that **edited** this repository, not one that mentioned it. The
first version grepped the whole transcript for the repo name, which also caught sessions
that merely discussed it. Over-exclusion is the expensive direction: sample size is the
scarce resource, and the first four lines ever collected were worthless precisely because
all of them were `self=yes`. Those sessions invoke the guidance skills by construction, so
counting them as successes flatters the rate.

### How the rate is computed

Agreed with a second install of this hook so both sides measure the same thing. Written
down here because an agreement that lives only in a chat is not an agreement.

1. Group records by session id and keep the final one. The hook fires per turn while every
   column is session-cumulative, so counting lines weights by session length rather than by
   session.
2. Drop sessions where the relevant field reads `n/a`, and sessions where `writes + sh` is
   zero. `n/a` means the skill was never installed, so the session could not have invoked
   it; scoring that as `no` pads the rate with impossible cases.
3. Keep `self=yes` sessions in the source set. `self` is a hint, not an exclusion rule.
4. Classify each remaining session by hand as `meta` or `ordinary`, from what it was doing.
5. Report each non-invocation rate twice: over all eligible sessions, and over ordinary
   sessions only.
6. Report the distinct session count beside each rate.
7. Under ten sessions in a view, call that view insufficient data rather than a rate.

Steps 3 and 4 replace an earlier rule that excluded `self=yes` outright. That rule was
argued from inflation: sessions editing this repository invoke the guidance skills by
construction, so counting them as successes flatters the number. The argument only runs one
way. It drops meta-work that scored `yes` and silently keeps meta-work that scored `no`,
which makes the rate depend on which way the meta-work happened to fall. The parallel
install produced exactly that case: a session authoring and validating skills, including
running a validator against `behavioral-guidelines`, which never invoked it and recorded
`self=no` because it touched no path naming this repository.

Manual classification is affordable because the eligible set is small. If it stops being
small, that is a better problem than an exclusion rule with a bias in it.

First comparison window: 2026-08-21 through 2026-08-27 inclusive, local time on each side,
compared on the 28th. A session spanning midnight counts to the day its last line falls on.

```bash
sort -k2,2 -k1,1 ~/.claude/skill-invocation.log | awk '{a[$2]=$0} END{for(s in a) print a[s]}'
```

That prints the last record per session, which is the input to steps 2 through 4.

A third value, `n/a`, means the skill is not installed on this machine at all. `no` claims
the skill was available and went unused, which is the thing being measured; a missing skill
reported as `no` would pad the failure rate with sessions that never could have invoked it.

### If your skills are named differently

The watched names are variables at the top of the script, overridable from the environment:

```json
{ "env": { "SKILL_LOG_WRITING": "write-for-humans" } }
```

`SKILL_LOG_WRITING` defaults to `writing-guidelines`, `SKILL_LOG_WORK` to
`behavioral-guidelines`. The `wg` and `bg` column names stay fixed so two installs with
different skill names still produce comparable logs.

This exists because a second install of this script does call its prose skill
`write-for-humans`, and the first version hardcoded the greps.

It reports and nothing else. No blocking, no output, exit 0 on every path including a
malformed payload or a missing transcript. About 260ms per turn on a 3MB transcript, run
asynchronously.

### Why it exists

A skill whose description does not match the task never loads, nothing errors, and the
work completes looking correct. Nothing in this repository detects that, and nothing can:
every check here verifies that files agree with each other, which is a different question
from whether a skill was reachable.

The only such failure caught so far was caught because someone asked directly. That is
one incident, not a rate. This hook exists to produce the rate before deciding whether a
blocking control is worth its friction.

### Install

```bash
ln -sfn "$REPO"/skill-invocation-log.sh ~/.claude/skill-invocation-log.sh
```

Then in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh ~/.claude/skill-invocation-log.sh",
            "timeout": 10,
            "async": true
          }
        ]
      }
    ]
  }
}
```

Requires `jq`. Writes to `~/.claude/skill-invocation.log`, which is outside this
repository and stays there.

### What it proves, and what it does not

It proves the `Skill` tool was called. It does not prove the guidance shaped the output,
and no hook can. What it converts is silent non-invocation into a recorded fact, which is
the failure mode that actually occurred.

Two limits worth knowing. The check is per session, not per task, so one invocation early
in a long session satisfies it for everything after. And the transcript path it reads is
an implementation detail rather than a documented contract, so the script falls back to a
search and then exits quietly, which means a broken version of it is invisible.

## Experience entry check

`update-knowledge` writes an experience entry unconditionally, and that entry is what
`synthesize-knowledge` counts. It is also the one output that depends entirely on the
model choosing to invoke a skill. [`kb-session-end.sh`](kb-session-end.sh) and
[`kb-session-start.sh`](kb-session-start.sh) turn a missed entry into a recorded fact.

A `SessionEnd` hook cannot ask for the entry itself: its stdout reaches the debug log
only, and the session is over. So the work is split. At session end the first script
decides whether an entry was owed and, if one was, appends a line to
`~/.claude/knowledge/.experience-debt`. At the start of the next session the second
script prints that queue, which for `SessionStart` lands in the transcript as context
Claude can see, then moves it to `.experience-debt.log` so the queue clears but the
history survives.

Owed means two things held: the transcript carried at least five `tool_use` records, and
nothing under `experiences/` was written after the session began. The window comes from a
marker file that `kb-session-start.sh` stamps per session and `find -newer` compares
against, which keeps both scripts free of `stat` and its incompatible BSD and GNU flags.
A `resume` or `compact` start leaves the marker alone, so the window tracks the stretch
of work rather than the process. No marker means no window, and the check makes no claim.

### Install

```bash
REPO=~/myProjects/andrei-agentic-ai-skills
ln -sfn "$REPO"/kb-session-end.sh ~/.claude/kb-session-end.sh
ln -sfn "$REPO"/kb-session-start.sh ~/.claude/kb-session-start.sh
```

```json
{
  "hooks": {
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "sh ~/.claude/kb-session-end.sh", "timeout": 10 }] }
    ],
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "sh ~/.claude/kb-session-start.sh", "timeout": 10 }] }
    ]
  }
}
```

Requires `jq` on `$PATH`.

### About that threshold

Five tool calls is a proxy for "task of substance", and proxies drift. Every session ends
with a row in `.experience-decisions.log` recording the count and the verdict -
`below-threshold`, `no-marker`, `entry-written`, or `flagged` - including the sessions
that were skipped, so the skipping is visible rather than silent.

Measured across 40 transcripts on the machine this was written on, sessions fell into
0-2 tool calls and 35-264, with nothing in between. Any threshold from 3 to 34 sorted
that history identically, so the number was not worth tuning there. On a busier install
the gap may not exist, and the log is what settles it: if rows marked `below-threshold`
start naming work worth recording, move the line to fit their counts.

The same data ruled out the sharper-looking signal. Counting file edits instead of tool
calls would have discarded a 250-call session that made zero edits and was pure research,
which is exactly the kind of session an experience entry is for. Counting `"type":"user"`
records is no better, because the transcript tags tool results as user messages.

## License

MIT - see [LICENSE](LICENSE).

## Status line

[`statusline-command.sh`](statusline-command.sh) renders two lines below the prompt:

```
🤖 Claude Opus 5 | ⚡ high | 🧠 40% | ⏱️ 5h ████░░░░░░ 42% resets 3:15PM
📁 my-repo | 🌳 no worktree | 🌿 feature-branch +2 ~1
```

**Line 1:** model, effort level, context window used, and 5-hour rate limit with a bar
that runs green → yellow → red as it fills. The 7-day limit is implemented but
commented out.

**Line 2:** repo name, worktree name, and branch with staged (`+N`) and modified
(`~N`) counts.

Install:

```bash
cp andrei-agentic-ai-skills/statusline-command.sh ~/.claude/
```

Then in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "sh ~/.claude/statusline-command.sh"
  }
}
```

Requires `jq` and `git` on `$PATH`.
