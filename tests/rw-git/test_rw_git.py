#!/usr/bin/env python3
"""Tests for rw_git.py, the program a sandboxed session runs, outside its sandbox, to write a repository's git directory.

    python3 tests/rw-git/test_rw_git.py

Every test builds a scratch HOME with a made-up identity and a launch.json listing one scratch repository, `sample`,
with a linked worktree at <repo>/.worktrees/sample-001-x on robowright/sample-001-x. BEHAVIORS.md is the table; each
test's docstring starts with its row. A planted program is a script that only touches a file under the scratch
`markers/` folder and exits 1: a marker that exists is a program git ran.

Every test runs rw_git through RUNNER, which points the module's account home at the scratch HOME: rw-git takes its
home from the account database, never from the environment, and a test must never read the real one. A test that
needs a remote also widens the module's protocol list to `file` and `http` (a scratch remote is neither ssh nor https)
and drops the system configuration's credential helpers, so no test asks the Owner's keychain. P1 checks the shipped
protocol list unpatched.
"""

import fcntl
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
from pathlib import Path

CLONE = Path(__file__).resolve().parents[2]
SCRIPTS = CLONE / "skills" / "robowright" / "scripts"
TOOL = SCRIPTS / "rw_git.py"
GIT = "/usr/bin/git"
# The test's own git runs nothing a planted key names: no hook, fsmonitor, signing, gc, attribute from a checkout,
# or the `mark` driver info/attributes names.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
TEST_GIT = [GIT, f"--attr-source={EMPTY_TREE}", "-c", "core.attributesFile=/dev/null", "-c", "core.hooksPath=/dev/null",
            "-c", "core.fsmonitor=false", "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false", "-c", "gc.auto=0",
            "-c", "maintenance.auto=false", "-c", "filter.mark.clean=", "-c", "filter.mark.smudge=", "-c",
            "filter.mark.process=", "-c", "filter.mark.required=false", "-c", "merge.mark.driver="]
SLUG = "sample-001-x"
BRANCH = f"robowright/{SLUG}"
OTHER_SLUG = "sample-002-y"
OTHER_BRANCH = f"robowright/{OTHER_SLUG}"
NAME, EMAIL = "Sample Builder", "builder@example.invalid"
RUNNER = """import os, sys
sys.path.insert(0, sys.argv[1])
import rw_git
home = os.environ.pop("RW_TEST_HOME")
rw_git.owner_home = lambda: home
temp = os.environ.pop("RW_TEST_TEMP")
rw_git.own_temp_folders = lambda: [temp]
if "RW_TEST_LOCK_WAIT" in os.environ:
    rw_git.LOCK_WAIT = float(os.environ.pop("RW_TEST_LOCK_WAIT"))
if sys.argv[2] == "remote":
    rw_git.PROTOCOLS = rw_git.PROTOCOLS + ("file", "http")
    owner_helpers = rw_git.owner_helpers
    rw_git.owner_helpers = lambda *args: [found for found in owner_helpers(*args) if found[0] not in ("system", "unknown")]
sys.exit(rw_git.main(sys.argv[3:]))
"""
HOOK_NAMES = ("applypatch-msg", "pre-applypatch", "post-applypatch", "pre-commit", "pre-merge-commit",
              "prepare-commit-msg", "commit-msg", "post-commit", "pre-rebase", "post-checkout", "post-merge",
              "pre-push", "post-rewrite", "reference-transaction", "pre-auto-gc", "post-index-change",
              "sendemail-validate", "fsmonitor-watchman", "p4-pre-submit", "push-to-checkout")
MESSAGE_LIMIT = 64 * 1024


class Origin(http.server.BaseHTTPRequestHandler):
    """An http remote that answers every request 401 with a cookie, or 404 once it sees credentials."""

    def do_GET(self):
        self.server.seen.append(dict(self.headers))
        if self.headers.get("Authorization"):
            self.send_response(404)
        else:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="sample"')
        self.send_header("Set-Cookie", "sample=1; Path=/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class RwGitCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        self.home = self.root / "home"
        self.home.mkdir()
        (self.home / ".gitconfig").write_text(f"[user]\n\tname = {NAME}\n\temail = {EMAIL}\n")
        self.markers = self.root / "markers"
        self.markers.mkdir()
        self.programs = self.root / "programs"
        self.programs.mkdir()
        self.sessions = self.root / "sessions"
        self.projects = self.root / "projects"
        self.repo = self.given_repo(self.root / "repos" / "sample")
        self.worktree = self.given_worktree(self.repo, f".worktrees/{SLUG}", BRANCH)
        self.session = self.given_session(SLUG)
        self.given_launch_json({"repos": [str(self.repo)], "sessions_root": str(self.sessions),
                                "projects_root": str(self.projects)})
        self.runner = self.root / "runner.py"
        self.runner.write_text(RUNNER)

    # -- scratch git, run directly as the test ---------------------------------------------------------------------

    def env(self, **extra):
        return {"HOME": str(self.home), "PATH": os.environ["PATH"], "TMPDIR": str(self.root),
                "GIT_CONFIG_NOSYSTEM": "1", **extra}

    def git(self, where, *args, check=True):
        done = subprocess.run([*TEST_GIT, "-C", str(where), *args], capture_output=True, text=True, env=self.env(),
                              stdin=subprocess.DEVNULL)
        if check:
            self.assertEqual(done.returncode, 0, f"git {args}: {done.stderr}")
        return done.stdout.strip()

    def given_repo(self, path):
        path.mkdir(parents=True)
        self.git(path, "init", "-q", "-b", "main")
        (path / "README").write_text("base\n")
        self.git(path, "add", "README")
        self.git(path, "commit", "-q", "-m", "base")
        with open(path / ".git" / "info" / "exclude", "a") as exclude:
            exclude.write(".worktrees/\n.claude/\n")
        return path

    def given_worktree(self, repo, place, branch):
        path = repo / place
        self.git(repo, "worktree", "add", "-q", "-b", branch, str(path))
        return path

    def given_session(self, slug):
        folder = self.sessions / slug
        folder.mkdir(parents=True)
        return folder

    def given_launch_json(self, config):
        path = self.home / ".claude" / "robowright" / "launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config) + "\n")

    def given_hook(self, strategy):
        hook = self.repo / ".claude" / "robowright" / "project.md"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(f"# Project hook\n\n## 10 · Publishing\n\npublish_strategy: {strategy}\n\nprose\n")

    def given_message(self, text="sample: a change\n", folder=None, name="commit-message.txt"):
        path = (folder or self.session) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def given_origin(self):
        origin = self.root / "origin.git"
        self.git(self.root, "init", "-q", "--bare", "-b", "main", str(origin))
        self.git(self.repo, "remote", "add", "origin", str(origin))
        self.git(self.repo, "push", "-q", "origin", "main")
        return origin

    def given_http_origin(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        server.seen = []
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/sample.git"
        self.git(self.repo, "remote", "add", "origin", url)
        return server, url

    def program(self, name):
        """A script that touches markers/<name> and exits 1."""
        path = self.programs / name
        path.write_text(f"#!/bin/sh\ntouch '{self.markers / name}'\nexit 1\n")
        path.chmod(0o755)
        return path

    def marked(self):
        return sorted(p.name for p in self.markers.iterdir())

    def commit_in(self, where, name, text, message):
        (where / name).write_text(text)
        self.git(where, "add", name)
        self.git(where, "commit", "-q", "-m", message)
        return self.git(where, "rev-parse", "HEAD")

    def head(self, where=None):
        return self.git(where or self.worktree, "rev-parse", "HEAD")

    def branch(self, where=None):
        return self.git(where or self.worktree, "symbolic-ref", "-q", "--short", "HEAD", check=False)

    def staged(self, where=None):
        return self.git(where or self.worktree, "diff", "--cached", "--name-only").splitlines()

    def given_conflict(self):
        """The branch and main both change README; returns (branch tip, main tip)."""
        tip = self.commit_in(self.worktree, "README", "branch\n", "branch edit")
        base = self.commit_in(self.repo, "README", "main\n", "main edit")
        return tip, base

    # -- rw-git ----------------------------------------------------------------------------------------------------

    def rw(self, *args, cwd=None, env=None, remote=False, timeout=60):
        """(exit code, stdout, stderr) of rw-git run in `cwd` (the worktree), through RUNNER when `remote`."""
        program = [sys.executable, "-I", str(self.runner), str(SCRIPTS), "remote" if remote else "local"]
        env = env or {"HOME": str(self.home), "PATH": os.environ["PATH"], "TMPDIR": str(self.root)}
        done = subprocess.run(program + list(args), cwd=str(cwd or self.worktree), capture_output=True, text=True,
                              env={**env, "RW_TEST_HOME": str(self.home), "RW_TEST_TEMP": str(self.root / "temp")}, stdin=subprocess.DEVNULL, timeout=timeout)
        return done.returncode, done.stdout, done.stderr

    def ok(self, *args, **kwargs):
        code, out, err = self.rw(*args, **kwargs)
        self.assertEqual(code, 0, f"rw-git {args}: {err}")
        return out

    def refused(self, code_name, *args, **kwargs):
        code, out, err = self.rw(*args, **kwargs)
        self.assertEqual(code, 2, f"rw-git {args}: exit {code}: {err}")
        self.assertIn(f"refused: {code_name}:", err, f"rw-git {args}")
        return err


class WhereItRunsTests(RwGitCase):
    def test_add__a_worktree_of_a_listed_repository_is_served(self):
        """W1 · in <repo>/.worktrees/<slug>, `add f` stages f, exit 0."""
        (self.worktree / "f").write_text("x\n")

        self.ok("add", "f")

        self.assertEqual(self.staged(), ["f"])

    def test_add__the_main_checkout_of_a_listed_repository_is_served(self):
        """W2 · in the main checkout, `add f` stages f, exit 0."""
        (self.repo / "f").write_text("x\n")

        self.ok("add", "f", cwd=self.repo)

        self.assertEqual(self.staged(self.repo), ["f"])

    def test_add__a_checkout_of_a_repository_repos_does_not_list_is_refused(self):
        """W3 · a second repository launch.json does not list: worktree-unlisted, exit 2, nothing staged."""
        other = self.given_repo(self.root / "repos" / "other")
        (other / "f").write_text("x\n")

        self.refused("worktree-unlisted", "add", "f", cwd=other)

        self.assertEqual(self.staged(other), [])

    def test_add__a_subdirectory_of_a_worktree_is_refused(self):
        """W4 · cwd <worktree>/sub is no worktree: worktree-unlisted, nothing staged."""
        (self.worktree / "sub").mkdir()
        (self.worktree / "sub" / "f").write_text("x\n")

        self.refused("worktree-unlisted", "add", "f", cwd=self.worktree / "sub")

        self.assertEqual(self.staged(), [])

    def test_add__no_repos_in_launch_json_trusts_nothing(self):
        """W5 · launch.json without `repos`: launch-config, exit 2, nothing staged."""
        self.given_launch_json({"sessions_root": str(self.sessions)})
        (self.worktree / "f").write_text("x\n")

        self.refused("launch-config", "add", "f")

        self.assertEqual(self.staged(), [])

    def test_add__a_repos_entry_spelled_through_a_link_is_refused(self):
        """W6 · `repos` names the repository through a symlink: launch-config naming the link."""
        link = self.root / "linked"
        link.symlink_to(self.repo)
        self.given_launch_json({"repos": [str(link)], "sessions_root": str(self.sessions)})
        (self.worktree / "f").write_text("x\n")

        err = self.refused("launch-config", "add", "f")

        self.assertIn(str(link), err)
        self.assertEqual(self.staged(), [])

    def test_add__a_worktree_whose_git_file_names_another_git_dir_is_refused(self):
        """W7 · the worktree's .git names the main clone's git dir: worktree-foreign-gitdir."""
        (self.worktree / ".git").write_text(f"gitdir: {self.repo / '.git'}\n")
        (self.worktree / "f").write_text("x\n")

        self.refused("worktree-foreign-gitdir", "add", "f")

    def assert_says_what_rw_git_serves(self, err):
        self.assertIn("`repos`", err)
        self.assertIn("`desktop_roots`", err)
        self.assertIn("granted folder", err)

    def test_add__a_directory_outside_every_listed_checkout_is_told_what_rw_git_serves(self):
        """W7.1 · an unlisted repository: worktree-unlisted naming `repos`, `desktop_roots` and a granted folder — a refusal naming `repos` alone sends the Owner to the wrong key."""
        other = self.given_repo(self.root / "repos" / "other")

        err = self.refused("worktree-unlisted", "add", "f", cwd=other)

        self.assert_says_what_rw_git_serves(err)

    def test_add__a_directory_that_is_no_repository_is_told_the_same_and_nothing_about_being_one(self):
        """W7.2 · a plain directory: W7.1's text and no claim it is or is not a repository — rw-git runs no git there to find out."""
        plain = self.root / "plain"
        plain.mkdir()

        err = self.refused("worktree-unlisted", "add", "f", cwd=plain)

        self.assert_says_what_rw_git_serves(err)
        self.assertNotRegex(err, r"(?i)is (not )?a (git )?repository")

    def test_add__owner_gits_untrusted_hint_passes_through(self):
        """W7.3 · a robowright.json naming a repository `repos` does not list: owner_git's text and hint, not W7.1's — the hint names the launch.json line that fixes it."""
        other = self.given_repo(self.root / "repos" / "other")
        folder = self.projects / "notes"
        folder.mkdir(parents=True)
        (folder / "robowright.json").write_text(json.dumps({"project": "notes", "repos": [
            {"name": "other", "path": str(other), "origin": "git@example.invalid:other.git"}]}) + "\n")

        err = self.refused("worktree-unlisted", "add", "f", cwd=other)

        self.assertIn("is not a worktree of a repository that `repos`", err)
        self.assertIn("a robowright.json names", err)
        self.assertNotIn("`desktop_roots`", err)

    def test_add__a_foreign_git_dir_passes_through(self):
        """W7.4 · W7's fixture: owner_git's foreign-gitdir text, not W7.1's — the fix is the worktree's .git file, not a grant."""
        (self.worktree / ".git").write_text(f"gitdir: {self.repo / '.git'}\n")

        err = self.refused("worktree-foreign-gitdir", "add", "f")

        self.assertIn("a git directory other than its own entry", err)
        self.assertNotIn("`desktop_roots`", err)

    def test_commit__a_worktree_at_the_old_place_keeps_working(self):
        """W8 · <repo>/.claude/worktrees/<slug> on robowright/<slug>: add and commit, exit 0, one commit on the branch."""
        legacy = self.given_worktree(self.repo, f".claude/worktrees/{OTHER_SLUG}", OTHER_BRANCH)
        message = self.given_message(folder=self.given_session(OTHER_SLUG))
        before = self.head(legacy)
        (legacy / "f").write_text("x\n")

        self.ok("add", "f", cwd=legacy)
        self.ok("commit", "--message-file", str(message), cwd=legacy)

        self.assertEqual(self.git(legacy, "rev-parse", "HEAD~1"), before)
        self.assertEqual(self.branch(legacy), OTHER_BRANCH)


class EnvironmentTests(RwGitCase):
    def test_add__git_dir_from_the_caller_is_dropped(self):
        """E1 · GIT_DIR names a second repository: f is staged in the worktree, the second repository's index unchanged."""
        other = self.given_repo(self.root / "repos" / "other")
        (self.worktree / "f").write_text("x\n")

        self.ok("add", "f", env={"HOME": str(self.home), "PATH": os.environ["PATH"], "GIT_DIR": str(other / ".git")})

        self.assertEqual(self.staged(), ["f"])
        self.assertEqual(self.staged(other), [])

    def test_commit__config_from_the_caller_environment_is_dropped(self):
        """E2 · GIT_CONFIG_PARAMETERS and GIT_CONFIG_COUNT carry an fsmonitor and an author: no marker, the scratch author."""
        fsmonitor = self.program("env-fsmonitor")
        env = {"HOME": str(self.home), "PATH": os.environ["PATH"],
               "GIT_CONFIG_PARAMETERS": f"'core.fsmonitor={fsmonitor}' 'user.name=Planted Name'",
               "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.email", "GIT_CONFIG_VALUE_0": "planted@example.invalid"}
        (self.worktree / "f").write_text("x\n")

        self.ok("add", "f", env=env)
        self.ok("commit", "--message-file", str(self.given_message()), env=env)

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%an <%ae>"), f"{NAME} <{EMAIL}>")

    def test_fetch__an_exec_path_from_the_caller_is_dropped(self):
        """E3 · GIT_EXEC_PATH names a folder holding a git-remote-http: fetch from an http origin, no marker."""
        server, _ = self.given_http_origin()
        exec_path = self.root / "exec-path"
        exec_path.mkdir()
        shutil.copy(self.program("git-remote-http"), exec_path / "git-remote-http")

        self.rw("fetch", remote=True, env={"HOME": str(self.home), "PATH": os.environ["PATH"],
                                           "GIT_EXEC_PATH": str(exec_path)})

        self.assertEqual(self.marked(), [])
        self.assertNotEqual(server.seen, [])

    def test_add__git_comes_from_a_fixed_path_not_path(self):
        """E4 · a `git` first on PATH: no marker, f staged."""
        fake = self.root / "fake-bin"
        fake.mkdir()
        shutil.copy(self.program("git"), fake / "git")
        (self.worktree / "f").write_text("x\n")

        self.ok("add", "f", env={"HOME": str(self.home), "PATH": f"{fake}:{os.environ['PATH']}"})

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.staged(), ["f"])

    @unittest.skipUnless(sys.platform == "darwin", "/usr/bin/git is an xcrun shim only on macOS")
    def test_add__developer_dir_from_the_caller_is_dropped(self):
        """E7 · DEVELOPER_DIR names a folder whose usr/bin/xcrun is a marker, the program /usr/bin/git's shim runs:
        no marker, f staged."""
        developer = self.root / "planted-developer"
        (developer / "usr" / "bin").mkdir(parents=True)
        shutil.copy(self.program("xcrun"), developer / "usr" / "bin" / "xcrun")
        (self.worktree / "f").write_text("x\n")

        self.ok("add", "f", env={"HOME": str(self.home), "PATH": os.environ["PATH"], "DEVELOPER_DIR": str(developer)})

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.staged(), ["f"])

    def given_planted_helper(self, config):
        """A git config at `config` naming a marker credential helper, the kind rw-git puts back from a global file."""
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(f"[credential]\n\thelper = {self.program('planted-helper')}\n")

    def test_fetch__home_comes_from_the_account_not_the_environment(self):
        """E5 · HOME names a folder with a launch.json listing the repository and a .gitconfig naming a helper: fetch
        from an http origin, no marker, the origin reached."""
        server, _ = self.given_http_origin()
        planted = self.root / "planted-home"
        shutil.copytree(self.home / ".claude", planted / ".claude")
        self.given_planted_helper(planted / ".gitconfig")

        self.rw("fetch", remote=True, env={"HOME": str(planted), "PATH": os.environ["PATH"]})

        self.assertEqual(self.marked(), [])
        self.assertNotEqual(server.seen, [])

    def test_fetch__xdg_config_home_from_the_caller_is_dropped(self):
        """E6 · XDG_CONFIG_HOME names a folder whose git/config names a helper: fetch from an http origin, no marker,
        the origin reached."""
        server, _ = self.given_http_origin()
        planted = self.root / "planted-xdg"
        self.given_planted_helper(planted / "git" / "config")

        self.rw("fetch", remote=True, env={"HOME": str(self.home), "PATH": os.environ["PATH"],
                                           "XDG_CONFIG_HOME": str(planted)})

        self.assertEqual(self.marked(), [])
        self.assertNotEqual(server.seen, [])


