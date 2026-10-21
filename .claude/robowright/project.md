# Project hook — robowright (this repository)

In-repo hook, per `skills/worker/PROJECT-HOOK.md` resolution rule 1: it travels with every
checkout, and is the worked example of a hook for a repository that installs by linking its own
files into `~/.claude`. Fourteen sections, fixed order; a section that does not apply says
`None in this repository.`

Commands verified against the tree as each unit is accepted; a row that names a unit is written by
that unit and does not exist before it.

## 1 · Identity

| | |
|---|---|
| Origin | `git@github.com:AJschoons/robowright.git` — match on `AJschoons/robowright` |
| Main clone | Wherever this checkout is; every path below is relative to `git rev-parse --show-toplevel` |
| Base ref | `main` |
| Artifact ids | None. Nothing is built or installed from this repo except symlinks |

**Clients**

None in this repository.

**The live `~/.claude/` tree may be this repo's main clone, through symlinks** (`skills/` and
`agents/` are what `install.sh` links). A session running from a worktree edits copies that
nothing links to until the Owner accepts the change and re-runs `install.sh`.

## 2 · Preflight extras

- `git status --short` on the main clone is empty, or every line is explained in the ledger. A
  dirty main clone is not this session's to touch; note it and continue.
- `git config core.hooksPath` prints `tools/hooks` — the scrub gate is wired. Missing → stop,
  `verification-failed`: nothing commits here without the gate.
- `test -r "${ROBOWRIGHT_DENYLIST:-$HOME/.config/robowright/denylist}"` — the gate's pattern
  list exists. Missing → stop, `verification-failed`.

## 3 · Worktree

Worktrees live inside the repo at `.worktrees/<slug>`, excluded by `.gitignore` and by
`.git/info/exclude`; `install.sh` links only `skills/` and `agents/`, so a worktree is never installed.

```sh
git worktree add -b robowright/<slug> "$(git rev-parse --show-toplevel)/.worktrees/<slug>" main
```

- Branch `robowright/<slug>`, `<slug>` matching the session directory's; unit N of a stack is
  `robowright/<slug>-u<N>`.
- A worktree made before U46 at `.claude/worktrees/<slug>` keeps working, for the launcher and
  rw-git alike, until it is torn down; a new one is made there only for a session whose
  `run.json` already names that place. A `**/.claude` deny in a machine's settings makes its files
  unwritable to a session.
- **Never run `install.sh` from a worktree against the real `$HOME`.** An install check runs on
  a scratch `HOME` only (→ 6).
- Teardown: removing the worktree and deleting the branch are Owner-only; hand the Owner the
  commands.

## 4 · Build

No compiled product. The build step is a syntax pass over every changed script, redirected to
`<session_dir>/evidence/build-<unit>.log`:

```sh
git diff --name-only --diff-filter=d <base>..HEAD -- '*.py' | xargs -r python3 -m py_compile; echo "EXIT=$?"
git diff --name-only --diff-filter=d <base>..HEAD -- '*.sh' 'tools/hooks/*' | xargs -r -n1 bash -n; echo "EXIT=$?"
git diff --name-only --diff-filter=d <base>..HEAD -- 'site/*.js' 'site/*.mjs' | xargs -r -n1 node --check; echo "EXIT=$?"
```

- **Verdict**: the three `EXIT=` lines, all `0`. Read by the `log-reader` agent or by `grep '^EXIT='`.
- **Build output directory**: none; `run.json.build_output` stays `""`.
- **Hang**: none possible; both commands finish in seconds. No output after 60 s is a machine problem.
- **Infrastructure failure**: `python3`, `bash` or `node` missing from `PATH`. Not a verdict; stop `verification-failed`.
- **Gate command**: None in this repository.

## 5 · Tests

One runner, `tests/run.sh` (written by unit `001-tracer`), runs every suite below from the repo
root and ends with the whole-tree scrub check, redirected to a log:

