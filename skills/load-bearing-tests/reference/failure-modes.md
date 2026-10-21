# Tests that pass for the wrong reason

Each of these has been found in real suites, usually in tests that read as thorough. Check for them
**while writing**, not only while mutating — every one is cheaper to avoid than to discover.

## 1 · The defaulted assertion

`XCTAssertNil(sut.pendingDeletionNoteID)` where `nil` is the property's initial value. The test passes
without the code under test running at all.

**Check, on every assertion:** the expected value must differ from the property's initial value *and*
from every fixture default — `nil`, `false`, `0`, `.zero`, `""`, empty collection. Arrange a pre-state
that differs from the expected post-state, then act, then assert.

**When "unchanged" genuinely is the expectation, also assert that the act ran.** A test asserting a
value is carried over passes on a total no-op, because the pre- and post-states are deliberately equal.

## 2 · Asserting against the constant under test

```swift
XCTAssertEqual(preview.height, NotesListViewModel.previewFallbackHeight)   // tautology
```

Changing the constant from `14` to `0` moves both sides of the comparison and leaves the test green.
Writing the symbol *feels* like documenting the relationship; it documents nothing a test can check,
because the constant's value **is** the behavior.

- **Assert the literal.** If the literal is genuinely unstable, that argues for a named constant in the
  *test*, not for reading the production one.
- Constants owned by a **collaborator** are fine (`NoteCardLayout.compactHeight`,
  `AppSpacing.medium`) — no mutation of the code under test moves them. The rule is about the
  type being tested.

## 3 · The vacuous comparison

`XCTAssertEqual(list.scrollOffset, 0)` where the fixture list was built with fewer notes than fit on screen — a
list that cannot scroll has offset `0`, so the test asserts `0 == 0` and survives a mutation that zeroes the
offset on purpose. Same shape: `padding` where the padding is `.zero`, `count` where the array is empty.

**Fixture rule:** distinct, non-default values per axis, so a crossover between two fields is visible.

## 4 · The environment-zeroed term

A term that evaluates to `0` in the test environment — `AppSpacing.tabBarHeight(in: window)` headless,
screen bounds, safe-area insets — makes any mutation of it invisible, even when the assertion follows
every other rule here. Evaluate **every term at test time**, not on paper, before claiming a test pins a
formula. If a term is zeroed, say so in the test's comment and find a second mutation on a live term.

## 5 · Asserting the collaborator instead of the state

Tests named `…completesWithoutScrollingTheList` asserted `animatedScrollCallCount == 0`. That is a claim
about the *scroller*. The suite's own softened path writes `scrollPosition` directly and never touches
the scroller — so the list can move with the assertion still green.

**Seed a sentinel and assert the state.** Assert the collaborator only when the call *is* the effect
(analytics, navigation, a network request).

## 6 · Testing the mock

A test whose assertions only read back values the test itself stubbed is testing the mocking framework.
The tell: no production code path is required for the assertion to hold. Mutation kills these
immediately — every mutation survives.

## 7 · Shared misunderstanding

The same agent writes the code and the test, misreads the requirement once, and encodes it twice: a
boundary silently moved from `>= 2` to `> 2`, confirmed by a test asserting the wrong threshold. Mutation
does **not** catch this — the test is load-bearing, it is just pinning the wrong behavior.

The defenses are different in kind, and the first is a whole skill — `bdd`, which runs before this one:
- Derive expected values from the **requirement or the pre-change behavior**, not from reading the
  implementation you just wrote. Written down per example, with its source, before the code exists.
- A **fresh-context adversarial review** of the diff, given the contract rather than your reasoning.
- For a moved behavior, characterize the **original** first and assert against that table.

## 8 · A test built on a false premise about lifetimes or ownership

A fix justified by a claim about object lifetime, tested by a suite containing no object whose lifetime
varies, proves the model rather than the code. The tell is the mismatch itself: when a fix's rationale
is about *when something is rebuilt*, the test must involve something being rebuilt. Read the ownership
chain — every stored reference from the screen's root down — before writing the test.

## 9 · Assertion roulette and magic numbers

Several unlabeled assertions in one test, so a failure does not say which claim broke; and unexplained
numeric literals whose provenance is lost. Both are the dominant measured smells in LLM-generated test
suites across models. One behavior per test, and derive literals in a comment or a named test-local
constant.

## 10 · The flaky test, inside a mutation run

A test whose assertion reads machine speed rather than a real bound — a poll ceiling set at 6× the
paced loop's limit, a one-second wait on a busy main actor — is a loud, obvious failure in a normal
gate. Inside a mutation run it reports `KILLED`, which is **silently wrong**, and the mutant it
"killed" goes in the ledger as covered.

That asymmetry is the argument for hardening a test that is currently green. Two causes in
practice: a ceiling that does not sit *at* the loop's bound, and de-serializing a large
`@MainActor` suite so every test starts at once and queues on the main actor, timing out a
*different* suite's wait.

## 11 · A green run on a tree that moved

In a shared clone, a concurrent session's commit can land between `build-for-testing` and
`test-without-building`; both commands succeed and the result is meaningless.

- Compare the executed test count against the previous run; treat any unexplained delta as contamination.
- `diff` executed test names against `grep -oE 'func test_[A-Za-z0-9_]+'` on the source.
- Put long verification runs in a throwaway worktree, not the shared clone.
