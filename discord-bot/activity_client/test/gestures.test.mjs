import test from "node:test";
import assert from "node:assert/strict";
import { canPress, makeEntry, phaseAt, roleOf, verdictOf } from "../src/qte-model.js";
import { gestureParams, judge, judgeGesture, practiceFrame } from "../src/practice.js";

const seeded = (seed) => () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
const frameOf = (mode, extra = {}) => ({ id: "a1", mode, difficulty: "medium", target: { id: "u1", name: "Ana" }, participants: [], timeout: 2,
  windows: { evade: [0, 2] }, commands: ["gesture"], arena: mode === "flick" ? { dir: "left" } : mode === "drag" ? { from: [0.2, 0.5], to: [0.8, 0.5], tolerance: 0.1 } : { count: 5 }, ...extra });

test("a swipe, drag or tap QTE is live for its target until it times out, with one gesture as its answer", () => {
  for (const mode of ["flick", "drag", "mash"]) {
    const e = makeEntry(frameOf(mode), { arrival: 0, youId: "u1" });
    assert.equal(e.role, "target");
    assert.equal(phaseAt(e, 1).kind, mode); assert.equal(phaseAt(e, 1).cmd, "gesture");
    assert.ok(canPress(e, "gesture", 1, {})); assert.ok(!canPress(e, "evade", 1, {}));
    assert.equal(phaseAt(e, 2.5).state, "late");
    assert.equal(makeEntry(frameOf(mode), { arrival: 0, youId: "u2" }).role, null);              // not for somebody else
  }
});

test("a fake QTE looks like an evade to its target, and answering it is falling for it", () => {
  const fake = { id: "9", mode: "fake", difficulty: "hard", target: { id: "u1", name: "Ana" }, participants: [], timeout: 3, windows: { evade: [0, 3] }, commands: ["evade", "parry"] };
  const e = makeEntry(fake, { arrival: 0, youId: "u1" });
  assert.equal(roleOf(fake, "u1"), "target");
  assert.equal(phaseAt(e, 1).kind, "evade");
  assert.equal(verdictOf({ ...e, pressedCmd: "evade" }, { ok: false }).label, "¡Era falso!");
  assert.equal(judge(practiceFrame("p", "hard", null, "fake"), "evade", 0.5).ok, false);
});

test("the server's reasons for a failed gesture are said in Spanish", () => {
  const e = makeEntry(frameOf("flick"), { arrival: 0, youId: "u1" });
  assert.equal(verdictOf({ ...e, pressedCmd: "gesture" }, { ok: false, why: "wrong_dir", ms: 900 }).label, "Otra dirección");
  assert.equal(verdictOf({ ...e, pressedCmd: "gesture" }, { ok: true, ms: 900 }).label, "¡Deslizado!");
});

test("practice gestures are judged by what the screen measured", () => {
  const flick = frameOf("flick"), drag = frameOf("drag"), mash = frameOf("mash");
  assert.deepEqual(judgeGesture(flick, { dir: "left" }), { ok: true });
  assert.equal(judgeGesture(flick, { dir: "up" }).why, "wrong_dir");
  assert.ok(judgeGesture(drag, { x: 0.85, y: 0.52 }).ok);
  assert.equal(judgeGesture(drag, { x: 0.5, y: 0.5 }).why, "missed");
  assert.ok(judgeGesture(mash, { count: 5 }).ok); assert.equal(judgeGesture(mash, { count: 4 }).why, "short");
  assert.equal(judge(flick, "gesture", 3, { data: { dir: "left" } }).label, "Tarde");
});

test("practice frames of the new kinds carry what they ask for, and it changes with the difficulty", () => {
  const rng = seeded(4);
  const drag = practiceFrame("d", "impossible", null, "drag", { random: rng });
  assert.ok(drag.arena.from[0] >= 0 && drag.arena.to[0] <= 1 && drag.arena.tolerance === 0.07 && drag.timeout === 1.7);
  assert.equal(practiceFrame("m", "easy", null, "mash").arena.count, 4);
  assert.ok(["up", "down", "left", "right"].includes(gestureParams("flick", "hard", rng).dir));
});
