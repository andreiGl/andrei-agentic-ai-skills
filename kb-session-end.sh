#!/bin/sh
# Records a reminder when a substantive session ends without an experience entry.
# The next SessionStart hook surfaces it while a model can act on it.
set -u

HOOKS_ENV="${KB_HOOKS_ENV:-$HOME/.claude/kb-hooks.env}"
# shellcheck disable=SC1090
[ -f "$HOOKS_ENV" ] && . "$HOOKS_ENV"

KB_ROOT="${KB_ROOT:-$HOME/.claude/knowledge}"
STATE_ROOT="${KB_SESSION_STATE_ROOT:-$HOME/.claude/kb-session}"
EXPERIENCES="$KB_ROOT/experiences"
MARKERS="$STATE_ROOT/markers"
DEBT="$STATE_ROOT/experience-debt"
DECISIONS="$STATE_ROOT/experience-decisions.log"
BANKED="$STATE_ROOT/banked-sessions"
MIN_TOOL_USES="${KB_EXPERIENCE_MIN_TOOL_USES:-20}"

# KB_SESSION_END_AUTOCOMMIT=1 runs kb-autocommit.sh after this script, on every
# exit path, for an install that wires it here instead of as its own SessionEnd
# hook. Sequential, so the debt this script writes is never raced.
input=
finish() {
    if [ "${KB_SESSION_END_AUTOCOMMIT:-0}" = 1 ]; then
        printf '%s' "$input" | sh "${KB_AUTOCOMMIT_SCRIPT:-$HOME/.claude/kb-autocommit.sh}"
    fi
    exit 0
}

[ -d "$EXPERIENCES" ] || finish
command -v jq >/dev/null 2>&1 || finish

input=$(cat)
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)

mkdir -p "$STATE_ROOT" 2>/dev/null || finish
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
    finish
fi

# The id becomes a filename. Real ids are letters, digits, - and _; anything else
# could point outside the markers directory.
case "$session_id" in
    *[!A-Za-z0-9_-]*)
        log_decision bad-session-id
        finish
        ;;
esac

# A typo here must not switch the check off, so anything that is not a plain number
# of at most 9 digits, or is zero, falls back to the default. Ten digits and up can
# pass the digit test and still overflow sh's integer comparison. Leading zeros
# read as decimal ("007" is 7), as in the kb-actions mod's debtToolThresholdOf:
# the surfaces must agree on one rule.
case "$MIN_TOOL_USES" in
    ''|*[!0-9]*|??????????*) MIN_TOOL_USES=20 ;;
esac
MIN_TOOL_USES=$(printf '%s' "$MIN_TOOL_USES" | sed 's/^0*//')
[ -n "$MIN_TOOL_USES" ] || MIN_TOOL_USES=20

tool_uses=$(grep -c '"type":"tool_use"' "$transcript" 2>/dev/null || true)
[ -n "$tool_uses" ] || tool_uses=0
marker="$MARKERS/$session_id.start"

# A session that wrote an entry is done. A resumed session ends again after every
# restart, and flagging those later ends would ask for an entry it already wrote.
if [ -f "$BANKED" ] && grep -qxF "$session_id" "$BANKED"; then
    rm -f "$marker"
    log_decision already-banked
    finish
fi

# No marker usually means the session cannot be attributed (the hook was
# installed mid-session). But the heaviest sessions on record had no marker
# either, and skipping them exempts the work most worth an entry, so far past
# the threshold - five times it - a session is flagged anyway.
if [ ! -f "$marker" ]; then
    if [ "$tool_uses" -ge "$((MIN_TOOL_USES * 5))" ]; then
        log_decision flagged-no-marker
        printf '%s\t%s\t%s tool uses\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$project" "$tool_uses" >> "$DEBT"
    else
        log_decision no-marker
    fi
    finish
fi

# New entry: a name in experiences/ that the marker did not list and that this
# session's transcript mentions, since writing the file names it. Without the second
# test, an entry another session wrote meanwhile would clear this one too. A marker
# written before snapshots existed has no header line and falls back to file times.
entry_written=no
if head -n 1 "$marker" | grep -q '^#tool_uses '; then
    start_uses=$(head -n 1 "$marker" | cut -d' ' -f2)
    case "$start_uses" in ''|*[!0-9]*) start_uses=0 ;; esac
    for f in "$EXPERIENCES"/*.md; do
        [ -f "$f" ] || continue
        name=$(basename "$f")
        if ! tail -n +2 "$marker" | grep -qxF "$name" && grep -qF "$name" "$transcript"; then
            entry_written=yes
            break
        fi
    done
    # A synthesis-only session banks through its distillation file in archive/,
    # under the same two tests: new since the marker, and named in the transcript.
    if [ "$entry_written" = no ]; then
        for f in "$EXPERIENCES"/archive/*.md; do
            [ -f "$f" ] || continue
            name=$(basename "$f")
            if ! tail -n +2 "$marker" | grep -qxF "archive/$name" && grep -qF "archive/$name" "$transcript"; then
                entry_written=yes
                break
            fi
        done
    fi
else
    start_uses=0
    find "$EXPERIENCES" -maxdepth 1 -type f -name '*.md' -newer "$marker" -print -quit 2>/dev/null \
        | grep -q . && entry_written=yes
fi

# Only the work since the marker counts; the transcript of a resumed session also
# holds everything before it.
tool_uses=$((tool_uses - start_uses))
[ "$tool_uses" -ge 0 ] || tool_uses=0

if [ "$entry_written" = yes ]; then
    rm -f "$marker"
    printf '%s\n' "$session_id" >> "$BANKED"
    # Kept short: only sessions that may still resume need to be in it.
    if [ "$(wc -l < "$BANKED")" -gt 500 ]; then
        tail -n 200 "$BANKED" > "$BANKED.tmp" && mv "$BANKED.tmp" "$BANKED"
    fi
    log_decision entry-written
    finish
fi

# Below the threshold the marker stays, so work across several resumes adds up.
if [ "$tool_uses" -lt "$MIN_TOOL_USES" ]; then
    log_decision below-threshold
    finish
fi

rm -f "$marker"
log_decision flagged
printf '%s\t%s\t%s tool uses\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$project" "$tool_uses" >> "$DEBT"
finish
