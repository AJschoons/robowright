// The build beat: a Worker builds unit 1, hands off to a fresh one on purpose, a Reader reads the
// log for it, and the Reviewer signs the floor off.
import { alternate, blinks } from '../kit-core.js';
import {
  grid, frame, titleBlockRows, robot, wrench, stamp, magnifier, ladder, groundHatch, stampAdvance, sparks,
  floor, ledger, log, meter, page, slip, pane, door,
} from './parts.js';

const T = 13000;
const WIDTH = 800;
const HEIGHT = 480;
const ROBOT_WEIGHTS = { line: 5, brace: 6.6 };

const BUILDING = { left: 180, width: 320, storey: 80, ground: 430 };
const FLOOR1_TOP = BUILDING.ground - BUILDING.storey;
const FLOOR1_CEILING_AT_OPEN = 0.3;    // floor 1's ceiling drawn where launch.js ends, walls up; keep equal to its FLOOR1_CEILING_AT_HANDOFF

const WORKER = { x: 260, y: 402, from: -360, to: 560 };
const REVIEWER = { x: 585, ground: 404, floor1: 384 };    // floor1: where the inspection opens
const READER = { x: 725, y: 402 };    // clear of REVIEWER's label at phone width
const LEDGER = { x: 30, y: 150, width: 110, height: 140, lines: 6 };
const LEDGER_LINE = LEDGER.width - 28;
const LOG = { x: 650, y: 190, width: 100, height: 150 };
const HANDOFF_AT = { x: 340, y: 410 };
const SLIP_FROM = { x: 695, y: 360 };
const SLIP_TO = { x: 262, y: 362 };    // over the fresh Worker's head

// The meter sits in the title block's top row, right of SAMPLE; the session hands off at the mark.
const METER = { x: -100, y: 10, width: 88, height: 10, mark: 0.8 };

const part = name => `[data-part="${name}"]`;
const rot = degrees => ({ transform: `rotate(${degrees}deg)` });
const at = (x, y) => ({ transform: `translate(${x}px, ${y}px)` });
const fill = fraction => ({ transform: `scaleX(${fraction})` });
const drawn = (length, fraction) => ({ strokeDashoffset: length * (1 - fraction) });

function building() {
  const { left, width, storey, ground } = BUILDING;
  const roof = ground - 3 * storey;
  return `
    <path d="M${left - 10} ${roof}L${left + width / 2} ${roof - 62}L${left + width + 10} ${roof}" class="ln dash faint"/>
    ${floor({ x: left, y: roof, width, height: storey, storeys: 2, look: 'ln dash faint' })}
    <rect data-part="floor1-fill" x="${left}" y="${FLOOR1_TOP}" width="${width}" height="${storey}" class="donefill" opacity="0"/>
    ${floor({ x: left, y: FLOOR1_TOP, width, height: storey, look: 'ln', part: 'floor1', outline: 'rise' })}
    <g data-part="floor1-done" opacity="0">${pane(210, 372)}${pane(426, 372)}${door(320, ground)}</g>`;
}

function titleBlock() {
  return `
    ${titleBlockRows(776, 24, 'SAMPLE', 'ELAPSED <tspan data-clock>00:00</tspan>', null)}
    <g transform="translate(776 24)"><g class="grow-narrow" style="--grow:2"><g transform="translate(${METER.x} ${METER.y})">
      ${meter('meter', METER.width, METER.height, METER.mark)}
    </g></g></g>`;
}

function worker(name) {
  return `
    <g transform="translate(${WORKER.x} ${WORKER.y})"><g data-part="${name}-move">
      <g transform="scale(.5)" data-part="${name}">${robot(wrench(), ROBOT_WEIGHTS)}</g>
    </g></g>`;
}

