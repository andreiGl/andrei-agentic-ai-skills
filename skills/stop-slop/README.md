# Stop Slop

> [!NOTE]
> Third-party skill, vendored into this repo. Source:
> [hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop) at commit
> [`8da1f03`](https://github.com/hardikpandya/stop-slop/commit/8da1f030185bdfe8471220585162991eaeb970e9)
> (2026-03-18), copied unmodified apart from this note. MIT licensed — see
> [LICENSE](LICENSE). Pull upstream changes with:
>
> ```bash
> git clone https://github.com/hardikpandya/stop-slop.git /tmp/stop-slop
> rsync -a --exclude .git --delete /tmp/stop-slop/ skills/stop-slop/
> ```

A skill for removing AI tells from prose.

<img width="3840" height="2160" alt="G-Yg4RVbIAAhVxW" src="https://github.com/user-attachments/assets/902afc15-1f40-4a9d-af24-8cd67afb8ebf" />

## What this is

AI writing has patterns. Predictable phrases, structures, rhythms. This skill teaches Claude (or any LLM) to catch and remove them.

## Skill Structure

```
stop-slop/
├── SKILL.md              # Core instructions
├── references/
│   ├── phrases.md        # Phrases to remove
│   ├── structures.md     # Structural patterns to avoid
│   └── examples.md       # Before/after transformations
├── README.md
└── LICENSE
```

## Quick start

**Claude Code:** Add this folder as a skill.

**Claude Projects:** Upload `SKILL.md` and reference files to project knowledge.

**Custom instructions:** Copy core rules from `SKILL.md`.

**API calls:** Include `SKILL.md` in your system prompt. Reference files load on demand.

## What it catches

**Banned phrases** - Throat-clearing openers, emphasis crutches, business jargon, all adverbs, vague declaratives, meta-commentary. See `references/phrases.md`.

**Structural clichés** - Binary contrasts, negative listings, dramatic fragmentation, rhetorical setups, false agency, narrator-from-a-distance voice, passive voice. See `references/structures.md`.

**Sentence-level rules** - No Wh- sentence starters, no em dashes, no staccato fragmentation, no lazy extremes, active voice required.

## Scoring

Rate 1-10 on each dimension:

| Dimension | Question |
|-----------|----------|
| Directness | Statements or announcements? |
| Rhythm | Varied or metronomic? |
| Trust | Respects reader intelligence? |
| Authenticity | Sounds human? |
| Density | Anything cuttable? |

Below 35/50: revise.

## Author

[Hardik Pandya](https://hvpandya.com)

## License

MIT. Use freely, share widely.
