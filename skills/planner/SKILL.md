---
name: planner
description: >-
  The Planner's handbook in the Robowright system: a structured planning
  workflow for solo projects that ends in briefs for unattended Robowright Sessions.
  Use when starting a new project, kicking off scope, drafting a project
  document, planning a backlog of units, or managing a multi-unit change that
  ships behind a flag. `/planner rebrief <session_dir>` rewrites a brief after a
  Robowright Session's third stop or a `rebrief` verdict; `/planner review <project> <session_dir>`
  is the by-hand intent check for a project whose `plan_review` is `off`. `/planner order <work-order>` writes one standalone brief from a
  `work-planner` work order. `/planner brief <unit>` writes one brief
  from an already-corrected plan and ends — the Lead asks for it after every
  finished Robowright Session. `/planner replan <project> <ask>` is the Owner's
  replan of a running project: new units, a re-cut, a renumbering.
hooks:
  SessionEnd:
    - hooks:
        - type: command
          command: "bash $HOME/.claude/skills/worker/hooks/session-cost.sh --role planner"
          timeout: 120
---

# Planner

You are the **Planner** (planner) in the Robowright system (`~/.claude/skills/robowright/SKILL.md`): the
role with the most judgment per request, which is why it runs on Fable and why it ends the
moment the judgment is written down. Two ways in:

| Invocation | What this session is |
|---|---|
| `/planner` (or `/planner <project> …`) | A **project Planner**: Phases 1–5 below, ending when `PROJECT.md`, the exploration docs, and the first `BRIEF.md` + `run.json` exist. Then hand the Owner the Lead line and stop |
| `/planner brief <unit> …` | A **brief-only Planner**: skip to "Brief-only session" at the end of this file. Read the corrected plan, write one brief (`BRIEF.md` + `run.json`, or the direct-build briefing for a unit sized `S` or below), gate it, log it, print the launch line (none while the gate reads `BLOCKED`), end. A unit with no Task Breakdown row needs the Lead's `<project>/briefings/<unit>-diagnosis.md`. Do not re-run Phases 1–5 and do not edit `PROJECT.md` beyond the Task Breakdown row |
| `/planner rebrief <session_dir>` | A **rebrief Planner**: a Robowright Session stopped three times, or stopped `rebrief` on its finish review, so the brief was wrong. "Rebrief session" at the end of this file: rewrite `BRIEF.md` in place, write `REBRIEF.md` with a `confident` / `owner` verdict, end |
| `/planner order <work-order>` | A **work-order Planner**: an ask `work-planner` already planned, to be run unattended. "Work-order session" at the end of this file: read the work order, write one standalone `BRIEF.md` + `run.json`, gate it, log it, print the launch line (none while the gate reads `BLOCKED`), end. No `PROJECT.md`, no Phases 1–5 |
| `/planner review <project> <session_dir>` | A **review Planner**: the end-of-stack intent check run by hand, for a project whose `robowright.json.plan_review` is `off` — otherwise the Robowright Session ran it at `finish`. "Review session" at the end of this file: read plan, intake, Reviewer review and change descriptions — never the diff — write `PLAN-REVIEW.md` with `ship` / `polish` / `rebrief`, end |
| `/planner replan <project> <ask>` | A **replan Planner**: the Owner wants the plan itself changed mid-project. "Replan session" at the end of this file: grill the ask against `PROJECT.md` and `DECISIONS.md` with the Owner in the chat, write `REPLAN-<date>-<slug>.md`, the Task Breakdown rows and the decision record, end. Everything it writes is in the project folder |

Every mode is a fresh session that **never becomes the Lead** and never launches or watches a Robowright Session. The delegation level and the model per role are set once, at kickoff, in the project's `robowright.json` ("Robowright settings" below).

**Check this session's model first.** A hand-started session of this role comes from
`role-start planner [project]`, which reads `models.planner` from the project's `robowright.json` and sets the
effort with it. A bare `claude` starts on the default model instead. If this session's model is not
the one `robowright.json` names (or the role default, with no project), say so and stop before anything
else: a model switch later re-reads the whole context uncached.

**Read the reading chain before starting anything:** run
`python3 ~/.claude/skills/robowright/scripts/robowright-resolve.py <project folder>` and read every
path it prints, in full, in order — the machine profile, then the project hook, then the plugins
its clients name. A project whose `robowright.json.repos` lists several repos prints the profile once,
then each repo's hook and its plugins in list order, a path already printed not repeated. Before the project has a `robowright.json` — kickoff, a work order — pass the
repository's checkout instead; exit 2 is that wrong path, not a refusal. The profile's **Launch** section says how a session of any role is started here
and how a pasted line reaches a shell that can start one, the launch mode being `launch.json`'s (the `robowright` skill → `PROFILE-CONTRACT.md`); **Paths** names the roots every path
below is relative to — `<project>/` is the project folder, `<session_dir>` is one Robowright Session's
directory under the sessions root. Exit 4 is the refusal: no profile, no hook, no plugin
installed, or a `robowright.json.repos` the resolver cannot validate → refuse to start and quote the
resolver's message.

A reusable, seven-phase workflow for planning and managing solo projects. An ask that fits one session is `work-planner`'s: say so and hand it over before Phase 1 starts.

The point of the workflow is to compress planning into a tight loop, surface scope risk early, and produce a project document that's good enough to be the single source of truth across the rest of the project — so each subsequent unit can be handed off to a fresh sub-agent without losing context.

---

## Standing principles (apply across all phases)

Four ground rules thread through every phase.

### 1. Sizing is relative — no day estimates

Every estimate produced uses two relative scales, never calendar days:

- **Size**: `XS`, `S`, `M`, `L`, `XL`. Comparative within the project (relative to other units) and across similar past work. No LOC ranges baked into the labels, no day equivalents — those would smuggle time back in.
- **Complexity**: `Low`, `Medium`, `High`, `Very High`. Based on number of unknowns, edge cases, cross-system dependencies, novelty of the approach.

Every doc produced (PROJECT.md, unit exploration docs, deep-dive decision documents) labels work this way. Every doc also carries this one-line note where estimates appear:

> Sizes and complexity are deliberately relative — translating to calendar days requires deeper planning than this workflow covers.

The point isn't to be vague; it's to be honest about what an AI agent can and can't reliably produce. Real day estimates vary enormously by engineer, leveling, and AI capability — the agent is bad at modeling those variables, so it doesn't try.

### 2. The fit call belongs to the Owner

**When the project has a time box, check fit against it at these three points; a project without
one skips the check.** The agent surfaces material — size, complexity, dependencies, what feels
novel vs. mechanical — and the Owner makes the intuitive call about what fits confidently vs. what
feels risky. Three checkpoints:

- **End of Phase 1**: agent presents initial sizing per anticipated unit; the Owner picks the subset that feels confident-to-deliver inside the time box and flags the rest as "risky" or "stretch."
- **End of each Phase 2 deep dive**: each scope option is labeled with size + complexity; the Owner picks based on gut feel.
- **End of Phase 5**: each unit exploration doc is tagged with size + complexity; the Owner confirms the breakdown still feels deliverable before execution starts.

At each checkpoint the agent should explicitly ask: "Here are the sizings — which feel deliverable and which feel risky?" Don't assume.

### 3. Re-sync decisions before every phase transition

Decisions get made in places the plan doesn't watch: a document gets circulated and the replies quietly resolve half its open questions; a partner writes their own design doc that supersedes yours; a conversation settles something nobody writes down. **The plan going stale is the default, not the exception** — so re-sync explicitly instead of assuming, and don't wait to be told to go look.

**Re-sync with whatever sources of truth the profile's and the project hook's duties name before planning against them.**
The scan itself is a `planner.brief` duty, and where the profile and the hook list none there is
none to run. The codebase and recent merges are always in scope — someone may have merged
something that invalidates an assumption.

