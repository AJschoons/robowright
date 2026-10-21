# Plan-usage tap, reader and guard — behaviour table

Written before the code, from the usage-tap brief (2026-09-21) and the
status-line doc (https://code.claude.com/docs/en/statusline.md, read 2026-09-21). `Assumed` rows
are defaults taken unattended; each one changes a Then if the Owner answers otherwise.

Paths: `$CLAUDE_USAGE_DIR` (default `~/.claude/usage`) holds `latest.json`;
the sessions root holds the Robowright Sessions: `usage-guard --runs-root <dir>` (repeatable), else
`$ROBOWRIGHT_SESSIONS_ROOT`, else `sessions_root` in `~/.claude/robowright/launch.json` — no default;
with none of them the guard refuses by name (G7).

## Tap — `skills/robowright/scripts/usage-tap.py` (statusLine.command)

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| T1.1 | records every present window | 5h 23.5% resets R1, 7d 41.2% resets R2, session s1 | the tap runs | latest.json holds both windows' pct and resets_at, session_id s1, captured_at within 5s of now | brief, Deliverable 1 |
| T1.2 | a missing window is not invented | only 7d 41.2% | the tap runs | latest.json has seven_day and no five_hour | doc: "each window may be independently absent" |
| T2.1 | no rate_limits leaves the file alone | a prior latest.json | the tap runs on input with no rate_limits | latest.json byte-identical | brief: "leaves the previous file untouched" |
| T3.1 | a re-render with no new API response does not refresh the stamp | session s1 wrote at api_duration 2300; latest.json then back-dated 20 min | s1 runs again with api_duration 2300 | latest.json unchanged | Assumed: the doc lists re-run triggers with no API call (permission mode, a passed `resets_at`, `refreshInterval`); re-stamping those would pass stale numbers off as fresh |
| T3.2 | a new API response does refresh it | as T3.1 | s1 runs with api_duration 2900 | captured_at within 5s of now | brief, Deliverable 1 |
| T4.1 | prints one short line | Opus, context 34%, 5h 23.5%, 7d 41.2% | the tap runs | stdout is exactly one line containing `Opus`, `34%`, `5h 24%`, `7d 41%` | brief lists the four fields; Assumed: whole percents, `5h`/`7d` labels |
| T4.2 | absent windows print as `--` | no rate_limits | the tap runs | line contains `5h --` and `7d --` | Assumed |
| T5.1 | never errors visibly | stdin is not JSON | the tap runs | exit 0, one non-empty line, no stderr, no latest.json | brief: "never errors visibly, always exits 0" |
| T5.2 | a write failure is swallowed | CLAUDE_USAGE_DIR is a regular file | the tap runs with rate_limits | exit 0, the line printed, no stderr | brief, same |

## Reader — `claude-usage`

Exit codes (Assumed numbering; the brief asks only that they are distinct): 0 ok · 1 over
threshold · 2 usage error (argparse's own) · 3 stale · 4 missing.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| U1.1 | prints pct, local reset time and age | fresh: 5h 23.5% resets 2100-01-01 00:00 UTC, TZ=UTC | `claude-usage` | exit 0; output has `23.5%`, `2100-01-01 00:00`, and `age` | brief, Deliverable 2 |
| U2.1 | `--json` for scripts | as U1.1 | `--json` | JSON with `state: ok`, `windows.five_hour.used_percentage 23.5`, `age_seconds` a number | brief |
| U3.1 | at the threshold is over | fresh 5h 90.0 | `--check 90` | exit 1 | brief: "at or above" |
| U3.2 | just under is ok | fresh 5h 89.9, 7d 10 | `--check 90` | exit 0 | brief |
| U3.3 | any window counts | fresh 5h 10, 7d 95 | `--check 90` | exit 1 | brief: "any window" |
| U4.1 | stale is never "under" | 5h 10 captured 16 min ago | `--check 90` | exit 3, output says stale | brief: default 15 min; stale never reported as under |
| U4.2 | stale wins over over | 5h 95 captured 16 min ago | `--check 90` | exit 3 | brief: the guard acts only on fresh data |
| U4.3 | the age is a flag | 5h 10 captured 16 min ago | `--check 90 --max-age 30` | exit 0 | brief: "flag-set age"; Assumed: minutes |
| U5.1 | missing file | no latest.json | `--check 90` | exit 4 | brief |
| U5.2 | an unreadable file counts as missing | latest.json is `{not json` | `claude-usage` | exit 4 | Assumed |
| U6.1 | a window past its reset is not counted | fresh; 5h 95 reset 1 min ago; 7d 40 | `--check 90` | exit 0 | Assumed, from the doc: Claude Code drops a window once `resets_at` passes |
| U6.2 | nothing current left is stale, not ok | fresh; only 5h 40, reset 1 min ago | `--check 90` | exit 3 | Assumed; brief: never "under" without data |

## Guard — `usage-guard`

Non-terminal = `run.json` `phase` is anything but `done` (`robowright/STATES.md`: only `done`
is terminal; `stopped` is resumable). A directory without a readable `run.json` is not a Robowright
Session. Exit codes match the reader's.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| G1.1 | STOP into every non-terminal session | fresh 5h 91; sessions A implement, B stopped, C done | `--once` | A and B have STOP; C has none; exit 1 | brief, Deliverable 3 |
| G1.2 | the STOP is one line naming window, pct, reset | as G1.1, TZ=UTC, 5h resets 2100-01-01 00:00 UTC | `--once` | A/STOP is one line containing `five_hour`, `91`, `2100-01-01 00:00` | brief |
| G1.4 (held out) | every window over is named | fresh 5h 92, 7d 96 resets 2099-12-31 23:00 UTC | `--once` | the STOP line names both windows, both pcts, both resets | brief: the line names "the window"; Assumed: all of them when two are over |
| G1.3 | at the threshold is over | fresh 5h 90.0; A implement | `--once` | A has STOP | brief |
| G2.1 | never overwrites a STOP | A already has STOP `the Owner's own` | `--once` at 5h 95 | A/STOP still reads `the Owner's own` | brief: idempotent |
| G3.1 | under writes nothing | fresh 5h 89, 7d 50; A implement | `--once` | no STOP; exit 0 | brief |
| G3.2 | the threshold is a flag | fresh 5h 85; A implement | `--once --threshold 80` | A has STOP | brief |
| G4.1 | stale writes nothing and warns | 5h 95 captured 16 min ago; A implement | `--once` | no STOP; output has `stale`; exit 3 | brief |
| G4.2 | missing writes nothing and warns | no latest.json; A implement | `--once` | no STOP; output has `missing`; exit 4 | brief |
| G5.1 | a directory that is not a session is skipped | a dir with no run.json | `--once` at 5h 95 | no STOP there | Assumed |
| G6.1 | `--watch` acts when usage crosses between polls | 5h 50; A implement | `--watch 1`, then latest.json rewritten to 5h 95 | A has STOP within 5 s | brief: `--watch <seconds>` |

### Guard — the sessions root

Written before the code, from the onboarding brief (2026-09-25: decisions D3 and D4, rules R1 and R2).
An empty `$ROBOWRIGHT_SESSIONS_ROOT` is absent; an empty or non-string `sessions_root` is absent.
launch.json's root is read as the launcher reads it (`run-launch.sh:358`): a leading `~/` is `$HOME`
followed by everything after the `~`; a bare `~` or `~user/…` is read as written, against the cwd.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| G7.1 | `--runs-root` wins | fresh 5h 95; a session under each of the flag root, the env root, and launch.json's `~/file-root` | `--once --runs-root <flag root>` | STOP in the flag root's session only | brief R1: "with `--runs-root <dir>` uses that dir"; D3 |
| G7.2 | `--runs-root` is repeatable | fresh 5h 95; a session under each of two roots | `--once --runs-root <a> --runs-root <b>` | STOP in both | D3: "`--runs-root` (repeatable)" |
| G7.3 | the env root wins over launch.json | fresh 5h 95; a session under the env root and under launch.json's root | `--once` | STOP under the env root only | brief R1: "with none, `$ROBOWRIGHT_SESSIONS_ROOT`" |
| G7.4 | launch.json's `sessions_root` is read | fresh 5h 95; no flag, no env; launch.json names an absolute root; a session there and one at the old default `~/Projects/robowright-sessions` | `--once` | STOP under launch.json's root; none at the old default | brief R1: "with neither, `launch.json`'s `sessions_root`"; D3: the default "is deleted" |
| G7.5 | an empty env var is absent | fresh 5h 95; env root `""`; launch.json names a root; a session in the cwd | `--once` | STOP under launch.json's root; none in the cwd | brief R1: "an empty env var is absent" |
| G7.6 | nothing configured is a refusal by name | 5h 100; no flag, env or launch.json; a session at the old default and one in the cwd | `--once` | exit 2; stderr is one line naming launch.json, `ROBOWRIGHT_SESSIONS_ROOT` and `--runs-root`; no STOP anywhere | brief R1: "exits 2 and writes no `STOP` — even at 100% usage"; D3. Assumed: launch.json named as `~/.claude/robowright/launch.json` or `$HOME` expanded — either names the file |
| G7.7 | an empty env var with no launch.json refuses | 5h 100; env root `""`; a session in the cwd | `--once` | as G7.6's refusal; no STOP in the cwd | brief R1: "an empty env var is absent" |
| G7.8 | an empty `sessions_root` refuses | 5h 100; `sessions_root: ""`; a session in the cwd | `--once` | as G7.6's refusal; no STOP | brief R1: "an empty … `sessions_root` is absent" |
| G7.9 | a non-string `sessions_root` refuses | 5h 100; `sessions_root` 5, a list, null, an object | `--once` | as G7.6's refusal, each | brief R1: "non-string `sessions_root` is absent" |
| G7.10 | a launch.json that does not parse refuses | 5h 100; launch.json is `{"sessions_root": "~/x",` | `--once` | as G7.6's refusal (so no traceback) | D3: "the shape at `spend-guard.py:197-228`" — an unreadable file gives no root |
| G7.11 | `--watch` refuses once | 5h 100; nothing configured | `--watch 1` | exits within 10 s with G7.6's refusal | brief R1's refusal is not limited to `--once`; D3 "exit 2" |
| G7.12 | a configured root that does not exist holds no sessions | fresh 5h 95; launch.json names a dir not created | `--once` | exit 1 (over); no traceback | brief hotspot: "a root that does not exist must yield no sessions and no traceback"; exit 1 is "at or over" (`usage-guard:17`) |
| G7.13 | `--help` says the new precedence | nothing configured | `--help` | exit 0; names `--runs-root`, `ROBOWRIGHT_SESSIONS_ROOT`, `launch.json`, `sessions_root`; not `Projects/robowright-sessions` | D3: "`usage-guard:15` … say the new precedence"; the default "is deleted" |
| G7.14 | a launch.json that cannot be read refuses | 5h 100; launch.json is a directory; a session in the cwd | `--once` | as G7.6's refusal (so no traceback); no STOP in the cwd | D3: "the shape at `spend-guard.py:197-228`", whose reader the Lead's R5.4 pins; added 2026-09-26 (PLAN-REVIEW §4 item 4) |
| G7.15 | a launch.json that is not an object refuses | 5h 100; launch.json is `[]`; a session in the cwd | `--once` | as G7.6's refusal (so no traceback); no STOP in the cwd | D3, as G7.14; the Lead's R5.5; added 2026-09-26 (PLAN-REVIEW §4 item 4) |
| G8.1 | `~//abs` is `$HOME/abs` | fresh 5h 95; `sessions_root: "~//abs"`; a session at `$HOME/abs/sample-001-x` | `--once` | STOP there | brief R2; D4: "`~//abs` names the directory `$HOME/abs`" |
| G8.2 | `~/abs` is `$HOME/abs` | as G8.1 with `"~/abs"`; a session at `<cwd>/~/abs` too | `--once` | STOP at `$HOME/abs`'s session only | brief R2: "The same four with `~/abs` behave the same"; D4 |
| G8.3 | a bare `~` is read as written | fresh 5h 95; `sessions_root: "~"`; a session in `$HOME` and one in `<cwd>/~` | `--once` | STOP in `<cwd>/~`'s only | D4: "Bare `~` … stay read as written" |
| G8.4 | `~user/abs` is read as written | fresh 5h 95; `sessions_root: "~root/abs"`; a session at `<cwd>/~root/abs` | `--once` | STOP there | D4: "`~user/x` stay read as written" |
