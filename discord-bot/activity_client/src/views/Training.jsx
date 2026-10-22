import { useEffect, useState } from "preact/hooks";
import { Dumbbell, Pause, Play, RotateCcw, Square, Trophy } from "lucide-preact";
import { useNow } from "../hooks.js";
import { cx } from "../util.js";
import { DIFFICULTY, MODE } from "../terms.js";
import { Page, Range, Section, Segmented, Setting, Switch } from "../ui/Controls.jsx";
import { COUNTS, DIFFICULTIES, KINDS, PRESETS, accuracy, averageMs, sanitizeConfig } from "../training-model.js";
import { backToConfig, loadBest, pauseTraining, startTraining, stopTraining, training } from "../training.js";

const KIND_HINT = {
  single: "Esquivar y, si se abre, parry.", group: "Solo esquivar.", direction: "Pulsa la flecha opuesta.",
  combo: "Una secuencia de esquives y parries.", bf_chain: "Parry dentro de la ventana; antes, rompe la cadena.",
  flick: "Desliza hacia donde apunta la flecha (o pulsa esa flecha).", drag: "Lleva la ficha a la diana (o muévela con las flechas y pulsa Enter).",
  mash: "Toca el botón (o la barra espaciadora) las veces que pide.", fake: "Parece un esquive de verdad: no lo pulses.",
};
const COUNT_LABEL = { 10: "10", 25: "25", 50: "50", 100: "100", 0: "Sin fin" };
const REASON = {
  finished: "Terminaste la tanda.", sudden: "Muerte súbita: fallaste.", stopped: "Paraste el entrenamiento.", left: "",
};
const pct = (x) => `${Math.round(x * 100)} %`;
const secs = (ms) => (ms == null ? "—" : `${(ms / 1000).toFixed(2)} s`);

function Toggle({ on, onChange, children, testid }) {
  return <button type="button" class="chipbtn" aria-pressed={on ? "true" : "false"} onClick={onChange} data-testid={testid}>{children}</button>;
}

