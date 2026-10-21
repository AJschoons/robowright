# Intake prompt — absorb a finished Robowright Session into the plan

Spawn one fresh-context subagent per finished Robowright Session. It gets the session directory,
the project folder, and read-only access to the worktree. Not: the Lead's reasoning, the
planning conversation, or a summary of "what the work was supposed to do" — the brief says
that, and the intake's job is to find where reality diverged from it.

```
A Robowright Session has finished at <session_dir>. You did not run it and you do not trust its
summaries. Read, in this order: HANDBACK.md if present, HANDOFF.md, the last ten headings of
LEDGER.md and every entry under `Assumed`, `Brief corrections`, `Parked`, and any Owner-answered
stop, reviews/*.md, and BRIEF.md last. The worktree is <worktree>, read-only; every code claim
is verified with `git show <tip>:<path>` against the tip in HANDOFF.md, never against a doc.

The plan lives in <project_dir>: PROJECT.md, DECISIONS.md, `Agent Explorations/*.md`, and
any `REPLAN-*.md`. Read PROJECT.md's Resolved Decisions table and every exploration doc for a
unit the session did not finish.

Write <session_dir>/INTAKE.md with exactly these sections, under one page each:

1. **Names and shapes that changed.** Every type, member, event, file, or branch the plan
   cites that the tip spells differently — the brief's frozen names, the Owner's review
   renames, anything in HANDBACK §1. For each: old → new, why (quote the ledger or the Owner),
   and a table of plan docs × stale mention counts (`grep -c`). Flag any old name that is now a
   different live type, so a blind replace would corrupt the docs.
2. **Decisions.** (a) Brief decisions the session answered — D-ref, answer, evidence path.
   (b) Ratified decisions the session or the Owner reversed — these are PROPOSED rows for the
   Owner, never applied by the Lead. (c) `Assumed` entries that should become decisions before
   the next brief. (d) Every `Decided (Lead)` and `(Planner)` entry, verbatim — these are the
   rows of the decision review the Owner reads at intake. Quote words; do not paraphrase intent.
3. **Behaviour changes** found versus the brief's pre-accepted list — declared, undeclared,
   and recorded-but-unfixed, each with the commit and whether a downstream unit makes it live.
4. **Structural facts the plan did not anticipate** — a base that moved, a protocol that
   already had what the plan meant to add, a seam that does not exist. Each with file:line at
   the tip and which remaining unit it changes.
5. **Still owed** — every Not verified, Deferred, `unverified` / `blocked` smoke row, comment
   pass not run, and unpublished artifact, with the reason the session gave.
6. **What the next brief inherits** — landmines, invariants to keep enforced (with the grep or
   test that enforces each), verification lanes that worked and ones that are unreachable,
   device findings. One line each, with where the evidence lives.
7. **Follow-ups** — Parked items and pre-existing bugs, as candidate follow-up items: one line,
   the file, and `unrelated` or `structural` per the sizing-the-move rule.
8. **Asks** — anything above that is the Owner's process, preference, or product call.
   Questions, not assertions.

Then one line: READY, or BLOCKED with the asks that gate the next brief. Read-only on every
file except INTAKE.md.
```

The Lead applies §1 and §4–§6 to the plan docs itself, proposes §2(b) to the Owner verbatim,
files §7 however the profile's `lead.intake` duties say follow-ups are filed on this machine
and only when the Owner says so, and carries every §8 item into the report as a question.
`doc-gate` runs on `PROJECT.md` after the edits, before the Owner reads it.
