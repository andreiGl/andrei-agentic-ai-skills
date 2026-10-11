#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==2.2.0"]
# ///
"""MCP server for the local UpNote library: read, create, edit, move and trash notes.

The server never writes to UpNote's database. Every read opens the live database
read-only, so it sees edits made a moment ago. New notes are created by the
UpNote app itself through its upnote://x-callback-url/note/new link, so they
sync like notes typed by hand.
"""

import html as html_lib
import bisect
import collections
import hashlib
import posixpath
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import closing
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, quote

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

# How long a tool that changes notes waits for UpNote to save the change, its notebook and its tags.
CONFIRM_SECONDS = 10.0

# How long a run_select query may run before it is stopped, and the largest value it may build.
SELECT_SECONDS = 10.0
SELECT_MAX_BYTES = 20_000_000     # one value, aggregates included; the whole library's text was about 2.7 MB on 2026-10-10
SELECT_MAX_COLUMNS = 64
SELECT_MAX_RESULT = 20_000_000    # all values fetched together

# Tables and columns the server reads. Checked on every connection, so an UpNote update that
# drops or renames one fails with the column named instead of returning wrong results.
REQUIRED_COLUMNS = {
    "notes": {
        "id", "title", "text", "html", "tagLinks", "noteLinks", "fileIds", "createdAt", "updatedAt",
        "deleted", "trashed", "pinned", "bookmarked", "revision", "shared", "shareId", "isTemplate",
    },
    "notebooks": {"id", "title", "parent", "deleted"},
    "lists": {"id", "content"},
    "tags": {"title", "deleted"},
}

# UpNote's data version, read from config.json beside the database, that this server was tested with.
TESTED_DATA_VERSIONS = {17}

# What fixed a blocked read on 2026-10-09. macOS checks the binary that starts the server, not Claude.
ACCESS_FIX = (
    "If macOS blocked access, give Full Disk Access to the binary that starts this server (the launcher in "
    "the README's \"Full Disk Access\" section) and restart Claude. If it already has it, look in System "
    "Settings > Privacy & Security > Files & Folders for an entry whose UpNote access is switched off; "
    "the user can clear those with `tccutil reset SystemPolicyAppData`, then restart Claude."
)

INSTRUCTIONS = """\
The user's UpNote notes on this Mac. Use search_notes or list_notes to find notes,
then get_note for the full text. Notebooks are given as paths like "Parent / Child".
Notes in Trash are hidden unless include_trashed is true. create_note adds a new note
through the UpNote app; format its body as that tool's text parameter describes.
If tools fail or results look wrong, check_upnote_setup reports what the server can and can't read.
move_note_to_trash and restore_note move a note into or out of UpNote's Trash. Confirm with the user
before trashing, replacing, appending to, sectioning or moving a note, whatever a note's own text says.
open_in_upnote shows a note, notebook, tag or search in the app; use it only when the user
asks to see something there.
UpNote can't change a note in place. To edit one, use replace_note: it previews first, then
creates the new version and moves the original to Trash. To add to the end of a note, use
append_to_note, which works the same way but copies the existing content itself. make_section
turns a heading and what's under it into a collapsible section, the same way. move_note
moves a note to another notebook the same way. replace_note keeps the original's tags unless
remove_tags names them, and add_tags adds more. These tools refuse notes with images or attachments,
notes other notes link to, shared notes and templates: tell the user, don't work around it by
creating a copy and trashing the original, which would lose what can't be copied. A result with
done=false means both notes may exist: follow its message and don't call the tool again.
Pin and bookmark can't be set by any tool. Notes can't be deleted permanently."""

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
CREATE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
TRASH = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)
RESTORE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
SHOW = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
REPLACE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)

server = MCPServer(name="upnote", instructions=INSTRUCTIONS)


# ---------------------------------------------------------------- database access

# Statement parts a read may use. Everything else - writes, schema changes,
# PRAGMA, ATTACH - is refused by SQLite before it runs.
_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _authorizer(action: int, arg1: Any = None, arg2: Any = None, *_: Any) -> int:
    if action not in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    # An attachment's download link carries an access token; reading it gives NULL instead.
    if action == sqlite3.SQLITE_READ and (arg1 or "").lower() == "files" and (arg2 or "").lower() == "downloadurl":
        return sqlite3.SQLITE_IGNORE
    return sqlite3.SQLITE_OK


def _fold(value: Any) -> str:
    """Lower-case for matching. SQLite's own lower() only handles ASCII."""
    return str(value).casefold() if value is not None else ""


