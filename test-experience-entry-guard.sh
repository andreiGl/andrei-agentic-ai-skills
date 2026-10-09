#!/bin/sh
# Runs isolated synthetic checks against the two hook scripts.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT
KB_ROOT="$TEST_ROOT/knowledge"
STATE_ROOT="$TEST_ROOT/state"
mkdir -p "$KB_ROOT/experiences/archive"

start() {
    printf '%s\n' "$1" | KB_ROOT="$KB_ROOT" KB_SESSION_STATE_ROOT="$STATE_ROOT" \
        sh "$ROOT/kb-session-start.sh"
}

end() {
    printf '%s\n' "$1" | KB_ROOT="$KB_ROOT" KB_SESSION_STATE_ROOT="$STATE_ROOT" \
        KB_EXPERIENCE_MIN_TOOL_USES=20 sh "$ROOT/kb-session-end.sh"
}

for number in $(seq 1 20); do
    printf '%s\n' '{"type":"tool_use"}'
done > "$TEST_ROOT/long.jsonl"

start '{"session_id":"short","source":"startup"}'
printf '%s\n' '{"type":"tool_use"}' > "$TEST_ROOT/short.jsonl"
end "{\"session_id\":\"short\",\"transcript_path\":\"$TEST_ROOT/short.jsonl\",\"cwd\":\"/tmp/project-short\"}" > "$TEST_ROOT/short.out"
[ ! -s "$TEST_ROOT/short.out" ]
grep -q 'below-threshold' "$STATE_ROOT/experience-decisions.log"

start '{"session_id":"missing","source":"startup"}'
end "{\"session_id\":\"missing\",\"transcript_path\":\"$TEST_ROOT/long.jsonl\",\"cwd\":\"/tmp/project-missing\"}" > "$TEST_ROOT/missing.out"
[ ! -s "$TEST_ROOT/missing.out" ]
grep -q 'project-missing' "$STATE_ROOT/experience-debt"
grep -q 'flagged' "$STATE_ROOT/experience-decisions.log"

start '{"session_id":"archive","source":"startup"}'
touch "$KB_ROOT/experiences/archive/ignored.md"
end "{\"session_id\":\"archive\",\"transcript_path\":\"$TEST_ROOT/long.jsonl\",\"cwd\":\"/tmp/project-archive\"}" > "$TEST_ROOT/archive.out"
[ ! -s "$TEST_ROOT/archive.out" ]
grep -q 'project-archive' "$STATE_ROOT/experience-debt"

start '{"session_id":"entry","source":"startup"}'
touch "$KB_ROOT/experiences/recorded.md"
{ cat "$TEST_ROOT/long.jsonl"; printf '%s\n' '{"input":"experiences/recorded.md"}'; } > "$TEST_ROOT/entry.jsonl"
end "{\"session_id\":\"entry\",\"transcript_path\":\"$TEST_ROOT/entry.jsonl\",\"cwd\":\"/tmp/project-entry\"}" > "$TEST_ROOT/entry.out"
[ ! -s "$TEST_ROOT/entry.out" ]
grep -q 'entry-written' "$STATE_ROOT/experience-decisions.log"

start '{"session_id":"resume","source":"startup"}'
resume_marker="$STATE_ROOT/markers/resume.start"
before=$(stat -f %m "$resume_marker" 2>/dev/null || stat -c %Y "$resume_marker")
sleep 1
start '{"session_id":"resume","source":"resume"}'
after=$(stat -f %m "$resume_marker" 2>/dev/null || stat -c %Y "$resume_marker")
[ "$before" = "$after" ]

last_decision() { tail -n 1 "$STATE_ROOT/experience-decisions.log" | cut -f4; }
tools() { n=$1; while [ "$n" -gt 0 ]; do printf '%s\n' '{"type":"tool_use"}'; n=$((n - 1)); done; }
payload() { printf '{"session_id":"%s","transcript_path":"%s","cwd":"/tmp/project-%s","source":"%s"}' "$1" "$2" "$1" "${3:-startup}"; }

