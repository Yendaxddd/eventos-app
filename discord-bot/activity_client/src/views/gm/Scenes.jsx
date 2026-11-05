// GM · Evento · Escena: which QTEs come up on their own for the kind of moment the event is in (scenes.py). A boss fight wants parries
// and Black Flashes; a chase wants dodging, swiping and mashing. One tap switches it for everybody, in the middle of the event.
import { useState } from "preact/hooks";
import { Clapperboard, Pencil, Plus, RotateCcw, Trash2 } from "lucide-preact";
import { usePanel } from "../../panel/data.js";
import { parseNumber } from "../../panel/format.js";
import { Block, ConfirmButton, Field } from "../../ui/Common.jsx";
import { Switch } from "../../ui/Controls.jsx";
import { Card, NumberInput } from "./ui.jsx";
import { useDo } from "./hooks.js";

const SHORT = { standard: "Parry", evade: "Esquivar", combo: "Combo", direction: "Dirección", fake: "Trampa", flick: "Deslizar", drag: "Arrastrar", mash: "Machacar" };
const GESTURES = ["flick", "drag", "mash"];

function SceneCard({ s, active, onUse, onEdit, busy }) {
  const kinds = Object.entries(s.weights).filter(([, w]) => w > 0);
  const parry = (s.weights.standard || 0) > 0 || (s.weights.combo || 0) > 0;
  return (
    <div class="scene-card" role="button" tabIndex={0} aria-pressed={active ? "true" : "false"} style={{ "--scene": s.color }} data-testid={`scene-${s.id}`}
      onClick={() => !busy && !active && onUse(s.id)} onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !active) { e.preventDefault(); onUse(s.id); } }}>
      <div class="row" style={{ gap: "6px", alignItems: "center" }}>
        <strong class="grow ellipsis">{s.name}</strong>
        <button class="btn btn-sm btn-ghost" type="button" aria-label={`Editar «${s.name}»`} onClick={(e) => { e.stopPropagation(); onEdit(s); }}><Pencil size={13} /></button>
      </div>
      {s.note && <span class="faint">{s.note}</span>}
      <div class="scene-kinds">{kinds.map(([k, w]) => <span key={k}>{SHORT[k] || k} {w}</span>)}</div>
      <span class="faint">{[parry ? "con parry" : "sin parry", s.counter ? "con contraataque" : "sin contraataque"].join(" · ")}{active ? " · ACTIVA" : ""}</span>
    </div>
  );
}

