# Scenario smells — how examples and tests go wrong

Each has been documented by the people who built BDD, usually after watching teams do it. Check
the **table** against 1–6 while writing it and the **tests** against 7–12 while reviewing them.
Tests that pass for the wrong reason are a different catalog:
`load-bearing-tests/reference/failure-modes.md`.

## In the table

### 1 · The example written after the code
The row's expected value was read off the implementation. It will pass, and it will keep passing
when the implementation is wrong in exactly the way it was wrong when you read it. *Tell:* the
source column says nothing, or you cannot fill it without opening the file.
**Fix:** delete the row's Then, re-derive it from the requirement. If it cannot be derived, it
is a question.

### 2 · Imperative steps
> Given the user opens Settings, taps Sync, scrolls to Attachments and taps the toggle

versus

> Given attachment sync is enabled

The first describes *how*; it breaks when the screen is redesigned though the behavior did not
change. *Test:* would the wording change if the implementation changed? Then it is describing
the implementation.

### 3 · Incidental detail
A Given listing the user's name, locale, account tier, and device model for a rule about free
space. The reader cannot tell which fact the outcome depends on — and neither can the next
person who edits it. **Fix:** keep what the rule depends on; push the rest into the
`given…()` helper's defaults.

### 4 · No rule behind the example
A row that illustrates nothing in the Rules pile — usually copied from a bug report or an
existing test. Either it reveals a missing rule (write the rule) or it duplicates a row
(delete it).

### 5 · The chain — When… Then… When… Then
One row walking through a whole session. The second When's Given is the first Then, so a
failure in step one reports as a failure of everything. **Fix:** one row per When; the earlier
outcome becomes the later row's Given, set up directly.

### 6 · Missing boundaries, missing collisions
Only the comfortable middle of each rule is listed. The rows that find bugs are the edge of
each rule (at the floor, one below) and the input where two rules both apply and the
requirement has to say which wins. No collision row usually means nobody asked.

## In the tests

### 7 · One test per method
`test_decide`, `test_decide_2`, `test_init`. The unit of testing is a behavior; a method has
many, and some behaviors span several methods. *Tell:* the test name contains a symbol name and
no outcome.

### 8 · The name that restates the assertion
`returnsDeclined`, `setsFlagToTrue`. Says what the code does, not what the user or caller
gets, or under which condition. **Fix:** outcome, then condition — "declines an upload that
would dip below the floor".

### 9 · Asserting how, not what
Verifying that `quota.freeMB` was read once, that `validate()` ran before `save()`, that a
private cache was populated. All of these can change with the behavior intact, and all can
hold with the behavior broken. Assert the returned value or the resulting state; assert an
interaction only when the call is the effect.

### 10 · Mocking what you own and could run
A mock `AttachmentPolicy` inside an `UploadQueue` test, with `stubbedDecision = .allowed`. The
test now proves the queue obeys a stub. Run the real policy with a fake `QuotaProbe`; the
port is the quota, not the policy.

### 11 · Logic in the test
A loop, an `if`, a computed expected value, a helper that re-implements the rule "to avoid
magic numbers". Any of these can carry the same bug as the code. Expected values are literals
with their derivation in the table — `79 − 30 = 49, floor 50 → free 1`.

### 12 · DRY over readable
Setup factored so far that the test body is one line and the reader must open three helpers to
learn what was given. A test is documentation first: repeat the two values that matter in the
test, hide only what is incidental.

## Sources

Hellesøy on scenarios written after the code and imperative style —
https://cucumber.io/blog/collaboration/the-worlds-most-misunderstood-collaboration-tool/ ·
declarative wording test — https://cucumber.io/docs/bdd/better-gherkin/ · BRIEF —
https://cucumber.io/blog/bdd/keep-your-scenarios-brief/ · North on Givens, single event, and
splitting — https://dannorth.net/blog/whats-in-a-story/ · Example Mapping —
https://cucumber.io/blog/bdd/example-mapping-introduction/ · behaviors not methods, DAMP, no
logic in tests — https://abseil.io/resources/swe-book/html/ch12.html · real → fake → mock,
state over interaction — https://abseil.io/resources/swe-book/html/ch13.html ·
structure-insensitive tests — https://testdesiderata.com/