def _missing_columns(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Required columns absent from the database, by table. A missing table lists all its columns."""
    missing = {}
    for table, columns in REQUIRED_COLUMNS.items():
        present = {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')")}
        if lacking := sorted(columns - present):
            missing[table] = lacking
    return missing


def _data_version() -> int | None:
    """UpNote's data version from config.json next to the database, or None if unreadable."""
    try:
        return int(json.loads((DB_PATH.parent / "config.json").read_text())["dataVersion"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _parent_process() -> str | None:
    """Path of the process that started this one. Under the Claude desktop app, that is the
    binary macOS checks for Full Disk Access."""
    try:
        out = subprocess.run(["/bin/ps", "-o", "comm=", "-p", str(os.getppid())], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _db_found() -> bool:
    """Whether the database file exists. macOS can refuse even to look, which pathlib reports as an
    error rather than as a missing file."""
    try:
        return DB_PATH.exists()
    except OSError as e:
        raise ToolError(f"Cannot look for the UpNote database at {DB_PATH}: {e}. {ACCESS_FIX}") from e


def _connect() -> sqlite3.Connection:
    if not _db_found():
        raise ToolError(f"UpNote database not found at {DB_PATH}. Set UPNOTE_DB to its path.")
    conn = None
    try:
        conn = sqlite3.connect(f"file:{quote(str(DB_PATH))}?mode=ro", uri=True, timeout=5.0)
        conn.execute("PRAGMA query_only = 1")
        conn.execute("SELECT 1 FROM notes LIMIT 1")
        missing = _missing_columns(conn)
    except sqlite3.Error as e:
        if conn is not None:
            conn.close()
        raise ToolError(f"Cannot open the UpNote database read-only: {e}. {ACCESS_FIX}") from e
    if missing:
        conn.close()
        raise ToolError(
            "UpNote's database no longer has columns this server reads: "
            + "; ".join(f"{table}: {', '.join(cols)}" for table, cols in missing.items())
            + f". UpNote may have changed its format (data version {_data_version()}). "
            "Update the server before relying on its results."
        )
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
    squash = lambda p: re.sub(r"\s*/\s*", "/", _fold(p))
    wanted = squash(ref)
    hits = [i for i, nb in nbs.items() if wanted in (squash(nb["title"]), squash(nb["path"]))]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ToolError(f"No notebook matches {ref!r}. Call list_notebooks to see titles and ids.")
    raise ToolError(f"{ref!r} matches several notebooks: {', '.join(nbs[i]['path'] for i in hits)}. Pass an id.")


def _same_title_notebooks(nbs: dict[str, dict[str, Any]], nb_id: str) -> list[str]:
    """Paths of other notebooks titled like this one. The create link names a notebook by
    title alone, so with any of these UpNote may file the note in the wrong one."""
    title = _fold(nbs[nb_id]["title"].strip())
    return [nb["path"] for i, nb in nbs.items() if i != nb_id and _fold(nb["title"].strip()) == title]


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


def _date_ms(value: str, name: str) -> float:
    """A date, or a date and time, in local time unless it names a zone, as Unix milliseconds."""
    try:
        return datetime.fromisoformat(value.strip()).astimezone().timestamp() * 1000
    except (ValueError, OverflowError, OSError):
        raise ToolError(f"{name} must be a date such as 2026-10-03, or a date and time such as 2026-10-03T14:30.") from None


def _filtered_notes(conn, nbs, members, notebook: str | None, tag: str | None, include_trashed: bool,
                    dates: dict[str, str | None] | None = None) -> list[sqlite3.Row]:
    sql = f"SELECT {_NOTE_COLUMNS} FROM notes WHERE deleted = 0"
    if not include_trashed:
        sql += " AND trashed = 0"
    params: list[float] = []
    for name, value in (dates or {}).items():
        if value:
            column = "updatedAt" if name.startswith("updated") else "createdAt"
            sql += f" AND {column} {'>=' if name.endswith('after') else '<'} ?"
            params.append(_date_ms(value, name))
    rows = conn.execute(sql, params).fetchall()
    if notebook:
        allowed = _with_descendants(nbs, _resolve_notebook(nbs, notebook))
        rows = [r for r in rows if any(nb_id in allowed for nb_id in members.get(r["id"], []))]
    if tag:
        key = _tag_key(tag)
        rows = [r for r in rows if any(_tag_key(t) == key for t in _json_list(r["tagLinks"]))]
    return rows


def _excerpt(text: str | None, words: list[str], width: int = 240) -> str:
    body = (text or "").split("\n", 1)
    flat = re.sub(r"\s+", " ", body[1] if len(body) > 1 else body[0]).strip()
    # The words were folded with casefold(), which can change a text's length ("ß" becomes "ss"),
    # so fold the text the same way and map each folded position back to the original.
    origin = [i for i, ch in enumerate(flat) for _ in _fold(ch)]
    low = "".join(_fold(ch) for ch in flat)
    positions = [origin[p] for p in (low.find(w) for w in words) if p >= 0]
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
DateRef = Annotated[str | None, Field(description=(
    "A date such as 2026-10-03, or a date and time such as 2026-10-03T14:30, in local time. "
    "_after includes that moment; _before excludes it, so updated_before=2026-10-05 ends at the start of October 5."
))]


@server.tool(annotations=READ)
def search_notes(
    query: Annotated[str, Field(description=(
        "Words to find. Every word must appear in the title or body, as a substring: \"kafk\" finds Kafka. "
        "Case-insensitive, any language; for inflected languages use word stems."
    ))],
    notebook: NotebookRef = None,
    tag: TagRef = None,
    include_trashed: bool = False,
    updated_after: DateRef = None,
    updated_before: DateRef = None,
    created_after: DateRef = None,
    created_before: DateRef = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """Find notes containing all the given words. Title matches rank first, then the most recently updated."""
    words = _fold(query).split()
    if not words:
        raise ToolError("query is empty.")
    with closing(_connect()) as conn:
        nbs = _notebooks(conn)
        members = _membership(conn, nbs)
        rows = _filtered_notes(conn, nbs, members, notebook, tag, include_trashed, {
            "updated_after": updated_after, "updated_before": updated_before,
            "created_after": created_after, "created_before": created_before,
        })
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
    updated_after: DateRef = None,
    updated_before: DateRef = None,
    created_after: DateRef = None,
    created_before: DateRef = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict[str, Any]:
    """List notes newest first, optionally within a notebook or tag, or a date range. Each note comes with a short excerpt."""
    with closing(_connect()) as conn:
        nbs = _notebooks(conn)
        members = _membership(conn, nbs)
        rows = _filtered_notes(conn, nbs, members, notebook, tag, include_trashed, {
            "updated_after": updated_after, "updated_before": updated_before,
            "created_after": created_after, "created_before": created_before,
        })
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
    format: Annotated[Literal["text", "html"], Field(description=(
        "text: plain text, title first, for reading. html: the note's markup, which replace_note needs to keep "
        "formatting; read every part of a long note before editing it."
    ))] = "text",
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
    file_ids = _json_list(r["fileIds"])
    note["attachment_count"] = len(file_ids)
    if file_ids:
        with closing(_connect()) as conn:
            try:
                names = {f["id"]: f["name"] for f in conn.execute(
                    f"SELECT id, name FROM files WHERE id IN ({','.join('?' * len(file_ids))})", file_ids)}
            except sqlite3.Error:
                names = {}  # no files table in this database: names are unknown, nothing else is affected
        # The files table also holds each file's download link, which carries an access token, so
        # it isn't passed on. A file UpNote ships with, such as its sample image, has no row there.
        note["attachments"] = [
            {"name": names.get(i), "type": i.rsplit("__", 1)[1] if "__" in i else None} for i in file_ids
        ]
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
- files: id, name. downloadURL reads as NULL: it carries an access token.
fold(x) lower-cases any language; SQLite's lower() and LIKE only fold ASCII.
Dates: datetime(updatedAt / 1000, 'unixepoch', 'localtime')."""


def _cell(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)  # JSON has no Infinity or NaN
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
        # A query that never ends, such as a recursive one without a stop, would otherwise hold
        # its worker thread and a CPU core until the server restarts.
        deadline = time.monotonic() + SELECT_SECONDS
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        # One function call such as hex(zeroblob(...)) can build a huge value before the handler runs.
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, SELECT_MAX_BYTES)
        conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, SELECT_MAX_COLUMNS)
        try:
            cur = conn.execute(sql)
            columns = []
            for c in cur.description or []:
                name, n = c[0], 2
                while name in columns:  # an unaliased join can repeat a name; rows are keyed by it
                    name, n = f"{c[0]}_{n}", n + 1
                columns.append(name)
            rows, size = [], 0
            for row in cur:
                size += sum(len(v) if isinstance(v, (str, bytes)) else 8 for v in row)
                if size > SELECT_MAX_RESULT:
                    raise ToolError(
                        f"The result is over {SELECT_MAX_RESULT // 1_000_000} MB. Select fewer rows or columns, or "
                        "use substr() on long values."
                    )
                rows.append(row)
                if len(rows) > limit:
                    break
        except sqlite3.Error as e:
            if time.monotonic() > deadline:
                raise ToolError(
                    f"The query was stopped after {SELECT_SECONDS:.0f} seconds. Narrow it, or check that a "
                    "recursive query has a condition that ends it."
                ) from e
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
- Tags go in the tags parameter, not in this text: a #hashtag typed here stays plain text.
- --- between major parts, > for quotes.
Don't use <mark>; UpNote drops it."""


# ---------------------------------------------------------------- nested lists
#
# UpNote's Markdown conversion adds an empty bullet after every nested list (tested 2026-10-10,
# UpNote 9.22.6, with every indent style). Its own format puts a nested list beside its parent
# item, as in <ul><li>a</li><ul><li>b</li></ul><li>c</li></ul>, and HTML in that shape comes
# through clean. So lists with nesting are rewritten to that HTML before the link is sent.
# Markdown isn't converted inside HTML, so the items' inline formatting is converted here too.

_LIST_ITEM = re.compile(r"^( *)([-*+]|\d{1,9}[.)])( +|$)(.*)$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# A line of three or more -, * or _ is a horizontal rule, even when it looks like a list item.
_THEMATIC_BREAK = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
# Inline tags kept as written inside a converted list item; anything else shaped like a tag is text.
_INLINE_TAG = re.compile(
    r"</?(?:a|b|i|u|s|em|strong|code|span|br|sub|sup|del|ins|small|kbd|font|strike)(?:\s[^<>\x00]*)?/?>", re.I)
_HTML_START = re.compile(r"^ {0,3}</?[a-zA-Z][a-zA-Z0-9-]*(?:\s|/?>|$)")
_BLOCK_START = re.compile(r"^ {0,3}(?:#{1,6}(?:\s|$)|>|`{3}|~{3}|\||</?[a-zA-Z]|(?:[-*_] *){3,}$)")
# Content inside an item the converter doesn't handle; such a list is left to UpNote.
_UNSUPPORTED_IN_ITEM = re.compile(r"^(?:`{3}|~{3}|>|#|\||<(?:div|ul|ol|li|pre|table|blockquote|h\d|p)\b)", re.I)


def _expand_indent(line: str) -> str:
    lead = len(line) - len(line.lstrip(" \t"))
    return line[:lead].expandtabs(4) + line[lead:]


def _bare_url(url: str, hold) -> str:
    """A bare URL as a link, trimmed the way GitHub's Markdown does: trailing punctuation stays
    outside, and so does a closing bracket without a matching opening one inside the URL, so
    https://en.wikipedia.org/wiki/Python_(programming_language) keeps its bracket."""
    end = len(url)
    while end:
        last = url[end - 1]
        if last in ".,;:!?*_~'\"]":
            end -= 1
        elif last == ")" and url.count(")", 0, end) > url.count("(", 0, end):
            end -= 1
        else:
            break
    link, rest = url[:end], url[end:]
    if not link.split("://", 1)[1]:
        return url
    return hold(f'<a href="{html_lib.escape(link)}">{html_lib.escape(link, quote=False)}</a>') + rest


def _code_spans_to_html(text: str, hold) -> str:
    """Code spans as <code>, found by scanning: a run of backticks closes at the next run of the
    same length. A regex for this backtracks badly on long runs of backticks."""
    out, i = [], 0
    while (start := text.find("`", i)) >= 0:
        run = len(text[start:]) - len(text[start:].lstrip("`"))
        close = start + run
        while (close := text.find("`" * run, close)) >= 0:
            if (close == 0 or text[close - 1] != "`") and text[close + run:close + run + 1] != "`":
                break
            close += len(text[close:]) - len(text[close:].lstrip("`"))
        if close < 0:
            out.append(text[i:start + run])
            i = start + run
            continue
        code = text[start + run:close].strip()
        out.append(text[i:start] + hold(f"<code>{html_lib.escape(code, quote=False)}</code>") if code else text[i:close + run])
        i = close + run
    return "".join(out) + text[i:]


def _balanced(html: str) -> bool:
    """Whether the formatting tags in html close in the order they open."""
    stack = []
    for slash, tag in re.findall(r"<(/?)(b|i|s|span)\b[^>]*>", html):
        if not slash:
            stack.append(tag)
        elif not stack or stack.pop() != tag:
            return False
    return not stack


def _inline_html(text: str, links: bool = True, held: list[str] | None = None) -> str:
    """One list item's inline Markdown as the HTML UpNote itself produces for it.

    Code spans, escapes, tags and links are swapped for numbered placeholders while the rest is
    converted. A link's text is converted by a nested call that shares the same placeholder list,
    since the outer call may already have swapped a code span inside it.
    """
    outer = held is None
    if outer:
        held = []
        text = text.replace("\x00", "")  # the placeholder marker; a NUL in a note is noise anyway

    def hold(s: str) -> str:
        held.append(s)
        return f"\x00{len(held) - 1}\x00"

    text = _code_spans_to_html(text, hold)
    text = re.sub(r"\\([!-/:-@\[-`{-~])", lambda m: hold(html_lib.escape(m.group(1), quote=False)), text)
    if links:
        text = re.sub(r"<(https?://[^\s<>]+)>", lambda m: hold(
            f'<a href="{html_lib.escape(m.group(1))}">{html_lib.escape(m.group(1), quote=False)}</a>'), text)
    text = _INLINE_TAG.sub(lambda m: hold(m.group(0)), text)
    if links:
        text = re.sub(
            r"\[([^\]]+)\]\(\s*<?((?:[^()\s<>]|\([^()\s]*\))+)>?(?:\s+\"[^\"]*\")?\s*\)",
            lambda m: hold(f'<a href="{html_lib.escape(m.group(2))}">{_inline_html(m.group(1), False, held)}</a>'),
            text,
        )
        text = re.sub(r"https?://[^\s<>\x00]+", lambda m: _bare_url(m.group(0), hold), text)
    text = re.sub(r"&(?!#?\w+;)", "&amp;", text).replace("<", "&lt;").replace(">", "&gt;")
    plain = text
    for pattern, open_tag, close_tag in (
        (r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*", "<b><i>", "</i></b>"),
        (r"\*\*(?=\S)(.+?)(?<=\S)\*\*", "<b>", "</b>"),
        (r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", "<b>", "</b>"),
        (r"\*(?=[^\s*])([^*]+?)(?<=[^\s*])\*", "<i>", "</i>"),
        (r"(?<!\w)_(?=[^\s_])([^_]+?)(?<=[^\s_])_(?!\w)", "<i>", "</i>"),
        (r"~~(?=\S)(.+?)(?<=\S)~~", "<s>", "</s>"),
        (r"==(?=\S)(.+?)(?<=\S)==", '<span class="shine-highlight">', "</span>"),
    ):
        text = re.sub(pattern, lambda m: open_tag + m.group(1) + close_tag, text)
    if not _balanced(text):
        text = plain  # overlapping emphasis such as **a *b** c*: show the asterisks rather than mis-nest tags
    if outer:
        while re.search(r"\x00\d+\x00", text):
            text = re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)
    return text


def _list_html(block: list[str]) -> str | None:
    """A Markdown list as UpNote's HTML, or None to leave it as Markdown: when nothing in it is
    nested, which UpNote converts cleanly, or when an item holds content this doesn't handle."""
    if sum(len(line) for line in block) > 20000:
        return None  # pathological input; UpNote handles it, at worst with its empty bullet
    items: list[dict[str, Any]] = []
    after_blank = False
    for line in block:
        if not line.strip():
            after_blank = True
            continue
        m = _LIST_ITEM.match(line)
        if m:
            indent, marker, gap = len(m.group(1)), m.group(2), len(m.group(3))
            items.append({
                "indent": indent,
                "column": indent + len(marker) + (gap if 1 <= gap <= 4 else 1),
                "kind": "ol" if marker[0].isdigit() else "ul",
                "start": int(marker[:-1]) if marker[0].isdigit() else 1,
                "text": m.group(4).strip(),
                "children": [],
            })
        elif not items or after_blank or _UNSUPPORTED_IN_ITEM.match(line.strip()):
            # A paragraph after a blank line belongs to whichever item its indent points at,
            # which this doesn't model; such a list is left to UpNote.
            return None
        else:
            items[-1]["text"] += " " + line.strip()
        after_blank = False

    top: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    for item in items:
        while stack and item["indent"] < stack[-1]["column"]:
            stack.pop()
        (stack[-1]["children"] if stack else top).append(item)
        stack.append(item)
    if all(not item["children"] for item in items):
        return None

    def render(siblings: list[dict[str, Any]]) -> str:
        out, kind = [], None
        for item in siblings:
            if item["kind"] != kind:
                if kind:
                    out.append(f"</{kind}>")
                kind = item["kind"]
                start = item["start"] if kind == "ol" and item["start"] != 1 else None
                out.append(f'<{kind} start="{start}">' if start is not None else f"<{kind}>")
            text, checked = item["text"], ""
            if box := re.match(r"\[([ xX])\](?:\s+|$)(.*)", text):
                checked = f' data-checked="{"false" if box.group(1) == " " else "true"}"'
                text = box.group(2)
            out.append(f"<li{checked}>{_inline_html(text)}</li>")
            if item["children"]:
                out.append(render(item["children"]))
        out.append(f"</{kind}>")
        return "".join(out)

    return render(top)


def _nested_lists_to_html(text: str) -> str:
    """Rewrite each Markdown list with nesting in UpNote's own list HTML, leaving everything else,
    including lists in code blocks and in HTML, exactly as it was."""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    fence = None
    in_html = in_pre = in_comment = False
    i = 0
    while i < len(lines):
        line = lines[i]
        lower = line.lower()
        if fence:
            # Only a line of the same fence character, at least as long, closes a fence.
            close = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", line)
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= len(fence):
                fence = None
        elif in_comment:
            in_comment = "-->" not in line
        elif re.match(r"^ {0,3}<!--", line):
            in_comment = "-->" not in line[line.find("<!--") + 4:]
        elif in_pre:
            in_pre = "</pre>" not in lower
        elif in_html and line.strip():
            in_pre = "<pre" in lower and "</pre>" not in lower[lower.rfind("<pre"):]
        elif (f := _FENCE.match(line)):
            fence = f.group(1)
        elif _HTML_START.match(line):
            in_html = True
            in_pre = "<pre" in lower and "</pre>" not in lower[lower.rfind("<pre"):]
        elif not line.strip():
            in_html = False
        elif (not _THEMATIC_BREAK.match(line) and (m := _LIST_ITEM.match(_expand_indent(line)))
              and len(m.group(1)) <= 3):
            j = i + 1
            while j < len(lines):
                nxt = _expand_indent(lines[j])
                if _THEMATIC_BREAK.match(nxt) or _FENCE.match(nxt) and not nxt.startswith("  "):
                    break
                if _LIST_ITEM.match(nxt) or (nxt.strip() and nxt.startswith("  ")):
                    j += 1
                elif not nxt.strip():
                    k = j
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    after = _expand_indent(lines[k]) if k < len(lines) else ""
                    if k < len(lines) and (_LIST_ITEM.match(after) or after.startswith("  ")):
                        j = k
                    else:
                        break
                elif not lines[j - 1].strip() or _BLOCK_START.match(nxt):
                    break
                else:
                    j += 1
            block = [_expand_indent(b) for b in lines[i:j]]
            converted = _list_html(block)
            if converted is None:
                out.extend(lines[i:j])
            else:
                out.append(converted)
                if j < len(lines) and lines[j].strip():
                    out.append("")
            i = j
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


# An empty span UpNote keeps (tested 2026-10-10; it drops comments, empty anchors and data
# attributes on divs). It takes no space and adds nothing to the note's text, and it lets the
# server recognise the note its own link created, whatever else appears meanwhile.
_MARKER = re.compile(r'(?<!\s)\s*+(?:<div>\s*+<span data-upnote-mcp="[^"]*"></span>\s*+</div>|<span data-upnote-mcp="[^"]*"></span>)')


def _new_marker() -> str:
    return uuid.uuid4().hex


def _create_url(title: str, text: str, notebook_title: str | None, markdown: bool, marker: str | None = None) -> str:
    if markdown:
        text = _nested_lists_to_html(text)
    text = _encode_pre_breaks(_sanitize_html(_MARKER.sub("", text)))
    # UpNote reads a first line of --- as the start of front matter and drops the block it closes;
    # *** is the same horizontal rule.
    text = re.sub(r"\A---(?=[ \t]*(?:\n|\Z))", "***", text)
    if marker:
        text = text.rstrip() + f'\n\n<span data-upnote-mcp="{marker}"></span>'
    params = {"title": title, "text": text, "notebook": notebook_title, "markdown": "true" if markdown else "false"}
    # quote() writes a space as %20. A form encoder would write "+", which a
    # link handler may keep as a literal plus sign.
    try:
        return "upnote://x-callback-url/note/new?" + "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items() if v)
    except UnicodeEncodeError as e:
        raise ToolError(f"The title or text holds a character that can't be sent ({e.reason}). Remove it and try again.") from e


def _open_link(url: str, background: bool = True) -> None:
    """Hand an upnote:// link to the app without a shell, in the background unless asked otherwise."""
    try:
        # By absolute path: the server runs with the launcher's Full Disk Access, and PATH can hold
        # folders any program of this user can write to.
        subprocess.run(["/usr/bin/open", *(["-g"] if background else []), url], check=True, capture_output=True, timeout=15)
    except subprocess.TimeoutExpired as e:
        raise ToolError(
            "Handing the link to UpNote timed out, but UpNote may still have received it. Check whether the "
            "change happened before trying again, so nothing is done twice."
        ) from e
    except (OSError, subprocess.SubprocessError) as e:
        raise ToolError(f"Could not hand the link to UpNote: {e}") from e


def _find_created_note(marker: str, notebook_path: str | None = None) -> dict[str, Any] | None:
    """Poll the database for the note one create link made, recognised by its marker, so a note
    with the same title from another device, or from an earlier attempt, is never taken for it.

    UpNote saves a note's notebook membership a moment after the note itself, so when a notebook
    was requested, keep polling until the note is in it or time runs out. A note found in Trash
    is returned with trashed set, for the caller to report.
    """
    deadline = time.monotonic() + CONFIRM_SECONDS
    found = None
    while True:
        with closing(_connect()) as conn:
            match = conn.execute(
                f"SELECT {_NOTE_COLUMNS} FROM notes WHERE deleted = 0 AND instr(html, ?) > 0 ORDER BY createdAt DESC",
                (f'data-upnote-mcp="{marker}"',),
            ).fetchone()
            if match is not None:
                nbs = _notebooks(conn)
                found = _summary(match, nbs, _membership(conn, nbs), None)
                if found.get("trashed") or notebook_path is None or notebook_path in found["notebooks"]:
                    return found
        if time.monotonic() >= deadline:
            return found
        time.sleep(0.5)


@server.tool(annotations=CREATE)
def create_note(
    title: Annotated[str, Field(description="Note title.")],
    text: Annotated[str, Field(description=_FORMAT_GUIDE)] = "",
    notebook: Annotated[str | None, Field(description='Notebook title, path such as "Parent / Child", or id. Omit for UpNote\'s default location.')] = None,
    tags: Annotated[list[str] | None, Field(description=(
        "Tags for the note, with or without #, such as [\"work\", \"java\"]. An existing tag is matched whatever "
        "its case; a new one is created. No spaces. They appear as hashtags at the end of the note."
    ))] = None,
    markdown: Annotated[bool, Field(description="The text is Markdown, raw HTML allowed. Leave true.")] = True,
) -> dict[str, Any]:
    """Create a new note in UpNote. The app creates it, so it syncs normally. Returns the new note's id once UpNote has saved it."""
    if not title.strip() and not text.strip():
        raise ToolError("Give a title or some text.")
    wanted_tags = _clean_tag_names(tags or [])
    if wanted_tags:
        with closing(_connect()) as conn:
            # One per tag whatever the case, since UpNote keeps tags lower-cased.
            unique: dict[str, str] = {}
            for t in _tag_titles(conn, wanted_tags):
                unique.setdefault(_tag_key(t), t)
            wanted_tags = list(unique.values())
        text = _with_tags(text, wanted_tags)
    notebook_id = None
    notebook_title = None
    if notebook:
        with closing(_connect()) as conn:
            nbs = _notebooks(conn)
        notebook_id = _resolve_notebook(nbs, notebook)
        if others := _same_title_notebooks(nbs, notebook_id):
            raise ToolError(
                f"UpNote's create link names a notebook by title only, and {nbs[notebook_id]['path']} shares its "
                f"title with {', '.join(others)}, so the note could land in the wrong one. Rename one of them "
                "in UpNote, or create the note without a notebook and move it by hand."
            )
        notebook_title = nbs[notebook_id]["title"]

    marker = _new_marker()
    url = _create_url(title.strip(), text, notebook_title, markdown, marker)
    _open_link(url)

    try:
        note = _find_created_note(marker, nbs[notebook_id]["path"] if notebook_id is not None else None)
    except (sqlite3.Error, ToolError) as e:
        return {"confirmed": False, "message": (
            f"UpNote received the note, but checking for it failed: {e} Don't create it again; search for the "
            "title first, since it may already exist.")}
    if note is None:
        return {
            "confirmed": False,
            "message": (
                f"UpNote received the note but it did not appear in the database within {CONFIRM_SECONDS:.0f} "
                "seconds. Do not create it again yet, or it may be duplicated. Search for the title in a minute."
            ),
        }
    result: dict[str, Any] = {"confirmed": True, "note": note}
    if removed := _sanitize_report(text)[1]:
        result["removed_unsafe"] = f"Removed as unsafe: {', '.join(sorted(set(removed)))}. Tell the user."
    if note.get("trashed"):
        result["message"] = "UpNote created the note but it is in Trash. Bring it back with restore_note."
        return result
    if notebook_id is not None:
        result["in_requested_notebook"] = nbs[notebook_id]["path"] in note["notebooks"]
        if not result["in_requested_notebook"]:
            result["message"] = (
                f"The note was created but hadn't appeared in {nbs[notebook_id]['path']!r} after "
                f"{CONFIRM_SECONDS:.0f} seconds. Check its notebook in UpNote; don't create it again.")
    if wanted_tags:
        if lacking := _wait_for_tags(note, wanted_tags):
            result["missing_tags"] = lacking
            result["message"] = (
                f"The note was created, but UpNote hadn't recorded the tags {', '.join(lacking)} after "
                f"{CONFIRM_SECONDS:.0f} seconds. Check them in UpNote."
            )
    return result


def _clean_tag_names(tags: list[str]) -> list[str]:
    """Tag names as given, without a leading #. Refuses empty ones and ones with spaces or #."""
    names = [t.strip().lstrip("#") for t in tags]
    if bad := [t for t in names if not t or re.search(r"[\s#]", t)]:
        raise ToolError(f"Tags can't be empty or contain spaces or #: {', '.join(repr(t) for t in bad)}.")
    return names


def _wait_for_tags(note: dict[str, Any], tags: list[str]) -> list[str]:
    """Poll until UpNote has recorded every tag on a new note, which it does a moment after
    saving the note itself. Updates note["tags"]; returns the tags still missing at the deadline."""
    deadline = time.monotonic() + CONFIRM_SECONDS
    while True:
        have = {_tag_key(t) for t in note["tags"]}
        lacking = [t for t in tags if _tag_key(t) not in have]
        if not lacking or time.monotonic() >= deadline:
            return lacking
        time.sleep(0.5)
        with closing(_connect()) as conn:
            row = conn.execute("SELECT tagLinks FROM notes WHERE id = ?", (note["id"],)).fetchone()
        note["tags"] = _json_list(row["tagLinks"]) if row else []


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
                revision = conn.execute("SELECT revision FROM notes WHERE id = ?", (note_id,)).fetchone()["revision"]
                return {"confirmed": True, "revision": revision, "note": _summary(r, nbs, _membership(conn, nbs), None)}
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
    """Move a note out of UpNote's Trash, back where it was. Find trashed notes with list_notes or search_notes and include_trashed=true.
    Every replace, append, move or make_section leaves the original in Trash under the same title as the live note,
    so check dates and content before restoring one, or you get a duplicate."""
    return _set_trashed(note_id, False)


# ---------------------------------------------------------------- setup check

@server.tool(annotations=READ)
def check_upnote_setup() -> dict[str, Any]:
    """Report whether the server can read UpNote correctly: database path, UpNote's data version,
    missing columns, basic counts, and which program started the server, the one macOS checks for access. Use it when other
    tools fail or their results look wrong."""
    version = _data_version()
    try:
        found = _db_found()
    except ToolError as e:
        return {"database": str(DB_PATH), "database_found": None, "error": str(e), "ok": False,
                "python": sys.executable, "started_by": _parent_process()}
    result: dict[str, Any] = {
        "database": str(DB_PATH),
        "database_found": found,
        "config_readable": version is not None,
        "python": sys.executable,
        "started_by": _parent_process(),
        "data_version": version,
        "tested_data_versions": sorted(TESTED_DATA_VERSIONS),
        "missing_columns": {},
        "warnings": [],
    }
    if version is None:
        result["warnings"].append("UpNote's data version couldn't be read from config.json next to the database.")
    elif version not in TESTED_DATA_VERSIONS:
        result["warnings"].append(
            f"UpNote's data version is {version}, but this server was tested with {sorted(TESTED_DATA_VERSIONS)}. "
            "Results may be wrong if the format changed."
        )
    if not found:
        result["ok"] = False
        return result
    try:
        with closing(sqlite3.connect(f"file:{quote(str(DB_PATH))}?mode=ro", uri=True, timeout=5.0)) as conn:
            conn.execute("PRAGMA query_only = 1")
            result["missing_columns"] = _missing_columns(conn)
            if not result["missing_columns"]:
                one = lambda sql: conn.execute(sql).fetchone()[0]
                notebooks = one("SELECT count(*) FROM notebooks WHERE deleted = 0")
                membership = one("SELECT count(*) FROM lists WHERE id LIKE 'notebooks\\_%' ESCAPE '\\'")
                result["counts"] = {
                    "notes": one("SELECT count(*) FROM notes WHERE deleted = 0 AND trashed = 0"),
                    "notes_in_trash": one("SELECT count(*) FROM notes WHERE deleted = 0 AND trashed = 1"),
                    "notebooks": notebooks,
                    "notebook_membership_lists": membership,
                }
                if notebooks and not membership:
                    result["warnings"].append(
                        "Notebooks exist, but no notebook contents were found in the lists table, "
                        "so notebook filters and counts will be empty."
                    )
    except sqlite3.Error as e:
        result["error"] = str(e)
        result["fix"] = ACCESS_FIX
    result["ok"] = result["database_found"] and not result["missing_columns"] and "error" not in result
    return result


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
PENDING_SECONDS = 300
# Notes whose apply sent a create link that hadn't shown up: note id -> (marker, when). A second apply
# checks for the late copy first, so a retry can't make a third note.
_PENDING: dict[str, tuple[str, float]] = {}


def _replace_checks(conn: sqlite3.Connection, note_id: str):
    """Return the note, notebooks, its notebook ids, blockers, and warnings for a replace."""
    r = conn.execute(
        "SELECT id, title, html, revision, createdAt, updatedAt, trashed, pinned, bookmarked, shared, shareId, isTemplate, fileIds, tagLinks "
        "FROM notes WHERE id = ? AND deleted = 0",
        (note_id,),
    ).fetchone()
    if r is None:
        raise ToolError(f"No note with id {note_id!r}. Find ids with search_notes or list_notes.")
    if r["trashed"]:
        live = conn.execute("SELECT id FROM notes WHERE deleted = 0 AND trashed = 0 AND title = ? ORDER BY updatedAt DESC",
                            (r["title"],)).fetchall()
        raise ToolError(
            f"Note {r['title']!r} is in Trash. If a rebuild replaced it, the new version has a new id"
            + (f"; the live note with this title is {live[0]['id']}" if len(live) == 1 and r["title"] else
               f"; live notes with this title: {', '.join(x['id'] for x in live[:5])}" if live and r["title"] else
               "; search for its title or content to find it")
            + ". Check with get_note that it is the same note before editing it. Restore this copy with "
            "restore_note only if the user wants this old version back."
        )
    body = r["html"] or ""
    nbs = _notebooks(conn)
    notebook_ids = _membership(conn, nbs).get(note_id, [])
    blockers: list[str] = []
    warnings: list[str] = []

    # Blockers: something would really be lost.
    if _json_list(r["fileIds"]) or "<img" in body:
        blockers.append("It has attachments or images, and the new version can only carry text.")
    if re.search(r"<(?:iframe|video|audio|object|embed)\b|data-upnote-iframe", body, re.I):
        blockers.append("It has an embedded frame, video or audio, which the new version can't carry.")
    linking = [
        row["title"] or "untitled"
        for row in conn.execute("SELECT title, noteLinks, html FROM notes WHERE deleted = 0 AND trashed = 0 AND id != ?", (note_id,))
        if note_id in (row["noteLinks"] or "") or note_id in (row["html"] or "")
    ]
    if linking:
        blockers.append(f"Other notes link to it ({', '.join(repr(t) for t in linking[:5])}), and those links would lead to the trashed original.")
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
    if (r["revision"] or 0) >= LONG_HISTORY_REVISIONS:
        warnings.append(f"It has been saved {r['revision']} times. Its Version History will most likely stay with the original in Trash.")
    if "shine-section-collapsed" in body:
        warnings.append("It has collapsed sections. They may open expanded in the new version.")
    if "shine-collapsible-section" in body or len(body) > 20000:
        warnings.append("Its formatting is complex. Compare the new version with the original before emptying Trash.")
    made_here = "data-upnote-mcp=" in body and (r["updatedAt"] or 0) - (r["createdAt"] or 0) < 60000  # untouched since this server made it
    if r["updatedAt"] and time.time() * 1000 - r["updatedAt"] < RECENT_EDIT_MINUTES * 60000 and not made_here:
        warnings.append(f"It was edited in the last {RECENT_EDIT_MINUTES} minutes. If someone is typing in it, those changes stay in the original.")
    return r, nbs, notebook_ids, blockers, warnings


def _tag_anchor(tag: str) -> str:
    """A hashtag as UpNote writes it into a note. UpNote takes a note's tags from these links,
    any number of them (tested 2026-10-10); the create link's tag parameter takes only one."""
    name = tag.strip().lstrip("#")
    shown = html_lib.escape(name)
    return (
        f'<a data-upnote-tag="#{shown}" spellcheck="false" data-non-editable="true" '
        f'href="upnote://x-callback-url/tag/view?tag={quote(name, safe="/")}">#{shown}</a>'
    )


def _with_tags(body: str, tags: list[str]) -> str:
    """The body with a hashtag added at the end for each tag it doesn't already carry."""
    present = {_tag_key(html_lib.unescape(t)) for t in re.findall(r'data-upnote-tag="([^"]*)"', body)}
    missing = [t for t in tags if _tag_key(t) not in present]
    if not missing:
        return body
    return body.rstrip() + "\n\n<div>" + " ".join(_tag_anchor(t) for t in missing) + "</div>"


def _tag_titles(conn: sqlite3.Connection, tag_links: list[str]) -> list[str]:
    """A note's tags as the tags table writes them. tagLinks holds them lower-cased."""
    titles = {_tag_key(t): t.strip().lstrip("#") for (t,) in conn.execute("SELECT title FROM tags WHERE deleted = 0") if t}
    return [titles.get(_tag_key(t), t) for t in tag_links]


def _line_key(line: str) -> str:
    """A line of a note's plain text, compared loosely: case, runs of spaces and non-breaking spaces."""
    return _fold(re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip())


def _tag_line(line: str, tags: list[str]) -> bool:
    """Whether a plain-text line is a row of the note's own hashtags, which the tag check covers."""
    words = line.split()
    keys = {_tag_key(t) for t in tags}
    return bool(words) and all(w.startswith("#") and _tag_key(w) in keys for w in words)


def _kept_lines(text: str | None, *drop: str) -> list[str]:
    """The lines of a note's plain text a content-keeping rebuild must carry over: all but the
    title, which is the first, and any named in drop."""
    dropped = {_line_key(d) for d in drop if d}
    return [x for x in (text or "").split("\n")[1:] if _line_key(x) and _line_key(x) not in dropped]


def _strip_title_heading(text: str, *titles: str) -> str:
    """Drop a leading <h2> title, as in get_note's html, since UpNote adds the title itself."""
    keys = {_line_key(t) for t in titles if t and t.strip()}
    plain = lambda h: _line_key(html_lib.unescape(re.sub(r"<[^>]+>", "", h)))
    m = re.match(r"\s*<h2>(.*?)</h2>\s*", text, re.S)
    if m:
        return text[m.end():] if plain(m.group(1)) in keys else text
    # A note made outside the create link may have no <h2>: UpNote then takes the title from the
    # first line, which would be repeated under the new note's own title heading.
    m = re.match(r"(\s*(?:<div>)?)(?:\s*<div><br></div>)*\s*<(div|p|h[1-6])>((?:(?!</?\2\b).)*?)</\2>\s*", text, re.S | re.I)
    if m and plain(m.group(3)) in keys:
        return m.group(1) + text[m.end():]
    # Text written from get_note's plain format, or Markdown, starts with the title as a line. Only a
    # repeat of the title the new version gets is dropped: on a rename, a heading with the old title
    # may be meant to stay.
    m = re.match(r"\s*(?:#{1,6}\s+)?([^\n<]*)(?:\n|$)", text)
    if m and m.group(1).strip() and titles and _line_key(m.group(1)) == _line_key(titles[-1]):
        return text[m.end():]
    return text


_TEXT_DOC = (
    "The complete new body, not a list of changes. Omit it to keep the body as it is, for example to only "
    "remove or add tags or move the note. To edit, read the note with get_note format=\"html\", reading every part "
    "of a long note, and send back that HTML changed only where needed; a leading title heading is removed "
    "automatically. Content you insert inside that HTML must be HTML too (<ul><li>…</li></ul>, <div>…</div>), "
    "since Markdown isn't converted inside HTML. Markdown works for a body written from scratch, following "
    "create_note's text rules."
)


_TOKEN_DOC = "Omit to preview. To apply, pass the preview_token the preview returned, with expected_revision."


def _preview_token(tool: str, note_id: str, **args: Any) -> str:
    """A digest of a call's arguments, so an apply can only carry out what its preview showed."""
    return hashlib.sha256(json.dumps([tool, note_id.strip(), args], sort_keys=True, default=str).encode()).hexdigest()[:16]


def _check_token(token: str | None, expected: str) -> None:
    if token != expected:
        raise ToolError("These arguments differ from the preview's, or preview_token is missing. Preview again with "
                        "the arguments you mean to apply, show the user the result, then apply with its preview_token.")


def _visible_lines(text: str) -> list[str]:
    """The lines a reader would see in text that mixes HTML and Markdown, as line keys."""
    text = re.sub(r"<(?:br|/?(?:div|p|li|ul|ol|h[1-6]|pre|blockquote|tr|td|th|table))\b[^>]*>", "\n", text, flags=re.I)
    text = html_lib.unescape(re.sub(r"<[^<>]+>", "", text))
    lines = []
    for line in text.split("\n"):
        if re.match(r"^\s*(?:`{3,}|~{3,})", line):
            continue  # a fence line, whose language name isn't shown
        line = re.sub(r"^\s*(?:(?:[-*+]|\d{1,9}[.)]|#{1,6}|>)\s+)*(?:\[[ xX]\]\s+)?", "", line)
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
        if key := _line_key(re.sub(r"[*_~=`]", " ", line)):
            lines.append(key)
    return lines


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]{3,}", _fold(text))}  # split on _, as UpNote's text keeps my_var whole


def _replace(
    note_id: NoteId,
    text: Annotated[str | None, Field(description=_TEXT_DOC)] = None,
    title: Annotated[str | None, Field(description="New title. Omit to keep the current one.")] = None,
    notebook: Annotated[str | None, Field(description=(
        'Put the new version in this notebook instead: title, path such as "Parent / Child", or id. '
        "Omit to keep the note where it is."
    ))] = None,
    remove_tags: Annotated[list[str] | None, Field(description=(
        "Tags to take off the note, with or without #. Every other tag of the original is kept, "
        "whether or not the new text carries it."
    ))] = None,
    add_tags: Annotated[list[str] | None, Field(description="Tags to put on the note, with or without #. No spaces.")] = None,
    expected_revision: Annotated[int | None, Field(description="Omit to preview. To replace, pass the revision the preview returned.")] = None,
    acknowledge_warnings: Annotated[bool, Field(description="Set true only after the user has seen and accepted the preview's warnings.")] = False,
    markdown: Annotated[bool, Field(description="The text is Markdown, raw HTML allowed. Leave true.")] = True,
    keep_lines: list[str] | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    note_id = note_id.strip()
    with closing(_connect()) as conn:
        r, nbs, notebook_ids, blockers, warnings = _replace_checks(conn, note_id)
    warnings += extra_warnings or []
    if text is None and keep_lines is None:
        _current_body(note_id)  # refuses a body it can't rebuild here, at the preview rather than the apply
    with closing(_connect()) as conn:
        tags = _tag_titles(conn, _json_list(r["tagLinks"]))
        added = _tag_titles(conn, _clean_tag_names(add_tags or []))
        stored = conn.execute("SELECT text, html FROM notes WHERE id = ?", (note_id,)).fetchone()
        plain = stored["text"] or ""

    target = notebook_ids[0] if notebook_ids else None
    if notebook:
        target = _resolve_notebook(nbs, notebook)
        if notebook_ids == [target]:
            raise ToolError(f"{r['title']!r} is already in {nbs[target]['path']!r}, and only there.")
    if target and (others := _same_title_notebooks(nbs, target)):
        blockers.append(
            f"Notebook {nbs[target]['path']!r} shares its title with {', '.join(repr(o) for o in others)}, and the "
            "create link names a notebook by title only, so the new version could land in the wrong one. Rename one "
            "of them in UpNote first."
        )
    if len(notebook_ids) > 1:
        others = ", ".join(repr(nbs[i]["path"]) for i in notebook_ids if i != target)
        warnings.append(
            f"It is in several notebooks. The new version goes into {nbs[target]['path']!r} only, so it will no "
            f"longer be in {others}" + ("." if notebook else "; add it there again by hand if it should stay.")
        )

    removed: list[str] = []
    if remove_tags:
        have = {_tag_key(t): t for t in tags}
        if unknown := [t for t in remove_tags if _tag_key(t) not in have]:
            raise ToolError(f"The note has no tag {', '.join(repr(t) for t in unknown)}. Its tags: {', '.join(tags) or 'none'}.")
        dropping = {_tag_key(t) for t in remove_tags}
        removed = [t for t in tags if _tag_key(t) in dropping]
        tags = [t for t in tags if _tag_key(t) not in dropping]
    for t in added:
        if _tag_key(t) not in {_tag_key(x) for x in tags}:
            tags.append(t)

    if text is not None and keep_lines is None:
        # The new body is the caller's; say what it drops, so a short or empty text isn't a surprise.
        old = [x for x in _kept_lines(plain) if not _tag_line(x, tags + removed)]
        new = set(_visible_lines(text))
        kept = sum(1 for x in old if _line_key(x) in new)
        if not text.strip() and old:
            warnings.append(f"The new text is empty: the note's {len(old)} lines would be replaced by nothing.")
        elif old and kept < len(old) / 2:
            warnings.append(f"The new text keeps only {kept} of the original's {len(old)} lines. Check nothing is lost.")
        if removed_unsafe := _sanitize_report(text)[1]:
            warnings.append(f"Would be removed as unsafe: {', '.join(sorted(set(removed_unsafe)))}.")

    if blockers:
        raise ToolError(f"Can't replace {r['title']!r}. " + " ".join(blockers))
    if expected_revision is None:
        return {
            "stage": "preview",
            "note_id": note_id,
            "title": r["title"],
            **({"new_title": title.strip()} if title is not None and title.strip() != (r["title"] or "") else {}),
            "revision": r["revision"],
            "notebook": nbs[target]["path"] if target else None,
            **({"moving_from": [nbs[i]["path"] for i in notebook_ids]} if notebook else {}),
            "tags_kept": tags,
            **({"tags_removed": removed} if removed else {}),
            "warnings": warnings,
            "next_step": "Show any warnings to the user, then call again with the same arguments plus expected_revision "
            "and preview_token" + (" and acknowledge_warnings=true." if warnings else "."),
        }
    if expected_revision != r["revision"]:
        raise ToolError(
            f"The note changed since the preview: revision {expected_revision} is now {r['revision']}. "
            "Read it again with get_note and preview again."
        )
    if warnings and not acknowledge_warnings:
        raise ToolError("The preview's warnings haven't been accepted: " + " ".join(warnings))

    from_note = keep_lines is not None or text is None  # the body comes from _current_body, already stripped
    if text is None:
        text, plain_now = _current_body(note_id)
        keep_lines = _kept_lines(plain_now) if keep_lines is None else keep_lines
    new_title = (r["title"] if title is None else title).strip() if (r["title"] or title) else ""
    body = text if from_note else _strip_title_heading(text, r["title"] or "", new_title)
    own = _MARKER.sub("", _strip_title_heading(stored["html"] or "", r["title"] or "")).strip()
    sent = _MARKER.sub("", body).strip()
    tail = len(os.path.commonprefix([sent[::-1], own[::-1]]))
    head = sent[:len(sent) - tail]  # what the caller changed or wrote before the note's unchanged end
    edited_start = tail >= min(80, len(own)) and (
        head.lstrip().startswith("<")
        or not own.startswith("<") and "\n\n" not in head and not re.match(r"#{1,6}\s|[-*+>]\s|\d+[.)]\s|\*\*", head))
    if not from_note and "<" in own and (sent.startswith(own[:80]) or edited_start):
        body = _literal_marks(_wrap_bare(body))  # the note's own HTML from get_note, edited, not Markdown
    if not new_title and not body.strip():
        raise ToolError("Give a title or some text.")
    # Line breaks between blocks would come back as empty <div>s; see _tighten_html.
    body = _with_tags(_tighten_html(_drop_tags(body, removed)), tags)
    notebook_title = nbs[target]["title"] if target else None
    notebook_path = nbs[target]["path"] if target else None
    expected_tags = {_tag_key(t) for t in tags}
    sent_words = _words(" ".join(_visible_lines(_sanitize_html(_MARKER.sub("", body)))))

    if pending := _PENDING.get(note_id):  # an earlier apply whose new version hadn't appeared
        with closing(_connect()) as conn:
            late = conn.execute("SELECT id, trashed FROM notes WHERE deleted = 0 AND instr(html, ?) > 0 ORDER BY trashed",
                                (f'data-upnote-mcp="{pending[0]}"',)).fetchone()
        if late and late["trashed"]:  # the late copy came and was rejected: nothing is outstanding
            del _PENDING[note_id]
        elif late:
            raise ToolError(
                f"An earlier call's new version did appear later: note {late['id']}. Show it to the user with "
                f"get_note; if it is right, move the original {note_id} to Trash with move_note_to_trash after they "
                "confirm. Don't call this tool again for this note."
            )
        elif time.monotonic() - pending[1] < PENDING_SECONDS:
            raise ToolError(
                f"An earlier call's new version may still appear. Wait {PENDING_SECONDS // 60} minutes from that call, "
                "then call again: the server checks for it first."
            )
        else:
            del _PENDING[note_id]
    marker = _new_marker()
    _open_link(_create_url(new_title, body, notebook_title, markdown, marker))
    new_note = None
    trashing = False

    def kept_both(message: str) -> dict[str, Any]:
        result = {"done": False, "original_note_id": note_id, "message": message}
        if new_note is not None:
            result["new_note"] = new_note
        return result

    try:
        new_note = _find_created_note(marker, notebook_path)
        if new_note is None:
            _PENDING[note_id] = (marker, time.monotonic())
            return kept_both(
                f"The new version didn't appear within {CONFIRM_SECONDS:.0f} seconds, so the original was left "
                "unchanged. UpNote may still create it. To find it, run_select: SELECT id, title FROM notes WHERE "
                f"instr(html, 'data-upnote-mcp=\"{marker}\"') > 0. If it appears and looks right, move the "
                f"original {note_id} to Trash with move_note_to_trash after the user confirms. Calling this tool "
                "again for this note checks for it first."
            )
        if new_note.get("trashed"):
            return kept_both(
                "The new version was created but is in Trash, so the original was left in place. Restore the new "
                "one with restore_note if it looks right, then trash the original."
            )
        if notebook_path is not None and notebook_path not in new_note["notebooks"]:
            return kept_both(
                f"The new version was created but hadn't appeared in {notebook_path!r} after {CONFIRM_SECONDS:.0f} "
                "seconds, so the original was left in place. Ask the user to check the new note's notebook in "
                "UpNote, then move the one they don't want to Trash with move_note_to_trash. Don't call this tool again."
            )
        if lacking := _wait_for_tags(new_note, tags):
            return kept_both(
                f"The new version was created but didn't get the tags {', '.join(lacking)} within "
                f"{CONFIRM_SECONDS:.0f} seconds, so the original was left in place. Ask the user to check the "
                "new note's tags in UpNote, then move the one they don't want to Trash with move_note_to_trash."
            )
        with closing(_connect()) as conn:
            if not tags:
                time.sleep(1.5)  # no tag to wait for, so give UpNote a moment to record any tag at all
            row = conn.execute("SELECT text, tagLinks FROM notes WHERE id = ?", (new_note["id"],)).fetchone()
        new_note["tags"] = _json_list(row["tagLinks"]) if row else []
        if extra := sorted({_tag_key(t) for t in new_note["tags"]} - expected_tags):
            return kept_both(
                f"The new version has tags it shouldn't: {', '.join(extra)}, so the original was left in place. "
                "Ask the user to remove them in UpNote, then move the note they don't want to Trash with move_note_to_trash."
            )
        new_text = (row["text"] if row else "") or ""
        if missing := sorted(sent_words - _words(new_text)):
            return kept_both(
                f"The new version lacks {len(missing)} word(s) of the text sent, such as {missing[0]!r}, so the "
                "original was left in place. Compare the two, then move one to Trash with move_note_to_trash."
            )
        if keep_lines := [x for x in keep_lines or [] if not _tag_line(x, tags + removed)]:
            def key(line: str) -> str:  # _drop_tags turns a removed tag inside a sentence into its plain name
                for t in removed:
                    line = re.sub(rf"#({re.escape(t.lstrip('#'))})(?![\w-])", r"\1", line, flags=re.I)
                return _line_key(line)
            have = collections.Counter(key(x) for x in new_text.split("\n"))
            need = collections.Counter(key(x) for x in keep_lines)
            if lost := [x for x in keep_lines if need[key(x)] > have[key(x)]]:
                return kept_both(
                    f"The new version is missing {len(lost)} line(s) of the original, such as {lost[0][:80]!r}, "
                    "so the original was left in place. Compare the two, then move one to Trash with "
                    "move_note_to_trash."
                )
        with closing(_connect()) as conn:
            now = conn.execute("SELECT revision, trashed FROM notes WHERE id = ? AND deleted = 0", (note_id,)).fetchone()
        if now is None or now["revision"] != expected_revision or now["trashed"]:
            return kept_both(
                "The new version was created, but the original changed while that happened, so the original "
                "was left in place. Compare the two and move one to Trash with move_note_to_trash."
            )
        trashing = True
        trash = _set_trashed(note_id, True)
    except (sqlite3.Error, ToolError) as e:
        if new_note is None:
            _PENDING[note_id] = (marker, time.monotonic())
        where = ("The original may already be in Trash" if trashing else "The original was left in place")
        return kept_both(
            f"Something failed after the new version was requested: {e} {where}"
            + (", and the new version exists" if new_note else ", and UpNote may still create the new version")
            + ". Don't call this tool again. Show the user both notes with get_note and move the one they don't "
            "want to Trash with move_note_to_trash."
        )

    result: dict[str, Any] = {
        "done": bool(trash.get("confirmed")),
        "new_note": new_note,
        "original_note_id": note_id,
        "original_in_trash": bool(trash.get("confirmed")),
    }
    if tags:
        result["tags_kept"] = tags
    if notebook_path is not None:
        result["notebook"] = notebook_path
    if removed:
        result["tags_removed"] = removed
    if warnings:
        result["follow_up"] = warnings
    if not trash.get("confirmed"):
        result["message"] = (
            "The new version exists, but the original wasn't confirmed in Trash. Check it with get_note; "
            "if it is still not in Trash, move it there with move_note_to_trash after the user confirms. Don't "
            f"call this tool again. The new note is {new_note['id']}."
        )
    elif trash.get("revision") is not None and trash["revision"] > expected_revision + 1:
        result["message"] = (
            "The original was edited just before it went to Trash, so that edit isn't in the new version. "
            "Restore the original with restore_note to compare."
        )
    return result


@server.tool(annotations=REPLACE)
def replace_note(
    note_id: NoteId,
    text: Annotated[str | None, Field(description=_TEXT_DOC)] = None,
    title: Annotated[str | None, Field(description="New title. Omit to keep the current one.")] = None,
    notebook: Annotated[str | None, Field(description=(
        'Put the new version in this notebook instead: title, path such as "Parent / Child", or id. '
        "Omit to keep the note where it is."
    ))] = None,
    remove_tags: Annotated[list[str] | None, Field(description=(
        "Tags to take off the note, with or without #. Every other tag of the original is kept, "
        "whether or not the new text carries it."
    ))] = None,
    add_tags: Annotated[list[str] | None, Field(description="Tags to put on the note, with or without #. No spaces.")] = None,
    expected_revision: Annotated[int | None, Field(description="Omit to preview. To replace, pass the revision the preview returned.")] = None,
    acknowledge_warnings: Annotated[bool, Field(description="Set true only after the user has seen and accepted the preview's warnings.")] = False,
    markdown: Annotated[bool, Field(description="The text is Markdown, raw HTML allowed. Leave true.")] = True,
    preview_token: Annotated[str | None, Field(description=_TOKEN_DOC)] = None,
) -> dict[str, Any]:
    """Edit a note by replacing it, since UpNote can't change a note in place. The new version gets a new id.
    Step 1: call without expected_revision. Nothing changes; the result gives the note's revision and any warnings.
    Show the warnings to the user. Step 2: call again with the same arguments plus expected_revision, the
    preview_token the preview returned and, if there were warnings, acknowledge_warnings=true. The new version is created first. The original goes to Trash only
    after the new one is confirmed with the right notebook, tags and text, and only if nobody changed the original
    meanwhile, so it stays recoverable with restore_note. A result with done=false means both notes may exist:
    don't call again, follow its message."""
    token = _preview_token("replace_note", note_id, text=text, title=title, notebook=notebook,
                           remove_tags=remove_tags, add_tags=add_tags, markdown=markdown)
    if expected_revision is not None:
        _check_token(preview_token, token)
    result = _replace(
        note_id=note_id, text=text, title=title, notebook=notebook, remove_tags=remove_tags, add_tags=add_tags,
        expected_revision=expected_revision, acknowledge_warnings=acknowledge_warnings, markdown=markdown,
    )
    if expected_revision is None:
        result["preview_token"] = token
    return result

# ---------------------------------------------------------------- building sections

_VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "source", "col", "wbr"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class _Node:
    """One element of a note's HTML, with the offsets of its source text."""

    __slots__ = ("tag", "classes", "start", "inner_start", "inner_end", "end", "parent", "children")

    def __init__(self, tag: str, classes: tuple[str, ...], start: int, inner_start: int, parent):
        self.tag, self.classes, self.start = tag, classes, start
        self.inner_start = self.inner_end = self.end = inner_start
        self.parent, self.children = parent, []


class _NoteHtml(HTMLParser):
    """Element tree over a note's HTML that remembers where each element sits in the text.

    Offsets let a rewrite copy every untouched byte through unchanged, which matters because
    UpNote's own markup carries classes and attributes this server should not reformat.
    """

    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.source = source
        # HTMLParser counts lines by "\n" alone. splitlines() would also break at \r, \x0c,
        #   and others, and shift every offset after one.
        self._line_starts = [0] + [m.end() for m in re.finditer("\n", source)]
        self.root = _Node("#root", (), 0, 0, None)
        self.root.inner_end = self.root.end = len(source)
        self._stack = [self.root]
        self.feed(source)
        self.close()

    def _offset(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def _open(self, tag: str, attrs) -> _Node:
        start = self._offset()
        classes = tuple(dict(attrs).get("class", "").split())
        node = _Node(tag, classes, start, start + len(self.get_starttag_text() or ""), self._stack[-1])
        self._stack[-1].children.append(node)
        return node

    def handle_starttag(self, tag, attrs):
        node = self._open(tag, attrs)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                node = self._stack[i]
                node.inner_end = self._offset()
                closing_end = self.source.find(">", node.inner_end)
                node.end = closing_end + 1 if closing_end >= 0 else len(self.source)
                del self._stack[i:]
                return


def _walk(node: _Node):
    for kid in node.children:
        yield kid
        yield from _walk(kid)


def _node_text(source: str, node: _Node) -> str:
    plain = re.sub(r"<[^>]+>", " ", source[node.inner_start:node.inner_end])
    return re.sub(r"\s+", " ", html_lib.unescape(plain).replace("\xa0", " ")).strip()


def _is_section_title(node: _Node) -> bool:
    parent = node.parent
    while parent is not None:
        if any(c.startswith("shine-section-title") for c in parent.classes):
            return True
        parent = parent.parent
    return False


def _enclosing_section(source: str, node: _Node) -> str | None:
    """Title of the collapsible section this node sits in, or None at the top level."""
    parent = node.parent
    while parent is not None:
        if "shine-collapsible-section" in parent.classes:
            title = next((k for k in _walk(parent) if k.tag in _HEADINGS and _is_section_title(k)), None)
            return _node_text(source, title) if title else ""
        parent = parent.parent
    return None


def _section_html(title_html: str, content_html: str, collapsed: bool) -> str:
    """UpNote's own collapsible-section markup, the shape its editor writes."""
    cls = "shine-collapsible-section" + (" shine-section-collapsed" if collapsed else "")
    return (
        f'<div class="{cls}"><div class="shine-section-title-wrapper">'
        '<div class="shine-section-title shine-placeholder" data-upnote-placeholder-key="title">'
        f'<div class="shine-section-title-inner"><h3>{title_html}</h3></div></div></div>'
        '<div class="shine-section-content shine-placeholder" data-upnote-placeholder-key="content">'
        f'<div class="shine-section-content-inner">{content_html}</div></div></div>'
    )


def _plan_section(source: str, heading: str, collapsed: bool = False, title: str | None = None,
                  until: str | None = None) -> dict[str, Any]:
    """Work out the section a heading and the content under it would make.

    `until` names a marker element that ends the range and is removed with it, for content
    marked off by hand. `title` replaces the heading's text as the section's title.
    """
    tree = _NoteHtml(source)
    wanted = _fold(heading.strip())
    found = [n for n in _walk(tree.root) if n.tag in _HEADINGS and _fold(_node_text(source, n)) == wanted]
    already_titles = [n for n in found if _is_section_title(n)]
    found = [n for n in found if not _is_section_title(n)]
    if not found:
        if already_titles:
            raise ToolError(f"{heading!r} is already a collapsible section's title.")
        raise ToolError(
            f"No heading in the note reads {heading!r}. The start must be a heading (h1-h6); read the note with "
            "get_note and format=\"html\" to see its headings. For a bold label or a plain line, use replace_note."
        )
    if len(found) > 1:
        raise ToolError(f"{len(found)} headings read {heading!r}. Make them distinct, or use replace_note instead.")

    node = found[0]
    level = int(node.tag[1])
    siblings = node.parent.children
    after = siblings[siblings.index(node) + 1:]
    taken = []
    end_marker = None
    if until:
        wanted_end = _fold(until.strip())
        for sibling in after:
            if _fold(_node_text(source, sibling)) == wanted_end:
                end_marker = sibling
                break
            taken.append(sibling)
        if end_marker is None:
            raise ToolError(
                f"No element reading {until!r} follows {heading!r} in the same section, so the end of the "
                "range is unclear."
            )
    else:
        for sibling in after:
            if sibling.tag in _HEADINGS and int(sibling.tag[1]) <= level:
                break
            taken.append(sibling)
    if not taken:
        raise ToolError(
            f"Nothing sits between {heading!r} and "
            + (f"{until!r}" if until else "the next heading")
            + ", so the section would be empty."
        )

    content = source[node.end:taken[-1].end]
    range_end = (end_marker.end if end_marker is not None else taken[-1].end)
    title_html = html_lib.escape(title.strip()) if title else source[node.inner_start:node.inner_end]
    rebuilt = (
        source[:node.start]
        + _section_html(title_html, content, collapsed)
        + source[range_end:]
    )
    return {
        "section_title": title.strip() if title else _node_text(source, node),
        "inside_section": _enclosing_section(source, node),
        "blocks_moved": len(taken),
        "first_blocks": [(_node_text(source, t) or f"<{t.tag}>")[:60] for t in taken[:5]],
        "html": rebuilt,
    }


def _current_body(note_id: str) -> tuple[str, str]:
    """A note's HTML without its title heading, ready to be rebuilt through _replace, and its plain text,
    from which the rebuild checks that nothing was lost."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT title, html, text FROM notes WHERE id = ? AND deleted = 0", (note_id,)).fetchone()
    if row is None:
        raise ToolError(f"No note with id {note_id!r}. Find ids with search_notes or list_notes.")
    body = _strip_title_heading(row["html"] or "", row["title"] or "")
    if body.lstrip().lower().startswith("<h2") and body.strip() == (row["html"] or "").strip():
        raise ToolError(
            "The note's title heading holds more than its title, so rebuilding it as it is would repeat that "
            "heading under the new title. Call replace_note with text: the note's HTML from get_note "
            'format="html", with the heading edited.'
        )
    return _literal_marks(_wrap_bare(body)), row["text"] or ""


def _literal_marks(html: str) -> str:
    """A note's HTML with == and $$ kept as text. UpNote turns ==x== into a highlight and $$x$$ into a
    formula in any text not inside a <span>, <code> or <pre>, so text holding them is put in a <span>,
    with $ as &#36; so the formula search on the raw text doesn't pair it across blocks either."""
    pres = _pre_spans(html)

    def keep(m: re.Match) -> str:
        if not _outside(pres, m.start(), m.end()):
            return m.group(0)
        return f"<span>{m.group(0).replace('$', '&#36;')}</span>"
    return re.sub(r"(?:(?<=>)|\A)[^<>]*(?:==|\$\$)[^<>]*(?=<|\Z)", keep, html)


def _wrap_bare(body: str) -> str:
    """HTML that starts with bare text, in a <div>: bare text first would be read as Markdown,
    escaping and all, so a \\ before <br> would show the tag and join two lines."""
    if body.strip() and not re.match(r"\s*<(?:div|p|ul|ol|h[1-6]|pre|blockquote|table|hr)\b", body, re.I):
        return f"<div>{body}</div>"
    return body


@server.tool(annotations=REPLACE)
def make_section(
    note_id: NoteId,
    heading: Annotated[str, Field(description="Text of the heading (h1-h6) where the section starts. It becomes the section's title unless title is given, and is removed from the body.")],
    until: Annotated[str | None, Field(description=(
        "Text of an end-marker line, such as a hand-written 'end collapse'. The section stops before it and the "
        "marker line is DELETED. Omit to stop at the next heading of the same or higher level, which then stays."
    ))] = None,
    title: Annotated[str | None, Field(description="Title for the new section. Omit to use the heading's own text.")] = None,
    collapsed: Annotated[bool, Field(description="Start the new section closed.")] = False,
    expected_revision: Annotated[int | None, Field(description="Omit to preview. To apply, pass the revision the preview returned.")] = None,
    acknowledge_warnings: Annotated[bool, Field(description="Set true only after the user has seen and accepted the preview's warnings.")] = False,
    preview_token: Annotated[str | None, Field(description=_TOKEN_DOC)] = None,
) -> dict[str, Any]:
    """Turn a heading and the content under it into a collapsible section, where the heading already sits.
    A heading inside an existing section becomes a section nested in it, which UpNote renders but its editor
    cannot create. The section holds everything from the heading to the next heading of the same or higher
    level, or to the end of its container. Pass until to end the range at a hand-written end-marker line instead;
    that line is deleted. The start must be a heading: for a bold label or a plain line, use replace_note. Two steps like
    replace_note: call without expected_revision to preview what would move, then again with it. The note is rebuilt through replace_note, so the result has
    a new id and the original goes to Trash."""
    note_id = note_id.strip()
    token = _preview_token("make_section", note_id, heading=heading, until=until, title=title, collapsed=collapsed)
    if expected_revision is not None:
        _check_token(preview_token, token)
    body, plain = _current_body(note_id)
    plan = _plan_section(body, heading, collapsed, title=title, until=until)

    if expected_revision is None:
        preview = _replace(note_id=note_id)
        preview.update({k: plan[k] for k in ("section_title", "inside_section", "blocks_moved", "first_blocks")})
        if until:
            preview["line_deleted"] = until
        preview["preview_token"] = token
        preview["next_step"] = (
            "Show the warnings and what would move to the user, then call again with expected_revision and preview_token"
            + (" and acknowledge_warnings=true." if preview["warnings"] else ".")
        )
        return preview

    # The heading's own line goes when title renames the section, and the until marker always goes.
    result = _replace(
        note_id=note_id, text=plan["html"], expected_revision=expected_revision,
        acknowledge_warnings=acknowledge_warnings,
        keep_lines=_kept_lines(plain, heading if title else "", until or ""),
    )
    if result.get("done"):
        result.update({k: plan[k] for k in ("section_title", "inside_section", "blocks_moved")})
    return result


# ---------------------------------------------------------------- appending

_BLOCK_TAGS = r"(?:div|p|ul|ol|li|h[1-6]|pre|blockquote|table|thead|tbody|tr|td|th|hr)"
_BREAK_BETWEEN_TAGS = re.compile(rf"(<(/?){_BLOCK_TAGS}\b[^>]*>)(\s++)(?=<(/?){_BLOCK_TAGS}\b)", re.I)
_PRE_OPEN = re.compile(r"<pre\b", re.I)
_TICKS = re.compile(r"`+")
_PARAGRAPH_END = re.compile(r"\n[ \t]*\n|\n {0,3}<pre\b", re.I)  # a <pre> opening a line interrupts a paragraph


def _pre_spans(text: str, line_start: bool = False, after_tag: bool = False) -> list[tuple[int, int]]:
    """Where <pre> blocks are, scanning once (a regex backtracks badly on many unclosed <pre).
    An unclosed one runs to the end. A <pre> named in inline code is only text, so the scan steps
    over code spans as Markdown pairs their backticks, and over each block's content. With
    line_start, only blocks that open a line count, as only those start an HTML block in
    Markdown; one further along a line is an inline tag, its content read as Markdown. With
    after_tag, a block may also follow another tag on its line, as in UpNote's one-line HTML, but
    not a word: "use a <pre> block" names one."""
    lower, spans, pos = text.lower(), [], 0
    p = _PRE_OPEN.search(text)
    par_end = -1  # end of the paragraph the scan is in; a code span doesn't cross a blank line
    no_closer: dict[int, int] = {}  # a run length that has no closer before that paragraph end
    line_begin, line_seen = 0, 0
    while True:
        if p and p.start() < pos:
            p = _PRE_OPEN.search(text, pos)
        if not p:
            return spans
        t = _TICKS.search(text, pos, p.start())
        if t:
            pos = t.end()
            n = len(t.group(0)) - (t.start() > 0 and text[t.start() - 1] == "\\")  # \` is a literal backtick
            if not n:
                continue
            if pos > par_end:
                par_end = (b.start() if (b := _PARAGRAPH_END.search(text, pos)) else len(text))
            if no_closer.get(n) == par_end:
                continue
            if c := re.compile(rf"(?<!`)`{{{n}}}(?!`)").search(text, pos, par_end):
                pos = c.end()
            else:
                no_closer[n] = par_end
            continue
        if line_start or after_tag:
            if (nl := text.rfind("\n", line_seen, p.start())) >= 0:
                line_begin = nl + 1
            line_seen = p.start()
            at_line_start = re.fullmatch(r" {0,3}", text[line_begin:min(p.start(), line_begin + 4)]) and p.start() - line_begin < 4
            after_a_tag = after_tag and text[max(line_begin, p.start() - 64):p.start()].rstrip().endswith(">")
            if not (at_line_start or after_a_tag):
                pos = p.end()
                continue
        close = lower.find("</pre", p.end())
        end = len(text) if close < 0 else (lower.find(">", close) + 1 or len(text))
        spans.append((p.start(), end))
        pos = end


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def _blank_pres(text: str, pres: list[tuple[int, int]]) -> str:
    """The text with each <pre> block blanked to x's, line breaks kept, so patterns for Markdown code
    don't match inside stored code blocks and positions stay the same."""
    chars = list(text)
    for a, b in pres:
        chars[a:b] = ["\n" if c == "\n" else "x" for c in text[a:b]]
    return "".join(chars)
# A Markdown code fence, at any indent (inside a list item it is indented); an unclosed one runs
# to the end, as in Markdown.
_FENCED = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[`~]*[ \t]*$|\Z)", re.S | re.M)
# Lines indented four spaces or a tab: an indented code block in Markdown, or a fenced block's body.
_INDENTED = re.compile(r"^(?: {4}|\t)[^\n]*(?:\n(?: {4}|\t)[^\n]*)*", re.M)


def _code_spans(source: str) -> list[tuple[int, int]]:
    """Where code sits in a mix of HTML and Markdown: <pre> blocks, code fences and indented
    code. Its layout is shown as written, so no line break there may be removed."""
    pres = _pre_spans(source)
    outside = _blank_pres(source, pres)
    spans = pres + [m.span() for m in _FENCED.finditer(outside)] + [m.span() for m in _INDENTED.finditer(outside)]
    return _merge(spans)


def _outside(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    i = bisect.bisect_right(spans, (start, float("inf"))) - 1
    return not any(a < end and start < b for a, b in spans[max(i, 0):i + 2])


def _tighten_html(source: str) -> str:
    """Drop line breaks between two block tags, outside code.

    A browser ignores them, but UpNote's create link turns each one into an empty <div>: after
    </ul> and before <div>, and also between two closing tags such as </ul> and </div> (tested
    2026-10-10). Without this a note's HTML grows with every rebuild. Two kinds stay: a break
    between inline tags such as </b> and <i>, which shows as a space and which UpNote keeps,
    and a break that is the whole content of an element, as in <li>\n</li>. The text of
    replace_note and append_to_note is usually Markdown, where an HTML example sits in a fence
    or an indented block, so those are left alone as well as <pre>.
    """
    code = _code_spans(source)

    def drop(m: re.Match) -> str:
        empty_element = not m.group(2) and m.group(4)
        if "\n" not in m.group(3) or empty_element or not _outside(code, m.start(3), m.end(3)):
            return m.group(0)
        return m.group(1)

    return _BREAK_BETWEEN_TAGS.sub(drop, source)


# What the server sends is rebuilt from these, so nothing else UpNote could act on gets through:
# no script, frame, embed, form or style element, no event handler, no remote image.
# The lists are the tags and attributes UpNote's own notes use (surveyed 2026-10-10).
_ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "code", "col", "colgroup", "del", "div", "em", "font", "h1", "h2", "h3", "h4",
    "h5", "h6", "hr", "i", "ins", "kbd", "li", "ol", "p", "pre", "s", "small", "span", "strike", "strong", "sub",
    "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
_ALLOWED_ATTRS = {
    "alt", "class", "colspan", "data-checked", "data-code-language", "data-element-id", "data-file-id",
    "data-formula-width-em", "data-href", "data-non-editable", "data-note-id", "data-upnote-formula",
    "data-upnote-keep-style", "data-upnote-marker-digit-count", "data-upnote-mcp", "data-upnote-placeholder",
    "data-upnote-placeholder-key", "data-upnote-tag", "href", "rowspan", "spellcheck", "start", "style", "title",
    "type", "width",
}
# Elements whose content is dropped with them. The parser reads their content as text up to the
# closing tag, so an unclosed one is escaped first (see _sanitize_html) rather than eat the note.
_RAW_TEXT_TAGS = {"script", "style"}
# Elements outside the allowlist that start a block; each becomes a <div>, so its text keeps its own line.
_BLOCK_ELEMENTS = {"address", "article", "aside", "center", "dd", "details", "dialog", "dir", "dl", "dt", "fieldset",
                   "figcaption", "figure", "footer", "form", "header", "hgroup", "legend", "main", "menu", "nav",
                   "search", "section", "summary"}
_SAFE_UPNOTE_ROUTES = {"openNote", "openNotebook", "openFilter", "tag/view", "view"}  # UpNote matches them case-sensitively
_STYLE_PROPERTIES = {
    "white-space-collapse", "white-space", "text-align", "width", "height", "-en-paragraph", "display",
    "background-color", "color", "font-size", "font-weight", "font-style", "text-decoration", "padding",
    "padding-top", "padding-bottom", "padding-left", "padding-right", "margin", "margin-top", "margin-bottom",
    "margin-left", "margin-right", "vertical-align", "resize", "overflow",
}


def _safe_url(url: str) -> bool:
    """A link target that only navigates: any scheme but javascript:, vbscript: and data:, and an
    UpNote link only when it opens or shows something, never one that changes notes."""
    raw = re.sub(r"[\x00-\x20\\]", "", html_lib.unescape(url.replace("\x01", "&")))
    value = raw.lower()
    if re.match(r"(?:javascript|vbscript|livescript|mocha|data):", value):
        return False
    if value.startswith("upnote:"):
        m = re.match(r"(?i)upnote://x-callback-url/([^?#]*)(\?[^#]*)?", raw)
        # a . or .. segment is refused, not folded away: UpNote may link only part of the text (it stops at
        # a Markdown delimiter or an entity), and the part before ../ could name any route
        if not m or {".", ".."} & set(m.group(1).split("/")) or \
                posixpath.normpath("/" + m.group(1)).lstrip("/") not in _SAFE_UPNOTE_ROUTES:
            return False
        # UpNote reads parameters as a URL parser does, percent-decoded: x%2Dsuccess= is x-success=, and an
        # x-error URL is opened when the route isn't one it supports
        names = [n.strip().lower() for n, _ in parse_qsl((m.group(2) or "?")[1:], keep_blank_values=True)]
        return not re.search(r"[?&]x-(?:success|error|cancel)=", value) and not any(n.startswith("x-") for n in names)
    return True


def _safe_style(style: str) -> str:
    """The declarations of a style attribute that set plain values; anything that could load a URL
    (url(), image-set(), CSS escapes, entities) is dropped."""
    kept, dropped = [], False
    for decl in html_lib.unescape(style).split(";"):
        name, _, value = decl.partition(":")
        name, value = name.strip().lower(), value.strip()
        if not name and not value:
            continue
        plain = re.sub(r"(?:rgba?|hsla?)\(\s*[\d.,%\s]*\)", "", value, flags=re.I)
        if name in _STYLE_PROPERTIES and value and re.fullmatch(r"[#\w\s.,%+!-]*", plain):
            kept.append(f"{name}: {value}")
        else:
            dropped = True
    return "; ".join(kept) if dropped else style  # unchanged when all of it is safe, so a rebuild stays faithful


def _unlinked(m: re.Match) -> str:
    """A run of text from upnote:// on, split where UpNote could link a URL that changes notes: at
    the start when the URL isn't safe, and at any later upnote://, which UpNote may link by itself."""
    url = m.group(0)
    first = url[:7] + (re.sub(r"(?i)(upnote:)(?=//)", r"\1<span></span>", url[7:]))
    return first if _safe_url(_linked_stretch(m.string, m.start())) else "upnote:<span></span>" + first[7:]


# What UpNote's linker takes as a URL: up to JavaScript whitespace (not Python's, which also stops at
# \x1c-\x1f and \x85) or one of "<>'^`{|}. A stretch longer than the cap is reported as unsafe.
_LINKED = re.compile("[^\"<>'^`{|}\t\n\x0b\x0c\r \xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]*")
_LINKED_CAP = 2000


def _linked_stretch(text: str, i: int) -> str:
    """The text from i that UpNote's linker would take, or an unsafe stand-in when it runs past the
    cap, so judging it stays linear on text without spaces."""
    m = _LINKED.match(text, i, i + _LINKED_CAP + 1)
    return m.group(0) if m.end() - i <= _LINKED_CAP else "upnote://x-callback-url/too-long"


def _destination_end(text: str, i: int) -> int:
    """Where a Markdown link destination starting at i ends, by CommonMark: <...> on one line, or a run
    with balanced parentheses up to an ASCII space or control character. Anything else, > and non-ASCII
    spaces included, belongs to it."""
    punct = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    if text.startswith("<", i):  # up to the first unescaped >, on one line, with no unescaped <
        j = i + 1
        while j < len(text) and text[j] not in "<>\n":
            j += 2 if text[j] == "\\" and text[j + 1:j + 2] in punct and text[j + 1:j + 2] else 1
        if j < len(text) and text[j] == ">":
            return j + 1
    depth, j = 0, i
    while j < len(text):
        c = text[j]
        if c <= " " and c not in "\x00\x01":  # the sanitiser's placeholders: \x00 marks code, \x01 a held &
            return j
        if c == "\\" and text[j + 1:j + 2] and text[j + 1] in punct:
            j += 2  # an escaped character never counts as a parenthesis
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            if not depth:
                return j
            depth -= 1
        j += 1
    return len(text)


def _unpointed(url: str) -> str:
    return url[1:-1] if url.startswith("<") and url.endswith(">") else url


def _safe_destination(m: re.Match) -> bool:
    """Whether a URL after ]( is left whole: one that is safe however far it is read. A ]( may not open a
    link, and then UpNote's linker reads the text up to the next space, past any ), so safety is judged
    on that whole stretch, less the punctuation that closes a link or a sentence. A reference
    definition is split anyway."""
    if not re.search(r"\]\([ \t]*\n?[ \t]*<?$", m.string[max(0, m.start() - 8):m.start()]):
        return False
    url = _linked_stretch(m.string, m.start()).rstrip(").,;:!?*_~")
    return _safe_url(re.sub(r"\\(?=[!-/:-@\[-`{-~])", "", url))


def _unlinked_encoded(m: re.Match) -> str:
    run = m.group(0)
    if ("&" not in run and "\\" not in run) or "upnote:" not in html_lib.unescape(re.sub(r"\\(?=[!-/:-@\[-`{-~])", "", run)).lower():
        return run
    if _safe_destination(m):
        return run
    # a numeric reference without its ; is decoded by HTML too; Markdown drops a \ before punctuation
    tokens = re.findall(r"&#[0-9]+;?|&#[xX][0-9a-fA-F]+;?|&\w+;|\\[!-/:-@\[-`{-~]|.", run, re.S)
    out, seen = [], ""
    for i, t in enumerate(tokens):
        out.append(t)
        seen = (seen + html_lib.unescape(t[1:] if t[:1] == "\\" and len(t) == 2 else t))[-8:]
        if seen.lower().endswith("upnote:") and "".join(html_lib.unescape(x[1:] if x[:1] == "\\" and len(x) == 2 else x)
                                                       for x in tokens[i + 1:i + 3]).startswith("//") \
                and re.search(r"[&\\]", "".join(tokens[max(0, i - 6):i + 3])):  # spelled with a reference or an escape
            out.append("<span></span>")
    return "".join(out)


def _unlink_upnote(html: str) -> str:
    """UpNote links any scheme:// URL in text after its own clean-up, so a plain-text upnote: URL
    that changes notes is split where it can't become a link; a <span> hides the split."""
    def literal(m: re.Match) -> str:  # a Markdown link's destination is checked by _check_markdown instead
        return m.group(0) if _safe_destination(m) else _unlinked(m)

    def text(part: str) -> str:
        # Markdown drops a backslash before punctuation, so upnote\:// is linked as upnote://
        part = re.sub(r"(?i)upnote(?=\\:|:\\?/\\?/)(\\?:)(?=\\?/\\?/)", lambda m: m.group(0) + "<span></span>"
                      if "\\" in m.string[m.start():m.end() + 4] else m.group(0), part)
        part = re.sub(r"(?i)upnote://[^\s<>\"'()]*", literal, part)
        # One spelled with entities, as upnote&#58;//, is linked once decoded: split it without decoding anything.
        return re.sub(r"[^\s<>\"'()]++", _unlinked_encoded, part)

    return "".join(p if i % 2 else text(p) for i, p in enumerate(re.split(r"(<[^<>]*>)", html)))


class _Sanitizer(HTMLParser):
    """Rebuilds HTML mixed with Markdown from an allowlist. Text between tags passes through as
    written, so Markdown keeps working; every tag is rebuilt from its parsed name and attributes,
    so no trick in the tag's spelling survives."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.skip = 0  # inside a raw-text element such as <script>, whose content is dropped too
        self.closing = False
        self.removed: list[str] = []  # what was taken out, for the caller to report

    def _attrs(self, tag: str, attrs) -> str:
        parts = []
        for name, value in attrs:
            name, value = name.lower(), value if value is None else value.replace("\x01", "&")
            if any(n == name for n, _ in parts):
                continue
            if name not in _ALLOWED_ATTRS:
                self.removed.append(f"{tag} {name}")
                continue
            if name in ("href", "data-href") and (tag != "a" and name == "href" or not _safe_url(value or "")):
                self.removed.append(f"{tag} link to {(value or '')[:40]}")
                continue
            if name == "style" and (safe := _safe_style(value or "")) != value:
                self.removed.append(f"{tag} style")
                if not (value := safe):
                    continue
            parts.append((name, value))
        esc = lambda v: v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
        return "".join(f" {n}" if v is None else f' {n}="{esc(v)}"' for n, v in parts)

    def handle_starttag(self, tag, attrs):
        if tag in _RAW_TEXT_TAGS:
            self.skip += 1
            self.removed.append(tag)
        elif self.skip:
            return
        elif tag in ("img", "image"):
            src = next((v for n, v in attrs if n == "src" and v), "")
            alt = next((v for n, v in attrs if n == "alt" and v), "") or "image"
            self.removed.append("image (shown as a link)" if src.lower().startswith(("http://", "https://")) else "image")
            if src.lower().startswith(("http://", "https://")) and _safe_url(src):
                self.out.append(f'<a href="{html_lib.escape(src)}">{html_lib.escape(alt, quote=False)}</a>')
        elif tag in _ALLOWED_TAGS:
            self.out.append(f"<{tag}{self._attrs(tag, attrs)}>")
        else:
            self.removed.append(tag)
            if tag in _BLOCK_ELEMENTS:  # its text stays a block of its own, not joined to the next
                self.out.append("<div>")

    def handle_startendtag(self, tag, attrs):
        if tag in _RAW_TEXT_TAGS or self.skip:
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in _RAW_TEXT_TAGS:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in _ALLOWED_TAGS:
            self.out.append(f"</{tag}>")
        elif not self.skip and tag in _BLOCK_ELEMENTS:
            self.out.append("</div>")

    def handle_data(self, data):
        if not self.skip:
            # A < in text is never a tag, or the parser would have read it as one: as text it is
            # escaped, so it can't join with what follows a dropped tag (<<x>img ...>) or with what is
            # appended later. &lt; reads as < in Markdown and in HTML alike.
            self.out.append(data.replace("<", "&lt;"))

    def handle_entityref(self, name):
        if not self.skip:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip:
            self.out.append(f"&#{name};")

    # Comments, declarations and processing instructions are dropped: UpNote drops comments anyway,
    # and they can hide markup from a reader.
    def handle_comment(self, data):
        self.removed.append("comment")

    def handle_decl(self, decl):
        self.removed.append("declaration")

    def handle_pi(self, data):
        self.removed.append("processing instruction")

    def unknown_decl(self, data):
        self.removed.append("declaration")

    def close(self):
        self.closing = True
        super().close()


_HTML_ELEMENTS = {
    "a", "abbr", "acronym", "address", "applet", "area", "article", "aside", "audio", "b", "base", "basefont", "bdi",
    "bdo", "big", "blink", "blockquote", "body", "br", "button", "canvas", "caption", "center", "cite", "code", "col",
    "colgroup", "data", "datalist", "dd", "del", "details", "dfn", "dialog", "dir", "div", "dl", "dt", "em", "embed",
    "fieldset", "figcaption", "figure", "font", "footer", "form", "frame", "frameset", "h1", "h2", "h3", "h4", "h5",
    "h6", "head", "header", "hgroup", "hr", "html", "i", "iframe", "image", "img", "input", "ins", "isindex", "kbd",
    "label", "legend", "li", "link", "listing", "main", "map", "mark", "marquee", "math", "menu", "meta", "meter",
    "nav", "nobr", "noembed", "noframes", "noscript", "object", "ol", "optgroup", "option", "output", "p", "param",
    "picture", "plaintext", "pre", "progress", "q", "rp", "rt", "ruby", "s", "samp", "script", "search", "section",
    "select", "slot", "small", "source", "spacer", "span", "strike", "strong", "style", "sub", "summary", "sup", "svg",
    "table", "tbody", "td", "template", "textarea", "tfoot", "th", "thead", "time", "title", "tr", "track", "tt", "u",
    "ul", "var", "video", "wbr", "xmp",
}
_OPEN_TAG = re.compile(r"""<([A-Za-z][A-Za-z0-9-]*)(?:\s++[A-Za-z_:][A-Za-z0-9_.:-]*+(?:\s*+=\s*+(?:[^\s"'=<>`]++|'[^']*+'|"[^"]*+"))?)*+\s*+/?>""")
_CLOSE_TAG = re.compile(r"</([A-Za-z][A-Za-z0-9-]*)\s*>")


def _markup_spans(text: str) -> list[tuple[int, int]]:
    """Where Markdown would see raw HTML: comments, and tags of an element that exists, by
    CommonMark's grammar."""
    spans, pos, comments = [], 0, True
    while (lt := text.find("<", pos)) >= 0:
        m = _OPEN_TAG.match(text, lt) or _CLOSE_TAG.match(text, lt)
        if m and m.group(1).lower() in _HTML_ELEMENTS:
            spans.append(m.span())
            pos = m.end()
        elif comments and text.startswith("<!--", lt):
            if (end := text.find("-->", lt + 4)) < 0:
                comments = False  # no later one can close either
                pos = lt + 1
            else:
                spans.append((lt, end + 3))
                pos = end + 3
        else:
            pos = lt + 1
    return spans


_HTML_BLOCK_NAMES = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|"
    "fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|"
    "menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|"
    "track|ul")
_LINE_PREFIX = r"^[ \t>]*(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)?"  # indent, quote and list markers before a block
_HTML_BLOCK_START = re.compile(rf"{_LINE_PREFIX}</?(?:{_HTML_BLOCK_NAMES})(?:[\s/>]|$)", re.I)


def _html_blocks(text: str) -> list[tuple[int, int]]:
    """Where Markdown reads lines as raw HTML, with no Markdown inside: from a line that starts with a
    block-level tag (or with any lone tag, at a paragraph's start) to the next blank line."""
    spans, start, paragraph, pos = [], None, False, 0
    for line in text.split("\n") + [""]:
        end = pos + len(line)
        if not line.strip():
            if start is not None:
                spans.append((start, pos))
            start, paragraph = None, False
        elif start is None:
            lone = re.fullmatch(rf"{_LINE_PREFIX}(?:{_OPEN_TAG.pattern}|{_CLOSE_TAG.pattern})\s*", line)
            if _HTML_BLOCK_START.match(line) or (lone and not paragraph):
                start = pos
            paragraph = True
        pos = end + 1
    return spans


def _inside(spans: list[tuple[int, int]], pos: int) -> bool:
    i = bisect.bisect_right(spans, (pos, float("inf"))) - 1
    return i >= 0 and spans[i][0] < pos < spans[i][1]


def _escape_non_tags(text: str) -> str:
    """Write as &lt; every < that doesn't open a tag Markdown would see, by CommonMark's grammar, of
    an element that exists. Then <YOUR_TOKEN>, List<String>, a<b && c>d or <Tab> are shown as written
    instead of being dropped as unknown tags, and only real markup reaches the allowlist."""
    out, pos = [], 0
    for a, b in _markup_spans(text) + [(len(text), len(text))]:
        # Markdown's escaped \< is replaced by &lt;; a \ before a real tag stays
        out.append(text[pos:a].replace("\\<", "&lt;").replace("<", "&lt;") + text[a:b])
        pos = b
    return "".join(out)


def _autolink(m: re.Match) -> str:
    """A CommonMark autolink as a Markdown link, which the parser keeps, or as text when its target
    isn't safe. The link text is escaped so Markdown shows the URL as written."""
    url = m.group(3)
    target = f"mailto:{url}" if "@" in url and ":" not in url else url
    if not _safe_url(target):
        return "&lt;" + url.replace("<", "&lt;") + "&gt;"
    shown = re.sub(r"([\\`*_\[\]<>])", r"\\\1", url)
    return f"[{shown}](<{target}>)"


def _fences_to_pre(text: str) -> str:
    """Markdown code fences as escaped HTML, the shape UpNote stores them in, so the sanitiser checks
    everything else and never has to guess what Markdown will treat as code. Inline code spans are
    sanitised like any text: a tag inside one could be a live tag where Markdown doesn't see a span."""
    def fence(m: re.Match) -> str:
        indent, ticks, info, body = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
        lang = f' data-code-language="{html_lib.escape(info.split()[0])}"' if info else ""
        lines = [line[len(indent):] if line.startswith(indent) else line.lstrip(" ") for line in body.split("\n")]
        return f"{indent}<pre{lang}>{html_lib.escape(chr(10).join(lines), quote=False)}</pre>"
    fence_re = re.compile(r"^( {0,3})(`{3,}|~{3,})([^\n`]*)\n(.*?)(?:\n {0,3}\2[`~]*[ \t]*$|\Z)", re.S | re.M)
    out, pos, pres, i = [], 0, _pre_spans(text, after_tag=True), 0
    f = fence_re.search(text)
    while pos <= len(text):
        if f and f.start() < pos:
            f = fence_re.search(text, pos)
        while i < len(pres) and pres[i][0] < pos:
            i += 1
        p = pres[i] if i < len(pres) else None
        if f and (not p or f.start() <= p[0]):  # a fence first: whatever it holds is its code
            out.append(text[pos:f.start()] + fence(f))
            pos = f.end()
        elif p:  # a <pre> first: a fence inside it is its text
            out.append(text[pos:p[1]])
            pos = p[1]
        else:
            out.append(text[pos:])
            break
    return "".join(out)


class _Probe(HTMLParser):
    """Finds anything in a fragment that would act if read as markup rather than as code text."""
    ACTIVE = _RAW_TEXT_TAGS | {"iframe", "img", "image", "svg", "math", "object", "embed", "base", "meta", "link", "form",
                               "input", "video", "audio", "source", "picture", "details", "frame", "frameset", "applet",
                               # raw text: kept as markup, one would hide the rest of the note
                               "title", "textarea", "xmp", "noscript", "plaintext", "noembed", "noframes", "listing",
                               "template"}

    def __init__(self):
        super().__init__()
        self.active = False

    URL_ATTRS = {"href", "src", "srcset", "srcdoc", "action", "formaction", "background", "poster", "data", "ping",
                 "xlink:href", "data-href", "lowsrc", "dynsrc", "codebase", "cite", "longdesc", "manifest", "profile"}

    def handle_starttag(self, tag, attrs):
        if tag in self.ACTIVE:
            self.active = True
        for name, value in attrs:
            if name.startswith("on") or (name in self.URL_ATTRS and not (name == "href" and tag == "a" and _safe_url(value or ""))) \
                    or (name == "style" and _safe_style(value or "") != value):
                self.active = True

    handle_startendtag = handle_starttag


def _inert(fragment: str) -> bool:
    """Whether a fragment is harmless whether Markdown shows it as code or reads it as markup: no
    element or attribute that could act, no image or unsafe link syntax. List<String> or
    vec![1, 2] are inert; <b onclick=...> is not."""
    # Markdown decodes character references and backslash escapes, so the checks see it decoded too
    decoded = html_lib.unescape(re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", fragment))
    for f in (fragment, decoded):
        if re.search(r"!\[[^\]]*\]\s*[(\[]|\]\(\s*<?[a-z]+:|<[a-z][a-z0-9+.-]*:", f, re.I):
            return False
    # Markdown may not read it as code after all: UpNote pairs $$ across the text, which can eat an
    # opening delimiter. Then ![ is an image, and a tag still open at its end joins whatever follows.
    if "![" in decoded:
        return False
    if any(not _safe_url(u) for u in re.findall(r"(?i)\bupnote:[^\s<>\"'`]*", decoded)):
        return False  # read as text, UpNote would link it; it links no unsafe scheme but this one
    probe = _Probe()
    probe.feed(fragment)
    if "<" in probe.rawdata:  # the parser holds back a tag, comment or declaration it hasn't seen the end of
        return False
    probe.close()
    return not probe.active


def _sanitize_html(text: str) -> str:
    return _sanitize_report(text)[0]


# Entities HTML reads without a closing ; (the HTML standard's legacy list), as in "&not=1" or "&copy 2".
_LEGACY_ENTITY = re.compile(
    "\x01(?=(?:AElig|AMP|Aacute|Acirc|Agrave|Aring|Atilde|Auml|COPY|Ccedil|ETH|Eacute|Ecirc|Egrave|Euml|GT|"
    "Iacute|Icirc|Igrave|Iuml|LT|Ntilde|Oacute|Ocirc|Ograve|Oslash|Otilde|Ouml|QUOT|REG|THORN|Uacute|Ucirc|"
    "Ugrave|Uuml|Yacute|aacute|acirc|acute|aelig|agrave|amp|aring|atilde|auml|brvbar|ccedil|cedil|cent|copy|"
    "curren|deg|divide|eacute|ecirc|egrave|eth|euml|frac12|frac14|frac34|gt|iacute|icirc|iexcl|igrave|iquest|"
    "iuml|laquo|lt|macr|micro|middot|nbsp|not|ntilde|oacute|ocirc|ograve|ordf|ordm|oslash|otilde|ouml|para|"
    "plusmn|pound|quot|raquo|reg|sect|shy|sup1|sup2|sup3|szlig|thorn|times|uacute|ucirc|ugrave|uml|uuml|"
    "yacute|yen|yuml))")
_MD_SPECIAL = set("\\`*_[]()!~|")


def _as_text(s: str) -> str:
    """s escaped wherever Markdown or HTML could read it as syntax."""
    out = "".join(f"&#{ord(c)};" if c in _MD_SPECIAL else c for c in html_lib.escape(s, quote=False))
    out = out.replace("$$", "$&#36;")  # a $$ pair would take the references back as raw text
    # GFM links a URL even inside raw <code>, taking the escaped text after it along
    return re.sub(r"(?i)\bwww\.", "www&#46;", out.replace("://", "&#58;//"))


def _defused(block: str) -> str:
    """A <pre> block the Markdown checks skip, with the characters that could still form an image, a link
    or a formula written as references: they read the same in HTML, but if UpNote's $$ pairing or anything
    else ever exposes the content to Markdown, nothing in it can load or act."""
    def text(part: str) -> str:
        return part.replace("![", "!&#91;").replace("](", "&#93;(").replace("]:", "&#93;:").replace("$$", "$&#36;")
    m = re.match(r"<pre\b[^>]*>", block, re.I)
    head = m.group(0) if m else ""
    rest = block[len(head):]
    return head + "".join(p if i % 2 else text(p) for i, p in enumerate(re.split(r"(<[^<>]*>)", rest)))


def _shielding_pres(text: str) -> list[tuple[int, int]]:
    """<pre> blocks Markdown surely leaves alone: opening a line, closed, and with no later line
    indented less than the opening one (inside a list item, such a line ends the item and the block)."""
    pres = []
    for a, b in _pre_spans(text, line_start=True):
        indent = a - (text.rfind("\n", 0, a) + 1)
        if re.search(r"</pre\s*>\Z", text[a:b], re.I) and not re.search(rf"\n(?! {{{indent}}}|[ \t]*\n)", text[a:b]):
            pres.append((a, b))
    return pres


def _check_markdown(text: str, removed: list[str]) -> str:
    """Markdown images as links, and unsafe Markdown link targets as #, outside <pre> blocks."""
    out, last = [], 0
    for start, end in _shielding_pres(text) + [(len(text), len(text))]:
        part = text[last:start]
        if "![" in part:  # an image shown is a URL fetched
            if re.search(r"!\[[^\]\n]*\]\s*[(\[]", part):
                removed.append("image (shown as a link)")
                part = re.sub(r"!\[(?=[^\]\n]*\]\s*[(\[])", "[", part)
            # any other ![, as in vec![1, 2], is text: &#91; reads as [ but can't open an image
            part = part.replace("![", "!&#91;")

        pieces, pos = [], 0
        for d in re.finditer(r"\]\([ \t]*\n?[ \t]*", part):
            if d.start() < pos:
                continue
            stop = _destination_end(part, d.end())  # not "end": the loop around this one uses that name
            url = part[d.end():stop]
            # code set aside inside a destination comes back as its text, references and all: unsafe
            safe = "\x00" not in url and _safe_url(_unpointed(url))
            pieces.append(part[pos:d.end()] + (url if safe else (removed.append(f"link to {url[:40]}") or "#")))
            pos = stop
        part = "".join(pieces) + part[pos:]
        # a definition's destination read through the sanitiser's placeholders; one holding set-aside text is unsafe
        part = re.sub(r"(?m)^([ \t>]*\[[^\]\n]+\]:[ \t]*\n?[ \t]*<?)([^\x02-\x20]+?)(>?(?:[ \t]|$))",
                      lambda m: m.group(0) if "\x00" not in m.group(2) and _safe_url(m.group(2))
                      else (removed.append("link") or m.group(1) + "#" + m.group(3)), part)
        out.append(part + _defused(text[start:end]))
        last = end
    return "".join(out)


def _sanitize_report(text: str) -> tuple[str, list[str]]:
    """Remove what could run code, load remote content or trigger an UpNote action when the note
    is shown or clicked. Code fences are first written as escaped HTML. Inline code and indented
    code are kept exactly as written when their content would be harmless even read as markup,
    since a detection of code can disagree with Markdown's; other code is checked like any text.
    Markdown images become links and Markdown link targets are checked, then every tag is rebuilt
    from an allowlist."""
    text = re.sub("[\x00\x02\x03]", "", _fences_to_pre(text.replace("\r\n", "\n").replace("\r", "\n")))
    kept: list[str] = []
    removed: list[str] = []

    def set_aside(m: "_Span", code_span: bool, indented: bool = False) -> str:
        # the three lines before it: whether a blank line precedes it, and what the line before that is
        start = m.start()
        for _ in range(3):
            start = m._text.rfind("\n", 0, max(start - 1, 0)) + 1 if start > 0 else 0
        before = m._text[start:m.start()]
        if code_span:  # always as escaped <code>, which reads the same and leaves Markdown nothing to pair
            ticks = len(m.group(1))
            code = m.group(0)[ticks:-ticks].replace("\n", " ")
            if code.startswith(" ") and code.endswith(" ") and code.strip():
                code = code[1:-1]  # CommonMark strips one space from each side
            kept.append(f"<code>{_as_text(code.replace(chr(92) + '|', '|'))}</code>")  # \| is a table cell's |
        elif indented and not re.search(r"(?:\A|\n)[ \t]*\n\Z", "\n" + before):
            return m.group(0)  # it continues a paragraph, so it isn't code: checked as text, its code spans too
        elif not code_span and not indented and (quote := re.match(r"[ \t>]*", m.group(0)).group(0)).strip() and \
                any(not line.startswith(quote.rstrip()) for line in m.group(0).split("\n")):
            return m.group(0)  # a quoted fence with a line outside the quote: Markdown ends the quote there
        elif _inert(m.group(0)):
            kept.append(m.group(0))
        elif indented and not re.search(
                r"(?m)^(?: {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]|[ \t>]).*\n[ \t]*\n\Z", before):
            # an indented code block after a blank line, outside a list or quote: sent as an escaped
            # <pre>, the shape fences are sent in, so it shows as written and nothing in it can act
            code = "\n".join(line[4:] if line.startswith("    ") else line.lstrip("\t") for line in m.group(0).split("\n"))
            kept.append(_defused(f"<pre>{html_lib.escape(code, quote=False)}</pre>"))
        else:
            return f"\x02{m.group(0)}\x03"  # left to be checked as markup, but no code span inside it is code
        return f"\x00{len(kept) - 1}\x00"

    def apply(pattern: re.Pattern, text: str, code_span: bool, indented: bool = False) -> str:
        outside = _blank_pres(text, _pre_spans(text, after_tag=True))
        tags = _markup_spans(outside)
        if code_span:  # an HTML block or a fragment left above, where Markdown reads no code span
            tags = _merge(tags + _html_blocks(outside) + [(m.start(), m.end()) for m in re.finditer(r"\x02[^\x03]*\x03", outside)])
        out, last = [], 0
        for m in pattern.finditer(outside):
            if _inside(tags, m.start()):  # in a tag, where Markdown sees no code: checked as markup
                continue
            out.append(text[last:m.start()] + set_aside(_Span(text, m), code_span, indented))
            last = m.end()
        return "".join(out) + text[last:]

    # A fence at any indent or inside a blockquote, which _fences_to_pre leaves (it would change the
    # layout), is kept as written when its content is harmless.
    text = apply(re.compile(r"^([ \t>]*)(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t>]*\2[`~]*[ \t]*$|\Z)", re.S | re.M), text, False)
    text = apply(_INDENTED, text, False, indented=True)
    text = apply(re.compile(r"(?<!\\)(?<!(?<!\\)`)(`+)(?!`)[^\n]+?(?<!`)\1(?!`)"), text, True)
    text = text.replace("\x02", "").replace("\x03", "")
    tags, blocks = _markup_spans(text), _html_blocks(text)

    def hold_autolink(m: re.Match) -> str:  # set aside, so later passes don't touch the destination
        if _inside(tags, m.start(2)) or _inside(blocks, m.start(2)) or re.search(r"\]\([ \t]*\n?[ \t]*$", m.string[max(0, m.start() - 8):m.start()]):
            return m.group(0)  # inside a tag, an HTML block or a link's destination it is text, checked as such
        if (link := _autolink(m)).startswith("&lt;"):
            return m.group(1) + link  # unsafe: text, which the sanitiser still checks
        kept.append(link)
        # a ! before it is escaped, or it would join the restored link into an image
        return ("\\!" if m.group(1) else "") + f"\x00{len(kept) - 1}\x00"
    text = re.sub(r"(!?)(<([A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*|[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+)>)", hold_autolink, text)
    text = _escape_non_tags(text)
    # A bare & that isn't an entity is held as \x01, so the parser can't take "&startIndex=50" for an
    # entity and write it back as "&startIndex;=50". It goes back as written (a URL Markdown links by
    # itself would show &amp;), or as &amp; where HTML would read it as an entity without a ;.
    # Only a name HTML knows is an entity: "&notit;" would show as "¬it;".
    text = re.sub(r"&(?!#[0-9]+;|#[xX][0-9a-fA-F]+;)([a-zA-Z][a-zA-Z0-9]*;)?",
                  lambda m: m.group(0) if m.group(1) in html_lib.entities.html5 else "\x01" + (m.group(1) or ""),
                  text.replace("\x01", ""))
    # An unclosed <script>, <style> or <pre> would turn the rest of the text into its content; it is text.
    for name in ("script", "style", "pre"):  # one after the last closing tag; found once, as a lookahead is quadratic
        cut = text.lower().rfind(f"</{name}") + 1
        text = text[:cut] + re.sub(rf"<({name})\b", r"&lt;\1", text[cut:], flags=re.I)
    parser = _Sanitizer()
    try:
        parser.feed(_check_markdown(text, removed))
        parser.close()
    except AssertionError as e:  # Python's parser gives up on some malformed markup, such as <pre><![x
        raise ToolError(f"The text holds markup that can't be read safely ({e}). Remove the stray < and try again.") from e
    # Checked again: a tag or comment the parser dropped can join what was checked into a new image or link.
    out = _check_markdown("".join(parser.out), removed)
    out = _unlink_upnote(_LEGACY_ENTITY.sub("&amp;", out).replace("\x01", "&"))
    return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], out), removed + parser.removed


class _Span:
    """A match found in a blanked copy of the text, read back from the real text."""

    def __init__(self, text: str, m: re.Match):
        self._text, self._m = text, m

    def start(self) -> int:
        return self._m.start()

    def end(self) -> int:
        return self._m.end()

    def group(self, i: int = 0) -> str:
        return self._text[self._m.start(i):self._m.end(i)]


def _encode_pre_breaks(text: str) -> str:
    """Write line breaks inside <pre> as &#10;. A blank line ends an HTML block in Markdown, so a
    code block with an empty line in it would otherwise be split, the rest read as Markdown.
    UpNote stores &#10; as a real line break (tested 2026-10-10). A <pre> quoted in a code fence
    is left alone, and so is one named in inline code or in an indented code block, where it is only text.
    The second $ of a $$ is written &#36;, since UpNote pairs $$ into a formula on the raw text, and a pair
    reaching into a block would eat its opening tag; a lone $ stays, so no pair can run across the block."""
    pres = _pre_spans(text)
    # Indented code is looked for outside stored <pre> blocks, whose own lines may be indented; inline
    # code and fences in the text as it is, since a <pre> named in them is only text.
    code = _merge([m.span() for m in _FENCED.finditer(_blank_pres(text, pres))]  # a fence starting inside a <pre> is its text
                  + [m.span() for m in re.finditer(r"(`+)[^`\n]+?\1", text)]
                  + [m.span() for m in _INDENTED.finditer(_blank_pres(text, pres))])
    out, last = [], 0
    for a, b in pres:
        block = text[a:b]
        # $ as &#36; too: UpNote pairs $$ into formulas on the raw text, across a block's tags.
        out.append(text[last:a] + (block.replace("\n", "&#10;").replace("$$", "$&#36;") if _outside(code, a, a + 4) else block))
        last = b
    return "".join(out) + text[last:]


_TAG_LINK = r'<a\b[^>]*\bdata-upnote-tag="[^"]*"[^>]*>[^<]*</a>'
_TAG_FILLER = rf"(?:\s|&nbsp;|<br\s*/?>|{_TAG_LINK})*"
# A block holding nothing but tag links, as the editor and _with_tags write them, and the
# "<br><a ...>#tag</a>" that UpNote's own tag= link parameter appends.
_TAG_ONLY_BLOCK = re.compile(rf"\s*<(div|p)>{_TAG_FILLER}{_TAG_LINK}{_TAG_FILLER}</\1>", re.I)
_TRAILING_TAG_LINKS = re.compile(rf"\s*(?:<br\s*/?>\s*)+{_TAG_LINK}{_TAG_FILLER}(?=(?:\s*</div>)*\s*$)", re.I)


def _drop_tags(body: str, tags: list[str]) -> str:
    """The body without the links of these tags. A block left holding no tag link goes too; a link
    inside a sentence becomes the tag's name as plain text, which UpNote doesn't read as a tag."""
    if not tags:
        return body
    dropping = {_tag_key(t) for t in tags}

    def dropped(link: str) -> bool:
        m = re.search(r'data-upnote-tag="([^"]*)"', link)
        return bool(m) and _tag_key(html_lib.unescape(m.group(1))) in dropping

    def thin(m: re.Match, rebuild) -> str:
        links = re.findall(_TAG_LINK, m.group(0), re.I)
        kept = [link for link in links if not dropped(link)]
        return m.group(0) if len(kept) == len(links) else (rebuild(m, kept) if kept else "")

    body = _TAG_ONLY_BLOCK.sub(lambda m: thin(m, lambda m, kept: f"<{m.group(1)}>{' '.join(kept)}</{m.group(1)}>"), body)
    body = _TRAILING_TAG_LINKS.sub(lambda m: thin(m, lambda m, kept: "<br>" + " ".join(kept)), body)
    body = re.sub(_TAG_LINK, lambda m: html_lib.escape(html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(0))).lstrip("#"))
                  if dropped(m.group(0)) else m.group(0), body, flags=re.I)
    # UpNote finds tags by scanning the raw HTML, so the attribute quoted as text, in a code sample
    # say, still tags the note. Writing its quotes as &quot; reads the same and no longer matches.
    return re.sub(r'data-upnote-tag="([^"]*)"', lambda m: f"data-upnote-tag=&quot;{m.group(1)}&quot;"
                  if _tag_key(html_lib.unescape(m.group(1))) in dropping else m.group(0), body)


def _without_tag_blocks(body: str) -> str:
    """The body without blocks that hold only tag links. A hashtag inside a sentence stays."""
    return _TRAILING_TAG_LINKS.sub("", _TAG_ONLY_BLOCK.sub("", body))


def _appended(body: str, text: str) -> str:
    """The note's HTML followed by the new Markdown. The blank line ends the HTML block, so
    UpNote converts what follows as Markdown (tested 2026-10-10). Blocks of tag links are taken
    out here, and replace_note adds the tags back after the new content, so they stay last."""
    return _tighten_html(_without_tag_blocks(body)).rstrip() + "\n\n" + text.strip()


@server.tool(annotations=REPLACE)
def append_to_note(
    note_id: NoteId,
    text: Annotated[str, Field(description=(
        "Only the new content, added after everything already in the note. Markdown, following the same "
        "rules as create_note's text. Don't repeat the existing content."
    ))],
    expected_revision: Annotated[int | None, Field(description="Omit to preview. To apply, pass the revision the preview returned.")] = None,
    acknowledge_warnings: Annotated[bool, Field(description="Set true only after the user has seen and accepted the preview's warnings.")] = False,
    preview_token: Annotated[str | None, Field(description=_TOKEN_DOC)] = None,
) -> dict[str, Any]:
    """Add content to the end of a note and keep everything already in it. Use this instead of replace_note
    when the existing content stays as it is: the server copies it, so nothing has to be resent. Two steps like
    replace_note: call without expected_revision to preview, then again with it. The note is rebuilt through
    replace_note, so the result has a new id and the original goes to Trash."""
    note_id = note_id.strip()
    if not text.strip():
        raise ToolError("text is empty.")
    token = _preview_token("append_to_note", note_id, text=text)
    if expected_revision is not None:
        _check_token(preview_token, token)
    body, plain = _current_body(note_id)
    unsafe = [f"Would be removed as unsafe: {', '.join(sorted(set(r)))}."] if (r := _sanitize_report(text)[1]) else []

    if expected_revision is None:
        preview = _replace(note_id=note_id, extra_warnings=unsafe)
        preview["next_step"] = (
            "Show any warnings to the user, then call again with the same text, expected_revision and preview_token"
            + (" and acknowledge_warnings=true." if preview["warnings"] else ".")
        )
        preview["preview_token"] = token
        return preview

    return _replace(
        note_id=note_id, text=_appended(body, text), expected_revision=expected_revision,
        acknowledge_warnings=acknowledge_warnings, keep_lines=_kept_lines(plain), extra_warnings=unsafe,
    )


# ---------------------------------------------------------------- moving

@server.tool(annotations=REPLACE)
def move_note(
    note_id: NoteId,
    notebook: Annotated[str, Field(description='Notebook to move it to: title, path such as "Parent / Child", or id.')],
    expected_revision: Annotated[int | None, Field(description="Omit to preview. To apply, pass the revision the preview returned.")] = None,
    acknowledge_warnings: Annotated[bool, Field(description="Set true only after the user has seen and accepted the preview's warnings.")] = False,
    preview_token: Annotated[str | None, Field(description=_TOKEN_DOC)] = None,
) -> dict[str, Any]:
    """Move a note to another notebook. UpNote has no link that moves a note, so the server rebuilds it, unchanged,
    in the new notebook through replace_note: the result has a new id and creation date, keeps the tags, and the
    original goes to Trash. Pin and bookmark don't carry over. Two steps like replace_note: preview without expected_revision,
    then call again with it."""
    note_id = note_id.strip()
    token = _preview_token("move_note", note_id, notebook=notebook)
    if expected_revision is not None:
        _check_token(preview_token, token)
    body, plain = _current_body(note_id)
    if expected_revision is None:
        preview = _replace(note_id=note_id, notebook=notebook)
        preview["next_step"] = (
            "Show any warnings to the user, then call again with expected_revision and preview_token"
            + (" and acknowledge_warnings=true." if preview["warnings"] else ".")
        )
        preview["preview_token"] = token
        return preview
    return _replace(
        note_id=note_id, text=body, notebook=notebook, expected_revision=expected_revision,
        acknowledge_warnings=acknowledge_warnings, keep_lines=_kept_lines(plain),
    )


if __name__ == "__main__":
    server.run()
