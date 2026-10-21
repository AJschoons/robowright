#!/usr/bin/env python3
"""
robowright-cost.py — where the tokens, estimated dollars, active hours and plan usage went, from
the accounting ledger every session end appends to (<accounting root>/records.jsonl, written by
worker/scripts/run-cost.py --ledger).

    robowright-cost.py --by project|unit|role|model|unit-id [--since YYYY-MM-DD] [--project NAME] [--json] [--accounting-root DIR]
    robowright-cost.py --migrate [--runs-root DIR] [--accounting-root DIR]

--since keeps the records whose `at` (when the record was written) falls on or after the date; a
migrated record's `at` is the day of the migration.

--migrate appends session and unit records, tagged source "migrate", for every finished Worker
session under the sessions root, keyed as the SessionEnd hook keys them, so a group either writer
already appended is not appended again. Doc-role sessions are not migrated.

--by project, unit, role and model sum `session`-scope records only — one per (Claude session,
role, model); a row's active hours count each Claude session once, however many records it has
in the row. --by unit-id sums `unit`-scope records only — one row per unit of work and unit id;
a row's active hours count each unit window (session dir, unit id) once, however many sessions
ran inside it. A unit record re-counts part of a session, so the two scopes are never added
together. A row's plan % is the one its newest record with a reading saw. A row's estimated USD
is a number only when its records name a session dir and every session dir they name has a
run.json setting spend_threshold_usd or spend_cap_usd to a number — a Planner, Lead or Explainer
record names none and rides with the sessions beside it — and is null otherwise.

The accounting root is --accounting-root, else $ROBOWRIGHT_ACCOUNTING_ROOT, else launch.json's
accounting_root, else `accounting` beside the sessions root — the resolution run-cost.py writes by.
"""

