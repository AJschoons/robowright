// Shared drawings, as SVG strings. A group a scene animates or scales sits inside a translate to
// its pivot, so the pivot is the group's local origin (kit.css → pivots).

export function grid(id, width, height) {
  return `
    <defs>
      <pattern id="${id}-g20" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0V20H0" class="gridmin" fill="none"/></pattern>
      <pattern id="${id}-g100" width="100" height="100" patternUnits="userSpaceOnUse"><path d="M100 0V100H0" class="gridmaj" fill="none"/></pattern>
    </defs>
    <rect width="${width}" height="${height}" fill="url(#${id}-g20)"/>
    <rect width="${width}" height="${height}" fill="url(#${id}-g100)"/>`;
}

// The drawing's border, inset from the view box's edges.
export function frame(width, height, inset) {
  return `<rect x="${inset}" y="${inset}" width="${width - 2 * inset}" height="${height - 2 * inset}" class="ln"/>`;
}

// A two-row title block hung from its top-right corner; [data-clock] is the kit's clock.
export function titleBlock(x, y, top, clockLabel, clock) {
  return `
    <g transform="translate(${x} ${y})"><g class="grow-narrow" style="--grow:2"><g transform="translate(-176 0)">
      <rect width="176" height="56" class="paper" style="stroke:var(--fg);stroke-width:2"/>
      <path d="M0 28H176" class="ln thin"/>
      <text x="10" y="19" class="lbl">${top}</text>
      <text x="10" y="47" class="lbl">${clockLabel} <tspan data-clock>${clock}</tspan></text>
    </g></g></g>`;
}

// A Robowright robot's head, drawn about its centre, holding `tool`; `weights` are { line, brace }.
export function robot(tool, weights) {
  return `
    <rect x="-32" y="-22" width="64" height="54" rx="18" class="bgfill" style="stroke:var(--fg);stroke-width:${weights.line}"/>
    <path d="M0 -22V-37" class="ln" style="stroke-width:${weights.line}"/>
    <rect class="ant brass" x="-4" y="-52" width="8" height="13" rx="1.5"/>
    <g transform="translate(0 3)"><g class="eyes"><g transform="translate(0 -3)">
      <ellipse cx="-13" cy="3" rx="6.5" ry="9.5" class="ink"/><ellipse cx="13" cy="3" rx="6.5" ry="9.5" class="ink"/>
    </g></g></g>
    <path d="M-35 -10C-39 -10 -40 -8 -40 -4L-40 0C-40 4 -42 5 -46 5C-42 5 -40 6 -40 10L-40 14C-40 18 -39 20 -35 20" class="brassln" style="stroke-width:${weights.brace}"/>
    <path d="M35 -10C39 -10 40 -8 40 -4L40 0C40 4 42 5 46 5C42 5 40 6 40 10L40 14C40 18 39 20 35 20" class="brassln" style="stroke-width:${weights.brace}"/>
    ${tool}`;
}

// The Owner: hard hat, and the bulb of an idea, standing on the ground at the origin.
export function person() {
  return `
    <path d="M-9 -44V-4M9 -44V-4" class="ln" style="stroke-width:3.2"/>
    <rect x="-21" y="-92" width="42" height="52" rx="13" class="bgfill" style="stroke:var(--fg);stroke-width:3.2"/>
    <path d="M-6 -92L0 -82L6 -92" class="ln" style="stroke-width:2.4"/>
    <g transform="rotate(-28 26 -62)"><rect x="18" y="-80" width="12" height="40" rx="6" class="bgfill" style="stroke:var(--fg);stroke-width:2.8"/></g>
    <circle cx="0" cy="-112" r="15" class="bgfill" style="stroke:var(--fg);stroke-width:3.2"/>
    <circle cx="-5.5" cy="-114" r="2.4" class="ink"/><circle cx="5.5" cy="-114" r="2.4" class="ink"/>
    <path d="M-5 -106Q0 -102 5 -106" class="ln" style="stroke-width:2.2"/>
    <path d="M-16 -118A16 16 0 0 1 16 -118Z" class="brass" style="stroke:var(--brass);stroke-width:3;stroke-linejoin:round"/>
    <path d="M-22 -118H22" class="brassln" style="stroke-width:3.4"/>
    <path d="M0 -132V-122" style="fill:none;stroke:var(--bg);stroke-width:2.4;stroke-linecap:round"/>
    <circle cx="0" cy="-166" r="10" class="bgfill" style="stroke:var(--fg);stroke-width:2.6"/>
    <path d="M-5 -154H5M-4 -149H4" class="ln" style="stroke-width:2.4"/>
    <path d="M-20 -166H-15M15 -166H20M-14 -180L-11 -177M14 -180L11 -177M0 -186V-181" class="ln" style="stroke-width:2.2"/>`;
}

