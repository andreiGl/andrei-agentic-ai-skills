#!/bin/bash
# activation-run.sh - run one activation-suite row in an isolated headless session.
#
# Sandbox: temp HOME + CLAUDE_CONFIG_DIR + cwd, so no hooks, no MCP servers, no
# plugins, and no user-level skills load. Only the skill under test is staged via
# --plugin-dir. Tools are locked to Skill + read-only; every write, exec, network,
# and MCP tool is disallowed. The suite runner (activation-run.py) calls this per row.
#
# Usage: activation-run.sh <plugin-root> <prompt-file> <out-json> [files-dir]
#   <plugin-root>  dir holding skills/<name>/SKILL.md (the minimal staged root)
#   <prompt-file>  file holding the row prompt (read as stdin source)
#   <out-json>     where the raw stream-json transcript is written
#   <files-dir>    optional; copied into the sandbox home before the session starts
#                  (rows that test a task on an existing artifact stage it here)
# Exit: 0 session ran (check the transcript for the verdict), nonzero on setup error.

set -u

PLUGIN_ROOT="${1:?usage: activation-run.sh <plugin-root> <prompt-file> <out-json> [files-dir]}"
PROMPT_FILE="${2:?usage: activation-run.sh <plugin-root> <prompt-file> <out-json> [files-dir]}"
OUT_JSON="${3:?usage: activation-run.sh <plugin-root> <prompt-file> <out-json> [files-dir]}"
FILES_DIR="${4:-}"

[ -d "$PLUGIN_ROOT/skills" ] || { echo "activation-run: no skills/ under $PLUGIN_ROOT" >&2; exit 2; }
[ -r "$PROMPT_FILE" ] || { echo "activation-run: cannot read $PROMPT_FILE" >&2; exit 2; }

SANDBOX=$(mktemp -d "${TMPDIR:-/tmp}/act-sandbox.XXXXXX") || exit 2
mkdir -p "$SANDBOX/home" "$SANDBOX/config"
trap 'rm -rf "$SANDBOX"' EXIT

# Gateway credentials pass by env only - never printed, never written to disk.
eval "$(python3 -I -c '
import json, shlex, sys
from pathlib import Path
try:
    env = json.load(open(Path.home() / ".claude" / "settings.json")).get("env") or {}
except Exception:
    sys.exit(1)
for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL"):
    if env.get(k):
        print("export %s=%s" % (k, shlex.quote(env[k])))
')" || { echo "activation-run: cannot read gateway env" >&2; exit 2; }
export ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_MODEL

PROMPT=$(cat "$PROMPT_FILE")

cd "$SANDBOX/home" || exit 2
if [ -n "$FILES_DIR" ]; then
  [ -d "$FILES_DIR" ] || { echo "activation-run: files-dir '$FILES_DIR' is not a directory" >&2; exit 2; }
  cp -R "$FILES_DIR"/. "$SANDBOX/home"/
fi
HOME="$SANDBOX/home" CLAUDE_CONFIG_DIR="$SANDBOX/config" \
  gtimeout 300 claude -p "$PROMPT" \
  --output-format stream-json --verbose \
  --allowedTools Skill Read Glob Grep \
  --disallowedTools 'Bash(git*)' Bash Edit Write NotebookEdit Task TaskStop \
    ListAgents SendMessage 'mcp__*' WebFetch WebSearch Workflow EnterWorktree \
    ExitWorktree CronCreate CronDelete CronList ScheduleWakeup DesignSync \
  --plugin-dir "$PLUGIN_ROOT" \
  > "$OUT_JSON" 2>/dev/null
echo "activation-run: transcript at $OUT_JSON (sandbox $SANDBOX removed)" >&2
