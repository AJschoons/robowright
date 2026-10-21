# Agent smoke pass — <TICKET>

**Not `pass`: <n> of <N>.** <one line naming them, or "none">
Pass: <n>. Pre-existing: <n>. Blocked: <n>. Infra: <n>. Unverified: <n>.

<!--
The not-pass count leads. A report that opens with the pass count reads as green at a
glance even when it isn't, which is the exact failure this ordering exists to prevent.
-->

## Environment

| | |
|---|---|
| Tip build | <branch @ sha, .app path> |
| Base build | <base sha, .app path — required if any row is class `touched`> |
| Device | <name / UDID> |
| Account | <tier / state> |
| Flags | <state> |
| Harness | <what drove it — a simulator driver, a browser, the CLI> |

## Checks

<!--
ONE ROW PER CHECK. The oracle column is written BEFORE the run. If it was written after
looking at the result, the row is worthless — delete it and re-run properly.
-->

| # | Surface | Class | Oracle (written before running) | Base | Tip | Verdict | Evidence |
|---|---|---|---|---|---|---|---|
| S1 | <screen + control> | Changed | <the predicate, concretely> | n/a | <observed> | Pass | `evidence/S1-tip.png` |
| S2 | <screen + control> | Touched | <the predicate> | <observed> | <observed> | Pass | `evidence/S2-base.txt`, `evidence/S2-tip.txt` |

Verdicts: `pass` · `fail` · `pre-existing` (failed on base too) · `blocked` (couldn't reach
it) · `infra` (harness broke) · `unverified` (ran, no artifact settles it).

## Failures

<!-- One block each for fail / blocked / unverified. Delete the section if there are none. -->

### S<n> — <verdict>

- **Expected:** <the pre-declared oracle>
- **Observed:** <what actually happened>
- **Evidence:** `evidence/...`
- **Reproduce:** <the exact steps or command>
- **Not fixed here.** <what it likely is, one line — a smoke run reports, it does not repair>

## Not run

| Surface | Why |
|---|---|
| <surface> | <manual-lane: needs human judgment on X> |
| <surface> | <accepted-untested: no seam to observe it through> |

## Budget

<n> checks, <n> nav retries, <wall clock>. <"Complete" — or what was left uncovered and why,
in priority order.>
