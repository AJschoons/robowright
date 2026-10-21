#!/usr/bin/env python3
"""
spend-guard.py — estimate each Robowright Session's API spend from its Claude Code transcripts,
warn at the brief's threshold, and drop a STOP file into the session directory at the cap.

**This script only matters where the budget is measured in dollars.** The machine profile's
Budget section says what a Robowright Session's budget is and what enforces it; a profile that
answers "dollars" names this script, and a profile that answers plan usage or wall hours does
not run it at all. A brief with neither `spend_threshold_usd` nor `spend_cap_usd` set is
skipped silently — there is nothing here to enforce.

Spend is computed from the per-message `usage` records under
~/.claude/projects/<worktree-slug>/**/*.jsonl (main session + subagents), priced per model.
Limits come from the session's own run.json, which the planner writes from the ratified brief:

    spend_cap_usd         STOP is written at or over this (stop_reason `owner-stop`)
    spend_threshold_usd   a warning line and a LEDGER.md entry, nothing else

`--cap` overrides every session's cap for one invocation, so it also brings sessions with no
limits of their own into scope. The STOP file is what the worker skill and its Stop hook
honour: the session finishes its current step, writes stop_reason `owner-stop`, rewrites
HANDOFF.md, ends.

The sessions root is --runs-root (repeatable), else $ROBOWRIGHT_SESSIONS_ROOT, else `sessions_root`
in ~/.claude/robowright/launch.json; with none of them the guard refuses by name, exits 2, and
writes nothing.

Usage:
    spend-guard.py                     # spend per Robowright Session, once
    spend-guard.py --watch 60          # poll every 60s; enforce each session's own cap
    spend-guard.py --cap 200 --watch 60
    spend-guard.py --dry-run --watch 60  # say what would happen, write nothing
    spend-guard.py --json
"""

import argparse
import functools
import glob
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "robowright", "scripts"))
import session_write  # noqa: E402

LAUNCH_JSON = os.path.expanduser("~/.claude/robowright/launch.json")
PROJECTS_ROOT = os.path.expanduser("~/.claude/projects")