// The Worker's wrench; .swing pivots at the grip.
export function wrench() {
  return `
    <g transform="translate(59 42)"><g class="swing"><g transform="translate(-59 -42)">
      <g transform="translate(50 10) scale(1.35) translate(-50 -10)">
        <path d="M57 34L73 10" class="ln" style="stroke-width:7.1"/><path d="M71 -1A9 9 0 1 0 86 9" class="ln" style="stroke-width:5.8"/>
      </g>
    </g></g></g>`;
}

// The Reviewer's stamp, held up.
export function stamp() {
  return `
    <g transform="translate(50 10) scale(1.35) translate(-50 -10)">
      <circle cx="69" cy="-8" r="6" class="ln" style="stroke-width:4.4"/><path d="M69 -2V8" class="ln" style="stroke-width:4.4"/>
      <rect x="56" y="8" width="26" height="9" rx="2" class="ln" style="stroke-width:4.4"/>
      <path d="M58 27L65 34L80 21" class="ln" style="stroke-width:4.4"/>
    </g>`;
}

export function ladder(left, right, top, bottom, firstRung, rungStep) {
  const rungs = [];
  for (let y = firstRung; y < bottom; y += rungStep) rungs.push(`M${left} ${y}H${right}`);
  return `
    <path d="M${left} ${top}V${bottom}M${right} ${top}V${bottom}" class="ln"/>
    <path d="${rungs.join('')}" class="ln thin"/>`;
}

export function groundHatch(fromX, toX, y, step) {
  const hatch = [];
  for (let x = fromX + 10; x < toX - 20; x += step) hatch.push(`M${x} ${y + 12}l12-12`);
  return `
    <path d="M${fromX} ${y}H${toX}" class="ln"/>
    <path d="${hatch.join('')}" class="ln thin faint"/>`;
}

// The verdict stamps, drawn about their centre; `part` names the group a scene animates.
export function stampHold(part, text) {
  return `
    <g class="grow-narrow" style="--grow:1.3"><g data-part="${part}" class="stamp stamp-hold" opacity="0">
      <rect x="-62" y="-20" width="124" height="40" rx="6"/><text x="0" y="6" text-anchor="middle">${text}</text>
    </g></g>`;
}

export function stampAdvance(part, text, grow = 1.3) {
  return `
    <g class="grow-narrow" style="--grow:${grow}"><g data-part="${part}" class="stamp stamp-adv" opacity="0">
      <rect x="-65" y="-20" width="130" height="40" rx="6"/><text x="10" y="6" text-anchor="middle">${text}</text>
      <path d="M-55 0L-49 6L-38 -6" class="doneln"/>
    </g></g>`;
}

// The citation sheet a Reviewer hands back with a HOLD.
export function sheet(part) {
  return `
    <g data-part="${part}" opacity="0">
      <path d="M-14 -16H10L16 -10V16H-14Z" class="paper" style="stroke:var(--attn);stroke-width:2.4"/>
      <path d="M-9 -6H10M-9 1H10M-9 8H4" class="attnln" style="stroke-width:2"/>
    </g>`;
}

