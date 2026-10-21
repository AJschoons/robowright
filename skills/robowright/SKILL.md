---
name: robowright
description: The map of the multi-session engineering system — who the roles are (Planner the planner, Lead the lead, Worker the builder, Reviewer the reviewer, Reader the reader, Explainer the explainer, Owner the owner), which model each runs on and why, what each hands the next on disk, and the invariants every role keeps. Read when starting any session in the system, when deciding which role a task belongs to, when a new skill or agent is added to Robowright, or when the Owner asks how the system fits together. The role handbooks (planner, lead, worker) carry the procedures; this carries the design. `/robowright help [question]` answers any question about running, adapting or improving Robowright, from the manual and then the repo itself, read-only.
argument-hint: "[help [question]]"
---

# Robowright

*The Planner plans, the Lead leads, the Worker builds, the Reviewer reviews, the
Reader reads, the Explainer explains, the Owner decides.*

Invoked with `help`: follow `HELP.md` beside this file, which needs no machine profile, and read on here only where it says.

Robowright is the system that takes a unit of work or a project from "we should do this" to a
reviewed, published stack with nobody watching most of the way. It is seven roles, one shared
filesystem, and a small set of contracts between them. This file is the map; each role's
procedure lives in its own handbook, and this file never repeats a handbook.

**Status: settled with the Owner, landed, and made machine-agnostic.** The
handbooks carry the role names (`planner`, `lead`, `worker`), the Reviewer and Reader agent
files exist, and every fact that is true of one machine rather than of the system now sits
behind the machine profile. What is still owed is listed under "What this changes" at the end.

## The one design fact everything else follows from

A Robowright Session's cost is mostly *re-reading its own context* at cache-read price, not thinking
or writing (`DESIGN.md` §1). So the system is shaped to
keep every session's context small and short-lived, and to put the expensive model only where a
request carries real judgment:

- **State lives on disk, never in a conversation.** `PROJECT.md`, `BRIEF.md`, `run.json`,
  `LEDGER.md`, `HANDOFF.md`, `HANDBACK.md`. Any role can die and a fresh one continues from
  the files. A role that needs something another role knew reads it from disk or does not
  get it.
- **Sessions are short and single-hat.** A session wears one role. A role change is a new
  session, not a mode switch inside an old one. The context that produced a unit of work is
  dead weight for the next unit.
- **The grader is never the author.** Nothing a role writes is judged by that role. Every
  check is a fresh context that gets the artifact and the contract, never the reasoning.
- **Big things are read by a Reader, never inline.** A build log, an accessibility tree, a
  200-line ledger, a review surface: a cheap reader returns the one line the caller needs.
- **The model matches the request, not the person.** Judgment per request is high for the
  Planner and rare for everyone else. Price follows that. A role has a *default* model and
  **variants named by capability** — an Opus Worker, a Sonnet Worker, a Sonnet
  Reviewer — and the brief picks the variant.

## Read the machine profile before starting anything

Every role reads `~/.claude/robowright/profile.md` in full at preflight; its seven headings are
the contract in `PROFILE-CONTRACT.md`. **No profile installed → refuse to start and say so.**
Do not guess a default. A role working for a project reads it as the first path of the reading
chain `scripts/robowright-resolve.py` prints — profile, then project hook, then plugins; for a
project whose `robowright.json.repos` lists several repos, the profile once, then each repo's hook
and plugins in list order — and each
role's handbook says where it runs that call.

The section every session needs before it does anything else is **Launch**. It decides how a
role's session is started and resumed on this machine and by whom, how a pasted line reaches a
shell that can start one, what a shell needs for `auto`, the exact command shapes, how the Lead
observes and messages a live Robowright Session, and the concurrency limits. The launch mode,
`paste` or `auto`, is `launch.json`'s, not the profile's. The observe command contract 7
requires is whichever one that section gives for the launch shape used.

**Why the answer can differ per machine without changing the design.** The design fact above is
about context, not about processes. A fresh background task inside the current session and a
freshly launched session are the same thing to this system: a fresh context that reads its
state from disk. Either one satisfies "sessions are short and single-hat". `run.json`,
`LEDGER.md`, `HANDOFF.md` and `HANDBACK.md` remain the state and the hand-off; the grader is
still never the author; the ceilings and the stop contract are untouched. A task or a session
that dies is resumed the same way: from the files.

