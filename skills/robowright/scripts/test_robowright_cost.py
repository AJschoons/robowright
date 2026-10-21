#!/usr/bin/env python3
"""Tests for robowright-cost.py's rollup, written from the accounting brief's U1 behaviors file
before the script existed.

    python3 skills/robowright/scripts/test_robowright_cost.py

Each test writes a synthetic ledger (<accounting root>/records.jsonl, one §6 record per line) into
a scratch accounting root, runs the rollup as a subprocess under a scratch HOME, and reads its
`--json` output: {"by": <by>, "scope": "session", "rows": [{"key": …, "requests": …,
"input_tokens": …, "output_tokens": …, "cache_read_tokens": …, "cache_write_tokens": …,
"estimated_usd": …, "active_hours": …, "plan_5h_pct": …, "plan_7d_pct": …}, …]}. The dollar
figures below are ledger inputs the rollup only adds up, never prices it computes.

The shared ledger, four session-scope records from three Claude sessions:

    record   project  unit               role      model             session  req  in    out  c.read  c.write  usd    active  at                 5h  7d
    S1 opus  sample   sample-013-ledger  worker    claude-opus-5-5   S1       2    300   60   3000    300      0.5    3600    09-20 11:15 +00    61  70
    S1 haiku sample   sample-013-ledger  subagent  claude-haiku-4-5  S1       1    30    7    400     60       0.25   3600    09-20 11:15 +00    61  70
    S2 opus  sample   sample-014-export  worker    claude-opus-5-5   S2       5    1000  500  9000    700      1.25   1800    09-21 09:00 +00    12  74
    S3 son.  demo     demo-002-intro     worker    claude-sonnet-5   S3       3    90    30   900     120      0.75   900     09-21 10:00 +00    20  75

The rollup does not price: it sums its records' estimates. It reads the pricing file only to say
which prices are current (U2 of the accounting brief). RollupCase names a synthetic pricing file
dated PRICES_AS_OF through $ROBOWRIGHT_PRICING_FILE and pins the day staleness is measured from
through $ROBOWRIGHT_PRICING_NOW, so no test reads the shipped file or the real date.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "robowright-cost.py"

S1 = "d4d4d4d4-0000-4000-8000-000000000001"
S2 = "d4d4d4d4-0000-4000-8000-000000000002"
S3 = "d4d4d4d4-0000-4000-8000-000000000003"
PRICES_AS_OF = "2026-09-10"
FRESH_TODAY = "2026-09-26"
THIRTY_ONE_DAYS_ON = "2026-10-11"  # 2026-09-10 + 31 days
OPUS_5_ROW = {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00}


def record(**fields):
    """One session-scope §6 record. The defaults are distinct and non-zero; a test names every value its rule depends on."""
    base = {
        "scope": "session", "at": "2026-09-20T11:15:00+00:00", "source": "hook",
        "project": "sample", "unit": "sample-013-ledger", "unit_id": None,
        "role": "worker", "model": "claude-opus-5-5", "session_id": S1,
        "session_dir": "/Users/owner/sessions/sample-013-ledger", "transcripts_pinned": True,
        "requests": 2, "input_tokens": 300, "output_tokens": 60, "cache_read_tokens": 3000,
        "cache_write_tokens": 300, "avg_context_tokens": 1800, "estimated_usd": 0.5, "price_as_of": None,
        "wall_seconds": 4000, "active_seconds": 3600,
        "plan_5h_pct": 61, "plan_7d_pct": 70, "plan_captured_at": 1789990000,
    }
    base.update(fields)
    return base


LEDGER = (
    record(project="sample", unit="sample-013-ledger", role="worker", model="claude-opus-5-5", session_id=S1,
           requests=2, input_tokens=300, output_tokens=60, cache_read_tokens=3000, cache_write_tokens=300,
           estimated_usd=0.5, active_seconds=3600, at="2026-09-20T11:15:00+00:00", plan_5h_pct=61, plan_7d_pct=70),
    record(project="sample", unit="sample-013-ledger", role="subagent", model="claude-haiku-4-5", session_id=S1,
           requests=1, input_tokens=30, output_tokens=7, cache_read_tokens=400, cache_write_tokens=60,
           estimated_usd=0.25, active_seconds=3600, at="2026-09-20T11:15:00+00:00", plan_5h_pct=61, plan_7d_pct=70),
    record(project="sample", unit="sample-014-export", role="worker", model="claude-opus-5-5", session_id=S2,
           requests=5, input_tokens=1000, output_tokens=500, cache_read_tokens=9000, cache_write_tokens=700,
           estimated_usd=1.25, active_seconds=1800, at="2026-09-21T09:00:00+00:00", plan_5h_pct=12, plan_7d_pct=74),
    record(project="demo", unit="demo-002-intro", role="worker", model="claude-sonnet-5", session_id=S3,
           requests=3, input_tokens=90, output_tokens=30, cache_read_tokens=900, cache_write_tokens=120,
           estimated_usd=0.75, active_seconds=900, at="2026-09-21T10:00:00+00:00", plan_5h_pct=20, plan_7d_pct=75),
)


class RollupCase(unittest.TestCase):
    """A scratch HOME with no launch.json and a scratch accounting root; the environment names neither root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.accounting_root = self.root / "accounting"
        self.accounting_root.mkdir()
        inherited = ("ROBOWRIGHT_SESSIONS_ROOT", "ROBOWRIGHT_ACCOUNTING_ROOT", "CLAUDE_USAGE_DIR",
                     "ROBOWRIGHT_PRICING_FILE", "ROBOWRIGHT_PRICING_NOW")
        self.env = {k: v for k, v in os.environ.items() if k not in inherited}
        self.pricing_file = self.root / "prices" / "pricing.json"
        self.pricing_file.parent.mkdir()
        self.pricing_file.write_text(json.dumps({"updated_at": PRICES_AS_OF, "source": "sample price page",
                                                 "default": OPUS_5_ROW, "models": {"claude-opus-5": OPUS_5_ROW}}) + "\n")
        self.env.update(HOME=str(self.home), ROBOWRIGHT_PRICING_FILE=str(self.pricing_file),
                        ROBOWRIGHT_PRICING_NOW=FRESH_TODAY)

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------ given

    def given_ledger(self, *lines):
        """records.jsonl from records (dicts) and raw lines (str), in order."""
        text = "".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines)
        (self.accounting_root / "records.jsonl").write_text(text)

    def given_run_json(self, name, text):
        """A scratch session dir <tmp>/session-dirs/<name> whose run.json holds this text (None: no run.json); returns the path a record's session_dir names."""
        session_dir = self.root / "session-dirs" / name
        session_dir.mkdir(parents=True, exist_ok=True)
        if text is not None:
            (session_dir / "run.json").write_text(text)
        return str(session_dir)

    def given_brief(self, name, **budget):
        """A scratch session dir whose run.json is a finished brief carrying these budget fields and no others."""
        return self.given_run_json(name, json.dumps({"ticket": name, "phase": "done", **budget}) + "\n")

    def given_dollar_session(self, name):
        """A scratch session dir whose brief budgets in dollars: a $40 threshold and a $60 cap."""
        return self.given_brief(name, spend_threshold_usd=40, spend_cap_usd=60)

    def in_dollar_sessions(self, *records):
        """These records, each named session_dir moved to a scratch dir of the same last name whose brief budgets in dollars; distinct dirs stay distinct."""
        return [dict(r, session_dir=self.given_dollar_session(Path(r["session_dir"]).name)) if r.get("session_dir") else r
                for r in records]

    # ------------------------------------------------------------ when

    def rollup(self, *flags, env=None, root_flag=True):
        args = [sys.executable, str(SCRIPT), *flags]
        if root_flag:
            args += ["--accounting-root", str(self.accounting_root)]
        return subprocess.run(args, env=env or self.env, capture_output=True, text=True)

    def rows(self, by, **kwargs):
        """--by <by> --json, as {row key: row}; fails the test on a non-zero exit or a duplicated key."""
        done = self.rollup("--by", by, "--json", **kwargs)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        keyed = {row["key"]: row for row in report["rows"]}
        self.assertEqual(len(keyed), len(report["rows"]), f"a key appears in two rows: {report['rows']}")
        return keyed

    # ------------------------------------------------------------ then

    def token_facts(self, row):
        return (row["requests"], row["input_tokens"], row["output_tokens"], row["cache_read_tokens"], row["cache_write_tokens"])


# ------------------------------------------------------------ R8 · a row per value of the --by field, summing session scope

class GroupingTests(RollupCase):
    def test_sums_requests_and_every_token_class_per_project(self):
        """--by project answers where the tokens went: sample's three records add to 8 requests and each class's total, demo's one record stands alone (U1 acceptance, D3)."""
        self.given_ledger(*LEDGER)

        rows = self.rows("project")

        self.assertEqual({key: self.token_facts(row) for key, row in rows.items()}, {
            "sample": (8, 1330, 567, 12400, 1060),
            "demo": (3, 90, 30, 900, 120),
        })

    def test_groups_by_the_named_field__for_unit_role_and_model(self):
        """Each --by groups on its own §6 field; a crossed field puts the unit's tokens under a role or a model (U1 acceptance: --by project|unit|role|model)."""
        self.given_ledger(*LEDGER)
        expected = {
            "unit": {"sample-013-ledger": 3, "sample-014-export": 5, "demo-002-intro": 3},
            "role": {"worker": 10, "subagent": 1},
            "model": {"claude-opus-5-5": 7, "claude-haiku-4-5": 1, "claude-sonnet-5": 3},
        }
        for by, requests in expected.items():
            with self.subTest(by=by):
                rows = self.rows(by)
                self.assertEqual({key: row["requests"] for key, row in rows.items()}, requests)

    def test_sums_the_records_estimated_usd_per_row(self):
        """The estimate per row is the sum of its records' estimates — 0.5 + 0.25 + 1.25 for sample — so the rollup agrees with the records it read (U1 acceptance)."""
        self.given_ledger(*self.in_dollar_sessions(*LEDGER))

        rows = self.rows("project")

        self.assertAlmostEqual(rows["sample"]["estimated_usd"], 2.0, places=6)
        self.assertAlmostEqual(rows["demo"]["estimated_usd"], 0.75, places=6)

    def test_never_adds_a_unit_scope_record_into_the_session_scope_rollup(self):
        """A unit record re-counts part of a session already counted; added in, U1's tokens appear twice (D3, Risk 1: "the rollup never sums the two together")."""
        self.given_ledger(record(scope="session", project="sample", requests=4),
                          record(scope="unit", unit_id="U1", project="sample", requests=3))

        done = self.rollup("--by", "project", "--json")

        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(report["scope"], "session")
        self.assertEqual([(row["key"], row["requests"]) for row in report["rows"]], [("sample", 4)])


# ------------------------------------------------------------ R9 · active hours and the last plan figure per row

class TimeAndPlanTests(RollupCase):
    def test_counts_each_session_s_active_time_once_per_row__when_it_has_several_records(self):
        """Every record of a session carries that session's active time, so a row adds it once per session: sample is S1's 3600 s + S2's 1800 s = 1.5 h, not 2.5 h; the worker row is S1 + S2 + S3 = 1.75 h (assumed Q8)."""
        self.given_ledger(*LEDGER)

        by_project = self.rows("project")
        by_role = self.rows("role")

        self.assertAlmostEqual(by_project["sample"]["active_hours"], 1.5, places=6)
        self.assertAlmostEqual(by_project["demo"]["active_hours"], 0.25, places=6)
        self.assertAlmostEqual(by_role["worker"]["active_hours"], 1.75, places=6)
        self.assertAlmostEqual(by_role["subagent"]["active_hours"], 1.0, places=6)

    def test_a_row_shows_the_plan_figures_of_its_latest_record(self):
        """Plan usage is a gauge, not a total: sample's row shows S2's 12 % and 74 %, written last, not the 61 % an earlier record carried (U1 acceptance: "the last plan %"; latest `at`, assumed Q9)."""
        self.given_ledger(*LEDGER)

        row = self.rows("project")["sample"]

        self.assertEqual((row["plan_5h_pct"], row["plan_7d_pct"]), (12, 74))

    def test_a_row_shows_the_latest_reading__not_a_later_record_that_has_none(self):
        """A migrated record is stamped at the migration and carries no reading; taking it as latest blanks a row that has a real one (end-of-stack re-review N1)."""
        self.given_ledger(record(at="2026-09-20T11:15:00+00:00", plan_5h_pct=50, plan_7d_pct=60),
                          record(at="2026-09-26T09:00:00+00:00", session_id=S2, source="migrate",
                                 plan_5h_pct=None, plan_7d_pct=None, plan_captured_at=None))

        row = self.rows("project")["sample"]

        self.assertEqual((row["plan_5h_pct"], row["plan_7d_pct"]), (50, 60))

    def test_latest_is_the_later_instant__across_a_utc_offset_change(self):
        """`at` carries the local offset, so the night clocks fall back 01:10-05:00 (06:10Z) is later than 01:30-04:00 (05:30Z) though it sorts first as text (U1 gate F3)."""
        self.given_ledger(record(at="2026-11-01T01:30:00-04:00", plan_5h_pct=10, plan_7d_pct=30),
                          record(at="2026-11-01T01:10:00-05:00", session_id=S2, plan_5h_pct=20, plan_7d_pct=40))

        row = self.rows("project")["sample"]

        self.assertEqual((row["plan_5h_pct"], row["plan_7d_pct"]), (20, 40))


