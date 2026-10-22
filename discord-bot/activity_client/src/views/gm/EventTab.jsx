import { useState } from "preact/hooks";
import { Flag, Heart, Layers, Play, Plus, RefreshCw, Send, Skull, Square, Swords, Undo2, Users, X, Zap } from "lucide-preact";
import { Block, ConfirmButton, Empty, Pill, Stat } from "../../ui/Common.jsx";
import { usePanel } from "../../panel/data.js";
import { parseNumber, plural } from "../../panel/format.js";
import { Card, Chips, DIFFICULTIES, DIFFICULTY_ES, NumberInput, Bar } from "./ui.jsx";
import { useDo, useDraft, useLive } from "./hooks.js";

const MODES = [
  ["single", "Individual", "Un QTE para una persona."], ["group", "Grupal", "Un QTE para todo el grupo."], ["combo", "Combo", "Cinco QTE seguidos para una persona."],
  ["direction", "Dirección", "Hay que responder con la flecha contraria."], ["fake", "Falso", "Sin aviso: cualquier respuesta falla al instante."],
  ["flick", "Deslizar", "Solo en la Actividad: deslizar hacia la flecha."], ["drag", "Arrastrar", "Solo en la Actividad: llevar la ficha a la diana."],
  ["mash", "Machacar", "Solo en la Actividad: tocar muchas veces seguidas."],
];
const MODE_TEXT = { single: "individual", group: "grupal", combo: "de combo", direction: "de dirección", fake: "falso", flick: "de deslizar", drag: "de arrastrar", mash: "de machacar" };
const QTE_MODES = [["standard", "Normal", "Solo QTE normales."], ["combo", "Combo", "Solo combos."], ["direction", "Dirección", "Solo de dirección."], ["random", "Al azar", "Según las probabilidades de abajo."]];
const VARIANT = { standard: "Normal", combo: "Combo", direction: "Dirección", fake: "Falso" };

function Status({ s }) {
  const boss = s.boss;
  return (
    <div class="col" style={{ gap: "var(--sp-3)" }} data-testid="gm-status">
      <div class="stat-grid">
        <Stat label="Combate" icon={Swords} tone={s.fight ? "ok" : undefined} value={s.fight ? "En curso" : "En pausa"} sub={s.fight ? "Los poderes se recargan." : "Las recargas están pausadas."} testid="gm-stat-fight" />
        <Stat label="QTE activos" icon={Zap} value={s.qtes.length} sub={s.qtes.length ? "Hay QTE esperando respuesta." : "Ninguno ahora mismo."} testid="gm-stat-qtes" />
        <Stat label="Jugadores" icon={Users} value={s.players.eligible} sub={s.players.afk ? `${plural(s.players.afk, "fuera de los QTE", "fuera de los QTE")}` : "Todos participan."} testid="gm-stat-players" />
        <Stat label="Sesión" icon={Flag} value={s.session.qtes} sub={`${plural(s.session.blackFlashes, "Black Flash", "Black Flash")} hoy`} testid="gm-stat-session" />
      </div>
      <div class="gm-boss-line" data-testid="gm-boss-line">
        <Skull size={18} />
        {boss ? (
          <>
            <strong class="display">{boss.name}</strong>
            <div class="grow"><Bar value={boss.hp} max={boss.max} kind="boss" label={`Vida de ${boss.name}`} /></div>
            {boss.tupper && <Pill tone="info">Tupperbox</Pill>}
          </>
        ) : <span class="faint">No hay un jefe en combate.</span>}
      </div>
      {s.stunLeft > 0 && <p class="gm-warn" role="status" data-testid="gm-stunned">El jefe está aturdido ({Math.ceil(s.stunLeft)} s): mientras tanto no se pueden lanzar QTE.</p>}
    </div>
  );
}

