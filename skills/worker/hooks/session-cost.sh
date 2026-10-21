#!/bin/bash
#
# session-cost.sh — SessionEnd hook for the worker skill.
#
# Records what a Robowright Session has cost so far, without it having to remember to. Finds the
# armed session directory from cwd, runs scripts/run-cost.py --write (which stores
# run.json.cost from the worktree's transcripts, plus this session's transcript in case the
# slug walk misses it), appends this Claude session's records to the accounting ledger
# (run-cost.py --ledger), and stamps one line in LEDGER.md. The estimated dollar figure joins that
# line only when run.json carries a dollar budget (spend_threshold_usd or spend_cap_usd); the
# request, token, and context figures are facts either way. Never blocks.
#
# An unarmed session is a no-op, unless a doc-role skill registered this hook with `--role
# planner|lead|explainer`: then its session and sidecars go to the ledger under that role, and
# nothing else is written. An armed cwd is the Worker's whatever --role says.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

role=""
[[ "${1:-}" == "--role" ]] && role="${2:-}"

input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[[ -n "$cwd" ]] || exit 0
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
run_cost="$script_dir/../scripts/run-cost.py"
[[ -f "$run_cost" ]] || exit 0

source "$(dirname "${BASH_SOURCE[0]}")/find-session-dir.sh"
run_dir=$(find_session_dir "$cwd" "$transcript")
if [[ -z "$run_dir" || ! -f "$run_dir/run.json" ]]; then
    case "$role" in
        planner|lead|explainer) ;;
        *) exit 0 ;;
    esac
    [[ -n "$session_id" && -n "$transcript" && -f "$transcript" ]] || exit 0
    python3 "$run_cost" --ledger --role "$role" --session-id "$session_id" --transcript "$transcript" --cwd "$cwd" >/dev/null 2>&1 || true
    exit 0
fi

args=(--run-dir "$run_dir" --write --json)
[[ -n "$transcript" && -f "$transcript" ]] && args+=(--transcript "$transcript")

out=$(python3 "$run_cost" "${args[@]}" 2>/dev/null) || out=""

# The accounting ledger counts this Claude session and its sidecars only; a failure here is never
# the session's problem. It also records any closed unit whose unit-close call never ran.
if [[ -n "$session_id" && -n "$transcript" && -f "$transcript" ]]; then
    python3 "$run_cost" --run-dir "$run_dir" --ledger --session-id "$session_id" --transcript "$transcript" >/dev/null 2>&1 || true
fi

[[ -n "$out" ]] || exit 0
# The estimate is quoted only when the brief carries a dollar budget (machine profile → Budget).
has_dollar_budget=$(jq -r '(.spend_threshold_usd != null) or (.spend_cap_usd != null)' "$run_dir/run.json" 2>/dev/null)
[[ "$has_dollar_budget" == "true" ]] || has_dollar_budget="false"
summary=$(printf '%s' "$out" | jq -r --argjson dollars "$has_dollar_budget" '"requests \(.requests) · out \(.output_tokens) · avg ctx \(.avg_context_tokens)" + (if $dollars then " · est " + (if .estimated_usd == null then "n/a" else "$\(.estimated_usd)" end) else "" end) + " · lines written \(.lines_written)" + (if .lines_shipped then " · shipped +\(.lines_shipped.added)/-\(.lines_shipped.removed)" else "" end)' 2>/dev/null)
[[ -n "$summary" ]] || exit 0

reason=$(printf '%s' "$input" | jq -r '.reason // "unknown"')
printf '\n%s session-cost (%s): %s — run.json.cost updated\n' "$(date '+%Y-%m-%d %H:%M')" "$reason" "$summary" | session_write append "$run_dir/LEDGER.md"
exit 0
