# raw/

Unprocessed source material, kept for provenance before extraction into `pages/`.

Naming: `YYYY-MM-DD-<topic>.<ext>`

Examples:
- `2026-06-12-connection-pool-notes.java` — a class excerpt
- `2026-06-12-test-framework-guide.txt` — an exported internal doc
- `2026-06-12-migration-pr.md` — a pasted PR description

Once extracted, keep the file and mark it in the first line:

```
<!-- processed: pages/<project>/<page>.md -->
```

Most raw material won't survive the Category A gate — see [../CLAUDE.md](../CLAUDE.md).
That's expected. Keep the source anyway; the gate decides what becomes a page, not
what's worth having on disk.
