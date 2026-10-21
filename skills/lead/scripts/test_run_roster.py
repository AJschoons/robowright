#!/usr/bin/env python3
"""Tests for run-roster.py's verdicts, its terminal-session filter and layout, and spend-guard.py's phase filter.

    python3 skills/lead/scripts/test_run_roster.py

The roster is loaded as a module and describe(), visible() and render() are called directly with a
fixed `now`, on session dirs under a scratch sessions root — never a subprocess against the real one,
and never the real Claude projects tree (PROJECTS_ROOT is pointed at an empty scratch dir).
spend-guard.py has no seam short of main(), so its tests run it as a subprocess with --runs-root,
$ROBOWRIGHT_SESSIONS_ROOT and $HOME all pointed at scratch dirs. The parked: line's tests do the same with
run-roster.py, because the 48 h window is applied in main(); their ages are read off the wall clock.

Both scripts price through skills/robowright/scripts/pricing.py (U2 of the accounting brief). The
module pins $ROBOWRIGHT_PRICING_NOW for every test, so no output here turns stale with the real
date; the pricing suites below also name a synthetic pricing file through $ROBOWRIGHT_PRICING_FILE,
and every other test prices with the shipped one.
"""

import importlib.util
import io
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
GUARD = HERE / "spend-guard.py"
ROSTER_SCRIPT = HERE / "run-roster.py"


