# Worked example — a sync banner, from view controller to view model

Steps 1–5 are illustrative: the legacy view controller was not compiled, and the refuter's
answers, the observation, and the Owner's replies are written as they would go. Step 6 is real — the
view model, its tests, and every quoted test line were compiled and run (Swift 6.3, Swift
Testing, 2026-09-20).

## The code being migrated

```swift
final class SyncStatusViewController: UIViewController {        //  1
    @IBOutlet private var bannerLabel: UILabel!
    @IBOutlet private var retryButton: UIButton!
    private var isSyncing = false
    private var lastError: SyncError?
    private var pendingCount = 0
    private var didDismissError = false

    override func viewWillAppear(_ animated: Bool) {            //  9
        super.viewWillAppear(animated)
        refreshBanner()
    }

    func syncDidStart(pending: Int) {                           // 14
        isSyncing = true
        pendingCount = pending
        refreshBanner()
    }

    func syncDidFinish(error: SyncError?) {                     // 20
        isSyncing = false
        lastError = error
        if error == nil { pendingCount = 0 }                    // 23
        analytics.track("sync_finished", ["ok": error == nil])  // 24
        refreshBanner()
    }

    @IBAction private func dismissTapped() {                    // 28
        didDismissError = true
        refreshBanner()
    }

    @IBAction private func retryTapped() {                      // 33
        guard !isSyncing else { return }                        // 34
        analytics.track("sync_retry_tapped", [:])               // 35
        syncService.start()                                     // 36
    }

    private func refreshBanner() {                              // 39
        if isSyncing {                                          // 40
            bannerLabel.text = pendingCount == 1 ? "Syncing 1 item…" : "Syncing \(pendingCount) items…"
            bannerLabel.isHidden = false
            retryButton.isHidden = true
        } else if let error = lastError, !didDismissError {     // 44
            bannerLabel.text = error == .offline ? "You're offline" : "Sync failed"
            bannerLabel.isHidden = false
            retryButton.isHidden = error == .offline            // 47
        } else if pendingCount < 0 {                            // 48
            bannerLabel.text = "Sync failed"
            bannerLabel.isHidden = false
        } else {                                                // 51
            bannerLabel.isHidden = true
            retryButton.isHidden = true
        }
    }
}
```

No tests, no view model, outlets everywhere — no seam, so no tier 1.

## 1 · Vocabulary

**Events in** — the screen appears (9) · a sync starts with *n* pending (14, called by
`SyncCoordinator`) · a sync finishes cleanly / offline / with a server error (20) · the user
dismisses the banner (28) · the user taps retry (33).

**Product states**

| State | Flags |
|---|---|
| Idle | `isSyncing == false`, `lastError == nil` |
| A sync is in flight | `isSyncing == true` |
| A failure is showing | `isSyncing == false`, `lastError != nil`, `didDismissError == false` |
| A failure was dismissed | `isSyncing == false`, `lastError != nil`, `didDismissError == true` |
| A sync is in flight, after a dismissal | `isSyncing == true`, `didDismissError == true` |

`grep -n didDismissError` finds one write, to `true`. **Nothing ever clears it** — which is
where the fifth state comes from; the code has it, and no one had named it.

**Observable outcomes** — banner text and visibility · retry visibility · `sync_finished`
tracked with `ok` · `sync_retry_tapped` tracked · a sync requested from `syncService`.

## 2 · Extract

The state grid (in `extraction.md`) produced two cells nobody would have written from a
top-to-bottom read — dismiss *during* a sync, and a failure *after* an earlier dismissal — and
the second-call question under "beyond the branch" produced a third: `retryTapped`'s guard reads
`isSyncing`, which only becomes true when `SyncCoordinator` calls back, so a second tap before
that callback passes the guard.

One file and one SHA, so both are hoisted: every citation is `SyncStatusViewController.swift` at
`a1b2c3d`. `Tier` and `Test` are filled in at steps 4 and 6 and left out of this listing.

