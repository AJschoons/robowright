// The glance: the Owner on other work, hat on, looks up at the dashboard on the wall once and goes
// back to work.
import { grid, frame, titleBlock, groundHatch, desk, monitor, seatedOwner, dashboardBar } from './parts.js';

const T = 10000;
const WIDTH = 800;
const HEIGHT = 480;
const SCREEN_LINES_AT = [0, 0, 0, 900, 2600, 7400, 8200];
const LOOK_UP = -24;   // degrees the head turns, to face the dashboard above the desk

const part = name => `[data-part="${name}"]`;
const rot = degrees => ({ transform: `rotate(${degrees}deg)` });
const fill = share => ({ transform: `scaleX(${share})` });
const shown = { opacity: 1 };
const hidden = { opacity: 0 };

function screen() {
  const lines = SCREEN_LINES_AT.map((_, i) => `<path data-part="line-${i + 1}" d="M16 ${20 + i * 12}H${44 + ((i * 29) % 52)}" class="ln" style="stroke-width:2.2;stroke:var(--faint)" opacity="0"/>`);
  return `
    ${lines.join('')}
    <rect x="120" y="18" width="48" height="30" rx="3" class="ln thin"/><rect x="120" y="74" width="48" height="30" rx="3" class="ln thin"/>
    <path d="M144 48V74" class="ln thin"/>`;
}

// The dashboard on the wall, 380 by 104 from its top-left corner; its labels grow at phone width.
function dashboard() {
  return `
    <path d="M190 -14V0" class="ln thin"/>
    <rect width="380" height="104" rx="6" class="paper" style="stroke:var(--fg);stroke-width:3"/>
    <g transform="translate(16 28)"><g class="grow-narrow"><text class="lbl" style="fill:var(--fg)">SAMPLE · SEARCH</text></g></g>
    <g transform="translate(16 40)">${dashboardBar('bar', ['done', 'done', 'working'])}</g>
    <g transform="translate(16 92)"><g class="grow-narrow"><text class="lbl">2 OF 3 SIGNED OFF · 1 WORKING</text></g></g>
    <rect data-part="dashboard-mark" x="-10" y="-10" width="400" height="124" rx="10" style="fill:none;stroke:var(--brass);stroke-width:3;stroke-dasharray:10 8" opacity="0"/>`;
}

function draw() {
  return `
    ${grid('glance', WIDTH, HEIGHT)}
    ${frame(WIDTH, HEIGHT, 10)}
    ${titleBlock(776, 24, 'SAMPLE', 'ELAPSED', '02:52')}
    <g transform="translate(30 36)">${dashboard()}</g>
    ${groundHatch(20, 780, 430, 20)}
    <g transform="translate(190 330)">${desk()}</g>
    <g transform="translate(284 190)">${monitor('screen')}${screen()}</g>
    <rect x="202" y="322" width="68" height="8" rx="2" class="paper" style="stroke:var(--fg);stroke-width:2"/>
    <g transform="translate(160 350)">${seatedOwner('owner', { wearsHat: true })}</g>`;
}

export default {
  duration: T,
  keyframes: [0, 5400, 9000],
  captions: [
    [0, 'Meanwhile, the Owner is on something else. The dashboard is the only thing to check.'],
    [3600, 'Two units signed off, one in progress, nothing waiting on them. Back to work.'],
    [7200, 'If the project stops, it says so here.'],
  ],
  theme: 'blueprint',
  clock: [[0, 172], [T, 205]],
  viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
  draw,
  // The Owner types, looks up at the dashboard, and types again; the third segment grows while the Owner types.
  choreograph(track) {
    track(part('owner-head'), [[0, rot(0)], [3800, rot(0)], [4300, rot(LOOK_UP)], [6400, rot(LOOK_UP)], [6900, rot(0)]]);
    track(part('owner-type'), [[0, shown], [3700, shown], [3800, hidden], [6900, hidden], [7000, shown]]);
    track(part('owner-rest'), [[0, hidden], [3700, hidden], [3800, shown], [6900, shown], [7000, hidden]]);
    track(part('bar-3'), [[0, fill(0.35)], [2400, fill(0.35)], [3000, fill(0.55)], [7600, fill(0.55)], [8200, fill(0.8)]]);
    track(part('dashboard-mark'), [[0, hidden], [7400, hidden], [7800, shown]]);
    for (const [i, from] of SCREEN_LINES_AT.entries()) {
      track(part(`line-${i + 1}`), from === 0 ? [[0, shown]] : [[from, hidden], [from + 200, shown]]);
    }
  },
};
