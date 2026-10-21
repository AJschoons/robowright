#!/usr/bin/env -S python3 -I
"""
rw-git — the one program a sandboxed session runs, outside its sandbox and as the Owner, to write a repository's git
directory. The session's sandbox denies that directory; Claude Code runs `rw-git *` unsandboxed because the session's
settings list it in `sandbox.excludedCommands`. So every value here comes from the session, and rw-git takes only
the subcommands below, each held to its shape, and keeps git from running any program the repository names.

    rw-git add <path>...                      stage these paths
    rw-git restore [--staged] <path>...       unstage them, or put the index copy back in the worktree
    rw-git commit --message-file <file>       commit what is staged, the message read from <file>
    rw-git commit --amend --message-file <file>
                                              replace the own branch's tip: no merge, and no remote-tracking ref
                                              (refs/remotes/*) holds it, as of the last fetch
    rw-git commit [--amend] --message-file <file> --scope-file <file>
                                              the same, refused unless every path the commit changes (a rename
                                              under its new path) matches a line of <file>: one literal pathspec per
                                              line, `#` comments and blank lines skipped
    rw-git switch -c <branch>                 make an own branch at HEAD and switch to it
    rw-git switch <branch>                    switch to an own branch (unmanaged: any existing branch)
    rw-git reset --soft <commit>              move the own branch to a full commit id, keeping index and files;
                                              prints the old tip
    rw-git reset --keep <commit>              the same, resetting the index and the files that differ; git refuses
                                              (exit 1) when that would lose a local change
    rw-git rebase [--autosquash] <commit>     rebase the own branch onto a full commit id; prints the old tip
    rw-git rebase --onto <new> <upstream>     replay <upstream>..HEAD onto <new>, both full ids; prints the old tip
    rw-git rebase --continue | --abort
    rw-git cherry-pick <commit>               apply one commit, by full id, to the own branch
    rw-git cherry-pick --continue | --abort
    rw-git stash push [<path>...]             stash on the own branch, tagged with this worktree's slug (unmanaged:
                                              its path)
    rw-git stash pop                          apply and drop this worktree's newest entry, and no other
    rw-git fetch                              origin's branches into refs/remotes/origin/*, no tags
    rw-git fetch --remote <name>              a configured remote's branches into refs/remotes/<name>/*, no tags
    rw-git push [--force-with-lease] <branch> one own branch to the same name on origin, no tags
    rw-git push [--force-with-lease] --remote <name> <branch>
                                              the same, to a configured remote that launch.json's `push_remotes`
                                              lists for this repository
    rw-git --help                             this text

Where it runs. The working directory is a worktree a repository in launch.json's `repos` lists, or that
repository's main checkout, checked as owner_git.py checks one: by canonical path, and with the worktree's own git
directory. A worktree at <repo>/.worktrees/<slug>, or at the old place <repo>/.claude/worktrees/<slug>, owns the
branches robowright/<slug> and robowright/<slug>-u<N>; the main checkout owns what an unmanaged checkout owns, below.
A path is relative to the worktree or absolute inside it, passes through no linked folder, and names no `.git`. The message file is a plain
file of at most 64 KiB under <sessions_root>/<slug>/ or <projects_root>/<project>/prs/<slug>/, reached through no link;
so is a scope file. A commit that adds, removes or moves a gitlink (mode 160000) is refused, whatever the
configuration ignores. A remote is named by one segment, `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, that `git remote` lists;
its URL never comes from the command line.
A push needs the main checkout's project hook to say `publish_strategy: draft-pr` or `pr-plus-deploy`. One rw-git runs
at a time in a repository: each holds an exclusive lock on rw-git.lock in its shared git directory from its first
check to git's last write, waiting at most 30 seconds for it; git's output is written after the lock is released.

Outside a managed worktree. A repository also counts when its main checkout lies under a granted folder: an entry of
launch.json's `desktop_roots` (absolute after ~/, no glob, no link; a bad entry is refused), or a
`sandbox.filesystem.allowWrite` or `permissions.additionalDirectories` entry of the account's own
~/.claude/settings.json (one with a glob, a relative path or a link is skipped, and all of them when that file lies
under a granted folder), and under no `denyWrite` or `Edit(…)` deny there or in that folder's .claude/settings.json; a
deny is matched as its glob (`**` any segments, `*` within one), and any other glob shape is refused. A grant made
for one session only (--add-dir, /add-dir, a project's settings) is invisible from here.

In an unmanaged checkout (a main checkout, or a linked worktree elsewhere) an own branch is any branch launch.json's
`protected_branches` does not protect: an object from a repository path, spelled as `repos` spells one, to a list of
branch names or fnmatch globs, each 1 to 255 bytes with no control byte (a bad entry is refused). Every repository
gets the default, main, master, develop, release/* and hotfix/*, and the branch refs/remotes/origin/HEAD names when it
is set; a list adds to them, never replaces them. Names match case folded, and a name holding a byte outside
printable ASCII, a character git refuses in a ref name, `@{` or `..` is protected. `switch <branch>` goes to any
existing branch, a protected one included; every subcommand that writes a branch (commit, commit --amend, reset, rebase,
cherry-pick, stash, push) is refused while HEAD is on a protected branch, and `switch -c` and `push` name an
unprotected one; reset and push --force-with-lease also refuse a branch a remote-tracking ref ending /<branch>
(case folded) or an upstream tracks, as of the last fetch. Each of those is refused on a detached HEAD, and, but for the --continue
/ --abort steps, with a merge, rebase, cherry-pick or revert stopped half way; so is `switch`. Its message file lies
under /private/tmp/claude-<uid>/, the account's DARWIN_USER_TEMP_DIR or a granted folder, and never inside the repository.

What it keeps git from running. Through the installed wrapper only PATH and HOME reach it, so an ssh agent's
SSH_AUTH_SOCK does not; run directly, it keeps only the caller's variables KEPT names. Either way no GIT_*,
XDG_CONFIG_HOME, DEVELOPER_DIR or ROBOWRIGHT_* variable, HOME is the account's home from the account database, and git is /usr/bin/git, not PATH's. Every call names
the git directory and worktree it checked, reads no attributes from the checkout (so no filter, merge or diff driver),
overrides every driver $GIT_DIR/info/attributes can name and turns off every config hook (hook.<name>.*) by name, a
name holding `=` or an empty one included, and sets: no fsmonitor, no hooks, no pager, no editor, no external diff, ssh as the ssh
command, no askpass, no alternate-refs command, no automatic gc or maintenance, no signing, no cookie file, no
update-refs, no follow-tags, no mirror, upload-pack and receive-pack by their own names, and only the ssh and https
transports. Credential helpers
come from the Owner's system and global configuration only.

Exit codes:
  exit 0  git ran and succeeded
  exit 1  git ran and failed; its output follows, control bytes removed
  exit 2  refused before git wrote anything: `refused: <code>: <detail>` on stderr
Refusal codes:
  usage                    not one of the forms above
  launch-config            launch.json has no well-formed `repos`, or names a path through a link; outside `repos`, a
                           bad `desktop_roots` entry or a settings file that cannot be read; unmanaged, a bad
                           `protected_branches` value; for a push to a remote other than origin, a bad `push_remotes` value
  repos-unconfigured       no repository is trusted
  worktree-unlisted        the working directory is not a worktree or main checkout of a `repos` repository, nor a
                           main checkout under a `desktop_roots` entry or a granted folder
  worktree-foreign-gitdir  the worktree's .git names a git directory other than its own, or its rw-git.lock is not a
                           file rw-git can open
  git-unsupported          /usr/bin/git cannot read attributes from a tree (--attr-source, git 2.41.0)
  path-outside             a path leaves the worktree, passes through a link, or names a .git
  attributes               a path to add has attributes under which git add would store other bytes than the file's
  branch-not-own           the branch named is not this worktree's
  branch-protected         unmanaged: HEAD, the branch named, or the rebase in progress is a protected branch
  head-not-own             HEAD, or the rebase in progress, is not on this worktree's branch; or, unmanaged, HEAD
                           is detached or an operation stopped half way
  commit-unknown           the commit is not a full lowercase 40-hex id of a commit in this repository
  amend-merge              the commit to amend has more than one parent
  amend-pushed             a remote-tracking ref holds the commit to amend
  branch-tracked           unmanaged: reset or push --force-with-lease of a branch a remote-tracking ref or an upstream
                           tracks
  scope                    the scope file is not one the message-file rules allow, or holds a control byte; or the
                           commit changes a path outside it (printed, one per line)
  gitlink                  the commit adds, removes or moves a submodule pointer (printed, one per line)
  remote-unknown           --remote names no remote this repository configures, or not as one plain segment; for a
                           push, a remote other than origin that `push_remotes` does not list
  message-file             the message file is not a plain file under the session's own folders (unmanaged: a
                           temp or granted folder, outside the repository)
  push-unpublished         the project hook does not publish pushed branches
  stash-none               no stash entry is this worktree's
  repo-busy                another rw-git has held the repository's rw-git.lock for 30 seconds
"""

