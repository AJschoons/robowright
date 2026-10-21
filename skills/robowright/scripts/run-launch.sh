#!/usr/bin/env bash
#
# run-launch.sh — start one Robowright Worker as a background Claude Code session in the
# Robowright Session's own worktree, or resume one that stopped. It also starts the two
# document-only roles: a Planner (brief | rebrief | review) and an Explainer (guide | report).
#
# This one WRITES: it starts a session that commits to the Robowright Session's branches. The
# command it runs is fixed — `claude --bg --model <m> --name <name> "/worker <session_dir>"`
# in the worktree named by run.json, plus the MCP flags run.json's `mcp` picks choose (absent, null
# or [], the default, starts the session with no MCP servers at all; each pick names a server on
# the approved list in ../mcp/, whose entry becomes the config and whose allow rules, or the pick's
# own, go out as --allowedTools) and `--tools` with run.json's `tools` (null, the default, is the
# lean list below)
# — and on --resume the first prompt is the same /worker
# invocation followed by one of two fixed sentences, chosen by the newest applied event in
# events.jsonl: a `resume` event means a decision is waiting in LEDGER.md, anything else means
# the process ended with neither. Never text from argv; nothing free-form passes through.
#
# It NEVER pushes and never touches a remote. Everything it starts works on local branches;
# publishing is a local branch plus the Explainer's guide, and accepting it is the Owner's word.
#
# launch.json's `launch` key says who starts the session: `auto`, this script runs `claude --bg`
# itself; `paste`, or no key, it starts nothing and hands the line off. A hand-off prints
# `paste this yourself:` and the line to run, appends a `hand-off via` ledger entry, prints
# `launch is yours`, and exits 0; run.json is untouched except the cost block a --rotate or --resume records first. Under `auto` an EPERM from `claude --bg`
# is the same hand-off: this shell cannot start a background session, and the machine profile's
# Launch section says what one needs. Any other `claude` failure exits 1. Once the line has been
# pasted, `--pin <id>` records the started session in run.json as a launch would; it starts
# nothing and runs no launch check.
#
# Refuses: a Robowright Session dir outside the sessions root; one whose phase is done; a worktree
# that no configured repository lists (owner_git.py, which also sets the options every git call in
# it carries), that is the main clone, missing, not the git toplevel, or dirty — except on --resume, where the
# uncommitted work is the resumed Robowright Session's own and the prompt says so; a launch, rotate or
# resume that session-state.py check-op says is not legal from the stored state
# (robowright skill, STATES.md); a STOP file; a live Claude session already in that worktree;
# --resume with no session id to resume; a Worker whose run.json locks
# names a lock that another Robowright Session holds; a non-null run.json `mcp_config` (retired: `mcp`
# replaced it); an `mcp` that is not a list of picks; an `mcp` pick whose server, workflow or allow
# rule the approved list does not allow, or whose binary is missing or outside its pin; an approved
# list holding a malformed entry, once any server is picked; a launch.json
# that is missing, written to another schema, short a key, or whose `launch` is neither paste nor auto;
# a model from any source outside the form in ../models.json; a `tools` outside KNOWN_TOOLS; a
# session id to resume that is not a UUID; a session dir with no ticket whose name is not a unit
# name; a missing worktree whose run.json branch git would not accept as a branch name.
#
#   run-launch.sh --run-dir <sessions root>/<unit>                     prompt first
#   run-launch.sh --run-dir <dir> --yes                                unattended
#   run-launch.sh --run-dir <dir> --dry-run                            plan only
#   run-launch.sh --run-dir <dir> --resume                             resume run.json's session_id
#   run-launch.sh --run-dir <dir> --resume <session-id> --yes                     resume a named session
#   run-launch.sh --run-dir <dir> --rotate --yes                       fresh session at a unit boundary
#   run-launch.sh --run-dir <dir> --pin <background id | sessionId>    record a pasted hand-off
#   run-launch.sh --planner brief   --project <project dir> --slug <slug> --dry-run
#   run-launch.sh --planner rebrief --project <project dir> --run-dir <dir> --yes
#   run-launch.sh --planner review  --project <project dir> --run-dir <dir> --yes
#   run-launch.sh --explainer guide  --project <project dir> --run-dir <dir> --yes
#   run-launch.sh --explainer report --project <project dir> --yes
#   run-launch.sh --direct --project <project dir> --slug <unit> --repo <repo> --base <full commit id>
#                 --briefing <project dir>/briefings/<file>.md [--model <m>] [--effort <e>] --dry-run
#
# --direct starts a direct build (the planner handbook → Size `S` or below), which has no run.json and no Robowright
# Session. role_grants.py direct makes <repo>/.worktrees/<unit> on robowright/<unit> from --base with a Worker's
# checks (a repository `repos` lists, no link or `.`/`..` at any prefix, a full commit id, attributes off), or reuses
# it when it is already that repository's worktree of that branch, at the old <repo>/.claude/worktrees/<unit> too while
# nothing is at the new place; anything else there is refused. The session is
# build-<unit>, started in the worktree with role_grants.py document's grants, no MCP servers, and one fixed prompt:
# `Build directly from the briefing at <briefing>: read it in full, and follow it.` The briefing is a regular file
# with one link, named one segment ending .md, directly in <project dir>/briefings/. The launch and a hand-off are
# logged in <project dir>/DECISIONS.md. After an `auto` start the registry must show the session's cwd is the
# worktree; otherwise it exits 1 naming both. --name, --ticket, --run-dir, --resume, --rotate and --pin are refused.
#
# --planner <mode> is the other launch this script makes: a fresh Planner session, started in
# the project folder with a fixed prompt, on the model the project's robowright.json names for the
# Planner (the run profile's document model when the file or the field is missing), and — like
# the Explainer — with no MCP
# servers at all, since both roles only read the plan and write markdown. Three modes, all end
# without launching:
#   brief     write BRIEF.md and run.json into <sessions root>/<unit>/ from the corrected plan;
#             refuses if BRIEF.md already exists
#   rebrief   a Robowright Session stopped three times: rewrite <session_dir>/BRIEF.md in place,
#             write REBRIEF.md (confident | owner), apply session-state.py's rebrief event; the
#             Lead then runs --rotate. Refuses a session that is not stopped, or has a STOP file
#   review    end-of-stack intent check: write <session_dir>/PLAN-REVIEW.md (ship | polish |
#             rebrief). Refuses a session that is not done or has no INTAKE.md
#
# --explainer <mode> launches an Explainer session the same way, on robowright.json's
# models.explainer (opus under every run profile when absent):
#   guide     a published stack's owner brief → <project>/<launch.json review_guide_dir>/<id>-owner-brief.md.
#             Needs a done Robowright Session with INTAKE.md; refuses if the brief exists
#   report    the end-of-project report → <project>/REPORT.md; refuses if it exists
#
#   --run-dir <path>      the Robowright Session directory holding BRIEF.md and run.json (required
#                         unless --planner brief / --explainer report). --session-dir is accepted
#                         as an alias, for the briefs and handbooks that still carry it
#   --planner <mode>      launch a Planner instead of a Worker: brief | rebrief | review (above)
#   --brief               shorthand for --planner brief
#   --direct              launch a direct build (above), with --project, --slug, --repo, --base and --briefing
#   --explainer <mode>    launch an Explainer instead of a Worker: guide | report (above)
#   --project <dir>       with --planner / --explainer: the project folder holding PROJECT.md
#                         and robowright.json (required)
#   --slug <slug>         with --planner brief: the readable half of the Robowright Session dir name.
#                         Lowercase letters, digits and hyphens, shaped by launch.json's
#                         unit.slug_regex; the refusal shows unit.slug_example (required)
#   --ticket <key>        with --planner brief, where launch.json names a unit.ticket_regex: the
#                         tracker key this brief is for. It prefixes the Robowright Session dir and is
#                         the unit id every later name is built from. Where launch.json names no
#                         ticket shape, this flag is refused rather than ignored
#   --name <name>         session display name; default: the worker prefix, the model and the unit
#                         id, lowercased. The document roles default to planner-<id>,
#                         planner-<id>-r<n>, planner-<id>-review and explainer-<id>
#   --model <alias>       the Worker variant: opus (default) or sonnet; also haiku, fable, or a
#                         full model id. Default: the `model` of the first unit that is not done,
#                         else run.json `model`, else the profile's model for that unit's kind.
#                         Passed as `claude --model` and recorded in the LEDGER entry; run.json
#                         `model` is the brief's own and is never written over, because the next
#                         unit inherits it
#   --profile <name>      showcase | standard | economy — the run profile, one field the launcher
#                         expands into a Worker model and an effort per unit kind (the table by
#                         `profile_expand` below). Overrides run.json `profile`; for a
#                         document-only launch, where there may be no run.json yet, this flag is
#                         the only source and defaults to standard. An unknown name is refused
#   --effort <level>      low | medium | high | xhigh | max for the session, overriding run.json
#                         `effort` and the profile. Passed BOTH as `claude --effort` (which wins
#                         outright but is not among the flags a backgrounded session carries over
#                         a supervisor wake) and inside `--settings` (which is carried over, and
#                         is re-read on every process the session starts)
#   --resume [id]         resume instead of launch; id defaults to run.json's session_id. A
#                         stopped session is refused until whoever decided has applied
#                         `session-state.py <dir> resume --by <owner|lead> --decision <text>`
#   --rotate              start a FRESH session for a Robowright Session that requested rotation at a
#                         unit boundary (state awaiting-rotation). Same fixed prompt as a launch; the preflight sees the request
#                         and continues from HANDOFF.md FIRST ACTION. Stop the previous session
#                         first (`claude stop <id>`) — this refuses while one is live
#   --stop-cap <n>        CLAUDE_CODE_STOP_HOOK_BLOCK_CAP for the session (default 40)
#   --compact-pct <n>     CLAUDE_AUTOCOMPACT_PCT_OVERRIDE for the session: the context window
#                         auto-compacts at this percentage of its normal fill (default: run.json
#                         `compact_pct`, else 85). Lower = smaller average context per request.
#                         The variable only lowers the threshold; a value above the default
#                         percentage is ignored, which is how the document roles neutralise it
#   --subagent-model <a>  CLAUDE_CODE_SUBAGENT_MODEL for the session: the default model of every
#                         subagent the session spawns (default sonnet). Reviewer agent files that
#                         pin `model:` outrank it, so the code Reviewers stay on opus regardless
#
# These three are environment variables, and a `claude --bg` session never sees the launcher's
# environment: the background daemon pre-forks a pool of spare processes and the launch claims
# one, so a session carries the environment of whoever started the daemon (measured 2026-09-22:
# a Worker launched with compact_pct 85 compacted at 50% because a Worker on another project with
# compact_pct 50 had started the daemon a day earlier). They therefore travel inside
# `--settings`, whose `env` block Claude Code writes into the process environment over the
# inherited value (docs: env-vars, "in settings files"). The launcher's own environment is
# scrubbed of them before the call, so a daemon this launch happens to start is clean.
#   --dry-run             print the plan, start nothing
#   --yes                 do not prompt for confirmation
#
# Every fact that differs between installs is read from `launch.json` beside the machine profile,
# at ~/.claude/robowright/launch.json: `sessions_root`, `review_guide_dir`, `report_scope`, the optional
# `launch` (`paste` or `auto`; no key means `paste`), and the `unit` block (`ticket_regex`, `ticket_example`, `slug_regex`, `slug_example`, `group_regex`)
# that says what a unit of work is called here, plus `repos`, which owner_git.py reads to decide the
# worktree is trusted. The patterns are POSIX ERE as bash reads them.
# This script ships no default for any of it but `launch` and refuses by name when the file or a key is
# missing. The two scripts it shells out to, session-state.py and run-cost.py, are found beside
# its own real path.
#
# Writes: <worktree>/.claude/autonomous-run (the session marker), one LEDGER.md entry, run.json's
# session_id and transcripts, and the background session itself. A --rotate or --resume first
# records the replaced session's cost in run.json (`claude stop` runs no SessionEnd hook), and
# never fails the launch over it. Watch it with `claude attach <id>` or `claude logs <id>`.
#
set -euo pipefail

