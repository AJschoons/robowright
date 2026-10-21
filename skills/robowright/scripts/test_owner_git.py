#!/usr/bin/env python3
"""Tests for owner_git.py: which worktree an Owner-side tool may run git in, and how it runs it.

    python3 skills/robowright/scripts/test_owner_git.py

Every test builds scratch repositories and a scratch projects root named by
$ROBOWRIGHT_PROJECTS_ROOT, and drives owner_git.py through its command line with a `git` on PATH
that records its argv and then runs the real git. No test writes a hook, an fsmonitor or an
editor: what is asserted is the refusal, the exit code and the argv.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / "owner_git.py"
REAL_GIT = shutil.which("git")
GIT = [REAL_GIT, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]
HARDENING = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "log.showSignature=false"]
# The argv log's separators: one field per argument, one line per git call.
FIELD = "\x1f"
# Brackets json.loads cannot decode: past the recursion limit before Python 3.14, and past its C stack guard from 3.14.
DEEP_NESTING = 1_000_000
RECORDING_GIT = f"""#!/bin/sh
for a in "$@"; do printf '%s{FIELD}' "$a"; done >> "$GIT_ARGV_LOG"
printf '\\n' >> "$GIT_ARGV_LOG"
exec {REAL_GIT} "$@"
"""


def git_calls(log: Path) -> list:
    if not log.is_file():
        return []
    return [line.split(FIELD)[:-1] for line in log.read_text().splitlines()]


def runs_in(call: list, path: Path) -> bool:
    """A call that runs git inside `path`: `-C <path>` among its global options."""
    return any(call[i] == "-C" and os.path.realpath(call[i + 1]) == os.path.realpath(path) for i in range(len(call) - 1))


class OwnerGitCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        self.projects = self.root / "projects"
        self.repo = self.given_repo("repo")
        self.worktree = self.root / "worktrees" / "wt"
        self.git(self.repo, "worktree", "add", "-q", "-b", "robowright/sample-001-x", str(self.worktree))
        self.home = self.root / "home"
        self.given_configured(self.repo)
        self.given_allowlisted(self.repo)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").write_text(RECORDING_GIT)
        (bin_dir / "git").chmod(0o755)
        self.log = self.root / "git-argv.log"
        self.env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", GIT_ARGV_LOG=str(self.log),
                        ROBOWRIGHT_PROJECTS_ROOT=str(self.projects), HOME=str(self.home),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(self.root))

    def git(self, where, *args):
        done = subprocess.run(GIT + ["-C", str(where), *args], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def given_repo(self, name):
        repo = self.root / name
        repo.mkdir(parents=True)
        self.git(repo, "init", "-q", "-b", "main")
        self.git(repo, "commit", "-q", "--allow-empty", "-m", "base")
        return repo

    def given_configured(self, *repos, project="sample"):
        folder = self.projects / project
        folder.mkdir(parents=True, exist_ok=True)
        entries = [{"name": Path(r).name, "path": str(r), "origin": "git@example.invalid:sample.git"} for r in repos]
        (folder / "robowright.json").write_text(json.dumps({"project": project, "repos": entries}) + "\n")

    def given_allowlisted(self, *repos):
        """launch.json's `repos`: the repositories the Owner trusts."""
        self.given_launch_json(json.dumps({"schema": 1, "repos": [str(r) for r in repos]}) + "\n")

    def given_launch_json(self, text):
        path = self.home / ".claude" / "robowright" / "launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def check(self, path):
        done = subprocess.run([sys.executable, str(TOOL), "worktree", str(path)], capture_output=True, text=True, env=self.env)
        return done.returncode, done.stdout, done.stderr


