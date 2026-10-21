#!/bin/bash
#
# resume-context.sh — SessionStart(compact) hook for the worker skill.
#
# After a compaction, re-injects the Robowright Session pointer and the first thing to do,
# because hook-added context and conversation-only instructions do not survive the summary.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[[ -n "$cwd" ]] || exit 0
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')

source "$(dirname "${BASH_SOURCE[0]}")/find-session-dir.sh"
run_dir=$(find_session_dir "$cwd" "$transcript")
[[ -n "$run_dir" && -f "$run_dir/run.json" ]] || exit 0

phase=$(jq -r '.phase // "unknown"' "$run_dir/run.json")
current=$(jq -r '[.units[]? | select(.status != "done")][0] | "\(.id // "none") on \(.branch // "?") (head \(.head // "unknown"))"' "$run_dir/run.json")
udid=$(jq -r '.device.udid // "unknown"' "$run_dir/run.json")
worktree=$(jq -r '.worktree // "unknown"' "$run_dir/run.json")

jq -n --arg run_dir "$run_dir" --arg phase "$phase" --arg current "$current" --arg udid "$udid" --arg worktree "$worktree" '{
    hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext: ("You are the Worker in a Robowright Session already under way. run_dir=\($run_dir) phase=\($phase) worktree=\($worktree) device=\($udid). Current unit: \($current). Before any other action: read \($run_dir)/run.json, then \($run_dir)/HANDOFF.md, then the Non-negotiables section of ~/.claude/skills/worker/SKILL.md; confirm git rev-parse HEAD in the worktree matches the current unit head; then continue from HANDOFF.md FIRST ACTION. Do not repeat completed units. Do not ask questions.")
    }
}'
exit 0
