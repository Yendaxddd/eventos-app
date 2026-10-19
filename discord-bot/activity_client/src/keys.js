// Keyboard shortcuts. The letter keys do nothing while typing in a box (Alt + the letter still works there).
import { qtes, view, back, sheet } from "./state.js";
import { byUrgency, canPress, elapsedSeconds, phaseAt } from "./qte-model.js";
import { context, press } from "./qte-store.js";
import { pressCommand } from "./ui/Actions.jsx";

const MAP = {
  KeyE: "evade", KeyP: "parry", KeyS: "save", KeyA: "adapt", KeyQ: "attack", Digit1: "power1", Digit2: "power2", Digit3: "domain",
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Space: "lead",
};
const TIMED = new Set(["evade", "parry", "save", "up", "down", "left", "right"]);

function pickEntry(cmd) {
  const now = performance.now();
  const ctx = context();
  const wanted = cmd === "save" ? "rescuer" : "target";
  const list = byUrgency(qtes.value.filter((e) => e.role === wanted), now);
  return list.find((e) => canPress(e, cmd, elapsedSeconds(e, now), { ...ctx, canWrite: e.practice ? true : ctx.canWrite }));
}

export function installKeys() {
  document.addEventListener("keydown", (event) => {
    if (event.repeat || event.ctrlKey || event.metaKey) return;
    const target = event.target;
    const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
    if (event.key === "Escape") {
      if (typing) { target.blur(); return; }
      if (sheet.value) { sheet.value = null; return; }
      if (view.value !== "event") back();
      return;
    }
    if (typing && !event.altKey) return;
    let cmd = MAP[event.code];
    if (!cmd) return;
    if (cmd === "lead") {                                     // Space: whatever the most urgent QTE needs right now
      const now = performance.now();
      const lead = byUrgency(qtes.value.filter((e) => e.role === "target" && !e.pressed && !e.ended), now)[0];
      if (!lead) return;
      const phase = phaseAt(lead, elapsedSeconds(lead, now));
      if (phase.state !== "live" || phase.cmd === "arrows") return;
      cmd = phase.cmd;
    }
    if (TIMED.has(cmd)) {
      const entry = pickEntry(cmd);
      if (entry) { event.preventDefault(); press(entry.id, cmd); }
    } else if (!typing || event.altKey) {
      event.preventDefault();
      pressCommand(cmd);
    }
  });
}
