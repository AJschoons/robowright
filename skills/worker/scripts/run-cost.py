#!/usr/bin/env python3
"""
run-cost.py — measure what a Robowright Session cost, from its transcripts, and record it.

Reads the Robowright Session's Claude Code transcripts — run.json's pins and any desktop
scheduled-task run whose first record carries `ROBOWRIGHT_RUN_DIR=<session dir>`, else everything
under the worktree's project dir, each with its subagent sidecars — and
prints one block: requests, tokens by class, average context per request, output by model,
an estimated USD figure, lines written by the Write/Edit tools, and lines shipped in the
diff. `--write` stores the block as `cost` in <session_dir>/run.json so successive Robowright
Sessions are comparable without anyone reading a usage panel.

    run-cost.py --run-dir <sessions root>/<slug>
    run-cost.py --run-dir … --write            # also store run.json.cost
    run-cost.py --run-dir … --json
    run-cost.py --run-dir … --transcript <path>  # add a transcript the slug walk misses
    run-cost.py --run-dir … --whole-worktree     # ignore the run.json pin; count the whole project dir
    run-cost.py --run-dir … --ledger --session-id <id> --transcript <path>   # a Worker session's end
    run-cost.py --run-dir … --ledger --unit <id>                            # a Worker's unit-close
    run-cost.py --ledger --role planner|lead|explainer --session-id <id> --transcript <path> --cwd <dir>

--run-dir is always explicit, except for a doc role, which has none: this script reads no sessions
root, so it has no default for one.

Token counts, request counts and context sizes are facts read from the transcript, and they
are the figures a ledger entry quotes. The USD figure is an ESTIMATE from the pricing file
(robowright/pricing.json, read by robowright/scripts/pricing.py) — null throughout when the file
is missing — it is meaningful only where the machine profile's Budget is measured in dollars, and
it can under-shoot a usage panel by a wide margin — so
`actual_usd` is left null for the Owner to fill in from the panel where a panel applies. Lines
written counts newlines in every Write `content` and Edit `new_string`; lines shipped is
`git diff --shortstat <base_sha>..<tip>` in the worktree, <tip> being `publish.tip`, else HEAD.
"""

import argparse
import functools
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

PROJECTS_ROOT = os.path.expanduser("~/.claude/projects")

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "robowright", "scripts"))
import owner_git  # noqa: E402
import session_write  # noqa: E402


