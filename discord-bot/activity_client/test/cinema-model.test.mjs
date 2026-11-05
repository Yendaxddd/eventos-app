import test from "node:test";
import assert from "node:assert/strict";
import { captionAt, crossed, durationOf, elapsedSeconds, imageAt, isOver, musicStepBefore, newStep, sceneAt, stepEnd } from "../src/cinema-model.js";

const cinema = {
  bg: "#000000", duration: 12,
  steps: [
    { type: "scene", at: 0, color: "#220033", image: "files/images/a.png", dim: 50 },
    { type: "audio", at: 0.5, mode: "music", sound: "m1", volume: 90 },
    { type: "text", at: 1, text: "Hola, viajeros.", duration: 3, effect: "type", speaker: "Rey" },
    { type: "effect", at: 3, effect: "shake", duration: 0.6 },
    { type: "text", at: 3.5, text: "Se acabó.", duration: 2, effect: "fade" },
    { type: "image", at: 6, image: "files/images/b.png", duration: 2, position: "center" },
    { type: "audio", at: 7, mode: "stop_music" },
    { type: "scene", at: 8, color: "#000000", image: null, dim: 0 },
  ],
};

test("the background is the latest scene step that has started", () => {
  const pick = ({ color, image, dim }) => ({ color, image, dim });
  assert.deepEqual(pick(sceneAt(cinema, 0)), { color: "#220033", image: "files/images/a.png", dim: 50 });
  assert.deepEqual(pick(sceneAt(cinema, 9)), { color: "#000000", image: null, dim: 0 });
  assert.deepEqual(pick(sceneAt({ bg: "#111111", steps: [] }, 5)), { color: "#111111", image: null, dim: 0 });
  assert.equal(sceneAt({ see: true, steps: [] }, 1).color, "transparent");         // see-through: the game shows behind
  const cross = sceneAt({ steps: [{ type: "scene", at: 0, color: "#111111" }, { type: "scene", at: 3, color: "#222222", transition: "fade" }] }, 3.4);
  assert.equal(cross.prev.color, "#111111");                                      // the first second of a fade: both, to blend them
  assert.equal(sceneAt({ steps: [{ type: "scene", at: 0, color: "#111111" }, { type: "scene", at: 3, color: "#222222" }] }, 4.5).prev, null);
});

test("a caption appears at its moment, is typed letter by letter, and the next one replaces it", () => {
  assert.equal(captionAt(cinema, 0.9), null);
  const early = captionAt(cinema, 1.25);
  assert.equal(early.step.speaker, "Rey");
  assert.equal(early.shown, 8);                                    // 0.25 s at 32 characters a second
  assert.equal(captionAt(cinema, 2.5).shown, "Hola, viajeros.".length);        // done typing: all of it stays until its time is over
  assert.equal(captionAt(cinema, 3.6).step.text, "Se acabó.");               // the later caption wins while both are showing
  assert.equal(captionAt(cinema, 3.6).shown, "Se acabó.".length);             // a fade caption is whole from the start
  assert.equal(captionAt(cinema, 5.6), null);
  assert.ok(Math.abs(captionAt(cinema, 4.5).left - 1) < 1e-9);
});

test("a picture shows for its time only", () => {
  assert.equal(imageAt(cinema, 5.9), null);
  assert.equal(imageAt(cinema, 6.5).step.image, "files/images/b.png");
  assert.equal(imageAt(cinema, 8), null);
});

test("sounds and effects start once, when the clock crosses their moment", () => {
  assert.deepEqual(crossed(cinema, 0, 1).map((s) => s.type), ["audio"]);
  assert.deepEqual(crossed(cinema, 0.5, 3).map((s) => s.type), ["effect"]);        // (from, to]: the one at exactly `from` already played
  assert.deepEqual(crossed(cinema, 0, 20).map((s) => s.type), ["audio", "effect", "audio"]);
  assert.deepEqual(crossed(cinema, 3, 3), []);
  assert.equal(crossed(cinema, 0, 20, ["scene"]).length, 1);                  // the scene at exactly 0 is not «after» 0
});

