#!/usr/bin/env python3
"""Tests for run-cost.py's lines_shipped(): the range a session's shipped lines are counted over (U4 · D9).

    python3 skills/worker/scripts/test_run_cost.py

run-cost.py is loaded as a module, and lines_shipped() is called directly with a run dict whose
worktree is a scratch git repo built in setUp. The tests never touch a real session dir or the
real sessions root. The repo's four commits change one file, and each candidate end of the range
gives different counts:

    base        one                          base..
    stale       one two three                +2 −0   the last unit head, before a fold
    published   ONE two three four           +4 −1   publish.tip
    HEAD        ONE two three four five      +5 −1   the worktree's HEAD

The ledger suites below (U1 of the accounting brief, written from its behaviors file before the
ledger existed) drive run-cost.py and the SessionEnd hook as subprocesses under a scratch HOME,
so ~/.claude/projects, ~/.claude/robowright/launch.json and ~/.claude/usage are all scratch, and
the accounting root is a scratch directory. Every usage figure comes from the synthetic
transcripts defined here: the ending session B (main transcript plus one sidecar) and an
earlier session A of the same session dir.

The pricing suites (U2 of the accounting brief, written from its behaviors file before
pricing.py existed) name a synthetic pricing file through $ROBOWRIGHT_PRICING_FILE and the day
staleness is measured from through $ROBOWRIGHT_PRICING_NOW, so no test reads the shipped
pricing.json or the real date. LedgerCase gives every ledger test SIX_ROWS dated
PRICES_AS_OF, fresh on FRESH_TODAY.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
ABSENT = object()


def load_run_cost():
    """run-cost.py's name is not importable; load it by path."""
    spec = importlib.util.spec_from_file_location("run_cost", HERE / "run-cost.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COST = load_run_cost()
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


class LinesShippedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.worktree = Path(self.tmp.name) / "worktree"
        subprocess.run(GIT + ["init", "-q", str(self.worktree)], check=True, capture_output=True)
        self.base = self.given_commit("one\n", "base")
        self.stale = self.given_commit("one\ntwo\nthree\n", "U1, before the fold")[:7]
        self.published = self.given_commit("ONE\ntwo\nthree\nfour\n", "U1, folded and published")
        self.head = self.given_commit("ONE\ntwo\nthree\nfour\nfive\n", "after publish")
        self.given_owner_repos(self.worktree)

    def tearDown(self):
        self.tmp.cleanup()

    def given_env(self, **values):
        for name, value in values.items():
            previous = os.environ.get(name)
            os.environ[name] = value
            self.addCleanup(lambda n=name, p=previous: os.environ.pop(n, None) if p is None else os.environ.__setitem__(n, p))

    def given_owner_repos(self, *repos):
        """The repositories the Owner configured, through $ROBOWRIGHT_PROJECTS_ROOT, and launch.json's `repos` in a scratch HOME."""
        projects = Path(self.tmp.name) / "owner-projects"
        (projects / "sample").mkdir(parents=True, exist_ok=True)
        entries = [{"name": f"repo-{i}", "path": str(r)} for i, r in enumerate(repos)]
        (projects / "sample" / "robowright.json").write_text(json.dumps({"repos": entries}) + "\n")
        self.given_launch_json({"repos": [str(r) for r in repos]})
        self.given_env(ROBOWRIGHT_PROJECTS_ROOT=str(projects), HOME=str(self.home))

    @property
    def home(self):
        return Path(self.tmp.name) / "owner-home"

    def given_launch_json(self, settings):
        (self.home / ".claude/robowright").mkdir(parents=True, exist_ok=True)
        (self.home / ".claude/robowright/launch.json").write_text(json.dumps(settings) + "\n")

    def given_recording_git(self):
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").write_text(RECORDING_GIT)
        (bin_dir / "git").chmod(0o755)
        log = Path(self.tmp.name) / "git-argv.log"
        self.given_env(PATH=f"{bin_dir}:{os.environ['PATH']}", GIT_ARGV_LOG=str(log))
        return log

    # ------------------------------------------------------------ given

    def given_commit(self, text, message):
        (self.worktree / "notes.txt").write_text(text)
        subprocess.run(GIT + ["-C", str(self.worktree), "add", "-A"], check=True, capture_output=True)
        subprocess.run(GIT + ["-C", str(self.worktree), "commit", "-q", "-m", message], check=True, capture_output=True)
        done = subprocess.run(GIT + ["-C", str(self.worktree), "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
        return done.stdout.strip()

    def given_run(self, publish, unit_head=None, base_sha=None):
        """A one-unit run over the scratch worktree. By default its unit head is the pre-fold commit and its base_sha is the base commit."""
        run = {
            "worktree": str(self.worktree),
            "base_sha": base_sha or self.base,
            "units": [{"id": "U1", "status": "done", "head": unit_head or self.stale, "gate_attempts": 1, "gate": {"review": "reviews/U1-gate.md"}}],
        }
        if publish is not ABSENT:
            run["publish"] = publish
        return run

    def published_at(self, tip):
        return {"strategy": "local-branch", "branch": "robowright/fixture", "tip": tip, "change_description": "prs/fixture.md"}

    # ------------------------------------------------------------ when

    def shipped(self, run):
        """lines_shipped(run) and what reached stderr. File descriptor 2 is captured, so the test sees a reason whether Python prints it or git's own stderr passes it through."""
        with tempfile.TemporaryFile(mode="w+") as err:
            sys.stderr.flush()
            saved = os.dup(2)
            os.dup2(err.fileno(), 2)
            try:
                result = COST.lines_shipped(run)
                sys.stderr.flush()
            finally:
                os.dup2(saved, 2)
                os.close(saved)
            err.seek(0)
            return result, err.read()

    def counts(self, result):
        return None if result is None else (result["added"], result["removed"], result["range"])

    # ------------------------------------------------------------ R3 · a published tip ends the range

    def test_range_ends_at_the_published_tip__not_at_a_stale_unit_head(self):
        """publish.tip ends the range, not the last unit head — after a sanctioned fold the stale head reports the wrong lines."""
        result, _ = self.shipped(self.given_run(publish=self.published_at(self.published[:7])))
        self.assertEqual(self.counts(result), (4, 1, f"{self.base[:10]}..{self.published[:7]}"))

    def test_range_ends_at_the_published_tip__when_the_unit_head_names_no_commit(self):
        """A unit head that names no commit does not affect a published run — an unresolvable head would otherwise fail the diff and report +0/−0."""
        result, _ = self.shipped(self.given_run(publish=self.published_at(self.published[:7]), unit_head="7fe8979a"))
        self.assertEqual(self.counts(result), (4, 1, f"{self.base[:10]}..{self.published[:7]}"))

    def test_range_ends_at_ten_characters_of_a_full_length_published_tip(self):
        """A 40-character tip ends the range with its first ten characters — the range would print a full SHA, unlike every other cost record."""
        result, _ = self.shipped(self.given_run(publish=self.published_at(self.published)))
        self.assertEqual(self.counts(result), (4, 1, f"{self.base[:10]}..{self.published[:10]}"))

    # ------------------------------------------------------------ R4 · no published tip, the worktree's HEAD ends the range

    def test_range_ends_at_the_worktree_head__when_publish_carries_no_tip(self):
        """Every publish shape without a tip counts base..HEAD, never the last unit head — live run.json files hold all five shapes, and only a dict with a tip may pick the end (range spelling open, Q1)."""
        ends_at_head = {f"{self.base[:10]}..HEAD", f"{self.base[:10]}..{self.head[:10]}"}
        for publish in (ABSENT, None, True, "local-branch", {"strategy": "local-branch", "branch": "robowright/fixture"}):
            with self.subTest(publish=publish):
                result, _ = self.shipped(self.given_run(publish=publish))
                self.assertIsNotNone(result)
                self.assertEqual((result["added"], result["removed"]), (5, 1))
                self.assertIn(result["range"], ends_at_head)

    # ------------------------------------------------------------ R5 · a failed diff is None with a reason, never +0/−0

    def test_returns_none_naming_the_base__when_base_sha_does_not_resolve(self):
        """An unresolvable base_sha gives None and names the SHA on stderr — +0/−0 would be recorded as a session that shipped nothing (assumed Q2)."""
        run = self.given_run(publish=self.published_at(self.published[:7]), base_sha="badc0ffee0ddf00dbadc0ffee0ddf00dbadc0ffe")
        result, err = self.shipped(run)
        self.assertIsNone(result)
        self.assertIn("badc0ff", err)

    def test_returns_none_naming_the_tip__when_the_published_tip_does_not_resolve(self):
        """An unresolvable publish.tip gives None and names the tip — falling back to another end would count lines that were never published (assumed Q2)."""
        result, err = self.shipped(self.given_run(publish=self.published_at("7fe8979a")))
        self.assertIsNone(result)
        self.assertIn("7fe8979", err)

    def test_returns_none_naming_the_field__when_base_sha_or_the_tip_is_not_a_commit_id(self):
        """SI-9: base_sha and publish.tip are session-written and reach git's argv outside the sandbox, so only hex or HEAD is passed; anything else is None, naming the field, before git runs."""
        for run, field in (
            (self.given_run(publish=self.published_at(self.published[:7]), base_sha="--stat"), "base_sha"),
            (self.given_run(publish=self.published_at("HEAD~1")), "publish.tip"),
            (self.given_run(publish=self.published_at("-p")), "publish.tip"),
        ):
            with self.subTest(field=field, run=run):
                result, err = self.shipped(run)
                self.assertIsNone(result)
                self.assertIn(field, err)

    # ------------------------------------------------------------ R6 · git runs only in a configured repository's worktree, hardened

    def test_returns_none_naming_the_refusal__when_no_configured_repository_lists_the_worktree(self):
        """R6.1 · a worktree no robowright.json repository lists is None naming worktree-unlisted, and no git runs inside it — its config would run as the Owner at SessionEnd."""
        self.given_owner_repos(Path(self.tmp.name) / "some-other-clone")
        log = self.given_recording_git()
        result, err = self.shipped(self.given_run(publish=self.published_at(self.published[:7])))
        self.assertIsNone(result)
        self.assertIn("worktree-unlisted", err)
        self.assertEqual([c for c in git_calls(log) if runs_in(c, self.worktree)], [])

    def test_returns_none_naming_the_key_and_the_file__when_launch_json_has_no_repos(self):
        """R6.3 · with launch.json holding no `repos`, the shipped range is None naming repos-unconfigured, the file and the `"repos": [...]` line, and no git runs inside the worktree — the Owner's cost line would go quiet with no word on why."""
        self.given_launch_json({"schema": 1})
        log = self.given_recording_git()
        result, err = self.shipped(self.given_run(publish=self.published_at(self.published[:7])))
        self.assertIsNone(result)
        self.assertIn("repos-unconfigured", err)
        self.assertIn(str(self.home / ".claude/robowright/launch.json"), err)
        self.assertIn(f'"repos": [{json.dumps(str(self.worktree))}]', err)
        self.assertEqual([c for c in git_calls(log) if runs_in(c, self.worktree)], [])

    def test_the_diff_carries_the_overrides_and_no_external_diff_or_textconv(self):
        """R6.2 · every git call starts with the fsmonitor, hooksPath, pager and showSignature overrides, and the diff passes --no-ext-diff --no-textconv — diff.external or a textconv driver would run as the Owner."""
        log = self.given_recording_git()
        result, err = self.shipped(self.given_run(publish=self.published_at(self.published[:7])))
        self.assertEqual(self.counts(result), (4, 1, f"{self.base[:10]}..{self.published[:7]}"), err)
        calls = git_calls(log)
        diffs = [c for c in calls if "diff" in c]
        self.assertEqual(len(diffs), 1, calls)
        self.assertIn("--no-ext-diff", diffs[0])
        self.assertIn("--no-textconv", diffs[0])
        for call in calls:
            self.assertEqual(call[:len(HARDENING)], HARDENING, call)

    def test_returns_none_naming_the_base__when_the_range_ends_at_head(self):
        """The HEAD-ended range fails the same way: an unresolvable base_sha gives None and a reason, not +0/−0 (assumed Q2)."""
        run = self.given_run(publish=True, base_sha="badc0ffee0ddf00dbadc0ffee0ddf00dbadc0ffe")
        result, err = self.shipped(run)
        self.assertIsNone(result)
        self.assertIn("badc0ff", err)


# ================================================================== the ledger (U1 · accounting)

RUN_COST = HERE / "run-cost.py"
SESSION_COST_HOOK = HERE.parent / "hooks" / "session-cost.sh"
# macOS /bin/bash is 3.2, which is what the hooks are written for.
BASH = "/bin/bash" if Path("/bin/bash").exists() else "bash"

EARLIER_SESSION = "a1a1a1a1-0000-4000-8000-000000000001"
ENDING_SESSION = "b2b2b2b2-0000-4000-8000-000000000002"
WORKTREE = "/Users/owner/wt/sample-013-ledger"
# Claude Code's project dir for WORKTREE: every non-alphanumeric character turned into "-".
PROJECT_DIR = "-Users-owner-wt-sample-013-ledger"

# One row per transcript line: (message id, model, timestamp, input, output, cache read, cache write).
# Figures are large enough that every (role, model) pair prices above a cent, so an estimate
# rounded to cents is still positive.
# Session B's main transcript. msg_b1 is one request written as two lines (Claude Code splits a
# response's content blocks); the <synthetic> line is a turn that never reached the API.
ENDING_MAIN = (
    ("msg_b1", "claude-opus-5-5", "2026-09-20T10:00:00.000Z", 100000, 20000, 1000000, 300000),
    ("msg_b1", "claude-opus-5-5", "2026-09-20T10:00:00.000Z", 100000, 20000, 1000000, 300000),
    ("msg_b2", "claude-opus-5-5", "2026-09-20T10:30:00.000Z", 200000, 40000, 2000000, 0),
    ("msg_b0", "<synthetic>", "2026-09-20T10:45:00.000Z", 0, 0, 0, 0),
    ("msg_b3", "claude-sonnet-5", "2026-09-20T11:00:00.000Z", 10000, 5000, 0, 50000),
)
# Session B's one sidecar, <B>/subagents/agent-b2s1.jsonl. Its last line is the session's last timestamp.
ENDING_SIDECAR = (
    ("msg_s1", "claude-haiku-4-5", "2026-09-20T10:10:00.000Z", 30000, 7000, 400000, 60000),
    ("msg_s2", "claude-opus-5-5", "2026-09-20T11:15:00.000Z", 50000, 9000, 600000, 0),
)
# Session A, an earlier session of the same session dir, pinned beside B in run.json.
EARLIER_MAIN = (
    ("msg_a1", "claude-opus-5-5", "2026-09-19T09:00:00.000Z", 7000, 700, 70000, 7000),
)
# B's window: 10:00:00Z (msg_b1) to 11:15:00Z (msg_s2, the sidecar) = 4500 s.
ENDING_WINDOW_SECONDS = 4500

# USD per million tokens: the six rows of run-cost.py's table at the accounting base (:46-54), as the
# pricing file spells a row. Synthetic only in the file around them: the date below is not the
# shipped file's, so a report quoting it proves it read this file.
SIX_ROWS = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write_5m": 5.00, "cache_write_1h": 8.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00},
    "claude-fable-5-1": {"input": 10.00, "output": 50.00, "cache_read": 0.25, "cache_write_5m": 12.50, "cache_write_1h": 20.00},
    "claude-fable-5": {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_write_5m": 12.50, "cache_write_1h": 20.00},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write_5m": 2.50, "cache_write_1h": 4.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00},
}
OPUS_5_ROW = SIX_ROWS["claude-opus-5"]
PRICES_AS_OF = "2026-09-10"
FRESH_TODAY = "2026-09-26"
# 2026-09-10 + 30 days = 2026-10-10 (not stale); + 31 days = 2026-10-11 (stale).
THIRTY_DAYS_ON = "2026-10-10"
THIRTY_ONE_DAYS_ON = "2026-10-11"

SECTION_6_FIELDS = (
    "scope", "at", "source", "project", "unit", "unit_id", "role", "model", "session_id", "session_dir",
    "transcripts_pinned", "requests", "input_tokens", "output_tokens", "cache_read_tokens",
    "cache_write_tokens", "avg_context_tokens", "estimated_usd", "price_as_of", "wall_seconds",
    "active_seconds", "plan_5h_pct", "plan_7d_pct", "plan_captured_at",
)


def transcript_text(rows):
    lines = []
    for n, (msg_id, model, at, inp, out, cache_read, cache_write) in enumerate(rows):
        lines.append(json.dumps({
            "type": "assistant", "timestamp": at, "uuid": f"uuid-{msg_id}-{n}",
            "message": {"id": msg_id, "type": "message", "role": "assistant", "model": model,
                        "content": [{"type": "text", "text": "ok"}],
                        "usage": {"input_tokens": inp, "output_tokens": out,
                                  "cache_read_input_tokens": cache_read,
                                  "cache_creation_input_tokens": cache_write}},
        }))
    return "\n".join(lines) + "\n"


class LedgerCase(unittest.TestCase):
    """A scratch HOME holding session B's and session A's transcripts under one project dir, a
    session dir under ~/sessions whose run.json pins both, and a scratch accounting root named by
    $ROBOWRIGHT_ACCOUNTING_ROOT. No launch.json and no usage file unless a test gives one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # $TMPDIR is a symlink on macOS; an unresolved HOME would put ~ on the other side of it.
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.sessions_root = self.home / "sessions"
        self.run_dir = self.sessions_root / "sample-013-ledger"
        self.run_dir.mkdir(parents=True)
        self.project_dir = self.home / ".claude/projects" / PROJECT_DIR
        self.project_dir.mkdir(parents=True)
        self.accounting_root = self.root / "accounting"
        self.accounting_root.mkdir()
        self.ending_transcript = self.given_transcript(ENDING_SESSION, ENDING_MAIN, ENDING_SIDECAR)
        self.earlier_transcript = self.given_transcript(EARLIER_SESSION, EARLIER_MAIN)
        inherited = ("CLAUDE_USAGE_DIR", "ROBOWRIGHT_SESSIONS_ROOT", "ROBOWRIGHT_ACCOUNTING_ROOT", "ROBOWRIGHT_RUN_DIR",
                     "ROBOWRIGHT_PRICING_FILE", "ROBOWRIGHT_PRICING_NOW")
        self.env = {k: v for k, v in os.environ.items() if k not in inherited}
        self.pricing_file = self.given_pricing()
        self.env.update(HOME=str(self.home), ROBOWRIGHT_ACCOUNTING_ROOT=str(self.accounting_root),
                        ROBOWRIGHT_PRICING_FILE=str(self.pricing_file), ROBOWRIGHT_PRICING_NOW=FRESH_TODAY)
        self.given_run()

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------ given

    def given_transcript(self, session_id, rows, sidecar=()):
        path = self.project_dir / f"{session_id}.jsonl"
        path.write_text(transcript_text(rows))
        if sidecar:
            side = self.project_dir / session_id / "subagents"
            side.mkdir(parents=True)
            (side / f"agent-{session_id[:4]}s1.jsonl").write_text(transcript_text(sidecar))
        return path

    def given_pricing(self, models=SIX_ROWS, default=OPUS_5_ROW, updated_at=PRICES_AS_OF):
        """A pricing file in the scratch root, in the shape Language → pricing file names."""
        path = self.root / "prices" / "pricing.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"updated_at": updated_at, "source": "sample price page",
                                    "default": default, "models": models}, indent=2) + "\n")
        return path

    def pin(self, session_id):
        """A transcript as the launcher's pin_session writes it into run.json: home-relative."""
        return f"~/.claude/projects/{PROJECT_DIR}/{session_id}.jsonl"

    def given_run(self, **fields):
        run = {"ticket": "sample-013-ledger", "project": "sample", "worktree": WORKTREE,
               "transcripts": [self.pin(EARLIER_SESSION), self.pin(ENDING_SESSION)], "cost": None}
        run.update(fields)
        (self.run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")

    def given_events(self, *events):
        """events.jsonl lines as session-state.py appends them: n, at (ISO with offset), event."""
        lines = [json.dumps({"n": n, "at": at, "event": event, "machine": "session"}) for n, (at, event) in enumerate(events, 1)]
        (self.run_dir / "events.jsonl").write_text("\n".join(lines) + "\n")

    def given_usage(self, directory, **windows):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "latest.json").write_text(json.dumps(dict({"session_id": "c3c3c3c3-0000-4000-8000-000000000003"}, **windows)))

    def given_launch_json(self, **keys):
        path = self.home / ".claude/robowright/launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict({"schema": 1}, **keys), indent=2) + "\n")

    def env_without(self, *names):
        return {k: v for k, v in self.env.items() if k not in names}

    # ------------------------------------------------------------ when

    def ledger(self, *extra, session_id=ENDING_SESSION, transcript=None, env=None):
        """run-cost.py --ledger for one ending Claude session, as the SessionEnd hook calls it."""
        return subprocess.run(
            [sys.executable, str(RUN_COST), "--run-dir", str(self.run_dir), "--ledger",
             "--session-id", session_id, "--transcript", str(transcript or self.ending_transcript), *extra],
            env=env or self.env, capture_output=True, text=True)

    def must_ledger(self, *extra, **kwargs):
        done = self.ledger(*extra, **kwargs)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    # ------------------------------------------------------------ then

    def ledger_path(self, root=None):
        return (root or self.accounting_root) / "records.jsonl"

    def records(self, root=None):
        path = self.ledger_path(root)
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def by_role_and_model(self, records):
        return {(r["role"], r["model"]): r for r in records}

    def worker_opus(self, root=None):
        return self.by_role_and_model(self.records(root))[("worker", "claude-opus-5-5")]


# ------------------------------------------------------------ R1 · one session-scope record per (role, model)

class LedgerRecordTests(LedgerCase):
    def test_appends_one_record_per_role_and_model__for_the_ending_session(self):
        """Session B's transcripts hold two roles and three models in four pairs, and the ledger gets exactly those four records — a record per session, per role or per model would make every --by row a guess (D3)."""
        self.must_ledger()

        records = self.records()

        self.assertEqual(len(records), 4, records)
        self.assertEqual(set(self.by_role_and_model(records)), {
            ("worker", "claude-opus-5-5"), ("worker", "claude-sonnet-5"),
            ("subagent", "claude-haiku-4-5"), ("subagent", "claude-opus-5-5"),
        })

    def test_each_record_carries_the_token_facts_of_its_own_role_and_model(self):
        """Requests and tokens by class are the facts every rollup sums; a figure summed into the wrong (role, model) pair, a request counted once per line instead of once per message, or a <synthetic> turn counted as a request all corrupt every report built on them (D3, §6)."""
        self.must_ledger()

        facts = {key: (r["requests"], r["input_tokens"], r["output_tokens"], r["cache_read_tokens"],
                       r["cache_write_tokens"], r["avg_context_tokens"])
                 for key, r in self.by_role_and_model(self.records()).items()}

        self.assertEqual(facts, {
            ("worker", "claude-opus-5-5"): (2, 300000, 60000, 3000000, 300000, 1800000),
            ("worker", "claude-sonnet-5"): (1, 10000, 5000, 0, 50000, 60000),
            ("subagent", "claude-haiku-4-5"): (1, 30000, 7000, 400000, 60000, 490000),
            ("subagent", "claude-opus-5-5"): (1, 50000, 9000, 600000, 0, 650000),
        })

    def test_every_record_carries_every_section_6_field(self):
        """U18 and U19 read the ledger by §6's field names; a record missing one is a KeyError in every reader downstream (§6, ratified)."""
        self.must_ledger()

        for record in self.records():
            with self.subTest(role=record.get("role"), model=record.get("model")):
                self.assertLessEqual(set(SECTION_6_FIELDS), set(record), sorted(set(SECTION_6_FIELDS) - set(record)))

    def test_record_names_its_scope_session_project_and_unit(self):
        """The identity fields are the rollup's group keys: project from run.json.project, unit from run.json.ticket, the hook's session id, and a scope of session with no unit id — any other value lands the tokens in the wrong row (§6; source "hook", assumed Q1)."""
        self.must_ledger()

        record = self.worker_opus()

        self.assertEqual(
            {k: record[k] for k in ("scope", "source", "project", "unit", "unit_id", "session_id", "session_dir")},
            {"scope": "session", "source": "hook", "project": "sample", "unit": "sample-013-ledger",
             "unit_id": None, "session_id": ENDING_SESSION, "session_dir": str(self.run_dir)})

    def test_record_is_stamped_with_an_offset_timestamp(self):
        """`at` is compared across machines and against event times written with an offset; a naive timestamp is ambiguous by the machine's zone (§6: "ISO-8601 with offset")."""
        self.must_ledger()

        at = datetime.fromisoformat(self.worker_opus()["at"])

        self.assertIsNotNone(at.utcoffset())

    def test_record_carries_an_estimate_and_the_pricing_file_s_date(self):
        """Every record has a dollar estimate, the larger request set the larger one, and quotes the pricing file's updated_at as price_as_of so a later reader knows which prices made it (§6: "price_as_of — pricing.json.updated_at"; U2 row: "records carry price_as_of")."""
        self.must_ledger()

        records = self.by_role_and_model(self.records())

        for key, record in records.items():
            with self.subTest(role_and_model=key):
                self.assertIsInstance(record["estimated_usd"], (int, float))
                self.assertGreater(record["estimated_usd"], 0)
                self.assertEqual(record["price_as_of"], PRICES_AS_OF)
        self.assertGreater(records[("worker", "claude-opus-5-5")]["estimated_usd"],
                           records[("worker", "claude-sonnet-5")]["estimated_usd"])

    def test_record_project_is_null__when_run_json_names_no_project(self):
        """A session launched before the launcher wrote run.json.project records no project rather than one derived a second way — two derivations of one key disagree the day launch.json's group_regex changes (assumed Q3)."""
        self.given_run(project=None)
        self.must_ledger()

        self.assertIsNone(self.worker_opus()["project"])

    def test_transcripts_pinned_is_true__when_run_json_pins_the_transcript_home_relative(self):
        """The launcher pins `~/.claude/projects/…` and the hook passes the absolute path of the same file; reading those as different transcripts would mark every launched session unpinned (§6, assumed Q20)."""
        self.must_ledger()

        self.assertTrue(self.worker_opus()["transcripts_pinned"])

    def test_transcripts_pinned_is_false__when_run_json_pins_no_transcripts(self):
        """Every pasted launch leaves run.json.transcripts null; the record says so, rather than claiming a pin that was never made (§6)."""
        self.given_run(transcripts=None)
        self.must_ledger()

        self.assertFalse(self.worker_opus()["transcripts_pinned"])


# ------------------------------------------------------------ R2 · the ending session's transcripts only

class LedgerTranscriptSetTests(LedgerCase):
    def test_counts_only_the_ending_session__when_run_json_pins_an_earlier_one_too(self):
        """A rotated brief pins several sessions; a record measured over every pin counts the earlier session's tokens again at each end (D4, Risk 1)."""
        self.must_ledger()

        record = self.worker_opus()

        self.assertEqual((record["requests"], record["input_tokens"]), (2, 300000))

    def test_write_still_measures_every_pinned_transcript_in_the_old_buckets(self):
        """run.json.cost is the per-session-dir total the roster and the Lead read; the ledger's narrower set and singular `subagent` must not leak into it (D4: "--write … unchanged"; green before the unit exists)."""
        done = subprocess.run(
            [sys.executable, str(RUN_COST), "--run-dir", str(self.run_dir), "--write", "--json",
             "--transcript", str(self.ending_transcript)],
            env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

        cost = json.loads((self.run_dir / "run.json").read_text())["cost"]

        self.assertEqual(cost["requests"], 6)
        self.assertEqual(set(cost["by_role"]), {"worker", "subagents"})
        self.assertEqual((cost["by_role"]["worker"]["requests"], cost["by_role"]["subagents"]["requests"]), (4, 2))


# ------------------------------------------------------------ R3 · append-only, once per session, under the lock

class LedgerAppendTests(LedgerCase):
    def test_second_call_for_the_same_session_appends_nothing(self):
        """The hook, a rotate and the Lead's intake can each ask for the same session's record; a second set of lines doubles that session in every rollup (U1 acceptance; exit 0, assumed Q7)."""
        self.must_ledger()
        first = self.ledger_path().read_text()

        again = self.ledger()

        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.ledger_path().read_text(), first)

    def test_a_call_for_another_session_of_the_same_session_dir_still_appends(self):
        """Once-per-session is keyed on the Claude session, not the session dir — keyed on the dir, a rotated brief records only its first session (D3, D4)."""
        self.must_ledger(session_id=EARLIER_SESSION, transcript=self.earlier_transcript)
        self.must_ledger()

        sessions = [r["session_id"] for r in self.records()]

        self.assertEqual((sessions.count(EARLIER_SESSION), sessions.count(ENDING_SESSION)), (1, 4))

    def test_keeps_every_existing_line__and_a_ragged_last_line_does_not_swallow_a_record(self):
        """The ledger is never rewritten, and a writer that died mid-line leaves a fragment the next append must start after — joined to it, the first new record is lost to every reader (D5, §3.2)."""
        seeded = ('{"scope": "session", "session_id": "c3c3c3c3-0000-4000-8000-000000000003", "project": "demo", "requests": 3}\n'
                  '{"scope": "session", "session_id": "c3c3')
        self.ledger_path().write_text(seeded)

        self.must_ledger()

        text = self.ledger_path().read_text()
        self.assertTrue(text.startswith(seeded), text[:300])
        appended = text[len(seeded):].splitlines()
        self.assertEqual(appended[0], "", "the first new record was joined to the ragged line")
        self.assertEqual([json.loads(line)["session_id"] for line in appended[1:]], [ENDING_SESSION] * 4)

    def test_leaves_the_lock_file_beside_the_ledger(self):
        """Two sessions ending in the same minute append to one file; the shared lock beside it is what serialises them, and the per-session-dir lock cannot (D5)."""
        self.must_ledger()

        self.assertTrue((self.accounting_root / ".records.lock").is_file())


# ------------------------------------------------------------ R4 · wall and active time

class ActiveTimeTests(LedgerCase):
    def test_wall_and_active_are_the_span_of_every_measured_transcript__when_no_events_exist(self):
        """The window runs from the first to the last timestamp across the main transcript and its sidecars — a sidecar still working after the main transcript's last line is still the session's time (D10)."""
        self.must_ledger()

        record = self.worker_opus()

        self.assertEqual((record["wall_seconds"], record["active_seconds"]), (ENDING_WINDOW_SECONDS, ENDING_WINDOW_SECONDS))

    def test_active_time_subtracts_a_stop_to_resume_gap_inside_the_window(self):
        """Time spent stopped waiting for the Owner is not work; a gap of 10:40Z–10:50Z, written with a +02:00 offset, takes 600 s off the 4500 s window (D10)."""
        self.given_events(("2026-09-20T12:05:00+02:00", "unit-start"),
                          ("2026-09-20T12:40:00+02:00", "stop"),
                          ("2026-09-20T12:50:00+02:00", "resume"))
        self.must_ledger()

        record = self.worker_opus()

        self.assertEqual((record["wall_seconds"], record["active_seconds"]), (4500, 3900))

    def test_active_time_clips_a_gap_to_the_window__and_ignores_one_outside_it(self):
        """A stop from before the session began counts only from the window's start (09:30Z–10:05Z → 300 s), and a gap after the window counts nothing — unclipped, an old stop makes active time negative (D10: "gaps clipped to it")."""
        self.given_events(("2026-09-20T02:30:00-07:00", "stop"),
                          ("2026-09-20T03:05:00-07:00", "resume"),
                          ("2026-09-20T11:30:00+00:00", "stop"),
                          ("2026-09-20T11:45:00+00:00", "resume"))
        self.must_ledger()

        self.assertEqual(self.worker_opus()["active_seconds"], 4200)

    def test_a_home_relative_run_dir_reads_its_events_and_records_the_absolute_session_dir(self):
        """`--run-dir ~/sessions/…` unexpanded, as a quoted launch line passes it: the record names the absolute session dir and the stop-to-resume gap still comes off the 4500 s window (U1 gate F2)."""
        self.given_events(("2026-09-20T12:40:00+02:00", "stop"),
                          ("2026-09-20T12:50:00+02:00", "resume"))
        done = subprocess.run(
            [sys.executable, str(RUN_COST), "--run-dir", "~/sessions/sample-013-ledger", "--ledger",
             "--session-id", ENDING_SESSION, "--transcript", str(self.ending_transcript)],
            env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

        record = self.worker_opus()

        self.assertEqual((record["session_dir"], record["active_seconds"]), (str(self.run_dir), 3900))


# ------------------------------------------------------------ R5 · plan usage at record time

class PlanUsageTests(LedgerCase):
    def test_plan_figures_are_copied_from_the_default_usage_file(self):
        """The plan's 5-hour and 7-day percentages at record time are the only spend figure a plan-budget install has (D11; plan_captured_at copied as written, assumed Q4)."""
        self.given_usage(self.home / ".claude/usage", captured_at=1789990000,
                         five_hour={"used_percentage": 23}, seven_day={"used_percentage": 41})
        self.must_ledger()

        record = self.worker_opus()

        self.assertEqual((record["plan_5h_pct"], record["plan_7d_pct"], record["plan_captured_at"]), (23, 41, 1789990000))

    def test_plan_figures_come_from_CLAUDE_USAGE_DIR__over_the_default(self):
        """usage-tap.py writes where $CLAUDE_USAGE_DIR says; reading the default beside it quotes a file nothing updates (D11)."""
        self.given_usage(self.home / ".claude/usage", captured_at=1789990000,
                         five_hour={"used_percentage": 23}, seven_day={"used_percentage": 41})
        self.given_usage(self.root / "usage", captured_at=1789995000,
                         five_hour={"used_percentage": 64}, seven_day={"used_percentage": 72})
        self.must_ledger(env=dict(self.env, CLAUDE_USAGE_DIR=str(self.root / "usage")))

        record = self.worker_opus()

        self.assertEqual((record["plan_5h_pct"], record["plan_7d_pct"], record["plan_captured_at"]), (64, 72, 1789995000))

    def test_plan_figures_are_null__when_there_is_no_usage_file(self):
        """No usage tap on the machine is no plan figure, not a failed record — the tokens are facts either way (D11)."""
        self.must_ledger()

        record = self.worker_opus()

        self.assertEqual((record["plan_5h_pct"], record["plan_7d_pct"], record["plan_captured_at"]), (None, None, None))

    def test_a_window_missing_from_the_usage_file_is_null__and_the_other_is_kept(self):
        """A usage file with no seven_day window gives plan_7d_pct null and still the 5-hour figure — one absent window must not erase the other (D11: "absent file or window → nulls")."""
        self.given_usage(self.home / ".claude/usage", captured_at=1789990000, five_hour={"used_percentage": 23})
        self.must_ledger()

        record = self.worker_opus()

        self.assertEqual((record["plan_5h_pct"], record["plan_7d_pct"]), (23, None))


# ------------------------------------------------------------ R6 · the accounting root's precedence

class AccountingRootTests(LedgerCase):
    def test_the_flag_names_the_accounting_root__over_the_environment(self):
        """--accounting-root is how a suite or a one-off points the write at scratch; losing to the environment would write a test's records into the Owner's ledger (Language: accounting root)."""
        flagged = self.root / "flagged"
        flagged.mkdir()

        self.must_ledger("--accounting-root", str(flagged))

        self.assertEqual(len(self.records(flagged)), 4)
        self.assertFalse(self.ledger_path().exists())

    def test_the_environment_names_the_accounting_root__over_launch_json(self):
        """$ROBOWRIGHT_ACCOUNTING_ROOT outranks launch.json, the order the sessions root already follows (Language: accounting root)."""
        self.given_launch_json(sessions_root="~/sessions", accounting_root="~/from-launch-json")

        self.must_ledger()

        self.assertEqual(len(self.records()), 4)
        self.assertFalse((self.home / "from-launch-json/records.jsonl").exists())

    def test_launch_json_names_the_accounting_root__with_a_leading_tilde_expanded(self):
        """launch.json is the install's own setting, and its paths are written home-relative like sessions_root (Language: accounting root; `~/` expanded, created when missing, assumed Q5)."""
        self.given_launch_json(sessions_root="~/sessions", accounting_root="~/ledger-home")

        self.must_ledger(env=self.env_without("ROBOWRIGHT_ACCOUNTING_ROOT"))

        self.assertEqual(len(self.records(self.home / "ledger-home")), 4)

    def test_the_accounting_root_defaults_beside_launch_json_s_sessions_root(self):
        """With no accounting_root anywhere the ledger sits at <sessions_root>/../accounting, created on first write — so an install that never set it still has one ledger, not none (Language: accounting root; created, assumed Q5)."""
        self.given_launch_json(sessions_root="~/sessions")

        self.must_ledger(env=self.env_without("ROBOWRIGHT_ACCOUNTING_ROOT"))

        self.assertEqual(len(self.records(self.home / "accounting")), 4)

    def test_the_default_follows_ROBOWRIGHT_SESSIONS_ROOT__over_launch_json_s_sessions_root(self):
        """The sessions root is resolved as run-roster.py resolves it, environment first; a default beside the other root splits one install's records over two ledgers (Language: accounting root)."""
        self.given_launch_json(sessions_root="~/sessions")
        elsewhere = self.root / "elsewhere/sessions"
        elsewhere.mkdir(parents=True)

        self.must_ledger(env=dict(self.env_without("ROBOWRIGHT_ACCOUNTING_ROOT"), ROBOWRIGHT_SESSIONS_ROOT=str(elsewhere)))

        self.assertEqual(len(self.records(self.root / "elsewhere/accounting")), 4)
        self.assertFalse((self.home / "accounting/records.jsonl").exists())

    def test_the_default_sits_beside_the_sessions_root_s_real_directory__when_it_is_a_symlink(self):
        """The launcher writes launches.jsonl beside the physical sessions root; a ledger beside the link's parent loses every index line (U3 gate F2)."""
        real = self.root / "real/sessions"
        real.mkdir(parents=True)
        (self.home / "linked").symlink_to(real)

        self.must_ledger(env=dict(self.env_without("ROBOWRIGHT_ACCOUNTING_ROOT"), ROBOWRIGHT_SESSIONS_ROOT=str(self.home / "linked")))

        self.assertEqual(len(self.records(self.root / "real/accounting")), 4)

    def test_refuses_and_writes_nothing__when_no_accounting_root_can_be_resolved(self):
        """With no flag, no environment and no launch.json there is no ledger to append to; guessing one scatters records where no rollup looks (assumed Q6)."""
        done = self.ledger(env=self.env_without("ROBOWRIGHT_ACCOUNTING_ROOT"))

        self.assertNotEqual(done.returncode, 0)
        self.assertIn("accounting", done.stderr)
        self.assertEqual(list(self.root.rglob("records.jsonl")), [])


# ------------------------------------------------------------ R7 · the SessionEnd hook appends the ending session's records

class SessionCostHookTests(LedgerCase):
    def setUp(self):
        super().setUp()
        self.cwd = self.root / "work"
        (self.cwd / ".claude").mkdir(parents=True)
        (self.cwd / ".claude/autonomous-run").write_text(f"{self.run_dir}\n")

    def hook(self, env=None):
        stdin = json.dumps({"session_id": ENDING_SESSION, "transcript_path": str(self.ending_transcript),
                            "cwd": str(self.cwd), "hook_event_name": "SessionEnd", "reason": "other"})
        return subprocess.run([BASH, str(SESSION_COST_HOOK)], input=stdin, env=marker_env(env or self.env), capture_output=True, text=True)

    def test_a_session_end_appends_the_ending_session_s_records_to_the_ledger(self):
        """The hook is the only thing that runs at every Worker session's end; it passes its own session_id and transcript_path, so the records name that session and count only its transcripts (U1 acceptance, D4)."""
        done = self.hook()

        self.assertEqual(done.returncode, 0, done.stderr)
        records = self.records()
        self.assertEqual({r["session_id"] for r in records}, {ENDING_SESSION})
        self.assertEqual(self.worker_opus()["requests"], 2)

    def test_a_ledger_that_cannot_be_written_still_exits_0_and_records_run_json_cost(self):
        """A session's end is never blocked, and the cost record and LEDGER.md line the hook wrote before the ledger existed still land when the ledger write fails (Landmine; pre-change behaviour at the accounting base)."""
        not_a_dir = self.root / "not-a-dir"
        not_a_dir.write_text("a file where the accounting root should be\n")

        done = self.hook(env=dict(self.env, ROBOWRIGHT_ACCOUNTING_ROOT=str(not_a_dir)))

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIsNotNone(json.loads((self.run_dir / "run.json").read_text())["cost"])
        self.assertIn("session-cost", (self.run_dir / "LEDGER.md").read_text())



class SessionWriteTests(LedgerCase):
    """SW-12 (tests/run-launch/BEHAVIORS.md): --write and the SessionEnd hook write into the session dir outside the
    sandbox, so never through an entry the session planted there."""

    OWNER_TEXT = "the Owner's file\n"

    def setUp(self):
        super().setUp()
        self.cwd = self.root / "work"
        (self.cwd / ".claude").mkdir(parents=True)
        (self.cwd / ".claude/autonomous-run").write_text(f"{self.run_dir}\n")

    def hook(self):
        return run_session_cost_hook(self.env, self.cwd, ENDING_SESSION, self.ending_transcript)

    def planted(self, name):
        target = self.root / f"target-{name.lstrip('.')}"
        target.write_text(self.OWNER_TEXT)
        (self.run_dir / name).symlink_to(target)
        return target

    def test_write_never_takes_the_lock_or_writes_run_json_through_a_link(self):
        """store_cost opened the state tool's lock and run.json.tmp for writing; the replace then moved a tmp link onto run.json."""
        for name in (".session-state.lock", "run.json.tmp"):
            with self.subTest(name):
                target = self.planted(name)
                subprocess.run([sys.executable, str(RUN_COST), "--run-dir", str(self.run_dir), "--write", "--json"],
                               env=self.env, capture_output=True, text=True)
                self.assertEqual(target.read_text(), self.OWNER_TEXT)
                self.assertFalse((self.run_dir / "run.json").is_symlink())
                (self.run_dir / name).unlink(missing_ok=True)

    def test_the_hook_never_appends_its_ledger_line_through_a_link(self):
        """The SessionEnd hook's cost line is its one write into the session dir."""
        target = self.planted("LEDGER.md")
        done = self.hook()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(target.read_text(), self.OWNER_TEXT)

    def test_ledger_never_takes_its_lock_or_appends_a_record_through_a_link(self):
        """SW-19: the accounting root sits beside the sessions root, inside the sandbox grant, so a session can plant there too."""
        for name in (".records.lock", "records.jsonl"):
            with self.subTest(name):
                target = self.root / f"target-{name.lstrip('.')}"
                target.write_text(self.OWNER_TEXT)
                (self.accounting_root / name).symlink_to(target)
                done = self.ledger()
                for entry in self.accounting_root.iterdir():
                    entry.unlink()
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn("refused:", done.stderr)
                self.assertEqual(target.read_text(), self.OWNER_TEXT)

    def test_ledger_creates_nothing_through_a_dangling_records_link(self):
        """SW-19: a dangling link would otherwise create the file wherever it points."""
        missing = self.root / "never-created.jsonl"
        self.ledger_path().symlink_to(missing)
        done = self.ledger()
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertFalse(missing.exists())



# ------------------------------------------------------------ U2 · one pricing file prices everything
#
# The --write fixture is every transcript run.json pins plus the ending one: six requests
# (msg_b1 is one request on two lines; the <synthetic> turn is none). Its tokens:
#   input        100,000 + 200,000 + 10,000 + 30,000 + 50,000 + 7,000        =   397,000
#   output        20,000 +  40,000 +  5,000 +  7,000 +  9,000 +   700        =    81,700
#   cache read 1,000,000 + 2,000,000 + 0 + 400,000 + 600,000 + 70,000         = 4,070,000
#   cache write  300,000 + 0 + 50,000 + 60,000 + 0 + 7,000                   =   417,000
# At the six rows (cache writes with no tier breakdown price at the 5-minute rate):
#   opus-5-5  b1 2.50 + b2 2.00 + s2 0.50 + a1 0.091 = 5.091   sonnet-5 b3 0.195   haiku-4-5 s1 0.18
#   total 5.466 → 5.47

TIERED_SESSION = "e5e5e5e5-0000-4000-8000-000000000005"
# One Sonnet request whose cache write is split across both tiers: 100,000 at 5 minutes, 200,000 at 1 hour.
TIERED_ROW = {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write_5m": 3.00, "cache_write_1h": 6.00}


def tiered_transcript_text():
    return json.dumps({
        "type": "assistant", "timestamp": "2026-09-21T09:00:00.000Z", "uuid": "uuid-msg_t1-0",
        "message": {"id": "msg_t1", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                              "cache_creation_input_tokens": 300000,
                              "cache_creation": {"ephemeral_5m_input_tokens": 100000,
                                                 "ephemeral_1h_input_tokens": 200000}}},
    }) + "\n"


class PricingCase(LedgerCase):
    # ------------------------------------------------------------ when

    def cost_block(self, *flags, env=None):
        """run-cost.py --write over the fixture, as the SessionEnd hook and the Lead's intake run it."""
        return subprocess.run(
            [sys.executable, str(RUN_COST), "--run-dir", str(self.run_dir), "--write",
             "--transcript", str(self.ending_transcript), *flags],
            env=env or self.env, capture_output=True, text=True)

    def stored_cost(self, env=None):
        done = self.cost_block("--json", env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads((self.run_dir / "run.json").read_text())["cost"]

    # ------------------------------------------------------------ then

    def line_starting(self, text, prefix):
        lines = [line for line in text.splitlines() if line.startswith(prefix)]
        self.assertEqual(len(lines), 1, text)
        return lines[0]

    def stale_lines(self, done):
        return [line for line in (done.stdout + done.stderr).splitlines() if "stale" in line.lower()]

    def token_figures(self, cost):
        return (cost["requests"], cost["input_tokens"], cost["output_tokens"], cost["cache_read_tokens"], cost["cache_write_tokens"])


# ------------------------------------------------------------ R6 · run-cost.py prices from the file, and only from the file

class PricedFromTheFileTests(PricingCase):
    def test_write_prices_the_existing_fixture_as_before__from_a_file_holding_the_six_rows(self):
        """Moving the prices into a file is not a change in arithmetic: the same fixture at the same rates gives the same $5.47 (smoke: "the base build's output on the same fixture is the oracle"; derivation above; green before the unit exists)."""
        cost = self.stored_cost()

        self.assertAlmostEqual(cost["estimated_usd"], 5.47, places=6)
        self.assertAlmostEqual(cost["by_model"]["claude-opus-5-5"]["estimated_usd"], 5.09, places=6)
        self.assertAlmostEqual(cost["by_model"]["claude-haiku-4-5"]["estimated_usd"], 0.18, places=6)
        self.assertEqual(self.token_figures(cost), (6, 397000, 81700, 4070000, 417000))

    def test_write_prices_every_model_at_the_default_row__when_the_file_names_none_of_them(self):
        """A file with no model rows and a $1-per-million default prices the fixture at its token total, 4,965,700 → $4.97 — a price table left in the script would still give $5.47 (invariant: "pricing.py is their only source"; D9: "the default row for an unknown id")."""
        ones = {"input": 1.00, "output": 1.00, "cache_read": 1.00, "cache_write_5m": 1.00, "cache_write_1h": 1.00}
        self.given_pricing(models={}, default=ones)

        cost = self.stored_cost()

        self.assertAlmostEqual(cost["estimated_usd"], 4.97, places=6)

    def test_a_record_prices_each_cache_write_tier_at_its_own_rate(self):
        """100,000 five-minute tokens at $3 plus 200,000 one-hour tokens at $6 is $1.50; one rate for both tiers gives $0.90 or $1.80 (D9: "carries both cache-write tiers")."""
        self.given_pricing(models={"claude-sonnet-5": TIERED_ROW})
        tiered = self.project_dir / f"{TIERED_SESSION}.jsonl"
        tiered.write_text(tiered_transcript_text())

        self.must_ledger(session_id=TIERED_SESSION, transcript=tiered)

        record = self.by_role_and_model(self.records())[("worker", "claude-sonnet-5")]
        self.assertAlmostEqual(record["estimated_usd"], 1.50, places=6)


# ------------------------------------------------------------ R7 · the printed block says which prices it used, and warns past 30 days

class PricesAsOfTests(PricingCase):
    def test_the_printed_block_says_prices_as_of_the_file_s_updated_at(self):
        """An estimate is only as good as its prices; the block names their date so a reader can judge it (D2: "every report prints prices as of <updated_at>")."""
        done = self.cost_block()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"prices as of {PRICES_AS_OF}", done.stdout)

    def test_the_printed_block_warns_once_and_still_prices__when_the_file_is_31_days_old(self):
        """Prices change often enough that a month-old file is suspect; a file 31 days old gets one warning line, and the estimate is still printed from it (D2; Language: stale; the line says "stale", assumed Q3)."""
        done = self.cost_block(env=dict(self.env, ROBOWRIGHT_PRICING_NOW=THIRTY_ONE_DAYS_ON))

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.stale_lines(done)), 1, done.stdout + done.stderr)
        self.assertIn("$5.47", self.line_starting(done.stdout, "estimated usd:"))

    def test_the_printed_block_carries_no_stale_warning__when_the_file_is_30_days_old(self):
        """30 days is not "more than 30 days"; a warning a day early is noise the Owner learns to skip (Language: stale; assumed Q3)."""
        done = self.cost_block(env=dict(self.env, ROBOWRIGHT_PRICING_NOW=THIRTY_DAYS_ON))

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.stale_lines(done), [])


