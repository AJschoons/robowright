#!/usr/bin/env python3
"""Tests for run-launch.sh that the session-state suite beside it does not pin: the refusals, the
ledger lines, the session marker, the resume prompt's opener and the document roles' model source.

Driven against a scratch HOME holding a synthetic launch.json, a scratch git repo and worktree,
and a stub `claude` on PATH. Nothing here starts a real session: a `--dry-run` asserts the plan
the Lead reads, and a `--yes` runs the stub, which records its argv.

    python3 tests/run-launch/test_run_launch.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/robowright/scripts"
LAUNCHER = SCRIPTS / "run-launch.sh"
STATE_TOOL = SCRIPTS / "session-state.py"
# macOS /bin/bash is 3.2, which is what the launcher is written for.
BASH = "/bin/bash" if Path("/bin/bash").exists() else "bash"
GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
OLD_ID = "aaaa1111-0000-4000-8000-000000000000"
NEW_ID = "bbbb2222-0000-4000-8000-000000000000"
# `~/` so the launcher's expansion of a home-relative root is exercised on every test.
LAUNCH_CONFIG = {
    "schema": 1,
    "sessions_root": "~/sessions",
    "review_guide_dir": "reviews",
    "report_scope": "project-prefix",
    "launch": "auto",
    "unit": {
        "ticket_regex": None,
        "ticket_example": None,
        "slug_regex": "^[a-z0-9]+(-[a-z0-9]+)*-[0-9]{3}(-[a-z0-9]+)+$",
        "slug_example": "sample-012-note-autosave",
        "group_regex": "^([0-9]*[a-z][a-z0-9]*(-[0-9]*[a-z][a-z0-9]*)*)-[0-9]{3}(-[a-z0-9]+)+$",
    },
}


HARDENING = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "log.showSignature=false"]
ARGV_FIELD = "\x1f"
RECORDING_GIT = f"""#!/bin/sh
for a in "$@"; do printf '%s{ARGV_FIELD}' "$a"; done >> "$RECORDED_GIT_ARGV"
printf '\\n' >> "$RECORDED_GIT_ARGV"
exec {shutil.which("git")} "$@"
"""


def git_calls(log):
    return [line.split(ARGV_FIELD)[:-1] for line in Path(log).read_text().splitlines()] if Path(log).is_file() else []


def hint_call(call):
    """A git call a refusal's hint may run: `check-ref-format`, which reads a string; owner_git.argv's config hook read
    before it, which reads only config; or the `--attr-source` probe at `-C /`."""
    return ("check-ref-format" in call or call[-4:] == ["config", "--null", "--get-regexp", "^hook\\."]
            or "-C" in call and call[call.index("-C") + 1] == "/")


def runs_in(call, path):
    """A call that runs git inside `path`: `-C <path>` among its global options."""
    return any(call[i] == "-C" and os.path.realpath(call[i + 1]) == os.path.realpath(path) for i in range(len(call) - 1))


class LauncherCase(unittest.TestCase):
    """A scratch HOME (which moves the sessions root and the session registry), a repo with one
    linked worktree, a session dir under the sessions root, and a `claude` stub on PATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # $TMPDIR is a symlink on macOS and the launcher resolves paths with `pwd -P`; an
        # unresolved HOME would put the sessions root on the other side of the symlink.
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        (self.home / ".claude/sessions").mkdir(parents=True)
        (self.home / ".claude/robowright").mkdir(parents=True)
        self.owner_repos = []
        self.given_launch_json(LAUNCH_CONFIG)
        self.runs_root = self.home / "sessions"
        self.runs_root.mkdir(parents=True)
        self.stub_calls = self.root / "argv.txt"
        stub = self.root / "bin"
        stub.mkdir()
        self.claude = stub / "claude"
        self.given_owner_repos(self.root / "repo")
        self.set_stub('printf "%%s\\n" "$@" >> "%s"\necho "backgrounded · bbbb2222 · worker"' % self.stub_calls)
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            PATH=f"{stub}:{os.environ['PATH']}",
        )
        # A launch writes the launch index and a resume writes the ledger; both resolve their root from
        # these first, so an inherited one would point a test at the Owner's files.
        for name in ("ROBOWRIGHT_ACCOUNTING_ROOT", "ROBOWRIGHT_SESSIONS_ROOT", "CLAUDE_USAGE_DIR"):
            self.env.pop(name, None)
        self.run_dir = self.runs_root / "sample-001-x"
        self.run_dir.mkdir()
        self.clock = 0

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------ given

    def given_launch_json(self, config):
        """launch.json as `config` says, its `repos` the repositories given_owner_repos configured unless `config` names its own."""
        config = dict({"repos": self.owner_repos}, **config)
        (self.home / ".claude/robowright/launch.json").write_text(json.dumps(config, indent=2) + "\n")

    def given_owner_repos(self, *repos):
        """The repositories the Owner configured, through $ROBOWRIGHT_PROJECTS_ROOT: the launcher runs git only in a worktree one of them lists."""
        projects = self.root / "owner-projects"
        (projects / "sample").mkdir(parents=True, exist_ok=True)
        entries = [{"name": f"repo-{i}", "path": str(r)} for i, r in enumerate(repos)]
        (projects / "sample" / "robowright.json").write_text(json.dumps({"repos": entries}) + "\n")
        self.owner_repos = [str(r) for r in repos]
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
        self.given_launch_json({k: v for k, v in config.items() if k != "repos"})
        if os.environ.get("ROBOWRIGHT_PROJECTS_ROOT") != str(projects):
            previous = os.environ.get("ROBOWRIGHT_PROJECTS_ROOT")
            os.environ["ROBOWRIGHT_PROJECTS_ROOT"] = str(projects)
            self.addCleanup(lambda: os.environ.pop("ROBOWRIGHT_PROJECTS_ROOT", None) if previous is None
                            else os.environ.__setitem__("ROBOWRIGHT_PROJECTS_ROOT", previous))

    def given_recording_git(self):
        """A `git` on the launcher's PATH that records each call's argv and runs the real git."""
        (self.root / "bin" / "git").write_text(RECORDING_GIT)
        (self.root / "bin" / "git").chmod(0o755)
        log = self.root / "git-argv.log"
        self.env["RECORDED_GIT_ARGV"] = str(log)
        return log

    def set_stub(self, body):
        self.claude.write_text("#!/bin/bash\n%s\n" % body)
        self.claude.chmod(0o755)

    def given_worktree(self, ignore_claude=True):
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(GIT + ["init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True)
        worktree = self.root / "worktrees" / "wt"
        worktree.parent.mkdir()
        subprocess.run(GIT + ["worktree", "add", "-q", "-b", "robowright/sample-001-x", str(worktree)], cwd=repo, check=True, capture_output=True)
        if ignore_claude:
            (worktree / ".gitignore").write_text(".claude/\n")
            subprocess.run(GIT + ["add", "-A"], cwd=worktree, check=True, capture_output=True)
            subprocess.run(GIT + ["commit", "-q", "-m", "ignore"], cwd=worktree, check=True, capture_output=True)
        self.worktree = worktree
        return worktree

    def given_run(self, unit_ids=("U1", "U2"), unit_fields=(), **fields):
        run = {
            "phase": "preflight",
            "delegation": "planner",
            "max_gate_attempts": 3,
            "rotate_sessions": True,
            "rotate": None,
            "rebriefs": [],
            "stop_reason": None,
            "worktree": str(self.worktree),
            "units": [{"id": i, "status": "todo", "head": "", "gate_attempts": 0, "gate": {"review": ""}} for i in unit_ids],
        }
        run.update(fields)
        for unit, extra in zip(run["units"], unit_fields):
            unit.update(extra)
        (self.run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        (self.run_dir / "BRIEF.md").write_text("brief\n")
        (self.run_dir / "reviews").mkdir(exist_ok=True)

    def rewrite_run(self, **fields):
        run = dict(self.run_json(), **fields)
        (self.run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")

    def given_implementing(self, **kwargs):
        self.given_run(**kwargs)
        self.must("preflight-pass")
        self.must("intake-complete")

    def given_unit_closed(self, unit):
        self.must("unit-start", "--unit", unit)
        review = self.run_dir / "reviews" / f"{unit}-gate.md"
        review.write_text("ADVANCE\n\nfindings\n")
        self.clock += 5
        stamp = time.time() + self.clock
        os.utime(review, (stamp, stamp))
        self.must("gate-advance", "--unit", unit)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", unit], cwd=self.worktree, check=True, capture_output=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.worktree, check=True, capture_output=True, text=True).stdout.strip()
        self.must("unit-close", "--unit", unit, "--head", head)

    def given_project(self, **role_models):
        project = self.root / "project"
        project.mkdir(exist_ok=True)
        (project / "PROJECT.md").write_text("# plan\n")
        if role_models:
            (project / "robowright.json").write_text(json.dumps({"models": role_models}))
        self.project = project
        return project

    # ------------------------------------------------------------ when

    def must(self, *args):
        done = subprocess.run([sys.executable, str(STATE_TOOL), str(self.run_dir), *args], capture_output=True, text=True,
                              env=self.env)
        self.assertEqual(done.returncode, 0, f"{args}: {done.stderr}")
        return done.stdout

    def launch(self, *flags, cwd=None, env=None):
        """Run the launcher and return (exit code, output with printf %q's backslashes dropped)."""
        done = subprocess.run(
            [BASH, str(LAUNCHER), "--run-dir", str(self.run_dir), *flags],
            env=env or self.env, cwd=cwd, capture_output=True,
        )
        out = (done.stdout + done.stderr).decode(errors="replace")
        return done.returncode, out.replace("\\", "")

    def plan(self, *flags, **kwargs):
        return self.launch("--dry-run", *flags, **kwargs)

    def start(self, *flags):
        """Run the launcher for real against the stub; returns the argv the stub was handed."""
        self.stub_calls.write_text("")
        code, out = self.launch("--yes", *flags)
        self.assertEqual(code, 0, out)
        return self.stub_calls.read_text().splitlines(), out

    def doc_plan(self, *flags):
        done = subprocess.run([BASH, str(LAUNCHER), *flags, "--project", str(self.project), "--dry-run"], env=self.env, capture_output=True)
        out = (done.stdout + done.stderr).decode(errors="replace")
        return done.returncode, out.replace("\\", "")

    def doc_start(self, *flags):
        """A document-only launch for real against the stub, so the file it appends to is observable."""
        self.stub_calls.write_text("")
        done = subprocess.run([BASH, str(LAUNCHER), *flags, "--project", str(self.project), "--yes"], env=self.env, capture_output=True)
        out = (done.stdout + done.stderr).decode(errors="replace")
        return done.returncode, out.replace("\\", "")

    def given_dead_pid(self):
        """A pid that has exited and been reaped — `kill -0` on it is ESRCH, not EPERM."""
        dead = subprocess.Popen([BASH, "-c", "exit 0"])
        dead.wait()
        return dead.pid

    # ------------------------------------------------------------ then

    def run_json(self):
        return json.loads((self.run_dir / "run.json").read_text())

    def ledger(self):
        return (self.run_dir / "LEDGER.md").read_text()


class ResumeTests(LauncherCase):
    def test_launcher__the_resume_prompt_re_invokes_the_worker_skill(self):
        """A skill's hooks register when the skill is invoked and a resumed process starts with none: a resume that only pointed at LEDGER.md would run with the stop gate disarmed. The worker handbook's Phase 0 reads `Resume this Robowright Session` after the session dir as the resume marker, so the opener is a contract, not prose."""
        self.given_worktree()
        self.given_implementing(session_id=OLD_ID)
        code, out = self.plan("--resume")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"--resume=\S+ /worker " + re.escape(str(self.run_dir)) + r" Resume this Robowright Session:")


class DocumentOnlyTests(LauncherCase):
    def test_launcher__robowright_json_outranks_the_profile_and_the_flag_outranks_robowright_json(self):
        """robowright.json is where a project pins a role's model, and the profile is only the answer when it does not — a profile that overrode the file would make the pin unwritable, and a flag that lost to it would make a one-off unreachable."""
        self.given_project(planner="sonnet")
        code, out = self.doc_plan("--brief", "--slug", "sample-003-z")
        self.assertEqual(code, 0, out)
        self.assertIn("model:     sonnet (from robowright.json)", out)
        code, out = self.doc_plan("--brief", "--slug", "sample-003-z", "--model", "haiku")
        self.assertEqual(code, 0, out)
        self.assertIn("model:     haiku (from flag)", out)

    def test_launcher__the_report_prompt_sends_the_explainer_to_the_manual_smoke_pass(self):
        """The manual pass is the authority on what was verified by hand and what was not; a report written from INTAKE.md alone claims a confidence nobody checked."""
        self.given_project()
        code, out = self.doc_plan("--explainer", "report")
        self.assertEqual(code, 0, out)
        self.assertIn("smoke/MANUAL-PASS.md", out)


class RefusalTests(LauncherCase):
    def test_launcher__a_stop_file_refuses_the_launch(self):
        """A STOP file is how the Owner halts a Robowright Session; a launch over one spends a
        session that the session's own preflight stops again immediately."""
        self.given_worktree()
        self.given_run()
        (self.run_dir / "STOP").write_text("")
        code, out = self.plan()
        self.assertEqual(code, 1, out)
        self.assertIn("STOP exists", out)
        (self.run_dir / "STOP").unlink()
        self.assertEqual(self.plan()[0], 0, self.plan()[1])

    def test_launcher__a_live_session_in_the_worktree_refuses_the_launch(self):
        """Two sessions in one worktree commit over each other, and the live one may be the
        Owner's own; a session record whose process is gone is not a reason to refuse."""
        self.given_worktree()
        self.given_run()
        record = self.home / ".claude/sessions/live.json"
        record.write_text(json.dumps({"name": "worker-opus-sample-001-x", "cwd": str(self.worktree), "pid": os.getpid(), "sessionId": NEW_ID, "status": "idle"}))
        code, out = self.plan()
        self.assertEqual(code, 1, out)
        self.assertIn("a live Claude session is already in %s" % self.worktree, out)
        record.write_text(json.dumps({"name": "worker-opus-sample-001-x", "cwd": str(self.worktree), "pid": self.given_dead_pid(), "sessionId": NEW_ID, "status": "idle"}))
        self.assertEqual(self.plan()[0], 0, self.plan()[1])

    def test_launcher__the_worktree_must_be_a_linked_worktree_not_the_main_clone(self):
        """A run.json that names the main clone would have an unattended session committing to
        whatever branch the Owner left checked out there."""
        self.given_worktree()
        self.given_run()
        self.rewrite_run(worktree=str(self.root / "repo"))
        code, out = self.plan()
        self.assertEqual(code, 1, out)
        self.assertIn("never the main clone", out)

    def test_launcher__compact_pct_must_be_a_percentage(self):
        """The value goes straight into CLAUDE_AUTOCOMPACT_PCT_OVERRIDE: a junk or out-of-range
        percentage is a context window that compacts at a size nobody chose, and the plan would
        print it as if it were the setting."""
        self.given_worktree()
        self.given_run()
        # The two refusals are asserted apart: a range test that accepted either message would
        # leave the "whole number" guard uncovered, since a non-numeric value fails the range
        # comparison too — with a message about bounds it never had.
        for bad in ("fifty", "50%"):
            code, out = self.plan("--compact-pct", bad)
            self.assertEqual(code, 1, out)
            self.assertIn("--compact-pct must be a whole number of percent", out)
        for bad in ("9", "101"):
            code, out = self.plan("--compact-pct", bad)
            self.assertEqual(code, 1, out)
            self.assertIn("--compact-pct must be between 10 and 100", out)
        code, out = self.plan("--compact-pct", "10")
        self.assertEqual(code, 0, out)
        self.assertIn("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=10", out)
        self.rewrite_run(compact_pct="lots")
        code, out = self.plan()
        self.assertEqual(code, 1, out)
        self.assertIn("--compact-pct must be a whole number of percent", out)

    def test_launcher__stop_cap_must_be_a_whole_number(self):
        """The value goes straight into CLAUDE_CODE_STOP_HOOK_BLOCK_CAP, which is what holds an
        unattended session to the stop contract; a non-numeric cap is whatever Claude Code makes of
        it — plausibly zero blocks, so the session ends its turn at the first Stop — and neither the
        plan nor the ledger would say the cap was junk."""
        self.given_worktree()
        self.given_run()
        code, out = self.plan("--stop-cap", "forty")
        self.assertEqual(code, 1, out)
        self.assertIn("--stop-cap must be a whole number", out)
        code, out = self.plan("--stop-cap", "60")
        self.assertEqual(code, 0, out)
        self.assertIn("CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=60", out)
        # Checked before the launch splits, so a document-only launch is refused the same way.
        self.given_project()
        code, out = self.doc_plan("--brief", "--slug", "sample-003-z", "--stop-cap", "forty")
        self.assertEqual(code, 1, out)
        self.assertIn("--stop-cap must be a whole number", out)

    def test_launcher__the_launch_writes_the_session_marker_into_the_worktree(self):
        """The marker is how every hook in the worktree finds the session dir it belongs to; a
        session started without it runs with no stop gate, no budget file and no cost record. A
        plan that starts nothing writes nothing."""
        self.given_worktree()
        self.given_run()
        marker = self.worktree / ".claude/autonomous-run"
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertFalse(marker.exists(), "a plan that starts nothing wrote the session marker")
        self.start()
        self.assertEqual(marker.read_text().strip(), str(self.run_dir))


class OwnerGitTests(LauncherCase):
    """The worktree run.json names is one a configured repository lists, and every git in it is hardened."""

    def test_launcher__refuses_a_worktree_no_configured_repository_lists_before_git_runs_inside_it(self):
        """W1 · a linked worktree of a repository no robowright.json names is refused, naming worktree-unlisted, on --dry-run too, and no git runs inside it — its fsmonitor would run as the Owner on the launcher's `git status`."""
        self.given_worktree()
        self.given_run()
        self.given_owner_repos(self.root / "some-other-clone")
        log = self.given_recording_git()

        code, out = self.plan()

        self.assertNotEqual(code, 0, out)
        self.assertIn("refused: worktree-unlisted: ", out)
        self.assertIn(str(self.worktree), out)
        self.assertEqual([c for c in git_calls(log) if runs_in(c, self.worktree)], [])

    def test_launcher__refuses_a_named_worktree_when_launch_json_has_no_repos_and_says_what_to_add(self):
        """W3 · with launch.json holding no `repos`, a worktree robowright.json names is refused repos-unconfigured on --dry-run, no git runs inside it, and the refusal names the file and prints the `"repos": [...]` line — the first launch after this change would fail with no word on how to fix it."""
        self.given_worktree()
        self.given_run()
        (self.home / ".claude/robowright/launch.json").write_text(json.dumps(LAUNCH_CONFIG, indent=2) + "\n")
        log = self.given_recording_git()

        code, out = self.plan()

        self.assertNotEqual(code, 0, out)
        self.assertIn("refused: repos-unconfigured: ", out)
        self.assertIn(str(self.home / ".claude/robowright/launch.json"), out)
        self.assertIn(f'"repos": [{json.dumps(str(self.root / "repo"))}]', out)
        self.assertEqual([c for c in git_calls(log) if runs_in(c, self.worktree)], [])

    def test_launcher__every_git_call_in_the_worktree_carries_the_overrides(self):
        """W2 · each git the launcher runs inside a listed worktree starts with the fsmonitor, hooksPath, pager and showSignature overrides — `status` would run the worktree's configured fsmonitor."""
        self.given_worktree()
        self.given_run()
        log = self.given_recording_git()

        code, out = self.plan()

        self.assertEqual(code, 0, out)
        inside = [c for c in git_calls(log) if runs_in(c, self.worktree)]
        self.assertIn("status", [a for c in inside for a in c])
        for call in inside:
            self.assertEqual(call[:len(HARDENING)], HARDENING, call)


class SteeredValueTests(LauncherCase):
    """A Robowright Session writes its own run.json, so the values a later launch reads back from
    it are held to the shape this install gives them before a path, a name or a prompt is built
    from them."""

    def given_launch_config(self, **unit):
        config = dict(LAUNCH_CONFIG, unit=dict(LAUNCH_CONFIG["unit"], **unit))
        self.given_launch_json(config)

    def refusal(self, out):
        """The launcher's `refusing:` line, or "" when it printed none."""
        return next((line for line in out.splitlines() if line.startswith("refusing:")), "")

    def test_launcher__a_run_json_ticket_that_is_not_one_path_segment_is_refused_before_a_path_or_name_is_built_from_it(self):
        """The ticket is the unit id the owner-brief path and every session name are built from, and a `../` ticket a session wrote into its own run.json sent the guide Explainer to write outside the project folder."""
        self.given_worktree()
        self.given_project()
        for ticket in ("../../../../.config/x", "..", ".hidden", "a//b", "sample 001 x", "-rf"):
            with self.subTest(launch="worker", ticket=ticket):
                self.given_run(ticket=ticket)
                code, out = self.plan()
                self.assertEqual(code, 1, out)
                self.assertIn("run.json", self.refusal(out), out)
                self.assertIn("ticket", self.refusal(out), out)
                self.assertNotIn("command:", out)
        self.given_run(phase="done", ticket="../../../../.config/x")
        (self.run_dir / "INTAKE.md").write_text("intake\n")
        for mode in (("--explainer", "guide"), ("--planner", "review")):
            with self.subTest(launch=mode):
                code, out = self.plan(*mode, "--project", str(self.project))
                self.assertEqual(code, 1, out)
                self.assertIn("run.json", self.refusal(out), out)
                self.assertIn("ticket", self.refusal(out), out)
                self.assertNotIn("guide:", out)
                self.assertNotIn("owner-brief.md", out)
                self.assertNotIn("command:", out)
        # Inside the ticket form the ticket is the unit id; with none, the directory's name still is.
        self.given_run(ticket="sample_001.x-2")
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn("(sample_001.x-2, phase", out)
        self.given_run()
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn("(sample-001-x, phase", out)

    def test_launcher__where_launch_json_names_a_ticket_shape_a_run_json_ticket_outside_it_is_refused(self):
        """A run.json ticket is held to launch.json's ticket_regex, and to the ticket form as well, so a ticket_regex with no closing anchor lets no path through."""
        self.given_worktree()
        # No trailing `$`: a hand-written pattern that stops at the key, as both example group_regex values did.
        self.given_launch_config(ticket_regex="^[A-Z][A-Z0-9]+-[0-9]+", ticket_example="ABC-1234")
        for ticket in ("sample-001-x", "ABC-1/../../../x"):
            with self.subTest(ticket=ticket):
                self.given_run(ticket=ticket)
                code, out = self.plan()
                self.assertEqual(code, 1, out)
                self.assertIn("run.json", self.refusal(out), out)
                self.assertIn("ticket", self.refusal(out), out)
                self.assertNotIn("command:", out)
        self.given_run(ticket="ABC-1")
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn("(ABC-1, phase", out)

    def test_launcher__a_ticket_flag_outside_the_ticket_form_is_refused_even_where_launch_json_s_ticket_shape_admits_it(self):
        """A brief started with a ticket that run.json's read-back refuses would write a session no later launch accepts, so the --ticket flag is held to the ticket form as well as to unit.ticket_regex."""
        self.given_project()
        self.given_launch_config(ticket_regex="^#?[0-9]+$", ticket_example="#42", slug_regex="^[a-z0-9]+(-[a-z0-9]+)*$", slug_example="fix")
        code, out = self.doc_plan("--planner", "brief", "--slug", "fix", "--ticket", "#42")
        self.assertEqual(code, 1, out)
        self.assertIn("--ticket", self.refusal(out), out)
        self.assertNotIn("command:", out)
        code, out = self.doc_plan("--planner", "brief", "--slug", "fix", "--ticket", "42")
        self.assertEqual(code, 0, out)
        self.assertIn("42-fix", out)

    def test_launcher__a_stop_code_outside_the_state_machine_s_six_is_refused_where_it_is_read(self):
        """The rebrief prompt and the Worker's plan carry run.json's stop code verbatim, and only the six names state-machine.json defines are one, so `budget; rm -rf ~` is refused by its key rather than handed to a Planner or left to the state tool's own complaint."""
        self.given_worktree()
        self.given_project()
        rebrief = ("--planner", "rebrief", "--project", str(self.project))
        self.given_run()
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.must("stop", "--code", "budget", "--detail", "wall hours")
        code, out = self.plan(*rebrief)
        self.assertEqual(code, 0, out)
        # A stopped session is still not a Worker launch; what refuses it is the state, not its code.
        code, out = self.plan()
        self.assertEqual(code, 1, out)
        self.assertIn("check-op launch", out)
        self.rewrite_run(stop_reason=dict(self.run_json()["stop_reason"], code="budget; rm -rf ~"))
        for flags in (rebrief, ()):
            with self.subTest(launch=flags or "worker"):
                code, out = self.plan(*flags)
                self.assertEqual(code, 1, out)
                self.assertIn("run.json", self.refusal(out), out)
                self.assertIn("stop_reason.code", self.refusal(out), out)
                self.assertNotIn("command:", out)


class LedgerTests(LauncherCase):
    def test_launcher__the_plan_names_the_file_the_entry_is_actually_appended_to(self):
        """A report Explainer is launched in the project folder and its entry goes to
        DECISIONS.md; a plan that names LEDGER.md sends the Lead to a file the launch never
        writes — and on a project folder without one, to a file that will never exist."""
        self.given_project()
        code, out = self.doc_plan("--explainer", "report")
        self.assertEqual(code, 0, out)
        self.assertIn("ledger:    %s/DECISIONS.md" % self.project, out)
        self.assertNotIn("LEDGER.md", out)
        code, out = self.doc_start("--explainer", "report")
        self.assertEqual(code, 0, out)
        self.assertIn("launched", (self.project / "DECISIONS.md").read_text())
        self.assertFalse((self.project / "LEDGER.md").exists())
        # Every other document-only mode does write the session dir's ledger.
        code, out = self.doc_plan("--brief", "--slug", "sample-003-z")
        self.assertEqual(code, 0, out)
        self.assertIn("ledger:    %s/sample-003-z/LEDGER.md" % self.runs_root, out)

    def test_launcher__a_dry_run_does_not_claim_an_entry_was_appended(self):
        """`--dry-run` is mandatory before every launch, so the plan is what the Lead reads
        most often: one that says an entry was appended has them record a launch that never
        happened, and the ledger tail the next roster tick prints is the previous session's."""
        self.given_worktree()
        self.given_run()
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn("ledger:    %s/LEDGER.md (dry run: nothing appended)" % self.run_dir, out)
        self.assertFalse((self.run_dir / "LEDGER.md").exists())
        argv, out = self.start()
        self.assertIn("ledger:    %s/LEDGER.md (one entry will be appended)" % self.run_dir, out)
        self.assertIn("via run-launch.sh", self.ledger())
        # The document-only plan has the same two wordings.
        self.given_project()
        code, out = self.doc_plan("--brief", "--slug", "sample-003-z")
        self.assertEqual(code, 0, out)
        self.assertIn("(dry run: nothing appended)", out)
        code, out = self.doc_start("--brief", "--slug", "sample-003-z")
        self.assertEqual(code, 0, out)
        self.assertIn("(one entry will be appended)", out)

    def test_launcher__a_resume_records_the_id_it_resumed_not_a_name_it_invented(self):
        """A resume passes no `--name`: the session keeps the one it was launched with. The name the
        launcher recomputes is built from the *current* model, so once units name their own models a
        resume would record a session that was never created — `claude attach` and SendMessage
        addressing both miss it — while the id that does work is only in the background-id line."""
        self.given_worktree()
        self.given_run(unit_fields=({"model": "opus"}, {"model": "sonnet"}), session_id=OLD_ID)
        self.start()
        self.assertIn("- session name: worker-opus-sample-001-x", self.ledger())
        self.must("preflight-pass")
        self.must("intake-complete")
        self.given_unit_closed("U1")
        self.must("stop", "--code", "verification-failed", "--detail", "why")
        self.must("resume", "--by", "owner", "--decision", "take route B")
        argv, out = self.start("--resume")
        self.assertIn("model:     sonnet Worker (from unit U2)", out)
        self.assertIn("- resumed session: %s" % OLD_ID, self.ledger())
        self.assertNotIn("worker-sonnet-sample-001-x", self.ledger())


class LaunchModeTests(LauncherCase):
    """launch.json's `launch` key through the stub: `auto` runs the command the plan printed,
    `paste` hands that same command off unrun, and an EPERM under `auto` is still a hand-off whose
    hint names no settings key. The config reading itself (the default, the refusals, the plan's
    `launch:` line) is pinned by the session-state suite's LaunchConfigTests."""

    HINT = 'hint: this shell could not start a background session; see the machine profile\'s Launch section, or set "launch": "paste" in %s'

    def setUp(self):
        super().setUp()
        # One NUL after each argument, so an argument holding a newline cannot pass for two.
        self.set_stub('printf "%%s\\0" "$@" >> "%s"\necho "backgrounded · bbbb2222 · worker"' % self.stub_calls)

    def given_launch_mode(self, mode):
        self.given_launch_json(dict(LAUNCH_CONFIG, launch=mode))
        return self.home / ".claude/robowright/launch.json"

    def given_eperm_stub(self):
        self.set_stub('printf "%%s\\0" "$@" >> "%s"\necho "Error: EPERM: operation not permitted, mkdir \'/home/owner/.claude/bg\'" >&2\nexit 1' % self.stub_calls)

    def launch_unedited(self, *flags):
        """The launcher with `flags`, its stdout and stderr apart and printf %q's quoting kept."""
        return subprocess.run([BASH, str(LAUNCHER), *flags], env=self.env, capture_output=True, text=True, errors="replace")

    def stub_argv(self):
        return self.stub_calls.read_text().split("\0")[:-1] if self.stub_calls.is_file() else []

    @staticmethod
    def words(quoted):
        """The words bash reads from a line the launcher printed with printf %q."""
        done = subprocess.run([BASH, "-c", "printf '%s\\0' " + quoted], capture_output=True, text=True, check=True)
        return done.stdout.split("\0")[:-1]

    def planned_command(self, stdout):
        found = re.search(r"^command:  (.*)$", stdout, re.M)
        self.assertIsNotNone(found, stdout)
        return self.words(found.group(1))

    def test_launcher__auto_starts_the_session_with_the_command_the_plan_printed(self):
        """`auto` is today's only behaviour: the Lead approves the plan's command and the launcher runs exactly that — a mode switch that edited the command on its way to `claude` would start a session nobody read (R5.1; green before the mode exists, assumed Q9)."""
        self.given_worktree()
        self.given_run()
        self.given_launch_mode("auto")

        done = self.launch_unedited("--run-dir", str(self.run_dir), "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(["claude"] + self.stub_argv(), self.planned_command(done.stdout))
        self.assertIn("started. attach:", done.stdout)
        self.assertNotIn("hand-off via", self.ledger())

    def test_launcher__paste_hands_off_the_command_the_plan_printed_without_running_it(self):
        """`paste` is the EPERM hand-off with the `claude` call skipped, so the line the Owner pastes has to be the command the Lead approved, started in the worktree with CLAUDECODE unset — any other line starts a session the plan never showed (R5.2)."""
        self.given_worktree()
        self.given_run()
        self.given_launch_mode("paste")

        done = self.launch_unedited("--run-dir", str(self.run_dir), "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.stub_argv(), [], "claude was invoked under paste")
        planned = self.planned_command(done.stdout)
        pasted = re.search(r'^paste this yourself:\s*cd (.*?) && \[ "\$\(pwd -P\)" = (.*?) \] && (.*)$', done.stdout, re.M)
        self.assertIsNotNone(pasted, done.stdout)
        self.assertEqual(self.words(pasted.group(1)), [str(self.worktree)])
        self.assertEqual(self.words(pasted.group(2)), [str(self.worktree)])
        pasted_words = self.words(pasted.group(3))
        self.assertEqual(pasted_words[:3], ["env", "-u", "CLAUDECODE"], pasted.group(2))
        self.assertEqual(pasted_words[-len(planned):], planned, pasted.group(2))

    def test_launcher__an_eperm_under_auto_at_the_worker_site_hints_at_the_launch_section_not_a_settings_key(self):
        """Under `auto` an EPERM still means this shell could not start the session, and it is still a hand-off; the hint sends the Lead to the profile's Launch section or to `paste`, because which settings key unblocks a shell is one install's fact, not the launcher's (R5.3, assumed Q5)."""
        self.given_worktree()
        self.given_run()
        config = self.given_launch_mode("auto")
        self.given_eperm_stub()

        done = self.launch_unedited("--run-dir", str(self.run_dir), "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(done.stdout.rstrip().endswith("launch is yours"), done.stdout)
        self.assertIn(self.HINT % config + "\n", done.stderr)
        self.assertNotIn("excludedCommands", done.stderr)
        self.assertNotIn("sandbox", done.stderr)
        self.assertEqual(self.ledger().count("\n- EPERM; nothing started\n"), 1, self.ledger())
        self.assertNotIn("launch: paste", self.ledger())

    def test_launcher__an_eperm_under_auto_at_the_document_only_site_hints_at_the_launch_section_too(self):
        """The document-only site prints the same hint on the same refusal — the two hint lines are the two places the old settings key was named (R5.4, assumed Q5)."""
        self.given_project()
        config = self.given_launch_mode("auto")
        self.given_eperm_stub()

        done = self.launch_unedited("--planner", "brief", "--slug", "sample-003-z", "--project", str(self.project), "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(done.stdout.rstrip().endswith("launch is yours"), done.stdout)
        self.assertIn(self.HINT % config + "\n", done.stderr)
        self.assertNotIn("excludedCommands", done.stderr)
        self.assertNotIn("sandbox", done.stderr)
        ledger = (self.runs_root / "sample-003-z/LEDGER.md").read_text()
        self.assertIn("EPERM; nothing started", ledger)
        self.assertNotIn("launch: paste", ledger)


class ProjectTests(LauncherCase):
    """run.json.project is the group_regex capture of the unit id the launcher already read, written
    once so every ledger record of the Robowright Session names the same project (accounting U1)."""

    def given_config(self, **keys):
        self.given_launch_json(dict(LAUNCH_CONFIG, **keys))

    def test_launcher__a_launch_writes_the_group_regex_capture_of_the_ticket_as_project__when_run_json_has_none(self):
        """A record copies run.json.project, so a session launched with none names no project in any rollup; `sample-013-ledger` under the example group_regex is project `sample` (D8; an absent key read as null, assumed Q16)."""
        self.given_worktree()
        for state, fields in (("null", {"project": None}), ("absent", {})):
            with self.subTest(project=state):
                self.given_run(ticket="sample-013-ledger", **fields)
                self.start()
                self.assertEqual(self.run_json().get("project"), "sample")

    def test_launcher__a_project_already_set_is_left_alone(self):
        """A project the Owner or an earlier launch set is the session's name in every record already written; overwriting it splits one session's rows over two projects (D8: "when null")."""
        self.given_worktree()
        self.given_run(ticket="sample-013-ledger", project="demo")

        self.start()

        self.assertEqual(self.run_json()["project"], "demo")

    def test_launcher__a_ticket_outside_group_regex_leaves_project_null_and_the_launch_goes_on(self):
        """A unit id this install's group_regex does not match has no project to capture; the launch is still the Owner's to make, and a guessed project is a wrong row (assumed Q15)."""
        self.given_worktree()
        self.given_config(unit=dict(LAUNCH_CONFIG["unit"], group_regex="^(other)-[0-9]{3}(-[a-z0-9]+)+$"))
        self.given_run(ticket="sample-013-ledger", project=None)

        self.start()

        self.assertIsNone(self.run_json()["project"])

    def test_launcher__a_paste_hand_off_leaves_project_null(self):
        """A hand-off starts nothing, and session-state's launcher contract is that it leaves run.json byte-for-byte as the Lead approved it; the project is written as pin_session writes, once a session started (D8; Q14 settled against test_session_state.py)."""
        self.given_worktree()
        self.given_config(launch="paste")
        self.given_run(ticket="sample-013-ledger", project=None)

        code, out = self.launch("--yes")

        self.assertEqual(code, 0, out)
        self.assertIsNone(self.run_json()["project"])

    def test_launcher__a_dry_run_writes_no_project(self):
        """`--dry-run` is the plan the Lead reads before every launch and starts nothing; it writes nothing, as it writes no session marker (assumed Q13; green before the unit exists)."""
        self.given_worktree()
        self.given_run(ticket="sample-013-ledger", project=None)

        code, out = self.plan()

        self.assertEqual(code, 0, out)
        self.assertIsNone(self.run_json()["project"])


class AccountingRootConfigTests(LauncherCase):
    """launch.json's optional `accounting_root`: absent is fine, present must be a filled string (accounting U1)."""

    def given_accounting_root(self, *value):
        config = dict(LAUNCH_CONFIG)
        if value:
            config["accounting_root"] = value[0]
        self.given_launch_json(config)

    def refusal(self, out):
        return next((line for line in out.splitlines() if line.startswith("refusing:")), "")

    def test_launcher__an_empty_or_non_string_accounting_root_is_refused_by_name(self):
        """An empty root is what a half-written launch.json leaves, and read as a path it puts the ledger in whatever directory a script runs from; the refusal names the key so the Owner knows which line to fix (launch.json rule; null present, assumed Q17)."""
        self.given_worktree()
        self.given_run()
        for bad in ("", 5, None):
            with self.subTest(accounting_root=bad):
                self.given_accounting_root(bad)
                code, out = self.plan()
                self.assertEqual(code, 1, out)
                self.assertIn("accounting_root", self.refusal(out), out)
                self.assertNotIn("command:", out)

    def test_launcher__accounting_root_absent_or_a_filled_path_is_accepted(self):
        """Every install written before this unit has no accounting_root, and schema 1 is not bumped for it; refusing its absence would stop every launch on those installs (launch.json rule; green before the unit exists)."""
        self.given_worktree()
        self.given_run()
        for state, value in (("absent", ()), ("filled", ("~/accounting",))):
            with self.subTest(accounting_root=state):
                self.given_accounting_root(*value)
                code, out = self.plan()
                self.assertEqual(code, 0, out)


# ================================================================== U3 · the launch index and the previous session's ledger records
#
# Written from the accounting brief's evidence/U3-behaviors.md before either existed.

INDEX_FIELDS = ("session_id", "role", "project", "unit", "session_dir", "model")


class LaunchIndexTests(LauncherCase):
    """<accounting_root>/launches.jsonl: one line per session the launcher started in `auto` mode."""

    def setUp(self):
        super().setUp()
        self.accounting = self.root / "accounting"
        self.env["ROBOWRIGHT_ACCOUNTING_ROOT"] = str(self.accounting)
        # The stub registers the session it "started", as `claude --bg` does, so the launcher can read the full id back.
        self.set_stub(
            'printf "%%s\\n" "$@" >> "%s"\n'
            'printf \'{"sessionId": "%s", "cwd": "%%s"}\\n\' "$PWD" > "$HOME/.claude/sessions/bbbb2222.json"\n'
            'echo "backgrounded · bbbb2222 · worker"' % (self.stub_calls, NEW_ID))

    def given_config(self, **keys):
        self.given_launch_json(dict(LAUNCH_CONFIG, **keys))

    def given_launchable(self):
        self.given_worktree()
        self.given_run(ticket="sample-013-ledger", project=None, model="opus")

    def index_lines(self, root=None):
        path = (root or self.accounting) / "launches.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_launcher__an_auto_launch_appends_one_launch_index_line_naming_the_started_session(self):
        """The index is how a record learns which unit and session dir a session belonged to when its own marker cannot say; a line naming the wrong id enriches nobody (Language: launch index; U3 row; project and model, assumed Q17, Q18)."""
        self.given_launchable()

        self.start()

        lines = self.index_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual({k: lines[0].get(k) for k in INDEX_FIELDS}, {
            "session_id": NEW_ID, "role": "worker", "project": "sample", "unit": "sample-013-ledger",
            "session_dir": str(self.run_dir), "model": "opus"})

    def test_launcher__the_launch_index_line_is_stamped_with_an_offset_timestamp(self):
        """`at` is compared with record and event times written with an offset (assumed Q27)."""
        self.given_launchable()

        self.start()

        lines = self.index_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIsNotNone(datetime.fromisoformat(lines[0]["at"]).utcoffset())

    def test_launcher__never_appends_its_launch_index_line_through_a_link(self):
        """SW-20: the accounting root sits inside the sandbox grant; the index is best effort, so the launch goes ahead."""
        self.given_launchable()
        self.accounting.mkdir()
        target = self.root / "target-launches"
        target.write_text(OWNER_TEXT)
        (self.accounting / "launches.jsonl").symlink_to(target)

        argv, out = self.start()

        self.assertNotEqual(argv, [])
        self.assertEqual(target.read_text(), OWNER_TEXT)
        self.assertIn("could not append", out)

    def test_launcher__a_paste_hand_off_appends_no_launch_index_line(self):
        """A hand-off starts nothing and the launcher never learns the session id, so there is no session to index (U3 row: "none in paste"; D6)."""
        self.given_launchable()
        self.given_config(launch="paste")

        code, out = self.launch("--yes")

        self.assertEqual(code, 0, out)
        self.assertEqual(list(self.root.rglob("launches.jsonl")), [])

    def test_launcher__a_planner_launch_under_auto_appends_its_line_with_its_role_unit_and_session_dir(self):
        """A doc role has no run.json; its index line is the only place its unit and session dir are written down (D6; Language: "one line per session the launcher started"; assumed Q16, Q17)."""
        self.given_project()

        code, out = self.doc_start("--brief", "--slug", "sample-003-z")

        self.assertEqual(code, 0, out)
        lines = self.index_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual({k: lines[0].get(k) for k in ("session_id", "role", "project", "unit", "session_dir")}, {
            "session_id": NEW_ID, "role": "planner", "project": "sample", "unit": "sample-003-z",
            "session_dir": str(self.runs_root / "sample-003-z")})

    def test_launcher__the_launch_index_goes_under_launch_json_s_accounting_root__without_the_environment(self):
        """The index sits beside the ledger its readers open; a launcher resolving another root writes an index nothing reads (Language: accounting root)."""
        self.env.pop("ROBOWRIGHT_ACCOUNTING_ROOT")
        self.given_config(accounting_root="~/ledger-home")
        self.given_launchable()

        self.start()

        self.assertEqual(len(self.index_lines(self.home / "ledger-home")), 1)

    def test_launcher__the_launch_index_defaults_beside_the_sessions_root(self):
        """With no accounting_root anywhere the root is <sessions_root>/../accounting, the same default the ledger's writer uses (Language: accounting root)."""
        self.env.pop("ROBOWRIGHT_ACCOUNTING_ROOT")
        self.given_launchable()

        self.start()

        self.assertEqual(len(self.index_lines(self.home / "accounting")), 1)

    def test_launcher__the_launch_index_defaults_beside_the_sessions_root_s_real_directory(self):
        """run-cost.py resolves a symlinked sessions root to its target; an index beside the link's parent is one no record reads (U3 gate F2)."""
        self.env.pop("ROBOWRIGHT_ACCOUNTING_ROOT")
        (self.root / "elsewhere").mkdir()
        (self.root / "elsewhere/sessions").symlink_to(self.home / "sessions")
        self.env["ROBOWRIGHT_SESSIONS_ROOT"] = str(self.root / "elsewhere/sessions")
        self.given_launchable()

        self.start()

        self.assertEqual(len(self.index_lines(self.home / "accounting")), 1)

    def test_launcher__a_launch_index_that_cannot_be_written_never_fails_the_launch(self):
        """The index is an enrichment; a launch the Lead approved still starts when it cannot be written (assumed Q20)."""
        not_a_dir = self.root / "not-a-dir"
        not_a_dir.write_text("a file where the accounting root should be\n")
        self.env["ROBOWRIGHT_ACCOUNTING_ROOT"] = str(not_a_dir)
        self.given_launchable()

        code, out = self.launch("--yes")

        self.assertEqual(code, 0, out)
        self.assertNotEqual(self.stub_calls.read_text(), "")
        self.assertIn("started.", out)


def previous_session_transcript():
    """Two opus requests of the session a --resume or --rotate replaces."""
    lines = []
    for msg_id, at in (("msg_q1", "2026-09-20T09:00:00.000Z"), ("msg_q2", "2026-09-20T09:20:00.000Z")):
        lines.append(json.dumps({
            "type": "assistant", "timestamp": at, "uuid": f"uuid-{msg_id}",
            "message": {"id": msg_id, "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                        "content": [{"type": "text", "text": "ok"}],
                        "usage": {"input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 10000,
                                  "cache_creation_input_tokens": 0}},
        }))
    return "\n".join(lines) + "\n"


class PreviousSessionLedgerTests(LauncherCase):
    """`claude stop` runs no SessionEnd hook, so a --rotate, or a --resume of another id, is the last moment
    the replaced session's records can reach the ledger (carried from the U1 gate; assumed Q21; U3 gate F1)."""

    def setUp(self):
        super().setUp()
        self.accounting = self.root / "accounting"
        self.env["ROBOWRIGHT_ACCOUNTING_ROOT"] = str(self.accounting)

    def given_previous_session(self):
        """run.json names OLD_ID and pins its transcript as pin_session writes it; U1 is closed."""
        self.given_worktree()
        project_dir = re.sub(r"[^A-Za-z0-9]", "-", str(self.worktree))
        transcript = self.home / ".claude/projects" / project_dir / f"{OLD_ID}.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(previous_session_transcript())
        self.given_implementing(ticket="sample-001-x", project="sample", session_id=OLD_ID,
                                transcripts=[f"~/.claude/projects/{project_dir}/{OLD_ID}.jsonl"])
        self.given_unit_closed("U1")

    def given_resumable(self):
        self.given_previous_session()
        self.must("stop", "--code", "verification-failed", "--detail", "why")
        self.must("resume", "--by", "owner", "--decision", "take route B")

    def previous_session_records(self):
        path = self.accounting / "records.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []
        return [(r["role"], r["model"], r["requests"]) for r in records
                if r.get("scope") == "session" and r.get("session_id") == OLD_ID]

    def test_launcher__a_resume_of_the_same_session_appends_nothing__its_own_end_records_it(self):
        """`--resume` continues the same session id; a record now would make the ledger skip everything it does after (U3 gate F1)."""
        self.given_resumable()

        self.start("--resume")

        self.assertEqual(self.previous_session_records(), [])

    def test_launcher__a_resume_of_another_session_appends_the_replaced_session_s_records(self):
        """A stopped session never ran its hook; resuming a different id replaces it, so its requests reach the ledger now (assumed Q21)."""
        self.given_resumable()

        self.start("--resume", "bbbb2222-0000-4000-8000-000000000000")

        self.assertEqual(self.previous_session_records(), [("worker", "claude-opus-5-5", 2)])

    def test_launcher__a_rotation_appends_the_previous_session_s_records_to_the_ledger(self):
        """A rotation replaces a session that ended without its hook just as a resume does (assumed Q21)."""
        self.given_previous_session()
        self.must("request-rotate")

        self.start("--rotate")

        self.assertEqual(self.previous_session_records(), [("worker", "claude-opus-5-5", 2)])

    def test_launcher__a_ledger_that_cannot_be_written_never_fails_a_resume(self):
        """Recording the replaced session is best effort; the Owner's resume of another id still starts, and says why nothing was recorded (Landmine: "--ledger there is best effort and never fails a launch")."""
        not_a_dir = self.root / "not-a-dir"
        not_a_dir.write_text("a file where the accounting root should be\n")
        self.env["ROBOWRIGHT_ACCOUNTING_ROOT"] = str(not_a_dir)
        self.given_resumable()
        self.stub_calls.write_text("")

        code, out = self.launch("--yes", "--resume", "bbbb2222-0000-4000-8000-000000000000")

        self.assertEqual(code, 0, out)
        self.assertNotEqual(self.stub_calls.read_text(), "")
        self.assertIn("could not append the previous session's records", out)


# ================================================================== P2 · project on --pin, a soft capture after launch, the desktop regex
#
# Written from the accounting polish's evidence/P2-behaviors.md before any of it existed.

PASTED_ID = "cccc3333-0000-4000-8000-000000000000"
# No parentheses: matches every unit id and folder name below and captures nothing.
CAPTURELESS_GROUP_REGEX = "^[a-z][a-z0-9-]*$"
DESKTOP_EXAMPLE = Path(__file__).resolve().parents[2] / "examples/desktop/launch.json"


class PinProjectTests(LauncherCase):
    """`--pin` is the one moment a paste install learns the session id, so it writes run.json.project
    as a started launch does: the group_regex capture of the unit id, once (P2 R1–R3)."""

    def given_pasted(self, group_regex=None, **fields):
        """A paste install whose hand-off was pasted: the session is registered and runs in the worktree."""
        unit = dict(LAUNCH_CONFIG["unit"], **({"group_regex": group_regex} if group_regex else {}))
        self.given_launch_json(dict(LAUNCH_CONFIG, launch="paste", unit=unit))
        self.given_worktree()
        self.given_run(ticket="sample-013-ledger", **fields)
        (self.home / ".claude/sessions" / f"{PASTED_ID[:8]}.json").write_text(json.dumps({"sessionId": PASTED_ID, "cwd": str(self.worktree)}))

    def pin(self, *flags):
        return self.launch("--pin", PASTED_ID[:8], *flags)

    def test_launcher__a_pin_writes_the_group_regex_capture_of_the_ticket_as_project__when_run_json_has_none(self):
        """On a paste install the pin is the only write after the session starts; without it every Worker record carries project null (P2.1: C1, D8)."""
        self.given_pasted(project=None)

        code, out = self.pin()

        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_json()["project"], "sample")

    def test_launcher__a_pin_leaves_a_project_already_set_alone(self):
        """A set project names every record already written; a pin that overwrote it would split one session's rows over two projects (P2.2: C1 "leaves a set value alone")."""
        self.given_pasted(project="demo")

        code, out = self.pin()

        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_json()["project"], "demo")

    def test_launcher__a_pin_whose_ticket_is_outside_group_regex_still_pins_and_leaves_project_null(self):
        """A unit id in no group has no project to name, and the pasted session still needs its id pinned for --resume and the cost reader (P2.3: C1, U1 Q15)."""
        self.given_pasted(group_regex="^(other)-[0-9]{3}(-[a-z0-9]+)+$", project=None)

        code, out = self.pin()

        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_json().get("session_id"), PASTED_ID)
        self.assertIsNone(self.run_json()["project"])

    def test_launcher__a_pin_under_a_group_regex_that_captures_nothing_still_pins_and_leaves_project_null(self):
        """The pin runs after the pasted session started, like the post-launch captures; refusing there leaves the session unpinned (P2.4: assumed P2 Q1)."""
        self.given_pasted(group_regex=CAPTURELESS_GROUP_REGEX, project=None)

        code, out = self.pin()

        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_json().get("session_id"), PASTED_ID)
        self.assertIsNone(self.run_json()["project"])

    def test_launcher__a_pin_dry_run_writes_no_project(self):
        """The dry run is how the Lead checks a pin before taking it, and it says "nothing written" (P2.5: the dry-run line)."""
        self.given_pasted(project=None)

        code, out = self.pin("--dry-run")

        self.assertEqual(code, 0, out)
        self.assertIn("would pin", out)
        self.assertIsNone(self.run_json()["project"])


class CapturelessGroupRegexTests(LauncherCase):
    """A group_regex that matches with no capture, met after `claude --bg` has started, leaves the
    project unnamed and the launch finishes as it did before the capture moved after the start (P2 R5, R6)."""

    def setUp(self):
        super().setUp()
        self.accounting = self.root / "accounting"
        self.env["ROBOWRIGHT_ACCOUNTING_ROOT"] = str(self.accounting)
        # The stub registers the session it "started", as `claude --bg` does, so the launcher can read the full id back.
        self.set_stub(
            'printf "%%s\\n" "$@" >> "%s"\n'
            'printf \'{"sessionId": "%s", "cwd": "%%s"}\\n\' "$PWD" > "$HOME/.claude/sessions/bbbb2222.json"\n'
            'echo "backgrounded · bbbb2222 · worker"' % (self.stub_calls, NEW_ID))
        unit = dict(LAUNCH_CONFIG["unit"], group_regex=CAPTURELESS_GROUP_REGEX)
        self.given_launch_json(dict(LAUNCH_CONFIG, unit=unit))

    def index_lines(self):
        path = self.accounting / "launches.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []

    def test_launcher__an_auto_launch_under_a_group_regex_that_captures_nothing_finishes_with_project_null(self):
        """The Worker is already running when the capture is read; exiting there leaves a live session with no launch entry and no `started.` line (P2.6: C3)."""
        self.given_worktree()
        self.given_run(ticket="sample-013-ledger", project=None)

        code, out = self.launch("--yes")

        self.assertEqual(code, 0, out)
        self.assertIn("started. attach: claude attach bbbb2222", out)
        self.assertRegex(self.ledger(), r"(?m)^## .* — launch via run-launch\.sh$")
        self.assertIsNone(self.run_json()["project"])

    def test_launcher__an_auto_launch_under_a_group_regex_that_captures_nothing_still_indexes_the_session_with_no_project(self):
        """The index line is how the session's records find their unit and dir; a launch without a project is still a started session (P2.7: C3, U3 row)."""
        self.given_worktree()
        self.given_run(ticket="sample-013-ledger", project=None)

        code, out = self.launch("--yes")

        self.assertEqual(code, 0, out)
        lines = self.index_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual({k: lines[0].get(k) for k in ("session_id", "role", "project", "unit")}, {
            "session_id": NEW_ID, "role": "worker", "project": None, "unit": "sample-013-ledger"})

    def test_launcher__a_planner_launch_under_a_group_regex_that_captures_nothing_finishes_and_indexes_the_folder_name(self):
        """A doc role's project is the folder it ran in when the capture names none; the Planner is already running when it is read (P2.8: C3, assumed P2 Q2)."""
        self.given_worktree()
        self.given_run(ticket="sample-013-ledger", phase="done")
        (self.run_dir / "INTAKE.md").write_text("intake\n")
        self.given_project()

        code, out = self.doc_start("--planner", "review", "--run-dir", str(self.run_dir))

        self.assertEqual(code, 0, out)
        self.assertIn("planner launched (review, ", self.ledger())
        lines = self.index_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual({k: lines[0].get(k) for k in ("role", "project", "unit")}, {
            "role": "planner", "project": "project", "unit": "sample-013-ledger"})


class DesktopExampleRegexTests(LauncherCase):
    """The desktop example's group_regex names a Worker's project from the bare tracker key in
    run.json.ticket and still groups keyed session dirs for intake inheritance (P2 R8)."""

    def desktop_unit(self):
        return json.loads(DESKTOP_EXAMPLE.read_text())["unit"]

    def test_launcher__the_desktop_group_regex_captures_the_tracker_prefix_from_a_bare_key_and_a_keyed_dir_name(self):
        """A ticket install's run.json.ticket is the bare key; a regex that needs a slug names no project for any Worker there (P2.9: C5)."""
        regex = self.desktop_unit()["group_regex"]
        for name in ("SMPL-482", "SMPL-482-export-csv"):
            with self.subTest(name=name):
                done = subprocess.run([BASH, "-c", '[[ "$1" =~ $2 ]] && printf "%s" "${BASH_REMATCH[1]}"', "match", name, regex],
                                      capture_output=True, text=True)
                self.assertEqual((done.returncode, done.stdout), (0, "SMPL"), done.stderr)

    def test_launcher__under_the_desktop_unit_block_a_brief_still_inherits_its_tracker_prefix_s_keyed_intake(self):
        """A new brief reads its group's newest intake; a regex that stopped matching keyed dir names would hand it none (P2.10: C5 "`latest_intake` still matches `SMPL-482-export-csv`")."""
        self.given_launch_json(dict(LAUNCH_CONFIG, unit=self.desktop_unit()))
        (self.runs_root / "SMPL-482-export-csv").mkdir()
        (self.runs_root / "SMPL-482-export-csv/INTAKE.md").write_text("intake\n")
        self.given_project()

        code, out = self.doc_plan("--planner", "brief", "--ticket", "SMPL-500", "--slug", "import-csv")

        self.assertEqual(code, 0, out)
        self.assertIn("intake:    %s/SMPL-482-export-csv/INTAKE.md\n" % self.runs_root, out)



class TicketlessTests(LauncherCase):
    """TL rows (BEHAVIORS.md): under the desktop example's ticket shape, a run.json with no ticket takes the session
    directory's name as its unit id, held to the install's unit form, and a Worker launch still names its project."""

    def setUp(self):
        super().setUp()
        self.unit = json.loads(DESKTOP_EXAMPLE.read_text())["unit"]
        self.given_launch_json(dict(LAUNCH_CONFIG, unit=self.unit))
        self.accounting = self.root / "accounting"
        self.env["ROBOWRIGHT_ACCOUNTING_ROOT"] = str(self.accounting)
        self.set_stub(
            'printf "%%s\\n" "$@" >> "%s"\n'
            'printf \'{"sessionId": "%s", "cwd": "%%s"}\\n\' "$PWD" > "$HOME/.claude/sessions/bbbb2222.json"\n'
            'echo "backgrounded · bbbb2222 · worker"' % (self.stub_calls, NEW_ID))

    def given_session_dir(self, name):
        self.run_dir = self.runs_root / name
        self.run_dir.mkdir(exist_ok=True)

    def refusal(self, out):
        return next((line for line in out.splitlines() if line.startswith("refusing:")), "")

    def index_lines(self):
        path = self.accounting / "launches.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []

    def test_launcher__a_session_with_no_ticket_launches_under_a_ticket_shape_named_by_its_directory(self):
        """TL-1: the Owner's decision (allow no ticket) — no ticket falls back to the directory-name unit form."""
        self.given_worktree()
        self.given_run(ticket=None, project="sample", model="opus")

        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn("(sample-001-x, phase", out)

        argv, out = self.start()
        self.assertEqual(argv[argv.index("--name") + 1], "worker-opus-sample-001-x", out)
        lines = self.index_lines()
        self.assertEqual([(line["unit"], line["project"]) for line in lines], [("sample-001-x", "sample")], lines)

    def test_launcher__a_malformed_ticket_is_still_refused_where_no_ticket_is_accepted(self):
        """TL-2: the Owner's decision — a ticket that is present but malformed is still refused; no ticket launches."""
        self.given_worktree()
        for ticket in ("sample-001-x", "ABC-1/../../../x"):
            with self.subTest(ticket=ticket):
                self.given_run(ticket=ticket, project="sample")
                code, out = self.plan()
                self.assertEqual(code, 1, out)
                self.assertIn("run.json", self.refusal(out), out)
                self.assertIn("ticket", self.refusal(out), out)
                self.assertNotIn("command:", out)
        self.given_run(ticket=None, project="sample")
        code, out = self.plan()
        self.assertEqual(code, 0, out)

    def test_launcher__a_ticketless_worker_launch_outside_every_group_needs_run_json_project(self):
        """TL-3: a ticket-less session must still be attributed to its project; with no ticket shape, a no-match
        launch goes on with project null as before."""
        self.given_worktree()
        self.given_session_dir("export-csv")
        # A project that is not a string names no project to any reader, so it counts as none.
        for project in (None, 7, ["sample"]):
            with self.subTest(project=project):
                self.given_run(ticket=None, project=project)
                code, out = self.plan()
                self.assertEqual(code, 1, out)
                self.assertIn("run.json.project", self.refusal(out), out)
                self.assertIn("group_regex", self.refusal(out), out)
                self.assertNotIn("command:", out)

        self.given_run(ticket=None, project="sample")
        code, out = self.plan()
        self.assertEqual(code, 0, out)

        self.given_launch_json(dict(LAUNCH_CONFIG, unit=dict(self.unit, ticket_regex=None, ticket_example=None)))
        self.given_run(ticket=None, project=None)
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIsNone(self.run_json()["project"])

    def test_launcher__a_ticketless_session_dir_in_a_group_takes_its_project_from_the_capture(self):
        """TL-4: a ticket-shaped directory name is unchanged — the group capture names the project."""
        self.given_worktree()
        self.given_session_dir("SMPL-482-export-csv")
        self.given_run(ticket=None, project=None)

        self.start()

        self.assertEqual(self.run_json()["project"], "SMPL")

    def test_launcher__planner_brief_takes_no_ticket_under_a_ticket_shape(self):
        """TL-5: --ticket is optional; with none the session dir is <root>/<slug>, and a bare slug in no group
        inherits no intake."""
        (self.runs_root / "SMPL-482-export-csv").mkdir()
        (self.runs_root / "SMPL-482-export-csv/INTAKE.md").write_text("intake\n")
        self.given_project()

        code, out = self.doc_plan("--planner", "brief", "--slug", "import-csv")

        self.assertEqual(code, 0, out)
        self.assertIn("import-csv → %s/import-csv\n" % self.runs_root, out)
        self.assertIn("--name planner-import-csv ", out)
        self.assertIn("intake:    none found", out)

    def test_launcher__a_session_dir_neither_a_slug_nor_ticket_slug_is_still_refused(self):
        """TL-7: a ticket-less name passes exactly the checks a no-regex install's name passes (SI-11)."""
        self.given_worktree()
        self.given_session_dir("Not-A-Unit_x")
        self.given_run(ticket=None, project="sample")

        code, out = self.plan()

        self.assertEqual(code, 1, out)
        self.assertIn("run.json", self.refusal(out), out)
        self.assertIn("'Not-A-Unit_x'", self.refusal(out), out)
        self.assertNotIn("command:", out)


REPO = Path(__file__).resolve().parents[2]
# A model value that closes the JSON string it is written into: enough to show the shape check, no payload.
QUOTED_MODEL = 'claude-x","z":{"a'


class SessionInputTests(LauncherCase):
    """Values a session can write reach a JSON blob, a flag or a printed command only in the shape
    the launcher gives them (BEHAVIORS.md, SI rows)."""

    def refusal(self, out):
        """The launcher's `refusing:` line, or "" when it printed none."""
        return next((line for line in out.splitlines() if line.startswith("refusing:")), "")

    def assert_refused(self, code, out, *words):
        self.assertEqual(code, 1, out)
        for word in words:
            self.assertIn(word, self.refusal(out), out)
        self.assertNotIn("command:", out)

    def test_launcher__a_model_outside_the_model_shape_is_refused_by_the_source_it_came_from(self):
        """SI-1: a model is written into the --settings JSON and passed as --model, so a quote, a space or a leading dash is refused before anything starts, and the refusal names the file or flag that needs editing."""
        self.given_worktree()
        for model in (QUOTED_MODEL, "-opus", "claude-x y"):
            sources = (
                ("flag", {}, ("--model", model)),
                ("brief", {"model": model}, ()),
                ("unit U1", {"unit_fields": ({"model": model},)}, ()),
                ("--subagent-model", {}, ("--subagent-model", model)),
            )
            for source, fields, flags in sources:
                with self.subTest(model=model, source=source):
                    self.given_run(**fields)
                    code, out = self.plan(*flags)
                    self.assert_refused(code, out, "model", source)
        self.given_project(planner=QUOTED_MODEL)
        code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
        self.assert_refused(code, out, "model", "robowright.json")
        self.given_run(model="claude-opus-5-5")
        code, out = self.plan()
        self.assertEqual(code, 0, out)

    def test_launcher__the_settings_blob_is_json_with_exactly_the_intended_keys(self):
        """SI-2: --settings outranks the user's own settings files, so the blob carries effort, the per-model effort, the three env variables and the write scope (WS rows), and nothing else.

        Declared guard for the encoder (bound 1): every value reaching the blob is shape-checked first (SI-1), so a printf builder with the right format would pass this too. It catches a blob that gains, loses or misnames a key."""
        self.given_worktree()
        self.given_run(model="opus", effort="high")
        argv, _ = self.start()
        blob = json.loads(argv[argv.index("--settings") + 1])
        self.assertEqual(set(blob), {"effortLevel", "modelSettings", "env", "permissions", "sandbox"})
        self.assertEqual(blob["effortLevel"], "high")
        self.assertEqual(blob["modelSettings"], {"claude-opus-5-5": {"effortLevel": "high"}})
        self.assertEqual(blob["env"], {"CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "40", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "85", "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"})

    def given_resumable(self, session_id):
        """An implementing session with a fresh event log, its run.json naming session_id."""
        (self.run_dir / "events.jsonl").unlink(missing_ok=True)
        self.given_implementing(session_id=session_id)

    def test_launcher__a_session_id_reaches_resume_only_as_a_uuid_and_as_one_argument(self):
        """SI-8: --resume takes an optional value, so a flag-shaped id would be read as the next flag; only a UUID is passed, joined to the flag with `=`."""
        self.given_worktree()
        for session_id in ("--version", "abc"):
            with self.subTest(session_id=session_id):
                self.given_resumable(session_id)
                code, out = self.plan("--resume")
                self.assert_refused(code, out, "session_id")
        self.given_resumable(OLD_ID)
        code, out = self.plan("--resume", "notauuid")
        self.assert_refused(code, out, "--resume")
        code, out = self.plan("--resume")
        self.assertEqual(code, 0, out)
        self.assertIn(" --resume=%s " % OLD_ID, out)

    def test_launcher__tools_is_a_comma_list_of_known_tool_names(self):
        """SI-10: `default` or an unknown name would widen the next session's tool set past the brief's own list, so only known built-in names, comma-joined, are passed."""
        self.given_worktree()
        for tools in ("default", "Bash,Nope", "Bash Read", ["Bash"], ""):
            with self.subTest(tools=tools):
                self.given_run(tools=tools)
                code, out = self.plan()
                self.assert_refused(code, out, "tools")
        self.given_run(tools="Bash,Read")
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn(" --tools Bash,Read ", out)

    def test_launcher__a_unit_id_taken_from_the_directory_name_must_be_a_unit_name(self):
        """SI-11: with no ticket, the session dir's name becomes the unit id that names the session and reaches a prompt, and any session can create a directory beside its own."""
        self.given_worktree()
        self.run_dir = self.runs_root / "Not-A-Unit_x"
        self.run_dir.mkdir()
        self.given_run()
        code, out = self.plan()
        self.assert_refused(code, out, "Not-A-Unit_x")
        self.run_dir = self.runs_root / "sample-001-x"
        self.given_run()
        code, out = self.plan()
        self.assertEqual(code, 0, out)

    def test_launcher__the_worktree_hint_quotes_its_branch_and_refuses_one_git_rejects(self):
        """SI-12: the hint is a command the reader pastes, and the branch in it comes from run.json."""
        self.worktree = self.root / "worktrees" / "gone"
        for branch, quoted in (("a;b", "a\\;b"), ("robowright/sample-001-x", "robowright/sample-001-x")):
            with self.subTest(branch=branch):
                self.given_run(unit_fields=({"branch": branch},))
                done = subprocess.run([BASH, str(LAUNCHER), "--run-dir", str(self.run_dir), "--dry-run"], env=self.env, capture_output=True, text=True)
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertIn("git worktree add -b %s " % quoted, done.stderr)
        self.given_run(unit_fields=({"branch": "a..b"},))
        code, out = self.plan()
        self.assert_refused(code, out, "branch")
        self.assertNotIn("git worktree add", out)

    def test_launcher__this_repo_ignores_the_session_marker(self):
        """SI-16: the marker names the session dir the hooks write to, and a committed one would arm them in every clone."""
        # A fresh repo holding only the tracked .gitignore: a clone's info/exclude or the user's global excludes would pass this for any tree.
        clone = self.root / "clone"
        subprocess.run(GIT + ["init", "-q", str(clone)], check=True, capture_output=True)
        (clone / ".gitignore").write_text((REPO / ".gitignore").read_text())
        done = subprocess.run(["git", "-C", str(clone), "-c", "core.excludesFile=/dev/null", "check-ignore", "-q", ".claude/autonomous-run"])
        self.assertEqual(done.returncode, 0)



class WriteScopeTests(LauncherCase):
    """WS rows (BEHAVIORS.md): what each role the launcher starts may write, read from the --settings blob it is handed."""

    def blob(self, argv):
        return json.loads(argv[argv.index("--settings") + 1])

    def git_dir(self, repo):
        """The repository's whole git directory: Claude Code's linked-worktree rule opens it to a Worker's shell (U46)."""
        return [str(Path(os.path.realpath(repo)) / ".git")]

    def edit_rules(self, repo):
        return [f"Edit(/{path}/**)" for path in self.git_dir(repo)]

    def leaves(self, *roots):
        """A leaf deny on each root: every `.git` under it, file or folder, at any depth (U46 bound 3)."""
        return [f"{root}/**/.git" for root in roots]

    def leaf_rules(self, *roots):
        return [rule for leaf in self.leaves(*roots) for rule in (f"Edit(/{leaf})", f"Edit(/{leaf}/**)")]

    def project_configs(self, projects):
        """What Claude Code loads as project settings from a folder (`.claude`, `.mcp.json`): the projects root's own and
        each project folder's, named, and through a wildcard for a folder made later (review 5 F3)."""
        folders = [projects] + sorted(c for c in projects.iterdir() if c.is_dir() and not c.is_symlink() and not c.name.startswith("."))
        named = [str(folder / name) for folder in folders for name in (".claude", ".mcp.json")]
        return named + [str(projects / "**" / ".claude"), str(projects / "**" / ".mcp.json")]

    def config_rules(self, paths):
        return [f"Edit(/{path}/**)" if path.endswith("/.claude") else f"Edit(/{path})" for path in paths]

    def given_second_repo(self, name="dep"):
        dep = self.root / name
        subprocess.run(GIT + ["init", "-q", str(dep)], check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=dep, check=True, capture_output=True)
        return dep

    def with_config(self, **keys):
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
        config.update(keys)
        self.given_launch_json(config)

    def test_launcher__a_worker_is_granted_its_session_folder_and_the_accounting_root_only(self):
        """WS-1: the Worker writes its ledger and run.json (C2, C3) and its unit's accounting records (C6); its worktree is its working directory. Nothing else is granted, so no other session's folder and no part of the projects root."""
        self.given_worktree()
        self.given_run()
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn("writes:    %s %s" % (self.run_dir, self.home / "accounting"), out)
        argv, _ = self.start()
        self.assertEqual(self.blob(argv)["permissions"]["additionalDirectories"], [str(self.run_dir), str(self.home / "accounting")])

    def test_launcher__a_worker_is_denied_the_main_clones_git_directory_and_runs_rw_git_outside_the_sandbox(self):
        """WS-2: Claude Code's linked-worktree rule opens the main clone's .git to the shell but for config and hooks; the
        index, refs and info/attributes are as dangerous. The Worker stages and commits through rw-git instead."""
        self.given_worktree()
        self.given_run()
        blob = self.blob(self.start()[0])
        leaves = self.leaves(self.worktree, self.run_dir, self.home / "accounting")
        self.assertEqual(blob["sandbox"], {"filesystem": {"denyWrite": self.git_dir(self.root / "repo") + leaves},
                                           "excludedCommands": ["rw-git *"]})
        self.assertEqual(blob["permissions"]["deny"], self.edit_rules(self.root / "repo")
                         + self.leaf_rules(self.worktree, self.run_dir, self.home / "accounting"))
        self.assertEqual(blob["permissions"].get("allow"), ["Bash(rw-git *)"])

    def test_launcher__a_lock_is_granted_as_its_lock_directory_only(self):
        """WS-3: a Worker takes each lock run.json names at <sessions root>/.<name>-lock (C7); granting the sessions root would hand it every other session's folder."""
        self.given_worktree()
        self.given_run(locks=["sim"])
        grants = self.blob(self.start()[0])["permissions"]["additionalDirectories"]
        self.assertIn(str(self.runs_root / ".sim-lock"), grants)
        self.assertNotIn(str(self.runs_root), grants)

    def test_launcher__the_launcher_makes_a_dependency_checkout_and_grants_no_admin_dir(self):
        """WS-4: `git worktree add` for a depends_on checkout writes the dependency repo's admin dir (C8), whose name git picks, so no grant can name it; the launcher makes the checkout on the Owner's side. run.json is session-written: the path must be a repository launch.json lists, the session one path segment, the ref a commit id, and `deps` no link."""
        self.given_worktree()
        dep = self.given_second_repo()
        self.given_owner_repos(self.root / "repo", dep)
        ref = subprocess.run(["git", "-C", str(dep), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        entry = {"session": "sample-000-dep", "repo": "dep", "path": str(dep), "ref": ref, "build_output": ""}
        self.given_run(depends_on=[entry])
        checkout = self.run_dir / "deps" / "sample-000-dep"
        self.assertEqual(self.plan()[0], 0)
        self.assertFalse(checkout.exists())
        blob = self.blob(self.start()[0])
        head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(head, ref)
        self.assertEqual(blob["permissions"]["additionalDirectories"], [str(self.run_dir), str(self.home / "accounting")])
        for path in self.git_dir(dep):
            self.assertIn(path, blob["sandbox"]["filesystem"]["denyWrite"])
        # The checkout is a worktree inside the session folder: every role's next launch must still be granted.
        for args in (["worker", str(self.run_dir), str(self.worktree)], ["document"]):
            done = subprocess.run([sys.executable, str(SCRIPTS / "role_grants.py"), *args], env=self.env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
        stray = self.given_second_repo("stray")
        for bad in (dict(entry, path=str(stray)), dict(entry, session="a/b"), dict(entry, ref="--orphan")):
            with self.subTest(entry=bad):
                self.given_run(depends_on=[bad])
                code, out = self.plan()
                self.assertEqual(code, 1, out)
                self.assertIn("depends_on", out)
                self.assertNotIn("command:", out)
        shutil.rmtree(self.run_dir / "deps")
        # Without the stale admin entry git would make the checkout, so only the link check can refuse it.
        subprocess.run(["git", "-C", str(dep), "worktree", "prune"], check=True)
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.run_dir / "deps").symlink_to(elsewhere)
        self.given_run(depends_on=[entry])
        code, out = self.launch("--yes")
        self.assertEqual(code, 1, out)
        self.assertIn("deps is a link", out)
        self.assertEqual(list(elsewhere.iterdir()), [])
        (self.run_dir / "deps").unlink()
        (self.run_dir / "deps").mkdir()
        (self.run_dir / "deps" / "sample-000-dep").symlink_to(elsewhere)
        code, out = self.launch("--yes")
        self.assertEqual(code, 1, out)
        self.assertIn("sample-000-dep is a link", out)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_launcher__no_grant_reaches_a_configured_repo_or_the_home_directory(self):
        """WS-5: a grant at or above the clone's working tree hands the session the code the Owner runs unsandboxed; one at the home directory hands it everything."""
        self.given_worktree()
        self.given_run()
        for root in (str(self.root / "repo"), "~/"):
            with self.subTest(accounting_root=root):
                self.with_config(accounting_root=root)
                code, out = self.plan()
                self.assertEqual(code, 1, out)
                self.assertIn("accounting root", out)
                self.assertNotIn("command:", out)

    def test_launcher__the_environment_never_moves_a_grant(self):
        """WS-6: a Lead that runs the launcher sets its environment, so a grant read from it would let a session widen the next one's."""
        self.given_worktree()
        self.given_run()
        self.env["ROBOWRIGHT_ACCOUNTING_ROOT"] = str(self.root)
        argv, _ = self.start()
        self.assertEqual(self.blob(argv)["permissions"]["additionalDirectories"], [str(self.run_dir), str(self.home / "accounting")])

    def test_launcher__a_planner_and_an_explainer_are_granted_the_projects_and_sessions_roots(self):
        """WS-7: a Planner writes briefs into new session folders and the plan into project folders (C12-C14), an Explainer the owner brief and report (C15)."""
        self.given_worktree()
        projects = self.root / "projects"
        projects.mkdir()
        self.with_config(projects_root=str(projects))
        self.given_project()
        for flags in (("--planner", "brief", "--slug", "sample-003-z"), ("--explainer", "report")):
            with self.subTest(flags=flags):
                code, out = self.doc_start(*flags)
                self.assertEqual(code, 0, out)
                blob = self.blob(self.stub_calls.read_text().splitlines())
                self.assertEqual(blob["permissions"]["additionalDirectories"], [str(projects), str(self.runs_root)])
                configs = self.project_configs(projects)
                self.assertEqual(blob["sandbox"], {"filesystem": {"denyWrite": self.git_dir(self.root / "repo") + configs
                                                                  + self.leaves(projects, self.runs_root)}})
                self.assertEqual(blob["permissions"]["deny"], self.edit_rules(self.root / "repo") + self.config_rules(configs)
                                 + self.leaf_rules(projects, self.runs_root))
                self.assertNotIn("allow", blob["permissions"])

    def test_launcher__a_document_role_whose_projects_root_holds_a_configured_repo_is_refused(self):
        """WS-8: a blanket grant over the clones' parent as the projects root is what this unit removes. The root here is the repo itself, which holds no other protected path, so only the repository check can refuse it."""
        self.given_worktree()
        self.with_config(projects_root=str(self.root / "repo"))
        self.given_project()
        code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
        self.assertEqual(code, 1, out)
        self.assertIn("projects root", out)
        self.assertIn("the repository", out)
        self.assertNotIn("command:", out)

    def test_launcher__the_launcher_adds_the_marker_to_the_repos_info_exclude(self):
        """WS-9: the Worker's preflight used to add it (C5), and WS-2 now denies it .git/info."""
        self.given_worktree(ignore_claude=False)
        self.given_run()
        self.start()
        self.assertIn(".claude/autonomous-run", (self.root / "repo/.git/info/exclude").read_text().splitlines())
        done = subprocess.run(["git", "-C", str(self.worktree), "check-ignore", "-q", ".claude/autonomous-run"])
        self.assertEqual(done.returncode, 0)

    def test_launcher__the_exclude_line_is_never_written_through_a_link(self):
        """WS-16: the main clone's .git is open to a Worker's shell but for config and hooks, so it can put a link at info before the next launch."""
        self.given_worktree(ignore_claude=False)
        self.given_run()
        info = self.root / "repo/.git/info"
        elsewhere = self.root / "elsewhere"
        info.rename(elsewhere)
        info.symlink_to(elsewhere)
        before = (elsewhere / "exclude").read_text()
        code, out = self.launch("--yes")
        self.assertEqual(code, 1, out)
        self.assertIn("info is a symlink", out)
        self.assertEqual((elsewhere / "exclude").read_text(), before)

    def test_launcher__no_root_grant_or_working_directory_has_a_link_at_or_above_it(self):
        """WS-10: a role granted a root can put a link in it, and a later role granted a path through that link would write the link's target. Following links safely is hard to get right, so none is followed: a link at any prefix is refused, the Owner's own included."""
        self.given_worktree()
        self.given_run(locks=["sim"])
        projects = self.root / "projects"
        projects.mkdir()
        self.with_config(projects_root=str(projects))
        self.given_project()
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())

        def linked(name, target_name=None):
            target = self.root / (target_name or name + "-real")
            target.mkdir(parents=True, exist_ok=True)
            link = self.root / name
            link.symlink_to(target)
            return link, target

        at, _ = linked("at")
        above, above_real = linked("above")
        (projects / "inside").symlink_to(above_real)
        for name in ("projects", "sessions", "accounting", "p"):
            (above_real / name).mkdir()
        (above_real / "p" / "PROJECT.md").write_text("# plan\n")
        (at.resolve() / "PROJECT.md").write_text("# plan\n")
        sessions = str(self.home / "sessions")
        layouts = [
            # (what, launch.json keys, run, the path named, the link named)
            ("the projects root a link", dict(projects_root=str(at)), "doc", str(at), str(at)),
            ("the projects root below a link", dict(projects_root=str(above / "projects")), "doc", str(above / "projects"), str(above)),
            ("the sessions root a link", dict(sessions_root=str(at)), "doc", str(at), str(at)),
            ("the sessions root below a link", dict(sessions_root=str(above / "sessions")), "doc", str(above / "sessions"), str(above)),
            ("the sessions root below a link in the projects root", dict(sessions_root=str(projects / "inside" / "sessions")), "doc",
             str(projects / "inside" / "sessions"), str(projects / "inside")),
            ("the accounting root a link", dict(accounting_root=str(at)), "worker", str(at), str(at)),
            ("the accounting root below a link", dict(accounting_root=str(above / "accounting")), "worker", str(above / "accounting"), str(above)),
            ("the accounting root below a link in the projects root", dict(accounting_root=str(projects / "inside" / "accounting")), "worker",
             str(projects / "inside" / "accounting"), str(projects / "inside")),
            ("a lock directory a link", {}, "lock", sessions + "/.sim-lock", sessions + "/.sim-lock"),
            ("the working directory a link in the projects root", {}, projects / "inside" / "p", str(projects / "inside" / "p"), str(projects / "inside")),
            ("the working directory a link", {}, at, str(at), str(at)),
            ("the working directory below a link", {}, above / "p", str(above / "p"), str(above)),
        ]
        for what, keys, run, path, link in layouts:
            with self.subTest(what):
                self.given_launch_json(dict(config, **keys))
                lock = Path(sessions) / ".sim-lock"
                if run == "lock":
                    lock.symlink_to(above_real)
                if run == "worker" or run == "lock":
                    code, out = self.plan()
                elif run == "doc":
                    code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
                else:
                    self.project = run
                    code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
                if lock.is_symlink():
                    lock.unlink()
                self.assertEqual(code, 1, out)
                self.assertIn(path, out)
                self.assertIn(link + " is a link", out)
                self.assertIn("real path", out)
                self.assertNotIn("command:", out)

    def test_launcher__no_root_grant_or_working_directory_holds_a_dot_or_dot_dot(self):
        """WS-18: `..` after a link took the kernel to one directory and the check to another (review 4 F1); with neither `.` nor `..` in a path, its spelling is the directory it names."""
        self.given_worktree()
        self.given_run()
        projects = self.root / "projects"
        (projects / "a").mkdir(parents=True)
        (projects / "p").mkdir()
        (projects / "p" / "PROJECT.md").write_text("# plan\n")
        self.with_config(projects_root=str(projects))
        self.given_project()
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
        layouts = [
            ("the projects root with `.`", dict(projects_root=str(self.root) + "/./projects"), "doc", "`.`"),
            ("the projects root with `..`", dict(projects_root=str(projects) + "/a/.."), "doc", "`..`"),
            ("the sessions root with `.`", dict(sessions_root="~/./sessions"), "doc", "`.`"),
            ("the sessions root with `..`", dict(sessions_root="~/x/../sessions"), "doc", "`..`"),
            ("the accounting root with `.`", dict(accounting_root="~/./accounting"), "worker", "`.`"),
            ("the accounting root with `..`", dict(accounting_root="~/x/../accounting"), "worker", "`..`"),
            ("the working directory with `..`", {}, Path(str(projects) + "/a/../p"), "`..`"),
        ]
        for what, keys, run, component in layouts:
            with self.subTest(what):
                self.given_launch_json(dict(config, **keys))
                if run == "worker":
                    code, out = self.plan()
                else:
                    if run != "doc":
                        self.project = run
                    code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
                self.assertEqual(code, 1, out)
                self.assertIn("holds a %s component" % component, out)
                self.assertNotIn("command:", out)

    def test_launcher__a_protected_path_spelled_in_another_case_is_still_matched(self):
        """WS-19: the volume takes a name in any letter case as the same directory, and the home directory is spelled by
        $HOME, which no check holds to the disk's spelling; so protected paths compare by device and inode."""
        upper = str(self.home).swapcase()
        if not os.path.exists(upper) or not os.path.samefile(upper, self.home):
            self.skipTest("a case-sensitive volume names another directory, or none, by another case")
        self.given_worktree()
        self.given_project()
        # Every root spelled as on disk, so only the home directory's own spelling differs.
        self.with_config(projects_root=str(self.home), sessions_root=str(self.runs_root))
        env = dict(self.env, HOME=upper)
        done = subprocess.run([BASH, str(LAUNCHER), "--planner", "brief", "--slug", "sample-003-z", "--project",
                               str(self.project), "--dry-run"], env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("at or above the home directory", done.stdout + done.stderr)
        self.assertNotIn("command:", done.stdout)

    def test_launcher__a_root_project_or_repository_spelled_other_than_on_disk_is_refused(self):
        """WS-20: a grant or a deny is a string the sandbox matches; one spelled in another letter case or Unicode form
        than the disk's names the directory for the kernel but may not match the path git, the kernel and the sandbox
        report (review 5 F4), and the launcher compares the working directory it starts in by that spelling (F1)."""
        if not os.path.exists(str(self.root).swapcase()):
            self.skipTest("a case-sensitive volume names another directory, or none, by another case")
        self.given_worktree()
        projects = self.root / "projects"
        projects.mkdir()
        nfc = self.root / unicodedata.normalize("NFC", "caf\u00e9")
        nfc.mkdir()
        self.given_project()
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
        repo = str(self.root / "repo")
        cases = [("the projects root in another case", dict(projects_root=str(self.root / "PROJECTS")), None, "PROJECTS", "projects"),
                 ("the sessions root in the other Unicode form", dict(sessions_root=unicodedata.normalize("NFD", str(nfc))), None,
                  unicodedata.normalize("NFD", "caf\u00e9"), unicodedata.normalize("NFC", "caf\u00e9")),
                 ("a repository in another case", dict(repos=[repo[:-4] + "REPO"]), None, "REPO", "repo"),
                 ("the --project in another case", {}, self.root / "PROJECT", "PROJECT", "project")]
        for what, keys, project, spelled, on_disk in cases:
            with self.subTest(what):
                self.given_launch_json(dict(dict(config, projects_root=str(projects)), **keys))
                if project is not None:
                    self.project = project
                code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
                self.assertEqual(code, 1, out)
                self.assertIn("spelled %s" % spelled, out)
                self.assertIn("names it %s" % on_disk, out)
                self.assertNotIn("command:", out)

    def given_python_swapping(self, swapped, target, to_link, when, at):
        """A `python3` on PATH that, `when` ("before" or "after") the launcher's first call naming `at`, turns the link
        `swapped` into a directory holding a PROJECT.md, or with `to_link` moves the directory aside and puts a link to
        `target` there. The race a role granted the projects root can run, made certain."""
        shim = self.root / "shim"
        shim.mkdir()
        flag = self.root / "swapped"
        swap = ('mv "$P" "$P.checked" && ln -s "%s" "$P"' % target if to_link
                else 'rm "$P" && mkdir "$P" && printf "# plan\\n" > "$P/PROJECT.md"')
        (shim / "python3").write_text(
            '#!/bin/bash\nP="%s"\nfirst=; case "$*" in *%s*) [ -e "%s" ] || { first=1; touch "%s"; } ;; esac\n'
            '[ -z "$first" ] || [ "%s" != before ] || { %s; }\n"%s" "$@"; code=$?\n'
            '[ -z "$first" ] || [ "%s" != after ] || { %s; }\nexit $code\n'
            % (swapped, at.replace(" ", "\\ "), flag, flag, when, swap, sys.executable, when, swap))
        (shim / "python3").chmod(0o755)
        return dict(self.env, PATH=f"{shim}:{self.env['PATH']}")

    def test_launcher__a_project_swapped_for_a_link_around_the_check_never_starts_there(self):
        """WS-21: a role granted the projects root can swap a folder in it for a link while the launcher runs (review 4
        F1, review 5 F1). The launcher checks the project as spelled before anything reads it, and starts only in the
        directory it checked, so neither the session's working directory nor its ledger lands in the repository. A swap
        of the project folder itself after the check is refused by the ledger's own write; one a level up is not, and
        one after the start finds the ledger written from inside the directory the session started in."""
        self.given_worktree()
        repo = self.root / "repo"
        projects = self.root / "projects"
        projects.mkdir()
        for inside in (repo / "sub", repo / "p"):
            inside.mkdir()
            (inside / "PROJECT.md").write_text("# plan\n")
        self.with_config(projects_root=str(projects))
        # (what, when, at which call, the folder swapped, the link's target, the --project)
        cases = [("before the check", "before", "role_grants.py document", projects / "p", repo / "sub", projects / "p"),
                 ("after the check", "after", "role_grants.py document", projects / "a", repo, projects / "a" / "p"),
                 ("after the start", "before", "session_write.py append", projects / "b", repo, projects / "b" / "p")]
        started = {"before the check": True, "after the check": False, "after the start": True}
        for what, when, at, swapped, target, project in cases:
            with self.subTest(what):
                shutil.rmtree(self.root / "shim", ignore_errors=True)
                (self.root / "swapped").unlink(missing_ok=True)
                for inside in (repo / "sub", repo / "p"):
                    (inside / "DECISIONS.md").unlink(missing_ok=True)
                if what == "before the check":
                    swapped.symlink_to(target)
                else:
                    project.mkdir(parents=True)
                    (project / "PROJECT.md").write_text("# plan\n")
                env = self.given_python_swapping(swapped, target, what != "before the check", when, at)
                pwd = self.root / "pwd.txt"
                pwd.write_text("")
                self.set_stub('pwd -P >> "%s"\necho "backgrounded · bbbb2222 · explainer"' % pwd)
                done = subprocess.run([BASH, str(LAUNCHER), "--explainer", "report", "--project", str(project), "--yes"],
                                      env=env, capture_output=True, text=True)
                out = done.stdout + done.stderr
                self.assertEqual([d for d in (repo / "sub", repo / "p") if (d / "DECISIONS.md").exists()], [], out)
                self.assertNotIn(str(repo), pwd.read_text(), out)
                if started[what]:
                    self.assertEqual(done.returncode, 0, out)
                    self.assertEqual(pwd.read_text().splitlines(), [str(project)], out)
                    if what == "after the start":
                        self.assertTrue((Path(str(swapped) + ".checked") / "p" / "DECISIONS.md").exists(), out)
                else:
                    self.assertEqual(done.returncode, 1, out)
                    self.assertIn("changed after it was checked", out)
                    self.assertEqual(pwd.read_text(), "", out)

    def test_launcher__a_pasted_hand_off_starts_only_in_the_directory_checked(self):
        """WS-25: in paste mode, the default, the Owner runs the hand-off line any time later; a role granted the projects
        root can swap a folder above the project for a link first, and a bare `cd` would start the session in the
        repository (review 6 F1). The line compares the shell's `pwd -P` with the path checked before it starts; the
        folder's space shows the compare quotes it (review 7 F2). The hand-off's own ledger line is written from inside
        the checked directory, so a swap just before it lands nowhere else (review 7 F1)."""
        self.given_worktree()
        repo = self.root / "repo"
        (repo / "p").mkdir()
        (repo / "p/PROJECT.md").write_text("# plan\n")
        projects = self.root / "projects"
        project = projects / "a b" / "p"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")
        self.with_config(projects_root=str(projects), launch="paste")
        done = subprocess.run([BASH, str(LAUNCHER), "--explainer", "report", "--project", str(project), "--yes"],
                              env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        line = re.search(r"^paste this yourself:\s*(cd .*)$", done.stdout, re.M).group(1)
        pwd = self.root / "pwd.txt"
        self.set_stub('pwd -P >> "%s"' % pwd)
        for what, swapped in (("after a swap", True), ("as checked", False)):
            with self.subTest(what):
                pwd.write_text("")
                if swapped:
                    (projects / "a b").rename(projects / "a.checked")
                    (projects / "a b").symlink_to(repo)
                ran = subprocess.run([BASH, "-c", line], env=self.env, cwd=self.root, capture_output=True, text=True)
                if swapped:
                    (projects / "a b").unlink()
                    (projects / "a.checked").rename(projects / "a b")
                    self.assertNotEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                    self.assertEqual(pwd.read_text(), "")
                else:
                    self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                    self.assertEqual(pwd.read_text().splitlines(), [str(project)])
        with self.subTest("a swap at the hand-off's ledger line"):
            (project / "DECISIONS.md").unlink()
            env = self.given_python_swapping(projects / "a b", repo, True, "before", "session_write.py append")
            done = subprocess.run([BASH, str(LAUNCHER), "--explainer", "report", "--project", str(project), "--yes"],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertFalse((repo / "p/DECISIONS.md").exists(), done.stdout + done.stderr)
            self.assertIn("hand-off via", (projects / "a b.checked/p/DECISIONS.md").read_text())

    def test_launcher__a_document_role_cannot_write_a_projects_claude_settings(self):
        """WS-22: Claude Code loads a folder's `.claude` settings and `.mcp.json` for a session started there, and runs
        their hooks and servers outside the sandbox; a Planner granted the projects root could plant them for the next
        session in another project, or for the Lead in the root (review 5 F3). The sandbox protects only the working
        directory's own and those above it."""
        self.given_worktree()
        projects = self.root / "projects"
        for folder in ("p1", "p2"):
            (projects / folder).mkdir(parents=True)
            (projects / folder / "PROJECT.md").write_text("# plan\n")
        self.with_config(projects_root=str(projects))
        self.project = projects / "p1"
        code, out = self.doc_start("--planner", "brief", "--slug", "sample-003-z")
        self.assertEqual(code, 0, out)
        blob = self.blob(self.stub_calls.read_text().splitlines())
        denied, rules = blob["sandbox"]["filesystem"]["denyWrite"], blob["permissions"]["deny"]
        for path in (projects / ".claude", projects / ".mcp.json", projects / "p2/.claude", projects / "p2/.mcp.json",
                     projects / "**/.claude", projects / "**/.mcp.json"):
            with self.subTest(path=str(path)):
                self.assertIn(str(path), denied)
                self.assertIn(f"Edit(/{path}/**)" if path.name == ".claude" else f"Edit(/{path})", rules)
        self.assertEqual(blob["permissions"]["additionalDirectories"], [str(projects), str(self.runs_root)])

    def test_launcher__a_grant_above_a_link_in_a_repositorys_spelling_is_refused(self):
        """WS-23: `repos` may name a clone through the Owner's own link; a role granted the directory holding that link
        could point it at another clone, and the denies and the allowlist would follow the new target."""
        self.given_worktree()
        links = self.root / "links"
        links.mkdir()
        (links / "repo").symlink_to(self.root / "repo")
        self.with_config(repos=[str(links / "repo")], projects_root=str(links))
        self.given_project()
        code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
        self.assertEqual(code, 1, out)
        self.assertIn("at or above the repository %s" % (links / "repo"), out)
        self.assertNotIn("command:", out)

    def test_launcher__role_grants_holds_a_workers_session_folder_itself(self):
        """WS-24: the launcher resolves the session folder before it asks, but role_grants.py is a tool of its own; a
        folder that is a link, or a directory elsewhere that only shares a session folder's name, would be granted."""
        self.given_worktree()
        self.given_run()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        linked = elsewhere / "sample-009-q"
        shutil.copytree(self.run_dir, linked)
        (self.runs_root / "sample-009-q").symlink_to(linked)
        namesake = elsewhere / self.run_dir.name
        shutil.copytree(self.run_dir, namesake)
        for what, folder, named in (("a session folder that is a link", self.runs_root / "sample-009-q", "is a link"),
                                    ("a namesake outside the sessions root", namesake, "is not a session folder")):
            with self.subTest(what):
                done = subprocess.run([sys.executable, str(SCRIPTS / "role_grants.py"), "worker", str(folder), str(self.worktree)],
                                      env=self.env, capture_output=True, text=True)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertIn(named, done.stderr)
                self.assertEqual(done.stdout, "")

    def test_launcher__a_document_role_with_no_well_formed_repos_is_refused(self):
        """WS-11: with `repos` missing or malformed nothing is denied, and the projects root could hold every clone unchecked."""
        self.given_worktree()
        projects = self.root / "projects"
        projects.mkdir()
        self.given_project()
        for repos in (None, ["relative/path"]):
            with self.subTest(repos=repos):
                config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
                config["projects_root"] = str(projects)
                config.pop("repos", None)
                if repos is not None:
                    config["repos"] = repos
                (self.home / ".claude/robowright/launch.json").write_text(json.dumps(config))
                code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
                self.assertEqual(code, 1, out)
                self.assertIn("repos", out)
                self.assertNotIn("command:", out)

    def test_launcher__no_grant_reaches_the_launchers_clone_or_launch_jsons_real_directory(self):
        """WS-12: the clone is the installed skills and the launcher itself; launch.json is the trust root, and where it is a link into another directory its real directory is what a session must not write."""
        self.given_worktree()
        self.given_project()
        with self.subTest(projects_root="the launcher's clone"):
            self.with_config(projects_root=str(REPO))
            code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
            self.assertEqual(code, 1, out)
            self.assertIn("the launcher's own clone", out)
        linked_config = self.root / "linked-config"
        (linked_config / "robowright").mkdir(parents=True)
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
        config["projects_root"] = str(linked_config)
        (linked_config / "robowright/launch.json").write_text(json.dumps(config))
        (self.home / ".claude/robowright/launch.json").unlink()
        (self.home / ".claude/robowright/launch.json").symlink_to(linked_config / "robowright/launch.json")
        with self.subTest(projects_root="above launch.json's real file"):
            code, out = self.doc_plan("--planner", "brief", "--slug", "sample-003-z")
            self.assertEqual(code, 1, out)
            self.assertIn("launch.json's real directory", out)
            self.assertNotIn("command:", out)

    def test_launcher__a_planted_commondir_is_refused_and_denied(self):
        """WS-17: a commondir file in the main clone's .git makes git read another directory's config and hooks, so the denies would move with it; the shell may write the rest of that .git."""
        self.given_worktree()
        self.given_run()
        blob = self.blob(self.start()[0])
        self.assertIn(str(Path(os.path.realpath(self.root / "repo")) / ".git"), blob["sandbox"]["filesystem"]["denyWrite"])
        planted = self.root / "planted"
        planted.mkdir()
        (self.root / "repo/.git/commondir").write_text(str(planted) + "\n")
        done = subprocess.run([sys.executable, str(SCRIPTS / "role_grants.py"), "document"], env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("commondir", done.stderr)

    def test_launcher__git_environment_never_moves_a_deny(self):
        """WS-13: GIT_DIR or GIT_COMMON_DIR in the environment role_grants.py runs in would make its git calls name another repository's files, and the real ones would go undenied."""
        self.given_worktree()
        other = self.given_second_repo("other")
        env = dict(self.env, GIT_DIR=str(other / ".git"), GIT_COMMON_DIR=str(other / ".git"))
        done = subprocess.run([sys.executable, str(SCRIPTS / "role_grants.py"), "document"], env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        denied = json.loads(done.stdout)["sandbox"]["filesystem"]["denyWrite"]
        self.assertEqual(denied[:1], self.git_dir(self.root / "repo"))
        self.assertNotIn(str(Path(os.path.realpath(other)) / ".git"), denied)

    def test_launcher__a_document_roles_working_directory_is_held_to_the_same_rule(self):
        """WS-14: the working directory is a write grant; a --project that holds a configured repository would grant it. The folder here holds that repository and not the home directory, so only the repository check can refuse it."""
        self.given_worktree()
        outer = self.root / "outer"
        outer.mkdir()
        inner = self.given_second_repo("outer/inner")
        self.with_config(repos=[str(self.root / "repo"), str(inner)])
        (outer / "PROJECT.md").write_text("# plan\n")
        done = subprocess.run([BASH, str(LAUNCHER), "--planner", "brief", "--slug", "sample-003-z", "--project", str(outer), "--dry-run"],
                              env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("working directory", done.stdout + done.stderr)
        self.assertIn("the repository", done.stdout + done.stderr)
        self.assertNotIn("command:", done.stdout)

    def test_launcher__a_document_roles_working_directory_inside_a_clone_or_worktree_is_refused(self):
        """WS-15: a folder holding a PROJECT.md inside a clone or a Worker's worktree (the launcher's own clone ships one), configured or not, would make that checkout the role's working directory, and so writable. A projects root that is itself a git repository is the Owner's own and starts."""
        self.given_worktree()
        projects = self.root / "projects"
        projects.mkdir()
        self.with_config(projects_root=str(projects))
        places = {"a configured repository": self.root / "repo" / "sub",
                  "a worktree": self.worktree / "sub",
                  "a clone launch.json does not list": self.given_second_repo("loose") / "sub",
                  "the launcher's own clone": REPO / "skills/one-off/templates"}
        for what, folder in places.items():
            with self.subTest(project=what):
                folder.mkdir(exist_ok=True)
                if not (folder / "PROJECT.md").exists():
                    (folder / "PROJECT.md").write_text("# plan\n")
                done = subprocess.run([BASH, str(LAUNCHER), "--planner", "brief", "--slug", "sample-003-z", "--project", str(folder), "--dry-run"],
                                      env=self.env, capture_output=True, text=True)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("working directory", done.stdout + done.stderr)
                self.assertIn("inside", done.stdout + done.stderr)
                self.assertNotIn("command:", done.stdout)
        with self.subTest(project="in a projects root that is a git repository"):
            subprocess.run(GIT + ["init", "-q", str(projects)], check=True, capture_output=True)
            (projects / "plan").mkdir()
            (projects / "plan" / "PROJECT.md").write_text("# plan\n")
            done = subprocess.run([BASH, str(LAUNCHER), "--planner", "brief", "--slug", "sample-003-z", "--project", str(projects / "plan"), "--dry-run"],
                                  env=self.env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with self.subTest(project="under a home directory that is a git repository"):
            shutil.rmtree(projects / ".git")
            subprocess.run(GIT + ["init", "-q", str(self.home)], check=True, capture_output=True)
            done = subprocess.run([BASH, str(LAUNCHER), "--planner", "brief", "--slug", "sample-003-z", "--project", str(projects / "plan"), "--dry-run"],
                                  env=self.env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)



SLUG = "sample-001-x"
BRANCH = "robowright/" + SLUG


class WorktreeCreationTests(LauncherCase):
    """WT rows (BEHAVIORS.md): a sandboxed Lead cannot write a repository's git directory, so the launcher creates a
    Worker's missing worktree on the Owner's side, from run.json values held to the hook's convention first."""

    def setUp(self):
        super().setUp()
        self.repo = self.root / "repo"
        subprocess.run(GIT + ["init", "-q", str(self.repo)], check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "base"], cwd=self.repo, check=True, capture_output=True)
        self.base = self.rev(self.repo, "HEAD")
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "after the base"], cwd=self.repo, check=True, capture_output=True)
        self.worktree = self.repo / ".worktrees" / SLUG
        self.log = self.given_recording_git()

    def rev(self, where, ref):
        return subprocess.run(["git", "-C", str(where), "rev-parse", ref], check=True, capture_output=True, text=True).stdout.strip()

    def given_briefed(self, worktree=None, branch=BRANCH, base=None, **fields):
        unit = {} if branch is None else {"branch": branch}
        self.given_run(worktree=str(worktree or self.worktree), base_sha=self.base if base is None else base,
                       unit_fields=(unit,), **fields)
        self.log.write_text("")

    def worktree_adds(self):
        return [c for c in git_calls(self.log) if "worktree" in c and "add" in c[c.index("worktree"):]]

    def repository_calls(self):
        """Every git call but those a refusal's hint may run (hint_call)."""
        return [c for c in git_calls(self.log) if not hint_call(c)]

    def assert_refused_before_git(self, code, out, named, path=None):
        self.assertEqual(code, 1, out)
        self.assertIn(named, out)
        self.assertFalse((path or self.worktree).exists())
        self.assertEqual(self.repository_calls(), [])
        self.assertNotIn("command:", out)

    def test_launcher__at_preflight_a_missing_worktree_on_the_convention_is_created_from_the_base(self):
        """WT-1: the Lead's sandbox cannot run `git worktree add` (review 3 F3), so the launch does it, with `-b` from base_sha while the branch does not exist yet; the dry run only says so."""
        self.given_briefed()
        code, out = self.plan()
        self.assertEqual(code, 0, out)
        self.assertIn("worktree add -b %s %s %s" % (BRANCH, self.worktree, self.base), out)
        self.assertFalse(self.worktree.exists())
        self.assertEqual(self.worktree_adds(), [])
        argv, out = self.start()
        self.assertTrue(argv, out)
        self.assertEqual(self.rev(self.worktree, "HEAD"), self.base)
        branch = subprocess.run(["git", "-C", str(self.worktree), "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True)
        self.assertEqual(branch.stdout.strip(), BRANCH)
        add = self.worktree_adds()
        self.assertEqual(len(add), 1, add)
        self.assertEqual(add[0][add[0].index("add"):], ["add", "--no-checkout", "-b", BRANCH, "--end-of-options", str(self.worktree), self.base])

    def test_launcher__a_hook_only_the_new_worktree_reads_does_not_run_as_it_is_checked_out(self):
        """WT-13: a config hook included only on the session's branch (`includeIf onbranch:robowright/**`), on
        post-index-change: the launch makes the worktree with the base's files, and the hook never runs — the checkout
        `worktree add` runs reads the new worktree's config, not the main clone's (gate F5)."""
        (self.repo / "notes.txt").write_text("base notes\n")
        subprocess.run(GIT + ["add", "notes.txt"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "-m", "notes"], cwd=self.repo, check=True, capture_output=True)
        base = self.rev(self.repo, "HEAD")
        markers = self.root / "markers"
        markers.mkdir()
        program = self.root / "hook-pic"
        program.write_text(f"#!/bin/sh\ntouch '{markers / 'pic'}'\n")
        program.chmod(0o755)
        included = self.root / "branch.gitconfig"
        included.write_text(f"[hook \"pic\"]\n\tevent = post-index-change\n\tcommand = {program}\n")
        with open(self.repo / ".git" / "config", "a") as config:
            config.write(f'[includeIf "onbranch:robowright/**"]\n\tpath = {included}\n')
        self.given_briefed(base=base)

        argv, out = self.start()

        self.assertTrue(argv, out)
        self.assertEqual((self.worktree / "notes.txt").read_text(), "base notes\n")
        self.assertEqual(sorted(p.name for p in markers.iterdir()), [])

    def test_launcher__a_repository_with_a_submodule_and_submodule_recurse_still_launches(self):
        """WT-14: a base holding a submodule, `submodule.recurse = true` in the repository's config: the launch makes
        the worktree with the base's files, as `worktree add` alone does — its checkout never recurses (gate F7)."""
        library = self.root / "library"
        library.mkdir()
        subprocess.run(GIT + ["init", "-q"], cwd=library, check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "library"], cwd=library, check=True, capture_output=True)
        (self.repo / "notes.txt").write_text("base notes\n")
        subprocess.run(GIT + ["-c", "protocol.file.allow=always", "submodule", "add", "-q", str(library), "library"],
                       cwd=self.repo, check=True, capture_output=True)
        subprocess.run(GIT + ["add", "notes.txt"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "-m", "notes and library"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(GIT + ["config", "submodule.recurse", "true"], cwd=self.repo, check=True, capture_output=True)
        base = self.rev(self.repo, "HEAD")
        self.given_briefed(base=base)

        argv, out = self.start()

        self.assertTrue(argv, out)
        self.assertEqual((self.worktree / "notes.txt").read_text(), "base notes\n")

    def test_launcher__a_checkout_that_fails_leaves_no_worktree_and_no_branch(self):
        """WT-15: the checkout after `worktree add --no-checkout` fails: the launch refuses, and no worktree is left
        registered, no folder and no branch, so the next launch makes it afresh rather than reusing an empty index
        (adversarial F1)."""
        shim = self.root / "shim"
        shim.mkdir()
        (shim / "git").write_text('#!/bin/sh\ncase " $* " in *" reset --hard "*) exit 1 ;; esac\nexec "%s" "$@"\n'
                                  % (self.root / "bin" / "git"))
        (shim / "git").chmod(0o755)
        self.given_briefed()

        code, out = self.launch("--yes", env=dict(self.env, PATH=f"{shim}:{self.env['PATH']}"))

        self.assertNotEqual(code, 0, out)
        self.assertIn("git could not make the worktree", out)
        listed = subprocess.run(["git", "-C", str(self.repo), "worktree", "list", "--porcelain"], capture_output=True, text=True)
        self.assertNotIn(str(self.worktree), listed.stdout)
        self.assertFalse(self.worktree.exists())
        branch = subprocess.run(["git", "-C", str(self.repo), "branch", "--list", BRANCH], capture_output=True, text=True)
        self.assertEqual(branch.stdout, "")

    def test_launcher__after_preflight_the_existing_branch_is_attached(self):
        """WT-2: once preflight has passed the branch holds the session's commits; a new branch from the base would lose them, and `-b` refuses an existing branch."""
        subprocess.run(GIT + ["branch", BRANCH, self.base], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(GIT + ["worktree", "add", "-q", str(self.root / "scratch"), BRANCH], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "the session's work"], cwd=self.root / "scratch", check=True, capture_output=True)
        work = self.rev(self.root / "scratch", "HEAD")
        subprocess.run(GIT + ["worktree", "remove", str(self.root / "scratch")], cwd=self.repo, check=True, capture_output=True)
        self.given_implementing(worktree=str(self.worktree), base_sha=self.base, unit_fields=({"branch": BRANCH},))
        self.log.write_text("")
        # The state machine allows no plain launch past intake, so that launch makes nothing.
        code, out = self.launch("--yes")
        self.assertEqual(code, 1, out)
        self.assertIn("check-op launch said no", out)
        self.assertFalse(self.worktree.exists())
        self.assertEqual(self.worktree_adds(), [])
        argv, out = self.start("--resume", NEW_ID)
        self.assertTrue(argv, out)
        self.assertEqual(self.rev(self.worktree, "HEAD"), work)
        add = self.worktree_adds()
        self.assertEqual(add[0][add[0].index("add"):], ["add", "--no-checkout", "--end-of-options", str(self.worktree), BRANCH])

    def test_launcher__a_finished_sessions_worktree_is_never_created(self):
        """WT-3: an accepted or parked session's worktree is torn down on purpose, and its branch is kept, so only the phase
        stops git attaching it again; role_grants.py refuses on its own as well as the launcher, and a phase that is no
        name at all is no later phase to attach in."""
        subprocess.run(GIT + ["branch", BRANCH, self.base], cwd=self.repo, check=True, capture_output=True)
        refused = {"done": "a finished session's worktree is not made", "parked": "a finished session's worktree is not made",
                   7: "is not a phase name"}
        for phase, named in (("done", "phase is done"), ("parked", "the session is finished"), (7, "does not exist")):
            with self.subTest(phase=phase):
                self.given_briefed(phase=phase)
                code, out = self.launch("--yes")
                self.assertEqual(code, 1, out)
                self.assertIn(named, out)
                for step in ("plan", "make"):
                    done = subprocess.run([sys.executable, str(SCRIPTS / "role_grants.py"), "worktree", str(self.run_dir), step],
                                          env=self.env, capture_output=True, text=True)
                    self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                    self.assertIn(refused[phase], done.stderr)
                self.assertFalse(self.worktree.exists())
                self.assertEqual(self.worktree_adds(), [])

    def test_launcher__a_worktree_path_off_the_convention_is_refused(self):
        """WT-4: run.json is session-written; the launcher creates only <repo>/.worktrees/<session dir name>, never a path a session chose."""
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        paths = {"beside the repository": self.root / "worktrees" / SLUG,
                 "another slug": self.repo / ".worktrees" / "sample-002-y",
                 "holding `..`": Path(str(self.repo) + "/.worktrees/../worktrees/" + SLUG),
                 "through a link at .worktrees": self.repo / ".worktrees" / SLUG,
                 "relative": Path("repo/.worktrees/" + SLUG)}
        for what, path in paths.items():
            with self.subTest(what):
                if what == "through a link at .worktrees":
                    (self.repo / ".worktrees").symlink_to(elsewhere)
                self.given_briefed(worktree=path)
                code, out = self.launch("--yes", cwd=self.root)
                self.assertEqual(code, 1, out)
                self.assertIn("%s/.worktrees/%s" % (self.repo, SLUG), out)
                self.assertEqual(self.repository_calls(), [])
                self.assertEqual(list(elsewhere.iterdir()), [])
                self.assertFalse((self.root / "worktrees").exists())
                if what == "through a link at .worktrees":
                    (self.repo / ".worktrees").unlink()
                self.assertFalse(self.worktree.exists())

    def test_launcher__a_run_json_naming_the_old_place_is_still_made_and_started_there(self):
        """WT-10: a session briefed before U46 names <repo>/.claude/worktrees/<slug>; it keeps working until torn down."""
        legacy = self.repo / ".claude" / "worktrees" / SLUG
        self.given_briefed(worktree=legacy)
        argv, out = self.start()
        self.assertTrue(argv, out)
        self.assertEqual(self.rev(legacy, "HEAD"), self.base)
        branch = subprocess.run(["git", "-C", str(legacy), "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True)
        self.assertEqual(branch.stdout.strip(), BRANCH)

    def test_launcher__a_worktree_made_under_dot_worktrees_stays_out_of_the_main_checkouts_status(self):
        """WT-11: accept.sh refuses a dirty main clone, and git lists a nested worktree as untracked."""
        self.given_briefed()
        self.assertTrue(self.start()[0])
        second = self.runs_root / "sample-002-y"
        second.mkdir()
        self.run_dir, saved = second, self.run_dir
        self.given_run(worktree=str(self.repo / ".worktrees" / "sample-002-y"), base_sha=self.base,
                       unit_fields=({"branch": "robowright/sample-002-y"},))
        self.assertTrue(self.start()[0])
        self.run_dir = saved
        exclude = (self.repo / ".git" / "info" / "exclude").read_text().splitlines()
        self.assertEqual(exclude.count("/.worktrees/"), 1, exclude)
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(status.stdout, "")

    def test_launcher__the_exclude_line_is_its_own_line_after_a_last_line_with_no_newline(self):
        """WT-12: appended bare, `/.worktrees/` would merge into the last line and ignore nothing."""
        (self.repo / ".git" / "info" / "exclude").write_text("/sample-local")
        self.given_briefed()

        self.assertTrue(self.start()[0])

        exclude = (self.repo / ".git" / "info" / "exclude").read_text().splitlines()
        self.assertEqual(exclude[:2], ["/sample-local", "/.worktrees/"])
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(status.stdout, "")

    def test_launcher__a_branch_off_the_convention_is_refused(self):
        """WT-5: `units[0].branch` reaches `git worktree add -b`; a value starting `-` would read as an option, and the hook names the branch robowright/<slug>."""
        for branch in ("-b", "other/" + SLUG, BRANCH + "/more", "robowright//" + SLUG, 7, None):
            with self.subTest(branch=branch):
                self.given_briefed(branch=branch)
                code, out = self.launch("--yes")
                self.assert_refused_before_git(code, out, "branch")

    def test_launcher__a_base_that_is_not_a_full_commit_id_of_the_repository_is_refused(self):
        """WT-6: base_sha reaches `git worktree add`; a short id can name another object later, and only a commit gives a
        branch. An annotated tag's own id peels to a commit, so git would take it; the id must be the commit's."""
        tree = self.rev(self.repo, "HEAD^{tree}")
        subprocess.run(GIT + ["tag", "-a", "-m", "a tag", "v1", self.base], cwd=self.repo, check=True, capture_output=True)
        tag = self.rev(self.repo, "refs/tags/v1")
        for base, git_runs in (("abc1234", False), ("g" * 40, False), ("1" * 40, True), (tree, True), (tag, True)):
            with self.subTest(base=base):
                self.given_briefed(base=base)
                code, out = self.launch("--yes")
                self.assertEqual(code, 1, out)
                self.assertIn("base_sha", out)
                self.assertFalse(self.worktree.exists())
                self.assertEqual(self.worktree_adds(), [])
                if not git_runs:
                    self.assertEqual(self.repository_calls(), [])

    def test_launcher__a_repository_launch_json_does_not_trust_gets_no_worktree(self):
        """WT-7: U36's allowlist is the Owner's word on which clones the Owner-side tools run git in."""
        stray = self.root / "stray"
        subprocess.run(GIT + ["init", "-q", str(stray)], check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=stray, check=True, capture_output=True)
        self.base = self.rev(stray, "HEAD")
        path = stray / ".worktrees" / SLUG
        self.given_briefed(worktree=path)
        code, out = self.launch("--yes")
        self.assert_refused_before_git(code, out, "repos", path)

    def test_launcher__the_new_branch_writes_no_ref_or_reflog_through_a_planted_link(self):
        """WT-9: a Worker's shell writes the shared .git, and `worktree add -b` writes the new branch's ref and appends
        its reflog as the Owner, following a link (found after review 7); a planted link would have the Owner's git
        append to, or create a file in, a place the session chose."""
        owner_file = self.root / "owner.txt"
        owner_dir = self.root / "owner-dir"
        logs = self.repo / ".git/logs/refs/heads"
        refs = self.repo / ".git/refs/heads"
        def reset():
            """No worktree, branch, ref or reflog left by the subtest before: each plant meets a fresh repository."""
            subprocess.run(GIT + ["worktree", "remove", "--force", str(self.worktree)], cwd=self.repo, capture_output=True)
            subprocess.run(GIT + ["branch", "-D", BRANCH], cwd=self.repo, capture_output=True)
            for leftover in (logs / "robowright", refs / "robowright", owner_dir):
                if leftover.is_symlink():
                    leftover.unlink()
                elif leftover.exists():
                    shutil.rmtree(leftover)
        plants = {"a link at the branch's reflog": (logs / BRANCH, owner_file),
                  "a link at the reflog's directory": (logs / "robowright", owner_dir),
                  "a link at the ref's directory": (refs / "robowright", owner_dir)}
        for what, (link, target) in plants.items():
            with self.subTest(what):
                reset()
                owner_file.write_text("the Owner's file\n")
                owner_dir.mkdir(exist_ok=True)
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target)
                self.given_briefed()
                code, out = self.launch("--yes")
                link.unlink()
                self.assertEqual(code, 1, out)
                self.assertIn(str(link), out)
                self.assertEqual(owner_file.read_text(), "the Owner's file\n")
                self.assertEqual(list(owner_dir.iterdir()), [])
                self.assertEqual(self.worktree_adds(), [])
                self.assertFalse(self.worktree.exists())
        with self.subTest("a reflog directory link planted after the check"):
            reset()
            owner_dir.mkdir()
            shim = self.root / "shim"
            shim.mkdir()
            (shim / "git").write_text(
                '#!/bin/sh\ncase " $* " in *" worktree add "*) [ -e "%s" ] || ln -s "%s" "%s" ;; esac\nexec "%s" "$@"\n'
                % (logs / "robowright", owner_dir, logs / "robowright", self.root / "bin" / "git"))
            (shim / "git").chmod(0o755)
            self.given_briefed()
            code, out = self.launch("--yes", env=dict(self.env, PATH=f"{shim}:{self.env['PATH']}"))
            self.assertEqual(list(owner_dir.iterdir()), [], out)

    def test_launcher__git_environment_never_moves_the_worktree_made(self):
        """WT-8: the Lead's environment reaches the launcher; GIT_DIR there would point every git call at another
        repository, and the base would be looked up and the branch made in it. The launch itself then stops at
        owner_git's worktree listing, which reads the same environment: that refusal is U36's and fails closed."""
        other = self.root / "other"
        subprocess.run(GIT + ["init", "-q", str(other)], check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=other, check=True, capture_output=True)
        self.given_briefed()
        env = dict(self.env, GIT_DIR=str(other / ".git"), GIT_COMMON_DIR=str(other / ".git"), GIT_WORK_TREE=str(other))
        _, out = self.launch("--yes", env=env)
        self.assertIn("worktree:  made", out)
        self.assertEqual(self.rev(self.worktree, "HEAD"), self.base)
        self.assertEqual(self.rev(self.repo, BRANCH), self.base)
        branches = subprocess.run(["git", "-C", str(other), "branch", "--list", BRANCH], capture_output=True, text=True)
        self.assertEqual(branches.stdout, "")


OWNER_TEXT = "the Owner's file\n"


class SessionWriteTests(LauncherCase):
    """SW-9 to SW-11 (BEHAVIORS.md): the launcher writes the marker, run.json and the ledger outside the sandbox, so
    never through an entry the session planted in its folder or its worktree."""

    def setUp(self):
        super().setUp()
        self.outside = self.root / "outside"
        self.outside.mkdir()

    def planted(self, link, text=OWNER_TEXT):
        target = self.outside / ("target-" + link.name.lstrip("."))
        target.write_text(text)
        link.symlink_to(target)
        return target

    def given_launchable(self):
        """A launchable session whose worktree ignores a `.claude` that is not a directory too."""
        self.given_worktree()
        with open(self.worktree / ".gitignore", "a") as f:
            f.write(".claude\n")
        subprocess.run(GIT + ["commit", "-q", "-am", "ignore any .claude"], cwd=self.worktree, check=True, capture_output=True)
        self.given_run()
        self.stub_calls.write_text("")

    def test_launcher__refuses_a_marker_whose_claude_dir_is_a_link(self):
        """SW-9: `mkdir -p` and the marker write would both follow a `.claude` link out of the worktree."""
        self.given_launchable()
        (self.worktree / ".claude").symlink_to(self.outside, target_is_directory=True)
        code, out = self.launch("--yes")
        self.assertEqual(code, 1, out)
        self.assertIn(".claude is a symlink", out)
        self.assertEqual(list(self.outside.iterdir()), [])
        self.assertEqual(self.stub_calls.read_text(), "")

    def test_launcher__rotate_requested_at_reaches_the_plan_only_as_an_iso_time(self):
        """SW-17: the value reaches the plan and a ledger heading, so a newline in it would split that heading."""
        self.given_launchable()
        for requested, refused in (("2026-10-15T01:02:03+00:00\nSECOND LINE", True), ("2026-10-15T01:02:03+00:00", False)):
            with self.subTest(requested=requested):
                self.rewrite_run(rotate={"requested_at": requested, "resumed_at": None, "next_unit": "U1"})
                code, out = self.plan("--rotate")
                self.assertEqual("rotate.requested_at" in out and code == 1, refused, out)
                self.assertNotIn("SECOND LINE", out)

    def test_launcher__a_worktree_path_with_a_newline_never_reaches_the_ledger(self):
        """SW-18: the worktree path is session-chosen and goes into the ledger entry; a newline in it would split that line."""
        self.given_worktree()
        odd = self.root / "worktrees" / "w\nt"
        subprocess.run(GIT + ["worktree", "add", "-q", "-b", "robowright/odd", str(odd)], cwd=self.root / "repo", check=True, capture_output=True)
        self.worktree = odd
        self.given_run()
        code, out = self.launch("--yes")
        self.assertEqual(code, 1, out)
        self.assertIn("'worktree' holds a control character", out)
        self.assertFalse((self.run_dir / "LEDGER.md").exists())

    def assert_launch_refused(self, link):
        target = self.planted(link)
        code, out = self.launch("--yes")
        self.assertEqual(code, 1, out)
        self.assertIn(link.name, out)
        self.assertEqual(target.read_text(), OWNER_TEXT)
        self.assertEqual(self.stub_calls.read_text(), "")

    def test_launcher__never_writes_the_marker_through_a_link(self):
        """SW-10: the marker is refused before anything starts, so a refusal never leaves a session running unarmed."""
        self.given_launchable()
        (self.worktree / ".claude").mkdir()
        self.assert_launch_refused(self.worktree / ".claude" / "autonomous-run")

    def test_launcher__never_appends_its_ledger_entry_through_a_link(self):
        """SW-10: the ledger is checked before anything starts, so a refusal never leaves a session running unrecorded."""
        self.given_launchable()
        self.assert_launch_refused(self.run_dir / "LEDGER.md")

    def pin_with(self, name):
        PinProjectTests.given_pasted(self, project=None)
        target = self.planted(self.run_dir / name)
        code, out = self.launch("--pin", PASTED_ID[:8])
        self.assertEqual(target.read_text(), OWNER_TEXT)
        self.assertFalse((self.run_dir / "run.json").is_symlink())
        return code, out

    def test_launcher__a_pin_never_takes_the_lock_through_a_link(self):
        """SW-11: --pin writes run.json under the state tool's lock, which it opened for writing."""
        code, out = self.pin_with(".session-state.lock")
        self.assertNotEqual(code, 0, out)
        self.assertIn(".session-state.lock", out)

    def test_launcher__a_pin_never_writes_run_json_through_a_tmp_link(self):
        """SW-11: run.json.tmp was opened for writing, and the replace then moved the link onto run.json."""
        code, out = self.pin_with("run.json.tmp")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_json().get("session_id"), PASTED_ID)

    def test_launcher__a_pin_never_appends_its_ledger_entry_through_a_link(self):
        """SW-11: the pin's ledger entry is the third launcher ledger append."""
        code, out = self.pin_with("LEDGER.md")
        self.assertNotEqual(code, 0, out)
        self.assertIn("LEDGER.md", out)


DEP_SESSION = "sample-000-dep"


class AttrSourceTests(LauncherCase):
    """AS rows (BEHAVIORS.md): the Owner's process checks a Worker's worktree out, and runs git in it, with no
    attributes read from session content, so no filter the session names runs as the Owner."""

    def setUp(self):
        super().setUp()
        (self.root / "global-attributes").write_text("*.md filter=globalmark\n")
        with (self.home / ".gitconfig").open("a") as config:
            config.write(f"[core]\n\tattributesFile = {self.root / 'global-attributes'}\n")
        for name in ("mark", "globalmark", "depmark"):
            with (self.home / ".gitconfig").open("a") as config:
                config.write(f'[filter "{name}"]\n\tsmudge = "touch {self.root / (name + "-smudge")} && cat"\n'
                             f'\tclean = "touch {self.root / (name + "-clean")} && cat"\n')
        self.repo = self.given_filtered_repo(self.root / "repo", "mark")
        self.base = self.rev(self.repo, "HEAD")
        self.worktree = self.repo / ".worktrees" / SLUG

    def given_filtered_repo(self, repo, name):
        """HEAD holds a.txt under filter `name`, CLAUDE.md under the global attributes file's filter, and
        .claude/settings.json. Its files were written, never checked out; the fixture's own `add` ran `clean`, so the
        markers are cleared after it."""
        repo.mkdir()
        self.fixture_git("init", "-q", str(repo), cwd=self.root)
        (repo / "a.txt").write_text("a\n")
        (repo / "CLAUDE.md").write_text("instructions\n")
        (repo / ".claude").mkdir()
        (repo / ".claude" / "settings.json").write_text("{}\n")
        (repo / ".gitattributes").write_text(f"*.txt filter={name}\n")
        self.fixture_git("add", "-A", cwd=repo)
        self.fixture_git("commit", "-q", "-m", "base", cwd=repo)
        self.clear_markers()
        return repo

    def clear_markers(self):
        for marker in self.root.glob("*-smudge"):
            marker.unlink()
        for marker in self.root.glob("*-clean"):
            marker.unlink()

    def ran(self):
        return sorted(m.name for m in list(self.root.glob("*-smudge")) + list(self.root.glob("*-clean")))

    def given_briefed(self, **fields):
        self.given_run(worktree=str(self.worktree), base_sha=self.base, unit_fields=({"branch": BRANCH},), **fields)

    def fixture_git(self, *args, cwd):
        return subprocess.run(GIT + list(args), cwd=cwd, env=self.env, check=True, capture_output=True, text=True).stdout

    def rev(self, where, ref):
        return self.fixture_git("rev-parse", ref, cwd=where).strip()

    def tracked_bytes(self, where):
        return {name: (where / name).read_bytes() for name in (".gitattributes", "a.txt", "CLAUDE.md", ".claude/settings.json")}

    def test_attr_source__the_launchers_worktree_runs_no_filter_and_holds_every_file(self):
        """AS-1: both `worktree add` paths, the new branch at preflight and the existing branch after it."""
        expected = self.tracked_bytes(self.repo)
        self.given_briefed()
        self.start()
        with self.subTest(path="new branch"):
            self.assertEqual(self.tracked_bytes(self.worktree), expected)
            self.assertEqual(self.ran(), [])
        shutil.rmtree(self.worktree)
        self.fixture_git("worktree", "prune", cwd=self.repo)
        self.clear_markers()
        self.given_implementing(worktree=str(self.worktree), base_sha=self.base, unit_fields=({"branch": BRANCH},))
        self.start("--resume", NEW_ID)
        with self.subTest(path="existing branch"):
            self.assertEqual(self.tracked_bytes(self.worktree), expected)
            self.assertEqual(self.ran(), [])

    def test_attr_source__a_dependency_checkout_runs_no_filter_and_holds_every_file(self):
        """AS-2: `checkouts` makes deps/<session> as the Owner too."""
        dep = self.given_filtered_repo(self.root / "dep", "depmark")
        self.given_owner_repos(self.repo, dep)
        ref = self.rev(dep, "HEAD")
        self.given_briefed(depends_on=[{"session": DEP_SESSION, "repo": "dep", "path": str(dep), "ref": ref, "build_output": ""}])
        self.start()
        checkout = self.run_dir / "deps" / DEP_SESSION
        self.assertEqual(self.tracked_bytes(checkout), self.tracked_bytes(dep))
        self.assertEqual(self.rev(checkout, "HEAD"), ref)
        self.assertEqual(self.ran(), [])

    def test_attr_source__a_git_without_attr_source_is_refused(self):
        """AS-3: an older git would read the session's attributes again, and say nothing; nor may the refusal hand the
        Owner the plain `worktree add` line, which would."""
        real = shutil.which("git")
        shim = self.root / "old-git"
        shim.mkdir()
        (shim / "git").write_text(
            '#!/bin/sh\nfor a in "$@"; do case "$a" in --attr-source*) echo "unknown option: $a" >&2; exit 129 ;; '
            'version|--version) echo "git version 2.39.0"; exit 0 ;; esac; done\nexec "%s" "$@"\n' % real)
        (shim / "git").chmod(0o755)
        env = dict(self.env, PATH=f"{shim}:{self.env['PATH']}")
        self.given_briefed()
        for flag in ("--dry-run", "--yes"):
            with self.subTest(worktree="missing", flag=flag):
                self.stub_calls.write_text("")
                code, out = self.launch(flag, env=env)
                self.assertNotEqual(code, 0, out)
                self.assertIn("2.41.0", out)
                self.assertNotIn("worktree add", out)
                self.assertFalse(self.worktree.exists())
                self.assertEqual(self.stub_calls.read_text(), "")
        # Refused on run.json before any attributes probe, and --pin, which makes no worktree: still no line to run.
        (self.home / ".claude/sessions").mkdir(parents=True, exist_ok=True)
        (self.home / ".claude/sessions" / f"{PASTED_ID[:8]}.json").write_text(json.dumps({"sessionId": PASTED_ID, "cwd": str(self.worktree)}))
        for case, fields, flags in (("base not a commit", {"base_sha": "1" * 40}, ("--dry-run", "--yes")),
                                    ("past preflight, no branch", {"phase": "working"}, ("--dry-run", "--yes")),
                                    ("pin", {}, ("--pin",))):
            for flag in flags:
                with self.subTest(worktree="missing", refused=case, flag=flag):
                    self.given_briefed()
                    self.rewrite_run(**fields)
                    code, out = self.launch(*((flag, PASTED_ID[:8]) if flag == "--pin" else (flag,)), env=env)
                    self.assertNotEqual(code, 0, out)
                    self.assertIn("2.41.0", out)
                    self.assertNotIn("worktree add", out)
                    self.assertFalse(self.worktree.exists())
        self.given_briefed()
        self.start()
        for flag in ("--dry-run", "--yes"):
            with self.subTest(worktree="present", flag=flag):
                self.stub_calls.write_text("")
                code, out = self.launch(flag, env=env)
                self.assertNotEqual(code, 0, out)
                self.assertIn("2.41.0", out)
                self.assertEqual(self.stub_calls.read_text(), "")

    def test_attr_source__the_launchers_status_writes_no_index(self):
        """AS-4: a Worker's shell writes its worktree's admin dir; git writes a refreshed index through a link there,
        onto whatever file it names, another repository's index included."""
        self.given_briefed()
        self.start()
        admin = Path(self.fixture_git("rev-parse", "--absolute-git-dir", cwd=self.worktree).strip())
        copy = self.root / "another-index"
        shutil.copy(admin / "index", copy)
        (admin / "index").unlink()
        (admin / "index").symlink_to(copy)
        before = copy.read_bytes()
        stamp = time.time() + 60
        os.utime(self.worktree / "CLAUDE.md", (stamp, stamp))
        code, out = self.plan()
        self.assertEqual(copy.read_bytes(), before, out)

    def test_attr_source__the_launchers_status_runs_no_clean(self):
        """AS-5: `status` passes a stat-dirty file through `clean`; the launcher runs it on every launch over a worktree that exists."""
        self.given_briefed()
        self.start()
        self.clear_markers()
        stamp = time.time() + 60
        os.utime(self.worktree / "a.txt", (stamp, stamp))
        os.utime(self.worktree / "CLAUDE.md", (stamp, stamp))
        code, out = self.plan()
        self.assertEqual(self.ran(), [], out)



DIRECT_PROMPT = "Build directly from the briefing at %s: read it in full, and follow it."


class DirectLaunchTests(LauncherCase):
    """DL rows (BEHAVIORS.md): `--direct` makes a direct build's worktree on the Worker's hardened path and starts the
    build in it, every argv value held to its shape first."""

    def setUp(self):
        # Named, not super(): TicketlessDirectTests borrows this setUp without inheriting the DL tests.
        LauncherCase.setUp(self)
        self.projects = self.root / "owner-projects"
        self.repo = self.root / "repo"
        subprocess.run(GIT + ["init", "-q", str(self.repo)], check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "base"], cwd=self.repo, check=True, capture_output=True)
        self.base = self.rev(self.repo, "HEAD")
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "after the base"], cwd=self.repo, check=True, capture_output=True)
        self.with_projects_root()
        self.project = self.projects / "sample"
        (self.project / "briefings").mkdir()
        self.briefing = self.project / "briefings" / (SLUG + ".md")
        self.briefing.write_text("build it\n")
        self.worktree = self.repo / ".worktrees" / SLUG
        self.cwd_file = self.root / "direct-cwd.txt"
        self.argv_file = self.root / "direct-argv.txt"
        self.given_registering_stub()
        self.log = self.given_recording_git()

    def with_projects_root(self):
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
        self.given_launch_json(dict(config, projects_root=str(self.projects)))

    def given_registering_stub(self, registered_cwd='"$(pwd -P)"'):
        """A `claude` that records its argv and working directory and registers its session in the scratch registry, with
        `registered_cwd` (shell) as its cwd, or registers nothing when it is None."""
        register = ("" if registered_cwd is None else
                    'jq -n --arg id "%s" --arg cwd %s \'{sessionId: $id, cwd: $cwd}\' > "$HOME/.claude/sessions/%s.json"\n'
                    % (NEW_ID, registered_cwd, NEW_ID[:8]))
        self.set_stub('pwd -P > "%s"\nprintf "%%s\\n" "$@" > "%s"\n%secho "backgrounded · %s · build"'
                      % (self.cwd_file, self.argv_file, register, NEW_ID[:8]))

    def given_launch_mode(self, mode):
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
        self.given_launch_json(dict(config, launch=mode))

    def rev(self, where, ref):
        return subprocess.run(["git", "-C", str(where), "rev-parse", ref], check=True, capture_output=True, text=True).stdout.strip()

    def values(self, **values):
        found = {"project": self.project, "slug": SLUG, "repo": self.repo, "base": self.base, "briefing": self.briefing}
        found.update(values)
        return found

    def direct(self, *flags, env=None, **values):
        """Run `--direct` with the fixture's values, each overridden by `values` (None drops the flag); returns (exit code,
        output with printf %q's backslashes dropped)."""
        argv = [BASH, str(LAUNCHER), "--direct"]
        for name, value in self.values(**values).items():
            if value is not None:
                argv += ["--" + name, str(value)]
        done = subprocess.run(argv + list(flags), env=env or self.env, cwd=self.root, capture_output=True)
        return done.returncode, (done.stdout + done.stderr).decode(errors="replace").replace("\\", "")

    def grants_tool(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "role_grants.py"), *args], env=self.env, capture_output=True, text=True)

    def started_argv(self):
        return self.argv_file.read_text().splitlines() if self.argv_file.exists() else None

    def worktree_adds(self):
        return [c for c in git_calls(self.log) if "worktree" in c and "add" in c[c.index("worktree"):]]

    def repository_calls(self):
        """WorktreeCreationTests' filter: every git call but those a refusal's hint may run (hint_call)."""
        return [c for c in git_calls(self.log) if not hint_call(c)]

    def branch_exists(self, repo=None):
        return subprocess.run(["git", "-C", str(repo or self.repo), "rev-parse", "--verify", "--quiet", "refs/heads/" + BRANCH],
                              capture_output=True).returncode == 0

    def assert_refused(self, code, out, named, before_git=False):
        self.assertEqual(code, 1, out)
        self.assertIn(named, out)
        self.assertNotIn("command:", out)
        self.assertEqual(self.worktree_adds(), [])
        self.assertIsNone(self.started_argv(), out)
        if before_git:
            self.assertEqual(self.repository_calls(), [], out)

    def fresh(self):
        """No worktree, branch, stub record or git record left by a subtest before."""
        subprocess.run(GIT + ["worktree", "remove", "--force", str(self.worktree)], cwd=self.repo, capture_output=True)
        subprocess.run(GIT + ["worktree", "prune"], cwd=self.repo, capture_output=True)
        subprocess.run(GIT + ["branch", "-D", BRANCH], cwd=self.repo, capture_output=True)
        for leftover in (self.argv_file, self.cwd_file):
            if leftover.exists():
                leftover.unlink()
        self.log.write_text("")

    def test_direct__the_worktree_is_made_at_the_convention_path_on_the_convention_branch_from_the_base(self):
        """DL-1: a direct build has no run.json, and no sandboxed role can write the repository's git directory."""
        code, out = self.direct("--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.rev(self.worktree, "HEAD"), self.base)
        branch = subprocess.run(["git", "-C", str(self.worktree), "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True)
        self.assertEqual(branch.stdout.strip(), BRANCH)
        add = self.worktree_adds()
        self.assertEqual(len(add), 1, add)
        self.assertEqual(add[0][add[0].index("add"):], ["add", "--no-checkout", "-b", BRANCH, "--end-of-options", str(self.worktree), self.base])

    def test_direct__a_repository_not_in_repos_is_refused_and_nothing_is_created(self):
        """DL-2: launch.json's `repos` is the Owner's word on which clones the Owner-side tools run git in."""
        stray = self.root / "stray"
        subprocess.run(GIT + ["init", "-q", str(stray)], check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=stray, check=True, capture_output=True)
        self.log.write_text("")
        code, out = self.direct("--yes", repo=stray, base=self.rev(stray, "HEAD"))
        self.assert_refused(code, out, "repos", before_git=True)
        self.assertFalse((stray / ".claude").exists())
        self.assertFalse(self.branch_exists(stray))

    def test_direct__a_base_that_is_not_a_full_commit_id_of_the_repository_is_refused(self):
        """DL-3: a short id can come to name another object, and only a commit's own id gives a branch."""
        tree = self.rev(self.repo, "HEAD^{tree}")
        subprocess.run(GIT + ["tag", "-a", "-m", "a tag", "v1", self.base], cwd=self.repo, check=True, capture_output=True)
        tag = self.rev(self.repo, "refs/tags/v1")
        for base, before_git in (("abc1234", True), ("g" * 40, True), ("1" * 40, False), (tree, False), (tag, False)):
            with self.subTest(base=base):
                self.log.write_text("")
                code, out = self.direct("--yes", base=base)
                self.assert_refused(code, out, "--base", before_git=before_git)
                self.assertFalse(self.worktree.exists())
                self.assertFalse(self.branch_exists())

    def test_direct__a_slug_or_branch_off_the_convention_is_refused(self):
        """DL-4: the slug names the worktree's directory and the branch; the launcher holds it to a unit name, and
        role_grants.py, which the Owner can run by hand, to one path segment and a branch git accepts."""
        for slug in ("-x", "a/b", "..", "Sample-001-X", "sample-x"):
            with self.subTest(launcher=slug):
                self.log.write_text("")
                code, out = self.direct("--yes", slug=slug)
                self.assert_refused(code, out, "--slug", before_git=True)
        for slug, named in (("a/b", "slug"), ("..", "slug"), (SLUG + ".lock", "branch")):
            with self.subTest(role_grants=slug):
                self.log.write_text("")
                done = self.grants_tool("direct", str(self.project), str(self.repo), slug, self.base, str(self.briefing), "plan")
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertIn(named, done.stderr)
                self.assertEqual(self.repository_calls(), [])
        self.assertFalse((self.repo / ".claude").exists())

    def test_direct__a_link_or_a_dot_at_any_prefix_of_the_repo_the_worktree_or_the_briefing_is_refused(self):
        """DL-5: a link the Lead or a session planted would point the Owner's git, or the prompt, somewhere it chose."""
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        other = self.root / "other-briefings"
        other.mkdir()
        (other / (SLUG + ".md")).write_text("other\n")
        (self.root / "repo-link").symlink_to(self.repo)
        (self.projects / "alias").symlink_to(self.project)
        plants = {
            "repo through a link": (dict(repo=self.root / "repo-link"), None, "repo-link"),
            "repo holding ..": (dict(repo=f"{self.root}/elsewhere/../repo"), None, "`..`"),
            ".worktrees a link": ({}, (self.repo / ".worktrees", elsewhere), ".worktrees"),
            "the worktree a link": ({}, (self.worktree, elsewhere), SLUG),
            "project through a link": (dict(project=self.projects / "alias", briefing=self.projects / "alias" / "briefings" / (SLUG + ".md")), None, "alias"),
            "briefings a link": (dict(project=self.projects / "linked", briefing=self.projects / "linked" / "briefings" / (SLUG + ".md")),
                                 (self.projects / "linked" / "briefings", other), "briefings"),
            "the briefing a link": (dict(briefing=self.project / "briefings" / "linked.md"),
                                    (self.project / "briefings" / "linked.md", other / (SLUG + ".md")), "linked.md"),
            "briefing holding ..": (dict(briefing=f"{self.project}/briefings/../briefings/{SLUG}.md"), None, "`..`"),
            "briefing holding .": (dict(briefing=f"{self.project}/briefings/./{SLUG}.md"), None, "`.`"),
        }
        for what, (values, plant, named) in plants.items():
            with self.subTest(what):
                self.log.write_text("")
                if plant:
                    link, target = plant
                    link.parent.mkdir(parents=True, exist_ok=True)
                    link.symlink_to(target)
                code, out = self.direct("--yes", **values)
                if plant:
                    link.unlink()
                self.assert_refused(code, out, named)
                self.assertEqual(list(elsewhere.iterdir()), [])
                self.assertFalse(self.worktree.exists())
                self.assertFalse(self.branch_exists())

    def test_direct__the_launchers_checkout_runs_no_filter_the_base_names(self):
        """DL-6: the checkout runs as the Owner, unsandboxed; a filter the base's .gitattributes names, defined in the
        Owner's global config, would run there."""
        with (self.home / ".gitconfig").open("a") as config:
            config.write(f'[filter "mark"]\n\tsmudge = "touch {self.root / "mark-smudge"} && cat"\n'
                         f'\tclean = "touch {self.root / "mark-clean"} && cat"\n')
        (self.root / "seed").mkdir()
        seed = self.root / "seed"
        (seed / "a.txt").write_text("a\n")
        (seed / ".gitattributes").write_text("*.txt filter=mark\n")
        env = dict(self.env, GIT_WORK_TREE=str(seed), GIT_DIR=str(self.repo / ".git"))
        subprocess.run(GIT + ["add", "-A"], cwd=seed, env=env, check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "-m", "filtered"], cwd=seed, env=env, check=True, capture_output=True)
        base = self.rev(self.repo, "HEAD")
        for marker in self.root.glob("mark-*"):
            marker.unlink()
        code, out = self.direct("--yes", base=base)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.worktree / "a.txt").read_text(), "a\n")
        self.assertEqual((self.worktree / ".gitattributes").read_text(), "*.txt filter=mark\n")
        self.assertEqual(sorted(m.name for m in self.root.glob("mark-*")), [])

    def test_direct__an_existing_worktree_of_the_branch_is_reused_and_anything_else_there_is_refused(self):
        """DL-7: a second launch of a build finds its worktree; anything else at that path is not the build's."""
        self.assertEqual(self.direct("--yes")[0], 0)
        self.fresh_record()
        code, out = self.direct("--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.worktree_adds(), [])
        self.assertEqual(self.cwd_file.read_text().strip(), str(self.worktree))
        legacy = self.repo / ".claude" / "worktrees" / SLUG
        legacy.parent.mkdir(parents=True)
        subprocess.run(GIT + ["worktree", "move", str(self.worktree), str(legacy)], cwd=self.repo, check=True, capture_output=True)
        self.fresh_record()
        code, out = self.direct("--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.worktree_adds(), [])
        self.assertEqual(self.cwd_file.read_text().strip(), str(legacy))
        self.assertFalse(self.worktree.exists())
        subprocess.run(GIT + ["worktree", "move", str(legacy), str(self.worktree)], cwd=self.repo, check=True, capture_output=True)
        stray = self.root / "stray"
        subprocess.run(GIT + ["init", "-q", str(stray)], check=True, capture_output=True)
        subprocess.run(GIT + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=stray, check=True, capture_output=True)
        def directory():
            self.worktree.mkdir(parents=True)
            (self.worktree / "kept").write_text("kept\n")
        def a_file():
            self.worktree.parent.mkdir(parents=True, exist_ok=True)
            self.worktree.write_text("kept\n")
        def another_branch():
            subprocess.run(GIT + ["worktree", "add", "-q", "-b", "other", str(self.worktree), self.base], cwd=self.repo, check=True, capture_output=True)
        def detached():
            subprocess.run(GIT + ["worktree", "add", "-q", "--detach", str(self.worktree), self.base], cwd=self.repo, check=True, capture_output=True)
        def another_repository():
            subprocess.run(GIT + ["worktree", "add", "-q", "-b", BRANCH, str(self.worktree)], cwd=stray, check=True, capture_output=True)
        def the_branch_alone():
            subprocess.run(GIT + ["branch", BRANCH, self.base], cwd=self.repo, check=True, capture_output=True)
        for what, plant in (("a directory", directory), ("a file", a_file), ("another branch", another_branch),
                            ("detached", detached), ("another repository's", another_repository),
                            ("the branch with no worktree", the_branch_alone)):
            with self.subTest(what):
                self.fresh()
                subprocess.run(GIT + ["branch", "-D", "other"], cwd=self.repo, capture_output=True)
                plant()
                before = (sorted(str(p) for p in self.worktree.rglob("*")) if self.worktree.is_dir()
                          else self.worktree.read_text() if self.worktree.exists() else None)
                self.log.write_text("")
                code, out = self.direct("--yes")
                self.assert_refused(code, out, str(self.worktree))
                if what == "the branch with no worktree":
                    self.assertIn("branch -D", out)
                    self.assertFalse(self.worktree.exists())
                    self.assertEqual(self.rev(self.repo, BRANCH), self.base)
                    continue
                after = sorted(str(p) for p in self.worktree.rglob("*")) if self.worktree.is_dir() else self.worktree.read_text()
                self.assertEqual(after, before)
                if self.worktree.is_dir() and what != "another repository's":
                    shutil.rmtree(self.worktree)
                elif self.worktree.is_file():
                    self.worktree.unlink()
                subprocess.run(GIT + ["worktree", "remove", "--force", str(self.worktree)], cwd=stray, capture_output=True)

    def fresh_record(self):
        for leftover in (self.argv_file, self.cwd_file):
            if leftover.exists():
                leftover.unlink()
        self.log.write_text("")

    def test_direct__the_session_starts_in_the_worktree_with_documents_grants(self):
        """DL-8: a build started in the project folder has no grant on its worktree (DECISIONS.md, "U40 launched")."""
        code, out = self.direct("--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cwd_file.read_text().strip(), str(self.worktree))
        argv = self.started_argv()
        self.assertEqual(argv[argv.index("--name") + 1], "build-" + SLUG)
        blob = json.loads(argv[argv.index("--settings") + 1])
        document = self.grants_tool("document")
        self.assertEqual(document.returncode, 0, document.stderr)
        expected = json.loads(document.stdout)
        leaf = f"{self.worktree}/**/.git"
        expected["sandbox"]["filesystem"]["denyWrite"].append(leaf)
        expected["permissions"]["deny"] += [f"Edit(/{leaf})", f"Edit(/{leaf}/**)"]
        expected["sandbox"]["excludedCommands"] = ["rw-git *"]
        expected["permissions"]["allow"] = ["Bash(rw-git *)"]
        self.assertEqual({k: blob[k] for k in ("permissions", "sandbox")}, expected)
        for granted in blob["permissions"]["additionalDirectories"]:
            self.assertIn(f"{granted}/**/.git", blob["sandbox"]["filesystem"]["denyWrite"], granted)

    def test_direct__the_prompt_is_the_fixed_sentence_and_a_briefing_elsewhere_is_refused(self):
        """DL-9: nothing free-form passes from argv into the prompt; only a briefing file's path, in its shape, does."""
        code, out = self.direct("--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.started_argv()[-1], DIRECT_PROMPT % self.briefing)
        (self.projects / "other" / "briefings").mkdir(parents=True)
        (self.project / "briefings" / "deeper").mkdir()
        (self.project / "briefings" / "a-dir.md").mkdir()
        (self.project / "briefings" / "notes.txt").write_text("x\n")
        (self.project / "briefings" / "with space.md").write_text("x\n")
        os.link(self.briefing, self.project / "briefings" / "hard.md")
        places = {"in the project folder": self.project / (SLUG + ".md"),
                  "in another project": self.projects / "other" / "briefings" / (SLUG + ".md"),
                  "a folder deeper": self.project / "briefings" / "deeper" / (SLUG + ".md"),
                  "with a space": self.project / "briefings" / "with space.md",
                  "not markdown": self.project / "briefings" / "notes.txt",
                  "a directory": self.project / "briefings" / "a-dir.md",
                  "a hard link": self.project / "briefings" / "hard.md",
                  "missing": self.project / "briefings" / "missing.md"}
        for path in places.values():
            if not path.exists() and path.name != "missing.md":
                path.write_text("x\n")
        for what, path in places.items():
            with self.subTest(what):
                self.fresh()
                code, out = self.direct("--yes", briefing=path)
                self.assert_refused(code, out, "--briefing")
                self.assertFalse(self.worktree.exists())

    def test_direct__paste_hands_off_the_line_and_starts_nothing(self):
        """DL-10: the launch key decides who starts the session, as for every other shape."""
        self.given_launch_mode("paste")
        code, out = self.direct("--yes")
        self.assertEqual(code, 0, out)
        self.assertIsNone(self.started_argv())
        self.assertIn("paste this yourself:", out)
        line = out.split("paste this yourself:\n", 1)[1].splitlines()[0]
        self.assertTrue(line.startswith('cd %s && [ "$(pwd -P)" = %s ] &&' % (self.worktree, self.worktree)), line)
        self.assertIn(DIRECT_PROMPT % self.briefing, line)
        self.assertIn("launch is yours", out)
        self.assertIn("hand-off via", (self.project / "DECISIONS.md").read_text())

    def test_direct__a_registry_cwd_that_is_not_the_worktree_fails_the_launch_naming_both(self):
        """DL-11: a build that started anywhere but its worktree has no grant on it, and says nothing."""
        self.given_registering_stub(registered_cwd=f'"{self.project}"')
        code, out = self.direct("--yes")
        self.assertEqual(code, 1, out)
        refusal = out.split("refusing: ", 1)[-1]
        self.assertIn(str(self.worktree), refusal)
        self.assertIn(str(self.project), refusal)
        self.fresh()
        self.given_registering_stub(registered_cwd=None)
        for stale in (self.home / ".claude/sessions").glob("*.json"):
            stale.unlink()
        code, out = self.direct("--yes")
        self.assertEqual(code, 1, out)
        refusal = out.split("refusing: ", 1)[-1]
        self.assertIn(str(self.worktree), refusal)
        self.assertIn("no cwd", refusal)

    def test_direct__a_dry_run_prints_the_plan_and_creates_nothing(self):
        """DL-12: the Lead reads the plan before the Owner's process writes anything."""
        code, out = self.direct("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("worktree add -b %s %s %s" % (BRANCH, self.worktree, self.base), out)
        self.assertIn("build-" + SLUG, out)
        self.assertIn(DIRECT_PROMPT % self.briefing, out)
        self.assertFalse(self.worktree.exists())
        self.assertFalse(self.branch_exists())
        self.assertFalse((self.project / "DECISIONS.md").exists())
        self.assertIsNone(self.started_argv())
        self.assertEqual(self.worktree_adds(), [])

    def test_direct__the_model_effort_and_other_shapes_flags_are_refused_by_name(self):
        """DL-13: the model reaches --model and the --settings JSON; the other shapes' flags mean nothing here."""
        for flags, named in ((("--model", 'op"us'), "flag"), (("--effort", "huge"), "effort"),
                             (("--run-dir", str(self.run_dir)), "--run-dir"), (("--name", "x"), "--name"),
                             (("--planner", "brief"), "--planner")):
            with self.subTest(flags=flags):
                code, out = self.direct("--dry-run", *flags)
                self.assertEqual(code, 1, out)
                self.assertIn(named, out)
                self.assertNotIn("command:", out)
        self.given_worktree_for_worker()
        for flag in ("--repo", "--base", "--briefing"):
            with self.subTest(without_direct=flag):
                code, out = self.launch("--dry-run", flag, "x")
                self.assertEqual(code, 1, out)
                self.assertIn("go with --direct", out)
                self.assertNotIn("command:", out)

    def given_worktree_for_worker(self):
        """A launchable Worker session beside the fixture, so a direct-only flag is the one thing wrong with its launch."""
        worktree = self.root / "worktrees" / "wt"
        worktree.parent.mkdir()
        subprocess.run(GIT + ["worktree", "add", "-q", "-b", "robowright/sample-001-x", str(worktree)], cwd=self.repo, check=True, capture_output=True)
        self.given_run(worktree=str(worktree))


class TicketlessDirectTests(LauncherCase):
    """TL-6 (BEHAVIORS.md): DL's fixture and helpers, borrowed so the DL tests do not run twice, under the desktop
    example's ticket shape."""

    with_projects_root = DirectLaunchTests.with_projects_root
    given_registering_stub = DirectLaunchTests.given_registering_stub
    rev = DirectLaunchTests.rev
    values = DirectLaunchTests.values
    direct = DirectLaunchTests.direct
    started_argv = DirectLaunchTests.started_argv
    worktree_adds = DirectLaunchTests.worktree_adds
    assert_refused = DirectLaunchTests.assert_refused

    def setUp(self):
        DirectLaunchTests.setUp(self)
        config = json.loads((self.home / ".claude/robowright/launch.json").read_text())
        self.given_launch_json(dict(config, unit=json.loads(DESKTOP_EXAMPLE.read_text())["unit"]))

    def test_direct__a_plain_slug_is_a_unit_name_under_a_ticket_shape(self):
        """TL-6: in_unit_form accepts a plain slug (TICKET_FORM, then SLUG_REGEX) when the regex is set; DL-4."""
        code, out = self.direct("--dry-run", slug="export-csv")
        self.assertEqual(code, 0, out)
        self.assertIn("worktree add -b robowright/export-csv %s/.worktrees/export-csv " % self.repo, out)

        code, out = self.direct("--dry-run", slug="Not-A-Unit_x")
        self.assert_refused(code, out, "--slug")


if __name__ == "__main__":
    unittest.main()