| Suite | Command | Ships in |
|---|---|---|
| scrub gate | `python3 tests/scrub-gate/test_scrub_gate.py` | In tree |
| role launcher | `python3 tests/role-start/test_role_start.py` | In tree |
| session state | `python3 skills/robowright/scripts/test_session_state.py` | In tree; its launch probe runs `examples/laptop/launch.json` |
| owner git | `python3 skills/robowright/scripts/test_owner_git.py` | In tree; scratch repos and a scratch projects root, a `git` on PATH that records argv |
| robowright-resolve | `python3 skills/robowright/scripts/test_robowright_resolve.py` | In tree |
| run roster | `python3 skills/lead/scripts/test_run_roster.py` | In tree |
| budget modes | `python3 skills/lead/scripts/test_budget_modes.py` | In tree; one `ok` line per check |
| accept | `python3 skills/lead/scripts/test_accept.py` | In tree; a synthetic repo under a scratch dir, never the main clone |
| run cost | `python3 skills/worker/scripts/test_run_cost.py` | In tree |
| cost rollup | `python3 skills/robowright/scripts/test_robowright_cost.py` | In tree |
| pricing | `python3 skills/robowright/scripts/test_pricing.py` | In tree |
| launcher | `python3 tests/run-launch/test_run_launch.py` | In tree |
| rw-git | `python3 tests/rw-git/test_rw_git.py` | In tree; scratch `$HOME`, scratch repos, a bare scratch origin and a local HTTP origin |
| plan usage | `python3 tests/usage/test_usage.py` | In tree |
| dashboard | `python3 tests/dash/test_dash.py` | In tree; a scratch `$HOME`, scratch roots and scratch git repos |
| install | `python3 tests/install/test_install.py` | In tree; a scratch `$HOME` and a synthetic clone, never the real `$HOME` |
| conventions | `python3 tests/conventions/test_conventions.py` | In tree; fixtures in a scratch root, the pre-commit hook in scratch git repos, then `tests/conventions/lint.py` over this tree |
| Whole-tree scrub | `tools/scrub-gate.sh --tree` | `001-tracer` |

- **Verdict lines**: `Ran N tests in …` then `OK`, or `FAILED (failures=F, errors=E)`; exit code
  `0` / `1`. Budget modes prints one `ok` line per check and ends `all passed`, exit `0`. The
  scrub check prints `scrub: clean` or one `scrub: <file>:<line>: denylist:<n>` per hit, `<n>`
  the matching pattern's line in the denylist; it never prints a pattern. A file name that
  matches is a hit of its own, `scrub: (name withheld):0: denylist:<n>`, and prints as
  `(name withheld)` in every hit line. `tests/run.sh` prints one line per suite and ends
  `EXIT=<n>`. Read by `log-reader` or `tail -3`; never a grep for a test name.
- **Scoping**: `python3 -m unittest <module>.<Class>.<test>` from the suite's directory; a unit
  that touches none of the areas runs none scoped and still owes the whole-suite run below.
- **Hang**: every suite fakes `claude` and `git` remotes; each finishes in about a minute or less.
  No line for 120 s is a hang. Kill, re-run once; twice is a gate failure.
- **Infrastructure failure**: `python3` missing.
- **Whole suite** = `tests/run.sh`; about 90 s, most of it session state.
- **Source-file patterns** (a commit touching any owes the whole suite): `*.py`, `*.sh`,
  `tools/hooks/*`, `tests/conventions/allowlist.txt`. Markdown, JSON under `examples/`, and evidence owe nothing.

### The site suites

The promo site under `site/` has two suites of its own, outside `tests/run.sh`. Both run from the
repo root.

| Suite | Command | Ships in |
|---|---|---|
| site kit | `node --test --test-reporter=tap 'site/tests/*.test.mjs'` | `robowright-site-001-stage` |
| site recorder | `node site/tools/recorder.mjs --check` | `robowright-site-001-stage` |

