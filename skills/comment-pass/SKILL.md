---
name: comment-pass
description: Strip narrative from the comments and docs a change adds, keeping only what helps a first-time code reviewer and what a future agent could not infer. Use before opening a PR, when reviewing a stack's documentation, when asked to tighten or trim comments, or whenever agent-written code carries prose that only makes sense to whoever implemented it.
---

# Comment pass

Agent-written code over-comments, and it over-comments in a specific, diagnosable way: it narrates
**the work** instead of describing **the code**. The author has the old version, the ticket, and the
whole session in their head, so prose that reads as insightful while writing reads as noise to
everyone who comes after. This is a recurring cleanup, not a one-off — run it as a deliberate pass
before a change is reviewed.

## The two audiences, and nobody else

Every comment has to earn its place with one of these. A comment serving neither gets deleted, not
shortened.

1. **A code reviewer meeting this code for the first time.** They have the new code and nothing else
   — no old version, no ticket, no session. Code is read far more than written, so the question is
   always "what does a stranger need to not misread this?"
2. **A future agent or engineer changing this code.** They need the constraint that will bite them:
   the ordering that matters, the API that behaves unexpectedly, the invariant the compiler does not
   enforce.

Anything that exists to show the reader how the change came about is serving the *author*, and the
author is not one of the audiences.

## Delete on sight

Six patterns, in rough order of how often they appear:

- **Change history.** "the body is the `didSet` this replaced", "rather than a `receive(on:)`-hopped
  subscription", "no longer does X", "converted from ObjC", "was a class, so only one field
  published". The reader cannot see the old code and does not care. It belongs in the commit message
  and the PR body, which is where it will still be true in a year.
- **Ticket arc and roadmap.** "the end state <TICKET> is building towards", "the flip PR", "the next
  change, once their `didSet` bodies are intents", "sequenced after this container". Rots the moment
  the sequence changes, and means nothing to someone who never saw the stack.
- **Rhetorical framing.** "And the payoff:", "What this bought:", "The sharpest case is". Essay
  scaffolding. State the fact.
- **Restating the symbol.** `/// Precomputed formatted note count strings keyed by folder ID` above
  `noteCountLabelByFolderID: [String: String]`. If a clause survives deleting every word the
  name and type already say, keep only that clause.
- **Justifying a decision nobody questioned.** Defending the chosen approach against an alternative
  that was never proposed, or describing a line that did *not* change.
- **Provenance in prose.** "(September 9th, 2025)", "added for the Y flow", author names. `git blame`
  owns this and never goes stale.

## Keep, and tighten

- **What a symbol *is*, when the name genuinely doesn't say it** — units, bounds, the distinction
  from its near-neighbour. `Whether the user is mid-swipe. Narrower than activeRowGestureType: a
  tap is a gesture but not an interaction that reveals the row actions.`
- **A constraint the compiler does not enforce.** Ordering requirements, "assign the whole struct,
  never a field", single-writer rules, "this must run before X".
- **A platform or library behaviour that will surprise the next reader.** "`withObservationTracking`'s
  handler is `@Sendable`, so the flag needs a box." Cite the mechanism, not the debugging story.
- **Why the code looks wrong but isn't.** The single highest-value comment there is: it stops a
  reviewer flagging a deliberate oddity, and stops the next agent "fixing" it.
- **A deliberate omission.** "no view reader on purpose" plus the ticket that decided it.
- **A documented annotation vocabulary.** A terse repeated marker (`// value-equal`,
  `// grouped(3) · no-equal`) defined once in a README earns its repetition — it is a machine-
  readable contract, not prose.

## The rewrite that fixes most of them

Narrative comments usually contain a real fact wrapped in a transition. Keep the fact, drop the
transition:

> ~~The single writer for the selected-note axis; the body is the `didSet` this replaced. `oldValue` is taken
> before the write because the deselect below needs the outgoing note.~~
>
> The single writer for the selected-note axis. `oldValue` is read before the write because the deselect below
> needs the outgoing note.

> ~~Everything derived from the selected folder hangs off here rather than a `didSet`, which `State` cannot
> host: the derivations call back into the view model.~~
>
> Everything derived from the selected folder. `State` cannot host this as a `didSet` — the derivations call
> back into the view model.

The test: **read the comment as if the change never happened.** If it only parses as a diff against
something invisible, rewrite it in the present tense or delete it.

## Doc files are the same pass, higher stakes

`ARCHITECTURE.md` / `README.md` sections a change rewrites get the same treatment, plus one more
check that code comments do not need: **every factual claim must be true against the tip.** A doc is
read as a contract. Verify counts, writer counts, line numbers, and "there are no X" claims by
grepping, not by memory — these are the claims that were true mid-stack and are false at the
end. Prefer naming the mechanism over quoting a number that will drift.

Dated status paragraphs ("**Status 2026-09-10.**") are fine in an architecture doc and wrong in a
code comment: the doc is a record, the code is not.

## Running the pass

1. **Enumerate, don't browse.** Per PR or per commit range:
   `git diff <base>..<tip> -- '*.swift' | grep -E '^\+\s*(///|//)'` and the same for `'*.md'`.
   Reviewing what you *remember* writing misses the moved comments.
2. **Classify every line** against the two audiences. Most lines are obvious; the arguable ones are
   usually change-history wearing a "why" costume.
3. **Read each survivor as a stranger.** Does it reference something not on screen? A previous API, a
   sibling PR, a ticket's sequence? Rewrite or cut.
4. **Check the deletions didn't take a fact with them.** If a narrative sentence was the only place a
   real constraint was recorded, restate the constraint plainly before deleting.
5. **Commit separately**, one commit per PR, so the cleanup is reviewable on its own and does not
   muddy the diff of the change itself. Subject: `<TICKET> trim the <area> comments to the contract`
   or similar — describe the result, not the activity.

## Calibration

- Default to **one line**. A `///` that runs past two sentences is usually carrying narrative.
- A comment block longer than the code it documents is a signal the *code* needs work, not that the
  comment needs expanding.
- Deleting is cheaper than it feels. A fact worth keeping is usually worth keeping in six words.
- Do not add comments during this pass except to replace a deleted narrative sentence that carried a
  real constraint.

## Why this keeps happening

The model writing the code has maximal context at exactly the moment it is least able to tell which
parts of that context are shared with the reader. Every explanation feels load-bearing while the
work is fresh. That is why this is a *separate pass* with a *different frame* — approach the diff as
someone who has never seen it, and the narrative becomes obvious.

Project rules that layer on top: the language style rule the profile or the project hook names, if any, and
whatever repo-level convention doc the project uses (e.g. an `AGENTS.md`) → "Comments &
Documentation", which may already ban change-history comments and ticket references in source.
This skill is how to *find and remove* what those rules say not to write.