test("somebody who joins late knows which music was playing", () => {
  assert.equal(musicStepBefore(cinema, 0.2), null);
  assert.equal(musicStepBefore(cinema, 5).mode, "music");
  assert.equal(musicStepBefore(cinema, 7.5).mode, "stop_music");
});

test("the clock of a run counts from when the server started it, with the time the frame took to arrive and the time it has been here", () => {
  const run = { startedAt: 1000, now: 3000 };                                  // it began 2 s before the frame was sent
  assert.equal(elapsedSeconds(run, { arrival: 500, now: 500 }), 2);
  assert.equal(elapsedSeconds(run, { arrival: 500, now: 1500, transitMs: 100 }), 3.1);
  assert.equal(elapsedSeconds({ startedAt: 5000, now: 1000 }, { arrival: 0, now: 0 }), 0);       // never negative
  assert.equal(isOver(cinema, 11.9), false);
  assert.equal(isOver(cinema, 12), true);
});

test("the editor measures a script and starts new steps where the last one ends", () => {
  assert.equal(durationOf(cinema.steps), 9);                                   // the picture ends at 8, plus a second of air
  assert.equal(stepEnd({ at: 2, duration: 1.5 }), 3.5);
  assert.deepEqual(newStep("text", []), { type: "text", at: 0, speaker: "", text: "", duration: 4, effect: "type", color: "", size: "normal", avatar: "", side: "bottom" });
  assert.equal(newStep("audio", cinema.steps).at, 8);
  assert.equal(newStep("post", []).type, "post");
  assert.equal(newStep("effect", []).duration, 0.6);
});

import { LANES, draggedTo, laneOf, orderOf, rulerTicks, validate } from "../src/cinema-model.js";

test("every kind of step sits on one row of the timeline", () => {
  for (const type of ["text", "title", "audio", "image", "scene", "weather", "effect", "vfx", "post"]) assert.ok(LANES.some((l) => l[2].includes(type)), type);
  assert.equal(laneOf("vfx"), "fx"); assert.equal(laneOf("effect"), "fx"); assert.equal(laneOf("audio"), "sound");
});

test("a draft says what stops it from being saved, naming the step by its place in time", () => {
  const ok = { name: "Llegada", steps: [{ type: "text", at: 2, text: "Hola" }, { type: "audio", at: 0, mode: "play", sound: "ab" }] };
  assert.equal(validate(ok), "");
  assert.match(validate({ ...ok, name: "  " }), /nombre/);
  assert.match(validate({ ...ok, steps: [] }), /al menos un paso/);
  assert.match(validate({ ...ok, steps: [{ type: "text", at: 2, text: "Hola" }, { type: "audio", at: 0, mode: "play", sound: "" }] }), /Paso 1 \(Sonido, 0 s\): elige un sonido/);
  assert.match(validate({ ...ok, steps: [{ type: "text", at: 3, text: "  " }] }), /Paso 1 \(Texto, 3 s\): escribe el texto/);
  assert.equal(validate({ ...ok, steps: [{ type: "audio", at: 0, mode: "stop_music" }] }), "");               // stopping the music needs no sound
  assert.match(validate({ ...ok, steps: [{ type: "image", at: 1, image: "" }] }), /elige una imagen/);
  assert.match(validate({ ...ok, steps: [{ type: "post", at: 1, text: "" }] }), /escribe el mensaje/);
  assert.match(validate({ ...ok, steps: [{ type: "text", at: "x", text: "a" }] }), /número de segundos/);
});

test("steps keep their order in time, and a tie keeps the order they were written in", () => {
  const steps = [{ id: "a", at: 5 }, { id: "b", at: 1 }, { id: "c", at: 5 }, { id: "d", at: "0.5" }];
  assert.deepEqual(orderOf(steps).map((s) => s.id), ["d", "b", "a", "c"]);
});

test("a dragged step lands on a snapped time inside the timeline", () => {
  assert.equal(draggedTo(2, 100, 400, 20), 7);                  // a quarter of the row is five seconds
  assert.equal(draggedTo(2, -900, 400, 20), 0);                 // never before the start
  assert.equal(draggedTo(18, 900, 400, 20), 20);                // nor past the end
  assert.equal(draggedTo(1, 2, 400, 20), 1.1);                  // snapped to a tenth
  assert.equal(draggedTo(4, 50, 0, 20), 4);                     // a row with no width moves nothing
});

