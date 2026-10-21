#!/usr/bin/env bash
# Links every directory under skills/ and every *.md under agents/ into $HOME/.claude, and writes rw-git,
# the program a session runs outside its sandbox to write git, into $HOME/.local/bin as a wrapper file.
#
# Usage: install.sh [--uninstall]
#
# Each link is absolute and points into this clone. A second run prints nothing. A link that points into an earlier
# robowright clone is retargeted, and the `linked` line prints the target it replaced; any other link that points
# outside this clone, and anything that is not a symlink, is refused, and a refusal makes no link at all — every target
# is checked before the first `ln`.
# --uninstall removes only the links whose resolved target is inside this clone, and the rw-git wrapper whose exec
# line names this clone.
#
set -euo pipefail
shopt -s nullglob

# An exported CDPATH would send a relative `cd` elsewhere.
CLONE="$(CDPATH='' cd -P -- "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILLS_DIR="$HOME/.claude/skills"
AGENTS_DIR="$HOME/.claude/agents"
BIN_DIR="$HOME/.local/bin"
RW_GIT_SOURCE="$CLONE/skills/robowright/scripts/rw_git.py"
MAX_LINK_HOPS=40
RW_GIT_PYTHON=""

usage() {
    echo "usage: bash install.sh [--uninstall]" >&2
    exit 2
}