- **Run the recorder bare.** The command above, with nothing before or after it: no `cd … &&`, no
  `>` redirect, no pipe. Anything else stops it matching a machine's sandbox exclusion (→ 12), and
  Chromium dies at launch. Copy its output into `<session_dir>/evidence/recorder-<unit>.log`
  afterwards. The site kit suite has no such limit and is redirected like any other.
- **Verdict lines**:
  - site kit: `# pass N` and `# fail 0`, exit `0`.
  - site recorder: one line per cell, `ok` or `FAIL` and the problems under it; then
    `recorder: ok (<n> shots)` and `EXIT=0`, or `recorder: FAIL <reason>` and `EXIT=1`. `EXIT=2`
    is a refused flag. Read the last two lines.
- **Hang**: the kit suite finishes in seconds. The recorder prints a cell line every few seconds;
  no new line for 180 s is a hang. Kill, re-run once; twice is a gate failure.
- **Infrastructure failure**: not a verdict; stop `verification-failed`. Any of:
  - `node` missing;
  - `recorder: FAIL playwright is not installed`;
  - `recorder: FAIL browserType.launch: …`: the browser is missing or the run was sandboxed.
- **Source-file patterns**: a commit touching `site/**/*.{html,css,js,mjs,svg}` or
  `site/package*.json` owes both site suites, and not `tests/run.sh`. A commit owing neither list
  runs neither.
- **Screenshots** land in `site/tests/out/`, ignored by git and emptied by every run.

## 6 · Kind checks

- **`refactor`** (a move, rename, or delete of installed files, or a file brought in from
  another tree): every row of `git diff -M --name-status <base>..HEAD` is `R100`, `D`, or `A`
  for a file the brief lists as brought in. For a file brought in, the brief names its source
  path and revision; `diff <source> <file>` shows only hunks of the kinds the brief lists (a
  scrub rename, a path retarget). Then the scratch-HOME install, run from the worktree:
  ```sh
  H=$(mktemp -d); HOME="$H" bash install.sh
  readlink "$H/.claude/skills/robowright"               # the worktree's skills/robowright
  find -L "$H/.claude" -type l -print                   # empty: no dangling link
  ls "$H/.claude/skills" | wc -l; ls skills | wc -l     # equal
  ls "$H/.claude/agents" | wc -l; ls agents/*.md | wc -l   # equal
  ```
  A dangling link, or anything linked from `tools/`, `tests/`, `examples/` or `.claude/`, is a
  failure.
- **`docs`**: `doc-gate` through the `reviewer-docs` agent on every prose file the unit added or
  rewrote, ledger under `<session_dir>/reviews/`. A skill or rule file also passes the
  `writing-for-agents` skill's checks.
- **`tests`**: the `load-bearing-tests` skill; one mutation per new test that must redden it.
- **`behavior`**: the `bdd` standard — `worker-spec` writes the behavior table and failing tests
  from the brief before the implementation; red evidence before the first implementing commit.
- **`ui`** (the site, `site/**`): the site recorder suite (→ 5), run bare, every cell `ok`. Copy
  `site/tests/out/*.png` to `<session_dir>/evidence/<unit>/`. The recorder proves the page loads
  clean, tells its captions, holds its themes and respects reduced motion in Chromium. Whether it
  looks right is the Owner's call, made from those screenshots in the owner brief.
