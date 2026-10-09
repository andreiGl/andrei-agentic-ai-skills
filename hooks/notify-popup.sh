#!/bin/sh
# macOS popup showing which Claude Code session needs attention.
# Reads hook JSON on stdin; optional $1 is an event label shown in the
# notification subtitle. Falls back to first user prompt when the
# session has no custom title.

event_label=${1:-}
input=$(cat)
transcript=$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("transcript_path", ""))
except Exception:
    print("")' 2>/dev/null)
[ -n "$transcript" ] || exit 0

title=""
if [ -f "$transcript" ]; then
  title=$(grep '"customTitle"' "$transcript" | tail -1 | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("customTitle", ""))
except Exception:
    print("")' 2>/dev/null)
fi

if [ -z "$title" ] && [ -f "$transcript" ]; then
  title=$(python3 - "$transcript" <<'PYEOF'
import json, sys
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try:
        d = json.loads(line)
    except ValueError:
        continue
    if d.get("type") != "user" or d.get("isSidechain"):
        continue
    content = d.get("message", {}).get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text")
    else:
        continue
    text = text.strip()
    if text and not text.startswith("<"):
        print(text[:80])
        break
PYEOF
)
fi

[ -n "$title" ] || title="Claude Code"
osascript - "$title" "$event_label" <<'EOF'
on run argv
  display notification item 1 of argv with title "Claude Code" subtitle item 2 of argv
end run
EOF

# Toast window in addition to the system banner; skip if binary missing.
if [ -x "$HOME/.claude/hooks/toast/Toast" ] && [ -n "$event_label" ]; then
  "$HOME/.claude/hooks/toast/Toast" "$title" "$event_label" >/dev/null 2>&1 &
fi
