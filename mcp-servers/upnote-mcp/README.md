# UpNote MCP server

An MCP server that connects Claude Code and Claude Desktop to the [UpNote](https://getupnote.com)
desktop app on macOS. Claude can search and read your notes, create formatted notes, move notes
to Trash and back, replace a note with an edited version, and open notes in the app.

It never writes to UpNote's database. Reads open the database read-only, and every change goes
through UpNote's own `upnote://` links, so the app makes the change and syncs it like one made
by hand.

## Requirements

- macOS, with UpNote installed from the Mac App Store. The server reads
  `~/Library/Containers/com.getupnote.desktop/Data/Library/Application Support/UpNote/upnote.sqlite3`.
  Set `UPNOTE_DB` to point it elsewhere.
- [uv](https://docs.astral.sh/uv/). The server declares its one dependency, the MCP Python SDK,
  inside `server.py`, and uv installs it on first run.
- UpNote running, for any tool that changes a note or opens the app.

## Install

Link this folder into `~/.claude` as shown in the [root README](../../README.md), then register
the server with each app.

Claude Code, for all projects:

```bash
claude mcp add --scope user upnote -- "$(command -v uv)" run --script ~/.claude/mcp-servers/upnote-mcp/server.py
```

Claude Desktop, in `~/Library/Application Support/Claude/claude_desktop_config.json`, with
absolute paths for both uv and the script:

```json
{
  "mcpServers": {
    "upnote": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["run", "--script", "/Users/you/.claude/mcp-servers/upnote-mcp/server.py"]
    }
  }
}
```

Restart Claude Desktop after editing that file. A running Claude Code session keeps the tools it
started with, so start a new one after changing the server.

## Tools

| Tool | What it does |
| :--- | :--- |
| `search_notes` | Finds notes containing all the given words in the title or body, case-insensitive in any language |
| `list_notes` | Lists notes newest first, optionally within a notebook or tag |
| `get_note` | Returns one note's text or HTML, in parts for long notes |
| `list_notebooks` | Lists notebooks with their paths and note counts |
| `list_tags` | Lists tags with note counts |
| `run_select` | Runs one read-only SQL query, for questions the other tools don't cover |
| `create_note` | Creates a note, optionally in a notebook, and returns its id once UpNote has saved it |
| `move_note_to_trash` | Moves a note to Trash |
| `restore_note` | Moves a note out of Trash |
| `replace_note` | Edits a note by creating a new version and trashing the original, after a preview |
| `open_in_upnote` | Shows a note, notebook, tag or search in the app |

Notes in Trash are left out of searches and lists unless `include_trashed` is set. No tool
deletes a note permanently.

## How changes are made

- **Reads** use a read-only SQLite connection. An authorizer refuses everything except reading,
  including writes, PRAGMA and ATTACH.
- **Create** sends UpNote's documented `note/new` link. The body is Markdown, with raw HTML for
  what Markdown can't express, such as UpNote's collapsible sections. The formatting guide Claude
  follows is part of the tool's description.
- **Trash and restore** send `note/moveToTrash` and `note/restore`. Neither is in UpNote's
  documentation, but both are in the app's link handler. The tool checks the note in the
  database first, so UpNote only ever receives ids that exist.
- **Every change is confirmed.** The tool polls the database until UpNote has saved the change,
  or says so if nothing changed within ten seconds.

## Replacing a note

UpNote has no link that edits a note, so `replace_note` creates a corrected copy and moves the
original to Trash. It takes two calls: a preview that changes nothing, then the replacement,
which has to pass back the revision number the preview returned.

The preview refuses when something would be lost for good: attachments or images, links from
other notes, a web share link, a template, or a note already in Trash. It warns, and the
replacement needs those warnings accepted, when the note is pinned or bookmarked, sits in more
than one notebook, has been saved 20 or more times, has collapsed or complex sections, or was
edited in the last ten minutes.

The original goes to Trash only after the new version is confirmed in the same notebook, and
only if nobody changed the original in the meantime. The new version gets a new id, so pinning
and Version History stay with the original.

## Limits

- macOS only, and by default only the App Store build's database location.
- The trash and restore links are undocumented, so an UpNote update could remove them.
- A search left active in UpNote stays active when `open_in_upnote` shows a notebook or tag, and
  no link clears it.
- Search matches substrings in the title and plain text. It is not a ranked index.

## Test

`test_readonly.py` compares every read tool with direct queries on your own library and confirms
that `run_select` refuses writes. It changes nothing. Run it from this folder:

```bash
uv run --script test_readonly.py
```

The create, trash, restore and replace tools were tested by hand against labelled test notes.
Those tests aren't included, because they change a real library.
