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

Clone, then copy the pieces you want into `~/.claude/`:

```bash
git clone https://github.com/andreiGl/andrei-agentic-ai-skills.git
```

Skills — copy all of them, or just the directories you want:

```bash
cp -R andrei-agentic-ai-skills/skills/* ~/.claude/skills/
```

Claude Code discovers skills at `~/.claude/skills/<name>/SKILL.md`, one level deep.
Nesting them in subdirectories stops them being registered.

The knowledge base scaffold — empty files with the right structure and conventions:

```bash
cp -R andrei-agentic-ai-skills/knowledge ~/.claude/knowledge
```

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
