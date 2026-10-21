# Robowright — working in this repository

This repository is the system itself: the skills, agents, launcher, hooks and dashboard that run
Robowright Sessions. A change here changes what runs on the Owner's machine.

## Trust model

- **Everything a session writes is untrusted input.** That covers:
  - `run.json`, `events.jsonl` and `.stop-gate-count` in a session directory;
  - `LEDGER.md`, `HANDOFF.md` and `HANDBACK.md`;
  - the session directory's own name, and any directory created beside it;
  - a `robowright.json` under the sessions root, and a project folder's `robowright.json`: Planners
    write it, and a Worker can too wherever your own settings grant it the projects root.

  A session controls all of these, and a prompt injection can control the session.
- **The Owner-side tools that read them run outside the sandbox.** The launcher, `accept.sh`,
  `role-start.py`, `run-cost.py`, `session-state.py`, the roster, the dashboard and the worker
  hooks all do. A value from a session file reaches a command line, a JSON blob, git or the
  Owner's terminal only after a shape check. `SECURITY.md` → "Values a session can write" lists
  every value and its check.
- **The limits a session runs under are instructions, not enforcement.** Never widen them from a
  value a session wrote.

## Every change

This is the maintainer's workflow for the main clone. A contributor works through pull requests, per
`CONTRIBUTING.md`.

- **The maintainer signs every `main` tip.** Signing is opt-in in `accept.sh`; the maintainer always
  accepts this repository with `accept.sh -S`, never rewrites `main`, and is the only one who pushes it.
  A session never pushes.
- **Tests never carry a working payload.** A security test proves a refusal or a validity
  (`.claude/rules/tests.md`).
- **`bash tests/run.sh` ends `EXIT=0`.** It includes `tests/conventions/`, the lint for the rules
  below.
- **Wire the hooks:** `git config core.hooksPath tools/hooks`. The pre-commit hook runs the scrub
  gate and the conventions lint on the staged tree. Never commit with `--no-verify`.

## Where the standards are

- `.claude/rules/`. Each rule loads when you read or edit a file it covers:
  - `session-inputs.md`: scripts, hooks, `tools/` and `install.sh`;
  - `dashboard.md`: the dashboard and its tests;
  - `public-content.md`: Markdown, tests and examples;
  - `tests.md`: test files.
- `CONTRIBUTING.md`: the bar, commits, and the conventions a change keeps.
- `SECURITY.md`: what a session can do, every session-written value and its check, and what the
  checks do not cover.
- `.claude/robowright/project.md`: this repository's project hook (build, tests, kind checks,
  commits).
