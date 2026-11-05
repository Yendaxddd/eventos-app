import { test } from "node:test";
import assert from "node:assert/strict";
import { isEditable, keyboardOpen } from "../src/viewport.js";

test("the keyboard counts as open only while something to write in has the focus and the visible height clearly shrank", () => {
  assert.equal(keyboardOpen({ focused: true, height: 500, tallest: 844 }), true);
  assert.equal(keyboardOpen({ focused: false, height: 500, tallest: 844 }), false);      // the page got smaller for another reason
  assert.equal(keyboardOpen({ focused: true, height: 820, tallest: 844 }), false);       // Discord's bar moving, not a keyboard
  assert.equal(keyboardOpen({ focused: true, height: 500, tallest: 0 }), false);
});

test("text boxes are places to write; buttons, checkboxes and sliders are not", () => {
  assert.equal(isEditable({ tagName: "TEXTAREA" }), true);
  assert.equal(isEditable({ tagName: "INPUT", type: "text" }), true);
  assert.equal(isEditable({ tagName: "INPUT", type: "number" }), true);
  assert.equal(isEditable({ tagName: "INPUT", type: "checkbox" }), false);
  assert.equal(isEditable({ tagName: "INPUT", type: "range" }), false);
  assert.equal(isEditable({ tagName: "BUTTON" }), false);
  assert.equal(isEditable({ tagName: "DIV", isContentEditable: true }), true);
  assert.equal(isEditable(null), false);
});
