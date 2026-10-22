// The game masters' quick controls, always at hand beside the chat (and in a drawer on phones): the boss, the fight, a QTE, a cinematic, the
// music, and what is already linked to each moment of a fight. Every button does what the panel's own button does (the server asks for the role again).
import { useState } from "preact/hooks";
import { Bug, Clapperboard, Crown, Pause, Flag, Flame, Heart, Link2, Music, Play, Skull, Sparkles, Square, Swords, Wand2, Zap } from "lucide-preact";
import { go, perms } from "../state.js";
import { act } from "../panel/data.js";
import { ConfirmButton } from "./Common.jsx";
import { Switch } from "./Controls.jsx";
import { Bar, DIFFICULTIES } from "../views/gm/ui.jsx";
import { useLive } from "../views/gm/hooks.js";
import { PRESETS } from "../fx-model.js";
import { cx } from "../util.js";
import { mobs } from "../mobs.js";

const MODES = [["single", "Individual"], ["group", "Grupal"], ["combo", "Combo"], ["direction", "Dirección"], ["flick", "Deslizar"], ["drag", "Arrastrar"], ["mash", "Machacar"], ["fake", "Falso"]];

function Block({ icon: Icon, title, children, testid }) {
  return (
    <section class="deck-block" data-testid={testid}>
      <h3 class="deck-title"><Icon size={13} /> {title}</h3>
      {children}
    </section>
  );
}

function Boss({ d, run, busy }) {
  const boss = d.boss.active;
  const [damage, setDamage] = useState("10");
  if (!boss) {
    return (
      <div class="col" style={{ gap: "8px" }}>
        {d.boss.character
          ? <button class="btn btn-primary btn-block" type="button" disabled={busy} onClick={() => run("gm.boss_spawn", {}, `«${d.boss.character}» aparece como jefe.`)} data-testid="deck-spawn"><Wand2 size={15} /> Aparecer a «{d.boss.character}»</button>
          : <p class="faint deck-hint">Elige qué personaje de Tupperbox hace de jefe.</p>}
        <div class="row" style={{ gap: "8px" }}>
          <Switch label="Modo jefe de Tupperbox" checked={d.boss.mode} onChange={(on) => run("gm.boss_mode", { on })} />
          <span class="deck-hint">Modo jefe de Tupperbox {d.boss.mode ? "activado" : "desactivado"}</span>
        </div>
        <button class="btn btn-sm btn-ghost" type="button" onClick={() => go("gm", { tab: "boss" })}>{d.boss.character ? "Ajustes y registro de jefes" : "Elegir personaje y registrar jefes"}</button>
      </div>
    );
  }
  const amount = (pct) => Math.max(1, Math.round((boss.max * pct) / 100));
  return (
    <div class="col" style={{ gap: "8px" }} data-testid="deck-boss">
      <div class="row" style={{ gap: "8px" }}>
        <strong class="ellipsis grow">{boss.name}</strong>
        {boss.tupper && <span class="chip">Tupperbox</span>}
      </div>
      <Bar kind="boss" value={boss.hp} max={boss.max} label={`Vida de ${boss.name}`} />
      <div class="deck-grid">
        {[5, 10, 25].map((p) => <button key={p} class="btn btn-sm" type="button" disabled={busy} onClick={() => run("gm.boss_hp", { action: "damage", amount: amount(p) })} data-testid={`deck-dmg-${p}`}>−{p} %</button>)}
        <button class="btn btn-sm" type="button" disabled={busy} onClick={() => run("gm.boss_hp", { action: "heal", amount: amount(10) })} data-testid="deck-heal"><Heart size={13} /> +10 %</button>
      </div>
      <div class="row" style={{ gap: "6px" }}>
        {/* the box keeps what is typed (an empty box while correcting the number stays empty); the button uses the number in it */}
        <input class="input num" type="number" inputMode="numeric" min={1} max={999999} value={damage} aria-label="Daño exacto" style={{ width: "92px" }} onInput={(e) => setDamage(e.currentTarget.value)} />
        <button class="btn btn-sm grow" type="button" disabled={busy || !(Math.round(Number(damage)) >= 1)} onClick={() => run("gm.boss_hp", { action: "damage", amount: Math.round(Number(damage)) })} data-testid="deck-dmg-exact">
          {Math.round(Number(damage)) >= 1 ? `Hacer ${Math.round(Number(damage))} de daño` : "Escribe el daño"}
        </button>
      </div>
      {(d.boss.abilities.length > 0 || d.boss.domain) && (
        <div class="deck-grid" data-testid="deck-abilities" aria-label="Habilidades del jefe">
          {d.boss.abilities.map((a) => <button key={a.name} class="btn btn-sm" type="button" disabled={busy} title={`${a.damage} de daño a todos`} onClick={() => run("gm.ability_use", { name: a.name }, `«${a.name}» lanzada.`)} data-testid={`deck-ability-${a.name}`}><Flame size={13} /> {a.name}</button>)}
          {d.boss.domain && <button class="btn btn-sm" type="button" disabled={busy} onClick={() => run("gm.domain_expand", {}, `«${d.boss.domain}» se expande.`)} data-testid="deck-domain"><Sparkles size={13} /> {d.boss.domain}</button>}
        </div>
      )}
      <div class="row" style={{ gap: "6px" }}>
        <ConfirmButton icon={Skull} confirm="Sí, derrotarlo" onConfirm={() => run("gm.boss_hp", { action: "defeat" }, "Jefe derrotado.")} class="grow" testid="deck-defeat">Derrotar</ConfirmButton>
        <ConfirmButton confirm="Sí, retirarlo" onConfirm={() => run("gm.boss_remove", {}, "Jefe retirado.")} class="btn-ghost" testid="deck-remove">Retirar</ConfirmButton>
      </div>
    </div>
  );
}