# ------------------------------------------------------------ R10 · what the command accepts and prints

class CommandTests(RollupCase):
    def test_refuses_a_by_it_does_not_know__naming_the_flag_and_the_value(self):
        """`--by session` is no grouping this unit offers; answering with some other grouping, or none, reads as a real report (U1 acceptance: "refused by name"; wording assumed Q23)."""
        self.given_ledger(*LEDGER)

        done = self.rollup("--by", "session", "--json")

        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--by", done.stderr)
        self.assertIn("session", done.stderr)
        self.assertEqual(done.stdout, "")

    def test_prints_each_figure_on_the_row_s_line__without_json(self):
        """The text report is what the Owner reads: the row's line carries requests, each token class, the estimate, active hours and both plan figures (U1 acceptance)."""
        self.given_ledger(record(project="sample", requests=9, input_tokens=115, output_tokens=26,
                                 cache_read_tokens=348, cache_write_tokens=49, estimated_usd=0.75,
                                 active_seconds=5400, plan_5h_pct=17, plan_7d_pct=39,
                                 session_dir=self.given_dollar_session("sample-013-ledger")))

        done = self.rollup("--by", "project")

        self.assertEqual(done.returncode, 0, done.stderr)
        lines = [line for line in done.stdout.splitlines() if "sample" in line]
        self.assertEqual(len(lines), 1, done.stdout)
        for figure in ("9", "115", "26", "348", "49", "0.75", "1.5", "17", "39"):
            with self.subTest(figure=figure):
                self.assertRegex(lines[0], r"(?<![\d.])" + re.escape(figure) + r"(?![\d.])")

    def test_reports_no_rows_and_exits_0__when_the_ledger_does_not_exist(self):
        """A fresh install has no ledger until its first session ends; that is an empty report, not an error a dashboard has to special-case (assumed Q10)."""
        report = self.rollup("--by", "project", "--json")

        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertEqual(json.loads(report.stdout)["rows"], [])

    def test_skips_a_line_that_is_not_a_record(self):
        """A writer that died mid-append leaves a fragment; one bad line must not hide every good one (assumed Q11)."""
        self.given_ledger(record(project="sample", session_id=S1, requests=4),
                          '{"scope": "session", "session_id": "d4d4',
                          record(project="sample", session_id=S2, requests=6))

        rows = self.rows("project")

        self.assertEqual(rows["sample"]["requests"], 10)

    def test_reads_the_ledger_under_ROBOWRIGHT_ACCOUNTING_ROOT__without_the_flag(self):
        """The rollup resolves the accounting root as the writer does; reading another root reports a ledger nothing appends to (Language: accounting root)."""
        self.given_ledger(record(project="sample", requests=4))

        rows = self.rows("project", env=dict(self.env, ROBOWRIGHT_ACCOUNTING_ROOT=str(self.accounting_root)), root_flag=False)

        self.assertEqual(rows["sample"]["requests"], 4)



# ------------------------------------------------------------ U2 · the rollup names its prices' date, warns when stale, and has no USD without them

class PricingTests(RollupCase):
    def setUp(self):
        super().setUp()
        self.missing = self.root / "nowhere" / "pricing.json"

    def without_pricing_file(self):
        return dict(self.env, ROBOWRIGHT_PRICING_FILE=str(self.missing))

    def stale_lines(self, done):
        return [line for line in (done.stdout + done.stderr).splitlines() if "stale" in line.lower()]

    def test_says_prices_as_of_the_pricing_file_s_updated_at(self):
        """The rollup is the report the Owner reads most; it names the prices' date like every other report (D2: "every report prints prices as of <updated_at>")."""
        self.given_ledger(*LEDGER)

        done = self.rollup("--by", "project")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"prices as of {PRICES_AS_OF}", done.stdout)

    def test_warns_once_that_prices_are_stale__when_the_file_is_31_days_old(self):
        """One warning line for the report, not one per row (D2; Language: stale — "prints one warning line"; the line says "stale", assumed Q3)."""
        self.given_ledger(*LEDGER)

        done = self.rollup("--by", "project", env=dict(self.env, ROBOWRIGHT_PRICING_NOW=THIRTY_ONE_DAYS_ON))

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.stale_lines(done)), 1, done.stdout + done.stderr)

    def test_every_row_s_usd_is_null_and_its_token_facts_unchanged__when_the_pricing_file_is_missing(self):
        """The U2 row lists robowright-cost.py among the reports that "print USD null … with unchanged token counts when the file is missing"; tokens are facts and stay (D9; the rollup nulls sums of records priced earlier too, assumed Q7)."""
        self.given_ledger(*self.in_dollar_sessions(*LEDGER))

        rows = self.rows("project", env=self.without_pricing_file())

        for key, row in rows.items():
            with self.subTest(row=key):
                self.assertIsNone(row["estimated_usd"])
        self.assertEqual(self.token_facts(rows["sample"]), (8, 1330, 567, 12400, 1060))
        self.assertEqual(self.token_facts(rows["demo"]), (3, 90, 30, 900, 120))

    def test_says_the_pricing_file_is_missing_in_exactly_one_stderr_line(self):
        """One line for the report, however many rows (D9: "with one stderr line")."""
        self.given_ledger(*LEDGER)

        done = self.rollup("--by", "project", "--json", env=self.without_pricing_file())

        self.assertEqual(done.returncode, 0, done.stderr)
        lines = [line for line in done.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, done.stderr)

    def test_the_text_report_prints_no_estimate_column_and_keeps_the_row_s_tokens__when_the_pricing_file_is_missing(self):
        """With no pricing file no row has a figure, so the table drops the est usd column rather than printing n/a, and still prints the token figures (fixes F1 rule 2, superseding U2's assumed Q5 "n/a in text" — Decided (Lead) 2026-09-27; assumed Q7)."""
        self.given_ledger(record(project="sample", requests=9, input_tokens=115, output_tokens=26,
                                 cache_read_tokens=348, cache_write_tokens=49, estimated_usd=0.75,
                                 session_dir=self.given_dollar_session("sample-013-ledger")))

        done = self.rollup("--by", "project", env=self.without_pricing_file())

        self.assertEqual(done.returncode, 0, done.stderr)
        lines = [line for line in done.stdout.splitlines() if "sample" in line]
        self.assertEqual(len(lines), 1, done.stdout)
        self.assertNotIn("n/a", lines[0])
        self.assertNotIn("est usd", done.stdout.splitlines()[0])
        self.assertNotRegex(lines[0], r"(?<![\d.])0\.75(?![\d.])")
        for figure in ("9", "115", "26", "348", "49"):
            with self.subTest(figure=figure):
                self.assertRegex(lines[0], r"(?<![\d.])" + re.escape(figure) + r"(?![\d.])")

    def test_a_row_whose_every_record_carries_a_null_estimate_has_a_null_estimate__not_zero(self):
        """Records written while the file was missing carry estimated_usd null; summing them to $0.00 reports free work (§6: "estimated_usd — null when pricing.json is missing"; assumed Q8)."""
        self.given_ledger(*self.in_dollar_sessions(
                          record(project="sample", session_id=S1, estimated_usd=None, price_as_of=None),
                          record(project="sample", session_id=S2, estimated_usd=None, price_as_of=None),
                          record(project="demo", session_id=S3, estimated_usd=0.75, price_as_of=PRICES_AS_OF)))

        rows = self.rows("project")

        self.assertIsNone(rows["sample"]["estimated_usd"])
        self.assertAlmostEqual(rows["demo"]["estimated_usd"], 0.75, places=6)


# ============================================================ U4 · --migrate, --since, --project
#
# Written from the accounting brief's U4 behaviors file before --migrate existed. Two finished
# synthetic sessions sit under a scratch sessions root; their transcripts sit under the scratch
# HOME's ~/.claude/projects, in the project dir Claude Code names after each worktree.
#
# Session A, pinned (sample-013-ledger; project "sample"; transcripts pins SA1 and SA2; SAX is a
# stray transcript in the same worktree project dir that nothing pinned):
#
#     at (Z)              what                                         model     in    out   c.read  c.write
#     09-20 10:00         msg_a1  SA1 main                             opus      1000  100   10000   1000
#     09-20 10:10         unit-start U1
#     09-20 10:20         msg_a2  SA1 main                             opus      2000  200   20000   0
#     09-20 10:25         msg_x1  SAX (stray, never measured)          sonnet    9000  900   90000   9000
#     09-20 10:30         msg_g1  SA1 sidecar, meta reviewer-gate      sonnet    3000  300   0       3000
#     09-20 10:35→10:40   stop → resume (300 s)
#     09-20 10:50         unit-close U1
#     09-20 11:00         msg_a3  SA1 main                             opus      4000  400   40000   0
#     09-21 09:00         unit-start U2
#     09-21 09:10         msg_a4  SA2 main                             opus      5000  500   50000   500
#     09-21 09:30         msg_a5  SA2 main                             opus      6000  600   60000   0
#     09-21 09:45         unit-close U2
#
# Session B, unpinned (sample-014-export; project null; transcripts null; SB1 and SB2 in its worktree
# project dir):
#
#     09-22 08:00         unit-start U1
#     09-22 08:10         msg_c1  SB1                                  opus      1500  150   15000   1500
#     09-22 08:40         msg_c2  SB1                                  opus      2500  250   25000   0
#     09-22 08:50         unit-close U1
#     09-23 07:00         msg_d1  SB2                                  opus      700   70    7000    0
#     09-23 07:15         msg_d2  SB2                                  opus      800   80    8000    0
#
# A migrate over A+B appends 9 records: 5 session-scope (SA1 worker·opus, SA1 reviewer-code·sonnet,
# SA2, SB1, SB2) and 4 unit-scope (A-U1 worker·opus and reviewer-code·sonnet, A-U2, B-U1).

RUN_COST = HERE.parent.parent / "worker" / "scripts" / "run-cost.py"
GROUP_REGEX = "^([a-z]+)-[0-9]+-"
OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5"
HAIKU = "claude-haiku-4-5"
PINNED_DIR = "sample-013-ledger"
UNPINNED_DIR = "sample-014-export"

SA1 = "e5e5e5e5-0000-4000-8000-0000000000a1"
SA2 = "e5e5e5e5-0000-4000-8000-0000000000a2"
SAX = "e5e5e5e5-0000-4000-8000-0000000000af"
SB1 = "e5e5e5e5-0000-4000-8000-0000000000b1"
SB2 = "e5e5e5e5-0000-4000-8000-0000000000b2"
SC1 = "e5e5e5e5-0000-4000-8000-0000000000c1"
SD1 = "e5e5e5e5-0000-4000-8000-0000000000d1"
SE1 = "e5e5e5e5-0000-4000-8000-0000000000e1"
SL = "e5e5e5e5-0000-4000-8000-0000000000f1"
S4 = "d4d4d4d4-0000-4000-8000-000000000004"
S5 = "d4d4d4d4-0000-4000-8000-000000000005"

# {session id: (main rows, sidecars)}; a row is (message id, model, timestamp, in, out, cache read,
# cache write); a sidecar is (name, agentType, rows).
PINNED_MAIN = {
    SA1: ((("msg_a1", OPUS, "2026-09-20T10:00:00.000Z", 1000, 100, 10000, 1000),
           ("msg_a2", OPUS, "2026-09-20T10:20:00.000Z", 2000, 200, 20000, 0),
           ("msg_a3", OPUS, "2026-09-20T11:00:00.000Z", 4000, 400, 40000, 0)),
          (("gate", "reviewer-gate", (("msg_g1", SONNET, "2026-09-20T10:30:00.000Z", 3000, 300, 0, 3000),)),)),
    SA2: ((("msg_a4", OPUS, "2026-09-21T09:10:00.000Z", 5000, 500, 50000, 500),
           ("msg_a5", OPUS, "2026-09-21T09:30:00.000Z", 6000, 600, 60000, 0)), ()),
}
PINNED_STRAY = {
    SAX: ((("msg_x1", SONNET, "2026-09-20T10:25:00.000Z", 9000, 900, 90000, 9000),), ()),
}
PINNED_EVENTS = (
    ("2026-09-20T10:10:00+00:00", "unit-start", "U1"),
    ("2026-09-20T10:35:00+00:00", "stop", None),
    ("2026-09-20T10:40:00+00:00", "resume", None),
    ("2026-09-20T10:50:00+00:00", "unit-close", "U1"),
    ("2026-09-21T09:00:00+00:00", "unit-start", "U2"),
    ("2026-09-21T09:45:00+00:00", "unit-close", "U2"),
)
UNPINNED_MAIN = {
    SB1: ((("msg_c1", OPUS, "2026-09-22T08:10:00.000Z", 1500, 150, 15000, 1500),
           ("msg_c2", OPUS, "2026-09-22T08:40:00.000Z", 2500, 250, 25000, 0)), ()),
    SB2: ((("msg_d1", OPUS, "2026-09-23T07:00:00.000Z", 700, 70, 7000, 0),
           ("msg_d2", OPUS, "2026-09-23T07:15:00.000Z", 800, 80, 8000, 0)), ()),
}
UNPINNED_EVENTS = (
    ("2026-09-22T08:00:00+00:00", "unit-start", "U1"),
    ("2026-09-22T08:50:00+00:00", "unit-close", "U1"),
)


