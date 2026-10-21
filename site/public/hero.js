// The hero: the README hero's composition (assets/hero-light.svg) rebuilt from the shared drawings,
// with live text. Positions inside the lifted group are the README's, so the two can be compared.
import { followViewBox } from './kit.js';
import { grid, frame, robot, person, ladder, groundHatch, floor } from './scenes/parts.js';

const WIDTH = 1200;
const HEIGHT = 720;
const NARROW_HEIGHT = 1520;    // room under the drawing for the key at phone width
const ROBOT_WEIGHTS = { line: 3.2, brace: 4.4 };
const ACCESSIBLE_NAME = 'A blueprint: the Owner and the Robowright crew turning one brief into a three-storey building of work units.';

const ROLES = [
  { digit: 1, label: 'OWNER', x: 76.5, y: 628.5 },
  { digit: 2, label: 'PLANNER', x: 215.1, y: 628.5 },
  { digit: 3, label: 'LEAD', x: 731.9, y: 138.5 },
  { digit: 4, label: 'WORKERS', x: 720.5, y: 464.5 },
  { digit: 4, label: 'READER', x: 847.8, y: 628.5 },
  { digit: 5, label: 'REVIEWER', x: 930.6, y: 268.5 },
  { digit: 6, label: 'EXPLAINER', x: 1047, y: 628.5 },
];
const FLOORS = [
  { label: 'UNIT 3', name: 'highlight-matches', top: 300 },
  { label: 'UNIT 2', name: 'search-bar', top: 400 },
  { label: 'UNIT 1', name: 'search-index', top: 500 },
];
const ONE_BRIEF = 'one brief';
const ETC = 'etc.';
const OWNER_LOOP = 'owner reviews and merges, or replans';
const TITLE = { wordmark: 'robowright', project: 'SAMPLE PROJECT', view: 'ELEVATION A', sheet: 'SHEET 1/1', revision: 'REV A' };

// Each robot blinks once, all within five seconds of load, so the hero needs no pause control
// (WCAG 2.2.2); none under reduced motion.
const BLINK_DELAYS_MS = [600, 1500, 2300, 1100, 3000, 3800, 2700, 4400, 1900];
const BLINK = [{ transform: 'scaleY(1)' }, { transform: 'scaleY(.12)', offset: 70 / 160 }, { transform: 'scaleY(1)' }];
const BLINK_MS = 160;

const line = width => `class="ln" style="stroke-width:${width}"`;

const PROPS = {
  compass: `<path d="M58 34L68 -6L78 34" ${line(3.2)}/><path d="M68 -6V-16" ${line(3.2)}/><circle cx="68" cy="-6" r="3.5" class="ink"/><path d="M61 22Q68 26 75 22" ${line(2.4)}/>`,
  wrench: `<g transform="translate(-7 0)"><path d="M57 34L73 10" ${line(5.12)}/><path d="M71 -1A9 9 0 1 0 86 9" ${line(4.16)}/></g>`,
  book: `<path d="M69 2C63 -2 57 -2 52 0V30C57 28 63 28 69 32C75 28 81 28 86 30V0C81 -2 75 -2 69 2Z" ${line(3.2)}/><path d="M69 2V32" ${line(2.4)}/>`,
  stamp: `<circle cx="69" cy="-8" r="6" ${line(3.2)}/><path d="M69 -2V8" ${line(3.2)}/><rect x="56" y="8" width="26" height="9" rx="2" ${line(3.2)}/><path d="M58 27L65 34L80 21" ${line(3.2)}/>`,
  clipboard: `<rect x="54" y="-8" width="30" height="40" rx="3" ${line(3.2)}/><rect x="62" y="-13" width="14" height="8" rx="2" class="ink"/><path d="M60 6H78M60 14H78M60 22H72" ${line(2.4)}/>`,
  speech: `<g transform="translate(20 22) scale(0.62)"><path d="M62 -78H102Q114 -78 114 -66V-44Q114 -32 102 -32H74L52 -18L62 -32Q50 -32 50 -44V-66Q50 -78 62 -78Z" class="ln" style="stroke-width:5.2"/><circle cx="65" cy="-55" r="5.5" class="ink"/><circle cx="82" cy="-55" r="5.5" class="ink"/><circle cx="99" cy="-55" r="5.5" class="ink"/></g>`,
};

