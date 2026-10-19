import test from "node:test";
import assert from "node:assert/strict";
import { makeEntry, phaseAt, canPress, byUrgency, deadlineOf, verdictOf, roleOf, elapsedSeconds } from "../src/qte-model.js";

const WIN = { evade: [0, 4.5], parry: [3.0, 5.0], bf: [3.8, 4.2] };
const base = (extra = {}) => ({
  id: "1", mode: "single", difficulty: "medium", target: { id: "7", name: "Ana" }, participants: [], tGo: 0, timeout: 5.0,
  windows: WIN, commands: ["evade", "parry", "save", "adapt"], ...extra,
});
const mine = (q, youId = "7") => makeEntry(q, { arrival: 0, net: 0, youId });

test("a single QTE is EVADE until the parry window opens, then PARRY, then late", () => {
  const e = mine(base());
  assert.equal(phaseAt(e, 0.0).kind, "evade");
  assert.equal(phaseAt(e, 2.99).kind, "evade");
  assert.deepEqual([phaseAt(e, 1).from, phaseAt(e, 1).to], [0, 3.0]);              // the evade button lasts until the parry opens
  const p = phaseAt(e, 3.0);
  assert.equal(p.kind, "parry");
  assert.deepEqual([p.from, p.to], [3.0, 5.0]);
  assert.ok(p.bf[0] > 0.39 && p.bf[1] < 0.61);                                       // the Black Flash band sits in the middle of the parry window
  assert.equal(phaseAt(e, 5.01).kind, "late");
});

test("the timeline starts when the bot started the QTE, not when the frame arrived", () => {
  const e = makeEntry(base(), { arrival: 1000, net: 120, youId: "7" });
  assert.equal(e.start, 880);
  assert.equal(elapsedSeconds(e, 1000), 0.12);
});

test("a QTE that was already running when the frame was sent starts that much earlier", () => {
  const e = makeEntry(base(), { arrival: 5000, net: 50, ago: 3.0, youId: "7" });
  assert.equal(e.start, 5000 - 50 - 3000);
  assert.equal(phaseAt(e, elapsedSeconds(e, 5000)).kind, "parry");                      // 3.05 s in: the parry window (from 3.0 s) is open
});

test("evade is still allowed while the parry window is open, until the evade window closes", () => {
  const e = mine(base());
  assert.equal(canPress(e, "evade", 3.5), true);
  assert.equal(canPress(e, "evade", 4.6), false);        // evade window over: the bot would call it too slow
  assert.equal(canPress(e, "parry", 3.5), true);
  assert.equal(canPress(e, "parry", 2.0), false);        // too early: the bot would fail it
  assert.equal(canPress(e, "parry", 5.5), false);
});

test("a parry on cooldown cannot be pressed, and a pressed QTE takes no second answer", () => {
  const e = mine(base());
  assert.equal(canPress(e, "parry", 3.5, { parryCooldown: 12 }), false);
  assert.equal(canPress({ ...e, pressed: true }, "evade", 1), false);
  assert.equal(canPress(e, "evade", 1, { canWrite: false }), false);
});

test("a group QTE only offers evade (the bot refuses a parry there)", () => {
  const q = base({ mode: "group", target: null, participants: ["7", "8"], windows: { evade: [0, 4.5], bf: null }, commands: ["evade"] });
  const e = mine(q);
  assert.equal(e.role, "target");
  assert.equal(phaseAt(e, 1).kind, "evade");
  assert.equal(phaseAt(e, 4.0).kind, "evade");
  assert.equal(phaseAt(e, 4.6).kind, "late");
  assert.equal(canPress(e, "parry", 3.5), false);
  assert.equal(roleOf(q, "99"), null);                 // not one of the participants: nothing to do
});

test("somebody else's QTE can be saved until the evade window closes", () => {
  const e = makeEntry(base({ target: { id: "9", name: "Luis" } }), { arrival: 0, youId: "7" });
  assert.equal(e.role, "rescuer");
  assert.equal(phaseAt(e, 2).kind, "save");
  assert.equal(canPress(e, "save", 2, { saves: { left: 1 } }), true);
  assert.equal(canPress(e, "save", 2, { saves: { left: 0 } }), false);   // no saves left this minute
  assert.equal(canPress(e, "save", 4.6, { saves: { left: 2 } }), false); // late: a failed save hurts the saver
});

