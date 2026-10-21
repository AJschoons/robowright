# Worked example — one requirement through the loop

Every code block here was compiled and run (Swift 6.4, Swift Testing, 2026-10-20). The output
lines are quoted from those runs, trimmed.

## The requirement

> An attachment upload should leave at least 50 MB of the user's quota free. If an upload would
> not fit, tell the user how much space to free. On cellular, ask before uploading anything over
> 20 MB.

## 1 · Discover

**Rules**
- R1 — an upload never leaves less than the quota floor (50 MB) free.
- R2 — on cellular, an upload over 20 MB needs the user's yes first.

**Questions**
- Q1 — an upload that lands *exactly* on the floor: allowed? → "leave **at least** 50 MB free":
  50 remaining satisfies it. Settled by the ticket's wording.
- Q2 — exactly 20 MB on cellular: ask? → "anything **over** 20 MB": no. Settled by the ticket.
- Q3 — both rules trip at once: which answer does the user get? → **the ticket does not say.**
  Asked the Owner with a proposed default (quota first — confirming an upload that then fails for
  space is the worse experience). The Owner agreed; the row's source is `the Owner, 2026-09-20`.

Q3 is the row a code-first pass never writes. The implementation would have picked an order by
accident, and the test written afterwards would have pinned whichever one it was.

## 2 · Formulate

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R1.1 | Floor | 1 000 MB free | 30 MB upload, Wi-Fi | Allowed | Ticket |
| R1.2 | Floor | 80 MB free | 30 MB upload, Wi-Fi | Allowed | Ticket, "at least" (Q1) |
| R1.3 | Floor | 79 MB free | 30 MB upload, Wi-Fi | Declined, free 1 MB | Ticket; 50 − (79 − 30) |
| R1.4 | Floor | 60 MB free | 30 MB upload, Wi-Fi | Declined, free 20 MB | Ticket |
| R1.5 | Floor | 10 MB free | 30 MB upload, Wi-Fi | Declined, free 70 MB | Ticket — free quota below the upload size itself |
| R2.1 | Cellular | Ample quota | 21 MB on cellular | Needs confirmation | Ticket, "over" |
| R2.2 | Cellular | Ample quota | 100 MB on cellular | Needs confirmation | Ticket |
| R2.3 | Cellular | Ample quota | 20 MB on cellular | Allowed | Ticket, "over" (Q2) |
| R2.4 | Cellular | Ample quota | 100 MB on Wi-Fi | Allowed | Ticket |
| R1×R2 | Precedence | 60 MB free | 30 MB on cellular | Declined, free 20 MB | The Owner, 2026-09-20 (Q3) |

The arithmetic in R1.3 is written from the **rule**, in the table, before any code exists to
compute it.

## 3 · Red

The skeleton — compiles, decides nothing:

```swift
public func decide(sizeMB: Int, isOnCellular: Bool) -> UploadDecision {
    .allowed
}
```

The tests, straight from the table (full file shape in `swift.md`):

```swift
@Suite("Attachment policy")
struct AttachmentPolicyTests {

    static func givenPolicy(freeMB: Int) -> AttachmentPolicy {
        AttachmentPolicy(quota: FakeQuota(freeMB: freeMB), quotaFloorMB: 50, cellularConfirmationThresholdMB: 20)
    }

    @Suite("R1 · keeps the quota floor free")
    struct QuotaFloor {

        /// an upload may use quota down to the floor — users blocked from uploads they have room for
        @Test("allows an upload that leaves free quota at or above the floor", arguments: [
            (freeMB: 1_000, sizeMB: 30),
            (freeMB: 80, sizeMB: 30),
        ])
        func allowsUploadLeavingFloorIntact(freeMB: Int, sizeMB: Int) {
            let policy = givenPolicy(freeMB: freeMB)

            let decision = policy.decide(sizeMB: sizeMB, isOnCellular: false)

            #expect(decision == .allowed)
        }

        /// the decline says how much to free — a decline with no number leaves the user guessing what to delete
        @Test("declines an upload that would dip below the floor, and says how much to free", arguments: [
            (freeMB: 79, sizeMB: 30, mustFreeMB: 1),
            (freeMB: 60, sizeMB: 30, mustFreeMB: 20),
            (freeMB: 10, sizeMB: 30, mustFreeMB: 70),
        ])
        func declinesUploadDippingBelowFloor(freeMB: Int, sizeMB: Int, mustFreeMB: Int) {
            let policy = givenPolicy(freeMB: freeMB)

            let decision = policy.decide(sizeMB: sizeMB, isOnCellular: false)

            #expect(decision == .declined(mustFreeMB: mustFreeMB))
        }
    }
    // R2 and the precedence row follow the same shape.
}
```