import fcntl
import fnmatch
import importlib.util
import io
import os
import pwd
import re
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import owner_git  # noqa: E402
import role_grants  # noqa: E402

EXIT_FAILED = 1
EXIT_REFUSED = 2
# SIP-protected, so no session and no PATH entry can stand in for it.
GIT = "/usr/bin/git"
SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
# The caller's variables rw-git and git keep, with LC_*; every other one, every GIT_*, proxy, editor, DEVELOPER_DIR and
# ROBOWRIGHT_* variable among them, is dropped before anything runs.
KEPT = ("HOME", "USER", "LOGNAME", "LANG", "TERM", "TMPDIR", "SSH_AUTH_SOCK")
# Attributes under which plain git add may store other bytes than the file's, refused whenever check-attr --all lists
# one: it prints the state `-filter` and the string `filter=unset` alike.
CONVERTING = ("filter", "ident", "working-tree-encoding")
# ls-files --eol's attr/ field (convert.c, get_convert_attr_ascii) → the action it fixes; "" and "text" depend on the config.
ATTRIBUTE_ACTIONS = {"": None, "text": None, "-text": "binary", "text eol=lf": "text-input",
                     "text eol=crlf": "text-crlf", "text=auto": "auto", "text=auto eol=lf": "auto-input",
                     "text=auto eol=crlf": "auto-crlf"}
# Paths per ls-files call, far below the argument-list limit.
NAMES_PER_CALL = 500
OBJECT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")  # SHA-1 or SHA-256
# convert.c's gather_stats: every byte below 32 but BS, TAB, LF, FF, CR and ESC, and DEL.
CONTROL = bytes(byte for byte in range(32) if byte not in b"\b\t\n\x0c\r\x1b") + b"\x7f"
PROTOCOLS = ("ssh", "https")
# Scopes whose credential helpers are put back after `credential.helper=` empties the list: the Owner's own files.
# Apple Git reports the gitconfig inside its Xcode or Command Line Tools bundle as `unknown`.
HELPER_SCOPES = ("system", "global", "unknown")
MESSAGE_LIMIT = 64 * 1024
WORKTREE_FOLDERS = (".worktrees", ".claude/worktrees")
# What a merge, rebase, cherry-pick or revert stopped half way leaves in the git directory.
STOPPED = ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD", "sequencer")
BRANCH_PREFIX = role_grants.BRANCH_PREFIX
# Protected in every unmanaged checkout, with the branch origin/HEAD names and any `protected_branches` list.
DEFAULT_PROTECTED = ("main", "master", "develop", "release/*", "hotfix/*")
ORIGIN_HEAD = "refs/remotes/origin/HEAD"
ORIGIN_PREFIX = "refs/remotes/origin/"
BRANCH_PATTERN_LIMIT = 255  # bytes
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# Never written: the disk may fold the name onto another (APFS: ſ is s), or git reads a pattern or a second ref in it.
UNWRITABLE = re.compile(r"[^\x21-\x7e]|[~^:?*\[\\]|@\{|\.\.")
LOCK_FILE = "rw-git.lock"
LOCK_WAIT = 30  # seconds before repo-busy
LOCK_RETRY = 0.1  # seconds
REMOTE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
GITLINK = b"160000"
PUSHED = ("draft-pr", "pr-plus-deploy")
PUBLISHING = re.compile(r"^##\s*10[.\s·][^\n]*\n(?:[ \t]*\n)*publish_strategy:[ \t]*(\S+)[ \t]*$", re.M)
# Every key that names a program git could run on these subcommands, or a file it would write; the ledger says why each.
OVERRIDES = (
    "core.fsmonitor=false",
    "core.hooksPath=/dev/null",
    "core.pager=cat",
    "core.editor=false",
    "sequence.editor=false",
    "diff.external=",
    "core.sshCommand=ssh",
    "core.askPass=",
    "core.alternateRefsCommand=",
    "credential.helper=",
    "protocol.allow=never",
    "remote.origin.mirror=false",
    "gc.auto=0",
    "maintenance.auto=false",
    "commit.gpgSign=false",
    "tag.gpgSign=false",
    "push.gpgSign=false",
    "log.showSignature=false",
    "http.cookieFile=",
    "http.saveCookies=false",
    "push.followTags=false",
    "submodule.recurse=false",
)
# Keys with a name in the middle, each one configured overridden: a URL-scoped key outranks the plain one whatever the
# order, and a driver can be named by $GIT_DIR/info/attributes, which git reads even under --attr-source. Each goes
# through --config-env, never -c, which git splits at the first `=`, and a name may hold one.
# A name may also be empty: `[filter ""]` is filter..smudge, which an attributes line `filter=` names.
NAMED = ((re.compile(r"protocol\.(.*)\.allow"), "never"), (re.compile(r"http\..*\.cookiefile"), ""),
         (re.compile(r"http\..*\.savecookies"), "false"),
         (re.compile(r"(filter|merge|diff)\..*\.(clean|smudge|process|driver|command|textconv)"), ""),
         (re.compile(r"filter\..*\.required"), "false"))
# A config hook (hook.<name>.*, git 2.54) runs whatever core.hooksPath says; hook.<name>.enabled=false turns one off.
HOOK_KEY = re.compile(r"hook\.(.*)\.[^.]+")
# The variable --config-env names for each override value, set in every git call's environment.
CONFIG_ENV = {"RW_GIT_NEVER": "never", "RW_GIT_EMPTY": "", "RW_GIT_FALSE": "false"}
CONFIG_VARIABLE = {value: variable for variable, value in CONFIG_ENV.items()}
# remote.<name>.uploadpack and .receivepack keep the first value git reads, so a -c cannot replace them; an option can.
UPLOAD_PACK = "--upload-pack=git-upload-pack"
RECEIVE_PACK = "--receive-pack=git-receive-pack"
HELP = __doc__.strip("\n")