# The bare name on PATH is a stow link to a link, so follow the chain: the real file's directory
# is where the tools this script shells out to sit. bash 3.2 has no `readlink -f`.
HERE="${BASH_SOURCE[0]}"
while [ -L "$HERE" ]; do
    LINK="$(readlink "$HERE")"
    case "$LINK" in
        /*) HERE="$LINK" ;;
        *)  HERE="$(dirname "$HERE")/$LINK" ;;
    esac
done
HERE="$(cd "$(dirname "$HERE")" && pwd -P)"

LAUNCH_CONFIG="$HOME/.claude/robowright/launch.json"
CLAUDE_SESSIONS_ROOT="$HOME/.claude/sessions"
# Two fixed prompts; the newest applied event picks one (below). Both open with the sentence
# the worker skill's Phase 0 step 1 reads as "this is a resume, not a start".
RESUME_PROMPT_ANSWERED="Resume this Robowright Session: the decision that answered your stop is the newest entry in LEDGER.md, and whoever decided has already applied the resume event, so run.json is back in the phase you left. Apply the decision per the worker skill's Compaction and resumption section, then continue from HANDOFF.md FIRST ACTION under the stop contract. Completed units are done; do not revisit them."
RESUME_PROMPT_ORPHAN="Resume this Robowright Session: the process ended with no stop and no decision, so nothing is waiting for you in LEDGER.md. Re-read the worker skill's Non-negotiables and the phase step you were in, check git status in the worktree, then continue from HANDOFF.md FIRST ACTION under the stop contract. Completed units are done; do not revisit them."
# Appended to whichever prompt is chosen when the resumed worktree still holds its own work.
DIRTY_PROMPT="The worktree has uncommitted changes from before the process ended: inspect them with git status and git diff, keep what belongs to the unit in flight, and never run git checkout -- over them."

# The two document-role flags, and the name this script is reached by. The role word in the
# messages built from SIDE is one of these flags with its dashes off, so those messages follow a
# renamed flag; the other `fail` lines that name a flag spell it out. The plain key beside it is what
# robowright.json is written in.
PLANNER_FLAG="--planner"
EXPLAINER_FLAG="--explainer"
LAUNCHER_NAME="$(basename "$0")"

SESSION_DIR=""
DIRECT="false"
REPO=""
BASE=""
BRIEFING=""
PLANNER_MODE=""
EXPLAINER_MODE=""
ROLE_KEY=""
SIDE=""
PROJECT=""
SLUG=""
TICKET=""
UNIT_ID=""
NAME=""
RESUME="false"
ROTATE="false"
RESUME_ID=""
PIN="false"
PIN_ID=""
NAME_GIVEN="false"
STOP_CAP="40"
COMPACT_PCT=""
MODEL=""
EFFORT=""
PROFILE=""
SUBAGENT_MODEL="sonnet"
DRY_RUN="false"
ASSUME_YES="false"

while [ $# -gt 0 ]; do
    case "$1" in
        --session-dir|--run-dir) SESSION_DIR="$2"; shift 2 ;;
        "$PLANNER_FLAG")   PLANNER_MODE="$2"; shift 2 ;;
        --brief)           PLANNER_MODE="brief"; shift ;;
        --direct)          DIRECT="true"; shift ;;
        --repo)     REPO="$2"; shift 2 ;;
        --base)     BASE="$2"; shift 2 ;;
        --briefing) BRIEFING="$2"; shift 2 ;;
        "$EXPLAINER_FLAG") EXPLAINER_MODE="$2"; shift 2 ;;
        --project)  PROJECT="$2"; shift 2 ;;
        --slug)     SLUG="$2"; shift 2 ;;
        --ticket)   TICKET="$2"; shift 2 ;;
        --name)     NAME="$2"; NAME_GIVEN="true"; shift 2 ;;
        --resume)
            RESUME="true"
            if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then RESUME_ID="$2"; shift 2; else shift; fi ;;
        --rotate)   ROTATE="true"; shift ;;
        --pin)
            PIN="true"
            if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then PIN_ID="$2"; shift 2; else shift; fi ;;
        --stop-cap) STOP_CAP="$2"; shift 2 ;;
        --compact-pct) COMPACT_PCT="$2"; shift 2 ;;
        --model)    MODEL="$2"; shift 2 ;;
        --effort)   EFFORT="$2"; shift 2 ;;
        --profile)  PROFILE="$2"; shift 2 ;;
        --subagent-model) SUBAGENT_MODEL="$2"; shift 2 ;;
        --dry-run)  DRY_RUN="true"; shift ;;
        --yes|-y)   ASSUME_YES="true"; shift ;;
        -h|--help)  awk 'NR>1 && !/^#/{exit} NR>1{sub(/^# ?/,""); print}' "$0"; exit 0 ;;
        *)          echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

command -v claude >/dev/null || { echo "claude not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }
command -v git >/dev/null || { echo "git not found" >&2; exit 1; }

# Refusals and the plan quote session-written values, so both reach the terminal with control bytes dropped.
OWNER_GIT="$HERE/owner_git.py"
show() { python3 "$OWNER_GIT" show; }
fail() { printf 'refusing: %s\n' "$*" | show >&2; exit 1; }

# The session can plant a link or a FIFO at any name in its folder and worktree, and this script runs outside the
# sandbox: every file it writes there goes through session_write.py.
SESSION_WRITE="$HERE/session_write.py"
#   append_to <file>: stdin appended to <file>
append_to() { python3 "$SESSION_WRITE" append "$1" || fail "nothing was appended to $1 (above)"; }
# run.json's worktree reaches a ledger line, so it holds no newline or other control character.
worktree_one_line() { case "$1" in *[[:cntrl:]]*) fail "run.json 'worktree' holds a control character, and it reaches the ledger" ;; esac; }
# Each file a launch writes, checked before anything starts; a missing one passes and is not created.
#   check_writable <file>...
check_writable() { python3 "$SESSION_WRITE" check "$@" || fail "a file this launch writes is not a plain file (above); nothing started"; }

# Hands the launch to whoever pastes the line into a shell that can start a background session.
# Writes no phase to run.json: the stored phase is already the one a started session would begin from.
#   handoff <dir to start in> <ledger file> <entry body, one "- …" line per line>
handoff() {
    local paste
    # Pasted any time later, so it starts only where the launcher checked, as start_or_handoff does.
    paste="$(printf 'cd %q && [ "$(pwd -P)" = %q ] &&' "$1" "$1"; printf ' %q' "${SCRUB_ENV[@]}" "${CMD[@]}")"
    echo "paste this yourself:"
    printf '%s\n' "$paste"
    # The Lead re-hands an unpasted hand-off from here; the printed line is gone after a rotation.
    {
        printf '\n## %s — hand-off via %s\n' "$(date '+%Y-%m-%d %H:%M')" "$LAUNCHER_NAME"
        printf '%s\n' "$3"
        printf -- '- paste: %s\n' "$paste"
    } | append_to "$2"
    echo "launch is yours"
    exit 0
}

# The one place a launch starts or is handed off, so the Worker and document-only sites cannot
# drift. Leaves claude's output in $OUT when it started a session; every other path exits.
#   start_or_handoff <dir to start in> <ledger file> <function printing the entry body from its "why nothing started" line>
start_or_handoff() {
    cd "$1"
    # A folder above it may have been swapped for a link since it was checked; once the shell is in it, the session's
    # working directory, and a ledger named relative to it, stay that directory whatever its path names later.
    [ "$(pwd -P)" = "$1" ] || fail "$1 changed after it was checked: it now leads to $(pwd -P); nothing started"
    [ "$LAUNCH_MODE" = "auto" ] || handoff "$1" "$2" "$("$3" "- launch: paste; nothing started")"
    OUT="$("${SCRUB_ENV[@]}" "${CMD[@]}" 2>&1)" && return 0
    echo "$OUT" >&2
    case "$OUT" in
        *EPERM*|*"operation not permitted"*)
            echo "hint: this shell could not start a background session; see the machine profile's Launch section, or set \"launch\": \"paste\" in $LAUNCH_CONFIG" >&2
            handoff "$1" "$2" "$("$3" "- EPERM; nothing started")" ;;
    esac
    exit 1
}

# A path given on argv, made absolute against this shell's directory, `//` squeezed and a trailing `/` dropped, and
# never resolved: role_grants.py refuses a link or a `.`/`..` in what this prints.
#   spelled_path <path>
spelled_path() {
    local path="$1"
    case "$path" in /*) ;; *) path="$PWD/$path" ;; esac
    printf '%s' "$path" | sed -e 's#//*#/#g' -e 's#\(.\)/$#\1#'
}

# Refuses when a live session in the registry is named $1.
#   refuse_live_name <name>
refuse_live_name() {
    local f n pid msg
    for f in "$CLAUDE_SESSIONS_ROOT"/*.json; do
        [ -f "$f" ] || continue
        n="$(jq -r '.name // empty' "$f" 2>/dev/null)" || continue
        [ "$n" = "$1" ] || continue
        pid="$(jq -r '.pid // empty' "$f")"
        [ -n "$pid" ] || continue
        msg="$(kill -0 "$pid" 2>&1 || true)"
        case "$msg" in *"No such process"*) continue ;; esac
        fail "a live session named $1 already exists (pid $pid). Attach to it or stop it first"
    done
}

# Refuses when a live session in the registry runs in the directory $1.
#   refuse_live_in <dir>
refuse_live_in() {
    local f cwd pid msg live="" live_stop=""
    for f in "$CLAUDE_SESSIONS_ROOT"/*.json; do
        [ -f "$f" ] || continue
        cwd="$(jq -r '.cwd // empty' "$f" 2>/dev/null)" || continue
        [ -n "$cwd" ] || continue
        cwd="$(cd "$cwd" 2>/dev/null && pwd -P)" || continue
        [ "$cwd" = "$1" ] || continue
        pid="$(jq -r '.pid // empty' "$f")"
        [ -n "$pid" ] || continue
        # kill -0 on a process we do not own is EPERM (exit 1 with a message), which still means alive;
        # a dead pid is ESRCH. Distinguish by the message.
        msg="$(kill -0 "$pid" 2>&1 || true)"
        case "$msg" in
            *"No such process"*) continue ;;
        esac
        live="$(jq -r '"\(.name // "unnamed") [\(.status // "?")], pid \(.pid), session \(.sessionId // "?")"' "$f")"
        # `claude stop` takes the eight-character id `claude agents --json` prints, never the name.
        live_stop="claude stop $(jq -r '.sessionId // "?"' "$f" | cut -c1-8)"
        break
    done
    [ -z "$live" ] || fail "a live Claude session is already in $1: $live. Message it, attach to it, or stop it first: $live_stop"
}

# The full sessionId of the registered session whose id starts with $1, or nothing.
registry_session_id() {
    local f sid
    for f in "$CLAUDE_SESSIONS_ROOT"/*.json; do
        [ -f "$f" ] || continue
        sid="$(jq -r '.sessionId // empty' "$f" 2>/dev/null)" || continue
        case "$sid" in "$1"*) printf '%s\n' "$sid"; return ;; esac
    done
}

# The cwd of the registered session whose sessionId is exactly $1, or nothing.
registry_session_cwd() {
    local f
    for f in "$CLAUDE_SESSIONS_ROOT"/*.json; do
        [ -f "$f" ] || continue
        [ "$(jq -r '.sessionId // empty' "$f" 2>/dev/null)" = "$1" ] || continue
        jq -r '.cwd // empty' "$f" 2>/dev/null
        return
    done
}

# run.json.session_id is what a later --resume defaults to, and run.json.transcripts is what the
# cost report and the roster price the Robowright Session from — unpinned, they fall back to every
# transcript the worktree ever saw. Both written under session-state.py's lock: the Worker's
# first events land within minutes.
#   pin_session <session dir> <sessionId> <worktree>
pin_session() {
    python3 - "$HERE" "$1" "$2" "$3" <<'PY'
import json, os, re, sys
sys.path.insert(0, sys.argv[1])
import session_write
session_dir, session_id, worktree = sys.argv[2], sys.argv[3], sys.argv[4]
run_json = os.path.join(session_dir, "run.json")
# Claude Code names a project dir after the cwd with every non-alphanumeric turned into "-"
# (run-cost.py project_slug). Both readers of `transcripts` expand the leading ~.
transcript = "~/.claude/projects/%s/%s.jsonl" % (re.sub(r"[^A-Za-z0-9]", "-", worktree), session_id)
with session_write.locked(os.path.join(session_dir, ".session-state.lock")):
    with open(run_json) as f:
        run = json.load(f)
    run["session_id"] = session_id
    transcripts = run.get("transcripts") or []
    if transcript not in transcripts:
        transcripts.append(transcript)
    run["transcripts"] = transcripts
    session_write.write_json_atomic(run_json, run)
PY
}

# run.json.project is what every accounting record of the Robowright Session is summed under. Set
# once, when null, under the same lock pin_session takes.
#   write_project <session dir> <project>
write_project() {
    python3 - "$HERE" "$1" "$2" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import session_write
session_dir, project = sys.argv[2], sys.argv[3]
run_json = os.path.join(session_dir, "run.json")
with session_write.locked(os.path.join(session_dir, ".session-state.lock")):
    with open(run_json) as f:
        run = json.load(f)
    if run.get("project") is not None:
        sys.exit(0)
    run["project"] = project
    session_write.write_json_atomic(run_json, run)
PY
}

# The accounting root as run-cost.py resolves it, minus its flag: $ROBOWRIGHT_ACCOUNTING_ROOT, else
# launch.json's accounting_root, else accounting/ beside the sessions root.
accounting_root() {
    local root="${ROBOWRIGHT_ACCOUNTING_ROOT:-}" sessions="${ROBOWRIGHT_SESSIONS_ROOT:-$SESSIONS_ROOT}"
    [ -n "$root" ] || root="$(jq -r '.accounting_root // empty' "$LAUNCH_CONFIG" 2>/dev/null || true)"
    case "$root" in "~/"*) root="$HOME/${root#"~/"}" ;; esac
    case "$sessions" in "~/"*) sessions="$HOME/${sessions#"~/"}" ;; esac
    # run-cost.py puts the default beside the sessions root's real directory.
    [ ! -d "$sessions" ] || sessions="$(cd "$sessions" && pwd -P)"
    [ -n "$root" ] || root="$(dirname "${sessions%/}")/accounting"
    printf '%s\n' "$root"
}

# One launches.jsonl line for a session this script started: what a record of that session reads
# for its unit and session dir when its own marker cannot say. Best effort; never fails a launch.
#   append_launch_index <sessionId> <role> <project or ""> <unit> <session dir or "">
append_launch_index() {
    local root at
    root="$(accounting_root)"
    at="$(date '+%Y-%m-%dT%H:%M:%S%z' | sed 's/\(..\)$/:\1/')"
    { mkdir -p "$root" && jq -cn --arg sid "$1" --arg role "$2" --arg project "$3" --arg unit "$4" --arg dir "$5" \
        --arg model "$MODEL" --arg at "$at" \
        '{session_id: $sid, role: $role, project: (if $project == "" then null else $project end), unit: $unit,
          session_dir: (if $dir == "" then null else $dir end), model: $model, at: $at}' \
        | python3 "$SESSION_WRITE" append "$root/launches.jsonl"; } 2>/dev/null \
        || echo "note: could not append to $root/launches.jsonl; the launch went ahead" >&2
}

# The eight-character id on claude --bg's "backgrounded" line, else the first such id in its output.
#   background_id_of <claude output>
background_id_of() {
    local id
    id="$(printf '%s\n' "$1" | sed -n 's/^backgrounded · \([0-9a-f]\{8\}\).*/\1/p' | head -1)"
    [ -n "$id" ] || id="$(printf '%s\n' "$1" | grep -Eo '[0-9a-f]{8}' | head -1 || true)"
    printf '%s\n' "$id"
}

background_id_line() {
    printf -- '- background id: %s (claude attach %s · claude logs %s)' "$1" "$1" "$1"
}

