#!/usr/bin/env python3
"""
role_grants — what a session the launcher or role-start.py starts may write, as the part of its --settings blob that
says so. Claude Code reads `permissions.additionalDirectories` for both the Bash sandbox and the file tools, so the shell
and Write/Edit agree; the working directory is the one other grant. Every configured repository's whole git directory
is denied to both, through `sandbox.filesystem.denyWrite` and an `Edit(...)` deny rule, because Claude Code's
linked-worktree rule opens the main clone's git directory to a Worker's shell, and an Owner's own settings may grant
wider. So is a leaf `<root>/**/.git` on each granted root, and on a committing role's worktree: a wildcard deny holds
only up to its first `**`, a leaf at any depth. A role that commits stages and commits through rw-git, which its
settings run outside the sandbox (`sandbox.excludedCommands`) and allow without a prompt (`permissions.allow`).

Every root is read from launch.json, never from the ROBOWRIGHT_* environment, and git runs with every GIT_* variable
removed: a Lead that runs the launcher sets its environment. Every root, grant and working directory must be absolute,
hold no `.` or `..`, and have no link at any prefix: a role that can write a root could otherwise put a link in it and
point a later session's grant anywhere, so no link is followed at all. Each component, and each `repos` entry's, must
be spelled as the disk names it, since the sandbox matches the string. Its spelling is then its place on disk, and
directories are compared by device and inode. No grant, and no working directory, may sit at or above the home
directory; nor at, above or inside a repository launch.json's `repos` lists, the launcher's own clone, or launch.json's
directory or its real one; nor inside any git checkout below the home directory that no root holds. Without a
well-formed `repos` nothing is granted.

    role_grants.py worker <session_dir> <worktree>   a Worker: its session folder, the accounting root and its run.json
                                                     locks' directories
    role_grants.py document [<cwd>]                  a Planner or an Explainer: the projects root and the sessions root,
                                                     never a project folder's Claude settings
    role_grants.py checkouts <session_dir>           make each depends_on checkout the Worker's preflight would, on the
                                                     Owner's side: its admin dir is named by git, so no grant can name it
    role_grants.py worktree <session_dir> plan|make  make run.json's missing worktree, or say how a launch would: the
                                                     Lead's sandbox cannot write the repository's git directory
    role_grants.py direct <project> <repo> <slug> <base> <briefing> plan|make|grants
                                                     the same for a direct build, which has no run.json, from argv held
                                                     to the same checks; `grants` prints document's fragment once the
                                                     worktree, if it exists, is the build's

stdout: the settings fragment, JSON, or one line per checkout or worktree. A refusal is `refused: <detail>` on stderr,
exit 2.
"""

import json
import os
import re
import stat
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import owner_git  # noqa: E402
import session_write  # noqa: E402

EXIT_REFUSED = 2
# The launcher's lock-name check: a name becomes one path segment under the sessions root.
LOCK_NAME = re.compile(r"[a-z0-9-]+")
# The launcher's TICKET_FORM: a depends_on session, or a session folder's name, becomes one path segment.
SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# run-cost.py's COMMIT_ID without HEAD: a depends_on ref reaches `git worktree add`.
COMMIT = re.compile(r"[0-9a-f]{7,40}")
# A base a new branch starts from: the full id, so it can never come to name another object.
FULL_COMMIT = re.compile(r"[0-9a-f]{40}")
# A direct build's briefing file name: one segment, so the prompt that names it carries no other text.
BRIEFING = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md")
CLONE = Path(os.path.realpath(__file__)).parents[3]
# Denied names that are folders, so their deny rule covers what is inside.
DENIED_FOLDERS = (".git", ".claude")
# A leaf deny on a root: every `.git` under it at any depth, a worktree's .git file as well as a folder. The wildcard is
# honoured by the macOS sandbox only.
LEAF = "/**/.git"
# What a role that commits runs outside its sandbox: the one program that writes a repository's git directory for it.
COMMITS = ("rw-git *",)
# What Claude Code loads as project settings from the folder a session starts in, and runs hooks and servers from
# outside the sandbox. The sandbox protects only the working directory's own and those above it.
PROJECT_CONFIGS = (".claude", ".mcp.json")
HOME = "the home directory"
# The project hook's Worktree and Naming conventions: <repo>/.worktrees/<slug> on robowright/<slug>, the slug being the
# session folder's name.
WORKTREES = "/.worktrees/"
# The main checkout's exclude line for the folder worktrees are made in, so its status stays clean for accept.sh.
EXCLUDED = "/.worktrees/"
BRANCH_PREFIX = "robowright/"


class Refused(Exception):
    pass


def git(fn, *args):
    """owner_git's `fn` with no GIT_* variable in the environment, so git reads the repository it is pointed at."""
    saved = {name: os.environ.pop(name) for name in [n for n in os.environ if n.startswith("GIT_")]}
    try:
        return fn(*args)
    finally:
        os.environ.update(saved)


def launch_config() -> dict:
    path = owner_git.launch_json()
    try:
        config = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise Refused(f"{path} cannot be read as JSON ({error})") from None
    if not isinstance(config, dict):
        raise Refused(f"{path} is not a JSON object")
    return config


