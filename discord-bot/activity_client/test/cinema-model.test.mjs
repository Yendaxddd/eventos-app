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
  assert.deepEqual(sceneAt(cinema, 0), { color: "#220033", image: "files/images/a.png", dim: 50 });
  assert.deepEqual(sceneAt(cinema, 9), { color: "#000000", image: null, dim: 0 });
  assert.deepEqual(sceneAt({ bg: "#111111", steps: [] }, 5), { color: "#111111", image: null, dim: 0 });
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
  assert.deepEqual(newStep("text", []), { type: "text", at: 0, speaker: "", text: "", duration: 4, effect: "type", color: "", size: "normal", avatar: "" });
  assert.equal(newStep("audio", cinema.steps).at, 8);
  assert.equal(newStep("post", []).type, "post");
  assert.equal(newStep("effect", []).duration, 0.6);
});

import { LANES, draggedTo, laneOf, orderOf, rulerTicks, validate } from "../src/cinema-model.js";

test("every kind of step sits on one row of the timeline", () => {
  for (const type of ["text", "audio", "image", "scene", "effect", "vfx", "post"]) assert.ok(LANES.some((l) => l[2].includes(type)), type);
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
