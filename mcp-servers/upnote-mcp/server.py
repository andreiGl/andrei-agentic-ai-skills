#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==2.2.0"]
# ///
"""MCP server for the local UpNote library: read notes, create notes.

The server never writes to UpNote's database. Every read opens the live database
read-only, so it sees edits made a moment ago. New notes are created by the
UpNote app itself through its upnote://x-callback-url/note/new link, so they
sync like notes typed by hand.
"""

import html as html_lib
import json
import os
import re
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

DB_PATH = Path(
    os.environ.get(
        "UPNOTE_DB",
        "~/Library/Containers/com.getupnote.desktop/Data/Library/Application Support/UpNote/upnote.sqlite3",
    )
).expanduser()

# How long create_note and the Trash tools wait for UpNote to save a change to its database.
CONFIRM_SECONDS = 10.0

INSTRUCTIONS = """\
The user's UpNote notes on this Mac. Use search_notes or list_notes to find notes,
then get_note for the full text. Notebooks are given as paths like "Parent / Child".
Notes in Trash are hidden unless include_trashed is true. create_note adds a new note
through the UpNote app; format its body as that tool's text parameter describes.
move_note_to_trash and restore_note move a note into or out of UpNote's Trash.
open_in_upnote shows a note, notebook, tag or search in the app; use it only when the user
asks to see something there.
UpNote can't change a note in place. To edit one, use replace_note: it previews first, then
creates the new version and moves the original to Trash. Notes can't be moved between
notebooks or deleted permanently."""

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
CREATE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
TRASH = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)
RESTORE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
SHOW = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
REPLACE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)

server = MCPServer(name="upnote", instructions=INSTRUCTIONS)


# ---------------------------------------------------------------- database access

# Statement parts a read may use. Everything else - writes, schema changes,
# PRAGMA, ATTACH - is refused by SQLite before it runs.
_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _authorizer(action: int, *_: Any) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _fold(value: Any) -> str:
    """Lower-case for matching. SQLite's own lower() only handles ASCII."""
    return str(value).casefold() if value is not None else ""


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise ToolError(f"UpNote database not found at {DB_PATH}. Set UPNOTE_DB to its path.")
    conn = None
    try:
        conn = sqlite3.connect(f"file:{quote(str(DB_PATH))}?mode=ro", uri=True, timeout=5.0)
        conn.execute("PRAGMA query_only = 1")
        conn.execute("SELECT 1 FROM notes LIMIT 1")
    except sqlite3.Error as e:
        if conn is not None:
            conn.close()
        raise ToolError(
            f"Cannot open the UpNote database read-only: {e}. If macOS blocked access, allow the "
            "Claude app to access data from other apps in System Settings > Privacy & Security."
        ) from e
    conn.row_factory = sqlite3.Row
    conn.create_function("fold", 1, _fold, deterministic=True)
    conn.set_authorizer(_authorizer)
    return conn


def _iso(ms: Any) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(float(ms) / 1000).astimezone().isoformat(timespec="seconds")


def _json_list(raw: Any) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


# ---------------------------------------------------------------- notebooks and tags

