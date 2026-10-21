// The one-way door beat: unit 3 reaches a call kept for the Owner; the question crosses the Owner's
// line, the project waits, and the answer comes back as a file.
import { alternate, blinks } from '../kit-core.js';
import {
  grid, frame, titleBlockRows, robot, wrench, stamp, clipboard, ladder, groundHatch, stampAdvance, sheet, sparks,
  questionCard, floor, board, page, ownerLine, pane, door, check, person,
} from './parts.js';

const T = 13000;
const WIDTH = 800;
const HEIGHT = 600;    // room under the Owner's line for the Owner, and the question while it waits there
const ROBOT_WEIGHTS = { line: 5, brace: 6.6 };
const LEAD_WEIGHTS = { line: 4.4, brace: 6 };

const BUILDING = { left: 180, width: 320, storey: 80, ground: 430 };
const FLOOR3_TOP = BUILDING.ground - 3 * BUILDING.storey;
const FLOOR3_CEILING_AT_OPEN = 0.2;    // unit 3's ceiling drawn where the door opens, walls up: further along than inspection.js's FLOOR3_WALLS_AT_END

const OWNER_LINE_Y = 474;
const WORKER = { x: 290, y: 242 };
const REVIEWER = { x: 585, y: 232 };
const LEAD = { x: 700, y: 384 };
const BOARD = { x: 620, y: 200, width: 160, height: 90 };    // wide enough for the ONE-WAY DOOR label grown at phone width; clear of the Reviewer
const CARD = { x: 230, y: 208 };    // its label, grown at phone width, ends clear of floor 3's right wall; its top clears the dashed roof
const ADVANCE = { x: 424, y: 219, grow: 1.15 };    // between the Worker's wrench and floor 3's right wall, under the roof

// Where the question and the answer travel: the Worker's hand, the board, the Lead, past the line.
const AT_WORKER = { x: 330, y: 230 };
const AT_BOARD = { x: 700, y: 255 };
const AT_LEAD = { x: 700, y: 340 };
const PAST_LINE = { x: 700, y: 536 };

// The Owner walks in under the line, left of where the question waits, a step at a time.
const OWNER = { x: 600, y: 584, scale: 0.5, from: -40 };
const OWNER_HAND = { x: OWNER.x + 35 * OWNER.scale, y: OWNER.y - 42 * OWNER.scale };    // person()'s hand is at (35, -42)
const OWNER_WALK = { from: 6800, to: 8000 };
const STEP_MS = 100;
const BOB = 4;

// The clock holds at 03:30 from the Worker's stop to the answer.
const T_STOP = 3600;
const T_ANSWER = 9400;

const PIVOT = 'transform-box:view-box;transform-origin:0 0';

const part = name => `[data-part="${name}"]`;
const rot = degrees => ({ transform: `rotate(${degrees}deg)` });
const at = (x, y) => ({ transform: `translate(${x}px, ${y}px)` });
const to = ({ x, y }) => at(x, y);
const drawn = (length, fraction) => ({ strokeDashoffset: length * (1 - fraction) });

function building() {
  const { left, width, storey, ground } = BUILDING;
  const floor2Top = ground - 2 * storey;
  const floor1Top = ground - storey;
  return `
    <path d="M${left - 10} ${FLOOR3_TOP}L${left + width / 2} ${FLOOR3_TOP - 62}L${left + width + 10} ${FLOOR3_TOP}" class="ln dash faint"/>
    <rect data-part="unit3-fill" x="${left}" y="${FLOOR3_TOP}" width="${width}" height="${storey}" class="donefill" opacity="0"/>
    ${floor({ x: left, y: FLOOR3_TOP, width, height: storey, outline: 'open-bottom', look: 'ln dash faint' })}
    ${floor({ x: left, y: FLOOR3_TOP, width, height: storey, look: 'ln', part: 'unit3', outline: 'rise' })}
    <g data-part="unit3-pane1" opacity="0">${pane(210, 212)}</g>
    <g data-part="unit3-pane2" opacity="0">${pane(426, 212)}</g>
    <g data-part="unit3-done" opacity="0">${check(left + width / 2, FLOOR3_TOP + storey / 2)}</g>
    ${floor({ x: left, y: floor2Top, width, height: storey, fill: 'donefill', look: 'ln' })}
    ${pane(210, 292)}${pane(426, 292)}${check(left + width / 2, floor2Top + storey / 2)}
    ${floor({ x: left, y: floor1Top, width, height: storey, fill: 'donefill', look: 'ln' })}
    ${pane(210, 372)}${pane(426, 372)}${door(320, ground)}`;
}

