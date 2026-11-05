// An object from a form: its card (name, picture, rarity...), how it grows (steps of spins, each with its effects), and who has it.
import { useState } from "preact/hooks";
import { Gift, Plus, Save, Trash2, UserMinus, X } from "lucide-preact";
import { Modal } from "../../ui/Overlays.jsx";
import { Field, Pill } from "../../ui/Common.jsx";
import { OBJECT_TYPE, rarityOf } from "../../panel/format.js";
import { cdn } from "../../util.js";
import { Chips, NumberInput, PictureInput } from "./ui.jsx";
import { useDo } from "./hooks.js";

const TYPES = [["adaptation", "Adaptación"], ["passive", "Pasivo"], ["triggered", "Con disparador"], ["consumable", "Consumible"]];
const RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "mythic"];
const DIFFS = [["easy", "Fácil"], ["medium", "Media"], ["hard", "Difícil"], ["impossible", "Imposible"]];

// "heal:15" -> its template and number, so the step shows a menu and a box instead of a code
export function readEffect(text, catalogue) {
  for (const [tpl, label, n] of catalogue) {
    if (n === null && tpl === text) return { tpl, label, n: null, raw: text };
    if (n !== null) {
      const re = new RegExp(`^${tpl.replace(/[.*+?^$()|[\]\\]/g, "\\$&").replace("\\{n\\}", "{n}").replace("{n}", "(\\d+(?:\\.\\d+)?)")}$`);
      const m = re.exec(text);
      if (m) return { tpl, label, n: Number(m[1]), raw: text };
    }
  }
  return { tpl: "custom", label: "A mano", n: null, raw: text };
}
export const writeEffect = (e) => (e.tpl === "custom" ? e.raw : e.tpl.replace("{n}", String(e.n ?? 0)));

function Steps({ steps, onChange, catalogue, testid }) {
  const setStep = (i, patch) => onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  return (
    <div class="col" style={{ gap: "8px" }} data-testid={testid}>
      {steps.map((s, i) => (
        <div key={i} class="obj-step">
          <label class="row" style={{ gap: "6px" }}><span class="faint">Con</span>
            <NumberInput value={s.spins} min={0} max={9999} unit="giros" label="Giros necesarios" width="110px" onInput={(v) => setStep(i, { spins: Math.max(0, Math.round(Number(v) || 0)) })} testid={`${testid}-spins-${i}`} />
          </label>
          <div class="col grow" style={{ gap: "6px" }}>
            {s.effects.map((text, k) => {
              const e = readEffect(text, catalogue);
              const put = (next) => setStep(i, { effects: s.effects.map((x, m) => (m === k ? writeEffect(next) : x)) });
              return (
                <div key={k} class="row wrap" style={{ gap: "6px" }}>
                  <select class="select grow" value={e.tpl} aria-label="Efecto" data-testid={`${testid}-effect-${i}-${k}`}
                    onChange={(ev) => { const tpl = ev.currentTarget.value; const def = catalogue.find((c) => c[0] === tpl); put(tpl === "custom" ? { tpl, raw: text } : { tpl, n: def ? def[2] : null }); }}>
                    {catalogue.map(([tpl, label]) => <option key={tpl} value={tpl}>{label}</option>)}
                    <option value="custom">Escribirlo a mano…</option>
                  </select>
                  {e.tpl !== "custom" && e.n !== null && <NumberInput value={e.n} min={0} max={1000} label="Cantidad" width="100px" onInput={(v) => put({ ...e, n: Number(v) || 0 })} />}
                  {e.tpl === "custom" && <input class="input grow" value={e.raw} placeholder="efecto:valor" onInput={(ev) => put({ tpl: "custom", raw: ev.currentTarget.value.trim() })} />}
                  <button class="btn btn-sm btn-ghost" type="button" aria-label="Quitar efecto" onClick={() => setStep(i, { effects: s.effects.filter((_, m) => m !== k) })}><X size={14} /></button>
                </div>
              );
            })}
            <div class="row" style={{ gap: "6px" }}>
              <button class="btn btn-sm" type="button" onClick={() => setStep(i, { effects: [...s.effects, writeEffect({ tpl: catalogue[0][0], n: catalogue[0][2] })] })} data-testid={`${testid}-add-effect-${i}`}><Plus size={14} /> Efecto</button>
              <button class="btn btn-sm btn-ghost" type="button" onClick={() => onChange(steps.filter((_, j) => j !== i))} aria-label="Quitar este paso"><Trash2 size={14} /></button>
            </div>
          </div>
        </div>
      ))}
      <button class="btn btn-sm" type="button" onClick={() => onChange([...steps, { spins: (steps.length ? steps[steps.length - 1].spins : 0) + 5, effects: [] }])} data-testid={`${testid}-add`}><Plus size={14} /> Paso</button>
    </div>
  );
}

