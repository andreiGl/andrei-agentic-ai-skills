#!/bin/sh
# Two jobs, in order:
#   1. Stamp a marker whose mtime is when this stretch of work began.
#      kb-session-end.sh compares experience files against it with find -newer.
#   2. Surface any session that ended without an experience entry. Plain stdout
#      from a SessionStart hook is added to the transcript as context Claude sees.
set -u

KB="$HOME/.claude/knowledge"
[ -d "$KB/experiences" ] || exit 0

input=$(cat)
sid=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
src=$(printf '%s' "$input" | jq -r '.source // empty' 2>/dev/null)

mkdir -p "$KB/.sessions"
find "$KB/.sessions" -name '*.start' -mtime +7 -delete 2>/dev/null

case "$src" in
  resume|compact) ;;                                  # same work continuing, keep the window open
  *) [ -n "$sid" ] && : > "$KB/.sessions/$sid.start" ;;
esac

DEBT="$KB/.experience-debt"
[ -s "$DEBT" ] || exit 0

echo "Knowledge base: these earlier sessions ended without an experience entry in ~/.claude/knowledge/experiences/ (date, project, tool calls):"
cat "$DEBT"
echo "Write the missing entries per the update-knowledge skill, or say why they should be skipped."

cat "$DEBT" >> "$DEBT.log"
rm -f "$DEBT"
