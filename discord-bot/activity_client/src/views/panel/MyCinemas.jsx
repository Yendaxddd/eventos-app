// Mi panel · Cinemáticas: a player writes a short cinematic for one of their powers or actions and sends it to the game masters.
// Once approved, it plays for everybody each time that player does that (cinema_requests.py). Nobody else sees it before.
import { useEffect, useState } from "preact/hooks";
import { CheckCircle2, Clapperboard, Clock3, Eye, Pencil, Plus, Send, Trash2, Undo2 } from "lucide-preact";
import { usePanel, act } from "../../panel/data.js";
import { creqRev } from "../../state.js";
import { previewCine } from "../../cine.js";
import { newStep } from "../../cinema-model.js";
import { Block, ConfirmButton, Empty, Pill } from "../../ui/Common.jsx";
import { Card } from "../gm/ui.jsx";
import { Editor, playable } from "../gm/CinemaTab.jsx";

export const STATUS = {
  draft: ["Borrador", null, Pencil], pending: ["Esperando al GM", "warn", Clock3], approved: ["Aprobada", "ok", CheckCircle2], rejected: ["Devuelta", "bad", Undo2],
};
const COOLDOWNS = [[60, "1 min"], [300, "5 min"], [900, "15 min"], [3600, "1 h"]];

const blank = (s) => ({
  id: "", name: "Mi técnica", kind: "request", bars: true, skippable: true, see: true, bg: "#000000", triggers: [], boss: "", share: "private", hint: "",
  note: "", bind: { event: "power_used", character: s.characters[0]?.name || "", slot: "1", cooldown: 300 },
  steps: [{ ...newStep("title", []), text: "¡Técnica secreta!", duration: 2.5 }, { ...newStep("text", [{ at: 0, duration: 2.5 }]), text: "Escribe lo que dice tu personaje…", speaker: s.characters[0]?.name || "" }],
});

