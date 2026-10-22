// Judging an answer on the player's own screen, with the same rules as the bot: used by the tutorial's practice, where
// nothing is sent to the server and nobody gets hurt.
import { ARROW_CMDS, GESTURE_MODES } from "./qte-model.js";
import { CMD } from "./terms.js";

const OPPOSITE = { up: "down", down: "up", left: "right", right: "left" };

// A QTE frame in the shape the server sends it, from the bot's timings (`rules.times[difficulty]`).
export function practiceFrame(id, difficulty, rules, mode = "single", extra = {}) {
  const t = (rules && rules.times && rules.times[difficulty]) || { evade: 4.5, parry: [3, 5], timeout: 5, perfect: 4 };
  const bfHalf = (rules && rules.bfWindow) || 0.2;
  const center = (t.parry[0] + t.parry[1]) / 2;
  const frame = {
    id: String(id), mode, difficulty, target: { id: "practice", name: "Tú" }, participants: [], tGo: 0, timeout: t.timeout,
    windows: { evade: [0, t.evade], parry: [t.parry[0], t.parry[1]], bf: [Math.max(0, center - bfHalf), center + bfHalf] },
    commands: ["evade", "parry"], practice: true,
  };
  if (mode === "group") { frame.participants = ["practice"]; frame.windows = { evade: [0, t.evade], bf: null }; frame.commands = ["evade"]; }
  if (mode === "direction") {
    const limit = Math.min(t.evade + 1, 4);
    frame.timeout = limit; frame.windows = { evade: [0, limit], bf: null }; frame.commands = ["up", "down", "left", "right"];
    frame.arrow = extra.arrow || "up";
  }
  if (mode === "bf_chain") {
    const from = extra.from ?? 1.0, len = extra.len ?? 1.2;
    frame.timeout = 3; frame.commands = ["parry"]; frame.chain = extra.chain || 1;
    frame.windows = { parry: [from, from + len], bf: [from + len / 2 - bfHalf, from + len / 2 + bfHalf] };
  }
  if (mode === "combo") {
    const sequence = extra.sequence || ["evade", "parry", "evade"];
    const step = t.evade + 0.5;
    frame.timeout = 15; frame.windows = null; frame.commands = ["evade", "parry"];
    frame.combo = { length: sequence.length, index: 0, step: sequence[0], limits: sequence.map((_, i) => step * (i + 1)), sequence };
  }
  if (mode === "fake") {
    frame.windows = { evade: [0, t.timeout], bf: null }; frame.commands = ["evade", "parry"];
  }
  if (GESTURE_MODES.includes(mode)) {
    frame.timeout = GESTURE_TIMEOUT[mode][difficulty] || GESTURE_TIMEOUT[mode].medium;
    frame.windows = { evade: [0, frame.timeout], bf: null }; frame.commands = ["gesture"];
    frame.arena = gestureParams(mode, difficulty, extra.random || Math.random);
  }
  return { ...frame, ...extra.override };
}

// The same rules as the server's arena.py: how long each gesture QTE lasts, and what it asks for.
export const GESTURE_TIMEOUT = {
  flick: { easy: 2.6, medium: 1.9, hard: 1.4, impossible: 1.0 },
  drag: { easy: 4.0, medium: 3.0, hard: 2.3, impossible: 1.7 },
  mash: { easy: 3.2, medium: 3.2, hard: 3.4, impossible: 3.6 },
};
const MASH_COUNT = { easy: 8, medium: 12, hard: 16, impossible: 22 };
const DRAG_TOLERANCE = { easy: 0.16, medium: 0.12, hard: 0.09, impossible: 0.07 };
export function gestureParams(mode, difficulty, rng = Math.random) {
  if (mode === "flick") return { dir: ["up", "down", "left", "right"][Math.floor(rng() * 4) % 4] };
  if (mode === "drag") {
    let from = [0.12 + rng() * 0.18, 0.2 + rng() * 0.6], to = [0.7 + rng() * 0.18, 0.2 + rng() * 0.6];
    if (rng() < 0.5) { from = [1 - from[0], from[1]]; to = [1 - to[0], to[1]]; }
    return { from, to, tolerance: DRAG_TOLERANCE[difficulty] || 0.12 };
  }
  return { count: MASH_COUNT[difficulty] || 12 };
}

