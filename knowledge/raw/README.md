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

A file marked that way is never promoted to `pages/`, never quoted into `gotchas.md`,
`learnings.md` or any other shared file, never published, and never included in a
cross-account handoff. Don't apply the Category A gate to it: the gate decides what is
page-worthy, and this marker says the question doesn't arise.

Whether marked material may go into an explicitly approved private backup is a decision each
install makes and states, because the answer depends on what that remote is and who approved
it. An earlier version of this file said such files never leave the machine at all. That
forbids backing up your own restricted notes to your own approved remote, which is a rule
people break, and a rule broken quietly is worse than one with a stated exception. The line
that matters is publication and handoff, not the disk.

The marker never overrides credential or secret exclusions. It says where knowledge may go,
not that a file is safe to commit.

Without this the two markers describe every file as either awaiting extraction or already
extracted, and a file that is neither reads as the first one.

Most raw material won't survive the Category A gate - see [../CLAUDE.md](../CLAUDE.md).
That's expected. Keep the source anyway; the gate decides what becomes a page, not
what's worth having on disk.
