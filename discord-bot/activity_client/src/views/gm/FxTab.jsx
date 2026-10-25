import { useState } from "preact/hooks";
import { Check, Loader2, Pencil, Play, Sparkles, Trash2, TriangleAlert, X } from "lucide-preact";
import { Block, Empty } from "../../ui/Common.jsx";
import { Range, Switch } from "../../ui/Controls.jsx";
import { act } from "../../panel/data.js";
import { playBinding } from "../../vfx.js";
import { DEFAULT_BINDING, DEFAULT_BY_TYPE, PRESETS, PRESET_IDS, isEmpty, sanitizeBinding } from "../../fx-model.js";
import { cx } from "../../util.js";
import { Card } from "./ui.jsx";
import { useAutosave, useLive } from "./hooks.js";

const POWER_TYPE = { destructive: "Destructivo", support: "Apoyo", defend: "Defensa", build: "Construcción", control: "Control" };
const GROUPS = [
  ["Poderes", ["power_used", "power_1", "power_2"]],
  ["Tus respuestas", ["evade_ok", "parry_ok", "counter", "rescue_ok", "combo_step", "qte_fail"]],
  ["Black Flash y combos", ["black_flash", "chain_max", "combo_done", "fake_fail", "group_done"]],
  ["Golpes y vida", ["player_hit", "low_hp", "heal", "boss_hit", "player_down", "checkpoint"]],
  ["Dominios", ["domain_cast", "domain", "boss_domain"]],
  ["Combate", ["boss_spawn", "boss_defeated", "fight_start", "fight_end"]],
  ["Enemigos", ["mob_spawn", "mob_attack", "mob_hit", "mob_down", "mobs_cleared"]],
];

// What a binding does, in a few words.
export function summary(binding, sounds = []) {
  if (!binding) return null;
  const parts = [PRESETS[binding.preset].label];
  if (binding.banner) parts.push(`rótulo «${binding.banner}»`); else if (binding.name) parts.push("muestra el nombre");
  if (binding.sound) parts.push(`sonido «${(sounds.find((s) => s.id === binding.sound) || { name: "¿?" }).name}»`);
  if (binding.delay) parts.push(`tras ${(binding.delay / 1000).toFixed(1)} s`);
  return parts.join(" · ");
}

function SaveState({ status, reason }) {
  if (status === "saving" || status === "pending") return <span class="save-state" data-state={status} role="status"><Loader2 size={13} class="spin-icon" /> Guardando…</span>;
  if (status === "invalid") return <span class="save-state warn" data-state={status} role="status"><TriangleAlert size={13} /> {reason}</span>;
  if (status === "error") return <span class="save-state bad" data-state={status} role="status"><TriangleAlert size={13} /> No se pudo guardar. Se reintenta al cambiar algo.</span>;
  return <span class="save-state ok" data-state="saved" role="status"><Check size={13} /> Guardado</span>;
}

