#!/bin/sh
# Commits and pushes the knowledge base when a session ends, so the off-machine
# copy does not quietly fall behind the working one.
#
# Files whose first line marks them internal-only are never staged. The raw/
# convention says such material does not leave the machine, and a private remote
# is still off the machine.
#
# SessionEnd output reaches nobody, so failures are logged rather than reported.
set -u

KB_ROOT="${KB_ROOT:-$HOME/.claude/knowledge}"
STATE_ROOT="${KB_SESSION_STATE_ROOT:-$HOME/.claude/kb-session}"
LOG="$STATE_ROOT/autocommit.log"

[ -d "$KB_ROOT/.git" ] || exit 0
command -v git >/dev/null 2>&1 || exit 0
cd "$KB_ROOT" 2>/dev/null || exit 0

# A hook that blocks on a credential prompt hangs session exit.
GIT_TERMINAL_PROMPT=0
export GIT_TERMINAL_PROMPT

input=$(cat 2>/dev/null || true)
project=unknown
if command -v jq >/dev/null 2>&1; then
    cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
    [ -n "${cwd:-}" ] && project=$(basename "$cwd")
fi

mkdir -p "$STATE_ROOT" 2>/dev/null || exit 0
stamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
note() { printf '%s\t%s\n' "$stamp" "$1" >> "$LOG"; }

git add -A 2>/dev/null || { note "git add failed"; exit 0; }

# Unstage anything marked internal-only. Checked on the first line only: the
# marker appears in prose elsewhere in this KB and a whole-file grep matches it.
held=
for f in $(git diff --cached --name-only 2>/dev/null); do
    [ -f "$f" ] || continue
    case "$(head -1 "$f" 2>/dev/null)" in
        *'internal-only: do not extract'*)
            git reset -q -- "$f" 2>/dev/null
            held="$held $f"
            ;;
    esac
done
[ -n "$held" ] && note "held back internal-only:$held"

if ! git diff --cached --quiet 2>/dev/null; then
    changed=$(git diff --cached --name-only | tr '\n' ' ')
    if [ -n "$held" ]; then
        git commit -q -m "Session notes from $project" -m "Files: $changed" \
            -m "Held back as internal-only:$held" 2>/dev/null
    else
        git commit -q -m "Session notes from $project" -m "Files: $changed" 2>/dev/null
    fi || { note "commit failed"; exit 0; }
fi

# Carry on to the push even when this session recorded nothing. An earlier run may
# have committed and then failed to push, and stopping here would leave that commit
# waiting for the next KB edit to carry it - which is exactly the session where
# nobody is thinking about the backup.
ahead=$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo unknown)
[ "$ahead" = "0" ] && exit 0

# Push only where this knowledge base has always pushed. An unattended push means
# nobody is at the keyboard to notice a remote that was repointed, or a second KB
# cloned into place, so the destination is checked rather than assumed. The commit
# is already made either way: refusing to push loses nothing but the upload.
#
# KB_REMOTE pins explicitly. Otherwise the first run records what it finds and every
# later run must match it. The pin lives outside the repository, so a fresh clone
# elsewhere pins itself rather than inheriting a stale expectation.
pin="$STATE_ROOT/remote.pin"
url=$(git config --get remote.origin.url 2>/dev/null || true)
expected="${KB_REMOTE:-}"
if [ -z "$expected" ] && [ -f "$pin" ]; then
    expected=$(cat "$pin" 2>/dev/null || true)
fi

if [ -z "${url:-}" ]; then
    note "no origin remote - commit kept local"
    exit 0
fi
if [ -z "${expected:-}" ]; then
    printf '%s\n' "$url" > "$pin" 2>/dev/null || true
    note "pinned origin for future runs"
elif [ "$url" != "$expected" ]; then
    note "REMOTE MISMATCH - refused to push, commit kept local. Compare git remote -v against $pin"
    exit 0
fi

if git push -q 2>/dev/null; then
    note "pushed $(git rev-parse --short HEAD)"
else
    note "PUSH FAILED - $(git rev-list --count @{u}..HEAD 2>/dev/null || echo '?') commit(s) local only"
fi
exit 0