function draw() {
  return `
    ${grid('build', WIDTH, HEIGHT)}
    <clipPath id="build-clip"><rect x="12" y="12" width="776" height="456"/></clipPath>
    ${frame(WIDTH, HEIGHT, 10)}
    ${titleBlock()}

    <text x="${LEDGER.x}" y="${LEDGER.y - 10}" class="lbl">LEDGER</text>
    <g transform="translate(${LEDGER.x} ${LEDGER.y})">${ledger('ledger', LEDGER.width, LEDGER.height, LEDGER.lines)}</g>
    <text x="${LOG.x}" y="${LOG.y - 10}" class="lbl">LOG</text>
    <g transform="translate(${LOG.x} ${LOG.y})">${log(LOG.width, LOG.height)}</g>

    <text x="24" y="386" class="lbl">UNIT 1</text>
    ${building()}
    ${groundHatch(20, 780, BUILDING.ground, 20)}
    ${ladder(565, 605, 160, BUILDING.ground, 180, 25)}
    <text x="${WORKER.x}" y="462" class="lbl" text-anchor="middle">WORKER</text>
    <text x="${REVIEWER.x}" y="462" class="lbl" text-anchor="middle">REVIEWER</text>
    <text data-part="reader-label" x="${READER.x}" y="462" class="lbl" text-anchor="middle" opacity="0">READER</text>

    <g transform="translate(${HANDOFF_AT.x} ${HANDOFF_AT.y})">${page('handoff', 'HANDOFF')}</g>
    <g transform="translate(410 390)">${stampAdvance('advance', 'ADVANCE')}</g>
    <g transform="translate(${WORKER.x + 50} ${WORKER.y - 12})">${sparks('sparks')}</g>
    <g transform="translate(${SLIP_FROM.x} ${SLIP_FROM.y})">${slip('slip')}</g>

    <g clip-path="url(#build-clip)">
      ${worker('first')}
      ${worker('fresh')}
      <g transform="translate(${READER.x} ${READER.y})"><g data-part="reader-move" opacity="0">
        <g transform="scale(-.5 .5)" data-part="reader">${robot(magnifier(), ROBOT_WEIGHTS)}</g>
      </g></g>
      <g transform="translate(${REVIEWER.x} 0)"><g data-part="reviewer-move">
        <g transform="scale(-.5 .5)" data-part="reviewer">${robot(stamp(), ROBOT_WEIGHTS)}</g>
      </g></g>
    </g>`;
}

// The first Worker builds, writes the ledger, fills its context to the mark, leaves the hand-off and walks off.
function firstWorker(track) {
  track(`${part('first')} .swing`, [[0, rot(0)], ...alternate(0, 4200, 500, rot(-28), rot(14)), [4300, rot(0)]]);
  track(`${part('first')} .eyes`, blinks([900, 2900, 4500]));
  track(`${part('first')} .ant`, [[0, { opacity: 1 }], [4900, { opacity: 1 }], [5100, { opacity: 0.25 }]]);
  track(part('handoff'), [
    [4400, { opacity: 0, ...at(-50, -20) }], [4600, { opacity: 1, ...at(-50, -20) }], [5000, { opacity: 1, ...at(0, 0) }],
    [7600, { opacity: 1, ...at(0, 0) }], [7900, { opacity: 0, ...at(-50, -30) }],
  ]);
  track(part('first-move'), [
    [5400, at(0, 0)], [5700, at(70, -6)], [6000, at(180, 0)], [6300, at(320, -6)], [6600, at(WORKER.to, 0)],
  ]);
}

// A fresh Worker walks in, reads the hand-off, finishes the floor and takes the Reader's slip.
function freshWorker(track) {
  const { from } = WORKER;
  track(part('fresh-move'), [
    [6500, at(from, 0)], [6800, at(from * 2 / 3, -6)], [7100, at(from / 3, 0)], [7400, at(-40, -6)], [7600, at(0, 0)],
  ]);
  track(`${part('fresh')} .swing`, [[0, rot(0)], [7900, rot(0)], ...alternate(8000, 9200, 500, rot(-28), rot(14)), [9300, rot(0)]]);
  track(`${part('fresh')} .eyes`, blinks([7700, 9900, 12000]));
  track(`${part('fresh')} .ant`, [
    [0, { opacity: 1 }], ...alternate(10800, 11100, 150, { opacity: 1 }, { opacity: 0.25 }), [11150, { opacity: 1 }],
  ]);
}

