// Words and small formatting for the dashboards. Pure, so it is tested without a browser.

export const RARITY = {
  common: { label: "Común", color: "#9ca3af" }, uncommon: { label: "Poco común", color: "#34d399" }, rare: { label: "Raro", color: "#60a5fa" },
  epic: { label: "Épico", color: "#c084fc" }, legendary: { label: "Legendario", color: "#fb923c" }, mythic: { label: "Mítico", color: "#fb7185" },
};
export const rarityOf = (key) => RARITY[key] || { label: key ? key[0].toUpperCase() + key.slice(1) : "Común", color: "#9ca3af" };

export const OBJECT_TYPE = { adaptation: "Adaptación", passive: "Pasivo", triggered: "Activable", consumable: "Consumible" };
export const POWER_TYPE = { destructive: "Destructivo", support: "Apoyo", defend: "Defensa", build: "Construcción", control: "Control" };
export const DOMAIN_TYPE = {
  simple: "Simple", pachinko: "Azar", reflect: "Reflejo", dps: "Daño continuo", cursed_partners: "Compañeros", court_trial: "Tribunal", soul_manipulator: "Alma",
};
export const TRACK_LABEL = { total: "Total", easy: "Fácil", medium: "Media", hard: "Difícil", impossible: "Imposible" };

export const BOARD = [
  ["success_rate", "Aciertos", "% de QTE acertados"], ["black_flashes", "Black Flash", "Black Flash conseguidos"], ["parry_streak", "Racha de parry", "Mejor racha de parries"],
  ["total_attempts", "Intentos", "QTE intentados"], ["best_time", "Mejor tiempo", "Respuesta más rápida"], ["saves", "Rescates", "Compañeros rescatados"],
];

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

// 45 -> "45 s", 200 -> "3 min 20 s", 3900 -> "1 h 5 min"
export function duration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  if (s < 60) return `${s} s`;
  if (s < 3600) return s % 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 60)} min`;
  const m = Math.floor((s % 3600) / 60);
  return m ? `${Math.floor(s / 3600)} h ${m} min` : `${Math.floor(s / 3600)} h`;
}

export const decimal = (n, digits = 1) => Number(n).toFixed(digits).replace(".", ",");

// what a game master typed in a number field → a number (a comma works as the decimal point), or null while it is empty or not a number
export function parseNumber(text) {
  const clean = String(text ?? "").trim().replace(",", ".");
  if (clean === "") return null;
  const n = Number(clean);
  return Number.isFinite(n) ? n : null;
}
export const num = (n) => String(Math.round(Number(n) * 100) / 100).replace(".", ",");      // 0.2 -> "0,2", 10 -> "10"

// ---- a power's effect: "damage:50" <-> { kind: "damage", a: 50 } ---------------------------------------------------
export const EFFECT_KINDS = [["damage", "Daño al jefe"], ["heal", "Curación"], ["stun", "Aturdir al jefe"], ["custom", "Avanzado"]];
const BUFF_NAME = { damage_boost: "daño", bf_boost: "probabilidad de Black Flash", attack: "ataque" };

export function parseEffect(effect) {
  const text = String(effect || "").trim();
  let m;
  if ((m = /^(damage|heal):(\d{1,6})$/i.exec(text))) return { kind: m[1].toLowerCase(), a: Number(m[2]) };
  if (/^stun$/i.test(text)) return { kind: "stun" };
  if ((m = /^buff:([a-z_]{1,24})(?::(\d{1,4}(?:\.\d{1,2})?))?(?::(\d{1,4}(?:\.\d{1,2})?))?$/i.exec(text))) {
    return { kind: "buff", name: m[1].toLowerCase(), a: m[2] === undefined ? 0.1 : Number(m[2]), b: m[3] === undefined ? 30 : Number(m[3]) };
  }
  return { kind: "custom", text };
}

export function buildEffect(e) {
  switch (e.kind) {
    case "damage": return `damage:${Math.max(0, Math.round(Number(e.a) || 0))}`;
    case "heal": return `heal:${Math.max(0, Math.round(Number(e.a) || 0))}`;
    case "stun": return "stun";
    case "buff": return `buff:${String(e.name || "ataque").toLowerCase().replace(/[^a-z_]/g, "") || "ataque"}:${Number(e.a) || 0}:${Number(e.b) || 0}`;
    default: return String(e.text || "").trim();
  }
}

export function effectLabel(effect) {
  const e = parseEffect(effect);
  switch (e.kind) {
    case "damage": return `Daño ${e.a}`;
    case "heal": return `Curación ${e.a}`;
    case "stun": return "Aturde al jefe";
    case "buff": return `Mejora (${BUFF_NAME[e.name] || e.name}): ${num(e.a)} durante ${duration(e.b)}`;
    default: return e.text || "—";
  }
}

// ---- the chart of response times ---------------------------------------------------------------------------------------
// points of a polyline for `values` (seconds, oldest first) inside w x h; faster answers are higher
export function chartPoints(values, w, h, pad = 4) {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length < 2) return { points: [], min: null, max: null };
  const min = Math.min(...v), max = Math.max(...v);
  const span = Math.max(0.001, max - min);
  const points = v.map((x, i) => [pad + (i / (v.length - 1)) * (w - 2 * pad), pad + ((x - min) / span) * (h - 2 * pad)]);
  return { points: points.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]), min, max };
}

// ---- tree: connect each skill to the ones it needs --------------------------------------------------------------------
// skills grouped by tier, in order: [[tier1 skills], [tier2 skills]...]
export function tiersOf(skills) {
  const map = new Map();
  for (const s of skills) {
    if (!map.has(s.tier)) map.set(s.tier, []);
    map.get(s.tier).push(s);
  }
  return [...map.keys()].sort((a, b) => a - b).map((t) => map.get(t));
}

// the sentence under a skill's button
export function skillStatus(s, points) {
  if (s.state === "maxed") return "Al máximo";
  if (s.state === "locked") return `Necesitas: ${s.needs.filter((n) => !n.met).map((n) => n.name).join(", ")}`;
  if (s.state === "poor") return `Cuesta ${s.cost}; te faltan ${s.cost - points}`;
  return `Aprender · cuesta ${s.cost}`;
}

// A colour from the game's data that can be seen on the dark interface: a nearly black one is replaced by `fallback`.
export function readable(color, fallback) {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(color || "").trim());
  if (!m) return fallback;
  const hex = (m[1].length === 3 ? m[1].split("").map((c) => c + c).join("") : m[1]).toLowerCase();
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const luminance = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  return luminance < 0.06 ? fallback : `#${hex}`;
}
