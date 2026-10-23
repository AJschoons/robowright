#!/usr/bin/env python3
"""Robowright dashboard: every project under the projects root, and every Robowright Session under the sessions root.

Read-only and token-free. It reads PROJECT.md (Task Breakdown, Detailed TODO), run.json, events.jsonl,
LEDGER.md and HANDOFF.md, plus `git merge-base` to tell built from complete.

The sessions root is --runs-root, else $ROBOWRIGHT_SESSIONS_ROOT, else `sessions_root` in
~/.claude/robowright/launch.json — run-roster.py's resolution, which refuses by name and exits 2 when none names
one. The projects root is --projects-root, else $ROBOWRIGHT_PROJECTS_ROOT, else launch.json's `projects_root`,
else the sessions root's parent. The longest silence seen per running session is kept in
robowright-dash.gaps.json under the accounting root (run-cost.py's), and only in memory when there is none.

    robowright-dash.py                  text summary of every project in the terminal
    robowright-dash.py <project>        text summary of one project, with its units
    robowright-dash.py --serve PORT     index at /, a page per project at /p/<name>, re-rendered on every GET
    robowright-dash.py --once DIR       index.html plus <project>.html into DIR
    [--all] [--runs-root DIR] [--projects-root DIR]
"""
import argparse
import html
import importlib.util
import itertools
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

CLONE = Path(__file__).resolve().parents[1]
# The project name ends at the first three-digit segment; launch.json's unit.group_regex wins when present.
FALLBACK_GROUP_REGEX = r"^([0-9]*[a-z][a-z0-9]*(-[0-9]*[a-z][a-z0-9]*)*)-[0-9]{3}-"
REFRESH_SECONDS = 20
EVENTS_SHOWN = 8
SIZE_WEIGHT = {"XS": 1, "S": 2, "M": 3, "L": 5, "XL": 8}
DEFAULT_WEIGHT = 3
# A unit's tone, most urgent first: complete = in its repo's main; built = every session done and through the Lead's
# intake, none in main yet; intake = done, but the Lead has not handed it to the Owner; settled = closed or moved.
PLAN_TONES = ("stopped", "owner-call", "rebriefing", "rotating", "working", "briefing", "briefed", "intake", "built", "complete", "parked", "settled", "todo")
# The legend reads the way work moves through the bar: furthest along first, not started last.
LEGEND_ORDER = ("complete", "built", "intake", "working", "rotating", "rebriefing", "owner-call", "stopped", "parked", "settled", "briefed", "briefing", "todo")
assert set(LEGEND_ORDER) == set(PLAN_TONES)
PLAN_LABEL = {"complete": "complete", "built": "awaiting acceptance", "intake": "with the Lead", "working": "working", "stopped": "stopped",
              "rotating": "rotating", "briefed": "briefed", "parked": "parked", "settled": "closed or moved", "todo": "not started",
              "rebriefing": "Planner rebriefing", "briefing": "Planner briefing", "owner-call": "rebrief needs your call"}
SESSION_TONE = {"done": "done", "stopped": "stopped", "parked": "parked", "briefed": "briefed"}
TERMINAL_TONES = ("done", "parked")
NOT_STARTED_TONES = ("todo", "briefed", "parked", "settled")
# What the Lead still owes a finished session before the Owner reads it (lead skill → intake, steps 2 and 7).
LEAD_STAGE_PHRASE = {"intake": "waiting on the Lead's intake", "review guide": "waiting on the Lead's owner brief",
                     "check": "waiting on the Lead's check", "owner brief": "the Lead's owner brief in progress"}
STUCK_MINUTES = 30
ACTIVITY_SCAN_MAX_FILES = 20000
# How far back main's history is searched for a squash that carries a session's exact tree.
MAIN_TREES_SCANNED = 200
SKIP_DIRS = {".git", "node_modules", ".build", "DerivedData", "Pods"}
REGISTRY_DIR = Path.home() / ".claude/sessions"
# A real run.json nests 5 levels deep; str() overflows near 70,000.
MAX_RUN_DEPTH = 100
# json.loads joins a valid pair, so any surrogate left in a string is lone.
LONE_SURROGATE = re.compile("[\ud800-\udfff]")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
# A slug `robowright/<slug>` can name as a branch: no `..`, `@{`, `^`, `~`, `:` or `/`, which git would read as more
# than a branch name, and no ending a ref may not have.
BRANCH_SLUG = re.compile(r"[A-Za-z0-9]+([._-][A-Za-z0-9]+)*(?<!\.lock)")
# A direct build's accept record, in the project folder's prs/<slug>/, and the commit id it must name.
ACCEPT_RECORD = "ACCEPTED.json"
FULL_COMMIT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# The id a branch verified gone from every trusted repository is held under: a deleted branch does not come back.
GONE = "gone"


# ---------------------------------------------------------------- config


def load_clone_script(name: str, relative: str):
    """A script of the clone whose file name is not importable, loaded by path; the dashboard runs from the clone."""
    path = CLONE / relative
    if not path.is_file():
        print(f"robowright-dash.py: {path} not found; run the dashboard from its clone, as tools/robowright-dash.py",
              file=sys.stderr)
        sys.exit(2)
    # No __pycache__ beside the scripts it loads: the dashboard never writes into the clone.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROSTER = load_clone_script("run_roster", "skills/lead/scripts/run-roster.py")
RUN_COST = load_clone_script("run_cost", "skills/worker/scripts/run-cost.py")
COST_ROLLUP = load_clone_script("robowright_cost", "skills/robowright/scripts/robowright-cost.py")
OWNER_GIT = load_clone_script("owner_git", "skills/robowright/scripts/owner_git.py")
LAUNCH_SETTINGS, LAUNCH_UNREAD = ROSTER.read_launch_json()
CONFIG = LAUNCH_SETTINGS or {}
ACCOUNTING_ROOT = RUN_COST.accounting_root(None)
GAPS_FILE = Path(ACCOUNTING_ROOT) / "robowright-dash.gaps.json" if ACCOUNTING_ROOT else None
# Set by main() from the flags, the environment and launch.json.
PROJECTS_ROOT: Path
SESSIONS_ROOT: Path
PLANNER_PREFIX = ((CONFIG.get("roles") or {}).get("planner") or {}).get("name_prefix") or "planner"
LEAD_PREFIX = ((CONFIG.get("roles") or {}).get("lead") or {}).get("name_prefix") or "lead"
EXPLAINER_PREFIX = ((CONFIG.get("roles") or {}).get("explainer") or {}).get("name_prefix") or "explainer"
GROUP_REGEX = re.compile((CONFIG.get("unit") or {}).get("group_regex") or FALLBACK_GROUP_REGEX)
OWNER_BRIEF_DIR = CONFIG.get("review_guide_dir") or "reviews"


# ---------------------------------------------------------------- small helpers


def parse_at(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.astimezone()


def ago(dt) -> str:
    if dt is None:
        return "—"
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    if seconds < 90:
        return f"{int(seconds)}s ago"
    if seconds < 5400:
        return f"{int(seconds // 60)}m ago"
    if seconds < 172800:
        return f"{seconds / 3600:.1f}h ago"
    return f"{int(seconds // 86400)}d ago"


def git(cwd: str, *args) -> str | None:
    """git with owner_git's overrides; a session's worktree reaches it only through listed_worktree."""
    try:
        out = OWNER_GIT.run(cwd, *args, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def trusted_repos() -> list:
    return OWNER_GIT.configured_repos(PROJECTS_ROOT, sessions=SESSIONS_ROOT)


def listed_worktrees() -> dict:
    return OWNER_GIT.index(trusted_repos())


def listed_branches() -> dict:
    return OWNER_GIT.branch_index(trusted_repos())


def untrusted() -> tuple | None:
    """(code, how to fix it) when launch.json's `repos` keeps a project's repository untrusted, so no worktree of it is read."""
    return OWNER_GIT.untrusted(PROJECTS_ROOT, sessions=SESSIONS_ROOT)


def trust_note() -> str:
    found = untrusted()
    return f" · {e(found[0])}: {e(found[1])}" if found else ""


def listed_worktree(worktree: str, listed: dict) -> tuple | None:
    """(canonical worktree, its configured repository), or None when no repository under the projects root lists it."""
    try:
        return OWNER_GIT.check(worktree, listed)
    except OWNER_GIT.Unlisted:
        return None


def weight(unit: dict) -> int:
    return SIZE_WEIGHT.get(unit["size"].strip("`* "), DEFAULT_WEIGHT)


def e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def count(value):
    """A finite run.json number, or None when the session wrote anything else there."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


# ---------------------------------------------------------------- sessions


def project_of(slug: str) -> str | None:
    match = GROUP_REGEX.match(slug)
    return match.group(1) if match else None


def filed_under(run: dict, slug: str) -> str | None:
    """The project a session is filed under: run.json.project when it is a non-empty string, else the directory name's capture."""
    project = run.get("project")
    return project if isinstance(project, str) and project else project_of(slug)


def session_number(slug: str) -> str:
    match = re.search(r"-(\d{3})-", slug)
    return match.group(1) if match else ""


def read_events(path: Path) -> list:
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"event": "unparseable line", "at": ""})
    return events


def ledger_headings(path: Path) -> list:
    if not path.exists():
        return []
    return [line[3:].strip() for line in path.read_text().splitlines() if line.startswith("## ")]


def handoff_first_action(path: Path) -> str:
    if not path.exists():
        return ""
    match = re.search(r"^## FIRST ACTION\s*\n(.*?)(?=^## |\Z)", path.read_text(), re.S | re.M)
    return match.group(1).strip() if match else ""


