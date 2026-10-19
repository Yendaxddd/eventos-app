import { useMemo, useRef, useState } from "preact/hooks";
import { ArrowLeft, Clapperboard, Copy, Eye, ImagePlus, MessageSquare, Pencil, Play, Plus, Save, Sparkles, Square, Trash2, Type, Volume2, X, Zap } from "lucide-preact";
import { Block, ConfirmButton, Empty, Pill } from "../../ui/Common.jsx";
import { Switch } from "../../ui/Controls.jsx";
import { uploadCinemaImage } from "../../net.js";
import { toast } from "../../state.js";
import { previewCine } from "../../cine.js";
import { STEP_LABELS, durationOf, newStep } from "../../cinema-model.js";
import { cdn, cx, plural } from "../../util.js";
import { Card, NumberInput } from "./ui.jsx";
import { useDo, useLive } from "./hooks.js";

const ICON = { text: Type, audio: Volume2, image: ImagePlus, scene: Sparkles, effect: Zap, post: MessageSquare };
const TEXT_EFFECTS = [["type", "Se va escribiendo"], ["fade", "Aparece entera"], ["shake", "Tiembla"]];
const AUDIO_MODES = [["play", "Suena una vez"], ["music", "Empieza música"], ["stop_music", "Para la música"]];
const EFFECTS = [["flash", "Destello"], ["shake", "Temblor"], ["blackout", "Fundido a negro"]];

const num = (v, fallback = 0) => { const n = Number(v); return Number.isFinite(n) ? n : fallback; };

// The draft as the screen plays it: numbers as numbers, unfinished steps left out, in time order, with its length.
export function playable(draft, keepPosts = false) {
  const steps = draft.steps.map((s) => ({ ...s, at: num(s.at), duration: s.duration === undefined ? undefined : num(s.duration, 3), dim: s.dim === undefined ? undefined : num(s.dim, 40), volume: s.volume === undefined ? undefined : num(s.volume, 100) }))
    .filter((s) => (s.type === "text" ? s.text && s.text.trim() : s.type === "image" ? s.image : s.type === "audio" ? s.mode === "stop_music" || s.sound : s.type === "post" ? keepPosts && s.text && s.text.trim() : true))
    .map((s) => (s.type === "text" ? { ...s, duration: s.duration || 3, color: s.color || null, avatar: s.avatar || null } : s))
    .sort((a, b) => a.at - b.at);
  return { ...draft, steps, bg: draft.bg || "#000000", duration: durationOf(steps.length ? steps : [{ at: 0, duration: 1 }]) };
}

function StepImage({ value, onChange, label }) {
  const picker = useRef(null);
  const [busy, setBusy] = useState(false);
  const upload = async (e) => {
    const file = e.currentTarget.files && e.currentTarget.files[0];
    e.currentTarget.value = "";
    if (!file) return;
    setBusy(true);
    try { onChange(await uploadCinemaImage(file)); } catch (error) { toast(error.message, "bad", 5000); }
    setBusy(false);
  };
  return (
    <div class="row" style={{ gap: "8px" }}>
      {value ? <img class="cine-thumb" src={cdn(value)} alt="" /> : <span class="cine-thumb empty" aria-hidden="true"><ImagePlus size={16} /></span>}
      <button class="btn btn-sm" type="button" onClick={() => picker.current && picker.current.click()} disabled={busy} data-testid="cine-image-upload">{busy ? "Subiendo…" : value ? "Cambiar" : label}</button>
      {value && <button class="btn btn-sm btn-ghost" type="button" onClick={() => onChange("")} aria-label="Quitar imagen"><X size={14} /></button>}
      <input ref={picker} type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden onChange={upload} data-testid="cine-image-file" />
    </div>
  );
}

