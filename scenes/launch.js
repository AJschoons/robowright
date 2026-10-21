// The launch beat: a Lead takes the brief and starts the first Worker; the Owner walks away.
import { alternate, blinks } from '../kit-core.js';
import { grid, frame, titleBlockRows, robot, clipboard, wrench, person, groundHatch, worktreeSign, sparks, floor, ownerLine } from './parts.js';

const T = 12000;
const WIDTH = 800;
const HEIGHT = 480;
const NARROW_HEIGHT = 560;    // room under the ground for the worktree sign, grown for phone width
const INSET = 10;
const LEAD_WEIGHTS = { line: 3.2, brace: 4.4 };
const WORKER_WEIGHTS = { line: 5, brace: 6.6 };
const BRANCH = 'robowright/sample-001-search-index';

const OWNER_X = 110;
const LEAD = { x: 280, y: 368 };    // high enough that the clipboard clears the ground
const WORKER = { x: 540, y: 406, from: -110 };
const BRIEF_FROM = { x: 150, y: 352 };
const BRIEF_TO = { x: 62, y: 40 };    // onto the Lead's clipboard

const BUILDING = { left: 470, width: 220, floor: 56 };
const FLOOR1_CEILING_AT_HANDOFF = 0.3;    // floor 1's ceiling drawn where build.js opens, walls up; keep equal to its FLOOR1_CEILING_AT_OPEN

// The Owner slides off the left edge a step at a time; the theme flips as they cross the frame.
const WALK = { from: 4400, to: 6200, distance: 180 };
const STEP_MS = 100;
const BOB = 4;
const T_FLIP = WALK.from + (OWNER_X - INSET) * (WALK.to - WALK.from) / WALK.distance;

const PIVOT = 'transform-box:view-box;transform-origin:0 0';

const part = name => `[data-part="${name}"]`;
const rot = degrees => ({ transform: `rotate(${degrees}deg)` });
const at = (x, y) => ({ transform: `translate(${x}px, ${y}px)` });
const facing = sign => ({ transform: `scale(${sign * 0.9}, 0.9)` });
const drawn = (length, fraction) => ({ strokeDashoffset: length * (1 - fraction) });

function briefSheet() {
  return `
    <g data-part="brief">
      <path d="M-13 -16H8L14 -10V16H-13Z" class="paper" style="stroke:var(--fg);stroke-width:2.4"/>
      <path d="M-8 -6H8M-8 1H8M-8 8H3" class="ln thin"/>
    </g>`;
}

function building() {
  const { left, width, floor: height } = BUILDING;
  const right = left + width;
  const ground = 430;
  const roof = ground - 3 * height;
  return `
    <path d="M${left - 10} ${roof}L${left + width / 2} ${roof - 50}L${right + 10} ${roof}" class="ln dash faint"/>
    ${floor({ x: left, y: roof, width, height, storeys: 3, look: 'ln dash faint' })}`;
}

// The worktree: a dashed building with its branch on a sign, above the roof at full width and
// under the ground at phone width.
function worktree() {
  const { left, width } = BUILDING;
  const apex = 430 - 3 * BUILDING.floor - 50;
  return `
    <g data-part="worktree" opacity="0">
      ${building()}
      <g class="wide-only">
        <path d="M${left + width / 2} ${apex - 14}V${apex}" class="ln thin"/>
        <g transform="translate(${left - 15} ${apex - 40})">${worktreeSign(BRANCH)}</g>
      </g>
      <g class="narrow-only"><g transform="translate(40 482)">${worktreeSign(BRANCH)}</g></g>
    </g>`;
}

function draw() {
  const floor1Top = 430 - BUILDING.floor;
  return `
    ${grid('launch', WIDTH, NARROW_HEIGHT)}
    <clipPath id="launch-clip"><rect x="12" y="12" width="776" height="${NARROW_HEIGHT - 24}"/></clipPath>
    <g class="wide-only">${frame(WIDTH, HEIGHT, INSET)}</g>
    <g class="narrow-only">${frame(WIDTH, NARROW_HEIGHT, INSET)}</g>
    ${titleBlockRows(776, 24, 'SAMPLE', 'ELAPSED <tspan data-clock>00:00</tspan>', 'launch-clock')}
    ${worktree()}
    ${floor({ x: BUILDING.left, y: floor1Top, width: BUILDING.width, height: BUILDING.floor, look: 'ln', part: 'floor1', outline: 'rise' })}
    ${groundHatch(20, 780, 430, 20)}
    <text x="${LEAD.x}" y="462" class="lbl" text-anchor="middle">LEAD</text>
    <text data-part="worker-label" x="${WORKER.x}" y="462" class="lbl" text-anchor="middle" opacity="0">WORKER</text>
    <g class="wide-only">${ownerLine(20, 780, 448, 120, 'owner')}</g>
    <g class="narrow-only">${ownerLine(20, 780, 472, 700, 'owner')}</g>

    <g clip-path="url(#launch-clip)">
      <g transform="translate(${OWNER_X} 430)"><g data-part="owner">${person()}</g></g>
    </g>
    <g transform="translate(${LEAD.x} ${LEAD.y})"><g data-part="lead" transform="scale(-.9 .9)" style="${PIVOT}">${robot(clipboard(), LEAD_WEIGHTS)}</g></g>
    <g transform="translate(${WORKER.x} ${WORKER.y})"><g data-part="worker-move" opacity="0">
      <g transform="scale(.5)" data-part="worker">${robot(wrench(), WORKER_WEIGHTS)}</g>
    </g></g>
    <g transform="translate(${WORKER.x + 50} ${WORKER.y - 12})">${sparks('sparks')}</g>
    <g transform="translate(${BRIEF_FROM.x} ${BRIEF_FROM.y})">${briefSheet()}</g>`;
}

