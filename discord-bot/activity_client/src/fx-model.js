// Visual effects for powers and game events, as pure data: a binding says which preset plays, in what colour, how strong, how fast and how
// late; `expand` turns it into the list of pieces the screen draws. The server keeps and checks the bindings (eventos_app/activity/fx.py; the
// same rules are written here and compared by test/fx-cases.json). Nothing here touches the DOM.
import { clamp } from "./util.js";

// Every piece: t = when it starts (ms from the start), k = what it is, ms = how long it lasts, i = strength (0–1), c = colour (default the preset's).
export const PRESETS = {
  slash:     { label: "Corte",      color: "#e8f0ff", hint: "Un tajo en diagonal con un destello.",
               parts: [{ t: 0, k: "slash", ms: 380, a: -24 }, { t: 90, k: "flash", ms: 260, i: 0.35, c: "#ffffff" }, { t: 60, k: "shake", ms: 260, i: 0.5 }] },
  explosion: { label: "Explosión",  color: "#ff7a45", hint: "Destello, onda, chispas y temblor.",
               parts: [{ t: 0, k: "flash", ms: 420, i: 0.8 }, { t: 0, k: "ring", ms: 700 }, { t: 0, k: "burst", ms: 900, n: 22 }, { t: 0, k: "shake", ms: 520, i: 1 }] },
  rayo:      { label: "Rayo",       color: "#8fb4ff", hint: "Dos fogonazos y un temblor seco.",
               parts: [{ t: 0, k: "flash", ms: 140, i: 0.9, c: "#ffffff" }, { t: 170, k: "flash", ms: 300, i: 0.7 }, { t: 0, k: "shake", ms: 380, i: 0.8 }, { t: 0, k: "slash", ms: 260, a: 78 }] },
  curacion:  { label: "Curación",   color: "#34d399", hint: "Un resplandor suave y chispas que suben.",
               parts: [{ t: 0, k: "aura", ms: 1200 }, { t: 0, k: "burst", ms: 1400, n: 18, up: true }, { t: 0, k: "ring", ms: 900 }] },
  escudo:    { label: "Escudo",     color: "#60a5fa", hint: "Ondas que se expanden y un borde brillante.",
               parts: [{ t: 0, k: "ring", ms: 700 }, { t: 130, k: "ring", ms: 700 }, { t: 0, k: "aura", ms: 1400 }] },
  carga:     { label: "Carga",      color: "#fbbf24", hint: "Se concentra la energía y estalla.",
               parts: [{ t: 0, k: "vignette", ms: 900, i: 0.6, grow: true }, { t: 0, k: "aura", ms: 900 }, { t: 900, k: "flash", ms: 350, i: 0.8 }, { t: 900, k: "shake", ms: 420, i: 0.9 }, { t: 900, k: "ring", ms: 700 }] },
  dominio:   { label: "Dominio",    color: "#a78bfa", hint: "La pantalla se oscurece, se acerca y se rompe.",
               parts: [{ t: 0, k: "vignette", ms: 2400, i: 0.9, dark: true }, { t: 0, k: "zoom", ms: 1800, i: 0.6 }, { t: 200, k: "ring", ms: 1200 }, { t: 900, k: "flash", ms: 500, i: 0.7 }, { t: 900, k: "shake", ms: 600, i: 1 }] },
  impacto:   { label: "Impacto",    color: "#ff5d5d", hint: "Un golpe corto: destello y temblor.",
               parts: [{ t: 0, k: "flash", ms: 200, i: 0.5 }, { t: 0, k: "shake", ms: 300, i: 0.8 }] },
  pulso:     { label: "Pulso",      color: "#c084fc", hint: "Tres ondas seguidas.",
               parts: [{ t: 0, k: "ring", ms: 800 }, { t: 220, k: "ring", ms: 800 }, { t: 440, k: "ring", ms: 800 }] },
  ninguno:   { label: "Sin efecto visual", color: "#ffffff", hint: "Solo el sonido y el rótulo, si los hay.", parts: [] },
};
export const PRESET_IDS = Object.keys(PRESETS);

// What a power looks like when nobody chose: by the type the bot gives it.
export const DEFAULT_BY_TYPE = { destructive: "explosion", support: "curacion", defend: "escudo", build: "carga", control: "rayo" };

export const DEFAULT_BINDING = { preset: "impacto", color: "", intensity: 100, speed: 100, delay: 0, banner: "", name: false, sound: "", scope: "all" };
const RANGES = { intensity: [25, 200], speed: [50, 200], delay: [0, 5000] };
const COLOR = /^#[0-9a-fA-F]{6}$/;

// Same rules as the server: anything that does not fit falls back to the default; unknown keys are dropped.
export function sanitizeBinding(raw) {
  const out = { ...DEFAULT_BINDING };
  if (!raw || typeof raw !== "object") return out;
  if (PRESET_IDS.includes(raw.preset)) out.preset = raw.preset;
  if (typeof raw.color === "string" && COLOR.test(raw.color)) out.color = raw.color.toLowerCase();
  for (const [key, [lo, hi]] of Object.entries(RANGES)) {
    const v = raw[key];
    if (typeof v === "number" && Number.isFinite(v)) out[key] = Math.round(clamp(v, lo, hi));
  }
  if (typeof raw.banner === "string") out.banner = raw.banner.replace(/[\u0000-\u001f]/g, "").trim().slice(0, 40);
  if (typeof raw.name === "boolean") out.name = raw.name;
  if (typeof raw.sound === "string" && /^[0-9a-f]{1,32}$/.test(raw.sound)) out.sound = raw.sound;
  if (raw.scope === "all" || raw.scope === "target") out.scope = raw.scope;
  return out;
}

// Does it do anything at all?
export const isEmpty = (b) => b.preset === "ninguno" && !b.banner && !b.name && !b.sound;

// The pieces to draw, in order of time. `ctx.name` is the power's name for a banner that shows it. `calm`: no strobing or shaking (the player's setting).
export function expand(binding, ctx = {}, { calm = false } = {}) {
  const b = sanitizeBinding(binding);
  const preset = PRESETS[b.preset];
  const speed = b.speed / 100, strength = b.intensity / 100;
  const color = b.color || preset.color;
  const out = [];
  for (const p of preset.parts) {
    if (calm && (p.k === "shake" || p.k === "zoom")) continue;
    const piece = { ...p, t: Math.round(b.delay + p.t / speed), ms: Math.round(p.ms / speed), c: p.c || color };
    if (p.i !== undefined) piece.i = clamp(p.i * strength * (calm && p.k === "flash" ? 0.4 : 1), 0, 1);
    out.push(piece);
  }
  const text = b.banner || (b.name ? String(ctx.name || "").slice(0, 40) : "");
  if (text) out.push({ t: Math.round(b.delay), k: "banner", ms: Math.round(1700 / speed), text, c: color });
  return out.sort((a, c) => a.t - c.t);
}

// How long the whole thing takes (for the editor's "probar" and for cleanup).
export const lengthOf = (pieces) => pieces.reduce((end, p) => Math.max(end, p.t + p.ms), 0);