function work(track) {
  track(part('sparks'), [
    [0, { opacity: 0 }], ...alternate(200, 4000, 400, { opacity: 0 }, { opacity: 1 }), [4100, { opacity: 0 }],
    [8000, { opacity: 0 }], ...alternate(8100, 9100, 400, { opacity: 0 }, { opacity: 1 }), [9200, { opacity: 0 }],
  ]);
  track(part('floor1-walls'), [[0, drawn(BUILDING.storey, 1)]]);
  track(part('floor1-ceiling'), [
    [0, drawn(BUILDING.width, FLOOR1_CEILING_AT_OPEN)], [4200, drawn(BUILDING.width, 0.7)],
    [8000, drawn(BUILDING.width, 0.7)], [9200, drawn(BUILDING.width, 1)],
  ]);
  const writes = [300, 1100, 1900, 2700, 3500, 8400];
  writes.forEach((start, i) => {
    track(part(`ledger-${i + 1}`), [[start, { strokeDashoffset: LEDGER_LINE }], [start + 400, { strokeDashoffset: 0 }]]);
  });
  track(part('meter'), [
    [0, fill(0.2)], [3400, fill(0.55)], [4400, fill(METER.mark)], [6300, fill(METER.mark)], [6500, fill(0.05)], [9200, fill(0.3)],
  ]);
}

// The Reader reads the log and sends one line back; the Reviewer climbs to floor 1 and signs it off.
function verdicts(track) {
  track(part('reader-move'), [
    [9300, { opacity: 0, ...at(60, 0) }], [9700, { opacity: 1, ...at(0, 0) }], [10000, { opacity: 1, ...at(0, -6) }],
    [10200, { opacity: 1, ...at(0, 0) }],
  ]);
  track(part('reader-label'), [[9500, { opacity: 0 }], [9800, { opacity: 1 }]]);
  track(`${part('reader')} .eyes`, blinks([9900, 12200]));
  track(part('slip'), [
    [10200, { opacity: 0, ...at(0, 0) }], [10350, { opacity: 1, ...at(0, 0) }],
    [10800, { opacity: 1, ...at(SLIP_TO.x - SLIP_FROM.x, SLIP_TO.y - SLIP_FROM.y) }],
    [11300, { opacity: 1, ...at(SLIP_TO.x - SLIP_FROM.x, SLIP_TO.y - SLIP_FROM.y) }],
    [11500, { opacity: 0, ...at(SLIP_TO.x - SLIP_FROM.x, SLIP_TO.y - SLIP_FROM.y) }],
  ]);
  track(part('reviewer-move'), [
    [0, at(0, REVIEWER.ground)], [10900, at(0, REVIEWER.ground)], [11100, at(0, (REVIEWER.ground + REVIEWER.floor1) / 2)],
    [11300, at(0, REVIEWER.floor1)],
  ]);
  track(`${part('reviewer')} .eyes`, blinks([2100, 7300, 11000]));
  track(`${part('reviewer')} .ant`, [
    [0, { opacity: 1 }], ...alternate(11300, 11600, 150, { opacity: 1 }, { opacity: 0.25 }), [11650, { opacity: 1 }],
  ]);
  track(part('advance'), [
    [11500, { opacity: 0, transform: 'scale(1.9) rotate(6deg)' }], [11680, { opacity: 1, transform: 'scale(1) rotate(3deg)' }],
  ]);
  track(part('floor1-fill'), [[11700, { opacity: 0 }], [12000, { opacity: 1 }]]);
  track(part('floor1-done'), [[11800, { opacity: 0 }], [12100, { opacity: 1 }]]);
}

export default {
  duration: T,
  keyframes: [1600, 5200, 8400, 10900, 12600],
  captions: [
    [0, 'A Worker builds unit 1, the index. Everything it decides goes in a ledger on disk.'],
    [3400, 'Its context is filling up. Instead of compacting, it writes a hand-off and ends its turn, on purpose.'],
    [6400, 'A fresh Worker reads the hand-off and picks up where the last one stopped. Nothing is carried but files.'],
    [9400, 'Build logs go to a token-efficient Reader, which hands back one line: the verdict. The Worker never reads the log.'],
  ],
  theme: 'blueprint',
  clock: [[0, 0], [T, 100]],
  viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
  draw,
  choreograph(track) {
    firstWorker(track);
    freshWorker(track);
    work(track);
    verdicts(track);
  },
};
