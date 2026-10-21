---
name: smoke-test
description: Decide what a set of changes actually needs smoke tested, then run the agent pass and write the manual pass document. Enumerates every user-facing behavior the diff changed or touched, splits it into an autonomous agent lane and a human lane, runs the agent lane in the simulated environment with pre-declared oracles and evidence, and hands the Owner a time-boxed pass/fail/N-A table with a stated reason for every row. Use before opening a PR or a stack, before a release build, when asked what to smoke test, or when a change is too large to eyeball.
---

# Smoke testing a change

Two lanes, in this order, and the order matters:

1. **The agent pass** — first line of defense. Runs unattended in whatever simulated
   environment the project has. Cheap, repeatable, and its only job is to burn down the
   checks that don't need a human, so the human pass isn't spent on them.
2. **The manual pass** — the Owner's confidence pass over a large change. A written document
   with a table they work through: pass, fail, or **N/A**, with a note. Time-boxed,
   risk-ordered, and every row says *why it exists* so they can kill the ones that don't
   make sense.

Both lanes are fed by one thing built first: **the surface inventory**. Skipping straight
to "here are some tests" is the failure mode this skill exists to prevent — it produces a
plausible-looking list that tracks the agent's mental model of the change rather than what
a person can actually see.

## What this is not

Not unit testing (`load-bearing-tests` owns that), not a UI test target, not a release
regression suite. Smoke scope is **"is this build worth a human's attention, and did the
thing the diff claims to do actually happen."** Edge cases, error-state matrices, and
anything a unit test already pins belong somewhere else — putting them here is how a
30-minute pass becomes a 3-hour one nobody runs.

## Deliverables

| File | Who reads it |
|---|---|
| `<out>/INVENTORY.md` | The agent, and the Owner if they question a row |
| `<out>/AGENT-PASS.md` | The Owner — the agent lane's results with evidence paths |
| `<out>/MANUAL-PASS.md` | The Owner — the table they fill in |
| `<out>/evidence/` | Screenshots, tree dumps, log excerpts, named by row id |

`<out>` is `<run_dir>/smoke/` inside a builder run (`worker` in Robowright), otherwise
`<project>/smoke/<TICKET>/`, where `<project>/` is the project folder the profile → Paths
names. All three documents have templates in `templates/`.

Callers that already route here, and what they hand over:

| Caller | Hands over | Gets back |
|---|---|---|
| The builder skill (`worker` in Robowright) Phase 2 step 5 | One unit's `ui`/`behavior` diff | The agent lane, scoped to that unit |
| The builder skill Phase 3 steps 4–6 | The whole stack's diff, plus the brief's `Smoke scope` and `sweep_screens` as a seed | All three documents; the inventory supersedes `sweep_screens` |
| The planner skill (`planner` in Robowright) Phase 6 step 6 | The ticket's diff, plus the exploration doc's §6 seed rows | All three documents |

A seed from a planner is a **guess made before the code existed**. Re-derive from the diff
and say what you added, dropped, or re-prioritized — never just adopt the seed.

---

## Phase 1 — Surface inventory

The unit of the inventory is **a thing a person can observe**, not a file and not a
commit. One changed file can produce four rows or none.

Start from the real diff — `git diff <base>..<head>`, base being the merge-base with the
integration branch, or the stack's base for a stack. Read hunks, not filenames: a
filename-level read cannot tell a copy change from a threading change.

### The four classes

Every non-trivially touched surface lands in exactly one:

- **Changed** — the diff intends a user-visible difference. The check is *did the new
  behavior happen*.
- **Touched** — refactors, moves, extractions, renames that reach a screen. The diff
  intends **no** visible difference, so the check is *is it identical to before*. This
  class is the one agents skip and the one that breaks. A pure-move PR with an
  empty smoke doc is a wrong smoke doc.
