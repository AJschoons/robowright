#!/usr/bin/env python3
"""
test_budget_modes.py — the two scripts' behaviour when a brief carries no dollar budget.

Both scripts were written when every brief carried `spend_threshold_usd` and `spend_cap_usd`.
A machine profile whose Budget section is measured in anything else leaves both null, and the
two scripts have to stay honest there: the roster shows what it can count instead of a dollar
estimate, and the guard has nothing to enforce and says so rather than reporting a figure
nobody ratified.

It also holds the transcript-discovery cases the roster, the guard and run-cost.py share: an
unpinned session is found through the project dir Claude Code names after its worktree, a desktop
scheduled-task run is found by the ROBOWRIGHT_RUN_DIR line in its first user record, a <synthetic>
record is not a request, and run-cost.py --write shares session-state.py's lock.

Fixtures are throwaway session directories under $TMPDIR, with pinned transcripts or a scratch
$HOME, so nothing reads or writes a real session directory, the Claude projects tree, or the
session registry.

    python3 test_budget_modes.py        # prints one ok/FAIL line per test; non-zero on failure
"""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROSTER = os.path.join(HERE, "run-roster.py")
GUARD = os.path.join(HERE, "spend-guard.py")
RUN_COST = os.path.join(HERE, "../../worker/scripts/run-cost.py")

FAILURES = []


def check(name, ok, detail=""):
    if ok:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}: {detail}")
        FAILURES.append(name)


def write_transcript(transcript, name):
    """Three priced requests, and one <synthetic> record — Claude Code's placeholder for a turn that
    never reached the API, which is not a request."""
    with open(transcript, "w") as f:
        f.write(json.dumps({
            "uuid": f"{name}-synthetic",
            "message": {
                "id": f"{name}-msg-synthetic",
                "model": "<synthetic>",
                "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            },
        }) + "\n")
        for i in range(3):
            f.write(json.dumps({
                "uuid": f"{name}-{i}",
                "message": {
                    "id": f"{name}-msg-{i}",
                    "model": "claude-opus-5",
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "cache_read_input_tokens": 20000,
                        "cache_creation_input_tokens": 3000,
                    },
                },
            }) + "\n")


def write_fixture(root, name, threshold, cap):
    """One session directory whose run.json pins a transcript with three priced requests."""
    transcript = os.path.join(root, name + ".jsonl")
    write_transcript(transcript, name)
    return write_session(root, name, threshold, cap, os.path.join(root, name + "-worktree"), [transcript])


