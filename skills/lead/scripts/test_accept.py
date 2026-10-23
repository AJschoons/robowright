#!/usr/bin/env python3
"""Tests for accept.sh: the Owner's squash of a finished Robowright Session onto the main clone.

    python3 skills/lead/scripts/test_accept.py

Every test builds a synthetic repository under a scratch dir: a main clone on `main`, a worktree
on a session branch two commits ahead, a scratch projects root whose robowright.json names the
main clone, and a session dir whose run.json is baselined through session-state.py's `adopt`, so
the `accept` event meets a legal, logged session. accept.sh runs as a subprocess with HOME and git's
global config pointed at scratch, and with a `git` on PATH that records its argv and then runs
the real git. No test writes a hook, an fsmonitor or an editor. Never the real main clone.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACCEPT = HERE / "accept.sh"
SESSION_STATE = HERE.parent.parent / "robowright" / "scripts" / "session-state.py"
BRANCH = "robowright/sample-001-notes"
# accept()'s and direct()'s default: --tip names the branch's tip at the call.
TIP_NOW = object()
# A full commit id that names no commit in any fixture repository.
NO_COMMIT = "0" * 40
FIRST_SUBJECT = "notes: store a note's title"
SECOND_SUBJECT = "notes: show the title in the list"
EDITED = "notes: a note has a title\n\nsquashed from the sample-001 session\n"
PREPARED = "notes: a prepared title message\n\nwritten to a file before the accept\n# a note to self\n"
GIT_DEFAULT = "Squashed commit of the following:\n\ncommit 0123456789abcdef\n"
# A file the Owner can read that is no squash message: its text must never be printed or committed.
OUTSIDE_TEXT = "STAND-IN-TEXT-OUTSIDE (not a message)\n"
REAL_GIT = shutil.which("git")
# The accept line's portable spelling, which accept-in-target names.
INSTALLED = "~/.claude/skills/lead/scripts/accept.sh"
HARDENING = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "log.showSignature=false"]
FIELD = "\x1f"
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


def subcommand(call: list) -> str:
    """The git subcommand: the first argument after the global options and their values."""
    i = 0
    while i < len(call) and call[i].startswith("-"):
        i += 2 if call[i] in ("-c", "-C") else 1
    return call[i] if i < len(call) else ""


class AcceptCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Resolved: macOS's temp dir is a link, and accept.sh prints canonical paths.
        root = Path(os.path.realpath(self.tmp.name))
        self.root = root
        self.home = root / "home"
        self.home.mkdir()
        self.main = root / "sample"
        self.worktree = root / "sample-wt"
        self.projects = root / "projects"
        self.dir = root / "sessions" / "sample-001-notes"
        self.unit_folder = self.dir / "prs" / "U1"
        self.unit_folder.mkdir(parents=True)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").write_text(RECORDING_GIT)
        (bin_dir / "git").chmod(0o755)
        self.path = f"{bin_dir}:{os.environ['PATH']}"
        self.log = root / "git-argv.log"
        self.given_repository()
        self.given_configured(self.main)
        self.given_allowlisted(self.main)
        self.given_session(phase="done")
        (self.dir / "INTAKE.md").write_text("# Intake\n")

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------ given

    def env(self):
        # An editor path that names no file: an accept that still asked git for one fails instead of waiting on a terminal.
        env = {k: v for k, v in os.environ.items() if k not in ("VISUAL", "EDITOR")}
        env.update(GIT_EDITOR="/nonexistent/editor", HOME=str(self.home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                   ROBOWRIGHT_PROJECTS_ROOT=str(self.projects), GIT_CEILING_DIRECTORIES=str(self.root))
        return env

    def accept_env(self):
        return dict(self.env(), PATH=self.path, GIT_ARGV_LOG=str(self.log))

    def git(self, where, *args):
        done = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True, env=self.env())
        self.assertEqual(done.returncode, 0, f"git {args}: {done.stderr}")
        return done.stdout.strip()

    def commit(self, where, name, subject):
        (Path(where) / name).write_text(f"{subject}\n")
        self.git(where, "add", name)
        self.git(where, "commit", "-q", "-m", subject)

    def given_repository(self):
        self.main.mkdir()
        self.git(self.main, "init", "-q", "-b", "main")
        self.git(self.main, "config", "user.name", "Sample Owner")
        self.git(self.main, "config", "user.email", "owner@example.invalid")
        self.commit(self.main, "README.md", "readme: the sample app")
        self.git(self.main, "worktree", "add", "-q", "-b", BRANCH, str(self.worktree), "main")
        self.commit(self.worktree, "title.txt", FIRST_SUBJECT)
        self.commit(self.worktree, "list.txt", SECOND_SUBJECT)

    def given_configured(self, *repos):
        folder = self.projects / "sample"
        folder.mkdir(parents=True, exist_ok=True)
        entries = [{"name": Path(r).name, "path": str(r), "origin": "git@example.invalid:sample.git"} for r in repos]
        (folder / "robowright.json").write_text(json.dumps({"project": "sample", "repos": entries}) + "\n")

    def given_allowlisted(self, *repos):
        """launch.json's `repos`: the repositories the Owner trusts."""
        self.given_launch_json({"schema": 1, "repos": [str(r) for r in repos]})

    def given_launch_json(self, settings):
        path = self.home / ".claude" / "robowright" / "launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings) + "\n")

    def given_session(self, phase, worktree=None):
        run = {
            "ticket": "sample-001-notes",
            "worktree": str(worktree or self.worktree),
            "phase": phase,
            "delegation": "planner",
            "rotate": None,
            "rebriefs": [],
            "stop_reason": None,
            "units": [{"id": "U1", "status": "done", "head": self.git(self.worktree, "rev-parse", "HEAD"), "gate_attempts": 1}],
        }
        (self.dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        done = subprocess.run([sys.executable, str(SESSION_STATE), str(self.dir), "adopt", "--by", "owner", "--reason", "fixture"],
                              capture_output=True, text=True, env=self.env())
        self.assertEqual(done.returncode, 0, done.stderr)

    # ------------------------------------------------------------ when / then

    def accept(self, *options, message=EDITED, cwd=None, tip=TIP_NOW):
        """accept.sh with `options`, `--message` naming a file holding `message` unless `message` is None, and `--tip`
        naming the session branch's tip now (or `tip`; none when None), run from `cwd` (the scratch root unless given)."""
        if tip is not None:
            options = ("--tip", self.branch_tip() if tip is TIP_NOW else tip, *options)
        if message is not None:
            options = ("--message", str(self.message_file(message)), *options)
        done = subprocess.run(["bash", str(ACCEPT), *options, str(self.dir)], capture_output=True, text=True,
                              env=self.accept_env(), cwd=cwd or self.tmp.name)
        return done.returncode, done.stdout, done.stderr

    def branch_tip(self):
        """The session branch's tip in the main clone, or a full id naming no commit when the branch is gone."""
        done = subprocess.run(["git", "-C", str(self.main), "rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}"],
                              capture_output=True, text=True, env=self.env())
        return done.stdout.strip() or NO_COMMIT

    def message_path(self):
        """Where the hook puts the squash message: the unit's folder under the session's prs/."""
        return self.unit_folder / "commit-message.txt"

    def message_file(self, text):
        path = self.message_path()
        path.write_text(text)
        return path

    def given_unwritable_tmpdir(self):
        scratch = self.root / "scratch-tmp"
        scratch.mkdir()
        scratch.chmod(0o500)
        return scratch

    def given_accept_scripts_in_the_main_clone(self):
        """accept.sh, owner_git.py and session_write.py committed in the main clone, as in this repository, and the
        branch rebased onto them; returns the clone's own accept.sh."""
        for script in (ACCEPT, HERE.parent.parent / "robowright" / "scripts" / "owner_git.py",
                       HERE.parent.parent / "robowright" / "scripts" / "session_write.py"):
            copy = self.main / script.relative_to(HERE.parent.parent.parent)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(script, copy)
        (self.main / ".gitignore").write_text("__pycache__/\n")
        self.git(self.main, "add", "skills", ".gitignore")
        self.git(self.main, "commit", "-q", "-m", "skills: the accept scripts, in the clone they integrate into")
        self.git(self.worktree, "rebase", "-q", "main")
        return self.main / "skills" / "lead" / "scripts" / "accept.sh"

    def snapshot(self):
        """Everything a refusal must leave alone: the main clone's HEAD, status and refs, and the session dir's files but
        the message, which the call itself writes; a file nobody may read, by its mode."""
        files = {str(p.relative_to(self.dir)): p.read_bytes() if os.access(p, os.R_OK) else p.stat().st_mode
                 for p in sorted(self.dir.rglob("*")) if p.is_file() and p != self.message_path()}
        return (self.git(self.main, "rev-parse", "HEAD"), self.git(self.main, "status", "--porcelain"),
                self.git(self.main, "for-each-ref", "--format=%(refname) %(objectname)"), files)

    def run_json(self):
        return json.loads((self.dir / "run.json").read_text())

    def assert_refused(self, name, *options, message=EDITED, tip=TIP_NOW):
        before = self.snapshot()
        code, _, err = self.accept(*options, message=message, tip=tip)
        self.assertEqual(code, 2, err)
        self.assertIn(f"refused: {name}: ", err)
        self.assertEqual(self.snapshot(), before)
        return err


class HappyPathTests(AcceptCase):
    """L1 · a done session with an intake, a tip ahead of main, a clean main clone and a message file is integrated."""

    def setUp(self):
        super().setUp()
        self.old_main = self.git(self.main, "rev-parse", "main")
        self.tip = self.git(self.main, "rev-parse", BRANCH)
        self.code, self.out, self.err = self.accept()

    def test_accept__main_gains_one_commit_on_the_old_main_with_the_tips_tree(self):
        """L1.1 main moves by exactly one commit, parented on the old main, carrying the tip's tree — anything else replays or loses the session's work."""
        self.assertEqual(self.code, 0, self.err)
        new = self.git(self.main, "rev-parse", "main")
        self.assertEqual(self.git(self.main, "rev-list", "--parents", "-n", "1", new).split(), [new, self.old_main])
        self.assertEqual(self.git(self.main, "rev-parse", f"{new}^{{tree}}"), self.git(self.main, "rev-parse", f"{self.tip}^{{tree}}"))

    def test_accept__the_commit_message_is_the_message_files(self):
        """L1.2 the squash commit carries the --message file's text — the Owner's reviewed message would not be what is integrated."""
        self.assertEqual(self.code, 0, self.err)
        self.assertEqual(self.git(self.main, "log", "-1", "--format=%B", "main").strip(), EDITED.strip())

    def test_accept__run_json_records_the_accepted_sha_through_the_accept_event(self):
        """L1.4 run.json.accepted = {sha, at} for the new main, and events.jsonl ends with `accept` — the roster and intake could not tell an accepted session from one awaiting acceptance."""
        self.assertEqual(self.code, 0, self.err)
        accepted = self.run_json().get("accepted") or {}
        self.assertEqual(accepted.get("sha"), self.git(self.main, "rev-parse", "main"))
        self.assertTrue(accepted.get("at"))
        last = json.loads((self.dir / "events.jsonl").read_text().splitlines()[-1])
        self.assertEqual((last["event"], last.get("refused", False)), ("accept", False))

    def test_accept__prints_that_the_integrated_tree_is_the_tips(self):
        """L1.5 the output says `tree-identical: yes` — the Owner has no line to check the squash against the reviewed tip."""
        self.assertEqual(self.code, 0, self.err)
        self.assertIn("tree-identical: yes", self.out)

    def test_accept__prints_the_teardown_line_and_never_runs_it(self):
        """L1.6 the worktree-remove line is printed and the worktree and branch still exist — teardown is the Owner's."""
        self.assertEqual(self.code, 0, self.err)
        self.assertIn(f"worktree remove {self.worktree}", self.out)
        self.assertTrue(self.worktree.is_dir())
        self.assertEqual(self.git(self.main, "rev-parse", BRANCH), self.tip)


class RefusalTests(AcceptCase):
    """L2–L8 · each preflight refuses by name, exit 2, and changes nothing."""

    def test_accept__refused_when_main_has_a_commit_the_tip_lacks(self):
        """L2 a tip behind main is refused main-not-ancestor — the squash would silently revert main's newer commit."""
        self.commit(self.main, "CHANGELOG.md", "changelog: a commit the session never saw")
        self.assert_refused("main-not-ancestor")

    def test_accept__refused_when_the_main_worktree_is_dirty(self):
        """L3 a modified tracked file in the main clone is refused main-dirty — the fast-forward would run over the Owner's uncommitted work."""
        (self.main / "README.md").write_text("an edit the Owner has not committed\n")
        self.assert_refused("main-dirty")

    def test_accept__refused_when_the_session_has_no_intake(self):
        """L4 no INTAKE.md is refused intake-missing — the plan would never absorb what the session changed."""
        (self.dir / "INTAKE.md").unlink()
        self.assert_refused("intake-missing")

    def test_accept__refused_when_the_session_is_not_done(self):
        """L5 phase end-of-stack is refused phase-not-done — unreviewed, unfinished work would be integrated."""
        self.given_session(phase="end-of-stack")
        self.assert_refused("phase-not-done")

    def test_accept__refused_when_the_session_is_already_accepted(self):
        """L7 a second accept of an accepted session is refused already-accepted — it was refused main-not-ancestor, whose rebase advice leads to an empty squash that overwrites accepted (gate F3)."""
        code, _, err = self.accept()
        self.assertEqual(code, 0, err)
        self.assert_refused("already-accepted")

    def test_accept__an_unreadable_run_json_is_an_error_and_not_a_refusal(self):
        """L8 a truncated run.json exits 1 naming the file, with no refusal line — it was refused phase-not-done quoting a phase the file never held (gate F1)."""
        (self.dir / "run.json").write_text('{"phase": "do')
        code, _, err = self.accept()
        self.assertEqual(code, 1, err)
        self.assertIn("is not readable JSON", err)
        self.assertNotIn("refused:", err)


class TipTests(AcceptCase):
    """L40–L42 · --tip names the commit the line was composed for, and the accept integrates that commit or nothing."""

    def test_accept__no_tip_is_refused_before_anything_is_read(self):
        """L40 no --tip, with no --message and no run.json either, is refused tip-missing, and nothing changes — an
        accept without it integrates whatever the branch holds when the Owner runs the line."""
        (self.dir / "run.json").unlink()
        self.assert_refused("tip-missing", message=None, tip=None)

    def test_accept__a_tip_that_is_not_a_full_commit_id_is_refused(self):
        """L41 --tip a short id, a branch name, or 40 characters with a non-hex one is refused tip-invalid — a name
        resolves to whatever it points at when the line runs."""
        for tip in ("abc1234", BRANCH, "g" * 40):
            with self.subTest(tip=tip):
                self.assert_refused("tip-invalid", tip=tip)

    def test_accept__a_branch_past_the_tip_is_refused_naming_both_ids(self):
        """L42 a commit added on the session branch after the line was composed is refused tip-moved, naming the tip
        the line gives and the branch's, and main does not move — the commit added would be integrated unreviewed."""
        composed = self.branch_tip()
        self.commit(self.worktree, "late.txt", "notes: a commit after the line was composed")
        err = self.assert_refused("tip-moved", tip=composed)
        self.assertIn(composed, err)
        self.assertIn(self.branch_tip(), err)


class MessageFileTests(AcceptCase):
    """L9–L11, L15, L20 · the message is the `--message` file, and nothing else."""

    def test_accept__a_message_file_is_integrated_with_its_comment_lines_stripped(self):
        """L9 main's new commit carries the file's message minus `#` lines — a comment meant for the Owner reaches history."""
        code, _, err = self.accept(message=PREPARED)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.git(self.main, "log", "-1", "--format=%B", "main").strip(),
                         "notes: a prepared title message\n\nwritten to a file before the accept")

    def test_accept__refused_when_the_message_file_holds_only_comments(self):
        """L10 a file of `#` lines only is refused message-empty, nothing written — an empty commit message would be integrated."""
        self.assert_refused("message-empty", message="# nothing to say\n")

    def test_accept__refused_by_name_when_the_message_file_is_missing_or_unreadable(self):
        """L11 a missing or mode-000 message file is refused message-unreadable naming the path, before anything is written — a half-run accept with no message (assumed Q1)."""
        missing = self.unit_folder / "no-such-message.txt"
        unreadable = self.unit_folder / "unreadable.txt"
        unreadable.write_text(PREPARED)
        unreadable.chmod(0)
        for path in (missing, unreadable):
            with self.subTest(path=path.name):
                err = self.assert_refused("message-unreadable", "--message", str(path), message=None)
                self.assertIn(str(path), err)

    def test_accept__refused_when_the_message_file_is_a_link_and_never_prints_its_target(self):
        """L11.1 a message file that is a symlink to a file outside the session's folders is refused message-unreadable,
        nothing on main, and the target's text is printed nowhere — it became main's commit message."""
        target = self.root / "outside" / "kept.txt"
        target.parent.mkdir()
        target.write_text("STAND-IN-TEXT-OUTSIDE (not a message)\n")
        link = self.unit_folder / "commit-message.txt"
        link.symlink_to(target)
        before = self.snapshot()
        code, out, err = self.accept("--message", str(link), message=None)
        self.assertEqual(code, 2, err)
        self.assertIn("refused: message-unreadable: ", err)
        self.assertIn(link.name, err)
        self.assertNotIn("STAND-IN-TEXT-OUTSIDE", out + err)
        self.assertEqual(self.snapshot(), before)

    def test_accept__refused_at_once_when_the_message_file_is_a_fifo(self):
        """L11.2 a FIFO at the message path is refused message-unreadable within seconds — `cat` waited on it for a
        writer that never comes."""
        fifo = self.unit_folder / "commit-message.txt"
        os.mkfifo(fifo)
        before = self.snapshot()
        done = subprocess.run(["bash", str(ACCEPT), "--tip", self.branch_tip(), "--message", str(fifo), str(self.dir)], capture_output=True,
                              text=True, env=self.accept_env(), cwd=self.tmp.name, timeout=5)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("refused: message-unreadable: ", done.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_accept__refused_when_the_message_file_has_gits_default_squash_subject(self):
        """L15 a file whose first line is `Squashed commit of the following:` is refused message-git-default — main gains a subject that says nothing (assumed Q2)."""
        self.assert_refused("message-git-default", message=GIT_DEFAULT)

    def test_accept__refused_without_a_message_file_and_never_asks_git_for_an_editor(self):
        """L20, M9 no --message is refused message-missing naming the hook's message path, nothing written, and no `git var` runs — the editor git's config names would run as the Owner, and a hint naming any file teaches a line accept.sh refuses."""
        err = self.assert_refused("message-missing", message=None)
        self.assertIn(f"--message {self.dir}/prs/<unit>/commit-message.txt ", err)
        done = subprocess.run(["bash", str(ACCEPT), "--tip", self.branch_tip(), f"{self.dir}/"], capture_output=True, text=True,
                              env=self.accept_env(), cwd=self.tmp.name)
        self.assertIn(f"--message {self.dir}/prs/<unit>/commit-message.txt ", done.stderr)
        self.assertNotIn("var", [subcommand(c) for c in git_calls(self.log)])


class MessagePlaceTests(AcceptCase):
    """M1–M8 · the squash message is read only from a unit folder directly under the session's prs/."""

    def assert_outside(self, path):
        """`path` holding outside text is refused message-outside naming the unit folders, nothing changed, its text
        printed nowhere."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(OUTSIDE_TEXT)
        before = self.snapshot()
        code, out, err = self.accept("--message", str(path), message=None)
        self.assertEqual(code, 2, err)
        self.assertIn("refused: message-outside: ", err)
        self.assertIn(f"{self.dir}/prs/<unit>", err)
        self.assertNotIn(OUTSIDE_TEXT.strip(), out + err)
        self.assertEqual(self.snapshot(), before)

    def test_accept__a_message_outside_a_unit_folder_of_the_session_is_refused_and_never_printed(self):
        """M1–M6 a message beside prs/, outside the session, directly in prs/, a folder too deep, a `..` that lands in the
        unit folder or stands for it, and a sibling session whose name starts with this one's are each refused
        message-outside — any file the Owner can read became main's commit message and was printed (U58 B1)."""
        cases = {
            "beside prs": lambda: self.dir / "commit-message.txt",
            "outside the session": lambda: self.root / "outside" / "message.txt",
            "directly in prs": lambda: self.dir / "prs" / "commit-message.txt",
            "one folder too deep": lambda: self.unit_folder / "notes" / "commit-message.txt",
            "a dot-dot landing inside": lambda: f"{self.unit_folder}/../U1/commit-message.txt",
            "a dot-dot as the unit folder": lambda: f"{self.dir}/prs/../commit-message.txt",
            "a folder sharing the leading characters":
                lambda: self.root / "sessions" / f"{self.dir.name}-other" / "prs" / "U1" / "commit-message.txt",
        }
        for name, place in cases.items():
            with self.subTest(place=name):
                self.tearDown()
                self.setUp()
                self.assert_outside(place())

    def test_accept__a_message_in_another_units_folder_is_integrated(self):
        """M7 a message in prs/U2/ integrates: run.json is read only after the message, so the folder is not pinned to
        the session's unit — a later tightening must show up as this test changing."""
        other = self.dir / "prs" / "U2" / "commit-message.txt"
        other.parent.mkdir()
        other.write_text(PREPARED)
        code, _, err = self.accept("--message", str(other), message=None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.git(self.main, "log", "-1", "--format=%s", "main"), "notes: a prepared title message")


class ConfigHookTests(AcceptCase):
    """L30 · the fast-forward runs no config hook (git 2.54's `hook.<name>.*`), which core.hooksPath=/dev/null leaves
    running, a name holding `=` included (U52b C4)."""

    def given_config_hooks(self, repo, event):
        markers = self.root / "markers"
        markers.mkdir(exist_ok=True)
        for name in ("probe", "a=b"):
            program = self.root / f"hook-{name}"
            program.write_text(f"#!/bin/sh\ntouch '{markers / name}'\n")
            program.chmod(0o755)
            self.git(repo, "config", f"hook.{name}.event", event)
            self.git(repo, "config", f"hook.{name}.command", str(program))
        return markers

    def test_accept__the_fast_forward_runs_no_post_merge_config_hook(self):
        """L30 post-merge config hooks `probe` and `a=b` in the main clone: the accept integrates and no marker exists."""
        markers = self.given_config_hooks(self.main, "post-merge")

        code, _, err = self.accept()

        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(p.name for p in markers.iterdir()), [])


