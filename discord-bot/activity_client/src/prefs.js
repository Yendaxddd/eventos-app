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
};

const CHOICES = {
  theme: ["dark", "oled", "contrast", "midnight", "ember", "forest", "rose", "sepia"],
  accent: ["violet", "blue", "cyan", "green", "amber", "pink", "red"], corners: ["round", "sharp", "soft"], bg: ["plain", "grid", "aurora"], palette: ["default", "cb"], density: ["compact", "comfortable", "spacious"],
  motion: ["full", "reduced"], vfx: ["full", "soft", "off"], buttonPlacement: ["random", "bottom", "left", "right"],
};
const RANGES = { textScale: [85, 140], buttonScale: [70, 160], volume: [0, 100], musicVolume: [0, 100], sfxVolume: [0, 100], messageLimit: [50, 400] };

// Same rules as the server (eventos_app/activity/prefs.py): anything that does not fit falls back to the default.
export function sanitizePrefs(raw) {
  const out = { ...DEFAULT_PREFS };
  if (!raw || typeof raw !== "object") return out;
  for (const [key, def] of Object.entries(DEFAULT_PREFS)) {
    if (!(key in raw)) continue;
    const v = raw[key];
    if (key in CHOICES) { if (CHOICES[key].includes(v)) out[key] = v; }
    else if (key in RANGES) { if (typeof v === "number" && Number.isFinite(v)) out[key] = Math.round(clamp(v, ...RANGES[key])); }
    else if (typeof def === "boolean") out[key] = Boolean(v);
  }
  return out;
}

const THEME_COLOR = { dark: "#090912", oled: "#000000", contrast: "#000000", midnight: "#060a16", ember: "#120a08", forest: "#07110c", rose: "#130910", sepia: "#15110b" };
const DENSITY = { compact: 0.82, comfortable: 1, spacious: 1.28 };

export function applyPrefs(p) {
  const root = document.documentElement;
  root.dataset.theme = p.theme;
  root.dataset.palette = p.palette;
  root.dataset.accent = p.accent;
  root.dataset.corners = p.corners;
  root.dataset.bg = p.bg;
  root.dataset.motion = p.motion;
  root.style.setProperty("--text-scale", String(p.textScale / 100));
  root.style.setProperty("--density", String(DENSITY[p.density] || 1));
  root.style.setProperty("--btn-scale", String(p.buttonScale / 100));
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", THEME_COLOR[p.theme] || "#090912");
}

export const loadLocalPrefs = () => sanitizePrefs(store.json("eventos.prefs", null));
export const saveLocalPrefs = (p) => store.set("eventos.prefs", JSON.stringify(p));
