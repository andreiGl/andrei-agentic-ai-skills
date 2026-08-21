#!/bin/sh
# Records a note when a substantive session ends without update-knowledge having
# written an experience entry. kb-session-start.sh surfaces the note in the next
# session, since SessionEnd's own stdout only reaches the debug log.
#
# Portable: no stat, no timestamp arithmetic. find -newer does the comparison
# against the marker kb-session-start.sh stamps.
set -u

KB="$HOME/.claude/knowledge"
[ -d "$KB/experiences" ] || exit 0

input=$(cat)
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
sid=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)

[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

project=$(basename "${cwd:-unknown}")
tools=$(grep -c '"type":"tool_use"' "$transcript" 2>/dev/null || true)
[ -n "${tools:-}" ] || tools=0

# Every session records what was decided, flagged or not. The threshold below is a
# proxy for update-knowledge's "task of substance"; re-derive it from this log when
# it starts being wrong, rather than by feel.
log_decision() {
  printf '%s\t%s\t%s\t%s\n' "$(date +%Y-%m-%d)" "$project" "$tools" "$1" \
    >> "$KB/.experience-decisions.log"
}

if [ "$tools" -lt 5 ]; then
  log_decision below-threshold
  exit 0
fi

# No marker means no window to measure over, so make no claim.
marker="$KB/.sessions/$sid.start"
if [ ! -f "$marker" ]; then
  log_decision no-marker
  exit 0
fi

if [ -n "$(find "$KB/experiences" -maxdepth 1 -name '*.md' -newer "$marker" 2>/dev/null | head -1)" ]; then
  rm -f "$marker"
  log_decision entry-written
  exit 0
fi

rm -f "$marker"
log_decision flagged
printf '%s\t%s\t%s tool calls\n' "$(date +%Y-%m-%d)" "$project" "$tools" >> "$KB/.experience-debt"
printf '{"systemMessage":"Knowledge base: no experience entry for this session (%s). Flagged for the next one."}\n' "$project"