class WorktreeTests(AcceptCase):
    """L17–L19 · the worktree is one the configured repository lists, and the main clone is that repository."""

    def test_accept__refused_when_no_configured_repository_lists_the_worktree(self):
        """L17 a worktree of a repository no robowright.json names is refused worktree-unlisted, nothing changed, and no git runs inside it — its config and hooks would run as the Owner."""
        self.given_configured(self.root / "some-other-clone")
        err = self.assert_refused("worktree-unlisted")
        self.assertIn(str(self.worktree), err)
        self.assertEqual([c for c in git_calls(self.log) if runs_in(c, self.worktree)], [])

    def test_accept__refused_when_the_worktree_s_git_file_names_another_repository(self):
        """L18 a listed worktree whose .git points into another clone is refused worktree-foreign-gitdir, and that clone's main does not move — accept.sh took the main clone from the worktree's own metadata."""
        decoy = self.root / "decoy"
        decoy.mkdir()
        self.git(decoy, "init", "-q", "-b", "main")
        self.git(decoy, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "decoy")
        self.git(decoy, "worktree", "add", "-q", "-b", BRANCH, str(self.root / "decoy-wt"), "main")
        decoy_main = self.git(decoy, "rev-parse", "main")
        (self.worktree / ".git").write_text((self.root / "decoy-wt" / ".git").read_text())

        self.assert_refused("worktree-foreign-gitdir")

        self.assertEqual(self.git(decoy, "rev-parse", "main"), decoy_main)

    def test_accept__every_git_call_carries_the_overrides(self):
        """L19 every git accept.sh runs, in the worktree and in the main clone, starts with the fsmonitor, hooksPath, pager and showSignature overrides — the merge would run the clone's post-merge hook as the Owner."""
        code, _, err = self.accept()
        self.assertEqual(code, 0, err)
        calls = git_calls(self.log)
        self.assertIn("merge", [subcommand(c) for c in calls])
        for call in calls:
            self.assertEqual(call[:len(HARDENING)], HARDENING, call)