test("the ruler has about eight marks at round seconds", () => {
  assert.deepEqual(rulerTicks(8), [0, 1, 2, 3, 4, 5, 6, 7, 8]);
  assert.deepEqual(rulerTicks(22), [0, 5, 10, 15, 20]);
  assert.deepEqual(rulerTicks(100), [0, 15, 30, 45, 60, 75, 90]);
});

// ---- 2.0: the creator's steps ------------------------------------------------------------------------------------------------
import { effectsAt, envelope, particles, pasteAt, screenLook, stageAt, templateSteps, titleAt, weatherAt, TEMPLATES } from "../src/cinema-model.js";

test("screen effects rise, hold and fade, and several can be on at once", () => {
  assert.equal(envelope("blur", 0), 0);
  assert.equal(envelope("blur", 0.5), 1);
  assert.ok(envelope("blur", 0.95) < 0.3 && envelope("flash", 0.1) > envelope("flash", 0.8));
  const cinema = { steps: [
    { type: "effect", at: 0, effect: "blur", duration: 4, intensity: 50 },
    { type: "effect", at: 1, effect: "tint", color: "#ff0000", duration: 4, intensity: 100 },
    { type: "effect", at: 1, effect: "shake", duration: 2, intensity: 100 },
  ] };
  const look = screenLook(effectsAt(cinema, 2), 2);
  assert.match(look.filter, /blur\(6\.0px\)/);
  assert.equal(look.layers[0].kind, "tint");
  assert.match(look.transform, /translate/);
  const calm = screenLook(effectsAt(cinema, 2), 2, true);                 // less motion: no shaking, the colours stay
  assert.equal(calm.transform, "");
  assert.equal(calm.layers.length, 1);
  assert.deepEqual(effectsAt(cinema, 9), []);
});

test("a dialogue keeps both portraits between its lines and says who is talking", () => {
  const cinema = { steps: templateSteps("dialogue", 2) };
  assert.equal(stageAt(cinema, 1), null);                                  // before it starts
  const first = stageAt(cinema, 2.5);
  assert.equal(first.active, "left");
  assert.equal(first.left.speaker, "Personaje A");
  const second = stageAt(cinema, 6);
  assert.equal(second.active, "right");
  assert.ok(second.left && second.right);
  assert.ok(stageAt(cinema, 5.1));                                          // between two lines the portraits stay
  assert.equal(stageAt(cinema, 30), null);                                  // and leave a moment after the last one
  const withScene = { steps: [...cinema.steps, { type: "scene", at: 7, color: "#000000" }] };
  assert.equal(stageAt(withScene, 7.5), null);                              // a new scene clears the stage
});

test("weather lasts until the next weather step and titles until their end", () => {
  const cinema = { steps: [{ type: "weather", at: 1, weather: "snow", intensity: 40 }, { type: "weather", at: 5, weather: "none" },
    { type: "title", at: 2, text: "Capítulo I", duration: 2 }] };
  assert.equal(weatherAt(cinema, 0.5), null);
  assert.equal(weatherAt(cinema, 3).weather, "snow");
  assert.equal(weatherAt(cinema, 6), null);
  assert.equal(titleAt(cinema, 3).step.text, "Capítulo I");
  assert.equal(titleAt(cinema, 4.5), null);
  const a = particles("rain", 50), b = particles("rain", 50);
  assert.deepEqual(a, b);                                                   // the same for everybody
  assert.ok(particles("rain", 100).length > a.length && particles("rain", 100, true).length < particles("rain", 100).length);
});

test("templates give steps from the cursor, and pasted steps keep their spacing", () => {
  for (const tpl of TEMPLATES) {
    const steps = templateSteps(tpl.id, 10);
    assert.ok(steps.length > 0 && Math.min(...steps.map((s) => s.at)) === 10, tpl.id);
    assert.ok(steps.every((s) => s.type), tpl.id);
  }
  const pasted = pasteAt([{ type: "text", at: 4, text: "a" }, { type: "effect", at: 5.5, effect: "flash" }], 20);
  assert.deepEqual(pasted.map((s) => s.at), [20, 21.5]);
});
