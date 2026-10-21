// The street: the camera pulls back from the finished building to show it beside a six-unit project
// and a twelve-storey tower, each built the same way.
import { grid, frame, ladder, groundHatch, building, tinyRobot } from './parts.js';

const T = 12000;
const WIDTH = 800;
const HEIGHT = 560;

// The world's origin is the small building's ground-left corner, where the hand-back drew it.
const ORIGIN = { x: 110, y: 450 };
const STOREY = 80;
const FAR_WEIGHT = 7;    // reads as a line at the end scale
const END_SCALE = 0.26;
const PULL = { from: 1200, to: 5200 };

const PIVOT = 'transform-box:view-box;transform-origin:0 0';

// Each project: its storeys, its place in the world, its stroke weight (null: the class's own) and
// the floors its robots stand on.
const PROJECTS = [
  { label: 'SEARCH · 3 UNITS', floors: 3, x: 0, width: 300, weight: null, robots: [2] },
  { label: 'DATABASE · 6 UNITS', floors: 6, x: 960, width: 480, weight: FAR_WEIGHT, robots: [3, 5] },
  { label: 'SYNC · 12 UNITS', floors: 12, x: 1920, width: 320, weight: FAR_WEIGHT, robots: [4, 8, 11] },
];
const LADDER_GAP = 20;
const LADDER_WIDTH = 36;
const ROOF_RISE = 62;
const LABEL_GAP = 12;

const part = name => `[data-part="${name}"]`;

// .lbl is 11px monospace: 0.6em a character plus .08em of letter spacing.
const LABEL_ADVANCE = 7.5;

function project({ floors, x, width, weight, robots }) {
  const left = x + width + LADDER_GAP;
  const top = -floors * STOREY - 20;
  const heads = robots.map(n => `<g transform="translate(${left + LADDER_WIDTH / 2} ${-(n - 0.5) * STOREY})">${tinyRobot()}</g>`);
  return `
    ${building(floors, { x, ground: 0, width, storey: STOREY, weight })}
    ${ladder(left, left + LADDER_WIDTH, top, 0, top + 20, 25)}
    ${heads.join('')}`;
}

// A project's name on a small board, centred over its roof where the pull-back leaves it.
function label({ label: text, floors, x, width }) {
  const boxWidth = Math.ceil(text.length * LABEL_ADVANCE) + 12;
  const centre = ORIGIN.x + END_SCALE * (x + width / 2);
  const bottom = ORIGIN.y - END_SCALE * (floors * STOREY + ROOF_RISE) - LABEL_GAP;
  return `
    <g transform="translate(${centre} ${bottom})"><g class="grow-narrow" style="--grow:2">
      <rect x="${-boxWidth / 2}" y="-20" width="${boxWidth}" height="20" class="paper" style="stroke:var(--fg);stroke-width:2"/>
      <text y="-6" text-anchor="middle" class="lbl">${text}</text>
    </g></g>`;
}

function draw() {
  return `
    ${grid('street', WIDTH, HEIGHT)}
    <clipPath id="street-clip"><rect x="12" y="12" width="776" height="${HEIGHT - 24}"/></clipPath>
    ${frame(WIDTH, HEIGHT, 10)}
    <g clip-path="url(#street-clip)">
      <g transform="translate(${ORIGIN.x} ${ORIGIN.y})"><g id="world" style="${PIVOT}">
        ${groundHatch(-600, 3000, 0, 20)}
        ${PROJECTS.map(project).join('')}
        <g data-part="search-far" opacity="0">${building(PROJECTS[0].floors, { x: PROJECTS[0].x, ground: 0, width: PROJECTS[0].width, storey: STOREY, weight: FAR_WEIGHT })}</g>
      </g></g>
    </g>
    <g data-part="labels" opacity="0">${PROJECTS.map(label).join('')}</g>`;
}

export default {
  duration: T,
  keyframes: [600, 2400, 6400, 9800],
  captions: [
    [0, 'This was a small project. The same shape runs at six units, or twelve.'],
    [4400, 'Every floor had its own session, its own inspection, and its own files on disk.'],
    [8000, 'Hand Claude Code a whole stack of changes. Come back to finished, reviewed work.'],
  ],
  theme: 'whiteprint',
  viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
  draw,
  // The world scales on one eased track so the pull-back reads as a camera move; then the labels fade in.
  choreograph(track) {
    track('#world', [
      [PULL.from, { transform: 'scale(1)', easing: 'ease-out' }], [PULL.to, { transform: `scale(${END_SCALE})` }],
    ]);
    track(part('search-far'), [[PULL.from, { opacity: 0 }], [PULL.to, { opacity: 1 }]]);
    track(part('labels'), [[PULL.to, { opacity: 0 }], [PULL.to + 800, { opacity: 1 }]]);
  },
};