class SubcommandTests(RwGitCase):
    def test_add__stages_exactly_the_named_paths_relative_or_absolute(self):
        """S1 · `add a <abs>/b` stages a and b, not c."""
        for name in ("a", "b", "c"):
            (self.worktree / name).write_text("x\n")

        self.ok("add", "a", str(self.worktree / "b"))

        self.assertEqual(self.staged(), ["a", "b"])

    def test_restore__staged_unstages_and_leaves_the_file(self):
        """S2 · `restore --staged f`: not staged, the file unchanged."""
        (self.worktree / "f").write_text("x\n")
        self.git(self.worktree, "add", "f")

        self.ok("restore", "--staged", "f")

        self.assertEqual(self.staged(), [])
        self.assertEqual((self.worktree / "f").read_text(), "x\n")

    def test_restore__puts_the_index_copy_back(self):
        """S3 · a tracked file edited: `restore README` and it reads as committed."""
        (self.worktree / "README").write_text("mutated\n")

        self.ok("restore", "README")

        self.assertEqual((self.worktree / "README").read_text(), "base\n")

    def test_commit__is_the_commit_git_commit_f_makes_today(self):
        """S4 · the scratch identity, no signature, and the message bytes `git commit -F` writes in a twin repository."""
        text = "\n\nsample: a change  \n\nwhy it changed\t\n# kept as written\n\n\n"
        message = self.given_message(text)
        twin = self.given_repo(self.root / "twin")
        (twin / "f").write_text("x\n")
        self.git(twin, "add", "f")
        self.git(twin, "commit", "-q", "-F", str(message))
        (self.worktree / "f").write_text("x\n")
        self.git(self.worktree, "add", "f")
        parent = self.head()

        self.ok("commit", "--message-file", str(message))

        raw = self.git(self.worktree, "cat-file", "commit", "HEAD")
        self.assertNotIn("gpgsig", raw)
        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%an <%ae>|%cn <%ce>|%P"),
                         f"{NAME} <{EMAIL}>|{NAME} <{EMAIL}>|{parent}")
        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%B"), self.git(twin, "log", "-1", "--format=%B"))
        self.assertEqual(self.branch(), BRANCH)

    def test_switch__create_makes_the_hooks_branch(self):
        """S5 · `switch -c robowright/<slug>-u2`: on it."""
        self.ok("switch", "-c", f"{BRANCH}-u2")

        self.assertEqual(self.branch(), f"{BRANCH}-u2")

    def test_switch__goes_back_to_an_own_branch(self):
        """S6 · from robowright/<slug>-u2, `switch robowright/<slug>`: on it."""
        self.git(self.worktree, "switch", "-q", "-c", f"{BRANCH}-u2")

        self.ok("switch", BRANCH)

        self.assertEqual(self.branch(), BRANCH)

    def test_rebase__onto_a_full_id_and_names_the_old_tip(self):
        """S7 · the branch behind a new base: `rebase <id>` parents it there, stdout names the old tip."""
        self.commit_in(self.worktree, "f", "x\n", "branch work")
        old = self.head()
        base = self.commit_in(self.repo, "g", "y\n", "main moved")

        out = self.ok("rebase", base)

        self.assertEqual(self.git(self.worktree, "rev-parse", "HEAD~1"), base)
        self.assertIn(old, out)
        self.assertEqual(self.branch(), BRANCH)

    def test_rebase__autosquash_folds_a_fixup(self):
        """S8 · a commit and its `fixup!`: `rebase --autosquash <base>` leaves one commit."""
        base = self.head()
        self.commit_in(self.worktree, "f", "x\n", "add f")
        self.commit_in(self.worktree, "f", "y\n", "fixup! add f")

        self.ok("rebase", "--autosquash", base)

        self.assertEqual(self.git(self.worktree, "rev-list", "--count", f"{base}..HEAD"), "1")
        self.assertEqual((self.worktree / "f").read_text(), "y\n")

    def test_rebase__abort_and_continue_finish_a_stopped_rebase(self):
        """S9 · a conflicting rebase: --abort is back on the old tip; again, resolved, add, --continue rebases."""
        tip, base = self.given_conflict()
        self.assertEqual(self.rw("rebase", base)[0], 1)

        self.ok("rebase", "--abort")
        self.assertEqual(self.head(), tip)
        self.assertEqual(self.rw("rebase", base)[0], 1)
        (self.worktree / "README").write_text("resolved\n")
        self.ok("add", "README")
        self.ok("rebase", "--continue")

        self.assertEqual(self.git(self.worktree, "rev-parse", "HEAD~1"), base)
        self.assertEqual(self.branch(), BRANCH)

    def test_cherry_pick__applies_one_commit(self):
        """S10 · a commit on another own branch: `cherry-pick <id>` puts its change on HEAD."""
        self.git(self.worktree, "switch", "-q", "-c", f"{BRANCH}-u2")
        picked = self.commit_in(self.worktree, "f", "x\n", "on u2")
        self.git(self.worktree, "switch", "-q", BRANCH)

        self.ok("cherry-pick", picked)

        self.assertEqual((self.worktree / "f").read_text(), "x\n")
        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%s"), "on u2")

    def test_cherry_pick__abort_and_continue_finish_a_stopped_pick(self):
        """S11 · a conflicting pick: --abort is back; again, resolved, add, --continue picks."""
        tip, base = self.given_conflict()
        self.assertEqual(self.rw("cherry-pick", base)[0], 1)

        self.ok("cherry-pick", "--abort")
        self.assertEqual(self.head(), tip)
        self.assertEqual(self.rw("cherry-pick", base)[0], 1)
        (self.worktree / "README").write_text("resolved\n")
        self.ok("add", "README")
        self.ok("cherry-pick", "--continue")

        self.assertEqual(self.git(self.worktree, "rev-parse", "HEAD~1"), tip)
        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%s"), "main edit")

    def test_stash__pop_takes_this_worktrees_entry_only(self):
        """S12 · this worktree pushes, another pushes after: pop restores this one's change, the other's entry stays."""
        other = self.given_worktree(self.repo, f".worktrees/{OTHER_SLUG}", OTHER_BRANCH)
        (self.worktree / "README").write_text("mine\n")
        (other / "README").write_text("theirs\n")

        self.ok("stash", "push", "README")
        self.ok("stash", "push", "README", cwd=other)
        self.assertEqual((self.worktree / "README").read_text(), "base\n")
        self.ok("stash", "pop")

        self.assertEqual((self.worktree / "README").read_text(), "mine\n")
        entries = self.git(self.repo, "stash", "list", "--format=%gs").splitlines()
        self.assertEqual(len(entries), 1, entries)
        self.assertIn(OTHER_SLUG, entries[0])

    def test_fetch__moves_remote_tracking_branches_only(self):
        """S13 · origin's main gains a commit: fetch moves refs/remotes/origin/main, local main stays."""
        origin = self.given_origin()
        clone = self.root / "clone"
        self.git(self.root, "clone", "-q", str(origin), str(clone))
        moved = self.commit_in(clone, "g", "y\n", "origin moved")
        self.git(clone, "push", "-q", "origin", "main")
        local = self.head(self.repo)

        self.ok("fetch", remote=True)

        self.assertEqual(self.git(self.repo, "rev-parse", "refs/remotes/origin/main"), moved)
        self.assertEqual(self.head(self.repo), local)

    def test_push__the_own_branch_only_and_a_lease_rewrites_it(self):
        """S14 · draft-pr hook and a tag: push leaves origin with the branch and no tag; --force-with-lease rewrites it."""
        origin = self.given_origin()
        self.given_hook("draft-pr")
        self.commit_in(self.worktree, "f", "x\n", "branch work")
        self.git(self.worktree, "tag", "v1")

        self.ok("push", BRANCH, remote=True)
        self.assertEqual(self.git(origin, "rev-parse", f"refs/heads/{BRANCH}"), self.head())
        self.assertEqual(self.git(origin, "tag", "--list"), "")
        self.git(self.worktree, "commit", "-q", "--amend", "-m", "branch work, amended")
        self.ok("push", "--force-with-lease", BRANCH, remote=True)

        self.assertEqual(self.git(origin, "rev-parse", f"refs/heads/{BRANCH}"), self.head())

    def test_help__names_every_subcommand_refusal_and_exit_code(self):
        """S15 · `--help`: exit 0, each subcommand, refusal code and exit code named."""
        out = self.ok("--help")

        for word in ("add", "restore", "commit", "switch", "rebase", "cherry-pick", "stash", "fetch", "push",
                     "usage", "launch-config", "worktree-unlisted", "worktree-foreign-gitdir", "path-outside",
                     "branch-not-own", "head-not-own", "commit-unknown", "message-file", "push-unpublished",
                     "stash-none", "exit 0", "exit 1", "exit 2", "--amend", "reset --soft", "reset --keep", "--onto",
                     "branch-protected", "amend-pushed", "amend-merge", "protected_branches",
                     "main, master, develop, release/* and hotfix/*", "--scope-file", "scope", "gitlink", "--remote",
                     "remote-unknown", "branch-tracked"):
            self.assertIn(word, out)

    def test_fetch__an_owner_helper_keyed_by_a_url_holding_an_equals_sign_is_put_back_whole(self):
        """S16.1 · beside the Owner's global credential.helper, one under `[credential "https://h.invalid/p?a=b"]`:
        the http origin sees credentials, and git parses every option — `-c` splits that key at its first `=`, and git
        refuses the call before it connects (gate F4)."""
        server, _ = self.given_http_origin()
        helper = self.programs / "owner-helper"
        helper.write_text("#!/bin/sh\necho username=sample\necho password=sample\n")
        helper.chmod(0o755)
        with open(self.home / ".gitconfig", "a") as config:
            config.write(f'[credential]\n\thelper = {helper}\n[credential "https://h.invalid/p?a=b"]\n\thelper = {helper}\n')

        _, _, err = self.rw("fetch", remote=True)

        self.assertNotIn("unable to parse command-line config", err)
        self.assertTrue(any(seen.get("Authorization") for seen in server.seen), err)

    def test_fetch__the_owners_own_credential_helper_still_answers(self):
        """S16 · the Owner's global credential.helper: an http origin sees its credentials."""
        server, _ = self.given_http_origin()
        helper = self.programs / "owner-helper"
        helper.write_text("#!/bin/sh\necho username=sample\necho password=sample\n")
        helper.chmod(0o755)
        with open(self.home / ".gitconfig", "a") as config:
            config.write(f"[credential]\n\thelper = {helper}\n")

        self.rw("fetch", remote=True)

        self.assertTrue(any(seen.get("Authorization") for seen in server.seen), server.seen)


