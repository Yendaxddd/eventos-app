// Training mode: random practice QTEs of the kinds, difficulties and pace the player chooses. Pure code (no DOM, no network), so the
// rules can be tested on their own; the clock that spawns them is in training.js and the page in views/Training.jsx.
import { clamp } from "./util.js";

export const KINDS = ["single", "group", "direction", "combo", "bf_chain"];
export const DIFFICULTIES = ["easy", "medium", "hard", "impossible"];
export const COUNTS = [10, 25, 50, 100, 0];             // 0 = until the player stops

export const DEFAULT_CONFIG = {
  kinds: ["single", "group", "direction", "combo"], difficulties: ["medium"],
  count: 25, gapMin: 1.5, gapMax: 4, simultaneous: 1, speed: 100, comboLength: 3, suddenDeath: false,
};

const RANGES = { gapMin: [0.3, 15], gapMax: [0.3, 15], simultaneous: [1, 3], speed: [50, 200], comboLength: [2, 6] };

// Anything that does not fit falls back to the default; lists keep only known values (in the usual order) and are never empty.
export function sanitizeConfig(raw) {
  const out = { ...DEFAULT_CONFIG, kinds: [...DEFAULT_CONFIG.kinds], difficulties: [...DEFAULT_CONFIG.difficulties] };
  if (!raw || typeof raw !== "object") return out;
  const pick = (list, known) => { const kept = known.filter((k) => Array.isArray(list) && list.includes(k)); return kept.length ? kept : null; };
  out.kinds = pick(raw.kinds, KINDS) || out.kinds;
  out.difficulties = pick(raw.difficulties, DIFFICULTIES) || out.difficulties;
  if (Number.isInteger(raw.count) && raw.count >= 0 && raw.count <= 500) out.count = raw.count;       // 0 = until stopped; the page offers a few, any other is fine
  for (const [key, [low, high]] of Object.entries(RANGES)) {
    const v = raw[key];
    if (typeof v === "number" && Number.isFinite(v)) out[key] = key === "gapMin" || key === "gapMax" ? Math.round(clamp(v, low, high) * 10) / 10 : Math.round(clamp(v, low, high));
  }
  if (out.gapMax < out.gapMin) out.gapMax = out.gapMin;
  if (typeof raw.suddenDeath === "boolean") out.suddenDeath = raw.suddenDeath;
  return out;
}

export const PRESETS = [
  ["warmup", "Calentamiento", { kinds: ["single", "group"], difficulties: ["easy"], count: 10, gapMin: 2.5, gapMax: 5, simultaneous: 1, speed: 100, suddenDeath: false }],
  ["normal", "Normal", { ...DEFAULT_CONFIG }],
  ["intense", "Intenso", { kinds: ["single", "group", "direction", "combo", "bf_chain"], difficulties: ["medium", "hard"], count: 50, gapMin: 1, gapMax: 2.5, simultaneous: 2, speed: 115, suddenDeath: false }],
  ["chaos", "Caos", { kinds: ["single", "group", "direction", "combo", "bf_chain"], difficulties: ["hard", "impossible"], count: 0, gapMin: 0.5, gapMax: 1.5, simultaneous: 3, speed: 130, suddenDeath: true }],
];

// ---- what to throw next -----------------------------------------------------------------------------------------------
const ARROWS = ["up", "down", "left", "right"];
const pickOf = (list, rng) => list[Math.min(list.length - 1, Math.floor(rng() * list.length))];

// The next QTE: { mode, difficulty, extra } for practiceFrame. `last` (the previous mode) is avoided when there is a choice.
export function nextSpec(config, rng = Math.random, last = null) {
  const kinds = config.kinds.length > 1 && last ? config.kinds.filter((k) => k !== last) : config.kinds;
  const mode = pickOf(kinds, rng);
  const difficulty = pickOf(config.difficulties, rng);
  const extra = {};
  if (mode === "direction") extra.arrow = pickOf(ARROWS, rng);
  if (mode === "combo") extra.sequence = Array.from({ length: config.comboLength }, () => (rng() < 0.5 ? "evade" : "parry"));
  if (mode === "bf_chain") { extra.chain = 1 + Math.floor(rng() * 3); extra.from = 0.8 + rng() * 0.7; extra.len = 1.1; }
  return { mode, difficulty, extra };
}