def transcript_lines(rows):
    """Assistant records in the transcript shape run-cost.py reads: timestamp, message id, model, usage."""
    return "".join(json.dumps({
        "type": "assistant", "timestamp": at, "uuid": f"uuid-{msg_id}-{n}",
        "message": {"id": msg_id, "type": "message", "role": "assistant", "model": model,
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": inp, "output_tokens": out,
                              "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": cache_write}},
    }) + "\n" for n, (msg_id, model, at, inp, out, cache_read, cache_write) in enumerate(rows))


class MigrateCase(RollupCase):
    """RollupCase plus a scratch sessions root, a scratch ~/.claude/projects, a launch.json holding only
    unit.group_regex, and a usage dir with no reading in it."""

    def setUp(self):
        super().setUp()
        self.sessions = self.root / "sessions"
        self.sessions.mkdir()
        self.projects = self.home / ".claude" / "projects"
        self.env["CLAUDE_USAGE_DIR"] = str(self.root / "usage")
        self.given_launch_json(unit={"group_regex": GROUP_REGEX})

    # ------------------------------------------------------------ given

    def given_launch_json(self, **keys):
        path = self.home / ".claude" / "robowright" / "launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Every install's launch.json carries `repos` (owner_git.py); the rollup reads past it.
        path.write_text(json.dumps(dict({"repos": ["~/Code/sample"]}, **keys)) + "\n")

    def given_session_dir(self, name, *, ticket, project, pinned, main, stray=None, events=(), phase="done"):
        """A session dir under the sessions root and its transcripts under the worktree's project dir.
        pinned: run.json.transcripts names every main transcript (home-relative, as pin_session writes
        it); else it is null. stray: transcripts written beside them that run.json never names."""
        worktree = f"/Users/owner/worktrees/{name}"
        slug = re.sub(r"[^A-Za-z0-9]", "-", worktree)
        project_dir = self.projects / slug
        project_dir.mkdir(parents=True, exist_ok=True)
        for session_id, (rows, sidecars) in {**main, **(stray or {})}.items():
            (project_dir / f"{session_id}.jsonl").write_text(transcript_lines(rows))
            for side_name, agent_type, side_rows in sidecars:
                side = project_dir / session_id / "subagents"
                side.mkdir(parents=True, exist_ok=True)
                (side / f"agent-{side_name}.jsonl").write_text(transcript_lines(side_rows))
                (side / f"agent-{side_name}.meta.json").write_text(json.dumps({"agentType": agent_type, "description": "sample task"}))
        session_dir = self.sessions / name
        session_dir.mkdir(exist_ok=True)
        run = {"ticket": ticket, "project": project, "worktree": worktree, "phase": phase,
               "transcripts": [f"~/.claude/projects/{slug}/{sid}.jsonl" for sid in main] if pinned else None,
               "session_id": list(main)[-1] if main else None, "units": []}
        (session_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        if events:
            (session_dir / "events.jsonl").write_text("".join(json.dumps(dict(
                {"n": n, "at": at, "event": event, "machine": "unit" if unit else "session"},
                **({"unit": unit} if unit else {}))) + "\n" for n, (at, event, unit) in enumerate(events, 1)))
        return session_dir

    def given_pinned_session(self):
        return self.given_session_dir(PINNED_DIR, ticket=PINNED_DIR, project="sample", pinned=True,
                                      main=PINNED_MAIN, stray=PINNED_STRAY, events=PINNED_EVENTS)

    def given_unpinned_session(self):
        return self.given_session_dir(UNPINNED_DIR, ticket=UNPINNED_DIR, project=None, pinned=False,
                                      main=UNPINNED_MAIN, events=UNPINNED_EVENTS)

    def given_one_request_session(self, name, session_id, *, ticket, project, phase="done"):
        """A pinned session dir with one opus request and no events."""
        return self.given_session_dir(name, ticket=ticket, project=project, pinned=True, phase=phase, main={
            session_id: ((("msg_solo_" + session_id[-2:], OPUS, "2026-09-24T12:00:00.000Z", 1200, 120, 12000, 0),), ())})

    # ------------------------------------------------------------ when

    def migrate(self, *flags, runs_root=None, env=None):
        return self.rollup("--migrate", "--runs-root", str(runs_root or self.sessions), *flags, env=env)

    # ------------------------------------------------------------ then

    def ledger_bytes(self):
        path = self.accounting_root / "records.jsonl"
        return path.read_bytes() if path.exists() else None

    def ledger_records(self):
        path = self.accounting_root / "records.jsonl"
        records = []
        for line in (path.read_text().splitlines() if path.exists() else []):
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
        return records

    def migrated(self):
        return [r for r in self.ledger_records() if r.get("source") == "migrate"]

    @staticmethod
    def identity(r):
        """(scope, session dir name, unit_id, session_id, role, model): which record this is."""
        return (r.get("scope"), os.path.basename(r.get("session_dir") or ""), r.get("unit_id"),
                r.get("session_id"), r.get("role"), r.get("model"))

    @staticmethod
    def facts(r):
        return (r["requests"], r["input_tokens"], r["output_tokens"], r["cache_read_tokens"], r["cache_write_tokens"])

    @staticmethod
    def lines_naming(done, name):
        return [line for line in (done.stdout + done.stderr).splitlines() if name in line]


# ------------------------------------------------------------ R2–R4 · the records a migrate appends

class MigrateRecordTests(MigrateCase):
    def test_appends_session_and_unit_records_for_each_claude_session_and_closed_unit(self):
        """--migrate backfills both scopes: one session record per (Claude session, role, model) and one unit record per closed unit's (session, role, model); a missing scope leaves --by unit-id or --by project blind to the past (U4 row; D3; D10; assumed U4 Q2)."""
        self.given_pinned_session()
        self.given_unpinned_session()

        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertCountEqual([self.identity(r) for r in self.ledger_records()], [
            ("session", PINNED_DIR, None, SA1, "worker", OPUS),
            ("session", PINNED_DIR, None, SA1, "reviewer-code", SONNET),
            ("session", PINNED_DIR, None, SA2, "worker", OPUS),
            ("session", UNPINNED_DIR, None, SB1, "worker", OPUS),
            ("session", UNPINNED_DIR, None, SB2, "worker", OPUS),
            ("unit", PINNED_DIR, "U1", SA1, "worker", OPUS),
            ("unit", PINNED_DIR, "U1", SA1, "reviewer-code", SONNET),
            ("unit", PINNED_DIR, "U2", SA2, "worker", OPUS),
            ("unit", UNPINNED_DIR, "U1", SB1, "worker", OPUS),
        ])

    def test_every_migrated_record_is_tagged_source_migrate(self):
        """A backfilled record says it was backfilled; tagged "hook", nobody can tell reconstructed history from a measured session end (D12: records "tagged source: migrate")."""
        self.given_pinned_session()
        self.given_unpinned_session()

        self.migrate()

        self.assertEqual({r["source"] for r in self.ledger_records()}, {"migrate"})

    def test_a_pinned_session_s_records_say_pinned__and_an_unpinned_one_s_say_not(self):
        """transcripts_pinned is how a reader knows a figure may include other sessions of the worktree; wrong, an overstated figure looks exact (U4 row: "the unpinned one with transcripts_pinned: false"; §6)."""
        self.given_pinned_session()
        self.given_unpinned_session()

        self.migrate()

        by_dir = {}
        for r in self.ledger_records():
            by_dir.setdefault(os.path.basename(r["session_dir"]), set()).add(r["transcripts_pinned"])
        self.assertEqual(by_dir, {PINNED_DIR: {True}, UNPINNED_DIR: {False}})

    def test_a_pinned_session_measures_only_its_pinned_transcripts__not_others_in_its_worktree_project_dir(self):
        """With transcripts pinned, a stray session in the same worktree is not this session's work; counted, it inflates both scopes (D12: "transcripts from run.json.transcripts else the worktree project dir")."""
        self.given_pinned_session()

        self.migrate()

        self.assertEqual({r["session_id"] for r in self.ledger_records()}, {SA1, SA2})

    def test_an_unpinned_session_measures_every_claude_session_in_its_worktree_project_dir(self):
        """With nothing pinned, each transcript in the worktree project dir is one Claude session with its own records; one merged record hides a rotation (D12 fallback; §6 "the transcript's basename on migrate"; assumed U4 Q2, Q3)."""
        self.given_unpinned_session()

        self.migrate()

        self.assertCountEqual([r["session_id"] for r in self.ledger_records() if r["scope"] == "session"], [SB1, SB2])

    def test_a_session_record_counts_its_own_transcript_and_its_sidecars(self):
        """Each session record sums its own transcript and sidecars, per role and model — SA1's opus is a1+a2+a3, its gate sidecar is reviewer-code (D4; D7; fixture arithmetic)."""
        self.given_pinned_session()
        self.given_unpinned_session()

        self.migrate()

        self.assertEqual({(r["session_id"], r["role"], r["model"]): self.facts(r)
                          for r in self.ledger_records() if r["scope"] == "session"}, {
            (SA1, "worker", OPUS): (3, 7000, 700, 70000, 1000),
            (SA1, "reviewer-code", SONNET): (1, 3000, 300, 0, 3000),
            (SA2, "worker", OPUS): (2, 11000, 1100, 110000, 500),
            (SB1, "worker", OPUS): (2, 4000, 400, 40000, 1500),
            (SB2, "worker", OPUS): (2, 1500, 150, 15000, 0),
        })

    def test_a_session_record_s_active_time_is_its_transcript_span_minus_a_stop_to_resume_gap(self):
        """SA1 spans 10:00→11:00 with a 300 s stop inside, so 3600 wall and 3300 active; a gap left in bills the Owner's pause as work (§3.3: "gaps are the same events, clipped to it")."""
        self.given_pinned_session()
        self.given_unpinned_session()

        self.migrate()

        self.assertEqual({(r["session_id"], r["role"]): (r["wall_seconds"], r["active_seconds"])
                          for r in self.ledger_records() if r["scope"] == "session"}, {
            (SA1, "worker"): (3600, 3300),
            (SA1, "reviewer-code"): (3600, 3300),
            (SA2, "worker"): (1200, 1200),
            (SB1, "worker"): (1800, 1800),
            (SB2, "worker"): (900, 900),
        })

    def test_a_unit_record_counts_only_the_requests_inside_its_window(self):
        """A-U1 runs 10:10→10:50: a2 and the gate sidecar count, a1 before and a3 after do not, and the stray x1 is not pinned (D10: "unit-start to the first unit-close after it")."""
        self.given_pinned_session()
        self.given_unpinned_session()

        self.migrate()

        self.assertEqual({(os.path.basename(r["session_dir"]), r["unit_id"], r["session_id"], r["role"], r["model"]): self.facts(r)
                          for r in self.ledger_records() if r["scope"] == "unit"}, {
            (PINNED_DIR, "U1", SA1, "worker", OPUS): (1, 2000, 200, 20000, 0),
            (PINNED_DIR, "U1", SA1, "reviewer-code", SONNET): (1, 3000, 300, 0, 3000),
            (PINNED_DIR, "U2", SA2, "worker", OPUS): (2, 11000, 1100, 110000, 500),
            (UNPINNED_DIR, "U1", SB1, "worker", OPUS): (2, 4000, 400, 40000, 1500),
        })

    def test_a_unit_record_s_active_time_is_its_window_minus_a_stop_to_resume_gap(self):
        """A-U1's window is 2400 s with a 300 s stop inside it, so 2100 active; the other windows have no gap (D10: "active_seconds is the window minus every stop → resume gap inside it")."""
        self.given_pinned_session()
        self.given_unpinned_session()

        self.migrate()

        self.assertEqual({(os.path.basename(r["session_dir"]), r["unit_id"], r["role"]): (r["wall_seconds"], r["active_seconds"])
                          for r in self.ledger_records() if r["scope"] == "unit"}, {
            (PINNED_DIR, "U1", "worker"): (2400, 2100),
            (PINNED_DIR, "U1", "reviewer-code"): (2400, 2100),
            (PINNED_DIR, "U2", "worker"): (2700, 2700),
            (UNPINNED_DIR, "U1", "worker"): (3000, 3000),
        })

    def test_a_scheduled_task_run_is_measured_in_both_scopes__though_it_sits_outside_the_worktree_project_dir(self):
        """A desktop scheduled-task run lives in the Lead folder's project dir and names its session dir in a ROBOWRIGHT_RUN_DIR line; unit records from it with no session record leave the session out of every --by (U4 gate F1; run.json.cost counts it the same way)."""
        session_dir = self.given_session_dir("sample-022-sched", ticket="sample-022-sched", project=None, pinned=False,
                                             main={}, events=UNPINNED_EVENTS)
        lead_dir = self.projects / "-Users-owner-lead"
        lead_dir.mkdir(parents=True)
        prompt = {"type": "user", "timestamp": "2026-09-22T08:00:30.000Z", "message": {"role": "user", "content":
                  f"<scheduled-task name=\"sample\">\n/worker {session_dir}\nROBOWRIGHT_RUN_DIR={session_dir}\n</scheduled-task>"}}
        (lead_dir / f"{SC1}.jsonl").write_text(json.dumps(prompt) + "\n" + transcript_lines(UNPINNED_MAIN[SB1][0]))

        self.migrate()

        self.assertCountEqual([self.identity(r) for r in self.ledger_records()], [
            ("session", "sample-022-sched", None, SC1, "worker", OPUS),
            ("unit", "sample-022-sched", "U1", SC1, "worker", OPUS),
        ])

    def test_two_finished_dirs_on_one_worktree_record_each_claude_session_once(self):
        """Two unpinned dirs that ran in the same worktree both resolve SB1 and SB2; appended once per dir, every --by counts those sessions twice. The first dir by name owns them, as a second migrate would leave it (U4 gate 2 F1; D3 "one record per (session, role bucket, model)")."""
        self.given_unpinned_session()
        worktree_twin = self.given_session_dir("sample-015-rerun", ticket="sample-015-rerun", project=None, pinned=False,
                                               main={}, events=())
        run = json.loads((worktree_twin / "run.json").read_text())
        run["worktree"] = f"/Users/owner/worktrees/{UNPINNED_DIR}"
        (worktree_twin / "run.json").write_text(json.dumps(run) + "\n")

        self.migrate()

        self.assertCountEqual([self.identity(r) for r in self.ledger_records() if r["scope"] == "session"], [
            ("session", UNPINNED_DIR, None, SB1, "worker", OPUS),
            ("session", UNPINNED_DIR, None, SB2, "worker", OPUS),
        ])

    def given_worktree_twin(self, name, *, phase, pins=(), session_id=None):
        """A session dir that ran in UNPINNED_DIR's worktree, holding no transcripts of its own: pins names
        transcripts in that worktree's project dir, as pin_session writes them."""
        twin = self.given_session_dir(name, ticket=name, project=None, pinned=False, main={}, phase=phase)
        worktree = f"/Users/owner/worktrees/{UNPINNED_DIR}"
        slug = re.sub(r"[^A-Za-z0-9]", "-", worktree)
        run = json.loads((twin / "run.json").read_text())
        run.update(worktree=worktree, session_id=session_id,
                   transcripts=[f"~/.claude/projects/{slug}/{sid}.jsonl" for sid in pins] or None)
        (twin / "run.json").write_text(json.dumps(run) + "\n")
        return twin

    def given_unpinned_session_last_seen_as(self, session_id):
        unpinned = self.given_unpinned_session()
        run = json.loads((unpinned / "run.json").read_text())
        run["session_id"] = session_id
        (unpinned / "run.json").write_text(json.dumps(run) + "\n")

    def test_an_unpinned_dir_leaves_out_a_session_a_live_dir_on_its_worktree_names(self):
        """SB2 is a live session's, which its session end records; recorded now under the unpinned dir, it takes SB2's key and the live dir's own record is never written (end-of-stack F2)."""
        self.given_unpinned_session_last_seen_as(SB1)
        self.given_worktree_twin("sample-016-live", phase="implementing", session_id=SB2)

        self.migrate()

        self.assertEqual({r["session_id"] for r in self.ledger_records() if r["scope"] == "session"}, {SB1})

    def test_a_session_pinned_by_a_later_dir_on_the_same_worktree_is_recorded_under_that_dir(self):
        """The pin says whose SB2 is; the first dir by name taking it because nothing is pinned in that dir puts the cost under the wrong unit of work (end-of-stack F2; U4 gate 2 N1)."""
        self.given_unpinned_session_last_seen_as(SB1)
        self.given_worktree_twin("sample-016-pinned", phase="done", pins=(SB2,), session_id=SB2)

        self.migrate()

        self.assertCountEqual([self.identity(r) for r in self.ledger_records() if r["scope"] == "session"], [
            ("session", UNPINNED_DIR, None, SB1, "worker", OPUS),
            ("session", "sample-016-pinned", None, SB2, "worker", OPUS),
        ])

    def test_an_unpinned_dir_s_unit_leaves_out_a_session_a_live_dir_on_its_worktree_names(self):
        """SL ran inside the unpinned dir's U1 window but is the live dir's; counted, U1 carries another unit of work's requests (end-of-stack F2)."""
        self.given_session_dir(UNPINNED_DIR, ticket=UNPINNED_DIR, project=None, pinned=False, main=UNPINNED_MAIN,
                               events=UNPINNED_EVENTS, stray={
                                   SL: ((("msg_l1", OPUS, "2026-09-22T08:20:00.000Z", 900, 90, 9000, 0),), ())})
        self.given_worktree_twin("sample-016-live", phase="implementing", session_id=SL)

        self.migrate()

        self.assertEqual({r["session_id"] for r in self.ledger_records() if r["scope"] == "unit"}, {SB1})

    def test_a_session_a_later_dir_only_pins_is_recorded_under_that_dir(self):
        """After a --rotate, run.json.session_id names the new session and the earlier one is claimed only by its pin (end-of-stack re-review N3)."""
        self.given_unpinned_session_last_seen_as(SB1)
        self.given_worktree_twin("sample-016-pinned", phase="done", pins=(SB2,), session_id=None)

        self.migrate()

        self.assertCountEqual([self.identity(r) for r in self.ledger_records() if r["scope"] == "session"], [
            ("session", UNPINNED_DIR, None, SB1, "worker", OPUS),
            ("session", "sample-016-pinned", None, SB2, "worker", OPUS),
        ])

    def test_a_migrated_record_carries_no_plan_reading__though_one_exists_today(self):
        """Today's 5-hour and 7-day figures say nothing about a session that ended days ago; written into its record, they read as that session's plan use (end-of-stack F3)."""
        usage = self.root / "usage"
        usage.mkdir()
        (usage / "latest.json").write_text(json.dumps({"captured_at": "2026-09-26T09:00:00+00:00",
                                                       "five_hour": {"used_percentage": 41},
                                                       "seven_day": {"used_percentage": 63}}))
        self.given_pinned_session()

        self.migrate()

        self.assertEqual({(r["plan_5h_pct"], r["plan_7d_pct"], r["plan_captured_at"]) for r in self.migrated()},
                         {(None, None, None)})

    def test_names_the_unit_of_work__the_unit_id__and_the_session_dir(self):
        """unit is the ticket, unit_id is set on unit scope only, session_dir is the absolute physical dir; a crossed field files the work under another brief (§6)."""
        self.given_pinned_session()
        self.given_unpinned_session()

        self.migrate()

        pinned, unpinned = str(self.sessions / PINNED_DIR), str(self.sessions / UNPINNED_DIR)
        self.assertEqual({(r["scope"], r["session_dir"], r["unit"], r["unit_id"]) for r in self.ledger_records()}, {
            ("session", pinned, PINNED_DIR, None),
            ("session", unpinned, UNPINNED_DIR, None),
            ("unit", pinned, PINNED_DIR, "U1"),
            ("unit", pinned, PINNED_DIR, "U2"),
            ("unit", unpinned, UNPINNED_DIR, "U1"),
        })


# ------------------------------------------------------------ R4 · project, and run.json left alone

class MigrateProjectTests(MigrateCase):
    def test_project_is_the_group_regex_capture_of_the_ticket__when_run_json_has_none(self):
        """Sessions from before U1 have project null; without the capture every backfilled record lands in a null row of --by project (U4 row: "project from group_regex"; D8; assumed U4 Q4, F1)."""
        self.given_unpinned_session()

        self.migrate()

        self.assertEqual({r["project"] for r in self.ledger_records()}, {"sample"})

    def test_keeps_the_project_run_json_already_names(self):
        """A project the launcher already wrote is the session's project; re-deriving it from the ticket files demo's work under sample (D8: written "when null"; assumed U4 Q4, F1)."""
        self.given_one_request_session("sample-015-audit", SC1, ticket="sample-015-audit", project="demo")

        self.migrate()

        self.assertEqual({r["project"] for r in self.ledger_records()}, {"demo"})

    def test_project_is_null__when_the_ticket_matches_no_group(self):
        """A ticket outside every group has no project; inventing one (the ticket, the dir name) makes a phantom --by project row (assumed U4 Q4, F1: "a ticket that does not match gives project: null")."""
        self.given_one_request_session("scratchpad", SE1, ticket="scratchpad", project=None)

        self.migrate()

        records = self.ledger_records()
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["project"])

    def test_writes_no_project_back_into_run_json(self):
        """--migrate backfills the ledger and nothing else; a run.json write races the launcher's lock-held project write (assumed U4 Q8; D8)."""
        session_dir = self.given_unpinned_session()
        before = (session_dir / "run.json").read_bytes()

        self.migrate()

        self.assertEqual((session_dir / "run.json").read_bytes(), before)


