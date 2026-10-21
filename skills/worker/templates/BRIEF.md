# BRIEF — <slug> <title>

Written <date> by <Planner session `planner-<…>` / the Owner>. Every fact below is a claim the Robowright Session re-verifies
against the worktree before acting; corrections go in `LEDGER.md` under `Brief corrections`.

## Run parameters

| | |
|---|---|
| `ticket` | `<slug>` — the unit-of-work id, in the form the project hook → Naming defines |
| `repo` | `<repos[].name>` — the `robowright.json.repos` entry this brief works in; the Lead branches the worktree from that entry's `path`. A work-order brief, with no `robowright.json`, names the checkout directory's basename |
| `client` | `<client>` \| `none` — the row of that repo's hook §1 client table the units build; `none` for a hook with no clients. `run.json.platform` is that client's `platform:` |
| `worktree` | `<worktree path>` — where the project hook → Worktree puts it |
| `base_ref` | `<base_ref>` at `<sha>` (the Robowright Session records the resolved SHA) |
| `shape` | `stack` \| `single-change` \| `one-off` — a one-off is one unit with no Lead, written and launched by the `one-off` skill; the Worker takes itself in at Finish |
| `publish` | `<strategy name>` \| `false` — the publish strategy the project hook → Publishing declares in its `publish_strategy:` line, run at the end exactly as that section defines it; `false` publishes nothing |
| `profile` | `null` (= `standard`) — the one dial for what this brief is worth, expanded by the launcher into a Worker variant and a session effort per unit kind (the table in the planner skill → **Run profile**). **`showcase`**: work the Owner will learn from or ship without rereading. **`standard`**: the default, and everything else. **`economy`**: a mechanical stack, or a throwaway repo. An unknown name is refused at launch |
| `model` | `null` — the profile decides. Set it only to depart from the profile for **every** unit whose row below leaves `model` blank; a unit's own `model` departs for that unit alone. An explicitly set value beats the profile |
| `effort` | `null` — the profile decides. Set it only to depart from the profile for this session: `low`, `medium`, `high`, `xhigh`, `max`. The launcher passes it as `--effort` and inside `--settings`, because a backgrounded session carries the second over a supervisor wake and not the first |
| `mcp` | `[]` — the session starts with no MCP servers at all, because a server it never uses still costs its tool roster and its instructions. Where a unit needs servers, a list of picks from the approved list (`robowright/mcp/README.md`), each `{"server", "workflows", "allow"}` with `allow` optional; the launcher refuses a server, workflow or allow rule the list does not allow, and a binary that is missing or outside its pin |
| `tools` | `null` — the launcher's lean built-in tool list (its `LEAN_TOOLS`), because every tool definition rides on every request. A comma-separated list where a unit needs a tool the lean list leaves out, each name from the launcher's `KNOWN_TOOLS`; `default` is refused |
| `delegation` | `planner` — copied from the project's `robowright.json`; a brief may tighten to `lead` or `owner`, never loosen. Who answers a stop: `lead` → "the stop contract, from the lead's side" |
| `robowright` | `reviewer_code: opus`, `reviewer_prose: sonnet` — from `robowright.json.models`, never from this brief's `profile`; the Robowright Session passes these as `model:` when it spawns a Reviewer |
| `max_wall_hours` | `10` |
| `wall_hours_extension_pct` | `25` — the one extension the Lead may grant on a `budget` stop without the Owner. `0` makes every budget stop the Owner's |
| `max_gate_attempts` | `3` per unit |
| `locks` | `[]` — the lock names the plugin §6 of each client the units build for asks the launcher to respect, so the Lead can see before launching that this brief serialises against others. `[]` when no client's plugin names one |
| `depends_on` | `[]` — **Planner-written; the Worker never edits it.** One entry `{session, repo, path, ref, build_output}` per finished Robowright Session, in any repo of the project, whose commit a unit needs: `session` its session-directory name, `repo` a `robowright.json.repos` name and `path` that entry's `path`, `ref` a commit SHA and never a branch, `build_output` copied from its `run.json` (may be `""`). The Worker checks each out read-only at `<session_dir>/deps/<session>` (worker Phase 0 step 7a) |
| `spend_threshold_usd` | `null` — **only when the profile → Budget is in dollars**: the figure at which its guard warns and writes a ledger line; the Robowright Session continues. `null` otherwise |
| `spend_cap_usd` | `null` — **only when the profile → Budget is in dollars**: the figure at which its guard writes `STOP` and the Robowright Session ends with `owner-stop`. `null` otherwise |
| `rotate_sessions` | `true` for any brief with more than one unit, `false` for a single unit — a fresh session per unit: the Robowright Session ends its turn at each unit close and the Lead (or the Owner) starts the next from `HANDOFF.md`, per the profile → Launch. Rotation restarts at the fixed floor where compaction lands above it; see `robowright/DESIGN.md` §2 |
| `compact_pct` | `85` — `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` for the session, passed by the launcher inside `--settings`; the context window fills at this percentage of normal |

