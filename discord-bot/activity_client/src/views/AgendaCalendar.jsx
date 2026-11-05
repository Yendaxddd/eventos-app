// «Agenda · Calendario»: concrete dates that override the week («el 15 no puedo», «sábado 22 sí, de 18 a 23, desde el móvil»), the
// team's month (who can come each day, with their hours in your clock) and the time zone each person is in (agenda.py).
import { useMemo, useState } from "preact/hooks";
import { ChevronLeft, ChevronRight, Globe, MapPin, Trash2 } from "lucide-preact";
import { Segmented } from "../ui/Controls.jsx";
import {
  DAYS_SHORT, MONTHS, calendarSays, clockAt, dayCrowd, dayKey, dayTitle, deviceZone, monthGrid, personOffset, rangeLabel, zoneLabel, zoneList, zoneOffset,
} from "../agenda-model.js";

const STATE = [["yes", "Puedo"], ["maybe", "Quizá"], ["no", "No puedo"]];
const WORD = { yes: "puede", maybe: "quizá", no: "no puede" };

// ── the time zone: the device's, or one picked by hand ─────────────────────────────────────────────────────────────
export function ZonePicker({ mine, zone, run }) {
  const manual = !!(mine && mine.tzManual);
  const zones = useMemo(zoneList, []);
  const device = deviceZone();
  const pick = (tz) => run("agenda.zone", { tz, offset: zoneOffset(tz), manual: true });
  const reset = () => run("agenda.zone", { tz: device, offset: zoneOffset(device), manual: false });
  return (
    <div class="cal-zone" data-testid="agenda-zone">
      <Globe size={15} />
      <span class="grow"><b>Tu zona horaria:</b> {zoneLabel(zone.tz, zone.offset)} · son las {clockAt(zone.offset)}{manual ? " · elegida a mano" : " · la del dispositivo"}</span>
      <select class="input input-sm" aria-label="Elegir zona horaria" value={zone.tz} onChange={(e) => pick(e.currentTarget.value)} data-testid="agenda-zone-select">
        {!zones.includes(zone.tz) && zone.tz && <option value={zone.tz}>{zone.tz}</option>}
        {zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}
      </select>
      {manual && <button class="btn btn-sm btn-ghost" type="button" onClick={reset}>Usar la del dispositivo</button>}
    </div>
  );
}

// Everybody's zone and what their clock says now.
export function TeamZones({ people }) {
  const known = people.filter((p) => p.tz || p.offset);
  if (!known.length) return null;
  return (
    <div class="cal-zones" data-testid="team-zones">
      <span class="faint"><Globe size={12} /> Zonas horarias</span>
      {known.map((p) => {
        const off = personOffset(p);
        return <span class="chip" key={p.id} title={p.tz || ""}>{p.name} · {zoneLabel(p.tz, off)} · {clockAt(off)}</span>;
      })}
    </div>
  );
}