class Refused(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class Place:
    """Where rw-git runs: the checked worktree, its repository, its git directory, and its slug (None for the main
    checkout), plus the options every git call carries."""

    def __init__(self, worktree, repo, git_dir, slug):
        self.worktree, self.repo, self.git_dir, self.slug = worktree, repo, git_dir, slug
        self.shown = []
        self.attributes, self.extra, self.protected = [], [], ()
        # The Owner's credential helpers, each a variable an --config-env option in `extra` names.
        self.helpers = {}

    def argv(self, *args, attributes=False):
        return git_argv(self.git_dir, self.worktree, self.extra if attributes else self.attributes + self.extra, *args)


def git_argv(git_dir, worktree, extra, *args) -> list:
    overrides = [word for pair in OVERRIDES for word in ("-c", pair)]
    return [GIT, "--no-pager", "--literal-pathspecs", f"--git-dir={git_dir}", f"--work-tree={worktree}", *overrides,
            *extra, *args]


def child_env(place) -> dict:
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", **CONFIG_ENV, **place.helpers)


def call(place, *args, data=None, attributes=False) -> subprocess.CompletedProcess:
    return subprocess.run(place.argv(*args, attributes=attributes), cwd=place.worktree, env=child_env(place), capture_output=True,
                          input=data if data is not None else b"", check=False)


def text(raw: bytes) -> str:
    return owner_git.shown(raw.decode("utf-8", "surrogateescape"))


def run(place, *args, data=None) -> int:
    """git's exit as rw-git's: 0, or 1 with its output shown."""
    done = call(place, *args, data=data)
    place.shown += [(sys.stdout, text(done.stdout)), (sys.stderr, text(done.stderr))]
    return 0 if done.returncode == 0 else EXIT_FAILED


def read(place, *args) -> str:
    done = call(place, *args)
    return done.stdout.decode("utf-8", "surrogateescape") if done.returncode == 0 else ""


# -- where it runs ---------------------------------------------------------------------------------------------------

def locate() -> Place:
    try:
        repos = role_grants.repos()
        for entry in role_grants.spelled_repos():
            role_grants.unlinked("`repos` entry", entry)
    except role_grants.Refused as refusal:
        raise Refused("launch-config", str(refusal)) from None
    try:
        listed = owner_git.index(repos)
        here = os.path.realpath(os.getcwd())
        if here not in listed:
            desktop = role_grants.desktop_repo(here, role_grants.launch_config(), owner_home())
            listed = {**owner_git.index([desktop]), **listed} if desktop is not None else listed
    except role_grants.Refused as refusal:
        raise Refused("launch-config", str(refusal)) from None
    except OSError as error:
        raise Refused("worktree-unlisted", f"the working directory cannot be named ({owner_git.shown(error)})") from None
    try:
        worktree, repo = owner_git.check(os.getcwd(), listed)
    except owner_git.UnlistedDirectory:
        raise Refused("worktree-unlisted", f"'{owner_git.shown(here)}' is not a directory rw-git serves: a worktree or main "
                                           f"checkout of a repository `repos` in {owner_git.launch_json()} lists, or a main "
                                           f"checkout under a `desktop_roots` entry or a granted folder") from None
    except owner_git.Unlisted as refusal:
        raise Refused(refusal.code, refusal.detail) from None
    name = os.path.basename(worktree)
    slug = None
    if any(os.path.dirname(worktree) == os.path.join(repo, folder) for folder in WORKTREE_FOLDERS):
        slug = name if role_grants.SEGMENT.fullmatch(name) else None
    place = Place(worktree, repo, admin_dir(worktree, repo), slug)
    place.attributes, place.extra, place.helpers = extra_options(place)
    if slug is None:
        place.protected = protected_patterns(repo) + origin_head(place)
    return place


def origin_head(place) -> tuple:
    """The branch refs/remotes/origin/HEAD names, as a pattern matching only that name, or nothing when it is unset."""
    target = read(place, "symbolic-ref", "-q", ORIGIN_HEAD).strip()
    if not (target.startswith(ORIGIN_PREFIX) and len(target) > len(ORIGIN_PREFIX)):
        return ()
    return (re.sub(r"([*?\[])", r"[\1]", target[len(ORIGIN_PREFIX):]),)


def protected_patterns(repo) -> tuple:
    """The default, plus launch.json's `protected_branches` list for `repo`: an object from a repository path as
    `repos` spells one to its branch names or fnmatch globs. A list adds to the default, never replaces it; any
    entry out of shape is refused by name."""
    try:
        value = role_grants.launch_config().get("protected_branches")
    except role_grants.Refused as refusal:
        raise Refused("launch-config", str(refusal)) from None
    if value is None:
        return DEFAULT_PROTECTED
    if not isinstance(value, dict):
        raise Refused("launch-config", "`protected_branches` in launch.json is not an object from a repository path to "
                                       "a list of branch names")
    found = DEFAULT_PROTECTED
    for key, names in value.items():
        if not owner_git.REPO_ENTRY.fullmatch(key):
            raise Refused("launch-config", f"the `protected_branches` key {owner_git.shown(repr(key))} is not an "
                                           f"absolute or ~/ path")
        if not isinstance(names, list):
            raise Refused("launch-config", f"`protected_branches` for {owner_git.shown(key)} is not a list")
        for name in names:
            if not (isinstance(name, str) and name and not CONTROL_CHARACTERS.search(name)
                    and len(name.encode("utf-8", "surrogatepass")) <= BRANCH_PATTERN_LIMIT):
                raise Refused("launch-config", f"the `protected_branches` entry {owner_git.shown(repr(name))} for "
                                               f"{owner_git.shown(key)} is not a branch name of 1 to "
                                               f"{BRANCH_PATTERN_LIMIT} bytes without a control byte")
        if os.path.realpath(owner_git.home_path(key)) == repo:
            found = DEFAULT_PROTECTED + tuple(names)
    return found


def admin_dir(worktree, repo) -> str:
    """The git directory every call names: the main clone's, or the entry in its worktrees/ whose gitdir file names
    this worktree. Both are read from the repository's own git directory, so a .git file the session rewrites after
    the check is never read."""
    try:
        common = role_grants.common_dir(repo)
    except role_grants.Refused as refusal:
        raise Refused("worktree-foreign-gitdir", str(refusal)) from None
    if common is None:
        raise Refused("worktree-unlisted", f"{repo} has no git directory")
    if worktree == repo:
        return common
    entries = os.path.join(common, "worktrees")
    for entry in sorted(os.listdir(entries)) if os.path.isdir(entries) else []:
        named = owner_git.read_entry(os.path.join(entries, entry, "gitdir"))
        try:
            if named is not None and os.path.realpath(os.path.dirname(os.fsdecode(named.strip()))) == worktree:
                return os.path.join(entries, entry)
        except owner_git.PATH_ERRORS:
            continue
    raise Refused("worktree-foreign-gitdir", f"no entry in {entries} names {worktree}")


def extra_options(place) -> tuple:
    """Options read from this repository: no attributes from the checkout, then each URL-scoped key and driver
    overridden and each config hook turned off, by --config-env, and the Owner's own credential helpers put back after
    the list is emptied, by --config-env too (a helper's key may hold a URL with `=`), with the variables they name."""
    attributes = owner_git.no_attributes(place.repo)
    if attributes is None:
        raise Refused("git-unsupported", owner_git.attributes_refusal())
    extra = []
    for _, name, _ in configured(place, r"^(protocol|http|filter|merge|diff|hook)\."):
        for pattern, value in NAMED:
            found = pattern.fullmatch(name)
            if found and not (value == "never" and found.group(1) in PROTOCOLS):
                extra.append(f"--config-env={name}={CONFIG_VARIABLE[value]}")
        hook = HOOK_KEY.fullmatch(name)
        off = f"--config-env=hook.{hook.group(1)}.enabled={CONFIG_VARIABLE['false']}" if hook else None
        if off is not None and off not in extra:
            extra.append(off)
    for protocol in PROTOCOLS:
        extra += ["-c", f"protocol.{protocol}.allow=always"]
    helpers = {}
    for number, (_, name, value) in enumerate(owner_helpers(place)):
        helpers[f"RW_GIT_HELPER_{number}"] = value
        extra.append(f"--config-env={name}=RW_GIT_HELPER_{number}")
    return list(attributes), extra, helpers


def configured(place, pattern) -> list:
    """(scope, key, value) for every configured key matching `pattern`, in the order git reads them."""
    # --null prints scope NUL key NL value NUL; a key with no value has no NL.
    fields = read(place, "config", "--show-scope", "--null", "--get-regexp", pattern).split("\0")
    found = []
    for scope, entry in zip(fields[0::2], fields[1::2]):
        name, _, value = entry.partition("\n")
        found.append((scope, name, value))
    return found


def owner_helpers(place) -> list:
    return [found for found in configured(place, r"^credential\.(.+\.)?helper$")
            if found[0] in HELPER_SCOPES and found[2]]


# -- values ----------------------------------------------------------------------------------------------------------

def is_own(place, branch) -> bool:
    """A managed worktree owns robowright/<slug> and robowright/<slug>-u<N>; an unmanaged checkout every unprotected
    branch."""
    if place.slug is None:
        return not is_protected(place, branch)
    own = BRANCH_PREFIX + place.slug
    return branch == own or re.fullmatch(re.escape(own) + r"-u[1-9][0-9]*", branch) is not None


def is_protected(place, branch) -> bool:
    """Matched case folded: on a case-insensitive disk a loose refs/heads/Develop is the file of develop. git expands
    `@{-N}` in a name to create, and reads `*` in a push as a pattern, so an UNWRITABLE name is never one to write."""
    folded = branch.lower()
    return UNWRITABLE.search(branch) is not None or any(fnmatch.fnmatchcase(folded, pattern.lower())
                                                       for pattern in place.protected)


def own_branch(place, branch) -> str:
    if is_own(place, branch):
        return branch
    if place.slug is None:
        raise Refused("branch-protected", f"{owner_git.shown(branch)} is {own_name(place)}")
    raise Refused("branch-not-own", f"{owner_git.shown(branch)} is not {own_name(place)}")


def own_name(place) -> str:
    if place.slug is None:
        return f"protected here ({', '.join(owner_git.shown(name) for name in place.protected)})"
    return f"{BRANCH_PREFIX}{place.slug} or {BRANCH_PREFIX}{place.slug}-u<N>"


def own_head(place, settled=True) -> str:
    """HEAD's branch, once it is own. Unmanaged, also with no operation stopped half way unless `settled` is False."""
    head = read(place, "symbolic-ref", "-q", "HEAD").strip()
    branch = head[len("refs/heads/"):] if head.startswith("refs/heads/") else None
    if place.slug is None:
        if branch is None:
            raise Refused("head-not-own", "HEAD is detached; an unmanaged checkout writes only on a branch")
        if settled:
            unstopped(place)
        return own_branch(place, branch)
    if branch is None or not is_own(place, branch):
        raise Refused("head-not-own", f"HEAD is {owner_git.shown(branch or 'detached')}, not {own_name(place)}")
    return branch


def unstopped(place) -> None:
    stopped = next((name for name in STOPPED if os.path.lexists(os.path.join(place.git_dir, name))), None)
    if stopped is not None:
        raise Refused("head-not-own", f"{stopped} is in {place.git_dir}: finish or abort that operation first")


def in_progress(place, folder) -> None:
    """A stopped rebase must be of an own branch, as its head-name names it."""
    for name in (folder, "rebase-apply"):
        entry = owner_git.read_entry(os.path.join(place.git_dir, name, "head-name"))
        if entry is None:
            continue
        head = entry.decode("utf-8", "surrogateescape").strip()
        branch = head[len("refs/heads/"):] if head.startswith("refs/heads/") else ""
        if not branch or not is_own(place, branch):
            code = "branch-protected" if place.slug is None and branch else "head-not-own"
            raise Refused(code, f"the rebase in progress is of {owner_git.shown(head)}, not an own branch")


def known_commit(place, commit) -> str:
    if not role_grants.FULL_COMMIT.fullmatch(commit):
        raise Refused("commit-unknown", f"{owner_git.shown(commit)} is not a full 40-hex commit id")
    if read(place, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{commit}^{{commit}}").strip() != commit:
        raise Refused("commit-unknown", f"{commit} is not a commit in {place.repo}")
    return commit


def inside(place, paths) -> list:
    """Each path as git takes it, relative to the worktree, once it stays inside, passes no link and names no .git."""
    found = []
    for path in paths:
        full = os.path.normpath(path if os.path.isabs(path) else os.path.join(place.worktree, path))
        if full != place.worktree and not full.startswith(place.worktree + "/"):
            raise Refused("path-outside", f"{owner_git.shown(path)} is outside {place.worktree}")
        relative = os.path.relpath(full, place.worktree)
        parts = [] if relative == "." else relative.split("/")
        if any(part.lower() == ".git" for part in parts):
            raise Refused("path-outside", f"{owner_git.shown(path)} names a .git")
        current = place.worktree
        for part in parts[:-1]:
            current = os.path.join(current, part)
            if os.path.islink(current):
                raise Refused("path-outside", f"{owner_git.shown(path)} passes through the link {owner_git.shown(current)}")
        found.append(relative)
    return found


def message_folders(place, code="message-file") -> tuple:
    """(the session folder, a pattern for <projects_root>/<project>/prs/<slug>), as launch.json spells the roots."""
    try:
        config = role_grants.launch_config()
        sessions = role_grants.unlinked("sessions root", role_grants.spelled_sessions(config))
        projects = role_grants.spelled(config, "projects_root")
        projects = role_grants.unlinked("projects root", projects) if projects else None
    except role_grants.Refused as refusal:
        raise Refused(code, f"the session's folders cannot be named: {refusal}") from None
    prs = None
    if projects:
        prs = re.compile(re.escape(projects) + r"/[A-Za-z0-9][A-Za-z0-9._-]*/prs/" + re.escape(place.slug) + "/")
    return f"{sessions}/{place.slug}/", prs


def unmanaged_message_path(place, path, code="message-file") -> str:
    """For an unmanaged checkout: `path` with /tmp/ and /var/ spelled as the folders they link to, once it lies under
    this account's own temp folder or a granted folder no deny covers, and outside the repository being committed."""
    for link, real in (("/tmp/", "/private/tmp/"), ("/var/", "/private/var/")):
        path = real + path[len(link):] if path.startswith(link) else path
    for folder in (place.repo, place.worktree, os.path.dirname(place.git_dir.rstrip("/")), place.git_dir):
        if role_grants.is_under(path, os.path.realpath(folder)):
            raise Refused(code, f"{owner_git.shown(path)} is inside the repository being committed")
    try:
        granted, denied = role_grants.desktop_grants(role_grants.launch_config(), owner_home())
    except role_grants.Refused as refusal:
        raise Refused(code, f"the granted folders cannot be named: {refusal}") from None
    places = [*own_temp_folders(), *granted]
    if not any(role_grants.is_under(path, folder) for folder in places) or role_grants.is_denied(path, denied):
        raise Refused(code, f"{owner_git.shown(path)} is not under this account's temp folder or a granted folder")
    return path


def own_temp_folders() -> list:
    """/private/tmp/claude-<uid> and the account's DARWIN_USER_TEMP_DIR, each where this account owns it and no link
    leads."""
    found = [f"/private/tmp/claude-{os.getuid()}"]
    done = subprocess.run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True, check=False)
    user = done.stdout.strip().rstrip("/") if done.returncode == 0 else ""
    if user.startswith("/var/"):
        found.append("/private" + user)
    owned = []
    for folder in found:
        try:
            checked = os.lstat(role_grants.unlinked("temp folder", folder))
        except (role_grants.Refused, OSError):
            continue
        if stat.S_ISDIR(checked.st_mode) and checked.st_uid == os.getuid():
            owned.append(folder)
    return owned


def message(place, path, code="message-file") -> bytes:
    """The message file's bytes: an absolute path with no `.`, `..` or empty part, under the session's own folders,
    opened one component at a time without following a link, a regular file with one link of at most 64 KiB. The
    scope file is read the same way, refused as `scope`."""
    parts = path.split("/")
    if not path.startswith("/") or any(part in ("", ".", "..") for part in parts[1:]):
        raise Refused(code, f"{owner_git.shown(path)} is not an absolute path without `.`, `..` or `//`")
    if place.slug is None:
        path = unmanaged_message_path(place, path, code)
        parts = path.split("/")
    else:
        session, prs = message_folders(place, code)
        if not (path.startswith(session) or (prs is not None and prs.match(path))):
            raise Refused(code, f"{owner_git.shown(path)} is not under {session} or "
                                f"<projects_root>/<project>/prs/{place.slug}/")
    try:
        fd = open_unlinked(parts[1:])
    except owner_git.PATH_ERRORS as error:
        raise Refused(code, f"{owner_git.shown(path)} cannot be opened without following a link "
                            f"({owner_git.shown(error)})") from None
    try:
        found = os.fstat(fd)
        if not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
            raise Refused(code, f"{owner_git.shown(path)} is not a regular file with one link")
        data = os.read(fd, MESSAGE_LIMIT + 1)
    finally:
        os.close(fd)
    if len(data) > MESSAGE_LIMIT:
        raise Refused(code, f"{owner_git.shown(path)} is longer than {MESSAGE_LIMIT} bytes")
    return data


def open_unlinked(parts) -> int:
    """A descriptor for /<parts>, each folder opened under the last with O_NOFOLLOW, so no link is followed even if
    one appears while it is opened, and the file opened non-blocking so a FIFO never waits."""
    folder = open_folder(parts[:-1])
    try:
        return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    finally:
        os.close(folder)


def open_folder(parts) -> int:
    """A descriptor for the folder /<parts>, each opened under the last with O_NOFOLLOW."""
    folder = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            inner = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
            os.close(folder)
            folder = inner
    except BaseException:
        os.close(folder)
        raise
    return folder


def publishes(place) -> None:
    """The main checkout's project hook, or the machine-local one matching origin, publishes pushed branches."""
    spec = importlib.util.spec_from_file_location("robowright_resolve",
                                                  os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                               "robowright-resolve.py"))
    resolve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resolve)
    try:
        hook = resolve.resolve_hook(place.repo)
        found = PUBLISHING.search(resolve.read(hook))
    except (SystemExit, OSError, ValueError):
        raise Refused("push-unpublished", f"no project hook for {place.repo} names a publish strategy") from None
    strategy = found.group(1) if found else None
    if strategy not in PUSHED:
        raise Refused("push-unpublished", f"the project hook's publish_strategy is {owner_git.shown(strategy)}, "
                                          f"not {' or '.join(PUSHED)}: nothing is pushed")