function StepCard({ step, index, d, update, remove, duplicate }) {
  const Icon = ICON[step.type];
  const set = (patch) => update(index, patch);
  return (
    <div class={cx("cine-step", `t-${step.type}`)} data-testid={`cine-step-${index}`} id={`cine-step-${index}`}>
      <div class="cine-step-head">
        <span class="cine-step-icon"><Icon size={16} /></span>
        <strong>{STEP_LABELS[step.type]}</strong>
        <label class="cine-at">en el segundo <NumberInput value={step.at} min={0} max={3600} step={0.5} unit="s" label={`Momento del paso ${index + 1}`} testid={`cine-at-${index}`} width="110px" onInput={(v) => set({ at: v })} /></label>
        <span class="grow" />
        <button class="btn btn-sm btn-ghost" type="button" onClick={() => duplicate(index)} aria-label="Duplicar paso" title="Duplicar"><Copy size={14} /></button>
        <button class="btn btn-sm btn-ghost" type="button" onClick={() => remove(index)} aria-label="Quitar paso" title="Quitar" data-testid={`cine-remove-${index}`}><Trash2 size={14} /></button>
      </div>
      {step.type === "text" && (
        <div class="col" style={{ gap: "8px" }}>
          <div class="gm-grid">
            <label class="field"><span class="field-label">Quién habla</span><input class="input" maxLength={60} value={step.speaker} placeholder="(nadie: texto de narrador)" onInput={(e) => set({ speaker: e.currentTarget.value })} data-testid={`cine-speaker-${index}`} /></label>
            <label class="field"><span class="field-label">Cuánto se ve</span><NumberInput value={step.duration} min={0.5} max={600} step={0.5} unit="s" label="Duración" onInput={(v) => set({ duration: v })} /></label>
            <label class="field"><span class="field-label">Cómo aparece</span>
              <select class="select" value={step.effect} onChange={(e) => set({ effect: e.currentTarget.value })}>{TEXT_EFFECTS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
            <label class="field"><span class="field-label">Tamaño</span>
              <select class="select" value={step.size} onChange={(e) => set({ size: e.currentTarget.value })}><option value="normal">Normal</option><option value="big">Grande (títulos)</option></select></label>
          </div>
          <textarea class="textarea" maxLength={600} value={step.text} placeholder="Lo que se dice…" onInput={(e) => set({ text: e.currentTarget.value })} data-testid={`cine-text-${index}`} aria-label="Texto" />
          <div class="row wrap" style={{ gap: "12px" }}>
            <label class="row" style={{ gap: "6px" }}><span class="faint">Color del texto</span><input type="color" value={step.color || "#ffffff"} onInput={(e) => set({ color: e.currentTarget.value })} aria-label="Color del texto" /></label>
            <StepImage value={step.avatar} onChange={(avatar) => set({ avatar })} label="Retrato" />
          </div>
        </div>
      )}
      {step.type === "audio" && (
        <div class="gm-grid">
          <label class="field"><span class="field-label">Qué hace</span>
            <select class="select" value={step.mode} onChange={(e) => set({ mode: e.currentTarget.value })} data-testid={`cine-mode-${index}`}>{AUDIO_MODES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
          {step.mode !== "stop_music" && (
            <>
              <label class="field"><span class="field-label">Sonido de la biblioteca</span>
                <select class="select" value={step.sound} onChange={(e) => set({ sound: e.currentTarget.value })} data-testid={`cine-sound-${index}`}>
                  <option value="">— elige uno —</option>
                  {d.sounds.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select></label>
              <label class="field"><span class="field-label">Volumen</span><NumberInput value={step.volume} min={0} max={100} step={5} unit="%" label="Volumen" onInput={(v) => set({ volume: v })} /></label>
            </>
          )}
        </div>
      )}
      {step.type === "image" && (
        <div class="gm-grid">
          <label class="field"><span class="field-label">Imagen</span><StepImage value={step.image} onChange={(image) => set({ image })} label="Subir imagen" /></label>
          <label class="field"><span class="field-label">Cuánto se ve</span><NumberInput value={step.duration} min={0.5} max={600} step={0.5} unit="s" label="Duración" onInput={(v) => set({ duration: v })} /></label>
          <label class="field"><span class="field-label">Dónde</span>
            <select class="select" value={step.position} onChange={(e) => set({ position: e.currentTarget.value })}><option value="center">Centro</option><option value="left">Izquierda</option><option value="right">Derecha</option></select></label>
        </div>
      )}
      {step.type === "scene" && (
        <div class="gm-grid">
          <label class="field"><span class="field-label">Color de fondo</span><input type="color" value={step.color || "#000000"} onInput={(e) => set({ color: e.currentTarget.value })} aria-label="Color de fondo" /></label>
          <label class="field"><span class="field-label">Imagen de fondo</span><StepImage value={step.image} onChange={(image) => set({ image })} label="Subir fondo" /></label>
          <label class="field"><span class="field-label">Oscurecer</span><NumberInput value={step.dim} min={0} max={100} step={5} unit="%" label="Oscurecer" onInput={(v) => set({ dim: v })} /></label>
        </div>
      )}
      {step.type === "effect" && (
        <div class="gm-grid">
          <label class="field"><span class="field-label">Efecto</span>
            <select class="select" value={step.effect} onChange={(e) => set({ effect: e.currentTarget.value })}>{EFFECTS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
          <label class="field"><span class="field-label">Dura</span><NumberInput value={step.duration} min={0.1} max={30} step={0.1} unit="s" label="Duración" onInput={(v) => set({ duration: v })} /></label>
          {step.effect !== "shake" && <label class="field"><span class="field-label">Color</span><input type="color" value={step.color || "#ffffff"} onInput={(e) => set({ color: e.currentTarget.value })} aria-label="Color" /></label>}
        </div>
      )}
      {step.type === "post" && (
        <div class="col" style={{ gap: "6px" }}>
          <textarea class="textarea" maxLength={1500} value={step.text} placeholder="El mensaje que el bot escribe en el canal del evento…" onInput={(e) => set({ text: e.currentTarget.value })} data-testid={`cine-post-${index}`} aria-label="Mensaje al canal" />
          <span class="faint gm-hint">Sale en el canal a esa hora, sin mencionar a nadie. Los jugadores que no estén en la Actividad también lo leen.</span>
        </div>
      )}
    </div>
  );
}

function Timeline({ draft }) {
  const view = playable(draft, true);
  const total = Math.max(view.duration - 1, 1);
  return (
    <div class="cine-timeline" data-testid="cine-timeline" role="img" aria-label={`Línea de tiempo de ${Math.round(total)} segundos con ${view.steps.length} pasos`}>
      <div class="cine-track">
        {view.steps.map((s, i) => (
          <i key={i} class={cx("cine-mark", `t-${s.type}`)} style={{ left: `${Math.min(100, (s.at / total) * 100)}%`, width: s.duration ? `${Math.max(0.8, Math.min(100, (s.duration / total) * 100))}%` : undefined }} title={`${STEP_LABELS[s.type]} · ${s.at} s`} />
        ))}
      </div>
      <div class="cine-scale faint"><span>0 s</span><span>{Math.round(total)} s</span></div>
    </div>
  );
}

function Editor({ start, d, onClose, replace }) {
  const [draft, setDraft] = useState(start);
  const [busy, run] = useDo();
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(start), [draft, start]);
  const set = (patch) => setDraft((old) => ({ ...old, ...patch }));
  const sorted = (steps) => steps.map((s, i) => [s, i]).sort((a, b) => num(a[0].at) - num(b[0].at) || a[1] - b[1]).map((x) => x[0]);
  const update = (i, patch) => setDraft((old) => ({ ...old, steps: old.steps.map((s, k) => (k === i ? { ...s, ...patch } : s)) }));
  const remove = (i) => setDraft((old) => ({ ...old, steps: old.steps.filter((_, k) => k !== i) }));
  const duplicate = (i) => setDraft((old) => ({ ...old, steps: sorted([...old.steps, { ...old.steps[i], at: num(old.steps[i].at) + 1 }]) }));
  const add = (type) => setDraft((old) => ({ ...old, steps: [...old.steps, newStep(type, old.steps.map((s) => ({ ...s, at: num(s.at), duration: num(s.duration, 0) })))] }));
  const toggleTrigger = (id) => set({ triggers: draft.triggers.includes(id) ? draft.triggers.filter((t) => t !== id) : [...draft.triggers, id] });
  const save = async () => {
    const out = await run("save", "gm.cinema_save", { cinema: { ...draft, steps: sorted(draft.steps) } }, "Cinemática guardada.");
    if (out) { replace(out); onClose(out.saved); }
  };
  return (
    <div class="dash-col" data-testid="cine-editor">
      <Card title={draft.id ? "Editar cinemática" : "Nueva cinemática"} icon={Clapperboard} testid="cine-editor-card"
        actions={<button class="btn btn-sm btn-ghost" type="button" onClick={() => onClose(null)} data-testid="cine-back"><ArrowLeft size={14} /> Volver</button>}>
        <div class="col" style={{ gap: "var(--sp-3)" }}>
          <label class="field"><span class="field-label">Nombre</span><input class="input" maxLength={80} value={draft.name} onInput={(e) => set({ name: e.currentTarget.value })} placeholder="p. ej. Llegada del Rey" data-testid="cine-name" /></label>
          <div class="row wrap" style={{ gap: "16px" }}>
            <label class="row" style={{ gap: "8px" }}><Switch label="Barras de cine" checked={draft.bars} onChange={(v) => set({ bars: v })} /><span>Barras de cine</span></label>
            <label class="row" style={{ gap: "8px" }}><Switch label="Se puede saltar" checked={draft.skippable} onChange={(v) => set({ skippable: v })} /><span>Cada jugador puede saltarla</span></label>
            <label class="row" style={{ gap: "8px" }}><span class="faint">Fondo</span><input type="color" value={draft.bg || "#000000"} onInput={(e) => set({ bg: e.currentTarget.value })} aria-label="Color de fondo de la cinemática" /></label>
          </div>
          <div class="col" style={{ gap: "6px" }}>
            <span class="field-label">Empieza sola cuando… <span class="faint">(si no marcas nada, solo la pones tú)</span></span>
            <div class="row wrap gm-chips">
              {d.events.map((e) => <button key={e.id} type="button" class="choice" aria-pressed={draft.triggers.includes(e.id) ? "true" : "false"} onClick={() => toggleTrigger(e.id)} data-testid={`cine-trigger-${e.id}`}>{e.label}</button>)}
            </div>
          </div>
        </div>
      </Card>
      <Card title="Pasos" icon={Type} hint="Cada paso ocurre en un segundo de la línea de tiempo. Se ordenan solos al guardar." testid="cine-steps"
        actions={<button class="btn btn-sm" type="button" onClick={() => previewCine(playable(draft))} data-testid="cine-preview"><Eye size={14} /> Ver aquí</button>}>
        <Timeline draft={draft} />
        <div class="col" style={{ gap: "10px", marginTop: "var(--sp-3)" }}>
          {draft.steps.map((step, i) => <StepCard key={i} step={step} index={i} d={d} update={update} remove={remove} duplicate={duplicate} />)}
          {draft.steps.length === 0 && <p class="faint">Todavía no hay pasos: añade el primero.</p>}
        </div>
        <div class="row wrap" style={{ gap: "6px", marginTop: "var(--sp-3)" }} data-testid="cine-add">
          {Object.keys(STEP_LABELS).map((type) => { const Icon = ICON[type]; return <button key={type} class="btn btn-sm" type="button" onClick={() => add(type)} data-testid={`cine-add-${type}`}><Icon size={14} /> {STEP_LABELS[type]}</button>; })}
        </div>
      </Card>
      <div class="row" style={{ gap: "8px", justifyContent: "flex-end" }}>
        <button class="btn btn-ghost" type="button" onClick={() => onClose(null)}>Cancelar</button>
        <button class="btn btn-primary" type="button" onClick={save} disabled={busy !== null || (!dirty && !!draft.id)} data-testid="cine-save"><Save size={16} /> Guardar</button>
      </div>
    </div>
  );
}

const BLANK = () => ({ id: "", name: "", steps: [newStep("scene", []), { ...newStep("text", [{ at: 0, duration: 1 }]), text: "Escribe aquí lo que se dice…" }], triggers: [], bg: "#000000", bars: true, skippable: true });

function List({ d, replace, edit }) {
  const [busy, run] = useDo();
  const play = async (c) => { const out = await run(`play-${c.id}`, "gm.cinema_play", { id: c.id }, `«${c.name}» suena y se ve para todos.`); if (out) replace(out); };
  const stop = async () => { const out = await run("stop", "gm.cinema_stop", {}, "Cinemática parada."); if (out) replace(out); };
  const copy = async (c) => { const out = await run(`copy-${c.id}`, "gm.cinema_duplicate", { id: c.id }, "Cinemática duplicada."); if (out) replace(out); };
  const del = async (c) => { const out = await run(`del-${c.id}`, "gm.cinema_delete", { id: c.id }, `«${c.name}» borrada.`); if (out) replace(out); };
  const auto = async (enabled) => { const out = await run("auto", "gm.cinema_auto", { enabled }); if (out) replace(out); };
  return (
    <div class="dash-col" data-testid="cine-list">
      <Card title="Cinemáticas" icon={Clapperboard} testid="cine-card"
        hint="Escenas con texto, imágenes y sonido en el momento exacto, para todos a la vez. Pónlas tú o ligalas a lo que pasa (aparece el jefe, cae el jefe, un dominio…)."
        actions={<button class="btn btn-sm btn-primary" type="button" onClick={() => edit(BLANK())} data-testid="cine-new"><Plus size={14} /> Nueva</button>}>
        <div class="row" style={{ gap: "10px", marginBottom: "var(--sp-3)" }}>
          <Switch label="Cinemáticas automáticas" checked={d.autoplay} onChange={auto} />
          <span>Que empiecen solas cuando pasa lo que tienen ligado</span>
        </div>
        {d.cinemas.length === 0
          ? <Empty icon={Clapperboard} title="Todavía no hay cinemáticas">Crea la primera: un texto, un sonido y un momento.</Empty>
          : d.cinemas.map((c) => (
            <div key={c.id} class={cx("cine-item", d.running === c.id && "is-running")} data-testid={`cine-item-${c.id}`}>
              <div class="info">
                <strong class="ellipsis">{c.name}</strong>
                <span class="faint">{plural(c.steps.length, "paso", "pasos")} · {Math.round(c.duration - 1)} s</span>
                <div class="row wrap" style={{ gap: "4px" }}>{c.triggers.map((t) => <Pill key={t} tone="info">{(d.events.find((e) => e.id === t) || { label: t }).label}</Pill>)}</div>
              </div>
              {d.running === c.id
                ? <button class="btn btn-sm btn-danger" type="button" onClick={stop} data-testid={`cine-stop-${c.id}`}><Square size={14} /> Parar</button>
                : <button class="btn btn-sm btn-primary" type="button" onClick={() => play(c)} disabled={busy !== null} data-testid={`cine-play-${c.id}`}><Play size={14} /> Poner</button>}
              <button class="btn btn-sm" type="button" onClick={() => edit({ ...c, steps: c.steps.map((s) => ({ ...s, color: s.color || "", avatar: s.avatar || "", image: s.image || "" })) })} data-testid={`cine-edit-${c.id}`}><Pencil size={14} /> Editar</button>
              <button class="btn btn-sm btn-ghost" type="button" onClick={() => copy(c)} aria-label={`Duplicar «${c.name}»`} title="Duplicar"><Copy size={14} /></button>
              <ConfirmButton icon={Trash2} confirm="Sí, borrar" onConfirm={() => del(c)} class="btn-ghost" testid={`cine-delete-${c.id}`} label={`Borrar «${c.name}»`} />
            </div>
          ))}
      </Card>
    </div>
  );
}

export function CinemaTab() {
  const q = useLive("gm.cinemas", {}, 4000);
  const [editing, setEditing] = useState(null);
  return (
    <Block q={q}>
      {(d) => (editing
        ? <Editor key={editing.id || "new"} start={editing} d={d} replace={q.replace} onClose={() => setEditing(null)} />
        : <List d={d} replace={q.replace} edit={setEditing} />)}
    </Block>
  );
}