function ConfigStage() {
  const t = training.value;
  const [config, setConfig] = useState(t.config);
  const change = (patch) => setConfig((c) => sanitizeConfig({ ...c, ...patch }));
  const flip = (key, value) => {
    const list = config[key].includes(value) ? config[key].filter((x) => x !== value) : [...config[key], value];
    if (list.length) change({ [key]: list });                      // there is always at least one of each
  };
  return (
    <>
      {t.reason === "stopped" && <div class="card-2" data-testid="training-note">Terminaste sin responder ningún QTE, así que no hay resumen.</div>}
      <div class="card-2 col" style={{ gap: "var(--sp-2)" }}>
        <p>Aquí aparecen QTE de práctica al azar, con los mismos tiempos del juego. <b>No hay daño ni puntos</b> y nada llega al servidor. Si te llega un QTE de verdad, se atiende primero y el entrenamiento espera.</p>
      </div>
      <Section title="Preajustes">
        <div class="chiprow" role="group" aria-label="Preajustes">
          {PRESETS.map(([id, name, preset]) => <button key={id} type="button" class="chipbtn" onClick={() => setConfig(sanitizeConfig(preset))} data-testid={`preset-${id}`}>{name}</button>)}
        </div>
      </Section>
      <Section title="Qué practicar">
        <Setting title="Tipos de QTE" hint="Se elige uno al azar de los marcados." stack>
          <div class="chiprow" role="group" aria-label="Tipos de QTE">
            {KINDS.map((k) => <Toggle key={k} on={config.kinds.includes(k)} onChange={() => flip("kinds", k)} testid={`kind-${k}`}>{MODE[k]}</Toggle>)}
          </div>
          <span class="faint" style={{ fontSize: ".75rem" }}>{config.kinds.map((k) => `${MODE[k]}: ${KIND_HINT[k]}`).join(" · ")}</span>
        </Setting>
        <Setting title="Dificultad" hint="Cambia las ventanas de esquive y parry, como en el juego." stack>
          <div class="chiprow" role="group" aria-label="Dificultad">
            {DIFFICULTIES.map((d) => <Toggle key={d} on={config.difficulties.includes(d)} onChange={() => flip("difficulties", d)} testid={`diff-${d}`}>{DIFFICULTY[d]}</Toggle>)}
          </div>
        </Setting>
        {config.kinds.includes("combo") && (
          <Setting title="Largo del combo" stack>
            <Range label="Largo del combo" min={2} max={6} value={config.comboLength} onChange={(v) => change({ comboLength: v })} format={(v) => `${v} pasos`} />
          </Setting>
        )}
      </Section>
      <Section title="Ritmo">
        <Setting title="Cantidad" hint="Cuántos QTE tiene la tanda." stack>
          <Segmented label="Cantidad" value={config.count} onChange={(v) => change({ count: v })} options={COUNTS.map((n) => [n, COUNT_LABEL[n]])} />
        </Setting>
        <Setting title="Pausa entre QTE" hint="Un tiempo al azar entre estos dos valores." stack>
          <Range label="Pausa mínima" min={0.3} max={15} step={0.1} value={config.gapMin} onChange={(v) => change({ gapMin: v })} format={(v) => `mín. ${v.toFixed(1)} s`} />
          <Range label="Pausa máxima" min={0.3} max={15} step={0.1} value={config.gapMax} onChange={(v) => change({ gapMax: v })} format={(v) => `máx. ${v.toFixed(1)} s`} />
        </Setting>
        <Setting title="A la vez" hint="Cuántos QTE pueden estar en pantalla al mismo tiempo (para practicar la prioridad)." stack>
          <Segmented label="A la vez" value={config.simultaneous} onChange={(v) => change({ simultaneous: v })} options={[[1, "1"], [2, "2"], [3, "3"]]} />
        </Setting>
        <Setting title="Velocidad" hint="Por encima de 100 % las ventanas son más cortas que las del juego; por debajo, más largas." stack>
          <Range label="Velocidad" min={50} max={200} step={5} value={config.speed} onChange={(v) => change({ speed: v })} format={(v) => `${v} %`} />
        </Setting>
        <Setting title="Muerte súbita" hint="La tanda termina en cuanto fallas uno.">
          <Switch label="Muerte súbita" checked={config.suddenDeath} onChange={(v) => change({ suddenDeath: v })} />
        </Setting>
      </Section>
      <button class="btn btn-primary btn-lg btn-block" type="button" onClick={() => startTraining(config)} data-testid="training-start"><Play size={18} /> Empezar</button>
    </>
  );
}

function Stat({ label, value, testid }) {
  return <div><span>{label}</span><b class="num" data-testid={testid}>{value}</b></div>;
}

function RunStage() {
  const t = training.value;
  const { stats, config } = t;
  useNow(250, true);
  const total = config.count || "∞";
  const avg = averageMs(stats);
  return (
    <div class="col" style={{ gap: "var(--sp-4)" }} data-testid="training-run" data-avoid>
      <div class="card-2 col" style={{ gap: "var(--sp-3)" }}>
        <div class="row">
          <strong class="grow">{t.paused ? "En pausa" : stats.total === 0 && t.spawned === 0 ? "Prepárate…" : "Entrenando"}</strong>
          <span class="num dim" data-testid="training-progress">{stats.total} / {total}</span>
        </div>
        {config.count > 0 && <div class="bar-thin"><i style={{ width: `${Math.min(100, (stats.total / config.count) * 100)}%` }} /></div>}
        <div class="metrics">
          <Stat label="Aciertos" value={stats.ok} testid="stat-ok" />
          <Stat label="Fallos" value={stats.fail} testid="stat-fail" />
          <Stat label="Racha" value={stats.streak} testid="stat-streak" />
          <Stat label="Precisión" value={stats.total ? pct(accuracy(stats)) : "—"} />
          <Stat label="Tiempo medio" value={secs(avg)} />
        </div>
        <div class="dots" aria-hidden="true">{stats.recent.map((r, i) => <i key={i} data-ok={r} />)}</div>
      </div>
      <div class="row" style={{ gap: "var(--sp-2)" }}>
        <button class="btn grow" type="button" onClick={() => pauseTraining(!t.paused)} data-testid="training-pause">{t.paused ? <><Play size={16} /> Seguir</> : <><Pause size={16} /> Pausar</>}</button>
        <button class="btn btn-primary grow" type="button" onClick={() => stopTraining("stopped")} data-testid="training-stop"><Square size={16} /> Terminar</button>
      </div>
      <p class="faint center-text" style={{ fontSize: ".8125rem" }}>Responde con los botones flotantes o con las teclas de siempre (E, P, flechas, Espacio).</p>
    </div>
  );
}

