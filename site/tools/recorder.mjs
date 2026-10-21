// The recorder: loads the site in Playwright's Chromium and records every scene. `--check` runs the
// matrix — theme × viewport × reduced motion, plus one cell that leaves the theme to the page — and
// prints one line per cell, then `recorder: ok (<n> shots)` or `recorder: FAIL <reason>`, then EXIT=.
// Rules: tests/BEHAVIORS.md → recorder behaviours.
import http from 'node:http';
import { readFile, rm, mkdir } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { themeAt } from '../public/kit-core.js';

const SITE = fileURLToPath(new URL('..', import.meta.url));
const PUBLIC = join(SITE, 'public');
const OUT = join(SITE, 'tests', 'out');
const THEMES = ['whiteprint', 'blueprint', 'night'];
const VIEWPORTS = [{ name: '1280x800', width: 1280, height: 800 }, { name: '390x844', width: 390, height: 844 }];
const MOTIONS = ['no-preference', 'reduce'];
const RESERVED = { '--stills': 'U7', '--frames': 'U8' };
const SCENES_TIMEOUT_MS = 10000;
const KEY_TOLERANCE_MS = 20;
const LAYOUT_TOLERANCE_PX = 0.5;
const ANNOUNCE_SETTLE_MS = 900;   // kit.js announces a caption 700 ms after it settles    // kit.js: scroll lands within a pixel; the scrubber rounds to 10 ms
const HERO_SHOT_AFTER_MS = 750;   // after the load and the scroll-and-resize probe, the shot lands between hero.js's first two blinks (600–760 and 1100–1260 ms after mount)
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json',
};

function cells() {
  const matrix = THEMES.flatMap(theme => VIEWPORTS.flatMap(viewport => MOTIONS.map(motion => ({
    name: `${theme} ${viewport.name} ${motion}`,
    file: `${theme}-${viewport.name}-${motion}`,
    theme,
    scheme: theme === 'whiteprint' ? 'light' : 'dark',
    viewport,
    motion,
  }))));
  const follow = {
    name: `system-light ${VIEWPORTS[0].name} ${MOTIONS[0]}`,
    file: `system-light-${VIEWPORTS[0].name}-${MOTIONS[0]}`,
    theme: null,
    scheme: 'light',
    viewport: VIEWPORTS[0],
    motion: MOTIONS[0],
  };
  return [...matrix, follow];
}

function finish(verdict, code) {
  console.log(`recorder: ${verdict}`);
  console.log(`EXIT=${code}`);
  process.exitCode = code;
}

async function main(args) {
  const reserved = args.find(arg => arg in RESERVED);
  if (reserved) return finish(`FAIL ${reserved} is reserved for ${RESERVED[reserved]}`, 2);
  if (!args.includes('--check')) return finish('FAIL usage: node site/tools/recorder.mjs --check', 2);

  let chromium;
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    return finish('FAIL playwright is not installed: npm install in site/', 1);
  }
  await rm(OUT, { recursive: true, force: true });
  await mkdir(OUT, { recursive: true });
  const server = await serve(PUBLIC);
  let browser;
  try {
    browser = await chromium.launch();
    const base = `http://127.0.0.1:${server.address().port}/`;
    const all = cells();
    const failed = [];
    let shots = 0;
    for (const cell of all) {
      const { problems, shots: taken } = await runCell(browser, base, cell);
      shots += taken;
      console.log(`${problems.length ? 'FAIL' : 'ok  '} ${cell.name} (${taken} shots)`);
      for (const problem of problems) console.log(`       ${problem}`);
      if (problems.length) failed.push(`${cell.name}: ${problems[0]}`);
    }
    if (failed.length) return finish(`FAIL ${failed.length} of ${all.length} cells; first: ${failed[0]}`, 1);
    finish(`ok (${shots} shots)`, 0);
  } catch (error) {
    finish(`FAIL ${error.message.split('\n')[0]}`, 1);
  } finally {
    await browser?.close();
    server.close();
  }
}

