---
name: spend-debug
description: Find the cuts in a project's, a unit's or a period's Robowright spend — runs robowright-cost.py, walks a fixed six-item checklist, and reports each cut with the number behind it and what it would save. Writes nothing. Manual invocation only.
disable-model-invocation: true
model: sonnet
argument-hint: "<project> | <unit slug> | --since YYYY-MM-DD  [--accounting-root DIR] [--projects-root DIR]"
---

# spend-debug

A Reviewer (reviewer) on Sonnet: an enumeration of the accounting ledger against a fixed
checklist. Every command below is a read — `robowright-cost.py --by`, `jq`, `ls`. The report
goes to the Owner in chat and nowhere else. `robowright-cost.py --migrate` appends to the ledger,
so it is the one mode of that script this skill leaves to the Owner.

Every number in the report is **sourced**: it is a value a command printed, or arithmetic on such
values with the formula shown. An item whose number the ledger does not carry names the file it
read instead, or says it cannot be judged from the ledger.

## 1 · Scope and paths

The argument names the scope: a project (`demo`), a unit slug (`demo-001-alpha`), or
`--since YYYY-MM-DD`; a project and `--since` combine. `--accounting-root` and `--projects-root`,
when given, win over everything below.

Paths, as an installed clone resolves them:

| Name | Path |
|---|---|
| `COST` | `~/.claude/skills/robowright/scripts/robowright-cost.py` |
| `PRICING` | `~/.claude/skills/robowright/pricing.json` |
| `LAUNCH` | `~/.claude/robowright/launch.json` |
| window | `jq .autoCompactWindow ~/.claude/settings.json` |

- **Accounting root** `ROOT`: `--accounting-root`, else `$ROBOWRIGHT_ACCOUNTING_ROOT`, else
  `jq -r '.accounting_root // empty' "$LAUNCH"`, else `accounting` beside the sessions root
  (`$ROBOWRIGHT_SESSIONS_ROOT`, else `jq -r '.sessions_root // empty' "$LAUNCH"`, with its
  symlinks resolved) — the order `robowright-cost.py` resolves by. The ledger is
  `L="$ROOT/records.jsonl"`. Pass `--accounting-root "$ROOT"` to every `COST` call so the rollups
  and the queries read one file.
- **Project config**: `<projects root>/<project>/robowright.json`, the projects root from
  `--projects-root`, else `jq -r '.projects_root // empty' "$LAUNCH"`. For a unit scope the
  project is the `project` field of that unit's records.
- **`~/` paths**: `launch.json` writes paths as `~/…` and `jq -r` returns them literally, so
  expand a leading `~/` in every path from `LAUNCH`, the environment or an argument before
  using it — `ROOT="${ROOT/#\~/$HOME}"` — as the script does.

Done when `ROOT`, `L`, the window and the config path are each printed with the command that
found them, or named as missing. A missing window leaves item 1 not judged; a missing config
leaves item 3 not judged; a missing `LAUNCH` leaves item 2's launch mode not judged; the other
items run.

## 2 · The reads

Run these once, in this order, and keep each output for the report's Sources.

```sh
for by in role model unit unit-id; do python3 "$COST" --accounting-root "$ROOT" --by $by [--project P] [--since D]; done
```

A unit scope runs them with no `--project` and reads only the slug's rows of `--by unit` and
`--by unit-id`; its role and model split comes from the session table below, since
`robowright-cost.py` has no unit filter.

**The session table** — one row per Claude session, role and model, with the fields the rollup
does not print (`p`, `u`, `s`: project, unit slug, since date; `""` for any not given):

```sh
jq -nrR --arg p "$P" --arg u "$U" --arg s "$D" '
  [inputs | fromjson? | select(type == "object" and .scope == "session"
     and ($p == "" or .project == $p) and ($u == "" or .unit == $u) and ($s == "" or (.at // "")[0:10] >= $s))]
  | group_by([.session_id, .role, .model])[]
  | [.[0].session_id, .[0].role, .[0].model, (.[0].session_dir // "-"), (map(.requests) | add),
     ((map(.input_tokens + .cache_read_tokens + .cache_write_tokens) | add) / (map(.requests) | add) | floor),
     (map(.input_tokens) | add), (map(.output_tokens) | add), (map(.cache_read_tokens) | add),
     (map(.cache_write_tokens) | add), (map(.estimated_usd // 0) | add * 100 | round / 100),
     .[0].wall_seconds, .[0].active_seconds] | @tsv' "$L"
```