class AllowlistTests(AcceptCase):
    """L24–L25 · accept.sh integrates only into a repository launch.json's `repos` lists."""

    def test_accept__a_repository_a_new_robowright_json_plants_is_refused_and_does_not_move(self):
        """L24 the N-1 reproduction: a session's repository and worktree, named by a new project folder's robowright.json and not by launch.json's `repos`, is refused worktree-unlisted naming `repos`, its main does not move, and no git runs in it — accept.sh integrated into the planted repository with its own config in force."""
        planted = self.root / "planted"
        planted.mkdir()
        self.git(planted, "init", "-q", "-b", "main")
        self.git(planted, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "planted")
        planted_wt = self.root / "planted-wt"
        self.git(planted, "worktree", "add", "-q", "-b", BRANCH, str(planted_wt), "main")
        self.git(planted_wt, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "ahead")
        planted_main = self.git(planted, "rev-parse", "main")
        folder = self.projects / "newfolder"
        folder.mkdir(parents=True)
        (folder / "robowright.json").write_text(json.dumps({"repos": [{"name": "planted", "path": str(planted)}]}) + "\n")
        self.given_session(phase="done", worktree=planted_wt)

        err = self.assert_refused("worktree-unlisted")

        self.assertIn("`repos`", err)
        self.assertEqual(self.git(planted, "rev-parse", "main"), planted_main)
        self.assertEqual([c for c in git_calls(self.log) if runs_in(c, planted) or runs_in(c, planted_wt)], [])

    def test_accept__no_repos_key_is_refused_naming_the_key_the_file_and_the_line_to_add(self):
        """L25 with launch.json holding no `repos`, accept.sh is refused repos-unconfigured, nothing changed, and stderr names the file and prints the `"repos": [...]` line holding the configured repository — the first accept after this change would fail with no word on how to fix it."""
        self.given_launch_json({"schema": 1})

        err = self.assert_refused("repos-unconfigured")

        self.assertIn(str(self.home / ".claude/robowright/launch.json"), err)
        self.assertIn(f'"repos": [{json.dumps(str(self.main))}]', err)


