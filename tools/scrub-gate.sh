#!/usr/bin/env bash
# Refuses added lines that match a denylist pattern.
#
#   scrub-gate.sh --cached              the index against HEAD (pre-commit)
#   scrub-gate.sh --range <old> <new>   every commit in <old>..<new> (pre-push); an all-zero
#                                       <old> means every commit not on any remote
#   scrub-gate.sh --tree                every tracked file as it is on disk; a symlink's text
#
# Denylist: ${ROBOWRIGHT_DENYLIST:-$HOME/.config/robowright/denylist}, one POSIX ERE per
# line, matched case-insensitively; `#` lines and blank lines are not patterns.
# A hit prints `scrub: <file>:<line>: denylist:<n>`, <n> the pattern's line in the denylist.
# A file name is matched too: a matching name is a hit at line 0 and prints as `(name withheld)`
# in every hit line.
# Exit 0 clean, 1 on any hit, 2 when the gate cannot run (no readable denylist, bad arguments,
# an unusable pattern, a file name holding a newline).

set -uo pipefail
# Byte-wise: under a UTF-8 locale awk dies on a byte that is not valid UTF-8. Patterns also run
# under the caller's locale, which folds non-ASCII case.
readonly caller_lc_all="${LC_ALL-}"
export LC_ALL=C

# Only the gate's own lines reach stderr, on fd 3: a tool's error or warning can name a withheld
# file or quote a pattern.
exec 3>&2 2> /dev/null

# A bash error exits 1 with its message on /dev/null; a hit exit sets `verdict` first.
on_exit() {
    [[ -n "${work-}" ]] && rm -rf "$work"
    if [[ $1 -eq 1 && "${verdict-}" != hit ]] || [[ $1 -gt 2 ]]; then
        echo "scrub: stopped on an internal error" >&3
        exit 2
    fi
}
work= verdict=; trap 'on_exit $?' EXIT

readonly ZERO_OID=0000000000000000000000000000000000000000

denylist="${ROBOWRIGHT_DENYLIST:-$HOME/.config/robowright/denylist}"
if [[ ! -e "$denylist" ]]; then
    echo "scrub: denylist not found: $denylist" >&3
    exit 2
fi
if [[ -d "$denylist" || ! -r "$denylist" ]]; then
    echo "scrub: denylist not readable: $denylist" >&3
    exit 2
fi

