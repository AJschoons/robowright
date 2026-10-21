# run-launch — test ledger

Commit ids in this record refer to the project's history before it was published; they are not in this repository.

2026-09-25. 12 tests carried over from an earlier launcher suite, green on the first run against
the unchanged launcher (`Ran 12 tests … OK`). Four rounds, fourteen mutations to `run-launch.sh`,
the kill set predicted in writing before each round, the launcher restored after each
(`git status --short` showed only `tests/run-launch/`).

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | resume command drops the `/worker <session dir>` prefix | resume_prompt_re_invokes_the_worker_skill | same | KILLED |
| M2 | the `robowright.json` model branch never taken | robowright_json_outranks_the_profile… | same | KILLED |
| M3 | report prompt drops `smoke/MANUAL-PASS.md` | report_prompt_sends_the_explainer_to_the_manual_smoke_pass | same | KILLED |
| M4 | Worker-site STOP refusal removed | a_stop_file_refuses_the_launch | same | KILLED |
| M5 | live-session refusal removed | a_live_session_in_the_worktree_refuses_the_launch | same | KILLED |
| M6 | `*/worktrees/*` path check removed | the_worktree_must_be_a_linked_worktree_not_the_main_clone | same | KILLED |
| M7 | `--compact-pct` whole-number check removed | compact_pct_must_be_a_percentage | same | KILLED |
| M8 | `--stop-cap` whole-number check removed | stop_cap_must_be_a_whole_number | same | KILLED |
| M9 | marker write removed | the_launch_writes_the_session_marker_into_the_worktree | same (error reading the absent marker, at the Then) | KILLED |
| M10 | report ledger target → `<project>/LEDGER.md` | the_plan_names_the_file_the_entry_is_actually_appended_to | same | KILLED |
| M11 | Worker-site dry-run verb removed | a_dry_run_does_not_claim_an_entry_was_appended | same | KILLED |
| M12 | `worker_entry` never records the resumed id | a_resume_records_the_id_it_resumed_not_a_name_it_invented | same | KILLED |

| M13 | both resume prompts open `Resume this session:` | resume_prompt_re_invokes_the_worker_skill | same | KILLED |
| M14 | the marker also written before the dry-run exit | the_launch_writes_the_session_marker_into_the_worktree | same | KILLED |

M1 and M9 are killed by the session-state suite too (its `--resume … /worker` and hand-off
marker assertions), so a fourth round mutated what only this suite asserts: the resume opener
(M13) and no marker on a dry run (M14). No survivors, no wrong predictions, no tests deleted.
Every test has a kill the session-state suite does not also make.

## The launch mode (U2)

