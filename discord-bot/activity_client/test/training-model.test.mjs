import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_CONFIG, PRESETS, accuracy, averageMs, beats, emptyStats, gapMs, mergeBest, nextSpec, record, sanitizeConfig, scaleFrame } from "../src/training-model.js";
import { practiceFrame, judge } from "../src/practice.js";

const seeded = (seed) => () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };

test("the configuration keeps what fits and falls back to the defaults for the rest", () => {
  assert.deepEqual(sanitizeConfig(null), DEFAULT_CONFIG);
  const c = sanitizeConfig({ kinds: ["combo", "nope", "single"], difficulties: [], count: 7, gapMin: 9, gapMax: 2, simultaneous: 9, speed: "fast", comboLength: 1, suddenDeath: "yes" });
  assert.deepEqual(c.kinds, ["single", "combo"]);                      // known values, in the usual order
  assert.deepEqual(c.difficulties, DEFAULT_CONFIG.difficulties);       // an empty list is never accepted
  assert.equal(c.count, 7); assert.equal(sanitizeConfig({ count: 9999 }).count, DEFAULT_CONFIG.count); assert.equal(sanitizeConfig({ count: 2.5 }).count, DEFAULT_CONFIG.count);
  assert.equal(c.gapMin, 9); assert.equal(c.gapMax, 9);                // the maximum is never below the minimum
  assert.equal(c.simultaneous, 3); assert.equal(c.comboLength, 2);
  assert.equal(c.speed, 100); assert.equal(c.suddenDeath, false);
  for (const [, , preset] of PRESETS) assert.deepEqual(sanitizeConfig(preset), { ...DEFAULT_CONFIG, ...preset });   // every preset is valid as it is
});

test("the next QTE only uses the chosen kinds and difficulties, and avoids repeating the kind", () => {
  const config = sanitizeConfig({ kinds: ["single", "direction", "combo", "bf_chain"], difficulties: ["hard", "impossible"], comboLength: 4 });
  const rng = seeded(7);
  let last = null;
  const seen = new Set();
  for (let i = 0; i < 200; i++) {
    const spec = nextSpec(config, rng, last);
    assert.ok(config.kinds.includes(spec.mode) && config.difficulties.includes(spec.difficulty));
    assert.notEqual(spec.mode, last);
    if (spec.mode === "combo") assert.equal(spec.extra.sequence.length, 4);
    if (spec.mode === "direction") assert.ok(["up", "down", "left", "right"].includes(spec.extra.arrow));
    seen.add(spec.mode); last = spec.mode;
  }
  assert.equal(seen.size, 4);
  assert.equal(nextSpec(sanitizeConfig({ kinds: ["group"] }), rng, "group").mode, "group");      // a single kind can repeat
});

test("the pause between QTEs stays inside the chosen range", () => {
  const c = sanitizeConfig({ gapMin: 1, gapMax: 2 });
  const rng = seeded(3);
  for (let i = 0; i < 100; i++) { const g = gapMs(c, rng); assert.ok(g >= 1000 && g <= 2000); }
});

test("speed shortens every window together, and slower lengthens them", () => {
  const rules = { times: { medium: { evade: 4, parry: [3, 5], perfect: 4, timeout: 5 } }, bfWindow: 0.2 };
  const base = practiceFrame("a", "medium", rules, "single");
  const fast = scaleFrame(base, 200);
  assert.equal(fast.timeout, 2.5); assert.deepEqual(fast.windows.evade, [0, 2]); assert.deepEqual(fast.windows.parry, [1.5, 2.5]);
  assert.equal(scaleFrame(base, 100), base);
  const combo = scaleFrame(practiceFrame("b", "medium", rules, "combo"), 50);
  assert.equal(combo.combo.limits[0], base.windows.evade[1] * 2 + 1);
});