def write_unpinned_fixture(root, home, name, threshold, cap):
    """A session that pins nothing, in a <repo>/.worktrees/ worktree: its transcript is found
    only through the project dir Claude Code names after the cwd, every non-alphanumeric
    character turned into "-" (~/Dev/sample/.worktrees/x → -Users-…-sample--worktrees-x)."""
    worktree = os.path.join(os.path.realpath(home), "repo", ".worktrees", "wt_1")
    os.makedirs(worktree)
    project_dir = os.path.join(home, ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", worktree))
    os.makedirs(project_dir)
    write_transcript(os.path.join(project_dir, "session.jsonl"), name)
    return write_session(root, name, threshold, cap, worktree, [])


def write_opening_transcript(transcript, name, opening):
    """A transcript whose first user record is `opening`, after the queue-operation records Claude
    Code writes first, then three priced requests."""
    write_transcript(transcript, name)
    with open(transcript) as f:
        priced = f.read()
    with open(transcript, "w") as f:
        for op in ("enqueue", "dequeue"):
            f.write(json.dumps({"type": "queue-operation", "operation": op}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": opening}}) + "\n")
        f.write(priced)


def scheduled_opening(run_dir):
    """The first user record of a desktop scheduled-task run whose prompt is the Lead's two lines."""
    return (f'<scheduled-task name="robowright-x" file="/Users/x/.claude/scheduled-tasks/robowright-x/SKILL.md">\n'
            f"This is an automated run of a scheduled task.\n\n"
            f"/worker {run_dir}\nROBOWRIGHT_RUN_DIR={run_dir}\n</scheduled-task>")


def write_scheduled_fixture(root, home, name, pinned):
    """A Robowright Session launched as a desktop scheduled task. Its transcript lives in the project dir
    of the Lead's folder (~/Dev), not the worktree's, and is found only by the ROBOWRIGHT_RUN_DIR line in
    its first user record. Beside it, in the same project dir: its subagent sidecar; the Lead's own
    transcript, which quotes the same line but is not a scheduled-task run; and a scheduled run for
    a sibling session whose dir shares this one's name as a prefix. A stray session opened in the
    worktree is not counted either: a found run is as precise as a pin, so the worktree walk is
    skipped. Each holds three requests, so the right count is 6 (run + sidecar), plus 3 for a pin."""
    session_dir = os.path.join(root, name)
    project_dir = os.path.join(home, ".claude", "projects", "-Users-x-Dev")
    os.makedirs(project_dir, exist_ok=True)
    run_file = os.path.join(project_dir, f"{name}-run.jsonl")
    write_opening_transcript(run_file, f"{name}-run", scheduled_opening(session_dir))
    sidecar_dir = os.path.join(project_dir, f"{name}-run", "subagents")
    os.makedirs(sidecar_dir)
    write_transcript(os.path.join(sidecar_dir, "agent-a.jsonl"), f"{name}-sidecar")
    write_opening_transcript(os.path.join(project_dir, f"{name}-lead.jsonl"), f"{name}-lead",
                             f"You are the Lead. The run's first record opens with <scheduled-task name=…>.\n"
                             f"```\n/worker {session_dir}\nROBOWRIGHT_RUN_DIR={session_dir}\n```")
    write_opening_transcript(os.path.join(project_dir, f"{name}-sibling.jsonl"), f"{name}-sibling",
                             scheduled_opening(session_dir + "-2"))
    worktree = os.path.join(os.path.realpath(home), "worktrees", name)
    stray_dir = os.path.join(home, ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", worktree))
    os.makedirs(stray_dir)
    write_transcript(os.path.join(stray_dir, "stray.jsonl"), f"{name}-stray")
    transcripts = []
    if pinned:
        pin = os.path.join(root, f"{name}-pin.jsonl")
        write_transcript(pin, f"{name}-pin")
        transcripts = [pin]
    return write_session(root, name, 80, 100, worktree, transcripts)


def write_cache_read_fixture(root, name, model):
    """One request that is nothing but a million cache-read tokens, so the estimate is the model's
    cache-read price per million."""
    transcript = os.path.join(root, name + ".jsonl")
    with open(transcript, "w") as f:
        f.write(json.dumps({
            "uuid": f"{name}-0",
            "message": {"id": f"{name}-msg-0", "model": model, "usage": {"cache_read_input_tokens": 1_000_000}},
        }) + "\n")
    return write_session(root, name, 80, 100, os.path.join(root, name + "-worktree"), [transcript])


def write_every_class_fixture(root, name, model):
    """One request carrying a million tokens of each priced class — input, output, cache read, 5m
    and 1h cache write — so the estimate is the sum of the model's five rates."""
    transcript = os.path.join(root, name + ".jsonl")
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
        "cache_creation_input_tokens": 2_000_000,
        "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000, "ephemeral_1h_input_tokens": 1_000_000},
    }
    with open(transcript, "w") as f:
        f.write(json.dumps({"uuid": f"{name}-0", "message": {"id": f"{name}-msg-0", "model": model, "usage": usage}}) + "\n")
    return write_session(root, name, 80, 100, os.path.join(root, name + "-worktree"), [transcript])


def write_session(root, name, threshold, cap, worktree, transcripts):
    session_dir = os.path.join(root, name)
    os.makedirs(session_dir)
    with open(os.path.join(session_dir, "run.json"), "w") as f:
        json.dump({
            "ticket": name,
            "phase": "build",
            "worktree": worktree,
            "transcripts": transcripts,
            "started_at": "2026-09-19T00:00:00Z",
            "updated_at": "2026-09-19T00:00:00Z",
            "max_wall_hours": 10,
            "spend_threshold_usd": threshold,
            "spend_cap_usd": cap,
            "units": [{"id": "U1", "status": "todo"}],
        }, f)
    return session_dir


def run(argv, home=None):
    env = dict(os.environ, HOME=home) if home else None
    proc = subprocess.run([sys.executable] + argv, capture_output=True, text=True, env=env)
    return proc


def row_for(stdout, name):
    for line in stdout.splitlines():
        if line.startswith("|") and f"| {name} " in line:
            return line
    return ""


def main():
    root = tempfile.mkdtemp(prefix="budget-modes-", dir=os.environ.get("TMPDIR") or "/tmp")
    try:
        write_fixture(root, "no-budget", None, None)
        write_fixture(root, "dollar-budget", 80, 100)

        roster = run([ROSTER, "--runs-root", root, "--all", "--no-lead"])
        check("roster exits 0", roster.returncode == 0, roster.stderr.strip())
        null_row = row_for(roster.stdout, "no-budget")
        dollar_row = row_for(roster.stdout, "dollar-budget")

        check("roster: a session with no dollar threshold or cap shows requests and tokens",
              "req" in null_row and "out tok" in null_row and "$" not in null_row,
              f"row was {null_row!r}")
        check("roster: a session with a dollar cap still shows dollars against its limits",
              "$" in dollar_row and "cap $100" in dollar_row and "req" not in dollar_row,
              f"row was {dollar_row!r}")

        roster_json = run([ROSTER, "--runs-root", root, "--all", "--no-lead", "--json"])
        check("roster --json exits 0", roster_json.returncode == 0, roster_json.stderr.strip())
        try:
            rows = {r["run"]: r for r in json.loads(roster_json.stdout)["runs"]}
        except (ValueError, KeyError) as e:
            rows = {}
            check("roster --json is parseable", False, str(e))
        counted = [r for r in rows.values()
                   if isinstance(r.get("requests"), int) and r["requests"] > 0
                   and isinstance(r.get("tokens_out"), int) and r["tokens_out"] > 0]
        check("roster --json carries requests and tokens for every session",
              len(counted) == 2, f"counted {len(counted)} of {len(rows)}: {sorted(rows)}")

        guard = run([GUARD, "--runs-root", root])
        check("guard exits 0", guard.returncode == 0, guard.stderr.strip())
        check("guard: a session with a dollar cap is reported",
              "dollar-budget:" in guard.stdout, f"stdout was {guard.stdout!r}")
        check("guard: a session with no dollar threshold or cap is skipped silently",
              "no-budget" not in guard.stdout, f"stdout was {guard.stdout!r}")

        empty = run([GUARD, "--runs-root", root, "--only", "no-budget"])
        check("guard exits 0 with nothing in scope", empty.returncode == 0, empty.stderr.strip())
        check("guard: says there is nothing to enforce rather than reporting no sessions",
              "nothing to enforce" in empty.stdout, f"stdout was {empty.stdout!r}")

        unpinned_root = os.path.join(root, "unpinned-root")
        home = os.path.join(root, "home")
        os.makedirs(unpinned_root)
        os.makedirs(home)
        unpinned_dir = write_unpinned_fixture(unpinned_root, home, "unpinned", 80, 100)

        found = run([ROSTER, "--runs-root", unpinned_root, "--all", "--no-lead", "--json"], home=home)
        try:
            requests = json.loads(found.stdout)["runs"][0].get("requests")
        except (ValueError, KeyError, IndexError) as e:
            requests = f"unparseable: {e}"
        check("roster: an unpinned session in a .worktrees worktree finds its transcripts",
              requests == 3, f"requests was {requests!r}; stderr {found.stderr.strip()!r}")

        guarded = run([GUARD, "--runs-root", unpinned_root], home=home)
        check("guard: an unpinned session in a .worktrees worktree is priced from its transcripts",
              "over 3 msgs" in guarded.stdout, f"stdout was {guarded.stdout!r}")

        cost = run([RUN_COST, "--run-dir", unpinned_dir, "--json"], home=home)
        try:
            cost_requests = json.loads(cost.stdout).get("requests")
        except ValueError as e:
            cost_requests = f"unparseable: {e}"
        check("run-cost: an unpinned session in a .worktrees worktree finds its transcripts",
              cost_requests == 3, f"requests was {cost_requests!r}; stderr {cost.stderr.strip()!r}")

        # A desktop scheduled-task run: found by its ROBOWRIGHT_RUN_DIR line, with its sidecar, and
        # never through the Lead's transcript or a sibling session's run (6 requests); a pin is
        # counted on top of it (9).
        sched_root = os.path.join(root, "sched-root")
        sched_home = os.path.join(root, "sched-home")
        os.makedirs(sched_root)
        os.makedirs(sched_home)
        sched_dirs = {name: write_scheduled_fixture(sched_root, sched_home, name, pinned)
                      for name, pinned in (("sched", False), ("sched-pinned", True))}
        expected = {"sched": 6, "sched-pinned": 9}

        listed = run([ROSTER, "--runs-root", sched_root, "--all", "--no-lead", "--json"], home=sched_home)
        try:
            roster_requests = {r["run"]: r.get("requests") for r in json.loads(listed.stdout)["runs"]}
        except (ValueError, KeyError) as e:
            roster_requests = {"unparseable": str(e)}
        guarded = run([GUARD, "--runs-root", sched_root], home=sched_home)
        guard_requests = {m.group(1): int(m.group(2))
                          for m in re.finditer(r"^(\S+): \$[\d,.]+ over (\d+) msgs", guarded.stdout, re.M)}
        cost_requests = {}
        for name, session_dir in sched_dirs.items():
            cost = run([RUN_COST, "--run-dir", session_dir, "--json"], home=sched_home)
            try:
                cost_requests[name] = json.loads(cost.stdout).get("requests")
            except ValueError as e:
                cost_requests[name] = f"unparseable: {e}; stderr {cost.stderr.strip()!r}"
        for script, counts in (("roster", roster_requests), ("guard", guard_requests), ("run-cost", cost_requests)):
            check(f"{script}: a scheduled-task run is found by its ROBOWRIGHT_RUN_DIR line, with its sidecar and any pin",
                  counts == expected, f"requests were {counts!r}, expected {expected!r}")

        # platform.claude.com/docs/en/about-claude/pricing: a cache read is $1 / MTok on Claude Fable 5
        # and $0.25 / MTok on Claude Fable 5.1, whose id starts with Fable 5's.
        price_root = os.path.join(root, "price-root")
        os.makedirs(price_root)
        for name, model, expected in (("fable-5", "claude-fable-5", 1.00), ("fable-5-1", "claude-fable-5-1", 0.25)):
            session_dir = write_cache_read_fixture(price_root, name, model)
            cost = run([RUN_COST, "--run-dir", session_dir, "--json"])
            try:
                estimated = json.loads(cost.stdout).get("estimated_usd")
            except ValueError as e:
                estimated = f"unparseable: {e}"
            check(f"run-cost: a million cache-read tokens on {model} is ${expected:.2f}",
                  estimated == expected, f"estimated_usd was {estimated!r}")
        priced = run([ROSTER, "--runs-root", price_root, "--all", "--no-lead", "--json"])
        try:
            spend = {r["run"]: r.get("spend_usd") for r in json.loads(priced.stdout)["runs"]}
        except (ValueError, KeyError) as e:
            spend = {"unparseable": str(e)}
        check("roster: Fable 5 and Fable 5.1 cache reads are priced apart",
              spend == {"fable-5": 1.00, "fable-5-1": 0.25}, f"spend_usd was {spend!r}")
        guard_priced = run([GUARD, "--runs-root", price_root])
        check("guard: Fable 5 and Fable 5.1 cache reads are priced apart",
              "fable-5: $1.00 " in guard_priced.stdout and "fable-5-1: $0.25 " in guard_priced.stdout,
              f"stdout was {guard_priced.stdout!r}")

        # platform.claude.com/docs/en/about-claude/pricing, fetched 2026-09-24: Claude Opus 5.5 is
        # $4 input, $20 output, $0.20 cache read (0.05x), $5 5m write, $8 1h write — $37.20 for a
        # million of each. Its id starts with Opus 5's, whose rates would give $46.75.
        opus_root = os.path.join(root, "opus-5-5-root")
        os.makedirs(opus_root)
        opus_dir = write_every_class_fixture(opus_root, "opus-5-5", "claude-opus-5-5")
        cost = run([RUN_COST, "--run-dir", opus_dir, "--json"])
        try:
            estimated = json.loads(cost.stdout).get("estimated_usd")
        except ValueError as e:
            estimated = f"unparseable: {e}"
        check("run-cost: a million of each token class on claude-opus-5-5 is $37.20",
              estimated == 37.20, f"estimated_usd was {estimated!r}")
        priced = run([ROSTER, "--runs-root", opus_root, "--all", "--no-lead", "--json"])
        try:
            spend = [r.get("spend_usd") for r in json.loads(priced.stdout)["runs"]]
        except (ValueError, KeyError) as e:
            spend = f"unparseable: {e}"
        check("roster: a million of each token class on claude-opus-5-5 is $37.20",
              spend == [37.20], f"spend_usd was {spend!r}")
        guard_priced = run([GUARD, "--runs-root", opus_root])
        check("guard: a million of each token class on claude-opus-5-5 is $37.20",
              "opus-5-5: $37.20 " in guard_priced.stdout, f"stdout was {guard_priced.stdout!r}")

        # session-state.py writes run.json under <session_dir>/.session-state.lock; run-cost --write
        # is the other writer, so it waits for the same lock and writes onto what is there then.
        run_json = os.path.join(unpinned_dir, "run.json")
        with open(os.path.join(unpinned_dir, ".session-state.lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            writer = subprocess.Popen([sys.executable, RUN_COST, "--run-dir", unpinned_dir, "--write", "--json"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, HOME=home))
            time.sleep(1.0)
            with open(run_json) as held:
                during = json.load(held)
            during["phase"] = "changed-while-scanning"
            with open(run_json, "w") as held:
                json.dump(during, held)
            fcntl.flock(lock, fcntl.LOCK_UN)
        writer.wait(timeout=30)
        with open(run_json) as after_file:
            after = json.load(after_file)
        check("run-cost --write: waits for the state tool's lock",
              "cost" not in during, f"cost was written while the lock was held: {during.get('cost')!r}")
        check("run-cost --write: stores cost onto run.json as it is at write time",
              after.get("phase") == "changed-while-scanning" and (after.get("cost") or {}).get("requests") == 3,
              f"phase {after.get('phase')!r}, cost {after.get('cost')!r}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall passed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
