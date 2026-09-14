#!/usr/bin/env bash
# resume-sessions.sh — resume all sessions saved in ~/.claude/saved-sessions.json
# Usage:
#   resume-sessions.sh              # tmux (creates session "claude-restored")
#   resume-sessions.sh --plain      # no tmux: print resume commands to paste
#   resume-sessions.sh --yes        # skip the confirmation prompt
# Bash 3.2 compatible (macOS /bin/bash): no mapfile, no associative arrays.
set -euo pipefail

SAVE_FILE="$HOME/.claude/saved-sessions.json"
TMUX_NAME="claude-restored"
ASSUME_YES=0
[ "${1:-}" = "--yes" ] && ASSUME_YES=1

[[ -f "$SAVE_FILE" ]] || { echo "No saved sessions file: $SAVE_FILE (run save-sessions.sh first)" >&2; exit 1; }

# One row per session: <sessionId><TAB><cwd><TAB><title-or-prompt>, skipping
# the current session (resuming it from within itself would attach a second
# interface to the conversation already driving this script). Two sources for
# the current id: the save file's currentSessionId (the session the save ran
# from) and $CLAUDE_CODE_SESSION_ID (the session running THIS script - the
# save may be older, from a different session, e.g. saved Friday, restored
# Monday from a fresh session).
ROWS=$(jq -r --arg self "${CLAUDE_CODE_SESSION_ID:-}" '
  (.currentSessionId // "") as $cur
  | .sessions[]
  | select(.sessionId != $cur)
  | select(.sessionId != $self)
  | select(.current != true)
  | [.sessionId, .cwd, (.summary // .lastPrompt // "")] | @tsv' "$SAVE_FILE")

[ -n "$ROWS" ] || { echo "No sessions to resume (only the current session is in $SAVE_FILE)" >&2; exit 0; }

# Live-session detection, best-effort: catches only sessions whose id appears
# in argv (--session-id / --resume <id-or-path>, e.g. daemon-forked runs).
# IDE-started sessions run as bare `claude` with NO id in argv (verified on
# this machine) and are invisible to this check - the confirmation prompt
# below is the real guard against double-driving a live session.
# The || true guards keep pipefail from aborting when a grep finds nothing.
# Each grep gets its own pipe from $ps_out: a shared stdin group would leave
# the second grep with drained input (only the first pattern would be found).
ps_out=$(ps -eo tty=,args= 2>/dev/null | awk '$1 !~ /^\?/' || true)
live_ids=$({
  printf '%s\n' "$ps_out" | grep -oE -- '--session-id [0-9a-f-]{36}' | awk '{print $2}' || true
  printf '%s\n' "$ps_out" | grep -oE -- '--resume [^ ]+' | sed -E 's|^--resume (.*/)?([0-9a-f]{8}-[0-9a-f-]{27,36})(\.jsonl)?$|\2|' | grep -E '^[0-9a-f-]{36}$' || true
} | sort -u)

kept_rows=""
skipped_live=0
while IFS= read -r row; do
  id=$(printf '%s' "$row" | cut -f1)
  if printf '%s\n' "$live_ids" | grep -qx "$id"; then
    echo "SKIP (already live): $id" >&2
    skipped_live=$((skipped_live + 1))
  else
    kept_rows="${kept_rows}${row}"$'\n'
  fi
done <<EOF
$ROWS
EOF

kept_rows=${kept_rows%$'\n'}
[ -n "$kept_rows" ] || {
  echo "All saved sessions are already live - nothing to resume. Restart the IDE first if you want them moved into tmux." >&2
  exit 0
}

if [ "$skipped_live" -gt 0 ]; then
  echo "Skipped $skipped_live session(s) that are still open." >&2
fi

if ! command -v tmux >/dev/null || [ "${1:-}" = "--plain" ]; then
  echo "# Paste each of these in a separate terminal:"
  while IFS= read -r row; do
    id=$(printf '%s' "$row" | cut -f1); cwd=$(printf '%s' "$row" | cut -f2)
    [[ -d "$cwd" ]] || cwd="$HOME"
    echo "cd $(printf '%q' "$cwd") && claude --resume $(printf '%q' "$id")"
  done <<EOF
$kept_rows
EOF
  exit 0
fi

count=$(printf '%s\n' "$kept_rows" | wc -l | tr -d ' ')
echo "About to resume $count session(s) in tmux session '$TMUX_NAME':"
n=0
while IFS= read -r row; do
  n=$((n + 1))
  id=$(printf '%s' "$row" | cut -f1); cwd=$(printf '%s' "$row" | cut -f2); title=$(printf '%s' "$row" | cut -f3)
  printf '  %d. %-70s (%s)\n' "$n" "${title:-(untitled)}" "$cwd"
done <<EOF
$kept_rows
EOF

if [ "$ASSUME_YES" -ne 1 ]; then
  printf 'Proceed? [y/N] '
  read -r answer
  case "$answer" in
    y|Y|yes|Yes) ;;
    *) echo "Aborted." ; exit 0 ;;
  esac
fi

# If a claude-restored session survives from an earlier restore, add windows to
# it instead of failing on a duplicate session name.
if tmux has-session -t "$TMUX_NAME" 2>/dev/null; then
  echo "tmux session '$TMUX_NAME' already exists - adding windows to it." >&2
  first=0
else
  first=1
fi

while IFS= read -r row; do
  id=$(printf '%s' "$row" | cut -f1); cwd=$(printf '%s' "$row" | cut -f2)
  if [[ ! -d "$cwd" ]]; then
    echo "WARN: cwd missing for $id, using \$HOME" >&2
    cwd="$HOME"
  fi
  name="claude-${id:0:8}"
  if [ "$first" -eq 1 ]; then
    # Plain shell window + send-keys: a window whose start command exits
    # instantly closes at once (and can kill a single-window tmux server).
    tmux new-session -d -s "$TMUX_NAME" -n "$name" -c "$cwd"
    first=0
  else
    tmux new-window -d -t "$TMUX_NAME" -n "$name" -c "$cwd"
  fi
  tmux send-keys -t "$TMUX_NAME:$name" "claude --resume $(printf '%q' "$id")" Enter
done <<EOF
$kept_rows
EOF

echo "Resumed $count session(s) in tmux session '$TMUX_NAME'."
echo "Attach with:  tmux attach -t $TMUX_NAME   (switch windows: Ctrl-b n / Ctrl-b p, detach: Ctrl-b d)"
