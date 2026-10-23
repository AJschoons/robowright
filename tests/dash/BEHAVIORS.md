# Robowright dashboard, run from the clone — behaviour table

Commit ids in this record refer to the project's history before it was published; they are not in this repository.

Written before the code, from the unit's brief (U1 acceptance rules 1-7, decisions D1-D4, D9 and the
reviewer's hotspots). Rows sourced `pre-change behavior at 55d542de` pin what the brought-in dashboard
already did and must keep; `Assumed` rows are defaults taken unattended — each changes a Then if the
Owner answers otherwise. `<old>` stands for a retired product name, `legacy` in
`test_dash.py`.

    python3 tests/dash/test_dash.py

Questions behind the Assumed rows:
- Q3 A copy outside the clone: exit 2, one stderr line naming the missing `run-roster.py`, no traceback.
- Q4 A symlink into the clone resolves through `Path(__file__).resolve()` and runs normally.
- Q5 A leading `~/` in launch.json's `projects_root` is `$HOME/`, as the roster reads `sessions_root`.
- Q8 `owner_brief` present (even false) wins over `review_guide` (settled by D4).
- Q9 The hold phrase is read from the `--once` pages; the text summary prints no Lead-stage phrase.
- Q10 The gaps file keys the longest silence in minutes by session slug (pre-change behavior).
- Not pinned: several `--runs-root` flags (Q1); an accounting root that is named but absent (Q2).

## Table

Fixture defaults (the `given…()` helpers): scratch `$HOME` (realpath'd temp dir) and cwd; sessions root
`<base>/roots/sessions`, projects root `<base>/roots/projects`; project `sample` with one Task Breakdown
row `U1 | first`; session `sample-001-first`, phase `implement`, every file last written 5 minutes ago;
the three `ROBOWRIGHT_*_ROOT` variables stripped unless the row sets them.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| R1.1 | summary from launch.json's roots | launch.json names `sessions_root` and `projects_root`; project `sample`; session `sample-001-first` implementing | `robowright-dash.py` | exit 0; a line begins `sample: `; a line reads `sample-001-first  implement …` | brief rule (1): "prints the text summary of the scratch project and its sessions, exit 0"; line shape: pre-change behavior at 55d542de (`text_summary`: `<project>: …` head, one `<slug>  <phase>` line per live session) | `test_prints_the_project_and_its_live_session__when_launch_json_names_both_roots` |
| R1.2 (held out) | summary from `~/` roots | launch.json names `~/roots/sessions` and `~/roots/projects`, both under the scratch `$HOME` | `robowright-dash.py` | as R1.1 | D1: the roster's `launch_path` — "a leading `~/` becomes $HOME/"; Assumed (Q5) for `projects_root` | `test_reads_home_relative_roots__when_launch_json_names_them_with_a_tilde` |
| R2.1 | refuses by name | no launch.json, no env, no flag | `robowright-dash.py` | exit 2; stdout empty; stderr is exactly `run-roster.py: no sessions root: set sessions_root in <HOME>/.claude/robowright/launch.json (no such file), or set $ROBOWRIGHT_SESSIONS_ROOT, or pass --runs-root` | brief rule (2); D1: "The refusal is the roster's line and exit code 2"; the line: `run-roster.py:578, 611-612` | `test_refuses_with_the_rosters_line_and_exit_2__when_nothing_names_a_sessions_root` |
| R2.2 (held out) | a projects root alone is not a sessions root | launch.json names only `projects_root` | `robowright-dash.py` | exit 2; stdout empty; stderr is exactly `run-roster.py: no sessions root: set sessions_root in <launch.json> (sessions_root is missing, empty or not a string), or set $ROBOWRIGHT_SESSIONS_ROOT, or pass --runs-root` | Goal: "refusing by name with exit 2 when none names one"; the line: `run-roster.py:609-612` | `test_refuses__when_launch_json_names_only_a_projects_root` |
| R2.3 | `--once` refuses too | nothing names a sessions root | `--once <base>/out` | exit 2; stdout empty; stderr begins `run-roster.py: no sessions root:`; no `index.html` in `<base>/out` | Q6, settled by the Goal | `test_refuses_and_writes_no_pages__when_once_runs_with_no_sessions_root` |
| R3.1 | `--runs-root` beats the env | sessions `sample-001-from-flag` under the flag root, `sample-002-from-env` under `$ROBOWRIGHT_SESSIONS_ROOT`, `sample-003-from-launch` under launch.json's | `--runs-root <flag root>` | exit 0; stdout names `sample-001-from-flag`, not `sample-002-from-env`, not `sample-003-from-launch` | brief rule (3): "`--runs-root` beats `$ROBOWRIGHT_SESSIONS_ROOT`" | `test_reads_the_flag_sessions_root__over_the_env_and_launch_json` |
| R3.2 | the env beats launch.json | as R3.1 without the flag | `robowright-dash.py` | exit 0; names `sample-002-from-env`, not `sample-003-from-launch` | brief rule (3): "which beats `launch.json`" | `test_reads_the_env_sessions_root__over_launch_json` |
| R3.3 | `--projects-root` beats the env | project `sample` with unit `from-flag` under the flag root, `from-env` under `$ROBOWRIGHT_PROJECTS_ROOT`, `from-launch` under launch.json's `projects_root` | `sample --projects-root <flag root>` | exit 0; stdout names `from-flag`, not `from-env` | brief rule (3): "`--projects-root` beats `$ROBOWRIGHT_PROJECTS_ROOT`" | `test_reads_the_flag_projects_root__over_the_env` |
| R3.4 | the env beats launch.json | `from-env` under the env root, `from-launch` under launch.json's | `sample` | exit 0; names `from-env`, not `from-launch` | brief rule (3): "which beats `launch.json`'s `projects_root`" | `test_reads_the_env_projects_root__over_launch_json` |
| R3.5 | launch.json beats the parent | `from-launch` under launch.json's `projects_root`, `from-parent` under the sessions root's parent | `sample` | exit 0; names `from-launch`, not `from-parent` | brief rule (3): "which beats the sessions root's parent" | `test_reads_launch_json_projects_root__over_the_sessions_roots_parent` |
| R3.6 | the parent is the last default | launch.json names only `sessions_root` (`<base>/roots/sessions`); `from-parent` at `<base>/roots/sample` | `sample` | exit 0; names `from-parent` | D2: "else the sessions root's parent" | `test_reads_the_sessions_roots_parent__when_nothing_names_a_projects_root` |
| R3.7 (held out) | the parent of a flag-named root | no launch.json; `from-parent` at `<base>/flag-roots/sample` | `sample --runs-root <base>/flag-roots/sessions` | exit 0; names `from-parent` | D2 as R3.6, the sessions root as `--runs-root` names it | `test_reads_the_flag_sessions_roots_parent__when_only_runs_root_is_given` |
| R4.1 | `--once` writes gaps under the accounting root | launch.json roots; a working session quiet 5 min; `$ROBOWRIGHT_ACCOUNTING_ROOT` = `<base>/accounting` (exists) | `--once <base>/out` | exit 0; `<base>/accounting/robowright-dash.gaps.json` has `sample-001-first` ≥ 5; no file under the clone's `tools/` added or rewritten | brief rule (4); D3; entry shape: pre-change behavior at 55d542de (Q10) | `test_writes_the_gaps_file_under_the_accounting_root__when_once_writes_pages` |
| R4.2 | `--serve` writes gaps there too | as R4.1 | `--serve <free port>`, one GET `/` | the GET answers 200; the gaps file as R4.1; `tools/` unchanged | brief rule (4): "`--serve` polled once" | `test_writes_the_gaps_file_under_the_accounting_root__when_served_and_polled_once` |
| R4.3 | no accounting root, no write | no launch.json, no env; a working session quiet 5 min | `--once <base>/out --runs-root <base>/roots/sessions` | exit 0; no `robowright-dash.gaps.json` anywhere under the scratch base; `tools/` unchanged | brief rule (4): "with no accounting root nothing is written anywhere and the run still succeeds"; D3: "with only `--runs-root` and nothing else, `accounting_root(None)` is None" | `test_writes_no_gaps_file_anywhere__when_no_accounting_root_is_named` |
| R4.5 | no bytecode for the clone's scripts | as R4.3; `PYTHONPYCACHEPREFIX` = `<base>/pycache`, `PYTHONDONTWRITEBYTECODE` unset | `robowright-dash.py --runs-root <base>/roots/sessions` | exit 0; no `.pyc` under the prefix for a file of the clone | D3: "the script directory becomes read-only in fact"; end-of-stack review F1 | `test_writes_no_bytecode_for_the_scripts_it_loads__when_python_would_cache_them` |
| R4.4 (held out) | the root beside the sessions root | launch.json names `sessions_root` `<base>/roots/sessions` and no `accounting_root`; `<base>/roots/accounting` exists; no env | `robowright-dash.py` | exit 0; `<base>/roots/accounting/robowright-dash.gaps.json` has `sample-001-first` | D3: "else `accounting` beside the sessions root named by … launch.json `sessions_root`" | `test_writes_the_gaps_file_beside_the_sessions_root__when_launch_json_names_only_that` |
| R5.1 | `owner_brief` holds a finished session | `robowright.json` `{"owner_brief": true}`; `sample-001-first` done, INTAKE.md present, worktree a plain dir (not in main); no owner brief | `--once <base>/out` | exit 0; the pages contain `Waiting on the Lead's owner brief` | brief rule (5); D4: the display text "becomes `waiting on the Lead's owner brief`"; surface: Assumed (Q9) | `test_holds_a_finished_session_for_the_owner_brief__when_robowright_json_asks_for_one` |
| R5.2 | the brief releases it | as R5.1 plus `reviews/sample-001-first-owner-brief.md` in the project folder | `--once <base>/out` | exit 0; the pages do not contain the phrase | brief rule (5): "until `reviews/<slug>-owner-brief.md` exists" | `test_releases_the_session__when_its_owner_brief_exists` |
| R5.3 | `review_guide` is the alias | `robowright.json` `{"review_guide": true}`; no brief | `--once <base>/out` | exit 0; the pages contain the phrase | brief rule (5): "a folder with `{"review_guide": true}` behaves the same (alias)" | `test_holds_the_session__when_robowright_json_uses_the_review_guide_alias` |
| R5.5 (held out) | `owner_brief` present wins over the alias | `robowright.json` `{"owner_brief": false, "review_guide": true}`; no brief | `--once <base>/out` | exit 0; the pages do not contain the phrase | D4: "the switch is `owner_brief`, read as `review_guide` when absent" (Q8) | `test_does_not_hold_the_session__when_owner_brief_is_false_beside_the_alias` |
| R6.1 | in main on `robowright/<slug>` | scratch repo: `robowright/sample-001-first` one commit ahead of `main`, fast-forwarded into `main`; the session done, INTAKE.md, worktree = the repo | `sample` | exit 0; the U1 line reads `complete` | brief rule (6); label: pre-change behavior at 55d542de (`PLAN_LABEL`) | `test_reads_the_unit_complete__when_its_robowright_branch_is_in_main` |
| R6.2 | no old-prefix branch is tried | as R6.1 but the branch is `<old>/sample-001-first` (in `main`); no `robowright/` branch | `sample` | exit 0; the U1 line reads `awaiting acceptance`, not `complete` | brief rule (6): "no `<old>/` prefix is tried"; label as R6.1 | `test_reads_the_unit_awaiting_acceptance__when_only_an_old_prefix_branch_is_in_main` |
| R6.3 (held out) | a branch not in main is not complete | `robowright/sample-001-first` one commit ahead, not merged | `sample` | exit 0; the U1 line reads `awaiting acceptance` | brief rule (6): "reads landed when that branch is in main" — not otherwise | `test_reads_the_unit_awaiting_acceptance__when_its_robowright_branch_is_not_in_main` |
| R7.1 | no private path | the clone's `tools/robowright-dash.py` | its lines searched for a home-directory path (`/Users/`, `/home/`) (case-sensitive, as `grep -n -E`) | no line matches | brief rule (7) | `test_carries_no_home_directory_path` |
| H1 | a copy outside the clone fails by name | launch.json roots; the script copied to `<base>/elsewhere/tools/` | the copy runs | exit 2; stderr is one line naming `<base>/elsewhere/skills/lead/scripts/run-roster.py`; no `Traceback` | hotspot: "fails with one stderr line naming that path, non-zero exit, no traceback (Assumed: exit 2)" (Q3) | `test_fails_with_one_line_naming_the_missing_roster__when_copied_outside_the_clone` |
| H2 | a symlink runs normally | launch.json roots; project and session as R1.1; `<base>/linked/robowright-dash.py` → the clone's script | the symlink runs | as R1.1 | hotspot: "resolves through `Path(__file__).resolve()` and runs normally (Assumed)" (Q4) | `test_prints_the_summary__when_run_through_a_symlink_into_the_clone` |
| H3 | no accounting root, nothing in the cwd | as R4.3 | `robowright-dash.py --runs-root <base>/roots/sessions` from the scratch cwd | exit 0; stdout names `sample-001-first`; no `robowright-dash.gaps.json` in the cwd | hotspot: "`record_quiet` with no accounting root writes no `robowright-dash.gaps.json` into the cwd"; brief rule (4) | `test_writes_no_gaps_file_into_the_cwd__when_no_accounting_root_is_named` |

Rule 7 has no held-out row: it is one static search over the whole file.

## U2 — a Summary cell per unit, spend from the ledger, the verdict and the asks on a finished card

Written before the code, from U2's brief (rules 1-6, brief correction 3, decisions D5, D6, D8, D9, D12 and the
reviewer's hotspots). Rows sourced `observed at e2927cd` pin what the dashboard already does and must keep.

Questions behind the Assumed rows:
- Q1 The text summary's purpose line is in the detailed summary (`robowright-dash.py <project>`), on the unit's line
  or the line under it.
- Q2 A row whose cell count differs from a `Summary` header's has no purpose line: every cell after the break is shifted.
- Q3 A well-formed row whose `Summary` cell is empty takes its purpose from `Description` (D6: "from it, else from description").
- Q4 A card's spend line is one `div.note.spend` in its Details, reading `<n> requests`, `<n> output tokens`, `$<x.xx> est.` and
  `<h.h> h active`, formatted as the rollup's table formats them (`{:,}`, `.2f`, `.1f`); `n/a est.` when unpriced. A row reads a line as its visible text followed by its titles, which hold the exact figures.
- Q5 A Claude session's active time counts once however many records it has, as the rollup counts it.
- Q6 The project's spend is one line on the project page, the hero's `p.facts`, outside every session card.
- Q7 The "no ledger" note is on the project page, once (case-insensitive `no ledger`).
- Q8 The verdict is one element, class `verdict`, on the finished session's card.
- Q9 The asks line reads `<n> asks` in the card, with each ask's text.
- Not pinned: a ledger with no record for a session's ticket (absent line or zeros); project records for a ticket
  with no session dir (D5's "sum over its sessions" against rule 2's rollup); a verdict on an unfinished card;
  `1 ask` or `1 asks`; a spend line in the text summary or on the index page; the legacy `-review-guide.md` brief.

Fixture defaults: launch.json naming `<base>/roots/sessions` and `<base>/roots/projects` unless the row says
otherwise. The R1 rows use SLUG done, through intake, worktree not in main (U1 awaiting acceptance). The R2 rows use
U1 `first` and U2 `second`, both working, `$ROBOWRIGHT_ACCOUNTING_ROOT` = `<base>/accounting`. Ledger records are
written `(ticket, role, session_id, requests, output tokens, estimated USD, active seconds)`.
Records: A = `(sample-001-first, worker, w-1, 12, 3400, 1.25, 1800)`, B = `(sample-001-first, reviewer, r-1, 5, 1100, 0.40, 1080)`,
C = unit-scope `(sample-001-first, worker, w-1, 7, 2000, 0.90, 900)` with unit_id U1, D = `(sample-002-second, worker, w-2, 3, 600, 0.20, 360)`.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| U2-R1.1 | Summary header, Summary purpose | header `SUMMARY_HEADER` (D6); U1 row Summary `Totals the sample's spend per unit.`, Description `Parser rewrite …` | `--once <out>` | every `class="purpose"` on index and sample pages is the Summary text; at least one | rule (1): "gives each unit's purpose line the Summary cell … in `--once` HTML" | `test_shows_the_summary_cell_as_every_purpose_line__when_the_header_has_summary` |
| U2-R1.2 | same, text summary | as U2-R1.1 | `sample` | the U1 line or the one under it has the Summary text; stdout has no Description text | rule (1): "in the text summary"; placement Assumed (Q1) | `test_prints_the_summary_cell_with_its_unit__when_the_header_has_summary` |
| U2-R1.3 | no Summary, Description purpose | pre-D6 header, row well-formed | `--once <out>` | every purpose is the Description text | rule (1): "a header without it gives the Description cell"; observed at e2927cd (green at red) | `test_shows_the_description_cell_as_every_purpose_line__when_the_header_has_no_summary` |
| U2-R1.4 | same, text summary | as U2-R1.3 | `sample` | the U1 line or the one under it has the Description text | rule (1); placement Assumed (Q1) | `test_prints_the_description_cell_with_its_unit__when_the_header_has_no_summary` |
| U2-R1.5 | the guard, unchanged | Summary header; U1 row one cell short (the pre-D6 row) | `--once <out>` | sample page shows `PROJECT.md row has 8 cells, the header has 9`; the plan row's size is blank | rule (1): "still blanks size … and shows the row error (the existing cell-count guard, unchanged)"; text observed at e2927cd (green at red) | `test_shows_the_row_error_and_a_blank_size__when_a_row_is_one_cell_short_of_a_summary_header` |
| U2-R1.6 | no shifted purpose | as U2-R1.5 | `--once <out>` | no purpose element on either page (not `ENG-7`, not `docs/first.md`) | hotspot: "a mismatched row must not show a shifted cell as its purpose"; none at all Assumed (Q2) | `test_shows_no_purpose_line__when_a_row_is_one_cell_short_of_a_summary_header` |
| U2-R1.7 | same, text summary | as U2-R1.5 | `sample` | stdout has neither `ENG-7` nor `docs/first.md` | hotspot as U2-R1.6 (Q2) (green at red) | `test_prints_no_shifted_cell__when_a_row_is_one_cell_short_of_a_summary_header` |
| U2-R1.8 | empty Summary falls back | Summary header; U1's Summary cell empty | `--once <out>` | every purpose is the Description text | D6: "sets the purpose line from it, else from `description`"; Assumed (Q3) (green at red) | `test_shows_the_description_cell_as_the_purpose__when_the_summary_cell_is_empty` |
| U2-R2.1 | a card sums its session records | ledger A, B, C | `--once <out>` | SLUG's card has one spend line, in its Details: `17 requests`, `4,500 output tokens`, `$1.65 est.`, `0.8 h active` (A+B; C would make 24) | rule (2): "shows the two session records' sums … and not the unit record's"; D5; format Assumed (Q4) | `test_shows_the_sum_of_its_tickets_session_records__not_the_unit_record` |
| U2-R2.2 | keyed by ticket, not session_dir | ledger A, B, and D written from SLUG's dir | `--once <out>` | SECOND's card: `3 requests`, `600 output tokens`, `$0.20 est.`, `0.1 h active`; SLUG's shows `17 requests` | D5: "whose `unit` equals `run.json.ticket` … never `session_dir`" | `test_keys_each_card_by_the_records_ticket__not_the_session_dir_it_was_written_from` |
| U2-R2.3 | project spend is the rollup's | ledger A, B, C, D, and a project `other` record | `--once <out>` | one project spend line (the hero's facts): `20 requests`, `5,100 output tokens`, `$1.85 est.`, `0.9 h active`; the rollup's `sample` row is (20, 5100, 1.85, 0.9) | rule (2): "equals `robowright-cost.py --by project --json …` for that project's key, to the cent"; placement Assumed (Q6) | `test_shows_the_project_spend_the_rollup_gives_its_project__to_the_cent` |
| U2-R2.4 | one session's time once | A, and w-1 again on another model `(4, 300, 0.05, 1800)` | `--once <out>` | `16 requests`, `3,700 output tokens`, `$1.30 est.`, `0.5 h active` (not 1.0) | `robowright-cost.py` rollup: "a row's active hours count each Claude session once"; Assumed (Q5) | `test_counts_one_claude_sessions_active_time_once__when_it_has_a_record_per_model` |
| U2-R2.5 | unpriced is n/a, not 0.00 | A and B with `estimated_usd: null` | `--once <out>` | `17 requests`; `n/a est.`; no `0.00` | hotspot: "must not crash the sum nor print `0.00`"; the rollup's table prints `n/a` for a null row | `test_marks_the_estimate_n_a__when_no_record_of_the_ticket_is_priced` |
| U2-R2.6 | null adds nothing | A null, B 0.40 | `--once <out>` | `$0.40 est.` | hotspot: "follow what the rollup does for null USD" — `rollup` adds only non-null estimates | `test_sums_the_priced_records__when_one_of_the_tickets_records_is_unpriced` |
| U2-R2.7 | a ticket-less session adds nothing | A, B, D, and a `unit: null` Lead record of project `other` (50 requests); a third `sample` session whose `run.json.ticket` is null | `--once <out>` | the project spend line (the hero's facts): `20 requests`, `5,100 output tokens`, `$1.85 est.`, `0.9 h active` — the rollup's `sample` row | D5: "sum over its sessions"; rule (2): equals the rollup's row; added after gate finding F1 (U2 gate attempt 1) | `test_leaves_out_records_with_no_unit__when_a_session_of_the_project_has_no_ticket` |
| U2-R3.1 | no root, no spend line | no launch.json, no env; `--runs-root` only; two sessions | `--once <out> --runs-root <sessions>` | no `spend` element, no ` est.` on either page; sample page says `no ledger` once | rule (3); D5: "the line is absent and the page says 'no ledger' once"; placement Assumed (Q7) | `test_shows_no_spend_line_and_one_no_ledger_note__when_nothing_names_an_accounting_root` |
| U2-R3.2 | no file, no spend line | accounting root exists, no `records.jsonl`; two sessions | `--once <out>` | as U2-R3.1 | rule (3): "or a root with no `records.jsonl`" | `test_shows_no_spend_line_and_one_no_ledger_note__when_the_accounting_root_has_no_records_file` |
| U2-R3.3 | a malformed line is skipped | A, a truncated line, `[1, 2]`, B | `--once <out>` | exit 0; `17 requests`, `$1.65 est.` | rule (3): "skipped as `read_records` skips it" | `test_skips_a_malformed_ledger_line__and_sums_the_rest` |
| U2-R3.4 | a ledger, no note | ledger A | `--once <out>` | no `no ledger` on the sample page | rule (3) read with its converse: the note stands for the missing ledger (green at red) | `test_carries_no_no_ledger_note__when_the_ledger_exists` |
| U2-R4.1 | a finished card shows the verdict | SLUG done; `plan_reviews` `[{n 1, verdict polish}]` | `--once <out>` | SLUG's card has one `verdict` element, containing `polish` | rule (4); D8; element Assumed (Q8) | `test_shows_the_verdict_on_the_card__when_run_json_has_one_plan_review` |
| U2-R4.2 | the newest wins | `[{n 1, 09-19, rebrief}, {n 2, 09-20, polish}]` — last, highest n and latest agree | `--once <out>` | one `verdict`: `polish`, not `rebrief` | D8: "the newest `run.json.plan_reviews[]` entry's `verdict`" | `test_shows_the_newest_verdict_only__when_run_json_has_two_plan_reviews` |
| U2-R4.3 | no key, nothing | SLUG done, no `plan_reviews` | `--once <out>` | no `verdict` element | rule (4): "an absent key … shows nothing" (green at red) | `test_shows_no_verdict__when_run_json_has_no_plan_reviews_key` |
| U2-R4.4 | empty list, nothing | `plan_reviews: []` | `--once <out>` | no `verdict` element | rule (4): "or `[]`, shows nothing" (green at red) | `test_shows_no_verdict__when_run_json_has_an_empty_plan_reviews_list` |
| U2-R5.1 | asks from the table | owner brief, `## Decide now` a table of 2 rows, then `## Key decisions` with 1 row | `--once <out>` | SLUG's card: `2 asks`, both ask texts | rule (5); brief correction 3: "one ask per table body row … ends at the next `## `"; wording Assumed (Q9) | `test_lists_two_asks_and_their_text__when_decide_now_has_two_table_rows` |
| U2-R5.2 | asks from bullets | `## Decide now` with 2 `- ` bullets | `--once <out>` | `2 asks`, both texts | rule (5): "has two bullets … shows '2 asks' and both bullet texts" | `test_lists_two_asks_and_their_text__when_decide_now_has_two_bullets` |
| U2-R5.3 | empty section | `## Decide now`: prose and a header-only table | `--once <out>` | `0 asks` | brief correction 3: "An empty section shows '0 asks'" | `test_shows_zero_asks__when_decide_now_has_no_rows` |
| U2-R5.4 | no brief, no line | no owner brief | `--once <out>` | the sample page has no `<n> ask(s)` | rule (5): "no file, no line" (green at red) | `test_shows_no_asks_line__when_there_is_no_owner_brief` |
| U2-R6.1 | the template's header | `skills/planner/PROJECT-TEMPLATE.md` | its Task Breakdown header read | exactly D6's nine columns | rule (6); D6 | `test_has_the_d6_header__in_the_task_breakdown` |
| U2-R6.2 | every example row | as U2-R6.1 | its body rows read | each has 9 cells and a non-empty Summary cell | rule (6): "every example row has the cell" | `test_gives_every_example_row_a_summary_cell__in_the_task_breakdown` |
| U2-R6.3 | the note's sentence | as U2-R6.1 | grep, not a test | the note says the Planner fills `Summary` when the row is created, one or two plain sentences, never its status | rule (6); D6 — the wording is the implementer's, so the caller's grep and doc gate check it | — |

Invariant (a `PROJECT.md` without `Summary` renders as at U1): U2-R1.3 and the U1 rows above pin it; no page-diff
test against U1's script, because the new spend and card elements and the note change every page by design.

## P1 — the project line is `--by project`'s row, "Nothing" is not an ask, one ask is singular, a malformed plan review is no verdict

Written before the code, from the polish brief (`PLAN-REVIEW.md` §6, P1, rules 1-4). The project's key is its
folder name, which is what `robowright-cost.py` records as `project`; no ledger or `run.json` field is added.
U2-R2.3 and U2-R2.7 stand unchanged.

Questions behind the Assumed rows:
- P1-Q1 A card counts every session-scope record whose `unit` is its ticket, whatever the record's `project` (the
  brief: "A card still shows the session-scope records for its own ticket only"; U2 D5). A record of project `other`
  naming SLUG's ticket is on SLUG's card and not on `sample`'s project line.
- Not pinned: the text summary; a project with no record of its own; "Nothing to decide" or any other wording than
  `nothing`/`none`; a non-object entry before the last.