// A static server over site/public on an ephemeral port; nothing outside the root is served.
function serve(root) {
  const server = http.createServer(async (request, response) => {
    let path;
    try {
      path = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    } catch {
      return response.writeHead(400).end();
    }
    const file = normalize(join(root, path.endsWith('/') ? `${path}index.html` : path));
    if (!file.startsWith(root + sep)) return response.writeHead(403).end();
    try {
      const body = await readFile(file);
      response.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(body);
    } catch {
      response.writeHead(404).end();
    }
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function runCell(browser, base, cell) {
  const context = await browser.newContext({
    viewport: { width: cell.viewport.width, height: cell.viewport.height },
    reducedMotion: cell.motion,
    colorScheme: cell.scheme,
  });
  if (cell.theme) await context.addInitScript(pinTheme, cell.theme);
  const page = await context.newPage();
  const problems = [];
  page.on('console', message => { if (message.type() === 'error') problems.push(`console: ${message.text()}`); });
  page.on('pageerror', error => problems.push(`page error: ${error.message}`));
  page.on('requestfailed', request => problems.push(`request failed: ${request.url()}`));
  page.on('response', response => { if (response.status() >= 400) problems.push(`${response.status()}: ${response.url()}`); });

  let shots = 0;
  try {
    await page.goto(base, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready.then(() => true));
    await page.waitForFunction(() => Object.keys(window.scenes ?? {}).length > 0, null, { timeout: SCENES_TIMEOUT_MS });
    await checkPage(page, cell, problems);
    const scenes = await page.evaluate(() => Object.entries(window.scenes).map(([id, scene]) => ({
      id, duration: scene.duration, keyframes: scene.keyframes, captions: scene.captions.map(([, text]) => text), theme: scene.theme,
    })));
    for (const scene of scenes) shots += await checkScene(page, cell, scene, problems);
    await checkGaps(page, cell, scenes, problems);
    if (!cell.theme) await checkReleased(page, problems);
    shots += await checkHero(page, base, cell, problems);
  } catch (error) {
    problems.push(`aborted: ${error.message.split('\n')[0]}`);
  } finally {
    await context.close();
  }
  return { problems, shots };
}

// Runs in the page before its scripts, when <html> may not exist yet.
function pinTheme(theme) {
  const pin = () => { document.documentElement.dataset.theme = theme; };
  if (document.documentElement) return pin();
  new MutationObserver((_, observer) => {
    if (!document.documentElement) return;
    pin();
    observer.disconnect();
  }).observe(document, { childList: true });
}

// R8, R10 (before the story).
async function checkPage(page, cell, problems) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  if (overflow > 0) problems.push(`page: ${overflow}px wider than the viewport`);
  if (!cell.theme && await currentTheme(page) !== null) problems.push(`theme: ${await currentTheme(page)} set before the story`);
  await page.waitForTimeout(ANNOUNCE_SETTLE_MS);
  const announced = await page.evaluate(() => [...document.querySelectorAll('[aria-live]')].map(live => live.textContent).join(''));
  if (announced !== '') problems.push(`announced before the story: "${announced}"`);
}

// R3, R7 (hero), R12, and the hero's screenshot, on hero.html: the hero is not on the story's page.
async function checkHero(page, base, cell, problems) {
  await page.goto(`${base}hero.html`, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready.then(() => true));
  const hero = await page.waitForFunction(() => {
    const box = document.querySelector('#hero svg')?.getBoundingClientRect();
    return box && box.width > 0 && box.height > 0;
  }, null, { timeout: SCENES_TIMEOUT_MS }).then(() => true, () => false);
  if (!hero) {
    problems.push('hero: #hero svg has no bounding box');
    return 0;
  }
  const animations = await page.evaluate(() => document.querySelector('#hero svg').getAnimations({ subtree: true }).length);
  if (cell.motion === 'reduce' && animations > 0) problems.push(`hero: ${animations} animations under reduced motion`);
  await page.evaluate(() => scrollBy(0, 1));
  await page.setViewportSize({ width: cell.viewport.width, height: cell.viewport.height - 1 });
  await page.setViewportSize({ width: cell.viewport.width, height: cell.viewport.height });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForTimeout(HERO_SHOT_AFTER_MS);
  await page.locator('#hero').screenshot({ path: join(OUT, `hero-${cell.file}.png`) });
  return 1;
}

// R2, R4, R5, R6, R7, R10, R13: every key frame reached by scrolling, as a reader would.
async function checkScene(page, cell, scene, problems) {
  const read = [];
  const layouts = [];
  for (const [i, ms] of scene.keyframes.entries()) {
    const frame = await scrollToTime(page, scene.id, ms);
    read.push(frame.caption);
    layouts.push(frame.layout);
    const landed = Math.abs(frame.position - ms);
    if (cell.motion === 'reduce' ? landed !== 0 : landed > KEY_TOLERANCE_MS) {
      problems.push(`${scene.id} @${ms}: landed at ${frame.position}`);
    }
    if (!frame.isActive) problems.push(`${scene.id} @${ms}: not the active scene`);
    const expected = cell.theme ?? themeAt(ms, scene.theme);
    if (frame.theme !== expected) problems.push(`${scene.id} @${ms}: theme ${frame.theme}, expected ${expected}`);
    await page.screenshot({ path: join(OUT, `${scene.id}-${cell.file}-${i + 1}.png`), clip: frame.clip });
  }
  for (const [i, layout] of layouts.entries()) {
    const moved = Object.keys(layout).filter(key => Math.abs(layout[key] - layouts[0][key]) > LAYOUT_TOLERANCE_PX);
    if (moved.length > 0) {
      problems.push(`${scene.id} @${scene.keyframes[i]}: ${moved.map(key => `${key} ${layout[key]}, at the first key frame ${layouts[0][key]}`).join('; ')}`);
    }
  }
  await page.waitForTimeout(ANNOUNCE_SETTLE_MS);
  const announced = await page.evaluate(id => document.querySelector(`[data-scene="${id}"] [aria-live]`).textContent, scene.id);
  if (announced !== read.at(-1)) problems.push(`${scene.id}: announced "${announced}" at the end, showing "${read.at(-1)}"`);
  if (cell.motion === 'reduce') {
    const [first, second] = scene.keyframes;
    const between = await scrollToTime(page, scene.id, (first + second) / 2);
    if (between.position !== first) problems.push(`${scene.id}: between key frames shows ${between.position}, not ${first}`);
  }
  const told = read.filter((caption, i) => caption !== read[i - 1]);
  const mismatch = scene.captions.findIndex((caption, i) => told[i] !== caption);
  if (mismatch !== -1 || told.length !== scene.captions.length) {
    const at = mismatch === -1 ? scene.captions.length : mismatch;
    problems.push(`${scene.id}: caption ${at + 1} reads "${told[at] ?? '(none)'}", declared "${scene.captions[at] ?? '(none)'}"`);
  }
  return scene.keyframes.length;
}

function scrollToTime(page, id, ms) {
  return page.evaluate(async ({ id, ms }) => {
    const scroller = document.querySelector(`[data-scene="${id}"]`);
    const rect = scroller.getBoundingClientRect();
    const travel = rect.height - innerHeight;
    scrollTo({ top: Math.ceil(scrollY + rect.top + travel * ms / window.scenes[id].duration), behavior: 'instant' });
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const stage = scroller.querySelector('.stage');
    const box = stage.getBoundingClientRect();
    const drawing = stage.querySelector(':scope > svg').getBoundingClientRect();
    const controls = stage.querySelector('.controls').getBoundingClientRect();
    return {
      caption: stage.querySelector('.caption').textContent,
      position: Number(stage.querySelector('input[type=range]').value),
      theme: document.documentElement.dataset.theme ?? null,
      isActive: window.scene === window.scenes[id],
      clip: { x: box.x, y: box.y, width: box.width, height: box.height },
      layout: { gap: controls.top - drawing.bottom, x: drawing.x, y: drawing.y, width: drawing.width, height: drawing.height },
    };
  }, { id, ms });
}

// TH4: between two story scenes, reached from the earlier one's end, its theme holds.
async function checkGaps(page, cell, scenes, problems) {
  const order = await page.evaluate(() => [...document.querySelectorAll('#story [data-scene]')].map(scroller => scroller.dataset.scene));
  for (const [i, id] of order.slice(1).entries()) {
    const earlier = scenes.find(scene => scene.id === order[i]);
    await scrollToTime(page, earlier.id, earlier.duration);
    const theme = await page.evaluate(async ({ before, after }) => {
      const top = document.querySelector(`[data-scene="${before}"]`).getBoundingClientRect().bottom;
      const bottom = document.querySelector(`[data-scene="${after}"]`).getBoundingClientRect().top;
      scrollTo({ top: Math.round(scrollY + (top + bottom) / 2 - innerHeight / 2), behavior: 'instant' });
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      return document.documentElement.dataset.theme ?? null;
    }, { before: earlier.id, after: id });
    const expected = cell.theme ?? themeAt(earlier.duration, earlier.theme);
    if (theme !== expected) problems.push(`gap ${earlier.id} → ${id}: theme ${theme}, expected ${expected}`);
  }
}

// R6: past the story, the theme goes back to the system's.
async function checkReleased(page, problems) {
  await page.evaluate(async () => {
    scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
  const theme = await currentTheme(page);
  if (theme !== null) problems.push(`theme: ${theme} still set past the story`);
}

function currentTheme(page) {
  return page.evaluate(() => document.documentElement.dataset.theme ?? null);
}

await main(process.argv.slice(2));