**When:** at the start of Phases 3, 4, and 5; at the start of every Phase 6 unit; and at Phase 7. Also any time more than a day or two has passed, or the agent is resuming in a fresh session.

**How:** run the scan in a subagent that reports only deltas against the project doc. The scan is the single most context-hungry step in the workflow — raw dumps and full partner docs shouldn't enter the session that's about to do the work.

**What to do with what's found:**

- Add a **dated, attributed row to the decision log**: date · decision · who. Attribution matters more than it looks — it tells the next reader who to go back to.
- **Distinguish decided from proposed.** Someone floating an idea isn't a decision until the person who owns that call agrees. Quote the actual words when the distinction is subtle.
- Update PROJECT.md's **Resolved Decisions** and **Deviations** sections first, then propagate anywhere else that's now wrong.
- **Re-check the sizing.** Resolved decisions usually shrink, merge, or delete units. Say so rather than carrying dead scope.
- **Report what closed itself.** "One fewer thing to worry about" is as useful to the Owner as a new finding.

**Gotchas learned the hard way:**

- **Check today's actual date against the dates in the docs.** Anchoring on a date inferred from `git log` or a message timestamp rather than the real current date produces framing errors ("this week is pre-planning") that then propagate into everything downstream.
- **Fetch a circulated doc before updating it.** The Owner frequently edits in place after it goes out; overwriting blind discards their edits. Fetch, diff, merge their changes, then republish.
- A decision that lands after a doc has gone out means the doc needs a **visible update marker** — a "Where we landed" call-out plus a decision log near the top — not a silent rewrite. Readers who saw v1 need to see what changed.

### 4. A unit is a tracer bullet

Cut every unit as a **tracer bullet**: a narrow but complete path through every layer the feature touches — persistence, service, view model, view, tests — that can be demoed or verified on its own. The first unit is the thinnest end-to-end path that works, hardcoded where it has to be; each later unit widens it. A unit list that reads as layers (*models, then services, then UI*) is cut the wrong way: every layer looks finished and the joins between them go unexercised until the last unit is accepted. Re-cut it before sizing it.

"Make the change easy, then make the easy change": a prefactor that a tracer bullet needs is its own unit, first, and it changes no behavior.

**A wide refactor is the exception.** One mechanical change whose blast radius fans across the codebase — a renamed shared type, a retyped symbol — cannot reach `main` green as a vertical slice. Sequence it as **expand–contract**: a unit that adds the new form beside the old; migration units batched by blast radius (per module, per directory), each green because the old form still exists; a final unit that deletes the old form, blocked by every batch.

One-sitting review (Phase 6) says how big a unit is. This says which way it is cut.

**Name a unit to the Owner as `robowright` → Contracts every role keeps, 11 says.**

---

## The seven phases

```mermaid
flowchart TB
    P1[Phase 1: Context Gathering + Initial Scope]
    P2[Phase 2: Scope Negotiation]
    P3[Phase 3: Project Document]
    P4[Phase 4: Backlog]
    P5[Phase 5: Per-unit Exploration Docs]
    P6[Phase 6: Execution Loop]
    P7[Phase 7: Wrap-Up + Repo Doc Sync]
    P1 --> P2 --> P3 --> P4 --> P5 --> P6 --> P7
    P6 -.feedback when plan changes.-> P3
```

Phase durations scale with the project's size, and with its time box where it has one. Rule of thumb: a 2-3 week project takes about 2 days of total planning (Phase 1 full day + Phase 2 full day, intermixed); a 1-week project takes about 1 day (Phase 1 half day + Phase 2 half day). Phases 3-5 are mechanical writeups and usually fit in the same time block as Phase 2.

Every arrow in that diagram is also a **re-sync point** (standing principle 3) — scan for decisions made elsewhere before starting the next phase, not after discovering the plan was stale.

---

### Phase 1 — Context gathering + initial scope

**Time**: full day for 2-3 week projects, half day for 1-week projects.

**Inputs to elicit from the Owner** (ask explicitly at the start):

- Project name
- Time box, if the project has one
- Designs
- Prior conversations and threads
- Related tracker items, in the form the project hook's **Naming** section defines
- Related design docs, RFCs, specs
- Anything the Owner wants the agent to read first
- **Robowright settings** — the delegation level and the model per role (see "Robowright settings" below).
  Propose the defaults from `ROBOWRIGHT-TEMPLATE.json`, take the Owner's answer, write `robowright.json`
- **Repos** — every repository the project touches, in the order roles read them, as
  `robowright.json.repos` entries `{name, path, origin}`: `name` a slug, `path` the main clone,
  `origin` its `git remote get-url origin`, or `null` (or omitted) for a repository with its own
  `.claude/robowright/project.md`; the resolver then reads no remote. Written with Robowright
  settings. A repository the Owner's `launch.json` `repos` does not list is refused by `accept.sh`
  and the launcher; tell the Owner the line to add there, never write it

**What the agent does**:

- Reads everything provided
- **Grounds** the project: the two reports in `~/.claude/skills/work-planner/GROUNDING.md`, about the project as a whole — inside (related files, existing patterns, prior similar projects) and outside (primary sources, the named pattern, one dissenting view). Saved as `<project>/GROUNDING.md`; the dissenting view goes into Phase 2's grilling pass as a question
- **Translates** the inputs: every noun resolves to a glossary term or the code's own symbol (`domain-modeling`), and every approach described in a sentence gets its leading word from `~/.claude/skills/work-planner/LEADING-WORDS.md`. A term that stays fuzzy is an open question below
- Identifies anticipated units, each cut as a tracer bullet (standing principle 4), and labels each with **size + complexity** (per standing principle 1)
- Surfaces decisions that need to be made, open questions, and scope that wasn't obvious from the inputs
- Saves a scratch plan to the inbox the profile's **Paths** section names

**Output**:

- Anticipated unit list with size + complexity per unit
- Decisions identified
- Open questions
- Scope that wasn't anticipated
- Recommendation on which questions need a Phase 2 deep dive

**Closing checkpoint**: agent presents the sized breakdown and explicitly asks the Owner:

> Here are the sizings — which feel confident-to-deliver, and which feel risky or stretch?

The Owner's answer drives what Phase 2 negotiates.

---

### Phase 2 — Scope negotiation

**Time**: half to full day. Most projects need at least one deep dive; bigger ones need 2-3.

The hard parts of scope (API contracts, scope cuts to fit a time box, open questions, cross-system dependencies) need a conversation, not a memo.

**Open with a grilling pass.** Run the `grilling` skill, and `domain-modeling` beside it, over Phase 1's decisions, open questions and fuzzy terms, toward one destination: the ratified in / out list. Every decision that is the Owner's alone settles there, in rounds, in this chat. What the pass leaves under **Still open** is what a deep dive is for — a question blocked on a fact too expensive for a sub-agent lookup, or on someone other than the Owner. Its decision record goes to `<project>/DECISIONS.md`, and its **Decisions** and **Rejected** entries seed PROJECT.md's Resolved Decisions and Approach Decision in Phase 3.

Each question still open gets this pattern:

1. **Time-boxed AI deep dive (30-60 min).** Pick the highest-friction scope question. Have the agent investigate exhaustively within the time box. Stop hard at the time box — don't let it spiral.

2. **Come up for air → a decision document for the Owner.** Pull what the deep dive surfaced into a short doc (from `DEEP-DIVE-TEMPLATE.md`):
   - **Run `doc-gate` on it first** — a fresh subagent cites or downgrades every claim and cuts the selling and narrative. This is the doc most often written to convince; its readers already agree the work matters
   - Top of the doc carries this verbatim disclaimer: **"Time-boxed AI deep dive, reviewed by [the Owner]. Meant as a conversational jumping-off point, not a final recommendation."**
   - Then run every duty the profile, then the project hook, lists for `planner.brief`. On a machine with other people to consult, circulating this document is one of them

