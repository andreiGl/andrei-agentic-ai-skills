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
- [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. The server declares its one
  dependency, the MCP Python SDK, inside `server.py`, and uv installs it on first run.
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
| `check_upnote_setup` | Reports the database path, UpNote's data version, any missing columns, and note counts |

Notes in Trash are left out of searches and lists unless `include_trashed` is set. No tool
deletes a note permanently.

## Examples

Ask in plain language. Claude picks the tools.

- "What's my latest note?"
- "Find my notes about JSON Patch and summarize them."
- "Which notebooks have the most notes?"
- "Create a note in Get Started with a checklist for tomorrow."
- "Move the note titled Old draft to Trash." Claude should confirm which note first.
- "In my Plans note, change Triage to In progress." Claude previews the replacement and shows
  any warnings before making it.
- "Open my Recipes notebook in UpNote."

## Formatting

`create_note` and `replace_note` take Markdown. Each of these was checked in UpNote after
creating a note with it:

- Headings, bold, italic, strikethrough, links, and inline code
- Bullet lists nested to any depth, numbered lists, and checkboxes written as `- [ ]` and `- [x]`
- Quotes, dividers, tables, and code blocks with a language, such as `json` or `bash`
- A green highlight written as `==text==`
- Raw HTML for underline with `<u>`, a yellow highlight with
  `<span class="shine-highlight-yellow">`, and UpNote's collapsible sections

UpNote drops `<mark>`. The note title becomes the note's heading, so the body shouldn't repeat it.

Tags can't be set this way. The create link has no tag option, and a `#hashtag` in the body stays
plain text, so tags have to be added in UpNote.

## How changes are made

- **Reads** use a read-only SQLite connection. An authorizer refuses everything except reading,
  including writes, PRAGMA and ATTACH.
- **Create** sends UpNote's documented `note/new` link. The body is Markdown, with raw HTML for
  what Markdown can't express, such as UpNote's collapsible sections. The formatting guide Claude
  follows is part of the tool's description.
- **Trash and restore** send `note/moveToTrash` and `note/restore`. Neither is in UpNote's
  documentation, but both are in the app's link handler. The tool checks the note in the
  database first, so UpNote only ever receives ids that exist.
- **The database format is checked on every connection.** If an UpNote update removes a table or
  column the server reads, tools fail with the missing column named instead of returning wrong
  results. `check_upnote_setup` also warns when UpNote's data version, read from `config.json`
  next to the database, isn't the tested version 17.
- **Every change is confirmed.** The tool polls the database until UpNote has saved the change,
  or says so if nothing changed within ten seconds.

## Replacing a note

UpNote has no link that edits a note, so `replace_note` creates a corrected copy and moves the
original to Trash. It takes two calls: a preview that changes nothing, then the replacement,
which has to pass back the revision number the preview returned.

The preview refuses when something would be lost for good: attachments or images, links from
other notes, a web share link, a template, or a note already in Trash. It warns, and the
replacement needs those warnings accepted, when the note is pinned or bookmarked, has tags, sits
in more than one notebook, has been saved 20 or more times, has collapsed or complex sections, or was
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

## Troubleshooting

- **Start with `check_upnote_setup`.** Ask Claude to run it. It shows which database the server
  reads, UpNote's data version, and any columns an UpNote update removed.
- **Check the connection.** In Claude Code, `claude mcp get upnote` should report the server as
  connected. Claude Desktop logs each server to
  `~/Library/Logs/Claude/mcp-server-upnote.log`, and a working start logs
  "Server started and connected successfully".
- **"Cannot open the UpNote database read-only".** macOS may block one app from reading another
  app's data. Allow the Claude app under System Settings, Privacy & Security.
- **Claude Desktop can't start the server.** The app doesn't use your shell's `PATH`, so the
  `command` in its config has to be uv's absolute path. `command -v uv` prints it.
- **A change reports it wasn't confirmed.** The tool waited ten seconds without seeing UpNote
  save it. Check the note before trying again, so nothing gets created twice.

## Test

`test_readonly.py` compares every read tool with direct queries on your own library and confirms
that `run_select` refuses writes. It changes nothing. Run it from this folder:

```bash
uv run --script test_readonly.py
```

The create, trash, restore and replace tools were tested by hand against labelled test notes.
Those tests aren't included, because they change a real library.
