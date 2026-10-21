# Machine profile — example: one personal Mac, `paste` launch, `auto` opt-in, plan-usage budget

An example install. Copy it to `~/.claude/robowright/profile.md`, beside a copy of
`examples/laptop/launch.json`, and replace what differs. Every name, path and number below is
invented. Seven sections, fixed order, per `skills/robowright/PROFILE-CONTRACT.md`; a section
that does not apply says `None on this machine.`

---

## 1. Identity

| | |
|---|---|
| Machine | The Owner's laptop |
| Organisation | None. No employer, no managed settings, no org policy |
| Owner | The person who owns this machine and every repository Robowright works in here |

Robowright works in the repos whose hooks `robowright-resolve` finds on this Mac:
`~/.claude/robowright/projects/*.md` plus any checkout's own `.claude/robowright/project.md`.
This install starts with one: `projects/sample.md`, for `example-org/sample`.

Per-project settings: `robowright.json` in the project folder.

---

## 2. Launch

**One runtime: the Claude Code CLI on this Mac, on one subscription.** The Owner and the Lead
work in CLI sessions; every other role starts as a CLI background session:

```
claude --bg --model <m> --name <name> "/worker <session_dir>"
```

through the launcher, `run-launch.sh` (linked into `~/.local/bin`). This example's `launch.json`
sets `"launch": "paste"`: the launcher prints the line under `paste this yourself:`, the Owner
pastes it into a terminal on this Mac, and `--pin <id>` records it. Under `"launch": "auto"` the
launcher runs the line itself, and prints it as above only when the shell it runs in cannot start
a background session. `auto` is the opt-in (`SECURITY.md` → The threat model). Dry-run first,
always.
Nothing else starts a Worker here, so the Owner's `settings.json` adds the optional
`"skillOverrides": {"worker": "user-invocable-only"}` (`SECURITY.md` → What each role can write).

| To | Command |
|---|---|
| Launch a Worker | `run-launch.sh --run-dir <session_dir> --dry-run`, then `--yes` |
| Resume a stopped Worker | `run-launch.sh --run-dir <session_dir> --resume --yes` — the session's first prompt is `/worker <session_dir>` followed by one of the launcher's two fixed sentences — the newest `LEDGER.md` entry holds the decision, or nothing is waiting — never free text |
| Record a pasted hand-off | `run-launch.sh --run-dir <session_dir> --pin <id>` — `<id>` from `claude agents --json`, the row whose `cwd` is the worktree |
| Rotate at a unit boundary | Stop the previous session, then `run-launch.sh --run-dir <session_dir> --rotate --yes` |
| Stop a live session | `claude stop <id>`, the eight-character id `claude agents --json` prints. The out-of-band stop a Worker honours is `<session_dir>/STOP` |
| Start a Planner or the Lead by hand | `role-start planner [project]` · `role-start lead [project]` — model, effort and name from `launch.json` → `roles`; with a project, the model from its `robowright.json` → `models` |
| Start a Planner for a brief | `run-launch.sh --planner brief --project <project dir> --slug <slug> --dry-run`, then `--yes` |
| Start an Explainer | `run-launch.sh --explainer guide --project <project dir> --run-dir <session_dir> --yes` |
| Start a direct build | `run-launch.sh --direct --project <project dir> --slug <unit> --repo ~/Code/sample --base <full commit id> --briefing <project dir>/briefings/<unit>.md --dry-run`, then `--yes` — it makes the worktree and starts `build-<unit>` in it |

The launcher prints a `model:` and an `effort:` line naming where each came from. Read both
before `--yes`.

**Observing a live Robowright Session:** `python3 ~/.claude/skills/lead/scripts/run-roster.py`,
one row per session derived from the session dirs on every call; `claude attach <id>` and
`claude logs <id>`, handed to the Owner in the message that starts a session;
`claude agents --json` for what is alive. The Lead messages a live session with `SendMessage`,
and arms `SendMessage … notify_when_idle: true` for a one-shot notice when it next goes idle.

**What each session may write** rides in the `--settings` the launcher and `role-start` pass, from
`launch.json` (`SECURITY.md` → What each role can write). The Owner's own `settings.json` grants no
`additionalDirectories` and no `allowWrite`, since a folder granted there reaches every launched session too
(`SECURITY.md` → The recommended setup):

| Session | Writes |
|---|---|
| Worker | its worktree, `~/Projects/robowright-sessions/<slug>/`, `~/Projects/robowright-accounting/`; `~/Code/sample/.git` and any `.git` under its grants denied, so it writes git through `rw-git` |
| Planner, Explainer | `~/Projects/`, `~/Projects/robowright-sessions/` |
| Lead, a hand-started Planner | those two and `~/Projects/robowright-accounting/` |

The launcher makes a missing Worker worktree at `~/Code/sample/.worktrees/<slug>`, and a direct build's at
`~/Code/sample/.worktrees/<unit>` (`--direct`), which then gets a Planner's grants and commits through `rw-git`. The fallback where the
launcher cannot run: the Owner runs the hook's `git worktree add` line, then, from the worktree,
`s="$(python3 ~/.claude/skills/robowright/scripts/role_grants.py document)" && claude --bg --settings "$s" …`. A
build started by hand gets only its own command line's grants.

**Concurrency: one Robowright Session per lock name at a time.** A brief lists its locks in
`run.json.locks`; the launcher refuses a second holder of any listed name. Reviewers, Readers,
a Planner, and any session whose `locks` is empty may overlap a holder.

---

## 3. Budget

**Measured in plan usage and wall hours, never dollars.** The subscription is not billed per
token, so no role estimates, enforces or reports a dollar figure.