- **`security`** (a trigger row: it fires whatever the unit's kind). A diff touching
  `skills/**/scripts/**`, `skills/**/hooks/**`, `tools/**`, `install.sh` or `tests/conventions/`
  → `python3 tests/conventions/test_conventions.py`, verdict `OK`, at every gate.
  - On a failure, `python3 tests/conventions/lint.py` lists the sites.
  - The ledger entry lists every line the diff adds to `tests/conventions/allowlist.txt`.
  - The Worker pastes the rules in `.claude/rules/session-inputs.md`, plus
    `.claude/rules/dashboard.md` when `tools/robowright-dash.py` is in the diff, into the gate
    prompt's contract and the end-of-stack prompt's invariants. The reviewer checks every changed
    line against each rule, and every new allowlist reason against the code it names.

## 7 · Device

None in this repository. No lease, no build lock: `run.json.locks` is `[]`.

## 8 · Regression sweep

None in this repository. The end-of-stack check is `tests/run.sh` plus the scratch-HOME install.

## 9 · Commits and history

Subject `<area>: <what changed>`, lowercase, no period — `gate: refuse a commit whose added
lines match the denylist`, `tests: the runner`. Body says why; the verdict lines live in the
change description and the evidence logs. A commit that fixes a failing verdict quotes the new
one. Trailer: `Co-Authored-By: <model name as launched> <noreply@anthropic.com>`. A session stages
with `rw-git add`, runs `tools/hooks/pre-commit` itself, then commits with
`rw-git commit --message-file <file>`, the message written into its own session folder. No
history rewriting on `main`; fold-and-restack only on the session's own `robowright/` branches,
with `rw-git rebase`, whose printed old tip goes into the ledger. **The pre-commit gate refuses an
added line matching the denylist, and a conventions lint finding in the staged tree. rw-git runs
no hook, so a session runs the gate by hand before every commit; no role uses `--no-verify`.**

## 10 · Publishing

publish_strategy: local-branch

**Published means: a local branch in the Robowright Session's worktree, plus the Explainer's owner
brief in the project folder's owner-brief directory.**

**Nothing is pushed. No pull requests.**

**Accepting.** Finished work is integrated into local `main` only when the Owner accepts it. A branch
behind local `main` is rebased first; the script squashes it onto local `main`, fast-forwards, and prints the
worktree teardown, which is the Owner's too. **The Owner pushes.** No role does.

accept: ~/.claude/skills/lead/scripts/accept.sh --tip <tip> --message <session_dir>/prs/<unit>/commit-message.txt <session_dir> — the Owner runs it, `<tip>` the full id of the branch tip that was reviewed

A direct build has no session directory. Its change description is `<project_dir>/prs/<unit>.md`, its squash message
`<project_dir>/prs/<unit>/commit-message.txt`, and it is accepted with
`~/.claude/skills/lead/scripts/accept.sh --direct -S --base <base> --tip <tip> --message <project_dir>/prs/<unit>/commit-message.txt <project_dir> <unit>`,
`<base>` the full id of the commit it was cut from and `<tip>` the full id of the branch tip that was reviewed. The Lead
composes that line from the launch's `--base`, `git rev-parse` of the reviewed tip and this message path; the change
description names the base and the reviewed tip and carries no accept line. The Owner runs it.

**What a finished change carries.** One change description for the whole change, at
`<session_dir>/prs/<unit>.md`: what changed and why, how it was verified (verdict lines quoted),
and what is still owed. Plain Markdown, no pull-request template. Beside it, the squash
message at `<session_dir>/prs/<unit>/commit-message.txt`: one message for the whole change,
following §9's subject, body and `Co-Authored-By` trailer, the file `accept.sh --message` takes.
**Review-size ceiling:** under 300 lines of core logic per change, a ceiling and not a target.
**Base for the next brief:** local `main`, always; a predecessor branch not yet in `main` is not a
valid base.

Plus, for this repository: **a change that moves, adds, or deletes installed files says so in
the change description under an "after accepting" heading** — the Owner re-runs `install.sh`
after the accept.

## 11 · Toolbelt map

None in this repository. `tools/scrub-gate.sh` is a hook, not a toolbelt entry: it runs from the
Owner's `git commit` and `git push`, and by hand as `tools/hooks/pre-commit` (a session, before
`rw-git commit`) and `tools/scrub-gate.sh --tree`. `tools/robowright-dash.py`,
the dashboard, is a tool run from the clone, not a toolbelt entry: `tools/` is never linked.