export function sparks(part) {
  return `<g data-part="${part}" opacity="0"><path d="M-2 -14l8-6M0 -2h10M-4 8l8 6" class="brassln" style="stroke-width:3"/></g>`;
}

// The Planner's pen; .swing pivots at the grip.
export function pen() {
  return `
    <g transform="translate(63 40)"><g class="swing"><g transform="translate(-63 -40)">
      <g transform="translate(50 10) scale(1.35) translate(-50 -10)">
        <path d="M62 29L80 -2" class="ln" style="stroke-width:7.1"/><path d="M74 8L80 -2" class="brassln" style="stroke-width:7.1"/>
        <path d="M56 39L59 30L65 33Z" class="ink"/>
      </g>
    </g></g></g>`;
}

// The Lead's clipboard.
export function clipboard() {
  return `
    <g transform="translate(50 10) scale(1.35) translate(-50 -10)">
      <rect x="54" y="-8" width="30" height="40" rx="3" class="ln" style="stroke-width:4.4"/>
      <rect x="62" y="-13" width="14" height="8" rx="2" class="ink"/>
      <path d="M60 6H78M60 14H78M60 22H72" class="ln" style="stroke-width:3"/>
    </g>`;
}

// Two arrows chasing each other round a circle, drawn about its centre; `part` names the group a
// scene turns, which pivots there.
export function cycle(part, radius) {
  const point = (degrees, distance) => {
    const a = degrees * Math.PI / 180;
    return [Math.cos(a) * distance, Math.sin(a) * distance].map(v => v.toFixed(1)).join(' ');
  };
  const arrow = (from, to) => {
    const tipAngle = to + 12;
    return `
      <path d="M${point(from, radius)}A${radius} ${radius} 0 0 1 ${point(to, radius)}" class="ln"/>
      <path d="M${point(tipAngle, radius)}L${point(to, radius - 6)}L${point(to, radius + 6)}Z" class="ink"/>`;
  };
  return `<g data-part="${part}" style="transform-box:view-box;transform-origin:0 0">${arrow(200, 328)}${arrow(20, 148)}</g>`;
}

// A question on a card, drawn about its centre; `part` names the card, `<part>-ask` its question
// mark and `<part>-check` the answer a scene shows in its place.
export function questionCard(part) {
  return `
    <g data-part="${part}" opacity="0">
      <path d="M-14 -16H10L16 -10V16H-14Z" class="paper" style="stroke:var(--fg);stroke-width:2.4"/>
      <g data-part="${part}-ask">
        <path d="M-5 -6Q-5 -11 1 -11Q7 -11 7 -6Q7 -2 1 0V3" class="ln" style="stroke-width:2.4"/><circle cx="1" cy="9" r="1.8" class="ink"/>
      </g>
      <path data-part="${part}-check" d="M-7 1L-2 6L8 -5" class="doneln" opacity="0"/>
    </g>`;
}

// .lbl is 11px monospace: 0.6em a character plus .08em of letter spacing.
const LABEL_ADVANCE = 7.5;

// A worktree's sign, its branch name on a board hung from the board's top-left corner.
export function worktreeSign(text) {
  const width = Math.ceil(text.length * LABEL_ADVANCE) + 20;
  return `
    <g class="grow-narrow" style="--grow:2">
      <rect width="${width}" height="26" class="paper" style="stroke:var(--fg);stroke-width:2"/>
      <text x="10" y="17" class="lbl">${text}</text>
    </g>`;
}

// A two-row title block like titleBlock(), whose bottom row is `bottom` as given: it holds the
// kit's [data-clock] only if `bottom` does. `part` names that row for a scene that shows it
// part-way, or is null.
export function titleBlockRows(x, y, top, bottom, part) {
  const named = part === null ? '' : ` data-part="${part}"`;
  return `
    <g transform="translate(${x} ${y})"><g class="grow-narrow" style="--grow:2"><g transform="translate(-176 0)">
      <rect width="176" height="56" class="paper" style="stroke:var(--fg);stroke-width:2"/>
      <path d="M0 28H176" class="ln thin"/>
      <text x="10" y="19" class="lbl">${top}</text>
      <text x="10" y="47" class="lbl"${named}>${bottom}</text>
    </g></g></g>`;
}

