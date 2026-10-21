# <name> — a one-off

**Project:** <name> — a one-off: one unit, no Lead (`robowright.json` → `shape: one-off`)
**Work order:** [`<YYYY-MM-DD>-<slug>.md`](./<YYYY-MM-DD>-<slug>.md), grounding in [`<slug>-grounding.md`](./<slug>-grounding.md)
**Robowright Session:** `<sessions_root>/<ticket>/`

> Sizes and complexity are deliberately relative — translating to calendar days requires deeper planning than this workflow covers.

## Context

<The work order's Destination and Why, two or three sentences.>

## Language

The work order's Language section, copied.

| Term | Means | Avoid |
|---|---|---|
| <term> | <one line> | <the words it replaces> |

## Task Breakdown

> The `Unit` cell is the unit's `run.json.ticket`. `Summary` is one or two plain sentences on what the unit does, never its status; the dashboard shows it as the unit's purpose line, and the owner brief's word cap is read from `Size`.

| # | Unit | Summary | Tracker | Description | Exploration Doc | Size | Complexity | Status |
|---|------|---------|---------|-------------|-----------------|------|------------|--------|
| U1 | `<ticket>` | <One or two sentences: what this unit does> | — | <The work order's Approach, one line> | The work order | <XS / S / M> | <Low / Medium / High> | Not Started |

## Resolved Decisions

| Date | Decision | Who | Source |
|------|----------|-----|--------|
| <M/D> | <each of the work order's Decisions, one row> | The Owner | The work order |

## Related Documents

- [`DECISIONS.md`](./DECISIONS.md) — seeded from the work order's Decisions and Rejected
- the work order and its grounding, linked in the header
- `<sessions_root>/<ticket>/BRIEF.md` — the brief; `INTAKE.md` and the owner brief follow when the session finishes
