import { useRef, useState } from "preact/hooks";
import { Download, Drama, Pencil, Plus, Trash2, Upload, UserPlus, Zap } from "lucide-preact";
import { charAvatars, toast } from "../../state.js";
import { uploadImage } from "../../net.js";
import { Avatar } from "../../ui/Avatar.jsx";
import { Modal } from "../../ui/Overlays.jsx";
import { Block, ConfirmButton, Empty, Field, Pill } from "../../ui/Common.jsx";
import { act, usePanel } from "../../panel/data.js";
import { TupperImport } from "./TupperImport.jsx";
import { POWER_TYPE, duration } from "../../panel/format.js";
import { KINDS, MAX_PARTS, PRESETS, compose, describe, effectSummary, freshPart, parse } from "../../power-model.js";
import { cdn, cx } from "../../util.js";

const COOLDOWNS = [30, 60, 120, 300, 600];
const SLOT_NAME = { 1: "Poder 1 · de lore", 2: "Poder 2 · de historia" };

const SHOW = [["all", "Todos"], ["self", "Solo yo"], ["off", "Nadie"]];

// The effects of a power, as rows the player builds (or the text of an effect the builder cannot show, kept as it is).
function EffectBuilder({ parts, setParts, text, setText, meta, type }) {
  const advanced = parts === null;
  const kinds = Object.keys(KINDS);
  const change = (i, patch) => setParts(parts.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const lines = advanced ? [] : describe(parts, meta.multiplier || 1, meta.cap || 500);
  return (
    <div class="col power-builder" style={{ gap: "8px" }} data-testid="power-builder">
      {advanced ? (
        <div class="row" style={{ gap: "8px" }}>
          <select class="select" value="custom" data-testid="power-effect-kind" style={{ maxWidth: "190px" }}
            onChange={(e) => { const k = e.currentTarget.value; if (k !== "custom") setParts([freshPart(k)]); }}>
            {kinds.map((k) => <option key={k} value={k}>{KINDS[k][0]}</option>)}<option value="custom">Avanzado (texto)</option>
          </select>
          <input class="input" maxLength={160} value={text} data-testid="power-effect-text" onInput={(e) => setText(e.currentTarget.value)} placeholder="damage:80;stun:3" />
        </div>
      ) : parts.map((p, i) => (
        <div key={i} class="power-row" data-testid={`power-row-${i}`}>
          <select class="select" value={p.kind} data-testid={i === 0 ? "power-effect-kind" : `power-effect-kind-${i}`}
            onChange={(e) => { const k = e.currentTarget.value; if (k === "custom") setText(compose(parts)); else setParts(parts.map((q, j) => (j === i ? freshPart(k) : q))); }}>
            {kinds.map((k) => <option key={k} value={k}>{KINDS[k][0]}</option>)}
            {i === 0 && <option value="custom">Avanzado (texto)</option>}
          </select>
          {KINDS[p.kind][1].map(([key, label, unit, min, max, step], f) => (
            <label key={key} class="num-input" title={label}>
              <input class="input num" type="number" min={min} max={max} step={step} value={p[key]} aria-label={label}
                data-testid={i === 0 && f === 0 ? "power-effect-amount" : `power-effect-${i}-${key}`}
                onInput={(e) => change(i, { [key]: Math.max(min, Math.min(max, Number(e.currentTarget.value) || 0)) })} />
              <i aria-hidden="true">{unit}</i>
            </label>
          ))}
          {parts.length > 1 && <button class="btn btn-sm btn-ghost" type="button" aria-label="Quitar este efecto" onClick={() => setParts(parts.filter((_, j) => j !== i))}><Trash2 size={14} /></button>}
        </div>
      ))}
      <div class="row wrap" style={{ gap: "6px" }}>
        {!advanced && parts.length < MAX_PARTS && <button class="btn btn-sm" type="button" onClick={() => setParts([...parts, freshPart("heal")])} data-testid="power-add-effect"><Plus size={14} /> Otro efecto</button>}
        <button class="btn btn-sm btn-ghost" type="button" onClick={() => setParts(parse(PRESETS[type] || "damage:80"))} data-testid="power-suggest">Sugerir para «{POWER_TYPE[type] || type}»</button>
      </div>
      {!advanced && (
        <div class="power-preview-box" data-testid="power-preview">
          <span class="field-label">Al usarlo</span>
          {lines.map((l) => <div key={l}>{l}</div>)}
          {(meta.multiplier || 1) !== 1 && parts.some((p) => p.kind === "damage" || p.kind === "damage_all") && (
            <small class="faint">Tu daño ahora va ×{(meta.multiplier || 1).toFixed(2)} (arma, mejoras y venganza).</small>
          )}
        </div>
      )}
    </div>
  );
}

function PowerEditor({ character, slot, power, types, meta, onClose, onSaved }) {
  const [f, setF] = useState({
    name: power ? power.name : "", description: power ? power.description : "", type: power ? power.type : types[0] || "destructive",
    cooldown: power ? power.cooldown : 60, trigger: power && power.trigger ? power.trigger : "", image: power && power.image ? power.image : "",
    show: power && power.show ? power.show : "all",
  });
  const [parts, setParts] = useState(() => (power ? parse(power.effect) : [freshPart("damage")]));
  const [text, setText] = useState(() => (power ? power.effect : ""));
  const [busy, setBusy] = useState(null);
  const picker = useRef(null);
  const set = (patch) => setF((old) => ({ ...old, ...patch }));
  const code = parts ? compose(parts) : text.trim();
  const setTextMode = (value) => { setParts(null); setText(value); };

  const upload = async (e) => {
    const picked = e.currentTarget.files && e.currentTarget.files[0];
    e.currentTarget.value = "";
    if (!picked) return;
    setBusy("upload");
    try { set({ image: await uploadImage(picked) }); toast("Imagen subida.", "ok"); } catch (error) { toast(error.message, "bad", 4500); }
    setBusy(null);
  };
  const save = async () => {
    setBusy("save");
    const out = await act("panel.power", { character, slot, ...f, effect: code }, "Poder guardado.");
    setBusy(null);
    if (out) onSaved(out);
  };

  return (
    <Modal title={`${power ? "Editar" : "Nuevo"} poder · ${character}`} onClose={onClose}
      actions={<><button class="btn btn-ghost" type="button" onClick={onClose}>Cancelar</button>
        <button class="btn btn-primary" type="button" onClick={save} disabled={busy !== null} data-testid="power-save">{busy === "save" ? "Guardando…" : "Guardar poder"}</button></>}>
      <div class="col form" style={{ gap: "var(--sp-3)" }} data-testid="power-editor">
        <p class="faint" style={{ fontSize: ".8125rem" }}>{SLOT_NAME[slot]}. Se activa en combate con <span class="kbd">*power{slot}*</span> cuando tienes la carga completa.</p>
        <Field label="Nombre"><input class="input" maxLength={50} value={f.name} onInput={(e) => set({ name: e.currentTarget.value })} placeholder="p. ej. Corte dimensional" data-testid="power-name" /></Field>
        <Field label="Qué hace" hint="Una frase o dos: es lo que se verá en el canal al usarlo.">
          <textarea class="textarea" maxLength={900} value={f.description} onInput={(e) => set({ description: e.currentTarget.value })} data-testid="power-description" />
        </Field>
        <Field label="Tipo">
          <select class="select" value={f.type} onChange={(e) => set({ type: e.currentTarget.value })} data-testid="power-type">
            {types.map((t) => <option key={t} value={t}>{POWER_TYPE[t] || t}</option>)}
          </select>
        </Field>
        <Field label="Efecto en el combate" hint="Hasta 4 efectos a la vez. Los números son reales: el bot los aplica tal cual (el daño, con tu arma y tus mejoras).">
          <EffectBuilder parts={parts} setParts={setParts} text={text} setText={setTextMode} meta={meta || {}} type={f.type} />
        </Field>
        <Field label="Recarga (segundos)" hint={`Tarda ${duration(f.cooldown)} en poder usarse otra vez, contando solo el tiempo de combate.`}>
          <div class="row wrap" style={{ gap: "6px" }}>
            <input class="input" type="number" min={0} max={86400} value={f.cooldown} style={{ maxWidth: "120px" }} data-testid="power-cooldown" onInput={(e) => set({ cooldown: Number(e.currentTarget.value) })} />
            {COOLDOWNS.map((c) => <button key={c} type="button" class="choice" aria-pressed={f.cooldown === c ? "true" : "false"} onClick={() => set({ cooldown: c })}>{duration(c)}</button>)}
          </div>
        </Field>
        <Field label="Frase que lo activa (opcional)" hint="Si alguien escribe esta frase en el canal, el poder se lanza solo. Ejemplo: «expansión de dominio».">
          <input class="input" maxLength={100} value={f.trigger} onInput={(e) => set({ trigger: e.currentTarget.value })} data-testid="power-trigger" />
        </Field>
        <Field label="Imagen o GIF (opcional)" hint="Aparece al lanzar el poder. Pega un enlace de Discord o sube una imagen (máx. 8 MB).">
          <div class="row" style={{ gap: "8px" }}>
            <input class="input" type="url" placeholder="https://…" value={f.image} onInput={(e) => set({ image: e.currentTarget.value.trim() })} data-testid="power-image" />
            <button class="btn" type="button" onClick={() => picker.current && picker.current.click()} disabled={busy !== null}><Upload size={16} />{busy === "upload" ? "Subiendo…" : "Subir"}</button>
            <input ref={picker} type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden onChange={upload} data-testid="power-file" />
          </div>
          {f.image && <img class="power-preview" src={cdn(f.image)} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
        </Field>
        <Field label="Quién ve la imagen en pantalla" hint="En la Actividad, la imagen o el GIF llena la pantalla un momento al lanzar el poder.">
          <div class="row wrap gm-chips" role="group" aria-label="Quién ve la imagen">
            {SHOW.map(([v, t]) => <button key={v} type="button" class="choice" aria-pressed={f.show === v ? "true" : "false"} onClick={() => set({ show: v })} data-testid={`power-show-${v}`}>{t}</button>)}
          </div>
        </Field>
      </div>
    </Modal>
  );
}

function Power({ character, slot, power, types, meta, replace }) {
  const [editing, setEditing] = useState(false);
  const close = () => setEditing(false);
  const remove = async () => {
    const out = await act("panel.unpower", { character, slot }, "Poder quitado.");
    if (out) replace(out);
  };
  return (
    <div class={cx("power", !power && "empty")} data-testid={`power-${character}-${slot}`}>
      <div class="power-head">
        <Zap size={14} /><b>{SLOT_NAME[slot]}</b>
      </div>
      {power ? (
        <>
          <div class="power-title">
            {power.image && <img class="power-thumb" src={cdn(power.image)} alt="" />}
            <strong class="display">{power.name}</strong>
          </div>
          <p>{power.description}</p>
          <div class="row wrap" style={{ gap: "6px" }}>
            <Pill>{POWER_TYPE[power.type] || power.type}</Pill>
            <Pill tone="warn">Recarga {duration(power.cooldown)}</Pill>
            <Pill tone="info">{effectSummary(power.effect, (meta && meta.multiplier) || 1, (meta && meta.cap) || 500)}</Pill>
            {power.trigger && <Pill tone="primary">«{power.trigger}»</Pill>}
          </div>
          <div class="row" style={{ gap: "6px", marginTop: "6px" }}>
            <button class="btn btn-sm" type="button" onClick={() => setEditing(true)} data-testid={`power-edit-${character}-${slot}`}><Pencil size={14} /> Editar</button>
            <ConfirmButton icon={Trash2} confirm="Sí, quitar" onConfirm={remove} class="btn-ghost">Quitar</ConfirmButton>
          </div>
        </>
      ) : (
        <>
          <p class="faint">Aún no tiene poder en esta ranura.</p>
          <button class="btn btn-sm" type="button" onClick={() => setEditing(true)} data-testid={`power-add-${character}-${slot}`}><Plus size={14} /> Crear poder</button>
        </>
      )}
      {editing && <PowerEditor character={character} slot={slot} power={power} types={types} meta={meta} onClose={close} onSaved={(out) => { replace(out); close(); }} />}
    </div>
  );
}

function Character({ c, types, meta, replace }) {
  const picture = c.avatar || charAvatars.value[c.name];
  const drop = async () => {
    const out = await act("panel.unregister", { name: c.name }, `«${c.name}» ya no está registrado.`);
    if (out) replace(out);
  };
  return (
    <article class="char" data-testid={`char-${c.name}`}>
      <header class="char-head">
        <Avatar url={picture} name={c.name} size="lg" />
        <strong class="display grow ellipsis" title={c.name}>{c.name}</strong>
        <ConfirmButton icon={Trash2} confirm="Sí, quitar" onConfirm={drop} class="btn-ghost" testid={`char-drop-${c.name}`}>Quitar</ConfirmButton>
      </header>
      <div class="powers">
        {[1, 2].map((slot) => <Power key={slot} character={c.name} slot={slot} power={c.powers[`power${slot}`]} types={types} meta={meta} replace={replace} />)}
      </div>
    </article>
  );
}

function Register({ d, replace }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const submit = async (value) => {
    const text = String(value === undefined ? name : value).trim();
    if (!text) return;
    setBusy(true);
    const out = await act("panel.register", { name: text }, `«${text}» registrado.`);
    setBusy(false);
    if (out) { replace(out); setName(""); }
  };
  return (
    <section class="card-2" data-testid="register">
      <div class="card-title"><UserPlus size={16} /><strong class="display">Registrar un personaje</strong></div>
      <form class="row" style={{ gap: "8px" }} onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input class="input" value={name} maxLength={80} placeholder="Nombre exacto, tal como sale en Tupperbox" onInput={(e) => setName(e.currentTarget.value)} data-testid="register-name" aria-label="Nombre del personaje" />
        <button class="btn btn-primary" type="submit" disabled={busy || !name.trim()} data-testid="register-submit"><Plus size={16} /> Registrar</button>
      </form>
      <div style={{ marginTop: "var(--sp-2)" }}>
        <button class="btn btn-sm" type="button" onClick={() => setImporting(true)} data-testid="tupper-open"><Download size={14} /> Importar de Tupperbox</button>
      </div>
      {importing && <TupperImport d={d} replace={replace} onClose={() => setImporting(false)} />}
      <p class="faint" style={{ fontSize: ".75rem", marginTop: "var(--sp-2)" }}>Debe escribirse igual que en Tupperbox (con sus mayúsculas, emojis y símbolos). Solo puedes registrar hasta {d.max} personajes.</p>
      {d.suggestions.length > 0 && (
        <div class="suggest" data-testid="suggestions">
          <span class="faint" style={{ fontSize: ".75rem" }}>Se han visto hablando en el canal y nadie los tiene registrados:</span>
          <div class="row wrap" style={{ gap: "6px" }}>
            {d.suggestions.map((n) => <button key={n} type="button" class="choice" onClick={() => submit(n)} disabled={busy} data-testid={`suggest-${n}`}><Plus size={12} /> {n}</button>)}
          </div>
        </div>
      )}
    </section>
  );
}

function Characters({ d, replace }) {
  return (
    <div class="dash-col" data-testid="characters">
      <Register d={d} replace={replace} />
      {d.characters.length === 0
        ? <Empty icon={Drama} title="Todavía no tienes personajes">Registra el nombre de tu personaje de Tupperbox para poder escribir como él y darle poderes.</Empty>
        : d.characters.map((c) => <Character key={c.name} c={c} types={d.types} meta={d} replace={replace} />)}
    </div>
  );
}

export function CharactersTab() {
  const q = usePanel("panel.characters");
  return <Block q={q}>{(d) => <Characters d={d} replace={q.replace} />}</Block>;
}
