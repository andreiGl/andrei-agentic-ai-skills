#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==2.2.0"]
# ///
"""Read-only check of the UpNote MCP server against your own UpNote library.

Starts server.py from this folder over stdio, calls every read tool, and compares each result
with a direct read-only query on the database. Also sends writes through run_select and expects
every one to be refused. Changes nothing. Exits non-zero if any check fails.
"""
import asyncio, json, os, sqlite3, sys
from pathlib import Path
from urllib.parse import quote
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
    params = StdioServerParameters(command="uv", args=["run", "--script", SERVER])
    async with stdio_client(params) as (rd, wr):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            check("twelve tools", sorted(tools) == sorted(["search_notes","list_notes","get_note","list_notebooks","list_tags","run_select","create_note","move_note_to_trash","restore_note","replace_note","open_in_upnote","check_upnote_setup"]), ",".join(sorted(tools)))
            check("read tools marked read-only", all(tools[n].annotations.read_only_hint for n in tools if n not in ("create_note", "move_note_to_trash", "restore_note", "replace_note")))
            check("create_note not read-only", tools["create_note"].annotations.read_only_hint is False)

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

            err, d, _ = await call(s, "list_notes", notebook=biggest["path"], limit=100)
            check("notebook filter covers at least its direct notes", not err and d["total"] >= biggest["note_count"], f"{d['total']} >= {biggest['note_count']}")
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
    print("FAILURES:", fails)
asyncio.run(main())
sys.exit(1 if fails else 0)
