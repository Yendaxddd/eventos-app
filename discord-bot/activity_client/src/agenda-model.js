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

// ── time zones and the calendar of concrete dates ─────────────────────────────────────────────────────────────────────
// A player's concrete dates are keys «YYYY-MM-DD» in their own calendar, with hours «HH:MM» in their own clock; the server
// also keeps their time zone (IANA) and its offset in minutes, so anybody's screen can show those hours in its own clock.

export const deviceZone = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { return ""; } };

// Minutes ahead of UTC that `tz` is at `date` (Madrid in winter: 60). An unknown zone: the device's.
export function zoneOffset(tz, date = new Date()) {
  if (tz) {
    try {
      const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
        timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      }).formatToParts(date).map((p) => [p.type, p.value]));
      const asUtc = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour % 24, +parts.minute);
      return Math.round((asUtc - Math.floor(date.getTime() / 60_000) * 60_000) / 60_000);
    } catch { /* not a zone this browser knows */ }
  }
  return -date.getTimezoneOffset();
}

// Every zone the browser knows (or a short list), for the manual picker.
const FEW_ZONES = ["America/Mexico_City", "America/Bogota", "America/Lima", "America/Santiago", "America/Argentina/Buenos_Aires",
  "America/Caracas", "America/New_York", "America/Los_Angeles", "Europe/Madrid", "Europe/London", "Atlantic/Canary", "UTC"];
export function zoneList() {
  try { const all = Intl.supportedValuesOf("timeZone"); if (all && all.length) return all.includes("UTC") ? all : [...all, "UTC"]; } catch { /* old browser */ }
  return FEW_ZONES;
}

export function offsetLabel(minutes) {
  const sign = minutes < 0 ? "−" : "+", abs = Math.abs(minutes);
  return `UTC${sign}${Math.floor(abs / 60)}${abs % 60 ? `:${two(abs % 60)}` : ""}`;
}

// «Madrid · UTC+1»
export function zoneLabel(tz, offset) {
  const city = tz ? tz.split("/").pop().replace(/_/g, " ") : "";
  return city ? `${city} · ${offsetLabel(offset)}` : offsetLabel(offset);
}

// What a clock in that offset reads at `ms`: «21:40».
export function clockAt(offset, ms = Date.now()) {
  const d = new Date(ms + offset * 60_000);
  return `${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`;
}

// The calendar date «YYYY-MM-DD» a clock `offset` minutes ahead of UTC shows at `ms`.
export function dayKey(ms, offset) {
  const d = new Date(ms + offset * 60_000);
  return `${d.getUTCFullYear()}-${two(d.getUTCMonth() + 1)}-${two(d.getUTCDate())}`;
}
export const keyOf = (y, m, d) => `${y}-${two(m + 1)}-${two(d)}`;          // m from 0
export const weekdayOf = (key) => mod(new Date(`${key}T00:00:00Z`).getUTCDay() - 1, 7);   // Monday 0
export function addDays(key, n) {
  const d = new Date(`${key}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return keyOf(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

// A month as 6 weeks of 7 days, Monday first: [{ key, day, inMonth }].
export function monthGrid(year, month) {
  const first = keyOf(year, month, 1);
  const start = addDays(first, -weekdayOf(first));
  return Array.from({ length: 42 }, (_, i) => {
    const key = addDays(start, i);
    return { key, day: Number(key.slice(8)), inMonth: Number(key.slice(5, 7)) === month + 1 };
  });
}
export const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
export function dayTitle(key) {
  return `${DAYS[weekdayOf(key)]} ${Number(key.slice(8))} de ${MONTHS[Number(key.slice(5, 7)) - 1]}`;
}

const minutesOf = (hhmm) => (hhmm ? Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5)) : null);
const hhmm = (m) => `${two(Math.floor(mod(m, 1440) / 60))}:${two(mod(m, 60))}`;

// A range of hours from somebody's clock (offset `from`) in another clock (offset `to`): { from, to, days } where `days` is
// −1 / 0 / +1 if the start lands on another date there. Missing ends stay "".
export function moveRange(start, end, fromOffset, toOffset) {
  const delta = toOffset - fromOffset;
  const a = minutesOf(start), b = minutesOf(end);
  const days = a !== null ? Math.floor((a + delta) / 1440) : 0;
  return { from: a !== null ? hhmm(a + delta) : "", to: b !== null ? (b === 1440 && !delta ? "24:00" : hhmm(b + delta)) : "", days };
}

export function rangeLabel(r) {
  if (!r.from && !r.to) return "todo el día";
  const tail = r.days > 0 ? " (día siguiente)" : r.days < 0 ? " (día anterior)" : "";
  if (r.from && r.to) return `${r.from}–${r.to}${tail}`;
  return r.from ? `desde las ${r.from}${tail}` : `hasta las ${r.to}`;
}

// The offset a person's hours are in: their zone now (if this browser knows it), else what they saved.
export const personOffset = (p, date = new Date()) => (p && p.tz ? zoneOffset(p.tz, date) : (p && Number(p.offset)) || 0);

// Who can on a date of the viewer's calendar: people who marked that date, and (for the rest) whether their week has hours that
// weekday. [{ id, name, a: "yes"|"maybe"|"no", from, to, note, tz, offset, range, byWeek }]; the marked first.
export function dayCrowd(people, key, viewerOffset) {
  const out = [];
  const wd = weekdayOf(key);
  for (const p of people || []) {
    const offset = personOffset(p);
    const d = (p.days || {})[key];
    if (d) {
      out.push({ id: p.id, name: p.name, a: d.a, note: d.note, tz: p.tz, offset, byWeek: false,
        range: moveRange(d.from, d.to, offset, viewerOffset) });
      continue;
    }
    const local = toLocal(p.week, Math.round(offset / 60)).slice(wd * 24, wd * 24 + 24);
    const best = local.includes(2) ? 2 : local.includes(1) ? 1 : 0;
    if (!best) continue;
    const first = local.findIndex((v) => v > 0), last = 23 - [...local].reverse().findIndex((v) => v > 0);
    out.push({ id: p.id, name: p.name, a: best === 2 ? "yes" : "maybe", note: "", tz: p.tz, offset, byWeek: true,
      range: moveRange(hourLabel(first), last === 23 ? "24:00" : hourLabel(last + 1), offset, viewerOffset) });
  }
  const order = { yes: 0, maybe: 1, no: 2 };
  return out.sort((x, y) => x.byWeek - y.byWeek || order[x.a] - order[y.a] || x.name.localeCompare(y.name));
}

// What each person's calendar says about a poll date `at` (ms): [{ name, a, note, outside }] for those who marked that day in
// their own calendar. `outside`: they can that day, but not at that hour.
export function calendarSays(people, at) {
  const out = [];
  for (const p of people || []) {
    const offset = personOffset(p, new Date(at));
    const d = (p.days || {})[dayKey(at, offset)];
    if (!d) continue;
    const local = new Date(at + offset * 60_000);
    const m = local.getUTCHours() * 60 + local.getUTCMinutes();
    const a = minutesOf(d.from), b = minutesOf(d.to);
    const outside = d.a !== "no" && ((a !== null && m < a) || (b !== null && m >= b));
    out.push({ name: p.name, a: d.a, note: d.note, outside, from: d.from, to: d.to });
  }
  return out;
}
