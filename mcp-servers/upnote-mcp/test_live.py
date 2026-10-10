#!/usr/bin/env python3
"""Live check of the tools that change notes, against your real UpNote library.

Starts server.py from this folder over stdio, as Claude does, and runs create_note,
append_to_note, make_section, replace_note, move_note_to_trash and restore_note on notes it
creates, titled "ZZ live test <time> (safe to delete)". After each step it reads what UpNote
stored. Every note it created is moved to Trash at the end, even when a check fails.

What it leaves behind: the test notes in Trash, synced to your other devices like any note,
until you empty Trash. It tags them zz-live-test, a tag UpNote drops again once its notes are
in Trash. It needs UpNote running, and takes about a minute.

Run it with --live; without that it only prints this. Exits non-zero if any check fails.
"""
import asyncio, os, re, sqlite3, sys, time
from pathlib import Path
from urllib.parse import quote

if "--live" not in sys.argv:
    print(__doc__)
    sys.exit(0)

import importlib.util
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().with_name("server.py")
spec = importlib.util.spec_from_file_location("upnote_server", SERVER)
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)

DB = os.environ.get("UPNOTE_DB") or os.path.expanduser(
    "~/Library/Containers/com.getupnote.desktop/Data/Library/Application Support/UpNote/upnote.sqlite3")
RUN = time.strftime("%H%M%S")
TITLE = f"ZZ live test {RUN} (safe to delete)"
TAG = "zz-live-test"
TAG2 = "zz-live-test-2"

