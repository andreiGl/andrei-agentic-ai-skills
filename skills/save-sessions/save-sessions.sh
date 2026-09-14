#!/usr/bin/env bash
# save-sessions.sh — snapshot recently-active Claude Code sessions to ~/.claude/saved-sessions.json
# Usage: save-sessions.sh [window-hours]   (default: 24)
set -euo pipefail

WINDOW_HOURS="${1:-24}"
SESSIONS_ROOT="$HOME/.claude/projects"
OUT_FILE="$HOME/.claude/saved-sessions.json"

[[ -d "$SESSIONS_ROOT" ]] || { echo "No Claude sessions dir: $SESSIONS_ROOT" >&2; exit 1; }

python3 - "$SESSIONS_ROOT" "$WINDOW_HOURS" "$OUT_FILE" <<'PY'
import json, os, sys, time

root, window, out = sys.argv[1], sys.argv[2], sys.argv[3]
cutoff = time.time() - float(window) * 3600
out_path = os.path.expanduser(out)

sessions = []
for dirpath, _, files in os.walk(root):
    for fn in files:
        if not fn.endswith(".jsonl"):
            continue
        path = os.path.join(dirpath, fn)
        try:
            if os.path.getmtime(path) < cutoff:
                continue
            sid = fn[:-6]
            cwd = last_prompt = entrypoint = None
            n_lines = 0
            # Custom title (from /rename or --name) lives in a sidecar file,
            # not in the transcript itself.
            title = None
            title_path = os.path.join(dirpath, sid, "custom-title.json")
            if os.path.isfile(title_path):
                try:
                    with open(title_path, encoding="utf-8") as tf:
                        title = json.load(tf).get("customTitle") or None
                except (json.JSONDecodeError, OSError):
                    pass
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    n_lines += 1
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if cwd is None and rec.get("cwd"):
                        cwd = rec["cwd"]
                    if entrypoint is None and rec.get("entrypoint"):
                        entrypoint = rec["entrypoint"]
                    if rec.get("type") == "user":
                        c = rec.get("message", {}).get("content")
                        if isinstance(c, str):
                            text = c
                        elif isinstance(c, list):
                            text = " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
                        else:
                            continue
                        text = text.strip()
                        if text and not text.startswith("<"):  # skip system-injected user records
                            last_prompt = text[:120]
            if n_lines == 0 or last_prompt is None:
                continue  # empty or no real user turns
            # Subagent (Agent-tool / SDK) transcripts look like real sessions but are
            # never interactive work. They carry entrypoint "sdk-cli"; real ones "cli".
            if entrypoint == "sdk-cli":
                continue
            sessions.append({
                "sessionId": sid,
                "cwd": cwd or os.path.expanduser("~"),
                "summary": title,
                "lastPrompt": last_prompt,
                "mtime": os.path.getmtime(path),
            })
        except OSError:
            continue

sessions.sort(key=lambda s: -s["mtime"])

# The current session: deterministic env var when running inside Claude,
# newest-modified transcript otherwise.
current_sid = os.environ.get("CLAUDE_CODE_SESSION_ID") or (
    sessions[0]["sessionId"] if sessions else None)

for s in sessions:
    s["current"] = s["sessionId"] == current_sid
    del s["mtime"]

# Merge with the existing save file: keep entries not re-captured (e.g. sessions
# saved Friday, re-saving Monday with a 24h window), replace same-id entries.
existing = []
if os.path.isfile(out_path):
    try:
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f).get("sessions", [])
    except (json.JSONDecodeError, OSError):
        existing = []
captured = {s["sessionId"] for s in sessions}

def is_subagent(sid):
    # Check the transcript's first entrypoint marker for kept entries.
    for dirpath, _, files in os.walk(root):
        if sid + ".jsonl" in files:
            try:
                with open(os.path.join(dirpath, sid + ".jsonl"),
                          encoding="utf-8", errors="replace") as f:
                    for _ in range(20):
                        line = f.readline()
                        if not line:
                            break
                        if '"entrypoint":"sdk-cli"' in line:
                            return True
                        if '"entrypoint":"cli"' in line:
                            return False
            except OSError:
                pass
            break
    return False

merged = sessions + [
    e for e in existing
    if e.get("sessionId") not in captured
    and not is_subagent(e["sessionId"])  # drop stragglers an older save captured
]


doc = {
    "savedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "windowHours": int(window),
    "currentSessionId": current_sid,
    "sessions": merged,
}
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2)

print(f"Saved {len(sessions)} session(s) to {out_path} ({len(merged)} total incl. kept older entries)")
for s in merged:
    mark = " *" if s.get("current") else "  "
    print(f" {mark} {s['sessionId'][:8]}  {(s['summary'] or s['lastPrompt'])[:70]}  [{s['cwd']}]")
PY