# ------------------------------------------------------------ R1 · which session dirs are migrated

class MigrateSkipTests(MigrateCase):
    def test_skips_by_name_a_session_dir_without_run_json(self):
        """A dir with no run.json is no finished session; skipped silently, the Owner cannot tell it was looked at, and failing on it stops the backfill (U4 row: "skipped by name"; assumed U4 Q5)."""
        self.given_pinned_session()
        self.given_unpinned_session()
        (self.sessions / "sample-017-empty").mkdir()
        (self.sessions / "sample-017-empty" / "BRIEF.md").write_text("# sample\n")

        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len([line for line in self.lines_naming(done, "sample-017-empty") if "skip" in line.lower()]), 1)
        self.assertEqual(len(self.ledger_records()), 9)

    def test_skips_by_name_a_session_whose_phase_is_not_done(self):
        """A session still running (or stopped, or parked) is not finished; migrated now, its hook's own records later are blocked by the partial ones (U4 row: "phase other than done is skipped by name"; assumed U4 Q5 for the wording)."""
        self.given_pinned_session()
        for phase in ("implement", "stopped", "parked"):
            with self.subTest(phase=phase):
                self.given_one_request_session("sample-016-draft", SD1, ticket="sample-016-draft", project="sample", phase=phase)

                done = self.migrate()

                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(len([line for line in self.lines_naming(done, "sample-016-draft") if "skip" in line.lower()]), 1)
                self.assertEqual([r for r in self.ledger_records() if os.path.basename(r["session_dir"]) == "sample-016-draft"], [])

    def test_skips_by_name_a_session_dir_whose_run_json_is_not_json(self):
        """One damaged run.json must not end the backfill of every other session, nor pass unnoticed (assumed U4 Q6)."""
        self.given_pinned_session()
        self.given_unpinned_session()
        (self.sessions / "sample-018-broken").mkdir()
        (self.sessions / "sample-018-broken" / "run.json").write_text("{not json\n")

        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len([line for line in self.lines_naming(done, "sample-018-broken") if "skip" in line.lower()]), 1)
        self.assertEqual(len(self.ledger_records()), 9)

    def test_says_once_that_doc_role_sessions_are_not_migrated(self):
        """Planner, Lead and Explainer sessions before this brief left no marker; the Owner is told once why they are absent, not once per dir (§4 Step 4: "says so once"; D12; assumed U4 Q7)."""
        self.given_pinned_session()
        self.given_unpinned_session()

        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len([line for line in (done.stdout + done.stderr).splitlines() if re.search(r"doc.role", line, re.I)]), 1)


# ------------------------------------------------------------ SW-21 · a planted ledger link (tests/run-launch/BEHAVIORS.md)

class MigrateSessionWriteTests(MigrateCase):
    def test_refuses_a_ledger_link_and_writes_nothing_through_it(self):
        """SW-21: --migrate appends through run-cost's append_records, whose refusal is not an OSError; review 3 P2-1."""
        self.given_pinned_session()
        self.accounting_root.mkdir(parents=True, exist_ok=True)
        target = self.root / "target-records"
        target.write_text("the Owner's file\n")
        (self.accounting_root / "records.jsonl").symlink_to(target)

        done = self.migrate()

        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("refused:", done.stderr)
        self.assertEqual(target.read_text(), "the Owner's file\n")


