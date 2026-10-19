// Short synthesised sounds (no audio files to ship) and vibration, controlled by the player's settings.
import { prefs } from "./state.js";

let ctx = null;

function audio() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { ctx = new AC(); } catch { return null; }
  }
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

// Browsers only let a page make sound after the person touched it once.
export function unlockAudio() { audio(); }
document.addEventListener("pointerdown", unlockAudio, { once: true, passive: true });
document.addEventListener("keydown", unlockAudio, { once: true });

function tone(c, { freq, to = freq, start = 0, dur = 0.12, type = "sine", gain = 0.5 }) {
  const t0 = c.currentTime + start;
  const osc = c.createOscillator(), amp = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (to !== freq) osc.frequency.exponentialRampToValueAtTime(to, t0 + dur);
  const volume = (prefs.value.volume / 100) * gain;
  amp.gain.setValueAtTime(0.0001, t0);
  amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, volume), t0 + 0.012);
  amp.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(amp).connect(c.destination);
  osc.start(t0);
  osc.stop(t0 + dur + 0.03);
}

const SOUNDS = {
  qte: (c) => { tone(c, { freq: 620, to: 880, dur: 0.1, type: "triangle" }); tone(c, { freq: 880, start: 0.09, dur: 0.1, type: "triangle" }); },
  parry: (c) => { tone(c, { freq: 1046, to: 1318, dur: 0.14, type: "square", gain: 0.28 }); },
  ok: (c) => { [523, 659, 784].forEach((f, i) => tone(c, { freq: f, start: i * 0.07, dur: 0.14, type: "triangle" })); },
  bad: (c) => { tone(c, { freq: 180, to: 90, dur: 0.28, type: "sawtooth", gain: 0.35 }); },
  bf: (c) => { tone(c, { freq: 220, to: 1760, dur: 0.35, type: "sawtooth", gain: 0.3 }); [880, 1175, 1568].forEach((f, i) => tone(c, { freq: f, start: 0.3 + i * 0.06, dur: 0.18, type: "triangle" })); },
  tick: (c) => { tone(c, { freq: 1400, dur: 0.04, type: "square", gain: 0.15 }); },
  beat: (c) => { tone(c, { freq: 440, dur: 0.09, type: "sine", gain: 0.6 }); },
};

export function play(name) {
  if (!prefs.value.sound || !SOUNDS[name]) return;
  const c = audio();
  if (c) { try { SOUNDS[name](c); } catch { /* sound is a courtesy */ } }
}

export function vibrate(pattern) {
  if (prefs.value.haptics && navigator.vibrate) { try { navigator.vibrate(pattern); } catch { /* not allowed here */ } }
}
