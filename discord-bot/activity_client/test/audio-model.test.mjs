import test from "node:test";
import assert from "node:assert/strict";
import { effectGain, musicGain, musicOffset, isStale, shouldPreload } from "../src/audio-model.js";

const prefs = { audio: true, sfxVolume: 50, musicVolume: 80 };

test("the loudness of a sound is the server's volume times the player's, and zero when the player turned the event sound off", () => {
  assert.equal(effectGain(80, prefs), 0.4);
  assert.equal(effectGain(100, { ...prefs, sfxVolume: 100 }), 1);
  assert.equal(effectGain(80, { ...prefs, audio: false }), 0);
  assert.equal(effectGain(500, { ...prefs, sfxVolume: 100 }), 1);                      // never above full
});

test("the music is the game master's volume times the track's own times the player's music volume", () => {
  const music = { volume: 50, sound: { volume: 80 } };
  assert.ok(Math.abs(musicGain(music, prefs) - 0.5 * 0.8 * 0.8) < 1e-9);
  assert.equal(musicGain(null, prefs), 0);
  assert.equal(musicGain(music, { ...prefs, audio: false }), 0);
  assert.equal(musicGain({ volume: 100, sound: {} }, { ...prefs, musicVolume: 100 }), 1);
});

test("somebody who joins late starts the track where the others are, wrapping a loop and skipping what already ended", () => {
  const m = (extra) => ({ startedAt: 1000, now: 11000, loop: true, ...extra });
  assert.equal(musicOffset(m(), { duration: 60 }), 10);                                // 10 s since it started
  assert.equal(musicOffset(m(), { duration: 4 }), 2);                                  // a 4 s loop has gone round twice
  assert.equal(musicOffset(m(), { duration: 60, transitMs: 100, heldMs: 400 }), 10.5);
  assert.equal(musicOffset(m({ loop: false }), { duration: 60 }), 10);
  assert.equal(musicOffset(m({ loop: false }), { duration: 8 }), null);                // it ended 2 s ago
  assert.equal(musicOffset(m({ now: 1000 }), { duration: 60 }), 0);
  assert.equal(musicOffset(m(), {}), 10);                                              // length not known yet: the plain elapsed time
  assert.equal(musicOffset(m({ loop: false }), {}), null);
});

test("a sound that comes late is dropped, and only small non-music sounds are loaded ahead", () => {
  assert.equal(isStale({ at: 1000 }, 3000), false);
  assert.equal(isStale({ at: 1000 }, 6000), true);
  assert.equal(isStale({}, 6000), false);
  assert.equal(shouldPreload({ kind: "sfx", size: 1000 }), true);
  assert.equal(shouldPreload({ kind: "music", size: 1000 }), false);
  assert.equal(shouldPreload({ kind: "voice", size: 9 * 1024 * 1024 }), false);
});
