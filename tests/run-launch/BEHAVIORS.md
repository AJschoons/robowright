# run-launch — behaviour table

Twelve tests carried over from an earlier launcher suite, whose subject the session-state suite
beside the launcher does not pin. Source of each expected value: the earlier test's own docstring
(the rule) and the launcher's text at the base (the literal it prints). Five tests there are not
here: each asserted one machine's configuration, not the launcher.

Every test runs against a scratch HOME whose `launch.json` is synthetic: `sessions_root`
`~/sessions` (so the `~/` expansion runs on every test), no ticket shape, `launch` `auto`.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R1.1 | a resume re-invokes the worker skill | an implementing session with a `session_id` | `--resume --dry-run` | the command reads `--resume <id> /worker <session dir> Resume this Robowright Session:` | earlier docstring; `RESUME_PROMPT_*` opener |
| R2.1 | the project's settings file outranks the profile, and a flag outranks the file | `robowright.json` models.planner = sonnet | `--brief --slug sample-003-z --dry-run`, then with `--model haiku` | `model:     sonnet (from robowright.json)`, then `model:     haiku (from flag)` | earlier docstring |
| R2.2 | the report prompt names the manual smoke pass | a project | `--explainer report --dry-run` | the output carries `smoke/MANUAL-PASS.md` | earlier docstring |
| R3.1 | a STOP file refuses a Worker launch | a launchable session with `STOP` | `--dry-run` | exit 1, `STOP exists`; exit 0 once `STOP` is gone | earlier docstring |
| R3.2 | a live session in the worktree refuses the launch; a dead one does not | a registry entry whose cwd is the worktree, pid live, then pid reaped | `--dry-run` | exit 1, `a live Claude session is already in <worktree>`; exit 0 with the dead pid | earlier docstring |
| R3.3 | the worktree must be a linked worktree | run.json names the main clone | `--dry-run` | exit 1, `never the main clone` | earlier docstring |
| R3.4 | `--compact-pct` is a whole percentage in 10–100 | a launchable session | `--compact-pct fifty`, `50%`, `9`, `101`, `10`; run.json `compact_pct: "lots"` | the first two and the last refused `must be a whole number of percent`; `9`, `101` refused `must be between 10 and 100`; `10` plans with `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=10` | earlier docstring |
| R3.5 | `--stop-cap` is a whole number, at both sites | a launchable session; a project | `--stop-cap forty`, `60`; a brief with `forty` | `forty` refused `must be a whole number` at both sites; `60` plans `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=60` | earlier docstring |
| R3.6 | a launch writes the session marker; a plan does not | a launchable session | `--dry-run`, then `--yes` | no marker after the plan; `<worktree>/.claude/autonomous-run` holds the session dir after the launch | earlier docstring |
| R4.1 | the plan names the file the entry goes to | a project | `--explainer report` dry run and `--yes`; `--brief` dry run | report: `ledger:    <project>/DECISIONS.md`, no `LEDGER.md` anywhere, `DECISIONS.md` gains `launched`; brief: `ledger:    <root>/sample-003-z/LEDGER.md` | earlier docstring |
| R4.2 | a dry run does not claim an entry was appended | a launchable session; a project | Worker and brief, `--dry-run` then `--yes` | `(dry run: nothing appended)` and no `LEDGER.md` on the plan; `(one entry will be appended)` and a `via run-launch.sh` entry on the launch | earlier docstring |
| R4.3 | a resume records the id it resumed | U1 on opus, U2 on sonnet, a `session_id` | launch, close U1, stop, resume, `--resume --yes` | `- session name: worker-opus-sample-001-x` on the launch; `model:     sonnet Worker (from unit U2)` and `- resumed session: <id>` on the resume; no `worker-sonnet-sample-001-x` | earlier docstring |

## The launch mode

`launch.json`'s `launch` key through the stub. These four rows take their source from the brief's
decisions, not the launcher's text; the config reading itself (the absent-key default, the refusals, the plan's `launch:` line,
`--pin`) is pinned by the session-state suite's `LaunchConfigTests`. Each test switches the
synthetic fixture's `launch` to the mode its row names.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R5.1 | `auto` runs the command the plan printed | a launchable session, `launch` `auto` | `--yes` | the stub is called once with exactly the words of the plan's `command:` line after `claude`; `started. attach:`; no `hand-off via` entry | brief Goal: "`auto` is today's behaviour"; the plan-equals-argv form is assumed (Q9), and holds before the key exists |
| R5.2 | `paste` hands off that same command, unrun | a launchable session, `launch` `paste` | `--yes` | the stub is never called; the paste line is `cd <worktree> && [ "$(pwd -P)" = <worktree> ] && ` then words starting `env -u CLAUDECODE` and ending with exactly the plan's `command:` words | brief D2: "`paste` is the EPERM hand-off with the `claude` call skipped" |
| R5.3 | an EPERM under `auto` is a hand-off whose hint names no settings key, Worker site | a launchable session, `launch` `auto`, a stub failing with EPERM | `--yes` | exit 0 ending `launch is yours`; stderr has `hint: this shell could not start a background session; see the machine profile's Launch section, or set "launch": "paste" in <launch.json>`; no `excludedCommands`, no `sandbox`; one `- EPERM; nothing started` line; no `launch: paste` | brief D3: the hint "says the shell could not start a background session and points at the profile → Launch, or at `"launch": "paste"`"; the words are assumed (Q5) |
| R5.4 | the same, document-only site | a project, `launch` `auto`, the EPERM stub | `--planner brief --slug sample-003-z --yes` | exit 0 ending `launch is yours`; the same hint line; no `excludedCommands`, no `sandbox`; the session ledger has `EPERM; nothing started` and no `launch: paste` | brief D3 (both hint lines change) |

Assumed, with the default taken:

- Q5 — the hint's words: the line above, on stderr where the old hint went.
- Q9 — "the same argv as before the key existed" is pinned as "the argv the plan printed"; the
  byte-identity with the earlier launcher is carried by every earlier launch test passing with only
  the fixture's `launch: auto` added.

## The project after a launch and on `--pin` (accounting polish P2)

