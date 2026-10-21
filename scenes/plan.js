// The plan beat: the Owner and a Planner go back and forth until one brief exists.
import { alternate, blinks } from '../kit-core.js';
import { grid, frame, titleBlockRows, robot, pen, person, groundHatch, cycle, questionCard, floor } from './parts.js';

const T = 12000;
const WIDTH = 800;
const HEIGHT = 480;
const NARROW_HEIGHT = 1040;   // room under the ground for the brief, grown for phone width
const ROBOT_WEIGHTS = { line: 3.2, brace: 4.4 };

// The brief hangs from a pivot that puts it on the easel at full width and, grown twice, under
// the ground at phone width: wide top-left (440, 100), narrow top-left (70, 470).
const BRIEF_PIVOT = { x: 810, y: -270 };
const BRIEF_OFFSET = { x: -370, y: 370 };
const BRIEF_WIDTH = 330;
const BRIEF_HEIGHT = 270;

const FLOOR_PERIMETER = 268;   // 2 × (100 + 34)
const GROUND_LENGTH = 116;
// The roof keeps .dash's 8-on, 7-off pattern while it is drawn in: the pattern written out over the
// roof, then a gap as long as the roof, so an offset of the written-out length hides it.
const ROOF_LENGTH = 2 * Math.hypot(58, 16);
const ROOF_DASHES = Math.ceil(ROOF_LENGTH / 15);
const ROOF_PATTERN = `${'8 7 '.repeat(ROOF_DASHES - 1)}8 ${7 + ROOF_LENGTH}`;
const RULE_LENGTH = 294;
const UNITS = [
  { name: 'highlight-matches', top: 64 },
  { name: 'search-bar', top: 98 },
  { name: 'search-index', top: 132 },
];

// Each question card leaves the Planner, is answered at the Owner, and is put away.
const QUESTIONS = [
  { part: 'question1', at: 300 },
  { part: 'question2', at: 2200 },
  { part: 'question3', at: 3600 },
];
const CARD_FROM = { x: 70, y: 0 };

const part = name => `[data-part="${name}"]`;
const rot = degrees => ({ transform: `rotate(${degrees}deg)` });
const at = (x, y) => ({ transform: `translate(${x}px, ${y}px)` });
const seal = scale => ({ transform: `scale(${scale})` });

function brief() {
  const floors = UNITS.map(({ name, top }, i) => `
    ${floor({ x: 24, y: top, width: 100, height: 34, look: 'ln thin', part: `floor${i + 1}`, hidden: true })}
    <text data-part="name${i + 1}" x="140" y="${top + 21}" class="lbl" opacity="0">${name}</text>`).join('');
  return `
    <path d="M0 0H${BRIEF_WIDTH - 22}L${BRIEF_WIDTH} 22V${BRIEF_HEIGHT}H0Z" class="paper" style="stroke:var(--fg);stroke-width:2.4"/>
    <path d="M${BRIEF_WIDTH - 22} 0V22H${BRIEF_WIDTH}" class="ln thin"/>
    <text x="18" y="28" class="lbl">BRIEF</text>
    <path d="M18 40H${BRIEF_WIDTH - 40}" class="ln thin faint"/>
    <path data-part="roof" d="M16 64L74 48L132 64" class="ln thin dash faint"
      style="stroke-dasharray:${ROOF_PATTERN};stroke-dashoffset:${ROOF_DASHES * 15}"/>
    ${floors}
    <path data-part="ground" d="M16 166H132" class="ln thin"
      style="stroke-dasharray:${GROUND_LENGTH};stroke-dashoffset:${GROUND_LENGTH}"/>
    <path data-part="owner-rule" d="M18 196H${18 + RULE_LENGTH}" class="ln thin"
      style="stroke-dasharray:${RULE_LENGTH};stroke-dashoffset:${RULE_LENGTH}"/>
    <text data-part="owner-call" x="18" y="222" class="lbl" opacity="0">one call kept for the Owner</text>
    <g transform="translate(296 248)"><g data-part="seal" opacity="0" style="transform-box:view-box;transform-origin:0 0">
      <circle r="14" class="brass"/><circle r="9" style="fill:none;stroke:var(--bg);stroke-width:2"/>
    </g></g>`;
}

function easel() {
  return `
    <g class="wide-only">
      <path d="M470 378L450 430M750 378L770 430" class="ln"/>
      <rect x="430" y="90" width="350" height="290" rx="4" class="ln thin faint"/>
    </g>`;
}