function Launch({ s, replace }) {
  const players = usePanel("gm.players");
  const [mode, setMode] = useState("single");
  const [difficulty, setDifficulty] = useState("medium");
  const [target, setTarget] = useState("");
  const [busy, run] = useDo();
  const list = (players.data && players.data.players) || [];
  const person = list.find((p) => p.id === target);
  const stunned = s.stunLeft > 0;
  const who = mode === "group" ? "a todo el grupo" : person ? `a ${person.name}` : "a alguien al azar";
  const launch = async () => {
    const out = await run("launch", "gm.launch", { mode, difficulty, target: mode === "group" ? null : target || null }, "QTE lanzado.");
    if (out) replace(out);
  };
  return (
    <Card title="Lanzar un QTE" icon={Zap} hint="Es lo mismo que las teclas F9–F12 y /targetqte del bot." testid="gm-launch">
      <div class="col" style={{ gap: "var(--sp-3)" }}>
        <Chips label="Tipo de QTE" value={mode} options={MODES} onChange={setMode} testid="gm-mode" />
        <Chips label="Dificultad" value={difficulty} options={DIFFICULTIES} onChange={setDifficulty} testid="gm-difficulty" />
        <div class="gm-grid">
          <label class="field">
            <span class="field-label">A quién</span>
            <select class="select" value={mode === "group" ? "" : target} disabled={mode === "group"} onChange={(e) => setTarget(e.currentTarget.value)} data-testid="gm-target">
              <option value="">{mode === "group" ? "Todo el grupo" : "Alguien al azar"}</option>
              {list.map((p) => <option key={p.id} value={p.id}>{p.name}{p.online ? " · en la Actividad" : ""}</option>)}
            </select>
          </label>
          <div class="gm-launch-go">
            <button class="btn btn-primary btn-lg" type="button" onClick={launch} disabled={busy !== null || stunned} data-testid="gm-launch-go">
              <Play size={18} />{busy === "launch" ? "Lanzando…" : "Lanzar QTE"}
            </button>
          </div>
        </div>
        <p class="faint gm-hint" data-testid="gm-launch-summary">Lanzará un QTE {MODE_TEXT[mode]} de dificultad {DIFFICULTY_ES[difficulty].toLowerCase()} {who}.</p>
      </div>
    </Card>
  );
}

function Batch({ s, replace }) {
  const [busy, run] = useDo();
  const batch = s.batch;
  const step = async (action, difficulty, done) => {
    const out = await run(action, "gm.batch", { action, difficulty }, done);
    if (out) replace({ ...s, batch: out });
  };
  return (
    <Card title="Tanda de QTE" icon={Layers} hint="Prepara varios QTE y envíalos juntos, uno detrás de otro." testid="gm-batch"
      actions={batch.active ? <Pill tone="primary">{plural(batch.pending.length, "QTE en la tanda", "QTE en la tanda")}</Pill> : null}>
      {!batch.active ? (
        <button class="btn" type="button" onClick={() => step("start", null, "Tanda empezada.")} disabled={busy !== null} data-testid="gm-batch-start"><Plus size={16} /> Empezar una tanda</button>
      ) : (
        <div class="col" style={{ gap: "var(--sp-3)" }}>
          <div class="row wrap" style={{ gap: "6px" }} aria-label="Añadir a la tanda">
            {DIFFICULTIES.map(([id, text]) => (
              <button key={id} type="button" class="btn btn-sm" disabled={busy !== null} data-testid={`gm-batch-add-${id}`} onClick={() => step("add", id)}><Plus size={14} />{text}</button>
            ))}
          </div>
          <div class="row wrap gm-queue" data-testid="gm-batch-queue">
            {batch.pending.length === 0 ? <span class="faint">Añade QTE con los botones de arriba.</span>
              : batch.pending.map((d, i) => <Pill key={i} tone="primary">{i + 1}. {DIFFICULTY_ES[d] || d}</Pill>)}
          </div>
          <div class="row wrap" style={{ gap: "8px" }}>
            <button class="btn btn-primary" type="button" disabled={busy !== null || batch.pending.length === 0} onClick={() => step("send", null, "Tanda enviada.")} data-testid="gm-batch-send"><Send size={16} /> Enviar la tanda</button>
            <button class="btn" type="button" disabled={busy !== null || batch.pending.length === 0} onClick={() => step("undo")} data-testid="gm-batch-undo"><Undo2 size={16} /> Quitar el último</button>
            <button class="btn btn-ghost" type="button" disabled={busy !== null} onClick={() => step("cancel", null, "Tanda cancelada.")} data-testid="gm-batch-cancel"><X size={16} /> Cancelar</button>
          </div>
        </div>
      )}
    </Card>
  );
}