`run.json.project` is the `group_regex` capture of the unit id (accounting D8). These rows come from
the polish contract (PLAN-REVIEW §6 P2), quoted in the session's `evidence/P2-behaviors.md`, which
also holds the planned mutation per test. `--pin` rows run under `launch` `paste` with the pasted
session registered in the worktree; the capture-less regex is `^[a-z][a-z0-9-]*$`.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| P2.0 | a paste hand-off writes no project | `paste`, `project` null | `--yes` | exit 0; `project` null | C2 "A paste hand-off itself still writes nothing"; existing `ProjectTests` row |
| P2.1 | a pin writes the capture when `project` is null | ticket `sample-013-ledger`, `project` null | `--pin cccc3333` | exit 0; `project` `sample` | C1 "writes `run.json.project` when null, from the same `match_group "$UNIT_ID"` capture" |
| P2.2 | a pin leaves a set project alone | `project` `demo` | `--pin cccc3333` | `project` `demo` | C1 "leaves a set value alone" |
| P2.3 | a unit id outside `group_regex` still pins, project null | `group_regex` `^(other)-…` | `--pin cccc3333` | exit 0; `session_id` pinned; `project` null | C1; the Worker site's no-match rule (assumed U1 Q15) |
| P2.4 | a capture-less regex still pins, project null | the capture-less regex | `--pin cccc3333` | exit 0; `session_id` pinned; `project` null | Assumed P2 Q1: soft, as the post-launch captures |
| P2.5 | a pin dry run writes no project | `project` null | `--pin cccc3333 --dry-run` | exit 0; `would pin`; `project` null | the dry-run line: "…; nothing written" |
| P2.6 | a Worker launch under a capture-less regex finishes as before | `auto`, ticket `sample-013-ledger`, `project` null | `--yes` | exit 0; `started. attach: claude attach bbbb2222`; a `## … — launch via run-launch.sh` entry; `project` null | C3 "leaves `project` null and the launcher exits as it did at base (launch entry written, `started.` line printed)" |
| P2.7 | …and still writes its launch index line | as P2.6 | `--yes` | one line: `worker`, the started id, `project` null, `unit` `sample-013-ledger` | C3; U3 row "one line per session the launcher started" |
| P2.8 | a Planner launch under a capture-less regex finishes and indexes the folder name | a finished session, project folder `project` | `--planner review --run-dir … --yes` | exit 0; `planner launched (review, ` in LEDGER.md; index `project` `project` | C3; Assumed P2 Q2: the folder name, as a no-match today |
| P2.9 | the desktop example's `group_regex` captures the tracker prefix | the example file's regex under bash `[[ =~ ]]` | `SMPL-482`; `SMPL-482-export-csv` | both match, capture `SMPL` | C5 "`SMPL-482` → `SMPL` and `SMPL-482-export-csv` → `SMPL`" |
| P2.10 | under the desktop unit block a brief still inherits the keyed intake | `SMPL-482-export-csv/INTAKE.md` under the sessions root | `--planner brief --ticket SMPL-500 --slug import-csv --dry-run` | `intake:    <root>/SMPL-482-export-csv/INTAKE.md` | C5 "`latest_intake` still matches `SMPL-482-export-csv`" |
| P2.11 | a capture-less regex is still refused before a launch | `group_regex` `^.+-[0-9]{3}-` | `--planner brief --slug sample-003-z --dry-run` | exit 1, `refusing:` naming `group_regex` | C4 "The two pre-launch callers … are unchanged"; pinned by the session-state suite's `test_launcher__a_group_regex_that_matches_but_captures_nothing_is_refused_by_name` |

Assumed, with the default taken:

- P2 Q1 — `--pin` under a capture-less regex is soft: the pin runs after the pasted session started,
  and refusing there leaves `session_id` unpinned.
- P2 Q2 — a doc role's index project under a capture-less regex is the project folder's name, the
  same fallback a no-match takes.