// ── one of my days ──────────────────────────────────────────────────────────────────────────────────────────────────
function DayEditor({ day, current, hint, today, run }) {
  const [d, setD] = useState(() => current || { a: "yes", from: "", to: "", note: "" });
  const set = (patch) => setD((old) => ({ ...old, ...patch }));
  const device = deviceZone();
  const save = () => run("agenda.day", { date: day, day: d, today, tz: device, offset: zoneOffset(device) });
  const clear = () => run("agenda.day", { date: day, day: null, today, tz: device, offset: zoneOffset(device) });
  const past = day < today;
  return (
    <div class="card-2 cal-editor" data-testid="day-editor">
      <strong class="cal-title">{dayTitle(day)}{current ? "" : " · sin marcar"}</strong>
      {!current && <span class="faint">{hint ? `Vale tu semana: ${hint}.` : "Tu semana no tiene horas ese día."} Márcalo para cambiar solo esta fecha.</span>}
      <div class="segmented" role="group" aria-label="Ese día">
        {STATE.map(([a, label]) => <button key={a} type="button" data-a={a} aria-pressed={d.a === a ? "true" : "false"} onClick={() => set({ a })} disabled={past}>{label}</button>)}
      </div>
      {d.a !== "no" && (
        <div class="row wrap" style={{ gap: "8px" }}>
          <label class="field"><span>Desde (tu hora)</span><input class="input" type="time" value={d.from} onInput={(e) => set({ from: e.currentTarget.value })} disabled={past} data-testid="day-from" /></label>
          <label class="field"><span>Hasta</span><input class="input" type="time" value={d.to} onInput={(e) => set({ to: e.currentTarget.value })} disabled={past} data-testid="day-to" /></label>
        </div>
      )}
      <label class="field"><span><MapPin size={12} /> Dónde o cómo (opcional)</span>
        <input class="input" value={d.note} maxLength={120} placeholder={d.a === "no" ? "De viaje, boda, exámenes…" : "Desde el móvil, en casa de un amigo, solo voz…"} onInput={(e) => set({ note: e.currentTarget.value })} disabled={past} data-testid="day-note" />
      </label>
      <div class="row wrap" style={{ gap: "8px" }}>
        <button class="btn btn-sm btn-primary" type="button" onClick={save} disabled={past} data-testid="day-save">Guardar este día</button>
        {current && <button class="btn btn-sm btn-ghost" type="button" onClick={clear} data-testid="day-clear"><Trash2 size={14} /> Quitar (vuelve a valer tu semana)</button>}
      </div>
    </div>
  );
}

// ── who can come that day ───────────────────────────────────────────────────────────────────────────────────────────
function DayCrowd({ day, crowd }) {
  return (
    <div class="card-2 cal-editor" data-testid="day-crowd">
      <strong class="cal-title">{dayTitle(day)}</strong>
      {crowd.length === 0 && <span class="faint">Nadie ha dicho nada de ese día.</span>}
      {crowd.map((c) => (
        <div class={`cal-person a-${c.a}`} key={c.id}>
          <span class={`chip ${c.a}`}>{c.name}</span>
          <span class="grow">
            <b>{WORD[c.a]}</b>{c.a !== "no" ? ` · ${rangeLabel(c.range)}` : ""}{c.byWeek ? " · según su semana" : ""}
            {c.note && <span class="cal-note"><MapPin size={11} /> {c.note}</span>}
          </span>
          <span class="faint cal-tz" title={c.tz || ""}>{zoneLabel(c.tz, c.offset)}</span>
        </div>
      ))}
      {crowd.length > 0 && <span class="faint" style={{ fontSize: ".72rem" }}>Las horas están en tu hora.</span>}
    </div>
  );
}