# -- subcommands -----------------------------------------------------------------------------------------------------

def plain(args) -> bool:
    return all(arg and not arg.startswith("-") for arg in args)


def parse(args):
    """(handler, its arguments) for one of the forms --help lists; Refused usage for anything else."""
    verb, rest = (args[0], args[1:]) if args else (None, [])
    if verb == "add" and rest and plain(rest):
        return add, rest
    if verb == "restore" and rest[:1] == ["--staged"] and rest[1:] and plain(rest[1:]):
        return restore, [True, *rest[1:]]
    if verb == "restore" and rest and plain(rest):
        return restore, [False, *rest]
    amend = rest[:1] == ["--amend"]
    form = rest[1:] if amend else rest
    if verb == "commit" and len(form) in (2, 4) and form[0] == "--message-file" and form[2:3] in ([], ["--scope-file"]):
        return commit, [form[1], amend, form[3] if len(form) == 4 else None]
    if verb == "reset" and len(rest) == 2 and rest[0] in ("--soft", "--keep") and plain(rest[1:]):
        return reset, rest
    if verb == "switch" and len(rest) == 2 and rest[0] == "-c" and plain(rest[1:]):
        return switch, [True, rest[1]]
    if verb == "switch" and len(rest) == 1 and plain(rest):
        return switch, [False, rest[0]]
    if verb == "rebase" and rest in (["--continue"], ["--abort"]):
        return rebase_step, rest
    if verb == "rebase" and len(rest) == 3 and rest[0] == "--onto" and plain(rest[1:]):
        return rebase_onto, rest[1:]
    if verb == "rebase" and len(rest) in (1, 2) and rest[:-1] in ([], ["--autosquash"]) and plain(rest[-1:]):
        return rebase, [rest[:-1] == ["--autosquash"], rest[-1]]
    if verb == "cherry-pick" and rest in (["--continue"], ["--abort"]):
        return pick_step, rest
    if verb == "cherry-pick" and len(rest) == 1 and plain(rest):
        return pick, rest
    if verb == "stash" and rest[:1] == ["push"] and plain(rest[1:]):
        return stash_push, rest[1:]
    if verb == "stash" and rest == ["pop"]:
        return stash_pop, []
    if verb == "fetch" and not rest:
        return fetch, [None]
    if verb == "fetch" and len(rest) == 2 and rest[0] == "--remote" and plain(rest[1:]):
        return fetch, rest[1:]
    lease = rest[:1] == ["--force-with-lease"]
    target = rest[1:] if lease else rest
    if verb == "push" and len(target) == 1 and plain(target):
        return push, [lease, target[0], None]
    if verb == "push" and len(target) == 3 and target[0] == "--remote" and plain(target[1:]):
        return push, [lease, target[2], target[1]]
    raise Refused("usage", f"rw-git {owner_git.shown(' '.join(args))} is not a form rw-git takes; see rw-git --help")


