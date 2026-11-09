#!/bin/sh
# Commits and pushes the knowledge base when a session ends, so the off-machine
# copy does not quietly fall behind the working one.
#
# One file for every install. Per-machine values come from the environment or
# from $KB_HOOKS_ENV (default ~/.claude/kb-hooks.env), a plain KEY=value file read
# at start. Nothing install-specific is written in this script.
#
#   KB_APPROVED_REMOTE  set: origin must be exactly this URL. Unset: the first
#                       run pins what it finds (or KB_REMOTE) and later runs
#                       must match the pin.
#   KB_STAGE_PATHS      set: only these top-level paths may be committed or
#                       pushed, space-separated. Unset: everything is staged.
#   KB_SAFE_PATH=1      run git with a system-only PATH.
#
# Files whose first line marks them internal-only are never staged. The raw/
# convention says such material does not leave the machine, and a private remote
# is still off the machine.
#
# SessionEnd output reaches nobody, so failures are logged, and each failure also
# leaves a notice that kb-session-start.sh prints into the next session. Notices
# append, so a second failure does not erase the first. Only a successful push
# clears them; a run with nothing to do leaves them for the next start to surface.
# Each notice starts with a short code (push-failed, skipped-remote, ...).
set -u

HOOKS_ENV="${KB_HOOKS_ENV:-$HOME/.claude/kb-hooks.env}"
# shellcheck disable=SC1090
[ -f "$HOOKS_ENV" ] && . "$HOOKS_ENV"

KB_ROOT="${KB_ROOT:-$HOME/.claude/knowledge}"
STATE_ROOT="${KB_SESSION_STATE_ROOT:-$HOME/.claude/kb-session}"
LOG="$STATE_ROOT/autocommit.log"
NOTICE="$STATE_ROOT/autocommit-notice"
# Used only when STATE_ROOT itself cannot be written, so it has to live elsewhere.
FALLBACK_NOTICE="${KB_AUTOCOMMIT_FALLBACK_NOTICE:-$HOME/.claude/kb-autocommit-notice}"
LOCK="$STATE_ROOT/autocommit.lock"
APPROVED_REMOTE="${KB_APPROVED_REMOTE:-}"
STAGE_PATHS="${KB_STAGE_PATHS:-}"
# A live run cannot outlast the hook's 30s timeout in settings.json, so a lock this
# old was left by a run that was killed.
STALE_LOCK_SECONDS="${KB_AUTOCOMMIT_STALE_LOCK_SECONDS:-120}"
# Must stay under that 30s timeout: a push killed from outside never reaches the log.
# The fetch can run twice, so two fetches plus a push must fit in it too.
NETWORK_TIMEOUT="${KB_AUTOCOMMIT_NETWORK_TIMEOUT:-8}"

# A hook that blocks on a credential prompt hangs session exit.
GIT_TERMINAL_PROMPT=0
export GIT_TERMINAL_PROMPT
if [ "${KB_SAFE_PATH:-0}" = 1 ]; then
    PATH="/usr/bin:/bin:/usr/sbin:/sbin"
    export PATH
fi

stamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
note() { printf '%s\t%s\n' "$stamp" "$1" >> "$LOG" 2>/dev/null || true; }
# fail <code> <message>
fail() {
    note "$1: $2"
    ( printf '%s\t%s: %s\n' "$stamp" "$1" "$2" >> "$NOTICE" ) 2>/dev/null || true
}

[ -d "$KB_ROOT/.git" ] || exit 0
command -v git >/dev/null 2>&1 || exit 0

if ! mkdir -p "$STATE_ROOT" 2>/dev/null || ! touch "$LOG" 2>/dev/null; then
    ( printf '%s\t%s\n' "$stamp" "state-dir-unwritable: state directory $STATE_ROOT not writable - nothing committed" \
        >> "$FALLBACK_NOTICE" ) 2>/dev/null || true
    exit 0
fi

# Checked one at a time: zero is as wrong as garbage for both. A zero stale age
# would take over every live lock, and a zero timeout would fail every push.
for setting in "$STALE_LOCK_SECONDS" "$NETWORK_TIMEOUT"; do
    case "$setting" in
        ''|*[!0-9]*|0|00*) fail skipped-invalid-config "invalid stale-lock or network timeout setting - nothing committed"; exit 0 ;;
    esac