class WorktreeCheckTests(OwnerGitCase):
    def test_check__a_worktree_no_configured_repository_lists_is_refused_before_git_runs_inside_it(self):
        """O1 · a checkout of a repository that no robowright.json names is refused worktree-unlisted, exit 2, naming the path — a session-chosen checkout's own config would run as the Owner."""
        other = self.given_repo("elsewhere")
        stray = self.root / "worktrees" / "stray"
        self.git(other, "worktree", "add", "-q", "-b", "stray", str(stray))

        code, out, err = self.check(stray)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)
        self.assertIn(str(stray), err)
        self.assertEqual(out, "")
        self.assertEqual([c for c in git_calls(self.log) if runs_in(c, stray)], [])

    def test_check__a_listed_worktree_is_accepted_and_names_the_configured_repository(self):
        """O2 · a linked worktree of a configured repository, given through a symlink, prints its canonical path then that repository — a compare of the spelling would refuse a real worktree, and the main clone must come from configuration."""
        alias = self.root / "alias"
        alias.symlink_to(self.worktree)

        code, out, err = self.check(alias)

        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [str(self.worktree), str(self.repo)])

    def test_check__a_listed_path_whose_git_file_names_another_repository_is_refused(self):
        """O3 · a listed worktree whose .git file points into another repository is refused worktree-foreign-gitdir — git would read that repository's config, and accept.sh would find its main clone there."""
        other = self.given_repo("elsewhere")
        (self.worktree / ".git").write_text(f"gitdir: {other / '.git'}\n")

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-foreign-gitdir: ", err)

    def test_check__a_repository_named_only_outside_the_projects_root_is_not_configured(self):
        """O4 · a robowright.json two levels down is not read — the configured set would grow with whatever a session writes under a project folder."""
        shutil.rmtree(self.projects)
        nested = self.projects / "sample" / "nested"
        nested.mkdir(parents=True)
        (nested / "robowright.json").write_text(json.dumps({"repos": [{"name": "repo", "path": str(self.repo)}]}))

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def test_check__control_bytes_in_the_refused_path_are_not_printed(self):
        """O5 · the refusal names the path with its C0, DEL and C1 control characters removed — an escape sequence in run.json.worktree would rewrite the Owner's terminal."""
        code, _, err = self.check(str(self.root / "a\x1b[2Jb\u009b2Jc"))

        self.assertEqual(code, 2, err)
        self.assertNotIn("\x1b", err)
        self.assertNotIn("\u009b", err)
        self.assertIn("a[2Jb2Jc", err)

    def test_check__a_robowright_json_in_the_sessions_root_is_not_configuration(self):
        """O8 · with the sessions root one level under the projects root, a robowright.json a session writes there names no configured repository — a session's own bare repository and its config would be trusted (review 1 F1)."""
        sessions = self.projects / "sessions"
        sessions.mkdir(parents=True)
        other = self.given_repo("session-made")
        stray = self.root / "worktrees" / "stray"
        self.git(other, "worktree", "add", "-q", "-b", "stray", str(stray))
        (sessions / "robowright.json").write_text(json.dumps({"repos": [{"name": "x", "path": str(other)}]}))
        self.given_allowlisted(self.repo, other)
        self.env["ROBOWRIGHT_SESSIONS_ROOT"] = str(sessions)

        code, _, err = self.check(stray)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def test_check__a_repository_inside_the_sessions_root_is_not_configured(self):
        """O9 · a configured path that lies under the sessions root is dropped, even one launch.json's `repos` lists — a session can write anything there, a repository's config included (review 1 F1)."""
        sessions = self.root / "sessions"
        sessions.mkdir()
        inside = sessions / "sample-001-x" / "repo"
        inside.parent.mkdir()
        shutil.move(str(self.repo), str(inside))
        self.git(inside, "worktree", "repair", str(self.worktree))
        self.given_configured(inside)
        self.given_allowlisted(inside)
        self.env["ROBOWRIGHT_SESSIONS_ROOT"] = str(sessions)

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def test_check__a_git_file_naming_a_session_made_gitdir_that_shares_the_common_dir_is_refused(self):
        """O10 · a .git file pointing at a git dir outside the repository's worktrees/, whose commondir names the real repository, is refused worktree-foreign-gitdir — git would read that git dir's config.worktree (review 1 F2)."""
        made = self.root / "made-gitdir"
        made.mkdir()
        admin = Path(self.git(self.worktree, "rev-parse", "--absolute-git-dir"))
        for name in ("HEAD", "commondir"):
            (made / name).write_text((admin / name).read_text() if name == "HEAD" else str(self.repo / ".git") + "\n")
        (made / "gitdir").write_text(str(self.worktree / ".git") + "\n")
        shutil.copy(admin / "index", made / "index")
        (self.worktree / ".git").write_text(f"gitdir: {made}\n")

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-foreign-gitdir: ", err)


class SiblingGitDirTests(OwnerGitCase):
    def test_check__a_git_file_naming_another_worktree_s_entry_in_the_same_repository_is_refused(self):
        """O12 · a listed worktree whose .git names a sibling worktree's entry in the same repository is refused worktree-foreign-gitdir — git would use that entry's HEAD, index and config.worktree for this path."""
        sibling = self.root / "worktrees" / "sibling"
        self.git(self.repo, "worktree", "add", "-q", "-b", "sibling", str(sibling))
        (self.worktree / ".git").write_text((sibling / ".git").read_text())

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-foreign-gitdir: ", err)


