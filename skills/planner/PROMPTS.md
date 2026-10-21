# Reusable prompts

Copy-pasteable prompts for kicking off the Planner and per-unit sessions in the `planner` workflow (Robowright: `~/.claude/skills/robowright/SKILL.md`).

The Planner session runs Phases 1–5 and ends when the first brief exists; Phase 6 is a fresh Lead session, and every later brief is a fresh brief-only Planner (see `SKILL.md` → "Brief-only session"). In the attended fallback below, each unit session is a fresh, full Claude Code session — spun up for a single unit, named, given enough context to do that unit independently, and **ended when the unit's wrap-up is done**. The project docs are the handoff between sessions; never `/compact` across a unit boundary to keep going.

Paths below are relative to the roots the machine profile's **Paths** section names: `<project>/` is the project folder. How a session is started comes from its **Launch** section; session names and the `<base_ref>` come from the project hook's **Naming** section.

Where a project has its own written implementation-agent brief, point the fresh session at that file instead of the generic onboarding prompt below — it carries the same structure plus the project's specifics.

These prompts are the **attended fallback**. The Phase 6 default is an unattended `worker` Robowright Session launched and watched through the `lead` skill; that skill carries the launch line, the resume and nudge messages, and the intake prompt.

---

## Planner kickoff (start of project)

Use when starting a brand new project. Fire this in a fresh Fable session, started in the project folder per the profile's **Launch** section and named `planner-<project>`.

```
Run the `planner` skill from scratch for project `<project>`.

Inputs:
- Time box: <X weeks, or none>
- Designs: <link or N/A>
- Prior discussion: <links or N/A>
- Related tracker items: <comma list or N/A>
- Related docs / RFCs: <paths or links or N/A>
- Anything else you should read first: <notes or N/A>

Start with Phase 1; ask me for anything missing before proceeding. At the end of Phase 1, present the anticipated unit breakdown with size and complexity per unit and ask me which feel confident-to-deliver vs. risky.
```

---

## Sub-agent: onboarding (start of each unit)

Use when kicking off a fresh sub-agent for a specific unit. Adapt the project name and unit id.

```
Read `<project>/PROJECT.md` first. Its **Status & Progress** section names the next unit and what you inherit from completed ones; **Deviations** and **Gotchas** carry what previous sessions learned the hard way — trust them over anything staler.

Then read ONLY the exploration doc for that unit in `Agent Explorations/` (implementation steps, risks, code citations). Don't pre-read the other units' docs — but do skim §10 (Implementation Notes & Deviations) of the completed predecessors, which carry forward-looking notes aimed at you.

You are a one-unit session: when this unit's wrap-up is done, you stop, and the next unit gets a fresh session. Anything that must outlive this session goes in the docs, not chat.

After reading, confirm what you understand and which unit is next — but ask me to confirm before planning.

Also read the always-on rules that govern how we work:
- the Owner's own rules, when the machine has them
- `~/.claude/skills/robowright/RULES.md` — how big a move to make, and what gets deferred
- the project hook's **Publishing** section — what "published" means here and what a change description has to carry

When you're done onboarding, list:
1. What you understand about the project
2. Which unit you think is next
3. Anything unclear or that's diverged from the docs you'd want me to confirm before planning
```

---

## Sub-agent: unit planning (after onboarding confirmed)

Use after the sub-agent has onboarded and you've confirmed the unit. This prompt produces the commit-by-commit implementation plan.

```
Re-sync first, in a subagent: have it run every duty the profile, then the project hook, lists for `planner.brief`, plus a scan of the codebase and recent merges, and report ONLY deltas against PROJECT.md. Raw dumps stay out of this session. If the tracker item, PROJECT.md, and the exploration doc disagree, flag it instead of picking one.

Then pull in the remaining context yourself (the corresponding `Agent Explorations/<unit>.md` doc, related codebase files, designs if linked) and verify the exploration doc's code citations against the real code — they drift.

Then create an incremental step-by-step implementation plan where:

- Each step is a single reviewable and committable unit
- Each step leaves the codebase compilable / runnable
- Steps build on each other logically — earliest steps are smallest / safest, later steps build on settled foundations
- The whole unit is sized so one person can review it in one sitting. The numeric ceiling is per the project hook → **Publishing**, and it is a ceiling, not a target. If the unit is bigger than that, propose splitting it BEFORE we start — into the fewest pieces that each stay reviewable, never into one-move pieces.
- Size each move per the `sizing-the-move` rule: anything structural the end state needs goes in now, fully; anything unrelated is recorded in the exploration doc's §9 as `unrelated` and not done. No `known gap` notes, no forwarders kept for their tests.

For each step, include:
- A short name
- What changes (files + brief description)
- A proposed commit message on its own line in a fenced code block, ready to copy

After the steps, list:
- Risks I should know about, with mitigations
- The smoke pass — run the `smoke-test` skill against the diff rather than listing checks freehand. I want the agent lane run first and its results, then a manual pass doc with a tier, a why per row, and an N/A column. Say which rows I still have to judge myself and which you already settled
- Anything that diverged from the exploration doc — call it out so we can update the doc

Don't start executing. Wait for my go-ahead. Then execute one step at a time, stopping after each one for review.
```

