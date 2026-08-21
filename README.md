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
