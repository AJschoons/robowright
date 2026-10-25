#!/usr/bin/env bash
# accept.sh [-S|--sign] --tip <commit> --message <file> <session_dir> — integrates a finished Robowright Session: one
# squash commit carrying the session branch tip's tree, parented on the main clone's checked-out
# branch, which then fast-forwards to it. The Owner runs the installed copy, never one inside the clone it
# integrates; a Lead or a Worker hands the Owner the line, with --message naming a file that holds the
# squash message. -S signs the squash with the main clone's own signing configuration.
#
# accept.sh --direct [-S|--sign] --base <commit> --tip <commit> --message <file> <project_dir> <slug> — the same for a
# direct build, which has no session folder: the range <base>..robowright/<slug> becomes one commit on the
# main clone's branch, and <project_dir>/prs/<slug>/ACCEPTED.json records it. Its refusals are listed at
# direct_accept.
#
# A session's worktree is run.json's, accepted only when a repository that launch.json's `repos` lists and
# a robowright.json under the projects root names lists it (owner_git.py), and the main clone is
# that configured repository. Every
# git call carries owner_git.py's overrides: no fsmonitor, no hooks (config hooks turned off by name, read in the
# checkout the call runs in), no pager.
# No editor runs.
#
# --tip is the full id of the branch tip the line was composed for; the accept integrates that commit or nothing.
#
# Preflight, each refused by name with exit 2 before anything is written:
#   tip-missing              no --tip was given (both modes, before anything is read)
#   tip-invalid              --tip is not a full commit id (both modes, before anything is read)
#   message-missing          no --message was given
#   message-outside          --message is not a file directly in a unit folder <session_dir>/prs/<unit>/, spelled with
#                            no `.`, `..` or empty part, <session_dir> links resolved; nothing is read
#   message-unreadable       session_write.py would not read the --message file: missing, a link on its path, not a
#                            regular file with one link, or over 64 KiB
#   phase-not-done           run.json phase is not done
#   already-accepted         run.json.accepted is set
#   intake-missing           <session_dir>/INTAKE.md does not exist
#   repos-unconfigured       launch.json has no well-formed `repos`, so no repository is trusted
#   worktree-unlisted        no configured repository lists run.json.worktree
#   worktree-foreign-gitdir  a listed worktree whose .git names another repository's git dir
#   accept-in-target         accept.sh, resolved, is inside the main clone or a worktree it lists; run the installed copy
#   tip-moved                the session branch's tip is not --tip
#   main-not-ancestor        the main clone's branch is not an ancestor of the session branch's tip
#   main-dirty               `git status --porcelain --ignore-submodules=all` in the main clone prints anything
# `#` lines are dropped from the message, and it is refused, exit 2, nothing integrated:
#   message-empty        nothing is left
#   message-git-default  the first line is git's `Squashed commit of the following:`
# Session-written text is printed with its control bytes removed. After the fast-forward,
# run.json.accepted is written through session-state.py's `accept` event, the tree-identical check is
# printed, and so is the teardown line, which this script never runs. Its `branch -D` names every unit branch of the
# session that the tip holds; a unit branch holding a commit the tip lacks is printed as kept instead.

set -uo pipefail

readonly EXIT_REFUSED=2
# accept.sh itself, links resolved; the scripts beside it are its clone's.
SELF=$(python3 -I -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}") && [[ -n "$SELF" ]] \
    || { echo "accept: cannot resolve accept.sh's own path: nothing was run" >&2; exit 1; }
readonly SELF
readonly SCRIPTS="$(dirname "$SELF")/../../robowright/scripts"
# The accept line's portable spelling: install.sh links it to a clone no session can write.
readonly INSTALLED='~/.claude/skills/lead/scripts/accept.sh'
readonly SESSION_STATE="$SCRIPTS/session-state.py"
readonly OWNER_GIT="$SCRIPTS/owner_git.py"
readonly SESSION_WRITE="$SCRIPTS/session_write.py"
# A unit name `robowright/<slug>` takes as one branch segment, as BRANCH_SLUG in tools/robowright-dash.py.
readonly SLUG_FORM='^[A-Za-z0-9]+([._-][A-Za-z0-9]+)*$'
# A full commit id, SHA-1 or SHA-256.
readonly COMMIT_FORM='^([0-9a-f]{40}|[0-9a-f]{64})$'

