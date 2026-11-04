// The looks of the Activity: ready-made styles (a theme, an accent, corners, a background, a typeface and a way of drawing panels that go
// together), and the colours each theme and accent show in a small preview. Pure data, tested without a browser.

export const LOOK_KEYS = ["theme", "accent", "accentColor", "baseColor", "corners", "bg", "font", "surface"];

// [id, name, one line, the look]
export const STYLES = [
  ["eventos", "Eventos", "Tinta violeta con aurora: el de siempre.", { theme: "dark", accent: "violet", corners: "round", bg: "aurora", font: "tech", surface: "solid" }],
  ["pro", "Profesional", "Gris neutro y azul, sin adornos.", { theme: "slate", accent: "blue", corners: "round", bg: "plain", font: "clean", surface: "solid" }],
  ["tactico", "Táctico", "Medianoche, cian y cuadrícula. Esquinas rectas.", { theme: "midnight", accent: "cyan", corners: "sharp", bg: "grid", font: "mono", surface: "solid" }],
  ["cristal", "Cristal", "Paneles translúcidos sobre un océano.", { theme: "ocean", accent: "teal", corners: "soft", bg: "aurora", font: "clean", surface: "glass" }],
  ["brasa", "Brasa", "Cálido, con un brillo de fuego abajo.", { theme: "ember", accent: "amber", corners: "round", bg: "glow", font: "tech", surface: "solid" }],
  ["bosque", "Bosque", "Verdes tranquilos y puntos suaves.", { theme: "forest", accent: "green", corners: "soft", bg: "dots", font: "clean", surface: "solid" }],
  ["sakura", "Sakura", "Rosa y violeta, cristal y aurora.", { theme: "rose", accent: "pink", corners: "soft", bg: "aurora", font: "clean", surface: "glass" }],
  ["neon", "Neón", "Negro puro, líneas de neón.", { theme: "oled", accent: "pink", corners: "sharp", bg: "grid", font: "tech", surface: "outline" }],
  ["pergamino", "Pergamino", "Sepia y oro, letra de libro.", { theme: "sepia", accent: "gold", corners: "sharp", bg: "plain", font: "serif", surface: "outline" }],
  ["claro", "Claro", "Fondo blanco para días de sol.", { theme: "light", accent: "violet", corners: "round", bg: "dots", font: "clean", surface: "solid" }],
  ["papel", "Papel", "Crema y rojo, como una novela.", { theme: "paper", accent: "red", corners: "sharp", bg: "plain", font: "serif", surface: "outline" }],
  ["contraste", "Alto contraste", "Lo más legible posible.", { theme: "contrast", accent: "gold", corners: "round", bg: "plain", font: "clean", surface: "solid" }],
].map(([id, name, hint, look]) => ({ id, name, hint, look }));

