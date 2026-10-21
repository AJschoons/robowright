
# Sizing the move

Two standing rules pull against each other — "don't over-engineer, don't creep scope" and
"don't leave the job half done" — and an agent with no tie-breaker oscillates between them:
it adds a protocol nobody needs in one turn and defers a redesign the ticket needs in the
next. This is the tie-breaker. Apply it before proposing, building, deferring, or trimming
anything. The question is always *what kind of thing is this* — not *how big is it*.

1. **Structural, and the end state needs it → do it now, fully.** A seam the tests need, a
   member that reads like state, a protocol the design has been avoiding, a redesign after a
   patch has failed twice. Never a half-measure, a `known gap` note, a "defer to stretch", or
   a fourth placement of the same fix. A true one-way door stops and asks — but *smaller* is
   not the safe default here.
2. **Unrelated to the ticket → out of scope. Record it; don't do it.** Adjacent cleanup, a
   drive-by bug, modernising the logging API of lines a move touched. A pure-move PR that
   also rewrites what it moved stops being reviewable as a move. Park it — ledger,
   exploration doc §9, follow-up ticket — and move on.
3. **Verification → never economize, up to the written ceiling.** Full mutation batches, not
   the headline ones; every unproven test gets fixed, not just the visible ones; the effort tier
   the reasoning needs. Tests are cheap; a lost finding is not. **A fix that failed
   review once is re-verified by running** — build, test, or simulator — never by reasoning
   alone; a third failure on the same finding means redesign, not another placement. Where a
   brief names a ceiling, it is a bound, not a target: stop when every test is killed or
   declared, never past the ceiling; reaching it with work still unproven, write down what you
   would run with more and stop. A run after a commit that changed no code is the rule read
   as absolute — cite the last run instead.
4. **Abstraction for testability alone → don't.** No protocol, generic, coordinator method,
   or view-model pass-through whose only justification is a test that doesn't exist yet. A
   forwarder whose body is one call is deleted, not kept for its tests — callers read the
   source directly. Add the seam in the PR whose test needs it.
5. **PR and ticket granularity → optimize for reviewer load, not LOC.** `<300 logic LOC` is a
   ceiling, not a target; a stack of many one-move PRs is the failure mode. Review fixes and doc
   corrections land as **one commit on top of the PR they belong to** — never a new PR for a
   four-line fix, never a follow-up branch while the owning branch is open. Fold into an
   origin commit only when nothing is stacked above it.
6. **Human checkpoints → only where the brief puts one.** A stop for a one-way door, and
   nothing else.

When a call is genuinely open between rules 1 and 2 — is this structural or unrelated? —
ask. That is the one place a question beats a default.