// ── the month ───────────────────────────────────────────────────────────────────────────────────────────────────────
export function Calendar({ data, zone, myHours, run }) {
  const today = dayKey(Date.now(), zone.offset);
  const [mode, setMode] = useState("mine");
  const [month, setMonth] = useState(() => [Number(today.slice(0, 4)), Number(today.slice(5, 7)) - 1]);
  const [sel, setSel] = useState(today);
  const mine = data.people.find((p) => p.id === data.me);
  const myDays = (mine && mine.days) || {};
  const grid = useMemo(() => monthGrid(month[0], month[1]), [month[0], month[1]]);
  const crowds = useMemo(() => Object.fromEntries(grid.map((g) => [g.key, dayCrowd(data.people, g.key, zone.offset)])), [grid, data, zone.offset]);
  const move = (n) => setMonth(([y, m]) => { const t = y * 12 + m + n; return [Math.floor(t / 12), ((t % 12) + 12) % 12]; });
  const marked = Object.keys(myDays).filter((k) => k >= today).length;
  return (
    <div class="col" style={{ gap: "var(--sp-3)" }}>
      <div class="row agenda-tools">
        <Segmented label="Calendario" value={mode} onChange={setMode} options={[["mine", "Mis días"], ["team", "Equipo"]]} />
        <span class="faint grow" style={{ fontSize: ".75rem" }}>{mode === "mine" ? `${marked} ${marked === 1 ? "día marcado" : "días marcados"} · un día marcado manda sobre tu semana` : "Quién puede cada día (lo marcado y, si no, su semana)"}</span>
      </div>
      <div class="cal-head">
        <button class="btn btn-sm btn-ghost" type="button" aria-label="Mes anterior" onClick={() => move(-1)}><ChevronLeft size={16} /></button>
        <strong class="grow">{MONTHS[month[1]][0].toUpperCase() + MONTHS[month[1]].slice(1)} {month[0]}</strong>
        <button class="btn btn-sm btn-ghost" type="button" aria-label="Mes siguiente" onClick={() => move(1)}><ChevronRight size={16} /></button>
      </div>
      <div class={`cal ${mode}`} role="grid" aria-label={mode === "mine" ? "Mis días" : "Los días del equipo"} data-testid={`cal-${mode}`}>
        {DAYS_SHORT.map((d) => <span class="cal-dow" key={d}>{d}</span>)}
        {grid.map((g) => {
          const d = myDays[g.key];
          const crowd = crowds[g.key] || [];
          const count = (a) => crowd.filter((c) => c.a === a).length;
          const weekly = myHours[(new Date(`${g.key}T00:00:00Z`).getUTCDay() + 6) % 7];
          return (
            <button type="button" key={g.key} role="gridcell" data-key={g.key}
              class={`cal-day ${g.inMonth ? "" : "out"} ${g.key < today ? "past" : ""} ${g.key === today ? "today" : ""} ${g.key === sel ? "sel" : ""} ${mode === "mine" && d ? `a-${d.a}` : ""}`}
              aria-label={`${dayTitle(g.key)}${mode === "mine" && d ? `: ${WORD[d.a]}` : ""}`} onClick={() => setSel(g.key)}>
              <span class="cal-num">{g.day}</span>
              {mode === "mine"
                ? (d ? <span class="cal-mark">{d.a === "no" ? "No" : d.from ? d.from : d.a === "yes" ? "Sí" : "¿?"}{d.note ? " •" : ""}</span> : weekly && <span class="cal-dot" title="Tu semana tiene horas este día" />)
                : (crowd.length > 0 && (
                  <span class="cal-counts">
                    {count("yes") > 0 && <b class="y">{count("yes")}</b>}
                    {count("maybe") > 0 && <b class="m">{count("maybe")}</b>}
                    {count("no") > 0 && <b class="n">{count("no")}</b>}
                  </span>
                ))}
            </button>
          );
        })}
      </div>
      {mode === "mine"
        ? <DayEditor key={`${sel}:${JSON.stringify(myDays[sel] || null)}`} day={sel} current={myDays[sel]} hint={myHours[(new Date(`${sel}T00:00:00Z`).getUTCDay() + 6) % 7]} today={today} run={run} />
        : <DayCrowd day={sel} crowd={crowds[sel] || dayCrowd(data.people, sel, zone.offset)} />}
    </div>
  );
}

// ── what the calendars say about a poll date ────────────────────────────────────────────────────────────────────────
export function PollCalendar({ people, at }) {
  const says = calendarSays(people, at).filter((s) => s.a === "no" || s.outside || s.note);
  if (!says.length) return null;
  return (
    <div class="poll-cal" data-testid="poll-cal">
      {says.map((s) => (
        <span key={s.name} class={`chip ${s.a === "no" ? "no" : s.outside ? "maybe" : s.a}`} title={s.note || ""}>
          {s.name}: {s.a === "no" ? "no puede ese día" : s.outside ? `ese día solo ${s.from || "…"}–${s.to || "…"} (su hora)` : WORD[s.a]}{s.note ? ` · ${s.note}` : ""}
        </span>
      ))}
    </div>
  );
}