class SubmoduleTests(AcceptCase):
    def test_accept__the_main_clone_status_does_not_descend_into_submodules(self):
        """L23 the main-dirty check runs `status --porcelain --ignore-submodules=all` in the main clone — status would run git in each submodule under that submodule's own config (review 2 F11)."""
        code, _, err = self.accept()
        self.assertEqual(code, 0, err)
        statuses = [c for c in git_calls(self.log) if subcommand(c) == "status"]
        self.assertEqual([("--ignore-submodules=all" in c) for c in statuses], [True])


class DisplayTests(AcceptCase):
    """L21 · session-written text accept.sh prints carries no control bytes."""

    def test_accept__control_bytes_in_the_message_and_the_phase_are_not_printed(self):
        """L21 an escape sequence, C0 or C1, in the message file and in run.json.phase reaches neither stdout nor stderr — it could hide or rewrite what the Owner reads before the accept."""
        code, out, _ = self.accept(message="notes: a title\x1b[2J\n\nbody\x07 and \u009b2J é\n")
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x07", out)
        self.assertNotIn("\u009b", out)
        self.assertIn("notes: a title[2J", out)
        self.assertIn("body and 2J é", out)

        run = self.run_json()
        run["phase"] = "end\x1b]0;x\x07-of-stack"
        (self.dir / "run.json").write_text(json.dumps(run))
        code, _, err = self.accept()
        self.assertEqual(code, 2, err)
        self.assertIn("refused: phase-not-done: ", err)
        self.assertNotIn("\x1b", err)
        self.assertNotIn("\x07", err)


class SignTests(AcceptCase):
    """L22 · `-S` signs the squash with the main clone's own signing configuration; without it nothing is signed."""

    def given_ssh_signing(self):
        key = self.root / "signing-key"
        made = subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "sample", "-f", str(key)], capture_output=True, text=True)
        if made.returncode != 0:
            self.skipTest(f"ssh-keygen could not make a key: {made.stderr}")
        self.git(self.main, "config", "gpg.format", "ssh")
        self.git(self.main, "config", "user.signingkey", str(key))

    def commit_tree_calls(self):
        return [c for c in git_calls(self.log) if subcommand(c) == "commit-tree"]

    def test_accept__dash_s_reaches_commit_tree_and_the_squash_is_signed(self):
        """L22.1 `accept.sh -S` runs `commit-tree -S` and main's new commit carries a signature — a session's squash could not be signed like a direct build's."""
        self.given_ssh_signing()
        code, _, err = self.accept("-S")
        self.assertEqual(code, 0, err)
        self.assertEqual([("-S" in c) for c in self.commit_tree_calls()], [True])
        self.assertIn("gpgsig", self.git(self.main, "cat-file", "commit", "main"))

    def test_accept__sign_is_the_long_spelling_of_dash_s(self):
        """L22.2 `--sign` is `-S` — the spelling in a pasted accept line would be refused as unknown."""
        self.given_ssh_signing()
        code, _, err = self.accept("--sign")
        self.assertEqual(code, 0, err)
        self.assertEqual([("-S" in c) for c in self.commit_tree_calls()], [True])

    def test_accept__without_dash_s_the_squash_is_not_signed(self):
        """L22.3 with signing configured but no -S, commit-tree gets no -S and the commit has no signature — behaviour without the flag changed. Guard: a default of `-S` breaks every unsigned accept, so no edit reddens this test alone; it guards an unsigned accept that starts signing."""
        self.given_ssh_signing()
        code, _, err = self.accept()
        self.assertEqual(code, 0, err)
        self.assertEqual([("-S" in c) for c in self.commit_tree_calls()], [False])
        self.assertNotIn("gpgsig", self.git(self.main, "cat-file", "commit", "main"))



SLUG = "sample-001-notes"
CONFLICTING = "list.txt"
# Text, not Python: an accept that imported it would fail with a SyntaxError, and nothing in it runs either way.
NOT_PYTHON = "a build's file named like a standard library module; not Python\n"
NOTES = "".join(f"line {n}\n" for n in range(1, 9))
DIRECT_REFUSALS = ("message-missing", "message-unreadable", "message-empty", "message-git-default", "description-missing",
                   "already-accepted", "branch-missing", "base-not-ancestor", "base-not-on-main", "main-dirty", "worktree-dirty",
                   "slug-invalid", "base-invalid", "tip-missing", "tip-invalid", "tip-moved")


