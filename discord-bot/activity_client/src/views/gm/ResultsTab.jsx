// GM · Resultados: the round as it goes (what each player did), and the results screens — made from the round or from scratch,
// edited block by block, shown to everybody and edited again while they are on screen (every save updates all screens at once).
import { useEffect, useState } from "preact/hooks";
import {
  ArrowDown, ArrowUp, Award, ClipboardList, Eye, EyeOff, FilePlus2, ListOrdered, Plus, RotateCcw, Save, Table2, Trash2, Trophy, Type, Wand2, X,
} from "lucide-preact";
import { usePanel } from "../../panel/data.js";
import { Block, ConfirmButton, Empty, Field, Pill } from "../../ui/Common.jsx";
import { Switch } from "../../ui/Controls.jsx";
import { AWARD_ICONS, ResultsBody } from "../../ui/Results.jsx";
import { cx } from "../../util.js";
import { Card } from "./ui.jsx";
import { useDo } from "./hooks.js";

const BLOCKS = [
  ["podium", "Podio", Trophy, () => ({ type: "podium", title: "Podio", entries: [{ name: "", value: "" }, { name: "", value: "" }, { name: "", value: "" }] })],
  ["awards", "Premios", Award, () => ({ type: "awards", title: "Premios", items: [{ icon: "trophy", title: "", name: "", value: "" }] })],
  ["text", "Texto", Type, () => ({ type: "text", title: "", body: "" })],
  ["list", "Lista", ListOrdered, () => ({ type: "list", title: "Recompensas", items: [{ name: "", text: "" }] })],
  ["stats", "Tabla", Table2, () => ({ type: "stats", title: "Estadísticas", columns: [], rows: [] })],
];
const KIND = Object.fromEntries(BLOCKS.map(([k, label, Icon]) => [k, { label, Icon }]));
const blank = () => ({ id: "", title: "Resultados del capítulo", subtitle: "", blocks: [BLOCKS[2][3]()] });
const swap = (list, i, j) => { const out = list.slice(); [out[i], out[j]] = [out[j], out[i]]; return out; };
const setAt = (list, i, value) => list.map((x, j) => (j === i ? value : x));

// rows of a block (podium entries, awards, list items): edit, add, remove
function Rows({ items, make, max, render, onChange, addLabel }) {
  return (
    <div class="rs-ed-rows">
      {items.map((it, i) => (
        <div class="rs-ed-row" key={i}>
          {render(it, (patch) => onChange(setAt(items, i, { ...it, ...patch })))}
          <button class="btn btn-sm btn-ghost" type="button" aria-label="Quitar" onClick={() => onChange(items.filter((_, j) => j !== i))}><X size={14} /></button>
        </div>
      ))}
      {items.length < max && <button class="btn btn-sm btn-ghost" type="button" onClick={() => onChange([...items, make()])}><Plus size={14} /> {addLabel}</button>}
    </div>
  );
}

const In = ({ value, onInput, placeholder, grow, max = 80 }) => (
  <input class={cx("input input-sm", grow && "grow")} value={value} maxLength={max} placeholder={placeholder} onInput={(e) => onInput(e.currentTarget.value)} />
);

