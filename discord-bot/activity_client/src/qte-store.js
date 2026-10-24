// The QTEs on this player's screen: they come from the server (or from the tutorial's practice), they are answered
// with a button, and the verdict comes back. All timing is the player's own stopwatch (see qte-model.js).
import { batch } from "@preact/signals";
import { closeKeyboard } from "./viewport.js";
import { qtes, you, comp, link, canWrite, activeAs, me, prefs, flash, toast, sheet } from "./state.js";
import { makeEntry, phaseAt, elapsedSeconds, canPress, verdictOf, byUrgency, TIMED_CMDS } from "./qte-model.js";
import { judge } from "./practice.js";
import { play, vibrate } from "./sound.js";

let sendFrame = () => {};
export const bindSender = (fn) => { sendFrame = fn; };

const GRACE_SEEN_MS = 120;           // a frozen screen is forgiven up to this much between "frame arrived" and "first painted"

// How long a frame took to get here: what the server measured, or half of our own typical round trip.
export function netMs() {
  const c = comp.value;
  if (c.net !== null && c.net !== undefined) return c.net;
  return (link.value.median || 0) / 2;
}

function replace(id, patch) {
  qtes.value = qtes.value.map((e) => (e.id === id ? { ...e, ...(typeof patch === "function" ? patch(e) : patch) } : e));
}
const find = (id) => qtes.value.find((e) => e.id === String(id));

function remove(id, delay) {
  setTimeout(() => { qtes.value = qtes.value.filter((e) => e.id !== id); }, delay);
}

export function startQte(frame, { practice = false, ago = 0 } = {}) {
  const id = String(frame.id);
  if (find(id)) return;
  const entry = makeEntry(frame, { arrival: performance.now(), net: practice ? 0 : netMs(), ago, youId: practice ? "practice" : you.value && you.value.id, practice });
  if (entry.role === null && !practice) {            // not for this player and nothing for them to do: keep it out of the way
    return;
  }
  qtes.value = [...qtes.value, entry];
  if (entry.role === "target") { sheet.value = null; closeKeyboard(); play("qte"); vibrate(40); }      // a QTE for you comes before anything else on screen (the phone's keyboard too)
  if (practice) {                                    // a practice QTE the player lets run out says so, as the real one would hurt
    setTimeout(() => {
      const open = find(id);
      if (open && !open.pressed) {
        settle(open, null, open.q.mode === "fake" ? { ok: true, label: "¡Era falso!", sub: "no caíste" } : { ok: false, label: "Se acabó el tiempo", sub: "no se pulsó nada" });
      }
    }, (frame.timeout || 5) * 1000 + 60);
  }
}

// A practice QTE the player let slip (a combo step whose time ran out, for one): it ends as a miss, as the real one would.
export function expirePractice(id, label = "Se acabó el tiempo", sub = "no se pulsó nada") {
  const open = find(id);
  if (open && open.practice && !open.pressed) settle(open, null, { ok: false, label, sub });
}

export function endQte(id) {
  const entry = find(id);
  if (!entry) return;
  if (entry.q.mode === "fake" && entry.role === "target" && !entry.pressed && !entry.result) {     // it ended and nobody fell for it
    const verdict = { ok: true, label: "¡Era falso!", sub: "no caíste" };
    replace(entry.id, { ended: true, endedAt: performance.now(), pressed: true, result: verdict });
    playVerdict(verdict);
    remove(entry.id, 1700);
    return;
  }
  replace(entry.id, { ended: true, endedAt: performance.now() });
  remove(entry.id, entry.pressed ? 1700 : 450);
}

export function clearQtes() {
  qtes.value = qtes.value.filter((e) => e.practice);       // a tutorial in progress keeps its practice
}

// First paint of a widget: from here on the player can see it.
export function markSeen(id) {
  const entry = find(id);
  if (!entry || entry.seen !== null) return;
  entry.seen = Math.min(performance.now(), entry.arrival + 1000);       // mutated on purpose: nothing needs to redraw for it
}

export function context() {
  const m = me.value;
  const now = performance.now();
  const left = (at) => (at ? Math.max(0, (at - now) / 1000) : 0);
  return {
    canWrite: canWrite.value || false,
    parryCooldown: m ? left(m.parryAt) : 0,
    saves: m && m.saves ? { left: m.saves.left, wait: left(m.saves.at), limit: m.saves.limit } : null,
    keepEvade: prefs.value.keepEvade,
  };
}