// One storey with its top-left at (x, y), or `storeys` equal storeys stacked down from it: a `fill`
// under an outline drawn in `look`. `outline` 'open-bottom' leaves the bottom edge to the storey
// below, and 'walls' the top edge too; `hidden` dashes the outline out for a scene to draw on.
// `roof` is path data stroked with an open outline, for a drawing whose roof shares its dashes.
// 'rise' is one storey a scene puts up, always dashed out: `<part>-walls`, both walls drawn bottom
// to top by one dash offset on their group, then `<part>-ceiling`, left to right; no bottom edge.
export function floor({ x, y, width, height, look, fill = null, part = null, style = null, storeys = 1, outline = 'box', hidden = false, roof = '' }) {
  const right = x + width;
  const bottom = y + storeys * height;
  const perimeter = 2 * (width + storeys * height);
  const dividers = [];
  for (let i = 1; i < storeys; i++) dividers.push(`M${x} ${y + i * height}H${right}`);
  const styles = [style, hidden ? `stroke-dasharray:${perimeter};stroke-dashoffset:${perimeter}` : null].filter(Boolean);
  const named = part === null ? '' : ` data-part="${part}"`;
  const styled = styles.length === 0 ? '' : ` style="${styles.join(';')}"`;
  const under = fill === null ? '' : `<rect x="${x}" y="${y}" width="${width}" height="${bottom - y}" class="${fill}"/>`;
  switch (outline) {
    case 'box': {
      const between = dividers.length === 0 ? '' : `<path d="${dividers.join('')}" class="${look}"/>`;
      return `${under}<rect${named} x="${x}" y="${y}" width="${width}" height="${bottom - y}" class="${look}"${styled}/>${between}`;
    }
    case 'open-bottom':
      return `${under}<path${named} d="M${x} ${bottom}V${y}H${right}V${bottom}${dividers.join('')}${roof}" class="${look}"${styled}/>`;
    case 'walls':
      return `${under}<path${named} d="M${x} ${bottom}V${y}M${right} ${y}V${bottom}${dividers.join('')}${roof}" class="${look}"${styled}/>`;
    case 'rise': {
      if (storeys !== 1) throw new Error(`floor: 'rise' puts up one storey, not ${storeys}`);
      const dashed = length => [style, `stroke-dasharray:${length};stroke-dashoffset:${length}`].filter(Boolean).join(';');
      return `${under}<g data-part="${part}-walls" style="${dashed(height)}">`
        + `<path d="M${x} ${bottom}V${y}" class="${look}"/><path d="M${right} ${bottom}V${y}" class="${look}"/></g>`
        + `<path data-part="${part}-ceiling" d="M${x} ${y}H${right}" class="${look}" style="${dashed(width)}"/>`;
    }
    default:
      throw new Error(`floor: no outline ${outline}`);
  }
}

// The Reader's magnifying glass.
export function magnifier() {
  return `
    <g transform="translate(50 10) scale(1.35) translate(-50 -10)">
      <path d="M57 33L67 18" class="ln" style="stroke-width:5.8"/>
      <circle cx="73" cy="9" r="10" class="ln" style="stroke-width:4.4"/>
      <path d="M67 6A7 7 0 0 1 72 2" class="ln" style="stroke-width:2.4"/>
    </g>`;
}

// A plain ruled page, drawn about its centre, with `label` over it or none when it is null; `part`
// names the page and its label together.
export function page(part, label) {
  const over = label === null ? '' : `<text y="-24" text-anchor="middle" class="lbl">${label}</text>`;
  return `
    <g data-part="${part}" opacity="0">
      <path d="M-13 -16H8L14 -10V16H-13Z" class="paper" style="stroke:var(--fg);stroke-width:2.4"/>
      <path d="M-8 -6H8M-8 1H8M-8 8H3" class="ln thin"/>
      ${over}
    </g>`;
}

