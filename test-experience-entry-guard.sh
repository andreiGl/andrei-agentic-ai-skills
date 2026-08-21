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
end "{\"session_id\":\"entry\",\"transcript_path\":\"$TEST_ROOT/long.jsonl\",\"cwd\":\"/tmp/project-entry\"}" > "$TEST_ROOT/entry.out"
[ ! -s "$TEST_ROOT/entry.out" ]
grep -q 'entry-written' "$STATE_ROOT/experience-decisions.log"

start '{"session_id":"resume","source":"startup"}'
resume_marker="$STATE_ROOT/markers/resume.start"
before=$(stat -f %m "$resume_marker" 2>/dev/null || stat -c %Y "$resume_marker")
sleep 1
start '{"session_id":"resume","source":"resume"}'
after=$(stat -f %m "$resume_marker" 2>/dev/null || stat -c %Y "$resume_marker")
[ "$before" = "$after" ]

printf '%s\n' 'Synthetic hook checks passed.'