One run. Read every result:

```
✘ Test "declines an upload that would dip below the floor, and says how much to free" recorded an issue
  with 3 arguments freeMB → 79, sizeMB → 30, mustFreeMB → 1 at AttachmentPolicyTests.swift:43:13:
  Expectation failed: decision == .declined(mustFreeMB: mustFreeMB)
✘ Test "asks for confirmation above the cellular threshold" recorded an issue with 1 argument sizeMB → 21 …
  Expectation failed: decision == .needsConfirmation
✘ Test "declines for quota before asking about cellular" recorded an issue …
  Expectation failed: decision == .declined(mustFreeMB: 20)
✔ Test "allows an upload that leaves free quota at or above the floor" with 2 test cases passed
✔ Test "does not ask at or below the threshold, or on Wi-Fi" with 2 test cases passed
✘ Test run with 5 tests in 3 suites failed after 0.001 seconds with 6 issues.
```

Three tests red, each on its Then. **Two green at red** — they expect `.allowed`, which is what
the skeleton returns. No constant could have failed all five: the three cases partition the
outcomes, so some example always expects whichever one the skeleton picks. (A function
returning a count would not have this problem — return `-1`, which no row expects.) They are
marked unproven and owe their kill first.

## 4 · Green

```swift
public func decide(sizeMB: Int, isOnCellular: Bool) -> UploadDecision {
    let shortfallMB = quotaFloorMB - (quota.freeMB - sizeMB)
    guard shortfallMB <= 0 else { return .declined(mustFreeMB: shortfallMB) }
    guard isOnCellular, sizeMB > cellularConfirmationThresholdMB else { return .allowed }
    return .needsConfirmation
}
```

```
✔ Test run with 5 tests in 3 suites passed after 0.001 seconds.
```

No Given, When, or Then was touched.

## 5 · Prove

The two unproven tests first. Their rows are the boundary rows (R1.2, R2.3), so their mutations
are the boundary operators. Disjoint statements, disjoint predicted kill sets — one batch:

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | `shortfallMB <= 0` → `< 0` | "allows … at or above the floor", case 80/30 only | That case only: `decision == .allowed` failed | KILLED — match |
| M2 | `sizeMB > threshold` → `>=` | "does not ask at or below the threshold", case 20/cellular only | That case only: `decision == .allowed` failed | KILLED — match |

Reverted, `git status` clean. Without rows R1.2 and R2.3 both mutants survive — the boundary
examples found at step 1 are what make the tests load-bearing at step 5. The remaining
mutations (guard order for R1×R2, the `mustFreeMB` arithmetic) continue in
`load-bearing-tests`' loop.

Held-out example, from the rule after green: 50 MB free, 1 MB upload → declined, free 1 MB.
Predicted pass; passed.

## 6 · Report

> **Assumed / asked:** Q3 (both rules trip) — quota first, confirmed by the Owner.
> **Green at red:** the two `.allowed` tests; killed by M1 and M2 on their boundary cases.
> **Table changes after red:** none. **Disputes:** none.
