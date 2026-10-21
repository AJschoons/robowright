#!/usr/bin/env bash
# Runs every suite the project hook lists, then the whole-tree scrub check.
#
# One line per suite: `<suite>: <verdict>`; a suite whose script is not in the tree prints
# `<suite>: skipped (not yet in tree)` and does not fail the run. Ends `EXIT=<n>`, n non-zero
# when any suite or the scrub check failed. Run from anywhere; it works from the repo root.

set -uo pipefail
cd "$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)" || exit 2

readonly SUITES=(
    "scrub gate|tests/scrub-gate/test_scrub_gate.py"
    "role launcher|tests/role-start/test_role_start.py"
    "session state|skills/robowright/scripts/test_session_state.py"
    "owner git|skills/robowright/scripts/test_owner_git.py"
    "robowright-resolve|skills/robowright/scripts/test_robowright_resolve.py"
    "run roster|skills/lead/scripts/test_run_roster.py"
    "budget modes|skills/lead/scripts/test_budget_modes.py"
    "accept|skills/lead/scripts/test_accept.py"
    "run cost|skills/worker/scripts/test_run_cost.py"
    "cost rollup|skills/robowright/scripts/test_robowright_cost.py"
    "pricing|skills/robowright/scripts/test_pricing.py"
    "launcher|tests/run-launch/test_run_launch.py"
    "rw-git|tests/rw-git/test_rw_git.py"
    "plan usage|tests/usage/test_usage.py"
    "dashboard|tests/dash/test_dash.py"
    "install|tests/install/test_install.py"
    "conventions|tests/conventions/test_conventions.py"
)

status=0
log=$(mktemp "${TMPDIR:-/tmp}/run-tests.XXXXXX") || exit 2
trap 'rm -f "$log"' EXIT

for row in "${SUITES[@]}"; do
    name="${row%%|*}"
    script="${row#*|}"
    if [[ ! -f "$script" ]]; then
        echo "$name: skipped (not yet in tree)"
        continue
    fi
    python3 "$script" > "$log" 2>&1
    code=$?
    # unittest prints `Ran N tests in …` then `OK` or `FAILED (...)`; budget modes ends `all passed`.
    # A runner may colour its verdict; strip the escapes before matching.
    plain=$(sed $'s/\x1b\\[[0-9;]*m//g' "$log")
    count=$(grep -E '^Ran ' <<< "$plain" | tail -1)
    verdict=$(grep -E '^(OK|FAILED|all passed)' <<< "$plain" | tail -1)
    if [[ $code -ne 0 ]]; then
        status=1
        echo "$name: FAILED exit=$code ${count} ${verdict}"
    else
        echo "$name: ${count:+$count · }${verdict:-exit 0}"
    fi
done

# The gate's lines reach the caller untouched; it never prints a pattern, so there is nothing to filter.
tools/scrub-gate.sh --tree || status=1

echo "EXIT=$status"
exit "$status"
