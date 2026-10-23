# Dashboard — test ledger

Commit ids in this record refer to the project's history before it was published; they are not in this repository.

Each dated entry keeps the words of its day: "landed" and "Ready to land" are now "complete" and "Awaiting
acceptance" (U43).

Rows in `BEHAVIORS.md`. Every mutation below was a literal text replacement applied to
`tools/robowright-dash.py`, the whole suite run, and the file restored from a copy of the commit;
`git status` was clean after the pass. Predictions were written before each run; a round applies
its mutations together, so each round's predicted sets are disjoint. Run 2026-09-26.

Run: `python3 tests/dash/test_dash.py` (about 3 s)

Red at the spec commit: 29 of 29, the script absent — so the red proved nothing about the Thens, and
every test owed a kill below.

| # | round | mutation | predicted | observed |
|---|---|---|---|---|
| A | 1 | `--runs-root` never passed to the roster | R3.1, R3.7, R4.3, H3 | match |
| B | 1 | the roster gets no reason for an unread launch.json | R2.1 | match |
| C | 1 | `$ROBOWRIGHT_PROJECTS_ROOT` ignored | R3.4 | match |
| D | 1 | the `review_guide` alias dropped | R5.3 | match — shared with T's wider set; J kills R5.3 alone of the alias |
| T | 1 | every finished session reads as in main | R6.2, R6.3 | wider: also R5.1 — a done session read as landed is never held |
| V | 1 | a home-directory path in a comment | R7.1 | match |
| E | 2 | the gaps file back beside the script | R4.1, R4.2, R4.3, R4.4 | match |
| G | 2 | the old branch prefix tried first | R6.2 | match |
| I | 2 | `owner_brief: false` falls through to the alias | R5.5 | survived — masked by J, which changed the phrase R5.5 looks for; re-run in round 3 |
| J | 2 | the hold's phrase back to the old wording | R5.1, R5.3 | match |
| F | 3 | no accounting root writes the gaps file into the cwd | R4.3, H3 | match |
| H | 3 | the branch prefix is not `robowright/` | R6.1 | match |
| L | 3 | the projects default is the sessions root itself, not its parent | R3.6, R3.7 | match |
| I | 3 | as round 2, alone of the phrase | R5.5 | match |
| M | 4 | launch.json's `projects_root` ignored | R1.1, R3.2, R3.5, R5.1, R5.3, R6.1, R6.2, R6.3, H2 | wider: also R1.2 (its `~/` projects root is launch.json's). Narrower: not R3.2 — its session prints as a no-project row either way |
| N | 4 | `--once` goes on without a sessions root | R2.3 | match |
| M2 | 5 | launch.json's `projects_root` read without `~/` expansion | R1.2 | match |
| P | 5 | an unread reason defaults to `no such file` | R2.2 | match |
| Q | 5 | `--projects-root` ignored | R3.3 | match |
| S | 5 | the owner brief's file name not recognised | R5.2 | match |
| U | 5 | no guard on a missing roster path | H1 | match |

28 of 29 killed. **R3.2 is a declared guard** (its docstring): the env-over-launch.json order lives in
`run-roster.py`'s `sessions_roots`, outside this file; the guard protects against the dashboard
resolving its sessions root itself. The mutation not run, at the five-round ceiling: in
`run-roster.py`'s `sessions_roots`, read `launch_path(settings, "sessions_root")` before the
environment — predicted R3.2 here, and the roster's own R2 rows.

## U2

Same method, on the implementing commit. The U2 rows are `U2-R…` in `BEHAVIORS.md`. Red at the spec
commit: 20 of the 28 new tests failed on their Then. Eight were already green (R1.3, R1.5, R1.7, R1.8,
R3.4, R4.3, R4.4, R5.4), so each owed a kill here. M20 mutates `skills/planner/PROJECT-TEMPLATE.md`,
not the script.

| # | round | mutation | predicted | observed |
|---|---|---|---|---|
| M1 | 1 | the purpose ignores Summary | R1.1, R1.2 | match |
| M2 | 1 | the guard no longer blanks the purpose under a Summary header | R1.6, R1.7 | match |
| M3 | 1 | unit-scope records relabelled session scope before the rollup | R2.1, R2.3 | match |
| M4 | 1 | the oldest plan review instead of the newest | R4.2 | match |
| M5 | 2 | an unpriced estimate prints `0.00` | R2.5 | match |
| M6 | 2 | a card sums every ticket of its project | R2.2 | match |
| M7 | 2 | the "no ledger" note dropped | R3.1, R3.2 | match |
| M8 | 2 | `- ` bullets not counted as asks | R5.2 | match |
| M9 | 3 | a table's header row counted as an ask | R5.1, R5.3 | match |
| M11 | 3 | `has_ledger` always false | R3.4, R2.3 | match |
| M12 | 3 | ledger lines parsed strictly instead of by `read_records` | R3.3 | match |
| M13 | 3 | unpriced records dropped before the sum | R2.5, R2.6 | narrower: not R2.6, which asserts only the estimate, and dropping its null record leaves `0.40` |
| M10 | 4 | asks read from the whole brief instead of `## Decide now` | R5.1 | wider: also R5.2, R5.3, whose fixtures carry rows or bullets in later sections |
| M22 | 4 | one unpriced record makes the whole estimate unpriced | R2.6 | match |
| M16 | 4 | the cell-count guard fires only on a long row | R1.5, R1.6, R1.7 | match |
| M21 | 4 | every record counted as its own Claude session | R2.4 | match |
| M17 | 5 | the purpose is the Summary cell only, whatever the header | R1.3, R1.4, R1.8 | match |
| M18 | 5 | a card with no plan review shows a `none` verdict | R4.3, R4.4 | match |
| M19 | 5 | no owner brief reads the same as an empty one | R5.4 | match |
| M20 | 5 | the template header back to eight columns | R6.1, R6.2 | narrower: not R6.2, which counts each row's cells against nine, not against the header |

27 of 28 killed. **R6.2 is a declared guard** (its docstring). It protects the template against an
example row without its Summary cell. The mutation not run, at the five-round ceiling: delete U1's
Summary cell in `PROJECT-TEMPLATE.md`, predicted to redden R6.2 alone.

R2.7 was added after the U2 gate's finding F1: a session with no ticket put `None` in the project's ticket
set, so every `unit: null` record, whatever its project, joined the project's spend. Its baseline is the
unfixed tree, `88e8ff7`'s `{ticket_of(s) for s in sessions}`. It went red there on its Then, reading
`70 requests` where 20 was expected, and it passes with the fix. That baseline is its kill: 28 of 29 U2
tests killed, and R6.2 declared.

## End of stack

R4.5 was added after the end-of-stack review's F1: loading the clone's scripts by path let Python
write their bytecode beside them, so a run wrote `__pycache__` into the clone's `skills/`. Its
baseline is the unfixed tree, `d0c497f`: it went red there on its Then, with four clone `.pyc`
files under the scratch prefix (`evidence/eos-F1-red.log` in the session dir), and it passes with
`sys.dont_write_bytecode` set before the loads. That baseline is its kill.

## P1

Red at the spec commit: 3 of 5 on their Thens (P1-R1.1, P1-R2.1, P1-R2.2). P1-R3.1 and P1-R4.1 were
green there, the singular and the `isinstance` guard already in place, so each owed the kill below.
One mutation per rule, each applied alone, predictions written before the runs. Run 2026-09-27.

