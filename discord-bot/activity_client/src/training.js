// The training session: throws random practice QTEs (see training-model.js), reads how each one ended and keeps the numbers. Nothing here is
// sent to the server, and nobody gets hurt. The QTEs are the same widgets as the real ones (the practice entries of qte-store.js).
import { signal } from "@preact/signals";
import { qtes, rules } from "./state.js";
import { startQte, expirePractice } from "./qte-store.js";
import { phaseAt, elapsedSeconds } from "./qte-model.js";
import { practiceFrame } from "./practice.js";
import { DEFAULT_CONFIG, beats, emptyStats, gapMs, mergeBest, nextSpec, record, sanitizeConfig, scaleFrame } from "./training-model.js";
import { store } from "./util.js";

const CONFIG_KEY = "eventos.training.config", BEST_KEY = "eventos.training.best";
const TICK_MS = 100;
const LEAD_IN_MS = 1600;                  // «prepárate» before the first one

export const loadConfig = () => sanitizeConfig(store.json(CONFIG_KEY, null));
export const saveConfig = (config) => store.set(CONFIG_KEY, JSON.stringify(config));
export const loadBest = () => store.json(BEST_KEY, null) || {};

// phase: "config" | "run" | "done"
export const training = signal({ phase: "config", config: loadConfig(), stats: emptyStats(), spawned: 0, paused: false, startedAt: 0, endedAt: 0, records: [], recordsBeaten: [], reason: "" });

let timer = 0, nextAt = 0, lastMode = null, rng = Math.random, serial = 0;
const recorded = new Set();
const mine = (e) => e.practice && String(e.id).startsWith("train-");
const set = (patch) => { training.value = { ...training.value, ...patch }; };

export function startTraining(config = training.value.config, { random = Math.random } = {}) {
  stopTimer();
  clearTraining();
  rng = random; recorded.clear(); lastMode = null;
  const clean = sanitizeConfig(config);
  saveConfig(clean);
  const now = performance.now();
  nextAt = now + LEAD_IN_MS;
  training.value = { phase: "run", config: clean, stats: emptyStats(), spawned: 0, paused: false, startedAt: now, endedAt: 0, records: [], recordsBeaten: [], reason: "" };
  timer = setInterval(tick, TICK_MS);
}

function stopTimer() { clearInterval(timer); timer = 0; }
export function clearTraining() { qtes.value = qtes.value.filter((e) => !mine(e)); }

export function pauseTraining(paused) { if (training.value.phase === "run") set({ paused }); }

// Ends the session. With nothing answered there is nothing to show: back to the settings.
export function stopTraining(reason = "stopped") {
  stopTimer();
  clearTraining();
  const t = training.value;
  if (t.phase !== "run") return;
  if (!t.stats.total) { set({ phase: "config", reason }); return; }
  const best = loadBest();
  const records = beats(t.stats, best);
  store.set(BEST_KEY, JSON.stringify(mergeBest(t.stats, best)));
  set({ phase: "done", endedAt: performance.now(), recordsBeaten: records, reason });
}

export function backToConfig() { stopTimer(); clearTraining(); set({ phase: "config", reason: "" }); }

// A real QTE for this player comes first: nothing new is thrown while one is open.
const realOpen = () => qtes.value.some((e) => !e.practice && e.role === "target" && !e.pressed && !e.ended);

function tick() {
  const t = training.value;
  if (t.phase !== "run") { stopTimer(); return; }
  const now = performance.now();
  const entries = qtes.value.filter(mine);

  // combo steps that ran out of time end the QTE (the practice timer only knows the whole QTE)
  for (const e of entries) {
    if (e.q.mode === "combo" && !e.pressed && !e.busy && phaseAt(e, elapsedSeconds(e, now)).state === "late") expirePractice(e.id, "Combo roto", "demasiado lento");
  }

  // read what finished
  let stats = t.stats, records = t.records, changed = false;
  for (const e of qtes.value.filter(mine)) {
    if (!e.pressed || !e.result || recorded.has(e.id)) continue;
    recorded.add(e.id);
    const timedOut = e.pressedCmd === null || e.pressedCmd === undefined;
    const r = { ok: e.result.ok === true, bf: !!e.result.bf, ms: e.ms, timedOut, mode: e.q.mode, difficulty: e.q.difficulty };
    stats = record(stats, r); records = [...records, r]; changed = true;
    nextAt = Math.max(nextAt, now + Math.round(t.config.gapMin * 800));        // a breath after one ends
  }
  if (changed) set({ stats, records });

  const config = t.config;
  if (config.suddenDeath && stats.fail > 0) { endLater(); return; }
  if (config.count > 0 && stats.total >= config.count) { endLater(); return; }
  if (t.paused || realOpen()) { nextAt = Math.max(nextAt, now + TICK_MS); return; }

  const open = qtes.value.filter((e) => mine(e) && !e.pressed && !e.ended).length;
  if (now >= nextAt && open < config.simultaneous && (config.count === 0 || t.spawned < config.count)) spawn(config);
}

// let the last verdict be seen for a moment before the summary
let ending = 0;
function endLater() {
  stopTimer();
  clearTimeout(ending);
  ending = setTimeout(() => stopTraining(training.value.config.suddenDeath && training.value.stats.fail > 0 ? "sudden" : "finished"), 900);
}

function spawn(config) {
  const spec = nextSpec(config, rng, lastMode);
  lastMode = spec.mode;
  const frame = scaleFrame(practiceFrame(`train-${++serial}`, spec.difficulty, rules.value, spec.mode, spec.extra), config.speed);
  frame.tGo = 0;
  startQte(frame, { practice: true });
  nextAt = performance.now() + gapMs(config, rng);
  set({ spawned: training.value.spawned + 1 });
}

export { DEFAULT_CONFIG };
