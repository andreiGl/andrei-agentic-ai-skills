# update-knowledge

Persists learnings from the current task into `~/.claude/knowledge/`. Wired into the
global `CLAUDE.md`, so it usually runs without being asked.

## What's conditional and what isn't

| Output | When |
| :--- | :--- |
| A page, or a `gotchas.md` line | Only when the Category A gate passes |
| A `learnings.md` entry | Only when there was a rule or surprise |
| An experience entry | Always |

A routine task produces only the experience entry. That's the normal outcome — a page
per task is how a knowledge base fills with noise and stops being read.

## Why the experience entry is unconditional

`synthesize-knowledge` reads `experiences/` to find recurring patterns. The useful
signal is often that an unremarkable area keeps coming up; skip entries on quiet
sessions and that signal disappears. Quiet sessions get three lines, not a full write-up.

## Also

Source material handed to you during the session — a pasted doc, an exported guide —
gets saved verbatim to `raw/` before extraction. The extract is a summary; the source
is the evidence.

Distillation and trimming belong to [`synthesize-knowledge`](../synthesize-knowledge),
which is the only place those thresholds are stated.

## Related

- [`load-knowledge`](../load-knowledge) · [`build-knowledge`](../build-knowledge) ·
  [`check-knowledge`](../check-knowledge) · [`synthesize-knowledge`](../synthesize-knowledge)
