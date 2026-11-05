// «Agenda»: when everybody can play. Each player paints their week (in their own clock) and marks concrete dates on a calendar
// (AgendaCalendar.jsx), the team's week shows as a heat map with the best stretches, and the game masters with the «Agenda» box
// open date polls and pick the winner. Each person's time zone is the device's or one they pick by hand.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { CalendarCheck, CalendarClock, CalendarDays, CalendarPlus, Check, Eraser, Lock, Plus, RotateCcw, Trash2, Users, X } from "lucide-preact";
import { agendaRev, toast } from "../state.js";
import { rpc } from "../net.js";
import { Page, Section, Segmented } from "../ui/Controls.jsx";
import {
  DAYS, DAYS_SHORT, HOURS, bestSlots, deviceZone, fromInput, heat, hourLabel, leader, nextAt, peakOf, strength, tally, toInput, toLocal, toUtc, untilLabel, whenLabel,
  zoneLabel, zoneOffset,
} from "../agenda-model.js";
import { Calendar, PollCalendar, TeamZones, ZonePicker } from "./AgendaCalendar.jsx";
const ANSWER = [["yes", "Puedo"], ["maybe", "Quizá"], ["no", "No"]];

function useAgenda() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const rev = agendaRev.value;
  useEffect(() => {
    let live = true;
    rpc("agenda.get").then((d) => { if (live) { setData(d); setError(""); } }).catch((e) => live && setError(e.message || String(e)));
    return () => { live = false; };
  }, [rev]);
  const run = async (op, args) => {
    try { const d = await rpc(op, args); setData(d); return d; } catch (e) { toast(e.message || String(e), "bad"); return null; }
  };
  return { data, error, run };
}

// ── the next event ────────────────────────────────────────────────────────────────────────────────────────────────
export function NextEvent({ next, compact }) {
  if (!next) return null;
  const now = Date.now();
  const live = next.at <= now && now < next.at + next.minutes * 60_000;
  return (
    <div class={`agenda-next ${compact ? "compact" : ""}`} data-testid="agenda-next">
      <span class="agenda-next-ico"><CalendarCheck size={compact ? 16 : 22} /></span>
      <span class="grow">
        <small>{live ? "Ahora mismo" : "Próximo evento"}</small>
        <strong>{next.title}</strong>
        <span class="faint">{whenLabel(next.at)} · {live ? "en curso" : untilLabel(next.at, now)}</span>
      </span>
    </div>
  );
}

