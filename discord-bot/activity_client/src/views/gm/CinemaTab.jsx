import { useMemo, useRef, useState } from "preact/hooks";
import { ArrowLeft, Check, ChevronLeft, ChevronRight, Clapperboard, Copy, Eye, ImagePlus, Loader2, MessageSquare, Pencil, Play, Plus, Sparkles, Square, Trash2, TriangleAlert, Type, Volume2, X, Zap } from "lucide-preact";
import { Block, ConfirmButton, Empty, Pill } from "../../ui/Common.jsx";
import { Range, Switch } from "../../ui/Controls.jsx";
import { uploadCinemaImage } from "../../net.js";
import { toast } from "../../state.js";
import { previewCine } from "../../cine.js";
import { LANES, STEP_LABELS, draggedTo, durationOf, newStep, orderOf, rulerTicks, validate } from "../../cinema-model.js";
import { PRESETS, PRESET_IDS } from "../../fx-model.js";
import { playBinding } from "../../vfx.js";
import { act } from "../../panel/data.js";
import { cdn, cx, plural } from "../../util.js";
import { Card, NumberInput } from "./ui.jsx";
import { useAutosave, useDo, useLive } from "./hooks.js";

const ICON = { text: Type, audio: Volume2, image: ImagePlus, scene: Sparkles, effect: Zap, vfx: Zap, post: MessageSquare };
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

