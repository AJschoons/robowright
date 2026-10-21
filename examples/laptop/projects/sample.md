# Project hook — sample (example)

An example machine-local hook, for a repository that cannot carry its own. Copy it to
`~/.claude/robowright/projects/sample.md` beside the laptop profile. The repository, commands
and paths are invented: `example-org/sample` is a small Python notes library with a command-line
front end, tested with the standard library's `unittest`. Fourteen sections, fixed order, per
`skills/worker/PROJECT-HOOK.md`; a section that does not apply says `None in this repository.`

## 1 · Identity

| | |
|---|---|
| Origin | `git@github.com:example-org/sample.git` — match on `example-org/sample` |
| Main clone | `~/Code/sample`; every path below is relative to `git rev-parse --show-toplevel` |
| Base ref | `main` |
| Artifact ids | None. The library is used from the checkout; nothing is built or installed |

**Clients**

None in this repository.

## 2 · Preflight extras

- `git status --short` on the main clone is empty, or every line is explained in the ledger. A
  dirty main clone is not this session's to touch; note it and continue.
- `python3 --version` prints 3.9 or later. Older → stop, `verification-failed`.

## 3 · Worktree

Worktrees live inside the repo at `.worktrees/<slug>`, excluded by `.git/info/exclude`.

```sh
git worktree add -b robowright/<slug> "$(git rev-parse --show-toplevel)/.worktrees/<slug>" main
```

- Branch `robowright/<slug>`, `<slug>` matching the session directory's; unit N of a stack is
  `robowright/<slug>-u<N>`.
- Teardown: removing the worktree and deleting the branch are Owner-only; hand the Owner the
  commands.

## 4 · Build

No compiled product. The build step is a syntax pass over every changed Python file, redirected
to `<session_dir>/evidence/build-<unit>.log`:

```sh
git diff --name-only --diff-filter=d <base>..HEAD -- '*.py' | xargs -r python3 -m py_compile; echo "EXIT=$?"
```

- **Verdict**: the `EXIT=` line, `0`. Read by the `log-reader` agent or by `grep '^EXIT='`.
- **Build output directory**: none; `run.json.build_output` stays `""`.
- **Hang**: none possible; the pass finishes in seconds. No output after 60 s is a machine problem.
- **Infrastructure failure**: `python3` missing from `PATH`. Not a verdict; stop `verification-failed`.
- **Gate command**: None in this repository.

## 5 · Tests

One suite, run from the repo root and redirected to a log:

```sh
python3 -m unittest discover -s tests -t . ; echo "EXIT=$?"
```

- **Verdict lines**: `Ran N tests in …` then `OK` or `FAILED (failures=F, errors=E)`, and the
  `EXIT=` line. Read by `log-reader` or `tail -3`; never a grep for a test name.
- **Scoping**: `python3 -m unittest tests.<module>.<Class>` from the repo root.
- **Hang**: the suite finishes in under a minute. No line for 120 s is a hang. Kill, re-run
  once; twice is a gate failure.
- **Infrastructure failure**: `python3` missing. Not a verdict.
- **Whole suite** = the command above.
- **Source-file patterns** (a commit touching any owes the whole suite): `*.py`. Markdown and
  evidence owe nothing.

## 6 · Kind checks

- **`refactor`**: every row of `git diff -M --name-status <base>..HEAD` for a moved file is
  `R100`; a moved function's body is unchanged in `git diff -M --color-moved`.
- **`docs`**: `doc-gate` through the `reviewer-docs` agent on every prose file the unit added or
  rewrote, ledger under `<session_dir>/reviews/`.
- **`tests`**: the `load-bearing-tests` skill; one mutation per new test that must redden it.
- **`behavior`**: the `bdd` standard — `worker-spec` writes the behavior table and failing tests
  from the brief before the implementation; red evidence before the first implementing commit.
- **`ui`**: None in this repository.

## 7 · Device

None in this repository. No lease, no build lock: `run.json.locks` is `[]`.

