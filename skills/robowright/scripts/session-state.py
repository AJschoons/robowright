#!/usr/bin/env python3
"""session-state.py — the one writer of a Robowright Session's state.

Every change to run.json's `phase`, `stop_reason`, `rotate`, `rebriefs`, and a unit's `status`,
`gate_attempts` and `head` goes through one event here. The event is checked against
../state-machine.json (legal from-state, then every guard), applied atomically, and appended to
<session_dir>/events.jsonl. Anything else in run.json is still edited directly.

    session-state.py <session_dir> <event> [options]     apply one transition
    session-state.py <session_dir> status [--json]       state, legal events, problems
    session-state.py <session_dir> check                 exit 1 when the stored state is illegal
    session-state.py <session_dir> check-op <op>         may a launcher launch | rotate | resume
    session-state.py <session_dir> adopt --by <who> --reason <text>
                                                         baseline a session the tool did not write
    session-state.py doc [--write | --check]             generate ../STATES.md from the table

Events and their options:
    preflight-pass | intake-complete | begin-end-of-stack | finish | rotation-resumed
    request-rotate   [--next-unit ID]
    stop             --code CODE --detail TEXT
    resume           --by owner|lead --decision TEXT [--phase PHASE] [--wall-hours H]
    rebrief          --verdict confident|owner --why TEXT [--next-unit ID]
    plan-review      --verdict ship|polish|rebrief [--unit ID, required from implementing]
    rebase           --base SHA --head SHA --by owner|lead --decision TEXT [--unit-heads U1=SHA,U2=SHA]
    park             --by owner --reason TEXT
    accept           --head SHA
    unit-start | gate-hold | gate-advance   [--unit ID] [--review PATH]
    unit-close       [--unit ID] --head SHA

Exit codes: 0 applied or legal; 1 illegal stored state, or usage; 2 refused (a guard failed or
the event is not legal from the current state). A refusal changes nothing and is logged.
"""

import argparse
import copy
import hashlib
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import owner_git  # noqa: E402
import session_write  # noqa: E402

TABLE_PATH = Path(__file__).resolve().parent.parent / "state-machine.json"
DOC_PATH = TABLE_PATH.parent / "STATES.md"

UNIT_IN_FLIGHT = ("building", "held", "gated")
PRE_UNIT_PHASES = ("preflight", "intake")
POST_UNIT_PHASES = ("end-of-stack", "done")
PUBLISH_STRATEGIES = {"draft-pr", "local-branch", "push-to-branch", "pr-plus-deploy"}

EXIT_OK = 0
EXIT_ILLEGAL = 1
EXIT_REFUSED = 2


class Refused(Exception):
    def __init__(self, guard, why):
        super().__init__(why)
        self.guard = guard
        self.why = why


# ---------------------------------------------------------------- table


def load_table():
    with open(TABLE_PATH) as fh:
        return json.load(fh)


def machine(table, machine_id):
    for m in table["machines"]:
        if m["id"] == machine_id:
            return m
    raise KeyError(machine_id)


def phase_map(table):
    return {s["phase"]: s["id"] for s in machine(table, "session")["states"] if "phase" in s}


def transition(table, event):
    for m in table["machines"]:
        if m.get("enforced") is not True:
            continue
        for t in m["transitions"]:
            if t["event"] == event:
                return m, t
    return None, None


def enforced_events(table):
    return [t["event"] for m in table["machines"] if m.get("enforced") is True for t in m["transitions"]]


# ---------------------------------------------------------------- stored state


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def stop_code(run):
    stop = run.get("stop_reason")
    return stop.get("code") if isinstance(stop, dict) else stop or None


def stop_fields(run):
    stop = run.get("stop_reason")
    return stop if isinstance(stop, dict) else {}


def pending_rotation(run):
    rotate = run.get("rotate") or {}
    return bool(rotate.get("requested_at")) and not rotate.get("resumed_at")


def session_state(table, run):
    """The session machine's state, or None when `phase` is not one the table knows."""
    phase = run.get("phase") or "preflight"
    if phase == "done":
        return "done"
    # A stop code with a working phase is the encoding older sessions wrote; read, never written.
    if phase == "stopped" or stop_code(run):
        return "stopped"
    if pending_rotation(run):
        return "awaiting-rotation" if phase in phase_map(table) else None
    return phase_map(table).get(phase)


def never_launched(table, run, session_dir, is_live):
    """A brief nothing launched. `briefed` also covers a preflight that is running or died, so each mark a launch
    leaves rules it out: a live session, the launcher's pin (`session_id`, `transcripts`), any event. `started_at` is
    written only by `preflight-pass`, which also leaves `briefed`, so it guards against a hand edit."""
    if session_state(table, run) != "briefed" or is_live:
        return False
    if run.get("session_id") or run.get("transcripts") or run.get("started_at"):
        return False
    return not read_events(Path(session_dir))


def effective_phase(run):
    """The working phase the units belong to: `phase_before` while stopped, else `phase`."""
    phase = run.get("phase") or "preflight"
    if phase == "stopped":
        return stop_fields(run).get("phase_before")
    return phase


def units(run):
    return [u for u in (run.get("units") or []) if isinstance(u, dict)]


def unit_status(unit):
    return unit.get("status") or "todo"


def in_flight(run):
    return [u for u in units(run) if unit_status(u) in UNIT_IN_FLIGHT]


def attempts(unit):
    value = unit.get("gate_attempts")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def unit_rows(run):
    return [[u.get("id"), unit_status(u), u.get("gate_attempts") or 0, u.get("head") or ""] for u in units(run)]


def digests(run):
    core = {k: run.get(k) for k in ("phase", "stop_reason", "rotate")}
    core["rebriefs"] = run.get("rebriefs") or []
    return {"core": _sha(core), "units": _sha(unit_rows(run))}


def model_digests(run):
    """The models the launcher passes as flags. Kept out of digests(), whose value every existing event log holds."""
    return {"model": _sha(run.get("model")), "unit_models": _sha([u.get("model") for u in units(run)])}


def event_digest(run):
    return dict(digests(run), **model_digests(run))


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def read_events(session_dir):
    path = session_dir / "events.jsonl"
    if not path.is_file():
        return []
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = None
        # A half-written append must cost one line, never the roster or the tool.
        rows.append(row if isinstance(row, dict) else {"corrupt": True, "line": number})
    return rows


def applied(events):
    return [e for e in events if e.get("refused") is not True and e.get("corrupt") is not True]


def legal_publish(value):
    # false and null publish nothing; a dict is what publishing wrote over the key
    if value is None or value is False or isinstance(value, dict):
        return True
    return isinstance(value, str) and value in PUBLISH_STRATEGIES