@functools.lru_cache(maxsize=None)
def prices():
    """The pricing file, loaded once a run so a missing file says so in one stderr line. Without it
    every estimate is null, and a null estimate crosses no threshold and no cap."""
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../robowright/scripts/pricing.py")
    spec = importlib.util.spec_from_file_location("pricing", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load()


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


def transcript_paths(run, run_dir):
    """Every transcript that belongs to this Robowright Session. run.json may pin sessions explicitly,
    and a desktop scheduled-task run is found by its ROBOWRIGHT_RUN_DIR line."""
    explicit = (run.get("transcripts") or []) + scheduled_run_transcripts(run_dir)
    if explicit:
        paths = []
        for session_path in explicit:
            session_path = os.path.expanduser(session_path)
            paths.append(session_path)
            side_dir = session_path[: -len(".jsonl")] if session_path.endswith(".jsonl") else session_path
            paths.extend(glob.glob(os.path.join(side_dir, "**", "*.jsonl"), recursive=True))
        return paths
    worktree = run.get("worktree")
    if not worktree:
        return []
    return glob.glob(os.path.join(PROJECTS_ROOT, project_slug(worktree), "**", "*.jsonl"), recursive=True)


def spend_of(paths):
    usd = 0.0
    messages = 0
    tokens_out = 0
    seen = set()
    for path in paths:
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = rec.get("message") or {}
                    usage = msg.get("usage")
                    if not usage:
                        continue
                    # Claude Code's placeholder for a turn that never reached the API; not a request.
                    if msg.get("model") == "<synthetic>":
                        continue
                    mid = msg.get("id") or rec.get("uuid")
                    if mid in seen:
                        continue
                    seen.add(mid)
                    usd += prices().usage_cost(msg.get("model", ""), usage) or 0.0
                    tokens_out += usage.get("output_tokens", 0)
                    messages += 1
        except OSError:
            continue
    return (usd if prices().as_of else None), messages, tokens_out


def number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def launch_sessions_root():
    """launch.json's sessions_root, read as session-state.py's locks_root reads it: (root, None), or (None, why not)."""
    if not os.path.exists(LAUNCH_JSON):
        return None, "no such file"
    try:
        with open(LAUNCH_JSON) as f:
            settings = json.load(f)
    except (OSError, ValueError) as e:
        return None, f"unreadable: {e}"
    if not isinstance(settings, dict):
        return None, "not a JSON object"
    root = settings.get("sessions_root")
    if not (isinstance(root, str) and root):
        return None, "sessions_root is missing, empty or not a string"
    if root.startswith("~/"):
        return os.path.expanduser("~") + root[1:], None
    return root, None


def sessions_roots(flag_roots):
    """--runs-root, else $ROBOWRIGHT_SESSIONS_ROOT, else launch.json's sessions_root; None, with the refusal on stderr, when none names one."""
    if flag_roots:
        return [os.path.expanduser(root) for root in flag_roots]
    env_root = os.environ.get("ROBOWRIGHT_SESSIONS_ROOT")
    if env_root:
        return [os.path.expanduser(env_root)]
    root, why = launch_sessions_root()
    if root:
        return [root]
    print(f"spend-guard.py: no sessions root: set sessions_root in {LAUNCH_JSON} ({why}), "
          "or set $ROBOWRIGHT_SESSIONS_ROOT, or pass --runs-root", file=sys.stderr)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap", type=float, default=None, help="USD; overrides every session's spend_cap_usd")
    ap.add_argument("--watch", type=int, default=0, help="poll interval seconds; 0 = once")
    ap.add_argument("--warn", type=float, default=0.8, help="fraction of cap to warn at when the session has no spend_threshold_usd")
    ap.add_argument("--only", action="append", default=None, help="session directory name(s); repeatable")
    ap.add_argument("--dry-run", action="store_true", help="report what would happen; never write")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--runs-root", action="append", default=None,
                    help="repeatable; default $ROBOWRIGHT_SESSIONS_ROOT, else sessions_root in launch.json")
    args = ap.parse_args()

    roots = sessions_roots(args.runs_root)
    if roots is None:
        return 2
    stale = prices().stale_warning()
    if stale:
        print(stale, file=sys.stderr)
    if not args.json:
        print(prices().as_of_line(), flush=True)
    warned = set()
    stopped = set()
    while True:
        rows = []
        run_dirs = []
        for root in roots:
            run_dirs += glob.glob(os.path.join(root, "*"))
        for run_dir in sorted(run_dirs):
            name = os.path.basename(run_dir)
            run_json = os.path.join(run_dir, "run.json")
            if not os.path.isfile(run_json) or (args.only and name not in args.only):
                continue
            try:
                with open(run_json) as f:
                    run = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            phase = run.get("phase")
            if phase in ("done", "stopped", "parked") and not args.only:
                continue
            cap = args.cap if args.cap is not None else number(run.get("spend_cap_usd"))
            threshold = number(run.get("spend_threshold_usd"))
            if threshold is None and cap is not None:
                threshold = cap * args.warn
            if cap is None and threshold is None:
                # No dollar budget on this brief, so there is nothing here to enforce: skip it
                # silently rather than print an estimate nobody ratified. The profile's Budget
                # section holds whatever gate this machine does use.
                continue
            usd, messages, tokens_out = spend_of(transcript_paths(run, run_dir))
            stop_file = os.path.join(run_dir, "STOP")
            action = ""
            if usd is not None and cap is not None and usd >= cap and not os.path.exists(stop_file) and name not in stopped:
                action = f"STOP (cap ${cap:,.0f})"
                if not args.dry_run:
                    stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
                    try:
                        session_write.replace(stop_file, f"spend-guard: ${usd:,.2f} >= spend_cap_usd ${cap:,.2f} at {stamp}\n")
                        session_write.append(os.path.join(run_dir, "LEDGER.md"),
                                             f"\n{stamp} spend-guard: STOP written, estimated ${usd:,.2f} >= cap ${cap:,.2f}\n")
                        stopped.add(name)
                    except session_write.Refused as refusal:
                        # Not marked stopped, so the next pass tries again.
                        action = f"refused: {refusal}"
            elif usd is not None and threshold is not None and usd >= threshold and name not in warned and name not in stopped:
                action = f"warning: past threshold ${threshold:,.0f}"
                warned.add(name)
                if not args.dry_run:
                    try:
                        session_write.append(os.path.join(run_dir, "LEDGER.md"),
                                             f"\n{datetime.now():%Y-%m-%d %H:%M} spend-guard: estimated ${usd:,.2f} past spend_threshold_usd ${threshold:,.2f}\n")
                    except session_write.Refused as refusal:
                        action = f"refused: {refusal}"
            elif os.path.exists(stop_file):
                action = "(STOP present)"
            rows.append({
                "run": name, "phase": phase, "usd": round(usd, 2) if usd is not None else None, "messages": messages,
                "tokens_out": tokens_out, "cap": cap, "threshold": threshold, "action": action,
            })

        if args.json:
            json.dump(rows, sys.stdout)
            print(flush=True)
        else:
            for r in rows:
                limits = " / ".join(
                    s for s in (
                        f"warn ${r['threshold']:,.0f}" if r["threshold"] is not None else "",
                        f"cap ${r['cap']:,.0f}" if r["cap"] is not None else "",
                    ) if s
                ) or "no limits"
                spend = "n/a" if r["usd"] is None else f"${r['usd']:,.2f}"
                line = f"{r['run']}: {spend} over {r['messages']} msgs, {r['tokens_out']:,} out tokens, phase={r['phase']}, {limits}"
                if r["action"]:
                    line += f"  ** {'would ' if args.dry_run and r['action'].startswith('STOP') else ''}{r['action']} **"
                print(line, flush=True)
            if not rows:
                print("nothing to enforce: no unfinished Robowright Session carries a dollar threshold or cap",
                      flush=True)
        if not args.watch:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