# ------------------------------------------------------------ R8 · a missing pricing file nulls every dollar figure and no token figure

class MissingPricingFileTests(PricingCase):
    def setUp(self):
        super().setUp()
        self.missing = self.root / "nowhere" / "pricing.json"
        self.env["ROBOWRIGHT_PRICING_FILE"] = str(self.missing)

    def test_every_usd_figure_in_the_cost_block_is_null__when_the_pricing_file_is_missing(self):
        """Without prices there is no estimate; $0.00, or a figure from a remembered table, reads as a real one (D9: "makes every USD figure null")."""
        cost = self.stored_cost()

        self.assertIsNone(cost["estimated_usd"])
        self.assertIsNone(cost["usd_per_request"])
        for model, m in cost["by_model"].items():
            with self.subTest(model=model):
                self.assertIsNone(m["estimated_usd"])
        for role, r in cost["by_role"].items():
            with self.subTest(role=role):
                self.assertIsNone(r["estimated_usd"])

    def test_every_token_figure_in_the_cost_block_is_unchanged__when_the_pricing_file_is_missing(self):
        """Tokens are facts read from the transcript; losing the prices must not lose them (invariant: "a missing pricing file changes no token figure"; derivation above)."""
        cost = self.stored_cost()

        self.assertEqual(self.token_figures(cost), (6, 397000, 81700, 4070000, 417000))
        self.assertEqual(cost["by_model"]["claude-opus-5-5"]["requests"], 4)

    def test_says_the_pricing_file_is_missing_in_exactly_one_stderr_line(self):
        """One line, however many requests went unpriced (D9: "with one stderr line"; the line names the file, assumed Q4)."""
        done = self.cost_block("--json")

        self.assertEqual(done.returncode, 0, done.stderr)
        lines = [line for line in done.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, done.stderr)
        self.assertIn(str(self.missing), lines[0])

    def test_the_printed_block_shows_the_estimate_as_n_a_and_keeps_its_token_lines__when_the_pricing_file_is_missing(self):
        """The text block still prints every token figure and marks the estimate n/a instead of failing on a missing number (U2 row: "print USD null (or n/a) with unchanged token counts"; n/a in text, assumed Q5)."""
        done = self.cost_block()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("n/a", self.line_starting(done.stdout, "estimated usd:"))
        self.assertIn("81,700", self.line_starting(done.stdout, "output tokens:"))
        input_line = self.line_starting(done.stdout, "input tokens:")
        for figure in ("397,000", "4,070,000", "417,000"):
            with self.subTest(figure=figure):
                self.assertIn(figure, input_line)

    def test_a_record_carries_null_estimate_and_null_price_date_with_its_token_facts__when_the_pricing_file_is_missing(self):
        """A ledger record made without prices says so in both fields and keeps its tokens, so a rollup can still count it (§6: "estimated_usd — null when pricing.json is missing", "price_as_of — … or null")."""
        self.must_ledger()

        records = self.by_role_and_model(self.records())

        for key, record in records.items():
            with self.subTest(role_and_model=key):
                self.assertIsNone(record["estimated_usd"])
                self.assertIsNone(record["price_as_of"])
        worker_opus = records[("worker", "claude-opus-5-5")]
        self.assertEqual((worker_opus["requests"], worker_opus["input_tokens"]), (2, 300000))

    def test_a_session_end_still_records_its_token_facts__when_the_pricing_file_mistypes_its_date(self):
        """A hand edit that writes "2026-10-1" must not cost the ledger a session: the record lands with null prices and its tokens (D9: "leaves the token facts"; gate U2 F1)."""
        self.missing.parent.mkdir(parents=True, exist_ok=True)
        self.missing.write_text(json.dumps({"updated_at": "2026-10-1", "source": "s", "default": SIX_ROWS["claude-opus-5"],
                                            "models": SIX_ROWS}))
        self.must_ledger()

        records = self.by_role_and_model(self.records())

        worker_opus = records[("worker", "claude-opus-5-5")]
        self.assertIsNone(worker_opus["estimated_usd"])
        self.assertEqual((worker_opus["requests"], worker_opus["input_tokens"]), (2, 300000))