def spelled(config: dict, key: str):
    """A launch.json path as written, `~/` expanded, or None when the key is absent."""
    value = config.get(key)
    if value is None:
        return None
    if not (isinstance(value, str) and owner_git.REPO_ENTRY.fullmatch(value)):
        raise Refused(f"`{key}` in {owner_git.launch_json()} is not an absolute or ~/ path")
    return owner_git.home_path(value)


def spelled_sessions(config: dict) -> str:
    sessions = spelled(config, "sessions_root")
    if sessions is None:
        raise Refused(f"{owner_git.launch_json()} names no `sessions_root`")
    return sessions


def spelled_accounting(config: dict) -> str:
    """run-cost.py's default without its environment: launch.json's `accounting_root`, else `accounting` beside the sessions root."""
    return spelled(config, "accounting_root") or os.path.join(os.path.dirname(spelled_sessions(config).rstrip("/")), "accounting")


def roots(config: dict) -> list:
    """Every root a role may be granted, as spelled: a checkout one of them holds is the Owner's own."""
    return [r for r in (spelled(config, "projects_root"), spelled_sessions(config), spelled_accounting(config)) if r]


def unlinked(name: str, path: str) -> str:
    """`path` once it is absolute, holds no `.` or `..`, and has no link at any prefix and no component spelled other
    than the disk names it, `//` and a trailing `/` dropped; else Refused naming the path and the component. The sandbox
    matches the string, so it must be the one the kernel reports. What does not exist yet cannot be a link now, and a
    link put there later is refused at the next launch."""
    if not path.startswith("/"):
        raise Refused(f"the {name} {path} is not an absolute path")
    parts = [part for part in path.split("/") if part]
    dots = next((part for part in parts if part in (".", "..")), None)
    if dots is not None:
        raise Refused(f"the {name} {path} holds a `{dots}` component; name the real path instead")
    current = ""
    for part in parts:
        current += "/" + part
        try:
            mode = os.lstat(current).st_mode
        except (FileNotFoundError, NotADirectoryError):
            break
        except owner_git.PATH_ERRORS as error:
            raise Refused(f"the {name} {path} cannot be checked at {current} ({error})") from None
        if stat.S_ISLNK(mode):
            raise Refused(f"the {name} {path} is refused: {current} is a link; name the real path instead, which no "
                          f"link leads to")
        disk = disk_name(current)
        if disk != part:
            raise Refused(f"the {name} {path} is spelled {part} at {current}, but the disk names it {disk}; name it as "
                          f"on disk")
    return "/" + "/".join(parts)


def disk_name(path: str) -> str:
    """The name the parent directory holds for the entry `path` reaches, which a case- or form-insensitive volume may
    spell differently."""
    parent, part = os.path.split(path)
    try:
        names = os.listdir(parent)
        if part in names:
            return part
        found = os.lstat(path)
        return next(n for n in names if os.lstat(os.path.join(parent, n))[:2] == found[:2])
    except (StopIteration, *owner_git.PATH_ERRORS) as error:
        raise Refused(f"{path} cannot be checked against its directory's listing ({error})") from None


def identity(path: str):
    """(device, inode) of the directory `path` names, or None: letter case and Unicode form never matter."""
    try:
        found = os.stat(path)
    except owner_git.PATH_ERRORS:
        return None
    return found.st_dev, found.st_ino


def lineage(path: str) -> list:
    """The identity of `path` and of every directory above it that exists, walking its spelling upward."""
    found = []
    current = path
    while True:
        here = identity(current)
        if here is not None:
            found.append(here)
        parent = os.path.dirname(current)
        if parent == current:
            return found
        current = parent


def above(path: str) -> list:
    """Identities of the directories whose writer can change what an Owner's `path` names: the one it names and those
    above it, and those above each link its spelling passes through."""
    found = lineage(os.path.realpath(path))
    current = ""
    for part in [part for part in path.split("/") if part]:
        current += "/" + part
        if os.path.islink(current):
            found += lineage(os.path.realpath(os.path.dirname(current)))
    return found


# A character the sandbox or a permission rule reads as a pattern: a grant spelled with one is skipped.
GLOB = re.compile(r"[*?\[\]{}]")
EDIT_DENY = re.compile(r"Edit(?:\((.*)\))?")
# The glob shapes a deny is matched by: `**` as a whole segment, any number of segments; `*`, within one segment.
UNMATCHED_GLOB = re.compile(r"[?\[\]{}]")
SETTINGS_LIMIT = 1 << 20


def desktop_grants(config: dict, home: str) -> tuple:
    """(granted folders, denied folders) for a checkout no `repos` entry lists: launch.json's `desktop_roots`, then the
    `sandbox.filesystem.allowWrite` and `permissions.additionalDirectories` of the account's own
    `<home>/.claude/settings.json`, read through its link. Denied: every `denyWrite` and `Edit(…)` deny there and in
    each granted folder's `.claude/settings.json`. A settings grant with a glob, a relative path or a link at any prefix
    is skipped, and every settings grant when the settings file lies under a granted folder; a deny is matched as its
    glob (deny_pattern); a deny in a glob shape it cannot match, a settings file that exists but cannot be read, and a
    bad `desktop_roots` entry are Refused, by name.
    A grant made for one session only is invisible here."""
    roots = list(desktop_roots(config))
    settings_file = os.path.realpath(os.path.join(home, ".claude", "settings.json"))
    settings = settings_of(settings_file) if os.path.lexists(settings_file) else {}
    from_settings = []
    for entry in [*setting_list(settings, "sandbox", "filesystem", "allowWrite"),
                  *setting_list(settings, "permissions", "additionalDirectories")]:
        path = grant_path(entry, home)
        if path is None:
            continue
        try:
            from_settings.append(unlinked("granted folder", path))
        except Refused:
            continue
    # A settings file a session could write grants nothing: its grants are skipped, its denies still count.
    writable = any(is_under(settings_file, folder) for folder in roots + from_settings)
    granted = roots if writable else roots + from_settings
    # Claude Code opens the file at ~/.claude; through a link, its relative denies are read from both folders.
    bases = dict.fromkeys((os.path.join(home, ".claude"), os.path.dirname(settings_file)))
    denied = [path for base in bases for path in denies_of(settings, base, home, "/")]
    for folder in granted:
        local = os.path.join(folder, ".claude", "settings.json")
        denied += denies_of(settings_of(local), folder, home, folder) if os.path.lexists(local) else []
    return granted, denied