def add(place, *paths):
    relative = inside(place, paths)
    unconverted(place, relative)
    return run(place, "add", "--", *relative)


def unconverted(place, relative):
    """Refuses when, for a file add would stage, plain git add would store other bytes than rw-git's add, which reads
    no attributes from the checkout, or would stop where rw-git's would not. Only check-attr and ls-files read the
    checkout's attributes, and neither runs a program."""
    listed = call(place, "ls-files", "-z", "--modified", "--others", "--exclude-standard", "--", *relative)
    # An entry whose stat changed but whose bytes did not: plain git add hashes it again, with its attributes.
    rehashed = call(place, "diff-files", "--ignore-submodules=all", "--name-only", "-z", "--", *relative)
    index = Index(place, relative)
    names = list(dict.fromkeys([name for name in (listed.stdout + rehashed.stdout).split(b"\0") if name]
                               + index.racy()))
    if listed.returncode != 0:
        return
    files = [name for name in names if regular(place, os.fsdecode(name))]
    if not files:
        return
    named = attributes_of(call(place, "check-attr", "-z", "--stdin", "--all", data=b"\0".join(files) + b"\0",
                               attributes=True))
    plain, own = eol_attributes(place, files, attributes=True), eol_attributes(place, files, attributes=False)
    endings = LineEndings(place)
    for name in files:
        reason = conversion(place, os.fsdecode(name), named.get(name, {}), plain.get(name), own.get(name), endings,
                            index)
        if reason is not None:
            raise Refused("attributes", f"{owner_git.shown(os.fsdecode(name))} has {owner_git.shown(reason)}, so plain "
                                        f"git add would store other bytes than rw-git, or stop, since rw-git reads no "
                                        f"attributes from the checkout; that file is the Owner's to stage")


