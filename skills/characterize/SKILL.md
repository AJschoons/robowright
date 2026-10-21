---
name: characterize
description: Extracts a behavior table from existing, untested code before it is migrated, so the migration has a guardrail written in product language rather than in the source's branches. Use when moving logic out of a view controller or view into a view model, migrating architectures, porting a feature to another platform (iOS to Android), consolidating or rewriting legacy code with no tests, chasing coverage on migrated logic, or whenever the contract is "no behavior change" and nothing executable proves it. Hands off to bdd for the tests and to load-bearing-tests once they are green.
---

# Characterize

A migration's contract is "no behavior change", and on untested code nothing checks it. Tests
cannot be the guardrail because there are none, and the code's own `if`/`else` cannot be the
language of the guardrail because the migration is about to change it. So build the missing
thing: a **behavior table** — what the code does, as a user or a collaborator would see it —
extracted before anything moves, used as the oracle for tests against the new shape, and thrown
away when those tests exist.

This is `bdd` run backwards. There, an expected value never comes from the implementation. Here
it comes from nowhere else. The two skills share the table format and meet at `bdd` step 3.

Aviation has worked this way for decades (DO-178C): tests come from requirements; structural
coverage only checks the tests are *adequate*; code no test reaches is either a missing
requirement, dead, or deliberately deactivated — never a reason to write a test from the code.

## The one rule

**A row says what the code does — not what it should do, and not how it does it.**

- *Not what it should do*: a bug is characterized as it behaves, marked `suspect`, and preserved.
  Fixing it is a behavior change, and that is the Owner's call, never a side effect of describing it.
- *Not how*: a row that would stop being true when the code is restructured is written in the
  wrong language. **Branches choose the examples; the table never mentions them.** The test of a
  row: would it read the same about the old view controller, the new view model, and a port to
  another platform?

## When it applies

| Situation | Do |
|---|---|
| Logic is moving and has no tests — VC → view model, architecture migration, consolidation, rewrite | **The loop below** |
| Porting a feature to another platform | The loop, in **port mode** (end of this file) |
| The code already has behavior-level tests | Keep them as the guardrail; characterize only what they do not reach |
| Both old and new can run side by side in one process | Golden-master / approval tests are strictly stronger — use them, and this only for what they cannot see |
| A pure move, rename, or signature change | The project hook → Kind checks `refactor` row; no table owed |

Scope is the **migration unit** — the logic that is moving — and the rows are written at **user
level**: what someone using the app, or a collaborator on the other side of a port, would
observe.

## The loop

Copy this checklist into your working notes and tick it as you go.

```
- [ ] 1 Vocabulary  events in · product states (each mapped to the flags behind it) · observable outcomes
- [ ] 2 Extract     one row per behavior, a concrete example traced through the code, exact constants
- [ ] 3 Trace       every decision point and every outcome statement → a row or a disposition; unaccounted = 0
- [ ] 4 Fidelity    each row checked by the strongest tier it allows; tier-2 observation is the Owner's risk call
- [ ] 5 Suspects    every suspect, and every fact you could not get, in front of the Owner before code moves
- [ ] 6 Hand off    bdd step 3: tests from the table against the new shape, red first, then migrate
- [ ] 7 Delete      the table goes when the tests are green and proven; the test names are what remains
```

### 1 · Vocabulary

Before any row, three short lists — mechanics in `reference/extraction.md`:

- **Events in** — everything that can make this code run: user actions, lifecycle, delegate and
  notification callbacks, observers, timers, calls from other types.
