# role-start — test ledger

2026-09-21. 10 tests written from `BEHAVIORS.md` before the script existed; first run 5 failures and
5 errors, all "script missing" rather than an assertion, so every test owed a kill. Green on the
first implementation with no Given, When or Then edited. 14 mutations, each run alone (suite ≈ 2 s),
kill set predicted before the run.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | `--model` takes the role default, ignoring the project | project_settings_pick, unknown_alias | same | KILLED |
| M2 | `--effort` hardcoded `high` | role_without_project, dry_run | same | KILLED |
| M3 | prompt appended unconditionally | role_without_prompt | same | KILLED |
| M4 | session name drops the project | project_settings_pick | same | KILLED |
| M5 | no `chdir` into the project | project_settings_pick | same | KILLED |
| M6 | missing settings file falls back to the default | project_without_settings | same | KILLED |
| M7 | fallback note removed | settings_without_the_role | same | KILLED |
| M8 | alias → id map bypassed | effort_rides | same | KILLED |
| M9 | unknown alias forced to the Opus id | unknown_alias | same | KILLED |
| M10 | unknown role exits 4 | unknown_role | same | KILLED |
| M11 | `--dry-run` falls through to exec | dry_run | same | KILLED |
| M12 | `roles` guard removed | launch_config_without_roles | same | KILLED |
| M13 | bare `effortLevel` hardcoded `high` | effort_rides | same | KILLED |
| M14 | prompt never appended | role_without_project | same | KILLED |

No survivors, no wrong predictions, no tests deleted. Every test has at least one kill of its own
(M4/M5 for project_settings_pick, M9 for unknown_alias, M11 for dry_run, M14 for role_without_project).

Accepted-untested: that `claude` honours `--effort` / `--settings` as documented — observable only in
a live session.

## 2026-10-15 — write scope (R8.1 to R8.3, U38)

Three tests, red first; R4.1 narrowed to the effort keys plus the blob's key set. Mutations shared with
`tests/run-launch/TEST-LEDGER.md` (W rows).

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| W2 | `info` no longer denied | R8.1 | same | KILLED |
| W7 | no at-or-above check | R8.2 | same | KILLED |
| W8 | configured repos not protected | R8.2 | same | KILLED |
| W10 | document roles lose the projects root | R8.1, R8.2 | same | KILLED |
| W11 | `Edit(...)` rules relative | R8.1 | same | KILLED |
| W15 | role-start keeps the caller's cwd | R8.3 | same | KILLED |
| W16 | role-start drops the accounting root | R8.1 | same | KILLED |

Review 1 added R8.4 and a home-cwd subtest in R8.2; their mutations (W19, W23) are in the run-launch ledger.

Review 2 added a project inside the repository to R8.2; W30 (inside a protected path passes) kills it.

Review 3 added a project reached through a link to R8.2; W40 (working directory not link-walked) kills it, and W30
now kills R8.2 alone.

Review 4 added `commondir` to R8.1's denied set; W42 kills it.

Redesign (no links in a grant): W30 and W40 retire with the walker they mutated. In `evidence/redesign/mutations-1.log`,
R8.5 kills M1 (a link at a prefix not refused), M2 (`.`/`..` not refused) and W23 (working directory unchecked);
R8.2 kills M5, M18, W8, W10 and W23; R8.1 kills W2, W10 and W42; R8.4 kills W19. All are as predicted.

Review 5 fixes:
- R8.6 (a project swapped for a link after the check) was red before the fix. F1d (no `getcwd` compare) kills it
  (`kill-F1d.log`).
- R8.1's expected set gained `config.worktree` (F2) and the project-config denies (F3). Red before each change; F3a,
  F3b and F3c kill it.

U46: R8.1's expected set gained the leaf `<root>/**/.git` deny on each granted root, and now denies the git
directory whole rather than its `config`, `hooks`, `info` and `config.worktree` files. Red on the U45 base. L03r, no leaf on a granted root,
kills R8.1. KILLED, as predicted.