def desktop_roots(config: dict) -> list:
    """launch.json's `desktop_roots`, each absolute after `~/`, with no glob and no link at any prefix."""
    value = config.get("desktop_roots")
    if value is None:
        return []
    if not isinstance(value, list):
        raise Refused(f"`desktop_roots` in {owner_git.launch_json()} is not a list of folders")
    found = []
    for entry in value:
        if not (isinstance(entry, str) and owner_git.REPO_ENTRY.fullmatch(entry)) or GLOB.search(entry):
            raise Refused(f"the `desktop_roots` entry {owner_git.shown(repr(entry))} in {owner_git.launch_json()} is not "
                          f"an absolute or ~/ path without a glob")
        found.append(unlinked("`desktop_roots` entry", owner_git.home_path(entry)))
    return found


def settings_of(path: str) -> dict:
    """A settings file that exists, as a JSON object: a regular file, its link followed, of at most SETTINGS_LIMIT
    bytes, opened without waiting on a FIFO; else Refused, since its denies would be lost."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as error:
        raise Refused(f"{path} cannot be opened ({error}), so its denies are unknown") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Refused(f"{path} is not a regular file, so its denies are unknown")
        data = os.read(fd, SETTINGS_LIMIT + 1)
    except OSError as error:
        raise Refused(f"{path} cannot be read ({error}), so its denies are unknown") from None
    finally:
        os.close(fd)
    try:
        found = json.loads(data) if len(data) <= SETTINGS_LIMIT else None
    except ValueError as error:
        raise Refused(f"{path} cannot be read as JSON ({error}), so its denies are unknown") from None
    if not isinstance(found, dict):
        raise Refused(f"{path} is not a JSON object of at most {SETTINGS_LIMIT} bytes, so its denies are unknown")
    return found


def setting_list(settings: dict, *keys) -> list:
    value = settings
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []


def grant_path(entry: str, home: str):
    """An absolute grant as the sandbox reads it, or None for one spelled relative or with a glob."""
    if GLOB.search(entry):
        return None
    if entry == "~" or entry.startswith("~/"):
        return os.path.normpath(home + entry[1:])
    if entry.startswith("/"):
        return os.path.normpath("/" + entry.lstrip("/"))
    return None


def denies_of(settings: dict, base: str, home: str, anywhere: str) -> list:
    """Every folder or pattern a `denyWrite` entry or an `Edit` deny names: a `/` path both absolute and from `base`, a
    relative one from `base`, a relative `Edit` rule at any depth below `anywhere`, and `Edit` alone all of `anywhere`."""
    found = []
    for entry in setting_list(settings, "sandbox", "filesystem", "denyWrite"):
        found += deny_paths(entry, base, home, base)
    for rule in setting_list(settings, "permissions", "deny"):
        matched = EDIT_DENY.fullmatch(rule.strip())
        if matched is not None:
            entry = matched.group(1)
            if not entry:
                found.append(anywhere)
                continue
            found += deny_paths(entry, base, home, anywhere)
            if not (entry.startswith("/") or entry == "~" or entry.startswith("~/")):
                # Claude Code reads a relative rule from the session's working directory, which may be any folder below.
                found += deny_paths(re.sub(r"^(?:\.\.?/)+", "", entry), base, home, anywhere.rstrip("/") + "/**")
    return found


def deny_paths(entry: str, base: str, home: str, relative_root: str) -> list:
    if entry == "~" or entry.startswith("~/"):
        spelled = [home + entry[1:]]
    elif entry.startswith("/"):
        spelled = ["/" + entry.lstrip("/"), base + "/" + entry.lstrip("/")]
    else:
        spelled = [relative_root + "/" + entry]
    found = []
    for path in spelled:
        parts = [part for part in path.split("/") if part and part != "."]
        literal = next((i for i, part in enumerate(parts) if "*" in part or UNMATCHED_GLOB.search(part)), len(parts))
        head = "/" + "/".join(parts[:literal])
        for folder in dict.fromkeys((os.path.normpath(head), os.path.realpath(head))):
            found.append("/".join([folder.rstrip("/"), *parts[literal:]]) or "/")
    for pattern in found:
        deny_pattern(pattern)
    return found


def deny_pattern(pattern: str):
    """A deny with a glob as a pattern over a whole path: `**` as a segment is any number of segments, none included,
    and `*` any run within one segment. Any other glob shape is Refused by name: a deny is never widened or skipped."""
    if "*" not in pattern and not UNMATCHED_GLOB.search(pattern):
        return None
    regex = ""
    for part in [part for part in pattern.split("/") if part]:
        if UNMATCHED_GLOB.search(part) or ("**" in part and part != "**"):
            raise Refused(f"the deny {owner_git.shown(pattern)} uses a glob rw-git does not match ({part}); write it "
                          f"with `**` segments and `*` only")
        regex += r"(?:/[^/]+)*" if part == "**" else "/" + "[^/]*".join(re.escape(piece) for piece in part.split("*"))
    return re.compile(regex)


def is_under(path: str, folder: str) -> bool:
    return folder == "/" or path == folder or path.startswith(folder.rstrip("/") + "/")


def folded(path: str) -> str:
    """`path` with letter case and Unicode form taken out, as a case- and form-insensitive volume compares names."""
    return unicodedata.normalize("NFD", unicodedata.normalize("NFD", path).casefold())


def is_denied(path: str, denied: list) -> bool:
    """`path`, or a folder above it, matches a denied pattern, or lies under a denied folder, as written or in any
    letter case or Unicode form: a deny spelled otherwise than the disk still names the folder."""
    # Folding reorders combining marks across a `*`, so a deny that matched as written could stop matching folded.
    return any(denies(path, entry) or denies(folded(path), folded(entry)) for entry in denied)


def denies(path: str, entry: str) -> bool:
    pattern = deny_pattern(entry)
    if pattern is None:
        return is_under(path, entry)
    current = path
    while True:
        if pattern.fullmatch(current):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def desktop_repo(path: str, config: dict, home: str):
    """The main checkout of the repository whose checkout holds the canonical `path`, when it lies under a granted
    folder and under no denied one, and `path` lies under no denied one; else None."""
    repo = main_checkout(path)
    if repo is None:
        return None
    granted, denied = desktop_grants(config, home)
    if not any(is_under(repo, folder) for folder in granted):
        return None
    if any(is_denied(place, denied) for place in (repo, path)):
        return None
    return repo


def main_checkout(path: str):
    """The canonical main checkout above `path`: the nearest folder holding a `.git` folder, or, for a `.git` file, the
    checkout whose `.git/worktrees/<id>` it names. Read without git, and checked by owner_git afterwards."""
    current = path
    while True:
        dot_git = os.path.join(current, ".git")
        try:
            mode = os.lstat(dot_git).st_mode
        except FileNotFoundError:
            mode = None
        except owner_git.PATH_ERRORS:
            return None
        if mode is not None:
            if stat.S_ISDIR(mode):
                return current
            data = owner_git.read_entry(dot_git) if stat.S_ISREG(mode) else None
            if data is None or not data.startswith(b"gitdir: "):
                return None
            try:
                named = os.path.realpath(os.fsdecode(data[len(b"gitdir: "):].strip()))
            except owner_git.PATH_ERRORS:
                return None
            entries = os.path.dirname(named)
            if os.path.basename(entries) != "worktrees" or os.path.basename(os.path.dirname(entries)) != ".git":
                return None
            return os.path.dirname(os.path.dirname(entries))
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def repos() -> list:
    allowed, why = owner_git.allowed_repos()
    if allowed is None:
        raise Refused(f"{why}, so nothing marks a clone protected and no write is granted")
    return [unlinked("repository", repo) for repo in allowed]


def spelled_repos() -> list:
    """Each `repos` entry as launch.json spells it, `~/` expanded, so a link in the spelling is protected too."""
    repos()
    return [owner_git.home_path(entry) for entry in launch_config()["repos"]]


def common_dir(repo: str):
    """The repository's shared git directory, or None when it is no git checkout. A main clone's is named from its .git
    on disk, since git's own report follows a commondir the shell can write there."""
    dot_git = os.path.join(repo, ".git")
    if os.path.isdir(dot_git):
        common = os.path.realpath(dot_git)
        if os.path.lexists(os.path.join(common, "commondir")):
            raise Refused(f"{common}/commondir exists, so git reads another directory's config and hooks for {repo}; "
                          f"remove it")
        return common
    if os.path.lexists(dot_git):
        dirs = git(owner_git.git_dirs, repo)
        if dirs is None:
            raise Refused(f"git cannot name the git directory of the repository {repo}, so nothing in it can be denied")
        return dirs[1]
    return None