# Text a session wrote, as printed: tab and newline kept, every other C0, DEL and C1 control dropped.
show() { python3 "$OWNER_GIT" show; }
refuse() { echo "refused: $1: $2" | show >&2; exit "$EXIT_REFUSED"; }
die() { echo "accept: $1" | show >&2; exit 1; }

readonly USAGE="usage: accept.sh [-S|--sign] --tip <commit> --message <file> <session_dir>, or accept.sh --direct [-S|--sign] --base <commit> --tip <commit> --message <file> <project_dir> <slug>"
has_message_file=false
is_direct=false
has_base=false
has_tip=false
message_file=""
base=""
expected_tip=""
positionals=()
sign=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --message) [[ $# -ge 2 ]] || die "$USAGE"; has_message_file=true; message_file=$2; shift 2 ;;
        --base) [[ $# -ge 2 ]] || die "$USAGE"; has_base=true; base=$2; shift 2 ;;
        --tip) [[ $# -ge 2 ]] || die "$USAGE"; has_tip=true; expected_tip=$2; shift 2 ;;
        --direct) is_direct=true; shift ;;
        -S|--sign) sign=(-S); shift ;;
        -*) die "$USAGE" ;;
        *) positionals+=("$1"); shift ;;
    esac
done

# Refused before anything is read unless --tip is a full commit id.
check_tip_form() {
    $has_tip || refuse tip-missing "accept.sh integrates the commit the line names: add --tip <the full id of the reviewed branch tip>"
    [[ "$expected_tip" =~ $COMMIT_FORM ]] || refuse tip-invalid "--tip '$expected_tip' is not a full commit id"
}

# Refused, naming both ids, when the branch tip $1 is not --tip's: the branch moved after the line was composed.
check_tip_moved() {
    [[ "$1" == "$expected_tip" ]] \
        || refuse tip-moved "$2 is at $1, not at --tip $expected_tip: a commit was added after the line was composed; nothing was integrated. Review the branch again, then run the line with its new tip"
}

# $1 with its links resolved, as check_message_place compares it.
real_path() { python3 -I -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"; }

# Refused message-outside, before the --message file is read, unless its path is absolute with no `.`, `..` or empty
# part and its folder is $1/prs/$2, $1 links resolved, or $1/prs/<any one segment> when no $2 is given. The --message path
# itself is not resolved: a link on it is message-unreadable, and resolving it would read the folders it names.
check_message_place() {
    local folder
    folder=$(python3 -I -c '
import os, sys
message, prefix = sys.argv[1:3]
unit = sys.argv[3] if len(sys.argv) > 3 else None
real = os.path.realpath(prefix)
parts = message.split("/")
print(os.path.join(real, "prs", "<unit>" if unit is None else unit))
is_shaped = message.startswith("/") and not any(part in ("", ".", "..") for part in parts[1:])
is_placed = len(parts) >= 3 and "/".join(parts[:-2]) == os.path.join(real, "prs") and (unit is None or parts[-2] == unit)
sys.exit(0 if is_shaped and is_placed else 3)
' "$message_file" "$@")
    case $? in
        0) return 0 ;;
        3) refuse message-outside "$message_file is not a file directly in $folder/: accept.sh reads the squash message only from there; nothing was read or written" ;;
        *) die "could not check where $message_file lies: nothing was read or written" ;;
    esac
}

# The --message file's bytes into $raw_message, read by session_write.py: a session writes that file, and can plant a
# link or a FIFO at its name or on its path. Refused message-unreadable with session_write.py's reason.
read_message() {
    raw_message=$(python3 "$SESSION_WRITE" read "$message_file" 2>/dev/null) && return 0
    local why
    why=$(python3 "$SESSION_WRITE" read "$message_file" 2>&1 >/dev/null)
    refuse message-unreadable "${why#refused: }: nothing was written"
}

