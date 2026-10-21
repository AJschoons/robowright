# Fidelity — checking that each row is true of the old code

Contents: why this is the weak link · tier 1 pin · tier 2 observe (the risk call, the run) ·
tier 3 refute (prompt, output) · reconciling

## Why this is the weak link

Step 3's trace proves the table is **complete** against the old code, mechanically. Mutation
proves the new tests are **load-bearing** against the new code, by running. Nothing mechanical
proves a row's Then is what the old code actually does — and a wrong row produces a green,
load-bearing test that pins the wrong behavior, which is the exact failure this skill exists to
prevent. Measured: specifications mined from code that all *verify* drop to 24–47% when scored
for completeness, and reading-only equivalence judgment by the best model tops out at 78% on a
benchmark with a 50% baseline. So: use the strongest tier each row allows, and label what is
left.

## Tier 1 — pin, where the old code has a seam

Feathers' algorithm, unchanged:

1. Get the code into a harness.
2. Assert something you know is wrong.
3. Run; read the actual value out of the failure.
4. Paste it in; name the test for the behavior.

Compare the actual with the row. They agree → the row is tier 1. They differ → the row was
wrong; correct the table.

- **Do not dig a seam to get here.** Introducing one in untested code is itself an unguarded
  change. Use a seam that already exists, or one reachable by a refactoring that is mechanical
  and reviewable at a glance — extract a pure function, inject through an existing initializer,
  a closure property with the old call as its default. Anything more, and the row stays at
  tier 2 or 3.
- Pin tests are scaffolding too. They are shaped like the old code; once the view-model tests
  are green and proven, the pins are deleted with the code they pinned, in the same change.
- Async work that finishes after teardown, statics that cannot be replaced, and defensive code
  that cannot be reached are the usual reasons a pin cannot be written. Say which, and move on.

## Tier 2 — observe the running base build

The old logic may be untestable, but the old **app** runs. For a row whose Given can be reached
and whose Then is on screen (or in a log the project hook names), run the build from *before*
the migration and watch the row happen.

### The risk call — the Owner's, every time

Observation costs a base build, a simulator, and a minute or two a row, so it is a judgment
about risk, and the judgment is the Owner's. After tier 3 has run, put this in front of them:

```
**Tier-2 candidates** — <n> of <total> rows are observable on the base build.

| # | Row (short) | Why it is risky | Cost |
|---|---|---|---|
| B9 | later failures silent after a dismissal | suspect · state accumulates across 4 events · refuter: cannot-determine | ~2 min |
| B13 | double tap starts two syncs | suspect · depends on a callback arriving late | ~3 min, needs a slow network |

Not candidates: <n> rows with no on-screen or logged outcome (analytics payloads: B5–B7) — they
stay tier 3.

**Recommend:** observe B9 and B13 (the two the refuter could not settle); skip the other <n>
single-branch rows, each traced in under ten lines. Base build: ~<m> min.

Observe: none / these / all?
```

What makes a row risky enough to recommend: it is `suspect`; the refuter returned `refuted` or
`cannot-determine`; the outcome depends on ordering, timing, or a late callback; the Given takes
several events to reach; a wrong row would cost data, money, or something irreversible; a name
on the path turned out to lie. What does not: a single-branch row with a short trace, pure
formatting already pinned at tier 1.

Unattended, the brief carries the answer. No answer → observe nothing, and the report says the
tier-2 call was never made.

### The run

`smoke-test`'s agent lane, pointed at the base build instead of a diff — its rules hold here
unchanged:

- **Observability pre-flight first**: the element has an accessibility node, the screen is
  reachable by deep link or a few taps, the Given's state can be seeded. A row that fails
  pre-flight is `blocked` before any build is spent, and stays tier 3.
- **The oracle is the row's Then, written down before the run.** That is the whole point: the
  table predicts, the app answers.
- The leased simulator only, by UDID; one simulator command per call.
- Evidence by path — the predicate's output and a screenshot that has been looked at.
- Per row: `matches` · `differs — actual: <what happened>` · `blocked — <why>` ·
  `unverified — ran, nothing settles it`. Only `matches` and `differs` change the table;
  `blocked` and `unverified` are not confirmations.

A `differs` corrects the table. A `suspect` row that `matches` is now a confirmed oddity, which
is a stronger thing to bring to the Owner than a suspicion.

## Tier 3 — refute, by a fresh reader

For every row not pinned. The reader must be a **fresh context** — a subagent that has not seen
your extraction — because a second look from the context that made the misreading does not find
it. Give it the table, the vocabulary, the code at the pinned SHA, and nothing else: not your
notes, not your grids, not your reasoning. In Robowright this is a Reviewer; anywhere else, a
general-purpose subagent.

### Prompt

```
You are checking a behavior table that someone else extracted from existing code. You have not
seen how they did it. The table will be used as the only oracle for a migration of this code, so
a row that is wrong becomes a passing test that defends the wrong behavior. Your job is to break
it.

Code: <repo> at <sha>, files <paths and line ranges>.
Vocabulary and table: <path>.

For every row:
1. Take the row's Given and When as concrete values. Trace them through the code line by line,
   writing down each intermediate value. Read the body of every helper on the path.
2. Ignore what names and comments suggest; report what the statements do.
3. Compare where your trace ends with the row's Then — exact strings, constants, payloads,
   and the order of effects.
4. Verdict: `holds` · `refuted — actual: <what the code does, file:line>` ·
   `cannot-determine — <what you would need>`. When unsure, it is not `holds`.

Then, separately:
- Check each product state's flag mapping in the vocabulary against the code's writes.
- List any behavior you found on these paths that **no row covers**, with file:line.
- List any row that describes how the code works rather than what a user or collaborator
  would observe.

Read by line range, never whole files. Change nothing. Do not suggest fixes to the code; a bug
is reported as what the code does.
```

### Output

One line per row, then the three lists. `holds` rows stay tier 3 — a reader agreeing is
evidence, not proof. Everything else is work:

- `refuted` → re-trace it yourself with the refuter's line citations; the table takes whichever
  the code supports. If you still disagree after that, neither of you settles it by reading —
  it is a tier-2 candidate, flagged as `refuter disagreed`. Then grep the table for the
  corrected row's id: a row that says "as B16" was wrong wherever B16 was.
- `cannot-determine` → usually a missing piece of context (a caller, a configuration value).
  Supply it and ask again once; then tier-2 candidate.
- **uncovered behavior** → a new row, and step 3's trace was not at zero after all. Find out
  why the trace missed it before adding the row.
- **source-language rows** → rewrite at the right altitude (`extraction.md`).

## Reconciling

Every change to the table after extraction is kept as a line beneath it — row, what it said,
what it says now, which tier found it. Those lines are the most useful thing in the final
report: they are the misreadings that would otherwise have shipped as tests.

The tally in the table's header (format in `SKILL.md`, step 3) is updated as each tier
reports, so nobody mistakes a tier-3 table for a verified one:

```
Rows: 13 · tier 1: 0 · tier 2: 2 (matches 2) · tier 3: 11 (holds 10, corrected 1) · unchecked: 0
Trace: 8 decision points + 13 outcome statements → 17 mapped, 3 dead, 1 unobservable, 0 undetermined, 0 unaccounted
Suspects: 4 rows, 3 causes — B4 · B9, B10 · B13 (all preserved; the Owner 2026-09-20)
```