# ================================================================== U3 · roles from the sidecars, unit windows, doc roles
#
# Written from evidence/U3-behaviors.md before any of U3 existed. Three fixtures:
#   - one-sidecar sessions on 2026-09-21, one per agent type (SidecarCase);
#   - the unit-window session f6f6…06 on 2026-09-22 (UnitWindowCase), pinned beside sessions A and B;
#   - a Planner session c7c7…07 on 2026-09-23 whose cwd is <scratch>/folders/demo (DocRoleCase).

# D7's table: agentType → role bucket.
AGENT_TYPE_BUCKETS = (
    ("reviewer-gate", "reviewer-code"),
    ("reviewer-adversarial", "reviewer-code"),
    ("reviewer-map", "reviewer-code"),
    ("reviewer-docs", "reviewer-prose"),
    ("reviewer-intake", "reviewer-prose"),
    ("reader-roster", "reader"),
    ("log-reader", "reader"),
    ("ui-tree-reader", "reader"),
    ("worker-spec", "spec"),
)

TYPED_MAIN = (("msg_m1", "claude-opus-5-5", "2026-09-21T08:00:00.000Z", 1000, 100, 10000, 1000),)
TYPED_SIDECAR = (("msg_x1", "claude-sonnet-5", "2026-09-21T08:10:00.000Z", 3000, 300, 30000, 3000),)


