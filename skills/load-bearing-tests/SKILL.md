---
name: load-bearing-tests
description: Prove a new test can actually fail, by editing the code under test until exactly that test reddens — targeted mutation testing, "edit tests", negative controls. Use whenever writing, reviewing, or accepting unit tests; before claiming a test suite covers a behavior; when a regression test is added for a bug fix; or when deciding whether a test is worth keeping. Not whole-suite mutation scoring.
---

# Load-bearing tests

A green test proves nothing about whether it *can* go red. Coverage says the line ran. Review says the
assertion looks plausible. Neither catches a test that passes for the wrong reason — and that is the
default failure mode when the same agent writes both the code and the test, because the assertion and
the bug come from one reading of the requirement.

The only check that catches it: **break the behavior on purpose and confirm exactly the expected test
fails.**

## Scope — what this is not

This is **targeted, diff-scoped, hand-picked** mutation, a handful of edits aimed at behavior you just
wrote or moved, each with its kill set predicted in advance. It is *not* whole-suite mutation scoring
(Stryker/PIT/`cargo-mutants` chasing a percentage). Do not install a mutation-scoring tool, do not
report a mutation score as a quality number, and do not mutate code the change did not touch.

## The bar

Every test in the diff clears one of two bars before it ships:

1. **Killed** — at least one *compiling* edit to the code under test makes this test fail.
2. **Declared guard** — nothing compiling can redden it, but it protects a named, realistic defect
   (a contract a future edit would plausibly break, a crash, a wrong analytics payload). Write the
   defect down; the doc comment and the ledger both say it.

**A test that clears neither gets deleted**, and the deletion is reported. An uncovered path left
uncovered beats a green assertion that cannot fail — the green one stops anyone else from writing the
real test.

Same bar for the inverse: if a behavior you moved or wrote has no test *and* no seam to observe it
through, record it as accepted-untested with the reason. Do not paper over it with a test that passes
either way.

## The loop

**0 · Know the cost first.** Find the cheapest command that runs *only* the suites you are touching,
and time one run. Consult the repo's own build/test skill or rules for the exact shape and flags. If
that number is minutes, batching (step 3) is mandatory rather than an optimization.

**1 · Characterize before writing.** (Arriving from `bdd` with green tests: characterize the new
implementation now, then skip to step 3.) One row per branch of the code under test: inputs, outputs, side
effects, observable in a test yes/no. Flag anything dead or unreachable. This table is what makes the
predictions in step 3 possible; without it you will predict from the branch the code is "for" rather
than from its inputs, which is the single most common source of wrong predictions.

**2 · Write the test.** Doc comment in this exact format, one line:

```
/// <what behavior this protects> — <what goes wrong if it breaks>
```

Name it for the behavior — outcome, then condition — per the `bdd` skill, which also decides what the
test asserts and where its expected value comes from. Arrange through named `given…()` helpers. Assert
**state, not the collaborator**, wherever both exist — "the coordinator wasn't called" is a claim about
the collaborator; "`isSelectionModeEnabled` is still false" is the claim you meant.

**3 · Predict the kill set, in writing, before mutating.** A table:

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|

Predicting first is what makes the run verification instead of narration. Reading the failures and then
explaining them is not verification.

**4 · Apply and run.** Four mutations per batch. Batch only when the mutations touch **disjoint
statements** *and* have **disjoint predicted kill sets** — disjoint predictions alone is not enough,
because two mutations on the same statement mask each other and you get a false "covered".

Mechanics: apply with a direct edit, run the scoped suite, revert with `git checkout -- <file>` (in a Robowright Session, `rw-git restore <file>`). Above
roughly fifty mutations a scripted harness with a catalog and a journal pays for itself — but check the
runner tolerates it first: `xcodebuild` **cannot run from inside a script under the agent sandbox** and
reports every mutation as a compile failure, so under that constraint each run is its own direct Bash
call. Ten `NO-COMPILE`s in a row is a broken harness, not ten broken mutations.

**5 · Reconcile.** Every row resolves to one of four, and three of them are findings:

| Outcome | What it means | Action |
|---|---|---|
| Match | Predicted set == observed set | Nothing |
| Killed by a sibling | *Some* test failed, but not the one this mutation was written to prove | **Not a kill for that test.** An audit can find many "proven" tests with only a sibling's failure behind them |
| Over-predicted | Fewer tests failed than predicted | **Your model of the code is wrong.** Find out why before moving on — it is usually a test asserting something narrower than its name claims |
| Wider than predicted | More tests failed | Usually fine; confirm the extras fail for the right reason |
| Survivor | Nothing failed | Either a missing assertion (add it), a vacuous assertion (fix the fixture), or a genuinely unreachable defect (record it) |

### Record a verdict per mutation, and never collapse two of them

| Verdict | Meaning |
|---|---|
| `KILLED` | A test failed. Confirm it failed for the predicted reason. A trap that takes the test process down is a kill only for the test that was running when it died — name it, and say `by trap` |
| `SURVIVED` | Nothing failed — a hole until proven otherwise |
| `EQUIVALENT` | Cannot change observable behavior, so no correct test can kill it |
| `OUT-OF-TIER` | Only observable on a device / in a UI test / over the network — a real gap this tier cannot close |
| `CHANGE-DETECTOR` | Killable only by a test that would pin an implementation detail; not worth writing |
| `NO-COMPILE` | Neither killer nor survivor; substitute one that compiles |
| `SUITE-DID-NOT-RUN` | Infrastructure noise. Re-run once before investigating |