function figure(x, y, scale, prop) {
  return `<g transform="translate(${x} ${y}) scale(${scale})">${robot(PROPS[prop], ROBOT_WEIGHTS)}</g>`;
}

function badge({ digit, label, x, y }) {
  return `
    <g transform="translate(${x} ${y})"><g class="grow-narrow" style="--grow:2">
      <circle r="10.5" class="bgfill" style="stroke:var(--fg);stroke-width:2"/>
      <text y="4" text-anchor="middle" class="badge">${digit}</text>
    </g></g>
    <text x="${x + 18}" y="${y + 5}" class="hlbl wide-only">${label}</text>`;
}

function building() {
  return `
    ${floor({ x: 470, y: 400, width: 360, height: 100, storeys: 2, outline: 'open-bottom', look: 'ln', style: 'stroke-width:2.6' })}
    ${floor({ x: 470, y: 300, width: 360, height: 100, outline: 'walls', look: 'ln', style: 'stroke-width:2.6;stroke-dasharray:10 8', roof: 'M456 300L650 236L844 300' })}
    <path d="M492 532h40v30h-40ZM768 532h40v30h-40Z" ${line(2.2)}/>
    <path d="M627 600V528H673V600" ${line(2.6)}/>
    <path d="M641 563L648 570L660 555" ${line(3)}/>
    <path d="M470 196H830M470 184V208M830 184V208M464 202L476 190M824 202L836 190" ${line(2.2)}/>
    <text x="650" y="186" text-anchor="middle" class="hlbl wide-only">${ONE_BRIEF.toUpperCase()}</text>
    <text x="650" y="180" text-anchor="middle" class="hlbl narrow-only">${ONE_BRIEF.toUpperCase()}</text>
    <path d="M444 600V300M432 600H456M438 606L450 594M432 500H456M438 506L450 494M432 400H456M438 406L450 394M432 300H456M438 306L450 294" ${line(2.2)}/>
    <path d="M444 300V248" ${line(2.2)} stroke-dasharray="6 6"/>
    <text x="436" y="280" text-anchor="end" class="hlbl">${ETC.toUpperCase()}</text>
    ${FLOORS.map(({ label, name, top }) => `
      <text x="432" y="${top + 47}" text-anchor="end" class="hlbl floor">${label}</text>
      <text x="432" y="${top + 65}" text-anchor="end" class="hlbl name wide-only">${name}</text>`).join('')}`;
}

function cast() {
  return `
    <g transform="translate(84 600)">${person()}</g>
    ${figure(240, 566.4, 0.8, 'compass')}
    <path d="M143.4 533.8A24 24 0 0 1 186.8 530.0" ${line(3)}/><path d="M190.3 536.1L192.0 527.0L181.6 533.0Z" class="ink"/>
    <path d="M188.6 550.2A24 24 0 0 1 145.2 554.0" ${line(3)}/><path d="M141.7 547.9L140.0 557.0L150.4 551.0Z" class="ink"/>
    <path d="M218 448H250L262 460V502H218Z M250 448V460H262M227 472H253M227 482H253M227 492H244" ${line(2.6)}/>
    <path d="M240 440C270 266 358 196 444 196" ${line(2.2)} stroke-dasharray="9 7"/>
    <path d="M442 189L456 196L442 203Z" class="ink"/>
    ${figure(520, 466.4, 0.8, 'wrench')}
    ${figure(630, 466.4, 0.8, 'wrench')}
    <g opacity="0.3">${figure(560, 366.4, 0.8, 'wrench')}${figure(700, 366.4, 0.8, 'wrench')}</g>
    ${ladder(870, 896, 290, 600, 316, 22)}
    ${figure(883, 466.4, 0.8, 'book')}
    ${ladder(962, 988, 290, 600, 316, 22)}
    ${figure(975, 396, 0.8, 'stamp')}
    ${figure(632, 127.2, 0.9, 'clipboard')}
    ${figure(1080, 566.4, 0.8, 'speech')}
    ${ROLES.map(badge).join('')}`;
}

