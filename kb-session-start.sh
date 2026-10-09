#!/bin/sh
# Stamps a session marker and surfaces any pending experience-entry reminders.
set -u

KB_ROOT="${KB_ROOT:-$HOME/.claude/knowledge}"
STATE_ROOT="${KB_SESSION_STATE_ROOT:-$HOME/.claude/kb-session}"
EXPERIENCES="$KB_ROOT/experiences"
MARKERS="$STATE_ROOT/markers"
DEBT="$STATE_ROOT/experience-debt"
NOTICE="$STATE_ROOT/autocommit-notice"
FALLBACK_NOTICE="${KB_AUTOCOMMIT_FALLBACK_NOTICE:-$HOME/.claude/kb-autocommit-notice}"

# kb-autocommit.sh runs at SessionEnd, where nobody sees its output, so its failures
# wait here. The fallback file is written when the state directory itself was not
# writable; it is printed but kept until that directory works again to take it.
for f in "$NOTICE" "$FALLBACK_NOTICE"; do
    [ -s "$f" ] || continue
    printf '%s\n' 'Knowledge base backup needs attention (kb-autocommit.sh):'
    cut -f2- "$f"
    if [ "$f" = "$NOTICE" ] || { mkdir -p "$STATE_ROOT" 2>/dev/null && [ -w "$STATE_ROOT" ]; }; then
        cat "$f" >> "$STATE_ROOT/autocommit.log" 2>/dev/null && : > "$f"
    fi
done

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

# The id becomes a filename. Real ids are letters, digits, - and _; anything else
# could point outside the markers directory.
case "$session_id" in
    ''|*[!A-Za-z0-9_-]*) exit 0 ;;
esac

mkdir -p "$MARKERS" 2>/dev/null || exit 0
find "$MARKERS" -name '*.start' -mtime +7 -delete 2>/dev/null

case "$source" in
    resume|compact)
        ;;
    *)
        : > "$MARKERS/$session_id.start"
        ;;
esac