Collapsing `OUT-OF-TIER` or `CHANGE-DETECTOR` into `EQUIVALENT` **launders a coverage gap into a proof**
— they are the rows the Owner most wants to see. And an equivalence argument is worth no more than a
worthless test unless it was **written down before the run**: register the prediction, then run the
mutant anyway. Reasoning decides what to write, not whether it worked.

`NO-COMPILE` is the verdict most often wrong. A harness that pastes a prose instruction
("(delete line 53)") into source journals a compile failure in zero seconds and it reads like evidence —
such a verdict may never have been compiled. Re-express every one as a
literal replacement and re-run. If no compiling mutation can produce the defect, then it is unreachable
and the test guarding it is the one to delete.

**6 · Leave the tree clean.** `git status` and `git diff` before committing. A mutation left in the
working tree is the worst possible outcome of this technique.

### Three things that silently corrupt a run

- **A flaky test reports `KILLED`.** In a normal gate a spurious failure is loud; inside a mutation run
  it is indistinguishable from a kill, and it is silently wrong. That asymmetry is why it is worth
  hardening a test that is currently passing — a timing ceiling that reads machine speed rather than
  the paced bound will "kill" anything.
- **A mutation anchored by line number can land on the wrong occurrence** — a sibling method's
  identical line — which runs one mutant twice and reads as two kills. Pin every mutation to the text
  it actually replaced, not a line offset.
- **A stale build.** Confirm the run that reported the kill actually rebuilt the mutated file.

And where you have the machine time, **run the mutants you believe are equivalent instead of reasoning
about them.** Reasoning decides what to write; only the run says whether it worked. Survivors have
twice appeared under tests written specifically to kill them.

## The prediction rules that keep being wrong

Distilled from real mutations. Read `reference/mutation-catalog.md` for the operator list; these
five are the reasoning errors:

1. **Mutate a write inside each branch, not only the condition that selects it.** A condition mutation
   proves the branch is reachable and distinguishable. It says nothing about whether the work inside is
   pinned. Condition-only passes are how vacuous assertions survive a full mutation pass.
2. **Predict both sides of a boolean guard.** Inverting a guard swaps two populations; it does not
   narrow one. Name an input on each side.
3. **Making a branch unconditional cannot change the answer for inputs that already took it.** Forcing
   `note.isPinned ? a : b` to always return `a` is caught by the *unpinned* tests, not the pinned ones.
4. **A two-argument `max`/`min` next to a conditional zero is usually a floor, not a comparison.** Ask
   which degenerate case it protects before predicting.
5. **Clamped or interpolated functions need three samples** — below the floor, an interior point, above
   the ceiling. Endpoints prove the clamps and the direction; only the interior proves the slope, and a
   midpoint is immune to `1 - clamp` → `clamp`.

## Regression tests owe a baseline

A test written for a bug fix must be **shown to fail on the pre-fix tree**: stash or revert the fix, run
it, confirm red, restore. A "regression test" never observed failing on the broken code is an assertion
of faith. This is cheaper than a mutation pass and it is not optional — say in the PR body that you ran
it.

## Before designing a suite: prove the seam works

For any dependency whose contract is "call me back", write **one throwaway test asserting the callback
fires at all** before designing anything around it. A completion handler that never fires in a headless
test looks identical to one that fires and does nothing, and it silently truncates every test after the
call. Delete the spike once it has made its argument; record what it showed in the commit message.

## Proportionality

The budget is per *behavior*, not per test: roughly one mutation per distinct branch or write in the
diff, in batches of four. A pure rename, a forwarder, or a data-only struct needs none. A payload built
from six fields needs a mutation per field that a test claims to pin — that is where unasserted
properties hide.

## Record it

For a single PR, the prediction table goes in the PR body or the session's working notes. For a stack
or anything the Owner will read a coverage number from, keep a ledger — one section per PR — at
`<session_dir>/evidence/<unit>-mutations.md` inside a Robowright Session, else
`<project>/prs/ledgers/<TICKET>-MUTATION-LEDGER.md`. Template and a worked example:
`reference/LEDGER-TEMPLATE.md`. The ledger is what makes a coverage claim believable; the number alone
is not evidence.

## Reporting to the Owner

Report the three interesting things, not the score: **mutations that survived**, **predictions that were
wrong**, and **tests deleted or accepted-untested**. "N mutations, N−3 killed" is the boring half;
the wrong predictions are the half that found real holes.

## Reference

- `reference/mutation-catalog.md` — mutation operators by code shape, and what each one is evidence of.
- `reference/failure-modes.md` — the catalog of tests that pass for the wrong reason: defaulted
  assertions, asserting against the constant under test, environment-zeroed terms, testing the mock,
  shared misunderstanding. Read this while writing tests, not only while mutating.
- `reference/LEDGER-TEMPLATE.md` — ledger format.
