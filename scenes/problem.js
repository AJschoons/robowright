// The problem scene: the Owner before the project, at a desk, being the loop. Outside the story, so
// it pins no theme.
import { blinks } from '../kit-core.js';
import {
  grid, frame, titleBlockRows, robot, groundHatch, desk, monitor, seatedOwner, bubble, wallClock, enterKey, hat,
} from './parts.js';

const T = 12000;
const WIDTH = 800;
const HEIGHT = 480;
const ROBOT_WEIGHTS = { line: 4, brace: 4.4 };
const SHEETS_AT = [0, 3700, 4300, 4900, 6700, 7100, 7500, 7900, 8300];   // the REVIEW pile, one sheet each
const SHEET = 7;
const SCREEN_LINES_AT = [0, 0, 0, 3400, 4200, 5000, 6800];
const BUBBLES_GONE = [9600, 10000];

// Each bubble's tail tip, laid out again at phone width, where bubbles grow ×1.6 and the title block ×2.
const BUBBLES = [
  { text: 'Done. Review?', at: 0, wide: [490, 190], narrow: [480, 212] },
  { text: 'Summary?', at: 3600, wide: [500, 144], narrow: [296, 150] },
  { text: 'Cheaper model?', at: 4600, wide: [630, 250], narrow: [588, 262] },
  { text: 'Next session?', at: 6900, wide: [640, 204], narrow: [236, 100] },
  { text: 'Done. Review?', at: 7600, wide: [650, 158], narrow: [596, 318] },
  { text: 'Summary?', at: 8200, wide: [600, 300], narrow: [160, 184] },
];

// The clock on the wall, from 9:05 in the morning to 3:25 in the afternoon, at the hands' angles
// from twelve; [ms, hour hand, minute hand].
const CLOCK = [[0, 272.5, 30], [3300, 272.5, 30], [5300, 350, 960], [6600, 350, 960], [8500, 460, 2280], [9500, 460, 2280], [11000, 462.5, 2310]];

const part = name => `[data-part="${name}"]`;
const rot = degrees => ({ transform: `rotate(${degrees}deg)` });
const at = (x, y) => ({ transform: `translate(${x}px, ${y}px)` });
const shown = { opacity: 1 };
const hidden = { opacity: 0 };

function screen() {
  const lines = SCREEN_LINES_AT.map((_, i) => `<path data-part="line-${i + 1}" d="M16 ${20 + i * 12}H${56 + ((i * 37) % 70)}" class="ln" style="stroke-width:2.2;stroke:var(--faint)" opacity="0"/>`);
  return `
    ${lines.join('')}
    <path d="M16 98l6 4l-6 4" class="ln" style="stroke-width:2.2"/><rect x="28" y="96" width="7" height="12" class="brass"/>
    <g transform="translate(150 46) scale(.42)" data-part="claude">${robot('', ROBOT_WEIGHTS)}</g>`;
}

function pile() {
  const sheets = SHEETS_AT.map((_, i) => `<rect data-part="sheet-${i + 1}" x="${494 + (i % 2) * 3}" y="${323 - (i + 1) * SHEET}" width="54" height="${SHEET}" rx="1" class="paper" style="stroke:var(--fg);stroke-width:2" opacity="0"/>`);
  return `
    ${sheets.join('')}
    <g data-part="pile-label"><g transform="translate(522 308)"><g class="grow-narrow"><text text-anchor="middle" class="lbl">REVIEW</text></g></g></g>`;
}

function bubbles() {
  return BUBBLES.map(({ text, wide, narrow }, i) => `
    <g class="wide-only" transform="translate(${wide[0]} ${wide[1]})">${bubble(`bubble-${i + 1}-wide`, text)}</g>
    <g class="narrow-only" transform="translate(${narrow[0]} ${narrow[1]})">${bubble(`bubble-${i + 1}-narrow`, text)}</g>`).join('');
}

function draw() {
  return `
    ${grid('problem', WIDTH, HEIGHT)}
    ${frame(WIDTH, HEIGHT, 10)}
    ${titleBlockRows(776, 24, 'BEFORE', 'YOUR DESK', null)}
    <g transform="translate(80 90)">${wallClock('clock')}</g>
    ${groundHatch(20, 780, 430, 20)}
    <g transform="translate(190 330)">${desk()}</g>
    <g transform="translate(284 190)">${monitor('screen')}${screen()}</g>
    <g transform="translate(236 330)">${enterKey('enter')}</g>
    ${pile()}
    <g transform="translate(160 350)">${seatedOwner('owner', { wearsHat: false })}</g>
    <g transform="translate(575 327)">${hat('hat')}</g>
    ${bubbles()}`;
}

