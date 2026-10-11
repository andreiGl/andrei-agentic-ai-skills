#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==2.2.0"]
# ///
"""Read-only check of the UpNote MCP server against your own UpNote library.

Starts server.py from this folder over stdio, calls every read tool, and compares each result
with a direct read-only query on the database. Also sends writes through run_select and expects
every one to be refused. Changes nothing. Exits non-zero if any check fails.
"""
import asyncio, importlib.util, json, os, re, sqlite3, sys, time
from urllib.parse import quote
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = str(Path(__file__).resolve().with_name("server.py"))
DB = os.environ.get("UPNOTE_DB") or os.path.expanduser("~/Library/Containers/com.getupnote.desktop/Data/Library/Application Support/UpNote/upnote.sqlite3")
ref = sqlite3.connect(f"file:{quote(DB)}?mode=ro", uri=True)
fails = 0
def check(name, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

async def call(s, tool, **args):
    r = await s.call_tool(tool, args)
    data = r.structured_content
    text = " ".join(getattr(c, "text", "") for c in r.content)
    return r.is_error, data, text

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-I", SERVER])
    async with stdio_client(params) as (rd, wr):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            check("fifteen tools", sorted(tools) == sorted(["search_notes","list_notes","get_note","list_notebooks","list_tags","run_select","create_note","move_note_to_trash","restore_note","replace_note","open_in_upnote","check_upnote_setup","make_section","append_to_note","move_note"]), ",".join(sorted(tools)))
            check("read tools marked read-only", all(tools[n].annotations.read_only_hint for n in tools if n not in ("create_note", "move_note_to_trash", "restore_note", "replace_note", "make_section", "append_to_note", "move_note", "open_in_upnote")))
            check("open_in_upnote isn't read-only, since it takes focus", tools["open_in_upnote"].annotations.read_only_hint is False)
            check("every tool that changes notes is marked as such",
                  all(tools[n].annotations.read_only_hint is False for n in ("create_note", "move_note_to_trash", "restore_note", "replace_note", "make_section", "append_to_note", "move_note")))
            check("  and the ones that trash a note as destructive", all(tools[n].annotations.destructive_hint for n in
                  ("move_note_to_trash", "replace_note", "make_section", "append_to_note", "move_note")))

            err, d, _ = await call(s, "check_upnote_setup")
            check("setup check reports ok with no missing columns", not err and d["ok"] and d["missing_columns"] == {}, str(d)[:160])
            check("setup check data version is a tested one", not err and d["data_version"] in d["tested_data_versions"], str(d.get("data_version")))
            live_now = ref.execute("select count(*) from notes where deleted=0 and trashed=0").fetchone()[0]
            check("setup check note count matches DB", not err and d["counts"]["notes"] == live_now, f"{d['counts']['notes']} vs {live_now}")

            err, d, _ = await call(s, "list_notebooks")
            nb_n = ref.execute("select count(*) from notebooks where deleted=0").fetchone()[0]
            check("list_notebooks count matches DB", not err and len(d["notebooks"]) == nb_n, f"{len(d['notebooks'])} vs {nb_n}")
            exp_members = ref.execute("select count(*) from lists l, json_each(l.content) j join notes n on n.id=j.value join notebooks b on 'notebooks_'||b.id=l.id where l.id like 'notebooks\\_%' escape '\\' and n.deleted=0 and n.trashed=0 and b.deleted=0").fetchone()[0]
            got_members = sum(nb["note_count"] for nb in d["notebooks"])
            check("notebook note counts sum matches DB", got_members == exp_members, f"{got_members} vs {exp_members}")
            child = next((nb for nb in d["notebooks"] if nb["parent_id"]), None)
            check("child notebook has a path with a parent", child is not None and " / " in child["path"])
            biggest = max(d["notebooks"], key=lambda nb: nb["note_count"])

            err, d, _ = await call(s, "list_tags")
            check("list_tags returns tags", not err and len(d["tags"]) > 0, f"{len(d['tags'])} tags, top count {d['tags'][0]['note_count']}")
            top_tag = d["tags"][0]["tag"]

            err, d, _ = await call(s, "list_notes", limit=5)
            live = ref.execute("select count(*) from notes where deleted=0 and trashed=0").fetchone()[0]
            newest = ref.execute("select id from notes where deleted=0 and trashed=0 order by updatedAt desc limit 1").fetchone()[0]
            check("list_notes total matches DB", not err and d["total"] == live, f"{d['total']} vs {live}")
            check("list_notes newest first matches DB", d["notes"][0]["id"] == newest)
            err, d2, _ = await call(s, "list_notes", include_trashed=True, limit=1)
            live_t = ref.execute("select count(*) from notes where deleted=0").fetchone()[0]
            check("include_trashed adds trashed notes", d2["total"] == live_t, f"{d2['total']} vs {live_t}")

            # notebook filter: a notebook's own notes plus its sub-notebooks', counted directly
            nbrows = ref.execute("select id, parent from notebooks where deleted=0").fetchall()
            def subtree(root):
                found, grew = {root}, True
                while grew:
                    grew = False
                    for i, par in nbrows:
                        if par in found and i not in found:
                            found.add(i); grew = True
                return found
            nb_by_path = {nb["path"]: nb for nb in (await call(s, "list_notebooks"))[1]["notebooks"]}
            parent_nb = next((nb for nb in nb_by_path.values() if any(c["parent_id"] == nb["id"] for c in nb_by_path.values())), biggest)
            for label, nb in (("biggest notebook", biggest), ("notebook with sub-notebooks", parent_nb)):
                ids = subtree(nb["id"])
                want = ref.execute(
                    "select count(distinct n.id) from lists l, json_each(l.content) j join notes n on n.id=j.value "
                    f"where l.id in ({','.join('?' * len(ids))}) and n.deleted=0 and n.trashed=0",
                    ["notebooks_" + i for i in ids]).fetchone()[0]
                err, d, _ = await call(s, "list_notes", notebook=nb["path"], limit=1)
                check(f"notebook filter matches DB, {label}", not err and d["total"] == want, f"{d.get('total')} vs {want}")
            err, d, _ = await call(s, "list_notes", tag="#" + top_tag.lstrip("#"), limit=1)
            exp_tag = sum(1 for (raw,) in ref.execute("select tagLinks from notes where deleted=0 and trashed=0") if any(str(t).lstrip('#').casefold()==top_tag.lstrip('#').casefold() for t in json.loads(raw or '[]')))
            check("tag filter with # matches DB", not err and d["total"] == exp_tag, f"{d['total']} vs {exp_tag}")

            # search: pick a Cyrillic word and an ASCII word from the library itself, compare with Python-side count
            rows = ref.execute("select title, text from notes where deleted=0 and trashed=0").fetchall()
            import re
            cyr = next((w for _, t in rows for w in re.findall(r"[А-Яа-яЁё]{6,}", t or "")), None)
            for word in [w for w in [cyr, "upnote"] if w]:
                q = word.upper()
                exp = sum(1 for ti, te in rows if q.casefold() in (ti or "").casefold() or q.casefold() in (te or "").casefold())
                err, d, _ = await call(s, "search_notes", query=q, limit=3)
                check(f"search upper-cased {'Cyrillic' if word is cyr else 'ASCII'} word matches Python count", not err and d["total_matches"] == exp, f"{d['total_matches']} vs {exp}")
            err, d, _ = await call(s, "search_notes", query="zzqxj-no-such-word-8871")
            check("search with no hits returns zero", not err and d["total_matches"] == 0)

            nid, tlen = ref.execute("select id, length(text) from notes where deleted=0 and trashed=0 order by length(text) desc limit 1").fetchone()
            err, d, _ = await call(s, "get_note", note_id=nid, max_chars=1000)
            check("get_note length matches DB", not err and d["length"] == tlen and len(d["content"]) == 1000 and d["next_offset"] == 1000)
            err, d, _ = await call(s, "get_note", note_id=nid, offset=tlen - 10, max_chars=1000)
            check("get_note last part has no next_offset", not err and "next_offset" not in d and len(d["content"]) == 10)

            err, d, _ = await call(s, "run_select", sql="select count(*) as n from notes where deleted=0 and trashed=0")
            check("run_select count", not err and d["rows"][0]["n"] == live)
            err, d, _ = await call(s, "run_select", sql="select b.title, count(*) c from lists l, json_each(l.content) j join notes n on n.id=j.value join notebooks b on 'notebooks_'||b.id = l.id where l.id like 'notebooks\\_%' escape '\\' group by b.title order by c desc limit 2")
            check("run_select json_each join works", not err and d["rows"], str(err) + " " + str(d)[:120] if err else "")
            err, d, _ = await call(s, "run_select", sql="select fold('ПРИВЕТ') as f")
            check("fold() lower-cases Cyrillic", not err and d["rows"][0]["f"] == "привет")

            # failing inputs: each must be refused
            for bad in ["DELETE FROM notes WHERE id='x'", "UPDATE notes SET title=title WHERE 0", "CREATE TABLE t(x)", "PRAGMA journal_mode", "ATTACH DATABASE '/tmp/upnote-attach-test.db' AS x", "SELECT 1; DELETE FROM notes WHERE 0", "INSERT INTO lists(id) VALUES('x')"]:
                err, _, text = await call(s, "run_select", sql=bad)
                check(f"refused: {bad[:40]}", err, text[:90])
            check("ATTACH created no file", not os.path.exists("/tmp/upnote-attach-test.db"))
            err, _, text = await call(s, "list_notes", notebook="No Such Notebook 9981")
            check("unknown notebook is an error", err, text[:80])
            err, _, text = await call(s, "get_note", note_id="no-such-id")
            check("unknown note id is an error", err, text[:60])
            err, _, text = await call(s, "search_notes", query="   ")
            check("empty query is an error", err, text[:60])
            # date filters against the same counts taken directly
            import datetime as _dt
            day = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
            ms = _dt.datetime.fromisoformat(day).astimezone().timestamp() * 1000
            want = ref.execute("SELECT count(*) FROM notes WHERE deleted=0 AND trashed=0 AND updatedAt >= ?", (ms,)).fetchone()[0]
            err, d, text = await call(s, "list_notes", updated_after=day, limit=1)
            check("updated_after matches DB", not err and d["total"] == want, f"{d.get('total')} vs {want}")
            want = ref.execute("SELECT count(*) FROM notes WHERE deleted=0 AND trashed=0 AND createdAt < ?", (ms,)).fetchone()[0]
            err, d, text = await call(s, "list_notes", created_before=day, limit=1)
            check("created_before matches DB", not err and d["total"] == want, f"{d.get('total')} vs {want}")
            err, _, text = await call(s, "list_notes", created_after="yesterday")
            check("a date that isn't one is an error", err and "must be a date" in text, text[:80])

            # attachment names come from the files table, without download links
            row = ref.execute("SELECT n.id, n.fileIds FROM notes n WHERE n.deleted=0 AND n.trashed=0 AND EXISTS "
                              "(SELECT 1 FROM json_each(n.fileIds) j JOIN files f ON f.id = j.value) LIMIT 1").fetchone()
            if row:
                ids = json.loads(row[1])
                names = dict(ref.execute(f"SELECT id, name FROM files WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall())
                err, d, _ = await call(s, "get_note", note_id=row[0])
                got = d.get("attachments", [])
                check("get_note lists attachment names", not err and [a["name"] for a in got] == [names.get(i) for i in ids], str(got)[:120])
                check("  without download links", "http" not in json.dumps(got))
            # the other two date filters, and paging and sorting
            want = ref.execute("SELECT count(*) FROM notes WHERE deleted=0 AND trashed=0 AND updatedAt < ?", (ms,)).fetchone()[0]
            err, d, _ = await call(s, "list_notes", updated_before=day, limit=1)
            check("updated_before matches DB", not err and d["total"] == want, f"{d.get('total')} vs {want}")
            want = ref.execute("SELECT count(*) FROM notes WHERE deleted=0 AND trashed=0 AND createdAt >= ?", (ms,)).fetchone()[0]
            err, d, _ = await call(s, "list_notes", created_after=day, limit=1)
            check("created_after matches DB", not err and d["total"] == want, f"{d.get('total')} vs {want}")
            err, d, _ = await call(s, "search_notes", query="the", updated_after=day, limit=100)
            want = sum(1 for (t, x) in ref.execute("SELECT title, text FROM notes WHERE deleted=0 AND trashed=0 AND updatedAt >= ?", (ms,))
                       if "the" in (t or "").casefold() or "the" in (x or "").casefold())
            check("search honours a date filter", not err and d["total_matches"] == want, f"{d.get('total_matches')} vs {want}")
            order = [r[0] for r in ref.execute("SELECT id FROM notes WHERE deleted=0 AND trashed=0 ORDER BY createdAt DESC LIMIT 3")]
            err, d, _ = await call(s, "list_notes", sort="created", limit=3)
            check("sort=created matches DB", not err and [n["id"] for n in d["notes"]] == order)
            err, d, _ = await call(s, "list_notes", sort="created", limit=2, offset=1)
            check("offset skips notes", not err and [n["id"] for n in d["notes"]] == order[1:3])

            # tag counts, html format, attachment count, run_select limit and truncation
            err, d, _ = await call(s, "list_tags")
            counts = {}
            for (raw,) in ref.execute("SELECT tagLinks FROM notes WHERE deleted=0 AND trashed=0"):
                for t in set(json.loads(raw or "[]")):
                    counts[str(t).lstrip("#").casefold()] = counts.get(str(t).lstrip("#").casefold(), 0) + 1
            got = {t["tag"].lstrip("#").casefold(): t["note_count"] for t in d["tags"]}
            check("list_tags counts match DB", all(got.get(k) == v for k, v in counts.items()), str([(k, got.get(k), v) for k, v in counts.items() if got.get(k) != v][:3]))
            nid, html, fids = ref.execute("SELECT id, html, fileIds FROM notes WHERE deleted=0 AND trashed=0 AND length(html) > 200 LIMIT 1").fetchone()
            err, d, _ = await call(s, "get_note", note_id=nid, format="html", max_chars=1000)
            check("format=html returns the html", not err and d["content"] == html[:1000])
            check("attachment_count matches fileIds", d["attachment_count"] == len(json.loads(fids or "[]")))
            err, d, _ = await call(s, "run_select", sql="SELECT id FROM notes", limit=2)
            check("run_select keeps to its limit and says it truncated", not err and len(d["rows"]) == 2 and d["truncated"] is True)
            err, d, _ = await call(s, "run_select", sql="SELECT 1 AS a, 2 AS a")
            check("run_select keeps both of two same-named columns", not err and d["rows"] == [{"a": 1, "a_2": 2}], str(d))
            err, d, _ = await call(s, "run_select", sql="SELECT downloadURL FROM files WHERE downloadURL IS NULL LIMIT 1")
            n_files = ref.execute("SELECT count(*) FROM files").fetchone()[0]
            check("run_select reads download links as NULL", not err and (len(d["rows"]) == 1 or n_files == 0), str(d)[:80])
            err, _, text = await call(s, "run_select", sql="SELECT length(hex(zeroblob(12000000)))")
            check("run_select refuses a value over 20 MB", err and "too big" in text, text[:80])
            err, d, text = await call(s, "run_select", sql="SELECT length(group_concat(text, char(10))) AS n FROM notes WHERE deleted=0")
            check("run_select allows an aggregate over the whole library", not err and d["rows"][0]["n"] > 0, text[:80])
            err, _, text = await call(s, "run_select", sql="SELECT " + ", ".join(f"{i} AS c{i}" for i in range(70)))
            check("run_select refuses more than 64 columns", err and "too many columns" in text, text[:80])
            err, _, text = await call(s, "run_select", limit=500, sql=(
                "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM n WHERE i < 30) SELECT hex(zeroblob(900000)) FROM n"))
            check("run_select refuses a result over 20 MB", err and "over 20 MB" in text, text[:80])

            # the rebuild tools' refusals, which all happen before anything is sent to UpNote
            # the first note a replace would accept, found by previewing candidates
            note, text = None, ""
            for cand in ref.execute("SELECT id, revision FROM notes WHERE deleted=0 AND trashed=0 AND coalesce(isTemplate, 0) = 0 "
                                    "AND coalesce(fileIds, '[]') = '[]' AND html NOT LIKE '%<img%' ORDER BY updatedAt LIMIT 20").fetchall():
                err, d, text = await call(s, "replace_note", note_id=cand[0], text="x")
                if not err:
                    note = cand
                    break
            check("replace_note preview changes nothing and gives the revision",
                  note is not None and d["stage"] == "preview" and d["revision"] == note[1], text[:100])
            if note is None:
                raise SystemExit("no note a replace would accept; can't test the refusals")
            err, d, text = await call(s, "replace_note", note_id=note[0], text="")
            check("an empty new text gets a warning", not err and any("empty" in w for w in d["warnings"]), str(d.get("warnings")))
            err, d, text = await call(s, "replace_note", note_id=note[0])
            check("no text keeps the body: no content warning", not err and not any("lines" in w for w in d["warnings"]), str(d.get("warnings")))
            err, d, text = await call(s, "replace_note", note_id=note[0], add_tags=["zz-preview-only"])
            check("add_tags shows in the preview", not err and "zz-preview-only" in d["tags_kept"], str(d.get("tags_kept")))
            err, _, text = await call(s, "replace_note", note_id=note[0], add_tags=["two words"])
            check("add_tags refuses a name with a space", err and "spaces" in text, text[:80])
            err, p, text = await call(s, "replace_note", note_id=note[0], text="x")
            err, _, text = await call(s, "replace_note", note_id=note[0], text="x", expected_revision=note[1] - 1,
                                      preview_token=p["preview_token"])
            check("a stale revision is refused", err and "changed since the preview" in text, text[:100])
            err, _, text = await call(s, "replace_note", note_id=note[0], text="something else", expected_revision=note[1],
                                      preview_token=p["preview_token"])
            check("an apply with other arguments than the preview's is refused", err and "differ from the preview" in text, text[:100])
            err, _, text = await call(s, "replace_note", note_id=note[0], text="x", expected_revision=note[1])
            check("an apply without preview_token is refused", err and "preview_token is missing" in text, text[:100])
            err, _, text = await call(s, "replace_note", note_id=note[0], text="x", remove_tags=["no-such-tag-9981"])
            check("removing a tag the note hasn't got is refused", err and "has no tag" in text, text[:100])
            err, _, text = await call(s, "append_to_note", note_id=note[0], text="  ")
            check("an empty append is refused", err and "text is empty" in text, text[:80])
            err, d, _ = await call(s, "get_note", note_id=note[0])
            if d.get("notebooks"):
                err, _, text = await call(s, "move_note", note_id=note[0], notebook=d["notebooks"][0])
                check("moving a note to its own notebook is refused", err and "already in" in text, text[:100])
            started = time.monotonic()
            err, _, text = await call(s, "run_select", sql="WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c")
            took = time.monotonic() - started
            check("a query that never ends is stopped", err and "stopped after" in text and took < 20, f"{took:.1f}s {text[:70]}")

    # excerpts land on the match even when casefold() changes the text's length
    spec = importlib.util.spec_from_file_location("upnote_server", SERVER)
    srv = importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
    ex = srv._excerpt("x" * 300 + " Straße here", [srv._fold("straße")], 60)
    check("excerpt finds a word that casefold() lengthens", "Straße" in ex, ex)
    ex = srv._excerpt("ß" * 200 + " target word", [srv._fold("target")], 40)
    check("excerpt position maps back past lengthened letters", "target" in ex, ex)

    # the sanitiser leaves what a reader sees unchanged on every note a rebuild would accept
    changed = []
    with srv.closing(srv._connect()) as conn:
        for nid, html, fids in conn.execute("SELECT id, html, fileIds FROM notes WHERE deleted=0 AND trashed=0"):
            body = (html or "").split("</h2>", 1)[-1]
            if srv._json_list(fids) or "<img" in body or re.search(r"<(?:iframe|video|audio)|data-upnote-iframe", body):
                continue
            if srv._visible_lines(srv._sanitize_html(body)) != srv._visible_lines(body):
                changed.append(nid)
    check("the sanitiser keeps the visible text of every rebuildable note", not changed, str(changed[:5]))

    # an unchanged rebuild of each such note passes the rebuild's own word check against its stored text
    refused = []
    with srv.closing(srv._connect()) as conn:
        for nid, title, html, text, fids, tl in conn.execute(
                "SELECT id, title, html, text, fileIds, tagLinks FROM notes WHERE deleted=0 AND trashed=0"):
            if srv._json_list(fids) or "<img" in (html or "") or re.search(r"<(?:iframe|video|audio)|data-upnote-iframe", html or ""):
                continue
            body = srv._with_tags(srv._tighten_html(srv._strip_title_heading(html or "", title or "")), srv._json_list(tl))
            sent = srv._words(" ".join(srv._visible_lines(srv._sanitize_html(srv._MARKER.sub("", body)))))
            if sent - srv._words(text or ""):
                refused.append(nid)
    check("the word check accepts an unchanged rebuild of every rebuildable note", not refused, f"{len(refused)}: {refused[:3]}")

    # duplicate notebook titles, simulated in-process: refused before any link is sent
    sent = []
    srv._open_link = lambda url, background=True: sent.append(url)
    real = srv._notebooks
    def doubled(conn):
        nbs = real(conn)
        first = next(iter(nbs.values()))
        nbs["dup-test-id"] = {"id": "dup-test-id", "title": first["title"].upper(), "parent": None, "path": "Other"}
        return nbs
    srv._notebooks = doubled
    with srv.closing(srv._connect()) as conn:
        first = next(iter(real(conn).values()))
    try:
        srv.create_note(title="never sent", notebook=first["id"]); check("create_note refuses a shared notebook title", False, "no error")
    except srv.ToolError as e:
        check("create_note refuses a shared notebook title", "by title only" in str(e) and not sent, str(e)[:80])
    try:
        srv.create_note(title="never sent", tags=["a b"]); check("create_note refuses a tag with a space", False, "no error")
    except srv.ToolError as e:
        check("create_note refuses a tag with a space", "spaces" in str(e) and not sent, str(e)[:80])
    srv._notebooks = real

    # rebuilds against a stand-in for UpNote, which stores the visible lines of what was sent: no link
    # reaches the app and nothing is trashed, so these exercise the verification after the copy
    from urllib.parse import parse_qs, urlsplit
    import types
    sent.clear()
    real_connect, real_find, real_wait, real_trash, real_time = srv._connect, srv._find_created_note, srv._wait_for_tags, srv._set_trashed, srv.time

    stored = {"text": None}  # what UpNote would store, when the test knows it; else made from what was sent

    class FakeConn:
        def __init__(self):
            self.conn = real_connect()
        def __getattr__(self, name):
            return getattr(self.conn, name)
        def execute(self, sql, args=()):
            if args and args[0] == "fake-new":
                q = parse_qs(urlsplit(sent[-1]).query)
                body = q.get("text", [""])[0]
                tags = [t.lower() for t in re.findall(r'data-upnote-tag="#([^"]+)"', body)]
                body = re.sub(r"<(?:br|/?(?:div|p|li|ul|ol|h[1-6]|pre|blockquote|tr|td|th|table))\b[^>]*>", "\n", body, flags=re.I)
                text = stored["text"] or q.get("title", [""])[0] + "\n" + srv.html_lib.unescape(re.sub(r"<[^<>]+>", "", body))
                return types.SimpleNamespace(fetchone=lambda: {"text": text, "tagLinks": json.dumps(tags)})
            return self.conn.execute(sql, args)
    srv._connect = FakeConn
    srv._find_created_note = lambda marker, path=None: {"id": "fake-new", "trashed": False, "notebooks": [path] if path else [], "tags": []}
    srv._wait_for_tags = lambda note, tags: []
    srv._set_trashed = lambda nid, trashed: {"confirmed": True, "revision": None}
    srv.time = types.SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic, time=time.time)
    try:
        with srv.closing(real_connect()) as conn:
            tagged = conn.execute("SELECT id, tagLinks, revision FROM notes WHERE deleted=0 AND trashed=0 AND tagLinks LIKE '[\"%' "
                                  "AND (fileIds IS NULL OR fileIds = '[]') AND html NOT LIKE '%<img%' AND html NOT LIKE '%<iframe%'").fetchall()
        refused = []
        for nid, tl, rev in tagged:
            with srv.closing(real_connect()) as c:
                tag = srv._tag_titles(c, srv._json_list(tl))[0]
            try:
                res = srv._replace(nid, remove_tags=[tag], expected_revision=rev, acknowledge_warnings=True)
            except srv.ToolError:
                continue  # refused at preview, before anything would be sent
            if not res.get("done"):
                refused.append((nid, res.get("message", "")[:90]))
        check("removing a tag keeps the body and passes the checks after the copy", tagged and not refused,
              f"{len(refused)} of {len(tagged)}: {refused[:2]}")

        # an append, and a replace_note given the note's own HTML, on every note a preview accepts
        with srv.closing(real_connect()) as conn:
            notes = conn.execute("SELECT id, html, text, revision FROM notes WHERE deleted=0 AND trashed=0 AND (fileIds IS NULL OR fileIds = '[]') "
                                 "AND html NOT LIKE '%<img%' AND html NOT LIKE '%<iframe%'").fetchall()
        failed, unwrapped, tried = {"append": [], "own html": []}, [], 0
        for nid, html, text, rev in notes:
            try:
                token = srv.append_to_note(nid, "Appended line here")["preview_token"]
            except srv.ToolError:
                continue
            tried += 1
            accepted = (nid, html, text, rev)
            stored["text"] = (text or "") + "\nAppended line here"
            if not (res := srv.append_to_note(nid, "Appended line here", rev, True, token)).get("done"):
                failed["append"].append((nid, res.get("message", "")[:90]))
            stored["text"] = text or ""
            if not (res := srv._replace(nid, text=html, expected_revision=rev, acknowledge_warnings=True)).get("done"):
                failed["own html"].append((nid, res.get("message", "")[:90]))
            body = parse_qs(urlsplit(sent[-1]).query).get("text", [""])[0]
            if re.match(r"\s*[^<\s]", body) and re.search(r"<(?:br|div|p|ul|ol|li|pre)\b", body):
                unwrapped.append(nid)
        for kind, bad in failed.items():
            check(f"{kind}: every rebuild passes the checks after the copy", tried and not bad, f"{len(bad)} of {tried}: {bad[:2]}")
        stored["text"] = None
        check("own HTML that starts with bare text is sent inside a <div>", not unwrapped, str(unwrapped[:3]))
        nid, html, text, rev = accepted
        stored["text"] = (text or "").split("\n")[0] + "\nStatus: done\nNext: ship"
        srv._replace(nid, text="**Status:** done<br>**Next:** ship", expected_revision=rev, acknowledge_warnings=True)
        stored["text"] = None
        body = parse_qs(urlsplit(sent[-1]).query).get("text", [""])[0]
        check("Markdown with a <br> isn't taken for the note's HTML", body.startswith("**Status:**"), body[:60])

        # round 7: what a caller is told
        with srv.closing(real_connect()) as conn:
            pair = conn.execute("SELECT t.id, l.id FROM notes t JOIN notes l ON l.title = t.title AND l.trashed = 0 AND l.deleted = 0 "
                                "WHERE t.trashed = 1 AND t.deleted = 0 AND t.title != '' AND (SELECT count(*) FROM notes x WHERE "
                                "x.title = t.title AND x.trashed = 0 AND x.deleted = 0) = 1").fetchone()
            two_h2 = [x for x in conn.execute("SELECT id, title, html FROM notes WHERE deleted=0 AND trashed=0 AND html LIKE '<h2>%</h2><h2>%'")
                      if x[2].startswith(f"<h2>{srv.html_lib.escape(x[1] or '', quote=False)}</h2><h2>")]
            bare = next((x for x in notes if re.match(r"\s*[^<\s]", srv._strip_title_heading(x[1] or "", "")
                         .split("</h2>", 1)[-1]) and "<div>" in (x[1] or "")), None)
        if pair:
            try:
                srv._replace(pair[0]); check("a trashed id names the live version", False, "no error")
            except srv.ToolError as e:
                check("a trashed id names the live version", pair[1] in str(e) and "Restore it" not in str(e), str(e)[:120])
        for nid, title, html in two_h2[:3]:
            try:
                srv._current_body(nid); ok = True
            except srv.ToolError as e:
                ok = str(e)
            check(f"a title heading followed by another heading can be rebuilt: {title[:30]!r}", ok is True, str(ok)[:80])
        nid, html, text, rev = accepted
        check("a rename's preview shows the new title", srv._replace(nid, title="Brand new title").get("new_title") == "Brand new title")
        prev = srv.append_to_note(nid, "<b onclick=x()>hi</b>")
        check("an append's unsafe-text warning asks for acknowledgement", "acknowledge_warnings" in prev["next_step"]
              and any("unsafe" in w for w in prev["warnings"]), prev["next_step"])
        try:
            srv.append_to_note(nid, "<b onclick=x()>hi</b>", rev, False, prev["preview_token"])
            check("  and the apply needs it", False, "no error")
        except srv.ToolError as e:
            check("  and the apply needs it", "warnings" in str(e), str(e)[:80])
        srv._find_created_note = lambda marker, path=None: None
        res = srv._replace(nid, title="Brand new title", expected_revision=rev, acknowledge_warnings=True)
        check("a copy that didn't appear is findable by its marker", "run_select" in res["message"] and "data-upnote-mcp" in res["message"], res["message"][:80])
        try:
            srv._replace(nid, title="Brand new title", expected_revision=rev, acknowledge_warnings=True)
            check("  and a retry doesn't send a second create link", False, "no error")
        except srv.ToolError as e:
            check("  and a retry doesn't send a second create link", "may still appear" in str(e), str(e)[:80])
        with srv.closing(real_connect()) as conn:
            trashed_marker = conn.execute("SELECT html FROM notes WHERE trashed = 1 AND deleted = 0 AND html LIKE '%data-upnote-mcp=%'").fetchone()
        if trashed_marker:
            srv._PENDING[nid] = (re.search(r'data-upnote-mcp="([^"]*)"', trashed_marker[0]).group(1), time.monotonic())
            srv._find_created_note = lambda marker, path=None: {"id": "fake-new", "trashed": False, "notebooks": [path] if path else [], "tags": []}
            stored["text"] = text or ""
            res = srv._replace(nid, expected_revision=rev, acknowledge_warnings=True)
            stored["text"] = None
            check("  a late copy the user trashed doesn't block the note", res.get("done") and nid not in srv._PENDING, str(res)[:100])
        srv._PENDING.clear()
        srv._find_created_note = lambda marker, path=None: {"id": "fake-new", "trashed": False, "notebooks": [path] if path else [], "tags": []}

        # UpNote's list wipe (2026-10-11): the notebook's list comes back holding only the new note
        real_members = srv._notebook_members
        calls = []
        srv._notebook_members = lambda nb: (calls.append(nb) or (["a", "b", "c"] if len(calls) % 2 else ["fake-new"]))
        try:
            nid, html, text, rev = accepted
            stored["text"] = text or ""
            res = srv._replace(nid, title="Wipe test", expected_revision=rev, acknowledge_warnings=True)
            check("a rebuild that wipes the notebook's list keeps the original and says so",
                  not res.get("done") and res.get("notebook_members_lost", {}).get("missing") == 3, str(res)[:120])
            with srv.closing(real_connect()) as conn:
                nb = next(v for v in srv._notebooks(conn).values() if not srv._same_title_notebooks(srv._notebooks(conn), v["id"]))
            res = srv.create_note("Wipe test", "x", notebook=nb["id"])
            check("  and create_note reports it", res.get("notebook_members_lost", {}).get("missing_note_ids") == ["a", "b", "c"], str(res)[:120])
        finally:
            srv._notebook_members = real_members
            stored["text"] = None
        if bare:
            nid, html, text, rev = bare
            stored["text"] = text or ""
            edited = re.sub(r"(<h2>.*?</h2>\s*)(\w)", r"\1EDITED\2", html, count=1, flags=re.S)
            srv._replace(nid, text=edited, expected_revision=rev, acknowledge_warnings=True)
            stored["text"] = None
            body = parse_qs(urlsplit(sent[-1]).query).get("text", [""])[0]
            check("own HTML edited in its first line is still sent inside a <div>", body.startswith("<div>"), body[:60])
            stored["text"] = (text or "") + "\nSummary\nStatus: done"
            srv._replace(nid, text="## Summary\n\n**Status:** done\n\n" + html, expected_revision=rev, acknowledge_warnings=True)
            stored["text"] = None
            body = parse_qs(urlsplit(sent[-1]).query).get("text", [""])[0]
            check("Markdown written before the note's own HTML stays Markdown", body.startswith("## Summary"), body[:60])
    finally:
        srv._connect, srv._find_created_note, srv._wait_for_tags, srv._set_trashed, srv.time = real_connect, real_find, real_wait, real_trash, real_time
    print("FAILURES:", fails)
asyncio.run(main())
sys.exit(1 if fails else 0)
