import test from "node:test";
import assert from "node:assert/strict";
import { DraftMemory } from "../src/views/gm/draft.js";
import { parseNumber } from "../src/panel/format.js";

test("a number typed by a game master is read with a comma or a point, and an empty or broken field is null", () => {
  assert.equal(parseNumber("12"), 12);
  assert.equal(parseNumber(" 2,5 "), 2.5);
  assert.equal(parseNumber("0.25"), 0.25);
  assert.equal(parseNumber("-3"), -3);
  assert.equal(parseNumber(0), 0);
  for (const bad of ["", "   ", null, undefined, "abc", "1,2,3", "Infinity", "NaN"]) assert.equal(parseNumber(bad), null, String(bad));
});

test("a form follows the server until the person types, and then keeps their text", () => {
  const m = new DraftMemory({ v: "100" });
  assert.deepEqual(m.sync({ v: "120" }), { v: "120" });             // nobody typed: the new copy is shown
  assert.equal(m.sync({ v: "120" }), undefined);                    // the same copy again: nothing to do
  m.edit({ v: "150" });
  assert.equal(m.sync({ v: "130" }), undefined);                    // typed: the server's change does not overwrite it
  assert.deepEqual(m.now, { v: "150" });
});

test("typing while a save is on its way is not lost, and the form is not marked as clean", () => {
  const m = new DraftMemory({ v: "100" });
  const sent = m.edit({ v: "150" });                                // saved...
  m.edit({ v: "99999" });                                           // ...and the person types again before the answer
  assert.equal(m.saved(sent), false);                               // so this save does not clear what they typed
  assert.equal(m.dirty, true);
  assert.equal(m.sync({ v: "150" }), undefined);                    // the server confirms the first value: the draft stays
  assert.deepEqual(m.now, { v: "99999" });
});

test("after a save nothing else was typed: the form takes the server's tidied copy", () => {
  const m = new DraftMemory({ v: "100" });
  const sent = m.edit({ v: "150.0" });
  assert.equal(m.saved(sent), true);
  assert.equal(m.dirty, false);
  assert.deepEqual(m.sync({ v: "150" }), { v: "150" });             // "150.0" becomes what the server keeps
  assert.deepEqual(m.now, { v: "150" });
});

test("several edits in the same moment add up, and a function sees the latest values", () => {
  const m = new DraftMemory({ weights: { a: 1 }, mode: "x" });
  m.edit({ mode: "y" });
  const next = m.edit((old) => ({ weights: { ...old.weights, b: 2 } }));
  assert.deepEqual(next, { weights: { a: 1, b: 2 }, mode: "y" });
});

test("a render shows what the form holds unless it is being typed; reset goes back to the server", () => {
  const m = new DraftMemory({ v: "1" });
  m.render({ v: "1" });
  assert.deepEqual(m.now, { v: "1" });
  m.edit({ v: "2" });
  m.render({ v: "1" });                                              // an old render must not undo the typing
  assert.deepEqual(m.now, { v: "2" });
  assert.deepEqual(m.reset({ v: "9" }), { v: "9" });
  assert.equal(m.dirty, false);
  assert.equal(m.sync({ v: "9" }), undefined);
});