# The message, as read, into $message with its # lines dropped; refused when nothing, or git's default, is left.
# It moves only through variables and pipes: sessions can write $TMPDIR, and bash 3.2 puts a here-string there.
# With -S and gpg.format=ssh, git itself still writes the commit it signs to a file in $TMPDIR.
take_message() {
    echo "squash message, from $message_file:" | show
    printf '%s\n' "$raw_message" | sed 's/^/  | /' | show
    message=$(printf '%s\n' "$raw_message" | "${GIT[@]}" -C "$1" stripspace --strip-comments)
    [[ -n "$message" ]] || refuse message-empty "the message is empty once its # lines are dropped: nothing was committed"
    [[ "$(printf '%s\n' "$message" | head -n 1)" != "Squashed commit of the following:" ]] \
        || refuse message-git-default "the subject is git's 'Squashed commit of the following:': nothing integrated; write the subject this change deserves"
}

# Refused when accept.sh is inside a checkout of the repository it integrates into: after the fast-forward, the scripts
# beside it would be the build's, run as the Owner.
refuse_in_target() {
    local checkout
    checkout=$("${GIT[@]}" -C "$1" worktree list --porcelain -z | python3 -I -c '
import os, sys
sys.path.insert(0, sys.argv[2])
import owner_git
fields = sys.stdin.buffer.read().split(b"\0")
# The main entry names the git dir, not the clone, when that lives elsewhere (--separate-git-dir): the clone is added.
checkouts = [sys.argv[3]] + [os.fsdecode(f[len(b"worktree "):]) for f in fields if f.startswith(b"worktree ")]
print(next((c for c in checkouts if owner_git.is_within(sys.argv[1], [c])), ""))
' "$SELF" "$SCRIPTS" "$1") || die "could not list the checkouts of $1: nothing was integrated"
    [[ -z "$checkout" ]] || refuse accept-in-target "$SELF is inside $checkout, a checkout of the repository this accept rewrites: run $INSTALLED, linked by install.sh to a clone no session can write"
}

# The full commit id an accept record names, or nothing; the record is session-written, so it is read as owner_git reads one.
recorded_sha() {
    python3 -I -c '
import json, re, sys
sys.path.insert(0, sys.argv[1])
import owner_git
data = owner_git.read_entry(sys.argv[2])
try:
    sha = json.loads(data).get("sha") if data is not None else None
except (ValueError, AttributeError, RecursionError):
    sha = None
print(sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) else "")
' "$SCRIPTS" "$1" 2>/dev/null
}