// A strip of paper carrying one line, drawn about its centre; `part` names it.
export function slip(part) {
  return `
    <g data-part="${part}" opacity="0">
      <rect x="-22" y="-8" width="44" height="16" rx="2" class="paper" style="stroke:var(--fg);stroke-width:2.2"/>
      <path d="M-14 0H14" class="doneln" style="stroke-width:3"/>
    </g>`;
}

// A ledger sheet hung from its top-left corner, whose `lines` ruled lines a scene writes one at a
// time: `<part>-<i>`, from 1, each dashed out for a track to draw on.
export function ledger(part, width, height, lines) {
  const length = width - 28;
  const rows = [];
  for (let i = 1; i <= lines; i++) {
    rows.push(`<path data-part="${part}-${i}" d="M14 ${14 + i * 16}H${14 + length}" class="ln thin"
      style="stroke-dasharray:${length};stroke-dashoffset:${length}"/>`);
  }
  return `
    <path d="M0 0H${width - 16}L${width} 16V${height}H0Z" class="paper" style="stroke:var(--fg);stroke-width:2.4"/>
    <path d="M${width - 16} 0V16H${width}" class="ln thin"/>
    ${rows.join('')}`;
}

// A long log hung from its top-left corner: many short lines, the last one the verdict.
export function log(width, height) {
  const lengths = [0.8, 0.55, 0.7, 0.4, 0.75, 0.6, 0.85, 0.5, 0.65, 0.45, 0.8, 0.6];
  const usable = width - 24;
  const rows = [];
  for (let y = 14, i = 0; y < height - 24; y += 10, i++) {
    rows.push(`M12 ${y}h${Math.round(usable * lengths[i % lengths.length])}`);
  }
  return `
    <rect width="${width}" height="${height}" class="paper" style="stroke:var(--fg);stroke-width:2.4"/>
    <path d="${rows.join('')}" class="ln thin faint"/>
    <path d="M12 ${height - 12}H${12 + Math.round(usable * 0.6)}" class="doneln"/>`;
}

// A context meter hung from its top-left corner: `part` names the fill a scene grows from the left
// edge, and a tick stands at `mark`, the fraction at which the session hands off.
export function meter(part, width, height, mark) {
  return `
    <g data-part="${part}" style="transform-box:view-box;transform-origin:0 0"><rect width="${width}" height="${height}" class="brass"/></g>
    <rect width="${width}" height="${height}" class="ln thin"/>
    <path d="M${width * mark} -4V${height + 4}" class="ln thin"/>`;
}

// A pin board on two legs, hung from its top-left corner; the legs reach `legs` below it.
export function board(width, height, legs) {
  return `
    <path d="M14 ${height}V${height + legs}M${width - 14} ${height}V${height + legs}" class="ln"/>
    <rect width="${width}" height="${height}" rx="3" class="paper" style="stroke:var(--fg);stroke-width:2.4"/>`;
}

// The Owner's line, after the hero's dashed loop: a dashed rule from `from` to `to` at `y`, with
// `text` on a knockout centred at `labelX`.
export function ownerLine(from, to, y, labelX, text) {
  const width = Math.ceil(text.length * LABEL_ADVANCE) + 12;
  return `
    <path d="M${from} ${y}H${to}" class="ln thin" style="stroke-dasharray:9 7"/>
    <g transform="translate(${labelX} ${y})"><g class="grow-narrow" style="--grow:2">
      <rect x="${-width / 2}" y="-4.5" width="${width}" height="9.5" class="bgfill"/>
      <text y="3" text-anchor="middle" class="lbl">${text}</text>
    </g></g>`;
}

// A window pane, its top-left at (x, y).
export function pane(x, y) {
  return `<rect x="${x}" y="${y}" width="44" height="30" class="ln thin"/>`;
}