def sidecar_session(n):
    return f"d4d4d4d4-0000-4000-8000-{n:012d}"


def meta_json(agent_type, **extra):
    """A sidecar's .meta.json in the shape §3.1 quotes: agentType, description, toolUseId, spawnDepth, sometimes a model alias."""
    return json.dumps(dict({"agentType": agent_type, "description": "sample task", "toolUseId": "toolu_sample",
                            "spawnDepth": 1}, **extra))


def run_session_cost_hook(env, cwd, session_id, transcript, *args):
    """The SessionEnd hook as Claude Code runs it: its registered arguments, and the hook input on stdin."""
    stdin = json.dumps({"session_id": session_id, "transcript_path": str(transcript), "cwd": str(cwd),
                        "hook_event_name": "SessionEnd", "reason": "other"})
    return subprocess.run([BASH, str(SESSION_COST_HOOK), *args], input=stdin, env=marker_env(env), capture_output=True, text=True)


def marker_env(env):
    """The hook honours a marker only under the sessions root; every fixture's session dir sits under ~/sessions."""
    return dict(env, ROBOWRIGHT_SESSIONS_ROOT=env.get("ROBOWRIGHT_SESSIONS_ROOT") or str(Path(env["HOME"]) / "sessions"))


class SidecarCase(LedgerCase):
    def given_session(self, session_id, main_rows, sidecars=(), project_dir=None):
        """A main transcript and its sidecars. Each sidecar is (name, rows, meta): meta is the text of
        agent-<name>.meta.json beside agent-<name>.jsonl, or None for no meta file."""
        directory = project_dir or self.project_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{session_id}.jsonl"
        path.write_text(transcript_text(main_rows))
        side = directory / session_id / "subagents"
        for name, rows, meta in sidecars:
            side.mkdir(parents=True, exist_ok=True)
            (side / f"agent-{name}.jsonl").write_text(transcript_text(rows))
            if meta is not None:
                (side / f"agent-{name}.meta.json").write_text(meta)
        return path

    def session_scope(self, session_id):
        return self.by_role_and_model([r for r in self.records() if r["scope"] == "session" and r["session_id"] == session_id])


