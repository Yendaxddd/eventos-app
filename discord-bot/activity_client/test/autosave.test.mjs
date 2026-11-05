import test from "node:test";
import assert from "node:assert/strict";
import { Autosaver } from "../src/autosave.js";

// a clock the test moves by hand
function harness(options = {}) {
  let now = 0, next = 1;
  const timers = new Map();
  const saves = [], statuses = [];
  const state = { fail: false, hold: null };
  const saver = new Autosaver(async (value) => {
    saves.push(value);
    if (state.hold) await state.hold;
    if (state.fail) throw new Error("down");
    return true;
  }, {
    delay: 500, onStatus: (s, r) => statuses.push(r ? `${s}:${r}` : s), ...options,
    setTimer: (fn, ms) => { const id = next++; timers.set(id, { fn, at: now + ms }); return id; },
    clearTimer: (id) => timers.delete(id),
  });
  const advance = async (ms) => {
    now += ms;
    for (const [id, t] of [...timers]) if (t.at <= now) { timers.delete(id); t.fn(); }
    await new Promise((r) => setImmediate(r));
  };
  return { saver, saves, statuses, advance, state, timers };
}

test("a change is saved a moment after the person stops, and several quick changes make one save", async () => {
  const h = harness();
  h.saver.baseline({ a: 1 });
  h.saver.update({ a: 2 }); await h.advance(300);
  h.saver.update({ a: 3 }); await h.advance(300);
  assert.deepEqual(h.saves, []);                       // still being typed
  assert.equal(h.saver.status, "pending");
  await h.advance(300);
  assert.deepEqual(h.saves, [{ a: 3 }]);
  assert.equal(h.saver.status, "saved");
  assert.deepEqual(h.statuses, ["pending", "saving", "saved"]);
});

test("going back to what the server has cancels the save", async () => {
  const h = harness();
  h.saver.baseline({ a: 1 });
  h.saver.update({ a: 2 });
  h.saver.update({ a: 1 });
  await h.advance(1000);
  assert.deepEqual(h.saves, []);
  assert.equal(h.saver.status, "saved");
});

test("a change that cannot be saved yet says why, and is saved once it can", async () => {
  const h = harness({ check: (v) => (v.name ? "" : "Falta el nombre") });
  h.saver.baseline({ name: "x" });
  h.saver.update({ name: "" });
  assert.equal(h.saver.status, "invalid"); assert.equal(h.saver.reason, "Falta el nombre");
  await h.advance(1000);
  assert.deepEqual(h.saves, []);
  h.saver.update({ name: "y" }); await h.advance(600);
  assert.deepEqual(h.saves, [{ name: "y" }]); assert.equal(h.saver.status, "saved");
});

test("a failed save shows an error, keeps the change and tries again with the next one or with flush", async () => {
  const h = harness();
  h.saver.baseline({ a: 1 });
  h.state.fail = true;
  h.saver.update({ a: 2 }); await h.advance(600);
  assert.equal(h.saver.status, "error");
  h.state.fail = false;
  await h.saver.flush();
  assert.deepEqual(h.saves, [{ a: 2 }, { a: 2 }]); assert.equal(h.saver.status, "saved");
});

test("what changes while a save is in flight is saved right after it", async () => {
  const h = harness();
  h.saver.baseline({ a: 1 });
  let release; h.state.hold = new Promise((r) => { release = r; });
  h.saver.update({ a: 2 }); await h.advance(600);
  assert.equal(h.saver.status, "saving");
  h.saver.update({ a: 3 });
  release(); h.state.hold = null; await h.advance(0);
  assert.equal(h.saver.status, "pending");
  await h.advance(600);
  assert.deepEqual(h.saves, [{ a: 2 }, { a: 3 }]); assert.equal(h.saver.status, "saved");
});

test("opening something else forgets what was pending for the old one", async () => {
  const h = harness();
  h.saver.baseline({ id: 1 });
  h.saver.update({ id: 1, x: 1 });
  h.saver.baseline({ id: 2 });
  await h.advance(1000);
  assert.deepEqual(h.saves, []); assert.equal(h.saver.status, "saved");
});