- **Blast radius** — not in the diff at all, but downstream of something in it: callers of
  a changed helper, other conformers of a changed protocol, other readers of a changed
  constant or persisted key. Found by walking outward from changed symbols, never by
  reading the diff.
- **No user-facing surface** — dead-code deletion, docs, test-only changes, logging with
  no product consumer. **Name these explicitly with the reason.** A silently dropped file
  and a deliberately excluded one look identical in a list that only shows what's included.

Trivial, and exempt from all of the above: whitespace, formatting, comments, and a rename
the compiler verified end-to-end. Everything else earns a row or an explicit exclusion.

### Change kind → the question it raises

Walk each hunk and ask which of these it is. This table is the whole point of the phase —
it converts "code changed" into "a person could see X":

| The diff does this | User-facing question |
|---|---|
| Adds a screen, control, or state | Does it appear, and does it do the thing |
| Changes copy, a format, a unit | Right text, at long/short lengths, largest Dynamic Type, every locale it ships in |
| Moves or extracts code (pure refactor) | Is the screen exactly what it was — including scroll position, animation, and first-frame |
| Changes a shared helper, extension, or constant | **Every caller is a surface.** The diff shows none of them |
| Changes a model, persisted shape, or cache key | Does an app already installed on the old build still work — migration, not fresh install |
| Changes a network call or response parsing | Empty, error, slow, offline, and partial responses |
| Changes async, threading, or ordering | Where does the UI land when it resolves late, twice, or out of order |
| Adds or changes a feature flag | **Both states**, and a flip while the app is running if that's reachable |
| Changes DI, init, or lifecycle | Cold start, background/foreground, memory warning, re-entry from a deep link |
| Changes navigation or deep links | Each entry point separately, plus back, plus the entry that skips the parent screen |
| Changes a delegate or protocol conformance | Who else conforms, who else calls |
| Deletes code | Is it truly dead — grep for string-based, storyboard, and runtime lookups the compiler can't see |
| Changes analytics or logging | Does the event still fire, with the right payload, exactly once |
| Changes permissions or entitlements | The denied path, on first run |

### The blast-radius walk, bounded

For each changed symbol: find its direct callers (one hop). For anything foundation-level
— a shared extension, a base class, a design-system component, a constant used across
features — go two hops. Stop there and say you stopped; an unbounded walk produces a
hundred rows and gets ignored wholesale, which is worse than thirty good ones.

### Row shape

Each inventory row carries:

- **id** — `S1`, `S2`, … Referenced by both pass documents and by evidence filenames.
- **surface** — screen plus the specific control or state. "Notes list, sort button",
  not "Notes list".
- **class** — changed / touched / blast-radius.
- **what changed** — one clause, pointing at `file:line`.
- **risk hypothesis** — *the specific way this breaks*. "The sort chip reads its title from
  a lazily-built view model that now initializes after first layout, so it could render
  empty on cold start." Not "sorting might not work." This sentence becomes the *why* column
  in the manual doc, and a row that can't produce one is a row that shouldn't exist.
- **priority** — P0/P1/P2 by `reach × blast × cost-of-being-wrong`. P0 is: on the app's main
  path, or can corrupt persisted data, lose user content, or emit wrong analytics. Ordering
  is the entire value of the priority — it is what makes a truncated pass still useful.

---

## Phase 2 — Triage into lanes

One question decides the lane, and it is not "is this hard":

> **Can you write down, right now and before running anything, an observable predicate a
> script could evaluate?**

Yes → **agent lane**. An accessibility-tree predicate, a log line, a network request, a
persisted value, a specific pixel region, a screenshot with a named thing to look for.

No → **manual lane**. Visual quality, animation and timing, gesture feel, "does this look
right", layout judgment at the edges, anything needing real hardware, real accounts, real
money, real location, or a camera.

Neither → **accepted-untested.** Record it with the reason, the same way
`load-bearing-tests` records behavior with no seam. Do not manufacture a check that passes
either way, and do not quietly drop it.