class DirectCase(AcceptCase):
    """A direct build: no session folder, its records in the project folder's prs/<slug>/, the change description beside
    them, and its branch in the trusted main clone, two commits ahead of the base."""

    def setUp(self):
        super().setUp()
        self.folder = self.projects / "sample"
        self.records = self.folder / "prs" / SLUG
        self.records.mkdir(parents=True)
        (self.folder / "prs" / f"{SLUG}.md").write_text("# Change description\n")
        self.base = self.git(self.main, "rev-parse", "main")
        self.tip = self.git(self.main, "rev-parse", BRANCH)

    def message_path(self):
        """Where the hook puts a direct build's squash message: prs/<slug>/ in the project folder."""
        return self.records / "commit-message.txt"

    def direct(self, *options, message=EDITED, base=None, slug=SLUG, cwd=None, script=ACCEPT, tip=TIP_NOW):
        """`script` --direct with `options`, --base (the fixture's base unless given), --tip (the branch's tip now
        unless given; none when None), --message naming a file holding `message` unless it is None, the project folder
        and `slug`, run from `cwd` (the scratch root unless given)."""
        args = ["--direct", "--base", base or self.base, *options]
        if tip is not None:
            args = ["--tip", self.branch_tip() if tip is TIP_NOW else tip, *args]
        if message is not None:
            args = ["--message", str(self.message_file(message)), *args]
        done = subprocess.run(["bash", str(script), *args, str(self.folder), slug], capture_output=True, text=True,
                              env=self.accept_env(), cwd=cwd or self.tmp.name)
        return done.returncode, done.stdout, done.stderr

    def direct_snapshot(self):
        """Everything a refusal must leave alone: main's HEAD, status and refs, the worktree's status, the project's files
        but the message, which the call itself writes."""
        files = {str(p.relative_to(self.folder)): p.read_bytes() for p in sorted(self.folder.rglob("*"))
                 if p.is_file() and p != self.message_path()}
        return (self.git(self.main, "rev-parse", "HEAD"), self.git(self.main, "status", "--porcelain"),
                self.git(self.main, "for-each-ref", "--format=%(refname) %(objectname)"),
                self.git(self.worktree, "status", "--porcelain"), files)

    def assert_direct_refused(self, name, *options, **kwargs):
        before = self.direct_snapshot()
        code, _, err = self.direct(*options, **kwargs)
        self.assertEqual(code, 2, err)
        self.assertIn(f"refused: {name}: ", err)
        self.assertEqual(self.direct_snapshot(), before)
        return err

    def record(self):
        return json.loads((self.records / "ACCEPTED.json").read_text())

    def given_main_moved(self, name="CHANGELOG.md"):
        self.commit(self.main, name, "changelog: a commit the build never saw")
        return self.git(self.main, "rev-parse", "main")


class DirectHappyPathTests(DirectCase):
    """X1–X3 · main still at the base: one commit carrying the tip's tree, the record, the teardown line."""

    def setUp(self):
        super().setUp()
        self.code, self.out, self.err = self.direct()

    def test_direct__main_at_base_gains_one_commit_with_the_tips_tree_and_the_files_message(self):
        """X1 main moves by one commit on the base, with the tip's tree and the message file's text — the build's reviewed tree would not be what is integrated."""
        self.assertEqual(self.code, 0, self.err)
        new = self.git(self.main, "rev-parse", "main")
        self.assertEqual(self.git(self.main, "rev-list", "--parents", "-n", "1", new).split(), [new, self.base])
        self.assertEqual(self.git(self.main, "rev-parse", f"{new}^{{tree}}"), self.git(self.main, "rev-parse", f"{self.tip}^{{tree}}"))
        self.assertEqual(self.git(self.main, "log", "-1", "--format=%B", "main").strip(), EDITED.strip())

    def test_direct__writes_the_accept_record_with_sha_at_base_and_tip(self):
        """X2 prs/<slug>/ACCEPTED.json holds sha (the new main), at, base and tip, and nothing else (assumed Q3) — the dashboard has no record to verify, so the build never reads landed."""
        self.assertEqual(self.code, 0, self.err)
        record = self.record()
        self.assertEqual(sorted(record), ["at", "base", "sha", "tip"])
        self.assertEqual((record["sha"], record["base"], record["tip"]), (self.git(self.main, "rev-parse", "main"), self.base, self.tip))
        self.assertIsNotNone(datetime.fromisoformat(record["at"]).tzinfo)

    def test_direct__prints_the_teardown_and_never_runs_it(self):
        """X3 the worktree-remove and branch-delete line is printed and both still exist — teardown is the Owner's."""
        self.assertEqual(self.code, 0, self.err)
        self.assertIn(f"worktree remove {self.worktree}", self.out)
        self.assertIn(f"branch -D {BRANCH}", self.out)
        self.assertTrue(self.worktree.is_dir())
        self.assertEqual(self.git(self.main, "rev-parse", BRANCH), self.tip)


class DirectRecordUnwritableTests(DirectCase):
    """052a-X1 · the record write fails after main fast-forwarded: prs/<slug>/ is read-only, which session_write.py
    check passes (the record is missing) and replace refuses."""

    def setUp(self):
        super().setUp()
        self.message_file(EDITED)
        self.records.chmod(0o555)

    def recovery_line(self, err):
        """The line after `Write it with: ` in `err`, as the two argv lists its `|` separates."""
        match = re.search(r"Write it with: (.*)$", err, re.M)
        self.assertIsNotNone(match, err)
        words = shlex.split(match.group(1))
        cut = words.index("|")
        return words[:cut], words[cut + 1:]

    def test_direct__an_unwritable_record_after_the_fast_forward_prints_the_line_that_writes_it(self):
        """052a-X1 nonzero exit with main at the squash, and the message carries the line that writes ACCEPTED.json — main moved and nothing says how to record it, so the dashboard never reads the build landed."""
        code, _, err = self.direct("--message", str(self.message_path()), message=None)

        self.assertNotEqual(code, 0, err)
        squash = self.git(self.main, "rev-parse", "main")
        self.assertEqual(self.git(self.main, "rev-list", "--parents", "-n", "1", squash).split(), [squash, self.base])
        printer, writer = self.recovery_line(err)
        self.records.chmod(0o755)
        printed = subprocess.run(printer, capture_output=True, check=True).stdout
        subprocess.run(writer, input=printed, capture_output=True, check=True)
        self.assertEqual((self.record()["sha"], self.record()["base"], self.record()["tip"]), (squash, self.base, self.tip))


class DirectMovedMainTests(DirectCase):
    """X4–X5 · main moved past the base: the range applied as one commit, or refused on a conflict."""

    def test_direct__a_moved_main_gets_the_range_applied_and_says_so(self):
        """X4 main gains one commit on the moved main holding main's new file and the branch's two, and the output says main moved 1 commit and the patch-id matches (assumed Q2) — the Owner's hand-run cherry-pick, the accepted baseline, would be refused or silent."""
        moved = self.given_main_moved()
        code, out, err = self.direct()
        self.assertEqual(code, 0, err)
        new = self.git(self.main, "rev-parse", "main")
        self.assertEqual(self.git(self.main, "rev-list", "--parents", "-n", "1", new).split(), [new, moved])
        self.assertEqual(sorted(self.git(self.main, "ls-tree", "--name-only", new).split()),
                         ["CHANGELOG.md", "README.md", "list.txt", "title.txt"])
        self.assertIn("main moved: 1 commit", out)
        self.assertIn("patch-id: same", out)

    def test_direct__says_the_patch_id_differs_when_main_already_holds_part_of_the_change(self):
        """X11 main making the branch's first edit identically after the base integrates cleanly and prints `patch-id: DIFFERENT` — the Owner reads `same` for a commit that is not the reviewed change."""
        self.commit(self.main, "title.txt", FIRST_SUBJECT)
        code, out, err = self.direct()
        self.assertEqual(code, 0, err)
        self.assertIn("patch-id: DIFFERENT", out)

    def test_direct__a_conflicting_range_is_refused_with_main_and_the_worktree_untouched(self):
        """X5 main changing the line the branch changes is refused range-conflicts, nothing written anywhere — a half-applied pick would leave the Owner's main checkout mid-conflict."""
        self.given_main_moved(name=CONFLICTING)
        self.assert_direct_refused("range-conflicts")
        self.assertFalse((self.records / "ACCEPTED.json").exists())


