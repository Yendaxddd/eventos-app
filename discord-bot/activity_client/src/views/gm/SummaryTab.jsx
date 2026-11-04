// GM · Resúmenes: connect an AI (any OpenAI-compatible API), pick a stretch of the event, and get a summary of what happened — with the
// cinematics that played in it linked. Edit it, then publish it in the players' «Resúmenes» (and, if wanted, in the event channel).
import { useEffect, useState } from "preact/hooks";
import { BookOpen, Bot, Clapperboard, Eye, EyeOff, KeyRound, Send, Sparkles, Trash2, Wand2, X } from "lucide-preact";
import { usePanel } from "../../panel/data.js";
import { Block, ConfirmButton, Empty, Field, Pill } from "../../ui/Common.jsx";
import { Markdown } from "../../md.jsx";
import { cx } from "../../util.js";
import { fromInput, toInput } from "../../agenda-model.js";
import { CinemaLinks, rangeLabel } from "../Summaries.jsx";
import { previewCine } from "../../cine.js";
import { rpc } from "../../net.js";
import { toast } from "../../state.js";
import { Card } from "./ui.jsx";
import { useDo } from "./hooks.js";

const HOUR = 3_600_000;
const endInput = (ms) => toInput(ms + 59_999);          // an end rounded up to the minute, so «now» includes what just happened
const PRESETS = [
  ["Última hora", () => [Date.now() - HOUR, Date.now()]],
  ["Últimas 3 h", () => [Date.now() - 3 * HOUR, Date.now()]],
  ["Hoy", () => { const d = new Date(); d.setHours(0, 0, 0, 0); return [d.getTime(), Date.now()]; }],
  ["Ayer", () => { const d = new Date(); d.setHours(0, 0, 0, 0); return [d.getTime() - 24 * HOUR, d.getTime()]; }],
];
const KNOWN = [
  ["OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"],
  ["OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"],
  ["Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"],
  ["Ollama (local)", "http://localhost:11434/v1", "llama3.1"],
  ["LM Studio (local)", "http://localhost:1234/v1", "local-model"],
];

function AiCard({ ai, run, busy, take }) {
  const [f, setF] = useState({ base_url: ai.base_url, model: ai.model, temperature: ai.temperature, prompt: ai.prompt, api_key: "" });
  useEffect(() => setF({ base_url: ai.base_url, model: ai.model, temperature: ai.temperature, prompt: ai.prompt, api_key: "" }), [ai.base_url, ai.model, ai.has_key]);
  const set = (patch) => setF((x) => ({ ...x, ...patch }));
  const save = async () => take(await run("ai", "gm.ai_set", { ...f, api_key: f.api_key || undefined }, "Conexión guardada."));
  const test = async () => {
    const out = await run("test", "gm.ai_test", {});
    if (out) toast(`La IA responde (${out.ms} ms): «${out.reply}»`, "ok", 5000);
  };
  return (
    <Card title="Conexión con la IA" icon={Bot} testid="ai-card"
      hint="Cualquier API compatible con OpenAI: OpenAI, OpenRouter, Groq, o una local como Ollama o LM Studio. La clave se queda en este ordenador; nadie la ve desde la Actividad."
      actions={<>{ai.has_key ? <Pill tone="ok" icon={KeyRound}>Clave {ai.key_hint}</Pill> : <Pill tone="warn" icon={KeyRound}>Sin clave</Pill>}</>}>
      <div class="row wrap gm-chips" role="group" aria-label="Proveedores conocidos">
        {KNOWN.map(([name, url, model]) => (
          <button key={name} type="button" class="choice" aria-pressed={f.base_url === url ? "true" : "false"} onClick={() => set({ base_url: url, model })}>{name}</button>
        ))}
      </div>
      <div class="sum-grid">
        <Field label="Dirección de la API" hint="Suele acabar en /v1"><input class="input" value={f.base_url} onInput={(e) => set({ base_url: e.currentTarget.value })} data-testid="ai-url" /></Field>
        <Field label="Modelo"><input class="input" value={f.model} onInput={(e) => set({ model: e.currentTarget.value })} data-testid="ai-model" /></Field>
        <Field label={ai.has_key ? "Cambiar la clave (déjala vacía para mantenerla)" : "Clave de la API"} hint="Las locales (Ollama, LM Studio) no la necesitan.">
          <input class="input" type="password" autocomplete="off" value={f.api_key} placeholder={ai.has_key ? "••••••••" : "sk-…"} onInput={(e) => set({ api_key: e.currentTarget.value })} data-testid="ai-key" />
        </Field>
        <Field label={`Creatividad: ${Number(f.temperature).toFixed(1)}`} hint="Baja: más fiel y seca. Alta: más narrativa.">
          <input class="range" type="range" min="0" max="1.5" step="0.1" value={f.temperature} onInput={(e) => set({ temperature: Number(e.currentTarget.value) })} />
        </Field>
      </div>
      <Field label="Instrucciones para la IA (opcional)" hint="Vacío: las de siempre (en español, en orden, sin inventar, mencionando las cinemáticas).">
        <textarea class="textarea" rows={3} value={f.prompt} placeholder={ai.default_prompt} onInput={(e) => set({ prompt: e.currentTarget.value })} />
      </Field>
      <div class="row wrap" style={{ gap: "8px", justifyContent: "flex-end" }}>
        {ai.has_key && <ConfirmButton class="btn-ghost" icon={X} confirm="Sí, quitarla" onConfirm={async () => take(await run("ai", "gm.ai_set", { clear_key: true }, "Clave quitada."))}>Quitar la clave</ConfirmButton>}
        <button class="btn btn-sm" type="button" disabled={busy === "test"} onClick={test} data-testid="ai-test"><Sparkles size={14} /> {busy === "test" ? "Probando…" : "Probar"}</button>
        <button class="btn btn-sm btn-primary" type="button" disabled={busy === "ai"} onClick={save} data-testid="ai-save">Guardar</button>
      </div>
    </Card>
  );
}

