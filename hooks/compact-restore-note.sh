#!/bin/sh
# SessionStart hook (matcher compact): runs right after auto or manual compaction.
# Plain stdout from SessionStart hooks is injected into the new context, so the
# post-compaction session gets the in-flight state captured at compact time plus
# a pointer to the full pre-compact transcript snapshot.

set -u

input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
latest_key=$(printf '%s' "${cwd:-default}" | tr '/' '-')

backup_dir="$HOME/.claude/compaction-backups"
latest="$backup_dir/LATEST-$latest_key"
state="$backup_dir/STATE-$latest_key.md"

if [ -f "$state" ]; then
  cat "$state" 2>/dev/null
  printf '\n'
fi

if [ -f "$latest" ]; then
  snapshot=$(cat "$latest" 2>/dev/null)
  if [ -n "$snapshot" ] && [ -f "$snapshot" ]; then
    lines=$(wc -l < "$snapshot" 2>/dev/null | tr -d ' ')
    printf 'Full pre-compact transcript snapshot saved at %s (%s lines). If any detail from before the compaction is missing, read that file.\n' "$snapshot" "$lines"
  fi
fi

cat <<'EOF'
Resume rules after compaction:
- Re-orient from the state above before acting. If the repo has a PROGRESS.md for the current task, it is the authoritative record - read it first.
- Do not assume long jobs (builds, test suites, containers) died in the compact; check for running state before re-launching anything.
- Continue with the narrowest next step. Ask the user only if the captured state is not enough to act on.
EOF

exit 0