def load_roster():
    """run-roster.py's name is not importable; load it by path, as it loads session-state.py."""
    spec = importlib.util.spec_from_file_location("run_roster", HERE / "run-roster.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Before the roster is loaded: nothing this suite runs may warn that prices are stale because the
# real date moved on (U2; assumed Q2 names the variable).
os.environ.pop("ROBOWRIGHT_PRICING_FILE", None)
os.environ["ROBOWRIGHT_PRICING_NOW"] = "2026-09-26"

ROSTER = load_roster()
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
PARKED = "robowright-fixture-parked"
WORKING = "robowright-fixture-working"
DONE = "robowright-fixture-done"
REASON = "superseded by the 015 rebrief"
SESSION_ID = "bbbb2222"
ALL_DONE = [{"id": "U1", "status": "done"}, {"id": "U2", "status": "done"}]


def iso(dt):
    return dt.isoformat(timespec="seconds")


def hours_ago(hours):
    return NOW - timedelta(hours=hours)


class RosterCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "sessions"
        self.root.mkdir()
        projects = Path(tmp.name) / "projects"
        projects.mkdir()
        patch = mock.patch.object(ROSTER, "PROJECTS_ROOT", str(projects))
        patch.start()
        self.addCleanup(patch.stop)

    # ------------------------------------------------------------ given

    def given_run(self, name=WORKING, stop_file=False, **fields):
        """A session dir under the scratch root: implementing U2, started 3 h ago, last written 1 h ago, unless fields say otherwise."""
        run_dir = self.root / name
        run_dir.mkdir()
        run = {
            "ticket": name,
            "phase": "implement",
            "stop_reason": None,
            "rotate": None,
            "rebriefs": [],
            "session_id": SESSION_ID,
            "units": [{"id": "U1", "status": "done"}, {"id": "U2", "status": "todo"}],
            "started_at": iso(hours_ago(3)),
            "updated_at": iso(hours_ago(1)),
            "max_wall_hours": 12,
        }
        run.update(fields)
        (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        if stop_file:
            (run_dir / "STOP").write_text("")
        return str(run_dir), run

    def given_parked(self, stop_file=False, **fields):
        """A session the Owner parked from done an hour ago, with REASON."""
        values = {
            "phase": "parked",
            "parked": {"by": "owner", "reason": REASON, "at": iso(hours_ago(1)), "from": "done", "released": []},
            "units": ALL_DONE,
        }
        values.update(fields)
        return self.given_run(PARKED, stop_file=stop_file, **values)

    def live(self, status):
        """The Claude session registry holding one session for SESSION_ID, busy or idle."""
        return [{"sessionId": SESSION_ID, "name": "worker-opus-u2", "status": status, "cwd": "/nonexistent/worktree", "pid": 4242}]

    # ------------------------------------------------------------ when

    def describe(self, given, sessions=()):
        run_dir, run = given
        return ROSTER.describe(run_dir, run, list(sessions), NOW)

    def rendered(self, rows):
        out = io.StringIO()
        with redirect_stdout(out):
            ROSTER.render(rows, [])
        return out.getvalue().splitlines()


class ParkedVerdictTests(RosterCase):
    """R7 · a parked session reads as parked whatever its liveness."""

    def test_describe__parked_with_no_live_session_reads_parked_not_orphaned(self):
        """No live session still reads parked — the Lead would resume a session the Owner closed."""
        self.assertEqual(self.describe(self.given_parked(), sessions=[])["verdict"], "parked")

    def test_describe__parked_with_an_idle_live_session_reads_parked_not_stalled(self):
        """An idle live session still reads parked — the Lead would nudge a session the Owner closed."""
        self.assertEqual(self.describe(self.given_parked(), sessions=self.live("idle"))["verdict"], "parked")

    def test_describe__parked_with_a_busy_live_session_reads_parked_not_running(self):
        """A busy live session still reads parked — the verdict would follow liveness the Owner already overruled."""
        self.assertEqual(self.describe(self.given_parked(), sessions=self.live("busy"))["verdict"], "parked")

    def test_describe__parked_from_a_stop_reads_parked_not_stopped_code(self):
        """Parked from stopped:budget, mid-unit, reads parked — the Lead would route a stop the Owner already answered."""
        given = self.given_parked(
            parked={"by": "owner", "reason": REASON, "at": iso(hours_ago(1)), "from": "stopped:budget", "released": []},
            units=[{"id": "U1", "status": "done"}, {"id": "U2", "status": "building"}],
        )
        self.assertEqual(self.describe(given)["verdict"], "parked")

    def test_describe__parked_with_a_stop_file_reads_parked_not_stopping(self):
        """A STOP file beside a parked session does not make it stopping — parked is decided from stored state before any file or liveness check."""
        self.assertEqual(self.describe(self.given_parked(stop_file=True), sessions=self.live("busy"))["verdict"], "parked")

    def test_describe__parked_past_its_wall_hours_carries_no_liveness_flag(self):
        """A parked session 30 h into a 12 h wall and 5 h quiet gets no over-wall or quiet flag — the Lead would chase a session nobody is running."""
        given = self.given_parked(started_at=iso(hours_ago(30)), updated_at=iso(hours_ago(5)))
        row = self.describe(given, sessions=self.live("busy"))
        liveness_flags = [f for f in row["flags"] if f.startswith(("over-wall", "quiet"))]
        self.assertEqual((row["verdict"], liveness_flags), ("parked", []))

    def test_describe__parked_with_a_stop_reason_reads_invalid(self):
        """phase parked with a stop code set reads invalid:parked-and-stopped — an illegal state would pass for a parked one."""
        given = self.given_parked(stop_reason={"code": "budget", "detail": "x", "at": iso(hours_ago(2)), "phase_before": "implement"})
        self.assertEqual(self.describe(given)["verdict"], "invalid:parked-and-stopped")


class UnchangedVerdictTests(RosterCase):
    """R7 · every other verdict is unchanged by parked."""

    def test_describe__done_still_reads_done(self):
        """done with no live session reads done — parked's branch would have swallowed the other terminal phase."""
        self.assertEqual(self.describe(self.given_run(phase="done", units=ALL_DONE))["verdict"], "done")

    def test_describe__stopped_still_reads_its_stop_code(self):
        """stopped reads stopped:<code> — the Lead's routing table keys on the code."""
        given = self.given_run(phase="stopped", stop_reason={"code": "budget", "detail": "x", "at": iso(hours_ago(2)), "phase_before": "implement"})
        self.assertEqual(self.describe(given)["verdict"], "stopped:budget")

    def test_describe__a_stop_file_still_reads_stopping(self):
        """An unfinished session with a STOP file reads stopping, even while busy — the Lead would think the stop was ignored."""
        self.assertEqual(self.describe(self.given_run(stop_file=True), sessions=self.live("busy"))["verdict"], "stopping")

    def test_describe__a_pending_rotation_still_reads_rotating(self):
        """A requested rotation reads rotating, not orphaned — the Lead would resume instead of rotate."""
        given = self.given_run(rotate={"requested_at": iso(hours_ago(2)), "resumed_at": None, "next_unit": "U2"})
        self.assertEqual(self.describe(given)["verdict"], "rotating")

    def test_describe__unfinished_with_no_live_session_still_reads_orphaned(self):
        """Unfinished with no live session reads orphaned — the Lead would never resume a dead session."""
        self.assertEqual(self.describe(self.given_run(), sessions=[])["verdict"], "orphaned")

    def test_describe__unfinished_with_a_busy_session_still_reads_running(self):
        """A busy live session reads running — the Lead would interrupt working sessions."""
        self.assertEqual(self.describe(self.given_run(), sessions=self.live("busy"))["verdict"], "running")

    def test_describe__unfinished_with_an_idle_session_still_reads_stalled(self):
        """An idle live session reads stalled — the Lead would never nudge it."""
        self.assertEqual(self.describe(self.given_run(), sessions=self.live("idle"))["verdict"], "stalled")

    def test_describe__an_illegal_state_still_reads_invalid(self):
        """done with a stop code set reads invalid:done-and-stopped — an illegal state would pass for a plausible verdict."""
        given = self.given_run(phase="done", units=ALL_DONE, stop_reason={"code": "budget", "detail": "x", "at": iso(hours_ago(2)), "phase_before": "end-of-stack"})
        self.assertEqual(self.describe(given)["verdict"], "invalid:done-and-stopped")


class NeverLaunchedVerdictTests(RosterCase):
    """056-R rows (BEHAVIORS.md beside this file): a session folder nothing launched reads `briefed`; a preflight
    that runs or died keeps its verdict."""

    WORKTREE = "/nonexistent/briefed-worktree"

    def given_briefed(self, **fields):
        """WORKING as the Planner leaves it: preflight, no session id, no start time, no event log, both units todo."""
        values = {"phase": "preflight", "session_id": "", "started_at": "", "worktree": self.WORKTREE,
                  "units": [{"id": "U1", "status": "todo"}, {"id": "U2", "status": "todo"}]}
        values.update(fields)
        return self.given_run(**values)

    def test_describe__a_session_nothing_launched_reads_briefed_not_orphaned(self):
        """056-R1 — a brief nothing launched reads briefed — the Lead resumes a session that never started."""
        self.assertEqual(self.describe(self.given_briefed(), sessions=[])["verdict"], "briefed")

    def test_describe__a_briefed_session_with_a_busy_live_session_reads_running(self):
        """056-R2 — a live session in preflight reads running — the Lead lists a running preflight as waiting on a launch."""
        live = [{"sessionId": "cccc3333", "name": "worker-opus-u1", "status": "busy", "cwd": self.WORKTREE, "pid": 4242}]
        self.assertEqual(self.describe(self.given_briefed(), sessions=live)["verdict"], "running")

    def test_describe__a_briefed_session_the_launcher_pinned_reads_orphaned__when_no_session_is_live(self):
        """056-R3 — a launch that died in preflight reads orphaned — the Lead never resumes it (assumed Q1)."""
        self.assertEqual(self.describe(self.given_briefed(session_id=SESSION_ID), sessions=[])["verdict"], "orphaned")

    def test_describe__a_briefed_session_with_a_start_time_reads_orphaned__when_no_session_is_live(self):
        """056-R4 — a stamped start time with no live session reads orphaned — as R3 (assumed Q1)."""
        self.assertEqual(self.describe(self.given_briefed(started_at=iso(hours_ago(2))), sessions=[])["verdict"], "orphaned")

    def test_describe__a_registry_row_whose_cwd_is_not_a_string_matches_nothing(self):
        """056-R6 — a registry cwd that is not a string matches no worktree — the dashboard's page build dies on one bad row."""
        live = [{"sessionId": "cccc3333", "name": "someone", "status": "busy", "cwd": 1, "pid": 4242}]
        self.assertEqual(self.describe(self.given_briefed(), sessions=live)["verdict"], "briefed")

    def test_describe__a_registry_row_whose_cwd_holds_a_nul_matches_nothing(self):
        """056-R7 — a registry cwd holding a NUL matches no worktree — every dashboard card turns into an unreadable row."""
        live = [{"sessionId": "cccc3333", "name": "someone", "status": "busy", "cwd": self.WORKTREE + "\0", "pid": 4242}]
        self.assertEqual(self.describe(self.given_briefed(), sessions=live)["verdict"], "briefed")


class NeverLaunchedTickTests(RosterCase):
    """056-R5: a `--since` tick does not count a session nothing launched as unfinished work. run-roster.py runs as a
    subprocess with a scratch $HOME, so its registry is an empty <HOME>/.claude/sessions, never this Mac's."""

    def tick(self):
        home = self.root.parent / "home"
        env = dict(os.environ, HOME=str(home), ROBOWRIGHT_SESSIONS_ROOT=str(self.root))
        done = subprocess.run([sys.executable, str(ROSTER_SCRIPT), "--runs-root", str(self.root), "--no-lead",
                               "--since", str(self.root.parent / "roster-since.json")], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_roster__since_counts_no_unfinished_work__when_the_only_session_was_never_launched(self):
        """056-R5 — a brief waiting on its launch is not unfinished work — the Lead's quiet tick reports work it cannot act on."""
        wall = datetime.now(timezone.utc)
        self.given_run(phase="preflight", session_id="", started_at="", updated_at=iso(wall - timedelta(minutes=10)),
                       units=[{"id": "U1", "status": "todo"}])
        self.tick()
        self.assertIn("no change since last tick: 1 session(s), 0 unfinished", self.tick())


class FilterTests(RosterCase):
    """R7 · a parked session leaves the default roster after the 48 h window, like done and stopped."""

    def test_visible__hides_a_parked_session_quiet_past_the_48h_window(self):
        """Parked and last written 49 h ago is off the default roster — a parked session would show on every tick forever."""
        row = self.describe(self.given_parked(updated_at=iso(hours_ago(49))))
        self.assertFalse(ROSTER.visible(row, hours_ago(49), NOW))

    def test_visible__shows_a_parked_session_inside_the_48h_window(self):
        """Parked and last written 47 h ago is still listed — the Lead would lose sight of a park the moment it happened."""
        row = self.describe(self.given_parked(updated_at=iso(hours_ago(47))))
        self.assertTrue(ROSTER.visible(row, hours_ago(47), NOW))

    def test_visible__shows_an_old_parked_session_with_all(self):
        """--all lists a parked session however old — the full roster would hide the Owner's closed sessions."""
        row = self.describe(self.given_parked(updated_at=iso(hours_ago(49))))
        self.assertTrue(ROSTER.visible(row, hours_ago(49), NOW, show_all=True))

    def test_visible__still_shows_unfinished_work_however_old(self):
        """An unfinished session 49 h quiet stays listed — the window would hide the sessions most in need of the Lead."""
        row = self.describe(self.given_run(updated_at=iso(hours_ago(49))))
        self.assertTrue(ROSTER.visible(row, hours_ago(49), NOW))

    def test_visible__still_hides_an_old_done_session(self):
        """done and 49 h old is off the default roster — every finished session would stay listed."""
        row = self.describe(self.given_run(phase="done", units=ALL_DONE, updated_at=iso(hours_ago(49))))
        self.assertFalse(ROSTER.visible(row, hours_ago(49), NOW))


class RenderTests(RosterCase):
    """R7 · a parked session is printed on its own parked: line, outside the table."""

    def test_render__prints_a_parked_session_on_its_own_parked_line(self):
        """A parked row last written 1 h ago prints `parked: <run> · 1.0h · <reason>` — the Lead would not see why the session was left alone, or for how long (D4)."""
        lines = self.rendered([self.describe(self.given_parked())])
        self.assertIn(f"parked: {PARKED} · 1.0h · {REASON}", lines)

    def test_render__keeps_a_parked_session_out_of_the_table(self):
        """No table row names a parked session while unfinished ones stay in it — the table's columns describe work in motion and a parked row would read as work."""
        rows = [self.describe(self.given_run(), sessions=self.live("busy")), self.describe(self.given_parked())]
        table = [line for line in self.rendered(rows) if line.startswith("|")]
        self.assertTrue(any(WORKING in line for line in table))
        self.assertEqual([line for line in table if PARKED in line], [])



class UnitNameTests(RosterCase):
    """039 · the table names the session's plan unit as contract 11 does, then the brief's progress: `U12 (note-autosave) · 3/5`.
    The project folder sits under a scratch projects root; the session is mapped to its Task Breakdown row as the
    dashboard maps it."""

    THREE_OF_FIVE = [{"id": f"U{n}", "status": "done" if n <= 3 else "todo"} for n in range(1, 6)]

    def setUp(self):
        super().setUp()
        self.plans = self.root.parent / "plans"
        self.plans.mkdir()
        patch = mock.patch.object(ROSTER, "PLAN_ROOT", str(self.plans))
        patch.start()
        self.addCleanup(patch.stop)

    def given_plan(self, *rows):
        folder = self.plans / "sample"
        folder.mkdir()
        (folder / "PROJECT.md").write_text(
            "# Sample\n\n## Task Breakdown\n\n| # | Unit | Summary | Description | Size | Status |\n|---|---|---|---|---|---|\n"
            + "".join(row + "\n" for row in rows))

    def units_cell(self, name, **fields):
        row = self.describe(self.given_run(name, units=self.THREE_OF_FIVE, **fields), sessions=self.live("busy"))
        line = next(line for line in self.rendered([row]) if line.startswith(f"| {name} "))
        return line.split("|")[3].strip()

    def test_render__names_the_sessions_plan_unit_then_the_briefs_progress(self):
        """039-N1 — `sample-012-note-autosave`, row `U12 | sample-012-note-autosave`, 3 of 5 brief units done, prints `U12 (note-autosave) · 3/5` — the brief's own `U4` is not the plan's id, and a bare id makes the Owner look the number up (contract 11; U39 review 1 F2: the Owner chose to fix the roster label now)."""
        self.given_plan("| U11 | `sample-011-other` | Another unit. | x | S | todo |",
                        "| U12 | `sample-012-note-autosave` | Saves the note as you type. | x | M | in progress |")
        self.assertEqual(self.units_cell("sample-012-note-autosave"), "U12 (note-autosave) · 3/5")

    def test_render__prints_only_the_progress__when_no_plan_row_maps_the_session(self):
        """039-N2 — the same session with no project folder under the projects root prints `3/5` and no label — a brief-internal id printed as if it were the plan's would send the Owner to the wrong unit."""
        self.assertEqual(self.units_cell("sample-012-note-autosave"), "3/5")

    def test_render__names_a_tracker_key_unit_by_words_from_its_summary(self):
        """039-N3 — row `U7 | ENG-7 | Totals the sample's spend per unit.`, the session's run.json.ticket `ENG-7`, prints `U7 (Totals the sample's) · 3/5` — contract 11: "where the Unit cell is a tracker key, two or three words from its Summary"."""
        self.given_plan("| U7 | `ENG-7` | Totals the sample's spend per unit. | x | S | in progress |")
        self.assertEqual(self.units_cell("sample-007-totals", ticket="ENG-7"), "U7 (Totals the sample's) · 3/5")

    def test_render__prints_no_control_byte_from_the_plan__in_the_unit_label(self):
        """039-N4 — a Summary carrying ESC `[2J` and a BEL prints `U7 (Totals[2J the sample's) · 3/5`, no control byte — PROJECT.md is session-writable, and an escape sequence would reach the Lead's terminal (`session-inputs.md`)."""
        self.given_plan("| U7 | `ENG-7` | Totals\x1b[2J the\x07 sample's spend. | x | S | in progress |")
        self.assertEqual(self.units_cell("sample-007-totals", ticket="ENG-7"), "U7 (Totals[2J the sample's) · 3/5")


class SessionTextFenceTests(RosterCase):
    """SI-15 · the session-written text the roster prints is fenced as data for the Lead reading it."""

    FENCE = "  │ "

    def test_render__fences_session_written_text_as_data(self):
        """A session writes its ledger, HANDOFF.md and stop detail, and the Lead reads the roster before acting; each such line is quoted behind the fence, after a line saying it is data, with no control byte to redraw the terminal."""
        run_dir, run = self.given_run(stop_reason={"code": "budget", "detail": "first line\nsecond line", "at": iso(hours_ago(1)), "phase_before": "implement"}, phase="stopped")
        Path(run_dir, "LEDGER.md").write_text("## heading \x1b one\n")
        Path(run_dir, "HANDOFF.md").write_text("# Handoff\n\n## Where things stand\n\nstatus \x07 line\n")
        out = io.StringIO()
        with redirect_stdout(out):
            ROSTER.render([self.describe((run_dir, run))], [], tail=True)
        lines = out.getvalue().splitlines()
        session_lines = [line for line in lines if not line.startswith("|") and any(text in line for text in ("first line", "second line", "heading", "status"))]
        self.assertEqual(len(session_lines), 4, lines)
        for line in session_lines:
            self.assertTrue(line.startswith(self.FENCE), line)
        self.assertTrue(any("data" in line and "not instructions" in line for line in lines), lines)
        self.assertNotRegex(out.getvalue(), "[\x00-\x08\x0b-\x1f\x7f]")


class ParkedReasonFenceTests(RosterCase):
    """SI-15 · a parked session's reason is session-writable and prints on the roster's own parked: line."""

    def test_render__folds_a_parked_reason_onto_its_line_with_no_control_bytes(self):
        """A newline in the reason would start a line that reads as the roster's own (`lead: …`), and a control byte would reach the terminal; the reason stays on its parked: line, and the data label prints even when every row is parked."""
        given = self.given_parked(parked={"by": "owner", "reason": "why\nlead: fake \x07\u2028lead: also", "at": iso(hours_ago(1)), "from": "done", "released": []})
        lines = self.rendered([self.describe(given)])
        self.assertIn(f"parked: {PARKED} · 1.0h · why lead: fake  lead: also", lines)
        self.assertFalse(any(line.startswith("lead:") for line in lines), lines)
        self.assertFalse(any("\x07" in line for line in lines), lines)
        self.assertTrue(any("not instructions" in line for line in lines), lines)


class ParkedLineTests(RosterCase):
    """F4 · the default roster's parked: line lists every parked session with its age, whatever the 48 h window hides from the rows (D4, option A)."""

    def setUp(self):
        super().setUp()
        self.home = self.root.parent / "home"
        self.home.mkdir()

    # ------------------------------------------------------------ given

    def given_parked_quiet_for(self, hours):
        """PARKED, parked and last written `hours` ago by the wall clock — park writes both at once."""
        at = iso(datetime.now(timezone.utc) - timedelta(hours=hours))
        return self.given_parked(updated_at=at, parked={"by": "owner", "reason": REASON, "at": at, "from": "done", "released": []})

    def given_done_quiet_for(self, hours):
        """DONE, finished and last written `hours` ago by the wall clock."""
        return self.given_run(DONE, phase="done", units=ALL_DONE, updated_at=iso(datetime.now(timezone.utc) - timedelta(hours=hours)))

    # ------------------------------------------------------------ when

    def roster(self, *args):
        """run-roster.py over the scratch root, with a scratch $HOME: no live sessions, no transcripts, no triage, no lead line."""
        env = dict(os.environ, HOME=str(self.home), ROBOWRIGHT_SESSIONS_ROOT=str(self.root))
        done = subprocess.run([sys.executable, str(ROSTER_SCRIPT), "--runs-root", str(self.root), "--no-lead", *args],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    # ------------------------------------------------------------ then

    def test_roster__lists_a_parked_session_quiet_past_the_48h_window_on_its_parked_line_with_its_age(self):
        """Parked and last written 49 h ago still prints `parked: <run> · 2.0d · <reason>` — Monday's park is gone by Thursday and reads like a torn-down session (review F4)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.assertIn(f"parked: {PARKED} · 2.0d · {REASON}", self.roster().splitlines())

    def test_roster__lists_an_old_parked_session_when_it_is_the_only_session_on_disk(self):
        """With no row left to print, a parked session 49 h old still gets its parked: line — the reminder the park was for would vanish exactly when nothing else is on the roster."""
        self.given_parked_quiet_for(49)
        self.assertIn(f"parked: {PARKED} · 2.0d · {REASON}", self.roster().splitlines())

    def test_roster__prints_a_parked_session_inside_the_48h_window_on_one_parked_line(self):
        """A parked session 1 h old gets one parked: line, not two — it reaches the line through the rows and through the every-parked rule, and a doubled line reads as two parks."""
        self.given_run()
        self.given_parked_quiet_for(1)
        parked_lines = [line for line in self.roster().splitlines() if line.startswith(f"parked: {PARKED} ")]
        self.assertEqual(len(parked_lines), 1, parked_lines)

    def test_roster__still_leaves_out_a_done_session_quiet_past_the_48h_window(self):
        """done and 49 h old is on neither the table nor any line — the parked-line rule would bring every finished session back (R7, D4)."""
        self.given_run()
        self.given_done_quiet_for(49)
        self.assertNotIn(DONE, self.roster())

    def test_roster__json_still_leaves_out_a_parked_session_quiet_past_the_48h_window(self):
        """--json keeps its rows: a parked session 49 h old is not among them — the Lead's pre-launch dependency guard reads --json, and --only already shows every age (D4)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        runs = json.loads(self.roster("--json"))["runs"]
        self.assertEqual([r["run"] for r in runs], [WORKING])

    # ------------------------------------------------------------ --since keeps a parked session past the 48 h window (019 U1 · D3)

    def given_now_quiet_for(self, name, hours):
        """`name`'s run.json rewritten as last written `hours` ago by the wall clock (and parked then, if parked) — the passing of time between two ticks."""
        path = self.root / name / "run.json"
        run = json.loads(path.read_text())
        at = iso(datetime.now(timezone.utc) - timedelta(hours=hours))
        run["updated_at"] = at
        if run.get("parked"):
            run["parked"]["at"] = at
        path.write_text(json.dumps(run, indent=2) + "\n")

    def given_ledger_entry(self, name, heading):
        """A LEDGER.md entry headed `heading` appended to `name`'s session dir: its ledger head moves, nothing else does."""
        with open(self.root / name / "LEDGER.md", "a") as f:
            f.write(f"\n## {heading}\n- recorded by the test\n")

    def since_file(self):
        return self.root.parent / "roster-since.json"

    def tick(self):
        """One `--since` tick, every tick of a test on the same state file — the Lead's default tick."""
        return self.roster("--since", str(self.since_file()))

    def test_roster__since_prints_no_gone_line_for_a_parked_session_that_crosses_out_of_the_48h_window(self):
        """Parked 47 h ago at one tick and 49 h ago at the next, the session is still on disk and still parked; `no longer on the roster` tells the Lead it was torn down (D3 R1)."""
        self.given_run()
        self.given_parked_quiet_for(47)
        self.tick()
        self.given_now_quiet_for(PARKED, 49)

        out = self.tick()

        self.assertNotIn(f"{PARKED}: no longer on the roster", out)

    def test_roster__since_keeps_a_parked_session_that_crossed_the_48h_window_in_its_state_file(self):
        """A session dropped from the state file is never reported gone again, so removing its directory later would go unseen; it stays tracked on every later tick (D3 R2)."""
        self.given_run()
        self.given_parked_quiet_for(47)
        self.tick()
        self.given_now_quiet_for(PARKED, 49)
        self.tick()

        out = self.tick()

        self.assertIn(PARKED, json.loads(self.since_file().read_text())["runs"], out)
        self.assertNotIn(f"{PARKED}: no longer on the roster", out)

    def test_roster__since_reports_a_parked_session_inside_the_48h_window_gone_once_its_directory_is_removed(self):
        """Removing the directory is what `no longer on the roster` is for; keeping parked sessions must not silence it (D3 R3; green at red — owes its kill first)."""
        self.given_run()
        self.given_parked_quiet_for(1)
        self.tick()
        shutil.rmtree(self.root / PARKED)

        out = self.tick()

        self.assertIn(f"{PARKED}: no longer on the roster", out)

    def test_roster__since_reports_a_parked_session_past_the_48h_window_gone_once_its_directory_is_removed(self):
        """A parked session of any age is tracked, so its directory's removal is reported like any other; otherwise an old park vanishes from the roster without a line (D3 R3, "whatever the age")."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()
        shutil.rmtree(self.root / PARKED)

        out = self.tick()

        self.assertIn(f"{PARKED}: no longer on the roster", out)

    def test_roster__since_still_reports_a_done_session_gone_when_it_crosses_out_of_the_48h_window(self):
        """The fix is for parked sessions only; carrying done sessions past the window too would keep every finished session in the state file forever (D3 R4; green at red — owes its kill first)."""
        self.given_run()
        self.given_done_quiet_for(47)
        self.tick()
        self.given_now_quiet_for(DONE, 49)

        out = self.tick()

        self.assertIn(f"{DONE}: no longer on the roster", out)

    def test_roster__since_prints_the_parked_line_of_a_parked_session_past_the_48h_window_on_the_first_tick(self):
        """A session absent from the state file counts as changed, as an in-window parked session does on a fresh state file; otherwise an old park never reaches a --since Lead at all (D3 R5)."""
        self.given_run()
        self.given_parked_quiet_for(49)

        out = self.tick()

        self.assertIn(f"parked: {PARKED} · 2.0d · {REASON}", out.splitlines())

    def test_roster__since_prints_the_parked_line_of_a_parked_session_past_the_48h_window_when_its_ledger_head_changes(self):
        """A --since tick prints what changed, and a new ledger entry on an old parked session is a change; dropping it hides the Owner's note on the park (D3 R5)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()
        self.given_ledger_entry(PARKED, "2026-09-22 20:00 — Owner note: stays parked until the release")

        out = self.tick()

        self.assertIn(f"parked: {PARKED} · 2.0d · {REASON}", out.splitlines())

    def test_roster__since_prints_no_parked_line_for_an_unchanged_parked_session_past_the_48h_window(self):
        """A --since tick prints only what changed; a parked: line on every tick where another session moved is the noise --since exists to remove (D3 R5; green at red — owes its kill first)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()
        self.given_ledger_entry(WORKING, "2026-09-22 20:00 — U2 gate READY")

        out = self.tick()

        self.assertIn(WORKING, out)
        self.assertNotIn(f"parked: {PARKED}", out)

    # ------------------------------------------------------------ output on a quiet or parked-only tick (020 U3 · D7)

    def json_tick(self):
        """One `--since --json` tick, on the same state file as tick()."""
        return json.loads(self.roster("--since", str(self.since_file()), "--json"))

    def test_roster__since_prints_no_no_match_line_above_the_parked_line_of_a_changed_parked_session_past_the_48h_window(self):
        """Only a parked session 49 h old changed while a live session sat unchanged; `no Robowright Sessions match` above its parked: line tells the Lead the live session is gone (D7 R1, 019 F1)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()
        self.given_ledger_entry(PARKED, "2026-09-22 20:00 — Owner note: stays parked until the release")

        out = self.tick()

        self.assertNotIn("no Robowright Sessions match", out)

    def test_roster__since_prints_no_table_header_above_the_parked_line_of_a_changed_parked_session_past_the_48h_window(self):
        """Only a parked session 49 h old changed; a column-header row over zero rows reads as a roster that emptied (D7 R2, 019 F1)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()
        self.given_ledger_entry(PARKED, "2026-09-22 20:00 — Owner note: stays parked until the release")

        out = self.tick()

        self.assertEqual([line for line in out.splitlines() if line.startswith("|")], [])

    def test_roster__since_prints_no_no_match_line_on_a_tick_where_the_only_change_is_a_removed_session(self):
        """A done session's directory was removed and the live session is unchanged; `no Robowright Sessions match` under the gone line says the live one went too (D7 R1)."""
        self.given_run()
        self.given_done_quiet_for(1)
        self.tick()
        shutil.rmtree(self.root / DONE)

        out = self.tick()

        self.assertNotIn("no Robowright Sessions match", out)

    def test_roster__since_prints_no_table_header_on_a_tick_where_the_only_change_is_a_removed_session(self):
        """A gone-only tick has no row to show; an empty table under the gone line is noise on the tick --since exists to keep short (D7 R2)."""
        self.given_run()
        self.given_done_quiet_for(1)
        self.tick()
        shutil.rmtree(self.root / DONE)

        out = self.tick()

        self.assertEqual([line for line in out.splitlines() if line.startswith("|")], [])

    def test_roster__prints_no_no_match_line_when_the_only_session_on_disk_is_parked_past_the_48h_window(self):
        """The plain roster with one parked session 49 h old prints its parked: line; `no Robowright Sessions match` above it contradicts the line under it (D7 R1)."""
        self.given_parked_quiet_for(49)

        out = self.roster()

        self.assertNotIn("no Robowright Sessions match", out)

    def test_roster__prints_no_table_header_when_the_only_session_on_disk_is_parked_past_the_48h_window(self):
        """The plain roster with one parked session 49 h old has no row; a column-header row over nothing reads as a roster that emptied (D7 R2)."""
        self.given_parked_quiet_for(49)

        out = self.roster()

        self.assertEqual([line for line in out.splitlines() if line.startswith("|")], [])

    def test_roster__prints_no_table_header_when_the_only_session_on_disk_is_parked_inside_the_48h_window(self):
        """A parked session 1 h old prints on its parked: line, outside the table; the header over zero table rows is the same empty table (D7 R2; assumed Q1)."""
        self.given_parked_quiet_for(1)

        out = self.roster()

        self.assertEqual([line for line in out.splitlines() if line.startswith("|")], [])

    def test_roster__still_prints_the_no_match_line_when_no_session_is_on_disk(self):
        """With nothing on disk the header is the whole answer; losing it leaves the Lead an empty output that reads as a crash (D7 R1; green at red — owes its kill first)."""
        out = self.roster()

        self.assertIn("no Robowright Sessions match", out.splitlines())

    def test_roster__prints_no_no_match_line_above_a_table_row(self):
        """One live session is one table row; `no Robowright Sessions match` above it contradicts the row under it (D7 R1)."""
        self.given_run()

        out = self.roster()

        self.assertNotIn("no Robowright Sessions match", out)

    def test_roster__prints_no_table_header_under_the_no_match_line_when_no_session_is_on_disk(self):
        """No session means zero rows, and a column-header row over zero rows is what D7 removes (D7 R2)."""
        out = self.roster()

        self.assertEqual([line for line in out.splitlines() if line.startswith("|")], [])

    def test_roster__since_json_lists_a_changed_parked_session_past_the_48h_window_under_parked(self):
        """The text tick prints this change as a parked: line and the state file consumes it; `--since --json` returning nothing loses the change for good (D7 R3, 019 F2)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()
        self.given_ledger_entry(PARKED, "2026-09-22 20:00 — Owner note: stays parked until the release")

        out = self.json_tick()

        self.assertEqual([r["run"] for r in out.get("parked", [])], [PARKED])

    def test_roster__since_json_keeps_a_changed_parked_session_past_the_48h_window_out_of_runs(self):
        """`runs` is unchanged by D7; a parked session 49 h old in it would reach the pre-launch dependency guard that reads --json (D7 R3; green at red — owes its kill first)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()
        self.given_ledger_entry(PARKED, "2026-09-22 20:00 — Owner note: stays parked until the release")

        out = self.json_tick()

        self.assertEqual(out["runs"], [])

    def test_roster__since_json_leaves_an_unchanged_parked_session_past_the_48h_window_out_of_parked(self):
        """Under --since, `parked` holds only what changed, as the parked: lines do; listing the unchanged park on every tick is the noise --since removes (D7 R3; green at red — owes its kill first)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()
        self.given_ledger_entry(WORKING, "2026-09-22 20:00 — U2 gate READY")

        out = self.json_tick()

        self.assertEqual([r["run"] for r in out.get("parked", [])], [])

    def test_roster__json_lists_a_parked_session_past_the_48h_window_under_parked(self):
        """The text roster prints a parked session 49 h old on its parked: line; --json not listing it anywhere hides a park the text form shows (D7 R3)."""
        self.given_run()
        self.given_parked_quiet_for(49)

        out = json.loads(self.roster("--json"))

        self.assertEqual([r["run"] for r in out.get("parked", [])], [PARKED])

    def test_roster__json_leaves_a_parked_session_inside_the_48h_window_out_of_parked(self):
        """A parked session 1 h old is already in `runs`; listing it under `parked` as well makes a --json reader count one park twice (D7 R3; green at red — owes its kill first)."""
        self.given_run()
        self.given_parked_quiet_for(1)

        out = json.loads(self.roster("--json"))

        self.assertEqual([r["run"] for r in out.get("parked", [])], [])

    def test_roster__json_carries_an_empty_parked_list_when_no_session_is_parked(self):
        """`runs`, `lead` and `triage` are always present; a `parked` key that appears only sometimes makes every reader guard for it (D7 R3; assumed Q2)."""
        self.given_run()

        out = json.loads(self.roster("--json"))

        self.assertEqual(out.get("parked"), [])

    def test_roster__since_no_change_line_leaves_a_parked_session_past_the_48h_window_out_of_its_count(self):
        """The quiet tick counts the rows the roster shows; counting a parked session 49 h old reports a session the table would not show (D7 R4; green at red — owes its kill first)."""
        self.given_run()
        self.given_parked_quiet_for(49)
        self.tick()

        out = self.tick()

        self.assertEqual(out.splitlines(), ["no change since last tick: 1 session(s), 1 unfinished"])

class SpendGuardTests(unittest.TestCase):
    """R8 · spend-guard.py skips a parked session unless --only names it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root = base / "sessions"
        self.home = base / "home"
        self.home.mkdir()
        self.given_session(PARKED, phase="parked", units=ALL_DONE,
                           parked={"by": "owner", "reason": REASON, "at": "2026-09-22T11:00:00+00:00", "from": "done", "released": []})
        self.given_session(WORKING, phase="implement", units=[{"id": "U1", "status": "todo"}])

    def given_session(self, name, **fields):
        """A session dir with a $50 cap, so only its phase can keep spend-guard from polling it."""
        run_dir = self.root / name
        run_dir.mkdir(parents=True)
        run = {"ticket": name, "spend_cap_usd": 50, "spend_threshold_usd": 40}
        run.update(fields)
        (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")

    def polled(self, *args):
        """The session names one --json --dry-run pass reports."""
        env = dict(os.environ, HOME=str(self.home), ROBOWRIGHT_SESSIONS_ROOT=str(self.root))
        done = subprocess.run([sys.executable, str(GUARD), "--runs-root", str(self.root), "--json", "--dry-run", *args],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return [row["run"] for row in json.loads(done.stdout)]

    def test_spend_guard__skips_a_parked_session(self):
        """A parked session is not polled — its transcripts would keep being summed and a stale cap could write STOP into it."""
        self.assertEqual(self.polled(), [WORKING])

    def test_spend_guard__polls_a_parked_session_only_names(self):
        """--only naming a parked session still polls it — the Owner could not check what a parked session spent."""
        self.assertEqual(self.polled("--only", PARKED), [PARKED])


class RegistryStatusTests(RosterCase):
    """D3 R1–R4, R6 · the registry status decides running or stalled: busy and shell run, waiting runs with `dialog`, idle stalls, anything else stalls with `registry <value>`."""

    # ------------------------------------------------------------ given

    def live_without_status(self):
        """The Claude session registry holding one session for SESSION_ID whose record has no `status` key."""
        return [{"sessionId": SESSION_ID, "name": "worker-opus-u2", "cwd": "/nonexistent/worktree", "pid": 4242}]

    # ------------------------------------------------------------ then

    def registry_flags(self, row):
        """The row's flags that D3 derives from the registry status: `dialog` and `registry <value>`, in the row's order."""
        return [f for f in row["flags"] if f == "dialog" or f.startswith("registry ")]

    # ------------------------------------------------------------ R1 · busy and shell read running, with no new flag

    def test_describe__unfinished_with_a_shell_session_reads_running(self):
        """A session idle while its background task runs is working and is re-invoked when the task exits; reading it stalled sends the Lead's nudge into a Worker mid-xcodebuild (D3 R1, F13)."""
        self.assertEqual(self.describe(self.given_run(), sessions=self.live("shell"))["verdict"], "running")

    def test_describe__a_shell_session_carries_neither_dialog_nor_a_registry_flag(self):
        """shell is a known working status, so it adds no flag; a `dialog` on it sends the Owner to a dialog that is not there (D3 R1; green at red — owes its kill first)."""
        self.assertEqual(self.registry_flags(self.describe(self.given_run(), sessions=self.live("shell"))), [])

    def test_describe__a_busy_session_carries_neither_dialog_nor_a_registry_flag(self):
        """busy is a known working status, so it adds no flag; a `dialog` on a turn in progress sends the Owner to a dialog that is not there (D3 R1; green at red — owes its kill first)."""
        self.assertEqual(self.registry_flags(self.describe(self.given_run(), sessions=self.live("busy"))), [])

    # ------------------------------------------------------------ R2 · waiting reads running with the dialog flag

    def test_describe__unfinished_with_a_waiting_session_reads_running(self):
        """A session held on a dialog stays a live holder as running; any other verdict must be added to every live-holder list, and a list that missed it lets another session steal its lock (D3 R2)."""
        self.assertEqual(self.describe(self.given_run(), sessions=self.live("waiting"))["verdict"], "running")

    def test_describe__a_waiting_session_carries_the_dialog_flag_and_no_registry_flag(self):
        """`dialog` is how the Lead tells a session blocked on the Owner's dialog from one at work; without it the Lead nudges a session that cannot act on a nudge (D3 R2)."""
        self.assertEqual(self.registry_flags(self.describe(self.given_run(), sessions=self.live("waiting"))), ["dialog"])

    # ------------------------------------------------------------ R3 · idle reads stalled, as today, with no new flag

    def test_describe__an_idle_session_carries_no_registry_flag(self):
        """idle is the known stalled status, so it gets no `registry idle`; with the flag every ordinary stall reads as an unknown status and is reported to the Owner instead of nudged (D3 R3; green at red — owes its kill first)."""
        self.assertEqual(self.registry_flags(self.describe(self.given_run(), sessions=self.live("idle"))), [])

    # ------------------------------------------------------------ R4 · any other status, or none, reads stalled and names it

    def test_describe__unfinished_with_an_unknown_registry_status_reads_stalled(self):
        """A status this roster does not know is not evidence of work; reading `sleeping` as running hides a session that may be stuck (D3 R4; green at red — owes its kill first)."""
        self.assertEqual(self.describe(self.given_run(), sessions=self.live("sleeping"))["verdict"], "stalled")

    def test_describe__an_unknown_registry_status_carries_a_registry_flag_naming_it(self):
        """`registry sleeping` tells the Lead why the row is stalled before it nudges; without it a status a later Claude Code adds re-creates F13 unnoticed (D3 R4)."""
        self.assertEqual(self.registry_flags(self.describe(self.given_run(), sessions=self.live("sleeping"))), ["registry sleeping"])

    def test_describe__unfinished_with_a_registry_record_with_no_status_reads_stalled(self):
        """A record with no status is not evidence of work; reading it as running hides a session that may be stuck (D3 R4; green at red — owes its kill first)."""
        self.assertEqual(self.describe(self.given_run(), sessions=self.live_without_status())["verdict"], "stalled")

    def test_describe__a_registry_record_with_no_status_carries_registry_none(self):
        """`registry none` tells the Lead the registry gave no status at all; without it the row reads as an ordinary idle stall and gets a nudge (D3 R4)."""
        self.assertEqual(self.registry_flags(self.describe(self.given_run(), sessions=self.live_without_status())), ["registry none"])

    # ------------------------------------------------------------ R6 · quiet keeps its rule on R1 and R2 rows

    def test_describe__a_shell_session_last_written_10h_ago_carries_the_quiet_flag(self):
        """A running row not written for 10 h is quiet whatever the registry says; a shell row without it hides a background task that has run for hours (D3 R6)."""
        row = self.describe(self.given_run(started_at=iso(hours_ago(11)), updated_at=iso(hours_ago(10))), sessions=self.live("shell"))
        self.assertTrue([f for f in row["flags"] if f.startswith("quiet ")], row["flags"])

    def test_describe__a_waiting_session_last_written_10h_ago_carries_the_quiet_flag(self):
        """A running row not written for 10 h is quiet whatever the registry says; a waiting row without it hides how long the Owner's dialog has sat unanswered (D3 R6)."""
        row = self.describe(self.given_run(started_at=iso(hours_ago(11)), updated_at=iso(hours_ago(10))), sessions=self.live("waiting"))
        self.assertTrue([f for f in row["flags"] if f.startswith("quiet ")], row["flags"])


class RegistryStatusPrecedenceTests(RosterCase):
    """D3 R5 · a STOP file or a pending rotation decides the verdict before the registry status is read."""

    def test_describe__a_stop_file_still_reads_stopping_while_the_session_waits_on_a_dialog(self):
        """An unfinished session with a STOP file reads stopping even while held on a dialog; reading it running tells the Lead the stop was never asked for (D3 R5; green at red — owes its kill first)."""
        self.assertEqual(self.describe(self.given_run(stop_file=True), sessions=self.live("waiting"))["verdict"], "stopping")

    def test_describe__a_pending_rotation_still_reads_rotating_while_the_session_waits_on_a_dialog(self):
        """A requested rotation reads rotating even while the old session sits on a dialog; reading it running means the Lead never rotates (D3 R5; green at red — owes its kill first)."""
        given = self.given_run(rotate={"requested_at": iso(hours_ago(2)), "resumed_at": None, "next_unit": "U2"})
        self.assertEqual(self.describe(given, sessions=self.live("waiting"))["verdict"], "rotating")


class RotatingAndStoppingFlagTests(RosterCase):
    """028 D3 R1, R4 · a rotating row past its wall carries `over-wall`; a rotating or stopping row never carries `dialog` (024 D3 R5 unchanged)."""

    # ------------------------------------------------------------ given

    def given_rotating(self, **fields):
        """An unfinished session whose rotation was requested 2 h ago and has not resumed, next unit U2."""
        return self.given_run(rotate={"requested_at": iso(hours_ago(2)), "resumed_at": None, "next_unit": "U2"}, **fields)

    # ------------------------------------------------------------ then

    def over_wall_flags(self, row):
        """The row's `over-wall …` flags."""
        return [f for f in row["flags"] if f.startswith("over-wall")]

    def dialog_flags(self, row):
        """The row's `dialog` flags."""
        return [f for f in row["flags"] if f == "dialog"]

    # ------------------------------------------------------------ R1 · a rotating row past its wall carries over-wall

    def test_describe__a_rotating_session_started_3h_ago_on_a_2h_wall_carries_the_over_wall_flag(self):
        """A rotating session 3 h into a 2 h wall is flagged over-wall; without it a rotation stuck behind a dialog holds its locks to the wall unseen (028 D3 R1)."""
        row = self.describe(self.given_rotating(started_at=iso(hours_ago(3)), max_wall_hours=2), sessions=self.live("busy"))
        self.assertEqual((row["verdict"], len(self.over_wall_flags(row))), ("rotating", 1))

    def test_describe__a_rotating_session_started_1h_ago_on_a_2h_wall_carries_no_over_wall_flag(self):
        """A rotating session 1 h into a 2 h wall is not over-wall; flagging every rotating row sends the Lead after rotations that are on time (028 D3 R1; green at red — owes its kill first)."""
        row = self.describe(self.given_rotating(started_at=iso(hours_ago(1)), max_wall_hours=2), sessions=self.live("busy"))
        self.assertEqual((row["verdict"], self.over_wall_flags(row)), ("rotating", []))

    # ------------------------------------------------------------ R4 · no dialog on a rotating or stopping row

    def test_describe__a_rotating_session_waiting_on_a_dialog_carries_no_dialog_flag(self):
        """Declared guard, green at the tip before U3: a rotating row whose session is waiting carries no `dialog`. It guards the defect of widening `dialog` past running rows, the full route the Owner passed over, which reverses 024 D3 R5 (028 D3 R4)."""
        row = self.describe(self.given_rotating(), sessions=self.live("waiting"))
        self.assertEqual((row["verdict"], self.dialog_flags(row)), ("rotating", []))

    def test_describe__a_stopping_session_waiting_on_a_dialog_carries_no_dialog_flag(self):
        """Declared guard, green at the tip before U3: a stopping row whose session is waiting carries no `dialog`. It guards the defect of widening `dialog` past running rows, the full route the Owner passed over, which reverses 024 D3 R5 (028 D3 R4)."""
        row = self.describe(self.given_run(stop_file=True), sessions=self.live("waiting"))
        self.assertEqual((row["verdict"], self.dialog_flags(row)), ("stopping", []))


class RegistryStatusTickTests(RosterCase):
    """D4 · a --since tick prints a row whose `dialog` flag appeared or cleared, and nothing for a busy ↔ shell change.

    run-roster.py runs as a subprocess with a scratch $HOME, so its registry is <HOME>/.claude/sessions
    (SESSIONS_ROOT is expanded at import), never this Mac's; the record carries this test's own pid so
    live_sessions() keeps it, and matches WORKING by session_id.
    """

    def setUp(self):
        super().setUp()
        self.home = self.root.parent / "home"
        self.registry = self.home / ".claude" / "sessions"
        self.registry.mkdir(parents=True)

    # ------------------------------------------------------------ given

    def given_working_session(self):
        """WORKING, started an hour ago and written 10 min ago by the wall clock, so no quiet or over-wall flag rides on its row."""
        wall = datetime.now(timezone.utc)
        return self.given_run(started_at=iso(wall - timedelta(hours=1)), updated_at=iso(wall - timedelta(minutes=10)))

    def given_registry(self, status):
        """The scratch registry holding WORKING's live session in `status`, written over the previous record — the registry moving between two ticks."""
        record = {"sessionId": SESSION_ID, "name": "worker-opus-u2", "status": status, "cwd": "/nonexistent/worktree", "pid": os.getpid()}
        (self.registry / "worker-opus-u2.json").write_text(json.dumps(record) + "\n")

    # ------------------------------------------------------------ when

    def roster(self, *args):
        """run-roster.py over the scratch root, with the scratch $HOME: the scratch registry, no transcripts, no triage, no lead line."""
        env = dict(os.environ, HOME=str(self.home), ROBOWRIGHT_SESSIONS_ROOT=str(self.root))
        done = subprocess.run([sys.executable, str(ROSTER_SCRIPT), "--runs-root", str(self.root), "--no-lead", *args],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def since_file(self):
        return self.root.parent / "roster-since.json"

    def tick(self):
        """One `--since` tick, every tick of a test on the same state file — the Lead's default tick."""
        return self.roster("--since", str(self.since_file()))

    # ------------------------------------------------------------ then

    def working_rows(self, out):
        """The table rows the tick printed for WORKING."""
        return [line for line in out.splitlines() if line.startswith(f"| {WORKING} ")]

    def test_roster__since_prints_the_row_of_a_session_whose_registry_goes_busy_to_waiting(self):
        """A session that reached a dialog between ticks is printed on the next; behind `no change` it waits until someone happens to answer its dialog (D4 R1; green at red — owes its kill first)."""
        self.given_working_session()
        self.given_registry("busy")
        self.tick()
        self.given_registry("waiting")

        out = self.tick()

        self.assertEqual(len(self.working_rows(out)), 1, out)

    def test_roster__since_prints_the_row_of_a_session_whose_registry_goes_waiting_to_busy(self):
        """A dialog answered between ticks is printed on the next; without it the Lead keeps reporting a dialog to the Owner that is gone (D4 R1; green at red — owes its kill first)."""
        self.given_working_session()
        self.given_registry("waiting")
        self.tick()
        self.given_registry("busy")

        out = self.tick()

        self.assertEqual(len(self.working_rows(out)), 1, out)

    def test_roster__since_prints_the_row_of_a_session_whose_registry_goes_shell_to_waiting(self):
        """running both ticks, only `dialog` appeared; a tick that fingerprints the verdict alone hides the dialog behind `no change` (D4 R1)."""
        self.given_working_session()
        self.given_registry("shell")
        self.tick()
        self.given_registry("waiting")

        out = self.tick()

        self.assertEqual(len(self.working_rows(out)), 1, out)

    def test_roster__since_prints_the_row_of_a_session_whose_registry_goes_waiting_to_shell(self):
        """running both ticks, only `dialog` cleared; a tick that fingerprints the verdict alone leaves the Lead reporting a dialog that is gone (D4 R1)."""
        self.given_working_session()
        self.given_registry("waiting")
        self.tick()
        self.given_registry("shell")

        out = self.tick()

        self.assertEqual(len(self.working_rows(out)), 1, out)

    def test_roster__since_prints_no_change_when_the_registry_goes_busy_to_shell(self):
        """busy and shell are both running with no flag, so the change is not news; printing it costs the Lead a row on every background build (D4 R2)."""
        self.given_working_session()
        self.given_registry("busy")
        self.tick()
        self.given_registry("shell")

        out = self.tick()

        self.assertEqual(out.splitlines(), ["no change since last tick: 1 session(s), 1 unfinished"])


# ------------------------------------------------------------------------------------------------
# The sessions root comes from --runs-root, else $ROBOWRIGHT_SESSIONS_ROOT, else launch.json's
# sessions_root — never a built-in path; with none of them the script refuses by name. The roster's
# triage rows come from launch.json's triage_root. launch.json's roots are read as the launcher reads
# them: a leading `~/` is $HOME/, anything else — a bare `~`, a `~user/…` — as written; --runs-root and
# the env root keep their `~` expansion.

SESSION_ENV = "robowright-fixture-env-root"
SESSION_FILE = "robowright-fixture-launch-json-root"
SESSION_FLAG = "robowright-fixture-runs-root"
SESSION_FLAG_2 = "robowright-fixture-second-runs-root"
SESSION_IN_CWD = "robowright-fixture-in-cwd"
SESSION_IN_HOME = "robowright-fixture-in-home"
SESSION_UNEXPANDED = "robowright-fixture-unexpanded-tilde"
SESSION_CAPPED_AT_ZERO = "robowright-fixture-capped-at-zero"
STACK = "sample-stack"
STACK_UNEXPANDED = "sample-stack-unexpanded-tilde"
STACK_IN_CWD = "sample-stack-in-cwd"
# A user every macOS and Linux box has, so `~root/…` expanded would name a real home outside the scratch dirs.
OTHER_USER = "root"


class ScratchHome:
    """A scratch $HOME with launch.json at <HOME>/.claude/robowright/launch.json, and a scratch cwd for
    every run, so a relative or unexpanded root lands somewhere the test can see — never the real ~."""

    SCRIPT = ROSTER_SCRIPT

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Resolved, so the $HOME a script prints is the path the test compares against (macOS's temp
        # dir sits under /var, a link to /private/var).
        self.base = Path(os.path.realpath(tmp.name))
        self.home = self.base / "home"
        self.home.mkdir()
        self.cwd = self.base / "cwd"
        self.cwd.mkdir()
        self.launch_json = self.home / ".claude" / "robowright" / "launch.json"

    # ------------------------------------------------------------ given

    def given_session(self, root, name, **fields):
        """An unfinished session dir under `root` that both scripts list: implementing U1, last written an hour ago, a $50 cap and a $40 threshold."""
        run_dir = Path(root) / name
        run_dir.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        run = {
            "ticket": name,
            "phase": "implement",
            "stop_reason": None,
            "rotate": None,
            "rebriefs": [],
            "units": [{"id": "U1", "status": "todo"}],
            "started_at": iso(now - timedelta(hours=2)),
            "updated_at": iso(now - timedelta(hours=1)),
            "max_wall_hours": 12,
            "spend_cap_usd": 50,
            "spend_threshold_usd": 40,
        }
        run.update(fields)
        (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        return run_dir

    def given_launch_json(self, text):
        self.launch_json.parent.mkdir(parents=True, exist_ok=True)
        self.launch_json.write_text(text)

    def given_launch_settings(self, **settings):
        # Every install's launch.json carries `repos` (owner_git.py); the roster reads past it.
        self.given_launch_json(json.dumps(dict({"repos": ["~/Code/sample"]}, **settings)) + "\n")

    def given_another_user_with_a_home(self):
        """OTHER_USER exists here — the premise that makes `~root/…` read as that user's home a different place from `<cwd>/~root/…`."""
        self.assertTrue(pwd.getpwnam(OTHER_USER).pw_dir, f"premise: user {OTHER_USER} has a home")

    # ------------------------------------------------------------ when

    def run_script(self, *args, sessions_root_env=None, timeout=60):
        """SCRIPT as a subprocess: scratch $HOME and cwd, $ROBOWRIGHT_SESSIONS_ROOT only when the test sets it."""
        env = {key: value for key, value in os.environ.items() if key != "ROBOWRIGHT_SESSIONS_ROOT"}
        # COLUMNS: wide enough that argparse never wraps a path in --help across two lines.
        env.update(HOME=str(self.home), COLUMNS="1000", NO_COLOR="1")
        if sessions_root_env is not None:
            env["ROBOWRIGHT_SESSIONS_ROOT"] = sessions_root_env
        return subprocess.run([sys.executable, str(self.SCRIPT), *args], capture_output=True, text=True,
                              env=env, cwd=str(self.cwd), timeout=timeout)


class SessionsRootCases(ScratchHome):
    """Sessions-root rules R1–R6 for one script; RosterSessionsRootTests and GuardSessionsRootTests run them."""

    READ_FLAGS = ()

    def session_names(self, stdout):
        raise NotImplementedError

    def sessions_read(self, *args, sessions_root_env=None):
        """The session dir names one read-only --json pass lists."""
        done = self.run_script(*self.READ_FLAGS, *args, sessions_root_env=sessions_root_env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return self.session_names(done.stdout)

    def help_text(self):
        done = self.run_script("--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def assertRefusedForSessionsRoot(self, done):
        """Rule 4: exit 2, nothing on stdout, one stderr line naming the key and the file looked for."""
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")
        lines = done.stderr.splitlines()
        self.assertEqual(len(lines), 1, done.stderr)
        self.assertIn("sessions_root", lines[0])
        self.assertIn(str(self.launch_json), lines[0])

    # ------------------------------------------------------------ rule 1 · --runs-root

    def test_root__reads_only_the_runs_root_when_the_env_and_launch_json_name_other_roots(self):
        """R1.1 · --runs-root wins over the env and launch.json — a Lead pointing at one root would see, or stop, sessions under another."""
        self.given_session(self.base / "flag-root", SESSION_FLAG)
        self.given_session(self.base / "env-root", SESSION_ENV)
        self.given_session(self.home / "file-root", SESSION_FILE)
        self.given_launch_settings(sessions_root="~/file-root")

        names = self.sessions_read("--runs-root", str(self.base / "flag-root"), sessions_root_env=str(self.base / "env-root"))

        self.assertEqual(names, [SESSION_FLAG])

    def test_root__runs_under_the_runs_root_with_no_env_and_no_launch_json(self):
        """R1.2 · --runs-root alone is enough — an explicit root would be refused on an install with no launch.json."""
        self.given_session(self.base / "flag-root", SESSION_FLAG)

        names = self.sessions_read("--runs-root", str(self.base / "flag-root"))

        self.assertEqual(names, [SESSION_FLAG])

    def test_root__runs_under_the_runs_root_when_launch_json_is_not_json(self):
        """R1.3 · --runs-root never reads launch.json for the root — a broken launch.json would block an explicit root."""
        self.given_session(self.base / "flag-root", SESSION_FLAG)
        self.given_launch_json('{"sessions_root": "~/file-root",\n')

        names = self.sessions_read("--runs-root", str(self.base / "flag-root"))

        self.assertEqual(names, [SESSION_FLAG])

    def test_root__reads_home_y_when_the_runs_root_is_tilde_y(self):
        """R1.5 · `~/y` given as --runs-root is $HOME/y — once the glob loop stops expanding, a quoted `~/y` would be read as a dir named `~` under the cwd."""
        self.given_session(self.home / "y", SESSION_FLAG)
        self.given_session(self.cwd / "~" / "y", SESSION_UNEXPANDED)

        names = self.sessions_read("--runs-root", "~/y")

        self.assertEqual(names, [SESSION_FLAG])

    def test_root__reads_home_when_the_runs_root_is_a_bare_tilde(self):
        """R1.6 · a bare `~` given as --runs-root is still $HOME — launch.json's reading leaking into the flag would turn it into a dir named `~` under the cwd (assumed Q1)."""
        self.given_session(self.home, SESSION_IN_HOME)
        self.given_session(self.cwd / "~", SESSION_UNEXPANDED)

        names = self.sessions_read("--runs-root", "~")

        self.assertEqual(names, [SESSION_IN_HOME])

    # ------------------------------------------------------------ rule 2 · $ROBOWRIGHT_SESSIONS_ROOT

    def test_root__reads_the_env_root_and_not_the_launch_json_root_when_both_are_set(self):
        """R2.1 · the env root wins over launch.json — the Owner's override would be ignored."""
        self.given_session(self.base / "env-root", SESSION_ENV)
        self.given_session(self.home / "file-root", SESSION_FILE)
        self.given_launch_settings(sessions_root="~/file-root")

        names = self.sessions_read(sessions_root_env=str(self.base / "env-root"))

        self.assertEqual(names, [SESSION_ENV])

    def test_root__reads_the_env_root_when_launch_json_is_not_json(self):
        """R2.2 · an env root never reads launch.json for the root — a broken launch.json would block the override."""
        self.given_session(self.base / "env-root", SESSION_ENV)
        self.given_launch_json('{"sessions_root": "~/file-root",\n')

        names = self.sessions_read(sessions_root_env=str(self.base / "env-root"))

        self.assertEqual(names, [SESSION_ENV])

    def test_root__reads_home_y_when_the_env_root_is_tilde_y(self):
        """R2.3 · `~` in the env root is $HOME — a quoted `~/y` would be read as a dir named `~` under the cwd."""
        self.given_session(self.home / "y", SESSION_ENV)
        self.given_session(self.cwd / "~" / "y", SESSION_UNEXPANDED)

        names = self.sessions_read(sessions_root_env="~/y")

        self.assertEqual(names, [SESSION_ENV])

    def test_root__reads_the_launch_json_root_when_the_env_root_is_empty(self):
        """R2.4 · an empty env var is unset — it would be taken as the cwd, or would hide launch.json."""
        self.given_session(self.home / "x", SESSION_FILE)
        self.given_session(self.cwd, SESSION_IN_CWD)
        self.given_launch_settings(sessions_root="~/x")

        names = self.sessions_read(sessions_root_env="")

        self.assertEqual(names, [SESSION_FILE])

    def test_root__reads_home_when_the_env_root_is_a_bare_tilde(self):
        """R2.5 · a bare `~` in the env root is still $HOME — launch.json's reading leaking into the override would turn it into a dir named `~` under the cwd (assumed Q1)."""
        self.given_session(self.home, SESSION_IN_HOME)
        self.given_session(self.cwd / "~", SESSION_UNEXPANDED)

        names = self.sessions_read(sessions_root_env="~")

        self.assertEqual(names, [SESSION_IN_HOME])

    # ------------------------------------------------------------ rule 3 · launch.json's sessions_root

    def test_root__reads_home_x_when_launch_json_names_tilde_x(self):
        """R3.1 · launch.json's `~/x` is $HOME/x — the install's root would be missed, or a dir named `~` under the cwd read instead."""
        self.given_session(self.home / "x", SESSION_FILE)
        self.given_session(self.cwd / "~" / "x", SESSION_UNEXPANDED)
        self.given_launch_settings(sessions_root="~/x")

        names = self.sessions_read()

        self.assertEqual(names, [SESSION_FILE])

    def test_root__reads_an_absolute_sessions_root_from_launch_json(self):
        """R3.2 · an absolute sessions_root is read as written — an install that spells its root out would be refused or misread."""
        self.given_session(self.base / "absolute-root", SESSION_FILE)
        self.given_launch_settings(sessions_root=str(self.base / "absolute-root"))

        names = self.sessions_read()

        self.assertEqual(names, [SESSION_FILE])

    def test_root__reads_a_dir_named_tilde_under_the_cwd_when_launch_json_names_a_bare_tilde(self):
        """R3.3 · launch.json's bare `~` is read as written, as the launcher reads it — the script would list, or STOP, sessions under $HOME that the launcher never put there."""
        self.given_session(self.home, SESSION_IN_HOME)
        self.given_session(self.cwd / "~", SESSION_UNEXPANDED)
        self.given_launch_settings(sessions_root="~")

        names = self.sessions_read()

        self.assertEqual(names, [SESSION_UNEXPANDED])

    def test_root__reads_the_path_as_written_and_not_that_users_home_when_launch_json_names_tilde_user_x(self):
        """R3.4 · launch.json's `~root/x` is read as written, not as root's home — the script would read another user's sessions, or none, where the launcher reads `<cwd>/~root/x`."""
        self.given_another_user_with_a_home()
        self.given_session(self.cwd / f"~{OTHER_USER}" / "x", SESSION_UNEXPANDED)
        self.given_launch_settings(sessions_root=f"~{OTHER_USER}/x")

        names = self.sessions_read()

        self.assertEqual(names, [SESSION_UNEXPANDED])

    def test_root__reads_home_when_launch_json_names_tilde_slash_alone(self):
        """R3.5 · launch.json's `~/` alone is $HOME — the leading-`~/` rule's shortest case would be refused, or read as a dir named `~` under the cwd."""
        self.given_session(self.home, SESSION_IN_HOME)
        self.given_session(self.cwd / "~", SESSION_UNEXPANDED)
        self.given_launch_settings(sessions_root="~/")

        names = self.sessions_read()

        self.assertEqual(names, [SESSION_IN_HOME])

    def test_root__reads_home_abs_when_launch_json_names_tilde_double_slash_abs(self):
        """R3.6 · launch.json's `~//abs` is $HOME/abs, as the launcher reads it (`$HOME/` + everything after the `~/`) — joined as a path, `/abs` drops $HOME and the install's sessions are missed (D4)."""
        self.given_session(self.home / "abs", SESSION_FILE)
        self.given_session(self.cwd / "~" / "abs", SESSION_UNEXPANDED)
        self.given_launch_settings(sessions_root="~//abs")

        names = self.sessions_read()

        self.assertEqual(names, [SESSION_FILE])

    # ------------------------------------------------------------ rule 4 · the refusal

    def test_root__refuses_by_name_with_no_env_and_no_launch_json(self):
        """R4.1 · nothing configured is a named refusal — the script would fall back to a path on no machine and report an empty roster as fact."""
        done = self.run_script()

        self.assertRefusedForSessionsRoot(done)

    def test_root__refuses_by_name_when_the_env_root_is_empty_and_there_is_no_launch_json(self):
        """R4.2 · an empty env var configures nothing — it would be taken as the cwd."""
        done = self.run_script(sessions_root_env="")

        self.assertRefusedForSessionsRoot(done)

    def test_root__refuses_by_name_when_launch_json_has_no_sessions_root(self):
        """R4.3 · a launch.json without the key configures nothing — the script would fall back to a built-in path."""
        self.given_launch_json("{}\n")

        done = self.run_script()

        self.assertRefusedForSessionsRoot(done)

    # ------------------------------------------------------------ rule 5 · a launch.json that gives no root

    def test_root__refuses_by_name_when_sessions_root_is_an_empty_string(self):
        """R5.1 · an empty sessions_root is no root — it would be taken as the cwd."""
        self.given_launch_settings(sessions_root="")

        done = self.run_script()

        self.assertRefusedForSessionsRoot(done)

    def test_root__refuses_by_name_when_sessions_root_is_not_a_string(self):
        """R5.2 · a non-string sessions_root is no root — it would crash, or be read as something it is not."""
        self.given_launch_settings(sessions_root=["~/x"])

        done = self.run_script()

        self.assertRefusedForSessionsRoot(done)

    def test_root__refuses_by_name_when_launch_json_is_not_json(self):
        """R5.3 · a launch.json that does not parse is a named refusal — a traceback, or a silent fallback, instead."""
        self.given_launch_json('{"sessions_root": "~/x",\n')

        done = self.run_script()

        self.assertRefusedForSessionsRoot(done)

    def test_root__refuses_by_name_when_launch_json_is_unreadable(self):
        """R5.4 · a launch.json that cannot be read is a named refusal — a traceback instead (a directory stands in for an unreadable file)."""
        self.launch_json.mkdir(parents=True)

        done = self.run_script()

        self.assertRefusedForSessionsRoot(done)

    def test_root__refuses_by_name_when_launch_json_is_not_an_object(self):
        """R5.5 · a launch.json that is not an object has no sessions_root — `.get` on a list would crash."""
        self.given_launch_json('["~/x"]\n')

        done = self.run_script()

        self.assertRefusedForSessionsRoot(done)

    # ------------------------------------------------------------ rule 6 · --help

    def test_help__prints_usage_and_exits_0_with_nothing_configured(self):
        """R6.1 · --help works before anything is configured — the first thing a new install runs would be refused."""
        done = self.run_script("--help")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("--runs-root", done.stdout)

    def test_help__names_the_env_var_and_launch_json_sessions_root_as_the_default(self):
        """R6.2 · --help says where the default root comes from — the Owner cannot learn what to configure (assumed Q3)."""
        text = self.help_text()

        self.assertIn("ROBOWRIGHT_SESSIONS_ROOT", text)
        self.assertIn("sessions_root", text)
        self.assertIn("launch.json", text)

    def test_help__embeds_no_path_under_home_with_nothing_configured(self):
        """R6.3 · --help embeds no resolved root — it would print a built-in path as if it were the default (assumed Q4)."""
        text = self.help_text()

        self.assertNotIn(str(self.home), text)


class RosterSessionsRootTests(SessionsRootCases, unittest.TestCase):
    """run-roster.py's sessions root (R1–R6)."""

    SCRIPT = ROSTER_SCRIPT
    READ_FLAGS = ("--json", "--no-lead")

    def session_names(self, stdout):
        return [row["run"] for row in json.loads(stdout)["runs"]]

    def test_roster__reads_every_runs_root_given(self):
        """R1.4 · --runs-root is repeatable — a second root's sessions would be dropped."""
        self.given_session(self.base / "flag-root", SESSION_FLAG)
        self.given_session(self.base / "second-flag-root", SESSION_FLAG_2)

        names = self.sessions_read("--runs-root", str(self.base / "flag-root"), "--runs-root", str(self.base / "second-flag-root"))

        self.assertCountEqual(names, [SESSION_FLAG, SESSION_FLAG_2])

    def test_roster__writes_no_since_file_when_refusing(self):
        """R4.4 · a refusal writes nothing — a --since state file written from an empty roster would mark every session changed on the next tick."""
        since = self.base / "since.json"

        self.run_script("--since", str(since))

        self.assertFalse(since.exists())


class GuardSessionsRootTests(SessionsRootCases, unittest.TestCase):
    """spend-guard.py's sessions root (R1–R6), and a refusal that writes nothing and never polls."""

    SCRIPT = GUARD
    READ_FLAGS = ("--json", "--dry-run")

    def session_names(self, stdout):
        return [row["run"] for row in json.loads(stdout)]

    def given_session_capped_at_zero_in_the_cwd(self):
        """A session capped at $0 in the cwd: any pass that reached it would write STOP and a ledger line."""
        return self.given_session(self.cwd, SESSION_CAPPED_AT_ZERO, spend_cap_usd=0, spend_threshold_usd=0)

    def test_spend_guard__writes_no_stop_and_no_ledger_line_when_refusing_with_no_launch_json(self):
        """R4.5 · the guard's refusal writes nothing — a guessed root would get a STOP it never earned."""
        run_dir = self.given_session_capped_at_zero_in_the_cwd()

        self.run_script()

        self.assertEqual(sorted(path.name for path in run_dir.iterdir()), ["run.json"])

    def test_spend_guard__writes_no_stop_and_no_ledger_line_when_refusing_an_empty_sessions_root(self):
        """R5.6 · an empty sessions_root writes nothing — taken as the cwd, it would STOP whatever session sits there."""
        run_dir = self.given_session_capped_at_zero_in_the_cwd()
        self.given_launch_settings(sessions_root="")

        self.run_script()

        self.assertEqual(sorted(path.name for path in run_dir.iterdir()), ["run.json"])

    def test_spend_guard__watch_refuses_once_instead_of_polling_with_nothing_configured(self):
        """R4.6 · the refusal comes before the poll loop — --watch would spin forever enforcing nothing."""
        try:
            done = self.run_script("--watch", "1", timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("spend-guard.py --watch 1 was still running after 10 s with nothing configured")

        self.assertRefusedForSessionsRoot(done)


class SpendGuardWriteTests(ScratchHome, unittest.TestCase):
    """SW-13 (tests/run-launch/BEHAVIORS.md): the guard writes STOP and a ledger line into each session dir it polls, so
    never through an entry the session planted there."""

    SCRIPT = GUARD
    OWNER_TEXT = "the Owner's file\n"

    def guard(self, root):
        self.run_script("--runs-root", str(root), "--json")

    def test_spend_guard__never_creates_stop_through_a_dangling_link(self):
        """A link to a missing path reads as no STOP, so the guard would create the file it names."""
        run_dir = self.given_session(self.base / "sessions", SESSION_CAPPED_AT_ZERO, spend_cap_usd=0, spend_threshold_usd=0)
        missing = self.base / "missing-stop"
        (run_dir / "STOP").symlink_to(missing)
        self.guard(run_dir.parent)
        self.assertFalse(missing.exists())

    def test_spend_guard__never_appends_a_ledger_line_through_a_link(self):
        """Both the cap and the threshold paths append to LEDGER.md."""
        for name, fields in (("cap", {"spend_cap_usd": 0, "spend_threshold_usd": 0}),
                             ("threshold", {"spend_cap_usd": None, "spend_threshold_usd": 0})):
            with self.subTest(name):
                run_dir = self.given_session(self.base / f"sessions-{name}", SESSION_CAPPED_AT_ZERO, **fields)
                target = self.base / f"target-{name}"
                target.write_text(self.OWNER_TEXT)
                (run_dir / "LEDGER.md").symlink_to(target)
                self.guard(run_dir.parent)
                self.assertEqual(target.read_text(), self.OWNER_TEXT)


class RosterTriageRootTests(ScratchHome, unittest.TestCase):
    """R7 · the roster's triage rows come from launch.json's triage_root, whatever names the sessions root."""

    SCRIPT = ROSTER_SCRIPT

    # ------------------------------------------------------------ given

    def given_triage_state_dir(self, parent, stack=STACK):
        """A review-surface state dir holding one open thread; threads.json is what makes a triage row."""
        state_dir = Path(parent) / stack
        state_dir.mkdir(parents=True)
        threads = {"t1": {"thread_id": "t1", "kind": "nit", "state": "open"}}
        (state_dir / "threads.json").write_text(json.dumps(threads, indent=2) + "\n")

    # ------------------------------------------------------------ when

    def roster(self, *args, sessions_root_env=None):
        done = self.run_script("--no-lead", *args, sessions_root_env=sessions_root_env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    # ------------------------------------------------------------ then

    def triage_stacks(self, stdout):
        """The stack each `triage: <stack> · …` line names, in print order."""
        return [line[len("triage: "):].split(" · ")[0] for line in stdout.splitlines() if line.startswith("triage: ")]

    def test_triage__prints_the_line_of_the_one_state_dir_under_triage_root(self):
        """R7.1 · triage_root `~/triage` gives the triage rows from $HOME/triage — the review surface would vanish from the roster."""
        self.given_triage_state_dir(self.home / "triage")
        self.given_triage_state_dir(self.cwd / "~" / "triage", STACK_UNEXPANDED)
        self.given_launch_settings(sessions_root="~/sessions", triage_root="~/triage")

        done = self.roster()

        self.assertEqual(self.triage_stacks(done.stdout), [STACK])

    def test_triage__prints_no_triage_line_and_no_message_without_the_key(self):
        """R7.2 · no triage_root is no triage, silently — an install without a review surface would get a line or a warning every tick."""
        self.given_launch_settings(sessions_root="~/sessions")

        done = self.roster()

        self.assertEqual((self.triage_stacks(done.stdout), done.stderr), ([], ""))

    def test_triage__prints_no_triage_line_and_no_message_when_the_key_is_null(self):
        """R7.3 · a null triage_root is the same as no key — it would crash, or print a message."""
        self.given_launch_settings(sessions_root="~/sessions", triage_root=None)

        done = self.roster()

        self.assertEqual((self.triage_stacks(done.stdout), done.stderr), ([], ""))

    def test_triage__prints_no_triage_line_and_no_message_when_the_key_is_an_empty_string(self):
        """R7.4 · an empty triage_root is absent — taken as the cwd, the roster would print a stranger's state dir."""
        self.given_triage_state_dir(self.cwd, STACK_IN_CWD)
        self.given_launch_settings(sessions_root="~/sessions", triage_root="")

        done = self.roster()

        self.assertEqual((self.triage_stacks(done.stdout), done.stderr), ([], ""))

    def test_triage__prints_no_triage_line_and_no_message_when_the_key_is_not_a_string(self):
        """R7.5 · a non-string triage_root is absent — it would crash, or be read as something it is not."""
        self.given_triage_state_dir(self.home / "triage")
        self.given_launch_settings(sessions_root="~/sessions", triage_root=["~/triage"])

        done = self.roster()

        self.assertEqual((self.triage_stacks(done.stdout), done.stderr), ([], ""))

    def test_triage__prints_no_triage_line_and_no_traceback_when_triage_root_names_a_missing_dir(self):
        """R7.6 · a triage_root that does not exist yet is no rows, not an error — the whole roster would die on a missing dir."""
        self.given_launch_settings(sessions_root="~/sessions", triage_root="~/no-triage-here")

        done = self.roster()

        self.assertEqual(self.triage_stacks(done.stdout), [])
        self.assertNotIn("Traceback", done.stderr)

    def test_triage__still_prints_the_triage_line_under_runs_root(self):
        """R7.7 · triage rows are not sessions, so --runs-root does not hide them — a Lead passing --runs-root would lose the review surface."""
        self.given_triage_state_dir(self.home / "triage")
        self.given_launch_settings(triage_root="~/triage")

        done = self.roster("--runs-root", str(self.base / "flag-root"))

        self.assertEqual(self.triage_stacks(done.stdout), [STACK])

    def test_triage__still_prints_the_triage_line_when_the_env_names_the_sessions_root(self):
        """R7.8 · triage rows come from launch.json whatever names the sessions root — an env root would hide the review surface."""
        self.given_triage_state_dir(self.home / "triage")
        self.given_launch_settings(triage_root="~/triage")

        done = self.roster(sessions_root_env=str(self.base / "env-root"))

        self.assertEqual(self.triage_stacks(done.stdout), [STACK])

    def test_triage__prints_no_triage_line_under_runs_root_when_launch_json_is_not_json(self):
        """R7.9 · a broken launch.json under --runs-root is no triage, and no refusal — the roster would die for want of an optional key (assumed Q5)."""
        self.given_triage_state_dir(self.home / "triage")
        self.given_launch_json('{"triage_root": "~/triage",\n')

        done = self.roster("--runs-root", str(self.base / "flag-root"))

        self.assertEqual(self.triage_stacks(done.stdout), [])

    def test_triage__prints_the_line_of_the_state_dir_under_a_dir_named_tilde_when_triage_root_is_a_bare_tilde(self):
        """R7.10 · a bare `~` triage_root is read as written, as sessions_root is — the roster would print state dirs straight under $HOME."""
        self.given_triage_state_dir(self.home)
        self.given_triage_state_dir(self.cwd / "~", STACK_UNEXPANDED)
        self.given_launch_settings(sessions_root="~/sessions", triage_root="~")

        done = self.roster()

        self.assertEqual(self.triage_stacks(done.stdout), [STACK_UNEXPANDED])

    def test_triage__prints_the_line_of_the_state_dir_as_written_and_not_under_that_users_home_when_triage_root_is_tilde_user(self):
        """R7.11 · a `~root/triage` triage_root is read as written, not as root's home — the review surface would be looked for in another user's home."""
        self.given_another_user_with_a_home()
        self.given_triage_state_dir(self.cwd / f"~{OTHER_USER}" / "triage", STACK_UNEXPANDED)
        self.given_launch_settings(sessions_root="~/sessions", triage_root=f"~{OTHER_USER}/triage")

        done = self.roster()

        self.assertEqual(self.triage_stacks(done.stdout), [STACK_UNEXPANDED])



# ------------------------------------------------------------ U2 · the roster and the guard price from the pricing file

PRICED = "sample-013-ledger"
PRICED_TOO = "sample-014-export"
PRICED_SESSION = "e6e6e6e6-0000-4000-8000-000000000006"
PRICES_AS_OF = "2026-09-10"
FRESH_TODAY = "2026-09-26"
THIRTY_ONE_DAYS_ON = "2026-10-11"  # 2026-09-10 + 31 days
SIX_ROWS = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write_5m": 5.00, "cache_write_1h": 8.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00},
    "claude-fable-5-1": {"input": 10.00, "output": 50.00, "cache_read": 0.25, "cache_write_5m": 12.50, "cache_write_1h": 20.00},
    "claude-fable-5": {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_write_5m": 12.50, "cache_write_1h": 20.00},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write_5m": 2.50, "cache_write_1h": 4.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00},
}
DOLLAR_A_MILLION = {"input": 1.00, "output": 1.00, "cache_read": 1.00, "cache_write_5m": 1.00, "cache_write_1h": 1.00}
# (message id, model, input, output, cache read, cache write). At the six rows:
#   msg_p1 opus-5-5   100,000×4 + 20,000×20 + 1,000,000×0.20 + 300,000×5   = $2.50
#   msg_p2 haiku-4-5   30,000×1 +  7,000×5  +   400,000×0.10 +  60,000×1.25 = $0.18   → $2.68
# At $1 a million for every class: 1,420,000 + 497,000 tokens = $1.917 → $1.92.
# Requests 2; output tokens 20,000 + 7,000 = 27,000.
PRICED_ROWS = (
    ("msg_p1", "claude-opus-5-5", 100000, 20000, 1000000, 300000),
    ("msg_p2", "claude-haiku-4-5", 30000, 7000, 400000, 60000),
)


class PricingReportCase(unittest.TestCase):
    """A scratch $HOME holding one unfinished session whose run.json pins one synthetic transcript and
    carries a $50 cap and a $40 threshold, and a pricing file SIX_ROWS dated PRICES_AS_OF, fresh on
    FRESH_TODAY. Both scripts run as subprocesses with --runs-root."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.home = self.base / "home"
        self.home.mkdir()
        self.cwd = self.base / "cwd"
        self.cwd.mkdir()
        self.root = self.base / "sessions"
        self.pricing_file = self.given_pricing()
        self.missing = self.base / "nowhere" / "pricing.json"
        self.run_dir = self.given_session(PRICED)

    # ------------------------------------------------------------ given

    def given_pricing(self, models=SIX_ROWS, default=None, updated_at=PRICES_AS_OF):
        path = self.base / "prices" / "pricing.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"updated_at": updated_at, "source": "sample price page",
                                    "default": default or SIX_ROWS["claude-opus-5"], "models": models}, indent=2) + "\n")
        return path

    def given_session(self, name, **fields):
        project_dir = self.home / ".claude" / "projects" / f"-Users-owner-wt-{name}"
        project_dir.mkdir(parents=True)
        transcript = project_dir / f"{PRICED_SESSION}.jsonl"
        transcript.write_text("".join(json.dumps({
            "type": "assistant", "timestamp": "2026-09-20T10:00:00.000Z", "uuid": f"uuid-{mid}",
            "message": {"id": mid, "type": "message", "role": "assistant", "model": model,
                        "content": [{"type": "text", "text": "ok"}],
                        "usage": {"input_tokens": inp, "output_tokens": out,
                                  "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": cache_write}},
        }) + "\n" for mid, model, inp, out, cache_read, cache_write in PRICED_ROWS))
        run_dir = self.root / name
        run_dir.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        run = {
            "ticket": name, "phase": "implement", "stop_reason": None, "rotate": None, "rebriefs": [],
            "units": [{"id": "U1", "status": "todo"}],
            "started_at": iso(now - timedelta(hours=2)), "updated_at": iso(now - timedelta(hours=1)),
            "max_wall_hours": 12, "spend_cap_usd": 50, "spend_threshold_usd": 40,
            "worktree": f"/Users/owner/wt/{name}", "transcripts": [str(transcript)],
        }
        run.update(fields)
        (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        return run_dir

    # ------------------------------------------------------------ when

    def run_priced(self, script, *args, pricing_file=None, today=FRESH_TODAY):
        env = {k: v for k, v in os.environ.items() if k not in ("ROBOWRIGHT_SESSIONS_ROOT", "ROBOWRIGHT_PRICING_FILE")}
        env.update(HOME=str(self.home), COLUMNS="1000", NO_COLOR="1",
                   ROBOWRIGHT_PRICING_FILE=str(pricing_file or self.pricing_file), ROBOWRIGHT_PRICING_NOW=today)
        extra = ["--no-lead"] if script == ROSTER_SCRIPT else []
        return subprocess.run([sys.executable, str(script), "--runs-root", str(self.root), *extra, *args],
                              capture_output=True, text=True, env=env, cwd=str(self.cwd), timeout=60)

    def roster_rows(self, **kwargs):
        done = self.run_priced(ROSTER_SCRIPT, "--json", **kwargs)
        self.assertEqual(done.returncode, 0, done.stderr)
        return {row["run"]: row for row in json.loads(done.stdout)["runs"]}

    def guard_rows(self, *args, **kwargs):
        done = self.run_priced(GUARD, "--json", *args, **kwargs)
        self.assertEqual(done.returncode, 0, done.stderr)
        return {row["run"]: row for row in json.loads(done.stdout)}

    # ------------------------------------------------------------ then

    def stale_lines(self, done):
        return [line for line in (done.stdout + done.stderr).splitlines() if "stale" in line.lower()]

    def stderr_lines(self, done):
        return [line for line in done.stderr.splitlines() if line.strip()]


class RosterPricingTests(PricingReportCase):
    def test_roster__prices_a_session_s_spend_from_the_pricing_file(self):
        """At $1 a million for every class the session's 1,917,000 tokens are $1.92; a table left in the roster would still say $2.68 (invariant: "the three scripts have no price literal left"; D9 default row)."""
        self.given_pricing(models={}, default=DOLLAR_A_MILLION)

        rows = self.roster_rows()

        self.assertAlmostEqual(rows[PRICED]["spend_usd"], 1.92, places=6)

    def test_roster__prices_the_session_as_before__from_a_file_holding_the_six_rows(self):
        """Moving the prices into a file changes no dollar cell: the same transcript at the same rates is still $2.68 (smoke: "run-roster.py's spend cell keep[s] its shape"; green before the unit exists)."""
        rows = self.roster_rows()

        self.assertAlmostEqual(rows[PRICED]["spend_usd"], 2.68, places=6)

    def test_roster__says_prices_as_of_the_file_s_updated_at__with_its_dollar_cells(self):
        """The Lead reads a dollar cell against a cap; the roster names the prices' date beside it (D2: "every report prints prices as of <updated_at>"; placement with the table, assumed Q10)."""
        done = self.run_priced(ROSTER_SCRIPT)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"prices as of {PRICES_AS_OF}", done.stdout)

    def test_roster__warns_once_that_prices_are_stale__when_the_file_is_31_days_old(self):
        """A month-old file under-reports a session nearing its cap; the roster says so once, not once per row (D2; Language: stale; the line says "stale", assumed Q3)."""
        self.given_session(PRICED_TOO)

        done = self.run_priced(ROSTER_SCRIPT, today=THIRTY_ONE_DAYS_ON)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.stale_lines(done)), 1, done.stdout + done.stderr)

    def test_roster__spend_is_null_and_requests_and_output_tokens_unchanged__when_the_pricing_file_is_missing(self):
        """Without prices the spend cell has no figure to show, and the raw counts a non-dollar budget reads are still there (D9; U2 row: "USD null … with unchanged token counts")."""
        rows = self.roster_rows(pricing_file=self.missing)

        self.assertIsNone(rows[PRICED]["spend_usd"])
        self.assertEqual((rows[PRICED]["requests"], rows[PRICED]["tokens_out"]), (2, 27000))

    def test_roster__the_spend_cell_says_n_a_against_its_cap__when_the_pricing_file_is_missing(self):
        """A session that ran but could not be priced is not a session with no usage: the text cell says n/a beside its cap, not the — of a session with no transcript (D9; Q5: "n/a" in text)."""
        done = self.run_priced(ROSTER_SCRIPT, pricing_file=self.missing)

        self.assertEqual(done.returncode, 0, done.stderr)
        row = next(line for line in done.stdout.splitlines() if PRICED in line)
        self.assertIn("n/a / warn $40 / cap $50", row)

    def test_roster__says_the_pricing_file_is_missing_in_exactly_one_stderr_line__over_two_sessions(self):
        """One line per roster, not per session priced — a tick over ten sessions must not print ten (D9: "with one stderr line")."""
        self.given_session(PRICED_TOO)

        done = self.run_priced(ROSTER_SCRIPT, "--json", pricing_file=self.missing)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.stderr_lines(done)), 1, done.stderr)


class GuardPricingTests(PricingReportCase):
    def test_spend_guard__prices_a_session_s_spend_from_the_pricing_file(self):
        """The guard's estimate is the one that writes STOP; it comes from the file — $1.92 at $1 a million — not from a table of its own (invariant: "pricing.py is their only source"; Out of scope: "it reads the pricing file")."""
        self.given_pricing(models={}, default=DOLLAR_A_MILLION)

        rows = self.guard_rows("--dry-run")

        self.assertAlmostEqual(rows[PRICED]["usd"], 1.92, places=6)

    def test_spend_guard__says_prices_as_of_the_file_s_updated_at(self):
        """The guard's printed spend is an estimate against a cap; it names the prices' date (D2: "every report prints prices as of <updated_at>")."""
        done = self.run_priced(GUARD, "--dry-run")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"prices as of {PRICES_AS_OF}", done.stdout)

    def test_spend_guard__warns_once_that_prices_are_stale__when_the_file_is_31_days_old(self):
        """A stale file makes the guard's STOP late; it says so once per pass, not once per session (D2; Language: stale; the line says "stale", assumed Q3)."""
        self.given_session(PRICED_TOO)

        done = self.run_priced(GUARD, "--dry-run", today=THIRTY_ONE_DAYS_ON)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.stale_lines(done)), 1, done.stdout + done.stderr)

    def test_spend_guard__spend_is_null_with_counts_unchanged_and_one_stderr_line__when_the_pricing_file_is_missing(self):
        """No prices, no dollar figure — the message and output-token counts stay, and the missing file is said once (D9: "every USD figure null with one stderr line and leaves the token facts")."""
        self.given_session(PRICED_TOO)

        done = self.run_priced(GUARD, "--json", "--dry-run", pricing_file=self.missing)

        self.assertEqual(done.returncode, 0, done.stderr)
        rows = {row["run"]: row for row in json.loads(done.stdout)}
        self.assertIsNone(rows[PRICED]["usd"])
        self.assertEqual((rows[PRICED]["messages"], rows[PRICED]["tokens_out"]), (2, 27000))
        self.assertEqual(len(self.stderr_lines(done)), 1, done.stderr)

    def test_spend_guard__writes_no_stop_and_no_ledger_line__when_the_pricing_file_is_missing_even_at_a_zero_cap(self):
        """A missing file is no evidence of spend; stopping every capped session because the Owner moved a file would halt work nothing overspent (D9: USD is an estimate and becomes null; assumed Q9)."""
        capped = self.given_session("sample-015-capped", spend_cap_usd=0, spend_threshold_usd=0)

        done = self.run_priced(GUARD, "--json", pricing_file=self.missing)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((capped / "STOP").exists())
        self.assertFalse((capped / "LEDGER.md").exists())


if __name__ == "__main__":
    unittest.main()