Columns: session, role, model, session dir, requests, average context, input, output, cache
read, cache write, estimated USD, wall seconds, active seconds.

**The unit table** — unit-scope records by unit, unit id and role: the same `jq` with
`.scope == "unit"`, grouped by `[.unit, .unit_id, .role]`, printing unit, unit id, role,
requests and estimated USD.

**Each session directory** the session table names, once however many sessions share it:

```sh
jq '{ticket, compact_pct, rotate_sessions, model, stop_reason, units: [.units[] | {id, model, gate_attempts}],
     extra_reviews: .verification.extra_review_subagents_used, extra_max: .verification.max_extra_review_subagents}' "$DIR/run.json"
jq -cR 'fromjson? | select(.event | IN("unit-close", "request-rotate", "rotation-resumed", "stop", "resume"))
        | {at, event, unit, code, actor}' "$DIR/events.jsonl"
ls "$DIR/reviews"
```

Plus `jq . "$PRICING"`, `jq -r .launch "$LAUNCH"`, the project config, and the Budget section
of `~/.claude/robowright/profile.md`, which says whether the machine bills a subscription or an
API key. The ledger says neither, and the plan decides two things below: the main session's
cache TTL (1 hour on a subscription within plan usage, 5 minutes on an API key,
`~/.claude/skills/robowright/DESIGN.md` §5), and whether USD is what the Owner pays.

**Rates.** A model id takes the `PRICING` row of its longest matching key, else `default`, in
USD per million tokens. In every formula below, `input`, `output`, `cache_read` and
`cache_write_5m` are that row's rates, and token counts are named as counts. The ledger does not
split cache writes by TTL, so a cache write is priced at `cache_write_5m`. Give each saving as
tokens first — the formula's count before its rate — then the USD estimate. On a subscription
the tokens are what a cut saves and the USD only compares cuts
(`~/.claude/skills/robowright/OWNERS-GUIDE.md` → Accounting); item 3's repricing has no token
saving, so say so there. With no pricing file every saving is given in tokens.

## 3 · The checklist, in this order

Each item gives its number, the line it is fine under, the cut, and the saving's formula.

### 1. Average context per request against `compact_pct`

- **Number:** each Worker session's (role `worker`) average context, against its ceiling
  `compact_pct × window / 100`, `compact_pct` from its session's `run.json` (absent: 85, the
  launcher's default).
- **Fine:** the average is at most half the ceiling.
- **Cut:** a lower `compact_pct` in that project's next brief. How far, and the floor, are the
  Owner's call: a ceiling that leaves no room above the fixed base is too low
  (`~/.claude/skills/robowright/DESIGN.md` §2).
- **Saves:** priced for a 10-point step, this checklist's convention rather than a measured one:
  `requests × (0.10 × window / 2) × cache_read / 1e6`. Context climbs from the base to the
  ceiling, so the average falls by half the ceiling's drop; say this model with the number.

### 2. Rotation timing

- **Number:** per session directory, units closed (`unit-close` events), Worker sessions
  (distinct session ids with role `worker`), `rotate_sessions`, and each rotation's wait from
  `request-rotate` to `rotation-resumed`.
- **Fine:** one unit, or at least as many Worker sessions as units closed; and the waits sum to
  under a tenth of that directory's Worker wall seconds.
- **Cut:** a session that carried more than one unit → `rotate_sessions: true` in the next
  multi-unit brief. Long waits → name `launch.json`'s `launch`: in `paste` the next session waits
  for whoever pastes, in `auto` for the Lead's tick.
- **Saves:** for the carried session, `requests × (its average context − the median average of
  the scope's rotated Worker sessions) × cache_read / 1e6`, a rotated session being one in a
  directory with at least as many Worker sessions as units closed; with none in scope, the saving
  is not estimable. For waits, the wall hours; no tokens.

### 3. Model per role against the project's config

- **Number:** the session table summed by role and model: requests and USD.
- **Configured:** `robowright.json`'s `models` — ledger role `worker`, `planner`, `lead`,
  `explainer`, `reader` to the key of that name; `reviewer-code` to `reviewer_code`;
  `reviewer-prose` to `reviewer_prose`. A Worker's brief overrides with `run.json`'s `model` or a
  unit's `model`. `spec` is the `model:` line of `~/.claude/agents/worker-spec.md`. `subagent`
  has no key; the launcher's `--subagent-model` defaults to `sonnet`. A ledger model id matches
  an alias it contains (`claude-opus-5-5` matches `opus`).