# ---------------------------------------------------------------------------------------------
# launch.json — the facts that differ per install, beside the machine profile. Read as data with
# jq, never sourced: this script runs outside the sandbox. It ships no defaults but `launch`'s, so an install
# that has not written the file is refused rather than run on another install's paths. The
# regexes are matched by bash, so they are POSIX ERE as `[[ =~ ]]` reads them, not PCRE.
# ---------------------------------------------------------------------------------------------
[ -f "$LAUNCH_CONFIG" ] || fail "$LAUNCH_CONFIG is missing — every install writes its own (schema 1; see the machine profile beside it)"
CONFIG_PROBLEM="$(jq -r '
    def bad(k; ok): if ok then empty else k end;
    def isa(path; t): (getpath(path) | type) == t;
    # An empty string is what a half-written file leaves, and an empty value is the dangerous
    # one: an empty sessions root turns the under-root fence into a test every path passes.
    def filled(path): isa(path; "string") and (getpath(path) | length) > 0;
    [ bad("schema"; isa(["schema"]; "number"))
    , bad("sessions_root"; filled(["sessions_root"]))
    , bad("review_guide_dir"; filled(["review_guide_dir"]))
    , bad("report_scope"; filled(["report_scope"]))
    , bad("unit"; isa(["unit"]; "object"))
    , bad("unit.ticket_regex"; filled(["unit","ticket_regex"]) or isa(["unit","ticket_regex"]; "null"))
    , bad("unit.ticket_example"; filled(["unit","ticket_example"]) or isa(["unit","ticket_example"]; "null"))
    , bad("unit.slug_regex"; filled(["unit","slug_regex"]))
    , bad("unit.slug_example"; filled(["unit","slug_example"]))
    , bad("unit.group_regex"; filled(["unit","group_regex"]))
    ] | .[0] // empty' "$LAUNCH_CONFIG" 2>/dev/null)" || fail "$LAUNCH_CONFIG is not readable JSON"
[ -z "$CONFIG_PROBLEM" ] || fail "$LAUNCH_CONFIG: '$CONFIG_PROBLEM' is missing or is not the type schema 1 gives it"
SCHEMA="$(jq -r '.schema' "$LAUNCH_CONFIG")"
[ "$SCHEMA" = "1" ] || fail "$LAUNCH_CONFIG is schema $SCHEMA; this launcher reads schema 1"
SESSIONS_ROOT="$(jq -r '.sessions_root' "$LAUNCH_CONFIG")"
case "$SESSIONS_ROOT" in "~/"*) SESSIONS_ROOT="$HOME/${SESSIONS_ROOT#"~/"}" ;; esac
# Resolve it physically: Robowright Session dirs are resolved with `pwd -P` below, and a root under a
# symlink (macOS $TMPDIR is /var → /private/var) would never match the under-root test.
if [ -d "$SESSIONS_ROOT" ]; then SESSIONS_ROOT="$(cd "$SESSIONS_ROOT" && pwd -P)"; fi
# The project's guide dir only: a session's own reviews/ is a constant session-state.py requires.
REVIEW_GUIDE_DIR="$(jq -r '.review_guide_dir' "$LAUNCH_CONFIG")"
REPORT_SCOPE="$(jq -r '.report_scope' "$LAUNCH_CONFIG")"
case "$REPORT_SCOPE" in
    project-prefix|all-roots) ;;
    *) fail "$LAUNCH_CONFIG: 'report_scope' must be project-prefix or all-roots (got '$REPORT_SCOPE')" ;;
esac
# Optional, so schema 1 still holds: no key means paste. `=` marks a key that is present, so an
# empty value is refused rather than read as absent.
LAUNCH_SETTING="$(jq -r 'if has("launch") then "=" + (.launch | tostring) else "" end' "$LAUNCH_CONFIG")"
if [ -n "$LAUNCH_SETTING" ]; then
    LAUNCH_MODE="${LAUNCH_SETTING#=}"
    LAUNCH_SOURCE="launch.json"
else
    LAUNCH_MODE="paste"
    LAUNCH_SOURCE="default: launch.json names no launch key"
fi
case "$LAUNCH_MODE" in
    paste|auto) ;;
    *) fail "$LAUNCH_CONFIG: 'launch' must be paste or auto (got '$LAUNCH_MODE')" ;;
esac
# Optional too; the scripts that write and read the accounting ledger resolve it, this only refuses a bad one.
jq -e '(has("accounting_root") | not) or ((.accounting_root | type) == "string" and (.accounting_root | length) > 0)' "$LAUNCH_CONFIG" >/dev/null \
    || fail "$LAUNCH_CONFIG: 'accounting_root' is optional, and when present must be a non-empty path"
TICKET_REGEX="$(jq -r '.unit.ticket_regex // empty' "$LAUNCH_CONFIG")"
TICKET_EXAMPLE="$(jq -r '.unit.ticket_example // empty' "$LAUNCH_CONFIG")"
SLUG_REGEX="$(jq -r '.unit.slug_regex' "$LAUNCH_CONFIG")"
SLUG_EXAMPLE="$(jq -r '.unit.slug_example' "$LAUNCH_CONFIG")"
GROUP_REGEX="$(jq -r '.unit.group_regex' "$LAUNCH_CONFIG")"
[ -z "$TICKET" ] || [ -n "$TICKET_REGEX" ] || fail "--ticket is not a flag this install takes; $LAUNCH_CONFIG names no unit.ticket_regex"

# ---------------------------------------------------------------------------------------------
# The run profile — one field in run.json (or --profile), expanded here and nowhere else in code.
# The prose copy of this table is the BRIEF.md Run parameters `profile` row; keep them in step.
# Kinds split two ways: the bounded, pattern-following ones (tests, docs, refactor) and everything
# else, which is where judgment is bought.
# ---------------------------------------------------------------------------------------------
check_profile() {
    case "$1" in
        showcase|standard|economy) ;;
        *) fail "profile (from $2) must be showcase, standard, or economy (got '$1')" ;;
    esac
}
kind_group() { case "$1" in tests|docs|refactor) echo "lean" ;; *) echo "other" ;; esac; }
# "<model> <effort>" for a profile and a group: lean | other for a Worker, doc for a document-only role.
profile_expand() {
    case "$1:$2" in
        showcase:lean)  echo "opus medium" ;;
        showcase:other) echo "opus high" ;;
        showcase:doc)   echo "fable high" ;;
        showcase:explainer) echo "opus high" ;;
        standard:lean)  echo "sonnet medium" ;;
        standard:other) echo "opus medium" ;;
        standard:doc)   echo "fable medium" ;;
        standard:explainer) echo "opus medium" ;;
        economy:lean)   echo "sonnet low" ;;
        economy:other)  echo "opus medium" ;;
        economy:doc)    echo "opus medium" ;;
        economy:explainer) echo "opus medium" ;;
    esac
}
check_effort() {
    case "$1" in
        low|medium|high|xhigh|max) ;;
        *) fail "effort (from $2) must be low, medium, high, xhigh, or max (got '$1')" ;;
    esac
}
# One model shape and one alias map for this launcher and role-start.py. A model reaches --model,
# the --settings JSON and the subagent env, and run.json and robowright.json are session-writable,
# so every model value read is held to the form before anything starts.
MODELS="$HERE/../models.json"
MODEL_FORM="$(jq -r '.form' "$MODELS" 2>/dev/null)" || fail "$MODELS is not readable JSON"
check_model() {
    [[ "$1" =~ $MODEL_FORM ]] || fail "model (from $2) must be opus, sonnet, haiku, fable, or a full claude-* model id of lowercase letters, digits, '.' and '-' (got '$1')"
}
# A background session carries --settings over a supervisor wake and does not carry --effort, so
# the level rides on both. The per-model key is set too because it outranks the bare one, and
# A machine's settings.json may pin these ids; a model id this map does not know is used as written.
# session_settings <effort> <model> <stop_cap> <compact_pct> <subagent_model> <grants>: the --settings JSON.
# The `env` block is the only channel that reaches a daemon-claimed session (see the header). <grants> is
# role_grants.py's fragment: what the session may write, and the git files it may not, carried over a wake the same way.
session_settings() {
    jq -cn --argjson ids "$(jq -c '.ids' "$MODELS")" --arg effort "$1" --arg model "$2" \
        --arg cap "$3" --arg pct "$4" --arg subagent "$5" --argjson grants "$6" \
        '{effortLevel: $effort, modelSettings: {($ids[$model] // $model): {effortLevel: $effort}},
          env: {CLAUDE_CODE_STOP_HOOK_BLOCK_CAP: $cap, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE: $pct, CLAUDE_CODE_SUBAGENT_MODEL: $subagent}}
         + $grants'
}
# What a role may write, from launch.json alone (role_grants.py); refused by name when a grant would reach a repository,
# the home directory or this clone. Left in GRANTS, and printed in the plan from it.
GRANTS_TOOL="$HERE/role_grants.py"
#   role_grants worker <session dir> <worktree> | role_grants document <project dir> | role_grants direct … grants
role_grants() { GRANTS="$(python3 "$GRANTS_TOOL" "$@")" || fail "no write grant for this session (above); nothing started"; }
grants_plan() {
    jq -r '"writes:    " + (.permissions.additionalDirectories | join(" ")), "denied:    " + (.sandbox.filesystem.denyWrite | join(" "))' <<<"$GRANTS"
}
# A session id reaches `claude --resume`, whose value is optional, so only a UUID is passed.
SESSION_UUID_FORM='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
# session-state.py's now_iso(): seconds, and an offset or Z.
ISO_TIME_FORM='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$'

# The launcher's own environment must not reach the session or a daemon this call starts.
SCRUB_ENV=(env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_STOP_HOOK_BLOCK_CAP -u CLAUDE_AUTOCOMPACT_PCT_OVERRIDE -u CLAUDE_CODE_SUBAGENT_MODEL)

# session-state.py owns what run.json's state means and which operation is legal from it
# (robowright skill, STATES.md). This script asks; it never re-derives.
STATE_TOOL="$HERE/session-state.py"
STATE_MACHINE="$HERE/../state-machine.json"
COST_TOOL="$HERE/../../worker/scripts/run-cost.py"
session_state() {
    local status_json
    status_json="$(python3 "$STATE_TOOL" "$1" status --json)" || fail "session-state.py could not read $1 (above)"
    printf '%s' "$status_json" | jq -r '.state // "invalid"'
}
# $3 is appended to the refusal: the one fix this caller knows for its state, or "".
check_op() { python3 "$STATE_TOOL" "$1" check-op "$2" || fail "session-state.py check-op $2 said no (above); python3 $STATE_TOOL $1 status shows the state and what is legal from it$3"; }

# A missing worktree the launcher will not make is refused with the command that recreates it, filled from run.json;
# <base> is the reader's. The branch exists once preflight has passed, and `-b` refuses an existing branch, so
# only a briefed session gets `-b`. A finished session's worktree is torn down on purpose, so it
# gets no command.
fail_worktree_missing() {
    local phase branch worktree
    # The hint's plain `worktree add` reads the base's attributes: on a git without --attr-source no line is safe to hand
    # over, since a checkout there runs, as the Owner, the filters a session names.
    python3 "$OWNER_GIT" attr-source || fail "worktree $2 does not exist, and this git cannot make it without running the filters its base names (above); nothing started"
    phase="$(jq -r '.phase // "preflight"' "$1/run.json")"
    branch="$(jq -r '.units[0]?.branch? // empty' "$1/run.json")"
    # The hint is a command the reader pastes.
    if [ -n "$branch" ]; then
        git check-ref-format --branch "$branch" >/dev/null 2>&1 || fail "worktree $2 does not exist, and run.json units[0].branch is not a branch name git accepts (got '$branch')"
        branch="$(printf '%q' "$branch")"
    fi
    worktree="$(printf '%q' "$2")"
    case "$phase" in
        done|parked)
            fail "worktree $2 does not exist
run.json phase is $phase: the session is finished, so its worktree is not recreated" ;;
        preflight)
            fail "worktree $2 does not exist
create it per the project hook → Worktree, e.g.: git worktree add -b ${branch:-<branch>} $worktree <base>" ;;
        *)
            fail "worktree $2 does not exist
create it per the project hook → Worktree, e.g.: git worktree add $worktree ${branch:-<branch>}" ;;
    esac
}

# A session's sandbox cannot write a repository's git directory, so a missing worktree is made here, on the Owner's
# side: only at the hook's <repo>/.worktrees/<session dir name> on robowright/<session dir name>, held to those
# shapes by role_grants.py before git runs, and only once the state machine allows this launch. A dry run prints the
# line and stops, since every later check reads the worktree.
make_worktree() {
    local op line
    line="$(python3 "$GRANTS_TOOL" worktree "$1" plan)" || fail_worktree_missing "$1" "$2"
    if [ "$RESUME" = "true" ]; then op=resume; elif [ "$ROTATE" = "true" ]; then op=rotate; else op=launch; fi
    check_op "$1" "$op" ""
    if [ "$DRY_RUN" = "true" ]; then
        printf '%s\n' "$line" | show
        echo "dry run — nothing started; the rest of the plan is checked once the worktree exists"
        exit 0
    fi
    python3 "$GRANTS_TOOL" worktree "$1" make || fail_worktree_missing "$1" "$2"
}

# The unit of work a Robowright Session is for: run.json's `ticket`, which is what the Planner's
# template writes. Where the install names a ticket shape, a brief carrying none is refused —
# the guide path and the session name would otherwise be built from a directory name.
# A session writes its own run.json, so the ticket is held to one path segment before a path or
# a prompt is built from it.
TICKET_FORM='^[A-Za-z0-9][A-Za-z0-9._-]*$'
read_unit_id() {
    UNIT_ID="$(jq -r '.ticket // empty' "$1/run.json")"
    [ -n "$UNIT_ID" ] || [ -z "$TICKET_REGEX" ] || fail "$1/run.json has no ticket"
    if [ -n "$UNIT_ID" ]; then
        [[ "$UNIT_ID" =~ $TICKET_FORM ]] || fail "$1/run.json: 'ticket' must be one path segment of letters, digits, '.', '_' and '-' (got '$UNIT_ID')"
        [ -z "$TICKET_REGEX" ] || [[ "$UNIT_ID" =~ $TICKET_REGEX ]] || fail "$1/run.json: 'ticket' must look like $TICKET_EXAMPLE (got '$UNIT_ID')"
    fi
    if [ -z "$UNIT_ID" ]; then
        # Any session can create a directory beside its own, and this name reaches a prompt.
        UNIT_ID="$(basename "$1")"
        in_unit_form "$UNIT_ID" || fail "$1/run.json has no ticket, and the directory name '$UNIT_ID' is not a unit name on this install (unit.slug_regex in $LAUNCH_CONFIG)"
    fi
}