- P2 Q3 — the pin reads the unit id a launch reads (`ticket`, else the session dir's name); a ticket
  the launch would refuse leaves the pin standing and `project` null (not pinned by a test).

## Values a session can write (session inputs)

A session can write its own `run.json`, its `.stop-gate-count`, its worktree's session marker and
the directories beside its own; a Planner writes `robowright.json`. The code that reads them runs
outside the sandbox and outside the session's permission settings, so each value is held to a shape
before it reaches a JSON blob, a flag, arithmetic, git or a printed command. Source of every
expected value: the Owner's fix brief for this change (2026-10-13), bound named per row. Tests
assert refusal or neutralisation only; no value carries a working payload — a quote, a brace or a
leading `-` is enough to fail the shape.

Rows live in the suite that owns the script: L = `tests/run-launch/test_run_launch.py`,
R = `tests/role-start/test_role_start.py`, S = `skills/robowright/scripts/test_session_state.py`,
C = `skills/worker/scripts/test_run_cost.py`, Q = `skills/lead/scripts/test_run_roster.py`.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| SI-1 | every model value the launcher reads is held to the model shape, refused by its source | a quote-and-brace model in turn: `--model`, run.json `model`, `units[].model`, `--subagent-model`, `robowright.json` `models.planner`; also `-opus` and `claude-x y` | `--dry-run` (Worker, or `--planner brief`) | exit 1; the `refusing:` line names the source (`flag`, `brief`, `unit U1`, `--subagent-model`, `robowright.json`); no `command:` line | bound 2 (L) |
| SI-2 | the settings blob is JSON with exactly the intended keys | a launchable session on `opus`, effort `high` | `--yes` | the stub's `--settings` value parses; top-level keys `effortLevel`, `modelSettings`, `env`; `modelSettings` is `{claude-opus-5-5: {effortLevel: high}}`; `env` holds exactly the three variables | bound 1 (L) |
| SI-3 | role-start holds the model it reads to the same shape | `robowright.json` `models.planner` = a quote-and-brace value, then `-x` | `role-start.py planner <project>` | exit non-zero naming `robowright.json`; `claude` never called | bound 2 (R) |
| SI-4 | both scripts read one shared model definition | — | read `skills/robowright/models.json` | it holds the form and the alias ids; role-start's and the launcher's ids for `opus` come from it | bound 2 (R, L via SI-2) |
| SI-5 | a hand-edited model is flagged like phase | an implementing session | hand-edit `model`, then `units[0].model` | `check` exits 1 with `edited-outside-tool` naming the model | bound 3 (S) |
| SI-6 | a session whose newest event predates the model digest is not flagged | an implementing session whose newest event has no model digest | `check` | exit 0 | bound 3: the integrity check must not flag every existing session (S) |
| SI-7 | the stop-gate counter is never evaluated; a non-digit count reads as 0 | the counter holds the current fingerprint and `5+0`, then `x{`; then `08` | the Stop hook runs | it blocks, and the counter holds `<fingerprint> 1`; `08` counts as eight, so the hook releases and writes `<fingerprint> 9` | bound 4 (S) |
| SI-8 | `session_id` reaches `--resume` only as a UUID, as `--resume=<id>` | run.json `session_id` `--version`, then `abc`; then `--resume notauuid`; then a UUID | `--resume --dry-run` | the first three exit 1 naming `session_id`/`--resume`; the UUID plans `--resume=<uuid>` | bound 5 (L) |
| SI-9 | `base_sha` and `publish.tip` reach git only as hex or `HEAD` | `base_sha` `--stat`; then `publish.tip` `HEAD~1` | `lines_shipped` | `None`, stderr names `base_sha` / `publish.tip` | bound 6 (C) |
| SI-10 | `tools` is a comma list of known tool names | run.json `tools` `default`, `Bash,Nope`, `Bash Read`, `["Bash"]` | `--dry-run` | exit 1 naming `tools`; `Bash,Read` plans `--tools Bash,Read` | bound 7 (L) |
| SI-11 | the directory-name fallback for the unit id is a unit name | no `ticket`, session dir `Not-A-Unit_x` | `--dry-run` | exit 1 naming the directory; `sample-001-x` still plans | bound 7 (L) |
| SI-12 | the worktree hint quotes its branch and refuses one git rejects | the worktree missing; `units[0].branch` `a;b`, then `a..b` | `--dry-run` | `a;b` appears quoted (`a\;b`); `a..b` is refused naming `branch` | bound 7 (L) |
| SI-13 | `lock_names` is held to `^[a-z0-9-]+$` | a stopped session listing the lock `x.y`, which exists and is owned by this session | `park` | that lock is left in place; the park notes it | bound 7 (S) |
| SI-14 | a marker counts only when its session dir sits under the sessions root | the marker names a session dir outside the root, then one inside | the Stop hook runs | outside: no block, no counter written; inside: block | bound 7 (S) |
| SI-15 | `run-roster --tail` fences session-written text as data | a ledger heading and a HANDOFF line with an escape byte, a two-line stop detail | `render(tail=True)` | a data label line precedes them; every session-written line starts with the fence prefix; no control byte | bound 7 (Q) |
| SI-16 | the session marker is git-ignored in this repo | this checkout | `git check-ignore .claude/autonomous-run` | exit 0 | bound 8 (L) |

## Session writes (SW)

A session can create any entry in its own folder and worktree: a symlink, a FIFO, a hard link. The
hooks, the launcher, the state tool, `run-cost.py` and `spend-guard.py` write into that folder
outside the sandbox, so every such write opens the name itself, never through a link, and only onto
a regular file with one link. Source of every expected value: the fix brief for this change
(2026-10-15), bound named per row. Every target is a scratch file; the planted value is a link, never
a payload.

Rows live where SI's do, plus W = `skills/robowright/scripts/test_session_state.py` for the shared
helper `session_write.py`, and the conventions suite (K) for the lint row.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| SW-1 | the Stop hook's counter is never written through a link | `.stop-gate-count` is a symlink to a scratch target holding text | the Stop hook runs on a working session | it still blocks; the target's text is unchanged; the link is still a link | bound 1, hooks (S) |
| SW-2 | the Stop hook's ledger line is never appended through a link | rotation requested; `LEDGER.md` is a symlink to a scratch target | the Stop hook runs | it releases; the target is unchanged | bound 1, hooks (S) |
| SW-3 | a dangling ledger link creates nothing | `LEDGER.md` is a symlink to a scratch path that does not exist | the Stop hook releases for rotation, then the PreCompact hook runs | the path still does not exist | bound 1, "the session file is not created through it" (S) |
| SW-4 | the PreCompact hook's line is never appended through a link | `LEDGER.md` is a symlink to a scratch target | the PreCompact hook runs | the target is unchanged | bound 1, hooks (S) |
| SW-5 | `rotate.requested_at` reaches the ledger only as an ISO-8601 time | `rotate.requested_at` holds a valid time, then a newline and a second line | the Stop hook releases for rotation | the ledger gains exactly one line each time; the valid time is quoted; the second line's text is not in the ledger | bound 1, "no session-written value reaches a LEDGER line with a newline" (S) |
| SW-6 | the Stop hook's stuck line holds one line whatever `phase` says | a hand-edited `phase` with a newline in it and the counter at the release threshold | the Stop hook releases after six blocks | the ledger gains exactly one line | bound 1, same (S) |
| SW-7 | the state tool never truncates or writes through its lock link | `.session-state.lock` is a symlink to a scratch target holding text | a refused `accept`, then a legal event | both exit 2 naming the lock; the target's text is unchanged; run.json and events.jsonl are unchanged | bound 1, "a refused land must not empty the lock's target" (S) |
| SW-8 | the state tool never appends an event through a link | `events.jsonl` is a symlink to a scratch target | a legal event | exit 2 naming events.jsonl; the target and run.json are unchanged | bound 1, state tool (S) |
| SW-9 | the launcher refuses a marker whose `.claude` is a link | the worktree's `.claude` is a symlink to a scratch directory | `--yes` | exit 1 naming `.claude`; nothing is created in the scratch directory; the stub never ran | bound 1, "refuse the autonomous-run marker when `$WORKTREE/.claude` is a symlink" (L) |
| SW-10 | the launcher never writes the marker or a ledger entry through a link | `.claude/autonomous-run`, then `LEDGER.md`, is a symlink to a scratch target | `--yes` | exit 1 naming the file; the target is unchanged; the stub never ran | bound 1, launcher (L) |
| SW-17 | the launcher holds `rotate.requested_at` to an ISO-8601 time | a launchable session whose `rotate.requested_at` holds a newline and a second line, then a valid time | `--rotate --dry-run` | the first is refused naming `rotate.requested_at`, and the second line is printed nowhere; the valid time is not refused for its shape | bound 1, "no session-written value reaches a LEDGER line with a newline" (L) |
| SW-18 | the launcher refuses a worktree path holding a control character | a git-listed worktree whose directory name holds a newline | `--yes` | exit 1 naming `worktree`; no ledger entry | bound 1, "no session-written value reaches a LEDGER line with a newline"; review 1 F1 (L) |
| SW-11 | `--pin` never writes run.json, its lock or the ledger through a link | `.session-state.lock`, then `LEDGER.md`, is a symlink to a scratch target | `--pin` | exit non-zero; the target is unchanged | bound 1, launcher `:314,323,338,345` (L) |
| SW-12 | `run-cost.py --write` never writes through the lock link, and the SessionEnd hook's line never through a ledger link | `.session-state.lock`, then `LEDGER.md`, is a symlink to a scratch target | `run-cost.py --write`, then the SessionEnd hook | the target is unchanged | bound 1, "find any other such write" (C) |
| SW-13 | `spend-guard.py` never writes STOP or a ledger line through a link | a session past its cap; `STOP`, then `LEDGER.md`, is a symlink to a scratch target | one pass | the target is unchanged | bound 1, same (Q) |
| SW-14 | the helper refuses every target that is not a regular file with one link, and refuses fast | a symlink, a dangling symlink, a FIFO, a hard link, a directory; a link as the parent directory | `append`, `replace` and `check` | exit 2 naming the path; nothing created, changed or truncated; the FIFO returns at once | bound 1, Python and Bash rules (W) |
| SW-15 | the helper writes a plain file | a missing file, then an existing one | `check`, `append`, then `replace` | check passes and creates nothing; append creates then extends; replace leaves exactly the new text | bound 1, the writes still happen (W) |
| SW-16 | the lint flags a bare redirect to a file in a hook or the launcher | a hook with `>> "$run_dir/LEDGER.md"`, the launcher with `> "$MARKER"`; then `>/dev/null`, `2>&1`, `>&2` | `lint.py` | the first two are `session-write` findings; the rest are not | bound 5, conventions check (K) |
| SW-19 | `run-cost.py --ledger` never takes the ledger lock or appends a record through a link | `<accounting root>/.records.lock`, then `records.jsonl`, is a symlink to a scratch target; then `records.jsonl` is a dangling link | `run-cost.py --ledger` | exit 2 with `refused:`; each target is unchanged and the dangling path is still absent | Lead's delegated call 2026-10-15, closing review 2 P2-1: the accounting root sits under the sandbox grant (L) |
| SW-20 | the launcher never appends its launch index line through a link, and still launches | `<accounting root>/launches.jsonl` is a symlink to a scratch target | an `auto` launch | the session starts; the target is unchanged; a note says nothing was appended | same; the index is best effort, "never fails a launch" (L) |
| SW-21 | `robowright-cost.py --migrate` refuses a planted ledger link the way `--ledger` does | `<accounting root>/records.jsonl` is a symlink to a scratch target; a finished session to migrate | `--migrate` | exit 2 with `refused:`; the target is unchanged | review 3 P2-1: the shared `append_records` now raises a refusal that is not an `OSError` (R) |
| SW-22 | the helper reads only a regular file with one link, reached through no link, and refuses fast | a link in a folder above the file, a link at the name, a FIFO, a hard link, a directory, a file of 64 KiB + 1 byte; a relative path, and one holding `.`, `..` or `//`; a missing file | `read` | exit 2, `refused: <path>: <why>` on stderr; nothing on stdout, so the link target's bytes are never printed; the FIFO returns at once | U52b B1: accept.sh's message and the Owner tools' `robowright.json` are session-written (W) |
| SW-23 | the helper reads a plain file | a file of a few bytes, then one of exactly 64 KiB | `read` | exit 0, its bytes on stdout unchanged | U52b B1, the reads still happen (W) |

## Write scope (WS)

What each role the launcher starts may write, passed in its `--settings` blob: `permissions.additionalDirectories`
for the shell and the file tools alike, and denied to both (`sandbox.filesystem.denyWrite`, an `Edit(...)` deny) every
configured repository's whole git directory, and a leaf `<root>/**/.git` on each granted root. A role that commits
also carries `sandbox.excludedCommands: ["rw-git *"]` and a leaf on its worktree (U46). Rows cite the characterization table (C rows) in the
unit's ledger. Grants are read from `launch.json` only, never from the environment the launcher runs in.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| WS-1 | a Worker is granted its session folder and the accounting root, and nothing else | a launchable session, no locks, no `depends_on` | `--yes` | `additionalDirectories` is exactly `[<session dir>, <accounting root>]`; the plan's `writes:` line names both | C2, C3, C6; bound 2 |
| WS-2 | a Worker's settings deny the main clone's whole git directory, and every `.git` under its worktree and its grants, to the shell and the file tools, and run `rw-git` outside the sandbox without a prompt | the same | `--yes` | `denyWrite` is exactly `<repo>/.git`, `<worktree>/**/.git`, `<session dir>/**/.git`, `<accounting root>/**/.git`; `permissions.deny` is the matching `Edit(//…)` rules, a leaf's both as itself and with `/**`; `sandbox.excludedCommands` is exactly `["rw-git *"]`, and `permissions.allow` exactly `["Bash(rw-git *)"]` | U46 bound 3: drop the Workers' `.git` sub-grants, a leaf deny on each granted root; bound 2: `rw-git *` for every role that commits |
| WS-3 | a lock named in `run.json` is granted as its lock directory only | `locks: ["sim"]` | `--yes` | `<sessions root>/.sim-lock` is granted; the sessions root itself is not | C7 |
| WS-4 | the launcher makes a `depends_on` checkout, and grants no admin dir | an entry whose `path` is a second repo `repos` lists and whose `ref` is its HEAD; then a stray `path`, a `session` holding `/`, a `ref` that is not a commit id; then `deps` a link; then `deps/<session>` a link | `--dry-run`, `--yes` | the dry run makes nothing; `--yes` makes `<session dir>/deps/<session>` at the ref, grants only the session folder and the accounting root, and denies the dep's whole git directory; each bad entry is refused naming `depends_on`; through a link nothing is made; with the checkout made, `role_grants.py worker` and `document` still grant | C8; review 1 F1, F2: git names the admin dir, so no grant can; review 3 F1 |
| WS-5 | no grant is at or above a configured repository or the home directory | `accounting_root` set to the repo itself, then to `~/` | `--dry-run` | refused naming the grant and what it would reach; nothing starts | bound 7 |
| WS-6 | the environment never moves a grant | `ROBOWRIGHT_ACCOUNTING_ROOT` points at the repo's parent | `--yes` | the grant is `launch.json`'s accounting root; the launch is not refused | a Lead sets the launcher's environment (U36's decision on `repos`) |
| WS-7 | a Planner and an Explainer are granted the projects root and the sessions root | `projects_root` set | `--planner brief --yes`, `--explainer report --yes` | `additionalDirectories` is exactly `[<projects root>, <sessions root>]`; `denyWrite` is the repo's git directory, then the projects' Claude settings of WS-22, then `<projects root>/**/.git` and `<sessions root>/**/.git`; no `excludedCommands` and no `permissions.allow` | C12–C15; bound 2; U46 bound 3: a role that does not commit runs no `rw-git` |
| WS-8 | a document role whose projects root holds a configured repository is refused | `projects_root` is the repo's parent | `--planner brief --dry-run` | refused naming the projects root; nothing starts | bound 7 |
| WS-9 | the launcher, not the session, adds the marker to the repo's `info/exclude` | a worktree that does not ignore `.claude/` | `--yes` | `<repo>/.git/info/exclude` holds `.claude/autonomous-run`, and `git check-ignore` in the worktree passes | C5 moves to the Owner side, since WS-2 denies `info` |
| WS-10 | no root, grant or working directory has a link at or above it | in turn the projects root, the sessions root, the accounting root, a lock directory and a document role's `--project`: the path itself a link; then below a link outside every root; then below a link inside another root | `--dry-run` | refused naming the path and the link, and saying to point launch.json at the real path; nothing starts | the Owner's decision 2026-10-15 (A): reviews 2, 3 and 4 each found a way past a link resolver, so no link is followed at all |
| WS-11 | with no well-formed `repos`, nothing is granted | launch.json without `repos`; then with a relative entry | `--planner brief --dry-run` | refused naming `repos`; nothing starts | review 1 F4 |
| WS-12 | no grant reaches the launcher's clone or launch.json's real directory | `projects_root` is this clone; then launch.json is a link into a directory that `projects_root` names | `--planner brief --dry-run` | refused naming the clone, then launch.json's real directory | bound 7; review 1 F5, F10; review 2 F6 |
| WS-13 | git environment never moves a deny | `GIT_DIR` and `GIT_COMMON_DIR` name another repo | `role_grants.py document` | the denies name the configured repo's files | review 1 F6 |
| WS-14 | a document role's working directory is held to the same rule | `--project` is a folder holding a configured repo and not the home directory | `--planner brief --dry-run` | refused naming the working directory and the repository | review 1 F8; review 2 F6 |
| WS-15 | a document role's working directory inside a git checkout is refused | `--project` is a folder with a `PROJECT.md` inside the configured repo; inside a Worker's worktree; inside a clone `repos` does not list; this clone's `skills/one-off/templates`; then a folder in a projects root that is itself a git repository; then under a home directory that is one | `--planner brief --dry-run` | refused naming the working directory as inside; nothing starts; the last two plan | review 2 F2; review 3 F4 |
| WS-16 | the exclude line is never written through a link | the repo's `.git/info` is a link to another directory | `--yes` | exit 1 naming `info` as a symlink; the target's `exclude` unchanged | review 2 F6 |
| WS-17 | a planted `commondir` is refused, and `commondir` is denied | a launch; then `<repo>/.git/commondir` names another directory | `--yes`; `role_grants.py document` | `denyWrite` holds `<repo>/.git`, which holds `commondir`; then exit 2 naming `commondir` | review 4 F2: git would read that directory's config and hooks, and name it as the repo's |
| WS-18 | no root, grant or working directory holds a `.` or `..` component | in turn the projects root, the sessions root and the accounting root spelled with `/./`, then with `/../`; a `--project` spelled with `/../` | `--dry-run` | refused naming the path and the component; nothing starts | the Owner's decision 2026-10-15 (A); review 4 F1: `..` after a link left the kernel and the check on different directories |
| WS-19 | a protected path spelled in another case is still matched | `$HOME` spelled in another letter case; every root spelled as on disk; the projects root the home directory | `--planner brief --dry-run` | refused naming the home directory; skipped on a case-sensitive volume | the Owner's decision 2026-10-15 (A): directories compare by `(st_dev, st_ino)`, never by spelling; `$HOME` is held to no spelling |
| WS-20 | a root, project or repository spelled other than on disk is refused | in turn the projects root in another letter case, the sessions root in the other Unicode form, a `repos` entry in another case, a `--project` in another case | `--planner brief --dry-run` | refused naming the component as spelled and as the disk names it; nothing starts; skipped on a case-sensitive volume | review 5 F4: the sandbox matches a deny as a string |
| WS-21 | a project swapped for a link around the check never starts there | the projects root granted; a `python3` that swaps a folder at the launcher's first `role_grants.py document` or `session_write.py append`: `projects/p`, a link to `<repo>/sub`, made a directory before the check; `projects/a`, a directory, made a link to the repository after it; `projects/b` made that link after the session started | `--explainer report --project … --yes` | the first starts in `projects/p`; the second exits 1, "changed after it was checked", nothing started; the third starts in `projects/b/p` and its ledger line lands in that directory; no `DECISIONS.md` in the repository and no session there | review 4 F1, review 5 F1: the check and the start must name one directory |
| WS-22 | a document role cannot write a project's Claude settings | the projects root holding `p1` and `p2`; a Planner started in `p1` | `--planner brief --yes` | `denyWrite` and `Edit(…)` deny rules hold `.claude` and `.mcp.json` of the projects root and of `p2`, and `<projects>/**/.claude` and `/**/.mcp.json`; the grants are unchanged | review 5 F3: Claude Code loads them for a session started there and runs their hooks outside the sandbox, which protects only the working directory's own and those above it |
| WS-23 | a grant above a link in a repository's spelling is refused | `repos` names `<root>/links/repo`, a link to the clone; the projects root is `<root>/links` | `--planner brief --dry-run` | refused naming the repository as spelled; nothing starts | SECURITY.md: a role granted the directory holding the Owner's link could repoint it; review 5 F6 (MA, ML) |
| WS-24 | `role_grants.py worker` holds the session folder itself | a session folder under the sessions root that is a link to a copy elsewhere; then a directory elsewhere named like an existing session folder | `role_grants.py worker <folder> <worktree>` | exit 2 naming the link, then "is not a session folder"; nothing on stdout | review 5 F6 (MC, MD): the launcher's own checks run first, so only a direct call shows these |
| WS-25 | a pasted hand-off starts only in the directory checked, and writes its ledger line there | `launch` `paste`; the project `projects/a b/p` (a space, which the compare must quote); after the hand-off, `projects/a b` moved aside and made a link to the repository, which holds `p/`; then a launch whose `python3` makes that swap at the hand-off's ledger append | `--explainer report --yes`, then the printed line run in bash; then again with the swap undone; then the launch with the swap | the swapped run exits non-zero and claude never runs; the unswapped run starts claude in `projects/a b/p`; the hand-off's ledger line lands in the checked folder, never `<repo>/p/DECISIONS.md` | review 6 F1: paste is the default, and the Owner pastes the line any time later; review 7 F1, F2 |

