#!/usr/bin/env python3
"""Tests for session-state.py, driven through its command line against scratch session dirs.

    python3 test_session_state.py

Every test asserts what landed in run.json or events.jsonl, never only the exit code. Each one
has been seen failing under a targeted mutation of the tool (the project's mutation ledger).
"""

import importlib.util
import inspect
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / "session-state.py"
SKILLS = HERE.parent.parent
TEMPLATE = SKILLS / "worker/templates/run.json"
ROSTER = SKILLS / "lead/scripts/run-roster.py"
COST = SKILLS / "worker/scripts/run-cost.py"
WRITE_HOOK = SKILLS / "worker/hooks/write-budget.sh"
STOP_GATE = SKILLS / "worker/hooks/stop-gate.sh"
PRECOMPACT = SKILLS / "worker/hooks/precompact.sh"
AGENTS = SKILLS.parent / "agents"
LAUNCHER = HERE / "run-launch.sh"
LEAN_TOOLS = "Bash,Read,Write,Edit,Grep,Glob,Agent,Skill,Monitor,TaskStop,ToolSearch,LSP,WebFetch,WebSearch"
# The role flags, as the launcher spells them: the word it prints is the flag with its dashes off,
# so the assertions on that word derive it from here rather than spelling the word a second time.
PLANNER_FLAG = "--planner"
EXPLAINER_FLAG = "--explainer"
PLANNER_ROLE = PLANNER_FLAG.lstrip("-")
EXPLAINER_ROLE = EXPLAINER_FLAG.lstrip("-")
SHA = "0123abc"
# Approved-list entries for the launcher's MCP tests: made-up servers, so no test depends on the real
# list or on a binary this machine happens to have. Every value is distinct, so a crossed wire shows.
MCP_GIZMO = {
    "server": "gizmo",
    "install": "never installed: a test fixture",
    "command": "gizmo-server",
    "args": ["serve", "--stdio"],
    "env": {"GIZMO_TELEMETRY": "off", "GIZMO_GREETING": "hello world"},
    "version_args": ["version"],
    "version_pin": "2.7",
    "workflows_env": "GIZMO_WORKFLOWS",
    "workflows": ["alpha", "beta", "gamma"],
    "allow": ["mcp__gizmo__*"],
}
MCP_WIDGET = {
    "server": "widget",
    "install": "never installed: a test fixture",
    "command": "widget-server",
    "args": ["--stdio"],
    "env": {"WIDGET_MODE": "quiet"},
    "version_args": ["--version"],
    "version_pin": "1.4",
    "workflows_env": "WIDGET_GROUPS",
    "workflows": ["reads", "writes"],
    "allow": ["mcp__widget__*"],
}


HARDENING = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "log.showSignature=false"]
# A `git` that records its argv, one field per argument and one line per call, then runs the real git.
ARGV_FIELD = "\x1f"
RECORDING_GIT = f"""#!/bin/sh
for a in "$@"; do printf '%s{ARGV_FIELD}' "$a"; done >> "$GIT_ARGV_LOG"
printf '\\n' >> "$GIT_ARGV_LOG"
exec {shutil.which("git")} "$@"
"""


def git_calls(log):
    return [line.split(ARGV_FIELD)[:-1] for line in Path(log).read_text().splitlines()] if Path(log).is_file() else []


def runs_in(call, path):
    """A call that runs git inside `path`: `-C <path>` among its global options."""
    return any(call[i] == "-C" and os.path.realpath(call[i + 1]) == os.path.realpath(path) for i in range(len(call) - 1))


class SessionCase(unittest.TestCase):
    def setUp(self):
        # The temp directory sits below a link on macOS (/tmp, /var), and the launcher grants no path below a link.
        self.tmp = tempfile.TemporaryDirectory(dir=os.path.realpath(tempfile.gettempdir()))
        self.dir = Path(self.tmp.name)
        self.given_owner_repos(Path(self.tmp.name) / "worktree", Path(self.tmp.name) / "fixture" / "repo")

    def given_owner_repos(self, *repos):
        """The repositories the Owner configured, through $ROBOWRIGHT_PROJECTS_ROOT: git runs only in a worktree one of them lists."""
        projects = Path(self.tmp.name) / "owner-projects"
        (projects / "sample").mkdir(parents=True, exist_ok=True)
        entries = [{"name": f"repo-{i}", "path": str(r), "origin": "git@example.invalid:sample.git"} for i, r in enumerate(repos)]
        (projects / "sample" / "robowright.json").write_text(json.dumps({"repos": entries}) + "\n")
        # launch.json's `repos` is the other half of the trust: a scratch HOME carrying only that key.
        home = Path(self.tmp.name) / "owner-home"
        (home / ".claude/robowright").mkdir(parents=True, exist_ok=True)
        self.owner_repos = [str(r) for r in repos]
        (home / ".claude/robowright/launch.json").write_text(json.dumps({"repos": self.owner_repos}) + "\n")
        for name, value in (("ROBOWRIGHT_PROJECTS_ROOT", str(projects)), ("HOME", str(home))):
            previous = os.environ.get(name)
            os.environ[name] = value
            self.addCleanup(lambda name=name, previous=previous: os.environ.pop(name, None) if previous is None
                            else os.environ.__setitem__(name, previous))

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------ given

    def given_session(self, unit_ids=("U1", "U2"), **fields):
        for child in self.dir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        run = {
            "phase": "preflight",
            "delegation": "planner",
            "plan_review": "off",
            "max_gate_attempts": 3,
            "rotate_sessions": True,
            "rotate": None,
            "rebriefs": [],
            "stop_reason": None,
            "units": [{"id": i, "status": "todo", "head": "", "gate_attempts": 0, "gate": {"review": ""}} for i in unit_ids],
        }
        run.update(fields)
        (self.dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        (self.dir / "BRIEF.md").write_text("brief\n")
        (self.dir / "reviews").mkdir(exist_ok=True)

    def given_implementing(self, unit_ids=("U1", "U2"), **fields):
        self.given_session(unit_ids, **fields)
        self.must("preflight-pass")
        self.must("intake-complete")

    def given_gate_review(self, unit, verdict):
        path = self.dir / "reviews" / f"{unit}-gate.md"
        path.write_text(f"{verdict}\n\nfindings\n")
        # mtime granularity: make every rewrite visibly newer than the last gate event
        stamp = time.time() + self.bump()
        os.utime(path, (stamp, stamp))

    def bump(self):
        self.clock = getattr(self, "clock", 0) + 5
        return self.clock

    def given_unit_closed(self, unit):
        self.must("unit-start", "--unit", unit)
        self.given_gate_review(unit, "ADVANCE")
        self.must("gate-advance", "--unit", unit)
        # unit-close resolves --head in an existing worktree (D8), so a launcher fixture's closes on its real HEAD.
        worktree = self.run_json().get("worktree")
        head = SHA
        if isinstance(worktree, str) and os.path.isdir(worktree):
            head = subprocess.run(["git", "-C", worktree, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        self.must("unit-close", "--unit", unit, "--head", head)

    def given_rebrief_files(self, verdict="confident"):
        (self.dir / "REBRIEF.md").write_text(f"# Rebrief\n\nVerdict: {verdict}\n")
        number = len(self.run_json()["rebriefs"]) + 1
        (self.dir / f"BRIEF.r{number}.md").write_text("old\n")

    def given_stopped(self, code="verification-failed"):
        self.must("stop", "--code", code, "--detail", "why")

    def marker_env(self, **extra):
        """A worker hook honours the session marker only under the sessions root; the session dir is a temp dir, so its parent is the root."""
        return dict(os.environ, ROBOWRIGHT_SESSIONS_ROOT=str(self.dir.parent), **extra)

    def given_hand_edit(self, mutate):
        run = self.run_json()
        mutate(run)
        (self.dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")

    def given_home(self, root, sessions_root, **overrides):
        """A scratch HOME holding this install's launch.json and an empty session registry.

        The launcher reads its machine facts from `$HOME/.claude/robowright/launch.json` and
        nothing else, so HOME is the whole seam — the same one that lets each Mac's install carry its own facts.
        Returns (home, env).
        """
        home = root / "home"
        (home / ".claude/sessions").mkdir(parents=True, exist_ok=True)
        config = {
            "schema": 1,
            "sessions_root": str(sessions_root),
            "review_guide_dir": "reviews",
            "report_scope": "project-prefix",
            # Every launch test before the key existed asserts on a started stub session, which
            # is `auto`; absent means `paste`, so a test of the default removes the key.
            "launch": "auto",
            "unit": {
                "ticket_regex": None,
                "ticket_example": None,
                "slug_regex": "^[a-z0-9]+(-[a-z0-9]+)*-[0-9]{3}(-[a-z0-9]+)+$",
                "slug_example": "sample-012-note-autosave",
                "group_regex": "^([0-9]*[a-z][a-z0-9]*(-[0-9]*[a-z][a-z0-9]*)*)-[0-9]{3}(-[a-z0-9]+)+$",
            },
            "repos": self.owner_repos,
        }
        for key, value in overrides.items():
            if key in config["unit"]:
                config["unit"][key] = value
            else:
                config[key] = value
        self.write_launch_config(home, config)
        return home, dict(os.environ, HOME=str(home))

    def write_launch_config(self, home, config):
        path = home / ".claude/robowright/launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if config is None:
            if path.is_file():
                path.unlink()
        else:
            path.write_text(json.dumps(config, indent=2) + "\n")
        return path

    def given_launcher_fixture(self, **config):
        """A repo, its linked worktree with .claude ignored, and a session dir under a scratch sessions root. Returns (session, worktree, env)."""
        root = self.dir / "fixture"
        repo = root / "repo"
        repo.mkdir(parents=True)
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True)
        worktree = root / "worktrees" / "wt"
        worktree.parent.mkdir()
        subprocess.run(git + ["worktree", "add", "-q", "-b", "robowright/test", str(worktree)], cwd=repo, check=True, capture_output=True)
        (worktree / ".gitignore").write_text(".claude/\n")
        subprocess.run(git + ["add", "-A"], cwd=worktree, check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "-m", "ignore"], cwd=worktree, check=True, capture_output=True)
        session = root / "sessions" / "sample-001-x"
        session.mkdir(parents=True)
        self.dir = session
        _, env = self.given_home(root, session.parent, **config)
        return session, worktree, env

    def given_stub_claude(self, env):
        """A `claude` on PATH that appends its argv to a file and prints a backgrounded line, under a scratch HOME with no live sessions. Returns (argv file, env)."""
        root = self.dir.parent.parent
        (root / "home/.claude/sessions").mkdir(parents=True, exist_ok=True)
        stub = root / "bin"
        stub.mkdir()
        record = root / "argv.txt"
        (stub / "claude").write_text('#!/bin/bash\nprintf "%%s\\n" "$@" >> "%s"\necho "backgrounded · bbbb2222 · worker"\n' % record)
        (stub / "claude").chmod(0o755)
        return record, dict(env, HOME=str(root / "home"), PATH=f"{stub}:{os.environ['PATH']}")

    def given_stub_claude_eperm(self, env):
        """A `claude` on PATH that appends its argv to a file, prints the EPERM refusal `claude --bg` gives from a sandboxed shell, and exits 1. Returns (argv file, env)."""
        return self.given_stub_claude_failing(env, "Error: EPERM: operation not permitted, mkdir '/Users/owner/.claude/bg'")

    def given_stub_claude_failing(self, env, message):
        """A `claude` on PATH that appends its argv to a file, prints `message` to stderr, and exits 1, under a scratch HOME with no live sessions. Returns (argv file, env)."""
        root = self.dir.parent.parent
        (root / "home/.claude/sessions").mkdir(parents=True, exist_ok=True)
        stub = root / "bin"
        stub.mkdir()
        record = root / "argv.txt"
        (stub / "claude").write_text('#!/bin/bash\nprintf "%%s\\n" "$@" >> "%s"\necho %s >&2\nexit 1\n' % (record, shlex.quote(message)))
        (stub / "claude").chmod(0o755)
        return record, dict(env, HOME=str(root / "home"), PATH=f"{stub}:{os.environ['PATH']}")

    def given_approved_list(self, *entries):
        """A copy of the launcher in a scratch skills tree whose approved list holds only `entries`. Returns the copy's path.

        The launcher finds its list at `$HERE/../mcp`, HERE being its own file's resolved directory, so
        the copy is a real file (a symlink would resolve back to the real tree and the real list) and
        everything it shells out to is linked beside it. Call after given_launcher_fixture.
        """
        root = self.dir.parent.parent
        skills = root / "skills"
        scripts = skills / "robowright/scripts"
        scripts.mkdir(parents=True)
        for tool in HERE.iterdir():
            if tool.is_file() and tool.name != LAUNCHER.name:
                (scripts / tool.name).symlink_to(tool)
        launcher = scripts / LAUNCHER.name
        shutil.copy2(LAUNCHER, launcher)
        (skills / "robowright/models.json").symlink_to(HERE.parent / "models.json")
        (skills / "worker/scripts").mkdir(parents=True)
        (skills / "worker/scripts" / COST.name).symlink_to(COST)
        listing = skills / "robowright/mcp"
        listing.mkdir()
        for entry in entries:
            (listing / f"{entry['server']}.json").write_text(json.dumps(entry, indent=2) + "\n")
        return launcher

    def given_server_binary(self, env, entry, version):
        """An MCP server binary on a scratch PATH that prints `version` for the entry's exact version_args and fails on anything else. Returns (binary, env)."""
        bin_dir = (self.dir.parent.parent / "serverbin").resolve()
        bin_dir.mkdir(exist_ok=True)
        binary = bin_dir / entry["command"]
        asked = " ".join(entry["version_args"])
        binary.write_text('#!/bin/bash\n[ "$*" = %s ] || { echo "unknown arguments: $*" >&2; exit 2; }\necho %s\n' % (shlex.quote(asked), shlex.quote(version)))
        binary.chmod(0o755)
        if str(bin_dir) in env["PATH"].split(":"):
            return binary, env
        return binary, dict(env, PATH=f"{bin_dir}:{env['PATH']}")

    def given_mcp_brief(self, worktree, **fields):
        """run.json with its worktree and `fields` over the session's own; `mcp` and `mcp_config` are absent unless given."""
        run = {k: v for k, v in self.run_json().items() if k not in ("mcp", "mcp_config")}
        run.update(worktree=str(worktree.resolve()), **fields)
        (self.dir / "run.json").write_text(json.dumps(run))

    def given_committed_file(self, worktree, name):
        """A tracked file in the worktree, so it stays clean for a launch while the file is there for a glob to match."""
        (worktree / name).write_text("decoy\n")
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["add", name], cwd=worktree, check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "-m", "decoy"], cwd=worktree, check=True, capture_output=True)

    # ------------------------------------------------------------ when / then

    @staticmethod
    def run_launcher(launcher, session, env, *flags, cwd=None):
        """The launcher at `launcher` on `session` with `flags`. Returns the finished process."""
        return subprocess.run(["bash", str(launcher), "--session-dir", str(session), *flags], env=env, cwd=cwd, capture_output=True, text=True)

    @staticmethod
    def recorded_argv(record):
        """The argv the stub `claude` recorded, one element per line; empty when it never ran."""
        return record.read_text().splitlines() if record.is_file() else []

    @staticmethod
    def allow_rules(argv):
        """Every rule passed after an --allowedTools (either spelling), each flag's one value split on commas and spaces."""
        rules = []
        for at, arg in enumerate(argv):
            if arg in ("--allowedTools", "--allowed-tools"):
                rules += [rule for rule in re.split(r"[,\s]+", argv[at + 1]) if rule]
        return rules

    @staticmethod
    def built_config(argv):
        """The config passed after --mcp-config: inline JSON, or the JSON file it names."""
        value = argv[argv.index("--mcp-config") + 1]
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return json.loads(Path(value).read_text())

    @staticmethod
    def mcp_block(out):
        """The plan's `mcp:` line and any 11-space-indented lines continuing it."""
        lines = out.splitlines()
        start = next(at for at, line in enumerate(lines) if line.startswith("mcp:"))
        block = [lines[start]]
        for line in lines[start + 1:]:
            if not line.startswith(" " * 11):
                break
            block.append(line)
        return "\n".join(block)

    def tool(self, *args):
        done = subprocess.run([sys.executable, str(TOOL), str(self.dir), *args], capture_output=True, text=True)
        return done.returncode, done.stdout, done.stderr

    def must(self, *args):
        code, out, err = self.tool(*args)
        self.assertEqual(code, 0, f"{args}: {err}")
        return out

    def run_json(self):
        return json.loads((self.dir / "run.json").read_text())

    def unit(self, unit_id):
        return [u for u in self.run_json()["units"] if u["id"] == unit_id][0]

    def events(self):
        path = self.dir / "events.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []

    def state(self):
        return json.loads(self.must("status", "--json"))

    def assert_refused(self, guard, *args):
        before = (self.dir / "run.json").read_text()
        code, _, err = self.tool(*args)
        self.assertEqual(code, 2, err)
        self.assertIn(f": {guard}: ", err)
        self.assertEqual((self.dir / "run.json").read_text(), before)


class SessionStateTests(SessionCase):
    # ------------------------------------------------------------ session lifecycle

    def test_template__is_briefed_and_legal(self):
        """The shipped run.json template is a legal `briefed` session — a Planner's fresh brief would otherwise be refused at launch."""
        (self.dir / "run.json").write_text(TEMPLATE.read_text())
        info = self.state()
        self.assertEqual((info["state"], info["problems"]), ("briefed", []))

    def test_preflight_pass__moves_briefed_to_intake(self):
        """preflight-pass writes phase intake and the start time — the session would stay launchable forever otherwise."""
        self.given_session()
        self.must("preflight-pass")
        run = self.run_json()
        self.assertEqual(run["phase"], "intake")
        self.assertTrue(run["started_at"])
        self.assertEqual(run["updated_at"], self.events()[-1]["at"])

    def test_preflight_pass__refused_without_brief(self):
        """No BRIEF.md, no start — a session with no contract would run."""
        self.given_session()
        (self.dir / "BRIEF.md").unlink()
        self.assert_refused("brief-exists", "preflight-pass")

    def test_event__refused_from_a_state_the_table_does_not_list(self):
        """finish from briefed is refused — a session could be marked done without running."""
        self.given_session()
        self.assert_refused("from-state", "finish")

    def test_refusal__is_logged_and_does_not_count_as_applied(self):
        """A refusal lands in events.jsonl as refused — the Lead loses the signal, or check reads it as a state change."""
        self.given_session()
        self.tool("finish")
        self.assertEqual([(e["event"], e["refused"], e["guard"]) for e in self.events()], [("finish", True, "from-state")])
        self.assertEqual(self.state()["problems"], [])

    def test_intake_complete__refused_when_unit_ids_repeat(self):
        """Duplicate unit ids are refused — every later --unit would address the wrong unit."""
        self.given_session()
        self.must("preflight-pass")
        self.given_hand_edit(lambda run: run["units"][1].update(id="U1"))
        self.assert_refused("stored-state-legal", "intake-complete")

    def test_intake_complete__refused_with_no_units(self):
        """An empty unit list is refused — implementing with nothing to implement goes straight to end-of-stack."""
        self.given_session(unit_ids=())
        self.must("preflight-pass")
        self.assert_refused("units-populated", "intake-complete")

    def test_intake_complete__refused_when_a_unit_has_no_id(self):
        """Every unit needs an id — no event could ever address it."""
        self.given_session()
        self.must("preflight-pass")
        self.given_hand_edit(lambda run: run["units"][1].update(id=""))
        self.assert_refused("units-populated", "intake-complete")

    def test_begin_end_of_stack__refused_with_an_open_unit(self):
        """end-of-stack needs every unit done — the whole-change review would run on a partial change."""
        self.given_implementing()
        self.given_unit_closed("U1")
        self.assert_refused("all-units-done", "begin-end-of-stack")

    def test_finish__refused_until_each_handoff_file_exists(self):
        """done needs the end-of-stack review, HANDOFF.md and HANDBACK.md — intake would read a record that is not there."""
        self.given_implementing(unit_ids=("U1",))
        self.given_unit_closed("U1")
        self.must("begin-end-of-stack")
        needed = {"end-of-stack-review-exists": "reviews/end-of-stack.md", "handoff-exists": "HANDOFF.md", "handback-exists": "HANDBACK.md"}
        contents = {"reviews/end-of-stack.md": "ADVANCE\n", "HANDOFF.md": "x\n", "HANDBACK.md": "x\n"}
        for guard, rel in needed.items():
            for other, text in contents.items():
                (self.dir / other).write_text(text)
            (self.dir / rel).unlink()
            self.assert_refused(guard, "finish")
        for rel, text in contents.items():
            (self.dir / rel).write_text(text)
        self.must("finish")
        self.assertEqual(self.run_json()["phase"], "done")

    # ------------------------------------------------------------ unit gate loop

    def test_unit_start__refused_while_a_predecessor_is_open(self):
        """Units run in order — two in flight, or a stack built on an ungated base."""
        self.given_implementing()
        self.assert_refused("predecessors-done", "unit-start", "--unit", "U2")

    def test_unit_start__defaults_to_the_first_todo_unit(self):
        """Without --unit the first todo unit starts — the Worker would have to restate what run.json already says."""
        self.given_implementing()
        self.must("unit-start")
        self.assertEqual((self.unit("U1")["status"], self.unit("U2")["status"]), ("building", "todo"))

    def test_unit_event__refused_outside_implementing(self):
        """A unit cannot move while the session is stopped — work would continue past a stop."""
        self.given_implementing()
        self.given_stopped()
        self.assert_refused("session-is-implementing", "unit-start", "--unit", "U1")

    def test_gate_advance__refused_when_the_review_says_hold(self):
        """The builder cannot advance over a HOLD — the grader would be the author."""
        self.given_implementing()
        self.must("unit-start")
        self.given_gate_review("U1", "HOLD")
        self.assert_refused("gate-review-says-advance", "gate-advance")

    def test_gate_hold__refused_when_the_review_says_advance(self):
        """gate-hold needs a HOLD — an attempt would be burned against a passing review."""
        self.given_implementing()
        self.must("unit-start")
        self.given_gate_review("U1", "ADVANCE")
        self.assert_refused("gate-review-says-hold", "gate-hold")

    def test_gate_hold__counts_the_attempt_and_records_the_review(self):
        """A HOLD costs one attempt and names its review — the cap would never be reached."""
        self.given_implementing()
        self.must("unit-start")
        self.given_gate_review("U1", "HOLD")
        self.must("gate-hold")
        unit = self.unit("U1")
        self.assertEqual((unit["status"], unit["gate_attempts"], unit["gate"]["review"]), ("held", 1, "reviews/U1-gate.md"))

    def test_gate__refused_until_the_review_is_rewritten(self):
        """One review buys one verdict — a fix could be advanced on the review of the code before it."""
        self.given_implementing()
        self.must("unit-start")
        self.given_gate_review("U1", "HOLD")
        self.must("gate-hold")
        (self.dir / "reviews" / "U1-gate.md").write_text("ADVANCE\n")
        stale = self.events()[-1]["review_mtime"]
        os.utime(self.dir / "reviews" / "U1-gate.md", (stale, stale))
        self.assert_refused("gate-review-is-fresh", "gate-advance")

    def test_gate__refused_at_the_attempt_cap(self):
        """At max_gate_attempts neither verdict is accepted — the only exit is a verification-failed stop."""
        self.given_implementing(max_gate_attempts=2)
        self.must("unit-start")
        for _ in range(2):
            self.given_gate_review("U1", "HOLD")
            self.must("gate-hold")
        self.given_gate_review("U1", "ADVANCE")
        self.assert_refused("gate-attempts-under-cap", "gate-advance")
        self.given_gate_review("U1", "HOLD")
        self.assert_refused("gate-attempts-under-cap", "gate-hold")
        self.must("stop", "--code", "verification-failed", "--detail", "cap")

    def test_unit_close__refused_before_an_advance(self):
        """A building unit cannot close — a unit would be done with no gate verdict."""
        self.given_implementing()
        self.must("unit-start")
        self.assert_refused("from-state", "unit-close", "--unit", "U1", "--head", SHA)

    def test_unit_event__refused_when_no_unit_is_in_a_state_it_applies_to(self):
        """Without --unit and nothing gated, close is refused — it would otherwise pick a unit the event does not apply to."""
        self.given_implementing()
        self.must("unit-start")
        self.assert_refused("from-state", "unit-close", "--head", SHA)

    def test_unit_event__refused_for_a_unit_run_json_does_not_have(self):
        """An unknown --unit is refused by name — a typo would otherwise fall through to the first candidate."""
        self.given_implementing()
        self.assert_refused("unit-known", "unit-start", "--unit", "U9")

    def test_unit_close__refused_when_the_review_was_rewritten_to_hold(self):
        """close re-reads the review — a re-gate that came back HOLD after the advance would be ignored."""
        self.given_implementing()
        self.must("unit-start")
        self.given_gate_review("U1", "ADVANCE")
        self.must("gate-advance")
        self.given_gate_review("U1", "HOLD")
        self.assert_refused("gate-review-says-advance", "unit-close", "--head", SHA)

    def test_unit_close__records_the_head(self):
        """close writes done and the head SHA — the next unit would have no base to branch from."""
        self.given_implementing()
        self.given_unit_closed("U1")
        self.assertEqual((self.unit("U1")["status"], self.unit("U1")["head"]), ("done", SHA))

    def test_unit_close__refused_without_a_sha(self):
        """head must look like a commit — prose in head breaks the stop-gate fingerprint and the roster."""
        self.given_implementing()
        self.must("unit-start")
        self.given_gate_review("U1", "ADVANCE")
        self.must("gate-advance")
        self.assert_refused("head-given", "unit-close", "--head", "the tip")

    # ------------------------------------------------------------ rotation

    def test_request_rotate__refused_mid_unit(self):
        """No rotation with a unit in flight — the fresh session would start from a half-built unit."""
        self.given_implementing()
        self.given_unit_closed("U1")
        self.must("unit-start")
        self.assert_refused("no-unit-in-flight", "request-rotate")

    def test_request_rotate__refused_before_any_unit_is_done(self):
        """Rotation is a unit-boundary event — a session could rotate forever without working."""
        self.given_implementing()
        self.assert_refused("a-unit-is-done", "request-rotate")

    def test_request_rotate__refused_when_the_brief_turned_rotation_off(self):
        """rotate_sessions false means continue — the session would end its turn with nobody to restart it."""
        self.given_implementing(rotate_sessions=False)
        self.given_unit_closed("U1")
        self.assert_refused("rotation-enabled", "request-rotate")

    def test_request_rotate__refused_once_the_last_unit_is_closed(self):
        """The last unit goes on to end-of-stack in the same session — a rotation here arms next_unit null, and no launcher path says what a fresh session does with it."""
        self.given_implementing(unit_ids=("U1", "U2"))
        self.given_unit_closed("U1")
        self.given_unit_closed("U2")
        self.assert_refused("a-unit-is-todo", "request-rotate")

    def test_request_rotate__refused_once_the_last_unit_is_closed_even_naming_a_next_unit(self):
        """--next-unit does not reopen a finished stack — the fresh session would be sent to a unit that is already done."""
        self.given_implementing(unit_ids=("U1", "U2"))
        self.given_unit_closed("U1")
        self.given_unit_closed("U2")
        self.assert_refused("a-unit-is-todo", "request-rotate", "--next-unit", "U2")

    def test_rotation__round_trip_names_the_next_unit_and_returns_to_implementing(self):
        """request-rotate arms the rotation with the next unit; rotation-resumed consumes it — the Stop hook and launcher key on exactly these fields."""
        self.given_implementing()
        self.given_unit_closed("U1")
        self.must("request-rotate")
        rotate = self.run_json()["rotate"]
        self.assertTrue(rotate["requested_at"])
        self.assertEqual((rotate["resumed_at"], rotate["next_unit"], self.state()["state"]), (None, "U2", "awaiting-rotation"))
        self.must("rotation-resumed")
        self.assertTrue(self.run_json()["rotate"]["resumed_at"])
        self.assertEqual(self.state()["state"], "implementing")

    # ------------------------------------------------------------ stop, resume, rebrief

    def test_stop__records_where_it_stopped_and_cancels_a_pending_rotation(self):
        """stop keeps the phase it left and clears rotate — resume would not know where to return, or the session reads as both stopped and rotating."""
        self.given_implementing()
        self.given_unit_closed("U1")
        self.must("request-rotate")
        self.given_stopped("base-moved")
        run = self.run_json()
        self.assertEqual((run["phase"], run["rotate"]), ("stopped", None))
        self.assertEqual((run["stop_reason"]["code"], run["stop_reason"]["detail"], run["stop_reason"]["phase_before"]), ("base-moved", "why", "implement"))

    def test_stop__refused_with_an_unknown_code(self):
        """Only the table's stop codes — the Lead's routing table has no row for anything else."""
        self.given_implementing()
        self.assert_refused("stop-code-known", "stop", "--code", "tired", "--detail", "x")

    def test_stop__refused_without_detail(self):
        """detail is required — the Lead reads it before anything else."""
        self.given_implementing()
        self.assert_refused("detail", "stop", "--code", "budget", "--detail", " ")

    def test_stop__owner_stop_needs_the_stop_file(self):
        """owner-stop is only legal while STOP exists — a Worker could escalate any stop to Owner-only."""
        self.given_implementing()
        self.assert_refused("stop-file-present-for-owner-stop", "stop", "--code", "owner-stop", "--detail", "x")
        (self.dir / "STOP").write_text("")
        self.must("stop", "--code", "owner-stop", "--detail", "x")

    def test_resume__returns_to_the_phase_it_left(self):
        """resume restores phase_before, not implement — an end-of-stack stop would re-enter the unit loop."""
        self.given_implementing(unit_ids=("U1",))
        self.given_unit_closed("U1")
        self.must("begin-end-of-stack")
        self.given_stopped()
        self.must("resume", "--by", "owner", "--decision", "go")
        run = self.run_json()
        self.assertEqual((run["phase"], run["stop_reason"]), ("end-of-stack", None))

    def test_resume__refused_while_the_stop_file_exists(self):
        """STOP must be gone first — the session would stop again at once."""
        self.given_implementing()
        (self.dir / "STOP").write_text("")
        self.given_stopped("owner-stop")
        self.assert_refused("stop-file-absent", "resume", "--by", "owner", "--decision", "go")

    def test_resume__refused_without_a_decision(self):
        """A resume carries its decision — a stop could be cleared with nothing decided."""
        self.given_implementing()
        self.given_stopped()
        self.assert_refused("decision", "resume", "--by", "owner", "--decision", "")

    def test_resume__lead_refused_at_delegation_owner(self):
        """At delegation owner every stop is the Owner's — the Lead would decide what it was never delegated."""
        self.given_implementing(delegation="owner")
        self.given_stopped()
        self.assert_refused("decider-allowed", "resume", "--by", "lead", "--decision", "go")
        self.must("resume", "--by", "owner", "--decision", "go")

    def test_resume__lead_refused_for_owner_stop(self):
        """owner-stop is the Owner's at every level — the Lead could overrule the Owner's own stop."""
        self.given_implementing()
        (self.dir / "STOP").write_text("")
        self.given_stopped("owner-stop")
        (self.dir / "STOP").unlink()
        self.assert_refused("decider-allowed", "resume", "--by", "lead", "--decision", "go")

    def test_resume__lead_refused_on_the_third_stop_and_owner_allowed(self):
        """The third stop is a rebrief or the Owner's — the Lead would keep deciding a brief that is wrong."""
        self.given_implementing()
        for _ in range(2):
            self.given_stopped()
            self.must("resume", "--by", "lead", "--decision", "go")
        self.given_stopped()
        self.assert_refused("not-rebrief-due-for-lead", "resume", "--by", "lead", "--decision", "go")
        self.must("resume", "--by", "owner", "--decision", "go")

    def test_resume__legacy_stop_beside_a_working_phase_returns_to_that_phase(self):
        """A stop code with phase still implement (older sessions) reads as stopped and resumes to implement — those sessions would be unresumable."""
        self.given_session(phase="implement", stop_reason={"code": "budget", "detail": "x"})
        self.assertEqual(self.state()["state"], "stopped")
        self.must("adopt", "--by", "owner", "--reason", "legacy")
        self.must("resume", "--by", "owner", "--decision", "go")
        run = self.run_json()
        self.assertEqual((run["phase"], run["stop_reason"]), ("implement", None))

    def test_rebrief__restores_the_phase_arms_a_rotation_and_resets_the_stop_count(self):
        """rebrief clears the stop, records itself, and arms a rotation — the launcher's rotate path would refuse, or the Lead stays locked out after it."""
        self.given_implementing()
        for _ in range(2):
            self.given_stopped()
            self.must("resume", "--by", "lead", "--decision", "go")
        self.given_stopped("one-way-door")
        (self.dir / "REBRIEF.md").write_text("# Rebrief 1\n\nVerdict: confident\n")
        (self.dir / "BRIEF.r1.md").write_text("old\n")
        self.must("rebrief", "--verdict", "confident", "--why", "units re-cut")
        run = self.run_json()
        self.assertEqual((run["phase"], run["stop_reason"], run["rotate"]["reason"], run["rotate"]["next_unit"]), ("implement", None, "rebrief", "U1"))
        entry = run["rebriefs"][0]
        self.assertEqual((entry["n"], entry["verdict"], entry["why"], entry["stop_code"]), (1, "confident", "units re-cut", "one-way-door"))
        info = self.state()
        self.assertEqual((info["state"], info["stops_since_rebrief"]), ("awaiting-rotation", 0))

    def test_rebrief__a_unit_in_flight_returns_to_todo_and_the_session_can_rotate(self):
        """A rebrief of a mid-unit stop resets that unit — it would otherwise write rotating-mid-unit, which no event, launcher or adopt can leave."""
        self.given_implementing()
        self.must("unit-start")
        self.given_gate_review("U1", "HOLD")
        self.must("gate-hold")
        self.given_stopped("one-way-door")
        self.given_rebrief_files()
        self.must("rebrief", "--verdict", "confident", "--why", "x")
        unit = self.unit("U1")
        self.assertEqual((unit["status"], unit["gate_attempts"], self.state()["problems"]), ("todo", 0, []))
        self.assertEqual(self.tool("check-op", "rotate")[0], 0)

    def test_rebrief__the_planner_may_recut_open_units_but_not_done_ones(self):
        """Units not done may be replaced before the event; a done unit may not change — a rebrief could rewrite history, or be refused for doing its job."""
        self.given_implementing()
        self.given_unit_closed("U1")
        self.given_stopped()
        self.given_rebrief_files()
        self.given_hand_edit(lambda run: run.update(units=[run["units"][0], {"id": "U2a", "status": "todo"}, {"id": "U2b", "status": "todo"}]))
        self.must("rebrief", "--verdict", "confident", "--why", "split U2")
        self.assertEqual(([u["id"] for u in self.run_json()["units"]], self.state()["problems"]), (["U1", "U2a", "U2b"], []))

        self.given_implementing()
        self.given_unit_closed("U1")
        self.given_stopped()
        self.given_rebrief_files()
        self.given_hand_edit(lambda run: run["units"][0].update(head="fffffff"))
        self.assert_refused("done-units-untouched", "rebrief", "--verdict", "confident", "--why", "x")

    def given_end_of_stack_stop_with_a_new_unit(self):
        self.given_implementing()
        self.given_unit_closed("U1")
        self.given_unit_closed("U2")
        self.must("begin-end-of-stack")
        self.given_stopped("one-way-door")
        self.given_rebrief_files("owner")
        self.given_hand_edit(lambda run: run["units"].append({"id": "U3", "status": "todo", "head": "", "gate_attempts": 0, "gate": {"review": ""}}))

    def test_rebrief__after_an_end_of_stack_stop_may_add_a_unit_and_return_to_implement(self):
        """An end-of-stack review that finds a hole needs a new unit; the stored-state check read end-of-stack and refused every rebrief that added one (oss-001, rebrief 2)."""
        self.given_end_of_stack_stop_with_a_new_unit()
        self.must("rebrief", "--verdict", "owner", "--why", "F1", "--phase", "implement")
        run = self.run_json()
        self.assertEqual((run["phase"], run["rotate"]["next_unit"], self.unit("U3")["status"]), ("implement", "U3", "todo"))
        self.assertEqual((self.state()["state"], self.state()["problems"]), ("awaiting-rotation", []))

    def test_rebrief__an_added_unit_is_still_refused_when_the_target_phase_is_end_of_stack(self):
        """--phase moves the check to the target phase, it does not skip it — an open unit in end-of-stack is illegal whichever way the phase arrives."""
        self.given_end_of_stack_stop_with_a_new_unit()
        self.assert_refused("stored-state-legal", "rebrief", "--verdict", "owner", "--why", "x")
        self.assert_refused("stored-state-legal", "rebrief", "--verdict", "owner", "--why", "x", "--phase", "end-of-stack")

    def test_resume__cannot_bring_in_a_unit_added_after_an_end_of_stack_stop(self):
        """Only a rebrief re-cuts units; a resume with --phase implement must not become a way to add one without a REBRIEF.md."""
        self.given_end_of_stack_stop_with_a_new_unit()
        self.assert_refused("stored-state-legal", "resume", "--by", "owner", "--decision", "go", "--phase", "implement")

    def test_resume__after_verification_failed_the_unit_gets_a_fresh_gate_budget(self):
        """Resuming a gate-cap stop resets the unit's attempts — every event but another stop would be refused forever."""
        self.given_implementing(max_gate_attempts=2)
        self.must("unit-start")
        for _ in range(2):
            self.given_gate_review("U1", "HOLD")
            self.must("gate-hold")
        self.given_stopped("verification-failed")
        self.must("resume", "--by", "lead", "--decision", "route B")
        self.assertEqual(self.unit("U1")["gate_attempts"], 0)
        self.given_gate_review("U1", "ADVANCE")
        self.must("gate-advance")

    def test_resume__any_other_stop_keeps_the_gate_count(self):
        """Only verification-failed buys a fresh budget — a budget or base-moved stop would become a way to reset the cap."""
        self.given_implementing()
        self.must("unit-start")
        self.given_gate_review("U1", "HOLD")
        self.must("gate-hold")
        self.given_stopped("base-moved")
        self.must("resume", "--by", "lead", "--decision", "rebased")
        self.assertEqual(self.unit("U1")["gate_attempts"], 1)

    # ------------------------------------------------------------ resume --wall-hours (028 D2)
    # Rows: 028 evidence/U2-behaviors.md. D2's guard name and refusal wording are the Session's (BRIEF doors), so a
    # wall-hours refusal is asserted as a logged resume refusal by a guard no resume could be refused by before D2.

    RESUME_REFUSALS_BEFORE_D2 = {"stored-state-legal", "log-intact", "from-state", "result-legal", "phase-before", "stop-file-absent", "decision", "by", "decider-allowed", "not-rebrief-due-for-lead"}

    def given_budget_stop(self, **fields):
        self.given_implementing(**fields)
        self.given_stopped("budget")

    def given_last_event_carries(self, **fields):
        rows = self.events()
        rows[-1].update(fields)
        (self.dir / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in rows))

    def given_extended_then_stopped_again(self, by, from_hours, to_hours, pct=25):
        """A budget stop resumed by `by` with its wall moved from `from_hours` to `to_hours`, recorded as D2 R2 records it, then a second budget stop."""
        self.given_budget_stop(max_wall_hours=from_hours, wall_hours_extension_pct=pct)
        self.must("resume", "--by", by, "--decision", "extend")
        self.given_hand_edit(lambda run: run.update(max_wall_hours=to_hours))
        self.given_last_event_carries(wall_hours=[from_hours, to_hours])
        self.given_stopped("budget")

    def assert_wall_hours_refused(self, *args):
        before = (self.dir / "run.json").read_text()
        logged = len(self.events())
        code, _, err = self.tool("resume", *args)
        self.assertEqual(code, 2, err)
        self.assertEqual((self.dir / "run.json").read_text(), before)
        self.assertEqual([(e["event"], e.get("refused")) for e in self.events()[logged:]], [("resume", True)], err)
        self.assertNotIn(self.events()[-1]["guard"], self.RESUME_REFUSALS_BEFORE_D2, err)

    def test_resume__wall_hours_refused_after_a_verification_failed_stop(self):
        """A wall extension answers only a budget stop — any stop could buy hours it was not stopped for."""
        self.given_implementing(max_wall_hours=2, wall_hours_extension_pct=25)
        self.given_stopped("verification-failed")
        self.assert_wall_hours_refused("--by", "owner", "--decision", "extend", "--wall-hours", "4")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__wall_hours_refused_after_a_base_moved_stop(self):
        """Every non-budget code refuses --wall-hours, not only verification-failed — a check on one code would let the rest through."""
        self.given_implementing(max_wall_hours=2, wall_hours_extension_pct=25)
        self.given_stopped("base-moved")
        self.assert_wall_hours_refused("--by", "owner", "--decision", "extend", "--wall-hours", "4")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__lead_wall_hours_at_the_cap_moves_max_wall_hours_and_resumes(self):
        """A Lead extension to exactly from × 1.25 is written and the session resumes — the extension would be talk again, as 023's run.json still reading 2 shows."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "2.5")
        run = self.run_json()
        self.assertEqual((code, run["max_wall_hours"], run["phase"], run["stop_reason"]), (0, 2.5, "implement", None), err)

    def test_resume__lead_wall_hours_at_a_cap_binary_floats_cannot_hold_moves(self):
        """3 h at 20% caps at exactly 3.6, which binary floats compute as 3.5999… — the tool would refuse the cap it names in its own refusal."""
        self.given_budget_stop(max_wall_hours=3, wall_hours_extension_pct=20)
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "3.6")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 3.6), err)

    def test_resume__wall_hours_event_records_from_and_to(self):
        """The resume record carries wall_hours [from, to] under the deciding actor — the one-extension rule would have nothing to read."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "2.5")
        record = self.events()[-1]
        self.assertEqual((record["event"], record["actor"], record.get("refused"), record.get("wall_hours")), ("resume", "lead", None, [2, 2.5]))

    def test_resume__lead_wall_hours_above_the_cap_refused(self):
        """A Lead extension past from × (1 + pct/100) is refused — the Lead would grant wall hours past the Owner's allowance."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "2.6")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__lead_cap_follows_the_sessions_own_percentage_at_the_cap(self):
        """At 50% a Lead may take 4 h to 6 h — a cap fixed at 25% would refuse what this session's run.json allows."""
        self.given_budget_stop(max_wall_hours=4, wall_hours_extension_pct=50)
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "6")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 6), err)

    def test_resume__lead_cap_follows_the_sessions_own_percentage_above_the_cap(self):
        """At 10% a Lead may not take 4 h to 4.5 h — a cap fixed at 25% would grant more than this session's run.json allows."""
        self.given_budget_stop(max_wall_hours=4, wall_hours_extension_pct=10)
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "4.5")
        self.assertEqual(self.run_json()["max_wall_hours"], 4)

    def test_resume__lead_cap_after_an_owner_extension_is_computed_from_the_owners_number(self):
        """After the Owner moved the wall to 3 h, the Lead's cap is 3.75 h — an Owner extension would lift the Lead's cap with it."""
        self.given_extended_then_stopped_again("owner", 2, 3, pct=25)
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "3.8")
        self.assertEqual(self.run_json()["max_wall_hours"], 3)

    def test_resume__second_lead_extension_refused(self):
        """A Lead gets one wall extension per session — repeated in-cap extensions would compound past anything the Owner allowed."""
        self.given_extended_then_stopped_again("lead", 2, 2.5, pct=25)
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "3")
        self.assertEqual(self.run_json()["max_wall_hours"], 2.5)

    def test_resume__owner_extension_leaves_the_lead_its_one(self):
        """An Owner extension does not spend the Lead's one, and the Lead's cap then starts from the Owner's 3 h — the Lead would be locked out by the Owner's own decision."""
        self.given_extended_then_stopped_again("owner", 2, 3, pct=25)
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "3.5")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 3.5), err)

    def test_resume__refused_lead_attempt_does_not_use_up_the_leads_extension(self):
        """Only an applied Lead extension counts — one refused attempt would cost the Lead the extension it never got (assumed Q2)."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.assert_refused("decision", "resume", "--by", "lead", "--decision", "")
        self.given_last_event_carries(wall_hours=[2, 2.6])
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "2.5")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 2.5), err)

    def test_resume__missing_percentage_never_reads_as_unlimited(self):
        """With no wall_hours_extension_pct, a Lead extension past 25% is refused — an old run.json would give the Lead an unlimited wall."""
        self.given_budget_stop(max_wall_hours=2)
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "2.6")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__missing_percentage_refuses_a_lead_extension(self):
        """With no wall_hours_extension_pct, the Lead has no allowance and any Lead extension is refused — the Lead would grant hours the brief never allowed (assumed Q1)."""
        self.given_budget_stop(max_wall_hours=2)
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "2.5")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__missing_percentage_leaves_the_owner_free(self):
        """The Owner's extension does not read the percentage — an old run.json would lock the Owner out of their own wall."""
        self.given_budget_stop(max_wall_hours=2)
        code, _, err = self.tool("resume", "--by", "owner", "--decision", "extend", "--wall-hours", "4")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 4), err)

    def test_resume__owner_wall_hours_past_the_lead_cap_applied(self):
        """The Owner may extend 2 h to 4 h, past the Lead's 25% — the Owner would be held to the Lead's cap."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        code, _, err = self.tool("resume", "--by", "owner", "--decision", "extend", "--wall-hours", "4")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 4), err)

    def test_resume__owner_extends_after_the_lead_used_its_one(self):
        """The Lead's one-extension rule does not bind the Owner — the Owner could not extend a session the Lead already had."""
        self.given_extended_then_stopped_again("lead", 2, 2.5, pct=25)
        code, _, err = self.tool("resume", "--by", "owner", "--decision", "extend", "--wall-hours", "5")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 5), err)

    def test_resume__owner_wall_hours_nan_refused(self):
        """NaN is not above the current wall — every comparison against it is false, so a `<=` check would write NaN into run.json."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.assert_wall_hours_refused("--by", "owner", "--decision", "extend", "--wall-hours", "nan")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__owner_wall_hours_infinite_refused(self):
        """An infinite wall is refused — run.json would hold Infinity, which no JSON reader accepts (assumed Q4)."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.assert_wall_hours_refused("--by", "owner", "--decision", "extend", "--wall-hours", "inf")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__lead_wall_hours_equal_to_the_current_wall_refused(self):
        """--wall-hours 2 from 2 is refused — an extension that extends nothing would still spend the Lead's one."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "2")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__owner_wall_hours_equal_to_the_current_wall_refused(self):
        """The at-or-below refusal binds the Owner too — an Owner resume would record an extension of nothing."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.assert_wall_hours_refused("--by", "owner", "--decision", "extend", "--wall-hours", "2")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__owner_wall_hours_below_the_current_wall_refused(self):
        """--wall-hours 1.5 from 2 is refused — a budget resume would shrink the wall the session just ran out of."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.assert_wall_hours_refused("--by", "owner", "--decision", "extend", "--wall-hours", "1.5")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__without_wall_hours_leaves_max_wall_hours(self):
        """A budget resume without --wall-hours resumes and leaves the wall — every existing resume would start moving it."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "go")
        run = self.run_json()
        self.assertEqual((code, run["max_wall_hours"], run["phase"]), (0, 2, "implement"), err)

    def test_resume__without_wall_hours_writes_todays_event_record(self):
        """A resume without --wall-hours writes the same record keys as before D2 — a wall_hours key, even null, would read as an extension."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        self.must("resume", "--by", "lead", "--decision", "go")
        self.assertEqual(sorted(self.events()[-1]), ["actor", "at", "decision", "digest", "event", "from", "machine", "n", "session_from", "session_to", "to", "units"])

    def test_resume__without_wall_hours_is_not_limited_by_an_earlier_lead_extension(self):
        """The one-extension rule binds only a --wall-hours resume — after one extension the Lead could never resume a budget stop again."""
        self.given_extended_then_stopped_again("lead", 2, 2.5, pct=25)
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "go")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 2.5), err)

    def test_resume__wall_hours_refused_cleanly_with_no_event_log(self):
        """With no events.jsonl, --wall-hours is refused by log-intact as any event is — reading the missing log for an earlier extension would crash the tool."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        (self.dir / "events.jsonl").unlink()
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "2.5")
        self.assertEqual((code, [(e["event"], e.get("guard")) for e in self.events()], self.run_json()["max_wall_hours"]), (2, [("resume", "log-intact")], 2), err)

    def test_resume__wall_hours_refused_cleanly_with_an_empty_event_log(self):
        """With an empty events.jsonl, --wall-hours is refused by log-intact as any event is — reading the empty log for an earlier extension would crash the tool."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        (self.dir / "events.jsonl").write_text("")
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "2.5")
        self.assertEqual((code, [(e["event"], e.get("guard")) for e in self.events()], self.run_json()["max_wall_hours"]), (2, [("resume", "log-intact")], 2), err)

    def test_resume__wall_hours_refused_cleanly_after_a_half_written_last_line(self):
        """A half-written last line refuses --wall-hours by log-intact, as it refuses any event — the earlier-extension read would crash on it."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        log = self.dir / "events.jsonl"
        with open(log, "a") as fh:
            fh.write('{"n": 5, "event": "resume", "actor": "lead", "wall_hours": [2, 2.')
        lines_before = len(log.read_text().splitlines())
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "2.5")
        added = [json.loads(line) for line in log.read_text().splitlines()[lines_before:]]
        self.assertEqual((code, [(e["event"], e.get("guard")) for e in added], self.run_json()["max_wall_hours"]), (2, [("resume", "log-intact")], 2), err)

    def test_resume__half_written_line_mid_log_reads_as_no_earlier_extension(self):
        """A truncated Lead-extension line that is no longer last (as after adopt) is no earlier extension — one torn append would crash the tool or spend the Lead's one."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=25)
        log = self.dir / "events.jsonl"
        lines = log.read_text().splitlines()
        torn = '{"n": 3, "event": "resume", "actor": "lead", "wall_hours": [2, 2.'
        log.write_text("\n".join(lines[:1] + [torn] + lines[1:]) + "\n")
        code, _, err = self.tool("resume", "--by", "lead", "--decision", "extend", "--wall-hours", "2.5")
        self.assertEqual((code, self.run_json()["max_wall_hours"]), (0, 2.5), err)

    def test_resume__wall_hours_refused_without_a_stored_max_wall_hours(self):
        """With no max_wall_hours there is no `from` to extend, so --wall-hours is refused and the key stays absent — the tool would invent a wall the brief never set (assumed Q3)."""
        self.given_budget_stop(wall_hours_extension_pct=25)
        self.assert_wall_hours_refused("--by", "owner", "--decision", "extend", "--wall-hours", "4")
        self.assertNotIn("max_wall_hours", self.run_json())

    def test_resume__infinite_percentage_never_reads_as_unlimited(self):
        """A run.json holding Infinity for wall_hours_extension_pct refuses a Lead extension to 10 h — the cap would be infinite and the Lead's wall unlimited."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=float("inf"))
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "10")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__nan_percentage_never_reads_as_unlimited(self):
        """A run.json holding NaN for wall_hours_extension_pct refuses a Lead extension to 10 h — `hours > NaN` is false, so no cap would ever refuse."""
        self.given_budget_stop(max_wall_hours=2, wall_hours_extension_pct=float("nan"))
        self.assert_wall_hours_refused("--by", "lead", "--decision", "extend", "--wall-hours", "10")
        self.assertEqual(self.run_json()["max_wall_hours"], 2)

    def test_resume__wall_hours_refused_from_a_nan_max_wall_hours(self):
        """A NaN max_wall_hours is no `from` to extend, as a missing one is not — `hours <= NaN` is false and the record would carry NaN (assumed, end-of-stack F2)."""
        self.given_budget_stop(max_wall_hours=float("nan"), wall_hours_extension_pct=25)
        self.assert_wall_hours_refused("--by", "owner", "--decision", "extend", "--wall-hours", "4")

    def test_rebrief__refused_when_the_last_event_recorded_no_unit_rows(self):
        """Without recorded unit rows the done units cannot be vouched for — the event says adopt first rather than guessing."""
        self.given_implementing()
        self.given_stopped()
        self.given_rebrief_files()
        stripped = [{k: v for k, v in e.items() if k != "units"} for e in self.events()]
        (self.dir / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in stripped))
        self.assert_refused("done-units-untouched", "rebrief", "--verdict", "confident", "--why", "x")

    def test_rebrief__refused_when_the_file_says_a_different_verdict(self):
        """The event's verdict must be REBRIEF.md's — a Planner could write owner and launch as confident."""
        self.given_implementing()
        self.given_stopped()
        (self.dir / "REBRIEF.md").write_text("Verdict: owner\n")
        (self.dir / "BRIEF.r1.md").write_text("old\n")
        self.assert_refused("rebrief-file-has-verdict", "rebrief", "--verdict", "confident", "--why", "x")

    def test_rebrief__refused_unless_the_old_brief_was_kept(self):
        """BRIEF.r<n>.md must exist — the brief that failed three times would be lost."""
        self.given_implementing()
        self.given_stopped()
        (self.dir / "REBRIEF.md").write_text("Verdict: confident\n")
        self.assert_refused("superseded-brief-kept", "rebrief", "--verdict", "confident", "--why", "x")

    # ------------------------------------------------------------ check

    def test_check__flags_each_core_field_edited_by_hand(self):
        """A hand edit to phase, stop_reason, rotate or rebriefs fails check — the single-writer rule would be a convention again."""
        edits = {
            "phase": lambda run: run.update(phase="intake"),
            "stop_reason": lambda run: run.update(stop_reason={"code": "budget"}),
            "rotate": lambda run: run.update(rotate={"requested_at": "t", "resumed_at": "t"}),
            "rebriefs": lambda run: run.update(rebriefs=[{"n": 1}]),
        }
        for field, edit in edits.items():
            with self.subTest(field):
                self.given_implementing()
                self.given_hand_edit(edit)
                code, out, _ = self.tool("check")
                self.assertEqual(code, 1)
                self.assertIn("edited-outside-tool: phase", out)

    def test_check__flags_each_unit_field_edited_by_hand(self):
        """A hand edit to a unit's id, status, gate_attempts or head fails check — the gate guard could be walked around with an Edit."""
        edits = {"id": "U7", "status": "done", "gate_attempts": 2, "head": SHA}
        for field, value in edits.items():
            with self.subTest(field):
                self.given_implementing()
                self.given_hand_edit(lambda run: run["units"][0].update({field: value}))
                code, out, _ = self.tool("check")
                self.assertEqual(code, 1)
                self.assertIn("edited-outside-tool: a unit", out)

    def test_event__refused_after_a_hand_edit_until_adopted(self):
        """No event applies over a hand edit — the next legal event would re-baseline the digest and launder it (a reset gate count, a closed unit)."""
        self.given_implementing(max_gate_attempts=1)
        self.must("unit-start")
        self.given_gate_review("U1", "HOLD")
        self.must("gate-hold")
        self.given_hand_edit(lambda run: run["units"][0].update(gate_attempts=0))
        self.given_gate_review("U1", "ADVANCE")
        self.assert_refused("log-intact", "gate-advance")
        self.must("adopt", "--by", "owner", "--reason", "owner reset the budget")
        self.must("gate-advance")

    def test_check__a_half_written_log_line_is_a_problem_not_a_crash(self):
        """A corrupt events.jsonl line is reported and adopt clears it — one truncated append would take down the tool, the launcher and the whole roster."""
        self.given_implementing()
        with open(self.dir / "events.jsonl", "a") as log:
            log.write('{"n": 3, "event": "unit-st')
        info = self.state()
        self.assertEqual([p.split(":")[0] for p in info["problems"]], ["corrupt-event-log"])
        self.must("adopt", "--by", "owner", "--reason", "truncated append")
        self.assertEqual(self.tool("check")[0], 0)

    def test_adopt__refused_on_an_illegal_state(self):
        """adopt baselines only a legal state — it would otherwise be the way to launder an illegal one."""
        self.given_session(phase="stopped")
        code, _, err = self.tool("adopt", "--by", "owner", "--reason", "x")
        self.assertEqual((code, self.events()), (2, []))
        self.assertIn("stored-state-legal", err)

    def test_check__lets_intake_populate_units(self):
        """Units edited during intake pass check — Phase 1 writes them directly, by design."""
        self.given_session()
        self.must("preflight-pass")
        self.given_hand_edit(lambda run: run["units"].append({"id": "U3", "status": "todo"}))
        self.assertEqual(self.tool("check")[0], 0)

    def test_check__a_session_past_briefed_with_no_log_needs_adopting(self):
        """No events.jsonl past briefed fails check until adopted — a session written around the tool would read as legal."""
        self.given_session(phase="implement")
        self.assertEqual(self.tool("check")[0], 1)
        self.must("adopt", "--by", "owner", "--reason", "predates the tool")
        self.assertEqual(self.tool("check")[0], 0)

    def test_check__names_each_illegal_stored_state(self):
        """Each illegal combination is named — the roster would print a plausible verdict for a state that cannot exist."""
        done, todo, building = ({"id": i, "status": s} for i, s in (("A", "done"), ("B", "todo"), ("C", "building")))
        cases = {
            "unknown-phase": {"phase": "paused"},
            "stopped-without-code": {"phase": "stopped"},
            "unknown-stop-code": {"phase": "stopped", "stop_reason": {"code": "tired", "phase_before": "implement"}},
            "done-and-stopped": {"phase": "done", "stop_reason": {"code": "budget"}, "units": [done]},
            "done-and-rotating": {"phase": "done", "rotate": {"requested_at": "t"}, "units": [done]},
            "stopped-and-rotating": {"phase": "stopped", "stop_reason": {"code": "budget", "phase_before": "implement"}, "rotate": {"requested_at": "t"}},
            "unknown-unit-status": {"phase": "implement", "units": [{"id": "A", "status": "wip"}]},
            "duplicate-unit-id": {"phase": "implement", "units": [todo, todo]},
            "two-units-in-flight": {"phase": "implement", "units": [building, {"id": "D", "status": "held"}]},
            "unit-out-of-order": {"phase": "implement", "units": [todo, done]},
            "gate-attempts-over-cap": {"phase": "implement", "units": [{"id": "A", "status": "held", "gate_attempts": 4}]},
            "bad-gate-attempts": {"phase": "implement", "units": [{"id": "A", "status": "held", "gate_attempts": "2"}]},
            "units-started-before-implement": {"phase": "intake", "units": [building]},
            "units-open-after-implement": {"phase": "end-of-stack", "units": [done, todo]},
            "implementing-without-units": {"phase": "implement", "units": []},
            "rotating-mid-unit": {"phase": "implement", "rotate": {"requested_at": "t"}, "units": [building]},
        }
        for name, fields in cases.items():
            with self.subTest(name):
                self.given_session(**fields)
                named = [p.split(":")[0] for p in self.state()["problems"]]
                self.assertIn(name, named)

    def test_event__refused_on_an_illegal_stored_state(self):
        """No event applies to an illegal state — the tool would launder it into a legal-looking one."""
        self.given_session(phase="stopped")
        self.assert_refused("stored-state-legal", "resume", "--by", "owner", "--decision", "go")

    # ------------------------------------------------------------ queries

    def test_status__lists_only_the_events_legal_now(self):
        """legal_events follows the table — an agent told it may finish from implementing will try."""
        self.given_implementing()
        self.assertEqual(sorted(self.state()["legal_events"]), ["begin-end-of-stack", "plan-review", "rebase", "request-rotate", "stop", "unit-start"])

    def test_check_op__follows_the_operations_table(self):
        """launch, rotate and resume are answered from stored state — the launcher would restart work in progress."""
        self.given_session()
        self.assertEqual([self.tool("check-op", op)[0] for op in ("launch", "rotate", "resume")], [0, 2, 0])
        self.must("preflight-pass")
        self.must("intake-complete")
        self.assertEqual([self.tool("check-op", op)[0] for op in ("launch", "rotate", "resume")], [2, 2, 0])
        self.given_unit_closed("U1")
        self.must("request-rotate")
        self.assertEqual([self.tool("check-op", op)[0] for op in ("launch", "rotate", "resume")], [2, 0, 2])

    def test_check_op__a_stopped_session_is_resumable_only_after_the_resume_event(self):
        """resume is refused while stopped — a session would be woken with its stop unanswered."""
        self.given_implementing()
        self.given_stopped()
        self.assertEqual(self.tool("check-op", "resume")[0], 2)
        self.must("resume", "--by", "lead", "--decision", "go")
        self.assertEqual(self.tool("check-op", "resume")[0], 0)

    def test_check_op__refused_on_a_hand_edited_session(self):
        """The launcher will not start a session whose state was edited around the tool."""
        self.given_implementing()
        self.given_hand_edit(lambda run: run["units"][0].update(status="done"))
        self.assertEqual(self.tool("check-op", "resume")[0], 2)

    def test_doc__prose_is_sentence_case_and_an_identifier_keeps_its_case(self):
        """A label that opens with an event, operation or field name stays as written — a capitalised event is one the tool refuses."""
        spec = importlib.util.spec_from_file_location("session_state_tool", TOOL)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        ids = tool.doc_ids(tool.load_table())
        labels = ["third stop", "request-rotate", "launch, then preflight-pass", "rotate_sessions is false"]
        self.assertEqual([tool._sentence(label, ids) for label in labels], ["Third stop", "request-rotate", "launch, then preflight-pass", "rotate_sessions is false"])

    def test_doc__the_session_machine_draws_which_states_release_the_stop_gate(self):
        """stop-gate.sh sends its reader to this column — without it the hook's release rule is drawn nowhere."""
        done = subprocess.run([sys.executable, str(TOOL), "doc"], capture_output=True, text=True)
        stored = [line for line in done.stdout.splitlines() if " | `phase = " in line or " | `rotate.requested_at set" in line]
        rows = {line.split("|")[1].strip(): line for line in stored}
        self.assertIn("| release |", rows["`awaiting-rotation`"])
        self.assertIn("| block |", rows["`implementing`"])

    def test_doc__states_md_matches_the_table(self):
        """Declared guard: STATES.md is generated; this fails when the table changed and the doc was not regenerated."""
        done = subprocess.run([sys.executable, str(TOOL), "doc", "--check"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


class IntegrationTests(SessionCase):
    """The three readers of the table: the roster, the launcher, the Worker's write hook."""

    def roster(self, *args, live_cwd=None):
        """Run the roster against a scratch HOME, so the verdicts never depend on which Claude sessions are live on this Mac."""
        home = Path(self.tmp.name) / "roster-home"
        sessions = home / ".claude/sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        if live_cwd is not None:
            (sessions / "live.json").write_text(json.dumps({"pid": os.getpid(), "cwd": str(live_cwd), "status": "busy", "sessionId": "live", "name": "someone-else"}))
        done = subprocess.run([sys.executable, str(ROSTER), *args, "--all", "--json", "--no-lead"], capture_output=True, text=True, env=dict(os.environ, HOME=str(home)), cwd=str(live_cwd or home))
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = json.loads(done.stdout)
        return rows["runs"] if isinstance(rows, dict) else rows

    def roster_row(self):
        return self.roster("--runs-root", str(self.dir.parent), "--only", self.dir.name)[0]

    def test_roster__a_session_with_no_worktree_matches_no_live_session(self):
        """A run.json with no worktree matches no live session, so a brief nothing launched reads briefed, not running — realpath of an empty string is the roster's own cwd, so it adopted whatever Claude session was live there."""
        root = self.dir / "root"
        (root / "a").mkdir(parents=True)
        (root / "a" / "run.json").write_text(json.dumps({"phase": "preflight", "units": []}))
        rows = self.roster("--runs-root", str(root), live_cwd=root)
        self.assertEqual([(r["run"], r["verdict"], r["session_name"]) for r in rows], [("a", "briefed", None)])

    def test_roster__a_session_parked_from_briefed_reads_parked(self):
        """052a-R1: a brief the Owner parked before launch reads parked — the Lead would offer to launch a brief the Owner shelved."""
        self.given_session()
        self.tool("park", "--by", "owner", "--reason", "held until the release ships")
        self.assertEqual(self.roster_row()["verdict"], "parked")

    def test_roster__an_illegal_state_is_invalid_not_a_plausible_verdict(self):
        """phase stopped with no code prints invalid — the Lead would route a stop that has no reason."""
        self.given_session(phase="stopped")
        self.assertEqual(self.roster_row()["verdict"], "invalid:stopped-without-code")

    def test_roster__awaiting_rotation_is_rotating_and_a_hand_edit_is_flagged(self):
        """The roster's rotating verdict and edited-outside-tool flag come from the tool's state — the two would drift apart again."""
        self.given_implementing()
        self.given_unit_closed("U1")
        self.must("request-rotate")
        row = self.roster_row()
        self.assertEqual((row["verdict"], row["state"], row["flags"]), ("rotating", "awaiting-rotation", []))
        self.given_hand_edit(lambda run: run["units"][1].update(status="done"))
        self.assertIn("edited-outside-tool", self.roster_row()["flags"])

    def test_roster__one_undescribable_session_does_not_blind_the_rest(self):
        """A session the roster cannot describe becomes one invalid row — the Lead would otherwise lose every session to one bad file."""
        root = self.dir / "root"
        good, bad = root / "a-good", root / "b-bad"
        for session in (good, bad):
            session.mkdir(parents=True)
        (good / "run.json").write_text(json.dumps({"phase": "preflight", "units": []}))
        (bad / "run.json").write_text(json.dumps({"phase": "implement", "units": ["U1"]}))
        rows = self.roster("--runs-root", str(root))
        self.assertEqual({r["run"]: r["verdict"].split(":")[0] for r in rows}, {"a-good": "briefed", "b-bad": "invalid"})

    def stop_gate_blocks(self, background_tasks=()):
        worktree = self.dir / "wt"
        (worktree / ".claude").mkdir(parents=True, exist_ok=True)
        (worktree / ".claude" / "autonomous-run").write_text(str(self.dir) + "\n")
        stop_input = {"cwd": str(worktree), "background_tasks": list(background_tasks)}
        done = subprocess.run(["bash", str(STOP_GATE)], input=json.dumps(stop_input), capture_output=True, text=True, env=self.marker_env())
        if not done.stdout.strip():
            return False
        # Claude Code reads a Stop hook's decision and reason at the top level; nested under hookSpecificOutput they are ignored.
        out = json.loads(done.stdout)
        return out.get("decision") == "block" and bool(out.get("reason"))

    def test_stop_gate__releases_exactly_where_the_tool_says_the_session_is_not_working(self):
        """The Stop hook reads run.json itself; it must agree with the tool on working, stopped (both encodings), awaiting-rotation and parked — a disagreement strands a session or ends one early."""
        self.given_implementing()
        self.assertTrue(self.stop_gate_blocks())
        self.given_unit_closed("U1")
        self.must("request-rotate")
        self.assertFalse(self.stop_gate_blocks())
        self.must("rotation-resumed")
        self.assertTrue(self.stop_gate_blocks())
        self.given_stopped()
        self.assertFalse(self.stop_gate_blocks())
        self.given_session(phase="implement", stop_reason="budget")
        self.assertEqual(self.state()["state"], "stopped")
        self.assertFalse(self.stop_gate_blocks())
        self.given_implementing()
        self.given_stopped()
        self.must("park", "--by", "owner", "--reason", "left for a rebrief")
        self.assertEqual(self.state()["state"], "parked")
        self.assertFalse(self.stop_gate_blocks())

    def test_precompact__hands_the_summarizer_plain_text_carrying_first_action(self):
        """Claude Code appends a PreCompact hook's exit-0 stdout to the summary request as custom compact instructions, and parses output that opens with { as hook JSON instead — a JSON blob would reach the summarizer verbatim, or fail validation."""
        self.given_implementing()
        (self.dir / "HANDOFF.md").write_text("# Handoff\n\n## FIRST ACTION\n\nrun the U2 scoped suite\n\n## Open items\n\nnone\n")
        worktree = self.dir / "wt"
        (worktree / ".claude").mkdir(parents=True)
        (worktree / ".claude" / "autonomous-run").write_text(str(self.dir) + "\n")
        done = subprocess.run(["bash", str(PRECOMPACT)], input=json.dumps({"cwd": str(worktree), "trigger": "auto"}), capture_output=True, text=True, env=self.marker_env())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(done.stdout.lstrip().startswith("{"), done.stdout[:80])
        self.assertIn(str(self.dir), done.stdout)
        self.assertIn("run the U2 scoped suite", done.stdout)
        self.assertNotIn("Open items", done.stdout)
        self.assertIn("compaction (auto)", (self.dir / "LEDGER.md").read_text())

    def test_stop_gate__lets_a_turn_end_while_background_work_will_wake_the_session(self):
        """A Worker waiting on a background gate reviewer is paused, not done: Claude Code wakes it when the task ends, and blocking meanwhile only spins it until the stuck detector releases (first Robowright Session, 2026-09-20: 15 blocks in one wait)."""
        self.given_implementing()
        self.assertFalse(self.stop_gate_blocks([{"id": "a1", "type": "agent", "status": "running"}]))
        self.assertTrue(self.stop_gate_blocks([{"id": "a1", "type": "agent", "status": "completed"}]))
        self.assertTrue(self.stop_gate_blocks([]))

    def test_write_hook__flags_a_guarded_field_written_directly(self):
        """A direct run.json write that changed a guarded field feeds the rule back to the Worker; an unguarded one is silent."""
        self.given_implementing()
        worktree = self.dir / "wt"
        (worktree / ".claude").mkdir(parents=True)
        (worktree / ".claude" / "autonomous-run").write_text(str(self.dir) + "\n")
        payload = json.dumps({"tool_name": "Edit", "cwd": str(worktree), "tool_input": {"file_path": str(self.dir / "run.json"), "new_string": "x"}})
        home = self.dir / "home"
        tool_dir = home / ".claude/skills/robowright"
        tool_dir.mkdir(parents=True)
        (tool_dir / "scripts").symlink_to(HERE)
        (tool_dir / "state-machine.json").symlink_to(HERE.parent / "state-machine.json")

        def hook():
            done = subprocess.run(["bash", str(WRITE_HOOK)], input=payload, capture_output=True, text=True, env=self.marker_env(HOME=str(home)))
            return done.stdout

        self.given_hand_edit(lambda run: run.update(ticket="renamed"))
        self.assertEqual(hook(), "")
        self.given_hand_edit(lambda run: run["units"][0].update(status="done"))
        self.assertIn("edited-outside-tool", json.loads(hook())["hookSpecificOutput"]["additionalContext"])

    def test_launcher__asks_the_tool_before_launch_rotate_or_resume(self):
        """The launcher refuses what check-op refuses — a fresh launch over work in progress, or a resume of an unanswered stop."""
        root = self.dir / "fixture"
        repo = root / "repo"
        repo.mkdir(parents=True)
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True)
        worktree = root / "worktrees" / "wt"
        worktree.parent.mkdir()
        subprocess.run(git + ["worktree", "add", "-q", "-b", "robowright/test", str(worktree)], cwd=repo, check=True, capture_output=True)
        sessions = root / "sessions"
        session = sessions / "sample-001-x"
        session.mkdir(parents=True)
        self.dir = session
        _, env = self.given_home(root, sessions)

        def launch(*flags):
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--dry-run", *flags], env=env, capture_output=True, text=True)
            return done.returncode, done.stdout + done.stderr

        def given(**fields):
            run = dict(self.run_json(), worktree=str(worktree.resolve()), session_id="00000000-0000-0000-0000-000000000000", **fields)
            (session / "run.json").write_text(json.dumps(run))

        self.given_session()
        given()
        self.assertEqual(launch()[0], 0, launch()[1])
        self.must("preflight-pass")
        self.must("intake-complete")
        code, out = launch()
        self.assertEqual(code, 1)
        self.assertIn("check-op launch", out)
        self.assertEqual(launch("--resume")[0], 0, launch("--resume")[1])
        # A skill's hooks register when the skill is invoked and a resumed process starts with none: the resume prompt has to invoke it.
        self.assertRegex(launch("--resume")[1], r"--resume=\S+ /worker\\ " + re.escape(str(session.resolve())))
        project = root / "project"
        project.mkdir()
        (project / "PROJECT.md").write_text("# plan\n")
        rebrief = ("--planner", "rebrief", "--project", str(project))
        code, out = launch(*rebrief)
        self.assertEqual(code, 1)
        self.assertIn("a rebrief answers a stopped one", out)
        self.given_stopped()
        for flag in ("--resume", "--rotate"):
            code, out = launch(flag)
            self.assertEqual(code, 1)
            self.assertIn(f"check-op {flag[2:]}", out)
        (session / "STOP").write_text("")
        code, out = launch(*rebrief)
        self.assertEqual(code, 1)
        self.assertIn("STOP exists", out)
        (session / "STOP").unlink()
        self.assertEqual(launch(*rebrief)[0], 0, launch(*rebrief)[1])
        self.given_rebrief_files()
        self.must("rebrief", "--verdict", "confident", "--why", "x")
        self.assertIn("launch it with --rotate", launch(*rebrief)[1])
        self.assertEqual(launch("--rotate")[0], 0, launch("--rotate")[1])

    def test_launcher__the_resume_prompt_says_whether_a_decision_is_waiting(self):
        """A resume prompt written for an answered stop sends an orphan — process died, no stop, no decision — to a LEDGER.md entry nobody wrote (first Robowright Session, 2026-09-20)."""
        root = self.dir / "fixture"
        repo = root / "repo"
        repo.mkdir(parents=True)
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True)
        worktree = root / "worktrees" / "wt"
        worktree.parent.mkdir()
        subprocess.run(git + ["worktree", "add", "-q", "-b", "robowright/test", str(worktree)], cwd=repo, check=True, capture_output=True)
        session = root / "sessions" / "sample-001-x"
        session.mkdir(parents=True)
        self.dir = session
        _, env = self.given_home(root, session.parent)

        def plan(*flags):
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--dry-run", *flags], env=env, capture_output=True, text=True)
            # The plan prints the command shell-quoted; unescape it so the prompt reads as prose.
            return done.returncode, (done.stdout + done.stderr).replace("\\", "")

        self.given_implementing()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()), session_id="00000000-0000-0000-0000-000000000000")))
        code, out = plan("--resume")
        self.assertEqual(code, 0, out)
        self.assertIn("the process ended with no stop and no decision", out)
        self.assertNotIn("the decision that answered your stop", out)
        self.given_stopped()
        self.must("resume", "--by", "owner", "--decision", "take route B")
        code, out = plan("--resume")
        self.assertEqual(code, 0, out)
        self.assertIn("the decision that answered your stop is the newest entry in LEDGER.md", out)
        self.assertNotIn("no stop and no decision", out)

    def test_launcher__only_a_resume_may_start_on_a_dirty_worktree(self):
        """A crash mid-edit leaves the session's own uncommitted work, and refusing to resume over it stranded the Robowright Session; a fresh launch or rotate over it still has no owner for those changes (first Robowright Session, 2026-09-20)."""
        root = self.dir / "fixture"
        repo = root / "repo"
        repo.mkdir(parents=True)
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True)
        worktree = root / "worktrees" / "wt"
        worktree.parent.mkdir()
        subprocess.run(git + ["worktree", "add", "-q", "-b", "robowright/test", str(worktree)], cwd=repo, check=True, capture_output=True)
        session = root / "sessions" / "sample-001-x"
        session.mkdir(parents=True)
        self.dir = session
        _, env = self.given_home(root, session.parent)

        def plan(*flags):
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--dry-run", *flags], env=env, capture_output=True, text=True)
            return done.returncode, (done.stdout + done.stderr).replace("\\", "")

        self.given_session()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()), session_id="00000000-0000-0000-0000-000000000000")))
        self.assertEqual(plan()[0], 0, plan()[1])
        (worktree / "scratch.txt").write_text("half an edit\n")
        code, out = plan("--resume")
        self.assertEqual(code, 0, out)
        self.assertIn("dirty:", out)
        self.assertIn("?? scratch.txt", out)
        self.assertIn("uncommitted changes from before the process ended", out)
        for flag in ((), ("--rotate",)):
            code, out = plan(*flag)
            self.assertEqual(code, 1, out)
            self.assertIn("worktree is dirty", out)
            # The dirty gate, not the state gate: a briefed session is otherwise launchable.
            self.assertNotIn("check-op", out)

    def test_launcher__a_resume_records_the_new_background_id_and_session_id(self):
        """claude --bg --resume prints the resumed id before the new one, and the new session runs under a new id — the ledger's attach line and run.json.session_id would otherwise name a session that no longer exists, and an unpinned run.json.transcripts prices the session from every transcript the worktree ever saw (first Robowright Session, 2026-09-20)."""
        root = self.dir / "fixture"
        repo = root / "repo"
        repo.mkdir(parents=True)
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True)
        worktree = root / "worktrees" / "wt"
        worktree.parent.mkdir()
        subprocess.run(git + ["worktree", "add", "-q", "-b", "robowright/test", str(worktree)], cwd=repo, check=True, capture_output=True)
        (worktree / ".gitignore").write_text(".claude/\n")
        subprocess.run(git + ["add", "-A"], cwd=worktree, check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "-m", "ignore"], cwd=worktree, check=True, capture_output=True)
        session = root / "sessions" / "sample-001-x"
        session.mkdir(parents=True)
        self.dir = session
        self.given_implementing()
        run = dict(self.run_json(), worktree=str(worktree.resolve()))
        (session / "run.json").write_text(json.dumps(run))
        home = root / "home"
        (home / ".claude/sessions").mkdir(parents=True)
        (home / ".claude/sessions/new.json").write_text(json.dumps({"sessionId": "bbbb2222-0000-4000-8000-000000000000", "cwd": "/elsewhere", "pid": 1}))
        stub = root / "bin"
        stub.mkdir()
        (stub / "claude").write_text("#!/bin/bash\necho 'resuming aaaa1111-0000-4000-8000-000000000000'\necho 'backgrounded · bbbb2222 · worker'\n")
        (stub / "claude").chmod(0o755)
        _, env = self.given_home(root, session.parent)
        env = dict(env, PATH=f"{stub}:{os.environ['PATH']}")

        def resume():
            return subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--resume", "aaaa1111-0000-4000-8000-000000000000", "--yes"], env=env, capture_output=True, text=True)

        done = resume()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("background id: bbbb2222 ", (session / "LEDGER.md").read_text())
        self.assertEqual(self.run_json()["session_id"], "bbbb2222-0000-4000-8000-000000000000")
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(worktree.resolve()))
        pinned = f"~/.claude/projects/{slug}/bbbb2222-0000-4000-8000-000000000000.jsonl"
        self.assertEqual(self.run_json()["transcripts"], [pinned])
        # A second resume lands on the same transcript path; the pin is a set, not a tally.
        self.assertEqual(resume().returncode, 0)
        self.assertEqual(self.run_json()["transcripts"], [pinned])

    def test_launcher__a_relaunch_records_what_the_previous_session_cost(self):
        """`claude stop` runs no SessionEnd hook and a finished session is left idle, so run.json.cost stayed null and no cost line ever reached the ledger; the relaunch is the last moment anyone is looking (first Robowright Session, 2026-09-20)."""
        root = self.dir / "fixture"
        repo = root / "repo"
        repo.mkdir(parents=True)
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True, capture_output=True)
        worktree = root / "worktrees" / "wt"
        worktree.parent.mkdir()
        subprocess.run(git + ["worktree", "add", "-q", "-b", "robowright/test", str(worktree)], cwd=repo, check=True, capture_output=True)
        (worktree / ".gitignore").write_text(".claude/\n")
        subprocess.run(git + ["add", "-A"], cwd=worktree, check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "-m", "ignore"], cwd=worktree, check=True, capture_output=True)
        session = root / "sessions" / "sample-001-x"
        session.mkdir(parents=True)
        self.dir = session
        self.given_implementing()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()))))
        home = root / "home"
        (home / ".claude/sessions").mkdir(parents=True)
        project = home / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(worktree.resolve()))
        project.mkdir(parents=True)
        (project / "aaaa1111-0000-4000-8000-000000000000.jsonl").write_text(json.dumps(
            {"timestamp": "2026-09-20T10:00:00Z", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "output_tokens": 5}}}) + "\n")
        stub = root / "bin"
        stub.mkdir()
        (stub / "claude").write_text("#!/bin/bash\necho 'backgrounded · bbbb2222 · worker'\n")
        (stub / "claude").chmod(0o755)
        _, env = self.given_home(root, session.parent)
        env = dict(env, PATH=f"{stub}:{os.environ['PATH']}")

        def resume(*flags):
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--resume", "aaaa1111-0000-4000-8000-000000000000", *flags], env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

        resume("--dry-run")
        self.assertIsNone(self.run_json().get("cost"), "a plan that starts nothing wrote run.json.cost")
        resume("--yes")
        cost = self.run_json()["cost"]
        self.assertIsNotNone(cost, "run.json.cost is still null after the relaunch")
        self.assertEqual(cost["requests"], 1)

    def test_launcher__a_worker_gets_the_mcp_servers_its_brief_names_and_no_others(self):
        """A Worker that uses no MCP server still carries every configured server's roster and instructions; the brief's `mcp` picks decide which approved servers it gets, and an approved server the brief did not pick stays out."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO, MCP_WIDGET)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        _, env = self.given_server_binary(env, MCP_WIDGET, "1.4.2")

        def plan():
            done = subprocess.run(["bash", str(launcher), "--session-dir", str(session), "--dry-run"], env=env, capture_output=True, text=True)
            return done.returncode, (done.stdout + done.stderr).replace("\\", "")

        self.given_mcp_brief(worktree)
        code, out = plan()
        self.assertEqual(code, 0, out)
        self.assertIn('mcp:       --strict-mcp-config --mcp-config {"mcpServers":{}}', out)
        # Twice: the mcp: line the Lead reads, and the command the launch would run.
        self.assertEqual(out.count("--strict-mcp-config"), 2, out)
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])
        code, out = plan()
        self.assertEqual(code, 0, out)
        self.assertIn("gizmo", self.mcp_block(out))
        self.assertNotIn('{"mcpServers":{}}', out)
        self.assertNotIn("widget", out)

    def test_launcher__a_worker_starts_with_the_lean_tool_list_unless_its_brief_names_another(self):
        """Built-in tool definitions are a fixed cost of every request a Worker makes; the lean list is the tools a session has been seen to use, and a brief whose units need another names its own."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        # `default` restores every tool, so it is refused like an unknown name (tests/run-launch SI-10).
        for written, passed in ((None, LEAN_TOOLS), ("Bash,Read", "Bash,Read")):
            (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()), tools=written)))
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--dry-run"], env=env, capture_output=True, text=True)
            out = (done.stdout + done.stderr).replace("\\", "")
            self.assertEqual(done.returncode, 0, out)
            self.assertIn("tools:     %s\n" % passed, out)
            self.assertIn(" --tools %s " % passed, out)

    def test_launcher__the_approved_list_is_the_one_beside_the_launcher_wherever_it_is_run_from(self):
        """The Lead, a hook and the Owner run the launcher from different directories, and HOME holds the stow install's own list; the list that decides what a session may start must be the one beside the running launcher, never whatever the caller's directory or HOME makes of it."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        home = session.parent.parent / "home"
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        decoy = dict(MCP_GIZMO, command="decoy-server", allow=["mcp__gizmo__decoy"])
        for listing in (session / "mcp", home / "mcp", home / ".claude/skills/robowright/mcp"):
            listing.mkdir(parents=True)
            (listing / "gizmo.json").write_text(json.dumps(decoy))
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])
        for cwd in (worktree, session, home):
            with self.subTest(cwd=cwd.name):
                done = subprocess.run(["bash", str(launcher), "--session-dir", str(session), "--dry-run"], env=env, cwd=cwd, capture_output=True, text=True)
                out = (done.stdout + done.stderr).replace("\\", "")
                self.assertEqual(done.returncode, 0, out)
                self.assertIn("mcp__gizmo__*", self.mcp_block(out))
                self.assertNotIn("decoy", out)

    def test_launcher__the_started_session_gets_the_mcp_flags_on_every_command_it_builds(self):
        """The plan prints one command and the launch runs another: a launch and a resume are built separately, and flags on the plan alone would leave the real session with every MCP server in context."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)

        def start(*flags):
            record.write_text("")
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--yes", *flags], env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            argv = record.read_text().splitlines()
            self.assertIn("--strict-mcp-config", argv)
            self.assertEqual(argv[argv.index("--mcp-config") + 1], '{"mcpServers":{}}')
            self.assertIn("--tools", argv)
            self.assertEqual(argv[argv.index("--tools") + 1], LEAN_TOOLS)

        self.given_session()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()))))
        start()
        self.must("preflight-pass")
        self.must("intake-complete")
        start("--resume", "aaaa1111-0000-4000-8000-000000000000")
        self.given_unit_closed("U1")
        self.must("request-rotate")
        start("--rotate")

    # ------------------------------------------------------------ the brief's `mcp` picks (U2 of 029)
    # Every test below runs a copy of the launcher whose approved list is a scratch one
    # (given_approved_list), with fake server binaries on a scratch PATH (given_server_binary).

    def test_launcher__a_brief_with_no_mcp_picks_plans_exactly_today_s_empty_strict_config(self):
        """Every run.json written before `mcp` existed carries `mcp_config: null` and no `mcp`, and the template will carry `mcp: []`: each must plan the strict empty set it always did, with no allow rules, or every brief in flight changes under it."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        for fields in ({}, {"mcp_config": None}, {"mcp": None}, {"mcp": []}):
            with self.subTest(fields=json.dumps(fields)):
                self.given_mcp_brief(worktree, **fields)

                done = self.run_launcher(launcher, session, env, "--dry-run")

                out = (done.stdout + done.stderr).replace("\\", "")
                self.assertEqual(done.returncode, 0, out)
                self.assertIn('mcp:       --strict-mcp-config --mcp-config {"mcpServers":{}}\n', out)
                self.assertIn(' --strict-mcp-config --mcp-config {"mcpServers":{}} --tools ', out)
                self.assertNotIn("--allowedTools", out)
                self.assertNotIn("--allowed-tools", out)

    def test_launcher__a_brief_with_an_empty_mcp_list_starts_with_no_servers_and_no_allow_rules(self):
        """The plan and the started command are built apart, and an empty list is where an empty `--allowedTools ''` would slip in: a Worker with no picks must start exactly as it does today."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[])

        done = self.run_launcher(launcher, session, env, "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        argv = self.recorded_argv(record)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--mcp-config") + 1], '{"mcpServers":{}}')
        self.assertNotIn("--allowedTools", argv)
        self.assertNotIn("--allowed-tools", argv)

    def test_launcher__a_server_that_is_not_on_the_approved_list_is_refused_and_the_refusal_names_the_list(self):
        """Adding a server is the Owner's call: a brief that names an unlisted one must start nothing, and the refusal must say where the list is so the Owner knows where an entry would go."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "sprocket", "workflows": ["alpha"]}])

        done = self.run_launcher(launcher, session, env, "--yes")

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(str((launcher.parent.parent / "mcp").resolve()), done.stderr)
        self.assertIn("sprocket", done.stderr)
        self.assertEqual(self.recorded_argv(record), [], "claude ran for an unlisted server")

    def test_launcher__a_server_name_outside_lower_case_letters_digits_and_hyphens_is_refused_before_it_is_looked_up(self):
        """The list is read through a case-insensitive file system, so `Gizmo` would open gizmo.json and start the same server under a second key; a name refused by its shape never reaches the lookup (the rule robowright-resolve.py:50 applies to repo names)."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO, dict(MCP_GIZMO, server="-gizmo", allow=["mcp__-gizmo__*"]))
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        for name in ("Gizmo", "-gizmo"):
            with self.subTest(server=name):
                self.given_mcp_brief(worktree, mcp=[{"server": name, "workflows": ["alpha"]}])

                done = self.run_launcher(launcher, session, env, "--yes")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn(f"'{name}', which is not a name the approved list", done.stderr)
                self.assertIn(str((launcher.parent.parent / "mcp").resolve()), done.stderr)
                self.assertEqual(self.recorded_argv(record), [], "claude ran for a name the list cannot hold")

    def test_launcher__a_server_name_that_climbs_out_of_the_approved_list_is_refused(self):
        """A server name is a file name inside the list: `../outside` must not reach an entry file that sits beside the list, or any JSON on disk becomes a server a brief can start."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        (launcher.parent.parent / "outside.json").write_text(json.dumps(dict(MCP_GIZMO, server="outside")))
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_mcp_brief(worktree, mcp=[{"server": "../outside", "workflows": ["alpha"]}])

        done = self.run_launcher(launcher, session, env, "--dry-run")

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(str((launcher.parent.parent / "mcp").resolve()), done.stderr)

    def test_launcher__a_workflow_the_entry_does_not_offer_is_refused(self):
        """The entry's workflows are the tool groups the Owner approved; a name that only resembles one, or two smuggled into the comma-joined variable as one, must not load anything."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        # A newline splits into two approved lines under a line-by-line check.
        for workflow in ("delta", "alp", "alpha,beta", "alpha\nbeta"):
            with self.subTest(workflow=workflow):
                self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": [workflow]}])

                done = self.run_launcher(launcher, session, env, "--dry-run")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn(workflow, done.stderr)

    def test_launcher__a_pick_that_names_no_workflows_is_refused(self):
        """A pick is `{server, workflows, allow}` with only `allow` optional; a pick with no workflows, or an empty list the server reads as none, would start the server with whatever it loads by default, which nobody chose."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        for pick in ({"server": "gizmo"}, {"server": "gizmo", "workflows": []}):
            with self.subTest(pick=json.dumps(pick)):
                self.given_mcp_brief(worktree, mcp=[pick])

                done = self.run_launcher(launcher, session, env, "--dry-run")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("workflows", done.stderr)

    def test_launcher__an_allow_rule_that_reaches_past_its_own_server_is_refused(self):
        """An allow rule runs every matching call unprompted: one that reaches all servers, another server, or a built-in tool would pass calls the brief never chose."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO, MCP_WIDGET)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        _, env = self.given_server_binary(env, MCP_WIDGET, "1.4.2")
        cases = (
            ([{"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__*"]}], "mcp__*"),
            ([{"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__widget__*"]}], "mcp__widget__*"),
            ([{"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__gizmox__*"]}], "mcp__gizmox__*"),
            ([{"server": "gizmo", "workflows": ["alpha"], "allow": ["Bash(*)"]}], "Bash(*)"),
            # widget is picked too, but the rule is listed under gizmo.
            ([{"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__widget__*"]}, {"server": "widget", "workflows": ["reads"]}], "mcp__widget__*"),
            # --allowedTools splits its value on commas and spaces, so one rule can smuggle in several.
            ([{"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__gizmo__x,Bash(*)"]}], "Bash(*)"),
            ([{"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__gizmo__y mcp__widget__*"]}], "mcp__widget__*"),
            # bash's [A-Za-z] follows the locale's collation, which admits é under en_US.UTF-8.
            ([{"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__gizmo__é"]}], "mcp__gizmo__é"),
        )
        for picks, rule in cases:
            with self.subTest(picks=json.dumps(picks)):
                self.given_mcp_brief(worktree, mcp=picks)

                done = self.run_launcher(launcher, session, env, "--dry-run")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn(rule, done.stderr)

    def test_launcher__a_server_whose_binary_is_not_on_path_is_refused(self):
        """A session whose server cannot start runs without the tools its brief planned around, and says so only mid-task; the launch is the moment to refuse."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])

        done = self.run_launcher(launcher, session, env, "--dry-run")

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("gizmo-server", done.stderr)

    def test_launcher__a_server_version_outside_the_pin_is_refused_and_both_versions_are_named(self):
        """The pin is the version the Owner approved; `2.70.0` is not `2.7.x`, and a refusal that names only one version leaves the Owner guessing whether to upgrade the binary or the pin."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])
        for printed in ("2.8.0", "2.70.0"):
            with self.subTest(printed=printed):
                _, run_env = self.given_server_binary(env, MCP_GIZMO, printed)

                done = self.run_launcher(launcher, session, run_env, "--dry-run")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn(printed, done.stderr)
                self.assertIn("2.7", done.stderr)

    def test_launcher__a_server_version_inside_the_pin_is_accepted(self):
        """A pin of `2.7` means the 2.7 line: a patch release the Owner's brew upgrade brings in must not stop every session that names the server."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])
        for printed in ("2.7", "2.7.0", "2.7.12"):
            with self.subTest(printed=printed):
                _, run_env = self.given_server_binary(env, MCP_GIZMO, printed)

                done = self.run_launcher(launcher, session, run_env, "--dry-run")

                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn("gizmo", self.mcp_block(done.stdout))

    def test_launcher__a_server_found_through_a_relative_path_entry_is_still_named_by_absolute_path(self):
        """The session starts inside the worktree, not where the launcher ran, so a binary found through a relative PATH entry must reach the config as the absolute path the launcher checked."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        gizmo, _ = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        env = dict(env, PATH=f"{gizmo.parent.name}:{env['PATH']}")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])

        done = self.run_launcher(launcher, session, env, "--yes", cwd=gizmo.parent.parent)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.built_config(self.recorded_argv(record))["mcpServers"]["gizmo"]["command"], str(gizmo))

    def test_launcher__an_entry_whose_server_is_not_its_file_name_is_refused_as_malformed(self):
        """The README's "server, equal to the file name" is the entry naming itself; one that names another server could land on that server's key and drop it."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        (launcher.parent.parent / "mcp/widget.json").write_text(json.dumps(dict(MCP_WIDGET, server="gizmo")))
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        _, env = self.given_server_binary(env, MCP_WIDGET, "1.4.2")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}, {"server": "widget", "workflows": ["reads"]}])

        done = self.run_launcher(launcher, session, env, "--yes")

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("widget.json is malformed", done.stderr)
        self.assertEqual(self.recorded_argv(record), [], "claude ran with an entry that names another server")

    def test_launcher__the_built_config_runs_the_picked_server_by_absolute_path_with_the_entry_s_args_env_and_workflows(self):
        """A daemon-started session's PATH is not the launcher's, so the config must carry the binary the launcher checked, by absolute path, with the entry's args and env intact (a space included) and the brief's workflows in the entry's variable, and no approved server the brief did not pick."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO, MCP_WIDGET)
        gizmo, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        _, env = self.given_server_binary(env, MCP_WIDGET, "1.4.2")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["gamma", "alpha"]}])

        done = self.run_launcher(launcher, session, env, "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        argv = self.recorded_argv(record)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv.count("--mcp-config"), 1, argv)
        servers = self.built_config(argv)["mcpServers"]
        self.assertEqual(set(servers), {"gizmo"})
        self.assertEqual(servers["gizmo"]["command"], str(gizmo))
        self.assertEqual(servers["gizmo"]["args"], ["serve", "--stdio"])
        self.assertEqual(servers["gizmo"]["env"]["GIZMO_TELEMETRY"], "off")
        self.assertEqual(servers["gizmo"]["env"]["GIZMO_GREETING"], "hello world")
        self.assertEqual(sorted(servers["gizmo"]["env"]["GIZMO_WORKFLOWS"].split(",")), ["alpha", "gamma"])

    def test_launcher__two_picks_start_both_servers_with_both_servers_allow_rules(self):
        """`mcp` is a list: a brief that needs two servers must get both, each with its own binary, variable and default rule, not only the first pick."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO, MCP_WIDGET)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        widget, env = self.given_server_binary(env, MCP_WIDGET, "1.4.2")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}, {"server": "widget", "workflows": ["reads"]}])

        done = self.run_launcher(launcher, session, env, "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        argv = self.recorded_argv(record)
        servers = self.built_config(argv)["mcpServers"]
        self.assertEqual(set(servers), {"gizmo", "widget"})
        self.assertEqual(servers["widget"]["command"], str(widget))
        self.assertEqual(servers["widget"]["env"]["WIDGET_GROUPS"], "reads")
        self.assertEqual(sorted(self.allow_rules(argv)), ["mcp__gizmo__*", "mcp__widget__*"])

    def test_launcher__the_allow_rules_reach_the_started_session_on_launch_resume_and_rotate(self):
        """Workers run in auto mode, and an MCP call with no allow rule leaves a `--bg` session waiting on a dialog nobody answers; launch, resume and rotate are built apart, so each must carry the rules, literally, never glob-expanded against the worktree."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO, MCP_WIDGET)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        _, env = self.given_server_binary(env, MCP_WIDGET, "1.4.2")
        # A file the glob mcp__gizmo__* would match, in the directory the launcher runs from.
        self.given_committed_file(worktree, "mcp__gizmo__decoy")

        def start(*flags):
            record.write_text("")
            done = self.run_launcher(launcher, session, env, "--yes", *flags, cwd=worktree)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            argv = self.recorded_argv(record)
            self.assertEqual(self.allow_rules(argv), ["mcp__gizmo__*"], argv)
            # --allowedTools takes <tools...>: the value must be closed by another option, never by the prompt.
            flag = next(at for at, arg in enumerate(argv) if arg in ("--allowedTools", "--allowed-tools"))
            self.assertTrue(argv[flag + 2].startswith("--"), argv)

        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])
        start()
        self.must("preflight-pass")
        self.must("intake-complete")
        start("--resume", "aaaa1111-0000-4000-8000-000000000000")
        self.given_unit_closed("U1")
        self.must("request-rotate")
        start("--rotate")

    def test_launcher__a_brief_s_allow_rules_replace_the_entry_s_defaults(self):
        """A brief that allows only the calls its task needs must not also inherit the entry's catch-all: a merged list would pass every tool the brief meant to keep behind the classifier."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__gizmo__list_things", "mcp__gizmo__get_thing"]}])

        done = self.run_launcher(launcher, session, env, "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(sorted(self.allow_rules(self.recorded_argv(record))), ["mcp__gizmo__get_thing", "mcp__gizmo__list_things"])

    def test_launcher__the_same_server_picked_twice_is_refused(self):
        """Two picks of one server can only collide: one `mcpServers` key, one workflow variable, two sets of rules; which one wins would be the launcher's accident, not the brief's choice."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        # GIZMO opens gizmo.json on a case-insensitive file system, and its own allow rule passes the
        # prefix check.
        for second in ({"server": "gizmo", "workflows": ["beta"]}, {"server": "GIZMO", "workflows": ["beta"], "allow": ["mcp__GIZMO__*"]}):
            with self.subTest(second=second["server"]):
                self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}, second])

                done = self.run_launcher(launcher, session, env, "--dry-run")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn(f"'{second['server']}'", done.stderr)

    def test_launcher__a_brief_that_still_names_an_mcp_config_is_refused_and_pointed_at_mcp(self):
        """A non-null `mcp_config` could name any config file and start an unlisted server beside the picks; the refusal must name `mcp` and the list."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        old = session / "old-servers.json"
        old.write_text(json.dumps({"mcpServers": {"ios": {"command": "true"}}}))
        # Any non-null value is refused, the empty string and false included.
        cases = ({"mcp_config": str(old)}, {"mcp_config": str(old), "mcp": [{"server": "gizmo", "workflows": ["alpha"]}]}, {"mcp_config": ""}, {"mcp_config": False})
        for fields in cases:
            with self.subTest(fields=json.dumps(fields)):
                self.given_mcp_brief(worktree, **fields)

                done = self.run_launcher(launcher, session, env, "--dry-run")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                # `mcp` as a word of its own: not the prefix of mcp_config, not the list's directory name.
                self.assertRegex(done.stderr, r"(?<![\w/-])mcp(?![\w/-])")
                self.assertIn(str((launcher.parent.parent / "mcp").resolve()), done.stderr)

    def test_launcher__a_null_mcp_config_beside_mcp_picks_is_accepted(self):
        """Every existing run.json carries `mcp_config: null`; a brief that adds `mcp` without deleting it must launch with its picks, not be refused over a field that says nothing."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_mcp_brief(worktree, mcp_config=None, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])

        done = self.run_launcher(launcher, session, env, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("gizmo", self.mcp_block(done.stdout))

    def test_launcher__the_plan_s_mcp_line_shows_the_servers_and_their_allow_rules(self):
        """The Owner and the Lead read the plan's `mcp:` line before `--yes`; it must show which servers start and which calls run unprompted, as written, not glob-expanded against the worktree."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        # A file the glob mcp__gizmo__* would match, in the directory the launcher runs from.
        self.given_committed_file(worktree, "mcp__gizmo__decoy")
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])

        done = self.run_launcher(launcher, session, env, "--dry-run", cwd=worktree)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        block = self.mcp_block(done.stdout)
        self.assertIn("gizmo", block)
        self.assertIn("mcp__gizmo__*", block)
        self.assertNotIn("decoy", done.stdout)

    def test_launcher__a_malformed_mcp_value_is_refused_cleanly(self):
        """A hand-edited brief is where a string or an object lands in place of a list; jq over it must end in a refusal the Owner can act on, never a jq error with the launch half done."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        cases = (
            "gizmo",
            {"server": "gizmo", "workflows": ["alpha"]},
            ["gizmo"],
            [{"workflows": ["alpha"]}],
            [{"server": "gizmo", "workflows": "alpha"}],
            [{"server": "gizmo", "workflows": ["alpha"], "allow": "mcp__gizmo__*"}],
            # jq's `//` reads false as absent.
            [{"server": "gizmo", "workflows": ["alpha"], "allow": False}],
            # A misspelled `allow` reads as absent and would launch with the entry's widest default.
            [{"server": "gizmo", "workflows": ["alpha"], "allowedTools": ["mcp__gizmo__*"]}],
            [{"server": "gizmo", "workflows": ["alpha"], "Allow": ["mcp__gizmo__*"]}],
        )
        for picks in cases:
            with self.subTest(mcp=json.dumps(picks)):
                self.given_mcp_brief(worktree, mcp=picks)

                done = self.run_launcher(launcher, session, env, "--dry-run")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("refusing: ", done.stderr)
                self.assertNotIn("jq: error", done.stderr)
                self.assertNotIn("dry run — nothing started", done.stdout)

    def test_launcher__a_hostile_value_in_any_string_slot_of_a_pick_is_refused_by_the_launcher(self):
        """Every string slot a pick has, fed each hostile variant of a valid value, must end in the launcher's own refusal: never a jq error, never a launch, never a half-built --mcp-config in the plan. A value checked in one reading and used in another is the bug class."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        pick = {"server": "gizmo", "workflows": ["alpha"], "allow": ["mcp__gizmo__*"]}
        slots = (
            ("server", "gizmo", lambda value: dict(pick, server=value)),
            ("workflows[]", "alpha", lambda value: dict(pick, workflows=[value])),
            ("allow[]", "mcp__gizmo__*", lambda value: dict(pick, allow=[value])),
        )
        for slot, good, place in slots:
            # Values may be added to this corpus; every one must stay refused.
            corpus = (good + "\n", "\n" + good, good[:2] + "\n" + good[2:], good + "\t", good + " ", good + ",", good + "\u0000",
                      good.upper(), good[:-1] + "é", "-" + good, "", False, 1, {}, [])
            for value in corpus:
                with self.subTest(slot=slot, value=repr(value)):
                    self.given_mcp_brief(worktree, mcp=[place(value)])
                    record.unlink(missing_ok=True)

                    done = self.run_launcher(launcher, session, env, "--yes")

                    self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                    self.assertIn("refusing: ", done.stderr)
                    self.assertNotIn("jq: error", done.stderr)
                    self.assertNotIn("--mcp-config", done.stdout)
                    self.assertEqual(self.recorded_argv(record), [], "claude ran for a hostile pick")

    def test_launcher__an_mcp_value_that_is_neither_a_list_nor_null_is_refused(self):
        """Only an absent `mcp`, null or a list says which servers to start; jq's `//` reads false as absent, so a `false` would launch with no servers when the brief plainly meant something else."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        for value in (False, True, "", 0, 1, {}):
            with self.subTest(mcp=json.dumps(value)):
                self.given_mcp_brief(worktree, mcp=value)
                record.unlink(missing_ok=True)

                done = self.run_launcher(launcher, session, env, "--yes")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("refusing: run.json mcp must be a list", done.stderr)
                self.assertEqual(self.recorded_argv(record), [], "claude ran for an mcp that is not a list")

    def test_launcher__a_picked_entry_that_is_malformed_is_refused_and_named(self):
        """An entry is the Owner's approval of exactly one binary and its arguments; one that is not JSON, lacks a key, or holds a value the launcher would have to split or guess at must stop the launch and name the file, not start a server nobody approved in that shape."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])
        without_command = {k: v for k, v in MCP_GIZMO.items() if k != "command"}
        cases = (
            "{ not json",
            json.dumps(without_command),
            json.dumps(dict(MCP_GIZMO, args="serve --stdio")),
            json.dumps(dict(MCP_GIZMO, env={"GIZMO_TELEMETRY": 0})),
            json.dumps(dict(MCP_GIZMO, version_args=[])),
            json.dumps(dict(MCP_GIZMO, version_args=["--version\n"])),
            json.dumps(dict(MCP_GIZMO, version_pin="")),
            json.dumps(dict(MCP_GIZMO, command="gizmo server")),
            json.dumps(dict(MCP_GIZMO, command="../bin/gizmo-server")),
            json.dumps(dict(MCP_GIZMO, workflows=["alpha", "beta\n"])),
        )
        for text in cases:
            with self.subTest(entry=text):
                (launcher.parent.parent / "mcp/gizmo.json").write_text(text)
                record.unlink(missing_ok=True)

                done = self.run_launcher(launcher, session, env, "--yes")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("gizmo.json is malformed", done.stderr)
                self.assertNotIn("jq: error", done.stderr)
                self.assertEqual(self.recorded_argv(record), [], "claude ran with a malformed entry")

    def test_launcher__a_list_file_whose_name_is_not_a_server_name_is_refused_as_malformed(self):
        """The file name is the server's key in the list, and a name the list cannot hold, such as `Widget` on a case-insensitive volume, is an entry nobody can pick by that name; the Owner learns of it at the next launch that uses the list, not never."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO)
        (launcher.parent.parent / "mcp/Widget.json").write_text(json.dumps(dict(MCP_WIDGET, server="Widget", allow=["mcp__Widget__*"])))
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])

        done = self.run_launcher(launcher, session, env, "--yes")

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("Widget.json is malformed", done.stderr)
        self.assertEqual(self.recorded_argv(record), [], "claude ran beside a list file nobody can pick")

    def test_launcher__a_server_binary_that_reads_stdin_cannot_skip_the_next_server_s_check(self):
        """Every picked server owes its binary check, whatever an earlier server's binary does while printing its version; one that drained the launcher's plan would start the next server with no command at all."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO, MCP_WIDGET)
        binary, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        self.given_session()
        self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}, {"server": "widget", "workflows": ["reads"]}])
        # A binary gets no descriptor it was not given; fd 3 carries the plan.
        for reads in ("cat >/dev/null", "cat <&3 >/dev/null 2>&1"):
            with self.subTest(reads=reads):
                binary.write_text("#!/bin/bash\n%s\necho 2.7.12\n" % reads)

                done = self.run_launcher(launcher, session, env, "--yes")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("widget-server is not on PATH", done.stderr)
                self.assertEqual(self.recorded_argv(record), [], "claude ran with a server whose binary was never checked")

    def test_launcher__an_unreadable_list_file_blocks_only_a_brief_that_picks(self):
        """A brief with no picks never needs the list, so an entry the launcher cannot read stays unread for it; for a brief that picks, it is malformed, as one that is not JSON is."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        launcher = self.given_approved_list(MCP_GIZMO, MCP_WIDGET)
        _, env = self.given_server_binary(env, MCP_GIZMO, "2.7.12")
        unreadable = launcher.parent.parent / "mcp/widget.json"
        unreadable.chmod(0)
        self.given_session()

        with self.subTest(mcp="absent"):
            self.given_mcp_brief(worktree)

            done = self.run_launcher(launcher, session, env, "--dry-run")

            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertNotIn("jq: error", done.stderr)
        with self.subTest(mcp="gizmo"):
            self.given_mcp_brief(worktree, mcp=[{"server": "gizmo", "workflows": ["alpha"]}])

            done = self.run_launcher(launcher, session, env, "--yes")

            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn("widget.json is malformed", done.stderr)
            self.assertEqual(self.recorded_argv(record), [], "claude ran beside a list file the launcher could not read")

    def test_launcher__the_model_is_the_next_unit_s_own_where_the_brief_names_one(self):
        """Rotation starts a fresh session per unit, so a docs unit need not run on the model the behavior unit beside it needs — and a model read off a unit already done would price the session from work that is finished."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()

        def given(unit_models=(), **fields):
            run = dict(self.run_json(), worktree=str(worktree.resolve()), **fields)
            for unit, unit_model in zip(run["units"], unit_models):
                unit["model"] = unit_model
            (session / "run.json").write_text(json.dumps(run))

        def plan(*flags):
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--dry-run", *flags], env=env, capture_output=True, text=True)
            return done.returncode, done.stdout + done.stderr

        given()
        self.assertIn("model:     opus Worker (from profile standard, kind other)", plan()[1])
        given(model="haiku")
        self.assertIn("model:     haiku Worker (from brief)", plan()[1])
        given(("sonnet", "opus"), model="haiku")
        self.assertIn("model:     sonnet Worker (from unit U1)", plan()[1])
        self.assertIn("model:     fable Worker (from flag)", plan("--model", "fable")[1])
        given(("gpt-5", "opus"), model="haiku")
        code, out = plan()
        self.assertEqual(code, 1, out)
        self.assertIn("unit U1", out)
        given(("sonnet", "opus"), model="haiku")
        self.must("preflight-pass")
        self.must("intake-complete")
        self.given_unit_closed("U1")
        self.must("request-rotate")
        self.assertIn("model:     opus Worker (from unit U2)", plan("--rotate")[1])

    def test_launcher__a_session_started_on_a_unit_s_model_leaves_the_brief_s_own_alone(self):
        """A unit whose row names no model inherits the brief's, so a session started on one unit's model may not write it over the brief's: the next unit would run on the finished unit's model, and a dry run — the Lead's mandatory one — never performs the write."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)

        def start(*flags):
            record.write_text("")
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--yes", *flags], env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            argv = record.read_text().splitlines()
            return argv[argv.index("--model") + 1], done.stdout

        self.given_session()
        run = dict(self.run_json(), worktree=str(worktree.resolve()), model="opus")
        run["units"][0]["model"] = "sonnet"
        (session / "run.json").write_text(json.dumps(run))
        model, out = start()
        self.assertEqual(model, "sonnet", out)
        self.assertEqual(self.run_json()["model"], "opus", "the launch rewrote the brief's own model with U1's")
        self.assertIn("- model: sonnet (from unit U1)", (session / "LEDGER.md").read_text())
        self.must("preflight-pass")
        self.must("intake-complete")
        self.given_unit_closed("U1")
        self.must("request-rotate")
        model, out = start("--rotate")
        self.assertEqual(model, "opus", out)
        self.assertIn("model:     opus Worker (from brief)", out)

    # ------------------------------------------------------------ run profile

    def given_profiled(self, session, worktree):
        """Returns (given, plan): `given(kind, **run fields)` rewrites run.json with U1 on that kind, `plan(*flags)` dry-runs."""

        def given(kind, unit_model=None, **fields):
            run = dict(self.run_json(), worktree=str(worktree.resolve()), **fields)
            run["units"][0]["kind"] = kind
            run["units"][0]["model"] = unit_model
            (session / "run.json").write_text(json.dumps(run))

        def plan(*flags):
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--dry-run", *flags], env=self.profile_env, capture_output=True, text=True)
            return done.returncode, done.stdout + done.stderr

        return given, plan

    def test_launcher__the_profile_gives_each_unit_kind_its_worker_model_and_effort(self):
        """One field the Owner sets per brief, not a model and an effort per unit: the profile is the Owner's one dial for how much a Robowright Session is worth spending, and it has to expand to a different answer for a bounded unit than for a behavior one or it is just a global model flag."""
        session, worktree, self.profile_env = self.given_launcher_fixture()
        self.given_session()
        given, plan = self.given_profiled(session, worktree)
        table = {
            "showcase": {"tests": ("opus", "medium"), "behavior": ("opus", "high")},
            "standard": {"tests": ("sonnet", "medium"), "behavior": ("opus", "medium")},
            "economy": {"tests": ("sonnet", "low"), "behavior": ("opus", "medium")},
        }
        for profile, kinds in table.items():
            for kind, (model, effort) in kinds.items():
                given(kind, profile=profile)
                code, out = plan()
                self.assertEqual(code, 0, out)
                self.assertIn("model:     %s Worker (from profile %s, kind %s)" % (model, profile, kind), out)
                self.assertIn("effort:    %s (from profile %s, kind %s)" % (effort, profile, kind), out)
        # docs and refactor are the same bounded group as tests; ui is the same judgment group as behavior.
        for kind, model, effort in (("docs", "sonnet", "low"), ("refactor", "sonnet", "low"), ("ui", "opus", "medium")):
            given(kind, profile="economy")
            code, out = plan()
            self.assertEqual(code, 0, out)
            self.assertIn("model:     %s Worker (from profile economy, kind %s)" % (model, kind), out)
            self.assertIn("effort:    %s (from profile economy, kind %s)" % (effort, kind), out)
        # A unit whose row names no kind is read as the judgment group, never as the cheap one —
        # written as null, and written as the empty string a Planner's half-filled table leaves.
        for blank in (None, ""):
            given(blank, profile="economy", unit_model="opus")
            code, out = plan()
            self.assertEqual(code, 0, out)
            self.assertIn("model:     opus Worker (from unit U1)", out)
            self.assertIn("effort:    medium (from profile economy, kind other)", out)

    def test_launcher__a_null_profile_is_the_standard_one(self):
        """Every brief written before the field existed leaves it absent, and the Planner's template ships it null: the default has to be a real profile, not an empty model that falls through to opus for a docs unit."""
        session, worktree, self.profile_env = self.given_launcher_fixture()
        self.given_session()
        given, plan = self.given_profiled(session, worktree)
        for kind, model, effort in (("tests", "sonnet", "medium"), ("behavior", "opus", "medium")):
            for fields in ({"profile": None}, {}):
                given(kind, **fields)
                code, out = plan()
                self.assertEqual(code, 0, out)
                self.assertIn("model:     %s Worker (from profile standard, kind %s)" % (model, kind), out)
                self.assertIn("effort:    %s (from profile standard, kind %s)" % (effort, kind), out)

    def test_launcher__an_explicitly_set_model_or_effort_beats_the_profile(self):
        """The profile is a default the Owner departs from per unit; a value somebody wrote down by hand — the unit's model, the brief's own, the launch flag, the brief's effort — is the departure, and a profile that overrode it would make the departure unwritable."""
        session, worktree, self.profile_env = self.given_launcher_fixture()
        self.given_session()
        given, plan = self.given_profiled(session, worktree)

        given("tests", profile="economy", unit_model="fable")
        code, out = plan()
        self.assertEqual(code, 0, out)
        self.assertIn("model:     fable Worker (from unit U1)", out)
        # The unit's model is not the unit's effort: effort still comes from the profile row.
        self.assertIn("effort:    low (from profile economy, kind tests)", out)
        self.assertIn("model:     opus Worker (from flag)", plan("--model", "opus")[1])

        given("tests", profile="economy", model="haiku")
        self.assertIn("model:     haiku Worker (from brief)", plan()[1])

        given("tests", profile="economy", effort="xhigh")
        code, out = plan()
        self.assertEqual(code, 0, out)
        self.assertIn("effort:    xhigh (from brief)", out)
        self.assertIn("effort:    high (from flag)", plan("--effort", "high")[1])

        given("tests", profile="economy", effort="ludicrous")
        code, out = plan()
        self.assertEqual(code, 1, out)
        self.assertIn("low, medium, high, xhigh, or max", out)

    def test_launcher__the_profile_flag_beats_run_json_on_the_worker_path(self):
        """The Lead's documented cheap rerun is `--profile economy` over a brief that says otherwise; a flag the Worker path read past would run the brief's profile and print a `model:` line agreeing with the wrong answer."""
        session, worktree, self.profile_env = self.given_launcher_fixture()
        self.given_session()
        given, plan = self.given_profiled(session, worktree)
        given("tests", profile="showcase")
        code, out = plan("--profile", "economy")
        self.assertEqual(code, 0, out)
        self.assertIn("model:     sonnet Worker (from profile economy, kind tests)", out)
        self.assertIn("effort:    low (from profile economy, kind tests)", out)

    def test_launcher__a_refused_profile_names_the_place_it_was_written(self):
        """The refusal exists to send the Owner to the file that needs editing: a bad `--profile` blamed on run.json sends them to a file that is correct."""
        session, worktree, self.profile_env = self.given_launcher_fixture()
        self.given_session()
        given, plan = self.given_profiled(session, worktree)
        given("tests", profile="economy")
        code, out = plan("--profile", "cheep")
        self.assertEqual(code, 1, out)
        self.assertIn("profile (from flag)", out)
        self.assertNotIn("profile (from run.json)", out)

    def test_launcher__an_empty_profile_is_refused_rather_than_read_as_standard(self):
        """An empty string is what a half-filled BRIEF.md table leaves behind, and it is the one value that would run a showcase brief cheap while the provenance line claims `profile standard` as if somebody had written it."""
        session, worktree, self.profile_env = self.given_launcher_fixture()
        self.given_session()
        given, plan = self.given_profiled(session, worktree)
        given("tests", profile="")
        code, out = plan()
        self.assertEqual(code, 1, out)
        self.assertIn("profile (from run.json)", out)

    def test_launcher__a_multi_word_unit_kind_does_not_shift_into_the_model(self):
        """`kind` is a free-text column in the brief's unit table, not an enum: two words in it must not slide the unit's model one field over, which either refuses a model nobody wrote or silently reads one as the unit's."""
        session, worktree, self.profile_env = self.given_launcher_fixture()
        self.given_session()
        given, plan = self.given_profiled(session, worktree)
        given("ui tests", profile="standard")
        code, out = plan()
        self.assertEqual(code, 0, out)
        self.assertIn("model:     opus Worker (from profile standard, kind ui tests)", out)
        given("docs sonnet", profile="standard")
        code, out = plan()
        self.assertEqual(code, 0, out)
        self.assertIn("model:     opus Worker (from profile standard, kind docs sonnet)", out)

    def test_launcher__an_unknown_profile_name_is_refused_by_name(self):
        """A misspelt profile that fell back to standard would run a showcase brief cheap and never say so; the refusal has to name the three, because the names are the whole interface."""
        session, worktree, self.profile_env = self.given_launcher_fixture()
        self.given_session()
        given, plan = self.given_profiled(session, worktree)
        given("tests", profile="cheap")
        code, out = plan()
        self.assertEqual(code, 1, out)
        for name in ("showcase", "standard", "economy"):
            self.assertIn(name, out)

    def test_launcher__the_started_session_carries_its_effort_on_launch_resume_and_rotate(self):
        """`--effort` is not on the list of flags a backgrounded session carries over, and `--settings` is: the effort has to ride on both channels, and on all three commands, or a Worker the supervisor retires and wakes comes back at whatever effort a machine's `settings.json` may set."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)

        def start(*flags):
            record.write_text("")
            done = subprocess.run(["bash", str(LAUNCHER), "--session-dir", str(session), "--yes", *flags], env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            argv = record.read_text().splitlines()
            self.assertIn("--effort", argv)
            self.assertIn("--settings", argv)
            # A flag after the positional prompt is a different command, so membership is not enough.
            prompt = next(i for i, arg in enumerate(argv) if arg.startswith("/worker "))
            self.assertLess(argv.index("--effort") + 1, prompt, argv)
            self.assertLess(argv.index("--settings") + 1, prompt, argv)
            self.assertEqual(argv[argv.index("--effort") + 1], "medium", argv)
            settings = json.loads(argv[argv.index("--settings") + 1])
            self.assertEqual(settings["effortLevel"], "medium", settings)
            # The per-model key outranks the bare one, and a machine's settings.json may pin opus per id.
            self.assertEqual(settings["modelSettings"]["claude-opus-5-5"]["effortLevel"], "medium", settings)

        self.given_session()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()))))
        start()
        self.must("preflight-pass")
        self.must("intake-complete")
        start("--resume", "aaaa1111-0000-4000-8000-000000000000")
        self.given_unit_closed("U1")
        self.must("request-rotate")
        start("--rotate")

    def started_model_settings(self, unit_model):
        """The modelSettings object of the --settings JSON a Worker on `unit_model` is started with."""
        session, worktree, env = self.given_worker_launchable(unit_model=unit_model)
        record, env = self.given_stub_claude(env)
        done = self.launch_worker(session, env, "--yes")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        argv = record.read_text().splitlines()
        return json.loads(argv[argv.index("--settings") + 1])["modelSettings"]

    def test_launcher__a_sonnet_worker_pins_its_effort_under_the_current_sonnet_id(self):
        """The per-model effort key only applies when it names the id the session actually runs; a stale Sonnet id leaves a daemon-woken Sonnet Worker on the Owner's own pin (models overview, 2026-10-12: claude-sonnet-5-5)."""
        self.assertEqual(self.started_model_settings("sonnet"), {"claude-sonnet-5-5": {"effortLevel": "medium"}})

    def test_launcher__a_haiku_worker_pins_its_effort_under_the_current_haiku_id(self):
        """As for Sonnet: a stale Haiku id keys an effort no Haiku session reads (models overview, 2026-10-12: claude-haiku-5-5)."""
        self.assertEqual(self.started_model_settings("haiku"), {"claude-haiku-5-5": {"effortLevel": "medium"}})

    def test_launcher__a_document_only_role_takes_its_model_and_effort_from_the_profile(self):
        """A Planner or an Explainer is launched before any run.json exists, so its profile is a flag — and an economy project buys the cheaper planning model, which is the one place economy costs judgment rather than tokens."""
        root = self.dir / "fixture"
        project = root / "project"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")
        _, env = self.given_home(root, root / "sessions")

        def plan(*flags):
            done = subprocess.run(["bash", str(LAUNCHER), "--planner", "brief", "--slug", "sample-003-z", "--project", str(project), "--dry-run", *flags], env=env, capture_output=True, text=True)
            return done.returncode, done.stdout + done.stderr

        for flags, model, effort, source in (
            ((), "fable", "medium", "profile standard"),
            (("--profile", "showcase"), "fable", "high", "profile showcase"),
            (("--profile", "economy"), "opus", "medium", "profile economy"),
            (("--profile", "economy", "--model", "sonnet"), "sonnet", "medium", "flag"),
        ):
            code, out = plan(*flags)
            self.assertEqual(code, 0, out)
            self.assertIn("action:    launch brief-only Planner", out)
            # profile.md and the Lead's hand-off both send the reader to a `model:` line before --yes.
            self.assertIn("model:     %s (from %s)" % (model, source), out)
            self.assertIn("effort:    %s (from profile %s)" % (effort, flags[1] if flags else "standard"), out)
        code, out = plan("--profile", "cheap")
        self.assertEqual(code, 1, out)
        for name in ("showcase", "standard", "economy"):
            self.assertIn(name, out)
        # The Owner's call: an Explainer with no robowright.json entry is on opus under every profile.
        for profile, effort in (("showcase", "high"), ("standard", "medium"), ("economy", "medium")):
            done = subprocess.run(["bash", str(LAUNCHER), "--explainer", "report", "--slug", "sample", "--project", str(project), "--dry-run", "--profile", profile], env=env, capture_output=True, text=True, errors="replace")
            out = done.stdout + done.stderr
            self.assertEqual(done.returncode, 0, out)
            self.assertIn("model:     opus (from profile %s)" % profile, out)
            self.assertIn("effort:    %s (from profile %s)" % (effort, profile), out)

    def test_launcher__a_document_only_role_starts_with_no_mcp_servers(self):
        """A Planner and an Explainer read the plan and write markdown, and the Lead starts one after every finished Robowright Session: a configured server costs its tool roster and its instruction block on every one of them."""
        root = self.dir / "fixture"
        project = root / "project"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")
        _, env = self.given_home(root, root / "sessions")

        def plan(*flags):
            done = subprocess.run(["bash", str(LAUNCHER), *flags, "--project", str(project), "--dry-run"], env=env, capture_output=True)
            # printf %q renders the report prompt's em dash as a raw byte under a C locale.
            out = (done.stdout + done.stderr).decode(errors="replace")
            self.assertEqual(done.returncode, 0, out)
            return out.replace("\\", "")

        for flags in (("--planner", "brief", "--slug", "sample-003-z"), ("--explainer", "report")):
            out = plan(*flags)
            self.assertIn('mcp:       --strict-mcp-config --mcp-config {"mcpServers":{}}', out)
            # Twice: the mcp: line the Lead reads, and the command the launch would run.
            self.assertEqual(out.count("--strict-mcp-config"), 2, out)

    def test_launcher__a_brief_inherits_the_newest_intake_of_its_own_project(self):
        """The sessions root is shared across projects — another project's newer INTAKE.md must not reach this project's Planner."""
        root = self.dir / "fixture"
        sessions = root / "sessions"
        project = root / "project"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")
        own, other = sessions / "sample-001-x", sessions / "other-002-y"
        for age_seconds, session in ((200, own), (100, other)):
            session.mkdir(parents=True)
            (session / "INTAKE.md").write_text("intake\n")
            stamp = time.time() - age_seconds
            os.utime(session / "INTAKE.md", (stamp, stamp))
        _, env = self.given_home(root, sessions)
        brief = ["bash", str(LAUNCHER), "--planner", "brief", "--project", str(project), "--slug", "sample-003-z", "--dry-run"]
        done = subprocess.run(brief, env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"intake:    {own.resolve()}/INTAKE.md", done.stdout)
        self.assertNotIn(str(other.resolve()), done.stdout)

    def test_launcher__the_group_a_brief_inherits_from_ends_at_its_first_unit_number(self):
        """A slug may carry a second three-digit run — a bug number, a screen size — and the group is the project name before the first one; read at the last, the brief lands in a group of its own, the Planner writes it with nothing inherited, and no refusal says so."""
        root = self.dir / "fixture"
        sessions = root / "sessions"
        project = root / "project"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")
        earlier = sessions / "sample-011-earlier"
        earlier.mkdir(parents=True)
        (earlier / "INTAKE.md").write_text("intake\n")
        _, env = self.given_home(root, sessions)
        brief = ["bash", str(LAUNCHER), "--planner", "brief", "--project", str(project), "--slug", "sample-012-fix-404-page", "--dry-run"]
        done = subprocess.run(brief, env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"intake:    {earlier.resolve()}/INTAKE.md", done.stdout)

    def test_launcher__a_brief_never_inherits_an_intake_from_a_directory_whose_name_is_not_a_unit_name(self):
        """A Worker can make any directory under the shared sessions root and the newest intake's path reaches the Planner's prompt verbatim, so a directory named with a sentence must be passed over, silently, even where the install's group_regex is still unanchored."""
        root = self.dir / "fixture"
        project = root / "project"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")

        slug_sessions = root / "slug-sessions"
        earlier, stray = slug_sessions / "sample-011-earlier", slug_sessions / "sample-999-some words here"
        for age_seconds, session in ((200, earlier), (100, stray)):
            session.mkdir(parents=True)
            (session / "INTAKE.md").write_text("intake\n")
            stamp = time.time() - age_seconds
            os.utime(session / "INTAKE.md", (stamp, stamp))
        # An unanchored group_regex: the name check alone has to pass over the stray.
        _, env = self.given_home(root / "slug-install", slug_sessions,
                                 group_regex="^([0-9]*[a-z][a-z0-9]*(-[0-9]*[a-z][a-z0-9]*)*)-[0-9]{3}-")
        brief = ["bash", str(LAUNCHER), "--planner", "brief", "--project", str(project), "--slug", "sample-012-fix", "--dry-run"]
        done = subprocess.run(brief, env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"intake:    {earlier.resolve()}/INTAKE.md", done.stdout)
        self.assertNotIn("some words here", done.stdout + done.stderr)

        ticket_sessions = root / "ticket-sessions"
        old, stray = ticket_sessions / "ABC-1-old", ticket_sessions / "ABC-2-some words here"
        for age_seconds, session in ((200, old), (100, stray)):
            session.mkdir(parents=True)
            (session / "INTAKE.md").write_text("intake\n")
            stamp = time.time() - age_seconds
            os.utime(session / "INTAKE.md", (stamp, stamp))
        _, env = self.given_home(root / "ticket-install", ticket_sessions, ticket_regex="^[A-Z][A-Z0-9]*-[0-9]+$", ticket_example="ABC-1234",
                                 slug_regex="^[a-z0-9]+(-[a-z0-9]+)*$", slug_example="review-feedback",
                                 group_regex="^([A-Z][A-Z0-9]*)-[0-9]+-")
        brief = ["bash", str(LAUNCHER), "--planner", "brief", "--project", str(project), "--slug", "review-feedback", "--ticket", "ABC-9", "--dry-run"]
        done = subprocess.run(brief, env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"intake:    {old.resolve()}/INTAKE.md", done.stdout)
        self.assertNotIn("some words here", done.stdout + done.stderr)

        # An empty first segment is not a ticket: with no ^ on group_regex, only the split can pass over it.
        leading_hyphen = ticket_sessions / "-ABC-3-foo"
        leading_hyphen.mkdir(parents=True)
        (leading_hyphen / "INTAKE.md").write_text("intake\n")
        _, env = self.given_home(root / "unanchored-install", ticket_sessions, ticket_regex="^[A-Z][A-Z0-9]*-[0-9]+$", ticket_example="ABC-1234",
                                 slug_regex="^[a-z0-9]+(-[a-z0-9]+)*$", slug_example="review-feedback",
                                 group_regex="([A-Z][A-Z0-9]*)-[0-9]+-")
        done = subprocess.run(brief, env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"intake:    {old.resolve()}/INTAKE.md", done.stdout)
        self.assertNotIn("-ABC-3-foo", done.stdout + done.stderr)

        # A ticket_regex with no $ still never lets a sentence through: the fixed ticket form comes first.
        loose_sessions = root / "loose-sessions"
        old, stray = loose_sessions / "ABC-1-old", loose_sessions / "ABC-1-some words here-x"
        for age_seconds, session in ((200, old), (100, stray)):
            session.mkdir(parents=True)
            (session / "INTAKE.md").write_text("intake\n")
            stamp = time.time() - age_seconds
            os.utime(session / "INTAKE.md", (stamp, stamp))
        _, env = self.given_home(root / "loose-install", loose_sessions, ticket_regex="^[A-Z][A-Z0-9]*-[0-9]+", ticket_example="ABC-1234",
                                 slug_regex="^[a-z0-9]+(-[a-z0-9]+)*$", slug_example="review-feedback",
                                 group_regex="^([A-Z][A-Z0-9]*)-[0-9]+-")
        done = subprocess.run(brief, env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"intake:    {old.resolve()}/INTAKE.md", done.stdout)
        self.assertNotIn("some words here", done.stdout + done.stderr)

    # ------------------------------------------------------------ launch hand-off and model override (U3 · D3, D4, D5)

    PRIOR_LEDGER = "# Ledger\n\n## 2026-09-20 09:00 — launch via run-launch.sh\n- session name: worker-sample-001-x\n"
    HAND_OFF_HEADING = r"(?m)^## \d{4}-\d{2}-\d{2}.* — hand-off via %s$" % re.escape(LAUNCHER.name)

    def given_worker_launchable(self, unit_model=None, **fields):
        """The launcher fixture on a legal fresh launch, run.json pointing at the worktree, U1 on `unit_model`, and one earlier LEDGER.md entry. Returns (session, worktree, env)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        run = dict(self.run_json(), worktree=str(worktree.resolve()), **fields)
        run["units"][0]["model"] = unit_model
        (session / "run.json").write_text(json.dumps(run))
        (session / "LEDGER.md").write_text(self.PRIOR_LEDGER)
        return session, worktree, env

    def given_document_only_project(self):
        """A project folder under a scratch sessions root. self.dir becomes the brief's session dir, which the launch itself creates. Returns (project, env)."""
        root = Path(self.tmp.name) / "fixture"
        sessions = root / "sessions"
        sessions.mkdir(parents=True)
        project = root / "project"
        project.mkdir()
        (project / "PROJECT.md").write_text("# plan\n")
        _, env = self.given_home(root, sessions)
        self.dir = sessions / "sample-003-z"
        return project, env

    def launch_worker(self, session, env, *flags):
        return subprocess.run(["bash", str(LAUNCHER), "--run-dir", str(session), *flags], env=env, capture_output=True, text=True, errors="replace")

    def launch_brief(self, project, env):
        return subprocess.run(["bash", str(LAUNCHER), PLANNER_FLAG, "brief", "--slug", "sample-003-z", "--project", str(project), "--yes"], env=env, capture_output=True, text=True, errors="replace")

    def paste_line(self, stdout):
        """The command after `paste this yourself:`, on the label's own line or the next."""
        found = re.search(r"^paste this yourself:\s*(cd .*)$", stdout, re.M)
        self.assertIsNotNone(found, stdout)
        return found.group(1)

    def test_launcher__an_eperm_refusal_at_the_worker_site_is_a_hand_off_not_a_failure(self):
        """An EPERM from claude --bg is a launch the Owner finishes by pasting — exit 0 ending `launch is yours`, one hand-off entry in the session's ledger, the marker written, run.json untouched; read as a failure the Lead re-runs --yes into the same refusal, read as a start it waits on a session that never ran."""
        session, worktree, env = self.given_worker_launchable()
        _, env = self.given_stub_claude_eperm(env)
        run_before = (session / "run.json").read_bytes()

        done = self.launch_worker(session, env, "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(done.stdout.rstrip().endswith("launch is yours"), done.stdout)
        self.assertNotIn("started. attach:", done.stdout)
        ledger = (session / "LEDGER.md").read_text()
        self.assertTrue(ledger.startswith(self.PRIOR_LEDGER), ledger)
        self.assertEqual(ledger.count("hand-off via"), 1, ledger)
        self.assertRegex(ledger, self.HAND_OFF_HEADING)
        self.assertIn("EPERM; nothing started", ledger)
        self.assertEqual((worktree / ".claude/autonomous-run").read_text(), f"{session.resolve()}\n")
        self.assertEqual((session / "run.json").read_bytes(), run_before)

    def test_launcher__the_worker_hand_off_prints_a_paste_line_that_runs_the_launch_it_tried(self):
        """The paste line is `cd <worktree> && [ "$(pwd -P)" = <worktree> ] && <env scrub> <command>` with every word quoted — without the cd the session starts wherever the Owner's shell is, without the compare a folder swapped for a link since the check moves it (U38 review 6 F1), without the scrub it inherits CLAUDECODE, and one unquoted word splits the --settings JSON the per-session env rides in (assumed Q1)."""
        session, worktree, env = self.given_worker_launchable()
        record, env = self.given_stub_claude_eperm(env)

        done = self.launch_worker(session, env, "--yes")

        tried = record.read_text()
        line = self.paste_line(done.stdout)
        self.assertTrue(line.startswith(f'cd {worktree.resolve()} && [ "$(pwd -P)" = {worktree.resolve()} ] && env -u CLAUDECODE '), line)
        self.assertIn("--settings", line)
        self.assertEqual(subprocess.run(["bash", "-n", "-c", line], capture_output=True).returncode, 0, line)
        record.write_text("")
        subprocess.run(["bash", "-c", line], env=env, capture_output=True)
        self.assertEqual(record.read_text(), tried, line)

    def test_launcher__the_hand_off_entry_records_the_paste_line_it_printed(self):
        """The Lead re-hands an unpasted hand-off from the ledger (lead/SKILL.md `orphaned`) and may never re-run --yes for it, so the entry has to carry the exact line — after a rotation the printed one is gone (U3 gate F1)."""
        session, worktree, env = self.given_worker_launchable()
        _, env = self.given_stub_claude_eperm(env)

        done = self.launch_worker(session, env, "--yes")

        self.assertIn(f"- paste: {self.paste_line(done.stdout)}\n", (session / "LEDGER.md").read_text())

    def test_launcher__an_eperm_refusal_at_the_document_only_site_is_a_hand_off_into_its_own_ledger(self):
        """A Planner or Explainer launch refused with EPERM is handed off the same way, its entry in the ledger that role's successful launch writes to and its paste line starting in the project folder — the Lead reads both sites the same way (assumed Q1)."""
        project, env = self.given_document_only_project()
        _, env = self.given_stub_claude_eperm(env)

        done = self.launch_brief(project, env)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(done.stdout.rstrip().endswith("launch is yours"), done.stdout)
        ledger = (self.dir / "LEDGER.md").read_text()
        self.assertEqual(ledger.count("hand-off via"), 1, ledger)
        self.assertRegex(ledger, self.HAND_OFF_HEADING)
        line = self.paste_line(done.stdout)
        self.assertTrue(line.startswith(f'cd {project.resolve()} && [ "$(pwd -P)" = {project.resolve()} ] && env -u CLAUDECODE '), line)
        self.assertIn("--settings", line)
        self.assertEqual(subprocess.run(["bash", "-n", "-c", line], capture_output=True).returncode, 0, line)

    def test_launcher__any_other_claude_failure_at_the_worker_site_still_exits_1_with_no_ledger_entry(self):
        """Only EPERM is a hand-off: a claude that failed for any other reason did not start and has nothing to paste, and an exit 0 would tell the Lead it had."""
        session, worktree, env = self.given_worker_launchable()
        _, env = self.given_stub_claude_failing(env, "API Error: 529 Overloaded")

        done = self.launch_worker(session, env, "--yes")

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("API Error: 529 Overloaded", done.stderr)
        self.assertNotIn("launch is yours", done.stdout + done.stderr)
        self.assertNotIn("paste this yourself", done.stdout + done.stderr)
        self.assertEqual((session / "LEDGER.md").read_text(), self.PRIOR_LEDGER)

    def test_launcher__any_other_claude_failure_at_the_document_only_site_still_exits_1_with_no_ledger_entry(self):
        """The document-only site keeps today's exit 1 for a non-EPERM failure too — a hand-off arm that caught every failure there would ledger launches that never happened."""
        project, env = self.given_document_only_project()
        _, env = self.given_stub_claude_failing(env, "API Error: 529 Overloaded")

        done = self.launch_brief(project, env)

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertNotIn("launch is yours", done.stdout + done.stderr)
        self.assertNotIn("paste this yourself", done.stdout + done.stderr)
        self.assertFalse((self.dir / "LEDGER.md").exists())

    # ------------------------------------------------------------ pinning a handed-off launch (018 U1 · D2)

    PASTED_ID = "cccc3333-0000-4000-8000-000000000000"
    PASTED_BG = "cccc3333"
    EARLIER_ID = "aaaa1111-0000-4000-8000-000000000000"
    DECOY_ID = "9999eeee-0000-4000-8000-000000000000"
    PIN_HEADING = r"(?m)^## .*pinned after hand-off.*$"

    def given_handed_off(self, **fields):
        """A Worker launch that claude --bg refused with EPERM: `launch is yours` printed, run.json as the Planner wrote it (plus `fields`), one hand-off entry in LEDGER.md. Returns (session, worktree, env, argv file)."""
        session, worktree, env = self.given_worker_launchable(**fields)
        record, env = self.given_stub_claude_eperm(env)
        done = self.launch_worker(session, env, "--yes")
        self.assertIn("launch is yours", done.stdout, done.stdout + done.stderr)
        return session, worktree, env, record

    def given_registered_session(self, env, session_id, **fields):
        """A `~/.claude/sessions/<first 8>.json` entry under the scratch HOME, as Claude Code writes one for a started session; `fields` adds cwd, pid or the like."""
        path = Path(env["HOME"]) / ".claude/sessions" / f"{session_id[:8]}.json"
        path.write_text(json.dumps(dict(sessionId=session_id, **fields)))

    def pin(self, session, env, *args):
        return self.launch_worker(session, env, "--pin", *args)

    def transcript_for(self, worktree, session_id):
        """The launch path's transcript rule: ~/.claude/projects/<worktree with every non-alphanumeric as "-">/<sessionId>.jsonl."""
        return "~/.claude/projects/%s/%s.jsonl" % (re.sub(r"[^A-Za-z0-9]", "-", str(worktree.resolve())), session_id)

    def test_launcher__a_pin_by_background_id_records_the_session_it_names_and_its_transcript(self):
        """A hand-off writes nothing to run.json, so until the Lead pins the pasted session --resume has no id and the cost reader prices every transcript the worktree ever saw (review F1)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.DECOY_ID)
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        run = self.run_json()
        self.assertEqual(run.get("session_id"), self.PASTED_ID, done.stdout + done.stderr)
        self.assertEqual(run.get("transcripts"), [self.transcript_for(worktree, self.PASTED_ID)])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_launcher__a_pin_by_full_session_id_records_the_same_session_as_a_pin_by_background_id(self):
        """The Lead may hold either form of the id — `claude agents --json` prints the short one, the registry the long one — and a pin that took only one would refuse the other."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_ID)

        run = self.run_json()
        self.assertEqual(run.get("session_id"), self.PASTED_ID, done.stdout + done.stderr)
        self.assertEqual(run.get("transcripts"), [self.transcript_for(worktree, self.PASTED_ID)])

    def test_launcher__a_pin_writes_the_same_session_id_and_transcripts_a_launch_writes_for_that_session(self):
        """The pin after a hand-off and the pin after a started launch must agree field for field — if they drift, --resume and the cost reader read a pinned hand-off differently from a launched session (D2)."""
        session, worktree, env = self.given_worker_launchable()
        _, env = self.given_stub_claude(env)
        self.given_registered_session(env, "bbbb2222-0000-4000-8000-000000000000", cwd=str(worktree.resolve()))
        as_handed_off = (session / "run.json").read_bytes()
        launched = self.launch_worker(session, env, "--yes")
        by_launch = self.run_json()
        self.assertEqual(by_launch.get("session_id"), "bbbb2222-0000-4000-8000-000000000000", launched.stdout + launched.stderr)
        (session / "run.json").write_bytes(as_handed_off)

        done = self.pin(session, env, "bbbb2222")

        by_pin = self.run_json()
        self.assertEqual((by_pin.get("session_id"), by_pin.get("transcripts")), (by_launch["session_id"], by_launch["transcripts"]), done.stdout + done.stderr)

    def test_launcher__a_pin_replaces_the_session_id_an_earlier_session_left(self):
        """A rotation hand-off pins over the previous session's id; keeping the old one would make --resume wake a session that already ended its turn (D2: overwriting, as a launch does)."""
        session, worktree, env, _ = self.given_handed_off(session_id=self.EARLIER_ID)
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(self.run_json().get("session_id"), self.PASTED_ID, done.stdout + done.stderr)

    def test_launcher__a_pin_appends_the_transcript_and_keeps_the_earlier_sessions(self):
        """transcripts is what the Robowright Session is priced from; replacing it would drop every earlier session's cost from the report."""
        earlier = "~/.claude/projects/-earlier/aaaa1111-0000-4000-8000-000000000000.jsonl"
        session, worktree, env, _ = self.given_handed_off(transcripts=[earlier])
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(self.run_json().get("transcripts"), [earlier, self.transcript_for(worktree, self.PASTED_ID)], done.stdout + done.stderr)

    def test_launcher__pinning_the_same_session_twice_lists_its_transcript_once(self):
        """A Lead that re-runs a pin it is unsure landed must not double the session's cost in the report (assumed Q2)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))
        self.pin(session, env, self.PASTED_BG)

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(self.run_json().get("transcripts"), [self.transcript_for(worktree, self.PASTED_ID)], done.stdout + done.stderr)

    def test_launcher__a_pin_whose_id_matches_no_registered_session_is_refused_and_changes_nothing(self):
        """An id the registry does not know names no session this Mac started; pinning it anyway would point --resume and the cost reader at a transcript that does not exist (D2)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.DECOY_ID)
        run_before = (session / "run.json").read_bytes()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual((session / "run.json").read_bytes(), run_before)

    def test_launcher__a_pin_id_found_inside_a_session_id_but_not_at_its_start_is_no_match(self):
        """The lookup is the launch path's prefix scan; a substring match would pin some other session whose id merely contains the eight characters (D2)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, "eeee5555-0000-4000-8000-0000cccc3333", cwd=str(worktree.resolve()))
        run_before = (session / "run.json").read_bytes()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual((session / "run.json").read_bytes(), run_before)

    def test_launcher__a_refused_pin_adds_no_ledger_entry(self):
        """An entry headed `pinned after hand-off` for a pin that was refused tells the Lead the session is pinned when it is not (assumed Q1; green at red — owes its kill first)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.DECOY_ID)
        ledger_before = (session / "LEDGER.md").read_bytes()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual((session / "LEDGER.md").read_bytes(), ledger_before, done.stdout + done.stderr)

    def test_launcher__a_pin_needs_no_yes_and_starts_no_claude_session(self):
        """The pasted session is already running; a pin that launched would start a second Worker in the same worktree (D2: --pin launches nothing)."""
        session, worktree, env, record = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))
        calls_before = record.read_text()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(record.read_text(), calls_before)

    def test_launcher__a_pin_given_yes_still_starts_no_claude_session(self):
        """--yes beside --pin must not fall through into a launch that starts a second Worker and pins twice (D2 and the brief's --yes hotspot; exit code left open, assumed Q3; green at red — owes its kill first)."""
        session, worktree, env, record = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))
        calls_before = record.read_text()

        done = self.pin(session, env, self.PASTED_BG, "--yes")

        self.assertEqual(record.read_text(), calls_before, done.stdout + done.stderr)

    def test_launcher__a_pin_succeeds_while_the_pasted_session_is_live_in_the_worktree(self):
        """When the Lead pins, the pasted session is live in this worktree — the very thing the launch path's live-session check refuses — so a pin that ran that check could never succeed (D2)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()), pid=os.getpid(), status="busy")

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.run_json().get("session_id"), self.PASTED_ID)

    def test_launcher__a_pin_succeeds_after_the_pasted_worker_has_moved_the_phase_on(self):
        """The pasted Worker passes preflight and intake within minutes, and launch is illegal from implement; a pin that checked the phase would refuse the normal case (D2)."""
        session, worktree, env, _ = self.given_handed_off()
        self.must("preflight-pass")
        self.must("intake-complete")
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.run_json().get("session_id"), self.PASTED_ID)

    def test_launcher__a_pin_succeeds_on_a_dirty_worktree(self):
        """The pasted Worker is editing the worktree while the Lead pins; the launch path's dirty-tree refusal would block every pin taken mid-unit (D2)."""
        session, worktree, env, _ = self.given_handed_off()
        (worktree / "work-in-progress.txt").write_text("the pasted Worker's edit\n")
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.run_json().get("session_id"), self.PASTED_ID)

    def test_launcher__a_pin_succeeds_while_another_session_holds_a_listed_lock(self):
        """A lock only decides whether a second holder may start; a pin starts nothing, so a held lock must not stop the Lead recording the session that is already running (D2)."""
        session, worktree, env, _ = self.given_handed_off(locks=["sim"])
        holder = session.parent / "sample-002-y"
        holder.mkdir()
        (session.parent / ".sim-lock").mkdir()
        (session.parent / ".sim-lock/owner").write_text(f"{holder}\n")
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.run_json().get("session_id"), self.PASTED_ID)

    def test_launcher__a_pin_whose_worktree_is_missing_names_the_path_run_json_gives(self):
        """The --pin refusal printed `worktree  does not exist` — the failed resolve had already emptied the path, so the Lead could not tell which worktree was gone (review F12, D10 R1)."""
        session, worktree, env, _ = self.given_handed_off()
        missing = str(worktree.parent / "wt-torn-down")
        run = self.run_json()
        run["worktree"] = missing
        (session / "run.json").write_text(json.dumps(run))
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(missing, done.stdout + done.stderr)

    def test_launcher__a_pin_whose_worktree_is_missing_prints_the_worktree_add_command_run_json_fills(self):
        """A refusal that only says the worktree is gone left the Lead to work out the command that creates it; the command filled from run.json is the fix (026 D4 R1; wording assumed Q1)."""
        session, worktree, env, _ = self.given_handed_off()
        missing = str(worktree.parent / "wt-torn-down")
        run = self.run_json()
        run["worktree"] = missing
        run["units"][0]["branch"] = "robowright/sample-001-first-unit"
        run["units"][1]["branch"] = "robowright/sample-001-second-unit"
        (session / "run.json").write_text(json.dumps(run))
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add -b robowright/sample-001-first-unit {missing} <base>"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)

    def test_launcher__a_pin_of_a_accepted_session_whose_worktree_is_gone_prints_no_worktree_add_command(self):
        """An accepted session's worktree is torn down on purpose; telling the Lead to recreate it sends them to rebuild finished work (026 hotspot on run-launch.sh:693; assumed Q2)."""
        session, worktree, env, _ = self.given_handed_off()
        run = self.run_json()
        run["worktree"] = str(worktree.parent / "wt-torn-down")
        run["phase"] = "done"
        run["units"][0]["branch"] = "robowright/sample-001-first-unit"
        (session / "run.json").write_text(json.dumps(run))
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertNotIn("git worktree add", done.stdout + done.stderr)

    # ------------------------------------------------------------ the pin refusal's hint follows the stored phase (027 U2 · D2)

    def given_pin_with_worktree_gone(self, phase, branch):
        """given_handed_off, then run.json's worktree moved to a path that does not exist, `phase` stored, and units[0].branch set to `branch`; the pasted session is registered in the real worktree. Returns (session, env, the missing path)."""
        session, worktree, env, _ = self.given_handed_off()
        missing = str(worktree.parent / "wt-torn-down")
        run = self.run_json()
        run["worktree"] = missing
        run["phase"] = phase
        run["units"][0]["branch"] = branch
        (session / "run.json").write_text(json.dumps(run))
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))
        return session, env, missing

    def test_launcher__a_pin_of_a_parked_session_whose_worktree_is_gone_prints_no_command_and_says_it_is_finished(self):
        """The pin path has no phase check before the worktree, so a parked session was told to recreate a worktree torn down with finished work (027 D2 R2; finished line assumed in brief)."""
        session, env, missing = self.given_pin_with_worktree_gone(phase="parked", branch="robowright/sample-001-first-unit")

        done = self.pin(session, env, self.PASTED_BG)

        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        finished = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            "run.json phase is parked: the session is finished, so its worktree is not recreated"), out)
        self.assertIsNotNone(finished, out)
        self.assertGreater(finished.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add", out)

    def test_launcher__a_pin_of_a_accepted_session_whose_worktree_is_gone_says_it_is_finished(self):
        """An accepted session's refusal said only that the worktree does not exist, which reads as a broken brief rather than finished work (027 D2 R2; finished line assumed in brief)."""
        session, env, missing = self.given_pin_with_worktree_gone(phase="done", branch="robowright/sample-001-first-unit")

        done = self.pin(session, env, self.PASTED_BG)

        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        finished = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            "run.json phase is done: the session is finished, so its worktree is not recreated"), out)
        self.assertIsNotNone(finished, out)
        self.assertGreater(finished.start(), out.index(refusal), out)

    def test_launcher__a_pin_of_an_implementing_session_whose_worktree_is_missing_prints_the_command_that_reuses_its_branch(self):
        """Past briefed the unit's branch already exists, so the `-b` command the refusal printed fails as printed (027 D2 R3)."""
        session, env, missing = self.given_pin_with_worktree_gone(phase="implement", branch="robowright/sample-001-first-unit")

        done = self.pin(session, env, self.PASTED_BG)

        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} robowright/sample-001-first-unit"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add -b", out)
        self.assertNotIn("<base>", out)

    def test_launcher__a_pin_of_a_stopped_session_whose_worktree_is_missing_prints_the_command_that_reuses_its_branch(self):
        """A stopped session's branch already exists, so the `-b` command the refusal printed fails as printed (027 D2 R3)."""
        session, env, missing = self.given_pin_with_worktree_gone(phase="stopped", branch="robowright/sample-001-first-unit")

        done = self.pin(session, env, self.PASTED_BG)

        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} robowright/sample-001-first-unit"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add -b", out)
        self.assertNotIn("<base>", out)

    def test_launcher__a_pin_in_a_phase_the_launcher_does_not_know_whose_worktree_is_missing_prints_the_command_that_reuses_its_branch(self):
        """Only a briefed session gets the `-b` form; reading an unknown phase as briefed would print a command that fails on a branch that exists (027 D2 R3)."""
        session, env, missing = self.given_pin_with_worktree_gone(phase="paused", branch="robowright/sample-001-first-unit")

        done = self.pin(session, env, self.PASTED_BG)

        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} robowright/sample-001-first-unit"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add -b", out)
        self.assertNotIn("<base>", out)

    def test_launcher__a_pin_past_briefed_whose_unit_branch_is_empty_prints_the_reuse_command_with_a_branch_placeholder(self):
        """An empty units[0].branch filled the command with nothing, leaving `git worktree add <wt> ` with the branch silently missing (027 D2 R4)."""
        session, env, missing = self.given_pin_with_worktree_gone(phase="implement", branch="")

        done = self.pin(session, env, self.PASTED_BG)

        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} <branch>"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)

    # ------------------------------------------------------------ a retired device_lock, and the lock-name check on locks[]

    def given_lock_held_elsewhere(self, session, name):
        """<sessions root>/.<name>-lock whose owner is another session dir under the same root. Returns that holder."""
        holder = session.parent / "sample-002-y"
        holder.mkdir(exist_ok=True)
        lock = session.parent / f".{name}-lock"
        lock.mkdir()
        (lock / "owner").write_text(f"{holder}\n")
        return holder

    def test_launcher__a_device_lock_is_not_read_as_a_lock(self):
        """With locks absent, `device_lock: "ios-build"` serialises on nothing, so a lock another session holds under that name does not refuse the launch — the retired spelling would still gate launches (Owner 2026-09-23)."""
        session, _, env = self.given_worker_launchable(device_lock="ios-build")
        self.given_lock_held_elsewhere(session, "ios-build")

        done = self.launch_worker(session, env, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_launcher__a_device_lock_that_is_no_lock_name_is_not_refused(self):
        """A device_lock of true, 5, an object or a bad string no longer refuses the launch — the retired key would still be validated as if it were read."""
        session, _, env = self.given_worker_launchable()
        for value in (True, 5, {"name": "ios-build"}, "iOS Build"):
            with self.subTest(device_lock=value):
                (session / "run.json").write_text(json.dumps(dict(self.run_json(), device_lock=value)))

                done = self.launch_worker(session, env, "--dry-run")

                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_launcher__a_locks_entry_that_is_not_a_lock_name_is_refused(self):
        """The loop below the jq splits on newlines, so `"a\\nb"` would serialise on two locks no brief names, and `"iOS Build"` on one park never releases (D5 R1, end-of-stack F2)."""
        session, _, env = self.given_worker_launchable()
        for value in ("a\nb", "iOS Build"):
            with self.subTest(entry=value):
                (session / "run.json").write_text(json.dumps(dict(self.run_json(), locks=[value])))

                done = self.launch_worker(session, env, "--dry-run")

                self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn("lock", done.stdout + done.stderr)

    def test_launcher__a_pin_appends_one_ledger_entry_headed_pinned_after_hand_off(self):
        """The ledger is how the Lead and the Owner learn a hand-off was finished; without the entry a pinned hand-off reads as one still waiting on the paste (D2)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))
        ledger_before = (session / "LEDGER.md").read_text()

        done = self.pin(session, env, self.PASTED_BG)

        ledger = (session / "LEDGER.md").read_text()
        self.assertTrue(ledger.startswith(ledger_before), ledger)
        appended = ledger[len(ledger_before):]
        self.assertEqual(len(re.findall(r"(?m)^## ", appended)), 1, done.stdout + done.stderr + appended)
        self.assertRegex(appended, self.PIN_HEADING)

    def test_launcher__the_pin_entry_carries_the_background_id_line_the_launch_entry_carries(self):
        """The background id is what `claude attach` and `claude logs` take; the launch entry records it for a started session, and a pinned hand-off needs the same line to be reachable (D2)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))
        ledger_before = (session / "LEDGER.md").read_text()

        done = self.pin(session, env, self.PASTED_BG)

        appended = (session / "LEDGER.md").read_text()[len(ledger_before):]
        self.assertIn("- background id: cccc3333 (claude attach cccc3333 · claude logs cccc3333)\n", appended, done.stdout + done.stderr)

    def test_launcher__a_pin_by_full_session_id_records_its_first_eight_characters_as_the_background_id(self):
        """`claude attach` takes the eight-character id, not the full sessionId; a pin by full id that wrote the long form would print an attach command that fails (Language: background id)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))
        ledger_before = (session / "LEDGER.md").read_text()

        done = self.pin(session, env, self.PASTED_ID)

        appended = (session / "LEDGER.md").read_text()[len(ledger_before):]
        self.assertIn("- background id: cccc3333 (claude attach cccc3333 · claude logs cccc3333)\n", appended, done.stdout + done.stderr)

    def test_launcher__a_pinned_hand_off_resumes_with_no_id_argument(self):
        """This is F1's failure: a hand-off that ended with no stop and no decision refused --resume with `needs a session id`, so the Lead could not wake it at all (review F1)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))
        pinned = self.pin(session, env, self.PASTED_BG)

        done = self.launch_worker(session, env, "--resume", "--dry-run")

        self.assertEqual(done.returncode, 0, pinned.stderr + done.stdout + done.stderr)
        self.assertIn(f"--resume={self.PASTED_ID} ", done.stdout + done.stderr)

    # ------------------------------------------------------------ a pin refuses a session that is not in the worktree (019 U1 · D4)

    def given_directory_elsewhere(self, worktree, name="elsewhere"):
        """A real directory beside the fixture's worktrees folder, symlinks resolved — a cwd some other Robowright Session or shell could be in."""
        path = worktree.parent.parent / name
        path.mkdir()
        return path.resolve()

    def given_link_to(self, worktree, name="worktree-link"):
        """A symlink to the worktree, as a link the Owner keeps to the repo's `.worktrees/<slug>` is. Returns the link's own, unresolved path."""
        link = worktree.parent.parent / name
        link.symlink_to(worktree.resolve(), target_is_directory=True)
        return link

    def test_launcher__a_pin_whose_session_runs_outside_the_worktree_is_refused_and_changes_nothing(self):
        """A Lead that copies the wrong row of `claude agents --json` would otherwise pin a foreign session silently: --resume would wake it and the cost reader price its transcript as this Robowright Session's (D4 R6)."""
        session, worktree, env, _ = self.given_handed_off()
        elsewhere = self.given_directory_elsewhere(worktree)
        self.given_registered_session(env, self.PASTED_ID, cwd=str(elsewhere))
        run_before = (session / "run.json").read_bytes()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((session / "run.json").read_bytes(), run_before)

    def test_launcher__a_pin_refused_for_a_session_outside_the_worktree_adds_no_ledger_entry(self):
        """A `pinned after hand-off` entry for a refused pin tells the Lead and the Owner the hand-off is finished when nothing was recorded (D4 R6)."""
        session, worktree, env, _ = self.given_handed_off()
        elsewhere = self.given_directory_elsewhere(worktree)
        self.given_registered_session(env, self.PASTED_ID, cwd=str(elsewhere))
        ledger_before = (session / "LEDGER.md").read_bytes()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual((session / "LEDGER.md").read_bytes(), ledger_before, done.stdout + done.stderr)

    def test_launcher__a_pin_refused_for_a_session_outside_the_worktree_names_both_directories(self):
        """The Lead has to see which session it picked and where it should have been to find the right row; a refusal naming neither sends it back to guessing (D4 R6)."""
        session, worktree, env, _ = self.given_handed_off()
        elsewhere = self.given_directory_elsewhere(worktree)
        self.given_registered_session(env, self.PASTED_ID, cwd=str(elsewhere))

        done = self.pin(session, env, self.PASTED_BG)

        output = done.stdout + done.stderr
        self.assertIn(str(elsewhere), output)
        self.assertIn(str(worktree.resolve()), output)

    def test_launcher__a_pin_whose_session_runs_in_a_directory_named_like_the_worktree_is_refused(self):
        """`<worktree>-other` starts with the worktree's path but is another directory; a comparison by string prefix would pin a session from a sibling worktree (D4 R6: the same directory)."""
        session, worktree, env, _ = self.given_handed_off()
        sibling = self.given_directory_elsewhere(worktree, name=f"worktrees/{worktree.name}-other")
        self.given_registered_session(env, self.PASTED_ID, cwd=str(sibling))
        run_before = (session / "run.json").read_bytes()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((session / "run.json").read_bytes(), run_before)

    def test_launcher__a_pin_whose_registry_entry_has_no_cwd_is_refused_and_changes_nothing(self):
        """An entry with no cwd cannot show the session is in the worktree; accepting it reopens the silent foreign pin D4 closes (D4 R7)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID)
        run_before = (session / "run.json").read_bytes()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((session / "run.json").read_bytes(), run_before)

    def test_launcher__a_pin_refused_for_a_registry_entry_with_no_cwd_adds_no_ledger_entry(self):
        """Refused the same way as a foreign cwd: a ledger entry for a pin that did not happen reads as a finished hand-off (D4 R7)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID)
        ledger_before = (session / "LEDGER.md").read_bytes()

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual((session / "LEDGER.md").read_bytes(), ledger_before, done.stdout + done.stderr)

    def test_launcher__a_pin_refused_for_a_registry_entry_with_no_cwd_names_the_worktree(self):
        """With no cwd there is one path to name; the refusal still says where the session should have been, as the foreign-cwd refusal does (D4 R7; assumed Q3)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID)

        done = self.pin(session, env, self.PASTED_BG)

        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(str(worktree.resolve()), done.stdout + done.stderr)

    def test_launcher__a_pin_whose_session_cwd_reaches_the_worktree_through_a_symlink_is_accepted(self):
        """A session started from a link to `<repo>/.worktrees/<slug>` registers the link's path, not the repo's; comparing paths without following links would refuse a correctly pasted session (D4 R8; green at red — owes its kill first)."""
        session, worktree, env, _ = self.given_handed_off()
        link = self.given_link_to(worktree)
        self.given_registered_session(env, self.PASTED_ID, cwd=str(link))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.run_json().get("session_id"), self.PASTED_ID)

    def test_launcher__a_pin_is_accepted_when_run_json_names_the_worktree_through_a_symlink(self):
        """Links are followed on both sides: a run.json whose worktree is the stow link's path still matches a session registered at the real directory (D4 R6, R8; green at red — owes its kill first)."""
        session, worktree, env, _ = self.given_handed_off()
        link = self.given_link_to(worktree)
        run = self.run_json()
        run["worktree"] = str(link)
        (session / "run.json").write_text(json.dumps(run))
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.run_json().get("session_id"), self.PASTED_ID)

    def test_launcher__a_dry_run_pin_of_a_session_outside_the_worktree_reports_the_refusal(self):
        """The dry run is how the Lead checks a pin before taking it; a `would pin` for a session the real pin refuses is a check that approves the wrong row (D4 R9)."""
        session, worktree, env, _ = self.given_handed_off()
        elsewhere = self.given_directory_elsewhere(worktree)
        self.given_registered_session(env, self.PASTED_ID, cwd=str(elsewhere))

        done = self.pin(session, env, self.PASTED_BG, "--dry-run")

        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("would pin", done.stdout + done.stderr)

    def test_launcher__a_dry_run_pin_of_the_session_in_the_worktree_still_says_it_would_pin(self):
        """The check runs before `would pin`, not instead of it: a dry run that refused every session would make the Lead skip the dry run (D4 R9; green at red — owes its kill first)."""
        session, worktree, env, _ = self.given_handed_off()
        self.given_registered_session(env, self.PASTED_ID, cwd=str(worktree.resolve()))

        done = self.pin(session, env, self.PASTED_BG, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("would pin", done.stdout + done.stderr)

    def test_launcher__the_dry_run_model_line_says_when_the_worker_model_overrides_the_robowright_worker(self):
        """A unit's own model can quietly depart from the project's robowright.worker; the dry-run `model:` line is what the Lead reads before --yes, so the departure has to be on it."""
        session, worktree, env = self.given_worker_launchable(unit_model="sonnet", robowright={"worker": "opus"})

        done = self.launch_worker(session, env, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        model_line = re.search(r"(?m)^model:.*$", done.stdout).group(0)
        self.assertIn("sonnet Worker (from unit U1)", model_line)
        self.assertIn("— overrides robowright worker opus", model_line)

    def test_launcher__the_dry_run_model_line_is_silent_when_the_worker_model_is_the_robowright_worker(self):
        """No departure, no note — a note on every launch is one the Lead learns to skip."""
        session, worktree, env = self.given_worker_launchable(unit_model="sonnet", robowright={"worker": "sonnet"})

        done = self.launch_worker(session, env, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("model:     sonnet Worker (from unit U1)", done.stdout)
        self.assertNotIn("overrides robowright worker", done.stdout)

    def test_launcher__the_dry_run_model_line_is_silent_when_run_json_names_no_robowright_worker(self):
        """A run.json with no robowright block has nothing to compare against — a note naming an empty robowright worker would be printed on every legacy session (assumed Q5)."""
        session, worktree, env = self.given_worker_launchable(unit_model="sonnet")

        done = self.launch_worker(session, env, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("model:     sonnet Worker (from unit U1)", done.stdout)
        self.assertNotIn("overrides robowright worker", done.stdout)

    def test_launcher__the_ledger_model_line_records_that_the_worker_model_overrode_the_robowright_worker(self):
        """The ledger's `- model:` line is the only durable record of which model ran a unit, so the override is written there too, not only printed."""
        session, worktree, env = self.given_worker_launchable(unit_model="sonnet", robowright={"worker": "opus"})
        _, env = self.given_stub_claude(env)

        done = self.launch_worker(session, env, "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        model_line = re.search(r"(?m)^- model:.*$", (session / "LEDGER.md").read_text()).group(0)
        self.assertIn("sonnet (from unit U1)", model_line)
        self.assertIn("— overrides robowright worker opus", model_line)

    # ------------------------------------------------------------ the override note fires only on a real override (U2 · F2, D5)

    def given_next_unit_kind(self, session, kind):
        """Rewrites run.json so U1, the next unit, is of `kind`."""
        run = json.loads((session / "run.json").read_text())
        run["units"][0]["kind"] = kind
        (session / "run.json").write_text(json.dumps(run))

    def test_launcher__the_dry_run_model_line_is_silent_when_the_profile_chose_the_worker_model(self):
        """The profile departs from robowright.worker by design for a docs unit, so that is no override — a note on every docs, tests or refactor launch has the Lead confirm overrides that never happened (review F2)."""
        session, worktree, env = self.given_worker_launchable(profile="standard", robowright={"worker": "opus"})
        self.given_next_unit_kind(session, "docs")

        done = self.launch_worker(session, env, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        model_line = re.search(r"(?m)^model:.*$", done.stdout).group(0)
        self.assertIn("sonnet Worker (from profile standard, kind docs)", model_line)
        self.assertNotIn("overrides robowright worker", model_line)

    def test_launcher__the_ledger_model_line_is_silent_when_the_profile_chose_the_worker_model(self):
        """The ledger's `- model:` line is the durable record, so a profile choice written there as an override would misstate every lean unit's history (review F2)."""
        session, worktree, env = self.given_worker_launchable(profile="standard", robowright={"worker": "opus"})
        self.given_next_unit_kind(session, "docs")
        _, env = self.given_stub_claude(env)

        done = self.launch_worker(session, env, "--yes")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        model_line = re.search(r"(?m)^- model:.*$", (session / "LEDGER.md").read_text()).group(0)
        self.assertIn("sonnet (from profile standard, kind docs)", model_line)
        self.assertNotIn("overrides robowright worker", model_line)

    def test_launcher__the_dry_run_model_line_is_silent_when_the_profile_flag_chose_the_worker_model(self):
        """--profile picks a profile, not a model: the model still comes from the profile, so it is no override — reading every flag as one would bring the noise back on the Lead's documented cheap rerun."""
        session, worktree, env = self.given_worker_launchable(robowright={"worker": "opus"})
        self.given_next_unit_kind(session, "docs")

        done = self.launch_worker(session, env, "--dry-run", "--profile", "economy")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        model_line = re.search(r"(?m)^model:.*$", done.stdout).group(0)
        self.assertIn("sonnet Worker (from profile economy, kind docs)", model_line)
        self.assertNotIn("overrides robowright worker", model_line)

    def test_launcher__the_dry_run_model_line_says_when_the_brief_model_overrides_the_robowright_worker(self):
        """A brief-wide model is written by hand and departs from robowright.worker, so it keeps the note even on a docs unit whose profile row picks the same model — the note exists for exactly this departure."""
        session, worktree, env = self.given_worker_launchable(profile="standard", model="sonnet", robowright={"worker": "opus"})
        self.given_next_unit_kind(session, "docs")

        done = self.launch_worker(session, env, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        model_line = re.search(r"(?m)^model:.*$", done.stdout).group(0)
        self.assertIn("sonnet Worker (from brief)", model_line)
        self.assertIn("— overrides robowright worker opus", model_line)

    def test_launcher__the_dry_run_model_line_says_when_the_model_flag_overrides_the_robowright_worker(self):
        """--model is a departure somebody typed, so it keeps the note — silencing every non-unit source would hide the override the Lead is asked to confirm."""
        session, worktree, env = self.given_worker_launchable(robowright={"worker": "opus"})

        done = self.launch_worker(session, env, "--dry-run", "--model", "sonnet")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        model_line = re.search(r"(?m)^model:.*$", done.stdout).group(0)
        self.assertIn("sonnet Worker (from flag)", model_line)
        self.assertIn("— overrides robowright worker opus", model_line)


class LaunchConfigTests(SessionCase):
    """One launcher serves every install, so every fact that differs between them is data it reads.

    `launch.json` beside the machine profile is that data. It is never sourced and the launcher
    ships no defaults for it, so no install can silently inherit another install's paths or
    unit-of-work shape.
    """

    def given_project(self, root):
        project = root / "project"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")
        return project

    def launch(self, env, *flags):
        done = subprocess.run(["bash", str(LAUNCHER), *flags], env=env, capture_output=True, text=True, errors="replace")
        return done.returncode, done.stdout + done.stderr

    def test_launcher__a_missing_launch_json_is_refused_by_the_path_it_looks_at(self):
        """The launcher's own tree carries no machine facts, so an install that has not written its launch.json has no sessions root, no guide directory and no unit shape — a default for any of them would be one install's fact running on the other's machine, silently."""
        root = self.dir / "fixture"
        home, env = self.given_home(root, root / "sessions")
        config = self.write_launch_config(home, None)
        code, out = self.launch(env, "--run-dir", str(root / "nope"), "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn(str(config), out)
        # The help is the one thing that must answer before any of it is configured.
        code, out = self.launch(env, "--help")
        self.assertEqual(code, 0, out)
        self.assertIn("launch.json", out)

    def test_launcher__a_launch_json_key_that_is_absent_or_ill_typed_is_refused_by_name(self):
        """A key read as empty would land an owner brief in the project root, or accept every dir as under the sessions root; the refusal has to name the file and the key, because writing that file is the whole of an install's setup."""
        root = self.dir / "fixture"
        home, env = self.given_home(root, root / "sessions")
        config = home / ".claude/robowright/launch.json"
        good = json.loads(config.read_text())

        def refusal(mutate):
            broken = json.loads(json.dumps(good))
            mutate(broken)
            config.write_text(json.dumps(broken, indent=2) + "\n")
            code, out = self.launch(env, "--run-dir", str(root / "nope"), "--dry-run")
            self.assertEqual(code, 1, out)
            self.assertIn(str(config), out)
            return out

        for key, mutate in (
            ("sessions_root", lambda c: c.pop("sessions_root")),
            # An empty string is what a half-written file leaves, and an empty sessions root
            # turns the under-root fence into a test every absolute path passes.
            ("sessions_root", lambda c: c.update(sessions_root="")),
            ("unit.slug_regex", lambda c: c["unit"].update(slug_regex="")),
            ("review_guide_dir", lambda c: c.update(review_guide_dir=7)),
            ("report_scope", lambda c: c.pop("report_scope")),
            ("unit", lambda c: c.pop("unit")),
            ("unit.slug_regex", lambda c: c["unit"].pop("slug_regex")),
            ("unit.group_regex", lambda c: c["unit"].update(group_regex=None)),
        ):
            self.assertIn(key, refusal(mutate), key)
        # report_scope is a closed set: an unknown value is not a scoping the launcher can honour.
        self.assertIn("report_scope", refusal(lambda c: c.update(report_scope="everything")))

    def test_launcher__a_launch_json_written_to_another_schema_is_refused(self):
        """Another install may write this file too, and a later schema may move a key rather than add one: reading it as schema 1 would be a launcher quietly running on half the facts."""
        root = self.dir / "fixture"
        home, env = self.given_home(root, root / "sessions", schema=2)
        code, out = self.launch(env, "--run-dir", str(root / "nope"), "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn("schema", out)
        self.assertIn("1", out)

    def test_launcher__the_sessions_root_is_the_one_launch_json_names(self):
        """The sessions root is the fence around everything the launcher will start, and it is a different path on every install; an environment variable that moved it would be a seam only the tests use, and a hardcoded default would be this install's path running on another's."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()))))
        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 0, out)

        elsewhere = session.parent.parent / "elsewhere"
        elsewhere.mkdir()
        self.write_launch_config(session.parent.parent / "home", dict(
            json.loads((session.parent.parent / "home/.claude/robowright/launch.json").read_text()),
            sessions_root=str(elsewhere)))
        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn(str(elsewhere), out)
        self.assertIn("sessions_root", out)
        # The root moves in launch.json and nowhere else: the old environment override is gone.
        code, out = self.launch(dict(env, ROBOWRIGHT_SESSIONS_ROOT=str(session.parent)), "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 1, out)

    def test_launcher__the_owner_brief_goes_to_the_directory_launch_json_names(self):
        """An install that publishes a local branch keeps its owner briefs under the project's reviews/, and another install may keep them under prs/: the Explainer is told the path, so the launcher has to read where it is, not assume."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        project = self.given_project(session.parent.parent)
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()), phase="done")))
        (session / "INTAKE.md").write_text("intake\n")
        home = session.parent.parent / "home"
        good = json.loads((home / ".claude/robowright/launch.json").read_text())

        for directory in ("reviews", "prs"):
            self.write_launch_config(home, dict(good, review_guide_dir=directory))
            code, out = self.launch(env, "--explainer", "guide", "--project", str(project), "--run-dir", str(session), "--dry-run")
            self.assertEqual(code, 0, out)
            self.assertIn("guide:     %s/%s/sample-001-x-owner-brief.md" % (project.resolve(), directory), out)

    def test_launcher__the_end_of_stack_review_is_read_from_the_session_s_own_reviews_folder(self):
        """Where a project keeps its owner briefs is an install fact; where a Robowright Session keeps its own reviews is not — `reviews/end-of-stack.md` is the path session-state.py requires before a session may reach done, so an install whose owner briefs live under prs/ would send the review pass, and the owner brief that cites it, to a file nobody writes."""
        session, worktree, env = self.given_launcher_fixture(review_guide_dir="prs")
        self.given_session()
        project = self.given_project(session.parent.parent)
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()), phase="done")))
        (session / "INTAKE.md").write_text("intake\n")

        code, out = self.launch(env, "--planner", "review", "--project", str(project), "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 0, out)
        out = out.replace("\\", "")
        self.assertIn("%s/reviews/end-of-stack.md" % session.resolve(), out)
        self.assertNotIn("%s/prs/end-of-stack.md" % session.resolve(), out)

        code, out = self.launch(env, "--explainer", "guide", "--project", str(project), "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 0, out)
        out = out.replace("\\", "")
        # The owner brief is written into the project's review_guide_dir and read from the session's reviews/.
        self.assertIn("guide:     %s/prs/sample-001-x-owner-brief.md" % project.resolve(), out)
        self.assertIn("INTAKE.md, reviews/,", out)

    def test_launcher__a_group_regex_that_matches_but_captures_nothing_is_refused_by_name(self):
        """launch.json is hand-written per install and every other mistake in it is refused by the key that is wrong; a capture group dropped in an edit would instead read an unset BASH_REMATCH and kill the script with a bash diagnostic that names neither the file nor the key."""
        root = self.dir / "fixture"
        project = self.given_project(root)
        home, env = self.given_home(root, root / "sessions", group_regex="^.+-[0-9]{3}-")
        code, out = self.launch(env, "--planner", "brief", "--project", str(project), "--slug", "sample-003-z", "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn("refusing:", out)
        self.assertIn(str(home / ".claude/robowright/launch.json"), out)
        self.assertIn("group_regex", out)

    def test_launcher__the_tools_it_shells_out_to_are_its_own_siblings(self):
        """The launcher is reached by a bare name that is a link to a link, and the tools it asks are the ones beside it; resolving them through HOME or an environment variable would have a worktree's launcher asking the installed copy's state tool."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()))))
        chain = session.parent.parent / "bin"
        chain.mkdir()
        (chain / "hop.sh").symlink_to(LAUNCHER)
        (chain / "run-launch.sh").symlink_to("hop.sh")
        done = subprocess.run(["bash", str(chain / "run-launch.sh"), "--run-dir", str(session), "--dry-run"],
                              env=env, capture_output=True, text=True, cwd=str(session.parent.parent))
        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, out)
        # The state tool's own verdict line: it was found, run, and asked about this session.
        self.assertIn("launch: ok", out)

    @unittest.skipUnless((SKILLS.parent / "examples/laptop/launch.json").is_file(), "this tree ships no launch.json (each install writes its own)")
    def test_launcher__this_install_s_own_launch_json_is_one_the_launcher_accepts(self):
        """The regexes are matched by bash, and the examples are what the handbooks print; a pattern this install's bash reads differently from whoever wrote it refuses every brief, and nothing else in the tree runs the committed file."""
        config = json.loads((SKILLS.parent / "examples/laptop/launch.json").read_text())
        root = self.dir / "fixture"
        project = self.given_project(root)
        home, env = self.given_home(root, root / "sessions")
        self.write_launch_config(home, dict(config, sessions_root=str(root / "sessions")))

        unit = config["unit"]
        brief = ["--planner", "brief", "--project", str(project), "--slug", unit["slug_example"], "--dry-run"]
        if unit["ticket_regex"] is not None:
            brief += ["--ticket", unit["ticket_example"]]
        code, out = self.launch(env, *brief)
        self.assertEqual(code, 0, out)
        # A trailing hyphen is the near miss every install's slug shape has to refuse.
        near_miss = list(brief)
        near_miss[near_miss.index(unit["slug_example"])] = unit["slug_example"] + "-"
        code, out = self.launch(env, *near_miss)
        self.assertEqual(code, 1, out)
        self.assertIn(unit["slug_example"], out)

    # ------------------------------------------------------------ the launch mode: `paste` or `auto` (U2 · D1–D5)
    # Rows R1–R8 of the unit's behavior table. `given_home` writes `"launch": "auto"`, so every
    # test here names the mode it runs under, or removes the key to get the default.

    PRIOR_LEDGER = "# Ledger\n\n## 2026-09-20 09:00 — launch via run-launch.sh\n- session name: worker-sample-001-x\n"
    HAND_OFF_HEADING = r"(?m)^## \d{4}-\d{2}-\d{2}.* — hand-off via %s$" % re.escape(LAUNCHER.name)
    PASTE_ENTRY_LINE = "\n- launch: paste; nothing started\n"
    RUNNING_ID = "aaaa1111-0000-4000-8000-000000000000"
    PASTED_ID = "cccc3333-0000-4000-8000-000000000000"

    def given_worker_on(self, **config):
        """A legal fresh Worker launch under a launch.json with `config` over the fixture's, one earlier LEDGER.md entry, and a stub `claude` that would start. Returns (session, worktree, env, argv file)."""
        session, worktree, env = self.given_launcher_fixture(**config)
        self.given_session(worktree=str(worktree.resolve()))
        (session / "LEDGER.md").write_text(self.PRIOR_LEDGER)
        record, env = self.given_stub_claude(env)
        return session, worktree, env, record

    def given_worker_running(self, **config):
        """given_worker_on, moved on to implementing, with one transcript of the running session under the scratch HOME for the relaunch's cost record to price. Returns (session, worktree, env, argv file)."""
        session, worktree, env, record = self.given_worker_on(**config)
        self.must("preflight-pass")
        self.must("intake-complete")
        (session / "LEDGER.md").write_text(self.PRIOR_LEDGER)
        transcripts = Path(env["HOME"]) / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(worktree.resolve()))
        transcripts.mkdir(parents=True)
        (transcripts / f"{self.RUNNING_ID}.jsonl").write_text(json.dumps(
            {"timestamp": "2026-09-20T10:00:00Z", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "output_tokens": 5}}}) + "\n")
        return session, worktree, env, record

    def given_brief_on(self, **config):
        """A project folder and a scratch sessions root under a launch.json with `config` over the fixture's, and a stub `claude` that would start. self.dir becomes the brief's session dir, which the launch itself creates. Returns (project, env, argv file)."""
        root = self.dir / "fixture"
        sessions = root / "sessions"
        sessions.mkdir(parents=True)
        project = self.given_project(root)
        _, env = self.given_home(root, sessions, **config)
        self.dir = sessions / "sample-003-z"
        record, env = self.given_stub_claude(env)
        return project, env, record

    def without_launch_key(self, env):
        """The fixture's launch.json with its `launch` key removed — never set to "" (D5)."""
        config = json.loads(self.launch_config(env).read_text())
        del config["launch"]
        self.write_launch_config(Path(env["HOME"]), config)

    def with_launch_value(self, env, value):
        config = json.loads(self.launch_config(env).read_text())
        self.write_launch_config(Path(env["HOME"]), dict(config, launch=value))

    @staticmethod
    def launch_config(env):
        return Path(env["HOME"]) / ".claude/robowright/launch.json"

    @staticmethod
    def run_worker(session, env, *flags):
        return subprocess.run(["bash", str(LAUNCHER), "--run-dir", str(session), *flags], env=env, capture_output=True, text=True, errors="replace")

    @staticmethod
    def run_brief(project, env, *flags):
        return subprocess.run(["bash", str(LAUNCHER), PLANNER_FLAG, "brief", "--slug", "sample-003-z", "--project", str(project), *flags], env=env, capture_output=True, text=True, errors="replace")

    def paste_line(self, stdout):
        found = re.search(r"^paste this yourself:\s*(cd .*)$", stdout, re.M)
        self.assertIsNotNone(found, stdout)
        return found.group(1)

    def assert_handed_off_unstarted(self, done, record, ledger, prior=""):
        """The hand-off (BRIEF Language), under `paste`: exit 0 ending `launch is yours`, `claude` never run, one hand-off entry after `prior` carrying the paste line and `- launch: paste; nothing started`, and no hint."""
        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, out)
        self.assertTrue(done.stdout.rstrip().endswith("launch is yours"), out)
        self.assertEqual(self.recorded_argv(record), [], "claude was invoked under paste")
        text = ledger.read_text()
        self.assertTrue(text.startswith(prior), text)
        self.assertEqual(text.count("hand-off via"), 1, text)
        self.assertRegex(text, self.HAND_OFF_HEADING)
        self.assertEqual(text.count(self.PASTE_ENTRY_LINE), 1, text)
        self.assertIn("\n- paste: %s\n" % self.paste_line(done.stdout), text)
        self.assertNotIn("EPERM", text)
        self.assertNotIn("hint:", out)

    def test_launcher__a_launch_json_with_no_launch_key_hands_a_worker_launch_off_unstarted(self):
        """Absent means `paste`: an install that never chose a mode must not have its launcher start sessions on its own — the one mode that is safe in every shell is the one a missing key gets (R1.1, assumed Q4)."""
        session, worktree, env, record = self.given_worker_on()
        self.without_launch_key(env)

        done = self.run_worker(session, env, "--yes")

        self.assert_handed_off_unstarted(done, record, session / "LEDGER.md", self.PRIOR_LEDGER)

    def test_launcher__paste_hands_a_worker_launch_off_with_the_marker_written_and_run_json_untouched(self):
        """`paste` is the EPERM hand-off with the claude call skipped: the marker is written so the pasted session finds its hooks, and run.json is left as a started session would begin from — a hand-off before the marker leaves the pasted session with no stop gate (R2.1, assumed Q4)."""
        session, worktree, env, record = self.given_worker_on(launch="paste")
        run_before = (session / "run.json").read_bytes()

        done = self.run_worker(session, env, "--yes")

        self.assert_handed_off_unstarted(done, record, session / "LEDGER.md", self.PRIOR_LEDGER)
        self.assertEqual((worktree / ".claude/autonomous-run").read_text(), f"{session.resolve()}\n")
        self.assertEqual((session / "run.json").read_bytes(), run_before)
        self.assertFalse((session / "events.jsonl").exists())

    def test_launcher__paste_hands_a_rotation_off_after_recording_the_previous_session_s_cost(self):
        """A rotation is the last moment anyone looks at what the replaced session cost, and pasting it does not change that; beyond the cost block the hand-off leaves run.json and events.jsonl as they were, so the pasted session begins from the stored state (R2.2, assumed Q4, Q6)."""
        session, worktree, env, record = self.given_worker_running(launch="paste")
        self.given_unit_closed("U1")
        self.must("request-rotate")
        run_before = self.run_json()
        run_before.pop("cost", None)
        events_before = (session / "events.jsonl").read_bytes()

        done = self.run_worker(session, env, "--rotate", "--yes")

        self.assert_handed_off_unstarted(done, record, session / "LEDGER.md", self.PRIOR_LEDGER)
        self.assertEqual((worktree / ".claude/autonomous-run").read_text(), f"{session.resolve()}\n")
        run_after = self.run_json()
        cost = run_after.pop("cost", None)
        self.assertEqual(run_after, run_before)
        self.assertIsNotNone(cost, "the rotation's cost record did not run under paste")
        self.assertEqual(cost["requests"], 1)
        self.assertEqual((session / "events.jsonl").read_bytes(), events_before)

    def test_launcher__paste_hands_a_resume_off_after_recording_the_previous_session_s_cost(self):
        """A resume under `paste` records the stopped session's cost and writes the marker exactly as a started resume does, then hands the resume command off; run.json beyond the cost block and events.jsonl are untouched (R2.3, assumed Q4, Q6)."""
        session, worktree, env, record = self.given_worker_running(launch="paste")
        run_before = self.run_json()
        run_before.pop("cost", None)
        events_before = (session / "events.jsonl").read_bytes()

        done = self.run_worker(session, env, "--resume", self.RUNNING_ID, "--yes")

        self.assert_handed_off_unstarted(done, record, session / "LEDGER.md", self.PRIOR_LEDGER)
        self.assertEqual((worktree / ".claude/autonomous-run").read_text(), f"{session.resolve()}\n")
        run_after = self.run_json()
        cost = run_after.pop("cost", None)
        self.assertEqual(run_after, run_before)
        self.assertIsNotNone(cost, "the resume's cost record did not run under paste")
        self.assertEqual(cost["requests"], 1)
        self.assertEqual((session / "events.jsonl").read_bytes(), events_before)

    def test_launcher__paste_hands_a_planner_launch_off_into_its_own_ledger(self):
        """The document-only site hands off through the same function as the Worker site, into the ledger its started launch would write and from the project folder it would start in — two sites that drift give the Lead two readings of one mode (R2.4, assumed Q4)."""
        project, env, record = self.given_brief_on(launch="paste")

        done = self.run_brief(project, env, "--yes")

        self.assert_handed_off_unstarted(done, record, self.dir / "LEDGER.md")
        self.assertTrue(self.paste_line(done.stdout).startswith(f'cd {project.resolve()} && [ "$(pwd -P)" = {project.resolve()} ] && env -u CLAUDECODE '), done.stdout)

    def test_launcher__a_launch_value_other_than_paste_or_auto_is_refused_by_name_before_anything_is_written(self):
        """launch.json is hand-written per install, and a mode the launcher cannot name is one it must not guess: `Auto` read as `paste` hands off what the Owner meant to start, `yes` read as `auto` starts what they meant to paste. The refusal names the file, the key, both values and what it found, and comes before the marker, the ledger or the stub (R6.1, assumed Q3)."""
        session, worktree, env, record = self.given_worker_on()
        run_before = (session / "run.json").read_bytes()
        for value, found in ((2, "2"), ("", ""), ("Auto", "Auto"), ("yes", "yes")):
            with self.subTest(launch=value):
                self.with_launch_value(env, value)

                done = self.run_worker(session, env, "--yes")

                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn(f"refusing: {self.launch_config(env)}: 'launch' must be paste or auto (got '{found}')\n", done.stderr)
                self.assertEqual(self.recorded_argv(record), [])
                self.assertFalse((worktree / ".claude/autonomous-run").exists())
                self.assertEqual((session / "LEDGER.md").read_text(), self.PRIOR_LEDGER)
                self.assertEqual((session / "run.json").read_bytes(), run_before)

    def test_launcher__a_bad_launch_value_refuses_a_document_only_launch_before_its_session_dir_is_made(self):
        """A brief's session dir is made by the launch itself, so a refusal that came after the `mkdir` would leave an empty session dir the next brief for that slug trips over (R6.2, assumed Q3)."""
        project, env, record = self.given_brief_on(launch="yes")

        done = self.run_brief(project, env, "--yes")

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(f"refusing: {self.launch_config(env)}: 'launch' must be paste or auto (got 'yes')\n", done.stderr)
        self.assertEqual(self.recorded_argv(record), [])
        self.assertFalse(self.dir.exists(), "the refused brief made its session dir")

    def test_launcher__a_null_launch_value_is_refused_rather_than_read_as_absent(self):
        """Only a missing key means `paste`; a `null` is a value someone wrote, and reading it as absent is the same slip that would read a half-written file as a choice (R6.3, assumed Q2)."""
        session, worktree, env, record = self.given_worker_on(launch=None)

        done = self.run_worker(session, env, "--yes")

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(f"refusing: {self.launch_config(env)}: 'launch' must be paste or auto (got 'null')\n", done.stderr)
        self.assertEqual(self.recorded_argv(record), [])
        self.assertFalse((worktree / ".claude/autonomous-run").exists())

    def test_launcher__a_bad_launch_value_refuses_a_pin_too(self):
        """The mode check sits beside report_scope's and refuses every invocation of a misconfigured install; a pin that slipped past it would be the one command still writing run.json from a launch.json the launcher calls broken (R6.4, assumed Q3, Q7)."""
        session, worktree, env, _ = self.given_worker_on(launch="Auto")
        (Path(env["HOME"]) / ".claude/sessions" / f"{self.PASTED_ID[:8]}.json").write_text(json.dumps({"sessionId": self.PASTED_ID, "cwd": str(worktree.resolve())}))
        run_before = (session / "run.json").read_bytes()

        done = self.run_worker(session, env, "--pin", self.PASTED_ID[:8])

        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(f"refusing: {self.launch_config(env)}: 'launch' must be paste or auto (got 'Auto')\n", done.stderr)
        self.assertEqual((session / "run.json").read_bytes(), run_before)

    def test_launcher__the_worker_plan_names_the_launch_mode_and_where_it_came_from(self):
        """The Lead reads the plan before every --yes, and whether that --yes starts a session or prints a line to paste is the difference between waiting on a Worker and owing the Owner a paste; a default has to say it is one (R7.1, assumed Q1)."""
        session, worktree, env, _ = self.given_worker_on()
        for launch, line in (("auto", "launch:    auto (launch.json)"),
                             ("paste", "launch:    paste (launch.json)"),
                             (None, "launch:    paste (default: launch.json names no launch key)")):
            with self.subTest(launch=launch):
                if launch is None:
                    self.without_launch_key(env)
                else:
                    self.with_launch_value(env, launch)

                done = self.run_worker(session, env, "--dry-run")

                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertRegex(done.stdout, r"(?m)^%s$" % re.escape(line))

    def test_launcher__the_document_only_plan_names_the_launch_mode_and_where_it_came_from(self):
        """A Planner or Explainer launch is handed off or started by the same mode, so its plan carries the same line (R7.2, assumed Q1)."""
        project, env, _ = self.given_brief_on()
        for launch, line in (("auto", "launch:    auto (launch.json)"),
                             ("paste", "launch:    paste (launch.json)"),
                             (None, "launch:    paste (default: launch.json names no launch key)")):
            with self.subTest(launch=launch):
                if launch is None:
                    self.without_launch_key(env)
                else:
                    self.with_launch_value(env, launch)

                done = self.run_brief(project, env, "--dry-run")

                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertRegex(done.stdout, r"(?m)^%s$" % re.escape(line))

    def test_launcher__a_pin_under_paste_records_the_pasted_session(self):
        """`paste` is the mode whose every launch ends in a paste, so --pin is how each of its sessions reaches run.json; a pin gated on the mode would leave --resume and the cost reader without an id (R8.1)."""
        session, worktree, env, _ = self.given_worker_on(launch="paste")
        (Path(env["HOME"]) / ".claude/sessions" / f"{self.PASTED_ID[:8]}.json").write_text(json.dumps({"sessionId": self.PASTED_ID, "cwd": str(worktree.resolve())}))

        done = self.run_worker(session, env, "--pin", self.PASTED_ID[:8])

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.run_json().get("session_id"), self.PASTED_ID)
        self.assertRegex((session / "LEDGER.md").read_text(), r"(?m)^## .*pinned after hand-off.*$")

class UnitOfWorkTests(SessionCase):
    """The shape of a unit of work — a slug here, a tracker key somewhere else — is the other half
    of what differs between installs, so `launch.json`'s `unit` block drives the flags, the
    directory name, and the id every session name and guide path is built from."""

    def given_project(self, root):
        project = root / "project"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")
        return project

    def launch(self, env, *flags):
        done = subprocess.run(["bash", str(LAUNCHER), *flags], env=env, capture_output=True, text=True, errors="replace")
        return done.returncode, done.stdout + done.stderr

    def test_launcher__a_brief_s_slug_must_match_the_shape_launch_json_names(self):
        """The slug becomes a directory under the shared sessions root and the id every later session name is built from; the shape is a per-install convention, and the refusal has to show the install's own example rather than one the launcher carries."""
        root = self.dir / "fixture"
        project = self.given_project(root)
        _, env = self.given_home(root, root / "sessions", slug_regex="^x-[0-9]{2}$", slug_example="x-42")

        def brief(slug):
            return self.launch(env, "--planner", "brief", "--project", str(project), "--slug", slug, "--dry-run")

        self.assertEqual(brief("x-42")[0], 0, brief("x-42")[1])
        code, out = brief("sample-012-note-autosave")
        self.assertEqual(code, 1, out)
        self.assertIn("x-42", out)
        # The character class is the install-independent half: a slug is a directory name.
        code, out = brief("x/42")
        self.assertEqual(code, 1, out)
        self.assertIn("lowercase letters, digits, and hyphens", out)

    def test_launcher__a_ticket_is_refused_where_this_install_names_no_ticket_shape(self):
        """--ticket is one flag every install parses, and on an install with no tracker it can only be a caller repeating a handbook written for another install: swallowing it would write the brief into a directory nobody asked for."""
        root = self.dir / "fixture"
        project = self.given_project(root)
        home, env = self.given_home(root, root / "sessions")
        code, out = self.launch(env, "--planner", "brief", "--project", str(project), "--slug", "sample-003-z", "--ticket", "ABC-1234", "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn(str(home / ".claude/robowright/launch.json"), out)
        self.assertIn("ticket_regex", out)

    def test_launcher__where_launch_json_names_a_ticket_shape_a_brief_is_built_from_it(self):
        """An install with a tracker names its unit of work by key: the key is required, shape-checked, and it — not the slug — is the directory prefix and the id the Planner is briefed for."""
        root = self.dir / "fixture"
        project = self.given_project(root)
        sessions = root / "sessions"
        own, other = sessions / "ABC-1-old", sessions / "XYZ-2-other"
        for age_seconds, made in ((200, own), (100, other)):
            made.mkdir(parents=True)
            (made / "INTAKE.md").write_text("intake\n")
            stamp = time.time() - age_seconds
            os.utime(made / "INTAKE.md", (stamp, stamp))
        _, env = self.given_home(root, sessions, ticket_regex="^[A-Z][A-Z0-9]*-[0-9]+$", ticket_example="ABC-1234",
                                 slug_regex="^[a-z0-9]+(-[a-z0-9]+)*$", slug_example="review-feedback",
                                 group_regex="^([A-Z][A-Z0-9]*)-[0-9]+(-[a-z0-9]+)+$")

        def brief(*flags):
            return self.launch(env, "--planner", "brief", "--project", str(project), "--slug", "review-feedback", "--dry-run", *flags)

        code, out = brief()
        self.assertEqual(code, 1, out)
        self.assertIn("ABC-1234", out)
        code, out = brief("--ticket", "nope-1")
        self.assertEqual(code, 1, out)
        self.assertIn("ABC-1234", out)
        code, out = brief("--ticket", "ABC-9")
        self.assertEqual(code, 0, out)
        self.assertIn("%s/ABC-9-review-feedback" % sessions.resolve(), out)
        self.assertIn("--name %s-abc-9 " % PLANNER_ROLE, out)
        self.assertIn("brief ABC-9:", out.replace("\\", ""))
        # The group a brief inherits from is the capture launch.json's group_regex makes, not a shape built in here.
        self.assertIn("intake:    %s/INTAKE.md" % own.resolve(), out)
        self.assertNotIn(str(other.resolve()), out)

    def test_launcher__the_unit_id_is_the_ticket_run_json_carries(self):
        """Every install's templates write `ticket`, and the guide path, the session name and the plan line are built from it; where the install names a ticket shape, a brief that carries none is refused rather than quietly named after its directory."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        project = self.given_project(session.parent.parent)

        def given(**fields):
            (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()), **fields)))

        given(ticket="sample-001-renamed")
        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("(sample-001-renamed, phase", out)
        self.assertIn("--name worker-opus-sample-001-renamed ", out.replace("\\", ""))
        # No ticket, and no ticket shape on this install: the directory name is the id.
        given(ticket=None)
        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("(sample-001-x, phase", out)
        # An install whose units are tracker keys has no directory-name fallback to make.
        home = session.parent.parent / "home"
        self.write_launch_config(home, dict(json.loads((home / ".claude/robowright/launch.json").read_text()),
                                            unit=dict(json.loads((home / ".claude/robowright/launch.json").read_text())["unit"],
                                                      ticket_regex="^[A-Z][A-Z0-9]*-[0-9]+$", ticket_example="ABC-1234")))
        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn("no ticket", out)

    def test_launcher__brief_is_shorthand_for_the_planner_s_brief_mode(self):
        """The shorthand is what the handbooks print for the commonest launch there is, and it is the one flag a caller written for another install would otherwise be refused on."""
        root = self.dir / "fixture"
        project = self.given_project(root)
        _, env = self.given_home(root, root / "sessions")
        code, out = self.launch(env, "--brief", "--project", str(project), "--slug", "sample-003-z", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("action:    launch brief-only Planner", out)

    def test_launcher__how_far_the_report_reads_is_the_scoping_launch_json_names(self):
        """The Explainer is told which sessions the report is written from; an install may keep one project's sessions under the shared root or everything under it, and inheriting either by omission gives a report written from the wrong set."""
        root = self.dir / "fixture"
        project = self.given_project(root)
        sessions = root / "sessions"
        sessions.mkdir(parents=True)
        home, env = self.given_home(root, sessions)

        def report():
            code, out = self.launch(env, "--explainer", "report", "--project", str(project), "--dry-run")
            self.assertEqual(code, 0, out)
            return out.replace("\\", "")

        self.assertIn("%s/project-" % sessions.resolve(), report())
        self.write_launch_config(home, dict(json.loads((home / ".claude/robowright/launch.json").read_text()), report_scope="all-roots"))
        out = report()
        self.assertNotIn("%s/project-" % sessions.resolve(), out)
        self.assertIn(str(sessions.resolve()), out)

    def test_launcher__a_finished_session_is_refused_before_the_worktree_is_looked_at(self):
        """An accepted session's worktree is torn down, so the first refusal a caller sees would be `worktree does not exist` — which reads as a broken brief rather than as work that is already finished."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree / "gone"), phase="done")))
        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn("phase is done", out)
        self.assertNotIn("does not exist", out)

    def test_launcher__a_launch_whose_worktree_is_missing_names_the_path_run_json_gives(self):
        """The --run-dir refusal printed `worktree  does not exist` — the failed resolve had already emptied the path, so the caller could not tell which worktree was gone (review F12, D10 R1)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        missing = str(worktree.parent / "wt-torn-down")
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=missing)))
        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn(missing, out)

    # ------------------------------------------------------------ refusals name the fix (026 U3 · D4)

    def test_launcher__a_launch_whose_worktree_is_missing_prints_the_worktree_add_command_run_json_fills(self):
        """The dry run printed only `worktree <path> does not exist`, and a Planner brief had left the command to the Lead (023 LEDGER); the command filled from run.json is the fix (026 D4 R1; wording assumed Q1)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        missing = str(worktree.parent / "wt-torn-down")
        run = dict(self.run_json(), worktree=missing)
        run["units"][0]["branch"] = "robowright/sample-001-first-unit"
        run["units"][1]["branch"] = "robowright/sample-001-second-unit"
        (session / "run.json").write_text(json.dumps(run))

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add -b robowright/sample-001-first-unit {missing} <base>"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)

    def test_launcher__a_launch_whose_worktree_is_missing_and_whose_units_is_not_a_list_keeps_the_worktree_refusal(self):
        """Reading `units[0].branch` for the command exited 5 on a raw jq error when `units` was a string, where the launcher had refused with `worktree <path> does not exist` (026 D4 R3; end-of-stack F2)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        missing = str(worktree.parent / "wt-torn-down")
        self.given_hand_edit(lambda run: run.update(worktree=missing, units="x"))

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        self.assertIn(f"refusing: worktree {missing} does not exist", out)

    def test_launcher__a_launch_of_a_accepted_session_whose_worktree_is_gone_prints_no_worktree_add_command(self):
        """An accepted session's worktree is torn down on purpose; its refusal has to stay first, or the caller is told to recreate a worktree for finished work (026 hotspot on run-launch.sh:721)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        run = dict(self.run_json(), worktree=str(worktree.parent / "wt-torn-down"), phase="done")
        run["units"][0]["branch"] = "robowright/sample-001-first-unit"
        (session / "run.json").write_text(json.dumps(run))

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        self.assertIn("run.json phase is done", out)
        self.assertNotIn("git worktree add", out)

    # ------------------------------------------------------------ the launch refusal's hint follows the stored phase (027 U2 · D2)

    def given_worktree_torn_down(self, worktree, branch):
        """run.json as the Given left it, with its worktree moved to a path that does not exist and units[0].branch set to `branch` (left out when None). Returns the missing path."""
        missing = str(worktree.parent / "wt-torn-down")

        def tear_down(run):
            run["worktree"] = missing
            if branch is not None:
                run["units"][0]["branch"] = branch

        self.given_hand_edit(tear_down)
        return missing

    def test_launcher__a_launch_whose_run_json_has_no_phase_and_whose_worktree_is_missing_prints_the_new_branch_command(self):
        """A run.json with no phase is a briefed session, as the launcher reads it everywhere else; reading the absent phase as some later one would drop the `-b` a new branch needs (027 D2 R1)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        self.given_hand_edit(lambda run: run.pop("phase"))
        missing = self.given_worktree_torn_down(worktree, branch="robowright/sample-001-first-unit")

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add -b robowright/sample-001-first-unit {missing} <base>"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)

    def test_launcher__a_launch_of_a_parked_session_whose_worktree_is_gone_prints_no_command_and_says_it_is_finished(self):
        """Only `done` is refused before the worktree check, so a parked session reached the hint and was told to recreate a worktree torn down with finished work (027 D2 R2; finished line assumed in brief)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        self.given_hand_edit(lambda run: run.update(phase="parked"))
        missing = self.given_worktree_torn_down(worktree, branch="robowright/sample-001-first-unit")

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        finished = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            "run.json phase is parked: the session is finished, so its worktree is not recreated"), out)
        self.assertIsNotNone(finished, out)
        self.assertGreater(finished.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add", out)

    def test_launcher__a_launch_of_an_implementing_session_whose_worktree_is_missing_prints_the_command_that_reuses_its_branch(self):
        """Past briefed the unit's branch already exists, so the `-b` command the refusal printed fails as printed (027 D2 R3)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing()
        missing = self.given_worktree_torn_down(worktree, branch="robowright/sample-001-first-unit")

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} robowright/sample-001-first-unit"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add -b", out)
        self.assertNotIn("<base>", out)

    def test_launcher__a_launch_in_intake_whose_worktree_is_missing_prints_the_command_that_reuses_its_branch(self):
        """Intake runs after preflight has made the branch, so reading it as briefed like preflight would print a `-b` command that fails as printed (027 D2 R3)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        self.must("preflight-pass")
        missing = self.given_worktree_torn_down(worktree, branch="robowright/sample-001-first-unit")

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} robowright/sample-001-first-unit"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add -b", out)
        self.assertNotIn("<base>", out)

    def test_launcher__a_resume_of_a_stopped_session_whose_worktree_is_missing_prints_the_command_that_reuses_its_branch(self):
        """The refusal fires before --resume is read, and a stopped session's branch already exists, so the `-b` command it printed fails as printed (027 D2 R3)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing()
        self.must("unit-start", "--unit", "U1")
        self.given_stopped("budget")
        missing = self.given_worktree_torn_down(worktree, branch="robowright/sample-001-first-unit")

        code, out = self.launch(env, "--run-dir", str(session), "--resume", "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} robowright/sample-001-first-unit"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add -b", out)
        self.assertNotIn("<base>", out)

    def test_launcher__a_rotate_of_a_session_awaiting_rotation_whose_worktree_is_missing_prints_the_command_that_reuses_its_branch(self):
        """A rotation is pending with the phase still implement, and the branch holds the closed unit's work, so the `-b` command the refusal printed fails as printed (027 D2 R3, hotspot on the pending rotation)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing(worktree=str(worktree.resolve()))
        self.given_unit_closed("U1")
        self.must("request-rotate")
        missing = self.given_worktree_torn_down(worktree, branch="robowright/sample-001-first-unit")

        code, out = self.launch(env, "--run-dir", str(session), "--rotate", "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} robowright/sample-001-first-unit"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)
        self.assertNotIn("git worktree add -b", out)
        self.assertNotIn("<base>", out)

    def test_launcher__a_launch_past_briefed_whose_unit_has_no_branch_prints_the_reuse_command_with_a_branch_placeholder(self):
        """With no units[0].branch the reuse command would end at the worktree path, and git would read that as a new branch named for the path's last component (027 D2 R4)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing()
        missing = self.given_worktree_torn_down(worktree, branch=None)

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} <branch>"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)

    def test_launcher__a_briefed_launch_whose_unit_has_no_branch_prints_the_new_branch_command_with_a_branch_placeholder(self):
        """With no units[0].branch the `-b` flag would take the worktree path as its branch name, and the command runs wrong instead of failing (027 D2 R4)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        missing = self.given_worktree_torn_down(worktree, branch=None)

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add -b <branch> {missing} <base>"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)

    def test_launcher__a_launch_past_briefed_whose_units_is_not_a_list_keeps_the_worktree_refusal_and_prints_the_reuse_command(self):
        """The phase split adds a second read of run.json beside units[0].branch; a malformed units must still end in the worktree refusal, not a raw jq exit 5 (027 D2 R5 with R4; placeholder assumed Q5)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing()
        missing = str(worktree.parent / "wt-torn-down")
        self.given_hand_edit(lambda run: run.update(worktree=missing, units="x"))

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        refusal = f"refusing: worktree {missing} does not exist"
        self.assertIn(refusal, out)
        command = re.search(r"(?m)^\s*%s\s*$" % re.escape(
            f"create it per the project hook → Worktree, e.g.: git worktree add {missing} <branch>"), out)
        self.assertIsNotNone(command, out)
        self.assertGreater(command.start(), out.index(refusal), out)

    def test_launcher__a_plain_launch_of_a_session_awaiting_rotation_is_refused_naming_rotate(self):
        """The refusal said only that launch is illegal from awaiting-rotation, and the flag that starts the waiting session was left for the Lead to find (026 D4 R2; wording assumed Q1)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing(worktree=str(worktree.resolve()))
        self.given_unit_closed("U1")
        self.must("request-rotate")

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        self.assertIn("refused: launch: the session is awaiting-rotation", out)
        self.assertIn("launch it with --rotate", out)

    def test_launcher__a_plain_launch_of_an_invalid_session_awaiting_rotation_is_refused_without_naming_rotate(self):
        """The hint was keyed on the status line's awaiting-rotation, not on why check-op refused, so an invalid stored state was sent to a --rotate launch that check-op refuses in turn (026 D4 R3; U3 gate F1)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing(worktree=str(worktree.resolve()))
        self.given_unit_closed("U1")
        self.must("request-rotate")
        self.given_hand_edit(lambda run: run["units"][1].update(status="building"))

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        self.assertIn("refused: launch: the stored state is invalid: rotating-mid-unit", out)
        self.assertNotIn("--rotate", out)

    def test_launcher__a_plain_launch_of_a_stopped_session_is_refused_without_naming_rotate(self):
        """A stopped session is resumed or rebriefed, never rotated; a refusal naming --rotate there sends the Lead to a launch that is refused in turn (026 D4 R3)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing(worktree=str(worktree.resolve()))
        self.given_stopped()

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        self.assertIn("refused: launch: the session is stopped; launch is legal from briefed, intake", out)
        self.assertNotIn("--rotate", out)

    def test_launcher__a_plain_launch_of_a_accepted_session_is_refused_without_naming_rotate(self):
        """An accepted session has nothing left to start; a refusal naming --rotate there invites a launch over finished work (026 D4 R3)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session(worktree=str(worktree.resolve()), phase="done")

        code, out = self.launch(env, "--run-dir", str(session), "--dry-run")

        self.assertEqual(code, 1, out)
        self.assertIn("run.json phase is done", out)
        self.assertNotIn("--rotate", out)

    def test_launcher__a_resume_of_a_session_awaiting_rotation_is_refused_as_before(self):
        """The --rotate hint belongs to a plain launch only; every other refusal keeps its text, so a resume refusal gains no hint (026 D4 R3; assumed Q3)."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_implementing(worktree=str(worktree.resolve()), session_id="00000000-0000-0000-0000-000000000000")
        self.given_unit_closed("U1")
        self.must("request-rotate")

        code, out = self.launch(env, "--run-dir", str(session), "--resume", "--dry-run")

        self.assertEqual(code, 1, out)
        self.assertIn("refused: resume: the session is awaiting-rotation", out)
        self.assertNotIn("launch it with --rotate", out)


class LauncherWordingTests(SessionCase):
    """The role words, flags and script name the launcher prints are the ones it takes and is.

    A refusal names the role flag the caller typed and a dry run names the session under that
    role; a directory not given is asked for as `--run-dir`, with `--session-dir` still accepted;
    the ledger line and the printed next command name the launcher's own file. The role words
    and the launcher's name come from the role and flag constants and `LAUNCHER`, never written
    out twice; the directory flags are pinned as written, because the handbooks print them.
    """

    def given_project(self, root):
        project = root / "project"
        project.mkdir(parents=True)
        (project / "PROJECT.md").write_text("# plan\n")
        return project

    def launch(self, env, *flags):
        done = subprocess.run(["bash", str(LAUNCHER), *flags], env=env, capture_output=True, text=True, errors="replace")
        return done.returncode, done.stdout + done.stderr

    def test_launcher__the_role_word_it_prints_is_the_role_flag_it_takes(self):
        """A refusal naming a flag this launcher does not accept, or a session name under a prefix the roster does not know, is worse than no message at all: both send the reader to a command that cannot work."""
        root = self.dir / "fixture"
        project = self.given_project(root)
        _, env = self.given_home(root, root / "sessions")
        brief = (PLANNER_FLAG, "brief", "--slug", "sample-003-z", "--project", str(project))

        code, out = self.launch(env, *brief, "--resume")
        self.assertEqual(code, 1, out)
        self.assertIn("%s does not combine with --resume" % PLANNER_FLAG, out)
        code, out = self.launch(env, EXPLAINER_FLAG, "report")
        self.assertEqual(code, 1, out)
        self.assertIn("%s needs --project" % EXPLAINER_FLAG, out)

        code, out = self.launch(env, *brief, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("%-11sbrief" % (PLANNER_ROLE + ":"), out)
        self.assertIn("--name %s-sample-003-z " % PLANNER_ROLE, out)
        code, out = self.launch(env, EXPLAINER_FLAG, "report", "--project", str(project), "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("%-11sreport" % (EXPLAINER_ROLE + ":"), out)
        self.assertIn("--name %s-project " % EXPLAINER_ROLE, out)

    def test_launcher__its_messages_echo_the_directory_flag_it_asks_for(self):
        """The handbooks print one spelling and the launcher used to answer in another: a refusal naming a flag the caller did not type sends them to the wrong line of the wrong document. The older spelling stays accepted, because written briefs still carry it."""
        session, worktree, env = self.given_launcher_fixture()
        self.given_session()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()))))
        project = self.given_project(session.parent.parent)

        code, out = self.launch(env, "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn("--run-dir is required", out)
        code, out = self.launch(env, EXPLAINER_FLAG, "guide", "--project", str(project), "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn("needs --run-dir", out)
        code, out = self.launch(env, "--run-dir", str(session / "gone"), "--dry-run")
        self.assertEqual(code, 1, out)
        self.assertIn("Robowright Session dir does not exist", out)
        self.assertEqual(self.launch(env, "--session-dir", str(session), "--dry-run")[0], 0)

    def test_launcher__the_lines_it_prints_name_the_launcher_itself(self):
        """The Lead's next command is a line this script prints, and the ledger records which script started a session; a name written in by hand is wrong the moment the file is renamed, and wrong on another install the moment the two names differ."""
        session, worktree, env = self.given_launcher_fixture()
        record, env = self.given_stub_claude(env)
        self.given_session()
        (session / "run.json").write_text(json.dumps(dict(self.run_json(), worktree=str(worktree.resolve()))))
        done = subprocess.run(["bash", str(LAUNCHER), "--run-dir", str(session), "--yes"], env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("via %s" % LAUNCHER.name, (session / "LEDGER.md").read_text())
        project = self.given_project(session.parent.parent)
        code, out = self.launch(env, PLANNER_FLAG, "brief", "--project", str(project), "--slug", "sample-003-z", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("print the %s --dry-run line" % LAUNCHER.name, out.replace("\\", ""))


class AgentPinTests(unittest.TestCase):
    """The launcher's `--settings` carries a bare `effortLevel` that reaches every subagent, so an agent's own pin is the only thing between it and the session's level."""

    @unittest.skipUnless(AGENTS.is_dir(), "this tree ships no agent definitions")
    def test_agents__an_opus_agent_pins_the_effort_it_needs(self):
        """A Worker on the economy profile runs at low effort and hands that level to every subagent that pins none: the Opus agents exist because the judgment is worth Opus, and one at low effort costs Opus money for a cheap answer while nothing in the launcher output or the ledger says it was downgraded."""
        unpinned = []
        for agent in sorted(AGENTS.glob("*.md")):
            front = agent.read_text().split("---")[1] if agent.read_text().startswith("---") else ""
            if re.search(r"^model:\s*opus\s*$", front, re.M) and not re.search(r"^effort:\s*\w+\s*$", front, re.M):
                unpinned.append(agent.name)
        self.assertEqual(unpinned, [], "these Opus agents follow the session's effort instead of their own")


class PublishStrategyTests(SessionCase):
    """run.json.publish names how the session publishes; the tool is the one place a misspelt strategy is caught before publishing reads it."""

    # intake, implement and stopped span pre-, mid- and post-unit phases; the check must hold in all three.
    PHASES = ("intake", "implement", "stopped")
    ABSENT = object()

    def given_phase(self, phase):
        if phase == "intake":
            self.given_session()
            self.must("preflight-pass")
        elif phase == "implement":
            self.given_implementing()
        else:
            self.given_implementing()
            self.given_stopped()

    def given_publish(self, value):
        if value is self.ABSENT:
            self.given_hand_edit(lambda run: run.pop("publish", None))
        else:
            self.given_hand_edit(lambda run: run.update(publish=value))

    def assert_legal(self, value):
        for phase in self.PHASES:
            with self.subTest(publish=value, phase=phase):
                self.given_phase(phase)
                self.given_publish(value)
                self.assertEqual(self.state()["problems"], [])
                self.assertEqual(self.tool("check")[0], 0)

    def test_check__each_publish_strategy_name_is_legal(self):
        """draft-pr, local-branch, push-to-branch and pr-plus-deploy pass check — a session naming its strategy would be refused every event."""
        for name in ("draft-pr", "local-branch", "push-to-branch", "pr-plus-deploy"):
            self.assert_legal(name)

    def test_check__publish_false_is_legal(self):
        """false publishes nothing and passes check — the brief template's no-publishing value would be refused every event."""
        self.assert_legal(False)

    def test_check__an_unset_publish_or_the_record_publishing_wrote_is_legal(self):
        """null, a missing key, and the dict publishing leaves behind pass check — the template's null and every published session would be illegal."""
        for value in (None, self.ABSENT, {"branch": "robowright/sample-012-note-autosave", "pr": "https://github.com/example/app/pull/12"}):
            self.assert_legal(value)

    def test_check__any_other_publish_value_is_bad_publish_and_names_the_value(self):
        """A string that is not one of the four, a number, or the retired `true`, fails check as bad-publish alone, quoting it — publishing would read a misspelt strategy as none, or a 1 or a true as some strategy nobody named."""
        for value in ("true", "draft_pr", "local branch", "Draft-PR", "", 1, 0, True):
            for phase in self.PHASES:
                with self.subTest(publish=value, phase=phase):
                    self.given_phase(phase)
                    self.given_publish(value)
                    found = self.state()["problems"]
                    self.assertEqual([p.split(":")[0] for p in found], ["bad-publish"])
                    self.assertIn(repr(value), found[0].split(":", 1)[1])
                    self.assertEqual(self.tool("check")[0], 1)

    def test_table__bad_publish_is_in_the_glossary_and_the_table_still_matches_the_code(self):
        """bad-publish has its glossary line, the table and the code agree both ways, and STATES.md is current — any mismatch makes every command of the tool refuse to run."""
        spec = importlib.util.spec_from_file_location("session_state_tool", TOOL)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        table = tool.load_table()
        self.assertIn("bad-publish", table["illegal_states"])
        self.assertEqual(tool.table_problems(table), [])
        done = subprocess.run([sys.executable, str(TOOL), "doc", "--check"], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "STATES.md matches the table"), done.stderr)


class RemovedKeyTests(SessionCase):
    """The old run.json spellings are no longer read (Owner 2026-09-23): a finished session still carries them, and they are neither a problem nor a warning."""

    UDID = "00000000-0000-4000-8000-000000000000"
    DERIVED = "/Users/owner/derived/Sample-abcdefghij"
    RUN_DIR = "/Users/owner/sessions/sample-001-x"

    # The shape of every session briefed before the rename, with both old verification counters.
    OLD_SHAPED = {
        "udid": UDID,
        "device_lock": "ios-build",
        "derived_data": DERIVED,
        "run_dir": RUN_DIR,
        "sweep": {"base_app": "/tmp/base.app", "tip_app": "/tmp/tip.app"},
        "verification": {"max_mutation_rounds_per_unit": 2, "whole_target_runs_owed": ["final-tip"], "whole_target_runs": ["U1"], "max_extra_review_subagents": 1},
    }

    # ------------------------------------------------------------ an old key is ignored

    def test_check__an_old_shaped_run_json_is_legal_and_prints_no_warn(self):
        """check on an old-shaped run.json exits 0 with nothing on stderr — every finished session would warn on each Lead tick for keys nothing reads."""
        self.given_implementing(**self.OLD_SHAPED)
        code, out, err = self.tool("check")
        self.assertEqual(code, 0, err)
        self.assertNotIn("WARN:", out + err)

    def test_status__an_old_shaped_run_json_prints_no_warn(self):
        """status on an old-shaped run.json prints no WARN line — the removed table would still be consulted."""
        self.given_implementing(**self.OLD_SHAPED)
        code, out, err = self.tool("status")
        self.assertEqual(code, 0, err)
        self.assertNotIn("WARN:", out + err)

    def test_status_json__carries_no_deprecated_field(self):
        """status --json has no deprecated key — a script reading it would still see a migration owed that nothing enforces."""
        self.given_implementing(**self.OLD_SHAPED)
        info = self.state()
        self.assertNotIn("deprecated", info)
        self.assertEqual((info["problems"], info["legal"]), ([], True))

    def test_check__strict_is_no_longer_an_option(self):
        """check --strict is refused as an unknown option — a caller still passing it would read exit 0 as \"no old keys\"."""
        self.given_implementing()
        code, _, err = self.tool("check", "--strict")
        self.assertEqual(code, 2, err)

    # ------------------------------------------------------------ events and check-op ignore them

    def test_check_op__an_old_shaped_session_gets_the_answers_it_got_before_and_no_warn(self):
        """launch, rotate and resume answer an old-shaped session as one without the keys, silently — a finished session's leftovers would refuse or clutter a relaunch."""
        self.given_session(**self.OLD_SHAPED)
        briefed = [self.tool("check-op", op) for op in ("launch", "rotate", "resume")]
        self.must("preflight-pass")
        self.must("intake-complete")
        implementing = [self.tool("check-op", op) for op in ("launch", "rotate", "resume")]
        self.assertEqual([code for code, _, _ in briefed], [0, 2, 0])
        self.assertEqual([code for code, _, _ in implementing], [2, 2, 0])
        self.assertNotIn("WARN:", "".join(out + err for _, out, err in briefed + implementing))

    def walk(self, **fields):
        """Every event the tool applies, in lifecycle order, plus one refusal; returns each (code, stdout, stderr)."""
        self.given_session(**fields)
        results = []
        step = lambda *args: results.append(self.tool(*args))
        step("finish")
        step("preflight-pass")
        step("intake-complete")
        step("stop", "--code", "verification-failed", "--detail", "why")
        step("resume", "--by", "lead", "--decision", "go")
        step("stop", "--code", "verification-failed", "--detail", "why")
        step("resume", "--by", "lead", "--decision", "go")
        step("stop", "--code", "one-way-door", "--detail", "why")
        self.given_rebrief_files("confident")
        step("rebrief", "--verdict", "confident", "--why", "units re-cut")
        step("rotation-resumed")
        step("unit-start", "--unit", "U1")
        self.given_gate_review("U1", "HOLD")
        step("gate-hold", "--unit", "U1")
        self.given_gate_review("U1", "ADVANCE")
        step("gate-advance", "--unit", "U1")
        step("unit-close", "--unit", "U1", "--head", SHA)
        step("request-rotate")
        step("rotation-resumed")
        step("unit-start", "--unit", "U2")
        self.given_gate_review("U2", "ADVANCE")
        step("gate-advance", "--unit", "U2")
        step("unit-close", "--unit", "U2", "--head", SHA)
        step("begin-end-of-stack")
        (self.dir / "reviews/end-of-stack.md").write_text("ADVANCE\n")
        for rel in ("HANDOFF.md", "HANDBACK.md"):
            (self.dir / rel).write_text("x\n")
        step("finish")
        return results

    def test_events__an_old_shaped_session_walks_the_lifecycle_exactly_as_one_without_the_keys(self):
        """Every event on an old-shaped run.json exits, prints and refuses exactly as on one without the keys, with no WARN line — a removed key read anywhere in the event path would change a session's course."""
        plain = self.walk()
        old = self.walk(**self.OLD_SHAPED)
        self.assertEqual([code for code, _, _ in plain], [2] + [0] * 20)
        self.assertEqual(old, plain)
        self.assertNotIn("WARN:", "".join(out + err for _, out, err in old))

    def test_events__leave_every_removed_key_in_run_json_as_it_was(self):
        """Events rewrite run.json with the old keys and their values intact — the tool owns the state fields, not the rest of the record."""
        self.given_implementing(**self.OLD_SHAPED)
        self.given_unit_closed("U1")
        run = self.run_json()
        self.assertEqual({key: run.get(key) for key in self.OLD_SHAPED}, self.OLD_SHAPED)


class ParkTests(SessionCase):
    """park: the Owner's leave-it-alone, which releases the session's own locks (U2 · D6, D7).

    The session dir sits one level under a scratch sessions root, because with no launch.json park
    looks for locks beside it; $ROBOWRIGHT_SESSIONS_ROOT points at a second scratch root that park must
    not read. park runs under a scratch HOME, which holds a launch.json only where a test writes
    one (020 U2 · D6). Every lock is fixture-* under these temp dirs — never the real sessions root.
    """

    REASON = "superseded by the 015 rebrief"

    def setUp(self):
        super().setUp()
        self.root = Path(self.tmp.name) / "sessions"
        self.dir = self.root / "robowright-park-fixture"
        self.dir.mkdir(parents=True)
        self.configured_root = Path(self.tmp.name) / "configured-sessions-root"
        self.configured_root.mkdir()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    # ------------------------------------------------------------ given

    def given_intake(self):
        self.given_session()
        self.must("preflight-pass")

    def given_end_of_stack(self, **fields):
        self.given_implementing(unit_ids=("U1",), **fields)
        self.given_unit_closed("U1")
        self.must("begin-end-of-stack")

    def given_awaiting_rotation(self):
        self.given_implementing()
        self.given_unit_closed("U1")
        self.must("request-rotate")

    def given_done(self, **fields):
        self.given_end_of_stack(**fields)
        (self.dir / "reviews/end-of-stack.md").write_text("ADVANCE\n")
        for rel in ("HANDOFF.md", "HANDBACK.md"):
            (self.dir / rel).write_text("x\n")
        self.must("finish")

    def given_stopped_mid_unit(self, code="budget", **fields):
        """Stopped from implementing with U1 building — the session most likely to still hold a lock."""
        self.given_implementing(**fields)
        self.must("unit-start", "--unit", "U1")
        self.given_stopped(code)

    def given_parked(self):
        self.given_done()
        self.park()

    def given_lock(self, name, owner=None, root=None):
        """<root>/.<name>-lock, with an `owner` file holding `owner` when it is given."""
        lock = (root or self.root) / f".{name}-lock"
        lock.mkdir()
        if owner is not None:
            (lock / "owner").write_text(owner)
        return lock

    def owned_here(self):
        return f"{self.dir}\n"

    # ------------------------------------------------------------ when / then

    def park_env(self):
        """The environment park runs in: the scratch HOME, and $ROBOWRIGHT_SESSIONS_ROOT at the root park must not read."""
        return dict(os.environ, HOME=str(self.home), ROBOWRIGHT_SESSIONS_ROOT=str(self.configured_root))

    def tool(self, *args):
        done = subprocess.run([sys.executable, str(TOOL), str(self.dir), *args], capture_output=True, text=True, env=self.park_env())
        return done.returncode, done.stdout, done.stderr

    def park(self, reason=REASON):
        """Applies park as the Owner; returns everything it printed."""
        code, out, err = self.tool("park", "--by", "owner", "--reason", reason)
        self.assertEqual(code, 0, err)
        return out + err

    def released(self):
        return self.run_json()["parked"]["released"]

    # ------------------------------------------------------------ R1 · the Owner parks a done or stopped session

    def test_park__from_done_records_the_owner_the_reason_the_time_and_done_as_origin(self):
        """park from done writes phase parked and parked = {by, reason, at, from: done} — nobody could later say who parked it, why, when, or from where."""
        self.given_done()
        self.park()
        run = self.run_json()
        parked = run["parked"]
        self.assertEqual(
            (run["phase"], parked["by"], parked["reason"], parked["at"], parked["from"]),
            ("parked", "owner", self.REASON, self.events()[-1]["at"], "done"),
        )

    def test_park__from_a_stop_mid_unit_records_the_stop_code_as_origin_and_clears_the_stop(self):
        """park from stopped records from = stopped:<code> and clears stop_reason, unit in flight or not — the session would read as parked and stopped at once, or the stop it was parked for would be lost."""
        self.given_stopped_mid_unit("budget")
        self.park()
        run = self.run_json()
        self.assertEqual((run["phase"], run["parked"]["from"], run["stop_reason"]), ("parked", "stopped:budget", None))

    def test_park__leaves_a_legal_session_in_state_parked(self):
        """A parked session is the table's parked state with no problems — check, the launcher and the roster would read it as invalid."""
        self.given_done()
        self.park()
        info = self.state()
        self.assertEqual((info["state"], info["problems"]), ("parked", []))

    # ------------------------------------------------------------ R2 · refused from every other state

    def test_park__refused_from_every_state_but_briefed_done_and_stopped(self):
        """052a-S4: park from intake, implementing, end-of-stack or awaiting-rotation is refused, run.json untouched — work in flight would be abandoned mid-step."""
        states = {
            "intake": self.given_intake,
            "implementing": self.given_implementing,
            "end-of-stack": self.given_end_of_stack,
            "awaiting-rotation": self.given_awaiting_rotation,
        }
        for state, given in states.items():
            with self.subTest(state):
                given()
                self.assertEqual(self.state()["state"], state)
                self.assert_refused("from-state", "park", "--by", "owner", "--reason", self.REASON)

    def test_park__from_briefed_records_briefed_as_origin(self):
        """052a-S1: park from briefed records from = briefed — the record would say the session finished, and the dashboard would place it mid-brief."""
        self.given_session()
        self.park()
        run = self.run_json()
        self.assertEqual((run["phase"], run["parked"]["from"], run["parked"]["reason"]), ("parked", "briefed", self.REASON))

    def test_park__from_briefed_refused_without_a_reason(self):
        """052a-S2: no --reason, no park from briefed either — a brief would be shelved with nothing saying why."""
        self.given_session()
        self.assert_refused("reason", "park", "--by", "owner")

    def test_park__from_briefed_refused_for_anyone_but_the_owner(self):
        """052a-S3: --by lead is refused park-is-owner from briefed — the Lead could shelve a brief the Owner meant to launch."""
        self.given_session()
        self.assert_refused("park-is-owner", "park", "--by", "lead", "--reason", self.REASON)

    # ------------------------------------------------------------ R3 · the Owner's alone, with a reason

    def test_park__refused_for_anyone_but_the_owner(self):
        """--by lead is refused park-is-owner — the Lead could close out a session the Owner meant to resume."""
        self.given_done()
        self.assert_refused("park-is-owner", "park", "--by", "lead", "--reason", self.REASON)

    def test_park__refused_without_a_reason(self):
        """No --reason, no park — the roster's parked: line and the record would say nothing about why."""
        self.given_done()
        self.assert_refused("reason", "park", "--by", "owner")

    def test_park__refused_with_a_blank_reason(self):
        """A blank --reason is refused like a missing one — whitespace would pass for a reason."""
        self.given_done()
        self.assert_refused("reason", "park", "--by", "owner", "--reason", "  ")

    def test_park__refused_releases_no_lock(self):
        """A refused park leaves the session's own lock in place — a refused Lead park would free a device the session still holds."""
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        lock = self.given_lock("fixture-mine", self.owned_here())
        self.assert_refused("park-is-owner", "park", "--by", "lead", "--reason", self.REASON)
        self.assertTrue(lock.is_dir())

    # ------------------------------------------------------------ R4 · the event carries its reason

    def test_park__event_log_carries_the_reason(self):
        """The park event in events.jsonl records --reason — the reason would reach run.json but not the log."""
        self.given_done()
        self.park()
        park = self.events()[-1]
        self.assertEqual((park["event"], park.get("refused", False), park.get("reason")), ("park", False, self.REASON))

    # ------------------------------------------------------------ R5 · releases exactly the session's own locks

    def test_park__leaves_a_lock_whose_name_is_not_a_lock_name(self):
        """SI-13: locks is session-written and park removes the directory a lock name builds, so only lowercase letters, digits and `-` make a name; park notes any other entry and removes nothing for it, even a lock this session owns."""
        lock = self.given_lock("x.y", self.owned_here())
        self.given_stopped_mid_unit(locks=["x.y"])
        out = self.park()
        self.assertTrue(lock.is_dir())
        self.assertEqual(self.released(), [])
        self.assertIn('"x.y"', out)

    def test_park__releases_a_listed_lock_this_session_owns(self):
        """A lock in locks owned by this session dir is removed and listed in parked.released — a parked session would hold the device forever, since nothing else releases it."""
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        lock = self.given_lock("fixture-mine", self.owned_here())
        self.park()
        self.assertEqual((lock.exists(), self.released()), (False, ["fixture-mine"]))

    def test_park__still_releases_its_own_lock_beside_a_null_locks_entry(self):
        """A null beside a lock this session owns does not stop the release, and parked.released stays a list of the names freed — a refusal would strand park, and a bad entry in released would break its shape (review F5, D6)."""
        self.given_stopped_mid_unit(locks=["fixture-mine", None])
        lock = self.given_lock("fixture-mine", self.owned_here())
        self.park()
        self.assertEqual((lock.exists(), self.released()), (False, ["fixture-mine"]))

    def test_park__names_a_null_locks_entry_it_cannot_release(self):
        """park exits 0 and its output names the null entry — silently dropped, the Owner reads a release that looks complete for a list the launcher refuses (review F5, D6)."""
        self.given_stopped_mid_unit(locks=["fixture-mine", None])
        self.given_lock("fixture-mine", self.owned_here())
        out = self.park()
        self.assertRegex(out, r"(?m)^.*lock.*\bnull\b.*$")

    def test_park__names_an_empty_string_locks_entry_it_cannot_release(self):
        """An empty string is not a lock name either, so park names it as `""` — only null would be caught, and the next hand-edit leaves a blank entry nobody hears about (D6; assumed U2 Q3)."""
        self.given_stopped_mid_unit(locks=["fixture-mine", ""])
        self.given_lock("fixture-mine", self.owned_here())
        out = self.park()
        self.assertRegex(out, r'(?m)^.*lock.*"".*$')

    def test_park__leaves_a_listed_lock_another_session_owns(self):
        """A lock owned by another session dir is left, not recorded as released, and named in the output — park would free a device another session is building on (assumed Q1)."""
        other = self.root / "robowright-park-fixture-other"
        other.mkdir()
        self.given_stopped_mid_unit(locks=["fixture-theirs"])
        lock = self.given_lock("fixture-theirs", f"{other}\n")
        out = self.park()
        self.assertEqual(((lock / "owner").read_text(), self.released()), (f"{other}\n", []))
        self.assertIn("fixture-theirs", out)

    def test_park__names_an_absent_lock_and_releases_nothing(self):
        """A listed lock that is not there is named in the output, released as nothing, and not created — the Owner could not tell a lock park skipped from one it freed (assumed Q1)."""
        self.given_stopped_mid_unit(locks=["fixture-absent"])
        out = self.park()
        self.assertEqual(((self.root / ".fixture-absent-lock").exists(), self.released()), (False, []))
        self.assertIn("fixture-absent", out)

    def test_park__leaves_a_lock_whose_owner_cannot_be_read(self):
        """A lock with no owner file is never removed — park would clear a lock nobody can say is this session's."""
        self.given_stopped_mid_unit(locks=["fixture-unowned"])
        lock = self.given_lock("fixture-unowned")
        self.park()
        self.assertEqual((lock.is_dir(), self.released()), (True, []))

    def test_park__releases_a_lock_whose_owner_names_this_session_through_a_symlink(self):
        """The owner line is compared by realpath — a lock taken through another spelling of the session dir would never be released."""
        alias = Path(self.tmp.name) / "alias-of-the-session"
        alias.symlink_to(self.dir, target_is_directory=True)
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        lock = self.given_lock("fixture-mine", f"{alias}\n")
        self.park()
        self.assertEqual((lock.exists(), self.released()), (False, ["fixture-mine"]))

    def test_park__reads_only_the_first_line_of_owner(self):
        """Only owner's first line names the holder — a lock whose owner file says more would never be released."""
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        lock = self.given_lock("fixture-mine", f"{self.dir}\ntaken before the first build\n")
        self.park()
        self.assertEqual((lock.exists(), self.released()), (False, ["fixture-mine"]))

    def test_park__a_device_lock_is_not_read(self):
        """With no locks key, a device_lock names nothing to release, even a lock this session owns — the retired spelling would still drive a release (Owner 2026-09-23)."""
        self.given_stopped_mid_unit(device_lock="fixture-legacy")
        lock = self.given_lock("fixture-legacy", self.owned_here())
        self.park()
        self.assertEqual((lock.is_dir(), self.released()), (True, []))

    def test_park__notes_nothing_about_a_device_lock_that_is_no_lock_name(self):
        """A device_lock of true, "", false or null earns no note — the retired key would still be validated as if it were read."""
        for value in (True, "", False, None):
            with self.subTest(device_lock=value):
                self.tearDown()
                self.setUp()
                self.given_stopped_mid_unit(device_lock=value)
                out = self.park()
                self.assertEqual(self.released(), [])
                self.assertNotIn("device_lock", out)

    def test_park__records_an_empty_release_with_no_lock_source(self):
        """With no locks key, parked.released is an empty list — a reader would have to tell absent from empty (assumed Q2)."""
        self.given_done()
        self.park()
        self.assertEqual(self.released(), [])

    def test_park__notes_nothing_when_locks_is_absent(self):
        """An absent locks key is not a value to note — only a locks[] entry that is present and not a lock name is."""
        self.given_stopped_mid_unit()
        out = self.park()
        self.assertNotIn("not a lock name", out)

    def test_park__looks_for_locks_beside_the_session_dir_not_under_the_configured_root(self):
        """The sessions root is the session dir's parent — park would release a same-named lock under whatever root the environment names."""
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        beside = self.given_lock("fixture-mine", self.owned_here())
        configured = self.given_lock("fixture-mine", self.owned_here(), root=self.configured_root)
        self.park()
        self.assertEqual((beside.exists(), configured.is_dir()), (False, True))

    def test_park__releases_its_lock_when_the_session_dir_is_given_as_dot(self):
        """`session-state.py . park` from inside the session dir finds the lock beside it — park is terminal, so a lock it missed stays held with no tool left to release it."""
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        lock = self.given_lock("fixture-mine", self.owned_here())
        done = subprocess.run([sys.executable, str(TOOL), ".", "park", "--by", "owner", "--reason", self.REASON], capture_output=True, text=True, env=self.park_env(), cwd=self.dir)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((lock.exists(), self.released()), (False, ["fixture-mine"]))

    # ------------------------------------------------------------ the lock sits under launch.json's sessions_root (020 U2 · D6)

    def given_launch_json(self, sessions_root):
        """$HOME/.claude/robowright/launch.json under the scratch HOME, naming `sessions_root` — the file the launcher takes the root from."""
        self.given_home(Path(self.tmp.name), sessions_root)

    def given_launch_json_text(self, text):
        """$HOME/.claude/robowright/launch.json holding `text` as written, for a file park cannot take a root from."""
        path = self.home / ".claude/robowright/launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_park__releases_its_lock_under_launch_json_s_sessions_root_when_that_is_not_the_parent(self):
        """The launcher refuses on <sessions_root>/.<name>-lock; park looked beside the session dir, so a session one level deeper parked and kept its lock forever (review F5, D6 R1)."""
        sessions_root = Path(self.tmp.name)
        self.given_launch_json(str(sessions_root))
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        at_root = self.given_lock("fixture-mine", self.owned_here(), root=sessions_root)
        beside = self.given_lock("fixture-mine", self.owned_here())
        self.park()
        self.assertEqual((at_root.exists(), beside.is_dir(), self.released()), (False, True, ["fixture-mine"]))

    def test_park__expands_a_home_relative_sessions_root(self):
        """launch.json may name the root as `~/…`, and the launcher expands it against $HOME — park taking `~` literally would find no lock and release nothing (D6 R1)."""
        sessions_root = self.home / "robowright-sessions"
        sessions_root.mkdir()
        self.given_launch_json("~/robowright-sessions")
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        at_root = self.given_lock("fixture-mine", self.owned_here(), root=sessions_root)
        self.park()
        self.assertEqual((at_root.exists(), self.released()), (False, ["fixture-mine"]))

    def test_park__releases_its_lock_under_home_abs_when_launch_json_names_tilde_double_slash_abs(self):
        """launch.json's `~//abs` is $HOME/abs, as the launcher reads it — joined as a path, `/abs` drops $HOME, park finds no lock, and the parked session holds the device forever (D4)."""
        sessions_root = self.home / "abs"
        sessions_root.mkdir()
        self.given_launch_json("~//abs")
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        at_root = self.given_lock("fixture-mine", self.owned_here(), root=sessions_root)
        beside = self.given_lock("fixture-mine", self.owned_here())
        self.park()
        self.assertEqual((at_root.exists(), beside.is_dir(), self.released()), (False, True, ["fixture-mine"]))

    def test_park__reads_a_bare_tilde_sessions_root_as_written_against_its_cwd(self):
        """launch.json's bare `~` is read as written, as the launcher reads it — taken as $HOME, park would free a same-named lock the launcher never consults (D4; green at red — owes its kill first)."""
        cwd = Path(self.tmp.name) / "cwd"
        (cwd / "~").mkdir(parents=True)
        self.given_launch_json("~")
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        as_written = self.given_lock("fixture-mine", self.owned_here(), root=cwd / "~")
        in_home = self.given_lock("fixture-mine", self.owned_here(), root=self.home)
        done = subprocess.run([sys.executable, str(TOOL), str(self.dir), "park", "--by", "owner", "--reason", self.REASON], capture_output=True, text=True, env=self.park_env(), cwd=cwd)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((as_written.exists(), in_home.is_dir(), self.released()), (False, True, ["fixture-mine"]))

    def test_park__with_no_launch_json_releases_its_lock_beside_the_session_dir(self):
        """A HOME with no launch.json is the test sandbox, and there the root is the session dir's parent, as before — every scratch park would otherwise lose its lock lookup (D6 R2; green at red — owes its kill first)."""
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        beside = self.given_lock("fixture-mine", self.owned_here())
        self.park()
        self.assertEqual((beside.exists(), self.released()), (False, ["fixture-mine"]))

    def test_park__a_launch_json_that_is_not_json_falls_back_to_the_parent_and_says_so(self):
        """A launch.json park cannot parse gives the parent, and park's output names launch.json — silently, the Owner would read a partial release as the whole of it (D6 R3)."""
        self.given_launch_json_text("{ not json\n")
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        beside = self.given_lock("fixture-mine", self.owned_here())
        out = self.park()
        self.assertEqual((beside.exists(), self.released()), (False, ["fixture-mine"]))
        self.assertIn("launch.json", out)

    def test_park__a_launch_json_with_no_sessions_root_falls_back_to_the_parent_and_says_so(self):
        """A launch.json lacking sessions_root gives the parent, and park's output names launch.json — a crash would strand park, a silent fallback would hide why a lock stayed (D6 R3)."""
        self.given_launch_json_text(json.dumps({"schema": 1}) + "\n")
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        beside = self.given_lock("fixture-mine", self.owned_here())
        out = self.park()
        self.assertEqual((beside.exists(), self.released()), (False, ["fixture-mine"]))
        self.assertIn("launch.json", out)

    def test_park__a_launch_json_whose_sessions_root_is_not_a_string_falls_back_to_the_parent_and_says_so(self):
        """A non-string sessions_root gives the parent, and park's output names launch.json — read as text, `5` becomes a relative directory no lock is in (D6 R3)."""
        self.given_launch_json_text(json.dumps({"schema": 1, "sessions_root": 5}) + "\n")
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        beside = self.given_lock("fixture-mine", self.owned_here())
        out = self.park()
        self.assertEqual((beside.exists(), self.released()), (False, ["fixture-mine"]))
        self.assertIn("launch.json", out)

    def test_park__takes_the_root_from_launch_json_never_from_robowright_sessions_root(self):
        """With launch.json present, $ROBOWRIGHT_SESSIONS_ROOT naming another root is still not read — park would free a same-named lock the launcher never consults (D6 R4)."""
        sessions_root = Path(self.tmp.name)
        self.given_launch_json(str(sessions_root))
        self.given_stopped_mid_unit(locks=["fixture-mine"])
        at_root = self.given_lock("fixture-mine", self.owned_here(), root=sessions_root)
        configured = self.given_lock("fixture-mine", self.owned_here(), root=self.configured_root)
        self.park()
        self.assertEqual((at_root.exists(), configured.is_dir(), self.released()), (False, True, ["fixture-mine"]))

    def test_park__leaves_the_worktree(self):
        """park never touches the worktree — uncommitted work the Owner may still want would be lost."""
        worktree = Path(self.tmp.name) / "worktree"
        worktree.mkdir()
        (worktree / "Unpublished.swift").write_text("let kept = true\n")
        self.given_stopped_mid_unit(worktree=str(worktree))
        self.park()
        self.assertEqual((worktree / "Unpublished.swift").read_text(), "let kept = true\n")

    # ------------------------------------------------------------ R6 · no event leaves parked

    def test_status__a_parked_session_has_no_legal_event(self):
        """status lists nothing legal from parked — an agent told it may resume a parked session will try."""
        self.given_parked()
        self.assertEqual(self.state()["legal_events"], [])

    def test_park__no_event_leaves_parked(self):
        """park, resume, stop, rebrief and finish are each refused from parked, run.json untouched — a parked session could be reopened, which is the unpark D6 rules out."""
        self.given_parked()
        attempts = {
            "park": ("--by", "owner", "--reason", "parked twice"),
            "resume": ("--by", "owner", "--decision", "carry on after all"),
            "stop": ("--code", "budget", "--detail", "x"),
            "rebrief": ("--verdict", "confident", "--why", "x"),
            "finish": (),
        }
        for event, flags in attempts.items():
            with self.subTest(event):
                self.assert_refused("from-state", event, *flags)

    # ------------------------------------------------------------ R9 · terminal, and never also stopped

    def test_table__parked_is_a_terminal_session_state(self):
        """The session machine lists parked beside done as terminal — the machine's designed ends would omit the Owner's."""
        table = json.loads((HERE.parent / "state-machine.json").read_text())
        session = [m for m in table["machines"] if m["id"] == "session"][0]
        self.assertEqual(session["terminal"], ["done", "parked"])

    def test_check__names_parked_and_stopped(self):
        """phase parked with a stop code set is named parked-and-stopped — the roster would print a plausible verdict for a state park never writes."""
        self.given_session(
            phase="parked",
            stop_reason={"code": "budget", "phase_before": "implement"},
            parked={"by": "owner", "reason": self.REASON, "at": "2026-09-22T10:00:00+00:00", "from": "stopped:budget", "released": []},
            units=[{"id": "U1", "status": "done"}],
        )
        named = [p.split(":")[0] for p in self.state()["problems"]]
        self.assertIn("parked-and-stopped", named)


class UnitCloseHeadTests(SessionCase):
    """unit-close --head resolves in the session's worktree when there is one (U4 · D8).

    The worktree is a scratch git repo beside the session dir, never inside it, because
    given_session empties the session dir. When run.json.worktree names no directory, the SHA's
    shape is all the tool can check.
    """

    def setUp(self):
        super().setUp()
        self.worktree = Path(self.tmp.name) / "worktree"
        self.dir = Path(self.tmp.name) / "session"
        self.dir.mkdir()
        subprocess.run(["git", "init", "-q", str(self.worktree)], check=True, capture_output=True)
        (self.worktree / "notes.txt").write_text("one\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")

    # ------------------------------------------------------------ given

    def git(self, *args):
        done = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(self.worktree), *args], check=True, capture_output=True, text=True)
        return done.stdout.strip()

    def given_advanced(self, worktree):
        self.given_implementing(worktree=str(worktree))
        self.must("unit-start", "--unit", "U1")
        self.given_gate_review("U1", "ADVANCE")
        self.must("gate-advance", "--unit", "U1")

    # ------------------------------------------------------------ then

    def assert_head_refused_by_name(self, head):
        before = (self.dir / "run.json").read_text()
        code, _, err = self.tool("unit-close", "--unit", "U1", "--head", head)
        self.assertEqual(code, 2, err)
        self.assertIn(": head-given: ", err)
        self.assertIn(head, err)
        self.assertEqual((self.dir / "run.json").read_text(), before)

    # ------------------------------------------------------------ R1 · an existing worktree resolves the head

    def test_unit_close__refused_naming_a_head_that_names_no_commit_in_the_worktree(self):
        """A well-formed SHA that names nothing in the worktree is refused by name — run.json would record a head no reviewer, roster or cost range can resolve (007's U4)."""
        self.given_advanced(self.worktree)
        self.assert_head_refused_by_name("7fe8979a")

    def test_unit_close__refused_naming_a_head_that_is_a_tree_not_a_commit(self):
        """An object that exists but is not a commit is refused — checking existence alone would accept a tree SHA as a unit's head."""
        self.given_advanced(self.worktree)
        tree = self.git("rev-parse", "HEAD^{tree}")
        self.assert_head_refused_by_name(tree)

    def test_unit_close__records_a_head_that_is_a_commit_in_the_worktree(self):
        """A SHA that resolves to a commit closes the unit as before — the resolve check would otherwise block every close."""
        self.given_advanced(self.worktree)
        commit = self.git("rev-parse", "--short=7", "HEAD")
        self.must("unit-close", "--unit", "U1", "--head", commit)
        self.assertEqual((self.unit("U1")["status"], self.unit("U1")["head"]), ("done", commit))

    def test_unit_close__refused_a_ref_name_that_resolves_but_is_not_a_sha(self):
        """HEAD resolves in git but is still refused — the shape check stays, and a symbolic head moves after the close."""
        self.given_advanced(self.worktree)
        before = (self.dir / "run.json").read_text()
        code, _, err = self.tool("unit-close", "--unit", "U1", "--head", "HEAD")
        self.assertEqual(code, 2, err)
        self.assertIn(": head-given: ", err)
        self.assertEqual((self.dir / "run.json").read_text(), before)

    def test_unit_close__refused_when_no_configured_repository_lists_the_worktree(self):
        """R1.5 · a worktree no robowright.json repository lists is refused head-given naming worktree-unlisted, and no git runs inside it — its config would run as the Owner when the Owner applies an event."""
        self.given_owner_repos(Path(self.tmp.name) / "some-other-clone")
        self.given_advanced(self.worktree)
        commit = self.git("rev-parse", "--short=7", "HEAD")
        log, env = self.recording_git()
        before = (self.dir / "run.json").read_text()

        done = subprocess.run([sys.executable, str(TOOL), str(self.dir), "unit-close", "--unit", "U1", "--head", commit],
                              capture_output=True, text=True, env=env)

        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn(": head-given: ", done.stderr)
        self.assertIn("worktree-unlisted", done.stderr)
        self.assertEqual((self.dir / "run.json").read_text(), before)
        self.assertEqual([c for c in git_calls(log) if runs_in(c, self.worktree)], [])

    def test_unit_close__every_git_call_in_the_worktree_carries_the_overrides(self):
        """R1.6 · each git the head check runs starts with the fsmonitor, hooksPath, pager and showSignature overrides — a call without them runs the worktree's configured fsmonitor."""
        self.given_advanced(self.worktree)
        commit = self.git("rev-parse", "--short=7", "HEAD")
        log, env = self.recording_git()

        done = subprocess.run([sys.executable, str(TOOL), str(self.dir), "unit-close", "--unit", "U1", "--head", commit],
                              capture_output=True, text=True, env=env)

        self.assertEqual(done.returncode, 0, done.stderr)
        calls = git_calls(log)
        self.assertTrue(any(runs_in(c, self.worktree) for c in calls), calls)
        for call in calls:
            self.assertEqual(call[:len(HARDENING)], HARDENING, call)

    def recording_git(self):
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "git").write_text(RECORDING_GIT)
        (bin_dir / "git").chmod(0o755)
        log = Path(self.tmp.name) / "git-argv.log"
        return log, dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", GIT_ARGV_LOG=str(log))

    # ------------------------------------------------------------ R2 · no worktree, shape only

    def test_unit_close__records_a_well_formed_head_when_the_worktree_is_gone(self):
        """With the recorded worktree torn down, a well-formed SHA is accepted on shape — a unit closed after teardown could never close."""
        self.given_advanced(Path(self.tmp.name) / "torn-down-worktree")
        self.must("unit-close", "--unit", "U1", "--head", "7fe8979a")
        self.assertEqual((self.unit("U1")["status"], self.unit("U1")["head"]), ("done", "7fe8979a"))


class AcceptTests(SessionCase):
    """accept: the Owner's record that a done session's squash is on main (016 S1–S3); accept.sh applies it."""

    def given_done(self):
        self.given_implementing(unit_ids=("U1",))
        self.given_unit_closed("U1")
        self.must("begin-end-of-stack")
        (self.dir / "reviews/end-of-stack.md").write_text("ADVANCE\n")
        for rel in ("HANDOFF.md", "HANDBACK.md"):
            (self.dir / rel).write_text("x\n")
        self.must("finish")

    def test_accept__from_done_records_the_accepted_sha_and_time_and_stays_done(self):
        """S1 accept writes accepted = {sha, at}, keeps phase done, and logs the SHA — nothing on disk would say the work reached main, or which commit it is."""
        self.given_done()
        self.must("accept", "--head", "7fe8979a")
        run = self.run_json()
        self.assertEqual((run["phase"], run["accepted"]["sha"]), ("done", "7fe8979a"))
        self.assertTrue(run["accepted"]["at"])
        last = self.events()[-1]
        self.assertEqual((last["event"], last.get("refused", False), last.get("head")), ("accept", False, "7fe8979a"))

    def test_accept__refused_from_a_session_that_is_not_done(self):
        """S2 accept from end-of-stack or parked is refused from-state, run.json untouched — unfinished or abandoned work would read as accepted."""
        self.given_done()
        self.must("park", "--by", "owner", "--reason", "left")
        self.assert_refused("from-state", "accept", "--head", "7fe8979a")
        self.given_implementing(unit_ids=("U1",))
        self.given_unit_closed("U1")
        self.must("begin-end-of-stack")
        self.assert_refused("from-state", "accept", "--head", "7fe8979a")

    def test_accept__refused_a_head_that_is_not_a_sha(self):
        """S3 `--head main` is refused head-given — a ref name moves, so accepted.sha would stop naming the accepted commit."""
        self.given_done()
        self.assert_refused("head-given", "accept", "--head", "main")

    def test_accept__the_old_event_name_is_not_an_event(self):
        """043-S1 `land` is a usage error that writes nothing — a second name for the record would leave two words for one act on disk."""
        self.given_done()
        before = ((self.dir / "run.json").read_text(), (self.dir / "events.jsonl").read_text())
        code, _, err = self.tool("land", "--head", "7fe8979a")
        self.assertNotEqual(code, 0, err)
        self.assertIn("invalid choice: 'land'", err)
        self.assertEqual(((self.dir / "run.json").read_text(), (self.dir / "events.jsonl").read_text()), before)


class PlanReviewCase(SessionCase):
    """Givens for the finish review (017 U1): a one-unit session at end-of-stack, PLAN-REVIEW.md, the polish gate."""

    def given_end_of_stack(self, **fields):
        self.given_implementing(unit_ids=("U1",), **fields)
        self.given_unit_closed("U1")
        self.must("begin-end-of-stack")

    def given_plan_review_file(self, verdict):
        (self.dir / "PLAN-REVIEW.md").write_text(f"# Plan review\n\nVerdict: {verdict}\n\nfindings\n")

    def given_plan_review(self, verdict, *flags):
        self.given_plan_review_file(verdict)
        self.must("plan-review", "--verdict", verdict, *flags)

    def given_polish_gate(self, verdict):
        (self.dir / "reviews" / "polish-gate.md").write_text(f"{verdict}\n\nfindings\n")

    def assert_not_applied(self, event, *args):
        """Refused by any means, a guard or the flag parser: exit non-zero, run.json untouched, no applied event logged."""
        before = (self.dir / "run.json").read_text()
        code, _, err = self.tool(event, *args)
        self.assertNotEqual(code, 0, err)
        self.assertEqual((self.dir / "run.json").read_text(), before)
        self.assertEqual([e for e in self.events() if e.get("event") == event and not e.get("refused")], [])


class PlanReviewTests(PlanReviewCase):
    """R1 · plan-review records the finish review's verdict on the session machine (017 U1 · D3)."""

    # ------------------------------------------------------------ R1 · from end-of-stack

    def test_plan_review__ship_from_end_of_stack_is_recorded_and_the_state_stays(self):
        """R1.1 ship with PLAN-REVIEW.md saying ship appends {n, at, verdict, unit: null, path}, stays at end-of-stack, check legal — finish would have no verdict on record to read (n, path assumed Q1, Q2)."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file("ship")

        self.must("plan-review", "--verdict", "ship")

        reviews = self.run_json()["plan_reviews"]
        self.assertEqual(len(reviews), 1)
        entry = reviews[0]
        self.assertEqual(sorted(entry), ["at", "n", "path", "unit", "verdict"])
        self.assertEqual((entry["n"], entry["verdict"], entry["unit"], Path(entry["path"]).name), (1, "ship", None, "PLAN-REVIEW.md"))
        self.assertTrue(entry["at"])
        self.assertEqual((self.state()["state"], self.tool("check")[0]), ("end-of-stack", 0))

    def test_plan_review__refused_without_the_review_file(self):
        """R1.2 no PLAN-REVIEW.md is refused plan-review-file-has-verdict — a verdict could be recorded that no Planner wrote."""
        self.given_end_of_stack(plan_review="finish")

        self.assert_refused("plan-review-file-has-verdict", "plan-review", "--verdict", "ship")

    def test_plan_review__refused_when_the_file_says_another_verdict(self):
        """R1.3 --verdict ship against a file saying polish is refused plan-review-file-has-verdict — a Worker could finish past a Planner who asked for polish."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file("polish")

        self.assert_refused("plan-review-file-has-verdict", "plan-review", "--verdict", "ship")

    def test_plan_review__refused_when_the_review_is_off(self):
        """R1.4 plan_review off refuses plan-review-on, even with a ship file on disk — a session the brief exempted would record a review nobody asked for."""
        self.given_end_of_stack(plan_review="off")
        self.given_plan_review_file("ship")

        self.assert_refused("plan-review-on", "plan-review", "--verdict", "ship")

    def test_plan_review__applied_when_run_json_has_no_plan_review_key(self):
        """R1.5 a run.json without plan_review reads as finish, so the review is recorded — every session briefed before 017 could never record its finish review."""
        self.given_end_of_stack()
        self.given_hand_edit(lambda run: run.pop("plan_review"))
        self.given_plan_review_file("ship")

        self.must("plan-review", "--verdict", "ship")

        self.assertEqual([r["verdict"] for r in self.run_json()["plan_reviews"]], ["ship"])

    # ------------------------------------------------------------ R1 · from implementing (per-unit)

    def test_plan_review__from_implementing_records_the_unit(self):
        """R1.6 from implementing, --unit U1 is recorded on the entry and the state stays — a per-unit review would not say which unit it judged."""
        self.given_implementing(plan_review="per-unit")
        self.given_unit_closed("U1")
        self.given_plan_review_file("ship")

        self.must("plan-review", "--verdict", "ship", "--unit", "U1")

        self.assertEqual([r["unit"] for r in self.run_json()["plan_reviews"]], ["U1"])
        self.assertEqual((self.state()["state"], self.tool("check")[0]), ("implementing", 0))

    def test_plan_review__from_implementing_refused_without_a_unit(self):
        """R1.7 from implementing without --unit is refused unit-known — a mid-stack review would be recorded as the finish review (assumed Q4)."""
        self.given_implementing(plan_review="per-unit")
        self.given_unit_closed("U1")
        self.given_plan_review_file("ship")

        self.assert_refused("unit-known", "plan-review", "--verdict", "ship")

    def test_plan_review__from_implementing_refused_naming_a_unit_run_json_does_not_have(self):
        """R1.8 --unit U9 is refused unit-known — a typo would record a review of a unit that does not exist (assumed Q4)."""
        self.given_implementing(plan_review="per-unit")
        self.given_unit_closed("U1")
        self.given_plan_review_file("ship")

        self.assert_refused("unit-known", "plan-review", "--verdict", "ship", "--unit", "U9")

    # ------------------------------------------------------------ R1 · the shared --verdict flag

    def test_plan_review__refused_the_rebrief_verdict_confident(self):
        """R1.9 plan-review --verdict confident is not applied, even with a file saying it — widening --verdict would let a rebrief's word stand for a finish verdict."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file("confident")

        self.assert_not_applied("plan-review", "--verdict", "confident")

    def test_plan_review__verdict_ship_does_not_leak_into_rebrief(self):
        """R1.10 rebrief --verdict ship is not applied, even with REBRIEF.md saying it — widening --verdict would let a finish verdict launch a rebrief rotation."""
        self.given_implementing()
        self.given_stopped()
        (self.dir / "REBRIEF.md").write_text("# Rebrief\n\nVerdict: ship\n")
        (self.dir / "BRIEF.r1.md").write_text("old\n")

        self.assert_not_applied("rebrief", "--verdict", "ship", "--why", "x")


class FinishPlanReviewTests(PlanReviewCase):
    """R2 · finish waits for a settled finish review: plan-review-settled (017 U1 · D3, D8)."""

    def given_ready_to_finish(self, **fields):
        self.given_end_of_stack(**fields)
        (self.dir / "reviews/end-of-stack.md").write_text("ADVANCE\n")
        for rel in ("HANDOFF.md", "HANDBACK.md"):
            (self.dir / rel).write_text("x\n")

    # ------------------------------------------------------------ R2 · refused

    def test_finish__refused_with_no_verdict_when_the_review_is_on(self):
        """R2.1 plan_review finish with plan_reviews empty is refused plan-review-settled — a session would reach done with its finish review never run."""
        self.given_ready_to_finish(plan_review="finish", plan_reviews=[])

        self.assert_refused("plan-review-settled", "finish")

    def test_finish__refused_with_no_verdict_when_the_key_is_absent(self):
        """R2.2 no plan_review key and no plan_reviews is refused plan-review-settled, not a crash — an old-shaped run.json would skip the review, or the tool would crash on it (Q8 assumed)."""
        self.given_ready_to_finish()
        self.given_hand_edit(lambda run: run.pop("plan_review"))

        self.assert_refused("plan-review-settled", "finish")

    def test_finish__refused_after_a_rebrief_verdict(self):
        """R2.4 a rebrief verdict refuses finish — a stack the Planner said misses the plan would reach done instead of stopping."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("rebrief")

        self.assert_refused("plan-review-settled", "finish")

    def test_finish__refused_after_polish_without_a_polish_gate(self):
        """R2.5 polish with no reviews/polish-gate.md is refused — the polish would reach done ungated."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("polish")

        self.assert_refused("plan-review-settled", "finish")

    def test_finish__refused_after_polish_whose_gate_says_hold(self):
        """R2.6 polish with a polish gate saying HOLD is refused — a polish the gate rejected would reach done."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("polish")
        self.given_polish_gate("HOLD")

        self.assert_refused("plan-review-settled", "finish")

    def test_finish__refused_when_a_rebrief_follows_a_ship(self):
        """R2.9 the newest verdict decides: ship then rebrief is refused — an older ship would outvote the review that found the stack wrong."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("ship")
        self.given_plan_review("rebrief")

        self.assert_refused("plan-review-settled", "finish")

    def test_finish__a_per_unit_verdict_does_not_settle_finish(self):
        """R2.10 a per-unit ship recorded in implementing does not settle finish — the whole stack would finish on a review of one unit (assumed Q5)."""
        self.given_implementing(unit_ids=("U1",), plan_review="per-unit")
        self.given_unit_closed("U1")
        self.given_plan_review("ship", "--unit", "U1")
        self.must("begin-end-of-stack")
        (self.dir / "reviews/end-of-stack.md").write_text("ADVANCE\n")
        for rel in ("HANDOFF.md", "HANDBACK.md"):
            (self.dir / rel).write_text("x\n")

        self.assert_refused("plan-review-settled", "finish")

    # ------------------------------------------------------------ R2 · applied

    def test_finish__applied_after_a_ship_verdict(self):
        """R2.3 a ship verdict lets finish move the session to done — the review that passed would still block the session."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("ship")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    def test_finish__applied_after_polish_whose_gate_says_advance(self):
        """R2.7 polish with a polish gate saying ADVANCE lets finish move to done — a polished, gated stack could never finish."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("polish")
        self.given_polish_gate("ADVANCE")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    def test_finish__applied_with_no_verdict_when_the_review_is_off(self):
        """R2.8 plan_review off finishes with no PLAN-REVIEW.md and no verdict — a session the brief exempted could never finish."""
        self.given_ready_to_finish(plan_review="off")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")


# Fixed instants for the polish gate's freshness (017 P1 rule 2), each an ISO `at` and its epoch.
AT_0900_UTC, EPOCH_0900_UTC = "2026-09-26T09:00:00+00:00", 1790413200
AT_1000_UTC, EPOCH_1000_UTC = "2026-09-26T10:00:00+00:00", 1790416800
AT_1000_UTC_AS_IST = "2026-09-26T15:30:00+05:30"  # the same instant as AT_1000_UTC, written with a non-UTC offset
AT_1100_UTC = "2026-09-26T11:00:00+00:00"
MODE_REFUSAL = "expected finish, per-unit or off"
# The bound's mapping for the old schema's boolean, as the refusal spells it.
BOOLEAN_MAPPING = 'false → "off", true → "finish"'


class P1GuardCase(PlanReviewCase):
    """Givens for 017 P1 (the guards do what D3 says): a refusal whose message is read, a rebrief stop, a dated polish gate."""

    def refusal(self, guard, *args):
        """assert_refused's checks — exit 2, the guard named, run.json untouched — returning stderr so the message can be read."""
        before = (self.dir / "run.json").read_text()
        code, _, err = self.tool(*args)
        self.assertEqual(code, 2, err)
        self.assertIn(f": {guard}: ", err)
        self.assertEqual((self.dir / "run.json").read_text(), before)
        return err

    def given_ready_to_finish(self, **fields):
        self.given_end_of_stack(**fields)
        (self.dir / "reviews/end-of-stack.md").write_text("ADVANCE\n")
        for rel in ("HANDOFF.md", "HANDBACK.md"):
            (self.dir / rel).write_text("x\n")

    def given_rebrief_stop(self, rebrief_text):
        self.given_implementing()
        self.given_stopped()
        (self.dir / "REBRIEF.md").write_text(rebrief_text)
        (self.dir / "BRIEF.r1.md").write_text("old\n")

    def given_plan_review_file_text(self, text):
        (self.dir / "PLAN-REVIEW.md").write_text(text)

    def given_polish_gate_at(self, verdict, epoch):
        self.given_polish_gate(verdict)
        os.utime(self.dir / "reviews" / "polish-gate.md", (epoch, epoch))

    def given_finish_reviews_dated(self, *ats):
        """Rewrite the recorded finish reviews' at, oldest first: plan_reviews is not guarded state, so check stays legal."""
        def date(run):
            for entry, at in zip(run["plan_reviews"], ats):
                entry["at"] = at
        self.given_hand_edit(date)

    def given_plan_review_value(self, value):
        self.given_hand_edit(lambda run: run.update(plan_review=value))

    def assert_names_a_non_string(self, err, json_type, json_value):
        """The refusal names the JSON type and value it found and the three legal strings (021 bound 2)."""
        self.assertIn(f"run.json.plan_review is the {json_type} {json_value}, not a string: " + MODE_REFUSAL, err)


BY_HAND_PLAN_REVIEW = (
    "# Planner review — the whole stack\n"
    "\n"
    "The verdict below is the whole stack's; the per-unit verdict was ship.\n"
    "\n"
    "## Verdict: `polish`\n"
    "\n"
    "findings\n"
)
BY_HAND_REBRIEF = (
    "# Rebrief 1\n"
    "\n"
    "The gate's verdict was HOLD three times; a confident re-cut was tried first.\n"
    "\n"
    "## Verdict: `owner`\n"
    "\n"
    "why\n"
)


class FinishVerdictTests(P1GuardCase):
    """oss-024 U1 · finish needs reviews/end-of-stack.md to say ADVANCE: the guard end-of-stack-review-says-advance (D1, D2)."""

    def given_ready_but_for_the_review(self, review):
        """End of stack with plan_review off and HANDOFF.md, HANDBACK.md written; reviews/end-of-stack.md holds `review` verbatim."""
        self.given_ready_to_finish()
        (self.dir / "reviews/end-of-stack.md").write_text(review)

    @staticmethod
    def doc_rows(prefix):
        """The rows of the generated STATES.md (`doc` prints what `doc --write` stores) that start with `prefix`."""
        doc = subprocess.run([sys.executable, str(TOOL), "doc"], capture_output=True, text=True).stdout
        return [row for row in doc.splitlines() if row.startswith(prefix)]

    # ------------------------------------------------------------ R1 · refused unless the first line is ADVANCE

    def test_finish__refused_when_the_end_of_stack_review_says_hold(self):
        """R1.1 a HOLD end-of-stack review refuses finish and the session stays at end-of-stack — a session would finish on a review that found a defect."""
        self.given_ready_but_for_the_review("HOLD\n\nfindings\n")

        err = self.refusal("end-of-stack-review-says-advance", "finish")

        self.assertIn("reviews/end-of-stack.md first line says HOLD, not ADVANCE", err)
        self.assertEqual(self.run_json()["phase"], "end-of-stack")

    def test_finish__refused_when_the_end_of_stack_review_says_neither_word(self):
        """R1.2 a first line that is neither ADVANCE nor HOLD refuses finish — a placeholder review would pass for a verdict."""
        self.given_ready_but_for_the_review("x\n")

        err = self.refusal("end-of-stack-review-says-advance", "finish")

        self.assertIn("reviews/end-of-stack.md first line says neither ADVANCE nor HOLD, not ADVANCE", err)

    def test_finish__refused_when_the_end_of_stack_review_is_empty(self):
        """R1.3 an empty end-of-stack review refuses finish — a touched file would pass for a review."""
        self.given_ready_but_for_the_review("")

        err = self.refusal("end-of-stack-review-says-advance", "finish")

        self.assertIn("reviews/end-of-stack.md first line says neither ADVANCE nor HOLD, not ADVANCE", err)

    def test_finish__refused_when_a_heading_comes_before_the_verdict(self):
        """R1.4 `# review` above HOLD is the first non-blank line, so the verdict is neither word — a reader that skipped headings would widen the parser the contract fixes."""
        self.given_ready_but_for_the_review("# review\n\nHOLD\n")

        err = self.refusal("end-of-stack-review-says-advance", "finish")

        self.assertIn("reviews/end-of-stack.md first line says neither ADVANCE nor HOLD, not ADVANCE", err)

    def test_finish__refused_when_advance_appears_only_below_a_hold(self):
        """R1.5 only the first non-blank line is the verdict — a HOLD review that quotes ADVANCE in its findings would finish."""
        self.given_ready_but_for_the_review("HOLD\n\nADVANCE once finding 1 is fixed\n")

        err = self.refusal("end-of-stack-review-says-advance", "finish")

        self.assertIn("reviews/end-of-stack.md first line says HOLD, not ADVANCE", err)

    # ------------------------------------------------------------ R2 · accepted in every gate_verdict form of ADVANCE

    def test_finish__accepted_when_the_end_of_stack_review_says_advance(self):
        """R2.1 an ADVANCE end-of-stack review lets finish reach done — every clean session would be stranded at end-of-stack."""
        self.given_ready_but_for_the_review("ADVANCE\n\nfindings\n")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    def test_finish__accepted_when_advance_is_bold(self):
        """R2.2 `**ADVANCE**` is ADVANCE — a reviewer's bold verdict would be read as no verdict."""
        self.given_ready_but_for_the_review("**ADVANCE**\n")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    def test_finish__accepted_when_advance_is_in_backticks(self):
        """R2.3 `` `ADVANCE` `` is ADVANCE — a reviewer's code-spanned verdict would be read as no verdict."""
        self.given_ready_but_for_the_review("`ADVANCE`\n")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    def test_finish__accepted_when_advance_is_lower_case(self):
        """R2.4 `advance` is ADVANCE — the verdict read would be case-sensitive where the gate guards are not."""
        self.given_ready_but_for_the_review("advance\n")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    def test_finish__accepted_when_blank_lines_come_before_advance(self):
        """R2.5 the verdict is the first non-blank line, spaces stripped — a leading blank line would hide an ADVANCE."""
        self.given_ready_but_for_the_review("\n\n  ADVANCE  \n\nfindings\n")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    # ------------------------------------------------------------ R3 · a missing review is named as missing

    def test_finish__names_the_review_missing_rather_than_its_verdict_when_the_file_is_absent(self):
        """R3.1 with no end-of-stack review the refusal is end-of-stack-review-exists — the Lead reading a stop would be told of a verdict that was never written."""
        self.given_ready_to_finish()
        (self.dir / "reviews/end-of-stack.md").unlink()

        err = self.refusal("end-of-stack-review-exists", "finish")

        self.assertNotIn("end-of-stack-review-says-advance", err)

    # ------------------------------------------------------------ R4 · the table decides legality, guards decide acceptance

    def test_status__still_lists_finish_as_legal_while_the_review_says_hold(self):
        """R4.1 finish stays among legal_events at end-of-stack with a HOLD on disk — status would stop telling the Worker which event the HOLD loop ends in."""
        self.given_ready_but_for_the_review("HOLD\n")

        self.assertIn("finish", self.state()["legal_events"])

    # ------------------------------------------------------------ R5 · STATES.md shows the guard

    def test_doc__the_finish_row_lists_the_verdict_guard_after_the_exists_guard(self):
        """R5.1 STATES.md's finish row names end-of-stack-review-says-advance after end-of-stack-review-exists — the drawn machine would not be the enforced one (order, not adjacency: assumed Q1)."""
        rows = self.doc_rows("| `finish` |")

        self.assertEqual(len(rows), 1)
        self.assertIn("`end-of-stack-review-says-advance`", rows[0])
        self.assertLess(rows[0].index("`end-of-stack-review-exists`"), rows[0].index("`end-of-stack-review-says-advance`"))

    def test_doc__the_guards_table_says_the_end_of_stack_review_must_say_advance(self):
        """R5.2 the guards table has the new guard's line saying the verdict is ADVANCE — a refusal's `rule:` line would print nothing."""
        rows = self.doc_rows("| `end-of-stack-review-says-advance` |")

        self.assertEqual(len(rows), 1)
        self.assertIn("its verdict is ADVANCE", rows[0])

    def test_doc__verification_failed_names_the_end_of_stack_review_cap(self):
        """R5.3 the verification-failed stop code covers an end-of-stack review that held max_gate_attempts times — the stop the HOLD loop ends in would have no code that says so."""
        rows = self.doc_rows("| `verification-failed` |")

        self.assertEqual(len(rows), 1)
        self.assertIn("end-of-stack review held", rows[0])


class VerdictLineTests(P1GuardCase):
    """P1 rule 1 · plan-review and rebrief read one verdict line: the first matching ^\\s*#*\\s*Verdict:, backticks, * and spaces stripped."""

    # ------------------------------------------------------------ plan-review-file-has-verdict

    def test_plan_review__refused_ship_when_the_verdict_line_says_rebrief_and_prose_says_ship(self):
        """P1-1.1 Verdict: rebrief, then "the gate verdict was ADVANCE; ship", refuses --verdict ship — a review that found the stack wrong would be recorded as ship."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file_text("Verdict: rebrief\n\nfindings\n\nthe gate verdict was ADVANCE; ship\n")

        self.refusal("plan-review-file-has-verdict", "plan-review", "--verdict", "ship")

    def test_plan_review__refused_ship_when_only_a_second_verdict_line_says_ship(self):
        """P1-1.2 Verdict: rebrief, then a later Verdict: ship line, refuses --verdict ship — any verdict line anywhere would stand for the review's verdict."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file_text("Verdict: rebrief\n\nfindings\n\n## The first review, for the record\n\nVerdict: ship\n")

        self.refusal("plan-review-file-has-verdict", "plan-review", "--verdict", "ship")

    def test_plan_review__refused_when_no_line_starts_with_verdict(self):
        """P1-1.3 a file whose only mention is "The Planner's verdict is ship." is refused — prose would be recorded as a verdict nobody wrote."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file_text("# Plan review\n\nThe Planner's verdict is ship.\n")

        self.refusal("plan-review-file-has-verdict", "plan-review", "--verdict", "ship")

    def test_plan_review__accepts_the_by_hand_backticked_heading_after_prose(self):
        """P1-1.4 `## Verdict: `polish`` after a title and a prose line mentioning verdict is accepted — every by-hand PLAN-REVIEW.md on this machine would be refused."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file_text(BY_HAND_PLAN_REVIEW)

        self.must("plan-review", "--verdict", "polish")

        self.assertEqual(self.run_json()["plan_reviews"][-1]["verdict"], "polish")

    def test_plan_review__refused_the_word_an_earlier_prose_line_uses(self):
        """P1-1.5 the by-hand file's prose says ship, its verdict line says polish: --verdict ship is refused — a polish review would be recorded as ship and finish ungated."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file_text(BY_HAND_PLAN_REVIEW)

        self.refusal("plan-review-file-has-verdict", "plan-review", "--verdict", "ship")

    def test_plan_review__accepts_a_lower_case_verdict_key(self):
        """P1-1.6 a `verdict: ship` line is accepted — the line match is case-insensitive, and a lower-case key would refuse a real verdict."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_file_text("# Plan review\n\nverdict: ship\n")

        self.must("plan-review", "--verdict", "ship")

        self.assertEqual(self.run_json()["plan_reviews"][-1]["verdict"], "ship")

    # ------------------------------------------------------------ rebrief-file-has-verdict

    def test_rebrief__refused_confident_when_only_a_second_verdict_line_says_it(self):
        """P1-1.7 REBRIEF.md Verdict: owner, then a later Verdict: confident, refuses --verdict confident — a rebrief the Planner sent to the Owner would launch as confident."""
        self.given_rebrief_stop("# Rebrief 1\n\nVerdict: owner\n\n## The draft, for the record\n\nVerdict: confident\n")

        self.refusal("rebrief-file-has-verdict", "rebrief", "--verdict", "confident", "--why", "x")

    def test_rebrief__refused_the_word_an_earlier_prose_line_uses(self):
        """P1-1.8 prose mentioning verdict and confident before `## Verdict: `owner`` refuses --verdict confident — the prose would launch a rebrief the Owner owns."""
        self.given_rebrief_stop(BY_HAND_REBRIEF)

        self.refusal("rebrief-file-has-verdict", "rebrief", "--verdict", "confident", "--why", "x")

    def test_rebrief__accepts_the_by_hand_backticked_heading_after_prose(self):
        """P1-1.9 `## Verdict: `owner`` after a title and a prose line mentioning verdict is accepted — every by-hand REBRIEF.md would be refused."""
        self.given_rebrief_stop(BY_HAND_REBRIEF)

        self.must("rebrief", "--verdict", "owner", "--why", "x")

        self.assertEqual(self.run_json()["rebriefs"][-1]["verdict"], "owner")

    def test_rebrief__refused_when_no_line_starts_with_verdict(self):
        """P1-1.10 a REBRIEF.md whose only mention is "My verdict is confident." is refused — prose would launch a rebrief rotation."""
        self.given_rebrief_stop("# Rebrief\n\nMy verdict is confident.\n")

        self.refusal("rebrief-file-has-verdict", "rebrief", "--verdict", "confident", "--why", "x")

    def test_rebrief__accepts_a_bold_verdict_word(self):
        """P1-1.11 `Verdict: **confident**` is accepted — the * strip would be missing and an emphasised verdict refused."""
        self.given_rebrief_stop("# Rebrief\n\nVerdict: **confident**\n")

        self.must("rebrief", "--verdict", "confident", "--why", "x")

        self.assertEqual(self.run_json()["rebriefs"][-1]["verdict"], "confident")


class PolishGateFreshnessTests(P1GuardCase):
    """P1 rule 2 · finish after polish refuses a polish gate older than the newest finish-scope plan_reviews[].at (same second is fresh)."""

    def test_finish__refused_when_the_polish_gate_predates_the_finish_review(self):
        """P1-2.1 polish recorded at 15:30:00+05:30 (epoch 1790416800), gate ADVANCE at 1790416799, is refused with the re-gate message — a gate from before the polish would pass the polish ungated."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("polish")
        self.given_finish_reviews_dated(AT_1000_UTC_AS_IST)
        self.given_polish_gate_at("ADVANCE", EPOCH_1000_UTC - 1)

        err = self.refusal("plan-review-settled", "finish")

        self.assertIn("reviews/polish-gate.md predates the finish review: re-gate the polish", err)

    def test_finish__applied_when_the_polish_gate_is_from_the_same_second(self):
        """P1-2.2 polish recorded at epoch 1790416800, gate ADVANCE at 1790416800, finishes — at is whole seconds, so a gate written right after would be refused as stale."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("polish")
        self.given_finish_reviews_dated(AT_1000_UTC_AS_IST)
        self.given_polish_gate_at("ADVANCE", EPOCH_1000_UTC)

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    def test_finish__refused_when_the_polish_gate_predates_only_the_newest_finish_review(self):
        """P1-2.3 polish at 09:00Z and again at 10:00Z, gate at 09:30Z, is refused — the first polish's gate would pass the second polish ungated."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("polish")
        self.given_plan_review("polish")
        self.given_finish_reviews_dated(AT_0900_UTC, AT_1000_UTC)
        self.given_polish_gate_at("ADVANCE", 1790415000)

        err = self.refusal("plan-review-settled", "finish")

        self.assertIn("reviews/polish-gate.md predates the finish review: re-gate the polish", err)

    def test_finish__a_newer_per_unit_review_does_not_stale_the_polish_gate(self):
        """P1-2.4 finish polish at 09:00Z, gate at 09:30Z, a per-unit ship at 11:00Z: finishes — a unit's review would force a re-gate of a polish it never judged."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("polish")
        self.given_finish_reviews_dated(AT_0900_UTC)
        self.given_hand_edit(lambda run: run["plan_reviews"].append({"n": 2, "at": AT_1100_UTC, "verdict": "ship", "unit": "U1", "path": "PLAN-REVIEW.md"}))
        self.given_polish_gate_at("ADVANCE", 1790415000)

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")

    def test_finish__a_stale_polish_gate_does_not_block_a_ship_verdict(self):
        """P1-2.5 ship at 10:00Z with a leftover polish gate from 09:00Z finishes — the freshness check would block a stack that needed no polish."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("ship")
        self.given_finish_reviews_dated(AT_1000_UTC)
        self.given_polish_gate_at("ADVANCE", EPOCH_0900_UTC)

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")


class PlanReviewModeTests(P1GuardCase):
    """P1 rule 3 · run.json.plan_review is finish, per-unit, off, or missing/null (finish); any other value is refused (021)."""

    # ------------------------------------------------------------ plan-review-on

    def test_plan_review__refused_a_misspelled_plan_review_value(self):
        """P1-3.1 plan_review "finsih" refuses plan-review with the expected-values message — a typo would silently run the review the brief meant to configure."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_value("finsih")
        self.given_plan_review_file("ship")

        err = self.refusal("plan-review-on", "plan-review", "--verdict", "ship")

        self.assertIn("run.json.plan_review is the string 'finsih': expected finish, per-unit or off", err)

    def test_plan_review__refused_a_capitalised_off(self):
        """P1-3.2 plan_review "Off" refuses plan-review — a brief that meant off would record a review it had exempted."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_value("Off")
        self.given_plan_review_file("ship")

        err = self.refusal("plan-review-on", "plan-review", "--verdict", "ship")

        self.assertIn("run.json.plan_review is the string 'Off': " + MODE_REFUSAL, err)

    def test_plan_review__refused_an_empty_plan_review(self):
        """021 B1.5 plan_review "" refuses plan-review with the expected-values message (replaces P1-3.5) — an empty string read as finish would hide a hand edit that meant off."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_value("")
        self.given_plan_review_file("ship")

        err = self.refusal("plan-review-on", "plan-review", "--verdict", "ship")

        self.assertIn("run.json.plan_review is the string '': " + MODE_REFUSAL, err)

    def test_plan_review__refused_a_false_plan_review_naming_the_old_mapping(self):
        """021 B1.1 plan_review false refuses plan-review, naming the boolean and its old meaning — false read as finish runs the review the Owner turned off."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_value(False)
        self.given_plan_review_file("ship")

        err = self.refusal("plan-review-on", "plan-review", "--verdict", "ship")

        self.assert_names_a_non_string(err, "boolean", "false")
        self.assertIn(BOOLEAN_MAPPING, err)

    def test_plan_review__refused_a_true_plan_review_naming_the_old_mapping(self):
        """021 B1.3 plan_review true refuses plan-review, naming the boolean and its old meaning — the refusal printed 'True' and left the Owner to guess why."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_value(True)
        self.given_plan_review_file("ship")

        err = self.refusal("plan-review-on", "plan-review", "--verdict", "ship")

        self.assert_names_a_non_string(err, "boolean", "true")
        self.assertIn(BOOLEAN_MAPPING, err)

    def test_plan_review__refused_a_zero_plan_review(self):
        """021 B1.4 plan_review 0 refuses plan-review, naming the number — 0 read as finish, the same silent inversion as false."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_value(0)
        self.given_plan_review_file("ship")

        err = self.refusal("plan-review-on", "plan-review", "--verdict", "ship")

        self.assert_names_a_non_string(err, "number", "0")
        self.assertNotIn(BOOLEAN_MAPPING, err)

    def test_plan_review__a_null_plan_review_reads_as_finish(self):
        """021 B1.8 plan_review null records the verdict, as a missing key does — a null the tool refused would strand a run.json written with an explicit null."""
        self.given_end_of_stack(plan_review="finish")
        self.given_plan_review_value(None)
        self.given_plan_review_file("ship")

        self.must("plan-review", "--verdict", "ship")

        self.assertEqual(self.run_json()["plan_reviews"][-1]["verdict"], "ship")

    # ------------------------------------------------------------ plan-review-settled

    def test_finish__refused_a_plan_review_value_spelled_with_an_underscore(self):
        """P1-3.3 plan_review "per_unit" with a ship on record refuses finish with the expected-values message — a typo would finish under a mode nobody chose."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("ship")
        self.given_plan_review_value("per_unit")

        err = self.refusal("plan-review-settled", "finish")

        self.assertIn("run.json.plan_review is the string 'per_unit': " + MODE_REFUSAL, err)

    def test_finish__refused_a_capitalised_off(self):
        """P1-3.4 plan_review "Off" with a ship on record refuses finish — "Off" would read as finish, and the brief's intent would never be surfaced."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("ship")
        self.given_plan_review_value("Off")

        err = self.refusal("plan-review-settled", "finish")

        self.assertIn("run.json.plan_review is the string 'Off': " + MODE_REFUSAL, err)

    def test_finish__refused_an_empty_plan_review_for_the_value(self):
        """021 B1.6 plan_review "" with no verdict refuses finish for the value, not the missing verdict (replaces P1-3.6) — the Owner would chase a review the setting may have meant to turn off."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review_value("")

        err = self.refusal("plan-review-settled", "finish")

        self.assertIn("run.json.plan_review is the string '': " + MODE_REFUSAL, err)

    def test_finish__refused_a_false_plan_review_naming_the_old_mapping(self):
        """021 B1.2 plan_review false with a ship on record refuses finish, naming the boolean and its old meaning — a session the Owner exempted would finish as if reviewed."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("ship")
        self.given_plan_review_value(False)

        err = self.refusal("plan-review-settled", "finish")

        self.assert_names_a_non_string(err, "boolean", "false")
        self.assertIn(BOOLEAN_MAPPING, err)

    def test_finish__refused_a_list_plan_review(self):
        """021 B1.7 plan_review ["finish"] with a ship on record refuses finish, naming the array — the refusal printed a Python list and no type."""
        self.given_ready_to_finish(plan_review="finish")
        self.given_plan_review("ship")
        self.given_plan_review_value(["finish"])

        err = self.refusal("plan-review-settled", "finish")

        self.assert_names_a_non_string(err, "array", '["finish"]')

    def test_finish__per_unit_is_an_accepted_plan_review_value(self):
        """P1-3.7 plan_review per-unit with a finish-scope ship finishes — a value check that forgot per-unit would strand every per-unit session."""
        self.given_ready_to_finish(plan_review="per-unit")
        self.given_plan_review("ship")

        self.must("finish")

        self.assertEqual(self.run_json()["phase"], "done")


class StopRebriefTests(SessionCase):
    """R3 · rebrief is a stop code: the finish review's rebrief verdict stops the session (017 U1 · D4)."""

    def test_stop__rebrief_from_end_of_stack_records_the_code_and_the_phase_it_left(self):
        """R3.1 stop --code rebrief from end-of-stack stops with that code, its detail and phase_before end-of-stack — a rebrief verdict would leave the session no legal way to stop."""
        self.given_implementing(unit_ids=("U1",))
        self.given_unit_closed("U1")
        self.must("begin-end-of-stack")

        self.must("stop", "--code", "rebrief", "--detail", "the stack ships a cache the plan never asked for")

        run = self.run_json()
        stop = run["stop_reason"]
        self.assertEqual((run["phase"], stop["code"], stop["detail"], stop["phase_before"]), ("stopped", "rebrief", "the stack ships a cache the plan never asked for", "end-of-stack"))

    def test_stop__rebrief_joins_codes_the_glossary_no_longer_counts(self):
        """R3.2 the unknown-stop-code line in the table and in STATES.md counts no codes — the glossary would say six (or seven) and be wrong the next time a code is added."""
        table = json.loads((HERE.parent / "state-machine.json").read_text())
        doc = subprocess.run([sys.executable, str(TOOL), "doc"], capture_output=True, text=True).stdout

        line = table["illegal_states"]["unknown-stop-code"]
        rows = [row for row in doc.splitlines() if row.startswith("| `unknown-stop-code` |")]

        self.assertEqual(len(rows), 1)
        self.assertNotIn("six", line)
        self.assertNotIn("seven", line)
        self.assertNotIn("six", rows[0])
        self.assertNotIn("seven", rows[0])


class RebaseTests(SessionCase):
    """R4 · rebase: a mid-session rebase with a Lead decision on record, written through the tool (017 U1 · D6).

    The worktree is a scratch git repo beside the session dir, the UnitCloseHeadTests shape: one
    `base` commit (base0), then the session's work on branch `work`. given_upstream_moved adds a
    commit on branch `upstream` from base0; given_rebased_onto replays `work` onto it.
    """

    DECISION = "rebase onto the moved main: 012 added the parser U2 builds on"

    def setUp(self):
        super().setUp()
        self.worktree = Path(self.tmp.name) / "worktree"
        self.dir = Path(self.tmp.name) / "session"
        self.dir.mkdir()
        subprocess.run(["git", "init", "-q", str(self.worktree)], check=True, capture_output=True)
        (self.worktree / "notes.txt").write_text("one\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base0 = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-b", "work")

    # ------------------------------------------------------------ given

    def git(self, *args):
        done = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(self.worktree), *args], check=True, capture_output=True, text=True)
        return done.stdout.strip()

    def commit(self, name):
        (self.worktree / name).write_text(f"{name}\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", name)
        return self.git("rev-parse", "HEAD")

    def given_u1_done(self, **fields):
        self.given_implementing(worktree=str(self.worktree), base_sha=self.base0, **fields)
        self.commit("unit-one.txt")
        self.given_unit_closed("U1")

    def given_upstream_moved(self):
        self.git("checkout", "-q", "-b", "upstream", self.base0)
        upstream = self.commit("upstream.txt")
        self.git("checkout", "-q", "work")
        return upstream

    def given_rebased_onto(self, upstream):
        self.git("rebase", "-q", upstream)
        return self.git("rev-parse", "HEAD")

    # ------------------------------------------------------------ then

    def assert_rebase_refused(self, *flags):
        """Refused whichever guard says so: exit 2, run.json untouched, a refused rebase on the log."""
        before = (self.dir / "run.json").read_text()
        code, _, err = self.tool("rebase", *flags)
        self.assertEqual(code, 2, err)
        self.assertEqual((self.dir / "run.json").read_text(), before)
        last = self.events()[-1]
        self.assertEqual((last["event"], last.get("refused")), ("rebase", True))

    # ------------------------------------------------------------ R4 · applied

    def test_rebase__moves_base_sha_and_records_the_rebase(self):
        """R4.1 rebase rewrites base_sha and appends {n, at, from, to, tip, by, decision}, state kept, check legal — a rebased session keeps measuring its diff from the old base (n assumed Q1)."""
        self.given_u1_done()
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)

        self.must("rebase", "--base", upstream, "--head", tip, "--by", "lead", "--decision", self.DECISION)

        run = self.run_json()
        self.assertEqual(run["base_sha"], upstream)
        self.assertEqual(len(run["rebases"]), 1)
        entry = run["rebases"][0]
        self.assertEqual(sorted(entry), ["at", "by", "decision", "from", "n", "tip", "to"])
        self.assertEqual((entry["n"], entry["from"], entry["to"], entry["tip"], entry["by"], entry["decision"]), (1, self.base0, upstream, tip, "lead", self.DECISION))
        self.assertTrue(entry["at"])
        self.assertEqual((self.state()["state"], self.tool("check")[0]), ("implementing", 0))

    def test_rebase__at_delegation_owner_the_owner_decides_it(self):
        """R4.2 at delegation owner, --by owner is applied and recorded as the Owner's — the generalized decider guard would lock the Owner out too."""
        self.given_u1_done(delegation="owner")
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)

        self.must("rebase", "--base", upstream, "--head", tip, "--by", "owner", "--decision", self.DECISION)

        run = self.run_json()
        self.assertEqual((run["base_sha"], [r["by"] for r in run["rebases"]]), (upstream, ["owner"]))

    def test_rebase__the_event_log_names_the_worker_as_its_actor(self):
        """R4.13 a rebase decided by the Lead is logged with actor Worker, the table's actor for the row — the decider lives in rebases[].by, and a log naming the Lead would say the Lead ran the event."""
        self.given_u1_done()
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)

        self.must("rebase", "--base", upstream, "--head", tip, "--by", "lead", "--decision", self.DECISION)

        record = self.events()[-1]
        self.assertEqual((record["event"], record["actor"], record.get("refused")), ("rebase", "Worker", None))

    def test_rebase__unit_heads_rewrite_each_done_units_head_and_check_stays_legal(self):
        """R4.10 --unit-heads U1=<sha>,U2=<sha> rewrites both done units' heads from end-of-stack, and check is legal after — the recorded heads name commits the rebase replaced, or the digest flags the session."""
        self.given_implementing(worktree=str(self.worktree), base_sha=self.base0)
        self.commit("unit-one.txt")
        self.given_unit_closed("U1")
        self.commit("unit-two.txt")
        self.given_unit_closed("U2")
        self.must("begin-end-of-stack")
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)
        u1 = self.git("rev-parse", "HEAD~1")

        self.must("rebase", "--base", upstream, "--head", tip, "--by", "lead", "--decision", self.DECISION, "--unit-heads", f"U1={u1},U2={tip}")

        self.assertEqual((self.unit("U1")["head"], self.unit("U2")["head"], self.run_json()["base_sha"]), (u1, tip, upstream))
        self.assertEqual((self.state()["state"], self.tool("check")[0]), ("end-of-stack", 0))

    # ------------------------------------------------------------ R4 · refused by a named guard

    def test_rebase__refused_without_a_decision(self):
        """R4.3 no --decision is refused by the decision guard, base_sha untouched — a rebase could move the base with nothing decided (reported name assumed Q3)."""
        self.given_u1_done()
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)

        self.assert_refused("decision", "rebase", "--base", upstream, "--head", tip, "--by", "lead")

    def test_rebase__lead_refused_at_delegation_owner(self):
        """R4.4 --by lead at delegation owner is refused decider-allowed, saying every decision is the Owner's — the Lead would decide a rebase it was never delegated."""
        self.given_u1_done(delegation="owner")
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)
        before = (self.dir / "run.json").read_text()

        code, _, err = self.tool("rebase", "--base", upstream, "--head", tip, "--by", "lead", "--decision", self.DECISION)

        self.assertEqual(code, 2, err)
        self.assertIn(": decider-allowed: ", err)
        self.assertIn("every decision", err)
        self.assertEqual((self.dir / "run.json").read_text(), before)

    def test_rebase__refused_a_base_the_worktree_was_not_rebased_onto(self):
        """R4.5 a base HEAD does not descend from is refused base-given — base_sha would name a commit the session's diff is not built on."""
        self.given_u1_done()
        upstream = self.given_upstream_moved()
        head = self.git("rev-parse", "HEAD")

        self.assert_refused("base-given", "rebase", "--base", upstream, "--head", head, "--by", "lead", "--decision", self.DECISION)

    def test_rebase__refused_a_base_that_names_no_commit(self):
        """R4.6 a well-formed SHA naming nothing in the worktree is refused base-given — base_sha would name a commit no diff can start from."""
        self.given_u1_done()
        head = self.git("rev-parse", "HEAD")

        self.assert_refused("base-given", "rebase", "--base", "7fe8979a", "--head", head, "--by", "lead", "--decision", self.DECISION)

    def test_rebase__refused_when_the_worktree_is_gone(self):
        """R4.7 with run.json.worktree naming no directory, rebase is refused base-given — ancestry cannot be checked, so an unverified base would be written (assumed Q6)."""
        self.given_implementing(worktree=str(Path(self.tmp.name) / "torn-down-worktree"), base_sha=self.base0)
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)

        self.assert_refused("base-given", "rebase", "--base", upstream, "--head", tip, "--by", "lead", "--decision", self.DECISION)

    def test_rebase__refused_a_head_that_names_no_commit(self):
        """R4.8 a tip naming nothing in the worktree is refused head-given — rebases[] would record a tip no reviewer can resolve."""
        self.given_u1_done()
        upstream = self.given_upstream_moved()
        self.given_rebased_onto(upstream)

        self.assert_refused("head-given", "rebase", "--base", upstream, "--head", "7fe8979a", "--by", "lead", "--decision", self.DECISION)

    def test_rebase__refused_from_a_stopped_session(self):
        """R4.9 rebase from stopped is refused from-state — a stop would be walked around by rewriting its base instead of resuming."""
        self.given_u1_done()
        self.given_stopped("base-moved")
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)

        self.assert_refused("from-state", "rebase", "--base", upstream, "--head", tip, "--by", "lead", "--decision", self.DECISION)

    # ------------------------------------------------------------ R4 · --unit-heads refused

    def test_rebase__refused_a_unit_heads_pair_naming_a_unit_that_is_not_done(self):
        """R4.11 --unit-heads naming a todo unit is refused, its head untouched — a head would be written for a unit no gate passed (guard name assumed Q7)."""
        self.given_u1_done()
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)

        self.assert_rebase_refused("--base", upstream, "--head", tip, "--by", "lead", "--decision", self.DECISION, "--unit-heads", f"U2={tip}")

    def test_rebase__refused_a_unit_heads_pair_whose_sha_is_not_a_commit(self):
        """R4.12 --unit-heads U1=<sha naming nothing> is refused, U1's head untouched — a done unit's head would name no commit (guard name assumed Q7)."""
        self.given_u1_done()
        upstream = self.given_upstream_moved()
        tip = self.given_rebased_onto(upstream)

        self.assert_rebase_refused("--base", upstream, "--head", tip, "--by", "lead", "--decision", self.DECISION, "--unit-heads", "U1=7fe8979a")


class DigestTests(SessionCase):
    """R5 · the guarded digest is unchanged: plan_review, plan_reviews and rebases stay outside it (017 U1 · D7)."""

    # digests() as it read at the 017 base, and what that tool returned for RUN below; inlined so the suite needs no history.
    BASE_SOURCE = (
        "def digests(run):\n"
        "    core = {k: run.get(k) for k in (\"phase\", \"stop_reason\", \"rotate\")}\n"
        "    core[\"rebriefs\"] = run.get(\"rebriefs\") or []\n"
        "    return {\"core\": _sha(core), \"units\": _sha(unit_rows(run))}\n"
    )
    BASE_DIGESTS = {"core": "07a77550b166798e", "units": "a0b28a62944506be"}
    # Every guarded field set, plus the keys 017 adds; distinct values so a crossed wire shows.
    RUN = {
        "phase": "end-of-stack",
        "stop_reason": None,
        "rotate": {"requested_at": "2026-09-20T10:00:00+00:00", "resumed_at": "2026-09-20T10:05:00+00:00", "next_unit": "U2", "reason": "context"},
        "rebriefs": [{"n": 1, "at": "2026-09-19T09:00:00+00:00", "by": "planner", "verdict": "confident", "why": "units re-cut", "stop_code": "one-way-door"}],
        "units": [{"id": "U1", "status": "done", "gate_attempts": 2, "head": "7fe8979a"}, {"id": "U2", "status": "done", "gate_attempts": 1, "head": "0123abc"}],
        "base_sha": "a1b2c3d4",
        "plan_review": "finish",
        "plan_reviews": [{"n": 1, "at": "2026-09-21T11:00:00+00:00", "verdict": "ship", "unit": None, "path": "PLAN-REVIEW.md"}],
        "rebases": [{"n": 1, "at": "2026-09-20T12:00:00+00:00", "from": "a1b2c3d4", "to": "b2c3d4e5", "tip": "c3d4e5f6", "by": "lead", "decision": "rebase onto main"}],
    }

    def tool_now(self):
        spec = importlib.util.spec_from_file_location("session_state_now", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_digests__source_is_byte_identical_to_the_base(self):
        """R5.1 digests() reads exactly as at the 017 base — a changed digest flags every finished session edited-outside-tool."""
        now = self.tool_now()

        self.assertEqual(inspect.getsource(now.digests), self.BASE_SOURCE)

    def test_digests__a_run_carrying_the_new_keys_digests_as_at_the_base(self):
        """R5.2 a run.json with plan_review, plan_reviews and rebases digests exactly as the 017 base's tool digests it — a helper the digest reads could still pull a new key in."""
        now = self.tool_now()

        self.assertEqual(now.digests(self.RUN), self.BASE_DIGESTS)

    def test_digests__the_new_keys_edited_by_hand_leave_check_legal(self):
        """R5.3 plan_review, plan_reviews and rebases rewritten by hand leave check legal — guarding them would flag every session written before 017 edited-outside-tool."""
        self.given_implementing(unit_ids=("U1",))
        self.given_unit_closed("U1")
        self.must("begin-end-of-stack")
        self.given_hand_edit(lambda run: run.update(plan_review="per-unit", plan_reviews=self.RUN["plan_reviews"], rebases=self.RUN["rebases"]))

        code, out, _ = self.tool("check")

        self.assertEqual(code, 0, out)


class RunTemplateTests(SessionCase):
    """R6 · the run.json template starts every brief with the finish review on and nothing recorded (017 U1 · D8)."""

    def test_template__carries_the_finish_review_on_and_nothing_recorded(self):
        """R6.1 templates/run.json carries plan_review finish, plan_reviews [] and rebases [] — a fresh brief would silently skip the finish review or start with a stale record."""
        template = json.loads(TEMPLATE.read_text())

        self.assertEqual((template.get("plan_review"), template.get("plan_reviews"), template.get("rebases")), ("finish", [], []))


class IntakeDrawingTests(SessionCase):
    """R7 · the intake drawing shows the finish review before intake, and STATES.md is regenerated (017 U1 · D11)."""

    @staticmethod
    def reachable(machine, start):
        seen, todo = set(), [start]
        while todo:
            here = todo.pop()
            for t in machine["transitions"]:
                if here in t["from"] and t["to"] not in seen:
                    seen.add(t["to"])
                    todo.append(t["to"])
        return seen

    def test_intake_drawing__plan_reviewed_comes_before_intake_written(self):
        """R7.1 plan-reviewed leads to intake-written and never follows it — the drawing would still show the review running after intake, which 017 moved into the session (exact edges assumed Q9)."""
        table = json.loads((HERE.parent / "state-machine.json").read_text())
        intake = [m for m in table["machines"] if m["id"] == "intake"][0]

        self.assertIn("intake-written", self.reachable(intake, "plan-reviewed"))
        self.assertNotIn("plan-reviewed", self.reachable(intake, "intake-written"))

    def test_doc__check_prints_that_states_md_matches_the_table(self):
        """R7.2 doc --check exits 0 and prints `STATES.md matches the table` — the generated doc would draw a machine the tool no longer enforces."""
        done = subprocess.run([sys.executable, str(TOOL), "doc", "--check"], capture_output=True, text=True)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("STATES.md matches the table", done.stdout.splitlines())


class SessionInputTests(SessionCase):
    """Values a session can write reach the hooks and the integrity check only in the shape this
    install gives them (tests/run-launch/BEHAVIORS.md, SI rows)."""

    def hook_env(self, sessions_root):
        return dict(os.environ, ROBOWRIGHT_SESSIONS_ROOT=str(sessions_root))

    def stop_gate(self, sessions_root):
        """The Stop hook from an armed worktree; returns what it printed."""
        worktree = self.dir / "wt"
        (worktree / ".claude").mkdir(parents=True, exist_ok=True)
        (worktree / ".claude" / "autonomous-run").write_text(str(self.dir) + "\n")
        done = subprocess.run(["bash", str(STOP_GATE)], input=json.dumps({"cwd": str(worktree)}), capture_output=True, text=True, env=self.hook_env(sessions_root))
        return done.stdout

    def blocked(self, printed):
        return bool(printed.strip()) and json.loads(printed).get("decision") == "block"

    def test_check__flags_the_model_edited_by_hand(self):
        """SI-5: the launcher writes run.json's model into the next session's flags, so a hand edit to it is flagged like phase is, at the brief and at a unit."""
        edits = {
            "model": lambda run: run.update(model="sonnet"),
            "units[].model": lambda run: run["units"][1].update(model="sonnet"),
        }
        for field, edit in edits.items():
            with self.subTest(field):
                self.given_implementing(model="opus")
                self.given_hand_edit(edit)
                code, out, _ = self.tool("check")
                self.assertEqual(code, 1, out)
                self.assertIn("edited-outside-tool: model", out)

    def test_check__a_newest_event_from_before_the_model_digest_is_not_flagged(self):
        """SI-6: an event log written before the model was guarded carries no model digest; reading its absence as a change would flag every session in flight."""
        self.given_implementing(model="opus")
        path = self.dir / "events.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            for key in ("model", "unit_models"):
                (row.get("digest") or {}).pop(key, None)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        code, out, _ = self.tool("check")
        self.assertEqual(code, 0, out)

    def test_stop_gate__a_counter_that_is_not_a_number_counts_as_zero(self):
        """SI-7: the counter file is session-writable and the hook runs outside the sandbox, so its count is never evaluated: `5+0` would read as five and `x{` would not read at all."""
        self.given_implementing()
        root = self.dir.parent
        self.assertTrue(self.blocked(self.stop_gate(root)))
        counter = self.dir / ".stop-gate-count"
        fingerprint = counter.read_text().split()[0]
        for count in ("5+0", "x{"):
            with self.subTest(count=count):
                counter.write_text(f"{fingerprint} {count}\n")
                self.assertTrue(self.blocked(self.stop_gate(root)))
                self.assertEqual(counter.read_text(), f"{fingerprint} 1\n")
        # A leading zero is still a decimal count: 08 is eight blocks, so the ninth releases.
        counter.write_text(f"{fingerprint} 08\n")
        self.assertFalse(self.blocked(self.stop_gate(root)))
        self.assertEqual(counter.read_text(), f"{fingerprint} 9\n")

    def test_stop_gate__the_sessions_root_comes_from_launch_json_when_the_environment_names_none(self):
        """SI-14: an install names its sessions root in launch.json, `~/` and a symlinked path included, and sets no environment variable; a root the hook could not read there would leave every worker hook silent."""
        self.given_implementing()
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home)
        (home / "sessions").symlink_to(self.dir.parent, target_is_directory=True)
        (home / ".claude/robowright").mkdir(parents=True)
        (home / ".claude/robowright/launch.json").write_text(json.dumps({"sessions_root": "~/sessions"}))
        worktree = self.dir / "wt"
        (worktree / ".claude").mkdir(parents=True, exist_ok=True)
        (worktree / ".claude" / "autonomous-run").write_text(str(self.dir) + "\n")
        env = {k: v for k, v in os.environ.items() if k != "ROBOWRIGHT_SESSIONS_ROOT"}
        done = subprocess.run(["bash", str(STOP_GATE)], input=json.dumps({"cwd": str(worktree)}), capture_output=True, text=True, env=dict(env, HOME=str(home)))
        self.assertTrue(self.blocked(done.stdout), done.stderr)

    def test_stop_gate__a_marker_naming_a_session_dir_outside_the_sessions_root_arms_nothing(self):
        """SI-14: the marker sits in the session's own worktree, so it could point the hooks' writes at any directory holding a run.json."""
        self.given_implementing()
        elsewhere = self.dir / "other-root"
        elsewhere.mkdir()
        self.assertEqual(self.stop_gate(elsewhere), "")
        self.assertFalse((self.dir / ".stop-gate-count").exists())
        self.assertTrue(self.blocked(self.stop_gate(self.dir.parent)))



SESSION_WRITE = HERE / "session_write.py"
OWNER_TEXT = "the Owner's file\n"


class SessionWriteTests(SessionCase):
    """SW rows (tests/run-launch/BEHAVIORS.md): the hooks and the state tool write into the session dir outside the
    sandbox, so never through an entry the session planted there."""

    def setUp(self):
        super().setUp()
        self.outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.outside)

    def planted(self, name, text=OWNER_TEXT):
        """`name` in the session dir as a symlink to a scratch file outside it holding `text`, or to a missing path
        when `text` is None; returns the target."""
        target = self.outside / ("target-" + name.lstrip("."))
        if text is not None:
            target.write_text(text)
        link = self.dir / name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target)
        return target

    def hook(self, script):
        worktree = self.dir / "wt"
        (worktree / ".claude").mkdir(parents=True, exist_ok=True)
        (worktree / ".claude" / "autonomous-run").write_text(str(self.dir) + "\n")
        return subprocess.run(["bash", str(script)], input=json.dumps({"cwd": str(worktree), "trigger": "auto"}),
                              capture_output=True, text=True, env=self.marker_env())

    def given_rotation_requested(self):
        self.given_implementing()
        self.given_unit_closed("U1")
        self.must("request-rotate")

    def ledger_added(self, before):
        path = self.dir / "LEDGER.md"
        return (path.read_text() if path.exists() else "")[len(before):]

    def helper(self, mode, path, text="new line\n"):
        return subprocess.run([sys.executable, str(SESSION_WRITE), mode, str(path)], input=text, capture_output=True,
                              text=True, timeout=10)

    def snapshot(self):
        return {name: (self.dir / name).read_bytes() for name in ("run.json", "events.jsonl")}

    def test_stop_gate__never_writes_its_counter_through_a_planted_link(self):
        """SW-1: the counter is rewritten on every blocked turn end, outside the sandbox."""
        self.given_implementing()
        target = self.planted(".stop-gate-count")
        done = self.hook(STOP_GATE)
        self.assertEqual(json.loads(done.stdout)["decision"], "block", done.stderr)
        self.assertEqual(target.read_text(), OWNER_TEXT)
        self.assertTrue((self.dir / ".stop-gate-count").is_symlink())

    def test_stop_gate__never_appends_its_rotation_line_through_a_planted_link(self):
        """SW-2: the rotation release appends to LEDGER.md with no Owner action at all."""
        self.given_rotation_requested()
        target = self.planted("LEDGER.md")
        done = self.hook(STOP_GATE)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, ""), done.stderr)
        self.assertEqual(target.read_text(), OWNER_TEXT)

    def test_hooks__a_dangling_ledger_link_creates_nothing(self):
        """SW-3: a link to a missing path would otherwise create the Owner's file wherever it names."""
        self.given_rotation_requested()
        target = self.planted("LEDGER.md", text=None)
        self.hook(STOP_GATE)
        self.hook(PRECOMPACT)
        self.assertFalse(target.exists())

    def test_precompact__never_appends_through_a_planted_link(self):
        """SW-4: the compaction stamp is the PreCompact hook's one write."""
        self.given_implementing()
        target = self.planted("LEDGER.md")
        done = self.hook(PRECOMPACT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(target.read_text(), OWNER_TEXT)

    def test_stop_gate__rotate_requested_at_reaches_the_ledger_only_as_an_iso_time(self):
        """SW-5: rotate.requested_at is session-written and the Stop hook runs no integrity check; a newline in it
        would put a whole line of the session's choosing in the ledger."""
        self.given_rotation_requested()
        for requested, quoted in (("2026-10-15T01:02:03+00:00", True), ("2026-10-15T01:02:03+00:00\nSECOND LINE", False)):
            with self.subTest(requested=requested):
                self.given_hand_edit(lambda run: run["rotate"].update(requested_at=requested))
                before = self.ledger_added("")
                self.hook(STOP_GATE)
                added = self.ledger_added(before)
                self.assertEqual(added.count("\n"), 1, added)
                self.assertNotIn("SECOND LINE", added)
                if quoted:
                    self.assertIn("(requested 2026-10-15T01:02:03+00:00)", added)

    def test_stop_gate__the_stuck_line_is_one_line_whatever_phase_says(self):
        """SW-6: phase reaches the release-after-six line, and a hand edit can put a newline in it."""
        self.given_implementing()
        self.given_hand_edit(lambda run: run.update(phase="implement\nSECOND LINE"))
        self.hook(STOP_GATE)
        counter = self.dir / ".stop-gate-count"
        counter.write_text(counter.read_text().split()[0] + " 5\n")
        done = self.hook(STOP_GATE)
        self.assertEqual(done.stdout.strip(), "", done.stderr)
        added = self.ledger_added("")
        self.assertEqual(added.count("\n"), 1, added)
        self.assertNotIn("SECOND LINE", added)

    def test_state_tool__never_truncates_or_writes_through_a_planted_lock_link(self):
        """SW-7: accept runs outside the sandbox through accept.sh, and the lock was opened for writing before any guard."""
        self.given_implementing()
        target = self.planted(".session-state.lock")
        before = self.snapshot()
        for event in (("accept", "--head", "7fe8979a"), ("unit-start", "--unit", "U1")):
            with self.subTest(event=event[0]):
                code, _, err = self.tool(*event)
                self.assertEqual(code, 2, err)
                self.assertIn(".session-state.lock", err)
                self.assertEqual(target.read_text(), OWNER_TEXT)
                self.assertEqual(self.snapshot(), before)

    def test_state_tool__never_appends_an_event_through_a_planted_link(self):
        """SW-8: the event log is the state tool's other write; a link there passes the integrity check when its
        target holds the real log."""
        self.given_implementing()
        log = (self.dir / "events.jsonl").read_text()
        target = self.planted("events.jsonl", text=log)
        run = (self.dir / "run.json").read_bytes()
        code, _, err = self.tool("unit-start", "--unit", "U1")
        self.assertEqual(code, 2, err)
        self.assertIn("events.jsonl", err)
        self.assertEqual(target.read_text(), log)
        self.assertEqual((self.dir / "run.json").read_bytes(), run)

    def test_session_write__refuses_every_target_but_a_regular_file_with_one_link(self):
        """SW-14: a symlink, a dangling one, a FIFO, a hard link, a directory and a linked parent are each refused
        by path, and nothing is created, changed or truncated; the FIFO does not block the writer."""
        target = self.outside / "target"
        linked_dir = self.outside / "linked-dir"
        linked_dir.mkdir()
        cases = {
            "symlink": lambda p: p.symlink_to(target),
            "dangling": lambda p: p.symlink_to(self.outside / "missing"),
            "fifo": lambda p: os.mkfifo(p),
            "hard link": lambda p: os.link(target, p),
            "directory": lambda p: p.mkdir(),
        }
        for mode in ("append", "replace", "check"):
            for name, plant in cases.items():
                with self.subTest(mode=mode, target=name):
                    target.write_text(OWNER_TEXT)
                    path = self.dir / f"{mode}-{name.replace(' ', '-')}"
                    plant(path)
                    done = self.helper(mode, path)
                    self.assertEqual(done.returncode, 2, done.stderr)
                    self.assertIn(path.name, done.stderr)
                    self.assertEqual(target.read_text(), OWNER_TEXT)
                    self.assertFalse((self.outside / "missing").exists())
            with self.subTest(mode=mode, target="linked parent"):
                parent = self.dir / f"{mode}-parent"
                parent.symlink_to(linked_dir)
                done = self.helper(mode, parent / "LEDGER.md")
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertEqual(list(linked_dir.iterdir()), [])

    def test_session_write__appends_and_replaces_a_plain_file(self):
        """SW-15: the writes the sites make still happen on a plain file, and a check creates nothing."""
        path = self.dir / "LEDGER.md"
        self.assertEqual(self.helper("check", path).returncode, 0)
        self.assertFalse(path.exists())
        self.assertEqual(self.helper("append", path, "a\n").returncode, 0)
        self.assertEqual(self.helper("append", path, "b\n").returncode, 0)
        self.assertEqual(path.read_text(), "a\nb\n")
        self.assertEqual(self.helper("replace", path, "c\n").returncode, 0)
        self.assertEqual(path.read_text(), "c\n")

    def test_session_write__read_refuses_every_path_but_an_unlinked_regular_file(self):
        """SW-22: accept.sh's message and the Owner tools' robowright.json are read through `read`; each planted
        shape is refused by path with nothing on stdout, and the FIFO does not block the reader."""
        target = self.dir / "outside" / "target"
        target.parent.mkdir()
        target.write_text(OWNER_TEXT)
        (self.dir / "real" / "inner").mkdir(parents=True)
        (self.dir / "real" / "inner" / "file").write_text(OWNER_TEXT)
        (self.dir / "linked").symlink_to(self.dir / "real")
        cases = {
            "link in a parent folder": (lambda p: None, self.dir / "linked" / "inner" / "file"),
            "symlink": (lambda p: p.symlink_to(target), None),
            "fifo": (lambda p: os.mkfifo(p), None),
            "hard link": (lambda p: os.link(target, p), None),
            "directory": (lambda p: p.mkdir(), None),
            "64 KiB + 1": (lambda p: p.write_bytes(b"x" * (64 * 1024 + 1)), None),
            "missing": (lambda p: None, None),
        }
        for name, (plant, given) in cases.items():
            with self.subTest(target=name):
                path = given or self.dir / f"read-{name.replace(' ', '-')}"
                plant(path)
                started = time.monotonic()
                done = subprocess.run([sys.executable, str(SESSION_WRITE), "read", str(path)], capture_output=True,
                                      timeout=10)
                self.assertLess(time.monotonic() - started, 5)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertEqual(done.stdout, b"")
                self.assertTrue(done.stderr.startswith(b"refused: "), done.stderr)
                self.assertIn(path.name.encode(), done.stderr)
        for spelled in ("relative/file", f"{self.dir}/./real/inner/file", f"{self.dir}/real/../real/inner/file",
                        f"{self.dir}//real/inner/file"):
            with self.subTest(path=spelled):
                done = subprocess.run([sys.executable, str(SESSION_WRITE), "read", spelled], capture_output=True,
                                      timeout=10)
                self.assertEqual((done.returncode, done.stdout), (2, b""), done.stderr)
                self.assertTrue(done.stderr.startswith(b"refused: "), done.stderr)

    def test_session_write__read_prints_a_plain_file_as_it_is(self):
        """SW-23: the reads the sites make still happen, up to the 64 KiB limit."""
        for name, data in (("small", b"subject\n\nbody \xe2\x80\x94 kept\n"), ("limit", b"y" * (64 * 1024))):
            with self.subTest(file=name):
                path = self.dir / name
                path.write_bytes(data)
                done = subprocess.run([sys.executable, str(SESSION_WRITE), "read", str(path)], capture_output=True,
                                      timeout=10)
                self.assertEqual((done.returncode, done.stdout), (0, data), done.stderr)


class NeverLaunchedTests(SessionCase):
    """056-S rows (skills/lead/scripts/BEHAVIORS.md): `never_launched()` tells a session nothing launched from a
    preflight that is running or died, on the stored fields the launcher and the tool write."""

    def setUp(self):
        super().setUp()
        spec = importlib.util.spec_from_file_location("session_state_never_launched", TOOL)
        self.state = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.state)

    def never_launched(self, is_live=False):
        run = json.loads((self.dir / "run.json").read_text())
        return self.state.never_launched(self.state.load_table(), run, self.dir, is_live)

    def test_never_launched__true_for_a_briefed_session_nothing_touched(self):
        """056-S1 — a brief nothing launched is never launched — the roster and the dashboard read it as dead work."""
        self.given_session()
        self.assertIs(self.never_launched(), True)

    def test_never_launched__false_while_a_live_session_runs_preflight(self):
        """056-S2 — a live session in preflight is launched — a running preflight reads as a brief waiting on the Owner."""
        self.given_session()
        self.assertIs(self.never_launched(is_live=True), False)

    def test_never_launched__false_once_the_launcher_pinned_a_session(self):
        """056-S3 — a pinned session id means a launch happened — a launch that died in preflight is never resumed (assumed Q1)."""
        self.given_session(session_id="aaaa1111-2222-3333-4444-555566667777")
        self.assertIs(self.never_launched(), False)

    def test_never_launched__false_once_the_launcher_pinned_a_transcript(self):
        """056-S4 — a pinned transcript means a launch happened — as S3 when the registry gave no id (assumed Q1)."""
        self.given_session(transcripts=["~/.claude/projects/-sample/aaaa1111.jsonl"])
        self.assertIs(self.never_launched(), False)

    def test_never_launched__false_once_a_start_time_is_stamped(self):
        """056-S5 — a start time means preflight ran — a resumed-to-preflight session reads as never launched (assumed Q1)."""
        self.given_session(started_at="2026-10-18T09:00:00+00:00")
        self.assertIs(self.never_launched(), False)

    def test_never_launched__false_once_any_event_is_logged(self):
        """056-S6 — any line in the event log means the tool ran on it — a Worker's refused first event reads as no launch."""
        self.given_session()
        (self.dir / "events.jsonl").write_text(json.dumps({"n": 1, "event": "preflight-pass", "refused": True}) + "\n")
        self.assertIs(self.never_launched(), False)

    def test_never_launched__false_past_the_briefed_state(self):
        """056-S7 — only the briefed state can be unlaunched — an intake session with its pin lost reads as a fresh brief."""
        self.given_session(phase="intake")
        self.assertIs(self.never_launched(), False)


if __name__ == "__main__":
    unittest.main()
