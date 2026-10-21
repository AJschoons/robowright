#!/usr/bin/env python3
"""
owner_git — how the Owner-side tools run git in a Robowright Session's worktree.

run.json.worktree is session-written, and accept.sh, the launcher, the dashboard, run-cost.py and
session-state.py run git inside it outside the sandbox. A worktree is accepted only when a
repository from the Owner's configuration lists it in `git worktree list`, compared by canonical
path, and its git common dir is that repository's. The configured repositories are those that
launch.json's `repos` lists and a project folder's robowright.json names in `repos[].path`, the
project folders being those one level under the projects root: $ROBOWRIGHT_PROJECTS_ROOT, else
launch.json's `projects_root`, as the dashboard reads it. launch.json is the Owner's and a
robowright.json may be a session's, so a robowright.json narrows `repos` and never widens it; with
no well-formed `repos`, no repository is trusted. Nothing under the sessions root counts. Nothing
runs inside an unlisted worktree; a listed one must have its own git dir, the repository's
`worktrees/<id>` entry that names it.

Every git call goes through `argv`, whose global options turn off what git would otherwise run
from its configuration on the commands these tools use: the fsmonitor, every hook, the pager,
and the signature check `log.showSignature` asks for. A config hook (`hook.<name>.*`, git 2.54)
runs whatever `core.hooksPath` says, so `argv` reads the repository's on every call and turns each
off by name with `--config-env`, whose variable `env` sets: `-c` splits at the first `=`, and a
name may hold one.

    owner_git.py worktree <path>   stdout: the worktree's canonical path, then its repository's;
                                   a refusal is `refused: <code>: <detail>` on stderr, exit 2:
                                   repos-unconfigured, worktree-unlisted or worktree-foreign-gitdir
    owner_git.py branch <name>     stdout: the one configured repository holding refs/heads/<name>, then the canonical
                                   worktree that has it checked out, or an empty line; a refusal, exit 2:
                                   branch-missing or branch-ambiguous
    owner_git.py flags <repo>      the global options for git in <repo>, one per line, for a shell caller's argv; then
                                   a line `--env` and the NAME=value lines the caller exports before its first git call
    owner_git.py show              stdin to stdout with every C0, DEL and C1 control but tab and newline dropped
"""

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

EXIT_REFUSED = 2
HARDENED = ("--no-pager", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "log.showSignature=false")
# The variable every --config-env option names, set in the environment of each git call.
CONFIG_ENV = {"OWNER_GIT_FALSE": "false"}
HOOK_KEY = re.compile(r"hook\.(.*)\.[^.]+")
# git 2.41.0 added --attr-source, and exports it to child processes as GIT_ATTR_SOURCE (release notes, git.c).
ATTR_SOURCE_SINCE = "2.41.0"
CONTROL_BYTES = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
# What a path call raises on bytes a session wrote: a NUL or a lone surrogate, and on Python 3.12 and older a
# long symlink chain, which realpath resolves one recursion per link.
PATH_ERRORS = (OSError, ValueError, RecursionError)
# Bytes read from an admin gitdir file at most: a path longer than this is not one git wrote.
ENTRY_LIMIT = 4096
# Bytes read_unlinked returns at most, as rw_git.MESSAGE_LIMIT.
READ_LIMIT = 64 * 1024
# O_NONBLOCK so a FIFO planted at the name refuses at once instead of waiting for a writer.
UNLINKED = os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
LAUNCH_JSON = ".claude/robowright/launch.json"
# A launch.json `repos` entry: absolute or `~/`, with no control byte.
REPO_ENTRY = re.compile(r"(/|~/)[^\x00-\x1f\x7f-\x9f]*")