Four tests in `LaunchModeTests`, rows R5.1–R5.4 of `BEHAVIORS.md`, written before the launcher
read the `launch` key. Round logs are the session's; each round's kill set was predicted in
writing first, and the launcher was restored after each.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M3 | the EPERM hint restored to the sandbox settings-key words | eperm_under_auto_at_the_worker_site…, eperm_under_auto_at_the_document_only_site… | same | KILLED |
| M5 | `claude` still called under `paste` | paste_hands_off_the_command_the_plan_printed_without_running_it | same (with the shared suite's paste cases) | KILLED |
| M9 | under `paste`, the handed-off command drops its last word | paste_hands_off_the_command_the_plan_printed_without_running_it | same; shared suite green | KILLED |
| M10 | the started command gains `--verbose` | auto_starts_the_session_with_the_command_the_plan_printed | same, **and** the shared suite's worker hand-off paste-line test — a wrong prediction | KILLED |
| M11 | the plan's `command:` line gains `--verbose`, runtime unchanged | auto_starts…, paste_hands_off… | same; shared suite green | KILLED |

`auto_starts…` passed before the change (today's behaviour); M11 is its kill. No survivors, no
tests deleted. Every test has a kill the session-state suite does not also make.

## `project` on `--pin`, the soft `match_group`, the desktop regex (polish P2)

Ten tests in `PinProjectTests`, `CapturelessGroupRegexTests` and `DesktopExampleRegexTests`, rows
P2.1–P2.10 of `BEHAVIORS.md`, written before the change. P2.2–P2.5 and P2.10 passed before it and
owe the kills below. Rounds 1–2 mutate the launcher, round 3 the desktop example, round 4 the
launcher against the session-state suite's pre-launch refusal test (P2.11), run scoped; each
round's kill set was predicted in writing first, and the file restored after each.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | the pin writes no project | a_pin_writes_the_group_regex_capture_of_the_ticket_as_project__when_run_json_has_none | same | KILLED |
| M2 | write_project's null guard dropped | a_pin_leaves_a_project_already_set_alone, a_project_already_set_is_left_alone | same | KILLED |
| M3 | a pin whose ticket matches no group writes the session dir's name | a_pin_whose_ticket_is_outside_group_regex_still_pins_and_leaves_project_null | same | KILLED |
| M4 | the pin's match_group without --soft | a_pin_under_a_group_regex_that_captures_nothing_still_pins_and_leaves_project_null | same | KILLED |
| M5 | the pin's project write moved above the dry-run exit | a_pin_dry_run_writes_no_project | same | KILLED |
| M6 | the Worker's post-launch match_group without --soft (the base's hard fail) | an_auto_launch_under_a_group_regex_that_captures_nothing_finishes_with_project_null, an_auto_launch_under_a_group_regex_that_captures_nothing_still_indexes_the_session_with_no… | same | KILLED |
| M7 | no launch index line when the Worker's unit id captured nothing | an_auto_launch_under_a_group_regex_that_captures_nothing_still_indexes_the_session_with_no… | same | KILLED |
| M8 | the doc role's post-launch match_group without --soft | a_planner_launch_under_a_group_regex_that_captures_nothing_finishes_and_indexes_the_folder… | same | KILLED |
| M9 | desktop group_regex tail back to (-[a-z0-9]+)+$ | the_desktop_group_regex_captures_the_tracker_prefix_from_a_bare_key_and_a_keyed_dir_name | same | KILLED |
| M10 | desktop group_regex stops at the key (+ → $) | the_desktop_group_regex_captures_the_tracker_prefix_from_a_bare_key_and_a_keyed_dir_name, under_the_desktop_unit_block_a_brief_still_inherits_its_tracker_prefix_s_keyed_intake | same | KILLED |
| M11 | the pre-launch brief caller (:722) takes --soft | a_group_regex_that_matches_but_captures_nothing_is_refused_by_name | same | KILLED |

No survivors, no wrong predictions, no tests deleted.

## Values a session can write (SI rows)

2026-10-13. Each refusal row was red on `9a127e5` before the code that satisfies it. SI-2 and SI-6 are
guards, green on base by design. SI-2's docstring declares that a `printf` builder with the right
format would also pass it, because every value reaching the blob is shape-checked first. Mutations
ran in scratch clones, one at a time. The kill set was written before each run, and every touched
suite was run. `git status` was clean after each mutation.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | `check_model` matches `.*` | SI-1 model shape | SI-1, plus session-state `the_model_is_the_next_unit_s_own…`, which asserts that `gpt-5` is refused through the same check | KILLED (overlap) |
| M2 | the settings blob gains a `hooks` key | SI-2 | same | KILLED |
| M3 | role-start's model check off | SI-3 | same | KILLED |
| M4 | `models.json` gains a key | SI-4 | same | KILLED |
| M5 | run.json `session_id` UUID check off | SI-8 | same | KILLED |
| M6 | the known-tool-name check off | SI-10 | same | KILLED |
| M7 | the unit-form check on the directory fallback off | SI-11 | same | KILLED |
| M8 | the hint's branch is not quoted | SI-12 | same | KILLED |
| M9 | `.gitignore` loses the marker | SI-16 | same | KILLED |
| M10 | the top-level `model` digest check off | SI-5 `[model]` | same | KILLED |
| M11 | the `unit_models` digest check off | SI-5 `[units[].model]` | same | KILLED |
| M12 | the model digest compared when the event lacks it | SI-6 | same | KILLED |
| M13 | the lock-name pattern is `.+` | SI-13 | same (also re-run on the `x.y` form) | KILLED |
| M14 | the counter's digits check off | SI-7 | same | KILLED |
| M15 | the marker's under-root check off | SI-14 outside-root | same | KILLED |
| M16 | `base_sha` check off | SI-9 `base_sha` | same | KILLED |
| M17 | the roster's fence prefix dropped | SI-15 fence | same | KILLED |
| M18 | `10#` dropped from the counter | SI-7 (`08`) | same | KILLED |
| M19 | the launch.json `sessions_root` lookup removed | SI-14 launch.json | same | KILLED |
| M20 | the parked reason is not folded | SI-15 parked | same | KILLED |
| M21 | the parked reason is folded on `\n` only | SI-15 parked (U+2028) | same | KILLED |

No survivors. One test was replaced. The first SI-13 test reached a lock outside the sessions root
through `x/../../outside`, which is a working traversal on base. It now uses `x.y`, an off-shape
name for a lock this session owns inside the root, and is still red on base.

## Session writes (SW rows)

2026-10-15. Every SW row was red on `ece9986` (the tests, with `session_write.py` a stub that wrote the way
every site did) before the code that satisfies it, except SW-15, a guard that the writes still happen,
green on the stub by design; SW-17 was red on the launcher before its hold. The FIFO subtests of SW-14 were
red as a timeout: the stub blocked on the FIFO. Mutations ran on the committed tree one at a time, the
kill set written before each run, then `git checkout --` of that file; `git status` was clean after the
pass. Tests: S = `test_session_state.SessionWriteTests`, L = `test_run_launch.SessionWriteTests`,
C = `test_run_cost.SessionWriteTests`, Q = `test_run_roster.SpendGuardWriteTests`.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| W1 | the Stop hook's counter back to `>` | SW-1 (S) | same | KILLED |
| W2 | the Stop hook's rotation line back to `>>` | SW-2, SW-3 (S) | same | KILLED |
| W3 | the PreCompact line back to `>>` | SW-3, SW-4 (S) | same | KILLED |
| W4 | the Stop hook's ISO hold removed | SW-5 (S) | same | KILLED |
| W5 | the Stop hook's phase hold removed | SW-6 (S) | same | KILLED |
| W6 | the state tool's lock opened `"w"` | SW-7 (S) | same | KILLED |
| W7 | the state tool's early `events.jsonl` check removed | SW-8 (S): run.json is written before the append refuses | same | KILLED |
| W8 | the helper's one-link check removed | SW-14 (S), the hard-link subtests | same | KILLED |
| W9 | the helper's `replace` without the truncate | SW-15 (S) | same | KILLED |
| W10 | the helper opens the name without `O_NOFOLLOW` | every symlink row: SW-1 to SW-4, SW-7, SW-8, SW-10, SW-11 lock and ledger, SW-12 hook, SW-13, SW-14 | same | KILLED |
| W11 | the launcher's `.claude` link check removed | SW-9 (L): the marker write still refuses, by another message | same | KILLED |
| W12 | `LEDGER.md` left out of the launcher's pre-start check | SW-10 ledger (L): the stub runs before the append refuses | same | KILLED |
| W13 | `pin_session` writes `run.json.tmp` and replaces | SW-11 tmp (L) | same | KILLED |
| W14 | the launcher's ISO hold removed | SW-17 (L) | same | KILLED |
| W15 | `store_cost`'s lock opened `"w"` | SW-12 lock (C) | same | KILLED |
| W16 | the SessionEnd hook's line back to `>>` | SW-12 hook (C) | same | KILLED |
| W17 | the spend guard's STOP opened `"w"` | SW-13 STOP (Q) | same | KILLED |
| W18 | the spend guard's threshold line opened `"a"` | SW-13 threshold (Q) | same | KILLED |
| W19 | `store_cost` writes `run.json.tmp` and replaces | SW-12 tmp (C) | same | KILLED |
| W20 | the helper's `check` creates the file | SW-15 (S) | same | KILLED |
| W21 | the launcher's worktree control-character hold removed (the launch path) | SW-18 (L) | same | KILLED |
| W22 | `append_records`' ledger lock opened `"w"` | SW-19 lock (C) | same | KILLED |
| W23 | `records.jsonl` appended with `open(path, "a")` | SW-19 records and dangling (C) | same | KILLED |
| W24 | `--ledger`'s refusal not caught (a traceback, exit 1) | SW-19, all three (C) | same | KILLED |
| W25 | the launch index line back to `>>` | SW-20 (L), and conventions T1 (the allowlist line is gone) | same | KILLED |
| W26 | `--migrate`'s refusal arm removed (the tree before review 3) | SW-21 (R), red in `evidence/red-3.log` | same | KILLED |

No survivors. SW-10's marker case and SW-11's lock and ledger cases are each guarded twice, by the
launcher's pre-start check and by the write itself, so only W10 reaches them.

Review 1 added SW-18, red on `d80e792`, and two changes with no row. `spend-guard.py` no longer marks a
session stopped when its STOP write is refused, so the next `--watch` pass tries again: reaching it needs
a second poll, and no test drives the loop, so it is accepted untested. The Stop hook's quiet return when
`python3` is missing is a header note, not a row: the suites need python3 to run at all.

After review 2, the Lead extended the rule to the accounting root: SW-19 and SW-20, red on `fa0a5ab`, and
W22 to W25, each killing the tests predicted.
Review 3 added SW-21: `--migrate` shares `append_records`, and a refusal there is not an `OSError`.

## 2026-10-15 — write scope (WS-1 to WS-9, U38)

Nine tests plus SI-2's widened key set, red first on the missing behaviour. Seventeen mutations across
`role_grants.py`, `run-launch.sh` and `role-start.py` (shared with the role-start suite), the kill set predicted
before the run.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| W1 | worker drops the accounting root | WS-1, WS-6 | those and WS-5, whose scenario is set through `accounting_root` | KILLED |
| W2 | `info` no longer denied | WS-2, WS-4, WS-7, R8.1 | same | KILLED |
| W3 | locks not granted | WS-3 | same | KILLED |
| W4 | `depends_on` path not held to `repos` | WS-4 | same | KILLED |
| W5 | `depends_on` session not one segment | WS-4 | same | KILLED |
| W6 | dep grant is all of `worktrees/` | WS-4 | same | KILLED |
| W7 | no at-or-above check | WS-5, WS-8, R8.2 | same | KILLED |
| W8 | configured repos not protected | WS-8, R8.2 | R8.2 only: WS-8's root also held `$HOME`; WS-8 now uses the repo as the root, then both | KILLED |
| W9 | the environment moves the accounting grant | WS-6 | same | KILLED |
| W10 | document roles lose the projects root | WS-7, WS-8, R8.1, R8.2 | same | KILLED |
| W11 | `Edit(...)` rules relative | WS-2, WS-7, R8.1 | same | KILLED |
| W12 | launcher drops the grants from `--settings` | WS-1–4, WS-6, WS-7, SI-2 | same | KILLED |
| W13 | launcher never writes `info/exclude` | WS-9 | same | KILLED |
| W14 | document launch passes no grants | WS-7, WS-8 | same | KILLED |
| W17 | the plan prints the grants in another order | WS-1 | same | KILLED |

Review 1 added WS-10 to WS-14 and reshaped WS-4 (the launcher makes the dependency checkout; W6 retired with
the dependency grant). Ten more mutations, predicted before the run:

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| W18 | links below a root not refused | WS-10 | same | KILLED |
| W19 | no `repos` grants anyway | WS-11, R8.4 | same | KILLED |
| W20 | `launch.json`'s real directory not protected | WS-12 | same | KILLED |
| W21 | launcher clone not protected | WS-12 | same | KILLED |
| W22 | `GIT_*` not removed | WS-13 | same | KILLED |
| W23 | working directory not checked | WS-14, R8.2 | same | KILLED |
| W24 | checkouts never made | WS-4 | same | KILLED |
| W25 | ref not held to a commit id | WS-4 | same | KILLED |
| W26 | `deps` link not refused | WS-4 | SURVIVED: git refused the step on a stale admin entry whose message also said "deps"; WS-4 now prunes it and asserts "deps is a link", then KILLED | KILLED |
| W27 | launcher never makes checkouts | WS-4 | same | KILLED |

Review 2 added WS-15 and WS-16, a target link in WS-4, three layouts in WS-10, and reshaped WS-12 and WS-14 so each
fails on its own check. Seven more mutations:

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| W28 | a root that is itself a link passes | WS-10 | same | KILLED |
| W29 | roots compared by spelling | WS-10 | SURVIVED: the spelling layouts linked the accounting root itself, refused by W28's check; the link moved between two roots, then KILLED | KILLED |
| W30 | inside a protected path passes | WS-15, R8.2 | same | KILLED |
| W31 | worktrees not protected | WS-15 | same | KILLED |
| W32 | checkout target link not refused | WS-4 | same | KILLED |
| W33 | `info` link not refused | WS-16 | same | KILLED |
| W34 | a grant inside the home directory refused too | every test that expects a grant | same, plus the role-start R1 rows | KILLED |

Review 3 replaced the worktree listing with the git-checkout rule and made the link walk follow every link. WS-4
relaunches after its checkout; WS-10 adds an Owner's link into the projects root and another Unicode form; WS-15 adds
a clone `repos` does not list, a link in the projects root, and two layouts that must still plan (a projects root, and
a home directory, versioned with git). W31 (worktrees not protected) retired with the listing. Then every mutation
re-ran at the tip (`mutations-all.log`): all killed.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| W29 | roots compared by spelling (re-anchored) | WS-10 | WS-10, and R8.2, whose link subtest names the projects root as spelled | KILLED |
| W35 | links behind a link not walked | WS-10 | same | KILLED |
| W36 | no Unicode folding | WS-10 | same | KILLED |
| W37 | git checkouts not refused | WS-15 | same | KILLED |
| W38 | a checkout a root holds refused too | WS-15 | same | KILLED |
| W39 | launcher passes the canonical project | WS-15 | same | KILLED |
| W40 | working directory not link-walked | WS-15, R8.2 | same | KILLED |
| W41 | checkouts at or above home refused | WS-15 | same | KILLED |

W30 (inside a protected path passes) now kills R8.2 only: WS-15's repository case is refused by the checkout rule too.

Review 4 added WS-17 (a planted `commondir`), a `..` after a link and a `..` after an Owner's link to WS-15, and
`commondir` to every denied set. Five more mutations (`mutations-5.log`):

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| W42 | `commondir` not denied | WS-2, WS-4, WS-7, WS-13, WS-17, R8.1 | same | KILLED |
| W43 | a planted `commondir` not refused | WS-17 | same | KILLED |
| W44 | `..` collapsed by spelling | WS-15 | same | KILLED |
| W45 | the launcher starts in the logical folder | WS-15 | same | KILLED |
| W46 | a main clone's denies read back from git | WS-17 | same | KILLED |

## Redesign (no links in a grant; the launcher makes a Worker's worktree)

The walker mutations (W30-W41, W44-W46) target code that is deleted; they are retired with it. Runner
`evidence/redesign/mutate2.py`, results `mutations-1.log`, every mutation reverted by `git checkout` (status clean
after).

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | a link at a prefix not refused | WS-10, WT-4, R8.5 | same | KILLED |
| M2 | `.`/`..` not refused | WS-18, R8.5 | same | KILLED |
| M3 | identity by spelling | WS-19 | same | KILLED (case-insensitive volume only) |
| M4 | git checkouts not refused | WS-15 | same | KILLED |
| M5 | "inside a protected path" dropped | WS-19, R8.2 | same | KILLED |
| M6 | preflight attaches instead of `-b` | WT-1 | same | KILLED |
| M7 | the dry run makes the worktree | WT-1 | same | KILLED |
| M8 | no `--end-of-options` at preflight | WT-1 | same | KILLED |
| M9 | later phases take `-b` from the base | WT-2 | same | KILLED |
| M10b | `role_grants.py` drops the finished-phase refusal | WT-3 | SURVIVED, then WT-3 | KILLED after the fix below |
| M11 | worktree path not link-checked | WT-4 | same | KILLED |
| M12 | a relative worktree taken from the cwd | WT-4 | same | KILLED |
| M13 | branch not held to `robowright/<slug>` | WT-5 | same | KILLED |
| M14 | a 7-hex base accepted | WT-6 | same | KILLED |
| M15 | base not peeled to a commit | WT-6 | same | KILLED |
| M16 | any repository on the convention trusted | WT-7 | WT-7, WT-4 | KILLED |
| M17 | worktree made before the state machine is asked | WT-2 | same | KILLED |
| M18 | no at-or-above check | WS-5, WS-8, WS-12, WS-14, WS-19, R8.2 | WS-5, WS-12, WS-14, R8.2 | KILLED |
| W1 | worker drops the accounting root | WS-1, WS-4, WS-6 | those, WS-5, WS-10, WS-18 | KILLED |
| W2 | `info` not denied | WS-2, WS-4, WS-7, WS-13, R8.1 | same | KILLED |
| W3 | locks not granted | WS-3 | WS-3, WS-10 | KILLED |
| W8 | configured repos not protected | WS-8, WS-14, WS-19, R8.2 | same | KILLED |
| W10 | document roles lose the projects root | WS-7, WS-8, WS-10, WS-18, WS-19, R8.1, R8.2 | those, WS-12 | KILLED |
| W19 | no `repos` grants anyway | WS-11, R8.4 | same | KILLED |
| W20 | launch.json's real directory unprotected | WS-12 | same | KILLED |
| W21 | launcher clone unprotected | WS-12, WS-19 | same | KILLED |
| W22 | `GIT_*` kept | WS-13 | SURVIVED, then WT-8 | KILLED after the fix below |
| W23 | working directory unchecked | WS-10, WS-14, WS-15, WS-18, WS-19, R8.2, R8.5 | same | KILLED |
| W38 | a checkout a root holds refused too | WS-15 | same | KILLED |
| W41 | checkouts at or above home refused | WS-15 | same | KILLED |
| W42 | `commondir` not denied | WS-2, WS-4, WS-7, WS-13, WS-17, R8.1 | same | KILLED |
| W43 | a planted `commondir` not refused | WS-17 | same | KILLED |

Mismatches. M18: WS-8's root is the repository itself and WS-19's aliases name the clone itself, so the "inside"
half of the rule refuses both with "at" dropped. M16's extra WT-4 kill is the relative path, which ends in the
convention and is then refused by `unlinked()` without naming it. W1, W3, W10's extras assert a role's whole grant
list.

Survivors, fixed in the tests:
- M10b: the launcher refuses `done` before the worktree step, and with no `parked` branch the attach step refused
  for a missing branch instead, so `fail_worktree_missing` printed the finished refusal either way. WT-3 now keeps the
  branch, as a torn-down session does, and calls `role_grants.py worktree <dir> plan|make` directly
  (`kill-M10b.log`: both subtests red).
- W22: a main clone's denies are now read from its `.git` on disk, so WS-13 runs no git and no longer guards the
  stripping. The stripping matters where git runs: the worktree the launcher makes. New WT-8 (`kill-W22.log`: red).

## Review 5 fixes

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M3 | identity by spelling | WS-19 (`$HOME` in another case) | same | KILLED |
| F4r | `repos()` not held to the disk's spelling | WS-20 repository subtest | same | KILLED |
| F1a | `--project` resolved with `cd -P` before the check | WS-21 before-the-check | that, and WS-10, WS-18 working-directory subtests | KILLED |
| F1b | no `pwd -P` compare at the start | WS-21 after-the-check | same | KILLED |
| F1c | ledger line through the absolute path | WS-21 after-the-start | same | KILLED |
| F3a | no named project-config denies | WS-22 named, WS-7, R8.1 | same | KILLED |
| F3b | no wildcard project-config denies | WS-22 wildcard, WS-7, R8.1 | same | KILLED |
| F3c | `.claude` Edit rule without `/**` | WS-22 `.claude`, WS-7, R8.1 | same | KILLED |
| MA | `above()` ignores links in a protected spelling | WS-23 | same | KILLED |
| ML | `repos` protected only by real path | WS-23 | same | KILLED |
| MC | session folder not link-checked | WS-24 link | same | KILLED |
| MD | session folder identity not compared | WS-24 namesake | same | KILLED |
| MF | a non-string phase accepted | WT-3 phase `7` | same | KILLED |
| MI | `base_sha` not compared with the peeled commit | WT-6 tag | same | KILLED |

F2's new deny entries reddened WS-2, WS-4, WS-7 and WS-13 before the change (`red-F2.log`). Dropping them again is
that baseline.

## Reviews 6 and 7, and the shared `.git` reflog

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| R6F1 | no compare in the paste line | WS-25 after a swap, R5.2 | same | KILLED |
| R7a | `%s` for the compare's path | WS-25 as checked (a space in the path) | same | KILLED |
| R7b | hand-off before the `cd` | WS-25 ledger subtest | same (it errors: the line landed beside the test) | KILLED |
| R8a | no link check on the new branch's ref and reflog | WT-9, the three plant subtests | same, after the test's isolation fix | KILLED |
| R8b | `worktree add` without `core.logAllRefUpdates=false` | WT-9, the race subtest | same | KILLED |

## Attributes off (AS rows, the Owner's 2026-10-15 "option 1, switch to attr-source")

Red before the change: `red-AS.log`, every AS test failing on its assertion (9 subtests). Each mutation below was
applied to 7e20862, run against `AttrSourceTests` plus WT-1 and WT-2, and reverted; logs `kill-AS*.log`.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| ASa | the new-branch `worktree add` without the attribute options | AS-1 new branch | that, and AS-2 | KILLED; AS-2's launch also makes the main worktree, and its "no marker" covers both |
| ASb | the existing-branch `worktree add` without them | AS-1 existing branch | same | KILLED |
| ASc | `--attr-source` without `-c core.attributesFile=/dev/null` | AS-1 both, AS-2, AS-5 | same | KILLED |
| ASd | the `deps/` `worktree add` without them | AS-2 | same | KILLED |
| ASe | `no_attributes` without its `check-attr` probe | AS-3 | same, all four subtests | KILLED |
| ASf | the launcher's git array without them | AS-1 both, AS-5 | that, and AS-2 | KILLED; the same reason as ASa: the launcher's `status` runs `clean` on the main worktree |
| ASg | the launcher's `status` without `--no-optional-locks` | AS-4 | same | KILLED |

Review 11 F1: on an old git with the worktree missing, the refusal handed the Owner the plain `worktree add` line.
AS-3's missing-worktree subtests now also assert no `worktree add` line, seen red first (`red-R11F1.log`, 2 subtests).

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| ASh | `worktree_refused` without its exit-3 branch | AS-3 missing, both flags | same | KILLED; code removed by the review 12 fix |
| ASi | `role_grants.py` exits 2 for `AttributesUnsupported` | AS-3 missing, both flags | same | KILLED; code removed by the review 12 fix |

Review 12 F1: that fix held only when the attributes probe was the refusal. A run.json refusal before it, and `--pin`,
still handed over the line. The gate moved into `fail_worktree_missing`, ahead of the line, on
`owner_git.py attr-source` (`--attr-source` asked at `-C /`, no repository); the exit 3 path is gone. AS-3 gained
five subtests (a base not a commit, past preflight with no branch, both flags; `--pin`), seen red first
(`red-R12F1.log`). `repository_calls` now also skips the `-C /` probe, as it skips `check-ref-format`.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| ASj | `fail_worktree_missing` without its `attr-source` gate | AS-3's seven missing-worktree subtests | same | KILLED |
| ASk | `has_attr_source` without the `--attr-source … version` call | same | same | KILLED |

## Direct launch (DL rows, U42)

Red before the change: 37 failures over 13 tests, each on `--direct` being unknown or `role_grants.py direct` printing
its usage (`evidence/red-1.log`). Every mutation below was predicted in writing, applied to the implementing commit, run
against `DirectLaunchTests`, `WorktreeCreationTests` and `AttrSourceTests`, and reverted (`evidence/mutate.py`,
`evidence/mutations-1.log`).

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| DL1 | the new-branch `worktree add` from `HEAD`, not the base | DL-1, WT-1 | that, and WT-8 | KILLED; WT-8 also asserts the base |
| DL2 | `direct_worktree` without `convention_repo` | DL-2 | same | KILLED |
| DL3a | `base_commit` takes any id that peels to a commit | DL-3, WT-6 | same | KILLED |
| DL3b | `FULL_COMMIT` takes 7–40 hex | DL-3, WT-6 | same | KILLED |
| DL4a | the launcher's `in_unit_form` check on `--slug` off | DL-4 | same | KILLED |
| DL4b | `role_grants.py`'s slug segment check off | DL-4 | same | KILLED |
| DL4c | `direct_worktree` without `branch_name` | DL-4 | same | KILLED |
| DL5 | `direct_briefing` without `unlinked` on the briefing | DL-5 | same | KILLED |
| DL6 | the new-branch `worktree add` without the attribute options | DL-6, AS-1 | that, and AS-2 | KILLED; AS-2's launch makes the main worktree too (ASa) |
| DL7a | reuse without the branch check | DL-7 | same | KILLED |
| DL7b | reuse of anything at the path | DL-7 | same | KILLED |
| DL8a | the session started in the project folder | DL-1, DL-6, DL-7, DL-8, DL-9, DL-10 | same | KILLED |
| DL8b | `grants` with the accounting root | DL-8 | same | KILLED |
| DL9a | the prompt reworded | DL-9, DL-10, DL-12 | same | KILLED |
| DL9b | a briefing name may hold a space | DL-9 | same | KILLED |
| DL9c | a briefing at any depth under `briefings/` | DL-5, DL-9 | DL-9 | KILLED; prediction wrong: DL-5's `..` path is refused by `unlinked` first |
| DL9d | a hard-linked briefing accepted | DL-9 | same | KILLED |
| DL10 | the launch logged to `LEDGER.md`, not `DECISIONS.md` | DL-10 | same | KILLED |
| DL11a | a registry cwd elsewhere only echoed | DL-11 | same | KILLED |
| DL11b | no registry cwd only echoed | DL-11 | none | SURVIVED: the wrong-directory refusal fired after it, and DL-11 read the whole output |
| DL12 | the dry run makes the worktree | DL-12 | same | KILLED |
| DL13a | no `check_model` on the direct path | DL-13 | same | KILLED |
| DL13b | `--name` taken | DL-13 | same | KILLED |

DL11b: DL-11 now reads only the `refusing:` line, which must name the worktree and say `no cwd`; DL11a and DL11b
re-run, both KILLED. DL-13 gained three subtests after the code (a Worker launch given `--repo`, `--base` or
`--briefing`), so they owed a kill first: DL13c, that refusal turned off, reddened exactly those three. KILLED.

Declared guards inside DL-5: "repo through a link" is also refused by `convention_repo` (the spelling is not a
trusted repository's), "the worktree a link" by the reuse check, and "project through a link" by the briefing's own
`unlinked`. Each subtest guards the layer that names the link, and DL5 kills the test as a whole.

Review 1 F1: the refusal of an existing branch with no worktree had no subtest. DL-7 gained one after the code, so it
owed a kill: DL7c, `direct_worktree` without the `branch_exists` refusal, reddened exactly that subtest. KILLED.

## rw-git, leaf denies and `.worktrees` (U46)

The rows for a Worker's and a direct build's grants (leaf `<root>/**/.git` denies, `excludedCommands`, the git
directory denied whole) and the move to `<repo>/.worktrees/<slug>` were seen red on the U45 base. Each mutation ran in its
own scratch copy of the tree, with its red set predicted in writing first.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| L01 | a Worker gets no leaf on its worktree | the Worker deny test | same | KILLED |
| L02 | no `excludedCommands` | the Worker deny test, DL-8 | same | KILLED |
| L03 | no leaf on a granted root | the Worker deny test, the planner/explainer grants test, DL-8 | the first two; DL-8 green | KILLED; prediction wrong, see below |
| L04 | only the git directory's `config` denied, not the whole directory | the Worker deny test, the planner/explainer grants test | those, and four more deny tests | KILLED |
| L05 | the old place not recognised as a convention worktree | the old-place `run.json` test, DL-7 | same | KILLED |
| L06 | a direct build never falls back to the old place | DL-7 | same | KILLED |
| L07 | the launcher's direct fallback names `.worktrees` | DL-7 | same | KILLED |
| L08 | no `/.worktrees/` line added to `info/exclude` | the `info/exclude` test | same | KILLED |
| L09 | that line added even when it is there | the `info/exclude` test | same | KILLED |
| L10 | the launcher's path check drops `*/.worktrees/*` | the Worker deny test, the preflight-create test | the preflight-create test and seven others; the Worker deny test green | KILLED; prediction wrong: that test's worktree is not under `.worktrees` |
| L11 | the convention folder is the old one | the preflight-create test, the `info/exclude` test | those and 37 more | KILLED |
| L12 | a direct build made at the old place | DL-6 | DL-6 and six more DL tests | KILLED |
| L13 | only `.claude` counted as a folder deny | the Worker deny test, the planner/explainer grants test | same | KILLED |

L03 and DL-8: DL-8 compared the settings with `role_grants document` plus the worktree's own leaf. `document` builds
those settings from the same code, so the mutation changed both sides of the comparison equally and DL-8 stayed
green. DL-8 now also asserts, straight from the brief, that every granted root has a `<root>/**/.git` deny. On the
re-run, L03 kills DL-8.

Accepted untested: `os.path.isdir(path)` in `fragment`. A denied path that is a directory by any name other than
`.git` or `.claude` gets an `Edit(/<path>/**)` rule. Every directory denied today has one of those two names, so no
test can redden it. It protects a denied directory added later under another name, which would otherwise get only
`Edit(/<path>)`, a rule that covers none of the files inside it.

Review 1 fixes:
- **F1, WT-12.** The exclude line now lands on its own line after a last line with no newline. WT-12 was red first.
- **F9, the allow rule.** A committing role's settings carry `permissions.allow: ["Bash(rw-git *)"]`, since an
  excluded command goes through the regular permission flow. WS-2 and DL-8 now assert it, and WS-7 asserts its absence;
  all three were red first.

A full re-run after the fixes killed L01–L16 and I01–I07, each in its own scratch copy. L09 was re-pointed at the new
exclude check before it ran, and L10's prediction is as wrong as before.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| L14 | the exclude line appended bare | WT-12 | same | KILLED |
| L15 | no allow rule for a committing role | WS-2, DL-8 | same | KILLED |
| L16 | the allow rule for every role | WS-7 | same | KILLED |

## U52b · `session_write.py read` (SW-22, SW-23)

Applied to `owner_git.read_unlinked`, which `session_write.read` wraps; both tests red (usage, exit 1) before the code.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | the folder walk opens each folder without `O_NOFOLLOW` | SW-22 | same | KILLED |
| M2 | the size check refuses at `READ_LIMIT`, not past it | SW-23 | same | KILLED |

## U52b · review fix rounds (WT-13, WT-14, WT-15)

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| G5 | the checkout run from the repository with `-C <worktree>` | WT-13 | same | KILLED |
| G5b | no checkout after `--no-checkout` | WT-13 | same | KILLED |
| G7 | the checkout's `--no-recurse-submodules` dropped (gate fix round 2) | WT-14 | same | KILLED |
| G8 | the failed checkout's `worktree remove` dropped | WT-15 | same | KILLED |
| G9 | the branch `-b` made is never deleted after a failed checkout | WT-15 | same | KILLED |