// A floor's tick, drawn about its centre (cx, cy).
export function check(cx, cy) {
  return `<path d="M${cx - 11.5} ${cy}l8 8l15-16" class="doneln"/>`;
}

// A floor's door, standing on (x, y) at its bottom-left corner, checked off.
export function door(x, y) {
  return `<rect x="${x}" y="${y - 46}" width="40" height="46" class="ln thin"/><path d="M${x + 9} ${y - 24}l8 8l15-16" class="doneln"/>`;
}

// A finished building of `floors` storeys standing on (x, ground) at its bottom-left corner: every
// floor done, with two windows, a ticked door on the ground floor and a tick centred on every floor
// above it, a roof over the top. `weight` is the outline's stroke width, heavier for a building seen
// from far off, or null for the class's own.
export function building(floors, { x, ground, width, storey, weight }) {
  const style = weight === null ? null : `stroke-width:${weight}`;
  const storeys = [];
  for (let i = 1; i <= floors; i++) {
    const y = ground - i * storey;
    const windows = `${pane(x + 30, y + 22)}${pane(x + width - 74, y + 22)}`;
    const fittings = i === 1
      ? `${windows}${door(x + width / 2 - 20, ground)}`
      : `${windows}${check(x + width / 2, y + storey / 2)}`;
    storeys.push(`${floor({ x, y, width, height: storey, fill: 'donefill', look: 'ln', style })}${fittings}`);
  }
  const top = ground - floors * storey;
  const styled = style === null ? '' : ` style="${style}"`;
  return `${storeys.join('')}<path d="M${x - 10} ${top}L${x + width / 2} ${top - 62}L${x + width + 10} ${top}" class="ln"${styled}/>`;
}

// A robot's head alone, drawn about its centre in heavy strokes, for a building seen from far off.
export function tinyRobot() {
  return `
    <rect x="-24" y="-17" width="48" height="40" rx="13" class="bgfill" style="stroke:var(--fg);stroke-width:6"/>
    <path d="M0 -17V-29" class="ln" style="stroke-width:6"/>
    <rect x="-5" y="-39" width="10" height="11" rx="2" class="brass"/>
    <ellipse cx="-10" cy="3" rx="5" ry="7.5" class="ink"/><ellipse cx="10" cy="3" rx="5" ry="7.5" class="ink"/>`;
}

// The Owner's seal, drawn about its centre: a brass ring with `text` on a band across it; `part`
// names the group a scene stamps down.
export function brassStamp(part, text) {
  return `
    <g class="grow-narrow" style="--grow:1.4"><g data-part="${part}" class="stamp" opacity="0">
      <circle r="40" class="bgfill" style="stroke:var(--brass);stroke-width:4"/>
      <circle r="33" style="fill:none;stroke:var(--brass);stroke-width:1.6"/>
      <rect x="-56" y="-14" width="112" height="28" rx="3" class="bgfill" style="stroke:var(--brass);stroke-width:3"/>
      <text x="0" y="6" text-anchor="middle" style="fill:var(--brass)">${text}</text>
    </g></g>`;
}

// The Owner's desk, its top's left end at the origin, standing on the ground 100 below.
export function desk() {
  return `
    <path d="M0 0H410" class="ln" style="stroke-width:4"/><path d="M0 8H410" class="ln thin"/>
    <path d="M60 8V100M390 8V100" class="ln"/>`;
}

// A monitor hung from its screen's top-left corner, 186 by 124, its stand reaching 16 down to the
// desk; `part` names the screen.
export function monitor(part) {
  return `
    <path d="M93 124V140M68 140H118" class="ln"/>
    <rect data-part="${part}" width="186" height="124" rx="5" class="paper" style="stroke:var(--fg);stroke-width:3"/>`;
}