// What the cinematic is for: which action, as which character, which power, how often, and a word for the game masters.
function BindPanel({ draft, set, s }) {
  const bind = draft.bind || {};
  const change = (patch) => set({ bind: { ...bind, ...patch } });
  const char = s.characters.find((c) => c.name === bind.character);
  return (
    <div class="creq-bind" data-testid="creq-bind">
      <span class="field-label">Cuándo se pone</span>
      <div class="row wrap gm-chips" role="group" aria-label="Cuándo se pone">
        {s.events.map((e) => <button key={e.id} type="button" class="choice" aria-pressed={bind.event === e.id ? "true" : "false"} onClick={() => change({ event: e.id })}>{e.label}</button>)}
      </div>
      <div class="row wrap" style={{ gap: "8px" }}>
        <label class="field grow"><span class="field-label">Personaje</span>
          <select class="select" value={bind.character || ""} onChange={(e) => change({ character: e.currentTarget.value })} data-testid="creq-character">
            {(bind.event !== "power_used" || !s.characters.length) && <option value="">Cualquiera de los míos</option>}
            {s.characters.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </label>
        {bind.event === "power_used" && (
          <label class="field grow"><span class="field-label">Poder</span>
            <select class="select" value={bind.slot || ""} onChange={(e) => change({ slot: e.currentTarget.value })} data-testid="creq-slot">
              <option value="">Cualquiera</option>
              {(char?.powers.length ? char.powers : [{ slot: "1", name: "Poder 1" }, { slot: "2", name: "Poder 2" }]).map((p) => <option key={p.slot} value={p.slot}>{p.name}</option>)}
            </select>
          </label>
        )}
        <label class="field"><span class="field-label">Como mucho, una vez cada</span>
          <select class="select" value={String(bind.cooldown ?? 300)} onChange={(e) => change({ cooldown: Number(e.currentTarget.value) })}>
            {COOLDOWNS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
      </div>
      <label class="field"><span class="field-label">Mensaje para el equipo de GM (opcional)</span>
        <input class="input" maxLength={300} value={draft.note || ""} placeholder="Es la técnica final de Kuro; ¿podría sonar con el tema del jefe?" onInput={(e) => set({ note: e.currentTarget.value })} />
      </label>
      <p class="faint gm-hint">Hasta {s.maxSeconds} s. Se guarda sola mientras escribes; cuando esté lista, vuelve y pulsa «Enviar al GM». Nadie más la verá antes de que salga.</p>
    </div>
  );
}

function Body({ s, replace }) {
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(null);
  const run = async (name, op, args, done) => { setBusy(name); const out = await act(op, args, done); setBusy(null); if (out) replace(out); return out; };
  if (editing) {
    return (
      <Editor key={editing.id || "new"} player start={editing} d={s.d} steps={s.steps} replace={replace} onClose={() => setEditing(null)}
        save={(cinema) => act("creq.save", { cinema: { ...cinema, kind: "request" } })}
        extra={(draft, set) => <BindPanel draft={draft} set={set} s={s} />} />
    );
  }
  return (
    <div class="dash-col" data-testid="creq-list">
      <Card title="Mis cinemáticas" icon={Clapperboard}
        hint="Escribe una escena corta para un poder o una acción tuya (un Black Flash, tu dominio, un contraataque…). Cuando el equipo de GM la apruebe, saldrá para todos cada vez que la hagas."
        actions={s.mine.length < s.limit && <button class="btn btn-sm btn-primary" type="button" onClick={() => setEditing(blank(s))} data-testid="creq-new"><Plus size={14} /> Nueva</button>}>
        {s.mine.length === 0 && <Empty icon={Clapperboard} title="Todavía no tienes ninguna">Crea una para tu técnica favorita.</Empty>}
        {s.mine.map((c) => {
          const [label, tone, Icon] = STATUS[c.status] || STATUS.draft;
          return (
            <div key={c.id} class="cine-item creq-item" data-testid={`creq-${c.id}`}>
              <div class="info">
                <strong class="ellipsis">{c.name}</strong>
                <span class="faint">{c.bindLabel} · {Math.round(c.duration - 1)} s</span>
                <div class="row wrap" style={{ gap: "4px" }}><Pill tone={tone} icon={Icon}>{label}</Pill></div>
                {c.review && <span class="creq-review">GM: {c.review}</span>}
              </div>
              <button class="btn btn-sm btn-ghost" type="button" onClick={() => previewCine(playable(c))} aria-label="Ver"><Eye size={14} /></button>
              <button class="btn btn-sm" type="button" onClick={() => setEditing({ ...c, note: c.note || "", hint: "", steps: c.steps.map((st) => ({ ...st, color: st.color || "", avatar: st.avatar || "", image: st.image || "", ...(st.type === "title" ? { subtitle: st.subtitle || "" } : {}) })) })} data-testid={`creq-edit-${c.id}`}><Pencil size={14} /> Editar</button>
              {(c.status === "draft" || c.status === "rejected") && <button class="btn btn-sm btn-primary" type="button" disabled={busy !== null} onClick={() => run("send", "creq.send", { id: c.id }, "Enviada: el equipo de GM la revisará.")} data-testid={`creq-send-${c.id}`}><Send size={14} /> Enviar al GM</button>}
              <ConfirmButton icon={Trash2} class="btn-ghost" confirm="Sí, borrar" label={`Borrar «${c.name}»`} onConfirm={() => run("del", "creq.delete", { id: c.id }, "Borrada.")} />
            </div>
          );
        })}
        {s.characters.length === 0 && <p class="faint gm-hint">Registra un personaje en «Personajes» para ligar la cinemática a sus poderes.</p>}
      </Card>
    </div>
  );
}

export function MyCinemasTab() {
  const q = usePanel("creq.state");
  const rev = creqRev.value;
  useEffect(() => { if (rev) q.refresh(); }, [rev]);
  return <Block q={q}>{(s) => <Body s={s} replace={q.replace} />}</Block>;
}