---

## Sub-agent: adversarial diff review (code complete, before the Owner reviews)

Use when the unit's code is complete, before presenting it for human review. The point is a reviewer that isn't biased toward code it just wrote.

```
The unit's code is complete. Before I review it, run an adversarial review.

Spawn a fresh-context subagent whose only inputs are:
- the full diff: `git diff <base_ref>...HEAD`
- the exploration doc: `<project>/Agent Explorations/<unit>.md`

It reports findings with file:line references, checking:
1. Implementation steps (§4) that didn't land, or landed differently than described
2. Risks (§5) whose stated mitigations are not actually present in the diff
3. Changes outside the stated scope (§9)
4. Any §9 row tagged `structural`, or any `known gap` / TODO in the diff whose subject is structural to this unit — those are findings, not notes
5. Correctness bugs in the changed lines
6. The Review Overlay, when a `reviewer.overlay` row names one (`PROFILE-CONTRACT.md` → Review Overlay): I paste its paths here as `- **Review Overlay**: <paths, the profile's first, then the hook's> | none`. It is appended after the findings as `## Review Overlay`, each file's output headed by its path and in that file's own shape — its findings-eligible items in the classes `worker/prompts/REVIEW-GATE.md` names count as findings here, every other item is a note; a listed file that does not exist is said so once and is never a finding; `none` → no section, and the review says `no Review Overlay named` once

Correctness and stated requirements ONLY — no style findings, no speculative hardening. For each finding: fix it as one commit on top, or tell me why it should be deferred. A fix that fails a second review is verified by running, not by reasoning. Record what the review found (or that it found nothing) in the exploration doc's §10 either way.
```

---

## Sub-agent: change write-up (after the unit is done)

Use after the adversarial review is resolved and the branch is ready. This produces the change description + project doc update.

```
The unit is done. Time for the change write-up + project doc update.

1. Write the change description in the form the project hook's **Publishing** section defines. Run the `doc-gate` skill on it — fresh subagent, claim ledger and trim pass — and apply the verdicts before saving. Save it to `<project>/prs/<unit>.md` so I can copy-paste with formatting intact.

2. Update `<project>/PROJECT.md` — re-read it immediately before editing; the planner session writes it too:
   - Update the Task Breakdown table status for this unit
   - Update the Status & Progress paragraph
   - Add any deviations from the planned approach to the Deviations list

3. Update the corresponding `Agent Explorations/<unit>.md`:
   - Fill in section 10 (Implementation Notes & Deviations) with anything that diverged from the planned approach
   - Note any opportunistic improvements that crept in beyond the original scope
   - Note any new gotchas discovered — also surface them in PROJECT.md's Gotchas section

4. Identify the next incomplete unit from the Task Breakdown table and note it in the Status & Progress section.

After all of that, list:
- The change description file path
- A one-line summary of what changed in PROJECT.md
- A one-line summary of what changed in the exploration doc
- The next unit you'd suggest picking up

Then stop — the next unit gets a fresh session.
```

---

## Sub-agent: end-of-unit / in-review update

Use when the unit is in review and you've gotten reviewer feedback that surfaced new context worth capturing. This is a smaller maintenance update.

```
The unit is in review and reviewers surfaced new context I want to capture in the project docs before it leaks out of memory.

Re-read PROJECT.md and the corresponding `Agent Explorations/<unit>.md`. Then update both with:

