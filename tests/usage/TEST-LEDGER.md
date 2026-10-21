# Plan-usage tap, reader, guard — test ledger

Rows in `BEHAVIORS.md`. Every mutation below was a literal text replacement applied to the tree,
the whole suite run, and the file restored; `git status` was clean after the pass. Predictions
were written before the run. Run 2026-09-21.

Run: `python3 tests/usage/test_usage.py` (about 4 s)

Red at the skeleton step (constant exits, no writes): 26 of 30 failed on their Thens. Green at
red, so each owed a kill first: T2.1, T3.1, G2.1, G5.1 — killed by M1, M2/M3, G3, G9.

| # | file | mutation | predicted | observed |
|---|---|---|---|---|
| M1 | tap | write even with no windows | T2.1 | match |
| M2 | tap | the unchanged-API-time guard is `if False` | T3.1 | match |
| M3 | tap | the per-session mark is never written | T3.1 | match |
| M4 | tap | an absent window becomes `{used_percentage: 0}` | T1.2 | match |
| M5 | tap | `resets_at` recorded as null | T1.1 | match |
| M6 | tap | `session_id` dropped | T1.1 | match |
| M7 | tap | `captured_at` 20 min early | T1.1, T3.2 | match |
| M8 | tap | percent truncated, not rounded | T4.1, T5.2 | match |
| M9 | tap | absent window prints `0%` | T4.2 | match |
| M10 | tap | bad input prints an empty line | T5.1 | match |
| M11 | tap | a write failure re-raised | T5.2 | match |
| M12 | tap | model name hardcoded | T4.1 | match |
| M13 | tap | context percent hardcoded `--` | T4.1 | match |
| R1 | reader | a passed reset never counts as reset | U6.1, U6.2 | match |
| R2 | reader | `>=` → `>` threshold | U3.1, G1.3 | match |
| R3 | reader | age no longer makes a reading stale | U4.1, U4.2, G4.1 | match |
| R4 | reader | no current window is not stale | U6.2 | match |
| R5 | reader | `--max-age` ignored | U4.3 | match |
| R6 | reader | a parse error is not caught | U5.2 | match |
| R7 | reader | missing reported as stale | U5.1, G4.2 | wider: also U5.2 — the same return serves a corrupt file |
| R8 | reader | percent left out of the text | U1.1 | match |
| R9 | reader | reset time loses `%H:%M` | U1.1, G1.2, G1.4 | match |
| R10 | reader | `age` label renamed | U1.1 | match |
| R11 | reader | `stale:` label renamed | U4.1 | match |
| R12 | reader | `age_seconds` a string | U2.1 | wider: every text-mode test — `describe_age` compares the string and raises |
| R13 | reader | over checked before stale | U4.2, G4.1 | match |
| R14 | reader | only the 5-hour window read | U3.3 | wider: also G1.4, U6.1 (both read the weekly window); U3.3 confirmed by subtest label |
| R15 | reader | threshold − 1 | U3.2 | wider: also G3.1 (89 ≥ 89); U3.2 confirmed by subtest label |
| G1 | guard | stopped sessions skipped | G1.1 | match |
| G2 | guard | done sessions included | G1.1 | match |
| G3 | guard | STOP opened `w`, not `x` | G2.1 | match |
| G4 | guard | reset time dropped from the STOP line | G1.2, G1.4 | match |
| G5 | guard | only the first window over named | G1.4 | match |
| G6 | guard | default threshold 80 | G3.1 | match |
| G7 | guard | `--threshold` not passed to the reader | G3.2 | match |
| G8 | guard | `--watch` reads once, then only sleeps | G6.1 | match |
| G9 | guard | a dir without run.json treated as a session | G5.1 | match |
| G10 | guard | missing warning reworded | G4.2 | match |
| G11 | guard | STOP never written | G1.1, G1.2, G1.3, G1.4, G3.2, G6.1 | match |
| G12 | guard | stale returns 0 | G4.1 | match |

No survivors, no over-predictions. Four wider-than-predicted, each explained above.

## The sessions root — G7, G8 (run 2026-09-25)

Red at the skeleton step (`--runs-root` accepted and ignored): 15 of 17 failed on their Thens.
Green at red: G7.3, G7.12 — killed by S5, S12. Rounds were batches with disjoint predictions.

| # | file | mutation | predicted | observed |
|---|---|---|---|---|
| S1 | guard | `--runs-root` ignored | G7.1, G7.2 | match |
| S2 | guard | an empty `$ROBOWRIGHT_SESSIONS_ROOT` counts as set | G7.5, G7.7 | match |
| S3 | guard | a launch.json parse error is not caught | G7.10 | match |
| S4 | guard | only `~//` expanded, not `~/` | G8.2 | match |
| S5 | guard | launch.json read before the env var | G7.3 | match |
| S6 | guard | `sessions_root` not checked for a string | G7.9 (5, list, dict) | match |
| S7 | guard | the refusal applies to `--once` only | G7.11 | match |
| S8 | guard | docstring names the old default | G7.13 | match |
| S9 | guard | `~/` joined as a path (`/abs` drops `$HOME`) | G8.1 | match |
| S10 | guard | every other root through `expanduser` | G8.3, G8.4 | match |
| S11 | guard | the refusal exits 0 | G7.6–G7.11 | match |
| S12 | guard | a literal absolute `sessions_root` refused | G7.4, G7.5, G7.12 | match |

No survivors, no over-predictions.

## launch.json unreadable, not an object — G7.14, G7.15 (run 2026-09-26)

Written after the code, so green at red: each owed a kill first, K1 and K2. One mutation per run.

| # | file | mutation | predicted | observed |
|---|---|---|---|---|
| K1 | guard | the `isinstance(settings, dict)` check dropped | G7.15 | match |
| K2 | guard | the except swallows only `ValueError` | G7.14 | match |

No survivors, no over-predictions.

## Accepted untested

- **Atomic replace** (temp file + `os.replace`) in the tap. No seam shows a torn read from a
  single-process test; `os.rename` is equivalent on one filesystem. Protects the guard from
  parsing a half-written file when two sessions render at once.
- **The real status-line contract** — that Claude Code sends `rate_limits` and
  `cost.total_api_duration_ms` as documented. Measured once by hand (see the report), not
  tested.
- **G7.12's own claim** — no traceback on a missing root — is killed only by S12, which refuses
  the root instead. Declared guard against `open_sessions` listing the root with `os.listdir`.