- **Product states** — the situations the code distinguishes, named as a user would ("a sync is
  in flight", "a failure was dismissed"), each mapped to the flags and properties that encode
  it. Legacy code keeps its state machine implicit in booleans; naming it is half the work, and
  the mapping is what lets a reviewer check you. Not every state has a flag: **anything
  pending is a state** — a scheduled closure, a request in flight, a running timer — and so is
  state kept in a control (`applyButton.isEnabled` doing the job of a guard).
- **Observable outcomes** — what a user sees or feels, and what leaves through a port: network,
  persistence, analytics, navigation, haptics, accessibility announcements, and **time** —
  a delay, debounce, or timer is a port the new shape will need a seam for.

Rows are sentences over these three lists. A word in a row that is in none of them is either a
missing entry or source language leaking in. When a user-facing name is not in the code — it
lives in a storyboard or a remote config — quote the identifier, mark it `label unknown`, and
add it to the facts needed (step 5).

### 2 · Extract

One row per behavior — `bdd`'s Given / When / Then, with the source column replaced by where it
was observed and what is owed on it:

| # | Given | When | Then | Observed at | Status | Tier | Test |
|---|---|---|---|---|---|---|---|
| B7 | A sync is in flight | It finishes with a server error | "Sync failed" with retry; `sync_finished ok=false` is tracked | `SyncStatusVC.swift:20-25, 44-47` | Preserve | — | |

One Given, one When, one Then per row; each boundary is its own row. **A row generalizes
nothing**: "(any control or Reset does the same)" is a claim nobody traced — trace it as its
own row or drop it. A Then that says "as B16" inherits B16's mistakes, so when a row is
corrected, grep the table for its id and re-check every row that leans on it. `Tier` stays `—` until
step 4 and `Test` empty until step 6. The SHA goes in the table's header when one covers every
row; the file name stays in each citation whenever the unit spans more than one file.

- **A concrete example, traced.** Pick real input values and walk them through the code line by
  line; the Then is where the walk ends, with the **exact** strings, constants and payloads.
  Read what the code does, not what its names promise — a method called `resetState()` that
  resets two of three fields is the row. This is Feathers' "assert something wrong and read the
  actual", done by hand because there is no harness.
- **Grids find the rows you would not think to write.** For event-and-flag logic, lay product
  states against events: every cell is an outcome, "nothing happens", or "unreachable" — and a
  cell you cannot fill is a row you have not traced. For combinational logic, conditions against
  outcomes, merging conditions that do not matter. Most units need both, and more than one of
  each: one grid per independent dimension of state, crossing two only where an outcome depends
  on both. Grids are working paper; only rows go in the table.
- **The field sweep finds what is not there.** The trace in step 3 can only walk code that
  exists; the worst legacy behaviors are omissions. For every stored field: which events write
  it, which outcomes read it — then, for every event whose name or doc comment says it touches
  the whole ("reset", "clear all", "apply", a payload "of the filters"), which fields it
  skips. A reset that leaves one filter on has no branch to find it by.
- **Guards the UI made unreachable become reachable.** A view model's methods can be called
  directly, so a guard that could never fire because the button was disabled in that state is
  a row — marked `api-only`, so nobody tries to observe it in the app.
- **Beyond the branch.** Ordering of effects, anything that hops a queue or awaits, defaults and
  fallbacks, once-only guards, what happens on the second call, what is captured and for how
  long, and where it can trap. None of these is an `if`, and they are where migrations break.
  The checklist is in `reference/extraction.md`; every heading gets an answer, even "none".
- **Status** is `preserve` by default; `suspect` when the behavior looks unintended (say why in
  one clause); never anything that means "fixed".

### 3 · Trace — the completeness gate

Walk the code once more, mechanically, in the other direction. Two things are counted, each
once, and each maps to at least one row or gets a disposition:

- every **decision point** — `if`, `guard`, `switch`, ternary, `??`, `?.` on something that can
  be nil, `&&` / `||` that short-circuits an effect, `try?`, early return, loop condition,
  `catch`, a boolean expression assigned straight to an outcome — **with every arm mapped**;
- every **outcome statement** — a write to anything the user sees or feels, and every call out
  through a port — *whether or not it sits inside a branch*. `button.isEnabled = false` on a
  straight line is as easy to lose in a move as any `else`.

| Disposition | Meaning | Owed |
|---|---|---|
| `dead` | Cannot execute; say why, with the `grep` that shows it | Reported to the Owner; not migrated, not tested |
| `defensive` | Guards a state the type system or lifecycle already excludes; no outcome to observe | One line of why |
| `unobservable` | Runs, but nothing a user or port can see changes — a write overwritten before it is read, a check whose removal would change nothing | Reported; these are usually findings |
| `incidental` | Diagnostics with no product meaning (debug logging) | Named, so the migration keeps or drops it on purpose |
| `undetermined` | Whether it can execute depends on a fact not in the code — a storyboard value, a caller's habit, a server's contract | The fact goes to the Owner in step 5; write the row as if reachable; it blocks hand-off until answered or the Owner accepts it open |

**The gate is `unaccounted = 0`.** A decision point or outcome statement with no row and no
disposition is a behavior you have not characterized. This is what coverage was standing in
for: if every one maps to a row and every row gets a test, coverage follows — and after the
migration an uncovered line in the new code is invented behavior or dead code, and either is a
finding. Never close a gap by writing a test from the branch; write the row it belongs to.

The table's header carries the tally from here on, so nobody mistakes an unchecked table for a
verified one:

```
Rows: 13 · tier 1: 0 · tier 2: 0 · tier 3: 0 · unchecked: 13
Trace: 8 decision points + 13 outcome statements → 17 mapped, 3 dead, 1 unobservable, 0 undetermined, 0 unaccounted
Suspects: 4 rows, 3 causes — B4 · B9, B10 · B13
```

### 4 · Fidelity — is each row true?

Completeness is mechanical. Fidelity is the weak link: a row can be traced, plausible, and
wrong. Check each row by the strongest tier it allows, and record the tier in the table:

1. **Pin** — the old code has a seam a test can reach: write the characterization test against
   the old code, read the actual, keep it until the migration lands.
2. **Observe** — no seam, but the behavior is visible in the running app: run the **base build**
   and watch it happen. *Optional, and the Owner's decision* — see below.
3. **Refute** — everything else: a fresh-context reader gets the table and the code, not your
   reasoning, and tries to break each row by tracing its example independently. Prompt and
   output shape in `reference/fidelity.md`. It is the weakest tier — the best model on a
   reading-only equivalence benchmark scored 78% against a 50% baseline — so a tier-3 row is
   labeled as such wherever the table is shown.

**Tier 2 is a risk judgment, so put the judgment in front of the Owner rather than making it.**
After tier 3 has run, present: the rows that qualify (user-visible, reachable in the simulator),
why each is risky — `suspect`, refuter disagreed, depends on timing or ordering, state
accumulated across several events, costly if wrong — what observing them costs (a base build,
a simulator, roughly a minute or two a row), and your recommendation: none, the risky subset, or
all. The Owner picks. Unattended, the brief carries the Owner's answer; with no answer, observe nothing and say
so. The run itself is `smoke-test`'s agent lane pointed at the base build — oracle written
first, predicate as the check, screenshot as the record (`reference/fidelity.md`).

A row a tier disproves is corrected **in the table first**, with what the code actually did.
If extraction and refuter cannot settle it by reading, that row is a tier-2 candidate by
definition.

### 5 · Suspects, and the facts you could not get

Two lists go to the Owner before code moves.

**Suspects, grouped by cause** — three rows that are one never-cleared flag are one question.
Each asks: *preserve, or fix as a declared behavior change?* Default, and the only option
unattended, is preserve — the test pins the odd behavior, its doc comment ends `(suspect B9)`,
and the PR description lists it. A fix is its own commit with its own row, never folded into the
move.

**Facts needed** — everything the code could not tell you and a row depends on: a storyboard's
slider minimum, whether the presenter reuses the instance, what a delay is for, a label that
lives in a nib. Each names the rows and `undetermined` dispositions waiting on it. A suspect
that hinges on a fact is asked as the fact first. Unattended and unanswerable, the rows stay
written as if reachable, marked, and the hand-off says what is open.

### 6 · Hand off

Into `bdd` at step 3, with the table as the requirement and every row sourced `observed at
<sha>`: tests against the **new** shape — a skeleton view model that decides nothing — one red
run, then migrate until green without touching a Given, When, or Then. Then `load-bearing-tests`.
One mutation is always worth running: **quietly fix a suspect** and confirm exactly its test
fails — that is the guardrail doing the job it was built for. After the migration,
the table is the input to whatever equivalence check the project hook → Kind checks names.

### 7 · Delete

The table is scaffolding. It lives with the project's planning documents or the session's
evidence, never in the repository, and its line citations start rotting the day the code moves.
Row ids stay in the table's `Test` column and out of the source. When the tests are green and
proven, the behavior sentences in the test names are the durable record, and the code is the
source of truth again.

## Port mode

Same loop, with the new side on another platform — the two sides can never run in one process,
so the table is the only thing both can be checked against.

- Add a **verdict** column for the new side: `EXACT` · `APPROX (the delta)` · `GAP (priority)` ·
  `CUT (the scope decision it cites)`. Platform idiom is a legitimate `APPROX`; it is written
  down, not assumed.
- **No extras.** Invented behavior is the documented failure of AI ports. Anything on the new
  side with no row is a finding, however helpful.
- If the old side has tests, read them — they state intent the source does not — but a row
  still cites code.
- For pure logic, consider turning rows into a **shared fixture file** both platforms' test
  suites consume (JSON vectors read by XCTest and JUnit, with a per-case list of platforms
  allowed to diverge). That artifact outlives the port, which is the point of it, and the
  reason it is a separate decision from this table.

## Excuses, and what is true instead

| The thought | The reality |
|---|---|
| "I'll cover every branch; that's the same thing." | Tests shaped like the old branches break on the first refactor and pass on a wrong one. Branches pick the examples; rows say what happens. |
| "This is obviously a bug, I'll fix it while I'm here." | Someone may depend on it, and a fix inside a move is invisible in review. `suspect`, preserve, ask. |
| "The name tells me what it does." | Names are where models hallucinate behavior. Trace the example. |
| "I read it carefully; it doesn't need a second reader." | A second look from the same context does not find your misreading. A fresh one with a concrete input does. |
| "It's just logging / analytics, not behavior." | It leaves through a port, someone's dashboard depends on it, and it has no branch to remind you. It gets a row. |
| "The gate is at 3 unaccounted, close enough." | Those three are the behaviors nobody described. That is the whole list of what the migration can silently lose. |
| "I'll keep the table as documentation." | It cites lines that are about to move. In three days it is wrong and someone trusts it. |

## Reference

- `reference/extraction.md` — where events and port calls hide in UIKit and SwiftUI code, the
  beyond-the-branch checklist, the two grids with examples, and the altitude test for a row.
- `reference/fidelity.md` — the three tiers in detail: pinning through a seam, the tier-2 risk
  call and observation run, and the refuter's prompt and output.
- `reference/worked-example.md` — a view controller's sync banner through all seven steps: the
  state grid that finds three suspects, the trace that finds a dead branch and a dead write,
  and the compiled view-model tests that catch a quiet fix.