function Breakdown({ title, rows, label }) {
  const keys = Object.keys(rows);
  if (!keys.length) return null;
  return (
    <div class="card-2 col" style={{ gap: "var(--sp-2)" }}>
      <strong>{title}</strong>
      {keys.map((k) => (
        <div class="row brk" key={k}><span class="grow">{label[k] || k}</span><span class="num dim">{rows[k].ok} / {rows[k].n}</span><span class="num" style={{ minWidth: "3.5em", textAlign: "right" }}>{pct(rows[k].ok / rows[k].n)}</span></div>
      ))}
    </div>
  );
}

const RECORD = { streak: "Mejor racha", accuracy: "Mejor precisión", speed: "Tiempo medio más rápido" };

function DoneStage() {
  const t = training.value;
  const { stats } = t;
  const best = loadBest();
  const seconds = Math.max(1, Math.round((t.endedAt - t.startedAt) / 1000));
  return (
    <div class="col" style={{ gap: "var(--sp-4)" }} data-testid="training-done">
      <div class="card-2 col" style={{ gap: "var(--sp-3)" }}>
        <div class="row"><Trophy size={20} /><strong class="grow">Resumen del entrenamiento</strong><span class="faint num">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span></div>
        {REASON[t.reason] && <p class="dim">{REASON[t.reason]}</p>}
        <div class="metrics">
          <Stat label="Precisión" value={pct(accuracy(stats))} testid="sum-accuracy" />
          <Stat label="Aciertos" value={`${stats.ok} / ${stats.total}`} testid="sum-ok" />
          <Stat label="Mejor racha" value={stats.bestStreak} testid="sum-streak" />
          <Stat label="Tiempo medio" value={secs(averageMs(stats))} />
          <Stat label="Más rápido" value={secs(stats.bestMs)} />
          <Stat label="Black Flash" value={stats.bf} />
          <Stat label="Sin pulsar" value={stats.timeouts} />
        </div>
        {t.recordsBeaten.length > 0 && (
          <div class="row" style={{ flexWrap: "wrap", gap: "var(--sp-2)" }} data-testid="training-records">
            {t.recordsBeaten.map((r) => <span class="chip primary" key={r}><Trophy size={12} /> ¡Récord! {RECORD[r]}</span>)}
          </div>
        )}
        <p class="faint" style={{ fontSize: ".75rem" }}>Tus mejores marcas en este dispositivo: racha {best.bestStreak || 0}{best.accuracy ? ` · precisión ${pct(best.accuracy)}` : ""}{best.averageMs ? ` · tiempo medio ${secs(best.averageMs)}` : ""}.</p>
      </div>
      <Breakdown title="Por tipo" rows={stats.byKind} label={MODE} />
      <Breakdown title="Por dificultad" rows={stats.byDifficulty} label={DIFFICULTY} />
      <div class="row" style={{ gap: "var(--sp-2)" }}>
        <button class="btn grow" type="button" onClick={backToConfig} data-testid="training-settings"><RotateCcw size={16} /> Cambiar ajustes</button>
        <button class="btn btn-primary grow" type="button" onClick={() => startTraining(t.config)} data-testid="training-again"><Play size={16} /> Otra vez</button>
      </div>
    </div>
  );
}

export function TrainingPage() {
  const phase = training.value.phase;
  useEffect(() => () => { if (training.value.phase === "run") stopTraining("left"); }, []);       // leaving the page ends the session
  return (
    <Page title="Entrenamiento" icon={Dumbbell}>
      {phase === "config" && <ConfigStage />}
      {phase === "run" && <RunStage />}
      {phase === "done" && <DoneStage />}
    </Page>
  );
}
