---
name: bdd
description: Behavior-first, test-first workflow (BDD) for any change that adds or alters behavior. Use before writing implementation code for a feature, a behavior change, or a bug fix; when writing, naming, structuring, or reviewing unit tests; when deciding what to test or where an expected value should come from; when turning a ticket, brief, or acceptance criteria into tests; and for Given/When/Then, TDD, red-green, Swift Testing or XCTest suite design. Hands off to load-bearing-tests once the tests are green.
---

# Behavior first

`load-bearing-tests` proves a test **can fail**. It cannot prove the test pins the **right**
behavior: a test written after reading the code inherits the code's mistakes, and mutation then
certifies the mistake (`load-bearing-tests/reference/failure-modes.md` #7). The measured version:
an LLM shown buggy code writes tests that affirm the bug and fewer that catch it; given the
specification instead, both reverse ([ISSTA 2026](https://arxiv.org/abs/2607.22883)). This skill
is the half that comes first — it decides *what* the tests say. That skill decides whether they
can say it.

BDD here is the discipline, not the tooling: rules and concrete examples agreed **before** the
code, then expressed directly in Swift Testing or XCTest. No Gherkin, no feature files, no new
dependency — that layer pays only when a non-programmer reads it.

## The one rule

**An expected value comes from the requirement, never from the implementation.** Everything
below is a consequence: the tests exist, and have been watched failing, before the code that
satisfies them does — because that ordering is the only evidence the oracle was not copied from
the answer.

## When it applies

| The change | Mode |
|---|---|
| New behavior, a behavior change, a bug fix | **The loop below**, in full |
| Tests for code that already exists, a migration of untested logic, a port | **The `characterize` skill first**: the expected values *are* the current behavior, extracted into the same table with every row sourced `observed at <sha>` — then this loop from step 3 |
| Pure rename, move, forwarder, data-only type, docs, layout with no logic | None — `sizing-the-move` rule 4; layout goes to `smoke-test` |
| A spike to learn whether something is possible | None while spiking; then **delete the spike** and start at step 1. Code written before its test does not get tests retrofitted around it |

## The loop

Copy this checklist into your working notes and tick it as you go.

```
- [ ] 1 Discover   rules, examples, questions — from the requirement, before opening the code under change
- [ ] 2 Formulate  behavior table written; every row names where its expected value came from
- [ ] 3 Red        tests written from the table; one run; each fails on its Then — quoted
- [ ] 4 Green      simplest general implementation; no Given, When, or Then edited
- [ ] 5 Prove      load-bearing-tests, owed first by any test that was green at step 3
- [ ] 6 Report     table changes after red, disputes, tests green at red, questions defaulted
```

### 1 · Discover

Read the requirement — ticket, brief, acceptance criteria, design, the Owner's message — and split it
into three piles (Example Mapping, minus the index cards):

- **Rules** — one sentence each, in the domain's words. "An upload never leaves less than the
  quota floor free."
- **Examples** — concrete cases that illustrate one rule, with real values: the ordinary case,
  each boundary, the case where two rules collide.
- **Questions** — anything the requirement does not settle. *"At exactly the floor — allowed?"*

A question is **never resolved by guessing and encoding the guess as an assertion** — that is
how a misreading gets a green test defending it. Attended: put the pile to the Owner as a `grilling`
round, your proposed default as each **Rec**. Every Question earns a slot — each one changes a
Then — and the Owner's answer becomes the row's source (`the Owner, <date>`), so the table is the pass's record.
Unattended: take the defensible default, record it as `Assumed`, and mark the row so the
reviewer sees an assumption rather than a fact. The test for "settled by the wording": could
two competent readers take it differently? Then it is `Assumed`, however sure you are — quote
the wording *and* mark it.

Many rules means the work is more than one unit. Many questions means it was not ready: when
`Assumed` rows reach half the table, carry on, but the report **leads** with that count and the
questions — every answer changes a Then, so the work is not done until someone answers them.

Read existing code for **seams and vocabulary** — what is injectable, what the domain calls
things. Not for answers.

### 2 · Formulate — the behavior table

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R1.2 | Keeps the floor free | 80 MB free, floor 50 | A 30 MB attachment is uploaded | Allowed | Ticket: "leave at least 50 MB free" → at the floor is allowed |

The last column is the point of the table. Legal entries: the ticket or brief (quoted), the Owner
(dated), a design or spec (linked), a platform contract (doc link), `pre-change behavior at
<sha>` for characterization, `Assumed: <default>` for a defaulted question. **Never**: "the
implementation", "ran it and copied the output" for new behavior, or blank.

One row per example; one **When** per row. More than about six rows for one rule, or rows whose
Whens chain (`when… then… when…`), means split.

Attended, **show the table before writing tests**. It is the cheapest moment to correct a rule,
and it is the conversation BDD is named for. Do not wait for approval unless a question is open.
Unattended, write it where the run keeps its evidence or working notes, before the tests.

### 3 · Red

Write the tests from the table — shape and naming below, Swift mechanics in
`reference/swift.md`. For API that does not exist yet, add the smallest skeleton that compiles
and decides nothing: a constant return, never `fatalError` — a crash is not a red. Pick a
constant **no row expects** (`-1` for a count) so every test can be seen failing; when the
return type leaves no such value — a `Bool`, a small enum — some test will be green at red.

One run for the whole table — batch by table, not by test. Where a run costs minutes that is
mandatory; where it costs seconds it is still enough. Then read every result:

- **Fails on its Then** — correct. Quote the line: test name, expected, actual.
- **Fails any other way** — compile error, crash, fixture, timeout: not red. Fix the test.
- **Passes** — not done, *unproven*. Either the skeleton's constant matches (unavoidable when
  the outcomes partition the return type), or the behavior already exists and the row is a
  characterization. Mark it; it owes its kill first at step 5.

### 4 · Green

Implement the **rule**, not the examples — the examples are samples. A branch that exists to
satisfy one row's literal values is special-casing, and the first unlisted input exposes it.

Tests are read-only in this step, with one distinction:

| May change | May not change |
|---|---|
| **Plumbing** — construction, type and parameter names, which seam the fake plugs into — when the design moved | A **Given** value, the **When**, a **Then** |

When a Then looks wrong, that is a dispute, not an edit: go to the row's source. Source agrees
with the test → the code is wrong. Source is ambiguous → it was a question all along; ask or
default it, change the **table first**, then the test, and report the change. If the behavior
cannot be implemented as specified, say so rather than bending the test until it passes.

Then refactor with the suite green. A test that breaks under a behavior-preserving refactor was
pinned to structure — fix the test's coupling, not the refactor.

### 5 · Prove

Hand the green tests to `load-bearing-tests`: predicted kill set, mutations, reconcile. Tests
marked unproven at step 3 go first, and boundaries in the table are where their mutations live
(`<=` → `<` kills the at-the-floor row or nothing does). Before mutating, add **one held-out
example per rule**, derived from the rule after green and predicted to pass — a failure means
the implementation fit the listed rows rather than the rule. Held-out rows join the table
marked as such, sourced like any other; keep the ones that reach a branch no other row does
(they then owe a kill too), drop the ones that duplicate a row. They are reported, not counted
as a table change after red.

### 6 · Report

To the Owner, only what they could disagree with: rows whose source is `Assumed`; any table change
after red, with the reason; disputes and how the source settled them; tests that were green at
red and what killed them. The table itself goes in the PR body or the unit's evidence.

## What a test says

- **One behavior per test**: one When, and Thens about one outcome. Parameterize examples of
  the same rule (`arguments:`); never loop or branch inside a test.
- **The name is a sentence: outcome, then condition.** The check — *would this name survive a
  rewrite of the implementation?* `test_decide__returnsDeclined` would not.
  - Swift Testing: `@Test("declines an upload that would dip below the floor")` on
    `func declinesUploadDippingBelowFloor()`; suites named for the capability and nested per
    rule or context.
  - XCTest: `test_<outcome>__<condition>` — `test_declinesUpload__whenItWouldDipBelowFloor`.
  - Adding to a suite that uses another scheme: keep its prefix, make the rest say outcome and
    condition. Renaming tests you did not write is out of scope.
- **Given holds what this behavior depends on and nothing else.** Everything incidental lives in
  a `given…()` helper's defaults — and those defaults are distinct and non-zero, so a crossed
  wire shows (`failure-modes.md` #1, #3).
- **Real values in domain words.** `freeMB: 79`, not `value1`. A reader should be able to
  check the arithmetic against the rule.
- **Through the public surface.** No asserting on privates, call order, or which helper ran.
- The doc comment stays `load-bearing-tests`' one line: `/// <behavior protected> — <what goes
  wrong if it breaks>`. Swift Testing prints it under a failure. A test pinning an `Assumed`
  row ends that line with `(assumed Q4)`, so the assumption is visible where the test fails.

## Doubles

The unit is a **behavior**, not a class — a test may run several real types together, and
usually should. Replace only what is slow, nondeterministic, or outside the process, at the port
where it enters: network, persistence, clock, location, notifications.

Prefer **real → fake → mock**, and **state → interaction**. Assert a call only when the call
*is* the effect — analytics, navigation, an outgoing request. Agents over-mock measurably —
mocks added in 36% of agent commits against 26% of non-agent ones
([MSR 2026](https://arxiv.org/abs/2602.00409)) — and a test that reads back what it stubbed
tests the mock (`failure-modes.md` #6).

## Bug fixes

The bug report is the requirement. Row one is the reproduction: Given the reported state, When
the reported action, Then **the correct outcome, from the report or the original spec** — not
from reading the broken code to see what it "meant". Red on the unfixed tree is the regression
baseline `load-bearing-tests` asks for; you get it for free by doing the steps in order.

## Excuses, and what is true instead

| The thought | The reality |
|---|---|
| "Too small to need the table." | Then the table is three rows and two minutes. The boundary you would have guessed is one of them. |
| "I'll write the tests right after." | Tests written after are derived from the code. They pass immediately, prove nothing about the requirement, and mutation will certify them anyway. |
| "I already know what it should do." | Then the source column is quick to fill in. If a cell is hard to fill, you did not know. |
| "The test is wrong, I'll just fix the expected value." | That is a dispute. Source first, table second, test third — and it gets reported. |
| "I need to see the implementation to know the API." | You are designing the API; the test is its first caller. Read seams and vocabulary, not answers. |
| "It passed first time, so it's done." | It has never been seen failing. It is the least proven test in the file. |
| "I wrote the code already; I'll keep it as reference." | Reference is contamination. Delete it, or call the work a characterization and source the rows to `pre-change behavior`. |
| "A mock is easier here." | Easier to write, and it asserts your own stub. Fake the port; assert the state. |
| "The run is expensive, I'll skip red." | One red run per table, not per test. Skipping it is what makes every later green meaningless. |

## Reference

- `reference/worked-example.md` — one requirement through all six steps, with the real red,
  green, and mutation output. Read once before the first use.
- `reference/swift.md` — Swift Testing and XCTest mechanics: nested suites, `init` as the shared
  Given, `arguments:` tables, fakes at ports, Given/When/Then in XCTest and UI tests.
- `reference/scenario-smells.md` — the documented ways examples and tests go wrong, each with a
  before and after. Read while writing the table, and when reviewing someone else's tests.