## 12 · Traps

- **`install.sh` never links `.claude/`.** This hook lives there, so a builder's install carries
  no hook for this repository unless they copy one to their machine-local hooks.
- **`core.hooksPath` is relative** and resolves per worktree, so every worktree runs its own
  `tools/hooks/` for the Owner's commits. A unit that edits the gate is gated by its own edit from
  that commit on. A session's `rw-git commit` runs no hook at all (`core.hooksPath=/dev/null`): the
  gate runs only when the session runs `tools/hooks/pre-commit` itself.
- **The denylist lives outside the repo** at `~/.config/robowright/denylist`
  (`ROBOWRIGHT_DENYLIST` overrides). It is private: never copy it, quote it, or commit it.
- **Suites sit beside their scripts** under `skills/*/scripts/` and are linked with them; a
  suite is never moved out to `tests/` unless the script moves too.
- **No committed `__pycache__`.** `.gitignore` covers it; a `.pyc` in `git status` is a
  finding.
- **The sandbox kills the site recorder's Chromium** at launch: macOS denies the Mach
  service it registers. An `excludedCommands` entry for `node site/tools/recorder.mjs:*` lets it
  run, and matches only the bare command (→ 5).
- **A machine that runs the recorder needs that exclusion for the bare command, and it runs code
  outside the sandbox.** Treat a diff to the recorder, to what it imports from `site/public/`, to a
  `site/node_modules/` if one exists, or to `site/package*.json` as unsandboxed code, and review it
  that way.
- **Playwright and its browser live outside the worktree.** The package is in a parent folder's
  `node_modules`, e.g. `~/Code/node_modules`, which Node finds from any worktree below it; the
  browser is in Playwright's cache.
  Installing or bumping either is the Owner's. A session never runs `npm install`.
- **Every sandboxed `node` prints about 190 `failed to copy trust settings` lines** to stderr. They
  are harmless; read the verdict lines, never the whole output.

## 13 · Naming

Slugs, not ticket keys.

| What | Form |
|---|---|
| Unit of work | `<project>-<NNN>-<slug>` — e.g. `sample-001-tracer` |
| Base ref | `main` |
| Branch | `robowright/<slug>`; unit N of a stack `robowright/<slug>-u<N>` |
| Planner session | `planner-<slug>` |
| Lead session | `lead-<project>` |
| Worker session | `worker-<model>-<slug>` |
| Explainer session | `explainer-<slug>` |
| Attended task session | `task-<slug>` |

File names inside a session directory are constants: `BRIEF.md`, `run.json`, `LEDGER.md`,
`HANDOFF.md`, `HANDBACK.md`, `INTAKE.md`, `STOP`.

## 14 · Duties

Run after the profile's rows for the same point.

| Role | Extension point | Run |
|---|---|---|
| Planner | `planner.brief` | **The security invariants.** A unit whose scope touches the paths §6 `security` lists gets every rule of `.claude/rules/session-inputs.md`, and of `.claude/rules/dashboard.md` for the dashboard, in BRIEF.md → Invariants and hotspots, one invariant per rule, citing the file |
| Worker | `worker.preflight` | None in this repository. |
| Worker | `worker.unit-gate` | **The scrub sweep.** `tools/scrub-gate.sh --tree` over the worktree; a hit is a HOLD naming the file and line |
| Worker | `worker.publish` | **The "after accepting" check.** A change that moves, adds, or deletes installed files carries the "after accepting" heading §10 requires; add it if it is missing |
| Lead | `lead.tick` | None in this repository. |
| Lead | `lead.intake` | None in this repository. |
| Lead | `lead.post-publish` | None in this repository. |
| Explainer | `explainer.publish` | None in this repository. |
| Reviewer | `reviewer.overlay` | None in this repository. |
