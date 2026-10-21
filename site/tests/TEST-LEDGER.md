# kit-core mutation ledger

Targeted mutants of `public/kit-core.js`, each run alone against `kit-core.test.mjs`; the kill set
was written into the harness before the run. Test ids are the rows of `BEHAVIORS.md`.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | `first[0] > 0` → `>= 0` | K3 | K3 | KILLED, match |
| M2 | drop the first frame's props from the start pad | K2 | K2 | KILLED, match |
| M3 | `last[0] < T` → `<= T` | K3 | K3 | KILLED, match |
| M4 | `t / T` → `t / (T + 1)` | K1, K3 | K1, K3 | KILLED, match |
| M5 | drop the last frame's props from the end pad | K2 | K2 | KILLED, match |
| M6 | `point[0] > t` → `>= t` (lastAtOrBefore) | C1, S3, TH3 | C1, S3, TH3 | KILLED, match |
| M7 | start from the last point, not the first | C3, S2 | C3, S2 | KILLED, match |
| M8 | remove the loop's `break` | C2, C3, CL1, CL2, CL3, CL4, S1, S2, TH2 | C2, C3, CL1, CL2, CL3, CL4, S1, S2, TH2 | KILLED, match |
| M9 | never consider the last point | C1, CL7, S3, S4, TH3 | C1, CL7, S3, S4, TH3 | KILLED, match |
| M10 | `Math.round` → `Math.floor` | CL4 | CL4 | KILLED, match |
| M11 | hours not zero-padded | CL1, CL2, CL3, CL4, CL6, CL7 | CL1, CL2, CL3, CL4, CL6, CL7 | KILLED, match |
| M12 | minutes not zero-padded | CL5, CL6 | CL5, CL6 | KILLED, match |
| M13 | `?? before` → `?? points[0]` | CL7 | CL7 | KILLED, match |
| M14 | `after` is always the last point | CL2 | CL2 | KILLED, match |
| M15 | `after - before` → `after + before` | CL1, CL2, CL3, CL4 | CL1, CL2, CL3, CL4 | KILLED, match |
| M16 | drop the `span === 0` guard | CL7 | CL7 | KILLED, match |
| M17 | drop the single-theme return | TH1 | TH1 | KILLED, match |
| M18 | themeAt always returns the last point's theme | TH2 | TH2 | KILLED, match |
| M19 | drop the `travel <= 0` guard | P6 | P6 | KILLED, match |
| M20 | drop the clamp's floor | P1, P3 | P1, P3 | KILLED, match |
| M21 | drop the clamp's ceiling | P5 | P5 | KILLED, match |
| M22 | divide by the height, not the travel | P2, P4 | P2, P4 | KILLED, match |
| M23 | `t <= to` → `t < to` | A1 | A1 | KILLED, match |
| M24 | step a whole period, not half | A1, A2 | A1, A2 | KILLED, match |
| M25 | close at 60 ms, not 70 | B1 | B1 | KILLED, match |
| M26 | drop the reopen frame | B1, B2 | B1, B2 | KILLED, match |

26 mutants, 26 killed, every prediction matched. Each of the 30 tests is reddened by at least one.

## Removed before mutating

- `clockAt` clamped the interpolation fraction to [0, 1]. Between a point and the next one after `t`,
  the fraction is already in range, so no input reaches the clamp; it was deleted, not tested.

## Held-out examples

One per rule, derived after green and predicted to pass: a track padded at one end only, the middle
of three captions, the first stretch of a three-point clock, the middle of three theme points, a
quarter of the way through a scroller, a scene with no blinks. All six passed; each reaches a branch
a table row already reaches, so none was kept.


## Review fixes: the scene controls

Rows NK, PK, SC and PF were written from the adversarial review's F1, F4 and F6 and the smoke rows
they break, before the code. All 13 tests failed on their assertion against constant skeletons,
then passed. Mutants of `public/kit-core.js`, each run alone:

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M40 | next ignores the tolerance | NK2 | NK2 | KILLED, match |
| M41 | no next becomes `now`, not none | NK3, PF3 | NK3, PF3 | KILLED, match |
| M42 | previous falls back to the first key frame, not 0 | PK2 | PK2 | KILLED, match |
| M43 | previous adds the tolerance instead of subtracting it | PK1 | PK1 | KILLED, match |
| M44 | a scrub to exactly `now` takes the forward branch | none: registered EQUIVALENT before the run | none | EQUIVALENT: an `input` event never repeats the value, and under reduced motion `now` is a key frame |
| M45 | drop "a long scrub forward lands where it passed" | SC2 | SC2 | KILLED, match |
| M46 | scrubbing forward from the last key frame falls back to the first | SC4 | SC4 | KILLED, match |
| M47 | a small step forward snaps back instead of advancing | SC1 | SC1 | KILLED, match |
| M48 | the end needs exactly the duration | PF1 | PF1 | KILLED, match |
| M49 | reduced motion ignored at the end | PF3 | PF3 | KILLED, match |
| M50 | play always starts from 0 | PF2, PF4 | PF2, PF4 | KILLED, match |
| M51 | next is the last key frame past now, not the first | NK1, SC1 | NK1, SC1 | KILLED, match |
| M52 | the scrub snaps `now`, not the value | SC2, SC3 | SC2, SC3 | KILLED, match |