def git_dir(repo: str) -> list:
    """The repository's whole git directory, or [] when it is no git checkout."""
    common = common_dir(repo)
    return [] if common is None else [common]


def checkout_holding(path: str, owned: list):
    """The git checkout below the home directory that holds `path`, unless a directory in `owned` holds that checkout."""
    home = lineage(os.path.realpath(Path.home()))
    current = path
    while True:
        here = identity(current)
        if here is not None:
            if here in home:
                return None
            if os.path.lexists(os.path.join(current, ".git")) and not any(o in lineage(current) for o in owned):
                return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def check(grants: list, protected: list, config: dict, working=()):
    """Refuse any (name, path) grant or working directory at or above a protected path, or inside one but the home
    directory, or inside a git checkout no root or grant holds: a projects root versioned with git is the Owner's own.
    Every grant and working directory has passed unlinked(), so its spelling walks its real ancestors."""
    owned = [i for i in (identity(path) for path in roots(config) + [grant for _, grant in grants]) if i]
    for name, grant in list(grants) + list(working):
        mine, line = identity(grant), lineage(grant)
        for what, path in protected:
            if not path:
                continue
            if mine is not None and mine in above(path):
                raise Refused(f"the {name} {grant} is at or above {what} {path}; a session granted it could write that")
            if what != HOME and identity(path) in line:
                raise Refused(f"the {name} {grant} is inside {what} {path}; a session granted it could write that")
        holder = checkout_holding(grant, owned)
        if holder:
            raise Refused(f"the {name} {grant} is inside the git checkout {holder}; a session granted it could write that")