## 8 · Regression sweep

None in this repository. The end-of-stack check is the whole suite.

## 9 · Commits and history

Subject `<area>: <what changed>`, lowercase, no period — `notes: save a draft every 30 seconds`.
Body says why; the verdict lines live in the change description and the evidence logs. A commit
that fixes a failing verdict quotes the new one. Trailer:
`Co-Authored-By: <model name as launched> <noreply@anthropic.com>`. No history rewriting on
`main`; fold-and-restack only on the session's own `robowright/` branches, with `rw-git rebase`,
its printed old tip in the ledger and `git diff <old tip> <rewritten>` empty for the tip after.
Every write to the git directory goes through `rw-git`; reads stay plain `git`.

## 10 · Publishing

publish_strategy: local-branch

**Published means: a local branch in the Robowright Session's worktree, plus the Explainer's
owner brief in the project folder's owner-brief directory.** Nothing is pushed; no pull requests.

**Accepting.** Finished work is integrated into local `main` only when the Owner accepts it. A
branch behind local `main` is rebased first; the script squashes it onto local `main`, fast-forwards, and prints the
worktree teardown, which is the Owner's too. The Owner pushes.

accept: ~/.claude/skills/lead/scripts/accept.sh --tip <tip> --message <session_dir>/prs/<unit>/commit-message.txt <session_dir> — the Owner runs it, `<tip>` the full id of the branch tip that was reviewed

A direct build has no session directory. Its change description is `<project_dir>/prs/<unit>.md`, its squash message
`<project_dir>/prs/<unit>/commit-message.txt`, and it is accepted with
`~/.claude/skills/lead/scripts/accept.sh --direct --base <base> --tip <tip> --message <project_dir>/prs/<unit>/commit-message.txt <project_dir> <unit>`,
`<base>` the full id of the commit it was cut from and `<tip>` the full id of the branch tip that was reviewed. The Lead
composes that line from the launch's `--base`, `git rev-parse` of the reviewed tip and this message path; the change
description names the base and the reviewed tip and carries no accept line. The Owner runs it.

**What a finished change carries.** One change description for the whole change, at
`<session_dir>/prs/<unit>.md`: what changed and why, how it was verified (verdict lines quoted),
and what is still owed. Beside it, the squash message at
`<session_dir>/prs/<unit>/commit-message.txt`, in this hook's commit form with its trailer: the file
`accept.sh --message` takes. **Review-size ceiling:** under 300 lines of core logic per change.
**Base for the next brief:** local `main`; a predecessor branch not yet in `main` is not a valid base.

## 11 · Toolbelt map

None in this repository.

## 12 · Traps

- **`tests/fixtures/` holds note files the suite reads byte for byte.** An editor that strips
  trailing whitespace on save breaks three tests; write fixtures with the Write tool only.

## 13 · Naming

Slugs, not ticket keys.

| What | Form |
|---|---|
| Unit of work | `sample-<NNN>-<slug>` — e.g. `sample-012-note-autosave` |
| Base ref | `main` |
| Branch | `robowright/<slug>`; unit N of a stack `robowright/<slug>-u<N>` |
| Planner session | `planner-<slug>` |
| Lead session | `lead-sample` |
| Worker session | `worker-<model>-<slug>` |
| Explainer session | `explainer-<slug>` |
| Attended task session | `task-<slug>` |

## 14 · Duties

Run after the profile's rows for the same point.

| Role | Extension point | Run |
|---|---|---|
| Planner | `planner.brief` | None in this repository. |
| Worker | `worker.preflight` | None in this repository. |
| Worker | `worker.unit-gate` | None in this repository. |
| Worker | `worker.publish` | None in this repository. |
| Lead | `lead.tick` | None in this repository. |
| Lead | `lead.intake` | None in this repository. |
| Lead | `lead.post-publish` | None in this repository. |
| Explainer | `explainer.publish` | None in this repository. |
| Reviewer | `reviewer.overlay` | None in this repository. |
