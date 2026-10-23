# run-roster.py — behaviour table

    python3 skills/lead/scripts/test_run_roster.py

Earlier units' rows are in the test classes' docstrings (`R7 ·`, `D4 ·`); this table starts at U56.

## 056 · a session folder nothing launched reads `briefed`

From U56 (briefed-tone), a direct build. A session the Planner briefed and nothing launched stores
`phase = preflight`, as a running preflight does. The state tool's `never_launched()` tells them apart: the
`briefed` state, no live session, no `session_id`, no `transcripts`, no `started_at`, nothing in `events.jsonl`.
Rows sourced `Assumed (Q1)` read the brief's `session` as `session_id` and `transcripts` (the launcher's pin) and its
`launched_at` as `started_at` (stamped by `preflight-pass`): neither key the brief names exists in any writer.

Fixture: `robowright-fixture-working` with `phase = preflight`, `session_id` and `started_at` empty, no
`events.jsonl`, units `U1` and `U2` todo.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 056-R1 | never launched | the fixture, no live session | `describe()` | verdict `briefed` | brief B2: "A never-launched session gets its own verdict, `briefed`" | `test_describe__a_session_nothing_launched_reads_briefed_not_orphaned` |
| 056-R2 | preflight running | the fixture, a busy live session matched by worktree | `describe()` | verdict `running` | brief B1: "A briefed session with a live session (preflight running) … is not unlaunched" | `test_describe__a_briefed_session_with_a_busy_live_session_reads_running` |
| 056-R3 | died in preflight, pinned | the fixture, `session_id` set, no live session | `describe()` | verdict `orphaned` | brief B2: "A launch that died in preflight stays `orphaned`"; Assumed (Q1) | `test_describe__a_briefed_session_the_launcher_pinned_reads_orphaned__when_no_session_is_live` |
| 056-R4 | a hand-edited start time | the fixture, `started_at` set, no live session | `describe()` | verdict `orphaned` | brief B1: "with `launched_at` set and no live session"; Assumed (Q1) | `test_describe__a_briefed_session_with_a_start_time_reads_orphaned__when_no_session_is_live` |
| 056-R6 | a registry `cwd` not a string | the fixture; a busy live record with `cwd` the number `1` | `describe()` | verdict `briefed`, no exception | gate review F3: `realpath(1)` raised `TypeError`, which the dashboard's page build does not catch; session-inputs rule (hold every value to its shape) | `test_describe__a_registry_row_whose_cwd_is_not_a_string_matches_nothing` |
| 056-R7 | a registry `cwd` with a NUL | the fixture; a busy live record with `cwd` the worktree plus a NUL | `describe()` | verdict `briefed`, no exception | gate review F3: `realpath` raised `ValueError`, every dashboard card an error row | `test_describe__a_registry_row_whose_cwd_holds_a_nul_matches_nothing` |
| 056-R5 | not unfinished work | the fixture, alone under the root; a first `--since` tick, then a second | the second tick | `no change since last tick: 1 session(s), 0 unfinished` | brief B2: "It is not counted as unfinished work" (the `--since` unfinished count) | `test_roster__since_counts_no_unfinished_work__when_the_only_session_was_never_launched` |

## 056 · `never_launched()` in `session-state.py`

Tested in `skills/robowright/scripts/test_session_state.py`, `NeverLaunchedTests`, on the module loaded by path.
Fixture: the suite's `given_session()` (`phase = preflight`, no `session_id`, no `started_at`, no `events.jsonl`).

| # | Given | When | Then | Source | Test |
|---|---|---|---|---|---|
| 056-S1 | the fixture | `never_launched(…, is_live=False)` | `True` | brief B1: "`briefed` state, no `session`, no `launched_at`, and 0 events" | `test_never_launched__true_for_a_briefed_session_nothing_touched` |
| 056-S2 | the fixture | `is_live=True` | `False` | brief B1: "with a live session (preflight running) … is **not** unlaunched" | `test_never_launched__false_while_a_live_session_runs_preflight` |
| 056-S3 | `session_id` a UUID | `is_live=False` | `False` | brief B1: "no `session`"; Assumed (Q1) | `test_never_launched__false_once_the_launcher_pinned_a_session` |
| 056-S4 | `transcripts` one path | `is_live=False` | `False` | as S3 | `test_never_launched__false_once_the_launcher_pinned_a_transcript` |
| 056-S5 | `started_at` set | `is_live=False` | `False` | brief B1: "no `launched_at`"; Assumed (Q1) | `test_never_launched__false_once_a_start_time_is_stamped` |
| 056-S6 | one line in `events.jsonl` | `is_live=False` | `False` | brief B1: "0 events" | `test_never_launched__false_once_any_event_is_logged` |
| 056-S7 | `phase = intake`, nothing else set | `is_live=False` | `False` | brief B1: "`briefed` state" | `test_never_launched__false_past_the_briefed_state` |

