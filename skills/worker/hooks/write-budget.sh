#!/bin/bash
#
# write-budget.sh — PostToolUse(Write|Edit) hook for the worker skill.
#
# Makes the artifact budgets real without blocking a legitimate write. After a Write or
# Edit lands on one of a Robowright Session's state files, it measures the payload and, when the
# file is over budget or the write bypassed the ledger appender, feeds one line back into the
# model's context as additionalContext. Never denies (the tool has already run), never edits
# the file. Silent for every write outside the session directory.
#
# Budgets (lines of the payload — Write `content` or Edit `new_string`):
#   LEDGER.md    any direct Write/Edit where the profile names a ledger appender (≤25 lines)
#   run.json     written at unit close and on stop only; payload over 400 lines flagged. A write
#                that changed a field session-state.py owns is flagged first (STATES.md)
#   HANDOFF.md   rewritten at unit boundaries only; payload over 200 lines flagged
#   HANDBACK.md  payload over 200 lines flagged ("under two pages", per its template)
#   anything else under the session directory (prs/, reviews/, smoke/): over 400 lines flagged

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')
case "$tool" in Write|Edit|MultiEdit) ;; *) exit 0 ;; esac

cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[[ -n "$cwd" ]] || exit 0
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')

source "$(dirname "${BASH_SOURCE[0]}")/find-session-dir.sh"
run_dir=$(find_session_dir "$cwd" "$transcript")
[[ -n "$run_dir" ]] || exit 0

file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[[ -n "$file" ]] || exit 0
case "$file" in "$run_dir"/*) ;; *) exit 0 ;; esac

payload_lines=$(printf '%s' "$input" | jq -r '
    (.tool_input.content // .tool_input.new_string // ([.tool_input.edits[]?.new_string] | join("\n")) // "")
    | split("\n") | length')
name=$(basename "$file")
rel=${file#"$run_dir"/}

msg=""
case "$name" in
    LEDGER.md)
        msg="LEDGER.md was written directly ($payload_lines-line payload). Entries go through the ledger appender the machine profile names (Tools), which enforces the 25-line budget; where it names none, one Write append of at most 25 lines. Detail belongs in evidence/<name>.md, written once and cited by path." ;;
    run.json)
        # phase, stop_reason, rotate, rebriefs and a unit's status, gate_attempts and head have
        # one writer. The tool's own check says whether this write touched them.
        state_tool="$HOME/.claude/skills/robowright/scripts/session-state.py"
        edited=""
        # check exits 1 on exactly the case we are looking for, so pipefail must not decide this.
        [[ -f "$state_tool" ]] && edited=$(python3 "$state_tool" "$run_dir" check 2>/dev/null | grep -m1 'edited-outside-tool' || true)
        if [[ -n "$edited" ]]; then
            msg="run.json: ${edited#INVALID: }. Those fields are written only by python3 $state_tool $run_dir <event> (status lists the events legal now). Put the field back as it was, then apply the event; the launcher refuses this session and the roster flags it until check passes."
        fi
        [[ -n "$msg" ]] || (( payload_lines <= 400 )) || msg="run.json payload was $payload_lines lines. Budget: write it at unit close and on stop only, and keep prose out of it — long notes go to LEDGER.md (via the ledger appender) or evidence/, not into gate fields." ;;
    HANDOFF.md|HANDBACK.md)
        (( payload_lines > 200 )) && msg="$name payload was $payload_lines lines; budget is ~200. It is a cold-start doc, not a log: point at LEDGER.md and evidence/ paths instead of restating them, and rewrite it only at unit boundaries." ;;
    *)
        (( payload_lines > 400 )) && msg="$rel payload was $payload_lines lines. Every line here is re-read on every later request of this session; write detail once and cite the path." ;;
esac
[[ -n "$msg" ]] || exit 0

jq -n --arg msg "worker write budget: $msg" '{
    hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: $msg
    }
}'
exit 0