def protected_paths(extra=()) -> list:
    launch = owner_git.launch_json()
    return ([(HOME, str(Path.home())),
             ("the launcher's own clone", str(CLONE)),
             ("launch.json's directory", str(launch.parent)),
             ("launch.json's real directory", os.path.dirname(os.path.realpath(launch)))]
            + [("the repository", repo) for repo in spelled_repos()] + list(extra))


def fragment(grants: list, denied: list, commits=False) -> dict:
    """The --settings keys: the grants for both mechanisms, each denied path and a leaf on each grant to the shell and
    the file tools, and for a role that commits, rw-git run outside the sandbox."""
    denied = denied + [path + LEAF for _, path in grants]
    rules = []
    for path in denied:
        if path.endswith(LEAF):
            rules.append(f"Edit(/{path})")
        is_folder = os.path.basename(path) in DENIED_FOLDERS or os.path.isdir(path)
        rules.append(f"Edit(/{path}/**)" if is_folder else f"Edit(/{path})")
    permissions = {"additionalDirectories": [path for _, path in grants], "deny": rules}
    sandbox = {"filesystem": {"denyWrite": denied}}
    if commits:
        # An excluded command goes through the regular permission flow: unallowed, it would stop an unattended role.
        permissions["allow"] = [f"Bash({command})" for command in COMMITS]
        sandbox["excludedCommands"] = list(COMMITS)
    return {"permissions": permissions, "sandbox": sandbox}


def denied_paths(extra_repos=()) -> list:
    denied = []
    for repo in list(extra_repos) + repos():
        denied += [path for path in git_dir(repo) if path not in denied]
    return denied


def project_configs(projects: str) -> list:
    """The project settings of the projects root and of each folder in it, named so every sandbox honours them, and of
    any folder made later, through a wildcard only the macOS sandbox honours."""
    try:
        names = sorted(os.listdir(projects))
    except FileNotFoundError:
        names = []
    except owner_git.PATH_ERRORS as error:
        raise Refused(f"the projects root {projects} cannot be listed ({error})") from None
    folders = [projects] + [os.path.join(projects, n) for n in names
                            if not n.startswith(".") and stat.S_ISDIR(os.lstat(os.path.join(projects, n)).st_mode)]
    return ([os.path.join(folder, name) for folder in folders for name in PROJECT_CONFIGS]
            + [os.path.join(projects, "**", name) for name in PROJECT_CONFIGS])


def document(with_accounting: bool, cwd=None, worktree=None) -> dict:
    """A role that plans or explains: the projects root when launch.json names one, the sessions root, and for a role
    started by hand the accounting root its shell writes cost records to. `cwd`, where it starts, is held to the same rule.
    With `worktree`, a direct build that starts and commits there: a leaf on it, and rw-git outside the sandbox."""
    config = launch_config()
    grants = []
    projects = spelled(config, "projects_root")
    if projects is not None:
        grants.append(("projects root", unlinked("projects root", projects)))
    grants.append(("sessions root", unlinked("sessions root", spelled_sessions(config))))
    if with_accounting:
        grants.append(("accounting root", unlinked("accounting root", spelled_accounting(config))))
    working = [("working directory", unlinked("working directory", cwd))] if cwd else []
    check(grants, protected_paths(), config, working)
    denied = denied_paths() + (project_configs(grants[0][1]) if projects is not None else [])
    if worktree is None:
        return fragment(grants, denied)
    built = fragment(grants, denied, commits=True)
    leaf = worktree + LEAF
    built["sandbox"]["filesystem"]["denyWrite"].append(leaf)
    built["permissions"]["deny"] += [f"Edit(/{leaf})", f"Edit(/{leaf}/**)"]
    return built


def run_json(session_dir: str) -> dict:
    try:
        with open(os.path.join(session_dir, "run.json")) as handle:
            run = json.load(handle)
    except (OSError, ValueError) as error:
        raise Refused(f"{session_dir}/run.json cannot be read ({error})") from None
    if not isinstance(run, dict):
        raise Refused(f"{session_dir}/run.json is not a JSON object")
    return run


def lock_grants(run: dict, config: dict) -> list:
    locks = run.get("locks") or []
    if not (isinstance(locks, list) and all(isinstance(n, str) and LOCK_NAME.fullmatch(n) for n in locks)):
        raise Refused("run.json locks is not a list of lock names")
    sessions = unlinked("sessions root", spelled_sessions(config))
    return [("lock directory", unlinked("lock directory", f"{sessions}/.{name}-lock")) for name in locks]