function Scene({ d, run, busy }) {
  const [cinema, setCinema] = useState("");
  const [track, setTrack] = useState("");
  const chosen = d.cinemas.find((c) => c.id === (cinema || (d.cinemas[0] && d.cinemas[0].id)));
  const pick = track || (d.tracks[0] && d.tracks[0].id) || "";
  return (
    <div class="col" style={{ gap: "8px" }}>
      {d.cinemas.length === 0 ? <p class="faint deck-hint">Todavía no hay cinemáticas.</p> : (
        <div class="row" style={{ gap: "6px" }}>
          <select class="select grow" value={chosen ? chosen.id : ""} aria-label="Cinemática" onChange={(e) => setCinema(e.currentTarget.value)} data-testid="deck-cinema">
            {d.cinemas.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.seconds} s</option>)}
          </select>
          {d.running
            ? <button class="btn btn-sm btn-danger" type="button" onClick={() => run("gm.cinema_stop", {}, "Cinemática parada.")} data-testid="deck-cinema-stop"><Square size={13} /> Parar</button>
            : <button class="btn btn-sm btn-primary" type="button" disabled={busy || !chosen} onClick={() => run("gm.cinema_play", { id: chosen.id }, "Suena y se ve para todos.")} data-testid="deck-cinema-play"><Clapperboard size={13} /> Poner</button>}
        </div>
      )}
      {d.tracks.length === 0 ? <p class="faint deck-hint">Sube música en la pestaña Audio.</p> : (
        <div class="row" style={{ gap: "6px" }}>
          <select class="select grow" value={pick} aria-label="Música" onChange={(e) => setTrack(e.currentTarget.value)} data-testid="deck-track">
            {d.tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <button class="btn btn-sm" type="button" disabled={busy || !pick} onClick={() => run("gm.music_play", { id: pick, volume: 100 }, "Suena para todos.")} data-testid="deck-music-play"><Music size={13} /> Sonar</button>
        </div>
      )}
      {d.music && (
        <div class="row" style={{ gap: "6px" }}>
          <span class="deck-hint grow ellipsis">Suena: {d.music.name}</span>
          <button class="btn btn-sm btn-ghost" type="button" onClick={() => run("gm.music_stop", {})} data-testid="deck-music-stop"><Square size={13} /> Parar</button>
        </div>
      )}
    </div>
  );
}

// What one moment of the fight starts, in a few words.
export function linkText(l, sounds) {
  const music = l.phase ? (l.phase.mode === "stop" ? "para la música" : `pone «${(sounds.find((s) => s.id === l.phase.sound) || { name: "¿?" }).name}»`) : "";
  const cue = l.cue ? (sounds.find((s) => s.id === l.cue.sound) || { name: "¿?" }).name : "";
  return [...l.cinemas.map((c) => `🎬 ${c.name}${c.boss ? ` (solo ${c.boss})` : ""}`), music ? `🎵 ${music}` : "", l.effect ? `✨ ${PRESETS[l.effect.preset].label}` : "", cue ? `🔊 ${cue}` : ""].filter(Boolean).join(" · ");
}

function Links({ d }) {
  const rows = d.links.filter((l) => linkText(l, d.sounds));
  return (
    <div class="col" style={{ gap: "6px" }} data-testid="deck-links">
      {rows.length === 0 && <p class="faint deck-hint">Nada enlazado todavía. En la pestaña Jefe del panel puedes ligar una cinemática, música, un efecto y un sonido a «Aparece el jefe», «Cae el jefe» o «Empieza el combate», y todo salta solo.</p>}
      {rows.map((l) => (
        <div class="deck-link" key={l.event} data-testid={`deck-link-${l.event}`}>
          <strong>{l.label}</strong>
          <span class="deck-hint">{linkText(l, d.sounds)}</span>
        </div>
      ))}
      <button class="btn btn-sm btn-ghost" type="button" onClick={() => go("gm", { tab: "boss" })} data-testid="deck-links-edit">Cambiar los enlaces</button>
    </div>
  );
}