# ------------------------------------------------------------ U3 R1, R2 · a sidecar's role bucket comes from its agent type

class SidecarRoleTests(SidecarCase):
    def ledger_one_sidecar(self, n, rows, meta):
        session_id = sidecar_session(n)
        transcript = self.given_session(session_id, TYPED_MAIN, [("typed", rows, meta)])
        self.must_ledger(session_id=session_id, transcript=transcript)
        return self.session_scope(session_id)

    def test_each_agent_type_in_the_table_lands_in_its_role_bucket(self):
        """A Worker's Reviewers, Readers and spec writer are the costs the Owner tunes one at a time; lumped into one subagent bucket, --by role cannot say which one grew (D7; U3 row)."""
        for n, (agent_type, bucket) in enumerate(AGENT_TYPE_BUCKETS, 1):
            with self.subTest(agent_type=agent_type):
                records = self.ledger_one_sidecar(n, TYPED_SIDECAR, meta_json(agent_type))

                self.assertEqual(set(records), {("worker", "claude-opus-5-5"), (bucket, "claude-sonnet-5")})

    def test_an_agent_type_outside_the_table_lands_in_subagent(self):
        """An ad-hoc agent type is still a sidecar's cost; it lands in subagent rather than being dropped or given a bucket nobody reads (D7: "else subagent")."""
        records = self.ledger_one_sidecar(20, TYPED_SIDECAR, meta_json("general-purpose"))

        self.assertEqual(set(records), {("worker", "claude-opus-5-5"), ("subagent", "claude-sonnet-5")})

    def test_a_sidecar_with_no_meta_file_lands_in_subagent(self):
        """Older sidecars have no .meta.json; their tokens still count, as subagent (U3 row: "or no meta file as subagent")."""
        records = self.ledger_one_sidecar(21, TYPED_SIDECAR, None)

        self.assertEqual(set(records), {("worker", "claude-opus-5-5"), ("subagent", "claude-sonnet-5")})

    def test_a_sidecar_whose_meta_file_is_not_json_lands_in_subagent(self):
        """A half-written meta file must not cost the ledger the whole session's record (assumed Q23)."""
        records = self.ledger_one_sidecar(22, TYPED_SIDECAR, "{not json")

        self.assertEqual(set(records), {("worker", "claude-opus-5-5"), ("subagent", "claude-sonnet-5")})

    def test_a_sidecar_s_model_is_the_usage_record_s_id__not_the_meta_file_s_alias(self):
        """The meta file's model is an alias when present ("sonnet"); a record keyed by it prices at the wrong row and splits one model over two --by model rows (D7: "never the meta file")."""
        haiku = (("msg_x1", "claude-haiku-4-5", "2026-09-21T08:10:00.000Z", 3000, 300, 30000, 3000),)

        records = self.ledger_one_sidecar(23, haiku, meta_json("reviewer-docs", model="sonnet"))

        self.assertEqual(set(records), {("worker", "claude-opus-5-5"), ("reviewer-prose", "claude-haiku-4-5")})

    def test_two_agent_types_of_one_bucket_make_one_record_per_model(self):
        """reviewer-gate and reviewer-adversarial both land in reviewer-code, so on one model they are one record, 3000 + 5000 input and 2 requests — two records for one (session, role, model) break D3's key (D3)."""
        session_id = sidecar_session(24)
        transcript = self.given_session(session_id, TYPED_MAIN, [
            ("gate", (("msg_g1", "claude-sonnet-5", "2026-09-21T08:10:00.000Z", 3000, 300, 30000, 3000),), meta_json("reviewer-gate")),
            ("adversarial", (("msg_v1", "claude-sonnet-5", "2026-09-21T08:20:00.000Z", 5000, 500, 50000, 0),), meta_json("reviewer-adversarial")),
        ])
        self.must_ledger(session_id=session_id, transcript=transcript)

        records = [r for r in self.records() if r["session_id"] == session_id]

        self.assertEqual(len(records), 2, records)
        code = self.by_role_and_model(records)[("reviewer-code", "claude-sonnet-5")]
        self.assertEqual((code["requests"], code["input_tokens"], code["output_tokens"], code["cache_read_tokens"],
                          code["cache_write_tokens"]), (2, 8000, 800, 80000, 3000))

    def test_write_keeps_its_worker_and_subagents_buckets__when_sidecars_name_their_agent_type(self):
        """run.json.cost is read by the roster and the Lead under its old keys; the ledger's buckets must not leak into it (invariant: `--write` unchanged; green before the unit exists)."""
        session_id = sidecar_session(25)
        self.given_session(session_id, TYPED_MAIN, [("typed", TYPED_SIDECAR, meta_json("reviewer-gate"))])
        self.given_run(transcripts=[self.pin(session_id)])

        done = subprocess.run([sys.executable, str(RUN_COST), "--run-dir", str(self.run_dir), "--write", "--json"],
                              env=self.env, capture_output=True, text=True)

        self.assertEqual(done.returncode, 0, done.stderr)
        by_role = json.loads((self.run_dir / "run.json").read_text())["cost"]["by_role"]
        self.assertEqual(set(by_role), {"worker", "subagents"})
        self.assertEqual((by_role["worker"]["requests"], by_role["subagents"]["requests"]), (1, 1))


