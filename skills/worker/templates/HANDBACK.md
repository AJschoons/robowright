# HANDBACK — <slug> → Lead: what downstream inherits

Written at Phase 4 for the Lead (and the next brief's Planner), not for the next Robowright Session.
`HANDOFF.md` says where this one stands; this says what the *plan* has to change because it ran. Every
claim carries a `file:line` at the tip, a SHA, or an evidence path. Under two pages. Name every unit
as `U12 (note-autosave)` (`robowright` → Contracts every role keeps, 11): the Lead and the Explainer
carry these rows to the Owner.

## 1. Read this first

The one to three things that cannot wait: a frozen name the Owner changed in review, a decision
reversed with the Owner's yes, a base that moved. For each, what the plan docs still say
and a per-file count of stale mentions.

## 2. The shipped surface

The public shape of what landed, as code at the tip — the type, its members, its events —
not a description of it. Downstream plans against this block, not against the exploration
doc that predicted it. Name the tip SHA and `run.json.build_output` (or `""`): a later brief's
`depends_on` entry is copied from them.

## 3. Behaviour changes

Against the brief's pre-accepted list: declared, undeclared, and recorded-but-unfixed. For
each unfixed one, the condition under which a later unit makes it live.

## 4. Decisions this Robowright Session answered

| Ref | Question | Answer | Evidence |
|---|---|---|---|

Include `Assumed` ledger entries the Owner should ratify or reverse before the next brief.

## 5. Structural facts the plan did not anticipate

One paragraph each, file:line at the tip, and which remaining unit it changes.

## 6. Still owed

Not verified, deferred, `unverified` / `blocked` smoke rows, unpublished artifacts, comment
pass if not run — with the reason given. These are not done; plan around them.

## 7. What the next unit inherits

Landmines (one line, the file), invariants and the grep or test that enforces each,
verification lanes that worked, surfaces that are unreachable and why, device findings.

## 8. Where the artifacts are

| | |
|---|---|
| `reviews/…` | |
| `evidence/…` | |
| `LEDGER.md` | Every assumption, correction and rejected path, newest last |

## 9. Cost against the last Robowright Session

One line from `run.json.cost`: requests · output tokens · avg context · lines written :
shipped — plus the estimated USD only where the profile → Budget is in dollars — and which
ceilings were hit. The Planner sets the next brief's budget fields and verification ceilings
from this, not from memory.
