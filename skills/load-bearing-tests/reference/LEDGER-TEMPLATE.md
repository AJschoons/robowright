# `<TICKET>` — mutation ledger

> Predictions written **before** the tests existed; `observed` filled in after running.
> Base: `<commit>` on `<branch>`.

---

## PR<n> — `<branch-slug>`

Suite: `<TestSuiteName>` (new file / existing). **N tests, all green.**
Every mutation applied to `<FileUnderTest>.swift`; suite re-run per batch. Batches chosen so the
mutations touch disjoint statements **and** the predicted kill sets are disjoint.

### Results

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| M1 | Delete the `onSortButtonTap` log | T1, T4 | T1, T4 | ✅ match |
| M2 | `source: .notesList` → `.search` | T1 | T1 | ✅ match |
| M6 | `layout: .list` → `.grid` | T5, T6 | **T5 only** | ⚠️ over-predicted |
| M13 | `size: .card` → `.compact` | T14 | — → T14 | ✅ after adding the assertion (F2) |
| M17 | Folder branch calls `presentFolderPicker` instead of `dismiss` | T7, T10 | T7, T8, T9, T16 | ✅ killed, wider than predicted |

**<N-1> of <N> tests have at least one killer.** Exceptions below.

Verdicts: `KILLED` · `SURVIVED` · `EQUIVALENT` · `OUT-OF-TIER` · `CHANGE-DETECTOR` · `NO-COMPILE` ·
`SUITE-DID-NOT-RUN`. Never fold `OUT-OF-TIER` or `CHANGE-DETECTOR` into `EQUIVALENT` — those two rows
are the ones worth reading. ⚠️ marks a prediction that missed, whichever way it missed.

### Findings

Numbered, one per interesting row. A finding is any over-prediction, any survivor, any non-compiling
seed, and any test deleted or accepted. State *why*, not just *what* — the reason is the reusable part.

**F1 — <over-prediction>.** Why the prediction was wrong, and whether the coverage or the reasoning was
at fault.

**F2 — <survivor that became an added assertion>.** What was unasserted, where the property is readable,
what assertion closed it.

**F3 — <seed mutations that do not compile>.**

| Seed | Why | Substitute used |
|---|---|---|
| … | … | … |

**F4 — <test deleted>.** `test_…` asserted X. No compiling mutation of the current code can make it
fail, because <reason>. Deleted rather than kept green.

**F5 — <accepted untested>.** `<behavior>` has no test seam (<reason>). Recorded here rather than
covered by an assertion that cannot fail.

### Test index

| # | Test |
|---|---|
| T1 | `test_onSortButtonTap__logsSortTappedForNotesList` |
| T2 | *(deleted — F4)* |

### Out of scope, deliberately

Pre-existing logic this change does not touch, and what remains uncovered in it.