| # | mutation | predicted | observed |
|---|---|---|---|
| N1 | the project line sums its sessions' tickets again, not the rollup's `project` row | P1-R1.1 | match |
| N2 | the "Nothing" / "None" filter dropped | P1-R2.1, P1-R2.2 | match |
| N3 | the count's singular dropped | P1-R3.1 | match |
| N4 | `verdict_line`'s `isinstance` guard dropped | P1-R4.1 | match |

5 of 5 killed.

## P3

Red at the spec commit: 9 of 16 on their Thens (P3-R1.1, R1.4, R1.5, R2.1, R3.1–R3.5). P3-R1.2, R1.3 and
R4.1–R4.4 were green there, the tree always showing dollars and never a plan-usage line, so each owed the kill
below. The U2 and P1 spend rows run under `DOLLAR_BRIEF`, a Given change; none of their Thens moved. The Owner amended rule 2
to "every" before the implementing commit: P3-R2.2's Then flipped (a mixed project shows no dollars) and red against
the "any" implementation; P3-R2.3 and R2.4 were added, green there, and owe M2.d and M2.c. Every mutation below ran
against the "every" implementation. One or two
literal replacements per mutation, each applied alone, predictions written before the runs. Run 2026-09-27.

| # | mutation | predicted | observed |
|---|---|---|---|
| M1.a | the card always shows dollars | P3-R1.1, R1.4, R1.5 | match |
| M1.b | the card's dollars follow the project's any-limit | P3-R1.1 | match |
| M1.c | only `spend_threshold_usd` counts | P3-R1.2 | match |
| M1.d | truthiness in place of `number(...) is not None` | P3-R1.3 | match |
| M1.e | key presence in place of `number(...)` | P3-R1.4 | match |
| M1.f | an unpriced line prints `est usd n/a` whatever the limits | P3-R1.5 | match |
| M2.a | the project line always shows dollars | P3-R2.1, R2.2, R2.4 | match |
| M2.b | any of the project's sessions instead of every | P3-R2.2 | match |
| M2.c | the at-least-one-session guard dropped | P3-R2.4 | match |
| M2.d | every session anywhere, not only the project's | P3-R2.3 | match |
| M3.a | `$CLAUDE_USAGE_DIR` ignored | P3-R3.1, R3.2, R3.4, R3.5, R4.4 | match |
| M3.b | the `~/.claude/usage` fallback ignored | P3-R3.3 | match |
| M3.c | the line on the index only | P3-R3.2 | match |
| M3.d | the line on project pages only | P3-R3.1, R3.3, R3.4, R3.5 | match |
| M3.f | an absent window prints | P3-R3.4 | match |
| M3.g | an absent `captured_at` prints as `as of None` | P3-R3.5 | match |
| M3.h | the line gated on the billing rule | P3-R3.1–R3.5 | match |
| M4.a | the no-reading guard dropped | P3-R4.1–R4.4 | match |
| M4.b | the guard is "all three None" | P3-R4.3 | match |
| M4.c | the dashboard reads `latest.json` itself, catching only `OSError` | P3-R4.2 | match |
| M4.d | a missing tap directory renders a `no tap` line | P3-R4.1 | match |
| M4.e | falls back to `~/.claude/usage` when `$CLAUDE_USAGE_DIR` has no reading | P3-R4.4 | match |

18 of 18 killed. P3-R3.1 has no single-row kill: each property it pins is shared with an index row (R3.3–R3.5) or
an env row (R3.2, R3.4, R3.5, R4.4); it reddens under M3.a, M3.d and M3.h.

## F1

What the tap writes: `skills/robowright/scripts/usage-tap.py:67` writes `"captured_at": int(time.time())`, epoch
seconds as a JSON integer, and run-cost.py's `plan_usage()` hands it back untouched. The accepted shapes follow: an
int or float of seconds, and an ISO-8601 string, which is what P3's fixtures used.