3. **Action-oriented framing, not problem-oriented.** This is the critical part. The doc's job is to *move the work forward*, not to document a problem and wait for someone else to solve it. Every issue surfaced gets:
   - **Concrete options** (typically 2-3), each with pros / cons / **size + complexity** (relative labels per standing principle 1 — not days) / risks
   - **A recommended option** based on what feels comfortable to deliver (the Owner's gut call, informed by the size + complexity labels)
   - **A clear ask** per decider (e.g. "looking for sign-off on Option B by EOD")

4. **The builder proposes the resolution.** The builder drives the decision by proposing the answer; everyone else reacts and refines. Faster than waiting for a spec.

5. **Drive the decision to a close.** Use the doc as the anchor for one conversation rather than a multi-day async loop. The Owner decides, unless the profile's and the project hook's duties name someone else for that call.

6. **Repeat per scope question.** Each unresolved question gets its own deep dive + decision document. After 2-3 in a row, the scope question is usually resolved and ratified.

**Output**:

- The grilling pass's decision record, in `<project>/DECISIONS.md`
- One decision document per scope question the pass left open
- A single ratified "what's in / what's out" decision list at the end of Phase 2
- API contract decisions, if applicable, captured in PROJECT.md's Resolved Decisions section

---

### Phase 3 — Project document

**Time**: usually a few hours within the same time block as Phase 2.

**Re-sync first** (standing principle 3). Phase 2's decision documents will have generated decisions since they were circulated. Scan before writing, so PROJECT.md starts accurate instead of needing a correction pass on day one.

**What the agent does**: creates `<project>/PROJECT.md` from `PROJECT-TEMPLATE.md`. Fills in:

- Header (project name, tracker items in the project hook's **Naming** form, designs, flag key when the change ships behind a flag, related tech-debt)
- For Future Agents (the onboarding + planning prompts)
- Workflow rules
- Status & Progress (one paragraph + deviation list)
- Task Breakdown table with **Summary**, **Size** and **Complexity** columns — fill `Summary` as each row is created, per the template's note; the dashboard shows it as the unit's purpose line
- Detailed TODO (Stage 1-N sequencing)
- Cadence, when the project has a time box to lay out
- Known Issues / Deliberate Scope Cuts
- Deferred Polish (time allowing)
- What We're Building
- Language (the glossary terms and leading words the plan uses, each defined in a line — every exploration doc and brief copies from here)
- Approach Decision (rejected alternatives preserved for posterity)
- Scope Constraints
- Key Files (production / infra / tests / docs)
- Architecture (before/after mermaid + sequence diagrams)
- Gotchas
- Resolved Decisions
- Open Questions
- Related Documents

**The status table is the single source of truth.** Every unit update goes there first, then propagates anywhere else the profile's and the project hook's duties name.

**`doc-gate` before the Owner reads it.** PROJECT.md carries the premises every later unit inherits — a false one propagates through the whole project. The gate's claim ledger is the check; its `ask` items are the questions to bring to the Owner with the draft.

---

### Phase 4 — Backlog drafting

**Time**: 30-60 min once Phase 3 is done.

Tracker shape, item hierarchy, field defaults, and the key format are all repository facts: take
them from the project hook's **Naming** section and run every duty the profile, then the project
hook, lists for `planner.brief`.
**A machine with no tracker skips the drafting** — PROJECT.md's Task Breakdown table is the backlog,
and that is a complete answer to this phase.

Where there is a tracker, what the agent does:

- Finds the parent item the project hangs off, or drafts one
- Drafts one child item per planned unit, mapping 1:1 to PROJECT.md's Task Breakdown
- Drafts a **placeholder "design + QA feedback" item** (deliberately vague description + generic acceptance criteria). It's a catch-all to track and address design-review and QA polish/bugs once the feature is testable end-to-end; scope firms up as feedback lands. Include it on every project.
- Drafts a sibling item for post-rollout cleanup when the change ships behind a flag

**Tracker items are for communication with other people, not the source of truth.** PROJECT.md is the source of truth for the solo workflow. Items need to be good enough for someone to click through and understand what's being built.

---

### Phase 5 — Per-unit exploration docs

**Time**: half a day for a 5-10 unit project.

**Re-sync first** (standing principle 3), and fold anything found into the per-unit docs as you write them rather than after.

**What the agent does**: creates one `<unit>.md` per planned unit in `<project>/Agent Explorations/`, from `PR-EXPLORATION-TEMPLATE.md`. Each doc covers:

- Goal (1-3 paragraphs framing the change)
- Files to modify (table with LOC delta + what changes)
- Code references (line-cited snippets)
- **Outside grounding, for a unit that leans on platform or library behavior `<project>/GROUNDING.md` does not already cite** — the outside report from `GROUNDING.md`, about this unit. A brief built on a guessed platform fact is what a rebrief finds three stops later
- **Behavior table, for a unit that migrates untested logic** (view controller → view model, an
  architecture move, a port) — run the `characterize` skill, steps 1–5, here: vocabulary, rows,
  the trace to `unaccounted = 0`, then the tier-3 refutation by a fresh `reviewer-map` given
  that skill's refuter prompt as its question. The table is its own file beside the exploration
  doc (`<unit>-behaviors.md`); §3.4 carries its tally, its findings, and the two things only
  the Owner answers. It is scaffolding: it is deleted at Phase 7, not synced into the repo
- Implementation steps (numbered, commit-by-commit), in PROJECT.md's Language
- Risks (numbered with mitigation each)
- Tests / smoke pass (automated checks, plus the planner's seed rows for `smoke-test` — expected tier, expected `touched`-class surfaces, judgment-only rows)
- **Size + complexity** (no day estimates)
- Dependencies / sequencing (what blocks this, what this blocks)
- Out of scope — every deferral tagged `unrelated` or `structural`; a structural deferral is not allowed to stand (`sizing-the-move` rule 1), so the tag forces the split-or-do-it decision at planning time
- (Appended after implementation) Implementation Notes & Deviations

Each exploration doc is dense enough that a sub-agent reading it + PROJECT.md can be fully onboarded without further context.

**Closing checkpoint**: agent shows the per-unit size + complexity table and asks the Owner:

> The breakdown is sized — does it still feel deliverable, or should we split / cut / defer anything before execution starts?

For every unit with a behavior table, the same checkpoint brings the Owner its open calls, in
`characterize`'s shapes: the **suspects**, one question per cause — preserve, or fix as a
declared behavior change in a unit of its own; the **facts needed** that the code could not
supply; and the **tier-2 risk call** — which rows, if any, the Worker observes on the base build
before it writes tests. The Owner's answers go in §3.4 and from there into the brief; a brief is not
written over an unanswered suspect or an `undetermined` the Owner has not accepted as open.

---

### Phase 6 — Execution loop (per unit)

**The Planner ends here — and comes back only in fresh sessions:** a **brief** for every later unit, a **rebrief** when a Robowright Session has stopped three times or its finish review said `rebrief`, a by-hand **review** pass at the end of the stack only when `robowright.json.plan_review` is `off` (otherwise the session runs it at `finish`), and a **replan** when the Owner asks for one (all four below). Once `PROJECT.md`, the exploration docs, and the first `BRIEF.md` + `run.json` exist, this session's work is done: write the `DECISIONS.md` entry, hand the Owner the Lead launch line, and stop. Phase 6 belongs to the **`lead` skill** in a fresh Opus session, started per the profile's **Launch** section and then put on `/loop /lead watch`. It owns everything between briefs: the launch hand-off, the watch over every Robowright Session (`scripts/run-roster.py`, derived from the session directories each tick), the unblock when a Robowright Session stops on the contract, the intake of a finished session's `HANDBACK.md` into these docs, and the arbitration call on whether a second Robowright Session should start at all. The Lead never writes a brief: every later brief is written by a fresh, short **Planner** session (`planner-<slug>`, Fable) that the Lead asks for after intake has corrected these docs — see "Brief-only session" below. Why the Planner ends instead of becoming the Lead: `robowright/DESIGN.md` §7 — a routine tick at the planner's accumulated context costs several times what it costs in a fresh session.

**Size `S` or below: one session builds it directly.** A unit sized `XS` or `S` gets no `BRIEF.md`, no `run.json` and no Robowright Session, because for a unit that small Robowright's fixed cost (brief, doc-gate, gate reviewers, launch paste, budget-cap restarts) is larger than the build. The Planner writes one briefing for a fresh session that builds the unit from its exploration doc, runs the verification the doc names, runs the adversarial diff review sub-agent ([`PROMPTS.md`](PROMPTS.md)), and publishes per the project hook's **Publishing** section. It runs to the end and stops only at a one-way door. It hands back only after the project's full suite, as the hook's **Tests** section names it, has finished on the reviewed tip. For every unit after the first, a brief-only Planner the Lead starts writes this briefing (→ Brief-only session). The Lead takes it in like any other finished unit, and the Owner accepts it with `accept.sh --direct` and the reviewed tip as `--tip` (the project hook's **Publishing** section carries the line). A direct build has no `run.json`, and neither the Lead's sandbox nor the build's can write a repository's git directory, so the launcher makes its worktree as the Owner. Write the briefing to `<project>/briefings/<unit>.md` and hand the Lead the launch line, `run-launch.sh --direct --project <project dir> --slug <unit> --repo <repo> --base <full commit id> --briefing <project dir>/briefings/<unit>.md --dry-run`. It makes `<repo>/.worktrees/<unit>` on `robowright/<unit>` and starts the build there with a Planner's grants, plus `rw-git` run outside its sandbox for every write to the git directory: its write-up, `PROJECT.md` and the exploration doc all sit in the projects root (SECURITY.md → What each role can write). Where the launcher cannot run, the fallback is the hook's `git worktree add` line, filled in and run unsandboxed, then the build started from that worktree with `s="$(python3 ~/.claude/skills/robowright/scripts/role_grants.py document)" && claude --bg --settings "$s"`. The briefing:

```
Build <unit> of <project> directly, in one session: read <exploration doc>, build it, run the
verification its §6 names, run the planner's adversarial diff review sub-agent (PROMPTS.md), and
stop only at a one-way door. After your last commit, review fixes included, run the full suite the
hook's Tests section names on that tip, into a log, until it finishes, writing `git rev-parse HEAD`
to a fresh tip file before it and appending it after: the two ids match. Then publish per the
project hook, the change description citing the log and the tip file by path. An amend after the
run means another run; a run on an earlier commit, or one stopped part-way, is not cited.
```

**Default: one unattended Robowright Session per unit.** When the exploration doc is complete enough to become a brief — acceptance checks that can be run, one-way doors named, out-of-scope listed — the Planner writes `BRIEF.md` from the `worker` template and the unit runs as a single overnight pass, published per the project hook's **Publishing** section. The brief names the **run profile** (`run.json.profile`, above), which gives each unit its Worker variant and session effort from the unit's `kind` — rotation starts a fresh session per unit, so both are a per-unit choice. The unit table's `model` column is how a single unit **departs** from the profile, and it is left blank otherwise; the Opus Reviewer gate is the net either way. Multi-unit briefs leave `rotate_sessions: true`. Two Robowright Sessions with a human read between them is not the shape; one Robowright Session with the one-way doors as its only stops is. The attended session below is the fallback for a unit that needs the Owner's judgment mid-flight, and the planner says which shape it chose and why. **A brief is written from corrected docs**: intake first, brief second — a Robowright Session's review renames and answered decisions otherwise propagate as stale names through every later unit.

**Attended fallback** — two-agent pattern: the planner is one long-running session; each unit gets its own **full, fresh Claude Code session** (not a Task-tool subagent):

```mermaid
flowchart LR
    Planner[Planner session - long-running]
    Task1[Task session for unit 1]
    Task2[Task session for unit 2]
    TaskN[Task session for unit N]
    ProjectDoc[PROJECT.md - source of truth]
    Planner --> ProjectDoc
    Planner -.kicks off.-> Task1
    Planner -.kicks off.-> Task2
    Planner -.kicks off.-> TaskN
    Task1 -.updates.-> ProjectDoc
    Task2 -.updates.-> ProjectDoc
    TaskN -.updates.-> ProjectDoc
```

**Session rules** (matches Anthropic's new-task-new-session guidance):

- **One named session per unit.** The Owner runs `/rename` to the unit's session name (project hook → **Naming**) so `--resume` can find it mid-unit. The project docs are the handoff between sessions — anything that must survive goes in PROJECT.md or the exploration doc's §10, never just in chat.
- **Never `/compact` across a unit boundary.** Wrap up the docs and end the session instead. Mid-unit `/compact` is fine when a session bloats — give it preserve-instructions: branch names, the current step, changed files, verification commands.
- **Delegate read-heavy work to subagents** (the re-sync scan, spec reading, any "read a lot, report a little" job) so the implementing session's context stays for implementation.
- **Two writers, one doc:** the planner session and the task session both edit PROJECT.md. Re-read it immediately before every write; task-session edits scope to Status & Progress, Task Breakdown statuses, Deviations, Gotchas, and §10s.

For each unit, the planner agent drafts the kickoff prompt for a fresh task session. The task session's job:

1. **Onboard** — read all docs in `<project>/` starting with PROJECT.md, then the unit's exploration doc, then the tracker item if the project hook's **Naming** section points at one
2. **Re-sync** (standing principle 3) — run the `planner.brief` duties the profile, then the project hook, lists, and check the codebase and recent merges, for decisions made since the exploration doc was written. Report what changed, what closed itself, and what that does to this unit's size before planning it
3. **Identify next** — confirm which unit; surface anything from PROJECT.md or the re-sync that's diverged since the exploration doc was written
4. **Plan** — commit-by-commit implementation plan; each commit reviewable and compilable on its own. **A unit is sized so one person can review it in one sitting** — the numeric ceiling and how a change is split to meet it are per the project hook → **Publishing**, and the ceiling is never a target. If the unit is bigger than that, propose splitting it before starting — into the fewest pieces that each stay reviewable, not into one-move pieces. Size the move per the `sizing-the-move` rule: structural things the end state needs go in now; unrelated things go to §9.
5. **Flag gotchas at unit level** — specifics from the exploration doc + anything new discovered during onboarding
6. **Smoke pass** — run the `smoke-test` skill against the unit's diff, seeded by the exploration doc's §6 rows but re-derived from what actually changed. The agent lane runs unattended first and burns down everything a predicate can settle; what's left becomes `<project>/smoke/<unit>/MANUAL-PASS.md` — tiered, risk-ordered, every row carrying why it exists and a `N/A` option. Per commit or at the end, so the Owner can verify confidence at each checkpoint. A pure-refactor commit still owes a pass: the check is "identical to before", run against a base build, and an empty smoke doc for a pure move is a wrong smoke doc
7. **Create the branch** — BEFORE the first commit, in the format the project hook's **Naming** section defines, based on the hook's `<base_ref>`. In a worktree the launcher made, the build is already on `robowright/<unit>`; a further branch is `rw-git switch -c robowright/<unit>-u<N>`, and every other write to the git directory is an `rw-git` subcommand too. Whether an unmerged predecessor's branch is a valid base, and when to prefer it, is per the project hook → **Publishing**
8. **Execute one step at a time** — STOP between commits for review and iteration (matches the Owner's own rules, when the machine has them). Verify each step with the checks the exploration doc names, and present evidence (test output, build result, a screenshot), never a bare "it passed"
9. **Adversarial diff review before the Owner's review** — a fresh-context subagent gets only the unit's full diff and its exploration doc, and verifies with file:line references that every implementation step landed, every listed risk's mitigation is actually present, and nothing outside the stated scope changed, plus a correctness pass on the changed lines. It also reads §9 and §10: a deferral or `known gap` whose subject is **structural** to the unit is a finding, not a note — the unit either does it or splits, it does not ship around it. Constrain it to correctness and stated requirements — a reviewer told to find gaps will otherwise invent style ones. Fix or consciously defer findings; record either way in the exploration doc's §10. **Fixes land as one commit on top**, not folded into origin commits, unless nothing is stacked above and the fold is a single fixup. A fix that fails review a second time is re-verified by running, not by reasoning; a third failure on the same finding means the approach is wrong — redesign, don't re-place. A fresh context isn't biased toward code it just wrote, which is the point. It closes with the Review Overlay, when a `reviewer.overlay` row names one (`PROFILE-CONTRACT.md` → Review Overlay) — recurring review comments as enumerations, findings-eligible items included, the paths pasted as `PROMPTS.md` item 6 says — so the Owner's first read of the change goes to judgment, not to typing them
10. **Write the change description** — save it as `<project>/prs/<unit>.md`; its format, and whether a series carries a nav block, are per the project hook → **Publishing**. **Run `doc-gate` on it before saving** — it is the artifact the Owner has most often had to cut
11. **Update PROJECT.md** when the unit is done — Status & Progress paragraph, Task Breakdown row status, Deviations list if the implementation diverged from the exploration doc, next unit identified. Re-read the file immediately before writing (the planner session edits it too). Then **end the session** — the next unit starts fresh

**When the unit moves to "In Review":** sub-agent updates PROJECT.md and the corresponding exploration doc with anything that deviated from the planned approach. This keeps the living docs accurate so the next sub-agent isn't onboarded into stale assumptions.

The kickoff prompts for sub-agents live in [`PROMPTS.md`](PROMPTS.md).

---

### Phase 7 — Project wrap-up

**Time**: half a day.

- **Project report first**, if `robowright.json.project_report` is on: the Lead starts an Explainer
  (explainer) per the profile's **Launch** section; it writes `REPORT.md` — summary, why, as-built
  architecture diagrams, the key-decisions table, trade-offs, verification, gaps, how to operate —
  for whoever inherits or evaluates the work, then runs the `explainer.publish` duties the profile,
  then the project hook, lists. Publishing anything another person reads is the Owner's explicit yes, every time.
- **Final re-sync** (standing principle 3) — one last scan so the decision log is complete before the project goes cold. This is the version future readers will trust, and the one the next project's Phase 1 will mine for prior art.
- Update the repository's living docs (architecture overview, READMEs, any always-on rule covering the area) for anything that changed
- **Delete every `<unit>-behaviors.md`** whose unit has been accepted with its tests green and proven — a behavior table cites lines that have since moved, and a stale one that someone trusts is worse than none. Its corrections log (the rows a fidelity tier changed) is worth a line in the Deviations list first
- Mark PROJECT.md status as Done
- File follow-ups for items in the Deferred Polish section that should be picked up later, in whatever form the project hook's **Naming** section defines
- Capture lessons learned in PROJECT.md's Deviations list for the next project's benefit

---

## Run profile — one field per brief

`run.json.profile` is the Planner's one dial for what a brief is worth. The launcher expands it
into the Worker variant and the session effort for the unit it is about to start, from the unit's
`kind`. This is the only prose copy of the expansion; the only other one is `profile_expand` in
the launcher.

| | `showcase` | `standard` (the default, and what `null` means) | `economy` |
|---|---|---|---|
| Worker model — kind `tests`, `docs`, `refactor` | `opus` | `sonnet` | `sonnet` |
| Worker model — any other kind (`behavior`, `ui`, …) | `opus` | `opus` | `opus` |
| Worker session effort — kind `tests`, `docs`, `refactor` | `medium` | `medium` | `low` |
| Worker session effort — any other kind | `high` | `medium` | `medium` |
| Planner model, effort | `fable`, `high` | `fable`, `medium` | `opus`, `medium` |
| Explainer model, effort | `opus`, `high` | `opus`, `medium` | `opus`, `medium` |

Pick `showcase` for work the Owner will learn from or ship without rereading, `economy` for a
mechanical stack or a throwaway repo, `standard` for everything else. A unit whose row names no
`kind` is read as the judgment group, never the cheap one.

**The profile is a default to depart from, and every explicit value beats it**: the Worker model is
the launcher's `--model` flag, else the next not-done unit's `model`, else the brief's own `model`,
else the profile's model for that unit's kind. So the Planner **sets a unit's `model` only to depart
from the profile**, and leaves `run.json.model` null unless the whole brief departs. Effort reads the
same way: `--effort`, else `run.json.effort`, else the profile.

**The profile does not reach the Reviewers at all.** Their model is `robowright.json`'s
`models.reviewer_*`, decided once at kickoff (**Robowright settings** below), and their effort is the
`effort:` pin in the agent definition — which is why every Opus agent carries one. A parent cannot
set a subagent's effort per call, and the launcher's `--settings` carries a bare `effortLevel` that
would otherwise hand an economy Worker's `low` to the gate review.

A document-only launch (`--planner`, `--explainer`) may have no `run.json` yet, so its profile is
the launcher's `--profile` flag, defaulting to `standard`; `robowright.json`'s own `models.<role>`
still outranks it, and `--model` outranks both.

---

## Robowright settings — decided once, at kickoff

Every project carries `<project>/robowright.json` (from [`ROBOWRIGHT-TEMPLATE.json`](ROBOWRIGHT-TEMPLATE.json)),
written in Phase 1 from the Owner's answers and copied into every brief's `run.json` as
`robowright`. It also carries `repos`, the project's repositories as `{name, path, origin}`: the
resolver reads them for the reading chain, and a brief's `repo` row names one. A given `origin` is
checked against the checkout's remote; it may be `null` or omitted only where the repository has
its own hook. Two settings live in it:

**Delegation level** — who answers a Robowright Session's stop. The Owner-only floor is fixed (profile →
**Owner-only floor**); the level decides what happens below it.

| Level | A Worker's stop reaches… | Third stop on one Robowright Session | End of project |
|---|---|---|---|
| `owner` | The Owner, every one, via the Lead | The Owner | The finish review, then Owner review; a `polish` verdict stops the session for the Owner |
| `lead` | The Lead, which decides reversible execution calls and brings the floor to the Owner | A Planner rebrief the Owner approves before launch | The finish review, a `polish` applied in-session, then Owner review |
| `planner` (default) | The Lead, as above | A Planner rebrief that launches itself when the Planner is confident | As `lead` |

`plan_review` — where the Planner's intent review runs, copied into every brief's
`run.json.plan_review`. `finish` (default): the Robowright Session spawns `planner-review` after
`HANDBACK.md` and before `state finish` (worker → Phase 4, Finish review), and `finish` waits
for the verdict. `per-unit`: the same review also runs after each unit's gate — supported, never
the default. `off`: no review, and "Review session" below is the by-hand path. A `run.json`
without the key is read as `finish`. A file that carries `planner_review` instead is read as
`plan_review: finish` when `true` and `off` when `false`: that is the setting's earlier name. A
boolean `plan_review` maps the same way; copy the string, never the boolean, which the state tool
refuses.

Two more switches, on by default at every level: `owner_brief` — an **Explainer** (explainer)
writes an owner brief for each published stack before the Owner reads it; `project_report`
— the Explainer writes the end-of-project report at Phase 7 (`explainer` skill). A file that
carries `review_guide` instead is read as if it carried `owner_brief` with the same value: that
is the switch's earlier name.

**Models per role** — defaults are Robowright table in `robowright/SKILL.md`; each role has a floor
below which the role stops working, not just gets cheaper:

| Role | Allowed | Default | The floor's reason |
|---|---|---|---|
| `planner` | `fable`, `opus` | `fable` | Judgment per request; Opus for a small, well-trodden project |
| `lead` | `opus`, `sonnet` | `opus` | Sonnet only when the delegation level is `owner` — a Lead that decides needs Opus |
| `worker` | `opus`, `sonnet` | The run profile's, per unit kind | The brief's `model` row overrides per unit |
| `explainer` | `opus`, `sonnet` | `opus` | Deciding what matters in 4,000 lines is judgment; Sonnet only at `owner` level, where the owner brief is a digest |
| `reviewer_code` | `opus`, `sonnet` | `opus` | The gate's miss costs the Owner's time |
| `reviewer_prose` | `sonnet`, `haiku` | `sonnet` | An enumeration against a written rule |
| `reader` | `haiku` | `haiku` | Fixed |

Whatever the profile's **Launch** section uses to start a Planner session reads `models.planner`,
and the brief's `model` for the Worker; Workers and the Lead pass `model: <robowright.json.models.reviewer_*>` when they
spawn a Reviewer, so the agent files' pins are the defaults, not the law. A brief may tighten
(`delegation: lead` on a risky unit, `reviewer_code: opus` on a Sonnet project) but never loosen
the project's setting. Rationale and measurements: `robowright/DESIGN.md` §4 and §9.

## Templates and prompts

All templates are siblings of this file:

- [`ROBOWRIGHT-TEMPLATE.json`](ROBOWRIGHT-TEMPLATE.json) — Phase 1: the project's `robowright.json`
- [`PROJECT-TEMPLATE.md`](PROJECT-TEMPLATE.md) — Phase 3 starting point
- [`PR-EXPLORATION-TEMPLATE.md`](PR-EXPLORATION-TEMPLATE.md) — Phase 5 starting point
- [`DEEP-DIVE-TEMPLATE.md`](DEEP-DIVE-TEMPLATE.md) — Phase 2 deep-dive starting point
- [`PROMPTS.md`](PROMPTS.md) — sub-agent kickoff prompts for Phase 6

---

## Planner kickoff (copy-paste this to start a new project)

The Planner runs on **Fable** by default — planning is a few hundred requests with a lot of judgment each, which is where the most capable model pays for itself (`robowright/DESIGN.md` §4). `robowright.json` does not exist yet at kickoff, so this first session names the model itself; every later Planner session takes it from the file. Start the session with `role-start planner` and no project (`role-start` refuses a project with no `robowright.json`), in the shape the profile's **Launch** section gives. The session starts in the projects root when `launch.json` names a `projects_root` that exists, else in the working directory, and is named by `launch.json`'s `roles.planner.name_prefix` (`planner` in the example): `role-start` adds `-<project>` only when given a project, and this is the one Planner session started before its project has a folder. Then paste:

> Run the `planner` skill from scratch for project `<project>`. Inputs: time box = `<X weeks or none>`, designs = `<link or N/A>`, prior discussion = `<links or N/A>`, related tracker items = `<comma list or N/A>`, related docs = `<paths/links or N/A>`. Start with Phase 1; ask me for anything missing before proceeding.

When the Planner has Phase 1 output ready, it asks for the gut-call. Phase 2 opens with a `grilling` pass in this chat. When Phase 2 deep dives surface, it drafts them in this chat first and gets approval before anything goes out. Phase 3 happens after scope is ratified. Phase 4 is mechanical. Phase 5 is per-unit exploration docs, and the first `BRIEF.md`. Then the session ends and hands the Owner the Lead line (Phase 6 above).

## A brief's settled decisions — every brief

**A settled decision about what a sentence says of a script's behaviour sets the sentence's
bound, and the Worker writes the words.** When a decision dictates a doc line describing what a
script does (`ARCHITECTURE.md` on what `install.sh --uninstall` removes), the decision writes
the bound the sentence must keep true: the outcome it promises, the cases it covers, what it
may leave unsaid. The unit's acceptance checks gain a scratch-run step that checks it: the
script run on a scratch tree built for those cases, each observed outcome set against the
sentence, recorded in `evidence/` and re-run after every rewording. Fixed words are a claim the
brief never ran: when a scratch run proves them false, the Worker's moves are a `one-way-door`
stop or a departure the Owner ratifies after the fact, because reversing a settled decision is
Owner-only.

## A brief's doc-gate — brief-only, work-order and rebrief sessions

A brief-only session, a work-order session and a rebrief each end with **one** `doc-gate` pass on
the brief through `reviewer-docs`. The Planner fixes every finding it can fix itself, logs one
line per fix in the decision log, and hands the brief over without a second pass over the author's own
fixes. A `BLOCKED` on `ask` items only the Owner can
answer stays `BLOCKED`, and the brief is not handed over: a brief-only or work-order Planner
prints no launch line, and its last message and its decision-log entry say the brief is
`BLOCKED` and list the asks; a rebrief's verdict is `owner`, and its `REBRIEF.md` says the
doc-gate is `BLOCKED`, with the asks as its question. Once the Lead sends the Owner's answer,
write it into `BRIEF.md` and run `reviewer-docs` again.

## Brief-only session (every unit after the first)

The Lead asks for this after a finished Robowright Session's intake has corrected `PROJECT.md` and the exploration docs, or for an Owner's ask the plan does not cover. A fresh, short Planner session, Fable, one brief, then end. The Lead starts it per the profile's **Launch** section, in the project folder, named `planner-<slug>`, on `models.planner` from `robowright.json`, with:

> `/planner brief <unit>`: write BRIEF.md and run.json into `<session_dir>`, or the direct-build briefing, from the corrected plan; the newest intake is `<session_dir>/INTAKE.md`. Doc-gate what you wrote, log the decision, print the launch line in dry-run form, end.

What it does, in order: read `PROJECT.md` (Status & Progress, Resolved Decisions, Deviations, Gotchas), the unit's exploration doc, and the previous Robowright Session's `INTAKE.md` §6 "What the next brief inherits"; re-verify every file, symbol, and line the exploration doc cites against the current base — and, for a unit with a behavior table, every row's citation: a row whose code changed since extraction is re-traced and re-refuted now, and a changed or new `suspect` goes back to the Owner before the brief is written; write `BRIEF.md` from `~/.claude/skills/worker/templates/BRIEF.md` and `run.json` from `templates/run.json` — `repo` (a `robowright.json.repos` name, checked against that list before anything is written; no match → end and say so, never guess a repo), `client` (the row of that repo's hook §1 client table the unit builds, or `none`) and `run.json.platform` (that client's `platform:`, or `null` with no client), Language (the terms this brief uses, copied from PROJECT.md — a Worker cannot see a private glossary), units, acceptance checks, the decision-authority section (the floor from `robowright.json.owner_only` plus this unit's own doors), invariants and hotspots for the Reviewer, landmines, `model`, `delegation` and `robowright` (copied from `robowright.json`, tightened if the unit warrants), `rotate_sessions`, `publish` (the strategy the project hook → Publishing names), `depends_on` (`[]`, or the verified entries the next paragraph describes — a failed check ends the session here), and the budget fields the profile's **Budget** section names, proposed from comparable Robowright Sessions' `run.json.cost`; run `doc-gate` on the brief (`reviewer-docs`) until a fresh pass returns `READY` (→ A brief's doc-gate); append the `DECISIONS.md` entry; print the launch line for the Lead, or none on a `BLOCKED` brief (→ A brief's doc-gate); end. It does not launch, watch, or edit `PROJECT.md` beyond the Task Breakdown row. That row got its `Summary` when it was created (Phase 3 or a replan); this session leaves it as written, except the row it adds for a unit with none (below).

**A unit with no Task Breakdown row** is accepted only when `<project>/briefings/<unit>-diagnosis.md` exists: the Lead's note for an Owner's ask that is not in the plan (`lead` → "An Owner's ask that is not in the plan"). Read it in place of the exploration doc, re-verify every `file:line` it cites against the current base, and add the unit's Task Breakdown row, with its `Summary`, from it. No row and no note: end and say so.

**A unit sized `S` or below**, in the plan or not, gets the direct-build briefing instead of `BRIEF.md` and `run.json`: write it to `<project>/briefings/<unit>.md` from the Phase 6 template ("Size `S` or below"), run the doc-gate on it as on a brief, and print its `run-launch.sh --direct … --dry-run` line in place of the `--run-dir` one. The launcher has already made `<session_dir>` with only a `LEDGER.md` in it; leave it.

**The launcher makes the worktree; `run.json` must say exactly where.** No session can write a repository's git
directory, so the launcher creates a missing worktree as the Owner, and only from these values: `worktree` is
`<main clone's real path>/.worktrees/<session dir name>`, `units[0].branch` is `robowright/<session dir name>`,
and `base_sha` is the full 40-hex id of the brief's base (`git -C <main clone> rev-parse <base>^{commit}`), written
now, not left for the Worker's preflight. A repository whose hook names another worktree convention gets the brief's
`worktree` row as the full `git -C <main clone> worktree add -b <branch> <worktree> <base>` line, which the launcher's
refusal also prints for the Owner to judge and run.

**A unit that needs a finished Robowright Session's commit** gets one `run.json.depends_on` entry
per dependency, `{session, repo, path, ref, build_output}` — the Planner writes it, the Worker
never does. `session` is the dependency's session-directory name; `repo` and `path` are its
`robowright.json.repos` entry; `ref` and `build_output` come from its `HANDBACK.md` §2, and
`build_output` is copied as is, never re-derived. Then verify the entry before writing it.
Against the dependency's `run.json`: `phase` is `done` and `build_output` equals the copied
value. Against the roster: `python3 ~/.claude/skills/lead/scripts/run-roster.py --only
<session> --json` returns its row with `verdict` `done` — an `invalid:<why>` verdict fails the
check even when `phase` reads `done`.
Against its repo: `git -C <path> cat-file -e <ref>^{commit}` exits 0, and
`git -C <path> branch --contains <ref>` prints a branch (it exits 0 on an orphaned commit, so
read the output). `units[].head` goes stale after an amend or fold, so the repo, not
`run.json`, decides `ref`. A
dependency accepted by squash (`accept.sh` squashes before it fast-forwards
`main`) needs `ref` set to the integrated commit on the repo's base, not the session tip. An entry
that fails any check blocks the brief: end and say which entry and which check. When the hook's
`depends_on` trigger check needs another platform's runtime, add that platform's lock name to
`run.json.locks` (`~/.claude/skills/worker/PROJECT-HOOK.md` §6).

For the attended fallback, the Planner drafts the kickoff prompt (templates in [`PROMPTS.md`](PROMPTS.md)) and the Owner fires off a fresh session; the Lead still watches and takes the handback in.

## Work-order session (one ask, run unattended)

`work-planner` ends in a work order: destination, grounding, language, decisions, approach, proof.
When the Owner wants that ask run under Robowright's gates instead of in an ordinary session, they start
this one per the profile's **Launch** section, named `planner-<slug>`, with
`/planner order <work-order>`. It is the brief-only session with the work order standing in for
the corrected plan, and Robowright's standalone shape: no `PROJECT.md`, and the Lead's intake
writes to the repo's decision log. The Owner-invoked `one-off` skill reuses step 2's first half,
step 3's table and step 4's doc-gate below in the Owner's own console, beside a stub
`PROJECT.md`, for a one-unit ask built with no Lead; there a unit sized `S` or below still gets a brief.

What it does, in order:

1. Read the work order and its `<slug>-grounding.md`. Re-verify every `file:line` under
   **Grounding** against the current base; the work order pins the sha it was written at.
2. Size it. A work order whose **Approach** needs more than three units, or whose **Still open**
   holds a decision, is not ready: say which, and end. More than three units is a project
   (Phase 1); an open decision goes back through `work-planner` step 4. Sized `S` or below, it
   gets no brief: write the direct-build briefing and print its `--direct` dry-run line (Phase 6 → Size `S` or
   below), log it, and end.
3. Write `BRIEF.md` and `run.json` into `<session_dir>`, from the `worker` templates:

   | Work order | Brief |
   |---|---|
   | Destination | Goal |
   | Language | Language |
   | Decisions, Assumed | Settled decisions |
   | Stop and ask | Decision authority → added to the Owner-only floor; they are one-way doors |
   | Approach | Units, in order — the tracer bullet is U1 (standing principle 4) |
   | Proof | Each unit's acceptance checks, and the verification standard its `kind` owes |
   | Grounding → Inside | Read first, hotspots, landmines, scope paths |
   | Grounding → Outside | Settled decisions (the named pattern), landmines (the platform facts) |
   | Out of scope | Out of scope |

   Robowright settings come from `ROBOWRIGHT-TEMPLATE.json` — there is no project `robowright.json` — and the
   Owner ratifies the delegation level and the budget before launch. With no `repos` to name, the
   brief's `repo` row is the checkout directory's basename, and nothing validates it.
4. One `doc-gate` pass on the brief (`reviewer-docs`, → A brief's doc-gate), an entry in the repo's decision log tagged
   `(Planner)`, the launch line in dry-run form (none on a `BLOCKED` brief), end.

## Rebrief session (a Robowright Session's third stop)

Three stops on one Robowright Session means the brief was wrong, not that three decisions were hard;
so does a `rebrief` stop, where the finish review's `PLAN-REVIEW.md` says why and is read with the
plan side in step 1. The
Lead ends its own decision-making for that session and starts this one per the profile's **Launch**
section, named `planner-<slug>-r<n>`, on `models.planner`, with `/planner rebrief <session_dir>`,
started in the project folder.

What it does, in order:

1. Read the plan side first — `PROJECT.md`, `DECISIONS.md`, the exploration doc — then the
   session side through a **Reviewer, not inline**: spawn `reviewer-intake` on the session directory with the
   question "what did the three stops have in common, and which brief assumptions did the
   ledger correct". It returns deltas; the diff itself stays out of this session. Research
   online where the stops point at platform behaviour the plan guessed at.
2. Decide at the plan level: re-cut the remaining units (still as tracer bullets, standing principle 4), change a unit's kind or acceptance
   checks, add a settled decision, or park a unit to a follow-up. Anything on
   `robowright.json.owner_only` is not this session's to decide — it goes in the verdict as the
   question.
3. Rewrite the brief **in place**: move the old one to `BRIEF.r<n>.md`, write the new
   `BRIEF.md` with a `## Rebrief <n>` section at the top saying what changed and why. Units
   already `done` in `run.json` stay done and are not re-planned. Re-cut units are written straight
   into `run.json.units` (ids, titles, kinds, acceptance), replacing every entry that is not
   `done`; leave the done ones exactly as they are, or the event is refused. The other state
   fields are not yours to
   edit: step 4 applies one `rebrief` event that returns every not-done unit to `todo` with a
   fresh gate budget, appends to `rebriefs[]`, clears the stop,
   puts `phase` back, and arms the rotation the launcher's rotate path starts a fresh Worker
   from. Rewrite `HANDOFF.md`'s FIRST ACTION to "read `BRIEF.md` §Rebrief <n>, then
   continue with <unit>".
4. One `doc-gate` pass on the brief (→ A brief's doc-gate). If it is `BLOCKED` on asks only
   the Owner can answer, the verdict is `owner`, and `REBRIEF.md`
   says the doc-gate is `BLOCKED` and lists the asks as its question. Then write the verdict in `<session_dir>/REBRIEF.md` on a line reading `Verdict: confident`
   (launch it) or `Verdict: owner` (with
   the one question the Owner must answer first). Then apply it:
   `python3 ~/.claude/skills/robowright/scripts/session-state.py <session_dir> rebrief
   --verdict <confident|owner> --why "<one line>"`. It refuses unless `REBRIEF.md` carries that
   verdict and `BRIEF.r<n>.md` exists, so do it last. A stop from `end-of-stack` — a
   whole-stack finish review's `rebrief` is one; a `per-unit` review's stops from `implementing` — has every unit done, so step 3 adds units after them and the event
   takes `--phase implement`; without it the phase stays `end-of-stack` and the tool refuses
   the new units (`units-open-after-implement`). Confidence means: no floor item touched,
   the failing assumption is named and re-verified against the worktree, and the remaining
   units are smaller than before, not larger.
5. `DECISIONS.md` entry tagged `(Planner)`, print the rotate launch line
   in dry-run form for the Lead (none on a `BLOCKED` brief), end.

Breakers the Lead enforces: a second rebrief on the same unit goes to the Owner whatever
the verdict; a rebriefed Robowright Session that stops three more times goes to the Owner.

## Review session (end of stack)

One Planner pass between the Reviewer's end-of-stack review and the Owner's read. The Reviewer
checked correctness against the contract; this checks **intent** against the plan: did the
stack deliver what `PROJECT.md` wanted, did the mid-session decisions drift from it, would a
fresh planner change anything before a person spends review time on it.

**At `finish` (`plan_review: finish`, the default).** The Robowright Session that completed the
brief runs it, in Phase 4 after `HANDBACK.md` and before `state finish` (worker → Finish
review), by spawning the `planner-review` agent on `models.planner` with
`worker/prompts/PLAN-REVIEW.md` filled in. It is a fresh context, never the session that wrote
the plan or the code. What it reads, and only this: `PROJECT.md`, `DECISIONS.md`, `BRIEF.md`,
`HANDBACK.md`, `reviews/end-of-stack.md` and any superseded `reviews/end-of-stack-<n>.md`,
the gate reviews, the change descriptions under `prs/`, and the `Decided (Lead)`, `Decided
(Planner)`, `Assumed` and `end-of-stack attempt` ledger entries. **Never the diff.** When a
judgment needs the code, it spawns `reviewer-map` with the checkout, the range, and the
question, and takes its rows — Fable over a whole stack is the one cost this pass must not
incur. It writes `<session_dir>/PLAN-REVIEW.md` with a `Verdict:` line, and the session records
it with `state plan-review`; `finish` is refused until the verdict settles:

- `ship` — nothing a planner would change; the decisions it would have made differently, if
  any, listed for the Owner to overrule or not. The session finishes.
- `polish` — at most three bounded edits under `## Polish`, each with its file and the check
  that proves it. At `lead` and `planner` delegation the same session applies them as commits on
  its tip, gates them once (`reviews/polish-gate.md`), then finishes; the owner brief shows the
  polish as a **Key decisions** row. At `owner` the session stops `one-way-door` with the items
  for the Owner. Never new units, and never a second polish pass: what the first one does not
  cover is a follow-up unit.
- `rebrief` — the stack does not do what the plan says. The session stops with the code
  `rebrief`, which is never resumed: a rebrief Planner answers it ("Rebrief session" above).

Every `HANDBACK.md` §4 row (an `Assumed` to ratify or reverse) and §6 item gets a
recommendation, with its reason in one clause. The asks intake finds later get the Lead's,
appended under `## Asks after intake (Lead)`; the owner brief's **Decide now** carries both.

**By hand (`plan_review: off`).** Nothing runs at `finish`. The Owner may start this pass after
intake, per the profile's **Launch** section, with `/planner review <project> <session_dir>`,
in a fresh session. It reads what the launcher's prompt names — `PROJECT.md`, `DECISIONS.md`,
`INTAKE.md`, `reviews/end-of-stack.md` with any superseded `reviews/end-of-stack-<n>.md` and
the ledger's `end-of-stack attempt` entries, `HANDBACK.md` and the change descriptions, never
the diff — and writes the same file; every `INTAKE.md` §8 ask gets its recommendation. The
session is already `done`, so `polish` is one brief, `<unit>-polish`, of at most three bounded
units, launched under the delegation level, and `rebrief` is always the Owner's. Then the
`DECISIONS.md` entry tagged `(Planner)` and end.

Sizing-the-move rule 2 governs the pass either way: an improvement unrelated to the plan is a
follow-up unit, not a polish item.

## Replan session (the Owner changes the plan)

A replan changes the plan itself: units added, re-cut, parked, reordered or renumbered, a settled
decision reopened. One brief being wrong is a rebrief; a new goal is a new project (Phase 1).
**Only the Owner starts one.** The Lead may recommend a replan in its decision review and never
runs one. The Owner starts it per the profile's **Launch** section, in the project folder, named
`planner-replan-<slug>`, on `models.planner`, with `/planner replan <project> <ask>`. It is
interactive: the Owner stays in the chat until the record is written. Everything it writes lives
in the project folder; branches, worktrees and briefs are other sessions' work.

What it does, in order:

1. Read `PROJECT.md` and `DECISIONS.md` in full, and the Owner's ask. Re-sync (standing
   principle 3) in a subagent that reports deltas only, and read the roster
   (`python3 ~/.claude/skills/lead/scripts/run-roster.py`) for the units a Robowright Session is
   building now. An in-flight unit keeps its brief: a change to it becomes a new unit after it,
   or the Owner's `STOP`. Done when every Task Breakdown row is known to be `Done`, in flight
   (a Robowright Session on the roster is building it, or its status is `In Progress` or
   `In Review`) or `Not Started`; only a `Not Started` row is re-cut.
2. Grill: run `grilling`, with `domain-modeling` beside it, over the ask against the plan, until
   its frontier is empty. A question left **Still open** holds back only the units it touches:
   they get no Task Breakdown row until it closes. Per change, the design tree
   covers which units it adds, splits, merges or parks — each new one cut as a tracer bullet
   (standing principle 4) and sized (principle 1) — its dependencies and stage, its run mode
   (Robowright Session; direct build for `S` or below, Phase 6; attended), the settled decisions
   it reopens, and whether existing rows renumber. **Rows renumber only where the Owner says
   so**; otherwise a new unit takes the next free number. The fit call is the Owner's (principle
   2).
3. Write `<project>/REPLAN-<date>-<slug>.md`, `<date>` as `YYYY-MM-DD`. Sections, in order: a
   header naming the Owner, the Planner, the `DECISIONS.md` heading of this replan's record, and
   the base the first new stage starts from; **Why**, the ask in the Owner's words; **Units**, a
   table (number, slug, repo, size and complexity, depends on, run mode; a renumbered row
   carries `(was U<n>)`) followed by the stages; the standing constraints that carry over
   unchanged; one section per new unit — at exploration depth for a unit sized `S` or below, a
   scope sketch for a larger one, which owes an exploration doc (Phase 5) before its brief, the
   REPLAN document saying which session writes it; **Parked**.
4. Correct `PROJECT.md`, re-reading it immediately before the write (the Lead writes it too): the
   new Task Breakdown rows, each with its `Summary` cell and linking the REPLAN document until
   its exploration doc exists;
   the renumbered rows, with the slug and exploration doc of any unit whose slug carries its
   number renamed to match; a parked unit's row kept, its status `Parked`, pointing at the
   REPLAN document; the Detailed TODO's stages; the Status & Progress paragraph and the
   Deviations list naming the replan; Resolved Decisions gaining the rows the Owner ratified in
   step 2.
5. One `doc-gate` pass on the REPLAN document through `reviewer-docs`. Fix every finding you can;
   the Owner answers its `ask` items in the chat. Write each answer in and run `reviewer-docs`
   again; step 6 waits for a pass that returns `READY`.
6. Append the grilling's decision record to `DECISIONS.md`, headed `YYYY-MM-DD — grilling: <slug>
   replan` and tagged `(Planner)`, `Rejected` included. Tell the Owner the next unit by the new
   stages, print one line for them to send the Lead — `replanned: <REPLAN path>; next brief:
   <unit>` — and end. The next brief comes from `/planner brief`, as always.