def _notebooks(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute("SELECT id, title, parent FROM notebooks WHERE deleted = 0").fetchall()
    nbs = {r["id"]: {"id": r["id"], "title": r["title"] or "", "parent": r["parent"] or None} for r in rows}

    def path(nb_id: str, seen: frozenset[str] = frozenset()) -> str:
        nb = nbs[nb_id]
        parent = nb["parent"]
        if parent in nbs and parent not in seen:
            return f"{path(parent, seen | {nb_id})} / {nb['title']}"
        return nb["title"]

    for nb_id in nbs:
        nbs[nb_id]["path"] = path(nb_id)
    return nbs


def _membership(conn: sqlite3.Connection, nbs: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Map note id to notebook ids.

    UpNote keeps each notebook's note ids as a JSON array in the lists table, in a
    row whose id is "notebooks_<notebook id>". The notebooks.notes column is empty.
    """
    members: dict[str, list[str]] = {}
    rows = conn.execute("SELECT id, content FROM lists WHERE id LIKE 'notebooks\\_%' ESCAPE '\\'")
    for r in rows:
        nb_id = r["id"].removeprefix("notebooks_")
        if nb_id in nbs:
            for note_id in _json_list(r["content"]):
                members.setdefault(note_id, []).append(nb_id)
    return members


def _resolve_notebook(nbs: dict[str, dict[str, Any]], ref: str) -> str:
    ref = ref.strip()
    if ref in nbs:
        return ref
    wanted = _fold(ref)
    hits = [i for i, nb in nbs.items() if wanted in (_fold(nb["title"]), _fold(nb["path"]))]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ToolError(f"No notebook matches {ref!r}. Call list_notebooks to see titles and ids.")
    raise ToolError(f"{ref!r} matches several notebooks: {', '.join(nbs[i]['path'] for i in hits)}. Pass an id.")


def _with_descendants(nbs: dict[str, dict[str, Any]], root: str) -> set[str]:
    found = {root}
    grew = True
    while grew:
        grew = False
        for nb_id, nb in nbs.items():
            if nb["parent"] in found and nb_id not in found:
                found.add(nb_id)
                grew = True
    return found


def _tag_key(tag: str) -> str:
    return _fold(tag.strip().lstrip("#"))


# ---------------------------------------------------------------- note helpers

_NOTE_COLUMNS = "id, title, text, tagLinks, createdAt, updatedAt, trashed, pinned, bookmarked"


def _filtered_notes(conn, nbs, members, notebook: str | None, tag: str | None, include_trashed: bool) -> list[sqlite3.Row]:
    sql = f"SELECT {_NOTE_COLUMNS} FROM notes WHERE deleted = 0"
    if not include_trashed:
        sql += " AND trashed = 0"
    rows = conn.execute(sql).fetchall()
    if notebook:
        allowed = _with_descendants(nbs, _resolve_notebook(nbs, notebook))
        rows = [r for r in rows if any(nb_id in allowed for nb_id in members.get(r["id"], []))]
    if tag:
        key = _tag_key(tag)
        rows = [r for r in rows if any(_tag_key(t) == key for t in _json_list(r["tagLinks"]))]
    return rows


def _excerpt(text: str | None, words: list[str], width: int = 240) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    low = flat.lower()
    positions = [p for p in (low.find(w) for w in words) if p >= 0]
    start = max(0, min(positions) - width // 3) if positions else 0
    snippet = flat[start:start + width]
    return ("…" if start > 0 else "") + snippet + ("…" if start + width < len(flat) else "")


def _summary(r: sqlite3.Row, nbs, members, excerpt: str | None) -> dict[str, Any]:
    note: dict[str, Any] = {
        "id": r["id"],
        "title": r["title"] or "",
        "notebooks": [nbs[i]["path"] for i in members.get(r["id"], []) if i in nbs],
        "tags": _json_list(r["tagLinks"]),
        "created": _iso(r["createdAt"]),
        "updated": _iso(r["updatedAt"]),
    }
    for flag in ("trashed", "pinned", "bookmarked"):
        if r[flag]:
            note[flag] = True
    if excerpt is not None:
        note["excerpt"] = excerpt
    return note


# ---------------------------------------------------------------- read tools

NotebookRef = Annotated[
    str | None,
    Field(description='Notebook title, path such as "Parent / Child", or id. Sub-notebooks are included.'),
]
TagRef = Annotated[str | None, Field(description="Tag title, with or without #.")]


@server.tool(annotations=READ)
def search_notes(
    query: Annotated[str, Field(description="Words to find. Every word must appear in the title or body. Case-insensitive, any language.")],
    notebook: NotebookRef = None,
    tag: TagRef = None,
    include_trashed: bool = False,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """Find notes containing all the given words. Title matches rank first, then the most recently updated."""
    words = _fold(query).split()
    if not words:
        raise ToolError("query is empty.")
    with closing(_connect()) as conn:
        nbs = _notebooks(conn)
        members = _membership(conn, nbs)
        rows = _filtered_notes(conn, nbs, members, notebook, tag, include_trashed)
    hits = []
    for r in rows:
        title, body = _fold(r["title"]), _fold(r["text"])
        if all(w in title or w in body for w in words):
            hits.append((sum(w in title for w in words), r["updatedAt"] or 0, r))
    hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
    return {
        "total_matches": len(hits),
        "notes": [_summary(r, nbs, members, _excerpt(r["text"], words)) for _, _, r in hits[:limit]],
    }


@server.tool(annotations=READ)
def list_notes(
    sort: Literal["updated", "created"] = "updated",
    notebook: NotebookRef = None,
    tag: TagRef = None,
    include_trashed: bool = False,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict[str, Any]:
    """List notes newest first, optionally within a notebook or tag. Each note comes with a short excerpt."""
    with closing(_connect()) as conn:
        nbs = _notebooks(conn)
        members = _membership(conn, nbs)
        rows = _filtered_notes(conn, nbs, members, notebook, tag, include_trashed)
    key = "createdAt" if sort == "created" else "updatedAt"
    rows.sort(key=lambda r: r[key] or 0, reverse=True)
    return {
        "total": len(rows),
        "offset": offset,
        "notes": [_summary(r, nbs, members, _excerpt(r["text"], [], 160)) for r in rows[offset:offset + limit]],
    }


@server.tool(annotations=READ)
def get_note(
    note_id: str,
    format: Literal["text", "html"] = "text",
    offset: Annotated[int, Field(ge=0, description="Character offset, for reading a long note in parts.")] = 0,
    max_chars: Annotated[int, Field(ge=1000, le=100000)] = 30000,
) -> dict[str, Any]:
    """Get one note's content and details. Long notes come in parts: pass next_offset back as offset."""
    with closing(_connect()) as conn:
        nbs = _notebooks(conn)
        members = _membership(conn, nbs)
        r = conn.execute(
            f"SELECT {_NOTE_COLUMNS}, html, noteLinks, fileIds FROM notes WHERE id = ? AND deleted = 0",
            (note_id.strip(),),
        ).fetchone()
    if r is None:
        raise ToolError(f"No note with id {note_id!r}.")
    body = (r["html"] if format == "html" else r["text"]) or ""
    note = _summary(r, nbs, members, None)
    note.update({"format": format, "length": len(body), "offset": offset, "content": body[offset:offset + max_chars]})
    if offset + max_chars < len(body):
        note["next_offset"] = offset + max_chars
    if linked := _json_list(r["noteLinks"]):
        note["linked_note_ids"] = linked
    note["attachment_count"] = len(_json_list(r["fileIds"]))
    return note


@server.tool(annotations=READ)
def list_notebooks() -> dict[str, Any]:
    """List all notebooks with their ids, paths, and how many notes each holds directly, not counting Trash."""
    with closing(_connect()) as conn:
        nbs = _notebooks(conn)
        members = _membership(conn, nbs)
        live = {r["id"] for r in conn.execute("SELECT id FROM notes WHERE deleted = 0 AND trashed = 0")}
    counts = {nb_id: 0 for nb_id in nbs}
    for note_id, nb_ids in members.items():
        if note_id in live:
            for nb_id in nb_ids:
                counts[nb_id] += 1
    notebooks = [
        {"id": nb["id"], "title": nb["title"], "path": nb["path"], "parent_id": nb["parent"], "note_count": counts[nb["id"]]}
        for nb in nbs.values()
    ]
    notebooks.sort(key=lambda nb: _fold(nb["path"]))
    return {"notebooks": notebooks}


@server.tool(annotations=READ)
def list_tags() -> dict[str, Any]:
    """List tags with how many notes carry each, not counting Trash."""
    with closing(_connect()) as conn:
        titles = [r["title"] for r in conn.execute("SELECT title FROM tags WHERE deleted = 0") if r["title"]]
        links = [r["tagLinks"] for r in conn.execute("SELECT tagLinks FROM notes WHERE deleted = 0 AND trashed = 0")]
    counts: dict[str, int] = {}
    shown: dict[str, str] = {}
    for title in titles:
        shown.setdefault(_tag_key(title), title)
        counts.setdefault(_tag_key(title), 0)
    for raw in links:
        for tag in set(_json_list(raw)):
            key = _tag_key(tag)
            shown.setdefault(key, tag)
            counts[key] = counts.get(key, 0) + 1
    tags = [{"tag": shown[k], "note_count": counts[k]} for k in counts]
    tags.sort(key=lambda t: (-t["note_count"], _fold(t["tag"])))
    return {"tags": tags}


_SELECT_HELP = """\
One read-only SQLite SELECT. Writes, PRAGMA and ATTACH are refused.
Useful tables and columns:
- notes: id, title, text (plain body), html, createdAt and updatedAt (Unix epoch milliseconds),
  deleted and trashed (filter both to 0), pinned, bookmarked, isTemplate,
  tagLinks (JSON array of tag titles), noteLinks (JSON array of note ids), fileIds.
- notebooks: id, title, parent (parent notebook id), deleted.
- lists: a row with id 'notebooks_<notebook id>' holds that notebook's note ids as a JSON array in content.
  Join with: FROM lists l, json_each(l.content) j JOIN notes n ON n.id = j.value.
- files: id, name, downloadURL.
fold(x) lower-cases any language; SQLite's lower() and LIKE only fold ASCII.
Dates: datetime(updatedAt / 1000, 'unixepoch', 'localtime')."""


def _cell(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + f"… <{len(value) - 2000} more characters; use get_note>"
    return value


@server.tool(annotations=READ)
def run_select(
    sql: Annotated[str, Field(description=_SELECT_HELP)],
    limit: Annotated[int, Field(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    """Run a custom read-only SQL query when the other tools don't cover the question."""
    with closing(_connect()) as conn:
        try:
            cur = conn.execute(sql)
            columns = [c[0] for c in cur.description or []]
            rows = cur.fetchmany(limit + 1)
        except sqlite3.Error as e:
            raise ToolError(f"Query refused or failed: {e}") from e
    return {
        "columns": columns,
        "rows": [{c: _cell(v) for c, v in zip(columns, tuple(row))} for row in rows[:limit]],
        "truncated": len(rows) > limit,
    }


# ---------------------------------------------------------------- create tool

# Verified by creating a note with each construct and viewing it in UpNote 9.22.2.
# The style follows the user's own notes.
_FORMAT_GUIDE = """\
Note body in Markdown. Format it the way the user formats notes - structured and scannable,
not plain paragraphs. The title becomes the note's heading, so don't repeat it.
- Sections: "### Heading". A ticket section starts with its linked key:
  ### [KEY-123](https://tracker/browse/KEY-123) Short summary
- Collapsible section, for long or finished material. Raw HTML; its content must be HTML too:
  <div class="shine-collapsible-section"><div class="shine-section-title-wrapper"><div class="shine-section-title shine-placeholder" data-upnote-placeholder-key="title"><div class="shine-section-title-inner"><h3>Title</h3></div></div></div><div class="shine-section-content shine-placeholder" data-upnote-placeholder-key="content"><div class="shine-section-content-inner"><ul><li>item</li></ul></div></div></div>
- Bullet lists nested with two-space indents; numbered lists for ordered steps.
- Status markers at the start of an item: ✅ done, ❌ closed or dropped (pair with ~~strikethrough~~),
  ➡ current state or next step (as ***➡ In Review***), ⏰ waiting on someone.
- **Bold** for labels such as **The fix:**, *italic* for asides and statuses,
  <u>underline</u> for group labels such as <u>Follow-ups</u>.
- `inline code` for identifiers, paths, roles, commands.
- Code blocks: fence them and put the language right after the opening backticks, such as
  ```json, ```bash, ```java, ```yaml or ```markdown. UpNote stores it as the block's language.
- <span class="shine-highlight-yellow">text</span> marks who or what is blocking; ==text== is a green highlight.
- Links as [text](url); bare URLs also become links. Checkboxes: - [ ] and - [x]. Markdown tables work.
- --- between major parts, > for quotes.
Don't use <mark>; UpNote drops it."""


def _create_url(title: str, text: str, notebook_title: str | None, markdown: bool) -> str:
    params = {"title": title, "text": text, "notebook": notebook_title, "markdown": "true" if markdown else "false"}
    # quote() writes a space as %20. A form encoder would write "+", which a
    # link handler may keep as a literal plus sign.
    return "upnote://x-callback-url/note/new?" + "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items() if v)


def _open_link(url: str, background: bool = True) -> None:
    """Hand an upnote:// link to the app without a shell, in the background unless asked otherwise."""
    try:
        subprocess.run(["open", *(["-g"] if background else []), url], check=True, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        raise ToolError(f"Could not hand the link to UpNote: {e}") from e


def _recent_note_ids(since_ms: float) -> set[str]:
    """Ids of notes created since since_ms. Taken before sending a create link, so an
    earlier note with the same title can't be mistaken for the new one."""
    with closing(_connect()) as conn:
        return {r["id"] for r in conn.execute("SELECT id FROM notes WHERE createdAt >= ?", (since_ms,))}


def _find_created_note(
    since_ms: float, title: str, notebook_path: str | None = None, exclude: set[str] = frozenset()
) -> dict[str, Any] | None:
    """Poll the database for the note UpNote just created.

    Only a note that wasn't in `exclude` and isn't in Trash counts. UpNote saves a note's
    notebook membership a moment after the note itself, so when a notebook was requested,
    keep polling until the note is in it or time runs out.
    """
    deadline = time.monotonic() + CONFIRM_SECONDS
    wanted = _fold(title.strip())
    found = None
    while True:
        with closing(_connect()) as conn:
            rows = conn.execute(
                f"SELECT {_NOTE_COLUMNS} FROM notes WHERE deleted = 0 AND trashed = 0 AND createdAt >= ? "
                "ORDER BY createdAt DESC",
                (since_ms,),
            ).fetchall()
            rows = [r for r in rows if r["id"] not in exclude]
            match = next((r for r in rows if _fold((r["title"] or "").strip()) == wanted), None)
            if match is None and not wanted and len(rows) == 1:
                match = rows[0]
            if match is not None:
                nbs = _notebooks(conn)
                found = _summary(match, nbs, _membership(conn, nbs), None)
                if notebook_path is None or notebook_path in found["notebooks"]:
                    return found
        if time.monotonic() >= deadline:
            return found
        time.sleep(0.5)


@server.tool(annotations=CREATE)
def create_note(
    title: Annotated[str, Field(description="Note title.")],
    text: Annotated[str, Field(description=_FORMAT_GUIDE)] = "",
    notebook: Annotated[str | None, Field(description='Notebook title, path such as "Parent / Child", or id. Omit for UpNote\'s default location.')] = None,
    markdown: bool = True,
) -> dict[str, Any]:
    """Create a new note in UpNote. The app creates it, so it syncs normally. Returns the new note's id once UpNote has saved it."""
    if not title.strip() and not text.strip():
        raise ToolError("Give a title or some text.")
    notebook_id = None
    notebook_title = None
    if notebook:
        with closing(_connect()) as conn:
            nbs = _notebooks(conn)
        notebook_id = _resolve_notebook(nbs, notebook)
        notebook_title = nbs[notebook_id]["title"]

    url = _create_url(title.strip(), text, notebook_title, markdown)

    since_ms = time.time() * 1000 - 2000
    existing = _recent_note_ids(since_ms)
    _open_link(url)

    note = _find_created_note(
        since_ms, title, nbs[notebook_id]["path"] if notebook_id is not None else None, existing
    )
    if note is None:
        return {
            "confirmed": False,
            "message": (
                f"UpNote received the note but it did not appear in the database within {CONFIRM_SECONDS:.0f} "
                "seconds. Do not create it again yet, or it may be duplicated. Search for the title in a minute."
            ),
        }
    result: dict[str, Any] = {"confirmed": True, "note": note}
    if notebook_id is not None:
        result["in_requested_notebook"] = nbs[notebook_id]["path"] in note["notebooks"]
    return result


# ---------------------------------------------------------------- trash tools

NoteId = Annotated[str, Field(description="The note's id, from search_notes, list_notes or get_note.")]


def _set_trashed(note_id: str, trashed: bool) -> dict[str, Any]:
    """Move a note into or out of Trash through UpNote, then wait for the app to save it.

    The routes note/moveToTrash and note/restore are not in UpNote's documentation. They
    are in the app's own link handler, and the app itself builds moveToTrash links. The
    change goes through the app, so it syncs like one made by hand. The id is always
    checked against the database first, so the app only receives ids that exist.
    """
    note_id = note_id.strip()
    with closing(_connect()) as conn:
        before = conn.execute("SELECT title, trashed FROM notes WHERE id = ? AND deleted = 0", (note_id,)).fetchone()
    if before is None:
        raise ToolError(
            f"No note with id {note_id!r}. Find ids with search_notes or list_notes; "
            "for notes already in Trash, pass include_trashed=true."
        )
    if bool(before["trashed"]) == trashed:
        raise ToolError(f"Note {before['title']!r} is {'already' if trashed else 'not'} in Trash.")

    route = "moveToTrash" if trashed else "restore"
    _open_link(f"upnote://x-callback-url/note/{route}?noteId={quote(note_id, safe='')}")

    deadline = time.monotonic() + CONFIRM_SECONDS
    while True:
        with closing(_connect()) as conn:
            r = conn.execute(f"SELECT {_NOTE_COLUMNS} FROM notes WHERE id = ? AND deleted = 0", (note_id,)).fetchone()
            if r is not None and bool(r["trashed"]) == trashed:
                nbs = _notebooks(conn)
                return {"confirmed": True, "note": _summary(r, nbs, _membership(conn, nbs), None)}
        if time.monotonic() >= deadline:
            return {
                "confirmed": False,
                "message": (
                    f"UpNote received the link, but the note's Trash state had not changed after "
                    f"{CONFIRM_SECONDS:.0f} seconds. Check it with get_note before trying again."
                ),
            }
        time.sleep(0.5)


@server.tool(annotations=TRASH)
def move_note_to_trash(note_id: NoteId) -> dict[str, Any]:
    """Move a note to UpNote's Trash. It can be brought back with restore_note until Trash is emptied in the app.
    Confirm which note with the user before calling this."""
    return _set_trashed(note_id, True)


@server.tool(annotations=RESTORE)
def restore_note(note_id: NoteId) -> dict[str, Any]:
    """Move a note out of UpNote's Trash, back where it was. Find trashed notes with list_notes or search_notes and include_trashed=true."""
    return _set_trashed(note_id, False)


# ---------------------------------------------------------------- open tool

@server.tool(annotations=SHOW)
def open_in_upnote(
    note_id: Annotated[str | None, Field(description="Open this note.")] = None,
    notebook: Annotated[str | None, Field(description='Show this notebook: title, path such as "Parent / Child", or id.')] = None,
    tag: Annotated[str | None, Field(description="Show notes with this tag, with or without #.")] = None,
    search: Annotated[str | None, Field(description="Run this search in UpNote's search box.")] = None,
) -> dict[str, Any]:
    """Show a note, notebook, tag or search in the UpNote app and bring the app to the front. Pass exactly one.
    It changes what UpNote displays and takes focus from the user's current app, so use it only when the user
    asks to see something in UpNote. If a search is active in UpNote, a notebook or tag opens inside those
    search results; no link can clear the search box, so tell the user to clear it to see everything."""
    given = {k: v for k, v in {"note_id": note_id, "notebook": notebook, "tag": tag, "search": search}.items() if v and v.strip()}
    if len(given) != 1:
        raise ToolError("Pass exactly one of note_id, notebook, tag or search.")
    (kind, value), = given.items()
    value = value.strip()

    # Every target is checked in the database first, so UpNote only receives ones that exist.
    with closing(_connect()) as conn:
        if kind == "note_id":
            r = conn.execute("SELECT title, trashed FROM notes WHERE id = ? AND deleted = 0", (value,)).fetchone()
            if r is None:
                raise ToolError(f"No note with id {value!r}. Find ids with search_notes or list_notes.")
            url = f"upnote://x-callback-url/openNote?noteId={quote(value, safe='')}"
            shown = {"note": r["title"] or "", **({"trashed": True} if r["trashed"] else {})}
        elif kind == "notebook":
            nbs = _notebooks(conn)
            nb_id = _resolve_notebook(nbs, value)
            url = f"upnote://x-callback-url/openNotebook?notebookId={quote(nb_id, safe='')}"
            shown = {"notebook": nbs[nb_id]["path"]}
        elif kind == "tag":
            key = _tag_key(value)
            titles = [row["title"] for row in conn.execute("SELECT title FROM tags WHERE deleted = 0") if row["title"]]
            match = next((t for t in titles if _tag_key(t) == key), None)
            if match is None:
                raise ToolError(f"No tag {value!r}. Call list_tags to see the tags.")
            url = f"upnote://x-callback-url/tag/view?tag={quote(match.lstrip('#'), safe='')}"
            shown = {"tag": match}
        else:
            url = f"upnote://x-callback-url/view?action=search&query={quote(value, safe='')}"
            shown = {"search": value}

    _open_link(url, background=False)
    return {"sent": True, "showing": shown}


# ---------------------------------------------------------------- replace tool

# A note saved this many times has a long Version History, which belongs to the original.
LONG_HISTORY_REVISIONS = 20
RECENT_EDIT_MINUTES = 10


def _replace_checks(conn: sqlite3.Connection, note_id: str):
    """Return the note, notebooks, its notebook ids, blockers, and warnings for a replace."""
    r = conn.execute(
        "SELECT id, title, html, revision, updatedAt, trashed, pinned, bookmarked, shared, shareId, isTemplate, fileIds "
        "FROM notes WHERE id = ? AND deleted = 0",
        (note_id,),
    ).fetchone()
    if r is None:
        raise ToolError(f"No note with id {note_id!r}. Find ids with search_notes or list_notes.")
    if r["trashed"]:
        raise ToolError(f"Note {r['title']!r} is in Trash. Restore it with restore_note first.")
    body = r["html"] or ""
    nbs = _notebooks(conn)
    notebook_ids = _membership(conn, nbs).get(note_id, [])
    blockers: list[str] = []
    warnings: list[str] = []

    # Blockers: something would really be lost.
    if _json_list(r["fileIds"]) or "<img" in body:
        blockers.append("It has attachments or images, and the new version can only carry text.")
    linking = [
        row["title"] or "untitled"
        for row in conn.execute("SELECT title, noteLinks, html FROM notes WHERE deleted = 0 AND id != ?", (note_id,))
        if note_id in (row["noteLinks"] or "") or note_id in (row["html"] or "")
    ]
    if linking:
        blockers.append(f"Other notes link to it ({', '.join(linking[:5])}), and those links would lead to the trashed original.")
    if r["shared"] or r["shareId"]:
        blockers.append("It is shared by web link, and the link belongs to the original note.")
    if r["isTemplate"]:
        blockers.append("It is a template, and the new version would be an ordinary note.")

    # Warnings: recoverable by hand, or worth checking afterwards.
    bookmarks = conn.execute("SELECT content FROM lists WHERE id = 'bookmarkedNotes'").fetchone()
    if r["pinned"]:
        warnings.append("It is pinned. Pin the new version by hand.")
    if r["bookmarked"] or (bookmarks and note_id in _json_list(bookmarks["content"])):
        warnings.append("It is bookmarked. Bookmark the new version by hand.")
    if len(notebook_ids) > 1:
        others = ", ".join(nbs[i]["path"] for i in notebook_ids[1:])
        warnings.append(f"It is in several notebooks. The new version goes into {nbs[notebook_ids[0]]['path']} only; add it to {others} by hand.")
    if (r["revision"] or 0) >= LONG_HISTORY_REVISIONS:
        warnings.append(f"It has been saved {r['revision']} times. Its Version History will most likely stay with the original in Trash.")
    if "shine-section-collapsed" in body:
        warnings.append("It has collapsed sections. They may open expanded in the new version.")
    if "shine-collapsible-section" in body or len(body) > 20000:
        warnings.append("Its formatting is complex. Compare the new version with the original before emptying Trash.")
    if r["updatedAt"] and time.time() * 1000 - r["updatedAt"] < RECENT_EDIT_MINUTES * 60000:
        warnings.append(f"It was edited in the last {RECENT_EDIT_MINUTES} minutes. If someone is typing in it, those changes stay in the original.")
    return r, nbs, notebook_ids, blockers, warnings


def _strip_title_heading(text: str, *titles: str) -> str:
    """Drop a leading <h2> title, as in get_note's html, since UpNote adds the title itself."""
    m = re.match(r"\s*<h2>(.*?)</h2>\s*", text, re.S)
    if m:
        heading = _fold(html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip())
        if heading in {_fold(t.strip()) for t in titles if t}:
            return text[m.end():]
    return text


@server.tool(annotations=REPLACE)
def replace_note(
    note_id: NoteId,
    text: Annotated[str, Field(description=(
        "The complete new body, not a list of changes. To keep existing formatting, start from get_note "
        "with format=\"html\" and change only what's needed; a leading <h2> title heading is removed "
        "automatically. New content follows the same rules as create_note's text."
    ))],
    title: Annotated[str | None, Field(description="New title. Omit to keep the current one.")] = None,
    expected_revision: Annotated[int | None, Field(description="Omit to preview. To replace, pass the revision the preview returned.")] = None,
    acknowledge_warnings: Annotated[bool, Field(description="Set true only after the user has seen and accepted the preview's warnings.")] = False,
    markdown: bool = True,
) -> dict[str, Any]:
    """Edit a note by replacing it, since UpNote can't change a note in place. The new version gets a new id.
    Step 1: call without expected_revision. Nothing changes; the result gives the note's revision and any warnings.
    Show the warnings to the user. Step 2: call again with expected_revision and, if there were warnings,
    acknowledge_warnings=true. The new version is created first. The original goes to Trash only after that
    succeeds and only if nobody changed it meanwhile, so it stays recoverable with restore_note."""
    note_id = note_id.strip()
    with closing(_connect()) as conn:
        r, nbs, notebook_ids, blockers, warnings = _replace_checks(conn, note_id)
    if blockers:
        raise ToolError(f"Can't replace {r['title']!r}. " + " ".join(blockers))
    if expected_revision is None:
        return {
            "stage": "preview",
            "note_id": note_id,
            "title": r["title"],
            "revision": r["revision"],
            "notebook": nbs[notebook_ids[0]]["path"] if notebook_ids else None,
            "warnings": warnings,
            "next_step": "Show any warnings to the user, then call again with expected_revision"
            + (" and acknowledge_warnings=true." if warnings else "."),
        }
    if expected_revision != r["revision"]:
        raise ToolError(
            f"The note changed since the preview: revision {expected_revision} is now {r['revision']}. "
            "Read it again with get_note and preview again."
        )
    if warnings and not acknowledge_warnings:
        raise ToolError("The preview's warnings haven't been accepted: " + " ".join(warnings))

    new_title = (r["title"] if title is None else title).strip() if (r["title"] or title) else ""
    body = _strip_title_heading(text, r["title"] or "", new_title)
    if not new_title and not body.strip():
        raise ToolError("Give a title or some text.")
    notebook_title = nbs[notebook_ids[0]]["title"] if notebook_ids else None

    since_ms = time.time() * 1000 - 2000
    existing = _recent_note_ids(since_ms)
    _open_link(_create_url(new_title, body, notebook_title, markdown))
    notebook_path = nbs[notebook_ids[0]]["path"] if notebook_ids else None
    new_note = _find_created_note(since_ms, new_title, notebook_path, existing)
    if new_note is None:
        return {
            "done": False,
            "message": (
                f"The new version didn't appear within {CONFIRM_SECONDS:.0f} seconds, so the original was left "
                "unchanged. Search for the title before trying again, so there's no duplicate."
            ),
        }

    if notebook_path is not None and notebook_path not in new_note["notebooks"]:
        return {
            "done": False,
            "new_note": new_note,
            "message": (
                f"The new version was created but hadn't appeared in {notebook_path} after {CONFIRM_SECONDS:.0f} "
                "seconds, so the original was left in place. Check the new note's notebook in UpNote, then move "
                "one of the two to Trash with move_note_to_trash."
            ),
        }

    with closing(_connect()) as conn:
        now = conn.execute("SELECT revision, trashed FROM notes WHERE id = ? AND deleted = 0", (note_id,)).fetchone()
    if now is None or now["revision"] != expected_revision or now["trashed"]:
        return {
            "done": False,
            "new_note": new_note,
            "message": (
                "The new version was created, but the original changed while that happened, so the original "
                "was left in place. Compare the two and move one to Trash with move_note_to_trash."
            ),
        }

    trash = _set_trashed(note_id, True)
    result: dict[str, Any] = {
        "done": bool(trash.get("confirmed")),
        "new_note": new_note,
        "original_note_id": note_id,
        "original_in_trash": bool(trash.get("confirmed")),
    }
    if notebook_path is not None:
        result["in_original_notebook"] = True
    if warnings:
        result["follow_up"] = warnings
    if not trash.get("confirmed"):
        result["message"] = "The new version exists, but the original wasn't confirmed in Trash. Check it with get_note."
    return result


if __name__ == "__main__":
    server.run()