Fixture defaults as U2's. Ledger records `(ticket, role, session_id, requests, output tokens, estimated USD, active
seconds)`, project `sample` unless named: A as U2's, P = `(null, planner, p-1, 9, 2300, 0.70, 720)`,
Z = `(sample-001-first, worker, w-8, 40, 8000, 3.00, 2880)` of project `other`.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| P1-R1.1 | the project line is the rollup's project row | ledger P, A, Z | `--once <out>` | the rollup's `sample` row is (21, 5700, 1.95, 0.7); one project spend line (the hero's facts): `21 requests`, `5,700 output tokens`, `$1.95 est.`, `0.7 h active` (P+A; the tickets' records A+Z would make 52); SLUG's card: `52 requests`, `11,400 output tokens`, `$4.25 est.`, `1.3 h active` (A+Z) | rule (1): "P's line counts the first two and not the third, and equals `robowright-cost.py --by project --json` for P to the cent"; card: "A card still shows the session-scope records for its own ticket only" — Assumed (P1-Q1) | `test_counts_the_projects_records_whatever_their_unit__not_another_projects_record_of_its_ticket` |
| P1-R2.1 | a "Nothing" row is no ask | `## Decide now` a table whose only body row's first cell is `Nothing` | `--once <out>` | SLUG's asks line: `0 asks`, no `Nothing` | rule (2): "a Decide now whose only row says 'Nothing' reads as '0 asks'" | `test_shows_zero_asks__when_decide_nows_only_table_row_says_nothing` |
| P1-R2.2 | a "None." bullet is no ask | `## Decide now` bullets `None.` and ASK_FLAG | `--once <out>` | SLUG's asks line: count `1` (either form), ASK_FLAG, no `None` | rule (2): "lowercased and stripped of a trailing period, is `nothing` or `none`, in a table row or a bullet … a section with 'Nothing' and one real ask reads '1 ask'" | `test_counts_one_ask__when_decide_now_has_a_none_bullet_and_one_real_ask` |
| P1-R3.1 | one ask is singular | `## Decide now` a table of one row, ASK_EXPORT | `--once <out>` | SLUG's asks line: `1 ask`, not `1 asks`; ASK_EXPORT | rule (3): "A finished card with exactly one ask reads '1 ask', not '1 asks'" (green at red) | `test_reads_one_ask_in_the_singular__when_decide_now_has_exactly_one_row` |
| P1-R4.1 | a last plan review that is not an object | SLUG done; `plan_reviews` `[{n 1, rebrief}, "polish"]` | `--once <out>` | exit 0, no `Traceback` on stderr; SLUG's card present; no `verdict` element on either page | rule (4): "A `plan_reviews` whose last entry is not an object shows no verdict line and no traceback" (green at red) | `test_shows_no_verdict_and_no_traceback__when_the_last_plan_review_is_not_an_object` |

The count in P1-R2.2 matches `1 ask` and `1 asks` alike, so dropping the singular branch reddens P1-R3.1 only.

## P3 — dollars only under a dollar brief, one plan-usage line per page

Written before the code, from the second polish brief (P3, rules 1-3; the Owner: "follow the roster's existing
rule, plus one plan-usage line per page"). "Sets" a limit means what run-roster.py's row build and `usage_cell`
mean: `number(run.json[field]) is not None`, so `0` is set and `null` or a missing key is not. The plan-usage
reading is run-cost.py's `plan_usage()`: `$CLAUDE_USAGE_DIR` when it is set and non-empty, else `~/.claude/usage`;
file `latest.json`; `(None, None, None)` on a missing file, bad JSON or a non-object.

Given change to rows already here: `Spend`'s sessions (SLUG, SECOND, and U2-R2.7's `sample-003-briefing`) now set
`spend_threshold_usd: 25` (`DOLLAR_BRIEF`), so U2-R2.1…R2.7, U2-R3.3 and P1-R1.1 keep pinning their own rule under a
dollar brief. Their Whens and Thens are unchanged. The test harness also strips `$CLAUDE_USAGE_DIR` unless a test
sets it (`env_usage=`), as it strips the `ROBOWRIGHT_*_ROOT` variables.

Brief correction (Owner), 2026-09-27, before the implementing commit: rule 2 is "every", not "any". A project's
spend line shows a dollar estimate (`$x est.`) only when every one of the project's sessions' run.json sets either field, and there is
at least one session; a mixed or session-less project shows no dollar figure, not even `n/a` (a dollar figure beside
spend that was never billed in dollars misleads). P3-R2.2's Then flipped
with it; P3-R2.3 and P3-R2.4 were added. Source: the amended brief, rule 2.

