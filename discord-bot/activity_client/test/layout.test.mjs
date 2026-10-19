import test from "node:test";
import assert from "node:assert/strict";
import { randomSpot, edgeSpot, pickSpot, pickSpotFit, clampSpot, packAll, anyOverlap, GAP, EDGE } from "../src/layout.js";

const AREA = { left: 300, top: 150, width: 640, height: 540 };
const BOX = { w: 140, h: 190 };

// a deterministic "random" so the tests do not flake
function seeded(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; };
}
const touch = (a, b) => a.x < b.x + b.w + GAP - 1 && a.x + a.w + GAP - 1 > b.x && a.y < b.y + b.h + GAP - 1 && a.y + a.h + GAP - 1 > b.y;
const inside = (a) => a.x >= AREA.left + EDGE - 1 && a.y >= AREA.top + EDGE - 1 && a.x + a.w <= AREA.left + AREA.width - EDGE + 1 && a.y + a.h <= AREA.top + AREA.height - EDGE + 1;

test("random spots never overlap each other and stay inside the area", () => {
  for (let seed = 1; seed <= 60; seed++) {
    const rng = seeded(seed), taken = [];
    for (let i = 0; i < 3; i++) {
      const spot = randomSpot(AREA, taken, BOX, rng);
      taken.push({ ...spot, ...BOX });
    }
    taken.forEach((a, i) => { assert.ok(inside(a), `seed ${seed}: widget ${i} left the area`); taken.slice(i + 1).forEach((b, j) => assert.ok(!touch(a, b), `seed ${seed}: widgets ${i} and ${i + 1 + j} overlap`)); });
  }
});

test("spots look random: different seeds give different places", () => {
  const spots = new Set(Array.from({ length: 12 }, (_, i) => JSON.stringify(randomSpot(AREA, [], BOX, seeded(i + 7)))));
  assert.ok(spots.size >= 10);
});

test("a crowded area still gives a place, as far from the others as it can", () => {
  const taken = [{ x: AREA.left + 10, y: AREA.top + 10, w: 400, h: 500 }];
  const spot = randomSpot(AREA, taken, BOX, seeded(3));
  assert.ok(Number.isFinite(spot.x) && Number.isFinite(spot.y));
  const tiny = { left: 0, top: 0, width: 100, height: 100 };               // smaller than the box itself
  assert.deepEqual(randomSpot(tiny, [], BOX, seeded(1)), { x: EDGE, y: EDGE });
});

test("fixed placements stack along an edge without overlapping", () => {
  for (const placement of ["bottom", "left", "right"]) {
    const taken = [];
    for (let i = 0; i < 4; i++) {
      const spot = edgeSpot(AREA, taken, BOX, placement);
      taken.push({ ...spot, ...BOX });
    }
    taken.forEach((a, i) => { assert.ok(inside(a), `${placement}: widget ${i} left the area`); taken.slice(i + 1).forEach((b) => assert.ok(!touch(a, b), `${placement}: overlap`)); });
  }
  const bottom = edgeSpot(AREA, [], BOX, "bottom");
  assert.ok(Math.abs(bottom.x + BOX.w / 2 - (AREA.left + AREA.width / 2)) < 2);   // the first one is centred
  assert.equal(edgeSpot(AREA, [], BOX, "left").x, AREA.left + EDGE);
  assert.equal(edgeSpot(AREA, [], BOX, "right").x, AREA.left + AREA.width - BOX.w - EDGE);
});

test("pickSpot follows the player's placement setting", () => {
  assert.deepEqual(pickSpot(AREA, [], BOX, "left"), edgeSpot(AREA, [], BOX, "left"));
  assert.deepEqual(pickSpot(AREA, [], BOX, "random", seeded(5)), randomSpot(AREA, [], BOX, seeded(5)));
});

test("a spot is pulled back inside when the area shrinks (a phone turned, the keyboard opened)", () => {
  const smaller = { left: 0, top: 0, width: 300, height: 260 };
  const spot = clampSpot(smaller, { x: 900, y: 700 }, BOX);
  assert.deepEqual(spot, { x: 300 - BOX.w - EDGE, y: 260 - BOX.h - EDGE });
});

test("a crowded screen shrinks the newest widget instead of stacking it on another", () => {
  const boxAt = (k) => ({ w: Math.round(BOX.w * k), h: Math.round(BOX.h * k) });
  let shrunk = 0;
  for (let seed = 1; seed <= 400; seed++) {
    const rng = seeded(seed), taken = [];
    for (let i = 0; i < 6; i++) {
      const spot = pickSpotFit(AREA, taken, boxAt, "random", rng);
      if (spot.k < 1) shrunk++;
      taken.push(spot);
    }
    taken.forEach((a, i) => { assert.ok(inside(a), `seed ${seed}: widget ${i} left the area`); taken.slice(i + 1).forEach((b, j) => assert.ok(!touch(a, b), `seed ${seed}: widgets ${i} and ${i + 1 + j} overlap`)); });
  }
  assert.ok(shrunk > 0);                                  // six widgets do not always fit at full size
  assert.equal(pickSpotFit(AREA, [], boxAt, "random", seeded(2)).k, 1);   // but a lone one is never shrunk
});

test("when widgets cannot be placed one by one, laying them all out again always fits a phone", () => {
  const phone = { left: 8, top: 190, width: 359, height: 330 };
  const boxAt = (k) => ({ w: Math.round(130 * k), h: Math.round(176 * k) });
  for (let n = 1; n <= 6; n++) {
    const packed = packAll(phone, Array.from({ length: n }, () => boxAt));
    assert.ok(packed, `${n} widgets`);
    assert.ok(!anyOverlap(packed), `${n} widgets overlap`);
    packed.forEach((b) => assert.ok(b.x >= phone.left + EDGE - 1 && b.x + b.w <= phone.left + phone.width - EDGE + 1 && b.y + b.h <= phone.top + phone.height - EDGE + 1));
  }
  assert.equal(packAll(phone, Array.from({ length: 30 }, () => boxAt)), null);       // nobody can lay out thirty
  assert.equal(anyOverlap([{ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 5, w: 10, h: 10 }]), true);
});
