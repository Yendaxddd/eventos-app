// Changing a setting: it applies at once, is remembered in this browser, and is sent to the server a moment later
// so it follows the player to their other devices.
import { prefs } from "./state.js";
import { DEFAULT_PREFS, sanitizePrefs, saveLocalPrefs } from "./prefs.js";
import { send } from "./net.js";

let timer = null;

function persist() {
  saveLocalPrefs(prefs.value);
  clearTimeout(timer);
  timer = setTimeout(() => send({ t: "prefs", prefs: prefs.value }), 700);
}

export function setPrefs(patch) {
  prefs.value = sanitizePrefs({ ...prefs.value, ...patch });
  persist();
}

export function resetPrefs() {
  prefs.value = { ...DEFAULT_PREFS, tutorialDone: prefs.value.tutorialDone };
  persist();
}