### Observability pre-flight — before any oracle is written

"Can you write a predicate" has a second half: **can the seam you intend to use see the
thing at all?** Answer it per row, up front, from a live tree of the surface (one
`describe-ui` dump per screen, asked about through the `ui-tree-reader` agent — never read
inline):

| Check | If it fails |
|---|---|
| The element carries an accessibility node (an id, a label, or a frame you can name) | `blocked` now, with "no accessibility node" as the reason; the row moves to the manual lane or accepted-untested |
| Its id or label is stable across launches and encodes the state you want to assert | Assert on a different attribute, or `manual` |
| The surface is reachable by deep link or ≤3 taps from one | `blocked` now; do not plan a navigation you have not seen work |
| For `touched` rows, the same node exists on the base build | `unverified` on base is not a baseline; say so before running |

Record the pre-flight's verdicts in `INVENTORY.md`'s lane column. Its point is that a row
which cannot be observed is scoped out **before** the agent lane spends a build, a launch and
three navigation attempts finding out — elements a third-party SDK draws itself, such as a
chart's data points, often carry no accessibility node, and a note saying so does not stop anyone authoring
against them; the pre-flight does.

Two rules that keep the lanes honest:

- **A surface can be in both**, and often should: the agent proves the control exists and
  responds, the Owner judges whether it looks right. The manual row then says "agent already
  confirmed it renders; you're judging the animation" so they know what's left.
- **Anything the agent lane passes with evidence comes off the manual doc**, unless the
  human judgment is genuinely separate. This is the skill's main job: the manual pass
  should be short *because* the agent pass was thorough.

---

## Phase 3 — The agent pass

Runs unattended. The project hook (`PROJECT-HOOK.md`) supplies how to build, launch,
navigate, read the screen, and capture evidence; where the repository builds for a platform with a plugin, that plugin's §1
names the build and its verdicts and its §4 names the device model — how to drive it, read the
screen and lease it (the iOS plugin: `axe describe-ui`, `xcrun simctl`, the simulator lease).

### Oracle first, always

**Write the expected observation into `AGENT-PASS.md` before running the check.** Then run
it. The dominant failure mode in agent-generated testing is the expectation being written
after the observation — the agent navigates, sees a screen, and declares it correct, which
is a tautology dressed as a test. A pre-declared oracle that turns out to be wrong is a
finding; a post-hoc one is nothing.

### Baselines for the `touched` class

"Nothing changed" cannot be proven on the tip build alone. For every `touched` row, run the
identical check on a **base build** and compare. Same device, same account, same seed
state. A predicate that holds on base and fails on tip is a defect. A predicate that fails
on both is pre-existing — report it as such, don't fix it here, and don't count it against
the change.

This is the smoke-test analogue of the mutation loop in `load-bearing-tests`: a check that
would have passed before the change, and still passes, proved nothing about the change.

### Verdicts — six, and never collapsed to two

| Verdict | Means |
|---|---|
| `pass` | Oracle held, evidence captured |
| `fail` | Oracle did not hold on tip |
| `pre-existing` | Failed on base too |
| `blocked` | Could not reach the surface (nav failed, gated by an account or flag) |
| `infra` | Build, simulator, or harness broke |
| `unverified` | Ran, but produced no artifact that settles it |

**`blocked`, `infra`, and `unverified` are not passes.** Rolling them up as "no issues
found" is the false-green this whole document is built against. The agent pass
report leads with the count of rows that are *not* `pass`, before the count that are.

### Evidence, by path

Every verdict names its artifact under `evidence/<row-id>-<step>.<ext>` — a screenshot,
a tree dump, a log excerpt with the surrounding lines. A claim with no artifact is
`unverified`, however confident the prose. Screenshots get **looked at**, not just
captured; a saved PNG nobody read is a file, not evidence.

### Budget, and when to stop

- **20 checks is a large agent pass.** More than that means Phase 2 sent manual-lane work
  down the agent lane.
