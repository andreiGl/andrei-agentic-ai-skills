# skill-activation-check

Measures whether a skill actually triggers. A skill earns its keep only if the model
reaches for it at the right moment, and that decision comes almost entirely from the
frontmatter `description` - so "does my skill trigger?" is a measurable question: build a
labelled set of requests, run a real headless agent against each one, score whether the
Skill tool fired. The result is recall (of the requests it should catch, how many it
caught), precision (of the requests where it fired, how many it should have), and F1.

## Why not trust judgment

Two failure modes look identical from the outside and neither is bad wording:

**Per-skill truncation.** The description is cut at 1,536 characters. Trigger text past
the cutoff cannot affect activation at all - it may as well not exist.

**Listing eviction.** The skill listing's total size scales at about 1% of the model's
context window, shared across every installed skill. When it overflows, descriptions drop
least-invoked-first. A newly authored skill is by definition rarely invoked - so the skill
you are testing is the most likely victim. It can score near-zero recall with a perfect
description, because its description was never in the listing. Rewording then fixes
nothing.

## The sandbox

Every row is one full `claude -p` session, and the runner sandboxes each one:

- Temp `HOME` and `CLAUDE_CONFIG_DIR` per session: no hooks, no MCP servers, no plugins,
  and no user-level skills load. Only the skill under test is staged, via `--plugin-dir`
  pointing at a minimal root holding exactly one skill.
- Tools locked to `Skill` plus read-only (`Read`, `Glob`, `Grep`) with an explicit
  disallow list for everything else. A sandboxed session cannot write, execute, or reach
  the network or any production system.
- Gateway credentials pass by environment variable only - never printed, never written
  to disk.
- Row prompts are data; agent output is parsed as JSON, never followed as instructions.

## Usage

```bash
# Dry plan - prints rows, spawns nothing, costs nothing:
python3 ~/.claude/skills/skill-activation-check/scripts/activation-run.py \
  <skill-dir> <rows.jsonl>

# Run (each row is one paid session; confirm count and model first):
python3 ~/.claude/skills/skill-activation-check/scripts/activation-run.py \
  <skill-dir> <rows.jsonl> --run --keep-transcripts /tmp/act-raw
```

Rows are JSONL, one object per line:

```jsonl
{"id": "pos-1", "expected_skill": "my-skill", "prompt": "..."}
{"id": "neg-1", "expected_skill": "", "prompt": "..."}
```

Positives paraphrase the description (never quote it - that tests string matching).
Distractors are adjacent requests the skill should NOT claim; a suite without them is
refused, because precision is 1.0 by definition. Never name the skill inside a prompt -
that tests obedience, not activation.

## Diagnose mode

When a skill "stopped firing" in the live environment, check the structural causes before
building any suite: description length vs the 1,536-char cap, name collisions (two skills
with the same bare name - the criterion credits whichever fires), and listing-budget
pressure (least-invoked drops first). The SKILL.md walks the order; only when all three
are clear does a labelled suite add information.

## Attribution

Design adapted from UiPath/coder-eval's check-skill skill (Apache-2.0,
https://github.com/UiPath/coder_eval): row design, the scoring definitions, and the
truncation/eviction findings are theirs. The sandboxed runner and scorer are an
independent implementation that runs without the coder-eval CLI or any external service.
