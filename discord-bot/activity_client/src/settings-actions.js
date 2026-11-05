// Changing a setting: it applies at once, is remembered in this browser, and is sent to the server a moment later
// so it follows the player to their other devices.
import { prefs } from "./state.js";
import { DEFAULT_PREFS, sanitizePrefs, saveLocalPrefs } from "./prefs.js";
import { send } from "./net.js";

let timer = null;
let unsent = false;                // changed while the server could not hear it: the next welcome must not undo it

export const prefsUnsent = () => unsent;

function persist() {
  saveLocalPrefs(prefs.value);
  clearTimeout(timer);
  unsent = true;
  timer = setTimeout(() => { if (send({ t: "prefs", prefs: prefs.value })) unsent = false; }, 700);
}

// After a reconnection: what was changed meanwhile goes up now (and the server's older copy is not taken).
export function flushPrefs() {
  if (!unsent) return false;
  clearTimeout(timer);
  if (send({ t: "prefs", prefs: prefs.value })) unsent = false;
  return true;
}

export function setPrefs(patch) {
  prefs.value = sanitizePrefs({ ...prefs.value, ...patch });
  persist();
}

export function resetPrefs() {
  prefs.value = { ...DEFAULT_PREFS, tutorialDone: prefs.value.tutorialDone };
  persist();
}
