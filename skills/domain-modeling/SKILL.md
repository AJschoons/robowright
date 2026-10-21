---
name: domain-modeling
description: Build and sharpen a project's domain model. Use when discussing codebase terminology, when a term in an ask or a plan is fuzzy or overloaded, or when writing or editing a glossary (`CONTEXT.md`).
---

# Domain modeling

Adapted from Matt Pocock's `domain-modeling` skill (MIT, <https://github.com/mattpocock/skills>).
The session moves and the glossary format are that skill's; where the glossary lives and where
decisions go are the Owner's.

Actively build and sharpen the project's domain model as you design. This is the *active* discipline: challenging terms, inventing edge-case scenarios, and writing the glossary down the moment a term crystallises. (Merely *reading* the glossary for vocabulary is not this skill: that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.)

## Where the glossary lives

- A repo whose root holds `CONTEXT.md` or `CONTEXT-MAP.md` has opted in: that file is the glossary.
  Opting a repo in is the Owner's act.
- Every other repo: `<projects root>/glossaries/<repo>.md` — the projects root the profile → Paths
  names, beside the project folders — named for the repository rather than the
  worktree (`basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"`).
  Work with no repo under it: `<projects root>/glossaries/<topic>.md`.

Create the file lazily, when the first term is resolved. Both homes use the format in
[CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md).

A private glossary is invisible to an agent that goes looking, so a document handed to another
agent — a work order, a brief — inlines the definition of each glossary term it uses.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in the glossary, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y. Which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account': do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible. Which is right?"

### Update the glossary inline

When a term is resolved, update the glossary right there. Don't batch these up: capture them as they happen.

The glossary should be devoid of implementation details. Do not treat it as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Decisions go to the decision log

A decision that crystallises while modeling — hard to reverse, surprising without context, the
result of a real trade-off — belongs to the decision log the Owner's own rules name, when the
machine has them, or to the calling skill's record (`grilling`'s decision record, a work order's Decisions section). The glossary
carries the term the decision settled, and the log carries the decision.
