// Per-player display settings. The server keeps them for each person (so they follow them from phone to PC) and the
// browser keeps a copy so the look is right before the connection is up.
import { clamp, store } from "./util.js";

export const DEFAULT_PREFS = {
  theme: "dark",            // dark | oled | contrast | midnight | ember | forest | rose | sepia
  accent: "violet",         // violet | blue | cyan | green | amber | pink | red
  corners: "round",         // round | sharp | soft
  bg: "plain",              // plain | grid | aurora
  palette: "default",       // default | cb (colour-blind friendly)
  textScale: 100,           // 85 – 140 (%)
  density: "comfortable",   // compact | comfortable | spacious
  motion: "full",           // full | reduced
  vfx: "full",              // visual effects of powers and events: full | soft (no shaking, gentle flashes) | off
  buttonScale: 100,         // size of the floating QTE buttons, 70 – 160 (%)
  buttonPlacement: "random",// random | bottom | left | right
  keepEvade: false,         // keep a small Evade button while the parry window is open
  queueMode: false,         // show only the most urgent QTE and queue the rest
  sound: true, volume: 60,  // the little sounds of the interface (QTE arrives, verdicts) and their volume
  cinema: true,             // show the cinematics the game masters play (off: only their sound, no overlay)
  audio: true, musicVolume: 70, sfxVolume: 85,   // the event's own sound: music and the sounds the game masters play or bind to events
  haptics: true,
  showAvatars: true, showMedia: true, showTimestamps: true,
  showPlayers: true, compactHud: false,
  messageLimit: 150,        // messages kept on screen, 50 – 400
  tutorialDone: false,
  screenTop: 0, screenBottom: 0, screenSide: 0,      // extra margins (px) for a screen the page does not fit exactly
  accentColor: "#8b5cf6", baseColor: "#0b0b16",       // the colours of the «custom» accent and theme
  font: "tech",             // titles' typeface: tech | clean | serif | mono
  surface: "solid",         // how panels are drawn: solid | glass | outline
  arrange: "classic",       // the event screen: classic | mirror | focus | compact
  followEvent: true,        // take the look the game masters chose for the event (until the player picks their own)
};

export const THEMES = ["dark", "oled", "contrast", "midnight", "ember", "forest", "rose", "sepia", "slate", "ocean", "light", "paper", "custom"];
export const ACCENTS = ["violet", "blue", "cyan", "teal", "green", "gold", "amber", "pink", "red", "custom"];
const CHOICES = {
  theme: THEMES,
  accent: ACCENTS, corners: ["round", "sharp", "soft"], bg: ["plain", "grid", "dots", "aurora", "glow"], palette: ["default", "cb"], density: ["compact", "comfortable", "spacious"],
  font: ["tech", "clean", "serif", "mono"], surface: ["solid", "glass", "outline"], arrange: ["classic", "mirror", "focus", "compact"],
  motion: ["full", "reduced"], vfx: ["full", "soft", "off"], buttonPlacement: ["random", "bottom", "left", "right"],
};
const RANGES = { textScale: [85, 140], buttonScale: [70, 160], volume: [0, 100], musicVolume: [0, 100], sfxVolume: [0, 100], messageLimit: [50, 400], screenTop: [0, 80], screenBottom: [0, 80], screenSide: [0, 60] };

// Same rules as the server (eventos_app/activity/prefs.py): anything that does not fit falls back to the default.
export function sanitizePrefs(raw) {
  const out = { ...DEFAULT_PREFS };
  if (!raw || typeof raw !== "object") return out;
  for (const [key, def] of Object.entries(DEFAULT_PREFS)) {
    if (!(key in raw)) continue;
    const v = raw[key];
    if (key in CHOICES) { if (CHOICES[key].includes(v)) out[key] = v; }
    else if (key === "accentColor" || key === "baseColor") { if (typeof v === "string" && /^#[0-9a-fA-F]{6}$/.test(v)) out[key] = v.toLowerCase(); }
    else if (key in RANGES) { if (typeof v === "number" && Number.isFinite(v)) out[key] = Math.round(clamp(v, ...RANGES[key])); }
    else if (typeof def === "boolean") out[key] = Boolean(v);
  }
  return out;
}

const THEME_COLOR = { dark: "#090912", oled: "#000000", contrast: "#000000", midnight: "#060a16", ember: "#120a08", forest: "#07110c", rose: "#130910", sepia: "#15110b",
  slate: "#0d0f13", ocean: "#04121a", light: "#f3f4f8", paper: "#f4efe6" };
const LIGHT = new Set(["light", "paper"]);

// How light a colour is (0 black – 1 white), to know whether text over it should be dark or light.
export function luminance(hex) {
  const n = parseInt(String(hex).slice(1), 16);
  if (!Number.isFinite(n)) return 0;
  const lin = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
}

// The look the game masters chose for the event: a player who follows it sees it instead of their own.
export const LOOK_KEYS = ["theme", "accent", "accentColor", "baseColor", "corners", "bg", "font", "surface"];
export function effectivePrefs(p, eventLook = null) {
  if (!p.followEvent || !eventLook || typeof eventLook !== "object") return p;
  const out = { ...p };
  const clean = sanitizePrefs({ ...p, ...eventLook });
  for (const k of LOOK_KEYS) out[k] = clean[k];
  return out;
}
const DENSITY = { compact: 0.82, comfortable: 1, spacious: 1.28 };

export function applyPrefs(own, eventLook = null) {
  const p = effectivePrefs(own, eventLook);
  const root = document.documentElement;
  root.dataset.theme = p.theme;
  root.dataset.mode = p.theme === "custom" ? (luminance(p.baseColor) > 0.35 ? "light" : "dark") : LIGHT.has(p.theme) ? "light" : "dark";
  root.dataset.font = p.font;
  root.dataset.surface = p.surface;
  root.dataset.arrange = p.arrange;
  if (p.theme === "custom") root.style.setProperty("--c-base", p.baseColor); else root.style.removeProperty("--c-base");
  if (p.accent === "custom") {
    root.style.setProperty("--c-accent", p.accentColor);
    root.style.setProperty("--c-on-accent", luminance(p.accentColor) > 0.45 ? "#111118" : "#ffffff");
  } else { root.style.removeProperty("--c-accent"); root.style.removeProperty("--c-on-accent"); }
  root.dataset.palette = p.palette;
  root.dataset.accent = p.accent;
  root.dataset.corners = p.corners;
  root.dataset.bg = p.bg;
  root.dataset.motion = p.motion;
  root.style.setProperty("--text-scale", String(p.textScale / 100));
  root.style.setProperty("--density", String(DENSITY[p.density] || 1));
  root.style.setProperty("--btn-scale", String(p.buttonScale / 100));
  root.style.setProperty("--adj-top", `${p.screenTop}px`);
  root.style.setProperty("--adj-bottom", `${p.screenBottom}px`);
  root.style.setProperty("--adj-side", `${p.screenSide}px`);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", p.theme === "custom" ? p.baseColor : THEME_COLOR[p.theme] || "#090912");
}

export const loadLocalPrefs = () => sanitizePrefs(store.json("eventos.prefs", null));
export const saveLocalPrefs = (p) => store.set("eventos.prefs", JSON.stringify(p));
