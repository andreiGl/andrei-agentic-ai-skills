# Knowledge Base - Conventions

A personal, cross-project knowledge base for use with Claude Code. It lives at
`~/.claude/knowledge/`, outside any repository, and carries context across sessions so
project background doesn't have to be re-explained every time.

This file is the only place these conventions are defined. The `*-knowledge` skills say
what to do; they defer here for how.

---

## Layout

```
knowledge/
├── CLAUDE.md           - this file: conventions and structure
├── INDEX.md            - every page, with project, tags, and covered paths
├── learnings.md        - chronological journal across all projects
├── gotchas.md          - one-line sharp facts, fast to scan
├── active-context.md   - open work and areas in flux
├── pages/<project>/    - curated knowledge pages, one directory per repo
├── pages/shared/       - facts that apply everywhere, incl. patterns.md
├── experiences/        - per-session notes: decisions made, surprises found
│   └── archive/        - entries already distilled into pages
└── raw/                - original source material before extraction
```

One directory per repo under `pages/`, named after the repo. Facts that apply
everywhere go in `pages/shared/`.

Distilled experience entries move into `experiences/archive/` rather than staying put.
That's deliberate: `synthesize-knowledge` triggers on how many *undistilled* entries
have accumulated, so leaving them in place would keep the trigger permanently true.

---

## The Category A gate

Ask before creating any page:

> "Can this fact be derived from reading the code in under 3 tool calls?"

- **Yes** → don't write a page. Add a line to `gotchas.md` only if the fact is
  non-obvious or counterintuitive. Otherwise skip it entirely.
- **No** → record it.

Things that pass the gate:
- Behavior of an external system that the code can't tell you
- A constraint that exists for reasons invisible in the code
- A personal preference not written down in any project file
- A build or test behavior that contradicts what you'd reasonably expect

Things that don't:
- What a task did - the commit message covers it
- Module lists, class hierarchies, package structure - read the code
- Style rules that a config file in the repo already states
- Commit or PR format - that belongs in the project's own `CLAUDE.md`

---

## Page conventions

### Naming

`kebab-case.md`, under 40 characters. Prefix with a category hint when it helps
scanning: `db-`, `build-`, `auth-`.

### Header - required on every page

```markdown
# <Title>

**Project:** <repo name> | shared
**Tags:** comma-separated keywords
**Covers:** repo-relative path globs this page describes
**Status:** verified | inferred | stale
**Last updated:** YYYY-MM-DD
**Related:** [[other-page]], [[another-page]]
```

`Tags` drives loading - `load-knowledge` matches them against task keywords.
`Covers` drives staleness - `check-knowledge` matches recently changed files against
these globs.

**The header is the source of truth for both.** `INDEX.md` carries the same values as a
derived cache, so a skill can route without opening every page. When the two disagree,
the header wins - copy it across rather than reconciling by hand. Verify a glob matches
something real before writing it: an invented glob is worse than `—`, because then every
unrelated commit flags the page.

Write `Covers: —` when the page describes no particular paths, as the cross-cutting
pages (`gotchas`, `active-context`, `learnings`, `patterns`) all do. That's a real
value, not a blank to be filled in later: it tells `check-knowledge` to skip the page
rather than invent globs for it. **Tags**, by contrast, are never optional - a page
without them will never be loaded by anything.

**Status:**
- `verified` - checked against the live codebase; trust it
- `inferred` - written from exploration, not verified; spot-check any specific class
  name, path, or signature before acting on it
- `stale` - known to need updating; read with skepticism

### Body

1. One-paragraph summary - the whole point in 3-5 sentences.
2. Key concepts - terms and facts a reader needs first.
3. Detail sections - H2/H3, code blocks annotated with a language.
4. Gotchas - a dedicated section for what bites.
5. Cross-references - `[[page-name]]`, no `.md` extension. See below for how they
   resolve and when a back-link is required.

### How `[[links]]` resolve

A link is the page's filename without `.md`. Resolve it by looking, in order, at:

1. The KB root - `learnings`, `gotchas`, `active-context`, `INDEX`
2. `pages/<current project>/`
3. `pages/shared/`

Filenames are unique across the whole KB, so a link never needs a path. Two pages in
different projects must not share a name - if you want `db-notes` in two projects,
prefix them.

### When a back-link is required

Topic page to topic page: **always both ways.** If A links B, add the link back from B.

The four hub pages - `gotchas`, `active-context`, `learnings`, `patterns` - are exempt.
They aggregate across the whole KB and link outward to many topic pages; requiring
reciprocity would put a near-identical `Related:` line on every page in the KB, which
carries no navigational information. A topic page links a hub only when that hub is
genuinely worth reading alongside it.

---

## Processing new source material

1. Save the source verbatim in `raw/` as `YYYY-MM-DD-<topic>.<ext>`.
2. Apply the Category A gate. Most material won't survive it - that's expected.
3. What survives goes into `pages/<project>/`, one concept per page. Merge into an
   existing page when the material belongs there.
4. Update `INDEX.md` and add `[[links]]` both ways.
5. Add to `learnings.md` if the session produced a surprise or a rule.
6. Write a dated entry in `experiences/`.

Once processed, mark the raw file in its first line:
`<!-- processed: pages/<project>/<page>.md -->`

---

## What does not go here

- Whole source files - keep excerpts; the repo is the source of truth
- In-session task state - that's what plans and task lists are for
- Git history or who-changed-what - `git log` is authoritative
- Anything already in the project's own `CLAUDE.md`

---

## Freshness

- Every page carries **Last updated**.
- Before acting on a remembered class, function, or path, confirm it still exists.
- When a page contradicts what you observe, fix the page and note the correction in
  `learnings.md`.

---

## learnings.md

Chronological, newest last, under 10 lines per entry:

```markdown
## YYYY-MM-DD - <short topic>
**What worked:** ...
**What didn't / surprised us:** ...
**Rule extracted:** ...
**Prevented (optional):** [what would have happened]. Gotcha: [the bullet that caught it].
```

Include **Prevented** only when a `gotchas.md` bullet visibly caught something during
the session. Bullets that never appear in a Prevented entry across many sessions are
candidates for deletion - that's the signal they aren't earning their place.

`synthesize-knowledge` owns distillation, and its own "When to run" section is the only
place the thresholds are stated. Don't restate them here or in the other skills - that
is how three slightly different versions of one rule end up in three files.