done

# The lock is a directory because mkdir is atomic: two sessions ending together
# would otherwise commit the same files twice or race each other's push.
acquire_lock() {
    if mkdir "$LOCK" 2>/dev/null; then
        printf '%s\n' "$$" > "$LOCK/pid"
        date +%s > "$LOCK/created"
        return 0
    fi
    created=$(cat "$LOCK/created" 2>/dev/null || echo 0)
    case "$created" in ''|*[!0-9]*) created=0 ;; esac
    [ $(( $(date +%s) - created )) -ge "$STALE_LOCK_SECONDS" ] || return 1
    stale="$STATE_ROOT/autocommit.lock.stale.$$"
    if mv "$LOCK" "$stale" 2>/dev/null && rm -rf "$stale" && mkdir "$LOCK" 2>/dev/null; then
        printf '%s\n' "$$" > "$LOCK/pid"
        date +%s > "$LOCK/created"
        note "recovered stale lock"
        return 0
    fi
    return 2
}
acquire_lock
case $? in
    0) ;;
    1) note "another run holds the lock - skipped"; exit 0 ;;
    *) fail skipped-lock-recovery-failed "could not recover a stale lock at $LOCK - nothing committed"; exit 0 ;;
esac
# Set only after the lock is ours, so an early exit never removes another run's lock.
trap 'rm -rf "$LOCK"' EXIT
trap 'exit 1' HUP INT TERM

# The project the session ran in: the hook payload's cwd, else the working
# directory (when kb-session-end.sh calls this script, it passes the payload on).
input=$(cat 2>/dev/null || true)
project=$(basename "${PWD:-unknown}")
if command -v jq >/dev/null 2>&1; then
    cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
    [ -n "${cwd:-}" ] && project=$(basename "$cwd")
fi

cd "$KB_ROOT" 2>/dev/null || exit 0
# A read-only KB (an A/B study batch) cannot take new content: skip cleanly
# instead of failing git add and leaving a spurious backup notice.
[ -w "$KB_ROOT" ] || { note "skipped-readonly"; exit 0; }

# macOS has no timeout(1). Runs the command in the background and kills it once the
# limit passes, so a stalled network call fails here, where it gets logged.
run_network() {
    "$@" &
    pid=$!
    waited=0
    while kill -0 "$pid" 2>/dev/null; do
        if [ "$waited" -ge "$NETWORK_TIMEOUT" ]; then
            kill "$pid" 2>/dev/null
            wait "$pid" 2>/dev/null
            return 124
        fi
        sleep 1
        waited=$((waited + 1))
    done
    wait "$pid"
}

# Push only where this knowledge base has always pushed. An unattended push means
# nobody is at the keyboard to notice a remote that was repointed, or a second KB
# cloned into place, so the destination is checked rather than assumed. Nothing is
# committed when the check fails, so the next run, after a fix, commits it all.
#
# KB_APPROVED_REMOTE fixes the URL. Otherwise KB_REMOTE, or the first run records
# what it finds and every later run must match it. The pin lives outside the
# repository, so a fresh clone elsewhere pins itself rather than inheriting a
# stale expectation.
[ "$(git branch --show-current 2>/dev/null)" = main ] || { fail skipped-branch "KB is not on main - nothing committed"; exit 0; }
[ "$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null)" = origin/main ] \
    || { fail skipped-upstream "main does not track origin/main - nothing committed"; exit 0; }
url=$(git config --get remote.origin.url 2>/dev/null || true)
if [ -z "${url:-}" ]; then
    fail skipped-remote "no origin remote - nothing committed"
    exit 0
fi
# git push writes to every pushurl, and get-url shows only the first, so any
# pushurl at all is refused.
if [ -n "$(git config --get-all remote.origin.pushurl 2>/dev/null)" ]; then
    fail skipped-remote "REMOTE MISMATCH - origin has a pushurl, refused. Check git remote -v"
    exit 0
fi
pin="$STATE_ROOT/remote.pin"
expected="$APPROVED_REMOTE"
[ -n "$expected" ] || expected="${KB_REMOTE:-}"
if [ -z "$expected" ] && [ -f "$pin" ]; then
    expected=$(cat "$pin" 2>/dev/null || true)