function draw() {
  const cards = QUESTIONS.map(({ part: name }) => `<g transform="translate(160 240)">${questionCard(name)}</g>`).join('');
  return `
    ${grid('plan', WIDTH, NARROW_HEIGHT)}
    <g class="wide-only">${frame(WIDTH, HEIGHT, 10)}</g>
    <g class="narrow-only">${frame(WIDTH, NARROW_HEIGHT, 10)}</g>
    ${titleBlockRows(776, 24, 'SAMPLE', 'PLANNING', null)}
    ${groundHatch(20, 780, 430, 20)}
    ${easel()}
    <g transform="translate(${BRIEF_PIVOT.x} ${BRIEF_PIVOT.y})"><g class="grow-narrow" style="--grow:2">
      <g transform="translate(${BRIEF_OFFSET.x} ${BRIEF_OFFSET.y})">${brief()}</g>
    </g></g>

    <g transform="translate(110 430)">${person()}</g>
    <g transform="translate(300 384)"><g data-part="planner" transform="scale(-.9 .9)">${robot(pen(), ROBOT_WEIGHTS)}</g></g>
    <g transform="translate(205 336)">${cycle('cycle', 26)}</g>
    ${cards}`;
}

// Three questions go from the Planner to the Owner and come back answered.
function questions(track) {
  for (const { part: name, at: start } of QUESTIONS) {
    track(part(name), [
      [start, { opacity: 0, ...at(CARD_FROM.x, CARD_FROM.y) }], [start + 300, { opacity: 1, ...at(CARD_FROM.x, CARD_FROM.y) }],
      [start + 800, { opacity: 1, ...at(0, 0) }], [start + 1700, { opacity: 1, ...at(0, 0) }],
      [start + 2000, { opacity: 0, ...at(0, -24) }],
    ]);
    track(part(`${name}-ask`), [[start + 900, { opacity: 1 }], [start + 1100, { opacity: 0 }]]);
    track(part(`${name}-check`), [[start + 900, { opacity: 0 }], [start + 1100, { opacity: 1 }]]);
  }
  track(part('cycle'), [[300, rot(0)], [5000, rot(720)]]);
}

// The Planner writes the questions, then the brief on a blank sheet: the ground, three floors, the
// roof, the Owner's line, the seal.
function planner(track) {
  track(`${part('planner')} .swing`, [
    [0, rot(0)], ...alternate(300, 700, 200, rot(-14), rot(8)), [800, rot(0)],
    [2100, rot(0)], ...alternate(2200, 2600, 200, rot(-14), rot(8)), [2700, rot(0)],
    [3500, rot(0)], ...alternate(3600, 4000, 200, rot(-14), rot(8)), [4100, rot(0)],
    [5100, rot(0)], ...alternate(5200, 8400, 200, rot(-14), rot(8)), [8500, rot(0)],
  ]);
  track(`${part('planner')} .eyes`, blinks([1900, 4400, 9000, 11000]));
}

function briefDrawn(track) {
  track(part('ground'), [[5000, { strokeDashoffset: GROUND_LENGTH }], [5200, { strokeDashoffset: 0 }]]);
  UNITS.forEach((unit, i) => {
    const start = 5200 + (UNITS.length - 1 - i) * 700;
    track(part(`floor${i + 1}`), [[start, { strokeDashoffset: FLOOR_PERIMETER }], [start + 600, { strokeDashoffset: 0 }]]);
    track(part(`name${i + 1}`), [[start + 400, { opacity: 0 }], [start + 700, { opacity: 1 }]]);
  });
  track(part('roof'), [[7200, { strokeDashoffset: ROOF_DASHES * 15 }], [7400, { strokeDashoffset: 0 }]]);
  track(part('owner-rule'), [[7600, { strokeDashoffset: RULE_LENGTH }], [8100, { strokeDashoffset: 0 }]]);
  track(part('owner-call'), [[8000, { opacity: 0 }], [8400, { opacity: 1 }]]);
  track(part('seal'), [[9600, { opacity: 0, ...seal(1.9) }], [9800, { opacity: 1, ...seal(1) }]]);
}

export default {
  duration: T,
  keyframes: [1600, 4800, 7400, 8800, 10400],
  captions: [
    [0, 'The Owner wants search in the notes app. A Planner session asks the questions first.'],
    [5000, 'Scope, three units, and the one call kept for the Owner go on a single brief.'],
    [9500, 'The brief is a file. So is every hand-off after it.'],
  ],
  theme: 'whiteprint',
  viewBox: { wide: `0 0 ${WIDTH} ${HEIGHT}`, narrow: `0 0 ${WIDTH} ${NARROW_HEIGHT}` },
  draw,
  choreograph(track) {
    questions(track);
    planner(track);
    briefDrawn(track);
  },
};
