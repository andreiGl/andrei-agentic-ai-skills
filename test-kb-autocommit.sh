#!/bin/sh
# Runs kb-autocommit.sh and the notice handling in kb-session-start.sh against a
# throwaway knowledge base with a local bare remote.
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'chmod -R u+w "$TMP" 2>/dev/null; rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export KB_ROOT="$TMP/kb"
export KB_SESSION_STATE_ROOT="$TMP/state"
export KB_AUTOCOMMIT_FALLBACK_NOTICE="$TMP/fallback-notice"
REMOTE="$TMP/remote.git"
export KB_REMOTE="$REMOTE"
STATE="$KB_SESSION_STATE_ROOT"
mkdir -p "$HOME"

fails=0
check() {
    if eval "$2"; then
        printf 'ok   %s\n' "$1"
    else
        printf 'FAIL %s\n' "$1"
        fails=$((fails + 1))
    fi
}
# Called in a subshell wherever a variable is set in front of it: sh keeps such
# assignments after a function call returns.
autocommit() { printf '{"cwd":"/x/proj"}' | sh "$ROOT/kb-autocommit.sh"; }
start_hook() { printf '{}' | sh "$ROOT/kb-session-start.sh"; }
remote_head() { git --git-dir="$REMOTE" rev-parse main 2>/dev/null; }

git init -q --bare -b main "$REMOTE"
git init -q -b main "$KB_ROOT"
git -C "$KB_ROOT" config user.name test
git -C "$KB_ROOT" config user.email test@example.com
mkdir -p "$KB_ROOT/experiences"
echo "# KB" > "$KB_ROOT/INDEX.md"
git -C "$KB_ROOT" add -A && git -C "$KB_ROOT" commit -qm init
git -C "$KB_ROOT" remote add origin "$REMOTE"
git -C "$KB_ROOT" push -q -u origin main

# A normal run commits and pushes, and leaves no notice.
echo "- a gotcha" > "$KB_ROOT/gotchas.md"
autocommit
check "commits and pushes" '[ "$(remote_head)" = "$(git -C "$KB_ROOT" rev-parse HEAD)" ]'
check "no notice after success" '[ ! -s "$STATE/autocommit-notice" ]'
check "lock released" '[ ! -d "$STATE/autocommit.lock" ]'

# Internal-only material stays out of the commit.
printf 'internal-only: do not extract\nsecret\n' > "$KB_ROOT/private.md"
autocommit
check "internal-only file held back" '! git -C "$KB_ROOT" ls-files --error-unmatch private.md >/dev/null 2>&1'
rm -f "$KB_ROOT/private.md"

# A live lock skips the run without a notice; the files stay uncommitted.
mkdir "$STATE/autocommit.lock"; date +%s > "$STATE/autocommit.lock/created"
echo "- second" >> "$KB_ROOT/gotchas.md"
autocommit
check "live lock skips the run" '[ -n "$(git -C "$KB_ROOT" status --porcelain)" ]'
check "live lock leaves no notice" '[ ! -s "$STATE/autocommit-notice" ]'
check "live lock not removed" '[ -d "$STATE/autocommit.lock" ]'

# A lock older than the limit is taken over.
echo 0 > "$STATE/autocommit.lock/created"
autocommit
check "stale lock recovered and run completes" '[ -z "$(git -C "$KB_ROOT" status --porcelain)" ]'
check "stale recovery logged" 'grep -q "recovered stale lock" "$STATE/autocommit.log"'

# Bad settings refuse to run, each checked on its own.
for bad in 0 abc 007; do
    echo "- $bad" >> "$KB_ROOT/gotchas.md"
    rm -f "$STATE/autocommit-notice"
    (KB_AUTOCOMMIT_NETWORK_TIMEOUT=$bad autocommit)
    check "network timeout '$bad' rejected" 'grep -q "invalid" "$STATE/autocommit-notice"'
    rm -f "$STATE/autocommit-notice"
    (KB_AUTOCOMMIT_STALE_LOCK_SECONDS=$bad autocommit)
    check "stale lock age '$bad' rejected" 'grep -q "invalid" "$STATE/autocommit-notice"'
done
check "nothing committed with bad settings" '[ -n "$(git -C "$KB_ROOT" status --porcelain)" ]'
rm -f "$STATE/autocommit-notice"

# A push that hangs is cut off and reported.
cat > "$REMOTE/hooks/pre-receive" <<'EOF'
#!/bin/sh
sleep 5
EOF
chmod +x "$REMOTE/hooks/pre-receive"
echo "- hung" >> "$KB_ROOT/gotchas.md"
start=$(date +%s)
(KB_AUTOCOMMIT_NETWORK_TIMEOUT=1 autocommit)
elapsed=$(( $(date +%s) - start ))
check "hung push cut off (${elapsed}s)" '[ "$elapsed" -lt 5 ] && [ "$(remote_head)" != "$(git -C "$KB_ROOT" rev-parse HEAD)" ]'
check "timeout leaves a notice" 'grep -q "TIMED OUT" "$STATE/autocommit-notice"'
rm -f "$REMOTE/hooks/pre-receive"
sleep 5

