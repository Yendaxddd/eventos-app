import { test } from "node:test";
import assert from "node:assert/strict";
import { HOURS, bestSlots, heat, leader, nextAt, tally, toLocal, toUtc, untilLabel } from "../src/agenda-model.js";

test("a week goes to the player's clock and back unchanged", () => {
  const local = new Array(HOURS).fill(0);
  local[4 * 24 + 20] = 2;            // Friday 20:00 local
  local[0] = 1;                      // Monday 00:00 local
  for (const shift of [-6, 0, 2, 5, 13]) {
    const utc = toUtc(local, shift);
    assert.equal(utc.length, HOURS);
    assert.deepEqual(toLocal(utc, shift), local, `shift ${shift}`);
  }
  // Friday 20:00 in Madrid summer (+2) is Friday 18:00 UTC; Monday 00:00 there is Sunday 22:00 UTC
  const utc = toUtc(local, 2);
  assert.equal(utc[4 * 24 + 18], "2");
  assert.equal(utc[6 * 24 + 22], "1");
});

test("the team's heat counts yes and maybe, and the best stretches do not overlap", () => {
  const w = (cells) => { const a = new Array(HOURS).fill(0); for (const [i, v] of cells) a[i] = v; return toUtc(a, 0); };
  const fri = (h) => 4 * 24 + h;
  const people = [
    { name: "Ana", week: w([[fri(20), 2], [fri(21), 2], [fri(22), 2]]) },
    { name: "Mina", week: w([[fri(20), 2], [fri(21), 2], [fri(22), 1]]) },
    { name: "Luis", week: w([[fri(21), 1]]) },
  ];
  const cells = heat(people, 0);
  assert.equal(cells[fri(21)].yes, 2);
  assert.equal(cells[fri(21)].maybe, 1);
  assert.deepEqual(cells[fri(22)].who, [["Ana", 2], ["Mina", 1]]);
  const slots = bestSlots(cells, { min: 2, max: 3 });
  assert.equal(slots[0].day, 4);
  assert.equal(slots[0].yes, 2);
  for (let i = 0; i < slots.length; i++) for (let j = i + 1; j < slots.length; j++) {
    const a = slots[i], b = slots[j];
    assert.ok(a.day !== b.day || a.to <= b.from || b.to <= a.from, "overlap");
  }
});

test("a poll's tally and its leader", () => {
  const poll = { options: [{ id: "a" }, { id: "b" }], votes: { 1: { a: "maybe", b: "yes" }, 2: { a: "yes", b: "yes" }, 3: { a: "no" } }, names: { 1: "Ana", 2: "Mina", 3: "Luis" } };
  const t = tally(poll);
  assert.deepEqual([t.a.yes, t.a.maybe, t.a.no], [1, 1, 1]);
  assert.deepEqual(t.b.who.yes, ["Ana", "Mina"]);
  assert.equal(leader(poll), "b");
  assert.equal(leader({ options: [{ id: "a" }], votes: {} }), null);
});

test("the next time a weekday and hour comes around is in the future and on that weekday", () => {
  const now = new Date(2026, 10, 4, 12, 0).getTime();          // Wednesday 4 Nov 2026, 12:00 local
  const fri = new Date(nextAt(4, 20, now));
  assert.equal(fri.getDay(), 5);
  assert.equal(fri.getHours(), 20);
  assert.equal(fri.getDate(), 6);
  const wedSoon = new Date(nextAt(2, 12, now));                  // right now → next week
  assert.equal(wedSoon.getDate(), 11);
  assert.equal(untilLabel(now + 3 * 3_600_000, now), "en 3 h");
  assert.equal(untilLabel(now - 2 * 86_400_000 - 1, now).startsWith("hace"), true);
});
