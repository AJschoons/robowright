---
name: grilling
description: Interview the Owner relentlessly about a plan, design, or decision before anything is built — a design tree worked in numbered rounds, every question carrying a recommended answer, ending in a decision record. Use when the Owner says "grill me", asks to stress-test or think through a plan, when a request carries several open decisions, or when another skill calls for a grilling pass (planner Phase 2, bdd's Discover step).
---

# Grilling

Adapted from Matt Pocock's `grilling` skill (MIT, <https://github.com/mattpocock/skills>).

Interview the Owner relentlessly until you reach a shared understanding. Map the plan as a **design
tree**: every decision branches into the decisions that hang off it.

## Rounds

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already
settled: the questions you can ask *now* without guessing at answers you haven't heard yet. Ask
the frontier in one round, numbered, each with your recommended answer, then wait. A question
whose answer depends on another question still open in this round belongs to a later round.

A frontier wider than six asks the six that unblock the most and carries the rest forward.

```
**Q1 — <title>** *(one-way door, when it is one)*
<the question. Where it is genuinely open: 2–3 options, each with what it costs.>
**Rec:** <your answer> — <the reason in one line; a fact gets its `file:line` or doc link>

**Q2 — …**

**Assumed** — reversible calls I made myself; object to any:
- <the call> — <why>
```

Each round's answers reshape the tree: settled decisions push the frontier outward and unblock
what depended on them. Recompute the frontier and ask the next round.

## What earns a question

A decision earns a question when it clears the `decision-reporting` threshold: it constrains the
future, trades one real thing for another, reaches outside the files in play, or a competent
engineer could go the other way. Everything below that line you decide yourself and list under
**Assumed**, so a round stays short enough to answer by voice.

Two kinds always earn one. A **one-way door** — persisted shapes, public API and protocol
surfaces, new dependencies, migrations, anything shipped or built on — carries the tag. And
*structural or unrelated?* (`sizing-the-move` rules 1 and 2), whenever that call is open.

## Facts are yours, decisions are theirs

Finding *facts* is your job. When a frontier question needs one — what the code does, how an API
behaves, what a library supports — dispatch a sub-agent for the codebase, research online for
anything beyond it, and cite what comes back with its certainty level. A running exploration is
an unsettled prerequisite: the questions downstream of it wait for the report, and the rest of
the frontier goes out now. The *decisions* are the Owner's: put each one to them and wait.

Be opinionated. When an answer looks like a mistake, say so once, with the reason, in the next
round; after that it is their call.

## Reading their answers

The Owner may dictate. One reply covers several questions, out of order, with approximate names. Match
each part to its question by content and resolve garbled symbols from the codebase.

- "take your recs" settles every question they did not address that round at its recommendation.
  Without it, an unaddressed question stays on the frontier.
- An answer that contradicts an earlier one, or the code, opens the next round as Q1.
- When they turn down a recommendation, keep their reason in their words: it becomes the record's
  **Rejected** entry.

## Done

The session is done when the frontier is empty: every branch visited, nothing silently assumed.
Write the **decision record** and show it to them:

- **Decisions** — chose X over Y because <reason>. Costs: <what was given up>.
- **Rejected** — the approach, who killed it, the reason in their framing.
- **Assumed** — every call you made for them, all rounds.
- **Parked** — ruled unrelated to this effort, and where it was recorded.
- **Still open** — blocked on a fact or a person, with what unblocks it.

Append it to the log `decision-reporting` names, under `## YYYY-MM-DD — grilling: <topic>`.
Standalone, building starts once the Owner confirms the record.

## Called by another skill

The caller may set two things, and its word wins: **what earns a question** (`bdd` asks every
Question in its pile) and **where the record lands** (`bdd`: the behavior table's source column;
`planner`: `<project>/DECISIONS.md`). Rounds, recommendations, and reading their answers stay as
above. When the frontier is empty, hand back to the caller's next step.