def regular(place, name) -> bool:
    """A regular file reached through no link; a folder, a link or a deleted file stores none of its own."""
    try:
        fd = open_unlinked(place.worktree.split("/")[1:] + name.split("/"))
    except OSError:
        return False
    try:
        return stat.S_ISREG(os.fstat(fd).st_mode)
    finally:
        os.close(fd)


def attributes_of(found) -> dict:
    """check-attr -z's output as {name: {attribute: value}}."""
    fields = found.stdout.split(b"\0")
    attributes = {}
    for name, attribute, value in zip(fields[0::3], fields[1::3], fields[2::3]):
        attributes.setdefault(name, {})[attribute.decode()] = value.decode("utf-8", "surrogateescape")
    return attributes


def eol_attributes(place, names, attributes) -> dict:
    """{name: ls-files --eol's attr/ field}, git's own reading of `text`, `crlf` and `eol` (convert_attrs), so a string
    value spelled `set` or `unset` is never taken for that state. `attributes` reads the checkout's, as plain git does."""
    found = {}
    for start in range(0, len(names), NAMES_PER_CALL):
        chunk = [os.fsdecode(name) for name in names[start:start + NAMES_PER_CALL]]
        done = call(place, "ls-files", "-z", "--eol", "--cached", "--others", "--exclude-standard", "--", *chunk,
                    attributes=attributes)
        for entry in done.stdout.split(b"\0") if done.returncode == 0 else []:
            fields, tab, name = entry.partition(b"\t")
            _, _, attribute = fields.partition(b"attr/")
            if tab:
                found[name] = attribute.decode("ascii", "replace").rstrip(" ")
    return found


def conversion(place, name, named, plain, own, endings, index):
    """The setting under which plain git add would store other bytes than rw-git's add for this regular file, or stop
    where rw-git's would not; None when the two agree."""
    converting = [attribute for attribute in CONVERTING if attribute in named]
    if converting:
        return f"{converting[0]}={named[converting[0]]}"
    if plain not in ATTRIBUTE_ACTIONS or own not in ATTRIBUTE_ACTIONS:
        return "line-ending attributes git did not report"
    theirs, mine = action(plain, endings), action(own, endings)
    if theirs == mine and (theirs == "binary" or endings.safecrlf != "true"):
        return None
    try:
        fd = open_unlinked(place.worktree.split("/")[1:] + name.split("/"))
    except OSError:
        return None
    with os.fdopen(fd, "rb") as handle:
        stats = text_stats(handle)
    held = stats[0] > 0 and not stats[2] and index.holds_crlf(name)
    declared = plain or f"core.autocrlf={endings.autocrlf}"
    stored = add_stores(theirs, stats, held, endings)
    if stored == "stops":
        return f"{declared} and core.safecrlf=true, under which plain git add stops on it"
    return None if stored == add_stores(mine, stats, held, endings) else declared


class LineEndings:
    """core.autocrlf, core.safecrlf and core.eol as git reads them (environment.c): a word in any case, or else a
    boolean, so `yes`, `on`, `1` and a bare key are true."""

    def __init__(self, place):
        self.autocrlf = config_value(place, "core.autocrlf", "input", "false")
        self.safecrlf = config_value(place, "core.safecrlf", "warn", "warn")
        found = call(place, "config", "--get", "core.eol")
        eol = found.stdout.strip().lower() if found.returncode == 0 else b""
        # text_eol_is_crlf: autocrlf true, or else core.eol=crlf; `native` is LF everywhere rw-git runs.
        self.crlf_text = self.autocrlf == "true" or (self.autocrlf == "false" and eol == b"crlf")


def config_value(place, key, word, absent) -> str:
    """`word`, "true" or "false" for a key git reads as that word or else as a boolean; `absent` when it is not set."""
    found = call(place, "config", "--get", key)
    if found.returncode != 0:
        return absent
    if found.stdout.rstrip(b"\n").lower() == word.encode():
        return word
    typed = call(place, "config", "--type=bool", "--get", key)
    if typed.returncode != 0:
        raise Refused("attributes", f"{key} is neither `{word}` nor a boolean, so git add would stop")
    return typed.stdout.strip().decode()


def action(attribute, endings) -> str:
    """convert_attrs' crlf_action from attr/ and the config: binary, text-input or text-crlf (every CRLF to LF on add,
    LF or CRLF on checkout), or auto, auto-input or auto-crlf (only in a file git takes for text)."""
    if attribute == "":
        return {"false": "binary", "true": "auto-crlf", "input": "auto-input"}[endings.autocrlf]
    if attribute == "text":
        return "text-crlf" if endings.crlf_text else "text-input"
    return ATTRIBUTE_ACTIONS[attribute]


def checks_out_crlf(action, endings) -> bool:
    """output_eol is CRLF."""
    return action in ("text-crlf", "auto-crlf") or (action == "auto" and endings.crlf_text)


def add_stores(action, stats, held, endings):
    """crlf_to_git on add: whether it turns CRLFs to LF, or "stops" when core.safecrlf=true finds that a checkout would
    not give the file back as it is. Under auto, a binary file is kept as it is before that check, and an index copy
    holding a CRLF keeps the file's."""
    crlf, lonelf, binary = stats
    auto = action.startswith("auto")
    if action == "binary" or (auto and binary):
        return False
    converts = crlf > 0 and not (auto and held)
    if endings.safecrlf == "true":
        after_crlf, after_lf = (0, lonelf + crlf) if converts else (crlf, lonelf)
        if checks_out_crlf(action, endings) and after_lf and not (auto and after_crlf):
            after_crlf, after_lf = after_crlf + after_lf, 0
        if (crlf and not after_crlf) or (lonelf and not after_lf):
            return "stops"
    return converts


def text_stats(handle) -> tuple:
    """(CRLF count, lone LF count, whether git takes the file for binary), as convert.c's gather_stats and
    convert_is_binary count: a lone CR, a NUL, or more than one control byte per 128 printable ones."""
    crlf = crs = lfs = nul = controls = size = 0
    last = b""
    for chunk in iter(lambda: handle.read(1 << 20), b""):
        crlf += chunk.count(b"\r\n") + (last == b"\r" and chunk.startswith(b"\n"))
        crs += chunk.count(b"\r")
        lfs += chunk.count(b"\n")
        nul += chunk.count(b"\0")
        controls += len(chunk) - len(chunk.translate(None, CONTROL))
        size += len(chunk)
        last = chunk[-1:]
    printable = size - crs - lfs - controls
    if last == b"\x1a":
        controls -= 1  # git does not count a final DOS end-of-file mark
    return crlf, lfs - crlf, crs > crlf or nul > 0 or (printable >> 7) < controls


