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
import asyncio, importlib.util, json, os, sqlite3, sys, time
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
            check("read tools marked read-only", all(tools[n].annotations.read_only_hint for n in tools if n not in ("create_note", "move_note_to_trash", "restore_note", "replace_note", "make_section", "append_to_note", "move_note")))
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
            err, _, text = await call(s, "run_select", sql="SELECT length(hex(zeroblob(100000000)))")
            check("run_select refuses a huge value", err and "too big" in text, text[:80])

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
            err, _, text = await call(s, "replace_note", note_id=note[0], text="x", expected_revision=note[1] - 1)
            check("a stale revision is refused", err and "changed since the preview" in text, text[:100])
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
    print("FAILURES:", fails)
asyncio.run(main())
sys.exit(1 if fails else 0)
