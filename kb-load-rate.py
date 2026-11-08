#!/usr/bin/env python3
"""How often sessions load the knowledge base.

Usage: kb-load-rate.py [--from YYYY-MM-DD[THH:MM]] [--to YYYY-MM-DD[THH:MM]]
                       [--root DIR] [--exclude SUBSTRING]...

Definitions (fixed here so two runs count the same way):
- A session is one top-level <project>/<id>.jsonl under the projects root.
  Subagent transcripts (<id>/subagents/) are not sessions and are not read.
- A session belongs to the window by its START: the first event timestamp in
  the file, not the file's mtime. A resumed session counts once, by its start.
- A session has tool work when it holds at least one tool_use named Bash, Read,
  Edit, Write, Grep or Glob.
- A session loaded the KB when it holds a tool_use named Skill whose
  input.skill is "load-knowledge". A mention in text never counts.

Prints one line per project and a total: sessions with tool work, how many
loaded the KB, and the rate. A rate on fewer than 15 sessions is marked
LOW-N: one session moves it by more than 6 points.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

TOOL_WORK = {"Bash", "Read", "Edit", "Write", "Grep", "Glob"}
MIN_N = 15


def parse_when(value):
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.astimezone()  # local time when no zone given


def scan(path):
    """Return (start, has_tool_work, loaded_kb) for one transcript."""
    start, work, loaded = None, False, False
    with open(path, errors="replace") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            if start is None and ev.get("timestamp"):
                try:
                    start = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
                except ValueError:
                    pass
            msg = ev.get("message")
            if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
                continue
            for c in msg["content"]:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                name = c.get("name")
                if name in TOOL_WORK:
                    work = True
                elif name == "Skill" and (c.get("input") or {}).get("skill") == "load-knowledge":
                    loaded = True
    return start, work, loaded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--exclude", action="append", default=[],
                    help="skip project folders whose name contains this text")
    a = ap.parse_args()
    lo, hi = parse_when(a.start), parse_when(a.end)

    per = {}
    for proj in sorted(os.listdir(a.root)):
        pdir = os.path.join(a.root, proj)
        if not os.path.isdir(pdir) or any(x in proj for x in a.exclude):
            continue
        for name in os.listdir(pdir):
            if not name.endswith(".jsonl"):
                continue
            start, work, loaded = scan(os.path.join(pdir, name))
            if start is None or not work:
                continue
            if (lo and start < lo) or (hi and start >= hi):
                continue
            n, k = per.get(proj, (0, 0))
            per[proj] = (n + 1, k + loaded)

    def line(label, n, k):
        rate = f"{100 * k / n:.0f}%" if n else "-"
        flag = "  LOW-N" if n < MIN_N else ""
        return f"{k:4d}/{n:<4d} {rate:>5}{flag}  {label}"

    for proj, (n, k) in sorted(per.items(), key=lambda x: -x[1][0]):
        print(line(proj, n, k))
    tn = sum(n for n, _ in per.values())
    tk = sum(k for _, k in per.values())
    print(line("TOTAL", tn, tk))


if __name__ == "__main__":
    sys.exit(main())