fi
if [ -z "$expected" ]; then
    printf '%s\n' "$url" > "$pin" 2>/dev/null || true
    note "pinned origin for future runs"
elif [ "$url" != "$expected" ]; then
    fail skipped-remote "REMOTE MISMATCH - refused, nothing committed. Compare git remote -v against the approved remote"
    exit 0
fi
[ -z "$(git ls-files -u 2>/dev/null)" ] || { fail skipped-conflict "unmerged files in $KB_ROOT - nothing committed"; exit 0; }

# Something staged by hand is someone's work in progress, not this hook's to commit.
if [ -n "$(git diff --cached --name-only 2>/dev/null)" ]; then
    fail skipped-prestaged "files already staged in $KB_ROOT - left for you to commit, nothing pushed"
    exit 0
fi

# Catch up with a push from another machine before committing. One quiet retry
# covers transient network churn: 35 same-day fetch failures under parallel
# sessions on 2026-11-08 at work while the remote stayed reachable.
fetch() { run_network git fetch -q origin main 2>/dev/null; }
if ! fetch; then
    sleep 2
    fetch || { fail fetch-failed "FETCH FAILED twice - nothing committed"; exit 0; }
fi
local_head=$(git rev-parse HEAD)
remote_head=$(git rev-parse origin/main 2>/dev/null || echo "$local_head")
if [ "$local_head" != "$remote_head" ]; then
    if git merge-base --is-ancestor "$local_head" "$remote_head" 2>/dev/null; then
        git merge -q --ff-only origin/main 2>/dev/null || { fail skipped-diverged "fast-forward to origin/main failed - nothing committed"; exit 0; }
        note "fast-forwarded"
    elif ! git merge-base --is-ancestor "$remote_head" "$local_head" 2>/dev/null; then
        fail skipped-diverged "KB and origin/main have diverged - nothing committed, merge by hand"
        exit 0
    fi
fi

# Every path a push would publish: the working tree and every file any unpushed
# commit touched, even one a later commit deleted, since its blob stays in history.
publish_paths=$(
    {
        git ls-files -z -m -o -d --exclude-standard 2>/dev/null
        git log -z --format= --name-only '@{u}..HEAD' 2>/dev/null
    } | tr '\0' '\n' | grep -v '^$' | sort -u
)

# Credential-looking files never leave the machine. The whole run stops rather
# than holding them back, because an unpushed commit cannot be held back.
sensitive=$(printf '%s\n' "$publish_paths" \
    | grep -Ei '(^|/)[^/]*(credentials|secret)[^/]*$|\.(pem|key|p12|pfx)$|(^|/)\.env($|\.)' \
    | paste -sd' ' -)
if [ -n "$sensitive" ]; then
    fail skipped-sensitive-name "credential-looking file(s) in the knowledge base: $sensitive - nothing committed or pushed"
    exit 0
fi

# With an allowlist, a path outside it stops the run the same way.
if [ -n "$STAGE_PATHS" ]; then
    allowed_re=$(printf '%s\n' $STAGE_PATHS | sed 's/[.[\*^$]/\\&/g; s#.*#^&(/|$)#' | paste -sd'|' -)
    unapproved=$(printf '%s\n' "$publish_paths" | grep -Ev "$allowed_re" | paste -sd' ' -)
    if [ -n "$unapproved" ]; then
        fail skipped-unapproved-path "path(s) outside KB_STAGE_PATHS: $unapproved - nothing committed or pushed"
        exit 0
    fi
    # A tracked file that .gitignore now covers would be committed anyway.
    # shellcheck disable=SC2086
    ignored=$(git ls-files -ci --exclude-standard -- $STAGE_PATHS 2>/dev/null | paste -sd' ' -)
    if [ -n "$ignored" ]; then
        fail skipped-ignored-tracked "tracked file(s) that .gitignore covers: $ignored - nothing committed"
        exit 0
    fi
fi

if [ -n "$STAGE_PATHS" ]; then
    for p in $STAGE_PATHS; do
        [ -e "$p" ] || git ls-files --error-unmatch -- "$p" >/dev/null 2>&1 || continue
        git add -A -- "$p" 2>/dev/null || { git reset -q 2>/dev/null; fail stage-failed "git add failed"; exit 0; }
    done
