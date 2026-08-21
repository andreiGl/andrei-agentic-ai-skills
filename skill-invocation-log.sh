#!/bin/sh
# Stop hook, report only. Records whether the guidance skills were invoked this
# session, alongside how much was produced. Never blocks, never speaks.
# Log: ~/.claude/skill-invocation.log   Columns: ts session wg bg skills writes
IN=$(cat 2>/dev/null)
SID=$(printf '%s' "$IN" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SID" ] && exit 0

# Prefer the cwd-derived path; fall back to a scan, since the layout is not a contract.
T="$HOME/.claude/projects/$(printf '%s' "$PWD" | sed 's#/#-#g')/$SID.jsonl"
[ -f "$T" ] || T=$(find "$HOME/.claude/projects" -name "$SID.jsonl" -maxdepth 2 2>/dev/null | head -1)
[ -f "$T" ] || exit 0

wg=no; bg=no
grep -q '"skill":"writing-guidelines"'    "$T" 2>/dev/null && wg=yes
grep -q '"skill":"behavioral-guidelines"' "$T" 2>/dev/null && bg=yes
# grep -c prints the count and still exits 1 on zero matches, so `|| echo 0`
# would append a second zero. Take the count, then normalise.
skills=$(grep -c '"name":"Skill"' "$T" 2>/dev/null | tr -d ' \n')
writes=$(grep -c '"name":"Write"\|"name":"Edit"' "$T" 2>/dev/null | tr -d ' \n')
[ -z "$skills" ] && skills=0
[ -z "$writes" ] && writes=0

printf '%s %s wg=%s bg=%s skills=%s writes=%s\n' \
  "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$(printf '%s' "$SID" | cut -c1-8)" \
  "$wg" "$bg" "$skills" "$writes" >> "$HOME/.claude/skill-invocation.log"
exit 0