| # | Given | When | Then | Observed at | Status |
|---|---|---|---|---|---|
| B1 | No sync has happened | The screen appears | No banner, no retry | 9-11, 51-53 | Preserve |
| B2 | — | A sync starts with 3 pending | "Syncing 3 items…", no retry | 14-17, 40-43 | Preserve |
| B3 | — | A sync starts with 1 pending | "Syncing 1 item…" | 41 | Preserve |
| B4 | — | A sync starts with 0 pending | "Syncing 0 items…" | 41 | **Suspect** — reads as a glitch; coordinator can call with an empty queue |
| B5 | A sync is in flight | It finishes cleanly | Banner and retry hidden; `sync_finished ok=true` | 20-25, 51-53 | Preserve |
| B6 | A sync is in flight | It finishes offline | "You're offline", **no** retry; `sync_finished ok=false` | 44-47 | Preserve |
| B7 | A sync is in flight | It finishes with a server error | "Sync failed", retry shown; `sync_finished ok=false` | 44-47 | Preserve |
| B8 | A failure is showing | The user dismisses it | Banner and retry hidden | 28-30, 51-53 | Preserve |
| B9 | A failure was dismissed earlier | A later sync fails | **No banner, no retry** | 29, 44 | **Suspect** — flag never clears; every later failure is silent |
| B10 | A sync is in flight | The user dismisses, then the sync fails | Progress stays up; then nothing shows | 29, 40, 44 | **Suspect** — same flag |
| B11 | A failure is showing | The user taps retry | A sync is requested; `sync_retry_tapped` | 33-36 | Preserve |
| B12 | A sync is in flight | Retry is invoked | Nothing requested, nothing tracked | 34 | Preserve |
| B13 | A failure is showing | Retry is tapped twice before the start is reported | Two syncs requested, two events tracked | 34, 14 | **Suspect** — guard is set by a later callback |

## 3 · Trace

**Decision points** — each counted once, every arm mapped:

| # | Decision point | Line | Arms → rows |
|---|---|---|---|
| D1 | `if error == nil { pendingCount = 0 }` | 23 | **Unobservable** — `pendingCount` is only read while syncing, and every sync start overwrites it first |
| D2 | `guard !isSyncing` | 34 | Returns → B12 · continues → B11, B13 |
| D3 | `if isSyncing` | 40 | true → B2–B4, B10 · false → D5 |
| D4 | `pendingCount == 1 ? :` | 41 | One → B3 · otherwise → B2, B4 |
| D5 | `else if let error = lastError, !didDismissError` | 44 | true → B6, B7 · false → D8 |
| D6 | `error == .offline ? :` (text) | 45 | Offline → B6 · otherwise → B7 |
| D7 | `retryButton.isHidden = error == .offline` | 47 | Hidden → B6 · shown → B7 |
| D8 | `else if pendingCount < 0` | 48 | **Dead** — `grep -n "pendingCount ="` finds two writes: `pending` from `queue.count`, and the literal `0`. The final `else` (51) → B1, B5, B8, B9 |

**Outcome statements** — each counted once, inside a branch or not:

| # | Statement | Line | Rows |
|---|---|---|---|
| O1 | `analytics.track("sync_finished", …)` | 24 | B5, B6, B7 |
| O2–O3 | `analytics.track("sync_retry_tapped")`, `syncService.start()` | 35, 36 | B11, B13 |
| O4–O6 | Progress text, banner shown, retry hidden | 41, 42, 43 | B2, B3, B4 |
| O7–O9 | Failure text, banner shown, retry visibility | 45, 46, 47 | B6, B7 |
| O10–O11 | "Sync failed", banner shown | 49, 50 | **Dead** — inside D8's arm |
| O12–O13 | Banner hidden, retry hidden | 52, 53 | B1, B5, B8, B9 |

