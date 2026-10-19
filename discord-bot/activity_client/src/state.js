// The client's state: small signals the interface reads, and the few actions that change them.
import { signal, computed, batch } from "@preact/signals";
import { DEFAULT_PREFS, loadLocalPrefs } from "./prefs.js";

// ---- connection + who is who ----------------------------------------------------------------------------------
export const conn = signal({ state: "starting", text: "Conectando…", detail: "" });    // starting | connected | error
export const banner = signal(null);                    // { text, kind } shown under the top bar (reconnecting, errors)
export const you = signal(null);                       // { id, name, avatar }
export const perms = signal({ gm: false });
export const channelName = signal("Evento");
export const users = signal([]);                       // people inside the Activity
export const canWrite = signal(false);
export const version = signal("");

// ---- the mirrored channel -------------------------------------------------------------------------------------
export const messages = signal([]);

// ---- the game -------------------------------------------------------------------------------------------------
export const game = signal(null);                      // { boss, fight, players }
export const me = signal(null);                        // this player's private state, with countdowns as local times (see net.js)
export const characters = signal([]);
export const charAvatars = signal({});
export const activeAs = signal("me");
export const rules = signal(null);                     // the bot's QTE timings, for the tutorial's practice

// ---- timing ---------------------------------------------------------------------------------------------------
export const link = signal({ min: null, median: null, jitter: null, offset: 0, quality: "off", samples: 0 });
export const comp = signal({ net: null, device: 0, cap: 300 });       // what the server adds/removes from this player's answers
export const calib = signal(null);                     // result of the last latency test, as the server keeps it

// ---- settings -------------------------------------------------------------------------------------------------
export const prefs = signal(loadLocalPrefs());

// ---- QTEs on screen (see qte-store.js) -------------------------------------------------------------------------
export const qtes = signal([]);

// ---- navigation, overlays -------------------------------------------------------------------------------------
export const view = signal("event");                   // event | menu | settings | latency | training | help | profile ...
export const viewArgs = signal(null);
export const openTab = (tab) => { viewArgs.value = { tab }; };           // switch tab inside «Mi panel» (the page itself does not change)
export const sheet = signal(null);                     // "players" | null (bottom drawer on small screens)
export const tutorial = signal({ active: false, step: 0 });
export const pip = signal(false);                      // Discord shrank the Activity into a small floating window
export const toasts = signal([]);
export const fx = signal(null);                        // { kind: "hit" | "heal" | "bf", n }

// Pages remember where you came from, so Back (and Esc) returns there: gear -> settings -> back is the event again,
// menu -> settings -> back is the menu.
const trail = [];
export function go(name, args = null) {
  batch(() => {
    if (name === "event") trail.length = 0;
    else if (name !== view.value) { trail.push(view.value); if (trail.length > 8) trail.shift(); }
    view.value = name; viewArgs.value = args; sheet.value = null;
  });
}
export function back() {
  const previous = trail.pop() || "event";
  batch(() => { view.value = previous; viewArgs.value = null; sheet.value = null; });
}

let toastId = 0;
export function toast(text, kind = "info", ms = 3200) {
  const id = ++toastId;
  toasts.value = [...toasts.value.slice(-3), { id, text, kind }];
  setTimeout(() => { toasts.value = toasts.value.filter((t) => t.id !== id); }, ms);
}

let fxCount = 0;
export function flash(kind) {
  fx.value = { kind, n: ++fxCount };
}

// ---- derived --------------------------------------------------------------------------------------------------
export const myHp = computed(() => {
  const g = game.value, id = you.value && you.value.id;
  return g && id ? g.players.find((p) => p.id === id) || null : null;
});

export const activeCharacter = computed(() => (activeAs.value === "me" ? null : activeAs.value));

export const connected = computed(() => conn.value.state === "connected");

// ---- helpers for countdowns that the server sends as moments ----------------------------------------------------
// Each `me` frame carries `now` (the server clock when it was sent). A moment `until` on that clock becomes a local
// time: it arrives about `net` ms after it was sent, so that much of it is already gone.
export function localMoment(until, frameNow, arrival, netMs) {
  if (!until) return null;
  return arrival + (until - frameNow) - Math.max(0, netMs || 0);
}
export const secondsUntil = (localTime, nowMs = performance.now()) => (localTime ? Math.max(0, (localTime - nowMs) / 1000) : 0);

export function resetDefaults() {
  prefs.value = { ...DEFAULT_PREFS };
}