# Editing an entry that existed at the start does not count as writing one.
touch "$KB_ROOT/experiences/old.md"
start "$(payload edit "$TEST_ROOT/none.jsonl")"
sleep 1; touch "$KB_ROOT/experiences/old.md"
end "$(payload edit "$TEST_ROOT/long.jsonl")" >/dev/null
[ "$(last_decision)" = flagged ]

# An entry another session wrote meanwhile does not clear this one.
start "$(payload other "$TEST_ROOT/none.jsonl")"
touch "$KB_ROOT/experiences/someone-else.md"
end "$(payload other "$TEST_ROOT/long.jsonl")" >/dev/null
[ "$(last_decision)" = flagged ]

# A resumed session whose marker an earlier end removed gets a new one, which starts
# counting from the tool uses already in its transcript.
tools 30 > "$TEST_ROOT/resumed.jsonl"
start "$(payload resumed "$TEST_ROOT/resumed.jsonl" resume)"
[ "$(head -n 1 "$STATE_ROOT/markers/resumed.start")" = '#tool_uses 30' ]
tools 5 >> "$TEST_ROOT/resumed.jsonl"
end "$(payload resumed "$TEST_ROOT/resumed.jsonl")" >/dev/null
[ "$(last_decision)" = below-threshold ]
[ -f "$STATE_ROOT/markers/resumed.start" ]
# Below the threshold the marker stays, so the next part of the session adds to it.
tools 20 >> "$TEST_ROOT/resumed.jsonl"
end "$(payload resumed "$TEST_ROOT/resumed.jsonl")" >/dev/null
[ "$(last_decision)" = flagged ]
tail -n 1 "$STATE_ROOT/experience-debt" | grep -q '25 tool uses'

# A session that wrote an entry is not flagged when it ends again after a resume.
start "$(payload resume "$TEST_ROOT/entry.jsonl" resume)"
end "$(payload entry "$TEST_ROOT/entry.jsonl")" >/dev/null
[ "$(last_decision)" = already-banked ]
start "$(payload entry "$TEST_ROOT/entry.jsonl" resume)"
tools 40 >> "$TEST_ROOT/entry.jsonl"
end "$(payload entry "$TEST_ROOT/entry.jsonl")" >/dev/null
[ "$(last_decision)" = already-banked ]

# A bad threshold falls back to 20 instead of switching the check off.
for bad in abc 0 007 99999999999; do
    start "$(payload "bad$bad" "$TEST_ROOT/none.jsonl")"
    printf '%s\n' "$(payload "bad$bad" "$TEST_ROOT/long.jsonl")" | KB_ROOT="$KB_ROOT" KB_SESSION_STATE_ROOT="$STATE_ROOT" \
        KB_EXPERIENCE_MIN_TOOL_USES=$bad sh "$ROOT/kb-session-end.sh"
    [ "$(last_decision)" = flagged ]
done

# A marker from before snapshots (empty file) still works, by file time.
mkdir -p "$STATE_ROOT/markers"; : > "$STATE_ROOT/markers/legacy.start"
sleep 1; touch "$KB_ROOT/experiences/legacy-entry.md"
end "$(payload legacy "$TEST_ROOT/long.jsonl")" >/dev/null
[ "$(last_decision)" = entry-written ]

# A long debt list is capped at ten lines when shown.
: > "$STATE_ROOT/experience-debt"
for n in $(seq 1 12); do printf '2026-01-01T00:00:00Z\tp%s\t30 tool uses\n' "$n" >> "$STATE_ROOT/experience-debt"; done
start '{"session_id":"cap","source":"startup"}' > "$TEST_ROOT/cap.out"
[ "$(grep -c 'tool uses' "$TEST_ROOT/cap.out")" -eq 10 ]
grep -q '(12 entries total' "$TEST_ROOT/cap.out"
[ "$(grep -c 'tool uses' "$STATE_ROOT/experience-debt.log")" -ge 12 ]

printf '%s\n' 'Synthetic hook checks passed.'
