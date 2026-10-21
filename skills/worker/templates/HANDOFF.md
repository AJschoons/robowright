# HANDOFF — <slug>

Rewritten at every unit boundary. Written for a reader with no context and no transcript.
Treat every claim you can cheaply re-check as a claim.

## Where things stand

| | |
|---|---|
| Phase | `implement` · U3 of U6 in progress |
| Worktree | `<worktree path>` on `<branch>` |
| Base | `<sha>` — confirm with `git merge-base --is-ancestor` |
| HEAD | `<sha>` |
| Device | `<device id>` — **this lease belongs to the session that wrote this; a new session gets its own.** Locks, one per name in `run.json.locks` (none when it is empty): `<name>` · held / released |
| Last gate | U2 · the counts, verdict, and exit lines, quoted from the project hook's reader |
| Published | Nothing published · or the strategy that ran and what the project hook → Publishing produced, with paths or links |
| Stop reason | None · or `one-way-door: <detail>` |

## FIRST ACTION

The one thing to do before anything else, with the exact command and the expected result.
Usually: the state of the working tree (dirty? never compiled?) and how to get to green.

## Read these first

1. `run.json` — machine state
2. `LEDGER.md` — the last three entries
3. `BRIEF.md` §Units — the rows not yet done

## Remaining units

| Id | Title | Status | Notes |
|---|---|---|---|

## Things that will bite you

Traps hit here, one line each, with the fix.

## Open items

Assumptions the next reader might reverse; parked findings; brief corrections not yet
reflected in the brief.

## Verified vs not verified

- Verified: …, with `evidence/` paths
- Not verified: …, and why (never estimated)
- Comment pass: `reviews/comment-pass.md` · <n> lines classified, <d> deleted, <r> rewritten,
  folded at `<sha>` · or **not run**, and why
- Ceilings: mutation rounds <n>/<max> per unit · whole-suite runs <n> (<which points>) ·
  extra reviewers <n>/<max> · what more would have been run, if anything

## Cost

From `scripts/run-cost.py`, in whatever the profile → Budget is measured in. Reading at
`<HH:MM>`, before the final entry; `run.json.cost` is the authority:

| | This Robowright Session | Previous, if there is one |
|---|---|---|
| Requests | | |
| Output tokens | | |
| Avg context / request | | |
| Lines written : shipped | | |
| Estimated USD | *Only meaningful under a dollar budget; `actual_usd` is the Owner's to fill* | |

## Smoke pass for the Owner

The authority is `<session_dir>/smoke/MANUAL-PASS.md`, written by the `smoke-test` skill, with
the inventory and the agent lane's evidence beside it. Reproduced here so a reader with no
context is not sent to another file first — if the two ever disagree, `MANUAL-PASS.md` wins.

**Agent pass:** <n> of <N> not `pass` — <name them, or "none">. See `smoke/AGENT-PASS.md`.
**Tier:** <Quick / Standard / Deep>, <budget> min. Ordered so stopping anywhere leaves the
least important rows behind.
**If you do one thing:** <the single highest-value check>.

| # | Area | ~min | Agent |
|---|---|---|---|
| 1 | | | |

`agent` is the Robowright Session's own verdict (`pass` · `fail` · `pre-existing` · `blocked` ·
`infra` · `unverified` — the last three are **not** passes). The index above is read-only; the
rows the Owner taps are below it as flat task lists, because a checkbox is only tappable as a real
list item at block level and a table cell parses inline.

**1 · \<area\>** · \<n\> min · [S1](smoke/INVENTORY.md)
\<exact steps, one line\>
**Expect** \<one observable outcome\> · **Why** \<one clause\>

- [ ] pass
- [ ] fail —
- [ ] n/a —

Unchecked means *not reached* — the doc is stop-anywhere, so fail needs its own box. Every
`n/a` owes a few words; those prune the next inventory. Full hypotheses live in
`smoke/INVENTORY.md` under the row id.

**Deliberately not tested:** <area — why>. **Accepted-untested:** <surface — why there is no
check at all>.