function Editor({ start, kinds, onClose, run, take }) {
  const [d, setD] = useState(start);
  const set = (patch) => setD((old) => ({ ...old, ...patch }));
  const weight = (k, text) => setD((old) => ({ ...old, weights: { ...old.weights, [k]: Math.max(0, Math.min(100, Math.round(parseNumber(text) ?? 0))) } }));
  const total = Object.values(d.weights).reduce((a, b) => a + (b || 0), 0);
  const save = async () => { const out = await run("save", "gm.scene_save", { scene: d }, "Escena guardada."); if (out) { take(out); onClose(); } };
  const remove = async () => { const out = await run("del", "gm.scene_delete", { id: d.id }, "Escena borrada."); if (out) { take(out); onClose(); } };
  return (
    <div class="col" style={{ gap: "var(--sp-3)" }} data-testid="scene-editor">
      <div class="row wrap" style={{ gap: "8px" }}>
        <Field label="Nombre" class="grow"><input class="input" maxLength={40} value={d.name} onInput={(e) => set({ name: e.currentTarget.value })} data-testid="scene-name" /></Field>
        <Field label="Color"><input class="input" type="color" value={d.color} onInput={(e) => set({ color: e.currentTarget.value })} style={{ width: "64px", padding: "2px" }} /></Field>
      </div>
      <Field label="Para qué es (lo ven los jugadores al pasar el ratón)"><input class="input" maxLength={160} value={d.note} onInput={(e) => set({ note: e.currentTarget.value })} /></Field>
      <span class="field-label">Probabilidad de cada QTE (0 = nunca sale)</span>
      <div class="scene-weights">
        {kinds.map((k) => (
          <label key={k.id} class="field">
            <span class="field-label">{k.label}{GESTURES.includes(k.id) ? " ·  Actividad" : ""}</span>
            <NumberInput value={d.weights[k.id] || 0} min={0} max={100} step={5} label={`Probabilidad de ${k.label}`} testid={`scene-w-${k.id}`} onInput={(t) => weight(k.id, t)} />
          </label>
        ))}
      </div>
      <p class="faint gm-hint">«Solo esquivar» es el QTE normal sin parry (y sin Black Flash). Deslizar, arrastrar y machacar solo existen en la Actividad:
        a quien juegue desde el canal le sale un QTE de dirección (o de esquivar) en su lugar.</p>
      <label class="row" style={{ gap: "8px", alignItems: "center" }}>
        <Switch checked={d.counter} onChange={(counter) => set({ counter })} label="Contraataque tras esquivar rápido" />
        <span>Contraataque tras esquivar rápido</span>
      </label>
      <div class="row wrap" style={{ gap: "8px" }}>
        <button class="btn btn-primary" type="button" disabled={!d.name.trim() || total === 0} onClick={save} data-testid="scene-save">Guardar</button>
        <button class="btn btn-ghost" type="button" onClick={onClose}>Cancelar</button>
        {d.id && <ConfirmButton icon={Trash2} class="btn-ghost" confirm="Sí, borrar" label={`Borrar «${d.name}»`} onConfirm={remove} />}
      </div>
    </div>
  );
}

export function ScenesCard() {
  const q = usePanel("gm.scenes");
  const [busy, run] = useDo();
  const [editing, setEditing] = useState(null);
  const take = (out) => q.replace(out);
  const use = async (id) => { const out = await run("use", "gm.scene_use", { id }, id ? "Escena cambiada: todos la ven." : "Sin escena: QTE en modo clásico."); if (out) take(out); };
  return (
    <Card title="Escena" icon={Clapperboard} testid="gm-scenes"
      hint="Qué QTE salen solos en este momento del evento. En una huida no hay parry ni contraataque; en el jefe, sí. Vale para los QTE automáticos, F9-F12, las habilidades del jefe y los enemigos."
      actions={!editing && <button class="btn btn-sm" type="button" onClick={() => setEditing({ id: "", name: "Nueva escena", color: "#a78bfa", note: "", counter: true, weights: { evade: 50, direction: 50 } })} data-testid="scene-new"><Plus size={14} /> Nueva</button>}>
      <Block q={q}>
        {(d) => editing
          ? <Editor start={editing} kinds={d.kinds} onClose={() => setEditing(null)} run={run} take={take} />
          : (
            <div class="col" style={{ gap: "var(--sp-2)" }}>
              <div class="scene-list">
                <div class="scene-card" role="button" tabIndex={0} aria-pressed={!d.active ? "true" : "false"} data-testid="scene-none"
                  onClick={() => d.active && !busy && use("")} onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && d.active) { e.preventDefault(); use(""); } }}>
                  <strong>Sin escena</strong>
                  <span class="faint">Manda el «modo de los QTE automáticos» de abajo, como siempre.{!d.active ? " · ACTIVA" : ""}</span>
                </div>
                {d.scenes.map((s) => <SceneCard key={s.id} s={s} active={d.active === s.id} onUse={use} onEdit={setEditing} busy={busy !== null} />)}
              </div>
              <div><button class="btn btn-sm btn-ghost" type="button" disabled={busy !== null} onClick={async () => { const out = await run("presets", "gm.scene_presets", {}, "Escenas de serie restauradas."); if (out) take(out); }}>
                <RotateCcw size={14} /> Restaurar las de serie (Jefe, Combate, Huida, Esquivar)</button></div>
            </div>
          )}
      </Block>
    </Card>
  );
}