// ── a date poll ───────────────────────────────────────────────────────────────────────────────────────────────────
function PollCard({ poll, me, canEdit, run, people }) {
  const t = tally(poll);
  const mine = (poll.votes || {})[me] || {};
  const lead = leader(poll);
  const total = Object.keys(poll.votes || {}).length;
  const answer = (oid, a) => run("agenda.vote", { poll: poll.id, answers: { ...mine, [oid]: a } });
  return (
    <div class={`poll ${poll.open ? "" : "closed"}`} data-testid="poll">
      <div class="poll-head">
        <div class="grow">
          <strong>{poll.title}</strong>
          <span class="faint">{poll.open ? `${total} ${total === 1 ? "respuesta" : "respuestas"} · ${poll.minutes / 60 >= 1 ? `${+(poll.minutes / 60).toFixed(1)} h` : `${poll.minutes} min`}` : "Cerrada"}{poll.by ? ` · abierta por ${poll.by}` : ""}</span>
          {poll.note && <p class="poll-note">{poll.note}</p>}
        </div>
        {canEdit && !poll.open && <button class="btn btn-sm btn-ghost" type="button" title="Reabrir" onClick={() => run("gm.schedule_close", { poll: poll.id, option: null })}><RotateCcw size={14} /></button>}
        {canEdit && <button class="btn btn-sm btn-ghost danger" type="button" title="Borrar la votación" onClick={() => confirm(`¿Borrar «${poll.title}»?`) && run("gm.schedule_delete", { poll: poll.id })}><Trash2 size={14} /></button>}
      </div>
      <div class="poll-options">
        {poll.options.map((o) => {
          const c = t[o.id];
          const n = Math.max(1, c.yes + c.maybe + c.no);
          const chosen = poll.chosen === o.id;
          if (!poll.open && !chosen) return null;
          return (
            <div class={`poll-opt ${chosen ? "chosen" : ""} ${poll.open && lead === o.id ? "lead" : ""}`} key={o.id}>
              <div class="poll-when">
                <strong>{whenLabel(o.at)}</strong>
                <span class="faint">{chosen ? "Fecha elegida" : untilLabel(o.at)}{poll.open && lead === o.id ? " · la que más gente puede" : ""}</span>
              </div>
              <div class="poll-bar" title={`Pueden: ${c.who.yes.join(", ") || "nadie"}\nQuizá: ${c.who.maybe.join(", ") || "nadie"}\nNo: ${c.who.no.join(", ") || "nadie"}`}>
                <i class="yes" style={{ width: `${(c.yes / n) * 100}%` }} /><i class="maybe" style={{ width: `${(c.maybe / n) * 100}%` }} />
              </div>
              <span class="poll-count num" title="Pueden · quizá · no"><b>{c.yes}</b> <small>+{c.maybe}</small>{c.no > 0 && <em> · {c.no} no</em>}</span>
              {poll.open && (
                <div class="poll-answer segmented" role="group" aria-label={`Tu respuesta para ${whenLabel(o.at)}`}>
                  {ANSWER.map(([a, label]) => <button key={a} type="button" data-a={a} aria-pressed={mine[o.id] === a ? "true" : "false"} onClick={() => answer(o.id, a)}>{label}</button>)}
                </div>
              )}
              {canEdit && poll.open && <button class="btn btn-sm" type="button" onClick={() => run("gm.schedule_close", { poll: poll.id, option: o.id })} data-testid="poll-pick"><Check size={14} /> Elegir</button>}
              {(c.who.yes.length > 0 || c.who.maybe.length > 0) && (
                <div class="poll-who">
                  {c.who.yes.map((name) => <span class="chip yes" key={`y${name}`}>{name}</span>)}
                  {c.who.maybe.map((name) => <span class="chip maybe" key={`m${name}`}>{name}?</span>)}
                </div>
              )}
              {poll.open && <PollCalendar people={people} at={o.at} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── a new poll (game masters) ───────────────────────────────────────────────────────────────────────────────────────
function NewPoll({ slots, run, onDone }) {
  const [title, setTitle] = useState("Nueva sesión");
  const [minutes, setMinutes] = useState(120);
  const [note, setNote] = useState("");
  const [dates, setDates] = useState(() => slots.slice(0, 3).map((s) => toInput(nextAt(s.day, s.from))));
  const add = (value = "") => setDates((d) => (d.length >= 8 ? d : [...d, value]));
  const submit = async (e) => {
    e.preventDefault();
    const options = dates.map(fromInput).filter((x) => x !== null);
    if (!options.length) { toast("Pon al menos una fecha.", "bad"); return; }
    if (await run("gm.schedule_propose", { title, minutes, note, options })) { toast("Votación abierta: todos la ven ya.", "ok"); onDone(); }
  };
  return (
    <form class="card-2 agenda-form" onSubmit={submit} data-testid="poll-form">
      <label class="field"><span>Título</span><input class="input" value={title} maxLength={80} onInput={(e) => setTitle(e.currentTarget.value)} /></label>
      <label class="field"><span>Nota (opcional)</span><input class="input" value={note} maxLength={300} placeholder="Capítulo 4: el asalto final" onInput={(e) => setNote(e.currentTarget.value)} /></label>
      <div class="field"><span>Duración</span>
        <Segmented label="Duración" value={minutes} onChange={setMinutes} options={[[60, "1 h"], [90, "1 h 30"], [120, "2 h"], [180, "3 h"], [240, "4 h"]]} />
      </div>
      <div class="field"><span>Fechas (tu hora)</span>
        {dates.map((d, i) => (
          <div class="row" key={i} style={{ gap: "6px" }}>
            <input class="input grow" type="datetime-local" value={d} onInput={(e) => { const v = e.currentTarget.value; setDates((all) => all.map((x, j) => (j === i ? v : x))); }} />
            <button class="btn btn-sm btn-ghost" type="button" aria-label="Quitar esta fecha" onClick={() => setDates((all) => all.filter((_, j) => j !== i))}><X size={14} /></button>
          </div>
        ))}
        <div class="row" style={{ gap: "6px", flexWrap: "wrap" }}>
          <button class="btn btn-sm btn-ghost" type="button" onClick={() => add(toInput(nextAt(5, 20)))} disabled={dates.length >= 8}><Plus size={14} /> Añadir fecha</button>
          {slots.slice(0, 4).map((s) => (
            <button key={s.start} class="btn btn-sm btn-ghost" type="button" disabled={dates.length >= 8} onClick={() => add(toInput(nextAt(s.day, s.from)))} title="Una de las mejores horas del equipo">
              <Users size={13} /> {DAYS_SHORT[s.day]} {hourLabel(s.from)} · {s.yes}
            </button>
          ))}
        </div>
      </div>
      <div class="row" style={{ gap: "8px", justifyContent: "flex-end" }}>
        <button class="btn btn-sm btn-ghost" type="button" onClick={onDone}>Cancelar</button>
        <button class="btn btn-sm btn-primary" type="submit"><CalendarPlus size={14} /> Abrir votación</button>
      </div>
    </form>
  );
}

// ── the week grid: the player's own (paintable) or the team's (a heat map) ─────────────────────────────────────────
function WeekGrid({ cells, paint, onCell, onDay, onHour, testid, selected }) {
  const dragging = useRef(false);
  useEffect(() => {
    const up = () => { dragging.current = false; };
    window.addEventListener("pointerup", up);
    return () => window.removeEventListener("pointerup", up);
  }, []);
  const box = useRef(null);
  useEffect(() => {                                   // open at the first marked hour (or the afternoon), not at midnight
    const el = box.current;
    if (!el) return;
    const marked = cells.map((c, i) => ((paint ? c > 0 : c.yes + c.maybe > 0) ? i % 24 : 99));
    const first = Math.min(...marked);
    const hour = first < 99 ? Math.max(0, first - 1) : 15;
    const row = el.querySelector(`.week-hour[data-h="${hour}"]`);
    if (row) el.scrollTop = row.offsetTop - 30;
  }, []);
  const hit = (e) => { const i = Number(e.currentTarget.dataset.i); onCell(i, e.type); };
  return (
    <div class="week-scroll" ref={box}>
    <div class={`week ${paint ? "paint" : "heat"}`} data-testid={testid} role="grid" aria-label={paint ? "Mi semana" : "La semana del equipo"}>
      <span class="week-corner" />
      {DAYS_SHORT.map((d, day) => (
        <button type="button" class="week-day" key={d} onClick={() => onDay && onDay(day)} title={paint ? `Marcar todo el ${DAYS[day].toLowerCase()}` : DAYS[day]}>{d}</button>
      ))}
      {Array.from({ length: 24 }, (_, hour) => [
        <button type="button" class="week-hour num" data-h={hour} key={`h${hour}`} onClick={() => onHour && onHour(hour)} title={paint ? `Marcar las ${hourLabel(hour)} toda la semana` : ""}>{hourLabel(hour)}</button>,
        ...DAYS_SHORT.map((_, day) => {
          const i = day * 24 + hour;
          const c = cells[i];
          return (
            <span
              key={i} data-i={i} role="gridcell"
              class={`week-cell ${selected === i ? "sel" : ""}`}
              data-v={paint ? c : undefined}
              style={paint ? undefined : { "--s": c.s }}
              aria-label={`${DAYS[day]} ${hourLabel(hour)}`}
              onPointerDown={(e) => { if (paint && e.pointerType === "mouse") dragging.current = true; hit(e); }}
              onPointerEnter={(e) => { if (paint && dragging.current) hit(e); }}
            />
          );
        }),
      ])}
    </div>
    </div>
  );
}

function MyWeek({ data, run, shift, zone }) {
  const mine = data.people.find((p) => p.id === data.me);
  const [local, setLocal] = useState(() => toLocal(mine ? mine.week : "", shift));
  const [note, setNote] = useState(mine ? mine.note : "");
  const [brush, setBrush] = useState(2);
  const [saved, setSaved] = useState("");
  const timer = useRef(null);
  const save = (next, nextNote = note) => {
    clearTimeout(timer.current);
    setSaved("…");
    timer.current = setTimeout(async () => {
      const device = deviceZone();
      const d = await run("agenda.week", { week: toUtc(next, shift), note: nextNote, tz: device, offset: zoneOffset(device) });
      setSaved(d ? "Guardado" : "");
    }, 700);
  };
  const change = (fn) => setLocal((prev) => { const next = fn(prev.slice()); save(next); return next; });
  const onCell = (i, type) => change((w) => {
    w[i] = type === "pointerdown" && brush !== 0 && w[i] === brush ? 0 : brush;       // tapping a painted hour with the same brush clears it
    return w;
  });
  const onDay = (day) => change((w) => { const all = w.slice(day * 24, day * 24 + 24).every((v) => v === brush); for (let h = 0; h < 24; h++) w[day * 24 + h] = all ? 0 : brush; return w; });
  const onHour = (hour) => change((w) => { const all = [0, 1, 2, 3, 4, 5, 6].every((d) => w[d * 24 + hour] === brush); for (let d = 0; d < 7; d++) w[d * 24 + hour] = all ? 0 : brush; return w; });
  const marked = local.filter((v) => v > 0).length;
  return (
    <div class="col" style={{ gap: "var(--sp-3)" }}>
      <div class="row agenda-tools">
        <div class="segmented" role="group" aria-label="Pincel">
          <button type="button" aria-pressed={brush === 2 ? "true" : "false"} data-a="yes" onClick={() => setBrush(2)}><Check size={14} /> Puedo</button>
          <button type="button" aria-pressed={brush === 1 ? "true" : "false"} data-a="maybe" onClick={() => setBrush(1)}>Quizá</button>
          <button type="button" aria-pressed={brush === 0 ? "true" : "false"} onClick={() => setBrush(0)}><Eraser size={14} /> Borrar</button>
        </div>
        <span class="faint grow" style={{ fontSize: ".75rem" }}>{marked} h marcadas{saved ? ` · ${saved}` : ""}</span>
        {marked > 0 && <button class="btn btn-sm btn-ghost" type="button" onClick={() => confirm("¿Borrar toda tu semana?") && change((w) => w.fill(0))}><Trash2 size={14} /> Vaciar</button>}
      </div>
      <p class="faint" style={{ fontSize: ".78rem", margin: 0 }}>Toca las horas (o arrastra con el ratón). Toca un día o una hora para marcar toda la columna o la fila. Las horas son las tuyas ({zoneLabel(zone.tz, zone.offset)}).</p>
      <WeekGrid cells={local} paint onCell={onCell} onDay={onDay} onHour={onHour} testid="my-week" />
      <label class="field"><span>Una nota para el equipo (opcional)</span>
        <input class="input" value={note} maxLength={200} placeholder="Los domingos solo por la tarde; en exámenes hasta el 20" onInput={(e) => { const v = e.currentTarget.value; setNote(v); save(local, v); }} />
      </label>
    </div>
  );
}

function TeamWeek({ data, cells, slots }) {
  const [sel, setSel] = useState(null);
  const peak = peakOf(cells);
  const view = cells.map((c) => ({ ...c, s: strength(c, peak).toFixed(2) }));
  const c = sel !== null ? cells[sel] : null;
  const notes = data.people.filter((p) => p.note);
  return (
    <div class="col" style={{ gap: "var(--sp-3)" }}>
      {data.people.length === 0 ? <p class="faint">Nadie ha marcado su semana todavía. ¡Sé el primero!</p> : (
        <>
          <div class="agenda-best">
            {slots.map((s, i) => (
              <button type="button" class={`best ${i === 0 ? "top" : ""}`} key={s.start} onClick={() => setSel(s.start)}>
                <strong>{DAYS[s.day]} {hourLabel(s.from)}–{hourLabel(s.to % 24)}</strong>
                <span class="faint"><b>{s.yes}</b> pueden{s.maybe ? ` · ${s.maybe} quizá` : ""}</span>
              </button>
            ))}
          </div>
          <WeekGrid cells={view} onCell={(i) => setSel(i)} testid="team-week" selected={sel} />
          <div class="agenda-legend faint"><span>Menos gente</span><i /><span>Más gente</span><span class="grow" /><span>{data.people.length} {data.people.length === 1 ? "persona" : "personas"}</span></div>
          {c && (
            <div class="card-2 agenda-who" data-testid="agenda-who">
              <strong>{DAYS[Math.floor(sel / 24)]} {hourLabel(sel % 24)}</strong>
              <div class="poll-who">
                {c.who.length === 0 && <span class="faint">Nadie</span>}
                {c.who.map(([name, v]) => <span class={`chip ${v === 2 ? "yes" : "maybe"}`} key={name}>{name}{v === 1 ? "?" : ""}</span>)}
              </div>
            </div>
          )}
          {notes.length > 0 && (
            <div class="agenda-notes">
              {notes.map((p) => <p key={p.id}><b>{p.name}:</b> {p.note}</p>)}
            </div>
          )}
          <TeamZones people={data.people} />
        </>
      )}
    </div>
  );
}

// The clock this screen shows: the zone picked by hand, else the device's.
function zoneOf(data) {
  const mine = data && data.people.find((p) => p.id === data.me);
  const tz = mine && mine.tzManual && mine.tz ? mine.tz : deviceZone();
  return { tz, offset: zoneOffset(tz) };
}

// For each weekday (Monday 0) the stretch my week marks, «18:00–22:00», or "".
function weekHours(week, shift) {
  const local = toLocal(week, shift);
  return DAYS.map((_, day) => {
    const row = local.slice(day * 24, day * 24 + 24);
    const first = row.findIndex((v) => v > 0);
    if (first < 0) return "";
    const last = 23 - [...row].reverse().findIndex((v) => v > 0);
    return `${hourLabel(first)}–${last === 23 ? "24:00" : hourLabel(last + 1)}`;
  });
}

export function AgendaPage() {
  const { data, error, run } = useAgenda();
  const [making, setMaking] = useState(false);
  const zone = zoneOf(data);
  const shift = Math.round(zone.offset / 60);
  const cells = useMemo(() => (data ? heat(data.people, shift) : Array.from({ length: HOURS }, () => ({ yes: 0, maybe: 0, who: [] }))), [data, shift]);
  const slots = useMemo(() => bestSlots(cells, { min: 2, max: 4, top: 5 }), [cells]);
  if (!data) return <Page title="Agenda" icon={CalendarDays}><p class="faint">{error || "Cargando…"}</p></Page>;
  const mine = data.people.find((p) => p.id === data.me);
  const open = data.polls.filter((p) => p.open), closed = data.polls.filter((p) => !p.open);
  return (
    <Page title="Agenda" icon={CalendarDays}
      actions={data.canEdit && !making && <button class="btn btn-sm btn-primary" type="button" onClick={() => setMaking(true)} data-testid="poll-new"><CalendarPlus size={14} /> Proponer fechas</button>}>
      <NextEvent next={data.next} />
      {making && <NewPoll slots={slots} run={run} onDone={() => setMaking(false)} />}
      {open.length > 0 && (
        <Section title="Votaciones abiertas">
          {open.map((p) => <PollCard key={p.id} poll={p} me={data.me} canEdit={data.canEdit} run={run} people={data.people} />)}
        </Section>
      )}
      <ZonePicker mine={mine} zone={zone} run={run} />
      <Section title="Calendario"><Calendar data={data} zone={zone} myHours={weekHours(mine ? mine.week : "", shift)} run={run} /></Section>
      <Section title="Mi semana (lo de siempre)"><MyWeek key={shift} data={data} run={run} shift={shift} zone={zone} /></Section>
      <Section title="La semana del equipo"><TeamWeek data={data} cells={cells} slots={slots} /></Section>
      {closed.length > 0 && (
        <Section title="Fechas elegidas">
          {closed.map((p) => <PollCard key={p.id} poll={p} me={data.me} canEdit={data.canEdit} run={run} people={data.people} />)}
        </Section>
      )}
      {!data.canEdit && open.length === 0 && <p class="faint agenda-foot"><Lock size={13} /> Las votaciones de fechas las abre el equipo de GM. <CalendarClock size={13} /> Marca tu semana para que sepan cuándo puedes.</p>}
    </Page>
  );
}