## Worktree creation (WT)

A sandboxed Lead cannot write a repository's git directory, so the launcher creates a Worker's missing worktree on the
Owner's side (the Owner's decision 2026-10-15, option 2). Every input is session-written (`run.json`), so each is held
to its shape before git runs. The convention is the hook's §3: `<repo>/.worktrees/<slug>` on branch
`robowright/<slug>`, `<slug>` the session directory's name. `<repo>/.claude/worktrees/<name>` is the desktop
app's: a run.json naming a missing worktree there is refused like any other path off
the convention (WT-10), and an existing listed worktree there is started as it is (WT-16).

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| WT-1 | at preflight a missing worktree on the convention is created from the base on a new branch | `worktree` `<repo>/.worktrees/sample-001-x`, absent; `units[0].branch` `robowright/sample-001-x`; `base_sha` a commit behind the repo's HEAD; phase `preflight` | `--dry-run`, then `--yes` | the dry run exits 0, prints the `worktree add` line, and leaves the path absent with no `worktree add` run; `--yes` makes the worktree on that branch at `base_sha`, with `--end-of-options` before the path, and starts the Worker | §3 Worktree; the brief's bound 2 |
| WT-2 | after preflight the existing branch is attached | the WT-1 worktree made, a commit on its branch, the worktree removed, phase `implementing` | a plain `--yes`, then `--resume <id> --yes` | the plain launch, which the state machine refuses, makes nothing; the resume puts the worktree back on `robowright/sample-001-x` at that commit, not at the base, and the Worker starts | bound 2: "later phases attach the existing branch" |
| WT-3 | a finished session's worktree is never created, nor one for a phase that is no name | phase `done`; then `parked`; then `7`; the branch `robowright/sample-001-x` still exists | `--yes`; `role_grants.py worktree <dir> plan` and `make` | the launcher exits 1 (the finished refusal, then the missing-worktree hint); `role_grants.py` refuses on its own, exit 2: "a finished session's worktree is not made", then "is not a phase name"; the path absent and no `worktree add` run | bound 2; 026 and 027 rows in the session-state suite; review 5 F6 (MF) |
| WT-4 | a worktree path off the convention is refused | the path in a directory beside the repo; with another slug; holding `..`; through a link at `<repo>/.worktrees`; relative | `--yes` | exit 1 naming the convention; nothing created; no git run | bound 2: the launcher never creates a path a session chose |
| WT-5 | a branch off the convention is refused | `units[0].branch` `-b`, `other/sample-001-x`, `robowright/sample-001-x/more`, `robowright//sample-001-x`, a number, absent | `--yes` | exit 1 naming the branch; nothing created; no git run | bound 2; prefix rule `robowright/<slug>` (§13) |
| WT-6 | a base that is not a full commit id of that repository is refused | `base_sha` 7 hex; 40 characters with a non-hex one; 40 hex naming no object; the 40-hex id of a tree; the id of an annotated tag on the base | `--yes` | exit 1 naming `base_sha`; nothing created; no git run for the first two, and no `worktree add` for the last three | bound 2; review 5 F6 (MI): a tag peels to a commit |
| WT-7 | a repository launch.json does not trust gets no worktree | a second clone `repos` does not list, the path on the convention inside it | `--yes` | exit 1 naming the repository rule; nothing created; no git run | U36's allowlist |
| WT-8 | git environment never moves the worktree made | `GIT_DIR`, `GIT_COMMON_DIR` and `GIT_WORK_TREE` name a second repository in the launcher's environment | `--yes` | the worktree is made in the configured repository at `base_sha`, its branch there, and none in the second repository (the launch then stops at U36's worktree listing, which reads the same environment and fails closed) | review 1 F6, carried to the git the launcher now runs |
| WT-10 | a run.json naming a missing worktree at the old place is refused, and nothing is made | `worktree` `<repo>/.claude/worktrees/sample-001-x`, absent, at preflight | `--yes` | exit 1, the output carrying `is not where the launcher makes one`; no `worktree add` run; the path absent; the Worker not started | old-place brief R4; D1; D7: "a `run.json` naming a missing worktree anywhere else, `<repo>/.claude/worktrees/<name>` included, is refused with nothing made" |
| WT-16 | an existing listed worktree at the old place is started where it is | a worktree at `<repo>/.claude/worktrees/sample-001-x` on `robowright/sample-001-x` at the base, named by `run.json.worktree`, at preflight | `--yes` | the Worker starts; the session marker in that worktree names the session dir; no `worktree add` run | old-place brief R6; D3: the existing-worktree admission `*/worktrees/*\|*/.worktrees/*` is not changed; D7: "the launcher starts a Worker in an existing listed worktree under any `worktrees/` or `.worktrees/` path component" |
| WT-11 | making a worktree under `.worktrees` keeps it out of the main checkout's status | WT-1's launch; then a second session's | `--yes`, twice | `<repo>/.git/info/exclude` holds `/.worktrees/` once; `git status --porcelain` in the main checkout prints nothing | U46 bound 4: `accept.sh` refuses a dirty main clone, and a nested worktree shows as untracked |
| WT-12 | the exclude line is its own line when the file's last line has no newline | `info/exclude` is `/sample-local` with no final newline | `--yes` | the file's first two lines are `/sample-local` and `/.worktrees/`; `git status --porcelain` in the main checkout prints nothing | review 1 F1: appended bare, the two would merge into one line that ignores nothing |
| WT-13 | a hook only the new worktree reads does not run as it is checked out | a base with `notes.txt`; `includeIf "onbranch:robowright/**"` in the shared config, its file naming `hook.pic` on post-index-change | `--yes` | the worktree holds `notes.txt` at the base; no marker | gate F5: `worktree add` checks out in a child that reads the new worktree's config; `--no-checkout`, then `reset --hard` through `owner_git.run(<worktree>)` |
| WT-14 | a repository with a submodule still launches when `submodule.recurse` is set | a base holding a submodule `library`; `submodule.recurse = true` in the repository's config | `--yes` | the worktree holds `notes.txt` at the base; the launch exits 0 | gate F7: the standalone `reset --hard` recursed, where `worktree add`'s own checkout does not, and died on the new worktree's missing submodule git dir; `--no-recurse-submodules` |
| WT-15 | a checkout that fails leaves nothing behind | a git that fails `reset --hard` | `--yes` | refused `git could not make the worktree`; the worktree is not listed, its folder is gone, and `robowright/<slug>` does not exist | adversarial F1: `--no-checkout` then a failed reset left a registered worktree with an empty index, which the next launch reused; `worktree add` itself removes its half-made worktree |
| WT-9 | the new branch writes no ref or reflog through a planted link | at preflight, in turn: `.git/logs/refs/heads/robowright/sample-001-x` a link to an Owner file; `.git/logs/refs/heads/robowright` a link to an Owner directory; `.git/refs/heads/robowright` the same; then that reflog directory link planted by a `git` shim just before `worktree add` | `--yes` | the first three exit 1 naming the link, the Owner's file and directory untouched, no `worktree add` run; the fourth leaves the Owner's directory empty | found after review 7: git follows a link when it appends a reflog, as the Owner |