function startForm(obj) {
  if (!obj) return { creating: true, id: "", name: "", description: "", lore: "", type: "adaptation", rarity: "rare", slots: 1, tradeable: true, unique: false, image: "", emoji: "📦", color: "#a78bfa", tracking: "total", thresholds: [] };
  const display = obj.display || {};
  return { creating: false, id: obj.id, name: obj.name || "", description: obj.description || "", lore: obj.lore || "", type: obj.type, rarity: obj.rarity || "common",
    slots: obj.slots_required || 1, tradeable: obj.tradeable !== false, unique: !!obj.unique, image: obj.image_url || "", emoji: display.emoji || "📦", color: display.color || "#888888",
    tracking: (obj.tracking && obj.tracking.type) || "total", thresholds: obj.thresholds || [] };
}

export function ObjectForm({ loaded, players, effects, onClose, onSaved }) {
  const [f, setF] = useState(() => startForm(loaded && loaded.object));
  const [busy, run] = useDo();
  const [owners, setOwners] = useState(loaded ? loaded.owners : []);
  const [giveTo, setGiveTo] = useState("");
  const catalogue = (loaded && loaded.effects) || effects || [["heal:{n}", "Cura al llegar (PV)", 10]];
  const set = (patch) => setF((old) => ({ ...old, ...patch }));
  const total = f.tracking === "total";
  const thresholds = total ? (Array.isArray(f.thresholds) ? f.thresholds : []) : (Array.isArray(f.thresholds) ? {} : f.thresholds);
  const save = async () => {
    const out = await run("save", "gm.object_save", { object: { ...f, image: f.image || null, thresholds } }, f.creating ? "Objeto creado." : "Objeto guardado.");
    if (out) onSaved(out);
  };
  const give = async () => {
    if (!giveTo) return;
    const out = await run("give", "gm.obj_give", { id: giveTo, object: f.id }, "Objeto entregado.");
    if (out) setOwners([...owners, { id: giveTo, name: (players.find((p) => p.id === giveTo) || { name: giveTo }).name }]);
  };
  const take = async (o) => {
    const out = await run("take", "gm.obj_take", { id: o.id, object: f.id }, "Objeto retirado.");
    if (out) setOwners(owners.filter((x) => x.id !== o.id));
  };
  const rarity = rarityOf(f.rarity);
  return (
    <Modal title={f.creating ? "Nuevo objeto" : `Editar «${f.name}»`} onClose={onClose} wide
      actions={<><button class="btn btn-ghost" type="button" onClick={onClose}>Cerrar</button><button class="btn btn-primary" type="button" onClick={save} disabled={busy !== null} data-testid="obj-save"><Save size={15} /> Guardar</button></>}>
      <div class="col form" style={{ gap: "var(--sp-3)" }} data-testid="obj-form">
        <div class="obj-form-head" style={{ "--rarity": f.color || rarity.color }}>
          <span class="obj-icon big">{f.image ? <img src={cdn(f.image)} alt="" /> : f.emoji}</span>
          <div class="grow col" style={{ gap: "6px" }}>
            <div class="row wrap" style={{ gap: "8px" }}>
              <Field label="Nombre" class="grow"><input class="input" maxLength={80} value={f.name} onInput={(e) => set({ name: e.currentTarget.value })} data-testid="obj-name" /></Field>
              <Field label="Identificador"><input class="input" maxLength={40} value={f.id} disabled={!f.creating} placeholder="espada_lunar" onInput={(e) => set({ id: e.currentTarget.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} data-testid="obj-id" /></Field>
            </div>
            <div class="row wrap" style={{ gap: "6px" }}><Pill>{rarity.label}</Pill><Pill>{OBJECT_TYPE[f.type] || f.type}</Pill>{f.unique && <Pill tone="primary">Único</Pill>}</div>
          </div>
        </div>
        <div class="gm-grid">
          <Field label="Tipo"><select class="select" value={f.type} onChange={(e) => set({ type: e.currentTarget.value })} data-testid="obj-type">{TYPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Field>
          <Field label="Rareza"><select class="select" value={f.rarity} onChange={(e) => set({ rarity: e.currentTarget.value })}>{RARITIES.map((r) => <option key={r} value={r}>{rarityOf(r).label}</option>)}</select></Field>
          <Field label="Espacios"><NumberInput value={f.slots} min={1} max={10} label="Espacios" onInput={(v) => set({ slots: Number(v) || 1 })} /></Field>
          <Field label="Emoji y color"><span class="row" style={{ gap: "6px" }}><input class="input" maxLength={8} value={f.emoji} style={{ maxWidth: "70px" }} onInput={(e) => set({ emoji: e.currentTarget.value })} aria-label="Emoji" /><input type="color" value={f.color} onInput={(e) => set({ color: e.currentTarget.value })} aria-label="Color" /></span></Field>
        </div>
        <div class="row wrap" style={{ gap: "16px" }}>
          <label class="row" style={{ gap: "6px" }}><input type="checkbox" checked={f.unique} onChange={(e) => set({ unique: e.currentTarget.checked })} /> Único (solo una persona lo puede tener)</label>
          <label class="row" style={{ gap: "6px" }}><input type="checkbox" checked={f.tradeable} onChange={(e) => set({ tradeable: e.currentTarget.checked })} /> Se puede intercambiar</label>
        </div>
        <Field label="Descripción"><textarea class="textarea" maxLength={500} value={f.description} onInput={(e) => set({ description: e.currentTarget.value })} data-testid="obj-description" /></Field>
        <Field label="Historia (opcional)"><textarea class="textarea" maxLength={400} value={f.lore} onInput={(e) => set({ lore: e.currentTarget.value })} /></Field>
        <Field label="Imagen"><PictureInput value={f.image} onChange={(v) => set({ image: v })} testid="obj-image" /></Field>
        <Field label="Cómo crece" hint="Cada vez que el jugador hace *adapt* gana un giro. Al llegar a los giros de un paso, consigue sus efectos.">
          <Chips value={f.tracking} options={[["total", "Un solo contador"], ["per_difficulty", "Un contador por dificultad"]]} onChange={(v) => set({ tracking: v, thresholds: v === "total" ? [] : {} })} testid="obj-tracking" />
        </Field>
        {total ? <Steps steps={thresholds} onChange={(t) => set({ thresholds: t })} catalogue={catalogue} testid="obj-steps" /> : DIFFS.map(([d, label]) => (
          <div key={d} class="col" style={{ gap: "6px" }}><b>{label}</b>
            <Steps steps={thresholds[d] || []} onChange={(t) => set({ thresholds: { ...thresholds, [d]: t } })} catalogue={catalogue} testid={`obj-steps-${d}`} />
          </div>
        ))}
        {!f.creating && (
          <Field label="Quién lo tiene">
            <div class="col" style={{ gap: "6px" }} data-testid="obj-owners">
              {owners.length === 0 && <span class="faint">Nadie todavía.</span>}
              {owners.map((o) => <div key={o.id} class="row" style={{ gap: "8px" }}><span class="grow">{o.name}</span><button class="btn btn-sm btn-ghost" type="button" onClick={() => take(o)} disabled={busy !== null}><UserMinus size={14} /> Quitar</button></div>)}
              <div class="row" style={{ gap: "6px" }}>
                <select class="select grow" value={giveTo} onChange={(e) => setGiveTo(e.currentTarget.value)} aria-label="Dar a" data-testid="obj-give-to">
                  <option value="">— dárselo a… —</option>
                  {players.filter((p) => !owners.some((o) => o.id === p.id)).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <button class="btn btn-sm" type="button" onClick={give} disabled={!giveTo || busy !== null} data-testid="obj-give"><Gift size={14} /> Dar</button>
              </div>
            </div>
          </Field>
        )}
      </div>
    </Modal>
  );
}