function Fight({ s, replace, reload }) {
  const [busy, run] = useDo();
  const fight = async (action, done) => {
    const out = await run("fight", "gm.fight", { action }, done);
    if (out) replace(out);
  };
  const checkpoint = async () => {
    if (await run("checkpoint", "gm.checkpoint", {}, `Checkpoint lanzado: +${s.regen} HP a todos.`)) reload();
  };
  const sync = () => run("sync", "gm.sync", {}, "Comandos de barra sincronizados.");
  return (
    <Card title="Combate" icon={Swords} hint="Las recargas de los poderes solo avanzan mientras hay combate." testid="gm-fight">
      <div class="row wrap" style={{ gap: "8px" }}>
        {s.fight
          ? <ConfirmButton icon={Square} confirm="Sí, terminar" onConfirm={() => fight("end", "Combate terminado.")} disabled={busy !== null} testid="gm-fight-end">Terminar el combate</ConfirmButton>
          : <button class="btn btn-primary" type="button" onClick={() => fight("start", "Combate empezado.")} disabled={busy !== null} data-testid="gm-fight-start"><Play size={16} /> Empezar el combate</button>}
        <button class="btn" type="button" onClick={checkpoint} disabled={busy !== null} data-testid="gm-checkpoint"><Heart size={16} /> Checkpoint (+{s.regen} HP a todos)</button>
        <button class="btn btn-ghost" type="button" onClick={sync} disabled={busy !== null} data-testid="gm-sync"><RefreshCw size={16} /> Sincronizar comandos</button>
      </div>
      <p class="faint gm-hint" style={{ marginTop: "var(--sp-2)" }}>{s.checkpoints ? `${plural(s.checkpoints, "checkpoint lanzado", "checkpoints lanzados")} en esta sesión.` : "Aún no se ha lanzado ningún checkpoint."}</p>
    </Card>
  );
}

function AutoMode({ s, replace }) {
  const [busy, run] = useDo();
  const form = useDraft({ mode: s.qteMode, weights: s.weights });
  const { draft, edit } = form;
  const keys = Object.keys(s.weights);
  const total = keys.reduce((sum, k) => sum + (draft.weights[k] || 0), 0);
  const setWeight = (key, text) => edit((old) => ({ weights: { ...old.weights, [key]: Math.max(0, Math.min(100, Math.round(parseNumber(text) ?? 0))) } }));
  const save = async () => {
    const sent = draft;
    const out = await run("mode", "gm.qte_mode", { mode: sent.mode, weights: sent.weights }, "Modo de QTE guardado.");
    if (out) { form.saved(sent); replace(out); }
  };
  return (
    <Card title="QTE automáticos" icon={Zap} hint="Cuál sale solo durante el evento, y con qué probabilidad si eliges «Al azar»." testid="gm-automode">
      <div class="col" style={{ gap: "var(--sp-3)" }}>
        <Chips label="Modo de los QTE automáticos" value={draft.mode} options={QTE_MODES} onChange={(mode) => edit({ mode })} testid="gm-qtemode" />
        <div class="gm-weights" data-disabled={draft.mode === "random" ? "0" : "1"}>
          {keys.map((k) => (
            <label key={k} class="field">
              <span class="field-label">{VARIANT[k] || k}</span>
              <NumberInput value={draft.weights[k]} min={0} max={100} step={5} unit="%" label={`Probabilidad de ${VARIANT[k] || k}`} testid={`gm-weight-${k}`} onInput={(t) => setWeight(k, t)} />
            </label>
          ))}
        </div>
        <p class="faint gm-hint">{draft.mode === "random" ? (total === 0 ? "Alguna probabilidad debe ser mayor que 0." : "Se reparten según el peso de cada uno (no hace falta que sumen 100).") : "Las probabilidades solo cuentan en el modo «Al azar»."}</p>
        <div><button class="btn btn-primary" type="button" onClick={save} disabled={busy !== null || (draft.mode === "random" && total === 0)} data-testid="gm-qtemode-save">Guardar</button></div>
      </div>
    </Card>
  );
}

function Running({ s }) {
  if (!s.qtes.length) return null;
  return (
    <Card title="QTE en curso" icon={Zap} testid="gm-running">
      <ul class="gm-list">
        {s.qtes.map((q) => (
          <li key={q.id} class="gm-item">
            <b class="num">#{q.id}</b>
            <span class="grow">QTE {MODE_TEXT[q.mode] || q.mode}{q.target ? ` · ${q.target}` : " · todo el grupo"}</span>
            <Pill>{DIFFICULTY_ES[q.difficulty] || q.difficulty}</Pill>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function EventTab() {
  const q = useLive("gm.state", null, 2500);
  return (
    <div class="dash-col" data-testid="gm-event">
      <Block q={q}>
        {(s) => (
          <>
            <Status s={s} />
            <Launch s={s} replace={q.replace} />
            <Running s={s} />
            <Batch s={s} replace={q.replace} />
            <Fight s={s} replace={q.replace} reload={q.refresh} />
            <AutoMode s={s} replace={q.replace} />
          </>
        )}
      </Block>
    </div>
  );
}
