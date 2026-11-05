import test from "node:test";
import assert from "node:assert/strict";
import { buildEffect, chartPoints, duration, effectLabel, num, parseEffect, plural, rarityOf, readable, skillStatus, tiersOf } from "../src/panel/format.js";

test("durations read like a person would say them", () => {
  assert.equal(duration(0), "0 s");
  assert.equal(duration(45), "45 s");
  assert.equal(duration(60), "1 min");
  assert.equal(duration(200), "3 min 20 s");
  assert.equal(duration(3600), "1 h");
  assert.equal(duration(3900), "1 h 5 min");
  assert.equal(duration(-5), "0 s");
  assert.equal(duration("x"), "0 s");
});

test("numbers use the decimal comma and drop useless zeros", () => {
  assert.equal(num(0.2), "0,2");
  assert.equal(num(10), "10");
  assert.equal(num(2.5), "2,5");
  assert.equal(num(0.125), "0,13");
  assert.equal(plural(1, "punto", "puntos"), "1 punto");
  assert.equal(plural(3, "punto", "puntos"), "3 puntos");
});

test("an effect code is understood, shown in Spanish and built back the same", () => {
  assert.deepEqual(parseEffect("damage:50"), { kind: "damage", a: 50 });
  assert.deepEqual(parseEffect(" HEAL:30 "), { kind: "heal", a: 30 });
  assert.deepEqual(parseEffect("stun"), { kind: "stun" });
  assert.deepEqual(parseEffect("buff:attack:0.2:30"), { kind: "buff", name: "attack", a: 0.2, b: 30 });
  assert.deepEqual(parseEffect("buff:attack"), { kind: "buff", name: "attack", a: 0.1, b: 30 });
  assert.deepEqual(parseEffect("lluvia de fuego"), { kind: "custom", text: "lluvia de fuego" });
  assert.equal(effectLabel("damage:50"), "Daño 50");
  assert.equal(effectLabel("heal:30"), "Curación 30");
  assert.equal(effectLabel("stun"), "Aturde al jefe");
  assert.equal(effectLabel("buff:attack:0.2:30"), "Mejora (ataque): 0,2 durante 30 s");
  assert.equal(effectLabel("buff:speed:10:90"), "Mejora (speed): 10 durante 1 min 30 s");
  assert.equal(effectLabel("buff:damage_boost:20:30"), "Mejora (daño): 20 durante 30 s");
  assert.equal(effectLabel(""), "—");
  for (const code of ["damage:50", "heal:30", "stun", "buff:attack:0.2:30"]) assert.equal(buildEffect(parseEffect(code)), code);
  assert.equal(buildEffect({ kind: "damage", a: -5 }), "damage:0");
  assert.equal(buildEffect({ kind: "damage", a: 12.7 }), "damage:13");
  assert.equal(buildEffect({ kind: "buff", name: "At Ack!", a: 1, b: 5 }), "buff:atack:1:5");
  assert.equal(buildEffect({ kind: "custom", text: "  algo  " }), "algo");
});

test("rarities have a name and a colour, even unknown ones", () => {
  assert.equal(rarityOf("legendary").label, "Legendario");
  assert.equal(rarityOf("legendary").color, "#fb923c");
  assert.equal(rarityOf("bizarre").label, "Bizarre");
  assert.equal(rarityOf(undefined).label, "Común");
});

test("the response-time chart needs two answers and puts faster ones higher", () => {
  assert.deepEqual(chartPoints([1], 100, 40).points, []);
  const { points, min, max } = chartPoints([2, 1, 3, Number.NaN], 100, 40, 4);
  assert.equal(points.length, 3);
  assert.equal(min, 1); assert.equal(max, 3);
  assert.deepEqual(points[0], [4, 20]);      // 2 s: halfway
  assert.deepEqual(points[1], [50, 4]);      // 1 s: the top
  assert.deepEqual(points[2], [96, 36]);     // 3 s: the bottom
});

test("skills are laid out by tier and say what is missing", () => {
  const skills = [{ id: "a", tier: 2 }, { id: "b", tier: 1 }, { id: "c", tier: 2 }];
  assert.deepEqual(tiersOf(skills).map((row) => row.map((s) => s.id)), [["b"], ["a", "c"]]);
  assert.equal(skillStatus({ state: "maxed" }, 3), "Al máximo");
  assert.equal(skillStatus({ state: "locked", needs: [{ name: "X", met: false }, { name: "Y", met: true }] }, 3), "Necesitas: X");
  assert.equal(skillStatus({ state: "poor", cost: 5 }, 3), "Cuesta 5; te faltan 2");
  assert.equal(skillStatus({ state: "available", cost: 2 }, 3), "Aprender · cuesta 2");
});

test("a nearly black colour from the data is swapped for one that can be seen", () => {
  assert.equal(readable("#1a1a2e", "#fb923c"), "#fb923c");
  assert.equal(readable("#000", "#fb923c"), "#fb923c");
  assert.equal(readable("#4169E1", "#fb923c"), "#4169e1");
  assert.equal(readable("#fff", "#fb923c"), "#ffffff");
  assert.equal(readable("red", "#fb923c"), "#fb923c");
  assert.equal(readable(undefined, "#fb923c"), "#fb923c");
});