class Unlisted(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class UnlistedDirectory(Unlisted):
    """check's refusal of a directory outside every listed worktree, when launch.json itself is not the reason."""


class Unreadable(Exception):
    """read_unlinked's refusal; the text is why."""


def shown(value) -> str:
    """Session-written text as printed to the Owner: no C0, DEL or C1 control, so no escape sequence reaches the terminal.
    A byte git printed that is not UTF-8 shows as U+FFFD."""
    text = str(value).encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    return CONTROL_BYTES.sub("", text)


def emit(stream, text: str):
    """UTF-8 to a standard stream whatever the locale's encoding, so a print never fails on what it prints; a path's
    undecodable bytes go out as they came in."""
    stream.flush()
    stream.buffer.write(text.encode("utf-8", "surrogateescape"))
    stream.buffer.flush()


def argv(cwd, *args, timeout=None) -> list:
    """git in `cwd` with HARDENED and every config hook there turned off; run it with `env()`."""
    return ["git", *HARDENED, *hooks_off(cwd, timeout), "-C", str(cwd), *args]


def env() -> dict:
    return dict(os.environ, **CONFIG_ENV)


def hooks_off(cwd, timeout=None) -> list:
    """`--config-env=hook.<name>.enabled=OWNER_GIT_FALSE` once for each config hook name the repository at `cwd`
    configures, read now: a session that can write its config can add one at any time."""
    done = subprocess.run(["git", *HARDENED, "-C", str(cwd), "config", "--null", "--get-regexp", r"^hook\."],
                          capture_output=True, env=env(), timeout=timeout, check=False)
    off = []
    for entry in done.stdout.split(b"\0") if done.returncode == 0 else []:
        found = HOOK_KEY.fullmatch(entry.partition(b"\n")[0].decode("utf-8", "surrogateescape"))
        option = f"--config-env=hook.{found.group(1)}.enabled=OWNER_GIT_FALSE" if found else None
        if option is not None and option not in off:
            off.append(option)
    return off


def run(cwd, *args, timeout=None) -> subprocess.CompletedProcess:
    # A path git prints may hold any byte a session wrote; surrogateescape keeps it without raising.
    return subprocess.run(argv(cwd, *args, timeout=timeout), capture_output=True, text=True, encoding="utf-8",
                          errors="surrogateescape", env=env(), timeout=timeout)


def home_path(value: str) -> str:
    """A configured path as the launcher reads it: a leading `~/` is $HOME, anything else as written."""
    return str(Path.home()) + value[1:] if value.startswith("~/") else value


def launch_json() -> Path:
    return Path.home() / LAUNCH_JSON


def projects_root():
    if os.environ.get("ROBOWRIGHT_PROJECTS_ROOT"):
        return os.path.expanduser(os.environ["ROBOWRIGHT_PROJECTS_ROOT"])
    try:
        settings = json.loads(launch_json().read_text())
    except (OSError, ValueError):
        return None
    root = settings.get("projects_root") if isinstance(settings, dict) else None
    return home_path(root) if isinstance(root, str) and root else None


def sessions_root():
    """$ROBOWRIGHT_SESSIONS_ROOT, else launch.json's `sessions_root`, canonical; None when neither names one."""
    if os.environ.get("ROBOWRIGHT_SESSIONS_ROOT"):
        return os.path.realpath(os.path.expanduser(os.environ["ROBOWRIGHT_SESSIONS_ROOT"]))
    try:
        settings = json.loads(launch_json().read_text())
    except (OSError, ValueError):
        return None
    root = settings.get("sessions_root") if isinstance(settings, dict) else None
    return os.path.realpath(home_path(root)) if isinstance(root, str) and root else None


def is_within(path: str, roots) -> bool:
    """`path` is one of `roots` or under one, compared as the same directory on disk, so letter case and links do not matter."""
    roots = [r for r in roots if r and os.path.isdir(r)]
    current = path
    while True:
        if any(os.path.exists(current) and os.path.samefile(current, r) for r in roots):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def allowed_repos() -> tuple:
    """(canonical paths launch.json's `repos` lists, None), or (None, why not). Any entry out of shape drops the whole
    list: a typo in the Owner's own file is refused by name rather than trusting a set the Owner did not write."""
    path = launch_json()
    try:
        settings = json.loads(path.read_text())
    except OSError as error:
        return None, f"{path} cannot be read ({error.strerror})"
    except ValueError:
        return None, f"{path} is not JSON"
    if not isinstance(settings, dict) or "repos" not in settings:
        return None, f"{path} has no `repos` key"
    entries = settings["repos"]
    if not isinstance(entries, list):
        return None, f"`repos` in {path} is not a list"
    for number, entry in enumerate(entries, 1):
        if not (isinstance(entry, str) and REPO_ENTRY.fullmatch(entry)):
            return None, f"`repos` entry {number} in {path} ({shown(json.dumps(entry))}) is not an absolute or ~/ path"
    return [os.path.realpath(home_path(entry)) for entry in entries], None


def excluded(sessions=None) -> list:
    """The sessions roots: the one the environment or launch.json names, and `sessions`, one a caller was given another way."""
    return [sessions_root(), os.path.realpath(sessions) if sessions else None]


def named_repos(root=None, sessions=None) -> list:
    """(as written, canonical) for every existing `repos[].path` in a robowright.json one level under the projects root,
    outside every sessions root. These are session-writable: only what `repos` also lists is trusted."""
    root = projects_root() if root is None else root
    if root is None:
        return []
    sessions = excluded(sessions)
    try:
        real_root = os.path.realpath(root)
        folders = sorted(Path(root).iterdir())
    except PATH_ERRORS:
        return []
    named = []
    for folder in folders:
        if is_within(os.path.realpath(folder), sessions):
            continue
        try:
            settings = json.loads(read_unlinked(os.path.join(real_root, folder.name, "robowright.json")))
        except (*PATH_ERRORS, Unreadable):
            continue
        entries = settings.get("repos") if isinstance(settings, dict) else None
        for entry in entries if isinstance(entries, list) else []:
            path = entry.get("path") if isinstance(entry, dict) else None
            if not (isinstance(path, str) and path):
                continue
            try:
                repo = os.path.realpath(home_path(path))
            except PATH_ERRORS:
                continue
            if os.path.isdir(repo) and not is_within(repo, sessions) and repo not in (r for _, r in named):
                named.append((path, repo))
    return named


def same_dir(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except PATH_ERRORS:
        return False


def configured_repos(root=None, sessions=None) -> list:
    """Canonical paths, as launch.json's `repos` spells them, of each repository `repos` lists and a robowright.json one
    level under the projects root names, compared as the same directory on disk. A sessions root is session-writable,
    so nothing in or under it is configuration, even a path `repos` lists."""
    allowed, _ = allowed_repos()
    if not allowed:
        return []
    sessions = excluded(sessions)
    repos = []
    for _, named in named_repos(root, sessions[1]):
        repo = next((a for a in allowed if same_dir(a, named)), None)
        if repo is not None and not is_within(repo, sessions) and repo not in repos:
            repos.append(repo)
    return repos


def untrusted(root=None, sessions=None):
    """(code, how to fix it) when no worktree of a repository is accepted for a reason the Owner fixes in launch.json:
    `repos` missing or out of shape, or a robowright.json naming a repository `repos` does not list. None otherwise."""
    allowed, why = allowed_repos()
    named = named_repos(root, sessions)
    if allowed is None:
        paths = [path for path, _ in named] or ["/path/to/your/repo"]
        return "repos-unconfigured", (f"{why}, so no repository is trusted. Add the repositories your projects' "
                                      f"robowright.json name, once you have checked each is yours, to {launch_json()}: "
                                      f'"repos": {shown(json.dumps(paths))}')
    unlisted = [path for path, repo in named if not any(same_dir(a, repo) for a in allowed)]
    if not unlisted:
        return None
    return "worktree-unlisted", (f"a robowright.json names {shown(json.dumps(unlisted))}, which `repos` in {launch_json()} "
                                 f"does not list. Add a path there only if that repository is yours: "
                                 f'"repos": {shown(json.dumps(allowed + unlisted))}')


def worktrees_of(repo: str) -> list:
    """[canonical path, the branch it has checked out or None] for every worktree `repo` lists, or [] if git cannot."""
    listing = worktree_listing(repo)
    return [] if listing is None else listing


def worktree_listing(repo: str):
    """worktrees_of's entries, or None when git cannot list the worktrees of `repo`."""
    try:
        found = run(repo, "worktree", "list", "--porcelain", "-z", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if found.returncode != 0:
        return None
    entries, current = [], None
    for field in found.stdout.split("\0"):
        if field.startswith("worktree "):
            # One entry a session made unresolvable drops that entry, not every worktree the repository lists.
            try:
                current = [os.path.realpath(field[len("worktree "):]), None]
            except PATH_ERRORS:
                current = None
                continue
            entries.append(current)
        elif field.startswith("branch refs/heads/") and current is not None:
            current[1] = field[len("branch refs/heads/"):]
    return entries


def listed_by(repo: str) -> list:
    return [path for path, _ in worktrees_of(repo)]


def index(repos=None) -> dict:
    """Every listed worktree's canonical path → the configured repository that lists it."""
    listed = {}
    for repo in configured_repos() if repos is None else repos:
        for path in listed_by(repo):
            listed.setdefault(path, repo)
    return listed


def branch_index(repos=None) -> dict:
    """Every branch a listed worktree has checked out → (that worktree's canonical path, the configured repository)."""
    branches = {}
    for repo in configured_repos() if repos is None else repos:
        for path, branch in worktrees_of(repo):
            if branch is not None:
                branches.setdefault(branch, (path, repo))
    return branches


def holder(name: str, repos=None) -> tuple:
    """(the one configured repository holding refs/heads/<name>, the canonical worktree that has it checked out or None),
    or Unlisted: branch-missing when none holds it or git cannot say for one or cannot list the holder's worktrees,
    branch-ambiguous when more than one does."""
    repos = configured_repos() if repos is None else repos
    held = []
    for repo in repos:
        try:
            found = run(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}", timeout=30)
        except (OSError, subprocess.SubprocessError):
            found = None
        if found is None or found.returncode not in (0, 1):
            raise Unlisted("branch-missing", f"git cannot say whether {repo} holds refs/heads/{shown(name)}")
        if found.returncode == 0:
            held.append(repo)
    if not held:
        hint = untrusted()
        detail = (f"no repository that `repos` in {launch_json()} lists and a robowright.json under the projects root "
                  f"names holds refs/heads/{shown(name)}")
        raise Unlisted("branch-missing", f"{detail}; {hint[1]}" if hint else detail)
    if len(held) > 1:
        raise Unlisted("branch-ambiguous", f"refs/heads/{shown(name)} is in {', '.join(held)}: accept it from one, after "
                                           f"deleting the branch from the others")
    listing = worktree_listing(held[0])
    if listing is None:
        raise Unlisted("branch-missing", f"git cannot list the worktrees of {held[0]}")
    worktree = next((path for path, branch in listing if branch == name), None)
    return held[0], worktree


def git_dirs(path: str):
    """(git dir, common dir) of a checkout, canonical, or None."""
    try:
        found = run(path, "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = found.stdout.splitlines()
    if found.returncode != 0 or len(lines) != 2:
        return None
    try:
        return tuple(os.path.realpath(line) for line in lines)
    except PATH_ERRORS:
        return None


def read_entry(path: str):
    """A session-written admin file's bytes, or None when it is a symlink, unreadable, or longer than ENTRY_LIMIT.
    Never waits on a FIFO."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except PATH_ERRORS:
        return None
    try:
        data = os.read(fd, ENTRY_LIMIT + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    return data if len(data) <= ENTRY_LIMIT else None


def read_unlinked(path) -> bytes:
    """`path`'s bytes, read as rw_git.message reads a message file, for a file a session can write: Unreadable unless
    it is absolute with no `.`, `..` or empty part, every folder is opened under the last with O_NOFOLLOW, and the
    name is a regular file with one link of at most READ_LIMIT bytes, opened so a FIFO never waits.
    FileNotFoundError when it is missing."""
    spelled = os.fspath(path)
    parts = spelled.split("/")
    if not spelled.startswith("/") or any(part in ("", ".", "..") for part in parts[1:]):
        raise Unreadable("not an absolute path without `.`, `..` or `//`")
    folder = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[1:-1]:
            inner = os.open(part, os.O_RDONLY | os.O_DIRECTORY | UNLINKED, dir_fd=folder)
            os.close(folder)
            folder = inner
        fd = os.open(parts[-1], os.O_RDONLY | UNLINKED, dir_fd=folder)
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as error:
        raise Unreadable(f"cannot be opened without following a link, or not a file "
                         f"({getattr(error, 'strerror', None) or error})") from None
    finally:
        os.close(folder)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Unreadable("not a regular file with one link")
        chunks, size = [], 0
        while size <= READ_LIMIT:
            chunk = os.read(fd, READ_LIMIT + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    finally:
        os.close(fd)
    if size > READ_LIMIT:
        raise Unreadable(f"longer than {READ_LIMIT} bytes")
    return b"".join(chunks)


def is_own_git_dir(path: str, repo: str) -> bool:
    """The checkout's git dir is the repository's: its common dir, or a worktrees/<id> entry there that names this checkout."""
    mine, theirs = git_dirs(path), git_dirs(repo)
    if mine is None or theirs is None or mine[1] != theirs[1]:
        return False
    git_dir, common = mine
    if git_dir == common:
        return path == os.path.realpath(repo)
    if os.path.dirname(git_dir) != os.path.join(common, "worktrees"):
        return False
    data = read_entry(os.path.join(git_dir, "gitdir"))
    if data is None:
        return False
    # The gitdir file is session-written: any byte in it that a path call cannot take reads as "names another".
    try:
        return os.path.realpath(os.path.dirname(os.fsdecode(data.strip()))) == path
    except PATH_ERRORS:
        return False


def check(worktree, listed=None) -> tuple:
    """(canonical worktree, its repository), or Unlisted. The listing is read before any git runs inside the worktree."""
    if not isinstance(worktree, str) or not worktree:
        raise Unlisted("worktree-unlisted", f"run.json.worktree is not a path ({shown(repr(worktree))})")
    try:
        path = os.path.realpath(worktree)
    except PATH_ERRORS:
        raise Unlisted("worktree-unlisted", f"run.json.worktree is not a path ({shown(repr(worktree))})") from None
    listed = index() if listed is None else listed
    repo = listed.get(path)
    if repo is None:
        detail = (f"'{shown(worktree)}' is not a worktree of a repository that `repos` in {launch_json()} lists and a "
                  f"robowright.json under the projects root names")
        hint = untrusted()
        if hint is None:
            raise UnlistedDirectory("worktree-unlisted", detail)
        raise Unlisted(hint[0], f"{detail}; {hint[1]}")
    # A listed path whose .git file names a git dir other than its own entry in the repository would run that
    # git dir's config. One hardened rev-parse runs inside the worktree to find out.
    if not is_own_git_dir(path, repo):
        raise Unlisted("worktree-foreign-gitdir", f"'{shown(worktree)}' is listed by {repo}, but its .git names "
                                                  f"a git directory other than its own entry in that repository")
    return path, repo


def no_attributes(repo: str):
    """git options under which nothing reads attributes from a checkout, its index or core.attributesFile, so no filter
    that session content names runs; None when this git has no --attr-source. The empty tree is the repository's own,
    SHA-1 or SHA-256."""
    tree = run(repo, "hash-object", "-t", "tree", "/dev/null", timeout=30)
    if tree.returncode != 0:
        return None
    flags = [f"--attr-source={tree.stdout.strip()}", "-c", "core.attributesFile=/dev/null"]
    return flags if run(repo, *flags, "check-attr", "--all", "--", "probe", timeout=30).returncode == 0 else None


def has_attr_source() -> bool:
    """Whether this git takes --attr-source, asked outside any repository: a git before it rejects the option."""
    tree = run("/", "hash-object", "-t", "tree", "/dev/null", timeout=30)
    return tree.returncode == 0 and run("/", f"--attr-source={tree.stdout.strip()}", "version", timeout=30).returncode == 0


def attributes_refusal() -> str:
    found = subprocess.run(["git", "version"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (f"{shown(found.stdout.strip() or 'this git')} cannot read attributes from a tree (--attr-source, added in git "
            f"{ATTR_SOURCE_SINCE}), so a checkout or status here would run filters session content names")


def main(args) -> int:
    if args == ["show"]:
        emit(sys.stdout, shown(sys.stdin.buffer.read().decode("utf-8", "replace")))
        return 0
    if len(args) == 2 and args[0] == "flags":
        # A hook name may hold any byte: printed as git gave it, so the off switch names that hook.
        lines = [*HARDENED, *hooks_off(args[1]), "--env", *(f"{k}={v}" for k, v in CONFIG_ENV.items())]
        sys.stdout.buffer.write("".join(f"{line}\n" for line in lines).encode("utf-8", "surrogateescape"))
        return 0
    if len(args) == 2 and args[0] == "worktree":
        try:
            path, repo = check(args[1])
        except Unlisted as refusal:
            emit(sys.stderr, f"refused: {refusal.code}: {refusal.detail}\n")
            return EXIT_REFUSED
        emit(sys.stdout, f"{path}\n{repo}\n")
        return 0
    if len(args) == 2 and args[0] == "branch":
        try:
            repo, worktree = holder(args[1])
        except Unlisted as refusal:
            emit(sys.stderr, f"refused: {refusal.code}: {refusal.detail}\n")
            return EXIT_REFUSED
        emit(sys.stdout, f"{repo}\n{worktree or ''}\n")
        return 0
    if len(args) == 2 and args[0] == "attributes":
        flags = no_attributes(args[1])
        if flags is None:
            emit(sys.stderr, f"refused: attributes-unsupported: {attributes_refusal()}\n")
            return EXIT_REFUSED
        print("\n".join(flags))
        return 0
    if args == ["attr-source"]:
        if not has_attr_source():
            emit(sys.stderr, f"refused: attributes-unsupported: {attributes_refusal()}\n")
            return EXIT_REFUSED
        return 0
    print("usage: owner_git.py worktree <path> | owner_git.py branch <name> | owner_git.py attributes <repo> | owner_git.py attr-source | "
          "owner_git.py flags <repo> | owner_git.py show", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