class DirectRefusalTests(DirectCase):
    """X8–X10 · each preflight refuses by name, exit 2, before anything is written."""

    def test_direct__refused_by_name_before_anything_is_written(self):
        """X8 each of the brief's preflight cases is refused by its name with main, the worktree and the project's files unchanged — a half-run accept, or one over the Owner's or the build's uncommitted work."""
        cases = {
            "message-missing": lambda: {"message": None},
            "message-unreadable": lambda: {"message": None, "options": ("--message", str(self.records / "no-such.txt"))},
            "message-empty": lambda: {"message": "# nothing to say\n"},
            "message-git-default": lambda: {"message": GIT_DEFAULT},
            "description-missing": lambda: (self.folder / "prs" / f"{SLUG}.md").unlink() or {},
            "already-accepted": lambda: [(self.records / "ACCEPTED.json").write_text("{}\n"), {}][1],
            "branch-missing": lambda: self.given_message_for(**self.given_described("sample-002-other")),
            "base-not-ancestor": lambda: {"base": self.given_main_moved()},
            "base-not-on-main": lambda: {"base": self.git(self.main, "rev-parse", f"{BRANCH}~1")},
            "main-dirty": lambda: [(self.main / "README.md").write_text("an edit the Owner has not committed\n"), {}][1],
            "worktree-dirty": lambda: [(self.worktree / "title.txt").write_text("an edit the build never committed\n"), {}][1],
            "slug-invalid": lambda: self.given_message_for(f"{SLUG}.lock"),
            "base-invalid": lambda: {"base": "HEAD~1"},
            "tip-missing": lambda: {"tip": None},
            "tip-invalid": lambda: {"tip": BRANCH},
            "tip-moved": lambda: {"tip": self.given_tip_moved()},
        }
        self.assertEqual(tuple(cases), DIRECT_REFUSALS)
        for name, given in cases.items():
            with self.subTest(refusal=name):
                self.tearDown()
                self.setUp()
                kwargs = given()
                options = kwargs.pop("options", ())
                self.assert_direct_refused(name, *options, **kwargs)

    def test_direct__a_branch_past_the_tip_is_refused_naming_both_ids(self):
        """X30 --direct, a commit added on the branch after the line was composed: tip-moved naming both ids, and nothing
        written — --direct keeps no phase guard, so --tip is what pins the reviewed commit."""
        composed = self.given_tip_moved()
        err = self.assert_direct_refused("tip-moved", tip=composed)
        self.assertIn(composed, err)
        self.assertIn(self.branch_tip(), err)

    def given_tip_moved(self):
        """A commit added on the branch after the line was composed; returns the tip the line names."""
        composed = self.branch_tip()
        self.commit(self.worktree, "late.txt", "notes: a commit after the line was composed")
        return composed

    def given_message_for(self, slug):
        """The message at prs/<slug>/ for a build other than the fixture's, so the refusal after the message is reached."""
        path = self.folder / "prs" / slug / "commit-message.txt"
        path.parent.mkdir(exist_ok=True)
        path.write_text(EDITED)
        return {"slug": slug, "message": None, "options": ("--message", str(path))}

    def given_described(self, slug):
        """A change description and records folder for `slug`, a build no repository has a branch for."""
        (self.folder / "prs" / f"{slug}.md").write_text("# Change description\n")
        (self.folder / "prs" / slug).mkdir()
        return {"slug": slug}

    def test_direct__refused_when_two_trusted_repositories_hold_the_branch(self):
        """X9 a second trusted repository the project names, also holding robowright/<slug>, is refused branch-ambiguous and neither main moves — the accept would pick one of two branches by order."""
        other = self.root / "other"
        other.mkdir()
        self.git(other, "init", "-q", "-b", "main")
        self.git(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "other")
        self.git(other, "branch", BRANCH)
        other_main = self.git(other, "rev-parse", "main")
        self.given_configured(self.main, other)
        self.given_allowlisted(self.main, other)
        self.assert_direct_refused("branch-ambiguous")
        self.assertEqual(self.git(other, "rev-parse", "main"), other_main)

    def test_direct__a_branch_only_in_an_untrusted_repository_is_missing_and_no_git_runs_there(self):
        """X10 robowright/<slug> held only by a repository robowright.json names and launch.json's `repos` does not list is refused branch-missing, and no git runs in it — its config and hooks would run as the Owner."""
        planted = self.root / "planted"
        planted.mkdir()
        self.git(planted, "init", "-q", "-b", "main")
        self.git(planted, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "planted")
        self.git(planted, "branch", BRANCH)
        self.git(self.worktree, "switch", "-q", "--detach")
        self.git(self.main, "branch", "-D", BRANCH)
        self.given_configured(self.main, planted)
        self.assert_direct_refused("branch-missing")
        self.assertEqual([c for c in git_calls(self.log) if runs_in(c, planted)], [])


class DirectMessagePlaceTests(DirectCase):
    """X40–X49 · a direct build's squash message is read only from <project_dir>/prs/<slug>/, <project_dir> links
    resolved."""

    def assert_outside(self, path, folder=None):
        """`path` holding outside text is refused message-outside naming prs/<slug>/ under the real project folder,
        nothing written, its text printed nowhere; the project folder is given as `folder`, else the real one."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(OUTSIDE_TEXT)
        self.folder, given = Path(folder or self.folder), self.folder
        try:
            before = self.direct_snapshot()
            code, out, err = self.direct("--message", str(path), message=None)
            after = self.direct_snapshot()
        finally:
            self.folder = given
        self.assertEqual(code, 2, err)
        self.assertIn("refused: message-outside: ", err)
        self.assertIn(f"{self.records}", err)
        self.assertNotIn(OUTSIDE_TEXT.strip(), out + err)
        self.assertEqual(after, before)
        self.assertFalse((self.records / "ACCEPTED.json").exists())

    def test_direct__a_message_outside_the_builds_prs_folder_is_refused_and_never_printed(self):
        """X40–X46 a message beside prs/, outside the project, directly in prs/, a folder too deep, a `..` that lands in
        the folder, a folder whose name starts with the slug, and another build's folder are each refused message-outside
        — the line is session text, and any file the Owner can read became main's commit message and was printed (U58 B1)."""
        cases = {
            "beside prs": lambda: self.folder / "commit-message.txt",
            "outside the project": lambda: self.root / "outside" / "message.txt",
            "directly in prs": lambda: self.folder / "prs" / "commit-message.txt",
            "one folder too deep": lambda: self.records / "notes" / "commit-message.txt",
            "a dot-dot landing inside": lambda: f"{self.records}/../{SLUG}/commit-message.txt",
            "a folder sharing the leading characters": lambda: self.folder / "prs" / f"{SLUG}-other" / "commit-message.txt",
            "another build's folder": lambda: self.folder / "prs" / "sample-002-other" / "commit-message.txt",
        }
        for name, place in cases.items():
            with self.subTest(place=name):
                self.tearDown()
                self.setUp()
                self.assert_outside(place())

    def test_direct__a_project_folder_given_through_a_link_takes_the_message_only_from_its_real_folder(self):
        """X47–X48 with the project folder given as a link, the message spelled through the link is refused
        message-outside and the one in the real folder integrates — the prefix is compared as the disk spells it."""
        link = self.root / "linked-project"
        link.symlink_to(self.folder)
        self.assert_outside(link / "prs" / SLUG / "commit-message.txt", folder=link)
        self.message_file(EDITED)
        args = ["--tip", self.tip, "--message", str(self.message_path()), "--direct", "--base", self.base, str(link), SLUG]
        done = subprocess.run(["bash", str(ACCEPT), *args], capture_output=True, text=True, env=self.accept_env(), cwd=self.tmp.name)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.git(self.main, "log", "-1", "--format=%B", "main").strip(), EDITED.strip())

    def test_direct__no_message_names_the_builds_message_path(self):
        """X49 no --message is refused message-missing, and the line it prints names prs/<slug>/commit-message.txt —
        a hint naming any file teaches a line accept.sh refuses."""
        err = self.assert_direct_refused("message-missing", message=None)
        self.assertIn(f"--message {self.folder}/prs/{SLUG}/commit-message.txt ", err)

    def test_direct__no_message_names_the_real_message_path_for_a_folder_spelled_with_a_trailing_slash(self):
        """X49.1 the project folder given as `<folder>/` still gets prs/<slug>/commit-message.txt under its real path in
        the hint — `<folder>//prs/…` has an empty part, and message-outside refuses the line the hint taught (gate F1)."""
        args = ["--tip", self.tip, "--direct", "--base", self.base, f"{self.folder}/", SLUG]
        done = subprocess.run(["bash", str(ACCEPT), *args], capture_output=True, text=True, env=self.accept_env(), cwd=self.tmp.name)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn(f"--message {self.folder}/prs/{SLUG}/commit-message.txt ", done.stderr)

    def test_direct__a_records_folder_that_is_a_link_is_refused_before_the_message_is_read(self):
        """X8.1 prs/<slug>/ a link to a folder holding the message is refused message-unreadable, nothing written — the
        message, and then ACCEPTED.json, would be read and written through a link a session planted."""
        moved = self.root / "records-elsewhere"
        self.records.rename(moved)
        self.records.symlink_to(moved)
        (moved / "commit-message.txt").write_text(EDITED)
        err = self.assert_direct_refused("message-unreadable", "--message", str(self.message_path()), message=None)
        self.assertNotIn("record-unwritable", err)


