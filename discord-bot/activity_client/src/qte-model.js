// What a QTE looks like to a player over time. Pure functions (no DOM, no network), so they can be tested on their own.
//
// A QTE frame (from the server) says when it started (`tGo`), how long it lasts (`timeout`) and, in seconds from its start,
// the windows in which an answer counts: `windows.evade = [0, e]`, `windows.parry = [a, b]`, `windows.bf = [c, d]` (the
// Black Flash band inside the parry window). The bot judges every answer by those windows, so the screen shows exactly them:
//
//   single, for the target   EVADE until the parry window opens, then PARRY until it closes, then "late"
//   group                    EVADE until the evade window closes (parry is refused by the bot in a group QTE)
//   direction                the arrows, until the window closes
//   combo                    the current step's button, until that step's limit
//   bf_chain                 wait for the parry window (pressing early ends the chain), then PARRY
//   single, for somebody else  RESCATAR (save) until the evade window closes

export const TIMED_CMDS = ["evade", "parry", "save", "up", "down", "left", "right"];
export const ARROW_CMDS = ["up", "down", "left", "right"];

export function roleOf(q, youId) {
  if (!youId || !q || q.mode === "fake") return null;
  if (q.mode === "group") return (q.participants || []).includes(youId) ? "target" : null;
  if (q.target && q.target.id === youId) return "target";
  if (q.mode === "single" && q.target && (q.commands || []).includes("save")) return "rescuer";
  return null;
}

// `net` is how long the QTE frame took to reach us (ms) and `ago` how long the QTE had already been running when the server
// sent it (seconds; a QTE joined after a reconnect): the timeline starts when the bot started the QTE, not when we heard of it.
export function makeEntry(q, { arrival, net = 0, ago = 0, youId = null, practice = false } = {}) {
  const role = roleOf(q, youId);
  const entry = {
    id: String(q.id), q, role, practice, arrival, start: arrival - Math.max(0, net) - Math.max(0, ago) * 1000,
    seen: null, pressed: false, busy: false, result: null, ended: false, endedAt: 0, pressedCmd: null, step: null,
  };
  if (q.mode === "combo" && q.combo) {
    entry.step = { cmd: q.combo.step, index: q.combo.index || 0, from: 0 };
  }
  return entry;
}

export const elapsedSeconds = (entry, nowMs) => (nowMs - entry.start) / 1000;

const live = (kind, cmd, from, to, extra = {}) => ({ kind, cmd, from, to, state: "live", ...extra });

// The phase a QTE is in at `t` seconds after it started.
export function phaseAt(entry, t) {
  const q = entry.q, w = q.windows || {};
  const evEnd = w.evade ? w.evade[1] : 0;
  const parry = w.parry || null;
  const timeout = q.timeout || 0;

  if (entry.role === "rescuer") {
    return t <= evEnd ? live("save", "save", 0, evEnd) : { kind: "late", cmd: null, from: evEnd, to: timeout, state: "late", of: "save" };
  }
  if (entry.role !== "target") return { kind: "none", cmd: null, from: 0, to: 0, state: "late" };

  switch (q.mode) {
    case "single": {
      if (!parry) return t <= evEnd ? live("evade", "evade", 0, evEnd) : { kind: "late", cmd: null, from: evEnd, to: timeout, state: "late" };
      const evadeTo = Math.min(evEnd, parry[0]);
      const parryTo = Math.min(parry[1], timeout || parry[1]);
      if (t < evadeTo) return live("evade", "evade", 0, evadeTo, { next: "parry" });
      if (t < parry[0]) return { kind: "wait", cmd: null, from: evadeTo, to: parry[0], state: "wait" };
      if (t <= parryTo) return live("parry", "parry", parry[0], parryTo, { bf: bfBand(w.bf, parry[0], parryTo), evadeEnd: evEnd });
      return { kind: "late", cmd: null, from: parryTo, to: timeout, state: "late", of: "parry" };
    }
    case "group":
      return t <= evEnd ? live("evade", "evade", 0, evEnd) : { kind: "late", cmd: null, from: evEnd, to: timeout, state: "late" };
    case "direction":
      return t <= evEnd ? live("arrows", "arrows", 0, evEnd, { arrow: q.arrow }) : { kind: "late", cmd: null, from: evEnd, to: timeout, state: "late" };
    case "combo": {
      const step = entry.step;
      if (!step) return { kind: "none", cmd: null, from: 0, to: 0, state: "late" };
      const limit = (q.combo.limits && q.combo.limits[step.index]) || timeout;
      return t <= limit ? live("combo", step.cmd, step.from, limit, { index: step.index, length: q.combo.length })
        : { kind: "late", cmd: null, from: limit, to: timeout, state: "late" };
    }
    case "bf_chain": {
      if (!parry) return { kind: "none", cmd: null, from: 0, to: 0, state: "late" };
      const parryTo = Math.min(parry[1], timeout || parry[1]);
      if (t < parry[0]) return { kind: "wait", cmd: null, from: 0, to: parry[0], state: "wait", chain: q.chain };
      if (t <= parryTo) return live("bf", "parry", parry[0], parryTo, { bf: bfBand(w.bf, parry[0], parryTo), chain: q.chain });
      return { kind: "late", cmd: null, from: parryTo, to: timeout, state: "late", of: "parry", chain: q.chain };
    }
    default:
      return { kind: "none", cmd: null, from: 0, to: 0, state: "late" };
  }
}