export const gapMs = (config, rng = Math.random) => Math.round((config.gapMin + rng() * (config.gapMax - config.gapMin)) * 1000);

// Speeds a practice frame up (speed 150 = every window is a third shorter) or slows it down.
export function scaleFrame(frame, speed) {
  const f = 100 / clamp(speed, 50, 200);
  if (f === 1) return frame;
  const span = (pair) => (pair ? [pair[0] * f, pair[1] * f] : pair);
  const out = { ...frame, timeout: frame.timeout * f };
  if (frame.windows) out.windows = { ...frame.windows, evade: span(frame.windows.evade), parry: span(frame.windows.parry), bf: span(frame.windows.bf) };
  if (frame.combo) out.combo = { ...frame.combo, limits: frame.combo.limits.map((x) => x * f) };
  return out;
}

// ---- the session's numbers --------------------------------------------------------------------------------------------
export function emptyStats() {
  return { total: 0, ok: 0, fail: 0, timeouts: 0, streak: 0, bestStreak: 0, bf: 0, msSum: 0, msN: 0, bestMs: null, byKind: {}, byDifficulty: {}, recent: [] };
}

// One finished QTE: { ok, bf, ms (ms from the start, when answered), timedOut, mode, difficulty }. Returns new stats (the old ones are untouched).
export function record(stats, r) {
  const next = { ...stats, byKind: { ...stats.byKind }, byDifficulty: { ...stats.byDifficulty }, recent: [...stats.recent, r.ok ? 1 : 0].slice(-24) };
  next.total++;
  if (r.ok) {
    next.ok++; next.streak++; next.bestStreak = Math.max(next.bestStreak, next.streak);
    if (r.bf) next.bf++;
    if (Number.isFinite(r.ms)) { next.msSum += r.ms; next.msN++; next.bestMs = next.bestMs === null ? r.ms : Math.min(next.bestMs, r.ms); }
  } else {
    next.fail++; next.streak = 0;
    if (r.timedOut) next.timeouts++;
  }
  for (const [bucket, key] of [["byKind", r.mode], ["byDifficulty", r.difficulty]]) {
    const old = next[bucket][key] || { n: 0, ok: 0 };
    next[bucket][key] = { n: old.n + 1, ok: old.ok + (r.ok ? 1 : 0) };
  }
  return next;
}

export const accuracy = (stats) => (stats.total ? stats.ok / stats.total : 0);
export const averageMs = (stats) => (stats.msN ? Math.round(stats.msSum / stats.msN) : null);

// Compared with the player's bests (kept on this device): which ones this session beat. A session of fewer than 10 QTEs only counts for the streak.
export function beats(stats, best) {
  const out = [];
  const b = best || {};
  if (stats.bestStreak > (b.bestStreak || 0) && stats.bestStreak >= 3) out.push("streak");
  if (stats.total >= 10) {
    if (accuracy(stats) > (b.accuracy || 0)) out.push("accuracy");
    const avg = averageMs(stats);
    if (avg !== null && (b.averageMs == null || avg < b.averageMs)) out.push("speed");
  }
  return out;
}

export function mergeBest(stats, best) {
  const b = { ...(best || {}) };
  b.bestStreak = Math.max(b.bestStreak || 0, stats.bestStreak);
  if (stats.total >= 10) {
    b.accuracy = Math.max(b.accuracy || 0, accuracy(stats));
    const avg = averageMs(stats);
    if (avg !== null) b.averageMs = b.averageMs == null ? avg : Math.min(b.averageMs, avg);
  }
  return b;
}
