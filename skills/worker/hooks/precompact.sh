#!/bin/bash
#
# precompact.sh — PreCompact hook for the worker skill.
#
# Tells the compaction summarizer what a Robowright Session cannot afford to lose, and
# stamps the ledger so the next reader knows a compaction happened here. Never blocks.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[[ -n "$cwd" ]] || exit 0
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')

source "$(dirname "${BASH_SOURCE[0]}")/find-session-dir.sh"
run_dir=$(find_session_dir "$cwd" "$transcript")
[[ -n "$run_dir" && -f "$run_dir/run.json" ]] || exit 0

printf '\n%s compaction (%s) — re-read run.json, HANDOFF.md, and the skill non-negotiables before acting\n' \
    "$(date '+%Y-%m-%d %H:%M')" "$(printf '%s' "$input" | jq -r '.trigger // "unknown"')" | session_write append "$run_dir/LEDGER.md"

# HANDOFF.md's FIRST ACTION section, if present, so the summary carries the next step
# verbatim rather than a paraphrase of it.
first_action=""
if [[ -f "$run_dir/HANDOFF.md" ]]; then
    first_action=$(awk '/^## FIRST ACTION/{on=1; next} /^## /{if(on) exit} on' "$run_dir/HANDOFF.md" | head -20 | tr '\n' ' ' | cut -c1-1200)
fi

# Exit-0 stdout is appended to the summary request as custom compact instructions. Plain text
# only: output that opens with { is parsed as hook JSON instead.
printf '%s\n' "A Worker Robowright Session is in progress at $run_dir. Preserve verbatim: the session directory path, the worktree path, base_sha, the device lease and any build lock held, the current unit id and its branch, every quoted build/test verdict line not yet written to LEDGER.md, open review findings and their triage state, assumptions made, and the stop contract (only one-way-door, verification-failed, behavior-change, base-moved, budget, owner-stop, rebrief may end it). Drop raw tool output, file contents, log excerpts, UI dumps, and all completed-unit detail; those live in run.json, LEDGER.md, and evidence/ and must not be re-summarized."
[[ -z "$first_action" ]] || printf '%s\n' "HANDOFF.md FIRST ACTION, verbatim: $first_action"
exit 0
