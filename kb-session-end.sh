#!/bin/sh
# Records a reminder when a substantive session ends without an experience entry.
# The next SessionStart hook surfaces it while a model can act on it.
set -u

KB_ROOT="${KB_ROOT:-$HOME/.claude/knowledge}"
STATE_ROOT="${KB_SESSION_STATE_ROOT:-$HOME/.claude/kb-session}"
EXPERIENCES="$KB_ROOT/experiences"
MARKERS="$STATE_ROOT/markers"
DEBT="$STATE_ROOT/experience-debt"
DECISIONS="$STATE_ROOT/experience-decisions.log"
MIN_TOOL_USES="${KB_EXPERIENCE_MIN_TOOL_USES:-20}"

[ -d "$EXPERIENCES" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)

mkdir -p "$STATE_ROOT" 2>/dev/null || exit 0
project=$(basename "${cwd:-unknown}")
tool_uses=0

log_decision() {
    printf '%s\t%s\t%s\t%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$project" "$tool_uses" "$1" \
        >> "$DECISIONS"
}

# Logged rather than skipped silently, so a session missing from the log means the
# hook did not run, not that it ran without the input it needs.
if [ -z "$transcript" ] || [ ! -f "$transcript" ] || [ -z "$session_id" ]; then
    log_decision no-payload
    exit 0
fi

# The id becomes a filename. Real ids are letters, digits, - and _; anything else
# could point outside the markers directory.
case "$session_id" in
    *[!A-Za-z0-9_-]*)
        log_decision bad-session-id
        exit 0
        ;;
esac

case "$MIN_TOOL_USES" in
    ''|*[!0-9]*)
        exit 0
        ;;
esac

tool_uses=$(grep -c '"type":"tool_use"' "$transcript" 2>/dev/null || true)
[ -n "$tool_uses" ] || tool_uses=0

if [ "$tool_uses" -lt "$MIN_TOOL_USES" ]; then
    log_decision below-threshold
    exit 0
fi

marker="$MARKERS/$session_id.start"
if [ ! -f "$marker" ]; then
    log_decision no-marker
    exit 0
fi

if find "$EXPERIENCES" -maxdepth 1 -type f -name '*.md' -newer "$marker" -print -quit 2>/dev/null \
    | grep -q .; then
    rm -f "$marker"
    log_decision entry-written
    exit 0
fi

rm -f "$marker"
log_decision flagged
printf '%s\t%s\t%s tool uses\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$project" "$tool_uses" >> "$DEBT"