**What the brief carries:** `max_wall_hours` and the verification ceilings
(`max_mutation_rounds_per_unit`, `whole_suite_runs_owed`, `max_extra_review_subagents`).
`spend_threshold_usd` and `spend_cap_usd` stay `null`.

**The reading is `claude-usage`**, before every launch and on every Lead tick: the 5-hour and
weekly percentages, each with its reset time, and the reading's age; `--json` for a script. The
Lead does not start a Robowright Session when the 5-hour window is above 70% or the weekly above
85%, and says which number blocked it.

**The reading comes from the status line.** `usage-tap.py` records each API response's usage to
`~/.claude/usage/latest.json`; the `statusLine.command` that runs it is text in
`skills/robowright/OWNERS-GUIDE.md`, pasted into the Owner's own settings. `claude-usage` exits 3
when the reading is older than 15 minutes and 4 when there is none. **Stale or missing is never
"under"**: the Lead refreshes the reading before a launch, or asks the Owner.

**The enforcement is `usage-guard`, at a ceiling of 90%.** The Lead starts
`usage-guard --threshold 90 --watch 60` in the background on its first tick and checks it on
each tick after. At or above the ceiling in either window, on a fresh reading, it writes
`<session_dir>/STOP` into every Robowright Session whose `phase` is not `done`, one line naming
the window, the percentage and the reset. It never overwrites a STOP. The ceiling moves only on
the Owner's word.

**The cost line in a ledger entry** quotes requests, tokens by class, and average context per
request, from `run-cost.py`. Never a dollar figure.

**Where the usage went, across sessions,** is the accounting ledger (§6), summed by
`robowright-cost.py` (§4): requests, tokens, active hours and the last plan % per project, unit,
role or model. Its `est usd` column comes from `skills/robowright/pricing.json`, which the Owner
keeps current; here it is an estimate nobody is billed, and no role quotes it.

**The Lead's own session** hands off to a fresh one when its context has compacted twice. The
roster is derived from disk on every call, so a fresh Lead loses nothing.

---

## 4. Tools

| Job | Tool | Fallback |
|---|---|---|
| Commit | `rw-git add <paths>`, then `rw-git commit --message-file <file>`, the message written into the session folder | — |
| Git wrapper | None on this machine; reads run `git` directly, and every write to the git directory runs `rw-git` | — |
| Push | **None.** Nothing in Robowright pushes here — see §5 | — |
| Build / test log verdict | The `log-reader` agent | `tail -3` of the log |
| Ledger append | The `Write` / `Edit` tool, one append of at most 25 lines; detail goes to an evidence file, cited by path | — |
| Cost | `python3 ~/.claude/skills/worker/scripts/run-cost.py --run-dir <session_dir> --write` | The Lead backfills it at intake |
| Spend by project, unit, role or model | `python3 ~/.claude/skills/robowright/scripts/robowright-cost.py --by project\|unit\|role\|model`, with `--since YYYY-MM-DD`, `--project <name>` or `--json`; `--migrate` backfills the ledger from finished sessions | `run-cost.py --run-dir <session_dir>`, one session at a time |
| Dashboard: every project and session, with spend | `python3 <clone>/tools/robowright-dash.py [<project>] [--serve PORT\|--once DIR]`, run from the clone — `tools/` is not linked. Sessions root from `--runs-root`, `$ROBOWRIGHT_SESSIONS_ROOT` or `launch.json`'s `sessions_root`; projects root from `--projects-root`, `$ROBOWRIGHT_PROJECTS_ROOT`, `launch.json`'s `projects_root`, else the sessions root's parent | The roster, `run-roster.py` |

---

## 5. Owner-only floor

Beyond the floor every profile shares — money, shipping a behaviour change, schema or public
API, reversing a settled decision, anything another person reads — these are the Owner's alone
on this machine:

- **any push**, to any remote, on any branch
- **any deploy**
- **signing, keystore or store-console anything**
- **version or build-number changes**
- **new dependencies**
- **deleting branches or worktrees**

---

## 6. Paths

| What | Where |
|---|---|
| Launcher settings | `~/.claude/robowright/launch.json` — the sessions root, owner-brief directory, report scope and unit shape the launcher reads |
| Sessions root | `~/Projects/robowright-sessions/<slug>/` — `launch.json`'s `sessions_root`, which every script that lists sessions reads when no `--runs-root` or `$ROBOWRIGHT_SESSIONS_ROOT` is given |
| Accounting root | `~/Projects/robowright-accounting/` — `launch.json`'s `accounting_root`, unless `$ROBOWRIGHT_ACCOUNTING_ROOT` is set: the ledger `records.jsonl`, its lock `.records.lock`, and the launch index `launches.jsonl` |
| Project folders | `~/Projects/<project>/` — `launch.json`'s `projects_root` |
| Trusted repositories | `~/Code/sample` — `launch.json`'s `repos`. `accept.sh`, the launcher, the dashboard and the cost tools run git only in a worktree of a repository listed there and named by a project's `robowright.json`; a new repository gets its line there before its first session |
| Owner briefs | `~/Projects/<project>/reviews/<slug>-owner-brief.md` |
| Decision logs | `~/Projects/decision-logs/` |
| Inbox — agent output with no better home | `~/Projects/inbox/` |
| Owner rules | None on this machine |

---

## 7. Duties

The project hook (→ Duties) may list duties at any extension point too. A handbook reaching one
runs every duty listed here, then the hook's, in order, and nothing when both list none.

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
| Reviewer | `reviewer.overlay` | `~/.config/robowright/review-overlay.md` — this install's copy of `examples/laptop/review-overlay.md` |
