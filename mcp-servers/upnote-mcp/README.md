# UpNote MCP server

An MCP server that connects Claude Code and Claude Desktop to the [UpNote](https://getupnote.com)
desktop app on macOS. Claude can search and read your notes, create formatted notes, move notes
to Trash and back, add to the end of a note, replace a note with an edited version, and open
notes in the app.

It never writes to UpNote's database. Reads open the database read-only, and every change goes
through UpNote's own `upnote://` links, so the app makes the change and syncs it like one made
by hand.

## Requirements

- macOS, with UpNote installed from the Mac App Store. The server reads
  `~/Library/Containers/com.getupnote.desktop/Data/Library/Application Support/UpNote/upnote.sqlite3`.
  Set `UPNOTE_DB` to point it elsewhere.
- [python.org's Python](https://www.python.org/downloads/macos/) 3.12 or newer, and `clang`
  from the Xcode Command Line Tools to build the launcher. [Full Disk Access](#full-disk-access)
  explains why the server runs this way.
- UpNote running, for any tool that changes a note or opens the app.

## Install

Link this folder into `~/.claude` as shown in the [root README](../../README.md). Then build a
venv for the server and the launcher that starts it, and register the launcher with Claude Code
for all projects:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv ~/.claude/mcp-servers/upnote-mcp-venv
~/.claude/mcp-servers/upnote-mcp-venv/bin/python -m pip install 'mcp==2.2.0'
clang -O2 -o ~/.claude/mcp-servers/upnote-mcp-launcher ~/.claude/mcp-servers/upnote-mcp/launcher.c
codesign -s - -i ca.glotov.upnote-mcp-launcher -f ~/.claude/mcp-servers/upnote-mcp-launcher
claude mcp add --scope user upnote -- ~/.claude/mcp-servers/upnote-mcp-launcher
```

Keep the `mcp` version in the venv in step with the one `server.py` declares.

For Claude Desktop, add the launcher by its absolute path to
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "upnote": {
      "command": "/Users/you/.claude/mcp-servers/upnote-mcp-launcher"
    }
  }
}
```

Last, add `~/.claude/mcp-servers/upnote-mcp-launcher` under System Settings, Privacy & Security,
Full Disk Access, and restart Claude. A running Claude Code session keeps the tools it started
with, so start a new one after changing the server.

## Tools

| Tool | What it does |
| :--- | :--- |
| `search_notes` | Finds notes containing all the given words in the title or body, case-insensitive in any language, optionally within a notebook, tag or date range |
| `list_notes` | Lists notes by last update or creation date, newest first, optionally within a notebook, tag or date range |
| `get_note` | Returns one note's text or HTML, in parts for long notes, with its attachments' names |
| `list_notebooks` | Lists notebooks with their paths and note counts |
| `list_tags` | Lists tags with note counts |
| `run_select` | Runs one read-only SQL query, for questions the other tools don't cover. It stops a query after ten seconds, refuses values over 50 MB, and reads attachment download links as NULL |
| `create_note` | Creates a note, optionally in a notebook and with tags, and returns its id once UpNote has saved it |
| `move_note_to_trash` | Moves a note to Trash |
| `restore_note` | Moves a note out of Trash |
| `replace_note` | Edits a note by creating a new version and trashing the original, after a preview; can also move it or remove tags |
| `append_to_note` | Adds content to the end of a note, copying what's already there, the same way as `replace_note` |
| `move_note` | Moves a note to another notebook by rebuilding it there unchanged, the same way as `replace_note` |
| `make_section` | Turns a heading, or a range between two markers, into a collapsible section, nested where it sits |
| `open_in_upnote` | Shows a note, notebook, tag or search in the app |
| `check_upnote_setup` | Reports the database path, UpNote's data version, any missing columns, note counts, and which program started the server |

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
- "Add a follow-up item to my Plans note." Claude appends it and keeps the rest of the note.
- "What did I change this week?" Claude lists notes with `updated_after`.
- "Move my Plans note to Archive." Claude previews the move, then rebuilds the note there.
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

UpNote's own Markdown conversion adds an empty bullet after every nested list, whatever the
indent. So before sending, the server rewrites each list that has nesting as HTML in the shape
UpNote's editor uses, with the items' formatting converted too: bold, italic, code, links, bare
URLs, `<https://…>` links, strikethrough, `==green==`, checkboxes, and inline HTML such as `<u>`.
A numbered list keeps its starting number. Flat lists, and lists in code blocks, HTML or HTML
comments, are sent as written. So is a list whose items hold a code block, a quote, a table, or
a paragraph after a blank line, and it keeps the empty bullet.

Tags go in `create_note`'s `tags` parameter. The server adds each one as a hashtag link at the
end of the note, which is how UpNote stores tags, and waits until UpNote has recorded them. A
`#hashtag` typed in the body stays plain text.

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
other notes, a web share link, or a template. It also refuses a note already in Trash, and one in
a notebook whose title another notebook shares. It warns, and the replacement needs those
warnings accepted, when the note is pinned or bookmarked, sits in more than one
notebook, has been saved 20 or more times, has collapsible sections or a body over 20,000
characters, or was edited in the last ten minutes.

The new version keeps the original's tags. UpNote stores a tag as a hashtag link inside the note,
so the server adds one at the end for each tag the new text doesn't already carry, and waits until
UpNote has recorded them. To drop a tag, name it in `remove_tags`: its links are taken out, and
one inside a sentence becomes plain text. Pin and bookmark can't be
carried over: no link sets them (tested 2026-10-10; UpNote answers "This link is not supported."
for routes such as `note/pin`), so the preview warns about them.

The original goes to Trash only after the new version is confirmed in its notebook with the
same tags, and only if nobody changed the original in the meantime. For the tools that keep the
content, `append_to_note`, `move_note` and `make_section`, every line of the original's text must
also be in the new version. If anything fails after the new version exists, the tool says so and
leaves both notes for you to compare. The new version gets a new id, so Version History stays
with the original.

Line breaks between HTML tags are removed only outside `<pre>` blocks and Markdown code fences,
so a code example keeps its layout. A note made outside UpNote's create link may have no title
heading, its title being its first line; that line isn't repeated under the new version's title.

`notebook` puts the new version in another notebook, and `move_note` does only that: it rebuilds
the note unchanged in the notebook you name. UpNote has no link that moves a note, so a move costs
what a replace does: a new id, and pin and bookmark set again by hand.

Hand-written raw HTML, such as a collapsible section copied from the note's own `get_note` html,
survives the round-trip: UpNote re-parses it as native formatting (2026-09-24, UpNote 9.22.2).

## Adding to a note

`append_to_note` takes only the new content, in Markdown, and adds it after everything already in
the note. The server copies the existing content itself, so Claude never resends a long note, and
nothing in it can be dropped or reworded on the way. It rebuilds the note through `replace_note`,
with the same preview, warnings and checks, so the result has a new id and the original goes to
Trash.

The existing HTML goes first, then a blank line, then the new Markdown. The blank line makes
UpNote convert what follows as Markdown. If the note ends with a list and the new text starts
with one, UpNote joins them into one list. Tag links are moved below the new content, so a
note's tags stay at its end however often it's appended to. A hashtag inside a sentence stays
where it is.

Every rebuild, by `replace_note`, `append_to_note` or `make_section`, first removes line breaks
between block tags. A browser ignores them, but UpNote's create link turns each one into an empty
`<div>`, so a note would collect them with every rebuild. A line break between inline tags, such
as `</b>` and `<i>`, shows as a space and is kept; UpNote keeps it too (2026-10-10, UpNote 9.22.6).

## Nested sections

UpNote's editor can't put a collapsible section inside another one, but it renders and syncs them
correctly, and keeps them when you edit the note by hand. `make_section` builds them: name a heading
inside an existing section, and the heading with the content under it becomes a section nested there.
The section holds everything to the next heading of the same or higher level, or to the end of its
container, and `collapsed=true` makes it start closed.

Content marked off by hand works too: pass `until` with the text of an end marker, and the section runs
from the heading to that marker, both markers being removed. `title` names the section when the heading
itself is only a marker.

It previews first, the same as `replace_note`, and rebuilds the note the same way, so the result has a
new id. Everything outside the wrapped range is copied through unchanged, apart from the line breaks
between block tags that every rebuild removes. It refuses a heading it
can't find, one that appears twice, one that is already a section's title, one with nothing under it,
an `until` marker it can't find after the heading, and any note whose own title heading holds extra
content, since rebuilding that would duplicate it.

## Limits

- macOS only, and by default only the App Store build's database location.
- The trash and restore links are undocumented, so an UpNote update could remove them.
- A search left active in UpNote stays active when `open_in_upnote` shows a notebook or tag, and
  no link clears it.
- Search matches substrings in the title and plain text. It is not a ranked index.
- Creating or replacing a note in a notebook whose title another notebook shares is refused,
  since UpNote's create link names a notebook by title only.

## Troubleshooting

- **Start with `check_upnote_setup`.** Ask Claude to run it. It shows which database the server
  reads, UpNote's data version, any columns an UpNote update removed, and which program started
  the server, which is the one macOS checks for access.
- **Check the connection.** In Claude Code, `claude mcp get upnote` should report the server as
  connected. Claude Desktop logs each server to
  `~/Library/Logs/Claude/mcp-server-upnote.log`, and a working start logs
  "Server started and connected successfully".
- **"Cannot open the UpNote database read-only".** macOS blocks reading another app's data
  without Full Disk Access, and granting it to Claude is not enough: the Claude desktop app
  starts MCP servers as their own responsible process, so macOS checks the binary in `command`.
  The desktop app may serve the tools even in a Claude Code session, so fix its config too.
  Check that the launcher from [Install](#install) has Full Disk Access.
- **Still blocked with Full Disk Access granted.** Look in System Settings, Privacy & Security,
  Files & Folders, for an entry whose "access data from UpNote" is switched off, often greyed out.
  `tccutil reset SystemPolicyAppData` clears those, and then Claude needs a restart: a server
  already running stays blocked after the reset.
- **Claude Desktop can't start the server.** The app doesn't use your shell's `PATH`, so the
  `command` in its config has to be the launcher's absolute path, without `~`.
- **A change reports it wasn't confirmed.** The tool waited ten seconds without seeing UpNote
  save it. Check the note before trying again, so nothing gets created twice.
- **A notebook is refused because another one has the same title.** UpNote's create link names a
  notebook by title only, so with two notebooks of that title the note could land in either.
  Rename one of them in UpNote.

## Full Disk Access

A grant on uv or Homebrew's Python doesn't last. Homebrew signs them ad hoc, so macOS ties the
grant to one build and drops it on the next `brew upgrade`. `launcher.c` builds a small binary
that starts `server.py` and waits for it. It never changes, so its grant holds. It takes no
arguments and always runs `~/.claude/mcp-servers/upnote-mcp/server.py` with the venv's Python, so
its command line can't point the grant at another program. It builds both paths from `HOME` when
it starts, though, so anyone who can set `HOME` for it can run their own code under the grant.

The launcher doesn't use uv. With uv in the chain, macOS recorded a separate "access data from
UpNote" decision against each Homebrew uv build, switched off and locked, and the server failed
with "unable to open database file" until `tccutil reset SystemPolicyAppData` and a Claude
restart. So the launcher runs a venv built from python.org's Python, which is signed by the
Python Software Foundation rather than ad hoc, and which Homebrew never upgrades.

Rebuilding the launcher changes its signature, so grant it again after a rebuild: remove it from
Full Disk Access, add it back, and restart Claude. It runs whatever `server.py` holds, so the
grant extends to any edit of that file.

## Test

The tests run on the server's venv. `test_make_section.py` checks the section-building logic,
and the HTML clean-up `append_to_note` does, against synthetic note markup, and
`test_nested_lists.py` checks the nested-list rewrite. Neither touches UpNote or your notes.
Run all four tests from this folder:

```bash
~/.claude/mcp-servers/upnote-mcp-venv/bin/python test_make_section.py
~/.claude/mcp-servers/upnote-mcp-venv/bin/python test_nested_lists.py
```

`test_readonly.py` compares every read tool except `open_in_upnote`, which changes what the app
shows, with direct queries on your own library: filters, sorting, paging and counts. It also
confirms that `run_select` refuses writes, and that the rebuild tools refuse a stale revision, an
unknown tag, an empty append and a move to the same notebook, all before anything is sent. It
changes nothing:

```bash
~/.claude/mcp-servers/upnote-mcp-venv/bin/python test_readonly.py
```

`test_live.py` checks the tools that change notes: create, append, `make_section`, replace with
a tag removed, move, trash and restore. It works on notes it creates, titled "ZZ live test" with
the time, and checks after each step what UpNote stored: tags kept and last, no empty bullets or
empty `<div>`s, the existing content unchanged, and a fenced code example intact. It also checks
that a stale revision and unaccepted warnings are refused. At the end it moves every note it
created to Trash, where they stay, synced to your other devices, until you empty Trash. The moved
note briefly sits in one of your notebooks and stays listed there in Trash. It needs UpNote
running, takes about ten seconds, and only runs with `--live`. Run it after an UpNote update:

```bash
~/.claude/mcp-servers/upnote-mcp-venv/bin/python test_live.py --live
```