- **Fine:** every row matches.
- **Cut:** a row on a dearer model than configured → move it to the configured one. The ledger
  does not record what chose the model, so name the settings that could have: the agent file's
  `model:` line, the brief's `model`, `robowright.json`, the launcher's `--subagent-model`. A row
  on a cheaper model is no saving: report it to the Owner as a quality question.
- **Saves:** the row's USD less its token counts at the configured model's rates,
  `(input count × input + output count × output + cache read count × cache_read + cache write count × cache_write_5m) / 1e6`.
  The configured model's row is the id the ledger shows for that alias in scope, else the
  longest `PRICING` key containing the alias; name the row used.

### 4. Reviewers per unit

- **Number:** from the unit table, each unit's `reviewer-code` and `reviewer-prose` requests and
  USD, and their share of the unit's USD (the sum of that unit's rows); from `run.json`, each unit's `gate_attempts` and the
  session's `extra_reviews` of `extra_max`; the files in `reviews/`. The ledger does not count
  reviewer spawns; `run.json` and `reviews/` do.
- **Fine:** every unit has one gate attempt and the session used no extra reviews.
- **Cut:** a unit with more than one gate attempt → the cut is upstream: name the review that
  held it. Extra reviews used → `verification.max_extra_review_subagents` lowered in the next
  brief of that size, if the Owner judges the gate review enough.
- **Saves:** repeat gates, `unit reviewer USD × (attempts − 1) / attempts`; extra reviews,
  `session reviewer-code USD × extra_reviews / (sum of gate attempts + extra_reviews)`.

### 5. The doc roles' share

- **Number:** from `--by role`, the Planner, Lead and Explainer USD (tokens when USD is `n/a`)
  and their share of the scope's total. Reviewers a doc role spawned are under `reviewer-*`,
  not in this share. Per Lead session: average context, and cache write over cache read.
- **Fine:** each Lead session's average context is at most twice the smallest Lead average in
  scope, and its cache writes are at most a tenth of its cache reads. One Lead session in scope
  leaves the first test not judged.
- **Cut:** a grown Lead → end it and start a fresh one sooner
  (`~/.claude/skills/robowright/DESIGN.md` §3). Heavy cache writes → ticks landing after the
  cache TTL rewrite the whole context (`~/.claude/skills/robowright/DESIGN.md` §5): a tick
  interval under the TTL, or the 1-hour TTL.
- **Saves:** grown Lead, `requests × (its average − the smallest Lead average) × cache_read / 1e6`;
  cache writes, `(cache write − cache read / 10) × (cache_write_5m − cache_read) / 1e6`.

### 6. Idle wall time and Owner stops

- **Number:** per Worker session, wall less active seconds — the stopped time inside it. From
  `events.jsonl`, each `stop`'s code and the minutes to its `resume`, and who resumed it. An
  Owner stop is code `owner-stop`, or a stop the Owner resumed. A stop with no resume and a
  `stop_reason` in `run.json` is a session still stopped. Rotation waits are item 2's.
- **Not judged from the ledger:** a doc role's record carries wall as active, so its idle time;
  and a session waiting at a prompt with no stop, which counts as active.
- **Fine:** no stop, or only `owner-stop`s; report an Owner stop's hours either way.
- **Cut, by code:** `one-way-door` → the brief's authority section decides that class ahead;
  `budget` → the brief's wall allowance; `verification-failed` → item 4's held gate;
  `base-moved` → one session per worktree; `behavior-change` → the brief's contract;
  `owner-stop` → the Owner's own call, no cut.
- **Saves:** for each cut stop, its hours in wall time; and if it outlasted the profile's cache
  TTL, the one re-write of the context on resume, `average context × (cache_write_5m − cache_read) / 1e6`.
  With no profile to name the plan, give the re-write as applying past 5 minutes and past 1 hour
  both.

## 4 · The report

First one line of paths: `ROOT`, the ledger, the window and the config, each with the command
that found it or `missing`. Then one block per item, in checklist order:

```
<n>. <item> — fine | cut
   number: <value>  (<command or file>)
   cut:    <the change, and the file and field it lands in>
   saves:  <USD, tokens or hours>  (<formula with the values>)
```

An item is `cut` when any session or unit in it fails its line: the number gives every one, and
`cut` and `saves` cover the failing ones. A fine item gives the number that shows it and no `cut`
or `saves` line. After the six: **Not
judged** — each item or part the ledger cannot answer, and why; **Sources** — every command run,
in order. Savings overlap (items 1, 2 and 5 all lower context), so the report gives no total.

Done when all six items are present in order, each with a cut or `fine`, and every number traces
to a command in Sources.