- **Three attempts to reach a surface**, then `blocked` and move on. Do not debug the app's
  navigation inside a smoke run.
- **Do not fix anything.** Finding a defect ends that row and gets reported; it does not
  start a repair. The one exception is a harness problem (wrong build installed, sim not
  signed in) — fix that and re-run, and say you did.
- Total wall-clock budget belongs in the run's config. If it blows, report what was covered
  and what wasn't, ranked — never silently truncate.

---

## Phase 4 — The manual pass document

The deliverable. Written from `templates/MANUAL-PASS.md`.

### Time box first, rows second

Pick a tier up front, state it and the reason at the top of the doc, and **fit the rows to
it**. The tier drives the row count, not the other way around.

| Tier | Budget | Rows | When |
|---|---|---|---|
| **Quick** | ~10 min | 4–6 | One PR, one surface, agent pass all-green |
| **Standard** | 25–35 min | 10–18 | A normal PR touching a couple of screens; the default |
| **Deep** | 60–90 min | 18–25 + one charter | A stack, a rearchitecture, a flag flip, or anything with a `touched` class bigger than the `changed` one |

The floor and ceiling are not arbitrary: a smoke suite that can't finish in well under an
hour stops being run, and unbroken manual exploration past ~90 minutes is fatigue, not
coverage — the session-based-testing literature converges on 45–90 minutes for the same
reason.

**If the rows exceed the tier, cut rows — never compress steps.** A row squeezed into "also
check the other three screens" is a row that gets skipped. Cut from the bottom of the
priority order and list what was cut in a **"deliberately not testing"** section with the
reason. That section is what makes the doc safe to trust: it shows the judgment, not just
the result.

**Deep tier adds a charter**, not more rows — one time-boxed exploratory session aimed at
the riskiest area, in the form *"Explore \<target\> with \<specific inputs or conditions\>
to discover \<the class of problem\>."* Scripted rows find the breaks you predicted; the
charter is where the unpredicted ones come from.

### Ordering

**Risk-order the groups, screen-order within a group.** Pure risk ordering makes the Owner
bounce between screens and burns the budget on navigation; pure screen ordering buries the
P0 behind setup. Group by screen, sort the groups by their highest-priority row.

The doc must be **truncation-safe**: stopping after any row leaves the most important
things already covered. Say so explicitly at the top — "stop whenever; it's ordered so
what's left is the least important."

### The rows are a task list, not a table

