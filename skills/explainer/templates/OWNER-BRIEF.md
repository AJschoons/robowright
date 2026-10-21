# Owner brief — <unit> <title>

Written <date> by `explainer-<slug>` from the Robowright Session record, never the diff. Every
row cites the file it came from. **Cap:** <1,000 | 400> words (<size> in `PROJECT.md` § Task
Breakdown, or "no size found") · **Count:** <n> by `wc -w`.

## Decide now

What only the Owner can answer before accepting this. "Nothing" is a valid answer; say so.

| Ask | Recommendation (Planner / Lead) | Cites |
|---|---|---|
| <the question, one sentence> | <the answer, and why in one clause> | `PLAN-REVIEW.md` § <heading> or § Asks after intake (Lead) / `INTAKE.md` § 8 |

## Key decisions

Made for you, ranked by the decider's confidence, most sure first. Overrule one with a
`review-feedback` brief.

| Decision | By | Alternative passed over, and why | Cites |
|---|---|---|---|
| <the call> | Lead / Planner | <what was not chosen> — <the reason it lost> | `<session_dir>/LEDGER.md` § <heading> |

## What changed

<one paragraph, from BRIEF.md § Goal and INTAKE.md § 3: what the Owner's system does now that it
did not before, and the verdict lines the ledger quotes>

## Spot-check

At most three. Each is a hunk a gate review held, or a hotspot the brief named.

| Where | The question to hold while reading it | Cites |
|---|---|---|
| `<file>:<line>` @ `<sha>` | <from what the Reviewer held and how it resolved, or the hotspot's risk> | `reviews/<unit>-gate.md` § <heading> / `BRIEF.md` § Invariants and hotspots for the adversarial reviewer |

## Where the detail lives

- `INTAKE.md` — <session_dir path>
- `PLAN-REVIEW.md` — <path, and its verdict; or "not run (`plan_review: off`)">
- Gate reviews and end-of-stack review — `<session_dir>/reviews/`
- Evidence — `<session_dir>/evidence/`
- Change description — `<session_dir>/prs/<unit>.md`
