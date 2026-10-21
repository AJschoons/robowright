# Robowright — design notes

Why the system is shaped the way `SKILL.md` says. Read on demand; nothing here is procedure.
The design calls below came from reading a Robowright Session's own transcripts under
`~/.claude/projects/<worktree-slug>/**/*.jsonl`, with the same method the cost scripts use
(per-message `usage`, deduped by message id, one model's list price). Those sessions ran on a
private repository, so their figures stay there; what follows is the mechanism they showed.
The scripts' absolute totals run low, so read ratios, not totals. Prices are a machine fact and
live with the profile (→ Budget). Run `run-cost.py` on your own sessions for your numbers.

## 1. Where a Robowright Session's cost goes

In the sessions read, the main session carried most of the cost, and inside it cache reads
were the dominant term by far; output, the part that produces code, was a small share. The
cache-read component is `context × the cache-read rate`, so every request pays to re-read its
whole context before it writes a token.

**Consequence:** the lever is average context per request and the number of requests. Model
choice for the writer is third.

## 2. The context ceiling

A session compacts when its window fills. Lowering the ceiling with
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (the brief's `compact_pct`) cut cost per request with the same
skill, repository and model, because average context fell. The post-compaction floor did not
move: it is the fixed base — system prompt, `CLAUDE.md` and its imported rule files, the skill
listing, and the compaction summary. That floor is why **rotation** (a fresh session per unit
from `HANDOFF.md`, restarting at the fixed base) beats **compaction** (a lossy summary that lands
above it and grows again): rotation is the same idea done cleanly, and the design already had it
(`rotate_sessions`, the launcher's rotate path, the `rotating` roster verdict). It becomes the
default for multi-unit briefs. A single-unit session has no rotation to reset it, so a
`compact_pct` somewhat below the 85 default brings the reset earlier and holds the average
context down; the floor is the fixed base plus the room a unit's work needs above it, and a
value that leaves no such room against the 250k window is too low. Read the ledger for
post-compaction mistakes after changing it.

**Since 2026-09-21** the ceiling is set in two places: a machine's `settings.json` may set
`autoCompactWindow` to 250k (the sessions behind §1 ran at 500k) and the launcher's `compact_pct` default is 85, so a session compacts
near 212k. Once, the launcher's environment did not reach the session.
`claude --bg` claims a pre-forked spare from the background daemon, which keeps the environment
of whoever started the daemon. A Worker on another project had started it with
`compact_pct: 50`, so sessions launched after it compacted at about half the intended ceiling,
a Planner repeatedly within minutes. The three
per-session variables travel inside `--settings`, whose `env` block is written over the
inherited value (probe: a session launched under a 50 daemon with
`--settings '{"env":{"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE":"77"}}'` printed 77). `compact_pct` is a
percentage of that window: a value chosen against the old 500k window gives half the tokens
against 250k, so re-derive it, never carry it over.

**Request count:** a main session's tool calls included many `cd` calls, `until` loops, and
whole-file `grep`, `sed` and `cat` reads. The `cd`s bought nothing. Rule 8 of the Worker's
handbook bans them; the git tool the profile names (→ Tools) exists so a git command needs no
`cd`. The `until` loops are requests spent sleeping — the background-task notification is free.

## 3. Subagents pay for the rules on every request

A subagent that loads `CLAUDE.md` starts at the fixed base: `CLAUDE.md`, the rule files, and
the skill list, re-read at cache-read price on every request of every subagent. A `log-reader`
(Haiku, `omitClaudeMd: true`) starts at a small fraction of that. An independent community
measurement (dev.to, 2026) puts the fixed spawn cost at ~54k tokens.

Reviewers also grew: a gate reviewer that read most of the worktree with `sed` and `cat`
ended with a context several times the fixed base. The Reviewer rules in `SKILL.md` — agent
definitions, `omitClaudeMd`, `maxTurns`, hunks by range — are the response; before them the
reviewers were plain prompt files spawned ad hoc, and every one inherited Opus.

**The lead:** a planner that carried on as lead grew a large context over its ticks, and a
fresh session at the fixed base does the same routine tick for several times less, and more
than that on an intake tick, which reads more. Hence the design call: the Planner ends, the
Lead starts fresh.

## 4. Model by role — what the evidence supports

The community pattern (Anthropic's own multi-agent research post; jsmanifest,
CloudZero; the r/ClaudeAI thread of 2026-08) converges on *strong model plans and reviews,
cheaper model does bounded work*, with claimed savings of 40–80% and no two sources agreeing
on a number. One metered counter-example (Systima, "Subagent Tax"): two Opus subagents cost
2.6× the sequential tokens with no wall-clock gain; two Fable subagents, 5.9×. Fan out only
for independent work, never to parallelize one read.

How that lands on Robowright:

| Role | Model | Reasoning |
|---|---|---|
| Planner | Fable | Few hundred requests, high judgment each, highest downstream cost of a wrong call. Fable's premium (2× Opus on input/output) is spent where it buys the most |
| Lead | Opus | Thousands of low-judgment ticks. Fable's cache *read* is half Opus's but its write is 2×, and a tick that lands after the cache TTL is a write; only worth it with the 1h TTL on |
| Worker | Opus default; Sonnet by the brief | The thread's one named Sonnet failure mode is "silently redesigns while it codes" — an anecdote, not a documented pattern, but it is the failure the gate is worst at pricing. So the Planner picks the variant per brief: Opus for judgment-heavy units, Sonnet for bounded pattern-following ones, the Opus Reviewer gate as the net either way. Each session's `run.json.cost` is the record that tunes the choice |
| Reviewer, code | Opus | Correctness miss costs the Owner's time; same-model blind spots already noted in the Review Overlay |
| Reviewer, prose | Sonnet | Enumeration against a written rule; 60% cheaper per token at list; writes no code |
| Reader | Haiku | Already measured right |

Mechanism (all documented in the Claude Code docs, fetched 2026-09-18): agent frontmatter
`model:` takes `sonnet` / `opus` / `haiku` / `fable` / `inherit`; `effort:` overrides the
session's; a launched background session accepts `--model` and `--effort`;
`CLAUDE_CODE_SUBAGENT_MODEL` sets the default for a session's subagents and frontmatter outranks
it. No hook can pick a model.

## 5. Cache TTL — the fact that decides whether ticks are free

Claude Code caches in two buckets. The **main conversation** gets a 1-hour TTL automatically
only on a subscription plan within plan usage; on an API key it is 5 minutes. **Subagents,
compaction, and forks are always 5 minutes** unless `subagentPromptCacheTtl: "1h"` is set.
The costs page says a scheduled task or cross-session message that arrives after the TTL
"sends your full context each time". A missed tick costs roughly **11×** what a hit costs, at
any context size, and the absolute gap scales with context: small at a fresh Lead's, several
times larger at a long-lived one's. The 1h write costs 2× base instead of 1.25×, so it pays with
two or more ticks an hour — always, during a watch. **The usage panel prints
the main cache's TTL and warm/cold state.** Which plan a session bills to is a machine fact; the
profile's Budget section is where it is written down.

`notify_when_idle` is one-shot, same-machine, 12-hour expiry, and only a *main conversation*
can subscribe — a Reader reading the roster cannot be the one that arms it.

## 6. Accounting

- `run-roster.py`, the spend guard, and `run-cost.py` carry model price tables, and once
  two rows were stale: Sonnet 5 looked far dearer than it is, and Fable 5.1 was priced as
  Opus, so a Fable session's output cost came out too low. Prices are a machine fact
  and belong with the profile (→ Budget); the scripts' job is the arithmetic, not the rates.
- `run-cost.py` walking every transcript under the worktree's project dir once reported several
  times a session's actual cost, because the worktree still carried an earlier one. For a
  session's total it counts the transcripts `run.json.transcripts` pins, as the spend guard
  does (`../lead/scripts/spend-guard.py:117`), and walks the worktree only when none are pinned or
  `--whole-worktree` is passed (`../worker/scripts/run-cost.py:124-140`). A unit's ledger record
  reads both, bounded by the unit's window (`../worker/scripts/run-cost.py:143-146`).
- Neither prints cost per request, the number `compact_pct` and `rotate_sessions` should be set
  from.
- There is no long-context surcharge on these models; sessions near the old 500k window were priced
  correctly on that axis.
- The three tables are now one Owner-maintained file, `pricing.json`, read through `pricing.py`.
  Every text report prints its `updated_at` and every report warns past 30 days; without the file, USD is null.
- Where the money went across sessions is the append-only ledger `<accounting_root>/records.jsonl`,
  one record per session, role and model, read back by `robowright-cost.py`.

## 7. When the Planner ends — decided 2026-09-18

| Option | For | Against |
|---|---|---|
| **A. Ends at the first brief; fresh Lead; a fresh Planner per later brief** (chosen) | Lead ticks at the fixed base, not a grown context (§3). Fable spend stops when judgment stops. Forces the plan onto disk, which the system assumes anyway. Brief-writing stays on Fable | One more launch per unit of work, a line the Owner pastes unless the profile's Launch section lets a role start a session itself |
| B. Planner becomes the Lead (the handbooks before this) | No handoff loss | Several times the cost per tick (§3); two hats in one context; a Fable Lead doubles every tick's write for judgment it rarely uses |
| C. Planner stays idle; Lead messages it for briefs | Keeps the planning context | Every wake is a full cache miss on a large Fable context, paid before it types a word; breaks the rule against messaging a session that is not executing a brief; two long-lived sessions |

## 8. Names — settled 2026-09-18

System **Robowright**; titles **Planner**, **Lead**, **Worker**, **Reviewer**,
**Reader**, **Owner**, each paired with a plain role — planner, lead, builder, reviewer,
reader, owner — written in parentheses at first mention wherever a person reads it, because a
title alone does not explain itself. Plain job titles, chosen so a newcomer can guess the
function. Variants are named by capability: Opus Worker, Sonnet Worker,
Sonnet Reviewer. Rejected: *Sawyer* and *Sweep* (not guessable),
*Scout* and *Inspector* for the checker (Reviewer kept — enforces the rules, writes citations),
*Builder* (too generic), a collective noun for the worker (plural for a single thing), the
metaphor-family system names that only a collective-noun worker would have needed.
Scripts are unnamed: tools, not roles.

## 9. Delegation — decided 2026-09-18

Before this, every one of the six stop codes reached the Owner through the Lead, so an overnight
Robowright Session stopped at the first judgment call and waited for morning. The measured cost was
not the money (a stopped session spends nothing) but the wall clock and the shape of the ask:
six small decisions arriving one at a time, each a full context switch for a person.

**Three tiers, one floor.** The Worker already assumed everything reversible and logged it
(`Assumed`). The new middle tier is the Lead deciding execution-level calls whose chosen option
a commit on the branch can undo before publish, written down with the alternative *before* the
resume. The Owner-only floor is closed and fixed in `robowright.json.owner_only`: the budget cap,
time past the brief's allowance, accepting a product-visible change, schema / public API /
protocol, reversing a settled decision, anything another person reads. A brief may add to the
floor, never remove from it.

**Why a third stop is a rebrief.** Three stops on one Robowright Session means the brief's model of
the work was wrong, not that three decisions were hard (sizing-the-move rule 3: a third failure
means redesign, not another placement). Rebriefing is plan-level judgment, which the system
already puts in one role, so it is a Planner mode, not a Lead power — keeping "the Lead never
writes a brief" a rule with no exceptions. The Planner writes the verdict; the Lead stays the
only launcher so one role owns the roster.

**Why the review pass is a Planner and not a Reviewer.** The end-of-stack Reviewer checks the
contract; nothing checked intent — whether the stack did what `PROJECT.md` wanted and whether
the mid-session decisions drifted. That is planner-class judgment. Grader-never-author holds at
the session level (a fresh session, never the planner's), and the pass never reads the diff:
code questions go to a Reviewer that reports deltas, because Fable over a whole stack is the one
cost that would make the pass not worth running. Bounded to one pass and at most one three-unit
polish brief, so "improvements" cannot become a loop.

**2026-09-26: the pass runs at `finish`, inside the Worker's session.** The Worker spawns the
`planner-review` subagent on the Planner's model once `HANDBACK.md` is on disk, records its
verdict with `state plan-review`, and `finish` waits on it; `run.json.plan_review` (`finish`,
`per-unit` or `off`) says where it runs, and `off` keeps the by-hand pass above.
Grader-never-author now holds at the subagent level: the reviewer is a fresh context that never
reads the diff, not the session that built the stack. The bound is unchanged: a review's
polish is one pass, applied as commits on the tip and gated before `finish` reads it, and what
it leaves is a follow-up.

**Why the decision review is at intake and not per decision.** A ping per decision recreates
the interruption the tier exists to remove; a review at intake is the engineering-manager
shape — here is what I decided for you, ranked by how sure I was, here is how to overrule it.
Overruling is a brief, so it lands on disk like everything else.

**Models per role, within floors.** The role table in §4 is the default, not the law. A small
project can run its Planner on Opus; a `owner`-level project can run its Lead on Sonnet
(a Lead that only relays needs no judgment); nothing runs below its floor — a Haiku Planner
or a Sonnet code Reviewer is a different system, not a cheaper one. Set once at kickoff in
`robowright.json`, copied into `run.json.robowright`, read by the launcher, and passed as
`model:` on every Reviewer spawn. Documented but never exercised: the Agent tool's own schema says a per-call
`model` takes precedence over the agent definition's frontmatter, and the Reviewer rows depend
on that being true; the first Sonnet-Reviewer project confirms it.

## 10. The Explainer — decided 2026-09-18

The last role added, and the one the others make necessary: when Robowright can produce a large,
correct stack overnight, the cost that remains is the owner understanding it well enough to
review, accept, and answer for it. Two research passes, every claim labelled
with its URL and whether it is a study, practitioner or vendor source, shaped the two documents.

**Review guide, section order by evidence strength.** Risk-tiered routing (skip / skim / full by
blast radius) has the strongest support — Meta's RADAR paper with production metrics — so the
guide leads with a risk tier and labels every change in the stack and every file, with the rule
that a label cites the Reviewer gate review that earned it, never the Explainer's read. The
Anthropic RCT (n=52) found engineers using AI scored 50% vs 67% on comprehension of the code; the
countermeasure with support is explain-back, so the guide poses three questions with the line
numbers where the answers live — posed, not assigned: the Owner chose not to have answers written to a file, and left answering
them to the reader. Google's
what / why / how-tested description and bottom-up review of stacked diffs are institutional
standards and give the guide its §2 and §3. Everything vendor-shaped ranked low: GitHub disclaims
evidence that Copilot change summaries help reviewers; CodeRabbit walkthroughs and CodeSee maps
have no independent study. Two caveats the researcher flagged: Google has no documented "reading
order for reviewers" practice — the read-order section is a synthesis — and the 400-lines-an-hour
figure is a single 2006 vendor study, so the guide's session guidance carries that caveat.

**Project report.** Fourteen formats compared (ADR, MADR, arc42, C4, Google design docs, Amazon
6-pager and PR/FAQ, RFC close-outs, Shape Up, Atlassian's project poster / DACI / retrospective
templates, Microsoft's playbook decision log). The distillation pattern with the clearest source is
Microsoft's: full records stay in the log, a summary table (ID, status, alternatives, consequence)
is the executive index — the report's §4, capped at ten rows. The one falsifiable diagram rule
found: architecture diagram for blast radius, sequence diagram only if operation order changed,
skip class and data-flow diagrams. No controlled study compares diagram types; that is
practitioner consensus. Sections 8–9 (known gaps, how to operate and extend) have no named
source and are labelled as the researcher's synthesis.

**Why a role and not a Lead or Planner mode.** It fails every test in "Adding to Robowright": it
writes no code, judges no artifact against a contract, returns more than a line, decides
nothing, changes no plan. It explains, and no other role does. Opus,
because ranking what matters in a large change is judgment; Sonnet only at `owner` level,
where the guide is a digest. Guide per **published stack**, not per Robowright Session, because
bottom-up stacked review is the unit the evidence supports.

**2026-09-26: the owner brief replaces the guide.** The nine sections above gave way to five —
Decide now, Key decisions, What changed, Spot-check, Where the detail lives — capped at 1,000
words for a unit sized M or larger and 400 for S or XS, with the doc-gate blocking a brief over
its cap. The explain-back and risk-tier evidence above is unchanged and now informs
**Spot-check**: each item is a line a review held or a hotspot the brief named, cited to the
review that earned it, and poses the question to hold while reading it, never assigned. The read
order, file map and session guidance stay out of the brief, in the intake and gate reviews it links.
