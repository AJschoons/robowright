# Swift mechanics — Swift Testing and XCTest

Contents: mapping · suite shape · example tables · shared Given · preconditions · async events ·
fakes at ports · XCTest · UI tests · what not to reach for

The Swift Testing snippets were compiled and run (Swift 6.4, 2026-10-20). The XCTest ones were
**not** compiled in that pass — check them against the target before copying.

Use whichever framework the target already uses for the suite you are adding to; default to
Swift Testing for a new suite where the target supports it. A project's own rules on running
tests win over anything here.

## Mapping

| BDD idea | Swift Testing | XCTest |
|---|---|---|
| Capability / feature | Outer `@Suite("Attachment policy") struct` | `final class AttachmentPolicyTests: XCTestCase` |
| Rule or context | Nested `@Suite("R1 · keeps the quota floor free") struct` | `// MARK: - R1 · keeps the quota floor free` |
| Example | `@Test("declines an upload that would dip below the floor")` | `func test_declinesUpload__whenItWouldDipBelowFloor()` |
| Several examples of one rule | `arguments:` — each case reported and re-runnable alone | One test per example, or a table looped through a helper that passes `file:line:` |
| Shared Given | The suite's `init` — a fresh instance per test | `setUp()` |
| Given / When / Then | Blank-line-separated blocks; comments only when a block is long | `// Given` `// When` `// Then`, or `XCTContext.runActivity` in long flows |
| Hard precondition | `try #require(…)` | `try XCTUnwrap(…)` |
| Cross-cutting label | `.tags(.quota)` | — |

## Suite shape

```swift
import Testing

import Attachments

@Suite("Attachment policy")
struct AttachmentPolicyTests {

    static func givenPolicy(freeMB: Int) -> AttachmentPolicy {
        AttachmentPolicy(quota: FakeQuota(freeMB: freeMB), quotaFloorMB: 50, cellularConfirmationThresholdMB: 20)
    }

    @Suite("R1 · keeps the quota floor free")
    struct QuotaFloor {

        /// the decline says how much to free — a decline with no number leaves the user guessing what to delete
        @Test("declines an upload that would dip below the floor, and says how much to free")
        func declinesUploadDippingBelowFloor() {
            let policy = givenPolicy(freeMB: 60)

            let decision = policy.decide(sizeMB: 30, isOnCellular: false)

            #expect(decision == .declined(mustFreeMB: 20))
        }
    }
}
```

- The display string is the sentence; the function name is a plain camelCase echo of it so
  `-only-testing` filters and stack traces stay usable. Raw-identifier names (SE-0451,
  ``func `declines an upload…`()``) work from Swift 6.2 but are awkward in those filters —
  prefer the display string.
- Suite names carry the rule id from the behavior table, so a failure reads back to a row. A
  collision row (`R1×R2`) lives in the suite of the rule that decides the outcome.
- A nested suite reaches the outer suite's `static` helpers unqualified.
- `#expect(a == b)` prints both sides on failure, and the test's `///` line under it — which is
  why the doc comment says what breaks.

## Example tables — `arguments:`

One rule, several rows of the behavior table:

```swift
@Test("declines an upload that would dip below the floor, and says how much to free", arguments: [
    (freeMB: 79, sizeMB: 30, mustFreeMB: 1),
    (freeMB: 60, sizeMB: 30, mustFreeMB: 20),
    (freeMB: 10, sizeMB: 30, mustFreeMB: 70),
])
func declinesUploadDippingBelowFloor(freeMB: Int, sizeMB: Int, mustFreeMB: Int) { … }
```

- Labeled tuples keep each row readable as a table row; the failure names the row
  (`with 3 arguments freeMB → 79, sizeMB → 30, mustFreeMB → 1`).
- **The expected value is a column**, written from the rule. Never compute it in the test body
  with the production formula — that is asserting against the code under test.
- Two argument collections make a Cartesian product. For paired inputs use one collection of
  tuples, or `zip(sizes, expected)`.