# ------------------------------------------------------------ R5–R6 · idempotent and append-only

class MigrateIdempotencyTests(MigrateCase):
    def hook_records(self, scope, unit_id=None, source="hook"):
        """What the hook path wrote for SA1 of session A: worker·opus and reviewer-code·sonnet, keyed by A's physical dir."""
        common = dict(scope=scope, unit_id=unit_id, source=source, session_id=SA1, project="sample", unit=PINNED_DIR,
                      session_dir=str(self.sessions / PINNED_DIR))
        return [record(role="worker", model=OPUS, **common), record(role="reviewer-code", model=SONNET, **common)]

    def test_a_second_migrate_appends_nothing_and_says_so(self):
        """Run twice, the backfill must not double the past; silent, the Owner cannot tell "nothing to do" from "failed" (U4 row: "a second --migrate appends nothing and says so"; assumed U4 Q5)."""
        self.given_pinned_session()
        self.given_unpinned_session()
        self.migrate()
        before = self.ledger_bytes()

        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.ledger_bytes(), before)
        self.assertIn("0 record(s) appended", done.stdout)

    def test_says_how_many_records_it_appended(self):
        """The first run reports the 9 records it wrote, the number the ledger grew by (assumed U4 Q5: run-cost.py's "N record(s) appended")."""
        self.given_pinned_session()
        self.given_unpinned_session()

        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("9 record(s) appended", done.stdout)
        self.assertEqual(len(self.ledger_bytes().splitlines()), 9)

    def test_skips_the_session_and_the_unit_the_hook_already_recorded__and_appends_the_rest(self):
        """SA1's session and A's U1 are in the ledger from the hook; SA2's worker·opus shares their (session_dir, scope, unit_id, role, model) and is still a different session to count (D12; D3; assumed U4 Q1)."""
        self.given_pinned_session()
        self.given_unpinned_session()
        self.given_ledger(*self.hook_records("session"), *self.hook_records("unit", unit_id="U1", source="unit-close"))

        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertCountEqual([self.identity(r) for r in self.migrated()], [
            ("session", PINNED_DIR, None, SA2, "worker", OPUS),
            ("session", UNPINNED_DIR, None, SB1, "worker", OPUS),
            ("session", UNPINNED_DIR, None, SB2, "worker", OPUS),
            ("unit", PINNED_DIR, "U2", SA2, "worker", OPUS),
            ("unit", UNPINNED_DIR, "U1", SB1, "worker", OPUS),
        ])

    def test_records_the_physical_session_dir__when_the_sessions_root_is_reached_through_a_symlink(self):
        """A session dir is one ledger key however it was reached; a link path here and a physical one from the hook count U1 twice (U3 addendum R6.6)."""
        self.given_pinned_session()
        link = self.root / "sessions-link"
        link.symlink_to(self.sessions)

        self.migrate(runs_root=link)

        self.assertEqual({r["session_dir"] for r in self.ledger_records()}, {str(self.sessions / PINNED_DIR)})

    def test_a_unit_the_hook_recorded_is_not_recorded_again__through_a_symlinked_sessions_root(self):
        """The hook keyed A's U1 by the physical dir; a migrate through a link must still find it, or U1 is counted twice in --by unit-id (U3 addendum: "one session dir is one ledger key however it was reached")."""
        self.given_pinned_session()
        self.given_ledger(*self.hook_records("unit", unit_id="U1", source="unit-close"))
        link = self.root / "sessions-link"
        link.symlink_to(self.sessions)

        self.migrate(runs_root=link)

        self.assertEqual([self.identity(r) for r in self.migrated() if r["scope"] == "unit"],
                         [("unit", PINNED_DIR, "U2", SA2, "worker", OPUS)])

    def test_the_session_end_call_appends_nothing_for_a_session_migrate_already_recorded(self):
        """Migrate first, hook second: the late session-end call must see migrate's records as its own, or SA2 is counted twice (D12 idempotency, both directions; U1 row: "a second call for the same session_id appends nothing")."""
        session_dir = self.given_pinned_session()
        self.given_unpinned_session()
        self.migrate()
        before = self.ledger_bytes()
        sa2 = self.projects / re.sub(r"[^A-Za-z0-9]", "-", f"/Users/owner/worktrees/{PINNED_DIR}") / f"{SA2}.jsonl"

        done = subprocess.run([sys.executable, str(RUN_COST), "--run-dir", str(session_dir), "--ledger",
                               "--session-id", SA2, "--transcript", str(sa2),
                               "--accounting-root", str(self.accounting_root)],
                              env=self.env, capture_output=True, text=True)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.ledger_bytes(), before)

    def test_leaves_every_existing_ledger_line_as_it_was(self):
        """The ledger is append-only; a migrate that rewrites it (sorting, dropping a ragged line) destroys records nobody can rebuild (invariant: "--migrate reads before it writes and never touches an existing line")."""
        self.given_pinned_session()
        self.given_unpinned_session()
        self.given_ledger(LEDGER[0], "not a record", LEDGER[3])
        before = self.ledger_bytes()

        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        after = self.ledger_bytes()
        self.assertTrue(after.startswith(before), "an existing ledger byte changed")
        self.assertGreater(len(after), len(before))


# ------------------------------------------------------------ R7 · the sessions root

class MigrateRootTests(MigrateCase):
    def test_reads_the_sessions_root_from_ROBOWRIGHT_SESSIONS_ROOT__without_the_flag(self):
        """The sessions root resolves as run-roster.py's does, so the Owner's usual environment migrates without a flag (assumed U4 Q9)."""
        self.given_pinned_session()
        self.given_unpinned_session()

        done = self.rollup("--migrate", env=dict(self.env, ROBOWRIGHT_SESSIONS_ROOT=str(self.sessions)))

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.ledger_records()), 9)

    def test_refuses_by_name_and_writes_nothing__when_nothing_names_a_sessions_root(self):
        """With no root there is nothing to walk; "0 appended" would read as "already migrated" (assumed U4 Q10)."""
        self.given_pinned_session()

        done = self.rollup("--migrate")

        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--runs-root", done.stderr)
        self.assertIsNone(self.ledger_bytes())

    def test_refuses_naming_the_path_and_writes_nothing__when_the_sessions_root_does_not_exist(self):
        """A mistyped root is a mistake to show, not an empty backfill to report (assumed U4 Q10)."""
        missing = self.root / "nowhere" / "sessions"

        done = self.migrate(runs_root=missing)

        self.assertNotEqual(done.returncode, 0)
        self.assertIn(str(missing), done.stderr)
        self.assertIsNone(self.ledger_bytes())

    def test_appends_nothing_and_says_so__over_an_empty_sessions_root(self):
        """An empty root is a real, finished answer: nothing to backfill, exit 0 (U4 row "says so", by analogy; assumed U4 Q5)."""
        done = self.migrate()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("0 record(s) appended", done.stdout)
        self.assertEqual(self.ledger_records(), [])


# ------------------------------------------------------------ R8–R9 · --since and --project filter every --by
#
#     record  project  unit               role      model   session  req   at
#     F1      sample   sample-013-ledger  worker    opus    S1       2     2026-09-20T11:15+00:00
#     F2      sample   sample-013-ledger  subagent  haiku   S1       1     2026-09-20T11:15+00:00
#     F3      sample   sample-009-intake  worker    opus    S4       40    2026-08-20T10:00+00:00
#     F4      demo     demo-002-intro     worker    sonnet  S3       300   2026-09-21T10:00+00:00
#     F5      sampler  sampler-001-probe  worker    opus    S5       5000  2026-09-22T09:00+00:00

FILTER_LEDGER = (
    record(project="sample", unit="sample-013-ledger", role="worker", model=OPUS, session_id=S1,
           requests=2, at="2026-09-20T11:15:00+00:00"),
    record(project="sample", unit="sample-013-ledger", role="subagent", model=HAIKU, session_id=S1,
           requests=1, at="2026-09-20T11:15:00+00:00"),
    record(project="sample", unit="sample-009-intake", role="worker", model=OPUS, session_id=S4,
           requests=40, at="2026-08-20T10:00:00+00:00"),
    record(project="demo", unit="demo-002-intro", role="worker", model=SONNET, session_id=S3,
           requests=300, at="2026-09-21T10:00:00+00:00"),
    record(project="sampler", unit="sampler-001-probe", role="worker", model=OPUS, session_id=S5,
           requests=5000, at="2026-09-22T09:00:00+00:00"),
)