# ------------------------------------------------------------ U3 R3–R6 · unit windows

UNIT_SESSION = "f6f6f6f6-0000-4000-8000-000000000006"
# Session f6f6…06's main transcript. U1 runs 10:00:00Z → 11:00:00Z; U2 11:05Z → 11:20Z.
UNIT_MAIN = (
    ("msg_u0", "claude-opus-5-5", "2026-09-22T09:50:00.000Z", 1000, 100, 10000, 0),    # before U1
    ("msg_u1", "claude-opus-5-5", "2026-09-22T10:05:00.000Z", 2000, 200, 20000, 3000),  # U1
    ("msg_u2", "claude-opus-5-5", "2026-09-22T10:40:00.000Z", 6000, 600, 60000, 0),     # U1
    ("msg_u3", "claude-opus-5-5", "2026-09-22T11:00:02.000Z", 7000, 700, 70000, 0),     # between U1's two closes
    ("msg_u4", "claude-opus-5-5", "2026-09-22T11:10:00.000Z", 8000, 800, 80000, 0),     # U2
)
# Its one sidecar, a reviewer-gate, inside U1.
UNIT_GATE_SIDECAR = (("msg_g1", "claude-sonnet-5", "2026-09-22T10:10:00.000Z", 4000, 400, 0, 5000),)

# events.jsonl at −05:00: (at, event, unit). The stop → resume gap is 10:20Z → 10:35Z, 900 s inside U1.
U1_START = ("2026-09-22T05:00:00-05:00", "unit-start", "U1")
U1_STOP = ("2026-09-22T05:20:00-05:00", "stop", None)
U1_RESUME = ("2026-09-22T05:35:00-05:00", "resume", None)
U1_CLOSE = ("2026-09-22T06:00:00-05:00", "unit-close", "U1")
U1_CLOSE_AGAIN = ("2026-09-22T06:00:04-05:00", "unit-close", "U1")
U2_START = ("2026-09-22T06:05:00-05:00", "unit-start", "U2")
U2_CLOSE = ("2026-09-22T06:20:00-05:00", "unit-close", "U2")
UNIT_EVENTS = (U1_START, U1_STOP, U1_RESUME, U1_CLOSE, U2_START, U2_CLOSE)
UNIT_EVENTS_CLOSING_U1_TWICE = (U1_START, U1_STOP, U1_RESUME, U1_CLOSE, U1_CLOSE_AGAIN, U2_START, U2_CLOSE)
UNIT_EVENTS_U2_OPEN = (U1_START, U1_STOP, U1_RESUME, U1_CLOSE, U2_START)

# U1: worker × opus is msg_u1 + msg_u2; reviewer-code × sonnet is msg_g1. Window 3600 s, 900 s stopped.
U1_FACTS = {
    ("worker", "claude-opus-5-5"): (2, 8000, 800, 80000, 3000),
    ("reviewer-code", "claude-sonnet-5"): (1, 4000, 400, 0, 5000),
}

# A session started by pasting the hand-off, so never pinned: one request inside U1, one inside U2.
PASTED_SESSION = "f7f7f7f7-0000-4000-8000-000000000007"
PASTED_MAIN = (
    ("msg_p1", "claude-opus-5-5", "2026-09-22T10:50:00.000Z", 3000, 300, 30000, 0),  # U1
    ("msg_p2", "claude-opus-5-5", "2026-09-22T11:15:00.000Z", 5000, 500, 50000, 0),  # U2
)


class UnitWindowCase(SidecarCase):
    """Session f6f6…06 is pinned beside A and B; neither has a timestamp on 2026-09-22."""

    def setUp(self):
        super().setUp()
        self.unit_transcript = self.given_session(UNIT_SESSION, UNIT_MAIN, [("gate", UNIT_GATE_SIDECAR, meta_json("reviewer-gate"))])
        self.given_run(transcripts=[self.pin(EARLIER_SESSION), self.pin(ENDING_SESSION), self.pin(UNIT_SESSION)])

    def given_unit_events(self, events):
        """events.jsonl lines as session-state.py appends them: a unit event carries its unit id."""
        lines = [json.dumps(dict({"n": n, "at": at, "event": event, "machine": "unit" if unit else "session"},
                                 **({"unit": unit} if unit else {})))
                 for n, (at, event, unit) in enumerate(events, 1)]
        (self.run_dir / "events.jsonl").write_text("\n".join(lines) + "\n")

    def ledger_unit(self, unit_id, env=None):
        """run-cost.py --ledger --unit, as the Worker runs it at unit-close (worker/SKILL.md step 8)."""
        return subprocess.run([sys.executable, str(RUN_COST), "--run-dir", str(self.run_dir), "--ledger", "--unit", unit_id],
                              env=env or self.env, capture_output=True, text=True)

    def unit_records(self, unit_id):
        return [r for r in self.records()
                if r["scope"] == "unit" and r["unit_id"] == unit_id and r["session_dir"] == str(self.run_dir)]

    def facts(self, records):
        return {(r["role"], r["model"]): (r["requests"], r["input_tokens"], r["output_tokens"], r["cache_read_tokens"],
                                          r["cache_write_tokens"]) for r in records}


