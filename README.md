# Andrei's Agentic AI Skills

> [!NOTE]
> Shared as-is. These work for me but haven't been tested much beyond my own setup,
> so your mileage may vary.

Claude Code skills for development workflows — a persistent cross-project knowledge
base and a set of coding behavioral guidelines — plus a custom status line.

## Contents

- [Installation](#installation)
- [Skills](#skills)
  - [Code quality](#code-quality)
  - [Knowledge base](#knowledge-base)
- [How the knowledge base works](#how-the-knowledge-base-works)
- [Status line](#status-line)

## Installation

```bash
git clone https://github.com/andreiGl/andrei-agentic-ai-skills.git
```

Then either copy the pieces into `~/.claude/`, or symlink them so this repo stays the
source of truth. Claude Code follows symlinks, and skills registered through one behave
identically.

### Copy

```bash
cp -R andrei-agentic-ai-skills/skills/* ~/.claude/skills/
cp -R andrei-agentic-ai-skills/knowledge ~/.claude/knowledge
```

Simple, but edits made while working don't flow back — you have to remember to copy
them across, and in practice you won't.

### Symlink (what I run)

```bash
REPO=~/IdeaProjects/andrei-agentic-ai-skills
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
published. The copies here are empty templates for a fresh install — they're meant to
diverge from a live knowledge base, which is why they aren't linked.

The same reasoning applies to [`CLAUDE.md`](CLAUDE.md) at the repo root: it's an example
of the wiring, not a symlink target, because global instructions tend to accumulate
project-specific and private rules over time.

The knowledge skills do nothing until the global `CLAUDE.md` tells Claude when to run
them. See [`CLAUDE.md`](CLAUDE.md) in this repo for the wiring I use — copy the
`## Knowledge base` section into your own `~/.claude/CLAUDE.md`.

## Skills

### Code quality

| Skill | Description |
| :--- | :--- |
| [`behavioral-guidelines`](skills/behavioral-guidelines) | Principles that reduce common LLM coding mistakes: avoid overcomplication, make surgical changes, surface assumptions, write for a human reader |

Referenced directly from `CLAUDE.md` rather than invoked, so it applies to every
coding task.

### Knowledge base

Five skills that maintain a knowledge base carrying context across sessions.

| Skill | When it runs |
| :--- | :--- |
| [`load-knowledge`](skills/load-knowledge) | Start of a substantial task in a project that has pages |
| [`update-knowledge`](skills/update-knowledge) | After a task that produced a surprise, correction, or rule |
| [`build-knowledge`](skills/build-knowledge) | On request, to create or extend a KB |
| [`check-knowledge`](skills/check-knowledge) | Before a large task, or 2+ weeks since pages were verified |
| [`synthesize-knowledge`](skills/synthesize-knowledge) | 5+ experience entries, or a theme repeating in learnings |

## How the knowledge base works

Context windows reset between sessions. Some facts aren't recoverable from the code at
all — how an external system actually behaves, why one approach was chosen over
another, which failure mode already burned you twice. The knowledge base is where
those go.

```
knowledge/
├── CLAUDE.md           — conventions and structure (the single source for them)
├── INDEX.md            — every page, with project, tags, and covered paths
├── learnings.md        — chronological journal across projects
├── gotchas.md          — one-line sharp facts
├── active-context.md   — open work and areas in flux
├── pages/<project>/    — curated pages, one directory per repo
├── experiences/        — per-session notes
└── raw/                — source material before extraction
```

The gate that keeps it useful:

> "Can this fact be derived from reading the code in under 3 tool calls?"

If yes, it doesn't become a page. A knowledge base that restates the codebase goes
stale silently and stops being read — the discipline is discarding most of what you
gather.

Two header fields drive everything. `Tags` decides what `load-knowledge` pulls in for
a given task; `Covers` (repo-relative path globs) lets `check-knowledge` map recent
commits onto the pages that claim to describe them. A page with neither will never
surface and never be verified.

There's a [presentation deck](knowledge/presentation/knowledge-base-deck.html)
walking through the system — clone and open it in a browser.

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
