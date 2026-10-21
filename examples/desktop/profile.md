ILLUSTRATIVE — read by no suite and tested by nothing; `examples/laptop/` is the tested install.

# Machine profile — example: a headless Mac over SSH, `paste` launch, dollar budget

An example install for a headless desktop Mac reached over SSH, whose Claude Code settings do not
let a session start a background session. Copy it to `~/.claude/robowright/profile.md`, beside a
copy of `examples/desktop/launch.json`, and replace what differs. Every name, path and number
below is invented. Seven sections, fixed order, per `skills/robowright/PROFILE-CONTRACT.md`; a
section that does not apply says `None on this machine.`

---

## 1. Identity

| | |
|---|---|
| Machine | The Owner's headless desktop Mac, reached over SSH from their laptop |
| Organisation | None. No employer, no managed settings, no org policy |
| Owner | The person who owns this machine and every repository Robowright works in here |

Robowright works in the repos whose hooks `robowright-resolve` finds on this Mac:
`~/.claude/robowright/projects/*.md` plus any checkout's own `.claude/robowright/project.md`.

Per-project settings: `robowright.json` in the project folder.

---

## 2. Launch

**One runtime: the Claude Code CLI on this Mac, in SSH sessions the Owner opens.** `launch.json`
sets `"launch": "paste"`: no session here starts another. The Lead runs the launcher, which
starts nothing, prints the line under `paste this yourself:`, and appends a `hand-off via`
ledger entry. The Owner pastes that line into a fresh SSH shell on this Mac, in the worktree the
line names, then gives the Lead the session's id for `--pin`. Dry-run first, always.

| To | Command |
|---|---|
| Hand off a Worker | `run-launch.sh --run-dir <session_dir> --dry-run`, then `--yes`; the Owner pastes the printed line |
| Record a pasted hand-off | `run-launch.sh --run-dir <session_dir> --pin <id>` — `<id>` from `claude agents --json`, the row whose `cwd` is the worktree |
| Resume a stopped Worker | `run-launch.sh --run-dir <session_dir> --resume --yes`, pasted the same way — the first prompt is `/worker <session_dir>` followed by one of the launcher's two fixed sentences — the newest `LEDGER.md` entry holds the decision, or nothing is waiting |
| Rotate at a unit boundary | Stop the previous session, then `run-launch.sh --run-dir <session_dir> --rotate --yes`, pasted the same way |
| Stop a live session | `claude stop <id>`, the eight-character id `claude agents --json` prints. The out-of-band stop a Worker honours is `<session_dir>/STOP` |
| Start a Planner or the Lead by hand | `role-start planner [project]` · `role-start lead [project]` |
| Start an Explainer | `run-launch.sh --explainer guide --project <project dir> --run-dir <session_dir> --yes`, pasted the same way |

**Observing a live Robowright Session:** `python3 ~/.claude/skills/lead/scripts/run-roster.py`,
one row per session derived from the session dirs; `claude attach <id>` and `claude logs <id>`
from any SSH shell on this Mac. The Lead messages a live session with `SendMessage`, and arms
`SendMessage … notify_when_idle: true` for a one-shot notice when it next goes idle.

**What each session may write** rides in the `--settings` the launcher and `role-start` pass, from
`launch.json` (`SECURITY.md` → What each role can write); the Owner's own settings grant sessions nothing more here:

| Session | Writes |
|---|---|
| Worker | its worktree, `~/robowright/robowright-sessions/<slug>/`, `~/robowright/accounting/`; both repositories' whole git directories and any `.git` under its grants denied, so it writes git through `rw-git` |
| Planner, Explainer | `~/robowright/projects/`, `~/robowright/robowright-sessions/` |
| Lead, a hand-started Planner | those two and `~/robowright/accounting/` |

**Concurrency: one Robowright Session per lock name at a time.** The launcher refuses a second
holder of any name in `run.json.locks`.

---

## 3. Budget

**Measured in dollars.** Sessions here bill an API key per token.

**What the brief carries:** `spend_threshold_usd` and `spend_cap_usd`, plus `max_wall_hours`
and the verification ceilings (`max_mutation_rounds_per_unit`, `whole_suite_runs_owed`,
`max_extra_review_subagents`).

**The enforcement is `spend-guard.py`.** The Lead starts
`python3 ~/.claude/skills/lead/scripts/spend-guard.py --watch 60` in the background on its first
tick and checks it on each tick after. It prices each session's transcripts, writes a warning
and a `LEDGER.md` entry at `spend_threshold_usd`, and writes `<session_dir>/STOP` at
`spend_cap_usd`. A brief with neither field set is not enforced.

