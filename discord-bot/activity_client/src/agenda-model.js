// The agenda's arithmetic, tested without a browser. The server keeps every week in UTC (168 hours, Monday 00:00 UTC first,
// each "0" no, "1" maybe, "2" yes); the screen shows it in the player's own clock. `shift` is the player's offset from UTC
// in whole hours (Madrid in summer: +2, Mexico City: -6).

export const HOURS = 168;
export const DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
export const DAYS_SHORT = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

export const localShift = (date = new Date()) => Math.round(-date.getTimezoneOffset() / 60);
const mod = (n, m) => ((n % m) + m) % m;

// A UTC week (string) as an array of numbers in local order: index day * 24 + hour, Monday first.
export function toLocal(week, shift) {
  const out = new Array(HOURS).fill(0);
  const text = String(week || "").padEnd(HOURS, "0");
  for (let u = 0; u < HOURS; u++) out[mod(u + shift, HOURS)] = Number(text[u]) || 0;
  return out;
}

// And back: a local array as the UTC string the server keeps.
export function toUtc(local, shift) {
  const out = new Array(HOURS).fill("0");
  for (let l = 0; l < HOURS; l++) out[mod(l - shift, HOURS)] = String(Math.max(0, Math.min(2, local[l] | 0)));
  return out.join("");
}

// Everybody's weeks added up, in local order: [{ yes, maybe, who: [[name, 2|1], …] }].
export function heat(people, shift) {
  const cells = Array.from({ length: HOURS }, () => ({ yes: 0, maybe: 0, who: [] }));
  for (const person of people || []) {
    const local = toLocal(person.week, shift);
    local.forEach((v, i) => {
      if (v === 2) { cells[i].yes++; cells[i].who.push([person.name, 2]); }
      else if (v === 1) { cells[i].maybe++; cells[i].who.push([person.name, 1]); }
    });
  }
  return cells;
}

const score = (c) => c.yes + c.maybe * 0.5;

// The best stretches of at least `min` hours (and at most `max`) where the same crowd can play: the strongest first.
// [{ day, from, to, yes, maybe, start }] — `start` is the local index of the first hour, `to` is exclusive.
export function bestSlots(cells, { min = 2, max = 4, top = 5, need = 1 } = {}) {
  const found = [];
  for (let start = 0; start < HOURS; start++) {
    const day = Math.floor(start / 24), from = start % 24;
    let best = null;                                   // the stretch from this hour that is worth most (a longer one only if as many can come)
    for (let len = min; len <= max; len++) {
      if (from + len > 24) break;
      const run = cells.slice(start, start + len);
      const yes = Math.min(...run.map((c) => c.yes));
      const maybe = Math.min(...run.map((c) => c.yes + c.maybe)) - yes;
      if (yes + maybe < need) break;
      const value = (yes + maybe * 0.5) * (1 + len / 10);
      if (!best || value > best.value) best = { day, from, to: from + len, yes, maybe, start, value };
    }
    if (best) found.push(best);
  }
  found.sort((a, b) => b.value - a.value || a.start - b.start);
  const picked = [];
  for (const slot of found) {
    if (picked.some((p) => p.day === slot.day && slot.from < p.to && p.from < slot.to)) continue;   // no overlapping stretches
    picked.push(slot);
    if (picked.length >= top) break;
  }
  return picked;
}

// How strong a cell looks, 0..1, against the busiest hour of the week.
export function strength(cell, peak) {
  return peak > 0 ? Math.min(1, score(cell) / peak) : 0;
}
export const peakOf = (cells) => Math.max(0, ...cells.map(score));

// The next time a local weekday and hour comes around (a timestamp), at least `lead` ms from now.
export function nextAt(day, hour, now = Date.now(), lead = 30 * 60_000) {
  const d = new Date(now);
  const today = mod(d.getDay() - 1, 7);                         // Monday 0
  const at = new Date(d.getFullYear(), d.getMonth(), d.getDate() + mod(day - today, 7), hour, 0, 0, 0);
  if (at.getTime() < now + lead) at.setDate(at.getDate() + 7);
  return at.getTime();
}

// A poll's tally: for each option { yes, maybe, no, who: { yes: [names], maybe: [...], no: [...] } }.
export function tally(poll) {
  const out = {};
  for (const o of poll.options || []) out[o.id] = { yes: 0, maybe: 0, no: 0, who: { yes: [], maybe: [], no: [] } };
  for (const [uid, answers] of Object.entries(poll.votes || {})) {
    const name = (poll.names || {})[uid] || "Alguien";
    for (const [oid, a] of Object.entries(answers || {})) {
      if (!out[oid] || !(a in out[oid].who)) continue;
      out[oid][a]++;
      out[oid].who[a].push(name);
    }
  }
  return out;
}

// The option most people can make (yes counts double a maybe); null if nobody answered.
export function leader(poll) {
  const t = tally(poll);
  let best = null;
  for (const o of poll.options || []) {
    const v = t[o.id].yes * 2 + t[o.id].maybe;
    if (v > 0 && (!best || v > best.v)) best = { id: o.id, v };
  }
  return best ? best.id : null;
}

const two = (n) => String(n).padStart(2, "0");
export const hourLabel = (h) => `${two(h)}:00`;

// «sábado 14 de diciembre, 20:00» in the player's clock.
export function whenLabel(ms) {
  try {
    return new Intl.DateTimeFormat("es", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }).format(new Date(ms));
  } catch { return new Date(ms).toLocaleString(); }
}

// «en 3 días», «en 5 h», «ahora», «hace 2 h».
export function untilLabel(ms, now = Date.now()) {
  const diff = ms - now, abs = Math.abs(diff);
  const h = Math.round(abs / 3_600_000), d = Math.round(abs / 86_400_000);
  const amount = abs < 3_600_000 ? `${Math.max(1, Math.round(abs / 60_000))} min` : abs < 48 * 3_600_000 ? `${h} h` : `${d} días`;
  if (abs < 60_000) return "ahora";
  return diff > 0 ? `en ${amount}` : `hace ${amount}`;
}

// What a <input type="datetime-local"> holds for a timestamp, and back.
export function toInput(ms) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}T${two(d.getHours())}:${two(d.getMinutes())}`;
}
export function fromInput(text) {
  const ms = new Date(text).getTime();
  return Number.isFinite(ms) ? ms : null;
}