test("a fake QTE shows nothing to anybody", () => {
  const q = base({ mode: "fake", target: null, windows: null, commands: [] });
  assert.equal(roleOf(q, "7"), null);
});

test("a combo shows the current step's button until that step's limit", () => {
  const q = base({ mode: "combo", windows: null, timeout: 15, commands: ["evade", "parry"], combo: { length: 3, index: 0, step: "parry", limits: [5, 10, 15] } });
  const e = mine(q);
  const p = phaseAt(e, 1);
  assert.deepEqual([p.kind, p.cmd, p.to], ["combo", "parry", 5]);
  assert.equal(canPress(e, "parry", 1), true);
  assert.equal(canPress(e, "evade", 1), false);          // the wrong action breaks the combo: it is never offered
  const next = { ...e, step: { cmd: "evade", index: 1, from: 1.2 } };
  const n = phaseAt(next, 2);
  assert.deepEqual([n.cmd, n.from, n.to], ["evade", 1.2, 10]);
  assert.equal(canPress({ ...next, busy: true }, "evade", 2), false);   // waiting for the verdict of the last step
});

test("a direction QTE accepts any arrow until its window closes", () => {
  const q = base({ mode: "direction", windows: { evade: [0, 4.0], bf: null }, commands: ["up", "down", "left", "right"], arrow: "⬆️", timeout: 4 });
  const e = mine(q);
  assert.equal(phaseAt(e, 1).kind, "arrows");
  assert.equal(canPress(e, "left", 1), true);
  assert.equal(canPress(e, "evade", 1), false);
  assert.equal(canPress(e, "left", 4.2), false);
});

test("a Black Flash chain waits for its parry window and then offers only the parry", () => {
  const q = base({ mode: "bf_chain", windows: { parry: [0.8, 1.7], bf: [1.1, 1.4] }, commands: ["parry"], timeout: 3, chain: 2 });
  const e = mine(q);
  assert.equal(phaseAt(e, 0.3).kind, "wait");
  assert.equal(canPress(e, "parry", 0.3), false);        // pressing early would end the chain
  assert.equal(phaseAt(e, 1.0).kind, "bf");
  assert.equal(canPress(e, "parry", 1.0), true);
  assert.equal(phaseAt(e, 1.8).kind, "late");
});

test("when the evade window ends before the parry window opens there is a gap with nothing to press", () => {
  const q = base({ windows: { evade: [0, 2.0], parry: [3.0, 5.0], bf: null } });
  const e = mine(q);
  assert.equal(phaseAt(e, 1.9).kind, "evade");
  assert.equal(phaseAt(e, 2.5).kind, "wait");
  assert.equal(canPress(e, "evade", 2.5), false);
  assert.equal(phaseAt(e, 3.1).kind, "parry");
});

test("the most urgent QTE comes first, and finished ones go last", () => {
  const a = mine(base({ id: "a", timeout: 6.75 }));
  const b = { ...mine(base({ id: "b", timeout: 3.5 })) };
  const c = { ...mine(base({ id: "c", timeout: 2.0 })), pressed: true };
  assert.deepEqual(byUrgency([a, b, c], 0).map((e) => e.id), ["b", "a", "c"]);
  assert.equal(deadlineOf(a), 6.75);
});

test("verdicts name what happened", () => {
  const e = { ...mine(base()), pressedCmd: "parry" };
  assert.equal(verdictOf(e, { ok: true, ms: 4000 }).label, "¡Parry perfecto!");
  assert.equal(verdictOf(e, { ok: true, ms: 3200 }).label, "¡Parry!");
  assert.equal(verdictOf(e, { ok: true, ms: 4000, bf: true }).label, "¡Black Flash!");
  assert.equal(verdictOf({ ...e, pressedCmd: "evade" }, { ok: true, ms: 900 }).label, "¡Esquivado!");
  assert.equal(verdictOf(e, { ok: false, ms: 1200 }).ok, false);
  assert.equal(verdictOf(e, { ok: null }).ok, null);
});