// ---- one step's form (only the selected step shows one) -----------------------------------------------------------------------
function StepForm({ step, d, set }) {
  return (
    <>
      {step.type === "text" && (
        <div class="col" style={{ gap: "8px" }}>
          <div class="gm-grid">
            <label class="field"><span class="field-label">Quién habla</span><input class="input" maxLength={60} value={step.speaker} placeholder="(nadie: texto de narrador)" onInput={(e) => set({ speaker: e.currentTarget.value })} data-testid="cine-speaker" /></label>
            <label class="field"><span class="field-label">Cuánto se ve</span><NumberInput value={step.duration} min={0.5} max={600} step={0.5} unit="s" label="Duración" testid="cine-duration" onInput={(v) => set({ duration: v })} /></label>
            <label class="field"><span class="field-label">Cómo aparece</span>
              <select class="select" value={step.effect} onChange={(e) => set({ effect: e.currentTarget.value })}>{TEXT_EFFECTS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
            <label class="field"><span class="field-label">Tamaño</span>
              <select class="select" value={step.size} onChange={(e) => set({ size: e.currentTarget.value })}><option value="normal">Normal</option><option value="big">Grande (títulos)</option></select></label>
          </div>
          <textarea class="textarea" maxLength={600} value={step.text} placeholder="Lo que se dice…" onInput={(e) => set({ text: e.currentTarget.value })} data-testid="cine-text" aria-label="Texto" />
          <div class="row wrap" style={{ gap: "12px" }}>
            <label class="row" style={{ gap: "6px" }}><span class="faint">Color del texto</span><input type="color" value={step.color || "#ffffff"} onInput={(e) => set({ color: e.currentTarget.value })} aria-label="Color del texto" /></label>
            <StepImage value={step.avatar} onChange={(avatar) => set({ avatar })} label="Retrato" />
          </div>
        </div>
      )}
      {step.type === "audio" && (
        <div class="gm-grid">
          <label class="field"><span class="field-label">Qué hace</span>
            <select class="select" value={step.mode} onChange={(e) => set({ mode: e.currentTarget.value })} data-testid="cine-mode">{AUDIO_MODES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
          {step.mode !== "stop_music" && (
            <>
              <label class="field"><span class="field-label">Sonido de la biblioteca</span>
                <select class="select" value={step.sound} onChange={(e) => set({ sound: e.currentTarget.value })} data-testid="cine-sound">
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
      {step.type === "vfx" && (
        <div class="col" style={{ gap: "8px" }}>
          <div class="fx-presets" role="group" aria-label="Efecto visual">
            {PRESET_IDS.filter((p) => p !== "ninguno").map((p) => (
              <button key={p} type="button" class="fx-preset" aria-pressed={step.preset === p ? "true" : "false"} data-testid={`cine-vfx-${p}`} onClick={() => set({ preset: p })}><i style={{ background: PRESETS[p].color }} />{PRESETS[p].label}</button>
            ))}
          </div>
          <div class="fx-grid">
            <label class="field"><span class="field-label">Color</span><input type="color" value={step.color || (PRESETS[step.preset] || PRESETS.explosion).color} onInput={(e) => set({ color: e.currentTarget.value })} aria-label="Color del efecto" /></label>
            <label class="field"><span class="field-label">Fuerza</span><Range label="Fuerza" min={25} max={200} step={5} value={step.intensity} onChange={(v) => set({ intensity: v })} format={(v) => `${v} %`} /></label>
            <label class="field"><span class="field-label">Velocidad</span><Range label="Velocidad" min={50} max={200} step={5} value={step.speed} onChange={(v) => set({ speed: v })} format={(v) => `${v} %`} /></label>
            <label class="field"><span class="field-label">Rótulo grande</span><input class="input" maxLength={40} value={step.banner} placeholder="(opcional)" onInput={(e) => set({ banner: e.currentTarget.value })} /></label>
            <label class="field"><span class="field-label">Dura</span><NumberInput value={step.duration} min={0.1} max={30} step={0.1} unit="s" label="Duración" onInput={(v) => set({ duration: v })} /></label>
          </div>
          <div><button class="btn btn-sm" type="button" onClick={() => playBinding(step, {}, { force: true })} data-testid="cine-vfx-test"><Play size={14} /> Probar aquí</button></div>
        </div>
      )}
      {step.type === "post" && (
        <div class="col" style={{ gap: "6px" }}>
          <textarea class="textarea" maxLength={1500} value={step.text} placeholder="El mensaje que el bot escribe en el canal del evento…" onInput={(e) => set({ text: e.currentTarget.value })} data-testid="cine-post" aria-label="Mensaje al canal" />
          <span class="faint gm-hint">Sale en el canal a esa hora, sin mencionar a nadie. Los jugadores que no estén en la Actividad también lo leen.</span>
        </div>
      )}
    </>
  );
}

// What a step says, in a few words (the rows and the blocks of the timeline).
function brief(step, d) {
  const cut = (t, n = 28) => { const x = String(t || "").replace(/\s+/g, " ").trim(); return x.length > n ? `${x.slice(0, n - 1)}…` : x; };
  switch (step.type) {
    case "text": return step.speaker ? `${cut(step.speaker, 14)}: ${cut(step.text, 20)}` : cut(step.text);
    case "audio": return step.mode === "stop_music" ? "Para la música" : (d.sounds.find((s) => s.id === step.sound) || { name: "(sin sonido)" }).name;
    case "image": return step.image ? "Imagen" : "(sin imagen)";
    case "scene": return "Fondo";
    case "effect": return (EFFECTS.find((e) => e[0] === step.effect) || EFFECTS[0])[1];
    case "vfx": return (PRESETS[step.preset] || PRESETS.explosion).label;
    default: return cut(step.text);
  }
}

// ---- the timeline: one row per kind of step, a block per step; drag a block to move it, click it to edit it ------------------------------
function Timeline({ steps, total, selected, cursor, onSelect, onMove, onCursor, d }) {
  const drag = useRef(null);
  const lanes = LANES.filter(([id, , types]) => id !== "post" || steps.some((s) => types.includes(s.type)) || true);
  const percent = (t) => `${Math.max(0, Math.min(100, (t / total) * 100))}%`;
  const press = (e, step, width) => {
    if (e.button !== undefined && e.button !== 0) return;
    drag.current = { k: step._k, x: e.clientX, at: num(step.at), width, moved: false };
    onSelect(step._k);
    e.currentTarget.setPointerCapture && e.currentTarget.setPointerCapture(e.pointerId);
  };
  const move = (e) => {
    const g = drag.current;
    if (!g) return;
    const dx = e.clientX - g.x;
    if (!g.moved && Math.abs(dx) < 4) return;
    g.moved = true;
    onMove(g.k, draggedTo(g.at, dx, g.width, total));
  };
  const release = () => { drag.current = null; };
  return (
    <div class="cine-timeline" data-testid="cine-timeline">
      <div class="tl-ruler" aria-hidden="true">
        {rulerTicks(total).map((t) => <span key={t} style={{ left: percent(t) }}>{t}s</span>)}
      </div>
      {lanes.map(([id, label, types]) => (
        <div class="tl-lane" key={id} data-lane={id}>
          <span class="tl-label">{label}</span>
          <div class="tl-track" onClick={(e) => { if (e.target === e.currentTarget) { const r = e.currentTarget.getBoundingClientRect(); onCursor(Math.round(((e.clientX - r.left) / r.width) * total * 10) / 10); } }}>
            {steps.filter((s) => types.includes(s.type)).map((s) => {
              const Icon = ICON[s.type];
              return (
                <button key={s._k} type="button" class={cx("tl-block", `t-${s.type}`, selected === s._k && "on")} data-testid={`cine-block-${s._n}`}
                  style={{ left: percent(num(s.at)), width: s.duration ? `max(28px, ${Math.min(100, (num(s.duration) / total) * 100)}%)` : undefined }}
                  aria-label={`${STEP_LABELS[s.type]} en el segundo ${num(s.at)}: ${brief(s, d)}`} title={`${STEP_LABELS[s.type]} · ${num(s.at)} s · ${brief(s, d)}`}
                  onPointerDown={(e) => press(e, s, e.currentTarget.parentElement.getBoundingClientRect().width)} onPointerMove={move} onPointerUp={release}
                  onKeyDown={(e) => { if (e.key === "ArrowLeft") { e.preventDefault(); onMove(s._k, Math.max(0, Math.round((num(s.at) - 0.1) * 10) / 10)); } if (e.key === "ArrowRight") { e.preventDefault(); onMove(s._k, Math.round((num(s.at) + 0.1) * 10) / 10); } }}>
                  <Icon size={12} /><span>{brief(s, d)}</span>
                </button>
              );
            })}
            <i class="tl-cursor" style={{ left: percent(cursor) }} aria-hidden="true" />
          </div>
        </div>
      ))}
    </div>
  );
}

const SaveChip = ({ status, reason }) => {
  if (status === "saving" || status === "pending") return <span class="save-state" data-state={status} role="status" data-testid="cine-save-state"><Loader2 size={13} class="spin-icon" /> Guardando…</span>;
  if (status === "invalid") return <span class="save-state warn" data-state={status} role="status" data-testid="cine-save-state"><TriangleAlert size={13} /> Sin guardar: {reason}</span>;
  if (status === "error") return <span class="save-state bad" data-state={status} role="status" data-testid="cine-save-state"><TriangleAlert size={13} /> No se pudo guardar. Se reintenta al cambiar algo.</span>;
  return <span class="save-state ok" data-state="saved" role="status" data-testid="cine-save-state"><Check size={13} /> Todo guardado</span>;
};

let stepKey = 0;
const withKeys = (cinema) => ({ ...cinema, steps: cinema.steps.map((s) => ({ ...s, _k: ++stepKey })) });
const bare = (draft) => { const { id, ...rest } = draft; return { ...rest, steps: draft.steps.map(({ _k, _n, ...s }) => s) }; };

function Editor({ start, d, onClose, replace }) {
  const [draft, setDraft] = useState(() => withKeys(start));
  const [id, setId] = useState(start.id || "");
  const [selected, setSelected] = useState(null);
  const [cursor, setCursor] = useState(0);
  const [busy, run] = useDo();
  const ordered = useMemo(() => orderOf(draft.steps).map((s, n) => ({ ...s, _n: n + 1 })), [draft.steps]);
  const view = playable(draft, true);
  const total = Math.max(10, Math.ceil(view.duration));
  const set = (patch) => setDraft((old) => ({ ...old, ...patch }));
  const idRef = useRef(id);
  idRef.current = id;

  const auto = useAutosave(bare(draft), {
    key: start.id || "new",
    check: validate,
    save: async (value) => {
      const out = await act("gm.cinema_save", { cinema: { ...value, id: idRef.current, steps: orderOf(value.steps) } });
      if (!out) return false;
      if (!idRef.current && out.saved) setId(out.saved.id);
      replace(out);
      return true;
    },
  });

  const update = (k, patch) => setDraft((old) => ({ ...old, steps: old.steps.map((s) => (s._k === k ? { ...s, ...patch } : s)) }));
  const remove = (k) => { const at = ordered.findIndex((s) => s._k === k); setDraft((old) => ({ ...old, steps: old.steps.filter((s) => s._k !== k) })); setSelected(ordered[at + 1] ? ordered[at + 1]._k : ordered[at - 1] ? ordered[at - 1]._k : null); };
  const duplicate = (k) => { const src = draft.steps.find((s) => s._k === k); const copy = { ...src, _k: ++stepKey, at: Math.round((num(src.at) + 1) * 10) / 10 }; setDraft((old) => ({ ...old, steps: [...old.steps, copy] })); setSelected(copy._k); };
  const add = (type) => {
    const fresh = { ...newStep(type, []), at: cursor, _k: ++stepKey };
    if (type === "text" || type === "image") fresh.duration = fresh.duration || 4;
    setDraft((old) => ({ ...old, steps: [...old.steps, fresh] }));
    setSelected(fresh._k);
  };
  const toggleTrigger = (tid) => set({ triggers: draft.triggers.includes(tid) ? draft.triggers.filter((t) => t !== tid) : [...draft.triggers, tid] });
  const sel = ordered.find((s) => s._k === selected) || null;
  const at = sel ? ordered.indexOf(sel) : -1;
  const leave = async () => { await auto.flush(); onClose(null); };
  const playNow = async () => {
    await auto.flush();
    if (!idRef.current) { toast("Se guarda sola en cuanto esté completa; entonces podrás ponerla.", "info", 3500); return; }
    const out = await run("play", "gm.cinema_play", { id: idRef.current }, "Suena y se ve para todos.");
    if (out) replace(out);
  };

  return (
    <div class="dash-col" data-testid="cine-editor">
      <Card title={id ? "Editar cinemática" : "Nueva cinemática"} icon={Clapperboard} testid="cine-editor-card"
        actions={<><SaveChip status={auto.status} reason={auto.reason} /><button class="btn btn-sm btn-ghost" type="button" onClick={leave} data-testid="cine-back"><ArrowLeft size={14} /> Volver</button></>}>
        <div class="col" style={{ gap: "var(--sp-3)" }}>
          <div class="row wrap" style={{ gap: "8px" }}>
            <input class="input grow" maxLength={80} value={draft.name} onInput={(e) => set({ name: e.currentTarget.value })} placeholder="Nombre: p. ej. Llegada del Rey" aria-label="Nombre" data-testid="cine-name" />
            <button class="btn" type="button" onClick={() => previewCine(playable(draft))} data-testid="cine-preview"><Eye size={15} /> Ver aquí</button>
            <button class="btn btn-primary" type="button" onClick={playNow} disabled={busy !== null || !!auto.reason} data-testid="cine-play-now"><Play size={15} /> Poner para todos</button>
          </div>
          <details class="cine-settings" data-testid="cine-settings">
            <summary>Ajustes: {draft.bars ? "barras de cine" : "sin barras"} · {draft.skippable ? "se puede saltar" : "no se puede saltar"} · {draft.triggers.length ? `empieza sola con ${plural(draft.triggers.length, "suceso", "sucesos")}` : "solo la pones tú"}</summary>
            <div class="col" style={{ gap: "var(--sp-3)", marginTop: "var(--sp-3)" }}>
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
          </details>
        </div>
      </Card>

      <Card title="Línea de tiempo" icon={Type} testid="cine-steps"
        hint="Haz clic en un bloque para editarlo y arrástralo para moverlo en el tiempo. Haz clic en un hueco de cualquier fila para elegir en qué segundo se añade el siguiente paso.">
        <Timeline steps={ordered} total={total} selected={selected} cursor={cursor} d={d} onSelect={setSelected} onCursor={setCursor}
          onMove={(k, t) => update(k, { at: t })} />
        <div class="cine-add" data-testid="cine-add">
          <span class="faint">Añadir en el segundo</span>
          <NumberInput value={cursor} min={0} max={3600} step={0.5} unit="s" label="Segundo donde se añade" testid="cine-cursor" width="110px" onInput={(v) => setCursor(Math.max(0, num(v)))} />
          {Object.keys(STEP_LABELS).map((type) => { const Icon = ICON[type]; return <button key={type} class="btn btn-sm" type="button" onClick={() => add(type)} data-testid={`cine-add-${type}`}><Icon size={14} /> {STEP_LABELS[type]}</button>; })}
        </div>
      </Card>

      <Card title={sel ? `${STEP_LABELS[sel.type]} · paso ${sel._n} de ${ordered.length}` : "Paso"} icon={sel ? ICON[sel.type] : Pencil} testid="cine-step-card"
        actions={sel && (
          <>
            <button class="btn btn-sm btn-ghost" type="button" onClick={() => setSelected(ordered[at - 1]._k)} disabled={at <= 0} aria-label="Paso anterior"><ChevronLeft size={14} /></button>
            <button class="btn btn-sm btn-ghost" type="button" onClick={() => setSelected(ordered[at + 1]._k)} disabled={at >= ordered.length - 1} aria-label="Paso siguiente"><ChevronRight size={14} /></button>
            <button class="btn btn-sm btn-ghost" type="button" onClick={() => duplicate(sel._k)} aria-label="Duplicar paso" title="Duplicar" data-testid="cine-duplicate"><Copy size={14} /></button>
            <button class="btn btn-sm btn-ghost" type="button" onClick={() => remove(sel._k)} aria-label="Quitar paso" title="Quitar" data-testid="cine-remove"><Trash2 size={14} /></button>
          </>
        )}>
        {sel ? (
          <div class={cx("cine-step", `t-${sel.type}`)} data-testid="cine-step">
            <label class="cine-at">En el segundo <NumberInput value={sel.at} min={0} max={3600} step={0.1} unit="s" label="Momento del paso" testid="cine-at" width="120px" onInput={(v) => update(sel._k, { at: v })} /></label>
            <StepForm step={sel} d={d} set={(patch) => update(sel._k, patch)} />
          </div>
        ) : <p class="faint">Elige un paso en la línea de tiempo o en la lista de abajo, o añade uno nuevo.</p>}
      </Card>

      <Card title={`Pasos (${ordered.length})`} icon={Type} testid="cine-rows">
        {ordered.length === 0 && <p class="faint">Todavía no hay pasos: añade el primero.</p>}
        {ordered.map((s) => { const Icon = ICON[s.type]; return (
          <button key={s._k} type="button" class={cx("cine-row", `t-${s.type}`, selected === s._k && "on")} onClick={() => { setSelected(s._k); setCursor(num(s.at)); }} data-testid={`cine-row-${s._n}`}>
            <span class="num faint">{s._n}</span><span class="cine-row-at num">{num(s.at)} s</span><Icon size={14} /><strong>{STEP_LABELS[s.type]}</strong><span class="ellipsis faint">{brief(s, d)}</span>
          </button>); })}
      </Card>
    </div>
  );
}

const BLANK = () => ({ id: "", name: "Nueva cinemática", steps: [newStep("scene", []), { ...newStep("text", [{ at: 0, duration: 1 }]), text: "Escribe aquí lo que se dice…" }], triggers: [], bg: "#000000", bars: true, skippable: true });

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