**The cost line in a ledger entry** quotes the `per request:` and `estimated usd:` lines of
`run-cost.py`.

**The prices are `skills/robowright/pricing.json`**, which the Owner keeps current.
`spend-guard.py`, `run-cost.py` and `robowright-cost.py` all price from it, so a cap is enforced
at whatever rates it holds. Each text report prints `prices as of <updated_at>`, and each warns
on stderr once that date is more than 30 days old. Without the file, every USD figure is null and
`spend-guard.py` neither warns at a threshold nor writes a STOP.

**Where the money went, across sessions,** is the accounting ledger (§6), summed by
`robowright-cost.py` (§4) per project, unit, role or model.

**The Lead's own session** hands off to a fresh one when its context has compacted once, or when
the roster's `lead:` line passes 300 requests — on a per-token bill, context re-read on every
request is the cost.

---

## 4. Tools

| Job | Tool | Fallback |
|---|---|---|
| Commit | `rw-git add <paths>`, then `rw-git commit --message-file <file>`, the message written into the session folder | — |
| Git wrapper | None on this machine; reads run `git` directly, and every write to the git directory runs `rw-git` | — |
| Push | **None.** Nothing in Robowright pushes here — see §5 | — |
| Build / test log verdict | The `log-reader` agent | `tail -3` of the log |
| Ledger append | The `Write` / `Edit` tool, one append of at most 25 lines | — |
| Cost | `python3 ~/.claude/skills/worker/scripts/run-cost.py --run-dir <session_dir> --write` | The Lead backfills it at intake |
| Spend by project, unit, role or model | `python3 ~/.claude/skills/robowright/scripts/robowright-cost.py --by project\|unit\|role\|model`, with `--since YYYY-MM-DD`, `--project <name>` or `--json`; `--migrate` backfills the ledger from finished sessions | `run-cost.py --run-dir <session_dir>`, one session at a time |
| Dashboard: every project and session, with spend | `python3 <clone>/tools/robowright-dash.py [<project>] [--serve PORT\|--once DIR]`, run from the clone — `tools/` is not linked. Sessions root from `--runs-root`, `$ROBOWRIGHT_SESSIONS_ROOT` or `launch.json`'s `sessions_root`; projects root from `--projects-root`, `$ROBOWRIGHT_PROJECTS_ROOT`, `launch.json`'s `projects_root`, else the sessions root's parent | The roster, `run-roster.py` |

---

## 5. Owner-only floor

Beyond the floor every profile shares — money, shipping a behaviour change, schema or public
API, reversing a settled decision, anything another person reads — these are the Owner's alone
on this machine:

- **any push**, to any remote, on any branch
- **raising a brief's `spend_cap_usd`**, or running `spend-guard.py --cap` above it
- **new dependencies**
- **deleting branches or worktrees**

---

## 6. Paths

| What | Where |
|---|---|
| Launcher settings | `~/.claude/robowright/launch.json` |
| Sessions root | `~/robowright/robowright-sessions/<slug>/` — `launch.json`'s `sessions_root` |
| Accounting root | `~/robowright/accounting/` — `launch.json` names no `accounting_root`, so it is `accounting` beside the sessions root: the ledger `records.jsonl`, its lock `.records.lock`, and the launch index `launches.jsonl`, which the launcher writes only in `auto` mode, so never on this machine |
| Project folders | `~/robowright/projects/<project>/` — `launch.json`'s `projects_root` |
| Trusted repositories | `~/robowright/src/sample-app` and `~/robowright/src/sample-api` — `launch.json`'s `repos`. `accept.sh`, the launcher, the dashboard and the cost tools run git only in a worktree of a repository listed there and named by a project's `robowright.json`; a new repository gets its line there before its first session |
| Owner briefs | `~/robowright/projects/<project>/reviews/<slug>-owner-brief.md` |
| Decision logs | `~/robowright/projects/decision-logs/` — under the projects root, which every role but the Worker may write |
| Inbox — agent output with no better home | `~/robowright/projects/inbox/` — the same |
| Owner rules | None on this machine |

---

## 7. Duties

| Role | Extension point | Run |
|---|---|---|
| Planner | `planner.brief` | None. |
| Worker | `worker.preflight` | None. |
| Worker | `worker.unit-gate` | None. |
| Worker | `worker.publish` | None. |
| Lead | `lead.tick` | None. |
| Lead | `lead.intake` | None. |
| Lead | `lead.post-publish` | None. |
| Explainer | `explainer.publish` | None. |
| Reviewer | `reviewer.overlay` | None. |