function draw() {
  return `
    ${grid('door', WIDTH, HEIGHT)}
    <clipPath id="door-clip"><rect x="12" y="12" width="776" height="${HEIGHT - 24}"/></clipPath>
    ${frame(WIDTH, HEIGHT, 10)}
    ${titleBlockRows(776, 24, 'SAMPLE', 'ELAPSED <tspan data-clock>03:25</tspan><tspan data-part="paused"> ‖</tspan>', null)}

    <text x="24" y="${FLOOR3_TOP + 36}" class="lbl">UNIT 3</text>
    ${building()}
    ${groundHatch(20, 780, BUILDING.ground, 20)}
    ${ladder(565, 605, 160, BUILDING.ground, 180, 25)}
    <g transform="translate(${BOARD.x} ${BOARD.y})">${board(BOARD.width, BOARD.height, BUILDING.ground - BOARD.y - BOARD.height)}</g>
    <text x="${LEAD.x}" y="462" class="lbl" text-anchor="middle">LEAD</text>
    ${ownerLine(20, 780, OWNER_LINE_Y, 120, 'owner')}

    <g transform="translate(${CARD.x} ${CARD.y})"><g class="grow-narrow">
      ${questionCard('ask')}
      <text data-part="ask-label" x="22" y="4" class="lbl" opacity="0">index format?</text>
    </g></g>
    <g transform="translate(${ADVANCE.x} ${ADVANCE.y})">${stampAdvance('advance', 'ADVANCE', ADVANCE.grow)}</g>
    <g transform="translate(${WORKER.x + 50} ${WORKER.y - 12})">${sparks('sparks')}</g>

    <g clip-path="url(#door-clip)">
      <g transform="translate(${WORKER.x} ${WORKER.y})"><g transform="scale(.5)" data-part="worker">${robot(wrench(), ROBOT_WEIGHTS)}</g></g>
      <g transform="translate(${REVIEWER.x} ${REVIEWER.y})"><g transform="scale(-.5 .5)" data-part="reviewer">${robot(stamp(), ROBOT_WEIGHTS)}</g></g>
      <g transform="translate(${LEAD.x} ${LEAD.y})"><g data-part="lead-shake" style="${PIVOT}">
        <g transform="scale(.6)" data-part="lead">${robot(clipboard(), LEAD_WEIGHTS)}</g>
      </g></g>
      <g transform="translate(${OWNER.x} ${OWNER.y})"><g data-part="owner" style="${PIVOT}">
        <g transform="scale(${OWNER.scale})">${person()}</g>
      </g></g>
      <g data-part="question" opacity="0"><g class="grow-narrow">
        ${sheet('question-sheet')}
        <text y="-24" text-anchor="middle" class="lbl">ONE-WAY DOOR</text>
      </g></g>
      <g data-part="answer-move">${page('answer', null)}</g>
    </g>`;
}

// The Worker reaches the call, stops, writes the question; the answer comes back and it finishes.
function worker(track) {
  track(`${part('worker')} .swing`, [
    [0, rot(0)], ...alternate(0, 2600, 500, rot(-28), rot(14)), [2700, rot(0)],
    [10700, rot(0)], ...alternate(10800, 11800, 500, rot(-28), rot(14)), [11900, rot(0)],
  ]);
  track(`${part('worker')} .eyes`, blinks([700, 3700, 8000, 10600]));
  track(`${part('worker')} .ant`, [
    [0, { opacity: 1 }], ...alternate(1500, 1800, 150, { opacity: 1 }, { opacity: 0.25 }), [1850, { opacity: 1 }],
  ]);
  track(part('sparks'), [
    [0, { opacity: 0 }], ...alternate(100, 2500, 400, { opacity: 0 }, { opacity: 1 }), [2600, { opacity: 0 }],
    [10800, { opacity: 0 }], ...alternate(10900, 11700, 400, { opacity: 0 }, { opacity: 1 }), [11800, { opacity: 0 }],
  ]);
  track(part('unit3-walls'), [[0, drawn(BUILDING.storey, 1)]]);
  track(part('unit3-ceiling'), [
    [0, drawn(BUILDING.width, FLOOR3_CEILING_AT_OPEN)], [2600, drawn(BUILDING.width, 0.5)],
    [10800, drawn(BUILDING.width, 0.5)], [11800, drawn(BUILDING.width, 1)],
  ]);
  track(part('unit3-pane1'), [[10900, { opacity: 0 }], [11300, { opacity: 1 }]]);
  track(part('unit3-pane2'), [[11300, { opacity: 0 }], [11700, { opacity: 1 }]]);
  for (const name of ['ask', 'ask-label']) {
    track(part(name), [[1200, { opacity: 0 }], [1500, { opacity: 1 }], [11300, { opacity: 1 }], [11500, { opacity: 0 }]]);
  }
  track(part('ask-ask'), [[10500, { opacity: 1 }], [10650, { opacity: 0 }]]);
  track(part('ask-check'), [[10500, { opacity: 0 }], [10650, { opacity: 1 }]]);
}