else
    git add -A 2>/dev/null || { git reset -q 2>/dev/null; fail stage-failed "git add failed"; exit 0; }
fi

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
    added=$(git diff --cached --name-only --diff-filter=A 2>/dev/null)
    modified=$(git diff --cached --name-only --diff-filter=M 2>/dev/null)

    # Subject line. The session already described itself: update-knowledge writes an
    # experience entry whose first line names the work in the session's own words, which
    # beats anything derivable from cwd. Fall back to what changed, and only then to the
    # project name.
    newexp=$(printf '%s\n' "$added" | grep '^experiences/[^/]*\.md$' | head -1)
    subject=
    if [ -n "$newexp" ] && [ -f "$newexp" ]; then
        subject=$(head -1 "$newexp" | sed 's/^#* *//; s/^[0-9][0-9-]* *- *//')
    fi
    if [ -z "$subject" ]; then
        names=$(printf '%s\n' "$added" "$modified" | grep -v '^$' | sed 's#.*/##; s#\.md$##' \
                | grep -v '^INDEX$' | paste -sd, - | cut -c1-50)
        if [ -n "$(printf '%s' "$added" | tr -d '[:space:]')" ]; then
            subject="Add ${names:-notes}"
        else
            subject="Update ${names:-notes}"
        fi
    fi
    subject=$(printf '%s' "$subject" | cut -c1-72 \
        | awk '{print toupper(substr($0,1,1)) substr($0,2)}')

    # Body. A diffstat says more per line than a file list, and the two journals are worth
    # counting because a line landing in them is the point of the exercise.
    body=$(printf 'Session in %s.\n' "$project")
    for j in learnings.md gotchas.md; do
        [ -f "$j" ] || continue
        n=$(git diff --cached --numstat -- "$j" 2>/dev/null | awk '{print $1}')
        [ -n "${n:-}" ] && [ "$n" != "0" ] && body=$(printf '%s\n%s: +%s lines' "$body" "${j%.md}" "$n")
    done
    stat=$(git diff --cached --stat 2>/dev/null)

    # The KB's own git hooks are not this script's to run unattended.
    if [ -n "$held" ]; then
        git -c core.hooksPath=/dev/null commit -q -m "$subject" -m "$body" -m "$stat" \
            -m "Held back as internal-only:$held" 2>/dev/null
    else
        git -c core.hooksPath=/dev/null commit -q -m "$subject" -m "$body" -m "$stat" 2>/dev/null
    fi || { git reset -q 2>/dev/null; fail commit-failed "commit failed"; exit 0; }
fi

# Carry on to the push even when this session recorded nothing. An earlier run may
# have committed and then failed to push, and stopping here would leave that commit
# waiting for the next KB edit to carry it - which is exactly the session where
# nobody is thinking about the backup.
ahead=$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo unknown)
[ "$ahead" = "0" ] && exit 0

# Bound the push so a stalled connection fails here rather than being killed by the
# SessionEnd deadline. That deadline is the highest per-hook timeout in settings and is
# shared with every other SessionEnd hook, so the time actually available is less than it
# looks. A process killed from outside never reaches the log, which turns a retryable
# failure into an invisible one - the commit would sit local with nothing recording why.
#
# http.lowSpeed* catches a stall rather than capping total time, which suits a repository
# this small: a real transfer finishes in about a second, so anything slow is stuck.
# HTTPS remotes only; an SSH remote would need a different bound. run_network caps
# the total time on top of that, for a connection that never starts at all.
run_network git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 push -q origin HEAD:refs/heads/main 2>/dev/null
status=$?
if [ "$status" -eq 0 ]; then
    note "pushed $(git rev-parse --short HEAD)"
    rm -f "$NOTICE"
elif [ "$status" -eq 124 ]; then
    fail push-timeout "PUSH TIMED OUT after ${NETWORK_TIMEOUT}s - $(git rev-list --count @{u}..HEAD 2>/dev/null || echo '?') commit(s) local only"
else
    fail push-failed "PUSH FAILED - $(git rev-list --count @{u}..HEAD 2>/dev/null || echo '?') commit(s) local only"
fi
exit 0