## Verification ceilings

Numbers the Robowright Session spends **to, and not past**. At a ceiling it writes in the ledger what it
would do with more — that line is worth more than a silent extra run. `sizing-the-move` rule 3
still holds below the ceiling: nothing is trimmed to save a build.

| | | |
|---|---|---|
| `max_mutation_rounds_per_unit` | `4` | A round is one scoped test run over one batch of ≤4 mutations. A test still unproven at the ceiling is deleted or declared, never carried |
| `whole_suite_runs_owed` | `unit-close, final-tip` | And **only when a source file changed since the last whole-suite run** — the project hook → Tests names the patterns; never after a prose-only commit. Remove `unit-close` for a single-unit brief |
| `max_extra_review_subagents` | `2` | Fresh-context reviewers beyond the owed set (per-unit gate, adversarial review and its re-review after a `HOLD`, comment pass, doc-gates): an equivalence audit, a second opinion |

Shape these were set against: a three-unit Robowright Session that spent more mutation
rounds on one unit than the rest, ran one whole-suite run after a prose-only commit, and used
two extra reviewers.

## Goal

One to three sentences: what is true when this is done, in terms a reviewer can check.

## Language

The glossary terms and leading words this brief uses, each defined in a line. Copied from the plan;
the Robowright Session uses these names in code, tests, commits and the ledger.

| Term | Means |
|---|---|
| | |

## Settled decisions

Decisions already made. The Robowright Session does not reopen these. A decision that sets the
bound for a sentence about a script's behaviour leaves the words to the Robowright Session; the
unit's scratch run checks them.

| | Decision | Why |
|---|---|---|
| D1 | | |

## Decision authority

Anything below found mid-session ends it with `stop_reason: one-way-door`, addressed to the
Lead. The Lead answers what `delegation` allows and brings the rest to the Owner.
Everything not listed here is the Robowright Session's own call, logged under `Assumed`.

**Owner-only (the floor, from `robowright.json.owner_only` and the profile → Owner-only floor —
never shortened):**

- accepting a product-visible behavior change inside a refactor or coverage unit
- deleting a public symbol, a feature flag, or anything with plausible future use
- a schema, persisted-data, or public protocol change. A new event, state or guard in a
  `state-machine.json` machine marked `"enforced": true` is a protocol change; a machine marked
  `"enforced": false` is a drawing, and not contract
- reversing any decision in the table above
- the budget cap, or wall hours past `wall_hours_extension_pct`
- anything another person reads

**This unit of work's doors (Lead-decidable at `lead`/`planner`, the Owner's at `owner`):**

- <a call the Planner could not settle in the brief but whose options are all reversible on the branch>

## Units, in order

One row per published change (stack) or commit group (single change). `kind` selects the gate:
`refactor` | `behavior` | `tests` | `ui` | `docs`.

| Id | Title | Kind | Model | Branch | Acceptance checks (runnable) | Device screens |
|---|---|---|---|---|---|---|
| U1 | | | | `<branch>` — per the project hook → Naming | | |

`kind` is what the profile reads to pick this unit's Worker variant and session effort, so it is
never left blank; a blank one is read as the judgment group. `model` is blank unless this unit
**departs** from the profile — the Opus gate review is the net either way. Rotation starts a fresh
session per unit, which is what makes both choices per unit.

Per-unit LOC-of-logic ceiling: 300 — a ceiling, not a target. A unit that grows past it is
split, logged, not finished as one; a unit far under it is not evidence the split was right.
Fewest units that each stay reviewable.

## Scope paths

Pathspecs the Robowright Session may commit under, one per line, git pathspec syntax (a directory,
a file, or a glob). Written to `<session_dir>/scope.txt` at preflight and passed to every commit
through the profile's commit tool (→ Tools). A refusal names the file outside the
list; the path may be added here **only** with a ledger entry saying why the unit needs
it — that entry is the stop-and-ask, done in writing. Leave empty to disable the check.