// The question goes to the board, the Lead cannot decide it, and it waits past the Owner's line.
function question(track) {
  track(part('question-sheet'), [[0, { opacity: 1 }]]);
  track(part('question'), [
    [3900, { opacity: 0, ...to(AT_WORKER) }], [4200, { opacity: 1, ...to(AT_WORKER) }], [4900, { opacity: 1, ...to(AT_BOARD) }],
    [6600, { opacity: 1, ...to(AT_BOARD) }], [7000, { opacity: 1, ...to(AT_LEAD) }], [7300, { opacity: 1, ...to(AT_LEAD) }],
    [8000, { opacity: 1, ...to(PAST_LINE) }], [T_ANSWER, { opacity: 1, ...to(PAST_LINE) }], [T_ANSWER + 200, { opacity: 0, ...to(PAST_LINE) }],
  ]);
  track(part('lead-shake'), [[6800, rot(0)], [6950, rot(-7)], [7100, rot(7)], [7250, rot(-7)], [7400, rot(0)]]);
  track(`${part('lead')} .eyes`, blinks([2400, 6700, 9900]));
  track(part('paused'), [[T_STOP - 50, { opacity: 0 }], [T_STOP, { opacity: 1 }], [T_ANSWER, { opacity: 1 }], [T_ANSWER + 50, { opacity: 0 }]]);
}

// The Owner walks in to meet the question, answers it from their hand, and fades once it has left.
function owner(track) {
  const distance = OWNER.x - OWNER.from;
  const frames = [[OWNER_WALK.from, { opacity: 1, ...at(-distance, 0) }]];
  for (let t = OWNER_WALK.from + STEP_MS, step = 1; t < OWNER_WALK.to; t += STEP_MS, step++) {
    const x = -distance * (OWNER_WALK.to - t) / (OWNER_WALK.to - OWNER_WALK.from);
    frames.push([t, { opacity: 1, ...at(x, step % 2 ? -BOB : 0) }]);
  }
  frames.push([OWNER_WALK.to, { opacity: 1, ...at(0, 0) }], [10000, { opacity: 1, ...at(0, 0) }], [10400, { opacity: 0, ...at(0, 0) }]);
  track(part('owner'), frames);
}

// The answer comes back up from the Owner's hand; the Reviewer signs unit 3 off.
function answer(track) {
  track(part('answer-move'), [
    [T_ANSWER + 100, to(OWNER_HAND)], [10000, to(AT_LEAD)], [10500, to(AT_WORKER)],
  ]);
  track(part('answer'), [[T_ANSWER + 100, { opacity: 0 }], [T_ANSWER + 300, { opacity: 1 }], [10700, { opacity: 1 }], [10900, { opacity: 0 }]]);
  track(`${part('reviewer')} .eyes`, blinks([3000, 8300, 11900]));
  track(`${part('reviewer')} .ant`, [
    [0, { opacity: 1 }], ...alternate(11800, 12100, 150, { opacity: 1 }, { opacity: 0.25 }), [12150, { opacity: 1 }],
  ]);
  track(part('advance'), [
    [12000, { opacity: 0, transform: 'scale(1.9) rotate(6deg)' }], [12180, { opacity: 1, transform: 'scale(1) rotate(3deg)' }],
  ]);
  track(part('unit3-fill'), [[12200, { opacity: 0 }], [12500, { opacity: 1 }]]);
  track(part('unit3-done'), [[12300, { opacity: 0 }], [12600, { opacity: 1 }]]);
}

export default {
  duration: T,
  keyframes: [2000, 5400, 8600, 10600, 12700],
  captions: [
    [0, 'Unit 3 reaches a call the brief kept for the Owner: the index format on disk.'],
    [3400, 'The Worker stops and writes the question down. It does not guess.'],
    [6400, "The Lead cannot decide it either. It crosses the Owner's line, and the project waits."],
    [T_ANSWER, 'The answer comes back as a line in a file. The Worker reads it and continues.'],
  ],
  theme: 'blueprint',
  clock: [[0, 205], [T_STOP, 210], [T_ANSWER, 210], [T, 225]],
  viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
  draw,
  choreograph(track) {
    worker(track);
    question(track);
    owner(track);
    answer(track);
  },
};
