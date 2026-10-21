# <unit> — [Short title]

> **Project:** [project name] — [design link or N/A]
> **Scratch plan:** in the inbox the profile's **Paths** section names
> **Tracker:** [link, in the project hook's **Naming** form, or N/A]
> **Architecture classification:** [Structural / Migration / Small-non-structural] — [one-line reason, e.g. "touches core feature controllers and DI plumbing"]
> **Related tech-debt:** [link] *[remove if N/A]*

---

## 1. Goal

[1-3 paragraphs framing the change.

What does this unit actually do? What's the user-visible (or developer-visible) outcome? What does it leave for later units?

Be concrete about the seam being moved or the behavior being added. Anchor on specific file paths and method names when possible.]

[Note the flag gating story when the change ships behind a flag — what's behind the flag, what's preserved on the legacy path, what happens at the eventual flip.]

---

## 2. Files to be modified

| File | LOC delta | What changes |
|---|---|---|
| `[path/to/File1]` | +~N | [What changes — new property, new method, refactor, etc.] |
| `[path/to/File2]` | -~N / +~N (~0 net) | [What changes] |
| `[path/to/File3]` | 0 (or 1-line update) | [What changes] |

**Files explicitly NOT modified in this unit** (deferred to later units):

- `[path]` — [reason]
- `[path]` — [reason]

---

## 3. Code references

### 3.1 [Subsection name — e.g. "Current construction site"]

```[startLine]:[endLine]:[path]
[code snippet — the thing being changed]
```

[Brief commentary if needed.]

### 3.2 [Subsection name — e.g. "Where it moves to"]

```[startLine]:[endLine]:[path]
[code snippet — target state]
```

### 3.3 [Subsection — call sites, transitional accessor, etc.]

```[startLine]:[endLine]:[path]
[code snippet]
```

### 3.4 Behavior table *[only for a unit that migrates untested logic — delete otherwise]*

Extracted with the `characterize` skill from `[base sha]`. The table itself:
`[<unit>-behaviors.md, beside this doc]` — scaffolding, deleted at wrap-up.

```
Rows: [n] · tier 1: [n] · tier 2: [pending the Owner's call] · tier 3: [n] (holds [n], corrected [n]) · unchecked: 0
Trace: [n] decision points + [n] outcome statements → [n] mapped, [n] dead, [n] unobservable, [n] undetermined, 0 unaccounted
Suspects: [n] rows, [n] causes — [ids, grouped by cause]
```

**Findings before anything moves:** [dead branches to drop rather than migrate, unobservable
writes, names that lie — each with `file:line`.]

**Suspects — the Owner's call, one question per cause:**

| Rows | What the code does | Why it looks unintended | Preserve / fix as its own unit |
|---|---|---|---|
| [B9, B10] | | | [answer + date] |

**Facts needed — what the code could not say:**

| Fact | Rows and `undetermined` dispositions waiting on it | Answer |
|---|---|---|
| [storyboard slider minimum] | [B10, D4] | [answer + date] |

**Tier-2 observation — the Owner's risk call:** [candidates table and recommendation in
`characterize/reference/fidelity.md`'s shape.] **Decision:** [none / rows … / all] — [date].

### 3.5 Outside grounding *[only for a unit that leans on platform or library behavior the project's `GROUNDING.md` does not cite — delete otherwise]*

| Fact the unit leans on | Source | Certainty |
|---|---|---|
| [fact] | [link] | [the docs say / I believe / unsure] |

**Named pattern:** [name, who named it, what it recommends] **Dissent:** [the counter-argument, and how it was answered]

---

## 4. Implementation steps

Commit-by-commit plan. Each step leaves the codebase in a compilable state and is reviewable on its own.

### Step 1 — [name]

[What changes in this step. Cite the files and methods affected.]

```
[commit message]
```

### Step 2 — [name]

[What changes.]

```
[commit message]
```

### Step 3 — [name]

[What changes.]

```
[commit message]
```

[More steps as needed.]

---

## 5. Risks

### Risk 1 — [name]

**What can go wrong:** [description.]

**Mitigation:** [how it's avoided / detected.]

**Severity:** [Low / Medium / High]

### Risk 2 — [name]

**What can go wrong:** [description.]

**Mitigation:** [...]

**Severity:** [...]

---

## 6. Tests / smoke pass

### Verification commands

The exact commands that prove this unit, so the implementing session can run them unprompted and paste evidence rather than asserting success. Command shapes come from the project hook → **Build** and **Tests**; what goes here is the scoping this unit needs.

```
[build command — per the project hook → Build, including the test-target build if the default build skips it]
```

```
[focused test command for this unit's test surface — per the project hook → Tests]
```

### Smoke pass

Run the `smoke-test` skill at the end of the unit — it builds the surface inventory from the
real diff, runs the agent lane unattended, and writes `<project>/smoke/<unit>/MANUAL-PASS.md`.
The rows below are the **planner's guess**, seeded before the code exists; the skill
re-derives them from the diff and will add, drop, or re-prioritize.

**Expected tier:** [Quick ~10min / Standard 25-35min / Deep 60-90min] — [one sentence why].

| # | Area | Do | Expect | Why | ~min | Lane |
|---|---|---|---|---|---|---|
| S1 | [screen] | [exact steps, one line] | [one observable outcome] | [one clause, <15 words] | [n] | Agent \| manual \| both |
| S2 | | | | | | |

No result boxes here — this is a planning doc, not the pass. The skill's `MANUAL-PASS.md`
adds `✓` / `✗` / `n/a` boxes as the **first three columns**, because a result column on the
right edge is off-screen in most markdown viewers.

A row with no concrete *why* is a row that should not exist — "sorting might not work" is
not a reason, "the chip title comes from a view model that now initializes after first
layout, so it can render empty on cold start" is.

**Expected `touched`-class surfaces** (refactors/moves reaching a screen, where the check is
"identical to before" rather than "the new thing happened"): [list, or "none"]. These oblige
the agent lane to build the **base** revision too — a pass on the tip alone proves nothing
about a pure move.

**Judgment-only rows** (no predicate can settle them — animation, layout at the edges,
feel): [list].
**Accepted-untested** (no seam, or needs hardware/real accounts): [list with reasons].

Standing candidates to consider, not to paste in wholesale — each still needs a *why* tied
to this diff: cold start / state restoration, network failure and offline, the accessibility
and form-factor rows the project hook's **Device** section names, and, when the change ships
behind a flag, the flag off as well as on.

### Automated tests

- [ ] [Unit test surface — which view models / utilities need new or updated tests]
- [ ] [Mock updates — which mock files need new stubs]
- [ ] [UI test impact — accessibility ids, deep links]

---

## 7. Size + complexity

**Size:** [XS / S / M / L / XL]
**Complexity:** [Low / Medium / High / Very High]

> Deliberately relative — not translated to calendar days. Sizes and complexity are comparative within this project and against similar past work.

---

## 8. Dependencies / sequencing

**Blocks this unit:** [list units that must be accepted first, or "none"]

**This unit blocks:** [list units that depend on this one being accepted]

**Coordinated with:** [other in-flight projects, server changes, design sign-off, etc.]

---

## 9. Out of scope

Explicitly deferred from this unit, with where it lands instead. **Every row is tagged
`unrelated` or `structural`.** `unrelated` (adjacent cleanup, a drive-by bug, a logging-API
modernisation of moved lines) is what this section is for. `structural` — a seam, a state
member, a protocol, a redesign that this unit's end state needs — **may not be deferred**: do
it in this unit, or split the unit so it is done first. A `structural` row surviving into
implementation is a finding for the adversarial review. (`sizing-the-move` rules 1–2.)

1. `unrelated` — [Deferred item] — handled in `<unit>` (see [`<unit>.md`](<unit>.md))
2. `unrelated` — [Deferred item] — captured in PROJECT.md's Deferred Polish section
3. `unrelated` — [Deferred item] — out of project scope; capture as a standalone follow-up

---

## 10. Implementation Notes & Deviations *[appended after the unit ships]*

[Update this section once the unit is in review or accepted. Capture anything that deviated from the plan above — implementation surprises, scope changes, design decisions ratified mid-unit, refactors that crept in.]

- **[Deviation 1]:** [What changed, why.]
- **[Deviation 2]:** [What changed, why.]
- **[Opportunistic improvement]:** [What was bundled in beyond the original scope, why it was worth doing.]

[If the unit's scope grew significantly: note the original vs. shipped LOC count and the reason. If new gotchas were discovered: add them to PROJECT.md's Gotchas section and reference here.]