class UnitRecordTests(UnitWindowCase):
    def test_appends_one_unit_scope_record_per_role_and_model_inside_the_unit_s_window(self):
        """--by unit-id sums unit-scope records; a unit-close that appends none leaves the unit out of every per-unit report (U3 row; D3)."""
        self.given_unit_events(UNIT_EVENTS)

        done = self.ledger_unit("U1")

        self.assertEqual(done.returncode, 0, done.stderr)
        records = self.unit_records("U1")
        self.assertEqual(len(records), 2, records)
        self.assertEqual({(r["role"], r["model"]) for r in records},
                         {("worker", "claude-opus-5-5"), ("reviewer-code", "claude-sonnet-5")})

    def test_a_unit_record_names_its_unit_its_scope_its_source_and_the_session_its_requests_came_from(self):
        """A unit record is found by scope and unit_id and says who wrote it; a record without them is summed into the session-scope rollup and counted twice (§6; session id assumed Q2, source assumed Q3)."""
        self.given_unit_events(UNIT_EVENTS)
        self.assertEqual(self.ledger_unit("U1").returncode, 0)

        for record in self.unit_records("U1"):
            with self.subTest(role=record["role"]):
                self.assertEqual(
                    {k: record[k] for k in ("scope", "unit_id", "source", "project", "unit", "session_id", "session_dir")},
                    {"scope": "unit", "unit_id": "U1", "source": "unit-close", "project": "sample",
                     "unit": "sample-013-ledger", "session_id": UNIT_SESSION, "session_dir": str(self.run_dir)})

    def test_a_unit_record_counts_only_the_requests_inside_the_unit_s_window(self):
        """U1 is msg_u1 + msg_u2 and the reviewer-gate's msg_g1; the request before its start, the one after its close, U2's, and the other pinned sessions are someone else's cost (D10; the pinned set, assumed Q1)."""
        self.given_unit_events(UNIT_EVENTS)
        self.assertEqual(self.ledger_unit("U1").returncode, 0)

        self.assertEqual(self.facts(self.unit_records("U1")), U1_FACTS)

    def test_a_unit_record_counts_an_unpinned_session_s_requests_inside_the_window(self):
        """A session the launcher never pinned (a pasted hand-off) still spent inside U1; left out at the close, the unit's key is taken and that cost is lost for good (end-of-stack F1; D12's worktree project dir)."""
        self.given_unit_events(UNIT_EVENTS)
        self.given_session(PASTED_SESSION, PASTED_MAIN)
        self.assertEqual(self.ledger_unit("U1").returncode, 0)

        pasted = [r for r in self.unit_records("U1") if r["session_id"] == PASTED_SESSION]

        self.assertEqual(self.facts(pasted), {("worker", "claude-opus-5-5"): (1, 3000, 300, 30000, 0)})

    def test_a_unit_record_counts_a_pinned_session_outside_the_worktree_project_dir(self):
        """A pinned session that ran from another folder (a desktop scheduled task starts in its creator's) is still this unit's; reading the worktree dir alone drops it (end-of-stack re-review N3)."""
        self.given_unit_events(UNIT_EVENTS)
        elsewhere = self.home / ".claude/projects" / "-Users-owner-folders-sample"
        self.given_session(PASTED_SESSION, PASTED_MAIN, project_dir=elsewhere)
        self.given_run(transcripts=[self.pin(UNIT_SESSION), f"~/.claude/projects/{elsewhere.name}/{PASTED_SESSION}.jsonl"])
        self.assertEqual(self.ledger_unit("U1").returncode, 0)

        pinned = [r for r in self.unit_records("U1") if r["session_id"] == PASTED_SESSION]

        self.assertEqual(self.facts(pinned), {("worker", "claude-opus-5-5"): (1, 3000, 300, 30000, 0)})

    def test_a_unit_record_s_active_time_is_its_window_minus_a_stop_to_resume_gap(self):
        """U1 ran 10:00Z–11:00Z and was stopped 10:20Z–10:35Z, written at −05:00: wall 3600, active 2700 — time waiting on the Owner is not the unit's work (D10)."""
        self.given_unit_events(UNIT_EVENTS)
        self.assertEqual(self.ledger_unit("U1").returncode, 0)

        worker = self.by_role_and_model(self.unit_records("U1"))[("worker", "claude-opus-5-5")]

        self.assertEqual((worker["wall_seconds"], worker["active_seconds"]), (3600, 2700))

    def test_a_unit_recorded_through_a_symlinked_session_dir_is_not_recorded_again(self):
        """The launcher writes physical paths; a Lead reaching the same session dir through a symlink must not append U1 twice (U3 gate F2)."""
        self.given_unit_events(UNIT_EVENTS)
        link = self.root / "linked-sessions"
        link.symlink_to(self.sessions_root)
        self.assertEqual(self.ledger_unit("U1").returncode, 0)

        done = subprocess.run([sys.executable, str(RUN_COST), "--run-dir", str(link / self.run_dir.name), "--ledger", "--unit", "U1"],
                              env=self.env, capture_output=True, text=True)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len([r for r in self.records() if r["scope"] == "unit"]), 2)

    def test_the_first_unit_close_ends_the_window__when_the_log_closes_the_unit_twice(self):
        """A duplicated unit-close 4 s later must neither stretch U1 to 3604 s and take in msg_u3, nor make a second window with a second set of records (D10; Landmine: "the first close after a start wins")."""
        self.given_unit_events(UNIT_EVENTS_CLOSING_U1_TWICE)
        self.assertEqual(self.ledger_unit("U1").returncode, 0)

        records = self.unit_records("U1")

        self.assertEqual(len(records), 2, records)
        worker = self.by_role_and_model(records)[("worker", "claude-opus-5-5")]
        self.assertEqual((worker["requests"], worker["wall_seconds"]), (2, 3600))

    def test_a_second_call_for_the_same_unit_appends_nothing(self):
        """A retried unit-close step must not count the unit twice (U1 row's idempotency, carried to unit scope; assumed Q6)."""
        self.given_unit_events(UNIT_EVENTS)
        self.assertEqual(self.ledger_unit("U1").returncode, 0)
        before = self.ledger_path().read_bytes()

        done = self.ledger_unit("U1")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.ledger_path().read_bytes(), before)

    def test_refuses_and_appends_nothing__for_a_unit_that_has_not_closed(self):
        """A unit with no unit-close has no window; the Worker that asked is told, naming the unit, and the backfill records it once it closes (assumed Q5)."""
        self.given_unit_events(UNIT_EVENTS_U2_OPEN)

        done = self.ledger_unit("U2")

        self.assertNotEqual(done.returncode, 0)
        self.assertIn("U2", done.stderr)
        self.assertEqual(self.unit_records("U2"), [])


class BackfillTests(UnitWindowCase):
    def test_a_session_end_appends_the_records_of_every_closed_unit_that_has_none(self):
        """A unit-close whose --unit call never ran is recorded at the next session end — found in the pinned transcripts even when the ending session is another one, and once despite the duplicated close (U3 row; D10; assumed Q1)."""
        self.given_unit_events(UNIT_EVENTS_CLOSING_U1_TWICE)

        self.must_ledger()

        u1, u2 = self.unit_records("U1"), self.unit_records("U2")
        self.assertEqual(len(u1), 2, u1)
        self.assertEqual({(r["role"], r["model"]) for r in u1}, {("worker", "claude-opus-5-5"), ("reviewer-code", "claude-sonnet-5")})
        self.assertEqual([(r["role"], r["model"]) for r in u2], [("worker", "claude-opus-5-5")])

    def test_a_backfilled_unit_counts_an_unpinned_session_s_requests_inside_its_window(self):
        """The session-end catch-up takes the unit's key as the close would; an unpinned session left out here is left out for good (end-of-stack F1)."""
        self.given_unit_events(UNIT_EVENTS)
        self.given_session(PASTED_SESSION, PASTED_MAIN)

        self.must_ledger()

        pasted = [r for r in self.unit_records("U2") if r["session_id"] == PASTED_SESSION]
        self.assertEqual(self.facts(pasted), {("worker", "claude-opus-5-5"): (1, 5000, 500, 50000, 0)})

    def test_backfilled_unit_records_say_so_in_their_source(self):
        """A reader tells a unit recorded at its close from one caught up later by `source` (§6 enum; assumed Q3)."""
        self.given_unit_events(UNIT_EVENTS)

        self.must_ledger()

        self.assertEqual({r["source"] for r in self.unit_records("U1") + self.unit_records("U2")}, {"backfill"})

    def test_a_unit_already_recorded_at_its_close_is_not_appended_again(self):
        """Only the missing units are backfilled; a unit recorded at its close and again at the session end is counted twice by --by unit-id (U3 row: "missing"; assumed Q6)."""
        self.given_unit_events(UNIT_EVENTS)
        self.assertEqual(self.ledger_unit("U1").returncode, 0)

        self.must_ledger()

        u1 = self.unit_records("U1")
        self.assertEqual((len(u1), {r["source"] for r in u1}), (2, {"unit-close"}))
        self.assertEqual(len(self.unit_records("U2")), 1)

    def test_a_unit_still_open_gets_no_unit_record(self):
        """A unit started and not closed has no window yet; a record for it now would be a partial one the later close could not correct (D10; "any closed unit's")."""
        self.given_unit_events(UNIT_EVENTS_U2_OPEN)

        self.must_ledger()

        self.assertEqual(self.unit_records("U2"), [])
        self.assertEqual(len(self.unit_records("U1")), 2)

    def test_a_unit_recorded_for_another_session_dir_is_still_backfilled_for_this_one(self):
        """Every brief has a U1; another brief's U1 record is not this brief's (assumed Q6: keyed on session_dir and unit_id)."""
        self.given_unit_events(UNIT_EVENTS)
        foreign = dict({field: None for field in SECTION_6_FIELDS}, scope="unit", source="unit-close", project="demo",
                       unit="demo-002-intro", unit_id="U1", role="worker", model="claude-opus-5-5",
                       session_id="e8e8e8e8-0000-4000-8000-000000000008",
                       session_dir="/Users/owner/sessions/demo-002-intro", requests=1)
        self.ledger_path().write_text(json.dumps(foreign) + "\n")

        self.must_ledger()

        self.assertEqual(len(self.unit_records("U1")), 2)

    def test_the_session_end_hook_backfills_the_closed_units(self):
        """The SessionEnd hook is the call that runs at every Worker session's end, so it is where a missed unit-close is caught (U3 row: "the session-end call")."""
        self.given_unit_events(UNIT_EVENTS)
        cwd = self.root / "work"
        (cwd / ".claude").mkdir(parents=True)
        (cwd / ".claude/autonomous-run").write_text(f"{self.run_dir}\n")

        done = run_session_cost_hook(self.env, cwd, ENDING_SESSION, self.ending_transcript)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.unit_records("U1")), 2)


# ------------------------------------------------------------ U3 R7, R8 · the doc roles' sessions

PLANNER_SESSION = "c7c7c7c7-0000-4000-8000-000000000007"
# Claude Code's project dir for a doc role's folder; the hook passes the transcript path directly.
DOC_PROJECT_DIR = "-Users-owner-folders-demo"
PLANNER_MAIN = (
    ("msg_p1", "claude-opus-5-5", "2026-09-23T08:00:00.000Z", 1500, 150, 15000, 1500),
    ("msg_p2", "claude-opus-5-5", "2026-09-23T08:30:00.000Z", 2500, 250, 25000, 0),
)
PLANNER_REVIEWER = (("msg_r1", "claude-sonnet-5", "2026-09-23T08:10:00.000Z", 3500, 350, 35000, 3500),)
# 08:00Z → 08:30Z.
PLANNER_WINDOW_SECONDS = 1800