class RobustnessTests(OwnerGitCase):
    def test_check__an_undecodable_byte_in_another_worktree_s_entry_does_not_stop_the_check(self):
        """O13 · a byte that is not UTF-8 in another worktree's `gitdir` file leaves this worktree accepted — one session's admin file would crash every accept, launch and render (review 2 F8)."""
        other = self.root / "worktrees" / "other"
        self.git(self.repo, "worktree", "add", "-q", "-b", "other", str(other))
        (self.repo / ".git" / "worktrees" / "other" / "gitdir").write_bytes(b"/tmp/\xff\xfe/.git\n")

        code, out, err = self.check(self.worktree)

        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [str(self.worktree), str(self.repo)])

    def test_check__an_undecodable_byte_in_this_worktree_s_own_entry_does_not_stop_the_check(self):
        """O17 · a byte that is not UTF-8 in this worktree's own `gitdir` file, whose path still resolves to the worktree, is read as a path and accepted — the check would crash every render that reaches it (review 3 F8)."""
        (self.root / "a").mkdir()
        entry = self.repo / ".git" / "worktrees" / "wt" / "gitdir"
        entry.write_bytes(os.fsencode(self.root / "a") + b"/\xff/../../worktrees/wt/.git\n")

        code, out, err = self.check(self.worktree)

        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [str(self.worktree), str(self.repo)])

    def test_check__a_nul_byte_in_this_worktree_s_own_entry_is_refused_not_raised(self):
        """O19 · a NUL in this worktree's own `gitdir` file, after a path git still lists as the worktree, is refused worktree-foreign-gitdir — git reads the file up to the NUL, Python's path calls raise on it, and the raise would crash every render (review 4 F14)."""
        entry = self.repo / ".git" / "worktrees" / "wt" / "gitdir"
        entry.write_bytes(os.fsencode(self.worktree) + b"\0/x/.git\n")

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-foreign-gitdir: ", err)

    def test_check__a_worktree_value_holding_a_nul_is_refused_not_raised(self):
        """O20 · `check` given a run.json.worktree that holds a NUL raises Unlisted worktree-unlisted, not ValueError — the dashboard catches only Unlisted, and reaches `check` without first asking whether the path is a directory (review 4)."""
        probe = ("import importlib.util, sys; spec = importlib.util.spec_from_file_location('owner_git', sys.argv[1]); "
                 "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                 "try:\n    m.check(sys.argv[2] + '\\0x')\nexcept m.Unlisted as refusal:\n    print(refusal.code)")

        done = subprocess.run([sys.executable, "-c", probe, str(TOOL), str(self.worktree)], capture_output=True, text=True, env=self.env)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "worktree-unlisted")

    def in_process(self, body, *args, timeout=30):
        """Runs `body` with `m` bound to owner_git, in a fresh interpreter; returns (exit code, stdout, stderr)."""
        probe = ("import importlib.util, sys; spec = importlib.util.spec_from_file_location('owner_git', sys.argv[1]); "
                 "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n" + body)
        done = subprocess.run([sys.executable, "-c", probe, str(TOOL), *map(str, args)], capture_output=True, text=True,
                              env=self.env, timeout=timeout)
        return done.returncode, done.stdout, done.stderr

    def test_check__a_sibling_entry_naming_a_long_symlink_chain_leaves_this_worktree_accepted(self):
        """O21 · on a Python whose realpath recurses per link (3.12 and older), another worktree's `gitdir` naming a 1200-link chain leaves this worktree accepted — the RecursionError would escape `index` and stop every session's check (review 5 F16)."""
        old = "/usr/bin/python3"
        probe = subprocess.run([old, "-c", "import sys; print(sys.version_info >= (3, 13))"], capture_output=True, text=True) \
            if os.path.exists(old) else None
        if probe is None or probe.stdout.strip() != "False":
            self.skipTest("no python3 older than 3.13 at /usr/bin/python3")
        other = self.root / "worktrees" / "other"
        self.git(self.repo, "worktree", "add", "-q", "-b", "other", str(other))
        links = self.root / "chain"
        links.mkdir()
        for i in range(1200):
            os.symlink(links / f"l{i + 1}", links / f"l{i}")
        (self.repo / ".git" / "worktrees" / "other" / "gitdir").write_bytes(os.fsencode(links / "l0") + b"/.git\n")

        done = subprocess.run([old, str(TOOL), "worktree", str(self.worktree)], capture_output=True, text=True, env=self.env)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines(), [str(self.worktree), str(self.repo)])

    def test_check__an_entry_that_turned_into_a_fifo_after_the_listing_is_refused_without_blocking(self):
        """O22 · a worktree's own `gitdir` replaced by a FIFO after the listing was taken is refused worktree-foreign-gitdir at once — a blocking read would hang the single-threaded dashboard for everyone (review 5 F17)."""
        code, out, err = self.in_process(
            "import os\nlisted = m.index()\nos.unlink(sys.argv[3]); os.mkfifo(sys.argv[3])\n"
            "try:\n    m.check(sys.argv[2], listed)\nexcept m.Unlisted as refusal:\n    print(refusal.code)",
            self.worktree, self.repo / ".git" / "worktrees" / "wt" / "gitdir", timeout=10)

        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "worktree-foreign-gitdir")

    def test_check__an_entry_that_is_a_symlink_is_refused_even_when_its_target_names_the_worktree(self):
        """O23 · a worktree's own `gitdir` that is a symlink is refused worktree-foreign-gitdir, though the file it points at names the worktree — following it would let a session point the read at /dev/zero or a FIFO (review 5 F17)."""
        entry = self.repo / ".git" / "worktrees" / "wt" / "gitdir"
        target = self.root / "named-elsewhere"
        target.write_bytes(entry.read_bytes())
        entry.unlink()
        entry.symlink_to(target)

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-foreign-gitdir: ", err)

    def test_check__an_entry_longer_than_a_path_is_refused_even_when_it_names_the_worktree(self):
        """O24 · a worktree's own `gitdir` longer than 4096 bytes is refused worktree-foreign-gitdir, though it names the worktree once trailing space is stripped — reading a session-written file without a bound reads as much as the session wrote (review 5 F17)."""
        entry = self.repo / ".git" / "worktrees" / "wt" / "gitdir"
        entry.write_bytes(os.fsencode(self.worktree / ".git") + b"\n" + b" " * 8192)

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-foreign-gitdir: ", err)

    def test_check__a_worktree_path_outside_ascii_is_accepted_under_a_latin_1_locale(self):
        """O18 · a listed worktree whose path holds a character outside ASCII is accepted when the locale is Latin-1 — reading its `gitdir` file in the locale's encoding would name a different path (review 3 F13)."""
        worktree = self.root / "worktrees" / "café"
        self.git(self.repo, "worktree", "add", "-q", "-b", "cafe", str(worktree))
        self.env.update(LC_ALL="en_US.ISO8859-1", LANG="en_US.ISO8859-1", PYTHONUTF8="0", PYTHONIOENCODING="")

        done = subprocess.run([sys.executable, str(TOOL), "worktree", os.fsencode(worktree)], capture_output=True, env=self.env)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines(), [os.fsencode(worktree), os.fsencode(self.repo)])

    def test_check__the_sessions_root_is_excluded_whatever_case_it_is_spelled_in(self):
        """O14 · on a case-insensitive volume, a sessions root named in other letter case still excludes its robowright.json — a case slip in launch.json would trust a session's file again (review 2 F10)."""
        sessions = self.projects / "sessions"
        sessions.mkdir(parents=True)
        if not (self.projects / "SESSIONS").exists():
            self.skipTest("this volume is case-sensitive")
        other = self.given_repo("session-made")
        stray = self.root / "worktrees" / "stray"
        self.git(other, "worktree", "add", "-q", "-b", "stray", str(stray))
        (sessions / "robowright.json").write_text(json.dumps({"repos": [{"name": "x", "path": str(other)}]}))
        self.given_allowlisted(self.repo, other)
        self.env["ROBOWRIGHT_SESSIONS_ROOT"] = str(self.projects / "SESSIONS")

        code, _, err = self.check(stray)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def test_configured_repos__a_sessions_root_the_caller_names_is_excluded_too(self):
        """O15 · `configured_repos(root, sessions)` skips the sessions root the caller passes, even one neither the environment nor launch.json names — the dashboard's --runs-root would trust a session's robowright.json (review 2 F1)."""
        sessions = self.projects / "flag-sessions"
        sessions.mkdir(parents=True)
        other = self.given_repo("session-made")
        (sessions / "robowright.json").write_text(json.dumps({"repos": [{"name": "x", "path": str(other)}]}))
        self.given_allowlisted(self.repo, other)
        probe = ("import importlib.util, json, sys; spec = importlib.util.spec_from_file_location('owner_git', sys.argv[1]); "
                 "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                 "print(json.dumps(m.configured_repos(sys.argv[2], sessions=sys.argv[3])))")

        done = subprocess.run([sys.executable, "-c", probe, str(TOOL), str(self.projects), str(sessions)],
                              capture_output=True, text=True, env=self.env)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), [str(self.repo)])


