#!/usr/bin/env python3
"""Tests for the Robowright dashboard, `tools/robowright-dash.py`, driven through its command line against a
scratch $HOME, scratch roots and a scratch cwd. Rows are named for `BEHAVIORS.md`; the kill for each test is in
`TEST-LEDGER.md`.

    python3 tests/dash/test_dash.py

Nothing here reads the real ~/.claude, a real sessions root, a real accounting root or a real plan-usage reading:
every run gets a scratch $HOME, and ROBOWRIGHT_SESSIONS_ROOT, ROBOWRIGHT_PROJECTS_ROOT, ROBOWRIGHT_ACCOUNTING_ROOT
and CLAUDE_USAGE_DIR are stripped unless a test sets them. Tests that need git build a scratch repo under the scratch dir, never the clone.
"""

import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "tools" / "robowright-dash.py"
GAPS_NAME = "robowright-dash.gaps.json"
ROOT_VARS = ("ROBOWRIGHT_SESSIONS_ROOT", "ROBOWRIGHT_PROJECTS_ROOT", "ROBOWRIGHT_ACCOUNTING_ROOT")
# Where run-cost.py's plan_usage() looks for the status-line tap's reading before ~/.claude/usage.
USAGE_VAR = "CLAUDE_USAGE_DIR"
# A branch prefix other than `robowright/`: R6.2 proves a merged branch under it never reads as complete.
OLD_NAME = "legacy"
REFUSAL_PREFIX = "run-roster.py: no sessions root:"
HOLD_PHRASE = "Waiting on the Lead's owner brief"
SLUG = "sample-001-first"
QUIET_MINUTES = 5

PROJECT_MD = """# Sample

One scratch project for the dashboard's tests.

## Task Breakdown

| # | Unit | Description | Repo | Size | Complexity | Status |
|---|---|---|---|---|---|---|
| U1 | `{unit}` | The sample's first unit | sample | S | low | in progress |
"""


def iso(dt):
    return dt.isoformat(timespec="seconds")


def tools_snapshot():
    """Every file under the clone's tools/ with its mtime, so a test can tell nothing was added or rewritten there."""
    return {str(p.relative_to(REPO)): p.stat().st_mtime_ns for p in (REPO / "tools").rglob("*") if p.is_file()}


def unit_line(stdout, unit_id):
    """The detailed summary's line for one Task Breakdown row, or "" when there is none."""
    return next((line for line in stdout.splitlines() if line.split()[:1] == [unit_id]), "")


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# ---------------------------------------------------------------- U2 fixtures: Summary cells, the ledger, finished cards

COST = REPO / "skills" / "robowright" / "scripts" / "robowright-cost.py"
TEMPLATE = REPO / "skills" / "planner" / "PROJECT-TEMPLATE.md"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SECOND = "sample-002-second"
# P3: a brief with a dollar limit, so a spend line carries its estimate (run-roster.py's usage_cell rule). The
# U2 and P1 spend rows run under it; P3's rows strip it where the rule needs a brief without one.
DOLLAR_BRIEF = {"spend_threshold_usd": 25}

# D6's Task Breakdown header, and the header every PROJECT.md had before it.
SUMMARY_HEADER = "| # | Unit | Summary | Tracker | Description | Exploration Doc | Size | Complexity | Status |"
OLD_HEADER = "| # | Unit | Tracker | Description | Exploration Doc | Size | Complexity | Status |"
SUMMARY = "Totals the sample's spend per unit."
DESCRIPTION = "Parser rewrite behind a flag"
SUMMARY_ROW = f"| U1 | `first` | {SUMMARY} | ENG-7 | {DESCRIPTION} | docs/first.md | M | medium | in progress |"
EMPTY_SUMMARY_ROW = f"| U1 | `first` |  | ENG-7 | {DESCRIPTION} | docs/first.md | M | medium | in progress |"
# Well-formed under OLD_HEADER; under SUMMARY_HEADER it is one cell short, so every cell from the third on is
# shifted one column left: Summary reads `ENG-7`, Description reads `docs/first.md`.
OLD_ROW = f"| U1 | `first` | ENG-7 | {DESCRIPTION} | docs/first.md | M | medium | in progress |"
SECOND_OLD_ROW = "| U2 | `second` | ENG-8 | The sample's second unit | docs/second.md | S | low | in progress |"
SHORT_ROW_ERROR = "PROJECT.md row has 8 cells, the header has 9"

# Owner briefs, in the shape of skills/explainer/templates/OWNER-BRIEF.md: `## Decide now` is a table whose first
# cell is the ask, and the next `## ` section carries a table of its own that is not an ask.
ASK_FLAG = "Should the sample ship behind a flag?"
ASK_EXPORT = "Keep the old export path for one release?"
KEY_DECISION = "Parse the Task Breakdown by column name"
BRIEF_HEAD = """# Owner brief — U1 first

Written by the Explainer from the session record. **Cap:** 400 words · **Count:** 212 by `wc -w`.

## Decide now

What only the Owner can answer before accepting this. "Nothing" is a valid answer; say so.

"""
BRIEF_TAIL = f"""
## Key decisions

| decision | by | alternative passed over, and why | cites |
|---|---|---|---|
| {KEY_DECISION} | Lead | by position — shifts on a short row | `LEDGER.md` § U1 |

## Where the detail lives

- `INTAKE.md` — the session folder
- `PLAN-REVIEW.md` — not run
"""
BRIEF_TABLE_ASKS = BRIEF_HEAD + f"""| ask | the Planner's recommendation | cites |
|---|---|---|
| {ASK_FLAG} | Yes; the flag costs one line | `PLAN-REVIEW.md` § Risk |
| {ASK_EXPORT} | No; nothing reads it | `INTAKE.md` § 8 |
""" + BRIEF_TAIL
BRIEF_BULLET_ASKS = BRIEF_HEAD + f"- {ASK_FLAG}\n- {ASK_EXPORT}\n" + BRIEF_TAIL
BRIEF_NO_ASKS = BRIEF_HEAD + "| ask | the Planner's recommendation | cites |\n|---|---|---|\n" + BRIEF_TAIL
# P1: the template's "Nothing" answer, as a table row and as a bullet beside a real ask; and exactly one real ask.
BRIEF_NOTHING_ROW = BRIEF_HEAD + """| ask | the Planner's recommendation | cites |
|---|---|---|
| Nothing | — | — |
""" + BRIEF_TAIL
BRIEF_NONE_BULLET_AND_ONE_ASK = BRIEF_HEAD + f"- None.\n- {ASK_FLAG}\n" + BRIEF_TAIL
BRIEF_ONE_ASK = BRIEF_HEAD + f"""| ask | the Planner's recommendation | cites |
|---|---|---|
| {ASK_EXPORT} | No; nothing reads it | `INTAKE.md` § 8 |
""" + BRIEF_TAIL

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def project_md(header, *rows):
    """A PROJECT.md for project `sample` whose Task Breakdown is `header` and `rows`."""
    rule = "|---" * (len(split_cells(header))) + "|"
    return ("# Sample\n\nOne scratch project for the dashboard's tests.\n\n## Task Breakdown\n\n"
            + "\n".join([header, rule, *rows]) + "\n")


def split_cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def ledger_record(unit, role, session_id, requests, output_tokens, estimated_usd, active_seconds, scope="session",
                  unit_id=None, session_dir="", project="sample", model="claude-sonnet-4-5"):
    """One line of <accounting root>/records.jsonl in run-cost.py's shape. The figures a spend line shows are the
    arguments; every other count is incidental, distinct and non-zero."""
    return {"scope": scope, "at": "2026-09-20T10:00:00-07:00", "source": "hook", "project": project, "unit": unit,
            "unit_id": unit_id, "role": role, "model": model, "session_id": session_id, "session_dir": str(session_dir),
            "transcripts_pinned": False, "requests": requests, "input_tokens": 41_017, "output_tokens": output_tokens,
            "cache_read_tokens": 903_011, "cache_write_tokens": 70_013, "avg_context_tokens": 97_019,
            "estimated_usd": estimated_usd, "price_as_of": "2026-09-01", "wall_seconds": active_seconds + 613,
            "active_seconds": active_seconds, "plan_5h_pct": 12, "plan_7d_pct": 3, "plan_captured_at": None}


def text_of(stdout):
    """The text summary with any ANSI colour stripped."""
    return ANSI.sub("", stdout)


def unit_and_next_line(stdout, unit_id):
    """The detailed summary's line for one Task Breakdown row and the line under it, where its purpose may sit."""
    lines = text_of(stdout).splitlines()
    index = next((i for i, line in enumerate(lines) if line.split()[:1] == [unit_id]), None)
    return "" if index is None else "\n".join(lines[index:index + 2])


class Page(HTMLParser):
    """One page `--once` wrote, as the Owner reads it: its visible text, and every element with its classes and the
    session card (`<details class="sess" id="s-<slug>">`) it sits in, and whether it carries `open` (a <details> the page
    starts expanded). Text is whitespace-collapsed with one space between pieces, so figures in adjacent elements never
    run together; <script> and <style> are not text."""

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.elements, self.stack, self.pieces, self.hidden = [], [], [], 0
        self.feed(Path(path).read_text())
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag in VOID_TAGS:
            return
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        card = attrs.get("id") if tag == "details" and "sess" in classes else (self.stack[-1]["card"] if self.stack else None)
        element = {"tag": tag, "classes": classes, "id": attrs.get("id"), "card": card, "open": "open" in attrs,
                   "pieces": []}
        self.elements.append(element)
        self.stack.append(element)
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_startendtag(self, tag, attrs):
        return

    def handle_endtag(self, tag):
        if not any(element["tag"] == tag for element in self.stack):
            return
        while self.stack:
            element = self.stack.pop()
            if element["tag"] in ("script", "style"):
                self.hidden -= 1
            if element["tag"] == tag:
                break

    def handle_data(self, data):
        if self.hidden:
            return
        self.pieces.append(data)
        for element in self.stack:
            element["pieces"].append(data)

    @staticmethod
    def joined(pieces):
        return " ".join(" ".join(pieces).split())

    def text(self):
        return self.joined(self.pieces)

    def card(self, slug):
        """The text of `slug`'s session card, or "" when the page has none."""
        return next((self.joined(el["pieces"]) for el in self.elements if el["tag"] == "details" and el["id"] == f"s-{slug}"), "")

    def is_open(self, id_):
        """Whether the page's <details id=`id_`> starts open; None when the page has no such element."""
        return next((el["open"] for el in self.elements if el["tag"] == "details" and el["id"] == id_), None)

    def texts(self, cls, card=None, outside_cards=False):
        """The text of every element carrying class `cls` — only those inside `card`'s session card when it is given,
        only those in no session card when `outside_cards`."""
        return [self.joined(el["pieces"]) for el in self.elements if cls in el["classes"]
                and (card is None or el["card"] == f"s-{card}") and not (outside_cards and el["card"])]


HARDENING = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "log.showSignature=false"]
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


class DashScratch(unittest.TestCase):
    """A scratch $HOME with launch.json at <HOME>/.claude/robowright/launch.json, scratch roots and a scratch cwd for
    every run, so a relative or unexpanded root lands somewhere the test can see — never the real ~."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Resolved, so a path the script prints is the path the test compares against (macOS's temp dir sits under
        # /var, a link to /private/var).
        self.base = Path(os.path.realpath(tmp.name))
        self.home = self.base / "home"
        self.home.mkdir()
        self.cwd = self.base / "cwd"
        self.cwd.mkdir()
        self.launch_json = self.home / ".claude" / "robowright" / "launch.json"
        self.roots = self.base / "roots"
        self.sessions = self.roots / "sessions"
        self.projects = self.roots / "projects"
        self.out = self.base / "out"

    # ------------------------------------------------------------ given

    def given_launch_settings(self, **settings):
        self.launch_json.parent.mkdir(parents=True, exist_ok=True)
        self.launch_json.write_text(json.dumps(settings) + "\n")

    def given_allowlisted(self, *repos):
        """launch.json's `repos`, beside whatever launch.json already holds: the repositories the Owner trusts."""
        settings = json.loads(self.launch_json.read_text()) if self.launch_json.is_file() else {}
        self.given_launch_settings(**dict(settings, repos=[str(r) for r in repos]))

    def given_launch_roots(self):
        """launch.json naming the scratch sessions root and projects root, both existing."""
        self.sessions.mkdir(parents=True, exist_ok=True)
        self.projects.mkdir(parents=True, exist_ok=True)
        self.given_launch_settings(sessions_root=str(self.sessions), projects_root=str(self.projects))

    def given_project(self, root=None, unit="first", name="sample"):
        """Project `name` (`sample` by default) under `root` (the scratch projects root by default): one Task Breakdown
        row, U1 `unit`."""
        folder = Path(root or self.projects) / name
        folder.mkdir(parents=True)
        (folder / "PROJECT.md").write_text(PROJECT_MD.format(unit=unit))
        return folder

    def given_session(self, root=None, slug=SLUG, phase="implement", intake=False, **fields):
        """A session dir under `root` (the scratch sessions root by default): implementing U1 of two, every file in it
        last written QUIET_MINUTES ago — a working session with a recent write, so the dashboard records its quiet."""
        run_dir = Path(root or self.sessions) / slug
        run_dir.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        run = {
            "ticket": slug,
            "phase": phase,
            "stop_reason": None,
            "rotate": None,
            "rebriefs": [],
            "units": [{"id": "U1", "status": "done"}, {"id": "U2", "status": "todo"}],
            "started_at": iso(now - timedelta(hours=2)),
            "updated_at": iso(now - timedelta(minutes=QUIET_MINUTES)),
        }
        run.update(fields)
        (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        if intake:
            (run_dir / "INTAKE.md").write_text("# Intake\n")
        written = time.time() - QUIET_MINUTES * 60
        for path in run_dir.iterdir():
            os.utime(path, (written, written))
        return run_dir

    def given_finished_session(self, **fields):
        """SLUG done and through the Lead's intake (INTAKE.md present), all its units done."""
        return self.given_session(phase="done", intake=True, units=[{"id": "U1", "status": "done"}], **fields)

    def given_worktree_not_in_main(self):
        """A plain directory standing in for a session's worktree: it exists, and no branch in it is in any main."""
        worktree = self.base / "worktrees" / SLUG
        worktree.mkdir(parents=True)
        return worktree

    def given_settings(self, folder, name, settings):
        (folder / name).write_text(json.dumps(settings) + "\n")

    def given_owner_brief(self, folder):
        reviews = folder / "reviews"
        reviews.mkdir(exist_ok=True)
        (reviews / f"{SLUG}-owner-brief.md").write_text("# Owner brief\n")

    def given_live_agent(self, name, status, cwd, registry=None, pid=None):
        """One row of Claude Code's live-session registry, `<registry>/<n>.json` — the scratch HOME's `.claude/sessions`
        unless the test names another directory: `name`, `status` (`busy` or `idle`), `cwd`, started ten minutes ago in
        epoch milliseconds. Its `pid` is this test runner's own, alive for the dashboard's run, unless the test gives
        another."""
        registry = Path(registry or self.home / ".claude" / "sessions")
        registry.mkdir(parents=True, exist_ok=True)
        row = {"pid": os.getpid() if pid is None else pid, "name": name, "status": status, "cwd": str(cwd),
               "startedAt": int((time.time() - 10 * 60) * 1000)}
        path = registry / f"{len(list(registry.glob('*.json'))) + 1}.json"
        path.write_text(json.dumps(row) + "\n")
        return path

    def given_repo(self, branch, merged):
        """A scratch repo on `main` with one commit, and `branch` one commit ahead of it — fast-forwarded into main
        when `merged`."""
        repo = self.base / "repos" / "sample"
        repo.mkdir(parents=True)
        self.git(repo, "init", "-q", "-b", "main")
        (repo / "README.md").write_text("sample\n")
        self.git(repo, "add", "README.md")
        self.git(repo, "commit", "-q", "-m", "base")
        self.git(repo, "checkout", "-q", "-b", branch)
        (repo / "first.txt").write_text("the first unit\n")
        self.git(repo, "add", "first.txt")
        self.git(repo, "commit", "-q", "-m", "first")
        self.git(repo, "checkout", "-q", "main")
        if merged:
            self.git(repo, "merge", "-q", "--ff-only", branch)
        return repo

    def git(self, repo, *args):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Sample Owner", "-c", "user.email=owner@example.invalid",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, env=self.env(), timeout=30)

    # ------------------------------------------------------------ when

    def env(self, env_sessions=None, env_projects=None, env_accounting=None, env_usage=None, env_tz=None):
        """The scratch $HOME; each ROBOWRIGHT_*_ROOT, and $CLAUDE_USAGE_DIR, only when the test sets it; $TZ set to
        `env_tz` when the test gives one, so a clock time the dashboard prints is in a zone the test chose."""
        env = {key: value for key, value in os.environ.items() if key not in (*ROOT_VARS, USAGE_VAR)}
        # PYTHONDONTWRITEBYTECODE: the dashboard's imports from skills/ leave no __pycache__ in the clone.
        # GIT_CEILING_DIRECTORIES: git never walks up out of the scratch dir looking for a repo.
        env.update(HOME=str(self.home), COLUMNS="1000", NO_COLOR="1", PYTHONDONTWRITEBYTECODE="1",
                   GIT_CEILING_DIRECTORIES=str(self.base), GIT_CONFIG_NOSYSTEM="1")
        for name, value in zip((*ROOT_VARS, USAGE_VAR), (env_sessions, env_projects, env_accounting, env_usage)):
            if value is not None:
                env[name] = str(value)
        if env_tz is not None:
            env["TZ"] = env_tz
        return env

    def run_dash(self, *args, script=DASH, timeout=60, **env_roots):
        """The dashboard as a subprocess, from the scratch cwd."""
        return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                              env=self.env(**env_roots), cwd=str(self.cwd), timeout=timeout)

    def pages(self):
        """Every page `--once` wrote, html-unescaped and joined, so a phrase reads as the Owner sees it."""
        return html.unescape("".join(p.read_text() for p in sorted(self.out.glob("*.html"))))

    def serve_and_get_once(self, port, **env_roots):
        """`--serve PORT`, one GET of `/` once it answers, then stopped: (the GET's status or None, stderr)."""
        server = subprocess.Popen([sys.executable, str(DASH), "--serve", str(port)], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, text=True, env=self.env(**env_roots), cwd=str(self.cwd))
        self.addCleanup(lambda: server.poll() is None and server.kill())
        status = None
        deadline = time.monotonic() + 20
        while status is None and server.poll() is None and time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=20) as response:
                    response.read()
                    status = response.status
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        if server.poll() is None:
            server.terminate()
        try:
            _, err = server.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            _, err = server.communicate()
        return status, err


# ---------------------------------------------------------------- R1 · summary from launch.json's roots


class Summary(DashScratch):

    def test_prints_the_project_and_its_live_session__when_launch_json_names_both_roots(self):
        """R1.1 — the summary comes from launch.json's roots — the dashboard shows nothing, or someone else's work."""
        self.given_launch_roots()
        self.given_project()
        self.given_session()

        result = self.run_dash()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"(?m)^sample: ")
        self.assertIn([SLUG, "implement"], [line.split()[:2] for line in result.stdout.splitlines()])

    def test_reads_home_relative_roots__when_launch_json_names_them_with_a_tilde(self):
        """R1.2 — `~/` roots are $HOME's — a launch.json written as the launcher writes it finds nothing (assumed Q5)."""
        home_sessions = self.home / "roots" / "sessions"
        self.given_project(self.home / "roots" / "projects")
        self.given_session(home_sessions)
        self.given_launch_settings(sessions_root="~/roots/sessions", projects_root="~/roots/projects")

        result = self.run_dash()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"(?m)^sample: ")
        self.assertIn([SLUG, "implement"], [line.split()[:2] for line in result.stdout.splitlines()])


# ---------------------------------------------------------------- R2 · refuses by name when no sessions root is named


class Refusal(DashScratch):

    def test_refuses_with_the_rosters_line_and_exit_2__when_nothing_names_a_sessions_root(self):
        """R2.1 — no sessions root is refused with the roster's own line — the dashboard guesses a private path."""
        result = self.run_dash()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(),
                         f"{REFUSAL_PREFIX} set sessions_root in {self.launch_json} (no such file), "
                         "or set $ROBOWRIGHT_SESSIONS_ROOT, or pass --runs-root")

    def test_refuses__when_launch_json_names_only_a_projects_root(self):
        """R2.2 — a projects root is not a sessions root — the dashboard reads sessions from the wrong place."""
        self.projects.mkdir(parents=True)
        self.given_launch_settings(projects_root=str(self.projects))

        result = self.run_dash()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(),
                         f"{REFUSAL_PREFIX} set sessions_root in {self.launch_json} "
                         "(sessions_root is missing, empty or not a string), "
                         "or set $ROBOWRIGHT_SESSIONS_ROOT, or pass --runs-root")

    def test_refuses_and_writes_no_pages__when_once_runs_with_no_sessions_root(self):
        """R2.3 — `--once` refuses like the summary — it writes pages of an empty or guessed world."""
        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith(REFUSAL_PREFIX), result.stderr)
        self.assertFalse((self.out / "index.html").exists())


# ---------------------------------------------------------------- R3 · which root wins


class SessionsRootPrecedence(DashScratch):

    def setUp(self):
        super().setUp()
        self.flag_sessions = self.base / "flag-sessions"
        self.env_sessions = self.base / "env-sessions"
        self.given_session(self.flag_sessions, "sample-001-from-flag")
        self.given_session(self.env_sessions, "sample-002-from-env")
        self.given_session(self.sessions, "sample-003-from-launch")
        self.given_launch_roots()

    def test_reads_the_flag_sessions_root__over_the_env_and_launch_json(self):
        """R3.1 — `--runs-root` beats the env and launch.json — the flag cannot point the dashboard anywhere else."""
        result = self.run_dash("--runs-root", str(self.flag_sessions), env_sessions=self.env_sessions)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sample-001-from-flag", result.stdout)
        self.assertNotIn("sample-002-from-env", result.stdout)
        self.assertNotIn("sample-003-from-launch", result.stdout)

    def test_reads_the_env_sessions_root__over_launch_json(self):
        """R3.2 — $ROBOWRIGHT_SESSIONS_ROOT beats launch.json — a per-shell root is ignored.

        Declared guard: the order lives in run-roster.py's sessions_roots; this protects the dashboard from
        resolving its sessions root itself and reading launch.json before the environment."""
        result = self.run_dash(env_sessions=self.env_sessions)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sample-002-from-env", result.stdout)
        self.assertNotIn("sample-003-from-launch", result.stdout)


class ProjectsRootPrecedence(DashScratch):
    """Every candidate root holds a project `sample` whose one unit is named for the root; the detailed summary of
    `sample` prints that unit's name, so the name says which root was read."""

    def setUp(self):
        super().setUp()
        self.sessions.mkdir(parents=True)
        self.flag_projects = self.base / "flag-projects"
        self.env_projects = self.base / "env-projects"
        self.launch_projects = self.base / "launch-projects"

    def test_reads_the_flag_projects_root__over_the_env(self):
        """R3.3 — `--projects-root` beats $ROBOWRIGHT_PROJECTS_ROOT — the flag cannot point the dashboard anywhere else."""
        self.given_project(self.flag_projects, unit="from-flag")
        self.given_project(self.env_projects, unit="from-env")
        self.given_project(self.launch_projects, unit="from-launch")
        self.given_launch_settings(sessions_root=str(self.sessions), projects_root=str(self.launch_projects))

        result = self.run_dash("sample", "--projects-root", str(self.flag_projects), env_projects=self.env_projects)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("from-flag", result.stdout)
        self.assertNotIn("from-env", result.stdout)

    def test_reads_the_env_projects_root__over_launch_json(self):
        """R3.4 — $ROBOWRIGHT_PROJECTS_ROOT beats launch.json's projects_root — a per-shell root is ignored."""
        self.given_project(self.env_projects, unit="from-env")
        self.given_project(self.launch_projects, unit="from-launch")
        self.given_launch_settings(sessions_root=str(self.sessions), projects_root=str(self.launch_projects))

        result = self.run_dash("sample", env_projects=self.env_projects)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("from-env", result.stdout)
        self.assertNotIn("from-launch", result.stdout)

    def test_reads_launch_json_projects_root__over_the_sessions_roots_parent(self):
        """R3.5 — launch.json's projects_root beats the sessions root's parent — a configured root is ignored."""
        self.given_project(self.launch_projects, unit="from-launch")
        self.given_project(self.roots, unit="from-parent")
        self.given_launch_settings(sessions_root=str(self.sessions), projects_root=str(self.launch_projects))

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("from-launch", result.stdout)
        self.assertNotIn("from-parent", result.stdout)

    def test_reads_the_sessions_roots_parent__when_nothing_names_a_projects_root(self):
        """R3.6 — the sessions root's parent is the last default — a launch.json naming one root finds no project."""
        self.given_project(self.roots, unit="from-parent")
        self.given_launch_settings(sessions_root=str(self.sessions))

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("from-parent", result.stdout)

    def test_reads_the_flag_sessions_roots_parent__when_only_runs_root_is_given(self):
        """R3.7 — the parent of a `--runs-root` root is the default too — a flag-only run finds no project."""
        flag_roots = self.base / "flag-roots"
        (flag_roots / "sessions").mkdir(parents=True)
        self.given_project(flag_roots, unit="from-parent")

        result = self.run_dash("sample", "--runs-root", str(flag_roots / "sessions"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("from-parent", result.stdout)


# ---------------------------------------------------------------- R4 · the gaps file lives under the accounting root


class GapsFile(DashScratch):

    def test_writes_the_gaps_file_under_the_accounting_root__when_once_writes_pages(self):
        """R4.1 — `--once` keeps the quiet record under the accounting root — it lands beside the script, in the clone."""
        self.given_launch_roots()
        self.given_project()
        self.given_session()
        accounting = self.base / "accounting"
        accounting.mkdir()
        before = tools_snapshot()

        result = self.run_dash("--once", str(self.out), env_accounting=accounting)

        self.assertEqual(result.returncode, 0, result.stderr)
        gaps = json.loads((accounting / GAPS_NAME).read_text())
        self.assertIn(SLUG, gaps)
        self.assertGreaterEqual(gaps[SLUG], QUIET_MINUTES)
        self.assertEqual(tools_snapshot(), before)

    def test_writes_the_gaps_file_under_the_accounting_root__when_served_and_polled_once(self):
        """R4.2 — `--serve` keeps the quiet record under the accounting root — it lands beside the script, in the clone."""
        self.given_launch_roots()
        self.given_project()
        self.given_session()
        accounting = self.base / "accounting"
        accounting.mkdir()
        before = tools_snapshot()

        status, err = self.serve_and_get_once(free_port(), env_accounting=accounting)

        self.assertEqual(status, 200, err)
        gaps = json.loads((accounting / GAPS_NAME).read_text())
        self.assertIn(SLUG, gaps)
        self.assertEqual(tools_snapshot(), before)

    def test_writes_no_gaps_file_anywhere__when_no_accounting_root_is_named(self):
        """R4.3 — no accounting root means the record stays in memory — a stray file appears beside the script or the pages."""
        self.given_project(self.roots)
        self.given_session()
        before = tools_snapshot()

        result = self.run_dash("--once", str(self.out), "--runs-root", str(self.sessions))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(self.base.rglob(GAPS_NAME)), [])
        self.assertEqual(tools_snapshot(), before)

    def test_writes_the_gaps_file_beside_the_sessions_root__when_launch_json_names_only_that(self):
        """R4.4 — the accounting root defaults to `accounting` beside launch.json's sessions root — the record is lost."""
        self.given_launch_settings(sessions_root=str(self.sessions))
        self.given_project(self.roots)
        self.given_session()
        (self.roots / "accounting").mkdir()

        result = self.run_dash()

        self.assertEqual(result.returncode, 0, result.stderr)
        gaps = json.loads((self.roots / "accounting" / GAPS_NAME).read_text())
        self.assertIn(SLUG, gaps)

    def test_writes_no_gaps_file_into_the_cwd__when_no_accounting_root_is_named(self):
        """H3 — no accounting root never means the cwd — every shell the dashboard runs from collects a gaps file."""
        self.given_project(self.roots)
        self.given_session()

        result = self.run_dash("--runs-root", str(self.sessions))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(SLUG, result.stdout)
        self.assertFalse((self.cwd / GAPS_NAME).exists())

    def test_writes_no_bytecode_for_the_scripts_it_loads__when_python_would_cache_them(self):
        """R4.5 — the clone is read-only in fact (D3) — a __pycache__ appears beside run-roster.py and run-cost.py."""
        self.given_project(self.roots)
        self.given_session()
        cache = self.base / "pycache"
        env = {**self.env(), "PYTHONPYCACHEPREFIX": str(cache)}
        del env["PYTHONDONTWRITEBYTECODE"]

        result = subprocess.run([sys.executable, str(DASH), "--runs-root", str(self.sessions)], capture_output=True,
                                text=True, env=env, cwd=str(self.cwd), timeout=60)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p for p in cache.rglob("*.pyc") if str(REPO.resolve()) in str(p)], [])


# ---------------------------------------------------------------- R5 · the owner-brief hold


class OwnerBriefHold(DashScratch):
    """launch.json naming both roots; project `sample`; SLUG done, through intake, its worktree not in main — so the
    only thing that can still hold it for the Lead is the owner brief."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.folder = self.given_project()
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

    def test_holds_a_finished_session_for_the_owner_brief__when_robowright_json_asks_for_one(self):
        """R5.1 — owner_brief holds a finished session for the Lead — the Owner is handed work with no brief (assumed Q9)."""
        self.given_settings(self.folder, "robowright.json", {"owner_brief": True})

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HOLD_PHRASE, self.pages())

    def test_releases_the_session__when_its_owner_brief_exists(self):
        """R5.2 — the owner brief releases the hold — a briefed session stays with the Lead forever (assumed Q9)."""
        self.given_settings(self.folder, "robowright.json", {"owner_brief": True})
        self.given_owner_brief(self.folder)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / "index.html").is_file())
        self.assertNotIn(HOLD_PHRASE, self.pages())

    def test_holds_the_session__when_robowright_json_uses_the_review_guide_alias(self):
        """R5.3 — review_guide still asks for the brief — older projects hand the Owner work with no brief (assumed Q9)."""
        self.given_settings(self.folder, "robowright.json", {"review_guide": True})

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HOLD_PHRASE, self.pages())

    def test_does_not_hold_the_session__when_owner_brief_is_false_beside_the_alias(self):
        """R5.5 — owner_brief, when present, wins over review_guide — the Owner cannot turn the hold off (assumed Q9)."""
        self.given_settings(self.folder, "robowright.json", {"owner_brief": False, "review_guide": True})

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / "index.html").is_file())
        self.assertNotIn(HOLD_PHRASE, self.pages())


# ---------------------------------------------------------------- R6 · in main on robowright/<slug>


class InMain(DashScratch):
    """launch.json naming both roots; project `sample`; SLUG done and through intake, its worktree a scratch repo."""

    def given_finished_session_in_repo(self, branch, merged, configured=True, allowlisted=True):
        self.given_launch_roots()
        folder = self.given_project()
        self.repo = self.given_repo(branch, merged)
        if configured:
            self.given_settings(folder, "robowright.json", {"repos": [{"name": "sample", "path": str(self.repo)}]})
        if allowlisted:
            self.given_allowlisted(self.repo)
        self.given_finished_session(worktree=str(self.repo))

    def run_dash_recording_git(self, *args):
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").write_text(RECORDING_GIT)
        (bin_dir / "git").chmod(0o755)
        log = self.base / "git-argv.log"
        env = dict(self.env(), PATH=f"{bin_dir}:{os.environ['PATH']}", GIT_ARGV_LOG=str(log))
        result = subprocess.run([sys.executable, str(DASH), *args], capture_output=True, text=True, env=env,
                                cwd=str(self.cwd), timeout=60)
        return result, git_calls(log)

    def test_reads_the_unit_awaiting_acceptance_and_runs_no_git_in_it__when_no_configured_repository_lists_the_worktree(self):
        """R6.4 — a merged branch in a checkout no robowright.json names is not read as complete, and no git runs inside it — its config and fsmonitor would run as the Owner on every render."""
        self.given_finished_session_in_repo(f"robowright/{SLUG}", merged=True, configured=False)

        result, calls = self.run_dash_recording_git("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("awaiting acceptance", unit_line(result.stdout, "U1"))
        self.assertEqual([c for c in calls if runs_in(c, self.repo)], [])

    def test_a_robowright_json_under_a_runs_root_given_by_flag_is_not_configuration(self):
        """R6.6 — with --runs-root naming a sessions root launch.json does not, a robowright.json a session writes there names no configured repository, and no git runs in that repository — a session's own repository and its config would be trusted (review 2 F1)."""
        self.given_finished_session_in_repo(f"robowright/{SLUG}", merged=True, configured=False)
        flag_root = self.projects / "flag-sessions"
        shutil.move(str(self.sessions), str(flag_root))
        (flag_root / "robowright.json").write_text(json.dumps({"repos": [{"name": "x", "path": str(self.repo)}]}))

        result, calls = self.run_dash_recording_git("--runs-root", str(flag_root), "sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("awaiting acceptance", unit_line(result.stdout, "U1"))
        self.assertEqual([c for c in calls if runs_in(c, self.repo)], [])

    def test_reads_the_unit_awaiting_acceptance_and_runs_no_git_in_it__when_launch_json_repos_does_not_list_the_repository(self):
        """R6.7 — a merged branch in a repository robowright.json names but launch.json's `repos` does not list is not read as complete, and no git runs inside it — a session's robowright.json would put its own repository's config in the Owner's every render (N-1)."""
        self.given_finished_session_in_repo(f"robowright/{SLUG}", merged=True, allowlisted=False)
        self.given_allowlisted(self.base / "another-clone")

        result, calls = self.run_dash_recording_git("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("awaiting acceptance", unit_line(result.stdout, "U1"))
        self.assertEqual([c for c in calls if runs_in(c, self.repo)], [])

    def test_names_the_key_the_file_and_the_line_to_add__when_launch_json_has_no_repos(self):
        """R6.8 — with launch.json holding no `repos`, the text summary's stderr and every page's footer name `repos`, the file and the `"repos": [...]` line holding the named repository — the dashboard would quietly stop reading every worktree."""
        self.given_finished_session_in_repo(f"robowright/{SLUG}", merged=True, allowlisted=False)
        line = f'"repos": [{json.dumps(str(self.repo))}]'

        result = self.run_dash("sample")
        written = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("repos-unconfigured", result.stderr)
        self.assertIn(str(self.launch_json), result.stderr)
        self.assertIn(line, result.stderr)
        self.assertEqual(written.returncode, 0, written.stderr)
        for page in sorted(self.out.glob("*.html")):
            with self.subTest(page=page.name):
                footer = html.unescape(page.read_text().split('<footer id="foot">', 1)[1])
                self.assertIn(str(self.launch_json), footer)
                self.assertIn(line, footer)

    def test_every_git_call_in_a_listed_worktree_carries_the_overrides(self):
        """R6.5 — each git the dashboard runs in a listed worktree starts with the fsmonitor, hooksPath, pager and showSignature overrides — a call without them runs the worktree's configured programs as the Owner."""
        self.given_finished_session_in_repo(f"robowright/{SLUG}", merged=True)

        result, calls = self.run_dash_recording_git("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("complete", unit_line(result.stdout, "U1"))
        inside = [c for c in calls if runs_in(c, self.repo)]
        self.assertTrue(inside, calls)
        for call in inside:
            self.assertEqual(call[:len(HARDENING)], HARDENING, call)

    def test_reads_the_unit_complete__when_its_robowright_branch_is_in_main(self):
        """R6.1 — a session branch in main reads complete — work in main shows as still awaiting acceptance."""
        self.given_finished_session_in_repo(f"robowright/{SLUG}", merged=True)

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("complete", unit_line(result.stdout, "U1"))

    def test_reads_the_unit_awaiting_acceptance__when_only_an_old_prefix_branch_is_in_main(self):
        """R6.2 — only the `robowright/` branch is tried — a merged branch under another prefix that ends in the slug passes for work in main."""
        self.given_finished_session_in_repo(f"{OLD_NAME}/{SLUG}", merged=True)

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        line = unit_line(result.stdout, "U1")
        self.assertIn("awaiting acceptance", line)
        self.assertNotIn("complete", line)

    def test_reads_the_unit_awaiting_acceptance__when_its_robowright_branch_is_not_in_main(self):
        """R6.3 — a branch not in main is not complete — work awaiting acceptance drops off the Owner's list."""
        self.given_finished_session_in_repo(f"robowright/{SLUG}", merged=False)

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("awaiting acceptance", unit_line(result.stdout, "U1"))


# ---------------------------------------------------------------- 039 · in main only on positive evidence


BRANCH = f"robowright/{SLUG}"
# A git that fails, as on a broken repository, whenever it is asked whether a `robowright/` branch exists.
BROKEN_BRANCH_GIT = f"""#!/bin/sh
for a in "$@"; do case "$a" in refs/heads/robowright/*) exit 128;; esac; done
exec {shutil.which("git")} "$@"
"""


class InMainTruth(DashScratch):
    """039 — launch.json naming both roots; project `sample`, whose robowright.json names one scratch repository that
    launch.json's `repos` lists unless a test says otherwise. A finished build is in main only on positive evidence."""

    run_dash_recording_git = InMain.run_dash_recording_git

    # ------------------------------------------------------------ given

    def given_trusted_repo(self, merged=False, allowlisted=True):
        """The scratch repository with `robowright/<SLUG>` one commit ahead of main, merged when `merged`."""
        self.given_launch_roots()
        self.folder = self.given_project()
        self.repo = self.given_repo(BRANCH, merged)
        self.given_settings(self.folder, "robowright.json", {"repos": [{"name": "sample", "path": str(self.repo)}]})
        if allowlisted:
            self.given_allowlisted(self.repo)

    def given_outside_worktree(self, branch=BRANCH, slug=SLUG):
        """A worktree of the scratch repository on `branch`, outside its `.worktrees`, as a worktree the Owner made by hand outside the repository is."""
        worktree = self.base / "elsewhere" / slug
        self.git(self.repo, "worktree", "add", "-q", str(worktree), branch)
        return worktree

    def given_change_description(self):
        prs = self.folder / "prs"
        prs.mkdir(exist_ok=True)
        (prs / f"{SLUG}.md").write_text("# Change description\n")

    def given_torn_down(self, worktree):
        """What teardown does after an accept: the worktree removed, then the branch deleted."""
        self.git(self.repo, "worktree", "remove", "--force", str(worktree))
        self.git(self.repo, "branch", "-D", BRANCH)

    # ------------------------------------------------------------ then

    def assert_unit_reads(self, label):
        result = self.run_dash("sample")
        self.assertEqual(result.returncode, 0, result.stderr)
        line = unit_line(result.stdout, "U1")
        self.assertIn(label, line)
        if label != "complete":
            self.assertNotIn("complete", line)

    # ------------------------------------------------------------ direct builds

    def test_reads_a_finished_direct_build_with_the_lead__when_its_worktree_is_outside_claude_worktrees_and_its_session_has_exited(self):
        """039-L1 — a change description, no live session, and a worktree on `robowright/<slug>` under another directory reads with the Lead, not complete — the 2026-10-15 dashboard showed three builds not in main as in main."""
        self.given_trusted_repo()
        self.given_outside_worktree()
        self.given_change_description()

        self.assert_unit_reads("with the Lead")

    def test_reads_a_finished_direct_build_complete__when_its_branch_is_gone_from_every_trusted_repository(self):
        """039-L2 — the same build after teardown removed its worktree and deleted its branch reads complete — teardown deletes the branch only after an accept, so accepted work would sit on the Lead's list forever."""
        self.given_trusted_repo()
        worktree = self.given_outside_worktree()
        self.given_change_description()
        self.given_torn_down(worktree)

        self.assert_unit_reads("complete")

    def test_reads_a_finished_direct_build_working__when_its_outside_worktree_holds_uncommitted_work(self):
        """039-L11 — a change description, no live session, and an uncommitted file in its worktree on `robowright/<slug>` outside `.worktrees` reads working — a worktree found only by the session's cwd or `.worktrees` is never checked for work the build has not committed."""
        self.given_trusted_repo()
        worktree = self.given_outside_worktree()
        self.given_change_description()
        (worktree / "unfinished.txt").write_text("not committed yet\n")

        self.assert_unit_reads("working")

    def test_never_reads_a_direct_build_complete__when_it_has_no_change_description(self):
        """039-L3 — a build whose branch is gone but whose prs/ holds only its records folder, no change description, reads working — a build abandoned before it was described would pass for work in main."""
        self.given_trusted_repo()
        self.git(self.repo, "branch", "-D", BRANCH)
        (self.folder / "prs" / SLUG).mkdir(parents=True)

        self.assert_unit_reads("working")

    def test_reads_a_direct_build_working__when_its_session_is_in_shell(self):
        """039-L5 — a change description, and its Worker `shell` (its turn idle while a background suite runs), reads working — U38 showed as with the Lead while its final suite still ran."""
        self.given_trusted_repo()
        worktree = self.given_outside_worktree()
        self.given_change_description()
        self.given_live_agent(f"build-{SLUG}", "shell", cwd=worktree)

        self.assert_unit_reads("working")

    def test_never_reads_a_direct_build_complete_nor_runs_git_in_it__when_launch_json_repos_does_not_list_its_repository(self):
        """039-L6 — with the repository robowright.json names absent from launch.json's `repos`, a finished build on `robowright/<slug>` there reads with the Lead and no git runs in the repository or the worktree — U36's gate; an untrusted repository's config would run as the Owner."""
        self.given_trusted_repo(allowlisted=False)
        self.given_allowlisted(self.base / "another-clone")
        worktree = self.given_outside_worktree()
        self.given_change_description()

        result, calls = self.run_dash_recording_git("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        line = unit_line(result.stdout, "U1")
        self.assertIn("with the Lead", line)
        self.assertNotIn("complete", line)
        self.assertEqual([c for c in calls if runs_in(c, self.repo) or runs_in(c, worktree)], [])

    def test_never_reads_a_direct_build_complete__when_its_branch_is_gone_only_from_the_repositories_it_may_read(self):
        """039-L7 — a finished build whose project names a repository launch.json's `repos` does not list stays with the Lead though no trusted repository holds its branch — the branch may live in the repository nobody may read."""
        self.given_trusted_repo(allowlisted=False)
        self.given_allowlisted(self.base / "another-clone")
        worktree = self.given_outside_worktree()
        self.given_change_description()
        self.given_torn_down(worktree)

        self.assert_unit_reads("with the Lead")

    def test_runs_no_git_with_the_slug_and_never_reads_it_complete__when_a_direct_build_is_named_what_no_branch_can_be(self):
        """039-L12 — a change description `sample-001-first.lock.md` (no branch can end `.lock`) in a trusted project: no git call carries the name, and its card is the Lead's (`sess intake`), not complete — git would answer "no such branch", which reads as torn down after an accept."""
        self.given_trusted_repo()
        hostile = f"{SLUG}.lock"
        (self.folder / "prs").mkdir()
        (self.folder / "prs" / f"{hostile}.md").write_text("# Change description\n")

        result, calls = self.run_dash_recording_git("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c for c in calls if any(hostile in arg for arg in c)], [])
        card = re.search(r'<details class="sess (\w+)" id="s-sample-001-first-lock"', (self.out / "sample.html").read_text())
        self.assertIsNotNone(card)
        self.assertEqual(card.group(1), "intake")

    # ------------------------------------------------------------ launched sessions

    def test_reads_a_launched_session_complete__when_run_json_accepted_is_set(self):
        """039-L4 — `run.json.accepted` reads complete though its worktree is a directory no repository lists — accept.sh's own record is the strongest evidence there is."""
        self.given_trusted_repo()
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()),
                                    accepted={"sha": "0" * 40, "at": "2026-10-15T10:00:00+00:00"})

        self.assert_unit_reads("complete")

    def test_reads_a_launched_session_awaiting_acceptance__when_only_the_old_landed_key_is_set(self):
        """043-D3 — a session whose run.json holds `landed` and not `accepted` reads awaiting acceptance — the old key read as a fallback leaves two words for one act on disk, and the migration's misses go unseen."""
        self.given_trusted_repo()
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()),
                                    landed={"sha": "0" * 40, "at": "2026-10-15T10:00:00+00:00"})

        self.assert_unit_reads("awaiting acceptance")

    def test_reads_a_launched_session_awaiting_acceptance__when_its_worktree_is_gone_and_its_branch_is_not_in_main(self):
        """039-L8 — a finished session whose worktree path no longer exists, with `robowright/<slug>` still in the repository and not in main, reads awaiting acceptance — a missing worktree is no evidence of an accept."""
        self.given_trusted_repo()
        self.given_finished_session(worktree=str(self.base / "removed" / SLUG))

        self.assert_unit_reads("awaiting acceptance")

    def test_reads_a_launched_session_complete__when_its_worktree_and_its_branch_are_both_gone(self):
        """039-L9 — a finished session whose worktree path no longer exists and whose branch no trusted repository holds reads complete — every session accepted before `run.json.accepted` existed would read as not in main."""
        self.given_trusted_repo()
        self.git(self.repo, "branch", "-D", BRANCH)
        self.given_finished_session(worktree=str(self.base / "removed" / SLUG))

        self.assert_unit_reads("complete")

    def test_reads_a_launched_session_awaiting_acceptance__when_its_worktree_is_gone_and_its_publish_tip_is_head(self):
        """039-L13 — as L8, with `run.json.publish.tip` `HEAD` (a shape the dashboard keeps): U1 reads awaiting acceptance — read in the main clone, `HEAD` is main itself, whose tree is always in main (review 1 F1)."""
        self.given_trusted_repo()
        self.given_finished_session(worktree=str(self.base / "removed" / SLUG), publish={"tip": "HEAD"})

        self.assert_unit_reads("awaiting acceptance")

    def test_reads_a_launched_session_awaiting_acceptance__when_its_branch_lives_in_a_trusted_repository_its_project_does_not_name(self):
        """039-L14 — SLUG finished, its worktree gone, `robowright/<SLUG>` unmerged in a second trusted repository that only another project names: U1 reads awaiting acceptance — the launcher accepts a worktree of any trusted repository, so a branch there is not gone (review 1 F4)."""
        self.given_trusted_repo()
        self.git(self.repo, "branch", "-D", BRANCH)
        other = self.given_project(name="other")
        elsewhere = self.base / "repos" / "other"
        elsewhere.mkdir(parents=True)
        self.git(elsewhere, "init", "-q", "-b", "main")
        self.git(elsewhere, "commit", "-q", "--allow-empty", "-m", "base")
        self.git(elsewhere, "branch", BRANCH)
        self.git(elsewhere, "commit", "-q", "--allow-empty", "-m", "main moves on")
        self.git(elsewhere, "checkout", "-q", BRANCH)
        (elsewhere / "first.txt").write_text("the first unit\n")
        self.git(elsewhere, "add", "first.txt")
        self.git(elsewhere, "commit", "-q", "-m", "the unit")
        self.git(elsewhere, "checkout", "-q", "main")
        self.given_settings(other, "robowright.json", {"repos": [{"name": "other", "path": str(elsewhere)}]})
        self.given_allowlisted(self.repo, elsewhere)
        self.given_finished_session(worktree=str(self.base / "removed" / SLUG))

        self.assert_unit_reads("awaiting acceptance")

    def test_reads_a_launched_session_awaiting_acceptance__when_git_cannot_say_whether_the_branch_exists(self):
        """039-L15 — as L9, but every `rev-parse` of a `refs/heads/robowright/` ref fails as git does on a broken repository (exit 128): U1 reads awaiting acceptance — git failing would read as the branch gone, so complete (review 1 F5)."""
        self.given_trusted_repo()
        self.git(self.repo, "branch", "-D", BRANCH)
        self.given_finished_session(worktree=str(self.base / "removed" / SLUG))
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").write_text(BROKEN_BRANCH_GIT)
        (bin_dir / "git").chmod(0o755)

        result = subprocess.run([sys.executable, str(DASH), "sample"], capture_output=True, text=True,
                                env=dict(self.env(), PATH=f"{bin_dir}:{os.environ['PATH']}"), cwd=str(self.cwd), timeout=60)

        self.assertEqual(result.returncode, 0, result.stderr)
        line = unit_line(result.stdout, "U1")
        self.assertIn("awaiting acceptance", line)
        self.assertNotIn("complete", line)

    def test_reads_a_finished_direct_build_with_the_lead__when_its_session_works_in_a_directory_no_trusted_repository_lists(self):
        """039-L16 — a change description, its branch in no trusted repository, and its Worker idle in an existing directory no trusted repository lists (an untrusted clone, a branch named otherwise): U1 reads with the Lead — teardown removes the worktree before the branch, so a worktree still on disk is no teardown (review 2 F6)."""
        self.given_trusted_repo()
        self.git(self.repo, "branch", "-D", BRANCH)
        self.given_change_description()
        self.given_live_agent(f"build-{SLUG}", "idle", cwd=self.given_worktree_not_in_main())

        self.assert_unit_reads("with the Lead")

    def test_reads_a_torn_down_direct_build_complete__when_another_projects_trusted_path_is_no_repository(self):
        """039-L17 — as L2, beside a second trusted path, named only by project `other`, that is a plain directory where git fails: U1 reads complete — one broken path elsewhere would leave every torn-down build in every project awaiting acceptance (review 2 F7)."""
        self.given_trusted_repo()
        worktree = self.given_outside_worktree()
        self.given_change_description()
        self.given_torn_down(worktree)
        broken = self.base / "repos" / "not-a-repo"
        broken.mkdir(parents=True)
        other = self.given_project(name="other")
        self.given_settings(other, "robowright.json", {"repos": [{"name": "other", "path": str(broken)}]})
        self.given_allowlisted(self.repo, broken)

        self.assert_unit_reads("complete")

    def test_reads_a_lower_numbered_session_awaiting_acceptance__when_a_higher_numbered_one_is_in_main(self):
        """039-L10 — SECOND's branch fast-forwarded into main and SLUG's not, both finished in the same repository: SLUG reads awaiting acceptance — every session branches from main and is accepted alone, so a later accept says nothing of an earlier one."""
        self.given_trusted_repo()
        self.given_finished_session(worktree=str(self.given_outside_worktree()))
        self.git(self.repo, "branch", f"robowright/{SECOND}", "main")
        self.given_session(slug=SECOND, phase="done", intake=True, units=[{"id": "U1", "status": "done"}],
                           worktree=str(self.given_outside_worktree(f"robowright/{SECOND}", SECOND)))

        self.assert_unit_reads("awaiting acceptance")



# ---------------------------------------------------------------- 055 · a direct build's accept record


class DirectAccept(DashScratch):
    """055 — a finished direct build in the trusted scratch repository, its worktree on `robowright/<slug>` outside
    `.worktrees`; main gains the branch's change as a cherry-pick onto a main that moved after the branch was cut, so
    main never holds the branch's tree."""

    given_trusted_repo = InMainTruth.given_trusted_repo
    given_outside_worktree = InMainTruth.given_outside_worktree
    given_change_description = InMainTruth.given_change_description
    given_torn_down = InMainTruth.given_torn_down
    assert_unit_reads = InMainTruth.assert_unit_reads

    def rev(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True,
                              env=self.env(), timeout=30).stdout.strip()

    def given_picked_onto_a_moved_main(self):
        self.given_trusted_repo()
        self.given_outside_worktree()
        self.given_change_description()
        (self.repo / "CHANGELOG.md").write_text("main moves on\n")
        self.git(self.repo, "add", "CHANGELOG.md")
        self.git(self.repo, "commit", "-q", "-m", "main moves on")
        self.git(self.repo, "cherry-pick", BRANCH)

    def given_record(self, sha):
        records = self.folder / "prs" / SLUG
        records.mkdir(parents=True, exist_ok=True)
        (records / "ACCEPTED.json").write_text(json.dumps({"sha": sha, "at": "2026-10-18T01:00:00+00:00",
                                                           "base": "0" * 40, "tip": "1" * 40}) + "\n")

    def test_reads_a_direct_build_complete__when_its_accept_record_names_a_commit_on_main(self):
        """055-A1 — an ACCEPTED.json whose sha is main's cherry-pick of the branch reads complete — a direct build accepted onto a moved main waits on the Lead's check forever."""
        self.given_picked_onto_a_moved_main()
        self.given_record(self.rev("rev-parse", "main"))

        self.assert_unit_reads("complete")

    def test_reads_a_direct_build_with_the_lead__when_its_accept_record_names_a_commit_not_on_main(self):
        """055-A2 — an ACCEPTED.json whose sha is the branch tip, a commit main does not hold, reads with the Lead — a session can write the record, so a record alone would land anything."""
        self.given_picked_onto_a_moved_main()
        self.given_record(self.rev("rev-parse", BRANCH))

        self.assert_unit_reads("with the Lead")

    def test_reads_a_direct_build_with_the_lead__when_its_accept_record_names_no_commit_id(self):
        """055-A3 — an ACCEPTED.json whose sha is the word `main` reads with the Lead — a ref name would resolve to main itself, which is always on main."""
        self.given_picked_onto_a_moved_main()
        self.given_record("main")

        self.assert_unit_reads("with the Lead")

    def test_reads_a_direct_build_with_the_lead__when_its_accept_record_names_a_commit_on_main_that_is_not_its_change(self):
        """055-A5 — an ACCEPTED.json whose sha is main's own commit before the pick, while the branch still exists, reads with the Lead — a session can name any commit on main, and teardown would then delete work main never got."""
        self.given_picked_onto_a_moved_main()
        self.given_record(self.rev("rev-parse", "main~1"))

        self.assert_unit_reads("with the Lead")

    def test_never_reads_an_accept_record_complete__when_a_direct_build_is_named_what_no_branch_can_be(self):
        """055-A7 — a change description and an ACCEPTED.json naming main's tip under `sample-001-first.lock` (no branch can end `.lock`): its card is the Lead's (`sess intake`) — the record's path is built from a name no shape check held."""
        self.given_trusted_repo()
        hostile = f"{SLUG}.lock"
        records = self.folder / "prs" / hostile
        records.mkdir(parents=True)
        (self.folder / "prs" / f"{hostile}.md").write_text("# Change description\n")
        (records / "ACCEPTED.json").write_text(json.dumps({"sha": self.rev("rev-parse", "main")}) + "\n")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        card = re.search(r'<details class="sess (\w+)" id="s-sample-001-first-lock"', (self.out / "sample.html").read_text())
        self.assertIsNotNone(card)
        self.assertEqual(card.group(1), "intake")

    def test_reads_a_torn_down_direct_build_complete__when_its_project_also_names_an_untrusted_repository(self):
        """055-A4 — a torn-down build whose project names the trusted repository and an existing directory launch.json's `repos` does not list reads complete — every finished direct build in a project naming an untrusted repository waits on the Lead's check forever."""
        self.given_trusted_repo()
        worktree = self.given_outside_worktree()
        self.given_change_description()
        self.given_torn_down(worktree)
        untrusted = self.base / "repos" / "untrusted"
        untrusted.mkdir(parents=True)
        self.given_settings(self.folder, "robowright.json", {"repos": [{"name": "sample", "path": str(self.repo)},
                                                                        {"name": "untrusted", "path": str(untrusted)}]})

        self.assert_unit_reads("complete")

    def given_other_trusted_repo(self):
        """A second scratch repository on `main`, one commit, holding no branch of the build."""
        other = self.base / "repos" / "other"
        other.mkdir(parents=True)
        self.git(other, "init", "-q", "-b", "main")
        self.git(other, "commit", "-q", "--allow-empty", "-m", "other")
        return other

    def other_main(self, other):
        return subprocess.run(["git", "-C", str(other), "rev-parse", "main"], check=True, capture_output=True, text=True,
                              env=self.env(), timeout=30).stdout.strip()

    def test_reads_a_direct_build_with_the_lead__when_its_accept_record_names_another_repositorys_main(self):
        """055-A8 — a project naming two trusted repositories, its branch unaccepted in the first and an ACCEPTED.json naming the second's main tip, reads with the Lead — the branch is checked only in the repository the record points at, so any record lands it."""
        self.given_trusted_repo()
        self.given_outside_worktree()
        self.given_change_description()
        other = self.given_other_trusted_repo()
        self.given_allowlisted(self.repo, other)
        self.given_settings(self.folder, "robowright.json", {"repos": [{"name": "sample", "path": str(self.repo)},
                                                                        {"name": "other", "path": str(other)}]})
        self.given_record(self.other_main(other))

        self.assert_unit_reads("with the Lead")

    def test_reads_a_direct_build_with_the_lead__when_its_branch_is_in_a_trusted_repository_its_project_does_not_name(self):
        """055-A9 — the branch unaccepted in a trusted repository the project does not name, and an ACCEPTED.json naming the main tip of the trusted repository it does name, reads with the Lead — the branch is looked for only where the project points, so any record lands it."""
        self.given_trusted_repo()
        self.given_outside_worktree()
        self.given_change_description()
        other = self.given_other_trusted_repo()
        self.given_allowlisted(self.repo, other)
        self.given_settings(self.folder, "robowright.json", {"repos": [{"name": "other", "path": str(other)}]})
        # Trusted means listed in `repos` and named by some project's robowright.json: here, another project's.
        neighbour = self.given_project(name="neighbour")
        self.given_settings(neighbour, "robowright.json", {"repos": [{"name": "sample", "path": str(self.repo)}]})
        self.given_record(self.other_main(other))

        self.assert_unit_reads("with the Lead")

    def test_reads_a_direct_build_complete__when_main_edited_beside_its_change_before_the_accept(self):
        """055-A10 — the branch editing line 6 of notes.txt, main editing line 3 after the cut, and a squash merge of the branch on main named by ACCEPTED.json, branch still there, reads complete (assumed: patch-id compares changed lines) — every accept onto a busy main waits on the Lead's check until teardown."""
        self.given_trusted_repo()
        worktree = self.given_outside_worktree()
        self.given_change_description()
        notes = "".join(f"line {n}\n" for n in range(1, 9))
        (self.repo / "notes.txt").write_text(notes)
        self.git(self.repo, "add", "notes.txt")
        self.git(self.repo, "commit", "-q", "-m", "notes: eight lines")
        self.git(worktree, "rebase", "-q", "main")
        (worktree / "notes.txt").write_text(notes.replace("line 6\n", "line six\n"))
        self.git(worktree, "commit", "-q", "-am", "notes: spell out six")
        (self.repo / "notes.txt").write_text(notes.replace("line 3\n", "line three\n"))
        self.git(self.repo, "commit", "-q", "-am", "notes: spell out three")
        self.git(self.repo, "merge", "-q", "--squash", BRANCH)
        self.git(self.repo, "commit", "-q", "-m", "first: the accepted build")
        self.given_record(self.rev("rev-parse", "main"))

        self.assert_unit_reads("complete")


# ---------------------------------------------------------------- R7 · no private path


class NoPrivateNames(unittest.TestCase):

    def test_carries_no_home_directory_path(self):
        """R7.1 — the script names no home-directory path — the clone ships one machine's layout."""
        # Absolute home folders on macOS and Linux; case-sensitive, as grep is. `~/` stays allowed: the script names
        # the documented `~/.claude/robowright/launch.json`.
        patterns = ("/Users/", "/home/")
        lines = DASH.read_text().splitlines()

        hits = [f"{number}: {line}" for number, line in enumerate(lines, 1) if any(p in line for p in patterns)]

        self.assertEqual(hits, [])


# ---------------------------------------------------------------- H · where the script runs from


class Location(DashScratch):

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.given_project()
        self.given_session()

    def test_fails_with_one_line_naming_the_missing_roster__when_copied_outside_the_clone(self):
        """H1 — a copy outside the clone names the roster it cannot find — the Owner gets a traceback (assumed Q3)."""
        copy = self.base / "elsewhere" / "tools" / "robowright-dash.py"
        copy.parent.mkdir(parents=True)
        shutil.copyfile(DASH, copy)

        result = self.run_dash(script=copy)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        lines = result.stderr.strip().splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertIn(str(self.base / "elsewhere" / "skills" / "lead" / "scripts" / "run-roster.py"), lines[0])

    def test_prints_the_summary__when_run_through_a_symlink_into_the_clone(self):
        """H2 — a symlink finds the roster through the clone — a linked install fails to start (assumed Q4)."""
        link = self.base / "linked" / "robowright-dash.py"
        link.parent.mkdir()
        link.symlink_to(DASH)

        result = self.run_dash(script=link)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"(?m)^sample: ")
        self.assertIn([SLUG, "implement"], [line.split()[:2] for line in result.stdout.splitlines()])


# ================================================================ U2 · a Summary cell per unit, spend from the ledger,
# the verdict and the asks on a finished card. Rows are `U2-…` in BEHAVIORS.md.


def shows(figure):
    """A pattern for `figure` standing alone: not the tail of a longer number (`117 requests` does not show
    `17 requests`) and not followed by another digit (`est usd 1.655` does not show `est usd 1.65`)."""
    return r"(?<![\w.,])" + re.escape(figure) + r"(?!\d)"


# ---------------------------------------------------------------- U2-R1 · the purpose line is the Summary cell


class PurposeLine(DashScratch):
    """launch.json naming both roots; SLUG done, through intake, its worktree not in main — so unit U1 is awaiting
    acceptance, and its purpose line shows on SLUG's card and on the awaiting-acceptance row."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

    def given_task_breakdown(self, header, *rows):
        folder = self.projects / "sample"
        folder.mkdir(parents=True)
        (folder / "PROJECT.md").write_text(project_md(header, *rows))

    def purposes(self):
        """Every purpose line on both pages `--once` wrote."""
        return [text for name in ("index.html", "sample.html") for text in Page(self.out / name).texts("purpose")]

    def test_shows_the_summary_cell_as_every_purpose_line__when_the_header_has_summary(self):
        """U2-R1.1 — a Summary header gives the purpose line the Summary cell — the Owner reads the implementation note instead of what the chunk does."""
        self.given_task_breakdown(SUMMARY_HEADER, SUMMARY_ROW)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        purposes = self.purposes()
        self.assertNotEqual(purposes, [])
        self.assertEqual(set(purposes), {SUMMARY})

    def test_prints_the_summary_cell_with_its_unit__when_the_header_has_summary(self):
        """U2-R1.2 — the text summary carries the Summary cell as the unit's purpose — the terminal view shows no purpose, or the wrong one (assumed Q1)."""
        self.given_task_breakdown(SUMMARY_HEADER, SUMMARY_ROW)

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(SUMMARY, unit_and_next_line(result.stdout, "U1"))
        self.assertNotIn(DESCRIPTION, text_of(result.stdout))

    def test_shows_the_description_cell_as_every_purpose_line__when_the_header_has_no_summary(self):
        """U2-R1.3 — a header without Summary keeps the Description purpose — every existing PROJECT.md loses its purpose lines."""
        self.given_task_breakdown(OLD_HEADER, OLD_ROW)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        purposes = self.purposes()
        self.assertNotEqual(purposes, [])
        self.assertEqual(set(purposes), {DESCRIPTION})

    def test_prints_the_description_cell_with_its_unit__when_the_header_has_no_summary(self):
        """U2-R1.4 — the text summary falls back to the Description cell — an older PROJECT.md prints no purpose (assumed Q1)."""
        self.given_task_breakdown(OLD_HEADER, OLD_ROW)

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(DESCRIPTION, unit_and_next_line(result.stdout, "U1"))

    def test_shows_the_row_error_and_a_blank_size__when_a_row_is_one_cell_short_of_a_summary_header(self):
        """U2-R1.5 — the cell-count guard still flags a short row — shifted cells pass for size and status."""
        self.given_task_breakdown(SUMMARY_HEADER, OLD_ROW)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        page = Page(self.out / "sample.html")
        self.assertIn(SHORT_ROW_ERROR, page.text())
        self.assertEqual(page.texts("size"), [""])

    def test_shows_no_purpose_line__when_a_row_is_one_cell_short_of_a_summary_header(self):
        """U2-R1.6 — a short row's shifted cells are never its purpose — the Owner reads a tracker key or a file path as what the chunk does (assumed Q2)."""
        self.given_task_breakdown(SUMMARY_HEADER, OLD_ROW)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.purposes(), [])

    def test_prints_no_shifted_cell__when_a_row_is_one_cell_short_of_a_summary_header(self):
        """U2-R1.7 — the text summary prints no shifted cell as a purpose — the terminal shows a tracker key or a path as what the chunk does (assumed Q2)."""
        self.given_task_breakdown(SUMMARY_HEADER, OLD_ROW)

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ENG-7", text_of(result.stdout))
        self.assertNotIn("docs/first.md", text_of(result.stdout))

    def test_shows_the_description_cell_as_the_purpose__when_the_summary_cell_is_empty(self):
        """U2-R1.8 — an empty Summary cell falls back to Description — a unit the Planner has not summarised yet shows no purpose (assumed Q3)."""
        self.given_task_breakdown(SUMMARY_HEADER, EMPTY_SUMMARY_ROW)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        purposes = self.purposes()
        self.assertNotEqual(purposes, [])
        self.assertEqual(set(purposes), {DESCRIPTION})


# ---------------------------------------------------------------- U2-R2 · spend from the ledger


class Spend(DashScratch):
    """launch.json naming both roots; project `sample` planning U1 `first` and U2 `second`; SLUG and SECOND both
    working, each brief setting a dollar limit (DOLLAR_BRIEF, so their lines carry an estimate); the accounting root
    `<base>/accounting`, named by $ROBOWRIGHT_ACCOUNTING_ROOT."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        folder = self.projects / "sample"
        folder.mkdir(parents=True)
        (folder / "PROJECT.md").write_text(project_md(OLD_HEADER, OLD_ROW, SECOND_OLD_ROW))
        self.first = self.given_session(**DOLLAR_BRIEF)
        self.second = self.given_session(slug=SECOND, **DOLLAR_BRIEF)
        self.accounting = self.base / "accounting"

    def given_brief_limits(self, run_dir, **limits):
        """run_dir's run.json with neither spend_threshold_usd nor spend_cap_usd, then the `limits` given (None is
        written as null); the file keeps the quiet given_session gave it."""
        path = run_dir / "run.json"
        run = json.loads(path.read_text())
        run.pop("spend_threshold_usd", None)
        run.pop("spend_cap_usd", None)
        run.update(limits)
        written = path.stat().st_mtime
        path.write_text(json.dumps(run, indent=2) + "\n")
        os.utime(path, (written, written))

    def given_ledger(self, *lines):
        """records.jsonl under the accounting root: a dict is one record, a string one raw line."""
        self.accounting.mkdir(parents=True, exist_ok=True)
        text = "".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines)
        (self.accounting / "records.jsonl").write_text(text)

    def run_once(self):
        return self.run_dash("--once", str(self.out), env_accounting=self.accounting)

    def spend(self, card=None):
        """Each spend line on the project page — `card`'s, in its Details, or with no card the hero's facts line — as its
        visible text then each phrase's exact figure from its title."""
        page = (self.out / "sample.html").read_text()
        if card:
            start = page.index(f'id="s-{card}"')
            end = page.find('<details class="sess', start)
            lines = re.findall(r'<div class="note spend">(.*?)</div>', page[start:end if end != -1 else None], re.S)
        else:
            lines = re.findall(r'<p class="facts">(.*?)</p>', page, re.S)
        return [" ".join(html.unescape(re.sub(r"<[^>]*>", " ", line)).split() + [html.unescape(t) for t in re.findall(r'title="([^"]*)"', line)])
                for line in lines]

    def rollup_row(self, project):
        """robowright-cost.py --by project --json, as the brief runs it; the row keyed `project`."""
        env = self.env()
        env.pop("ROBOWRIGHT_PRICING_FILE", None)
        result = subprocess.run([sys.executable, str(COST), "--by", "project", "--json", "--accounting-root",
                                 str(self.accounting), "--runs-root", str(self.sessions)],
                                capture_output=True, text=True, env=env, cwd=str(self.cwd), timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return next(row for row in json.loads(result.stdout)["rows"] if row["key"] == project)

    def test_shows_the_sum_of_its_tickets_session_records__not_the_unit_record(self):
        """U2-R2.1 — a card sums its ticket's session records and never the unit record — the Owner sees a unit's work counted twice."""
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
            ledger_record(SLUG, "worker", "w-1", 7, 2_000, 0.90, 900, scope="unit", unit_id="U1", session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertRegex(spend[0], shows("17 requests"))
        self.assertRegex(spend[0], shows("4,500 output tokens"))
        self.assertRegex(spend[0], shows("$1.65 est."))
        self.assertRegex(spend[0], shows("0.8 h active"))

    def spend_face(self, card):
        """`card`'s spend line in its Details as it reads on the page, its titles left out."""
        page = (self.out / "sample.html").read_text()
        start = page.index(f'id="s-{card}"')
        end = page.find('<details class="sess', start)
        line = re.search(r'<div class="note spend">(.*?)</div>', page[start:end if end != -1 else None], re.S).group(1)
        return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", line)).split())

    def test_reads_a_count_short_on_the_face__with_its_exact_figure_in_the_title(self):
        """033-B15 — 23,456 requests and 3,141,592 output tokens read `23k requests` and `3.1M output tokens`, each titled with its exact figure (Lead decision 5; §5 item 2, short counts with "exact figures in `title`")."""
        self.given_ledger(ledger_record(SLUG, "worker", "w-1", 23_456, 3_141_592, 1.25, 1_800, session_dir=self.first))

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        face = self.spend_face(SLUG)
        self.assertIn("23k requests", face)
        self.assertIn("3.1M output tokens", face)
        self.assertRegex(self.spend(card=SLUG)[0], shows("23,456 requests"))
        self.assertRegex(self.spend(card=SLUG)[0], shows("3,141,592 output tokens"))

    def test_rounds_a_short_count_up_to_its_next_unit__never_to_ten_point_oh_k_or_a_thousand_k(self):
        """033-B16 — 9,950 reads `10k` and 999,500 `1.0M`; 9,949 reads `9.9k` and 999,499 `999k` — a count at a unit's edge shows `10.0k` or `1000k`. Q6"""
        self.given_ledger(ledger_record(SLUG, "worker", "w-1", 9_950, 999_499, 1.25, 1_800, session_dir=self.first),
                          ledger_record(SECOND, "worker", "w-2", 9_949, 999_500, 0.20, 360, session_dir=self.second))

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(self.spend_face(SLUG), r"(?:^| )10k requests · 999k output tokens$")
        self.assertRegex(self.spend_face(SECOND), r"(?:^| )9\.9k requests · 1\.0M output tokens$")

    def test_keys_each_card_by_the_records_ticket__not_the_session_dir_it_was_written_from(self):
        """U2-R2.2 — a record counts for the ticket it names, whatever its session_dir — spend lands on the wrong session's card."""
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
            # SECOND's record, written from SLUG's session dir.
            ledger_record(SECOND, "worker", "w-2", 3, 600, 0.20, 360, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        page = Page(self.out / "sample.html")
        second = self.spend(card=SECOND)
        self.assertEqual(len(second), 1, second)
        self.assertRegex(second[0], shows("3 requests"))
        self.assertRegex(second[0], shows("600 output tokens"))
        self.assertRegex(second[0], shows("$0.20 est."))
        self.assertRegex(second[0], shows("0.1 h active"))
        self.assertRegex(" ".join(self.spend(card=SLUG)), shows("17 requests"))

    def test_shows_the_project_spend_the_rollup_gives_its_project__to_the_cent(self):
        """U2-R2.3 — the project's spend is the rollup's row for it — the dashboard and robowright-cost.py disagree on what a project cost."""
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
            ledger_record(SLUG, "worker", "w-1", 7, 2_000, 0.90, 900, scope="unit", unit_id="U1", session_dir=self.first),
            ledger_record(SECOND, "worker", "w-2", 3, 600, 0.20, 360, session_dir=self.second),
            ledger_record("other-001-elsewhere", "worker", "w-9", 100, 50_000, 9.00, 7_200, project="other"),
        )
        rollup = self.rollup_row("sample")
        # The rollup reads this ledger as the table does, so the literals below are its figures.
        self.assertEqual((rollup["requests"], rollup["output_tokens"], rollup["estimated_usd"], rollup["active_hours"]),
                         (20, 5_100, 1.85, 0.9))

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        project = self.spend()
        self.assertEqual(len(project), 1, project)
        self.assertRegex(project[0], shows("20 requests"))
        self.assertRegex(project[0], shows("5,100 output tokens"))
        self.assertRegex(project[0], shows("$1.85 est."))
        self.assertRegex(project[0], shows("0.9 h active"))

    def test_leaves_out_records_with_no_unit__when_a_session_of_the_project_has_no_ticket(self):
        """U2-R2.7 — a ticket-less session does not pull in every record whose unit is null — another project's Lead spend shows as this one's."""
        self.given_session(slug="sample-003-briefing", ticket=None, **DOLLAR_BRIEF)
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
            ledger_record(SECOND, "worker", "w-2", 3, 600, 0.20, 360, session_dir=self.second),
            ledger_record(None, "lead", "l-9", 50, 9_000, 4.00, 3_600, project="other"),
        )
        rollup = self.rollup_row("sample")
        self.assertEqual((rollup["requests"], rollup["output_tokens"], rollup["estimated_usd"], rollup["active_hours"]),
                         (20, 5_100, 1.85, 0.9))

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        project = self.spend()
        self.assertEqual(len(project), 1, project)
        self.assertRegex(project[0], shows("20 requests"))
        self.assertRegex(project[0], shows("5,100 output tokens"))
        self.assertRegex(project[0], shows("$1.85 est."))
        self.assertRegex(project[0], shows("0.9 h active"))

    def test_counts_one_claude_sessions_active_time_once__when_it_has_a_record_per_model(self):
        """U2-R2.4 — a Claude session's active time counts once, as the rollup counts it — a two-model session shows double its hours (assumed Q5)."""
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "worker", "w-1", 4, 300, 0.05, 1_800, session_dir=self.first, model="claude-haiku-4-5"),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertRegex(spend[0], shows("16 requests"))
        self.assertRegex(spend[0], shows("3,700 output tokens"))
        self.assertRegex(spend[0], shows("$1.30 est."))
        self.assertRegex(spend[0], shows("0.5 h active"))

    def test_marks_the_estimate_n_a__when_no_record_of_the_ticket_is_priced(self):
        """U2-R2.5 — unpriced records show `n/a est.`, never 0.00 — the Owner reads unpriced work as free."""
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, None, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, None, 1_080, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertRegex(spend[0], shows("17 requests"))
        self.assertRegex(spend[0], shows("n/a est."))
        self.assertNotIn("0.00", spend[0])

    def test_sums_the_priced_records__when_one_of_the_tickets_records_is_unpriced(self):
        """U2-R2.6 — a null estimate adds nothing to the priced ones, as the rollup sums — one unpriced record hides or zeroes the rest."""
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, None, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertRegex(spend[0], shows("$0.40 est."))

    def test_skips_a_malformed_ledger_line__and_sums_the_rest(self):
        """U2-R3.3 — a ragged ledger line is skipped as read_records skips it — one bad write blanks or crashes the page."""
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            '{"scope": "session", "unit": "sample-001-fi',
            "[1, 2]",
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertRegex(spend[0], shows("17 requests"))
        self.assertRegex(spend[0], shows("$1.65 est."))

    def test_carries_no_no_ledger_note__when_the_ledger_exists(self):
        """U2-R3.4 — a page with a ledger says nothing about a missing one — the Owner is told the ledger is gone when it is not."""
        self.given_ledger(ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first))

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("no ledger", Page(self.out / "sample.html").text().lower())

    # P1-R1 · the project line is `--by project`'s row

    def test_counts_the_projects_records_whatever_their_unit__not_another_projects_record_of_its_ticket(self):
        """P1-R1.1 — the project line is the rollup's `sample` row and SLUG's card keeps every record of its ticket — the project line leaves out its Planner's spend and counts another project's (card: assumed P1-Q1)."""
        self.given_ledger(
            # The project's Planner: a session-scope record of `sample` with no unit.
            ledger_record(None, "planner", "p-1", 9, 2_300, 0.70, 720),
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            # Project `other`'s record naming SLUG's ticket.
            ledger_record(SLUG, "worker", "w-8", 40, 8_000, 3.00, 2_880, project="other"),
        )
        rollup = self.rollup_row("sample")
        # The rollup reads this ledger as the table does, so the literals below are its figures: the Planner's and
        # the worker's records, 9 + 12, 2,300 + 3,400, 0.70 + 1.25, (720 + 1,800) s.
        self.assertEqual((rollup["requests"], rollup["output_tokens"], rollup["estimated_usd"], rollup["active_hours"]),
                         (21, 5_700, 1.95, 0.7))

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        page = Page(self.out / "sample.html")
        project = self.spend()
        self.assertEqual(len(project), 1, project)
        self.assertRegex(project[0], shows("21 requests"))
        self.assertRegex(project[0], shows("5,700 output tokens"))
        self.assertRegex(project[0], shows("$1.95 est."))
        self.assertRegex(project[0], shows("0.7 h active"))
        # SLUG's card: both records whose unit is its ticket, 12 + 40, 3,400 + 8,000, 1.25 + 3.00, (1,800 + 2,880) s.
        card = self.spend(card=SLUG)
        self.assertEqual(len(card), 1, card)
        self.assertRegex(card[0], shows("52 requests"))
        self.assertRegex(card[0], shows("11,400 output tokens"))
        self.assertRegex(card[0], shows("$4.25 est."))
        self.assertRegex(card[0], shows("1.3 h active"))


    # P3-R1 · a card shows dollars only under a brief that sets a dollar limit

    def test_shows_requests_tokens_and_hours_and_no_dollar_figure__when_its_brief_sets_no_spend_limit(self):
        """P3-R1.1 — a card under a brief with no dollar limit shows its requests, output tokens and active hours and no dollar figure, though a sibling's brief sets one — the Owner is shown a dollar estimate nobody can act on under a plan budget."""
        self.given_brief_limits(self.first)
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertNotIn("usd", spend[0].lower())
        self.assertNotIn("1.65", spend[0])
        self.assertNotIn("$", spend[0])
        self.assertNotIn("n/a", spend[0])
        self.assertRegex(spend[0], shows("17 requests"))
        self.assertRegex(spend[0], shows("4,500 output tokens"))
        self.assertRegex(spend[0], shows("0.8 h active"))

    def test_shows_the_dollar_estimate__when_its_brief_sets_only_a_spend_cap(self):
        """P3-R1.2 — a brief setting spend_cap_usd alone puts the estimate on its card — a capped session's cost vanishes from its card because only the warn threshold is read."""
        self.given_brief_limits(self.first, spend_cap_usd=40)
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertRegex(spend[0], shows("$1.65 est."))

    def test_shows_the_dollar_estimate__when_its_brief_sets_a_zero_spend_threshold(self):
        """P3-R1.3 — a threshold of 0 is set, as the roster's number() reads it — a zero limit reads as no limit and the card drops its dollars."""
        self.given_brief_limits(self.first, spend_threshold_usd=0)
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertRegex(spend[0], shows("$1.65 est."))

    def test_shows_no_dollar_figure__when_its_brief_writes_both_spend_limits_as_null(self):
        """P3-R1.4 — a limit written as null is not set, as the roster's number() reads it — a brief that names the keys without a value shows dollars the roster does not."""
        self.given_brief_limits(self.first, spend_threshold_usd=None, spend_cap_usd=None)
        self.given_brief_limits(self.second)
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertNotIn("usd", spend[0].lower())
        self.assertNotIn("1.65", spend[0])
        self.assertRegex(spend[0], shows("17 requests"))

    def test_shows_no_n_a__when_its_brief_sets_no_limit_and_no_record_of_its_ticket_is_priced(self):
        """P3-R1.5 — with no dollar limit an unpriced card shows no `n/a` either — the Owner reads a missing price as a dollar figure under a plan budget."""
        self.given_brief_limits(self.first)
        self.given_brief_limits(self.second)
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, None, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, None, 1_080, session_dir=self.first),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        spend = self.spend(card=SLUG)
        self.assertEqual(len(spend), 1, spend)
        self.assertNotIn("n/a", spend[0])
        self.assertNotIn("usd", spend[0].lower())
        self.assertRegex(spend[0], shows("17 requests"))

    # P3-R2 · the project line shows dollars only when one of its sessions' briefs sets a limit

    def test_shows_the_project_line_with_no_dollar_figure__when_none_of_its_sessions_sets_a_limit(self):
        """P3-R2.1 — no brief of `sample` sets a limit, so its line has no dollars, whatever another project's brief sets — a plan-budget project shows a dollar total, or borrows another project's limit."""
        self.given_brief_limits(self.first)
        self.given_brief_limits(self.second)
        # Another project's session, whose brief sets a cap.
        self.given_session(slug="other-001-elsewhere", spend_cap_usd=40)
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
            ledger_record(SECOND, "worker", "w-2", 3, 600, 0.20, 360, session_dir=self.second),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        project = self.spend()
        self.assertEqual(len(project), 1, project)
        self.assertNotIn("usd", project[0].lower())
        self.assertNotIn("1.85", project[0])
        self.assertNotIn("$", project[0])
        self.assertNotIn("n/a", project[0])
        # The rollup's `sample` row, as U2-R2.3: 12 + 5 + 3, 3,400 + 1,100 + 600, (1,800 + 1,080 + 360) s.
        self.assertRegex(project[0], shows("20 requests"))
        self.assertRegex(project[0], shows("5,100 output tokens"))
        self.assertRegex(project[0], shows("0.9 h active"))

    def test_shows_the_project_line_with_no_dollar_figure__when_one_of_its_two_sessions_sets_no_limit(self):
        """P3-R2.2 — a project mixing a dollar brief and a brief with no limit shows no dollar figure (Brief correction, Owner) — the Owner reads dollars for work that was not spent in dollars."""
        self.given_brief_limits(self.first)
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
            ledger_record(SECOND, "worker", "w-2", 3, 600, 0.20, 360, session_dir=self.second),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        project = self.spend()
        self.assertEqual(len(project), 1, project)
        self.assertNotIn("usd", project[0].lower())
        self.assertNotIn("1.85", project[0])
        self.assertNotIn("$", project[0])
        self.assertNotIn("n/a", project[0])
        self.assertRegex(project[0], shows("20 requests"))

    def test_shows_the_project_dollar_estimate__when_every_one_of_its_sessions_sets_a_limit__whatever_another_projects_brief_sets(self):
        """P3-R2.3 — every brief of `sample` sets a limit, so its line carries dollars, though another project's brief sets none — another project's unlimited brief hides this project's dollars."""
        # Another project's session, whose brief sets no limit; SLUG and SECOND keep DOLLAR_BRIEF.
        self.given_session(slug="other-001-elsewhere")
        self.given_ledger(
            ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.first),
            ledger_record(SLUG, "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.first),
            ledger_record(SECOND, "worker", "w-2", 3, 600, 0.20, 360, session_dir=self.second),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        project = self.spend()
        self.assertEqual(len(project), 1, project)
        self.assertRegex(project[0], shows("$1.85 est."))
        self.assertRegex(project[0], shows("20 requests"))

    def test_shows_the_project_line_with_no_dollar_figure__when_the_project_has_no_session(self):
        """P3-R2.4 — a project with records and no session has no brief to budget it, so no dollar figure — every-of-none reads as true and a session-less project shows dollars."""
        shutil.rmtree(self.first)
        shutil.rmtree(self.second)
        # The project's Planner: a session-scope record of `sample` with no unit.
        self.given_ledger(ledger_record(None, "planner", "p-1", 9, 2_300, 0.70, 720))

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        project = self.spend()
        self.assertEqual(len(project), 1, project)
        self.assertNotIn("usd", project[0].lower())
        self.assertNotIn("0.70", project[0])
        # The rollup's `sample` row: the Planner's record alone, 720 s.
        self.assertRegex(project[0], shows("9 requests"))
        self.assertRegex(project[0], shows("2,300 output tokens"))
        self.assertRegex(project[0], shows("0.2 h active"))


# ---------------------------------------------------------------- U2-R3 · no ledger, no spend line


class NoLedger(DashScratch):
    """Project `sample` planning U1 `first` and U2 `second`, SLUG and SECOND both working — two cards, so one note
    per card would show twice."""

    def given_two_sessions(self, projects_root):
        folder = projects_root / "sample"
        folder.mkdir(parents=True)
        (folder / "PROJECT.md").write_text(project_md(OLD_HEADER, OLD_ROW, SECOND_OLD_ROW))
        self.given_session()
        self.given_session(slug=SECOND)

    def assert_no_spend_and_one_note(self):
        pages = [Page(self.out / name) for name in ("index.html", "sample.html")]
        self.assertEqual([text for page in pages for text in page.texts("spend")], [])
        self.assertEqual([page for page in pages if " est." in page.text()], [])
        self.assertEqual(pages[1].text().lower().count("no ledger"), 1)

    def test_shows_no_spend_line_and_one_no_ledger_note__when_nothing_names_an_accounting_root(self):
        """U2-R3.1 — with no accounting root the spend line is absent and the page says so once — the Owner reads zero spend for work that was never measured."""
        # No launch.json and no $ROBOWRIGHT_ACCOUNTING_ROOT: only --runs-root, so run-cost.py's accounting_root is None,
        # and the projects root is the sessions root's parent.
        self.given_two_sessions(self.roots)

        result = self.run_dash("--once", str(self.out), "--runs-root", str(self.sessions))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_no_spend_and_one_note()

    def test_shows_no_spend_line_and_one_no_ledger_note__when_the_accounting_root_has_no_records_file(self):
        """U2-R3.2 — an accounting root with no records.jsonl renders as no ledger — the Owner reads zero spend for work that was never recorded."""
        self.given_launch_roots()
        self.given_two_sessions(self.projects)
        accounting = self.base / "accounting"
        accounting.mkdir()

        result = self.run_dash("--once", str(self.out), env_accounting=accounting)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_no_spend_and_one_note()


# ---------------------------------------------------------------- U2-R4 · the plan review's verdict on a finished card


class PlanReviewVerdict(DashScratch):
    """launch.json naming both roots; project `sample`; SLUG done, through intake, its worktree not in main."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.given_project()
        self.worktree = self.given_worktree_not_in_main()

    def verdicts(self, card=None):
        return [text for name in ("index.html", "sample.html") for text in Page(self.out / name).texts("verdict", card=card)]

    def test_shows_the_verdict_on_the_card__when_run_json_has_one_plan_review(self):
        """U2-R4.1 — a finished card shows its plan review's verdict — the Owner cannot see the review asked for polish."""
        self.given_finished_session(worktree=str(self.worktree), plan_reviews=[
            {"n": 1, "at": "2026-09-20T09:00:00-07:00", "verdict": "polish", "unit": "U1", "path": "PLAN-REVIEW.md"}])

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        verdicts = self.verdicts(card=SLUG)
        self.assertEqual(len(verdicts), 1, verdicts)
        self.assertIn("polish", verdicts[0])

    def test_shows_the_newest_verdict_only__when_run_json_has_two_plan_reviews(self):
        """U2-R4.2 — the newest plan review's verdict is the one shown — a superseded verdict passes for the current one."""
        self.given_finished_session(worktree=str(self.worktree), plan_reviews=[
            {"n": 1, "at": "2026-09-19T09:00:00-07:00", "verdict": "rebrief", "unit": "U1", "path": "PLAN-REVIEW.md"},
            {"n": 2, "at": "2026-09-20T09:00:00-07:00", "verdict": "polish", "unit": "U1", "path": "PLAN-REVIEW.md"}])

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        verdicts = self.verdicts(card=SLUG)
        self.assertEqual(len(verdicts), 1, verdicts)
        self.assertIn("polish", verdicts[0])
        self.assertNotIn("rebrief", verdicts[0])

    def test_shows_no_verdict__when_run_json_has_no_plan_reviews_key(self):
        """U2-R4.3 — no plan_reviews, no verdict — the card invents a verdict nobody gave."""
        self.given_finished_session(worktree=str(self.worktree))

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.verdicts(), [])

    def test_shows_no_verdict__when_run_json_has_an_empty_plan_reviews_list(self):
        """U2-R4.4 — an empty plan_reviews list, no verdict — the card crashes or shows an empty verdict."""
        self.given_finished_session(worktree=str(self.worktree), plan_reviews=[])

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.verdicts(), [])

    # P1-R4 · a last plan review that is not an object

    def test_shows_no_verdict_and_no_traceback__when_the_last_plan_review_is_not_an_object(self):
        """P1-R4.1 — a last plan_reviews entry that is not an object shows no verdict, not even an earlier entry's — one malformed run.json takes the whole page down."""
        self.given_finished_session(worktree=str(self.worktree), plan_reviews=[
            {"n": 1, "at": "2026-09-19T09:00:00-07:00", "verdict": "rebrief", "unit": "U1", "path": "PLAN-REVIEW.md"},
            "polish"])

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotEqual(Page(self.out / "sample.html").card(SLUG), "")
        self.assertEqual(self.verdicts(), [])


# ---------------------------------------------------------------- U2-R5 · the owner brief's asks on a finished card


class OwnerBriefAsks(DashScratch):
    """launch.json naming both roots; project `sample`, no robowright.json; SLUG done, through intake, not in main."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.folder = self.given_project()
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

    def given_brief(self, text):
        reviews = self.folder / "reviews"
        reviews.mkdir()
        (reviews / f"{SLUG}-owner-brief.md").write_text(text)

    def card(self):
        return Page(self.out / "sample.html").card(SLUG)

    def test_lists_two_asks_and_their_text__when_decide_now_has_two_table_rows(self):
        """U2-R5.1 — the card counts and lists the brief's Decide-now rows, and stops at the next section — the Owner misses a question, or answers a decision already made."""
        self.given_brief(BRIEF_TABLE_ASKS)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        card = self.card()
        self.assertRegex(card, shows("2 asks"))
        self.assertIn(ASK_FLAG, card)
        self.assertIn(ASK_EXPORT, card)

    def test_lists_two_asks_and_their_text__when_decide_now_has_two_bullets(self):
        """U2-R5.2 — bullet asks count as table rows do — a brief written as a list shows no asks."""
        self.given_brief(BRIEF_BULLET_ASKS)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        card = self.card()
        self.assertRegex(card, shows("2 asks"))
        self.assertIn(ASK_FLAG, card)
        self.assertIn(ASK_EXPORT, card)

    def test_shows_zero_asks__when_decide_now_has_no_rows(self):
        """U2-R5.3 — an empty Decide-now reads 0 asks — the next section's rows pass for asks, or a briefed session looks unbriefed."""
        self.given_brief(BRIEF_NO_ASKS)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(self.card(), shows("0 asks"))

    def test_shows_no_asks_line__when_there_is_no_owner_brief(self):
        """U2-R5.4 — no owner brief, no asks line — an unbriefed session reads as having nothing to decide."""
        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card(), "")
        self.assertNotRegex(Page(self.out / "sample.html").text(), r"(?<![\w.,])\d+ asks?\b")

    # P1-R2 · "Nothing" and "None" are not asks

    def asks(self):
        """The text of SLUG's one asks line."""
        asks = Page(self.out / "sample.html").texts("asks", card=SLUG)
        self.assertEqual(len(asks), 1, asks)
        return asks[0]

    def test_shows_zero_asks__when_decide_nows_only_table_row_says_nothing(self):
        """P1-R2.1 — a Decide now answered "Nothing" reads 0 asks — the Owner is sent to answer a question nobody asked."""
        self.given_brief(BRIEF_NOTHING_ROW)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        asks = self.asks()
        self.assertRegex(asks, shows("0 asks"))
        self.assertNotIn("Nothing", asks)

    def test_counts_one_ask__when_decide_now_has_a_none_bullet_and_one_real_ask(self):
        """P1-R2.2 — a "None." bullet beside a real ask is dropped and the ask kept — the count is one too many, or the real ask is lost with it."""
        self.given_brief(BRIEF_NONE_BULLET_AND_ONE_ASK)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        asks = self.asks()
        # `1 ask` or `1 asks`: the count is this rule's, the singular is P1-R3's.
        self.assertRegex(asks, shows("1 ask"))
        self.assertIn(ASK_FLAG, asks)
        self.assertNotIn("None", asks)

    # P1-R3 · one ask is singular

    def test_reads_one_ask_in_the_singular__when_decide_now_has_exactly_one_row(self):
        """P1-R3.1 — a finished card with one ask reads "1 ask" — the card reads "1 asks"."""
        self.given_brief(BRIEF_ONE_ASK)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        asks = self.asks()
        self.assertRegex(asks, shows("1 ask") + r"\b")
        self.assertNotRegex(asks, shows("1 asks"))
        self.assertIn(ASK_EXPORT, asks)


# ================================================================ P3 · one plan-usage line per page, read as run-cost.py's
# plan_usage() reads it. Rows are `P3-R3…` and `P3-R4…` in BEHAVIORS.md; P3-R1 and P3-R2 are in `Spend`.

# The status-line tap's latest.json, in the shape run-cost.py's plan_usage() reads: each window's used_percentage and
# the reading's captured_at. READING_AT_HOME's figures differ from READING_TAPPED's in every place, so a line read
# from the wrong directory shows.
TAPPED_AT = "2026-09-27T09:15:00-07:00"
HOME_AT = "2026-09-26T21:40:00-07:00"
READING_TAPPED = {"five_hour": {"used_percentage": 42}, "seven_day": {"used_percentage": 17.5}, "captured_at": TAPPED_AT}
READING_AT_HOME = {"five_hour": {"used_percentage": 88}, "seven_day": {"used_percentage": 61}, "captured_at": HOME_AT}
# The zone every plan-usage run is given (F1 rule 1): +05:30 and no DST, so a time printed in UTC, or the raw
# captured_at, shows. Clock times below are derived outside the dashboard with `TZ=Asia/Kolkata date -r <epoch> '+%T'`:
# TAPPED_AT is 16:15:00 UTC → 21:45:00; HOME_AT is 04:40:00 UTC on the 27th → 10:10:00.
CLOCK_ZONE = "Asia/Kolkata"


class PlanUsage(DashScratch):
    """launch.json naming both roots; project `sample` planning U1 `first` and U2 `second`; SLUG and SECOND both
    working, neither brief setting a dollar limit (the line does not depend on the billing rule), so the project page
    carries two cards; no accounting root. The tap's directory, when a test names one, is `<base>/usage` through
    $CLAUDE_USAGE_DIR; the fallback is `<scratch HOME>/.claude/usage`."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        folder = self.projects / "sample"
        folder.mkdir(parents=True)
        (folder / "PROJECT.md").write_text(project_md(OLD_HEADER, OLD_ROW, SECOND_OLD_ROW))
        self.given_session()
        self.given_session(slug=SECOND)
        self.usage_dir = self.base / "usage"
        self.home_usage = self.home / ".claude" / "usage"

    def given_reading(self, folder, reading):
        """latest.json in `folder`: a dict as JSON, a string as the raw file."""
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "latest.json").write_text(reading if isinstance(reading, str) else json.dumps(reading) + "\n")

    def run_once(self, usage_dir=None):
        return self.run_dash("--once", str(self.out), env_usage=usage_dir, env_tz=CLOCK_ZONE)

    def lines(self, name, outside_cards=False):
        """The text of every plan-usage element on page `name`."""
        return Page(self.out / name).texts("plan-usage", outside_cards=outside_cards)

    def assert_no_line_and_no_traceback(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        for name in ("index.html", "sample.html"):
            self.assertEqual(self.lines(name), [], name)
            self.assertNotIn("5-hour", Page(self.out / name).text(), name)

    # P3-R3 · each page carries one plan-usage line

    def test_shows_one_plan_usage_line_on_the_index_from_claude_usage_dir__over_the_reading_under_home(self):
        """P3-R3.1 — the index carries one line with $CLAUDE_USAGE_DIR's 5-hour and 7-day percentages and its captured_at's clock time (F1 rule 1) — the Owner reads another tap's reading, or none, on the page they open first."""
        self.given_reading(self.usage_dir, READING_TAPPED)
        self.given_reading(self.home_usage, READING_AT_HOME)

        result = self.run_once(self.usage_dir)

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.lines("index.html")
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(lines[0], shows("5-hour 42%"))
        self.assertRegex(lines[0], shows("7-day 17.5%"))
        self.assertRegex(lines[0], shows("as of 21:45:00"))
        self.assertNotIn(TAPPED_AT, lines[0])
        self.assertNotIn("88", lines[0])

    def test_shows_one_plan_usage_line_on_the_project_page_after_its_hero__and_one_on_the_index(self):
        """033-B8 (was P3-R3.2) — the project page carries one plan-usage line, in no card and after the hero closes, so not on the facts line, and the index carries one — the Owner loses the account's figure on the project page, or reads it as the project's (Owner, 2026-10-15)."""
        self.given_reading(self.usage_dir, READING_TAPPED)

        result = self.run_once(self.usage_dir)

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.lines("sample.html", outside_cards=True)
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual(len(self.lines("sample.html")), 1)
        self.assertRegex(lines[0], shows("5-hour 42%"))
        self.assertRegex(lines[0], shows("7-day 17.5%"))
        page_html = (self.out / "sample.html").read_text()
        hero_end = page_html.index("</section>", page_html.index('<section class="hero">'))
        self.assertGreater(page_html.index('class="note plan-usage"'), hero_end)
        for facts in Page(self.out / "sample.html").texts("facts"):
            self.assertNotIn("5-hour", facts)
        self.assertEqual(len(self.lines("index.html")), 1)

    def test_labels_the_plan_usage_line_as_the_plans_across_all_projects__in_the_same_words_on_both_pages(self):
        """033-B44 — on the index and the project page the line reads `Plan usage, all projects · …` and its title names the Claude plan's usage across every session, word for word the same — the account's figure reads as one project's (Owner, 2026-10-15)."""
        self.given_reading(self.usage_dir, READING_TAPPED)

        result = self.run_once(self.usage_dir)

        self.assertEqual(result.returncode, 0, result.stderr)
        seen = {}
        for name in ("index.html", "sample.html"):
            page_html = (self.out / name).read_text()
            titles = [html.unescape(t) for t in re.findall(r'<div class="note plan-usage" title="([^"]*)">', page_html)]
            self.assertEqual(len(titles), 1, name)
            self.assertIn("Claude plan's usage across every session", titles[0], name)
            seen[name] = (self.lines(name), titles[0])
        self.assertEqual(seen["index.html"][0], ["Plan usage, all projects · 5-hour 42% · 7-day 17.5% · as of 21:45:00"])
        self.assertEqual(seen["sample.html"], seen["index.html"])

    def test_reads_the_plan_usage_under_home__when_claude_usage_dir_is_unset(self):
        """P3-R3.3 — with no $CLAUDE_USAGE_DIR the line reads ~/.claude/usage/latest.json — a machine with the default tap shows no plan usage."""
        self.given_reading(self.home_usage, READING_AT_HOME)

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.lines("index.html")
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(lines[0], shows("5-hour 88%"))
        self.assertRegex(lines[0], shows("7-day 61%"))
        self.assertRegex(lines[0], shows("as of 10:10:00"))
        self.assertNotIn(HOME_AT, lines[0])

    def test_shows_only_the_five_hour_window__when_the_reading_has_no_seven_day_window(self):
        """P3-R3.4 — a reading with one window shows that window and leaves the other out — the Owner reads `None%` as a figure (assumed P3-Q2)."""
        self.given_reading(self.usage_dir, {"five_hour": {"used_percentage": 42}, "captured_at": TAPPED_AT})

        result = self.run_once(self.usage_dir)

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.lines("index.html")
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(lines[0], shows("5-hour 42%"))
        self.assertNotIn("7-day", lines[0])
        self.assertNotIn("None", lines[0])

    def test_shows_the_percentages_and_no_time__when_the_reading_has_no_captured_at(self):
        """P3-R3.5 — a reading with no captured_at shows its percentages and no time — the line reads `as of None` (assumed P3-Q3)."""
        self.given_reading(self.usage_dir, {"five_hour": {"used_percentage": 42}, "seven_day": {"used_percentage": 17.5}})

        result = self.run_once(self.usage_dir)

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.lines("index.html")
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(lines[0], shows("5-hour 42%"))
        self.assertRegex(lines[0], shows("7-day 17.5%"))
        self.assertNotIn("None", lines[0])
        self.assertNotIn("as of", lines[0])

    # P3-R4 · no reading, no line and no traceback

    def test_shows_no_plan_usage_line_and_no_traceback__when_there_is_no_reading_file(self):
        """P3-R4.1 — with no latest.json anywhere neither page has a plan-usage line, and the run does not fail — a machine on an API key gets an empty or crashing line."""
        result = self.run_once()

        self.assert_no_line_and_no_traceback(result)

    def test_shows_no_plan_usage_line_and_no_traceback__when_the_reading_is_not_valid_json(self):
        """P3-R4.2 — a torn latest.json gives no line and no traceback — one half-written tap file blanks or crashes the dashboard."""
        self.given_reading(self.usage_dir, '{"five_hour": {"used_percentage": 4')

        result = self.run_once(self.usage_dir)

        self.assert_no_line_and_no_traceback(result)

    def test_shows_no_plan_usage_line__when_the_reading_has_neither_window(self):
        """P3-R4.3 — a latest.json with a captured_at and no window is no reading — the line shows a time and no figure (assumed P3-Q1)."""
        self.given_reading(self.usage_dir, {"captured_at": TAPPED_AT})

        result = self.run_once(self.usage_dir)

        self.assert_no_line_and_no_traceback(result)

    def test_shows_no_plan_usage_line__when_claude_usage_dir_has_no_reading_though_home_does(self):
        """P3-R4.4 — a set $CLAUDE_USAGE_DIR is the only place read, as plan_usage() reads it — the line shows the default tap's reading when the Owner pointed elsewhere."""
        self.usage_dir.mkdir()
        self.given_reading(self.home_usage, READING_AT_HOME)

        result = self.run_once(self.usage_dir)

        self.assert_no_line_and_no_traceback(result)


# ================================================================ F1 · the plan-usage line's time is the reading's local
# clock time, and the index's Quiet group starts open when nothing is live. Rows are `F1-R1…` and `F1-R2…` in
# BEHAVIORS.md.

# The status-line tap's own shape: usage-tap.py writes `"captured_at": int(time.time())`, epoch seconds.
# An invented reading. `TZ=Asia/Kolkata date -r 1800000028 '+%T'` → 13:30:28 (`TZ=UTC` → 08:00:28).
TAP_EPOCH = 1800000028
NO_LIVE_NOTE = "No project has a live session right now."


class PlanUsageClock(DashScratch):
    """launch.json naming both roots; project `sample` with no session (the line does not depend on one); a reading
    under `<base>/usage` through $CLAUDE_USAGE_DIR with 5-hour 42 and 7-day 17.5 and the test's `captured_at`; every run
    under TZ=CLOCK_ZONE."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.given_project()
        self.usage_dir = self.base / "usage"

    def given_captured_at(self, captured_at):
        """latest.json with 5-hour 42, 7-day 17.5 and `captured_at` written as Python's json writes it (NaN as `NaN`)."""
        self.usage_dir.mkdir(parents=True, exist_ok=True)
        reading = {"five_hour": {"used_percentage": 42}, "seven_day": {"used_percentage": 17.5}, "captured_at": captured_at}
        (self.usage_dir / "latest.json").write_text(json.dumps(reading) + "\n")

    def run_once_and_read_line(self):
        """`--once` under CLOCK_ZONE: the run exits 0 with no traceback, and the index's one plan-usage line."""
        result = self.run_dash("--once", str(self.out), env_usage=self.usage_dir, env_tz=CLOCK_ZONE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        lines = Page(self.out / "index.html").texts("plan-usage")
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def assert_percentages_and_no_time(self, line, *raw):
        """The line keeps both percentages and drops ` · as of …`, and no form of the raw value is on it."""
        self.assertRegex(line, shows("5-hour 42%"))
        self.assertRegex(line, shows("7-day 17.5%"))
        self.assertNotIn("as of", line)
        for text in raw:
            self.assertNotIn(text, line)

    # F1-R1 · accepted shapes show as a local clock time

    def test_shows_the_local_clock_time_and_not_the_number__when_captured_at_is_the_taps_int_epoch_seconds(self):
        """F1-R1.1 — the tap's int epoch shows as the local HH:MM:SS — the Owner reads `as of 1800000028`."""
        self.given_captured_at(TAP_EPOCH)

        line = self.run_once_and_read_line()

        self.assertRegex(line, shows("as of 13:30:28"))
        self.assertNotIn("1800000028", line)

    def test_shows_the_local_clock_time__when_captured_at_is_float_epoch_seconds(self):
        """F1-R1.2 — a float epoch in seconds shows as the local HH:MM:SS — a fractional reading prints raw or crashes the page."""
        self.given_captured_at(1800000028.25)

        line = self.run_once_and_read_line()

        self.assertRegex(line, shows("as of 13:30:28"))
        self.assertNotIn("1800000028", line)

    def test_shows_the_local_clock_time_of_the_instant__when_captured_at_is_an_iso_string_with_an_offset(self):
        """F1-R1.3 — an ISO-8601 string with an offset shows its instant in the local zone — the line prints the raw string, or the writer's clock instead of the Owner's."""
        self.given_captured_at("2026-09-27T09:15:00-07:00")

        line = self.run_once_and_read_line()

        self.assertRegex(line, shows("as of 21:45:00"))
        self.assertNotIn("2026-09-27", line)

    def test_shows_the_clock_time_as_written__when_captured_at_is_an_iso_string_with_no_offset(self):
        """F1-R1.4 — an ISO string with no offset is read as local time and shown as written — a zoneless reading is shifted by a zone it never named (assumed F1-Q1)."""
        self.given_captured_at("2026-09-27T09:15:00")

        line = self.run_once_and_read_line()

        self.assertRegex(line, shows("as of 09:15:00"))
        self.assertNotIn("2026-09-27", line)

    def test_shows_the_epochs_local_clock_time__when_captured_at_is_zero(self):
        """F1-R1.5 — 0 is epoch seconds like any other non-negative number — a falsy test drops a valid time (assumed F1-Q3)."""
        self.given_captured_at(0)

        line = self.run_once_and_read_line()

        self.assertRegex(line, shows("as of 05:30:00"))

    # F1-R1 · anything else drops the time and keeps the percentages

    def test_shows_the_percentages_and_no_time__when_captured_at_is_a_bool(self):
        """F1-R1.6 — a bool is not a time, though Python counts it an int — the line shows `as of True` or 05:30:01."""
        self.given_captured_at(True)

        line = self.run_once_and_read_line()

        self.assert_percentages_and_no_time(line, "True", "true")

    def test_shows_the_percentages_and_no_time__when_captured_at_is_a_non_numeric_string(self):
        """F1-R1.7 — a string that is no ISO-8601 time drops the time — the line prints the string, or the run dies on a parse error."""
        self.given_captured_at("yesterday")

        line = self.run_once_and_read_line()

        self.assert_percentages_and_no_time(line, "yesterday")

    def test_shows_the_percentages_and_no_time__when_captured_at_is_negative(self):
        """F1-R1.8 — a negative number drops the time — a before-1970 reading shows as 05:29:59."""
        self.given_captured_at(-1)

        line = self.run_once_and_read_line()

        self.assert_percentages_and_no_time(line, "-1")

    def test_shows_the_percentages_and_no_time__when_captured_at_is_past_the_platforms_time_range(self):
        """F1-R1.9 — a number no clock can show drops the time — the run dies on the OverflowError."""
        self.given_captured_at(10**20)

        line = self.run_once_and_read_line()

        self.assert_percentages_and_no_time(line, "100000000000000000000", "1e+20")

    def test_shows_the_percentages_and_no_time__when_captured_at_is_nan(self):
        """F1-R1.10 — NaN names no instant and drops the time — the line shows `as of nan`, or the run dies on the ValueError (assumed F1-Q4)."""
        self.given_captured_at(float("nan"))

        line = self.run_once_and_read_line()

        self.assert_percentages_and_no_time(line, "nan", "NaN")

    def test_shows_the_percentages_and_no_time__when_captured_at_is_a_numeric_string(self):
        """F1-R1.11 — a quoted number is neither the tap's number nor ISO-8601 — a string reading is guessed into a time (assumed F1-Q2)."""
        self.given_captured_at("1800000028")

        line = self.run_once_and_read_line()

        self.assert_percentages_and_no_time(line, "1800000028")

    def test_shows_the_percentages_and_no_time__when_captured_at_is_an_iso_string_past_the_local_range(self):
        """F1-R1.12 — an ISO string whose instant no local clock can show drops the time — the run dies on the OverflowError (U19 fixes gate F1)."""
        self.given_captured_at("9999-12-31T23:59:59-12:00")

        line = self.run_once_and_read_line()

        self.assert_percentages_and_no_time(line, "9999")

    def test_shows_the_percentages_and_no_time__when_captured_at_is_a_zoneless_iso_string_at_the_range_edge(self):
        """F1-R1.13 — a zoneless ISO string that cannot be placed in the local zone drops the time — the run dies on the ValueError (U19 fixes gate F1)."""
        self.given_captured_at("9999-12-31T23:59:59")

        line = self.run_once_and_read_line()

        self.assert_percentages_and_no_time(line, "9999")


class QuietGroup(DashScratch):
    """launch.json naming both roots; no plan-usage reading and no accounting root. The quiet project, when a test
    has a second one, is `other`, with no session."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()

    def run_once_and_read_index(self):
        result = self.run_dash("--once", str(self.out))
        self.assertEqual(result.returncode, 0, result.stderr)
        return Page(self.out / "index.html")

    def test_starts_the_quiet_group_open__when_no_project_has_a_live_session(self):
        """F1-R2.1, as U33 re-cut it — with nothing live the Quiet group starts open under the quiet crew card, and the no-live note, which restated the card, is gone — the Owner opens the index and sees no project at all (DESIGN-U33 §5 item 19)."""
        self.given_project()

        index = self.run_once_and_read_index()

        self.assertIn("Quiet site. Nothing is running.", index.text())
        self.assertNotIn(NO_LIVE_NOTE, index.text())
        self.assertIs(index.is_open("quiet"), True)

    def test_starts_the_quiet_group_collapsed__when_one_project_has_a_live_session(self):
        """F1-R2.2 — one live project keeps the Quiet group collapsed — quiet projects crowd the live ones off the Owner's screen."""
        self.given_project()
        self.given_session()
        self.given_project(name="other")

        index = self.run_once_and_read_index()

        self.assertIs(index.is_open("quiet"), False)

    def test_starts_the_quiet_group_collapsed__when_the_only_card_is_a_finished_session_awaiting_acceptance(self):
        """F1-R2.3 — a project on the index only through its awaiting-acceptance row takes the live branch — the Quiet group opens beside a card and the note contradicts it (assumed F1-Q5)."""
        self.given_project()
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))
        self.given_project(name="other")

        index = self.run_once_and_read_index()

        self.assertIn("Awaiting acceptance", index.text())
        self.assertNotIn(NO_LIVE_NOTE, index.text())
        self.assertIs(index.is_open("quiet"), False)


# ---------------------------------------------------------------- U2-R6 · the Planner's template carries the Summary column


class ProjectTemplate(unittest.TestCase):

    def task_breakdown_rows(self):
        """The template's Task Breakdown table as cells, header first, the |---| rule dropped."""
        text = TEMPLATE.read_text()
        match = re.search(r"^## Task Breakdown\b.*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
        self.assertIsNotNone(match, "PROJECT-TEMPLATE.md has no ## Task Breakdown")
        rows = [split_cells(line) for line in match.group(1).splitlines() if line.strip().startswith("|")]
        return [row for row in rows if not set("".join(row)) <= set("-: ")]

    def test_has_the_d6_header__in_the_task_breakdown(self):
        """U2-R6.1 — the template's header is D6's — new projects are planned without a Summary column."""
        header = self.task_breakdown_rows()[0]

        self.assertEqual(header, ["#", "Unit", "Summary", "Tracker", "Description", "Exploration Doc", "Size",
                                  "Complexity", "Status"])

    def test_gives_every_example_row_a_summary_cell__in_the_task_breakdown(self):
        """U2-R6.2 — every example row has the header's cell count and a filled Summary cell — a Planner copying an example writes a short row.

        Declared guard: it protects the template from an example row that lacks its Summary cell."""
        body = self.task_breakdown_rows()[1:]

        self.assertNotEqual(body, [])
        self.assertEqual([(row[0], len(row)) for row in body if len(row) != 9], [])
        self.assertEqual([row[0] for row in body if not row[2]], [])


# ---------------------------------------------------------------- 023-U1 · a busy session on a finished unit: the follow-up pass


# A polish pass the Lead started on SLUG's unit, named for a slug with the unit's number.
FOLLOW_UP = "worker-opus-sample-001-first-polish"
EXPLAINER = "explainer-sample-001-first"
HELD_WHERE = "Waiting on the Lead's owner brief"


class FollowUpPass(DashScratch):
    """launch.json naming both roots; project `sample`, whose robowright.json asks for an owner brief; a worktree for
    SLUG that no main holds. Each test writes SLUG's session (finished and through intake unless it says otherwise),
    the owner brief when the session is released, and the one live agent the row is about."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.folder = self.given_project()
        self.given_settings(self.folder, "robowright.json", {"owner_brief": True})
        self.worktree = self.given_worktree_not_in_main()

    def given_released_session(self):
        """SLUG finished, through intake, its owner brief written: nothing holds it for the Lead."""
        run_dir = self.given_finished_session(worktree=str(self.worktree))
        self.given_owner_brief(self.folder)
        return run_dir

    def given_held_session(self):
        """SLUG finished and through intake, no owner brief: the Lead holds it, `Built · waiting on the Lead's owner brief`."""
        return self.given_finished_session(worktree=str(self.worktree))

    def given_explainer_prefix(self, prefix):
        """launch.json as given_launch_roots writes it, plus `roles.explainer.name_prefix`."""
        self.given_launch_settings(sessions_root=str(self.sessions), projects_root=str(self.projects),
                                   roles={"explainer": {"name_prefix": prefix}})

    @staticmethod
    def dead_pid():
        """The pid of a process that has exited and been reaped."""
        probe = subprocess.Popen([sys.executable, "-c", "pass"])
        probe.wait()
        return probe.pid

    def where_lines(self):
        """The where phrase of every In flight row on the index: its now line's first span."""
        index = (self.out / "index.html").read_text()
        return [html.unescape(where) for where in re.findall(r'<div class="now"><span(?: title="[^"]*")?>([^<]*)</span>', index)]

    def label(self):
        """SLUG's card label on the project page: the summary's state word, not the run units' rows in the card's body."""
        return Page(self.out / "sample.html").texts("st", card=SLUG)

    # F1 · a busy agent named for the finished unit is a follow-up pass

    def test_shows_the_card_working_on_a_follow_up_pass__when_a_busy_agent_is_named_for_the_finished_unit(self):
        """023-U1-F1.1 — a busy session named for a finished unit shows the card working again — the Owner accepts work a polish pass is still changing (assumed Q1)."""
        self.given_released_session()
        self.given_live_agent(FOLLOW_UP, "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("All units done · follow-up pass by worker-opus-sample-001-first-polish", self.where_lines())
        self.assertEqual(self.label(), ["Working"])
        self.assertTrue(Page(self.out / "sample.html").texts("now", card=SLUG)[0].startswith(
            "All units done · follow-up pass by worker-opus-sample-001-first-polish"))

    def test_lists_the_session_live_and_its_unit_working__when_a_busy_agent_is_named_for_the_finished_unit(self):
        """023-U1-F1.2 — the text summary counts a follow-up pass as live work — the summary says awaiting acceptance while the unit is still changing (assumed Q1, Q8)."""
        self.given_released_session()
        self.given_live_agent(FOLLOW_UP, "busy", cwd=self.cwd)

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn([SLUG, "done"], [line.split()[:2] for line in result.stdout.splitlines()])
        self.assertIn("working", unit_line(result.stdout, "U1"))

    def test_shows_the_follow_up_pass_and_not_the_owner_brief_hold__when_a_held_session_has_a_busy_agent_named_for_its_unit(self):
        """023-U1-F1.3 — a follow-up pass outranks the owner-brief hold — the card says the Lead owes a brief while a pass is still running (assumed Q1)."""
        self.given_held_session()
        self.given_live_agent(FOLLOW_UP, "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("All units done · follow-up pass by worker-opus-sample-001-first-polish", self.where_lines())
        self.assertNotIn(HOLD_PHRASE, self.pages())

    def test_shows_the_follow_up_pass_stuck__when_nothing_was_written_for_longer_than_the_stuck_limit(self):
        """023-U1-F1.4 — a follow-up pass is watched for silence like any working session — a hung polish pass reads as active forever (assumed Q7)."""
        run_dir = self.given_released_session()
        written = time.time() - 45 * 60
        for path in run_dir.iterdir():
            os.utime(path, (written, written))
        self.given_live_agent(FOLLOW_UP, "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Stuck? · nothing written for", Page(self.out / "index.html").text())

    # F2 · a busy agent in the finished unit's worktree is a follow-up pass, whatever its name

    def test_shows_the_card_working_on_a_follow_up_pass__when_a_busy_agent_runs_in_the_finished_units_worktree(self):
        """023-U1-F2.1 — a busy session in the unit's worktree is a follow-up pass under any name — a pass the Lead named freely goes unseen."""
        self.given_released_session()
        self.given_live_agent("task-dash-fixes", "busy", cwd=self.worktree)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("All units done · follow-up pass by task-dash-fixes", self.where_lines())

    # F3 · an Explainer on the finished unit is the Lead's owner brief in progress, not a follow-up

    def test_holds_the_card_for_the_owner_brief_in_progress__when_a_busy_explainer_is_named_for_the_finished_unit(self):
        """023-U1-F3.1 — a busy Explainer reads as the owner brief being written — the card says the brief is not started, or calls the Explainer more building."""
        self.given_held_session()
        self.given_live_agent(EXPLAINER, "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("The Lead's owner brief in progress", self.where_lines())
        pages = self.pages()
        self.assertNotIn(HOLD_PHRASE, pages)
        self.assertNotIn("follow-up pass", pages)

    # F4 · the Planner and the Lead are never a follow-up pass

    def test_keeps_the_held_card_as_it_was__when_a_busy_planner_is_named_for_the_finished_unit(self):
        """023-U1-F4.1 — a Planner named for the unit is not a follow-up pass — a Planner reading a finished brief turns the card working (assumed Q5)."""
        self.given_held_session()
        self.given_live_agent("planner-sample-001-first", "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HELD_WHERE, self.where_lines())
        self.assertNotIn("follow-up pass", self.pages())

    def test_keeps_the_held_card_as_it_was__when_a_busy_lead_runs_in_the_finished_units_worktree(self):
        """023-U1-F4.2 — the Lead is not a follow-up pass, even in the unit's worktree — the Lead's own intake turns the card working (assumed Q4, Q5)."""
        self.given_held_session()
        self.given_live_agent("lead-sample", "busy", cwd=self.worktree)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HELD_WHERE, self.where_lines())
        self.assertNotIn("follow-up pass", self.pages())

    # F5 · only a busy agent, and only on a finished session

    def test_keeps_the_held_card_as_it_was__when_the_agent_named_for_the_finished_unit_is_idle(self):
        """023-U1-F5.1 — an idle session is not a follow-up pass — a finished pass left open keeps the unit working forever (assumed Q5)."""
        self.given_held_session()
        self.given_live_agent(FOLLOW_UP, "idle", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HELD_WHERE, self.where_lines())
        self.assertNotIn("follow-up pass", self.pages())

    def test_shows_no_follow_up_pass__when_the_session_is_still_implementing(self):
        """023-U1-F5.2 — only a finished session has a follow-up pass — a running session's card claims all its units are done (assumed Q6)."""
        self.given_session(worktree=str(self.worktree))
        self.given_live_agent(FOLLOW_UP, "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(Page(self.out / "sample.html").card(SLUG), "")
        self.assertNotIn("follow-up pass", self.pages())

    # F6 · the Explainer prefix is launch.json's roles.explainer.name_prefix

    def test_holds_the_card_for_the_owner_brief_in_progress__when_a_busy_agent_carries_launch_jsons_explainer_prefix(self):
        """023-U1-F6.1 — launch.json's Explainer prefix names the Explainer — an install's renamed Explainer shows as more building."""
        self.given_explainer_prefix("guide")
        self.given_held_session()
        self.given_live_agent("guide-sample-001-first", "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("The Lead's owner brief in progress", self.where_lines())
        self.assertNotIn("follow-up pass", self.pages())

    def test_shows_the_follow_up_pass__when_a_busy_agent_carries_the_default_explainer_prefix_under_another_one(self):
        """023-U1-F6.2 — under another Explainer prefix, `explainer-` is an ordinary name — the default prefix is read from a literal and the setting is ignored."""
        self.given_explainer_prefix("guide")
        self.given_held_session()
        self.given_live_agent(EXPLAINER, "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("All units done · follow-up pass by explainer-sample-001-first", self.where_lines())

    # F7 · only a live row of $HOME's registry is seen

    def test_keeps_the_held_card_as_it_was__when_the_busy_agents_registry_file_is_outside_homes_registry(self):
        """023-U1-F7.1 — the registry is $HOME's `.claude/sessions` and nowhere else — a project's own `.claude/` passes for a live session (assumed Q3, Q5)."""
        self.given_held_session()
        self.given_live_agent(FOLLOW_UP, "busy", cwd=self.cwd, registry=self.cwd / ".claude" / "sessions")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HELD_WHERE, self.where_lines())
        self.assertNotIn("follow-up pass", self.pages())

    def test_keeps_the_held_card_as_it_was__when_the_busy_agents_pid_is_dead(self):
        """023-U1-F7.2 — a registry row whose process has exited is not live — a crashed pass keeps the unit working forever (assumed Q5)."""
        self.given_held_session()
        self.given_live_agent(FOLLOW_UP, "busy", cwd=self.cwd, pid=self.dead_pid())

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HELD_WHERE, self.where_lines())
        self.assertNotIn("follow-up pass", self.pages())


# ---------------------------------------------------------------- 023-U2 · filed by run.json.project, claimed by run.json.ticket, the brief under review_guide_dir


ORPHANS_HEADING = "Sessions with no project folder"
NOT_CLAIMED = "Not claimed by any unit"
RERUN = "sample-001-first-rerun"
# A tracker install's key, and the `unit` block of examples/desktop/launch.json that makes it one.
TRACKER = "SMPL-482"
TRACKER_UNIT = {
    "ticket_regex": "^[A-Z][A-Z0-9]+-[0-9]+$",
    "ticket_example": "SMPL-482",
    "slug_regex": "^[a-z0-9]+(-[a-z0-9]+)*$",
    "slug_example": "export-csv",
    "group_regex": "^([A-Z][A-Z0-9]*)-[0-9]+(-[a-z0-9]+)*$",
}
# PROJECT_MD's Task Breakdown header, for plans whose Unit cells a test writes itself.
PLAN_HEADER = "| # | Unit | Description | Repo | Size | Complexity | Status |"


class Binding(DashScratch):
    """launch.json naming both roots; project `sample`, one Task Breakdown row `first`. Each test writes SLUG's session,
    implementing, with the `run.json.project` the row is about."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.given_project()

    def card_on(self, page_name):
        """SLUG's card on the page `--once` wrote as `<page_name>.html`, or "" when that page has none."""
        return Page(self.out / f"{page_name}.html").card(SLUG)

    @staticmethod
    def live_lines(stdout, project):
        """The plain summary's live-session lines under `project`'s head, each as its first two words (slug, phase)."""
        lines = text_of(stdout).splitlines()
        start = next((i for i, line in enumerate(lines) if line.startswith(f"{project}: ")), None)
        if start is None:
            return None
        block = []
        for line in lines[start + 1:]:
            if not line.startswith(" "):
                break
            block.append(line.split()[:2])
        return block

    # B1 · run.json.project files the session

    def test_files_the_session_under_its_run_json_project__when_its_directory_name_captures_another(self):
        """023-U2-B1.1 — a session is filed under its run.json.project — a session the Lead filed under one project shows on another's page."""
        self.given_project(name="other")
        self.given_session(project="other")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card_on("other"), "")
        self.assertEqual(self.card_on("sample"), "")

    def test_lists_the_live_session_under_its_run_json_project_in_the_summary__when_its_directory_name_captures_another(self):
        """023-U2-B1.2 — the summary lists a session under its run.json.project — the terminal counts another project's work as this one's (assumed Q1)."""
        self.given_project(name="other")
        self.given_session(project="other")

        result = self.run_dash()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn([SLUG, "implement"], self.live_lines(result.stdout, "other") or [])
        self.assertIsNotNone(self.live_lines(result.stdout, "sample"))
        self.assertNotIn([SLUG, "implement"], self.live_lines(result.stdout, "sample"))

    # B2 · no usable run.json.project: the directory name's capture

    def test_files_the_session_under_the_capture__when_run_json_project_is_null(self):
        """023-U2-B2.1 — a null project falls back to the directory name's capture — every one-off and older session leaves its page."""
        self.given_session(project=None)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card_on("sample"), "")

    def test_files_the_session_under_the_capture__when_run_json_project_is_an_empty_string(self):
        """023-U2-B2.2 — an empty project falls back to the capture — a blank field files the session nowhere."""
        self.given_session(project="")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card_on("sample"), "")

    def test_files_the_session_under_the_capture__when_run_json_project_is_not_a_string(self):
        """023-U2-B2.3 — a project that is not a string falls back to the capture — a malformed run.json breaks the page or loses the session (assumed Q4)."""
        self.given_session(project=["other"])

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card_on("sample"), "")

    def test_files_a_brief_being_written_under_the_capture__when_its_session_dir_has_no_run_json(self):
        """023-U2-B2.4 — a session with no run.json is filed by the capture — a brief in progress drops off its project's page."""
        (self.sessions / SLUG).mkdir()
        self.given_live_agent(f"planner-{SLUG}", "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card_on("sample"), "")

    # B3 · a project with no folder is an orphan

    def test_lists_the_session_with_no_project_folder__when_run_json_project_names_a_folder_that_does_not_exist(self):
        """023-U2-B3.1 — a project with no PROJECT.md leaves the session an orphan on the index — the session vanishes from every page."""
        self.given_session(project="ghost")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        index = Page(self.out / "index.html")
        self.assertIn(ORPHANS_HEADING, index.text())
        self.assertNotEqual(index.card(SLUG), "")
        self.assertEqual(self.card_on("sample"), "")


class TicketClaim(DashScratch):
    """launch.json naming both roots. Each test writes the plan, and one implementing session whose `run.json.ticket` the
    row is about. A row's state on the project page links each session it claims, labelled by the session's number,
    or by its slug when the slug has none."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()

    def given_plan(self, name, *rows):
        """Project `name` whose Task Breakdown is PLAN_HEADER and `rows`."""
        folder = self.projects / name
        folder.mkdir(parents=True)
        (folder / "PROJECT.md").write_text(project_md(PLAN_HEADER, *rows))
        return folder

    def plan_states(self, project="sample"):
        """Each Task Breakdown row's state on `project`'s page, by unit id."""
        page = Page(self.out / f"{project}.html")
        return dict(zip(page.texts("id", outside_cards=True), page.texts("state", outside_cards=True)))

    # B4 · a tracker key is claimed by the row whose Unit cell it is

    def test_claims_the_tracker_session_for_its_row__when_run_json_ticket_equals_the_unit_cell(self):
        """023-U2-B4.1 — a row claims the session whose ticket is its Unit cell — every tracker-key session reads as unplanned."""
        self.given_launch_settings(sessions_root=str(self.sessions), projects_root=str(self.projects), unit=TRACKER_UNIT)
        self.given_plan(TRACKER, f"| U1 | `{TRACKER}` | The sample's tracker unit | sample | S | low | in progress |")
        self.given_session(slug=TRACKER, ticket=TRACKER, project=TRACKER)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(TRACKER, self.plan_states(TRACKER).get("U1", ""))
        self.assertNotIn(NOT_CLAIMED, Page(self.out / f"{TRACKER}.html").text())

    # B5 · a ticket claim is the session's only claim

    def test_claims_the_session_for_the_row_its_ticket_names__when_another_row_matches_its_directory_name(self):
        """023-U2-B5.1 — the ticket claim comes before the name rule — a rerun is counted under the row its name happens to match."""
        self.given_plan("sample",
                        "| U1 | `sample-001-first` | The sample's first unit | sample | S | low | in progress |",
                        "| U2 | `sample-001-first-rerun` | The first unit, run again | sample | S | low | in progress |")
        self.given_session(slug=RERUN, ticket=SLUG)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("001", self.plan_states().get("U1", ""))

    def test_leaves_the_session_off_the_row_its_name_matches__when_an_earlier_row_claims_it_by_ticket(self):
        """023-U2-B5.2 — a session claimed by ticket is no other row's — one session's points are earned twice."""
        self.given_plan("sample",
                        "| U1 | `sample-001-first` | The sample's first unit | sample | S | low | in progress |",
                        "| U2 | `sample-001-first-rerun` | The first unit, run again | sample | S | low | in progress |")
        self.given_session(slug=RERUN, ticket=SLUG)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        states = self.plan_states()
        self.assertIn("U2", states)
        self.assertNotIn("001", states["U2"])

    def test_claims_the_session_for_the_later_row_its_ticket_names__and_not_the_earlier_row_its_name_matches(self):
        """023-U2-B5.3 — every row's ticket claim runs before any name claim — an earlier row's name match steals a later row's ticketed session."""
        self.given_plan("sample",
                        "| U1 | `sample-001-first-rerun` | The first unit, run again | sample | S | low | in progress |",
                        "| U2 | `sample-001-first` | The sample's first unit | sample | S | low | in progress |")
        self.given_session(slug=RERUN, ticket=SLUG)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        states = self.plan_states()
        self.assertIn("001", states.get("U2", ""))
        self.assertIn("U1", states)
        self.assertNotIn("001", states["U1"])

    def test_claims_the_session_for_the_first_row_in_table_order__when_two_rows_share_its_ticket_and_the_todo_lists_the_later_first(self):
        """023-U2-B5.4 — two rows with one Unit cell: the first in table order claims the session — the work order, not the table, decides whose points it earns."""
        folder = self.given_plan("sample",
                                 "| U1 | `sample-001-first` | The sample's first unit | sample | S | low | in progress |",
                                 "| U2 | `sample-001-first` | The first unit, again | sample | S | low | in progress |")
        (folder / "PROJECT.md").write_text((folder / "PROJECT.md").read_text()
                                           + "\n## Detailed TODO\n\n### Stage 1\n\n- **U2** again\n- **U1** first\n")
        self.given_session(slug=RERUN, ticket=SLUG)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        states = self.plan_states()
        self.assertIn("001", states.get("U1", ""))
        self.assertIn("U2", states)
        self.assertNotIn("001", states["U2"])

    # B8 · no ticket claim: the name rule

    def test_claims_the_session_by_its_directory_name__when_run_json_ticket_is_null(self):
        """023-U2-B8.1 — a session with no ticket is claimed by its name — sessions launched without a ticket go unplanned."""
        self.given_project()
        self.given_session(ticket=None)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("001", self.plan_states().get("U1", ""))

    def test_claims_the_session_by_its_directory_name__when_run_json_ticket_matches_no_unit_cell(self):
        """023-U2-B8.2 — a ticket that is no row's Unit cell leaves the name rule in force — every slug-install session whose row names it short goes unplanned."""
        self.given_project()
        self.given_session(ticket=SLUG)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("001", self.plan_states().get("U1", ""))


class TicketlessSession(DashScratch):
    """065-T1: launch.json naming both roots; project `sample` planning U1 `export-csv`; a bare-slug session
    `export-csv` with no ticket, filed under `sample`; the accounting root `<base>/accounting`."""

    given_ledger = Spend.given_ledger
    run_once = Spend.run_once
    spend = Spend.spend
    plan_states = TicketClaim.plan_states

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        folder = self.projects / "sample"
        folder.mkdir(parents=True)
        (folder / "PROJECT.md").write_text(project_md(PLAN_HEADER, "| U1 | `export-csv` | Exports notes as CSV | sample | S | low | in progress |"))
        self.session = self.given_session(slug="export-csv", ticket=None, project="sample", **DOLLAR_BRIEF)
        self.accounting = self.base / "accounting"

    def test_claims_and_prices_a_session_with_no_ticket__by_its_directory_name(self):
        """065-T1 — the row whose Unit cell is the directory name claims the session, and its card sums the records
        whose unit is that name — its unit id is the directory name, as the launcher reads it (the U65 note)."""
        self.given_ledger(
            ledger_record("export-csv", "worker", "w-1", 12, 3_400, 1.25, 1_800, session_dir=self.session),
            ledger_record("export-csv", "reviewer", "r-1", 5, 1_100, 0.40, 1_080, session_dir=self.session),
            ledger_record(SLUG, "worker", "w-2", 3, 600, 0.20, 360),
        )

        result = self.run_once()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("export-csv", self.plan_states().get("U1", ""))
        spend = self.spend(card="export-csv")
        self.assertEqual(len(spend), 1, spend)
        self.assertRegex(spend[0], shows("17 requests"))
        self.assertRegex(spend[0], shows("$1.65 est."))


class OwnerBriefDirectory(DashScratch):
    """launch.json naming both roots and `review_guide_dir: "guides"`; project `sample`, whose robowright.json asks for
    an owner brief; SLUG done, through intake, its worktree not in main — so only the owner brief can still hold it."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.given_review_guide_dir("guides")
        self.folder = self.given_project()
        self.given_settings(self.folder, "robowright.json", {"owner_brief": True})
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

    def given_review_guide_dir(self, directory):
        """launch.json as given_launch_roots writes it, plus `review_guide_dir`."""
        self.given_launch_settings(sessions_root=str(self.sessions), projects_root=str(self.projects),
                                   review_guide_dir=directory)

    def given_brief_under(self, directory):
        """SLUG's owner brief, one Decide-now ask (ASK_EXPORT), at `<folder>/<directory>/<SLUG>-owner-brief.md`."""
        under = self.folder / directory
        under.mkdir()
        (under / f"{SLUG}-owner-brief.md").write_text(BRIEF_ONE_ASK)

    def card(self):
        return Page(self.out / "sample.html").card(SLUG)

    # B6 · the owner brief is read from review_guide_dir

    def test_releases_the_session__when_its_owner_brief_is_under_launch_jsons_review_guide_dir(self):
        """023-U2-B6.1 — the hold reads the brief from review_guide_dir — a briefed session stays with the Lead on an install that writes briefs elsewhere."""
        self.given_brief_under("guides")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card(), "")
        self.assertNotIn(HOLD_PHRASE, self.pages())

    def test_shows_the_briefs_ask_on_the_card__when_the_brief_is_under_launch_jsons_review_guide_dir(self):
        """023-U2-B6.2 — the Decide-now asks are read from review_guide_dir — the Owner sees no question the brief asks (assumed Q7)."""
        self.given_brief_under("guides")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        card = self.card()
        self.assertRegex(card, shows("1 ask"))
        self.assertIn(ASK_EXPORT, card)

    def test_holds_the_session__when_its_owner_brief_is_only_under_reviews_and_launch_json_names_another_dir(self):
        """023-U2-B6.3 — a brief outside review_guide_dir does not release the hold — a stale brief in the old place hands the Owner unbriefed work."""
        self.given_brief_under("reviews")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HOLD_PHRASE, self.pages())

    def test_shows_no_asks_line__when_the_owner_brief_is_only_under_reviews_and_launch_json_names_another_dir(self):
        """023-U2-B6.4 — asks come only from review_guide_dir — the card shows questions from a brief the launcher no longer writes."""
        self.given_brief_under("reviews")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card(), "")
        self.assertEqual(Page(self.out / "sample.html").texts("asks", card=SLUG), [])

    # B7 · `reviews` when launch.json gives no directory (the absent key is R5.1–R5.5's Given)

    def test_releases_the_session_by_its_brief_under_reviews__when_review_guide_dir_is_empty(self):
        """023-U2-B7.2 — an empty review_guide_dir means `reviews` — a blank key holds every briefed session for the Lead."""
        self.given_review_guide_dir("")
        self.given_brief_under("reviews")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.card(), "")
        self.assertNotIn(HOLD_PHRASE, self.pages())


# ---------------------------------------------------------------- prepub-3 · escaping, the Host check, bad numbers

# Folder names a session writer controls; each ends an attribute and opens one of its own if written raw.
LIVE_NAME = 'x" data-injected="live'
QUIET_NAME = 'y" data-injected="quiet'
INJECTED = "data-injected"


class Tags(HTMLParser):
    """Every start tag on a page as (tag, {attribute: value}), values unescaped as a browser reads them."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def hrefs(self):
        return {attrs["href"] for tag, attrs in self.tags if tag == "a" and "href" in attrs}

    def attribute_names(self):
        return {name for _, attrs in self.tags for name in attrs}


class Hostile(DashScratch):
    """launch.json naming both roots. Project LIVE_NAME holds SLUG, stopped (a Needs-attention row and a live card), and
    `sample-002-second`, implementing (an In-flight row); project QUIET_NAME has no session (a Quiet row)."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()

    def given_hostile_projects(self):
        self.given_project(name=LIVE_NAME)
        self.given_project(name=QUIET_NAME)
        self.given_session(project=LIVE_NAME, phase="stopped", stop_reason={"code": "verification-failed", "detail": "x"})
        self.given_session(slug="sample-002-second", project=LIVE_NAME)

    def serve(self):
        """`--serve` on a free port, answering: (port, get) where get(path, host) is (status, body) of one GET with that
        Host header."""
        port = free_port()
        server = subprocess.Popen([sys.executable, str(DASH), "--serve", str(port)], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, env=self.env(), cwd=str(self.cwd))
        self.addCleanup(lambda: server.poll() is None and server.kill())

        def get(path, host):
            request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": host})
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    return response.status, response.read().decode()
            except urllib.error.HTTPError as err:
                return err.code, err.read().decode()

        deadline = time.monotonic() + 20
        while server.poll() is None and time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                return port, get
            except OSError:
                time.sleep(0.1)
        self.fail("the dashboard never answered")

    # H1 · a folder name is written inert

    def test_writes_no_attribute_of_the_folder_names_own__when_a_project_folder_name_carries_a_quote(self):
        """prepub-3-H1.1 — every page --once writes keeps a quoted folder name inside its attribute — a folder name runs script on the dashboard."""
        self.given_hostile_projects()

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        for page_file in sorted(self.out.glob("*.html")):
            self.assertNotIn(INJECTED, Tags(page_file.read_text()).attribute_names(), page_file.name)

    def test_links_each_project_by_its_url_quoted_folder_name__when_the_name_carries_a_quote(self):
        """prepub-3-H1.2 — the index links a quoted folder name URL-quoted, from every row kind — a link that drops the name's tail opens the wrong page."""
        self.given_hostile_projects()

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        live, quiet = quote(LIVE_NAME, safe=""), quote(QUIET_NAME, safe="")
        self.assertLessEqual({f"{live}.html", f"{live}.html#s-{SLUG}", f"{live}.html#s-sample-002-second", f"{quiet}.html"},
                             Tags((self.out / "index.html").read_text()).hrefs())

    def test_serves_the_project_page_its_index_link_names__when_the_folder_name_carries_a_quote(self):
        """prepub-3-H1.3 — the served index links /p/<URL-quoted name>, and that link finds the folder by exact name — the escape breaks the lookup."""
        self.given_hostile_projects()
        port, get = self.serve()
        host = f"127.0.0.1:{port}"

        _, index = get("/", host)
        link = f"/p/{quote(LIVE_NAME, safe='')}"
        status, page_body = get(link, host)

        self.assertIn(link, Tags(index).hrefs())
        self.assertEqual(status, 200)
        self.assertIn(f"s-{SLUG}", page_body)

    def test_writes_no_element_of_the_planners_own__when_its_registry_status_carries_markup(self):
        """prepub-3-H1.4 — the Planner's live-registry status is escaped in the In-flight row — a registry value writes markup onto the dashboard."""
        self.given_project()
        (self.sessions / SLUG).mkdir(parents=True)
        self.given_live_agent(f"planner-{SLUG}", f'<b {INJECTED}="status">busy', cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        index = (self.out / "index.html").read_text()
        self.assertTrue("&lt;b" in index, "the status is not on the page escaped")
        self.assertNotIn(INJECTED, Tags(index).attribute_names())

    # H2 · the Host check

    def test_refuses_the_request__when_its_host_is_not_loopback_with_the_dashboards_port(self):
        """prepub-3-H2.1 — a Host other than loopback plus the port gets 403 — a rebound DNS name reads every page."""
        self.given_project()
        port, get = self.serve()

        statuses = {host: get("/", host)[0] for host in
                    (f"attacker.example:{port}", "attacker.example", f"localhost:{port + 1}", f"127.0.0.1:{port + 1}")}

        self.assertEqual(statuses, dict.fromkeys(statuses, 403))

    def test_serves_the_request__when_its_host_is_loopback_or_localhost_with_the_dashboards_port(self):
        """prepub-3-H2.2 — 127.0.0.1:<port> and localhost:<port> are served — the check locks the Owner out of their own dashboard."""
        self.given_project()
        port, get = self.serve()

        statuses = {host: get("/", host)[0] for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"LOCALHOST:{port}")}

        self.assertEqual(statuses, dict.fromkeys(statuses, 200))

    # H3 · a bad number renders as absent

    def test_renders_the_session_without_a_wall_meter__when_max_wall_hours_is_not_a_number(self):
        """prepub-3-H3.1 — a non-numeric max_wall_hours shows no wall budget — a session blanks the page it sits on."""
        self.given_project()
        self.given_session(max_wall_hours="eight")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        card = Page(self.out / "sample.html").card(SLUG)
        self.assertNotEqual(card, "")
        self.assertNotIn("eight", card)

    def test_renders_the_session_without_a_wall_meter__when_max_wall_hours_is_not_finite_or_overflows_a_float(self):
        """prepub-3-H3.3 — NaN, Infinity and an integer past a float's range show no wall budget — a session blanks or garbles its row."""
        for value in (float("nan"), float("inf"), 10 ** 400):
            with self.subTest(value=str(value)[:12]):
                shutil.rmtree(self.roots, ignore_errors=True)
                shutil.rmtree(self.out, ignore_errors=True)
                self.given_launch_roots()
                self.given_project()
                self.given_session(max_wall_hours=value)

                result = self.run_dash("--once", str(self.out))

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotEqual(Page(self.out / "sample.html").card(SLUG), "")
                self.assertEqual(Page(self.out / "sample.html").texts("meter", card=SLUG), [])

    def test_renders_the_session_without_a_wall_meter__when_max_wall_hours_is_a_boolean(self):
        """prepub-3-H3.4 — `true` is not an hour count and shows no wall budget — a flag reads as a one-hour budget."""
        self.given_project()
        self.given_session(max_wall_hours=True)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(Page(self.out / "sample.html").card(SLUG), "")
        self.assertEqual(Page(self.out / "sample.html").texts("meter", card=SLUG), [])

    def test_renders_the_held_unit_with_an_absent_limit__when_max_gate_attempts_is_not_a_number(self):
        """prepub-3-H3.2 — a non-numeric max_gate_attempts reads as no limit: `round 1 of ?` — a session blanks the page it sits on."""
        self.given_project()
        self.given_session(max_gate_attempts="three",
                           units=[{"id": "U1", "status": "held", "gate_attempts": 1}, {"id": "U2", "status": "todo"}])

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("round 1 of ?", self.pages())


# ---------------------------------------------------------------- dash-brand · the robot mark, brass, favicon, wordmark


# U26's art in Whiteprint: the mark the header and the favicon are drawn from, and its two ink colours.
ART_MARK = REPO / "assets" / "logo-mark-light.svg"
ART_LINE, ART_BRASS = "#12325A", "#A87300"
TRIANGLE_PATH = "M2 2v12h12L2 2Z"
BRAND_PAGES = ("index.html", "sample.html")


def paint(attrs, prop):
    """An element's `fill` or `stroke`: its `style` declaration if it has one, else its presentation attribute."""
    for declaration in (attrs.get("style") or "").split(";"):
        name, _, value = declaration.partition(":")
        if name.strip() == prop:
            return value.strip()
    return attrs.get(prop)


def drawing(svg_text):
    """Each shape of an SVG, keyed by its tag and its position (`d`, `cx` or `y`), to its (fill, stroke) and the rest
    of its geometry; plus the <svg>'s viewBox and each <g>'s transform."""
    shapes = {(tag, attrs.get("d") or attrs.get("cx") or attrs.get("y")):
              ((paint(attrs, "fill"), paint(attrs, "stroke")),
               sorted((k, v) for k, v in attrs.items() if k not in ("fill", "stroke", "style")))
              for tag, attrs in Tags(svg_text).tags if tag in ("circle", "rect", "ellipse", "path")}
    frames = {(tag, None): attrs.get("viewbox" if tag == "svg" else "transform")
              for tag, attrs in Tags(svg_text).tags if tag in ("svg", "g")}
    return {**shapes, **frames}


def art_drawing(line, brass, ring_fill):
    """The art's mark with its line colour read as `line`, its brass as `brass`, and the ring filled `ring_fill`."""
    inks = {ART_LINE: line, ART_BRASS: brass}
    shapes = {key: ((tuple(inks.get(value, value) for value in entry[0]), entry[1]) if isinstance(entry, tuple) else entry)
              for key, entry in drawing(ART_MARK.read_text()).items()}
    colours, geometry = shapes[("circle", None)]
    shapes[("circle", None)] = ((ring_fill, colours[1]), geometry)
    return shapes


def css_rules(page_text):
    """Every rule in a page's <style> blocks as (selectors, declarations)."""
    css = "".join(re.findall(r"<style>(.*?)</style>", page_text, re.S))
    return [([sel.strip() for sel in selectors.split(",")], body)
            for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def declared(body, prop):
    match = re.search(rf"(?:^|;){re.escape(prop)}:([^;]*)", body)
    return match and match.group(1).strip()


class Brand(DashScratch):
    """launch.json naming both roots; project `sample` with SLUG implementing; one `--once` run."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.given_project()
        self.given_session()
        result = self.run_dash("--once", str(self.out))
        self.assertEqual(result.returncode, 0, result.stderr)

    def page_text(self, name):
        return (self.out / name).read_text()

    def header_mark(self, name):
        """The first <svg> inside the page's <nav>, as written."""
        nav = re.search(r"<nav>(.*?)</nav>", self.page_text(name), re.S).group(1)
        return re.search(r"<svg\b.*?</svg>", nav, re.S).group(0)

    def favicons(self, name):
        head = re.search(r"<head>(.*?)</head>", self.page_text(name), re.S).group(1)
        return [attrs.get("href", "") for tag, attrs in Tags(head).tags
                if tag == "link" and "icon" in (attrs.get("rel") or "").split()]

    def test_defines_the_arts_brass_in_every_theme__when_a_page_is_written(self):
        """dash-brand-B1.1 — each theme declares the art's brass — the mark's braces and cursor paint in no colour on that theme."""
        themes = {selectors[0][len(":root[data-theme="):-1]: declared(body, "--brass")
                  for selectors, body in css_rules(self.page_text("index.html"))
                  if selectors[0].startswith(":root[data-theme=")}

        self.assertEqual(themes, {"whiteprint": "#A87300", "blueprint": "#F2C14E", "night": "#F2C14E"})

    def test_draws_the_arts_robot_mark_in_the_header__on_every_page(self):
        """dash-brand-B2.1 — the header's mark is the art's, line work in currentColor and accents in var(--brass) — the dashboard drifts from the README's logo."""
        for name in BRAND_PAGES:
            with self.subTest(page=name):
                mark = self.header_mark(name)

                self.assertEqual(Tags(mark).tags[0][1].get("aria-hidden"), "true")
                self.assertEqual(drawing(mark), art_drawing("currentColor", "var(--brass)", "none"))

    def test_carries_no_triangle_mark__on_any_page(self):
        """dash-brand-B2.2 — the ◣ triangle is gone from every page — the old mark lingers beside, or instead of, the new one."""
        for name in BRAND_PAGES:
            with self.subTest(page=name):
                self.assertNotIn(TRIANGLE_PATH, self.page_text(name))

    def test_links_an_inline_svg_favicon__on_every_page(self):
        """dash-brand-B3.1 — the head links one icon, an inline SVG data URI — the tab shows no mark, or the page fetches a file."""
        for name in BRAND_PAGES:
            with self.subTest(page=name):
                icons = self.favicons(name)

                self.assertEqual(len(icons), 1, icons)
                self.assertTrue(icons[0].startswith("data:image/svg+xml,"), icons[0][:40])

    def test_paints_the_favicon_in_whiteprints_line_and_brass_on_a_transparent_ground__on_every_page(self):
        """dash-brand-B3.2 — the favicon is the art's mark in fixed Whiteprint ink, ring unfilled — a CSS variable a lone SVG cannot resolve leaves the tab icon blank."""
        for name in BRAND_PAGES:
            with self.subTest(page=name):
                icon = unquote(self.favicons(name)[0].partition(",")[2])

                self.assertEqual(drawing(icon), art_drawing(ART_LINE, ART_BRASS, "none"))

    def test_reads_the_wordmark_in_lowercase__on_every_page(self):
        """dash-brand-B4.1 — the wordmark reads `robowright` — the header disagrees with the README's logo."""
        for name in BRAND_PAGES:
            with self.subTest(page=name):
                self.assertEqual(Page(self.out / name).texts("brand"), ["robowright"])

    def test_sets_the_wordmark_in_the_mono_font_stack__in_the_stylesheet(self):
        """dash-brand-B4.2 — `.brand` uses `.mono`'s font family — the wordmark falls back to the sans body face."""
        families = {sel: declared(body, "font-family") for selectors, body in css_rules(self.page_text("index.html"))
                    for sel in selectors if sel in (".brand", ".mono") and declared(body, "font-family")}

        self.assertIsNotNone(families.get(".mono"))
        self.assertEqual(families.get(".brand"), families[".mono"])

    def test_keeps_the_index_title_capitalised__when_the_wordmark_is_lowercase(self):
        """dash-brand-B5.1 — the index's <title> stays `Robowright` — the browser tab and bookmarks change name."""
        self.assertEqual(re.search(r"<title>(.*?)</title>", self.page_text("index.html")).group(1), "Robowright")


# ================================================================ 029-U1 · figures and row glyphs: the `note-brass` token,
# the art read from the clone's assets/ and tokenised, the figure for a session's observable state, and a glyph above
# every session row in Needs attention and In flight. Rows are `029-U1.…` in BEHAVIORS.md. Every expected figure is
# read from the art files themselves, so a glyph that drifts from the art reddens.


ROLE_ART = REPO / "assets" / "roles"
HERO_ART = REPO / "assets" / "hero-light.svg"
# The hero's Owner, and the path its light bulb begins with: the dashboard's Owner stops before it.
OWNER_GROUP = '<g transform="translate(84 600)">'
BULB_START = "M0 -132V-122"
ROBOT_ROLES = ("worker", "lead", "planner", "reviewer")
# Art exists for these two, but no observable state names them, so no row may draw them.
UNDRAWN_ROLES = ("reader", "explainer")
ART_PAPER = "#F4F7FA"
# The art's Whiteprint inks as a glyph paints them: a robot's, and the Owner's, whose paper fills become the figure fill.
ROBOT_INKS = {ART_LINE: "currentColor", ART_BRASS: "var(--brass)"}
OWNER_INKS = {ART_LINE: "currentColor", ART_BRASS: "var(--brass)", ART_PAPER: "var(--fig-fill)"}
# The keys every theme declares besides `note-brass`.
BASE_THEME_KEYS = {"bg", "surface", "fg", "muted", "faint", "line", "track", "done", "run", "attn", "attn-text", "attn-bg",
                   "attn-line", "idle", "brand", "brass", "grid", "note-bg", "note-line", "note-hover", "note-fg",
                   "note-muted", "note-faint", "note-attn", "note-run", "note-done"}
# One session per drawn figure, all under project `sample`.
FIVE_FIGURES = {SLUG: "owner", SECOND: "lead", "sample-003-third": "planner", "sample-004-fourth": "reviewer",
                "sample-005-fifth": "worker"}
ROBOT_FIGURES = {slug: role for slug, role in FIVE_FIGURES.items() if role != "owner"}
# The row glyph's viewBoxes and stroke widths (to one decimal, in the art's document order): head and stalk 6.0,
# braces 8.4, each prop stroke the art's × 1.2; the Owner's every stroke the hero's × 2.3.
ROW_ROBOT_VIEWBOX = (-50.0, -54.0, 154.0, 100.0)
ROW_OWNER_VIEWBOX = (-26.0, -137.0, 64.0, 135.1)
ROW_ROBOT_STROKES = {"worker": [6.0, 6.0, 8.4, 8.4, 8.5, 6.9], "lead": [6.0, 6.0, 8.4, 8.4, 5.3, 4.0],
                     "planner": [6.0, 6.0, 8.4, 8.4, 5.3, 5.3, 4.0], "reviewer": [6.0, 6.0, 8.4, 8.4, 5.3, 5.3, 5.3, 5.3]}
ROW_OWNER_STROKES = [7.4, 7.4, 6.4, 7.4, 6.9, 7.8]


def art_shapes(svg_text):
    """Each shape an SVG draws, in document order, as (key, attributes): a path keyed by its `d`, a rect by x and y, a
    circle by cx, cy and r, an ellipse by cx and cy."""
    keys = {"path": ("d",), "rect": ("x", "y"), "circle": ("cx", "cy", "r"), "ellipse": ("cx", "cy")}
    return [((tag, *(attrs.get(name) for name in keys[tag])), attrs) for tag, attrs in Tags(svg_text).tags if tag in keys]


def robot_art(role):
    """A role's -light.svg inner group: what sits inside its outer `<g transform="translate(…) scale(…)">`; the tile
    and the grid outside that group are left behind."""
    text = (ROLE_ART / f"{role}-light.svg").read_text()
    start = text.index("<g transform")
    return text[text.index(">", start) + 1:text.rindex("</g>")]


def owner_art():
    """The hero's Owner group, from `<g transform="translate(84 600)">` to its own `</g>`."""
    text = HERO_ART.read_text()
    start = text.index(OWNER_GROUP)
    depth = 0
    for tag in re.finditer(r"<g\b|</g>", text[start:]):
        depth += -1 if tag.group() == "</g>" else 1
        if depth == 0:
            return text[start:start + tag.end()]
    raise ValueError("the hero's Owner group never closes")


def owner_figure_art():
    """(the Owner's shapes before the bulb, the bulb's shapes), from the hero's group."""
    shapes = art_shapes(owner_art())
    bulb = next(i for i, (key, _) in enumerate(shapes) if key == ("path", BULB_START))
    return shapes[:bulb], shapes[bulb:]


def is_face_or_collar(key):
    """The eyes, smile and collar the row Owner drops: a circle of r 2.4 or 2.6, a path `M-5 -106Q…` or `M-6 -92L…`."""
    return (key[0] == "circle" and key[3] in ("2.4", "2.6")) or (key[0] == "path" and key[1].startswith(("M-5 -106Q", "M-6 -92L")))


def role_marks():
    """Each figure's path `d`s that no other figure's art draws: a robot's from its -light.svg inner group, the Owner's
    from the hero's group before the bulb."""
    drawn = {role: {key[1] for key, _ in art_shapes(robot_art(role)) if key[0] == "path"} for role in ROBOT_ROLES + UNDRAWN_ROLES}
    drawn["owner"] = {key[1] for key, _ in owner_figure_art()[0] if key[0] == "path"}
    return {role: paths - set().union(*(other for name, other in drawn.items() if name != role)) for role, paths in drawn.items()}


def roles_drawn(svg_text):
    """The figures whose own paths an SVG draws."""
    paths = {key[1] for key, _ in art_shapes(svg_text) if key[0] == "path"}
    return {role for role, marks in role_marks().items() if marks & paths}


def inked(shapes, inks):
    """Each shape's key to its (fill, stroke), each colour read through `inks`."""
    return {key: tuple(inks.get(value, value) for value in (paint(attrs, "fill"), paint(attrs, "stroke"))) for key, attrs in shapes}


def stroke_widths(svg_text):
    """Every stroke width an SVG's shapes set, in document order, to one decimal."""
    return [round(float(paint(attrs, "stroke-width")), 1) for _, attrs in art_shapes(svg_text) if paint(attrs, "stroke-width")]


def group_transforms(svg_text):
    return [attrs["transform"] for tag, attrs in Tags(svg_text).tags if tag == "g" and attrs.get("transform")]


def view_box(svg_text):
    """The <svg>'s viewBox as four numbers, or None when it has none."""
    box = Tags(svg_text).tags[0][1].get("viewbox")
    return tuple(float(n) for n in re.split(r"[\s,]+", box.strip())) if box else None


def classed(markup, token):
    """Every element of `markup` whose class list holds `token`, as its tag."""
    return [tag for tag, attrs in Tags(markup).tags if token in (attrs.get("class") or "").split()]


def first_text(markup):
    """The first non-blank text in `markup`, unescaped."""
    return next((html.unescape(piece).strip() for piece in re.split(r"<[^>]*>", markup) if piece.strip()), "")


def session_href(slug, project="sample"):
    """The href an index row links a session's card with, as `--once` writes it."""
    return f'{quote(project, safe="")}.html#s-{slug}'


class GlyphScratch(DashScratch):
    """launch.json naming both roots. Each test writes its world, runs `--once` once, and reads the index's rows."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()

    # ------------------------------------------------------------ given

    def given_stopped(self, slug=SLUG):
        return self.given_session(slug=slug, phase="stopped",
                                  stop_reason={"code": "verification-failed", "detail": "the sample's suite is red"})

    def given_briefing(self, slug=SLUG):
        """`slug`'s session folder with no run.json yet, and its Planner live and busy: a brief being written."""
        (self.sessions / slug).mkdir(parents=True)
        self.given_live_agent(f"planner-{slug}", "busy", cwd=self.cwd)

    def given_running_direct_build(self):
        """SLUG as a direct build: no session folder, nothing in prs/, a busy live Worker named for it."""
        self.given_live_agent(f"worker-{SLUG}", "busy", cwd=self.cwd)

    def given_finished_direct_build(self):
        """SLUG as a direct build whose change description is in the project's prs/, its Worker idle in a worktree no
        main holds: finished, and the Lead's to check."""
        prs = self.projects / "sample" / "prs"
        prs.mkdir(parents=True)
        (prs / f"{SLUG}.md").write_text("# Change description\n")
        self.given_live_agent(f"worker-{SLUG}", "idle", cwd=self.given_worktree_not_in_main())

    # ------------------------------------------------------------ when

    def when_written(self, script=DASH):
        """`--once <out>`: exit 0 and no traceback; the index as written."""
        result = self.run_dash("--once", str(self.out), script=script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.index = (self.out / "index.html").read_text()
        return self.index

    # ------------------------------------------------------------ then

    def row(self, href):
        """(attributes, inner markup) of the index's `a.row` linking `href`, never the crew member linking it too; the test
        fails when there is none."""
        match = re.search(rf'<a\b(?=[^>]*\bclass="row\b)[^>]*\bhref="{re.escape(href)}"[^>]*>(.*?)</a>', self.index, re.S)
        if match is None:
            self.fail(f"the index has no row linking {href}")
        return Tags(match.group(0)).tags[0][1], match.group(1)

    def main(self, href):
        """The markup inside the row's `<div class="main">`, to the row's end."""
        _, inner = self.row(href)
        _, found, rest = inner.partition('<div class="main">')
        self.assertTrue(found, inner[:200])
        return rest

    def glyph(self, href):
        """The <svg> the row's `.main` opens with, inside `<span class="gl" aria-hidden="true">`; the test fails when the
        `.main` opens with anything else."""
        main = self.main(href)
        match = re.match(r'<span class="gl" aria-hidden="true">\s*(<svg\b.*?</svg>)\s*</span>', main, re.S)
        if match is None:
            self.fail(f"the row linking {href} opens its .main with {main[:80]!r}, not the glyph")
        return match.group(1)

    def assert_figure(self, slug, role, project="sample"):
        """`slug`'s row opens with an aria-hidden, unfocusable glyph drawing `role`'s figure and no other's."""
        svg = self.glyph(session_href(slug, project))
        opening = Tags(svg).tags[0][1]
        self.assertEqual((opening.get("aria-hidden"), opening.get("focusable")), ("true", "false"))
        self.assertEqual(roles_drawn(svg), {role})

    def assert_bare(self, href):
        """The row linking `href` drawn without a figure: its `.main` opens with the head's name, no `.gl` in it, no class `g`."""
        attrs, inner = self.row(href)
        self.assertTrue(self.main(href).startswith('<div class="head"><span class="name mono">'), self.main(href)[:80])
        self.assertEqual(classed(inner, "gl"), [])
        self.assertNotIn("g", (attrs.get("class") or "").split())


# ---------------------------------------------------------------- 029-U1 R1 · `note-brass`; R8 · the glyph's CSS


class GlyphStyles(GlyphScratch):
    """Project `sample` with SLUG implementing; one `--once` run."""

    def setUp(self):
        super().setUp()
        self.given_project()
        self.given_session()
        self.when_written()

    def style(self):
        return "".join(re.findall(r"<style>(.*?)</style>", self.index, re.S))

    def theme_rules(self):
        return {selectors[0][len(":root[data-theme="):-1]: body for selectors, body in css_rules(self.index)
                if selectors[0].startswith(":root[data-theme=")}

    def test_declares_note_brass_per_theme__when_a_page_is_written(self):
        """029-U1.1.1 — every theme declares `--note-brass`: #A87300, #A87300, #F2C14E — brass on the peach paper paints in no colour, or in a contrast-failing one."""
        themes = {name: declared(body, "--note-brass") for name, body in self.theme_rules().items()}

        self.assertEqual(themes, {"whiteprint": "#A87300", "blueprint": "#A87300", "night": "#F2C14E"})

    def test_remaps_brass_to_note_brass_on_the_needs_attention_paper__in_the_stylesheet(self):
        """029-U1.1.2 — `#attention .list{--brass:var(--note-brass)}` is in the stylesheet — a glyph's braces on the peach paper keep Blueprint's pale brass."""
        self.assertIn("#attention .list{--brass:var(--note-brass)}", self.style())

    def test_adds_only_note_brass_to_each_themes_keys__when_a_page_is_written(self):
        """029-U1.1.3 — each theme's keys are `BASE_THEME_KEYS` plus `note-brass` — a figure token leaks into THEMES, or an existing token goes missing."""
        keys = {name: set(re.findall(r"(?:^|;)--([\w-]+):", body)) for name, body in self.theme_rules().items()}

        self.assertEqual(keys, dict.fromkeys(("whiteprint", "blueprint", "night"), BASE_THEME_KEYS | {"note-brass"}))

    def test_aligns_a_glyph_row_with_the_specs_rules__in_the_stylesheet(self):
        """029-U1.8.1, as U33 re-cut it — the glyph box and the head rules are in the stylesheet verbatim — the glyph block or the state sit off the name (DESIGN-U33 §4.6, §4.7 rule 2)."""
        for rule in (".srow .gl{display:flex;align-items:flex-end;height:30px;margin:0 0 4px;--fig-fill:none}",
                     ".srow .head{display:flex;align-items:baseline;gap:14px}"):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.style())


# ---------------------------------------------------------------- 029-U1 R2 · the figure for a session's state; R3 · the row Owner


class RowFigure(GlyphScratch):
    """Project `sample` with U1 `first`; each test writes one session, SLUG, in the state its row is about."""

    def setUp(self):
        super().setUp()
        self.folder = self.given_project()

    def test_draws_the_owner_above_the_row__when_a_working_session_has_a_stop_file(self):
        """029-U1.2.1 — a STOP file draws the Owner though the session is implementing — the Owner reads a running robot on a session waiting on them."""
        run_dir = self.given_session()
        (run_dir / "STOP").write_text("")

        self.when_written()

        self.assert_figure(SLUG, "owner")

    def test_draws_the_owner_above_the_row__when_the_session_stopped(self):
        """029-U1.2.2 — a stopped session draws the Owner — a stop that needs the Owner reads as someone else's."""
        self.given_stopped()

        self.when_written()

        self.assert_figure(SLUG, "owner")

    def test_draws_the_owner_above_the_row__when_run_json_is_unreadable(self):
        """029-U1.2.3 — an unreadable run.json (tone `unknown`) draws the Owner — a broken session reads as running."""
        run_dir = self.given_session()
        (run_dir / "run.json").write_text("{")

        self.when_written()

        self.assert_figure(SLUG, "owner")

    def test_draws_the_owner_above_the_row__when_a_rebrief_needs_the_owners_call(self):
        """029-U1.2.4 — a rebrief whose verdict is the Owner's (tone `owner-call`) draws the Owner — the call waits unseen behind a Lead."""
        self.given_session(rotate={"requested_at": iso(datetime.now(timezone.utc)), "reason": "rebrief"},
                           rebriefs=[{"n": 1, "verdict": "owner", "why": "the sample's scope moved"}])

        self.when_written()

        self.assert_figure(SLUG, "owner")

    def test_draws_the_lead_above_the_row__when_the_session_is_briefed(self):
        """029-U1.2.5 — a briefed session draws the Lead, though it sits in Needs attention — ready-to-launch reads as a stop."""
        self.given_session(phase="briefed")

        self.when_written()

        self.assert_figure(SLUG, "lead")

    def test_draws_the_lead_above_the_row__when_the_session_is_rotating(self):
        """029-U1.2.6 — a rotating session draws the Lead — a hand-off reads as the Worker still building."""
        self.given_session(rotate={"requested_at": iso(datetime.now(timezone.utc)), "reason": "context"})

        self.when_written()

        self.assert_figure(SLUG, "lead")

    def test_draws_the_lead_above_the_row__when_a_finished_session_waits_on_the_leads_intake(self):
        """029-U1.2.7 — a finished session with no INTAKE.md (tone `intake`) draws the Lead — work with the Lead reads as still building."""
        self.given_session(phase="done", worktree=str(self.given_worktree_not_in_main()))

        self.when_written()

        self.assert_figure(SLUG, "lead")

    def test_draws_the_lead_above_the_row__when_a_finished_direct_build_waits_on_the_leads_check(self):
        """029-U1.2.8 — a finished direct build (tone `intake`, stage `check`) draws the Lead, not a Worker — `kind: direct` is matched before tone `intake` and finished work reads as still building."""
        self.given_finished_direct_build()

        self.when_written()

        self.assert_figure(SLUG, "lead")

    def test_draws_the_planner_above_the_row__when_a_brief_is_being_written(self):
        """029-U1.2.9 — a session folder with no run.json and a busy Planner draws the Planner — a brief in writing reads as a build."""
        self.given_briefing()

        self.when_written()

        self.assert_figure(SLUG, "planner")

    def test_draws_the_planner_above_the_row__when_a_stopped_session_has_a_busy_planner(self):
        """029-U1.2.10 — a stopped session whose Planner is busy is `rebriefing` and draws the Planner — the figure reads run.json's `stopped` and shows the Owner while the Planner rewrites the brief."""
        self.given_stopped()
        self.given_live_agent(f"planner-{SLUG}-r1", "busy", cwd=self.cwd)

        self.when_written()

        self.assert_figure(SLUG, "planner")

    def test_draws_a_worker_above_the_row__when_a_direct_build_is_running(self):
        """029-U1.2.11 — a running direct build draws a Worker — a build with no session folder gets no figure, or another role's."""
        self.given_running_direct_build()

        self.when_written()

        self.assert_figure(SLUG, "worker")

    def test_draws_the_reviewer_above_the_row__when_the_session_is_in_its_end_of_stack_review(self):
        """029-U1.2.12 — a working session in phase `end-of-stack` draws the Reviewer — the final review reads as more building."""
        self.given_session(phase="end-of-stack")

        self.when_written()

        self.assert_figure(SLUG, "reviewer")

    def test_draws_a_worker_above_the_row__when_the_session_is_implementing(self):
        """029-U1.2.13 — a working session implementing a unit draws a Worker — the commonest row draws the wrong role."""
        self.given_session()

        self.when_written()

        self.assert_figure(SLUG, "worker")

    def test_draws_a_worker_above_the_row__when_a_finished_session_has_a_busy_follow_up_pass(self):
        """029-U1.2.14 — a done session with a busy follow-up pass is `working` and draws a Worker — the follow-up row has no figure."""
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))
        self.given_live_agent(FOLLOW_UP, "busy", cwd=self.cwd)

        self.when_written()

        self.assert_figure(SLUG, "worker")

    def test_draws_the_row_owner_without_eyes_smile_or_collar__when_the_session_stopped(self):
        """029-U1.3.1 — the row Owner has no r 2.4/2.6 circle, no `M-5 -106Q`, no `M-6 -92L` — sub-pixel detail turns the face to mush."""
        self.given_stopped()

        self.when_written()

        glyph = self.glyph(session_href(SLUG))
        self.assertEqual(roles_drawn(glyph), {"owner"})
        self.assertNotRegex(glyph, r'<circle\b[^>]*\br="2\.[46]"')
        self.assertNotIn("M-5 -106Q", glyph)
        self.assertNotIn("M-6 -92L", glyph)

    def test_draws_the_row_owner_without_the_light_bulb__when_the_session_stopped(self):
        """029-U1.3.2 — no shape from the hero's bulb (from `M0 -132V-122` on) is in the row Owner — the website's Owner carries the hero's idea bulb."""
        self.given_stopped()

        self.when_written()

        glyph = self.glyph(session_href(SLUG))
        self.assertEqual(roles_drawn(glyph), {"owner"})
        bulb = {key for key, _ in owner_figure_art()[1]}
        self.assertEqual([key for key, _ in art_shapes(glyph) if key in bulb], [])


# ---------------------------------------------------------------- 029-U1 R4 · the glyph takes no column


class RowPlacement(GlyphScratch):
    """Project `sample` with U1 `first`; the sessions each test names."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def assert_one_left_edge(self, href):
        """The row is classed `row srow`, and its one dot sits inside its state at the right end."""
        attrs, inner = self.row(href)
        self.assertLessEqual({"row", "srow"}, set((attrs.get("class") or "").split()))
        self.assertEqual(len(classed(inner, "dot")), 1)
        self.assertNotIn('class="dot', re.sub(r'<span class="st[^"]*">.*?</span>', "", inner, flags=re.S))

    def test_keeps_the_rows_one_dot_in_its_state__when_a_needs_attention_row_carries_a_glyph(self):
        """029-U1.4.1, as U33 re-cut it — a Needs attention session row is `row srow` and its only dot is in its state — the dot returns to the left edge as a second marker beside the figure (DESIGN-U33 §4.7 rule 4)."""
        self.given_stopped()

        self.when_written()

        self.assert_one_left_edge(session_href(SLUG))

    def test_keeps_the_rows_one_dot_in_its_state__when_an_in_flight_row_carries_a_glyph(self):
        """029-U1.4.2, as U33 re-cut it — an In flight session row is `row srow` and its only dot is in its state — the flight dot returns beside the figure (DESIGN-U33 §4.7 rule 4)."""
        self.given_session()

        self.when_written()

        self.assert_one_left_edge(session_href(SLUG))

    def test_puts_the_name_right_after_the_glyph_and_first_in_text__in_both_lists(self):
        """029-U1.4.3 — the glyph span is followed by the head's `.name`, and the name is `.main`'s first text — a glyph column shifts the name, or the glyph speaks."""
        self.given_stopped()
        self.given_session(slug=SECOND)

        self.when_written()

        for slug, name in ((SLUG, "001-first"), (SECOND, "002-second")):
            with self.subTest(slug=slug):
                main = self.main(session_href(slug))
                self.assertRegex(main, r'(?s)^<span class="gl" aria-hidden="true">\s*<svg\b.*?</svg>\s*</span><div class="head"><span class="name mono">')
                self.assertEqual(first_text(main), name)

    def test_draws_no_glyph_on_the_awaiting_acceptance_row__beside_a_session_row_that_has_one(self):
        """029-U1.4.4 — the "Awaiting acceptance" row has no `.gl` and no `g`, while a stopped row beside it has its glyph — a unit row grows a robot it is not (assumed Q1)."""
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))
        self.given_stopped(slug=SECOND)

        self.when_written()

        self.glyph(session_href(SECOND))
        self.assertEqual(first_text(self.main("sample.html#plan")), "Awaiting acceptance")
        attrs, inner = self.row("sample.html#plan")
        self.assertEqual(classed(inner, "gl"), [])
        self.assertNotIn("g", (attrs.get("class") or "").split())

    def test_draws_no_glyph_on_the_project_pages_rows__only_on_its_session_cards(self):
        """029-U1.4.5 (reversed by U31) — on the project page no `.row` carries `g` or a `.gl`; the only `.gl`s are the two on-site cards', each the first child of a `<summary>` — the plan rows grow figures and shift. Until U31 this row said the page had no `.gl` and no `g` at all; U31 puts the glyph on the Needs attention and Working cards (Owner 2026-10-14, DESIGN-U31 "The delta"), rows 031-P1.1–P5.1."""
        self.given_session()
        self.given_stopped(slug=SECOND)

        self.when_written()

        self.glyph(session_href(SLUG))
        project_page = (self.out / "sample.html").read_text()
        rows = [attrs for tag, attrs in Tags(project_page).tags if "row" in (attrs.get("class") or "").split()]
        self.assertTrue(rows, "the project page has no rows")
        self.assertEqual([attrs for attrs in rows if "g" in (attrs.get("class") or "").split()], [])
        self.assertEqual(len(classed(project_page, "gl")), 2)
        self.assertEqual(len(re.findall(r'<summary><span class="gl"', project_page)), 2)


# ---------------------------------------------------------------- 029-U1 R5 · the art tokenised; R9 · the row proportions


class GlyphArt(GlyphScratch):
    """Project `sample` with one session per drawn figure (FIVE_FIGURES): SLUG stopped, SECOND briefed,
    `sample-003-third` briefing, `sample-004-fourth` in its end-of-stack review, `sample-005-fifth` implementing; one
    `--once` run."""

    def setUp(self):
        super().setUp()
        self.given_project()
        self.given_stopped()
        self.given_session(slug=SECOND, phase="briefed")
        self.given_briefing("sample-003-third")
        self.given_session(slug="sample-004-fourth", phase="end-of-stack")
        self.given_session(slug="sample-005-fifth")
        self.when_written()

    def test_writes_no_art_colour_and_no_accessible_name__in_any_row_glyph(self):
        """029-U1.5.1 — no glyph carries #12325A, #A87300 or #F4F7FA, a <title>, `role=` or `aria-label=` — a figure ignores the theme, or a screen reader reads a decoration."""
        for slug in FIVE_FIGURES:
            with self.subTest(slug=slug):
                glyph = self.glyph(session_href(slug)).lower()

                found = [mark for mark in ("#12325a", "#a87300", "#f4f7fa", "<title", "role=", "aria-label=") if mark in glyph]

                self.assertEqual(found, [])

    def test_paints_each_robot_shape_in_current_color_and_brass__as_its_art_inks_it(self):
        """029-U1.5.2 — each robot glyph draws exactly its art's inner-group shapes, line ink as currentColor and brass as var(--brass) — a shape goes missing or keeps a fixed colour (assumed Q7)."""
        for slug, role in ROBOT_FIGURES.items():
            with self.subTest(role=role):
                glyph = self.glyph(session_href(slug))

                self.assertEqual(inked(art_shapes(glyph), {}), inked(art_shapes(robot_art(role)), ROBOT_INKS))

    def test_paints_the_row_owner_in_current_color_brass_and_the_figure_fill__as_the_hero_inks_it(self):
        """029-U1.5.3 — the row Owner draws the hero group's shapes before the bulb, less face and collar, paper fills as var(--fig-fill) — the Owner's body paints the hero's paper on the peach note (assumed Q7)."""
        glyph = self.glyph(session_href(SLUG))
        kept = [shape for shape in owner_figure_art()[0] if not is_face_or_collar(shape[0])]

        self.assertEqual(inked(art_shapes(glyph), {}), inked(kept, OWNER_INKS))

    def test_frames_each_row_glyph_in_its_specs_view_box(self):
        """029-U1.9.1 — a row robot's viewBox is -50 -54 154 100 and the row Owner's -26 -137 64 135.1 — the glyph is cropped, or its left edge leaves the name's first character."""
        for slug, role in FIVE_FIGURES.items():
            with self.subTest(role=role):
                expected = ROW_OWNER_VIEWBOX if role == "owner" else ROW_ROBOT_VIEWBOX

                self.assertEqual(view_box(self.glyph(session_href(slug))), expected)

    def test_strokes_each_row_robot_at_the_row_weights__head_braces_and_props_as_the_spec_sets_them(self):
        """029-U1.9.2 — a row robot's strokes are 6.0, 6.0, 8.4, 8.4, then each prop stroke × 1.2 — the glyph is drawn at the crew's weights or the art's, too thin at 28 px (assumed Q6)."""
        for slug, role in ROBOT_FIGURES.items():
            with self.subTest(role=role):
                self.assertEqual(stroke_widths(self.glyph(session_href(slug))), ROW_ROBOT_STROKES[role])

    def test_strokes_the_row_owner_at_the_heros_weights_scaled_for_thirty_pixels(self):
        """029-U1.9.3 — the row Owner's strokes are the hero's × 2.3: 7.4, 7.4, 6.4, 7.4, 6.9, 7.8 — the 30 px Owner is drawn in hairlines (assumed Q2, Q6)."""
        self.assertEqual(stroke_widths(self.glyph(session_href(SLUG))), ROW_OWNER_STROKES)

    def test_keeps_only_the_arts_inner_transforms__in_each_row_glyph(self):
        """029-U1.9.4 — a robot glyph keeps its prop's `translate(50 10) scale(1.35) translate(-50 -10)` and drops the tile's outer group; the Owner keeps only its arm's rotate — the figure lands off its viewBox (assumed Q7)."""
        for slug, role in FIVE_FIGURES.items():
            with self.subTest(role=role):
                expected = group_transforms(owner_art())[1:] if role == "owner" else group_transforms(robot_art(role))

                self.assertEqual(group_transforms(self.glyph(session_href(slug))), expected)


# ---------------------------------------------------------------- 029-U1 R6 · a missing or unreadable asset


class GlyphFallback(GlyphScratch):
    """Project `sample`; the dashboard run from a scratch copy of the clone, so an asset can be missing without any
    new input to point the loader elsewhere."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def given_clone_copy(self, missing=(), unreadable=()):
        """A scratch copy of the clone at <base>/clone: the dashboard script, skills/ (the scripts it loads and the
        tables they read) and assets/, with each `missing` asset deleted and each `unreadable` one a directory in its
        file's place. Returns the copied script."""
        clone = self.base / "clone"
        (clone / "tools").mkdir(parents=True)
        shutil.copyfile(DASH, clone / "tools" / "robowright-dash.py")
        shutil.copytree(REPO / "skills", clone / "skills", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "assets", clone / "assets")
        for name in (*missing, *unreadable):
            (clone / "assets" / name).unlink()
        for name in unreadable:
            (clone / "assets" / name).mkdir()
        return clone / "tools" / "robowright-dash.py"

    def test_draws_no_figure_on_the_row_whose_role_art_is_missing__and_still_draws_the_others(self):
        """029-U1.6.1 — with roles/worker-light.svg gone the Worker's row renders bare, exit 0, and the Lead's keeps its figure — one missing file crashes the page or blanks every glyph (assumed Q1)."""
        self.given_session()
        self.given_session(slug=SECOND, phase="briefed")
        script = self.given_clone_copy(missing=["roles/worker-light.svg"])

        self.when_written(script=script)

        self.assert_bare(session_href(SLUG))
        self.assert_figure(SECOND, "lead")

    def test_draws_no_owner_on_the_row__when_the_hero_art_is_missing(self):
        """029-U1.6.2 — with hero-light.svg gone the Owner's row renders bare, exit 0, and a Worker's keeps its figure — the Owner's source missing crashes the page (assumed Q1)."""
        self.given_stopped()
        self.given_session(slug=SECOND)
        script = self.given_clone_copy(missing=["hero-light.svg"])

        self.when_written(script=script)

        self.assert_bare(session_href(SLUG))
        self.assert_figure(SECOND, "worker")

    def test_draws_no_figure_on_the_row__when_its_role_art_cannot_be_read(self):
        """029-U1.6.3 — a directory where roles/worker-light.svg should be renders the Worker's row bare, exit 0, and the Lead's keeps its figure — an unreadable file is a traceback (assumed Q1, Q3)."""
        self.given_session()
        self.given_session(slug=SECOND, phase="briefed")
        script = self.given_clone_copy(unreadable=["roles/worker-light.svg"])

        self.when_written(script=script)

        self.assert_bare(session_href(SLUG))
        self.assert_figure(SECOND, "lead")


# ---------------------------------------------------------------- 029-U1 R7 · hostile names never reach a glyph


class GlyphHostile(GlyphScratch):
    """The hostile world (`given_hostile_projects`): project LIVE_NAME holds SLUG, stopped (a Needs attention row), and
    SECOND, implementing (an In flight row); project QUIET_NAME has no session."""

    given_hostile_projects = Hostile.given_hostile_projects

    def test_carries_nothing_of_a_hostile_name_or_slug__in_either_rows_glyph(self):
        """029-U1.7.1 — neither glyph holds the project name raw, `e()`-escaped or URL-quoted, `data-injected`, or the slug — a figure interpolates session data (assumed Q4)."""
        self.given_hostile_projects()

        self.when_written()

        for slug in (SLUG, SECOND):
            with self.subTest(slug=slug):
                glyph = self.glyph(session_href(slug, LIVE_NAME))

                found = [value for value in (LIVE_NAME, html.escape(LIVE_NAME), quote(LIVE_NAME, safe=""), INJECTED, slug)
                         if value in glyph]

                self.assertEqual(found, [])

    def test_escapes_the_hostile_rows_as_at_base__when_they_carry_glyphs(self):
        """029-U1.7.2 — each hostile row links its URL-quoted card, names its slug first, and carries no `data-injected` attribute — the glyph's insertion breaks the row's escaping."""
        self.given_hostile_projects()

        self.when_written()

        for slug in (SLUG, SECOND):
            with self.subTest(slug=slug):
                attrs, inner = self.row(session_href(slug, LIVE_NAME))

                self.assertNotIn(INJECTED, set(attrs) | Tags(inner).attribute_names())
                self.assertEqual(first_text(self.main(session_href(slug, LIVE_NAME))), slug)


# ---------------------------------------------------------------- 029-U2 · the crew card and the quiet state
# "On site · N" between the plan-usage line and Needs attention: one member per session on site (its figure, the
# session, a fixed doing phrase, its project), capped with a "+K more" ghost per cap the count exceeds, or the dozing
# Worker when nothing is on site. Rows are `029-U2.…` in BEHAVIORS.md. Figures are checked against the art files, as
# the row glyphs are.


SITE_OPEN = '<section class="site" aria-labelledby="site-h">'
QUIET_LINE = "Quiet site. Nothing is running."
NO_RUNNING_NOTE = "Nothing is running right now."
NO_ATTENTION_NOTE = "Nothing needs attention right now."
MONO_STACK = 'ui-monospace,"SF Mono",Menlo,monospace'
# Up to eight sessions on site under project `sample`, in the order the caps tests make them most recently active.
ON_SITE = ("sample-001-first", "sample-002-second", "sample-003-third", "sample-004-fourth", "sample-005-fifth",
           "sample-006-sixth", "sample-007-seventh", "sample-008-eighth")
# The crew figure's viewBoxes, prop placement and stroke widths, in the art's document order: head and stalk 3.5,
# braces 4.9, each prop stroke the art's × 0.945 (7.11 → 6.72, 5.78 → 5.46, 4.44 → 4.2, 3.33 → 3.15); the Owner's
# every stroke the hero's × 1.2 (legs 3.2, body 3.2, collar 2.4, arm 2.8, head 3.2, smile 2.2, hat dome 3, brim 3.4).
CREW_ROBOT_VIEWBOX = (-50.0, -54.0, 136.0, 90.0)
CREW_OWNER_VIEWBOX = (-26.0, -137.0, 64.0, 135.1)
CREW_PROP_TRANSFORM = "translate(-7 0)"
CREW_ROBOT_STROKES = {"worker": [3.5, 3.5, 4.9, 4.9, 6.72, 5.46], "lead": [3.5, 3.5, 4.9, 4.9, 4.2, 3.15],
                      "planner": [3.5, 3.5, 4.9, 4.9, 4.2, 4.2, 3.15], "reviewer": [3.5, 3.5, 4.9, 4.9, 4.2, 4.2, 4.2, 4.2]}
CREW_OWNER_STROKES = [3.84, 3.84, 2.88, 3.36, 3.84, 2.64, 3.6, 4.08]
# How far a crew stroke may sit from its exact product: 3.15 (3.33 × 0.945) is on a rounding edge.
STROKE_SLACK = 0.06
# The dozing Worker's eyes as (cx, cy, rx, ry): the art's eye ellipses at cy 6, rx 7, ry 1.8, closed lids.
DOZING_EYES = [(-13.0, 6.0, 7.0, 1.8), (13.0, 6.0, 7.0, 1.8)]
# A slug and a unit id carrying markup syntax: an element nothing defines, with the hostile world's inert attribute.
HOSTILE_SLUG = 'sample-003-<x data-injected="slug">'
HOSTILE_ANCHOR = "s-sample-003--x-data-injected--slug--"
HOSTILE_UNIT_ID = 'U9 <x data-injected="id">'
# The exact /attention.json body for CrewJson's world: SECOND stopped, `sample-003-third` briefed, U1 awaiting acceptance.
# `sample-004-fourth` is running and on site, so it is not a row.
ATTENTION_JSON = (
    '[{"key": "/p/sample#s-sample-002-second|Stopped \\u00b7 verification-failed", "project": "sample", '
    '"title": "002-second", "what": "Stopped \\u00b7 verification-failed", "href": "/p/sample#s-sample-002-second"}, '
    '{"key": "/p/sample#s-sample-003-third|Briefed \\u00b7 ready to launch", "project": "sample", "title": "003-third", '
    '"what": "Briefed \\u00b7 ready to launch", "href": "/p/sample#s-sample-003-third"}, '
    '{"key": "/p/sample#plan|U1 first", "project": "sample", "title": "Awaiting acceptance", "what": "U1 first", '
    '"href": "/p/sample#plan"}]')


def label(markup, cls):
    """The text of the first `<span>` of class `cls` in `markup`, unescaped and stripped; None when there is none."""
    match = re.search(rf'<span class="(?:[^"]*\s)?{cls}(?:\s[^"]*)?"[^>]*>(.*?)</span>', markup, re.S)
    return html.unescape(match.group(1)).strip() if match else None


def words(markup):
    """The text of `markup` as one whitespace-collapsed line, unescaped."""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", markup)).split())


class Voiced(HTMLParser):
    """The text of some markup a screen reader reads (`spoken`), and the text inside `aria-hidden="true"` (`hidden`)."""

    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.stack, self.spoken_parts, self.hidden_parts = [], [], []
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self.stack.append(dict(attrs).get("aria-hidden") == "true" or bool(self.stack and self.stack[-1]))

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        (self.hidden_parts if self.stack and self.stack[-1] else self.spoken_parts).append(data)

    def spoken(self):
        return " ".join("".join(self.spoken_parts).split())

    def hidden(self):
        return " ".join("".join(self.hidden_parts).split())


def css_declarations(body):
    """A rule's declarations as {property: value}, whitespace collapsed and none around commas."""
    pairs = (declaration.partition(":") for declaration in body.split(";"))
    return {name.strip(): re.sub(r"\s*,\s*", ",", " ".join(value.split())) for name, _, value in pairs if name.strip()}


def top_level_rules(page_text):
    """Every rule of a page's <style> outside an @media or @keyframes block, comments dropped, as (selectors,
    declarations)."""
    css = re.sub(r"/\*.*?\*/", "", "".join(re.findall(r"<style>(.*?)</style>", page_text, re.S)), flags=re.S)
    css = re.sub(r"@[^{}]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    return [([" ".join(sel.split()) for sel in selectors.split(",")], css_declarations(body))
            for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def styled(page_text, selector):
    """The declarations the top-level rules give `selector`, exactly as written in a rule's selector list, merged in
    document order."""
    found = {}
    for selectors, declarations in top_level_rules(page_text):
        if selector in selectors:
            found.update(declarations)
    return found


def compounds(selector):
    return re.split(r"\s*[>+~]\s*|\s+", selector.strip())


def styled_last(page_text, last, hover=False):
    """The declarations of every top-level rule with a selector ending in the compound `last`, merged in document
    order: those under `.member:hover` when `hover`, those under no `:hover` otherwise."""
    found = {}
    for selectors, declarations in top_level_rules(page_text):
        if any(compounds(sel)[-1] == last and ((".member:hover" in sel) if hover else (":hover" not in sel))
               for sel in selectors):
            found.update(declarations)
    return found


LONG_UNIT_TAIL = "keeps-every-session-file-it-reads-to-its-shape"


def index_row(page_text, href):
    """The inside of the index row linking `href`."""
    return re.search(rf'<a class="row srow" href="{re.escape(href)}">(.*?)</a>', page_text, re.S).group(1)


def spans_of(fragment, cls):
    """The text of every <span> in `fragment` whose class list starts with `cls`."""
    return [" ".join(html.unescape(re.sub(r"<[^>]*>", "", inner)).split())
            for inner in re.findall(rf'<span class="{cls}(?: [^"]*)?"[^>]*>(.*?)</span>', fragment, re.S)]


def clamped_lines(fragment):
    """Every two-line clamped line in `fragment` as (text, title)."""
    return [(" ".join(html.unescape(text).split()), html.unescape(title))
            for title, text in re.findall(r'<div class="desc clamp2" title="([^"]*)">([^<]*)</div>', fragment)]


def card_html(page_text, slug):
    """`slug`'s session card as written, up to the next card."""
    start = page_text.index(f'id="s-{slug}"')
    end = page_text.find('<details class="sess', start)
    return page_text[start:end if end != -1 else None]


def media_rules(page_text, query):
    """Every rule inside the page's `@media <query>` blocks as (selectors, declarations)."""
    css = re.sub(r"/\*.*?\*/", "", "".join(re.findall(r"<style>(.*?)</style>", page_text, re.S)), flags=re.S)
    blocks = re.findall(rf"@media {re.escape(query)}\{{((?:[^{{}}]*\{{[^{{}}]*\}})*)[^{{}}]*\}}", css)
    return [([" ".join(sel.split()) for sel in selectors.split(",")], body)
            for block in blocks for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block)]


def rule_named(page_text, selector):
    """The declarations of every top-level rule naming exactly `selector`, merged in document order."""
    found = {}
    for selectors, declarations in top_level_rules(page_text):
        if selector in selectors:
            found.update(declarations)
    return found


def attention_word_ink(page_text):
    """The colour reaching a stopped state word on the index's attention paper: rules ending in `.st.attn`, bare or
    under `#attention`, merged in document order (the `#attention` ones are also the more specific)."""
    found = {}
    for selectors, declarations in top_level_rules(page_text):
        if any(sel == ".st.attn" or (sel.startswith("#attention ") and compounds(sel)[-1] == ".st.attn")
               for sel in selectors):
            found.update(declarations)
    return found.get("color")


def styled_line(page_text, cls):
    """The declarations reaching one label line, `.who`, `.what` or `.where`: rules ending in that class, or in a `span`
    or `*` child of `.labels`; no `:hover` rule."""
    found = {}
    for selectors, declarations in top_level_rules(page_text):
        for sel in selectors:
            parts = compounds(sel)
            is_line = parts[-1] == cls or (parts[-1] in ("span", "*") and len(parts) > 1 and parts[-2].endswith(".labels"))
            if is_line and ":hover" not in sel:
                found.update(declarations)
                break
    return found


def raw_stroke_widths(svg_text):
    """Every stroke width an SVG's shapes set, in document order, as numbers."""
    return [float(paint(attrs, "stroke-width")) for _, attrs in art_shapes(svg_text) if paint(attrs, "stroke-width")]


def flight_hrefs(index):
    """The hrefs of the In flight list's rows, in page order."""
    match = re.search(r'<details class="group" id="flight".*?</details>', index, re.S)
    return [attrs["href"] for tag, attrs in Tags(match.group(0)).tags if tag == "a"] if match else []


class CrewScratch(GlyphScratch):
    """launch.json naming both roots. Each test writes its world, runs `--once` once, and reads the index's crew card:
    `<section class="site" aria-labelledby="site-h">`, one `li` per member or ghost."""

    # ------------------------------------------------------------ given

    def given_touched(self, run_dir, minutes):
        """The session's run.json last written `minutes` ago: the most recent activity the dashboard reads."""
        at = time.time() - minutes * 60
        os.utime(run_dir / "run.json", (at, at))
        return run_dir

    def given_plan_written_long_ago(self, folder):
        """The project's PROJECT.md last written three hours ago, so its sessions alone set the project's order."""
        at = time.time() - 3 * 60 * 60
        os.utime(folder / "PROJECT.md", (at, at))

    # ------------------------------------------------------------ when

    def when_written(self, script=DASH, **env):
        """`--once <out>` with any root or usage variable the test gives: exit 0 and no traceback; the index as written."""
        result = self.run_dash("--once", str(self.out), script=script, **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.index = (self.out / "index.html").read_text()
        return self.index

    # ------------------------------------------------------------ then

    def site(self):
        """The crew card's section, as written; the test fails when the index has none."""
        match = re.search(rf"{re.escape(SITE_OPEN)}.*?</section>", self.index, re.S)
        if match is None:
            self.fail("the index has no crew card")
        return match.group(0)

    def heading(self):
        match = re.search(r'<h2 id="site-h">(.*?)</h2>', self.site(), re.S)
        if match is None:
            self.fail("the crew card has no h2#site-h")
        return words(match.group(1))

    def items(self):
        """Each `li` of the card, in order: its markup as written, its classes, its first element's tag and attributes
        (unescaped), its stage's markup, and its three label lines."""
        found = []
        for markup, li_attrs, inner in re.findall(r"(<li\b([^>]*)>(.*?)</li>)", self.site(), re.S):
            tags = Tags(inner).tags
            stage = re.search(r'(<span class="(?:[^"]*\s)?stage(?:\s[^"]*)?"[^>]*>.*)<span class="(?:[^"]*\s)?labels\b', inner, re.S)
            found.append({"markup": markup, "li": set((Tags(f"<li{li_attrs}>").tags[0][1].get("class") or "").split()),
                          "tag": tags[0][0] if tags else None, "attrs": tags[0][1] if tags else {},
                          "stage": stage.group(1).strip() if stage else None,
                          **{cls: label(inner, cls) for cls in ("who", "what", "where")}})
        return found

    def members(self):
        """The card's session members: each `li` that is no ghost and holds an `<a class="member">`."""
        return [item for item in self.items() if "more" not in item["li"] and item["tag"] == "a"
                and "member" in (item["attrs"].get("class") or "").split()]

    def ghosts(self):
        return [item for item in self.items() if "more" in item["li"]]

    def ghost_counts(self):
        """Each ghost's cap class (`c6`, `c4`, `c3`, or None) to the `+K` its stage shows."""
        return {next((c for c in ("c6", "c4", "c3") if c in g["li"]), None): words(g["stage"] or "") for g in self.ghosts()}

    def member(self, slug, project="sample", href=None):
        """The one member linking `href`, by default `slug`'s card under `project`; the test fails otherwise."""
        href = href or session_href(slug, project)
        found = [m for m in self.members() if m["attrs"].get("href") == href]
        if len(found) != 1:
            self.fail(f"{len(found)} crew members link {href}; the card's hrefs: {[m['attrs'].get('href') for m in self.members()]}")
        return found[0]

    def figure_of(self, item):
        """The <svg> on an item's stage; the test fails when there is none."""
        match = re.search(r"<svg\b.*?</svg>", item["stage"] or "", re.S)
        if match is None:
            self.fail(f"no figure on the stage of {item['attrs'].get('href')}: {(item['stage'] or '')[:80]!r}")
        return match.group(0)

    def h_marks(self):
        """Each member's narrow-width marks, `h3` and `h4`, in card order."""
        return [sorted({"h3", "h4"} & member["li"]) for member in self.members()]

    def assert_strokes(self, svg, expected):
        widths = raw_stroke_widths(svg)
        self.assertEqual(len(widths), len(expected), widths)
        for width, want in zip(widths, expected):
            self.assertAlmostEqual(width, want, delta=STROKE_SLACK, msg=f"{widths} against {expected}")


# ---------------------------------------------------------------- 029-U2 R1 · where the card sits


class CrewPlacement(CrewScratch):
    """Project `sample`: SLUG implementing (an In flight row) and SECOND stopped (a Needs attention row)."""

    def setUp(self):
        super().setUp()
        self.given_project()
        self.given_session()
        self.given_stopped(SECOND)

    def test_places_the_crew_card_after_the_plan_usage_line_and_before_both_lists__when_a_reading_is_shown(self):
        """029-U2.1.1 — the body runs h1, plan-usage line, crew card, #attention, #flight — the card lands under the lists, or the usage line moves."""
        usage = self.base / "usage"
        usage.mkdir()
        (usage / "latest.json").write_text(json.dumps(READING_TAPPED) + "\n")

        self.when_written(env_usage=usage)

        marks = ("<h1>Projects</h1>", 'class="note plan-usage"', SITE_OPEN, 'id="attention"', 'id="flight"')
        positions = [self.index.find(mark) for mark in marks]
        self.assertNotIn(-1, positions, dict(zip(marks, positions)))
        self.assertEqual(positions, sorted(positions))

    def test_puts_the_crew_card_right_under_the_heading__when_there_is_no_plan_usage_reading(self):
        """029-U2.1.2 — with no reading the card follows `<h1>Projects</h1>` directly — something else slips in above the crew."""
        self.when_written()

        self.assertIn("<h1>Projects</h1>" + SITE_OPEN, self.index)


# ---------------------------------------------------------------- 029-U2 R2 · N, the sessions on site


class CrewCount(CrewScratch):
    """Project `sample` with U1 `first`; the sessions each test names."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def test_counts_only_sessions_needing_attention_or_running__not_awaiting_acceptance_parked_or_orphan_ones(self):
        """029-U2.2.1 — two sessions waiting on the Owner and two running, across two projects, read `On site · 4` beside an awaiting-acceptance unit, a parked session and an orphan — the count takes in units, idle sessions or sessions no project lists."""
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))
        self.given_stopped("sample-002-second")
        self.given_session(slug="sample-003-third", phase="briefed")
        self.given_session(slug="sample-004-fourth")
        self.given_session(slug="sample-005-fifth", parked=True)
        self.given_project(name="other")
        self.given_session(slug="other-001-first")
        self.given_session(slug="notes-app-001-first")

        self.when_written()

        self.assertIn("Awaiting acceptance", self.index)
        self.assertIn(ORPHANS_HEADING, self.index)
        self.assertEqual(self.heading(), "On site · 4")
        self.assertEqual(sorted((m["who"], m["where"]) for m in self.members()),
                         [("001-first", "other"), ("002-second", "sample"), ("003-third", "sample"), ("004-fourth", "sample")])

    def test_reads_on_site_one__when_one_session_is_running(self):
        """029-U2.2.2 — one running session reads `On site · 1` — the smallest count is dropped or misread as quiet."""
        self.given_session()

        self.when_written()

        self.assertEqual(self.heading(), "On site · 1")

    def test_reads_on_site_with_no_count__when_nothing_is_on_site(self):
        """029-U2.2.3 — a project with no session reads `On site`, no count — the quiet card says `On site · 0`."""
        self.when_written()

        self.assertEqual(self.heading(), "On site")


# ---------------------------------------------------------------- 029-U2 R3 · the crew's order


class CrewOrder(CrewScratch):
    """Projects as each test names them; each session's run.json last written the minutes ago the test gives."""

    def test_lists_owner_calls_then_ready_to_launch_then_running__whatever_each_last_wrote(self):
        """029-U2.3.1 — a stopped session (30 min), then a briefed one (2 min), then running ones newest first (1, 10 min) — an Owner call hides behind fresher work."""
        self.given_project()
        self.given_touched(self.given_session(), 1)
        self.given_touched(self.given_session(slug=SECOND, phase="briefed"), 2)
        self.given_touched(self.given_stopped("sample-003-third"), 30)
        self.given_touched(self.given_session(slug="sample-004-fourth"), 10)

        self.when_written()

        self.assertEqual([m["who"] for m in self.members()], ["003-third", "002-second", "001-first", "004-fourth"])

    def test_lists_running_sessions_newest_first_across_projects__not_in_flights_per_project_order(self):
        """029-U2.3.2 — running sessions at 2, 10 and 20 min across two projects list by recency, while In flight groups them by project — the crew copies In flight's order and the newest work sits last."""
        for folder in (self.given_project(), self.given_project(name="other")):
            self.given_plan_written_long_ago(folder)
        self.given_touched(self.given_session(), 2)
        self.given_touched(self.given_session(slug="sample-003-third"), 20)
        self.given_touched(self.given_session(slug="other-002-second"), 10)

        self.when_written()

        self.assertEqual(flight_hrefs(self.index), [session_href(SLUG), session_href("sample-003-third"),
                                                    session_href("other-002-second", "other")])
        self.assertEqual([(m["who"], m["where"]) for m in self.members()],
                         [("001-first", "sample"), ("002-second", "other"), ("003-third", "sample")])


# ---------------------------------------------------------------- 029-U2 R4 · a member's markup


class CrewMember(CrewScratch):
    """Project `sample` with U1 `first`; the sessions each test names."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def given_building(self, slug=SLUG):
        return self.given_session(slug=slug, units=[{"id": "U1", "status": "building"}, {"id": "U2", "status": "todo"}])

    def test_labels_a_member_with_its_session_doing_and_project__beside_a_figure(self):
        """029-U2.4.1 — a member reads `001-first` / `building U1` / `sample` under a figure on its stage — the labels lose the project prefix rule, swap lines, or the stage is empty."""
        self.given_building()

        self.when_written()

        member = self.member(SLUG)
        self.figure_of(member)
        self.assertEqual((member["who"], member["what"], member["where"]), ("001-first", "building U1", "sample"))

    def test_links_each_member_to_its_sessions_row__in_both_lists(self):
        """029-U2.4.2 — each member is an `a.member` linking the same card its Needs attention or In flight row links — a figure opens the wrong card, or none."""
        self.given_stopped()
        self.given_building(SECOND)

        self.when_written()

        for slug in (SLUG, SECOND):
            with self.subTest(slug=slug):
                member = self.member(slug)
                self.row(session_href(slug))
                self.assertEqual(member["tag"], "a")

    def test_titles_a_member_project_session_and_doing(self):
        """029-U2.4.3 — the member's title is `sample · 001-first · building U1` — the hover text drops the project, which the label may ellipsize (assumed Q1)."""
        self.given_building()

        self.when_written()

        self.assertEqual(self.member(SLUG)["attrs"].get("title"), "sample · 001-first · building U1")

    def test_marks_the_owners_member_owner__and_no_robots(self):
        """029-U2.4.4 — the stopped session's `li` carries `owner`, the running one's does not — the Owner's column takes a robot's width, or a robot's the Owner's."""
        self.given_stopped()
        self.given_building(SECOND)

        self.when_written()

        self.assertIn("owner", self.member(SLUG)["li"])
        self.assertNotIn("owner", self.member(SECOND)["li"])

    def test_lists_the_crew_in_a_card_labelled_by_its_heading(self):
        """029-U2.4.5 — the section is labelled by `h2#site-h` and holds `div.crew-card > ul.crew > li` — the crew is no list, or no heading names it."""
        self.given_building()

        self.when_written()

        self.assertRegex(self.site(), r'^<section class="site" aria-labelledby="site-h"><h2 id="site-h">[^<]*</h2>'
                                      r'<div class="crew-card"><ul class="crew"><li\b')


# ---------------------------------------------------------------- 029-U2 R5 · the doing phrase, from observable state only


class CrewDoing(CrewScratch):
    """Project `sample` with U1 `first`; each test writes SLUG in the state its phrase names."""

    def setUp(self):
        super().setUp()
        self.folder = self.given_project()

    def doing(self, slug=SLUG):
        return self.member(slug)["what"]

    def test_says_your_call__when_the_session_stopped(self):
        """029-U2.5.1 — a stopped session says `your call` — the Owner's turn reads as someone else's."""
        self.given_stopped()

        self.when_written()

        self.assertEqual(self.doing(), "your call")

    def test_says_your_call__when_a_building_session_has_a_stop_file(self):
        """029-U2.5.2 — a STOP file says `your call` though U1 is building — the Owner's stop reads as work going on."""
        run_dir = self.given_session(units=[{"id": "U1", "status": "building"}])
        (run_dir / "STOP").write_text("")

        self.when_written()

        self.assertEqual(self.doing(), "your call")

    def test_says_your_call__when_a_rebrief_needs_the_owners_call(self):
        """029-U2.5.3 — a rebrief whose verdict is the Owner's says `your call` — the call reads as a hand-off."""
        self.given_session(rotate={"requested_at": iso(datetime.now(timezone.utc)), "reason": "rebrief"},
                           rebriefs=[{"n": 1, "verdict": "owner", "why": "the sample's scope moved"}])

        self.when_written()

        self.assertEqual(self.doing(), "your call")

    def test_says_your_call__when_run_json_is_unreadable(self):
        """029-U2.5.4 — an unreadable run.json says `your call` — a broken session drops off the card or breaks it."""
        run_dir = self.given_session()
        (run_dir / "run.json").write_text("{")

        self.when_written()

        self.assertEqual(self.doing(), "your call")

    def test_says_ready_to_launch__when_the_session_is_briefed(self):
        """029-U2.5.5 — a briefed session says `ready to launch` — the launch line reads as a stop."""
        self.given_session(phase="briefed")

        self.when_written()

        self.assertEqual(self.doing(), "ready to launch")

    def test_says_handing_off__when_the_session_is_rotating(self):
        """029-U2.5.6 — a rotating session says `handing off` — a rotation reads as the unit still building."""
        self.given_session(rotate={"requested_at": iso(datetime.now(timezone.utc)), "reason": "context"})

        self.when_written()

        self.assertEqual(self.doing(), "handing off")

    def test_says_leads_intake__when_a_finished_session_has_no_intake(self):
        """029-U2.5.7 — a done session with no INTAKE.md says `Lead's intake` — work with the Lead reads as building."""
        self.given_session(phase="done", worktree=str(self.given_worktree_not_in_main()))

        self.when_written()

        self.assertEqual(self.doing(), "Lead's intake")

    def test_says_leads_check__when_a_finished_direct_build_waits_on_the_lead(self):
        """029-U2.5.8 — a finished direct build (stage `check`) says `Lead's check`, not `direct build` — finished work reads as still building."""
        self.given_finished_direct_build()

        self.when_written()

        self.assertEqual(self.doing(), "Lead's check")

    def test_says_owner_brief__when_the_project_asks_for_one_and_none_is_written(self):
        """029-U2.5.9 — stage `review guide` says `owner brief` — the brief's wait reads as intake or as nothing."""
        self.given_settings(self.folder, "robowright.json", {"owner_brief": True})
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

        self.when_written()

        self.assertEqual(self.doing(), "owner brief")

    def test_says_owner_brief__when_an_explainer_is_writing_it(self):
        """029-U2.5.10 — stage `owner brief` (a busy Explainer) says `owner brief` — the brief in progress reads as more building."""
        self.given_settings(self.folder, "robowright.json", {"owner_brief": True})
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))
        self.given_live_agent(EXPLAINER, "busy", cwd=self.cwd)

        self.when_written()

        self.assertEqual(self.doing(), "owner brief")

    def test_says_reading_the_brief__when_the_session_is_in_phase_intake(self):
        """029-U2.5.11 — a working session in phase `intake` says `reading the brief` — the Worker's first read reads as building."""
        self.given_session(phase="intake", units=[{"id": "U1", "status": "todo"}])

        self.when_written()

        self.assertEqual(self.doing(), "reading the brief")

    def test_says_building_and_the_unit__when_the_current_unit_is_building(self):
        """029-U2.5.12 — current unit U1 `building` says `building U1` — the member hides which unit is in hand."""
        self.given_session(units=[{"id": "U1", "status": "building"}, {"id": "U2", "status": "todo"}])

        self.when_written()

        self.assertEqual(self.doing(), "building U1")

    def test_says_closing_and_the_unit__when_the_current_unit_passed_its_gate(self):
        """029-U2.5.13 — current unit U1 `gated` says `closing U1` — a passed gate reads as more building."""
        self.given_session(units=[{"id": "U1", "status": "gated"}, {"id": "U2", "status": "todo"}])

        self.when_written()

        self.assertEqual(self.doing(), "closing U1")

    def test_says_review_notes_and_the_unit__when_the_current_unit_is_held(self):
        """029-U2.5.14 — current unit U1 `held` says `review notes U1` — a held unit reads as clean progress."""
        self.given_session(units=[{"id": "U1", "status": "held", "gate_attempts": 1}, {"id": "U2", "status": "todo"}])

        self.when_written()

        self.assertEqual(self.doing(), "review notes U1")

    def test_says_final_review__when_the_session_is_in_its_end_of_stack_review(self):
        """029-U2.5.15 — phase `end-of-stack`, every unit done, says `final review` — the whole-change review reads as idle."""
        self.given_session(phase="end-of-stack", units=[{"id": "U1", "status": "done"}])

        self.when_written()

        self.assertEqual(self.doing(), "final review")

    def test_says_direct_build__when_a_direct_build_is_running(self):
        """029-U2.5.16 — a running direct build says `direct build` — a build with no session folder reads as a brief."""
        self.given_running_direct_build()

        self.when_written()

        self.assertEqual(self.doing(), "direct build")

    def test_says_writing_the_brief__when_a_planner_is_writing_it(self):
        """029-U2.5.17 — a session folder with no run.json and a busy Planner says `writing the brief` — a brief in writing reads as a build."""
        self.given_briefing()

        self.when_written()

        self.assertEqual(self.doing(), "writing the brief")

    def test_says_rebriefing__when_a_stopped_session_has_a_busy_planner(self):
        """029-U2.5.18 — a stopped session with a busy rebrief Planner says `rebriefing` — the Owner is asked for a call the Planner is already making."""
        self.given_stopped()
        self.given_live_agent(f"planner-{SLUG}-r1", "busy", cwd=self.cwd)

        self.when_written()

        self.assertEqual(self.doing(), "rebriefing")

    def test_says_working_and_never_the_status__when_the_current_units_status_is_one_the_table_does_not_name(self):
        """029-U2.5.19 — a current unit whose status is `polishing-the-sample` says `working`, and the member carries no part of it — session text reaches the card as a phrase."""
        self.given_session(units=[{"id": "U1", "status": "polishing-the-sample"}])

        self.when_written()

        member = self.member(SLUG)
        self.assertEqual(member["what"], "working")
        self.assertNotIn("polishing", member["markup"])


# ---------------------------------------------------------------- 029-U2 R6 · the caps and their ghosts; R2.4, R3.3 at the cap


class CrewCaps(CrewScratch):
    """Project `sample` with U1 `first`; the first N of ON_SITE, each implementing, the k-th last written k minutes ago,
    so the card's order is ON_SITE's."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def given_on_site(self, n):
        for minutes, slug in enumerate(ON_SITE[:n], start=1):
            self.given_touched(self.given_session(slug=slug), minutes)

    def test_shows_no_member_and_no_ghost__when_nothing_is_on_site(self):
        """029-U2.6.1 — N = 0: no `a.member` and no `li.more` — the quiet card links somewhere, or grows a ghost (assumed Q3)."""
        self.given_on_site(0)

        self.when_written()

        self.assertEqual((self.members(), self.ghosts()), ([], []))

    def test_shows_three_members_and_no_ghost__when_three_are_on_site(self):
        """029-U2.6.2 — N = 3: three unmarked members, no ghost — a ghost shows `+0`, or a member hides at a width that fits it."""
        self.given_on_site(3)

        self.when_written()

        self.assertEqual(self.h_marks(), [[], [], []])
        self.assertEqual(self.ghost_counts(), {})

    def test_marks_the_fourth_h3_and_adds_the_narrowest_ghost__when_four_are_on_site(self):
        """029-U2.6.3 — N = 4: member 4 carries `h3`; one ghost, `c3` `+1` — at 640 px the fourth drops with no `+1` in its place."""
        self.given_on_site(4)

        self.when_written()

        self.assertEqual(self.h_marks(), [[], [], [], ["h3"]])
        self.assertEqual(self.ghost_counts(), {"c3": "+1"})

    def test_marks_four_and_five_and_adds_two_ghosts__when_five_are_on_site(self):
        """029-U2.6.4 — N = 5: members 4–5 carry `h3`, member 5 `h4`; ghosts `c4` `+1`, `c3` `+2` — a narrow page loses sessions without a count."""
        self.given_on_site(5)

        self.when_written()

        self.assertEqual(self.h_marks(), [[], [], [], ["h3"], ["h3", "h4"]])
        self.assertEqual(self.ghost_counts(), {"c4": "+1", "c3": "+2"})

    def test_shows_six_members_and_two_ghosts__when_six_are_on_site(self):
        """029-U2.6.5 — N = 6: six members, 4–6 `h3`, 5–6 `h4`; ghosts `c4` `+2`, `c3` `+3`, no `c6` — a full wide card grows a `+0`."""
        self.given_on_site(6)

        self.when_written()

        self.assertEqual(self.h_marks(), [[], [], [], ["h3"], ["h3", "h4"], ["h3", "h4"]])
        self.assertEqual(self.ghost_counts(), {"c4": "+2", "c3": "+3"})

    def test_caps_at_six_members_and_adds_all_three_ghosts__when_seven_are_on_site(self):
        """029-U2.6.6 — N = 7: six members; ghosts `c6` `+1`, `c4` `+3`, `c3` `+4` — the seventh draws past the cap, or vanishes uncounted."""
        self.given_on_site(7)

        self.when_written()

        self.assertEqual(self.h_marks(), [[], [], [], ["h3"], ["h3", "h4"], ["h3", "h4"]])
        self.assertEqual(self.ghost_counts(), {"c6": "+1", "c4": "+3", "c3": "+4"})

    def test_counts_each_ghost_from_its_cap__when_eight_are_on_site(self):
        """029-U2.6.7 — N = 8: six members; ghosts `c6` `+2`, `c4` `+4`, `c3` `+5` — a ghost counts from the wrong cap."""
        self.given_on_site(8)

        self.when_written()

        self.assertEqual(self.h_marks(), [[], [], [], ["h3"], ["h3", "h4"], ["h3", "h4"]])
        self.assertEqual(self.ghost_counts(), {"c6": "+2", "c4": "+4", "c3": "+5"})

    def test_links_each_ghost_to_in_flight_with_its_count_spoken_only_in_its_labels(self):
        """029-U2.6.8 — each ghost is `<a class="member" href="#flight" title="K more on site, listed below">`, `+K` aria-hidden, labels `K more` / `listed below` / empty — the ghost speaks `+K`, or leads nowhere (assumed Q4)."""
        self.given_on_site(7)

        self.when_written()

        expected = {"c6": ("1 more on site, listed below", "1 more", "+1"), "c4": ("3 more on site, listed below", "3 more", "+3"),
                    "c3": ("4 more on site, listed below", "4 more", "+4")}
        ghosts = {next((c for c in ("c6", "c4", "c3") if c in g["li"]), None): g for g in self.ghosts()}
        self.assertEqual(set(ghosts), set(expected))
        for cap, (title, count_label, plus) in expected.items():
            with self.subTest(cap=cap):
                ghost = ghosts[cap]
                stage = Voiced(ghost["stage"] or "")

                self.assertEqual((ghost["tag"], ghost["attrs"].get("class"), ghost["attrs"].get("href"), ghost["attrs"].get("title")),
                                 ("a", "member", "#flight", title))
                self.assertEqual((ghost["who"], ghost["what"], ghost["where"]), (count_label, "listed below", ""))
                self.assertEqual((stage.spoken(), stage.hidden()), ("", plus))

    def test_counts_the_overflow_in_the_heading__when_eight_are_on_site(self):
        """029-U2.2.4 — eight on site read `On site · 8`, though six are drawn — the heading counts the figures, not the sessions."""
        self.given_on_site(8)

        self.when_written()

        self.assertEqual(self.heading(), "On site · 8")

    def test_shows_the_six_most_recently_active_then_the_ghosts__when_eight_are_on_site(self):
        """029-U2.3.3 — with eight on site the card draws the six most recent, `001-first` to `006-sixth`, then its ghosts — the overflow hides the newest work, or a ghost sits among the members (assumed Q5)."""
        self.given_on_site(8)

        self.when_written()

        self.assertEqual([m["who"] for m in self.members()],
                         ["001-first", "002-second", "003-third", "004-fourth", "005-fifth", "006-sixth"])
        self.assertEqual(["more" in item["li"] for item in self.items()], [False] * 6 + [True] * 3)


# ---------------------------------------------------------------- 029-U2 R7 · the quiet state


class CrewQuiet(CrewScratch):
    """Project `sample` with U1 `first` and no session on site."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def quiet_figure(self):
        """The one <svg> in the quiet card; the test fails when there is not exactly one."""
        figures = re.findall(r"<svg\b.*?</svg>", self.site(), re.S)
        self.assertEqual(len(figures), 1, self.site()[:200])
        return figures[0]

    def test_shows_one_unlinked_member_with_the_quiet_line__when_nothing_is_on_site(self):
        """029-U2.7.1 — the card is one `div.member` (no link) in `div.crew-card`, reading `Quiet site. Nothing is running.` — the quiet card links to an empty list, or stands outside the card's ground."""
        self.when_written()

        site = self.site()
        self.assertEqual(classed(site, "crew-card"), ["div"])
        self.assertEqual(classed(site, "member"), ["div"])
        self.assertNotIn("a", [tag for tag, _ in Tags(site).tags])
        self.assertIn(QUIET_LINE, words(site))

    def test_draws_the_dozing_worker_with_closed_lids__in_the_quiet_card(self):
        """029-U2.7.2 — the quiet figure is the Worker, aria-hidden, its eyes `cy 6, rx 7, ry 1.8` — an awake robot on a quiet site, or a redrawn face."""
        self.when_written()

        figure = self.quiet_figure()
        opening = Tags(figure).tags[0][1]
        self.assertEqual((opening.get("aria-hidden"), opening.get("focusable")), ("true", "false"))
        self.assertEqual(roles_drawn(figure), {"worker"})
        self.assertEqual([tuple(float(attrs.get(k)) for k in ("cx", "cy", "rx", "ry")) for tag, attrs in Tags(figure).tags
                          if tag == "ellipse"], DOZING_EYES)

    def test_frames_and_strokes_the_dozing_worker_as_the_crew_worker(self):
        """029-U2.7.3 — the dozing Worker has the crew Worker's viewBox, strokes and `translate(-7 0)` prop — the quiet figure stands off the ground or at the row's weights (assumed Q9)."""
        self.when_written()

        figure = self.quiet_figure()
        self.assertEqual(view_box(figure), CREW_ROBOT_VIEWBOX)
        self.assertEqual(group_transforms(figure), [CREW_PROP_TRANSFORM])
        self.assert_strokes(figure, CREW_ROBOT_STROKES["worker"])

    def test_drops_the_in_flight_note_and_keeps_the_needs_attention_note__when_the_site_is_quiet(self):
        """029-U2.7.4 — the quiet page has no `Nothing is running right now.` and keeps `Nothing needs attention right now.` — the page says nothing runs twice, or loses the attention note."""
        self.when_written()

        text = Page(self.out / "index.html").text()
        self.assertIn(QUIET_LINE, text)
        self.assertNotIn(NO_RUNNING_NOTE, text)
        self.assertIn(NO_ATTENTION_NOTE, text)

    def test_lists_a_awaiting_acceptance_unit_under_needs_attention__beside_the_quiet_card(self):
        """029-U2.7.5 — an awaiting-acceptance unit lists under #attention while the card is quiet and no In flight note shows — a ready unit makes the site look busy, or hides."""
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

        self.when_written()

        attention = re.search(r'<details class="group" id="attention".*?</details>', self.index, re.S)
        self.assertIsNotNone(attention, "no Needs attention list")
        self.assertIn("sample.html#plan", Tags(attention.group(0)).hrefs())
        self.assertIn("Awaiting acceptance", words(attention.group(0)))
        self.assertEqual(self.heading(), "On site")
        self.assertIn(QUIET_LINE, words(self.site()))
        self.assertNotIn(NO_RUNNING_NOTE, Page(self.out / "index.html").text())


# ---------------------------------------------------------------- 029-U2 R8 · both empty notes while N ≥ 1


class CrewNotes(CrewScratch):
    """Project `sample` with U1 `first`; one session on site."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def test_keeps_the_in_flight_note__when_the_only_session_on_site_needs_attention(self):
        """029-U2.8.1 — one stopped session: `On site · 1` and `Nothing is running right now.` — the In flight note is dropped whenever nothing runs, not only on a quiet site."""
        self.given_stopped()

        self.when_written()

        self.assertEqual(self.heading(), "On site · 1")
        self.assertIn(NO_RUNNING_NOTE, Page(self.out / "index.html").text())

    def test_keeps_the_needs_attention_note__when_the_only_session_on_site_is_running(self):
        """029-U2.8.2 — one running session: `On site · 1` and `Nothing needs attention right now.` — the crew card drops the attention note."""
        self.given_session()

        self.when_written()

        self.assertEqual(self.heading(), "On site · 1")
        self.assertIn(NO_ATTENTION_NOTE, Page(self.out / "index.html").text())


# ---------------------------------------------------------------- 029-U2 R9 · hostile names reach the card only escaped


class CrewHostile(CrewScratch):
    """The hostile world (`given_hostile_projects`): project LIVE_NAME holds SLUG, stopped, and SECOND, implementing;
    project QUIET_NAME has no session. The tests add a slug or a unit id carrying markup syntax."""

    given_hostile_projects = Hostile.given_hostile_projects

    def test_writes_a_hostile_project_name_into_members_only_escaped(self):
        """029-U2.9.1 — each member links the URL-quoted name, titles and labels it as written, and the card holds no `data-injected` attribute; the raw name is nowhere on the index — a folder name writes an attribute onto the card."""
        self.given_hostile_projects()

        self.when_written()

        for slug in (SLUG, SECOND):
            with self.subTest(slug=slug):
                member = self.member(slug, LIVE_NAME)

                self.assertEqual((member["attrs"].get("title") or "").split(" · ")[:2], [LIVE_NAME, slug])
                self.assertEqual((member["who"], member["where"]), (slug, LIVE_NAME))
        self.assertNotIn(INJECTED, Tags(self.site()).attribute_names())
        self.assertNotIn(LIVE_NAME, self.index)

    def test_writes_a_hostile_slug_into_its_member_only_escaped(self):
        """029-U2.9.2 — a slug carrying `<x data-injected="slug">` links its row's anchor, reads as written, and adds no element, attribute or `<script` to the card — a slug writes markup onto the dashboard (assumed Q6)."""
        self.given_hostile_projects()
        self.given_session(slug=HOSTILE_SLUG, project=LIVE_NAME)

        self.when_written()

        href = f'{quote(LIVE_NAME, safe="")}.html#{HOSTILE_ANCHOR}'
        member = self.member(HOSTILE_SLUG, href=href)
        self.row(href)
        site_tags = Tags(self.site())
        self.assertEqual(member["who"], HOSTILE_SLUG)
        self.assertEqual((member["attrs"].get("title") or "").split(" · ")[:2], [LIVE_NAME, HOSTILE_SLUG])
        self.assertNotIn("x", [tag for tag, _ in site_tags.tags])
        self.assertNotIn(INJECTED, site_tags.attribute_names())
        self.assertNotIn("<script", self.site())
        self.assertNotIn(HOSTILE_SLUG, self.index)

    def test_writes_a_hostile_unit_id_into_the_doing_phrase_only_escaped(self):
        """029-U2.9.3 — a building unit whose id carries `<x data-injected="id">` reads `building` and the id as written, and adds no element or attribute to the card — a unit id writes markup into the phrase (assumed Q6)."""
        self.given_project()
        self.given_session(units=[{"id": HOSTILE_UNIT_ID, "status": "building"}])

        self.when_written()

        site_tags = Tags(self.site())
        self.assertEqual(self.member(SLUG)["what"], f"building {HOSTILE_UNIT_ID}")
        self.assertNotIn("x", [tag for tag, _ in site_tags.tags])
        self.assertNotIn(INJECTED, site_tags.attribute_names())


# ---------------------------------------------------------------- 029-U2 R10 · /attention.json carries no crew


class CrewJson(CrewScratch):
    """Project `sample`: SLUG finished and through intake (U1 awaiting acceptance), SECOND stopped, `sample-003-third` briefed,
    `sample-004-fourth` implementing; the dashboard served on a free port."""

    serve = Hostile.serve

    def test_serves_attention_json_byte_for_byte_as_before__beside_a_crew(self):
        """029-U2.10.1 — /attention.json is `ATTENTION_JSON` to the byte: two session rows and Awaiting acceptance, no running session, no crew field — the crew card changes the rows the notifier keys on."""
        self.given_project()
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))
        self.given_stopped(SECOND)
        self.given_session(slug="sample-003-third", phase="briefed")
        self.given_session(slug="sample-004-fourth")
        port, get = self.serve()

        status, body = get("/attention.json", f"127.0.0.1:{port}")

        self.assertEqual((status, body), (200, ATTENTION_JSON))


# ---------------------------------------------------------------- 029-U2 R11 · the card's CSS


class CrewStyles(CrewScratch):
    """Project `sample` with SLUG implementing; one `--once` run."""

    def setUp(self):
        super().setUp()
        self.given_project()
        self.given_session()
        self.when_written()

    def style(self):
        return "".join(re.findall(r"<style>(.*?)</style>", self.index, re.S))

    def test_sets_the_stage_height_hatch_and_figure_fill__on_the_crew_card(self):
        """029-U2.11.1 — `.crew-card` sets `--stage:74px`, `--hatch:color-mix(in srgb,var(--fg) 32%,var(--surface))`, `--fig-fill:var(--surface)` — the ground floats off the figures' feet, or the Owner's body shows the line behind the arm."""
        card = styled(self.index, ".crew-card")

        self.assertEqual({name: card.get(name) for name in ("--stage", "--hatch", "--fig-fill")},
                         {"--stage": "74px", "--hatch": "color-mix(in srgb,var(--fg) 32%,var(--surface))", "--fig-fill": "var(--surface)"})

    def test_draws_the_ground_line_and_hatch_under_the_stage__edge_to_edge(self):
        """029-U2.11.2 — `.crew-card::before` is generated, absolute at `calc(16px + var(--stage))`, edge to edge, a 2 px `--fg` top border over the -45° hatch — the figures stand on nothing, or the ground stops short of the border (assumed Q11)."""
        ground = styled(self.index, ".crew-card::before")

        found = {name: ground.get(name) for name in ("content", "position", "top", "left", "right", "border-top")}
        found["background"] = ground.get("background") or ground.get("background-image")
        self.assertEqual(found, {"content": '""', "position": "absolute", "top": "calc(16px + var(--stage))", "left": "0",
                                 "right": "0", "border-top": "2px solid var(--fg)",
                                 "background": "repeating-linear-gradient(-45deg,transparent 0 7px,var(--hatch) 7px 8.4px)"})

    def test_sizes_the_member_owner_and_ghost_columns__in_the_crew_list(self):
        """029-U2.11.3 — `.crew li{flex:0 1 136px;min-width:0}`, `.crew li.owner{flex-basis:116px}`, `.crew li.more{flex:0 0 96px}` — long names push the card wider than the page, or the ghost shrinks (assumed Q7)."""
        found = (styled(self.index, ".crew li").get("flex"), styled(self.index, ".crew li").get("min-width"),
                 styled(self.index, ".crew li.owner").get("flex-basis"), styled(self.index, ".crew li.more").get("flex"))

        self.assertEqual(found, ("0 1 136px", "0", "116px", "0 0 96px"))

    def test_sets_the_labels_twenty_pixels_under_the_stage(self):
        """029-U2.11.4 — `.labels` sets `margin-top:20px`, the 10 px ground band plus 10 px air — the session name sits on the hatch (assumed Q7)."""
        self.assertEqual(styled_last(self.index, ".labels").get("margin-top"), "20px")

    def test_keeps_each_label_line_to_one_line_with_an_ellipsis(self):
        """029-U2.11.5 — `.who`, `.what` and `.where` each get `white-space:nowrap`, `overflow:hidden`, `text-overflow:ellipsis` — a long slug wraps and the card grows a row (assumed Q7)."""
        for cls in (".who", ".what", ".where"):
            with self.subTest(line=cls):
                line = styled_line(self.index, cls)

                self.assertEqual({name: line.get(name) for name in ("white-space", "overflow", "text-overflow")},
                                 {"white-space": "nowrap", "overflow": "hidden", "text-overflow": "ellipsis"})

    def test_sets_the_session_in_mono_500_and_the_doing_and_project_in_muted_sans(self):
        """029-U2.11.6 — `.who` is the mono stack at 500 in `--fg`; `.what` and `.where` are `--muted` and not mono — the three lines read as one, or the faint colour fails contrast (assumed Q7, Q12)."""
        who = styled_last(self.index, ".who")
        self.assertEqual((who.get("font-family"), who.get("font-weight"), who.get("color")), (MONO_STACK, "500", "var(--fg)"))
        for cls in (".what", ".where"):
            with self.subTest(line=cls):
                line = styled_last(self.index, cls)

                self.assertEqual(line.get("color"), "var(--muted)")
                self.assertNotIn("monospace", line.get("font-family") or "")

    def test_outlines_a_focused_member_in_the_run_colour(self):
        """029-U2.11.7 — `a.member:focus-visible{outline:2px solid var(--run);outline-offset:-2px}` is in the stylesheet — a keyboard user cannot see which figure has focus."""
        self.assertIn("a.member:focus-visible{outline:2px solid var(--run);outline-offset:-2px}", self.style())

    def test_underlines_the_session_on_hover_in_faint_three_pixels_below(self):
        """029-U2.11.8 — `.member:hover .who` is underlined in `--faint` with a 3 px offset — a figure shows no sign it is a link (assumed Q7)."""
        hover = styled_last(self.index, ".who", hover=True)

        self.assertIn("underline", hover.get("text-decoration") or hover.get("text-decoration-line") or "")
        self.assertIn("var(--faint)", hover.get("text-decoration-color") or hover.get("text-decoration") or "")
        self.assertEqual(hover.get("text-underline-offset"), "3px")

    def test_shows_one_ghost_per_width__in_the_stylesheet(self):
        """029-U2.6.9 — the three ghost rules are in the stylesheet verbatim, `.crew`-prefixed — at 780 or 640 px the hidden ghost never shows, or two show."""
        for rule in (".crew .c4,.crew .c3{display:none}",
                     "@media (max-width:780px){.crew li.h4,.crew .c6{display:none}.crew .c4{display:block}}",
                     "@media (max-width:640px){.crew li.h3,.crew .c4{display:none}.crew .c3{display:block}"
                     ".crew li{flex-basis:118px}.crew li.owner{flex-basis:104px}.crew li.more{flex-basis:84px}}"):
            with self.subTest(rule=rule[:40]):
                self.assertIn(rule, self.style())


# ---------------------------------------------------------------- 029-U2 R12 · the crew figures


class CrewFigure(CrewScratch):
    """Project `sample` with one session per drawn figure (FIVE_FIGURES): SLUG stopped, SECOND briefed,
    `sample-003-third` briefing, `sample-004-fourth` in its end-of-stack review, `sample-005-fifth` implementing; one
    `--once` run."""

    def setUp(self):
        super().setUp()
        self.given_project()
        self.given_stopped()
        self.given_session(slug=SECOND, phase="briefed")
        self.given_briefing("sample-003-third")
        self.given_session(slug="sample-004-fourth", phase="end-of-stack")
        self.given_session(slug="sample-005-fifth")
        self.when_written()

    def crew_figure(self, slug):
        return self.figure_of(self.member(slug))

    def test_stands_each_members_figure_on_its_stage__as_the_sessions_state_picks_it(self):
        """029-U2.12.1 — each member's stage holds an aria-hidden, unfocusable figure of the role its row shows — the card and the rows disagree on who holds a session."""
        for slug, role in FIVE_FIGURES.items():
            with self.subTest(role=role):
                figure = self.crew_figure(slug)
                opening = Tags(figure).tags[0][1]

                self.assertEqual((opening.get("aria-hidden"), opening.get("focusable")), ("true", "false"))
                self.assertEqual(roles_drawn(figure), {role})

    def test_draws_the_crew_owner_with_eyes_smile_and_collar__and_no_bulb(self):
        """029-U2.12.2 — the crew Owner keeps its r 2.4 eyes, `M-5 -106Q` smile and `M-6 -92L` collar, and draws none of the bulb — the 70 px Owner is faceless, or carries the hero's bulb."""
        figure = self.crew_figure(SLUG)
        bulb = {key for key, _ in owner_figure_art()[1]}

        self.assertRegex(figure, r'<circle\b[^>]*\br="2\.[46]"')
        self.assertIn("M-5 -106Q", figure)
        self.assertIn("M-6 -92L", figure)
        self.assertEqual([key for key, _ in art_shapes(figure) if key in bulb], [])

    def test_writes_no_art_colour_and_no_accessible_name__in_any_crew_figure(self):
        """029-U2.12.3 — no crew figure carries #12325A, #A87300 or #F4F7FA, a <title>, `role=` or `aria-label=` — a figure ignores the theme, or a screen reader reads a decoration."""
        for slug in FIVE_FIGURES:
            with self.subTest(slug=slug):
                figure = self.crew_figure(slug).lower()

                found = [mark for mark in ("#12325a", "#a87300", "#f4f7fa", "<title", "role=", "aria-label=") if mark in figure]

                self.assertEqual(found, [])

    def test_paints_each_crew_robot_shape_as_its_art_inks_it(self):
        """029-U2.12.4 — each crew robot draws exactly its art's inner-group shapes, line ink `currentColor`, brass `var(--brass)` — a shape goes missing or keeps a fixed colour."""
        for slug, role in ROBOT_FIGURES.items():
            with self.subTest(role=role):
                self.assertEqual(inked(art_shapes(self.crew_figure(slug)), {}), inked(art_shapes(robot_art(role)), ROBOT_INKS))

    def test_paints_the_crew_owner_as_the_hero_inks_it__face_and_collar_included(self):
        """029-U2.12.5 — the crew Owner draws every hero-group shape before the bulb, paper fills as `var(--fig-fill)` — the Owner's body shows the card's line through it."""
        self.assertEqual(inked(art_shapes(self.crew_figure(SLUG)), {}), inked(owner_figure_art()[0], OWNER_INKS))

    def test_frames_each_crew_figure_in_its_specs_view_box(self):
        """029-U2.12.6 — a crew robot's viewBox is -50 -54 136 90, the crew Owner's -26 -137 64 135.1 — the figure is cropped or floats above the ground."""
        for slug, role in FIVE_FIGURES.items():
            with self.subTest(role=role):
                expected = CREW_OWNER_VIEWBOX if role == "owner" else CREW_ROBOT_VIEWBOX

                self.assertEqual(view_box(self.crew_figure(slug)), expected)

    def test_strokes_each_crew_robot_at_the_crew_weights(self):
        """029-U2.12.7 — a crew robot's strokes are 3.5, 3.5, 4.9, 4.9, then each prop stroke × 0.945 — the 52 px robot is drawn at the row's or the art's weights (assumed Q9)."""
        for slug, role in ROBOT_FIGURES.items():
            with self.subTest(role=role):
                self.assert_strokes(self.crew_figure(slug), CREW_ROBOT_STROKES[role])

    def test_strokes_the_crew_owner_at_the_heros_weights_times_one_point_two(self):
        """029-U2.12.8 — the crew Owner's strokes are the hero's × 1.2: 3.84, 3.84, 2.88, 3.36, 3.84, 2.64, 3.6, 4.08 — the 70 px Owner is drawn in hairlines or at the row's weight (assumed Q8, Q9)."""
        self.assert_strokes(self.crew_figure(SLUG), CREW_OWNER_STROKES)

    def test_stands_each_crew_robots_prop_on_the_ground__and_keeps_the_owners_arm_turn(self):
        """029-U2.12.9 — a crew robot's only group transform is `translate(-7 0)`; the Owner's only one is its arm's `rotate(-28 26 -62)` — the prop floats at the glyph's 1.35 scale, or the figure lands off its viewBox."""
        for slug, role in FIVE_FIGURES.items():
            with self.subTest(role=role):
                expected = group_transforms(owner_art())[1:] if role == "owner" else [CREW_PROP_TRANSFORM]

                self.assertEqual(group_transforms(self.crew_figure(slug)), expected)


# ---------------------------------------------------------------- 029-U2 R13 · a missing art file leaves the member, not its figure


class CrewFallback(CrewScratch):
    """Project `sample`; the dashboard run from a scratch copy of the clone with roles/worker-light.svg deleted."""

    given_clone_copy = GlyphFallback.given_clone_copy

    def setUp(self):
        super().setUp()
        self.given_project()

    def test_keeps_the_member_with_an_empty_stage__when_its_role_art_is_missing(self):
        """029-U2.13.1 — with the Worker's art gone the running member keeps its labels on an empty stage, exit 0, and the briefed member keeps the Lead — one missing file drops a session from the card or crashes the page (assumed Q10)."""
        self.given_session()
        self.given_session(slug=SECOND, phase="briefed")
        script = self.given_clone_copy(missing=["roles/worker-light.svg"])

        self.when_written(script=script)

        member = self.member(SLUG)
        self.assertEqual((member["who"], member["where"]), ("001-first", "sample"))
        self.assertIsNotNone(member["stage"], "the member has no stage")
        self.assertNotIn("<svg", member["stage"])
        self.assertEqual(roles_drawn(self.figure_of(self.member(SECOND))), {"lead"})

    def test_keeps_the_quiet_line_without_a_figure__when_the_worker_art_is_missing(self):
        """029-U2.13.2 — with the Worker's art gone the quiet card still reads `Quiet site. Nothing is running.` with no figure, exit 0 — the quiet page crashes or shows an empty card (assumed Q10)."""
        script = self.given_clone_copy(missing=["roles/worker-light.svg"])

        self.when_written(script=script)

        self.assertEqual(self.heading(), "On site")
        self.assertIn(QUIET_LINE, words(self.site()))
        self.assertNotIn("<svg", self.site())


# ================================================================ 029-U3 · the empty state and the footer stamp: with no
# project at all, the hero, tokenised and cropped, over three lines; the maker's mark first in every page's footer. Rows
# are `029-U3.…` in BEHAVIORS.md. The hero and the stamp are checked against the art files themselves.


LOGO_ART = REPO / "assets" / "logo-light.svg"
ART_GRID = "#D3DEEA"
# The art's inks as each sheet maps them. In the hero, every paper becomes the page's background, Owner included, and the one grid line the
# page's line colour. In the stamp, brass becomes the faded stamp accent and paper becomes no fill at all.
HERO_INKS = {ART_LINE: "currentColor", ART_BRASS: "var(--brass)", ART_PAPER: "var(--bg)", ART_GRID: "var(--line)"}
STAMP_INKS = {ART_LINE: "currentColor", ART_BRASS: "var(--stamp-accent)", ART_PAPER: "none"}
# The hero's 1200 × 720 sheet cropped 18 units in from each edge.
HERO_VIEWBOX = (18.0, 18.0, 1164.0, 684.0)
HERO_CSS = {"display": "block", "width": "100%", "max-width": "760px", "height": "auto", "margin": "28px auto 18px",
            "color": "var(--fg)"}
EMPTY_OPEN = '<h1>Projects</h1><section class="empty">'
HERO_OPEN = '<svg class="hero-art"'
NO_PROJECTS_LINE = "<p>No projects yet.</p>"
START_LINE = "Start one with role-start planner <project>."
OLD_EMPTY_LINE = "No project folder with a PROJECT.md"
# A projects root whose last folder carries markup syntax and an ampersand, and that folder's name as e() writes it.
HOSTILE_ROOT_NAME = 'projects <x data-injected="root"> & co'
HOSTILE_ROOT_ESCAPED = "projects &lt;x data-injected=&quot;root&quot;&gt; &amp; co"
# The footer's text: the clock time, the 20 s refresh, then whatever the page adds after it.
FOOTER_TEXT = re.compile(r"Updated \d{2}:\d{2}:\d{2} · refreshes every 20s(?: · .*)?")
FOOTER_CSS = {"display": "flex", "align-items": "center", "gap": "12px"}
STAMP_CSS = {"width": "48px", "height": "48px", "color": "var(--faint)", "flex": "none"}
STAMP_ACCENT = "color-mix(in srgb,var(--brass) 85%,var(--bg))"


def painted_shapes(svg_text, inks=None):
    """Each shape an SVG draws, in document order, as (key, fill, stroke, every other attribute sorted), each colour
    read through `inks`: the art with its inks swapped compares equal to a page's tokenised copy of it."""
    inks = inks or {}
    return [(key, *(inks.get(value, value) for value in (paint(attrs, "fill"), paint(attrs, "stroke"))),
             sorted((name, value) for name, value in attrs.items() if name not in ("fill", "stroke", "style")))
            for key, attrs in art_shapes(svg_text)]


def paints_over(drawn_text, art_text, ink):
    """The paints a page's copy of some art gives every fill or stroke the art paints `ink`; None when the two draw a
    different number of shapes."""
    drawn, art = painted_shapes(drawn_text), painted_shapes(art_text)
    if len(drawn) != len(art):
        return None
    return {page for page_shape, art_shape in zip(drawn, art) for page, inked_as in zip(page_shape[1:3], art_shape[1:3])
            if inked_as == ink}


def plain(markup):
    """The text of `markup` with its tags removed (not replaced by spaces), unescaped, whitespace collapsed:
    `with <code>x</code>.` reads `with x.`."""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", markup)).split())


class EmptyScratch(CrewScratch):
    """launch.json naming both roots, each existing and empty unless the test adds to them. Each test runs `--once` or
    `--serve` once and reads the index's `main` or a page's footer."""

    given_clone_copy = GlyphFallback.given_clone_copy
    serve = Hostile.serve

    # ------------------------------------------------------------ then

    def main_markup(self):
        match = re.search(r'<main id="main">(.*)</main>', self.index, re.S)
        if match is None:
            self.fail('the index has no <main id="main">')
        return match.group(1)

    def empty_section(self):
        """The inside of the index's `<section class="empty">`; the test fails when there is none."""
        match = re.search(r'<section class="empty">(.*?)</section>', self.index, re.S)
        if match is None:
            self.fail('the index has no <section class="empty">')
        return match.group(1)

    def hero(self):
        """The index's `<svg class="hero-art">` as written; the test fails when there is none."""
        match = re.search(rf"{re.escape(HERO_OPEN)}.*?</svg>", self.index, re.S)
        if match is None:
            self.fail("the index draws no hero")
        return match.group(0)

    def lines(self):
        """Each `<p>` of the empty section as written, in order, the hero left out."""
        return re.findall(r"<p\b[^>]*>.*?</p>", re.sub(r"<svg\b.*?</svg>", "", self.empty_section(), flags=re.S), re.S)

    def footer(self, page_text):
        """(the stamp's <svg> as written, or None; the plain text of the `<span>` after it) for a page whose footer is
        `<footer id="foot">[<svg>…</svg>]<span>…</span></footer>`; the test fails on a footer of any other shape."""
        match = re.search(r'<footer id="foot">(.*?)</footer>', page_text, re.S)
        if match is None:
            self.fail('the page has no <footer id="foot">')
        shaped = re.fullmatch(r"\s*(?:(<svg\b[^>]*>.*?</svg>)\s*)?<span>(.*)</span>\s*", match.group(1), re.S)
        if shaped is None:
            self.fail(f"the footer holds {match.group(1)[:120]!r}, not an optional stamp then <span>…</span>")
        return shaped.group(1), plain(shaped.group(2))

    def stamp(self, page_text):
        """The <svg> the page's footer opens with; the test fails when it opens with its text."""
        stamp, _ = self.footer(page_text)
        if stamp is None:
            self.fail("the footer opens with no stamp")
        return stamp


# ---------------------------------------------------------------- 029-U3 R1 · the empty state


class EmptyState(EmptyScratch):
    """No project folder and no session: both roots exist and are empty, unless the test adds an orphan."""

    def test_opens_main_with_the_heading_then_the_empty_section__holding_the_hero_then_three_lines(self):
        """029-U3.1.1 — with no project and no orphan, main is `<h1>Projects</h1><section class="empty">` holding the hero, then `<p>`, `<p>`, `<p class="where">`, and nothing else — the hero lands under the text, a list, a note or the crew card slips in."""
        self.when_written()

        shaped = re.fullmatch(rf"\s*{re.escape(EMPTY_OPEN)}\s*({re.escape(HERO_OPEN)}[^>]*>.*?</svg>)"
                              r"((?:\s*<p\b[^>]*>.*?</p>)*)\s*</section>\s*", self.main_markup(), re.S)
        self.assertIsNotNone(shaped, self.main_markup()[:160])
        self.assertEqual([attrs.get("class") for tag, attrs in Tags(shaped.group(2)).tags if tag == "p"], [None, None, "where"])

    def test_says_no_projects_yet_and_how_to_start_one__when_there_is_no_project(self):
        """029-U3.1.2 — line 1 is `<p>No projects yet.</p>` and line 2 reads `Start one with role-start planner <project>.` — the page drops the call to action or misquotes the command."""
        self.when_written()

        lines = self.lines()
        self.assertEqual(len(lines), 3, lines)
        self.assertEqual((lines[0], plain(lines[1])), (NO_PROJECTS_LINE, START_LINE))

    def test_names_the_projects_root_it_looked_under_in_mono__when_there_is_no_project(self):
        """029-U3.1.3 — line 3 is `<p class="where">Looking for folders with a PROJECT.md under <span class="mono">ROOT</span></p>` — the empty page stops saying where it looked."""
        self.when_written()

        self.assertEqual(self.lines()[2:], [f'<p class="where">Looking for folders with a PROJECT.md under '
                                            f'<span class="mono">{self.projects}</span></p>'])

    def test_shows_neither_list_note_nor_the_old_empty_line__when_there_is_no_project(self):
        """029-U3.1.4 — the page holds no `Nothing needs attention`, no `Nothing is running` and no `No project folder with a PROJECT.md` — the empty state stacks the list notes and the one-line empty message under the hero."""
        self.when_written()

        text = html.unescape(self.index)
        for phrase in ("Nothing needs attention", "Nothing is running", OLD_EMPTY_LINE):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, text)

    def test_hides_the_hero_from_screen_readers__and_strips_its_role_and_label(self):
        """029-U3.1.5 — the hero's <svg> is `class="hero-art"`, `aria-hidden="true"`, `focusable="false"`, with no `role`, `aria-label` or `id` — a screen reader announces the art's long label over the page's own text (assumed Q6)."""
        self.when_written()

        opening = Tags(self.hero()).tags[0][1]
        self.assertEqual((opening.get("class"), opening.get("aria-hidden"), opening.get("focusable")), ("hero-art", "true", "false"))
        self.assertEqual({"role", "aria-label", "id"} & set(opening), set())

    def test_crops_the_heros_paper_margin__with_its_view_box(self):
        """029-U3.1.6 — the hero's viewBox is `18 18 1164 684` — a flat band of margin sits between the page's grid and the sheet's frame."""
        self.when_written()

        self.assertEqual(view_box(self.hero()), HERO_VIEWBOX)

    def test_draws_the_hero_art_shape_for_shape__with_only_its_four_inks_turned_to_tokens(self):
        """029-U3.1.7 — every shape and group of hero-light.svg, in order and unchanged, with #12325A, #A87300, #F4F7FA, #D3DEEA read as currentColor, var(--brass), var(--bg), var(--line) — the approved art is redrawn, or loses its bulb, or keeps a fixed colour that shows a light patch on a dark theme."""
        self.when_written()

        art = HERO_ART.read_text()
        self.assertEqual(painted_shapes(self.hero()), painted_shapes(art, HERO_INKS))
        self.assertEqual(group_transforms(self.hero()), group_transforms(art))

    def test_leaves_no_fixed_art_colour_role_label_or_id_in_the_hero(self):
        """029-U3.1.8 — the hero markup holds none of #12325A, #A87300, #F4F7FA, #D3DEEA, and no `role=`, `aria-label=` or `id=` — a light ink survives on the dark themes, or an id collides with the page's."""
        self.when_written()

        hero = self.hero()
        for ink in (ART_LINE, ART_BRASS, ART_PAPER, ART_GRID):
            with self.subTest(ink=ink):
                self.assertNotIn(ink, hero.upper())
        self.assertIsNone(re.search(r"(?<![\w-])(?:role|aria-label|id)=", hero))

    def test_paints_every_paper_in_the_hero_the_page_background__the_owners_included(self):
        """029-U3.1.9 — each fill the art paints #F4F7FA, the Owner's body and head among them, is var(--bg) in the hero — one ink table for hero, stamp and figure fills the hero's Owner with the crew's figure fill."""
        self.when_written()

        self.assertEqual(paints_over(self.hero(), HERO_ART.read_text(), ART_PAPER), {"var(--bg)"})

    def test_draws_the_heros_grid_line_in_the_line_token(self):
        """029-U3.1.10 — the art's one #D3DEEA stroke is var(--line) in the hero — the grid stays light-blue on Blueprint and Night."""
        self.when_written()

        self.assertEqual(paints_over(self.hero(), HERO_ART.read_text(), ART_GRID), {"var(--line)"})

    def test_keeps_the_owners_light_bulb_in_the_hero(self):
        """029-U3.1.11 — the hero draws the path `M0 -132V-122`, the Owner's bulb — the crew's bulbless Owner is reused, forking the approved art."""
        self.when_written()

        self.assertIn(("path", BULB_START), [key for key, _ in art_shapes(self.hero())])

    def test_sizes_the_hero_as_the_spec_sets_it__in_the_stylesheet(self):
        """029-U3.1.12 — `.hero-art` is display block, width 100%, max-width 760px, height auto, margin `28px auto 18px`, colour var(--fg) — the hero renders at 1200 px wide, or its currentColor lines take the muted text colour (assumed Q9, Q14)."""
        self.when_written()

        found = styled_last(self.index, ".hero-art")
        self.assertEqual({name: found.get(name) for name in HERO_CSS}, HERO_CSS)

    def test_keeps_main_to_the_heading_and_the_empty_section__when_a_plan_usage_reading_is_shown(self):
        """029-U3.1.13 — with a plan-usage reading and no project, main still opens `<h1>Projects</h1><section class="empty">` with the hero — the usage line sits between the heading and the hero (assumed Q1)."""
        usage = self.base / "usage"
        usage.mkdir()
        (usage / "latest.json").write_text(json.dumps(READING_TAPPED) + "\n")

        self.when_written(env_usage=usage)

        self.assertRegex(self.main_markup(), rf"^\s*{re.escape(EMPTY_OPEN)}\s*{re.escape(HERO_OPEN)}")

    def test_shows_no_empty_state__when_an_orphan_session_exists_without_any_project(self):
        """029-U3.1.14 — a session with no project folder keeps the index out of the empty state: no `.empty`, no hero, the orphans listed — the orphan hides behind "No projects yet."."""
        self.given_session(slug="notes-app-001-first")

        self.when_written()

        self.assertIn(ORPHANS_HEADING, self.index)
        self.assertNotIn('class="empty"', self.index)
        self.assertNotIn(HERO_OPEN, self.index)


class EmptyHostileRoot(EmptyScratch):
    """No project and no session, under a projects root whose last folder is HOSTILE_ROOT_NAME."""

    def setUp(self):
        super().setUp()
        self.hostile_root = self.roots / HOSTILE_ROOT_NAME
        self.hostile_root.mkdir(parents=True)
        self.given_launch_settings(sessions_root=str(self.sessions), projects_root=str(self.hostile_root))

    def test_writes_a_hostile_projects_root_escaped__in_the_where_line(self):
        """029-U3.1.15 — line 3 carries the root as e() writes it, `&lt;x data-injected=&quot;root&quot;&gt; &amp; co` — the root reaches the page raw (assumed Q11)."""
        self.when_written()

        self.assertEqual(self.lines()[2:], [f'<p class="where">Looking for folders with a PROJECT.md under '
                                            f'<span class="mono">{self.roots}/{HOSTILE_ROOT_ESCAPED}</span></p>'])

    def test_writes_no_element_or_attribute_from_a_hostile_projects_root__on_the_empty_page(self):
        """029-U3.1.16 — the empty index holds no `x` element and no `data-injected` attribute — a folder name becomes markup on the dashboard (assumed Q11)."""
        self.when_written()

        tags = Tags(self.index)
        self.assertNotIn("x", {tag for tag, _ in tags.tags})
        self.assertNotIn(INJECTED, tags.attribute_names())


# ---------------------------------------------------------------- 029-U3 R2 · the empty state with no hero art


class EmptyFallback(EmptyScratch):
    """No project and no session; the dashboard run from a scratch copy of the clone with the hero gone."""

    def test_writes_the_three_lines_with_no_hero__when_the_hero_art_is_missing(self):
        """029-U3.2.1 — with hero-light.svg gone the empty section holds no <svg> and its three lines, exit 0 — a missing hero crashes the page or blanks the empty state (assumed Q4)."""
        script = self.given_clone_copy(missing=["hero-light.svg"])

        self.when_written(script=script)

        self.assertNotIn("<svg", self.empty_section())
        self.assertEqual([plain(line) for line in self.lines()],
                         ["No projects yet.", START_LINE, f"Looking for folders with a PROJECT.md under {self.projects}"])

    def test_writes_the_three_lines_with_no_hero__when_the_hero_art_cannot_be_read(self):
        """029-U3.2.2 — a directory where hero-light.svg should be leaves the same text-only empty section, exit 0 — an unreadable hero is a traceback (assumed Q4)."""
        script = self.given_clone_copy(unreadable=["hero-light.svg"])

        self.when_written(script=script)

        self.assertNotIn("<svg", self.empty_section())
        self.assertEqual([plain(line) for line in self.lines()],
                         ["No projects yet.", START_LINE, f"Looking for folders with a PROJECT.md under {self.projects}"])

    def test_keeps_the_footer_stamp__when_only_the_hero_art_is_missing(self):
        """029-U3.2.3 — with hero-light.svg gone the footer still opens with the stamp — one missing file takes the other art with it."""
        script = self.given_clone_copy(missing=["hero-light.svg"])

        self.when_written(script=script)

        self.assertEqual(classed(self.stamp(self.index), "stamp"), ["svg"])


# ---------------------------------------------------------------- 029-U3 R3 · one project ends the empty state


class EmptyGivesWay(EmptyScratch):
    def setUp(self):
        super().setUp()
        self.given_project()

    def test_shows_the_quiet_card_and_no_empty_state__when_one_project_has_no_session(self):
        """029-U3.3.1 — one project and no session: no `.empty`, no hero, the quiet card — the hero shows while a project exists."""
        self.when_written()

        self.assertNotIn('class="empty"', self.index)
        self.assertNotIn(HERO_OPEN, self.index)
        self.assertIn(QUIET_LINE, words(self.site()))

    def test_shows_the_crew_card_and_no_empty_state__when_one_project_has_a_running_session(self):
        """029-U3.3.2 — one project, SLUG implementing: no `.empty`, no hero, `On site · 1` — the hero shows beside the crew."""
        self.given_session()

        self.when_written()

        self.assertNotIn('class="empty"', self.index)
        self.assertNotIn(HERO_OPEN, self.index)
        self.assertEqual(self.heading(), "On site · 1")


# ---------------------------------------------------------------- 029-U3 R4 · the stamp first in every footer


class Stamp(EmptyScratch):
    """Each test writes its world: project `sample` with SLUG implementing, or nothing at all."""

    def test_opens_the_footer_with_the_stamp_then_the_updated_line__on_both_pages_once_writes(self):
        """029-U3.4.1 — index.html and sample.html each have `<footer id="foot">` holding `<svg class="stamp">` then `<span>Updated HH:MM:SS · refreshes every 20s…</span>` — a page misses its hallmark, or the stamp lands after the text (assumed Q7, Q8)."""
        self.given_project()
        self.given_session()

        self.when_written()

        for name in BRAND_PAGES:
            with self.subTest(page=name):
                stamp, text = self.footer((self.out / name).read_text())
                self.assertEqual(classed(stamp or "", "stamp"), ["svg"])
                self.assertIsNotNone(FOOTER_TEXT.fullmatch(text), text)

    def test_opens_the_footer_with_the_stamp_then_the_updated_line__on_both_pages_the_server_answers(self):
        """029-U3.4.2 — `/` and `/p/sample`, served, each open the footer with `<svg class="stamp">` then the `Updated` span — the live dashboard differs from the --once pages (assumed Q7, Q8)."""
        self.given_project()
        self.given_session()
        port, get = self.serve()

        for path in ("/", "/p/sample"):
            with self.subTest(path=path):
                status, body = get(path, f"127.0.0.1:{port}")
                stamp, text = self.footer(body)
                self.assertEqual(status, 200)
                self.assertEqual(classed(stamp or "", "stamp"), ["svg"])
                self.assertIsNotNone(FOOTER_TEXT.fullmatch(text), text)

    def test_opens_the_footer_with_the_stamp__on_the_empty_index(self):
        """029-U3.4.3 — with no project the index's footer opens with `<svg class="stamp">` then the `Updated` span — the empty page, the one a new user sees first, has no hallmark (assumed Q7, Q8)."""
        self.when_written()

        stamp, text = self.footer(self.index)
        self.assertEqual(classed(stamp or "", "stamp"), ["svg"])
        self.assertIsNotNone(FOOTER_TEXT.fullmatch(text), text)

    def test_hides_the_stamp_from_screen_readers_in_the_logos_view_box(self):
        """029-U3.4.4 — the stamp is `class="stamp"`, viewBox `-104 -104 208 208` as logo-light.svg's, `aria-hidden="true"`, `focusable="false"`, no `role` or `aria-label` — every footer announces "robowright maker's mark" (assumed Q6)."""
        self.when_written()

        stamp = self.stamp(self.index)
        opening = Tags(stamp).tags[0][1]
        self.assertEqual((opening.get("class"), view_box(stamp), opening.get("aria-hidden"), opening.get("focusable")),
                         ("stamp", view_box(LOGO_ART.read_text()), "true", "false"))
        self.assertEqual({"role", "aria-label"} & set(opening), set())

    def test_draws_the_logo_art_shape_for_shape__with_its_inks_turned_to_the_stamps_tokens(self):
        """029-U3.4.5 — every shape and group of logo-light.svg, in order and unchanged, with #12325A, #A87300, #F4F7FA read as currentColor, var(--stamp-accent), none — the mark is redrawn, or its brass pops at full strength."""
        self.when_written()

        stamp, art = self.stamp(self.index), LOGO_ART.read_text()
        self.assertEqual(painted_shapes(stamp), painted_shapes(art, STAMP_INKS))
        self.assertEqual(group_transforms(stamp), group_transforms(art))

    def test_paints_the_stamps_accent_in_the_faded_token_and_leaves_its_paper_unfilled(self):
        """029-U3.4.6 — the stamp carries `var(--stamp-accent)`, no #A87300 and no #F4F7FA, and the art's paper circle is `fill="none"` — a paper disc covers the footer, or the brass stays fixed on the dark themes."""
        self.when_written()

        stamp = self.stamp(self.index)
        self.assertIn("var(--stamp-accent)", stamp)
        self.assertNotIn(ART_BRASS, stamp.upper())
        self.assertNotIn(ART_PAPER, stamp.upper())
        self.assertEqual(paints_over(stamp, LOGO_ART.read_text(), ART_PAPER), {"none"})

    def test_lays_the_footer_out_in_a_centred_row__in_the_stylesheet(self):
        """029-U3.4.7 — `footer` declares `display:flex`, `align-items:center`, `gap:12px` — the stamp sits above the text, or the text rides its baseline (assumed Q14)."""
        self.when_written()

        found = styled_last(self.index, "footer")
        self.assertEqual({name: found.get(name) for name in FOOTER_CSS}, FOOTER_CSS)

    def test_sizes_the_stamp_at_48px_in_the_faint_ink__in_the_stylesheet(self):
        """029-U3.4.8 — `.stamp` declares width and height 48px, `color:var(--faint)`, `flex:none` — the rings merge below 44 px, or the stamp shrinks as the text wraps (assumed Q14)."""
        self.when_written()

        found = styled_last(self.index, ".stamp")
        self.assertEqual({name: found.get(name) for name in STAMP_CSS}, STAMP_CSS)

    def test_mixes_the_stamp_accent_from_brass_eighty_five_percent_toward_the_background__in_the_stylesheet(self):
        """029-U3.4.9 — every declaration of `--stamp-accent` is `color-mix(in srgb,var(--brass) 85%,var(--bg))` — the braces and cursor pop out of a faint stamp, or fall under 3:1 in Whiteprint (assumed Q13; 85% from U32 bound 1, 032-F1.2)."""
        self.when_written()

        accents = {declarations["--stamp-accent"] for _, declarations in top_level_rules(self.index)
                   if "--stamp-accent" in declarations}
        self.assertEqual(accents, {STAMP_ACCENT})


# ---------------------------------------------------------------- 029-U3 R5 · the footer with no logo art


class StampFallback(EmptyScratch):
    """The dashboard run from a scratch copy of the clone with logo-light.svg gone or unreadable."""

    def test_writes_the_footer_text_alone__when_the_logo_art_is_missing(self):
        """029-U3.5.1 — with logo-light.svg gone, index.html and sample.html each end in `<footer id="foot"><span>Updated …</span></footer>`, exit 0 — a missing logo crashes every page or drops the update time (assumed Q3, Q8)."""
        self.given_project()
        self.given_session()
        script = self.given_clone_copy(missing=["logo-light.svg"])

        self.when_written(script=script)

        for name in BRAND_PAGES:
            with self.subTest(page=name):
                stamp, text = self.footer((self.out / name).read_text())
                self.assertIsNone(stamp)
                self.assertIsNotNone(FOOTER_TEXT.fullmatch(text), text)

    def test_writes_the_footer_text_alone__when_the_logo_art_cannot_be_read(self):
        """029-U3.5.2 — a directory where logo-light.svg should be leaves the index's footer as its `Updated` span alone, exit 0 — an unreadable logo is a traceback (assumed Q3, Q8)."""
        self.given_project()
        script = self.given_clone_copy(unreadable=["logo-light.svg"])

        self.when_written(script=script)

        stamp, text = self.footer(self.index)
        self.assertIsNone(stamp)
        self.assertIsNotNone(FOOTER_TEXT.fullmatch(text), text)

    def test_keeps_the_hero__when_only_the_logo_art_is_missing(self):
        """029-U3.5.3 — with logo-light.svg gone and no project, the empty section still opens with the hero — one missing file takes the other art with it."""
        script = self.given_clone_copy(missing=["logo-light.svg"])

        self.when_written(script=script)

        self.assertTrue(self.empty_section().startswith(HERO_OPEN), self.empty_section()[:80])


# ---------------------------------------------------------------- 029-U3 R6 · /attention.json with no project


class EmptyJson(EmptyScratch):
    """The dashboard served on a free port."""

    def test_serves_an_empty_attention_list__when_there_is_no_project(self):
        """029-U3.6.1 — with no project /attention.json is `[]` — the empty state adds a row or a field the notifier keys on."""
        port, get = self.serve()

        status, body = get("/attention.json", f"127.0.0.1:{port}")

        self.assertEqual((status, body), (200, "[]"))

    def test_serves_attention_json_byte_for_byte_as_before__beside_the_footer_stamp(self):
        """029-U3.6.2 — CrewJson's world serves `ATTENTION_JSON` to the byte — the footer stamp changes the rows the notifier keys on."""
        self.given_project()
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))
        self.given_stopped(SECOND)
        self.given_session(slug="sample-003-third", phase="briefed")
        self.given_session(slug="sample-004-fourth")
        port, get = self.serve()

        status, body = get("/attention.json", f"127.0.0.1:{port}")

        self.assertEqual((status, body), (200, ATTENTION_JSON))


# ---------------------------------------------------------------- 031 · row glyphs on the project page's session cards

CARD_GLYPH_RULES = (
    ".sess>summary>.gl{grid-column:1/-1;display:flex;align-items:flex-end;height:30px;--fig-fill:none}",
)
SUMMARY_RULE = (".sess>summary{display:grid;grid-template-columns:minmax(0,1fr) auto auto;column-gap:14px;row-gap:4px;"
                "align-items:baseline;padding:14px 20px 12px;cursor:pointer;list-style:none}")
NARROW_SUMMARY_RULE = ".sess>summary{padding:12px 16px 10px;grid-template-columns:minmax(0,1fr) auto}"
CARD_GLYPH = re.compile(r'<span class="gl" aria-hidden="true">\s*(<svg\b.*?</svg>)\s*</span>', re.S)


class CardScratch(CrewScratch):
    """launch.json naming both roots. Each test writes its world, runs `--once` once, and reads a page's session cards:
    `<details class="sess …" id="s-<slug>">`, its `<summary>` up to `</summary>`."""

    def page(self, project="sample"):
        """The project page `--once` writes, named for the project's folder as it is."""
        return (self.out / f"{project}.html").read_text()

    def card(self, slug, page):
        """(the card's `<details>` attributes, its summary's inner markup) for `slug`'s card on `page`; the test fails when
        there is none."""
        match = re.search(rf'(<details\b[^>]*\bid="{re.escape(anchor_of(slug))}"[^>]*>)<summary>(.*?)</summary>', page, re.S)
        if match is None:
            self.fail(f"no session card for {slug}")
        return Tags(match.group(1)).tags[0][1], match.group(2)

    def card_glyph(self, slug, page):
        """The <svg> `slug`'s summary opens with, inside `<span class="gl" aria-hidden="true">`; the test fails when the
        summary opens with anything else."""
        _, summary = self.card(slug, page)
        match = CARD_GLYPH.match(summary)
        if match is None:
            self.fail(f"{slug}'s summary opens with {summary[:80]!r}, not the glyph")
        return match.group(1)

    def assert_carded(self, slug, role, page):
        """`slug`'s card is classed `sess`, and its summary opens with the glyph drawing `role`'s figure and no other's."""
        attrs, _ = self.card(slug, page)
        self.assertIn("sess", (attrs.get("class") or "").split())
        self.assertEqual(roles_drawn(self.card_glyph(slug, page)), {role})

    def assert_uncarded(self, slug, page):
        """`slug`'s card carries no class `g` and no `.gl` in its summary."""
        attrs, summary = self.card(slug, page)
        self.assertNotIn("g", (attrs.get("class") or "").split())
        self.assertEqual(classed(summary, "gl"), [])


def anchor_of(slug):
    return "s-" + re.sub(r"[^\w-]", "-", slug)


class CardGlyph(CardScratch):
    """Project `sample` with U1 `first`; the sessions each test names."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def test_draws_the_figure_role_maps_to__on_each_attention_and_working_card(self):
        """031-P1.1 — stopped → Owner and briefed → Lead (Needs attention), implementing → Worker and end-of-stack → Reviewer (Working), each card classed `sess` (U33: the `g` class went with the grid it keyed) — an on-site card shows no one, or the wrong one."""
        self.given_stopped()
        self.given_session(slug=SECOND, phase="briefed")
        self.given_session(slug="sample-003-third")
        self.given_session(slug="sample-004-fourth", phase="end-of-stack", units=[{"id": "U1", "status": "done"}])

        self.when_written()

        page = self.page()
        for slug, role in ((SLUG, "owner"), (SECOND, "lead"), ("sample-003-third", "worker"), ("sample-004-fourth", "reviewer")):
            with self.subTest(slug=slug):
                self.assert_carded(slug, role, page)

    def test_puts_the_glyph_first_in_the_summary__then_the_dot_slug_state_and_time_unchanged(self):
        """031-P1.2, as U33 re-cut it — the working card's summary is the glyph, then the slug span, then the dot inside the state, then the time — the glyph lands after the slug, or a second marker returns to the left edge (DESIGN-U33 §4.5 `render_session`, §4.7 rule 4)."""
        self.given_session()

        self.when_written()

        _, summary = self.card(SLUG, self.page())
        rest = CARD_GLYPH.sub("", summary, count=1)
        self.assertTrue(CARD_GLYPH.match(summary), summary[:80])
        self.assertRegex(rest, r'^<span class="slug mono" title="sample-001-first">001-first</span>'
                               r'<span class="st"><i class="dot run"></i>Working</span><span class="ago">[^<]*</span>$')

    def test_draws_no_glyph_on_waiting_done_or_error_cards__nor_on_awaiting_acceptance(self):
        """031-P2.1 — a parked, a done and an unreadable session's cards carry no `.gl` and no `g`, and the Awaiting acceptance alert none — a figure claims someone is on site who is not."""
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))
        self.given_session(slug=SECOND, parked=True)
        (self.given_session(slug="sample-003-third") / "run.json").write_text("{")
        self.given_session(slug="sample-004-fourth", phase="done", intake=True, units=[{"id": "U1", "status": "done"}])

        self.when_written()

        page = self.page()
        for slug in (SECOND, "sample-003-third", "sample-004-fourth"):
            with self.subTest(slug=slug):
                self.assert_uncarded(slug, page)
        alert = re.search(r'<a class="alert awaiting".*?</a>', page, re.S)
        self.assertIsNotNone(alert, "no Awaiting acceptance alert")
        self.assertEqual(classed(alert.group(0), "gl"), [])

    def test_draws_one_figure_per_on_site_card__and_no_other_on_the_project_page(self):
        """031-P2.2, as U33 re-cut it — beside the header mark, the footer stamp and the project's own crew card's two figures, the page's only <svg>s are the two on-site cards' glyphs — a second, larger figure appears in a card's body (DESIGN-U33 §4.7 rule 5)."""
        self.given_stopped()
        self.given_session(slug=SECOND)
        self.given_session(slug="sample-003-third", parked=True)

        self.when_written()

        page = self.page()
        crew = re.search(r'<section class="site".*?</section>', page, re.S).group(0)
        outside_crew = page.replace(crew, "")
        figures = [(attrs.get("class") or "") for tag, attrs in Tags(outside_crew).tags if tag == "svg"]
        self.assertEqual(sorted(figures), ["fig", "fig", "mark", "stamp"])
        self.assertEqual([attrs.get("class") for tag, attrs in Tags(crew).tags if tag == "svg"], ["fig", "fig"])
        self.assertEqual(len(CARD_GLYPH.findall(page)), 2)
        self.assertEqual([self.card_glyph(slug, page) for slug in (SLUG, SECOND)], CARD_GLYPH.findall(page))

    def test_keeps_the_glyph_when_a_card_is_collapsed__no_rule_hides_it(self):
        """031-P2.3 — the glyph sits in the `<summary>` a collapsed card still shows, and no rule selects a `.gl` by `[open]` or hides it — a collapsed on-site card loses who holds it (Owner Q1)."""
        self.given_session()

        self.when_written()

        page = self.page()
        self.card_glyph(SLUG, page)
        css = "".join(re.findall(r"<style>(.*?)</style>", page, re.S))
        hiding = [rule for rule in re.findall(r"[^{}]+\{[^{}]*\}", css)
                  if ".gl" in rule.partition("{")[0] and ("[open]" in rule or "display:none" in rule)]
        self.assertEqual(hiding, [])

    def test_draws_the_same_constant_glyph_on_the_card_as_on_the_index_row(self):
        """031-P3.1 — the stopped and the working card's glyph is byte for byte its index row's — the card's figure is built per session, not the module constant."""
        self.given_stopped()
        self.given_session(slug=SECOND)

        self.when_written()

        page = self.page()
        for slug in (SLUG, SECOND):
            with self.subTest(slug=slug):
                self.assertEqual(self.card_glyph(slug, page), self.glyph(session_href(slug)))

    def test_carries_the_spec_rules_and_keeps_the_summary_rules__in_the_stylesheet(self):
        """031-P4.1, as U33 re-cut it — the summary grid, its glyph row and its 560 px two-column rule are in the stylesheet verbatim — the figure, slug and state lose their one left edge (DESIGN-U33 §4.6)."""
        self.given_session()

        self.when_written()

        css = "".join(re.findall(r"<style>(.*?)</style>", self.page(), re.S))
        for rule in CARD_GLYPH_RULES + (SUMMARY_RULE, NARROW_SUMMARY_RULE):
            with self.subTest(rule=rule):
                self.assertIn(rule, css)


class OrphanCardGlyph(CardScratch):
    """No project folder: `notes-app-001-first` implementing and `notes-app-002-second` parked, orphans on the index."""

    def test_draws_the_glyph_on_a_running_orphans_card__and_none_on_a_parked_one(self):
        """031-P5.1 — on the index's orphan list the running card carries the Worker, the parked card none — orphans skip the rule `render_session` keeps."""
        self.given_session(slug="notes-app-001-first")
        self.given_session(slug="notes-app-002-second", parked=True)

        self.when_written()

        self.assertIn(ORPHANS_HEADING, self.index)
        self.assert_carded("notes-app-001-first", "worker", self.index)
        self.assert_uncarded("notes-app-002-second", self.index)


class CardGlyphHostile(CardScratch):
    """The hostile world (`given_hostile_projects`): project LIVE_NAME holds SLUG, stopped, and SECOND, implementing."""

    given_hostile_projects = Hostile.given_hostile_projects

    def test_carries_nothing_of_a_hostile_name_or_slug__in_either_cards_glyph(self):
        """031-P3.2 — neither card's glyph holds the project name raw, escaped or quoted, `data-injected`, or the slug, and the page carries no `data-injected` attribute — the card's figure interpolates session data."""
        self.given_hostile_projects()

        self.when_written()

        page = self.page(LIVE_NAME)
        for slug in (SLUG, SECOND):
            with self.subTest(slug=slug):
                glyph = self.card_glyph(slug, page)
                found = [value for value in (LIVE_NAME, html.escape(LIVE_NAME), quote(LIVE_NAME, safe=""), INJECTED, slug)
                         if value in glyph]
                self.assertEqual(found, [])
        self.assertNotIn(INJECTED, Tags(page).attribute_names())


class GhostTarget(CrewScratch):
    """Project `sample` with U1 `first`; seven on site, the k-th of ON_SITE last written k minutes ago."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def test_links_every_ghost_to_needs_attention__when_no_running_member_is_on_the_crew(self):
        """031-G1.1 — seven stopped sessions: each ghost links `#attention`, which the index carries, and there is no `#flight` — the ghost leads nowhere (U29 end-of-stack F1; Decided (Lead) 2026-10-14)."""
        for minutes, slug in enumerate(ON_SITE[:7], start=1):
            self.given_touched(self.given_stopped(slug), minutes)

        self.when_written()

        self.assertEqual(sorted(g["attrs"].get("href") for g in self.ghosts()), ["#attention"] * 3)
        self.assertIn('id="attention"', self.index)
        self.assertNotIn('id="flight"', self.index)

    def test_links_every_ghost_to_in_flight__when_a_running_member_is_on_the_crew_past_the_cap(self):
        """031-G1.2 — six stopped and one implementing, the running one seventh and hidden: each ghost links `#flight`, which the index carries — the target follows only the drawn members (Decided (Lead) 2026-10-14)."""
        for minutes, slug in enumerate(ON_SITE[:6], start=1):
            self.given_touched(self.given_stopped(slug), minutes)
        self.given_touched(self.given_session(slug=ON_SITE[6]), 7)

        self.when_written()

        self.assertEqual(sorted(g["attrs"].get("href") for g in self.ghosts()), ["#flight"] * 3)
        self.assertIn('id="flight"', self.index)



# ================================================================ 032 · the footer's contrast; wrong-shaped run.json values
# Rows are `032-…` in BEHAVIORS.md. Contrast is WCAG 2.x's, from each theme's tokens as the page declares them.


THEME_NAMES = ("whiteprint", "blueprint", "night")
# WCAG 2.x AA: normal text (1.4.3), and a graphic's parts (1.4.11).
TEXT_CONTRAST, GRAPHIC_CONTRAST = 4.5, 3.0
STAMP_MIX = re.compile(r"color-mix\(in srgb,var\(--([\w-]+)\) (\d+(?:\.\d+)?)%,var\(--bg\)\)")


def channels(hex_):
    return [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def luminance(rgb):
    """WCAG 2.x relative luminance of sRGB channels in [0, 1]."""
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def token_of(value):
    """`var(--name)` → `name`; the test fails on anything else, so a literal colour cannot dodge the theme check."""
    match = re.fullmatch(r"var\(--([\w-]+)\)", value or "")
    return match and match.group(1)


class FooterContrast(GlyphScratch):
    """Project `sample` with SLUG implementing; one `--once` run; each theme's tokens read from the page's
    `:root[data-theme=<name>]` rule."""

    def setUp(self):
        super().setUp()
        self.given_project()
        self.given_session()
        self.when_written()

    def themes(self):
        rules = {selectors[0][len(":root[data-theme="):-1]: body for selectors, body in css_rules(self.index)
                 if selectors[0].startswith(":root[data-theme=")}
        return {name: {key: value for key, value in re.findall(r"--([\w-]+):(#[0-9A-Fa-f]{6})", rules[name])}
                for name in THEME_NAMES}

    def test_writes_the_footer_text_at_least_four_and_a_half_to_one_on_the_background__in_every_theme(self):
        """032-F1.1 — the `footer` rule's colour is a theme token whose contrast on `--bg` is at least 4.5:1 in Whiteprint, Blueprint and Night — the footer's 12 px text fails AA (U32 bound 1; was 3.0:1 in Whiteprint)."""
        ink = token_of(styled_last(self.index, "footer").get("color"))
        self.assertTrue(ink, "the footer's colour is not a theme token")
        for name, tokens in self.themes().items():
            with self.subTest(theme=name):
                self.assertGreaterEqual(contrast(channels(tokens[ink]), channels(tokens["bg"])), TEXT_CONTRAST)

    def test_draws_the_stamps_line_and_accent_at_least_three_to_one_on_the_background__in_every_theme(self):
        """032-F1.2 — the stamp's line ink (`.stamp` colour) and `--stamp-accent` (brass mixed toward `--bg`) each reach 3:1 on `--bg` in every theme — the mark's braces vanish into the paper (U32 bound 1, "a graphic, held to 3:1")."""
        line = token_of(styled_last(self.index, ".stamp").get("color"))
        mix = STAMP_MIX.fullmatch(styled_last(self.index, "footer").get("--stamp-accent") or "")
        self.assertTrue(line and mix, "the stamp's inks are not theme tokens")
        accent, share = mix.group(1), float(mix.group(2)) / 100
        for name, tokens in self.themes().items():
            bg = channels(tokens["bg"])
            mixed = [share * a + (1 - share) * b for a, b in zip(channels(tokens[accent]), bg)]
            with self.subTest(theme=name, ink="line"):
                self.assertGreaterEqual(contrast(channels(tokens[line]), bg), GRAPHIC_CONTRAST)
            with self.subTest(theme=name, ink="accent"):
                self.assertGreaterEqual(contrast(mixed, bg), GRAPHIC_CONTRAST)


class WrongShapes(DashScratch):
    """launch.json naming both roots; project `sample` with U1 `first`. Each test writes SLUG with one run.json value
    of the wrong shape, carrying markup syntax where it holds a string."""

    run_dash_recording_git = InMain.run_dash_recording_git

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.folder = self.given_project()

    # ------------------------------------------------------------ given

    def given_run_edit(self, run_dir, edit):
        """run_dir's run.json passed through `edit`, keeping the quiet given_session gave it."""
        path = run_dir / "run.json"
        run = json.loads(path.read_text())
        edit(run)
        written = path.stat().st_mtime
        path.write_text(json.dumps(run, indent=2) + "\n")
        os.utime(path, (written, written))

    # ------------------------------------------------------------ when

    def when_served(self, **env_roots):
        """`--serve`, one GET each of `/` and `/p/sample`, then stopped: ({path: status, None when the connection
        dropped or no answer came}, {path: body}, stderr)."""
        port = free_port()
        server = subprocess.Popen([sys.executable, str(DASH), "--serve", str(port)], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, text=True, env=self.env(**env_roots), cwd=str(self.cwd))
        self.addCleanup(lambda: server.poll() is None and server.kill())
        deadline = time.monotonic() + 20
        while server.poll() is None and time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        statuses, bodies = {}, {}
        for path in ("/", "/p/sample"):
            request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": f"127.0.0.1:{port}"})
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    statuses[path], bodies[path] = response.status, response.read().decode()
            except urllib.error.HTTPError as err:
                statuses[path], bodies[path] = err.code, err.read().decode()
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                statuses[path], bodies[path] = None, ""
        server.terminate()
        try:
            _, err = server.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            _, err = server.communicate()
        return statuses, bodies, err

    def when_card_written(self, name):
        """`--once <base>/<name>`: exit 0, no traceback; SLUG's card on sample.html as (its text as the Owner reads it,
        the text of each `.state` in it: the session's, then each unit's)."""
        out = self.base / name
        result = self.run_dash("--once", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        page = Page(out / "sample.html")
        return page.card(SLUG), page.texts("st", card=SLUG) + page.texts("state", card=SLUG)

    # ------------------------------------------------------------ then

    def then_both_pages_answer(self, served):
        statuses, bodies, err = served
        self.assertEqual(statuses, {"/": 200, "/p/sample": 200})
        self.assertNotIn("Traceback", err)
        for path, body in bodies.items():
            with self.subTest(path=path):
                self.assertNotIn(INJECTED, Tags(body).attribute_names())

    # S1 · a wrong shape never fails a page

    def test_serves_the_index_and_the_project_page__when_phase_is_a_list(self):
        """032-S1.1 — `phase` a list holding markup syntax: `/` and `/p/sample` each answer 200, no traceback, no injected attribute — the whole dashboard fails on one session's file (U32 bound 2; U29 HANDBACK §6)."""
        self.given_session(phase=[f'<b {INJECTED}="phase">', "implement"])

        self.then_both_pages_answer(self.when_served())

    def test_serves_the_index_and_the_project_page__when_phase_is_a_dict(self):
        """032-S1.2 — `phase` an object whose key holds markup syntax: both pages answer 200, no traceback, no injected attribute — the index fails on an unhashable phase (U32 bound 2)."""
        self.given_session(phase={f'<b {INJECTED}="phase">': "implement"})

        self.then_both_pages_answer(self.when_served())

    def test_serves_the_index_and_the_project_page__when_a_units_status_is_a_list(self):
        """032-S1.3 — U2's `status` a list holding markup syntax: both pages answer 200, no traceback, no injected attribute — a unit's status fails the run track (U32 bound 2)."""
        self.given_session(units=[{"id": "U1", "status": "done"}, {"id": "U2", "status": [f'<b {INJECTED}="status">']}])

        self.then_both_pages_answer(self.when_served())

    # S2 · a wrong shape reads as a missing value

    def test_reads_a_list_valued_phase_as_no_phase__on_the_session_card(self):
        """032-S2.1 — SLUG's card with `phase: ["implement"]` reads word for word as with no `phase`, whose states read `Working`, `done`, `not started` in the dashboard before U32 — a wrong shape shows as something a missing value never does, or the hold changes how a missing one reads (U32 bound 2, "reads as the same thing a missing one does today")."""
        run_dir = self.given_session()
        self.given_run_edit(run_dir, lambda run: run.pop("phase"))
        missing = self.when_card_written("missing")
        self.given_run_edit(run_dir, lambda run: run.update(phase=["implement"]))

        self.assertEqual(missing[1], ["Working", "done", "not started"])
        self.assertEqual(self.when_card_written("wrong"), missing)

    def test_reads_a_list_valued_unit_status_as_no_status__on_the_session_card(self):
        """032-S2.2 — SLUG's card with U2's `status: ["building"]` reads word for word as with U2 carrying no `status`, whose states read `Working`, `done`, `?` (`Working · implement` in the dashboard before U33, which keeps raw phases off the face) (U32 bound 2, as S2.1)."""
        run_dir = self.given_session()
        self.given_run_edit(run_dir, lambda run: run["units"][1].pop("status"))
        missing = self.when_card_written("missing")
        self.given_run_edit(run_dir, lambda run: run["units"][1].update(status=["building"]))

        self.assertEqual(missing[1], ["Working", "done", "?"])
        self.assertEqual(self.when_card_written("wrong"), missing)

    # S3 · the other fields session-inputs.md names: ticket and commit ids

    def test_serves_the_index_and_the_project_page__when_ticket_is_a_list_and_a_ledger_exists(self):
        """032-S3.1 — `ticket` a list, with an accounting ledger: both pages answer 200, no traceback — the spend lookup fails on an unhashable ticket (U32 bound 2, "any other run.json field the same rule names")."""
        accounting = self.base / "accounting"
        accounting.mkdir()
        (accounting / "records.jsonl").write_text(json.dumps(ledger_record(SLUG, "worker", "s-1", 3, 500, 1.25, 600)) + "\n")
        self.given_session(ticket=[SLUG])

        self.then_both_pages_answer(self.when_served(env_accounting=accounting))

    def test_summarises_the_project__when_a_finished_units_head_is_a_list(self):
        """032-S3.2 — SLUG done in a listed worktree, its unit's `head` a list: `robowright-dash.py sample` exits 0 and reads U1 awaiting acceptance — git's argv fails on a non-string (U32 bound 2; commit id: `COMMIT_ID` in run-cost.py)."""
        self.given_finished_repo(head=["0" * 40])

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("awaiting acceptance", unit_line(result.stdout, "U1"))

    def test_passes_no_option_shaped_head_or_tip_to_git__when_a_finished_session_writes_them(self):
        """032-S3.3 — SLUG done in a listed worktree, its unit's `head` `--head-option` and `publish.tip` `--tip-option`: no git call carries either, and U1 reads awaiting acceptance — a session's value reaches git as a flag (U32 bound 2; `session-inputs.md`, commit ids)."""
        self.given_finished_repo(head="--head-option", publish={"tip": "--tip-option"})

        result, calls = self.run_dash_recording_git("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("awaiting acceptance", unit_line(result.stdout, "U1"))
        self.assertEqual([c for c in calls if any(a.startswith(("--head-option", "--tip-option")) for a in c)], [])

    # S4 · the rest of SECURITY.md's state-field row, and `worktree`

    def test_serves_the_index_and_the_project_page__when_rotate_is_a_string(self):
        """032-S4.1 — `rotate` a string: both pages answer 200, no traceback — `rotate.get` fails every page (review 1 F1; SECURITY.md, the `phase`, `stop_reason`, `rotate`, `rebriefs`, `units[]` row)."""
        self.given_session(rotate="x")

        self.then_both_pages_answer(self.when_served())

    def test_serves_the_index_and_the_project_page__when_a_stopped_sessions_stop_reason_is_a_list(self):
        """032-S4.2 — `phase: stopped`, `stop_reason` a list: both pages answer 200, no traceback — `stop.get` fails the page (review 1 F1)."""
        self.given_session(phase="stopped", stop_reason=["x"])

        self.then_both_pages_answer(self.when_served())

    def test_serves_the_index_and_the_project_page__when_a_rebrief_entry_is_not_an_object(self):
        """032-S4.3 — a pending rebrief rotation whose `rebriefs` holds a number: both pages answer 200, no traceback (review 1 F1)."""
        self.given_session(rotate={"reason": "rebrief", "requested_at": iso(datetime.now(timezone.utc))}, rebriefs=[1])

        self.then_both_pages_answer(self.when_served())

    def test_serves_the_index_and_the_project_page__when_units_is_an_object(self):
        """032-S4.4 — `units` an object keyed by unit id: both pages answer 200, no traceback (review 1 F1)."""
        self.given_session(units={"U1": {"status": "done"}})

        self.then_both_pages_answer(self.when_served())

    def test_serves_the_index_and_the_project_page__when_a_unit_is_not_an_object(self):
        """032-S4.5 — `units` holding a number beside a unit: both pages answer 200, no traceback (review 1 F1)."""
        self.given_session(units=[{"id": "U1", "status": "done"}, 7])

        self.then_both_pages_answer(self.when_served())

    def test_serves_the_index_and_the_project_page__when_worktree_is_a_list(self):
        """032-S4.6 — a working session's `worktree` a list: both pages answer 200, no traceback — the activity scan fails every page (review 1 F1; SECURITY.md, the `worktree` row names the dashboard)."""
        self.given_session(worktree=["x"])

        self.then_both_pages_answer(self.when_served())

    # S5 · the strings inside `stop_reason` and `rebriefs`

    def test_serves_the_index_and_the_project_page__when_a_stop_detail_is_a_list(self):
        """032-S5.1 — `phase: stopped`, `stop_reason.detail` a list: both pages answer 200, no traceback — `clip` fails the needs-attention row (review 2 F4)."""
        self.given_session(phase="stopped", stop_reason={"code": "gate-attempts", "detail": ["x"]})

        self.then_both_pages_answer(self.when_served())

    def test_serves_the_index_and_the_project_page__when_a_rebriefs_why_is_a_number(self):
        """032-S5.2 — a pending rebrief whose last entry's `why` is a number: both pages answer 200, no traceback (review 2 F4)."""
        self.given_session(rotate={"reason": "rebrief", "requested_at": iso(datetime.now(timezone.utc))},
                           rebriefs=[{"verdict": "owner", "why": 5}])

        self.then_both_pages_answer(self.when_served())

    def test_summarises_the_project__when_a_stop_code_is_a_list(self):
        """032-S5.3 — `stop_reason.code` a list: `robowright-dash.py` exits 0, no traceback, and SLUG's line carries no code — the summary's `'  · ' + code` fails (review 2 F4; SECURITY.md's `stop_reason.code` row)."""
        self.given_session(stop_reason={"code": ["x"]})

        result = self.run_dash()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertRegex(result.stdout, rf"(?m)^    {SLUG}  implement  · \d+m ago$")

    # S6 · a run.json the dashboard cannot serve reads as an unreadable one

    def then_reads_as_unreadable(self):
        """Both pages answer 200 with no traceback, and SLUG's card on sample.html is the error card: its one state
        reads `Unreadable`, as a run.json of `{` reads in the dashboard before U32."""
        self.then_both_pages_answer(self.when_served())
        _, states = self.when_card_written("once")
        self.assertEqual(states, ["Unreadable"])

    def test_reads_as_unreadable__when_run_json_is_not_an_object(self):
        """032-S6.1 — run.json a JSON list: both pages answer 200, SLUG's card reads `Unreadable` — every page fails at `run.get` (review 1 F3; Lead 2026-10-14)."""
        (self.given_session() / "run.json").write_text("[1]\n")

        self.then_reads_as_unreadable()

    def test_reads_as_unreadable__when_a_string_holds_a_lone_surrogate(self):
        """032-S6.2 — `phase` a lone surrogate escape: both pages answer 200, SLUG's card reads `Unreadable` — the page cannot be encoded as UTF-8 (review 3 N1; Lead 2026-10-14)."""
        self.given_session(phase="\ud800")

        self.then_reads_as_unreadable()

    def test_reads_as_unreadable__when_a_number_has_more_digits_than_python_converts(self):
        """032-S6.3 — `max_wall_hours` an integer of 5000 digits: both pages answer 200, SLUG's card reads `Unreadable` — `json.loads` raises a ValueError the loader does not catch (review 3 N2; Lead 2026-10-14)."""
        path = self.given_session() / "run.json"
        path.write_text(path.read_text().replace('"phase"', f'"max_wall_hours": {"9" * 5000}, "phase"', 1))

        self.then_reads_as_unreadable()

    def given_nested(self, depth):
        """SLUG implementing, its run.json carrying `deep`: empty lists nested `depth` levels."""
        path = self.given_session() / "run.json"
        path.write_text(path.read_text().replace('"phase"', f'"deep": {"[" * depth}{"]" * depth}, "phase"', 1))

    def test_reads_as_unreadable__when_run_json_nests_deeper_than_encoding_reaches(self):
        """032-S6.4 — a value nested 110,000 deep, which `json.loads` reads and `json.dumps` overflows: both pages answer 200, SLUG's card reads `Unreadable` — a check by encoding fails a run.json the dashboard before U32 served (review 4 F1; reads Unreadable by the depth cap, review 5 F1)."""
        self.given_nested(110_000)

        self.then_reads_as_unreadable()

    def test_reads_as_unreadable__when_a_displayed_value_nests_deeper_than_str_reaches(self):
        """032-S6.6 — U1's `id` a list nested 80,000 deep, under the encoder's limit and past `str()`'s: both pages answer 200, SLUG's card reads `Unreadable` — the run track's f-string overflows and fails the page (review 5 F1)."""
        path = self.given_session() / "run.json"
        path.write_text(path.read_text().replace('"id": "U1"', f'"id": {"[" * 80_000}{"]" * 80_000}', 1))

        self.then_reads_as_unreadable()

    def test_renders_the_card_as_without_it__when_an_unread_value_nests_fifty_deep(self):
        """032-S6.7 — a field the dashboard never reads, a list nested 50 deep: SLUG's card reads word for word as without it — the depth cap hides a session a real run.json could be (session-state.py writes about 4 levels; review 5 F1's fix)."""
        run_dir = self.given_session()
        plain = self.when_card_written("plain")
        self.given_run_edit(run_dir, lambda run: run.update(deep=json.loads("[" * 50 + "]" * 50)))

        self.assertEqual(self.when_card_written("deep"), plain)

    def test_reads_as_unreadable__when_run_json_nests_deeper_than_json_loads_reaches(self):
        """032-S6.5 — a value nested 200,000 deep, past `json.loads`'s own limit: both pages answer 200, SLUG's card reads `Unreadable` — the parser's RecursionError fails every page (review 4 F1; Lead 2026-10-14, "catch what `json.loads` raises")."""
        self.given_nested(200_000)

        self.then_reads_as_unreadable()

    def test_ends_options_before_every_revision_given_to_merge_base_and_log(self):
        """033-G1 — every `merge-base` and `log` call the in-main check makes ends its options with `--end-of-options` before its revisions — a value shaped like an option reaches git as one (U33 bound 5, N-6; `session-inputs.md`, "end options with `--end-of-options`")."""
        self.given_finished_repo(head="not-a-commit")

        result, calls = self.run_dash_recording_git("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        merge_bases = [c for c in calls if "merge-base" in c]
        logs = [c for c in calls if "log" in c]
        self.assertTrue(merge_bases and logs, calls)
        self.assertEqual([c[-3] for c in merge_bases], ["--end-of-options"] * len(merge_bases))
        self.assertEqual([c[-2] for c in logs], ["--end-of-options"] * len(logs))

    def given_finished_repo(self, head, **fields):
        """SLUG done and through intake in a scratch repo robowright.json lists, its branch not in main; U1's `head`
        as given."""
        self.repo = self.given_repo(f"robowright/{SLUG}", merged=False)
        self.given_settings(self.folder, "robowright.json", {"repos": [{"name": "sample", "path": str(self.repo)}]})
        self.given_allowlisted(self.repo)
        self.given_session(phase="done", intake=True, worktree=str(self.repo),
                           units=[{"id": "U1", "status": "done", "head": head}], **fields)


# ================================================================ 033 · the content pass: direction B of DESIGN-U33
# Rows `033-…` in BEHAVIORS.md. A card's face is its <summary> and every part of its body outside Details; Details is
# the card's `<details class="sub more">`. A plan row's face is its `summary.row` (or its plain `div.row`), and its
# disclosure is `<details class="unit" id="u-<id>">`.

PIPE_SUMMARY = r"Totals a \| b per unit"
STOP_CODE, STOP_DETAIL = "verification-failed", "the sample's suite is red"


def card_summary(page_text, slug):
    """The markup inside `slug`'s card's <summary>; '' when the page has no such card."""
    match = re.search(rf'<details class="sess[^"]*" id="s-{re.escape(slug)}"[^>]*><summary>(.*?)</summary>', page_text, re.S)
    return match.group(1) if match else ""


def plan_stages(page_text):
    """Each stage of a project page's plan, in order: its label, its theme, and the ids of the units inside it."""
    plan = page_text.split('<h2 id="plan">', 1)[-1].split("<h2 ", 1)[0]
    return [(re.search(r"<b>([^<]*)</b>", stage).group(1), re.search(r'<span class="stage-name">([^<]*)</span>', stage).group(1),
             re.findall(r'<span class="id mono">([^<]+)</span>', stage))
            for stage in re.split(r'<details class="plan-stage" id="stage-[\w-]+"[^>]*>', plan)[1:]]


class ContentPass(GlyphScratch):
    """launch.json naming both roots; each test writes its own projects and sessions and runs `--once` once."""

    def given_plan(self, header, *rows, name="sample"):
        folder = self.projects / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "PROJECT.md").write_text(project_md(header, *rows).replace("# Sample", f"# {name}"))
        return folder

    def given_events(self, run_dir, *events):
        (run_dir / "events.jsonl").write_text("".join(json.dumps(ev) + "\n" for ev in events))

    def page(self, name="sample.html"):
        return Page(self.out / name)

    # 033-B1..B3 · the plan

    def test_shows_the_summary_cell_on_a_plan_rows_face__and_the_description_when_there_is_no_summary_column(self):
        """033-B1 — a plan row's face shows the Summary cell, not the Description; with no Summary column it shows the Description — the plan's longest cell is the page (DESIGN-U33 §4.10 row 1, §5 item 4)."""
        self.given_plan(SUMMARY_HEADER, SUMMARY_ROW)
        self.given_plan(OLD_HEADER, OLD_ROW, name="other")

        self.when_written()

        self.assertEqual(self.page().texts("desc", outside_cards=True), [SUMMARY])
        self.assertEqual(self.page("other.html").texts("desc", outside_cards=True), [DESCRIPTION])

    def test_opens_the_description_and_the_status_cell_from_the_row__never_the_summary_twice(self):
        """033-B2 — a plan row's disclosure holds the Description when it differs from the Summary, and the Status cell always — the Status cell is a tooltip no touch screen opens, and the Description is lost (§4.10 row 2, §5 items 4 and 6)."""
        self.given_plan(SUMMARY_HEADER, SUMMARY_ROW)
        self.given_plan(OLD_HEADER, OLD_ROW, name="other")

        self.when_written()

        self.assertEqual(self.page().texts("unit-body"), [f"{DESCRIPTION} Status column · in progress"])
        self.assertEqual(self.page("other.html").texts("unit-body"), ["Status column · in progress"])
        self.assertIs(self.page().is_open("u-U1"), False)

    def test_draws_a_complete_unit_as_one_line__its_summary_behind_the_row(self):
        """033-B3 — a complete unit's row has no Summary line on its face; the Summary is in its disclosure — finished history fills the plan (§4.10 row 3, §5 item 5)."""
        self.given_plan(SUMMARY_HEADER, SUMMARY_ROW.replace("| in progress |", "| Done |"))

        self.when_written()

        self.assertEqual(self.page().texts("desc", outside_cards=True), [])
        self.assertEqual(self.page().texts("lede"), [SUMMARY])

    def test_reads_a_cell_holding_an_escaped_pipe_as_one_cell__as_github_renders_it(self):
        """033-P1 — a Summary cell holding `\\|` is one cell reading `|`, so the row has its header's cell count and its size — the plan shows "row has 10 cells" for a row GitHub renders whole (U33 bound 4; GFM spec, Tables, "include a pipe in a cell's content by escaping it")."""
        self.given_plan(SUMMARY_HEADER, SUMMARY_ROW.replace(SUMMARY, PIPE_SUMMARY))

        self.when_written()
        summary = self.run_dash("sample")

        self.assertEqual(self.page().texts("row-error"), [])
        self.assertEqual(self.page().texts("desc", outside_cards=True), ["Totals a | b per unit"])
        self.assertEqual(self.page().texts("size", outside_cards=True), ["M"])
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertEqual(unit_and_next_line(summary.stdout, "U1").splitlines()[1].strip(), "Totals a | b per unit")

    # 033-B4..B6 · a session card's face and its Details

    def test_carries_no_left_dot_and_no_raw_phase_or_lead_stage_on_a_cards_face__and_a_stop_keeps_its_code(self):
        """033-B4 — a card's face has no dot left of the slug; its state is the word alone, never `end-of-stack` or the Lead's `intake`; a stopped card's state keeps the code — internal vocabulary on every card, and two markers per row (§4.10 row 4, §5 item 7)."""
        self.given_project()
        self.given_session(phase="end-of-stack")
        self.given_session(slug=SECOND, phase="stopped", stop_reason={"code": STOP_CODE, "detail": STOP_DETAIL})
        third = "sample-003-third"
        self.given_session(slug=third, phase="done", worktree=str(self.given_worktree_not_in_main()),
                           units=[{"id": "U1", "status": "done"}])

        self.when_written()

        page_text = (self.out / "sample.html").read_text()
        states = {slug: self.page().texts("st", card=slug) for slug in (SLUG, SECOND, third)}
        self.assertEqual(states, {SLUG: ["Working"], SECOND: [f"Stopped · {STOP_CODE}"], third: ["With the Lead"]})
        for slug in (SLUG, SECOND, third):
            with self.subTest(slug=slug):
                outside_state = re.sub(r'<span class="st[^"]*">.*?</span>', "", card_summary(page_text, slug), flags=re.S)
                self.assertNotIn('class="dot', outside_state)
                self.assertEqual(len(classed(card_summary(page_text, slug), "dot")), 1)

    def test_drops_the_code_heading_from_the_stop_callout__and_keeps_the_stop_file_and_owner_call_headings(self):
        """033-B5 — a stopped card's callout is the stop's detail alone; the STOP-file and rebrief-call callouts keep their headings — the same code twice, 60 px apart (§4.10 row 5, §5 item 8)."""
        self.given_project()
        self.given_session(phase="stopped", stop_reason={"code": STOP_CODE, "detail": STOP_DETAIL})
        (self.given_session(slug=SECOND) / "STOP").write_text("")
        third = "sample-003-third"
        self.given_session(slug=third, phase="implement", rotate={"reason": "rebrief", "requested_at": iso(datetime.now(timezone.utc))},
                           rebriefs=[{"verdict": "owner", "why": "the plan needs a call."}])

        self.when_written()

        self.assertEqual(self.page().texts("callout", card=SLUG), [STOP_DETAIL])
        self.assertEqual(self.page().texts("callout", card=SECOND), ["Owner STOP file present The session halts at its next check."])
        self.assertTrue(self.page().texts("callout", card=third)[0].startswith("Rebrief needs your call"),
                        self.page().texts("callout", card=third))

    def test_keeps_repo_shape_quiet_spend_ledger_events_handoff_and_path_inside_details__and_nowhere_else_on_the_card(self):
        """033-B6 — repo, shape, longest quiet, spend, ledger, events, handoff and the path sit inside the card's Details and only there — diagnostics on the face of every card (§4.10 row 6, §5 items 9-12)."""
        accounting = self.base / "accounting"
        accounting.mkdir()
        (accounting / "records.jsonl").write_text(json.dumps(ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800)) + "\n")
        self.given_project()
        run_dir = self.given_session(repo="sample-repo", shape="stack")
        (run_dir / "LEDGER.md").write_text("# Ledger\n\n## 2026-10-15 — U1 closed\n")
        (run_dir / "HANDOFF.md").write_text("# Handoff\n\n## FIRST ACTION\nRun the sample suite.\n")
        self.given_events(run_dir, {"event": "unit-start", "unit": "U2", "from": "todo", "to": "building",
                                    "at": iso(datetime.now(timezone.utc) - timedelta(minutes=QUIET_MINUTES))})

        result = self.run_dash("--once", str(self.out), env_accounting=accounting)

        self.assertEqual(result.returncode, 0, result.stderr)
        card, details = self.page().card(SLUG), self.page().texts("more", card=SLUG)
        self.assertEqual(len(details), 1, details)
        facts = ("sample-repo", "stack", "longest quiet", "requests", "2026-10-15 — U1 closed", "Recent events",
                 "Run the sample suite.", str(run_dir))
        for fact in facts:
            with self.subTest(fact=fact):
                self.assertIn(fact, details[0])
                self.assertEqual(card.count(fact), details[0].count(fact))
        self.assertIs(self.page().is_open(f"mo-s-{SLUG}"), False)

    # 033-B7, B9 · the crew card on the project page; an In flight row

    def test_heads_the_project_page_with_a_crew_card_of_its_own_on_site_sessions__no_project_line__or_the_quiet_card(self):
        """033-B7 — the project page carries a crew card of only its own on-site sessions, linking their cards, with no project caption line; the quiet card when none is on site — the page's own sessions have no figure overview (§4.10 row 7, §5 item 14)."""
        self.given_project()
        self.given_session()
        self.given_session(slug=SECOND, phase="stopped", stop_reason={"code": STOP_CODE, "detail": STOP_DETAIL})
        self.given_project(name="other", unit="alpha")
        self.given_session(slug="other-001-alpha")
        self.given_project(name="still", unit="calm")

        self.when_written()

        page_text = (self.out / "sample.html").read_text()
        site = re.search(r'<section class="site".*?</section>', page_text, re.S)
        self.assertIsNotNone(site, "sample.html has no crew card")
        self.assertEqual(self.page().texts("who"), ["002-second", "001-first"])
        self.assertEqual([attrs.get("href") for tag, attrs in Tags(site.group(0)).tags if tag == "a"],
                         [f"#s-{SECOND}", f"#s-{SLUG}"])
        self.assertEqual(self.page().texts("where"), [])
        self.assertIn("Quiet site. Nothing is running.", self.page("still.html").text())

    def test_carries_no_legend_and_no_latest_event_line_on_an_in_flight_row__the_now_lines_title_holds_the_event(self):
        """033-B9 — an In flight row has no run legend and no line of its own for the latest event; its now line's title holds it — seven lines a row, two of them restating the others (§4.10 row 9, §5 items 15-16)."""
        self.given_project()
        run_dir = self.given_session(units=[{"id": "U1", "status": "done"}, {"id": "U2", "status": "building"}])
        self.given_events(run_dir, {"event": "unit-start", "unit": "U2", "from": "todo", "to": "building",
                                    "at": iso(datetime.now(timezone.utc) - timedelta(minutes=QUIET_MINUTES))})

        self.when_written()

        _, inner = self.row(session_href(SLUG))
        self.assertEqual(classed(inner, "run-key"), [])
        self.assertNotIn("U2 started", re.sub(r"<[^>]*>", " ", inner))
        now = re.search(r'<div class="now"><span title="([^"]*)">', inner)
        self.assertIsNotNone(now, inner[-400:])
        self.assertTrue(html.unescape(now.group(1)).startswith("U2 started · "), now.group(1))

    # 033-B10 · colour roles

    def test_sets_no_text_in_the_faint_ink__only_the_stamps_drawing(self):
        """033-B10 — no rule but the footer stamp's (an SVG drawn in currentColor, held to 3:1 by 032-F1.2) gives `color: var(--faint)` — path, size and event times at 3.2:1 (§4.4, §4.10 row 10)."""
        self.given_project()
        self.given_session()

        self.when_written()

        faint = {sel for selectors, body in css_rules(self.index) if declared(body, "color") == "var(--faint)" for sel in selectors}
        self.assertEqual(faint, {".stamp"})

    def test_reads_the_stopped_word_on_the_index_attention_paper_at_four_and_a_half_to_one__at_rest_and_on_hover(self):
        """033-B11 — the colour reaching a `.st.attn` word inside `#attention`, through the paper's own token map, is at least 4.5:1 on the paper's background and on a hovered row's, in every theme — `note-attn` on `note-hover` is 4.33:1 in Whiteprint (§4.9, "every text pair B uses passes AA"; WCAG 1.4.3 holds in every state)."""
        self.given_project()
        self.given_session(phase="stopped", stop_reason={"code": "verification-failed", "detail": "x"})

        self.when_written()

        paper = rule_named(self.index, "#attention .list")
        ink = token_of(attention_word_ink(self.index))
        rest, hover = token_of(paper.get("background")), token_of(rule_named(self.index, "a.row:hover").get("background"))
        self.assertTrue(ink and rest and hover, "the word or the paper is not drawn in theme tokens")
        for name, tokens in FooterContrast.themes(self).items():
            on_paper = lambda token: tokens[token_of(paper.get(f"--{token}")) or token]
            for state, ground in (("rest", rest), ("hover", hover)):
                with self.subTest(theme=name, state=state):
                    self.assertGreaterEqual(contrast(channels(on_paper(ink)), channels(on_paper(ground))), TEXT_CONTRAST)

    # 033-B12..B20 · after review 1

    def test_keeps_the_awaiting_acceptance_rows_state_word_short__its_units_on_a_clamped_line_with_all_of_them_in_the_title(self):
        """033-B12 — an Awaiting acceptance row's state word is the built count; the units it lists are one clamped line whose `title` holds every one — four long unit names in the nowrap state word squeeze the row's name to nothing and run off its edge (review 1 F1)."""
        names = [f"{word}-{LONG_UNIT_TAIL}" for word in ("alpha", "bravo", "charlie", "delta")]
        self.given_plan(OLD_HEADER, *(f"| U{n} | `{name}` | ENG-{n} | {DESCRIPTION} | docs/u{n}.md | S | low | in progress |"
                                      for n, name in enumerate(names, 1)))
        for n, name in enumerate(names, 1):
            worktree = self.base / "worktrees" / f"u{n}"
            worktree.mkdir(parents=True)
            self.given_session(slug=f"sample-00{n}-{name}", phase="done", intake=True, units=[{"id": "U1", "status": "done"}],
                               worktree=str(worktree))

        self.when_written()

        row = index_row(self.index, "sample.html#plan")
        listed = ", ".join(f"U{n} {name}" for n, name in enumerate(names, 1))
        self.assertEqual(spans_of(row, "st"), ["4 built"])
        self.assertEqual(clamped_lines(row), [(listed, listed)])

    def test_keeps_a_stopped_rows_state_word_to_its_code__an_idle_rebrief_planner_on_its_clamped_line(self):
        """033-B13 — a stopped row with an idle rebrief Planner reads `Stopped · <code>` in its state word and the Planner on the clamped line before the detail; the state word may shrink — sixty characters of nowrap state push the name off a phone (review 1 F1)."""
        self.given_project()
        self.given_stopped()
        self.given_live_agent(f"planner-{SLUG}", "idle", cwd=self.cwd)

        self.when_written()

        row = index_row(self.index, session_href(SLUG))
        why = "Rebrief Planner idle without a verdict · the sample's suite is red"
        self.assertEqual(spans_of(row, "st"), ["Stopped · verification-failed"])
        self.assertEqual(clamped_lines(row), [(why, why)])
        self.assertEqual(rule_named(self.index, ".srow .head .st").get("min-width"), "0")

    def test_repeats_a_summary_the_narrowest_face_clips_inside_the_row__and_gives_the_face_its_title(self):
        """033-B14 — a Summary longer than the face holds at its narrowest one-line width (45 characters) is repeated first in the row's disclosure, and the face's line carries it as its `title` — a 61–90 character Summary is clipped with nothing to read it by (§4.5, "the Summary in full, when the face clipped"; review 1 F3). Q5"""
        summary = "Totals what each session spent, per unit and per role, from the ledger."
        self.given_plan(SUMMARY_HEADER, SUMMARY_ROW.replace(SUMMARY, summary))

        self.when_written()

        page_text = (self.out / "sample.html").read_text()
        self.assertEqual(self.page().texts("unit-body"), [f"{summary} {DESCRIPTION} Status column · in progress"])
        self.assertEqual(re.findall(r'<div class="desc clamp1" title="([^"]*)">', page_text), [html.escape(summary)])

    def test_hides_the_time_on_a_card_at_560_px_or_less__and_on_no_index_row(self):
        """033-B17 — the 560 px block hides `.ago` on a card's summary and nowhere else, so an index row keeps its time (Lead decision 3; §5 item 13, "hidden at ≤ 560 px; still on the index rows' head")."""
        self.given_project()
        self.given_session()

        self.when_written()

        hidden = {sel for selectors, body in media_rules(self.index, "(max-width:560px)")
                  if css_declarations(body).get("display") == "none" for sel in selectors if compounds(sel)[-1] == ".ago"}
        self.assertEqual(hidden, {".sess>summary>.ago"})

    def test_heads_the_project_with_how_much_is_built_and_the_time_left__each_saying_what_it_is_weighted_by_in_its_title(self):
        """033-B18 — the hero's facts line reads `60% built` (U1, M, built of U1 M + U2 S) titled `weighted by unit size`, and `about 1h left` (U2's 2 points at U1's 1.9 h per 3 points) titled `of session time, at the pace so far` (§5 item 1)."""
        self.given_plan(OLD_HEADER, OLD_ROW, SECOND_OLD_ROW)
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

        self.when_written()

        facts = re.search(r'<p class="facts">(.*?)</p>', (self.out / "sample.html").read_text(), re.S).group(1)
        self.assertEqual(re.findall(r'<span title="([^"]*)">([^<]*)</span>', facts)[:2],
                         [("weighted by unit size", "60% built"), ("of session time, at the pace so far", "about 1h left")])

    def test_says_ready_to_launch_and_how_many_units_on_a_briefed_card__with_no_wall_meter(self):
        """033-B19 — a briefed card's now line reads `Ready to launch · 2 units` and draws no wall meter, though its brief sets a wall (§5 item 20, "the now line 'Ready to launch · 1 unit'"; "removed duplicate")."""
        self.given_project()
        self.given_session(phase="briefed", max_wall_hours=6)

        self.when_written()

        self.assertEqual(self.page().texts("now", card=SLUG), ["Ready to launch · 2 units"])
        self.assertNotIn('class="meter', card_html((self.out / "sample.html").read_text(), SLUG))

    def test_says_which_unit_a_stopped_card_stopped_in__on_its_now_line(self):
        """033-B20 — a stopped card's now line begins `Stopped in U2 of 2`, the unit not yet done (§4.5, the now line's position for a stopped card)."""
        self.given_project()
        self.given_stopped()

        self.when_written()

        self.assertRegex(self.page().texts("now", card=SLUG)[0], r"^Stopped in U2 of 2\b")

    def test_names_a_rebriefs_planner_once_on_its_card__in_the_callout__and_on_the_index_rows_now_line(self):
        """033-B21 — a rebriefing card names its Planner (`claude attach …`) once, in its calm callout; the index row, which has no callout, names it on its now line (§5 item 20's rule, "the same fact" once; review 1 F5)."""
        self.given_project()
        self.given_stopped()
        self.given_live_agent(f"planner-{SLUG}", "busy", cwd=self.cwd)

        self.when_written()

        card = card_html((self.out / "sample.html").read_text(), SLUG)
        self.assertEqual(card.count("claude attach"), 1)
        self.assertEqual(re.findall(r'<div class="callout calm">.*?</div>', card, re.S)[0].count("claude attach"), 1)
        self.assertIn("claude attach", re.search(r'<div class="now">.*?</div>', index_row(self.index, session_href(SLUG)), re.S).group(0))
    # 033-B22..B35 · after review 2

    def test_counts_a_stages_complete_units_as_some_of_all__and_as_all_when_every_one_has(self):
        """033-B22 — a stage with two of three units complete reads `2 of 3 complete`; one with both complete reads `2 complete` (§4.5 `render_plan`, a right-aligned count, "N complete" or "N of M complete"; review 2 S2a)."""
        done_row = lambda n, name: f"| U{n} | `{name}` | ENG-{n} | {DESCRIPTION} | docs/u{n}.md | S | low | Done |"
        self.given_plan(OLD_HEADER, done_row(1, "first"), done_row(2, "second"), OLD_ROW.replace("U1 | `first`", "U3 | `third`"))
        self.given_plan(OLD_HEADER, done_row(1, "first"), done_row(2, "second"), name="other")

        self.when_written()

        self.assertEqual(self.page().texts("count"), ["2 of 3 complete"])
        self.assertEqual(self.page("other.html").texts("count"), ["2 complete"])

    # 043-D1..D4 · the Owner's act is accept

    def test_counts_a_plan_row_whose_status_begins_accepted_as_complete(self):
        """043-D1 — Status cells `**Accepted 2026-10-15 as `0abc123`**` and `accepted` count as complete, so the stage reads `2 complete` — the Lead writes the Owner's accept into the row, and accepted work would read as not started."""
        row = lambda n, name, status: f"| U{n} | `{name}` | ENG-{n} | {DESCRIPTION} | docs/u{n}.md | S | low | {status} |"
        self.given_plan(OLD_HEADER, row(1, "first", "**Accepted 2026-10-15 as `0abc123`**"), row(2, "second", "accepted"))

        self.when_written()

        self.assertEqual(self.page().texts("count"), ["2 complete"])

    def test_counts_a_plan_row_whose_status_begins_landed_as_not_complete(self):
        """043-D4 — beside an `Accepted` row, a Status cell `**Landed 2026-10-15 as `0abc123`**` does not count, so the stage reads `1 of 2 complete` — the old prefix read as a fallback hides a PROJECT.md the migration missed."""
        row = lambda n, name, status: f"| U{n} | `{name}` | ENG-{n} | {DESCRIPTION} | docs/u{n}.md | S | low | {status} |"
        self.given_plan(OLD_HEADER, row(1, "first", "**Accepted 2026-10-15 as `0abc123`**"), row(2, "second", "**Landed 2026-10-15 as `0abc124`**"))

        self.when_written()

        self.assertEqual(self.page().texts("count"), ["1 of 2 complete"])

    def test_says_accepted_for_a_sessions_latest_accept_event(self):
        """043-D2 — a done session whose newest event is `accept` reads `Latest · Accepted` in its Details — the event name shows raw, the one move on the card not in plain words."""
        self.given_project()
        run_dir = self.given_finished_session(accepted={"sha": "0" * 40, "at": "2026-10-15T10:00:00+00:00"})
        self.given_events(run_dir, {"event": "accept", "head": "0" * 40, "from": "done", "to": "done",
                                    "at": iso(datetime.now(timezone.utc) - timedelta(minutes=QUIET_MINUTES))})

        self.when_written()

        latest = [text for text in self.page().texts("note", card=SLUG) if text.startswith("Latest · ")]
        self.assertEqual(len(latest), 1, latest)
        self.assertTrue(latest[0].startswith("Latest · Accepted · "), latest)

    # 037-S1..S2 · a plan's stages

    def given_todo(self, folder, todo):
        (folder / "PROJECT.md").write_text((folder / "PROJECT.md").read_text() + "\n## Detailed TODO\n\n" + todo)

    def test_groups_the_units_under_a_stage_heading__as_one_stage_with_its_label_and_theme(self):
        """037-S1 — `### Stage 1 — Foundation` groups U2 then U1 as one plan stage labelled `Stage 1`, its theme `Foundation` (PROJECT-TEMPLATE.md's Detailed TODO; the Owner's rename of 2026-10-15)."""
        self.given_todo(self.given_plan(OLD_HEADER, OLD_ROW, SECOND_OLD_ROW),
                        "### Stage 1 — Foundation\n\n1. **U2** — second\n2. **U1** — first\n")

        self.when_written()

        self.assertEqual(plan_stages((self.out / "sample.html").read_text()), [("Stage 1", "Foundation", ["U2", "U1"])])

    def test_still_groups_the_units_under_a_wave_heading__as_one_stage(self):
        """037-S2 — a plan written before the rename, `### Wave 1 — Foundation`, still groups U2 then U1 as one stage labelled `Wave 1` — an old plan loses its sequence (the brief's bound 1)."""
        self.given_todo(self.given_plan(OLD_HEADER, OLD_ROW, SECOND_OLD_ROW),
                        "### Wave 1 — Foundation\n\n1. **U2** — second\n2. **U1** — first\n")

        self.when_written()

        self.assertEqual(plan_stages((self.out / "sample.html").read_text()), [("Wave 1", "Foundation", ["U2", "U1"])])

    def test_draws_the_run_track_on_a_working_card__and_none_on_a_briefed_or_done_card(self):
        """033-B23 — a working card with brief units draws its bare run track; a briefed card and a done card draw none (§4.5 `render_session` step 3, "the bare run track, not for briefed or terminal sessions"; review 2 S2b)."""
        self.given_project()
        self.given_session()
        self.given_session(slug=SECOND, phase="briefed")
        third = "sample-003-third"
        self.given_session(slug=third, phase="done", intake=True)

        self.when_written()

        page_text = (self.out / "sample.html").read_text()
        tracks = {slug: card_html(page_text, slug).count('<div class="track">') for slug in (SLUG, SECOND, third)}
        self.assertEqual(tracks, {SLUG: 1, SECOND: 0, third: 0})

    def test_keeps_the_latest_move_in_details_when_the_card_has_events__and_no_latest_line_when_it_has_none(self):
        """033-B24 — a card with an event holds `Latest · <the move>` inside its Details and nowhere else on the card; a card with no event has no `Latest ·` line, its ledger line saying the same (§4.5 `details`, "(only when there are events)"; §5 items 11, 16; review 2 S2c, S2f)."""
        self.given_project()
        run_dir = self.given_session(units=[{"id": "U1", "status": "done"}, {"id": "U2", "status": "building"}])
        self.given_events(run_dir, {"event": "unit-start", "unit": "U2", "from": "todo", "to": "building",
                                    "at": iso(datetime.now(timezone.utc) - timedelta(minutes=QUIET_MINUTES))})
        (self.given_session(slug=SECOND) / "LEDGER.md").write_text("# Ledger\n\n## 2026-10-15 — U1 closed\n")

        self.when_written()

        latest = [text for text in self.page().texts("note", card=SLUG) if text.startswith("Latest · ")]
        self.assertEqual(len(latest), 1, latest)
        self.assertTrue(latest[0].startswith("Latest · U2 started"), latest)
        self.assertEqual(self.page().card(SLUG).count("Latest · "), self.page().texts("more", card=SLUG)[0].count("Latest · "))
        self.assertNotIn("Latest · ", self.page().card(SECOND))

    def test_ends_an_index_attention_row_with_how_long_ago_its_session_wrote(self):
        """033-B25 — an index attention row's head ends with the session's age, `5m ago` (§4.5 `render_attention`; §5 item 13, "still on the index rows' head"; review 2 S2d)."""
        self.given_project()
        self.given_stopped()

        self.when_written()

        self.assertEqual(spans_of(index_row(self.index, session_href(SLUG)), "ago"), [f"{QUIET_MINUTES}m ago"])

    def test_carries_the_wall_meter_on_a_working_cards_now_line__and_on_its_in_flight_row(self):
        """033-B26 — a working session whose brief sets 6 wall hours, started 2 h ago, reads `2.0 of 6h` beside a meter on its card's now line and on its index In flight row (§4.5 `now_line`; §5 item 9, "now line 'U3 of 4 · building · active 3m ago · ▬ 2.0 of 6h'"; review 2 S2e)."""
        self.given_project()
        self.given_session(max_wall_hours=6)

        self.when_written()

        card_now = re.search(r'<div class="now">.*?</div>', card_html((self.out / "sample.html").read_text(), SLUG), re.S).group(0)
        row_now = re.search(r'<div class="now">.*?</div>', index_row(self.index, session_href(SLUG)), re.S).group(0)
        for where, now in (("card", card_now), ("in flight", row_now)):
            with self.subTest(where=where):
                self.assertIn('<span class="meter">', now)
                self.assertIn("2.0 of 6h", re.sub(r"<[^>]*>", "", now))

    def test_places_the_project_pages_crew_card_right_after_its_header__before_any_section(self):
        """033-B27 — the project page's crew card follows the header and comes before the first section heading (§4.5 `render_project_page`, "`project_crew` comes after the hero"; review 2 S2g)."""
        self.given_project()
        self.given_session()

        self.when_written()

        page_text = (self.out / "sample.html").read_text()
        hero_end = page_text.index("</section>", page_text.index('<section class="hero"'))
        crew = page_text.index('<section class="site"')
        self.assertLess(hero_end, crew)
        self.assertLess(crew, page_text.index("<h2", hero_end))

    def test_draws_one_track_segment_per_brief_unit_on_an_in_flight_row(self):
        """033-B28 — an In flight row draws its session's run track, one segment per unit in the brief: two (§4.5 `flight_row_B`, "the purpose, the bare track and `now_line`"; review 2 S2h)."""
        self.given_project()
        self.given_session()

        self.when_written()

        track = re.search(r'<div class="track">(.*?)</div>', index_row(self.index, session_href(SLUG)), re.S)
        self.assertIsNotNone(track)
        self.assertEqual(len(re.findall(r'<i class="seg ', track.group(1))), 2)

    def test_says_handing_off_alone_for_a_rotating_session_with_no_brief_units(self):
        """033-B29 — a rotating session with no brief units reads `Handing off` on its now line, then its activity: no empty phrase between two separators (review 2 N1)."""
        self.given_project()
        self.given_session(units=[], rotate={"reason": "context", "requested_at": iso(datetime.now(timezone.utc))})

        self.when_written()

        self.assertEqual(self.page().texts("now", card=SLUG), [f"Handing off · active {QUIET_MINUTES}m ago"])

    def test_says_where_a_parked_or_owner_call_session_stopped__on_its_now_line(self):
        """033-B30 — a parked card's now line reads `Parked in U2 of 2`; a card whose rebrief waits on the Owner reads `Stopped in U2 of 2` — each is halted mid-brief, and where it halted is what the Owner resumes from. Q7"""
        self.given_project()
        self.given_session(parked=True)
        self.given_session(slug=SECOND, rotate={"reason": "rebrief", "requested_at": iso(datetime.now(timezone.utc))},
                           rebriefs=[{"verdict": "owner", "why": "the plan needs a call."}])

        self.when_written()

        self.assertRegex(self.page().texts("now", card=SLUG)[0], r"^Parked in U2 of 2\b")
        self.assertRegex(self.page().texts("now", card=SECOND)[0], r"^Stopped in U2 of 2\b")

    def test_links_the_project_pages_crew_ghost_to_its_working_list(self):
        """033-B31 — with eight sessions working, the project page's crew ghosts link `#working`, a heading the page has; the index's link `#flight` (review 2 N3; 031's ghost rule, read on the project page)."""
        self.given_project()
        for n in range(1, 9):
            self.given_session(slug=f"sample-00{n}-worker")

        self.when_written()

        page_text = (self.out / "sample.html").read_text()
        ghosts = re.findall(r'<li class="more c\d"><a class="member" href="([^"]*)"', page_text)
        self.assertTrue(ghosts)
        self.assertEqual(set(ghosts), {"#working"})
        self.assertIn('<h2 id="working">', page_text)
        self.assertEqual(set(re.findall(r'<li class="more c\d"><a class="member" href="([^"]*)"', self.index)), {"#flight"})

    def test_clamps_a_rebriefing_rows_stop_to_two_lines__the_whole_of_it_in_the_title(self):
        """033-B32 — an index In flight row for a rebriefing session carries `Stopped on <code>: <detail>` on one clamped line with the whole text in its `title` (review 2 N3)."""
        self.given_project()
        self.given_stopped()
        self.given_live_agent(f"planner-{SLUG}", "busy", cwd=self.cwd)

        self.when_written()

        reason = "Stopped on verification-failed: the sample's suite is red"
        self.assertEqual(clamped_lines(index_row(self.index, session_href(SLUG))), [(reason, reason)])

    def test_keeps_a_pending_rows_where_in_its_now_lines_title(self):
        """033-B33 — a brief being written shows on the index with `Planner writing the brief` as its now line's first `title` (review 2 N3)."""
        self.given_project()
        self.given_briefing()

        self.when_written()

        now = re.search(r'<div class="now"><span title="([^"]*)">', index_row(self.index, session_href(SLUG)))
        self.assertIsNotNone(now)
        self.assertEqual(html.unescape(now.group(1)), "Planner writing the brief")

    def test_keeps_an_escaped_pipe_at_the_end_of_a_row_with_no_closing_pipe__in_its_last_cell(self):
        """033-B34 — a row with no closing pipe whose last cell ends `\\|` keeps that pipe: the Status column reads `in progress |` (GFM: an escaped pipe is cell text; review 2 N3)."""
        self.given_plan(SUMMARY_HEADER, SUMMARY_ROW.removesuffix(" |").removesuffix("in progress") + "in progress \\|")

        self.when_written()

        self.assertEqual(self.page().texts("status"), ["Status column · in progress |"])

    def test_labels_the_ledgers_latest_heading_ledger_inside_details(self):
        """033-B35 — a card with a LEDGER.md holds `Ledger · <its last heading>` in its Details (§5 item 11, "then 'Ledger · …'"; review 2 N4)."""
        self.given_project()
        (self.given_session() / "LEDGER.md").write_text("# Ledger\n\n## 2026-10-15 — U1 closed\n")

        self.when_written()

        self.assertIn("Ledger · 2026-10-15 — U1 closed", self.page().texts("note", card=SLUG))
    # 033-B36..B43 · after review 3

    def test_keeps_the_rebrief_count_and_the_folders_files_on_the_facts_line_inside_details(self):
        """033-B36 — a card with two rebriefs and a `reviews/U1-gate.md` reads `2 rebriefs` and `U1-gate.md` on the facts line in its Details, and nowhere else on the card (§4.5 `facts_line`, "repo · shape · longest quiet · rebriefs · dir · files"; §5 item 9; review 3 S1a, S1b)."""
        self.given_project()
        run_dir = self.given_session(rebriefs=[{"verdict": "confident", "why": "a"}, {"verdict": "confident", "why": "b"}])
        (run_dir / "reviews").mkdir()
        (run_dir / "reviews" / "U1-gate.md").write_text("# Gate\n")

        self.when_written()

        path = self.page().texts("path", card=SLUG)
        self.assertEqual(len(path), 1, path)
        for fact in ("2 rebriefs", "U1-gate.md"):
            with self.subTest(fact=fact):
                self.assertIn(fact, path[0])
                self.assertEqual(self.page().card(SLUG).count(fact), 1)
                self.assertIn(fact, self.page().texts("more", card=SLUG)[0])

    def test_draws_no_tally_on_a_live_project_card_on_the_index(self):
        """033-B37 — a live project's card on the index has its bar and no tally legend, no `key seg` mark (§4.5 `render_index`, "delete `{tally(p["units"])}`"; §5 item 18; review 3 S1c)."""
        self.given_project()
        self.given_session()

        self.when_written()

        card = re.search(r'<a class="proj" href="sample\.html">.*?</a>', self.index, re.S).group(0)
        self.assertIn('<div class="track', card)
        self.assertNotIn('class="key seg', card)

    def test_shows_the_spend_under_the_header_of_a_project_with_no_task_breakdown(self):
        """033-B38 — a project whose PROJECT.md has no Task Breakdown still reads its spend on the facts line under its header (§5 item 2, spend on the facts line; review 3 S1d)."""
        accounting = self.base / "accounting"
        accounting.mkdir()
        (accounting / "records.jsonl").write_text(json.dumps(ledger_record(SLUG, "worker", "w-1", 12, 3_400, 1.25, 1_800)) + "\n")
        folder = self.projects / "sample"
        folder.mkdir(parents=True)
        (folder / "PROJECT.md").write_text("# Sample\n\nNo plan table yet.\n")
        self.given_session()

        result = self.run_dash("--once", str(self.out), env_accounting=accounting)

        self.assertEqual(result.returncode, 0, result.stderr)
        facts = re.findall(r'<p class="facts">(.*?)</p>', (self.out / "sample.html").read_text(), re.S)
        self.assertEqual(len(facts), 1, facts)
        self.assertIn("12 requests", re.sub(r"<[^>]*>", "", facts[0]))

    def test_keeps_the_folder_path_on_an_unreadable_card(self):
        """033-B39 — an Unreadable card's body is the error and then its session folder's path, by which the Owner finds the broken run.json (§4.5, "The error card is unchanged"; review 3 S1e)."""
        self.given_project()
        run_dir = self.given_session()
        (run_dir / "run.json").write_text("{")

        self.when_written()

        self.assertEqual(self.page().texts("path", card=SLUG), [str(run_dir)])

    def test_draws_no_run_track_on_a_parked_card(self):
        """033-B40 — a parked card draws no run track (§4.5 `render_session` step 3, "not for briefed or terminal sessions"; parked is terminal; review 3 S1f)."""
        self.given_project()
        self.given_session(parked=True)

        self.when_written()

        self.assertNotIn('<div class="track">', card_html((self.out / "sample.html").read_text(), SLUG))

    def test_says_ready_to_launch_and_one_unit__in_the_singular(self):
        """033-B41 — a briefed card with one unit reads `Ready to launch · 1 unit` (§5 item 20, quoted; review 3 N1)."""
        self.given_project()
        self.given_session(phase="briefed", units=[{"id": "U1", "status": "todo"}])

        self.when_written()

        self.assertEqual(self.page().texts("now", card=SLUG), ["Ready to launch · 1 unit"])

    def test_keeps_the_code_heading_on_a_rebriefing_cards_stop_callout(self):
        """033-B42 — a rebriefing card's calm stop callout is headed by the stop's code, which its state word does not carry (Q2, the half B5 does not pin; review 3 N2)."""
        self.given_project()
        self.given_stopped()
        self.given_live_agent(f"planner-{SLUG}", "busy", cwd=self.cwd)

        self.when_written()

        card = card_html((self.out / "sample.html").read_text(), SLUG)
        self.assertIn('<div class="callout calm"><b>verification-failed</b>the sample&#x27;s suite is red</div>', card)

    def test_links_the_project_pages_crew_ghost_to_its_attention_heading__when_nobody_on_site_is_running(self):
        """033-B43 — with eight sessions stopped, the project page's crew ghosts link `#attention`, and the page's Needs attention heading carries that id (review 3 N5)."""
        self.given_project()
        for n in range(1, 9):
            self.given_stopped(slug=f"sample-00{n}-worker")

        self.when_written()

        page_text = (self.out / "sample.html").read_text()
        self.assertEqual(set(re.findall(r'<li class="more c\d"><a class="member" href="([^"]*)"', page_text)), {"#attention"})
        self.assertIn('<h2 class="attn-head" id="attention">', page_text)

class TerminalText(DashScratch):
    """launch.json naming both roots; one project and one session whose text holds control bytes."""

    def test_prints_no_control_byte_from_session_text__in_the_terminal_summary(self):
        """033-T1 — the text summary strips C0, DEL and C1 bytes from a session's phase and stop code and from a plan cell — a session's file writes into the Owner's terminal (U33 bound 5, N-4; `session-inputs.md`, "Fence or strip session text")."""
        self.given_launch_roots()
        folder = self.projects / "sample"
        folder.mkdir(parents=True)
        row = SUMMARY_ROW.replace(SUMMARY, SUMMARY.replace(" ", "\x07 ", 1))
        self.assertNotEqual(row, SUMMARY_ROW, "the BEL never reached the plan cell")
        (folder / "PROJECT.md").write_text(project_md(SUMMARY_HEADER, row))
        self.given_session(phase="imple\x1bment\x7f", stop_reason={"code": "verification\x07-failed\x9b"})

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        for byte in ("\x1b", "\x07", "\x7f", "\x9b"):
            self.assertNotIn(byte, result.stdout)
        self.assertIn(f"{SLUG}  implement  · verification-failed  · ", result.stdout)
        self.assertEqual(unit_and_next_line(result.stdout, "U1").splitlines()[1].strip(), SUMMARY)


# Brackets json.loads cannot decode: past the recursion limit before Python 3.14, and past its C stack guard from 3.14.
DEEP_NESTING = 1_000_000


class FinalTrims(GlyphScratch):
    """launch.json naming both roots; each test writes its plan and sessions and runs `--once` once."""

    def given_plan(self, *rows):
        folder = self.projects / "sample"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "PROJECT.md").write_text(project_md(OLD_HEADER, *rows))
        return folder

    def given_unit_row(self, number, name):
        return f"| U{number} | `{name}` | ENG-{number} | {DESCRIPTION} | docs/{name}.md | S | low | in progress |"

    def given_finished_in_worktree(self, slug, intake=True, **fields):
        worktree = self.base / "worktrees" / slug
        worktree.mkdir(parents=True)
        return self.given_session(slug=slug, phase="done", intake=intake, units=[{"id": "U1", "status": "done"}],
                                  worktree=str(worktree), **fields)

    # 041-C1 · the index card's count line

    def test_counts_each_state_on_the_bar_in_one_line_under_it__in_the_bars_labels__leaving_out_a_state_with_no_unit(self):
        """041-C1 — a live project's card on the index reads, right under its bar, `1 Complete · 1 Awaiting acceptance · 1 With the Lead · 1 Briefed · 2 Not started`: each state's count in the bar's own `aria-label` words, in legend order, and no state with no unit (U33 Open, option one; brief bound 5)."""
        self.given_plan(*(self.given_unit_row(n, name) for n, name in
                          enumerate(("first", "second", "third", "fourth", "fifth", "sixth"), 1)))
        self.given_finished_in_worktree(SLUG)
        self.given_session(slug=SECOND, phase="briefed")
        self.given_finished_in_worktree("sample-003-third", intake=False)
        self.given_finished_in_worktree("sample-004-fourth", accepted={"sha": "0" * 40, "at": "2026-10-15T10:00:00+00:00"})

        self.when_written()

        card = re.search(r'<a class="proj" href="sample\.html">.*?</a>', self.index, re.S).group(0)
        line = re.search(r'<div class="track">(?:<i [^>]*></i>)*</div><div class="tally"><span>([^<]*)</span></div>', card)
        self.assertIsNotNone(line, card)
        self.assertEqual(html.unescape(line.group(1)), "1 Complete · 1 Awaiting acceptance · 1 With the Lead · 1 Briefed · 2 Not started")

    # 041-T1 · no time left once everything is built

    def test_leaves_the_time_left_off_the_facts_line__when_every_unit_is_built(self):
        """041-T1 — a project whose one unit is built reads `100% built` on its facts line and no `about Nh left`: at 100% it read `about 0h left` (brief bound 6). Below 100% the time left stays (033-B18)."""
        self.given_plan(OLD_ROW)
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

        self.when_written()

        facts = re.search(r'<p class="facts">(.*?)</p>', (self.out / "sample.html").read_text(), re.S).group(1)
        self.assertEqual(re.findall(r'<span title="[^"]*">([^<]*)</span>', facts), ["100% built"])

    # 041-G1 · a project robowright.json nested too deeply

    def test_writes_every_page__when_a_projects_robowright_json_is_nested_too_deeply_to_read(self):
        """041-G1 — a project whose robowright.json nests too deeply for json.loads is read as one with no robowright.json, by the dashboard and by `named_repos` (launch.json's `repos` set, so it runs): `--once` exits 0 with no traceback and writes the project's page (brief bound 7; U36 review 2, G2)."""
        self.given_allowlisted(self.base / "repo")
        folder = self.given_project()
        (folder / "robowright.json").write_text(f'{{"deep": {"[" * DEEP_NESTING}{"]" * DEEP_NESTING}}}\n')
        self.given_session()

        self.when_written()

        self.assertTrue((self.out / "sample.html").is_file())

    # 041-S1 · settings come only from robowright.json

    def test_ignores_a_settings_file_under_another_name__beside_robowright_json(self):
        """041-S1 — `local.json` asking for an owner brief beside a robowright.json that asks for none is ignored: SLUG, finished and through intake with no owner brief, reads awaiting acceptance, not held for a brief (brief bound 9; U34's deleted R5.4)."""
        folder = self.given_project()
        self.given_settings(folder, "robowright.json", {})
        self.given_settings(folder, "local.json", {"owner_brief": True})
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

        self.when_written()

        page = Page(self.out / "sample.html")
        states = dict(zip(page.texts("id", outside_cards=True), page.texts("state", outside_cards=True)))
        self.assertTrue(states.get("U1", "").startswith("Awaiting acceptance"), states)

    # 052b-R · a robowright.json the dashboard reads without following a link or waiting on a FIFO

    def test_ignores_a_robowright_json_that_is_a_link__to_a_file_outside_the_project(self):
        """052b-R1 — `sample`'s robowright.json a symlink to a file outside asking for an owner brief is read as `{}`:
        SLUG, finished and through intake with no owner brief, reads awaiting acceptance (U52b B3)."""
        folder = self.given_project()
        outside = self.base / "outside"
        outside.mkdir()
        self.given_settings(outside, "kept.json", {"owner_brief": True})
        (folder / "robowright.json").symlink_to(outside / "kept.json")
        self.given_finished_session(worktree=str(self.given_worktree_not_in_main()))

        self.when_written()

        page = Page(self.out / "sample.html")
        states = dict(zip(page.texts("id", outside_cards=True), page.texts("state", outside_cards=True)))
        self.assertTrue(states.get("U1", "").startswith("Awaiting acceptance"), states)

    def test_writes_every_page_at_once__when_a_projects_robowright_json_is_a_fifo(self):
        """052b-R2 — a FIFO at `sample`'s robowright.json, with launch.json's `repos` set so `named_repos` reads it
        too: `--once` exits 0 within seconds and writes the project's page; a read waited on it for a writer that
        never comes (U52b B3)."""
        self.given_allowlisted(self.base / "repo")
        folder = self.given_project()
        (folder / "robowright.json").unlink(missing_ok=True)
        os.mkfifo(folder / "robowright.json")
        self.given_session()

        result = self.run_dash("--once", str(self.out), timeout=20)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / "sample.html").is_file())


class NeverLaunched(DashScratch):
    """056-D rows: a session folder the Planner briefed and nothing launched reads Briefed, never Working, Stuck? or In
    flight. launch.json naming both roots; project `sample`; SLUG as the Planner leaves it, its files written 45 min
    ago, past STUCK_MINUTES, so a working tone would read Stuck?."""

    def setUp(self):
        super().setUp()
        self.given_launch_roots()
        self.given_project()

    def given_briefed_session(self, **fields):
        """SLUG at preflight with no session id, no start time and no event log, its worktree the scratch cwd."""
        values = {"session_id": "", "started_at": "", "worktree": str(self.cwd),
                  "units": [{"id": "U1", "status": "todo"}, {"id": "U2", "status": "todo"}]}
        run_dir = self.given_session(phase="preflight", **dict(values, **fields))
        written = time.time() - 45 * 60
        for path in run_dir.iterdir():
            os.utime(path, (written, written))
        return run_dir

    def index(self):
        return (self.out / "index.html").read_text()

    def attention_text(self):
        match = re.search(r'<details class="group" id="attention".*?</details>', self.index(), re.S)
        return html.unescape(re.sub(r"<[^>]+>", " ", match.group(0))) if match else ""

    def label(self):
        return Page(self.out / "sample.html").texts("st", card=SLUG)

    def test_lists_the_session_briefed_and_ready_to_launch__when_nothing_ever_launched_it(self):
        """056-D1 — a brief nothing launched waits on the Owner's launch line — it reads as work in progress, and is never launched."""
        self.given_briefed_session()

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Briefed · ready to launch", self.attention_text())

    def test_never_reads_the_session_stuck__when_nothing_ever_launched_it(self):
        """056-D2 — a brief nothing launched is never Stuck? — the Owner hunts for a hung session that never ran."""
        self.given_briefed_session()

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.pages().count("Stuck?"), 0)

    def test_lists_no_in_flight_row__when_nothing_ever_launched_the_session(self):
        """056-D3 — a brief nothing launched is not In flight — the index says work is running when none is."""
        self.given_briefed_session()

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([h for h in flight_hrefs(self.index()) if SLUG in h], [])

    def test_reads_the_session_working__when_a_live_session_runs_its_preflight(self):
        """056-D4 — a live session in preflight reads Working — a running preflight reads as a brief nobody launched."""
        self.given_briefed_session()
        self.given_live_agent("worker-opus-sample-001-first", "busy", cwd=self.cwd)

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.label(), ["Working"])

    def test_reads_the_session_working__when_a_launch_pinned_it_and_died_in_preflight(self):
        """056-D5 — a launch that died in preflight is not Briefed — the Owner launches a second Worker over it (assumed Q1)."""
        self.given_briefed_session(session_id="aaaa1111-2222-3333-4444-555566667777")

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.label(), ["Working"])

    def test_says_parked_before_launch__for_a_session_parked_from_briefed(self):
        """052a-D1 — a brief the Owner parked before launch reads `Parked before launch` and leaves Needs attention — `Parked in U1 of 2` places a session that never started mid-brief."""
        self.given_session(phase="parked", units=[{"id": "U1", "status": "todo"}, {"id": "U2", "status": "todo"}],
                           parked={"by": "owner", "reason": "held until the release ships",
                                   "at": iso(datetime.now(timezone.utc)), "from": "briefed", "released": []})

        result = self.run_dash("--once", str(self.out))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Page(self.out / "sample.html").texts("now", card=SLUG)[0], "Parked before launch")
        self.assertNotIn(SLUG, self.attention_text())


class DirectBuildShown(CrewScratch):
    """057-D rows: a direct build beside SLUG's folder under the sessions root. Project `sample` with U1 `first`."""

    def setUp(self):
        super().setUp()
        self.given_project()

    def given_folder_with_no_run_json(self):
        """SLUG's folder as a brief-only Planner launch leaves it: its ledger and no run.json."""
        (self.sessions / SLUG).mkdir(parents=True)
        (self.sessions / SLUG / "LEDGER.md").write_text("# Ledger\n")

    def rows(self, slug=SLUG):
        """How many of the index's `a.row` link `slug`'s card."""
        href = re.escape(session_href(slug))
        return len(re.findall(rf'<a\b(?=[^>]*\bclass="row\b)[^>]*\bhref="{href}"', self.index))

    def test_shows_the_running_direct_build__when_its_unit_has_a_folder_with_no_run_json(self):
        """057-D1 — a running direct build beside a folder with no run.json draws a Worker and says `direct build` — the folder a brief-only Planner left hides the build."""
        self.given_folder_with_no_run_json()
        self.given_running_direct_build()

        self.when_written()

        self.assert_figure(SLUG, "worker")
        self.assertEqual(self.member(SLUG)["what"], "direct build")

    def test_shows_one_row_the_direct_builds__when_a_planner_is_alive_for_the_folder(self):
        """057-D2 — a live Planner and a live direct build for one unit show one row, the build's — the briefing row hides the build, or both show."""
        self.given_briefing()
        (self.sessions / SLUG / "LEDGER.md").write_text("# Ledger\n")
        self.given_running_direct_build()

        self.when_written()

        self.assertEqual(self.rows(), 1)
        self.assert_figure(SLUG, "worker")
        self.assertEqual(self.member(SLUG)["what"], "direct build")
        self.assertNotIn("Planner briefing", self.pages())

    def test_shows_only_the_sessions_row__when_the_units_folder_holds_a_run_json(self):
        """057-D3 — a folder holding a run.json and a busy Worker named for it show one row, the session's — a Robowright Session also reads as a direct build."""
        self.given_session()
        self.given_running_direct_build()

        self.when_written()

        self.assertEqual(self.rows(), 1)
        self.assertNotEqual(self.member(SLUG)["what"], "direct build")

    def test_reads_the_finished_direct_build_with_the_lead__when_its_unit_has_a_folder_with_no_run_json(self):
        """057-D4 — a finished direct build beside a folder with no run.json reads with the Lead — the folder hides finished work the Lead has to check."""
        self.given_folder_with_no_run_json()
        self.given_finished_direct_build()

        result = self.run_dash("sample")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("with the Lead", unit_line(result.stdout, "U1"))


if __name__ == "__main__":
    unittest.main()