# run.json's stop code, left in STOP_CODE; it reaches a Planner prompt, so it is one of the state
# machine's names or absent.
read_stop_code() {
    STOP_CODE="$(jq -r '.stop_reason.code // empty' "$1/run.json")"
    [ -n "$STOP_CODE" ] || return 0
    jq -e --arg c "$STOP_CODE" '.stop_codes | has($c)' "$STATE_MACHINE" >/dev/null \
        || fail "$1/run.json: 'stop_reason.code' must be one of the stop_codes in $STATE_MACHINE (got '$STOP_CODE')"
}

# Whether a directory name is a unit name on this install: one safe segment whatever the install's
# own patterns allow, then a slug, or <ticket>-<slug> split at whichever hyphen makes both halves match.
in_unit_form() {
    local ticket rest="$1"
    [[ "$1" =~ $TICKET_FORM ]] || return 1
    if [ -z "$TICKET_REGEX" ]; then
        [[ "$1" =~ $SLUG_REGEX ]]
        return
    fi
    while [[ "$rest" == *-* ]]; do
        rest="${rest#*-}"
        ticket="${1%"-$rest"}"
        if [[ "$ticket" =~ $TICKET_REGEX ]] && [[ "$rest" =~ $SLUG_REGEX ]]; then
            return 0
        fi
    done
    return 1
}

# launch.json's capture on a directory name, left in MATCHED_GROUP; non-zero when the name is not
# in any group. A regex that matches but captures nothing would read an unset BASH_REMATCH[1]
# under `set -u`, so it is refused by name like every other launch.json error — except with
# --soft, from a caller whose session is already running, where it is non-zero like a miss.
#   match_group <name> [--soft]
MATCHED_GROUP=""
match_group() {
    MATCHED_GROUP=""
    [[ "$1" =~ $GROUP_REGEX ]] || return 1
    if [ "${#BASH_REMATCH[@]}" -le 1 ]; then
        [ "${2:-}" != "--soft" ] || return 1
        fail "$LAUNCH_CONFIG: 'unit.group_regex' matched '$1' and captured nothing — one capture group names the part a brief inherits from"
    fi
    MATCHED_GROUP="${BASH_REMATCH[1]}"
}