**The trap, on any machine.** An orchestrating session that cannot rotate itself — because it
is the thing holding the conversation — only grows. It must stay a **Lead**, never a
builder: delegate every unit of implementation and every large read, and hold verdicts and
decisions only. An orchestrator that starts doing the work itself is the most expensive shape
the system offers, because every later request re-reads the whole diff it just wrote. When its
context nears the compaction threshold it writes the state to disk and says so, rather than
pressing on.

## Robowright

| Title | Role | Default model · variants | One session is… | Handbook |
|---|---|---|---|---|
| **Planner** | planner | Fable · Opus Planner for a small project | One project's plan (Phases 1–5: scope, negotiate, `robowright.json`, `PROJECT.md`, the unit list, exploration docs, first brief), **or one later brief**, **or one standalone brief from a `work-planner` work order**, **or one rebrief** after a Robowright Session's third stop, **or one end-of-stack review** of intent against the plan, **or one replan** the Owner asks for mid-project. Every plan-level judgment call; ends when its one artifact is written | `planner` |
| **Lead** | lead | Opus · Sonnet only at `delegation: owner` | One project's execution (Phase 6): watch every Robowright Session from disk, decide the reversible execution calls the project's delegation level puts in its hands, bring the Owner-only floor to the Owner, take finished sessions back into the plan, ask for the next brief or rebrief, decide what launches. **The only role that escalates to the Owner.** Never implements, never writes a brief | `lead` |
| **Worker** | builder | Opus · Sonnet Worker | One brief, one worktree, a fresh session per unit: build, test, commit, review-gate each unit, run its own shakedown, publish the way the project hook defines publishing, leave a handoff. Stops only on the stop contract | `worker` (+ the repository's project hook, contract in `worker/PROJECT-HOOK.md`); agent `worker-spec` writes a `behavior` unit's behavior table and failing tests from the contract before the unit is implemented, applying `worker/prompts/BEHAVIOR-SPEC.md` and `bdd` |
| **Reviewer** | reviewer | Opus for code · Sonnet for prose | One artifact: a unit diff, a whole-stack diff, a change description, a comment set, a finished Robowright Session's record. Reads, reviews, writes citations, changes nothing | Agents `reviewer-gate`, `reviewer-adversarial`, `reviewer-docs`, `reviewer-intake`, `reviewer-map` (answers one question about a range so the Explainer and Planner never read the diff); they apply `worker/prompts/*`, `lead/prompts/HANDBACK-INTAKE.md`, `comment-pass`, `doc-gate`, and the Review Overlay, when a `reviewer.overlay` row names one (`PROFILE-CONTRACT.md` → Review Overlay) |
| **Reader** | reader | Haiku | One question about one big thing: a log's verdict, an element in a UI tree, a Robowright Session's ledger tail, the state of a review surface. Returns one line, decides nothing | Agents `log-reader`, `ui-tree-reader`, `reader-roster`, `reader-file`, plus any Reader-class script the profile's or the project hook's Duties name |
| **Explainer** | explainer | Opus · Sonnet at `owner` level | One document that explains finished work to the person who owns it but did not do it: an **owner brief** per published stack (what to decide now, the decisions made for the Owner, what changed, at most three spot-checks, where the detail lives; 1,000 words at most, 400 for a small unit) or the **project report** at wrap-up, for the people who will maintain the work and the ones who paid for it. Assembles from the record through Reviewers and Readers, never the diff, never re-derives, never posts | `explainer` |
| **Owner** | owner (you) | A human | The human. Sets Robowright (`robowright.json`: delegation level, model per role) at kickoff, ratifies the plan and each brief's budget, answers the floor — money, shipping, people — reads the decision review at intake, reviews the work, and does everything the profile's Owner-only floor reserves. Plans a one-unit ask in their own console with `/one-off` and accepts it with no Lead. The only role that speaks to other people | `one-off` |

Models are **per project, not per role forever**: `robowright.json` names one per role within a floor
(`planner/SKILL.md` → "Robowright settings"), the brief copies it into `run.json.robowright`, and every
launch line and Reviewer spawn reads it from there. The defaults above are what a project gets
when nobody says otherwise.

**Title and role, always together in anything a person reads.** The titles are the fun names
and they do not explain themselves, so every time one appears in chat, a report, a ledger, a
change description, or a doc heading, the plain role follows in parentheses the first time it is
used there: "a Planner (planner) session", "the Lead (lead)", "a Reviewer (reviewer) on the
diff". After the first pairing in a passage the title alone is fine. The tagline above uses the
same verbs, so it reads as the role column.

Two things are *not* Robowright: the **scripts** (`run-roster.py`, `run-cost.py`, and whatever the
profile's Tools and Budget sections name) are tools the Lead and Worker hold; and the **project
hook** is the repo-specific page of the Worker's handbook, not a role.

### Planner (planner) — Fable, one session per plan and then one per brief

Planning is a few hundred requests, each carrying a lot of judgment: what is in scope, what
the one-way doors are, how to size a unit, which decisions are settled. That is where the
most capable model pays for itself and where a wrong call costs the most downstream.

The Planner is **per brief, not per project**. The Phase 1–5 session ends when `PROJECT.md`,
the exploration docs, and the first brief exist. Every later brief is written by a fresh,
short `planner-<slug>` session that the Lead asks for once intake has corrected the
docs. The Planner never becomes the Lead and the Lead never writes a brief — brief-writing is
the judgment work (unit sizing, one-way doors, invariants for the Reviewer), and a session that
ticks for hours should not carry a Fable context to do it. The alternatives and their costs
are in `DESIGN.md` §7; the reason is §3: a planner-turned-lead ticks at a grown context,
several times the per-tick cost of a fresh Lead at the fixed base.

The front door for a single ask is the base skill `work-planner`, which any session runs: it ends
in a work order, and `/planner order <work-order>` is how one reaches Robowright. For a
one-unit ask of one to three hours, the Owner's front door is `/one-off <ask>`: it runs
`work-planner` in the Owner's console, writes a stub project and the brief, and launches one Worker
on the cheaper model with no Lead (`one-off`). The Planner
grounds and words a plan the same way — `work-planner`'s `GROUNDING.md` and `LEADING-WORDS.md`,
and `domain-modeling` beside `grilling` — so a work order and a project plan read alike.

Hands off: `<project_dir>/PROJECT.md`, `DECISIONS.md`, `Agent Explorations/PR*.md`, and one
`<session_dir>/BRIEF.md` + `run.json` per Robowright Session. Both roots are the profile's
(→ Paths).

### Lead (lead) — Opus

Thousands of cheap ticks re-reading the same roster, with judgment needed only at stops and
intakes. Opus in a fresh, small session is the right tool; Fable would double the write cost
of every tick for judgment that is not being exercised. The Lead runs under
`/loop /lead watch`, reads the roster once per tick (twice while a `running` session is unarmed), acts at most once per Robowright Session per
tick, and re-arms `notify_when_idle` on every live one in registry `busy`. It writes to the plan and to a Robowright
Session's `LEDGER.md` (to record the Owner's answer), never to its worktree or `run.json`.

Hands off: a launch line per brief, in the shape the profile's Launch section gives; an
`INTAKE.md` per finished Robowright Session, folded into `PROJECT.md`; then the launch line for the
next Planner session, which writes the next brief from the corrected docs. Once work is
published, the Lead runs every duty the profile, then the project hook, lists for
`lead.post-publish` — on a machine
with a review surface that is where the watch, the triage, the drafted replies, and any
`review-feedback` brief (via a brief-only Planner) live. It plans and drafts; it never commits.

### Worker (builder) — Opus by default, Sonnet by the brief's choice

The only role that writes code. The brief names the variant in its `model` field: an **Opus
Worker** is the default; a **Sonnet Worker** is the Planner's call for a brief
whose units are bounded and pattern-following (`docs`, `tests`, a mechanical `refactor`),
with the Opus Reviewer gate as the net either way. What keeps a Worker cheap is not the model
but the context discipline: `rotate_sessions: true` starts a fresh session per unit from
`HANDOFF.md`; `compact_pct` caps the window between rotations; every big read goes through a
Reader; one command per Bash call, no `cd`, no loops (`DESIGN.md` §2).

The one thing a Worker session does not write is what its own `behavior` unit is judged
against. `worker-spec` — a Worker-class agent, Opus, fresh context, `omitClaudeMd` — reads the
unit's contract and writes the behavior table and the tests before any of the unit exists; the
session then makes them pass without changing what they expect, and the gate Reviewer diffs
the tests from the spec commit to the head. "The grader is never the author", moved ahead of
the code: two independent readings of the contract, so a misreading shows up as a red test
instead of a green one.

Hands off: whatever the project hook's Publishing section calls published; `run.json` at
`done`; `HANDOFF.md` for a cold reader; `HANDBACK.md` for the Lead; `evidence/`, `reviews/`,
`smoke/` as the record.

### Reviewer (reviewer) — Opus for code, Sonnet for prose

A Reviewer never sees how the work was built; it gets the artifact, the contract, and the
evidence paths. Two kinds:

- **Code inspection** — the per-unit gate and the whole-stack adversarial review. Opus: a
  correctness miss here costs the Owner's time, and a same-model reviewer shares the author's
  blind spots, so this is not where to economize. Both close with the Review Overlay, when a
  `reviewer.overlay` row names one (`PROFILE-CONTRACT.md` → Review Overlay).
- **Prose and classification** — comment-pass, doc-gate, handback intake, the smoke
  inventory. Sonnet: each is an enumeration against a written rule, the rule does the
  judging, and none of them writes code. Escalate one to Opus when it returns `BLOCKED`.

Reviewers are **agent definitions** (`.claude/agents/reviewer-*.md`) with a default `model:`, an
`effort:` pin wherever that model is Opus — the session's effort reaches a subagent that pins none,
so an economy Worker's `low` would otherwise be the gate's —
`maxTurns` set, and `omitClaudeMd: true` — they read the skill they apply by path, so the
always-on rules are not re-read on every one of their requests. A Reviewer reads hunks
by range (`git show <sha>:<path> | sed -n 'a,bp'`), never whole files.

Hands off: one markdown file under `<session_dir>/reviews/` or the caller's ledger, first line
`ADVANCE` / `HOLD` / `CLEAN` / `CHANGES` / `READY` / `BLOCKED`, then citations.

### Reader (reader) — Haiku

Reads one large thing and returns only the line asked for. Haiku, `omitClaudeMd: true`,
`effort: low`, `maxTurns` under ten: a small fraction of the context per request of anything
that carries the rules. A Reader never decides, never edits, never runs a build. The set
grows whenever a role finds itself pulling a big file into its own context: today logs and
UI trees, next the roster tail for the Lead.

### Explainer (explainer) — Opus

The role that did not exist until the system worked: once Robowright can produce 4,000 correct
lines overnight, the bottleneck is the owner understanding them. The Explainer's two documents
are the answer to "what must I decide, and what did you decide for me" (the owner brief, per
published stack, before the Owner starts reading the change) and "what did we build and
why" (the project report, at wrap-up). Four rules in its handbook: assemble, never re-derive;
never read the diff (a Reviewer does); risk labels cite the gate review that earned them;
spot-check questions are posed, never assigned as homework. Evidence behind the owner brief's sections:
`DESIGN.md` §10.

Hands off: the owner brief and `<project_dir>/REPORT.md`, at the paths the profile names
(→ Paths). Publishing either one is whatever the profile, then the project hook, lists for
`explainer.publish`, and the
Owner's explicit yes on top of it.

### Owner (owner) — a human

Everything another person reads or that is hard to undo. Ratifies `PROJECT.md`, each brief
and its budget; answers `one-way-door` and `verification-failed` stops; reviews the finished
work; everything on the Owner-only floor is theirs. Launch is their line to paste unless the
machine's `launch.json` sets `launch` to `auto`; the profile's Launch section says who
carries the paste to a shell. Robowright brings them calls in
the decision-reporting shape the Owner's own rules give, when the machine has them, and
nothing it could have decided itself.

## A unit of work's path through Robowright

```
Owner ─ idea ─▶ Planner (Fable) ─ PROJECT.md, exploration docs, BRIEF.md ─▶ Lead (Opus)
                                                                                          │ launch
                                                                                          ▼
                            ┌────────────── Worker (Opus), one session per unit ──────────────┐
                            │ build → test → Reader reads the log → Reviewer gates the unit → close   │
                            │ … end of stack: Reviewer (adversarial) → [fix → re-review]* → ADVANCE      │
                            │ → Reviewer (comment-pass, Sonnet) → smoke → change descriptions            │
                            │ → Reviewer (doc-gate, Sonnet) → publish                                    │
                            │ → HANDBACK.md → Planner (planner-review, Fable): PLAN-REVIEW.md → [polish] → finish │
                            └───────────────────────── HANDOFF.md, HANDBACK.md ─────────────────────┘
                                                                                          │ done
                                                                                          ▼
                              Lead: Reviewer (intake, Sonnet) → INTAKE.md → PROJECT.md corrected
                                          → Owner asks → Explainer guide → decision review → next BRIEF.md
                                ─── or ─── stop → Lead decides (Decided (Lead)) → resume
                                ─── or ─── stop on the floor → Owner's answer → resume
                                ─── or ─── third stop, or a rebrief verdict → Planner rebrief (REBRIEF.md) → rotate
                                                                                          │ Owner says go
                                                                                          ▼
                              Lead: every duty the profile, then the project hook, lists for lead.post-publish
                                          → drafts for the Owner · Reviewer verifies any bot claim
                                          → review-feedback BRIEF.md (Planner) → Worker → accepted
```

Every arrow is a file. No arrow is a conversation.

## Contracts every role keeps

1. **Read before deciding.** The roster is a pointer, `HANDOFF.md` is the state, the ledger
   tail is the truth when `run.json` lags it.
2. **One action per Robowright Session per tick** for the Lead; **one command per Bash call** for
   everyone.
3. **Quote verdicts, never infer them.** The verdict lines are the ones the project hook names
   (→ Build, → Tests), read through a Reader or the hook's own verdict reader and quoted
   verbatim — never inferred, never grepped out of a log.
4. **Never post as the Owner.** Drafts yes; anything another person reads, no. That line is the
   profile's (→ Owner-only floor), and the profile is the only place an exception to it can be
   written down.
5. **The budget is ratified, then enforced.** A Robowright Session's budget is ratified in the
   brief; whatever the profile's Budget section names enforces it. No role raises it and no
   role writes `STOP` on its own.
6. **Size the move.** `sizing-the-move` applies to every role: structural → now and fully;
   unrelated → parked; verification → until proven, never past the ceiling.
   `sizing-the-move` is `RULES.md` in this directory; an Owner who wants it always on links it
   into `~/.claude/rules/`.
7. **Every background agent comes with its observe command** — the one the profile's Launch
   section gives for that launch shape — in the same message that started it, together with the
   session directory to read if the agent goes quiet.
8. **Only the Lead escalates.** A Worker's stop is addressed to the Lead, which decides
   what `delegation` allows — a reversible, execution-level call, written down with its
   alternative before the resume — and brings the Owner only the floor: the budget, shipping a
   behaviour change, schema / public API, reversing a settled decision, anything a person
   reads. A Robowright Session's third stop is a Planner rebrief, not a fourth decision. Every
   delegated decision reaches the Owner once, at intake, as the decision review.
9. **Robowright is configured, within floors.** `robowright.json` picks the model per role and the
   delegation level at kickoff; a brief may tighten either, never loosen. Nobody picks a model
   below a role's floor (`planner/SKILL.md` → "Robowright settings").
10. **Match the launch to the profile.** How a role's session is started here is the profile's
    Launch section, not a habit and not last week's machine; the launch mode, which decides
    whether the launcher starts it or hands off a line, is `launch.json`'s `launch` key. Read
    both before launching, not after.
11. **Name a unit to the Owner by its id and its name: `U12 (note-autosave)`.** The id is the
    `#` cell of its `PROJECT.md` Task Breakdown row. The name is the short name its slug ends in
    (`sample-012-note-autosave`), or, where the `Unit` cell is a tracker key, two or three words
    from its `Summary`. It goes in parentheses after the id — in chat, in a report, and in every
    document the Owner reads. A bare `U12` makes the Owner look the number up.

## Naming

The formats are the project hook's (→ Naming): slug or ticket key, base ref, branch, and the prefix
each role's session name takes. What Robowright fixes everywhere is the shape, and these
constants:

| What | Handle |
|---|---|
| Planner session | One per mode — the plan, one per later brief, one per rebrief (`-r<n>`), one for a by-hand end-of-stack review (`plan_review: off`), one per replan |
| Lead session | One per project |
| Worker session | One per Robowright Session, carrying the model the brief chose |
| Explainer session | One per published stack for an owner brief, one per project for the report |
| Robowright settings | `robowright.json` in the project folder — delegation level, model per role, the Owner-only floor, where the plan review runs; copied into each `run.json` as `delegation`, `robowright` and `plan_review` |
| Rebrief and review verdicts | `<session_dir>/REBRIEF.md` (`confident` / `owner`), `<session_dir>/PLAN-REVIEW.md` (`ship` / `polish` / `rebrief`, written at `finish` by `planner-review`); superseded briefs stay as `<session_dir>/BRIEF.r<n>.md` |
| Reviewer agent files | `.claude/agents/reviewer-gate.md`, `reviewer-adversarial.md`, `reviewer-docs.md`, `reviewer-intake.md`, `reviewer-map.md` |
| Worker agent files | `.claude/agents/worker-spec.md` |
| Planner agent files | `.claude/agents/planner-review.md` |
| Reader agent files | `.claude/agents/reader-roster.md`, `reader-file.md`; `log-reader` and `ui-tree-reader` keep their names until something forces a rename |
| A session directory | `BRIEF.md`, `run.json`, `LEDGER.md`, `HANDOFF.md`, `HANDBACK.md`, `INTAKE.md`, `STOP`, plus `evidence/`, `reviews/`, `smoke/` — constant on every machine; the root they sit under is the profile's (→ Paths) |
| A project folder | `PROJECT.md`, `DECISIONS.md`, `Agent Explorations/`, `smoke/`, `briefings/`, and the owner-brief folder the profile names (→ Paths) |
| Decision logs outside a project · agent output with no better home | The profile's (→ Paths) |

## Adding to Robowright

A new skill or agent joins as exactly one role, and its frontmatter says which. The test:
*does it write code?* → Worker territory, Opus. *Does it judge an artifact against a
contract?* → Reviewer; Opus if the artifact is code, Sonnet if it is prose or an enumeration.
*Does it read one big thing and return one line?* → Reader, Haiku, `omitClaudeMd`. *Does it
decide what happens next, at execution level?* → Lead, and it probably belongs in that
handbook rather than as a new skill. *Does it change the plan — units, scope, a settled
decision?* → Planner, as a mode of that handbook (brief, rebrief, review, replan), never a new skill.
*Does it explain finished work to someone who did not do it?* → Explainer, as a mode of that
handbook (guide, report). *Does it start the Owner's own path from the console?* → an
Owner-invoked skill (`disable-model-invocation: true`), as `one-off`, `robowright-onboard` and
`spend-debug` are. Anything that speaks to another person is the Owner's, full stop.

### Three layers, and where a new fact goes

| Layer | When it applies | What it carries | Where |
|---|---|---|---|
| **Machine profile** | Run time | Everything true of one machine or organisation: Identity, Launch, Budget, Tools, Owner-only floor, Paths, Duties | `~/.claude/robowright/profile.md`; contract in `PROFILE-CONTRACT.md` |
| **Project hook** | Run time | Everything true of one codebase: build, tests, kind checks, device, regression sweep, commits, publishing, traps, naming, duties | Resolved per repository; contract in `../worker/PROJECT-HOOK.md` |
| **Platform plugin** | Run time | Everything true of one toolchain: verdict and hang shapes, the device model, the default kind → check table | `~/.claude/robowright/plugins/<platform>.md` if the machine has one, else `~/.claude/skills/robowright/plugins/<platform>.md`, named by a hook's client table; contract in `PLUGIN-CONTRACT.md`, read via `robowright-resolve` |

A fact true of *this system* belongs in a handbook. A fact true of *this machine or
organisation* belongs in the profile. A fact true of *this repository* belongs in the project
hook. A fact true of *one toolchain* belongs in a platform plugin. No handbook names a scheme, a
test target, a launcher script, a budget unit, a branch prefix, or a service that publishes. How
the layers install on each machine, and the platform plugin layer: `ARCHITECTURE.md`.

**Extension points.** A handbook reaching one runs every duty the profile, then the project
hook, lists for it, in order, and nothing at all when both list none:

`planner.brief` · `worker.preflight` · `worker.unit-gate` · `worker.publish` ·
`lead.tick` · `lead.intake` · `lead.post-publish` · `explainer.publish` · `reviewer.overlay`

A step that exists on one machine only — a review-surface watch, a feedback triage, a
publishing step, a re-sync against a tracker — lives there and nowhere in this file.

## What this changes — what is still owed

What has landed is recorded in the repository's `CHANGELOG.md`.

Still owed:

| Item | Why | Where |
|---|---|---|
| A Stop hook that rotates on its own | A rotation that falls between the Lead's ticks otherwise waits for the next one; unproven that a hook can start a detached session, and a launcher that refuses while the rotating session is still live blocks it from the other side | `worker/hooks/stop-gate.sh`, one measured attempt first |
| A per-call `model:` on a Reviewer whose agent file pins `model:` | The Agent tool's own schema says a per-call `model` takes precedence over the agent definition's — documented, never exercised; `robowright.json`'s Reviewer rows depend on it and nobody has run a Sonnet code Reviewer yet | The first project with `reviewer_code: sonnet` |
| The Planner's `rebrief` and `review` modes on real work | Both are written and dry-run tested; no Robowright Session has stopped three times under the current contract, and no stack has had the review pass | The first one that earns it |
| The Explainer's `guide` and `report` on a real stack | The owner brief's sections rest on one RCT and one production study (`DESIGN.md` §10); whether the Owner actually reads the brief first, and whether its cap holds what they need, is the measurement | The first published stack |
| `worker-spec` on a real `behavior` unit | The evidence that a spec author who never sees the implementation writes better tests is function-scale and from older models; unmeasured here is how often its tests need more than plumbing changes to compile against the real seams — if that is most of the time, the Worker is rewriting the spec and the separation is buying nothing | The first brief with a `behavior` unit; count `Spec dispute` entries and plumbing edits at intake |
| One Robowright Session end to end | The design's cost reasoning came from sessions under the old shape; the first `planner-` → `lead-` → `worker-` chain here is the measurement that says whether the design holds | The next unit of work |

## State has one writer

A Robowright Session's state fields in `run.json` — `phase`, `stop_reason`, `rotate`, `rebriefs`,
and a unit's `status`, `gate_attempts`, `head` — change only through
`scripts/session-state.py <session_dir> <event>`. It checks the event against
`state-machine.json` (is it legal from here, do its guards hold on disk), applies it
atomically, and appends it to `<session_dir>/events.jsonl`; a refusal is logged too. The
launcher asks it what is legal (`check-op`), the roster asks it what a stored state means, and
the Worker's write hook asks it whether a direct edit touched a guarded field. Every role's
handbook names the events it applies: the Worker all of a session's own, the Planner
`rebrief`, the Lead or the Owner `resume`. `session-state.py <session_dir> status` answers
"what state is this and what may happen next" for any of them.

`STATES.md` draws every machine in the system — the two enforced ones and the documented
ones (roster verdicts, stop routing, rebrief, rotation, the Lead's tick, intake, the device
lock, publish and accept) — and the whole in aggregate. It is generated from the table
(`session-state.py doc --write`); a test fails when it is stale.

## The other files in this folder — for people, not for you

Do not read these to do a role's work; nothing procedural is in them.

- `STATES.md` — the state machines, drawn: read the one section you need when a transition is
  refused or a verdict is unclear.

- `README.md` — the five-minute explainer of the system for a human reader.
- `ARCHITECTURE.md` — the as-built map: the installs, the layers and each role's reading
  chain, the session lifecycle, `run.json`'s core and plugin keys, multi-repo projects and the
  dependency checkout, and which file to edit for each kind of addition.
- `OWNERS-GUIDE.md` — the same system from the Owner's seat: their path drawn as a flowchart,
  their decisions in order, what can interrupt them, and where to look.
- `PROFILE-CONTRACT.md` — the seven headings a machine profile must answer, and why a missing
  profile is a refusal rather than a default.
- `DESIGN.md` — the mechanisms behind the design: a Robowright Session's cost shape, the
  `compact_pct` ceiling, the subagent floor, cache-TTL facts. Read a section
  when a reason is needed, never the whole file.
