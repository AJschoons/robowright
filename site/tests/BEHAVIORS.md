# kit-core behaviours

The rules `kit-core.test.mjs` pins, written before `public/kit-core.js`. "§6" is the unit's
exploration doc → Tests, behaviours the kit-core tests pin. "Mockup" is the inspection-scene
mockup the kit's maths is ported from; its line numbers are given where a row characterizes it.
"D11" is the story revision's settled decision on the theme between scenes. "D5" and "D12" are the
opening revision's settled decisions on a scene with no theme and on the theme above the story.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| K1 | A track always spans the whole timeline | frames at 300 and 1600, T 13000 | `keyframeOffsets` | offsets 0, 300/13000, 1600/13000, 1 | §6: "first offset is 0 … last is 1 … offsets are t/T in order" |
| K2 | The padded ends hold their neighbour's state | opacity 0 at 300, opacity 1 at 1600, T 13000 | `keyframeOffsets` | offset 0 has opacity 0; offset 1 has opacity 1 | §3.1: both ends of every keyframe are written explicitly; mockup :207, :210 |
| K3 | A track that already spans the timeline is not padded | frames at 0 and 13000, T 13000 | `keyframeOffsets` | two keyframes, offsets 0 and 1 | Mockup :207, :210 (pads only when the first frame is after 0, the last before T) |
| S1 | Snap to the nearest key frame at or before t | keys 1000, 3300 | t 2000 | 1000 | §6 |
| S2 | Below the first key frame, the first | keys 1000, 3300 | t 500 | 1000 | §6 |
| S3 | A key frame snaps to itself | keys 1000, 3300 | t 3300 | 3300 | §6 |
| S4 | Past the last key frame, the last | keys 1000, 3300 | t 9000 | 3300 | §6: "the nearest key frame at or before t" |
| C1 | A caption starts at its own instant | captions at 0 and 4300 | t 4300 | the second | §6 |
| C2 | Until then the previous one shows | captions at 0 and 4300 | t 4299 | the first | §6 |
| C3 | Before the first caption, the first | captions at 1000 and 2000 | t 0 | the first | §6: "before the first, the first" |
| CL1 | The clock is linear between points | points (0, 130), (13000, 172) | t 6500 | `02:31` | §6 |
| CL2 | Equal neighbours hold the clock | points (0, 210), (4000, 210), (8000, 230) | t 2000 | `03:30` | §6 |
| CL3 | Each stretch interpolates between its own two points | points (0, 210), (4000, 210), (8000, 230) | t 6000 | `03:40` | §6: "linear between `[ms, minutes]` points" |
| CL4 | Minutes round to the nearest | points (0, 130), (13000, 172) | t 6350 (150.5 min) | `02:31` | Mockup :297 (`Math.round`) |
| CL5 | Hours and minutes are two digits each | points (0, 600), (1000, 600) | t 0 | `10:00` | §6: "formatted `HH:MM`" |
| CL6 | Single-digit hours and minutes are zero-padded | points (0, 65), (1000, 65) | t 0 | `01:05` | §6: "formatted `HH:MM`" |
| CL7 | Past the last point the clock holds | points (0, 130), (13000, 172) | t 20000 | `02:52` | Assumed: hold the last point (Q1) |
| TH1 | A single theme is constant | `'blueprint'` | t 7000 | `blueprint` | §6 |
| TH2 | Theme points switch at their own instant | points (0, whiteprint), (5000, blueprint) | t 4999 | `whiteprint` | §6 |
| TH3 | Theme points switch at their own instant | points (0, whiteprint), (5000, blueprint) | t 5000 | `blueprint` | §6 |
| TH4 | Inside the story the theme holds across a heading gap | story rect top −6000, bottom 14000; viewport middle 400 (the middle in the gap between two story scrollers) | `holdsTheme` | `true` | D11: "true when the viewport's middle is inside `#story`'s rect"; TH4 "between two story scenes, the earlier scene's theme stays" |
| TH5 | Past the story the theme is released | story rect top −19850, bottom 150; viewport middle 400 | `holdsTheme` | `false` | D11: TH5 "past the story, released" |
| TH6 | Above the story the theme is released | story rect top 1200, bottom 21200; viewport middle 400 (the middle above the story's start) | `holdsTheme` | `false` | D12: "a `holdsTheme` test for the top bound … a middle above `storyTop` → `false`"; Language: "outside the story, the system's preference" |
| TH7 | A scene with no theme pins nothing | `null` | t 0 | `null` | D5: "`themeAt(t, theme)` returns `null` for a `null` theme"; acceptance: `themeAt(0, null)` prints `null` |
| P1 | Progress is 0 with the scroller's top at the viewport's | height 5200, viewport 1000 | top 0 | 0 | §6 |
| P2 | Progress is 1 once the scroller's bottom reaches the viewport's | height 5200, viewport 1000 | top −4200 | 1 | §6 |
| P3 | Progress is 0 before the scroller arrives | height 5200, viewport 1000 | top 10 | 0 | §6: clamped to [0, 1] |
| P4 | Progress is the scrolled fraction | height 5200, viewport 1000 | top −2100 | 0.5 | §6: `-top / (height - vh)` |
| P5 | Progress is 1 after the scroller has left | height 5200, viewport 1000 | top −9000 | 1 | §6: clamped to [0, 1] |
| P6 | A scroller no taller than the viewport has no progress to make | height 1000, viewport 1000 | top 0 | 0 | Assumed: 0, never NaN (Q2) |
| A1 | Alternation starts on the first state, every half period, `to` inclusive | 0 to 1000, period 500, states a, b | `alternate` | a@0, b@250, a@500, b@750, a@1000 | Mockup :216-220 |
| A2 | Alternation stops at the last half period at or before `to` | 1700 to 2300, period 500 | `alternate` | a@1700, b@1950, a@2200 | Mockup :216-220 |
| B1 | A blink closes 70 ms after it starts and reopens at 160 ms | one blink at 2600 | `blinks` | open@0, open@2600, `scaleY(.12)`@2670, open@2760 | Mockup :221-225 |
| B2 | Each blink adds its three frames, in order | blinks at 1500 and 5800 | `blinks` | seven frames; the second blink starts at 5800 | Mockup :221-225 |
| NK1 | Next is the first key frame past now | keys 1000, 3300, 5800; tolerance 20 | now 1000 | 3300 | Copy → Scene controls: "Next key frame"; kit at `559a3bf` |
| NK2 | Within the tolerance of a key frame counts as on it | keys 1000, 3300, 5800; tolerance 20 | now 3290 | 5800 | Pre-change behaviour at `559a3bf` (`KEY_TOLERANCE_MS`: a scroll pixel is about 4 ms) |
| NK3 | Past the last key frame there is no next | keys 1000, 3300, 5800; tolerance 20 | now 5800 | none | Pre-change behaviour at `559a3bf`: Next then holds |
| PK1 | Previous is the last key frame before now | keys 1000, 3300, 5800; tolerance 20 | now 3300 | 1000 | Copy → Scene controls: "Previous key frame" |
| PK2 | Previous never moves forward: before the first key frame it goes to the scene's start | keys 1000, 3300, 5800; tolerance 20 | now 300 | 0 | Review F6 against the label "Previous key frame"; Assumed: the start, not staying put (Q4) |
| SC1 | Under reduced motion, a small scrub forward reaches the next key frame | keys 1000, 3300, 5800 | value 1010, now 1000 | 3300 | Review F1; S4 and S9: the key frames are reachable from the keyboard |
| SC2 | Under reduced motion, a scrub past key frames lands on the last one passed | keys 1000, 3300, 5800 | value 6000, now 1000 | 5800 | S4: only key frames are shown |
| SC3 | Under reduced motion, a small scrub back reaches the previous key frame | keys 1000, 3300, 5800 | value 3290, now 3300 | 1000 | Review F1; S4 |
| SC4 | Under reduced motion, scrubbing forward from the last key frame stays there | keys 1000, 3300, 5800 | value 5810, now 5800 | 5800 | S4: nothing after the last key frame is shown |
| PF1 | Play at the end starts again from the beginning | duration 13000, tolerance 20, motion on | now 12990 | 0 | Pre-change behaviour at `559a3bf` |
| PF2 | Play mid-scene carries on from where the scene is | duration 13000, tolerance 20, motion on | now 5000 | 5000 | Pre-change behaviour at `559a3bf` |
| PF3 | Under reduced motion, the last key frame is the end | keys 1000, 3300, 12600; duration 13000; tolerance 20 | now 12600 | 0 | Review F4; S3: play drives the scene under either setting |
| PF4 | Under reduced motion, play before the last key frame carries on | keys 1000, 3300, 12600; duration 13000; tolerance 20 | now 3300 | 3300 | S3 |

## Questions

- **Q1** — after a scene's last clock point, does the clock hold or keep running? Assumed hold:
  `seek` clamps `t` to the scene's duration, so the case only arises in a hand-written call.
- **Q2** — a scroller as short as the viewport divides by zero. Assumed progress 0: the scene
  sits on its first frame rather than seeking to `NaN`.
- **Q4** — before the first key frame, where does "Previous key frame" go? Assumed the scene's
  start (0): the control never moves the scene forward, and under reduced motion 0 shows the
  first key frame anyway.

# recorder behaviours

The rules `tools/recorder.mjs --check` pins, written before the recorder. The recorder loads the
page in Chromium once per cell, for every theme (whiteprint, blueprint, night) × viewport
(1280×800, 390×844) × reduced motion (`no-preference`, `reduce`), and once more with no theme set.
"§2" is the exploration doc → Changes, the recorder row; "§4" is its step 6; "S4", "S5" are rows of
its manual pass. "D4", "D5" and "D6" are the opening revision's settled decisions: the kit runs on
a page without `#story` (D4); a scene with no theme pins nothing (D5); the hero rules run on
`hero.html`, loaded once per cell, and the page rules stay on `index.html` (D6).

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R1 | A cell is clean | any cell | the page loads and every key frame is visited | no console error, page error, failed request or 4xx/5xx response | §2: "collects console errors and page errors" |
| R2 | The captions tell the declared story | any cell | each key frame is reached by scrolling | the captions read there, repeats collapsed, equal the scene's declared captions in order | §2: "asserts the caption sequence over the key frames equals the scene's declared captions" |
| R3 | The hero renders | any cell | `hero.html` has loaded | `#hero svg` has a non-empty bounding box | §2: "asserts the hero rendered"; D6: "the hero rules — `#hero svg` has a box … — run against `hero.html` loaded per cell" |
| R4 | Every key frame is recorded | any cell | each key frame is reached | one screenshot of the stage per key frame, `<scene>-<theme>-<viewport>-<motion>-<k>.png` | §2 |
| R5 | A theme set before load holds over the whole page | `data-theme` set on `<html>` before load | the scene is active | `<html>` keeps that theme | Assumed: a preset theme pins the page, so S5's "all three themes paint" reaches the scene (Q3) |
| R6 | With no theme set, the page follows the scene; a scene's theme holds past it until the next scene or the story's end | no theme set, system light | the scene is active, then the reader scrolls past it | `<html>` takes the scene's theme, holds it past the scene until the next scene or the story's end, then has none | §2: "`data-theme` … from the active scene's `theme`, restored to system outside the story"; D11: "a scene's theme holds past it until the next scene or the story's end" |
| R7 | Under reduced motion, the scene only shows key frames | reduced motion | each key frame, and a point between the first two, is reached by scrolling | the position is exactly that key frame; between the two, the earlier; on `hero.html`, the hero runs no animation | S4: "steps between seven key frames, no tweening"; §2 (hero): "none under reduced motion"; D6: "no animations under reduced motion … run against `hero.html` loaded per cell" |
| R8 | Nothing scrolls sideways | any cell | the page has loaded | the page is no wider than the viewport | Assumed: the phone layouts of steps 4–5 keep everything inside 390 px |
| R9 | The later modes are refused | `--stills` or `--frames` | the recorder starts | it refuses and exits non-zero | §2: "reserved for U7/U8 and refused here" |
| R10 | The story is announced only once the reader is in it | any cell | the page loads and settles; later the last key frame is reached and settles | the live region is empty at load, and holds the last key frame's caption at the end | §3.2 and S9: the caption the reader settles on, announced once per change; review F5 |
| R11 | A scene with no theme pins nothing and releases a pinned one | no theme set, system light; the kit has set the street's theme on `<html>` | the reader goes from the street's last key frame to the problem scene's first (the problem scene is mounted last, after the street) | `<html>` has no theme | Language: "a scene with `theme: null` pins nothing and releases a pinned one"; D5: "in the `system-light` cell the street's last key frame leaves a theme pinned and the jump to the problem scene's first key frame must release it, or the cell fails `theme … expected null`". Checked by the `system-light` cell only; accepted-untested at kit-test level, as `site/tests/` reaches no DOM |
| R12 | The kit runs on a page with no story | `hero.html`, which has no `#story`; any cell | the page is scrolled by a pixel and resized once, then two frames pass | no page error | D4: "the `hero.html` pass scrolls by a pixel and resizes once, waits two frames, and any `pageerror` fails the cell". This probe is the check: the guard reads `#story` in `drive()`, so it is not pure and has no kit-core test (D4: "if not, the BEHAVIORS row names the recorder pass as its check and says so"). `hero.html` is shorter than both viewports, so the pixel scroll fires no scroll event; the resize is what reaches `drive()` |
| R13 | The controls hold still under the drawing | any cell; a scene whose captions take different numbers of lines | each key frame is reached by scrolling | at every key frame, the gap from the drawing's bottom to the controls' top, and the drawing's x, y, width and height, are each within 0.5 px of their values at the first key frame | The Owner's phone feedback, finding 1 (`robowright-site/reviews/owner-feedback-2026-10-18-phone.md`): a caption that changes line count moves the controls; "the controls are like directly beneath the little animation thing", on desktop too |

## Questions

- **Q3** — the kit sets the active scene's theme on `<html>`, so a theme set beforehand would
  never reach the scene and the three-theme matrix would record blueprint three times. Assumed: a
  theme present before the kit loads pins the page and the kit leaves it alone. Readers never set
  one; the recorder does.
