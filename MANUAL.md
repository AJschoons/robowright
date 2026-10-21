# Running a project with Robowright

This page holds the commands for running a project, one task at a time, and links to the file that
carries the rest. Anything it does not cover, including how to adapt or improve the system for your
setup, is asked with `/robowright help <your question>`: the agent reads the repo and answers. It is
told to change nothing, and a session started in [plan mode](https://code.claude.com/docs/en/permission-modes)
(`claude --permission-mode plan`) also blocks edits until you approve a plan, except in an interactive
terminal session with bypass permissions available.

Below, `<clone>` is your clone of Robowright, `<project>` a project folder's name under your projects
root and `<project_dir>` its path, `<session_dir>` one Robowright Session's folder under your
sessions root, and `<unit>` a unit's name; any other value in angle brackets is yours to fill in.

## Before the first project

To set up a machine, clone Robowright into a folder no Claude Code session is granted, link it, and
run the onboarding interview. It writes your machine profile, `launch.json` and a first project hook,
links `role-start`, `run-launch.sh`, `claude-usage` and `usage-guard` into `~/.local/bin`, and on a
subscription points you at the status line to paste into your own settings. It ends on a green
`tests/run.sh`. A session is granted the folder it starts in, so start the onboarding session from a
folder that is not the clone, for the reason "Where to clone it" gives, not your home folder and not
`~/.claude`; an empty folder beside `<clone>` will do.

```sh
git clone https://github.com/AJschoons/robowright.git <clone>
bash <clone>/install.sh
claude    # then, inside the session: /robowright-onboard
```

Depth: [`skills/robowright-onboard/SKILL.md`](skills/robowright-onboard/SKILL.md), and
[`README.md` → Where to clone it](README.md#where-to-clone-it).

## Plan a project

To plan a project, start a Planner with no project name, since `role-start` refuses a project with no
`robowright.json` and the Planner writes it; `role-start` also passes the Planner's write grants. Then
paste the kickoff. You answer the time box, the Robowright settings and the fit calls. It ends when
`PROJECT.md`, one exploration doc per **unit** (one reviewable change) and the first **brief** exist: the
contract a **Robowright Session**, one unattended Worker in its own worktree, builds to.

```
role-start planner
Run the `planner` skill from scratch for project `<project>`. Inputs: time box = `<X weeks or none>`, designs = `<link or N/A>`, prior discussion = `<links or N/A>`, related tracker items = `<comma list or N/A>`, related docs = `<paths/links or N/A>`. Start with Phase 1; ask me for anything missing before proceeding.
```

Depth: [`skills/planner/SKILL.md` → Planner kickoff](skills/planner/SKILL.md#planner-kickoff-copy-paste-this-to-start-a-new-project),
and [`skills/robowright/OWNERS-GUIDE.md` → Decisions, in order](skills/robowright/OWNERS-GUIDE.md#decisions-in-order).

## Start it

To start a planned project, start the Lead and put it on its watch (the example `launch.json` sends
`/loop /lead watch` as its first prompt, so type it only where yours does not). The Lead launches each
Robowright Session through `run-launch.sh`, a dry run first and then `--yes`. Under `launch: paste`, the
default, the launcher starts nothing: it prints `paste this yourself:` and a `claude --bg` line for you
to run in a terminal, and once you say it ran, the Lead records the session with `--pin`.

```
role-start lead <project>
/loop /lead watch    # only if your launch.json sends the Lead no first prompt
```

Depth: [`skills/lead/SKILL.md` → Launch hand-off](skills/lead/SKILL.md#launch-hand-off).

## Watch it

Ask the Lead, or read it from disk: the roster gives each Robowright Session a verdict, the dashboard
serves a read-only page per project on `127.0.0.1`, `session-state.py` gives one session's state and
what may happen next, and its `LEDGER.md` what it did. The Lead hands you a watch command for each
session it starts (`claude attach <id>`, `claude logs <id>` in the example profiles). To stop one,
create `<session_dir>/STOP`; the Lead brings you a stop that is yours, and records your answer.

```
python3 <clone>/skills/lead/scripts/run-roster.py
python3 <clone>/tools/robowright-dash.py --serve 8765
python3 <clone>/skills/robowright/scripts/session-state.py <session_dir> status
```

Depth: [`skills/robowright/OWNERS-GUIDE.md` → Where to look](skills/robowright/OWNERS-GUIDE.md#where-to-look).

## A small piece of work

A **direct build** is a unit sized S or below: no Robowright Session folder, no `run.json`, one
session building from a briefing. The Lead asks a Planner for the briefing, then launches it with the
launcher's `--direct` line, dry run first. For a one- to three-hour ask too small for a project plan,
type `/one-off <ask>` in plan mode: you plan it in your own console as a one-unit project, and one
Worker builds it, usually on Sonnet, with no Lead.

```
run-launch.sh --direct --project <project_dir> --slug <unit> --repo <repo> --base <full commit id> --briefing <project_dir>/briefings/<unit>.md --dry-run
/one-off <ask>
```

Depth: [`skills/lead/SKILL.md` → Launch hand-off](skills/lead/SKILL.md#launch-hand-off), and
[`skills/one-off/SKILL.md`](skills/one-off/SKILL.md).

## The levers

The **run profile** is a brief's one dial: `showcase` puts every Worker on Opus, `standard` (the
default) puts tests, docs and refactor units on Sonnet, and `economy` also drops their effort to low
and runs the Planner on Opus. The launcher's `--model` and `--effort` beat it for one launch. The
**delegation level** and the rest of `robowright.json` are set once, at kickoff:

| Key | Sets |
|---|---|
| `delegation` | Who answers a stop below the Owner-only floor: `owner`, `lead` or `planner` (the default) |
| `models` | The model for each role |
| `plan_review` | Where the Planner's intent review runs: `finish` (the default), `per-unit` or `off` |
| `owner_brief` | Whether the Explainer writes an owner brief for each published stack |
| `project_report` | Whether the Explainer writes the end-of-project report |
| `owner_only` | That floor: the decisions that always stop for you, which every brief's **one-way doors** start from |
| `repos` | The project's repositories, by name, path and origin |

```
run-launch.sh --run-dir <session_dir> --model sonnet --effort medium --dry-run
```

Depth: [`skills/planner/SKILL.md` → Run profile](skills/planner/SKILL.md#run-profile--one-field-per-brief),
[→ Robowright settings](skills/planner/SKILL.md#robowright-settings--decided-once-at-kickoff), and
[`skills/planner/ROBOWRIGHT-TEMPLATE.json`](skills/planner/ROBOWRIGHT-TEMPLATE.json).

## When the plan changes

For an ask the plan does not cover, the Lead writes a diagnosis note and asks a Planner for one
brief. To re-cut the plan itself (new units, a renumbering), run a replan Planner, which grills the
ask with you in the chat. A Robowright Session that stopped three times gets a rebrief: a fresh
Planner rewrites its brief.

```
/planner brief <unit>              # the Lead starts this Planner
/planner replan <project> <ask>    # you start this one
/planner rebrief <session_dir>     # the Lead starts this Planner
```

Depth: `skills/planner/SKILL.md` → [Brief-only session](skills/planner/SKILL.md#brief-only-session-every-unit-after-the-first),
[Replan session](skills/planner/SKILL.md#replan-session-the-owner-changes-the-plan) and
[Rebrief session](skills/planner/SKILL.md#rebrief-session-a-robowright-sessions-third-stop).

## Spend

On a subscription, `claude-usage` prints the 5-hour and 7-day plan usage (exit `3`: stale, `4`: none),
and at a threshold `usage-guard` writes `STOP` into every running or resumable session.
`robowright-cost.py` says where the tokens went, `run-cost.py` what one session cost, and `/spend-debug`
where to cut. Dollars are estimates: `robowright-cost.py` and the dashboard show them only where a brief
sets a spend threshold or cap; `run-cost.py` always does, meaningful only under a dollar budget.

```
claude-usage
usage-guard --threshold 85 --watch 60
python3 <clone>/skills/robowright/scripts/robowright-cost.py --by project    # or unit, role, model
python3 <clone>/skills/worker/scripts/run-cost.py --run-dir <session_dir>
/spend-debug <project>
```

Depth: [`skills/robowright/OWNERS-GUIDE.md` → Accounting](skills/robowright/OWNERS-GUIDE.md#accounting).

## Finish

To accept finished work, run the line the Lead hands you, the first form for a Robowright Session
and the second for a direct build, with the full id of the reviewed tip; `-S` signs the squash. It
prints the worktree teardown, which is yours to run. The Explainer writes an owner brief for you to
read before each review; after the last unit, with `project_report` on, the Lead starts an Explainer
in report mode, which writes `<project_dir>/REPORT.md`.

Read the line before you run it. A line a Worker or a direct build wrote is session text: compose it
yourself from the build's base, `git rev-parse` of the reviewed tip in your main clone and the hook's
message path, or check every word and `--tip` against what you reviewed. With `-S` and
`gpg.format=ssh`, git writes the commit it signs to a file in `$TMPDIR` for `ssh-keygen` to read, so
a live session could have your key sign other bytes; [`SECURITY.md` → Values a session can
write](SECURITY.md#values-a-session-can-write) says why.

```
~/.claude/skills/lead/scripts/accept.sh [-S] --tip <tip> --message <session_dir>/prs/<unit>/commit-message.txt <session_dir>
~/.claude/skills/lead/scripts/accept.sh --direct [-S] --base <base> --tip <tip> --message <project_dir>/prs/<unit>/commit-message.txt <project_dir> <unit>
/explainer report <project>    # the Lead starts this Explainer
```

Depth: [`skills/lead/SKILL.md` → What already exists](skills/lead/SKILL.md#what-already-exists--use-it-do-not-rebuild-it),
and [`skills/explainer/SKILL.md` → Mode: report](skills/explainer/SKILL.md#mode-report).

## Anything else

This page is the basics. Anything it does not cover, including how to adapt or improve the system for
your setup, is asked with `/robowright help <your question>`: the agent reads the repo and answers.
It is told to change nothing, and a session started with `claude --permission-mode plan` also blocks
edits until you approve a plan, except in an interactive terminal session with bypass permissions
available.
