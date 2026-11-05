import { test } from "node:test";
import assert from "node:assert/strict";
import { calendarSays, dayCrowd, dayKey, moveRange, monthGrid, offsetLabel, rangeLabel, weekdayOf, zoneLabel, zoneOffset } from "../src/agenda-model.js";

test("time zones: offsets, labels and dates", () => {
  assert.equal(zoneOffset("UTC"), 0);
  assert.equal(zoneOffset("Europe/Madrid", new Date(Date.UTC(2026, 0, 10))), 60);
  assert.equal(zoneOffset("Europe/Madrid", new Date(Date.UTC(2026, 6, 10))), 120);
  assert.equal(zoneOffset("America/Mexico_City", new Date(Date.UTC(2026, 6, 10))), -360);
  assert.equal(zoneOffset("Asia/Kolkata", new Date(Date.UTC(2026, 6, 10))), 330);
  assert.equal(offsetLabel(-360), "UTC−6");
  assert.equal(offsetLabel(330), "UTC+5:30");
  assert.equal(zoneLabel("America/Mexico_City", -360), "Mexico City · UTC−6");
  const at = Date.UTC(2026, 10, 15, 2, 0);                   // 02:00 UTC on the 15th: still the 14th in Mexico
  assert.equal(dayKey(at, 60), "2026-11-15");
  assert.equal(dayKey(at, -360), "2026-11-14");
});

test("a month is six weeks from a Monday", () => {
  const g = monthGrid(2026, 10);                           // November 2026 starts on a Sunday
  assert.equal(g.length, 42);
  assert.equal(g[0].key, "2026-10-26");
  assert.equal(g[6].key, "2026-11-01");
  assert.ok(g[6].inMonth && !g[0].inMonth);
  assert.equal(weekdayOf("2026-11-04"), 2);                // a Wednesday
});

test("hours move between clocks and say when the day changes", () => {
  assert.deepEqual(moveRange("18:00", "23:00", -360, 60), { from: "01:00", to: "06:00", days: 1 });
  assert.deepEqual(moveRange("01:00", "", 60, -360), { from: "18:00", to: "", days: -1 });
  assert.equal(rangeLabel(moveRange("", "", 0, 60)), "todo el día");
  assert.equal(rangeLabel(moveRange("18:00", "23:00", -360, 60)), "01:00–06:00 (día siguiente)");
  assert.equal(rangeLabel(moveRange("", "22:00", 60, 60)), "hasta las 22:00");
});

const week = (from, to, v = 2) => {                       // UTC hours [from, to) every day
  const w = new Array(168).fill(0);
  for (let d = 0; d < 7; d++) for (let h = from; h < to; h++) w[d * 24 + h] = v;
  return w.join("");
};

test("who can on a day: the marked date wins over the week", () => {
  const people = [
    { id: "1", name: "Mina", tz: "UTC", offset: 0, week: week(18, 22), days: { "2026-11-15": { a: "no", from: "", to: "", note: "boda" } } },
    { id: "2", name: "Luis", tz: "UTC", offset: 0, week: "", days: { "2026-11-15": { a: "yes", from: "18:00", to: "23:00", note: "en el móvil" } } },
    { id: "3", name: "Eva", tz: "UTC", offset: 0, week: week(10, 12, 1), days: {} },
    { id: "4", name: "Nadie", tz: "UTC", offset: 0, week: "", days: {} },
  ];
  const crowd = dayCrowd(people, "2026-11-15", 60);
  assert.deepEqual(crowd.map((c) => [c.name, c.a, c.byWeek]), [["Luis", "yes", false], ["Mina", "no", false], ["Eva", "maybe", true]]);
  assert.equal(rangeLabel(crowd[0].range), "19:00–00:00");
  assert.equal(crowd[0].note, "en el móvil");
  assert.equal(rangeLabel(crowd[2].range), "11:00–13:00");
  const other = dayCrowd(people, "2026-11-16", 0);
  assert.deepEqual(other.map((c) => c.name), ["Mina", "Eva"]);
});

test("a poll date checks each calendar in that person's own clock", () => {
  const people = [
    { id: "1", name: "Mina", tz: "America/Mexico_City", offset: -360, days: { "2026-11-14": { a: "yes", from: "18:00", to: "20:00", note: "" } } },
    { id: "2", name: "Luis", tz: "Europe/Madrid", offset: 60, days: { "2026-11-15": { a: "no", from: "", to: "", note: "viaje" } } },
  ];
  const at = Date.UTC(2026, 10, 15, 2, 0);                 // 20:00 in Mexico (14th), 03:00 in Madrid (15th)
  const says = calendarSays(people, at);
  assert.deepEqual(says.map((s) => [s.name, s.a, s.outside]), [["Mina", "yes", true], ["Luis", "no", false]]);
  assert.equal(calendarSays(people, Date.UTC(2026, 10, 15, 1, 0))[0].outside, false);   // 19:00 in Mexico
});