12 killed, 1 equivalent, every prediction matched; each of the 13 tests is reddened by at least
one. The wiring in `kit.js` (the buttons, the scrubber handler and play) has no seam a unit test
reaches, and the recorder never presses a control: it is checked by the smoke pass.

# recorder mutation ledger

Targeted mutants of the page, each run alone against `tools/recorder.mjs --check`; the kill set was
written into the harness before the run. Cells are theme × viewport × motion; "all 13" is the twelve
matrix cells and the cell that leaves the theme to the page. Rows are `BEHAVIORS.md` → recorder.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M27 | the caption read a second early (`captionAt(now - 1000, …)`) | R2, all 13 | R2, all 13 | KILLED, match |
| M28 | the stylesheet's link misspelt | R1 (404), all 13 | R1, all 13, and R2, R3, R6, R8 with it | KILLED, wider: no stylesheet, no layout |
| M29 | the scroll handler throws after asking for a frame | R1 (page error), all 13 | R1, all 13 | KILLED, match |
| M30 | the hero never appended | R3, all 13 | R3, all 13 | KILLED, match |
| M31 | the hero blinks under reduced motion | R7, the 6 `reduce` cells | R7, the 6 `reduce` cells | KILLED, match |
| M32 | no snapping under reduced motion | R7, the 6 `reduce` cells | R7, the 6 `reduce` cells | KILLED, match |
| M33 | the stage drawing 110 % wide | R8, the 6 phone cells | R8, the 6 phone cells | KILLED, match |
| M34 | the theme never released | R6, the follow cell | R6, the follow cell | KILLED, match |
| M35 | the theme applied by the inactive scene | R6, the follow cell | R6, the follow cell | KILLED, match |
| M36 | progress divided by the height, not the travel | R2 and R7 (position), all 13 | R2, R7, all 13 | KILLED, match |
| M37 | the active scene chosen by `top >= middle` | not active, all 13 | all 13; the follow cell's theme too | KILLED, wider as predicted |
| M38 | the theme pin removed | R5, the 8 whiteprint and night cells | R5, those 8 | KILLED, match |
| M39 | the HOLD caption starts after its key frame | R2, all 13 | R2, all 13 | KILLED, match |

13 mutants, 13 killed. R4 and R9 are the recorder's own output, checked by running it: one file per
key frame and one hero per cell under `tests/out/`; `--stills` and `--frames` print `FAIL … reserved
for U7`/`U8` and exit 2.

## Wrong predictions

- The first M29 put the throw behind `mount.playing &&`, so it never ran without play and nothing
  failed. The model was wrong, not the recorder; the throw moved to where every scroll reaches it.
- The first M30 was a kill for the wrong reason: Playwright's `boundingBox()` waited out its timeout
  for a hero that was never there. The hero check now measures in the page and fails at once by
  name; M30 was re-run against it.

## Green at red

Only R5 was red before the kit changed (the 8 whiteprint and night cells, on the theme assertion).
Every other row characterizes the kit as built in steps 3–5 and owes its kill above. The blueprint
cells cannot redden R5: blueprint is the scene's own theme.

## Review fixes: announcing

R10 was red on all 13 cells before the kit changed (review F5: the first caption was announced at
load). The end-of-scene half was green at red and owed its kill.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M53 | announce only the first caption a scene settles on | R10 (end), all 13 | R10 (end), all 13 | KILLED, match |
| M54 | announce whether or not the scene is active | R10 (before the story), all 13 | R10 (before the story), all 13 | KILLED, match |

## The theme hold

TH4 and TH5 pin `holdsTheme`; the recorder's gap check pins the `drive()` condition that calls it.
TH5 was green at red (the skeleton returned `false`) and owed its kill.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M55 | `storyTop <= middle` → `storyTop >= middle` | TH4 | TH4 | KILLED, match |
| M56 | drop the bottom bound | TH5 | TH5 | KILLED, match |
| M57 | `drive()` releases whenever no scene is centred | the gap check, `system-light` only, one line per gap | the gap check, `system-light` only, six gaps | KILLED, match |

Dropping the top bound survives both tests: nothing pins the release above the story.

## A scene with no theme, and the theme above the story

TH6 pins `holdsTheme`'s top bound, which M56's note left unpinned; TH6 was green at red and owed its
kill. TH7 was red at red by a TypeError, not on its assertion, and owed a kill that compiles.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M58 | `themeAt` returns `'whiteprint'` for a `null` theme | TH7 | TH7 | KILLED, match |
| M59 | drop `holdsTheme`'s top bound | TH6 | TH6 | KILLED, match |