**This is not a style choice.** The Owner works the pass in a Markdown editor and taps the
boxes; Typora is the one measured. A checkbox
is only tappable when it is a real list item at block level — table cells are parsed inline,
so list syntax never applies inside one and `- [ ]` in a cell is literal text
([typora-issues#2659](https://github.com/typora/typora-issues/issues/2659)). Typora, GitHub,
GitLab and Obsidian all toggle real task items on click. So: **a flat task list per row.**

```markdown
**1 · Notes list, compact layout** · 8 min · [S1](INVENTORY.md)
Compact flag on. Force-quit. Cold launch → Notes. Look at the bottom of the list **before scrolling**.
**Expect** the compose button, the count footer and the search field all sit above the keyboard toolbar.
**Why** the inset now reads the toolbar's live height before layout, so it can be 0.

- [ ] pass
- [ ] fail —
- [ ] n/a —
```

- **Three boxes, flat, never nested.** Nesting a task list under a task item after
  intervening paragraphs is where Typora's renderer drops checkboxes
  ([#643](https://github.com/typora/typora-issues/issues/643)); a flat list at block level
  always works. Keep `fail` and `n/a` separate — collapsing them loses the n/a rate that
  Phase 5 prunes the inventory with.
- **`fail —` and `n/a —` carry a trailing dash on purpose**: both outcomes owe a written
  reason, and the dash is the prompt. `pass` needs none.
- **The row header line** is `**<n> · <area>** · <min> · <link to the inventory row>`.
- **do** — exact, executable steps, one line. "Cold launch, Notes tab, tap Sort, pick
  Date." Not "verify sorting works."
- **Expect** — one observable outcome. If a row needs three, it is three rows.
- **Why** — the risk hypothesis, **one clause, under ~15 words**. This is what makes the n/a
  box usable: the Owner can only correctly dismiss a row if they can see the reasoning that produced
  it. The full hypothesis lives in `INVENTORY.md` under the row id the header links to. If
  the clause cannot be short, the hypothesis is doing two jobs and the row should be two rows.

Never use `<input type="checkbox">` to fake a tappable box inside a table. Most renderers
strip it, none persist a click back to the file, and Typora is one of the ones that strips it.

### The plan table

A task list is long, so lead the section with a **read-only index** — no boxes — so the whole
pass and its budget are visible at a glance without scrolling past 100 lines of checklist:

| # | Area | ~min |
|---|---|---|

Risk-ordered, same order as the rows, summing to the tier budget. It is a table of contents,
not a place to record anything.

### The header block

Above the table, in this order, because a pass that begins with ten minutes of setup
guesswork does not get run:

1. **The one thing** — a single line: if they do nothing else, this is the check.
2. **Setup** — build/branch, device and OS, account and tier, flags on/off, seed state,
   network condition, anything to reset first.
3. **What the agent pass already covered** — with its verdict counts, so they aren't
   re-checking settled ground. Link `AGENT-PASS.md`.
4. **Tier and budget**, with the one-sentence reason for the tier.
5. **Deliberately not testing** — the cut list.

### Feature-flag changes

A flag gets a two-column matrix (off / on) on the rows where behavior diverges, not two
separate tables. **Flag-off rows are `touched`-class regression rows** and are usually the
higher priority: the on state is what everyone remembers to check.

---

## Phase 5 — Reconcile

After the Owner works the doc:

1. **Every `Fail` gets triaged** — reproduce, locate, and either fix or file. A fail with no
   follow-up is the doc lying to the next reader.
2. **Read the `N/A` rows back.** They are the highest-value feedback in the process: each
   one is a place the inventory over-generated. Fold the reason into the next run's
   exclusions.
3. **Watch the N/A rate.** Over ~30% means Phase 1 is generating rows from code structure
   instead of observable behavior — usually the blast-radius walk running too wide, or rows
   with a weak risk hypothesis. Tighten the hypothesis requirement before adding more rows.
4. **The completed doc is PR-description material.** The enumerated pass — "scroll → reload,
   note / folder / tag selection, preview toggle" — is worth more to a reviewer than the
   words "smoke tested."
5. **Decision log entry** in the decision-reporting shape the Owner's own rules give, when
   the machine has them: what was deliberately not tested, and why.

---

## Anti-patterns

Rows that should never appear in a manual pass document:

- **"Verify the app launches."** If it didn't, nothing below it matters and they'd know.
- **Anything a unit test pins.** If it's checkable without a screen, it's not smoke scope
  — send it to `load-bearing-tests` instead.
- **Edge-case matrices.** Five input-validation rows is a test suite wearing a smoke doc's
  clothes.
- **Rows with no observable difference.** If passing and failing look the same, it isn't a
  test. Delete it or make it a manual judgment row with an honest "look at X."
- **Rows the agent lane already proved,** restated for thoroughness.
- **"Regression test the whole feature."** Not a row. Either name the screens or admit the
  change is too big to smoke and needs a real regression pass.
- **A row whose *why* is "this file was modified."** That's the inventory, not a reason.

## Project hook

Everything naming a build command, a device, a deep link, an account, or an evidence path
lives in `PROJECT-HOOK.md` — read it at the start of Phase 3. With no hook available, the
agent lane degrades to whatever the environment offers and says so in `AGENT-PASS.md`;
it does not quietly skip to the manual doc.