// The Owner's hard hat, drawn about its brim's centre, as person() wears it; `part` names the group
// a scene lifts.
export function hat(part) {
  return `
    <g data-part="${part}" style="transform-box:view-box;transform-origin:0 0">
      <path d="M-16 0A16 16 0 0 1 16 0Z" class="brass" style="stroke:var(--brass);stroke-width:3;stroke-linejoin:round"/>
      <path d="M-22 0H22" class="brassln" style="stroke-width:3.4"/>
      <path d="M0 -14V-4" style="fill:none;stroke:var(--bg);stroke-width:2.4;stroke-linecap:round"/>
    </g>`;
}

// The Owner of person(), seated at a desk facing right, drawn about the hips on the seat, the chair
// on the ground 80 below. A scene shows one of each pair by opacity: `<part>-open` or
// `<part>-squint` (the eyes and mouth), and one arm of `<part>-rest`, `<part>-type` (the hand at
// 84, −30) or `<part>-reach` (the hand up at 66, −84); `<part>-sweat` and
// `<part>-bulb` start hidden. `<part>-head` turns about the neck. `wearsHat` puts the hard hat on.
export function seatedOwner(part, { wearsHat }) {
  const arm = (name, d, opacity) => `<path data-part="${part}-${name}" d="${d}" class="ln" style="stroke-width:3.2" opacity="${opacity}"/>`;
  return `
    <path d="M-26 -2V-52Q-26 -58 -20 -58" class="ln" style="stroke-width:3.2"/>
    <path d="M-30 2H26" class="ln" style="stroke-width:3.4"/>
    <path d="M-2 2V70M-24 70H20" class="ln"/>
    <circle cx="-24" cy="76" r="5" class="ln thin"/><circle cx="20" cy="76" r="5" class="ln thin"/>
    <path d="M-6 -4Q10 -4 36 -2V72M42 -2V72" class="ln" style="stroke-width:3.2"/>
    <path d="M30 72H54" class="ln"/>
    <rect x="-19" y="-56" width="40" height="54" rx="13" class="bgfill" style="stroke:var(--fg);stroke-width:3.2"/>
    <path d="M-5 -56L1 -46L7 -56" class="ln" style="stroke-width:2.4"/>
    ${arm('rest', 'M16 -40Q48 -40 70 -28', 1)}
    ${arm('type', 'M16 -40Q50 -44 76 -32L84 -30', 0)}
    ${arm('reach', 'M16 -40Q46 -62 66 -84', 0)}
    <g transform="translate(2 -62)"><g data-part="${part}-head" style="transform-box:view-box;transform-origin:0 0"><g transform="translate(0 -16)">
      <circle r="15" class="bgfill" style="stroke:var(--fg);stroke-width:3.2"/>
      <g data-part="${part}-open">
        <circle cx="-4" cy="-2" r="2.4" class="ink"/><circle cx="7" cy="-2" r="2.4" class="ink"/>
        <path d="M-3 6Q2 10 7 6" class="ln" style="stroke-width:2.2"/>
      </g>
      <g data-part="${part}-squint" opacity="0">
        <path d="M-7 -2H-1M4 -2H10" class="ln" style="stroke-width:2.6"/><path d="M-8 -9L-1 -6M11 -9L4 -6" class="ln" style="stroke-width:2.2"/>
        <path d="M-2 8H7" class="ln" style="stroke-width:2.2"/>
      </g>
      <path data-part="${part}-sweat" d="M22 -6Q28 4 22 8Q16 4 22 -6Z" class="ln thin" style="stroke:var(--run)" opacity="0"/>
      ${wearsHat ? `<g transform="translate(0 -6)">${hat(`${part}-hat`)}</g>` : ''}
    </g></g></g>
    <g data-part="${part}-bulb" opacity="0" transform="translate(2 -132)">
      <circle r="10" class="bgfill" style="stroke:var(--fg);stroke-width:2.6"/>
      <path d="M-5 12H5M-4 17H4" class="ln" style="stroke-width:2.4"/>
      <path d="M-20 0H-15M15 0H20M-14 -14L-11 -11M14 -14L11 -11M0 -20V-15" class="ln" style="stroke-width:2.2"/>
    </g>`;
}

