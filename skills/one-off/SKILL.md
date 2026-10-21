---
name: one-off
description: Plan a one- to three-hour ask in this console, then hand it to one Worker on the cheaper model that builds, reviews and takes itself in with no Lead; you accept it with accept.sh. Type /one-off <ask> in plan mode.
disable-model-invocation: true
---

# One-off

A **one-off** is a project with one unit. You plan it here, in the Owner's console; one Worker
(builder) builds it in its own Robowright Session on the cheaper model; with no Lead (lead), the
Worker's finish review, intake and owner brief take it in; the Owner accepts it with `accept.sh`.
Everything after the plan is the ordinary path — state, ledger, gates, review, accept — so this
skill writes the plan's files and starts the session, and restates none of the handbooks it
calls. Where a step names another handbook, open it and run that step as written there.

Read the reading chain first, as the Planner does (`planner` → "Read the reading chain before
starting anything", passing the checkout): the machine profile's **Launch** and **Paths**, and
the project hook's **Worktree** and **Naming**, are used below. `launch.json` is the one beside
the machine profile.

## 1. Model check

The plan is the Planner's (planner) work, so it runs on the Planner's model: `launch.json` →
`roles.planner.model`, else the Planner's default in the `robowright` skill's roles table. If this
session runs on another model, say so and stop, as `planner` → "Check this session's model first"
does.

## 2. Plan

Run `work-planner` steps 1–5 (`skills/work-planner/SKILL.md:11-69`) on the ask, as written:
destination, grounding, translation, grilling, work order. Plan mode holds through step 4. The
work order you present to leave plan mode is step 5's draft; write it, with the cold start, once
the Owner approves. It goes to the inbox (step 5's rule), and step 5 below moves it.

`work-planner` step 1 sizing an ask as a project ends this skill there: hand the Owner to
`planner`.

## 3. One unit, sized

Apply the first half of `planner` → "Work-order session" step 2: a `Still open` decision goes
back through `work-planner` step 4; an **Approach** of more than one unit is not a one-off —
up to three is `/planner order <work order>`, more is a project (`/planner`). Say which, and end
with the work order on disk.

Label the one unit with a `Size` (`XS`, `S`, `M`) and a `Complexity` (`Low`, `Medium`, `High`).
A unit that sizes `L` or `XL`, or rates `Very High`, is not a one-off either: end the same way.
Step 2's second half does not apply — a unit sized `S` or below still gets a brief, because the
cheaper Worker is the answer to the fixed cost that rule avoids.

**The model rule:** the Worker runs on `sonnet`, or `opus` when the row reads Size `M` or
Complexity `High`.

## 4. Name it

Two words come out of the plan:

- **name** — the project folder, lowercase words joined by hyphens with no three-digit segment
  (`sample`), except on a tracker install (below);
- **ticket** — the one unit, `<name>-001-<unit slug>` (`sample-001-note-autosave`). On an
  install whose `launch.json` sets `unit.ticket_regex`, the ticket is the tracker key the Owner
  gives you, and the name is the ticket itself (`SMPL-482`): its folder is
  `<projects_root>/SMPL-482/`.

Before anything is written, check both against `launch.json`'s `unit` block with bash's
`[[ =~ ]]`, as the launcher reads it. On a slug install: the ticket matches `slug_regex`, and
`group_regex`'s first capture on the ticket equals the name. On a tracker install: the ticket
matches `ticket_regex`; the capture test does not apply, since the name is the ticket. A miss
means choosing the words again and re-running the check; nothing is written until it passes.
Step 6 pre-fills `run.json.project` with the name, and the launcher writes its `group_regex`
capture there only when the field is null — the Worker's Finish finds the folder by that
field. The branch and the Worker's session name follow from the ticket in the forms the
project hook → Naming gives.

`<projects_root>` is `launch.json`'s `projects_root`, else the parent of its `sessions_root`.
If `<projects_root>/<name>/` or `<sessions_root>/<ticket>/` exists, say which and end.

## 5. Write the stub folder

`<projects_root>/<name>/` gets:

- `PROJECT.md` from `templates/PROJECT.md`: the work order's Destination and Why as Context, its
  Language, the one Task Breakdown row (`Unit` the ticket, `Summary`, `Size`, `Complexity`), its
  Decisions as Resolved Decisions;
- `robowright.json` from `templates/robowright.json`, with `models.worker` set by the model rule
  and `repos` naming the checkout the ask is in;
- `DECISIONS.md`, one dated heading holding the work order's Decisions and Rejected;
- the work order and its `<slug>-grounding.md`, moved in from the inbox.

## 6. Write the brief

`<sessions_root>/<ticket>/BRIEF.md` and `run.json`, from the `worker` templates by the table in
`planner` → "Work-order session" step 3. The stub's `robowright.json` is the settings that table
reads. The one-off sets, beyond it:

| Field | Value |
|---|---|
| `shape` | `one-off` |
| `project` | The name — the launcher writes it only on a started launch, and a `paste` launch never `--pin`ned would leave it null; it sets a filled field alone |
| `model` | The model rule; each unit row's `model` blank |
| `rotate_sessions` | `false` |
| `plan_review` | `finish` |
| `delegation` · `robowright` | From the stub: `planner` · its `models` |
| `worktree` row | The full command, by `planner` → "Fill the brief's `worktree` row" |
| `units[0]` | `id` `U1`, the ticket's row, `status` `todo` |

Then `python3 ~/.claude/skills/robowright/scripts/session-state.py <session_dir> status`. An
`INVALID` line is fixed in `run.json` before anything else.

## 7. Doc-gate and ratify

Run `planner` → "A brief's doc-gate" on `BRIEF.md`. The Owner is here, so a `BLOCKED` on asks
only the Owner can answer is asked now: write the answers into `BRIEF.md` and run
`reviewer-docs` again. Then the Owner ratifies the delegation level and the budget rows.

## 8. Worktree and launch

Run the brief's `worktree` command. Then the launcher the profile → Launch names:
`run-launch.sh --run-dir <session_dir> --dry-run`. Its `model:` line must name the model rule's
model `(from brief)`, as in `model: sonnet Worker (from brief)`; anything else is a `run.json`
to fix first. Then the
same line with `--yes`. Under `launch.json`'s `launch: auto` that starts the Worker. Under
`launch: paste` it starts nothing and prints `paste this yourself:` with the line; hand that to
the Owner, and once pasted, `--pin <id>` as the profile → Launch says.

## 9. Hand off

Three lines to the Owner, and end:

1. **Watch:** the roster or the dashboard. A stop waits for you — there is no Lead. Answer it
   in three moves: your answer as the newest `LEDGER.md` entry, headed `Decided (Owner)` (the
   resumed Worker reads it there); `python3 ~/.claude/skills/robowright/scripts/session-state.py
   <session_dir> resume --by owner --decision "<answer>"`; then
   `run-launch.sh --run-dir <session_dir> --resume --yes`. A `rebrief` stop is never resumed:
   `run-launch.sh --planner rebrief --project <projects_root>/<name> --run-dir <session_dir>`,
   dry-run then `--yes`, and the `--rotate` line it prints once `REBRIEF.md` is written.
2. **Read:** the session finishes by writing its own `INTAKE.md` and the owner brief at
   `<projects_root>/<name>/<review_guide_dir>/<ticket>-owner-brief.md`. No owner brief there
   means the guide missed twice: `HANDOFF.md`'s `FIRST ACTION` holds the launcher's dry-run
   line for it; run it, then the same line with `--yes`.
3. **Accept:** the `accept` line the project hook → Publishing names; the core's
   is `~/.claude/skills/lead/scripts/accept.sh --tip <tip> --message <session_dir>/prs/<unit>/commit-message.txt <session_dir>`,
   the squash message the Worker wrote, `<tip>` the full id of the branch tip that was reviewed.
   A one-off has no Lead, so the Owner takes `<tip>` from `git rev-parse refs/heads/<the session's branch>` in the
   main clone, the branch the project hook → Naming gives, and checks it against the tip they reviewed; the
   owner brief and the reviews are session text, not the source of that id.