# The next session start prints the notice, logs it, and clears it.
out=$(start_hook)
check "session start prints the notice" 'printf "%s" "$out" | grep -q "TIMED OUT"'
check "notice cleared after printing" '[ ! -s "$STATE/autocommit-notice" ]'
check "notice copied to the log" '[ "$(grep -c "TIMED OUT" "$STATE/autocommit.log")" -ge 2 ]'

# A failed push leaves a notice, and a later successful push clears it.
mv "$REMOTE" "$REMOTE.away"
echo "- third" >> "$KB_ROOT/gotchas.md"
autocommit
check "failed push leaves a notice" 'grep -q "PUSH FAILED" "$STATE/autocommit-notice"'
mv "$REMOTE.away" "$REMOTE"
autocommit
check "later success clears the notice" '[ ! -s "$STATE/autocommit-notice" ]'
check "unpushed commit caught up" '[ "$(remote_head)" = "$(git -C "$KB_ROOT" rev-parse HEAD)" ]'

# A run with nothing to do does not clear a notice nobody has seen yet.
printf '2026-01-01T00:00:00Z\tPUSH FAILED - test\n' > "$STATE/autocommit-notice"
autocommit
check "idle run keeps an unseen notice" 'grep -q "PUSH FAILED" "$STATE/autocommit-notice"'
rm -f "$STATE/autocommit-notice"

# An unwritable state directory writes the fallback notice instead.
chmod a-w "$STATE"
rm -f "$STATE/autocommit.log" 2>/dev/null
echo "- fourth" >> "$KB_ROOT/gotchas.md"
(KB_SESSION_STATE_ROOT="$STATE/sub" autocommit)
check "fallback notice written" 'grep -q "not writable" "$KB_AUTOCOMMIT_FALLBACK_NOTICE"'
chmod u+w "$STATE"
out=$(start_hook)
check "session start prints the fallback notice" 'printf "%s" "$out" | grep -q "not writable"'
check "fallback cleared once the state directory works" '[ ! -s "$KB_AUTOCOMMIT_FALLBACK_NOTICE" ]'

# Session ids that are not plain names never become marker files.
printf '{"session_id":"../escape","source":"startup"}' | sh "$ROOT/kb-session-start.sh" >/dev/null
check "bad session id writes no marker" '[ ! -e "$STATE/escape.start" ] && [ -z "$(ls "$STATE/markers" 2>/dev/null)" ]'

# A session end with no payload is logged.
printf '{}' | sh "$ROOT/kb-session-end.sh"
check "missing payload logged" 'grep -q "no-payload" "$STATE/experience-decisions.log"'
printf '{"session_id":"a/b","transcript_path":"%s"}' "$KB_ROOT/INDEX.md" | sh "$ROOT/kb-session-end.sh"
check "bad session id logged at session end" 'grep -q "bad-session-id" "$STATE/experience-decisions.log"'

# Credential-looking files stop the run: new ones, and ones in commits not yet pushed,
# even when a later commit deleted them again.
pushed=$(remote_head)
echo "token" > "$KB_ROOT/aws-credentials.md"
echo "- fifth" >> "$KB_ROOT/gotchas.md"
autocommit
check "untracked credential file stops the run" 'grep -q "credential-looking" "$STATE/autocommit-notice"'
check "nothing pushed with a credential file present" '[ "$(remote_head)" = "$pushed" ]'
check "nothing committed with a credential file present" '[ -n "$(git -C "$KB_ROOT" status --porcelain gotchas.md)" ]'
rm -f "$KB_ROOT/aws-credentials.md" "$STATE/autocommit-notice"
echo "KEY=1" > "$KB_ROOT/.env"
git -C "$KB_ROOT" add .env && git -C "$KB_ROOT" commit -qm "add env"
git -C "$KB_ROOT" rm -q .env && git -C "$KB_ROOT" commit -qm "remove env"
autocommit
check "credential file in an unpushed commit stops the push" 'grep -q ".env" "$STATE/autocommit-notice" && [ "$(remote_head)" = "$pushed" ]'
git -C "$KB_ROOT" reset -q --hard "$pushed"
rm -f "$STATE/autocommit-notice"

# A file staged by hand is left alone.
echo "- staged by hand" >> "$KB_ROOT/gotchas.md"
git -C "$KB_ROOT" add gotchas.md
autocommit
check "pre-staged work is not committed" '[ "$(git -C "$KB_ROOT" rev-parse HEAD)" = "$pushed" ] && grep -q "already staged" "$STATE/autocommit-notice"'
git -C "$KB_ROOT" reset -q
rm -f "$STATE/autocommit-notice"
autocommit
check "normal run works again afterwards" '[ "$(remote_head)" = "$(git -C "$KB_ROOT" rev-parse HEAD)" ] && [ "$(remote_head)" != "$pushed" ]'

if [ "$fails" -eq 0 ]; then
    echo "All kb-autocommit checks passed."
else
    echo "$fails check(s) failed."
    exit 1
fi
