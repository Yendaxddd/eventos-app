import test from "node:test";
import assert from "node:assert/strict";
import { KINDS, PRESETS, compose, describe, effectSummary, freshPart, parse } from "../src/power-model.js";

test("the builder reads and writes the same effect language as the bot, old forms included", () => {
  assert.deepEqual(parse("damage:50"), [{ kind: "damage", amount: 50 }]);
  assert.deepEqual(parse("stun"), [{ kind: "stun", seconds: 3 }]);
  assert.deepEqual(parse("buff:damage_boost:0.2:30"), [{ kind: "buff_damage", amount: 20, seconds: 30 }]);     // a fraction is a percent
  assert.equal(parse("buff:attack:0.2:30"), null);                                                               // not something the bot does
  assert.equal(parse("borrar todo"), null);
  const parts = [freshPart("damage_all"), freshPart("shield_team"), freshPart("stun")];
  assert.equal(compose(parts), "damage_all:60;shield_team:30:12;stun:3");
  assert.deepEqual(parse(compose(parts)), parts);
  for (const preset of Object.values(PRESETS)) assert.ok(parse(preset), preset);
  for (const kind of Object.keys(KINDS)) assert.ok(parse(compose([freshPart(kind)])), kind);
});

test("what a power will do is said with the player's real multiplier and the cap", () => {
  const lines = describe(parse("damage:100;heal:20"), 1.5, 500);
  assert.match(lines[0], /150 de daño/);
  assert.match(lines[1], /20 PV/);
  assert.match(describe(parse("damage:1000"), 1, 500)[0], /500 de daño al jefe \(el máximo\)/);
  assert.equal(effectSummary("stun:4"), "El jefe queda aturdido 4 s (los mini enemigos también esperan)");
  assert.equal(effectSummary("algo raro"), "algo raro");
});