class DirectConfigHookTests(DirectCase):
    """L31 · a config hook only the build's worktree reads (its config.worktree) does not run when accept.sh --direct
    checks that worktree's status (gate F2)."""

    def test_direct__a_hook_in_the_worktrees_own_config_does_not_run_on_its_status(self):
        """L31 extensions.worktreeConfig on, `hook.pic` on post-index-change in the worktree's config.worktree only, a
        tracked file touched so status rewrites the index: the accept integrates and no marker exists."""
        markers = self.root / "markers"
        markers.mkdir()
        program = self.root / "hook-pic"
        program.write_text(f"#!/bin/sh\ntouch '{markers / 'pic'}'\n")
        program.chmod(0o755)
        self.git(self.main, "config", "extensions.worktreeConfig", "true")
        self.git(self.worktree, "config", "--worktree", "hook.pic.event", "post-index-change")
        self.git(self.worktree, "config", "--worktree", "hook.pic.command", str(program))
        tracked = next(p for p in self.worktree.iterdir() if p.is_file() and p.name != ".git")
        os.utime(tracked, (1, 1))

        code, _, err = self.direct()

        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(p.name for p in markers.iterdir()), [])


class DirectGitTests(DirectCase):
    """X6–X7 · -S reaches the commit; every git call carries the overrides."""

    def test_direct__dash_s_reaches_commit_tree_and_signs(self):
        """X6 `--direct -S` runs commit-tree with -S and main's new commit carries a signature — this repository's main tip must be signed."""
        SignTests.given_ssh_signing(self)
        code, _, err = self.direct("-S")
        self.assertEqual(code, 0, err)
        self.assertEqual([("-S" in c) for c in git_calls(self.log) if subcommand(c) == "commit-tree"], [True])
        self.assertIn("gpgsig", self.git(self.main, "cat-file", "commit", "main"))

    def test_direct__every_git_call_carries_the_overrides(self):
        """X7 every git --direct runs starts with the fsmonitor, hooksPath, pager and showSignature overrides — the merge would run the main clone's post-merge hook as the Owner."""
        code, _, err = self.direct()
        self.assertEqual(code, 0, err)
        calls = git_calls(self.log)
        self.assertIn("merge", [subcommand(c) for c in calls])
        for call in calls:
            self.assertEqual(call[:len(HARDENING)], HARDENING, call)


class ImportPathTests(AcceptCase):
    """L26 · accept.sh run from the main clone's root never imports a module from it."""

    def test_accept__a_main_holding_a_module_named_like_the_standard_librarys_is_accepted_from_the_main_clone(self):
        """L26 main and the branch holding a `json.py` that is not Python, accept.sh run from the main clone, integrates and records the accept — a file the build put in main would run as the Owner on the next accept."""
        (self.main / "json.py").write_text(NOT_PYTHON)
        self.git(self.main, "add", "json.py")
        self.git(self.main, "commit", "-q", "-m", "a module named like the standard library's")
        self.git(self.worktree, "rebase", "-q", "main")
        self.given_session(phase="done")
        code, _, err = self.accept(cwd=self.main)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.run_json()["accepted"]["sha"], self.git(self.main, "rev-parse", "main"))


class TargetTests(AcceptCase):
    """L27–L28 · accept.sh runs from outside the clone it rewrites, and keeps the message out of the temp folder."""

    def test_accept__an_accept_sh_inside_the_main_clone_is_refused(self):
        """L27 the main clone's own accept.sh is refused accept-in-target naming the installed path, nothing changed — after the fast-forward it would run the build's scripts as the Owner."""
        script = self.given_accept_scripts_in_the_main_clone()
        self.given_session(phase="done")
        before = self.snapshot()
        done = subprocess.run(["bash", str(script), "--tip", self.branch_tip(), "--message", str(self.message_file(EDITED)), str(self.dir)],
                              capture_output=True, text=True, env=self.accept_env(), cwd=self.main)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("refused: accept-in-target: ", done.stderr)
        self.assertIn(INSTALLED, done.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_accept__the_message_never_goes_through_the_temp_folder(self):
        """L28 with TMPDIR a folder nothing may write, the accept integrates the message and the folder stays empty — a message file there can be swapped by a live session between display and commit (adversarial-4 F11)."""
        scratch = self.given_unwritable_tmpdir()
        done = subprocess.run(["bash", str(ACCEPT), "--tip", self.branch_tip(), "--message", str(self.message_file(EDITED)), str(self.dir)],
                              capture_output=True, text=True, env=dict(self.accept_env(), TMPDIR=str(scratch)), cwd=self.tmp.name)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.git(self.main, "log", "-1", "--format=%B", "main").strip(), EDITED.strip())
        self.assertEqual(sorted(p.name for p in scratch.iterdir()), [])


