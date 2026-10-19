// Judging an answer on the player's own screen, with the same rules as the bot: used by the tutorial's practice, where
// nothing is sent to the server and nobody gets hurt.
import { ARROW_CMDS } from "./qte-model.js";

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
  if (mode === "group") { frame.windows = { evade: [0, t.evade], bf: null }; frame.commands = ["evade"]; }
  if (mode === "direction") {
    const limit = Math.min(t.evade + 1, 4);
    frame.timeout = limit; frame.windows = { evade: [0, limit], bf: null }; frame.commands = ["up", "down", "left", "right"];
    frame.arrow = extra.arrow || "up";
  }
  if (mode === "combo") {
    const sequence = extra.sequence || ["evade", "parry", "evade"];
    const step = t.evade + 0.5;
    frame.timeout = 15; frame.windows = null; frame.commands = ["evade", "parry"];
    frame.combo = { length: sequence.length, index: 0, step: sequence[0], limits: sequence.map((_, i) => step * (i + 1)), sequence };
  }
  return { ...frame, ...extra.override };
}

// The verdict of pressing `cmd` at `t` seconds after the QTE started. Black Flash is a dice roll in the real game,
// so here landing in its band is reported as "zona Black Flash" instead of rolling.
export function judge(q, cmd, t, state = {}) {
  const w = q.windows || {};
  const evEnd = w.evade ? w.evade[1] : 0;
  const fmt = (x) => `${x.toFixed(2)} s`;
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
  if (q.mode === "group") return cmd === "evade" && t <= evEnd ? { ok: true, label: "¡Esquivado!", sub: fmt(t) } : { ok: false, label: "Tarde", sub: fmt(t) };
  if (q.mode === "direction") {
    if (!ARROW_CMDS.includes(cmd)) return { ok: false, label: "Fallaste", sub: "" };
    if (t > evEnd) return { ok: false, label: "Tarde", sub: fmt(t) };
    return cmd === OPPOSITE[q.arrow] ? { ok: true, label: "¡Correcto!", sub: fmt(t) } : { ok: false, label: "Dirección equivocada", sub: `era ${OPPOSITE[q.arrow]}` };
  }
  if (q.mode === "combo") {
    const index = state.index || 0, expected = q.combo.sequence[index], limit = q.combo.limits[index];
    if (cmd !== expected) return { ok: false, label: "Combo roto", sub: `tocaba ${expected}` };
    if (t > limit) return { ok: false, label: "Combo roto", sub: "demasiado lento" };
    return { ok: true, step: true, done: index + 1 >= q.combo.length, label: index + 1 >= q.combo.length ? "¡Combo completo!" : "¡Bien!", sub: fmt(t) };
  }
  return { ok: false, label: "Fallaste", sub: "" };
}