class FilterTests(RollupCase):
    def requests_by(self, by, *flags, env=None):
        """--by <by> --json <flags>, as {row key: requests}; fails the test on a non-zero exit."""
        done = self.rollup("--by", by, "--json", *flags, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return {row["key"]: row["requests"] for row in json.loads(done.stdout)["rows"]}

    def test_since_keeps_the_records_written_on_or_after_the_date__for_every_by(self):
        """F3 (08-20) drops out of every grouping; a --by that ignores --since answers "since September" with August in it (U4 row: "--since 2026-09-01 … filter every --by"; assumed U4 Q11: the field is at)."""
        self.given_ledger(*FILTER_LEDGER)
        expected = {
            "project": {"sample": 3, "demo": 300, "sampler": 5000},
            "unit": {"sample-013-ledger": 3, "demo-002-intro": 300, "sampler-001-probe": 5000},
            "role": {"worker": 5302, "subagent": 1},
            "model": {OPUS: 5002, HAIKU: 1, SONNET: 300},
        }
        for by, requests in expected.items():
            with self.subTest(by=by):
                self.assertEqual(self.requests_by(by, "--since", "2026-09-01"), requests)

    def test_since_includes_the_first_second_of_the_day_in_the_record_s_own_offset__and_not_the_second_before(self):
        """A since-date includes that day, dated as the writer's clock read when the record was written; a UTC or local-TZ reading moves 23:59:59 on the 31st at −05:00 into September (assumed U4 Q12)."""
        self.given_ledger(record(project="sample", session_id=S1, requests=2, at="2026-09-01T00:00:00-05:00"),
                          record(project="sample", session_id=S2, requests=5, at="2026-08-31T23:59:59-05:00"))

        requests = self.requests_by("project", "--since", "2026-09-01", env=dict(self.env, TZ="UTC"))

        self.assertEqual(requests, {"sample": 2})

    def test_refuses_a_since_that_is_not_a_date__naming_the_flag_and_the_value(self):
        """A --since the rollup cannot read must not fall back to "everything", which reads as a filtered answer (assumed U4 Q13; U1's "refused by name")."""
        self.given_ledger(*FILTER_LEDGER)
        for value in ("2026-09-31", "last-week"):
            with self.subTest(since=value):
                done = self.rollup("--by", "project", "--json", "--since", value)

                self.assertNotEqual(done.returncode, 0)
                self.assertIn("--since", done.stderr)
                self.assertIn(value, done.stderr)
                self.assertEqual(done.stdout, "")

    def test_refuses_a_since_in_another_iso_date_form__naming_the_flag_and_the_value(self):
        """The flag reads YYYY-MM-DD; a basic or week date accepted too makes --since's spelling depend on the Python version (end-of-stack N2)."""
        self.given_ledger(*FILTER_LEDGER)
        for value in ("20260901", "2026-W36-1"):
            with self.subTest(since=value):
                done = self.rollup("--by", "project", "--json", "--since", value)

                self.assertNotEqual(done.returncode, 0)
                self.assertIn(value, done.stderr)
                self.assertEqual(done.stdout, "")

    def test_project_keeps_only_that_project_s_records__for_every_by(self):
        """--project sample keeps F1–F3 in every grouping; a --by that ignores it shows demo's and sampler's work as sample's (U4 row: "--project sample … filter every --by")."""
        self.given_ledger(*FILTER_LEDGER)
        expected = {
            "project": {"sample": 43},
            "unit": {"sample-013-ledger": 3, "sample-009-intake": 40},
            "role": {"worker": 42, "subagent": 1},
            "model": {OPUS: 42, HAIKU: 1},
        }
        for by, requests in expected.items():
            with self.subTest(by=by):
                self.assertEqual(self.requests_by(by, "--project", "sample"), requests)

    def test_project_matches_the_whole_name__not_a_prefix(self):
        """sampler is another project; a prefix match adds its 5000 requests to sample (U4 row: "--project sample"; §6 project is a value)."""
        self.given_ledger(FILTER_LEDGER[0], FILTER_LEDGER[4])

        self.assertEqual(self.requests_by("project", "--project", "sample"), {"sample": 2})

    def test_since_and_project_together_keep_only_the_records_both_admit__for_every_by(self):
        """Both flags narrow the same set, F1 and F2; either one ignored when the other is given widens the answer silently (U4 row: both filter every --by)."""
        self.given_ledger(*FILTER_LEDGER)
        expected = {
            "project": {"sample": 3},
            "unit": {"sample-013-ledger": 3},
            "role": {"worker": 2, "subagent": 1},
            "model": {OPUS: 2, HAIKU: 1},
        }
        for by, requests in expected.items():
            with self.subTest(by=by):
                self.assertEqual(self.requests_by(by, "--since", "2026-09-01", "--project", "sample"), requests)


# ============================================================ U6 · --by unit-id sums the unit records
#
# Written from the accounting polish's U6 behaviors file (evidence/U6-behaviors.md) before
# --by unit-id existed. A unit-scope record measures one (Claude session, role, model) inside one
# unit window — unit-start to unit-close in one session dir — and carries the whole window's
# active_seconds. A unit-id row groups (unit, unit_id); its key is "<unit> <unit_id>".
#
# The mixed ledger, session and unit records of the same work (MIXED_LEDGER):
#
#     record      scope    unit               unit_id  role      model    session  req  in   out  c.read  c.write  usd   active  at (Z)       5h  7d
#     M1          session  sample-013-ledger  -        worker    opus     S1       2    300  60   3000    300      0.5   3600    09-20 11:15  61  70
#     M2          session  sample-013-ledger  -        subagent  haiku    S1       1    30   7    400     60       0.25  3600    09-20 11:15  61  70
#     M3          session  demo-002-intro     -        worker    sonnet   S3       4    90   30   900     120      0.75  900     09-21 10:00  20  75
#     M4          unit     sample-013-ledger  U1       worker    opus     S1       1    100  20   1000    300      0.2   2400    09-20 11:15  61  70
#     M5          unit     sample-013-ledger  U1       subagent  haiku    S1       1    30   7    400     60       0.25  2400    09-20 11:15  61  70
#     M6          unit     demo-002-intro     U1       worker    sonnet   S3       3    60   20   600     80       0.5   600     09-21 10:00  20  75
#
# --by unit-id reads M4–M6 only: sample-013-ledger U1 = 2 requests, demo-002-intro U1 = 3. Every
# other --by reads M1–M3 only, and prints what the rollup before U6 printed (the goldens below).
#
# The rotation (ROTATION): one window, sample-013-ledger U3, in one session dir, with S1 rotated out
# for S2 mid-unit; every record carries the window's 5400 s:
#
#     R1  S1 worker opus    req 4  in 400  out 40  c.read 4000  c.write 100  usd 0.4
#     R2  S1 subagent haiku req 1  in 50   out 5   c.read 500   c.write 20   usd 0.05
#     R3  S2 worker opus    req 6  in 600  out 60  c.read 6000  c.write 300  usd 0.6
#
#     sums: req 11, in 1050, out 105, c.read 10500, c.write 420, usd 1.05; active 5400 s once = 1.5 h
#     (once per session would be 3.0 h, once per record 4.5 h)

SAMPLE_DIR = "/Users/owner/sessions/sample-013-ledger"
SAMPLE_RERUN_DIR = "/Users/owner/sessions/sample-013-ledger-2"
DEMO_DIR = "/Users/owner/sessions/demo-002-intro"


def unit_record(**fields):
    """One unit-scope §6 record: record()'s defaults with scope unit and unit_id U1; a test names every value its rule depends on."""
    return record(**{"scope": "unit", "unit_id": "U1", "session_dir": SAMPLE_DIR, **fields})


MIXED_LEDGER = (
    record(project="sample", unit="sample-013-ledger", role="worker", model=OPUS, session_id=S1,
           session_dir=SAMPLE_DIR, requests=2, input_tokens=300, output_tokens=60, cache_read_tokens=3000,
           cache_write_tokens=300, estimated_usd=0.5, active_seconds=3600, at="2026-09-20T11:15:00+00:00",
           plan_5h_pct=61, plan_7d_pct=70),
    record(project="sample", unit="sample-013-ledger", role="subagent", model=HAIKU, session_id=S1,
           session_dir=SAMPLE_DIR, requests=1, input_tokens=30, output_tokens=7, cache_read_tokens=400,
           cache_write_tokens=60, estimated_usd=0.25, active_seconds=3600, at="2026-09-20T11:15:00+00:00",
           plan_5h_pct=61, plan_7d_pct=70),
    record(project="demo", unit="demo-002-intro", role="worker", model=SONNET, session_id=S3,
           session_dir=DEMO_DIR, requests=4, input_tokens=90, output_tokens=30, cache_read_tokens=900,
           cache_write_tokens=120, estimated_usd=0.75, active_seconds=900, at="2026-09-21T10:00:00+00:00",
           plan_5h_pct=20, plan_7d_pct=75),
    unit_record(project="sample", unit="sample-013-ledger", unit_id="U1", role="worker", model=OPUS, session_id=S1,
                session_dir=SAMPLE_DIR, requests=1, input_tokens=100, output_tokens=20, cache_read_tokens=1000,
                cache_write_tokens=300, estimated_usd=0.2, active_seconds=2400, at="2026-09-20T11:15:00+00:00",
                plan_5h_pct=61, plan_7d_pct=70),
    unit_record(project="sample", unit="sample-013-ledger", unit_id="U1", role="subagent", model=HAIKU, session_id=S1,
                session_dir=SAMPLE_DIR, requests=1, input_tokens=30, output_tokens=7, cache_read_tokens=400,
                cache_write_tokens=60, estimated_usd=0.25, active_seconds=2400, at="2026-09-20T11:15:00+00:00",
                plan_5h_pct=61, plan_7d_pct=70),
    unit_record(project="demo", unit="demo-002-intro", unit_id="U1", role="worker", model=SONNET, session_id=S3,
                session_dir=DEMO_DIR, requests=3, input_tokens=60, output_tokens=20, cache_read_tokens=600,
                cache_write_tokens=80, estimated_usd=0.5, active_seconds=600, at="2026-09-21T10:00:00+00:00",
                plan_5h_pct=20, plan_7d_pct=75),
)

ROTATION = (
    unit_record(unit="sample-013-ledger", unit_id="U3", session_dir=SAMPLE_DIR, session_id=S1, role="worker", model=OPUS,
                requests=4, input_tokens=400, output_tokens=40, cache_read_tokens=4000, cache_write_tokens=100,
                estimated_usd=0.4, active_seconds=5400),
    unit_record(unit="sample-013-ledger", unit_id="U3", session_dir=SAMPLE_DIR, session_id=S1, role="subagent", model=HAIKU,
                requests=1, input_tokens=50, output_tokens=5, cache_read_tokens=500, cache_write_tokens=20,
                estimated_usd=0.05, active_seconds=5400),
    unit_record(unit="sample-013-ledger", unit_id="U3", session_dir=SAMPLE_DIR, session_id=S2, role="worker", model=OPUS,
                requests=6, input_tokens=600, output_tokens=60, cache_read_tokens=6000, cache_write_tokens=300,
                estimated_usd=0.6, active_seconds=5400),
)

# The session-scope reports over MIXED_LEDGER, captured by running the U6 base's robowright-cost.py
# (with its pricing.py and run-cost.py, unpacked by `git archive`) under RollupCase's environment,
# before --by unit-id existed. The contract freezes them: "byte-identical output to" the U6 base.
GOLDEN_TEXT_BEFORE_U6 = {
    "project": """\
project                   requests        input       output     cache read   cache write   est usd  active h  plan 5h/7d %   (session scope)
demo                             4           90           30            900           120      0.75       0.2         20/75
sample                           3          330           67          3,400           360      0.75       1.0         61/70

prices as of 2026-09-10; each record's estimate was priced when it was written (its price_as_of)
""",
    "unit": """\
unit                      requests        input       output     cache read   cache write   est usd  active h  plan 5h/7d %   (session scope)
demo-002-intro                   4           90           30            900           120      0.75       0.2         20/75
sample-013-ledger                3          330           67          3,400           360      0.75       1.0         61/70

prices as of 2026-09-10; each record's estimate was priced when it was written (its price_as_of)
""",
    "role": """\
role                      requests        input       output     cache read   cache write   est usd  active h  plan 5h/7d %   (session scope)
worker                           6          390           90          3,900           420      1.25       1.2         20/75
subagent                         1           30            7            400            60      0.25       1.0         61/70

prices as of 2026-09-10; each record's estimate was priced when it was written (its price_as_of)
""",
    "model": """\
model                     requests        input       output     cache read   cache write   est usd  active h  plan 5h/7d %   (session scope)
claude-sonnet-5                  4           90           30            900           120      0.75       0.2         20/75
claude-opus-5-5                  2          300           60          3,000           300      0.50       1.0         61/70
claude-haiku-4-5                 1           30            7            400            60      0.25       1.0         61/70

prices as of 2026-09-10; each record's estimate was priced when it was written (its price_as_of)
""",
}
GOLDEN_UNIT_JSON_BEFORE_U6 = """\
{
  "by": "unit",
  "scope": "session",
  "rows": [
    {
      "key": "demo-002-intro",
      "requests": 4,
      "input_tokens": 90,
      "output_tokens": 30,
      "cache_read_tokens": 900,
      "cache_write_tokens": 120,
      "estimated_usd": 0.75,
      "active_hours": 0.25,
      "plan_5h_pct": 20,
      "plan_7d_pct": 75
    },
    {
      "key": "sample-013-ledger",
      "requests": 3,
      "input_tokens": 330,
      "output_tokens": 67,
      "cache_read_tokens": 3400,
      "cache_write_tokens": 360,
      "estimated_usd": 0.75,
      "active_hours": 1.0,
      "plan_5h_pct": 61,
      "plan_7d_pct": 70
    }
  ]
}
"""


class UnitIdCase(RollupCase):
    def unit_id_report(self, *flags):
        """--by unit-id --json <flags>, parsed; fails the test on a non-zero exit."""
        done = self.rollup("--by", "unit-id", "--json", *flags)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def requests_by_unit_id(self, *flags):
        return {row["key"]: row["requests"] for row in self.unit_id_report(*flags)["rows"]}

    @staticmethod
    def plain(stdout):
        """--help without the colour codes Python 3.14's argparse adds when the environment asks for colour."""
        return re.sub(r"\x1b\[[0-9;]*m", "", stdout)

    @classmethod
    def option_help(cls, stdout, flag):
        """One option's entry in --help's options list — its flag line and the indented lines under it — on one line."""
        lines = cls.plain(stdout).splitlines()
        starts = [n for n, line in enumerate(lines) if re.match(r"  " + re.escape(flag) + r"\b", line)]
        if not starts:
            return ""
        entry = [lines[starts[-1]]]
        for line in lines[starts[-1] + 1:]:
            if not line.strip() or re.match(r"  -", line):
                break
            entry.append(line)
        return " ".join(" ".join(entry).split())

    @staticmethod
    def lines_before_the_prices_line(stdout):
        """The table: every line above the blank line that precedes `prices as of …`."""
        return stdout.split("\n\n")[0].splitlines()


# ------------------------------------------------------------ R1 · one row per (unit, unit_id), unit scope only

class UnitIdGroupingTests(UnitIdCase):
    def test_gives_each_unit_id_of_each_unit_its_own_row__keyed_unit_then_unit_id(self):
        """U1 and U2 of one unit are two windows of work, and U1 of another unit is a third; a key of unit_id alone merges demo's U1 into sample's (U6: "grouped by (unit, unit_id) … key cell `<unit> <unit_id>`"; the JSON key, assumed Q1)."""
        self.given_ledger(unit_record(unit="sample-013-ledger", unit_id="U1", requests=2),
                          unit_record(unit="sample-013-ledger", unit_id="U2", session_id=S2, requests=5),
                          unit_record(project="demo", unit="demo-002-intro", unit_id="U1", session_id=S3,
                                      session_dir=DEMO_DIR, requests=3))

        self.assertEqual(self.requests_by_unit_id(), {
            "sample-013-ledger U1": 2,
            "sample-013-ledger U2": 5,
            "demo-002-intro U1": 3,
        })

    def test_sums_requests_tokens_and_estimates_of_both_sessions__when_a_rotation_splits_a_window(self):
        """A rotation mid-unit leaves two sessions' records in one window; the row is all of the unit's work, 4 + 1 + 6 requests and each class's total (U6: "two sessions inside one window … add their tokens and requests")."""
        self.given_ledger(*self.in_dollar_sessions(*ROTATION))

        rows = self.unit_id_report()["rows"]

        self.assertEqual([(r["key"], self.token_facts(r)) for r in rows],
                         [("sample-013-ledger U3", (11, 1050, 105, 10500, 420))])
        self.assertAlmostEqual(rows[0]["estimated_usd"], 1.05, places=6)

    def test_reads_no_session_scope_record__in_a_ledger_holding_both_scopes(self):
        """A session record re-counts the unit's work and has no unit_id; read in, M1–M3 add rows keyed "… None" or double the units (U6: "sums unit-scope records only"; D3: "two scopes summed together count everything twice")."""
        self.given_ledger(*MIXED_LEDGER)

        self.assertEqual(self.requests_by_unit_id(), {"sample-013-ledger U1": 2, "demo-002-intro U1": 3})


# ------------------------------------------------------------ R3 · a window's active time counts once

class UnitIdActiveTimeTests(UnitIdCase):
    def test_counts_a_window_s_active_time_once__though_two_sessions_ran_inside_it(self):
        """Every record of the window carries its 5400 s; once per session reports 3.0 h, once per record 4.5 h, for 1.5 h of work (U6: "counted once per (session_dir, unit_id), never once per session"; PLAN-REVIEW §3 Q3's trap)."""
        self.given_ledger(*ROTATION)

        row = self.unit_id_report()["rows"][0]

        self.assertAlmostEqual(row["active_hours"], 1.5, places=6)

    def test_adds_each_session_dir_s_window__when_a_unit_id_ran_again_in_another_session_dir(self):
        """A unit of work re-run in a new session dir has two U1 windows, 1800 s and 2700 s; one row, both counted, 1.25 h — once per row drops one run (U6: "counted once per (session_dir, unit_id)")."""
        self.given_ledger(unit_record(unit="sample-013-ledger", unit_id="U1", session_dir=SAMPLE_DIR, session_id=S1,
                                      role="worker", requests=2, active_seconds=1800),
                          unit_record(unit="sample-013-ledger", unit_id="U1", session_dir=SAMPLE_DIR, session_id=S1,
                                      role="subagent", model=HAIKU, requests=1, active_seconds=1800),
                          unit_record(unit="sample-013-ledger", unit_id="U1", session_dir=SAMPLE_RERUN_DIR, session_id=S4,
                                      role="worker", requests=5, active_seconds=2700))

        rows = self.unit_id_report()["rows"]

        self.assertEqual([(r["key"], r["requests"]) for r in rows], [("sample-013-ledger U1", 8)])
        self.assertAlmostEqual(rows[0]["active_hours"], 1.25, places=6)


# ------------------------------------------------------------ R4 · plan % from the newest reading

class UnitIdPlanTests(UnitIdCase):
    def test_a_unit_row_shows_the_newest_reading__not_an_older_one_or_a_later_record_without_one(self):
        """Plan usage is a gauge: 10:30's 30/40 is the newest reading; 10:00's 20/35 is older and 10:50's record has none (U6: "the newest record in the row with a non-null `plan_captured_at`")."""
        self.given_ledger(unit_record(at="2026-09-20T10:00:00+00:00", session_id=S1, plan_5h_pct=20, plan_7d_pct=35),
                          unit_record(at="2026-09-20T10:30:00+00:00", session_id=S1, role="subagent", model=HAIKU,
                                      plan_5h_pct=30, plan_7d_pct=40),
                          unit_record(at="2026-09-20T10:50:00+00:00", session_id=S2,
                                      plan_5h_pct=None, plan_7d_pct=None, plan_captured_at=None))

        row = self.unit_id_report()["rows"][0]

        self.assertEqual((row["plan_5h_pct"], row["plan_7d_pct"]), (30, 40))


# ------------------------------------------------------------ R5 · --since and --project filter unit rows

class UnitIdFilterTests(UnitIdCase):
    def test_since_keeps_the_unit_records_written_on_or_after_the_date(self):
        """An August window drops out of "since September"; ignored, sample-009-intake's 40 requests appear (U6: "`--since` … appl[ies] as [it does] today")."""
        self.given_ledger(unit_record(unit="sample-013-ledger", unit_id="U1", requests=2, at="2026-09-20T11:15:00+00:00"),
                          unit_record(unit="sample-009-intake", unit_id="U1", session_id=S4,
                                      session_dir="/Users/owner/sessions/sample-009-intake",
                                      requests=40, at="2026-08-20T10:00:00+00:00"))

        self.assertEqual(self.requests_by_unit_id("--since", "2026-09-01"), {"sample-013-ledger U1": 2})

    def test_project_keeps_only_that_project_s_unit_records(self):
        """--project sample keeps sample's window; demo's and sampler's are other projects' work (U6: "`--project` … appl[ies] as [it does] today")."""
        self.given_ledger(unit_record(project="sample", unit="sample-013-ledger", unit_id="U1", requests=2),
                          unit_record(project="demo", unit="demo-002-intro", unit_id="U1", session_id=S3,
                                      session_dir=DEMO_DIR, requests=300),
                          unit_record(project="sampler", unit="sampler-001-probe", unit_id="U1", session_id=S5,
                                      session_dir="/Users/owner/sessions/sampler-001-probe", requests=5000))

        self.assertEqual(self.requests_by_unit_id("--project", "sample"), {"sample-013-ledger U1": 2})


# ------------------------------------------------------------ R6 · the report says which scope it summed

class UnitIdScopeTests(UnitIdCase):
    def test_json_names_the_unit_scope_for_unit_id__and_the_session_scope_for_every_other_by(self):
        """A reader of --json learns from `scope` which records a row counts; "session" on a unit-id report tells it the wrong thing (U6: "the JSON `scope` key reads "unit" for unit-id and "session" otherwise")."""
        self.given_ledger(*MIXED_LEDGER)
        expected = {"unit-id": "unit", "project": "session", "unit": "session", "role": "session", "model": "session"}
        for by, scope in expected.items():
            with self.subTest(by=by):
                done = self.rollup("--by", by, "--json")

                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(json.loads(done.stdout)["scope"], scope)

    def test_the_text_header_says_unit_scope__for_unit_id(self):
        """The text report marks its scope at the end of the header; "(session scope)" over unit rows misstates what was summed (U6 scope rule; the marker's words, assumed Q3)."""
        self.given_ledger(*MIXED_LEDGER)

        done = self.rollup("--by", "unit-id")

        self.assertEqual(done.returncode, 0, done.stderr)
        header = done.stdout.splitlines()[0]
        self.assertIn("unit scope", header)
        self.assertNotIn("session scope", header)

    def test_the_text_row_s_key_cell_is_the_unit_a_space_and_the_unit_id(self):
        """The Owner reads the text table; the row names the work as `<unit> <unit_id>` and carries its figures (U6: "key cell `<unit> <unit_id>`, the same four columns plus requests")."""
        self.given_ledger(unit_record(unit="sample-013-ledger", unit_id="U7", requests=9, active_seconds=5400))

        done = self.rollup("--by", "unit-id")

        self.assertEqual(done.returncode, 0, done.stderr)
        rows = self.lines_before_the_prices_line(done.stdout)[1:]
        self.assertEqual(len(rows), 1, done.stdout)
        self.assertTrue(rows[0].startswith("sample-013-ledger U7 "), rows[0])
        self.assertRegex(rows[0], r"(?<![\d.])9(?![\d.])")
        self.assertRegex(rows[0], r"(?<![\d.])1\.5(?![\d.])")

    def test_help_says_which_scope_each_by_sums(self):
        """--help is where the Owner learns the two scopes; a --by line naming only session scope, or a claim that every --by sums it, hides that unit-id reads the other (U6: "`--help` says, per value, which scope it sums"; the substrings, assumed Q4)."""
        done = self.rollup("--help", root_flag=False)

        self.assertEqual(done.returncode, 0, done.stderr)
        by_option = self.option_help(done.stdout, "--by")
        self.assertIn("unit-id", by_option)
        self.assertRegex(by_option, r"\bunit\W{0,2}[- ]?scope")
        self.assertRegex(by_option, r"\bsession\W{0,2}[- ]?scope")
        self.assertNotRegex(" ".join(self.plain(done.stdout).split()), r"[Ee]very --by sums\W+session")


# ------------------------------------------------------------ R7 · no unit records, and a migrated ledger

class UnitIdEmptyTests(UnitIdCase):
    def test_prints_the_header_and_no_rows_and_exits_0__when_the_ledger_has_no_unit_records(self):
        """A ledger of session records only has nothing for unit-id to sum; that is an empty report, not an error or the session rows (U6: "A ledger with no unit records prints the header and no rows, exit 0")."""
        self.given_ledger(*MIXED_LEDGER[:3])

        done = self.rollup("--by", "unit-id")

        self.assertEqual(done.returncode, 0, done.stderr)
        table = self.lines_before_the_prices_line(done.stdout)
        self.assertEqual(len(table), 1, done.stdout)
        self.assertIn("requests", table[0])


class UnitIdMigrateTests(MigrateCase):
    def test_sums_the_unit_records_migrate_wrote__one_row_per_window(self):
        """--migrate writes unit records, so the past is readable per unit: A-U1 is a2 + the gate sidecar (2000 + 3000 in) over 2100 s, A-U2 is a4 + a5 (5000 + 6000) over 2700 s, B-U1 is c1 + c2 (1500 + 2500) over 3000 s (U6: "`--by unit-id` on a `--migrate`d ledger works"; D12; the U4 fixture above; hours to two places, assumed Q5)."""
        self.given_pinned_session()
        self.given_unpinned_session()
        self.assertEqual(self.migrate().returncode, 0)

        done = self.rollup("--by", "unit-id", "--json")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual({row["key"]: (row["requests"], row["input_tokens"], row["active_hours"])
                          for row in json.loads(done.stdout)["rows"]}, {
            "sample-013-ledger U1": (2, 5000, 0.58),
            "sample-013-ledger U2": (2, 11000, 0.75),
            "sample-014-export U1": (2, 4000, 0.83),
        })


# ------------------------------------------------------------ R2 · every other --by prints what it printed before

class SessionScopeUnchangedTests(RollupCase):
    def test_every_session_scope_by_prints_the_pre_u6_text_report__over_a_ledger_holding_both_scopes(self):
        """unit-id is a new value, not a new rule for the others; a changed key, scope or filter in project/unit/role/model shows as a diff against the frozen report (U6: "Every other `--by` value keeps summing session scope, byte-identical output to" the U6 base)."""
        self.given_ledger(*self.in_dollar_sessions(*MIXED_LEDGER))
        for by, golden in GOLDEN_TEXT_BEFORE_U6.items():
            with self.subTest(by=by):
                done = self.rollup("--by", by)

                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout, golden)

    def test_by_unit_prints_the_pre_u6_json_report__over_a_ledger_holding_both_scopes(self):
        """--by unit keeps its name and its meaning — session records grouped by their unit field — so a dashboard reading its JSON sees no change (U6: "`--by unit` included: it groups session-scope records by their `unit` field and is not renamed")."""
        self.given_ledger(*self.in_dollar_sessions(*MIXED_LEDGER))

        done = self.rollup("--by", "unit", "--json")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, GOLDEN_UNIT_JSON_BEFORE_U6)


