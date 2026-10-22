// The power builder's rules: the same effect language as the bot (eventos_app/powers.py), read and written here so the form can show
// what a power will really do, with this player's weapon and boosts, before it is saved. Pure functions (tested without a browser).

// kind -> [label, fields: [[key, label, unit, min, max, step, default]]]
export const KINDS = {
  damage: ["Daño al jefe", [["amount", "Daño", "PV", 0, 100000, 5, 80]]],
  damage_all: ["Daño a todos los enemigos", [["amount", "Daño", "PV", 0, 100000, 5, 60]]],
  heal: ["Curarte", [["amount", "Vida", "PV", 0, 100000, 5, 30]]],
  heal_team: ["Curar al equipo", [["amount", "Vida a cada uno", "PV", 0, 100000, 5, 20]]],
  shield: ["Escudo (tú)", [["amount", "Menos daño", "%", 1, 90, 5, 40], ["seconds", "Durante", "s", 1, 300, 1, 15]]],
  shield_team: ["Escudo (equipo)", [["amount", "Menos daño", "%", 1, 90, 5, 30], ["seconds", "Durante", "s", 1, 300, 1, 12]]],
  stun: ["Aturdir al jefe", [["seconds", "Durante", "s", 0.5, 10, 0.5, 3]]],
  buff_damage: ["Más daño (tú)", [["amount", "Más daño", "%", 1, 300, 5, 25], ["seconds", "Durante (0 = el próximo golpe)", "s", 0, 600, 5, 30]]],
  buff_bf: ["Más Black Flash (tú)", [["amount", "Probabilidad", "%", 1, 300, 5, 15], ["seconds", "Durante (0 = el próximo)", "s", 0, 600, 5, 30]]],
  charge_team: ["Carga para el equipo", [["amount", "Carga a cada uno", "%", 1, 100, 5, 20]]],
  cleanse: ["Quitarte efectos malos", []],
  cleanse_team: ["Quitar efectos malos al equipo", []],
};
export const MAX_PARTS = 4;

// a good starting point for each type of power (the type itself changes nothing in the fight: the effects do)
export const PRESETS = {
  destructive: "damage:120",
  support: "heal_team:25;charge_team:15",
  defend: "shield_team:40:12",
  build: "buff:damage_boost:25:30;buff:bf_boost:10:30",
  control: "stun:4;damage:40",
};

const n = (v) => String(Math.round(Number(v) * 100) / 100);

export function parse(effect) {
  const out = [];
  for (const raw of String(effect || "").toLowerCase().replace(/\s+/g, "").split(/[;+]/).filter(Boolean)) {
    const [kind, a, b, c] = raw.split(":");
    if (kind === "buff") {
      const value = a === "damage_boost" || a === "bf_boost" ? Number(b ?? 10) : NaN;
      if (!Number.isFinite(value)) return null;
      out.push({ kind: a === "damage_boost" ? "buff_damage" : "buff_bf", amount: value <= 1 ? value * 100 : value, seconds: Number(c ?? 30) });
    } else if (kind === "stun") out.push({ kind, seconds: Number(a ?? 3) });
    else if (kind === "cleanse" || kind === "cleanse_team") out.push({ kind });
    else if (kind === "shield" || kind === "shield_team") out.push({ kind, amount: Number(a ?? 30), seconds: Number(b ?? 15) });
    else if (KINDS[kind] && a !== undefined && Number.isFinite(Number(a))) out.push({ kind, amount: Number(a) });
    else return null;                                          // something the builder cannot show: the advanced box keeps it as text
  }
  return out.length ? out : null;
}

export function compose(parts) {
  return parts.map((p) => {
    switch (p.kind) {
      case "buff_damage": return `buff:damage_boost:${n(p.amount)}:${n(p.seconds)}`;
      case "buff_bf": return `buff:bf_boost:${n(p.amount)}:${n(p.seconds)}`;
      case "stun": return `stun:${n(p.seconds)}`;
      case "cleanse": case "cleanse_team": return p.kind;
      case "shield": case "shield_team": return `${p.kind}:${n(p.amount)}:${n(p.seconds)}`;
      default: return `${p.kind}:${n(p.amount)}`;
    }
  }).join(";");
}

export function freshPart(kind) {
  const part = { kind };
  for (const [key, , , , , , value] of KINDS[kind][1]) part[key] = value;
  return part;
}

const secs = (s) => (s >= 60 ? `${Math.floor(s / 60)} min${s % 60 ? ` ${s % 60} s` : ""}` : `${n(s)} s`);

// What it will do, in words, with this player's multiplier (weapon × boosts × revenge) and the game's damage cap.
export function describe(parts, multiplier = 1, cap = 500) {
  return (parts || []).map((p) => {
    const hit = Math.round(Math.min(cap, (p.amount || 0) * multiplier));
    switch (p.kind) {
      case "damage": return `💥 ${hit} de daño al jefe${hit >= cap ? " (el máximo)" : ""}`;
      case "damage_all": return `💥 ${hit} al jefe y ${Math.round((p.amount || 0) * multiplier)} a cada mini enemigo`;
      case "heal": return `💚 Te curas ${Math.round(p.amount)} PV`;
      case "heal_team": return `💚 Cada jugador en pie se cura ${Math.round(p.amount)} PV`;
      case "shield": return `🛡️ Recibes un ${Math.round(p.amount)} % menos de daño durante ${secs(p.seconds)}`;
      case "shield_team": return `🛡️ Todo el equipo recibe un ${Math.round(p.amount)} % menos de daño durante ${secs(p.seconds)}`;
      case "stun": return `🌀 El jefe queda aturdido ${secs(p.seconds)} (los mini enemigos también esperan)`;
      case "buff_damage": return `✨ +${n(p.amount)} % de daño ${p.seconds ? `durante ${secs(p.seconds)}` : "en tu próximo golpe"}`;
      case "buff_bf": return `✨ +${n(p.amount)} % de probabilidad de Black Flash ${p.seconds ? `durante ${secs(p.seconds)}` : "en el próximo"}`;
      case "charge_team": return `⚡ Los demás ganan un ${Math.round(p.amount)} % de carga de poder`;
      case "cleanse": return "🧼 Te quitas sangrado, quemadura, veneno, debilidad, aturdimiento y maldiciones";
      case "cleanse_team": return "🧼 Le quitas los efectos malos a todo el equipo";
      default: return "";
    }
  }).filter(Boolean);
}

// The short label of a saved power's effect (the cards of «Personajes»).
export function effectSummary(effect, multiplier = 1, cap = 500) {
  const parts = parse(effect);
  if (!parts) return String(effect || "—");
  return describe(parts, multiplier, cap).map((line) => line.replace(/^\S+\s/, "")).join(" · ");
}