- Only parameterize examples of the **same** rule with the **same** Then shape. Different
  outcomes are different tests; a `switch` on the row inside the test body is two tests
  pretending to be one.

## Shared Given — a context suite

When several examples share a starting state, the state is the suite:

```swift
@Suite("when the quota is 10 MB above the floor")
struct NearlyFull {
    let policy: AttachmentPolicy

    init() {
        policy = AttachmentPolicy(quota: FakeQuota(freeMB: 60), quotaFloorMB: 50, cellularConfirmationThresholdMB: 20)
    }

    @Test("declines an upload larger than the headroom")
    func declinesUploadLargerThanHeadroom() {
        #expect(policy.decide(sizeMB: 30, isOnCellular: false) == .declined(mustFreeMB: 20))
    }

    @Test("still allows an upload that fits the headroom")
    func allowsUploadThatFitsHeadroom() {
        #expect(policy.decide(sizeMB: 10, isOnCellular: false) == .allowed)
    }
}
```

Keep in `init` only what the suite's **name** promises. A value a test's Then depends on belongs
in that test, visible — not three screens up in shared setup.

## Preconditions

`try #require(…)` for a Given that must hold before the When means anything — unwrap, non-empty,
correct type. It stops the test with a clear message instead of failing the Then for the wrong
reason.

## Async events

When the behavior is "the caller is told once":

```swift
@Test("tells the caller once when the upload finishes")
func tellsCallerOnceWhenFinished() async {
    await confirmation(expectedCount: 1) { finished in
        let uploader = AttachmentUploader(onFinish: { finished() })

        await uploader.run()
    }
}
```

`expectedCount: 0` is the honest way to say "is never told". Before designing around any
callback seam, prove it fires at all (`load-bearing-tests` → "prove the seam works").

## Fakes at ports

```swift
struct FakeQuota: QuotaProbe {
    let freeMB: Int
}
```

A fake is a small real implementation of the port: it holds state and answers from it. It has
no `callCount`, no `stubbedResult`, and the test asserts the **subject's** resulting state or
return value, not the fake. Reach for a recording double only when the outgoing call is itself
the behavior — an analytics event, a navigation request, a network call — and then assert the
payload, not just that something was called.

## XCTest

```swift
final class AttachmentPolicyTests: XCTestCase {

    // MARK: - R1 · keeps the quota floor free

    /// the decline says how much to free — a decline with no number leaves the user guessing what to delete
    func test_declinesUpload__whenItWouldDipBelowFloor() {
        // Given
        let policy = givenPolicy(freeMB: 60)

        // When
        let decision = policy.decide(sizeMB: 30, isOnCellular: false)

        // Then
        XCTAssertEqual(decision, .declined(mustFreeMB: 20))
    }
}
```

`test_<outcome>__<condition>`. In a suite already using `test_<method>__<scenario>`, keep the
prefix it uses and make the scenario half state outcome and condition.

## UI tests and long flows

`XCTContext.runActivity(named:)` groups steps under a name in Xcode's report, and nests. Use it
where a flow is long enough that a bare failure line does not say which step broke:

```swift
XCTContext.runActivity(named: "Given a quota 10 MB above the floor") { _ in … }
XCTContext.runActivity(named: "When a 30 MB attachment is uploaded") { _ in … }
XCTContext.runActivity(named: "Then the quota warning names 20 MB") { _ in … }
```

Activity names are declarative — what is true, what happens, what results — never the taps.
The taps live inside the block, behind a screen-object method.

## What not to reach for

- **Quick** — maintenance mode, no route to Swift Testing. Nested suites and display names
  cover what `describe`/`context`/`it` gave.
- **Gherkin runners** (XCTest-Gherkin, Cucumberish, CucumberSwift) — a feature file plus step
  definitions is two more artifacts to keep in agreement, for a reader who does not exist here.
- **A `for` loop over examples** — stops at the first failure and reports one test.
  `arguments:` reports each row.