# Prints the absolute path a link chain ends at; bash 3.2 has no `readlink -f`.
resolve() {
    local path="$1" link dir hops=0
    while [ -L "$path" ] && [ "$hops" -lt "$MAX_LINK_HOPS" ]; do
        link="$(readlink "$path")"
        case "$link" in
            /*) path="$link" ;;
            *)  path="$(dirname "$path")/$link" ;;
        esac
        hops=$((hops + 1))
    done
    # `cd -P` resolves `..` on disk, after any symlinked component, not as text.
    if [ -d "$path" ]; then
        (cd -P "$path" && pwd -P)
        return
    fi
    dir="$(dirname "$path")"
    if [ -d "$dir" ]; then
        dir="$(cd -P "$dir" && pwd -P)"
    fi
    echo "$dir/$(basename "$path")"
}

is_inside_clone() {
    local resolved
    resolved="$(resolve "$1")"
    # A dangling path left unresolved may still carry `..`; it is never counted as inside.
    case "$resolved" in
        */..|*/../*) return 1 ;;
        "$CLONE"/*)  return 0 ;;
        *)          return 1 ;;
    esac
}

# The rw_git.py path a wrapper file's exec line names, or nothing when the file is not a wrapper.
wrapper_program() {
    python3 -I -c '
import shlex, sys
try:
    with open(sys.argv[1], encoding="utf-8") as wrapper:
        lines = wrapper.read().splitlines()
    words = shlex.split(lines[1]) if len(lines) == 2 and lines[0] == "#!/bin/sh -p" else []
except (OSError, UnicodeDecodeError, ValueError):
    words = []
if words[:3] == ["exec", "/usr/bin/env", "-i"] and "-I" in words and words[-1] == "$@":
    print(words[words.index("-I") + 1])
' "$1" 2>/dev/null || true
}

# True when the regular file $1 is a wrapper whose exec line names a program inside this clone.
is_own_wrapper() {
    local program
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    program="$(wrapper_program "$1")"
    [ -n "$program" ] && is_inside_clone "$program"
}

# One single-quoted sh word.
sh_quoted() {
    local quote="'" escaped="'\\''"
    printf "'%s'" "${1//$quote/$escaped}"
}

# True when $1, a resolved path, is <root>/$2/$3 and <root> holds install.sh and skills/robowright/SKILL.md as regular
# files, with no link on the way to either: an agent's resolved path does not pass through skills/.
is_in_earlier_clone() {
    local resolved="$1" kind="$2" name="$3" root
    [ "$(basename "$resolved")" = "$name" ] && [ "$(basename "$(dirname "$resolved")")" = "$kind" ] || return 1
    root="$(dirname "$(dirname "$resolved")")"
    [ -f "$root/install.sh" ] && [ ! -L "$root/install.sh" ] && [ ! -L "$root/skills" ] && [ ! -L "$root/skills/robowright" ] \
        && [ -f "$root/skills/robowright/SKILL.md" ] && [ ! -L "$root/skills/robowright/SKILL.md" ]
}

# Sets `refused` when a target holds anything that is not a symlink, or a live link that resolves outside this clone and
# outside an earlier robowright clone. A dangling link loses nothing, so it is retargeted. $2 is skills or agents.
refuse_target() {
    local target="$1" kind="$2" resolved
    if [ -L "$target" ]; then
        resolved="$(resolve "$target")"
        if [ -e "$resolved" ] && ! is_inside_clone "$target" \
            && ! is_in_earlier_clone "$resolved" "$kind" "$(basename "$target")"; then
            echo "install.sh: $target is a link to $resolved, outside this clone and not an earlier robowright clone; move it aside and run again" >&2
            refused=1
        fi
    elif [ -e "$target" ]; then
        echo "install.sh: $target exists and is not a symlink; move it aside and run again" >&2
        refused=1
    fi
}

# A retarget prints the link's old text through %q, so a control byte in it reaches the terminal escaped.
link_one() {
    local source="$1" target="$2" old
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
        return
    fi
    if [ -L "$target" ]; then
        old="$(readlink "$target")"
        rm "$target"
        ln -s "$source" "$target"
        printf 'linked %s (was %q)\n' "$target" "$old"
        return
    fi
    ln -s "$source" "$target"
    echo "linked $target"
}

# Source paths are passed as arguments, never serialised and re-parsed, so `|` or a newline in the clone path is safe.
# Sets RW_GIT_PYTHON, the interpreter write_rw_git pins, when this clone has rw_git.py.
refuse_unless_clean() {
    local refused=0 dir source probe kind dirs=("$SKILLS_DIR" "$AGENTS_DIR")
    if [ -f "$RW_GIT_SOURCE" ]; then
        dirs+=("$BIN_DIR")
        # A venv's .pth files run even under -I, so a venv's interpreter would run code its folder holds, as the Owner.
        probe="$(python3 -I -c 'import sys; print("venv" if sys.prefix != sys.base_prefix else "base"); print(sys.executable)')" \
            || probe=""
        kind="${probe%%$'\n'*}"
        RW_GIT_PYTHON="${probe#*$'\n'}"
        if [ "$kind" = "$probe" ] || [ -z "$RW_GIT_PYTHON" ]; then
            echo "install.sh: python3 printed no interpreter path; nothing was installed" >&2
            refused=1
        elif [ "$kind" != "base" ]; then
            echo "install.sh: $RW_GIT_PYTHON is a virtual environment's interpreter, refused for rw-git: deactivate the environment, or put the real python3 first on PATH, and run again" >&2
            refused=1
        fi
    fi
    for dir in "${dirs[@]}"; do
        if [ -L "$dir" ]; then
            echo "install.sh: $dir is a symlink; remove it and run: mkdir -p $dir" >&2
            refused=1
        elif [ -e "$dir" ] && [ ! -d "$dir" ]; then
            echo "install.sh: $dir is not a directory; move it aside and run again" >&2
            refused=1
        fi
    done
    for source in "$CLONE"/skills/*/; do
        source="${source%/}"
        refuse_target "$SKILLS_DIR/$(basename "$source")" skills
    done
    for source in "$CLONE"/agents/*.md; do
        [ -f "$source" ] || continue
        refuse_target "$AGENTS_DIR/$(basename "$source")" agents
    done
    if [ -f "$RW_GIT_SOURCE" ] && [ -e "$BIN_DIR/rw-git" ] && [ ! -L "$BIN_DIR/rw-git" ] \
        && ! is_own_wrapper "$BIN_DIR/rw-git"; then
        echo "install.sh: $BIN_DIR/rw-git exists and is not this clone's rw-git wrapper; move it aside and run again" >&2
        refused=1
    fi
    if [ "$refused" -ne 0 ]; then
        exit 1
    fi
}

install_links() {
    local source
    refuse_unless_clean
    mkdir -p "$SKILLS_DIR" "$AGENTS_DIR"
    for source in "$CLONE"/skills/*/; do
        source="${source%/}"
        link_one "$source" "$SKILLS_DIR/$(basename "$source")"
    done
    for source in "$CLONE"/agents/*.md; do
        [ -f "$source" ] || continue
        link_one "$source" "$AGENTS_DIR/$(basename "$source")"
    done
    write_rw_git
}

# rw-git runs as the Owner, outside every session's sandbox: whoever can write the folder it is found in, or a folder
# before it on PATH, chooses what runs. It is a file, not a link: `sh -p` reads no SHELLOPTS, PS4 or ENV, and `env -i`
# hands rw_git.py, run isolated by the interpreter found now, only PATH and HOME, so a caller's environment chooses
# nothing. The interpreter is the real one, never the /usr/bin/python3 shim, which execs $DEVELOPER_DIR's xcrun.
write_rw_git() {
    local wrapper temp
    [ -f "$RW_GIT_SOURCE" ] || return 0
    wrapper="$(printf '#!/bin/sh -p\nexec /usr/bin/env -i PATH=/usr/bin:/bin HOME=%s %s -I %s "$@"' \
        "$(sh_quoted "$HOME")" "$(sh_quoted "$RW_GIT_PYTHON")" "$(sh_quoted "$RW_GIT_SOURCE")")"
    if [ -f "$BIN_DIR/rw-git" ] && [ ! -L "$BIN_DIR/rw-git" ] && [ "$(cat "$BIN_DIR/rw-git")" = "$wrapper" ]; then
        return 0
    fi
    mkdir -p "$BIN_DIR"
    temp="$(mktemp "$BIN_DIR/.rw-git.XXXXXX")"
    printf '%s\n' "$wrapper" > "$temp"
    chmod 0755 "$temp"
    mv -f "$temp" "$BIN_DIR/rw-git"
    echo "wrote $BIN_DIR/rw-git"
    echo "rw-git: interpreter $RW_GIT_PYTHON"
    echo "rw-git: written into $BIN_DIR. Sessions run rw-git outside their sandbox, so no session may write $BIN_DIR, or any folder before it on PATH"
}

uninstall_links() {
    local dir entry
    if [ ! -L "$BIN_DIR" ] && { { [ -L "$BIN_DIR/rw-git" ] && is_inside_clone "$BIN_DIR/rw-git"; } \
        || is_own_wrapper "$BIN_DIR/rw-git"; }; then
        rm "$BIN_DIR/rw-git"
        echo "removed $BIN_DIR/rw-git"
    fi
    for dir in "$SKILLS_DIR" "$AGENTS_DIR"; do
        if [ -L "$dir" ] || [ ! -d "$dir" ]; then
            continue
        fi
        for entry in "$dir"/* "$dir"/.[!.]*; do
            if [ -L "$entry" ] && is_inside_clone "$entry"; then
                rm "$entry"
                echo "removed $entry"
            fi
        done
    done
}

case "$#:${1:-}" in
    0:)            install_links ;;
    1:--uninstall) uninstall_links ;;
    *)             usage ;;
esac