function BlockEditor({ block, onChange }) {
  const set = (patch) => onChange({ ...block, ...patch });
  switch (block.type) {
    case "podium":
      return <Rows items={block.entries} max={3} addLabel="Puesto" make={() => ({ name: "", value: "" })} onChange={(entries) => set({ entries })}
        render={(e, edit) => <><span class="rs-ed-place num">{block.entries.indexOf(e) + 1}º</span><In grow value={e.name} placeholder="Jugador" onInput={(name) => edit({ name })} /><In value={e.value} placeholder="120 pts" max={40} onInput={(value) => edit({ value })} /></>} />;
    case "awards":
      return <Rows items={block.items} max={12} addLabel="Premio" make={() => ({ icon: "trophy", title: "", name: "", value: "" })} onChange={(items) => set({ items })}
        render={(a, edit) => (
          <>
            <select class="select input-sm" value={a.icon} aria-label="Icono" onChange={(e) => edit({ icon: e.currentTarget.value })}>
              {Object.keys(AWARD_ICONS).map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
            <In grow value={a.title} placeholder="Premio (Mejor estratega)" max={60} onInput={(title) => edit({ title })} />
            <In value={a.name} placeholder="Jugador" max={60} onInput={(name) => edit({ name })} />
            <In value={a.value} placeholder="Detalle" max={60} onInput={(value) => edit({ value })} />
          </>
        )} />;
    case "text":
      return <textarea class="textarea" rows={3} maxLength={2000} value={block.body} placeholder="Lo que se decidió, lo que viene, una frase para cerrar el capítulo…" onInput={(e) => set({ body: e.currentTarget.value })} />;
    case "list":
      return <Rows items={block.items} max={24} addLabel="Línea" make={() => ({ name: "", text: "" })} onChange={(items) => set({ items })}
        render={(it, edit) => <><In value={it.name} placeholder="Quién (opcional)" max={60} onInput={(name) => edit({ name })} /><In grow value={it.text} placeholder="Qué (+50 monedas, la espada rota…)" max={200} onInput={(text) => edit({ text })} /></>} />;
    case "stats":
      return block.rows.length
        ? <p class="faint gm-hint">{block.rows.length} jugadores · {block.columns.map((c) => c[1]).join(", ")}. La tabla viene de la ronda; puedes quitarla o moverla.</p>
        : <p class="faint gm-hint">Tabla vacía: crea la pantalla «Desde la ronda» para llenarla con los datos del juego.</p>;
    default:
      return null;
  }
}

function Editor({ screen, showing, onSaved, run, busy }) {
  const [draft, setDraft] = useState(screen);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { setDraft(screen); setDirty(false); }, [screen.id, screen.updated]);
  const edit = (patch) => { setDraft((d) => ({ ...d, ...patch })); setDirty(true); };
  const blocks = draft.blocks;
  const setBlocks = (next) => edit({ blocks: next });
  const save = async () => {
    const out = await run("save", "gm.results_save", { screen: draft }, showing ? "Guardado: todos ven el cambio." : "Guardado.");
    if (out) { setDirty(false); onSaved(out); }
  };
  const live = showing === draft.id;
  return (
    <div class="rs-editor" data-testid="results-editor">
      <div class="rs-ed-main">
        <div class="row wrap" style={{ gap: "8px" }}>
          {live ? <Pill tone="ok" icon={Eye}>En pantalla</Pill> : <Pill icon={EyeOff}>Oculta</Pill>}
          {dirty && <Pill tone="warn">Sin guardar</Pill>}
          <span class="grow" />
          <button class="btn btn-sm btn-primary" type="button" disabled={busy === "save" || !dirty} onClick={save} data-testid="results-save"><Save size={14} /> {live ? "Guardar y actualizar" : "Guardar"}</button>
        </div>
        <Field label="Título"><input class="input" value={draft.title} maxLength={80} onInput={(e) => edit({ title: e.currentTarget.value })} /></Field>
        <Field label="Subtítulo"><input class="input" value={draft.subtitle} maxLength={160} placeholder="Capítulo 3 · La decisión del puente" onInput={(e) => edit({ subtitle: e.currentTarget.value })} /></Field>
        {blocks.map((b, i) => {
          const K = KIND[b.type] || KIND.text;
          return (
            <div class="rs-ed-block" key={b.id || i}>
              <div class="rs-ed-block-head">
                <K.Icon size={14} />
                <input class="input input-sm grow" value={b.title} maxLength={80} placeholder={K.label} aria-label="Título del bloque" onInput={(e) => setBlocks(setAt(blocks, i, { ...b, title: e.currentTarget.value }))} />
                <button class="btn btn-sm btn-ghost" type="button" aria-label="Subir" disabled={i === 0} onClick={() => setBlocks(swap(blocks, i, i - 1))}><ArrowUp size={14} /></button>
                <button class="btn btn-sm btn-ghost" type="button" aria-label="Bajar" disabled={i === blocks.length - 1} onClick={() => setBlocks(swap(blocks, i, i + 1))}><ArrowDown size={14} /></button>
                <button class="btn btn-sm btn-ghost" type="button" aria-label="Quitar el bloque" onClick={() => setBlocks(blocks.filter((_, j) => j !== i))}><Trash2 size={14} /></button>
              </div>
              <BlockEditor block={b} onChange={(nb) => setBlocks(setAt(blocks, i, nb))} />
            </div>
          );
        })}
        {blocks.length < 16 && (
          <div class="row wrap rs-ed-add" style={{ gap: "6px" }}>
            <span class="faint" style={{ fontSize: ".75rem" }}>Añadir:</span>
            {BLOCKS.filter(([k]) => k !== "stats").map(([k, label, Icon, make]) => (
              <button key={k} class="btn btn-sm btn-ghost" type="button" onClick={() => setBlocks([...blocks, make()])} data-testid={`results-add-${k}`}><Icon size={14} /> {label}</button>
            ))}
          </div>
        )}
      </div>
      <div class="rs-ed-preview" aria-label="Vista previa">
        <span class="eyebrow">Así lo verán</span>
        <div class="rs-card rs-preview"><ResultsBody screen={draft} /></div>
      </div>
    </div>
  );
}