Viewer toggle: nothing per group is stored per viewer. Under `--serve` the page script's in-place refresh records
every `details[id]`'s `open` and re-applies it to the fresh page, so a viewer who closes Quiet keeps it closed while
the server's default says open, and the other way round. The default therefore applies on a full load only: every
`--once` reload (file://), the first served load, a browser reload. A served index left open keeps Quiet as it was
when a session goes live or ends, until the next full load. No Python-observable seam, so no test.

Red at the spec commit `336d62c`: 15 of the 17 rows on their Thens (F1-R1.1–R1.11, F1-R2.1, P3-R3.1–R3.3, whose time
Then moved with F1 rule 1). F1-R2.2 and R2.3 were green there, and owed K13 and K14. One mutation each, applied alone,
predictions written before the runs (`evidence/fixes-F1-mutation-plan.md` in the session dir). Run 2026-09-27.

| # | mutation | predicted | observed |
|---|---|---|---|
| K1 | an int of 10^9 or more read as milliseconds | F1-R1.1 | match |
| K2 | a float is not accepted | F1-R1.2 | match |
| K3 | an ISO string shown in its own offset, not the local zone | F1-R1.3, P3-R3.1, R3.2, R3.3 | match |
| K4 | an ISO string with no offset read as UTC | F1-R1.4 | match |
| K5 | zero dropped (strictly positive guard) | F1-R1.5 | match |
| K6 | the bool guard dropped | F1-R1.6 | match |
| K7 | an unparseable string printed raw | F1-R1.7, R1.11 | match |
| K8 | the negative guard dropped | F1-R1.8 | match |
| K9 | `OverflowError` not caught | F1-R1.9 | match |
| K10 | NaN passes the guard and `ValueError` is not caught | F1-R1.10 | match |
| K11 | a numeric string coerced to epoch seconds | F1-R1.11 | match |
| K12 | Quiet never starts open | F1-R2.1 | match |
| K13 | Quiet always starts open | F1-R2.2, R2.3 | match |
| K14 | Quiet opens when no project has a non-terminal session, not on the empty-cards branch | F1-R2.3 | match |

14 of 14 F1 rows killed, each by a mutation whose red set was exactly the predicted one; 11 of the 14 by a mutation that reddens that row alone. F1-R1.3 has no
single-row kill: P3-R3.1–R3.3 read ISO strings with an offset too, the same property. F1-R1.7 shares K7 with R1.11,
which K11 kills alone. F1-R2.2 shares K13 with R2.3, which K14 kills alone.

After the F1 gate's HOLD (its F1): an ISO string whose instant falls outside the local range crashed the page, since
only the numeric path sat inside a `try`. F1-R1.12 and R1.13 were added and went red on `3e12b21` on their Then (exit 1,
an OverflowError and a ValueError traceback; `evidence/fixes-F1-gatefix-red.log`); the string path now has its own
`try`. All mutations re-ran alone against the fixed tree, predictions first (`evidence/fixes-F1-mutation-plan.md`);
K1–K14 matched again, K3 now reddening R1.12 too, and:

| # | mutation | predicted | observed |
|---|---|---|---|
| K15 | `OverflowError` not caught on the string path | F1-R1.12 | match |
| K16 | `ValueError` not caught on the string path | F1-R1.13 | match |

After the F1 gate's F2 (one mutation that reddens exactly its row, for each row), two solo kills, run in the same pass:

| # | mutation | predicted | observed |
|---|---|---|---|
| K17 | an unparseable string with a letter in it printed raw | F1-R1.7 | match |
| K18 | Quiet opens when any project has a live session, else on the empty-cards branch | F1-R2.2 | match |

16 of 16 F1 rows killed; 18 mutations, every red set exactly the predicted one; 15 of the 16 rows by a mutation that
reddens that row alone. F1-R1.3 alone has none: every mutation of the offset-to-local path also reddens F1-R1.12 and
P3-R3.1–R3.3, which read offset strings too.

## 023-U1

Red at the spec commit `ddbe9a7`: 8 of the 14 rows on their Thens (F1.1–F1.4, F2.1, F3.1, F6.1, F6.2; `FAILED
(failures=8)`, no errors). F4.1, F4.2, F5.1, F5.2, F7.1 and F7.2 were green there, the behaviour already holding, and
owed a kill each. One mutation at a time, applied alone to `tools/robowright-dash.py` at `568ab49`, the whole suite run,
the edit reverted by its inverse; predictions written before the first run; `git status` clean after the last.
Run 2026-10-12.

| # | mutation | predicted | observed |
|---|---|---|---|
| K1 | `follow_up_for` never consulted (`follow_up = None`) | F1.1, F1.2, F1.3, F1.4, F2.1, F3.1, F6.1, F6.2 | match |
| K2 | the Explainer check dropped (`explainer = None`) | F3.1, F6.1 | match |
| K3 | the Planner and Lead prefix skip dropped | F4.1, F4.2 | match |
| K4 | the worktree match dropped | F2.1 | match |
| K5 | the `busy` filter dropped | F5.1 | match |
| K6 | the `tone == "done"` guard dropped | F5.2 | match |
| K7 | `EXPLAINER_PREFIX` a literal `"explainer"` | F6.1, F6.2 | match |
| K8 | the follow-up block placed after the activity scan | F1.4 | match |
| K9 | `live_agents` also reads a cwd-relative `.claude/sessions` | F7.1 | match |
| K10 | `is_alive` dropped from `live_agents` | F7.2 | match |

14 of 14 rows killed; 10 mutations, every red set exactly the predicted one; 6 of the 14 by a mutation that reddens
that row alone (F1.4, F2.1, F5.1, F5.2, F7.1, F7.2). F4.1 and F4.2 share the prefix skip (K3); F1.1, F1.2 and F1.3
rest only on `follow_up_for` being consulted (K1); F3.1 and F6.1 share the Explainer check (K2), F6.1 and F6.2 the
prefix read (K7).

## 023-U2

Red at the spec commit `ea02f92`: 11 of the 18 rows on their Thens (B1.1, B1.2, B3.1, B4.1, B5.1–B5.3, B6.1–B6.4;
`FAILED (failures=11)`, no errors). B2.1–B2.4, B7.2, B8.1 and B8.2 were green there, the behaviour already holding,
and owed a kill each. One mutation at a time, applied alone to `tools/robowright-dash.py` at `287ffaa`, the whole
suite run, the file restored; predictions written before the first run; `git status` clean after the last.
Run 2026-10-13.

| # | mutation | predicted | observed |
|---|---|---|---|
| K1 | `run.json.project` not read (`filed_under` returns the capture) | B1.1, B1.2, B3.1, B4.1 | match |
| K2 | the capture fallback dropped in `filed_under` | B2.1, B2.2, B2.3 and every row whose session has no `project`; not B2.4 | match (61 red) |
| K3 | `pending_session` files by `run.get("project")` | B2.4 and the direct-build rows | B2.4 alone: no row asserts the page a direct build is filed on |
| K4 | the ticket match dropped (`ticket_claims` returns `{}`) | B4.1, B5.1, B5.2, B5.3 | match |
| K5 | a session ticketed to another row falls through to the name rule | B5.2, B5.3 | match |
| K6 | `lead_stage` reads a literal `reviews` | B6.1, B6.3 | match |
| K7 | the Decide-now read uses a literal `reviews` | B6.2, B6.4 | match |
| K8 | `CONFIG.get("review_guide_dir", "reviews")` (an empty value kept) | B7.2 | match |
| K9 | the name rules dropped from `sessions_for` | B8.1, B8.2 and earlier rows that read a unit's sessions | match (10 red) |
| K10 | `filed_under` without the string check | B2.3 | match |
| K11 | ticket claims built row by row | B5.3 | match |
| K12 | the ticket compared to the stripped unit name | B5.1, B5.2, B5.3; B4.1 survives | match |
| K13 | claims walk `plan_units`' Detailed TODO order, not table order (the tree before the gate fix) | B5.4 | match (scoped to `TicketClaim`) |

19 of 19 rows killed; 13 mutations, 12 red sets exactly the predicted one, K3 narrower (above). B5.4 was added at
the gate: its red is its run against the pre-fix tree. B7.1 (no key means
`reviews`) is a declared guard carried by R5.1–R5.5 and U2-R5.1–R5.4, which run with no `review_guide_dir`.

## prepub-3

Red at the spec commit `03089ee`, run against `9a127e5`'s dashboard: 6 of the 7 rows on their Thens (H1.1–H1.3,
H2.1, H3.1, H3.2; `FAILED (failures=6)`, no errors). H2.2 was green there, loopback already served, and owed a kill.
One mutation at a time, applied alone to `tools/robowright-dash.py` at the implementation, the dashboard suite run,
the file restored; predictions written before the first run; `git status` clean after the last. Run 2026-10-13.

| # | mutation | predicted | observed |
|---|---|---|---|
| K1 | `count` returns its value unchecked | H3.1, H3.2 | match |
| K2 | `wall` reads `max_wall_hours` raw | H3.1 | match |
| K3 | `run_unit_dot` reads `max_gate_attempts` raw | H3.2 | match |
| K4 | `unit_phrase` prints `max_gate_attempts` raw | H3.2 | match |
| K5 | the Host check removed | H2.1 | match |
| K6 | the Host compared without lowering its case | H2.2 | match |
| K7 | no Host allowed | H2.2, H1.3, every earlier `--serve` GET | match: H2.2, H1.3, `GapsFile`'s serve row |
| K8 | the `--once` link not URL-quoted | H1.1, H1.2 | H1.2 alone: the HTML escape at the href keeps the attribute inert |
| K9 | the `--once` link quoted with `safe='" ='` | H1.2 | match |
| K10 | `project_link` not URL-quoted | H1.3 | match |
| K11 | `e()` returns its value unescaped | H1.1 | match: the project page's `data-title` |
| K12 | K8 plus the quiet row's href unescaped (both layers off at one link) | H1.1, H1.2 | match |

7 of 7 rows killed; 12 mutations, 11 red sets exactly the predicted one, K8 narrower (above). K8 against K12 shows
each layer of the link carries weight: the URL quote alone is H1.2's, the HTML escape is what keeps H1.1 green when
the quote is gone.

H1.4 and H3.3 came from review 1 (findings 3, then 1 and 2). Red at their spec commit `f133564` against the
implementation before the fix: H1.4 on its escape assertion, H3.3 on all three subtests (NaN and Infinity drew a
meter, `10**400` crashed the render). Same procedure, run 2026-10-13.

| # | mutation | predicted | observed |
|---|---|---|---|
| K13 | `count` drops its `isfinite` check | H3.3 | match (3 subtests) |
| K14 | `count` lets `OverflowError` through | H3.3 | match (the `10**400` subtest) |
| K15 | `planner_line` writes the status unescaped | H1.4 | match |

9 of 9 rows killed; 15 mutations.