Presentation, the Worker's call under the brief ("the Worker decides … exact wording/formatting of the plan-usage
line, where on the page it sits"): one element of class `plan-usage`, outside every session card, reading
`Plan usage · 5-hour <p>% · 7-day <p>% · as of <captured_at>`. Each percentage is printed as the reading gives it
(`str`, as robowright-cost.py's `fmt` prints plan percentages), and `captured_at` as the reading gives it. On the
index it sits under the `Projects` heading, and on a project page after the hero (033-B8); since 2026-10-15 it reads
`Plan usage, all projects · …` (033-B44). Position is otherwise not pinned.

Brief-driven Then change (F1, 2026-09-27, before F1's implementing commit): the line's time is no longer
`captured_at` as the reading gives it. P3-R3.1, P3-R3.2 and P3-R3.3 now expect its local clock time, `as of 21:45:00`
for TAPPED and `as of 10:10:00` for HOME under `TZ=Asia/Kolkata`, and no raw ISO string on the line. Their Givens and
Whens are unchanged, and their runs now set `TZ` (plumbing). Source: F1 rule 1, "the reading's `captured_at` shown as
local wall-clock time in the footer's format … never the raw number". P3-R3.5 keeps its Then.

Questions behind the Assumed rows:
- P3-Q1 "No reading": a `latest.json` that gives neither percentage, whatever its `captured_at`, is no reading, so
  no line.
- P3-Q2 A reading with one window present: the line shows that window and leaves the other out. No `None`, no `-`.
- P3-Q3 A reading with no `captured_at`: the line shows the percentages and no time. No `as of None`.
- Not pinned: the text summary; `--serve`; `--project`; a non-object `latest.json` (plan_usage gives the same
  `(None, None, None)` as bad JSON); a limit written as a numeric string; a limited session with no ticket as the
  project's only limited brief; where on the index the plan-usage line sits (a project page's place is 033-B8's).

Fixture defaults as U2's. Ledger A, B, D as U2's (A, B of SLUG; D of SECOND). `sample`'s rollup row over A, B, D is
(20, 5100, 1.85, 0.9), as U2-R2.3. Readings: TAPPED = 5-hour 42, 7-day 17.5, at `2026-09-27T09:15:00-07:00`;
HOME = 5-hour 88, 7-day 61, at `2026-09-26T21:40:00-07:00`. The P3-R3 and P3-R4 sessions set no limit.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| P3-R1.1 | no limit, no dollars on the card | SLUG's brief sets neither field; SECOND's sets a threshold; ledger A, B | `--once <out>` | SLUG's card spend: `17 requests`, `4,500 output tokens`, `0.8 h active`; no `usd`, no `1.65`, no `$`, no `n/a` | rule (1): "Otherwise the line shows requests, output tokens and active hours, and no dollar figure, not even `n/a`"; "A card's spend line … its session's run.json" | `test_shows_requests_tokens_and_hours_and_no_dollar_figure__when_its_brief_sets_no_spend_limit` |
| P3-R1.2 | a cap alone is a limit | SLUG's brief: `spend_cap_usd: 40` only; ledger A, B | `--once <out>` | SLUG's card: `$1.65 est.` | rule (1): "sets `spend_threshold_usd` or `spend_cap_usd`" (green at red) | `test_shows_the_dollar_estimate__when_its_brief_sets_only_a_spend_cap` |
| P3-R1.3 | zero is set | SLUG's brief: `spend_threshold_usd: 0` only; ledger A, B | `--once <out>` | SLUG's card: `$1.65 est.` | rule (1): "(the rule run-roster.py's `usage_cell` uses …)"; `number(0)` is `0.0`, not None (green at red) | `test_shows_the_dollar_estimate__when_its_brief_sets_a_zero_spend_threshold` |
| P3-R1.4 | null is not set | SLUG's brief: both fields `null`; SECOND's sets neither; ledger A, B | `--once <out>` | SLUG's card: `17 requests`; no `usd`, no `1.65` | rule (1): "the rule run-roster.py's `usage_cell` uses"; `number(None)` is None | `test_shows_no_dollar_figure__when_its_brief_writes_both_spend_limits_as_null` |
| P3-R1.5 | no limit, no `n/a` | SLUG's and SECOND's briefs set neither; A, B unpriced | `--once <out>` | SLUG's card: `17 requests`; no `n/a`, no `usd` | rule (1): "and no dollar figure, not even `n/a`" | `test_shows_no_n_a__when_its_brief_sets_no_limit_and_no_record_of_its_ticket_is_priced` |
| P3-R2.1 | no session limited, no project dollars | SLUG's and SECOND's briefs set neither; `other-001-elsewhere` (project `other`) sets `spend_cap_usd: 40`; ledger A, B, D | `--once <out>` | one project spend line (the hero's facts): `20 requests`, `5,100 output tokens`, `0.9 h active`; no `usd`, no `1.85`, no `$`, no `n/a` | rule (2), amended: "only when every one of the project's sessions' run.json sets either field … otherwise the same line without a dollar figure"; "the figures themselves stay the rollup's `--by project` row" | `test_shows_the_project_line_with_no_dollar_figure__when_none_of_its_sessions_sets_a_limit` |
| P3-R2.2 | a mixed project shows no dollars | SLUG's brief sets neither; SECOND's sets a threshold; ledger A, B, D | `--once <out>` | one project spend line (the hero's facts): `20 requests`; no `usd`, no `1.85`, no `$`, no `n/a` | rule (2), amended: "a project that mixes dollar-limited and unlimited briefs … shows the line with no dollar figure" (Brief correction, Owner) | `test_shows_the_project_line_with_no_dollar_figure__when_one_of_its_two_sessions_sets_no_limit` |
| P3-R2.3 | every session limited, dollars, whatever another project's briefs | SLUG's and SECOND's briefs set a threshold; `other-001-elsewhere` (project `other`) sets neither; ledger A, B, D | `--once <out>` | the project spend line (the hero's facts): `$1.85 est.`, `20 requests` | rule (2), amended: "only when every one of the project's sessions' run.json sets either field" — the project's sessions, not another project's (green at red; owes a kill) | `test_shows_the_project_dollar_estimate__when_every_one_of_its_sessions_sets_a_limit__whatever_another_projects_brief_sets` |
| P3-R2.4 | no sessions, no dollars | `sample` has no session; ledger: P = `(null, planner, p-1, 9, 2300, 0.70, 720)` of `sample` | `--once <out>` | one project spend line (the hero's facts): `9 requests`, `2,300 output tokens`, `0.2 h active`; no `usd`, no `0.70` | rule (2), amended: "(and there is at least one session)"; figures: the rollup's `sample` row (P1 rule 1) (green at red; owes a kill) | `test_shows_the_project_line_with_no_dollar_figure__when_the_project_has_no_session` |
| P3-R3.1 | the index's line, from `$CLAUDE_USAGE_DIR` | TAPPED under `$CLAUDE_USAGE_DIR`; HOME under `~/.claude/usage` | `--once <out>` | index: one `plan-usage` element: `5-hour 42%`, `7-day 17.5%`, `2026-09-27T09:15:00-07:00`; no `88` | rule (3): "Each page the dashboard writes (the index …) carries one plan-usage line … read the way … `plan_usage()` reads it (`$CLAUDE_USAGE_DIR`, else `~/.claude/usage` …)"; wording the Worker's | `test_shows_one_plan_usage_line_on_the_index_from_claude_usage_dir__over_the_reading_under_home` |
| P3-R3.2 | the project page's line | as P3-R3.1; `sample.html` carries two cards | `--once <out>` | replaced by 033-B8: the project page has one plan-usage line, after its hero; the index has one | rule (3): "(the index and each project page) carries one plan-usage line" | — |
| P3-R3.3 | the `~/.claude/usage` fallback | no `$CLAUDE_USAGE_DIR`; HOME under the scratch `~/.claude/usage` | `--once <out>` | index: one line: `5-hour 88%`, `7-day 61%`, `2026-09-26T21:40:00-07:00` | rule (3): "`$CLAUDE_USAGE_DIR`, else `~/.claude/usage`, file `latest.json`" | `test_reads_the_plan_usage_under_home__when_claude_usage_dir_is_unset` |
| P3-R3.4 | one window present | `$CLAUDE_USAGE_DIR`: 5-hour 42 only, TAPPED's time | `--once <out>` | index: one line: `5-hour 42%`; no `7-day`, no `None` | Assumed (P3-Q2): the brief names "the 5-hour and 7-day percentages" and says nothing of one missing | `test_shows_only_the_five_hour_window__when_the_reading_has_no_seven_day_window` |
| P3-R3.5 | no `captured_at` | `$CLAUDE_USAGE_DIR`: 5-hour 42, 7-day 17.5, no `captured_at` | `--once <out>` | index: one line: `5-hour 42%`, `7-day 17.5%`; no `None`, no `as of` | Assumed (P3-Q3): the brief names "the reading's `captured_at`" and says nothing of one missing | `test_shows_the_percentages_and_no_time__when_the_reading_has_no_captured_at` |
| P3-R4.1 | no file, no line | no `$CLAUDE_USAGE_DIR`; nothing under the scratch `~/.claude/usage` | `--once <out>` | exit 0; no `Traceback`; no `plan-usage` element and no `5-hour` on the index or `sample.html` | rule (3): "No reading, a missing file, or bad JSON: no line and no traceback … a machine on an API key has no status-line tap and so no line" (green at red) | `test_shows_no_plan_usage_line_and_no_traceback__when_there_is_no_reading_file` |
| P3-R4.2 | bad JSON, no line | `$CLAUDE_USAGE_DIR`: a torn `latest.json` | `--once <out>` | as P3-R4.1 | rule (3): "or bad JSON: no line and no traceback" (green at red) | `test_shows_no_plan_usage_line_and_no_traceback__when_the_reading_is_not_valid_json` |
| P3-R4.3 | no window, no reading | `$CLAUDE_USAGE_DIR`: `{"captured_at": …}` only | `--once <out>` | as P3-R4.1 | rule (3): "No reading … no line"; Assumed (P3-Q1) what "no reading" covers (green at red) | `test_shows_no_plan_usage_line__when_the_reading_has_neither_window` |
| P3-R4.4 | a set `$CLAUDE_USAGE_DIR` is the only place read | `$CLAUDE_USAGE_DIR` an empty directory; HOME under `~/.claude/usage` | `--once <out>` | as P3-R4.1 | rule (3): "read the way … `plan_usage()` reads it (`$CLAUDE_USAGE_DIR`, else `~/.claude/usage` …)" (green at red) | `test_shows_no_plan_usage_line__when_claude_usage_dir_has_no_reading_though_home_does` |

## F1 — the plan-usage time is a local clock time, and the Quiet group starts open when nothing is live

Written before the code, from the fix brief (DECISIONS.md 2026-09-27 "dashboard fixes"). The Owner found every project
in the collapsed "Quiet · 4" group under "No project has a live session right now.", and the Lead found the plan-usage
line printing `captured_at` raw ("as of 1800000028"). The Owner chose "Quiet option (a) — open when no project is live,
collapsed otherwise". The rules, in the brief's words:
1. The plan-usage line's time is the reading's `captured_at` as local wall-clock time in the footer's format
   (`%H:%M:%S`, `datetime.now().astimezone()`), never the raw number. It accepts an int or float in seconds and an
   ISO-8601 string. Anything else (a bool, a non-numeric string, a negative or unparseable value) drops the
   " · as of …" part and keeps the percentages, never a traceback.
2. The index's "Quiet · N" group starts open when no project has a live session (the "No project has a live session
   right now." branch), and stays collapsed when at least one does.

What the tap writes: `skills/robowright/scripts/usage-tap.py` writes `"captured_at": int(time.time())`, epoch seconds
as a JSON integer. run-cost.py's `plan_usage()` hands `captured_at` back untouched, whatever its type, so the
dashboard is the only place that can apply the rule.

Local means the dashboard process's zone (`TZ`), as the footer's time is. Every run that asserts a clock time sets
`TZ=Asia/Kolkata` (+05:30, no DST), so a time printed in UTC shows, and so does the raw value. Each expected time is a
literal derived outside the dashboard with `TZ=Asia/Kolkata date -r <epoch> '+%T'`, never computed in a test.

Presentation, the Worker's call: the line keeps P3's shape, `Plan usage · 5-hour <p>% · 7-day <p>% · as of HH:MM:SS`,
and a dropped time leaves `Plan usage · 5-hour <p>% · 7-day <p>%`. Since 2026-10-15 the label reads
`Plan usage, all projects` (033-B44). An open Quiet group is
`<details class="group" id="quiet" open>`.

Harness plumbing: `env()` and `run_dash()` take `env_tz=` and set `TZ` for that run only. `PlanUsage.run_once` and
the F1 runs pass `Asia/Kolkata`. `Page` records whether an element carries `open`, read by `Page.is_open(id)`.
`given_project` takes `name=`, so a second, quiet project `other` can sit beside `sample`.

Questions behind the Assumed rows (none is the Owner's to decide: the tap never writes F1-Q1–Q4's shapes, and F1-Q5
follows the rule's own parenthetical):
- F1-Q1 An ISO-8601 string with no offset: read as local wall-clock time and shown as written (`09:15:00`). It names
  no zone, so the clock it writes is the only time it states, and reading it as UTC would add a zone it never named.
  This is also what `datetime.fromisoformat(…).astimezone()` does with a naive value.
- F1-Q2 A numeric string (`"1800000028"`): dropped. Rule 1 accepts "an int or float in seconds and an ISO-8601
  string". A quoted number is neither, and the tap writes a JSON number. Guessing its unit would show a wrong time,
  which is worse than no time. `fromisoformat` rejects it, so only an implementation that coerces strings to numbers
  would show one.
- F1-Q3 `0`: accepted, and shown as `05:30:00` under the tests' zone. Rule 1 puts the drop boundary at "negative",
  so 0 is on the accept side. `-1` (F1-R1.8) is the other side of that boundary. P3's `if captured` drop of a falsy
  value does not carry over.
- F1-Q4 NaN: dropped as "unparseable", because it names no instant. `Infinity` follows the same path as F1-R1.9's
  overflow and is not pinned separately.
- F1-Q5 A project on the index only through an attention row (here a finished session awaiting acceptance: tone `done`, so
  not in the project's live sessions, but it gets a card): Quiet stays collapsed. Rule 2's parenthetical names the
  branch, "the "No project has a live session right now." branch", which is the empty-cards branch, and that branch
  is not taken here. The Owner's defect was an index with no project in view, and a card is a project in view. The
  literal words "no project has a live session" would open it, and the note would then be absent while Quiet is
  open, which is the reading this row rules out. (A stopped, briefed, unknown or owner-call session is not
  terminal, so it already counts as live and needs no row.)

Not pinned:
- `--serve`: the served index is the same `render_index`, and the suite runs no JavaScript. See "Viewer toggle".
- Whether fractional seconds are truncated or rounded.
- An ISO string ending in `Z`, which takes F1-R1.3's offset path.
- A `captured_at` that is a JSON object or list.
- `Infinity`.
- A reading from another day shows its clock time and no date. That is the rule's format, `%H:%M:%S`.
- Where the line and the group sit on the page.
- The project hook's dashboard count line.

Viewer toggle (the page's script; a note, not a test). Nothing per group is in localStorage or sessionStorage. Only
under `--serve` (http) does the script refresh in place. Before it swaps in the fresh `#main`, it records every
`details[id]`'s `open` in a `kept` Map, then re-applies it, so on every in-place refresh the group's state on
screen beats the server's default. The viewer's own toggle therefore wins with no change to the script. A result is
that the new default applies only on a full load: under `--once` (file://, a full reload each time), on the first
`--serve` load, and on a browser reload. If a session goes live while a served index is open, Quiet stays open
until the next full load, and the reverse holds too. That is the viewer's state winning, as rule 2 asks, and the
script stays as it is. No Python-observable seam exists for it.

Fixture defaults: F1-R1 rows are project `sample` with no session, and a reading at `$CLAUDE_USAGE_DIR` with 5-hour 42,
7-day 17.5 and the row's `captured_at`. F1-R2 rows have no reading and no accounting root.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| F1-R1.1 | the tap's int epoch is a local clock time | `captured_at: 1800000028` (int, the tap's shape) | `--once <out>` under `TZ=Asia/Kolkata` | index line: `as of 13:30:28`; no `1800000028` | rule 1: "shown as local wall-clock time in the footer's format (`%H:%M:%S` …), never the raw number"; "epoch seconds today (e.g. 1800000028)"; `TZ=Asia/Kolkata date -r 1800000028 '+%T'` → `13:30:28` (`TZ=UTC` → `08:00:28`) | `test_shows_the_local_clock_time_and_not_the_number__when_captured_at_is_the_taps_int_epoch_seconds` |
| F1-R1.2 | a float epoch in seconds | `captured_at: 1800000028.25` | as F1-R1.1 | `as of 13:30:28`; no `1800000028` | rule 1: "accept an int or float in seconds"; `date -r 1800000028` as F1-R1.1. The .25 s is under half a second, so truncating and rounding both give `:28` | `test_shows_the_local_clock_time__when_captured_at_is_float_epoch_seconds` |
| F1-R1.3 | an ISO-8601 string with an offset is its instant, in the local zone | `captured_at: "2026-09-27T09:15:00-07:00"` | as F1-R1.1 | `as of 21:45:00`; no `2026-09-27` | rule 1: "accept … an ISO-8601 string", "shown as local wall-clock time"; 09:15 −07:00 = 16:15:00 UTC = epoch 1790525700; `TZ=Asia/Kolkata date -r 1790525700 '+%T'` → `21:45:00` | `test_shows_the_local_clock_time_of_the_instant__when_captured_at_is_an_iso_string_with_an_offset` |
| F1-R1.4 | an ISO string with no offset is local time | `captured_at: "2026-09-27T09:15:00"` | as F1-R1.1 | `as of 09:15:00`; no `2026-09-27` | Assumed (F1-Q1): read as local wall-clock time and shown as written. Read as UTC it would be `14:45:00` | `test_shows_the_clock_time_as_written__when_captured_at_is_an_iso_string_with_no_offset` |
| F1-R1.5 | zero is an epoch | `captured_at: 0` | as F1-R1.1 | `as of 05:30:00` | Assumed (F1-Q3): rule 1 drops "a negative … value", so 0 is accepted; `TZ=Asia/Kolkata date -r 0 '+%T'` → `05:30:00` | `test_shows_the_epochs_local_clock_time__when_captured_at_is_zero` |
| F1-R1.6 | a bool drops the time | `captured_at: true` | as F1-R1.1 | exit 0, no `Traceback`; one line, `5-hour 42%`, `7-day 17.5%`; no `as of`, no `True`, no `true` | rule 1: "anything else (a bool, …) drops the " · as of …" part and keeps the percentages, never a traceback". Read as an int, `true` would show `05:30:01` | `test_shows_the_percentages_and_no_time__when_captured_at_is_a_bool` |
| F1-R1.7 | a non-numeric string drops the time | `captured_at: "yesterday"` | as F1-R1.1 | as F1-R1.6; no `yesterday` | rule 1: "(… a non-numeric string …) drops" | `test_shows_the_percentages_and_no_time__when_captured_at_is_a_non_numeric_string` |
| F1-R1.8 | a negative number drops the time | `captured_at: -1` | as F1-R1.1 | as F1-R1.6; no `-1` | rule 1: "(… a negative … value) drops". Read as an epoch, `-1` would show `05:29:59` | `test_shows_the_percentages_and_no_time__when_captured_at_is_negative` |
| F1-R1.9 | a number past any clock drops the time | `captured_at: 100000000000000000000` (10^20, int) | as F1-R1.1 | as F1-R1.6; no `100000000000000000000`, no `1e+20` | rule 1: "(… unparseable value) drops … never a traceback"; the Lead's spec prompt: "an unparseable/out-of-range value". CPython's `fromtimestamp(10**20)` raises OverflowError | `test_shows_the_percentages_and_no_time__when_captured_at_is_past_the_platforms_time_range` |
| F1-R1.10 | NaN drops the time | `captured_at: NaN` (as Python's json writes and reads it) | as F1-R1.1 | as F1-R1.6; no `nan`, no `NaN` | Assumed (F1-Q4): a float that names no instant is "unparseable" | `test_shows_the_percentages_and_no_time__when_captured_at_is_nan` |
| F1-R1.11 | a numeric string drops the time | `captured_at: "1800000028"` | as F1-R1.1 | as F1-R1.6; no `1800000028` | Assumed (F1-Q2): neither "an int or float in seconds" nor "an ISO-8601 string" | `test_shows_the_percentages_and_no_time__when_captured_at_is_a_numeric_string` |
| F1-R1.12 | an ISO instant past the local range drops the time | `captured_at: "9999-12-31T23:59:59-12:00"` | as F1-R1.1 | as F1-R1.6; no `9999` | rule 1: "(… unparseable value) drops … never a traceback"; its instant is 9999-12-31T23:59:59 −12:00, past `datetime.max` in +05:30. Added after the fixes gate's F1 (red on `3e12b21`: an OverflowError traceback) | `test_shows_the_percentages_and_no_time__when_captured_at_is_an_iso_string_past_the_local_range` |
| F1-R1.13 | a zoneless ISO string that cannot be placed drops the time | `captured_at: "9999-12-31T23:59:59"` | as F1-R1.1 | as F1-R1.6; no `9999` | rule 1 as F1-R1.12; placing it in the local zone (F1-Q1) steps past year 9999. Added after the fixes gate's F1 (red on `3e12b21`: a ValueError traceback) | `test_shows_the_percentages_and_no_time__when_captured_at_is_a_zoneless_iso_string_at_the_range_edge` |
| F1-R2.1 | nothing live: Quiet starts open | project `sample`, no session | `--once <out>` | index: `Quiet site. Nothing is running.` and no `No project has a live session right now.`; `details#quiet` has `open` | rule 2: "starts open when no project has a live session (the "No project has a live session right now." branch)"; Owner: "open when no project is live"; DESIGN-U33 §5 item 19 (the quiet crew card replaces the note) | `test_starts_the_quiet_group_open__when_no_project_has_a_live_session` |
| F1-R2.2 | one live project: Quiet stays collapsed | `sample` with SLUG working; `other`, no session | `--once <out>` | index: `details#quiet` without `open` | rule 2: "stays collapsed when at least one does"; Owner: "collapsed otherwise" (green at red; owes a kill) | `test_starts_the_quiet_group_collapsed__when_one_project_has_a_live_session` |
| F1-R2.3 | an awaiting-acceptance card takes the live branch | `sample`: SLUG finished and through intake, its worktree not in main, so no live session and one `Awaiting acceptance` row; `other`, no session | `--once <out>` | index: `Awaiting acceptance` shown (the Given); no `No project has a live session right now.`; `details#quiet` without `open` | Assumed (F1-Q5): rule 2 names "the "No project has a live session right now." branch", and that branch is not taken when a card shows (green at red; owes a kill) | `test_starts_the_quiet_group_collapsed__when_the_only_card_is_a_finished_session_awaiting_acceptance` |

## 023-U1 — a busy session on a finished unit is a follow-up pass; a busy Explainer is the owner brief in progress

Written before the code, from the unit's brief (U1 rules H2–H8, decisions D1 and D6) and the private copy's delta
(eight diff hunks, one feature), whose behaviour is the oracle for these rows. `BRIEF` below is that unit's brief.

Fixture defaults (class `FollowUpPass`): launch.json naming the scratch roots; project `sample`, whose
`robowright.json` is `{"owner_brief": true}`; SLUG `sample-001-first`; a worktree directory at
`<base>/worktrees/sample-001-first` that no main holds. The session is **released** (finished, through intake, owner
brief written at `<folder>/reviews/sample-001-first-owner-brief.md`) or **held** (the same without the brief, so
so it reads `Waiting on the Lead's owner brief`). Agents are written by `given_live_agent` into
`<scratch HOME>/.claude/sessions/<n>.json` with `pid: os.getpid()`; their `cwd` is the scratch cwd unless the row says
the worktree.

### Rules
R1 — A finished session that has a busy live agent named for a slug with the unit's project and number is on a follow-up pass. Its card reads working: the where line is `All units done · follow-up pass by <name>`, the state word is `Working`, the unit's tone is working, and the summary lists the session as live.
R2 — A busy live agent whose `cwd` is the session's `run.json.worktree` is a follow-up pass, whatever its name.
R3 — A busy agent that carries the Explainer prefix is not a follow-up pass. It holds the finished session for the Lead with `the Lead's owner brief in progress`.
R4 — An agent with the Planner or Lead prefix is never a follow-up pass, whether it matches by name or by worktree.
R5 — Only a busy agent can be a follow-up pass, and only on a session whose tone is done.
R6 — The Explainer prefix is `launch.json` `roles.explainer.name_prefix`. When that key is absent the prefix is `explainer`.
R7 — Only a registry row under `$HOME/.claude/sessions` whose `pid` is alive counts as a live agent.

### Questions
Q1 — H2's F1 Given says `owner_brief: true` but does not say whether the brief exists. Released or held? → Assumed: both. F1.1, F1.2 and F1.4 use a released session; F1.3 uses a held one. Reason: a held session is already in flight and listed live at `89d726c`, so only a released one makes every F1 Then differ from base. The held case is the collision row: the private copy flips the tone to `working` inside `load_session`, before `hold_for_lead`, and `hold_for_lead` acts only on tone `done`.
Q2 — The label: H2 only says it "ends `· follow-up pass`". → Settled by DESIGN-U33 §5 item 7: the card's state word is `Working` and the follow-up phrase is the where line, the first span of the card's now line.
Q3 — F7: "the registry file under a path other than `<scratch HOME>/.claude/sessions`". Which path? → Assumed: `<scratch cwd>/.claude/sessions`. That is the directory a registry path resolved relative to the working directory would read, so the row can fail.
Q4 — F4's `lead-sample`: its `cwd`? → Assumed: the unit's worktree. Its name holds no `-NNN-`, so without that cwd the prefix skip would be untested. The private copy's prefix `continue` comes before both the name match and the worktree match.
Q5 — F4, F5 (idle) and F7: "the session reads as at `89d726c`". Which base state? → Assumed: held. Then the base outcome is a positive Then, the where line `Waiting on the Lead's owner brief` (R5.1's `HOLD_PHRASE`), plus no `follow-up pass` anywhere on the pages.
Q6 — F5 (implementing): what shows? → Assumed: SLUG's card is on the project page, and `follow-up pass` appears on no page. The implementing card's own where line belongs to existing behaviour and is not pinned here.
Q7 — Is the Stuck? indicator on a follow-up pass part of U1? → Assumed: yes, as one row. Exploration doc §3.1: "A tone flipped to `working` makes `load_session` scan … which is what the Stuck? indicator reads — intended: a follow-up that writes nothing for `STUCK_MINUTES` is stuck". The brief's H4 hotspot says the same. 45 minutes is past `STUCK_MINUTES` = 30.
Q8 — "the text summary lists the session as live" and "the unit bar's tone is working": in which output? → Assumed: the detailed summary, `robowright-dash.py sample`. It carries a live line beginning `sample-001-first done` (R1.1's shape: slug, then phase), and its `U1` unit line reads `working` (the unit tone, read the way R6.1–R6.3 read it).
Q9 — F1's agent `cwd`? → Assumed: the scratch cwd, not the worktree. Then F1 rests on the name match alone, and the worktree mutation (d) reddens F2 alone, as the kill set predicts.

### Table
| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 023-U1-F1.1 | R1 | released; busy `worker-opus-sample-001-first-polish`, cwd elsewhere | `--once <out>` | index where line `All units done · follow-up pass by worker-opus-sample-001-first-polish`; SLUG's card state word exactly `Working`, and its now line starts with that where line | BRIEF H2: "where line is `All units done · follow-up pass by worker-opus-sample-001-first-polish`, whose label ends `· follow-up pass`"; private copy H6/H7; DESIGN-U33 §5 item 7. Q2 settled. Assumed Q1, Q9 | `test_shows_the_card_working_on_a_follow_up_pass__when_a_busy_agent_is_named_for_the_finished_unit` |
| 023-U1-F1.2 | R1 | as F1.1 | `robowright-dash.py sample` | a line splitting to `sample-001-first done …`; the `U1` unit line contains `working` | BRIEF H2: "the unit bar's tone is working; the text summary lists the session as live". Assumed Q1, Q8 | `test_lists_the_session_live_and_its_unit_working__when_a_busy_agent_is_named_for_the_finished_unit` |
| 023-U1-F1.3 | R1 × hold | held; the same agent | `--once <out>` | the F1.1 where line; `Waiting on the Lead's owner brief` on no page | private copy H4: the tone flips to `working` in `load_session`, and the hold acts only on `done`. Assumed Q1 (collision row) | `test_shows_the_follow_up_pass_and_not_the_owner_brief_hold__when_a_held_session_has_a_busy_agent_named_for_its_unit` |
| 023-U1-F1.4 | R1 | released, every file in the session dir last written 45 min ago, empty worktree; the same agent | `--once <out>` | index text contains `Stuck? · nothing written for` | exploration §3.1: "a follow-up that writes nothing for `STUCK_MINUTES` is stuck"; BRIEF hotspot H4: "placed after it, a follow-up never shows Stuck?". Assumed Q7 | `test_shows_the_follow_up_pass_stuck__when_nothing_was_written_for_longer_than_the_stuck_limit` |
| 023-U1-F2.1 | R2 | released; busy `task-dash-fixes`, `cwd` = `run.json.worktree` (the same realpath string) | `--once <out>` | index where line `All units done · follow-up pass by task-dash-fixes` | BRIEF H3: "the agent `task-dash-fixes` with `cwd` equal to `run.json.worktree` — as F1"; private copy H3 `agent.get("cwd") == worktree` | `test_shows_the_card_working_on_a_follow_up_pass__when_a_busy_agent_runs_in_the_finished_units_worktree` |
| 023-U1-F3.1 | R3 | held; busy `explainer-sample-001-first` | `--once <out>` | index where line `The Lead's owner brief in progress`; `Waiting on the Lead's owner brief` and `follow-up pass` on no page | BRIEF H4: "no follow-up line, and the hold phrase is that one rather than `waiting on the Lead's owner brief`"; private copy H1, H5; the where line's wording: DESIGN-U33 §5 item 7 | `test_holds_the_card_for_the_owner_brief_in_progress__when_a_busy_explainer_is_named_for_the_finished_unit` |
| 023-U1-F4.1 | R4 | held; busy `planner-sample-001-first` | `--once <out>` | index where line `Waiting on the Lead's owner brief`; `follow-up pass` on no page | BRIEF H5: "`planner-sample-001-first` … busy — no follow-up; the session reads as at `89d726c`"; where line is pre-change behaviour at `89d726c` (R5.1). Assumed Q5 | `test_keeps_the_held_card_as_it_was__when_a_busy_planner_is_named_for_the_finished_unit` |
| 023-U1-F4.2 | R4 | held; busy `lead-sample`, `cwd` = the worktree | `--once <out>` | as F4.1 | BRIEF H5: "or `lead-sample` busy — no follow-up"; private copy H3: the prefix `continue` precedes both matches. Assumed Q4, Q5 | `test_keeps_the_held_card_as_it_was__when_a_busy_lead_runs_in_the_finished_units_worktree` |
| 023-U1-F5.1 | R5 | held; **idle** `worker-opus-sample-001-first-polish` | `--once <out>` | as F4.1 | BRIEF H6: "the agent idle … — no follow-up"; private copy H3 `status != "busy"`. Assumed Q5 | `test_keeps_the_held_card_as_it_was__when_the_agent_named_for_the_finished_unit_is_idle` |
| 023-U1-F5.2 | R5 | SLUG **implementing** (U1 done, U2 todo, no intake); busy `worker-opus-sample-001-first-polish` | `--once <out>` | SLUG's card present on `sample.html`; `follow-up pass` on no page | BRIEF H6: "or the session implementing — no follow-up"; private copy H4 `if tone == "done" else None`. Assumed Q6 | `test_shows_no_follow_up_pass__when_the_session_is_still_implementing` |
| 023-U1-F6.1 | R6 × R3 | launch.json `roles.explainer.name_prefix: "guide"`; held; busy `guide-sample-001-first` | `--once <out>` | index where line `The Lead's owner brief in progress`; `follow-up pass` on no page | BRIEF H7: "agent `guide-sample-001-first` — F3's outcome"; D1: "`EXPLAINER_PREFIX` read from `launch.json` `roles.explainer.name_prefix` with `explainer` as the default" | `test_holds_the_card_for_the_owner_brief_in_progress__when_a_busy_agent_carries_launch_jsons_explainer_prefix` |
| 023-U1-F6.2 | R6 × R1 | `name_prefix: "guide"`; held; busy `explainer-sample-001-first` | `--once <out>` | index where line `All units done · follow-up pass by explainer-sample-001-first` | BRIEF H7: "`explainer-sample-001-first` under that setting is a follow-up" | `test_shows_the_follow_up_pass__when_a_busy_agent_carries_the_default_explainer_prefix_under_another_one` |
| 023-U1-F7.1 | R7 | held; busy `worker-opus-sample-001-first-polish`, live pid, its file at `<scratch cwd>/.claude/sessions/1.json` | `--once <out>` | as F4.1 | BRIEF H8: "the registry file under a path other than `<scratch HOME>/.claude/sessions` … — unseen". Assumed Q3, Q5 | `test_keeps_the_held_card_as_it_was__when_the_busy_agents_registry_file_is_outside_homes_registry` |
| 023-U1-F7.2 | R7 | held; the same agent in `<scratch HOME>/.claude/sessions`, `pid` of an exited and reaped process | `--once <out>` | as F4.1 | BRIEF H8: "or `pid` dead — unseen". Assumed Q5 | `test_keeps_the_held_card_as_it_was__when_the_busy_agents_pid_is_dead` |

Rows F1.1–F1.4 are four tests because a page run and a summary run are two Whens, and because F1.3 (collision) and
F1.4 (Stuck?) are separate examples of R1. F6 has two tests, one for each half of H7.

## 023-U2 — a session is filed by `run.json.project` and claimed by `run.json.ticket`; the owner brief is read from `review_guide_dir`

Written before the code, from the unit's brief (U2 checks 1–8, decisions D2–D4). `BRIEF` below is that unit's brief.

Fixture defaults (classes `Binding`, `TicketClaim`, `OwnerBriefDirectory`): launch.json naming the scratch roots;
project `sample`; SLUG `sample-001-first`. `TicketClaim` writes its own Task Breakdown (`given_plan`); B4 adds
`examples/desktop/launch.json`'s `unit` block and a folder `SMPL-482`. `OwnerBriefDirectory` sets `review_guide_dir`.

### Rules
R1 — A session with a `run.json` is filed under `run.json.project` when that is a non-empty string, and under its directory name's capture otherwise.
R2 — A session with no `run.json` (a brief being written) is filed under the capture, as before.
R3 — A session whose project has no folder with a `PROJECT.md` is an orphan, listed on the index under "Sessions with no project folder" and on no project's page.
R4 — A Task Breakdown row claims every session whose unit id equals its Unit cell (backticks stripped, trimmed), before any name rule. The unit id is `run.json.ticket`, else the session directory's name (U65; before it, a session with no ticket had none).
R5 — A session claimed by ticket belongs to that row only. The name-after-the-number and owned-number rules apply only to sessions that no row claimed by ticket, whatever the rows' order.
R6 — A session whose unit id equals no row's Unit cell is claimed by the name rules as before.
R7 — The owner-brief directory under the project folder is launch.json's `review_guide_dir`, both for the Lead's hold and for the card's Decide-now asks.
R8 — When `review_guide_dir` is absent or empty, the directory is `reviews`.

### Questions
Q1 — B1: "absent from `sample`'s page and summary line". Which summary? → Assumed: the plain `robowright-dash.py` summary. It is the one run that prints both projects, so SLUG's live line (`sample-001-first  implement`, R1.1's shape) can be checked under `other:`'s head and absent under `sample:`'s.
Q2 — How is "claimed by U1" read? → Settled by: Language, "claimed — a session listed under a Task Breakdown row", together with the brief's B4 wording "the page carries no 'Not claimed by any unit'". On the project page, a row's plan state links each session it lists. The link is labelled with the session number, or with the slug when the slug has none (`unit_state`, pre-change behavior at `6277db0`). B4 also checks the note is absent. That absence alone would also pass when the session is filed nowhere, which is mutation (a).
Q3 — An empty-string `project`? → Settled by: D2, "when it is a non-empty string, else the capture", and the hotspot "`run.get("project") or project_of(dir_.name)` files an empty-string `project` by the capture".
Q4 — A `project` that is not a string? → Settled by: D2, "a non-empty string, else the capture", and the hotspot "a `project` that is not a string is a finding if it reaches the page". The value is Assumed: `["other"]`. A list is a plausible hand edit, and under the exploration doc's own sketch it would not even reach the page: the orphan check (`s["project"] not in known`, a set) raises on an unhashable value.
Q5 — "An orphan on the index": where? → Settled by: D2, "listed as a capture miss is today (`:723`)". A capture miss shows under the index heading `Sessions with no project folder`, with its card (`render_index`, pre-change behavior at `6277db0`).
Q6 — B5 puts the ticket row first. Does the rule hold when the row whose name matches comes first? → Settled by: D3, "a ticket-claimed session belongs to that row only, and the name rules apply to the sessions no row claimed by ticket", and the hotspot "the ticket pass must run over every row before any name pass". This gives row B5.3.
Q7 — B6 says "a Decide-now ask". Which brief, and what shows? → Assumed: `BRIEF_ONE_ASK`. The card shows `1 ask` and the ask's text, which is the asks line of U2-R5 (pre-change).
Q8 — B6 with the brief under `reviews/` only: does the card show its asks? → Settled by: D4, "`lead_stage` (`:595`) and the Decide-now read (`:676`) use `CONFIG.get("review_guide_dir") or "reviews"`". The configured directory has no brief, so the card has no asks line (U2-R5.4: no brief, no asks line).
Q9 — `review_guide_dir: ""`? → Settled by: D4's `or "reviews"`. That gives row B7.2.
Q10 — B7, the key absent: a new test? → Settled by: D4, "R5.1–R5.5 stay green with no test edited". B7.1 is a declared guard carried by existing tests whose launch.json has no `review_guide_dir` (`given_launch_roots`). No new test, because nothing a new test would catch is missed by R5.2 and U2-R5.1.
Q11 — B8 says "ticket null". What about a ticket that is no row's Unit cell? → Settled by: D3, "the name rules apply to the sessions no row claimed by ticket". Every earlier row has this Given: `given_session` writes `ticket` = SLUG, and the cell is `first`. B8.2 states it explicitly.
Q12 — Two rows with the same Unit cell? → Not pinned. It is a Decision-authority door ("stop with the rows"), and the brief gives the Lead's answer in advance: "the first row in table order claims it; log it as `Assumed`". If the Worker meets it, it is the Worker's stop, not a Then written here.

### Table
| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 023-U2-B1.1 | R1 | folder `other` with a `PROJECT.md`; SLUG with `project: "other"` | `--once <out>` | SLUG's card on `other.html`; no SLUG card on `sample.html` | BRIEF check (1): "filed under `other`, absent from `sample`'s page"; D2 | `test_files_the_session_under_its_run_json_project__when_its_directory_name_captures_another` |
| 023-U2-B1.2 | R1 | as B1.1 | `robowright-dash.py` | `[sample-001-first, implement]` among the live lines under `other: …`; `sample: …` printed without it | BRIEF check (1): "absent from `sample`'s … summary line". Assumed Q1 | `test_lists_the_live_session_under_its_run_json_project_in_the_summary__when_its_directory_name_captures_another` |
| 023-U2-B2.1 | R1 | SLUG with `project: null` | `--once <out>` | SLUG's card on `sample.html` | BRIEF check (2): "`project` null or absent — under `sample`"; D2 | `test_files_the_session_under_the_capture__when_run_json_project_is_null` |
| 023-U2-B2.2 | R1 | SLUG with `project: ""` | `--once <out>` | as B2.1 | D2 "non-empty string"; hotspot D2. Q3 settled | `test_files_the_session_under_the_capture__when_run_json_project_is_an_empty_string` |
| 023-U2-B2.3 | R1 | SLUG with `project: ["other"]` | `--once <out>` | exit 0; as B2.1 | D2 "non-empty string, else the capture"; hotspot "not a string is a finding if it reaches the page". Assumed Q4 (value) | `test_files_the_session_under_the_capture__when_run_json_project_is_not_a_string` |
| 023-U2-B2-absent | R1 | SLUG with no `project` key | any | as at `89d726c` | BRIEF check (2): "every R-row at `89d726c` green unchanged". **Declared guard**: `given_session` writes no `project`, so every earlier row is this example | every test before `023-U2` |
| 023-U2-B2.4 | R2 | dir SLUG with no `run.json`; busy live agent `planner-sample-001-first` | `--once <out>` | SLUG's card on `sample.html` | D2: "`pending_session` (no `run.json`) keeps the capture"; Invariant: "every session with no `run.json`, is filed exactly as at `89d726c`" | `test_files_a_brief_being_written_under_the_capture__when_its_session_dir_has_no_run_json` |
| 023-U2-B3.1 | R3 | SLUG with `project: "ghost"`; no folder `ghost` | `--once <out>` | index text has `Sessions with no project folder` and SLUG's card; no SLUG card on `sample.html` | BRIEF check (3): "an orphan on the index, not under `sample`"; D2 "listed as a capture miss is today". Q5 settled | `test_lists_the_session_with_no_project_folder__when_run_json_project_names_a_folder_that_does_not_exist` |
| 023-U2-B4.1 | R4 | launch.json's `unit` = `examples/desktop/launch.json`'s block; folder `SMPL-482`, row `` \| U1 \| `SMPL-482` \| … ``; session dir `SMPL-482`, `{ticket: "SMPL-482", project: "SMPL-482"}` | `--once <out>` | U1's plan state on `SMPL-482.html` links `SMPL-482`; that page has no `Not claimed by any unit` | BRIEF check (4): "claimed by U1, the page carries no 'Not claimed by any unit'"; D3. Q2 settled | `test_claims_the_tracker_session_for_its_row__when_run_json_ticket_equals_the_unit_cell` |
| 023-U2-B5.1 | R4 | rows U1 `` `sample-001-first` ``, U2 `` `sample-001-first-rerun` ``; dir `sample-001-first-rerun`, `ticket: "sample-001-first"` | `--once <out>` | U1's plan state links `001` | BRIEF check (5): "claimed by the first row only"; D3 "claims … by ticket first" | `test_claims_the_session_for_the_row_its_ticket_names__when_another_row_matches_its_directory_name` |
| 023-U2-B5.2 | R5 | as B5.1 | `--once <out>` | U2's plan state does not link `001` | BRIEF check (5) "first row only"; D3 "belongs to that row only" | `test_leaves_the_session_off_the_row_its_name_matches__when_an_earlier_row_claims_it_by_ticket` |
| 023-U2-B5.3 | R5 | rows reversed: U1 `` `sample-001-first-rerun` ``, U2 `` `sample-001-first` ``; the same session | `--once <out>` | U2's plan state links `001`; U1's does not | D3 "the name rules apply to the sessions no row claimed by ticket"; hotspot D3 "the ticket pass must run over every row before any name pass". Q6 settled | `test_claims_the_session_for_the_later_row_its_ticket_names__and_not_the_earlier_row_its_name_matches` |
| 023-U2-B5.4 | R5 | rows U1 and U2 both `` `sample-001-first` ``; Detailed TODO lists **U2** before **U1**; dir `sample-001-first-rerun`, `ticket: "sample-001-first"` | `--once <out>` | U1's plan state links `001`; U2's does not | BRIEF Decision authority, the Lead's answer to two rows with one Unit cell: "the first row in table order claims it". Added at U2 gate F1 | `test_claims_the_session_for_the_first_row_in_table_order__when_two_rows_share_its_ticket_and_the_todo_lists_the_later_first` |
| 023-U2-B6.1 | R7 | `review_guide_dir: "guides"`; brief at `sample/guides/sample-001-first-owner-brief.md` | `--once <out>` | SLUG's card present; `Waiting on the Lead's owner brief` on no page | BRIEF check (6): "released"; D4 (`lead_stage`) | `test_releases_the_session__when_its_owner_brief_is_under_launch_jsons_review_guide_dir` |
| 023-U2-B6.2 | R7 | as B6.1 | `--once <out>` | SLUG's card shows `1 ask` and `ASK_EXPORT` | BRIEF check (6): "the ask shown"; D4 (the Decide-now read). Assumed Q7 | `test_shows_the_briefs_ask_on_the_card__when_the_brief_is_under_launch_jsons_review_guide_dir` |
| 023-U2-B6.3 | R7 | `review_guide_dir: "guides"`; the brief at `sample/reviews/…` only | `--once <out>` | `Waiting on the Lead's owner brief` on a page | BRIEF check (6): "the same file under `reviews/` only — held" | `test_holds_the_session__when_its_owner_brief_is_only_under_reviews_and_launch_json_names_another_dir` |
| 023-U2-B6.4 | R7 | as B6.3 | `--once <out>` | SLUG's card present, with no asks line | D4 (the Decide-now read); U2-R5.4 "no owner brief, no asks line". Q8 settled | `test_shows_no_asks_line__when_the_owner_brief_is_only_under_reviews_and_launch_json_names_another_dir` |
| 023-U2-B7.1 | R8 | no `review_guide_dir` key | `--once <out>` | R5.1–R5.5 and U2-R5.1–R5.4 as at `89d726c` | BRIEF check (7): "`reviews`; R5.1–R5.5 unchanged"; D4 "R5.1–R5.5 stay green with no test edited". **Declared guard** (Q10) | R5.1–R5.5 (`OwnerBriefHold`), U2-R5.1–R5.4 (`OwnerBriefAsks`) |
| 023-U2-B7.2 | R8 | `review_guide_dir: ""`; brief at `sample/reviews/…` | `--once <out>` | SLUG's card present; `Waiting on the Lead's owner brief` on no page | D4: `CONFIG.get("review_guide_dir") or "reviews"`. Q9 settled | `test_releases_the_session_by_its_brief_under_reviews__when_review_guide_dir_is_empty` |
| 023-U2-B8.1 | R6 | default plan (`U1 \| first`); SLUG with `ticket: null` | `--once <out>` | U1's plan state links `001` | BRIEF check (8): "`ticket` null — the name rule, as today"; D3 | `test_claims_the_session_by_its_directory_name__when_run_json_ticket_is_null` |
| 023-U2-B8.2 | R6 | default plan; SLUG with `ticket: "sample-001-first"` (no row's cell) | `--once <out>` | U1's plan state links `001` | D3 "the name rules apply to the sessions no row claimed by ticket". Q11 settled | `test_claims_the_session_by_its_directory_name__when_run_json_ticket_matches_no_unit_cell` |

B1 has two tests because a page run and a summary run are two Whens. B5 and B6 each split by kill signature. B5.1
falls to (c) and B5.2 to (d). B6.1/B6.3 rest on the hold site, and B6.2/B6.4 on the Decide-now site.

## prepub-3 · Hostile input: folder names, the Host header, bad numbers

From the build's bound: every dynamic value written into HTML is escaped for its context, and an href built from a
folder name is URL-quoted, then HTML-escaped; the `/p/<name>` lookup stays an exact match; the server answers only a
`Host` of `127.0.0.1` or `localhost` with its own port, 403 otherwise; a non-numeric `max_wall_hours` "or similar
field" never crashes a render, and the row shows the value as absent. Assertions are on escaping and status codes; no
fixture carries a working script.

Q1 — "similar field"? → Assumed: the run.json numbers the render compares or divides, `max_wall_hours` and
`max_gate_attempts`. `gate_attempts` is held to the same check.
Q2 — "shows the value as absent" for `max_gate_attempts`? → Settled by: the render of an absent key at `9a127e5`,
`round <n> of ?`.
Q3 — A Host with no port, or another port? → Settled by: the bound, "with its own port". Both are 403.
Q4 — NaN, Infinity, an integer past a float's range? → Assumed: absent, as a non-number is. Python's `json` reads all
three. A negative number stays a number and renders as written.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| prepub-3-H1.1 | escape | project `x" data-injected="live` with a stopped session and an implementing one; project `y" data-injected="quiet` with none | `--once <out>` | no element on any page carries a `data-injected` attribute | bound 1, "escaped for its context" | `test_writes_no_attribute_of_the_folder_names_own__when_a_project_folder_name_carries_a_quote` |
| prepub-3-H1.2 | escape | as H1.1 | `--once <out>` | the index's hrefs include `<quoted>.html`, its `#s-<slug>` for both sessions, and the quiet project's | bound 1, "URL-quoted, then HTML-escaped" | `test_links_each_project_by_its_url_quoted_folder_name__when_the_name_carries_a_quote` |
| prepub-3-H1.3 | escape, lookup | as H1.1 | `--serve`; GET `/`, then the link `/p/<quoted>` | the index links `/p/<quoted>`; that GET is 200 and carries the stopped session's card | bound 1, "the `/p/<name>` lookup stays an exact match" | `test_serves_the_project_page_its_index_link_names__when_the_folder_name_carries_a_quote` |
| prepub-3-H1.4 | escape | project `sample`; SLUG's dir with no `run.json`; a busy live agent `planner-sample-001-first` whose status is `<b data-injected="status">busy` | `--once <out>` | the index carries `&lt;b`, and no element a `data-injected` attribute | bound 1, "every dynamic value"; review 1 finding 3 (`planner_line`) | `test_writes_no_element_of_the_planners_own__when_its_registry_status_carries_markup` |
| prepub-3-H2.1 | host | project `sample` | `--serve`; GET `/` with Host `attacker.example:<port>`, `attacker.example`, `localhost:<port+1>`, `127.0.0.1:<port+1>` | 403 each | bound 2, "anything else gets 403". Q3 settled | `test_refuses_the_request__when_its_host_is_not_loopback_with_the_dashboards_port` |
| prepub-3-H2.2 | host | as H2.1 | GET `/` with Host `127.0.0.1:<port>`, `localhost:<port>`, `LOCALHOST:<port>` | 200 each | bound 2, "the loopback address or `localhost` with its own port"; host names are case-insensitive | `test_serves_the_request__when_its_host_is_loopback_or_localhost_with_the_dashboards_port` |
| prepub-3-H3.1 | numbers | SLUG implementing, `max_wall_hours: "eight"` | `--once <out>` | exit 0; SLUG's card on `sample.html`, without `eight` | bound 3, "never crashes … shows the value as absent" | `test_renders_the_session_without_a_wall_meter__when_max_wall_hours_is_not_a_number` |
| prepub-3-H3.3 | numbers | SLUG implementing, `max_wall_hours` NaN, then Infinity, then `10**400` | `--once <out>` | exit 0; SLUG's card on `sample.html`, with no wall meter | bound 3, "shows the value as absent"; review 1 findings 1 and 2. Assumed Q4 | `test_renders_the_session_without_a_wall_meter__when_max_wall_hours_is_not_finite_or_overflows_a_float` |
| prepub-3-H3.4 | numbers | SLUG implementing, `max_wall_hours: true` | `--once <out>` | exit 0; SLUG's card on `sample.html`, with no wall meter | bound 3, "non-numeric … shows the value as absent": JSON `true` is not a number, though Python counts it an `int`; review 2 finding 2 | `test_renders_the_session_without_a_wall_meter__when_max_wall_hours_is_a_boolean` |
| prepub-3-H3.2 | numbers | SLUG implementing, U1 held at `gate_attempts: 1`, `max_gate_attempts: "three"` | `--once <out>` | exit 0; a page reads `round 1 of ?` | bound 3. Assumed Q1; Q2 settled | `test_renders_the_held_unit_with_an_absent_limit__when_max_gate_attempts_is_not_a_number` |

## dash-brand · the robot mark, a brass token, a favicon, a lowercase wordmark

From the Tier 1 brand brief (`briefings/dash-brand-tier1.md`, bounds 1–5): the header draws U26's robot mark from
`assets/logo-mark-*.svg` in place of the ◣ triangle, line work in `currentColor` and the braces and antenna cursor in
`var(--brass)`; every theme defines `--brass`; each page carries the same mark as an inline `data:image/svg+xml` icon in
Whiteprint's fixed colours on a transparent ground; the wordmark reads `robowright` in `.mono`'s font stack; the
page title stays `Robowright`. Expected colours and geometry are read from `assets/logo-mark-light.svg`, the art's
Whiteprint file, so a redrawn mark that drifts from the art reddens.

Q1 — Night's brass? → Settled by: the bound, `#F2C14E` unless it fails contrast against Night's `bg`. It is 10.84:1
against `#0B1624` (WCAG relative luminance), past 3:1 for graphics and 4.5:1 for text, so it stays.
Q2 — The ring's fill in the header? → Assumed: none. The art fills it with the theme's `bg`; the header sits on the
page's own background, and the bound gives the favicon a transparent ground.

Fixture: launch.json naming both roots; project `sample` with SLUG implementing; `--once <out>`. "Every page" is
`index.html` and `sample.html`.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| dash-brand-B1.1 | brass | the fixture | `--once <out>` | `:root[data-theme=whiteprint]` declares `--brass:#A87300`; `blueprint` and `night` `--brass:#F2C14E` | bound 2; the art's accent row (U26 ART-DIRECTION). Q1 settled | `test_defines_the_arts_brass_in_every_theme__when_a_page_is_written` |
| dash-brand-B2.1 | mark | the fixture | `--once <out>` | each page's header `<svg>` is `aria-hidden`, and draws every element of the art's mark with the art's line colour as `currentColor` and its brass as `var(--brass)` | bound 1; `assets/logo-mark-light.svg`. Q2 assumed | `test_draws_the_arts_robot_mark_in_the_header__on_every_page` |
| dash-brand-B2.2 | mark | the fixture | `--once <out>` | the triangle's path `M2 2v12h12L2 2Z…` is on no page | bound 1, "replaces the ◣ triangle" | `test_carries_no_triangle_mark__on_any_page` |
| dash-brand-B3.1 | favicon | the fixture | `--once <out>` | each page's `<head>` has one `<link rel="icon">` whose href starts `data:image/svg+xml,` | bound 3, "inline … no file, and no request" | `test_links_an_inline_svg_favicon__on_every_page` |
| dash-brand-B3.2 | favicon | the fixture | `--once <out>` | the decoded favicon draws every element of the art's mark in the art's own colours, its ring unfilled | bound 3, "Whiteprint's line and brass on a transparent ground" | `test_paints_the_favicon_in_whiteprints_line_and_brass_on_a_transparent_ground__on_every_page` |
| dash-brand-B4.1 | wordmark | the fixture | `--once <out>` | the text of each page's `.brand` is `robowright` | bound 4 | `test_reads_the_wordmark_in_lowercase__on_every_page` |
| dash-brand-B4.2 | wordmark | the fixture | `--once <out>` | the stylesheet sets `.brand`'s `font-family` to `.mono`'s | bound 4, "in `.mono`'s stack" | `test_sets_the_wordmark_in_the_mono_font_stack__in_the_stylesheet` |
| dash-brand-B5.1 | unchanged | the fixture | `--once <out>` | the index's `<title>` is `Robowright` | bound 5, "the page title text (`Robowright`)" | `test_keeps_the_index_title_capitalised__when_the_wordmark_is_lowercase` |

## 029-U1 · figures and row glyphs: the `note-brass` token, the art tokenised, the figure for a session's state

From the crew brief's U1 row (rules 1–8), its decisions D4, D6, D8, D9, D10 and D15, and the U29 design spec §2.1, §2.3
and §2.5. A glyph above every session row in Needs attention and In flight draws one figure, chosen from observable state
only, from the clone's own `assets/`: a robot from `assets/roles/<role>-light.svg`'s inner group, the Owner from the
hero's `<g transform="translate(84 600)">` group up to its bulb. Every expected figure, shape and colour is read from
those files in the test, never copied, so a glyph that drifts from the art reddens. Rows 9.x pin D10's row proportions,
which the brief settles but does not list among U1's acceptance checks.

The figure rule, in order, first match wins: a STOP file, or tone `stopped` / `unknown` / `owner-call` → Owner; tone
`briefed` → Lead; `rotating` → Lead; `intake` (a finished direct build included) → Lead; `briefing` or `rebriefing` →
Planner; `kind` `direct` with tone `working` → Worker; `working` in phase `end-of-stack` → Reviewer; any other
`working` → Worker. A figure is identified by the art paths no other figure draws (Reader and Explainer included, so
neither may appear).

Q1 — Does a row drawn without a figure (its art missing or unreadable), or the "Ready to land" row, carry class `g`? →
Assumed: no. Spec §2.5 derives `.row.g>.dot{margin-top:43px}` from "the 36 px glyph block", which a bare row lacks.
Q2 — Is the Owner's hat-dome stroke scaled × 2.3 with the rest? → Assumed: yes. D10 and §2.3 say "strokes × 2.3" and
"All strokes are the hero's", naming no exception; D15 makes the spec's numbers the bound over the design mock, which
leaves the dome at 3.
Q3 — Is a directory standing where an art file should be "unreadable"? → Assumed: yes, and it degrades as a missing
file does (D8, "a missing or unreadable file degrades").
Q4 — Rule 7's "no character from it": every SVG holds `"`, so the literal reading cannot hold. → Assumed: no character
sequence from the hostile values: the project name raw, `e()`-escaped and URL-quoted, `data-injected`, and the slug.
Q5 — `.srow .gl{…height:30px;margin:0 0 4px;--fig-fill:none}`: what does the brief's `…` stand for? → Assumed: §2.5's
whole declaration, `display:flex;align-items:flex-end;` before it.
Q6 — How exact are the stroke widths? → Assumed: to one decimal place. D15 makes rendering maths within 1 px the
Worker's own; one decimal still tells × 1.2 from × 0.945 or × 1.
Q7 — Does a glyph keep the art's shapes as written (each shape's `d`, `x`, `y`, `cx`, `cy`, `r`, its own fill and
stroke, its own group transforms)? → Assumed: yes. D10, "the role glyph's inner group is reused", "Geometry is never
redrawn". A paint may be an attribute or a `style` declaration.
Q8 — With `hero-light.svg` gone, does the Owner's row lose its figure? → Settled by: D8, "a missing or unreadable file
degrades: no figure on that row or member".

Fixture: launch.json naming both roots; project `sample` with U1 `first` unless the row names the hostile world; the
sessions the row names; `--once <out>`, exit 0 with no `Traceback` on stderr. A session's row is the index's `<a>`
linking `<project>.html#s-<slug>`. "The glyph" is the `<svg>` inside `<span class="gl" aria-hidden="true">`, the first
child of that row's `.main`. The five-figure world: SLUG stopped, SECOND briefed, `sample-003-third` briefing,
`sample-004-fourth` in phase `end-of-stack`, `sample-005-fifth` implementing.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 029-U1.1.1 | note-brass | SLUG implementing | `--once <out>` | `:root[data-theme=…]` declares `--note-brass` `#A87300` (whiteprint), `#A87300` (blueprint), `#F2C14E` (night) | brief U1 rule (1); Language, "`--note-brass` … `#A87300`, `#A87300`, `#F2C14E`"; spec §2.1 | `test_declares_note_brass_per_theme__when_a_page_is_written` |
| 029-U1.1.2 | note-brass | as 1.1 | `--once <out>` | the stylesheet holds `#attention .list{--brass:var(--note-brass)}` | brief U1 rule (1); D7 | `test_remaps_brass_to_note_brass_on_the_needs_attention_paper__in_the_stylesheet` |
| 029-U1.1.3 | note-brass | as 1.1 | `--once <out>` | each theme's custom properties are the base's 26 keys plus `note-brass` | brief U1 rule (1), "`THEMES` has no other new key"; key list: pre-change behavior at b02d51f | `test_adds_only_note_brass_to_each_themes_keys__when_a_page_is_written` |
| 029-U1.2.1 | figure | SLUG implementing, a `STOP` file in its folder | `--once <out>` | SLUG's row opens with an `aria-hidden="true" focusable="false"` glyph drawing the Owner | brief U1 rule (2), "`has_stop_file` … → Owner"; hotspot, "`has_stop_file` wins over a `working` tone" | `test_draws_the_owner_above_the_row__when_a_working_session_has_a_stop_file` |
| 029-U1.2.2 | figure | SLUG stopped, `verification-failed` | `--once <out>` | the Owner | rule (2), "tone `stopped` … → Owner" | `test_draws_the_owner_above_the_row__when_the_session_stopped` |
| 029-U1.2.3 | figure | SLUG's run.json is `{` (tone `unknown`) | `--once <out>` | the Owner | rule (2), "`unknown` … → Owner" | `test_draws_the_owner_above_the_row__when_run_json_is_unreadable` |
| 029-U1.2.4 | figure | SLUG rotating for a rebrief whose last verdict is `owner` (tone `owner-call`) | `--once <out>` | the Owner | rule (2), "`owner-call` → Owner" | `test_draws_the_owner_above_the_row__when_a_rebrief_needs_the_owners_call` |
| 029-U1.2.5 | figure | SLUG phase `briefed` | `--once <out>` | the Lead | rule (2), "tone `briefed` → Lead"; D4; hotspot, "`briefed` before the rest of `needs_you`" | `test_draws_the_lead_above_the_row__when_the_session_is_briefed` |
| 029-U1.2.6 | figure | SLUG with a rotate requested, reason `context` | `--once <out>` | the Lead | rule (2), "tone `rotating` → Lead" | `test_draws_the_lead_above_the_row__when_the_session_is_rotating` |
| 029-U1.2.7 | figure | SLUG phase `done`, no INTAKE.md, worktree not in main (tone `intake`) | `--once <out>` | the Lead | rule (2), "tone `intake` … → Lead" | `test_draws_the_lead_above_the_row__when_a_finished_session_waits_on_the_leads_intake` |
| 029-U1.2.8 | figure | SLUG a direct build: `prs/sample-001-first.md`, its Worker idle in a worktree not in main (tone `intake`, stage `check`) | `--once <out>` | the Lead | rule (2), "a finished direct build included: `lead_stage` `check`"; hotspot, "`intake` before `kind` `direct`" | `test_draws_the_lead_above_the_row__when_a_finished_direct_build_waits_on_the_leads_check` |
| 029-U1.2.9 | figure | SLUG's folder with no run.json; `planner-sample-001-first` busy (tone `briefing`) | `--once <out>` | the Planner | rule (2), "`briefing` … → Planner"; D4 | `test_draws_the_planner_above_the_row__when_a_brief_is_being_written` |
| 029-U1.2.10 | figure | SLUG stopped; `planner-sample-001-first-r1` busy (tone `rebriefing`) | `--once <out>` | the Planner | rule (2), "`rebriefing` → Planner"; hotspot, "`load_session` flips `stopped` to `rebriefing` … must reach the figure rule after the flip" | `test_draws_the_planner_above_the_row__when_a_stopped_session_has_a_busy_planner` |
| 029-U1.2.11 | figure | no session folder; `worker-sample-001-first` busy (a running direct build) | `--once <out>` | a Worker | rule (2), "`kind` `direct` with tone `working` → Worker"; D4 | `test_draws_a_worker_above_the_row__when_a_direct_build_is_running` |
| 029-U1.2.12 | figure | SLUG phase `end-of-stack` | `--once <out>` | the Reviewer | rule (2), "tone `working` with `phase` `end-of-stack` → Reviewer" | `test_draws_the_reviewer_above_the_row__when_the_session_is_in_its_end_of_stack_review` |
| 029-U1.2.13 | figure | SLUG implementing | `--once <out>` | a Worker | rule (2), "every other `working` → Worker" | `test_draws_a_worker_above_the_row__when_the_session_is_implementing` |
| 029-U1.2.14 | figure | SLUG done and through intake; `worker-opus-sample-001-first-polish` busy (tone `working`) | `--once <out>` | a Worker | rule (2), "every other `working` → Worker"; hotspot, "`done` to `working` on a follow-up" | `test_draws_a_worker_above_the_row__when_a_finished_session_has_a_busy_follow_up_pass` |
| 029-U1.3.1 | row Owner | SLUG stopped | `--once <out>` | the Owner glyph has no `<circle` of `r="2.4"` or `r="2.6"`, no `M-5 -106Q`, no `M-6 -92L` | brief U1 rule (3); spec §2.5, "Drop the eyes, smile and collar" | `test_draws_the_row_owner_without_eyes_smile_or_collar__when_the_session_stopped` |
| 029-U1.3.2 | row Owner | SLUG stopped | `--once <out>` | the Owner glyph draws none of the hero's bulb shapes (from `M0 -132V-122` on) | D3, "Owner figures (crew and row) have no light bulb"; spec §2.3, "the bulb removed (everything from `M0 -132V-122` on)" | `test_draws_the_row_owner_without_the_light_bulb__when_the_session_stopped` |
| 029-U1.4.1 | no column | SLUG stopped | `--once <out>` | its Needs attention row's `<a>` is classed `row srow` and holds exactly one `.dot`, inside its `.st` state span | DESIGN-U33 §4.7 rule 4: the one dot sits in the state at the right end, with no second marker beside the figure | `test_keeps_the_rows_one_dot_in_its_state__when_a_needs_attention_row_carries_a_glyph` |
| 029-U1.4.2 | no column | SLUG implementing | `--once <out>` | its In flight row's `<a>` is classed `row srow` and holds exactly one `.dot`, inside its `.st` state span | as 4.1 | `test_keeps_the_rows_one_dot_in_its_state__when_an_in_flight_row_carries_a_glyph` |
| 029-U1.4.3 | no column | SLUG stopped, SECOND implementing | `--once <out>` | each row's `.main` is the glyph span then `<div class="head"><span class="name mono">`; its first text is `001-first` / `002-second` | rule (4), "`.name` is still the first text of `.main`"; D2; spec §2.5, "first child of `.main`, before `.name`" | `test_puts_the_name_right_after_the_glyph_and_first_in_text__in_both_lists` |
| 029-U1.4.4 | no column | SLUG done and through intake (U1 "Awaiting acceptance"); SECOND stopped | `--once <out>` | SECOND's row has its glyph; the `sample.html#plan` row reads "Awaiting acceptance" and has no `.gl` and no class `g` | rule (4), "the "Ready to land" row … carr[ies] no `.gl`"; Assumed Q1 for `g` | `test_draws_no_glyph_on_the_awaiting_acceptance_row__beside_a_session_row_that_has_one` |
| 029-U1.4.5 (reversed by U31) | no column | SLUG implementing, SECOND stopped | `--once <out>` | SLUG's index row has its glyph; on `sample.html` no `.row` carries `g`, and the only two `.gl`s each open a `<summary>`. Until U31: `sample.html` has no element of class `gl` or `g` | rule (4), "every row on a project page … carr[ies] no `.gl`"; hotspot, "`.plan-wave .row` … carries no `.g`" (`.plan-stage` since U37); reversed for the session cards by U31 (Owner 2026-10-14, DESIGN-U31 "The delta"), rows 031-P1.1–P5.1 | `test_draws_no_glyph_on_the_project_pages_rows__only_on_its_session_cards` |
| 029-U1.5.1 | tokenised | the five-figure world | `--once <out>` | no glyph holds `#12325A`, `#A87300`, `#F4F7FA` (any case), `<title`, `role=` or `aria-label=` | brief U1 rule (5) | `test_writes_no_art_colour_and_no_accessible_name__in_any_row_glyph` |
| 029-U1.5.2 | tokenised | the five-figure world | `--once <out>` | each robot glyph draws exactly its art's inner-group shapes, each painted as the art with `#12325A` → `currentColor`, `#A87300` → `var(--brass)` | rule (5), "brass is `var(--brass)` and line work `currentColor`"; D9; D10. Assumed Q7 | `test_paints_each_robot_shape_in_current_color_and_brass__as_its_art_inks_it` |
| 029-U1.5.3 | tokenised | the five-figure world | `--once <out>` | the Owner glyph draws exactly the hero group's shapes before the bulb less face and collar, `#F4F7FA` fills → `var(--fig-fill)`, line → `currentColor`, hat → `var(--brass)` | D9, "in the Owner figure the body/arm/head fills become `var(--fig-fill)`"; spec §2.5, "Keep the hat in brass". Assumed Q7 | `test_paints_the_row_owner_in_current_color_brass_and_the_figure_fill__as_the_hero_inks_it` |
| 029-U1.6.1 | missing art | SLUG implementing, SECOND briefed; run from a scratch clone copy without `roles/worker-light.svg` | `--once <out>` | exit 0, no traceback; SLUG's row bare (`.main` opens with the head's `.name`, no `.gl`, no `g`); SECOND's draws the Lead | brief U1 rule (6); D8, "no figure on that row or member". Assumed Q1 | `test_draws_no_figure_on_the_row_whose_role_art_is_missing__and_still_draws_the_others` |
| 029-U1.6.2 | missing art | SLUG stopped, SECOND implementing; the copy without `hero-light.svg` | `--once <out>` | exit 0, no traceback; SLUG's row bare; SECOND's draws a Worker | D8. Q8 settled; Assumed Q1 | `test_draws_no_owner_on_the_row__when_the_hero_art_is_missing` |
| 029-U1.6.3 | missing art | as 6.1, with a directory where `roles/worker-light.svg` should be | `--once <out>` | as 6.1 | D8, "a missing or unreadable file degrades". Assumed Q1, Q3 | `test_draws_no_figure_on_the_row__when_its_role_art_cannot_be_read` |
| 029-U1.7.1 | hostile | project `x" data-injected="live` holding SLUG stopped and SECOND implementing; project `y" data-injected="quiet` | `--once <out>` | neither row's glyph holds the name raw, `e()`-escaped or URL-quoted, `data-injected`, or the slug | brief U1 rule (7), "the glyph markup contains no character from it". Assumed Q4 | `test_carries_nothing_of_a_hostile_name_or_slug__in_either_rows_glyph` |
| 029-U1.7.2 | hostile | as 7.1 | `--once <out>` | each row links `<URL-quoted name>.html#s-<slug>`, its `.main`'s first text is the slug, and no attribute in it is `data-injected` | rule (7), "reaches the row only through `e()`/`anchor()` exactly as at base"; pre-change behavior at b02d51f (prepub-3-H1.1, H1.2) | `test_escapes_the_hostile_rows_as_at_base__when_they_carry_glyphs` |
| 029-U1.8.1 | CSS | SLUG implementing | `--once <out>` | the stylesheet holds `.srow .gl{display:flex;align-items:flex-end;height:30px;margin:0 0 4px;--fig-fill:none}` and `.srow .head{display:flex;align-items:baseline;gap:14px}` | DESIGN-U33 §4.6, §4.7 rule 2. Assumed Q5 | `test_aligns_a_glyph_row_with_the_specs_rules__in_the_stylesheet` |
| 029-U1.8.2 | CSS | as 8.1 | `--once <out>` | dropped by U33 (§4.6: flight rows carry no left dot; 029-U1.4.2's one-dot check guards it) | rule (8), "unchanged"; pre-change behavior at b02d51f | — |
| 029-U1.9.1 | proportions | the five-figure world | `--once <out>` | each robot glyph's viewBox is `-50 -54 154 100`; the Owner's `-26 -137 64 135.1` | D10, "viewBoxes … `-26 -137 64 135.1` (Owner), … `-50 -54 154 100` (row robot)" | `test_frames_each_row_glyph_in_its_specs_view_box` |
| 029-U1.9.2 | proportions | the five-figure world | `--once <out>` | stroke widths in art order, to one decimal: Worker 6.0 6.0 8.4 8.4 8.5 6.9; Lead 6.0 6.0 8.4 8.4 5.3 4.0; Planner 6.0 6.0 8.4 8.4 5.3 5.3 4.0; Reviewer 6.0 6.0 8.4 8.4 5.3 5.3 5.3 5.3 | D10, "head 6.0, braces 8.4, prop × 1.2": 7.11 × 1.2 = 8.53, 5.78 × 1.2 = 6.93, 4.44 × 1.2 = 5.33, 3.33 × 1.2 = 4.0. Assumed Q6 | `test_strokes_each_row_robot_at_the_row_weights__head_braces_and_props_as_the_spec_sets_them` |
| 029-U1.9.3 | proportions | the five-figure world | `--once <out>` | the Owner's stroke widths, to one decimal: 7.4 7.4 6.4 7.4 6.9 7.8 | D10, "× 2.3": legs 3.2, body 3.2, arm 2.8, head 3.2, hat dome 3, brim 3.4 → 7.36, 7.36, 6.44, 7.36, 6.9, 7.82. Assumed Q2, Q6 | `test_strokes_the_row_owner_at_the_heros_weights_scaled_for_thirty_pixels` |
| 029-U1.9.4 | proportions | the five-figure world | `--once <out>` | a robot glyph's only group transform is its prop's `translate(50 10) scale(1.35) translate(-50 -10)`; the Owner's only one is the arm's `rotate(-28 26 -62)` | D10, "the row glyph keeps the 1.35 prop scale"; Landmines, "Each file's outer `<g transform=…>` is dropped"; the Owner viewBox is in the group's own units. Assumed Q7 | `test_keeps_only_the_arts_inner_transforms__in_each_row_glyph` |

## 029-U2 · the crew card and the quiet state: "On site · N", the doing phrase, the caps and their ghosts, the dozing Worker

From the crew brief's U2 row (rules 1–11) and U1 rule 3's second half, its decisions D4, D5, D6, D8, D9, D10 and D15,
and the U29 design spec §2.2–2.4, §2.6 and §2.10. The `<section class="site">` between the plan-usage line and Needs
attention holds one member per session on site:
- **on site**: `session_bucket` `attention` or `working`;
- **order**: Owner calls, then ready to launch, then running sessions newest first;
- **cap**: six members, with a `+K more` ghost per cap exceeded;
- **N = 0**: the dozing Worker.

A member's doing phrase is a fixed string chosen by observable state, and `working` for any state the table does not
name. Figures are checked against the art files, as U1's glyphs are. Rows 12.6–12.9 pin D10's crew proportions, which
the brief settles but does not list among U2's acceptance checks.

Q1 — Is the "session" in the `title`'s `project · session · doing` the full slug or the `.who` text? → Assumed: the `.who` text (the slug less `<project>-`). Spec §2.3 uses the one word `session` for both the title and `.who`, and the mock writes `notes-app · 004-search · your call`. Row 4.3.
Q2 — What does a member say when its current unit is `todo` or carries a status the table does not name? → Settled by: D6, "a state the table does not name gets the Worker figure and the fixed phrase `working`, never a session file's text". Row 5.19.
Q3 — Rule 6 gives N = 0 "min(N, 6) `li` members", but the mock's quiet card puts its `div.member` in an `li`. → Assumed: rule 6 counts `a.member` links and ghosts; the quiet card's unlinked `div` is rule 7's. Row 6.1.
Q4 — The brief says the ghost's "stage `aria-hidden`", spec §2.4 says the ghost placeholder is `aria-hidden`, and the mock marks neither. → Assumed: `+K` sits inside an element with `aria-hidden="true"` on the stage (the stage or the ghost span), and nothing on the stage is spoken; the link's accessible name is its labels. Row 6.8.
Q5 — Where do the ghosts sit? → Assumed: after the six members, per spec §2.4, "render members 1–6 … Then render one overflow `li.more`". Their order among themselves is not pinned. Row 3.3.
Q6 — Rule 9's "`<script` from the fixture": `given_hostile_projects` carries no `<script`, and `.claude/rules/tests.md` forbids committing a working payload. → Assumed: the hostile slug and unit id carry inert markup syntax, `<x data-injected="…">` (an element nothing defines, with the hostile world's inert attribute). The card must hold no `x` element, no `data-injected` attribute and no `<script`, and the raw slug must be nowhere on the index. `HOSTILE_SLUG` and `HOSTILE_UNIT_ID` carry the markup syntax; `given_hostile_projects` supplies the rest of the world. Rows 9.2, 9.3.
Q7 — Which selectors carry the CSS? The brief writes `li{flex:0 1 136px}`, `.labels{…}`, `.who` and the rest without a parent. → Assumed:
  - `.crew li`, `.crew li.owner`, `.crew li.more`, `.crew-card` and `.crew-card::before` exactly. The 640 px query's own `.crew li{flex-basis:118px}` and `.crew li.owner{flex-basis:104px}` must override them at equal specificity, and the mock writes them so.
  - The label rules are found by their last compound: `.labels`; `.who`, `.what` or `.where`; or a `span` or `*` child of `.labels`, whatever precedes it.
  - The hover rule is any `.member:hover … .who`.

  Rows 11.3–11.6, 11.8.
Q8 — Is the crew Owner's hat-dome stroke × 1.2 with the rest? → Assumed: yes, as U1's Q2 took × 2.3. Spec §2.3 says "All strokes are the hero's × 1.2" and D15 makes the spec the bound; the mock leaves the dome at 3. If the mock wins, row 12.8's seventh value becomes 3.0. Row 12.8.
Q9 — How exact are the crew strokes? → Assumed: within 0.06 units each. 3.33 × 0.945 = 3.15 sits on a rounding edge, so one decimal, as U1 used, would test the implementation's rounding instead of the rule. D15 gives rendering maths within 1 px to the Worker, and 0.06 units is under 0.04 px at 52 px. Rows 7.3, 12.7, 12.8.
Q10 — Does a member whose art is missing lose the figure, or the member? → Assumed: the member stays, its labels intact and its `.stage` present and empty, per D8, "no figure on that row or member". The stage keeps the labels on the ground line. The quiet card keeps its line. Rows 13.1, 13.2.
Q11 — How is the ground written? → Assumed:
  - `content:""` on `.crew-card::before`: a pseudo-element with no `content` is not generated, so the ground would not exist.
  - The spec's gradient as `background` or `background-image`, with the spaces after its commas not significant.
  - `left:0`, `right:0`.

  Row 11.2.
Q12 — Spec §2.3 says `.what` and `.where` are in "the page sans". How is that checked? → Assumed: their rules declare no monospace font-family, so they keep the page's font. Row 11.6.
Q13 — What does "byte-identical to base's" compare against? → Settled by: the rule itself. The expected body is the one the base `do_GET` serves for the same world, written into the test as a literal (pre-change behaviour at b02d51f). Row 10.1.

Fixture: launch.json names both roots; project `sample` with U1 `first` unless the row names another; the sessions the row
names; `--once <out>`, exit 0 with no `Traceback` on stderr. Terms the rows use:
- **The card**: the index's `<section class="site" aria-labelledby="site-h">`.
- **A member**: an `li` holding `<a class="member">`, found by its href, `<project>.html#s-<slug>`.
- **A ghost**: an `li.more`.
- **"N minutes ago"**: the session's run.json mtime, its most recent activity.
- **SLUG, SECOND**: `sample-001-first` and `sample-002-second`.
- **The caps world of N**: the first N of `sample-001-first` … `sample-008-eighth`, each implementing, the k-th written k minutes ago.
- **The five-figure world**: SLUG stopped, SECOND briefed, `sample-003-third` briefing, `sample-004-fourth` in `end-of-stack`, `sample-005-fifth` implementing.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 029-U2.1.1 | placement | SLUG implementing, SECOND stopped, a plan-usage reading | `--once <out>` | `<h1>Projects</h1>`, `class="note plan-usage"`, the card, `id="attention"`, `id="flight"` appear in that order | brief U2 rule (1); spec §2.2, "after the plan-usage line and before `#attention`" | `test_places_the_crew_card_after_the_plan_usage_line_and_before_both_lists__when_a_reading_is_shown` |
| 029-U2.1.2 | placement | as 1.1, no reading | `--once <out>` | the index holds `<h1>Projects</h1><section class="site" aria-labelledby="site-h">` | rule (1); `plan_usage_line()` is `""` with no reading (pre-change behavior at b02d51f) | `test_puts_the_crew_card_right_under_the_heading__when_there_is_no_plan_usage_reading` |
| 029-U2.2.1 | N | SLUG done and through intake (U1 awaiting acceptance); `sample-002-second` stopped; `sample-003-third` briefed; `sample-004-fourth` implementing; `sample-005-fifth` parked; project `other` with `other-001-first` implementing; orphan `notes-app-001-first` implementing | `--once <out>` | heading `On site · 4`; members (who, where) = (001-first, other), (002-second, sample), (003-third, sample), (004-fourth, sample) | rule (2): "`session_bucket` in (`attention`, `working`) across `projects` … "Ready to land" rows and orphan sessions are not counted"; parked → bucket `waiting`, done → `done` (`session_bucket`) | `test_counts_only_sessions_needing_attention_or_running__not_awaiting_acceptance_parked_or_orphan_ones` |
| 029-U2.2.2 | N | SLUG implementing | `--once <out>` | heading `On site · 1` | rule (2), "`On site · N` for N ≥ 1" | `test_reads_on_site_one__when_one_session_is_running` |
| 029-U2.2.3 | N | no session | `--once <out>` | heading `On site` | rule (2), "`On site` for N = 0"; spec §2.6, "The h2: "On site", with no count" | `test_reads_on_site_with_no_count__when_nothing_is_on_site` |
| 029-U2.2.4 | N | the caps world of 8 | `--once <out>` | heading `On site · 8` | Language, "N counts every session on site … the overflow included"; spec §2.2 | `test_counts_the_overflow_in_the_heading__when_eight_are_on_site` |
| 029-U2.3.1 | order | SLUG implementing (1 min), SECOND briefed (2 min), `sample-003-third` stopped (30 min), `sample-004-fourth` implementing (10 min) | `--once <out>` | who order `003-third`, `002-second`, `001-first`, `004-fourth` | rule (3), "attention sessions in `attention_rows` order … then the working sessions by … `by_recency` … newest first"; spec §2.2, "Owner calls first, then ready to launch, then running sessions by most recent activity" | `test_lists_owner_calls_then_ready_to_launch_then_running__whatever_each_last_wrote` |
| 029-U2.3.2 | order | projects `sample` and `other`, PROJECT.md 3 h old; SLUG (2 min), `sample-003-third` (20 min), `other-002-second` (10 min), all implementing | `--once <out>` | In flight lists 001, 003, then other's 002 (precondition); the crew lists (001-first, sample), (002-second, other), (003-third, sample) | rule (3), "which may differ from `render_in_flight`'s per-project order — the crew's order is its own" | `test_lists_running_sessions_newest_first_across_projects__not_in_flights_per_project_order` |
| 029-U2.3.3 | order | the caps world of 8 | `--once <out>` | members `001-first` … `006-sixth`; the card's `li`s are the six members then three ghosts | rule (3) with rule (6), "render members 1–6"; spec §2.4, "Then render one overflow `li.more`". Assumed Q5 | `test_shows_the_six_most_recently_active_then_the_ghosts__when_eight_are_on_site` |
| 029-U2.4.1 | member | SLUG implementing, U1 `building` | `--once <out>` | SLUG's member has a figure on its stage and reads `001-first` / `building U1` / `sample` | rule (4), "`.who` (slug minus the `<project>-` prefix, as the rows strip it), `.what` (doing), `.where` (project)"; rule (5), `building <id>` | `test_labels_a_member_with_its_session_doing_and_project__beside_a_figure` |
| 029-U2.4.2 | member | SLUG stopped, SECOND implementing with U1 `building` | `--once <out>` | each is an `<a>` linking `sample.html#s-<slug>`, the href its row links | rule (4), "the href equals the session's row href" | `test_links_each_member_to_its_sessions_row__in_both_lists` |
| 029-U2.4.3 | member | as 4.1 | `--once <out>` | title `sample · 001-first · building U1` | rule (4), "`title="{e(project · session · doing)}"`". Assumed Q1 | `test_titles_a_member_project_session_and_doing` |
| 029-U2.4.4 | member | as 4.2 | `--once <out>` | SLUG's `li` has class `owner`; SECOND's has not | rule (4), "`li.owner` for an Owner member"; U1's figure rule (stopped → Owner) | `test_marks_the_owners_member_owner__and_no_robots` |
| 029-U2.4.5 | member | as 4.1 | `--once <out>` | the card begins `<section class="site" aria-labelledby="site-h"><h2 id="site-h">…</h2><div class="crew-card"><ul class="crew"><li` | spec §2.2 markup; §2.9, "The crew is a real list, labelled by its h2" | `test_lists_the_crew_in_a_card_labelled_by_its_heading` |
| 029-U2.5.1 | doing | SLUG stopped | `--once <out>` | `your call` | rule (5), "`your call` (Owner rows)"; spec §2.3 table | `test_says_your_call__when_the_session_stopped` |
| 029-U2.5.2 | doing | SLUG implementing U1 `building`, a `STOP` file | `--once <out>` | `your call` | rule (5); spec §2.3, "has stop file → `your call`"; hotspot, "`has_stop_file` wins over a `working` tone" | `test_says_your_call__when_a_building_session_has_a_stop_file` |
| 029-U2.5.3 | doing | SLUG rotating for a rebrief whose last verdict is `owner` | `--once <out>` | `your call` | rule (5); spec §2.3, "tone `owner-call` … `your call`" | `test_says_your_call__when_a_rebrief_needs_the_owners_call` |
| 029-U2.5.4 | doing | SLUG's run.json is `{` | `--once <out>` | `your call` | rule (5); spec §2.3, "tone … `unknown` … `your call`" | `test_says_your_call__when_run_json_is_unreadable` |
| 029-U2.5.5 | doing | SLUG phase `briefed` | `--once <out>` | `ready to launch` | rule (5), "`ready to launch` (briefed)" | `test_says_ready_to_launch__when_the_session_is_briefed` |
| 029-U2.5.6 | doing | SLUG with a rotate requested, reason `context` | `--once <out>` | `handing off` | rule (5), "`handing off` (rotating)" | `test_says_handing_off__when_the_session_is_rotating` |
| 029-U2.5.7 | doing | SLUG phase `done`, no INTAKE.md, worktree not in main | `--once <out>` | `Lead's intake` | rule (5), "`intake` → `Lead's intake`" | `test_says_leads_intake__when_a_finished_session_has_no_intake` |
| 029-U2.5.8 | doing | SLUG a finished direct build (`prs/sample-001-first.md`, Worker idle in a worktree not in main) | `--once <out>` | `Lead's check` | rule (5), "`check` → `Lead's check`"; `check` is a direct build's stage (`lead_stage`); hotspot, "`intake` before `kind` `direct`" | `test_says_leads_check__when_a_finished_direct_build_waits_on_the_lead` |
| 029-U2.5.9 | doing | robowright.json `owner_brief: true`; SLUG done, through intake, no owner brief | `--once <out>` | `owner brief` | rule (5), "`review guide` … → `owner brief`" | `test_says_owner_brief__when_the_project_asks_for_one_and_none_is_written` |
| 029-U2.5.10 | doing | as 5.9, plus a busy `explainer-sample-001-first` | `--once <out>` | `owner brief` | rule (5), "… and `owner brief` → `owner brief`" | `test_says_owner_brief__when_an_explainer_is_writing_it` |
| 029-U2.5.11 | doing | SLUG phase `intake`, U1 `todo` | `--once <out>` | `reading the brief` | rule (5), "`reading the brief` (working, phase `intake`)" | `test_says_reading_the_brief__when_the_session_is_in_phase_intake` |
| 029-U2.5.12 | doing | SLUG implementing, U1 `building` | `--once <out>` | `building U1` | rule (5), "`building` → `building <id>`", "ids of the `U1` shape" | `test_says_building_and_the_unit__when_the_current_unit_is_building` |
| 029-U2.5.13 | doing | SLUG implementing, U1 `gated` | `--once <out>` | `closing U1` | rule (5), "`gated` → `closing <id>`" | `test_says_closing_and_the_unit__when_the_current_unit_passed_its_gate` |
| 029-U2.5.14 | doing | SLUG implementing, U1 `held`, round 1 | `--once <out>` | `review notes U1` | rule (5), "`held` → `review notes <id>`" | `test_says_review_notes_and_the_unit__when_the_current_unit_is_held` |
| 029-U2.5.15 | doing | SLUG phase `end-of-stack`, every unit done | `--once <out>` | `final review` | rule (5), "phase `end-of-stack` → `final review`" | `test_says_final_review__when_the_session_is_in_its_end_of_stack_review` |
| 029-U2.5.16 | doing | no session folder; `worker-sample-001-first` busy | `--once <out>` | `direct build` | rule (5), "`kind` `direct` → `direct build`"; D4 | `test_says_direct_build__when_a_direct_build_is_running` |
| 029-U2.5.17 | doing | SLUG's folder with no run.json; `planner-sample-001-first` busy | `--once <out>` | `writing the brief` | rule (5), "`briefing` → `writing the brief`"; D4 | `test_says_writing_the_brief__when_a_planner_is_writing_it` |
| 029-U2.5.18 | doing | SLUG stopped; `planner-sample-001-first-r1` busy | `--once <out>` | `rebriefing` | rule (5), "`rebriefing` → `rebriefing`"; hotspot, "`load_session` flips `stopped` to `rebriefing`" | `test_says_rebriefing__when_a_stopped_session_has_a_busy_planner` |
| 029-U2.5.19 | doing | SLUG implementing, U1 status `polishing-the-sample` | `--once <out>` | `working`; the member's markup holds no `polishing` | D6, "the fixed phrase `working`, never a session file's text". Q2 settled | `test_says_working_and_never_the_status__when_the_current_units_status_is_one_the_table_does_not_name` |
| 029-U2.6.1 | caps | the caps world of 0 | `--once <out>` | no member, no ghost | rule (6), "min(N, 6) `li` members … iff N > 3". Assumed Q3 | `test_shows_no_member_and_no_ghost__when_nothing_is_on_site` |
| 029-U2.6.2 | caps | the caps world of 3 | `--once <out>` | marks `[] [] []`; no ghost | rule (6), "members 4–6 carry `h3`"; "`.c3` … iff N > 3" → 3 is not | `test_shows_three_members_and_no_ghost__when_three_are_on_site` |
| 029-U2.6.3 | caps | the caps world of 4 | `--once <out>` | marks `[] [] [] [h3]`; ghosts {c3: `+1`} | rule (6): 4 > 3 → `c3` `+4−3`; 4 is not > 4 | `test_marks_the_fourth_h3_and_adds_the_narrowest_ghost__when_four_are_on_site` |
| 029-U2.6.4 | caps | the caps world of 5 | `--once <out>` | marks `[] [] [] [h3] [h3 h4]`; ghosts {c4: `+1`, c3: `+2`} | rule (6), "members 5–6 carry `h4`, 4–6 carry `h3`"; 5−4 = 1, 5−3 = 2 | `test_marks_four_and_five_and_adds_two_ghosts__when_five_are_on_site` |
| 029-U2.6.5 | caps | the caps world of 6 | `--once <out>` | marks `[] [] [] [h3] [h3 h4] [h3 h4]`; ghosts {c4: `+2`, c3: `+3`} | rule (6): 6 is not > 6; 6−4 = 2, 6−3 = 3 | `test_shows_six_members_and_two_ghosts__when_six_are_on_site` |
| 029-U2.6.6 | caps | the caps world of 7 | `--once <out>` | six members marked as 6.5; ghosts {c6: `+1`, c4: `+3`, c3: `+4`} | rule (6), "min(N, 6)"; 7−6 = 1, 7−4 = 3, 7−3 = 4 | `test_caps_at_six_members_and_adds_all_three_ghosts__when_seven_are_on_site` |
| 029-U2.6.7 | caps | the caps world of 8 | `--once <out>` | six members marked as 6.5; ghosts {c6: `+2`, c4: `+4`, c3: `+5`} | rule (6); 8−6 = 2, 8−4 = 4, 8−3 = 5 | `test_counts_each_ghost_from_its_cap__when_eight_are_on_site` |
| 029-U2.6.8 | caps | the caps world of 7 | `--once <out>` | each ghost is `<a class="member" href="#flight" title="K more on site, listed below">`; its labels are `K more` / `listed below` / empty; on its stage `+K` is aria-hidden and nothing is spoken (K = 1, 3, 4 for c6, c4, c3) | rule (6), "each ghost `<a class="member" href="#flight" title="K more on site, listed below">`, its stage `aria-hidden`, labels `K more` / `listed below` plus an empty third line". Assumed Q4 | `test_links_each_ghost_to_in_flight_with_its_count_spoken_only_in_its_labels` |
| 029-U2.6.9 | caps | SLUG implementing | `--once <out>` | the stylesheet holds `.crew .c4,.crew .c3{display:none}`, the 780 px and the 640 px `@media` rules, verbatim | rule (6), the three rules quoted verbatim, "the `.crew` prefix on every selector" | `test_shows_one_ghost_per_width__in_the_stylesheet` |
| 029-U2.7.1 | quiet | project `sample`, no session | `--once <out>` | the card has one `div.crew-card` and one `.member`, a `div`; no `<a>`; text `Quiet site. Nothing is running.` | rule (7), "one `<div class="member">` (not a link) … the text `Quiet site. Nothing is running.`"; spec §2.6, "the same card" | `test_shows_one_unlinked_member_with_the_quiet_line__when_nothing_is_on_site` |
| 029-U2.7.2 | quiet | as 7.1 | `--once <out>` | the card's one figure is aria-hidden, unfocusable, draws the Worker, ellipses (−13, 6, 7, 1.8) and (13, 6, 7, 1.8) | rule (7), "eyes `cy="6" rx="7" ry="1.8"`"; D10; spec §2.6, "each eye `ellipse` changed"; cx from `worker-light.svg` | `test_draws_the_dozing_worker_with_closed_lids__in_the_quiet_card` |
| 029-U2.7.3 | quiet | as 7.1 | `--once <out>` | its viewBox `-50 -54 136 90`, its one group transform `translate(-7 0)`, its strokes 3.5 3.5 4.9 4.9 6.72 5.46 | spec §2.6, "the crew Worker with each eye `ellipse` changed"; D10. Assumed Q9 | `test_frames_and_strokes_the_dozing_worker_as_the_crew_worker` |
| 029-U2.7.4 | quiet | as 7.1 | `--once <out>` | the page has `Quiet site. Nothing is running.` and `Nothing needs attention right now.`, and not `Nothing is running right now.` | rule (7); D5 | `test_drops_the_in_flight_note_and_keeps_the_needs_attention_note__when_the_site_is_quiet` |
| 029-U2.7.5 | quiet | SLUG done and through intake (U1 awaiting acceptance) | `--once <out>` | `#attention` links `sample.html#plan` reading `Awaiting acceptance`; heading `On site`; the quiet line; no `Nothing is running right now.` | rule (7), "a "Ready to land" unit still lists under `#attention` beside the quiet card"; D5 | `test_lists_a_awaiting_acceptance_unit_under_needs_attention__beside_the_quiet_card` |
| 029-U2.8.1 | notes | SLUG stopped | `--once <out>` | heading `On site · 1`; `Nothing is running right now.` present | rule (8), "both empty notes behave exactly as at base"; pre-change behavior at b02d51f (`render_in_flight`) | `test_keeps_the_in_flight_note__when_the_only_session_on_site_needs_attention` |
| 029-U2.8.2 | notes | SLUG implementing | `--once <out>` | heading `On site · 1`; `Nothing needs attention right now.` present | rule (8); pre-change behavior at b02d51f (`render_attention`) | `test_keeps_the_needs_attention_note__when_the_only_session_on_site_is_running` |
| 029-U2.9.1 | hostile | `given_hostile_projects`: project `x" data-injected="live` holding SLUG stopped and SECOND implementing | `--once <out>` | each member links `<quoted name>.html#s-<slug>`; its title starts `<name> · <slug>`; who = slug, where = name (unescaped); the card has no `data-injected` attribute; the raw name is not in index.html | rule (9), "appear in `title` and `href` only `e()`/`anchor()`-escaped: the raw string is absent from the page"; `.where` per rule (4); the slug is unstripped (its prefix is not `<name>-`) | `test_writes_a_hostile_project_name_into_members_only_escaped` |
| 029-U2.9.2 | hostile | as 9.1, plus `sample-003-<x data-injected="slug">` implementing under that project | `--once <out>` | its member links `<quoted name>.html#s-sample-003--x-data-injected--slug--`, which its row also links; who and the title's second part are the slug as written; the card has no `x` element, no `data-injected`, no `<script`; the raw slug is not in index.html | rule (9); `anchor()` maps each non-word, non-hyphen character to `-` (pre-change behavior at b02d51f). Assumed Q6 | `test_writes_a_hostile_slug_into_its_member_only_escaped` |
| 029-U2.9.3 | hostile | SLUG implementing a `building` unit whose id is `U9 <x data-injected="id">` | `--once <out>` | `.what` reads `building U9 <x data-injected="id">` as text; the card has no `x` element and no `data-injected` | rule (5), "the id is session text, escaped by `e()`, and may be longer"; Invariants, "a unit `id` in `building <id>` passes through `e()`". Assumed Q6 | `test_writes_a_hostile_unit_id_into_the_doing_phrase_only_escaped` |
| 029-U2.10.1 | json | SLUG done and through intake, SECOND stopped, `sample-003-third` briefed, `sample-004-fourth` implementing; served | `GET /attention.json` | 200 and exactly the base's body: SECOND's row, the briefed row, the Awaiting acceptance row (`ATTENTION_JSON`) | rule (10), "byte-identical to base's"; pre-change behavior at b02d51f (`do_GET`, `attention_rows`). Q13 settled | `test_serves_attention_json_byte_for_byte_as_before__beside_a_crew` |
| 029-U2.11.1 | CSS | SLUG implementing | `--once <out>` | `.crew-card` sets `--stage:74px`, `--hatch:color-mix(in srgb,var(--fg) 32%,var(--surface))`, `--fig-fill:var(--surface)` | rule (11); spec §2.1 (`--hatch`, `--fig-fill`), §2.2 (`--stage:74px`) | `test_sets_the_stage_height_hatch_and_figure_fill__on_the_crew_card` |
| 029-U2.11.2 | CSS | as 11.1 | `--once <out>` | `.crew-card::before`: `content:""`, `position:absolute`, `top:calc(16px + var(--stage))`, `left:0`, `right:0`, `border-top:2px solid var(--fg)`, background `repeating-linear-gradient(-45deg,transparent 0 7px,var(--hatch) 7px 8.4px)` | rule (11), "`::before` ground"; spec §2.2, Ground. Assumed Q11 | `test_draws_the_ground_line_and_hatch_under_the_stage__edge_to_edge` |
| 029-U2.11.3 | CSS | as 11.1 | `--once <out>` | `.crew li` flex `0 1 136px`, min-width `0`; `.crew li.owner` flex-basis `116px`; `.crew li.more` flex `0 0 96px` | rule (11), "`li{flex:0 1 136px}`, `li.owner{flex-basis:116px}`, `li.more{flex:0 0 96px}`"; spec §2.2, "`min-width:0`". Assumed Q7 | `test_sizes_the_member_owner_and_ghost_columns__in_the_crew_list` |
| 029-U2.11.4 | CSS | as 11.1 | `--once <out>` | `.labels` margin-top `20px` | rule (11), "`.labels{margin-top:20px}`". Assumed Q7 | `test_sets_the_labels_twenty_pixels_under_the_stage` |
| 029-U2.11.5 | CSS | as 11.1 | `--once <out>` | each of `.who`, `.what`, `.where` gets `white-space:nowrap`, `overflow:hidden`, `text-overflow:ellipsis` | rule (11), "every label line `nowrap` + ellipsis"; spec §2.3. Assumed Q7 | `test_keeps_each_label_line_to_one_line_with_an_ellipsis` |
| 029-U2.11.6 | CSS | as 11.1 | `--once <out>` | `.who` font-family `ui-monospace,"SF Mono",Menlo,monospace`, weight `500`, color `var(--fg)`; `.what`, `.where` color `var(--muted)`, no monospace | rule (11), "`.who` mono 500 `--fg`, `.what`/`.where` sans `--muted`"; spec §2.3 Type table. Assumed Q7, Q12 | `test_sets_the_session_in_mono_500_and_the_doing_and_project_in_muted_sans` |
| 029-U2.11.7 | CSS | as 11.1 | `--once <out>` | the stylesheet holds `a.member:focus-visible{outline:2px solid var(--run);outline-offset:-2px}` | rule (11), verbatim | `test_outlines_a_focused_member_in_the_run_colour` |
| 029-U2.11.8 | CSS | as 11.1 | `--once <out>` | under `.member:hover`, `.who` is underlined, in `var(--faint)`, `text-underline-offset:3px` | rule (11), "`.member:hover .who` underline `--faint` offset 3px"; spec §2.3 Hover. Assumed Q7 | `test_underlines_the_session_on_hover_in_faint_three_pixels_below` |
| 029-U2.12.1 | figure | the five-figure world | `--once <out>` | each member's stage figure is `aria-hidden="true" focusable="false"` and draws the role its row draws: Owner, Lead, Planner, Reviewer, Worker | rule (4), "`.stage` → figure"; D4, D6; Language, "figure … `aria-hidden`"; spec §2.9 | `test_stands_each_members_figure_on_its_stage__as_the_sessions_state_picks_it` |
| 029-U2.12.2 | figure | the five-figure world | `--once <out>` | the crew Owner has an `r="2.4"`/`"2.6"` circle, `M-5 -106Q`, `M-6 -92L`, and none of the bulb's shapes | brief U1 rule (3), "the crew Owner (U2) has all three"; D3, "no light bulb" | `test_draws_the_crew_owner_with_eyes_smile_and_collar__and_no_bulb` |
| 029-U2.12.3 | figure | the five-figure world | `--once <out>` | no crew figure holds `#12325A`, `#A87300`, `#F4F7FA`, `<title`, `role=` or `aria-label=` | D9; spec §2.9, "Every figure SVG is `aria-hidden`"; Invariants, "a figure … built from `assets/` with no interpolated data" | `test_writes_no_art_colour_and_no_accessible_name__in_any_crew_figure` |
| 029-U2.12.4 | figure | the five-figure world | `--once <out>` | each crew robot draws exactly its art's inner-group shapes, `#12325A` → `currentColor`, `#A87300` → `var(--brass)` | D9, D10, "the role glyph's inner group is reused"; spec §2.3, "Line work and eyes are `currentColor` … braces and cursor are `var(--brass)`" | `test_paints_each_crew_robot_shape_as_its_art_inks_it` |
| 029-U2.12.5 | figure | the five-figure world | `--once <out>` | the crew Owner draws every hero-group shape before the bulb, `#F4F7FA` → `var(--fig-fill)`, line → `currentColor`, hat → `var(--brass)` | D9, "in the Owner figure the body/arm/head fills become `var(--fig-fill)`"; spec §2.3, Owner figure | `test_paints_the_crew_owner_as_the_hero_inks_it__face_and_collar_included` |
| 029-U2.12.6 | figure | the five-figure world | `--once <out>` | robot viewBox `-50 -54 136 90`; Owner `-26 -137 64 135.1` | D10, "viewBoxes `-50 -54 136 90` (crew robot), `-26 -137 64 135.1` (Owner)"; spec §2.3 | `test_frames_each_crew_figure_in_its_specs_view_box` |
| 029-U2.12.7 | figure | the five-figure world | `--once <out>` | strokes, each within 0.06: Worker 3.5 3.5 4.9 4.9 6.72 5.46; Lead 3.5 3.5 4.9 4.9 4.2 3.15; Planner 3.5 3.5 4.9 4.9 4.2 4.2 3.15; Reviewer 3.5 3.5 4.9 4.9 4.2 4.2 4.2 4.2 | D10, "head stroke 3.5, braces 4.9, prop strokes × 0.945": 7.11 × 0.945 = 6.72, 5.78 × 0.945 = 5.46, 4.44 × 0.945 = 4.2, 3.33 × 0.945 = 3.15. Assumed Q9 | `test_strokes_each_crew_robot_at_the_crew_weights` |
| 029-U2.12.8 | figure | the five-figure world | `--once <out>` | the Owner's strokes, each within 0.06: 3.84 3.84 2.88 3.36 3.84 2.64 3.6 4.08 | D10, "the Owner is the hero group's strokes × 1.2 (crew)": legs 3.2, body 3.2, collar 2.4, arm 2.8, head 3.2, smile 2.2, hat dome 3, brim 3.4. Assumed Q8, Q9 | `test_strokes_the_crew_owner_at_the_heros_weights_times_one_point_two` |
| 029-U2.12.9 | figure | the five-figure world | `--once <out>` | a robot's only group transform is `translate(-7 0)`; the Owner's only one is `rotate(-28 26 -62)` | D10, "the crew prop transform `translate(50 10) scale(1.35) translate(-50 -10)` → `translate(-7 0)`"; Landmines, "Each file's outer `<g transform=…>` is dropped" | `test_stands_each_crew_robots_prop_on_the_ground__and_keeps_the_owners_arm_turn` |
| 029-U2.13.1 | missing art | SLUG implementing, SECOND briefed; run from a clone copy without `roles/worker-light.svg` | `--once <out>` | exit 0, no traceback; SLUG's member reads `001-first` / `sample` with a `.stage` holding no `<svg`; SECOND's draws the Lead | D8, "a missing or unreadable file degrades: no figure on that row or member". Assumed Q10 | `test_keeps_the_member_with_an_empty_stage__when_its_role_art_is_missing` |
| 029-U2.13.2 | missing art | project `sample`, no session; the same copy | `--once <out>` | exit 0; heading `On site`; the quiet line; no `<svg` in the card | D8. Assumed Q10 | `test_keeps_the_quiet_line_without_a_figure__when_the_worker_art_is_missing` |

## 029-U3 · the empty state and the footer stamp: the tokenised hero over three lines, the maker's mark in every footer

From the crew brief's U3 row (rules 1–6), its decisions D3, D8, D9, D11, D12, D14 and D15, and the U29 design spec
§2.7 and §2.8, with §1 findings 8–10 as the reasons. The hero and the stamp are checked shape for shape against
`assets/hero-light.svg` and `assets/logo-light.svg`, read in the test, with D9's inks swapped in. Rules 7 (the
screenshot pipeline and its greps) and 8 (the manual pass) are the Worker's and have no rows here.

Q1 — With a plan-usage reading and no project, does the usage line show above the hero? → Assumed: no. Rule (1) and spec §2.7 both give `main` as `<h1>Projects</h1><section class="empty">…</section>` and nothing else, and the Owner approved §2.7. If the usage line should stay, row 1.13's Then becomes `<h1>Projects</h1>`, the usage line, then the section. Row 1.13.
Q2 — Is a world with orphan sessions but no project folder the empty state? → Settled by: rule (1), "(`projects == []`, `orphans == []`)", and Language, "empty state | no projects and no orphan sessions". What that index shows instead is not pinned beyond the orphans heading. Row 1.14.
Q3 — With the logo missing, does the footer text keep its `<span>`? → Assumed: yes. D12, "the footer becomes `display:flex …` with the existing text in a `<span>`", names no condition, so the footer is `<footer id="foot"><span>Updated …</span></footer>`. Rows 5.1, 5.2.
Q4 — With the hero missing, does `<section class="empty">` stay? → Assumed: yes, holding the three lines. D8, "a text-only empty state", and rule (2), "the three lines render". Rows 2.1, 2.2.
Q5 — Does an unreadable art file degrade as a missing one does? → Settled by: D8, "a missing or unreadable file degrades: … a text-only empty state, no stamp". The fixture is U1's: a directory in the file's place. Rows 2.2, 5.2.
Q6 — May the hero's and the stamp's `<svg>` carry attributes the rules do not name (`xmlns`, `width`, `height`)? → Assumed: yes. The tests pin the attributes the rules name (`class`, `viewBox`, `aria-hidden`, `focusable`) and the absence of `role`, `aria-label` and (hero) `id`. Rule (4) writes the stamp's tag with `…`. The hero's tag is found by rule (2)'s own words, `<svg class="hero-art"`. Rows 1.5, 4.4.
Q7 — What is "every rendered page"? → Assumed: the index and the project page, both as `--once` writes them and as `--serve` answers `/` and `/p/<project>`, and the empty index. The 403 and 404 bodies are plain text, not pages. Rows 4.1–4.3.
Q8 — How much of the footer's text is pinned? → Assumed: `Updated HH:MM:SS · refreshes every 20s`, then optionally ` · ` and the page's own tail, as the whole of the `<span>`. D12, "the existing text in a `<span>`"; D14, "the 20 s refresh". Rows 4.1–4.3, 5.1, 5.2.
Q9 — Rule (1) names no CSS for the hero; is spec §2.7's sizing pinned? → Assumed: yes, because D15 makes §2's numbers the bound. The caller may drop row 1.12 whole; no other row depends on it. The three lines' type sizes and centring are left to the Owner's renders. Row 1.12.
Q10 — How is line 2 compared when its command's markup is the Worker's? → Settled by: rule (1), "the exact markup of the command is the Worker's; the text is not". The test removes tags without adding spaces, unescapes, and compares the text. Row 1.2.
Q11 — What hostile projects root? → Assumed: inert markup syntax and an ampersand in the root's last folder, `projects <x data-injected="root"> & co`, as U2's Q6 chose for slugs: an element nothing defines, with the hostile world's inert attribute. Rows 1.15, 1.16.
Q12 — What is the empty world's `/attention.json` at base? → Settled by: rule (6), "unchanged". The base `do_GET` serves `json.dumps` of the attention rows, and there are none with no project, so the body is `[]` (pre-change behaviour at b02d51f; `do_GET` still serves it). Row 6.1.
Q13 — Where is `--stamp-accent` declared? → Assumed: in any top-level rule. Every declaration of it carries rule (4)'s value; it never enters `THEMES` (Language, "tokens"). Row 4.9.
Q14 — Which selectors carry the CSS? → Assumed: any top-level rule whose selector ends in `footer`, `.stamp` or `.hero-art`, as U2's Q7 found label rules by their last compound. Rows 1.12, 4.7, 4.8.

Fixture: launch.json names both roots, each existing and empty unless the row adds to them; `--once <out>`, exit 0 with
no `Traceback` on stderr, unless the row serves. Terms the rows use:
- **No project**: both roots empty, no live agent: `projects == []`, `orphans == []`.
- **The hero**: the index's `<svg class="hero-art" …>…</svg>`.
- **The stamp**: the `<svg>` a footer opens with.
- **HERO_INKS**: `#12325A` → `currentColor`, `#A87300` → `var(--brass)`, `#F4F7FA` → `var(--bg)`, `#D3DEEA` → `var(--line)`.
- **STAMP_INKS**: `#12325A` → `currentColor`, `#A87300` → `var(--stamp-accent)`, `#F4F7FA` → `none`.
- **Shape for shape**: every circle, ellipse, rect and path, in document order, with every attribute but its paint
  unchanged, and every `<g>` transform; a paint is read from `style` or the attribute.
- **A clone copy**: U1's `given_clone_copy`, the dashboard run from a scratch copy with one asset deleted, or a directory
  in its place.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 029-U3.1.1 | empty state | no project | `--once <out>` | `main` is `<h1>Projects</h1><section class="empty">`, the hero, three `<p>` classed none, none, `where`, `</section>`, and nothing else | rule (1), "the index `main` is `<h1>Projects</h1><section class="empty">` holding an inline `<svg class="hero-art" …>`, then `<p>…</p>`, `<p>…</p>`, `<p class="where">…</p>`"; spec §2.7, "Main content" | `test_opens_main_with_the_heading_then_the_empty_section__holding_the_hero_then_three_lines` |
| 029-U3.1.2 | empty state | no project | `--once <out>` | line 1 is `<p>No projects yet.</p>`; line 2's text is `Start one with role-start planner <project>.` | rule (1), "`<p>No projects yet.</p>`, `<p>Start one with <code>role-start planner &lt;project&gt;</code>.</p>` (the exact markup of the command is the Worker's; the text is not)"; D11; Q10 | `test_says_no_projects_yet_and_how_to_start_one__when_there_is_no_project` |
| 029-U3.1.3 | empty state | no project | `--once <out>` | line 3 is `<p class="where">Looking for folders with a PROJECT.md under <span class="mono">ROOT</span></p>`, ROOT the scratch projects root | rule (1), "`<p class="where">Looking for folders with a PROJECT.md under <span class="mono">{e(PROJECTS_ROOT)}</span></p>`"; D11 | `test_names_the_projects_root_it_looked_under_in_mono__when_there_is_no_project` |
| 029-U3.1.4 | empty state | no project | `--once <out>` | no `Nothing needs attention`, no `Nothing is running`, no `No project folder with a PROJECT.md` | rule (1), "the page contains neither `Nothing needs attention` nor `Nothing is running` nor `No project folder with a PROJECT.md`"; spec §2.7 | `test_shows_neither_list_note_nor_the_old_empty_line__when_there_is_no_project` |
| 029-U3.1.5 | hero | no project | `--once <out>` | the hero's tag: `class="hero-art"`, `aria-hidden="true"`, `focusable="false"`; no `role`, `aria-label` or `id` | rule (1); D11, "decorative (`aria-hidden="true" focusable="false"`, `role` and `aria-label` stripped)". Assumed Q6 | `test_hides_the_hero_from_screen_readers__and_strips_its_role_and_label` |
| 029-U3.1.6 | hero | no project | `--once <out>` | viewBox `18 18 1164 684` | rule (1), `viewBox="18 18 1164 684"`; spec §1 finding 8, "Crop its 20-unit paper margin" | `test_crops_the_heros_paper_margin__with_its_view_box` |
| 029-U3.1.7 | hero | no project | `--once <out>` | the hero is hero-light.svg shape for shape, read through HERO_INKS | D9, "Tokenising is these substitutions … and nothing else"; D3, "otherwise `assets/hero-light.svg` untouched, tokenised and cropped only"; D10, "Geometry is never redrawn" | `test_draws_the_hero_art_shape_for_shape__with_only_its_four_inks_turned_to_tokens` |
| 029-U3.1.8 | hero | no project | `--once <out>` | none of `#12325A`, `#A87300`, `#F4F7FA`, `#D3DEEA` in any case; no `role=`, `aria-label=`, `id=` | rule (1), "the hero markup contains none of the four hex colours of D9, no `role=`, no `aria-label=`, and no `id=`" | `test_leaves_no_fixed_art_colour_role_label_or_id_in_the_hero` |
| 029-U3.1.9 | hero | no project | `--once <out>` | every paint over the art's `#F4F7FA` (26, the Owner's body and head among them) is `var(--bg)` | D9, "`#F4F7FA` → `var(--bg)` in the hero"; Landmines, "in the hero all of them become `var(--bg)`" | `test_paints_every_paper_in_the_hero_the_page_background__the_owners_included` |
| 029-U3.1.10 | hero | no project | `--once <out>` | the art's one `#D3DEEA` stroke is `var(--line)` | D9, "`#D3DEEA` → `var(--line)` in the hero" | `test_draws_the_heros_grid_line_in_the_line_token` |
| 029-U3.1.11 | hero | no project | `--once <out>` | the hero draws the path `M0 -132V-122` | D3, "the empty-state hero keeps its bulb"; D9, "the bulb begins at `M0 -132V-122`" | `test_keeps_the_owners_light_bulb_in_the_hero` |
| 029-U3.1.12 | hero | no project | `--once <out>` | `.hero-art`: `display:block`, `width:100%`, `max-width:760px`, `height:auto`, `margin:28px auto 18px`, `color:var(--fg)` | spec §2.7, "Sizing: `display:block; width:100%; max-width:760px; height:auto; margin:28px auto 18px; color:var(--fg)`"; D15. Assumed Q9, Q14 | `test_sizes_the_hero_as_the_spec_sets_it__in_the_stylesheet` |
| 029-U3.1.13 | empty state | no project; a plan-usage reading | `--once <out>` | `main` opens `<h1>Projects</h1><section class="empty"><svg class="hero-art"` | rule (1); spec §2.7, "Main content". Assumed Q1 | `test_keeps_main_to_the_heading_and_the_empty_section__when_a_plan_usage_reading_is_shown` |
| 029-U3.1.14 | empty state | no project; session `notes-app-001-first`, an orphan | `--once <out>` | the orphans heading; no `class="empty"`; no hero | rule (1), "(`projects == []`, `orphans == []`)"; Language, "empty state: no projects and no orphan sessions"; Q2 | `test_shows_no_empty_state__when_an_orphan_session_exists_without_any_project` |
| 029-U3.1.15 | escaping | no project; the projects root `<roots>/projects <x data-injected="root"> & co` | `--once <out>` | line 3's mono span reads `<roots>/projects &lt;x data-injected=&quot;root&quot;&gt; &amp; co` | rule (1), "{e(PROJECTS_ROOT)}"; `.claude/rules/dashboard.md`, "HTML text or a quoted attribute: `e()`". Assumed Q11 | `test_writes_a_hostile_projects_root_escaped__in_the_where_line` |
| 029-U3.1.16 | escaping | as 1.15 | `--once <out>` | no `x` element, no `data-injected` attribute on the index | `.claude/rules/dashboard.md`; prepub-3 H1.1's check. Assumed Q11 | `test_writes_no_element_or_attribute_from_a_hostile_projects_root__on_the_empty_page` |
| 029-U3.2.1 | missing art | no project; a clone copy without `hero-light.svg` | `--once <out>` | exit 0, no traceback; no `<svg` in the empty section; its lines read `No projects yet.`, line 2, `Looking for folders with a PROJECT.md under ROOT` | rule (2), "the three lines render and no `<svg class="hero-art"` does; exit 0"; D8, "a text-only empty state". Assumed Q4 | `test_writes_the_three_lines_with_no_hero__when_the_hero_art_is_missing` |
| 029-U3.2.2 | missing art | no project; a clone copy with a directory for `hero-light.svg` | `--once <out>` | as 2.1 | D8, "a missing or unreadable file degrades"; Q5. Assumed Q4 | `test_writes_the_three_lines_with_no_hero__when_the_hero_art_cannot_be_read` |
| 029-U3.2.3 | missing art | no project; a clone copy without `hero-light.svg` | `--once <out>` | the footer still opens with `<svg class="stamp">` | D8, each file degrades its own art ("a text-only empty state, no stamp"); rule (4), "every rendered page" | `test_keeps_the_footer_stamp__when_only_the_hero_art_is_missing` |
| 029-U3.3.1 | gives way | project `sample`, no session | `--once <out>` | no `class="empty"`, no hero; the crew card reads the quiet line | rule (3), "With one project present the `.empty` section is absent (the quiet card or crew card shows instead, U2)" | `test_shows_the_quiet_card_and_no_empty_state__when_one_project_has_no_session` |
| 029-U3.3.2 | gives way | project `sample`, SLUG implementing | `--once <out>` | no `class="empty"`, no hero; heading `On site · 1` | rule (3); U2 rule (2) | `test_shows_the_crew_card_and_no_empty_state__when_one_project_has_a_running_session` |
| 029-U3.4.1 | stamp | project `sample`, SLUG implementing | `--once <out>` | `index.html` and `sample.html`: `<footer id="foot">`, `<svg class="stamp">`, then a `<span>` reading `Updated HH:MM:SS · refreshes every 20s` and the page's tail | rule (4), "every rendered page (index, a project page, a `--once` page) has `<footer id="foot">` whose first child is `<svg class="stamp" …>` followed by `<span>Updated …</span>`"; D12; D14. Assumed Q7, Q8 | `test_opens_the_footer_with_the_stamp_then_the_updated_line__on_both_pages_once_writes` |
| 029-U3.4.2 | stamp | as 4.1, served | GET `/` and `/p/sample` | 200; each footer as 4.1 | rule (4). Assumed Q7, Q8 | `test_opens_the_footer_with_the_stamp_then_the_updated_line__on_both_pages_the_server_answers` |
| 029-U3.4.3 | stamp | no project | `--once <out>` | the index's footer as 4.1 | rule (4), "every rendered page". Assumed Q7, Q8 | `test_opens_the_footer_with_the_stamp__on_the_empty_index` |
| 029-U3.4.4 | stamp | no project | `--once <out>` | the stamp's tag: `class="stamp"`, viewBox logo-light.svg's (`-104 -104 208 208`), `aria-hidden="true"`, `focusable="false"`; no `role` or `aria-label` | rule (4), "`<svg class="stamp" viewBox="-104 -104 208 208" … aria-hidden="true" focusable="false">` … no `role=`/`aria-label=`"; spec §2.8. Assumed Q6 | `test_hides_the_stamp_from_screen_readers_in_the_logos_view_box` |
| 029-U3.4.5 | stamp | no project | `--once <out>` | the stamp is logo-light.svg shape for shape, read through STAMP_INKS | D9, "`#A87300` → `var(--brass)` (stamp: `var(--stamp-accent)`); `#F4F7FA` → … `none` in the stamp"; spec §2.8, "tokenised: line → `currentColor`, brass → `var(--stamp-accent)`, paper `#F4F7FA` → `none`" | `test_draws_the_logo_art_shape_for_shape__with_its_inks_turned_to_the_stamps_tokens` |
| 029-U3.4.6 | stamp | no project | `--once <out>` | `var(--stamp-accent)` present; no `#A87300`, no `#F4F7FA`; the art's paper circle paints `none` | rule (4), "the stamp carries `var(--stamp-accent)` and no `#A87300`, no `#F4F7FA` fill (the paper circle is `fill="none"`)" | `test_paints_the_stamps_accent_in_the_faded_token_and_leaves_its_paper_unfilled` |
| 029-U3.4.7 | stamp CSS | no project | `--once <out>` | `footer`: `display:flex`, `align-items:center`, `gap:12px` | rule (4), "`footer{display:flex;align-items:center;gap:12px…}`"; D12. Assumed Q14 | `test_lays_the_footer_out_in_a_centred_row__in_the_stylesheet` |
| 029-U3.4.8 | stamp CSS | no project | `--once <out>` | `.stamp`: `width:48px`, `height:48px`, `color:var(--faint)`, `flex:none` | rule (4), "`.stamp{width:48px;height:48px;color:var(--faint);flex:none}`"; D12, "48 px, never below 44". Assumed Q14 | `test_sizes_the_stamp_at_48px_in_the_faint_ink__in_the_stylesheet` |
| 029-U3.4.9 | stamp CSS | no project | `--once <out>` | every `--stamp-accent` declaration is `color-mix(in srgb,var(--brass) 85%,var(--bg))` | rule (4), "`--stamp-accent:color-mix(in srgb,var(--brass) 70%,var(--bg))`"; D12, "brass mixed 70 % toward `--bg`"; **raised to 85 % by U32** bound 1, "held to 3:1 … unless it fails that" (70 % is 2.44:1 in Whiteprint, 85 % the least whole step of five over 3:1; 032-F1.2). Assumed Q13 | `test_mixes_the_stamp_accent_from_brass_eighty_five_percent_toward_the_background__in_the_stylesheet` |
| 029-U3.5.1 | missing art | project `sample`, SLUG implementing; a clone copy without `logo-light.svg` | `--once <out>` | exit 0; `index.html` and `sample.html` footers hold the `<span>` alone, reading as 4.1 | rule (5), "With `assets/logo-light.svg` absent the footer renders without the stamp, exit 0"; D12. Assumed Q3, Q8 | `test_writes_the_footer_text_alone__when_the_logo_art_is_missing` |
| 029-U3.5.2 | missing art | project `sample`; a clone copy with a directory for `logo-light.svg` | `--once <out>` | exit 0; the index's footer as 5.1 | D8, "a missing or unreadable file degrades: … no stamp"; Q5. Assumed Q3, Q8 | `test_writes_the_footer_text_alone__when_the_logo_art_cannot_be_read` |
| 029-U3.5.3 | missing art | no project; a clone copy without `logo-light.svg` | `--once <out>` | the empty section opens with `<svg class="hero-art"` | D8, each file degrades its own art; rule (1) | `test_keeps_the_hero__when_only_the_logo_art_is_missing` |
| 029-U3.6.1 | json | no project, served | GET `/attention.json` | `(200, "[]")` | rule (6), "`/attention.json` unchanged"; D14; pre-change behaviour at b02d51f, Q12 | `test_serves_an_empty_attention_list__when_there_is_no_project` |
| 029-U3.6.2 | json | CrewJson's world: SLUG finished and through intake, SECOND stopped, `sample-003-third` briefed, `sample-004-fourth` implementing; served | GET `/attention.json` | `(200, ATTENTION_JSON)` | rule (6), "(as U2 rule 10)"; ATTENTION_JSON, pre-change behaviour at b02d51f (029-U2.10.1) | `test_serves_attention_json_byte_for_byte_as_before__beside_the_footer_stamp` |

## 031 · row glyphs on the project page's session cards; the crew ghost's link follows the data

From U31 (a direct build): `design/u31/DESIGN-U31.md`, "The delta (recommended: project page only)", the Owner's answers
to its Q1 (a collapsed card keeps its glyph) and Q2 (no larger figure), and the Lead's ghost decision (DECISIONS.md,
2026-10-14, "U29 done; ghost href decided"; U29 end-of-stack F1). The figure is U29's `glyph(figure_role(session))`, so
the role rows reuse 029-U1's state fixtures.

Q1 — "A running member on the crew": the drawn members only, or every session on site? → Assumed: every session on site,
the ghost's own count included. The ghost counts the hidden sessions, so its link must reach them; a running session
hidden past the cap still makes In flight exist. Row G1.2.
Q2 — How is "no existing CSS rule changes" tested? → Assumed: by the two `.sess>summary` rules the spec's narrow-width
claim rests on, verbatim; the whole-stylesheet comparison against the base is the reviewer's diff check. Row P4.1.
Q3 — How is "the glyph stays when collapsed" tested without a browser? → Assumed: the glyph is in `<summary>`, which a
closed `details` still shows, and no rule selects a `.gl` with `[open]` or `display:none`. Row P2.3.

Fixture: launch.json naming both roots; project `sample` with U1 `first` unless the row says otherwise; `--once <out>`,
exit 0, no `Traceback`. A **card** is `<details class="sess …" id="s-<slug>">` and its `<summary>`. **The glyph** is
`<span class="gl" aria-hidden="true"><svg…></svg></span>`.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 031-P1.1 | on site | SLUG stopped, SECOND briefed, `sample-003-third` implementing, `sample-004-fourth` at `end-of-stack` | `--once <out>` | each card is classed `sess`, its summary opens with the glyph drawing Owner, Lead, Worker, Reviewer | spec, "every `details.sess` … whose `session_bucket` is `attention` or `working`"; "Figure: `glyph(figure_role(session))`"; spec test bullet 1 | `test_draws_the_figure_role_maps_to__on_each_attention_and_working_card` |
| 031-P1.2 | markup | SLUG implementing | `--once <out>` | the summary is the glyph, then `<span class="slug mono" title="sample-001-first">001-first</span>`, `<span class="st"><i class="dot run"></i>Working</span>`, `<span class="ago">` with the time, nothing else | DESIGN-U33 §4.5 `render_session`, §4.7 rule 4: the dot moves into the state | `test_puts_the_glyph_first_in_the_summary__then_the_dot_slug_state_and_time_unchanged` |
| 031-P2.1 | not on site | SLUG done (not in main, Awaiting acceptance), SECOND parked, `sample-003-third` unreadable run.json, `sample-004-fourth` done | `--once <out>` | the parked, error and done cards carry no `g` and no `.gl`; the Awaiting acceptance alert no `.gl` | spec, "Which don't: Waiting … Done … Error cards … The Ready to land alert"; spec test bullet 2 | `test_draws_no_glyph_on_waiting_done_or_error_cards__nor_on_awaiting_acceptance` |
| 031-P2.2 | one figure | SLUG stopped, SECOND implementing, `sample-003-third` parked | `--once <out>` | outside the project's crew card the page's `<svg>`s are the mark, the stamp and two `fig`s, the two cards' glyphs; the crew card holds two `fig`s of its own | Owner Q2, "no larger figure on an expanded card"; DESIGN-U33 §4.7 rule 5 | `test_draws_one_figure_per_on_site_card__and_no_other_on_the_project_page` |
| 031-P2.3 | collapsed | SLUG implementing | `--once <out>` | the glyph is in the summary; no rule selects `.gl` with `[open]` or `display:none`. Assumed Q3 | Owner Q1, "a collapsed card keeps its glyph" | `test_keeps_the_glyph_when_a_card_is_collapsed__no_rule_hides_it` |
| 031-P3.1 | constant | SLUG stopped, SECOND implementing | `--once <out>` | each card's glyph is byte for byte its index row's | spec, "`glyph(figure_role(session))` … unchanged"; "the glyph is a module constant chosen by role" | `test_draws_the_same_constant_glyph_on_the_card_as_on_the_index_row` |
| 031-P3.2 | escaping | the hostile world (prepub-3): LIVE_NAME holds SLUG stopped, SECOND implementing | `--once <out>` | neither card's glyph holds the name raw, escaped or quoted, `data-injected` or the slug; the page has no `data-injected` attribute | spec, "Every escape: … no interpolated data"; `.claude/rules/dashboard.md` | `test_carries_nothing_of_a_hostile_name_or_slug__in_either_cards_glyph` |
| 031-P4.1 | CSS | SLUG implementing | `--once <out>` | verbatim: `.sess>summary>.gl{grid-column:1/-1;display:flex;align-items:flex-end;height:30px;--fig-fill:none}`; `.sess>summary{display:grid;grid-template-columns:minmax(0,1fr) auto auto;column-gap:14px;row-gap:4px;align-items:baseline;padding:14px 20px 12px;cursor:pointer;list-style:none}`; and the 560 px `.sess>summary{padding:12px 16px 10px;grid-template-columns:minmax(0,1fr) auto}`. Assumed Q2 | DESIGN-U33 §4.6 | `test_carries_the_spec_rules_and_keeps_the_summary_rules__in_the_stylesheet` |
| 031-P5.1 | orphans | no project; `notes-app-001-first` implementing, `notes-app-002-second` parked | `--once <out>` | on the index, the running orphan's card draws the Worker; the parked one's carries none | spec, "`index.html`'s orphan sessions also go through `render_session`, so they follow the same rule" | `test_draws_the_glyph_on_a_running_orphans_card__and_none_on_a_parked_one` |
| 031-G1.1 | ghost | seven stopped sessions, nothing running | `--once <out>` | the three ghosts link `#attention`; the index has `id="attention"` and no `id="flight"` | Decided (Lead) 2026-10-14, "`#flight` when a running member is on the crew, else `#attention`"; U29 end-of-stack F1 (a) | `test_links_every_ghost_to_needs_attention__when_no_running_member_is_on_the_crew` |
| 031-G1.2 | ghost | six stopped, then one implementing, seventh and hidden | `--once <out>` | the three ghosts link `#flight`; the index has `id="flight"`. Assumed Q1 | Decided (Lead) 2026-10-14 | `test_links_every_ghost_to_in_flight__when_a_running_member_is_on_the_crew_past_the_cap` |

## 032 · the footer's contrast; wrong-shaped `phase`, unit `status`, `ticket` and commit ids

From U32 (a direct build, Owner 2026-10-14): PROJECT.md → Deferred Polish items 4 and 5, and the brief's bounds 1 and 2.
Contrast is WCAG 2.x relative luminance from the theme tokens the page declares; a `color-mix` is computed in sRGB.
"Reads as missing" is the bound's own phrase: a wrong-shaped value renders exactly as the key left out.

Q1 — Which `run.json` fields beyond `phase` and `status` does "the same rule" name? → Decided after review 1 (F1):
the values `session-inputs.md` lists by name (`ticket`, and the commit ids `units[].head` and `publish.tip`), plus the
rest of SECURITY.md's state-field row that holds `phase` and `status` (`stop_reason`, `rotate`, `rebriefs`, `units`),
plus `worktree`, whose SECURITY.md row names the dashboard, and after review 2 (F4) the strings the dashboard reads
inside them: `stop_reason.code` and `.detail`, `rebriefs[].why`. Each is a one-line hold. Rows S3.1–S3.3, S4.1–S4.6, S5.1–S5.3.
Q2 — Is the stamp line (`.stamp`, `--faint`) part of the 3:1 graphic? → Assumed: yes, both of the stamp's inks. Row F1.2.

Fixture: launch.json naming both roots; project `sample` with U1 `first`; SLUG implementing unless the row says otherwise.
Served rows GET `/` and `/p/sample` with the right Host and read the server's stderr after it stops.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 032-F1.1 | footer text | the fixture | `--once <out>` | the `footer` rule's `color` is a theme token at ≥ 4.5:1 on `--bg` in Whiteprint, Blueprint and Night | bound 1, "meets WCAG AA for normal text (4.5:1) against `--bg` in all three themes"; WCAG 2.x 1.4.3 | `test_writes_the_footer_text_at_least_four_and_a_half_to_one_on_the_background__in_every_theme` |
| 032-F1.2 | footer stamp | the fixture | `--once <out>` | `.stamp`'s colour and `--stamp-accent`, brass mixed toward `--bg`, each ≥ 3:1 on `--bg` in every theme. Assumed Q2 | bound 1, "The footer stamp (`--stamp-accent`) is a graphic, held to 3:1"; WCAG 2.x 1.4.11 | `test_draws_the_stamps_line_and_accent_at_least_three_to_one_on_the_background__in_every_theme` |
| 032-S1.1 | never fails | `phase` a list holding markup syntax | `--serve`, GET both | `{"/": 200, "/p/sample": 200}`; no `Traceback` on stderr; no `data-injected` attribute on either | bound 2, "never fails a page … never echoes the raw value unescaped"; bound 4's rows | `test_serves_the_index_and_the_project_page__when_phase_is_a_list` |
| 032-S1.2 | never fails | `phase` an object whose key holds markup syntax | `--serve`, GET both | as S1.1 | bound 4, "a dict-valued `phase`" | `test_serves_the_index_and_the_project_page__when_phase_is_a_dict` |
| 032-S1.3 | never fails | U2's `status` a list holding markup syntax | `--serve`, GET both | as S1.1 | bound 4, "a list-valued unit `status`" | `test_serves_the_index_and_the_project_page__when_a_units_status_is_a_list` |
| 032-S2.1 | reads as missing | SLUG with no `phase`, then `phase: ["implement"]` | `--once` each | SLUG's card on `sample.html` reads word for word the same; the missing one's states read `Working`, `done`, `not started` | bound 2, "A wrong-shaped value reads as the same thing a missing one does today"; the states: pre-change behaviour at 19825d3 | `test_reads_a_list_valued_phase_as_no_phase__on_the_session_card` |
| 032-S2.2 | reads as missing | U2 with no `status`, then `status: ["building"]` | `--once` each | as S2.1; the missing one's states read `Working`, `done`, `?` | bound 2, as S2.1; the states: DESIGN-U33 §5 item 7 | `test_reads_a_list_valued_unit_status_as_no_status__on_the_session_card` |
| 032-S3.1 | ticket | `ticket` a list; an accounting ledger with one record | `--serve`, GET both | as S1.1 | bound 2, "any other `run.json` field the same rule names"; `session-inputs.md`, "a ticket". Assumed Q1 | `test_serves_the_index_and_the_project_page__when_ticket_is_a_list_and_a_ledger_exists` |
| 032-S3.2 | commit id | SLUG done and through intake in a listed scratch repo, its branch not in main; U1's `head` a list | `robowright-dash.py sample` | exit 0; U1 reads `awaiting acceptance` | bound 2; `session-inputs.md`, "a commit id: `COMMIT_ID` in run-cost.py"; R6.3 for the reading. Assumed Q1 | `test_summarises_the_project__when_a_finished_units_head_is_a_list` |
| 032-S3.3 | commit id | as S3.2, `head` `--head-option`, `publish.tip` `--tip-option`; git recorded | `robowright-dash.py sample` | exit 0; U1 `awaiting acceptance`; no git call has an argument starting with either | bound 2; `session-inputs.md`, commit ids and "a value starting with `-` never reads as a flag". Assumed Q1 | `test_passes_no_option_shaped_head_or_tip_to_git__when_a_finished_session_writes_them` |
| 032-S4.1 | state row | `rotate` the string `"x"` | `--serve`, GET both | `{"/": 200, "/p/sample": 200}`; no `Traceback` | review 1 F1; SECURITY.md's `phase`, `stop_reason`, `rotate`, `rebriefs`, `units[]` row | `test_serves_the_index_and_the_project_page__when_rotate_is_a_string` |
| 032-S4.2 | state row | `phase: stopped`, `stop_reason` a list | `--serve`, GET both | as S4.1 | as S4.1 | `test_serves_the_index_and_the_project_page__when_a_stopped_sessions_stop_reason_is_a_list` |
| 032-S4.3 | state row | `rotate` a pending rebrief, `rebriefs: [1]` | `--serve`, GET both | as S4.1 | as S4.1 | `test_serves_the_index_and_the_project_page__when_a_rebrief_entry_is_not_an_object` |
| 032-S4.4 | state row | `units` an object keyed by unit id | `--serve`, GET both | as S4.1 | as S4.1 | `test_serves_the_index_and_the_project_page__when_units_is_an_object` |
| 032-S4.5 | state row | `units` holding a number beside a unit | `--serve`, GET both | as S4.1 | as S4.1 | `test_serves_the_index_and_the_project_page__when_a_unit_is_not_an_object` |
| 032-S4.6 | worktree | a working session's `worktree` a list | `--serve`, GET both | as S4.1 | review 1 F1; SECURITY.md's `worktree` row, "the dashboard" | `test_serves_the_index_and_the_project_page__when_worktree_is_a_list` |
| 032-S5.1 | inside the state row | `phase: stopped`, `stop_reason.detail` a list | `--serve`, GET both | as S4.1 | review 2 F4 | `test_serves_the_index_and_the_project_page__when_a_stop_detail_is_a_list` |
| 032-S5.2 | inside the state row | a pending rebrief, last `rebriefs` entry's `why` a number | `--serve`, GET both | as S4.1 | review 2 F4 | `test_serves_the_index_and_the_project_page__when_a_rebriefs_why_is_a_number` |
| 032-S5.3 | inside the state row | `stop_reason.code` a list | `robowright-dash.py` | exit 0; no `Traceback`; SLUG's line reads `sample-001-first  implement  · <age>`, no code, as with no `stop_reason` | review 2 F4; SECURITY.md's `stop_reason.code` row; the line's shape: R1.1 | `test_summarises_the_project__when_a_stop_code_is_a_list` |

After review 3, decided by the Lead (2026-10-14, under delegation): bound 2's "never fails a page" also covers a
run.json the dashboard cannot serve at all (review 1 F3, review 3 N1 and N2). Each reads as an unreadable run.json
does: the error card, state `Unreadable` (pre-change behaviour at 19825d3 for a run.json of `{`).

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 032-S6.1 | unreadable | run.json is `[1]` | `--serve`, GET both; `--once` | `{"/": 200, "/p/sample": 200}`, no `Traceback`, no injected attribute; SLUG's card's states are `["Unreadable"]` | Lead 2026-10-14, "must each read the way a missing or unreadable `run.json` does today"; review 1 F3 | `test_reads_as_unreadable__when_run_json_is_not_an_object` |
| 032-S6.2 | unreadable | `phase` the JSON escape of a lone surrogate | as S6.1 | as S6.1 | as S6.1; review 3 N1 | `test_reads_as_unreadable__when_a_string_holds_a_lone_surrogate` |
| 032-S6.3 | unreadable | `max_wall_hours` an integer of 5000 digits | as S6.1 | as S6.1 | as S6.1; review 3 N2 | `test_reads_as_unreadable__when_a_number_has_more_digits_than_python_converts` |
| 032-S6.4 | unreadable | a value nested 110,000 deep (`json.loads` reads it, `json.dumps` overflows) | as S6.1 | as S6.1 | review 4 F1: a check by encoding failed a run.json 19825d3 served; review 5 F1: the depth cap reads it Unreadable | `test_reads_as_unreadable__when_run_json_nests_deeper_than_encoding_reaches` |
| 032-S6.5 | unreadable | a value nested 200,000 deep (past `json.loads`) | as S6.1 | as S6.1 | Lead 2026-10-14, "catch what `json.loads` raises"; review 4 F1 | `test_reads_as_unreadable__when_run_json_nests_deeper_than_json_loads_reaches` |
| 032-S6.6 | unreadable | U1's `id` a list nested 80,000 deep (under the encoder's limit, past `str()`'s) | as S6.1 | as S6.1 | review 5 F1 | `test_reads_as_unreadable__when_a_displayed_value_nests_deeper_than_str_reaches` |
| 032-S6.7 | not hidden | an unread field, a list nested 50 deep | `--once` twice | SLUG's card reads word for word as without the field | review 5 F1's fix: a depth cap must not hide a run.json session-state.py could write (it nests about 4 deep) | `test_renders_the_card_as_without_it__when_an_unread_value_nests_fifty_deep` |

## 033 · the content pass: one anatomy per session, the plan's Summary on the face, `\|` in a cell, terminal text

From U33 (a direct build, Owner 2026-10-15): DESIGN-U33 §4 (direction B) and its §4.10 behaviour rows, written from the
spec and not from its mock; the brief's bound 4 (an escaped pipe) and bound 5 (U35's N-6 and N-4, dashboard part).
A card's **face** is its `<summary>` plus its body outside **Details**, the card's `<details class="sub more">`. A plan
row's face is its `summary.row`, or its plain `div.row` when it has nothing to disclose; its **disclosure** is
`<details class="unit" id="u-<id>">`. Lead decisions for the Owner's open questions (DESIGN-U33 §6), 2026-10-15: row
glyphs stay under the crew card; plan usage leaves the project page (flipped by the Owner, 2026-10-15: it is back, after
the hero, B8 and B44); the time hides on cards at 560 px or less; the
Status cell shows inside the disclosure as "Status column"; numbers are short with the exact figure in the `title`.

Q1 — "With no Summary column it shows the Description": one world or two? → Assumed: one test, two projects, so the row
is red at the base on its first half. Row B1.
Q2 — Which callouts are "headed"? → Decided (build): the stop callout drops its code only where the state word carries
it, a stopped card; a rebriefing card's calm callout and any other card with a stop keep the code, which their state
word does not say. Row B5 pins the stopped card and the two headings the spec names.
Q3 — What does "no text uses `--faint`" grep? → Assumed: every rule whose `color` is `var(--faint)`; the footer stamp's
is a drawing in `currentColor`, held to 3:1 by 032-F1.2, and is the one allowed. Row B10.
Q4 — §4.9's table has no row for a hovered row on the index attention paper. → Decided (build): it is text in a state the
page draws, so it is held to 4.5:1 like the rest; the spec's B renders the stopped word in `note-attn`, which fails there.
Row B11, added after the implementation commit with its own red.
Q5 — When has the face "clipped" a Summary? The server cannot measure it. → Decided (build, after review 1 F3): the
face's one line holds about 45 characters at its narrowest, just over 560 px (the row less its dot, id, state and size,
at 13 px); a longer Summary is repeated in the disclosure, and the face always titles it. `SUMMARY` and `DESCRIPTION`
were 50 and 49 characters, clipped by that measure, so B2's "never the Summary twice" Given now uses shorter ones (35
and 28); B2's When and Then are unchanged.
Q6 — Where does a short number change unit? → Assumed: at the value that would round to the next one, so no count reads
`10.0k` or `1000k`. Row B16.
Q7 — What does a halted card's now line say? §4.5 names a stopped card's position; the mock printed a parked card as if
it were running. → Decided (build): a parked card reads `Parked in <unit> of <n>` and a card whose rebrief waits on the
Owner reads `Stopped in <unit> of <n>`. Each is halted mid-brief, and where it halted is what the Owner resumes from;
"building" would claim work that is not happening. A done card has no position phrase: its state word says it all.
Row B30.
Q8 — How does Lead decision 3 (the time hidden on cards at ≤ 560 px) flip? → Two edits in the 560 px block: delete
`.sess>summary>.ago{display:none}` and set that block's `.sess>summary` back to
`grid-template-columns:minmax(0,1fr) auto auto`; the first alone puts the time on a grid row of its own. Row B17 pins
the rule; flipping the decision flips B17's Then.

Fixture: launch.json naming both roots; project `sample` with U1 `first` unless the row says otherwise; `--once <out>`,
exit 0, no `Traceback`. `SUMMARY_ROW` is U1 under `SUMMARY_HEADER`: Summary `SUMMARY`, Description `DESCRIPTION`,
Status `in progress`.

| # | Rule | Given | When | Then | Expected value from | Test |
|---|---|---|---|---|---|---|
| 033-B1 | plan face | `sample`: `SUMMARY_ROW`; `other`: `OLD_ROW` under `OLD_HEADER` | `--once <out>` | `sample.html`'s plan descs are `[SUMMARY]`; `other.html`'s `[DESCRIPTION]` | DESIGN-U33 §4.10 row 1, "shows the Summary cell, not the Description. With no Summary column it shows the Description, because `purpose` falls back to it"; §5 item 4 | `test_shows_the_summary_cell_on_a_plan_rows_face__and_the_description_when_there_is_no_summary_column` |
| 033-B2 | disclosure | as B1 | `--once <out>` | `sample`'s one `unit-body` reads `DESCRIPTION Status column · in progress`; `other`'s reads `Status column · in progress`; `u-U1` starts closed | §4.10 row 2, "holds the Description when it differs from the Summary, and the Status cell always"; §4.5, "Status column · {plain(plan_status)}" | `test_opens_the_description_and_the_status_cell_from_the_row__never_the_summary_twice` |
| 033-B3 | complete | `SUMMARY_ROW` with Status `Done` (complete by the plan, no session) | `--once <out>` | no plan desc on the face; the disclosure's `lede` is `[SUMMARY]` | §4.10 row 3, "A landed unit's row has no Summary line on its face"; §4.5, "the Summary in full, when the face clipped or omitted it" | `test_draws_a_complete_unit_as_one_line__its_summary_behind_the_row` |
| 033-P1 | escaped pipe | `SUMMARY_ROW` with Summary `Totals a \| b per unit` | `--once <out>`; `robowright-dash.py sample` | no `row-error`; the face desc reads `Totals a \| b per unit` with the pipe unescaped; size `M`; the text summary's purpose line reads the same | U33 bound 4, "A cell containing `\|` … is one cell, as GitHub renders it"; GFM spec, Tables (extension): a pipe in a cell is escaped with `\|`, also inside other inline spans | `test_reads_a_cell_holding_an_escaped_pipe_as_one_cell__as_github_renders_it` |
| 033-B4 | card face | SLUG at `end-of-stack`; SECOND stopped, `verification-failed`; `sample-003-third` done with no INTAKE.md in an unlisted worktree (the Lead's intake) | `--once <out>` | the `.st` texts are `Working`, `Stopped · verification-failed`, `With the Lead`; each summary's one dot sits inside `.st` | §4.10 row 4, "no left dot … no raw phase … or Lead stage. A stopped card's state keeps the code"; §4.7 rule 4 | `test_carries_no_left_dot_and_no_raw_phase_or_lead_stage_on_a_cards_face__and_a_stop_keeps_its_code` |
| 033-B5 | callouts | SLUG stopped (code, detail); SECOND implementing with a STOP file; `sample-003-third` a pending rebrief whose verdict is `owner` | `--once <out>` | SLUG's callouts are `[detail]`; SECOND's is `Owner STOP file present The session halts at its next check.`; the third's begins `Rebrief needs your call`. Q2 | §4.10 row 5, "The stop callout has no code heading. The STOP-file and owner-call callouts keep theirs"; §5 item 8 | `test_drops_the_code_heading_from_the_stop_callout__and_keeps_the_stop_file_and_owner_call_headings` |
| 033-B6 | Details | SLUG implementing with `repo`, `shape`, a LEDGER.md heading, HANDOFF.md's FIRST ACTION, one event, one ledger record; the accounting root named | `--once <out>` | one Details; repo, shape, `longest quiet`, `requests`, the heading, `Recent events`, the first action and the session folder each appear in it, and as often in the whole card as in it; Details starts closed | §4.10 row 6, "Repo, shape, longest quiet, spend, ledger, events, handoff and the path all sit inside the card's Details"; §5 items 9-12 | `test_keeps_repo_shape_quiet_spend_ledger_events_handoff_and_path_inside_details__and_nowhere_else_on_the_card` |
| 033-B7 | project crew | `sample`: SLUG implementing, SECOND stopped; `other`: `other-001-alpha` implementing; `still`: no session | `--once <out>` | `sample.html` has a crew card whose `who`s are `002-second`, `001-first`, linking `#s-…` of each, and no `where`; `still.html` shows `Quiet site. Nothing is running.` | §4.10 row 7, "a crew card of only its own on-site sessions, with no project caption line. The quiet card shows when none is on site"; §4.5 `project_crew`, "with fragment hrefs" | `test_heads_the_project_page_with_a_crew_card_of_its_own_on_site_sessions__no_project_line__or_the_quiet_card` |
| 033-B8 (was P3-R3.2) | plan usage | P3's world, a reading in `$CLAUDE_USAGE_DIR` | `--once <out>` | `sample.html`: one `plan-usage` line, in no card, after the hero's `</section>`, with `5-hour 42%` and `7-day 17.5%`; no `5-hour` on the facts line; the index: one line | the Owner, 2026-10-15: "plan usage shows only on the index: I want that on the project page too; should be clear there as well" (flips Lead decision 2); the bound: "placed so it reads as a page-level fact about the account, not as part of the project's own facts line" | `test_shows_one_plan_usage_line_on_the_project_page_after_its_hero__and_one_on_the_index` |
| 033-B9 | In flight row | SLUG implementing, U2 `building`, one `unit-start` event for U2 | `--once <out>` | the index row has no `run-key` and no visible `U2 started`; its now line's first span's `title` begins `U2 started · ` | §4.10 row 9, "no legend and no separate latest-event line. Its now line's `title` holds the latest event"; §5 items 15-16 | `test_carries_no_legend_and_no_latest_event_line_on_an_in_flight_row__the_now_lines_title_holds_the_event` |
| 033-B10 | faint | the fixture | `--once <out>` | the selectors whose `color` is `var(--faint)` are exactly `{.stamp}`. Q3 | §4.4, "`--faint`: borders, hover rings and the overflow ghost only. Never text"; §4.10 row 10 | `test_sets_no_text_in_the_faint_ink__only_the_stamps_drawing` |
| 033-B11 | attention paper | SLUG stopped, `verification-failed` | `--once <out>` | in every theme, the ink reaching `#attention`'s `.st.attn`, read through the `#attention .list` token map, is ≥ 4.5:1 on that rule's `background` and on `a.row:hover`'s (the row is a link). Q4 | §4.9, "Every text pair B uses passes AA"; WCAG 2.2 SC 1.4.3, text in every state; the build's contrast table (`note-attn` on `note-hover`: 4.33 Whiteprint, 4.26 Blueprint) | `test_reads_the_stopped_word_on_the_index_attention_paper_at_four_and_a_half_to_one__at_rest_and_on_hover` |
| 033-B12 | attention word | `sample`: four units, each a long name (`<word>-LONG_UNIT_TAIL`), size S, each built by a finished session in an unlisted worktree | `--once <out>` | the index's Awaiting acceptance row: its `.st` reads `4 built`; its one clamped line and that line's `title` both read every unit, `U1 alpha-… , …, U4 delta-…` | review 1 F1: the nowrap state word squeezed the row's name to nothing and ran off its edge; the base had the list on a wrapping line with a `title` | `test_keeps_the_awaiting_acceptance_rows_state_word_short__its_units_on_a_clamped_line_with_all_of_them_in_the_title` |
| 033-B13 | attention word | SLUG stopped (`verification-failed`, a detail); its rebrief Planner live and idle | `--once <out>` | the index row's `.st` reads `Stopped · verification-failed`; its clamped line and `title` read `Rebrief Planner idle without a verdict · <detail>`; `.srow .head .st` declares `min-width:0` | review 1 F1, the same squeeze at phone width; `/attention.json`'s `what` keeps the aside (029-U2.10.1 pins the shape) | `test_keeps_a_stopped_rows_state_word_to_its_code__an_idle_rebrief_planner_on_its_clamped_line` |
| 033-B14 | clipped Summary | `SUMMARY_ROW` with a 70-character Summary | `--once <out>` | the unit's disclosure reads `<summary> DESCRIPTION Status column · in progress`; the face's `clamp1` line has the Summary as its `title`. Q5 | §4.5, "the Summary in full, when the face clipped or omitted it"; review 1 F3 | `test_repeats_a_summary_the_narrowest_face_clips_inside_the_row__and_gives_the_face_its_title` |
| 033-B15 | short numbers | Spend's world; one record on SLUG: 23,456 requests, 3,141,592 output tokens | `--once <out>` | SLUG's spend line, titles left out, holds `23k requests` and `3.1M output tokens`; with its titles, `23,456 requests` and `3,141,592 output tokens` | Lead decision 5; §5 item 2, short counts with "exact figures in `title`" | `test_reads_a_count_short_on_the_face__with_its_exact_figure_in_the_title` |
| 033-B16 | short numbers | Spend's world; SLUG: 9,950 requests, 999,499 tokens; SECOND: 9,949 requests, 999,500 tokens | `--once <out>` | SLUG's line ends `10k requests · 999k output tokens`; SECOND's `9.9k requests · 1.0M output tokens`. Q6 | Lead decision 5; review 1 F2 | `test_rounds_a_short_count_up_to_its_next_unit__never_to_ten_point_oh_k_or_a_thousand_k` |
| 033-B17 | narrow time | the fixture, SLUG implementing | `--once <out>` | in `@media (max-width:560px)`, the selectors ending in `.ago` that declare `display:none` are exactly `{.sess>summary>.ago}` | Lead decision 3; §5 item 13, "hidden at ≤ 560 px; still on the index rows' head" | `test_hides_the_time_on_a_card_at_560_px_or_less__and_on_no_index_row` |
| 033-B18 | hero facts | `OLD_ROW` (U1, M) and `SECOND_OLD_ROW` (U2, S); SLUG finished, through intake, in an unlisted worktree (U1 built) | `--once <out>` | the facts line's first two spans are `60% built` titled `weighted by unit size`, and `about 1h left` titled `of session time, at the pace so far` | §5 item 1, the facts line's percent built and hours left, with "weighted by size" and "of session time … at the pace so far" to the tooltip; 3 of 5 points built; U2's 2 points at SLUG's 1.9 h per 3 | `test_heads_the_project_with_how_much_is_built_and_the_time_left__each_saying_what_it_is_weighted_by_in_its_title` |
| 033-B19 | briefed card | SLUG `briefed`, two units, `max_wall_hours` 6 | `--once <out>` | the card's now line reads `Ready to launch · 2 units`; no `meter` in the card | §5 item 20, "the now line 'Ready to launch · 1 unit'"; the wall is "removed duplicate" | `test_says_ready_to_launch_and_how_many_units_on_a_briefed_card__with_no_wall_meter` |
| 033-B20 | stopped card | SLUG stopped, U1 done, U2 todo | `--once <out>` | the card's now line begins `Stopped in U2 of 2` | §4.5, the now line names where a stopped card stopped | `test_says_which_unit_a_stopped_card_stopped_in__on_its_now_line` |
| 033-B21 | rebrief holder | SLUG stopped; its rebrief Planner live and busy (rebriefing) | `--once <out>` | the card holds `claude attach` once, in its calm callout; the index row's now line holds it | §5 item 20's rule, one fact once; review 1 F5 | `test_names_a_rebriefs_planner_once_on_its_card__in_the_callout__and_on_the_index_rows_now_line` |
| 033-B22 | stage count | `sample`: U1 and U2 `Done`, U3 in progress; `other`: U1 and U2 `Done` | `--once <out>` | `sample.html`'s stage counts are `[2 of 3 complete]`; `other.html`'s `[2 complete]` | §4.5 `render_plan`, a right-aligned count, "N landed" or "N of M landed" | `test_counts_a_stages_complete_units_as_some_of_all__and_as_all_when_every_one_has` |
| 033-B23 | card bar | SLUG implementing (two units); SECOND `briefed`; `sample-003-third` done, through intake | `--once <out>` | `.track` count per card: SLUG 1, SECOND 0, third 0 | §4.5 `render_session` step 3, "the bare run track, not for briefed or terminal sessions" | `test_draws_the_run_track_on_a_working_card__and_none_on_a_briefed_or_done_card` |
| 033-B24 | Latest | SLUG implementing U2 with one `unit-start` event for U2; SECOND with a LEDGER.md heading and no event | `--once <out>` | SLUG's card has one note beginning `Latest · U2 started`, inside its Details only; SECOND's card has no `Latest · ` | §4.5 `details`, "the latest move (only when there are events)"; §5 items 11, 16 | `test_keeps_the_latest_move_in_details_when_the_card_has_events__and_no_latest_line_when_it_has_none` |
| 033-B25 | index time | SLUG stopped, written `QUIET_MINUTES` ago | `--once <out>` | the index row's `.ago` spans are `[5m ago]` | §4.5 `render_attention`; §5 item 13, "still on the index rows' head" | `test_ends_an_index_attention_row_with_how_long_ago_its_session_wrote` |
| 033-B26 | wall meter | SLUG implementing, started 2 h ago, `max_wall_hours` 6 | `--once <out>` | the card's now line and the In flight row's each hold `<span class="meter">` and read `2.0 of 6h` | §4.5 `now_line`; §5 item 9, "now line 'U3 of 4 · building · active 3m ago · ▬ 2.0 of 6h'" | `test_carries_the_wall_meter_on_a_working_cards_now_line__and_on_its_in_flight_row` |
| 033-B27 | crew place | the fixture, SLUG implementing | `--once <out>` | on `sample.html` the crew card starts after the hero's `</section>` and before the first `<h2` | §4.5 `render_project_page`, "`project_crew` comes after the hero" | `test_places_the_project_pages_crew_card_right_after_its_header__before_any_section` |
| 033-B28 | flight track | the fixture, SLUG implementing (two units) | `--once <out>` | the In flight row holds a `.track` of 2 segments | §4.5 `flight_row_B`, "the purpose, the bare track and `now_line`" | `test_draws_one_track_segment_per_brief_unit_on_an_in_flight_row` |
| 033-B29 | rotating | SLUG with no brief units and a `rotate` (reason `context`) | `--once <out>` | the card's now line reads `Handing off · active 5m ago` | review 2 N1: `Handing off · ·`, an empty phrase between two separators | `test_says_handing_off_alone_for_a_rotating_session_with_no_brief_units` |
| 033-B30 | halted position | SLUG parked; SECOND rotating for a rebrief whose verdict is `owner` | `--once <out>` | SLUG's now line begins `Parked in U2 of 2`; SECOND's `Stopped in U2 of 2`. Q7 | Q7 | `test_says_where_a_parked_or_owner_call_session_stopped__on_its_now_line` |
| 033-B31 | ghost link | eight sessions implementing in `sample` | `--once <out>` | `sample.html`'s ghosts all link `#working`, an `<h2 id="working">` the page has; the index's link `#flight` | review 2 N3; a ghost links the running list on its own page | `test_links_the_project_pages_crew_ghost_to_its_working_list` |
| 033-B32 | rebrief reason | SLUG stopped (`verification-failed`, its detail); its rebrief Planner live and busy | `--once <out>` | the In flight row's clamped line and `title` read `Stopped on verification-failed: <detail>` | review 2 N3; §5 item 17's clamp, the rebrief row's stop | `test_clamps_a_rebriefing_rows_stop_to_two_lines__the_whole_of_it_in_the_title` |
| 033-B33 | pending row | a brief being written for SLUG (busy Planner, no run.json) | `--once <out>` | the index row's now line's first `title` is `Planner writing the brief` | review 2 N3; §5 item 16's rule, where in the title | `test_keeps_a_pending_rows_where_in_its_now_lines_title` |
| 033-B34 | escaped pipe | `SUMMARY_ROW` with no closing pipe, its last cell `in progress \|` | `--once <out>` | the Status line reads `Status column · in progress \|` | GFM: an escaped pipe is cell text; review 2 N3 | `test_keeps_an_escaped_pipe_at_the_end_of_a_row_with_no_closing_pipe__in_its_last_cell` |
| 033-B35 | ledger label | SLUG with a LEDGER.md heading `2026-10-15 — U1 closed` | `--once <out>` | SLUG's notes hold `Ledger · 2026-10-15 — U1 closed` | §5 item 11, "then 'Ledger · …'" | `test_labels_the_ledgers_latest_heading_ledger_inside_details` |
| 033-B36 | facts line | SLUG implementing with two rebriefs and `reviews/U1-gate.md` | `--once <out>` | SLUG's one `.path` holds `2 rebriefs` and `U1-gate.md`; each appears once on the card, inside its Details | §4.5 `facts_line`, "repo · shape · longest quiet · rebriefs · dir · files"; §5 item 9 | `test_keeps_the_rebrief_count_and_the_folders_files_on_the_facts_line_inside_details` |
| 033-B37 | index card | the fixture, SLUG implementing | `--once <out>` | the index's `sample` card holds its `.track` and no `key seg` legend mark | §4.5 `render_index`, "delete `{tally(p["units"])}`"; §5 item 18 | `test_draws_no_tally_on_a_live_project_card_on_the_index` |
| 033-B38 | no-plan facts | `sample`'s PROJECT.md has no Task Breakdown; SLUG implementing; one ledger record (12 requests) on SLUG; the accounting root named | `--once <out>` | `sample.html` has one facts line, reading `12 requests` | §5 item 2, spend on the facts line under the header | `test_shows_the_spend_under_the_header_of_a_project_with_no_task_breakdown` |
| 033-B39 | error card | SLUG's run.json is `{` | `--once <out>` | SLUG's `.path` texts are `[<SLUG's folder>]` | §4.5, "The error card is unchanged" | `test_keeps_the_folder_path_on_an_unreadable_card` |
| 033-B40 | parked bar | SLUG parked (two units) | `--once <out>` | SLUG's card has no `.track` | §4.5 `render_session` step 3, "not for briefed or terminal sessions" | `test_draws_no_run_track_on_a_parked_card` |
| 033-B41 | briefed, one | SLUG `briefed`, one unit | `--once <out>` | the card's now line reads `Ready to launch · 1 unit` | §5 item 20, "the now line 'Ready to launch · 1 unit'" | `test_says_ready_to_launch_and_one_unit__in_the_singular` |
| 033-B42 | rebrief callout | SLUG stopped (`verification-failed`, its detail); its rebrief Planner live and busy | `--once <out>` | SLUG's card holds `<div class="callout calm"><b>verification-failed</b><detail></div>` | Q2, the heading a non-stopped state word does not carry | `test_keeps_the_code_heading_on_a_rebriefing_cards_stop_callout` |
| 033-B43 | ghost to attention | eight sessions stopped in `sample` | `--once <out>` | `sample.html`'s ghosts all link `#attention`; the page has `<h2 class="attn-head" id="attention">` | review 3 N5; a ghost links Needs attention when nobody on site is running | `test_links_the_project_pages_crew_ghost_to_its_attention_heading__when_nobody_on_site_is_running` |
| 033-B44 | plan usage, one wording | as B8 | `--once <out>` | on the index and on `sample.html` the line reads `Plan usage, all projects · 5-hour 42% · 7-day 17.5% · as of 21:45:00`, its `title` holds `Claude plan's usage across every session`, and both pages' text and `title` are the same | the Owner, 2026-10-15, "should be clear there as well"; the bound: "Plan usage, all projects · 5-hour 24% · 7-day 41% · as of …", "with a `title` saying it is the Claude plan's usage across every session. The index and the project page use the same words"; the time as P3-R3.1 | `test_labels_the_plan_usage_line_as_the_plans_across_all_projects__in_the_same_words_on_both_pages` |
| 033-G1 | end of options | SLUG done and through intake in a listed scratch repo, its branch not in main, its `head` not a commit id (so the branch is tried); git recorded | `robowright-dash.py sample` | at least one `merge-base` and one `log` call; each `merge-base`'s third-last argument and each `log`'s second-last is `--end-of-options` | U33 bound 5, N-6, "`--end-of-options` on the dashboard's `merge-base` and `log` git calls"; `session-inputs.md`, "end options with `--end-of-options` (git)" | `test_ends_options_before_every_revision_given_to_merge_base_and_log` |
| 033-T1 | terminal text | `SUMMARY_ROW` with a BEL in the Summary; SLUG's `phase` holds a lone ESC and a DEL, its stop code a BEL and a lone C1 CSI | `robowright-dash.py sample` | none of the four bytes in stdout; the session line reads `sample-001-first  implement  · verification-failed  · …`; the purpose line reads `SUMMARY` | U33 bound 5, N-4, "the terminal (text) summary strips control bytes from session text through the existing `shown()`"; `session-inputs.md`, "Fence or strip session text before you print it to the Owner" | `test_prints_no_control_byte_from_session_text__in_the_terminal_summary` |

Red at the spec commit (`82b963d`, before any implementation): 13 of 13, each on its own assertion. Evidence:
`red-033.log` in the U33 ledger folder.

## 037 · a plan's groups are stages; a `Wave` heading still groups

The Owner renamed a plan's ordered groups of units from waves to stages (2026-10-15). The dashboard already shows any
`###` heading in the Detailed TODO as a group label; these rows pin that for both words, through the renamed markup.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 037-S1 | stage | `OLD_ROW` (U1) and `SECOND_OLD_ROW` (U2); Detailed TODO `### Stage 1 — Foundation` listing U2 then U1 | `--once <out>` | `sample.html`'s plan is one `plan-stage`: label `Stage 1`, theme `Foundation`, units `[U2, U1]` | brief bound 1; `PROJECT-TEMPLATE.md` § Detailed TODO | `test_groups_the_units_under_a_stage_heading__as_one_stage_with_its_label_and_theme` |
| 037-S2 | old plan | the same, the heading `### Wave 1 — Foundation` | `--once <out>` | one `plan-stage`: label `Wave 1`, theme `Foundation`, units `[U2, U1]` | brief bound 1, "keeps reading an existing plan whose headings say `Wave`" | `test_still_groups_the_units_under_a_wave_heading__as_one_stage` |

Red before the dashboard change: 2 of 2, each on its assertion (the page had no `plan-stage`).

## 039 · in main only on positive evidence; a direct build's worktree found by its branch

From U39 (landed-truth), a direct build (Owner 2026-10-15). Bound 1: a direct build's worktree is found by
`robowright/<slug>` in `git worktree list` of the trusted repositories, wherever it is on disk. Bound 2: "never infer
landed from a missing worktree" — in main is `run.json.accepted` (named `landed` then), or the branch in main, or a finished build whose branch
is gone from every trusted repository while each one its project names is trusted (teardown deletes the branch only
after an accept). Review 1 widened "every repository its project names" to every trusted one (L14); review 2 added that a
worktree still on disk is never torn down (L16), and that only the project's own repositories must answer (L17).
Bound 2b: a direct build's session in `shell` is working.

Fixture: launch.json naming both roots; project `sample` whose robowright.json names one scratch repository, listed in
launch.json's `repos` unless the row says not; `robowright/<SLUG>` one commit ahead of `main` there. "Outside" is a
worktree at `<base>/elsewhere/<slug>`; "torn down" is `git worktree remove`, then `git branch -D`.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 039-L1 | direct, exited | `prs/<SLUG>.md`; an outside worktree on the branch; no live session | `robowright-dash.py sample` | U1 reads `with the Lead`, not `complete` | bound 2, "anything else that is finished reads as done, awaiting land"; the 2026-10-15 reproduction | `test_reads_a_finished_direct_build_with_the_lead__when_its_worktree_is_outside_claude_worktrees_and_its_session_has_exited` |
| 039-L2 | direct, torn down | as L1, then torn down | `sample` | U1 reads `complete` | bound 2, "its branch is gone from every trusted repo **and** its change description exists" (green at red; owes a kill) | `test_reads_a_finished_direct_build_complete__when_its_branch_is_gone_from_every_trusted_repository` |
| 039-L3 | no description | the branch deleted; `prs/<SLUG>/` with no `prs/<SLUG>.md`; no live session | `sample` | U1 reads `working` | bound 2, "a build with no change description is never landed" (green at red; owes a kill) | `test_never_reads_a_direct_build_complete__when_it_has_no_change_description` |
| 039-L11 | found by branch | as L1, with an uncommitted file in the worktree | `sample` | U1 reads `working` | bound 1, "find a direct build's worktree by its branch … wherever the worktree is on disk"; `direct_builds`, finished only with nothing uncommitted | `test_reads_a_finished_direct_build_working__when_its_outside_worktree_holds_uncommitted_work` |
| 039-L12 | slug shape | `prs/<SLUG>.lock.md` in the trusted project; git recorded | `--once <out>` | no git call carries `<SLUG>.lock`; its card is classed `sess intake` | `session-inputs.md`, "a new value gets a named check … and a test that a wrong shape is refused": `BRANCH_SLUG`. A name no branch can have would read "branch gone", so complete | `test_runs_no_git_with_the_slug_and_never_reads_it_complete__when_a_direct_build_is_named_what_no_branch_can_be` |
| 039-L4 | `run.json.accepted` | SLUG done, through intake, worktree a plain unlisted directory, `accepted` set | `sample` | U1 reads `complete` | bound 2, "a session whose `run.json.landed` is set is landed" | `test_reads_a_launched_session_complete__when_run_json_accepted_is_set` |
| 039-L5 | `shell` | as L1, and `build-<SLUG>` live in `shell` with the worktree as cwd | `sample` | U1 reads `working` | bound 2b, "Count `shell` as working too" | `test_reads_a_direct_build_working__when_its_session_is_in_shell` |
| 039-L6 | untrusted | as L1, the repository absent from `repos` (which lists another path); git recorded | `sample` | U1 reads `with the Lead`; no git call runs in the repository or the worktree | bound 1, "through `owner_git`"; U36's gate | `test_never_reads_a_direct_build_complete_nor_runs_git_in_it__when_launch_json_repos_does_not_list_its_repository` |
| 039-L7 | untrusted, torn down | as L6, then torn down | `sample` | U1 reads `with the Lead` | bound 2, "gone from every trusted repo" can only be read where every repository the project names is trusted | `test_never_reads_a_direct_build_complete__when_its_branch_is_gone_only_from_the_repositories_it_may_read` |
| 039-L8 | launched, worktree gone | SLUG done, through intake, `worktree` a path that does not exist; the branch still in the repository, not in main | `sample` | U1 reads `awaiting acceptance` | bound 2, "never infer landed from a missing worktree" | `test_reads_a_launched_session_awaiting_acceptance__when_its_worktree_is_gone_and_its_branch_is_not_in_main` |
| 039-L9 | launched, torn down | as L8 with the branch deleted | `sample` | U1 reads `complete` | bound 2's evidence, applied to a launched session: a session accepted before `run.json.accepted` existed (green at red; owes a kill) | `test_reads_a_launched_session_complete__when_its_worktree_and_its_branch_are_both_gone` |
| 039-L13 | symbolic tip | as L8, `publish.tip` `HEAD` | `sample` | U1 reads `awaiting acceptance` | review 1 F1: read in the main clone, `HEAD` is main; on the repository path only the branch itself is tested | `test_reads_a_launched_session_awaiting_acceptance__when_its_worktree_is_gone_and_its_publish_tip_is_head` |
| 039-L14 | another trusted repository | the branch deleted in the project's repository; `robowright/<SLUG>` unmerged in a second repository only project `other` names, both in `repos`; SLUG done, worktree gone | `sample` | U1 reads `awaiting acceptance` | review 1 F4: the launcher accepts a worktree of any trusted repository, so "gone" is read across every trusted one | `test_reads_a_launched_session_awaiting_acceptance__when_its_branch_lives_in_a_trusted_repository_its_project_does_not_name` |
| 039-L15 | git cannot say | as L9, every `rev-parse` of a `refs/heads/robowright/` ref exiting 128 | `sample` | U1 reads `awaiting acceptance` | review 1 F5: a failure is not "branch gone" (green at red; owes a kill) | `test_reads_a_launched_session_awaiting_acceptance__when_git_cannot_say_whether_the_branch_exists` |
| 039-L16 | worktree on disk | `prs/<SLUG>.md`; the branch in no trusted repository; `build-<SLUG>` idle with its cwd an existing directory no trusted repository lists | `sample` | U1 reads `with the Lead` | review 2 F6: teardown removes the worktree before the branch, so a worktree still on disk was never torn down | `test_reads_a_finished_direct_build_with_the_lead__when_its_session_works_in_a_directory_no_trusted_repository_lists` |
| 039-L17 | broken path elsewhere | as L2, plus a trusted path only project `other` names that is a plain directory (git exits 128) | `sample` | U1 reads `complete` | review 2 F7: only a repository the project names must answer; another trusted one that cannot is read as not holding the branch | `test_reads_a_torn_down_direct_build_complete__when_another_projects_trusted_path_is_no_repository` |
| 039-L10 | no stacking | SLUG done in an outside worktree, its branch not in main; SECOND done in an outside worktree on `robowright/<SECOND>`, at main | `sample` | U1 reads `awaiting acceptance` | bound 2, "keep the number-order stacking rule only where it still holds": it does not — the hook's base for every brief is local `main`, and units are accepted one by one | `test_reads_a_lower_numbered_session_awaiting_acceptance__when_a_higher_numbered_one_is_in_main` |

Red before the dashboard change: L1, L4–L8 and L10, each on its assertion; L11, written after, red with the
branch lookup reverted (`TEST-LEDGER.md`). L2, L3 and L9 pin what the old code already
did and are killed in `TEST-LEDGER.md`.

## 041 · a count line under the index card's bar; no time left at 100%; a robowright.json too deep to read; settings from `robowright.json` only

From U41 (final-trims), a direct build. Bound 5 is U33's Open, option one: the index card's built, queued and intake
segments sit under 3:1 contrast with no text, so the card counts each state on its bar in one line under it, in the
words of the segments' `aria-label`, a state with no unit left out. Complete is counted too, so the line accounts for
every segment drawn. Bound 6: no time left at 100% built. Bound 7: a project `robowright.json` that nests too deeply
for `json.loads` is skipped as an unreadable one is (U36 review 2, G2). Bound 9: U34 deleted R5.4 (the old settings
file); its rule, that settings come only from `robowright.json`, is pinned here through `owner_brief`.

Fixture: launch.json naming both roots. A unit's row is `OLD_HEADER`'s, size S; a finished session sits in a plain
directory no repository lists.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 041-C1 | count line | six units: U1 built (SLUG finished), U2 briefed (SECOND), U3 with the Lead (finished, no INTAKE.md), U4 complete (`run.json.accepted` set), U5 and U6 with no session | `--once <out>` | the index's `sample` card holds, right after its `.track`, `<div class="tally"><span>` reading `1 Complete · 1 Awaiting acceptance · 1 With the Lead · 1 Briefed · 2 Not started` | bound 5: "the same labels as the bar's `aria-label`" (`STATE`'s words, as `track` writes them), "a segment with a count of zero is not listed"; legend order is `LEGEND_ORDER` | `test_counts_each_state_on_the_bar_in_one_line_under_it__in_the_bars_labels__leaving_out_a_state_with_no_unit` |
| 041-T1 | time left | `OLD_ROW` only; SLUG finished (U1 built) | `--once <out>` | `sample.html`'s facts line spans are `[100% built]`, no `about 0h left` | bound 6: "When the project is 100% built, 'about Nh left' is not shown". Below 100% the time left stays: 033-B18 | `test_leaves_the_time_left_off_the_facts_line__when_every_unit_is_built` |
| 041-G1 | deep robowright.json | launch.json's `repos` set; `sample`'s robowright.json an object one of whose keys nests `DEEP_NESTING` arrays; SLUG implementing | `--once <out>` | exit 0, no `Traceback`; `sample.html` written | bound 7: "must not crash … the dashboard"; read as a missing robowright.json, by `project_settings` and by `owner_git.named_repos` | `test_writes_every_page__when_a_projects_robowright_json_is_nested_too_deeply_to_read` |
| 041-S1 | settings file | `sample`'s robowright.json `{}`, and `local.json` beside it `{"owner_brief": true}`; SLUG finished, through intake, no owner brief | `--once <out>` | U1's state begins `Awaiting acceptance`, not held for an owner brief | bound 9: "a settings file under another name sits beside `robowright.json` and is ignored"; U34's deleted R5.4 | `test_ignores_a_settings_file_under_another_name__beside_robowright_json` |

Red before the dashboard change: C1, T1 and G1, each on its assertion. S1 pins what the code already did and is killed in
`TEST-LEDGER.md`. `owner_git`'s half of bound 7 is O36 and O37 in `skills/robowright/scripts/test_owner_git.py`, both
red before the change.

## 043 · the Owner's act is accept

From U43 (accept-rename), a direct build (Owner 2026-10-16). The Owner's act is **accept**, its record
`run.json.accepted`, its event `accept`; a unit in main is **complete**, and one built and through the Lead's intake is
**awaiting acceptance**. The rows above read the new words; their sources quote the briefs of their day. Two readers
change meaning, not only words: the plan's Status cell and the event phrase. The Lead writes the Owner's accept into
the row's Status, so a cell that begins "Accepted" closes the unit as "Done" does. Nothing reads "landed" any more; the
Owner's own records are converted by a migration outside this repository.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 043-D1 | plan Status | `OLD_HEADER` rows U1 Status `**Accepted 2026-10-15 as `0abc123`**`, U2 Status `accepted`; no session | `--once <out>` | `sample.html`'s stage count is `[2 complete]` | brief: "`landed` … → `accepted`", "the plan-Status reader drops the 'landed' prefix"; TERMS.md §4, `unit_progress` | `test_counts_a_plan_row_whose_status_begins_accepted_as_complete` |
| 043-D2 | event phrase | SLUG finished, `run.json.accepted` set; its one event `accept`, done → done | `--once <out>` | SLUG's Details hold one `Latest · ` note, beginning `Latest · Accepted · ` | TERMS.md §4: "`EVENT_PHRASE` gains `accept`" | `test_says_accepted_for_a_sessions_latest_accept_event` |
| 043-D3 | no fallback, run.json | SLUG finished, worktree a plain unlisted directory, `run.json.landed` set and no `accepted` | `sample` | U1 reads `awaiting acceptance` | brief: "No fallback to `landed` or `land` anywhere in the shipped code"; review 1 F1 | `test_reads_a_launched_session_awaiting_acceptance__when_only_the_old_landed_key_is_set` |
| 043-D4 | no fallback, plan Status | `OLD_HEADER` rows U1 Status `**Accepted 2026-10-15 as `0abc123`**`, U2 Status `**Landed 2026-10-15 as `0abc124`**`; no session | `--once <out>` | `sample.html`'s stage count is `[1 of 2 complete]` | brief: "The plan-Status reader drops the 'landed' prefix"; review 1 F1 | `test_counts_a_plan_row_whose_status_begins_landed_as_not_complete` |

Red before the dashboard change: D1 and D2, each on its assertion (`[] != ['2 complete']`; `Latest · accept: done → done`).
D3 and D4 pin the absence of a fallback, so they were green when written; each owes the kill in `TEST-LEDGER.md`.

## 055 · a direct build's accept record; a project's trusted repositories

From U55 (direct-accept), a direct build. `accept.sh --direct` writes `prs/<slug>/ACCEPTED.json` after it integrates a
direct build. Bound 1: a direct build is in main when that record exists **and** its `sha` is an ancestor of main in a
trusted repository its project names **and**, while `robowright/<slug>` is still in any trusted repository, that
commit is on that repository's main and its own diff has the patch-id of the branch's diff, read over the changed
lines only (`-U0`); the project folder is session-writable, so a record alone is not evidence.
Bound 2: a project that names a repository `launch.json`'s `repos` does not list is judged on the ones it does list;
one naming none of them still says nothing (039-L7). 039's Bound 2, "each one its project names is trusted", now
reads "each trusted one its project names". Bound 3: a squash onto a main that moved after the branch
was cut leaves the branch's tree out of main; the record, not tree matching, is the evidence for it.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 055-A1 | record on main | SLUG's worktree on `robowright/<slug>` outside `.worktrees`, a change description; main moved, then a cherry-pick of the branch; `ACCEPTED.json` `sha` that pick | `sample` | U1 reads `complete` | brief A5, A7 | `test_reads_a_direct_build_complete__when_its_accept_record_names_a_commit_on_main` |
| 055-A2 | record off main | as A1, `sha` the branch tip | `sample` | U1 reads `with the Lead` | brief A5: "a record alone is not evidence" | `test_reads_a_direct_build_with_the_lead__when_its_accept_record_names_a_commit_not_on_main` |
| 055-A3 | record out of shape | as A1, `sha` the word `main` | `sample` | U1 reads `with the Lead` | brief A5; session-inputs rule (commit id) | `test_reads_a_direct_build_with_the_lead__when_its_accept_record_names_no_commit_id` |
| 055-A4 | trusted subset | torn down (worktree removed, branch deleted); `robowright.json` also names an existing directory `repos` does not list | `sample` | U1 reads `complete` | brief A6: "decide from its trusted ones instead of returning None" | `test_reads_a_torn_down_direct_build_complete__when_its_project_also_names_an_untrusted_repository` |
| 055-A5 | record on main, not the change | as A1, `sha` main's own commit before the pick; the branch still there | `sample` | U1 reads `with the Lead` | Bound 1: the record is checked against the branch while it exists (review 1 F2) | `test_reads_a_direct_build_with_the_lead__when_its_accept_record_names_a_commit_on_main_that_is_not_its_change` |
| 055-A7 | record under a name no branch can have | `prs/sample-001-first.lock.md` and `prs/sample-001-first.lock/ACCEPTED.json` naming main's tip | `--once <out>` | its card is `sess intake` | session-inputs rule (review 1 F4) | `test_never_reads_an_accept_record_complete__when_a_direct_build_is_named_what_no_branch_can_be` |
| 055-A8 | the branch checked wherever it is | the project names two trusted repositories; the branch, unaccepted, in the first; `ACCEPTED.json` names the second's main tip | `sample` | U1 reads `with the Lead` | brief A5: "a record alone is not evidence" (review 3 F2) | `test_reads_a_direct_build_with_the_lead__when_its_accept_record_names_another_repositorys_main` |
| 055-A9 | … in a trusted repository the project does not name | the branch, unaccepted, in a trusted repository the project does not name; the project names another trusted repository; `ACCEPTED.json` names its main tip | `sample` | U1 reads `with the Lead` | as A8 | `test_reads_a_direct_build_with_the_lead__when_its_branch_is_in_a_trusted_repository_its_project_does_not_name` |
| 055-A10 | an edit beside the change | `notes.txt` at the branch's base; the branch edits line 6, main line 3; main gains a squash merge of the branch, named by `ACCEPTED.json`; the branch still there | `sample` | U1 reads `complete` | brief A5, A7 (`DECISIONS.md:4546`); assumed: patch-id compares changed lines, not context (review 3 F3) | `test_reads_a_direct_build_complete__when_main_edited_beside_its_change_before_the_accept` |

Red before the dashboard change: A1 and A4, each on its assertion (`'complete' not found in '… with the Lead · 001'`);
after review 1, A5 (`'with the Lead' not found in '… complete · 001'`) and A7 (`'complete' != 'intake'`).
A2 and A3 were green when written, since nothing landed a direct build; each owes the kill in `TEST-LEDGER.md`.
After review 3, A8 and A9 (`'with the Lead' not found in '… complete · 001'`) and A10 (`'complete' not found in '…
with the Lead · 001'`). A9's first fixture named its branch's repository in no project, so it was not trusted; with a
second project naming it, A9 is red on the code before the fix and green after.

## 056 · a session folder nothing launched reads Briefed, not Working

From U56 (briefed-tone), a direct build. A session folder the Planner briefed and nothing launched stores
`phase = preflight`, as a running preflight does (`skills/robowright/state-machine.json`, state `briefed`). The
dashboard reads it through the state tool's `never_launched()`: the `briefed` state, no live session for it, no
`session_id`, no `transcripts`, no `started_at`, and nothing in `events.jsonl`. Rows sourced `Assumed (Q1)` take the
brief's `session` as `session_id` and `transcripts` (what the launcher pins) and its `launched_at` as `started_at`
(what `preflight-pass` stamps): neither key the brief names exists in any writer.

Fixture: `sample-001-first` with `phase = preflight`, units `U1` and `U2` todo, `session_id` and `started_at` empty,
no `events.jsonl`, `worktree` the scratch cwd, every file last written 45 minutes ago, past `STUCK_MINUTES`.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 056-D1 | never launched | the fixture, no live agent | `--once <out>` | the index's Needs attention lists it `Briefed · ready to launch` | brief B3: "reads tone `briefed` … groups where the dashboard puts work waiting on the Owner's launch line" | `test_lists_the_session_briefed_and_ready_to_launch__when_nothing_ever_launched_it` |
| 056-D2 | … never Stuck? | as D1 | `--once <out>` | no page carries `Stuck?` | brief B3: "never Working, never 'Stuck?'" | `test_never_reads_the_session_stuck__when_nothing_ever_launched_it` |
| 056-D3 | … not In flight | as D1 | `--once <out>` | the index's In flight list has no row for it | brief B3: "not under In flight" | `test_lists_no_in_flight_row__when_nothing_ever_launched_the_session` |
| 056-D4 | preflight running | as D1, plus a busy live agent whose cwd is the session's worktree | `--once <out>` | its card label reads `Working` | brief B1: "A briefed session with a live session (preflight running) … is not unlaunched" | `test_reads_the_session_working__when_a_live_session_runs_its_preflight` |
| 056-D5 | a launch that died in preflight | as D1, `session_id` a session UUID (the launcher's pin), no live agent | `--once <out>` | its card label reads `Working`, not `Briefed` | brief B1: "with `launched_at` set and no live session (a launch that died in preflight) is **not** unlaunched"; Assumed (Q1) | `test_reads_the_session_working__when_a_launch_pinned_it_and_died_in_preflight` |

Red before the code: D1 (`'Briefed · ready to launch' not found in ''`), D2 (`2 != 0`, two `Stuck?` on the pages),
D3 (`['sample.html#s-sample-001-first'] != []`). D4 and D5 were green at red; their kills are in `TEST-LEDGER.md` → 056.

## 052a · a session parked before it launched

From U52a (final-fixes-a), a direct build. `park` also leaves `briefed` (Owner, 2026-10-18), and the `parked` record's
`from` then reads `briefed`. The card's now line for a parked session reads `Parked in <unit> of <n>`, which would
place a session that never started mid-brief; for `from: briefed` it reads `Parked before launch`.

Fixture: project `sample`; SLUG with `phase = parked`, units `U1` and `U2` todo, `parked = {by: owner, reason, at,
from: briefed, released: []}`.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 052a-D1 | parked before launch | the fixture | `--once <out>` | SLUG's now line reads `Parked before launch`; the index's Needs attention does not list SLUG | REPLAN U52a → A: "when `parked.from` is `briefed` it reads "Parked before launch""; "a parked briefed session leaves Needs attention" | `test_says_parked_before_launch__for_a_session_parked_from_briefed` |

## 052b · a robowright.json read without following a link or waiting on a FIFO

From U52b (final-fixes-b), a direct build. B3: the dashboard's `project_settings` and `owner_git.named_repos`
read a project's `robowright.json` through `owner_git.read_unlinked`, which a Planner or a granted Worker can make a
link or a FIFO. A refused read is what an unreadable file was: `{}` for the dashboard, the folder skipped for
`named_repos`.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 052b-R1 | linked settings | `sample`'s robowright.json a symlink to a file outside the project holding `{"owner_brief": true}`; SLUG finished, through intake, no owner brief | `--once <out>` | U1's state begins `Awaiting acceptance`, not held for an owner brief | briefing B3: "the dashboard reads `{}`" for a refused read | `test_ignores_a_robowright_json_that_is_a_link__to_a_file_outside_the_project` |
| 052b-R2 | FIFO settings | launch.json's `repos` set; `sample`'s robowright.json a FIFO; SLUG implementing | `--once <out>`, under a 20 s timeout | exit 0 within the timeout; `sample.html` written | briefing B3: denial of service only | `test_writes_every_page_at_once__when_a_projects_robowright_json_is_a_fifo` |

## 057 · a direct build shown beside a session folder with no run.json

From U57 (direct-build-shown), a direct build. A brief-only Planner launch makes `<sessions_root>/<unit>/` before it
chooses a direct build, and leaves the folder holding only its ledger. `direct_builds` skipped every unit with a folder
under the sessions root, so the build behind such a folder never showed, running or finished. Only a folder holding a
`run.json` now hides a direct-build row; a direct build with a live session replaces the briefing row for its unit.

Fixture: project `sample`, U1 `first`; SLUG's folder under the sessions root as the Planner leaves it, with no run.json.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 057-D1 | running, folder | the fixture, no Planner; `worker-sample-001-first` busy | `--once <out>` | SLUG's row draws a Worker; the crew card says `direct build` | briefing B1: "a folder with no `run.json` never hides a direct build, running"; as 029-U1.2.11 and 029-U2.5.16 | `test_shows_the_running_direct_build__when_its_unit_has_a_folder_with_no_run_json` |
| 057-D2 | running, folder, Planner | the fixture; `planner-sample-001-first` busy; `worker-sample-001-first` busy | `--once <out>` | one row for SLUG, drawing a Worker; the crew card says `direct build`; no page says `Planner briefing` | briefing B2: "the dashboard shows the direct build's row and not the briefing row: the build is the later fact" | `test_shows_one_row_the_direct_builds__when_a_planner_is_alive_for_the_folder` |
| 057-D3 | running, run.json | SLUG implementing (a run.json); `worker-sample-001-first` busy | `--once <out>` | one row for SLUG, the session's: the crew card does not say `direct build` | briefing B1: "a folder with a `run.json` still excludes a direct-build row for its unit, as today" | `test_shows_only_the_sessions_row__when_the_units_folder_holds_a_run_json` |
| 057-D4 | finished, folder | the fixture, no Planner; SLUG's change description in `prs/`, its Worker idle in a worktree no main holds | `robowright-dash.py sample` | U1 reads `with the Lead` | briefing B1: "or finished (`prs/<slug>.md`)"; as 039-L1 | `test_reads_the_finished_direct_build_with_the_lead__when_its_unit_has_a_folder_with_no_run_json` |

## 065 · a session with no ticket

From U65 (parked-fixes), a direct build. Where `launch.json` names a ticket shape, a session may now carry no ticket;
its unit id is then its directory's name, as the launcher reads it. `ticket_of` returns that unit id, so the ticket
claim and the spend card read a ticket-less session as they read any other.

Fixture: project `sample` planning `| U1 | \`export-csv\` | Exports notes as CSV | … |`; a bare-slug session dir
`export-csv` implementing, `ticket` null, `project` `sample`, a dollar limit (DOLLAR_BRIEF); `records.jsonl` holding
two session records whose `unit` is `export-csv` and one whose `unit` is `sample-001-first`.

| # | Area | Given | When | Then | Source | Test |
|---|---|---|---|---|---|---|
| 065-T1 | no ticket, bare slug | the fixture | `--once <out>` | U1's state links `export-csv`; the `export-csv` card's spend line sums the two `export-csv` records only | the U65 note: a ticket-less session shows in each reader as its unit id, the directory name; 023-U2-B4.1, U2-R2.1 | `test_claims_and_prices_a_session_with_no_ticket__by_its_directory_name` |