def dependencies(run: dict) -> list:
    """(session, repository, ref) per depends_on entry. run.json is session-written, so the path must be a repository
    launch.json lists, the session one path segment and the ref a commit id."""
    entries = run.get("depends_on") or []
    if not isinstance(entries, list):
        raise Refused("run.json depends_on is not a list")
    found = []
    for entry in entries:
        session, path, ref = (entry.get(k) if isinstance(entry, dict) else None for k in ("session", "path", "ref"))
        if not (isinstance(session, str) and SEGMENT.fullmatch(session)):
            raise Refused(f"run.json depends_on session {owner_git.shown(json.dumps(session))} is not one path segment")
        if not (isinstance(ref, str) and COMMIT.fullmatch(ref)):
            raise Refused(f"run.json depends_on ref {owner_git.shown(json.dumps(ref))} is not a commit id")
        repo = next((r for r in repos() if isinstance(path, str) and path and owner_git.same_dir(r, owner_git.home_path(path))), None)
        if repo is None:
            raise Refused(f"run.json depends_on path {owner_git.shown(json.dumps(path))} is not a repository `repos` in "
                          f"{owner_git.launch_json()} lists")
        found.append((session, repo, ref))
    return found


def session_folder(config: dict, session_dir: str) -> str:
    """The session folder as `<sessions root>/<its name>`, held to unlinked() and the same directory as `session_dir`."""
    sessions = unlinked("sessions root", spelled_sessions(config))
    name = os.path.basename(os.path.realpath(session_dir))
    folder = unlinked("session folder", f"{sessions}/{name}")
    if not SEGMENT.fullmatch(name) or identity(folder) is None or identity(folder) != identity(session_dir):
        raise Refused(f"{session_dir} is not a session folder directly under the sessions root {sessions}")
    return folder


def worker(session_dir: str, worktree: str) -> dict:
    config = launch_config()
    session_dir = session_folder(config, session_dir)
    try:
        path, repo = git(owner_git.check, worktree)
    except owner_git.Unlisted as refusal:
        raise Refused(f"{refusal.code}: {refusal.detail}") from None
    run = run_json(session_dir)
    dependency_repos = [dep for _, dep, _ in dependencies(run)]
    grants = ([("session folder", session_dir),
               ("accounting root", unlinked("accounting root", spelled_accounting(config)))]
              + lock_grants(run, config))
    check(grants, protected_paths([("the repository", r) for r in [repo] + dependency_repos]), config)
    return fragment(grants, denied_paths([repo] + dependency_repos) + [path + LEAF], commits=True)


def checkouts(session_dir: str) -> list:
    """Make each missing <session_dir>/deps/<session> at its ref; one that exists is the Worker's preflight's to check."""
    session_dir = session_folder(launch_config(), session_dir)
    deps = os.path.join(session_dir, "deps")
    made = []
    for session, repo, ref in dependencies(run_json(session_dir)):
        if os.path.islink(deps):
            raise Refused(f"{deps} is a link; a checkout is never made through one")
        os.makedirs(deps, exist_ok=True)
        target = os.path.join(deps, session)
        if os.path.islink(target):
            raise Refused(f"{target} is a link; a checkout is never made through one")
        if os.path.exists(target):
            continue
        flags = attributes_off(repo)
        done = add_worktree(repo, [*flags, "worktree", "add", "--detach", "--end-of-options", target, ref])
        if done.returncode != 0:
            raise Refused(f"git could not make the depends_on checkout {target} at {ref}: {owner_git.shown(done.stderr.strip())}")
        made.append(f"deps:      {target} at {ref} from {repo}")
    return made


def attributes_off(repo: str) -> list:
    """The checkout runs as the Owner, unsandboxed: no filter a session's .gitattributes names may run there."""
    flags = git(owner_git.no_attributes, repo)
    if flags is None:
        raise Refused(git(owner_git.attributes_refusal))
    return flags


def convention_repo(worktree, slug: str, what: str) -> str:
    """The repository owner_git trusts whose <repo>/.worktrees/<slug> `worktree` is, spelled exactly so; else Refused
    naming `what`."""
    trusted = owner_git.configured_repos()
    places = {f"{repo}{WORKTREES}{slug}": repo for repo in trusted}
    if worktree not in places:
        raise Refused(f"{what} {owner_git.shown(json.dumps(worktree))} is not where the launcher makes one: "
                      f"<repo>{WORKTREES}{slug} in a repository `repos` in {owner_git.launch_json()} lists and a project's "
                      f"robowright.json names ({owner_git.shown(', '.join(places) or 'none')})")
    return places[worktree]


def branch_name(repo: str, branch: str, what: str):
    if git(owner_git.run, repo, "check-ref-format", "--branch", branch).returncode != 0:
        raise Refused(f"{what} {branch} is not a branch name git accepts")


def branch_exists(repo: str, branch: str) -> bool:
    found = git(owner_git.run, repo, "rev-parse", "--verify", "--quiet", "--end-of-options", f"refs/heads/{branch}")
    return found.returncode == 0