class DocRoleCase(SidecarCase):
    """A Planner session whose cwd is <scratch>/folders/demo, with one reviewer-docs sidecar, and no launch index unless a test writes one."""

    def setUp(self):
        super().setUp()
        self.doc_cwd = self.root / "folders" / "demo"
        self.doc_cwd.mkdir(parents=True)
        self.doc_projects = self.home / ".claude/projects" / DOC_PROJECT_DIR
        self.planner_transcript = self.given_session(PLANNER_SESSION, PLANNER_MAIN,
                                                     [("docs", PLANNER_REVIEWER, meta_json("reviewer-docs"))],
                                                     project_dir=self.doc_projects)

    def given_launch_index(self, *lines):
        (self.accounting_root / "launches.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))

    def index_line(self, **fields):
        return dict({"session_id": PLANNER_SESSION, "role": "planner", "project": "sample", "unit": "sample-013-ledger",
                     "session_dir": str(self.run_dir), "model": "opus", "at": "2026-09-23T02:59:00-05:00"}, **fields)

    def doc_ledger(self, role="planner", session_id=PLANNER_SESSION, transcript=None, env=None):
        """run-cost.py for a doc role: no run dir, the role the hook was registered with, and the session's cwd."""
        return subprocess.run(
            [sys.executable, str(RUN_COST), "--ledger", "--role", role, "--session-id", session_id,
             "--transcript", str(transcript or self.planner_transcript), "--cwd", str(self.doc_cwd)],
            env=env or self.env, capture_output=True, text=True)

    def must_doc_ledger(self, **kwargs):
        done = self.doc_ledger(**kwargs)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def planner_opus(self):
        return self.session_scope(PLANNER_SESSION)[("planner", "claude-opus-5-5")]


class DocRoleRecordTests(DocRoleCase):
    def test_a_doc_role_session_s_main_transcript_lands_under_its_role(self):
        """Planner, Lead and Explainer sessions are the cost no run.json ever saw; each lands under the role its hook names (Language: role bucket; the CLI, assumed Q15)."""
        for n, role in enumerate(("planner", "lead", "explainer"), 1):
            with self.subTest(role=role):
                session_id = f"c7c7c7c7-0000-4000-8000-{n:012d}"
                transcript = self.given_session(session_id, PLANNER_MAIN, project_dir=self.doc_projects)

                self.must_doc_ledger(role=role, session_id=session_id, transcript=transcript)

                self.assertEqual(set(self.session_scope(session_id)), {(role, "claude-opus-5-5")})

    def test_a_doc_role_record_names_the_cwd_basename_as_project_and_no_unit_or_session_dir(self):
        """With no launch index line the folder the session ran in is its project, and nothing claims a unit or session dir the session never had (U3 row; §6 "or null"; pinned false, assumed Q9)."""
        self.must_doc_ledger()

        record = self.planner_opus()

        self.assertEqual(
            {k: record[k] for k in ("scope", "source", "project", "unit", "unit_id", "session_id", "session_dir", "transcripts_pinned")},
            {"scope": "session", "source": "hook", "project": "demo", "unit": None, "unit_id": None,
             "session_id": PLANNER_SESSION, "session_dir": None, "transcripts_pinned": False})

    def test_a_doc_role_s_sidecar_lands_in_its_agent_type_s_bucket_under_the_same_session(self):
        """The Reviewer a Planner spawned is counted in the Planner's session and project, in its own bucket; the Planner's two opus requests stay the Planner's (D7; assumed Q8)."""
        self.must_doc_ledger()

        records = self.session_scope(PLANNER_SESSION)

        self.assertEqual({key: (r["requests"], r["input_tokens"], r["output_tokens"], r["cache_read_tokens"], r["cache_write_tokens"])
                          for key, r in records.items()}, {
            ("planner", "claude-opus-5-5"): (2, 4000, 400, 40000, 1500),
            ("reviewer-prose", "claude-sonnet-5"): (1, 3500, 350, 35000, 3500),
        })

    def test_a_doc_role_s_active_time_equals_its_wall_time(self):
        """A doc role has no events to subtract; 08:00Z–08:30Z is 1800 s of both (D10)."""
        self.must_doc_ledger()

        record = self.planner_opus()

        self.assertEqual((record["wall_seconds"], record["active_seconds"]), (PLANNER_WINDOW_SECONDS, PLANNER_WINDOW_SECONDS))

    def test_the_launch_index_line_for_the_session_supplies_its_project_unit_and_session_dir(self):
        """A launched Planner writing sample-013-ledger's brief belongs to that unit of work and project, which the folder name alone cannot say (D6; U3 row "or the launch index's line"; project from the line, assumed Q10)."""
        self.given_launch_index(self.index_line())

        self.must_doc_ledger()

        record = self.planner_opus()
        self.assertEqual((record["project"], record["unit"], record["session_dir"]), ("sample", "sample-013-ledger", str(self.run_dir)))

    def test_a_launch_index_line_for_another_session_changes_nothing(self):
        """Only the line for this session_id enriches it; another session's line would file this one under the wrong unit (U3 row: "for that session_id")."""
        self.given_launch_index(self.index_line(session_id="e8e8e8e8-0000-4000-8000-000000000008"))

        self.must_doc_ledger()

        record = self.planner_opus()
        self.assertEqual((record["project"], record["unit"], record["session_dir"]), ("demo", None, None))

    def test_the_role_comes_from_the_hook_argument__never_from_the_launch_index(self):
        """The launch index is an enrichment, never the marker: the hook's --role says what ended (D6; Language: launch index)."""
        self.given_launch_index(self.index_line(role="explainer"))

        self.must_doc_ledger()

        self.assertEqual({role for role, _ in self.session_scope(PLANNER_SESSION)}, {"planner", "reviewer-prose"})

    def test_a_doc_role_s_active_time_is_its_wall_time__even_when_its_indexed_session_dir_logs_a_stop(self):
        """A session dir's stop belongs to the Worker it stopped, not to a Planner the index ties to that dir (D10: "a doc role's active time equals its wall time")."""
        self.given_launch_index(self.index_line())
        self.given_events(("2026-09-23T03:05:00-05:00", "stop"), ("2026-09-23T03:20:00-05:00", "resume"))

        self.must_doc_ledger()

        self.assertEqual(self.planner_opus()["active_seconds"], PLANNER_WINDOW_SECONDS)

    def test_a_second_call_for_the_same_doc_role_session_appends_nothing(self):
        """A hook that fires twice for one session must not count it twice (U1 row: "a second call for the same session_id appends nothing")."""
        self.must_doc_ledger()
        before = self.ledger_path().read_bytes()

        self.must_doc_ledger()

        self.assertEqual(self.ledger_path().read_bytes(), before)


class DocRoleHookTests(DocRoleCase):
    def hook(self, *args, cwd=None, session_id=PLANNER_SESSION, transcript=None, env=None):
        return run_session_cost_hook(env or self.env, cwd or self.doc_cwd, session_id, transcript or self.planner_transcript, *args)

    def test_a_session_end_with_the_planner_role_and_no_marker_appends_a_planner_record_under_the_cwd_basename(self):
        """The doc-role skills register the hook with --role; that is the only marker a pasted Planner session has (U3 row; D6)."""
        done = self.hook("--role", "planner")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.planner_opus()["project"], "demo")

    def test_the_marker_wins_over_the_role_argument__and_the_worker_path_is_unchanged(self):
        """In an armed worktree the session is the Worker's whatever --role says; a planner record there moves the Worker's cost to another role and loses its session dir (hotspot: "the --role argument must not change the Worker path's result")."""
        armed = self.root / "work"
        (armed / ".claude").mkdir(parents=True)
        (armed / ".claude/autonomous-run").write_text(f"{self.run_dir}\n")

        done = self.hook("--role", "planner", cwd=armed, session_id=ENDING_SESSION, transcript=self.ending_transcript)

        self.assertEqual(done.returncode, 0, done.stderr)
        records = self.session_scope(ENDING_SESSION)
        self.assertEqual(set(records), {("worker", "claude-opus-5-5"), ("worker", "claude-sonnet-5"),
                                        ("subagent", "claude-haiku-4-5"), ("subagent", "claude-opus-5-5")})
        self.assertEqual({r["session_dir"] for r in records.values()}, {str(self.run_dir)})

    def test_a_session_end_with_no_marker_and_no_role_appends_nothing(self):
        """An ordinary session that invoked no doc-role skill is nobody's cost to record (Risk 2; pre-change behaviour; green before the unit exists)."""
        done = self.hook()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.records(), [])

    def test_a_session_end_with_a_role_outside_the_doc_roles_appends_nothing(self):
        """§6's role list is closed; a record under a role nobody defined is a row no report explains (assumed Q12)."""
        done = self.hook("--role", "wizard")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.records(), [])

    def test_a_doc_role_session_end_still_exits_0__when_the_ledger_cannot_be_written(self):
        """A session's end is never blocked by its accounting (hotspot: "it must still exit 0 on every path")."""
        not_a_dir = self.root / "not-a-dir"
        not_a_dir.write_text("a file where the accounting root should be\n")

        done = self.hook("--role", "planner", env=dict(self.env, ROBOWRIGHT_ACCOUNTING_ROOT=str(not_a_dir)))

        self.assertEqual(done.returncode, 0, done.stderr)


# ------------------------------------------------------------ U3 R9 · the doc-role skills register the hook

SKILLS = HERE.parents[1]


def session_end_commands(skill_md):
    """The `command:` values under `hooks:` → `SessionEnd:` in a SKILL.md's YAML frontmatter."""
    lines = skill_md.read_text().splitlines()
    front = lines[1:lines.index("---", 1)] if lines and lines[0] == "---" else []
    commands, inside = [], False
    for line in front:
        indent = len(line) - len(line.lstrip())
        if line.strip() == "SessionEnd:":
            inside = True
            continue
        if inside and line.strip() and indent <= 2:
            inside = False
        if inside and line.strip().startswith("command:"):
            commands.append(line.strip()[len("command:"):].strip().strip('"'))
    return commands


class FrontmatterHookTests(unittest.TestCase):
    def test_each_doc_role_skill_registers_the_session_cost_hook_with_its_role(self):
        """A skill's frontmatter hook is how a Planner, Lead or Explainer session's end reaches the ledger at all; without it, or with the wrong role, that role's rows never appear (U3 row; §2)."""
        for role in ("planner", "lead", "explainer"):
            with self.subTest(role=role):
                commands = session_end_commands(SKILLS / role / "SKILL.md")

                self.assertIn(f"bash $HOME/.claude/skills/worker/hooks/session-cost.sh --role {role}", commands)


# ------------------------------------------------------------ U3 R12 · the hook's LEDGER.md line (U2 gate N2)

class LedgerLineTests(LedgerCase):
    def setUp(self):
        super().setUp()
        self.given_run(spend_cap_usd=50)
        self.cwd = self.root / "work"
        (self.cwd / ".claude").mkdir(parents=True)
        (self.cwd / ".claude/autonomous-run").write_text(f"{self.run_dir}\n")

    def session_cost_line(self):
        lines = [line for line in (self.run_dir / "LEDGER.md").read_text().splitlines() if "session-cost" in line]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_the_ledger_md_line_shows_the_estimate_as_n_a__when_a_dollar_budget_meets_a_missing_pricing_file(self):
        """`est $null` reads as a malformed figure; an unpriced session under a dollar budget says n/a, as every other text report does (U2 gate N2; assumed Q22)."""
        env = dict(self.env, ROBOWRIGHT_PRICING_FILE=str(self.root / "nowhere" / "pricing.json"))

        done = run_session_cost_hook(env, self.cwd, ENDING_SESSION, self.ending_transcript)

        self.assertEqual(done.returncode, 0, done.stderr)
        line = self.session_cost_line()
        self.assertIn("est n/a", line)
        self.assertNotIn("null", line)

    def test_the_ledger_md_line_quotes_the_estimate__when_a_dollar_budget_meets_a_priced_session(self):
        """The n/a fix must not cost a priced session its figure: this fixture is $5.47 at the six rows (U2 row 17's oracle; pre-change behaviour; green before the unit exists)."""
        done = run_session_cost_hook(self.env, self.cwd, ENDING_SESSION, self.ending_transcript)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("est $5.47", self.session_cost_line())


if __name__ == "__main__":
    unittest.main()