Q1 (above) changes a Then of R3, R4, S3, S4 and S5 if the Owner meant a field a writer should start storing; B4
rules that out.

Red before the code: R1 (`'orphaned' != 'briefed'`), R5 (`'… 0 unfinished' not found in 'no change since last tick:
1 session(s), 1 unfinished'`), S1 (`False is not True`, the skeleton's constant). R2–R4 and S2–S7 were green at red;
their kills are in `tests/dash/TEST-LEDGER.md` → 056.
R6 and R7, added after the gate review, were red on the defect itself: `TypeError` and `ValueError` out of
`realpath`, the exceptions their Then rules out.

Changed after red: two tests in `skills/robowright/scripts/test_session_state.py`,
`test_roster__a_session_with_no_worktree_matches_no_live_session` and
`test_roster__one_undescribable_session_does_not_blind_the_rest`, built a bare `{"phase": "preflight"}` fixture, a
brief nothing launched, and asserted `orphaned` beside what each tests (no worktree matches no live session; one bad
file costs one row). B2 makes that fixture `briefed`, so their Then now reads `briefed`; neither row's subject changed.

## 052a · `park` from `briefed`

From U52a (final-fixes-a), a direct build. The Owner decided (2026-10-18) that `park` also leaves `briefed`, with
the guards it already has: `--by owner` and a non-empty `--reason`. The `parked` record keeps its shape; its `from`
reads `briefed`. Tested in `skills/robowright/scripts/test_session_state.py`: S rows in `ParkTests`, R1 in
`IntegrationTests`. Fixture: the suite's `given_session()` (`phase = preflight`, nothing launched).

| # | Given | When | Then | Source | Test |
|---|---|---|---|---|---|
| 052a-S1 | the fixture | `park --by owner --reason <why>` | exit 0; `phase = parked`, `parked.from == "briefed"`, `parked.reason` the reason | REPLAN U52a → A: "`from` becomes `"briefed"` for this case" | `test_park__from_briefed_records_briefed_as_origin` |
| 052a-S2 | the fixture | `park --by owner`, no `--reason` | refused by the reason guard, `run.json` untouched | REPLAN U52a → A: "The guards `park-is-owner` and `park-reason-given` … apply unchanged" | `test_park__from_briefed_refused_without_a_reason` |
| 052a-S3 | the fixture | `park --by lead --reason <why>` | refused `park-is-owner`, `run.json` untouched | as S2 | `test_park__from_briefed_refused_for_anyone_but_the_owner` |
| 052a-S4 | `intake`, `implementing`, `end-of-stack`, `awaiting-rotation` in turn | `park --by owner --reason <why>` | refused `from-state`, `run.json` untouched | `state-machine.json` `park.from` = `briefed`, `done`, `stopped`; replaces U2's R2 set | `test_park__refused_from_every_state_but_briefed_done_and_stopped` |
| 052a-R1 | the fixture, parked by the state tool from `briefed` | the roster, `--json` | the row's verdict is `parked` | REPLAN U52a → A: "the roster prints a parked session on its `parked:` line unchanged" | `test_roster__a_session_parked_from_briefed_reads_parked` |

## 065 · a session with no ticket is labelled by its directory name

From U65 (parked-fixes), a direct build. Where `launch.json` names a ticket shape, a session may now carry no ticket;
its unit id is then its directory's name, as the launcher reads it. The roster's plan label matches the Task Breakdown
row on that unit id, not on the raw `ticket`, so a ticket-less session is labelled like any other. The row's `ticket`
field stays the raw value.

Fixture: a bare-slug session dir `export-csv`, `ticket` null, `project` `sample`, 3 of 5 brief units done, a busy live
session; project `sample` planning `| U9 | \`export-csv\` | Exports notes as CSV. | … |`.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 065-N1 | no ticket, bare slug | the fixture | `render()` | the units cell reads `U9 (export-csv) · 3/5` | the U65 note: a ticket-less session shows in each reader as its unit id, the directory name; the launcher's fallback | `test_render__labels_a_session_with_no_ticket_by_its_directory_name` |

Red before the code: N1 (`'3/5' != 'U9 (export-csv) · 3/5'`). A dir in the `<project>-NNN-<rest>` form would match
through the name rules already, so the row uses a bare slug.
