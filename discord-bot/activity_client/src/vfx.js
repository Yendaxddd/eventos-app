// Draws the visual effects of powers and events on this screen (the presets and their timing are in fx-model.js). The pieces are small elements
// outside the page's own tree, animated with the browser and removed when they end, so nothing here makes the interface redraw.
import { prefs } from "./state.js";
import { expand, lengthOf } from "./fx-model.js";

let host = null;
const MAX_LIVE = 80;
export const vfxLog = [];                 // what was drawn (kind, at which ms): for tests and for looking around from the console

const surface = () => {
  if (!host || !host.isConnected) {
    host = document.createElement("div");
    host.className = "vfx-host";
    host.setAttribute("aria-hidden", "true");
    document.body.appendChild(host);
  }
  return host;
};

const root = () => document.getElementById("root");
const rand = (lo, hi) => lo + Math.random() * (hi - lo);

function add(className, style, keyframes, ms, easing = "ease-out") {
  const layer = surface();
  if (layer.childElementCount >= MAX_LIVE || typeof layer.animate !== "function") return null;
  const el = document.createElement("i");
  el.className = className;
  Object.assign(el.style, style);
  layer.appendChild(el);
  const anim = el.animate(keyframes, { duration: Math.max(30, ms), easing, fill: "forwards" });
  const done = () => el.remove();
  anim.onfinish = done; anim.oncancel = done;
  return el;
}

function shake(amount, ms) {
  const el = root();
  if (!el || typeof el.animate !== "function") return;
  const steps = Math.max(4, Math.round(ms / 45));
  const frames = [{ transform: "none" }];
  for (let i = 1; i < steps; i++) { const fade = 1 - i / steps; frames.push({ transform: `translate(${(rand(-1, 1) * amount * fade).toFixed(1)}px, ${(rand(-1, 1) * amount * 0.7 * fade).toFixed(1)}px)` }); }
  frames.push({ transform: "none" });
  el.animate(frames, { duration: ms, easing: "linear" });
}

function zoom(amount, ms) {
  const el = root();
  if (el && typeof el.animate === "function") el.animate([{ transform: "scale(1)" }, { transform: `scale(${1 + amount})` }, { transform: "scale(1)" }], { duration: ms, easing: "ease-in-out" });
}

const DRAW = {
  flash: (p) => add("vfx-flash", { background: p.c }, [{ opacity: p.i }, { opacity: 0 }], p.ms),
  vignette: (p) => add("vfx-vignette", { "--vc": p.dark ? "#000000" : p.c, "--vi": String(p.i) }, p.grow
    ? [{ opacity: 0, transform: "scale(1.4)" }, { opacity: 1, transform: "scale(1)" }]
    : [{ opacity: 0 }, { opacity: 1, offset: 0.2 }, { opacity: 1, offset: 0.7 }, { opacity: 0 }], p.ms, "ease-in-out"),
  ring: (p) => add("vfx-ring", { borderColor: p.c, boxShadow: `0 0 36px ${p.c}, inset 0 0 36px ${p.c}` }, [{ opacity: 0.9, transform: "translate(-50%, -50%) scale(0.1)" }, { opacity: 0, transform: "translate(-50%, -50%) scale(4.2)" }], p.ms),
  slash: (p) => add("vfx-slash", { background: `linear-gradient(90deg, transparent, ${p.c}, #ffffff, ${p.c}, transparent)`, "--a": `${p.a ?? -24}deg` },
    [{ opacity: 0, transform: "translate(-50%, -50%) rotate(var(--a)) scaleX(0.1)" }, { opacity: 1, transform: "translate(-50%, -50%) rotate(var(--a)) scaleX(1)", offset: 0.35 }, { opacity: 0, transform: "translate(-50%, -50%) rotate(var(--a)) scaleX(1.15)" }], p.ms),
  aura: (p) => add("vfx-aura", { boxShadow: `inset 0 0 90px 18px ${p.c}` }, [{ opacity: 0 }, { opacity: 0.85, offset: 0.3 }, { opacity: 0 }], p.ms, "ease-in-out"),
  zoom: (p) => { zoom(0.05 * (p.i ?? 0.6), p.ms); return null; },
  shake: (p) => { shake(14 * (p.i ?? 0.7), p.ms); return null; },
  burst: (p) => {
    for (let n = 0; n < (p.n || 16); n++) {
      const angle = p.up ? rand(-Math.PI * 0.85, -Math.PI * 0.15) : rand(0, Math.PI * 2);
      const far = rand(160, 460), size = rand(5, 13);
      add("vfx-spark", { background: p.c, width: `${size}px`, height: `${size}px`, boxShadow: `0 0 12px ${p.c}` },
        [{ opacity: 1, transform: "translate(-50%, -50%) scale(1)" }, { opacity: 0, transform: `translate(calc(-50% + ${Math.cos(angle) * far}px), calc(-50% + ${Math.sin(angle) * far}px)) scale(0.2)` }], p.ms * rand(0.6, 1));
    }
    return null;
  },
  banner: (p) => {
    const el = add("vfx-banner", { color: p.c }, [{ opacity: 0, transform: "translate(-50%, -30%) scale(0.85)", letterSpacing: "0.4em" }, { opacity: 1, transform: "translate(-50%, -50%) scale(1)", letterSpacing: "0.12em", offset: 0.18 },
      { opacity: 1, transform: "translate(-50%, -50%) scale(1.03)", offset: 0.78 }, { opacity: 0, transform: "translate(-50%, -60%) scale(1.08)" }], p.ms, "ease-out");
    if (el) el.textContent = p.text;
    return el;
  },
};

// Play an effect binding now. `force`: ignore the player's «Efectos visuales: apagados» (the editor's preview, which they asked for).
export function playBinding(binding, ctx = {}, { force = false } = {}) {
  const mode = prefs.value.vfx || "full";
  if (mode === "off" && !force) return 0;
  const calm = mode === "soft" || prefs.value.motion === "reduced";
  const pieces = expand(binding, ctx, { calm });
  for (const p of pieces) {
    setTimeout(() => {
      try {
        vfxLog.push({ k: p.k, t: p.t, at: Math.round(performance.now()) });
        if (vfxLog.length > 200) vfxLog.shift();
        const draw = DRAW[p.k];
        if (draw) draw(p);
      } catch { /* a missing effect must never break the game screen */ }
    }, p.t);
  }
  return lengthOf(pieces);
}
