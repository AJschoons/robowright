// The hand-back beat: the project is done, an Explainer brings the Owner a short brief, and the Owner
// reads it and stamps it accepted.
import { alternate, blinks } from '../kit-core.js';
import { grid, frame, titleBlockRows, robot, pen, person, groundHatch, ownerLine, ledger, building, brassStamp } from './parts.js';

const T = 12000;
const WIDTH = 800;
const HEIGHT = 560;
const ROBOT_WEIGHTS = { line: 5, brace: 6.6 };

// Must match street.js's ORIGIN and first project: the street opens on this building.
const BUILDING = { x: 110, ground: 450, width: 300, storey: 80 };

const OWNER_LINE_Y = 526;    // a row under the labels, so EXPLAINER does not read as part of it
const OWNER = { x: 660, from: 200 };
const EXPLAINER = { x: 260, y: 422, to: 210 };
const BRIEF = { width: 70, height: 90, lines: 4 };
const BRIEF_LINE = BRIEF.width - 28;
const BRIEF_AT_EXPLAINER = { x: 325, y: 366 };
const BRIEF_AT_OWNER = { x: 575, y: 360 };
const STAMP_AT = { x: 553, y: 365 };    // on the brief, clear of its label, the Owner's raised arm and the Explainer's antenna and pen at phone width

const part = name => `[data-part="${name}"]`;
const rot = degrees => ({ transform: `rotate(${degrees}deg)` });
const at = (x, y) => ({ transform: `translate(${x}px, ${y}px)` });

// The brief hangs about its centre, its label above it, grown from the label's own baseline.
function brief() {
  return `
    <g data-part="brief" opacity="0">
      <g transform="translate(${-BRIEF.width / 2} ${-BRIEF.height / 2})">${ledger('brief', BRIEF.width, BRIEF.height, BRIEF.lines)}</g>
      <g transform="translate(0 ${-BRIEF.height / 2 - 12})"><g class="grow-narrow" style="--grow:1.3"><text text-anchor="middle" class="lbl">OWNER BRIEF</text></g></g>
    </g>`;
}

function draw() {
  return `
    ${grid('handback', WIDTH, HEIGHT)}
    <clipPath id="handback-clip"><rect x="12" y="12" width="776" height="${HEIGHT - 24}"/></clipPath>
    ${frame(WIDTH, HEIGHT, 10)}
    ${titleBlockRows(776, 24, 'SAMPLE', 'ELAPSED <tspan data-clock>04:40</tspan>', null)}

    ${building(3, { ...BUILDING, weight: null })}
    ${groundHatch(20, 780, BUILDING.ground, 20)}
    ${ownerLine(20, 780, OWNER_LINE_Y, WIDTH / 2, 'owner reviews and merges, or replans')}

    <g clip-path="url(#handback-clip)">
      <g transform="translate(${OWNER.x} ${BUILDING.ground})"><g data-part="owner">
        <g transform="scale(-.9 .9)">${person()}</g>
      </g></g>
      <g transform="translate(${EXPLAINER.x} ${EXPLAINER.y})"><g data-part="explainer-move" opacity="0">
        <g transform="scale(.5)" data-part="explainer">${robot(pen(), ROBOT_WEIGHTS)}</g>
        <text y="${BUILDING.ground + 32 - EXPLAINER.y}" class="lbl" text-anchor="middle">EXPLAINER</text>
      </g></g>
      <g transform="translate(${BRIEF_AT_EXPLAINER.x} ${BRIEF_AT_EXPLAINER.y})"><g data-part="brief-move">${brief()}</g></g>
    </g>
    <g transform="translate(${STAMP_AT.x} ${STAMP_AT.y})">${brassStamp('accepted', 'ACCEPTED')}</g>`;
}

// The Owner walks back in from the right a step at a time, and stops facing the building.
function ownerReturns(track) {
  const steps = [];
  for (let t = 600, step = 0; t <= 2200; t += 100, step++) {
    const x = OWNER.from * (1 - (t - 600) / 1600);
    steps.push([t, at(x, step % 2 ? -4 : 0)]);
  }
  track(part('owner'), steps);
}

// The Explainer comes out of the building, writes the brief, and carries it to the Owner.
function explainer(track) {
  const { to } = EXPLAINER;
  const walk = [[5800, 0], [6150, to / 4], [6500, to / 2], [6850, to * 3 / 4], [7200, to]];
  track(part('explainer-move'), [
    [3600, { opacity: 0, ...at(0, 0) }], [3900, { opacity: 1, ...at(0, 0) }],
    ...walk.map(([t, x], i) => [t, { opacity: 1, ...at(x, i % 2 ? -6 : 0) }]),
  ]);
  track(`${part('explainer')} .swing`, [[0, rot(0)], ...alternate(4100, 5600, 400, rot(-20), rot(10)), [5700, rot(0)]]);
  track(`${part('explainer')} .eyes`, blinks([4600, 7400, 10200]));
  track(`${part('explainer')} .ant`, [
    [0, { opacity: 1 }], ...alternate(7300, 7600, 150, { opacity: 1 }, { opacity: 0.25 }), [7650, { opacity: 1 }],
  ]);
  track(part('brief'), [[3900, { opacity: 0 }], [4100, { opacity: 1 }]]);
  [4200, 4600, 5000, 5400].forEach((start, i) => {
    track(part(`brief-${i + 1}`), [[start, { strokeDashoffset: BRIEF_LINE }], [start + 300, { strokeDashoffset: 0 }]]);
  });
  const handed = at(BRIEF_AT_OWNER.x - BRIEF_AT_EXPLAINER.x, BRIEF_AT_OWNER.y - BRIEF_AT_EXPLAINER.y);
  track(part('brief-move'), [
    ...walk.map(([t, x], i) => [t, at(x, i % 2 ? -6 : 0)]), [7800, at(to, 0)], [8300, handed],
  ]);
}

// The Owner reads, then stamps it: brass, the Owner's own seal.
function accept(track) {
  track(part('accepted'), [
    [9600, { opacity: 0, transform: 'scale(1.9) rotate(-10deg)' }], [9780, { opacity: 1, transform: 'scale(1) rotate(-6deg)' }],
  ]);
}

export default {
  duration: T,
  keyframes: [2800, 5000, 7400, 8800, 10600],
  captions: [
    [0, 'Three units, three inspections, one call made by the Owner. The project is done.'],
    [3600, 'An Explainer writes the Owner a short brief: what to decide now, what changed, where the detail is.'],
    [8000, 'The Owner reads it, reviews code as needed, then accepts. That part is never automated.'],
  ],
  theme: 'whiteprint',
  clock: [[0, 280], [T, 280]],
  viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
  draw,
  choreograph(track) {
    ownerReturns(track);
    explainer(track);
    accept(track);
  },
};
