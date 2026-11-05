import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SyncEstimator, qualityOf, deviceLag, tapSpread } from "../src/clock.js";
import { practiceFrame, judge } from "../src/practice.js";
import { sanitizePrefs, DEFAULT_PREFS } from "../src/prefs.js";

test("the typical delay is the median, the jitter is how far samples stray from it", () => {
  const s = new SyncEstimator();
  [40, 42, 38, 300, 41].forEach((r) => s.add(r, 0));         // one spike must not drag the typical value
  assert.equal(s.median, 41);
  assert.equal(s.min, 38);
  assert.ok(s.jitter > 50 && s.jitter < 60);                  // (1+1+3+259+0)/5 = 52.8
  assert.equal(new SyncEstimator().median, null);
});

test("the clock offset is taken from the quickest round trips", () => {
  const s = new SyncEstimator();
  s.add(300, 500); s.add(30, 10); s.add(32, 12); s.add(35, 8); s.add(400, -900);
  assert.equal(s.offset, 10);
});

test("connection quality follows the typical round trip and the lost pings", () => {
  assert.equal(qualityOf(30), "great");
  assert.equal(qualityOf(120), "good");
  assert.equal(qualityOf(250), "fair");
  assert.equal(qualityOf(400), "poor");
  assert.equal(qualityOf(40, 0.3), "poor");
  assert.equal(qualityOf(40, 0.1), "fair");
  assert.equal(qualityOf(null), "off");
});

test("a device that taps late has lag; one that taps a little early has none", () => {
  assert.equal(deviceLag([-30, -30, -31, -29, -30, -30]), 0);        // normal anticipation
  assert.equal(deviceLag([20, 25, 22, 30, 18, 24]), 53);             // ~50 ms late: a slow screen
  assert.equal(deviceLag([200, 205, 210, 190, 202]), 150);           // capped
  assert.equal(deviceLag([5, 7]), null);                             // too few taps to say
  assert.equal(deviceLag([20, 25, 22, 300, 18, 24, -250]), 52);      // a missed beat is not lag
  assert.equal(tapSpread([10, 10, 10]), 0);
});

test("practice QTEs use the bot's real windows", () => {
  const rules = { times: { medium: { evade: 4.5, parry: [3.0, 5.0], timeout: 5.0 } }, bfWindow: 0.2 };
  const q = practiceFrame("p1", "medium", rules);
  assert.deepEqual(q.windows.evade, [0, 4.5]);
  assert.deepEqual(q.windows.parry, [3, 5]);
  assert.deepEqual(q.windows.bf, [3.8, 4.2]);
  assert.equal(q.timeout, 5.0);
  assert.deepEqual(practiceFrame("g", "medium", rules, "group").commands, ["evade"]);
});

test("practice verdicts follow the bot's rules", () => {
  const q = practiceFrame("p1", "medium", { times: { medium: { evade: 4.5, parry: [3.0, 5.0], timeout: 5.0 } }, bfWindow: 0.2 });
  assert.equal(judge(q, "evade", 1.0).ok, true);
  assert.equal(judge(q, "evade", 4.6).ok, false);
  assert.equal(judge(q, "parry", 2.0).label, "Demasiado pronto");
  assert.equal(judge(q, "parry", 3.3).label, "¡Parry!");
  assert.equal(judge(q, "parry", 4.0).bf, true);
  assert.equal(judge(q, "parry", 5.2).ok, false);
});

test("practice direction and combo", () => {
  const d = practiceFrame("d", "medium", null, "direction", { arrow: "up" });
  assert.equal(judge(d, "down", 1).ok, true);          // the opposite of the arrow shown
  assert.equal(judge(d, "up", 1).ok, false);
  const c = practiceFrame("c", "medium", null, "combo", { sequence: ["evade", "parry"] });
  assert.deepEqual([judge(c, "evade", 1, { index: 0 }).ok, judge(c, "evade", 1, { index: 0 }).done], [true, false]);
  assert.equal(judge(c, "evade", 1, { index: 1 }).ok, false);          // the step asked for a parry
  assert.equal(judge(c, "parry", 1, { index: 1 }).done, true);
});

test("settings are cleaned the same way the server cleans them", () => {
  assert.deepEqual(sanitizePrefs(null), DEFAULT_PREFS);
  // the very same cases are checked against the server's rules in tests/test_activity_settings.py
  const cases = JSON.parse(readFileSync(new URL("./prefs-cases.json", import.meta.url), "utf8"));
  for (const { raw, expected } of cases) assert.deepEqual(sanitizePrefs(raw), expected, JSON.stringify(raw));
  const out = sanitizePrefs({ theme: "oled", textScale: 500, buttonScale: "90", volume: -5, buttonPlacement: "up", sound: 0, nonsense: 1, density: "spacious" });
  assert.equal(out.theme, "oled");
  assert.equal(out.textScale, 140);                    // clamped
  assert.equal(out.buttonScale, 100);                  // text is not a number: the default
  assert.equal(out.volume, 0);
  assert.equal(out.buttonPlacement, "random");         // not a choice: the default
  assert.equal(out.sound, false);
  assert.equal(out.density, "spacious");
  assert.equal("nonsense" in out, false);
});