// the mini enemies: send one in from the bestiary, pause them, clear the field
function Mobs({ d, run, busy }) {
  const book = (d.mobs && d.mobs.bestiary) || [];
  const live = mobs.value;
  const [pick, setPick] = useState("");
  const chosen = book.find((t) => t.id === pick) || book[0];
  if (!book.length) return <p class="faint deck-hint">Crea enemigos en el panel (pestaña Enemigos) para enviarlos desde aquí.</p>;
  return (
    <div class="col" style={{ gap: "8px" }}>
      <div class="row" style={{ gap: "6px" }}>
        <select class="input grow" value={chosen ? chosen.id : ""} aria-label="Enemigo" onChange={(e) => setPick(e.currentTarget.value)} data-testid="deck-mob-pick">
          {book.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.hp} PV</option>)}
        </select>
        <button class="btn btn-sm btn-primary" type="button" disabled={busy || !chosen} data-testid="deck-mob-spawn" onClick={() => run("gm.mob_spawn", { id: chosen.id, count: 1 })}><Play size={13} /> Enviar</button>
      </div>
      {live.list.length > 0 && (
        <div class="deck-grid">
          <button class="btn btn-sm" type="button" disabled={busy} onClick={() => run("gm.mob_pause", { paused: !live.paused })} data-testid="deck-mob-pause">
            {live.paused ? <><Play size={13} /> Reanudar ({live.list.length})</> : <><Pause size={13} /> Pausar ({live.list.length})</>}
          </button>
          <ConfirmButton icon={Square} confirm="Sí, retirar" onConfirm={() => run("gm.mob_remove", { id: "all" }, "Enemigos retirados.")} testid="deck-mob-clear">Retirar</ConfirmButton>
        </div>
      )}
    </div>
  );
}

export function GmDeck() {
  return perms.value.gm ? <Deck /> : null;          // the requests only start for who has the role
}

function Deck() {
  const q = useLive("gm.quick", {}, 3000);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("single");
  const [difficulty, setDifficulty] = useState("medium");
  const d = q.data;
  const run = async (op, args, done) => {
    setBusy(true);
    const out = await act(op, args, done);
    setBusy(false);
    q.refresh();
    return out;
  };
  if (!d) return <div class="gm-deck" data-testid="gm-deck"><p class="faint deck-hint">{q.error || "Cargando el mando…"}</p></div>;
  const s = d.state;
  return (
    <div class="gm-deck" data-testid="gm-deck">
      <div class="deck-head">
        <Crown size={15} /><strong>Mando del GM</strong>
        <span class={cx("chip", s.fight && "ok")} data-testid="deck-fight-state">{s.fight ? "En combate" : "Sin combate"}</span>
      </div>
      <Block icon={Skull} title="Jefe" testid="deck-boss-block"><Boss d={d} run={run} busy={busy} /></Block>
      <Block icon={Swords} title="Combate">
        <div class="deck-grid">
          {s.fight
            ? <ConfirmButton icon={Square} confirm="Sí, terminar" onConfirm={() => run("gm.fight", { action: "end" }, "Combate terminado.")} class="deck-wide" testid="deck-fight-end">Terminar combate</ConfirmButton>
            : <button class="btn btn-sm btn-primary deck-wide" type="button" disabled={busy} onClick={() => run("gm.fight", { action: "start" }, "Combate empezado.")} data-testid="deck-fight-start"><Play size={13} /> Iniciar combate</button>}
          <button class="btn btn-sm deck-wide" type="button" disabled={busy} onClick={() => run("gm.checkpoint", {}, "Checkpoint lanzado.")} data-testid="deck-checkpoint"><Flag size={13} /> Checkpoint</button>
        </div>
      </Block>
      <Block icon={Zap} title="QTE rápido">
        <div class="deck-chips" role="group" aria-label="Tipo de QTE">
          {MODES.map(([id, text]) => <button key={id} type="button" class="choice" aria-pressed={mode === id ? "true" : "false"} onClick={() => setMode(id)}>{text}</button>)}
        </div>
        <div class="deck-chips" role="group" aria-label="Dificultad">
          {DIFFICULTIES.map(([id, text]) => <button key={id} type="button" class="choice" aria-pressed={difficulty === id ? "true" : "false"} onClick={() => setDifficulty(id)}>{text}</button>)}
        </div>
        <button class="btn btn-sm btn-block" type="button" disabled={busy || s.stunLeft > 0} onClick={() => run("gm.launch", { mode, difficulty, target: null })} data-testid="deck-launch">
          <Zap size={13} /> {s.stunLeft > 0 ? `Jefe aturdido (${Math.ceil(s.stunLeft)} s)` : "Lanzar a alguien al azar"}
        </button>
      </Block>
      <Block icon={Bug} title="Enemigos" testid="deck-mobs-block"><Mobs d={d} run={run} busy={busy} /></Block>
      <Block icon={Clapperboard} title="Escena y música"><Scene d={d} run={run} busy={busy} /></Block>
      <Block icon={Link2} title="Enlazado a cada momento" testid="deck-links-block"><Links d={d} /></Block>
      <button class="btn btn-sm btn-ghost btn-block" type="button" onClick={() => go("gm", { tab: "event" })}>Abrir el panel completo</button>
    </div>
  );
}