# The newest INTAKE.md under the sessions root whose group is $1, or empty. The group is
# launch.json's capture on a directory name, so a longer name that merely starts with the same
# letters is a different group.
latest_intake() {
    local intake candidate
    while IFS= read -r intake; do
        [ -n "$intake" ] || continue
        candidate="$(basename "$(dirname "$intake")")"
        # Any session can make a directory here, and its name reaches the Planner's prompt.
        in_unit_form "$candidate" || continue
        match_group "$candidate" || continue
        [ "$MATCHED_GROUP" = "$1" ] || continue
        printf '%s\n' "$intake"
        return 0
    done <<EOF
$(ls -t "$SESSIONS_ROOT"/*/INTAKE.md 2>/dev/null || true)
EOF
}

case "$STOP_CAP" in ''|*[!0-9]*) fail "--stop-cap must be a whole number" ;; esac
check_model "$SUBAGENT_MODEL" "--subagent-model"

# ---------------------------------------------------------------------------------------------
# --direct: a direct build (the planner handbook → Size `S` or below), which has no run.json and no Robowright
# Session. Self-contained; exits before the document-only and Worker paths. role_grants.py makes its worktree on the
# Worker's hardened path, and the session starts in it under the fixed prompt below, naming only the briefing file.
# ---------------------------------------------------------------------------------------------
if [ "$DIRECT" != "true" ] && [ -n "$REPO$BASE$BRIEFING" ]; then
    fail "--repo, --base and --briefing go with --direct"
fi
if [ "$DIRECT" = "true" ]; then
    [ -z "$PLANNER_MODE" ] && [ -z "$EXPLAINER_MODE" ] || fail "--direct is exclusive with --planner and --explainer"
    [ -z "$SESSION_DIR" ] || fail "--direct has no Robowright Session, so it takes no --run-dir"
    [ "$RESUME" = "false" ] && [ "$ROTATE" = "false" ] && [ "$PIN" = "false" ] || fail "--direct does not combine with --resume, --rotate or --pin"
    [ "$NAME_GIVEN" = "false" ] || fail "--direct names its session build-<slug>; it takes no --name"
    [ -z "$TICKET" ] || fail "--direct takes the unit's whole name as --slug; it takes no --ticket"
    [ -n "$PROJECT" ] || fail "--direct needs --project <project dir>"
    [ -n "$SLUG" ] || fail "--direct needs --slug <unit>"
    [ -n "$REPO" ] || fail "--direct needs --repo <repository>"
    [ -n "$BASE" ] || fail "--direct needs --base <full commit id>"
    [ -n "$BRIEFING" ] || fail "--direct needs --briefing <project dir>/briefings/<file>.md"
    # The slug names the worktree's directory and its branch, the hook's <slug>: a unit name on this install.
    in_unit_form "$SLUG" || fail "--slug must be a unit name on this install, like $SLUG_EXAMPLE (unit.slug_regex in $LAUNCH_CONFIG; got '$SLUG')"
    PROJECT="$(spelled_path "$PROJECT")"
    REPO="$(spelled_path "$REPO")"
    BRIEFING="$(spelled_path "$BRIEFING")"
    # role_grants.py direct_place: a build started before U46 keeps its worktree at the old place until it is torn down.
    WORKTREE="$REPO/.worktrees/$SLUG"
    if [ ! -e "$WORKTREE" ] && [ ! -L "$WORKTREE" ] && { [ -e "$REPO/.claude/worktrees/$SLUG" ] || [ -L "$REPO/.claude/worktrees/$SLUG" ]; }; then
        WORKTREE="$REPO/.claude/worktrees/$SLUG"
    fi
    DIRECT_TOOL=(python3 "$GRANTS_TOOL" direct "$PROJECT" "$REPO" "$SLUG" "$BASE" "$BRIEFING")
    WORKTREE_LINE="$("${DIRECT_TOOL[@]}" plan)" || fail "--direct: no worktree for this build (above); nothing started"
    role_grants direct "$PROJECT" "$REPO" "$SLUG" "$BASE" "$BRIEFING" grants
    PROFILE="${PROFILE:-standard}"
    check_profile "$PROFILE" "flag"
    # A direct build's kind is the plan's, not on file here: the judgment group, never the cheap one.
    read -r PROFILE_MODEL PROFILE_EFFORT <<<"$(profile_expand "$PROFILE" other)"
    MODEL_SOURCE="flag"; [ -n "$MODEL" ] || { MODEL="$PROFILE_MODEL"; MODEL_SOURCE="profile $PROFILE"; }
    check_model "$MODEL" "$MODEL_SOURCE"
    EFFORT_SOURCE="flag"; [ -n "$EFFORT" ] || { EFFORT="$PROFILE_EFFORT"; EFFORT_SOURCE="profile $PROFILE"; }
    check_effort "$EFFORT" "$EFFORT_SOURCE"
    COMPACT_PCT="${COMPACT_PCT:-85}"
    case "$COMPACT_PCT" in ''|*[!0-9]*) fail "--compact-pct must be a whole number of percent" ;; esac
    [ "$COMPACT_PCT" -ge 10 ] && [ "$COMPACT_PCT" -le 100 ] || fail "--compact-pct must be between 10 and 100"
    NAME="$(printf 'build-%s' "$SLUG" | tr '[:upper:]' '[:lower:]')"
    refuse_live_name "$NAME"
    [ ! -d "$WORKTREE" ] || refuse_live_in "$WORKTREE"
    LEDGER_TARGET="$PROJECT/DECISIONS.md"
    PROMPT="Build directly from the briefing at $BRIEFING: read it in full, and follow it."
    # Like a document role, a direct build starts with no MCP server; its briefing names none.
    MCP_FLAGS=(--strict-mcp-config --mcp-config '{"mcpServers":{}}')
    CMD=(claude --bg --model "$MODEL" "${MCP_FLAGS[@]}" --effort "$EFFORT" --settings "$(session_settings "$EFFORT" "$MODEL" "$STOP_CAP" "$COMPACT_PCT" "$SUBAGENT_MODEL" "$GRANTS")" --name "$NAME" "$PROMPT")
    LEDGER_VERB="one entry will be appended"
    [ "$DRY_RUN" != "true" ] || LEDGER_VERB="dry run: nothing appended"
    {
        echo "direct:    $SLUG — briefing $BRIEFING"
        echo "project:   $PROJECT"
        printf '%s\n' "$WORKTREE_LINE"
        echo "launch:    $LAUNCH_MODE ($LAUNCH_SOURCE)"
        echo "model:     $MODEL (from $MODEL_SOURCE)"
        echo "effort:    $EFFORT (from $EFFORT_SOURCE) — --effort for this process, --settings for the ones the supervisor wakes"
        echo "env:       via --settings: CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=$STOP_CAP, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=$COMPACT_PCT, CLAUDE_CODE_SUBAGENT_MODEL=$SUBAGENT_MODEL"
        echo "mcp:       ${MCP_FLAGS[*]}"
        grants_plan
        printf 'command:  '; printf ' %q' "${CMD[@]}"; printf '\n'
        echo "ledger:    $LEDGER_TARGET ($LEDGER_VERB)"
    } | show
    if [ "$DRY_RUN" = "true" ]; then
        echo "dry run — nothing started"
        exit 0
    fi
    if [ "$ASSUME_YES" != "true" ]; then
        printf 'Start it? [y/N] '
        read -r reply < /dev/tty
        case "$reply" in y|Y|yes) ;; *) echo "aborted"; exit 1 ;; esac
    fi
    check_writable "$LEDGER_TARGET"
    "${DIRECT_TOOL[@]}" make | show || fail "--direct: the worktree was not made (above); nothing started"
    # Checked again now it exists: the session starts only in the build's own worktree.
    "${DIRECT_TOOL[@]}" plan >/dev/null || fail "--direct: $WORKTREE is not the build's worktree after it was made (above); nothing started"
    # The body of a direct-build hand-off entry; $1 is the line saying why nothing started.
    direct_entry() {
        printf -- '- direct build (%s, %s effort %s) for %s\n' "$NAME" "$MODEL" "$EFFORT" "$SLUG"
        printf -- '- worktree: %s\n' "$WORKTREE"
        printf -- '- briefing: %s\n' "$BRIEFING"
        printf '%s\n' "$1"
    }
    start_or_handoff "$WORKTREE" "$LEDGER_TARGET" direct_entry
    echo "$OUT"
    DIRECT_BG_ID="$(background_id_of "$OUT")"
    DIRECT_SESSION_ID=""
    DIRECT_CWD=""
    # The registry entry is written as the session starts; give it a moment.
    for DIRECT_TRY in 1 2 3; do
        [ -z "$DIRECT_BG_ID" ] || DIRECT_SESSION_ID="$(registry_session_id "$DIRECT_BG_ID")"
        [ -z "$DIRECT_SESSION_ID" ] || DIRECT_CWD="$(registry_session_cwd "$DIRECT_SESSION_ID")"
        [ -z "$DIRECT_CWD" ] || break
        [ "$DIRECT_TRY" = 3 ] || sleep 1
    done
    DIRECT_CWD_REAL=""
    [ -z "$DIRECT_CWD" ] || DIRECT_CWD_REAL="$(cd "$DIRECT_CWD" 2>/dev/null && pwd -P || true)"
    # The registry is not the launcher's: only a UUID and the worktree itself reach the ledger.
    [[ "$DIRECT_SESSION_ID" =~ $SESSION_UUID_FORM ]] || DIRECT_SESSION_ID=""
    DIRECT_WHERE="not the worktree"; [ "$DIRECT_CWD_REAL" != "$WORKTREE" ] || DIRECT_WHERE="the worktree"
    [ -n "$DIRECT_CWD" ] || DIRECT_WHERE="none in the registry"
    printf '\n%s — direct build launched (%s, %s, %s) for %s via %s --direct; worktree %s; briefing %s; session %s, cwd %s\n' \
        "$(date '+%Y-%m-%d %H:%M')" "$NAME" "$MODEL effort $EFFORT" "${DIRECT_BG_ID:-no background id}" "$SLUG" "$LAUNCHER_NAME" \
        "$WORKTREE" "$BRIEFING" "${DIRECT_SESSION_ID:-not in the registry}" "$DIRECT_WHERE" | append_to "$LEDGER_TARGET"
    if [ -z "$DIRECT_CWD" ]; then
        fail "STARTED, NOT CONFIRMED: the registry in $CLAUDE_SESSIONS_ROOT shows no cwd for background id ${DIRECT_BG_ID:-(none printed)}, so nothing shows the build runs in its worktree $WORKTREE. Check claude agents --json, and stop it if its cwd is not the worktree"
    fi
    if [ "$DIRECT_CWD_REAL" != "$WORKTREE" ]; then
        fail "WRONG DIRECTORY: session ${DIRECT_SESSION_ID:-$DIRECT_BG_ID} runs in $DIRECT_CWD, not the worktree $WORKTREE, so it has no grant on its worktree. Stop it: claude stop $DIRECT_BG_ID"
    fi
    echo
    echo "watch:  claude attach $NAME     logs: claude logs $NAME"
    exit 0
fi

# ---------------------------------------------------------------------------------------------
# --planner <mode> / --explainer <mode>: a document-only session. Self-contained; exits before
# the Worker path.
# ---------------------------------------------------------------------------------------------
if [ -n "$PLANNER_MODE" ] && [ -n "$EXPLAINER_MODE" ]; then
    fail "--planner and --explainer are exclusive"
fi
if [ "$PIN" = "true" ] && { [ -n "$PLANNER_MODE" ] || [ -n "$EXPLAINER_MODE" ]; }; then
    fail "--pin records a Worker session; it is exclusive with --planner and --explainer"
fi
if [ -n "$PLANNER_MODE" ] || [ -n "$EXPLAINER_MODE" ]; then
    if [ -n "$PLANNER_MODE" ]; then ROLE_KEY="planner"; SIDE="${PLANNER_FLAG#--}"; else ROLE_KEY="explainer"; SIDE="${EXPLAINER_FLAG#--}"; fi
    [ "$RESUME" = "false" ] && [ "$ROTATE" = "false" ] || fail "--$SIDE does not combine with --resume or --rotate"
    case "$ROLE_KEY:${PLANNER_MODE}${EXPLAINER_MODE}" in
        planner:brief|planner:rebrief|planner:review|explainer:guide|explainer:report) ;;
        planner:*) fail "--planner must be brief, rebrief, or review (got '$PLANNER_MODE')" ;;
        *) fail "--explainer must be guide or report (got '$EXPLAINER_MODE')" ;;
    esac
    [ -n "$PROJECT" ] || fail "--$SIDE needs --project <dir>"
    # Checked as spelled before anything reads it, and never resolved: a role granted the projects root can swap a
    # folder in it for a link, so the session starts only in the directory the check looked at (start_or_handoff).
    PROJECT="$(spelled_path "$PROJECT")"
    role_grants document "$PROJECT"
    [ -d "$PROJECT" ] || fail "project dir does not exist"
    [ -f "$PROJECT/PROJECT.md" ] || fail "$PROJECT/PROJECT.md is missing — the $SIDE reads the plan from it"
    # There may be no run.json yet, so a document-only role takes its profile from the flag.
    PROFILE="${PROFILE:-standard}"
    check_profile "$PROFILE" "flag"
    DOC_GROUP="doc"; [ "$ROLE_KEY" != "explainer" ] || DOC_GROUP="explainer"
    read -r PROFILE_MODEL PROFILE_EFFORT <<<"$(profile_expand "$PROFILE" "$DOC_GROUP")"
    ROBOWRIGHT_MODEL=""
    if [ -e "$PROJECT/robowright.json" ] || [ -L "$PROJECT/robowright.json" ]; then
        # A role granted the projects root can make the file a link or a FIFO: session_write.py follows and waits on neither.
        PROJECT_SETTINGS_JSON="$(python3 "$SESSION_WRITE" read "$PROJECT/robowright.json")" \
            || fail "$PROJECT/robowright.json was not read (above): nothing started"
        ROBOWRIGHT_MODEL="$(printf '%s\n' "$PROJECT_SETTINGS_JSON" | jq -r --arg r "$ROLE_KEY" '.models[$r] // empty' 2>/dev/null || true)"
    fi
    [ -z "$ROBOWRIGHT_MODEL" ] || check_model "$ROBOWRIGHT_MODEL" "robowright.json models.$ROLE_KEY"
    if [ -n "$MODEL" ]; then
        MODEL_SOURCE="flag"
    elif [ -n "$ROBOWRIGHT_MODEL" ]; then
        MODEL="$ROBOWRIGHT_MODEL"
        MODEL_SOURCE="robowright.json"
    else
        MODEL="$PROFILE_MODEL"
        MODEL_SOURCE="profile $PROFILE"
    fi
    check_model "$MODEL" "$MODEL_SOURCE"
    if [ -n "$EFFORT" ]; then
        EFFORT_SOURCE="flag"
    else
        EFFORT="$PROFILE_EFFORT"
        EFFORT_SOURCE="profile $PROFILE"
    fi
    check_effort "$EFFORT" "$EFFORT_SOURCE"
    LATEST_INTAKE=""
    LEDGER_TARGET=""
    case "$ROLE_KEY:${PLANNER_MODE}${EXPLAINER_MODE}" in
        explainer:report)
            UNIT_ID="$(basename "$PROJECT")"
            SESSION_DIR="$PROJECT"
            LEDGER_TARGET="$PROJECT/DECISIONS.md"
            [ ! -f "$PROJECT/REPORT.md" ] || fail "$PROJECT/REPORT.md already exists — move it aside to write a new one"
            NAME="${NAME:-$(printf '%s-%s' "$SIDE" "$UNIT_ID" | tr '[:upper:]' '[:lower:]')}"
            REPORT_SESSIONS="$SESSIONS_ROOT"
            [ "$REPORT_SCOPE" != "project-prefix" ] || REPORT_SESSIONS="$SESSIONS_ROOT/$UNIT_ID-*"
            PROMPT="/explainer report $PROJECT: write REPORT.md in this folder from the project record (PROJECT.md, DECISIONS.md, this project's Robowright Sessions' INTAKE.md, PLAN-REVIEW.md and smoke/MANUAL-PASS.md under $REPORT_SESSIONS, the owner briefs under $REVIEW_GUIDE_DIR/), using one Reviewer for the as-built architecture and never the diff. Run doc-gate on it, then the machine profile's explainer.publish duty, and end. Do not push, post, launch, or edit anything else."
            ACTION="launch report Explainer"
            ;;
        explainer:guide)
            [ -n "$SESSION_DIR" ] || fail "--$SIDE guide needs --run-dir <dir>"
            SESSION_DIR="$(cd "$SESSION_DIR" 2>/dev/null && pwd -P)" || fail "Robowright Session dir does not exist"
            case "$SESSION_DIR" in
                "$SESSIONS_ROOT"/*) ;;
                *) fail "Robowright Session dir must be under $SESSIONS_ROOT (sessions_root in $LAUNCH_CONFIG)" ;;
            esac
            [ -f "$SESSION_DIR/run.json" ] || fail "$SESSION_DIR/run.json is missing"
            read_unit_id "$SESSION_DIR"
            PHASE="$(jq -r '.phase // "preflight"' "$SESSION_DIR/run.json")"
            [ "$PHASE" = "done" ] || fail "run.json phase is '$PHASE' — the guide is written for a finished, published Robowright Session"
            [ -f "$SESSION_DIR/INTAKE.md" ] || fail "$SESSION_DIR/INTAKE.md is missing — intake first (reviewer-intake), then the guide"
            GUIDE="$PROJECT/$REVIEW_GUIDE_DIR/$UNIT_ID-owner-brief.md"
            [ ! -f "$GUIDE" ] || fail "$GUIDE already exists — move it aside to write a new one"
            LEDGER_TARGET="$SESSION_DIR/LEDGER.md"
            NAME="${NAME:-$(printf '%s-%s' "$SIDE" "$UNIT_ID" | tr '[:upper:]' '[:lower:]')}"
            PROMPT="/explainer guide $PROJECT $SESSION_DIR: write the owner brief $GUIDE from the Robowright Session record (BRIEF.md, INTAKE.md, reviews/, PLAN-REVIEW.md if present, the Decided (Lead) and (Planner) ledger entries, HANDBACK.md and the change descriptions under $SESSION_DIR/prs/), using a Reviewer only where a section needs the code and never the diff. Spot-check items cite the review that earned them. Count its words against the cap, run doc-gate on it and end. Do not push, post, launch, or edit anything else."
            ACTION="launch guide Explainer"
            ;;
        planner:brief)
            [ -n "$SLUG" ] || fail "--planner brief needs --slug <slug>"
            case "$SLUG" in
                *[!a-z0-9-]*) fail "--slug must be lowercase letters, digits, and hyphens (got '$SLUG')" ;;
            esac
            [[ "$SLUG" =~ $SLUG_REGEX ]] || fail "--slug must look like $SLUG_EXAMPLE (got '$SLUG')"
            UNIT_ID="$SLUG"
            SESSION_DIR="$SESSIONS_ROOT/$SLUG"
            if [ -n "$TICKET_REGEX" ]; then
                [ -n "$TICKET" ] || fail "--planner brief needs --ticket <key>, e.g. $TICKET_EXAMPLE"
                [[ "$TICKET" =~ $TICKET_FORM ]] || fail "--ticket must be one path segment of letters, digits, '.', '_' and '-' (got '$TICKET')"
                [[ "$TICKET" =~ $TICKET_REGEX ]] || fail "--ticket must look like $TICKET_EXAMPLE (got '$TICKET')"
                UNIT_ID="$TICKET"
                SESSION_DIR="$SESSIONS_ROOT/$TICKET-$SLUG"
            fi
            LEDGER_TARGET="$SESSION_DIR/LEDGER.md"
            [ ! -f "$SESSION_DIR/BRIEF.md" ] || fail "$SESSION_DIR/BRIEF.md already exists — this brief is written; launch it with --run-dir"
            NAME="${NAME:-$(printf '%s-%s' "$SIDE" "$UNIT_ID" | tr '[:upper:]' '[:lower:]')}"
            # The sessions root is shared across projects; a brief inherits from its own group only.
            match_group "$(basename "$SESSION_DIR")" || true
            [ -z "$MATCHED_GROUP" ] || LATEST_INTAKE="$(latest_intake "$MATCHED_GROUP")"
            PROMPT="/planner brief $UNIT_ID: write BRIEF.md and run.json into $SESSION_DIR, or the direct-build briefing, from the corrected plan in this folder (PROJECT.md, DECISIONS.md, robowright.json, the unit's exploration doc)${LATEST_INTAKE:+; the newest intake is $LATEST_INTAKE, read its section 6 for what this brief inherits}. Run doc-gate on what you wrote, append the DECISIONS.md entry, print the $LAUNCHER_NAME --dry-run line for the Lead, and end. Do not launch, watch, or edit PROJECT.md beyond the Task Breakdown row."
            ACTION="launch brief-only Planner"
            ;;
        planner:rebrief|planner:review)
            [ -n "$SESSION_DIR" ] || fail "--$SIDE $PLANNER_MODE needs --run-dir <dir>"
            SESSION_DIR="$(cd "$SESSION_DIR" 2>/dev/null && pwd -P)" || fail "Robowright Session dir does not exist"
            case "$SESSION_DIR" in
                "$SESSIONS_ROOT"/*) ;;
                *) fail "Robowright Session dir must be under $SESSIONS_ROOT (sessions_root in $LAUNCH_CONFIG)" ;;
            esac
            [ -f "$SESSION_DIR/BRIEF.md" ] || fail "$SESSION_DIR/BRIEF.md is missing"
            [ -f "$SESSION_DIR/run.json" ] || fail "$SESSION_DIR/run.json is missing"
            read_unit_id "$SESSION_DIR"
            LEDGER_TARGET="$SESSION_DIR/LEDGER.md"
            PHASE="$(jq -r '.phase // "preflight"' "$SESSION_DIR/run.json")"
            read_stop_code "$SESSION_DIR"
            REBRIEF_COUNT="$(jq -r '(.rebriefs // []) | length' "$SESSION_DIR/run.json")"
            if [ "$PLANNER_MODE" = "rebrief" ]; then
                SESSION_STATE="$(session_state "$SESSION_DIR")"
                [ "$SESSION_STATE" != "awaiting-rotation" ] || fail "this Robowright Session is awaiting-rotation — a rebrief was already applied; launch it with --rotate, do not rebrief again"
                [ "$SESSION_STATE" = "stopped" ] || fail "this Robowright Session is $SESSION_STATE — a rebrief answers a stopped one; a running one rotates or is nudged"
                [ ! -e "$SESSION_DIR/STOP" ] || fail "$SESSION_DIR/STOP exists — the rebriefed Robowright Session could not rotate past it; delete it first if that is intended"
                N=$((REBRIEF_COUNT + 1))
                NAME="${NAME:-$(printf '%s-%s-r%s' "$SIDE" "$UNIT_ID" "$N" | tr '[:upper:]' '[:lower:]')}"
                PROMPT="/planner rebrief $SESSION_DIR: this Robowright Session has stopped again (stop_reason $STOP_CODE; rebrief number $N). Read the plan in this folder (PROJECT.md, DECISIONS.md, robowright.json, the unit's exploration doc) and the session's record through a Reviewer, never the diff. Rewrite $SESSION_DIR/BRIEF.md in place per the planner skill's Rebrief session section (old brief to BRIEF.r$N.md), write $SESSION_DIR/REBRIEF.md with a confident or owner verdict, then apply the rebrief with python3 $STATE_TOOL $SESSION_DIR rebrief --verdict <confident|owner> --why <one line> (the only writer of rebriefs, stop_reason and rotate; never edit them). Run doc-gate on the brief, append the DECISIONS.md entry, print the $LAUNCHER_NAME --run-dir $SESSION_DIR --rotate --dry-run line for the Lead, and end. Do not launch, watch, or edit the worktree."
                ACTION="launch rebrief Planner (rebrief $N, after stop: $STOP_CODE)"
            else
                [ "$PHASE" = "done" ] || fail "run.json phase is '$PHASE' — the review pass reads a finished Robowright Session"
                [ -f "$SESSION_DIR/INTAKE.md" ] || fail "$SESSION_DIR/INTAKE.md is missing — intake first (reviewer-intake), then the review"
                [ ! -f "$SESSION_DIR/PLAN-REVIEW.md" ] || fail "$SESSION_DIR/PLAN-REVIEW.md already exists — there is never a second review pass"
                NAME="${NAME:-$(printf '%s-%s-review' "$SIDE" "$UNIT_ID" | tr '[:upper:]' '[:lower:]')}"
                PROMPT="/planner review $PROJECT $SESSION_DIR: read PROJECT.md, DECISIONS.md, $SESSION_DIR/INTAKE.md, $SESSION_DIR/reviews/end-of-stack.md, $SESSION_DIR/HANDBACK.md and the change descriptions under $SESSION_DIR/prs/, never the diff; use a Reviewer for any question that needs the code. Write $SESSION_DIR/PLAN-REVIEW.md with one verdict (ship, polish, or rebrief) per the planner skill's Review session section, append the DECISIONS.md entry, and end. Do not launch, watch, or edit the worktree."
                ACTION="launch review Planner"
            fi
            ;;
    esac
    refuse_live_name "$NAME"
    # A document-only role reads the plan and writes markdown, so it gets no MCP server at all:
    # one it never calls still costs its tool roster and its per-server instruction block.
    MCP_FLAGS=(--strict-mcp-config --mcp-config '{"mcpServers":{}}')
    # A document role reads whole plans and intakes; it gets the full window (100 is above the
    # default percentage, so the override is ignored) and the same stop cap and subagent default.
    EFFORT_FLAGS=(--effort "$EFFORT" --settings "$(session_settings "$EFFORT" "$MODEL" "$STOP_CAP" 100 "$SUBAGENT_MODEL" "$GRANTS")")
    CMD=(claude --bg --model "$MODEL" "${MCP_FLAGS[@]}" "${EFFORT_FLAGS[@]}" --name "$NAME" "$PROMPT")

    LEDGER_VERB="one entry will be appended"
    [ "$DRY_RUN" != "true" ] || LEDGER_VERB="dry run: nothing appended"
    {
        printf '%-11s%s — %s → %s\n' "$SIDE:" "${PLANNER_MODE}${EXPLAINER_MODE}" "$UNIT_ID" "$SESSION_DIR"
        echo "project:   $PROJECT"
        echo "action:    $ACTION"
        echo "launch:    $LAUNCH_MODE ($LAUNCH_SOURCE)"
        echo "model:     $MODEL (from $MODEL_SOURCE)"
        echo "effort:    $EFFORT (from $EFFORT_SOURCE) — --effort for this process, --settings for the ones the supervisor wakes"
        echo "env:       via --settings: CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=$STOP_CAP, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=100 (full window), CLAUDE_CODE_SUBAGENT_MODEL=$SUBAGENT_MODEL"
        [ "$PLANNER_MODE" != "brief" ] || echo "intake:    ${LATEST_INTAKE:-none found under $SESSIONS_ROOT}"
        [ "$EXPLAINER_MODE" != "guide" ] || echo "guide:     $GUIDE"
        echo "mcp:       ${MCP_FLAGS[*]}"
        grants_plan
        printf 'command:  '; printf ' %q' "${CMD[@]}"; printf '\n'
        echo "ledger:    $LEDGER_TARGET ($LEDGER_VERB)"
    } | show
    if [ "$DRY_RUN" = "true" ]; then
        echo "dry run — nothing started"
        exit 0
    fi
    if [ "$ASSUME_YES" != "true" ]; then
        printf 'Start it? [y/N] '
        read -r reply < /dev/tty
        case "$reply" in y|Y|yes) ;; *) echo "aborted"; exit 1 ;; esac
    fi
    mkdir -p "$SESSION_DIR"
    [ "$EXPLAINER_MODE" != "guide" ] || mkdir -p "$PROJECT/$REVIEW_GUIDE_DIR"
    check_writable "$LEDGER_TARGET"
    # The body of a document-only hand-off entry; $1 is the line saying why nothing started.
    document_entry() {
        printf -- '- %s %s (%s, %s effort %s) for %s\n' "$SIDE" "${PLANNER_MODE}${EXPLAINER_MODE}" "$NAME" "$MODEL" "$EFFORT" "$UNIT_ID"
        printf '%s\n' "$1"
    }
    # Written once the shell is in the project it checked; the path through the projects root may lead elsewhere by then.
    case "$LEDGER_TARGET" in "$PROJECT"/*) LEDGER_TARGET="./${LEDGER_TARGET#"$PROJECT"/}" ;; esac
    start_or_handoff "$PROJECT" "$LEDGER_TARGET" document_entry
    echo "$OUT"
    DOC_BG_ID="$(background_id_of "$OUT")"
    DOC_SESSION_ID=""
    [ -z "$DOC_BG_ID" ] || DOC_SESSION_ID="$(registry_session_id "$DOC_BG_ID")"
    if [ -n "$DOC_SESSION_ID" ]; then
        # The same project name the Worker records of this unit carry; a report's unit is the folder itself.
        DOC_INDEX_PROJECT="$(basename "$PROJECT")"
        if match_group "$UNIT_ID" --soft; then DOC_INDEX_PROJECT="$MATCHED_GROUP"; fi
        DOC_INDEX_DIR="$SESSION_DIR"
        [ "$SESSION_DIR" != "$PROJECT" ] || DOC_INDEX_DIR=""
        append_launch_index "$DOC_SESSION_ID" "$ROLE_KEY" "$DOC_INDEX_PROJECT" "$UNIT_ID" "$DOC_INDEX_DIR"
    fi
    printf '\n%s — %s launched (%s, %s, %s) for %s via %s --%s %s; project %s%s\n' \
        "$(date '+%Y-%m-%d %H:%M')" "$SIDE" "${PLANNER_MODE}${EXPLAINER_MODE}" "$NAME" "$MODEL effort $EFFORT" "$UNIT_ID" "$LAUNCHER_NAME" "$SIDE" "${PLANNER_MODE}${EXPLAINER_MODE}" "$PROJECT" \
        "${LATEST_INTAKE:+; inherits $LATEST_INTAKE}" | append_to "$LEDGER_TARGET"
    echo
    echo "watch:  claude attach $NAME     logs: claude logs $NAME"
    case "${PLANNER_MODE}${EXPLAINER_MODE}" in
        guide)   echo "then:   read $GUIDE before the first read-through; hand it to the Owner with the change descriptions" ;;
        report)  echo "then:   read $PROJECT/REPORT.md; anything another person reads is the Owner's call — the machine profile's explainer.publish says what that takes" ;;
        brief)   echo "then:   $LAUNCHER_NAME --run-dir $SESSION_DIR --dry-run   (once BRIEF.md and run.json exist), or the --direct line the Planner printed for the direct-build briefing" ;;
        rebrief) echo "then:   read $SESSION_DIR/REBRIEF.md; on confident: $LAUNCHER_NAME --run-dir $SESSION_DIR --rotate --dry-run" ;;
        review)  echo "then:   read $SESSION_DIR/PLAN-REVIEW.md; ship → Owner review; polish → launch the polish brief; rebrief → Owner" ;;
    esac
    exit 0
fi

[ -n "$SESSION_DIR" ] || fail "--run-dir is required"
SESSION_DIR="$(cd "$SESSION_DIR" 2>/dev/null && pwd -P)" || fail "Robowright Session dir does not exist"
case "$SESSION_DIR" in
    "$SESSIONS_ROOT"/*) ;;
    *) fail "Robowright Session dir must be under $SESSIONS_ROOT (sessions_root in $LAUNCH_CONFIG)" ;;
esac
[ -f "$SESSION_DIR/BRIEF.md" ] || fail "$SESSION_DIR/BRIEF.md is missing"
[ -f "$SESSION_DIR/run.json" ] || fail "$SESSION_DIR/run.json is missing — the Planner writes it from templates/run.json"

# ---------------------------------------------------------------------------------------------
# --pin <id>: the Owner pasted a hand-off and the session is running, so record it exactly as a
# launch would have. Starts nothing, so it runs none of the launch checks below: the pasted
# session is live in the worktree, may already have moved the phase on, and holds its locks.
# ---------------------------------------------------------------------------------------------
if [ "$PIN" = "true" ]; then
    [ "$RESUME" = "false" ] && [ "$ROTATE" = "false" ] || fail "--pin records a session that is already running; it is exclusive with --resume and --rotate"
    [[ "$PIN_ID" =~ ^[0-9a-f]{8}[0-9a-f-]*$ ]] || fail "--pin needs the background id (eight hex characters, from claude agents --json) or the full sessionId of the pasted session"
    PIN_SESSION_ID="$(registry_session_id "$PIN_ID")"
    [ -n "$PIN_SESSION_ID" ] || fail "no session in $CLAUDE_SESSIONS_ROOT has an id starting $PIN_ID; nothing pinned"
    WORKTREE="$(jq -r '.worktree // empty' "$SESSION_DIR/run.json")"
    [ -n "$WORKTREE" ] || fail "run.json has no worktree"
    WORKTREE_RESOLVED="$(cd "$WORKTREE" 2>/dev/null && pwd -P)" || fail_worktree_missing "$SESSION_DIR" "$WORKTREE"
    WORKTREE="$WORKTREE_RESOLVED"
    worktree_one_line "$WORKTREE"
    # The hand-off line starts in the worktree, so any other cwd is the wrong row pasted.
    PIN_CWD="$(registry_session_cwd "$PIN_SESSION_ID")"
    [ -n "$PIN_CWD" ] || fail "session $PIN_SESSION_ID has no cwd in $CLAUDE_SESSIONS_ROOT, so nothing shows it runs in the worktree $WORKTREE; nothing pinned"
    [ "$(cd "$PIN_CWD" 2>/dev/null && pwd -P)" = "$WORKTREE" ] || fail "session $PIN_SESSION_ID runs in $PIN_CWD, not the worktree $WORKTREE; nothing pinned"
    if [ "$DRY_RUN" = "true" ]; then
        echo "dry run — would pin $PIN_SESSION_ID into $SESSION_DIR/run.json; nothing written"
        exit 0
    fi
    check_writable "$SESSION_DIR/.session-state.lock" "$SESSION_DIR/LEDGER.md"
    pin_session "$SESSION_DIR" "$PIN_SESSION_ID" "$WORKTREE"
    # The project a started launch writes. The pasted session is already running, so a unit id a
    # launch would refuse leaves project null rather than refusing the pin.
    if (read_unit_id "$SESSION_DIR") >/dev/null 2>&1; then
        read_unit_id "$SESSION_DIR"
        if match_group "$UNIT_ID" --soft; then write_project "$SESSION_DIR" "$MATCHED_GROUP"; fi
    fi
    {
        printf '\n## %s — pinned after hand-off via %s\n' "$(date '+%Y-%m-%d %H:%M')" "$LAUNCHER_NAME"
        printf -- '- session id: %s\n' "$PIN_SESSION_ID"
        background_id_line "$(printf '%s' "$PIN_SESSION_ID" | cut -c1-8)"
        printf '\n- worktree: %s\n' "$WORKTREE"
    } | append_to "$SESSION_DIR/LEDGER.md"
    echo "pinned: $PIN_SESSION_ID → $SESSION_DIR/run.json (session_id, transcripts)"
    exit 0
fi
[ ! -e "$SESSION_DIR/STOP" ] || fail "$SESSION_DIR/STOP exists — the Worker would stop again immediately; delete it first if that is intended"

PHASE="$(jq -r '.phase // "preflight"' "$SESSION_DIR/run.json")"
read_stop_code "$SESSION_DIR"
WORKTREE="$(jq -r '.worktree // empty' "$SESSION_DIR/run.json")"
read_unit_id "$SESSION_DIR"
# An accepted Robowright Session's worktree is torn down, so this is refused before the worktree checks:
# "worktree does not exist" reads as a broken brief rather than as work that is already finished.
[ "$PHASE" != "done" ] || fail "run.json phase is done"
RUN_SESSION_ID="$(jq -r '.session_id // empty' "$SESSION_DIR/run.json")"
ROTATE_REQUESTED="$(jq -r '.rotate.requested_at // empty' "$SESSION_DIR/run.json")"
# It reaches the plan and a ledger heading.
[ -z "$ROTATE_REQUESTED" ] || [[ "$ROTATE_REQUESTED" =~ $ISO_TIME_FORM ]] \
    || fail "run.json 'rotate.requested_at' must be an ISO-8601 time"
# locks[] names the machine-wide locks each client's platform plugin §6 defines; empty means this
# Robowright Session serialises against nothing.
# Names are validated inside jq: the loop below splits on newlines, so a name holding one must be
# refused before it can become two.
LOCK_NAMES_RAW="$(jq -r '.locks // [] | if type == "array" then .[] else error("locks is not a list") end | if type == "string" then . else error("\(tojson) in locks is not a string") end | if test("[^a-z0-9-]") then error("\(tojson) is not a lock name") else . end' "$SESSION_DIR/run.json")" \
    || fail "run.json locks is not a list of lock names — lowercase letters, digits, hyphens (jq's reason above)"
LOCK_NAMES=()
while IFS= read -r LOCK_NAME; do
    [ -n "$LOCK_NAME" ] || continue
    LOCK_NAMES+=("$LOCK_NAME")
done <<< "$LOCK_NAMES_RAW"
COMPACT_PCT="${COMPACT_PCT:-$(jq -r '.compact_pct // empty' "$SESSION_DIR/run.json")}"
COMPACT_PCT="${COMPACT_PCT:-85}"
case "$COMPACT_PCT" in ''|*[!0-9]*) fail "--compact-pct must be a whole number of percent" ;; esac
[ "$COMPACT_PCT" -ge 10 ] && [ "$COMPACT_PCT" -le 100 ] || fail "--compact-pct must be between 10 and 100"
# Rotation starts a fresh session per unit, so the model is a per-unit choice: the first unit
# that is not done is the one this session works, and its `model` outranks the brief's.
# `kind` is a free-text column in the brief's unit table, so the three fields are tab-separated:
# split on spaces, a two-word kind would slide the unit's model one field over.
NEXT_UNIT="$(jq -r 'first(.units[]? | select((.status // "todo") != "done")) | "\(.id // "?")\t\(if (.kind // "") == "" then "other" else .kind end)\t\(.model // "")"' "$SESSION_DIR/run.json")"
IFS=$'\t' read -r NEXT_UNIT_ID NEXT_UNIT_KIND UNIT_MODEL <<<"$NEXT_UNIT"
# No unit left, or a unit whose row names no kind, is read as the judgment group — never the cheap one.
KIND="${NEXT_UNIT_KIND:-other}"
# The source is decided before the value, so a refusal names the file that needs editing. Only an
# absent or null `profile` is the default: "" is what a half-filled brief table leaves, and it is
# refused rather than read as standard.
if [ -n "$PROFILE" ]; then
    PROFILE_SOURCE="flag"
elif [ "$(jq -r 'has("profile") and .profile != null' "$SESSION_DIR/run.json")" = "true" ]; then
    PROFILE="$(jq -r '.profile' "$SESSION_DIR/run.json")"
    PROFILE_SOURCE="run.json"
else
    PROFILE="standard"
    PROFILE_SOURCE="the default"
fi
check_profile "$PROFILE" "$PROFILE_SOURCE"
read -r PROFILE_MODEL PROFILE_EFFORT <<<"$(profile_expand "$PROFILE" "$(kind_group "$KIND")")"
BRIEF_MODEL="$(jq -r '.model // empty' "$SESSION_DIR/run.json")"
BRIEF_EFFORT="$(jq -r '.effort // empty' "$SESSION_DIR/run.json")"
[ -z "$MODEL" ] || check_model "$MODEL" "flag"
[ -z "$UNIT_MODEL" ] || check_model "$UNIT_MODEL" "unit $NEXT_UNIT_ID"
[ -z "$BRIEF_MODEL" ] || check_model "$BRIEF_MODEL" "brief"
if [ -n "$MODEL" ]; then
    MODEL_SOURCE="flag"
elif [ -n "$UNIT_MODEL" ]; then
    MODEL="$UNIT_MODEL"
    MODEL_SOURCE="unit $NEXT_UNIT_ID"
elif [ -n "$BRIEF_MODEL" ]; then
    MODEL="$BRIEF_MODEL"
    MODEL_SOURCE="brief"
else
    MODEL="$PROFILE_MODEL"
    MODEL_SOURCE="profile $PROFILE, kind $KIND"
fi
check_model "$MODEL" "$MODEL_SOURCE"
# Compared as written: `opus` and a full claude-opus-* id count as different models.
ROBOWRIGHT_WORKER="$(jq -r '.robowright.worker? // empty' "$SESSION_DIR/run.json")"
[ -z "$ROBOWRIGHT_WORKER" ] || check_model "$ROBOWRIGHT_WORKER" "run.json robowright.worker"
OVERRIDE_NOTE=""
# robowright.worker is the profile's per-kind choice, so only a hand-written model can override it.
case "$MODEL_SOURCE" in
    flag|"unit "*|brief)
        [ -z "$ROBOWRIGHT_WORKER" ] || [ "$ROBOWRIGHT_WORKER" = "$MODEL" ] || OVERRIDE_NOTE=" — overrides robowright worker $ROBOWRIGHT_WORKER" ;;
    "profile "*) ;;
esac
if [ -n "$EFFORT" ]; then
    EFFORT_SOURCE="flag"
elif [ -n "$BRIEF_EFFORT" ]; then
    EFFORT="$BRIEF_EFFORT"
    EFFORT_SOURCE="brief"
else
    EFFORT="$PROFILE_EFFORT"
    EFFORT_SOURCE="profile $PROFILE, kind $KIND"
fi
check_effort "$EFFORT" "$EFFORT_SOURCE"

[ -n "$WORKTREE" ] || fail "run.json has no worktree"
if [ "$RESUME" = "true" ] && [ "$ROTATE" = "true" ]; then
    fail "--resume and --rotate are exclusive: resume continues a stopped session's context, rotate starts a fresh one"
fi
if ! WORKTREE_RESOLVED="$(cd "$WORKTREE" 2>/dev/null && pwd -P)"; then
    make_worktree "$SESSION_DIR" "$WORKTREE"
    WORKTREE_RESOLVED="$(cd "$WORKTREE" 2>/dev/null && pwd -P)" || fail_worktree_missing "$SESSION_DIR" "$WORKTREE"
fi
WORKTREE="$WORKTREE_RESOLVED"
worktree_one_line "$WORKTREE"

# A Worker carries every configured MCP server's roster and instructions whether it uses one or
# not, so servers are off unless the brief picks them: run.json `mcp` names servers from the
# approved list beside this script's directory, and absent, null or [] is strict mode over an
# empty set. Adding to the list is the Owner's; a brief only picks from it.
MCP_LIST="$(dirname "$HERE")/mcp"

# Every check of run.json's picks and of the list is this one jq program, on the JSON values, so
# the string checked is the string used. It prints a refusal and halts, or prints the plan: the
# config minus each command path, the allow rules, and one line per server for the binary check.
# A value leaves it as raw text only when a negated class proved the whole string holds no
# whitespace, control character, `:` or `,`; `$` would match before a trailing newline. The one
# exception is a refusal's text, which goes to stderr and never reaches a command.
mcp_validator() {
    cat <<'JQ'
def refuse($why): "refusing: \($why)\n" | halt_error(1);
def check(items; ok; why): reduce items as $x (.; if $x | ok then . else refuse($x | why) end);
def only($class): type == "string" and length > 0 and (test("[^" + $class + "]") | not);
# A server name is a file name in the list and the middle of an `mcp__<server>__` rule, so it
# carries no path separator, no dot and no underscore. Lower case only: the list may sit on a
# case-insensitive volume, where `Gizmo.json` and `gizmo.json` are one file under two names.
def name_ok: only("a-z0-9-") and (startswith("-") | not);
def strings_ok: type == "array" and all(.[]; type == "string");
def words_ok($class): type == "array" and length > 0 and all(.[]; only($class));
def pick_ok: type == "object" and all(keys[]; . == "server" or . == "workflows" or . == "allow")
    and (.server | type) == "string" and (.workflows | strings_ok)
    and (.allow == null or (.allow | strings_ok));
def entry_ok($stem): ($stem | name_ok) and type == "object" and .server == $stem and (.install | type) == "string"
    and (.command | only("A-Za-z0-9._+-") and (startswith("-") or startswith(".") | not))
    and (.args | strings_ok) and (.env | type == "object" and all(.[]; type == "string"))
    and (.version_args | words_ok("A-Za-z0-9._=-")) and (.version_pin | only("0-9.") and (startswith(".") | not))
    and (.workflows_env | only("A-Za-z0-9_")) and (.workflows | words_ok("A-Za-z0-9_-")) and (.allow | strings_ok);

if .mcp_config != null then
    refuse("run.json mcp_config is retired: pick servers in run.json's mcp list instead, each from the approved list at \($dir), and set mcp_config to null")
elif (.mcp == null or ((.mcp | type) == "array" and all(.mcp[]; pick_ok))) | not then
    refuse("run.json mcp must be a list of picks, each {\"server\": <name>, \"workflows\": [<workflow>, ...], \"allow\": [<rule>, ...]}, allow optional")
else .mcp // [] end
| . as $picks
| check($picks[]; .server | name_ok; "run.json mcp names server '\(.server)', which is not a name the approved list at \($dir) can hold")
| check($picks | group_by(.server)[] | select(length > 1) | .[0]; false; "run.json mcp names server '\(.server)' twice; pick each server once")
| (if $picks == [] then {} else $list | map_values(try fromjson catch null) end) as $entries
| check($entries | to_entries[]; .key as $stem | .value | entry_ok($stem);
    "the approved-list entry \($dir)/\(.key).json is malformed; its keys are in \($dir)/README.md")
| [$picks[] | . as $p
    | ($entries[$p.server] // refuse("run.json mcp names server '\($p.server)', which has no entry in the approved list at \($dir). Adding one is the Owner's call")) as $e
    # The server reads an empty workflow variable as none chosen and loads its defaults.
    | if $p.workflows == [] then refuse("run.json mcp picks \($p.server) with no workflows; name the ones the brief needs from: \($e.workflows | join(", "))") else . end
    | [$p.workflows[] | select(. as $w | any($e.workflows[]; . == $w) | not)] as $unoffered
    | if $unoffered != [] then refuse("run.json mcp picks workflow '\($unoffered | join(", "))' for \($p.server), which its entry does not offer: \($e.workflows | join(", "))") else . end
    # A brief's allow replaces the entry's defaults. Either way a rule reaches this server only.
    | (if $p.allow == null then $e.allow else $p.allow end) as $rules
    # --allowedTools splits its value on commas and spaces, so one rule could carry several.
    | check($rules[]; only("A-Za-z0-9_*-");
        "allow rule '\(.)' under \($p.server) holds a character outside A-Z a-z 0-9 _ * -, which --allowedTools could split into rules past \($p.server)")
    | check($rules[]; . == "mcp__\($p.server)" or startswith("mcp__\($p.server)__");
        "allow rule '\(.)' under \($p.server) reaches past it; every rule is mcp__\($p.server) or starts mcp__\($p.server)__")
    | {server: $p.server, entry: $e, workflows: ($p.workflows | join(",")), rules: $rules}]
| {config: {mcpServers: map({key: .server, value: {command: null, args: .entry.args, env: (.entry.env + {(.entry.workflows_env): .workflows})}}) | from_entries},
   allow: [.[].rules[]] | join(","),
   servers: [.[] | [.server, .entry.command, .entry.version_pin, .workflows, (.rules | join(",")), (.entry.version_args | join(","))] | join(":")],
   missing: map({key: .server, value: "refusing: \(.server)'s binary \(.entry.command) is not on PATH. The Owner installs it: \(.entry.install)\n"}) | from_entries}
JQ
}

# One server the validator passed: a daemon-started session's PATH is not this one's, so the config
# carries the absolute path of the binary checked here.
add_mcp_server() {
    local server="$1" command_name="$2" pin="$3" workflows="$4" rules="$5" binary version
    local version_args=()
    IFS=, read -r -a version_args <<<"$6"
    binary="$(type -P "$command_name" || true)"
    [ -n "$binary" ] || { jq -j --arg server "$server" '.missing[$server]' <<<"$MCP_PLAN_JSON" >&2; exit 1; }
    case "$binary" in
        /*) ;;
        *) binary="$PWD/$binary" ;;
    esac
    version="$("$binary" "${version_args[@]}" </dev/null 3<&- 2>/dev/null | head -1 | tr -d '[:space:]' || true)"
    [ "$version" = "$pin" ] || case "$version" in
        "$pin".*) ;;
        *) fail "$binary prints version '$version', outside $server's approved pin $pin. Loosening a pin is the Owner's call" ;;
    esac
    MCP_CONFIG="$(jq -c --arg server "$server" --arg binary "$binary" '.mcpServers[$server].command = $binary' <<<"$MCP_CONFIG")"
    MCP_PLAN+=("$server: $binary $version, workflows $workflows; allow ${rules//,/ }")
}

# The list as one object keyed by file stem, each value the file's text: a pick finds its entry by
# exact key, never by a path built from its name, and a file that is not JSON is the validator's
# refusal rather than a jq error. So is one the launcher cannot read, and only for a brief that picks.
MCP_ENTRIES='{}'
for MCP_FILE in "$MCP_LIST"/*.json; do
    [ -f "$MCP_FILE" ] || continue
    MCP_STEM="${MCP_FILE##*/}"
    if [ -r "$MCP_FILE" ]; then
        MCP_ENTRIES="$(jq -c --arg stem "${MCP_STEM%.json}" --rawfile text "$MCP_FILE" '. + {($stem): $text}' <<<"$MCP_ENTRIES")"
    else
        MCP_ENTRIES="$(jq -c --arg stem "${MCP_STEM%.json}" '. + {($stem): null}' <<<"$MCP_ENTRIES")"
    fi
done
MCP_PLAN_JSON="$(jq -c --arg dir "$MCP_LIST" --argjson list "$MCP_ENTRIES" "$(mcp_validator)" "$SESSION_DIR/run.json")" || exit 1
MCP_CONFIG="$(jq -c '.config' <<<"$MCP_PLAN_JSON")"
MCP_PLAN=()
# The plan comes in on fd 3, which the version check closes, so no binary can read the next server's line.
while IFS=: read -r -u 3 MCP_SERVER MCP_COMMAND MCP_PIN MCP_WORKFLOWS MCP_RULES MCP_VERSION_ARGS; do
    add_mcp_server "$MCP_SERVER" "$MCP_COMMAND" "$MCP_PIN" "$MCP_WORKFLOWS" "$MCP_RULES" "$MCP_VERSION_ARGS"
done 3< <(jq -r '.servers[]' <<<"$MCP_PLAN_JSON")
MCP_FLAGS=(--strict-mcp-config --mcp-config "$MCP_CONFIG")
# --allowedTools takes a variadic list, so its one comma-joined value is closed by the next flag.
MCP_ALLOW="$(jq -r '.allow' <<<"$MCP_PLAN_JSON")"
ALLOW_FLAGS=()
if [ -n "$MCP_ALLOW" ]; then
    ALLOW_FLAGS=(--allowedTools "$MCP_ALLOW")
fi

# Built-in tool definitions ride on every request. A background session the supervisor retires
# and wakes may come back with the full set: that costs tokens and takes nothing away.
LEAN_TOOLS="Bash,Read,Write,Edit,Grep,Glob,Agent,Skill,Monitor,TaskStop,ToolSearch,LSP,WebFetch,WebSearch"
# A brief's `tools` names built-in tools from this list. `default`, which restores every tool, and a
# name outside it are refused: run.json is session-writable, and this is the next session's tool set.
KNOWN_TOOLS="$LEAN_TOOLS,MultiEdit,NotebookEdit,NotebookRead,TodoWrite,Task,TaskCreate,TaskGet,TaskList,TaskUpdate,TaskOutput,BashOutput,KillShell,ExitPlanMode,EnterPlanMode,AskUserQuestion,SendMessage,ListAgents,EnterWorktree,ExitWorktree,ScheduleWakeup,PushNotification,CronCreate,CronDelete,CronList,RemoteTrigger,SlashCommand"
TOOLS="$(jq -r --arg lean "$LEAN_TOOLS" --arg known "$KNOWN_TOOLS" '
    if .tools == null then $lean
    elif (.tools | type) == "string" and (.tools | test("\\A[A-Za-z]+(,[A-Za-z]+)*\\z")) and ((.tools | split(",")) - ($known | split(",")) == []) then .tools
    else empty end' "$SESSION_DIR/run.json")"
[ -n "$TOOLS" ] || fail "run.json 'tools' must be null or a comma-joined list of tool names from: $KNOWN_TOOLS"
# Every worktree convention puts a worktrees/ or .worktrees/ component in the path. The main clone has none,
# and the .git-file test below is what actually proves this is a linked worktree rather than a
# checkout that merely sits there.
case "$WORKTREE" in
    */worktrees/*|*/.worktrees/*) ;;
    *) fail "worktree must live under a .worktrees/ or worktrees/ directory, never the main clone: $WORKTREE" ;;
esac
# run.json.worktree is session-written: git runs inside it only once a configured repository lists
# it (owner_git.py prints the refusal), and then only with owner_git.py's overrides.
python3 "$OWNER_GIT" worktree "$WORKTREE" >/dev/null || fail "run.json worktree $WORKTREE is not one the Owner's configured repositories list (above)"
# owner_git.py prints the options, then `--env` and the variables its --config-env options name.
GIT=(git)
IS_GIT_ENV=false
while IFS= read -r FLAG; do
    if [ "$FLAG" = "--env" ]; then IS_GIT_ENV=true
    elif $IS_GIT_ENV; then export "$FLAG"
    else GIT+=("$FLAG"); fi
done < <(python3 "$OWNER_GIT" flags "$WORKTREE")
[ "${#GIT[@]}" -gt 1 ] && $IS_GIT_ENV || fail "owner_git.py printed no git options"
# The worktree's .gitattributes is session content: no git call here reads attributes, so none runs a filter as the Owner.
ATTRIBUTES_OFF="$(python3 "$OWNER_GIT" attributes "$WORKTREE")" || fail "no git call runs in $WORKTREE without --attr-source (above); nothing started"
while IFS= read -r FLAG; do GIT+=("$FLAG"); done <<< "$ATTRIBUTES_OFF"
TOPLEVEL="$("${GIT[@]}" -C "$WORKTREE" rev-parse --show-toplevel 2>/dev/null)" || fail "$WORKTREE is not a git checkout"
[ "$TOPLEVEL" = "$WORKTREE" ] || fail "$WORKTREE is not the checkout's toplevel ($TOPLEVEL)"
[ -f "$WORKTREE/.git" ] || fail "$WORKTREE has a .git directory, so it is a clone, not a linked worktree"
role_grants worker "$SESSION_DIR" "$WORKTREE"
# Effort rides on every command this script builds — launch, rotate and resume — for the same
# reason --model does: nothing restores it from the session record on a restart.
SESSION_FLAGS=("${MCP_FLAGS[@]}" ${ALLOW_FLAGS[@]+"${ALLOW_FLAGS[@]}"} --tools "$TOOLS" --effort "$EFFORT" --settings "$(session_settings "$EFFORT" "$MODEL" "$STOP_CAP" "$COMPACT_PCT" "$SUBAGENT_MODEL" "$GRANTS")")
# A Worker's shell writes the admin dir, and git writes a refreshed index through a link planted at its index.
DIRTY="$("${GIT[@]}" --no-optional-locks -C "$WORKTREE" status --short --ignore-submodules=all)"
# A process that died mid-edit left the work uncommitted, and it belongs to the session being
# resumed. Nothing else may start over changes it has no owner for.
if [ -n "$DIRTY" ] && [ "$RESUME" != "true" ]; then
    fail "worktree is dirty:
$DIRTY"
fi

if [ "$RESUME" = "true" ]; then
    if [ -n "$RESUME_ID" ]; then
        [[ "$RESUME_ID" =~ $SESSION_UUID_FORM ]] || fail "--resume takes a session UUID (got '$RESUME_ID')"
    else
        RESUME_ID="$RUN_SESSION_ID"
        [ -n "$RESUME_ID" ] || fail "--resume needs a session id: none given and run.json has no session_id (run-roster.py --json shows it when a session was seen)"
        [[ "$RESUME_ID" =~ $SESSION_UUID_FORM ]] || fail "run.json 'session_id' must be a session UUID (got '$RESUME_ID')"
    fi
    # A stopped session is resumable only once its decision is recorded: whoever decided applies
    # `session-state.py <dir> resume --by <owner|lead> --decision <text>` first.
    check_op "$SESSION_DIR" resume ""
elif [ "$ROTATE" = "true" ]; then
    check_op "$SESSION_DIR" rotate ""
else
    LAUNCH_FIX=""
    # Only when --rotate would be let through: an invalid stored state reads awaiting-rotation too.
    if python3 "$STATE_TOOL" "$SESSION_DIR" check-op rotate >/dev/null 2>&1; then
        LAUNCH_FIX="; launch it with --rotate"
    fi
    check_op "$SESSION_DIR" launch "$LAUNCH_FIX"
fi

# A live session already in this worktree means the Worker is running or the Owner is in it.
refuse_live_in "$WORKTREE"

# One Robowright Session holds a given device lock at a time on this machine — a shared simulator,
# a snapshot store with no lock of its own. The Worker takes and releases the lock per the
# project hook → Device; this script only refuses to start a second holder, and never creates
# or removes the lock.
for LOCK_NAME in ${LOCK_NAMES[@]+"${LOCK_NAMES[@]}"}; do
    LOCK="$SESSIONS_ROOT/.$LOCK_NAME-lock"
    [ -e "$LOCK" ] || continue
    LOCK_OWNER=""
    [ ! -f "$LOCK/owner" ] || LOCK_OWNER="$(head -1 "$LOCK/owner")"
    [ -n "$LOCK_OWNER" ] || fail "$LOCK exists but names no owner — a Worker probably died holding it. Inspect it and clear it by hand; this script never does"
    LOCK_OWNER="$(cd "$LOCK_OWNER" 2>/dev/null && pwd -P)" || LOCK_OWNER="$(head -1 "$LOCK/owner")"
    [ "$LOCK_OWNER" = "$SESSION_DIR" ] || fail "the $LOCK_NAME lock ($LOCK) is held by $LOCK_OWNER — one holder at a time on this machine. Wait for that Robowright Session to release it, or launch one whose brief names no locks"
done

NAME="${NAME:-$(printf 'worker-%s-%s' "$MODEL" "$UNIT_ID" | tr '[:upper:]' '[:lower:]')}"
MARKER="$WORKTREE/.claude/autonomous-run"

if [ "$RESUME" = "true" ]; then
    ACTION="resume session $RESUME_ID"
    # Which resume this is: a `resume` event means a decision is waiting in LEDGER.md; anything
    # else, or no log at all, means the process ended with neither a stop nor a decision.
    # Refused events never applied, so they are skipped; a corrupt log never reaches this line,
    # because check-op above refuses the resume outright.
    LAST_EVENT="$(jq -r 'select(.refused != true) | .event' "$SESSION_DIR/events.jsonl" 2>/dev/null | tail -1 || true)"
    if [ "$LAST_EVENT" = "resume" ]; then
        RESUME_PROMPT="$RESUME_PROMPT_ANSWERED"
    else
        RESUME_PROMPT="$RESUME_PROMPT_ORPHAN"
    fi
    [ -z "$DIRTY" ] || RESUME_PROMPT="$RESUME_PROMPT $DIRTY_PROMPT"
    # A skill's hooks register when the skill is invoked, and a resumed process starts with none:
    # the prompt invokes the skill again so the stop gate is armed.
    CMD=(claude --bg --model "$MODEL" "${SESSION_FLAGS[@]}" "--resume=$RESUME_ID" "/worker $SESSION_DIR $RESUME_PROMPT")
elif [ "$ROTATE" = "true" ]; then
    ACTION="rotate (fresh session; rotation requested $ROTATE_REQUESTED)"
    CMD=(claude --bg --model "$MODEL" "${SESSION_FLAGS[@]}" --name "$NAME" "/worker $SESSION_DIR")
else
    ACTION="launch"
    CMD=(claude --bg --model "$MODEL" "${SESSION_FLAGS[@]}" --name "$NAME" "/worker $SESSION_DIR")
fi

LEDGER_VERB="one entry will be appended"
[ "$DRY_RUN" != "true" ] || LEDGER_VERB="dry run: nothing appended"
{
    echo "dir:       $SESSION_DIR ($UNIT_ID, phase $PHASE${STOP_CODE:+, stopped: $STOP_CODE})"
    echo "worktree:  $WORKTREE"
    if [ -n "$DIRTY" ]; then
        echo "dirty:     uncommitted, and the resumed Robowright Session's own — it is told to sort them out:"
        printf '%s\n' "$DIRTY" | sed 's/^/           /'
    fi
    echo "action:    $ACTION"
    echo "launch:    $LAUNCH_MODE ($LAUNCH_SOURCE)"
    echo "marker:    $MARKER ← $SESSION_DIR"
    echo "model:     $MODEL Worker (from $MODEL_SOURCE)$OVERRIDE_NOTE; subagents default to $SUBAGENT_MODEL (reviewer-*.md pins outrank it)"
    echo "effort:    $EFFORT (from $EFFORT_SOURCE) — --effort for this process, --settings for the ones the supervisor wakes"
    echo "mcp:       ${MCP_FLAGS[*]}"
    for LINE in ${MCP_PLAN[@]+"${MCP_PLAN[@]}"}; do
        echo "           $LINE"
    done
    echo "tools:     $TOOLS"
    for LOCK_NAME in ${LOCK_NAMES[@]+"${LOCK_NAMES[@]}"}; do
        echo "lock:      $LOCK_NAME — free or already ours ($SESSIONS_ROOT/.$LOCK_NAME-lock)"
    done
    [ "${#LOCK_NAMES[@]}" -gt 0 ] || echo "lock:      none — run.json locks is empty"
    echo "env:       via --settings: CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=$STOP_CAP, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=$COMPACT_PCT, CLAUDE_CODE_SUBAGENT_MODEL=$SUBAGENT_MODEL; CLAUDECODE unset"
    grants_plan
    printf 'command:  '; printf ' %q' "${CMD[@]}"; printf '\n'
    echo "ledger:    $SESSION_DIR/LEDGER.md ($LEDGER_VERB)"
} | show

if [ "$DRY_RUN" = "true" ]; then
    echo "dry run — nothing started"
    exit 0
fi

if [ "$ASSUME_YES" != "true" ]; then
    printf 'Start it? [y/N] '
    read -r reply < /dev/tty
    case "$reply" in
        y|Y|yes) ;;
        *) echo "aborted"; exit 1 ;;
    esac
fi

# `mkdir -p` and the marker write would both follow a link here out of the worktree.
[ ! -L "$WORKTREE/.claude" ] || fail "$WORKTREE/.claude is a symlink; the marker is never written through one, so nothing started"
mkdir -p "$WORKTREE/.claude"
check_writable "$MARKER" "$SESSION_DIR/LEDGER.md" "$SESSION_DIR/.session-state.lock"
# A depends_on checkout's admin dir in the dependency repository is named by git, so no grant can name it: it is made here.
python3 "$GRANTS_TOOL" checkouts "$SESSION_DIR" || fail "a depends_on checkout was not made (above); nothing started"

# `claude stop` runs no SessionEnd hook and a finished session is left idle, so the session being
# replaced never recorded its own cost. This is the last moment anyone is looking. Best effort:
# a missing or failing cost tool never blocks the launch.
if [ "$RESUME" = "true" ] || [ "$ROTATE" = "true" ]; then
    python3 "$COST_TOOL" --run-dir "$SESSION_DIR" --write --json >/dev/null 2>&1 \
        || echo "note: $COST_TOOL could not record the previous session's cost; launching anyway" >&2
    PREVIOUS_ID="$(jq -r '.session_id // empty' "$SESSION_DIR/run.json" 2>/dev/null || true)"
    # A resume of that same id continues it, and its own end records it; recorded now, the ledger
    # would skip everything it does after.
    [ "$RESUME" != "true" ] || [ "$RESUME_ID" != "$PREVIOUS_ID" ] || PREVIOUS_ID=""
    # It builds a transcript path below.
    if [ -n "$PREVIOUS_ID" ] && ! [[ "$PREVIOUS_ID" =~ $SESSION_UUID_FORM ]]; then
        echo "note: run.json 'session_id' is not a session UUID; the previous session's records were not appended" >&2
        PREVIOUS_ID=""
    fi
    if [ -n "$PREVIOUS_ID" ]; then
        # pin_session's transcript path for that session.
        PREVIOUS_TRANSCRIPT="$HOME/.claude/projects/$(printf '%s' "$WORKTREE" | tr -c 'A-Za-z0-9' '-')/$PREVIOUS_ID.jsonl"
        python3 "$COST_TOOL" --run-dir "$SESSION_DIR" --ledger --session-id "$PREVIOUS_ID" --transcript "$PREVIOUS_TRANSCRIPT" >/dev/null 2>&1 \
            || echo "note: $COST_TOOL could not append the previous session's records to the accounting ledger; launching anyway" >&2
    fi
fi

printf '%s\n' "$SESSION_DIR" | python3 "$SESSION_WRITE" replace "$MARKER" || fail "the marker was not written (above)"

# A session is denied the repository's .git/info, so the marker's exclude line is added here, on the Owner's side.
if ! "${GIT[@]}" -C "$WORKTREE" check-ignore -q .claude/autonomous-run; then
    COMMON_DIR="$("${GIT[@]}" -C "$WORKTREE" rev-parse --path-format=absolute --git-common-dir)" || fail "git could not name $WORKTREE's common git dir"
    [ ! -L "$COMMON_DIR/info" ] || fail "$COMMON_DIR/info is a symlink; the exclude line is never written through one"
    mkdir -p "$COMMON_DIR/info"
    printf '.claude/autonomous-run\n' | append_to "$COMMON_DIR/info/exclude"
fi

# The body of a Worker ledger entry; $1 is the line saying what started, or empty.
worker_entry() {
    # On --resume the session keeps the name it was launched with, so record the id we resumed.
    if [ -n "$RESUME_ID" ]; then
        printf -- '- resumed session: %s\n' "$RESUME_ID"
    else
        printf -- '- session name: %s\n' "$NAME"
    fi
    [ -z "$1" ] || printf '%s\n' "$1"
    # The model varies per session once units name their own, and this is the only durable record
    # of which one ran which unit: run.json's `model` stays the brief's default for the next unit.
    printf -- '- model: %s (from %s)%s\n' "$MODEL" "$MODEL_SOURCE" "$OVERRIDE_NOTE"
    printf -- '- effort: %s (from %s)\n' "$EFFORT" "$EFFORT_SOURCE"
    printf -- '- worktree: %s\n' "$WORKTREE"
    printf -- '- env: stop cap %s · autocompact %s%%\n' "$STOP_CAP" "$COMPACT_PCT"
}

# The parent agent session exports CLAUDECODE=1; drop it so the child is a top-level session.
start_or_handoff "$WORKTREE" "$SESSION_DIR/LEDGER.md" worker_entry
echo "$OUT"
# The id on the "backgrounded" line: a resume prints the id it resumed first, and the new session runs under another.
BG_ID="$(background_id_of "$OUT")"

NEW_SESSION_ID=""
[ -z "$BG_ID" ] || NEW_SESSION_ID="$(registry_session_id "$BG_ID")"
[ -z "$NEW_SESSION_ID" ] || pin_session "$SESSION_DIR" "$NEW_SESSION_ID" "$WORKTREE"
# Written only once a session started: a hand-off leaves run.json as the Lead approved it. A unit
# id outside every group has no project to name; the launch goes on without one.
if match_group "$UNIT_ID" --soft; then
    write_project "$SESSION_DIR" "$MATCHED_GROUP"
fi
[ -z "$NEW_SESSION_ID" ] || append_launch_index "$NEW_SESSION_ID" worker \
    "$(jq -r '.project // empty' "$SESSION_DIR/run.json" 2>/dev/null || true)" "$UNIT_ID" "$SESSION_DIR"

BG_LINE=""
[ -z "$BG_ID" ] || BG_LINE="$(background_id_line "$BG_ID")"
{
    printf '\n## %s — %s via %s\n' "$(date '+%Y-%m-%d %H:%M')" "$ACTION" "$LAUNCHER_NAME"
    worker_entry "$BG_LINE"
} | append_to "$SESSION_DIR/LEDGER.md"

echo "started. attach: claude attach ${BG_ID:-<id>} · logs: claude logs ${BG_ID:-<id>} · roster: run-roster.py"