// The Owner hands the brief over; the Lead turns to the worktree and starts a Worker in it.
function handover(track) {
  track(part('brief'), [
    [300, { opacity: 1, ...at(0, 0) }], [1100, { opacity: 1, ...at(BRIEF_TO.x, BRIEF_TO.y) }],
    [1700, { opacity: 1, ...at(BRIEF_TO.x, BRIEF_TO.y) }], [1850, { opacity: 0, ...at(BRIEF_TO.x, BRIEF_TO.y) }],
  ]);
  track(part('lead'), [[1700, facing(-1)], [1950, facing(1)]]);
  track(`${part('lead')} .eyes`, blinks([800, 3300, 7000, 10200]));
  track(`${part('lead')} .ant`, [
    [0, { opacity: 1 }], ...alternate(2400, 2850, 150, { opacity: 1 }, { opacity: 0.25 }), [2900, { opacity: 1 }],
  ]);
  track(part('worktree'), [[1900, { opacity: 0 }], [2400, { opacity: 1 }]]);
  track(part('worker-move'), [
    [2700, { opacity: 0, ...at(WORKER.from, 0) }], [3000, { opacity: 1, ...at(WORKER.from, 0) }],
    [3400, { opacity: 1, ...at(WORKER.from / 2, -6) }], [3800, { opacity: 1, ...at(0, 0) }],
  ]);
  track(part('worker-label'), [[3500, { opacity: 0 }], [3800, { opacity: 1 }]]);
}

// The Owner slides left in steps, bobbing on alternate ones; the title block's clock row fades in just before the flip.
function walkOff(track) {
  const frames = [[WALK.from, at(0, 0)]];
  for (let t = WALK.from + STEP_MS, step = 1; t <= WALK.to; t += STEP_MS, step++) {
    const x = -WALK.distance * (t - WALK.from) / (WALK.to - WALK.from);
    frames.push([t, at(x, step % 2 ? -BOB : 0)]);
  }
  track(part('owner'), frames);
  track(part('launch-clock'), [[T_FLIP - 500, { opacity: 0 }], [T_FLIP - 200, { opacity: 1 }]]);
}

// Without the Owner, the Worker puts floor 1's walls up and starts its ceiling.
function work(track) {
  track(`${part('worker')} .swing`, [[0, rot(0)], ...alternate(6600, 11800, 500, rot(-28), rot(14)), [12000, rot(0)]]);
  track(`${part('worker')} .eyes`, blinks([4200, 8300, 11000]));
  track(part('sparks'), [
    [0, { opacity: 0 }], ...alternate(6800, 11600, 400, { opacity: 0 }, { opacity: 1 }), [11700, { opacity: 0 }],
  ]);
  track(part('floor1-walls'), [[6600, drawn(BUILDING.floor, 0)], [9400, drawn(BUILDING.floor, 1)]]);
  track(part('floor1-ceiling'), [[9600, drawn(BUILDING.width, 0)], [12000, drawn(BUILDING.width, FLOOR1_CEILING_AT_HANDOFF)]]);
}

export default {
  duration: T,
  keyframes: [1200, 3900, T_FLIP - 100, WALK.to + 200, 9600],
  captions: [
    [0, 'A Lead session takes the brief and starts the first Worker in a worktree of its own.'],
    [4300, 'The Owner walks away. The clock starts.'],
    [7400, "From here, everything above the Owner's line is decided and written down without them."],
  ],
  theme: [[0, 'whiteprint'], [T_FLIP, 'blueprint']],
  clock: [[0, 0], [T, 0]],
  viewBox: { wide: `0 0 ${WIDTH} ${HEIGHT}`, narrow: `0 0 ${WIDTH} ${NARROW_HEIGHT}` },
  draw,
  choreograph(track) {
    handover(track);
    walkOff(track);
    work(track);
  },
};
