# [Question being answered]

A decision document for the Owner: one scope question, the options, and a recommendation to accept or overrule.

> **Time-boxed AI deep dive ([X] minutes), reviewed by [the Owner]. Meant as a conversational jumping-off point, not a final recommendation.**

> Sizes and complexity below are deliberately relative — translating to calendar days requires deeper planning than this doc covers.

---

## The question

[One sentence, framed action-orientedly.

Good: "Should we cut note sharing or the flicker fix to fit the time box?"
Good: "What does the API contract need to look like for the new endpoint?"
Bad: "Note sharing is hard." (problem-oriented, not action-oriented)
Bad: "I'm worried about the flicker." (sentiment, not decision)]

---

## TL;DR recommendation

[One paragraph. Open with the recommended option.

"Recommend Option B (cut the flicker fix, keep note sharing). Ships the notes app's headline change inside the time box and leaves a one-frame placeholder flicker on first launch for a small follow-up. Asks: confirm the flicker can ship for one release; sign off on the fix being deferred."]

---

## Context

[What the agent investigated and what scope constraints framed the question.

- Project time box: [X weeks, or none]
- Current unit breakdown size: [estimated total size at current scope]
- Investigation included: [designs / files / prior discussion / prior project]
- Who the answer affects: [the Owner, plus anyone else the profile's and the project hook's duties name]

Link out to anything a reader might want to dig into:
- [Design link]
- [Related code area]
- [Existing tracker item]
- [Prior project reference]]

---

## Options

> Sizes and complexity are deliberately relative — comparative within this project and against similar past work. Not translated to calendar days.

### Option A — [short name]

**What it means:** [1-2 sentences describing the option concretely.]

**Pros:**
- [Pro 1]
- [Pro 2]

**Cons:**
- [Con 1]
- [Con 2]

**Size:** [XS / S / M / L / XL] · **Complexity:** [Low / Medium / High / Very High]

**Risks:**
- [Risk 1]
- [Risk 2]

### Option B — [short name]

**What it means:** [...]

**Pros:**
- [...]

**Cons:**
- [...]

**Size:** [...] · **Complexity:** [...]

**Risks:**
- [...]

### Option C — [short name] *[if applicable; default to 2-3 options total]*

**What it means:** [...]

**Pros:**
- [...]

**Cons:**
- [...]

**Size:** [...] · **Complexity:** [...]

**Risks:**
- [...]

---

## Recommendation rationale

[Why the recommended option, what it gives up, what's reasonable to defer.

"Option B feels right because it keeps the headline change and defers a regression nobody can see (a one-frame placeholder flicker on first launch). The deferred work can ship as a small follow-up."

If the recommendation hinges on the Owner's gut-call about which option fits confidently vs. risky, state that explicitly:

"Picking Option B over Option A is a gut-call on fit — Option A is technically achievable but would leave less room for the QA matrix at the end of the project. Recommend B if the time box is fixed; A if it can stretch."]

---

## What I need from you

Explicit asks per decider so it's clear who decides what. The Owner decides anything the profile's
**Owner-only floor** covers; the profile's and the project hook's duties name anyone else who has to weigh in.

- **Owner:** [specific question / sign-off needed]
- **[Role / name]:** [specific question / sign-off needed]
- **[Role / name]:** [specific question / sign-off needed]

If someone isn't needed for a decision, leave them off this list — keeping it tight keeps the conversation tight.

---

## Decision-by deadline

**By [day, time]** — so the project doesn't stall. Default to EOD or within 24 hours.

If there's no answer by the deadline, [fallback plan: default to the recommendation / take it to the Owner directly / cut the lowest-impact option].

---

## Next steps if [recommended option] is approved

[Concrete follow-up actions — follow-ups to file, PROJECT.md updates, design work to capture, etc.

- Update PROJECT.md Resolved Decisions section: "[Decision]: Option B chosen on [date]. Rationale: [one-liner]."
- File a follow-up for the deferred flicker fix, in the form the project hook's **Naming** section defines
- Note the resolution wherever the profile's and the project hook's duties say it goes]
