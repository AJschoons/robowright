// The scene kit: a seekable timeline per scene, driven by the page's scroll position.
// Play, the key-frame buttons and the scrubber all move the scroll position, so scroll stays the
// one source of the frame and nothing jumps when the reader scrolls again.
import {
  keyframeOffsets, snapToKeyframe, captionAt, clockAt, themeAt, holdsTheme, progressOf,
  nextKeyframe, previousKeyframe, reducedScrubTarget, playStart,
} from './kit-core.js';

const LABELS = {
  play: 'Play',
  pause: 'Pause',
  previous: 'Previous key frame',
  next: 'Next key frame',
  position: 'Scene position',
};
const ICONS = {
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  pause: '<path d="M6.5 4.5h4v15h-4zM13.5 4.5h4v15h-4z"/>',
  previous: '<path d="M5 4.5h3v15H5zM20 4.5v15L9 12z"/>',
  next: '<path d="M16 4.5h3v15h-3zM4 4.5v15L15 12z"/>',
};
const ANNOUNCE_AFTER_MS = 700;    // a fast scrub announces only the caption it settles on
const REDUCED_STEP_MS = 1600;     // how long play holds each key frame under reduced motion
const KEY_TOLERANCE_MS = 20;      // one scroll pixel is about 4 ms of a 13 s scene
const SCRUB_STEP_MS = 10;

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const narrowScreen = matchMedia('(max-width: 560px)');   // kit.css's narrow breakpoint
const pinnedTheme = document.documentElement.dataset.theme ?? null;   // set before load, it holds (the recorder's theme matrix)
const story = document.getElementById('story');
const mounts = [];
let active = null;
let frameRequested = false;
let themeSetByKit = false;

window.scenes = {};
window.scene = null;

export function createTimeline(T) {
  const animations = [];
  let now = 0;
  return {
    duration: T,
    get now() { return now; },
    track(el, frames) {
      const animation = el.animate(keyframeOffsets(frames, T), { duration: T, fill: 'both' });
      animation.pause();
      animations.push(animation);
    },
    seek(ms) {
      now = Math.max(0, Math.min(T, ms));
      for (const animation of animations) animation.currentTime = now;
      return now;
    },
  };
}

// `scroller` is a [data-scene] element holding a .stage; `scene` is a module from scenes/.
export function mountScene(scroller, scene) {
  const id = scroller.dataset.scene;
  const stage = scroller.querySelector('.stage');
  const svg = stage.querySelector('svg');
  svg.innerHTML = scene.draw();
  followViewBox(svg, scene.viewBox);

  const timeline = createTimeline(scene.duration);
  scene.choreograph((target, frames) => timeline.track(resolveTarget(svg, target), frames));

  const mount = { id, scroller, scene, timeline, view: buildView(stage, svg, scene), playing: false };
  mount.seek = ms => render(mount, timeline.seek(ms));
  wireControls(mount);
  mounts.push(mount);
  window.scenes[id] = {
    seek: mount.seek,
    duration: scene.duration,
    keyframes: scene.keyframes,
    captions: scene.captions,
    theme: scene.theme,
  };
  mount.seek(0);
  requestFrame();
  return window.scenes[id];
}

// `viewBox` is one view box, or { wide, narrow } for a drawing laid out again at phone width.
export function followViewBox(svg, viewBox) {
  const fit = () => {
    const box = typeof viewBox === 'string' ? viewBox : viewBox[narrowScreen.matches ? 'narrow' : 'wide'];
    svg.setAttribute('viewBox', box);
  };
  fit();
  narrowScreen.addEventListener('change', fit);
}

function resolveTarget(svg, target) {
  const el = typeof target === 'string' ? svg.querySelector(target) : target;
  if (!el) throw new Error(`scene track: nothing matches ${target}`);
  return el;
}

function buildView(stage, svg, scene) {
  const caption = stage.querySelector('.caption');
  caption.setAttribute('aria-hidden', 'true');
  const live = document.createElement('p');
  live.className = 'visually-hidden';
  live.setAttribute('aria-live', 'polite');
  stage.append(live);

  const controls = document.createElement('div');
  controls.className = 'controls';
  controls.innerHTML = `
    ${controlButton('previous')}${controlButton('play')}${controlButton('next')}
    <input type="range" min="0" max="${scene.duration}" step="${SCRUB_STEP_MS}" value="0" aria-label="${LABELS.position}">`;
  caption.before(controls);

  return {
    caption,
    live,
    clock: svg.querySelector('[data-clock]'),
    play: controls.querySelector('[data-action=play]'),
    previous: controls.querySelector('[data-action=previous]'),
    next: controls.querySelector('[data-action=next]'),
    scrubber: controls.querySelector('input'),
    announced: '',
    announceTimer: 0,
  };
}

function controlButton(action) {
  return `<button type="button" class="ctl" data-action="${action}" aria-label="${LABELS[action]}">${icon(action)}</button>`;
}

