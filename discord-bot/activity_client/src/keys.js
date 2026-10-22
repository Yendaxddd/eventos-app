// Keyboard shortcuts. The letter keys do nothing while typing in a box (Alt + the letter still works there).
import { qtes, view, back, sheet } from "./state.js";
import { GESTURE_MODES, byUrgency, canPress, elapsedSeconds, leadOf, phaseAt } from "./qte-model.js";
import { context, press } from "./qte-store.js";
import { pressCommand } from "./ui/Actions.jsx";

const MAP = {
  KeyE: "evade", KeyP: "parry", KeyS: "save", KeyA: "adapt", KeyQ: "attack", Digit1: "power1", Digit2: "power2", Digit3: "domain",
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Space: "lead",
};
const TIMED = new Set(["evade", "parry", "save", "up", "down", "left", "right"]);

// A key answers ONE QTE: the lead (see leadOf), or for a rescue the most urgent one. If the lead cannot take that button the key does
// nothing: it never falls through to another QTE (that is how one key used to answer several at once).
function pickEntry(cmd) {
  const now = performance.now();
  const ctx = context();
  const can = (e) => canPress(e, cmd, elapsedSeconds(e, now), { ...ctx, canWrite: e.practice ? true : ctx.canWrite });
  if (cmd === "save") return byUrgency(qtes.value.filter((e) => e.role === "rescuer"), now).find(can) || null;
  const lead = leadOf(qtes.value, now);
  return lead && can(lead) ? lead : null;
}

// On a Mac, Option + a letter writes a character (ñ, ´, ∑...): while typing, it only works as a shortcut for a QTE that is running.
const MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

export function installKeys() {
  document.addEventListener("keydown", (event) => {
    if (event.repeat || event.ctrlKey || event.metaKey) return;
    const target = event.target;
    const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
    if (event.key === "Escape") {
      if (document.querySelector(".modal-card")) return;      // a dialog closes itself with Escape: it must not also leave the page behind it
      if (typing) { target.blur(); return; }
      if (sheet.value) { sheet.value = null; return; }
      if (view.value !== "event") back();
      return;
    }
    if (typing && !event.altKey) return;
    if (target && target.tagName === "BUTTON" && (event.code === "Space" || event.code === "Enter")) return;      // a focused button answers for itself
    let cmd = MAP[event.code];
    if (!cmd) return;
    const leading = leadOf(qtes.value, performance.now());
    if (leading && GESTURE_MODES.includes(leading.q.mode) && (TIMED.has(cmd) || cmd === "lead")) return;      // its widget reads the keys
    if (cmd === "lead") {                                     // Space: whatever the most urgent QTE needs right now
      const now = performance.now();
      const lead = leadOf(qtes.value, now);
      if (!lead) return;
      const phase = phaseAt(lead, elapsedSeconds(lead, now));
      if (phase.state !== "live" || phase.cmd === "arrows") return;
      cmd = phase.cmd;
    }
    if (TIMED.has(cmd)) {
      const entry = pickEntry(cmd);
      if (entry) { event.preventDefault(); press(entry.id, cmd); }
    } else if (!typing || (event.altKey && !MAC)) {
      event.preventDefault();
      pressCommand(cmd);
    }
  });
}