def is_alive(pid) -> bool:
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def live_agents() -> list:
    """Claude Code's registry of running sessions — name, busy or idle, since when. An internal format, read defensively."""
    rows = []
    for path in REGISTRY_DIR.glob("*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and is_alive(row.get("pid")):
            rows.append(row)
    return rows


def planner_for(slug: str, agents: list) -> dict | None:
    """The newest live Planner named for this Robowright Session: `<prefix>-<slug>`, or `<prefix>-<slug>-r<n>` for a rebrief."""
    pattern = re.compile(rf"^{re.escape(PLANNER_PREFIX)}-{re.escape(slug)}(-r\d+)?$")
    return max((a for a in agents if pattern.match(a.get("name") or "")), key=lambda a: a.get("startedAt", 0), default=None)


def follow_up_for(slug: str, worktree: str, agents: list) -> dict | None:
    """A busy session working a finished unit: a polish or docs pass the Lead started on it, under whatever name.
    It belongs to the unit when its name ends in a slug with the unit's number, or it runs in the unit's worktree."""
    role_prefixes = (PLANNER_PREFIX + "-", LEAD_PREFIX + "-")
    for agent in agents:
        name = agent.get("name") or ""
        if agent.get("status") != "busy" or name.startswith(role_prefixes):
            continue
        named = slug_in(name)
        if (named and unit_key(named) == unit_key(slug)) or (worktree and agent.get("cwd") == worktree):
            return agent
    return None


def session_tone(run: dict, dir_: Path, agents: list) -> str:
    rotate = run.get("rotate") or {}
    if rotate.get("requested_at") and not rotate.get("resumed_at"):
        rebriefs = run.get("rebriefs") or []
        is_owner_verdict = rotate.get("reason") == "rebrief" and bool(rebriefs) and rebriefs[-1].get("verdict") == "owner"
        return "owner-call" if is_owner_verdict else "rotating"
    if run.get("parked"):
        return "parked"
    # `preflight` is stored for a brief nothing launched and a running preflight alike; the state tool tells them apart.
    if ROSTER.STATE.never_launched(ROSTER.STATE_TABLE, run, dir_, is_live=ROSTER.match_session(run, agents) is not None):
        return "briefed"
    return SESSION_TONE.get(run.get("phase", ""), "working")


def files_under(root: str):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            yield os.path.join(dirpath, name)


def last_write(roots: list) -> datetime | None:
    """Newest file write in the session folder and its worktree. Events mark only stage changes, so a Worker
    re-running its suite writes files long before it writes an event."""
    newest = 0.0
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for path in itertools.islice(files_under(root), ACTIVITY_SCAN_MAX_FILES):
            try:
                newest = max(newest, os.stat(path).st_mtime)
            except OSError:
                continue
    return datetime.fromtimestamp(newest, tz=timezone.utc) if newest else None


def load_gaps() -> dict:
    if GAPS_FILE is None:
        return {}
    try:
        return json.loads(GAPS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


LONGEST_QUIET = load_gaps()


def record_quiet(slug: str, minutes: float) -> float:
    """Longest silence the dashboard has observed for a running session, kept across restarts to tune STUCK_MINUTES."""
    if minutes <= LONGEST_QUIET.get(slug, 0):
        return LONGEST_QUIET[slug]
    LONGEST_QUIET[slug] = round(minutes, 1)
    if GAPS_FILE is None:
        return LONGEST_QUIET[slug]
    try:
        GAPS_FILE.write_text(json.dumps(LONGEST_QUIET, indent=1, sort_keys=True))
    except OSError:
        pass
    return LONGEST_QUIET[slug]


def is_commit_id(value) -> bool:
    return isinstance(value, str) and RUN_COST.COMMIT_ID.fullmatch(value) is not None


def held_run(run: dict) -> dict:
    """run.json with each value SECURITY.md lists that the dashboard reads held to its shape; any other shape reads as missing."""
    if not isinstance(run.get("phase"), str):
        run.pop("phase", None)
    if not isinstance(run.get("ticket"), str):
        run.pop("ticket", None)
    if not isinstance(run.get("worktree"), str):
        run.pop("worktree", None)
    if not isinstance(run.get("rotate"), dict):
        run.pop("rotate", None)
    if not isinstance(run.get("stop_reason"), (dict, str)):
        run.pop("stop_reason", None)
    for key in ("code", "detail"):
        if isinstance(run.get("stop_reason"), dict) and not isinstance(run["stop_reason"].get(key), str):
            run["stop_reason"].pop(key, None)
    for key in ("rebriefs", "units"):
        if key in run:
            run[key] = [entry for entry in run[key] if isinstance(entry, dict)] if isinstance(run[key], list) else []
    publish = run.get("publish")
    if isinstance(publish, dict) and not (publish.get("tip") == "HEAD" or is_commit_id(publish.get("tip"))):
        publish.pop("tip", None)
    for rebrief in run.get("rebriefs") or []:
        if not isinstance(rebrief.get("why"), str):
            rebrief.pop("why", None)
    for unit in run.get("units") or []:
        if not isinstance(unit.get("status"), str):
            unit.pop("status", None)
        if not is_commit_id(unit.get("head")):
            unit.pop("head", None)
    return run


def check_servable(run: dict) -> None:
    """ValueError for a value nested past MAX_RUN_DEPTH or a string holding a lone surrogate, which no page can carry.
    Walked with a stack: str() and json.dumps overflow on nesting json.loads still reads."""
    stack = [(run, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_RUN_DEPTH:
            raise ValueError("run.json nests too deeply")
        if isinstance(value, dict):
            stack.extend((part, depth + 1) for pair in value.items() for part in pair)
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, str) and LONE_SURROGATE.search(value):
            raise ValueError("run.json holds a string no page can encode")


def read_run(path: Path) -> dict:
    """run.json as an object the pages can carry; a ValueError otherwise, which reads as an unreadable run.json."""
    try:
        run = json.loads(path.read_text())
    except RecursionError as err:
        raise ValueError("run.json nests too deeply") from err
    if not isinstance(run, dict):
        raise ValueError("run.json is not a JSON object")
    check_servable(run)
    return run


def load_session(dir_: Path, run: dict, agents: list) -> dict:
    run = held_run(run)
    touched = max((p.stat().st_mtime for p in [dir_ / "run.json", dir_ / "LEDGER.md", dir_ / ".session-state.lock"]
                   if p.exists()), default=0)
    planner = planner_for(dir_.name, agents)
    tone = session_tone(run, dir_, agents)
    if tone == "stopped" and planner and planner.get("status") == "busy":
        tone = "rebriefing"
    follow_up = follow_up_for(dir_.name, run.get("worktree") or "", agents) if tone == "done" else None
    # An Explainer on a finished unit is writing the owner brief, a Lead step, not more building.
    explainer = follow_up if follow_up and (follow_up.get("name") or "").startswith(EXPLAINER_PREFIX + "-") else None
    if explainer:
        follow_up = None
    if follow_up:
        tone = "working"
    active = quiet = longest_quiet = None
    if tone in ("working", "rotating"):
        active = last_write([str(dir_), run.get("worktree")])
        if active:
            quiet = (datetime.now(timezone.utc) - active).total_seconds() / 60
            longest_quiet = record_quiet(dir_.name, quiet)
    return {
        "slug": dir_.name,
        "project": filed_under(run, dir_.name),
        "number": session_number(dir_.name),
        "dir": str(dir_),
        "run": run,
        "phase": run.get("phase", "?"),
        "tone": tone,
        "planner": planner,
        "follow_up": follow_up,
        "explainer": explainer,
        "active": active,
        "quiet_minutes": quiet,
        "longest_quiet": longest_quiet,
        "started": parse_at(run.get("started_at")),
        "touched": datetime.fromtimestamp(touched, tz=timezone.utc) if touched else None,
        "events": read_events(dir_ / "events.jsonl"),
        "ledger": ledger_headings(dir_ / "LEDGER.md"),
        "first_action": handoff_first_action(dir_ / "HANDOFF.md"),
        "has_stop_file": (dir_ / "STOP").exists(),
        "has_intake": (dir_ / "INTAKE.md").exists(),
        "files": sorted(p.name for sub in ("reviews", "prs") if (dir_ / sub).is_dir() for p in (dir_ / sub).glob("*.md")),
    }


def pending_session(slug: str, kind: str, tone: str, run: dict, dir_: Path, agent: dict | None, roots: list) -> dict:
    """A session with no run.json: a Planner still writing the brief, or a direct build, which has no session folder."""
    active = last_write([str(r) for r in roots]) if tone == "working" or kind == "briefing" else None
    quiet = (datetime.now(timezone.utc) - active).total_seconds() / 60 if active else None
    started_ms = (agent or {}).get("startedAt")
    return {"slug": slug, "project": project_of(slug), "number": session_number(slug), "dir": str(dir_), "run": run,
            "phase": kind, "tone": tone, "kind": kind, "planner": agent if kind == "briefing" else None, "agent": agent,
            "active": active, "quiet_minutes": quiet, "longest_quiet": None,
            "started": datetime.fromtimestamp(started_ms / 1000, tz=timezone.utc) if started_ms else None,
            "touched": active or last_write([str(dir_)]), "events": [], "ledger": ledger_headings(dir_ / "LEDGER.md"),
            "first_action": "", "has_stop_file": False, "has_intake": False,
            "files": sorted(p.name for p in dir_.glob("*.md")) if dir_.is_dir() else []}


def briefing_session(dir_: Path, agents: list) -> dict | None:
    """A session folder with no run.json yet is a brief being written, while its Planner is alive."""
    planner = planner_for(dir_.name, agents)
    if not planner:
        return None
    project = PROJECTS_ROOT / (project_of(dir_.name) or "")
    return pending_session(dir_.name, "briefing", "briefing", {}, dir_, planner, [dir_, project / "Agent Explorations"])


def slug_in(name: str) -> str | None:
    """The session slug a role session's name ends with: `worker-opus-<slug>` → `<slug>`."""
    parts = name.split("-")
    for i in range(1, len(parts)):
        candidate = "-".join(parts[i:])
        project = project_of(candidate)
        if project and session_number(candidate) and (PROJECTS_ROOT / project).is_dir():
            return candidate
    return None


def direct_worktree(slug: str, agent: dict | None, branches: dict) -> str:
    """The worktree a trusted repository lists on `robowright/<slug>`, wherever it is on disk; else the live session's
    cwd, which finds a build on a branch named some other way."""
    found = branches.get(f"robowright/{slug}")
    if found:
        return found[0]
    return agent["cwd"] if agent and agent.get("cwd") else ""


def unit_key(slug: str) -> tuple:
    """A unit is its project and session number; the name after the number is whatever the launching role typed."""
    return project_of(slug), session_number(slug)


def direct_build_agents(agents: list) -> dict:
    """Slug → the live session named for it under any role name but the Planner's and the Lead's; a name that ends in no
    slug is keyed None."""
    role_prefixes = (PLANNER_PREFIX + "-", LEAD_PREFIX + "-")
    return {slug_in(a.get("name") or ""): a for a in agents if not (a.get("name") or "").startswith(role_prefixes)}


def direct_builds(agents: list, known: set, hidden: set) -> list:
    """A direct build has no session folder: it shows as a live session named for its slug, and its records land in
    the project folder's prs/<slug>/. It is finished once prs/<slug>.md, the change description, exists, its session is
    not mid-turn (`shell` too: a background suite still runs), and its worktree has nothing uncommitted; a Worker may
    write the description before it commits.
    Any role name but the Planner's and the Lead's can front one: the Lead names direct builds as it likes. A hidden
    project's prs/ is not listed."""
    named = direct_build_agents(agents)
    workers = {unit_key(slug): a for slug, a in named.items() if slug}
    slugs = {unit_key(slug): slug for slug in named if slug}
    for folder in project_folders():
        prs = folder / "prs"
        if folder.name not in hidden and prs.is_dir():
            for p in prs.iterdir():
                slug = p.name.removesuffix(".md")
                if project_of(slug) == folder.name and session_number(slug):
                    slugs[unit_key(slug)] = slug
    found = []
    listed, branches = listed_worktrees(), listed_branches()
    for key, slug in sorted(slugs.items()):
        if key in known:
            continue
        prs = PROJECTS_ROOT / project_of(slug) / "prs"
        worker = workers.get(key)
        worktree = direct_worktree(slug, worker, branches)
        is_working = (worker or {}).get("status") in ROSTER.RUNNING_STATUSES
        checked = listed_worktree(worktree, listed) if worktree else None
        is_dirty = bool(checked and git(checked[0], "status", "--porcelain", "--ignore-submodules=all"))
        is_published = (prs / f"{slug}.md").exists() and not is_working and not is_dirty
        run = {"worktree": worktree, "phase": "done" if is_published else "working"}
        found.append(pending_session(slug, "direct", "done" if is_published else "working", run, prs / slug,
                                     worker, [prs / slug, worktree]))
    return found


def session_dirs() -> list:
    """(directory, run) for each session directory, its run.json read once: None when it has none, the error when it is
    unreadable."""
    if not SESSIONS_ROOT.is_dir():
        return []
    found = []
    for dir_ in sorted(SESSIONS_ROOT.iterdir()):
        if not dir_.is_dir():
            continue
        if not (dir_ / "run.json").exists():
            found.append((dir_, None))
            continue
        try:
            found.append((dir_, read_run(dir_ / "run.json")))
        except (ValueError, OSError) as err:
            found.append((dir_, err))
    return found


def filed_dir(dir_: Path, run) -> str | None:
    """The project a session directory is filed under; by its name alone when it has no readable run.json."""
    return filed_under(run, dir_.name) if isinstance(run, dict) else project_of(dir_.name)


def archived_projects() -> set:
    """The project folders whose robowright.json archives them, as run-roster.py's is_archived reads it."""
    return {f.name for f in project_folders() if ROSTER.is_archived(project_settings(f))}


def live_projects(dirs: list, agents: list) -> set:
    """Projects with live work: a session directory whose run.json phase is neither `done` nor `parked`, an unreadable
    one included, or a direct build the live-session registry names. Briefing folders, with no run.json, are not."""
    known = {unit_key(dir_.name) for dir_, run in dirs if run is not None}
    live = {filed_dir(dir_, run) for dir_, run in dirs
            if run is not None and not (isinstance(run, dict) and run.get("phase") in ("done", "parked"))}
    return live | {project_of(slug) for slug in direct_build_agents(agents) if slug and unit_key(slug) not in known}


def unreadable_session(dir_: Path, err: Exception) -> dict:
    return {"slug": dir_.name, "project": project_of(dir_.name), "number": session_number(dir_.name),
            "dir": str(dir_), "error": str(err), "tone": "unknown", "touched": None}


def load_sessions(dirs: list, agents: list, hidden: set) -> list:
    """Every session but those filed under a hidden project, which cost nothing past the run.json `dirs` already read."""
    found, known = [], {unit_key(dir_.name) for dir_, run in dirs if run is not None}
    for dir_, run in dirs:
        if filed_dir(dir_, run) in hidden:
            continue
        if run is None:
            pending = briefing_session(dir_, agents)
            if pending:
                found.append(pending)
            continue
        if not isinstance(run, dict):
            found.append(unreadable_session(dir_, run))
            continue
        try:
            found.append(load_session(dir_, run, agents))
        except (ValueError, OSError) as err:
            found.append(unreadable_session(dir_, err))
    builds = direct_builds(agents, known, hidden)
    building = {unit_key(b["slug"]) for b in builds if b["agent"]}
    return [s for s in found if not (s.get("kind") == "briefing" and unit_key(s["slug"]) in building)] + builds


def by_recency(sessions: list) -> list:
    key = lambda s: s.get("touched") or datetime.min.replace(tzinfo=timezone.utc)
    live = [s for s in sessions if s["tone"] not in TERMINAL_TONES]
    rest = [s for s in sessions if s["tone"] in TERMINAL_TONES]
    return sorted(live, key=key, reverse=True) + sorted(rest, key=key, reverse=True)


def default_branch(cwd: str) -> str:
    head = git(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    candidate = head.split("/", 1)[1] if head and "/" in head else "main"
    return candidate if git(cwd, "rev-parse", "--verify", "--quiet", candidate) else "main"


def is_in_main(session: dict, worktree: str) -> bool:
    """Only finished work can be in main; a branch with no commits yet is trivially an ancestor of main."""
    if session["tone"] != "done":
        return False
    run = session["run"]
    main = default_branch(worktree)
    heads = [u.get("head") for u in run.get("units") or [] if u.get("head")]
    branch = f'robowright/{session["slug"]}'
    ref = heads[-1] if heads else branch
    if git(worktree, "merge-base", "--is-ancestor", "--end-of-options", ref, main) is not None:
        return True
    publish = run.get("publish") if isinstance(run.get("publish"), dict) else {}
    return is_squashed_into(worktree, publish.get("tip") or branch, main)


def is_squashed_into(worktree: str, tip: str, main: str) -> bool:
    """An accept's squash (commit-tree onto main, then --ff-only) leaves the tip out of main's history but its tree in it."""
    tree = git(worktree, "rev-parse", "--verify", "--quiet", f"{tip}^{{tree}}")
    trees = git(worktree, "log", "--format=%T", "-n", str(MAIN_TREES_SCANNED), "--end-of-options", main) or ""
    return bool(tree) and tree in trees.split()


def project_repos(project: str | None, trusted: list) -> list | None:
    """The trusted repositories `project`'s robowright.json names, as `trusted` spells them; None when it names none that
    are trusted. A repository it names that `trusted` does not list is never read, so a branch living only there is unseen."""
    if project not in {f.name for f in project_folders()}:
        return None
    entries = project_settings(PROJECTS_ROOT / project).get("repos")
    if not isinstance(entries, list):
        return None
    repos = []
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        repo = next((t for t in trusted if OWNER_GIT.same_dir(t, OWNER_GIT.home_path(path))), None) if isinstance(path, str) else None
        if repo is not None and repo not in repos:
            repos.append(repo)
    return repos or None


def recorded_accept(session: dict) -> str | None:
    """The full commit id a direct build's prs/<slug>/ACCEPTED.json names, which `accept.sh --direct` writes; None when
    the record is missing, unreadable or out of shape, or the slug is not one branch name."""
    if not BRANCH_SLUG.fullmatch(session["slug"]):
        return None
    path = PROJECTS_ROOT / (session["project"] or "") / "prs" / session["slug"] / ACCEPT_RECORD
    data = OWNER_GIT.read_entry(str(path))
    try:
        record = json.loads(data) if data is not None else None
    except (ValueError, RecursionError):
        return None
    sha = record.get("sha") if isinstance(record, dict) else None
    return sha if isinstance(sha, str) and FULL_COMMIT_ID.fullmatch(sha) else None


def patch_id(repo: str, old: str, new: str) -> str | None:
    """`git patch-id --stable` of the diff old..new over its changed lines only, so an edit beside the change leaves it the
    same; read with no attributes, so no textconv or diff driver runs."""
    flags = OWNER_GIT.no_attributes(repo)
    if flags is None:
        return None
    try:
        diff = OWNER_GIT.run(repo, *flags, "diff-tree", "-p", "-U0", "--no-ext-diff", "--no-textconv", "--end-of-options", old, new,
                             timeout=5)
        if diff.returncode != 0:
            return None
        found = subprocess.run(OWNER_GIT.argv(repo, "patch-id", "--stable", timeout=5), input=diff.stdout,
                               capture_output=True, text=True, encoding="utf-8", errors="surrogateescape",
                               env=OWNER_GIT.env(), timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    words = found.stdout.split()
    return words[0] if found.returncode == 0 and words else None


def is_change_of(repo: str, sha: str, branch: str) -> bool:
    """Commit `sha`'s own diff has the patch-id of the branch's diff from where it left `sha`'s parent's history."""
    ref = f"refs/heads/{branch}"
    base = git(repo, "merge-base", "--end-of-options", f"{sha}^", ref)
    ours = patch_id(repo, f"{sha}^", sha)
    return bool(base) and ours is not None and ours == patch_id(repo, base, ref)


def is_accept_recorded(session: dict, trusted: list, verified: dict | None) -> bool:
    """A direct build's accept record names a commit on main in a trusted repository its project names, and while
    `robowright/<slug>` is still in any trusted repository, a commit on that repository's main carrying the branch's
    change. The project folder is session-writable, so the record alone is not evidence; once the branch is gone there is
    nothing left to compare, or to lose."""
    sha = recorded_accept(session)
    if sha and verified is not None and verified.get(session["slug"]) == sha:
        return True
    repos = project_repos(session["project"], trusted) if sha else None
    if repos is None:
        return False
    branch = f'robowright/{session["slug"]}'
    held = {repo: has_branch(repo, branch) for repo in trusted}
    # A repository the project names must answer; another trusted one that cannot is read as not holding the branch.
    if any(held.get(repo) is None for repo in repos):
        return False
    holders = [repo for repo, is_held in held.items() if is_held]
    on_main = [repo for repo in (holders or repos)
               if git(repo, "merge-base", "--is-ancestor", "--end-of-options", sha, default_branch(repo)) is not None]
    is_recorded = any(is_change_of(repo, sha, branch) for repo in on_main) if holders else bool(on_main)
    # Held only when every trusted repository answered: one that could not may hold the branch.
    if is_recorded and verified is not None and None not in held.values():
        verified[session["slug"]] = sha
    return is_recorded


def has_branch(repo: str, branch: str) -> bool | None:
    """Whether a trusted repository holds refs/heads/<branch>; None when git cannot say."""
    try:
        found = OWNER_GIT.run(repo, "rev-parse", "--verify", "--quiet", "--end-of-options", f"refs/heads/{branch}", timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {0: True, 1: False}.get(found.returncode)


def is_branch_in_main(repo: str, branch: str) -> bool:
    """The branch itself, never a tip the session wrote: in the main clone a symbolic tip such as `HEAD` is main."""
    main = default_branch(repo)
    ref = f"refs/heads/{branch}"
    return (git(repo, "merge-base", "--is-ancestor", "--end-of-options", ref, main) is not None
            or is_squashed_into(repo, ref, main))


def has_reached_main(session: dict, listed: dict, trusted: list, verified: dict | None) -> bool:
    """A finished session's branch is in main, read in its listed worktree or in the trusted repository that holds the
    branch; or `robowright/<slug>` is gone from every trusted repository while its project names at least one trusted
    repository and each of those answers, and no worktree of it is left on disk, since teardown deletes the branch only after an accept. A missing
    worktree alone says nothing."""
    worktree = session["run"].get("worktree")
    is_path = isinstance(worktree, str) and bool(worktree)
    checked = listed_worktree(worktree, listed) if is_path else None
    if checked:
        return is_in_main(session, checked[0])
    own = project_repos(session["project"], trusted)
    # Teardown removes the worktree before the branch: one still on disk was never torn down.
    if own is None or (is_path and os.path.isdir(worktree)) or not BRANCH_SLUG.fullmatch(session["slug"]):
        return False
    if verified is not None and verified.get(session["slug"]) == GONE:
        return True
    branch = f'robowright/{session["slug"]}'
    held = {repo: has_branch(repo, branch) for repo in trusted}
    # A repository the project names must answer; another trusted one that cannot is read as not holding the branch.
    if any(held[repo] is None for repo in own):
        return False
    holders = [repo for repo, is_held in held.items() if is_held]
    # Held only when every trusted repository answered: one that could not may hold the branch.
    if not holders and verified is not None and None not in held.values():
        verified[session["slug"]] = GONE
    return any(is_branch_in_main(repo, branch) for repo in holders) if holders else True


def in_main_slugs(sessions: list, verified: dict | None) -> set:
    """In main on positive evidence only: run.json.accepted, a direct build's verified accept record, or
    has_reached_main. Every session branches from main and is accepted on its own, so one session's accept says nothing
    of another's. `verified` is `--serve`'s slug → verified id for the life of the process, positives only; None when one
    refresh is all the process makes."""
    listed, trusted = listed_worktrees(), trusted_repos()
    return {s["slug"] for s in sessions
            if "error" not in s and s["tone"] == "done"
            and (s["run"].get("accepted") or (s.get("kind") == "direct" and is_accept_recorded(s, trusted, verified))
                 or has_reached_main(s, listed, trusted, verified))}


# ---------------------------------------------------------------- plan


def section(text: str, heading: str) -> str | None:
    match = re.search(rf"^## {re.escape(heading)}\b.*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return match.group(1) if match else None


def split_row(line: str) -> list:
    """A Markdown table row's cells as GitHub splits them: `\\|` is a pipe inside a cell, and reads as `|`."""
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return [c.strip().replace("\\|", "|") for c in UNESCAPED_PIPE.split(inner)]


def unit_cell(cell: str) -> str:
    """A Unit cell's text, backticks stripped: the unit's ticket, as run.json.ticket carries it."""
    ticked = re.search(r"`([^`]+)`", cell)
    return (ticked.group(1) if ticked else cell).strip()


def unit_name(cell: str, project: str) -> str:
    """The short name a session slug ends in, from a Unit cell: `teardown` (BASE), `proj-003-text-columns`, `…-wide`.
    The number in a full slug is not used: an earlier session can hold the same number under another name."""
    name = unit_cell(cell)
    full = re.match(rf"^{re.escape(project)}-\w{{3}}-(.+)$", name)
    return full.group(1) if full else re.sub(r"^(…|\.\.\.)-", "", name)


def plan_units(project_md: str, project: str) -> list:
    table = section(project_md, "Task Breakdown")
    if table is None:
        return []
    columns, units = None, []
    for line in table.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = split_row(line)
        if columns is None:
            columns = {c.lower(): i for i, c in enumerate(cells)}
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        get = lambda key: cells[columns[key]] if key in columns and columns[key] < len(cells) else ""
        uid = get("#")
        if not uid:
            continue
        unit = {"id": uid, "row": len(units), "name": unit_name(get("unit"), project), "ticket": unit_cell(get("unit")),
                "desc": get("description"), "repo": get("repo"),
                "purpose": get("summary") or get("description"),
                "size": get("size"), "complexity": get("complexity"), "plan_status": get("status"), "row_error": ""}
        if len(cells) != len(columns):
            # Every cell after the break is shifted, so none of them is trusted.
            unit.update(size="", complexity="", plan_status="",
                        row_error=f"PROJECT.md row has {len(cells)} cells, the header has {len(columns)}")
            if "summary" in columns:
                unit["purpose"] = ""
        units.append(unit)
    ids = {u["id"] for u in units}
    todo = section(project_md, "Detailed TODO") or ""
    stage, order = "", 0
    for line in todo.splitlines():
        if line.startswith("### "):
            stage = line[4:].strip()
        for bold in re.findall(r"\*\*([^*]+?)\*\*", line):
            token = bold.split()[0].rstrip(".:") if bold.split() else ""
            matched = [u for u in units if u["id"] == token] or (
                [u for u in units if u["id"].startswith(token)] if token and token not in ids else [])
            for u in matched:
                if "order" not in u:
                    u["stage"], u["order"] = stage, order
                    order += 1
    for u in units:
        u.setdefault("stage", "unsequenced")
        u.setdefault("order", 10_000)
    return sorted(units, key=lambda u: u["order"])


def owned_session_numbers(status: str) -> set:
    """Session numbers the Status column names as this unit's own: `NNN-slug` inside backticks or **NNN** in
    bold. A bare `008's tip` refers to another unit's session and is left alone."""
    numbers = set()
    for token in re.findall(r"`([^`]+)`", status):
        numbers.update(re.findall(r"(?<![\w])(\d{3})-[a-z]", token))
    numbers.update(re.findall(r"\*\*(\d{3})\b", status))
    return numbers


def ticket_claims(units: list, sessions: list) -> dict:
    """Slug → the first row, in table order, whose Unit cell equals the session's unit id (ticket_of)."""
    claims = {}
    for u in sorted(units, key=lambda u: u["row"]):
        for s in sessions:
            if u["ticket"] and ticket_of(s) == u["ticket"]:
                claims.setdefault(s["slug"], u)
    return claims


def sessions_for(unit: dict, project: str, sessions: list, ticketed: dict) -> list:
    """A row's ticket claim is the row's alone; the name rules read only the sessions no row claimed by ticket."""
    owned = owned_session_numbers(unit["plan_status"])
    found = []
    for s in sessions:
        if s["slug"] in ticketed:
            if ticketed[s["slug"]] is unit:
                found.append(s)
            continue
        rest = re.sub(r"^\d{3}-", "", s["slug"][len(project) + 1:])
        if rest == unit["name"] or s["number"] in owned:
            found.append(s)
    return sorted(found, key=lambda s: s["slug"])


def unit_progress(unit: dict, sessions: list, in_main: set) -> None:
    if not sessions:
        unit["fraction"] = 0.0
        status = unit["plan_status"].lower().lstrip("*_ ")
        unit["tone"] = ("complete" if status.startswith(("done", "accepted")) else
                        "briefed" if status.startswith("briefed") else
                        "parked" if status.startswith("parked") else
                        "settled" if status.startswith(("closed", "moved")) else "todo")
        if unit["tone"] == "complete":
            unit["fraction"] = 1.0
        return
    fractions, tones = [], []
    for s in sessions:
        if "error" in s:
            fractions.append(0.0)
            tones.append("stopped")
            continue
        run_units = s["run"].get("units") or []
        done = sum(1 for x in run_units if x.get("status") == "done")
        is_finished = s["tone"] in TERMINAL_TONES or s["tone"] == "intake"
        fractions.append(1.0 if is_finished else (done / len(run_units) if run_units else 0.0))
        tones.append("complete" if s["slug"] in in_main else "built" if s["tone"] == "done" else s["tone"])
    unit["fraction"] = sum(fractions) / len(fractions)
    unit["tone"] = next((t for t in PLAN_TONES if t in tones), "working")


OWNER_BRIEF_SUFFIXES = ("-owner-brief.md", "-review-guide.md")


def project_settings(folder: Path) -> dict:
    """`folder`'s robowright.json, which a session can make a link or a FIFO, read without following or waiting on
    either; `{}` when it is refused or unreadable."""
    try:
        return json.loads(OWNER_GIT.read_unlinked(os.path.join(os.path.realpath(folder.parent), folder.name,
                                                               "robowright.json")))
    except (OSError, ValueError, RecursionError, OWNER_GIT.Unreadable):
        return {}


def lead_stage(session: dict, folder: Path, wants_guide: bool) -> str | None:
    """The Lead step a finished session still waits on before it is the Owner's, or None once it is.
    A direct build leaves no intake or brief to read, so it stays the Lead's until it is accepted."""
    if session.get("kind") == "direct":
        return "check"
    if not session["has_intake"]:
        return "intake"
    if session.get("explainer"):
        return "owner brief"
    guides = [folder / OWNER_BRIEF_DIR / f'{session["slug"]}{suffix}' for suffix in OWNER_BRIEF_SUFFIXES]
    if wants_guide and not any(g.exists() for g in guides):
        return "review guide"
    return None


def hold_for_lead(sessions: list, folder: Path, in_main: set) -> None:
    """A finished session is the Lead's until its intake, and its owner brief where robowright.json asks for one,
    exist. Work in main is past that already, whatever its record says."""
    settings = project_settings(folder)
    wants_guide = bool(settings.get("owner_brief", settings.get("review_guide")))
    for s in sessions:
        if s.get("tone") != "done" or s["slug"] in in_main:
            continue
        stage = lead_stage(s, folder, wants_guide)
        if stage:
            s["tone"], s["lead_stage"] = "intake", stage


def read_ledger() -> list | None:
    """Every record of the accounting ledger, or None when there is no accounting root or no records file."""
    if not ACCOUNTING_ROOT:
        return None
    path = Path(ACCOUNTING_ROOT) / "records.jsonl"
    if not path.is_file():
        return None
    return COST_ROLLUP.read_records(path)


def ticket_of(session: dict) -> str:
    """The unit id, as the launcher reads it: run.json.ticket (held_run keeps only a string), else the session's slug."""
    return (session.get("run") or {}).get("ticket") or session["slug"]


def budgets_in_dollars(run: dict) -> bool:
    """run-roster.py's usage_cell rule: a brief that sets neither dollar limit runs under a budget not measured in dollars."""
    return ROSTER.number(run.get("spend_threshold_usd")) is not None or ROSTER.number(run.get("spend_cap_usd")) is not None


def spend_of(ledger: list, tickets: set, priced: bool) -> dict | None:
    """The rollup's figures over the session-scope records of these tickets, or None when there are none."""
    records = [{**r, "project": ""} for r in ledger if r.get("unit") in tickets]
    rows = COST_ROLLUP.rollup(records, "project", priced)
    return rows[0] if rows else None


def project_spend(ledger: list, project: str, priced: bool) -> dict | None:
    """The rollup's row for this project, as `robowright-cost.py --by project` prints it, or None when it has none."""
    return next((row for row in COST_ROLLUP.rollup(ledger, "project", priced) if row["key"] == project), None)


def decide_now_asks(path: Path) -> list | None:
    """The asks under an owner brief's `## Decide now`: each table body row's first cell and each `- ` bullet,
    except the template's "Nothing" answer. None when there is no brief."""
    try:
        text = path.read_text()
    except OSError:
        return None
    asks, is_body = [], False
    for line in (section(text, "Decide now") or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            asks.append(stripped[2:].strip())
        elif stripped.startswith("|"):
            cells = split_row(stripped)
            if set("".join(cells)) <= set("-: "):
                is_body = True
            elif is_body and cells[0]:
                asks.append(cells[0])
        else:
            is_body = False
    return [a for a in asks if a.lower().removesuffix(".") not in ("nothing", "none")]


def load_project(folder: Path, all_sessions: list, in_main: set, ledger: list | None, priced: bool, is_archived: bool) -> dict:
    name = folder.name
    text = (folder / "PROJECT.md").read_text()
    sessions = [s for s in all_sessions if s["project"] == name]
    hold_for_lead(sessions, folder, in_main)
    for s in sessions:
        s["spend"] = spend_of(ledger, {ticket_of(s)}, priced) if ledger is not None and ticket_of(s) else None
        if s.get("phase") == "done":
            s["asks"] = decide_now_asks(folder / OWNER_BRIEF_DIR / f'{s["slug"]}-owner-brief.md')
    units = plan_units(text, name)
    ticketed = ticket_claims(units, sessions)
    claimed, hours_per_point = set(), []
    for u in units:
        own = sessions_for(u, name, sessions, ticketed)
        claimed.update(s["slug"] for s in own)
        u["sessions"] = own
        for s in own:
            s["purpose"] = plain(u["purpose"])
        unit_progress(u, own, in_main)
        points_each = weight(u) / max(len(own), 1)
        for s in own:
            if s.get("tone") in ("done", "intake") and s.get("started") and s.get("touched"):
                hours_per_point.append((s["touched"] - s["started"]).total_seconds() / 3600 / points_each)
    # A closed or moved unit was never this plan's to deliver: it weighs nothing.
    total = sum(weight(u) for u in units if u["tone"] != "settled")
    earned = sum(weight(u) * u["fraction"] for u in units)
    complete_points = sum(weight(u) for u in units if u["tone"] == "complete")
    rate = sum(hours_per_point) / len(hours_per_point) if hours_per_point else None
    touched = [s["touched"] for s in sessions if s.get("touched")]
    mtime = datetime.fromtimestamp((folder / "PROJECT.md").stat().st_mtime, tz=timezone.utc)
    return {
        "name": name, "folder": str(folder), "archived": is_archived, "units": units, "sessions": by_recency(sessions),
        "unplanned": [s for s in by_recency(sessions) if s["slug"] not in claimed],
        "percent": 100 * earned / total if total else 0, "complete_percent": 100 * complete_points / total if total else 0,
        "points_total": total, "points_earned": earned, "points_complete": complete_points,
        "hours_left": (total - earned) * rate if rate else None, "measured_sessions": len(hours_per_point),
        "live": [s for s in sessions if s["tone"] not in TERMINAL_TONES],
        "touched": max(touched + [mtime]),
        "has_ledger": ledger is not None,
        "spend": project_spend(ledger, name, priced) if ledger is not None else None,
        "in_dollars": bool(sessions) and all(budgets_in_dollars(s.get("run") or {}) for s in sessions),
    }


def project_folders() -> list:
    if not PROJECTS_ROOT.is_dir():
        return []
    return sorted(p for p in PROJECTS_ROOT.iterdir() if (p / "PROJECT.md").is_file())


def load_world(only: str | None, shows_archived: bool, verified: dict | None) -> tuple[list, list]:
    """Every project, or `only`; an archived one with no live work, and its sessions, left out unless `shows_archived`."""
    agents, dirs, archived = live_agents(), session_dirs(), archived_projects()
    hidden = set() if shows_archived else archived - live_projects(dirs, agents)
    sessions = load_sessions(dirs, agents, hidden)
    in_main = in_main_slugs(sessions, verified)
    ledger = read_ledger()
    priced = ledger is not None and COST_ROLLUP.load_prices().as_of is not None
    projects = [load_project(f, sessions, in_main, ledger, priced, f.name in archived) for f in project_folders()
                if only in (None, f.name) and f.name not in hidden]
    known = {p.name for p in project_folders()}
    orphans = by_recency([s for s in sessions if s["project"] not in known])
    projects.sort(key=lambda p: (not p["live"], -p["touched"].timestamp()))
    return projects, orphans


# ---------------------------------------------------------------- terminal


def text_summary(projects: list, orphans: list, detailed: bool) -> str:
    lines = []
    for p in projects:
        counts = {}
        for u in p["units"]:
            counts[u["tone"]] = counts.get(u["tone"], 0) + 1
        tally = ", ".join(f"{counts[t]} {PLAN_LABEL[t]}" for t in LEGEND_ORDER if t in counts) or "no Task Breakdown"
        name = f"{p['name']} (archived)" if p["archived"] else p["name"]
        head = f"{name}: {p['percent']:.0f}% built, {p['complete_percent']:.0f}% complete" if p["units"] else name
        lines.append(f"{head} · {tally} · touched {ago(p['touched'])}")
        for s in p["live"]:
            stop = (s["run"].get("stop_reason") or {}) if "error" not in s else {}
            code = stop.get("code") if isinstance(stop, dict) else stop
            lines.append(f"    {s['slug']}  {s.get('phase', '?')}{'  · ' + code if code else ''}  · {ago(s['touched'])}")
        if detailed:
            for u in p["units"]:
                numbers = " ".join(s["number"] for s in u["sessions"] if s["number"])
                lines.append(f"    {u['id']:<10} {u['name'][:34]:<34} {u['size']:<3} {PLAN_LABEL[u['tone']]}"
                             f"{' · ' + numbers if numbers else ''}")
                if u["purpose"]:
                    lines.append(f"               {plain(u['purpose'])}")
            for s in p["unplanned"]:
                lines.append(f"    (unplanned) {s['slug']}  {s.get('phase', '?')}")
    if orphans:
        lines.append(f"no project folder: {', '.join(s['slug'] for s in orphans)}")
    # Every line carries session-written text: no control byte of it reaches the Owner's terminal.
    return "\n".join(OWNER_GIT.shown(line) for line in lines)


# ---------------------------------------------------------------- html


# Every tone maps to one of five dot styles: attention (red), running (blue, pulsing), queued (blue ring),
# built (green ring), complete (green), idle (grey).
STATE = {
    "stopped": ("attn", "Stopped"), "unknown": ("attn", "Unreadable"),
    "working": ("run", "Working"), "rotating": ("run", "Handing off"),
    "rebriefing": ("run", "Planner rebriefing"), "briefing": ("run", "Planner briefing"), "owner-call": ("attn", "Rebrief needs your call"),
    "briefed": ("queued", "Briefed"),
    "built": ("built", "Awaiting acceptance"), "intake": ("intake", "With the Lead"), "complete": ("complete", "Complete"), "done": ("complete", "Done"),
    "parked": ("idle", "Parked"), "settled": ("idle", "Closed or moved"), "todo": ("idle", "Not started"),
}
RUN_UNIT_DOT = {"done": "complete", "building": "run", "gated": "run", "held": "run", "todo": "idle"}
UNIT_PHRASE = {"building": "building", "gated": "passed review, closing", "done": "done", "todo": "not started"}
PHASE_PHRASE = {"intake": "reading the brief", "end-of-stack": "final review of the whole change",
                "awaiting-rotation": "handing off to a fresh session"}
EVENT_PHRASE = {
    "preflight-pass": "preflight passed", "intake-complete": "read the brief", "unit-start": "started",
    "gate-hold": "review asked for changes", "gate-advance": "passed review", "unit-close": "closed",
    "begin-end-of-stack": "final review of the whole change started", "finish": "finished",
    "request-rotate": "asked for a fresh session", "rotation-resumed": "picked up by a fresh session",
    "stop": "stopped", "resume": "resumed", "park": "parked", "rebrief": "rebriefed", "accept": "accepted",
}
# A crew member's doing phrase, at most about 18 characters to fit its column.
TONE_DOING = {"briefed": "ready to launch", "rotating": "handing off", "briefing": "writing the brief", "rebriefing": "rebriefing"}
LEAD_STAGE_DOING = {"intake": "Lead's intake", "check": "Lead's check", "review guide": "owner brief", "owner brief": "owner brief"}
PHASE_DOING = {"intake": "reading the brief", "end-of-stack": "final review"}
UNIT_DOING = {"building": "building", "gated": "closing", "held": "review notes"}
CREW_CAPS = (6, 4, 3)  # figures shown above 780 px, at 780 px or less, at 640 px or less
DETAIL_CHARS = 180
FINISHED_OPEN_MAX = 5
# Characters a plan row's one-line face holds at its narrowest (just over 560 px); a longer Summary is repeated inside.
SUMMARY_FACE_CHARS = 45
# One wording on the index and the project page: the reading is the account's, never one project's.
PLAN_USAGE_LABEL = "Plan usage, all projects"
PLAN_USAGE_TITLE = "The Claude plan's usage across every session, on every project"

# Cyanotype: one family, three themes. The note tokens paint the pinned paper that needs-you items sit on.
THEMES = {
    "whiteprint": {"bg": "#F4F7FA", "surface": "#FFFFFF", "fg": "#12325A", "muted": "#52698A", "faint": "#7C91AC",
                   "line": "#D3DEEA", "track": "#DAE4EE", "done": "#3E8C83", "run": "#3B7CC4", "attn": "#D8612E",
                   "attn-text": "#B24A1C", "attn-bg": "#FCEDE4", "attn-line": "#F2D3C2", "idle": "#BFCCDB",
                   "brand": "#12325A", "brass": "#A87300", "grid": "#E6EDF4",
                   "note-bg": "#FCEDE4", "note-line": "#F2D3C2", "note-hover": "#F8E2D5", "note-fg": "#12325A",
                   "note-muted": "#6B5A55", "note-faint": "#8F7B73", "note-attn": "#B24A1C", "note-run": "#3B7CC4",
                   "note-done": "#2F7F76", "note-brass": "#A87300"},
    "blueprint": {"bg": "#123A66", "surface": "#164676", "fg": "#EAF2FB", "muted": "#A9C1DC", "faint": "#86A5C8",
                  "line": "#2C5A8A", "track": "#2A5585", "done": "#7FD1B9", "run": "#9CCBF2", "attn": "#FF9A66",
                  "attn-text": "#FFB48C", "attn-bg": "#FCEBDD", "attn-line": "#EFCDB2", "idle": "#46729F",
                  "brand": "#FFFFFF", "brass": "#F2C14E", "grid": "#1B4674",
                  "note-bg": "#FCEBDD", "note-line": "#EFCDB2", "note-hover": "#F7DFCB", "note-fg": "#1B2F4A",
                  "note-muted": "#6B5A55", "note-faint": "#8F7B73", "note-attn": "#B04A1C", "note-run": "#2F6DB0",
                  "note-done": "#2A7A6E", "note-brass": "#A87300"},
    "night": {"bg": "#0B1624", "surface": "#111F31", "fg": "#D6E2EF", "muted": "#8FA3BA", "faint": "#6C829B",
              "line": "#1E3048", "track": "#1E3048", "done": "#5FB8A3", "run": "#7BAFE0", "attn": "#F08A5D",
              "attn-text": "#F4A07A", "attn-bg": "#33231F", "attn-line": "#5A3528", "idle": "#2E4460",
              "brand": "#BFD6F2", "brass": "#F2C14E", "grid": "#0F1C2D",
              "note-bg": "#33231F", "note-line": "#5A3528", "note-hover": "#3C2A25", "note-fg": "#EBD9D0",
              "note-muted": "#B89A8E", "note-faint": "#957B70", "note-attn": "#F4A07A", "note-run": "#7BAFE0",
              "note-done": "#5FB8A3", "note-brass": "#F2C14E"},
}
THEME_SCHEME = {"whiteprint": "light", "blueprint": "dark", "night": "dark"}
# With no saved pick the page follows the system: light gets Whiteprint, dark gets Blueprint.
SYSTEM_DARK_THEME = "blueprint"
THEME_KEY = "robowright-theme"


def theme_vars(name: str) -> str:
    return ";".join(f"--{k}:{v}" for k, v in THEMES[name].items()) + f";color-scheme:{THEME_SCHEME[name]}"


THEME_CSS = (f":root{{{theme_vars('whiteprint')}}}"
             f"@media (prefers-color-scheme:dark){{:root:not([data-theme]){{{theme_vars(SYSTEM_DARK_THEME)}}}}}"
             + "".join(f":root[data-theme={name}]{{{theme_vars(name)}}}" for name in THEMES))
# Runs in <head>, before first paint, so a saved theme never flashes the default.
THEME_BOOT = f"try{{const t=localStorage.getItem('{THEME_KEY}');if(t)document.documentElement.dataset.theme=t}}catch(_){{}}"
# U26's robot mark, from assets/logo-mark-*.svg; its ring is unfilled so the page shows through.
MARK = ('<svg class="mark" xmlns="http://www.w3.org/2000/svg" viewBox="-104 -104 208 208" aria-hidden="true">'
        '<circle r="96" fill="none" stroke="currentColor" stroke-width="11"/>'
        '<g transform="translate(0 14) scale(1.7)">'
        '<rect x="-32" y="-22" width="64" height="54" rx="18" fill="none" stroke="currentColor" stroke-width="6.2"/>'
        '<path d="M0 -22V-37" fill="none" stroke="currentColor" stroke-width="6.2" stroke-linecap="round"/>'
        '<rect x="-4" y="-52" width="8" height="13" rx="1.5" style="fill:var(--brass)"/>'
        '<ellipse cx="-13" cy="3" rx="6.5" ry="9.5" fill="currentColor"/>'
        '<ellipse cx="13" cy="3" rx="6.5" ry="9.5" fill="currentColor"/>'
        '<path d="M-35 -10C-39 -10 -40 -8 -40 -4L-40 0C-40 4 -42 5 -46 5C-42 5 -40 6 -40 10L-40 14C-40 18 -39 20 -35 20" '
        'fill="none" style="stroke:var(--brass)" stroke-width="6.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M35 -10C39 -10 40 -8 40 -4L40 0C40 4 42 5 46 5C42 5 40 6 40 10L40 14C40 18 39 20 35 20" '
        'fill="none" style="stroke:var(--brass)" stroke-width="6.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '</g></svg>')
# The tab icon has no page CSS to resolve against, so it takes Whiteprint's ink as fixed colours.
FAVICON = "data:image/svg+xml," + quote(MARK.replace("currentColor", THEMES["whiteprint"]["brand"])
                                        .replace("var(--brass)", THEMES["whiteprint"]["brass"]))

# The crew's figures, drawn from the clone's own assets/ at start: the art's light inks become the page's tokens.
ART_LINE, ART_BRASS, ART_PAPER, ART_GRID = "#12325A", "#A87300", "#F4F7FA", "#D3DEEA"
HERO_INKS = {ART_LINE: "currentColor", ART_BRASS: "var(--brass)", ART_PAPER: "var(--bg)", ART_GRID: "var(--line)"}
STAMP_INKS = {ART_LINE: "currentColor", ART_BRASS: "var(--stamp-accent)", ART_PAPER: "none"}
# The hero's sheet cropped 18 units in from each edge, so the page grid meets the sheet's frame (drawn at 20).
HERO_BOX, STAMP_BOX = "18 18 1164 684", "-104 -104 208 208"
ART_PAINT = re.compile(r' (fill|stroke)="(#[0-9A-Fa-f]{6})"')
DRAWN_ROLES = ("worker", "lead", "planner", "reviewer")
GLYPH_HEAD_STROKE, GLYPH_BRACE_STROKE = "5", "6.6"
PROP_GROUP = '<g transform="translate(50 10)'
GLYPH_PROP_GROUP = '<g transform="translate(50 10) scale(1.35) translate(-50 -10)">'
# The crew's props stand on the ground at the hero's scale, shifted as the hero's Workers are.
CREW_PROP_GROUP = '<g transform="translate(-7 0)">'
ART_EYE = re.compile(r'<ellipse cx="(-?13)" cy="3" rx="6.5" ry="9.5"')
DOZING_EYE = r'<ellipse cx="\1" cy="6" rx="7" ry="1.8"'
OWNER_GROUP, OWNER_BULB = '<g transform="translate(84 600)">', '<path d="M0 -132V-122"'
# The row Owner's eyes, smile and collar: under 1 px at 30 px tall.
OWNER_FACE = re.compile(r'<(?:circle|path)\b[^>]*?(?: r="2\.4"| d="M-5 -106Q| d="M-6 -92L)[^>]*/>')
ROW_ROBOT_BOX, ROW_ROBOT_PX, OWNER_BOX, ROW_OWNER_PX = (-50, -54, 154, 100), 28, (-26, -137, 64, 135.1), 30
ROW_HEAD_STROKE, ROW_BRACE_STROKE, ROW_PROP_SCALE, ROW_OWNER_SCALE = 6.0, 8.4, 1.2, 2.3
CREW_ROBOT_BOX, CREW_ROBOT_PX, CREW_OWNER_PX = (-50, -54, 136, 90), 52, 70
CREW_HEAD_STROKE, CREW_BRACE_STROKE, CREW_OWNER_SCALE = 3.5, 4.9, 1.2
CREW_PROP_SCALE = CREW_HEAD_STROKE / float(GLYPH_HEAD_STROKE) * 1.35


def read_art(relative: str) -> str:
    """A file under the clone's assets/, or '' when it is missing or unreadable: the page then draws no figure."""
    try:
        return (CLONE / "assets" / relative).read_text()
    except (OSError, UnicodeDecodeError):
        return ""


def repainted(tag: str, inks: dict) -> str:
    """One element's tag with each art ink swapped for its token. A var() paint goes in `style`, as MARK's do:
    var() in a presentation attribute does not resolve in every browser."""
    styles = []
    for prop, ink in ART_PAINT.findall(tag):
        token = inks.get(ink.upper(), ink)
        is_var = token.startswith("var(")
        tag = tag.replace(f' {prop}="{ink}"', "" if is_var else f' {prop}="{token}"', 1)
        if is_var:
            styles.append(f"{prop}:{token}")
    if not styles:
        return tag
    end = -2 if tag.endswith("/>") else -1
    return tag[:end] + ' style="' + ";".join(styles) + '"' + tag[end:]


def inked(art: str, inks: dict) -> str:
    return re.sub(r"<[a-z]+\b[^>]*>", lambda tag: repainted(tag.group(0), inks), art)


def scaled_strokes(art: str, factor: float) -> str:
    return re.sub(r'stroke-width="([\d.]+)"', lambda width: f'stroke-width="{round(float(width.group(1)) * factor, 2):g}"', art)


def robot_drawing(art: str, head: float, braces: float, prop_scale: float, prop_group: str) -> str:
    """A role glyph's inner group re-stroked for its size, its prop group's opening tag replaced by `prop_group`; the
    outer group, tile and grid are dropped. '' when the art has no such group."""
    try:
        start = art.index("<g transform")
        body = art[art.index(">", start) + 1:art.rindex("</g>")]
        props = body.index(PROP_GROUP)
    except ValueError:
        return ""
    face = (body[:props].replace(f'stroke-width="{GLYPH_HEAD_STROKE}"', f'stroke-width="{head:g}"')
            .replace(f'stroke-width="{GLYPH_BRACE_STROKE}"', f'stroke-width="{braces:g}"'))
    prop = scaled_strokes(body[props:], prop_scale)
    prop = prop_group + prop[prop.index(">") + 1:]
    return inked(face + prop, {ART_LINE: "currentColor", ART_BRASS: "var(--brass)"})


def owner_drawing(hero: str, stroke_scale: float, has_face: bool) -> str:
    """The hero's Owner up to its light bulb, strokes scaled, paper fills becoming `var(--fig-fill)`; '' when the hero has none."""
    try:
        start = hero.index(OWNER_GROUP) + len(OWNER_GROUP)
        body = hero[start:hero.index(OWNER_BULB, start)]
    except ValueError:
        return ""
    if not has_face:
        body = OWNER_FACE.sub("", body)
    return inked(scaled_strokes(body, stroke_scale),
                 {ART_LINE: "currentColor", ART_BRASS: "var(--brass)", ART_PAPER: "var(--fig-fill)"})


def figure(drawing: str, box: tuple, px: int) -> str:
    """An inline SVG of a drawing, `px` tall and hidden from screen readers; '' when there is nothing to draw."""
    if not drawing:
        return ""
    view_box = " ".join(f"{n:g}" for n in box)
    return (f'<svg class="fig" viewBox="{view_box}" width="{box[2] * px / box[3]:.0f}" height="{px}" '
            f'aria-hidden="true" focusable="false">{drawing}</svg>')


def sheet(art: str, css_class: str, view_box: str, inks: dict) -> str:
    """A whole asset in an <svg> of the page's own, inked, hidden from screen readers; '' when there is no art."""
    try:
        inside = art[art.index(">", art.index("<svg")) + 1:art.rindex("</svg>")]
    except ValueError:
        return ""
    return (f'<svg class="{css_class}" viewBox="{view_box}" aria-hidden="true" focusable="false">'
            f'{inked(inside, inks)}</svg>')


HERO_ART = read_art("hero-light.svg")
HERO = sheet(HERO_ART, "hero-art", HERO_BOX, HERO_INKS)
STAMP = sheet(read_art("logo-light.svg"), "stamp", STAMP_BOX, STAMP_INKS)
ROLE_ART = {role: read_art(f"roles/{role}-light.svg") for role in DRAWN_ROLES}
ROW_GLYPHS = {"owner": figure(owner_drawing(HERO_ART, ROW_OWNER_SCALE, has_face=False), OWNER_BOX, ROW_OWNER_PX),
              **{role: figure(robot_drawing(art, ROW_HEAD_STROKE, ROW_BRACE_STROKE, ROW_PROP_SCALE, GLYPH_PROP_GROUP),
                              ROW_ROBOT_BOX, ROW_ROBOT_PX) for role, art in ROLE_ART.items()}}
CREW_ROBOTS = {role: robot_drawing(art, CREW_HEAD_STROKE, CREW_BRACE_STROKE, CREW_PROP_SCALE, CREW_PROP_GROUP)
               for role, art in ROLE_ART.items()}
CREW_FIGURES = {"owner": figure(owner_drawing(HERO_ART, CREW_OWNER_SCALE, has_face=True), OWNER_BOX, CREW_OWNER_PX),
                **{role: figure(drawing, CREW_ROBOT_BOX, CREW_ROBOT_PX) for role, drawing in CREW_ROBOTS.items()}}
DOZING_WORKER = figure(ART_EYE.sub(DOZING_EYE, CREW_ROBOTS["worker"]), CREW_ROBOT_BOX, CREW_ROBOT_PX)

THEME_PICKER = ('<div class="themes" id="themes" role="group" aria-label="Theme">'
                + "".join(f'<button type="button" data-pick="{name}" aria-pressed="false">{name.title()}</button>' for name in THEMES)
                + "</div>")

CSS = """
*{box-sizing:border-box}
body{margin:0;background-color:var(--bg);background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);background-size:24px 24px;color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Inter","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding:28px 16px 48px}
a{color:inherit;text-decoration:none}
.mono,.brand{font-family:ui-monospace,"SF Mono",Menlo,monospace}.mono{font-size:.87em}
.muted{color:var(--muted)}
nav{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:13px;color:var(--muted);margin-bottom:28px}
.crumbs{display:flex;align-items:center;gap:8px;min-width:0}
a.row:hover,.plan-stage .row:hover{background:var(--bg)}
.notify{font:inherit;font-size:13px;color:var(--muted);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:4px 12px;cursor:pointer}
.notify:hover:enabled{color:var(--fg);border-color:var(--faint)}.notify:disabled{cursor:default}.notify[hidden]{display:none}
.flag{color:var(--attn-text)}
.brand{display:inline-flex;align-items:center;gap:7px;color:var(--brand);font-weight:600;letter-spacing:.01em}.mark{width:18px;height:18px}
.tools{display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:8px 10px}.notify{white-space:nowrap}
.themes{display:flex;border:1px solid var(--line);border-radius:999px;background:var(--surface);padding:2px}
.themes button{font:inherit;font-size:12px;color:var(--muted);background:none;border:0;border-radius:999px;padding:3px 10px;cursor:pointer}
.themes button:hover{color:var(--fg)}.themes button[aria-pressed=true]{background:var(--fg);color:var(--surface)}
#attention .list,.callout:not(.calm),.alert:not(.awaiting){--fg:var(--note-fg);--muted:var(--note-muted);--faint:var(--note-faint);--line:var(--note-line);--bg:var(--note-hover);--attn:var(--note-attn);--attn-text:var(--note-attn);--run:var(--note-run);--done:var(--note-done);background:var(--note-bg);border-color:var(--note-line);color:var(--fg)}
#attention .list{--brass:var(--note-brass)}
nav a:hover{color:var(--fg)}nav .here{color:var(--fg)}
h1{font-size:28px;font-weight:600;letter-spacing:-.02em;margin:0}
h2{font-size:13px;font-weight:500;color:var(--muted);margin:40px 0 12px}
footer{margin-top:48px;font-size:12px;color:var(--muted);line-height:1.7;display:flex;align-items:center;gap:12px;--stamp-accent:color-mix(in srgb,var(--brass) 85%,var(--bg))}
.stamp{width:48px;height:48px;color:var(--faint);flex:none}
.empty{text-align:center}.empty p{margin:0;font-size:15px}.empty p+p{margin-top:4px;font-size:13px;color:var(--muted)}.empty p.where{margin-top:10px;font-size:12px}
.hero-art{display:block;width:100%;max-width:760px;height:auto;margin:28px auto 18px;color:var(--fg)}

.dot{display:inline-block;flex:none;width:8px;height:8px;border-radius:50%;background:var(--idle)}
.dot.attn{background:var(--attn)}.dot.run{background:var(--run);animation:pulse 2s ease-in-out infinite}
.dot.queued{background:none;box-shadow:inset 0 0 0 1.5px var(--run)}.dot.built{background:color-mix(in srgb,var(--done) 40%,var(--track));box-shadow:inset 0 0 0 1.5px var(--done)}
.dot.complete{background:var(--done)}.dot.idle{background:var(--idle)}
@keyframes pulse{50%{opacity:.35}}@media (prefers-reduced-motion:reduce){.dot.run{animation:none}}

.track{display:flex;gap:2px;height:8px;border-radius:4px;overflow:hidden}
.track .seg{transition:opacity .12s}.track:hover .seg:not(:hover){opacity:.4}.track .seg[data-tip]{cursor:default}
.tip{position:fixed;z-index:20;pointer-events:none;max-width:min(420px,calc(100vw - 16px));padding:5px 9px;border-radius:6px;background:var(--fg);color:var(--surface);font-size:12px;line-height:1.35;box-shadow:0 2px 8px rgba(0,0,0,.18)}.tip[hidden]{display:none}
.track.big{height:12px;border-radius:6px}
.seg{background:var(--track)}.seg.attn{background:var(--attn)}.seg.run{background:var(--run)}
.seg.queued{background:color-mix(in srgb,var(--run) 35%,var(--track))}.seg.built{background:color-mix(in srgb,var(--done) 40%,var(--track))}
.seg.complete{background:var(--done)}
.seg.intake,.dot.intake{background:repeating-linear-gradient(135deg,color-mix(in srgb,var(--done) 70%,var(--track)) 0 2px,var(--track) 2px 4px)}.dot.intake{box-shadow:inset 0 0 0 1.5px var(--done)}
.tally{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;color:var(--muted)}
.tally span{display:inline-flex;align-items:center;gap:6px}.key{display:inline-block;flex:none;width:14px;height:8px;border-radius:2px}

.attn-head{color:var(--attn-text)}
.alert.awaiting{background:var(--surface);border-color:var(--line)}
.alert{display:flex;gap:12px;align-items:baseline;padding:14px 16px;border-radius:12px;background:var(--attn-bg);border:1px solid var(--attn-line)}
.alert b{font-weight:600}.alert .why{font-size:13px;color:var(--muted);margin-top:2px}

.projects{display:grid;gap:10px}
.proj{display:block;padding:18px 20px;background:var(--surface);border:1px solid var(--line);border-radius:14px;transition:border-color .15s}
.proj:hover{border-color:var(--faint)}
.proj-head,.hero-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:12px}
.proj-name{font-weight:600;font-size:15px}
.pct{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}.pct small{font-size:13px;font-weight:400;color:var(--muted);margin-left:4px}
.proj .tally{margin-top:12px}
.hero .pct{font-size:28px;letter-spacing:-.02em}.hero .tally{margin-top:14px}.hero p{font-size:13px;color:var(--muted);margin:10px 0 0}

.list{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.subhead{padding:12px 20px 6px;font-size:12px;color:var(--muted);border-top:1px solid var(--line)}
.subhead:first-child{border-top:0}.subhead b{font-weight:600;color:var(--fg);margin-right:6px}
.plan-stage>summary.stage-head{display:block;cursor:pointer;list-style:none;border-top:1px solid var(--line)}.plan-stage:first-child>summary.stage-head{border-top:0}.plan-stage>summary::-webkit-details-marker{display:none}.plan-stage>summary.stage-head::after{content:" ▸";font-size:11px}.plan-stage[open]>summary.stage-head::after{content:" ▾"}.plan-stage:not([open])>summary.stage-head{padding-bottom:12px}.stage-head .count{margin-left:6px}
.row{display:flex;align-items:center;gap:12px;padding:10px 20px}
.row .id{min-width:2.4em;color:var(--muted);font-variant-numeric:tabular-nums}
.row .main{flex:1;min-width:0}.row .name{font-weight:500}
.fig{display:block;color:var(--fg)}

.crew-card{--stage:74px;--hatch:color-mix(in srgb,var(--fg) 32%,var(--surface));--fig-fill:var(--surface);position:relative;background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;padding-top:16px}
.crew-card::before{content:"";position:absolute;left:0;right:0;top:calc(16px + var(--stage));height:8px;border-top:2px solid var(--fg);background:repeating-linear-gradient(-45deg,transparent 0 7px,var(--hatch) 7px 8.4px)}
.crew{list-style:none;margin:0;padding:0 8px;display:flex;justify-content:center}
.crew li{flex:0 1 136px;min-width:0}
.crew li.owner{flex-basis:116px}
.crew li.more{flex:0 0 96px}
.crew-card.quiet li{flex-basis:auto}
.member{display:flex;flex-direction:column;align-items:center;text-align:center;color:var(--fg);padding:0 4px 14px;border-radius:10px}
.crew-card.quiet .member{padding-bottom:16px}
.member .stage{height:var(--stage);display:flex;align-items:flex-end;justify-content:center}
.member .labels{margin-top:20px;max-width:100%;display:flex;flex-direction:column;font-size:12px;line-height:16px}
.member .labels>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.member .who{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-weight:500;color:var(--fg)}
.member .what,.member .where{color:var(--muted)}
a.member:hover .who{text-decoration:underline;text-decoration-color:var(--faint);text-underline-offset:3px}
a.member:focus-visible{outline:2px solid var(--run);outline-offset:-2px}
.ghost{width:40px;height:34px;border:2px dashed var(--faint);border-radius:11px;display:flex;align-items:center;justify-content:center;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:13px;font-weight:600;color:var(--muted);margin-bottom:1px}
.crew .c4,.crew .c3{display:none}
@media (max-width:780px){.crew li.h4,.crew .c6{display:none}.crew .c4{display:block}}
@media (max-width:640px){.crew li.h3,.crew .c4{display:none}.crew .c3{display:block}.crew li{flex-basis:118px}.crew li.owner{flex-basis:104px}.crew li.more{flex-basis:84px}}
.row .desc{font-size:13px;color:var(--muted);overflow-wrap:anywhere}.row .desc.row-error{color:var(--attn-text)}
.purpose{font-size:13px;color:var(--fg);margin-top:2px;overflow-wrap:anywhere}.body>.purpose{margin-top:0}
.row .state{font-size:13px;color:var(--muted);white-space:nowrap;text-align:right}
.row .state a{color:var(--fg);margin-left:6px;border-bottom:1px solid var(--line)}
.row .size{width:2em;text-align:right;font-size:12px;color:var(--muted)}
.row.attn .state{color:var(--attn-text)}
.note{font-size:13px;color:var(--muted);margin-top:10px}

.sessions{display:grid;gap:10px}.sessions>*,.projects>*{min-width:0}
.body .row .state{white-space:normal;text-align:right;max-width:45%}
.sess{background:var(--surface);border:1px solid var(--line);border-radius:14px}
.sess>summary{display:grid;grid-template-columns:minmax(0,1fr) auto auto;column-gap:14px;row-gap:4px;align-items:baseline;padding:14px 20px 12px;cursor:pointer;list-style:none}
.sess>summary::-webkit-details-marker{display:none}
.sess>summary>.gl{grid-column:1/-1;display:flex;align-items:flex-end;height:30px;--fig-fill:none}
.slug,.srow .head .name{font-size:14px;font-weight:500}
.sess>summary .slug{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.st{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--muted);white-space:nowrap}
.sess.attn .st,.st.attn{color:var(--attn-text)}
#attention .st.attn{color:var(--muted)}
.ago{font-size:13px;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.sess:target{border-color:var(--faint)}
.list>.sess{border:0;border-radius:0;border-top:1px solid var(--line)}.list>.sess:first-child{border-top:0}
.group>summary{cursor:pointer;list-style:none}.group>summary::-webkit-details-marker{display:none}.group>summary h2::after{content:' ▸';font-size:11px}.group[open]>summary h2::after{content:' ▾'}
.body{padding:0 20px 16px}.body>.track{margin:12px 0 0;height:6px}
.now{font-size:13px;color:var(--muted);margin-top:8px;display:flex;flex-wrap:wrap;align-items:center;gap:0 4px}.now .meter{margin:0 6px 0 0}
.more{margin-top:10px}.more .units{margin:4px 0 8px}
.meter{display:inline-block;width:64px;height:4px;border-radius:2px;background:var(--track);overflow:hidden;vertical-align:middle;margin-right:6px}
.meter i{display:block;height:100%;background:var(--muted)}.meter.over i{background:var(--attn)}
.callout{padding:12px 14px;border-radius:10px;background:var(--attn-bg);border:1px solid var(--attn-line);font-size:13px;margin:12px 0 0}
.callout b{display:block;font-size:13px;font-weight:600;margin-bottom:2px}
.callout.calm{background:var(--bg);border-color:var(--line)}
.body .row{padding:8px 0;border-top:1px solid var(--line)}.body .row:first-child{border-top:0}
.body .units{margin-bottom:8px}
.sub{margin-top:8px}.sub>summary{font-size:13px;color:var(--muted);cursor:pointer;padding:4px 0}
.events{list-style:none;margin:4px 0 0;padding:0;font-size:13px}
.events li{display:flex;gap:10px;padding:5px 0;border-top:1px solid var(--line)}
.events time{color:var(--muted);font-variant-numeric:tabular-nums;flex:none}
.events .d{color:var(--muted);white-space:pre-wrap}
pre{white-space:pre-wrap;font-size:12px;background:var(--bg);padding:12px;border-radius:8px;margin:6px 0 0}
.path{font-size:12px;color:var(--muted);word-break:break-all;margin-top:10px}
.clamp1{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.clamp2{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.facts{display:flex;flex-wrap:wrap;gap:0 4px}
.srow{display:block;padding:12px 20px}
.srow .head{display:flex;align-items:baseline;gap:14px}.srow .head .name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.srow .head .st{min-width:0;overflow:hidden}
.srow .gl{display:flex;align-items:flex-end;height:30px;margin:0 0 4px;--fig-fill:none}
.srow .track{margin:8px 0 0;height:6px}.srow .desc{margin-top:2px}
.plan .row{padding:9px 20px}
.unit>summary{list-style:none;cursor:pointer}.unit>summary::-webkit-details-marker{display:none}.unit[open]>summary{background:var(--bg)}
.unit-body{padding:2px 20px 12px calc(20px + 8px + 12px + 2.4em + 12px);font-size:13px;color:var(--muted)}
.unit-body p{margin:6px 0 0;overflow-wrap:anywhere}.unit-body .lede{color:var(--fg)}
.plan-stage>summary.stage-head{display:flex;align-items:baseline;gap:6px}.stage-head .stage-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media (max-width:560px){nav{flex-wrap:wrap}.themes button{padding:3px 8px}.row .size{display:none}.row{padding:10px 16px}.subhead{padding-left:16px;padding-right:16px}
 .proj{padding:16px}.sess>summary{padding:12px 16px 10px;grid-template-columns:minmax(0,1fr) auto}.sess>summary>.ago{display:none}
 .body{padding:0 16px 14px}h1{font-size:24px}.hero .pct{font-size:24px}
 .srow{padding:12px 16px}.plan .row{padding:9px 16px}.unit-body{padding-left:16px;padding-right:16px}
 .plan .clamp1{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
"""

SCRIPT = """
(() => {
  const openFromHash = () => {
    let el = location.hash && document.getElementById(location.hash.slice(1));
    for (; el; el = el.parentElement) if (el.tagName === 'DETAILS') el.open = true;
  };
  addEventListener('hashchange', openFromHash);
  openFromHash();
  const tip = document.createElement('div');
  tip.className = 'tip';
  tip.hidden = true;
  document.body.append(tip);
  const placeTip = ev => {
    const pad = 8, r = tip.getBoundingClientRect();
    const x = Math.min(Math.max(ev.clientX - r.width / 2, pad), innerWidth - r.width - pad);
    const y = ev.clientY - r.height - 12 < pad ? ev.clientY + 18 : ev.clientY - r.height - 12;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  };
  document.addEventListener('mouseover', ev => {
    const seg = ev.target.closest('[data-tip]');
    if (!seg) { if (!ev.target.closest('.track')) tip.hidden = true; return; }
    tip.textContent = seg.dataset.tip;
    tip.hidden = false;
    placeTip(ev);
  });
  document.addEventListener('mousemove', ev => { if (!tip.hidden) placeTip(ev); });
  document.documentElement.addEventListener('mouseleave', () => { tip.hidden = true; });
  const picker = document.getElementById('themes');
  const systemDark = matchMedia('(prefers-color-scheme: dark)');
  const markTheme = () => {
    const active = document.documentElement.dataset.theme || (systemDark.matches ? '%s' : 'whiteprint');
    for (const b of picker.querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.pick === active));
  };
  picker.addEventListener('click', ev => {
    const b = ev.target.closest('button');
    if (!b) return;
    document.documentElement.dataset.theme = b.dataset.pick;
    try { localStorage.setItem('%s', b.dataset.pick); } catch (_) {}
    markTheme();
  });
  systemDark.addEventListener('change', markTheme);
  markTheme();
  if (!location.protocol.startsWith('http')) { setTimeout(() => location.reload(), %d); return; }
  const toggle = document.getElementById('notify');
  const canNotify = 'Notification' in window;
  const showToggle = () => {
    const permission = canNotify ? Notification.permission : 'denied';
    toggle.hidden = permission === 'granted';
    toggle.disabled = permission === 'denied';
    toggle.textContent = permission === 'denied' ? 'Notifications blocked here' : 'Turn on notifications';
  };
  toggle.addEventListener('click', async () => { await Notification.requestPermission(); showToggle(); });
  showToggle();
  const SEEN_KEY = 'robowright-dash-seen';
  let seen = null;
  try { const stored = sessionStorage.getItem(SEEN_KEY); if (stored) seen = new Set(JSON.parse(stored)); } catch (_) {}
  const watch = async () => {
    try {
      const res = await fetch('/attention.json', {cache: 'no-store'});
      if (!res.ok) return;
      const rows = await res.json();
      document.title = (rows.length ? `(${rows.length}) ` : '') + document.body.dataset.title;
      const isAllowed = canNotify ? Notification.permission === 'granted' : false;
      if (seen && isAllowed) {
        for (const r of rows.filter(r => !seen.has(r.key))) {
          const n = new Notification(`${r.project} needs attention`, {body: `${r.title} · ${r.what}`, tag: r.key});
          n.onclick = () => { window.focus(); location.href = r.href; };
        }
      }
      seen = new Set(rows.map(r => r.key));
      try { sessionStorage.setItem(SEEN_KEY, JSON.stringify([...seen])); } catch (_) {}
    } catch (_) {}
  };
  watch();
  setInterval(watch, %d);
  setInterval(async () => {
    try {
      const res = await fetch(location.href, {cache: 'no-store'});
      if (!res.ok) return;
      const next = new DOMParser().parseFromString(await res.text(), 'text/html');
      const kept = new Map([...document.querySelectorAll('details[id]')].map(d => [d.id, d.open]));
      for (const id of ['nav', 'main', 'foot']) {
        const fresh = next.getElementById(id);
        if (fresh) document.getElementById(id).replaceWith(fresh);
      }
      tip.hidden = true;
      for (const [id, open] of kept) { const d = document.getElementById(id); if (d) d.open = open; }
    } catch (_) {}
  }, %d);
})();
""" % (SYSTEM_DARK_THEME, THEME_KEY, REFRESH_SECONDS * 1000, REFRESH_SECONDS * 1000, REFRESH_SECONDS * 1000)


def plain(text: str) -> str:
    """Markdown cell text without backticks, bold, or links."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text or "")
    return re.sub(r"[`*]", "", text).strip()


def clip(text: str, limit: int = DETAIL_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def purpose(text: str) -> str:
    """What a unit is for, from the plan's Task Breakdown, shown wherever its session appears."""
    return f'<div class="purpose">{e(text)}</div>' if text else ""


def dot(cls: str) -> str:
    return f'<i class="dot {e(cls)}"></i>'


def anchor(slug: str) -> str:
    return "s-" + re.sub(r"[^\w-]", "-", slug)


def stop_of(session: dict) -> dict:
    stop = (session.get("run") or {}).get("stop_reason") or {}
    return {"code": stop} if isinstance(stop, str) else stop


def session_bucket(session: dict) -> str:
    """Attention waits on the Owner (a briefed session waits for its launch line); working is running now;
    waiting is parked; done is done."""
    if needs_you(session):
        return "attention"
    if session["tone"] in ("working", "rotating", "rebriefing", "intake", "briefing"):
        return "working"
    if session["tone"] == "done":
        return "done"
    return "waiting"


def needs_you(session: dict) -> bool:
    return session["tone"] in ("stopped", "unknown", "briefed", "owner-call") or bool(session.get("has_stop_file"))


def figure_role(session: dict) -> str:
    """Whose figure a session shows, from what the dashboard observes and nothing else, first match winning. A state no
    rule names is the Worker's: a guess at a role nothing observes would be a fake."""
    tone = session["tone"]
    if session.get("has_stop_file") or tone in ("stopped", "unknown", "owner-call"):
        return "owner"
    if tone in ("briefed", "rotating", "intake"):
        return "lead"
    if tone in ("briefing", "rebriefing"):
        return "planner"
    if session.get("kind") == "direct":
        return "worker"
    if tone == "working" and session.get("phase") == "end-of-stack":
        return "reviewer"
    return "worker"


def glyph(role: str | None) -> str:
    """The figure above a session row's name; '' for a row with no role, or whose art could not be read."""
    if not ROW_GLYPHS.get(role):
        return ""
    return f'<span class="gl" aria-hidden="true">{ROW_GLYPHS[role]}</span>'


def doing(session: dict) -> str:
    """A crew member's phrase for what the dashboard observes, as text for e(); 'working' for a state no phrase names,
    never a session file's own words."""
    tone = session["tone"]
    if figure_role(session) == "owner":
        return "your call"
    if tone in TONE_DOING:
        return TONE_DOING[tone]
    if tone == "intake":
        return LEAD_STAGE_DOING.get(session.get("lead_stage"), "working")
    if session.get("kind") == "direct":
        return "direct build"
    if session.get("phase") in PHASE_DOING:
        return PHASE_DOING[session["phase"]]
    units = (session.get("run") or {}).get("units") or []
    current = next((u for u in units if u.get("status") != "done"), None)
    if current and current.get("status") in UNIT_DOING:
        return f'{UNIT_DOING[current["status"]]} {current.get("id")}'
    return "working"


def page(title: str, crumbs: str, body: str, foot: str) -> str:
    now = datetime.now().astimezone().strftime("%H:%M:%S")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><link rel="icon" href="{FAVICON}"><script>{THEME_BOOT}</script><style>{THEME_CSS}{CSS}</style></head>
<body data-title="{e(title)}"><div class="wrap"><nav><div class="crumbs" id="nav">{crumbs}</div>
<div class="tools"><button class="notify" id="notify" hidden>Turn on notifications</button>{THEME_PICKER}</div></nav><main id="main">{body}</main>
<footer id="foot">{STAMP}<span>Updated {now} · refreshes every {REFRESH_SECONDS}s{foot}</span></footer></div><script>{SCRIPT}</script></body></html>"""


def archived_mark(project: dict) -> str:
    """The word `archived` beside an archived project's name, which shows only with live work, `--all` or by name."""
    return ' <span class="muted">archived</span>' if project["archived"] else ""


def tip_attrs(text: str) -> str:
    """A progress segment's label: shown at once by SCRIPT's tooltip, and read by screen readers."""
    return f'data-tip="{e(text)}" aria-label="{e(text)}" role="img"'


def track(units: list, big: bool = False) -> str:
    segs = "".join(f'<i class="seg {STATE[u["tone"]][0]}" style="flex:{weight(u)}" '
                   f'{tip_attrs(f"{u["id"]} {u["name"]} · {STATE[u["tone"]][1]}")}></i>' for u in units)
    return f'<div class="track{" big" if big else ""}">{segs}</div>'


def tally(units: list) -> str:
    counts: dict = {}
    for u in units:
        counts[u["tone"]] = counts.get(u["tone"], 0) + 1
    return '<div class="tally">' + "".join(
        f'<span><i class="key seg {STATE[t][0]}"></i>{counts[t]} {PLAN_LABEL[t]}</span>' for t in LEGEND_ORDER if t in counts) + "</div>"


def count_line(units: list) -> str:
    """One line under an index card's bar: each state's unit count in the bar's own labels, a state with none left out."""
    counts: dict = {}
    for u in units:
        counts[u["tone"]] = counts.get(u["tone"], 0) + 1
    words = " · ".join(f"{counts[t]} {STATE[t][1]}" for t in LEGEND_ORDER if t in counts)
    return f'<div class="tally"><span>{e(words)}</span></div>'


def attention_of(session: dict) -> tuple[str, str, str, str]:
    """(dot, word, aside, why) for a session that needs the Owner: the state word, what else holds it, and the detail."""
    if session["tone"] == "briefed":
        return "queued", "Briefed · ready to launch", "", ""
    if session["tone"] == "owner-call":
        return "attn", "Rebrief needs your call", "", (last_rebrief(session).get("why") or "read REBRIEF.md")
    stop = stop_of(session)
    word = "Owner STOP file present" if session.get("has_stop_file") and session["tone"] != "stopped" else (
        "Unreadable run.json" if "error" in session else f"Stopped · {stop.get('code', 'no code')}")
    aside = "rebrief Planner idle without a verdict" if session["tone"] == "stopped" and session.get("planner") else ""
    return "attn", word, aside, session.get("error") or stop.get("detail") or ""


def last_rebrief(session: dict) -> dict:
    return ((session.get("run") or {}).get("rebriefs") or [{}])[-1]


def planner_line(session: dict) -> str:
    """Who holds a rebrief, and the command to watch it."""
    planner = session.get("planner") or {}
    short_id = (planner.get("sessionId") or "")[:8]
    since = planner.get("statusUpdatedAt") or planner.get("startedAt")
    at = datetime.fromtimestamp(since / 1000).strftime("%H:%M") if since else "?"
    return f'Planner {e(planner.get("status", "?"))} since {at} · <span class="mono">claude attach {e(short_id)}</span>'


def attention_rows(projects: list, href) -> list:
    """Everything across every project that waits on the Owner, most urgent first."""
    rows = []
    for p in projects:
        for s in p["sessions"]:
            if needs_you(s):
                mark, word, aside, detail = attention_of(s)
                # `what` keys the notifier's rows (/attention.json), so it keeps the aside; the page shows it on the why line.
                rows.append({"project": p["name"], "dot": mark, "session": s, "role": figure_role(s), "title": s["slug"].removeprefix(p["name"] + "-"),
                             "what": " · ".join(b for b in (word, aside) if b), "word": word,
                             "why": " · ".join(b for b in (aside[:1].upper() + aside[1:], detail) if b),
                             "purpose": s.get("purpose", ""), "href": f'{href(p["name"])}#{anchor(s["slug"])}', "when": ago(s.get("touched"))})
        built = [u for u in p["units"] if u["tone"] == "built"]
        if built:
            listed = ", ".join(f'{plain(u["id"])} {u["name"]}' for u in built)
            rows.append({"project": p["name"], "dot": "built", "session": None, "role": None, "title": "Awaiting acceptance",
                         "what": listed, "word": f"{len(built)} built", "why": listed,
                         "purpose": " · ".join(plain(u["purpose"]) for u in built if u["purpose"]),
                         "href": f'{href(p["name"])}#plan', "when": ""})
    urgency = {"attn": 0, "queued": 1, "built": 2}
    return sorted(rows, key=lambda r: urgency[r["dot"]])


def render_attention(rows: list) -> str:
    """The home page's cross-project list: open by default, collapsible, grouped by project."""
    if not rows:
        return f'<h2>Needs attention</h2><div class="note">{dot("idle")} Nothing needs attention right now.</div>'
    parts, project = [], None
    for r in sorted(rows, key=lambda r: r["project"]):
        if r["project"] != project:
            project = r["project"]
            parts.append(f'<div class="subhead"><b>{e(project)}</b></div>')
        when = f'<span class="ago">{e(r["when"])}</span>' if r["when"] else ""
        why = f'<div class="desc clamp2" title="{e(r["why"])}">{e(r["why"])}</div>' if r["why"] else ""
        parts.append(f'<a class="row srow" href="{e(r["href"])}"><div class="main">{glyph(r["role"])}<div class="head">'
                     f'<span class="name mono">{e(r["title"])}</span>{state_mark(r["dot"], r["word"])}{when}</div>'
                     f'{purpose(r["purpose"])}{why}</div></a>')
    return (f'<details class="group" id="attention" open><summary><h2 class="attn-head">Needs attention · {len(rows)}</h2></summary>'
            f'<div class="list">{"".join(parts)}</div></details>')


def on_site(attention: list, projects: list, href) -> list:
    """Every session on site as (project, session, href): the attention rows' sessions in their order, then the
    running ones newest first across projects."""
    waiting = [(r["project"], r["session"], r["href"]) for r in attention if r["session"]]
    home = {id(s): p["name"] for p in projects for s in p["sessions"]}
    running = by_recency([s for p in projects for s in p["sessions"] if session_bucket(s) == "working"])
    return waiting + [(home[id(s)], s, f'{href(home[id(s)])}#{anchor(s["slug"])}') for s in running]


def crew_member(project: str, session: dict, href: str, place: int, shows_project: bool) -> str:
    """One session on the crew card; `place`, from 1, marks the members a narrower page hides. The project line is left
    off a project's own page, whose name it is."""
    role = figure_role(session)
    who, what = session["slug"].removeprefix(project + "-"), doing(session)
    marks = " ".join(cls for cls, is_marked in (("owner", role == "owner"), ("h3", place > CREW_CAPS[2]),
                                               ("h4", place > CREW_CAPS[1])) if is_marked)
    li = f'<li class="{marks}">' if marks else "<li>"
    return (f'{li}<a class="member" href="{e(href)}" title="{e(f"{project} · {who} · {what}")}">'
            f'<span class="stage">{CREW_FIGURES[role]}</span><span class="labels"><span class="who">{e(who)}</span>'
            f'<span class="what">{e(what)}</span>{where_line(project, shows_project)}</span></a></li>')


def where_line(project: str, shows_project: bool) -> str:
    return f'<span class="where">{e(project)}</span>' if shows_project else ""


def crew_ghost(hidden: int, cap: int, is_running: bool, shows_project: bool) -> str:
    """The sessions past one cap, as a dashed placeholder linking the running list (the index's In flight, a project
    page's Working), or Needs attention when no member is running and that list is not drawn; the CSS shows one ghost
    per width."""
    running_list = "#flight" if shows_project else "#working"
    target = running_list if is_running else "#attention"
    spacer = '<span class="where">&nbsp;</span>' if shows_project else ""
    return (f'<li class="more c{cap}"><a class="member" href="{target}" title="{hidden} more on site, listed below">'
            f'<span class="stage" aria-hidden="true"><span class="ghost">+{hidden}</span></span>'
            f'<span class="labels"><span class="who">{hidden} more</span><span class="what">listed below</span>'
            f'{spacer}</span></a></li>')


def render_crew(crew: list, shows_project: bool) -> str:
    """The "On site" card: a figure per session on site up to the widest cap, then a ghost per cap exceeded; the
    dozing Worker when nothing is on site. `shows_project` is false on a project's own page."""
    if not crew:
        return ('<section class="site" aria-labelledby="site-h"><h2 id="site-h">On site</h2><div class="crew-card quiet">'
                f'<ul class="crew"><li><div class="member"><span class="stage">{DOZING_WORKER}</span><span class="labels">'
                '<span class="what">Quiet site. Nothing is running.</span></span></div></li></ul></div></section>')
    members = [crew_member(project, s, link, place, shows_project)
               for place, (project, s, link) in enumerate(crew[:CREW_CAPS[0]], start=1)]
    is_running = any(session_bucket(s) == "working" for _, s, _ in crew)
    ghosts = [crew_ghost(len(crew) - cap, cap, is_running, shows_project) for cap in CREW_CAPS if len(crew) > cap]
    return (f'<section class="site" aria-labelledby="site-h"><h2 id="site-h">On site · {len(crew)}</h2>'
            f'<div class="crew-card"><ul class="crew">{"".join(members + ghosts)}</ul></div></section>')


def run_unit_dot(unit: dict, run: dict) -> str:
    """A review round under its attempt limit is routine work; red only once the limit is spent."""
    limit = count(run.get("max_gate_attempts"))
    is_spent = limit is not None and (count(unit.get("gate_attempts")) or 0) >= limit
    return "attn" if unit.get("status") == "held" and is_spent else RUN_UNIT_DOT.get(unit.get("status"), "idle")


def unit_phrase(unit: dict, run: dict) -> str:
    status = unit.get("status", "?")
    if status == "held":
        limit = count(run.get("max_gate_attempts"))
        return f'fixing review notes · round {count(unit.get("gate_attempts")) or 0} of {"?" if limit is None else limit}'
    return UNIT_PHRASE.get(status, status)


def event_phrase(ev: dict) -> str:
    """The plain reading of an event; the raw label stays in the project page's Recent events."""
    name = ev.get("event", "?")
    if name not in EVENT_PHRASE:
        return event_label(ev)
    phrase = "resumed by you" if name == "resume" and str(ev.get("actor", "")).lower() == "owner" else EVENT_PHRASE[name]
    if ev.get("code"):
        phrase += f' · {ev["code"]}'
    text = f'{ev["unit"]} {phrase}' if ev.get("unit") else phrase
    return text[:1].upper() + text[1:]


def activity(session: dict) -> str:
    """'Stuck?' once a running session has written nothing for STUCK_MINUTES; otherwise when it last wrote."""
    quiet = session.get("quiet_minutes")
    if quiet is None:
        return ""
    since = ago(session["active"]).removesuffix(" ago")
    if quiet >= STUCK_MINUTES:
        return f'<span title="no file written in the session folder or worktree">Stuck? · nothing written for {since}</span>'
    return f"<span>active {since} ago</span>"


def run_track(run: dict) -> str:
    """One equal segment per unit in a session's brief, coloured by its status; each segment's tooltip names it."""
    segs = "".join(f'<i class="seg {run_unit_dot(u, run)}" style="flex:1" '
                   f'{tip_attrs(f"{u.get("id")} {u.get("title")} · {unit_phrase(u, run)}")}></i>' for u in run.get("units") or [])
    return f'<div class="track">{segs}</div>'


def short_number(n) -> str:
    """A count as read at a glance: 740, 2.3k, 23k, 3.1M. The exact figure goes in the caller's title."""
    if n >= 999_500:
        return f"{n / 1_000_000:.1f}M"
    if n >= 9_950:
        return f"{n / 1000:.0f}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return f"{n:,}"


def spend_bits(row: dict | None, in_dollars: bool) -> list:
    """A rollup row as short phrases, each with its exact figure in the title; the estimate first and only under a
    dollar brief. An estimate no record priced reads n/a, never 0.00."""
    if not row:
        return []
    bits = [f'<span title="{row["active_hours"]:.2f} active hours">{row["active_hours"]:.1f} h active</span>',
            f'<span title="{row["requests"]:,} requests">{short_number(row["requests"])} requests</span>',
            f'<span title="{row["output_tokens"]:,} output tokens">{short_number(row["output_tokens"])} output tokens</span>']
    if in_dollars:
        usd = "n/a" if row["estimated_usd"] is None else f'${row["estimated_usd"]:.2f}'
        bits.insert(0, f'<span title="estimated from the price table">{usd} est.</span>')
    return bits


def position(session: dict) -> tuple[str, str]:
    """(where a session is in its brief, as text for e(); its tooltip). '' when the state word already says it all."""
    run, tone = session["run"], session["tone"]
    units = run.get("units") or []
    current = next((u for u in units if u.get("status") != "done"), None)
    parked = run.get("parked")
    is_parked_before_launch = tone == "parked" and isinstance(parked, dict) and parked.get("from") == "briefed"
    if tone == "briefed":
        n = len(units)
        where = tip = f'Ready to launch · {n} unit{"" if n == 1 else "s"}' if n else "Ready to launch"
    elif is_parked_before_launch:
        where = tip = "Parked before launch"
    elif tone in TERMINAL_TONES:
        where = tip = f'Parked in {current.get("id")} of {len(units)}' if tone == "parked" and current else ""
    elif current:
        is_stopped = tone in ("stopped", "owner-call")
        where = (f'Stopped in {current.get("id")} of {len(units)}' if is_stopped else
                 f'{current.get("id")} of {len(units)} · {unit_phrase(current, run)}')
        tip = current.get("title") or ""
    elif units:
        where = tip = f'All units done · {PHASE_PHRASE.get(session["phase"], session["phase"])}'
    else:
        where = tip = ""
    if tone == "intake":
        phrase = LEAD_STAGE_PHRASE[session["lead_stage"]]
        where = tip = phrase[:1].upper() + phrase[1:]
    if session.get("follow_up"):
        where = tip = f'All units done · follow-up pass by {session["follow_up"].get("name")}'
    if tone == "rotating":
        is_rebrief = (run.get("rotate") or {}).get("reason") == "rebrief"
        handing_off = f"Handing off · {where}" if where else "Handing off"
        where = "Rebriefed · the Lead launches a fresh Worker" if is_rebrief else handing_off
    if tone == "rebriefing":
        where = tip = f'Planner rewriting the brief · rebrief {len(run.get("rebriefs") or []) + 1}'
    return where, tip


def latest_move(session: dict) -> str:
    """The newest event in plain words with its age, else the newest ledger heading; text for e()."""
    if session["events"]:
        last = session["events"][-1]
        return f'{event_phrase(last)} · {ago(parse_at(last.get("at", "")))}'
    return session["ledger"][-1] if session["ledger"] else ""


def short_state(session: dict) -> str:
    """The state word alone, as the crew card keeps it short: no raw phase or Lead stage. A stop keeps its code, which
    is the one thing the Owner reads it for."""
    if "error" in session:
        return "Unreadable"
    label = STATE.get(session["tone"], ("", session["phase"]))[1]
    code = stop_of(session).get("code") if session["tone"] == "stopped" else None
    return f"{label} · {code}" if code else label


def state_mark(cls: str, text: str) -> str:
    """The dot beside its state word, at a row's right end; the word takes the attention ink with an attention dot."""
    return f'<span class="st{" attn" if cls == "attn" else ""}">{dot(cls)}{e(text)}</span>'


def state_end(session: dict) -> str:
    """A session row's right end: the dot and the state word, then how long ago the session wrote."""
    return state_mark(STATE.get(session["tone"], ("idle", ""))[0], short_state(session)) + f'<span class="ago">{ago(session.get("touched"))}</span>'


def now_line(session: dict, names_holder: bool) -> str:
    """Where the session is, how recently it wrote, and its wall budget, on one line; the latest move in the title. A
    rebrief's line names who holds it where no callout does; a briefed session has no wall yet."""
    where, tip = position(session)
    title = latest_move(session) or tip
    head = f'<span title="{e(title)}">{e(where)}</span>' if where and title else (f"<span>{e(where)}</span>" if where else "")
    holder = planner_line(session) if names_holder and session["tone"] == "rebriefing" else ""
    wall_meter = "" if session["tone"] == "briefed" else wall(session)
    bits = [bit for bit in (head, holder, activity(session), wall_meter) if bit]
    return f'<div class="now">{" · ".join(bits)}</div>' if bits else ""


def rebrief_reason(session: dict) -> str:
    """The stop a rebriefing Planner is fixing, as one clamped line with the whole of it in the title."""
    if session["tone"] != "rebriefing":
        return ""
    stop = stop_of(session)
    reason = f'Stopped on {stop.get("code", "?")}: {stop.get("detail", "")}'
    return f'<div class="desc clamp2" title="{e(reason)}">{e(reason)}</div>'


def pending_flight_row(session: dict, prefix: str, href: str) -> str:
    """No brief, so no unit track: who holds what is being written, on the now line."""
    agent = session.get("agent") or {}
    if session["kind"] == "briefing":
        where, who = "Planner writing the brief", planner_line(session)
    else:
        where = "Direct build · no session folder, records in the project's prs/"
        who = f'Worker {e(agent.get("status", "gone"))} · <span class="mono">claude attach {e(agent.get("name", ""))}</span>' if agent else ""
    bits = [f'<span title="{e(where)}">{who or e(where)}</span>', activity(session)]
    return (f'<a class="row srow" href="{e(href)}"><div class="main">{glyph(figure_role(session))}<div class="head">'
            f'<span class="name mono">{e(session["slug"].removeprefix(prefix))}</span>{state_end(session)}</div>'
            f'{purpose(session.get("purpose"))}<div class="now">{" · ".join(b for b in bits if b)}</div></div></a>')


def flight_row(session: dict, prefix: str, href: str) -> str:
    if session.get("kind") in ("briefing", "direct") and session["tone"] in ("working", "briefing"):
        return pending_flight_row(session, prefix, href)
    return (f'<a class="row srow" href="{e(href)}"><div class="main">{glyph(figure_role(session))}<div class="head">'
            f'<span class="name mono">{e(session["slug"].removeprefix(prefix))}</span>{state_end(session)}</div>'
            f'{purpose(session.get("purpose"))}{rebrief_reason(session)}{run_track(session["run"])}{now_line(session, True)}</div></a>')


def render_in_flight(projects: list, href) -> str:
    """Every running session across projects: where it is in its brief, its wall budget, and its latest move."""
    running = [(p["name"], s) for p in projects for s in p["sessions"] if session_bucket(s) == "working"]
    if not running:
        return f'<h2>In flight</h2><div class="note">{dot("idle")} Nothing is running right now.</div>'
    parts, project = [], None
    for name, s in running:
        if name != project:
            project = name
            parts.append(f'<div class="subhead"><b>{e(name)}</b></div>')
        parts.append(flight_row(s, name + "-", f'{href(name)}#{anchor(s["slug"])}'))
    return (f'<details class="group" id="flight" open><summary><h2>In flight · {len(running)}</h2></summary>'
            f'<div class="list flight">{"".join(parts)}</div></details>')


def quiet_row(project: dict, href: str) -> str:
    units = project["units"]
    if units:
        complete = sum(1 for u in units if u["tone"] == "complete")
        desc, pct = f"{complete} of {len(units)} units complete", f'{project["complete_percent"]:.0f}% complete · '
    else:
        desc, pct = f'No plan table · {len(project["sessions"])} sessions', ""
    return (f'<a class="row" href="{e(href)}">{dot("idle")}<div class="main"><div class="name">{e(project["name"])}{archived_mark(project)}</div>'
            f'<div class="desc">{e(desc)}</div></div><span class="state">{pct}{ago(project["touched"])}</span></a>')


def awaiting_acceptance(project: dict, href: str) -> str:
    """Built units are finished but not in main; accepting them is the Owner's call."""
    built = [u for u in project["units"] if u["tone"] == "built"]
    if not built:
        return ""
    names = ", ".join(f'{plain(u["id"])} {u["name"]}' for u in built)
    count = f'{len(built)} unit{"s" if len(built) != 1 else ""} built, not in main yet'
    return (f'<a class="alert awaiting" href="{e(href)}">{dot("built")}<div><b>Awaiting acceptance</b> <span class="muted">{e(project["name"])} · {count}</span>'
            f'<div class="why">{e(clip(names))}</div></div></a>')


def unit_state(u: dict) -> str:
    first_by_number: dict = {}
    for s in u["sessions"]:
        first_by_number.setdefault(s["number"] or s["slug"], s)
    links = "".join(f'<a class="mono" href="#{anchor(s["slug"])}">{e(label)}</a>' for label, s in first_by_number.items())
    label = STATE[u["tone"]][1]
    if u["tone"] in ("working", "rotating", "rebriefing") and u["fraction"]:
        label += f' · {int(u["fraction"] * 100)}%'
    return f'<span class="state">{label}{links}</span>'


def is_stage_complete(units: list) -> bool:
    return all(u["tone"] in ("complete", "settled") for u in units)


def collapsed_stages(stages: list) -> set:
    """Every complete stage folds, except the latest one while no stage after it has started. Unsequenced units
    are not a stage in the sequence, so they fold as soon as they are all complete."""
    complete = {i for i, (_, units) in enumerate(stages) if is_stage_complete(units)}
    sequenced = [i for i in sorted(complete) if stages[i][0] != "unsequenced"]
    if not sequenced:
        return complete
    latest = sequenced[-1]
    has_later_started = any(u["tone"] not in NOT_STARTED_TONES for _, units in stages[latest + 1:] for u in units)
    return complete if has_later_started else complete - {latest}


def stage_count(units: list) -> str:
    complete = sum(1 for u in units if u["tone"] == "complete")
    if not complete:
        return ""
    return f"{complete} complete" if complete == len(units) else f"{complete} of {len(units)} complete"


def unit_row(u: dict) -> str:
    """One plan unit: its Summary on one line under its name (none once it is complete), and behind the row the
    Summary in full when the face clipped or left it out, the Description where it says more, and the Status cell."""
    cls = STATE[u["tone"]][0]
    summary, desc, status = plain(u["purpose"]), plain(u["desc"]), plain(u["plan_status"])
    is_complete = u["tone"] == "complete"
    line = f'<div class="desc clamp1" title="{e(summary)}">{e(summary)}</div>' if summary and not is_complete else ""
    if u["row_error"]:
        line += f'<div class="desc row-error">{e(u["row_error"])}</div>'
    face = (f'{dot(cls)}<span class="id mono">{e(plain(u["id"]))}</span><div class="main"><div class="name">{e(u["name"])}</div>{line}</div>'
            f'{unit_state(u)}<span class="size">{e(plain(u["size"]))}</span>')
    lede = summary if is_complete or len(summary) > SUMMARY_FACE_CHARS else ""
    inside = "".join(f'<p class="{kind}">{label}{e(text)}</p>' for kind, label, text in
                     (("lede", "", lede), ("long", "", "" if desc == summary else desc), ("status", "Status column · ", status)) if text)
    if not inside:
        return f'<div class="row {cls}">{face}</div>'
    unit_id = "u-" + re.sub(r"[^\w-]", "-", plain(u["id"]))
    return f'<details class="unit" id="{unit_id}"><summary class="row {cls}">{face}</summary><div class="unit-body">{inside}</div></details>'


def render_plan(project: dict) -> str:
    stages: list = []
    for u in project["units"]:
        if not stages or stages[-1][0] != u["stage"]:
            stages.append((u["stage"], []))
        stages[-1][1].append(u)
    collapsed = collapsed_stages(stages)
    parts = []
    for index, (stage, units) in enumerate(stages):
        head, _, rest = plain(stage).partition(" — ")
        is_open = "" if index in collapsed else " open"
        count = stage_count(units)
        count_html = f'<span class="count">{e(count)}</span>' if count else ""
        stage_id = "stage-" + re.sub(r"[^\w-]", "-", head)
        parts.append(f'<details class="plan-stage" id="{stage_id}"{is_open}>'
                     f'<summary class="subhead stage-head"><b>{e(head)}</b><span class="stage-name">{e(rest)}</span>{count_html}</summary>')
        parts.extend(unit_row(u) for u in units)
        parts.append("</details>")
    return f'<h2 id="plan">Plan</h2><div class="list plan">{"".join(parts)}</div>'


def render_run_units(run: dict) -> str:
    rows = []
    for unit in run.get("units") or []:
        rows.append(f'<div class="row">{dot(run_unit_dot(unit, run))}<span class="id mono">{e(unit.get("id"))}</span>'
                    f'<div class="main"><div class="desc" title="{e(unit.get("title"))}">{e(unit.get("title"))}</div></div>'
                    f'<span class="state">{e(unit_phrase(unit, run))}</span></div>')
    return f'<div class="units">{"".join(rows)}</div>' if rows else ""


def event_label(ev: dict) -> str:
    label = ev.get("event", "?")
    if ev.get("to"):
        label = f'{ev["unit"] + " " if ev.get("unit") else ""}{label}: {ev.get("from", "")} → {ev["to"]}'
    if ev.get("code"):
        label += f' · {ev["code"]}'
    return label


def render_events(events: list) -> str:
    rows = []
    for ev in events[-EVENTS_SHOWN:][::-1]:
        at = parse_at(ev.get("at", ""))
        label = event_label(ev)
        detail = f'<div class="d">{e(clip(ev["detail"], 400))}</div>' if ev.get("detail") else ""
        stamp = at.astimezone().strftime("%H:%M") if at else "--:--"
        rows.append(f'<li><time title="{e(ev.get("at"))}">{stamp}</time><div>{e(label)}{detail}</div></li>')
    return f'<ol class="events">{"".join(rows)}</ol>'


def wall(session: dict) -> str:
    run, started = session["run"], session["started"]
    max_hours = count(run.get("max_wall_hours")) or 0
    if not max_hours:
        return ""
    if not started:
        return "not started"
    is_frozen = session["tone"] in ("done", "intake", "stopped", "parked", "rebriefing", "owner-call")
    end = session["touched"] if is_frozen and session["touched"] else datetime.now(timezone.utc)
    hours = (end - started).total_seconds() / 3600
    over = " over" if hours > max_hours and not is_frozen else ""
    return (f'<span><span class="meter{over}"><i style="width:{min(100, hours / max_hours * 100):.0f}%"></i></span>'
            f'{hours:.1f} of {max_hours}h</span>')


def clock_time(captured) -> str:
    """A reading's captured_at as local HH:MM:SS: epoch seconds (usage-tap.py writes an int) or an ISO-8601 string;
    "" for anything else."""
    if isinstance(captured, bool):
        return ""
    if isinstance(captured, str):
        try:
            at = parse_at(captured)
            return at.astimezone().strftime("%H:%M:%S") if at else ""
        except (OverflowError, ValueError):
            return ""
    if not isinstance(captured, (int, float)) or not captured >= 0:
        return ""
    try:
        return datetime.fromtimestamp(captured).astimezone().strftime("%H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return ""


def plan_usage_line() -> str:
    """The status-line tap's newest reading, as run-cost.py reads it; none without a 5-hour or 7-day figure."""
    five_hour, seven_day, captured = RUN_COST.plan_usage()
    windows = [f"{label} {e(pct)}%" for label, pct in (("5-hour", five_hour), ("7-day", seven_day)) if pct is not None]
    if not windows:
        return ""
    clock = clock_time(captured)
    at = f" · as of {clock}" if clock else ""
    return f'<div class="note plan-usage" title="{e(PLAN_USAGE_TITLE)}">{PLAN_USAGE_LABEL} · {" · ".join(windows)}{at}</div>'


def verdict_line(run: dict) -> str:
    reviews = run.get("plan_reviews")
    newest = reviews[-1] if isinstance(reviews, list) and reviews and isinstance(reviews[-1], dict) else {}
    verdict = newest.get("verdict")
    return f'<div class="note verdict">Plan review · <b>{e(verdict)}</b></div>' if verdict else ""


def asks_line(asks: list | None) -> str:
    if asks is None:
        return ""
    items = "".join(f"<li>{e(plain(a))}</li>" for a in asks)
    return (f'<div class="note asks">Owner brief · {len(asks)} ask{"" if len(asks) == 1 else "s"}'
            f'{f"<ul>{items}</ul>" if items else ""}</div>')


def callouts(session: dict) -> str:
    """What a card asks of the Owner, or says it is waiting on. A stopped card's state word already carries its code, so
    its callout is the detail alone; every other callout keeps its heading."""
    run, stop = session["run"], stop_of(session)
    out = ""
    if session["tone"] == "rebriefing":
        out += (f'<div class="callout calm"><b>A Planner is rewriting the brief</b>{planner_line(session)}. '
                f'It ends with a verdict: confident, and the Lead relaunches; owner, and it comes to you. The stop it is fixing:</div>')
    if session["tone"] == "owner-call":
        out += (f'<div class="callout"><b>Rebrief needs your call</b>{e(last_rebrief(session).get("why") or "")} '
                f'Read REBRIEF.md in the session folder.</div>')
    if session["tone"] in ("stopped", "rebriefing") or stop:
        calm = " calm" if session["tone"] == "rebriefing" else ""
        head = "" if session["tone"] == "stopped" else f'<b>{e(stop.get("code", "stopped"))}</b>'
        out += f'<div class="callout{calm}">{head}{e(stop.get("detail", ""))}</div>'
    if session["has_stop_file"]:
        out += '<div class="callout"><b>Owner STOP file present</b>The session halts at its next check.</div>'
    if session["tone"] == "rotating":
        out += f'<div class="note">Handing off to a fresh session since {e((run.get("rotate") or {}).get("requested_at"))}.</div>'
    return out


def facts_line(session: dict) -> str:
    """A card's quiet facts at the foot of its Details: repo, shape, longest quiet, rebriefs, the folder and its files."""
    run = session["run"]
    longest = session.get("longest_quiet")
    rebriefs = len(run.get("rebriefs") or [])
    bits = [e(run.get("repo")) if run.get("repo") else "", e(run.get("shape")) if run.get("shape") else "",
            f"longest quiet {longest:.0f}m" if longest is not None else "",
            f"{rebriefs} rebrief{'s' if rebriefs != 1 else ''}" if rebriefs else "", e(session["dir"])]
    files = f' · {e(", ".join(session["files"]))}' if session["files"] else ""
    return f'<div class="path mono">{" · ".join(b for b in bits if b)}{files}</div>'


def details(session: dict, sid: str) -> str:
    """Everything on a card that is for digging, behind one disclosure: the brief's units, the latest move, the ledger,
    spend, the events and the handoff, then the facts line."""
    run = session["run"]
    spend = spend_bits(session.get("spend"), budgets_in_dollars(run))
    spend_html = f'<div class="note spend">Spend · {" · ".join(spend)}</div>' if spend else ""
    # With no events the latest move is the ledger heading, which the next line shows.
    latest = f'<div class="note">Latest · {e(latest_move(session))}</div>' if session["events"] else ""
    ledger = f'<div class="note">Ledger · {e(session["ledger"][-1])}</div>' if session["ledger"] else ""
    events = (f'<details class="sub" id="ev-{sid}"><summary>Recent events</summary>{render_events(session["events"])}</details>'
              if session["events"] else "")
    handoff = (f'<details class="sub" id="ho-{sid}"><summary>Handoff first action</summary><pre>{e(session["first_action"])}</pre></details>'
               if session["first_action"] else "")
    return (f'<details class="sub more" id="mo-{sid}"><summary>Details</summary>{render_run_units(run)}{latest}{ledger}'
            f'{spend_html}{events}{handoff}{facts_line(session)}</details>')


def render_session(session: dict, prefix: str = "") -> str:
    """A session's card: the figure over the slug, the state at the right end, then its purpose, what it asks, its
    bar and one now line; everything else is behind Details."""
    sid = anchor(session["slug"])
    cls = STATE.get(session["tone"], ("idle", ""))[0]
    is_open = " open" if session["tone"] not in TERMINAL_TONES else ""
    # An error card sits under Needs attention but stays bare: its body is the error alone.
    is_on_site = session_bucket(session) in ("attention", "working") and "error" not in session
    gl = glyph(figure_role(session)) if is_on_site else ""
    summary = (f'<summary>{gl}<span class="slug mono" title="{e(session["slug"])}">{e(session["slug"].removeprefix(prefix))}</span>'
               f'{state_end(session)}</summary>')
    if "error" in session:
        return (f'<details class="sess attn" id="{sid}" open>{summary}<div class="body"><div class="callout">'
                f'{e(session["error"])}</div><div class="path mono">{e(session["dir"])}</div></div></details>')
    run = session["run"]
    has_bar = bool(run.get("units")) and session["tone"] not in TERMINAL_TONES + ("briefed",)
    finished = verdict_line(run) + asks_line(session.get("asks")) if session["phase"] == "done" else ""
    return (f'<details class="sess {cls}" id="{sid}"{is_open}>{summary}<div class="body">{purpose(session.get("purpose"))}'
            f'{callouts(session)}{run_track(run) if has_bar else ""}{now_line(session, False)}{finished}{details(session, sid)}</div></details>')


def hero_facts(project: dict) -> str:
    """The project header's one line under the legend: how much is built, the time left, and the spend; each phrase
    says what it is weighted by, or its exact figure, in its title."""
    bits = []
    if project["units"]:
        bits.append(f'<span title="weighted by unit size">{project["percent"]:.0f}% built</span>')
    if project["hours_left"] is not None and project["points_earned"] < project["points_total"]:
        bits.append(f'<span title="of session time, at the pace so far">about {project["hours_left"]:.0f}h left</span>')
    if project["has_ledger"]:
        bits += spend_bits(project["spend"], project["in_dollars"])
    return f'<p class="facts">{" · ".join(bits)}</p>' if bits else ""


def project_crew(project: dict) -> str:
    """The index's On site card for this project's own sessions alone, each figure linking its card on this page."""
    here = lambda name: ""
    return render_crew(on_site(attention_rows([project], here), [project], here), False)


def render_project_page(project: dict, index_href: str) -> str:
    units = project["units"]
    if units:
        hero = (f'<section class="hero"><div class="hero-head"><h1>{e(project["name"])}{archived_mark(project)}</h1>'
                f'<div class="pct">{project["complete_percent"]:.0f}%<small>complete</small></div></div>{track(units, big=True)}{tally(units)}'
                f'{hero_facts(project)}</section>')
        plan = render_plan(project)
    else:
        hero = (f'<section class="hero"><h1>{e(project["name"])}{archived_mark(project)}</h1><p>PROJECT.md has no Task Breakdown table, so only sessions are shown.</p>'
                f'{hero_facts(project)}</section>')
        plan = ""
    unplanned = ""
    if units and project["unplanned"]:
        unplanned = f'<div class="note">Not claimed by any unit: {e(", ".join(s["slug"] for s in project["unplanned"]))}</div>'
    prefix = project["name"] + "-"
    buckets: dict = {"attention": [], "working": [], "waiting": [], "done": []}
    for s in project["sessions"]:
        buckets[session_bucket(s)].append(s)
    cards = {k: "".join(render_session(s, prefix) for s in v) for k, v in buckets.items()}
    awaiting = awaiting_acceptance(project, "#plan")
    attention_html = (f'<h2 class="attn-head" id="attention">Needs attention</h2><div class="sessions">{awaiting}{cards["attention"]}</div>'
                      if awaiting or cards["attention"] else "")
    working_html = f'<h2 id="working">Working</h2><div class="sessions">{cards["working"]}</div>' if cards["working"] else ""
    waiting_html = f'<h2>Waiting</h2><div class="sessions">{cards["waiting"]}</div>' if cards["waiting"] else ""
    done_html = ""
    if buckets["done"]:
        count = len(buckets["done"])
        is_open = " open" if count <= FINISHED_OPEN_MAX else ""
        done_html = (f'<details class="group" id="done"{is_open}><summary><h2>Done · {count}</h2></summary>'
                     f'<div class="list">{cards["done"]}</div></details>')
    no_ledger = "" if project["has_ledger"] else '<div class="note">Spend · no ledger: no accounting root, or no records.jsonl under it</div>'
    crumbs = f'<a class="brand" href="{e(index_href)}">{MARK}robowright</a><span>/</span><span class="here">{e(project["name"])}</span>'
    return page(project["name"], crumbs, f"{hero}{plan_usage_line()}{no_ledger}{project_crew(project)}{attention_html}{working_html}{waiting_html}{plan}{unplanned}{done_html}", f' · {e(project["folder"])}{trust_note()}')


def render_empty() -> str:
    return (f'<section class="empty">{HERO}<p>No projects yet.</p>'
            '<p>Start one with <code>role-start planner &lt;project&gt;</code>.</p>'
            f'<p class="where">Looking for folders with a PROJECT.md under <span class="mono">{e(PROJECTS_ROOT)}</span></p></section>')


def render_index(projects: list, orphans: list, href) -> str:
    crumbs, foot = f'<span class="here brand">{MARK}robowright</span>', f" · {e(PROJECTS_ROOT)} · {e(SESSIONS_ROOT)}{trust_note()}"
    if not projects and not orphans:
        return page("Robowright", crumbs, f"<h1>Projects</h1>{render_empty()}", foot)
    rows = attention_rows(projects, href)
    attention = render_attention(rows)
    crew = on_site(rows, projects, href)
    # The quiet card already says nothing is running, and that no project is live.
    is_quiet = bool(projects) and not crew
    site = render_crew(crew, True) if projects else ""
    flight = "" if is_quiet else render_in_flight(projects, href)
    live = [p for p in projects if p["live"] or attention_rows([p], href)]
    quiet = [p for p in projects if p not in live]
    cards = []
    for p in live:
        if p["units"]:
            pct = f'<span class="pct">{p["complete_percent"]:.0f}%<small>complete</small></span>'
            body = track(p["units"]) + count_line(p["units"])
        else:
            pct = ""
            live = len(p["live"])
            body = f'<div class="tally"><span>No plan table · {len(p["sessions"])} sessions{f" · {live} live" if live else ""}</span></div>'
        waiting_on_you = attention_rows([p], href)
        flag = (f'<span class="flag">{dot(waiting_on_you[0]["dot"])}{len(waiting_on_you)} need{"s" if len(waiting_on_you) == 1 else ""} attention</span>'
                if waiting_on_you else "")
        cards.append(f'<a class="proj" href="{e(href(p["name"]))}"><div class="proj-head"><span class="proj-name">{e(p["name"])}{archived_mark(p)}</span>{pct}</div>'
                     f'{body}<div class="tally" style="margin-top:6px">{flag}<span>Updated {ago(p["touched"])}</span></div></a>')
    if cards:
        listing = f'<h2>Live projects · {len(cards)}</h2><div class="projects">{"".join(cards)}</div>'
    elif is_quiet:
        listing = ""
    elif projects:
        listing = f'<h2>Live projects</h2><div class="note">{dot("idle")} No project has a live session right now.</div>'
    else:
        listing = f'<h2>Projects</h2><p class="muted">No project folder with a PROJECT.md under {e(PROJECTS_ROOT)}.</p>'
    quiet_open = "" if cards else " open"
    quiet_html = (f'<details class="group" id="quiet"{quiet_open}><summary><h2>Quiet · {len(quiet)}</h2></summary>'
                  f'<div class="list">{"".join(quiet_row(p, href(p["name"])) for p in quiet)}</div></details>' if quiet else "")
    other = f'<h2>Sessions with no project folder</h2><div class="sessions">{"".join(render_session(s) for s in orphans)}</div>' if orphans else ""
    body = f'<h1>Projects</h1>{plan_usage_line()}{site}{attention}{flight}{listing}{quiet_html}{other}'
    return page("Robowright", crumbs, body, foot)


# ---------------------------------------------------------------- entry points


def project_link(name: str) -> str:
    return f"/p/{quote(name, safe='')}"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0]).rstrip("/")
        port = self.server.server_port
        # A page another site rebinds to 127.0.0.1 arrives under its own Host.
        if (self.headers.get("Host") or "").lower() not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            body, status = "forbidden", 403
        elif path in ("", "/index.html"):
            projects, orphans = load_world(None, self.server.shows_archived, self.server.verified)
            body, status = render_index(projects, orphans, project_link), 200
        elif path == "/attention.json":
            projects, _ = load_world(None, self.server.shows_archived, self.server.verified)
            rows = attention_rows(projects, project_link)
            body, status = json.dumps([{"key": f'{r["href"]}|{r["what"]}', "project": r["project"], "title": r["title"],
                                        "what": r["what"], "href": r["href"]} for r in rows]), 200
        elif path.startswith("/p/"):
            projects, _ = load_world(path[3:], self.server.shows_archived, self.server.verified)
            body, status = (render_project_page(projects[0], "/"), 200) if projects else ("no such project", 404)
        else:
            body, status = "not found", 404
        data = body.encode()
        self.send_response(status)
        kind = "application/json" if path.endswith(".json") else "text/html"
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        return


def serve(port: int, shows_archived: bool) -> int:
    try:
        server = HTTPServer(("127.0.0.1", port), Handler)
        server.shows_archived = shows_archived
        server.verified = {}
    except OSError as err:
        if err.errno not in (48, 98):
            raise
        print(f"port {port} is taken; a dashboard may already be serving http://127.0.0.1:{port}", file=sys.stderr)
        return 1
    print(f"robowright-dash on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


def write_once(out: Path, shows_archived: bool) -> int:
    out.mkdir(parents=True, exist_ok=True)
    projects, orphans = load_world(None, shows_archived, None)
    (out / "index.html").write_text(render_index(projects, orphans, lambda name: f"{quote(name, safe='')}.html"))
    for p in projects:
        (out / f"{p['name']}.html").write_text(render_project_page(p, "index.html"))
    print(f"wrote {out / 'index.html'} and {len(projects)} project page(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", nargs="?", help="one project folder name under the projects root")
    parser.add_argument("--serve", type=int, metavar="PORT")
    parser.add_argument("--once", type=Path, metavar="DIR")
    parser.add_argument("--all", action="store_true", help="show archived projects and their sessions too")
    parser.add_argument("--runs-root", metavar="DIR",
                        help="the sessions root. Default: $ROBOWRIGHT_SESSIONS_ROOT, else sessions_root in launch.json")
    parser.add_argument("--projects-root", metavar="DIR",
                        help="the projects root. Default: $ROBOWRIGHT_PROJECTS_ROOT, else projects_root in launch.json, "
                             "else the sessions root's parent")
    args = parser.parse_args()
    global SESSIONS_ROOT, PROJECTS_ROOT
    roots = ROSTER.sessions_roots([args.runs_root] if args.runs_root else None, LAUNCH_SETTINGS, LAUNCH_UNREAD)
    if roots is None:
        return 2
    SESSIONS_ROOT = Path(roots[0])
    projects = (os.path.expanduser(args.projects_root or os.environ.get("ROBOWRIGHT_PROJECTS_ROOT") or "")
                or ROSTER.launch_path(LAUNCH_SETTINGS, "projects_root"))
    PROJECTS_ROOT = Path(projects) if projects else SESSIONS_ROOT.absolute().parent
    if args.serve:
        return serve(args.serve, args.all)
    if args.once:
        return write_once(args.once, args.all)
    # Naming a project is asking for it, archived or not.
    projects, orphans = load_world(args.project, args.all or args.project is not None, None)
    if args.project and not projects:
        print(f"no project folder {args.project} with a PROJECT.md under {PROJECTS_ROOT}", file=sys.stderr)
        return 2
    print(text_summary(projects, [] if args.project else orphans, detailed=bool(args.project)))
    found = untrusted()
    if found:
        print(OWNER_GIT.shown(f"robowright-dash: {found[0]}: {found[1]}"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