## Attributes off (AS)

The Owner's decision 2026-10-15, "option 1, switch to attr-source". A base commit's `.gitattributes`, or the Owner's
global attributes file, can name a filter the Owner's git config defines (git-lfs is the usual one), and a checkout or
a `status` runs it. Every git call the Owner's process makes in a Worker's worktree, and every `worktree add` it runs,
carries `--attr-source=<the empty tree>` and `-c core.attributesFile=/dev/null`: git reads no attributes from the
checkout, the index or that file, so no filter runs and the files are checked out raw. `git --attr-source` is new in
git 2.41.0 (release notes 2.41.0), which exports it to child processes as `GIT_ATTR_SOURCE` (`git.c` at v2.41.0).

Every AS fixture's base holds `a.txt`, `CLAUDE.md`, `.claude/settings.json` and a `.gitattributes` line
`*.txt filter=mark`; the scratch HOME's `.gitconfig` defines `filter.mark` and sets `core.attributesFile` to a file
naming `*.md filter=globalmark`. Each filter's `smudge` and `clean` write a marker file outside the repository.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| AS-1 | the launcher's worktree runs no filter and holds every file | the worktree absent at preflight; then absent past preflight, its branch existing | `--yes`; then `--resume <id> --yes` | every tracked file present, `CLAUDE.md` and `.claude/settings.json` included, with HEAD's bytes; no marker of `mark` or `globalmark` | the Owner's decision, item 1 |
| AS-2 | a `deps/<session>` checkout runs no filter and holds every file | a `depends_on` entry at a dependency repo's commit holding the same files under `filter=depmark` | `--yes` | `deps/<session>` holds every file at the ref; no `depmark` marker | item 1 |
| AS-3 | a git without `--attr-source` is refused | a `git` on PATH that rejects `--attr-source` and says `git version 2.39.0`; the worktree absent; then present | `--dry-run`; `--yes` | exit non-zero naming git 2.41.0; no worktree made; no session started; with the worktree absent, no `worktree add` line to run by hand, also when run.json is refused first (a base that is not a commit; past preflight with no branch) and on `--pin` | item 2; review 11 F1, review 12 F1 |
| AS-4 | the launcher's `status` writes no index | a populated worktree with a stat-dirty tracked file, its admin `index` a link to a copy elsewhere | `--dry-run` | the copy's bytes unchanged | item 4; review 10's open item |
| AS-5 | the launcher's `status` runs no `clean` | AS-1's worktree, `a.txt` touched | `--dry-run` | no `mark` marker | item 7: every git call in the worktree after it is made |