def state_problems(table, run):
    """Every way the stored state is one the table cannot produce. Empty means legal."""
    out = []
    phase = run.get("phase") or "preflight"
    code = stop_code(run)
    if phase not in phase_map(table):
        out.append(f"unknown-phase: phase is '{phase}'")
        return out
    if phase == "stopped" and not code:
        out.append("stopped-without-code: phase is stopped and stop_reason has no code")
    if code and code not in table["stop_codes"]:
        out.append(f"unknown-stop-code: '{code}'")
    if phase == "done" and code:
        out.append("done-and-stopped: phase is done and stop_reason is set")
    if phase == "parked" and code:
        out.append("parked-and-stopped: phase is parked and stop_reason is set")
    if phase == "done" and pending_rotation(run):
        out.append("done-and-rotating: phase is done and a rotation is pending")
    if code and pending_rotation(run):
        out.append("stopped-and-rotating: stop_reason is set and a rotation is pending")
    if not legal_publish(run.get("publish")):
        out.append(f"bad-publish: publish is {run.get('publish')!r}, not a publish strategy, false, null or a record")

    known = [s["id"] for s in machine(table, "unit")["states"]]
    rows = units(run)
    for u in rows:
        if unit_status(u) not in known:
            out.append(f"unknown-unit-status: {u.get('id')} is '{unit_status(u)}'")
    ids = [u.get("id") for u in rows]
    if len(set(ids)) != len(ids):
        out.append("duplicate-unit-id")
    if len(in_flight(run)) > 1:
        out.append("two-units-in-flight: " + ", ".join(str(u.get("id")) for u in in_flight(run)))
    seen_open = False
    for u in rows:
        if unit_status(u) != "done":
            seen_open = True
        elif seen_open:
            out.append(f"unit-out-of-order: {u.get('id')} is done after a unit that is not")
            break
    cap = run.get("max_gate_attempts")
    for u in rows:
        if u.get("gate_attempts") is not None and attempts(u) != u.get("gate_attempts"):
            out.append(f"bad-gate-attempts: {u.get('id')} has gate_attempts {u.get('gate_attempts')!r}, not a whole number")
        if isinstance(cap, int) and attempts(u) > cap:
            out.append(f"gate-attempts-over-cap: {u.get('id')} has {u.get('gate_attempts')} of {cap}")

    working = effective_phase(run)
    if working in PRE_UNIT_PHASES and any(unit_status(u) != "todo" for u in rows):
        out.append(f"units-started-before-implement: phase is {working}")
    if working in POST_UNIT_PHASES and (not rows or any(unit_status(u) != "done" for u in rows)):
        out.append(f"units-open-after-implement: phase is {working}")
    if working == "implement" and not rows:
        out.append("implementing-without-units")
    if pending_rotation(run) and in_flight(run):
        out.append("rotating-mid-unit: a rotation is pending while a unit is in flight")
    return out


def log_problems(table, run, events, ignore_units=False):
    """The stored state is legal but was not written by this tool."""
    done = applied(events)
    trailing = [e for e in events[(events.index(done[-1]) + 1 if done else 0):] if e.get("corrupt") is True]
    out = [f"corrupt-event-log: events.jsonl line {e['line']} is not an event; `adopt` re-baselines" for e in trailing[:1]]
    if not done:
        if session_state(table, run) == "briefed":
            return out
        return out + ["no-event-log: state is past briefed with no events.jsonl; `adopt` it"]
    last = done[-1].get("digest") or {}
    now = digests(run)
    if last.get("core") != now["core"]:
        out.append("edited-outside-tool: phase, stop_reason, rotate or rebriefs changed since the last event")
    if ignore_units is False and effective_phase(run) not in PRE_UNIT_PHASES and last.get("units") != now["units"]:
        out.append("edited-outside-tool: a unit's id, status, gate_attempts or head changed since the last event")
    # An event written before the models were guarded carries neither key.
    models = model_digests(run)
    if ignore_units is False and "model" in last and last["model"] != models["model"]:
        out.append("edited-outside-tool: model changed since the last event")
    if ignore_units is False and effective_phase(run) not in PRE_UNIT_PHASES and "unit_models" in last and last["unit_models"] != models["unit_models"]:
        out.append("edited-outside-tool: model changed on a unit since the last event")
    return out


def problems(table, run, events):
    return state_problems(table, run) + log_problems(table, run, events)


def legal_events(table, run):
    state = session_state(table, run)
    out = []
    for m in table["machines"]:
        if m.get("enforced") is not True:
            continue
        for t in m["transitions"]:
            if m["id"] == "session" and state in t["from"]:
                out.append(t["event"])
            if m["id"] == "unit" and state == "implementing":
                if any(unit_status(u) in t["from"] for u in units(run)):
                    out.append(t["event"])
    return out


# ---------------------------------------------------------------- guards


class Ctx:
    def __init__(self, table, session_dir, run, events, args):
        self.table = table
        self.dir = session_dir
        self.run = run
        self.events = events
        self.args = args
        self.unit = None
        self.notes = []
        self.record = {}


def _need(flag, value):
    if value is None or str(value).strip() == "":
        raise Refused(flag, f"--{flag} is required and may not be empty")


def _exists(ctx, guard, rel):
    if not (ctx.dir / rel).is_file():
        raise Refused(guard, f"{ctx.dir / rel} does not exist")


def g_brief_exists(ctx):
    _exists(ctx, "brief-exists", "BRIEF.md")


def g_units_populated(ctx):
    rows = units(ctx.run)
    if not rows or any(not u.get("id") for u in rows):
        raise Refused("units-populated", "run.json.units needs at least one unit, each with an id")


def g_rotation_enabled(ctx):
    if ctx.run.get("rotate_sessions") is not True:
        raise Refused("rotation-enabled", "run.json.rotate_sessions is not true: continue to the next unit")


def g_no_unit_in_flight(ctx):
    flying = in_flight(ctx.run)
    if flying:
        raise Refused("no-unit-in-flight", f"{flying[0].get('id')} is {unit_status(flying[0])}")


def g_a_unit_is_done(ctx):
    if not any(unit_status(u) == "done" for u in units(ctx.run)):
        raise Refused("a-unit-is-done", "no unit is done: a rotation happens at a unit boundary")


def g_a_unit_is_todo(ctx):
    if not any(unit_status(u) == "todo" for u in units(ctx.run)):
        raise Refused("a-unit-is-todo", "no unit is todo: after the last unit, begin-end-of-stack in this session")


def g_all_units_done(ctx):
    open_units = [u.get("id") for u in units(ctx.run) if unit_status(u) != "done"]
    if open_units or not units(ctx.run):
        raise Refused("all-units-done", "not done: " + (", ".join(map(str, open_units)) or "no units"))


def g_end_of_stack_review_exists(ctx):
    _exists(ctx, "end-of-stack-review-exists", "reviews/end-of-stack.md")


def g_end_of_stack_review_says_advance(ctx):
    path = ctx.dir / "reviews/end-of-stack.md"
    verdict = gate_verdict(path)
    if verdict != "ADVANCE":
        raise Refused("end-of-stack-review-says-advance", f"{path} first line says {verdict or 'neither ADVANCE nor HOLD'}, not ADVANCE")


def g_handoff_exists(ctx):
    _exists(ctx, "handoff-exists", "HANDOFF.md")


def g_handback_exists(ctx):
    _exists(ctx, "handback-exists", "HANDBACK.md")


def g_stop_code_known(ctx):
    _need("code", ctx.args.code)
    if ctx.args.code not in ctx.table["stop_codes"]:
        raise Refused("stop-code-known", f"'{ctx.args.code}' is not one of: " + ", ".join(ctx.table["stop_codes"]))


def g_stop_detail_given(ctx):
    _need("detail", ctx.args.detail)


def g_stop_file_present_for_owner_stop(ctx):
    if ctx.args.code == "owner-stop" and not (ctx.dir / "STOP").exists():
        raise Refused("stop-file-present-for-owner-stop", f"{ctx.dir / 'STOP'} does not exist")


def g_stop_file_absent(ctx):
    if (ctx.dir / "STOP").exists():
        raise Refused("stop-file-absent", f"{ctx.dir / 'STOP'} still exists")


def g_decision_given(ctx):
    _need("decision", ctx.args.decision)


def g_decider_allowed(ctx):
    _need("by", ctx.args.by)
    if ctx.args.by == "owner":
        return
    rules = ctx.table["delegation"]
    level = ctx.run.get("delegation") or "owner"
    if level not in rules["lead_may_decide_at"]:
        raise Refused("decider-allowed", f"delegation is '{level}': every decision is the Owner's")
    if stop_code(ctx.run) in rules["owner_only_codes"]:
        raise Refused("decider-allowed", f"'{stop_code(ctx.run)}' is the Owner's at every delegation level")