function MakeCard({ log, run, busy, take, last }) {
  const [range, setRange] = useState(() => [toInput(last ? last.to : Date.now() - 3 * HOUR), endInput(Date.now())]);
  const [title, setTitle] = useState("");
  const [style, setStyle] = useState("");
  const a = fromInput(range[0]), b = fromInput(range[1]);
  const inside = a && b ? log.filter((c) => c.at >= a && c.at <= b) : [];
  const make = async () => {
    if (!a || !b) { toast("Elige el principio y el final.", "bad"); return; }
    take(await run("make", "gm.summary_make", { from: a, to: b, title, style }, "Resumen listo: revísalo y publícalo."));
  };
  return (
    <Card title="Nuevo resumen" icon={Wand2} testid="summary-make" hint="La IA lee los mensajes del canal de ese tramo (y lo que dijeron las cinemáticas que se pusieron) y escribe un resumen. Tú lo revisas antes de publicarlo.">
      <div class="row wrap gm-chips" role="group" aria-label="Tramos rápidos">
        {PRESETS.map(([label, f]) => <button key={label} type="button" class="choice" onClick={() => { const [x, y] = f(); setRange([toInput(x), endInput(y)]); }}>{label}</button>)}
        {last && <button type="button" class="choice" onClick={() => setRange([toInput(last.to), endInput(Date.now())])}>Desde el último resumen</button>}
      </div>
      <div class="sum-grid">
        <Field label="Desde"><input class="input" type="datetime-local" value={range[0]} onInput={(e) => setRange([e.currentTarget.value, range[1]])} data-testid="summary-from" /></Field>
        <Field label="Hasta"><input class="input" type="datetime-local" value={range[1]} onInput={(e) => setRange([range[0], e.currentTarget.value])} data-testid="summary-to" /></Field>
        <Field label="Título (opcional)"><input class="input" value={title} maxLength={100} placeholder="Capítulo 3: el puente" onInput={(e) => setTitle(e.currentTarget.value)} /></Field>
        <Field label="Indicaciones para este resumen (opcional)"><input class="input" value={style} maxLength={600} placeholder="Corto, sin spoilers del final; resalta a Kuro" onInput={(e) => setStyle(e.currentTarget.value)} /></Field>
      </div>
      <p class="faint gm-hint"><Clapperboard size={13} /> {inside.length ? `Cinemáticas en este tramo: ${inside.map((c) => `«${c.name}»`).join(", ")}` : "Ninguna cinemática se puso en este tramo."}</p>
      <div class="row" style={{ justifyContent: "flex-end" }}>
        <button class="btn btn-primary" type="button" disabled={busy === "make"} onClick={make} data-testid="summary-go"><Wand2 size={16} /> {busy === "make" ? "Escribiendo… (puede tardar)" : "Hacer el resumen"}</button>
      </div>
    </Card>
  );
}