// The Black Flash band as fractions (0–1) of the parry phase, for drawing it on the bar.
function bfBand(bf, from, to) {
  if (!bf || to <= from) return null;
  const a = (bf[0] - from) / (to - from), b = (bf[1] - from) / (to - from);
  return [Math.max(0, Math.min(1, a)), Math.max(0, Math.min(1, b))];
}

// Seconds (from the QTE's start) at which, if nothing is pressed, the player fails. Used to decide which QTE is most urgent.
export function deadlineOf(entry) {
  const q = entry.q, w = q.windows || {};
  if (entry.role === "rescuer") return w.evade ? w.evade[1] : q.timeout;
  if (q.mode === "combo" && entry.step) return (q.combo.limits && q.combo.limits[entry.step.index]) || q.timeout;
  if (q.mode === "direction") return w.evade ? w.evade[1] : q.timeout;
  return q.timeout || (w.parry ? w.parry[1] : 0);
}

// Most urgent first. Entries that are over (answered or ended) go last, in the order they appeared.
export function byUrgency(entries, nowMs) {
  return [...entries].sort((a, b) => {
    const da = a.pressed || a.ended ? Infinity : deadlineOf(a) - elapsedSeconds(a, nowMs);
    const db = b.pressed || b.ended ? Infinity : deadlineOf(b) - elapsedSeconds(b, nowMs);
    return da - db || a.start - b.start;
  });
}

// Can this button be pressed right now? (The bot would refuse or punish the other cases.)
//   ctx = { canWrite, parryCooldown (s left), saves: { left, wait (s until one frees up) }, keepEvade }
export function canPress(entry, cmd, t, ctx = {}) {
  if (ctx.canWrite === false) return false;
  if (entry.ended || entry.busy) return false;
  if (entry.pressed && entry.q.mode !== "combo") return false;
  const ph = phaseAt(entry, t);
  if (ph.state !== "live") return false;
  if (ph.kind === "arrows") return ARROW_CMDS.includes(cmd);
  if (cmd === ph.cmd) {
    if (cmd === "parry" && ctx.parryCooldown > 0) return false;
    if (cmd === "save" && ctx.saves && ctx.saves.left <= 0) return false;
    return true;
  }
  // the evade window can still be open while the parry button is showing: allowed (keyboard, or the small button when kept)
  if (cmd === "evade" && ph.kind === "parry" && ph.evadeEnd !== undefined && t <= ph.evadeEnd && (entry.q.commands || []).includes("evade")) return true;
  return false;
}

// What to call the answer once the server says how it went.
export function verdictOf(entry, res) {
  const cmd = entry.pressedCmd;
  const ms = res.ms;
  if (res.ok === null || res.ok === undefined) return { ok: null, label: "Enviado", sub: "" };
  if (!res.ok) return { ok: false, label: "Fallaste", sub: ms != null ? `${(ms / 1000).toFixed(2)} s` : "" };
  const q = entry.q;
  if (res.bf) return { ok: true, bf: true, label: "¡Black Flash!", sub: ms != null ? `${(ms / 1000).toFixed(2)} s` : "" };
  const sub = ms != null ? `${(ms / 1000).toFixed(2)} s` : "";
  if (cmd === "parry") {
    const bf = q.windows && q.windows.bf;
    const perfect = bf && ms != null && ms / 1000 >= bf[0] && ms / 1000 <= bf[1];
    return { ok: true, label: perfect ? "¡Parry perfecto!" : "¡Parry!", sub, perfect: !!perfect };
  }
  if (cmd === "save") return { ok: true, label: "¡Rescate!", sub };
  if (ARROW_CMDS.includes(cmd)) return { ok: true, label: "¡Correcto!", sub };
  if (q.mode === "combo") return { ok: true, label: res.done ? "¡Combo completo!" : "¡Bien!", sub };
  return { ok: true, label: "¡Esquivado!", sub };
}