class AllowlistTests(OwnerGitCase):
    """O25–O35 · a repository is trusted only when launch.json's `repos` lists it and a project's robowright.json names it."""

    def given_planted(self, name="planted", folder="newfolder"):
        """A repository the session made, its worktree, and a new project folder whose robowright.json names it (N-1)."""
        planted = self.given_repo(name)
        worktree = self.root / "worktrees" / f"{name}-wt"
        self.git(planted, "worktree", "add", "-q", "-b", f"{name}-branch", str(worktree))
        self.given_configured(planted, project=folder)
        return planted, worktree

    def test_check__a_repository_named_but_not_in_launch_json_repos_is_refused_naming_the_key(self):
        """O25 · a robowright.json naming a repository launch.json's `repos` does not list is refused worktree-unlisted, no git runs in it, and the refusal names `repos`, launch.json and the `"repos": [...]` line that would add the repository — a session's own robowright.json would trust its own repository (N-1)."""
        planted, worktree = self.given_planted()

        code, out, err = self.check(worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)
        self.assertIn("`repos`", err)
        self.assertIn(str(self.home / ".claude/robowright/launch.json"), err)
        self.assertIn(f'"repos": {json.dumps([str(self.repo), str(planted)])}', err)
        self.assertEqual(out, "")
        self.assertEqual([c for c in git_calls(self.log) if runs_in(c, planted) or runs_in(c, worktree)], [])

    def test_check__a_repository_in_repos_that_no_robowright_json_names_is_refused(self):
        """O26 · a repository launch.json's `repos` lists but no project's robowright.json names is refused worktree-unlisted — `repos` would widen the set on its own, past what any project uses."""
        other = self.given_repo("listed-only")
        worktree = self.root / "worktrees" / "listed-only-wt"
        self.git(other, "worktree", "add", "-q", "-b", "listed-only", str(worktree))
        self.given_allowlisted(self.repo, other)

        code, _, err = self.check(worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def test_check__no_repos_key_trusts_nothing_and_prints_the_line_to_add(self):
        """O27 · a launch.json with no `repos` trusts no repository: a named worktree is refused repos-unconfigured, no git runs in it, and the refusal names the key, the file and a `"repos": [...]` line holding the named repository — failing open would leave N-1 on every install that never adds the key."""
        self.given_launch_json(json.dumps({"schema": 1}) + "\n")

        code, out, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: repos-unconfigured: ", err)
        self.assertIn(str(self.home / ".claude/robowright/launch.json"), err)
        self.assertIn(f'"repos": [{json.dumps(str(self.repo))}]', err)
        self.assertEqual(out, "")
        self.assertEqual([c for c in git_calls(self.log) if runs_in(c, self.worktree)], [])

    def test_check__no_launch_json_trusts_nothing(self):
        """O28 · with no launch.json at all, a named worktree is refused repos-unconfigured — a missing file read as "no allowlist, trust robowright.json" fails open."""
        (self.home / ".claude/robowright/launch.json").unlink()

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: repos-unconfigured: ", err)

    def test_check__a_launch_json_that_is_not_json_trusts_nothing(self):
        """O29 · a launch.json that does not parse is refused repos-unconfigured naming the file — a half-written file would fail open, or raise."""
        self.given_launch_json('{"repos": [' + json.dumps(str(self.repo)) + ',\n')

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: repos-unconfigured: ", err)
        self.assertNotIn("Traceback", err)

    def test_check__repos_of_the_wrong_type_trusts_nothing(self):
        """O30 · `repos` as a string, an object, null or a launch.json that is a list is refused repos-unconfigured — a string would be iterated as characters, an object as its keys."""
        for text in (json.dumps({"repos": str(self.repo)}), json.dumps({"repos": {str(self.repo): True}}),
                     json.dumps({"repos": None}), json.dumps([str(self.repo)])):
            with self.subTest(text=text):
                self.given_launch_json(text + "\n")

                code, _, err = self.check(self.worktree)

                self.assertEqual(code, 2, err)
                self.assertIn("refused: repos-unconfigured: ", err)

    def test_check__one_wrong_shaped_entry_drops_the_whole_list(self):
        """O31 · one entry that is not an absolute or `~/` path — relative, a bare `~`, empty, a number, an object, or holding a control byte — refuses the whole list repos-unconfigured, naming the entry — a relative entry resolves against whatever directory the Owner's tool runs in."""
        for bad in ("repo", "~", "", 7, {"path": str(self.repo)}, str(self.repo) + "\n", "./" + self.repo.name):
            with self.subTest(bad=bad):
                self.given_launch_json(json.dumps({"repos": [str(self.repo), bad]}) + "\n")

                code, _, err = self.check(self.worktree)

                self.assertEqual(code, 2, err)
                self.assertIn("refused: repos-unconfigured: ", err)
                self.assertIn("entry 2", err)

    def test_check__a_tilde_entry_is_home(self):
        """O32 · a `repos` entry `~/x` is $HOME/x, as the launcher reads a configured path — the documented form would trust nothing."""
        moved = self.home / "Code" / "repo"
        moved.parent.mkdir(parents=True)
        shutil.move(str(self.repo), str(moved))
        self.git(moved, "worktree", "repair", str(self.worktree))
        self.given_configured(moved)
        self.given_allowlisted("~/Code/repo")

        code, out, err = self.check(self.worktree)

        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [str(self.worktree), str(moved)])

    def test_check__an_entry_with_a_trailing_slash_or_other_letter_case_is_the_same_repository(self):
        """O33 · a `repos` entry with a trailing slash, or, on a case-insensitive volume, robowright.json spelling the path in other letter case, still trusts that repository and prints launch.json's spelling — a string compare would refuse the Owner's own repository."""
        self.given_allowlisted(str(self.repo) + "/")
        code, out, err = self.check(self.worktree)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [str(self.worktree), str(self.repo)])

        upper = self.repo.parent / self.repo.name.upper()
        if not upper.exists():
            self.skipTest("this volume is case-sensitive")
        self.given_configured(upper)
        self.given_allowlisted(self.repo)
        code, out, err = self.check(self.worktree)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [str(self.worktree), str(self.repo)])

    def test_check__a_planted_repository_in_another_letter_case_is_refused_on_a_case_sensitive_volume(self):
        """O34 · where letter case makes another directory, a planted repository whose path differs from an allowlisted one only in case is refused — trust would follow the spelling, not the directory."""
        if (self.repo.parent / self.repo.name.upper()).exists():
            self.skipTest("this volume is case-insensitive")
        planted, worktree = self.given_planted(name=self.repo.name.upper())

        code, _, err = self.check(worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def test_check__a_robowright_json_naming_a_link_trusts_only_what_repos_lists(self):
        """O35 · robowright.json naming a link is the link's target: a link to the allowlisted repository is that repository, and a link a session points at its own repository is refused — trust would follow the name robowright.json wrote."""
        link = self.root / "link-to-repo"
        link.symlink_to(self.repo)
        self.given_configured(link)
        code, out, err = self.check(self.worktree)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [str(self.worktree), str(self.repo)])

        planted, worktree = self.given_planted()
        link.unlink()
        link.symlink_to(planted)
        self.given_configured(link, project="newfolder")
        code, _, err = self.check(worktree)
        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def given_deeply_nested(self, project, repos=()):
        """`project`'s robowright.json: an object naming `repos`, and one key nested past the parser's recursion limit."""
        folder = self.projects / project
        folder.mkdir(parents=True, exist_ok=True)
        entries = json.dumps([{"path": str(r)} for r in repos])
        (folder / "robowright.json").write_text(f'{{"repos": {entries}, "deep": {"[" * DEEP_NESTING}{"]" * DEEP_NESTING}}}\n')

    def test_check__a_robowright_json_nested_too_deeply_is_skipped__and_the_listed_worktree_is_accepted(self):
        """O36 · another project's robowright.json nested too deeply for json.loads is skipped as an unreadable one is: the listed worktree is accepted, with no traceback — the RecursionError crashed accept.sh, the launcher and the dashboard (U36 review 2, G2)."""
        self.given_deeply_nested("hostile")

        code, out, err = self.check(self.worktree)

        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out.splitlines(), [str(self.worktree), str(self.repo)])

    def test_check__a_repository_named_only_by_a_robowright_json_nested_too_deeply_is_refused(self):
        """O37 · a skipped robowright.json trusts nothing: when the only one naming the allowlisted repository nests too deeply for json.loads, its worktree is refused worktree-unlisted, with no traceback (U36 review 2, G2, "fail closed")."""
        self.given_deeply_nested("sample", repos=[self.repo])

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertNotIn("Traceback", err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def test_check__a_robowright_json_that_is_a_link_trusts_nothing(self):
        """O38 · when the only robowright.json naming the allowlisted repository is a symlink to a file outside the
        projects root, it is skipped: the worktree is refused worktree-unlisted (U52b B3, S6-5)."""
        outside = self.root / "outside"
        outside.mkdir()
        settings = self.projects / "sample" / "robowright.json"
        settings.rename(outside / "kept.json")
        settings.symlink_to(outside / "kept.json")

        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)

    def test_check__a_robowright_json_that_is_a_fifo_is_skipped_at_once(self):
        """O39 · another project's robowright.json a FIFO is skipped within seconds, and the listed worktree is
        accepted: the read waited on it for a writer that never comes (U52b B3, S6-5)."""
        (self.projects / "hostile").mkdir()
        os.mkfifo(self.projects / "hostile" / "robowright.json")

        done = subprocess.run([sys.executable, str(TOOL), "worktree", str(self.worktree)], capture_output=True,
                              text=True, env=self.env, timeout=10)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines(), [str(self.worktree), str(self.repo)])