# $GIT for the main clone $1, and the variables its --config-env options name exported, from owner_git.py flags.
hardened_git() {
    GIT=(git)
    local line is_env=false
    while IFS= read -r line; do
        if [[ "$line" == "--env" ]]; then
            is_env=true
        elif $is_env; then
            export "$line"
        else
            GIT+=("$line")
        fi
    done < <(python3 "$OWNER_GIT" flags "$1")
    (( ${#GIT[@]} > 1 )) && $is_env || die "owner_git.py printed no git options: nothing was run"
}

# Into $teardown_branches, the session's unit branches in the main clone $1 that the tip $3 holds: robowright/<slug> and
# robowright/<slug>-u<N>, as rw-git owns them, <slug> the session folder's name; into $kept_branches, those it does not.
# Only the worktree's branch $2 when <slug> is out of shape or $2 is not one of them.
collect_unit_branches() {
    local main_clone=$1 head=$2 tip=$3 slug own ref name number is_head_own=false
    teardown_branches=() kept_branches=()
    slug=$(basename "$(real_path "$session_dir")")
    own="robowright/$slug"
    if [[ "$slug" =~ $SLUG_FORM && "$slug" != *.lock ]]; then
        while IFS= read -r ref; do
            name=${ref#refs/heads/}
            number=${name#"$own-u"}
            [[ "$name" == "$own" || ( "$number" != "$name" && "$number" =~ ^[1-9][0-9]*$ ) ]] || continue
            [[ "$name" == "$head" ]] && is_head_own=true
            if "${GIT[@]}" -C "$main_clone" merge-base --is-ancestor --end-of-options "$ref" "$tip" 2>/dev/null; then
                teardown_branches+=("$name")
            else
                kept_branches+=("$name")
            fi
        done < <("${GIT[@]}" -C "$main_clone" for-each-ref --sort=version:refname --format='%(refname)' \
            "refs/heads/$own" "refs/heads/$own-u*")
    fi
    if ! $is_head_own; then
        teardown_branches=("$head") kept_branches=()
    fi
}

# Preflight for --direct, each refused by name with exit 2 before anything is written, after tip-missing, tip-invalid,
# message-missing, message-outside (the file is not directly in <project_dir>/prs/<slug>/) and message-unreadable:
#   slug-invalid         <slug> is not one branch segment (SLUG_FORM), or ends .lock
#   base-invalid         --base is not a full commit id
#   description-missing  <project_dir>/prs/<slug>.md, the change description, does not exist
#   already-accepted     <project_dir>/prs/<slug>/ACCEPTED.json exists
#   record-unwritable    session_write.py would refuse to write ACCEPTED.json: prs/<slug>/ made a link or removed after
#                        the message was read through it
#   branch-missing       no trusted repository (owner_git.py) holds refs/heads/robowright/<slug>
#   branch-ambiguous     more than one does
#   accept-in-target     accept.sh, resolved, is inside the main clone or a worktree it lists
#   tip-moved            the branch tip is not --tip
#   base-not-ancestor    --base is not an ancestor of the branch tip
#   base-not-on-main     --base is not an ancestor of the main clone's branch
#   main-dirty           the main clone has uncommitted or untracked files
#   worktree-dirty       the worktree with the branch checked out has any
# then message-empty and message-git-default, and
#   range-conflicts      the range does not merge cleanly onto the main clone's branch
# With that branch still at --base, the commit carries the tip's tree; past it, the range is merged in by
# `merge-tree`, which writes no index and no checkout. The output says how far main moved and whether the integrated
# diff's patch-id is the branch's.
direct_accept() {
    local project_dir=$1 slug=$2
    [[ "$slug" =~ $SLUG_FORM && "$slug" != *.lock ]] || refuse slug-invalid "'$slug' is not a unit name robowright/<slug> can hold"
    [[ "$base" =~ $COMMIT_FORM ]] || refuse base-invalid "--base '$base' is not a full commit id"
    local description="$project_dir/prs/$slug.md" record="$project_dir/prs/$slug/ACCEPTED.json"
    [[ -f "$description" ]] || refuse description-missing "$description does not exist: a direct build is accepted from its change description"
    if [[ -e "$record" || -L "$record" ]]; then
        local recorded
        recorded=$(recorded_sha "$record")
        refuse already-accepted "$record exists, naming ${recorded:-no commit id}: a build is accepted once. A session can write that file: before any teardown, check the commit is on main with git merge-base --is-ancestor <commit> <main branch> in the main clone"
    fi
    python3 "$SESSION_WRITE" check "$record" 2>/dev/null \
        || refuse record-unwritable "$record could not be written (prs/$slug/ missing, or a link): nothing was integrated"

    local branch="robowright/$slug" held main_clone worktree
    # owner_git.py prints its own refusal line and exits 2.
    held=$(python3 "$OWNER_GIT" branch "$branch") || exit $?
    main_clone=$(printf '%s\n' "$held" | sed -n 1p)
    worktree=$(printf '%s\n' "$held" | sed -n 2p)
    hardened_git "$main_clone"
    refuse_in_target "$main_clone"

    local main_branch main_sha tip
    main_branch=$("${GIT[@]}" -C "$main_clone" symbolic-ref --short HEAD) || die "$main_clone has no branch checked out"
    [[ "$main_branch" != "$branch" ]] || die "$main_clone has $branch checked out: switch it to the branch the build integrates into"
    main_sha=$("${GIT[@]}" -C "$main_clone" rev-parse --verify HEAD) || die "$main_clone has no commit on $main_branch"
    tip=$("${GIT[@]}" -C "$main_clone" rev-parse --verify --end-of-options "refs/heads/$branch^{commit}") || die "$branch does not resolve in $main_clone"
    check_tip_moved "$tip" "$branch"
    "${GIT[@]}" -C "$main_clone" merge-base --is-ancestor --end-of-options "$base" "$tip" 2>/dev/null \
        || refuse base-not-ancestor "--base $base is not an ancestor of $branch ($tip) in $main_clone: give the commit the build was cut from"
    "${GIT[@]}" -C "$main_clone" merge-base --is-ancestor --end-of-options "$base" "$main_sha" 2>/dev/null \
        || refuse base-not-on-main "--base $base is not on $main_branch ($main_sha): the range would leave out the branch's commits before it; give the commit the build was cut from"
    local status
    status=$("${GIT[@]}" -C "$main_clone" status --porcelain --ignore-submodules=all) || die "git status failed in $main_clone"
    [[ -z "$status" ]] || refuse main-dirty "$main_clone has uncommitted or untracked files: $main_branch fast-forwards only over a clean tree"
    if [[ -n "$worktree" ]]; then
        python3 "$OWNER_GIT" worktree "$worktree" > /dev/null || exit $?
        local off=() worktree_git=()
        while IFS= read -r flag; do off+=("$flag"); done < <(python3 "$OWNER_GIT" attributes "$worktree")
        (( ${#off[@]} > 0 )) || die "no git call runs in $worktree without --attr-source: nothing was integrated"
        # The worktree reads config the main clone may not (config.worktree, an includeIf onbranch), so its hooks too.
        hardened_git "$worktree"
        worktree_git=("${GIT[@]}")
        hardened_git "$main_clone"
        status=$("${worktree_git[@]}" "${off[@]}" -C "$worktree" status --porcelain --ignore-submodules=all) || die "git status failed in $worktree"
        [[ -z "$status" ]] || refuse worktree-dirty "$worktree has uncommitted or untracked files: commit them on $branch, or remove them, first"
    fi
    take_message "$main_clone"

    local main_off=() tree merged
    while IFS= read -r flag; do main_off+=("$flag"); done < <(python3 "$OWNER_GIT" attributes "$main_clone")
    (( ${#main_off[@]} > 0 )) || die "no git call runs in $main_clone without --attr-source: nothing was integrated"
    if [[ "$main_sha" == "$base" ]]; then
        tree=$("${GIT[@]}" -C "$main_clone" rev-parse --verify "$tip^{tree}") || die "$tip has no tree: nothing integrated"
    else
        merged=$("${GIT[@]}" "${main_off[@]}" -C "$main_clone" merge-tree --write-tree --no-messages --merge-base="$base" "$main_sha" "$tip")
        case $? in
            0) tree=$(printf '%s\n' "$merged" | head -n 1) ;;
            1) refuse range-conflicts "$base..$branch conflicts with $main_branch ($main_sha): nothing integrated; rebase $branch onto $main_branch first" ;;
            *) die "merge-tree failed in $main_clone: nothing integrated" ;;
        esac
    fi

    local squash
    squash=$(printf '%s\n' "$message" | "${GIT[@]}" -C "$main_clone" commit-tree ${sign[@]+"${sign[@]}"} "$tree" -p "$main_sha" -F -) \
        || die "commit-tree failed: nothing integrated"
    "${GIT[@]}" -C "$main_clone" merge --ff-only --quiet "$squash" \
        || die "$main_branch did not fast-forward to $squash: nothing integrated, and $squash is unreferenced"
    echo "integrated: $squash on $main_branch in $main_clone" | show

    local accepted
    accepted=$(python3 -I -c '
import json, sys
from datetime import datetime, timezone
at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
print(json.dumps({"sha": sys.argv[1], "at": at, "base": sys.argv[2], "tip": sys.argv[3]}))
' "$squash" "$base" "$tip") || die "$squash is on $main_branch but its record could not be built; the dashboard reads this build as not accepted"
    if ! printf '%s\n' "$accepted" | python3 "$SESSION_WRITE" replace "$record"; then
        local rewrite
        printf -v rewrite "printf '%%s\\\\n' %q | python3 %q replace %q" "$accepted" "$SESSION_WRITE" "$record"
        die "$squash is on $main_branch but $record was not written; the dashboard reads this build as not accepted. Write it with: $rewrite"
    fi
    echo "recorded: $record" | show

    if [[ "$main_sha" == "$base" ]]; then
        echo "main at the base: $squash carries the tree of $branch at $tip" | show
    else
        local moved branch_id squash_id
        moved=$("${GIT[@]}" -C "$main_clone" rev-list --count "$base..$main_sha") || die "rev-list failed in $main_clone"
        echo "main moved: $moved commit$([[ "$moved" == 1 ]] || echo s) since $base" | show
        branch_id=$("${GIT[@]}" "${main_off[@]}" -C "$main_clone" diff-tree -p -U0 --no-ext-diff --no-textconv "$base" "$tip" \
            | "${GIT[@]}" -C "$main_clone" patch-id --stable | cut -d' ' -f1)
        squash_id=$("${GIT[@]}" "${main_off[@]}" -C "$main_clone" diff-tree -p -U0 --no-ext-diff --no-textconv "$main_sha" "$squash" \
            | "${GIT[@]}" -C "$main_clone" patch-id --stable | cut -d' ' -f1)
        if [[ -n "$branch_id" && "$branch_id" == "$squash_id" ]]; then
            echo "patch-id: same ($squash_id): the integrated diff is the branch's" | show
        else
            echo "patch-id: DIFFERENT ($main_branch ${squash_id:-none}, $branch ${branch_id:-none}): read git show $squash against the branch" | show
        fi
    fi

    echo "teardown is the Owner's; accept.sh never runs it:"
    if [[ -n "$worktree" ]]; then
        printf '  git -C %q worktree remove %q && git -C %q branch -D %q\n' "$main_clone" "$worktree" "$main_clone" "$branch"
    else
        printf '  git -C %q branch -D %q\n' "$main_clone" "$branch"
    fi
}

if $is_direct; then
    [[ ${#positionals[@]} -eq 2 ]] && $has_base || die "$USAGE"
    check_tip_form
    $has_message_file || refuse message-missing "accept.sh takes the squash message from a file: write it, then run $INSTALLED --direct --base $base --tip $expected_tip --message $(real_path "${positionals[0]}")/prs/${positionals[1]}/commit-message.txt ${positionals[0]} ${positionals[1]}"
    check_message_place "${positionals[0]}" "${positionals[1]}"
    read_message
    direct_accept "${positionals[0]}" "${positionals[1]}"
    exit 0
fi
[[ ${#positionals[@]} -eq 1 ]] && ! $has_base || die "$USAGE"
session_dir=${positionals[0]}
check_tip_form
$has_message_file || refuse message-missing "accept.sh takes the squash message from a file: write it, then run $INSTALLED --tip $expected_tip --message $(real_path "$session_dir")/prs/<unit>/commit-message.txt $session_dir"
check_message_place "$session_dir"
read_message
run_json="$session_dir/run.json"
[[ -f "$run_json" ]] || die "$run_json does not exist"

# One line each: phase, worktree, accepted.sha; a field that is not a string prints empty.
fields=$(python3 -I -c '
import json, sys
run = json.load(open(sys.argv[1]))
accepted = run.get("accepted") if isinstance(run.get("accepted"), dict) else {}
for value in (run.get("phase"), run.get("worktree"), accepted.get("sha")):
    print(value if isinstance(value, str) else "")
' "$run_json" 2>/dev/null) || die "$run_json is not readable JSON"
phase=$(printf '%s\n' "$fields" | sed -n 1p)
worktree=$(printf '%s\n' "$fields" | sed -n 2p)
accepted_sha=$(printf '%s\n' "$fields" | sed -n 3p)

[[ "$phase" == "done" ]] || refuse phase-not-done "run.json phase is '${phase:-preflight}': only a done session is accepted"
[[ -z "$accepted_sha" ]] || refuse already-accepted "run.json.accepted says $accepted_sha: this session is on main already"
[[ -f "$session_dir/INTAKE.md" ]] || refuse intake-missing "$session_dir/INTAKE.md does not exist: the Lead's intake comes before the accept"
[[ -d "$worktree" ]] || die "run.json.worktree '$worktree' is not a directory"

# owner_git.py prints its own refusal line and exits 2; the main clone is the configured repository.
checked=$(python3 "$OWNER_GIT" worktree "$worktree") || exit $?
worktree=$(printf '%s\n' "$checked" | sed -n 1p)
main_clone=$(printf '%s\n' "$checked" | sed -n 2p)
hardened_git "$worktree"
worktree_git=("${GIT[@]}")
hardened_git "$main_clone"
refuse_in_target "$main_clone"

branch=$("${worktree_git[@]}" -C "$worktree" symbolic-ref --short HEAD) || die "$worktree has no branch checked out"
main_branch=$("${GIT[@]}" -C "$main_clone" symbolic-ref --short HEAD) || die "$main_clone has no branch checked out"
main_sha=$("${GIT[@]}" -C "$main_clone" rev-parse --verify HEAD) || die "$main_clone has no commit on $main_branch"
tip=$("${GIT[@]}" -C "$main_clone" rev-parse --verify --end-of-options "$branch^{commit}") || die "$branch does not resolve in $main_clone"
check_tip_moved "$tip" "$branch"

"${GIT[@]}" -C "$main_clone" merge-base --is-ancestor "$main_sha" "$tip" \
    || refuse main-not-ancestor "$main_branch ($main_sha) is not an ancestor of $branch ($tip): the squash would revert what $main_branch gained since; rebase the session branch first"
status=$("${GIT[@]}" -C "$main_clone" status --porcelain --ignore-submodules=all) || die "git status failed in $main_clone"
[[ -z "$status" ]] || refuse main-dirty "$main_clone has uncommitted or untracked files: $main_branch fast-forwards only over a clean tree"

take_message "$main_clone"

squash=$(printf '%s\n' "$message" | "${GIT[@]}" -C "$main_clone" commit-tree ${sign[@]+"${sign[@]}"} "$tip^{tree}" -p "$main_sha" -F -) \
    || die "commit-tree failed: nothing integrated"
"${GIT[@]}" -C "$main_clone" merge --ff-only --quiet "$squash" \
    || die "$main_branch did not fast-forward to $squash: nothing integrated, and $squash is unreferenced"
echo "integrated: $squash on $main_branch in $main_clone" | show

python3 "$SESSION_STATE" "$session_dir" accept --head "$squash" \
    || die "$squash is on $main_branch but run.json.accepted was not written; apply: python3 $SESSION_STATE $session_dir accept --head $squash"

main_tree=$("${GIT[@]}" -C "$main_clone" rev-parse "HEAD^{tree}")
tip_tree=$("${GIT[@]}" -C "$main_clone" rev-parse "$tip^{tree}")
if [[ "$main_tree" == "$tip_tree" ]]; then
    echo "tree-identical: yes ($main_branch has $main_tree, the tree of $branch at $tip)" | show
else
    echo "tree-identical: NO ($main_branch has $main_tree, $branch at $tip has $tip_tree)" | show
    exit 1
fi

collect_unit_branches "$main_clone" "$branch" "$tip"
echo "teardown is the Owner's; accept.sh never runs it:"
printf '  git -C %q worktree remove %q' "$main_clone" "$worktree"
if (( ${#teardown_branches[@]} > 0 )); then
    printf ' && git -C %q branch -D' "$main_clone"
    printf ' %q' "${teardown_branches[@]}"
fi
printf '\n'
for kept in ${kept_branches[@]+"${kept_branches[@]}"}; do
    echo "kept: $kept holds a commit $branch at $tip lacks: read it before you delete it" | show
done