function RoundCard({ round, onBuild, onReset, busy, auto, onAuto }) {
  const rows = round.rows;
  return (
    <Card title={round.title} icon={ClipboardList} testid="results-round"
      hint="Lo que cada jugador hizo desde que empezó la ronda (un combate empieza una nueva). Cuando cae el jefe se crea una pantalla sola."
      actions={<>
        <button class="btn btn-sm btn-primary" type="button" disabled={busy === "build"} onClick={onBuild} data-testid="results-build"><Wand2 size={14} /> Pantalla desde la ronda</button>
        <ConfirmButton icon={RotateCcw} confirm="Sí, empezar de cero" onConfirm={onReset} label="Empezar una ronda nueva">Nueva ronda</ConfirmButton>
      </>}>
      <label class="row" style={{ gap: "8px", fontSize: ".8125rem" }}>
        <Switch label="Mostrar sola al caer el jefe" checked={auto} onChange={onAuto} />
        <span>Mostrarla a todos sola al caer el jefe</span>
      </label>
      {round.boss && <p class="faint gm-hint">{round.boss.name}: {round.boss.damage} de daño recibido{round.boss.defeated ? " · derrotado" : ""}</p>}
      {rows.length === 0 ? <Empty title="Sin datos todavía">Lanza un QTE o empieza un combate: aquí aparecerá quién hace qué.</Empty> : (
        <div class="rs-table-wrap">
          <table class="rs-table">
            <thead><tr><th>Jugador</th>{round.stats.filter(([k]) => rows.some((r) => r[k])).map(([k, l]) => <th key={k} class="num">{l}</th>)}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}><td>{r.name}</td>{round.stats.filter(([k]) => rows.some((x) => x[k])).map(([k]) => <td key={k} class="num">{r[k] || "·"}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function ResultsTab() {
  const q = usePanel("gm.results");
  const [busy, run] = useDo();
  const [open, setOpen] = useState(null);           // the screen being edited (its id, or "new")
  const take = (out) => { if (out) { q.replace(out); if (out.made) setOpen(out.made); } return out; };
  return (
    <Block q={q}>
      {(d) => {
        const screen = open === "new" ? blank() : d.screens.find((s) => s.id === open);
        return (
          <div class="col gm-stack" data-testid="gm-results">
            <RoundCard round={d.round} busy={busy} auto={d.auto}
              onBuild={async () => take(await run("build", "gm.results_build", {}, "Pantalla creada con los datos de la ronda."))}
              onReset={async () => take(await run("reset", "gm.results_reset", {}, "Ronda nueva."))}
              onAuto={async (on) => take(await run("auto", "gm.results_auto", { on }))} />
            <Card title="Pantallas de resultados" icon={Trophy}
              hint="Créalas, edítalas y enséñalas cuando quieras: después de un capítulo, de una decisión o de un jefe. Si editas la que está en pantalla, todos ven el cambio al guardar."
              actions={<button class="btn btn-sm" type="button" onClick={() => setOpen("new")} data-testid="results-new"><FilePlus2 size={14} /> En blanco</button>}>
              {d.screens.length === 0 && open !== "new" && <Empty title="Ninguna todavía">Crea una desde la ronda o en blanco.</Empty>}
              <div class="rs-screens">
                {d.screens.map((s) => (
                  <div class={cx("rs-screen-row", open === s.id && "on")} key={s.id}>
                    <button type="button" class="grow rs-screen-open" onClick={() => setOpen(open === s.id ? null : s.id)}>
                      <strong>{s.title}</strong>
                      <span class="faint">{s.blocks.length} bloques{s.by ? ` · ${s.by}` : ""} · {new Date(s.updated).toLocaleString()}</span>
                    </button>
                    {d.showing === s.id
                      ? <button class="btn btn-sm" type="button" disabled={busy === "hide"} onClick={async () => take(await run("hide", "gm.results_hide", {}, "Quitada de las pantallas."))}><EyeOff size={14} /> Ocultar</button>
                      : <button class="btn btn-sm btn-primary" type="button" disabled={busy === "show"} onClick={async () => take(await run("show", "gm.results_show", { id: s.id }, "Todos la están viendo."))} data-testid="results-show"><Eye size={14} /> Mostrar</button>}
                    <ConfirmButton icon={Trash2} class="btn-ghost" label="Borrar" onConfirm={async () => { take(await run("delete", "gm.results_delete", { id: s.id }, "Borrada.")); if (open === s.id) setOpen(null); }} />
                  </div>
                ))}
              </div>
              {screen && <Editor key={screen.id || "new"} screen={screen} showing={d.showing} busy={busy} run={run} onSaved={take} />}
            </Card>
          </div>
        );
      }}
    </Block>
  );
}