class ShowTests(OwnerGitCase):
    def test_show__writes_utf_8_whatever_the_locale_says(self):
        """O16 · under a Latin-1 output encoding, `show` still exits 0 and writes the text as UTF-8 — accept.sh would lose its refusal lines and message preview and integrate anyway (review 2 F9)."""
        env = dict(self.env, PYTHONIOENCODING="latin-1", LC_ALL="C")
        done = subprocess.run([sys.executable, str(TOOL), "show"], input="naïve \u2014 \u009bx\n".encode("utf-8"),
                              capture_output=True, env=env)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.decode("utf-8"), "naïve \u2014 x\n")

    def test_show__drops_c0_del_and_c1_controls_and_keeps_tab_newline_and_text(self):
        """O11 · `show` passes text through with tab, newline and non-ASCII letters kept and every C0, DEL and C1 control dropped — accept.sh prints session-written text through it, and U+009B is a CSI to many terminals (review 1 F5)."""
        done = subprocess.run([sys.executable, str(TOOL), "show"], input="a\tb\x1b[2J\x07é\u009b2J\x7f\nnext\n",
                              capture_output=True, text=True, env=self.env)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "a\tb[2Jé2J\nnext\n")


class HardenedArgvTests(OwnerGitCase):
    def test_flags__prints_the_global_options_that_turn_off_configured_programs(self):
        """O6 · `flags <repo>` prints the fsmonitor, hooksPath, pager and showSignature overrides one per line, then
        `--env` and the variable its --config-env options name — the shell callers build their git argv from it."""
        done = subprocess.run([sys.executable, str(TOOL), "flags", str(self.repo)], capture_output=True, text=True,
                              env=self.env)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines(), HARDENING + ["--env", "OWNER_GIT_FALSE=false"])

    def given_config_hooks(self, event):
        """`hook.<name>` for a plain name, one holding `=`, and the empty name `[hook ""]`, on `event`, each a program
        touching a marker."""
        markers = self.root / "markers"
        markers.mkdir(exist_ok=True)
        for name in ("probe", "a=b", ""):
            program = self.root / f"hook-{name or 'empty'}"
            program.write_text(f"#!/bin/sh\ntouch '{markers / (name or 'empty')}'\n")
            program.chmod(0o755)
            with open(self.repo / ".git" / "config", "a") as config:
                config.write(f'[hook "{name}"]\n\tevent = {event}\n\tcommand = {program}\n')
        return markers

    def test_flags__turns_off_each_config_hook_by_name(self):
        """O40 · with config hooks `probe` and `a=b` in the repository, `flags <repo>` adds one
        `--config-env=hook.<name>.enabled=OWNER_GIT_FALSE` for each — core.hooksPath=/dev/null leaves them running
        (git 2.54), and `-c hook.a=b.enabled=false` splits at the first `=` (U52b C3, S6-2)."""
        self.given_config_hooks("post-checkout")

        done = subprocess.run([sys.executable, str(TOOL), "flags", str(self.repo)], capture_output=True, text=True,
                              env=self.env)

        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(sorted(lines[len(HARDENING):lines.index("--env")]),
                         ["--config-env=hook..enabled=OWNER_GIT_FALSE", "--config-env=hook.a=b.enabled=OWNER_GIT_FALSE",
                          "--config-env=hook.probe.enabled=OWNER_GIT_FALSE"])

    def test_flags__a_hook_name_that_is_not_utf_8_is_printed_as_its_bytes(self):
        """O42 · a config hook named `x<0xff>y`: `flags <repo>` exits 0 and prints its off switch byte for byte — a
        traceback stops every accept and launch, and a replaced byte names another hook (gate F3)."""
        with open(self.repo / ".git" / "config", "ab") as config:
            config.write(b'[hook "x\xffy"]\n\tevent = post-checkout\n\tcommand = true\n')

        done = subprocess.run([sys.executable, str(TOOL), "flags", str(self.repo)], capture_output=True, env=self.env)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(b"--config-env=hook.x\xffy.enabled=OWNER_GIT_FALSE\n", done.stdout)

    def test_run__a_worktree_add_runs_no_config_hook(self):
        """O41 · `owner_git.run(repo, "worktree", "add", …)`, as the launcher's role_grants makes a worktree, with
        post-checkout config hooks `probe` and `a=b`: the worktree is made and no marker exists (U52b C4, S6-2)."""
        markers = self.given_config_hooks("post-checkout")
        sys.path.insert(0, str(HERE))
        import owner_git

        done = owner_git.run(self.repo, "worktree", "add", "-q", "--detach", str(self.root / "worktrees" / "made"), "HEAD")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.root / "worktrees" / "made" / ".git").is_file())
        self.assertEqual(sorted(p.name for p in markers.iterdir()), [])

    def test_check__every_git_call_carries_the_overrides_ahead_of_its_directory(self):
        """O7 · each git the check runs, in the configured repository and in the worktree, starts with the overrides — a call without them runs the repository's configured fsmonitor or hooks."""
        code, _, err = self.check(self.worktree)

        self.assertEqual(code, 0, err)
        calls = git_calls(self.log)
        self.assertTrue(any(runs_in(c, self.worktree) for c in calls), calls)
        self.assertTrue(any(runs_in(c, self.repo) for c in calls), calls)
        for call in calls:
            self.assertEqual(call[:len(HARDENING)], HARDENING, call)