```
<path/to/feature/>
<path/to/feature/tests/>
```

## Verification standard

Defaults by `kind`; a unit row may add to these, never remove.

- **all**: builds; scoped suites pass with the verdict lines the project hook → Tests names,
  read its one sanctioned way, quoted — never from a grep of the log.
- **refactor**: the hook's equivalence check (→ Kind checks) on every moved file; no behavior change.
  A refactor that **migrates untested logic** also carries the section "Behavior table" below:
  tests are written from that table against the new shape and seen red before the logic
  moves, every `suspect` row is preserved as observed, and the new tests owe the **tests**
  standard plus one quiet-fix mutation per suspect.
- **tests**: predicted kill set written before mutating; one mutation per new test file
  that must redden it; a test nothing reddens is deleted and logged.
- **behavior**: spec first — `worker-spec` writes the behavior table and the failing tests from
  this brief before the unit is implemented, so the unit row's acceptance checks state the
  **rules in the domain's words, with the examples and boundaries already known**; what it
  leaves open becomes an `Assumed` row or a stop. Red evidence before the first implementing
  commit; no Given, When, or Then changed without a `Spec dispute` entry; the spec tests then
  owe the **tests** standard below.
- **ui** / **behavior**: the `smoke-test` agent lane on each listed screen; the oracle
  written down before the check runs, the hook's device predicate as the check, a screenshot as the
  record, `blocked` and `unverified` reported as themselves rather than as clean.
- **end of stack**: adversarial review of the whole diff, then the sweep below.

## Behavior table *(only when a unit migrates untested logic — delete otherwise)*

From the exploration doc's §3.4. The table is the unit's oracle; the Robowright Session does not
re-extract it, and corrects it only through a `Table correction` ledger entry.

| | |
|---|---|
| Unit | `<unit id>` |
| Table | `<project_dir>/Agent Explorations/<unit>-behaviors.md`, extracted at `<sha>` — copied to `<session_dir>/evidence/<unit>-behaviors.md` at intake |
| Suspects | `<ids>` — **all preserved as observed**, per the Owner `<date>`. A fix is not in this brief |
| Observe on the base build (tier 2) | `none` \| `<row ids>` \| `all observable` — the Owner's risk call, `<date>`. Never widened or narrowed by the Robowright Session |
| Dropped on purpose | `<dead branches and unobservable writes the migration does not carry over, with file:line>` — so the reviewer does not report them as lost logic |

## Sweep screens (end-of-stack regression)

Base build vs tip build, same device, same walk. A predicate that holds on base and fails on
tip blocks.

**A starting guess, not the final list.** End-of-stack step 4 rebuilds it from the real diff
via `smoke-test`'s surface inventory, which supersedes this table — a screen here that the
inventory does not reach still gets swept, but the inventory adds what a planner could not
see before the code existed.

| Screen | Launch entry point | Predicates (project hook → Device) | Expected diffs |
|---|---|---|---|
| `<screen>` | `<deep link or route>` | `<predicate>` | None |

## Invariants and hotspots for the adversarial reviewer

- Invariant: …
- Hotspot: `<file>` `<symbol>` — why it is risky

## Landmines

Known traps in this area, one line each, with the file.

## Out of scope

Named, so the reviewer does not report them and the Robowright Session does not fix them.

## Read first

Files and docs to read before touching code, in order.

## Smoke scope

Planner-time **inputs** to the smoke pass, not the pass itself. The real documents are built at
the end of the stack with the `smoke-test` skill — surface inventory, the
unattended agent pass, and `MANUAL-PASS.md` for the Owner. Everything here is a claim that skill
re-verifies against the diff.

| | |
|---|---|
| Expected tier | `Quick` \| `Standard` \| `Deep` — and one sentence on why |
| Surfaces that need a human | The ones no predicate can settle: animation, layout judgment, feel |
| Surfaces the agent should settle | Reachable by an entry point, with an observable predicate |
| Known-noisy screens | Ones that produce false fails; named so they are not chased |
| Accounts / flags / seed state | What the pass has to start from |

If a `touched`-class surface is expected (a refactor reaching a screen), say so here — that
is what obliges the **base** build too, and it is the item most often missed at planning time.