test("a Black Flash chain frame is judged: too early breaks it, inside the window counts, the band is a Black Flash", () => {
  const frame = practiceFrame("c", "medium", null, "bf_chain", { chain: 2, from: 1, len: 1.2 });
  assert.equal(frame.chain, 2); assert.deepEqual(frame.commands, ["parry"]);
  assert.equal(judge(frame, "parry", 0.4).ok, false);
  assert.match(judge(frame, "parry", 0.4).label, /pronto/i);
  assert.equal(judge(frame, "parry", 1.1).ok, true);
  assert.equal(judge(frame, "parry", 1.6).bf, true);
  assert.equal(judge(frame, "parry", 2.6).ok, false);
  assert.equal(judge(frame, "evade", 1.5).ok, false);
});

test("the session counts hits, misses, streaks, reaction times and the breakdowns", () => {
  let s = emptyStats();
  const a = s;
  s = record(s, { ok: true, ms: 800, mode: "single", difficulty: "medium" });
  s = record(s, { ok: true, bf: true, ms: 600, mode: "single", difficulty: "hard" });
  s = record(s, { ok: false, timedOut: true, mode: "combo", difficulty: "hard" });
  s = record(s, { ok: true, ms: 1000, mode: "group", difficulty: "medium" });
  assert.equal(a.total, 0);                                            // the old stats are untouched
  assert.equal(s.total, 4); assert.equal(s.ok, 3); assert.equal(s.fail, 1); assert.equal(s.timeouts, 1);
  assert.equal(s.streak, 1); assert.equal(s.bestStreak, 2); assert.equal(s.bf, 1);
  assert.equal(averageMs(s), 800); assert.equal(s.bestMs, 600); assert.equal(accuracy(s), 0.75);
  assert.deepEqual(s.byKind.single, { n: 2, ok: 2 }); assert.deepEqual(s.byKind.combo, { n: 1, ok: 0 });
  assert.deepEqual(s.byDifficulty.hard, { n: 2, ok: 1 });
  assert.deepEqual(s.recent, [1, 1, 0, 1]);
});

test("records are only beaten by a session long enough to mean something", () => {
  let s = emptyStats();
  for (let i = 0; i < 4; i++) s = record(s, { ok: true, ms: 700, mode: "single", difficulty: "easy" });
  assert.deepEqual(beats(s, null), ["streak"]);                         // 4 in a row, but too short for accuracy and speed
  let long = emptyStats();
  for (let i = 0; i < 12; i++) long = record(long, { ok: i % 4 !== 3, ms: 900, mode: "single", difficulty: "easy" });
  const best = mergeBest(long, mergeBest(s, null));
  assert.equal(best.bestStreak, 4 > long.bestStreak ? 4 : long.bestStreak);
  assert.deepEqual(beats(long, best), []);                              // equal is not a record
  assert.deepEqual(beats(long, null).sort(), ["accuracy", "speed", "streak"]);
});

test("kinds that a person cannot do together are never open together; the rest still can", async () => {
  const { fitsWith, nextSpec: next } = await import("../src/training-model.js");
  assert.equal(fitsWith(["drag"], "mash"), false);          // two gestures
  assert.equal(fitsWith(["combo"], "drag"), false);         // a combo with a drag
  assert.equal(fitsWith(["mash"], "combo"), false);
  assert.equal(fitsWith(["drag"], "single"), true);         // a drag and a simple evade is fine
  assert.equal(fitsWith(["single", "single"], "single"), true);
  assert.equal(fitsWith([], "combo"), true);                 // alone, anything goes
  const config = sanitizeConfig({ kinds: ["drag", "mash", "combo"], simultaneous: 3 });
  assert.equal(next(config, () => 0.3, null, ["drag"]), null);      // nothing the player chose fits with the drag: wait
  assert.ok(next(config, () => 0.3, null, []));
  const chaos = PRESETS.find(([id]) => id === "chaos")[2];
  for (let seed = 1; seed < 60; seed++) {                   // whatever the chaos preset throws next, it fits with what is open
    let s = seed; const rng = () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296; };
    const open = ["single"];
    const spec = next(sanitizeConfig(chaos), rng, null, open);
    assert.ok(!spec || fitsWith(open, spec.mode));
  }
});