function titleBlock() {
  return `
    <rect x="900" y="40" width="260" height="110" class="bgfill" style="stroke:var(--fg);stroke-width:3"/>
    <path d="M900 96H1160M1040 96V150" ${line(2)}/>
    <text x="1030" y="79" text-anchor="middle" class="wordmark">${TITLE.wordmark}</text>
    <text x="913" y="118" class="tb">${TITLE.project}</text>
    <text x="913" y="140" class="tb">${TITLE.view}</text>
    <text x="1053" y="118" class="tb">${TITLE.sheet}</text>
    <text x="1053" y="140" class="tb">${TITLE.revision}</text>`;
}

function ownerLoop() {
  return `
    <path d="M1096 632V670H108V636" ${line(2.2)} stroke-dasharray="9 7"/>
    <path d="M101 642L108 630L115 642Z" class="ink"/>
    <rect x="392" y="660" width="420" height="20" class="bgfill wide-only"/>
    <rect x="124" y="648" width="956" height="44" class="bgfill narrow-only"/>
    <text x="602" y="675" text-anchor="middle" class="hlbl wide-only">${OWNER_LOOP.toUpperCase()}</text>
    <text x="602" y="682" text-anchor="middle" class="hlbl loop narrow-only">${OWNER_LOOP.toUpperCase()}</text>
    <path d="M584 616H600L606 622V644H584Z" class="bgfill" style="stroke:var(--fg);stroke-width:2;stroke-linejoin:round"/>
    <path d="M589 628H601M589 634H601M589 640H596" ${line(1.6)}/>
    <path d="M596 620H612L618 626V648H596Z" class="bgfill" style="stroke:var(--fg);stroke-width:2;stroke-linejoin:round"/>
    <path d="M601 632H613M601 638H613M601 644H608" ${line(1.6)}/>`;
}

// At phone width the role names, unit names and title block move under the drawing.
function narrowKey() {
  const roles = ROLES.map(({ digit, label }, i) => {
    const x = i % 2 ? 640 : 60;
    const y = 790 + Math.floor(i / 2) * 70;
    return `
      <circle cx="${x + 24}" cy="${y - 12}" r="24" class="bgfill" style="stroke:var(--fg);stroke-width:3"/>
      <text x="${x + 24}" y="${y - 2}" text-anchor="middle" class="badge key-digit">${digit}</text>
      <text x="${x + 64}" y="${y}" class="hlbl">${label}</text>`;
  }).join('');
  const floors = FLOORS.map(({ label, name }, row) => `
    <text x="60" y="${1080 + row * 56}" class="hlbl">${label}</text>
    <text x="300" y="${1080 + row * 56}" class="hlbl">${name}</text>`).join('');
  return `
    <g class="narrow-only">
      ${roles}${floors}
      <g transform="translate(-1666 1150) scale(2.2)">${titleBlock()}</g>
    </g>`;
}

function draw() {
  return `
    ${grid('hero', WIDTH, NARROW_HEIGHT)}
    <g class="wide-only">${frame(WIDTH, HEIGHT, 20)}</g>
    <g class="narrow-only">${frame(WIDTH, NARROW_HEIGHT, 20)}</g>
    <g class="wide-only">${titleBlock()}</g>
    <g transform="translate(0 -16)">
      ${groundHatch(36, 1164, 600, 22)}
      ${building()}
      ${cast()}
    </g>
    ${ownerLoop()}
    ${narrowKey()}`;
}

function blink(svg) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  svg.querySelectorAll('.eyes').forEach((eyes, i) => {
    eyes.animate(BLINK, { duration: BLINK_MS, delay: BLINK_DELAYS_MS[i % BLINK_DELAYS_MS.length] });
  });
}

export function mountHero(container) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', ACCESSIBLE_NAME);
  svg.innerHTML = draw();
  followViewBox(svg, { wide: `0 0 ${WIDTH} ${HEIGHT}`, narrow: `0 0 ${WIDTH} ${NARROW_HEIGHT}` });
  container.append(svg);
  blink(svg);
}
