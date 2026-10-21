# Mutation catalog — what to break, by code shape

Pick mutations that produce a **defect a human could plausibly write**, not arbitrary noise. Every one
must compile; a mutation that does not compile is neither a killer nor a survivor, and needs a
substitute (see "When it won't compile").

Examples are Swift because that is where this practice was built; the shapes are language-agnostic.

## By shape

| Code shape | Mutations that earn their cost | What a kill proves |
|---|---|---|
| `if` / `guard` condition | Invert it; drop one conjunct; replace with `true` / `false` | The branch is reachable **and** distinguishable — nothing more |
| Statement inside a branch | Delete it; reorder it against the statement next to it | The *work* in the branch is pinned, which is the thing you care about |
| Ternary | Force each side unconditional | Predict with inputs from the **other** side |
| Arithmetic | Drop a term; swap `+`/`-`; swap `*`/`/`; drop a divisor | The formula is pinned, not just its endpoints |
| `max` / `min` | Swap them | Which degenerate case the floor protects |
| Clamp or ramp | Delete the clamp; invert `1 - x` → `x`; collapse the range | Needs 3 samples: below, interior, above |
| Constant | Change its value | **Only** if no assertion reads the constant symbolically (see failure-modes §2) |
| Enum case passed to a collaborator | Swap for a sibling case | The specific case is asserted, not just "an event was logged" |
| Payload / struct literal | Drop each field; `nil` one out; swap two same-typed fields | Each field a test claims to pin is actually asserted |
| Optional chain / coalescing | `a ?? b` → `a`, then → `b` | Both halves are covered; fixtures must have *distinct* values |
| Nil / empty guard | `!= nil` → `== nil`; drop an `isEmpty` check | The guard is load-bearing, not decorative |
| Completion / callback | Call it synchronously instead of deferring; replace the closure body with `{}` | Ordering is pinned, not only the final state |
| Deduplication guard (`!=` before a write) | Drop the guard | Count emissions, don't assert the value |
| Call to a collaborator | Delete it; point it at a sibling method | The effect is observed, not merely the call site's existence |
| Analytics / logging | Delete the call; change one metadata field | The payload is asserted field by field |

## Ordering and concurrency

Statement order is load-bearing more often than it looks — a collaborator that re-enters synchronously
means everything after the call observes already-mutated state. Swapping two adjacent statements is a
cheap, always-compiling mutation and one of the highest-yield ones on moved code.

## When it won't compile

Common causes and the substitute that works:

| Cause | Substitute |
|---|---|
| Type mismatch (`Int64` vs `Int`) | Change the *value* instead of the accessor — pass `0` |
| Deleting a statement leaves `[weak self]` captured and unread | Replace the whole closure body with `{}` |
| The fixture type's `init` is `package`/`internal` and unreachable from the test target | Construct the value a different way (a factory, a literal enum case, a settable published property) rather than widening access |

**Verify every "does not compile" verdict.** It is the easiest one to fake: a catalog entry whose
replacement is prose — `(delete line 53)` — pasted into source fails to compile in zero seconds and
journals as evidence, though it was never compiled. Every
mutation is a literal replacement of text that exists.

Two failed constructions is **not** evidence something is hard to arrange. Before recording "needs ~40
lines of fixture machinery", try a different enum case and a different entry point — that has twice
turned a 40-line estimate into 20 lines that closed a real gap.

## Equivalent mutants

A mutation that cannot change observable behavior (`x + 0` → `x - 0`) is not a hole, and a correct test
cannot kill it. Two ways they show up here:

- **Genuinely equivalent** — record and move on, do not write a test for it.
- **Equivalent *in the test environment only*** — a term that evaluates to `0` headless (screen metrics,
  tab-bar heights, device insets) makes the mutation invisible however the assertion is written. This is
  the more dangerous one: say so in the test's own comment rather than letting the test name imply
  coverage that cannot exist, and find a second mutation on a non-zero term.

## Where the seed mutations come from

Write the seed list **while reading the code being tested, before writing tests** — one line per branch
or payload field. Writing it after the tests exist means seeding from what the tests already assert,
which is circular.

Arriving from `bdd`, the tests exist before the code does, so that order is impossible — and the
circularity is avoidable anyway: after green, seed from the **implementation's branches and writes**
with the test file closed, then predict. A branch with no row behind it is the finding.