// One binding being edited: everything saves by itself.
export function Editor({ initial, sounds, name, scopeChoice, scopeLabels, save, id }) {
  const [b, setB] = useState(() => sanitizeBinding(initial || { ...DEFAULT_BINDING, preset: "impacto" }));
  const set = (patch) => setB((old) => sanitizeBinding({ ...old, ...patch }));
  const state = useAutosave(b, { key: id, save: (v) => save(v), check: (v) => (isEmpty(v) ? "Elige un efecto visual, un rótulo o un sonido." : "") });
  const preset = PRESETS[b.preset];
  const test = () => playBinding({ ...b }, { name }, { force: true });
  return (
    <div class="fx-editor" data-testid={`fx-editor-${id}`}>
      <div class="fx-presets" role="group" aria-label="Efecto visual">
        {PRESET_IDS.map((p) => (
          <button key={p} type="button" class="fx-preset" aria-pressed={b.preset === p ? "true" : "false"} data-testid={`fx-preset-${id}-${p}`} onClick={() => set({ preset: p })}>
            <i style={{ background: PRESETS[p].color }} />{PRESETS[p].label}
          </button>
        ))}
      </div>
      <p class="faint fx-hint">{preset.hint}</p>
      {b.preset !== "ninguno" && (
        <div class="fx-grid">
          <label class="field"><span class="field-label">Color</span>
            <span class="row" style={{ gap: "8px" }}>
              <input type="color" value={b.color || preset.color} onInput={(e) => set({ color: e.currentTarget.value })} aria-label="Color del efecto" />
              {b.color && <button class="btn btn-sm btn-ghost" type="button" onClick={() => set({ color: "" })}>Color del efecto</button>}
            </span>
          </label>
          <label class="field"><span class="field-label">Fuerza</span><Range label="Fuerza" min={25} max={200} step={5} value={b.intensity} onChange={(v) => set({ intensity: v })} format={(v) => `${v} %`} /></label>
          <label class="field"><span class="field-label">Velocidad</span><Range label="Velocidad" min={50} max={200} step={5} value={b.speed} onChange={(v) => set({ speed: v })} format={(v) => `${v} %`} /></label>
        </div>
      )}
      <div class="fx-grid">
        <label class="field"><span class="field-label">Retraso</span><Range label="Retraso" min={0} max={5000} step={100} value={b.delay} onChange={(v) => set({ delay: v })} format={(v) => `${(v / 1000).toFixed(1)} s`} /></label>
        <label class="field"><span class="field-label">Rótulo grande</span>
          <input class="input" maxLength={40} placeholder="Texto que aparece en grande (opcional)" value={b.banner} onInput={(e) => set({ banner: e.currentTarget.value })} data-testid={`fx-banner-${id}`} />
        </label>
        <label class="field gm-check"><input type="checkbox" checked={b.name} onChange={(e) => set({ name: e.currentTarget.checked })} /> Mostrar el nombre como rótulo</label>
        {sounds && <label class="field"><span class="field-label">Sonido</span>
          <select class="select" value={b.sound} onChange={(e) => set({ sound: e.currentTarget.value })} aria-label="Sonido del efecto" data-testid={`fx-sound-${id}`}>
            <option value="">— sin sonido —</option>
            {sounds.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>}
        {scopeChoice && (
          <label class="field"><span class="field-label">Quién lo ve</span>
            <select class="select" value={b.scope} onChange={(e) => set({ scope: e.currentTarget.value })} aria-label="Quién ve el efecto">
              <option value="all">{(scopeLabels || {}).all || "Todos"}</option><option value="target">{(scopeLabels || {}).target || "Solo quien lo vive"}</option>
            </select>
          </label>
        )}
      </div>
      <div class="row wrap" style={{ gap: "8px", justifyContent: "space-between" }}>
        <button class="btn" type="button" onClick={test} data-testid={`fx-test-${id}`}><Play size={15} /> Probar aquí</button>
        <SaveState status={state.status} reason={state.reason} />
      </div>
    </div>
  );
}

export function Row({ id, title, sub, binding, sounds, name, scopeChoice, scopeLabels, save, clear, fallback, start }) {
  const [open, setOpen] = useState(false);
  const shown = binding || fallback;
  return (
    <div class={cx("gm-fx-row", open && "open")} data-testid={`fx-row-${id}`}>
      <div class="gm-fx-head">
        <div class="info"><strong>{title}</strong>{sub && <span class="faint">{sub}</span>}</div>
        <span class={cx("gm-fx-sum", !binding && "faint")} data-testid={`fx-sum-${id}`}>
          {shown && <i class="fx-dot" style={{ background: (shown.color || PRESETS[shown.preset].color) }} />}
          {binding ? summary(binding, sounds) : fallback ? `Por defecto: ${PRESETS[fallback.preset].label}` : "Sin efecto"}
        </span>
        {shown && <button class="btn btn-sm btn-ghost" type="button" onClick={() => playBinding(shown, { name }, { force: true })} aria-label={`Probar el efecto de ${title}`}><Play size={14} /></button>}
        <button class="btn btn-sm" type="button" onClick={() => setOpen(!open)} data-testid={`fx-edit-${id}`} aria-expanded={open ? "true" : "false"}>{open ? <><X size={14} /> Cerrar</> : <><Pencil size={14} /> {binding ? "Editar" : "Poner efecto"}</>}</button>
        {binding && <button class="btn btn-sm btn-ghost" type="button" onClick={clear} aria-label={`Quitar el efecto de ${title}`} data-testid={`fx-clear-${id}`}><Trash2 size={14} /></button>}
      </div>
      {open && <Editor id={id} initial={binding || fallback || start} sounds={sounds} name={name} scopeChoice={scopeChoice} scopeLabels={scopeLabels} save={save} />}
    </div>
  );
}

export function FxTab() {
  const q = useLive("gm.fx", {}, 5000);
  return (
    <Block q={q}>
      {(d) => <FxBody d={d} replace={q.replace} />}
    </Block>
  );
}

function FxBody({ d, replace }) {
  const byId = Object.fromEntries(d.events.map((e) => [e.id, e]));
  const saveFor = (what, args) => async (binding) => {
    const out = await act("gm.fx_set", { for: what, ...args, binding });
    if (out) { replace(out); return true; }
    return false;
  };
  const clearFor = (what, args) => async () => { const out = await act("gm.fx_clear", { for: what, ...args }, "Efecto quitado."); if (out) replace(out); };
  const setDefaults = async (on) => { const out = await act("gm.fx_defaults", { on }); if (out) replace(out); };
  return (
    <div class="dash-col" data-testid="gm-fx">
      <Card title="Efectos de los poderes" icon={Sparkles} testid="gm-fx-powers"
        hint="Cuando alguien usa un poder, todas las pantallas lo ven con el efecto que elijas aquí: color, fuerza, velocidad, retraso, rótulo y sonido. Los cambios se guardan solos."
        actions={<label class="row" style={{ gap: "8px" }}><span class="faint">Por defecto según su tipo</span><Switch label="Efectos por defecto de los poderes" checked={d.defaults} onChange={setDefaults} /></label>}>
        {d.powers.length === 0
          ? <Empty icon={Sparkles} title="Todavía no hay poderes registrados">Los jugadores los crean en «Mi panel → Personajes». Mientras tanto puedes dar un efecto a «Alguien usa un poder» más abajo.</Empty>
          : d.powers.map((p) => {
            const id = `power-${p.character}-${p.slot}`.replace(/[^\w-]+/g, "_");
            const fallback = d.defaults ? { ...DEFAULT_BINDING, preset: DEFAULT_BY_TYPE[p.type] || "impacto", name: true } : null;
            return <Row key={id} id={id} title={`${p.name}`} sub={`${p.character} · Poder ${p.slot}${POWER_TYPE[p.type] ? ` · ${POWER_TYPE[p.type]}` : ""}`} binding={p.binding} fallback={fallback}
              sounds={d.sounds} name={p.name} save={saveFor("power", { character: p.character, slot: p.slot })} clear={clearFor("power", { character: p.character, slot: p.slot })} />;
          })}
      </Card>
      <Card title="Efectos de lo que pasa" icon={Sparkles} testid="gm-fx-events" hint="Un efecto para cada cosa que ocurre en el juego: un golpe, un Black Flash, el jefe que cae… Un poder sin efecto propio usa el de su ranura («Poder 1» o «Poder 2») y, si no, el de «Alguien usa un poder».">
        {GROUPS.map(([title, ids]) => (
          <div key={title} class="gm-cue-group">
            <h3 class="gm-sub">{title}</h3>
            {ids.filter((id) => byId[id]).map((id) => (
              <Row key={id} id={`event-${id}`} title={byId[id].label} binding={byId[id].binding} sounds={d.sounds} name={byId[id].label}
                scopeChoice={byId[id].scope === "target"} save={saveFor("event", { event: id })} clear={clearFor("event", { event: id })} />
            ))}
          </div>
        ))}
      </Card>
    </div>
  );
}