- Any new gotchas surfaced by review (add to PROJECT.md Gotchas)
- Any design / architectural decisions that came out of review (add to PROJECT.md Resolved Decisions)
- Any deviations from the planned approach that surfaced during review iteration (append to the exploration doc's Implementation Notes & Deviations section)
- Any follow-up items reviewers flagged (add to PROJECT.md Deferred Polish or file as standalone follow-ups)

Don't change the Task Breakdown status (it's still In Review until the Owner accepts it). Keep the docs honest about what happened.
```

---

## Phase 2 deep-dive prompt (sub-agent for a single scope question)

Use when you need a time-boxed AI deep dive on a specific scope question during Phase 2. Adapt the question and time box.

```
Time-boxed deep dive: <X minutes, hard stop>.

Question: <the specific scope question — action-oriented framing, e.g. "Should we cut note sharing or the flicker fix to fit the time box?">

Context to investigate:
- Project time box: <X weeks, or none>
- Current unit breakdown is at: `<project>/PROJECT.md` (read it first)
- Designs: <link or N/A>
- Related code area: <paths or N/A>
- Existing tracker items / docs: <list or N/A>
- Who the answer affects: <list of deciders>

Stop hard at the time box — don't spiral. Produce a deep-dive decision document from `~/.claude/skills/planner/DEEP-DIVE-TEMPLATE.md`. Save it to `<project>/Deep Dives/<topic>.md` (create the folder if it doesn't exist).

The doc must:
- Open with the standard disclaimer ("Time-boxed AI deep dive, reviewed by [the Owner], conversational jumping-off point, not a final recommendation")
- Be action-oriented (concrete options + a recommendation, not a problem statement)
- Include 2-3 options each with size + complexity (relative, not days)
- List explicit asks per decider
- Specify a decision-by deadline (default EOD)

After saving, surface the recommendation summary in chat so I can review it before anything goes out.
```

---

## Replan (the Owner changes a running project's plan)

Use when the Owner wants units added, re-cut, parked, reordered or renumbered mid-project, or a settled decision reopened. Fire it in a fresh session on `models.planner`, started in the project folder per the profile's **Launch** section and named `planner-replan-<slug>`; the Owner stays in the chat. The steps are `SKILL.md` → "Replan session".

```
/planner replan <project> <the ask, in my words>

Read PROJECT.md and DECISIONS.md in full first, and the roster for what is in flight. Grill me on the ask against the plan until nothing is open. Renumber existing rows only where I say so. End with REPLAN-<date>-<slug>.md in the project folder, the Task Breakdown rows in PROJECT.md, and the decision record in DECISIONS.md. Nothing in a repo.
```

**The worked example** is a replan of this system's own project: eight changes to the system itself, asked for before two attended rollout units ran. Its header names the Owner, the Planner and its interactive four-round grilling, the `DECISIONS.md` heading holding the record, and the base the first stage starts from. **Why** gives the ask in the Owner's words and the reason the rollout units move behind it. **Units** is one table — number, slug, repo, size and complexity, depends on, run mode — in which the two rollout rows keep their slugs' subjects, take the last two numbers, and carry `(was U<n>)`; the stages follow, one line. After them: why one small unit still runs as a Robowright Session, the standing constraints restated unchanged, and the rule for exploration docs — the small units specified in place, each larger one getting its own exploration doc before its brief and linking the replan until then. One section per unit follows — the small ones at exploration depth, the larger ones as scope bullets, the two rollout units as a pointer to their existing exploration docs — and **Parked** closes it: four ideas left out, each with the reason.

---

## Notes

- Replace `<project>` and `<unit>` with real values before pasting.
- The onboarding prompt should be the FIRST message in a fresh session. Don't pre-load other context.
- **Session hygiene (the Owner's side):** `/rename` each unit session to the name the project hook's **Naming** section defines, right after firing the prompt, so `--resume` finds it. One unit per session; once the wrap-up is integrated into `main`, the session is done. If a session bloats mid-unit, `/compact` with instructions to preserve branch names, the current step, changed files, and verification commands — never compact just to roll into the next unit.
- For a project with no designs, no prior discussion, or no tracker, write `N/A` rather than omitting the line — it signals "I checked and there isn't one" vs. "I forgot to provide this."
- Sub-agents inherit the Owner's always-on rules automatically, when the machine has them; the onboarding prompt mentions them explicitly only as a reading-order signal.