H3.4 came from review 2 (finding 2: nothing killed `count`'s bool check). Red against `9a127e5`'s dashboard on its
meter assertion (`true or 0` drew a one-hour meter there); green at `72c02b9`.

| # | mutation | predicted | observed |
|---|---|---|---|
| K16 | `count` accepts a bool | H3.4 | match |

10 of 10 rows killed; 16 mutations.

## dash-brand

Rows B1.1–B5.1 in `BEHAVIORS.md` § dash-brand. Red at the spec commit `6c6cdea`, against `f950c93`'s dashboard: 7 of
8 red. B3.2 failed as an error, because there was no favicon to decode, so its assertion is proven by K5. B5.1 was
green, because it guards the title this change keeps; K8 kills it. Each mutation below was applied alone, the dash
suite was run, and the file was restored from a copy. `git status` held only the implementation. Run 2026-10-14.

| # | mutation | predicted | observed |
|---|---|---|---|
| K1 | Blueprint's `brass` is `#FFFFFF` | B1.1 | match |
| K2 | `MARK` loses `aria-hidden` | B2.1 | match |
| K3 | the triangle's path left in the footer | B2.2 | match |
| K4 | `FAVICON` is `/favicon.svg` | B3.1, B3.2 | match |
| K5 | `FAVICON` keeps `var(--brass)` | B3.2 | match |
| K6 | the project page's wordmark is `Robowright` | B4.1 | match |
| K7 | `.brand` dropped from the mono `font-family` rule | B4.2 | match |
| K8 | the index title is `robowright` | B5.1 | match |
| K9 | the ring filled with `var(--bg)` | B2.1, B3.2 | match |

8 of 8 rows killed; 9 mutations, every red set exactly the predicted one.

Review 1 found that `drawing()` compared only each shape's colours, so a mark scaled or resized away from the art stayed
green. It now compares every shape attribute, the `<svg>`'s viewBox and the `<g>`'s transform. With K10 applied, the
previous tests were green; with the fix, both rows are red.

| # | mutation | predicted | observed |
|---|---|---|---|
| K10 | the mark's group `scale(1.6)` | B2.1, B3.2 | match |
| K11 | the ring's `r="90"` | B2.1, B3.2 | match |

8 of 8 rows killed; 11 mutations.

## 029-U1

Rows 029-U1.1.1–029-U1.9.4 in `BEHAVIORS.md` § 029-U1, 38 tests. Red at the spec commit `8b6b8ee`, against `b02d51f`'s
dashboard: 36 of 38 red, every failure an assertion. 7.2 was green, because it guards an attribute the row already
escaped; P1 kills it. 8.2 was green, because it pins the In flight dot's offset this change keeps; T4 kills it. Each
round applied up to four mutations on distinct statements with disjoint predicted sets, ran the dash suite, and
restored the file with `git checkout`. `git status` was clean after each. Run 2026-10-14.

| # | round | mutation | predicted | observed |
|---|---|---|---|---|
| F3 | 1 | `figure_role` drops the Lead tones | 2.5–2.8, 5.2, 9.2, 6.1, 6.3 | match |
| T1 | 1 | Whiteprint's token is `note-gold` | 1.1, 1.3 | match |
| P1 | 1 | `render_attention` loses the ` g` class and adds an unescaped `data-p` | 4.1, 7.2, Hostile attribute tests | match |
| P3 | 1 | Ready to land rows carry the Lead | 4.4 | match |
| F2 | 2 | `figure_role` drops `stopped` from the Owner tones | 2.2, 3.1, 3.2, 5.3, 9.1, 9.3, 9.4, 6.2 | match |
| F4 | 2 | `figure_role` drops the Planner tones | 2.9, 2.10, 5.2, 9.2 | match |
| T2 | 2 | Needs attention keeps `--brass` | 1.2 | match |
| P2 | 2 | `flight_row`'s last return loses the ` g` class and spaces the glyph | 4.2, 4.3 | match |
| F6 | 3 | `figure_role` tests `phase != "end-of-stack"` | 2.12–2.14, 5.2, 9.2, 6.1–6.3 | match |
| F5 | 3 | a direct build returns the Lead | 2.11 | match |
| T3 | 3 | the glyph row's dot sits at `42px` | 8.1 | match |
| H1 | 3 | the glyph's `<svg>` carries the project, unescaped | 7.1 | match |
| F1 | 4 | `figure_role` ignores the stop file, `unknown` and `owner-call` | 2.1, 2.3, 2.4 | match |
| A1 | 4 | `robot_drawing` leaves the brass ink unpainted | 5.1, 5.2 | match |
| T4 | 4 | the In flight dot sits at `8px` | 8.2 | match |
| P4 | 4 | the session page's summary draws a glyph | 4.5 | match |

38 of 38 tests killed; 16 mutations in 4 rounds, every red set exactly the predicted one. The `kind == "direct"` line
returns what the default would, since a direct build is never `end-of-stack`; F5 pins it by changing its return.

## 029-U2

Rows 029-U2.1.1–029-U2.13.2 in `BEHAVIORS.md` § 029-U2, 72 tests. Red at the spec commit `9f1442b`, against U1's
dashboard: 71 of 72 red, every failure an assertion. 10.1 was green, because `/attention.json` is unchanged by rule;
J kills it. Each round applied four mutations on distinct statements with disjoint predicted sets, ran the dash suite,
and restored the file with `git checkout`. `git status` was clean after each. Run 2026-10-14.

| # | round | mutation | predicted | observed |
|---|---|---|---|---|
| P | 1 | the crew card renders after Needs attention | 1.1, 1.2 | match |
| C | 1 | the crew CSS block deleted | 6.9, 11.1–11.8 | match |
| O | 1 | running members oldest first | 3.1–3.3 | match |
| H | 1 | a member's href gains a trailing `-` (sweep: every member lookup) | 4.1–4.4, 5.1–5.19, 9.1–9.3, 12.1–12.9, 13.1 | match |
| N | 2 | the heading counts one fewer | 2.1, 2.2, 2.4, 8.1, 8.2 | match |
| K | 2 | `h3` from the third member | 6.2–6.7 | match |
| J | 2 | `/attention.json` rows carry `role` | 10.1 | match |
| Q | 2 | the quiet card reads `On site · 0` and links its member | 2.3, 6.1, 7.1, 7.5, 13.2 | match |
| G | 3 | the ghost's stage is not `aria-hidden` | 6.8 | match |
| D | 3 | the dozing Worker is the awake row glyph | 7.2, 7.3 | match |
| U | 3 | the crew list's class is `crew list` | 4.5 | match |
| W | 3 | a member's project label unescaped | 9.1, 9.2 | 9.1 only |
| F | 4 | In flight renders while quiet | 7.4, 7.5 | match |
| X | 4 | every doing phrase is `working` | 4.1, 4.3, 5.1–5.18, 9.3 | match |
| Fa | 4 | the crew Owner loses its face | 12.2, 12.5, 12.8 | match |
| R | 4 | the crew robots' art is assigned in reverse role order | 12.1, 12.4, 12.7, 13.1 | match |

72 of 72 tests killed; 16 mutations in 4 rounds. W's prediction was wrong: 9.2's Thens concern the hostile slug, and
W un-escaped only the project. 5.19, 9.2, 12.3, 12.6 and 12.9 are killed only by the sweep H. The four-round ceiling
left a targeted mutation for each unrun.

## 029-U3

Rows 029-U3.1.1–029-U3.6.2 in `BEHAVIORS.md` § 029-U3, 35 tests. Red at the spec commit `7957bff`, against U2's
dashboard: 29 of 35 red, every failure an assertion. Six were green, each guarding what the base already did: 1.14 (an
orphan keeps the index out of the empty state), 1.16 (the root was already escaped), 3.1 and 3.2 (one project), 6.1
and 6.2 (`/attention.json`); A, B, P and L kill them. Each round applied four mutations on distinct statements with
disjoint predicted sets, ran the dash suite, and restored the file with `git checkout`. `git status` was clean after
each. Run 2026-10-14.

| # | round | mutation | predicted | observed |
|---|---|---|---|---|
| A | 1 | the empty state ignores orphan sessions | 1.14 | match |
| B | 1 | the projects root unescaped in the where line | 1.15, 1.16 | match |
| F | 1 | the hero's grid ink left as its hex | 1.7, 1.8, 1.10 | match |
| S | 1 | footer gap, stamp accent mix and stamp width off by a step | 4.7, 4.8, 4.9 | match |
| V | 2 | the hero uncropped, its top margin zero | 1.6, 1.12 | match |
| D | 2 | the stamp's paper painted the page background | 4.5, 4.6 | match |
| Q | 2 | the hero's paper painted the figure fill | 1.7, 1.9 | match |
| K | 2 | the first and third lines reworded | 1.2, 1.3, 2.1, 2.2 | also 1.15 |
| J | 3 | the hero and stamp lose `focusable="false"` | 1.5, 4.4 | match |
| R | 3 | the hero's light bulb redrawn | 1.7, 1.11 | match |
| L | 3 | `/attention.json` gains a trailing newline | 6.1, 6.2, 029-U2.10.1 | match |
| P | 3 | a one-project index also draws the empty section | 3.1, 3.2 | match |
| M | 4 | the footer reads `Last updated` | 4.1, 4.2, 4.3, 5.1, 5.2 | match |
| N | 4 | the empty section is followed by the attention note | 1.1, 1.4 | match |
| O | 4 | the empty index keeps the plan-usage line | 1.13 | match |
| T | 4 | each art drops with the other's file | 2.3, 5.3 | match |

35 of 35 tests killed; 16 mutations in 4 rounds. K's prediction was wrong: 1.15 matches the whole where line, its
wording included, so rewording it reddens the hostile-root row as well as 1.3.

## 032 · the footer's contrast; wrong-shaped run.json values

Rows `032-…` in `BEHAVIORS.md`, plus 029-U3.4.9 re-pinned to 85 %. Red at the spec commit: 11 of 11, each on its
assertion: the two contrast rows on Whiteprint (3.00 and 2.44 under 4.5 and 3), 4.9 on the 70 % mix, the served rows
on a dropped connection, the card and summary rows on a `TypeError` exit, S3.3 on the git call carrying `--head-option`.
One mutation at a time, the whole dash suite each, the file restored with `git checkout`; `git status` was clean after.
Run 2026-10-14.

| # | mutation | predicted | observed |
|---|---|---|---|
| A | footer text back to `--faint` | F1.1 | match |
| B1 | a list `phase` kept | S1.1, S2.1 | match |
| B2 | a dict `phase` kept | S1.2 | match |
| B3 | a wrong `phase` written `null`, not dropped | S2.1 | survived, then match once S2.1 pinned the missing card's states |
| C1 | a list `status` kept | S1.3, S2.2 | match |
| C2 | a wrong `status` written `null`, not dropped | S2.2 | survived, then match once S2.2 pinned them |
| D | a list `ticket` kept | S3.1 | match |
| E | stamp accent back to 70 % | F1.2, 029-U3.4.9 | match |
| F | `head` not held | S3.2, S3.3 | match |
| G | `publish.tip` not held | S3.3 | match |

11 of 11 killed. B3 and C2 first survived because the hold runs on the missing case too: writing `null` changed both
cards alike, so comparing them proved nothing about "as a missing one reads today". S2.1 and S2.2 now also pin the
missing card's `.state` texts, checked against the tool at 19825d3.

After review 1 (F1), rows S4.1–S4.6: red at the spec commit, 6 of 6, each on a dropped connection. Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| R | `rotate` not held | S4.1 | match |
| P | `stop_reason` not held | S4.2 | match |
| Q | `rebriefs` not filtered | S4.3 | match |
| U | `units` not filtered | S4.4, S4.5 | match |
| W | `worktree` not held | S4.6 | match |

17 of 17 of the 032 rows and 4.9 killed.

After review 2 (F4), rows S5.1–S5.3: red at the spec commit, 3 of 3 (S5.1 and S5.2 on `/` dropping its connection,
S5.3 on exit 1). Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| K | `stop_reason.code` not held | S5.3 | match |
| D | `stop_reason.detail` not held | S5.1 | match |
| Y | `rebriefs[].why` not held | S5.2 | match |

20 of 20 of the 032 rows and 4.9 killed.

After review 3, the Lead's rows S6.1–S6.3: red at the spec commit, 3 of 3 (a page dropping its connection). Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| X1 | a run.json that is not an object kept | S6.1 | match |
| X2 | no encode check | S6.2 | match |
| X3 | only `JSONDecodeError` caught again | S6.1, S6.2, S6.3 | match |

23 of 23 of the 032 rows and 4.9 killed.

After review 4 (F1), rows S6.4–S6.5: red at the spec commit, 2 of 2 (no answer within the GET's 20 s). Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| Z | `RecursionError` not caught in `read_run` | S6.4, S6.5 | match |

25 of 25 of the 032 rows and 4.9 killed.

After review 5 (F1), `read_run` rewritten around `check_servable`. S6.6 was red at the spec commit. S6.4, re-pinned to
Unreadable, and S6.7 were green there, so each owed a kill. All of S6 re-killed against the new code. Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| Z1 | the depth cap off | S6.4, S6.6 | match |
| Z2 | the depth cap at 10 | S6.7 | match |
| Z3 | the lone-surrogate check off | S6.2 | match |
| Z4 | `json.loads`'s `RecursionError` not caught | S6.5 | match |
| X1 | a run.json that is not an object kept | S6.1 | match |
| X3 | only `JSONDecodeError` caught again | S6.1–S6.6 | match |

27 of 27 of the 032 rows and 4.9 killed.

## 033 · the content pass

Rows `033-…` in `BEHAVIORS.md`. Red at the spec commit: 13 of 13, each on its assertion; B11, written after the
implementation commit from the build's contrast table, red on its assertion too (4.33 and 4.26 under 4.5, Whiteprint
and Blueprint on hover). One mutation at a time, the whole dash suite each, the file restored with `git checkout`;
`git status` was clean after. Run 2026-10-15.

| # | mutation | predicted | observed |
|---|---|---|---|
| M1 | a plan row's face shows the Description | B1, P1 | match |
| M2 | the Status cell loses its "Status column · " label | B2 | match |
| M3 | a landed unit drawn as unlanded | B3 | match |
| M4 | an escaped pipe left as `\|` in its cell | P1 | match |
| M5 | a stop's code dropped from the state word | B4 | match |
| M6 | a stopped card's callout keeps its code heading | B5 | match |
| M7 | the handoff dropped from Details | B6 | match |
| M8 | no crew card on the project page | B7 | match, and 031-P2.2 errors: as U33 re-cut it, it finds the page's crew card first |
| M9 | plan usage back on the project page (B8's old Then; B8 now pins the reverse, killed by R1 below) | B8 | match |
| M10 | the now line's title loses the latest move | B9 | match |
| M11 | the time (`.ago`) in the faint ink | B10 | match |
| M12 | the attention paper's stopped word back to `note-attn` | B11 | match (Whiteprint and Blueprint, on hover) |
| M13 | `merge-base` without `--end-of-options` | G1 | match |
| M14 | the text summary printed without `owner_git.shown()` | T1 | match |

14 of 14 of the 033 rows killed. 029-U1.8.2 (`test_keeps_the_flight_dot_rule__when_glyph_rows_are_styled`) is deleted:
flight rows carry no left dot after B4, so the rule it kept is gone.

After review 1 (F1, F2, F3, F5), rows B12–B21. Red: B12, B13, B14 and B21, each on its assertion. B15–B20 pin
behaviour the implementation commit had already built, so they were green when written; review 1's surviving mutants
are their kills. Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| N1 | the Ready to land row's state word is the unit list | B12 | match |
| N2 | a stopped row's state word keeps the idle Planner aside | B13 | match |
| N3 | the face's threshold back to 90 characters | B14 | match |
| N4 | `short_number` returns the full figure | B15, B16 | match |
| N5 | the whole-k edge at 10,000, not 9,950 | B16 | match |
| N6 | the time kept on a card at 560 px | B17 | match |
| N7 | the hero without its percent built | B18 | match |
| N8 | a briefed card keeps its wall meter | B19 | match |
| N9 | a stopped card's now line reads like a working one | B20 | match |
| N10 | the card's now line names the rebrief Planner too | B21 | match |

24 of 24 of the 033 rows killed.

After review 2 (S1, S2, N1–N4), rows B22–B35, and T1's Given re-cut. Q5's shorter `SUMMARY` had left T1's
`replace("Totals what", …)` matching nothing, so the plan cell carried no BEL; T1 now builds its row from `SUMMARY` and
fails if the row is unchanged. Red: B29, on its assertion. The rest pin built behaviour and were green when written;
review 2's surviving mutants, or one like them, are their kills. Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| O1 | a stage's count never partial | B22 | match |
| O2 | the bar on briefed and done cards | B23 | match |
| O3a | no Latest line in Details | B24 | match |
| O3b | a Latest line with no events | B24 | match |
| O4 | no time on an index attention row | B25 | match |
| O5 | no wall meter on any now line | B26 | match (both subtests, card and In flight) |
| O6 | the crew card after the sections | B27 | match |
| O7 | no track on an In flight row | B28 | match |
| O8 | an empty phrase after `Handing off` | B29 | match |
| O9a | an owner-call card reads like a working one | B30 | match |
| O9b | a parked card with no position | B30 | match (an error: the card has no now line to read) |
| O10 | the project page's ghost links `#flight` | B31 | match |
| O11 | the rebrief reason unclamped | B32 | match |
| O12 | a pending row's where without its title | B33 | match |
| O13 | a trailing escaped pipe stripped | B34 | match |
| O14 | the ledger line's old label | B35 | match |
| O15 | plan lines bypass `owner_git.shown()` | T1 | match |

38 of 38 of the 033 rows killed, T1 again among them.

After review 3 (S1, N1, N2, N5), rows B36–B43. Each pins built behaviour and was green when written; review 3's surviving
mutants, or one like them, are their kills. Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| P1 | no rebrief count on the facts line | B36 | match |
| P2 | no files on the facts line | B36 | match |
| P3 | the tally back on a live index card | B37 | match |
| P4 | no facts line under a no-plan header | B38 | match |
| P5 | no folder path on an Unreadable card | B39 | match |
| P6 | a parked card draws its bar | B40 | match |
| P7 | the plural for one unit | B41 | match |
| P8 | every stop callout loses its code heading | B42 | match |
| P9 | no `attention` id on the project page | B43 | match |

46 of 46 of the 033 rows killed. `dot()`'s class escape is a declared guard: every caller passes a `STATE` or
`RUN_UNIT_DOT` value, so no input reaches it; the conventions lint is what holds the allowlist lines it retired.

B15's Given re-cut to invented counts (23,456 requests, 3,141,592 output tokens): the face reads `23k` and `3.1M`, the
same two branches of `short_number` as before. Re-killed.

| # | mutation | predicted | observed |
|---|---|---|---|
| Q1 | `short_number`'s M branch rounds to whole millions (`.0f`) | B15, B16 | match |

Plan usage back on the project page (Owner, 2026-10-15, flipping Lead decision 2). B8 rewritten to the new behaviour,
B44 added for the shared wording; both red on their assertions before the code. Same method.

| # | mutation | predicted | observed |
|---|---|---|---|
| R1 | the project page's line moved inside the hero, after the facts line | B8 | match |
| R2 | the label back to `Plan usage` | B44 | match |
| R3 | the title no longer names the Claude plan across every session | B44 | match |

47 of 47 of the 033 rows killed.

## 037 · a plan's groups are stages; a `Wave` heading still groups

Red before the dashboard change: S1 and S2, each on its assertion (the page had no `plan-stage`). One compiling
mutation per row, each run over the whole dashboard suite and reverted.

| # | mutation | predicted | observed |
|---|---|---|---|
| S1m | only a `### Wave ` heading starts a group in `plan_units` | S1 | match |
| S2m | only a `### Stage ` heading starts a group in `plan_units` | S2 | match |

2 of 2 of the 037 rows killed.

## 039 · landed only on positive evidence; a direct build's worktree found by its branch

Red before the dashboard change: L1, L4–L8 and L10, each on its assertion (`19c9691`). L2, L3 and L9 were green at
red: they pin what the old code already did. L11 and L12 were written with the code; each is red with the code it
pins taken out (M11, L12m). One compiling mutation per row, each over the whole dashboard suite, reverted after.

| # | mutation | predicted | observed |
|---|---|---|---|
| M1 | `has_landed` returns True for any listed worktree | L1, L10, R6.2, R6.3 | match, plus 033-G1, the option-shaped head row and the list-head row: each needs the in-main path to run |
| M2 | a branch gone everywhere reads not landed (`if holders else False`) | L2, L9 | match |
| M3 | `landed_slugs` drops `tone == "done"` | L3 | match |
| M4 | `landed_slugs` ignores `run.json.landed` | L4 | first run: none; `is_in_main` repeated the check. The repeat removed; second run: L4 |
| M5 | a direct build is working only when `busy` | L5 | match |
| M6 | `listed_branches` lists every repository a robowright.json names, trusted or not | L6 | match, plus R6.7 |
| M7 | `project_repos` skips an untrusted entry instead of refusing | L7 | match, plus L6 and R6.7: the untrusted project then reads landed |
| M8 | every repository reads as not holding the branch | L8 | match |
| M11 | `direct_worktree` ignores the branch index | L11 | match |
| L12m | `has_landed` drops the `BRANCH_SLUG` check | L12 | match |

12 of 12 of the 039 rows killed.

### Roster (`skills/lead/scripts/test_run_roster.py`, `UnitNameTests`)

Rewritten for the Owner's answer to review 1 F2 (2026-10-15, "option 1, fix the roster label now"): the label is the
plan row's, `U12 (note-autosave) · 3/5`. N1–N3 red on their assertions before the code (`'3/5 · U4 (note-autosave)'`);
N4 written with the code. Two first mutations were inert: N1's row is claimed by its ticket before the name rule runs,
and for `ENG-7` the short name equals the ticket. Each was replaced by one that changes the row's output.

| # | mutation | predicted | observed |
|---|---|---|---|
| R1 | a full-slug Unit cell keeps the whole slug as its name | N1 | match |
| R2 | an unmapped session prints the brief's current id | N2 | match |
| R3 | `TRACKER_KEY` no longer matches `ENG-7` | N3 | match |
| N4m | the label keeps control bytes | N4 | match |

### 039 review 1 fixes

L13 and L14 red on the pre-fix code (`4c885a0`), each on its assertion; L15 green at red. L14's first fixture made
every commit empty, so the branch's tree matched main's and read as squashed in; it now commits a file.

| # | mutation | predicted | observed |
|---|---|---|---|
| P1 | a `None` from `has_branch` no longer blocks; only `True` counts as held | L15 | match |
| P2 | the repository path back to `is_in_main(session, repo)` | L13 | match |
| P3 | the branch looked for only in the project's own repositories | L14 | match |

15 of 15 of the 039 rows killed.

### 039 review 2 fixes

L16 and L17 red at `381be91`, each on its assertion. L15 re-killed against the narrowed `None` rule.

| # | mutation | predicted | observed |
|---|---|---|---|
| Q1 | an existing worktree directory no longer blocks the "gone" inference | L16 | match |
| Q2 | every trusted repository must answer, as before | L17 | match |
| Q3 | the project's own repositories need not answer | L15 | match |

17 of 17 of the 039 rows killed.

## 041 · count line, time left, a robowright.json too deep to read, settings by name, the tap epoch

Run 2026-10-16. C1, T1 and G1 red before the change, each on its assertion; O36 and O37 (`test_owner_git.py`) red too.
Each mutation below was one edit, both the dashboard and the owner_git suites run, then restored; predictions written
before the run.

| # | mutation | predicted | observed |
|---|---|---|---|
| R1 | `count_line` lists every legend state, a zero count included | C1 | match |
| R2 | the index card drops `count_line` | C1 | match |
| R3 | `count_line` uses `PLAN_LABEL`'s words, not the bar's | C1 | match |
| R4 | `hero_facts` shows the time left whatever is built | T1 | match |
| R5 | `project_settings` stops catching `RecursionError` | G1 | match |
| R6 | `owner_git.named_repos` catches `(OSError, ValueError)` only, as before | G1, O36, O37 | match |
| R7 | `project_settings` merges every `*.json` in the folder, sorted by name | S1 | match |
| R8 | the plan-usage time rounds its epoch down to the minute | F1-R1.1, F1-R1.2 | match |

S1 pins what the code already did (green at red) and is killed by R7. R8 is why the tap epoch is `1800000028`: at
`1800000000` the epoch fell on a minute and no edit that drops the seconds could redden F1-R1.1. Each of the new rows
killed; `owner_git`'s two by R6.

## 043 · accept, complete, awaiting acceptance

Run 2026-10-16. D1 and D2 red before the change, each on its assertion. Each mutation below was one literal edit to
`tools/robowright-dash.py`, the whole suite run, then restored; predictions written before the run. M4 and M1 are 039's
mutations re-run over the renamed tests.

| # | mutation | predicted | observed |
|---|---|---|---|
| D1m | `unit_progress` reads the Status prefix `landed`, not `accepted` | D1 | match |
| D2m | `EVENT_PHRASE` drops `accept` | D2 | match |
| M4 | `in_main_slugs` ignores `run.json.accepted` | L4, 041-C1 | match |
| M1 | `has_reached_main` returns True for any listed worktree | L1, L10, R6.2, R6.3, 033-G1, S3.2, S3.3 | match |
| W1 | `PLAN_LABEL` says `complete` for `built` | the twelve rows reading `awaiting acceptance` in text mode | match |

Both new rows killed. M4 adds 041-C1 to 039's L4 because C1's U4 is complete through `run.json.accepted`.

D3 and D4, added after review 1 found that adding a fallback to the old names back left all 404 tests green. Both were
green when written, since the code has no fallback; each is killed by putting that fallback back:

| # | mutation | predicted | observed |
|---|---|---|---|
| D3m | `in_main_slugs` also reads `run.json.landed` | D3 | match |
| D4m | `unit_progress` also accepts the Status prefix `landed` | D4 | match |

## 055 · a direct build's accept record; a project's trusted repositories

One mutation per new row, each applied to a scratch copy of the tree, the 055 rows run, then restored; predictions
written before the run.

| # | mutation | predicted | observed |
|---|---|---|---|
| D1 | `is_accept_recorded` returns `bool(sha)`, never asking git | A2 | match |
| D2 | `FULL_COMMIT_ID` matches any text | A3 | match |
| D3 | `in_main_slugs` drops the accept-record term | A1 | match |
| D4 | `project_repos` returns None for any repository `repos` does not list, as before | A4 | match |

All four killed. A2 and A3 were green at red; D1 and D2 are their kills.

After review 1:

| # | mutation | predicted | observed |
|---|---|---|---|
| D5 | `is_accept_recorded` lands a record on main while the branch exists without `is_change_of` | A5 | match |
| D6 | `recorded_accept` drops its `BRANCH_SLUG` check | A7 | match |

After review 3 (adversarial). D1 and D5 are retargeted at the restructured `is_accept_recorded`; the run is in the
unit's `evidence/mutations.log`.

| # | mutation | predicted | observed |
|---|---|---|---|
| D1′ | `is_accept_recorded` counts every candidate repository as on main | A2 | match |
| D5′ | `is_accept_recorded` lands a record on main while the branch exists without `is_change_of` | A5 | match |
| D7 | `is_accept_recorded` looks for the branch only in the repositories the project names | A9 | match |
| D8 | `is_accept_recorded` counts a holder only where the record's commit is on main (the per-repository check) | A8, A9 | match |
| D9 | `patch_id` reads the diff with context | A10 | match |

## 056 · a session folder nothing launched reads Briefed

One batch for the D rows here and the 056-R and 056-S rows (`skills/lead/scripts/BEHAVIORS.md`), which share the
predicate. Each mutation applied to a scratch copy of the tree, the three 056 classes run, then restored; predictions
written before the run. D4, D5, R2, R3, R4 and S2–S7 were green at red; M1–M6, M10 and M12 are their kills.

| # | mutation | predicted | observed |
|---|---|---|---|
| M1 | `never_launched` ignores `is_live` | S2 R2 D4 | match |
| M2 | … drops the `session_id` term | S3 R3 D5 | match |
| M3 | … drops the `transcripts` term | S4 | match |
| M4 | … drops the `started_at` term | S5 R4 | match |
| M5 | … ignores `events.jsonl` | S6 | match |
| M6 | … holds for any state | S7 | match |
| M7 | … is always `False` | S1 R1 R5 D1 D2 D3 | match |
| M8 | the roster drops its `briefed` branch | R1 R5 | match |
| M9 | the `--since` count takes `briefed` as unfinished | R5 | match |
| M10 | the roster passes `is_live=False` | R2 | match |
| M11 | `session_tone` drops its `briefed` branch | D1 D2 D3 | match |
| M12 | `session_tone` passes `is_live=False` | D4 | match |
| M13 | `load_session` watches a `briefed` session for silence | D2 | match |
| M14 | In flight also takes a `briefed` session | D3 | match |
| M15 | `match_session` drops its `cwd` type check | R6 | match |
| M16 | `match_session` drops its NUL check | R7 | match |

All nineteen tests killed; M15 and M16 came with R6 and R7, after the gate review's F3. Held out, predicted and seen to pass, not kept (each takes a branch a kept row takes): the
worker template's `run.json` is never launched; a briefed session with an idle live session reads `stalled`.

## 052a · park from briefed; a session parked before it launched

One batch for 052a-D1 here and the 052a-S and 052a-R rows (`skills/lead/scripts/BEHAVIORS.md`). Each mutation
applied in the build's worktree, the named classes run, then restored (`git status` clean after the batch);
predictions written before the run. S1–S3, R1 and D1 were red before the code; S4 is U2's R2 test with `briefed`
dropped from its set.

| # | mutation | predicted | observed |
|---|---|---|---|
| M1 | `e_park` writes `done` for a briefed session | S1 | match |
| M2 | the reason guard skips a briefed session | S2 | match |
| M3 | the owner guard skips a briefed session | S3 | match |
| M4 | `park.from` also takes `intake` | S4 | match |
| M5 | the roster reads a session parked from briefed as `briefed` | R1 | match |
| M6 | the card's before-launch text keys on `from == "done"` | D1 | match |

## U52b · a project's robowright.json read through `read_unlinked` (052b-R1, R2)

Both red before the code (R1 named the Lead from the linked file; R2 hung on the FIFO).

| # | Mutation | Predicted | Verdict |
|---|---|---|---|
| M5 | `project_settings` reads with `read_text()` | R1 | match |
| M7 | the same, run against the FIFO | R2 (timeout) | match |

## U57 · a direct build beside a session folder with no run.json (057-D1–D4)

D1, D2 and D4 red before the code; D3 a guard, green before it.

| # | Mutation | Predicted | Verdict |
|---|---|---|---|
| M1 | `direct_builds` drops its `known` skip | D3 | match |
| M2 | `load_sessions` counts every folder as known, run.json or not | D1, D2, D4 | match |
| M3 | briefing rows never give way to a direct build | D2 | match |
| M4 | the live-session test inverted: a briefing row gives way to a build with no live session instead | D2 | match |

Untested, read from the code and not run: a finished direct build whose session has exited, beside a live Planner,
reads as showing both rows; no row asks for it.

## U65 · a session with no ticket (065-T1)

T1 red before the code: the row read `Not started`, no ticket claim for a session with no ticket.

| # | Mutation | Predicted | Verdict |
|---|---|---|---|
| M1 | `ticket_of` returns `run.json.ticket` only, no slug fallback | T1 | match |

## 061 · an archived project and its sessions left out (061-A1–A16) · 2026-10-23

Red before the code: A1, A2, A5–A15, each on its Then (A10 waited on the FIFO until the subprocess timeout; A15's
server refused `--all` and never answered). A3 and A4 were green at red: an unarchived project already shows.
A16 was added after green, as a held-out row; M15 is its red.

| # | Mutation | Predicted | Verdict |
|---|---|---|---|
| M1 | `load_world` keeps hidden projects in its project list | A1, A2, A5, A8, A10 | match |
| M2 | `archived_mark` returns nothing | A6, A9, A13, A15 | match |
| M3 | the text summary drops `(archived)` | A7, A12, A14 | match |
| M4 | `is_archived` takes any truthy value | A3 | match |
| M5 | `archived_projects` reads robowright.json with `read_text()`, links followed | A4 | match |
| M6 | a parked session reads live | A8 | match |
| M7 | a live direct build does not keep its project shown | A9 | match |
| M8 | no session directory reads live | A6, A7 | match |
| M9 | `load_sessions` loads a hidden project's sessions | A10, A11 | match |
| M10 | the same for a folder with no run.json only | A10 | match |
| M11 | naming a project does not show it when archived | A12 | match |
| M12 | `--serve` ignores `--all` | A15 | match |
| M13 | `--once` ignores `--all` | A13 | match |
| M14 | the text summary ignores `--all` | A14 | match |
| M15 | `direct_builds` lists a hidden project's `prs/` | A16 | match |

A1's "no orphans" assertion is a declared guard: a hidden project's folder still exists, so its sessions never read as
orphans unless `known` is built from the shown projects only, which no mutation here does.

## 061 · settled statuses (061-C1–C8) · 2026-10-23

Red before the code: C1–C3 and C5–C8, each on its Then. C4 was green at red: `Submitted` already read `not started`.

| # | Mutation | Predicted | Verdict |
|---|---|---|---|
| M16 | `unit_progress` has no settled tone | C1, C2, C3, C5, C6, C7, C8 | match |
| M17 | `moved` is not settled | C2, C3 | match |
| M18 | the settled check reads the status before the strip | C3 | match |
| M19 | a settled unit keeps its weight in `total` | C5 | match |
| M20 | `is_stage_complete` takes only `complete` | C6 | match |
| M21 | `PLAN_LABEL` reads a settled unit `not started` | C1, C2, C3, C7 | match |
| M22 | `STATE` reads it `Not started` | C8 | match |
| M23 | `submitted` is settled too | C4 | match |

## 061 · verified in main, once per `--serve` process (061-D1–D5) · 2026-10-23

Red before the code: D1 and D2, each on its Then (the second GET still named the branch, and the record's commit).
D3 and D4 were green at red: every refresh already checked again. D5 is a declared guard. A held-out row, a direct
build after teardown, served twice, passed and was dropped: it takes D1's path.

| # | Mutation | Predicted | Verdict |
|---|---|---|---|
| M24 | `has_reached_main` never reads the `gone` id | D1 | match |
| M25 | `has_reached_main` never holds the `gone` id | D1 | match |
| M26 | `is_accept_recorded` never reads a verified record | D2 | match |
| M27 | a record is matched by slug alone, not by its `sha` | D3 | match |
| M28 | a branch not in main is held as a negative | D4 | match |
| M29 | `--serve` holds no cache (`server.verified = None`) | D1, D2 | match |

D5 is a declared guard: no compiling edit reddens it. It guards against a verified id kept on disk, where a session
could plant one.

### Review fix round (061-D6–D10)

The gate review of D found three things.
- F1: a `gone` or a record was held from a refresh in which a trusted repository could not answer.
- F2: `gone` was read before the guards that cost no git call.
- F3: two mutations survived.

D6, D7 and D10 were red on their Thens before the fix; D10's baseline was taken on the D commit. D8 and D9 were green
at red. D8's first Given landed through `has_reached_main` as well, so M33 left it green. It was re-cut so that only
the record lands it: a pick on a side branch, then fast-forwarded into a moved main. This is a table change after red.

| # | Mutation | Predicted | Verdict |
|---|---|---|---|
| M30 | `gone` held though a repository could not answer | D6 | match |
| M31 | a record held though a repository could not answer | D10 | match |
| M32 | `gone` read before the worktree-on-disk guard | D7 | match |
| M33 | an unverified record held as a negative | D8 | mismatch on the first D8 (none), then match on the re-cut D8 |
| M34 | `/p/<name>` passes no cache | D9 | match |
| M35 | `/attention.json` passes no cache | D9 | match |

M24, M25 and M29, run again on the fix, also redden D9. D9 takes the same `gone` path through the other routes, and it
did not exist when those were predicted. M26–M28 match unchanged.
