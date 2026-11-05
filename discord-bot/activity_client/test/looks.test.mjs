import { test } from "node:test";
import assert from "node:assert/strict";
import { ARRANGEMENTS, STYLES, THEME_SWATCH, ACCENT_SWATCH, customSwatch, styleOf, swatchOf } from "../src/looks.js";
import { DEFAULT_PREFS, effectivePrefs, sanitizePrefs } from "../src/prefs.js";

test("every ready-made style is made of valid settings and is recognised again", () => {
  for (const s of STYLES) {
    const p = sanitizePrefs({ ...DEFAULT_PREFS, ...s.look });
    for (const [k, v] of Object.entries(s.look)) assert.equal(p[k], v, `${s.id}.${k}`);
    assert.equal(styleOf(p), s.id);
    assert.ok(THEME_SWATCH[s.look.theme] && ACCENT_SWATCH[s.look.accent], s.id);
  }
  assert.equal(new Set(STYLES.map((s) => s.id)).size, STYLES.length);
});

test("free colours draw a preview and never count as a ready-made style", () => {
  const sw = swatchOf({ theme: "custom", baseColor: "#203040", accent: "custom", accentColor: "#ff0088" });
  assert.equal(sw.bg, "#203040");
  assert.equal(sw.accent, "#ff0088");
  assert.equal(customSwatch("#f0f0f0").length, 6);
  assert.equal(styleOf({ ...DEFAULT_PREFS, theme: "custom" }), null);
});

test("the event's look wins only while the player follows it, and only for look settings", () => {
  const own = { ...DEFAULT_PREFS, theme: "light", textScale: 120 };
  const look = { theme: "ember", accent: "amber" };
  assert.equal(effectivePrefs({ ...own, followEvent: true }, look).theme, "ember");
  assert.equal(effectivePrefs({ ...own, followEvent: true }, look).textScale, 120);
  assert.equal(effectivePrefs({ ...own, followEvent: false }, look).theme, "light");
  assert.equal(effectivePrefs({ ...own, followEvent: true }, null).theme, "light");
});

test("every arrangement is a valid setting", () => {
  for (const a of ARRANGEMENTS) assert.equal(sanitizePrefs({ ...DEFAULT_PREFS, arrange: a.id }).arrange, a.id);
});