fails = 0
def check(name, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

def stored(note_id):
    conn = sqlite3.connect(f"file:{quote(DB)}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT html, text, tagLinks, trashed FROM notes WHERE id = ?", (note_id,)).fetchone()
    finally:
        conn.close()

def body(html):
    return html.split("</h2>", 1)[1] if "</h2>" in html else html

def tag_links(html):
    return re.findall(r'data-upnote-tag="([^"]*)"', html)

def common_checks(step, html, tags, also=(TAG2,)):
    check(f"{step}: tag kept", TAG in tags and all(t in tags for t in also), str(tags))
    check(f"{step}: no empty bullet", "<li>\n</li>" not in html)
    check(f"{step}: no empty <div> from a line break", "<div>\n</div>" not in html)
    links = tag_links(html)
    check(f"{step}: one link per tag, and nothing after them but closing tags", links == [f"#{TAG}"] + [f"#{t}" for t in also] and
          re.search(r'data-upnote-tag="[^"]*"[^>]*>[^<]*</a>(?:\s|</div>)*$', html) is not None,
          f"{links} … {html[-80:]!r}")

async def call(s, tool, **args):
    r = await s.call_tool(tool, args)
    return r.is_error, r.structured_content or {}, " ".join(getattr(c, "text", "") for c in r.content)

async def rebuild(s, step, tool, **args):
    """Preview, then apply, as Claude is told to. Returns the new note's id."""
    err, p, text = await call(s, tool, **args)
    check(f"{step}: preview", not err and p.get("stage") == "preview", text[:120])
    if err:
        raise SystemExit(1)
    check(f"{step}: preview lists the tag it keeps", TAG in [t.lower() for t in p.get("tags_kept", [])], str(p.get("tags_kept")))
    err, d, text = await call(s, tool, **args, expected_revision=p["revision"], acknowledge_warnings=bool(p["warnings"]))
    check(f"{step}: done, original in Trash", not err and d.get("done") and d.get("original_in_trash"), text[:160])
    if err or not d.get("done"):
        raise SystemExit(1)
    return d["new_note"]["id"]

async def main():
    created = []
    async with stdio_client(StdioServerParameters(command=sys.executable, args=["-I", str(SERVER)])) as (rd, wr):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            try:
                # 1. create: nested list, tag, a soft line break between two inline styles
                err, d, text = await call(s, "create_note", title=TITLE, tags=[TAG, TAG2], text=(
                    "### Details\n\nDetail text\n\n"
                    "### Part one\n\nLine with **bold**\n*italic* on the next line\n\n"
                    "- a\n  - nested with `code`\n- b"))
                check("create: confirmed", not err and d.get("confirmed"), text[:120])
                if err:
                    raise SystemExit(1)
                note = d["note"]["id"]; created.append(note)
                html, plain, tags, _ = stored(note)
                common_checks("create", html, tags)
                check("create: nested list in the editor's shape", "<ul><li>a</li><ul><li>nested with <code" in html, html[-300:])
                soft_break = "</b>\n<i>" in html
                print(f"INFO create: the soft line break is stored as {'</b>\\n<i>' if soft_break else 'something else'}")

                # 2. two appends: existing content kept, tags stay last, the soft break keeps its space
                for n, line in enumerate(["- appended one", "- appended two"], 1):
                    before = body(stored(note)[0])
                    keep = srv._tighten_html(srv._without_tag_blocks(before)).rstrip()
                    # UpNote may merge the new item into a list the body ends with, which moves the last
                    # closing tags; everything before them must match exactly.
                    keep = re.sub(r"(?:</(?:div|ul|ol|li)>)+$", "", keep)
                    note = await rebuild(s, f"append {n}", "append_to_note", note_id=note, text=line); created.append(note)
                    html, plain, tags, _ = stored(note)
                    common_checks(f"append {n}", html, tags)
                    check(f"append {n}: existing content kept byte for byte", body(html).startswith(keep), body(html)[:200])
                    check(f"append {n}: new item present", line[2:] in plain)
                    check(f"append {n}: bold and italic still apart", "bolditalic" not in plain.replace("*", ""),
                          plain[plain.find("bold") - 5:plain.find("bold") + 25] if "bold" in plain else plain[:80])

                # 3. make_section: the Details heading becomes a collapsible section, before Part one
                note = await rebuild(s, "make_section", "make_section", note_id=note, heading="Details"); created.append(note)
                html, plain, tags, _ = stored(note)
                common_checks("make_section", html, tags)
                check("make_section: section holds the detail text, not Part one",
                      re.search(r"shine-collapsible-section.*<h3>Details</h3>.*Detail text.*</div></div></div>\s*<h3>Part one", html, re.S) is not None,
                      html[:300])

                # 4. replace with plain Markdown that has no tag in it, removing the second tag
                note = await rebuild(s, "replace", "replace_note", note_id=note, text="### Rewritten\n\n- x\n  - y\n- z",
                                     remove_tags=[TAG2]); created.append(note)
                html, plain, tags, _ = stored(note)
                common_checks("replace", html, tags, also=())
                check("replace: second tag removed", TAG2 not in tags and f"#{TAG2}" not in html, str(tags))
                check("replace: new content", "Rewritten" in plain and "Detail text" not in plain)

                # 4b. move to another notebook, then check it sits only there, unchanged
                err, d, _ = await call(s, "list_notebooks")
                titles = [nb["title"].casefold() for nb in d["notebooks"]]
                target = next(nb for nb in d["notebooks"] if titles.count(nb["title"].casefold()) == 1)
                before = body(stored(note)[0])
                note = await rebuild(s, "move", "move_note", note_id=note, notebook=target["id"]); created.append(note)
                html, plain, tags, _ = stored(note)
                common_checks("move", html, tags, also=())
                err, d, _ = await call(s, "get_note", note_id=note)
                check("move: in the target notebook", not err and d["notebooks"] == [target["path"]], str(d.get("notebooks")))
                check("move: content unchanged", body(html) == srv._tighten_html(before), body(html)[:160])

                # 5. trash and restore
                err, d, text = await call(s, "move_note_to_trash", note_id=note)
                check("trash: confirmed", not err and d.get("confirmed") and stored(note)[3] == 1, text[:120])
                err, d, text = await call(s, "restore_note", note_id=note)
                check("restore: confirmed", not err and d.get("confirmed") and stored(note)[3] == 0, text[:120])
            finally:
                # Every note this run created goes to Trash, whatever happened above.
                err, d, _ = await call(s, "run_select", sql=(
                    "SELECT id FROM notes WHERE deleted = 0 AND trashed = 0 AND title = '" + TITLE.replace("'", "''") + "'"))
                for row in d.get("rows", []) if not err else []:
                    await call(s, "move_note_to_trash", note_id=row["id"])
                err, d, _ = await call(s, "run_select", sql=(
                    "SELECT count(*) AS n FROM notes WHERE deleted = 0 AND trashed = 0 AND title = '" + TITLE.replace("'", "''") + "'"))
                check("cleanup: every test note is in Trash", not err and d["rows"][0]["n"] == 0, str(d))

asyncio.run(main())
print("FAILURES:", fails)
sys.exit(1 if fails else 0)
