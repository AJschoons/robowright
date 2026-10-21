# Surface inventory — <TICKET>

**Diff:** `<base sha>..<head sha>` — <n> files, <n> hunks.
**Walk depth:** one hop from changed symbols; two hops for <name the foundation-level
symbols that earned it>. Stopped there.

## Surfaces

| Id | Surface | Class | What changed | Risk hypothesis | P | Lane |
|---|---|---|---|---|---|---|
| S1 | <screen + control> | Changed | <clause> (`file.swift:120`) | <the specific way this breaks> | P0 | Agent |
| S2 | <screen + control> | Touched | <clause> (`file.swift:40`) | <…> | P1 | Both |
| S3 | <screen + control> | Blast-radius | Caller of <symbol> (`other.swift:88`) | <…> | P1 | Manual |

Class: `changed` (diff intends a visible difference) · `touched` (intends none — check it's
identical) · `blast-radius` (not in the diff, downstream of it).
Lane: `agent` · `manual` · `both` · `accepted-untested`.

<!--
A row with no concrete risk hypothesis is a row that should not exist. "Sorting might not
work" is not a hypothesis; "the chip title comes from a view model that now initializes
after first layout, so it can render empty on cold start" is.
-->

## No user-facing surface

| File(s) | Why nothing to test |
|---|---|
| <path> | Test-only change |
| <path> | Dead code removal — grepped for string/storyboard/runtime lookups, none found |
| <path> | Docs |

## Accepted-untested

| Surface | Why there is no check |
|---|---|
| <surface> | <no seam to observe it through / needs hardware / needs real payment> |

## Counts

<n> surfaces: <n> changed, <n> touched, <n> blast-radius. Lanes: <n> agent, <n> manual,
<n> both, <n> accepted-untested. Priorities: <n> P0, <n> P1, <n> P2.
