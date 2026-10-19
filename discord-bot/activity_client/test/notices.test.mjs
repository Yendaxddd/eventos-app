import test from "node:test";
import assert from "node:assert/strict";
import { describeNotice } from "../src/notices.js";

test("what the button already shows the player is not said twice", () => {
  for (const kind of ["evade_ok", "evade_slow", "parry_ok", "parry_mistimed", "save_ok", "save_slow", "direction_ok", "direction_slow", "combo_step", "nonsense"]) {
    assert.equal(describeNotice(kind, { ms: 300 }), null, kind);
  }
});

test("the notices the screen does word come out in Spanish with their numbers", () => {
  assert.deepEqual(describeNotice("timeout"), { tone: "bad", text: "No respondiste a tiempo." });
  assert.equal(describeNotice("parry_cooldown", { seconds: 12 }).text, "El parry se está recargando: 12 s.");
  assert.equal(describeNotice("mirror_heal", { old: 40, new: 55 }).text, "Fragmento de espejo: +15 PV (40 → 55)");
  assert.equal(describeNotice("group_done", { ok: 3, total: 3 }).tone, "ok");
  assert.equal(describeNotice("group_done", { ok: 1, total: 3 }).text, "QTE grupal: lo lograron 1 de 3.");
  assert.match(describeNotice("combo_broken", { why: "wrong", expected: "parry" }).text, /tocaba «parry»/);
  assert.match(describeNotice("combo_broken", { why: "slow" }).text, /demasiado lento/);
  assert.match(describeNotice("direction_wrong", { shown: "⬆️", needed: "⬇️" }).text, /abajo.*opuesta a arriba/);
  const bf = describeNotice("black_flash", { damage: 50, chain: 2, mirror: true });
  assert.equal(bf.tone, "bf");
  assert.equal(bf.text, "¡Black Flash! 50 de daño · cadena 2/4 · Fragmento de espejo");
  assert.match(describeNotice("chain_end", { why: "noflash", cooldown: 10 }).text, /sin Black Flash.*recarga 10 s/);
  assert.equal(describeNotice("adapt_ok", { ms: 640, info: ["Espejo: 12 hard spins"] }).text, "Adaptado en 0.64 s · Espejo: 12 hard spins");
});

test("a malformed notice never throws", () => {
  assert.equal(describeNotice("direction_wrong", null).tone, "bad");
  assert.doesNotThrow(() => describeNotice("mirror_heal", undefined));
});