class DirectImportPathTests(DirectCase):
    """X12–X13, X20–X23 · accept.sh --direct never imports a module the build put in its cwd, runs from outside the clone it
    rewrites, and keeps the message out of the temp folder."""

    def test_direct__a_build_shipping_modules_named_like_the_standard_librarys_is_accepted_from_the_main_clone(self):
        """X12 a branch adding a `json.py` and a `datetime.py` that are not Python, accepted from the main clone, integrates and writes its record — the fast-forward puts the build's files in the cwd, and the record writer would run them as the Owner."""
        for name in ("json.py", "datetime.py"):
            self.commit(self.worktree, name, NOT_PYTHON.strip())
        self.tip = self.git(self.main, "rev-parse", BRANCH)
        code, _, err = self.direct(cwd=self.main)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.record()["sha"], self.git(self.main, "rev-parse", "main"))

    def test_direct__already_accepted_names_the_recorded_commit_from_the_main_clone(self):
        """X13 an existing record naming main's tip, with main holding a `json.py` that is not Python, is refused already-accepted naming that commit, from the main clone — reading the record would run main's file as the Owner."""
        (self.main / "json.py").write_text(NOT_PYTHON)
        self.git(self.main, "add", "json.py")
        self.git(self.main, "commit", "-q", "-m", "a module named like the standard library's")
        recorded = self.git(self.main, "rev-parse", "main")
        (self.records / "ACCEPTED.json").write_text(json.dumps({"sha": recorded}) + "\n")
        code, _, err = self.direct(cwd=self.main)
        self.assertEqual(code, 2, err)
        self.assertIn(f"refused: already-accepted: {self.records / 'ACCEPTED.json'} exists, naming {recorded}", err)


    def given_accept_scripts_in_the_main_clone(self):
        """The base moves to the commit adding accept.sh's scripts; returns the clone's own accept.sh."""
        script = super().given_accept_scripts_in_the_main_clone()
        self.base = self.git(self.main, "rev-parse", "main")
        return script

    def assert_refused_in_target(self, script):
        before = self.direct_snapshot()
        code, _, err = self.direct(cwd=self.main, script=script)
        self.assertEqual(code, 2, err)
        self.assertIn("refused: accept-in-target: ", err)
        self.assertIn(INSTALLED, err)
        self.assertEqual(self.direct_snapshot(), before)

    def test_direct__an_accept_sh_inside_the_main_clone_is_refused(self):
        """X21 the main clone's own accept.sh --direct is refused accept-in-target naming the installed path, nothing changed — after the fast-forward it would run the build's scripts as the Owner."""
        self.assert_refused_in_target(self.given_accept_scripts_in_the_main_clone())

    def test_direct__an_accept_sh_inside_a_worktree_of_the_main_clone_is_refused(self):
        """X22 the branch's worktree's accept.sh --direct is refused accept-in-target — that copy is the build's own (assumed Q6)."""
        self.given_accept_scripts_in_the_main_clone()
        self.assert_refused_in_target(self.worktree / "skills" / "lead" / "scripts" / "accept.sh")

    def test_direct__a_link_outside_the_clone_to_its_accept_sh_is_refused(self):
        """X23 a link outside every checkout naming the main clone's accept.sh is refused accept-in-target — the check would read the link's own path."""
        script = self.given_accept_scripts_in_the_main_clone()
        link = self.root / "installed" / "accept.sh"
        link.parent.mkdir()
        link.symlink_to(script)
        self.assert_refused_in_target(link)

    def test_direct__an_accept_sh_inside_a_main_clone_with_a_separate_git_dir_is_refused(self):
        """X24 the main clone's own accept.sh is refused accept-in-target when its git dir lives elsewhere (`--separate-git-dir`) — `worktree list` names the git dir, not the clone, for the main entry (adversarial-5 F12)."""
        script = self.given_accept_scripts_in_the_main_clone()
        self.git(self.main, "init", "-q", f"--separate-git-dir={self.root / 'store.git'}")
        self.git(self.main, "worktree", "repair")
        self.assert_refused_in_target(script)

    def test_direct__the_message_never_goes_through_the_temp_folder(self):
        """X20 with TMPDIR a folder nothing may write, the accept integrates the message and the folder stays empty — a message file there can be swapped by a live session between display and commit (adversarial-4 F11)."""
        scratch = self.given_unwritable_tmpdir()
        env = dict(self.accept_env(), TMPDIR=str(scratch))
        args = ["--message", str(self.message_file(EDITED)), "--direct", "--base", self.base, "--tip", self.tip,
                str(self.folder), SLUG]
        done = subprocess.run(["bash", str(ACCEPT), *args], capture_output=True, text=True, env=env, cwd=self.tmp.name)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.git(self.main, "log", "-1", "--format=%B", "main").strip(), EDITED.strip())
        self.assertEqual(sorted(p.name for p in scratch.iterdir()), [])


class DirectBesideTests(DirectCase):
    """X14–X16 · main edited beside the change: the same change, merged with no attribute the checkouts name."""

    def given_edits_beside_each_other(self):
        """notes.txt at a new base; the branch, rebased onto it, edits line 6; main then edits line 3."""
        (self.main / "notes.txt").write_text(NOTES)
        self.git(self.main, "add", "notes.txt")
        self.git(self.main, "commit", "-q", "-m", "notes: eight lines")
        self.base = self.git(self.main, "rev-parse", "main")
        self.git(self.worktree, "rebase", "-q", "main")
        (self.worktree / "notes.txt").write_text(NOTES.replace("line 6\n", "line six\n"))
        self.git(self.worktree, "commit", "-q", "-am", "notes: spell out six")
        self.tip = self.git(self.main, "rev-parse", BRANCH)
        (self.main / "notes.txt").write_text(NOTES.replace("line 3\n", "line three\n"))
        self.git(self.main, "commit", "-q", "-am", "notes: spell out three")

    def test_direct__says_the_patch_id_is_the_same_when_main_edited_beside_the_change(self):
        """X14 main editing line 3 after the branch edited line 6 integrates and prints `patch-id: same` (assumed Q6) — every accept onto a busy main would warn DIFFERENT for the reviewed change."""
        self.given_edits_beside_each_other()
        code, out, err = self.direct()
        self.assertEqual(code, 0, err)
        self.assertIn("patch-id: same", out)

    def test_direct__the_merge_runs_no_driver_the_checkout_names(self):
        """X15 a `.gitattributes` on main naming a merge driver that always fails for notes.txt leaves the merge clean — the merge would run a driver main's checkout names, as the Owner."""
        self.given_edits_beside_each_other()
        (self.main / ".gitattributes").write_text("notes.txt merge=refuses\n")
        self.git(self.main, "add", ".gitattributes")
        self.git(self.main, "commit", "-q", "-m", "attributes: a merge driver for notes")
        self.git(self.main, "config", "merge.refuses.driver", "false")
        code, _, err = self.direct()
        self.assertEqual(code, 0, err)
        self.assertNotIn("range-conflicts", err)

    def test_direct__the_worktree_check_runs_no_filter_the_build_names(self):
        """X16 the branch's `.gitattributes` naming a required clean filter that always fails, defined in the worktree's own config, with title.txt stat-dirty, still passes the worktree check — the status would run a filter the build names, as the Owner."""
        (self.worktree / ".gitattributes").write_text("title.txt filter=refuses\n")
        self.git(self.worktree, "add", ".gitattributes")
        self.git(self.worktree, "commit", "-q", "-m", "attributes: a filter for the title")
        self.tip = self.git(self.main, "rev-parse", BRANCH)
        self.git(self.main, "config", "extensions.worktreeConfig", "true")
        self.git(self.worktree, "config", "--worktree", "filter.refuses.clean", "false")
        self.git(self.worktree, "config", "--worktree", "filter.refuses.required", "true")
        later = (self.worktree / "title.txt").stat().st_mtime + 3600
        os.utime(self.worktree / "title.txt", (later, later))
        code, _, err = self.direct()
        self.assertEqual(code, 0, err)


class DirectTagTests(DirectCase):
    """X17 · only a branch is the branch."""

    def test_direct__a_tag_named_like_the_branch_holds_no_branch(self):
        """X17 a second trusted repository the project names, holding a tag named `refs/heads/robowright/<slug>`, leaves the accept to the main clone's branch — a tag would block the accept as ambiguous, or stand in for a branch no worktree check reaches."""
        other = self.root / "other"
        other.mkdir()
        self.git(other, "init", "-q", "-b", "main")
        self.git(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "other")
        self.git(other, "tag", f"refs/heads/{BRANCH}")
        self.given_configured(self.main, other)
        self.given_allowlisted(self.main, other)
        code, out, err = self.direct()
        self.assertEqual(code, 0, err)
        self.assertIn(f"in {self.main}", out)


if __name__ == "__main__":
    unittest.main()
