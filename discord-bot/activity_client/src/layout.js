// Where the floating QTE widgets go. Pure code, so it can be tested without a browser.
//
// Rule: widgets never overlap each other, and they stay inside the playing area (the chat), clear of its edges.
// "random" scatters them (the point of the floating buttons); the other placements stack them along an edge.

export const GAP = 14;      // minimum air between two widgets
export const EDGE = 10;     // distance kept from the edges of the area
const GRID = 12;            // step of the search for a free place when random tries fail

const overlaps = (a, b, gap = GAP) => a.x < b.x + b.w + gap && a.x + a.w + gap > b.x && a.y < b.y + b.h + gap && a.y + a.h + gap > b.y;

function insideArea(area, w, h) {
  return {
    minX: area.left + EDGE, maxX: Math.max(area.left + EDGE, area.left + area.width - w - EDGE),
    minY: area.top + EDGE, maxY: Math.max(area.top + EDGE, area.top + area.height - h - EDGE),
  };
}

// A free spot for a `w` x `h` box among the `taken` boxes. Random, but never overlapping when there is room: of a dozen
// random candidates the free one with the most air around it is taken (so the widgets spread out and leave room for the
// next ones); when none is free, every free place on a grid is tried, and only when there is truly none, the candidate
// farthest from the others (so the overlap is as small as it can be).
export function randomSpot(area, taken, { w, h }, rng = Math.random, tries = 14) {
  const r = insideArea(area, w, h);
  const air = (box) => (taken.length ? Math.min(...taken.map((t) => Math.hypot(box.x + w / 2 - (t.x + t.w / 2), box.y + h / 2 - (t.y + t.h / 2)))) : Infinity);
  const free = (box) => !taken.some((t) => overlaps(box, t));
  let pick = null, pickAir = -1, any = null, anyAir = -1;
  for (let i = 0; i < tries; i++) {
    const box = { x: r.minX + rng() * (r.maxX - r.minX), y: r.minY + rng() * (r.maxY - r.minY), w, h };
    const a = air(box);
    if (free(box) && (a > pickAir || pick === null)) { pick = box; pickAir = a; }
    if (a > anyAir) { any = box; anyAir = a; }
  }
  if (pick) return { x: Math.round(pick.x), y: Math.round(pick.y) };
  const open = [];
  for (let y = r.minY; y <= r.maxY + 0.5; y += GRID) {
    for (let x = r.minX; x <= r.maxX + 0.5; x += GRID) {
      const box = { x, y, w, h };
      if (free(box)) open.push(box);
    }
  }
  if (open.length) { const chosen = open[Math.floor(rng() * open.length)]; return { x: Math.round(chosen.x), y: Math.round(chosen.y) }; }
  return any ? { x: Math.round(any.x), y: Math.round(any.y) } : { x: Math.round(r.minX), y: Math.round(r.minY) };
}

// Fixed placements: slots along the bottom (centred row, wraps upwards), or along the left / right edge (stack, bottom up).
export function edgeSpot(area, taken, { w, h }, placement) {
  const r = insideArea(area, w, h);
  const step = (box) => !taken.some((t) => overlaps(box, t));
  if (placement === "bottom") {
    const cx = area.left + area.width / 2;
    for (let row = 0; row < 6; row++) {
      const y = r.maxY - row * (h + GAP);
      const slots = Math.max(1, Math.floor((area.width - 2 * EDGE + GAP) / (w + GAP)));
      for (let i = 0; i < slots; i++) {
        // alternate right/left of the centre: 0, +1, -1, +2, ...
        const shift = (i % 2 ? 1 : -1) * Math.ceil(i / 2);
        const x = Math.min(r.maxX, Math.max(r.minX, cx - w / 2 + shift * (w + GAP)));
        const box = { x, y: Math.max(r.minY, y), w, h };
        if (step(box)) return { x: Math.round(box.x), y: Math.round(box.y) };
      }
    }
  } else {
    const x = placement === "left" ? r.minX : r.maxX;
    for (let col = 0; col < 4; col++) {
      for (let row = 0; row < 8; row++) {
        const box = { x: placement === "left" ? x + col * (w + GAP) : x - col * (w + GAP), y: r.maxY - row * (h + GAP), w, h };
        if (box.y < r.minY - 1 || box.x < r.minX - 1 || box.x > r.maxX + 1) continue;
        if (step(box)) return { x: Math.round(box.x), y: Math.round(box.y) };
      }
    }
  }
  return randomSpot(area, taken, { w, h });
}

export function pickSpot(area, taken, size, placement = "random", rng = Math.random) {
  return placement === "random" ? randomSpot(area, taken, size, rng) : edgeSpot(area, taken, size, placement);
}

export const overlapsAny = (box, taken) => taken.some((t) => overlaps(box, t));

// A place for a widget that never overlaps: at full size if there is room, otherwise the widget is made smaller until it
// fits (a crowded screen shrinks the newest button instead of stacking it on another). `boxAt(k)` is the footprint at scale k.
export const SCALES = [1, 0.86, 0.74, 0.62];
export function pickSpotFit(area, taken, boxAt, placement = "random", rng = Math.random, scales = SCALES) {
  let last = null;
  for (const k of scales) {
    const size = boxAt(k);
    const spot = pickSpot(area, taken, size, placement, rng);
    last = { ...spot, ...size, k };
    if (!overlapsAny(last, taken)) return last;
  }
  return last;                                           // nothing fits even at the smallest size: the least bad spot
}

// Keep a spot inside the area after it changed (rotation, keyboard, resize).
export function clampSpot(area, spot, { w, h }) {
  const r = insideArea(area, w, h);
  return { x: Math.round(Math.min(r.maxX, Math.max(r.minX, spot.x))), y: Math.round(Math.min(r.maxY, Math.max(r.minY, spot.y))) };
}

// ---- last resort: lay everybody out again ------------------------------------------------------------------------------------
// When a screen is so crowded that the widgets cannot be placed one by one without touching, they are all laid out in rows
// (most urgent first), smaller if need be. This moves buttons that were already there, so it is only done to avoid overlapping.
function shelf(area, boxes) {
  const minX = area.left + EDGE, maxX = area.left + area.width - EDGE, maxY = area.top + area.height - EDGE;
  let x = minX, y = area.top + EDGE, rowHeight = 0;
  const out = [];
  for (const b of boxes) {
    if (x > minX && x + b.w > maxX + 0.5) { x = minX; y += rowHeight + GAP; rowHeight = 0; }
    if (x + b.w > maxX + 0.5 || y + b.h > maxY + 0.5) return null;
    out.push({ x: Math.round(x), y: Math.round(y) });
    x += b.w + GAP;
    rowHeight = Math.max(rowHeight, b.h);
  }
  return out;
}

export function packAll(area, boxAts, scales = [1, 0.86, 0.74, 0.62, 0.52, 0.44]) {
  for (const k of scales) {
    const boxes = boxAts.map((at) => at(k));
    const spots = shelf(area, boxes);
    if (spots) return spots.map((s, i) => ({ ...s, ...boxes[i], k }));
  }
  return null;
}

export function anyOverlap(boxes) {
  return boxes.some((a, i) => boxes.slice(i + 1).some((b) => overlaps(a, b, 0)));
}