export function press(id, cmd, data = undefined) {
  const entry = find(id);
  if (!entry) return false;
  const now = performance.now();
  const t = elapsedSeconds(entry, now);
  const ctx = entry.practice ? { canWrite: true } : context();
  if (!canPress(entry, cmd, t, ctx)) return false;

  vibrate(18);
  if (entry.practice) {
    const res = judge(entry.q, cmd, t, { index: entry.step ? entry.step.index : 0, data });
    settle(entry, cmd, res, { ms: Math.round(t * 1000) });
    return true;
  }
  const seen = entry.seen === null ? entry.arrival : Math.min(entry.seen, entry.arrival + GRACE_SEEN_MS);
  const dt = Math.max(0, Math.round(now - seen));
  const combo = entry.q.mode === "combo";
  replace(entry.id, { pressed: !combo, busy: combo, pressedCmd: cmd, pressedAt: now });
  if (document.activeElement && document.activeElement.blur && document.activeElement.closest && document.activeElement.closest(".qw, .rescue-chip")) document.activeElement.blur();
  if (sendFrame({ t: "press", id: entry.id, command: cmd, as: activeAs.value, dt, ...(data ? { data } : {}) }) === false) {      // the socket is down: nothing was sent
    replace(entry.id, { pressed: false, busy: false, pressedCmd: null });
    toast("Sin conexión: no se envió. Se está reconectando…", "bad");
    return false;
  }
  return true;
}

// The verdict of a practice answer, or the server's for a real one.
function settle(entry, cmd, res, extra = {}) {
  const combo = entry.q.mode === "combo";
  const verdict = res.label ? { ok: res.ok, bf: res.bf, label: res.label, sub: res.sub || "", perfect: res.perfect } : verdictOf({ ...entry, pressedCmd: cmd }, res);
  if (combo && res.ok && !res.done) {
    // practice combo: move to the next step
    const index = (entry.step ? entry.step.index : 0) + 1;
    replace(entry.id, { step: { cmd: entry.q.combo.sequence[index], index, from: elapsedSeconds(entry, performance.now()) }, result: null, pressedCmd: cmd, pressed: false, busy: false });      // the next button comes back (a result would lock it)
    playVerdict(verdict);
    return;
  }
  replace(entry.id, { pressed: true, pressedCmd: cmd, result: verdict, busy: false, ms: extra.ms ?? res.ms });
  playVerdict(verdict);
  if (entry.practice) remove(entry.id, 1900);
}

function playVerdict(v) {
  if (v.bf) { play("bf"); flash("bf"); vibrate([30, 40, 60]); }
  else if (v.ok) play("ok");
  else if (v.ok === false) { play("bad"); vibrate([60, 40, 60]); }
}

// ---- frames from the server --------------------------------------------------------------------------------------
export function onResult(frame) {
  const entry = find(frame.id);
  if (!entry) return;
  const bf = (frame.reactions || []).includes("❗");
  const res = { ok: frame.ok, ms: frame.ms, bf, done: frame.done, why: frame.why };
  if (res.ok === null || res.ok === undefined) {                 // an answer the game did not judge (e.g. parry on cooldown): the buttons come back
    replace(entry.id, { pressed: false, busy: false, pressedCmd: null });
    return;
  }
  const verdict = verdictOf(entry, res);
  const combo = entry.q.mode === "combo";
  if (combo && res.ok) {                                          // the next step arrives as a `qte_step` frame
    replace(entry.id, { result: verdict, busy: true, ms: frame.ms });
    playVerdict(verdict);
    return;
  }
  replace(entry.id, { pressed: true, busy: false, result: verdict, ms: frame.ms });
  playVerdict(verdict);
}

export function onStep(frame) {
  const entry = find(frame.id);
  if (!entry) return;
  replace(entry.id, { step: { cmd: frame.step, index: frame.index, from: elapsedSeconds(entry, performance.now()) }, busy: false, pressed: false, result: null });
}

// The server refused or lost the answer: the buttons come back.
export function onPressError(id, reason) {
  const entry = find(id);
  if (!entry) return;
  replace(entry.id, { pressed: false, busy: false, pressedCmd: null });
  if (/terminó/.test(reason || "")) endQte(entry.id);
}

export { byUrgency, phaseAt, elapsedSeconds, TIMED_CMDS };
export const sendRaw = (frame) => sendFrame(frame);
export { batch, toast };
