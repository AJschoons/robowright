#!/usr/bin/env python3
"""Tests for the plan-usage tap, the `claude-usage` reader and `usage-guard`, driven through their
command lines against scratch directories. Rows are named for `BEHAVIORS.md`; the kill for each
test is in `TEST-LEDGER.md`.

    python3 tests/usage/test_usage.py

Every path is overridden by env var, so nothing here reads or writes ~/.claude/usage or a real
Robowright Session.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TAP = REPO / "skills/robowright/scripts/usage-tap.py"
READER = REPO / "skills/robowright/scripts/claude-usage"
GUARD = REPO / "skills/robowright/scripts/usage-guard"

# 2100-01-01 00:00 UTC: a reset that never passes while these tests exist.
FAR_RESET = 4102444800
FAR_RESET_TEXT = "2100-01-01 00:00"
SIXTEEN_MINUTES = 16 * 60


class Scratch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.usage_dir = self.root / "usage"
        self.sessions = self.root / "sessions"
        self.usage_dir.mkdir()
        self.sessions.mkdir()
        self.latest = self.usage_dir / "latest.json"

    def tearDown(self):
        self._tmp.cleanup()

    def env(self):
        return {
            **os.environ,
            "CLAUDE_USAGE_DIR": str(self.usage_dir),
            "ROBOWRIGHT_SESSIONS_ROOT": str(self.sessions),
            "TZ": "UTC",
        }

    def run_tool(self, tool, *args, stdin=""):
        return subprocess.run(
            [sys.executable, str(tool), *args], input=stdin, capture_output=True, text=True,
            env=self.env(), timeout=20,
        )

    def write_latest(self, five_hour=None, seven_day=None, age_seconds=0):
        windows = {}
        if five_hour is not None:
            windows["five_hour"] = {"used_percentage": five_hour[0], "resets_at": five_hour[1]}
        if seven_day is not None:
            windows["seven_day"] = {"used_percentage": seven_day[0], "resets_at": seven_day[1]}
        record = {"captured_at": int(time.time()) - age_seconds, "session_id": "s-fixture", **windows}
        self.latest.write_text(json.dumps(record))

    def session(self, name, phase):
        path = self.sessions / name
        path.mkdir()
        (path / "run.json").write_text(json.dumps({"phase": phase}))
        return path


def status_input(session_id="s1", api_ms=2300, five_hour=None, seven_day=None, ctx=34,
                 model="Opus"):
    data = {
        "session_id": session_id,
        "model": {"id": "claude-opus-5", "display_name": model},
        "cost": {"total_api_duration_ms": api_ms},
        "context_window": {"used_percentage": ctx},
    }
    limits = {}
    if five_hour is not None:
        limits["five_hour"] = {"used_percentage": five_hour[0], "resets_at": five_hour[1]}
    if seven_day is not None:
        limits["seven_day"] = {"used_percentage": seven_day[0], "resets_at": seven_day[1]}
    if limits:
        data["rate_limits"] = limits
    return json.dumps(data)


class Tap(Scratch):
    def test_records_every_present_window_with_session_and_time(self):
        """T1.1 — the tap records both windows — the guard would read nothing."""
        result = self.run_tool(TAP, stdin=status_input(
            five_hour=(23.5, FAR_RESET), seven_day=(41.2, FAR_RESET - 1)))
        record = json.loads(self.latest.read_text())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(record["five_hour"], {"used_percentage": 23.5, "resets_at": FAR_RESET})
        self.assertEqual(record["seven_day"], {"used_percentage": 41.2, "resets_at": FAR_RESET - 1})
        self.assertEqual(record["session_id"], "s1")
        self.assertLess(abs(record["captured_at"] - time.time()), 5)

    def test_leaves_out_a_window_the_input_does_not_carry(self):
        """T1.2 — an absent window stays absent — a phantom window would be read as current."""
        self.run_tool(TAP, stdin=status_input(seven_day=(41.2, FAR_RESET)))
        record = json.loads(self.latest.read_text())
        self.assertNotIn("five_hour", record)
        self.assertEqual(record["seven_day"]["used_percentage"], 41.2)

    def test_leaves_the_previous_file_untouched_without_rate_limits(self):
        """T2.1 — no rate_limits keeps the last reading — a new session would erase it."""
        self.write_latest(five_hour=(50, FAR_RESET), age_seconds=60)
        before = self.latest.read_bytes()
        self.run_tool(TAP, stdin=status_input(session_id="s2"))
        self.assertEqual(self.latest.read_bytes(), before)

    def test_does_not_refresh_the_stamp_on_a_rerender_without_an_api_response(self):
        """T3.1 — a re-render keeps the old stamp — an idle session would pass stale numbers off as fresh."""
        self.run_tool(TAP, stdin=status_input(api_ms=2300, five_hour=(50, FAR_RESET)))
        self.write_latest(five_hour=(50, FAR_RESET), age_seconds=20 * 60)
        before = self.latest.read_bytes()
        self.run_tool(TAP, stdin=status_input(api_ms=2300, five_hour=(50, FAR_RESET)))
        self.assertEqual(self.latest.read_bytes(), before)

    def test_refreshes_the_stamp_after_a_new_api_response(self):
        """T3.2 — a new API response is recorded — the reading would go stale while work runs."""
        self.run_tool(TAP, stdin=status_input(api_ms=2300, five_hour=(50, FAR_RESET)))
        self.write_latest(five_hour=(50, FAR_RESET), age_seconds=20 * 60)
        self.run_tool(TAP, stdin=status_input(api_ms=2900, five_hour=(51, FAR_RESET)))
        record = json.loads(self.latest.read_text())
        self.assertLess(abs(record["captured_at"] - time.time()), 5)
        self.assertEqual(record["five_hour"]["used_percentage"], 51)

    def test_prints_model_context_and_both_windows_on_one_line(self):
        """T4.1 — the status line shows the four fields — the Owner loses the at-a-glance usage."""
        result = self.run_tool(TAP, stdin=status_input(
            five_hour=(23.5, FAR_RESET), seven_day=(41.2, FAR_RESET)))
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        for part in ("Opus", "34%", "5h 24%", "7d 41%"):
            self.assertIn(part, lines[0])

    def test_prints_dashes_for_absent_windows(self):
        """T4.2 — an absent window prints `--` — a blank or 0 reads as "no usage"."""
        result = self.run_tool(TAP, stdin=status_input())
        self.assertIn("5h --", result.stdout)
        self.assertIn("7d --", result.stdout)

    def test_exits_zero_quietly_on_input_that_is_not_json(self):
        """T5.1 — garbage in never errors — the status line goes blank or shows a traceback."""
        result = self.run_tool(TAP, stdin="{not json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertTrue(result.stdout.strip())
        self.assertFalse(self.latest.exists())

    def test_swallows_a_write_failure_and_still_prints(self):
        """T5.2 — an unwritable usage dir never errors — the status line goes blank."""
        self.usage_dir.rmdir()
        self.usage_dir.write_text("a file where the directory should be")
        result = self.run_tool(TAP, stdin=status_input(five_hour=(23.5, FAR_RESET)))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn("5h 24%", result.stdout)


class Reader(Scratch):
    def test_prints_percent_local_reset_time_and_age(self):
        """U1.1 — the text report carries pct, reset and age — the Lead cannot quote a window."""
        self.write_latest(five_hour=(23.5, FAR_RESET), age_seconds=120)
        result = self.run_tool(READER)
        self.assertEqual(result.returncode, 0)
        for part in ("23.5%", FAR_RESET_TEXT, "age"):
            self.assertIn(part, result.stdout)

    def test_json_carries_state_windows_and_age(self):
        """U2.1 — `--json` is machine-readable — scripts parse prose."""
        self.write_latest(five_hour=(23.5, FAR_RESET), age_seconds=120)
        report = json.loads(self.run_tool(READER, "--json").stdout)
        self.assertEqual(report["state"], "ok")
        self.assertEqual(report["windows"]["five_hour"]["used_percentage"], 23.5)
        self.assertIsInstance(report["age_seconds"], (int, float))

    def test_check_exit_codes_on_fresh_data(self):
        """U3.1–U3.3 — at or above the threshold in any window is over — the gate lets a launch through at the cap."""
        cases = [
            ("U3.1 at the threshold", (90.0, FAR_RESET), None, 1),
            ("U3.2 just under", (89.9, FAR_RESET), (10, FAR_RESET), 0),
            ("U3.3 weekly over", (10, FAR_RESET), (95, FAR_RESET), 1),
        ]
        for label, five_hour, seven_day, expected in cases:
            with self.subTest(label):
                self.write_latest(five_hour=five_hour, seven_day=seven_day)
                self.assertEqual(self.run_tool(READER, "--check", "90").returncode, expected)

    def test_stale_data_is_never_reported_as_under(self):
        """U4.1 — old data exits stale, not ok — a launch starts on a reading from before the burst."""
        self.write_latest(five_hour=(10, FAR_RESET), age_seconds=SIXTEEN_MINUTES)
        result = self.run_tool(READER, "--check", "90")
        self.assertEqual(result.returncode, 3)
        self.assertIn("stale", result.stdout)

    def test_stale_wins_over_over(self):
        """U4.2 — stale exits stale even above the threshold — callers act on a reading they cannot trust."""
        self.write_latest(five_hour=(95, FAR_RESET), age_seconds=SIXTEEN_MINUTES)
        self.assertEqual(self.run_tool(READER, "--check", "90").returncode, 3)

    def test_max_age_flag_widens_freshness(self):
        """U4.3 — `--max-age` sets the stale age in minutes — the flag is ignored."""
        self.write_latest(five_hour=(10, FAR_RESET), age_seconds=SIXTEEN_MINUTES)
        self.assertEqual(self.run_tool(READER, "--check", "90", "--max-age", "30").returncode, 0)

    def test_missing_file_exits_missing(self):
        """U5.1 — no file exits missing — a machine with no tap looks fine."""
        self.assertEqual(self.run_tool(READER, "--check", "90").returncode, 4)

    def test_unreadable_file_exits_missing(self):
        """U5.2 — a corrupt file exits missing — it crashes with a traceback instead."""
        self.latest.write_text("{not json")
        self.assertEqual(self.run_tool(READER).returncode, 4)

    def test_window_past_its_reset_is_not_counted(self):
        """U6.1 — a reset window no longer counts — a launch waits on a window that already reset."""
        self.write_latest(five_hour=(95, int(time.time()) - 60), seven_day=(40, FAR_RESET))
        self.assertEqual(self.run_tool(READER, "--check", "90").returncode, 0)

    def test_no_current_window_is_stale_not_ok(self):
        """U6.2 — every window reset exits stale — no data would be reported as under."""
        self.write_latest(five_hour=(40, int(time.time()) - 60))
        self.assertEqual(self.run_tool(READER, "--check", "90").returncode, 3)


class Guard(Scratch):
    def test_writes_stop_into_every_non_terminal_session(self):
        """G1.1 — STOP lands in live and stopped sessions, not done ones — a session runs past the cap."""
        self.write_latest(five_hour=(91, FAR_RESET))
        live = self.session("a-live", "implement")
        stopped = self.session("b-stopped", "stopped")
        done = self.session("c-done", "done")
        result = self.run_tool(GUARD, "--once")
        self.assertTrue((live / "STOP").exists())
        self.assertTrue((stopped / "STOP").exists())
        self.assertFalse((done / "STOP").exists())
        self.assertEqual(result.returncode, 1)

    def test_stop_is_one_line_naming_window_percent_and_reset(self):
        """G1.2 — the STOP line says why — the Lead has nothing to quote."""
        self.write_latest(five_hour=(91, FAR_RESET))
        live = self.session("a-live", "implement")
        self.run_tool(GUARD, "--once")
        lines = (live / "STOP").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        for part in ("five_hour", "91", FAR_RESET_TEXT):
            self.assertIn(part, lines[0])

    def test_stop_names_every_window_over_the_threshold(self):
        """G1.4 (held out) — both windows over are both named — the Lead schedules after the wrong reset."""
        self.write_latest(five_hour=(92, FAR_RESET), seven_day=(96, FAR_RESET - 3600))
        live = self.session("a-live", "implement")
        self.run_tool(GUARD, "--once")
        line = (live / "STOP").read_text()
        for part in ("five_hour", "92", "seven_day", "96", "2099-12-31 23:00"):
            self.assertIn(part, line)

    def test_at_the_threshold_writes_stop(self):
        """G1.3 — exactly 90% stops — the cap is exceeded before anything acts."""
        self.write_latest(five_hour=(90.0, FAR_RESET))
        live = self.session("a-live", "implement")
        self.run_tool(GUARD, "--once")
        self.assertTrue((live / "STOP").exists())

    def test_never_overwrites_an_existing_stop(self):
        """G2.1 — an existing STOP is kept — the Owner's reason is lost."""
        self.write_latest(five_hour=(95, FAR_RESET))
        live = self.session("a-live", "implement")
        (live / "STOP").write_text("the Owner's own\n")
        self.run_tool(GUARD, "--once")
        self.assertEqual((live / "STOP").read_text(), "the Owner's own\n")

    def test_under_the_threshold_writes_nothing(self):
        """G3.1 — under the cap writes nothing — sessions stop for no reason."""
        self.write_latest(five_hour=(89, FAR_RESET), seven_day=(50, FAR_RESET))
        live = self.session("a-live", "implement")
        result = self.run_tool(GUARD, "--once")
        self.assertFalse((live / "STOP").exists())
        self.assertEqual(result.returncode, 0)

    def test_threshold_flag_lowers_the_cap(self):
        """G3.2 — `--threshold` sets the cap — the Owner's ceiling is ignored."""
        self.write_latest(five_hour=(85, FAR_RESET))
        live = self.session("a-live", "implement")
        self.run_tool(GUARD, "--once", "--threshold", "80")
        self.assertTrue((live / "STOP").exists())

    def test_stale_data_writes_nothing_and_warns(self):
        """G4.1 — stale data never stops a session — a reading from before a reset stops live work."""
        self.write_latest(five_hour=(95, FAR_RESET), age_seconds=SIXTEEN_MINUTES)
        live = self.session("a-live", "implement")
        result = self.run_tool(GUARD, "--once")
        self.assertFalse((live / "STOP").exists())
        self.assertIn("stale", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 3)

    def test_missing_data_writes_nothing_and_warns(self):
        """G4.2 — no data never stops a session, and says so — silence reads as "under"."""
        live = self.session("a-live", "implement")
        result = self.run_tool(GUARD, "--once")
        self.assertFalse((live / "STOP").exists())
        self.assertIn("missing", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 4)

    def test_skips_a_directory_that_is_not_a_session(self):
        """G5.1 — a dir without run.json is left alone — stray folders collect STOP files."""
        self.write_latest(five_hour=(95, FAR_RESET))
        stray = self.sessions / "notes"
        stray.mkdir()
        self.run_tool(GUARD, "--once")
        self.assertFalse((stray / "STOP").exists())

    def test_watch_acts_when_usage_crosses_between_polls(self):
        """G6.1 — `--watch` re-reads each poll — a watch started under the cap never fires."""
        self.write_latest(five_hour=(50, FAR_RESET))
        live = self.session("a-live", "implement")
        watcher = subprocess.Popen(
            [sys.executable, str(GUARD), "--watch", "1"], env=self.env(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(1.5)
            self.assertFalse((live / "STOP").exists())
            self.write_latest(five_hour=(95, FAR_RESET))
            deadline = time.time() + 5
            while time.time() < deadline and not (live / "STOP").exists():
                time.sleep(0.2)
            self.assertTrue((live / "STOP").exists())
        finally:
            watcher.kill()
            watcher.wait()


# ------------------------------------------------------------------------------------------------
# The guard's sessions root is --runs-root (repeatable), else $ROBOWRIGHT_SESSIONS_ROOT, else
# `sessions_root` in ~/.claude/robowright/launch.json — never a built-in path; with none of them it
# refuses by name, exits 2 and writes no STOP. launch.json's root is read as the launcher reads it:
# a leading `~/` is $HOME followed by everything after the `~`, so `~//abs` is $HOME/abs; a bare `~`
# or a `~user/…` is read as written, against the cwd.

SESSION = "sample-001-x"
SESSION_ELSEWHERE = "sample-002-x"
# A user every macOS and Linux box has, so `~root/…` expanded would name a real home outside the scratch dirs.
OTHER_USER = "root"
# An old machine default the guard no longer reads (U1's `usage-guard:41` carried one), under the scratch HOME.
OLD_DEFAULT = Path("Projects/robowright-sessions")


class GuardSessionsRoot(Scratch):
    """G7–G8 · where the guard looks for sessions. A scratch HOME and cwd for every run;
    $ROBOWRIGHT_SESSIONS_ROOT only where a test sets it, since Scratch.env() sets it for every other test."""

    def setUp(self):
        super().setUp()
        # Resolved, so a path the guard builds from $HOME is the path the test looks at (macOS's temp
        # dir sits under /var, a link to /private/var).
        base = Path(os.path.realpath(self.root))
        self.base = base
        self.home = base / "home"
        self.home.mkdir()
        self.cwd = base / "cwd"
        self.cwd.mkdir()
        self.launch_json = self.home / ".claude" / "robowright" / "launch.json"
        self.env_root = None

    def env(self):
        env = {key: value for key, value in super().env().items() if key != "ROBOWRIGHT_SESSIONS_ROOT"}
        env["HOME"] = str(self.home)
        if self.env_root is not None:
            env["ROBOWRIGHT_SESSIONS_ROOT"] = self.env_root
        return env

    # ------------------------------------------------------------ given

    def given_session_at(self, root, name=SESSION):
        """A non-done session (phase implement) at <root>/<name>."""
        path = Path(root) / name
        path.mkdir(parents=True)
        (path / "run.json").write_text(json.dumps({"phase": "implement"}))
        return path

    def given_launch_settings(self, **settings):
        # Every install's launch.json carries `repos` (owner_git.py); the guards read past it.
        self.given_launch_json_text(json.dumps(dict({"repos": ["~/Code/sample"]}, **settings)) + "\n")

    def given_launch_json_text(self, text):
        self.launch_json.parent.mkdir(parents=True, exist_ok=True)
        self.launch_json.write_text(text)

    def given_usage_over(self, percent=95):
        self.write_latest(five_hour=(percent, FAR_RESET))

    # ------------------------------------------------------------ when

    def guard(self, *args, timeout=20):
        """usage-guard as a subprocess, from the scratch cwd under the scratch HOME."""
        return subprocess.run(
            [sys.executable, str(GUARD), *args], capture_output=True, text=True,
            env=self.env(), cwd=str(self.cwd), timeout=timeout,
        )

    # ------------------------------------------------------------ then

    def assertRefusedForSessionsRoot(self, done):
        """Exit 2 and one stderr line naming launch.json, $ROBOWRIGHT_SESSIONS_ROOT and --runs-root."""
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        lines = done.stderr.splitlines()
        self.assertEqual(len(lines), 1, done.stderr)
        line = lines[0]
        # The brief spells the file `~/.claude/robowright/launch.json`; spend-guard.py prints it expanded.
        self.assertTrue(
            any(name in line for name in ("~/.claude/robowright/launch.json", str(self.launch_json))),
            f"refusal does not name launch.json: {line}",
        )
        self.assertIn("ROBOWRIGHT_SESSIONS_ROOT", line)
        self.assertIn("--runs-root", line)

    def assertStopped(self, *sessions):
        for session in sessions:
            self.assertTrue((session / "STOP").exists(), f"no STOP in {session}")

    def assertNotStopped(self, *sessions):
        for session in sessions:
            self.assertFalse((session / "STOP").exists(), f"STOP written into {session}")

    # ------------------------------------------------------------ G7 · flag, else env, else launch.json, else refuse

    def test_guard_root__stops_only_under_the_runs_root_when_the_env_and_launch_json_name_other_roots(self):
        """G7.1 — --runs-root wins over the env and launch.json — a guard pointed at one root would STOP sessions under another."""
        self.given_usage_over()
        flagged = self.given_session_at(self.base / "flag-root")
        from_env = self.given_session_at(self.base / "env-root")
        from_file = self.given_session_at(self.home / "file-root")
        self.env_root = str(self.base / "env-root")
        self.given_launch_settings(sessions_root="~/file-root")

        self.guard("--once", "--runs-root", str(self.base / "flag-root"))

        self.assertStopped(flagged)
        self.assertNotStopped(from_env, from_file)

    def test_guard_root__stops_under_every_runs_root_given(self):
        """G7.2 — --runs-root is repeatable — a second root's sessions would run past the ceiling."""
        self.given_usage_over()
        first = self.given_session_at(self.base / "flag-root")
        second = self.given_session_at(self.base / "second-flag-root", SESSION_ELSEWHERE)

        self.guard("--once", "--runs-root", str(self.base / "flag-root"),
                   "--runs-root", str(self.base / "second-flag-root"))

        self.assertStopped(first, second)

    def test_guard_root__stops_under_the_env_root_and_not_the_launch_json_root_when_both_are_set(self):
        """G7.3 — the env root wins over launch.json — the Owner's override would be ignored."""
        self.given_usage_over()
        from_env = self.given_session_at(self.base / "env-root")
        from_file = self.given_session_at(self.home / "file-root")
        self.env_root = str(self.base / "env-root")
        self.given_launch_settings(sessions_root="~/file-root")

        self.guard("--once")

        self.assertStopped(from_env)
        self.assertNotStopped(from_file)

    def test_guard_root__stops_under_launch_json_s_sessions_root_with_no_flag_and_no_env(self):
        """G7.4 — launch.json's sessions_root is read — an install configured only there would never be enforced."""
        self.given_usage_over()
        from_file = self.given_session_at(self.base / "file-root")
        at_old_default = self.given_session_at(self.home / OLD_DEFAULT)
        self.given_launch_settings(sessions_root=str(self.base / "file-root"))

        self.guard("--once")

        self.assertStopped(from_file)
        self.assertNotStopped(at_old_default)

    def test_guard_root__reads_launch_json_when_the_env_root_is_empty(self):
        """G7.5 — an empty $ROBOWRIGHT_SESSIONS_ROOT is unset — it would be taken as the cwd, or hide launch.json."""
        self.given_usage_over()
        from_file = self.given_session_at(self.base / "file-root")
        in_cwd = self.given_session_at(self.cwd, SESSION_ELSEWHERE)
        self.env_root = ""
        self.given_launch_settings(sessions_root=str(self.base / "file-root"))

        self.guard("--once")

        self.assertStopped(from_file)
        self.assertNotStopped(in_cwd)

    def test_guard_root__refuses_by_name_and_writes_no_stop_with_nothing_configured_even_at_100_percent(self):
        """G7.6 — nothing configured is a named refusal that writes nothing — a built-in root would STOP one install's sessions on another's machine."""
        self.given_usage_over(100)
        at_old_default = self.given_session_at(self.home / OLD_DEFAULT)
        in_cwd = self.given_session_at(self.cwd, SESSION_ELSEWHERE)

        done = self.guard("--once")

        self.assertRefusedForSessionsRoot(done)
        self.assertNotStopped(at_old_default, in_cwd)

    def test_guard_root__refuses_by_name_when_the_env_root_is_empty_and_there_is_no_launch_json(self):
        """G7.7 — an empty env var configures nothing — it would be taken as the cwd and STOP what sits there."""
        self.given_usage_over(100)
        in_cwd = self.given_session_at(self.cwd)
        self.env_root = ""

        done = self.guard("--once")

        self.assertRefusedForSessionsRoot(done)
        self.assertNotStopped(in_cwd)

    def test_guard_root__refuses_by_name_when_sessions_root_is_an_empty_string(self):
        """G7.8 — an empty sessions_root is no root — it would be taken as the cwd and STOP what sits there."""
        self.given_usage_over(100)
        in_cwd = self.given_session_at(self.cwd)
        self.given_launch_settings(sessions_root="")

        done = self.guard("--once")

        self.assertRefusedForSessionsRoot(done)
        self.assertNotStopped(in_cwd)

    def test_guard_root__refuses_by_name_when_sessions_root_is_not_a_string(self):
        """G7.9 — a non-string sessions_root is no root — it would crash, or be read as a path it is not."""
        self.given_usage_over(100)
        in_cwd = self.given_session_at(self.cwd)
        for value in (5, ["~/x"], None, {"path": "~/x"}):
            with self.subTest(sessions_root=value):
                self.given_launch_settings(sessions_root=value)

                done = self.guard("--once")

                self.assertRefusedForSessionsRoot(done)
                self.assertNotStopped(in_cwd)

    def test_guard_root__refuses_by_name_when_launch_json_is_not_json(self):
        """G7.10 — a launch.json that does not parse names no root: a named refusal — a traceback, or a silent fallback, instead."""
        self.given_usage_over(100)
        in_cwd = self.given_session_at(self.cwd)
        self.given_launch_json_text('{"sessions_root": "~/x",\n')

        done = self.guard("--once")

        self.assertRefusedForSessionsRoot(done)
        self.assertNotStopped(in_cwd)

    def test_guard_root__refuses_by_name_when_launch_json_is_unreadable(self):
        """G7.14 — a launch.json that cannot be read names no root: a named refusal — a traceback instead (a directory stands in for an unreadable file)."""
        self.given_usage_over(100)
        in_cwd = self.given_session_at(self.cwd)
        self.launch_json.mkdir(parents=True)

        done = self.guard("--once")

        self.assertRefusedForSessionsRoot(done)
        self.assertNotStopped(in_cwd)

    def test_guard_root__refuses_by_name_when_launch_json_is_not_an_object(self):
        """G7.15 — a launch.json that is not an object has no sessions_root — `.get` on a list would crash."""
        self.given_usage_over(100)
        in_cwd = self.given_session_at(self.cwd)
        self.given_launch_json_text("[]\n")

        done = self.guard("--once")

        self.assertRefusedForSessionsRoot(done)
        self.assertNotStopped(in_cwd)

    def test_guard_root__watch_refuses_once_instead_of_polling_with_nothing_configured(self):
        """G7.11 — `--watch` refuses before its poll loop — it would spin forever enforcing nothing, or print the refusal every poll."""
        self.given_usage_over(100)
        try:
            done = self.guard("--watch", "1", timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("usage-guard --watch 1 was still running after 10 s with nothing configured")

        self.assertRefusedForSessionsRoot(done)

    def test_guard_root__a_launch_json_root_that_does_not_exist_is_no_sessions_and_no_traceback(self):
        """G7.12 — a configured root that is not there yet holds no sessions — the guard would crash on a fresh install.
        Guard: against `open_sessions` listing the root with `os.listdir`, which raises on a missing dir."""
        self.given_usage_over()
        self.given_launch_settings(sessions_root=str(self.base / "not-created-yet"))

        done = self.guard("--once")

        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)

    def test_guard_root__help_names_the_new_precedence_and_not_the_old_default(self):
        """G7.13 — --help says where the root comes from — the Owner would configure a path the guard no longer reads."""
        done = self.guard("--help")

        self.assertEqual(done.returncode, 0, done.stderr)
        for part in ("--runs-root", "ROBOWRIGHT_SESSIONS_ROOT", "launch.json", "sessions_root"):
            self.assertIn(part, done.stdout)
        self.assertNotIn(str(OLD_DEFAULT), done.stdout)

    # ------------------------------------------------------------ G8 · launch.json's root, read as the launcher reads it

    def test_guard_root__stops_under_home_abs_when_launch_json_names_tilde_double_slash_abs(self):
        """G8.1 — launch.json's `~//abs` is $HOME/abs, as the launcher reads it — joined as a path, `/abs` drops $HOME and the install's sessions run past the ceiling."""
        self.given_usage_over()
        under_home = self.given_session_at(self.home / "abs")
        self.given_launch_settings(sessions_root="~//abs")

        self.guard("--once")

        self.assertStopped(under_home)

    def test_guard_root__stops_under_home_abs_when_launch_json_names_tilde_abs(self):
        """G8.2 — launch.json's `~/abs` is $HOME/abs — the install's root would be missed, or a dir named `~` under the cwd read instead."""
        self.given_usage_over()
        under_home = self.given_session_at(self.home / "abs")
        unexpanded = self.given_session_at(self.cwd / "~" / "abs", SESSION_ELSEWHERE)
        self.given_launch_settings(sessions_root="~/abs")

        self.guard("--once")

        self.assertStopped(under_home)
        self.assertNotStopped(unexpanded)

    def test_guard_root__reads_a_bare_tilde_as_a_dir_named_tilde_under_the_cwd(self):
        """G8.3 — launch.json's bare `~` is read as written, as the launcher reads it — the guard would STOP sessions under $HOME the launcher never put there."""
        self.given_usage_over()
        in_home = self.given_session_at(self.home)
        as_written = self.given_session_at(self.cwd / "~", SESSION_ELSEWHERE)
        self.given_launch_settings(sessions_root="~")

        self.guard("--once")

        self.assertStopped(as_written)
        self.assertNotStopped(in_home)

    def test_guard_root__reads_tilde_user_abs_as_written_and_not_as_that_users_home(self):
        """G8.4 — launch.json's `~root/abs` is read as written — the guard would look in another user's home, where the launcher reads `<cwd>/~root/abs`."""
        self.given_usage_over()
        as_written = self.given_session_at(self.cwd / f"~{OTHER_USER}" / "abs")
        self.given_launch_settings(sessions_root=f"~{OTHER_USER}/abs")

        self.guard("--once")

        self.assertStopped(as_written)


if __name__ == "__main__":
    unittest.main()