// What a theme looks like in a preview: [background, panel, raised, line, text, faint text]
export const THEME_SWATCH = {
  dark: ["#090912", "#13131f", "#1a1a2a", "#2a2a42", "#ecebf8", "#75749a"],
  oled: ["#000000", "#0a0a10", "#11111a", "#20203a", "#ecebf8", "#75749a"],
  contrast: ["#000000", "#0d0d12", "#15151c", "#5a5a78", "#ffffff", "#b8b7d4"],
  midnight: ["#060a16", "#0e172b", "#14203a", "#243558", "#ecebf8", "#6f80a8"],
  ember: ["#120a08", "#231510", "#2e1c15", "#4a2f23", "#f6ebe4", "#957a6b"],
  forest: ["#07110c", "#10241a", "#163024", "#264a39", "#e8f5ee", "#6d9380"],
  rose: ["#130910", "#25121f", "#311a2a", "#4d2a41", "#f9eaf2", "#9a738a"],
  sepia: ["#15110b", "#261f15", "#32291c", "#4d4030", "#f3ead9", "#8f8269"],
  slate: ["#0d0f13", "#171a21", "#1e222b", "#2c323e", "#eceff4", "#6f7889"],
  ocean: ["#04121a", "#0b2230", "#102c3d", "#1d4258", "#e6f6fb", "#648a9a"],
  light: ["#eef0f5", "#ffffff", "#f6f7fa", "#d4d8e2", "#15171e", "#7d8494"],
  paper: ["#efe8dc", "#fbf8f2", "#f5f0e6", "#d6cbb6", "#2a2218", "#8a7d69"],
};
export const THEME_NAMES = {
  dark: "Tinta", oled: "Negro puro", contrast: "Alto contraste", midnight: "Medianoche", ember: "Brasa", forest: "Bosque", rose: "Rosa", sepia: "Sepia",
  slate: "Pizarra", ocean: "Océano", light: "Claro", paper: "Papel", custom: "Mi color",
};
// [main, partner]
export const ACCENT_SWATCH = {
  violet: ["#8b5cf6", "#ec4899"], blue: ["#3b82f6", "#22d3ee"], cyan: ["#06b6d4", "#34d399"], teal: ["#14b8a6", "#3b82f6"], green: ["#22c55e", "#14b8a6"],
  gold: ["#eab308", "#f97316"], amber: ["#f59e0b", "#ef4444"], pink: ["#ec4899", "#8b5cf6"], red: ["#ef4444", "#f59e0b"],
};
export const ACCENT_NAMES = { violet: "Violeta", blue: "Azul", cyan: "Cian", teal: "Turquesa", green: "Verde", gold: "Oro", amber: "Ámbar", pink: "Rosa", red: "Rojo", custom: "Mi color" };

// The colours to draw a look with, also for «custom» theme and accent.
export function swatchOf(look) {
  const t = look.theme === "custom" ? customSwatch(look.baseColor || "#0b0b16") : THEME_SWATCH[look.theme] || THEME_SWATCH.dark;
  const a = look.accent === "custom" ? [look.accentColor || "#8b5cf6", look.accentColor || "#8b5cf6"] : ACCENT_SWATCH[look.accent] || ACCENT_SWATCH.violet;
  return { bg: t[0], panel: t[1], raised: t[2], line: t[3], text: t[4], faint: t[5], accent: a[0], partner: a[1] };
}

function mix(hex, toward, amount) {
  const a = parseInt(hex.slice(1), 16), b = parseInt(toward.slice(1), 16);
  const ch = (n, s) => (n >> s) & 255;
  const m = (s) => Math.round(ch(a, s) + (ch(b, s) - ch(a, s)) * amount).toString(16).padStart(2, "0");
  return `#${m(16)}${m(8)}${m(0)}`;
}
function light(hex) {
  const n = parseInt(hex.slice(1), 16);
  return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255 > 0.6;
}
export function customSwatch(base) {
  const to = light(base) ? "#000000" : "#ffffff";
  return [base, light(base) ? mix(base, "#ffffff", 0.55) : mix(base, to, 0.06), mix(base, to, 0.1), mix(base, to, 0.18), mix(base, to, 0.92), mix(base, to, 0.46)];
}

// Which ready-made style these settings are exactly (custom colours never are one).
export function styleOf(prefs) {
  const found = STYLES.find((s) => Object.entries(s.look).every(([k, v]) => prefs[k] === v));
  return found ? found.id : null;
}

// The event screen's arrangements: [id, name, one line]
export const ARRANGEMENTS = [
  ["classic", "Clásica", "Equipo a la izquierda, chat en el centro y tu personaje a la derecha."],
  ["mirror", "Espejo", "Tu personaje a la izquierda y el equipo a la derecha (cómodo para zurdos)."],
  ["focus", "Enfoque", "Solo el chat en el centro, con tu barra y tus botones abajo, como en el móvil."],
  ["compact", "Compacta", "Columnas estrechas para pantallas pequeñas o ventanas a medias."],
].map(([id, name, hint]) => ({ id, name, hint }));
