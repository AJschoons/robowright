---
name: doc-gate
description: Pre-review gate for any prose artifact an agent hands to the Owner or publishes as them — project docs, deep-dive share-outs, PR descriptions, troubleshooting and knowledge-base docs, run handoffs. A fresh-context subagent produces a claim ledger (every load-bearing factual claim cited, downgraded, or turned into a question) and a trim pass (length budget, no selling, no narrative, team voice). Use before any doc reaches the Owner or a remote; the planner and builder skills invoke it at their hand-off points.
---

# Doc gate

Code has gates before the Owner sees it — the adversarial diff review, `load-bearing-tests`,
the gate review. Prose had none: a doc went from the agent straight to the Owner, who was its
first reviewer. Of the corrections the Owner had to type, most were about documents — a
premise stated as fact that was false, a fix explained that would not have fixed the bug, a doc that "sells" work already agreed,
a section of narrative about how the numbers moved, a team doc written as "I". This skill is
the missing gate. It runs as a **fresh-context subagent**: the author of a claim is the
worst judge of whether it is a claim.

## When

Before a document is handed to the Owner or written anywhere another person reads:

- the planner skill (`planner` in Robowright) — Phase 2 share-outs, Phase 3 `PROJECT.md`, Phase 6 change descriptions
- the builder skill (`worker` in Robowright) — change descriptions and `HANDOFF.md` at end of stack
- a change description, before it is saved (the Worker's publish step)
- any troubleshooting, research, or knowledge-base doc written for someone else

Not for: chat replies, ledgers, decision logs, code comments (`comment-pass` owns those).

## What the gate does

Two passes over the doc, one ledger out. The caller applies the verdicts; the gate is
read-only on the doc.

### Pass 1 — claim ledger

A load-bearing claim is any statement about code, platform, product, or process behavior
that the doc's argument rests on. Each one ends in exactly one state:

| State | Means |
|---|---|
| **Cited** | `file:line`, a URL, or a quoted source sits next to it, and the gate opened it |
| **Downgraded** | Rewritten as belief — "I believe", "could be the cause" — because no evidence was found |
| **Derived** | A count or number, with the command that produced it quoted beside it |
| **Ask** | An assumption about the Owner's own process, vendors, or preferences; becomes a question, not an assertion |
| **Deleted** | A claim the doc does not need |

Specific traps the ledger exists to catch, each of which has cost a correction:

- **A premise carried from an earlier doc.** "`NoteStore` saves on every keystroke" was
  false and propagated from one doc to the next. Re-verify inherited premises against the code or
  the API doc, not against the doc they came from.
- **A proposed fix that does not reach the bug.** If the doc says "the fix is X", the ledger
  names the failing path and shows X changes it. "Prefixing the asset name" did not fix a
  repo-wide `latest release` lookup.
- **Repro steps that were never run.** Steps handed to the Owner are `cited` only with the
  evidence path of the run that reproduced it. Otherwise they are `downgraded` to "steps I
  expect to reproduce it".
- **Numbers.** Coverage figures, LOC splits, test counts — `derived` with the command, or
  out. A coverage number for a view controller with no tests is a bug in the tooling, not a
  fact.
- **Product vocabulary.** "New users" is not "logged-out users". A term the doc's premise
  rests on is `cited` to the ticket, the design doc, or the person who defined it.
- **The Owner's own workflow.** How the Owner tracks their own tasks, which steps they run by
  hand, whether someone else should run a spike — `ask`, never asserted.

### Pass 2 — trim

Patterns the Owner has cut, applied mechanically. Each hit is `cut`, `rewrite`, or `keep` with
the pattern named.

- **Selling.** Any sentence whose job is to convince the reader the work matters, when the
  reader already agrees it does. State the ask and the size; stop.
- **Narrative.** How the change came about, what was tried, "numbers that moved", a section
  recounting the investigation. The reader's present tense only. Cut the section, not the
  sentences.
- **First person in a team doc.** A project doc, a share-out, a PR body is written for the
  team to move the work forward. "I think we should" becomes the recommendation.
- **Sounds generated.** Synthesizing closers ("so X governs Y"), three-item rhythm,
  hedged confidence about a decision already made, meta-labels grouping the interesting
  bits. The Owner's register rule, when the machine has one, carries the full list; this pass
  applies the items here.
- **Length.** Change descriptions: one paragraph of AI content, two at the ceiling. Docs: if
  it could be shorter by a third, it should be; cut whole sections before trimming sentences
  inside them. A document over a word cap the caller names is `BLOCKED`, never `cut`: the
  author cuts it and gates it again.
- **Certainty language.** "Is the cause" → "could be the cause" unless the ledger has it
  `cited`. Hedge claims about what a design cannot do and about future tickets; de-hedge
  statements about the current change.

Never touched: any slot the project hook → Publishing reserves for the Owner's own words and
anything below it, code fences, tables, `## testing` sections, emoji, an AI-written label.

## Running it

Spawn one fresh-context subagent per document. Inputs: the doc path, read-only access to
the repo or worktree it describes, and any evidence directory the doc cites. Not: the
conversation that produced the doc, the author's reasoning, or a summary of what the doc
"is trying to say".

Prompt shape (adapt the paths; keep the posture):

```
You are gating one document before a human reads it: <doc path>. You did not write it and
you do not trust it. Repo for verification: <worktree>, read-only. Evidence: <dir or none>.

Pass 1 — claim ledger. List every load-bearing factual claim about code, platform, product,
or process. For each, open the source and mark it cited (with file:line or URL), derived
(with the command), downgraded (rewrite as belief), ask (an assumption about the Owner's own
process), or deleted. Re-verify premises inherited from other docs against the code, not
against those docs. A proposed fix must be shown to reach the failing path. Repro steps are
cited only with the evidence of a run.

Pass 2 — trim. Mark each hit cut / rewrite / keep with the pattern: selling, narrative,
first person in a team doc, sounds generated, over length, certainty without a citation.
Cut sections whole before trimming sentences. Over a word cap named here is BLOCKED, not cut. Do not touch the Owner's reserved slot or anything under it,
code fences, tables, testing sections, emoji.

Output <out path>/DOC-GATE.md: the ledger as a table (claim · state · evidence), the trim
verdicts as a list (quote · verdict · pattern), then one line: READY, or BLOCKED with the
ask items that need the Owner and any word cap exceeded. Under one page. Read-only on the document.
```

Apply the verdicts yourself. Every `ask` goes to the Owner as a question before the doc does; a
doc with open asks is not handed over as finished. Record in the ledger or exploration doc
that the gate ran, with the counts. "Nothing to change" is a valid result and is still
recorded with the enumeration that proved it.

## What this is not

Not a style review — the Owner's register rule, when the machine has one, defines the voice;
this applies its cuts. Not a
correctness review of code — the adversarial review owns that. Not a second opinion on the
decision the doc records. If the gate finds itself arguing with the doc's conclusion rather
than its claims, that is a finding for the Owner, phrased as an `ask`, not a rewrite.