// A speech bubble with one line, drawn about the tip of its tail, its body up and to the right;
// `part` names it, scaled about the tip.
export function bubble(part, text) {
  const width = Math.ceil(text.length * LABEL_ADVANCE) + 20;
  const [left, top, bottom, r] = [-8, -40, -12, 9];
  const right = left + width;
  const outline = `M${left + r} ${top}H${right - r}A${r} ${r} 0 0 1 ${right} ${top + r}V${bottom - r}A${r} ${r} 0 0 1 ${right - r} ${bottom}`
    + `H26L0 0L10 ${bottom}H${left + r}A${r} ${r} 0 0 1 ${left} ${bottom - r}V${top + r}A${r} ${r} 0 0 1 ${left + r} ${top}Z`;
  return `
    <g class="grow-narrow"><g data-part="${part}" opacity="0" style="transform-box:view-box;transform-origin:0 0">
      <path d="${outline}" class="paper" style="stroke:var(--fg);stroke-width:2.2;stroke-linejoin:round"/>
      <text x="${left + width / 2}" y="${top + 18}" text-anchor="middle" class="lbl" style="fill:var(--fg)">${text}</text>
    </g></g>`;
}

// A wall clock drawn about its centre; `<part>-hour` and `<part>-minute` are its hands, drawn at
// twelve, which a scene turns about the centre.
export function wallClock(part) {
  return `
    <circle r="26" class="paper" style="stroke:var(--fg);stroke-width:3"/>
    <path d="M0 -20V-16M0 20V16M-20 0H-16M20 0H16" class="ln" style="stroke-width:2.2"/>
    <g data-part="${part}-hour" style="transform-box:view-box;transform-origin:0 0"><path d="M0 0V-12" class="ln"/></g>
    <g data-part="${part}-minute" style="transform-box:view-box;transform-origin:0 0"><path d="M0 0V-18" class="ln" style="stroke-width:2.4"/></g>
    <circle r="2" class="ink"/>`;
}

// The Enter key on its plate, drawn about the plate's bottom centre on the desk; `part` names the
// cap a scene presses down about that point, and `<part>-press` the marks a press makes.
export function enterKey(part) {
  return `
    <g class="grow-narrow">
      <rect x="-30" y="-12" width="60" height="12" rx="3" class="paper" style="stroke:var(--fg);stroke-width:2"/>
      <g data-part="${part}" style="transform-box:view-box;transform-origin:0 0">
        <rect x="-15" y="-24" width="30" height="24" rx="3" class="paper" style="stroke:var(--fg);stroke-width:2.6"/>
        <text y="-7" text-anchor="middle" class="lbl" style="fill:var(--fg);font-size:14px">↵</text>
      </g>
      <path data-part="${part}-press" d="M-12 -30L-16 -38M0 -32V-41M12 -30L16 -38" class="brassln" style="stroke-width:2.4" opacity="0"/>
    </g>`;
}

const DASHBOARD_SEGMENT = 112;
const DASHBOARD_GAP = 6;
const DASHBOARD_FILL = { done: 'var(--done)', working: 'var(--run)' };

// One project's bar on the dashboard, drawn from its top-left end, 20 high: one segment per unit
// in `states`, each `done` or `working`. `<part>-<n>` names segment n's fill, which a scene grows
// from the segment's left end.
export function dashboardBar(part, states) {
  return states.map((state, i) => {
    const x = i * (DASHBOARD_SEGMENT + DASHBOARD_GAP);
    return `
    <rect x="${x}" width="${DASHBOARD_SEGMENT}" height="20" rx="4" style="fill:var(--track)"/>
    <g transform="translate(${x} 0)"><rect data-part="${part}-${i + 1}" width="${DASHBOARD_SEGMENT}" height="20" rx="4" style="fill:${DASHBOARD_FILL[state]};transform-box:view-box;transform-origin:0 0"/></g>`;
  }).join('');
}
