#!/bin/sh
# Stamps a session marker and surfaces any pending experience-entry reminders.
set -u

KB_ROOT="${KB_ROOT:-$HOME/.claude/knowledge}"
STATE_ROOT="${KB_SESSION_STATE_ROOT:-$HOME/.claude/kb-session}"
EXPERIENCES="$KB_ROOT/experiences"
MARKERS="$STATE_ROOT/markers"
DEBT="$STATE_ROOT/experience-debt"

[ -d "$EXPERIENCES" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
source=$(printf '%s' "$input" | jq -r '.source // empty' 2>/dev/null)
if [ -s "$DEBT" ]; then
    printf '%s\n' 'Knowledge base: earlier substantive sessions ended without an experience entry:'
    cat "$DEBT"
    printf '%s\n' 'Apply update-knowledge for reusable findings, or explain why an entry is not needed.'
    cat "$DEBT" >> "$STATE_ROOT/experience-debt.log"
    : > "$DEBT"
fi

[ -n "$session_id" ] || exit 0

mkdir -p "$MARKERS" 2>/dev/null || exit 0
find "$MARKERS" -name '*.start' -mtime +7 -delete 2>/dev/null

case "$source" in
    resume|compact)
        ;;
    *)
        : > "$MARKERS/$session_id.start"
        ;;
esac