// The Enter key: a tap is down and up again; a hold keeps it down across a key frame.
const UP = 'up';
const DOWN = 'down';
const tap = t => [[t, UP], [t + 90, DOWN], [t + 220, UP]];
const hold = (from, to) => [[from, UP], [from + 90, DOWN], [to, DOWN], [to + 130, UP]];
const PRESSES = [
  [0, UP], ...tap(3400), ...tap(3800), ...tap(4200), ...tap(4600), ...tap(5000), ...hold(5300, 5900),
  ...tap(6300), ...tap(6700), ...tap(7100), ...tap(7500), ...tap(7900), ...hold(8500, 9100),
];

function loop(track) {
  for (const [i, { at: from }] of BUBBLES.entries()) {
    const pop = { opacity: 0, transform: 'scale(.6)' };
    const full = { opacity: 1, transform: 'scale(1)' };
    const gone = { opacity: 0, transform: 'scale(.9)' };
    const frames = from === 0 ? [[0, full]] : [[from, pop], [from + 250, full]];
    for (const copy of ['wide', 'narrow']) {
      track(part(`bubble-${i + 1}-${copy}`), [...frames, [BUBBLES_GONE[0], full], [BUBBLES_GONE[1], gone]]);
    }
  }
  track(part('enter'), PRESSES.map(([t, state]) => [t, { transform: state === DOWN ? 'scaleY(.75)' : 'scaleY(1)' }]));
  track(part('enter-press'), PRESSES.map(([t, state]) => [t, state === DOWN ? shown : hidden]));
  for (const [i, from] of SHEETS_AT.entries()) {
    track(part(`sheet-${i + 1}`), from === 0 ? [[0, shown]] : [[from, hidden], [from + 150, shown]]);
  }
  track(part('pile-label'), SHEETS_AT.flatMap((from, i) => (i === 0 ? [[0, at(0, 0)]] : [[from, at(0, -(i - 1) * SHEET)], [from + 150, at(0, -i * SHEET)]])));
  for (const [i, from] of SCREEN_LINES_AT.entries()) {
    track(part(`line-${i + 1}`), from === 0 ? [[0, shown]] : [[from, hidden], [from + 200, shown]]);
  }
  track(`${part('claude')} .eyes`, blinks([1200, 4100, 7300, 10400]));
  track(part('clock-hour'), CLOCK.map(([t, hour]) => [t, rot(hour)]));
  track(part('clock-minute'), CLOCK.map(([t, , minute]) => [t, rot(minute)]));
}

// The Owner squints and types through the loop, then sits back, has the idea and picks up the hat.
function owner(track) {
  track(part('owner-open'), [[0, shown], [3300, shown], [3600, hidden], [9400, hidden], [9700, shown]]);
  track(part('owner-squint'), [[0, hidden], [3300, hidden], [3600, shown], [9400, shown], [9700, hidden]]);
  track(part('owner-rest'), [[0, shown], [3200, shown], [3300, hidden], [9300, hidden], [9400, shown], [9800, shown], [9900, hidden]]);
  track(part('owner-type'), [[0, hidden], [3200, hidden], [3300, shown], [9300, shown], [9400, hidden]]);
  track(part('owner-reach'), [[0, hidden], [9800, hidden], [9900, shown]]);
  track(part('owner-sweat'), [[0, hidden], [6500, hidden], [7200, shown], [9400, shown], [9700, hidden]]);
  track(part('owner-bulb'), [[0, hidden], [9900, hidden], [10600, shown]]);
  track(part('hat'), [[0, at(0, 0)], [9900, at(0, 0)], [10400, at(-170, -170)], [10900, at(-343, -67)]]);
}

export default {
  duration: T,
  keyframes: [0, 5600, 8800, 11400],
  captions: [
    [0, 'Give Claude Code a long task and it ends the same way every time: it\'s your turn again.'],
    [3000, 'Review the work. Pick a cheaper model for the easy parts. Ask for a summary. Start the next session. Enter.'],
    [6500, 'Useful work is happening. Your part of it is pressing Enter.'],
    [9500, 'What if the loop ran without you, and only the real decisions came back?'],
  ],
  theme: null,
  viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
  draw,
  choreograph(track) {
    loop(track);
    owner(track);
  },
};