def stops_since_rebrief(events):
    count = 0
    for e in applied(events):
        if e.get("event") == "rebrief":
            count = 0
        elif e.get("event") == "stop":
            count += 1
    return count


def g_not_rebrief_due_for_lead(ctx):
    limit = ctx.table["delegation"]["rebrief_after_stops"]
    if ctx.args.by == "lead" and stops_since_rebrief(ctx.events) >= limit:
        raise Refused("not-rebrief-due-for-lead", f"stop {stops_since_rebrief(ctx.events)} since the last rebrief: rebrief, or the Owner's call")


def lead_extended_before(events):
    return any(e.get("event") == "resume" and e.get("actor") == "lead" and "wall_hours" in e for e in applied(events))


def g_wall_extension_allowed(ctx):
    hours = ctx.args.wall_hours
    if hours is None:
        return
    guard = "wall-extension-allowed"
    if stop_code(ctx.run) != "budget":
        raise Refused(guard, f"--wall-hours answers a budget stop; this stop is '{stop_code(ctx.run)}'")
    start = ctx.run.get("max_wall_hours")
    if not isinstance(start, (int, float)) or not math.isfinite(start):
        raise Refused(guard, "run.json has no max_wall_hours to extend from")
    if not math.isfinite(hours) or hours <= start:
        raise Refused(guard, f"--wall-hours {hours} must be a finite number above the current {start}")
    if ctx.args.by == "owner":
        return
    pct = ctx.run.get("wall_hours_extension_pct")
    if not isinstance(pct, (int, float)) or not math.isfinite(pct):
        raise Refused(guard, "run.json has no wall_hours_extension_pct: a Lead extension is the Owner's")
    cap = start * (1 + pct / 100)
    # 3 h at 20% computes as 3.5999…; a cap the refusal prints as 3.6 must admit 3.6
    if hours > cap and not math.isclose(hours, cap):
        raise Refused(guard, f"--wall-hours {hours} is past the Lead's cap {cap:g} ({start:g} + {pct:g}%)")
    if lead_extended_before(ctx.events):
        raise Refused(guard, "the Lead already extended this session's wall once: the next is the Owner's")


def verdict_word(text):
    # The by-hand form is `## Verdict: `polish``; a later line or a prose mention never counts.
    line = re.search(r"(?im)^\s*#*\s*Verdict:(.*)$", text)
    if line is None:
        return None
    word = re.match(r"[a-z]+", line.group(1).lstrip("`* \t"), re.I)
    return word.group(0).lower() if word else None


def g_rebrief_file_has_verdict(ctx):
    _need("verdict", ctx.args.verdict)
    _need("why", ctx.args.why)
    if ctx.args.verdict not in ("confident", "owner"):
        raise Refused("rebrief-file-has-verdict", f"'{ctx.args.verdict}' is not a rebrief verdict: confident or owner")
    _exists(ctx, "rebrief-file-has-verdict", "REBRIEF.md")
    if verdict_word((ctx.dir / "REBRIEF.md").read_text()) != ctx.args.verdict:
        raise Refused("rebrief-file-has-verdict", f"REBRIEF.md's first Verdict: line does not say '{ctx.args.verdict}'")


def g_superseded_brief_kept(ctx):
    n = len(ctx.run.get("rebriefs") or []) + 1
    _exists(ctx, "superseded-brief-kept", f"BRIEF.r{n}.md")


def g_done_units_untouched(ctx):
    done = applied(ctx.events)
    before = done[-1].get("units") if done else None
    if before is None:
        raise Refused("done-units-untouched", "the last event recorded no unit rows: `adopt` first")
    was = [row for row in before if row[1] == "done"]
    now = [row for row in unit_rows(ctx.run) if row[1] == "done"]
    if was != now:
        raise Refused("done-units-untouched", "a done unit was added, removed or changed: a rebrief re-cuts only what is not done")


def g_session_is_implementing(ctx):
    state = session_state(ctx.table, ctx.run)
    if state != "implementing":
        raise Refused("session-is-implementing", f"the session is {state}")


def g_predecessors_done(ctx):
    for u in units(ctx.run):
        if u is ctx.unit:
            return
        if unit_status(u) != "done":
            raise Refused("predecessors-done", f"{u.get('id')} is {unit_status(u)}: units run in order")


def g_gate_attempts_under_cap(ctx):
    cap = ctx.run.get("max_gate_attempts")
    cap = cap if isinstance(cap, int) else 3
    if attempts(ctx.unit) >= cap:
        raise Refused("gate-attempts-under-cap", f"{ctx.unit.get('id')} has used {attempts(ctx.unit)} of {cap}: stop with verification-failed")


def review_path(ctx):
    rel = ctx.args.review or f"reviews/{ctx.unit.get('id')}-gate.md"
    return ctx.dir / rel


def gate_verdict(path):
    for line in path.read_text().splitlines():
        word = line.strip().strip("`*# ").upper()
        if word:
            return word if word in ("ADVANCE", "HOLD") else None
    return None


def g_gate_review_is_fresh(ctx):
    path = review_path(ctx)
    if not path.is_file():
        raise Refused("gate-review-is-fresh", f"{path} does not exist")
    previous = [e for e in applied(ctx.events) if e.get("unit") == ctx.unit.get("id") and e.get("event") in ("gate-hold", "gate-advance")]
    if previous and path.stat().st_mtime <= previous[-1].get("review_mtime", 0):
        raise Refused("gate-review-is-fresh", f"{path} has not been rewritten since the last gate event: re-gate first")


def _gate_says(ctx, guard, wanted):
    path = review_path(ctx)
    if not path.is_file():
        raise Refused(guard, f"{path} does not exist")
    verdict = gate_verdict(path)
    if verdict != wanted:
        raise Refused(guard, f"{path} first line says {verdict or 'neither ADVANCE nor HOLD'}, not {wanted}")


def g_gate_review_says_hold(ctx):
    _gate_says(ctx, "gate-review-says-hold", "HOLD")


def g_gate_review_says_advance(ctx):
    _gate_says(ctx, "gate-review-says-advance", "ADVANCE")


def g_head_given(ctx):
    _need("head", ctx.args.head)
    shas = [ctx.args.head] + [sha for _, sha in unit_heads(ctx)]
    for sha in shas:
        if re.fullmatch(r"[0-9a-f]{7,40}", sha) is None:
            raise Refused("head-given", f"'{sha}' is not a commit SHA")
    worktree = ctx.run.get("worktree")
    # A unit closed after teardown has nothing to resolve against; the shape check stands alone.
    if not isinstance(worktree, str) or not os.path.isdir(worktree):
        return
    worktree = _listed_worktree("head-given", worktree)
    for sha in shas:
        if not _is_commit(worktree, sha):
            raise Refused("head-given", f"'{sha}' names no commit in {worktree}")


PLAN_VERDICTS = ("ship", "polish", "rebrief")


PLAN_REVIEW_MODES = ("finish", "per-unit", "off")


def plan_review_mode(ctx, guard):
    # A run.json written before the finish review existed reads as the default.
    mode = ctx.run.get("plan_review")
    if mode is None:
        return "finish"
    if isinstance(mode, str) and mode in PLAN_REVIEW_MODES:
        return mode
    if isinstance(mode, str):
        raise Refused(guard, f"run.json.plan_review is the string '{mode}': expected finish, per-unit or off")
    why = f"run.json.plan_review is the {json_type(mode)} {json.dumps(mode)}, not a string: expected finish, per-unit or off"
    if isinstance(mode, bool):
        why += '; the old schema\'s boolean maps as false → "off", true → "finish"'
    raise Refused(guard, why)


