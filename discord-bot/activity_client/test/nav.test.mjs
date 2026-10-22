import test from "node:test";
import assert from "node:assert/strict";
import { DESTINATIONS, navSection, searchDestinations } from "../src/nav.js";

test("the search finds places by name or by what people call them, without accents, best first", () => {
  assert.equal(searchDestinations("inventario")[0].id, "inventory");
  assert.equal(searchDestinations("objetos")[0].id, "inventory");                 // a word, not the name
  assert.equal(searchDestinations("latencia")[0].id, "latency");
  assert.equal(searchDestinations("LATÉNCIA")[0].id, "latency");                 // accents and case do not matter
  assert.equal(searchDestinations("ajus")[0].id, "settings");
  assert.deepEqual(searchDestinations("zzzz"), []);
});

test("game-master places are only offered to game masters", () => {
  assert.ok(!searchDestinations("jefe").some((d) => d.gm));
  assert.equal(searchDestinations("enemigos", { gm: true })[0].id, "gm-mobs");
  assert.equal(searchDestinations("", { gm: false }).length, DESTINATIONS.filter((d) => !d.gm).length);
});

test("every view belongs to one item of the bottom bar", () => {
  assert.equal(navSection("event"), "event");
  assert.equal(navSection("panel", "skills"), "panel");
  assert.equal(navSection("settings"), "more");
  assert.equal(navSection("gm", "boss"), "gm");
});
