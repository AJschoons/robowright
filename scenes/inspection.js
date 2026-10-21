// The inspection beat: unit 2 is built, held, fixed, re-inspected and signed off; then unit 3 starts.
import { alternate, blinks } from '../kit-core.js';
import {
  grid, frame, titleBlock, robot, wrench, stamp, ladder, groundHatch, stampHold, stampAdvance, sheet, sparks, floor, pane, check,
} from './parts.js';

const T = 13000;
const WIDTH = 800;
const HEIGHT = 480;
const NARROW_HEIGHT = 590;    // room under the ground for the unit names at phone width
const ROBOT_WEIGHTS = { line: 5, brace: 6.6 };
const STOREY = { width: 320, height: 80 };
const FLOOR3_WALLS_AT_END = 0.6;    // unit 3's walls drawn where the inspection ends; door.js opens further along, at its FLOOR3_CEILING_AT_OPEN

const UNITS = [
  { label: 'UNIT 3', name: 'highlight-matches', top: 190 },
  { label: 'UNIT 2', name: 'search-bar', top: 270 },
  { label: 'UNIT 1', name: 'search-index', top: 350 },
];

const part = name => `[data-part="${name}"]`;
const rot = degrees => ({ transform: `rotate(${degrees}deg)` });
const at = (x, y) => ({ transform: `translate(${x}px, ${y}px)` });
const drawn = (length, fraction) => ({ strokeDashoffset: length * (1 - fraction) });

function unitLabels() {
  return UNITS.map(({ label, name, top }, row) => `
    <text x="24" y="${top + 36}" class="lbl">${label}</text>
    <text x="24" y="${top + 53}" class="lbl name wide-only">${name}</text>
    <g class="narrow-only">
      <text x="40" y="${505 + row * 30}" class="lbl">${label}</text>
      <text x="170" y="${505 + row * 30}" class="lbl">${name}</text>
    </g>`).join('');
}

function building() {
  return `
    <path d="M170 190L340 128L510 190" class="ln dash faint"/>
    ${floor({ x: 180, y: 190, width: 320, height: 80, outline: 'open-bottom', look: 'ln dash faint' })}
    ${floor({ x: 180, y: 190, width: 320, height: 80, look: 'ln', part: 'unit3', outline: 'rise' })}
    ${floor({ x: 180, y: 270, width: 320, height: 80, look: 'ln dash faint' })}
    <rect data-part="unit2-hold" x="180" y="270" width="320" height="80" class="holdfill" opacity="0"/>
    <rect data-part="unit2-fill" x="180" y="270" width="320" height="80" class="donefill" opacity="0"/>
    ${floor({ x: 180, y: 270, width: 320, height: 80, look: 'ln', part: 'unit2', outline: 'rise' })}
    ${floor({ x: 180, y: 350, width: 320, height: 80, fill: 'donefill', look: 'ln' })}
    <rect x="210" y="372" width="44" height="30" class="ln thin"/>
    <rect x="426" y="372" width="44" height="30" class="ln thin"/>
    <rect x="320" y="384" width="40" height="46" class="ln thin"/>
    <path d="M329 406L337 414L352 398" class="doneln"/>
    <g data-part="unit2-pane1" opacity="0">${pane(210, 292)}</g>
    <g data-part="unit2-pane2" opacity="0">${pane(426, 292)}</g>
    <g data-part="unit2-check" opacity="0">${check(340, 310)}</g>`;
}

function draw() {
  return `
    ${grid('inspection', WIDTH, NARROW_HEIGHT)}
    <clipPath id="inspection-clip"><rect x="12" y="12" width="776" height="456"/></clipPath>
    <g class="wide-only">${frame(WIDTH, HEIGHT, 10)}</g>
    <g class="narrow-only">${frame(WIDTH, NARROW_HEIGHT, 10)}</g>
    ${titleBlock(776, 24, 'SAMPLE', 'ELAPSED', '02:10')}

    <path d="M150 190V430M144 190H156M144 270H156M144 350H156M144 430H156" class="ln thin faint"/>
    ${unitLabels()}
    ${building()}
    ${groundHatch(20, 780, 430, 20)}
    ${ladder(565, 605, 160, 430, 180, 25)}
    <text x="620" y="424" class="lbl">REVIEWER</text>
    <text x="196" y="462" class="lbl wide-only">ONE PROJECT · ONE WORKTREE · ONE GATE PER UNIT</text>
    <text x="40" y="465" class="lbl narrow-only">ONE PROJECT · ONE WORKTREE · ONE GATE PER UNIT</text>

    <g transform="translate(410 312)">${stampHold('hold', 'HOLD')}</g>
    <g transform="translate(410 312)">${stampAdvance('advance', 'ADVANCE')}</g>
    <g transform="translate(520 300)">${sheet('note')}</g>
    <g transform="translate(300 310)">${sparks('sparks')}</g>

    <g clip-path="url(#inspection-clip)">
      <g transform="translate(250 322)"><g data-part="worker-move"><g transform="scale(.5)" data-part="worker">${robot(wrench(), ROBOT_WEIGHTS)}</g></g></g>
      <g transform="translate(585 0)"><g data-part="reviewer-move"><g transform="scale(-.5 .5)" data-part="reviewer">${robot(stamp(), ROBOT_WEIGHTS)}</g></g></g>
    </g>`;
}