// Did the gesture do what was asked? (`data` is what the screen measured.) The server judges a real one the same way.
export function judgeGesture(q, data = {}) {
  const p = q.arena || {};
  if (q.mode === "flick") return data.dir === p.dir ? { ok: true } : { ok: false, why: "wrong_dir" };
  if (q.mode === "drag") {
    const dx = (data.x ?? -9) - p.to[0], dy = (data.y ?? -9) - p.to[1];
    return Math.hypot(dx, dy) <= p.tolerance ? { ok: true } : { ok: false, why: "missed" };
  }
  return (data.count || 0) >= p.count ? { ok: true } : { ok: false, why: "short" };
}

// The verdict of pressing `cmd` at `t` seconds after the QTE started. Black Flash is a dice roll in the real game,
// so here landing in its band is reported as "zona Black Flash" instead of rolling.
export function judge(q, cmd, t, state = {}) {
  const w = q.windows || {};
  const evEnd = w.evade ? w.evade[1] : 0;
  const fmt = (x) => `${x.toFixed(2)} s`;
  if (q.mode === "fake") return { ok: false, label: "¡Era falso!", sub: "caíste en la trampa" };
  if (GESTURE_MODES.includes(q.mode)) {
    if (t > q.timeout) return { ok: false, label: "Tarde", sub: fmt(t) };
    const r = judgeGesture(q, state.data || {});
    const why = { wrong_dir: "Dirección equivocada", missed: "Fuera del blanco", short: "Te faltaron toques" };
    return r.ok ? { ok: true, label: { flick: "¡Deslizado!", drag: "¡En el blanco!", mash: "¡Hecho!" }[q.mode], sub: fmt(t) } : { ok: false, label: why[r.why], sub: fmt(t) };
  }
  if (q.mode === "single") {
    if (cmd === "evade") return t <= evEnd ? { ok: true, label: "¡Esquivado!", sub: fmt(t) } : { ok: false, label: "Tarde", sub: `${fmt(t)} · el límite era ${evEnd.toFixed(1)} s` };
    if (cmd === "parry") {
      const [a, b] = w.parry;
      if (t < a) return { ok: false, label: "Demasiado pronto", sub: `${fmt(t)} · el parry abre en ${a.toFixed(1)} s` };
      if (t > b) return { ok: false, label: "Tarde", sub: fmt(t) };
      const bf = w.bf && t >= w.bf[0] && t <= w.bf[1];
      return bf ? { ok: true, bf: true, label: "¡Zona Black Flash!", sub: `${fmt(t)} · en el juego real tiene una probabilidad de salir` }
        : { ok: true, label: "¡Parry!", sub: fmt(t) };
    }
  }
  if (q.mode === "bf_chain") {
    const [a, b] = w.parry;
    if (cmd !== "parry") return { ok: false, label: "Fallaste", sub: "" };
    if (t < a) return { ok: false, label: "Demasiado pronto", sub: `${fmt(t)} · la cadena se rompe; la ventana abre en ${a.toFixed(1)} s` };
    if (t > b) return { ok: false, label: "Tarde", sub: fmt(t) };
    const bf = w.bf && t >= w.bf[0] && t <= w.bf[1];
    return bf ? { ok: true, bf: true, label: "¡Zona Black Flash!", sub: fmt(t) } : { ok: true, label: "¡Parry!", sub: fmt(t) };
  }
  if (q.mode === "group") return cmd === "evade" && t <= evEnd ? { ok: true, label: "¡Esquivado!", sub: fmt(t) } : { ok: false, label: "Tarde", sub: fmt(t) };
  if (q.mode === "direction") {
    if (!ARROW_CMDS.includes(cmd)) return { ok: false, label: "Fallaste", sub: "" };
    if (t > evEnd) return { ok: false, label: "Tarde", sub: fmt(t) };
    return cmd === OPPOSITE[q.arrow] ? { ok: true, label: "¡Correcto!", sub: fmt(t) } : { ok: false, label: "Dirección equivocada", sub: `era ${(CMD[OPPOSITE[q.arrow]] || "").toLowerCase()}` };
  }
  if (q.mode === "combo") {
    const index = state.index || 0, expected = q.combo.sequence[index], limit = q.combo.limits[index];
    if (cmd !== expected) return { ok: false, label: "Combo roto", sub: `tocaba ${(CMD[expected] || expected).toLowerCase()}` };
    if (t > limit) return { ok: false, label: "Combo roto", sub: "demasiado lento" };
    return { ok: true, step: true, done: index + 1 >= q.combo.length, label: index + 1 >= q.combo.length ? "¡Combo completo!" : "¡Bien!", sub: fmt(t) };
  }
  return { ok: false, label: "Fallaste", sub: "" };
}
