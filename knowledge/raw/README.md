# raw/

Unprocessed source material, kept for provenance before extraction into `pages/`.

Naming: `YYYY-MM-DD-<topic>.<ext>`

Examples:
- `2026-06-12-connection-pool-notes.java` - a class excerpt
- `2026-06-12-test-framework-guide.txt` - an exported internal doc
- `2026-06-12-migration-pr.md` - a pasted PR description

Once extracted, keep the file and mark it in the first line:

```
<!-- processed: pages/<project>/<page>.md -->
```

Some material is worth keeping and must never become a page - a measurement taken from a
private environment, an export that can't be republished. Extraction is not pending for
those, it is refused, so mark them in the first line instead:

```
<!-- internal-only: do not extract -->
```

A file marked that way is never promoted to `pages/`, never quoted into `gotchas.md` or
`learnings.md`, and never copied into anything that leaves the machine. Don't apply the
Category A gate to it: the gate decides what is page-worthy, and this marker says the
question doesn't arise.

Without this the two markers describe every file as either awaiting extraction or already
extracted, and a file that is neither reads as the first one.

Most raw material won't survive the Category A gate - see [../CLAUDE.md](../CLAUDE.md).
That's expected. Keep the source anyway; the gate decides what becomes a page, not
what's worth having on disk.
