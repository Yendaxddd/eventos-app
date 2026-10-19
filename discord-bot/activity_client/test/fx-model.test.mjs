import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_BINDING, DEFAULT_BY_TYPE, PRESETS, PRESET_IDS, expand, isEmpty, lengthOf, sanitizeBinding } from "../src/fx-model.js";

test("every preset has a label, a colour and valid pieces, and each type of power has a default", () => {
  for (const [id, p] of Object.entries(PRESETS)) {
    assert.ok(p.label && /^#[0-9a-f]{6}$/i.test(p.color) && p.hint, id);
    for (const part of p.parts) assert.ok(["flash", "shake", "vignette", "ring", "slash", "burst", "aura", "zoom"].includes(part.k) && part.ms > 0 && part.t >= 0, `${id}:${part.k}`);
  }
  for (const preset of Object.values(DEFAULT_BY_TYPE)) assert.ok(PRESET_IDS.includes(preset));
});

test("a binding keeps what fits and falls back for the rest", () => {
  assert.deepEqual(sanitizeBinding(null), DEFAULT_BINDING);
  const b = sanitizeBinding({ preset: "nope", color: "red", intensity: 999, speed: 1, delay: -5, banner: "  ¡Hola!\n ", name: "yes", sound: "zz", scope: "x", extra: 1 });
  assert.deepEqual(b, { ...DEFAULT_BINDING, intensity: 200, speed: 50, delay: 0, banner: "¡Hola!" });
});

test("the pieces follow the delay, the speed and the strength, and use the colour chosen", () => {
  const plain = expand({ preset: "explosion" });
  assert.equal(plain[0].t, 0); assert.equal(plain.find((p) => p.k === "flash").i, 0.8);
  const slow = expand({ preset: "explosion", speed: 50, delay: 500, intensity: 50, color: "#00ff00" });
  assert.equal(slow.find((p) => p.k === "ring").ms, 1400);
  assert.equal(slow.find((p) => p.k === "flash").t, 500); assert.equal(slow.find((p) => p.k === "flash").i, 0.4);
  assert.ok(slow.every((p) => p.c === "#00ff00"));
  assert.ok(lengthOf(slow) > lengthOf(plain));
  assert.deepEqual(expand({ preset: "carga" }).map((p) => p.t), [0, 0, 900, 900, 900]);
});

test("calm mode drops the shaking and zooming and softens the flashes", () => {
  const calm = expand({ preset: "dominio" }, {}, { calm: true });
  assert.ok(!calm.some((p) => p.k === "shake" || p.k === "zoom"));
  assert.ok(calm.find((p) => p.k === "flash").i < expand({ preset: "dominio" }).find((p) => p.k === "flash").i);
});

test("a banner shows the power's name or the text written, and a binding with nothing is empty", () => {
  assert.equal(expand({ preset: "ninguno", name: true }, { name: "Muerte súbita" })[0].text, "Muerte súbita");
  assert.equal(expand({ preset: "ninguno", name: true, banner: "¡Cuidado!" }, { name: "x" })[0].text, "¡Cuidado!");
  assert.deepEqual(expand({ preset: "ninguno" }), []);
  assert.equal(isEmpty(sanitizeBinding({ preset: "ninguno" })), true);
  assert.equal(isEmpty(sanitizeBinding({ preset: "ninguno", sound: "ab" })), false);
});

test("the client and the server agree on what a binding means", () => {
  const cases = JSON.parse(readFileSync(new URL("./fx-cases.json", import.meta.url), "utf8"));
  assert.ok(cases.length >= 5);
  for (const c of cases) assert.deepEqual(sanitizeBinding(c.raw), c.expected, JSON.stringify(c.raw));
});