# ============================================================ fixes F1 · a dollar figure only where the budget is in dollars
#
# Written from the accounting fixes' F1 behaviors file (evidence/fixes-F1-behaviors.md) before the
# rule existed. The Owner's rule: a dollar figure never covers spending that was not billed in
# dollars. A --by row's estimated_usd is a number only when its records name at least one non-empty
# session_dir and every distinct one they name has a run.json setting spend_threshold_usd or
# spend_cap_usd to a number (float() takes it, and it is not null). A Planner, Lead or Explainer
# record has no session_dir and rides with the sessions beside it. Each session dir is a scratch dir
# under the test's tmp root (RollupCase.given_brief / given_dollar_session / given_run_json).

ABSENT = object()


def doc_record(session_dir=ABSENT, **fields):
    """A doc-role session record (a Planner by default): record()'s defaults with this session_dir; ABSENT leaves the key out."""
    r = record(**{"role": "planner", **fields})
    if session_dir is ABSENT:
        del r["session_dir"]
    else:
        r["session_dir"] = session_dir
    return r


def row_lines(stdout, key):
    return [line for line in stdout.splitlines() if line.startswith(key + " ")]


# ------------------------------------------------------------ R1 · a figure only when every session dir the row names budgets in dollars

class DollarBilledRowTests(RollupCase):
    def test_a_row_keeps_its_estimate__when_every_session_dir_it_names_budgets_in_dollars(self):
        """Two sessions, each under a dollar brief, are all dollar-billed; nulling them hides spending the Owner budgets in dollars — 0.5 + 1.25 (fixes F1 rule 1: "a number only when … every distinct session_dir they name has a run.json that budgets in dollars")."""
        self.given_ledger(record(project="sample", session_id=S1, estimated_usd=0.5,
                                 session_dir=self.given_dollar_session("sample-013-ledger")),
                          record(project="sample", session_id=S2, estimated_usd=1.25,
                                 session_dir=self.given_dollar_session("sample-014-export")))

        rows = self.rows("project")

        self.assertAlmostEqual(rows["sample"]["estimated_usd"], 1.75, places=6)

    def test_a_row_s_estimate_is_null_in_json__when_one_session_dir_it_names_does_not_budget_in_dollars(self):
        """One session under a brief with no dollar limit makes the row's dollar figure cover spending not billed in dollars; demo, all dollar, keeps its 0.75 (fixes F1 rule 1: "every distinct session_dir … Otherwise the row's `estimated_usd` is null, in the table and in `--json` alike")."""
        self.given_ledger(record(project="sample", session_id=S1, estimated_usd=0.5,
                                 session_dir=self.given_dollar_session("sample-013-ledger")),
                          record(project="sample", session_id=S2, estimated_usd=1.25,
                                 session_dir=self.given_brief("sample-014-export")),
                          record(project="demo", session_id=S3, estimated_usd=0.75,
                                 session_dir=self.given_dollar_session("demo-002-intro")))

        rows = self.rows("project")

        self.assertIsNone(rows["sample"]["estimated_usd"])
        self.assertAlmostEqual(rows["demo"]["estimated_usd"], 0.75, places=6)


