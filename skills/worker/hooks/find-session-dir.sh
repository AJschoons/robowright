#!/bin/bash
#
# find-session-dir.sh — sourced by every worker hook.
#
# find_session_dir <cwd> <transcript_path> prints the armed Robowright Session's directory: the
# path held by the nearest .claude/autonomous-run marker between cwd and $HOME (when it sits under
# the sessions root; a marker naming any other directory arms nothing), else the
# ROBOWRIGHT_RUN_DIR of a desktop scheduled-task run (first user record starts `<scheduled-task `,
# and <dir>/run.json exists). Prints nothing when none is armed. The sentinel covers hooks that
# fire before the Worker's first `cd` into its worktree; autonomous-guard.sh parses it the same way.
# Also defines session_write, the one way a hook writes into the session dir.

# The first user record sits ~2 KB in; a scheduled-task prompt is a few KB at most.
readonly FIND_SESSION_TRANSCRIPT_HEAD_BYTES=65536
readonly SESSION_WRITE="$(dirname "${BASH_SOURCE[0]}")/../../robowright/scripts/session_write.py"

# session_write append|replace <path>: stdin into a file in the session dir. The session can plant a link or a FIFO
# at any name there and these hooks run outside the sandbox, so every hook write goes through this.
session_write() {
    command -v python3 >/dev/null 2>&1 || return 1
    python3 "$SESSION_WRITE" "$@"
}

# The sessions root as run-roster.py resolves it: $ROBOWRIGHT_SESSIONS_ROOT, else launch.json's
# sessions_root; resolved physically, or nothing when neither names a directory.
sessions_root() {
    local root="${ROBOWRIGHT_SESSIONS_ROOT:-}"
    [[ -n "$root" ]] || root=$(jq -r '.sessions_root // empty | strings' "$HOME/.claude/robowright/launch.json" 2>/dev/null)
    [[ -n "$root" ]] || return 0
    [[ "$root" == "~/"* ]] && root="$HOME/${root#"~/"}"
    (cd "$root" 2>/dev/null && pwd -P)
}

# The marker sits in the session's own worktree, so the dir it names is used only when it resolves
# under the sessions root.
marked_session_dir() {
    local root resolved
    [[ "$1" == /* ]] || return 0
    root=$(sessions_root)
    [[ -n "$root" ]] || return 0
    resolved=$(cd "$1" 2>/dev/null && pwd -P) || return 0
    [[ "$resolved" == "$root"/* ]] || return 0
    printf '%s' "$1"
}

find_session_dir() {
    local dir="$1"
    local transcript="$2"
    while [[ -n "$dir" && "$dir" != "/" ]]; do
        if [[ -f "$dir/.claude/autonomous-run" ]]; then
            marked_session_dir "$(tr -d '[:space:]' < "$dir/.claude/autonomous-run")"
            return 0
        fi
        [[ "$dir" == "$HOME" ]] && break
        dir=$(dirname "$dir")
    done

    [[ -f "$transcript" ]] || return 0
    local first_prompt
    first_prompt=$(head -c "$FIND_SESSION_TRANSCRIPT_HEAD_BYTES" "$transcript" | jq -R -n -r '
        first(inputs | fromjson? | select(.type == "user"))
        | .message.content
        | if type == "string" then . else ([.[]? | select(.type == "text") | .text] | join("\n")) end
    ' 2>/dev/null)
    [[ "$first_prompt" == "<scheduled-task "* ]] || return 0
    local run_dir
    run_dir=$(printf '%s\n' "$first_prompt" | sed -n 's|^ROBOWRIGHT_RUN_DIR=\(/[^[:space:]]*\)[[:space:]]*$|\1|p' | head -n 1)
    [[ -n "$run_dir" && -f "$run_dir/run.json" ]] || return 0
    printf '%s' "$run_dir"
}