class Index:
    """The index entries of the paths add would stage, read once and only when needed."""

    def __init__(self, place, relative):
        self.place, self.relative, self.entries = place, relative, None

    def holds_crlf(self, name) -> bool:
        """git's has_crlf_in_index: the index copy (stage 0, or else ours in a conflict) is text holding a CRLF."""
        stages = self.listed().get(os.fsencode(name), {})
        object_id = stages.get("0", stages.get("2", (None, None)))[1]
        if object_id is None:
            return False
        blob = call(self.place, "cat-file", "blob", object_id)
        if blob.returncode != 0:
            return False
        crlf, _, binary = text_stats(io.BytesIO(blob.stdout))
        return crlf > 0 and not binary

    def racy(self) -> list:
        """Every entry git add hashes again although its stat matches (CE_MATCH_RACY_IS_DIRTY): its file's mtime is no
        older than the index file's. read-cache.c's is_racy_stat may compare nanoseconds; whole seconds weigh no fewer."""
        try:
            since = int(os.stat(os.path.join(self.place.git_dir, "index")).st_mtime)
        except OSError:
            return []
        found = []
        for name, stages in self.listed().items():
            if any(mode == "160000" for mode, _ in stages.values()):
                continue
            parts = self.place.worktree.split("/")[1:] + os.fsdecode(name).split("/")
            try:
                folder = open_folder(parts[:-1])
            except OSError:
                continue
            try:
                found_stat = os.stat(parts[-1], dir_fd=folder, follow_symlinks=False)
            except OSError:
                continue
            finally:
                os.close(folder)
            if int(found_stat.st_mtime) >= since:
                found.append(name)
        return found

    def listed(self) -> dict:
        """{name: {stage: (mode, object id)}} from ls-files --stage."""
        if self.entries is not None:
            return self.entries
        listed = call(self.place, "ls-files", "-z", "--stage", "--", *self.relative)
        self.entries = {}
        for entry in listed.stdout.split(b"\0"):
            fields, _, name = entry.partition(b"\t")
            parts = fields.decode("ascii", "replace").split()
            if len(parts) == 3 and OBJECT_ID.fullmatch(parts[1]):
                self.entries.setdefault(name, {}).setdefault(parts[2], (parts[0], parts[1]))
        return self.entries


def restore(place, staged, *paths):
    return run(place, "restore", "--staged" if staged else "--worktree", "--", *inside(place, paths))


def commit(place, path, amend, scope):
    own_head(place)
    data = message(place, path)
    specs = scope_specs(place, scope) if scope is not None else None
    if amend:
        amendable(place)
    # The commit being written is the index over HEAD, or over HEAD^ for an amend.
    base = commit_base(place, "HEAD^" if amend else "HEAD")
    no_gitlinks(place, base)
    if specs is not None:
        in_scope(place, base, specs)
    return run(place, "commit", *(["--amend"] if amend else []), "-F", "-", data=data)


def commit_base(place, rev) -> str:
    """`rev`'s full id, or the empty tree when it names no commit (an unborn branch, a root commit's parent)."""
    found = read(place, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}").strip()
    return found or read(place, "hash-object", "-t", "tree", "--stdin").strip()


def staged(place, base, options, specs=()) -> bytes:
    """diff-index's output for the index over `base`, every gitlink shown whatever the configuration ignores."""
    done = call(place, "diff-index", "--cached", "-z", "--ignore-submodules=none", *options, base, "--", *specs)
    if done.returncode != 0:
        raise Refused("scope" if "--name-only" in options else "gitlink",
                      f"git could not list the staged paths: {text(done.stderr).strip()}")
    return done.stdout


def no_gitlinks(place, base) -> None:
    """A gitlink added, removed or moved, in either mode field of diff-index --raw, is the caller's to narrow out."""
    fields = staged(place, base, ["--raw", "--no-renames"]).split(b"\0")
    found = [os.fsdecode(path) for header, path in zip(fields[0::2], fields[1::2])
             if GITLINK in header.lstrip(b":").split()[:2]]
    if found:
        raise Refused("gitlink", "the commit changes a submodule pointer; unstage it:\n" + shown_lines(found))


def scope_specs(place, path) -> list:
    """The scope file's pathspecs: one per line, `#` comments and blank lines skipped, literal as every pathspec."""
    lines = message(place, path, "scope").decode("utf-8", "surrogateescape").split("\n")
    specs = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    bad = next((spec for spec in specs if CONTROL_CHARACTERS.search(spec)), None)
    if bad is not None:
        raise Refused("scope", f"the scope file's line {owner_git.shown(repr(bad))} holds a control byte")
    return specs


def in_scope(place, base, specs) -> None:
    """Every path the commit changes, a rename under its new path, is one the scope file's pathspecs list."""
    every = [os.fsdecode(name) for name in staged(place, base, ["--name-only", "-M"]).split(b"\0") if name]
    listed = set()
    if specs:
        listed = {os.fsdecode(name) for name in staged(place, base, ["--name-only", "-M"], specs).split(b"\0")}
    outside = [name for name in every if name not in listed]
    if outside:
        raise Refused("scope", "the commit touches paths outside the scope file:\n" + shown_lines(outside))


def shown_lines(names) -> str:
    return "\n".join(CONTROL_CHARACTERS.sub("", owner_git.shown(name)) for name in names) + "\n"


def amendable(place) -> None:
    """HEAD is no merge, and no remote-tracking ref holds it: an amend of a pushed commit is a force-push later."""
    parents = read(place, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:]
    if len(parents) > 1:
        raise Refused("amend-merge", f"HEAD has {len(parents)} parents; make a new commit instead")
    held = call(place, "for-each-ref", "--contains=HEAD", "--format=%(refname)", "refs/remotes/")
    if held.returncode != 0 or held.stdout.strip():
        where = text(held.stdout.split(b"\n")[0]) if held.returncode == 0 else "a ref that cannot be read"
        raise Refused("amend-pushed", f"HEAD is already in {where}; make a new commit on top instead")