@functools.lru_cache(maxsize=None)
def prices():
    """The pricing file, loaded once a run so a missing file says so in one stderr line."""
    spec = importlib.util.spec_from_file_location("pricing", os.path.join(HERE, "..", "..", "robowright", "scripts", "pricing.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load()


def usd_or_none(value, digits):
    return round(value, digits) if prices().as_of else None


def money(value, spec=",.2f"):
    return "n/a" if value is None else f"${value:{spec}}"


def project_slug(path):
    # Claude Code names a project dir after the cwd with every non-alphanumeric turned into "-".
    return re.sub(r"[^A-Za-z0-9]", "-", path)


# A run's first user record sits in the first ~2 KB of its transcript; the bound keeps a scan of
# every project dir to a few MB.
SENTINEL_SCAN_BYTES = 65536


def scheduled_run_transcripts(run_dir):
    """Transcripts of desktop scheduled-task runs launched for this Robowright Session. The Lead ends the
    task prompt with a `ROBOWRIGHT_RUN_DIR=<session dir>` line, the run's first user record wraps the
    prompt in `<scheduled-task …>`, and the run lives in the project dir of the Lead's folder, not
    the worktree's. A Lead transcript that merely quotes the line is not a scheduled-task run."""
    wanted = os.path.realpath(os.path.expanduser(run_dir))
    return sorted(p for p, run_dirs in scheduled_run_index().items() if wanted in run_dirs)


@functools.lru_cache(maxsize=None)
def scheduled_run_index():
    index = {}
    for path in glob.glob(os.path.join(PROJECTS_ROOT, "*", "*.jsonl")):
        try:
            with open(path, "rb") as f:
                head = f.read(SENTINEL_SCAN_BYTES)
        except OSError:
            continue
        if b"<scheduled-task " not in head or b"ROBOWRIGHT_RUN_DIR=" not in head:
            continue
        run_dirs = sentinel_run_dirs(head)
        if run_dirs:
            index[path] = run_dirs
    return index


def sentinel_run_dirs(head):
    """The ROBOWRIGHT_RUN_DIR values in the first user record, when that record is a scheduled-task run."""
    for line in head.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("type") != "user":
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.startswith("<scheduled-task "):
            return set()
        return {os.path.realpath(l[len("ROBOWRIGHT_RUN_DIR="):].strip())
                for l in content.splitlines() if l.startswith("ROBOWRIGHT_RUN_DIR=")}
    return set()


def transcript_paths(run, run_dir, extra, whole_worktree=False):
    """run.json `transcripts` pins the Robowright Session's own sessions (the launcher appends the
    transcript of every session it starts for the Robowright Session), and a desktop scheduled-task run
    is found by its ROBOWRIGHT_RUN_DIR line; each brings its subagent sidecar dir. With neither, or
    with --whole-worktree, fall back to every transcript under the worktree's project dir — which
    also counts any other session that ever used that worktree, and overstates the figure."""
    paths = set(os.path.expanduser(p) for p in extra or [])
    pinned = (run.get("transcripts") or []) + scheduled_run_transcripts(run_dir)
    if not whole_worktree and pinned:
        paths.update(os.path.expanduser(p) for p in pinned)
    for p in list(paths):
        side = p[:-len(".jsonl")] if p.endswith(".jsonl") else p
        paths.update(glob.glob(os.path.join(side, "**", "*.jsonl"), recursive=True))
    worktree = run.get("worktree")
    if worktree and (whole_worktree or not pinned):
        paths.update(glob.glob(os.path.join(PROJECTS_ROOT, project_slug(worktree), "**", "*.jsonl"), recursive=True))
    return sorted(p for p in paths if os.path.isfile(p))


def unit_transcript_paths(run, run_dir, extra):
    """A unit's window bounds what it counts, so it reads the pins and the worktree project dir both: a session
    nobody pinned (a pasted hand-off) still spent inside the window."""
    return sorted(set(transcript_paths(run, run_dir, extra)) | set(transcript_paths(run, run_dir, extra, whole_worktree=True)))


def lines_in(text):
    if not isinstance(text, str) or not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def role_of(path, run):
    """main session (the Worker) vs a subagent sidecar (Reviewers, Readers, ad-hoc agents).
    Sidecars live one directory below the session's .jsonl, so any transcript whose parent dir is
    not a project dir is a subagent."""
    parent = os.path.basename(os.path.dirname(path))
    return "subagents" if parent and not parent.startswith("-") else "worker"


def measure(paths, run=None):
    seen = set()
    totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0,
              "cache_read_tokens": 0, "cache_write_tokens": 0}
    by_model = {}
    by_role = {"worker": {"requests": 0, "estimated_usd": 0.0, "context_tokens": 0},
               "subagents": {"requests": 0, "estimated_usd": 0.0, "context_tokens": 0, "transcripts": 0}}
    usd = 0.0
    lines_written = 0
    writes = 0
    first_ts = last_ts = None
    for path in paths:
        role = role_of(path, run or {})
        if role == "subagents":
            by_role["subagents"]["transcripts"] += 1
        try:
            f = open(path, errors="replace")
        except OSError:
            continue
        with f:
            for line in f:
                if '"usage"' not in line and '"tool_use"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message") or {}
                ts = rec.get("timestamp")
                if ts:
                    first_ts = ts if first_ts is None or ts < first_ts else first_ts
                    last_ts = ts if last_ts is None or ts > last_ts else last_ts
                # Tool payloads: count every Write/Edit line, once per tool_use id.
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        tid = block.get("id")
                        key = ("tool", tid)
                        if tid and key in seen:
                            continue
                        seen.add(key)
                        name = block.get("name")
                        inp = block.get("input") or {}
                        if name == "Write":
                            lines_written += lines_in(inp.get("content"))
                            writes += 1
                        elif name == "Edit":
                            lines_written += lines_in(inp.get("new_string"))
                            writes += 1
                        elif name == "MultiEdit":
                            for e in inp.get("edits") or []:
                                lines_written += lines_in((e or {}).get("new_string"))
                            writes += 1
                usage = msg.get("usage")
                if not usage:
                    continue
                # Claude Code's placeholder for a turn that never reached the API; not a request.
                if msg.get("model") == "<synthetic>":
                    continue
                mid = msg.get("id") or rec.get("uuid")
                if ("msg", mid) in seen:
                    continue
                seen.add(("msg", mid))
                model = msg.get("model", "unknown")
                cw = usage.get("cache_creation_input_tokens", 0)
                totals["requests"] += 1
                totals["input_tokens"] += usage.get("input_tokens", 0)
                totals["output_tokens"] += usage.get("output_tokens", 0)
                totals["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
                totals["cache_write_tokens"] += cw
                m = by_model.setdefault(model, {"requests": 0, "output_tokens": 0, "estimated_usd": 0.0})
                m["requests"] += 1
                m["output_tokens"] += usage.get("output_tokens", 0)
                # 0.0 without prices; usd_or_none reports the whole figure as null.
                c = prices().usage_cost(model, usage) or 0.0
                m["estimated_usd"] += c
                usd += c
                r = by_role[role]
                r["requests"] += 1
                r["estimated_usd"] += c
                r["context_tokens"] += usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0) + cw
    for m in by_model.values():
        m["estimated_usd"] = usd_or_none(m["estimated_usd"], 2)
    for r in by_role.values():
        r["avg_context_tokens"] = int(r["context_tokens"] / r["requests"]) if r["requests"] else 0
        del r["context_tokens"]
        r["estimated_usd"] = usd_or_none(r["estimated_usd"], 2)
    ctx = totals["input_tokens"] + totals["cache_read_tokens"] + totals["cache_write_tokens"]
    avg_ctx = int(ctx / totals["requests"]) if totals["requests"] else 0
    usd_per_request = usd_or_none(usd / totals["requests"], 4) if totals["requests"] else None
    hours = None
    if first_ts and last_ts:
        try:
            a = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            b = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            hours = round((b - a).total_seconds() / 3600, 1)
        except ValueError:
            hours = None
    return {
        **totals,
        "avg_context_tokens": avg_ctx,
        "usd_per_request": usd_per_request,
        "by_model": by_model,
        "by_role": by_role,
        "estimated_usd": usd_or_none(usd, 2),
        "actual_usd": None,
        "price_table": f"{prices().as_of_line()}; unknown models priced at the default row",
        "lines_written": lines_written,
        "write_tool_calls": writes,
        "transcripts": len(paths),
        "wall_hours_transcript": hours,
    }


COMMIT_ID = re.compile(r"[0-9a-f]{7,40}")


def lines_shipped(run):
    worktree = run.get("worktree")
    base = run.get("base_sha")
    if not worktree or not base or not os.path.isdir(worktree):
        return None
    # A unit head goes stale after a sanctioned amend or fold; the published tip does not.
    publish = run.get("publish")
    tip = (publish.get("tip") if isinstance(publish, dict) else None) or "HEAD"
    # Both are session-written and reach git's argv outside the sandbox.
    if not (isinstance(base, str) and COMMIT_ID.fullmatch(base)):
        print(f"run-cost: shipped range not measured: base_sha is not a commit id ({base!r})", file=sys.stderr)
        return None
    if not (isinstance(tip, str) and (tip == "HEAD" or COMMIT_ID.fullmatch(tip))):
        print(f"run-cost: shipped range not measured: publish.tip is not a commit id or HEAD ({tip!r})", file=sys.stderr)
        return None
    try:
        worktree = owner_git.check(worktree)[0]
    except owner_git.Unlisted as refusal:
        print(f"run-cost: shipped range not measured: refused: {refusal.code}: {refusal.detail}", file=sys.stderr)
        return None
    try:
        diff = owner_git.run(worktree, "diff", "--shortstat", "--no-ext-diff", "--no-textconv", "--end-of-options",
                             f"{base}..{tip}", timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"run-cost: shipped range {base}..{tip} not measured: {error}", file=sys.stderr)
        return None
    if diff.returncode != 0:
        print(f"run-cost: shipped range {base}..{tip} not measured: {diff.stderr.strip()}", file=sys.stderr)
        return None
    added = removed = 0
    for part in diff.stdout.split(","):
        part = part.strip()
        if part.endswith("(+)"):
            added = int(part.split()[0])
        elif part.endswith("(-)"):
            removed = int(part.split()[0])
    return {"added": added, "removed": removed, "range": f"{base[:10]}..{tip[:10] if tip != 'HEAD' else 'HEAD'}"}


def store_cost(run_json, cost):
    """session-state.py is run.json's other writer: take its lock, and write onto the file as it
    is then — the scan above can outlast an event."""
    with session_write.locked(os.path.join(os.path.dirname(run_json), ".session-state.lock")):
        with open(run_json) as f:
            run = json.load(f)
        run["cost"] = cost
        session_write.write_json_atomic(run_json, run)


# ---------------------------------------------------------------------------------------------
# The accounting ledger: <accounting root>/records.jsonl, one record per (Claude session, role,
# model), appended at SessionEnd. The rollup is robowright-cost.py.
# ---------------------------------------------------------------------------------------------
LAUNCH_JSON = os.path.expanduser("~/.claude/robowright/launch.json")
LEDGER_FILE = "records.jsonl"
LEDGER_LOCK = ".records.lock"


def home_path(value):
    """A launch.json path as the launcher reads it: a leading `~/` is $HOME, anything else as written."""
    return os.path.expanduser("~") + value[1:] if value.startswith("~/") else value


def accounting_root(flag):
    """--accounting-root, else $ROBOWRIGHT_ACCOUNTING_ROOT, else launch.json's accounting_root, else
    `accounting` beside the sessions root ($ROBOWRIGHT_SESSIONS_ROOT, else launch.json's); None when
    nothing names one."""
    if flag:
        return os.path.expanduser(flag)
    if os.environ.get("ROBOWRIGHT_ACCOUNTING_ROOT"):
        return os.path.expanduser(os.environ["ROBOWRIGHT_ACCOUNTING_ROOT"])
    try:
        with open(LAUNCH_JSON) as f:
            settings = json.load(f)
    except (OSError, ValueError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    named = settings.get("accounting_root")
    if isinstance(named, str) and named:
        return home_path(named)
    sessions = os.environ.get("ROBOWRIGHT_SESSIONS_ROOT") or settings.get("sessions_root")
    if isinstance(sessions, str) and sessions:
        return os.path.join(os.path.dirname(os.path.realpath(home_path(os.path.expanduser(sessions)))), "accounting")
    return None


def session_transcripts(transcript):
    """The ending Claude session's own transcript and its sidecar dir — never the other sessions the session dir pinned."""
    side = transcript[:-len(".jsonl")] if transcript.endswith(".jsonl") else transcript
    return sorted([transcript] + glob.glob(os.path.join(side, "**", "*.jsonl"), recursive=True))


# D7: a sidecar's bucket is the agentType in its .meta.json; any other type, or no readable meta file, is `subagent`.
AGENT_TYPE_ROLES = {
    "reviewer-gate": "reviewer-code", "reviewer-adversarial": "reviewer-code", "reviewer-map": "reviewer-code",
    "reviewer-docs": "reviewer-prose", "reviewer-intake": "reviewer-prose",
    "reader-roster": "reader", "log-reader": "reader", "ui-tree-reader": "reader",
    "worker-spec": "spec",
}
DOC_ROLES = ("planner", "lead", "explainer")
LAUNCH_INDEX_FILE = "launches.jsonl"


def sidecar_role(path):
    """Only agentType is read: the meta file's model key is an alias when present, and the record's model is the usage record's id."""
    try:
        with open(path[:-len(".jsonl")] + ".meta.json") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return "subagent"
    return AGENT_TYPE_ROLES.get(meta.get("agentType") if isinstance(meta, dict) else None, "subagent")


def record_role(path, main_role):
    return sidecar_role(path) if role_of(path, {}) == "subagents" else main_role


def owning_session(path):
    """The Claude session a transcript belongs to: a main transcript's name, or the session dir a sidecar sits under."""
    parts = os.path.normpath(path).split(os.sep)
    for i in range(len(parts) - 1, 0, -1):
        if parts[i - 1].startswith("-"):
            return parts[i][:-len(".jsonl")] if parts[i].endswith(".jsonl") else parts[i]
    return os.path.basename(path)[:-len(".jsonl")]


def parse_time(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def timed_records(paths, main_role):
    """(role, path, at, request) for every timestamped record; request is (model, usage) once per request by
    measure()'s rules (one per message id, `<synthetic>` is not a request), else None."""
    seen = set()
    for path in paths:
        role = record_role(path, main_role)
        try:
            f = open(path, errors="replace")
        except OSError:
            continue
        with f:
            for line in f:
                if '"timestamp"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                at = parse_time(rec.get("timestamp"))
                msg = rec.get("message") or {}
                usage = msg.get("usage")
                mid = msg.get("id") or rec.get("uuid")
                if not usage or msg.get("model") == "<synthetic>" or mid in seen:
                    yield role, path, at, None
                    continue
                seen.add(mid)
                yield role, path, at, (msg.get("model", "unknown"), usage)


def add_request(buckets, key, request):
    model, usage = request
    b = buckets.setdefault(key, {"requests": 0, "input_tokens": 0, "output_tokens": 0,
                                 "cache_read_tokens": 0, "cache_write_tokens": 0, "usd": 0.0})
    b["requests"] += 1
    b["input_tokens"] += usage.get("input_tokens", 0)
    b["output_tokens"] += usage.get("output_tokens", 0)
    b["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
    b["cache_write_tokens"] += usage.get("cache_creation_input_tokens", 0)
    b["usd"] += prices().usage_cost(model, usage) or 0.0


def measure_buckets(paths, main_role):
    """Per (role, model): request and token counts; and the first and last timestamp across every path."""
    buckets = {}
    first = last = None
    for role, _, at, request in timed_records(paths, main_role):
        if at:
            first = at if first is None or at < first else first
            last = at if last is None or at > last else last
        if request:
            add_request(buckets, (role, request[0]), request)
    return buckets, first, last


def unit_buckets(paths, windows):
    """Per unit id, per (session, role, model): the requests whose timestamp falls inside that unit's window."""
    per_unit = {unit_id: {} for unit_id in windows}
    for role, path, at, request in timed_records(paths, "worker"):
        if request is None or at is None:
            continue
        for unit_id, (start, close) in windows.items():
            if start <= at <= close:
                add_request(per_unit[unit_id], (owning_session(path), role, request[0]), request)
    return per_unit


def read_events(run_dir):
    try:
        with open(os.path.join(run_dir, "events.jsonl")) as f:
            lines = f.readlines()
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and parse_time(event.get("at")) is not None:
            events.append(event)
    return events


def unit_windows(run_dir):
    """{unit id: (start, close)} for every closed unit: its unit-start to the first unit-close after it.
    events.jsonl can close a unit twice; the second close is not a second window."""
    starts, windows = {}, {}
    for event in read_events(run_dir):
        unit_id, at = event.get("unit"), parse_time(event["at"])
        if not unit_id or unit_id in windows:
            continue
        if event.get("event") == "unit-start":
            starts.setdefault(unit_id, at)
        elif event.get("event") == "unit-close" and unit_id in starts and at >= starts[unit_id]:
            windows[unit_id] = (starts[unit_id], at)
    return windows


def paused_seconds(run_dir, start, end):
    """Seconds inside [start, end] that the session spent between a `stop` event and the `resume` after it."""
    paused = 0.0
    stopped_at = None
    for event in read_events(run_dir):
        at = parse_time(event["at"])
        if event.get("event") == "stop":
            stopped_at = at
        elif event.get("event") == "resume" and stopped_at is not None:
            paused += max(0.0, (min(end, at) - max(start, stopped_at)).total_seconds())
            stopped_at = None
    return paused


def plan_usage():
    """The newest plan-usage reading the status-line tap left: (5-hour %, 7-day %, captured_at), None where absent."""
    usage_dir = os.environ.get("CLAUDE_USAGE_DIR") or os.path.expanduser("~/.claude/usage")
    try:
        with open(os.path.join(usage_dir, "latest.json")) as f:
            latest = json.load(f)
    except (OSError, ValueError):
        return None, None, None
    if not isinstance(latest, dict):
        return None, None, None
    return window_pct(latest, "five_hour"), window_pct(latest, "seven_day"), latest.get("captured_at")


def plan_reading(source):
    """A migrated record is written long after its session ended; today's reading is not that session's."""
    return (None, None, None) if source == "migrate" else plan_usage()


def window_pct(latest, window):
    reading = latest.get(window)
    return reading.get("used_percentage") if isinstance(reading, dict) else None


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ledger_record(identity, b, wall, active, plan):
    """identity: the §6 fields from scope to transcripts_pinned, in order; the facts follow."""
    plan_5h, plan_7d, captured = plan
    context = b["input_tokens"] + b["cache_read_tokens"] + b["cache_write_tokens"]
    return dict(identity, **{
        "requests": b["requests"], "input_tokens": b["input_tokens"], "output_tokens": b["output_tokens"],
        "cache_read_tokens": b["cache_read_tokens"], "cache_write_tokens": b["cache_write_tokens"],
        "avg_context_tokens": int(context / b["requests"]),
        "estimated_usd": usd_or_none(b["usd"], 4), "price_as_of": prices().as_of,
        "wall_seconds": int(wall), "active_seconds": int(active),
        "plan_5h_pct": plan_5h, "plan_7d_pct": plan_7d, "plan_captured_at": captured,
    })


def session_records(run, run_dir, session_id, transcript, source):
    buckets, first, last = measure_buckets(session_transcripts(transcript), "worker")
    wall = (last - first).total_seconds() if first and last else 0
    active = wall - paused_seconds(run_dir, first, last) if first and last else 0
    plan = plan_reading(source)
    pinned = any(os.path.realpath(os.path.expanduser(p)) == os.path.realpath(transcript)
                 for p in run.get("transcripts") or [])
    at = now_iso()
    return [ledger_record({
        "scope": "session", "at": at, "source": source,
        "project": run.get("project"), "unit": run.get("ticket"), "unit_id": None,
        "role": role, "model": model, "session_id": session_id,
        "session_dir": os.path.abspath(run_dir), "transcripts_pinned": pinned,
    }, b, wall, active, plan) for (role, model), b in sorted(buckets.items())]


def unit_records(run, run_dir, paths, windows, source):
    """{unit id: records}: one unit-scope record per (session, role, model) with a request inside the unit's window."""
    plan = plan_reading(source)
    at = now_iso()
    out = {}
    for unit_id, buckets in unit_buckets(paths, windows).items():
        start, close = windows[unit_id]
        wall = (close - start).total_seconds()
        active = wall - paused_seconds(run_dir, start, close)
        out[unit_id] = [ledger_record({
            "scope": "unit", "at": at, "source": source,
            "project": run.get("project"), "unit": run.get("ticket"), "unit_id": unit_id,
            "role": role, "model": model, "session_id": session_id,
            "session_dir": os.path.abspath(run_dir), "transcripts_pinned": bool(run.get("transcripts")),
        }, b, wall, active, plan) for (session_id, role, model), b in sorted(buckets.items())]
    return out


def launch_index_line(root, session_id):
    """The launcher's last launches.jsonl line for this session, or {}."""
    try:
        with open(os.path.join(root, LAUNCH_INDEX_FILE)) as f:
            lines = f.readlines()
    except OSError:
        return {}
    found = {}
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("session_id") == session_id:
            found = entry
    return found


def doc_role_records(root, role, session_id, transcript, cwd):
    """A Planner, Lead or Explainer session: its main transcript under its role, its sidecars by agent type.
    The role is always the hook's; the launch index only says which project, unit and session dir."""
    indexed = launch_index_line(root, session_id)
    buckets, first, last = measure_buckets(session_transcripts(transcript), role)
    wall = (last - first).total_seconds() if first and last else 0
    plan = plan_usage()
    at = now_iso()
    return [ledger_record({
        "scope": "session", "at": at, "source": "hook",
        "project": indexed.get("project") or os.path.basename(os.path.normpath(cwd)),
        "unit": indexed.get("unit"), "unit_id": None,
        "role": bucket_role, "model": model, "session_id": session_id,
        "session_dir": indexed.get("session_dir"), "transcripts_pinned": False,
    }, b, wall, wall, plan) for (bucket_role, model), b in sorted(buckets.items())]


def ledger_key(record):
    """What makes a group of records already present: a session's session-scope records, or one unit of one session dir."""
    if record.get("scope") == "unit":
        return ("unit", record.get("session_dir"), record.get("unit_id"))
    return ("session", record.get("session_id"))


def ledger_lines(body):
    for line in body.splitlines():
        try:
            old = json.loads(line)
        except ValueError:
            continue
        if isinstance(old, dict):
            yield old


def recorded_keys(root):
    try:
        with open(os.path.join(root, LEDGER_FILE), "rb") as f:
            return {ledger_key(old) for old in ledger_lines(f.read())}
    except OSError:
        return set()


def append_records(root, groups):
    """groups: (ledger_key, records) pairs; a group whose key the ledger, or an earlier group, already holds is
    skipped. Appends under the ledger's own lock — two sessions ending together each hold only their own
    session-state lock."""
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, LEDGER_FILE)
    with session_write.locked(os.path.join(root, LEDGER_LOCK)):
        body = b""
        if os.path.isfile(path):
            with open(path, "rb") as f:
                body = f.read()
        present = {ledger_key(old) for old in ledger_lines(body)}
        fresh = []
        for key, records in groups:
            if key not in present:
                present.add(key)
                fresh += records
        ragged = bool(body) and not body.endswith(b"\n")
        # A half-written last line must not swallow the first record.
        session_write.append(path, ("\n" if ragged and fresh else "") + "".join(json.dumps(r) + "\n" for r in fresh))
    return len(fresh)


def ledger_root(flag):
    root = accounting_root(flag)
    if not root:
        sys.exit("run-cost: no accounting root: pass --accounting-root, set $ROBOWRIGHT_ACCOUNTING_ROOT, "
                 f"or name accounting_root or sessions_root in {LAUNCH_JSON}")
    return root


def append_or_exit(root, groups):
    try:
        n = append_records(root, groups)
    except session_write.Refused as refusal:
        print(f"refused: --ledger: {refusal}", file=sys.stderr)
        return session_write.EXIT_REFUSED
    except OSError as exc:
        sys.exit(f"run-cost: cannot append to the ledger under {root}: {exc}")
    print(f"run-cost: {n} record(s) appended to {os.path.join(root, LEDGER_FILE)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir")
    ap.add_argument("--transcript", action="append", default=None, help="extra transcript path; repeatable")
    ap.add_argument("--write", action="store_true", help="store the block as run.json.cost")
    ap.add_argument("--whole-worktree", action="store_true",
                    help="ignore run.json transcripts and count every transcript under the worktree's project dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ledger", action="store_true",
                    help="append to the accounting ledger instead: the ending Claude session's records (--session-id and one "
                         "--transcript, plus any closed unit's missing ones), one closed unit's (--unit), or a doc role's (--role)")
    ap.add_argument("--session-id", help="with --ledger: the ending Claude session's id")
    ap.add_argument("--accounting-root", help="with --ledger: the ledger's directory (default $ROBOWRIGHT_ACCOUNTING_ROOT, "
                                              "else launch.json accounting_root, else accounting/ beside the sessions root)")
    ap.add_argument("--unit", help="with --ledger: the unit id whose unit-start → first unit-close window to record, at its unit-close")
    ap.add_argument("--role", choices=DOC_ROLES, help="with --ledger: the ending session is this doc role's; takes no --run-dir")
    ap.add_argument("--cwd", help="with --role: the session's cwd, whose basename is its project unless the launch index names one")
    args = ap.parse_args()
    one_transcript = bool(args.session_id and args.transcript and len(args.transcript) == 1)
    if args.role:
        if not (args.ledger and one_transcript and args.cwd):
            ap.error("--role needs --ledger, --session-id, --cwd and exactly one --transcript")
    elif not args.run_dir:
        ap.error("--run-dir is required, except with --role")
    elif args.ledger and not (args.unit or one_transcript):
        ap.error("--ledger needs --unit, or --session-id and exactly one --transcript")
    stale = prices().stale_warning()
    if stale:
        print(stale, file=sys.stderr)

    if args.role:
        root = ledger_root(args.accounting_root)
        transcript = os.path.abspath(os.path.expanduser(args.transcript[0]))
        return append_or_exit(root, [(("session", args.session_id),
                                      doc_role_records(root, args.role, args.session_id, transcript, args.cwd))])

    run_json = os.path.join(os.path.expanduser(args.run_dir), "run.json")
    try:
        with open(run_json) as f:
            run = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"run-cost: cannot read {run_json}: {exc}")

    if args.ledger:
        root = ledger_root(args.accounting_root)
        # Physical, as the launcher writes it: one session dir is one ledger key however it was reached.
        run_dir = os.path.realpath(os.path.expanduser(args.run_dir))
        windows = unit_windows(run_dir)
        if args.unit:
            if args.unit not in windows:
                sys.exit(f"run-cost: unit {args.unit} has no closed window in {run_dir}/events.jsonl "
                         "(no unit-start, or no unit-close after it); nothing appended")
            paths = unit_transcript_paths(run, run_dir, args.transcript)
            return append_or_exit(root, [(("unit", run_dir, args.unit),
                                          unit_records(run, run_dir, paths, {args.unit: windows[args.unit]}, "unit-close")[args.unit])])
        transcript = os.path.abspath(os.path.expanduser(args.transcript[0]))
        groups = [(("session", args.session_id), session_records(run, run_dir, args.session_id, transcript, "hook"))]
        # A unit whose --unit call never ran is caught up here; the scan is skipped when every closed unit is recorded.
        recorded = recorded_keys(root)
        missing = {u: w for u, w in windows.items() if ("unit", run_dir, u) not in recorded}
        if missing:
            paths = unit_transcript_paths(run, run_dir, args.transcript)
            groups += [(("unit", run_dir, u), records) for u, records in unit_records(run, run_dir, paths, missing, "backfill").items()]
        return append_or_exit(root, groups)

    paths = transcript_paths(run, args.run_dir, args.transcript, args.whole_worktree)
    cost = measure(paths, run)
    cost["lines_shipped"] = lines_shipped(run)
    cost["computed_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")
    previous = run.get("cost") or {}
    if previous.get("actual_usd") is not None:
        cost["actual_usd"] = previous["actual_usd"]

    if args.write:
        try:
            store_cost(run_json, cost)
        except session_write.Refused as refusal:
            print(f"refused: --write: {refusal}", file=sys.stderr)
            return session_write.EXIT_REFUSED

    if args.json:
        json.dump(cost, sys.stdout, indent=2)
        print()
        return 0

    shipped = cost["lines_shipped"]
    ratio = ""
    if shipped and shipped["added"]:
        ratio = f" ({cost['lines_written'] / shipped['added']:.1f}:1 written:shipped)"
    print(f"session:        {os.path.basename(os.path.abspath(args.run_dir))}  ({cost['transcripts']} transcript(s))")
    print(f"requests:       {cost['requests']:,}")
    print(f"output tokens:  {cost['output_tokens']:,}")
    print(f"input tokens:   {cost['input_tokens']:,} uncached · {cost['cache_read_tokens']:,} cache read · {cost['cache_write_tokens']:,} cache write")
    print(f"avg context:    {cost['avg_context_tokens']:,} tokens per request")
    if cost["requests"]:
        print(f"per request:    {money(cost['usd_per_request'], '.3f')}  (the number compact_pct and rotate_sessions are set from)")
    print(f"transcripts:    {'pinned by run.json' if (run.get('transcripts') and not args.whole_worktree) else 'every transcript under the worktree project dir'}")
    for model, m in sorted(cost["by_model"].items(), key=lambda kv: -kv[1]["requests"]):
        print(f"  {model}: {m['requests']:,} requests · {m['output_tokens']:,} out · est {money(m['estimated_usd'])}")
    w, sub = cost["by_role"]["worker"], cost["by_role"]["subagents"]
    print(f"by role:        worker {money(w['estimated_usd'])} over {w['requests']:,} req at {w['avg_context_tokens']:,} avg ctx · "
          f"subagents {money(sub['estimated_usd'])} over {sub['requests']:,} req in {sub['transcripts']} transcripts at {sub['avg_context_tokens']:,} avg ctx")
    print(f"estimated usd:  {money(cost['estimated_usd'])}  (estimate, meaningful only under a dollar budget — {prices().as_of_line()}; actual_usd: {cost['actual_usd']})")
    print(f"lines written:  {cost['lines_written']:,} over {cost['write_tool_calls']:,} Write/Edit calls" +
          (f"; shipped +{shipped['added']}/-{shipped['removed']} at {shipped['range']}{ratio}" if shipped else "; shipped: n/a (no worktree or base_sha, or the diff failed — see stderr)"))
    if cost["wall_hours_transcript"] is not None:
        print(f"wall (transcript): {cost['wall_hours_transcript']} h")
    if args.write:
        print(f"wrote run.json.cost in {run_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