def json_type(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    return "object"


def g_plan_review_on(ctx):
    if plan_review_mode(ctx, "plan-review-on") == "off":
        raise Refused("plan-review-on", "run.json.plan_review is off: this session records no plan review")


def g_plan_review_file_has_verdict(ctx):
    _need("verdict", ctx.args.verdict)
    if ctx.args.verdict not in PLAN_VERDICTS:
        raise Refused("plan-review-file-has-verdict", f"'{ctx.args.verdict}' is not a plan review verdict: one of {', '.join(PLAN_VERDICTS)}")
    if session_state(ctx.table, ctx.run) == "implementing":
        if not ctx.args.unit:
            raise Refused("unit-known", "from implementing, --unit names the unit the per-unit review judged")
        if ctx.args.unit not in [u.get("id") for u in units(ctx.run)]:
            raise Refused("unit-known", f"no unit '{ctx.args.unit}' in run.json")
    _exists(ctx, "plan-review-file-has-verdict", "PLAN-REVIEW.md")
    if verdict_word((ctx.dir / "PLAN-REVIEW.md").read_text()) != ctx.args.verdict:
        raise Refused("plan-review-file-has-verdict", f"PLAN-REVIEW.md's first Verdict: line does not say '{ctx.args.verdict}'")


def g_plan_review_settled(ctx):
    guard = "plan-review-settled"
    if plan_review_mode(ctx, guard) == "off":
        return
    finish_reviews = [r for r in (ctx.run.get("plan_reviews") or []) if isinstance(r, dict) and r.get("unit") is None]
    if not finish_reviews:
        raise Refused(guard, "no finish review is recorded: run planner-review, then `plan-review --verdict`")
    verdict = finish_reviews[-1].get("verdict")
    if verdict == "ship":
        return
    if verdict == "polish":
        gate = ctx.dir / "reviews/polish-gate.md"
        if not gate.is_file() or gate_verdict(gate) != "ADVANCE":
            raise Refused(guard, f"the finish review said polish and {gate} does not say ADVANCE")
        # `at` is whole seconds, so a gate written in the review's own second is fresh.
        if int(gate.stat().st_mtime) < datetime.fromisoformat(finish_reviews[-1]["at"]).timestamp():
            raise Refused(guard, "reviews/polish-gate.md predates the finish review: re-gate the polish")
        return
    raise Refused(guard, f"the finish review said {verdict}: stop with rebrief, never finish")


def g_base_given(ctx):
    _need("base", ctx.args.base)
    worktree = ctx.run.get("worktree")
    if not isinstance(worktree, str) or not os.path.isdir(worktree):
        raise Refused("base-given", f"run.json.worktree ({worktree!r}) is not a directory: the base cannot be checked")
    worktree = _listed_worktree("base-given", worktree)
    if re.fullmatch(r"[0-9a-f]{7,40}", ctx.args.base) is None or not _is_commit(worktree, ctx.args.base):
        raise Refused("base-given", f"'{ctx.args.base}' names no commit in {worktree}")
    if owner_git.run(worktree, "merge-base", "--is-ancestor", ctx.args.base, "HEAD").returncode != 0:
        raise Refused("base-given", f"'{ctx.args.base}' is not an ancestor of HEAD in {worktree}")


def _listed_worktree(guard, worktree):
    """run.json.worktree, canonical, once a configured repository lists it; refused before any git runs inside it."""
    try:
        return owner_git.check(worktree)[0]
    except owner_git.Unlisted as refusal:
        raise Refused(guard, f"{refusal.code}: {refusal.detail}")


def _is_commit(worktree, sha):
    return owner_git.run(worktree, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def unit_heads(ctx):
    """--unit-heads U1=<sha>,U2=<sha> as (unit, sha) pairs; each must name a done unit."""
    pairs = []
    for item in (ctx.args.unit_heads or "").split(","):
        if not item.strip():
            continue
        uid, _, sha = item.strip().partition("=")
        matches = [u for u in units(ctx.run) if u.get("id") == uid]
        if not matches:
            raise Refused("unit-known", f"--unit-heads names no unit '{uid}' in run.json")
        if unit_status(matches[0]) != "done":
            raise Refused("head-given", f"--unit-heads names {uid}, which is {unit_status(matches[0])}: only a done unit's head is rewritten")
        pairs.append((matches[0], sha))
    return pairs


def g_park_is_owner(ctx):
    _need("by", ctx.args.by)
    if ctx.args.by != "owner":
        raise Refused("park-is-owner", "park is the Owner's alone; the Lead never applies it")


def g_park_reason_given(ctx):
    _need("reason", ctx.args.reason)


GUARDS = {
    "brief-exists": g_brief_exists,
    "units-populated": g_units_populated,
    "rotation-enabled": g_rotation_enabled,
    "no-unit-in-flight": g_no_unit_in_flight,
    "a-unit-is-done": g_a_unit_is_done,
    "a-unit-is-todo": g_a_unit_is_todo,
    "all-units-done": g_all_units_done,
    "end-of-stack-review-exists": g_end_of_stack_review_exists,
    "end-of-stack-review-says-advance": g_end_of_stack_review_says_advance,
    "handoff-exists": g_handoff_exists,
    "handback-exists": g_handback_exists,
    "stop-code-known": g_stop_code_known,
    "stop-detail-given": g_stop_detail_given,
    "stop-file-present-for-owner-stop": g_stop_file_present_for_owner_stop,
    "stop-file-absent": g_stop_file_absent,
    "decision-given": g_decision_given,
    "decider-allowed": g_decider_allowed,
    "not-rebrief-due-for-lead": g_not_rebrief_due_for_lead,
    "wall-extension-allowed": g_wall_extension_allowed,
    "rebrief-file-has-verdict": g_rebrief_file_has_verdict,
    "superseded-brief-kept": g_superseded_brief_kept,
    "done-units-untouched": g_done_units_untouched,
    "session-is-implementing": g_session_is_implementing,
    "predecessors-done": g_predecessors_done,
    "gate-attempts-under-cap": g_gate_attempts_under_cap,
    "gate-review-is-fresh": g_gate_review_is_fresh,
    "gate-review-says-hold": g_gate_review_says_hold,
    "gate-review-says-advance": g_gate_review_says_advance,
    "head-given": g_head_given,
    "plan-review-on": g_plan_review_on,
    "plan-review-file-has-verdict": g_plan_review_file_has_verdict,
    "plan-review-settled": g_plan_review_settled,
    "base-given": g_base_given,
    "park-is-owner": g_park_is_owner,
    "park-reason-given": g_park_reason_given,
}


# ---------------------------------------------------------------- effects


def first_open_unit(run):
    for u in units(run):
        if unit_status(u) != "done":
            return u.get("id")
    return None


def phase_before(ctx):
    stored = stop_fields(ctx.run).get("phase_before")
    if ctx.run.get("phase") != "stopped":
        stored = stored or ctx.run.get("phase")
    target = ctx.args.phase or stored
    working = [s["phase"] for s in machine(ctx.table, "session")["states"] if s["id"] in machine(ctx.table, "session")["groups"][0]["states"]]
    if target not in working:
        raise Refused("phase-before", f"stop_reason has no usable phase_before ('{target}'): pass --phase, one of {', '.join(working)}")
    return target


def e_preflight_pass(ctx, at):
    ctx.run["phase"] = "intake"
    ctx.run["started_at"] = ctx.run.get("started_at") or at


def e_intake_complete(ctx, at):
    ctx.run["phase"] = "implement"


def e_request_rotate(ctx, at):
    ctx.run["rotate"] = {"requested_at": at, "resumed_at": None, "next_unit": ctx.args.next_unit or first_open_unit(ctx.run)}


def e_rotation_resumed(ctx, at):
    ctx.run["rotate"]["resumed_at"] = at


def e_begin_end_of_stack(ctx, at):
    ctx.run["phase"] = "end-of-stack"


def e_finish(ctx, at):
    ctx.run["phase"] = "done"


def e_stop(ctx, at):
    ctx.run["stop_reason"] = {"code": ctx.args.code, "detail": ctx.args.detail, "at": at, "phase_before": ctx.run.get("phase") or "preflight"}
    ctx.run["phase"] = "stopped"
    ctx.run["rotate"] = None


def e_resume(ctx, at):
    # The decision answers a unit that ran out of gate attempts; it gets a fresh budget, or the
    # only legal event left would be another stop.
    if stop_code(ctx.run) == "verification-failed":
        for unit in in_flight(ctx.run):
            unit["gate_attempts"] = 0
    if ctx.args.wall_hours is not None:
        ctx.record["wall_hours"] = [ctx.run["max_wall_hours"], ctx.args.wall_hours]
        ctx.run["max_wall_hours"] = ctx.args.wall_hours
    ctx.run["phase"] = phase_before(ctx)
    ctx.run["stop_reason"] = None


def e_rebrief(ctx, at):
    code = stop_code(ctx.run)
    # Everything not done is re-planned, the unit that was in flight included.
    for unit in units(ctx.run):
        if unit_status(unit) != "done":
            unit.update(status="todo", gate_attempts=0, head="")
    ctx.run["phase"] = phase_before(ctx)
    ctx.run["stop_reason"] = None
    entries = list(ctx.run.get("rebriefs") or [])
    entries.append({"n": len(entries) + 1, "at": at, "by": "planner", "verdict": ctx.args.verdict, "why": ctx.args.why, "stop_code": code})
    ctx.run["rebriefs"] = entries
    ctx.run["rotate"] = {"requested_at": at, "resumed_at": None, "next_unit": ctx.args.next_unit or first_open_unit(ctx.run), "reason": "rebrief"}


# A lock name becomes a directory park removes, so it is one segment, as the launcher holds it.
LOCK_NAME = re.compile(r"[a-z0-9-]+")


def is_lock_name(name):
    return isinstance(name, str) and LOCK_NAME.fullmatch(name) is not None


def lock_names(run):
    return [n for n in (run.get("locks") or []) if is_lock_name(n)]


def lock_owner(lock):
    try:
        first = (lock / "owner").read_text().splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    return os.path.realpath(first) if first else None


def locks_root(ctx, here):
    """The sessions_root the launcher reads from launch.json, resolved as it resolves it; the session dir's parent where there is none."""
    parent = Path(here).parent
    config = Path.home() / ".claude/robowright/launch.json"
    if not config.exists():
        return parent
    try:
        settings = json.loads(config.read_text())
    except (OSError, ValueError) as error:
        ctx.notes.append(f"locks: {config} is unreadable ({error}); looked beside the session dir")
        return parent
    root = settings.get("sessions_root") if isinstance(settings, dict) else None
    if not (isinstance(root, str) and root):
        ctx.notes.append(f"locks: {config} has no string sessions_root; looked beside the session dir")
        return parent
    if root.startswith("~/"):
        root = str(Path.home()) + root[1:]
    return Path(os.path.realpath(root))


def release_own_locks(ctx):
    """Removes each lock this session holds; every other lock is left and noted."""
    released = []
    here = os.path.realpath(ctx.dir)
    names = lock_names(ctx.run)
    root = locks_root(ctx, here) if names else None
    for name in names:
        lock = root / f".{name}-lock"
        if not lock.is_dir():
            ctx.notes.append(f"lock {name}: {lock} is absent; nothing released")
            continue
        owner = lock_owner(lock)
        if owner != here:
            ctx.notes.append(f"lock {name}: left in place, owner is {owner or 'unreadable'}")
            continue
        shutil.rmtree(lock)
        released.append(name)
    return released


def e_park(ctx, at):
    code = stop_code(ctx.run)
    if code:
        origin = f"stopped:{code}"
    elif session_state(ctx.table, ctx.run) == "briefed":
        origin = "briefed"
    else:
        origin = "done"
    listed = ctx.run.get("locks")
    for entry in listed if isinstance(listed, list) else []:
        if not is_lock_name(entry):
            ctx.notes.append(f"lock entry {json.dumps(entry)}: not a lock name; nothing released")
    released = release_own_locks(ctx)
    ctx.run["parked"] = {"by": ctx.args.by, "reason": ctx.args.reason, "at": at, "from": origin, "released": released}
    ctx.run["stop_reason"] = None
    ctx.run["phase"] = "parked"


def e_accept(ctx, at):
    ctx.run["accepted"] = {"sha": ctx.args.head, "at": at}


def e_plan_review(ctx, at):
    entries = list(ctx.run.get("plan_reviews") or [])
    unit = ctx.args.unit if session_state(ctx.table, ctx.run) == "implementing" else None
    entries.append({"n": len(entries) + 1, "at": at, "verdict": ctx.args.verdict, "unit": unit, "path": "PLAN-REVIEW.md"})
    ctx.run["plan_reviews"] = entries
    if unit:
        ctx.record["unit"] = unit


def e_rebase(ctx, at):
    for unit, sha in unit_heads(ctx):
        unit["head"] = sha
    entries = list(ctx.run.get("rebases") or [])
    entries.append({"n": len(entries) + 1, "at": at, "from": ctx.run.get("base_sha"), "to": ctx.args.base, "tip": ctx.args.head, "by": ctx.args.by, "decision": ctx.args.decision})
    ctx.run["rebases"] = entries
    ctx.run["base_sha"] = ctx.args.base


def e_unit_start(ctx, at):
    ctx.unit["status"] = "building"


def _record_gate(ctx, status):
    ctx.unit["status"] = status
    ctx.unit["gate_attempts"] = attempts(ctx.unit) + 1
    gate = ctx.unit.get("gate") if isinstance(ctx.unit.get("gate"), dict) else {}
    gate["review"] = str(review_path(ctx).relative_to(ctx.dir)) if review_path(ctx).is_relative_to(ctx.dir) else str(review_path(ctx))
    ctx.unit["gate"] = gate


def e_gate_hold(ctx, at):
    _record_gate(ctx, "held")


def e_gate_advance(ctx, at):
    _record_gate(ctx, "gated")


def e_unit_close(ctx, at):
    ctx.unit["status"] = "done"
    ctx.unit["head"] = ctx.args.head


EFFECTS = {
    "preflight-pass": e_preflight_pass,
    "intake-complete": e_intake_complete,
    "request-rotate": e_request_rotate,
    "rotation-resumed": e_rotation_resumed,
    "begin-end-of-stack": e_begin_end_of_stack,
    "finish": e_finish,
    "stop": e_stop,
    "resume": e_resume,
    "rebrief": e_rebrief,
    "park": e_park,
    "accept": e_accept,
    "plan-review": e_plan_review,
    "rebase": e_rebase,
    "unit-start": e_unit_start,
    "gate-hold": e_gate_hold,
    "gate-advance": e_gate_advance,
    "unit-close": e_unit_close,
}


# ---------------------------------------------------------------- apply


def pick_unit(ctx, t):
    rows = units(ctx.run)
    if ctx.args.unit:
        matches = [u for u in rows if u.get("id") == ctx.args.unit]
        if not matches:
            raise Refused("unit-known", f"no unit '{ctx.args.unit}' in run.json")
        return matches[0]
    candidates = [u for u in rows if unit_status(u) in t["from"]]
    if not candidates:
        raise Refused("from-state", f"no unit is {' or '.join(t['from'])}")
    return candidates[0]


def append_event(session_dir, record):
    path = session_dir / "events.jsonl"
    # A half-written last line must not swallow this one.
    ragged = path.is_file() and path.stat().st_size > 0 and path.read_bytes()[-1:] != b"\n"
    session_write.append(path, ("\n" if ragged else "") + json.dumps(record) + "\n")


def rebrief_target(run, args):
    """The run as the rebrief's --phase will leave it: a rebrief may add units the stored phase forbids, such as a new unit after an end-of-stack stop."""
    if not args.phase or run.get("phase") != "stopped" or not isinstance(run.get("stop_reason"), dict):
        return run
    target = copy.deepcopy(run)
    target["stop_reason"]["phase_before"] = args.phase
    return target


def apply_event(table, session_dir, event, args):
    m, t = transition(table, event)
    run_path = session_dir / "run.json"
    with session_write.locked(session_dir / ".session-state.lock"):
        # Refused here, before run.json is written, rather than after it.
        session_write.append(session_dir / "events.jsonl", b"")
        run = json.loads(run_path.read_text())
        events = read_events(session_dir)
        ctx = Ctx(table, session_dir, run, events, args)
        at = now_iso()
        before = session_state(table, run)
        record = {"n": len(events) + 1, "at": at, "event": event, "machine": m["id"], "actor": args.by if event == "resume" else t["actor"], "session_from": before}
        ctx.record = record
        try:
            illegal = state_problems(table, rebrief_target(run, args) if event == "rebrief" else run)
            if illegal:
                raise Refused("stored-state-legal", illegal[0])
            # A rebrief re-cuts the units by design; its own guard protects the done ones.
            tampered = log_problems(table, run, events, ignore_units=(event == "rebrief"))
            if tampered:
                raise Refused("log-intact", tampered[0])
            if m["id"] == "session":
                if before not in t["from"]:
                    raise Refused("from-state", f"'{event}' is not legal from {before}; legal now: {', '.join(legal_events(table, run)) or 'nothing'}")
                record["from"] = before
            else:
                ctx.unit = pick_unit(ctx, t)
                record["unit"] = ctx.unit.get("id")
                record["from"] = unit_status(ctx.unit)
                if record["from"] not in t["from"]:
                    raise Refused("from-state", f"'{event}' is not legal for {record['unit']}, which is {record['from']}")
            for name in t["guards"]:
                GUARDS[name](ctx)
            if event in ("gate-hold", "gate-advance"):
                record["review_mtime"] = review_path(ctx).stat().st_mtime
            EFFECTS[event](ctx, at)
            broken = state_problems(table, run)
            if broken:
                raise Refused("result-legal", broken[0])
        except Refused as refusal:
            record.update({"refused": True, "guard": refusal.guard, "why": refusal.why})
            append_event(session_dir, record)
            print(f"refused: {event}: {refusal.guard}: {refusal.why}", file=sys.stderr)
            glossary = table["guards"].get(refusal.guard)
            if glossary:
                print(f"  rule: {glossary}", file=sys.stderr)
            return EXIT_REFUSED

        run["updated_at"] = at
        after = session_state(table, run)
        record["session_to"] = after
        record["to"] = after if m["id"] == "session" else unit_status(ctx.unit)
        for key in ("code", "detail", "decision", "verdict", "why", "head", "next_unit", "reason", "base", "unit_heads"):
            if getattr(args, key, None):
                record[key] = getattr(args, key)
        record["digest"] = event_digest(run)
        record["units"] = unit_rows(run)
        session_write.write_json_atomic(run_path, run)
        append_event(session_dir, record)
    subject = f"{record.get('unit')}: " if record.get("unit") else ""
    print(f"{event}: {subject}{record['from']} -> {record['to']} (session: {after})")
    for note in ctx.notes:
        print(f"  {note}")
    return EXIT_OK


def adopt(table, session_dir, args):
    run = json.loads((session_dir / "run.json").read_text())
    illegal = state_problems(table, run)
    if illegal:
        print("refused: adopt: stored-state-legal: " + illegal[0], file=sys.stderr)
        return EXIT_REFUSED
    if not (args.by and (args.reason or "").strip()):
        print("refused: adopt: --by and --reason are required", file=sys.stderr)
        return EXIT_REFUSED
    state = session_state(table, run)
    with session_write.locked(session_dir / ".session-state.lock"):
        events = read_events(session_dir)
        append_event(session_dir, {"n": len(events) + 1, "at": now_iso(), "event": "adopt", "machine": "session", "actor": args.by, "session_from": state, "session_to": state, "why": args.reason, "digest": event_digest(run), "units": unit_rows(run)})
    print(f"adopt: baseline recorded at {state}")
    return EXIT_OK


# ---------------------------------------------------------------- queries


def status(table, session_dir):
    run = json.loads((session_dir / "run.json").read_text())
    events = read_events(session_dir)
    rows = units(run)
    current = (in_flight(run) or [u for u in rows if unit_status(u) != "done"] or [None])[0]
    found = problems(table, run, events)
    return {
        "state": session_state(table, run),
        "phase": run.get("phase") or "preflight",
        "stop_code": stop_code(run),
        "units_done": sum(1 for u in rows if unit_status(u) == "done"),
        "units_total": len(rows),
        "current_unit": current.get("id") if current else None,
        "current_unit_status": unit_status(current) if current else None,
        "gate_attempts": attempts(current) if current else 0,
        "stops_since_rebrief": stops_since_rebrief(events),
        "rebriefs": len(run.get("rebriefs") or []),
        "legal_events": [] if state_problems(table, run) else legal_events(table, run),
        "problems": found,
        "legal": not found,
        "events": len(applied(events)),
    }


def print_status(info):
    print(f"state: {info['state']}" + (f" ({info['stop_code']})" if info["stop_code"] else ""))
    if info["units_total"]:
        unit = f"; {info['current_unit']} is {info['current_unit_status']}, gate attempt {info['gate_attempts']}" if info["current_unit"] else ""
        print(f"units: {info['units_done']}/{info['units_total']} done{unit}")
    print(f"stops since rebrief: {info['stops_since_rebrief']}; rebriefs: {info['rebriefs']}; events: {info['events']}")
    print("legal events: " + (", ".join(info["legal_events"]) or "none"))
    for p in info["problems"]:
        print(f"INVALID: {p}")


def check_op(table, session_dir, op):
    ops = {k: v for k, v in table["operations"].items() if not k.startswith("_")}
    if op not in ops:
        print(f"unknown operation '{op}': one of {', '.join(ops)}", file=sys.stderr)
        return EXIT_ILLEGAL
    info = status(table, session_dir)
    if info["problems"]:
        print(f"refused: {op}: the stored state is invalid: {info['problems'][0]}", file=sys.stderr)
        return EXIT_REFUSED
    if info["state"] not in ops[op]:
        print(f"refused: {op}: the session is {info['state']}; {op} is legal from {', '.join(ops[op])}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"{op}: ok ({info['state']})")
    return EXIT_OK


# ---------------------------------------------------------------- doc


def _mid(state_id):
    return re.sub(r"[^a-z0-9]", "_", state_id.lower())


def _label(text):
    """A state-diagram label: a second colon or a semicolon ends the statement."""
    return text.replace(":", " -").replace(";", ",").replace('"', "'")


def _quoted(text):
    """A quoted flowchart label: only quotes and angle brackets (read as HTML) need care."""
    return text.replace('"', "'").replace("<", "#lt;").replace(">", "#gt;")


def doc_ids(table):
    """Every identifier the doc may print bare: a label that opens with one keeps its case."""
    ids = set(table["guards"]) | set(table["stop_codes"]) | set(table["operations"]) | set(table["illegal_states"])
    for m in table["machines"]:
        ids |= {s["id"] for s in m.get("states", [])} | {g["id"] for g in m.get("groups", [])}
        if m.get("enforced") is True:
            ids |= {t["event"] for t in m["transitions"]}
    return ids


def _sentence(text, ids):
    """Sentence case for prose; text that opens with an identifier or a code span is left alone.

    A label that opens with a role word carries its capital in the table.
    """
    first = text.split(" ", 1)[0].rstrip(",.:;")
    if first in ids or re.search(r"[_`=<.]", first):
        return text
    return text[:1].upper() + text[1:]


def _collapse(m, sources):
    """Replace a full group's states with the group id, so one arrow leaves the composite."""
    out = list(sources)
    for g in m.get("groups", []):
        if set(g["states"]) <= set(out):
            out = [s for s in out if s not in g["states"]] + [g["id"]]
    return out


def state_diagram(m, ids):
    lines = ["```mermaid", "stateDiagram-v2", "    direction LR"]
    grouped = {s: g for g in m.get("groups", []) for s in g["states"]}
    group_ids = {g["id"] for g in m.get("groups", [])}
    for s in m["states"]:
        if s["id"] not in grouped:
            lines.append(f'    state "{s["id"]}" as {_mid(s["id"])}')
    edges = []
    for t in m["transitions"]:
        target = t.get("to_group") if t["to"].startswith("@") else t["to"]
        for source in _collapse(m, t["from"]):
            edges.append((source, target, t["event"]))
    for g in m.get("groups", []):
        lines.append(f'    state "{_label(g["title"])}" as {_mid(g["id"])} {{')
        for sid in g["states"]:
            lines.append(f'        state "{sid}" as {_mid(sid)}')
        if m["initial"] in g["states"]:
            lines.append(f"        [*] --> {_mid(m['initial'])}")
        for source, target, event in edges:
            if grouped.get(source) is g and grouped.get(target) is g:
                lines.append(f"        {_mid(source)} --> {_mid(target)}" + (f" : {_label(_sentence(event, ids))}" if event else ""))
        lines.append("    }")
    if m["initial"] not in grouped:
        lines.append(f"    [*] --> {_mid(m['initial'])}")
    for source, target, event in edges:
        inside = source not in group_ids and target not in group_ids and grouped.get(source) is not None and grouped.get(source) is grouped.get(target)
        if inside is False:
            lines.append(f"    {_mid(source)} --> {_mid(target)}" + (f" : {_label(_sentence(event, ids))}" if event else ""))
    for sid in m.get("terminal", []):
        lines.append(f"    {_mid(sid)} --> [*]")
    lines.append("```")
    return lines


def flowchart(m, ids):
    lines = ["```mermaid", "flowchart TD"]
    grouped = {s for g in m.get("groups", []) for s in g["states"]}
    for s in m["states"]:
        if s["id"] not in grouped:
            shape = f'(["{s["id"]}"])' if s["id"] in m.get("terminal", []) or s["id"] == m["initial"] else f'["{s["id"]}"]'
            lines.append(f"    {_mid(s['id'])}{shape}")
    for g in m.get("groups", []):
        lines.append(f'    subgraph {_mid(g["id"])}["{_quoted(g["title"])}"]')
        for sid in g["states"]:
            lines.append(f'        {_mid(sid)}["{sid}"]')
        lines.append("    end")
    for t in m["transitions"]:
        for source in t["from"]:
            arrow = f' -->|"{_quoted(_sentence(t["event"], ids))}"| ' if t["event"] else " --> "
            lines.append(f"    {_mid(source)}{arrow}{_mid(t['to'])}")
    lines.append("```")
    return lines


def classifier_diagram(m, ids):
    lines = ["```mermaid", "flowchart TD"]
    for i, rule in enumerate(m["rules"]):
        last = i == len(m["rules"]) - 1
        if last:
            lines.append(f'    v{i}(["{_quoted(rule["then"])}"])')
            lines.append(f"    q{i - 1} -->|No| v{i}")
            break
        lines.append(f'    q{i}{{"{_quoted(_sentence(rule["if"], ids))}?"}}')
        lines.append(f'    v{i}(["{_quoted(rule["then"])}"])')
        lines.append(f"    q{i} -->|Yes| v{i}")
        if i > 0:
            lines.append(f"    q{i - 1} -->|No| q{i}")
    lines.append("```")
    return lines


def _md(text):
    """Angle brackets outside a code span would be read as HTML and vanish."""
    parts = str(text).split("`")
    return "`".join(p if i % 2 else p.replace("<", "&lt;").replace(">", "&gt;") for i, p in enumerate(parts))


def _cell(text):
    return _md(text).replace("|", "\\|").replace("\n", " ")


def machine_section(table, m):
    ids = doc_ids(table)

    def prose(text):
        return _cell(_sentence(text, ids))

    # Anchors come from machine ids, not titles, so rewording a title breaks no link to it.
    out = [f'<a name="m-{m["id"]}"></a>', "", f"## {m['title']}", "", _md(m["summary"]), ""]
    out.append(f"- **Stored in:** {_md(_sentence(m['stored_in'], ids))}")
    enforced = "`session-state.py` refuses anything not in this table" if m.get("enforced") is True else "Documented, not enforced: it lives in files and handbooks the tool does not write"
    enforced = _sentence(m.get("enforcement", enforced), ids)
    out += [f"- **Enforcement:** {enforced}", ""]
    if m["kind"] == "classifier":
        out += classifier_diagram(m, ids) + ["", "First match wins.", "", "| # | If | Verdict |", "|---|---|---|"]
        out += [f"| {i + 1} | {prose(r['if'])} | {_cell('`' + r['then'] + '`')} |" for i, r in enumerate(m["rules"])]
        out += ["", "Flags ride on a verdict and never replace it:", "", "| Flag | When |", "|---|---|"]
        out += [f"| {_cell('`' + f['id'] + '`')} | {prose(f['when'])} |" for f in m["flags"]]
        return out + [""]
    out += (flowchart(m, ids) if m.get("diagram") == "flowchart" else state_diagram(m, ids)) + [""]
    has_encoding = any("encoding" in s for s in m["states"])
    has_stop_gate = any("stop_gate" in s for s in m["states"])
    columns = ["State"] + (["Stored as"] if has_encoding else []) + (["Stop gate"] if has_stop_gate else []) + ["Meaning"]
    out += ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for s in m["states"]:
        marks = " (initial)" if s["id"] == m["initial"] else " (terminal)" if s["id"] in m.get("terminal", []) else ""
        row = [f"`{s['id']}`{marks}"]
        row += [_cell('`' + s.get('encoding', '') + '`')] if has_encoding else []
        row += [s.get("stop_gate", "")] if has_stop_gate else []
        row += [prose(s["meaning"])]
        out.append("| " + " | ".join(row) + " |")
    out.append("")
    if m.get("enforced") is True:
        out += ["| Event | From | To | Who | Guards | Effect | Handbook |", "|---|---|---|---|---|---|---|"]
        for t in m["transitions"]:
            guards = ", ".join(f"`{g}`" for g in t["guards"]) or "none"
            target = f"{t['to_group']}: {t['to'][1:].replace('-', ' ')}" if t["to"].startswith("@") else t["to"]
            out.append(f"| `{t['event']}` | {', '.join(t['from'])} | {_cell(target)} | {t['actor']} | {guards} | {prose(t['effect'])} | {_cell(t['source'])} |")
    else:
        out += ["| From | On | To |", "|---|---|---|"]
        for t in m["transitions"]:
            out.append(f"| {', '.join(t['from'])} | {prose(t['event']) or 'Always'} | {t['to']} |")
    return out + [""]


def render_doc(table):
    doc = table["doc"]
    out = [f"# {doc['title']}", "", "<!-- Generated by scripts/session-state.py doc --write from state-machine.json. Edit the table, not this file. -->", ""]
    for para in doc["intro"]:
        out += [para, ""]
    out += ["## Contents", ""]
    ordered = [m for m in table["machines"] if m["id"] == "system"] + [m for m in table["machines"] if m["id"] != "system"]
    for m in ordered:
        out.append(f"- [{m['title']}](#m-{m['id']})" + (" (enforced)" if m.get("enforced") is True else ""))
    out += ["- [Guards](#guards)", "- [Illegal stored states](#illegal-stored-states)", "- [Stop codes](#stop-codes)", "- [Launcher operations](#launcher-operations)", "- [Using the tool](#using-the-tool)", ""]
    for m in ordered:
        out += machine_section(table, m)
    out += ["## Guards", "", "A guard is a fact the tool checks on disk before it applies an event. A failed guard refuses the event, changes nothing, and is logged.", "", "| Guard | Holds when |", "|---|---|"]
    ids = doc_ids(table)
    out += [f"| `{name}` | {_cell(_sentence(text, ids))} |" for name, text in table["guards"].items()]
    out += ["", table["universal_guards"]["_doc"], "", "| On every event | Holds when |", "|---|---|"]
    out += [f"| `{name}` | {_cell(_sentence(text, ids))} |" for name, text in table["universal_guards"].items() if not name.startswith("_")]
    out += ["", "## Illegal stored states", "", table["illegal_states"]["_doc"], "", "| Name | Holds when |", "|---|---|"]
    out += [f"| `{name}` | {_cell(_sentence(text, ids))} |" for name, text in table["illegal_states"].items() if not name.startswith("_")]
    out += ["", "## Stop codes", "", "| Code | Meaning |", "|---|---|"]
    out += [f"| `{code}` | {_cell(_sentence(text, ids))} |" for code, text in table["stop_codes"].items()]
    rules = table["delegation"]
    out += ["", f"The Lead may decide a stop only at {' or '.join('`delegation: ' + x + '`' for x in rules['lead_may_decide_at'])}, never for {', '.join('`' + x + '`' for x in rules['owner_only_codes'])}, and not on stop {rules['rebrief_after_stops']} since the last rebrief.", ""]
    out += ["## Launcher operations", "", table["operations"]["_doc"], "", "| Operation | Legal from |", "|---|---|"]
    out += [f"| `{op}` | {', '.join(states)} |" for op, states in table["operations"].items() if not op.startswith("_")]
    out += ["", "## Using the tool", ""]
    for para in doc["usage"]:
        out += [para, ""]
    return "\n".join(out).rstrip("\n") + "\n"


def doc_command(table, mode):
    text = render_doc(table)
    if mode == "write":
        DOC_PATH.write_text(text)
        print(f"wrote {DOC_PATH}")
        return EXIT_OK
    if mode == "check":
        if DOC_PATH.is_file() and DOC_PATH.read_text() == text:
            print("STATES.md matches the table")
            return EXIT_OK
        print("STATES.md is stale: run `session-state.py doc --write`", file=sys.stderr)
        return EXIT_ILLEGAL
    sys.stdout.write(text)
    return EXIT_OK


def table_problems(table):
    """The table names a guard or an event the code does not implement, or the reverse."""
    out = []
    events = enforced_events(table)
    for m in table["machines"]:
        ids = {s["id"] for s in m.get("states", [])} | {g["id"] for g in m.get("groups", [])}
        for t in m.get("transitions", []):
            for sid in t["from"] + ([t["to"]] if not t["to"].startswith("@") else [t["to_group"]]):
                if sid not in ids:
                    out.append(f"{m['id']}: unknown state '{sid}'")
            for g in t.get("guards", []):
                if g not in GUARDS:
                    out.append(f"{m['id']}: guard '{g}' has no implementation")
                if g not in table["guards"]:
                    out.append(f"{m['id']}: guard '{g}' is not in the glossary")
    named = set(re.findall(r'out\.append\(f?"([a-z-]+)', inspect.getsource(state_problems)))
    listed = {k for k in table["illegal_states"] if not k.startswith("_")}
    out += [f"illegal state '{n}' is checked and not in the glossary" for n in sorted(named - listed)]
    out += [f"illegal state '{n}' is in the glossary and never checked" for n in sorted(listed - named)]
    out += [f"event '{e}' has no effect" for e in events if e not in EFFECTS]
    out += [f"effect '{e}' is not in the table" for e in EFFECTS if e not in events]
    out += [f"guard '{g}' is implemented and unused" for g in GUARDS if not any(g in t.get("guards", []) for m in table["machines"] for t in m.get("transitions", []))]
    return out


# ---------------------------------------------------------------- main


def main(argv):
    table = load_table()
    broken = table_problems(table)
    if broken:
        print("state-machine.json and session-state.py disagree:\n  " + "\n  ".join(broken), file=sys.stderr)
        return EXIT_ILLEGAL

    if argv[:1] == ["doc"]:
        ap = argparse.ArgumentParser(prog="session-state.py doc")
        ap.add_argument("--write", action="store_const", const="write", dest="mode")
        ap.add_argument("--check", action="store_const", const="check", dest="mode")
        return doc_command(table, ap.parse_args(argv[1:]).mode)

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session_dir")
    ap.add_argument("command", choices=enforced_events(table) + ["status", "check", "check-op", "adopt"])
    ap.add_argument("operation", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--unit")
    ap.add_argument("--review")
    ap.add_argument("--head")
    ap.add_argument("--next-unit", dest="next_unit")
    ap.add_argument("--code")
    ap.add_argument("--detail")
    ap.add_argument("--by", choices=table["delegation"]["levels"][:2])
    ap.add_argument("--decision")
    ap.add_argument("--wall-hours", dest="wall_hours", type=float)
    ap.add_argument("--phase")
    ap.add_argument("--verdict", choices=["confident", "owner", "ship", "polish", "rebrief"])
    ap.add_argument("--base")
    ap.add_argument("--unit-heads", dest="unit_heads")
    ap.add_argument("--why")
    ap.add_argument("--reason")
    args = ap.parse_args(argv)

    session_dir = Path(args.session_dir).expanduser()
    if not (session_dir / "run.json").is_file():
        print(f"{session_dir / 'run.json'} does not exist", file=sys.stderr)
        return EXIT_ILLEGAL

    if args.command == "status":
        info = status(table, session_dir)
        print(json.dumps(info, indent=2)) if args.json else print_status(info)
        return EXIT_OK
    if args.command == "check":
        info = status(table, session_dir)
        print_status(info)
        return EXIT_OK if info["legal"] else EXIT_ILLEGAL
    if args.command == "check-op":
        return check_op(table, session_dir, args.operation or "")
    try:
        if args.command == "adopt":
            return adopt(table, session_dir, args)
        return apply_event(table, session_dir, args.command, args)
    except session_write.Refused as refusal:
        print(f"refused: {args.command}: session-file: {refusal}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
