---
name: load-knowledge
description: Load the personal knowledge base at ~/.claude/knowledge/ to prime context before starting work. Use at the start of any substantial task, so gotchas, conventions, and open context recorded by past sessions are in hand before the first tool call.
---

# Load the Knowledge Base

Read the knowledge base before working, so context from past sessions is in hand
before the first tool call. Conventions live in `~/.claude/knowledge/CLAUDE.md`.

Run this at the start of substantial work without checking first whether the project
has pages — finding that out *is* step 1, and the empty case costs one line (see the
end of this file).

## 1. Always load

This list is authoritative; no other file restates it.

1. `~/.claude/knowledge/learnings.md` — rules and surprises from past sessions
2. `~/.claude/knowledge/INDEX.md` — every page, with tags and covered paths
3. `~/.claude/knowledge/gotchas.md` — sharp facts, fast to scan
4. `~/.claude/knowledge/active-context.md` — open work and areas in flux
5. `~/.claude/knowledge/pages/shared/patterns.md` — recurring patterns, if it exists

Skip anything already in the current context. If a file is missing, note it and move
on — that part of the KB just hasn't been built yet.

## 2. Then load by tag match

Identify the current project:

```bash
basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
```

Outside a repository that falls back to the directory name, which is usually right. If
it clearly isn't the project name, match on `shared` pages only rather than guessing.

Then read `INDEX.md` and load any page where:

- **Project** is the current project or `shared`, **and**
- **Tags** overlap the task description, **or** **Covers** matches a file the task
  will touch

Load the whole page, not an excerpt — pages are small by design. When more than five
pages match, load the ones whose Covers globs are closest to the files in play, and
say which ones you skipped.

## 3. Act on the Status field

`~/.claude/knowledge/CLAUDE.md` defines what the three values mean. What to do with a
page that isn't `verified`:

- **`inferred`** — before acting on a specific claim (class name, path, method
  signature), spot-check it with one `grep` or `ls`. If it holds, set
  `Status: verified` and bump **Last updated**. If it doesn't, fix the page and note
  the correction in `learnings.md`.
- **`stale`** — verify before acting on anything in it, and don't promote it to
  `verified` on the strength of one spot-check; a stale page was flagged for a reason
  the note should name.

## When there is nothing to load

If the project has no pages and `gotchas.md` is empty, say so in one line and start
the task. Don't run `build-knowledge` on the spot — building a KB is its own task,
worth doing deliberately rather than as a detour.