# ------------------------------------------------------------ R2 · a doc-role record rides with the sessions beside it

class DocRoleRecordTests(RollupCase):
    def test_a_doc_role_record_without_a_session_dir_adds_its_estimate_to_a_dollar_session_s_row(self):
        """The Planner's record has no session dir; treating that as not dollar-billed nulls every project with a Planner — 0.5 + 0.25 (fixes F1 rule 1: "neither qualifies nor disqualifies a row: it rides with the sessions beside it"; a null session_dir counts as absent, assumed Q1)."""
        cases = {"empty": "", "absent": ABSENT, "null": None}
        for case, session_dir in cases.items():
            with self.subTest(session_dir=case):
                self.given_ledger(record(project="sample", session_id=S1, estimated_usd=0.5,
                                         session_dir=self.given_dollar_session("sample-013-ledger")),
                                  doc_record(session_dir, project="sample", session_id=S2, estimated_usd=0.25))

                rows = self.rows("project")

                self.assertAlmostEqual(rows["sample"]["estimated_usd"], 0.75, places=6)

    def test_a_row_of_only_doc_role_records_has_a_null_estimate(self):
        """A Planner and a Lead with no session beside them name no brief, so nothing says the row was billed in dollars (fixes F1 rule 1: "a number only when the row's records name at least one non-empty `session_dir`")."""
        self.given_ledger(doc_record("", project="sample", role="planner", session_id=S1, estimated_usd=0.25),
                          doc_record(ABSENT, project="sample", role="lead", session_id=S2, estimated_usd=0.5))

        rows = self.rows("project")

        self.assertIsNone(rows["sample"]["estimated_usd"])


# ------------------------------------------------------------ R3 · a run.json that says nothing about dollars

class RunJsonTests(RollupCase):
    def test_a_row_s_estimate_is_null__when_its_session_dir_has_no_run_json(self):
        """No brief, no dollar budget; taking a missing run.json as dollar-billed puts a figure on spending nothing says was in dollars (fixes F1 rule 1: "A named session_dir whose run.json is missing … makes the row not dollar-billed")."""
        self.given_ledger(record(project="sample", estimated_usd=0.5, session_dir=self.given_run_json("sample-013-ledger", None)))

        rows = self.rows("project")

        self.assertIsNone(rows["sample"]["estimated_usd"])

    def test_a_row_s_estimate_is_null__when_its_run_json_cannot_be_read(self):
        """A truncated run.json that still carries a dollar threshold, or a directory where run.json should be, is no brief to read (fixes F1 rule 1: "whose run.json is … unreadable"; both count as unreadable, assumed Q3)."""
        def not_json(name):
            return self.given_run_json(name, '{"ticket": "sample-013-ledger", "spend_threshold_usd": 40')

        def a_directory(name):
            session_dir = self.given_run_json(name, None)
            (Path(session_dir) / "run.json").mkdir()
            return session_dir

        for case, given in {"not JSON": not_json, "a directory": a_directory}.items():
            with self.subTest(run_json=case):
                self.given_ledger(record(project="sample", estimated_usd=0.5, session_dir=given(f"sample-013-{case.replace(' ', '-')}")))

                rows = self.rows("project")

                self.assertIsNone(rows["sample"]["estimated_usd"])

    def test_a_row_s_estimate_is_null__when_its_run_json_is_not_an_object(self):
        """A run.json holding a list is not a brief, even when the list holds a dollar threshold (fixes F1 rule 1: "whose run.json is … not an object")."""
        self.given_ledger(record(project="sample", estimated_usd=0.5, session_dir=self.given_run_json(
            "sample-013-ledger", json.dumps([{"spend_threshold_usd": 40, "spend_cap_usd": 60}]) + "\n")))

        rows = self.rows("project")

        self.assertIsNone(rows["sample"]["estimated_usd"])

    def test_a_row_s_estimate_is_null__when_its_brief_sets_neither_dollar_limit(self):
        """A brief with no dollar threshold and no dollar cap runs under a budget not measured in dollars (fixes F1 rule 1: "or sets neither field"; the dashboard's budgets_in_dollars, via number(None) → None for a null field)."""
        cases = {"fields absent": {}, "fields null": {"spend_threshold_usd": None, "spend_cap_usd": None}}
        for case, budget in cases.items():
            with self.subTest(brief=case):
                self.given_ledger(record(project="sample", estimated_usd=0.5,
                                         session_dir=self.given_brief("sample-013-ledger", **budget)))

                rows = self.rows("project")

                self.assertIsNone(rows["sample"]["estimated_usd"])


# ------------------------------------------------------------ R4 · either dollar limit, when float() takes it

class DollarLimitTests(RollupCase):
    def test_a_row_keeps_its_estimate__when_its_brief_sets_only_a_dollar_threshold(self):
        """A $40 threshold alone is a dollar budget; requiring the cap too nulls every threshold-only brief (fixes F1 rule 1: "`spend_threshold_usd` or `spend_cap_usd` a number")."""
        self.given_ledger(record(project="sample", estimated_usd=0.5,
                                 session_dir=self.given_brief("sample-013-ledger", spend_threshold_usd=40)))

        rows = self.rows("project")

        self.assertAlmostEqual(rows["sample"]["estimated_usd"], 0.5, places=6)

    def test_a_row_keeps_its_estimate__when_its_brief_sets_only_a_dollar_cap(self):
        """A $60 cap alone is a dollar budget; reading only the threshold nulls every cap-only brief (fixes F1 rule 1: "`spend_threshold_usd` or `spend_cap_usd` a number")."""
        self.given_ledger(record(project="sample", estimated_usd=0.5,
                                 session_dir=self.given_brief("sample-013-ledger", spend_cap_usd=60)))

        rows = self.rows("project")

        self.assertAlmostEqual(rows["sample"]["estimated_usd"], 0.5, places=6)

    def test_a_row_keeps_its_estimate__when_its_dollar_threshold_is_a_numeric_string(self):
        """"40" is a number by the dashboard's test, so the two reports agree on the same brief; an isinstance check disagrees (fixes F1 rule 1: number() — "`float(value)` succeeds and value is not None")."""
        self.given_ledger(record(project="sample", estimated_usd=0.5,
                                 session_dir=self.given_brief("sample-013-ledger", spend_threshold_usd="40")))

        rows = self.rows("project")

        self.assertAlmostEqual(rows["sample"]["estimated_usd"], 0.5, places=6)

    def test_a_row_s_estimate_is_null__when_both_dollar_limits_are_strings_float_refuses(self):
        """"forty" and "sixty" are set but are not numbers; counting a field's presence calls a word a dollar budget (fixes F1 rule 1: number() — "`float(value)` succeeds")."""
        self.given_ledger(record(project="sample", estimated_usd=0.5, session_dir=self.given_brief(
            "sample-013-ledger", spend_threshold_usd="forty", spend_cap_usd="sixty")))

        rows = self.rows("project")

        self.assertIsNone(rows["sample"]["estimated_usd"])


# ------------------------------------------------------------ R6 · the table's est usd column

class EstimateColumnTests(RollupCase):
    def test_a_row_without_a_figure_prints_a_dash_in_the_est_usd_column__when_another_row_has_one(self):
        """sample's session budgets not in dollars and demo's does: the column stays for demo, and sample's cell says "-", not n/a (which reads as missing prices) nor 0.00 (which reads as free) (fixes F1 rule 2: "a row without one prints `-` in that column, never `n/a` and never `0.00`")."""
        self.given_ledger(record(project="sample", session_id=S1, estimated_usd=0.5,
                                 session_dir=self.given_brief("sample-013-ledger")),
                          record(project="demo", session_id=S3, estimated_usd=0.75,
                                 session_dir=self.given_dollar_session("demo-002-intro")))

        done = self.rollup("--by", "project")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("est usd", done.stdout.splitlines()[0])
        lines = row_lines(done.stdout, "sample")
        self.assertEqual(len(lines), 1, done.stdout)
        self.assertRegex(lines[0], r"(?<!\S)-(?!\S)")
        self.assertNotIn("n/a", lines[0])
        self.assertNotRegex(lines[0], r"(?<![\d.])0\.00(?![\d.])")
        self.assertNotRegex(lines[0], r"(?<![\d.])0\.50?(?![\d.])")

    def test_prints_no_est_usd_column__when_no_row_has_a_figure(self):
        """Neither project budgets in dollars (sample's brief sets no limit, demo has no run.json); a column of dashes is a dollar column with nothing in it (fixes F1 rule 2: "The table prints the `est usd` column only when at least one row has a figure")."""
        self.given_ledger(record(project="sample", session_id=S1, estimated_usd=0.5,
                                 session_dir=self.given_brief("sample-013-ledger")),
                          record(project="demo", session_id=S3, estimated_usd=0.75,
                                 session_dir=self.given_run_json("demo-002-intro", None)))

        done = self.rollup("--by", "project")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("est usd", done.stdout.splitlines()[0])
        for key in ("sample", "demo"):
            with self.subTest(row=key):
                lines = row_lines(done.stdout, key)
                self.assertEqual(len(lines), 1, done.stdout)
                self.assertNotRegex(lines[0], r"(?<!\S)-(?!\S)")
                self.assertNotIn("n/a", lines[0])


# ------------------------------------------------------------ R7 · --by unit-id rows follow the same rule

class UnitIdDollarTests(UnitIdCase):
    def test_a_unit_id_row_s_estimate_is_null__when_its_window_ran_in_a_session_dir_that_does_not_budget_in_dollars(self):
        """Unit rows are --by rows too; applying the rule to session scope only leaves a dollar figure on sample U1, whose brief sets no dollar limit, while demo U1 keeps its 0.5 (fixes F1 rule 1: "A `--by` row's `estimated_usd`" — unit-id is one of the --by values)."""
        self.given_ledger(unit_record(unit="sample-013-ledger", unit_id="U1", session_id=S1, estimated_usd=0.2,
                                      session_dir=self.given_brief("sample-013-ledger")),
                          unit_record(project="demo", unit="demo-002-intro", unit_id="U1", session_id=S3, estimated_usd=0.5,
                                      session_dir=self.given_dollar_session("demo-002-intro")))

        rows = self.unit_id_report()["rows"]

        self.assertEqual({r["key"]: r["estimated_usd"] for r in rows},
                         {"sample-013-ledger U1": None, "demo-002-intro U1": 0.5})


# ------------------------------------------------------------ R8 · rollup() stays the dashboard's seam

class RollupSeamTests(RollupCase):
    def test_rollup_keeps_a_record_s_estimate__whatever_its_session_dir_budgets(self):
        """The dashboard calls rollup(records, by, priced) and applies its own dollar rule to the page; the rule moved inside rollup() applies twice there (fixes F1 rule 1: "**not inside `rollup()`** … `rollup()`'s behavior and signature stay as they are")."""
        spec = importlib.util.spec_from_file_location("robowright_cost_under_test", SCRIPT)
        cost = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cost)
        records = [record(project="sample", estimated_usd=0.5, session_dir=self.given_brief("sample-013-ledger"))]

        rows = cost.rollup(records, "project", True)

        self.assertEqual([(r["key"], r["estimated_usd"]) for r in rows], [("sample", 0.5)])


# ------------------------------------------------------------ R9 · --help states the rule

class DollarHelpTests(UnitIdCase):
    def test_help_states_the_dollar_rule_by_its_brief_fields__in_place_of_meaningful_only_where_the_budget_is_in_dollars(self):
        """--help is where the Owner learns when a figure appears; the old sentence leaves it to the reader to know which budgets are in dollars (fixes F1 rule 3: "becomes rule 1 in one sentence"; the field names as the marker, assumed Q4)."""
        done = self.rollup("--help", root_flag=False)

        self.assertEqual(done.returncode, 0, done.stderr)
        text = " ".join(self.plain(done.stdout).split())
        self.assertNotIn("meaningful only where the budget is in dollars", text)
        self.assertIn("spend_threshold_usd", text)
        self.assertIn("spend_cap_usd", text)


if __name__ == "__main__":
    unittest.main()