import argparse
import glob
import importlib.util
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BY = ("project", "unit", "role", "model", "unit-id")
TOKEN_FIELDS = ("requests", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")


def load_run_cost():
    """run-cost.py's name is not importable; load it by path for the one accounting-root resolution."""
    spec = importlib.util.spec_from_file_location("run_cost", HERE.parent.parent / "worker/scripts/run-cost.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_prices():
    spec = importlib.util.spec_from_file_location("pricing", HERE / "pricing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load()


def read_records(path):
    """Every parseable record in the ledger; a line that is not one (a ragged write) is skipped."""
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def instant(record):
    """A record's `at` as seconds since the epoch; its local offset makes the text sort wrong across a DST change."""
    try:
        return datetime.fromisoformat(record.get("at").replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return float("-inf")


def scope_of(by):
    return "unit" if by == "unit-id" else "session"


def row_key(record, by):
    return f"{record.get('unit')} {record.get('unit_id')}" if scope_of(by) == "unit" else record.get(by)


def rollup(records, by, priced):
    """`priced` false — no pricing file — nulls every row's estimate, whatever its records carry."""
    scope = scope_of(by)
    rows = {}
    for r in records:
        if r.get("scope") != scope:
            continue
        key = row_key(r, by)
        row = rows.setdefault(key, {"key": key, **{k: 0 for k in TOKEN_FIELDS},
                                    "estimated_usd": None, "spans": {}, "latest": None})
        for k in TOKEN_FIELDS:
            row[k] += r.get(k) or 0
        if r.get("estimated_usd") is not None:
            row["estimated_usd"] = (row["estimated_usd"] or 0.0) + r["estimated_usd"]
        # Every record of a session carries the whole session's active time, and every record of a
        # unit window the whole window's, however many sessions ran inside it.
        span = (r.get("session_dir"), r.get("unit_id")) if scope == "unit" else r.get("session_id")
        row["spans"][span] = r.get("active_seconds") or 0
        # A record with no reading (a migrated one, or no status-line tap) says nothing about the plan.
        has_reading = r.get("plan_captured_at") is not None
        if has_reading and (row["latest"] is None or instant(r) > instant(row["latest"])):
            row["latest"] = r
    out = []
    for row in rows.values():
        latest = row.pop("latest") or {}
        row["estimated_usd"] = round(row["estimated_usd"], 2) if priced and row["estimated_usd"] is not None else None
        row["active_hours"] = round(sum(row.pop("spans").values()) / 3600, 2)
        row["plan_5h_pct"] = latest.get("plan_5h_pct")
        row["plan_7d_pct"] = latest.get("plan_7d_pct")
        out.append(row)
    return sorted(out, key=lambda row: -row["requests"])


def number(value):
    """run-roster.py's number(): what float() takes, else None."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def budgets_in_dollars(session_dir):
    """The dashboard's budgets_in_dollars over a session dir's run.json; a missing, unreadable or non-object one is not."""
    try:
        with open(os.path.join(session_dir, "run.json")) as f:
            run = json.load(f)
    except (OSError, TypeError, ValueError):
        return False
    return isinstance(run, dict) and (number(run.get("spend_threshold_usd")) is not None
                                      or number(run.get("spend_cap_usd")) is not None)


def dollar_billed(records, by):
    """The keys of the rows billed in dollars: they name a session dir, and every one they name budgets in dollars."""
    scope = scope_of(by)
    named = {}
    for r in records:
        if r.get("scope") == scope and r.get("session_dir"):
            named.setdefault(row_key(r, by), set()).add(r["session_dir"])
    in_dollars = {d: budgets_in_dollars(d) for d in set().union(*named.values())}
    return {key for key, dirs in named.items() if all(in_dollars[d] for d in dirs)}


def since_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}")


def written_on(record):
    """The calendar day of a record's `at` on the clock that wrote it; None when `at` is missing or unreadable."""
    try:
        return datetime.fromisoformat(record.get("at").replace("Z", "+00:00")).date()
    except (AttributeError, ValueError):
        return None


def sessions_root(flag, run_cost):
    """--runs-root, else $ROBOWRIGHT_SESSIONS_ROOT, else launch.json's sessions_root — run-roster.py's resolution."""
    if flag:
        return os.path.expanduser(flag)
    if os.environ.get("ROBOWRIGHT_SESSIONS_ROOT"):
        return os.path.expanduser(os.environ["ROBOWRIGHT_SESSIONS_ROOT"])
    named = launch_settings(run_cost).get("sessions_root")
    return run_cost.home_path(named) if isinstance(named, str) and named else None


def launch_settings(run_cost):
    try:
        with open(run_cost.LAUNCH_JSON) as f:
            settings = json.load(f)
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def group_of(ticket, group_regex):
    """launch.json's group_regex capture of a ticket, as the launcher writes run.json.project; None outside every group."""
    if not isinstance(ticket, str) or not isinstance(group_regex, str) or not group_regex:
        return None
    try:
        match = re.search(group_regex, ticket)
    except re.error:
        return None
    return match.group(1) if match and match.re.groups and match.group(1) else None


def finished_run(run_dir):
    """The run.json of a finished Worker session, else the reason the dir is skipped."""
    try:
        with open(os.path.join(run_dir, "run.json")) as f:
            run = json.load(f)
    except FileNotFoundError:
        return None, "no run.json"
    except (OSError, ValueError):
        return None, "run.json is not JSON"
    if not isinstance(run, dict):
        return None, "run.json is not a JSON object"
    if run.get("phase") != "done":
        return None, f"phase is {run.get('phase')!r}, not 'done'"
    return run, None


def claimed_sessions(runs_root):
    """{session id: the physical session dirs whose run.json pins it or names it as session_id}, over every dir of any phase."""
    claims = {}
    for name in sorted(os.listdir(runs_root)):
        entry = os.path.join(runs_root, name)
        try:
            with open(os.path.join(entry, "run.json")) as f:
                run = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(run, dict):
            continue
        pins = [os.path.basename(p)[:-len(".jsonl")] for p in run.get("transcripts") or []
                if isinstance(p, str) and p.endswith(".jsonl")]
        named = [run["session_id"]] if isinstance(run.get("session_id"), str) else []
        for session_id in pins + named:
            claims.setdefault(session_id, set()).add(os.path.realpath(entry))
    return claims


def main_transcripts(run, run_dir, run_cost, claimed_elsewhere):
    """The session's own Claude sessions: the pinned transcripts and its desktop scheduled-task runs, else every
    top-level transcript in its worktree's project dir that no other session dir claims."""
    pinned = [os.path.expanduser(p) for p in run.get("transcripts") or []] + run_cost.scheduled_run_transcripts(run_dir)
    if pinned:
        return sorted({p for p in pinned if os.path.isfile(p)})
    worktree = run.get("worktree")
    if not worktree:
        return []
    return sorted(p for p in glob.glob(os.path.join(run_cost.PROJECTS_ROOT, run_cost.project_slug(worktree), "*.jsonl"))
                  if os.path.basename(p)[:-len(".jsonl")] not in claimed_elsewhere)


def session_groups(run_cost, run, run_dir, claimed_elsewhere):
    """(ledger key, records) for each of the session's Claude sessions and each closed unit — the hook's keys, so either
    writer finds what the other already appended."""
    groups = []
    for transcript in main_transcripts(run, run_dir, run_cost, claimed_elsewhere):
        session_id = os.path.basename(transcript)[:-len(".jsonl")]
        groups.append((("session", session_id), run_cost.session_records(run, run_dir, session_id, transcript, "migrate")))
    windows = run_cost.unit_windows(run_dir)
    if windows:
        paths = [p for p in run_cost.transcript_paths(run, run_dir, None) if run_cost.owning_session(p) not in claimed_elsewhere]
        groups += [(("unit", run_dir, unit_id), records)
                   for unit_id, records in run_cost.unit_records(run, run_dir, paths, windows, "migrate").items()]
    return groups


def migrate(run_cost, root, runs_root_flag):
    """Backfill the ledger from every finished Worker session under the sessions root; a group already present is left alone."""
    runs_root = sessions_root(runs_root_flag, run_cost)
    if not runs_root:
        sys.exit("robowright-cost: --migrate has no sessions root: pass --runs-root, set $ROBOWRIGHT_SESSIONS_ROOT, "
                 "or name sessions_root in ~/.claude/robowright/launch.json")
    if not os.path.isdir(runs_root):
        sys.exit(f"robowright-cost: sessions root {runs_root} is not a directory; nothing appended")
    group_regex = (launch_settings(run_cost).get("unit") or {}).get("group_regex")
    claims = claimed_sessions(runs_root)
    groups = []
    for name in sorted(os.listdir(runs_root)):
        entry = os.path.join(runs_root, name)
        if not os.path.isdir(entry):
            continue
        run, reason = finished_run(entry)
        if run is None:
            print(f"robowright-cost: skip {name}: {reason}", file=sys.stderr)
            continue
        if run.get("project") is None:
            run = dict(run, project=group_of(run.get("ticket"), group_regex))
        # Physical, as the hook keys it: one session dir is one ledger key however it was reached.
        run_dir = os.path.realpath(entry)
        claimed_elsewhere = {session_id for session_id, owners in claims.items() if run_dir not in owners}
        groups += session_groups(run_cost, run, run_dir, claimed_elsewhere)
    print("robowright-cost: doc-role sessions (Planner, Lead, Explainer) are not migrated: none before the SessionEnd hook left a role marker",
          file=sys.stderr)
    try:
        n = run_cost.append_records(root, groups)
    except run_cost.session_write.Refused as refusal:
        print(f"refused: --migrate: {refusal}", file=sys.stderr)
        return run_cost.session_write.EXIT_REFUSED
    except OSError as exc:
        sys.exit(f"robowright-cost: cannot append to the ledger under {root}: {exc}")
    print(f"robowright-cost: {n} record(s) appended to {os.path.join(root, 'records.jsonl')}")
    return 0


def print_table(by, rows):
    has_usd = any(row["estimated_usd"] is not None for row in rows)
    usd_head = f" {'est usd':>9}" if has_usd else ""
    print(f"{by:<24} {'requests':>9} {'input':>12} {'output':>12} {'cache read':>14} {'cache write':>13}"
          f"{usd_head} {'active h':>9} {'plan 5h/7d %':>13}   ({scope_of(by)} scope)")
    for row in rows:
        usd = "-" if row["estimated_usd"] is None else f"{row['estimated_usd']:.2f}"
        usd_cell = f" {usd:>9}" if has_usd else ""
        plan = f"{fmt(row['plan_5h_pct'])}/{fmt(row['plan_7d_pct'])}"
        print(f"{str(row['key']):<24} {row['requests']:>9,} {row['input_tokens']:>12,} {row['output_tokens']:>12,} "
              f"{row['cache_read_tokens']:>14,} {row['cache_write_tokens']:>13,}{usd_cell} "
              f"{row['active_hours']:>9.1f} {plan:>13}")


def fmt(value):
    return "-" if value is None else str(value)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--by", choices=BY, help="one row per value of this record field; project, unit, role and model sum session-scope records, "
                         "unit-id sums unit-scope records, one row per unit of work and unit id")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--accounting-root")
    ap.add_argument("--since", type=since_date, help="with --by: only records whose `at` falls on or after this YYYY-MM-DD, in the offset `at` was written in")
    ap.add_argument("--project", help="with --by: only records of this project")
    ap.add_argument("--migrate", action="store_true",
                    help="append session and unit records for every finished Worker session under the sessions root instead")
    ap.add_argument("--runs-root", help="with --migrate: the sessions root (default $ROBOWRIGHT_SESSIONS_ROOT, else launch.json sessions_root)")
    args = ap.parse_args()
    if not args.migrate and not args.by:
        ap.error("--by is required, except with --migrate")

    run_cost = load_run_cost()
    root = run_cost.accounting_root(args.accounting_root)
    if not root:
        sys.exit("robowright-cost: no accounting root: pass --accounting-root, set $ROBOWRIGHT_ACCOUNTING_ROOT, "
                 "or name accounting_root or sessions_root in ~/.claude/robowright/launch.json")
    prices = load_prices()
    stale = prices.stale_warning()
    if stale:
        print(stale, file=sys.stderr)
    if args.migrate:
        return migrate(run_cost, root, args.runs_root)
    records = [r for r in read_records(os.path.join(root, "records.jsonl"))
               if (args.since is None or written_on(r) is not None and written_on(r) >= args.since)
               and (args.project is None or r.get("project") == args.project)]
    rows = rollup(records, args.by, priced=prices.as_of is not None)
    billed = dollar_billed(records, args.by)
    for row in rows:
        if row["key"] not in billed:
            row["estimated_usd"] = None
    if args.json:
        json.dump({"by": args.by, "scope": scope_of(args.by), "rows": rows}, sys.stdout, indent=2)
        print()
        return 0
    print_table(args.by, rows)
    print(f"\n{prices.as_of_line()}; each record's estimate was priced when it was written (its price_as_of)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