def base_commit(repo: str, base, what: str) -> str:
    if not (isinstance(base, str) and FULL_COMMIT.fullmatch(base)):
        raise Refused(f"{what} {owner_git.shown(json.dumps(base))} is not a full 40-hex commit id")
    found = git(owner_git.run, repo, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{base}^{{commit}}")
    if found.returncode != 0 or found.stdout.strip() != base:
        raise Refused(f"{what} {base} is not a commit in {repo}")
    return base


def new_branch_command(repo: str, branch: str, worktree: str, base, what: str) -> tuple:
    # `-b` writes the branch's ref and its reflog as the Owner, and a Worker's shell writes the shared git directory:
    # through a link there, git would append to or create a file the session chose.
    common = common_dir(repo)
    for kind in ("refs/heads", "logs/refs/heads"):
        unlinked("new branch's file", f"{common}/{kind}/{branch}")
    base = base_commit(repo, base, what)
    flags = attributes_off(repo)
    return (repo, [*flags, "worktree", "add", "-b", branch, "--end-of-options", worktree, base],
            f"git -C {repo} {' '.join(flags)} worktree add -b {branch} {worktree} {base}")


def worktree_command(session_dir: str) -> tuple:
    """(repository, the `worktree add` arguments, the line as the Owner reads it) for run.json's worktree, every value
    held to the hook's convention before git runs: the path <repo>/.worktrees/<slug> in a repository owner_git
    trusts, the branch robowright/<slug>, and at preflight a full commit id of that repository as the base. The
    arguments start with the options that read no attributes."""
    session_dir = session_folder(launch_config(), session_dir)
    slug = os.path.basename(session_dir)
    run = run_json(session_dir)
    # The launcher's `.phase // "preflight"`: only an absent or null phase is a briefed session.
    phase = "preflight" if run.get("phase") in (None, False) else run.get("phase")
    if not isinstance(phase, str):
        raise Refused(f"run.json phase {owner_git.shown(json.dumps(phase))} is not a phase name")
    if phase in ("done", "parked"):
        raise Refused(f"run.json phase is {owner_git.shown(json.dumps(phase))}: a finished session's worktree is not made")
    worktree = run.get("worktree")
    repo = convention_repo(worktree, slug, "run.json worktree")
    unlinked("worktree", worktree)
    units = run.get("units")
    branch = units[0].get("branch") if isinstance(units, list) and units and isinstance(units[0], dict) else None
    if branch != BRANCH_PREFIX + slug:
        raise Refused(f"run.json units[0].branch {owner_git.shown(json.dumps(branch))} is not {BRANCH_PREFIX}{slug}, the "
                      f"branch the launcher makes a worktree on")
    branch_name(repo, branch, "run.json units[0].branch")
    if phase != "preflight":
        if not branch_exists(repo, branch):
            raise Refused(f"the branch {branch} does not exist in {repo}, and run.json phase {phase} is past preflight")
        flags = attributes_off(repo)
        return (repo, [*flags, "worktree", "add", "--end-of-options", worktree, branch],
                f"git -C {repo} {' '.join(flags)} worktree add {worktree} {branch}")
    return new_branch_command(repo, branch, worktree, run.get("base_sha"), "run.json base_sha")


def add_worktree(repo: str, args: list):
    """`args`, a `worktree add` whose last two words are the path and the commit, run with --no-checkout, then the
    checkout run in the new worktree: its config (config.worktree, an includeIf onbranch or gitdir) can name a hook the
    main clone's does not, and owner_git turns off the hooks of the checkout a call runs in. No reflog is created: a
    link planted in logs/ after the check would have git create one where it points. The reset never recurses, as
    `worktree add`'s own checkout does not: a new worktree has no submodule git dirs."""
    split = args.index("add") + 1
    done = git(owner_git.run, repo, "-c", "core.logAllRefUpdates=false", *args[:split], "--no-checkout", *args[split:])
    if done.returncode != 0:
        return done
    flags = args[:args.index("worktree")]
    try:
        done = git(owner_git.run, args[-2], *flags, "-c", "core.logAllRefUpdates=false", "reset", "--hard", "-q",
                   "--no-recurse-submodules")
    except BaseException:
        undo_worktree(repo, args)
        raise
    if done.returncode != 0:
        undo_worktree(repo, args)
    return done


def undo_worktree(repo: str, args: list):
    """What `worktree add` itself does when its checkout fails: the half-made worktree goes, and so does the branch
    `-b` made at the commit, so no later launch reuses a worktree whose index is empty."""
    git(owner_git.run, repo, "worktree", "remove", "--force", "--force", "--end-of-options", args[-2])
    if "-b" in args:
        git(owner_git.run, repo, "update-ref", "-d", "--end-of-options", "refs/heads/" + args[args.index("-b") + 1],
            args[-1])


def make_worktree(repo: str, args: list, line: str) -> str:
    done = add_worktree(repo, args)
    if done.returncode != 0:
        raise Refused(f"git could not make the worktree: {owner_git.shown(done.stderr.strip())}")
    exclude_worktrees(repo)
    return f"worktree:  made: {line}"


def exclude_worktrees(repo: str):
    """The main checkout ignores the folder worktrees are made in: git lists a nested worktree as untracked, and
    accept.sh refuses a main clone whose status prints anything."""
    exclude = os.path.join(common_dir(repo), "info", "exclude")
    text = ""
    try:
        with open(exclude) as handle:
            text = handle.read()
    except FileNotFoundError:
        pass
    except owner_git.PATH_ERRORS as error:
        raise Refused(f"{exclude} cannot be read ({error})") from None
    if EXCLUDED in text.splitlines():
        return
    if not os.path.lexists(os.path.dirname(exclude)):
        os.mkdir(os.path.dirname(exclude))
    # session_write refuses a link at info/ or at exclude: a session's shell wrote the git directory before U46.
    try:
        session_write.append(exclude, ("\n" if text and not text.endswith("\n") else "") + EXCLUDED + "\n")
    except session_write.Refused as refusal:
        raise Refused(f"the exclude line was not written: {refusal}") from None


def made_worktree(session_dir: str, make: bool) -> str:
    repo, args, line = worktree_command(session_dir)
    if not make:
        return f"worktree:  missing; a launch runs: {line}"
    return make_worktree(repo, args, line)


def direct_briefing(config: dict, project: str, briefing: str) -> str:
    """The briefing once it is a regular file with one link, named by a path segment ending .md, directly in
    <project>/briefings/ of a folder directly in the projects root: the prompt that names it holds nothing else."""
    projects = spelled(config, "projects_root")
    if projects is None:
        raise Refused(f"{owner_git.launch_json()} names no `projects_root`, so no --briefing is inside it")
    projects = unlinked("projects root", projects)
    project = unlinked("--project folder", project)
    sessions = identity(unlinked("sessions root", spelled_sessions(config)))
    if (os.path.dirname(project) != projects or not SEGMENT.fullmatch(os.path.basename(project))
            or not os.path.isdir(project) or identity(project) == sessions):
        raise Refused(f"--project {project} is not a project folder directly in the projects root {projects}")
    briefing = unlinked("--briefing file", briefing)
    if os.path.dirname(briefing) != f"{project}/briefings" or not BRIEFING.fullmatch(os.path.basename(briefing)):
        raise Refused(f"--briefing {briefing} is not a file named <letters, digits, '.', '_', '-'>.md directly in "
                      f"{project}/briefings")
    try:
        found = os.lstat(briefing)
    except owner_git.PATH_ERRORS as error:
        raise Refused(f"--briefing {briefing} cannot be read ({error})") from None
    if not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
        raise Refused(f"--briefing {briefing} is not a regular file with one link")
    return briefing


def direct_worktree(project: str, repo: str, slug: str, base: str, briefing: str) -> tuple:
    """(repository, worktree, the `worktree add` arguments and line, or None when the worktree is already the
    repository's worktree of robowright/<slug> at <repo>/.worktrees/<slug>), for a direct build, which has no run.json:
    every argv value held to the Worker's checks before git runs."""
    direct_briefing(launch_config(), project, briefing)
    if not SEGMENT.fullmatch(slug):
        raise Refused(f"--slug {owner_git.shown(json.dumps(slug))} is not one path segment of letters, digits, '.', '_' and '-'")
    unlinked("--repo repository", repo)
    worktree = f"{repo}{WORKTREES}{slug}"
    repo = convention_repo(worktree, slug, "--repo")
    unlinked("worktree", worktree)
    branch = BRANCH_PREFIX + slug
    branch_name(repo, branch, "the branch")
    base_commit(repo, base, "--base")
    if os.path.lexists(worktree):
        try:
            path, owner = git(owner_git.check, worktree)
        except owner_git.Unlisted as refusal:
            raise Refused(f"{worktree} exists and is not a worktree of {repo} ({refusal.code}); nothing there is reused") from None
        if owner != repo or path != worktree or [path, branch] not in git(owner_git.worktrees_of, repo):
            raise Refused(f"{worktree} exists and is not {repo}'s worktree of {branch}; nothing there is reused")
        return repo, worktree, None
    if branch_exists(repo, branch):
        raise Refused(f"the branch {branch} exists in {repo} but no worktree is at {worktree}; nothing is made over it. "
                      f"Read it, then delete it (git -C {repo} branch -D {branch}) or make its worktree by hand")
    return (repo, worktree, new_branch_command(repo, branch, worktree, base, "--base")[1:])


def direct(args: list) -> str:
    """`direct <project> <repo> <slug> <base> <briefing> plan|make|grants`: the worktree line, or document's fragment."""
    *values, step = args
    repo, worktree, command = direct_worktree(*values)
    if step == "grants":
        return json.dumps(document(with_accounting=False, worktree=worktree))
    if command is None:
        return f"worktree:  {worktree} on {BRANCH_PREFIX}{values[2]}, reused"
    add, line = command
    if step == "plan":
        return f"worktree:  missing; a launch runs: {line}"
    return make_worktree(repo, add, line)


def main(args) -> int:
    try:
        if len(args) == 3 and args[0] == "worker":
            print(json.dumps(worker(args[1], args[2])))
        elif args[:1] == ["document"] and len(args) <= 2:
            print(json.dumps(document(with_accounting=False, cwd=args[1] if len(args) == 2 else None)))
        elif len(args) == 2 and args[0] == "checkouts":
            for line in checkouts(args[1]):
                owner_git.emit(sys.stdout, line + "\n")
        elif len(args) == 3 and args[0] == "worktree" and args[2] in ("plan", "make"):
            owner_git.emit(sys.stdout, made_worktree(args[1], make=args[2] == "make") + "\n")
        elif len(args) == 7 and args[0] == "direct" and args[6] in ("plan", "make", "grants"):
            owner_git.emit(sys.stdout, direct(args[1:]) + "\n")
        else:
            print("usage: role_grants.py worker <session_dir> <worktree> | document [<cwd>] | checkouts <session_dir> | "
                  "worktree <session_dir> plan|make | direct <project> <repo> <slug> <base> <briefing> plan|make|grants",
                  file=sys.stderr)
            return 1
    except Refused as refusal:
        owner_git.emit(sys.stderr, f"refused: {owner_git.shown(str(refusal))}\n")
        return EXIT_REFUSED
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