```
Trace: 8 decision points + 13 outcome statements → 17 mapped, 3 dead, 1 unobservable, 0 undetermined, 0 unaccounted
```

Two findings for the Owner before a line has moved: a branch to delete rather than migrate, and a
write that does nothing. The field sweep adds nothing here — four fields, and the one event
that ought to touch `didDismissError` and does not (a sync starting) is already B9.

## 4 · Fidelity

Tier 3: the refuter returned `holds` on eleven rows, `cannot-determine` on B13 ("need
`SyncCoordinator` to know whether `syncDidStart` is called synchronously from `start()`"), and
flagged nothing uncovered. Supplied the coordinator; second answer: `holds` — the callback is
dispatched async.

The risk call put to the Owner: B9, B10, B13 are observable, all three `suspect`, two depend on
accumulated state and one on timing; the other rows are single-branch with traces under ten
lines; B5–B7's analytics payloads have no on-screen outcome and stay tier 3. Recommended B9 and
B13. The Owner chose B9 only — B13 needs a throttled network to reproduce and is cheap to reason
about. Observed on the base build: fail a sync, dismiss, fail again → no banner. `matches`.

```
Rows: 13 · tier 1: 0 · tier 2: 1 (matches 1) · tier 3: 12 (holds 12, one after added context) · unchecked: 0
Trace: 8 decision points + 13 outcome statements → 17 mapped, 3 dead, 1 unobservable, 0 undetermined, 0 unaccounted
Suspects: 4 rows, 3 causes — B4 · B9, B10 · B13
```

## 5 · Suspects

Three questions, not four — B9 and B10 are one never-cleared flag. One fact needed: can
`SyncCoordinator` call `syncDidStart` with an empty queue (B4)? The Owner: yes, on a manual refresh
with nothing pending. The Owner's answers: preserve all in the migration; the flag gets a ticket — a fix
is "clear the dismissal when a new sync starts", a behavior change with its own row and its own
PR.

## 6 · Hand off

Tests written from the table against a skeleton view model (`banner` returns
`.syncing(itemCount: -1)`, every method empty). The view model returns semantic state; the
copy rows (B2–B4) are pinned where the string is built.

```swift
/// preserved as observed: a dismissal is never forgotten — (suspect B9) later failures are silent
@Test("shows no banner for a later failure once any failure has been dismissed")
func staysSilentAfterAnEarlierDismissal() {
    givenFailedSync(.server)
    viewModel.dismissTapped()

    givenFailedSync(.offline)

    #expect(viewModel.banner == nil)
    #expect(viewModel.showsRetry == false)
}
```

Red — eleven of twelve fail on their Then; one is green against the empty skeleton and is
marked unproven:

```
✘ Test "says the sync failed, with retry, and reports the failure" … (viewModel.banner → .syncing(itemCount: -1)) == .failed
✘ Test "starts a sync and reports the tap when the user retries a failure" … (syncService.startCount → 0) == 1
✔ Test "ignores retry while a sync is in flight" passed
✘ Test run with 12 tests in 1 suite failed after 0.001 seconds with 22 issues.
```

Migrated; green with no Given, When, or Then touched. The dead branch was not carried over and
the unobservable write was dropped — both declared in the PR description.

Then the two mutations that matter most here, predicted before running:

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | Drop the `isSyncing` guard in `retryTapped` | "ignores retry while a sync is in flight" (the unproven one) | That test: `startCount → 1`, `events` not empty | KILLED — match |
| M2 | **Quietly fix the suspect**: clear the dismissal when a sync fails | The B9 and B10 tests, nothing else | Exactly those two: `banner → .offline` and `→ .failed`, expected `nil` | KILLED — match |

M2 is the guardrail working: the most natural "improvement" an agent would make while moving
this code turns two tests red, by name, with the word *suspect* in the failure output.

## 7 · Delete

Tests green and proven; the table is removed with the project's scratch documents. What stays is
twelve test names that read as the behavior list, four of which say "preserved as observed".
