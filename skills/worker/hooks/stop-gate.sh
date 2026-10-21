#!/bin/bash
#
# stop-gate.sh — Stop hook for the worker skill.
#
# The states and which of them release are modelled in the robowright skill's STATES.md
# (column stop_gate of the session machine); this hook reads the same run.json fields with jq
# because it runs on every turn end and its gate must not depend on python. Its writes go through
# session_write, so without python3 it still gates but keeps no counter and no ledger line, and
# the release after six unchanged blocks never fires: only the harness's block cap ends the loop.
#
# Blocks the turn from ending while a Robowright Session is in a non-terminal phase, so a
# premature "done" summary turns back into work. Releases when run.json says done,
# stopped or parked, when the Owner has created <session_dir>/STOP, when a session rotation has been
# requested at a unit boundary (rotate.requested_at set, rotate.resumed_at empty — the next
# session is started per the machine profile's Launch section), when a background task is
# still running (the harness wakes the session when it ends), when nothing is armed for
# this cwd, or after six consecutive blocks with no change to run.json (something is stuck;
# let the harness cap and the Owner see it).
#
# Claude Code overrides a Stop hook after eight consecutive blocks regardless; raise with
# CLAUDE_CODE_STOP_HOOK_BLOCK_CAP for overnight sessions.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[[ -n "$cwd" ]] || exit 0
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')

source "$(dirname "${BASH_SOURCE[0]}")/find-session-dir.sh"
run_dir=$(find_session_dir "$cwd" "$transcript")
[[ -n "$run_dir" && -f "$run_dir/run.json" ]] || exit 0

phase=$(jq -r '.phase // "unknown"' "$run_dir/run.json" 2>/dev/null)
# A hand edit can put anything here, and the phase reaches a ledger line.
[[ "$phase" =~ ^[a-z][a-z-]*$ ]] || phase="invalid"
# Older sessions wrote stop_reason as a bare string; both forms mean stopped.
stop_reason=$(jq -r '(.stop_reason | if type == "object" then .code else . end) // empty' "$run_dir/run.json" 2>/dev/null)

case "$phase" in
    done|stopped|parked) exit 0 ;;
esac
[[ -n "$stop_reason" ]] && exit 0
[[ -f "$run_dir/STOP" ]] && exit 0

# Unit-boundary rotation: a fresh session was asked for; let this one end.
rotate_requested=$(jq -r '.rotate.requested_at // empty' "$run_dir/run.json" 2>/dev/null)
rotate_resumed=$(jq -r '.rotate.resumed_at // empty' "$run_dir/run.json" 2>/dev/null)
if [[ -n "$rotate_requested" && -z "$rotate_resumed" ]]; then
    # Nothing here runs the integrity check, so only an ISO-8601 time is quoted into the ledger.
    [[ "$rotate_requested" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:?[0-9]{2})?$ ]] \
        || rotate_requested="at a time not in ISO-8601 form"
    printf '%s stop-gate: released for session rotation (requested %s) — start the next session per the machine profile, Launch section\n' \
        "$(date '+%Y-%m-%d %H:%M')" "$rotate_requested" | session_write append "$run_dir/LEDGER.md"
    exit 0
fi

# Paused, not done: Claude Code wakes the session when a running background task ends.
running_tasks=$(printf '%s' "$input" | jq -r '[.background_tasks[]? | select(.status == "running")] | length' 2>/dev/null)
(( ${running_tasks:-0} > 0 )) && exit 0

# Stuck detector: same run.json fingerprint across consecutive blocks.
fingerprint=$(jq -c '{phase, units: [.units[]? | {id, status, head}], updated_at}' "$run_dir/run.json" 2>/dev/null | shasum | cut -c1-12)
counter_file="$run_dir/.stop-gate-count"
last=""
count=0
if [[ -f "$counter_file" ]]; then
    read -r last count < "$counter_file" || true
fi
# The session can write this file and the hook runs outside the sandbox: bash arithmetic would
# evaluate the count as an expression, so anything but a plain number counts as 0.
[[ "$count" =~ ^[0-9]{1,6}$ ]] || count=0
count=$((10#$count))
if [[ "$last" == "$fingerprint" ]]; then
    count=$((count + 1))
else
    count=1
fi
printf '%s %s\n' "$fingerprint" "$count" | session_write replace "$counter_file"

if (( count >= 6 )); then
    printf '%s stop-gate: released after %s blocks with no state change (phase=%s)\n' \
        "$(date '+%Y-%m-%d %H:%M')" "$count" "$phase" | session_write append "$run_dir/LEDGER.md"
    exit 0
fi

remaining=$(jq -r '[.units[]? | select(.status != "done")] | length' "$run_dir/run.json" 2>/dev/null)
current=$(jq -r '[.units[]? | select(.status != "done")][0].id // "none"' "$run_dir/run.json" 2>/dev/null)

# decision and reason are top-level for a Stop hook; hookSpecificOutput carries only additionalContext.
jq -n --arg phase "$phase" --arg remaining "${remaining:-?}" --arg current "$current" --arg run_dir "$run_dir" '{
    decision: "block",
    reason: ("worker: this Robowright Session is in phase \($phase) with \($remaining) unit(s) not done (next: \($current)). Continue per the stop contract, or stop properly: python3 ~/.claude/skills/robowright/scripts/session-state.py \($run_dir) stop --code <code> --detail <why>, then rewrite HANDOFF.md before ending. Do not ask a question; nobody is watching.")
}'
exit 0