// The Worker walks in, builds unit 2 with one window, adds the second after the HOLD, then climbs to unit 3.
function worker(track) {
  track(part('worker-move'), [
    [0, at(-320, 0)], [300, at(-320, 0)], [700, at(-170, -6)], [1000, at(-90, 0)], [1300, at(-30, -6)], [1600, at(0, 0)],
    [10900, at(0, 0)], [11300, at(30, -50)], [11700, at(40, -80)], [13000, at(40, -80)],
  ]);
  track(`${part('worker')} .swing`, [
    [0, rot(0)], ...alternate(1700, 4100, 500, rot(-28), rot(14)), [4200, rot(0)],
    [7200, rot(0)], ...alternate(7300, 8600, 320, rot(-30), rot(16)), [8700, rot(0)],
    ...alternate(11800, 13000, 500, rot(-28), rot(14)),
  ]);
  track(`${part('worker')} .eyes`, blinks([2600, 5200, 6300, 9900, 12300]));
  track(part('sparks'), [
    [0, { opacity: 0 }], ...alternate(2000, 4000, 400, { opacity: 0 }, { opacity: 1 }), [4100, { opacity: 0 }],
    [7300, { opacity: 0 }], ...alternate(7400, 8500, 260, { opacity: 0 }, { opacity: 1 }), [8600, { opacity: 0 }],
  ]);
  track(part('unit2-walls'), [[1700, drawn(STOREY.height, 0)], [3000, drawn(STOREY.height, 1)]]);
  track(part('unit2-ceiling'), [[3000, drawn(STOREY.width, 0)], [4100, drawn(STOREY.width, 1)]]);
  track(part('unit2-pane1'), [[2800, { opacity: 0 }], [3200, { opacity: 1 }]]);
  track(part('unit2-pane2'), [[7500, { opacity: 0 }], [8100, { opacity: 1 }]]);
  track(part('unit3-walls'), [[11900, drawn(STOREY.height, 0)], [13000, drawn(STOREY.height, FLOOR3_WALLS_AT_END)]]);
}

// The Reviewer climbs to unit 2, inspects, holds, re-inspects, advances, then climbs on.
function reviewer(track) {
  track(part('reviewer-move'), [
    [0, at(0, 384)], [4300, at(0, 384)], [4700, at(0, 372)], [5000, at(0, 360)], [5300, at(0, 334)], [5700, at(0, 312)],
    [11200, at(0, 312)], [11700, at(0, 268)], [12200, at(0, 232)], [13000, at(0, 232)],
  ]);
  track(`${part('reviewer')} .eyes`, blinks([1500, 5800, 8900, 10500]));
  track(`${part('reviewer')} .ant`, [
    [0, { opacity: 1 }], ...alternate(5700, 6000, 150, { opacity: 1 }, { opacity: 0.25 }), [6050, { opacity: 1 }],
    ...alternate(8700, 9300, 150, { opacity: 1 }, { opacity: 0.25 }), [9350, { opacity: 1 }],
  ]);
}

// HOLD flushes the floor and hands a citation over; ADVANCE signs the floor off.
function verdicts(track) {
  track(part('unit2-hold'), [[6000, { opacity: 0 }], [6200, { opacity: 1 }], [7000, { opacity: 1 }], [7400, { opacity: 0 }]]);
  track(part('hold'), [
    [6000, { opacity: 0, transform: 'scale(1.9) rotate(-8deg)' }], [6180, { opacity: 1, transform: 'scale(1) rotate(-4deg)' }],
    [6900, { opacity: 1, transform: 'scale(1) rotate(-4deg)' }], [7200, { opacity: 0, transform: 'scale(.9) rotate(-4deg)' }],
  ]);
  track(part('note'), [
    [6200, { opacity: 0, transform: 'translate(30px, 0)' }], [6500, { opacity: 1, transform: 'translate(0, 0)' }],
    [7100, { opacity: 1, transform: 'translate(-90px, 0)' }], [7400, { opacity: 0, transform: 'translate(-120px, 0)' }],
  ]);
  track(part('advance'), [
    [9400, { opacity: 0, transform: 'scale(1.9) rotate(6deg)' }], [9580, { opacity: 1, transform: 'scale(1) rotate(3deg)' }],
    [10600, { opacity: 1, transform: 'scale(1) rotate(3deg)' }], [10900, { opacity: 0, transform: 'scale(.9) rotate(3deg)' }],
  ]);
  track(part('unit2-fill'), [[9400, { opacity: 0 }], [9700, { opacity: 1 }]]);
  track(part('unit2-check'), [[9600, { opacity: 0 }], [9900, { opacity: 1 }]]);
}

export default {
  duration: T,
  keyframes: [1000, 3300, 5800, 6600, 8200, 10000, 12600],
  captions: [
    [0, 'A Worker is building unit 2, the search bar. Unit 1, the index, is already signed off.'],
    [4300, 'Before unit 2 can close, an adversarial Reviewer that never saw it being written climbs up to inspect it.'],
    [6000, 'HOLD. The Worker missed something.'],
    [7300, 'One fix, then a fresh inspection.'],
    [9400, 'ADVANCE. Unit 2 is signed off, with the finding on file.'],
    [10900, 'Only then does unit 3 begin.'],
  ],
  theme: 'blueprint',
  clock: [[0, 130], [T, 172]],
  viewBox: { wide: `0 0 ${WIDTH} ${HEIGHT}`, narrow: `0 0 ${WIDTH} ${NARROW_HEIGHT}` },
  draw,
  choreograph(track) {
    worker(track);
    reviewer(track);
    verdicts(track);
  },
};