class WorktreeListingFailsTests(OwnerGitCase):
    """052a-G rows: `git worktree list` fails in the configured repository while every other git call runs. accept.sh
    reads the listing only through `branch`, so `branch` refuses; every other reader keeps reading no worktree."""

    def setUp(self):
        super().setUp()
        failing = self.root / "bin" / "git"
        failing.write_text("""#!/bin/sh
prev=
for a in "$@"; do [ "$prev $a" = "worktree list" ] && exit 128; prev=$a; done
""" + "\n".join(RECORDING_GIT.splitlines()[1:]) + "\n")

    def test_branch__refused_branch_missing_when_git_cannot_list_the_worktrees(self):
        """052a-G1 · `branch` refuses branch-missing, exit 2, naming the repository — accept.sh would read no worktree and skip its worktree-dirty check."""
        done = subprocess.run([sys.executable, str(TOOL), "branch", "robowright/sample-001-x"], capture_output=True, text=True, env=self.env)

        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn(f"refused: branch-missing: git cannot list the worktrees of {self.repo}", done.stderr)

    def test_index_and_branch_index__read_empty_when_git_cannot_list_the_worktrees(self):
        """052a-G2 · index() and branch_index() read {} — the dashboard builds its page from both, and an exception there fails every page."""
        script = "import json, owner_git; print(json.dumps([owner_git.index(), owner_git.branch_index()]))"
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=self.env, cwd=str(HERE))

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), [{}, {}])

    def test_worktree__refused_worktree_unlisted_when_git_cannot_list_the_worktrees(self):
        """052a-G3 · `worktree` still refuses worktree-unlisted, exit 2 — rw-git, the launcher and accept.sh's worktree check refuse by check's name, not a traceback."""
        code, out, err = self.check(self.worktree)

        self.assertEqual(code, 2, err)
        self.assertIn("refused: worktree-unlisted: ", err)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
