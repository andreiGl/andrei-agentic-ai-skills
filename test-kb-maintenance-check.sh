#!/bin/sh
# Runs isolated synthetic checks against kb-maintenance-check.py.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT
KB_ROOT="$TEST_ROOT/knowledge"
mkdir -p "$KB_ROOT/experiences/archive"

run() {
    printf '%s\n' '{}' | KB_ROOT="$KB_ROOT" python3 "$ROOT/kb-maintenance-check.py"
}

expect_silent() {
    out=$(run)
    [ -z "$out" ]
}

expect_line() {
    out=$(run)
    printf '%s\n' "$out" | grep -q "$1"
}

set_dates() {
    printf '**Last verified:** %s\n**Last synthesized:** %s\n' "$1" "$2" > "$KB_ROOT/INDEX.md"
}

add_entries() {
    for i in $(seq 1 "$1"); do echo "# entry $i" > "$KB_ROOT/experiences/e$i.md"; done
}

# No INDEX.md at all: an absent knowledge base stays silent.
expect_silent

# Empty knowledge base with template "never" dates: silent until content lands.
set_dates never never
: > "$KB_ROOT/learnings.md"
expect_silent

# First entry with template dates: synthesize due (its age trigger has no date),
# and the age trigger is the one that fires.
echo "# first" > "$KB_ROOT/experiences/e1.md"
expect_line 'synthesize-knowledge'
expect_line 'Last synthesized is never'

# A datetime stamp (typo) reads as missing, not as a value to parse a prefix from.
# Synth is fresh so the age trigger stays quiet and the typo is what nags.
# The strict scan discards the malformed value, so the check fires via its
# missing-stamp path; assert the check fires and no raw None leaks into the note.
set_dates "2026-10-07T10:00:00Z" "2026-10-07"
expect_line 'check-knowledge'

# Fresh dates, five experience entries: synthesize due on the count trigger.
set_dates 2026-10-07 2026-10-07
add_entries 5
expect_line 'experiences/ holds 5 entries'

# Twenty-one learnings entries: synthesize due on the learnings trigger.
add_entries 2
for i in $(seq 1 21); do printf '\n## e%d\n**Rule:** x\n' "$i" >> "$KB_ROOT/learnings.md"; done
expect_line 'learnings.md holds 21 entries'

# Reset counts to one entry / one learnings entry; synthesis old, verification
# current: synthesize due on the age trigger alone (counts below thresholds).
for i in $(seq 3 7); do rm -f "$KB_ROOT/experiences/e$i.md"; done
grep -v '^## ' "$KB_ROOT/learnings.md" > "$KB_ROOT/learnings.md.tmp"
printf '\n## 2026-09-01 - one entry\n' >> "$KB_ROOT/learnings.md.tmp"
mv "$KB_ROOT/learnings.md.tmp" "$KB_ROOT/learnings.md"
set_dates 2026-10-07 2026-07-01
expect_line 'last synthesized 2026-07-01'

# Everything current: silent.
set_dates 2026-10-07 2026-10-07
expect_silent

# Synthesis current, verification old: check-knowledge due.
set_dates 2026-08-01 2026-10-07
expect_line 'check-knowledge'

printf '%s\n' 'Synthetic maintenance checks passed.'
