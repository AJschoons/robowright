# robowright.dev

The promo site. `public/` is the whole site: static HTML, CSS and JavaScript with no build step and
no runtime dependencies.

## Serve

From `site/`:

```sh
npm run serve
```

or, from anywhere, `python3 -m http.server -d site/public 8080`. Open `http://localhost:8080`.

Opening `index.html` as a file does not work once the scenes load: browsers refuse ES modules over
`file://`.

## Test

```sh
npm test
```

runs the kit's maths (`tests/kit-core.test.mjs`) under `node --test`; it ends `# fail 0`.

## Record

```sh
npm run check
```

runs `tools/recorder.mjs --check`. It serves `public/` on a free port, loads the page in
Playwright's Chromium, and for every theme × viewport (1280×800, 390×844) × reduced motion, plus one
cell that leaves the theme to the page:

- scrolls to every key frame of every scene, as a reader would;
- checks the captions there tell the scene's declared captions in order, the theme, and that
  reduced motion shows only key frames;
- checks the hero drew on `hero.html`, nothing scrolls sideways, and the console stayed clean;
- screenshots each key frame and the hero to `tests/out/`.

It prints a line per cell and ends `recorder: ok (<n> shots)` or `recorder: FAIL <reason>`, then
`EXIT=`. The rules it checks are in `tests/BEHAVIORS.md`.

Installing Playwright and its browser is the Owner's step, once: `npm install` in `site/`, or the
same version in any parent folder's `node_modules`, since Node looks there too; then
`npx playwright install chromium`. The browser lives outside the repository, in Playwright's cache.

## Share image

`public/share.png` is the link-preview image `index.html` names as its `og:image`: the hero, drawn
by `hero.js` on `public/hero.html`, at 1200×720. To regenerate it after the hero changes, run the
recorder once (`npm run check`), then from `site/`:

```sh
cp tests/out/hero-whiteprint-1280x800-reduce.png public/share.png
```

The reduced-motion shot, because the hero blinks otherwise and a shot can catch a closed eye.
