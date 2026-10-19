import { useRef, useState } from "preact/hooks";
import { Drama, Pencil, Plus, Trash2, Upload, UserPlus, Zap } from "lucide-preact";
import { charAvatars, toast } from "../../state.js";
import { uploadImage } from "../../net.js";
import { Avatar } from "../../ui/Avatar.jsx";
import { Modal } from "../../ui/Overlays.jsx";
import { Block, ConfirmButton, Empty, Field, Pill } from "../../ui/Common.jsx";
import { act, usePanel } from "../../panel/data.js";
import { EFFECT_KINDS, POWER_TYPE, buildEffect, duration, effectLabel, parseEffect } from "../../panel/format.js";
import { cdn, cx } from "../../util.js";

const COOLDOWNS = [30, 60, 120, 300, 600];
const SLOT_NAME = { 1: "Poder 1 · de lore", 2: "Poder 2 · de historia" };

// the effect as the editor shows it: damage / heal / stun get a simple form, anything else stays text
function startEffect(power) {
  if (!power) return { kind: "damage", a: 50 };
  const e = parseEffect(power.effect);
  return e.kind === "buff" || e.kind === "custom" ? { kind: "custom", text: power.effect } : e;
}

function PowerEditor({ character, slot, power, types, onClose, onSaved }) {
  const [f, setF] = useState({
    name: power ? power.name : "", description: power ? power.description : "", type: power ? power.type : types[0] || "destructive",
    cooldown: power ? power.cooldown : 60, trigger: power && power.trigger ? power.trigger : "", image: power && power.image ? power.image : "",
  });
  const [effect, setEffect] = useState(() => startEffect(power));
  const [busy, setBusy] = useState(null);
  const picker = useRef(null);
  const set = (patch) => setF((old) => ({ ...old, ...patch }));
  const code = buildEffect(effect);

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
        <Field label="Efecto en el combate" hint={effect.kind === "custom" ? "Formatos: damage:50 · heal:30 · stun · buff:damage_boost:20:30" : effectLabel(code)}>
          <div class="row" style={{ gap: "8px" }}>
            <select class="select" value={effect.kind} data-testid="power-effect-kind"
              onChange={(e) => { const kind = e.currentTarget.value; setEffect(kind === "custom" ? { kind, text: code } : kind === "stun" ? { kind } : { kind, a: effect.a || 50 }); }}>
              {EFFECT_KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            {(effect.kind === "damage" || effect.kind === "heal") && (
              <input class="input" type="number" min={0} max={999999} step={5} value={effect.a} style={{ maxWidth: "130px" }} data-testid="power-effect-amount"
                onInput={(e) => setEffect({ kind: effect.kind, a: Number(e.currentTarget.value) })} />
            )}
            {effect.kind === "custom" && <input class="input" maxLength={100} value={effect.text} data-testid="power-effect-text" onInput={(e) => setEffect({ kind: "custom", text: e.currentTarget.value })} />}
          </div>
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
      </div>
    </Modal>
  );
}

function Power({ character, slot, power, types, replace }) {
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
            <Pill tone="info">{effectLabel(power.effect)}</Pill>
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
      {editing && <PowerEditor character={character} slot={slot} power={power} types={types} onClose={close} onSaved={(out) => { replace(out); close(); }} />}
    </div>
  );
}

function Character({ c, types, replace }) {
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
        {[1, 2].map((slot) => <Power key={slot} character={c.name} slot={slot} power={c.powers[`power${slot}`]} types={types} replace={replace} />)}
      </div>
    </article>
  );
}

function Register({ d, replace }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
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
        : d.characters.map((c) => <Character key={c.name} c={c} types={d.types} replace={replace} />)}
    </div>
  );
}

export function CharactersTab() {
  const q = usePanel("panel.characters");
  return <Block q={q}>{(d) => <Characters d={d} replace={q.replace} />}</Block>;
}