function SummaryEditor({ s, run, busy, take }) {
  const [title, setTitle] = useState(s.title);
  const [text, setText] = useState(s.text);
  const [view, setView] = useState("preview");
  useEffect(() => { setTitle(s.title); setText(s.text); }, [s.id, s.updated]);
  const dirty = title !== s.title || text !== s.text;
  const save = () => run("save", "gm.summary_save", { id: s.id, title, text }, s.published ? "Guardado: los jugadores ya ven el cambio." : "Guardado.").then(take);
  const watch = async (id) => {          // a game master can watch any cinematic of the stretch, published or not
    try { const out = await rpc("summary.cinema", { id }); previewCine(out.cinema); } catch { toast("Publica el resumen para poder verla desde aquí, o ábrela en Cinemáticas.", "info"); }
  };
  return (
    <div class="sum-editor" data-testid="summary-editor">
      <div class="row wrap" style={{ gap: "8px" }}>
        {s.published ? <Pill tone="ok" icon={Eye}>Publicado</Pill> : <Pill icon={EyeOff}>Borrador</Pill>}
        <span class="faint" style={{ fontSize: ".75rem" }}>{rangeLabel(s.from, s.to)} · {s.messages} mensajes · {s.model}</span>
        <span class="grow" />
        <div class="segmented" role="group" aria-label="Vista">
          <button type="button" aria-pressed={view === "preview" ? "true" : "false"} onClick={() => setView("preview")}>Vista</button>
          <button type="button" aria-pressed={view === "edit" ? "true" : "false"} onClick={() => setView("edit")}>Editar</button>
        </div>
      </div>
      <Field label="Título"><input class="input" value={title} maxLength={100} onInput={(e) => setTitle(e.currentTarget.value)} /></Field>
      {view === "edit"
        ? <textarea class="textarea sum-textarea" rows={16} value={text} onInput={(e) => setText(e.currentTarget.value)} data-testid="summary-text" />
        : <div class="md sum-text card-2"><Markdown text={text} /></div>}
      <CinemaLinks cinemas={s.cinemas} onWatch={watch} />
      <div class="row wrap" style={{ gap: "8px", justifyContent: "flex-end" }}>
        <ConfirmButton class="btn-ghost" icon={Trash2} label="Borrar el resumen" onConfirm={async () => take(await run("del", "gm.summary_delete", { id: s.id }, "Borrado."))} />
        {dirty && <button class="btn btn-sm" type="button" disabled={busy === "save"} onClick={save} data-testid="summary-save">Guardar</button>}
        {s.published
          ? <button class="btn btn-sm" type="button" onClick={async () => take(await run("post", "gm.summary_post", { id: s.id, on: false }, "Retirado."))}><EyeOff size={14} /> Retirar</button>
          : <>
            <ConfirmButton icon={Send} confirm="Sí, también en el canal" onConfirm={async () => { if (dirty) await save(); take(await run("post", "gm.summary_post", { id: s.id, on: true, channel: true }, "Publicado aquí y en el canal.")); }}>Publicar y enviar al canal</ConfirmButton>
            <button class="btn btn-sm btn-primary" type="button" disabled={busy === "post"} onClick={async () => { if (dirty) await save(); take(await run("post", "gm.summary_post", { id: s.id, on: true }, "Publicado: ya está en «Resúmenes».")); }} data-testid="summary-publish"><BookOpen size={14} /> Publicar</button>
          </>}
      </div>
    </div>
  );
}

export function SummaryTab() {
  const q = usePanel("gm.summary");
  const [busy, run] = useDo();
  const [open, setOpen] = useState(null);
  const take = (out) => { if (out) { q.replace(out); if (out.made) setOpen(out.made); } return out; };
  return (
    <Block q={q}>
      {(d) => {
        const current = d.summaries.find((s) => s.id === open);
        return (
          <div class="col gm-stack" data-testid="gm-summary">
            <AiCard ai={d.ai} run={run} busy={busy} take={take} />
            <MakeCard log={d.cinemaLog} run={run} busy={busy} take={take} last={d.summaries[0]} />
            <Card title="Resúmenes" icon={BookOpen}>
              {d.summaries.length === 0 && <Empty title="Ninguno todavía">Haz el primero arriba.</Empty>}
              <div class="rs-screens">
                {d.summaries.map((s) => (
                  <button type="button" key={s.id} class={cx("rs-screen-row rs-screen-open", open === s.id && "on")} onClick={() => setOpen(open === s.id ? null : s.id)}>
                    <strong>{s.title}</strong>
                    <span class="faint">{s.published ? "Publicado" : "Borrador"} · {rangeLabel(s.from, s.to)}{s.cinemas.length ? ` · ${s.cinemas.length} cinemáticas` : ""}</span>
                  </button>
                ))}
              </div>
              {current && <SummaryEditor key={current.id} s={current} run={run} busy={busy} take={take} />}
            </Card>
          </div>
        );
      }}
    </Block>
  );
}