class RefusalTests(RwGitCase):
    def test_every_form_but_the_typed_subcommands_is_refused(self):
        """R1 · status, reset --hard, branch -D, config, init, commit -m, --no-verify, push --force, rebase -i/--exec,
        a leading -c: each usage, exit 2, and the edit and the branch survive."""
        (self.worktree / "README").write_text("edited\n")
        self.git(self.worktree, "branch", "keep")
        message = str(self.given_message())
        for args in (["status"], ["reset", "--hard"], ["branch", "-D", "keep"], ["config", "core.editor", "vi"],
                     ["init"], ["commit", "-m", "x"], ["commit", "--no-verify", "--message-file", message],
                     ["commit", "--message-file", message, "--amend"], ["push", "--force", BRANCH],
                     ["rebase", "-i", self.head()], ["rebase", "--exec", "true", self.head()],
                     ["-c", "core.editor=vi", "add", "README"], ["add"], [], ["stash", "drop"], ["fetch", "origin"],
                     ["switch", "--detach"], ["restore", "--source", "HEAD~1", "README"]):
            with self.subTest(args=args):
                self.refused("usage", *args)

        self.assertEqual((self.worktree / "README").read_text(), "edited\n")
        self.assertEqual(self.git(self.worktree, "branch", "--list", "keep"), "keep")

    def test_add__a_path_outside_the_worktree_is_refused(self):
        """R2 · ../x, /etc/hosts, sub/../../x: path-outside, nothing staged."""
        (self.worktree / "sub").mkdir()
        for path in ("../x", "/etc/hosts", "sub/../../x", str(self.repo / "README")):
            with self.subTest(path=path):
                self.refused("path-outside", "add", path)

        self.assertEqual(self.staged(), [])

    def test_add__a_path_through_a_linked_folder_is_refused(self):
        """R3 · link → a folder outside: `add link/f` is path-outside."""
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "f").write_text("x\n")
        (self.worktree / "link").symlink_to(outside)

        self.refused("path-outside", "add", "link/f")

        self.assertEqual(self.staged(), [])

    def test_add__a_path_naming_a_git_directory_is_refused(self):
        """R4 · .git/config and sub/.GIT/x: path-outside."""
        for path in (".git/config", "sub/.GIT/x", ".git"):
            with self.subTest(path=path):
                self.refused("path-outside", "add", path)

    def test_switch__create_makes_only_the_hooks_branch(self):
        """R5 · main, another session's branch, feature/x: branch-not-own, no branch made."""
        for name in ("main", OTHER_BRANCH, "feature/x", f"{BRANCH}-x", f"{BRANCH}/u2"):
            with self.subTest(name=name):
                self.refused("branch-not-own", "switch", "-c", name)
                self.assertEqual(self.git(self.repo, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{name}"),
                                 "main" if name == "main" else "")

    def test_switch__goes_only_to_an_own_branch(self):
        """R6 · `switch main`: branch-not-own, still on the own branch."""
        self.git(self.repo, "switch", "-q", "--detach")

        self.refused("branch-not-own", "switch", "main")

        self.assertEqual(self.branch(), BRANCH)

    def test_nothing_writes_history_on_a_branch_that_is_not_own(self):
        """R7 · on feature/x, then detached: commit, rebase, cherry-pick and stash push are head-not-own."""
        base = self.head()
        picked = self.commit_in(self.repo, "g", "y\n", "on main")
        message = str(self.given_message())
        (self.worktree / "README").write_text("edited\n")
        self.git(self.worktree, "add", "README")
        for move in (["switch", "-q", "-c", "feature/x"], ["switch", "-q", "--detach"]):
            self.git(self.worktree, *move)
            for args in (["commit", "--message-file", message], ["rebase", picked], ["cherry-pick", picked],
                         ["stash", "push", "README"]):
                with self.subTest(head=move[-1], args=args):
                    self.refused("head-not-own", *args)
                    self.assertEqual(self.head(), base)

    def test_commit__the_main_checkout_takes_no_message_from_a_session_folder(self):
        """R8 · the main checkout on notes, a message under the session's folder, no folder granted: message-file, and
        HEAD stays (U48 B1: an unmanaged checkout now commits, from a temp or granted folder only)."""
        self.git(self.repo, "switch", "-q", "-c", "notes")
        (self.repo / "f").write_text("x\n")
        self.git(self.repo, "add", "f")
        before = self.head(self.repo)

        self.refused("message-file", "commit", "--message-file", str(self.given_message()), cwd=self.repo)

        self.assertEqual(self.head(self.repo), before)

    def test_rebase_and_cherry_pick__take_a_full_id_of_a_commit_here(self):
        """R9 · a short id, a branch name, 40 hex naming nothing, a tree id: commit-unknown."""
        base = self.commit_in(self.repo, "g", "y\n", "on main")
        tree = self.git(self.repo, "rev-parse", "HEAD^{tree}")
        for target in (base[:12], "main", "0" * 40, tree, base.upper()):
            for verb in ("rebase", "cherry-pick"):
                with self.subTest(verb=verb, target=target):
                    self.refused("commit-unknown", verb, target)

    def test_commit__the_message_file_lies_under_the_sessions_own_folders(self):
        """R10 · in the worktree, in TMPDIR, another session's folder, another slug's prs/ folder: message-file."""
        project = self.projects / "sample"
        for path in (self.given_message(folder=self.worktree), self.given_message(folder=self.root),
                     self.given_message(folder=self.given_session(OTHER_SLUG)),
                     self.given_message(folder=project / "prs" / OTHER_SLUG),
                     self.given_message(folder=project / "prs" / SLUG / ".." / OTHER_SLUG)):
            (self.worktree / "f").write_text(str(path))
            self.git(self.worktree, "add", "f")
            with self.subTest(path=path):
                self.refused("message-file", "commit", "--message-file", str(path))
        self.ok("commit", "--message-file", str(self.given_message(folder=project / "prs" / SLUG)))

    def test_commit__the_message_file_is_read_without_following_a_link(self):
        """R11 · a symlink to an own file, a folder link on its path, a FIFO, 64 KiB + 1, a relative path: message-file."""
        real = self.given_message()
        (self.session / "link.txt").symlink_to(real)
        (self.session / "sub").symlink_to(self.session)
        fifo = self.session / "fifo"
        os.mkfifo(fifo)
        big = self.given_message("x" * (MESSAGE_LIMIT + 1), name="big.txt")
        (self.worktree / "f").write_text("x\n")
        self.git(self.worktree, "add", "f")
        before = self.head()
        for path in (str(self.session / "link.txt"), str(self.session / "sub" / "commit-message.txt"), str(fifo),
                     str(big), os.path.relpath(real, self.worktree)):
            with self.subTest(path=path):
                self.refused("message-file", "commit", "--message-file", path, timeout=20)

        self.assertEqual(self.head(), before)

    def test_push__leaves_only_where_the_hook_publishes_pushed_branches(self):
        """R12 · a local-branch hook, then no hook: push-unpublished, origin unchanged."""
        origin = self.given_origin()
        for strategy in ("local-branch", None):
            if strategy:
                self.given_hook(strategy)
            else:
                (self.repo / ".claude" / "robowright" / "project.md").unlink()
            with self.subTest(strategy=strategy):
                self.refused("push-unpublished", "push", BRANCH, remote=True)
                self.assertEqual(self.git(origin, "branch", "--list", BRANCH), "")

    def test_push__names_an_own_branch(self):
        """R13 · a draft-pr hook: `push main` is branch-not-own."""
        self.given_origin()
        self.given_hook("draft-pr")

        self.refused("branch-not-own", "push", "main", remote=True)
        self.refused("branch-not-own", "push", "--force-with-lease", "main", remote=True)

    def test_stash__pop_with_no_entry_of_this_worktree_pops_nothing(self):
        """R14 · only another worktree's entry: stash-none, the entry kept."""
        other = self.given_worktree(self.repo, f".worktrees/{OTHER_SLUG}", OTHER_BRANCH)
        (other / "README").write_text("theirs\n")
        self.ok("stash", "push", "README", cwd=other)

        self.refused("stash-none", "stash", "pop")

        self.assertEqual(len(self.git(self.repo, "stash", "list").splitlines()), 1)

    def test_commit__git_failing_is_exit_1(self):
        """R15 · nothing staged: exit 1, git's message on stderr."""
        code, _, err = self.rw("commit", "--message-file", str(self.given_message()))

        self.assertEqual(code, 1, err)
        self.assertNotIn("refused:", err)


class AttributeTests(RwGitCase):
    def given_attributes(self, text):
        (self.worktree / ".gitattributes").write_text(text)

    def blob(self, path):
        return subprocess.run(["git", "-C", str(self.worktree), "cat-file", "blob", f":{path}"], capture_output=True,
                              check=True).stdout

    def test_add__a_converting_attribute_is_refused(self):
        """R16 · filter, ident and working-tree-encoding: add of each, and add ., refused naming the attribute; nothing
        staged, no marker."""
        self.given_attributes("*.dat filter=ptr\n*.id ident\n*.enc working-tree-encoding=UTF-16\n")
        self.git(self.repo, "config", "filter.ptr.clean", str(self.program("clean")))
        for name, attribute in (("b.dat", "filter"), ("c.id", "ident"), ("d.enc", "working-tree-encoding")):
            (self.worktree / name).write_text("data\n")
        for paths, attribute in ((["b.dat"], "filter"), (["c.id"], "ident"), (["d.enc"], "working-tree-encoding"),
                                 (["."], "filter")):
            with self.subTest(paths):
                err = self.refused("attributes", "add", *paths)

                self.assertIn(attribute, err)
                self.assertEqual(self.staged(), [])
        self.assertEqual(self.marked(), [])

    def test_add__a_line_ending_attribute_refuses_a_carriage_return(self):
        """R17 · text eol=lf, and eol=crlf alone: a.txt and i.eol holding CRLF, each refused, nothing staged."""
        self.given_attributes("*.txt text eol=lf\n*.eol eol=crlf\n")
        for name in ("a.txt", "i.eol"):
            (self.worktree / name).write_bytes(b"one\r\ntwo\r\n")
            with self.subTest(name):
                err = self.refused("attributes", "add", name)

                self.assertIn(name, err)
                self.assertEqual(self.staged(), [])

    def test_add__a_line_ending_attribute_passes_a_file_git_would_not_convert(self):
        """R18 · text eol=lf, text=auto and -text: no CRLF, a NUL or a lone CR under auto, and -text: each staged byte for
        byte."""
        self.given_attributes("* text=auto\n*.txt text eol=lf\n*.raw -text eol=lf\n")
        files = {"b.txt": b"one\ntwo\n", "c.bin": b"\x00one\r\ntwo\r\n", "d.raw": b"one\r\ntwo\r\n",
                 "e.bin": b"one\rtwo\r\n", "f.bin": b"one\r\ntwo\r", "g.txt": b"one\rtwo\n"}
        for name, content in files.items():
            (self.worktree / name).write_bytes(content)

        self.ok("add", *files)

        self.assertEqual(self.staged(), sorted(files))
        for name, content in files.items():
            self.assertEqual(self.blob(name), content, name)


    def test_add__the_check_reads_no_fifo_and_follows_no_link(self):
        """R19 · * text, a FIFO p.txt and a link l.txt to a CRLF file outside: add . returns, exit 0, l.txt a link."""
        self.given_attributes("* text\n")
        os.mkfifo(self.worktree / "p.txt")
        outside = self.root / "outside.txt"
        outside.write_bytes(b"one\r\n")
        (self.worktree / "l.txt").symlink_to(outside)

        self.ok("add", ".", timeout=20)

        self.assertIn("l.txt", self.staged())
        self.assertEqual(self.git(self.worktree, "ls-files", "-s", "l.txt").split()[0], "120000")

    def test_add__a_listed_folder_is_no_file_to_scan(self):
        """R20 · * text, an untracked nested repository sub/, and a tracked t.txt now a folder: add . exits 0."""
        (self.worktree / "t.txt").write_text("one\n")
        self.git(self.worktree, "add", "t.txt")
        self.git(self.worktree, "commit", "-q", "-m", "t")
        (self.worktree / "t.txt").unlink()
        (self.worktree / "t.txt").mkdir()
        (self.worktree / "t.txt" / "f").write_text("one\n")
        self.given_attributes("* text\n")
        nested = self.given_repo(self.worktree / "sub")

        code, _, err = self.rw("add", ".")

        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        self.assertTrue(nested.exists())
        self.assertIn("t.txt/f", self.staged())

    def test_add__a_forced_text_refuses_a_crlf_beside_a_nul(self):
        """R21 · *.txt text, and the older *.old crlf: a.txt holding CRLF and a NUL, h.old holding CRLF, each refused,
        nothing staged."""
        self.given_attributes("*.txt text\n*.old crlf\n")
        (self.worktree / "a.txt").write_bytes(b"one\r\ntwo\x00\r\n")
        (self.worktree / "h.old").write_bytes(b"one\r\ntwo\r\n")
        for name in ("a.txt", "h.old"):
            with self.subTest(name):
                self.refused("attributes", "add", name)

                self.assertEqual(self.staged(), [])

    def test_add__the_scan_follows_no_link_at_any_folder(self):
        """R22 · d/f tracked, then d a link to an outside folder whose f holds CRLF, * text: add d exits 0."""
        (self.worktree / "d").mkdir()
        (self.worktree / "d" / "f").write_text("one\n")
        self.git(self.worktree, "add", "d/f")
        self.git(self.worktree, "commit", "-q", "-m", "d")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "f").write_bytes(b"one\r\n")
        shutil.rmtree(self.worktree / "d")
        (self.worktree / "d").symlink_to(outside)
        self.given_attributes("* text\n")

        code, _, err = self.rw("add", "d")

        self.assertEqual(code, 0, err)

    def test_add__a_deletion_is_staged_whatever_its_attributes(self):
        """R23 · *.dat filter=ptr, b.dat tracked then deleted: add b.dat exits 0, the deletion staged."""
        self.given_attributes("*.dat filter=ptr\n")
        (self.worktree / "b.dat").write_text("data\n")
        self.git(self.worktree, "-c", "core.attributesFile=/dev/null", "add", "b.dat")
        self.git(self.worktree, "commit", "-q", "-m", "b")
        (self.worktree / "b.dat").unlink()

        self.ok("add", "b.dat")

        self.assertEqual(self.git(self.worktree, "diff", "--cached", "--name-status"), "D\tb.dat")

    def test_add__eol_alone_forces_text(self):
        """R24 · * eol=lf: a CRLF beside a NUL, beside a lone CR, or before a final lone CR: each refused, nothing
        staged."""
        self.given_attributes("* eol=lf\n")
        files = {"a.txt": b"one\x00\r\ntwo\r\n", "b.txt": b"one\rtwo\r\n", "c.txt": b"one\r\ntwo\r"}
        for name, content in files.items():
            (self.worktree / name).write_bytes(content)
            with self.subTest(name):
                self.refused("attributes", "add", name)

                self.assertEqual(self.staged(), [])

    def test_add__the_owners_autocrlf_is_weighed_against_the_attributes(self):
        """R25 · core.autocrlf=input in the Owner's config, *.bin -text, *.ctl text: a.bin holding CRLF refused; c.ctl
        holding CRLF beside two \\x01 refused; u.txt, no attribute, holding CRLF staged as LF."""
        with open(self.home / ".gitconfig", "a") as config:
            config.write("[core]\n\tautocrlf = input\n")
        self.given_attributes("*.bin -text\n*.ctl text\n")
        files = {"a.bin": b"one\r\ntwo\r\n", "c.ctl": b"one\x01\x01two\r\n", "u.txt": b"one\r\ntwo\r\n"}
        for name, content in files.items():
            (self.worktree / name).write_bytes(content)
        for name in ("a.bin", "c.ctl"):
            with self.subTest(name):
                self.refused("attributes", "add", name)

        self.ok("add", "u.txt")

        self.assertEqual(self.staged(), ["u.txt"])
        self.assertEqual(self.blob("u.txt"), b"one\ntwo\n")

    def test_add__auto_takes_a_file_of_control_bytes_for_binary(self):
        """R26 · * text=auto: a CRLF beside two \\x01, a DEL, one NUL among 200 printable bytes, or one \\x01 among 200
        CRLFs, staged byte for byte; a CRLF before a final \\x1a, and one split across the 1 MiB read, each refused."""
        self.given_attributes("* text=auto\n")
        files = {"a.bin": b"one\x01\x01two\r\n", "b.bin": b"one\x7ftwo\r\n", "f.bin": b"a" * 200 + b"\x00\r\n",
                 "h.bin": b"\x01" + b"\r\n" * 200}
        for name, content in files.items():
            (self.worktree / name).write_bytes(content)
        (self.worktree / "e.txt").write_bytes(b"one\r\ntwo\x1a")
        (self.worktree / "g.txt").write_bytes(b"a" * ((1 << 20) - 1) + b"\r\ntwo\r\n")

        self.ok("add", *files)
        for name in ("e.txt", "g.txt"):
            with self.subTest(name):
                self.refused("attributes", "add", name)

        self.assertEqual(self.staged(), sorted(files))
        for name, content in files.items():
            self.assertEqual(self.blob(name), content, name)

    def test_add__auto_keeps_a_file_whose_index_copy_holds_crlf(self):
        """R27 · * text=auto; a.txt tracked as one\\r\\n, b.txt tracked as one\\0\\r\\n, each now one\\r\\ntwo\\r\\n:
        a.txt staged byte for byte, b.txt refused."""
        tracked = {"a.txt": b"one\r\n", "b.txt": b"one\x00\r\n"}
        for name, content in tracked.items():
            (self.worktree / name).write_bytes(content)
        self.git(self.worktree, "add", *tracked)
        self.git(self.worktree, "commit", "-q", "-m", "crlf")
        self.given_attributes("* text=auto\n")
        for name in tracked:
            (self.worktree / name).write_bytes(b"one\r\ntwo\r\n")

        self.ok("add", "a.txt")
        self.refused("attributes", "add", "b.txt")

        self.assertEqual(self.staged(), ["a.txt"])
        self.assertEqual(self.blob("a.txt"), b"one\r\ntwo\r\n")

    def test_add__an_attribute_rw_git_reads_too_is_no_divergence(self):
        """R28 · *.txt text in the repository's info/attributes, which rw-git reads too: a.txt holding CRLF staged as
        LF."""
        (self.repo / ".git" / "info" / "attributes").write_text("*.txt text\n")
        (self.worktree / "a.txt").write_bytes(b"one\r\ntwo\r\n")

        self.ok("add", "a.txt")

        self.assertEqual(self.blob("a.txt"), b"one\ntwo\n")

    def test_add__an_autocrlf_of_false_converts_nothing_of_rw_gits_own(self):
        """R29 · core.autocrlf=false in the Owner's config, * text=auto: a.txt holding CRLF refused."""
        with open(self.home / ".gitconfig", "a") as config:
            config.write("[core]\n\tautocrlf = false\n")
        self.given_attributes("* text=auto\n")
        (self.worktree / "a.txt").write_bytes(b"one\r\ntwo\r\n")

        self.refused("attributes", "add", "a.txt")

        self.assertEqual(self.staged(), [])

    def test_add__in_a_conflict_the_index_copy_is_ours(self):
        """R30 · a cherry-pick stopped on README, ours one\\r\\n; core.autocrlf=input, README text, README now
        one\\r\\ntwo\\r\\n: add README refused."""
        (self.worktree / "README").write_bytes(b"one\r\n")
        self.git(self.worktree, "commit", "-q", "-am", "ours")
        theirs = self.commit_in(self.repo, "README", "main\n", "theirs")
        self.git(self.worktree, "cherry-pick", theirs, check=False)
        with open(self.home / ".gitconfig", "a") as config:
            config.write("[core]\n\tautocrlf = input\n")
        self.given_attributes("README text\n")
        (self.worktree / "README").write_bytes(b"one\r\ntwo\r\n")

        self.refused("attributes", "add", "README")

        self.assertIn("2", self.git(self.worktree, "ls-files", "--stage", "README").split())

    def test_add__an_unchanged_file_git_would_rehash_is_weighed_too(self):
        """R31 · a.txt and b.txt tracked as one\\r\\n, refreshed with an old mtime; a.txt then given an older one, so its
        stat changed but it is not racily clean; * text:
        add a.txt refused; add b.txt exits 0, nothing staged."""
        past = time.time() - 100
        for name in ("a.txt", "b.txt"):
            (self.worktree / name).write_bytes(b"one\r\n")
            os.utime(self.worktree / name, (past, past))
        self.git(self.worktree, "add", "a.txt", "b.txt")
        self.git(self.worktree, "commit", "-q", "-m", "crlf")
        self.git(self.worktree, "update-index", "--refresh")
        os.utime(self.worktree / "a.txt", (past - 50, past - 50))
        self.given_attributes("* text\n")

        self.refused("attributes", "add", "a.txt")
        self.ok("add", "b.txt")

        self.assertEqual(self.staged(), [])

    def given_core(self, **values):
        """The Owner's global [core] section, rewritten: a value of None is the bare key, which git reads as true."""
        lines = "".join(f"\t{key}\n" if value is None else f"\t{key} = {value}\n" for key, value in values.items())
        (self.home / ".gitconfig").write_text(f"[user]\n\tname = {NAME}\n\temail = {EMAIL}\n[core]\n{lines}")

    def given_racy(self, name, tracked):
        """`name` committed as `tracked`, then checked out again under the Owner's config, its stat matching the index
        entry and its mtime no older than the index file's: racily clean, set by hand so no test depends on the clock."""
        path = self.worktree / name
        path.write_bytes(tracked)
        self.git(self.worktree, "add", name)
        self.git(self.worktree, "commit", "-q", "-m", name)
        path.unlink()
        self.git(self.worktree, "checkout", "--", name)
        past = time.time() - 100
        os.utime(path, (past, past))
        self.git(self.worktree, "update-index", "--refresh")
        index = Path(self.git(self.worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"))
        os.utime(index, (past, past))

    def test_add__safecrlf_true_refuses_what_plain_git_add_dies_on(self):
        """R32 · core.safecrlf=true: text=auto eol=lf under autocrlf=true and a CRLF file; eol=crlf and an LF file
        (true, yes, on, 1, a bare key, TRUE); autocrlf=true and a mixed file; text under core.eol=crlf and an LF file:
        each refused, nothing staged."""
        cases = [("a.txt", "* text=auto eol=lf\n", b"one\r\ntwo\r\n", {"autocrlf": "true", "safecrlf": "true"}),
                 ("m.txt", "", b"one\r\ntwo\n", {"autocrlf": "true", "safecrlf": "true"}),
                 ("e.txt", "* text\n", b"one\ntwo\n", {"eol": "crlf", "safecrlf": "true"})]
        cases += [(f"d{number}.txt", "* eol=crlf\n", b"one\ntwo\n", {"safecrlf": spelling})
                  for number, spelling in enumerate(("true", "yes", "on", "1", None, "TRUE"))]
        for name, attributes, content, core in cases:
            with self.subTest(name=name, core=core):
                self.given_attributes(attributes)
                (self.worktree / name).write_bytes(content)
                self.given_core(**core)

                err = self.refused("attributes", "add", name)

                self.assertIn("safecrlf", err)
                self.assertEqual(self.staged(), [])

    def test_add__safecrlf_warn_or_false_stages_what_plain_git_stores(self):
        """R33 · text=auto eol=lf under autocrlf=true, a CRLF file: staged as LF under safecrlf warn, WARN, false and
        unset; text and an LF file under safecrlf=true: staged byte for byte."""
        self.given_attributes("*.txt text=auto eol=lf\n*.lf text\n")
        for number, spelling in enumerate(("warn", "WARN", "false", "unset")):
            name = f"c{number}.txt"
            with self.subTest(safecrlf=spelling):
                core = {"autocrlf": "true"} if spelling == "unset" else {"autocrlf": "true", "safecrlf": spelling}
                self.given_core(**core)
                (self.worktree / name).write_bytes(b"one\r\ntwo\r\n")

                self.ok("add", name)

                self.assertEqual(self.blob(name), b"one\ntwo\n")
        self.given_core(safecrlf="true")
        (self.worktree / "b.lf").write_bytes(b"one\ntwo\n")

        self.ok("add", "b.lf")

        self.assertEqual(self.blob("b.lf"), b"one\ntwo\n")

    def given_racy_index(self, name):
        index = Path(self.git(self.worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"))
        mtime = os.stat(self.worktree / name).st_mtime
        os.utime(index, (mtime, mtime))
        self.assertEqual(self.git(self.worktree, "diff-files", "--name-only"), "")

    def test_add__a_racily_clean_entry_is_weighed_as_plain_git_hashes_it(self):
        """R34 · a racily clean a.txt tracked as one\\r\\ntwo\\r\\n under *.txt text, autocrlf=false: refused, the
        index entry unchanged."""
        self.given_core(autocrlf="false")
        self.given_racy("a.txt", b"one\r\ntwo\r\n")
        self.given_attributes("*.txt text\n")
        self.given_racy_index("a.txt")

        self.refused("attributes", "add", "a.txt")

        self.assertEqual(self.blob("a.txt"), b"one\r\ntwo\r\n")

    def test_add__a_racily_clean_entry_checked_out_by_autocrlf_is_weighed(self):
        """R34 · a racily clean b.bat tracked as LF and checked out as CRLF under autocrlf=true, now *.bat -text:
        refused, the index entry unchanged."""
        self.given_core(autocrlf="true")
        self.given_racy("b.bat", b"one\ntwo\n")
        self.assertEqual((self.worktree / "b.bat").read_bytes(), b"one\r\ntwo\r\n")
        self.given_attributes("*.bat -text\n")
        self.given_racy_index("b.bat")

        self.refused("attributes", "add", "b.bat")

        self.assertEqual(self.blob("b.bat"), b"one\ntwo\n")

    def test_add__an_autocrlf_of_true_in_any_spelling_is_weighed(self):
        """R35 · core.autocrlf true, yes, on, 1, a bare key, TRUE; *.bin -text: a CRLF a.bin refused under each; under
        true, u.txt with no attribute staged as LF."""
        self.given_attributes("*.bin -text\n")
        for number, spelling in enumerate(("true", "yes", "on", "1", None, "TRUE")):
            name = f"a{number}.bin"
            with self.subTest(autocrlf=spelling):
                self.given_core(autocrlf=spelling)
                (self.worktree / name).write_bytes(b"one\r\ntwo\r\n")

                self.refused("attributes", "add", name)

                self.assertEqual(self.staged(), [])
        self.given_core(autocrlf="true")
        (self.worktree / "u.txt").write_bytes(b"one\r\ntwo\r\n")

        self.ok("add", "u.txt")

        self.assertEqual(self.blob("u.txt"), b"one\ntwo\n")

    def test_add__a_string_value_spelled_like_a_state_is_a_string(self):
        """R36 · *.txt text=set, autocrlf=false: e.txt holding CRLF staged byte for byte; *.un text=unset and *.cr
        crlf=unset under autocrlf=input: each holding CRLF staged as LF."""
        self.given_attributes("*.txt text=set\n*.un text=unset\n*.cr crlf=unset\n")
        for name, autocrlf, stored in (("e.txt", "false", b"one\r\ntwo\r\n"), ("g.un", "input", b"one\ntwo\n"),
                                       ("k.cr", "input", b"one\ntwo\n")):
            with self.subTest(name):
                self.given_core(autocrlf=autocrlf)
                (self.worktree / name).write_bytes(b"one\r\ntwo\r\n")

                self.ok("add", name)

                self.assertEqual(self.blob(name), stored)

    def test_add__a_converting_attribute_is_refused_whatever_its_value(self):
        """R37 · *.h working-tree-encoding=unset, *.f filter=unset, a string each: h.h and f.f refused naming the
        attribute, nothing staged."""
        self.given_attributes("*.h working-tree-encoding=unset\n*.f filter=unset\n")
        for name, attribute in (("h.h", "working-tree-encoding"), ("f.f", "filter")):
            (self.worktree / name).write_bytes(b"one\ntwo\n")
            with self.subTest(name):
                err = self.refused("attributes", "add", name)

                self.assertIn(attribute, err)
                self.assertEqual(self.staged(), [])


class UnmanagedTests(RwGitCase):
    """U48 part B: a checkout outside <repo>/.worktrees/<slug> commits on its own branch, where a grant admits it."""

    def setUp(self):
        super().setUp()
        self.desk = self.root / "desk"
        self.desk.mkdir()
        self.notes = self.root / "notes"
        self.notes.mkdir()
        self.given_launch_json({"repos": [str(self.repo)], "sessions_root": str(self.sessions),
                                "projects_root": str(self.projects), "desktop_roots": [str(self.desk)]})

    def given_repo(self, path):
        """Every repository here, the listed one included, on notes: main is protected in an unmanaged checkout (U52b
        D1), and these rows commit on an unprotected branch."""
        repo = super().given_repo(path)
        self.git(repo, "switch", "-q", "-c", "notes")
        return repo

    def given_settings(self, settings, folder=None):
        path = (folder or self.home) / ".claude" / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings) + "\n")
        return path

    def given_note(self, folder=None, text="sample: a note\n"):
        return self.given_message(text, folder=folder or self.desk / "messages")

    def commits(self, where, message=None):
        (where / "f").write_text(f"{self.head(where)}\n")
        self.ok("add", "f", cwd=where)
        before = self.head(where)
        self.ok("commit", "--message-file", str(message or self.given_note()), cwd=where)
        self.assertNotEqual(self.head(where), before)
        self.assertEqual(self.git(where, "log", "-1", "--format=%s"), "sample: a note")

    def unlisted(self, where):
        (where / "f").write_text("x\n")
        self.refused("worktree-unlisted", "add", "f", cwd=where)
        self.assertEqual(self.staged(where), [])

    def test_commit__a_listed_main_checkout_commits_on_its_branch(self):
        """U1 · the main checkout of a `repos` repository, on notes: add and commit from a granted folder, exit 0."""
        self.commits(self.repo)
        self.assertEqual(self.branch(self.repo), "notes")

    def test_commit__a_repository_under_a_desktop_root_commits(self):
        """U2 · a repository under a `desktop_roots` entry, not in `repos`: its main checkout on notes, another
        unprotected branch and a linked worktree outside .worktrees commit, exit 0 (U49 D1: release/* is protected)."""
        repo = self.given_repo(self.desk / "notes-app")
        self.commits(repo)
        self.git(repo, "switch", "-q", "-c", "drafts/1.0")
        self.commits(repo)
        linked = self.given_worktree(repo, "elsewhere", "feature")
        self.commits(linked)

    def test_add__a_repository_outside_every_grant_is_unlisted(self):
        """U3 · a repository in no `repos` entry, no `desktop_roots` entry and no settings grant: worktree-unlisted."""
        self.unlisted(self.given_repo(self.root / "outside" / "notes-app"))

    def test_add__a_root_or_user_deny_excludes_the_repository(self):
        """U4 · under a `desktop_roots` entry, a repository its own .claude/settings.json denyWrite covers, or an
        Edit(…) deny in the user settings covers: worktree-unlisted."""
        denied = self.given_repo(self.desk / "denied")
        self.given_settings({"sandbox": {"filesystem": {"denyWrite": [str(denied)]}}}, folder=self.desk)
        self.unlisted(denied)
        edited = self.given_repo(self.desk / "edited")
        self.given_settings({"permissions": {"deny": [f"Edit(/{edited}/**)"]}})
        self.unlisted(edited)
        globbed = self.given_repo(self.desk / "globbed" / "inner")
        self.given_settings({"sandbox": {"filesystem": {"denyWrite": [f"{self.desk}/glob*/**"]}}})
        self.unlisted(globbed)

    def test_add__a_malformed_desktop_roots_entry_is_refused_by_name(self):
        """U5 · `desktop_roots` not a list, or holding a relative entry, a glob, a number: launch-config naming it."""
        repo = self.given_repo(self.desk / "notes-app")
        (repo / "f").write_text("x\n")
        for value, named in (("~/desk", "list"), (["desk"], "desk"), ([f"{self.desk}/*"], "*"), ([7], "7")):
            with self.subTest(value=value):
                self.given_launch_json({"repos": [str(self.repo)], "sessions_root": str(self.sessions),
                                        "desktop_roots": value})
                err = self.refused("launch-config", "add", "f", cwd=repo)
                self.assertIn(named, err)
                self.assertEqual(self.staged(repo), [])

    def test_add__a_desktop_roots_entry_through_a_link_is_refused(self):
        """U6 · a `desktop_roots` entry that is a link to the real folder: launch-config naming the link."""
        repo = self.given_repo(self.desk / "notes-app")
        (self.root / "desk-link").symlink_to(self.desk)
        self.given_launch_json({"repos": [str(self.repo)], "sessions_root": str(self.sessions),
                                "desktop_roots": [str(self.root / "desk-link")]})
        (repo / "f").write_text("x\n")
        err = self.refused("launch-config", "add", "f", cwd=repo)
        self.assertIn("desk-link", err)

    def test_add__no_desktop_roots_and_no_settings_behaves_as_before(self):
        """U7 · the key absent and no user settings: a repository under the old root is worktree-unlisted, and a managed
        worktree of `repos` still adds."""
        self.given_launch_json({"repos": [str(self.repo)], "sessions_root": str(self.sessions)})
        self.unlisted(self.given_repo(self.desk / "notes-app"))
        (self.worktree / "g").write_text("y\n")
        self.ok("add", "g")

    def test_commit__a_user_settings_grant_admits_a_repository(self):
        """U8 · no `desktop_roots`; `allowWrite` or `additionalDirectories` naming a folder (as ~/ or absolute): its
        repository commits. A grant with a glob, a relative grant, and a grant through a link admit nothing."""
        self.given_launch_json({"repos": [str(self.repo)], "sessions_root": str(self.sessions)})
        for key in ("allowWrite", "additionalDirectories"):
            with self.subTest(key=key):
                folder = self.home / f"granted-{key}"
                repo = self.given_repo(folder / "notes-app")
                spelled = f"~/granted-{key}" if key == "allowWrite" else str(folder)
                settings = ({"sandbox": {"filesystem": {"allowWrite": [spelled]}}} if key == "allowWrite"
                            else {"permissions": {"additionalDirectories": [spelled]}})
                self.given_settings(settings)
                self.commits(repo, self.given_note(folder / "messages"))
        hidden = self.given_repo(self.root / "hidden" / "notes-app")
        (self.root / "via").symlink_to(self.root / "hidden")
        for entry in (f"{self.root}/hid*", "hidden", str(self.root / "via")):
            with self.subTest(entry=entry):
                self.given_settings({"sandbox": {"filesystem": {"allowWrite": [entry]}}})
                self.unlisted(hidden)

    def test_add__a_link_into_a_granted_folder_is_not_the_repository(self):
        """U9 · a link inside a `desktop_roots` folder to a repository outside every grant: worktree-unlisted."""
        outside = self.given_repo(self.root / "outside" / "notes-app")
        (self.desk / "shortcut").symlink_to(outside)
        self.unlisted(self.desk / "shortcut")

    def test_add__a_git_file_naming_a_repository_outside_is_unlisted(self):
        """U10 · a folder under a `desktop_roots` entry whose .git file names a worktree entry of a repository outside
        every grant: worktree-unlisted."""
        outside = self.given_repo(self.root / "outside" / "notes-app")
        linked = self.given_worktree(outside, "../wt", "feature")
        planted = self.desk / "planted"
        planted.mkdir()
        (planted / ".git").write_text((linked / ".git").read_text())
        self.unlisted(planted)

    def test_add__settings_under_a_granted_folder_grant_nothing(self):
        """U11 · the user settings file a link to a file inside a `desktop_roots` folder, granting `<root>/other`: a
        repository there is worktree-unlisted, one under the root still adds, and the file's denies still count."""
        other = self.given_repo(self.root / "other" / "notes-app")
        repo = self.given_repo(self.desk / "notes-app")
        denied = self.given_repo(self.desk / "denied")
        planted = self.given_settings({"sandbox": {"filesystem": {"allowWrite": [str(self.root / "other")],
                                                                  "denyWrite": [str(denied)]}}},
                                      folder=self.desk / "kept")
        (self.home / ".claude").mkdir(exist_ok=True)
        (self.home / ".claude" / "settings.json").symlink_to(planted)
        self.unlisted(other)
        self.unlisted(denied)
        (repo / "f").write_text("x\n")
        self.ok("add", "f", cwd=repo)

    def test_commit__a_leaf_deny_of_a_name_leaves_the_repositories_holding_it(self):
        """U18 · `<root>/**/.git` as denyWrite in the root's settings, and `Edit(**/.git/**)` in the user settings: a
        repository under the root commits; one under `<root>/**/.claude` is worktree-unlisted."""
        self.given_settings({"sandbox": {"filesystem": {"denyWrite": [f"{self.desk}/**/.git", f"{self.desk}/**/.claude"]}}},
                            folder=self.desk)
        self.given_settings({"permissions": {"deny": ["Edit(**/.git/**)"]}})
        self.commits(self.given_repo(self.desk / "notes-app"))
        self.unlisted(self.given_repo(self.desk / "kept" / ".claude" / "notes-app"))

    def test_commit__the_dev_trusted_leaf_denies_leave_every_repository_under_the_root(self):
        """U20 · U47's root settings: `<root>/**/.git`, `<root>/**/.claude`, `<root>/**/.mcp.json` as denyWrite, each
        paired with an Edit(…) deny: `<root>/notes-app` and `<root>/apps/todo` commit."""
        rules = [f"{self.desk}/**/.git", f"{self.desk}/**/.claude", f"{self.desk}/**/.mcp.json"]
        self.given_settings({"permissions": {"deny": [f"Edit({rule})" for rule in rules]},
                             "sandbox": {"filesystem": {"denyWrite": rules}}}, folder=self.desk)
        self.commits(self.given_repo(self.desk / "notes-app"))
        self.commits(self.given_repo(self.desk / "apps" / "todo"))

    def test_add__a_glob_deny_matches_the_repository_or_a_folder_above_it(self):
        """U21 · `<root>/secret/**` and `<root>/secret` each take out `<root>/secret/repo`; `<root>/*/vendor` takes out
        `<root>/a/vendor/repo` and leaves `<root>/notes-app` and `<root>/a/b/vendor/repo`; `<root>/**/.claude` takes out
        `<root>/x/.claude/y`."""
        secret = self.given_repo(self.desk / "secret" / "repo")
        vendored = self.given_repo(self.desk / "a" / "vendor" / "repo")
        hidden = self.given_repo(self.desk / "x" / ".claude" / "y")
        kept = self.given_repo(self.desk / "notes-app")
        for rule in (f"{self.desk}/secret/**", f"{self.desk}/secret"):
            with self.subTest(rule=rule):
                self.given_settings({"sandbox": {"filesystem": {"denyWrite": [rule]}}}, folder=self.desk)
                self.unlisted(secret)
        self.given_settings({"sandbox": {"filesystem": {"denyWrite": [f"{self.desk}/*/vendor",
                                                                      f"{self.desk}/**/.claude"]}}}, folder=self.desk)
        self.unlisted(vendored)
        self.unlisted(hidden)
        self.commits(kept)
        self.commits(self.given_repo(self.desk / "a" / "b" / "vendor" / "repo"))

    def test_add__a_glob_shape_rw_git_cannot_match_is_refused_by_name(self):
        """U22 · a deny holding `?`, `[…]`, `{…}` or `a**`: launch-config naming that deny, nothing staged."""
        repo = self.given_repo(self.desk / "notes-app")
        (repo / "f").write_text("x\n")
        for rule in (f"{self.desk}/note?-app", f"{self.desk}/[n]otes-app", f"{self.desk}/{{a,b}}", f"{self.desk}/a**"):
            with self.subTest(rule=rule):
                self.given_settings({"sandbox": {"filesystem": {"denyWrite": [rule]}}}, folder=self.desk)
                err = self.refused("launch-config", "add", "f", cwd=repo)
                self.assertIn(rule.split("/")[-1], err)
                self.assertEqual(self.staged(repo), [])

    def test_add__a_deny_spelled_in_another_case_or_unicode_form_still_takes_the_repository_out(self):
        """U23 · `<root>/secret` denies `<root>/Secret/repo`, and a deny spelled NFD denies `<root>/café/repo` made NFC:
        worktree-unlisted each — a case- or form-insensitive volume names the same folder, and the deny failed open."""
        cased = self.given_repo(self.desk / "Secret" / "repo")
        accented = self.given_repo(self.desk / unicodedata.normalize("NFC", "café") / "repo")
        self.given_settings({"sandbox": {"filesystem": {"denyWrite": [f"{self.desk}/secret"]}}}, folder=self.desk)
        self.unlisted(cased)
        nfd = unicodedata.normalize("NFD", "café")
        self.given_settings({"sandbox": {"filesystem": {"denyWrite": [f"{self.desk}/{nfd}"]}}}, folder=self.desk)
        self.unlisted(accented)

    def test_add__a_deny_that_matches_as_written_still_takes_the_repository_out_once_folded(self):
        """U26 · `<root>/<a U+0301 U+0316>/repo`, marks out of canonical order, with `<root>/<a U+0301>*` denied:
        worktree-unlisted — folding the path whole and the pattern piece by piece reorders the marks across the `*`."""
        repo = self.given_repo(self.desk / "á̖" / "repo")
        self.given_settings({"sandbox": {"filesystem": {"denyWrite": [f"{self.desk}/á*"]}}}, folder=self.desk)
        self.unlisted(repo)

    def test_add__a_relative_edit_deny_matches_at_any_depth_below_where_it_is_read(self):
        """U24 · `Edit(secret)` and `Edit(./secret)` in the user settings, and `Edit(secret)` in the root's own settings,
        take out `<root>/secret` and `<root>/team/secret`; `<root>/notes-app` commits — Claude Code reads a relative rule
        from the session's working directory, so anchoring it at one folder served a repository the session cannot edit."""
        top = self.given_repo(self.desk / "secret")
        deep = self.given_repo(self.desk / "team" / "secret")
        for rule in ("Edit(secret)", "Edit(./secret)"):
            with self.subTest(rule=rule):
                self.given_settings({"permissions": {"deny": [rule]}})
                self.unlisted(top)
                self.unlisted(deep)
        self.given_settings({})
        self.given_settings({"permissions": {"deny": ["Edit(secret)"]}}, folder=self.desk)
        self.unlisted(top)
        self.unlisted(deep)
        self.commits(self.given_repo(self.desk / "notes-app"))

    def test_add__a_linked_user_settings_files_relative_deny_is_read_from_its_claude_folder_too(self):
        """U25 · `~/.claude/settings.json` a link to `<scratch>/dot/.claude/settings.json` denying `repos/secret`, and
        `~/.claude/repos` granted: `~/.claude/repos/secret` is worktree-unlisted — Claude Code opens the file at
        `~/.claude`, so reading the deny only from the link's folder served the repository it names."""
        granted = self.home / ".claude" / "repos"
        repo = self.given_repo(granted / "secret")
        target = self.given_settings({"sandbox": {"filesystem": {"denyWrite": ["repos/secret"]}}}, folder=self.root / "dot")
        link = self.home / ".claude" / "settings.json"
        link.symlink_to(target)
        self.given_launch_json({"repos": [str(self.repo)], "sessions_root": str(self.sessions),
                                "projects_root": str(self.projects), "desktop_roots": [str(self.desk), str(granted)]})
        self.unlisted(repo)

    def test_add__a_settings_file_that_is_no_regular_json_object_is_refused(self):
        """U19 · the root's .claude/settings.json a FIFO, or the user settings with a trailing comma: launch-config,
        promptly, and nothing staged."""
        repo = self.given_repo(self.desk / "notes-app")
        (repo / "f").write_text("x\n")
        (self.desk / ".claude").mkdir()
        os.mkfifo(self.desk / ".claude" / "settings.json")
        self.refused("launch-config", "add", "f", cwd=repo, timeout=20)
        os.unlink(self.desk / ".claude" / "settings.json")
        path = self.given_settings({})
        path.write_text('{"permissions": {"deny": [],}}\n')
        self.refused("launch-config", "add", "f", cwd=repo)
        self.assertEqual(self.staged(repo), [])

    def test_commit__an_unmanaged_checkout_is_refused_off_a_branch_or_mid_operation(self):
        """U12 · a detached HEAD, or MERGE_HEAD, rebase-merge, rebase-apply, CHERRY_PICK_HEAD or REVERT_HEAD present:
        head-not-own, and HEAD stays."""
        repo = self.given_repo(self.desk / "notes-app")
        (repo / "f").write_text("x\n")
        self.ok("add", "f", cwd=repo)
        message = str(self.given_note())
        before = self.head(repo)
        for name in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD", "sequencer"):
            with self.subTest(stopped=name):
                place = repo / ".git" / name
                place.mkdir() if name in ("rebase-merge", "rebase-apply", "sequencer") else place.write_text(before + "\n")
                self.refused("head-not-own", "commit", "--message-file", message, cwd=repo)
                shutil.rmtree(place) if place.is_dir() else place.unlink()
                self.assertEqual(self.head(repo), before)
        self.git(repo, "switch", "-q", "--detach")
        self.refused("head-not-own", "commit", "--message-file", message, cwd=repo)
        self.assertEqual(self.head(repo), before)

    def test_commit__an_unmanaged_message_file_lies_in_a_temp_or_granted_folder(self):
        """U14 · inside the repository, in an ungranted folder, under a deny inside a granted folder, through a link:
        message-file. Under a granted folder: exit 0."""
        repo = self.given_repo(self.desk / "notes-app")
        (repo / "f").write_text("x\n")
        self.ok("add", "f", cwd=repo)
        self.given_settings({"sandbox": {"filesystem": {"denyWrite": [str(self.desk / "private")]}}}, folder=self.desk)
        inside = self.given_message("sample: a note\n", folder=repo / "notes")
        ungranted = self.given_note(self.notes)
        denied = self.given_note(self.desk / "private")
        (self.desk / "linked").symlink_to(self.notes)
        linked = self.desk / "linked" / ungranted.name
        before = self.head(repo)
        for path in (inside, ungranted, denied, linked):
            with self.subTest(path=path):
                self.refused("message-file", "commit", "--message-file", str(path), cwd=repo)
                self.assertEqual(self.head(repo), before)
        self.ok("commit", "--message-file", str(self.given_note()), cwd=repo)
        self.assertNotEqual(self.head(repo), before)

    def test_commit__an_unmanaged_message_file_in_the_temp_folder_is_taken(self):
        """U17 · a message under the account's temp folder (here the scratch one the runner names): exit 0."""
        repo = self.given_repo(self.desk / "notes-app")
        self.commits(repo, self.given_note(self.root / "temp" / "u48"))

    def test_commit__a_managed_worktree_keeps_its_message_rule(self):
        """U15 · the managed worktree, a message under a granted folder: message-file; under its session folder: exit 0."""
        (self.worktree / "f").write_text("x\n")
        self.ok("add", "f")
        self.refused("message-file", "commit", "--message-file", str(self.given_note()))
        self.ok("commit", "--message-file", str(self.given_message()))

    def test_commit__an_unmanaged_checkout_runs_no_program_its_config_names(self):
        """U16 · fsmonitor, every hook, pager, editor, external diff and sshCommand planted in a repository under a
        `desktop_roots` entry: add, restore and commit leave no marker."""
        repo = self.given_repo(self.desk / "notes-app")
        for key, name in (("core.fsmonitor", "fsmonitor"), ("core.pager", "pager"), ("core.editor", "editor"),
                          ("diff.external", "external-diff"), ("core.sshCommand", "ssh-command"),
                          ("sequence.editor", "sequence-editor")):
            self.git(repo, "config", key, str(self.program(name)))
        hooks = repo / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        for name in HOOK_NAMES:
            shutil.copy(self.program(f"hook-{name}"), hooks / name)
        (repo / "f").write_text("x\n")
        self.ok("add", "f", cwd=repo)
        self.ok("restore", "--staged", "f", cwd=repo)
        self.ok("add", "f", cwd=repo)
        self.ok("commit", "--message-file", str(self.given_note()), cwd=repo)
        self.assertEqual(self.marked(), [])


class DailyTests(RwGitCase):
    """U49: a person's daily git. In an unmanaged checkout an own branch is any branch launch.json's
    `protected_branches` does not protect (D1); protection gates writes, not checking a branch out (D2). Every row runs
    with a hostile config planted in each repository, and no marker may exist after it."""

    DEFAULT_PROTECTED = ("master", "develop", "release/1.0", "hotfix/urgent")

    def setUp(self):
        super().setUp()
        self.desk = self.root / "desk"
        self.desk.mkdir()
        self.config = {"repos": [str(self.repo)], "sessions_root": str(self.sessions),
                       "projects_root": str(self.projects), "desktop_roots": [str(self.desk)]}
        self.given_launch_json(self.config)
        self.hostile(self.repo)
        self.addCleanup(lambda: self.assertEqual(self.marked(), []))

    def hostile(self, repo):
        """fsmonitor, pager, editor, external diff, sshCommand, sequence editor and every hook, each a marker."""
        for key, name in (("core.fsmonitor", "fsmonitor"), ("core.pager", "pager"), ("core.editor", "editor"),
                          ("diff.external", "external-diff"), ("core.sshCommand", "ssh-command"),
                          ("sequence.editor", "sequence-editor")):
            self.git(repo, "config", key, str(self.program(name)))
        hooks = repo / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        for name in HOOK_NAMES:
            shutil.copy(self.program(f"hook-{name}"), hooks / name)

    def notes_app(self, branch="main"):
        """desk/notes-app, a repository under a `desktop_roots` entry, on `branch`."""
        repo = self.given_repo(self.desk / "notes-app")
        self.hostile(repo)
        if branch != "main":
            self.git(repo, "switch", "-q", "-c", branch)
        return repo

    def note(self, text="sample: a note\n", name="note.txt"):
        return str(self.given_message(text, folder=self.desk / "messages", name=name))

    def protect(self, repo, names):
        self.given_launch_json({**self.config, "protected_branches": {str(repo): names}})

    def subjects(self, where, since):
        return self.git(where, "log", "--format=%s", f"{since}..HEAD").splitlines()

    # -- D1, D2: own and protected branches --------------------------------------------------------------------------

    def test_unmanaged__every_write_on_a_default_protected_branch_is_refused(self):
        """D1 · desk/notes-app on master, develop, release/1.0, hotfix/urgent: commit, commit --amend, rebase,
        rebase --onto, reset --soft, reset --keep, cherry-pick, stash push, stash pop, push of that branch and push of
        an unprotected one are branch-protected; HEAD stays."""
        repo = self.notes_app()
        base = self.head(repo)
        self.git(repo, "branch", "notes")
        picked = self.commit_in(repo, "g", "y\n", "side")
        self.git(repo, "reset", "-q", "--hard", base)
        note = self.note()
        for branch in self.DEFAULT_PROTECTED:
            self.git(repo, "switch", "-q", "-c", branch, base)
            tip = self.commit_in(repo, "h", branch + "\n", f"on {branch}")
            (repo / "README").write_text("edited\n")
            self.git(repo, "add", "README")
            for args in (["commit", "--message-file", note], ["commit", "--amend", "--message-file", note],
                         ["rebase", picked], ["rebase", "--onto", picked, base], ["reset", "--soft", base],
                         ["reset", "--keep", base], ["cherry-pick", picked], ["stash", "push", "README"],
                         ["stash", "pop"], ["push", branch], ["push", "notes"]):
                with self.subTest(branch=branch, args=args):
                    self.refused("branch-protected", *args, cwd=repo)
                    self.assertEqual(self.head(repo), tip)
                    self.assertEqual(self.branch(repo), branch)
            self.git(repo, "reset", "-q", "--hard", tip)
            self.git(repo, "switch", "-q", "main")

    def test_unmanaged__main_is_protected_by_default(self):
        """D3 · desk/notes-app on main, no `protected_branches`: commit, commit --amend and push main are
        branch-protected and HEAD stays (U52b D1)."""
        repo = self.notes_app()
        (repo / "f").write_text("x\n")
        self.ok("add", "f", cwd=repo)
        before = self.head(repo)
        note = self.note()

        for args in (["commit", "--message-file", note], ["commit", "--amend", "--message-file", note], ["push", "main"]):
            with self.subTest(args=args):
                self.refused("branch-protected", *args, cwd=repo)
                self.assertEqual(self.head(repo), before)

    def test_unmanaged__a_listed_glob_protects_and_the_list_adds_to_the_default(self):
        """D2 · protected_branches lists trunk and team/*: commit on trunk, team/a and develop (a default the list
        leaves out) is branch-protected; on feature it commits."""
        repo = self.notes_app()
        self.protect(repo, ["trunk", "team/*"])
        note = self.note()
        for branch, protected in (("trunk", True), ("team/a", True), ("develop", True), ("feature", False)):
            self.git(repo, "switch", "-q", "-c", branch, "main")
            (repo / "f").write_text(branch + "\n")
            self.ok("add", "f", cwd=repo)
            before = self.head(repo)
            with self.subTest(branch=branch):
                if protected:
                    self.refused("branch-protected", "commit", "--message-file", note, cwd=repo)
                    self.assertEqual(self.head(repo), before)
                else:
                    self.ok("commit", "--message-file", note, cwd=repo)
                    self.assertNotEqual(self.head(repo), before)
            self.git(repo, "reset", "-q", "--hard")

    def test_unmanaged__a_list_naming_main_still_protects_develop(self):
        """D37 · protected_branches lists only main: commit on develop is branch-protected — a list replaced the
        default, so naming main unprotected develop (U52b D2)."""
        repo = self.notes_app("develop")
        self.protect(repo, ["main"])
        (repo / "f").write_text("x\n")
        self.ok("add", "f", cwd=repo)
        before = self.head(repo)

        self.refused("branch-protected", "commit", "--message-file", self.note(), cwd=repo)
        self.assertEqual(self.head(repo), before)

    def test_unmanaged__the_branch_origin_head_names_is_protected(self):
        """D36 · refs/remotes/origin/HEAD naming origin/trunk: commit on trunk is branch-protected and on feature
        commits; with origin/HEAD unset, trunk commits too (U52b D1)."""
        repo = self.notes_app("trunk")
        self.git(repo, "branch", "feature")
        self.git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        note = self.note()

        (repo / "f").write_text("x\n")
        self.ok("add", "f", cwd=repo)
        self.refused("branch-protected", "commit", "--message-file", note, cwd=repo)
        self.git(repo, "switch", "-q", "feature")
        self.ok("commit", "--message-file", note, cwd=repo)
        self.git(repo, "switch", "-q", "trunk")
        self.git(repo, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        (repo / "g").write_text("y\n")
        self.ok("add", "g", cwd=repo)
        self.ok("commit", "--message-file", note, cwd=repo)

    def test_unmanaged__switch_goes_to_any_branch_and_creates_only_unprotected_ones(self):
        """D4 · on main: `switch develop` (protected) and back exit 0; from develop `switch -c feature` exits 0;
        `switch -c release/2`, `switch -c Develop`, `switch -c MASTER` and `switch -c @{-1}` naming a deleted
        release/9 are branch-protected and make no branch; with MERGE_HEAD present `switch main` is head-not-own."""
        repo = self.notes_app()
        self.git(repo, "branch", "develop")
        base = self.head(repo)
        self.git(repo, "switch", "-q", "-c", "release/9")
        self.git(repo, "switch", "-q", "main")
        self.git(repo, "branch", "-q", "-D", "release/9")
        self.refused("branch-protected", "switch", "-c", "@{-1}", cwd=repo)

        self.ok("switch", "develop", cwd=repo)
        self.assertEqual(self.branch(repo), "develop")
        self.ok("switch", "-c", "feature", cwd=repo)
        self.assertEqual(self.branch(repo), "feature")
        for name in ("release/2", "Develop", "MASTER"):
            with self.subTest(name=name):
                self.refused("branch-protected", "switch", "-c", name, cwd=repo)
                self.assertEqual(self.branch(repo), "feature")
        self.assertEqual(self.git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/"),
                         "develop\nfeature\nmain")
        self.assertEqual(self.head(repo), base)
        (repo / ".git" / "MERGE_HEAD").write_text(base + "\n")
        self.refused("head-not-own", "switch", "main", cwd=repo)
        self.assertEqual(self.branch(repo), "feature")

    def test_unmanaged__an_own_branch_rebases_picks_stashes_and_pushes(self):
        """D5 · desk/notes-app on feature: rebase onto main's new tip, cherry-pick a commit, stash push and pop (the
        entry tagged with the checkout's path, so a second unmanaged checkout's newer entry is left), push to origin under a draft-pr hook:
        each exit 0."""
        repo = self.notes_app()
        origin = self.root / "notes-origin.git"
        self.git(self.root, "init", "-q", "--bare", "-b", "main", str(origin))
        self.git(repo, "remote", "add", "origin", str(origin))
        hook = repo / ".claude" / "robowright" / "project.md"
        hook.parent.mkdir(parents=True)
        hook.write_text("# Project hook\n\n## 10 · Publishing\n\npublish_strategy: draft-pr\n")
        self.git(repo, "switch", "-q", "-c", "feature")
        self.commit_in(repo, "f", "x\n", "feature work")
        self.git(repo, "switch", "-q", "main")
        moved = self.commit_in(repo, "g", "y\n", "main moved")
        side = self.commit_in(repo, "s", "s\n", "side")
        self.git(repo, "reset", "-q", "--hard", moved)
        self.git(repo, "switch", "-q", "feature")
        two = self.desk / "notes-two"
        self.git(repo, "worktree", "add", "-q", "-b", "two", str(two))

        self.ok("rebase", moved, cwd=repo)
        self.assertEqual(self.subjects(repo, moved), ["feature work"])
        self.ok("cherry-pick", side, cwd=repo)
        self.assertEqual(self.subjects(repo, moved), ["side", "feature work"])
        (repo / "README").write_text("mine\n")
        self.ok("stash", "push", "README", cwd=repo)
        self.assertEqual((repo / "README").read_text(), "base\n")
        (two / "README").write_text("theirs\n")
        self.ok("stash", "push", "README", cwd=two)
        self.ok("stash", "pop", cwd=repo)
        self.assertEqual((repo / "README").read_text(), "mine\n")
        self.assertEqual(len(self.git(repo, "stash", "list").splitlines()), 1)
        self.ok("push", "feature", cwd=repo, remote=True)
        self.assertEqual(self.git(origin, "rev-parse", "feature"), self.head(repo))

    def test_unmanaged__a_branch_a_remote_tracks_is_never_reset_or_lease_pushed(self):
        """R38 · desk/notes-app, an origin and a draft-pr hook: on feature, which origin/feature holds, and on local,
        whose upstream is origin/other, `reset --soft <base>` and `push --force-with-lease` are branch-tracked and
        neither HEAD nor origin moves; on solo, tracked by nothing, both exit 0 (U52b D3)."""
        repo = self.notes_app()
        origin = self.root / "notes-origin.git"
        self.git(self.root, "init", "-q", "--bare", "-b", "main", str(origin))
        self.git(repo, "remote", "add", "origin", str(origin))
        hook = repo / ".claude" / "robowright" / "project.md"
        hook.parent.mkdir(parents=True)
        hook.write_text("# Project hook\n\n## 10 · Publishing\n\npublish_strategy: draft-pr\n")
        base = self.head(repo)
        for branch in ("feature", "other"):
            self.git(repo, "switch", "-q", "-c", branch, base)
            self.commit_in(repo, f"{branch}.txt", "x\n", branch)
            self.git(repo, "push", "-q", "origin", branch)
        self.git(repo, "switch", "-q", "-c", "local", base)
        self.commit_in(repo, "local.txt", "x\n", "local")
        self.git(repo, "branch", "-q", "--set-upstream-to=origin/other")
        self.git(repo, "switch", "-q", "-c", "solo", base)
        solo = self.commit_in(repo, "solo.txt", "x\n", "solo")

        for branch in ("feature", "local"):
            self.git(repo, "switch", "-q", branch)
            tip = self.head(repo)
            pushed = self.git(origin, "for-each-ref", "--format=%(refname) %(objectname)")
            for args in (["reset", "--soft", base], ["push", "--force-with-lease", branch]):
                with self.subTest(branch=branch, args=args):
                    self.refused("branch-tracked", *args, cwd=repo, remote=True)
                    self.assertEqual(self.head(repo), tip)
                    self.assertEqual(self.git(origin, "for-each-ref", "--format=%(refname) %(objectname)"), pushed)
        self.git(repo, "switch", "-q", "solo")
        self.ok("push", "--force-with-lease", "solo", cwd=repo, remote=True)
        self.assertEqual(self.git(origin, "rev-parse", "solo"), solo)
        self.git(repo, "update-ref", "-d", "refs/remotes/origin/solo")
        self.ok("reset", "--soft", base, cwd=repo)
        self.assertEqual(self.head(repo), base)

    def test_unmanaged__a_stopped_rebase_of_an_own_branch_aborts_and_one_of_a_protected_branch_is_refused(self):
        """D6 · a conflicting rebase stopped on feature: `rebase --abort` exits 0, back on the old tip; so does a
        conflicting cherry-pick's `cherry-pick --abort`. A rebase stopped on develop (started by plain git):
        `rebase --abort` and `--continue` are branch-protected."""
        repo = self.notes_app()
        self.git(repo, "switch", "-q", "-c", "feature")
        tip = self.commit_in(repo, "README", "feature\n", "feature edit")
        self.git(repo, "switch", "-q", "main")
        moved = self.commit_in(repo, "README", "main\n", "main edit")
        self.git(repo, "switch", "-q", "feature")
        self.assertEqual(self.rw("rebase", moved, cwd=repo)[0], 1)

        self.ok("rebase", "--abort", cwd=repo)

        self.assertEqual(self.head(repo), tip)
        self.assertEqual(self.rw("cherry-pick", moved, cwd=repo)[0], 1)
        self.ok("cherry-pick", "--abort", cwd=repo)
        self.assertEqual(self.head(repo), tip)
        self.git(repo, "switch", "-q", "-c", "develop", tip)
        self.git(repo, "rebase", moved, check=False)
        for step in ("--abort", "--continue"):
            with self.subTest(step=step):
                self.refused("branch-protected", "rebase", step, cwd=repo)
        self.assertTrue((repo / ".git" / "rebase-merge").is_dir())

    # -- R1: commit --amend ------------------------------------------------------------------------------------------

    def test_amend__rewrites_the_own_branch_tip_in_a_managed_worktree(self):
        """D7 · the managed worktree, a commit on its own branch, a new staged file: `commit --amend` exits 0; the tip
        holds both files, has the new message, and the same parent."""
        base = self.head()
        first = self.commit_in(self.worktree, "f", "x\n", "first")
        (self.worktree / "g").write_text("y\n")
        self.ok("add", "g")

        self.ok("commit", "--amend", "--message-file", str(self.given_message("sample: amended\n")))

        self.assertNotEqual(self.head(), first)
        self.assertEqual(self.git(self.worktree, "rev-parse", "HEAD^"), base)
        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%s"), "sample: amended")
        self.assertEqual(self.git(self.worktree, "ls-tree", "--name-only", "HEAD").splitlines(), ["README", "f", "g"])

    def test_amend__a_tip_any_remote_tracking_ref_holds_is_refused(self):
        """D8 · HEAD held by refs/remotes/fork/topic (no upstream set), equal or as an ancestor: amend-pushed, HEAD
        stays."""
        tip = self.commit_in(self.worktree, "f", "x\n", "first")
        message = str(self.given_message())
        later = self.git(self.worktree, "commit-tree", "-p", tip, "-m", "later", f"{tip}^{{tree}}")
        for held in (tip, later):
            self.git(self.repo, "update-ref", "refs/remotes/fork/topic", held)
            with self.subTest(held=held):
                self.refused("amend-pushed", "commit", "--amend", "--message-file", message)
                self.assertEqual(self.head(), tip)

    def test_amend__a_merge_commit_is_refused(self):
        """D9 · HEAD a merge of the own branch and main: amend-merge, HEAD stays."""
        self.commit_in(self.worktree, "f", "x\n", "first")
        self.commit_in(self.repo, "g", "y\n", "on main")
        self.git(self.worktree, "merge", "-q", "--no-edit", "main")
        merge = self.head()

        self.refused("amend-merge", "commit", "--amend", "--message-file", str(self.given_message()))

        self.assertEqual(self.head(), merge)

    # -- R2: reset ---------------------------------------------------------------------------------------------------

    def test_reset__soft_moves_the_own_branch_keeps_the_index_and_names_the_old_tip(self):
        """D10 · the managed worktree two commits past base: `reset --soft <base>` exits 0, HEAD is base, both files
        staged, stdout `rw-git: reset: <branch> was <tip>`. The same in desk/notes-app on feature."""
        for where, branch in ((self.worktree, BRANCH), (None, "feature")):
            if where is None:
                where = self.notes_app("feature")
            base = self.head(where)
            self.commit_in(where, "f", "x\n", "one")
            tip = self.commit_in(where, "g", "y\n", "two")
            with self.subTest(branch=branch):
                out = self.ok("reset", "--soft", base, cwd=where)
                self.assertIn(f"rw-git: reset: {branch} was {tip}\n", out)
                self.assertEqual(self.head(where), base)
                self.assertEqual(self.staged(where), ["f", "g"])

    def test_reset__keep_moves_the_branch_and_git_refuses_to_lose_a_local_change(self):
        """D11 · own branch one commit past base editing README: with README edited in the worktree, `reset --keep
        <base>` exits 1 and HEAD and the edit stay; with an unrelated edit, exit 0, HEAD is base, the edit kept."""
        base = self.head()
        tip = self.commit_in(self.worktree, "README", "committed\n", "edit")
        (self.worktree / "README").write_text("local\n")

        code, _, err = self.rw("reset", "--keep", base)

        self.assertEqual(code, 1, err)
        self.assertEqual(self.head(), tip)
        self.assertEqual((self.worktree / "README").read_text(), "local\n")
        self.git(self.worktree, "checkout", "--", "README")
        (self.worktree / "other").write_text("untracked\n")
        out = self.ok("reset", "--keep", base)
        self.assertIn(f"rw-git: reset: {BRANCH} was {tip}\n", out)
        self.assertEqual(self.head(), base)
        self.assertEqual((self.worktree / "other").read_text(), "untracked\n")

    def test_reset__only_soft_and_keep_with_a_full_id_of_a_commit_here(self):
        """D12 · reset --hard, --mixed, --merge, a bare id, two ids, a path: usage. A short id, a branch name, 40 hex
        naming nothing: commit-unknown. HEAD stays."""
        tip = self.commit_in(self.worktree, "f", "x\n", "one")
        base = self.git(self.worktree, "rev-parse", "HEAD^")
        for args in (["--hard", base], ["--mixed", base], ["--merge", base], [base], ["--soft", base, base],
                     ["--soft", base, "--", "f"], ["--soft"], ["--keep", "-q"]):
            with self.subTest(args=args):
                self.refused("usage", "reset", *args)
        for target in (base[:12], "main", "0" * 40):
            for mode in ("--soft", "--keep"):
                with self.subTest(mode=mode, target=target):
                    self.refused("commit-unknown", "reset", mode, target)
        self.assertEqual(self.head(), tip)

    # -- R3: rebase --onto -------------------------------------------------------------------------------------------

    def test_rebase_onto__replays_exactly_upstream_to_branch_and_names_the_old_tip(self):
        """D13 · the own branch holds the parent's two commits and three of its own; main moves. `rebase --onto <main>
        <parent tip>`: exit 0, main..HEAD is exactly the three own commits, the parent's are not replayed, stdout names
        the old tip. The same in desk/notes-app on feature."""
        for where, branch in ((self.worktree, BRANCH), (None, "feature")):
            if where is None:
                where = self.notes_app("feature")
            main = self.repo if where == self.worktree else where
            self.commit_in(where, "p1", "1\n", "parent one")
            parent = self.commit_in(where, "p2", "2\n", "parent two")
            for name in ("c1", "c2", "c3"):
                tip = self.commit_in(where, name, name + "\n", f"own {name}")
            if where != self.worktree:
                self.git(where, "switch", "-q", "main")
            moved = self.commit_in(main, "m", "m\n", "main moved")
            if where != self.worktree:
                self.git(where, "switch", "-q", "feature")
            with self.subTest(branch=branch):
                out = self.ok("rebase", "--onto", moved, parent, cwd=where)
                self.assertIn(f"rw-git: rebase: {branch} was {tip}\n", out)
                self.assertEqual(self.subjects(where, moved), ["own c3", "own c2", "own c1"])

    def test_rebase_onto__takes_two_full_ids_of_commits_here(self):
        """D14 · a short id, a branch name or 40 hex naming nothing in either place: commit-unknown; one id, three, or
        a flag: usage."""
        base = self.head()
        tip = self.commit_in(self.worktree, "f", "x\n", "one")
        for new, upstream in ((base[:12], base), (base, "main"), ("0" * 40, base), (base, "0" * 40)):
            with self.subTest(new=new, upstream=upstream):
                self.refused("commit-unknown", "rebase", "--onto", new, upstream)
        for args in (["--onto", base], ["--onto", base, base, base], ["--onto", "--autosquash", base, base],
                     ["--autosquash", "--onto", base, base]):
            with self.subTest(args=args):
                self.refused("usage", "rebase", *args)
        self.assertEqual(self.head(), tip)

    # -- in a managed worktree, the new forms keep head-not-own -------------------------------------------------------

    def test_managed__the_new_forms_are_head_not_own_off_the_own_branch(self):
        """D15 · the managed worktree on feature/x: commit --amend, reset --soft, reset --keep and rebase --onto are
        head-not-own; `switch main` stays branch-not-own (D2 is for unmanaged checkouts)."""
        base = self.head()
        self.git(self.worktree, "switch", "-q", "-c", "feature/x")
        tip = self.commit_in(self.worktree, "f", "x\n", "one")
        message = str(self.given_message())
        for args in (["commit", "--amend", "--message-file", message], ["reset", "--soft", base],
                     ["reset", "--keep", base], ["rebase", "--onto", base, base]):
            with self.subTest(args=args[:2]):
                self.refused("head-not-own", *args)
                self.assertEqual(self.head(), tip)
        self.refused("branch-not-own", "switch", "main")

    # -- R9: the key's shape -----------------------------------------------------------------------------------------

    def test_protected_branches__a_bad_value_is_refused_by_name(self):
        """D16 · protected_branches a list; a key not a path; a value not a list; an entry empty, holding a control
        byte, of 256 bytes, or not a string: launch-config naming it, in an unmanaged checkout; nothing committed."""
        repo = self.notes_app("feature")
        (repo / "f").write_text("x\n")
        self.git(repo, "add", "f")
        before = self.head(repo)
        note = self.note()
        key = str(repo)
        for value, named in ((["main"], "protected_branches"), ({"notes-app": ["main"]}, "notes-app"),
                             ({key: "main"}, key), ({key: [""]}, "''"), ({key: ["ma\x01in"]}, "ma\\x01in"), ({key: ["ma\tin"]}, "ma\\tin"),
                             ({key: ["a" * 256]}, "a" * 40), ({key: [7]}, "7")):
            self.given_launch_json({**self.config, "protected_branches": value})
            with self.subTest(value=value):
                err = self.refused("launch-config", "commit", "--message-file", note, cwd=repo)
                self.assertIn(named, err)
                self.assertEqual(self.head(repo), before)
        self.given_launch_json({**self.config, "protected_branches": {key: ["a" * 255]}})
        self.ok("commit", "--message-file", note, cwd=repo)

    # -- R4: --scope-file ----------------------------------------------------------------------------------------------

    def scope(self, text, folder=None, name="scope.txt"):
        return str(self.given_message(text, folder=folder, name=name))

    def test_scope__a_staged_path_outside_the_scope_is_refused_and_printed(self):
        """D20 · scope `#notes` (a comment), a blank line, `src`; src/a, b and a file named `#notes` staged: scope,
        stderr lists b and `#notes` and not src/a, nothing committed; with both unstaged, exit 0."""
        (self.worktree / "src").mkdir()
        (self.worktree / "src" / "a").write_text("a\n")
        (self.worktree / "b").write_text("b\n")
        (self.worktree / "#notes").write_text("n\n")
        self.ok("add", "src/a", "b", "#notes")
        before = self.head()
        scope = self.scope("#notes\n\nsrc\n")
        message = str(self.given_message())

        err = self.refused("scope", "commit", "--message-file", message, "--scope-file", scope)

        self.assertIn("\nb\n", err)
        self.assertIn("\n#notes\n", err)
        self.assertNotIn("src/a", err)
        self.assertEqual(self.head(), before)
        self.ok("restore", "--staged", "b", "#notes")
        self.ok("commit", "--message-file", message, "--scope-file", scope)
        self.assertNotEqual(self.head(), before)

    def test_scope__a_rename_counts_under_its_new_path(self):
        """D21 · old.txt tracked outside the scope, moved to src/new.txt and staged: scope `src`, exit 0."""
        self.commit_in(self.worktree, "old.txt", "x\n", "old")
        (self.worktree / "src").mkdir()
        self.git(self.worktree, "mv", "old.txt", "src/new.txt")

        self.ok("commit", "--message-file", str(self.given_message()), "--scope-file", self.scope("src\n"))

        self.assertEqual(self.git(self.worktree, "ls-tree", "-r", "--name-only", "HEAD").splitlines(),
                         ["README", "src/new.txt"])

    def test_scope__an_outside_path_is_printed_without_control_bytes(self):
        """D22 · a staged file named `e<ESC>[31mx<TAB>y` outside the scope: scope, printed as `e[31mxy`."""
        name = "e\x1b[31mx\ty"
        (self.worktree / name).write_text("x\n")
        self.git(self.worktree, "add", "--", name)

        err = self.refused("scope", "commit", "--message-file", str(self.given_message()), "--scope-file",
                           self.scope("src\n"))

        self.assertIn("\ne[31mxy\n", err)
        self.assertNotIn("\x1b", err)

    def test_scope__the_scope_file_obeys_the_message_file_rules(self):
        """D23 · the scope file a link to an own file, in the worktree, over 64 KiB, outside the session's folders, or
        holding a NUL line: scope, nothing committed. Unmanaged, one inside the repository: scope."""
        (self.worktree / "f").write_text("x\n")
        self.ok("add", "f")
        real = self.scope("f\n")
        (self.session / "link.txt").symlink_to(real)
        message = str(self.given_message())
        before = self.head()
        for path in (str(self.session / "link.txt"), self.scope("f\n", folder=self.worktree),
                     self.scope("f\n" * (MESSAGE_LIMIT // 2 + 1), name="big.txt"),
                     self.scope("f\n", folder=self.root / "elsewhere"), self.scope("f\n\x00\n", name="ctl.txt")):
            with self.subTest(path=path):
                self.refused("scope", "commit", "--message-file", message, "--scope-file", path)
                self.assertEqual(self.head(), before)
        repo = self.notes_app("feature")
        (repo / "f").write_text("x\n")
        self.ok("add", "f", cwd=repo)
        self.refused("scope", "commit", "--message-file", self.note(), "--scope-file",
                     self.scope("f\n", folder=repo / "notes"), cwd=repo)

    def test_scope__an_amend_is_held_to_the_whole_commit(self):
        """D24 · HEAD added b, outside the scope; c staged inside it: `commit --amend --scope-file` (scope `c`) is
        scope, naming b; HEAD stays."""
        tip = self.commit_in(self.worktree, "b", "b\n", "b outside")
        (self.worktree / "c").write_text("c\n")
        self.ok("add", "c")

        err = self.refused("scope", "commit", "--amend", "--message-file", str(self.given_message()), "--scope-file",
                           self.scope("c\n"))

        self.assertIn("\nb\n", err)
        self.assertEqual(self.head(), tip)

    # -- R5: gitlinks --------------------------------------------------------------------------------------------------

    def gitlink(self, where, path, commit):
        self.git(where, "update-index", "--add", "--cacheinfo", f"160000,{commit},{path}")

    def test_gitlink__an_added_removed_or_moved_gitlink_is_refused(self):
        """D25 · a staged gitlink added at sub; one committed at sub then removed; one moved from sub to lib: gitlink,
        the paths printed, HEAD stays. All with a committed .gitmodules giving sub and lib `ignore = all`, and
        diff.ignoreSubmodules=all and submodule.sub.ignore=all planted."""
        (self.worktree / ".gitmodules").write_text('[submodule "sub"]\n\tpath = sub\n\turl = ./x\n\tignore = all\n'
                                                   '[submodule "lib"]\n\tpath = lib\n\turl = ./x\n\tignore = all\n')
        commit = self.commit_in(self.worktree, ".gitmodules", (self.worktree / ".gitmodules").read_text(), "modules")
        message = str(self.given_message())
        self.git(self.repo, "config", "diff.ignoreSubmodules", "all")
        self.git(self.repo, "config", "submodule.sub.ignore", "all")
        self.gitlink(self.worktree, "sub", commit)
        err = self.refused("gitlink", "commit", "--message-file", message)
        self.assertIn("sub", err)
        self.git(self.worktree, "commit", "-q", "-m", "a gitlink, by plain git")
        tip = self.head()
        self.git(self.worktree, "update-index", "--force-remove", "sub")
        err = self.refused("gitlink", "commit", "--message-file", message)
        self.assertIn("sub", err)
        self.gitlink(self.worktree, "lib", commit)
        err = self.refused("gitlink", "commit", "--message-file", message)
        self.assertIn("sub", err)
        self.assertIn("lib", err)
        self.assertEqual(self.head(), tip)

    def test_gitlink__an_amend_of_a_commit_adding_one_is_refused(self):
        """D26 · HEAD (made by plain git) adds a gitlink at sub; a file staged: `commit --amend` is gitlink."""
        self.gitlink(self.worktree, "sub", self.head())
        self.git(self.worktree, "commit", "-q", "-m", "a gitlink, by plain git")
        tip = self.head()
        (self.worktree / "f").write_text("x\n")
        self.ok("add", "f")

        self.refused("gitlink", "commit", "--amend", "--message-file", str(self.given_message()))

        self.assertEqual(self.head(), tip)

    def test_gitlink__a_file_named_like_the_base_commit_does_not_block_a_commit(self):
        """D40 · an untracked file named HEAD's full id, a file staged: `commit` exits 0 on top of HEAD — without `--`,
        the gitlink check's diff-index read the id as a path too, and refused the commit as ambiguous."""
        tip = self.head()
        (self.worktree / tip).write_text("x\n")
        (self.worktree / "f").write_text("x\n")
        self.ok("add", "f")

        self.ok("commit", "--message-file", str(self.given_message()))

        self.assertEqual(self.git(self.worktree, "rev-parse", "HEAD^"), tip)

    # -- R6: named remotes ---------------------------------------------------------------------------------------------

    def given_fork(self):
        """origin and a second bare remote, fork, holding main and a commit origin does not have."""
        self.given_origin()
        fork = self.root / "fork.git"
        self.git(self.root, "clone", "-q", "--bare", str(self.root / "origin.git"), str(fork))
        clone = self.root / "fork-clone"
        self.git(self.root, "clone", "-q", str(fork), str(clone))
        moved = self.commit_in(clone, "g", "y\n", "fork moved")
        self.git(clone, "push", "-q", "origin", "main")
        self.git(self.repo, "remote", "add", "fork", str(fork))
        return fork, moved

    def test_fetch__a_named_remote_into_its_own_tracking_refs(self):
        """D27 · `fetch --remote fork`: refs/remotes/fork/main is fork's new commit; main and refs/remotes/origin/*
        stay."""
        _, moved = self.given_fork()
        main = self.head(self.repo)
        origin_refs = self.git(self.repo, "for-each-ref", "refs/remotes/origin")

        self.ok("fetch", "--remote", "fork", remote=True)

        self.assertEqual(self.git(self.repo, "rev-parse", "refs/remotes/fork/main"), moved)
        self.assertEqual(self.head(self.repo), main)
        self.assertEqual(self.git(self.repo, "for-each-ref", "refs/remotes/origin"), origin_refs)

    def test_push__an_own_branch_to_a_named_remote_only(self):
        """D28 · a draft-pr hook, remote.fork.mirror and remote.fork.receivepack planted: `push --remote fork <own>`
        exits 0; fork gains that branch and nothing else; origin does not gain it; no marker."""
        fork, _ = self.given_fork()
        self.given_hook("draft-pr")
        self.given_launch_json({**self.config, "push_remotes": {str(self.repo): ["fork"]}})
        self.commit_in(self.worktree, "f", "x\n", "branch work")
        self.git(self.repo, "config", "remote.fork.mirror", "true")
        self.git(self.repo, "config", "remote.fork.receivepack", str(self.program("receive-pack")))
        self.git(self.repo, "config", "remote.fork.uploadpack", str(self.program("upload-pack")))

        self.ok("push", "--remote", "fork", BRANCH, remote=True)
        self.ok("fetch", "--remote", "fork", remote=True)

        self.assertEqual(self.git(fork, "for-each-ref", "--format=%(refname)"), f"refs/heads/main\nrefs/heads/{BRANCH}")
        self.assertEqual(self.git(self.root / "origin.git", "branch", "--list", BRANCH), "")

    def test_remote__a_name_not_configured_or_out_of_shape_is_refused(self):
        """D29 · `--remote` naming no remote; `fork/x`, `.hidden` and `fork x`, each configured; a 65-byte name; a URL:
        remote-unknown for fetch and push, no refs/remotes written; `fetch --remote` with no name and `push --remote fork` with no branch: usage."""
        fork, _ = self.given_fork()
        self.given_hook("draft-pr")
        for name in ("fork/x", ".hidden", "fork x"):
            self.git(self.repo, "config", f"remote.{name}.url", str(fork))
        for name in ("nowhere", "fork/x", ".hidden", "a" * 65, "https://example.invalid/sample.git", "fork x"):
            for args in (["fetch", "--remote", name], ["push", "--remote", name, BRANCH]):
                with self.subTest(args=args):
                    self.refused("remote-unknown", *args, remote=True)
        self.assertEqual(self.git(self.repo, "for-each-ref", "refs/remotes/fork/x", "refs/remotes/.hidden"), "")
        for args in (["fetch", "--remote"], ["push", "--remote", "fork"], ["fetch", "--remote", "-x"],
                     ["push", "--remote", "fork", "--force-with-lease", BRANCH]):
            with self.subTest(args=args):
                self.refused("usage", *args, remote=True)

    def test_push__only_to_origin_or_a_remote_push_remotes_lists(self):
        """D38 · fork configured, a draft-pr hook: with no `push_remotes`, with one listing fork for another repository
        only, and with one listing upstream for this one, `push --remote fork <own>` is remote-unknown naming
        push_remotes and fork lacks the branch; `fetch --remote fork` still exits 0."""
        fork, _ = self.given_fork()
        self.given_hook("draft-pr")
        self.commit_in(self.worktree, "f", "x\n", "branch work")
        other = str(self.root / "other-repo")
        for remotes in (None, {other: ["fork"]}, {str(self.repo): ["upstream"]}):
            with self.subTest(push_remotes=remotes):
                self.given_launch_json(self.config if remotes is None else {**self.config, "push_remotes": remotes})
                err = self.refused("remote-unknown", "push", "--remote", "fork", BRANCH, remote=True)
                self.assertIn("push_remotes", err)
                self.assertEqual(self.git(fork, "branch", "--list", BRANCH), "")
        self.ok("fetch", "--remote", "fork", remote=True)

    def test_push__a_push_remotes_value_out_of_shape_is_refused_by_name(self):
        """D39 · `push_remotes` a list, a string for the repository, a list holding `fork/x`, a relative key:
        launch-config naming push_remotes, and fork lacks the branch."""
        fork, _ = self.given_fork()
        self.given_hook("draft-pr")
        self.commit_in(self.worktree, "f", "x\n", "branch work")
        for remotes in (["fork"], {str(self.repo): "fork"}, {str(self.repo): ["fork/x"]}, {"rel": ["fork"]}):
            with self.subTest(push_remotes=remotes):
                self.given_launch_json({**self.config, "push_remotes": remotes})
                err = self.refused("launch-config", "push", "--remote", "fork", BRANCH, remote=True)
                self.assertIn("push_remotes", err)
        self.assertEqual(self.git(fork, "branch", "--list", BRANCH), "")

    def test_remote__a_named_remote_on_a_local_transport_is_refused_by_git(self):
        """D30 · fork's URL a file:// path, the protocol list unpatched: `fetch --remote fork` exits 1 with git's
        transport 'file' not allowed; no refs/remotes/fork."""
        self.given_fork()
        self.git(self.repo, "remote", "set-url", "fork", (self.root / "fork.git").as_uri())

        code, _, err = self.rw("fetch", "--remote", "fork")

        self.assertEqual(code, 1, err)
        self.assertIn("transport 'file' not allowed", err)
        self.assertEqual(self.git(self.repo, "for-each-ref", "refs/remotes/fork"), "")

    # -- review 1: refspec patterns, folded names, one rw-git at a time ------------------------------------------------

    def test_push__a_name_that_is_a_pattern_or_two_refs_is_refused(self):
        """D31 · desk/notes-app on feature, local develop one commit past origin's, a draft-pr hook: `push 'd*'`,
        `'*'`, `'de?elop'`, `'[d]evelop'`, `'feature:develop'`, `'feature~0'`, `'feature^0'`, `'feat\\ure'`,
        `'main..feature'` are branch-protected; origin's refs stay."""
        repo = self.notes_app()
        origin = self.root / "notes-origin.git"
        self.git(self.root, "init", "-q", "--bare", "-b", "main", str(origin))
        self.git(repo, "remote", "add", "origin", str(origin))
        hook = repo / ".claude" / "robowright" / "project.md"
        hook.parent.mkdir(parents=True)
        hook.write_text("# Project hook\n\n## 10 · Publishing\n\npublish_strategy: draft-pr\n")
        self.git(repo, "switch", "-q", "-c", "develop")
        self.git(repo, "push", "-q", "origin", "main", "develop")
        self.commit_in(repo, "d", "d\n", "develop moved")
        self.git(repo, "switch", "-q", "-c", "feature")
        self.commit_in(repo, "f", "f\n", "feature work")
        refs = self.git(origin, "for-each-ref")

        for name in ("d*", "*", "de?elop", "[d]evelop", "feature:develop", "feature~0", "feature^0", "feat\\ure",
                     "main..feature"):
            with self.subTest(name=name):
                self.refused("branch-protected", "push", name, cwd=repo, remote=True)
                self.assertEqual(self.git(origin, "for-each-ref"), refs)

    def test_unmanaged__a_name_the_disk_folds_onto_a_protected_one_is_protected(self):
        """D32 · on main, master existing: `switch -c maſter`, `releaſe/1`, `café` are branch-protected and make no
        branch; with HEAD on refs/heads/maſter (plain git), `commit` is branch-protected and master stays."""
        repo = self.notes_app()
        self.git(repo, "branch", "master")
        master = self.git(repo, "rev-parse", "master")
        self.commit_in(repo, "f", "x\n", "main moved")

        for name in ("maſter", "releaſe/1", "café"):
            with self.subTest(name=name):
                self.refused("branch-protected", "switch", "-c", name, cwd=repo)
                self.assertEqual(self.branch(repo), "main")
                self.assertEqual(self.git(repo, "rev-parse", "master"), master)
        self.assertEqual(self.git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/"), "main\nmaster")
        self.git(repo, "symbolic-ref", "HEAD", "refs/heads/maſter")
        (repo / "g").write_text("y\n")
        self.ok("add", "g", cwd=repo)
        self.refused("branch-protected", "commit", "--message-file", self.note(), cwd=repo)
        self.assertEqual(self.git(repo, "rev-parse", "master"), master)

    def test_unmanaged__a_write_waits_for_the_repository_lock_and_checks_head_after_it(self):
        """D33 · on feature, one commit past develop, a shared lock held on <git dir>/rw-git.lock: `reset --soft
        <feature tip>` is still running after 1 s; HEAD moved to develop meanwhile; once the lock is released it is
        branch-protected and develop stays. From a linked worktree, `switch -c` waits on the same lock."""
        repo = self.notes_app()
        self.git(repo, "branch", "develop")
        develop = self.head(repo)
        self.git(repo, "switch", "-q", "-c", "feature")
        tip = self.commit_in(repo, "f", "x\n", "feature work")
        held = os.open(repo / ".git" / "rw-git.lock", os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, held)
        two = self.desk / "notes-two"
        self.git(repo, "worktree", "add", "-q", "-b", "two", str(two), develop)
        fcntl.flock(held, fcntl.LOCK_SH)
        waiting = self.started("reset", "--soft", tip, cwd=repo)
        linked = self.started("switch", "-c", "two-more", cwd=two)

        time.sleep(1)
        self.assertIsNone(waiting.poll(), "rw-git ran while the repository's lock was held")
        self.assertIsNone(linked.poll(), "rw-git in a linked worktree ran while the repository's lock was held")
        self.git(repo, "symbolic-ref", "HEAD", "refs/heads/develop")
        fcntl.flock(held, fcntl.LOCK_UN)
        _, err = waiting.communicate(timeout=60)
        linked.communicate(timeout=60)

        self.assertEqual(waiting.returncode, 2, err)
        self.assertIn("refused: branch-protected:", err)
        self.assertEqual(self.git(repo, "rev-parse", "develop"), develop)
        self.assertEqual(linked.returncode, 0)

    def test_unmanaged__a_call_stalled_on_a_fifo_makes_another_worktree_s_call_repo_busy_not_wait(self):
        """D34 · desk/notes-app's `rw-git add x.txt` stalled on a FIFO named .gitignore; from the linked worktree
        desk/notes-two, `rw-git add y.txt` with the deadline patched to 1 s is repo-busy naming rw-git.lock, within
        15 s."""
        repo = self.notes_app()
        two = self.desk / "notes-two"
        self.git(repo, "worktree", "add", "-q", "-b", "two", str(two))
        (repo / "x.txt").write_text("x\n")
        (two / "y.txt").write_text("y\n")
        fifo = repo / ".gitignore"
        os.mkfifo(fifo)
        stalled = self.started("add", "x.txt", cwd=repo)
        self.addCleanup(lambda: stalled.poll() is None and os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)))
        time.sleep(1)
        self.assertIsNone(stalled.poll(), "the FIFO did not stall git add")

        code, _, err = self.rw("add", "y.txt", cwd=two, env={**self.plain_env(), "RW_TEST_LOCK_WAIT": "1"}, timeout=15)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: repo-busy:", err)
        self.assertIn("rw-git.lock", err)

    def test_unmanaged__a_call_whose_output_nobody_reads_does_not_hold_the_lock(self):
        """D35 · desk/notes-app commits 3,000 staged files under `rw-git commit` whose stdout nobody reads; once the
        commit is made, `rw-git add y.txt` in the linked worktree desk/notes-two, deadline patched to 5 s, exits 0."""
        repo = self.notes_app("notes")
        two = self.desk / "notes-two"
        self.git(repo, "worktree", "add", "-q", "-b", "two", str(two))
        (two / "y.txt").write_text("y\n")
        many = repo / "many"
        many.mkdir()
        for number in range(3000):
            (many / f"file-{number:04}.txt").write_text(f"{number}\n")
        self.git(repo, "add", "many")
        before = self.head(repo)
        holder = self.started("commit", "--message-file", self.note(), cwd=repo)
        deadline = time.monotonic() + 60
        while self.head(repo) == before and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertNotEqual(self.head(repo), before, "the commit was not made")

        code, _, err = self.rw("add", "y.txt", cwd=two, env={**self.plain_env(), "RW_TEST_LOCK_WAIT": "5"}, timeout=20)

        self.assertEqual(code, 0, err)
        out, _ = holder.communicate(timeout=60)
        self.assertEqual(holder.returncode, 0)
        self.assertGreater(len(out), 65536)

    def plain_env(self):
        return {"HOME": str(self.home), "PATH": os.environ["PATH"], "TMPDIR": str(self.root)}

    def started(self, *args, cwd):
        """rw-git running in `cwd`, as `rw` runs it, not waited for."""
        program = [sys.executable, "-I", str(self.runner), str(SCRIPTS), "local", *args]
        env = {**self.plain_env(), "RW_TEST_HOME": str(self.home), "RW_TEST_TEMP": str(self.root / "temp")}
        process = subprocess.Popen(program, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        return process


class GrantsReaderTests(unittest.TestCase):
    """role_grants.desktop_grants, the one reader of the folders a Desktop session is granted (U47 points at it)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        sys.path.insert(0, str(SCRIPTS))
        import role_grants
        self.role_grants = role_grants

    def read(self, settings, config=None):
        role_grants = self.role_grants
        (self.home / ".claude" / "settings.json").write_text(json.dumps(settings))
        return role_grants.desktop_grants(config or {}, str(self.home))

    def test_grants__allow_write_and_additional_directories_count_and_globs_do_not(self):
        """G1 · allowWrite ~/a and //b, additionalDirectories c-abs, allowWrite with a glob or relative: a, b and c."""
        for name in ("a", "b", "c"):
            (self.root / name).mkdir()
        granted, _ = self.read({"sandbox": {"filesystem": {"allowWrite": ["~/../a", f"/{self.root}/b", "rel",
                                                                          f"{self.root}/*"]}},
                                "permissions": {"additionalDirectories": [str(self.root / "c")]}})
        self.assertEqual(granted, [str(self.root / "a"), str(self.root / "b"), str(self.root / "c")])

    def test_grants__denies_are_kept_as_globs_and_counted_from_every_source(self):
        """G2 · denyWrite /x/y*, Edit(~/z/**), Edit alone, Read(/w): `/x/y*`, `~/z/**` and `/` denied as written, `/w`
        not; `/x/y*` holds /x/yz/r and not /x/a, `~/z/**` holds ~/z itself."""
        _, denied = self.read({"sandbox": {"filesystem": {"denyWrite": ["/x/y*"]}},
                               "permissions": {"deny": ["Edit(~/z/**)", "Edit", "Read(/w)"]}})
        self.assertIn("/x/y*", denied)
        self.assertIn(f"{self.home}/z/**", denied)
        self.assertIn("/", denied)
        self.assertNotIn("/w", denied)
        globs = ["/x/y*", f"{self.home}/z/**"]
        self.assertTrue(self.role_grants.is_denied("/x/yz/r", globs))
        self.assertFalse(self.role_grants.is_denied("/x/a", globs))
        self.assertTrue(self.role_grants.is_denied(str(self.home / "z"), globs))

    def test_temp__the_account_temp_folders_are_its_own_and_unlinked(self):
        """G4 · own_temp_folders: /private/tmp/claude-<uid> when this account owns it, never the /tmp spelling, and
        every folder it names is a real directory this uid owns. Declared guard for the ownership check: nothing here
        can plant a /private/tmp/claude-<uid> another account owns, which is the defect it stops."""
        sys.path.insert(0, str(SCRIPTS))
        import rw_git
        found = rw_git.own_temp_folders()
        tmp = f"/private/tmp/claude-{os.getuid()}"
        if os.path.isdir(tmp) and os.lstat(tmp).st_uid == os.getuid():
            self.assertIn(tmp, found)
        for folder in found:
            self.assertTrue(folder.startswith("/private/"), folder)
            self.assertEqual(os.lstat(folder).st_uid, os.getuid())
            self.assertFalse(os.path.islink(folder))

    def test_grants__an_unreadable_root_settings_file_is_refused(self):
        """G3 · a `desktop_roots` folder whose .claude/settings.json is not JSON: Refused, so its denies are not lost."""
        root = self.root / "desk"
        (root / ".claude").mkdir(parents=True)
        (root / ".claude" / "settings.json").write_text("{")
        with self.assertRaises(self.role_grants.Refused):
            self.read({}, {"desktop_roots": [str(root)]})


class PlantedConfigTests(RwGitCase):
    """Each planted key names a program that touches a marker; after the subcommands that could reach it, none exists."""

    def plant(self, *pairs):
        for key, value in pairs:
            self.git(self.repo, "config", key, str(value))

    def plant_hooks(self):
        hooks = self.root / "hooks"
        hooks.mkdir()
        for name in HOOK_NAMES:
            shutil.copy(self.program(f"hook-{name}"), hooks / name)
            shutil.copy(hooks / name, self.repo / ".git" / "hooks" / name)
        self.plant(("core.hooksPath", hooks))

    def plant_filters(self, pattern):
        attributes = f"{pattern} filter=mark merge=mark diff=mark\n"
        (self.worktree / ".gitattributes").write_text(attributes)
        (self.repo / ".git" / "info" / "attributes").write_text(attributes)
        self.plant(("filter.mark.clean", self.program("filter-clean")),
                   ("filter.mark.smudge", self.program("filter-smudge")),
                   ("filter.mark.process", self.program("filter-process")),
                   ("filter.mark.required", "false"),
                   ("merge.mark.driver", f"{self.program('merge-driver')} %O %A %B"),
                   ("diff.mark.command", self.program("diff-command")),
                   ("diff.mark.textconv", self.program("diff-textconv")))

    def every_local_subcommand(self):
        """Every subcommand that needs no remote, each run whatever the last one did."""
        message = str(self.given_message())
        (self.worktree / "f").write_text("x\n")
        self.rw("add", "f")
        self.rw("commit", "--message-file", message)
        (self.worktree / "README").write_text("edited\n")
        self.rw("restore", "README")
        self.rw("stash", "push", "README")
        self.rw("stash", "pop")
        self.rw("switch", "-c", f"{BRANCH}-u2")
        self.rw("switch", BRANCH)
        tip, base = self.given_conflict()
        self.rw("rebase", base)
        self.rw("rebase", "--abort")
        self.rw("cherry-pick", base)
        (self.worktree / "README").write_text("resolved\n")
        self.rw("add", "README")
        self.rw("cherry-pick", "--continue")
        self.rw("rebase", "--autosquash", base)

    def test_k0__every_key_at_once_under_every_subcommand(self):
        """K0 · every program-naming key planted: no marker after every subcommand, local and remote."""
        self.given_origin()
        self.given_hook("draft-pr")
        self.plant_hooks()
        self.plant_filters("*.dat")
        self.plant(("core.fsmonitor", self.program("fsmonitor")), ("core.pager", self.program("pager")),
                   ("pager.log", self.program("pager-log")), ("core.editor", self.program("editor")),
                   ("sequence.editor", self.program("sequence-editor")), ("diff.external", self.program("diff-external")),
                   ("core.sshCommand", self.program("ssh-command")), ("credential.helper", self.program("credential")),
                   ("core.askPass", self.program("askpass")), ("gpg.program", self.program("gpg")),
                   ("gpg.ssh.program", self.program("gpg-ssh")), ("commit.gpgSign", "true"),
                   ("core.alternateRefsCommand", self.program("alternate-refs")), ("gc.auto", "1"),
                   ("gc.recentObjectsHook", self.program("recent-objects")),
                   ("remote.origin.uploadpack", self.program("upload-pack")),
                   ("remote.origin.receivepack", self.program("receive-pack")))

        self.every_local_subcommand()
        self.rw("fetch", remote=True)
        self.rw("push", BRANCH, remote=True)

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.git(self.root / "origin.git", "rev-parse", BRANCH),
                         self.git(self.worktree, "rev-parse", f"refs/heads/{BRANCH}"))

    def test_k24__config_hooks_by_name__a_name_holding_an_equals_sign_included(self):
        """K24 · hook.<name>.event and .command (git 2.54), which core.hooksPath=/dev/null does not turn off, for a
        plain name, one holding `=`, and the empty name `[hook ""]`: commit (pre-commit) and switch (post-checkout)
        run no marker."""
        for name in ("probe", "a=b"):
            self.plant((f"hook.{name}.event", "pre-commit"), (f"hook.{name}.command", self.program(f"hook-{name}")))
            self.git(self.repo, "config", "--add", f"hook.{name}.event", "post-checkout")
        with open(self.repo / ".git" / "config", "a") as config:
            config.write(f'[hook ""]\n\tevent = pre-commit\n\tevent = post-checkout\n\tcommand = {self.program("hook-empty")}\n')
        (self.worktree / "f").write_text("x\n")

        self.ok("add", "f")
        self.ok("commit", "--message-file", str(self.given_message()))
        self.ok("switch", "-c", f"{BRANCH}-u2")
        self.ok("switch", BRANCH)

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%s"), "sample: a change")

    def test_k25__a_driver_whose_name_holds_an_equals_sign(self):
        """K25 · filter.a=b.smudge named by $GIT_DIR/info/attributes: switch to a branch that checks the file out runs no
        marker; a `-c filter.a=b.smudge=` is split at the first `=` and never reaches the driver."""
        self.git(self.worktree, "switch", "-q", "-c", f"{BRANCH}-u2")
        self.commit_in(self.worktree, "c.txt", "kept\n", "sample: c")
        self.git(self.worktree, "switch", "-q", BRANCH)
        (self.repo / ".git" / "info" / "attributes").write_text("c.txt filter=a=b\n")
        self.plant(("filter.a=b.smudge", self.program("smudge-a=b")))

        self.ok("switch", f"{BRANCH}-u2")

        self.assertEqual(self.marked(), [])
        self.assertEqual((self.worktree / "c.txt").read_text(), "kept\n")

    def test_k25_1__a_driver_with_the_empty_name(self):
        """K25.1 · `[filter ""]` smudge, named by an $GIT_DIR/info/attributes line `c.txt filter=`: switch to a branch
        that checks the file out runs no marker (gate F1: plain git runs filter..smudge for it)."""
        self.git(self.worktree, "switch", "-q", "-c", f"{BRANCH}-u2")
        self.commit_in(self.worktree, "c.txt", "kept\n", "sample: c")
        self.git(self.worktree, "switch", "-q", BRANCH)
        (self.repo / ".git" / "info" / "attributes").write_text("c.txt filter=\n")
        with open(self.repo / ".git" / "config", "a") as config:
            config.write(f'[filter ""]\n\tsmudge = {self.program("smudge-empty")}\n')

        self.ok("switch", f"{BRANCH}-u2")

        self.assertEqual(self.marked(), [])
        self.assertEqual((self.worktree / "c.txt").read_text(), "kept\n")

    def test_k1__fsmonitor(self):
        """K1 · core.fsmonitor: add, commit, restore run no marker."""
        self.plant(("core.fsmonitor", self.program("fsmonitor")))
        (self.worktree / "f").write_text("x\n")

        (self.worktree / "README").write_text("edited\n")
        self.ok("add", "f")
        self.ok("commit", "--message-file", str(self.given_message()))
        self.ok("restore", "README")

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%s"), "sample: a change")

    def test_k2__hooks(self):
        """K2 · core.hooksPath and .git/hooks, every hook name: commit, switch, rebase, pick, stash, push, no marker."""
        self.plant_hooks()
        self.given_origin()
        self.given_hook("draft-pr")

        self.every_local_subcommand()
        self.rw("push", BRANCH, remote=True)

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.git(self.root / "origin.git", "rev-parse", BRANCH),
                         self.git(self.worktree, "rev-parse", f"refs/heads/{BRANCH}"))

    def test_k3_to_k6__the_pager_editor_and_external_diff_keys_are_overridden_on_every_call(self):
        """K3–K6 · declared guard: no subcommand pages, edits or diffs, so no planted key can show; the argv carries
        core.pager=cat, core.editor=false, sequence.editor=false and diff.external= so a later subcommand that does
        cannot run a program a repository names."""
        sys.path.insert(0, str(SCRIPTS))
        import rw_git

        argv = rw_git.git_argv("/nowhere/.git", "/nowhere", [], "status")

        for pair in ("core.pager=cat", "core.editor=false", "sequence.editor=false", "diff.external="):
            self.assertIn(pair, argv)
        self.assertIn("--no-pager", argv)

    def test_k7__ssh_command(self):
        """K7 · core.sshCommand, an ssh:// origin: fetch runs no marker."""
        self.plant(("core.sshCommand", self.program("ssh-command")))
        self.git(self.repo, "remote", "add", "origin", "ssh://127.0.0.1:1/sample.git")

        self.rw("fetch", timeout=60)

        self.assertEqual(self.marked(), [])

    def test_k8__credential_helpers_from_the_repository(self):
        """K8 · credential.helper and credential.<url>.helper: a fetch answered 401 runs no marker."""
        server, url = self.given_http_origin()
        self.plant(("credential.helper", self.program("credential")),
                   (f"credential.{url}.helper", self.program("credential-url")))

        self.rw("fetch", remote=True)

        self.assertEqual(self.marked(), [])
        self.assertNotEqual(server.seen, [])

    def test_k9__askpass(self):
        """K9 · core.askPass: a fetch answered 401 runs no marker. Declared guard behind GIT_TERMINAL_PROMPT=0, which
        stops git asking at all; with both gone it reddens."""
        server, _ = self.given_http_origin()
        self.plant(("core.askPass", self.program("askpass")))

        self.rw("fetch", remote=True)

        self.assertEqual(self.marked(), [])
        self.assertNotEqual(server.seen, [])

    def test_k10__a_command_transport_the_repository_allows(self):
        """K10 · protocol.ext.allow=always and an ext:: origin: fetch exit 1, no marker."""
        self.plant(("protocol.ext.allow", "always"), ("protocol.allow", "always"),
                   ("remote.origin.url", f"ext::{self.program('ext')} %S"))

        code, _, _ = self.rw("fetch")

        self.assertEqual(code, 1)
        self.assertEqual(self.marked(), [])

    def test_k23__a_remote_helper_the_repository_names(self):
        """K23 · remote.origin.vcs=ext with protocol.ext.allow=always: fetch exit 1, no marker."""
        self.plant(("protocol.ext.allow", "always"), ("remote.origin.vcs", "ext"),
                   ("remote.origin.url", f"{self.program('vcs')} %S"))

        code, _, _ = self.rw("fetch")

        self.assertEqual(code, 1)
        self.assertEqual(self.marked(), [])

    def test_k11__upload_pack(self):
        """K11 · remote.origin.uploadpack, a local origin: fetch runs no marker and fetches."""
        origin = self.given_origin()
        clone = self.root / "clone"
        self.git(self.root, "clone", "-q", str(origin), str(clone))
        moved = self.commit_in(clone, "g", "y\n", "origin moved")
        self.git(clone, "push", "-q", "origin", "main")
        self.plant(("remote.origin.uploadpack", self.program("upload-pack")))

        self.rw("fetch", remote=True)

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.git(self.repo, "rev-parse", "refs/remotes/origin/main"), moved)

    def test_k12__receive_pack(self):
        """K12 · remote.origin.receivepack: push runs no marker and pushes."""
        origin = self.given_origin()
        self.given_hook("draft-pr")
        self.plant(("remote.origin.receivepack", self.program("receive-pack")))

        self.rw("push", BRANCH, remote=True)

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.git(origin, "rev-parse", f"refs/heads/{BRANCH}"), self.head())

    def test_k13__filter_drivers(self):
        """K13 · filter.<driver>.clean, .smudge, .process named by .gitattributes: add refused (R16), restore and
        switch land, no marker."""
        self.plant_filters("*")
        (self.worktree / "f").write_text("x\n")

        self.refused("attributes", "add", "f")
        (self.worktree / "README").write_text("edited\n")
        self.ok("restore", "README")
        self.ok("switch", "-c", f"{BRANCH}-u2")
        self.ok("switch", BRANCH)

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.staged(), [])
        self.assertEqual((self.worktree / "README").read_text(), "base\n")

    def test_k14__merge_driver(self):
        """K14 · merge.<driver>.driver named by a committed .gitattributes: a conflicting pick runs no marker."""
        (self.repo / ".gitattributes").write_text("* merge=mark\n")
        self.git(self.repo, "add", ".gitattributes")
        self.git(self.repo, "commit", "-q", "-m", "attributes")
        self.git(self.worktree, "merge", "-q", "--ff-only", "main")
        self.plant(("merge.mark.driver", f"{self.program('merge-driver')} %O %A %B"))
        _, base = self.given_conflict()

        self.rw("cherry-pick", base)

        self.assertEqual(self.marked(), [])
        self.assertEqual(self.git(self.worktree, "rev-parse", "CHERRY_PICK_HEAD"), base)

    def test_k15__alternate_refs_command(self):
        """K15 · core.alternateRefsCommand with an alternate: fetch runs no marker."""
        self.given_origin()
        borrowed = self.given_repo(self.root / "borrowed")
        (self.repo / ".git" / "objects" / "info" / "alternates").write_text(f"{borrowed / '.git' / 'objects'}\n")
        self.plant(("core.alternateRefsCommand", self.program("alternate-refs")))
        origin_clone = self.root / "clone"
        self.git(self.root, "clone", "-q", str(self.root / "origin.git"), str(origin_clone))
        self.commit_in(origin_clone, "g", "y\n", "origin moved")
        self.git(origin_clone, "push", "-q", "origin", "main")

        self.rw("fetch", remote=True)

        self.assertEqual(self.marked(), [])

    def test_k16__no_automatic_gc(self):
        """K16 · gc.auto=1 and gc.recentObjectsHook over many loose objects: a commit packs nothing, no marker."""
        self.plant(("gc.auto", "1"), ("gc.autoDetach", "false"), ("gc.recentObjectsHook", self.program("recent-objects")))
        blobs = "".join(f"loose {n}\n" for n in range(600))
        loose = self.root / "loose"
        loose.mkdir()
        for number, line in enumerate(blobs.splitlines()):
            (loose / str(number)).write_text(line)
        self.git(self.repo, "hash-object", "-w", *[str(p) for p in loose.iterdir()])
        packs = sorted((self.repo / ".git" / "objects" / "pack").iterdir())
        (self.worktree / "f").write_text("x\n")

        self.ok("add", "f")
        self.ok("commit", "--message-file", str(self.given_message()))

        self.assertEqual(sorted((self.repo / ".git" / "objects" / "pack").iterdir()), packs)
        self.assertEqual(self.marked(), [])

    def test_k17__signing_programs(self):
        """K17 · commit.gpgSign with gpg.program and gpg.ssh.program: commit, rebase, pick run no marker, unsigned."""
        self.plant(("commit.gpgSign", "true"), ("gpg.program", self.program("gpg")),
                   ("gpg.ssh.program", self.program("gpg-ssh")))
        picked = self.commit_in(self.repo, "g", "y\n", "on main")
        (self.worktree / "f").write_text("x\n")

        self.rw("add", "f")
        self.ok("commit", "--message-file", str(self.given_message()))
        self.ok("cherry-pick", picked)
        self.ok("rebase", picked)

        self.assertEqual(self.marked(), [])
        self.assertNotIn("gpgsig", self.git(self.worktree, "cat-file", "commit", "HEAD"))

    def test_k18__cookie_files(self):
        """K18 · http.cookieFile and http.<url>.cookieFile with saveCookies: a fetch writes neither file."""
        server, url = self.given_http_origin()
        plain, scoped = self.root / "cookies-plain", self.root / "cookies-scoped"
        self.plant(("http.cookieFile", plain), ("http.saveCookies", "true"),
                   (f"http.{url}.cookieFile", scoped), (f"http.{url}.saveCookies", "true"))

        self.rw("fetch", remote=True)

        self.assertNotEqual(server.seen, [])
        self.assertFalse(plain.exists())
        self.assertFalse(scoped.exists())

    def test_k18__a_planted_cookie_file_is_not_read(self):
        """K18 · http.cookieFile, then http.<url>.cookieFile, naming a file of cookies for the origin: a fetch sends
        neither cookie."""
        server, url = self.given_http_origin()
        for key, name in (("http.cookieFile", "plain"), (f"http.{url}.cookieFile", "scoped")):
            with self.subTest(key):
                cookies = self.root / f"cookies-{name}"
                cookies.write_text(f"127.0.0.1\tFALSE\t/\tFALSE\t4102444800\t{name}\tmarker-{name}\n")
                self.plant((key, cookies))
                server.seen.clear()

                self.rw("fetch", remote=True)

                self.assertNotEqual(server.seen, [])
                self.assertNotIn(f"marker-{name}", " ".join(seen.get("Cookie", "") for seen in server.seen))
                self.git(self.repo, "config", "--unset", key)

    def test_k19__core_worktree(self):
        """K19 · core.worktree naming another folder: restore, in the worktree and in the main checkout, writes that
        checkout's file, the other folder untouched."""
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.plant(("core.worktree", elsewhere))
        for checkout in (self.worktree, self.repo):
            with self.subTest(checkout.name):
                (checkout / "README").write_text("edited\n")

                self.rw("restore", "README", cwd=checkout)

                self.assertEqual((checkout / "README").read_text(), "base\n")
                self.assertEqual(list(elsewhere.iterdir()), [])

    def test_k20__update_refs(self):
        """K20 · rebase.updateRefs and a branch pointing into the range: the branch does not move."""
        self.plant(("rebase.updateRefs", "true"))
        middle = self.commit_in(self.worktree, "f", "x\n", "one")
        self.git(self.repo, "branch", "bystander", middle)
        self.commit_in(self.worktree, "g", "y\n", "two")
        base = self.commit_in(self.repo, "h", "z\n", "main moved")

        self.ok("rebase", base)

        self.assertEqual(self.git(self.repo, "rev-parse", "bystander"), middle)

    def test_k21__configured_fetch_refspec(self):
        """K21 · remote.origin.fetch mapping onto refs/heads/*: fetch makes no local branch."""
        origin = self.given_origin()
        self.git(self.repo, "push", "-q", "origin", "main:refs/heads/bystander")
        self.plant(("remote.origin.fetch", "+refs/heads/*:refs/heads/*"))
        self.git(self.repo, "config", "--add", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        self.assertTrue(origin.exists())

        self.ok("fetch", remote=True)

        self.assertEqual(self.git(self.repo, "branch", "--list", "bystander"), "")

    def test_k22__mirror_and_follow_tags(self):
        """K22 · remote.origin.mirror and push.followTags with an annotated tag and a side branch: origin gains the
        branch only."""
        origin = self.given_origin()
        self.given_hook("draft-pr")
        self.commit_in(self.worktree, "f", "x\n", "branch work")
        self.git(self.worktree, "tag", "-a", "-m", "v1", "v1")
        self.git(self.repo, "branch", "side")
        self.plant(("remote.origin.mirror", "true"), ("push.followTags", "true"))

        self.ok("push", BRANCH, remote=True)

        self.assertEqual(self.git(origin, "for-each-ref", "--format=%(refname)"),
                         f"refs/heads/main\nrefs/heads/{BRANCH}")


class ShippedProtocolTests(RwGitCase):
    def test_fetch__a_local_origin_is_not_a_transport_rw_git_uses(self):
        """P1 · a file origin, the protocol list unpatched: exit 1, transport 'file' not allowed, nothing fetched."""
        origin = self.given_origin()
        clone = self.root / "clone"
        self.git(self.root, "clone", "-q", str(origin), str(clone))
        self.commit_in(clone, "g", "y\n", "origin moved")
        self.git(clone, "push", "-q", "origin", "main")
        before = self.git(self.repo, "for-each-ref", "refs/remotes")

        code, _, err = self.rw("fetch")

        self.assertEqual(code, 1, err)
        self.assertIn("transport 'file' not allowed", err)
        self.assertEqual(self.git(self.repo, "for-each-ref", "refs/remotes"), before)


class ExplicitWorktreeTests(RwGitCase):
    """U63: `--dir <path>` names the worktree. Every call runs from a plain folder outside every listed checkout, as a
    desktop-app background task's shell does."""

    def setUp(self):
        super().setUp()
        self.outside = self.root / "outside"
        self.outside.mkdir()

    def ok_at(self, where, *args, **kwargs):
        return self.ok("--dir", str(where), *args, cwd=self.outside, **kwargs)

    def refused_at(self, code_name, where, *args):
        return self.refused(code_name, "--dir", str(where), *args, cwd=self.outside)

    def git_files(self):
        """{path: (size, mtime)} for every file in the shared git directory but rw-git.lock."""
        common = self.repo / ".git"
        return {str(path.relative_to(common)): (path.stat().st_size, path.stat().st_mtime_ns)
                for path in common.rglob("*") if path.is_file() and path.name != "rw-git.lock"}

    def test_where__prints_the_worktree_dir_names(self):
        """X1 · `--dir <worktree> where` from outside: exit 0, the five lines naming the managed worktree."""
        git_dir = self.git(self.worktree, "rev-parse", "--absolute-git-dir")

        out = self.ok_at(self.worktree, "where")

        self.assertEqual(out.splitlines(), [f"worktree: {self.worktree}", f"repository: {self.repo}",
                                            f"git-dir: {git_dir}", f"kind: managed {SLUG}", f"head: {BRANCH}"])

    def test_where__without_dir_is_refused_as_today(self):
        """X2 · `where` from outside, no `--dir`: worktree-unlisted with W7.1's text — the cwd still decides alone."""
        err = self.refused("worktree-unlisted", "where", cwd=self.outside)

        self.assertIn(str(self.outside), err)
        self.assertIn("`repos`", err)
        self.assertIn("`desktop_roots`", err)

    def test_where__writes_nothing_in_the_git_directory(self):
        """X3 · `--dir <worktree> where`: every git directory file but rw-git.lock unchanged — where is read-only."""
        self.ok_at(self.worktree, "where")
        before = self.git_files()
        time.sleep(0.01)

        self.ok_at(self.worktree, "where")

        self.assertEqual(self.git_files(), before)

    def test_add__dir_serves_it_as_the_working_directory_did(self):
        """X4 · `--dir <worktree> add f` from outside: f staged, exit 0, as W1."""
        (self.worktree / "f").write_text("x\n")

        self.ok_at(self.worktree, "add", "f")

        self.assertEqual(self.staged(), ["f"])

    def test_commit__dir_serves_it_as_the_working_directory_did(self):
        """X5 · `--dir <worktree> commit --message-file` from outside: one commit on the branch, as S4."""
        (self.worktree / "f").write_text("x\n")
        self.git(self.worktree, "add", "f")
        parent = self.head()

        self.ok_at(self.worktree, "commit", "--message-file", str(self.given_message("sample: from outside\n")))

        self.assertEqual(self.git(self.worktree, "log", "-1", "--format=%an <%ae>|%P|%s"),
                         f"{NAME} <{EMAIL}>|{parent}|sample: from outside")
        self.assertEqual(self.branch(), BRANCH)

    def test_switch__dir_serves_create_and_return(self):
        """X6 · `--dir <worktree> switch -c <slug>-u2`, then `switch <slug>`: on each in turn, as S5, S6."""
        self.ok_at(self.worktree, "switch", "-c", f"{BRANCH}-u2")
        self.assertEqual(self.branch(), f"{BRANCH}-u2")

        self.ok_at(self.worktree, "switch", BRANCH)

        self.assertEqual(self.branch(), BRANCH)

    def test_rebase__dir_serves_it_as_the_working_directory_did(self):
        """X7 · `--dir <worktree> rebase <base>` from outside: parented on the base, the old tip named, as S7."""
        self.commit_in(self.worktree, "f", "x\n", "branch work")
        old = self.head()
        base = self.commit_in(self.repo, "g", "y\n", "main moved")

        out = self.ok_at(self.worktree, "rebase", base)

        self.assertEqual(self.git(self.worktree, "rev-parse", "HEAD~1"), base)
        self.assertIn(old, out)

    def test_add__a_dir_out_of_shape_is_refused_as_usage(self):
        """X8 · a relative, `-C`, `..`, `//`, trailing-`/` or `.` --dir, a repeated one, one after the verb, one with no
        value, one before --help: usage each, nothing staged — the path is held to its shape before anything runs."""
        (self.worktree / "f").write_text("x\n")
        w = str(self.worktree)
        for args in ([f"--dir", os.path.relpath(w, self.outside), "add", "f"], ["--dir", "-C", "add", "f"],
                     ["--dir", f"{w}/../{SLUG}", "add", "f"], ["--dir", w.replace("/repos/", "/repos//"), "add", "f"],
                     ["--dir", f"{w}/", "add", "f"], ["--dir", f"{w}/.", "add", "f"],
                     ["--dir", w, "--dir", w, "add", "f"], ["add", "--dir", w, "f"], ["where", "--dir", w],
                     ["--dir"], ["--dir", w, "--help"]):
            with self.subTest(args=args):
                self.refused("usage", *args, cwd=self.outside)
        self.assertEqual(self.staged(), [])

    def test_add__a_dir_naming_a_subdirectory_of_a_worktree_is_refused(self):
        """X9 · `--dir <worktree>/sub`: worktree-unlisted, nothing staged, as W4 — the check compares the whole path."""
        (self.worktree / "sub").mkdir()
        (self.worktree / "sub" / "f").write_text("x\n")

        self.refused_at("worktree-unlisted", self.worktree / "sub", "add", "f")

        self.assertEqual(self.staged(), [])

    def test_add__a_dir_naming_an_unlisted_repository_is_told_what_rw_git_serves(self):
        """X10 · `--dir <a repository repos does not list>`: worktree-unlisted with W7.1's text."""
        other = self.given_repo(self.root / "repos" / "other")
        (other / "f").write_text("x\n")

        err = self.refused_at("worktree-unlisted", other, "add", "f")

        self.assertIn(str(other), err)
        self.assertIn("`repos`", err)
        self.assertIn("`desktop_roots`", err)
        self.assertIn("granted folder", err)
        self.assertEqual(self.staged(other), [])

    def test_where__the_main_checkout_is_unmanaged_and_served(self):
        """X11 · `--dir <repo> where`: kind unmanaged, head main; `--dir <repo> add f` stages f there, as W2."""
        (self.repo / "f").write_text("x\n")

        out = self.ok_at(self.repo, "where")
        self.ok_at(self.repo, "add", "f")

        self.assertEqual(out.splitlines()[:2], [f"worktree: {self.repo}", f"repository: {self.repo}"])
        self.assertEqual(out.splitlines()[3:], ["kind: unmanaged", "head: main"])
        self.assertEqual(self.staged(self.repo), ["f"])

    def test_where__a_worktree_at_the_old_place_is_managed(self):
        """X12 · `--dir <repo>/.claude/worktrees/<slug> where`: kind managed <slug>, as W8."""
        legacy = self.given_worktree(self.repo, f".claude/worktrees/{OTHER_SLUG}", OTHER_BRANCH)

        out = self.ok_at(legacy, "where")

        self.assertIn(f"kind: managed {OTHER_SLUG}", out.splitlines())

    def test_where__a_dir_through_a_link_prints_the_canonical_worktree(self):
        """X13 · `--dir <a link to the worktree> where`: served, the worktree's canonical path printed, never the
        argument — the check is by canonical path, as for a working directory."""
        link = self.root / "shortcut"
        link.symlink_to(self.worktree)

        out = self.ok_at(link, "where")

        self.assertEqual(out.splitlines()[0], f"worktree: {self.worktree}")

    # -- switch --detach ---------------------------------------------------------------------------------------------

    def given_tip(self):
        """(base, the branch one commit past it, that commit editing README)."""
        base = self.head()
        return base, self.commit_in(self.worktree, "README", "branch\n", "branch edit")

    def test_switch__detach_puts_head_at_a_full_commit_id(self):
        """X14 · `--dir <worktree> switch --detach <base>`: HEAD detached at base, `where` says so, the branch stays at
        its tip."""
        base, tip = self.given_tip()

        self.ok_at(self.worktree, "switch", "--detach", base)

        self.assertEqual((self.branch(), self.head()), ("", base))
        self.assertEqual(self.ok_at(self.worktree, "where").splitlines()[4], f"head: detached {base}")
        self.assertEqual(self.git(self.worktree, "rev-parse", BRANCH), tip)

    def test_switch__an_own_branch_returns_from_a_detached_head(self):
        """X15 · from X14's detached HEAD, `--dir <worktree> switch <own branch>`: on it, at its tip."""
        base, tip = self.given_tip()
        self.git(self.worktree, "switch", "-q", "--detach", base)

        self.ok_at(self.worktree, "switch", BRANCH)

        self.assertEqual((self.branch(), self.head()), (BRANCH, tip))

    def test_switch__detach_takes_only_a_full_id_of_a_commit_here(self):
        """X16 · `switch --detach` with a short id, the id in upper case, 40 hex naming nothing, a tree's id:
        commit-unknown each, HEAD stays — a session's id never reaches git unchecked."""
        base, tip = self.given_tip()
        tree = self.git(self.worktree, "rev-parse", "HEAD^{tree}")

        for commit in (base[:7], base.upper(), "ab" * 20, tree):
            with self.subTest(commit=commit):
                self.refused_at("commit-unknown", self.worktree, "switch", "--detach", commit)
        self.assertEqual((self.branch(), self.head()), (BRANCH, tip))

    def test_switch__detach_takes_exactly_one_id(self):
        """X17 · `switch --detach` with no id, two ids, or `--force` before the id: usage each."""
        base, tip = self.given_tip()

        for rest in ([], [base, tip], ["--force", base]):
            with self.subTest(rest=rest):
                self.refused_at("usage", self.worktree, "switch", "--detach", *rest)
        self.assertEqual((self.branch(), self.head()), (BRANCH, tip))

    def test_switch__detach_over_a_local_change_git_would_overwrite_fails(self):
        """X18 · README edited, unstaged, and the base differs there: `switch --detach <base>` exits 1, the edit and
        HEAD stay — git refuses to lose a local change."""
        base, tip = self.given_tip()
        (self.worktree / "README").write_text("unsaved\n")

        code, _, err = self.rw("--dir", str(self.worktree), "switch", "--detach", base, cwd=self.outside)

        self.assertEqual(code, 1, err)
        self.assertEqual((self.worktree / "README").read_text(), "unsaved\n")
        self.assertEqual((self.branch(), self.head()), (BRANCH, tip))

    def test_commit__a_detached_head_is_refused_managed_and_unmanaged(self):
        """X19 · the managed worktree, then the main checkout, each detached at base by `switch --detach`, a file
        staged: `commit` is head-not-own, no new commit."""
        base, _ = self.given_tip()
        for where in (self.worktree, self.repo):
            with self.subTest(where=where.name):
                self.ok_at(where, "switch", "--detach", base)
                (where / "f").write_text("x\n")
                self.git(where, "add", "f")

                self.refused_at("head-not-own", where, "commit", "--message-file", str(self.given_message()))

                self.assertEqual(self.head(where), base)

    def test_switch__detach_in_an_unmanaged_checkout_with_a_rebase_stopped_is_refused(self):
        """X20 · the main checkout on feature, a conflicting rebase stopped: `switch --detach <base>` is head-not-own,
        the rebase still stopped — as plain switch, finish or abort first."""
        base = self.head(self.repo)
        self.git(self.repo, "switch", "-q", "-c", "feature")
        self.commit_in(self.repo, "README", "feature\n", "feature edit")
        self.git(self.repo, "switch", "-q", "main")
        moved = self.commit_in(self.repo, "README", "main\n", "main edit")
        self.git(self.repo, "switch", "-q", "feature")
        self.git(self.repo, "rebase", moved, check=False)

        self.refused_at("head-not-own", self.repo, "switch", "--detach", base)

        self.assertTrue((self.repo / ".git" / "rebase-merge").is_dir())

    def test_switch__detach_over_an_ignored_file_the_target_tracks_fails(self):
        """X22 · the base tracks notes.txt, the branch ignores it, the session has its own: `switch --detach <base>`
        exits 1, the file and HEAD stay — git's default would overwrite an ignored file silently."""
        base = self.commit_in(self.worktree, "notes.txt", "base\n", "track notes")
        self.git(self.worktree, "rm", "-q", "--cached", "notes.txt")
        (self.worktree / ".gitignore").write_text("notes.txt\n")
        self.git(self.worktree, "add", ".gitignore")
        self.git(self.worktree, "commit", "-q", "-m", "ignore notes")
        tip = self.head()
        (self.worktree / "notes.txt").write_text("mine\n")

        code, _, err = self.rw("--dir", str(self.worktree), "switch", "--detach", base, cwd=self.outside)

        self.assertEqual(code, 1, err)
        self.assertEqual((self.worktree / "notes.txt").read_text(), "mine\n")
        self.assertEqual((self.branch(), self.head()), (BRANCH, tip))

    def test_where__a_refusal_names_the_dir_as_spelled(self):
        """X23 · `--dir <a link to a plain folder> where`: worktree-unlisted naming the link, not its target — rw-git
        resolves the path outside the sandbox, so printing the target would tell a session where a link leads."""
        hidden = self.root / "hidden-target"
        hidden.mkdir()
        link = self.outside / "shortcut"
        link.symlink_to(hidden)

        err = self.refused_at("worktree-unlisted", link, "where")

        self.assertIn(f"'{link}'", err)
        self.assertNotIn(str(hidden), err)

    def test_where__a_dir_in_another_letter_case_is_refused(self):
        """X24 · the managed worktree and a desktop-root checkout, each spelled with one segment upper-cased: where and
        add are worktree-unlisted, nothing staged — served, the protected_branches key would not match it."""
        desk = self.root / "desk"
        repo = self.given_repo(desk / "notes-app")
        self.git(repo, "switch", "-q", "-c", "feature")
        self.given_launch_json({"repos": [str(self.repo)], "sessions_root": str(self.sessions),
                                "projects_root": str(self.projects), "desktop_roots": [str(desk)],
                                "protected_branches": {str(repo): ["feature"]}})
        for where, spelled in ((self.worktree, str(self.worktree).replace("/repos/", "/REPOS/")),
                               (repo, str(repo).replace("/notes-app", "/NOTES-APP"))):
            (where / "f").write_text("x\n")
            for args in (["where"], ["add", "f"]):
                with self.subTest(spelled=spelled, args=args):
                    self.refused("worktree-unlisted", "--dir", spelled, *args, cwd=self.outside)
            self.assertEqual(self.staged(where), [])

    def test_help__names_dir_where_and_switch_detach(self):
        """X21 · `rw-git --help`: names `--dir <path>`, `where` and `switch --detach` — the call shape a session learns."""
        out = self.ok("--help", cwd=self.outside)

        for words in ("rw-git --dir <path> <form>", "rw-git where", "rw-git switch --detach <commit>"):
            self.assertIn(words, out)


if __name__ == "__main__":
    unittest.main()
