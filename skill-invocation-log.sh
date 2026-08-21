#!/bin/sh
# Stop hook, report only. Records whether the guidance skills were invoked this
# session, alongside how much was produced. Never blocks, never speaks.
# Log: ~/.claude/skill-invocation.log
# Columns: ts session wg bg skills writes sh self

# Which skills to watch. Installs that name them differently override these
# rather than editing the greps below; a second install of this script already
# had to, because it calls its prose skill write-for-humans.
#   SKILL_LOG_WRITING=write-for-humans sh skill-invocation-log.sh
# or set them in the env block of ~/.claude/settings.json.
WRITING_SKILL="${SKILL_LOG_WRITING:-writing-guidelines}"
WORK_SKILL="${SKILL_LOG_WORK:-behavioral-guidelines}"
# Sessions that edited the skills repository itself invoke these skills by
# construction, so they are marked and excluded when computing a rate.
SELF_MATCH="${SKILL_LOG_SELF:-andrei-agentic-ai-skills}"

IN=$(cat 2>/dev/null)
SID=$(printf '%s' "$IN" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SID" ] && exit 0

# Prefer the cwd-derived path; fall back to a scan, since the layout is not a contract.
T="$HOME/.claude/projects/$(printf '%s' "$PWD" | sed 's#/#-#g')/$SID.jsonl"
[ -f "$T" ] || T=$(find "$HOME/.claude/projects" -name "$SID.jsonl" -maxdepth 2 2>/dev/null | head -1)
[ -f "$T" ] || exit 0

# A skill this install does not have reports n/a, never no. `no` claims the skill
# was available and went unused, which is the measurement; a missing skill would
# otherwise pad the failure rate with sessions that never could have invoked it.
seen() {
  [ -e "$HOME/.claude/skills/$1/SKILL.md" ] || { echo "n/a"; return; }
  if grep -q "\"skill\":\"$1\"" "$T" 2>/dev/null; then echo yes; else echo no; fi
}
wg=$(seen "$WRITING_SKILL")
bg=$(seen "$WORK_SKILL")

# grep -c prints the count and still exits 1 on zero matches, so `|| echo 0`
# would append a second zero. Take the count, then normalise.
num() { c=$(grep -cE "$1" 2>/dev/null | tr -d ' \n'); [ -z "$c" ] && c=0; echo "$c"; }
skills=$(grep -c '"name":"Skill"' "$T" 2>/dev/null | tr -d ' \n')
[ -z "$skills" ] && skills=0

# `writes` counts the Write and Edit tools. `sh` counts shell commands that look
# like they changed a file, and exists because a session driven through heredocs
# and sed logs writes=0 while rewriting the repository. gsub collapses each
# command to one line first: without it the count is output lines, not commands.
CMDS=$(jq -r 'try (.message.content[] | select(.type=="tool_use" and .name=="Bash") | .input.command | gsub("\n";" ")) // empty' "$T" 2>/dev/null)
writes=$(jq -r 'try (.message.content[] | select(.type=="tool_use" and (.name=="Write" or .name=="Edit")) | .name) // empty' "$T" 2>/dev/null | num '.')
shw=$(printf '%s\n' "$CMDS" | num '(^|[^>])>[^>&]|>>|\btee\b|sed -i|<<|\bmv \b|\bcp \b|\brm ')

self=no
grep -q "$SELF_MATCH" "$T" 2>/dev/null && self=yes

printf '%s %s wg=%s bg=%s skills=%s writes=%s sh=%s self=%s\n' \
  "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$(printf '%s' "$SID" | cut -c1-8)" \
  "$wg" "$bg" "$skills" "$writes" "$shw" "$self" >> "$HOME/.claude/skill-invocation.log"
exit 0