## Direct launch (DL)

A direct build (the planner handbook → Size `S` or below) has no `run.json`, so a Worker's worktree maker could not
make its worktree, and since U38 no sandboxed role can (the Owner's decision 2026-10-16, option 1). `--direct` makes it
on the same hardened path and starts the build in it. Every value comes from argv, which a Lead writes, so each is held
to its shape before git runs or the prompt is built. Source of every expected value: the U42 brief, Bound 1, the row
named per test.

Every DL fixture: a configured repository `repo` with a base commit and one after it; `launch.json` naming
`projects_root` and `repos`; the project `<projects root>/sample` with `briefings/sample-001-x.md`; slug
`sample-001-x`; a `claude` stub that records its argv and working directory and registers a session whose `cwd` is
its own.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| DL-1 | the worktree is made at the convention path on the convention branch, from a full commit id | the worktree absent | `--direct … --yes` | `<repo>/.worktrees/sample-001-x` exists on `robowright/sample-001-x` at the base; one `worktree add --no-checkout -b robowright/sample-001-x --end-of-options <path> <base>` ran, then the checkout in the new worktree (U52b gate F5) | "makes the worktree `<repo>/.claude/worktrees/<slug>` on branch `robowright/<slug>`", moved to `<repo>/.worktrees/<slug>` by U46 bound 4 |
| DL-2 | a repository not in `repos` is refused, and nothing is created | `--repo` a second clone `repos` does not list | `--yes` | exit 1 naming `repos`; no worktree; no git run in either repository | "`repos` membership" |
| DL-3 | a base that is not a full commit id of that repository is refused | `--base` 7 hex; 40 characters with a non-hex one; 40 hex naming no object; a tree id; an annotated tag's id | `--yes` | exit 1 naming `--base`; no worktree; no git run for the first two, and no `worktree add` for the rest | "the base a full commit id of that repository" |
| DL-4 | a slug or branch off the convention is refused | `--slug` `-x`, `a/b`, `..`, `Sample-001-X`, `sample-x`; `role_grants.py direct` given `a/b`, `..` and `sample-001-x.lock` | `--yes`; `role_grants.py direct … plan` | the launcher exits 1 naming `--slug`; `role_grants.py` exits 2 naming the slug, or for `.lock` the branch; no worktree and no git run in the repository | "the branch and slug conventions" |
| DL-5 | a link or a `.`/`..` at any prefix of the repo, the worktree path or the briefing path is refused | in turn: `--repo` through a link, or holding `..`; `<repo>/.worktrees` a link; the worktree path a link; `--project` through a link; `briefings` a link; the briefing a link; the briefing path holding `..` or `.` | `--yes` | exit 1 naming the link or the component; nothing created in the repository or behind the link; no session started | "no link and no `.`/`..` at any prefix" |
| DL-6 | the launcher's checkout runs no filter the base names | a base whose `.gitattributes` names `filter=mark`, defined in the scratch HOME's global config, its `smudge` and `clean` each touching a marker | `--yes` | every tracked file present with the base's bytes; no marker | "checkout with `--attr-source` empty and `core.attributesFile=/dev/null`" |
| DL-7 | an existing worktree of `robowright/<slug>` at the path is reused, and anything else there is refused | DL-1's worktree; then the build's worktree at the old place `<repo>/.claude/worktrees/<slug>` with nothing at the new one; then in turn: a plain directory; a file; the repository's worktree there on another branch; a detached one; another repository's worktree of `robowright/sample-001-x` there; the branch alone, with nothing at the path | `--yes` | the first starts the build in its worktree with no `worktree add`; the second exits 1 with `the branch robowright/sample-001-x exists in <repo> but no worktree is at <repo>/.worktrees/sample-001-x; nothing is made over it`, runs no `worktree add`, starts nothing, and leaves the worktree at the old place; each other exits 1 naming the path, leaves it as it was, runs no `worktree add` and starts nothing; the branch alone is refused with the command that deletes it, and keeps its commit | "reuses an existing worktree only when it is already the worktree of `robowright/<slug>` at that path"; old-place brief R5, D7: "a direct build's worktree is only ever at `<repo>/.worktrees/<slug>`" |
| DL-8 | the started session's working directory is the worktree, and its `--settings` carries `document`'s fragment plus what a committing role needs | DL-1 | `--yes` | the stub ran in the worktree; `--name build-sample-001-x`; the `--settings` blob's `permissions` and `sandbox.filesystem` equal `role_grants.py document`'s output with `<worktree>/**/.git` added to both; `sandbox.excludedCommands` is `["rw-git *"]`; `permissions.allow` is `["Bash(rw-git *)"]` | "starts `claude --bg` with the worktree as its working directory. Its `--settings` is `role_grants.py document`'s fragment" |
| DL-9 | the prompt is the fixed sentence with the briefing path, and a briefing elsewhere is refused | DL-1; then in turn the briefing: in the project folder; in another project's `briefings/`; one folder deeper; named with a space; not `.md`; a directory; a hard link; missing | `--yes` | the last argv word is `Build directly from the briefing at <path>: read it in full, and follow it.`; each other briefing exits 1 naming `--briefing`, with nothing created | "passes a fixed prompt, never text from argv" |
| DL-10 | `paste` hands off the line and starts nothing | `launch.json` `launch: paste` | `--yes` | exit 0; `paste this yourself:` then a line that starts `cd <worktree> && [ "$(pwd -P)" = <worktree> ] &&`; `launch is yours`; the stub never ran; a `hand-off via` entry in the project's `DECISIONS.md` | "follows `launch.json`'s `launch` key exactly as the other shapes do" |
| DL-11 | a registry `cwd` that is not the worktree makes the launch exit non-zero, naming both paths | the stub registers the session with `cwd` the project folder; then registers nothing | `--yes` | exit 1; the output names the worktree and the registry's `cwd`, or says the registry shows none | "confirms from the session registry that the new session's `cwd` is the worktree" |
| DL-12 | `--dry-run` prints the plan and creates nothing | the worktree absent | `--dry-run` | exit 0; the plan names the `worktree add -b` line, `build-sample-001-x` and the prompt; no worktree, no branch, no `DECISIONS.md`; the stub never ran; no `worktree add` | the brief's verify list |
| DL-13 | the model and effort are held to their shapes, and no flag of another shape is taken | `--model` with a quote, `--effort huge`; `--direct` with `--run-dir`, `--name`, `--planner`; a Worker launch given `--repo`, `--base` or `--briefing` | `--dry-run` | exit 1 naming the flag, or saying they go with `--direct`; no `command:` line | "checked against `models.json` like every other model" |

## Tracker-less work under a ticket shape (U65)

Where `launch.json` sets `unit.ticket_regex`, work with no tracker key is briefed, launched and built like any other:
a `run.json` with no ticket takes the session directory's name as its unit id, held to the install's unit form, as on
an install with no ticket shape. A ticket that is present is still held to the ticket form and to the regex. Such a
session still names its project: a Worker launch whose directory name is in no `group_regex` group needs
`run.json.project`. Source of every expected value: the Owner's decision (allow no ticket) and the U65 note, Scope 2.

Every TL fixture: `launch.json`'s `unit` is the desktop example's (`ticket_regex` `^[A-Z][A-Z0-9]+-[0-9]+$`, example
`SMPL-482`; `slug_regex` `^[a-z0-9]+(-[a-z0-9]+)*$`; `group_regex` `^([A-Z][A-Z0-9]*)-[0-9]+(-[a-z0-9]+)*$`), and a
`claude` stub that registers the session it starts. "The no-regex config" is the same block with no `ticket_regex`.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| TL-1 | a session with no ticket launches under a ticket shape, its unit id the directory name | `ticket` null, `project` `sample`, model `opus`, session dir `sample-001-x` | `--dry-run`; `--yes` | exit 0, `(sample-001-x, phase` in the plan; the stub given `--name worker-opus-sample-001-x`; the launch index line's unit `sample-001-x`, project `sample` | the Owner's decision (allow no ticket): no ticket falls back to the directory-name unit form, as with no regex |
| TL-2 | a malformed ticket is still refused | `ticket` `sample-001-x`, then `ABC-1/../../../x`, under the regex | `--dry-run` | exit 1 naming `run.json` and `ticket`; no `command:` line | the Owner's decision (allow no ticket): a present, malformed ticket is still refused (pinned by the existing `SteeredValueTests` ticket-shape test, beside the ticket-less case) |
| TL-3 | a ticket-less Worker launch outside every group needs `run.json.project`, a string | `ticket` null, `project` null, then `7`, then `["sample"]`, session dir `export-csv`; then `project` `sample`; then `project` null on the no-regex config | `--dry-run` | exit 1, the refusal names `run.json.project` and `group_regex`, no `command:` line; then exit 0; then exit 0 with `project` null | the U65 note, Scope 2: a ticket-less session is still attributed to its project; the no-regex case is the Worker site's no-match rule (`ProjectTests`, assumed U1 Q15) |
| TL-4 | a ticket-less session dir in a group takes its project from the capture | `ticket` null, `project` null, session dir `SMPL-482-export-csv` | `--yes` | exit 0; `project` `SMPL` | the U65 note, Scope 2: a ticket-shaped name is unchanged; `ProjectTests`' group capture |
| TL-5 | `--planner brief` takes no `--ticket` under a ticket shape | an intake under `SMPL-482-export-csv` | `--planner brief --slug import-csv --dry-run` | exit 0; the plan names `<root>/import-csv` and `planner-import-csv`; `intake:    none found` | the Owner's decision (allow no ticket): `--ticket` is optional, and with none the session dir is `<root>/<slug>`; a bare slug is in no group, so inherits no intake |
| TL-6 | `--direct --slug` takes a plain slug under a ticket shape | DL's fixture under the regex | `--direct --slug export-csv --dry-run`; `--slug Not-A-Unit_x` | exit 0, the plan names `<repo>/.worktrees/export-csv`; exit 1 naming `--slug` | the U65 note, Scope 2: `in_unit_form` takes a plain slug under a regex, through `TICKET_FORM` then `SLUG_REGEX`; DL-4 |
| TL-7 | a session dir that is neither a slug nor `<ticket>-<slug>` is still refused | `ticket` null, `project` `sample`, session dir `Not-A-Unit_x` | `--dry-run` | exit 1 naming `run.json` and the directory name; no `command:` line | the U65 note, Scope 2: a ticket-less name passes exactly a no-regex install's checks; SI-11 |