function icon(action) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[action]}</svg>`;
}

function render(mount, now) {
  const { scene, view } = mount;
  const caption = captionAt(now, scene.captions);
  if (view.caption.textContent !== caption) view.caption.textContent = caption;
  if (mount === active && caption !== view.announced) announce(view, caption);
  if (view.clock) view.clock.textContent = clockAt(now, scene.clock);
  view.scrubber.value = String(now);
  if (mount !== active) return;
  const theme = themeAt(now, scene.theme);
  if (theme === null) releaseTheme();
  else applyTheme(theme);
}

// Only the active scene speaks, so a scene seeking off-screen announces nothing.
function announce(view, caption) {
  view.announced = caption;
  clearTimeout(view.announceTimer);
  view.announceTimer = setTimeout(() => { view.live.textContent = caption; }, ANNOUNCE_AFTER_MS);
}

function applyTheme(name) {
  if (pinnedTheme) return;
  themeSetByKit = true;
  if (document.documentElement.dataset.theme !== name) document.documentElement.dataset.theme = name;
}

function releaseTheme() {
  if (!themeSetByKit) return;
  themeSetByKit = false;
  delete document.documentElement.dataset.theme;
}

// Scroll driver: any number of scroll events, one seek per animation frame.
function requestFrame() {
  if (frameRequested) return;
  frameRequested = true;
  requestAnimationFrame(drive);
}

function drive() {
  frameRequested = false;
  const middle = innerHeight / 2;
  const placed = mounts.map(mount => ({ mount, rect: mount.scroller.getBoundingClientRect() }));
  const storyRect = story?.getBoundingClientRect();   // a page without #story (hero.html) holds nothing
  const centred = placed.find(({ rect }) => rect.top <= middle && rect.bottom >= middle);
  active = centred ? centred.mount : null;
  window.scene = active ? window.scenes[active.id] : null;
  const isHeld = storyRect !== undefined && holdsTheme(storyRect.top, storyRect.bottom, middle);
  if (!active && !isHeld) releaseTheme();

  for (const { mount, rect } of placed) {
    const t = progressOf(rect.top, rect.height, innerHeight) * mount.scene.duration;
    const target = reducedMotion.matches ? snapToKeyframe(t, mount.scene.keyframes) : t;
    if (mount === active || target !== mount.timeline.now) mount.seek(target);
  }
}

function onScroll() {
  for (const mount of mounts) {
    const movedByReader = mount.expectedY !== undefined && Math.abs(scrollY - mount.expectedY) > 2;
    if (mount.playing && movedByReader) setPlaying(mount, false);
  }
  requestFrame();
}

function scrollToTime(mount, ms) {
  const rect = mount.scroller.getBoundingClientRect();
  const travel = rect.height - innerHeight;
  const y = Math.ceil(scrollY + rect.top + travel * ms / mount.scene.duration);
  mount.expectedY = y;
  scrollTo({ top: y, behavior: 'instant' });
}

// Controls
function wireControls(mount) {
  const { view } = mount;
  view.play.addEventListener('click', () => setPlaying(mount, !mount.playing));
  view.previous.addEventListener('click', () => {
    stepTo(mount, previousKeyframe(mount.timeline.now, mount.scene.keyframes, KEY_TOLERANCE_MS));
  });
  view.next.addEventListener('click', () => {
    stepTo(mount, nextKeyframe(mount.timeline.now, mount.scene.keyframes, KEY_TOLERANCE_MS) ?? mount.timeline.now);
  });
  view.scrubber.addEventListener('input', () => scrubTo(mount, Number(view.scrubber.value)));
}

function scrubTo(mount, value) {
  const now = mount.timeline.now;
  const target = reducedMotion.matches ? reducedScrubTarget(value, now, mount.scene.keyframes) : value;
  mount.view.scrubber.value = String(target);
  stepTo(mount, target);
}

function stepTo(mount, ms) {
  setPlaying(mount, false);
  scrollToTime(mount, ms);
}

function setPlaying(mount, isPlaying) {
  mount.playing = isPlaying;
  cancelAnimationFrame(mount.raf);
  const state = isPlaying ? 'pause' : 'play';
  mount.view.play.setAttribute('aria-label', LABELS[state]);
  mount.view.play.innerHTML = icon(state);
  if (!isPlaying) return;

  const { now } = mount.timeline;
  mount.playhead = playStart(now, mount.scene.duration, mount.scene.keyframes, reducedMotion.matches, KEY_TOLERANCE_MS);
  mount.expectedY = scrollY;   // a reader's scroll before the first step pauses play
  if (mount.playhead !== now) scrollToTime(mount, mount.playhead);
  mount.lastTick = performance.now();
  mount.raf = requestAnimationFrame(ts => tick(mount, ts));
}

function tick(mount, ts) {
  if (!mount.playing) return;
  const isFinished = reducedMotion.matches ? stepReduced(mount, ts) : advance(mount, ts);
  if (isFinished) return setPlaying(mount, false);
  mount.raf = requestAnimationFrame(next => tick(mount, next));
}

function advance(mount, ts) {
  mount.playhead = Math.min(mount.scene.duration, mount.playhead + (ts - mount.lastTick));
  mount.lastTick = ts;
  scrollToTime(mount, mount.playhead);
  return mount.playhead >= mount.scene.duration;
}

function stepReduced(mount, ts) {
  if (ts - mount.lastTick < REDUCED_STEP_MS) return false;
  mount.lastTick = ts;
  const next = nextKeyframe(mount.timeline.now, mount.scene.keyframes, KEY_TOLERANCE_MS);
  if (next === null) return true;
  mount.playhead = next;
  scrollToTime(mount, next);
  return false;
}

addEventListener('scroll', onScroll, { passive: true });
addEventListener('resize', requestFrame);
reducedMotion.addEventListener('change', requestFrame);