def untracked(place, branch) -> None:
    """Unmanaged: refused when a remote-tracking ref ends in this branch's name or the branch has an upstream, as of
    the last fetch: a reset, or a lease push, of it rewrites what a remote holds."""
    refs = call(place, "for-each-ref", "--format=%(refname)", "refs/remotes/")
    folded = "/" + branch.lower()
    named = [ref for ref in text(refs.stdout).splitlines() if ref.lower().endswith(folded)] if refs.returncode == 0 else []
    upstream = call(place, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{branch}@{{upstream}}")
    if refs.returncode != 0 or named or upstream.returncode == 0:
        where = named[0] if named else "its upstream" if upstream.returncode == 0 else "a ref that cannot be read"
        raise Refused("branch-tracked", f"{owner_git.shown(branch)} is tracked by {where}: a remote holds it, so it is "
                                        f"not rewritten here; make a new branch, or run git yourself")


def reset(place, mode, target):
    branch = own_head(place)
    if place.slug is None:
        untracked(place, branch)
    known_commit(place, target)
    old_tip(place, "reset", branch)
    return run(place, "reset", mode, target)


def old_tip(place, verb, branch) -> None:
    place.shown.append((sys.stdout, f"rw-git: {verb}: {branch} was {read(place, 'rev-parse', 'HEAD').strip()}\n"))


def switch(place, create, branch):
    if place.slug is None:
        unstopped(place)
    if create or place.slug is not None:
        own_branch(place, branch)
    if create:
        return run(place, "switch", "--no-track", f"--create={branch}")
    return run(place, "switch", "--no-guess", branch)


def rebase(place, autosquash, target):
    branch = own_head(place)
    known_commit(place, target)
    old_tip(place, "rebase", branch)
    return run(place, "rebase", "--no-update-refs", "--no-autostash",
               *(["--autosquash"] if autosquash else []), target)


def rebase_onto(place, new, upstream):
    branch = own_head(place)
    known_commit(place, new)
    known_commit(place, upstream)
    old_tip(place, "rebase", branch)
    return run(place, "rebase", "--no-update-refs", "--no-autostash", "--onto", new, upstream)


def rebase_step(place, step):
    in_progress(place, "rebase-merge")
    # git opens the editor on the commit a resolved conflict makes; `true` keeps the message git prepared.
    return run(place, *(["-c", "core.editor=true"] if step == "--continue" else []), "rebase", step)


def pick(place, target):
    own_head(place)
    known_commit(place, target)
    return run(place, "cherry-pick", target)


def pick_step(place, step):
    own_head(place, settled=False)
    return run(place, "cherry-pick", step)


def stash_push(place, *paths):
    own_head(place)
    return run(place, "stash", "push", f"--message=rw-git {stash_tag(place)}", "--", *inside(place, paths))


def stash_tag(place) -> str:
    """The slug, or an unmanaged checkout's canonical path: a slug holds no `/`, so neither is taken for the other."""
    return place.slug or place.worktree


def stash_entries(place) -> list:
    """(id, subject) of every stash entry, newest first."""
    lines = read(place, "log", "--walk-reflogs", "--format=%H%x00%gs", "refs/stash").splitlines()
    return [tuple(line.split("\0", 1)) for line in lines if "\0" in line]


def stash_pop(place):
    if place.slug is None:
        own_head(place)
    tag = f": rw-git {stash_tag(place)}"
    mine = next((entry for entry, subject in stash_entries(place) if subject.endswith(tag)), None)
    if mine is None:
        raise Refused("stash-none", f"no stash entry is this worktree's ({owner_git.shown(stash_tag(place))})")
    code = run(place, "stash", "apply", mine)
    if code != 0:
        return code
    # Re-found by id just before the drop: another worktree may have pushed an entry since.
    number = next((n for n, (entry, _) in enumerate(stash_entries(place)) if entry == mine), None)
    return code if number is None else run(place, "stash", "drop", f"stash@{{{number}}}")


def fetch(place, remote):
    name = known_remote(place, remote, False)
    return run(place, "-c", f"remote.{name}.mirror=false", "fetch", UPLOAD_PACK, "--no-tags", "--no-recurse-submodules",
               "--no-prune", "--refmap=", "--no-auto-maintenance", "--no-write-commit-graph", name,
               f"+refs/heads/*:refs/remotes/{name}/*")


def push(place, lease, branch, remote):
    own_branch(place, branch)
    if place.slug is None:
        own_head(place)
        if lease:
            untracked(place, branch)
    name = known_remote(place, remote, True)
    publishes(place)
    return run(place, "-c", f"remote.{name}.mirror=false", "push", RECEIVE_PACK, "--no-recurse-submodules",
               *([f"--force-with-lease=refs/heads/{branch}"] if lease else []), name,
               f"refs/heads/{branch}:refs/heads/{branch}")


def known_remote(place, remote, is_push) -> str:
    """origin when no name is given; else a remote this repository configures, by a name of one plain segment, and
    for a push one launch.json's `push_remotes` lists for it. Its URL comes from the repository's configuration, and
    only the ssh and https transports carry it."""
    if remote is None:
        return "origin"
    if not REMOTE_NAME.fullmatch(remote) or remote not in read(place, "remote").splitlines():
        raise Refused("remote-unknown", f"{owner_git.shown(remote)} is not a remote configured in {place.repo}")
    if is_push and remote != "origin" and remote not in push_remotes(place.repo):
        raise Refused("remote-unknown", f"{owner_git.shown(remote)} is not origin, and launch.json's `push_remotes` "
                                        f"does not list it for {place.repo}")
    return remote


def push_remotes(repo) -> tuple:
    """launch.json's `push_remotes` list for `repo`: an object from a repository path, as `repos` spells one, to remote
    names of one plain segment; empty when there is none. Any entry out of shape is refused by name."""
    try:
        value = role_grants.launch_config().get("push_remotes")
    except role_grants.Refused as refusal:
        raise Refused("launch-config", str(refusal)) from None
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise Refused("launch-config", "`push_remotes` in launch.json is not an object from a repository path to a "
                                       "list of remote names")
    found = ()
    for key, names in value.items():
        if not owner_git.REPO_ENTRY.fullmatch(key):
            raise Refused("launch-config", f"the `push_remotes` key {owner_git.shown(repr(key))} is not an absolute "
                                           f"or ~/ path")
        if not (isinstance(names, list) and all(isinstance(n, str) and REMOTE_NAME.fullmatch(n) for n in names)):
            raise Refused("launch-config", f"`push_remotes` for {owner_git.shown(key)} is not a list of remote names "
                                           f"of one plain segment")
        if os.path.realpath(owner_git.home_path(key)) == repo:
            found = tuple(names)
    return found


class RepositoryLock:
    """One rw-git at a time per repository, from its checks to git's last write: a second call's `switch` or `add`
    would otherwise move HEAD or the index between them. Taken in the shared git directory, which every worktree's
    branches and stash share; waited for LOCK_WAIT seconds, since a stalled call holds it for every worktree."""

    def __init__(self, place):
        try:
            common = role_grants.common_dir(place.repo)
        except role_grants.Refused as refusal:
            raise Refused("worktree-foreign-gitdir", str(refusal)) from None
        if common is None:
            raise Refused("worktree-unlisted", f"{place.repo} has no git directory")
        self.path = os.path.join(common, LOCK_FILE)

    def __enter__(self):
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        except OSError as error:
            raise Refused("worktree-foreign-gitdir",
                          f"{self.path} cannot be opened ({owner_git.shown(error)})") from None
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(self.fd)
                    raise Refused("repo-busy", f"another rw-git has held {self.path} for {LOCK_WAIT} s") from None
                time.sleep(LOCK_RETRY)

    def __exit__(self, *_):
        os.close(self.fd)


def owner_home() -> str:
    """The account's home, from the account database: HOME and XDG_CONFIG_HOME choose launch.json and git's global
    config, whose credential helpers rw-git puts back, and the caller sets both."""
    return pwd.getpwuid(os.getuid()).pw_dir


def main(args) -> int:
    kept = {name: value for name, value in os.environ.items() if name in KEPT or name.startswith("LC_")}
    os.environ.clear()
    os.environ.update(kept, PATH=SAFE_PATH, HOME=owner_home())
    if args in (["--help"], ["-h"]):
        print(HELP)
        return 0
    try:
        handler, values = parse(args)
        place = locate()
        try:
            with RepositoryLock(place):
                return handler(place, *values)
        finally:
            # Written once the lock is released, so a caller that never reads its pipe holds up no other rw-git.
            for stream, shown in place.shown:
                owner_git.emit(stream, shown)
    except Refused as refusal:
        owner_git.emit(sys.stderr, f"refused: {refusal.code}: {owner_git.shown(refusal.detail)}\n")
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