# Read once, here: `--tree` changes directory, and a relative path must name the caller's file.
patterns=()
pattern_lines=()
denylist_line=0
while IFS= read -r pattern || [[ -n "$pattern" ]]; do
    denylist_line=$((denylist_line + 1))
    pattern=${pattern%$'\r'}
    [[ "$pattern" =~ ^[[:space:]]*$ ]] && continue
    [[ "$pattern" =~ ^[[:space:]]*# ]] && continue
    patterns+=("$pattern")
    pattern_lines+=("$denylist_line")
done < "$denylist"

unreadable() {
    echo "scrub: could not read what was added" >&3
    exit 2
}

work=$(mktemp -d "${TMPDIR:-/tmp}/scrub-gate.XXXXXX") ||
    { echo "scrub: could not create a scratch directory" >&3; exit 2; }
# One added line per record: `$texts` holds the line, `$places` the matching `<line>\t<index>`,
# an index into `names`. A name never enters a record, so its characters cannot shift one.
texts="$work/texts"
places="$work/places"
# Every path the run matches as a name, one per line.
scope="$work/scope"
: > "$texts"
: > "$places"
: > "$scope"
names=()
newline_names=0

# Appends the NUL-separated names on stdin to `names` and the scope, counting those holding a
# newline.
add_names() {
    local name
    while IFS= read -r -d '' name; do
        names+=("$name")
        printf '%s\n' "$name" >> "$scope"
        [[ "$name" == *$'\n'* ]] && newline_names=$((newline_names + 1))
    done
}

# Reads a unified diff on stdin and records every added line with its new-side line number. Each
# section's file is the name on its own `+++ b/` line, unquoted; it is appended to the file $2,
# one per line, and numbered in `names` from $1. A deleted file's section (`+++ /dev/null`) adds
# no line. Nothing depends on the order or number of sections.
collect_added() {
    awk -v first="$1" -v section_names="$2" -v texts="$texts" -v places="$places" '
        # Undoes git quoting (core.quotePath=false): `"b/<name>"` with C escapes, and octal
        # escapes only for ASCII control bytes, so %c is safe.
        function unquote(s,   out, i, c) {
            out = ""
            for (i = 2; i <= length(s); i++) {
                c = substr(s, i, 1)
                if (c == "\"") { break }
                if (c != "\\") { out = out c; continue }
                c = substr(s, ++i, 1)
                if (c ~ /[0-7]/) {
                    out = out sprintf("%c", c * 64 + substr(s, i + 1, 1) * 8 + substr(s, i + 2, 1))
                    i += 2
                }
                else if (c == "a") { out = out "\007" }
                else if (c == "b") { out = out "\010" }
                else if (c == "t") { out = out "\t" }
                else if (c == "n") { out = out "\n" }
                else if (c == "v") { out = out "\013" }
                else if (c == "f") { out = out "\014" }
                else if (c == "r") { out = out "\r" }
                else { out = out c }
            }
            return out
        }
        BEGIN { file = -1 }
        /^diff --git / { in_header = 1; file = -1; next }
        in_header && /^\+\+\+ / {
            name = substr($0, 5)
            if (name == "/dev/null") { next }
            # An unquoted name holding a space ends in a tab git adds; a tab in a name is quoted.
            if (substr(name, 1, 1) == "\"") { name = unquote(name) } else { sub(/\t$/, "", name) }
            name = substr(name, 3)
            # A newline name is refused before any hit prints; this keeps the file one per line.
            gsub(/\n/, "?", name)
            print name > section_names
            file = first + sections++
            next
        }
        /^@@ / {
            in_header = 0
            split($3, new_side, ",")
            line = substr(new_side[1], 2) + 0
            next
        }
        in_header { next }
        /^\+/ {
            if (file >= 0) {
                print substr($0, 2) >> texts
                print line "\t" file >> places
            }
            line++
        }
    '
}

diff_added() {
    local name
    # Only a name the change adds or modifies can be reported; a deleted one is not counted.
    git diff --name-only -z --no-relative --no-renames --diff-filter=d "$@" > "$work/names" ||
        unreadable
    while IFS= read -r -d '' name; do
        printf '%s\n' "$name" >> "$scope"
        [[ "$name" == *$'\n'* ]] && newline_names=$((newline_names + 1))
    done < "$work/names"
    : > "$work/section-names"
    git -c core.quotePath=false diff -U0 --text --no-textconv --no-renames --no-ext-diff \
        --no-relative --no-color --submodule=short --src-prefix=a/ --dst-prefix=b/ "$@" |
        tr '\000' ' ' |
        collect_added "${#names[@]}" "$work/section-names" || unreadable
    while IFS= read -r name; do
        names+=("$name")
    done < "$work/section-names"
}

scan_commit() {
    local sha=$1 parent
    if parent=$(git rev-parse -q --verify "$sha^1"); then
        diff_added "$parent" "$sha"
    else
        diff_added "$(git hash-object -t tree /dev/null)" "$sha"
    fi
}

scan_range() {
    local old=$1 new=$2 sha
    if [[ "$new" == "$ZERO_OID" ]]; then
        return 0
    fi
    local -a exclude
    if [[ "$old" == "$ZERO_OID" ]] || ! git cat-file -e "$old^{commit}" 2>/dev/null; then
        exclude=(--not --remotes)
    else
        exclude=("^$old")
    fi
    local commits
    commits=$(git rev-list "$new" "${exclude[@]}") ||
        { echo "scrub: could not list the commits to check" >&3; exit 2; }
    for sha in $commits; do
        scan_commit "$sha"
    done
}

# A path that does not exist is absent only when its nearest existing directory can be searched;
# under one that cannot, the file may be there and unread.
is_absent() {
    local path=$1
    while [[ "$path" == */* ]]; do
        path=${path%/*}
        if [[ -e "$path" ]]; then
            [[ ! -d "$path" || -x "$path" ]]
            return
        fi
    done
    [[ -x . ]]
}

scan_tree() {
    local index name
    git ls-files -z > "$work/names" ||
        { echo "scrub: could not list the tracked files" >&3; exit 2; }
    add_names < "$work/names"
    for index in "${!names[@]}"; do
        name=${names[index]}
        if [[ ! -L "$name" && ! -f "$name" ]]; then
            [[ -e "$name" ]] || is_absent "$name" || unreadable
            continue
        fi
        # A symlink is read as the text git stores, never through to its target.
        if [[ -L "$name" ]]; then
            readlink -- "$name"
        else
            cat -- "$name"
        fi |
            tr '\000' ' ' |
            awk -v file="$index" -v texts="$texts" -v places="$places" '
                { print >> texts; print FNR "\t" file >> places }
            ' || unreadable
    done
}

case "${1:-}" in
    --cached) diff_added --cached ;;
    --range)
        if [[ $# -ne 3 ]]; then
            echo "usage: scrub-gate.sh --range <old> <new>" >&3
            exit 2
        fi
        scan_range "$2" "$3"
        ;;
    --tree)
        cd "$(git rev-parse --show-toplevel)" ||
            { echo "scrub: could not enter the top level of the repository" >&3; exit 2; }
        scan_tree
        ;;
    *)
        echo "usage: scrub-gate.sh --cached | --range <old> <new> | --tree" >&3
        exit 2
        ;;
esac

# A hit is one line; a name holding a newline cannot be reported on one.
if [[ $newline_names -gt 0 ]]; then
    echo "scrub: $newline_names file name(s) contain a newline; rename them" >&3
    exit 2
fi

# Writes `<record>:<line>` for every line of the file $2 matching $1 to $work/matched; grep's
# exit status.
match_pattern() {
    local pattern=$1 file=$2 locale status found=1
    : > "$work/matched"
    for locale in C "$caller_lc_all"; do
        # Another grep build may quote part of the pattern in its error message.
        LC_ALL=$locale grep -a -n -i -E -e "$pattern" "$file" >> "$work/matched" 2> /dev/null
        status=$?
        if [[ $status -gt 1 ]]; then
            return 2
        fi
        if [[ $status -eq 0 ]]; then
            found=0
        fi
    done
    return $found
}

# Refuses with exit 2 when pattern $1 is unusable; true when it matched a line of $2.
matches() {
    match_pattern "$1" "$2"
    local status=$?
    if [[ $status -gt 1 ]]; then
        echo "scrub: unusable pattern at denylist:$3" >&3
        exit 2
    fi
    return $status
}

# Nothing below prints a pattern: a hit or an error names its denylist line, `denylist:<n>`.
# Names first, so a matching name is known before any content hit could print it.
hits=0
withheld="$work/withheld"
name_hits="$work/name-hits"
: > "$withheld"
: > "$name_hits"
sort -u -o "$scope" "$scope"
for i in "${!patterns[@]}"; do
    matches "${patterns[i]}" "$scope" "${pattern_lines[i]}" || continue
    while IFS= read -r name; do
        printf '%s\n' "$name" >> "$withheld"
        echo "scrub: (name withheld):0: denylist:${pattern_lines[i]}" >> "$name_hits"
        hits=$((hits + 1))
    done < <(awk -F: 'NR == FNR { wanted[$1]; next } FNR in wanted' "$work/matched" "$scope")
done
cat "$name_hits"

# `is_withheld[index]` is set for every index into `names` whose name matched.
is_withheld=()
if [[ -s "$withheld" ]]; then
    # bash 3.2 under `set -u` calls an empty `names[@]` unbound.
    printf '%s\n' ${names[@]+"${names[@]}"} > "$work/all-names"
    while IFS= read -r index; do
        is_withheld[index]=1
    done < <(awk 'NR == FNR { wanted[$0]; next } $0 in wanted { print FNR - 1 }' \
        "$withheld" "$work/all-names")
fi

for i in "${!patterns[@]}"; do
    matches "${patterns[i]}" "$texts" "${pattern_lines[i]}" || continue
    while IFS=$'\t' read -r line index; do
        if [[ -n "${is_withheld[index]-}" ]]; then
            echo "scrub: (name withheld):$line: denylist:${pattern_lines[i]}"
        else
            echo "scrub: ${names[index]}:$line: denylist:${pattern_lines[i]}"
        fi
        hits=$((hits + 1))
    done < <(awk -F: 'NR == FNR { wanted[$1]; next } FNR in wanted' "$work/matched" "$places")
done

if [[ $hits -gt 0 ]]; then
    verdict=hit
    exit 1
fi
echo "scrub: clean"
