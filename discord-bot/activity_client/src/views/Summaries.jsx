// «Resúmenes»: what happened in the sessions you missed, written by the game masters (with an AI's help), with the cinematics of
// that stretch to watch again (summary.py). Only published summaries show here.
import { useEffect, useState } from "preact/hooks";
import { BookOpen, Clapperboard, Play } from "lucide-preact";
import { summariesRev, toast } from "../state.js";
import { rpc } from "../net.js";
import { previewCine } from "../cine.js";
import { Markdown } from "../md.jsx";
import { Page } from "../ui/Controls.jsx";
import { Empty } from "../ui/Common.jsx";

const fmt = (ms) => { try { return new Intl.DateTimeFormat("es", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(ms)); } catch { return new Date(ms).toLocaleString(); } };
export const rangeLabel = (a, b) => `${fmt(a)} → ${fmt(b)}`;

export async function watchCinema(id) {
  try {
    const out = await rpc("summary.cinema", { id });
    previewCine(out.cinema);
  } catch (e) { toast(e.message || String(e), "bad"); }
}

export function CinemaLinks({ cinemas, onWatch = watchCinema }) {
  if (!cinemas || !cinemas.length) return null;
  return (
    <div class="sum-cines">
      <span class="eyebrow"><Clapperboard size={13} /> Cinemáticas de este tramo</span>
      <div class="row wrap" style={{ gap: "6px" }}>
        {cinemas.map((c) => (
          <button key={c.id} class="btn btn-sm" type="button" onClick={() => onWatch(c.id)} data-testid="summary-watch">
            <Play size={13} /> {c.name} <span class="faint num">{new Date(c.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function SummariesPage() {
  const [list, setList] = useState(null);
  const [open, setOpen] = useState(0);
  const rev = summariesRev.value;
  useEffect(() => { rpc("summary.list").then((d) => setList(d.summaries)).catch((e) => toast(e.message, "bad")); }, [rev]);
  return (
    <Page title="Resúmenes" icon={BookOpen}>
      {list === null && <p class="faint">Cargando…</p>}
      {list && list.length === 0 && <Empty title="Todavía no hay resúmenes">Cuando el equipo de GM publique el resumen de una sesión, aparecerá aquí con sus cinemáticas.</Empty>}
      {list && list.map((s, i) => (
        <article class={`sum-card ${open === i ? "open" : ""}`} key={s.id} data-testid="summary">
          <button type="button" class="sum-head" onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i ? "true" : "false"}>
            <span class="grow"><strong>{s.title}</strong><span class="faint">{rangeLabel(s.from, s.to)}{s.cinemas.length ? ` · ${s.cinemas.length} cinemáticas` : ""}</span></span>
          </button>
          {open === i && (
            <div class="sum-body">
              <div class="md sum-text"><Markdown text={s.text} /></div>
              <CinemaLinks cinemas={s.cinemas} />
            </div>
          )}
        </article>
      ))}
    </Page>
  );
}
