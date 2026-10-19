// What the bot tells a player about an answer, now that the channel stays quiet: `{ t: "notice", kind, data }` frames. The bot says what
// happened (kind) and its numbers (data); the words are chosen here, in Spanish. A kind that the QTE button already shows the player
// (their own verdict: "¡Esquivado!", "Fallaste"...) says nothing here, so nothing is told twice.
const SECONDS = (ms) => (Number(ms) / 1000).toFixed(2);
const ARROWS = { "⬆️": "arriba", "⬇️": "abajo", "⬅️": "izquierda", "➡️": "derecha" };
const arrow = (glyph) => ARROWS[String(glyph || "")] || String(glyph || "").replace(/️/g, "");
const COMBO_WHY = (d) => (d.why === "slow" ? "fuiste demasiado lento" : `botón equivocado, tocaba «${d.expected || "?"}»`);

const KINDS = {
  stunned: () => ({ tone: "bad", text: "Estás aturdido: no puedes reaccionar." }),
  mirror_heal: (d) => ({ tone: "ok", text: `Fragmento de espejo: +${Math.max(0, (d.new || 0) - (d.old || 0))} PV (${d.old} → ${d.new})` }),
  parry_cooldown: (d) => ({ tone: "warn", text: `El parry se está recargando: ${d.seconds} s.` }),
  adapt_ok: (d) => ({ tone: "ok", text: `Adaptado en ${SECONDS(d.ms)} s${d.info && d.info.length ? ` · ${d.info.join(" · ")}` : ""}` }),
  adapt_mistimed: (d) => ({ tone: "bad", text: `Adaptación a destiempo (${SECONDS(d.ms)} s).` }),
  save_limit: () => ({ tone: "warn", text: "Límite de rescates: máximo 2 por minuto." }),
  group_no_parry: () => ({ tone: "warn", text: "En un QTE grupal no se puede hacer parry: esquiva." }),
  group_done: (d) => ({ tone: d.ok === d.total ? "ok" : "info", text: `QTE grupal: lo lograron ${d.ok} de ${d.total}.` }),
  combo_done: (d) => ({ tone: "ok", text: `¡Combo completo! ${d.length} golpes.` }),
  combo_broken: (d) => ({ tone: "bad", text: `Combo roto: ${COMBO_WHY(d)}.` }),
  combo_failed: (d) => ({ tone: "bad", text: `Combo fallido: hiciste ${d.done} de ${d.total}.` }),
  direction_wrong: (d) => ({ tone: "bad", text: `Dirección equivocada: había que pulsar ${arrow(d.needed)} (la opuesta a ${arrow(d.shown)}).` }),
  fake_fail: () => ({ tone: "bad", text: "¡Era un QTE falso! No había ningún ataque." }),
  timeout: () => ({ tone: "bad", text: "No respondiste a tiempo." }),
  chain_end: (d) => ({
    tone: d.why === "timeout" ? "info" : "warn",
    text: `${d.why === "timeout" ? "Cadena terminada" : d.why === "mistimed" ? "Parry a destiempo: la cadena termina" : "Parry sin Black Flash: la cadena termina"} · parry en recarga ${d.cooldown} s.`,
  }),
  chain_max: (d) => ({ tone: "bf", text: `¡CADENA MÁXIMA de Black Flash! Parry en recarga ${d.cooldown} s.` }),
  black_flash: (d) => ({ tone: "bf", text: `¡Black Flash! ${d.damage} de daño${d.chain ? ` · cadena ${d.chain}/4` : ""}${d.mirror ? " · Fragmento de espejo" : ""}` }),
  // the button already says these: evade_ok, evade_slow, parry_ok, parry_mistimed, save_ok, save_slow, direction_ok, direction_slow, combo_step
};

// { tone, text } for the screen, or null when there is nothing to add.
export function describeNotice(kind, data = {}) {
  const make = KINDS[kind];
  if (!make) return null;
  try { return make(data || {}); } catch { return null; }
}
