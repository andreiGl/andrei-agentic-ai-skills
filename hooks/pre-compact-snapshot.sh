#!/bin/sh
# PreCompact hook: snapshot the session transcript before compaction rewrites it,
# and extract in-flight state (branch, dirty files, last exchange, recent tool
# calls) so the post-compact session can resume without re-doing live work.
# Runs on auto and manual compaction. Always exits 0 - must never fail the compaction.

set -u

input=$(cat)

session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
transcript_path=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
trigger=$(printf '%s' "$input" | jq -r '.trigger // "unknown"' 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
latest_key=$(printf '%s' "${cwd:-default}" | tr '/' '-')

backup_dir="$HOME/.claude/compaction-backups"
mkdir -p "$backup_dir" || exit 0

# Resolve the transcript: prefer the path from stdin, else find it by session id.
if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
  if [ -n "$session_id" ]; then
    transcript_path=$(find "$HOME/.claude/projects" -maxdepth 2 -name "${session_id}.jsonl" 2>/dev/null | head -1)
  fi
fi

if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
  exit 0
fi

timestamp=$(date +%Y%m%d-%H%M%S)
backup_file="$backup_dir/${timestamp}-${trigger}-${session_id}.jsonl"
cp "$transcript_path" "$backup_file" 2>/dev/null || exit 0

# Remember the newest snapshot per project so the post-compact SessionStart hook
# can point at it. Keyed by cwd so projects never cross-reference.
printf '%s\n' "$backup_file" > "$backup_dir/LATEST-$latest_key"

# Keep only the 20 newest snapshots (LATEST/STATE are not .jsonl, so never removed).
ls -t "$backup_dir"/*.jsonl 2>/dev/null | tail -n +21 | while IFS= read -r old_file; do
  rm -f "$old_file"
done

# --- In-flight state for the post-compact session --------------------------
state_file="$backup_dir/STATE-$latest_key.md"
{
  printf '## In-flight state captured at compact (%s, trigger: %s)\n\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$trigger"

  if [ -n "$cwd" ] && [ -e "$cwd/.git" ]; then
    branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
    [ -n "$branch" ] && printf 'Git branch: %s\n' "$branch"
    dirty=$(git -C "$cwd" status --short 2>/dev/null | head -20)
    [ -n "$dirty" ] && printf 'Uncommitted changes:\n```\n%s\n```\n' "$dirty"
  fi

  # Last user request (text only, tool results filtered out)
  last_user=$(jq -r 'select(.type=="user") | .message.content
    | if type=="string" then .
      else ([.[]? | select(.type=="text") | .text] | join("\n")) end' "$transcript_path" 2>/dev/null \
    | grep -v '^[[:space:]]*$' | tail -c 600)
  [ -n "$last_user" ] && printf 'Last user request (tail):\n> %s\n\n' "$last_user"

  # Last assistant narration - usually the current plan and next step
  last_asst=$(jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="text") | .text' "$transcript_path" 2>/dev/null \
    | grep -v '^[[:space:]]*$' | tail -c 800)
  [ -n "$last_asst" ] && printf 'Last assistant statement (tail):\n> %s\n\n' "$last_asst"

  # Most recent tool calls - what was actively being worked on
  tools=$(jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use")
    | .name as $n
    | (.input.command // .input.file_path // .input.description // .input.pattern // .input.url // .input.prompt // ""
      | tostring | .[0:100]) as $d
    | "\($n): \($d)"' "$transcript_path" 2>/dev/null | tail -8)
  [ -n "$tools" ] && printf 'Most recent tool calls:\n```\n%s\n```\n' "$tools"

  # Last todo list, if the session used one
  todos=$(jq -r 'select(.type=="assistant") | .message.content[]?
    | select(.type=="tool_use") | select(.name=="TodoWrite") | .input.todos[]
    | "[\(.status)] \(.content)"' "$transcript_path" 2>/dev/null | tail -c 800)
  [ -n "$todos" ] && printf 'Todo list at compact:\n%s\n' "$todos"

  # Task-tool activity (TaskCreate/TaskUpdate/TaskList) - raw inputs, no schema assumptions
  tasks=$(jq -r 'select(.type=="assistant") | .message.content[]?
    | select(.type=="tool_use")
    | select(.name=="TaskCreate" or .name=="TaskUpdate" or .name=="TaskList")
    | "\(.name): \(.input | tostring | .[0:140])"' "$transcript_path" 2>/dev/null | tail -6)
  [ -n "$tasks" ] && printf 'Task-list activity:\n```\n%s\n```\n' "$tasks"
} > "$state_file" 2>/dev/null

exit 0
