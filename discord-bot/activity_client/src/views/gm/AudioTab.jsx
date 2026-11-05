import { useRef, useState } from "preact/hooks";
import { Bell, Library, Music, Play, Square, Trash2, Upload, Volume2, Zap } from "lucide-preact";
import { Block, ConfirmButton, Empty, Pill } from "../../ui/Common.jsx";
import { Range, Switch } from "../../ui/Controls.jsx";
import { uploadAudio } from "../../net.js";
import { toast } from "../../state.js";
import { playLocal } from "../../audio.js";
import { cx, plural } from "../../util.js";
import { Card } from "./ui.jsx";
import { useDo, useLive } from "./hooks.js";

const SCOPE = [["all", "Todos"], ["target", "Solo quien lo vive"]];
const GROUPS = [
  ["QTE", ["qte_start", "qte_easy", "qte_medium", "qte_hard", "qte_impossible", "qte_group", "qte_combo", "qte_direction", "qte_bf_chain", "qte_fake"]],
  ["Black Flash y combos", ["black_flash", "chain_max", "combo_done", "fake_fail", "group_done"]],
  ["Tus respuestas", ["evade_ok", "parry_ok", "counter", "rescue_ok", "combo_step", "qte_fail"]],
  ["Golpes y vida", ["player_hit", "low_hp", "heal", "boss_hit"]],
  ["Poderes", ["power_used", "power_1", "power_2"]],
  ["Dominios", ["domain_cast", "domain", "boss_domain"]],
  ["Combate", ["boss_spawn", "boss_defeated", "fight_start", "fight_end", "player_down", "checkpoint"]],
  ["Enemigos", ["mob_spawn", "mob_attack", "mob_hit", "mob_down", "mobs_cleared"]],
];
const bytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

// ---- the music everybody hears together -----------------------------------------------------------------------------------------
function MusicCard({ d, run, replace, busy }) {
  const now = d.music;
  const tracks = d.library.filter((s) => s.kind === "music");
  const [volume, setVolume] = useState(null);
  const shown = volume === null ? (now ? now.volume : 100) : volume;
  const start = async (sound) => { const out = await run("music", "gm.music_play", { id: sound.id, volume: 100 }, `Suena «${sound.name}» para todos.`); if (out) { setVolume(null); replace(out); } };
  const stop = async () => { const out = await run("music", "gm.music_stop", {}, "Música parada."); if (out) replace(out); };
  const change = async (v) => { setVolume(v); const out = await run("music-volume", "gm.music_volume", { volume: v }); if (out) { setVolume(null); replace(out); } };
  return (
    <Card title="Música" icon={Music} hint="Suena a la vez para todos los que están en la Actividad. Quien entra tarde la oye por donde va." testid="gm-music">
      {now ? (
        <div class="gm-now" data-testid="gm-music-now">
          <div class="row" style={{ gap: "10px" }}>
            <Music size={18} /><strong class="grow ellipsis">{now.sound.name}</strong>
            <Pill tone="ok">suena</Pill>
            <button class="btn btn-sm btn-danger" type="button" onClick={stop} disabled={busy !== null} data-testid="gm-music-stop"><Square size={14} /> Parar</button>
          </div>
          <Range label="Volumen de la música" min={0} max={100} step={5} value={shown} onChange={change} format={(v) => `${v} %`} />
        </div>
      ) : <p class="faint" data-testid="gm-music-none">No suena nada ahora.</p>}
      {tracks.length === 0
        ? <p class="faint">Sube música en la biblioteca (marca el tipo «Música») para poder ponerla aquí.</p>
        : <div class="gm-pads">{tracks.map((s) => (
            <button key={s.id} type="button" class={cx("sound-pad", now && now.sound.id === s.id && "is-on")} onClick={() => start(s)} disabled={busy !== null} data-testid={`gm-music-play-${s.id}`}>
              <Play size={14} /><span class="ellipsis">{s.name}</span>
            </button>))}</div>}
    </Card>
  );
}

// ---- the sounds to play right now -----------------------------------------------------------------------------------------------
function BoardCard({ d, run, busy }) {
  const pads = d.library.filter((s) => s.kind !== "music");
  const play = (sound) => run(`play-${sound.id}`, "gm.audio_play", { id: sound.id, volume: 100 });
  return (
    <Card title="Efectos al momento" icon={Zap} hint="Pulsa y suena para todos en ese instante: un golpe, una risa, un aviso." testid="gm-board"
      actions={<button class="btn btn-sm btn-ghost" type="button" onClick={() => run("stop", "gm.audio_stop", {})} data-testid="gm-audio-cut"><Square size={14} /> Cortar</button>}>
      {pads.length === 0 ? <p class="faint">Aún no hay efectos. Sube sonidos en la biblioteca.</p>
        : <div class="gm-pads">{pads.map((s) => (
            <button key={s.id} type="button" class="sound-pad" onClick={() => play(s)} disabled={busy === `play-${s.id}`} data-testid={`gm-pad-${s.id}`}>
              <Zap size={14} /><span class="ellipsis">{s.name}</span>
            </button>))}</div>}
    </Card>
  );
}

// ---- cues: a sound for what happens ---------------------------------------------------------------------------------------------
function CueRow({ event, d, run, replace }) {
  const cue = d.cues[event.id] || null;
  const set = async (patch) => {
    const next = { sound: cue ? cue.sound : "", volume: cue ? cue.volume : 100, scope: cue ? cue.scope : event.scope, enabled: cue ? cue.enabled : true, ...patch };
    if (!next.sound) return;
    const out = await run(`cue-${event.id}`, "gm.cue_set", { event: event.id, ...next });
    if (out) replace(out);
  };
  const clear = async () => { const out = await run(`cue-${event.id}`, "gm.cue_clear", { event: event.id }, "Aviso sin sonido."); if (out) replace(out); };
  return (
    <div class="gm-cue" data-testid={`gm-cue-${event.id}`}>
      <div class="info"><strong>{event.label}</strong></div>
      <select class="select" value={cue ? cue.sound : ""} aria-label={`Sonido de «${event.label}»`} data-testid={`gm-cue-sound-${event.id}`}
        onChange={(e) => { const sound = e.currentTarget.value; if (sound) set({ sound }); else if (cue) clear(); }}>
        <option value="">— sin sonido —</option>
        {d.library.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      {cue && (
        <>
          <input class="range" type="range" min={0} max={100} step={5} value={cue.volume} aria-label={`Volumen de «${event.label}»`} data-testid={`gm-cue-volume-${event.id}`}
            onChange={(e) => set({ volume: Number(e.currentTarget.value) })} />
          <select class="select" value={cue.scope} aria-label={`Quién oye «${event.label}»`} onChange={(e) => set({ scope: e.currentTarget.value })}>
            {SCOPE.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
          <Switch label={`«${event.label}» activado`} checked={cue.enabled} onChange={(v) => set({ enabled: v })} />
          <button class="btn btn-sm btn-ghost" type="button" onClick={() => run(`test-${event.id}`, "gm.cue_test", { event: event.id })} data-testid={`gm-cue-test-${event.id}`}><Play size={14} /> Probar</button>
        </>
      )}
    </div>
  );
}

function CuesCard({ d, run, replace }) {
  const byId = Object.fromEntries(d.events.map((e) => [e.id, e]));
  return (
    <Card title="Avisos automáticos" icon={Bell} hint="Elige qué suena cuando pasa algo en el juego. Un QTE usa el aviso de su tipo; si no lo tiene, el de su dificultad; y si tampoco, el de «Empieza un QTE»." testid="gm-cues">
      {d.library.length === 0 && <p class="faint">Primero sube sonidos a la biblioteca.</p>}
      {GROUPS.map(([title, ids]) => (
        <div key={title} class="gm-cue-group">
          <h3 class="gm-sub">{title}</h3>
          {ids.filter((id) => byId[id]).map((id) => <CueRow key={id} event={byId[id]} d={d} run={run} replace={replace} />)}
        </div>
      ))}
    </Card>
  );
}

// ---- the music that follows the fight --------------------------------------------------------------------------------------------
function PhaseRow({ event, d, run, replace }) {
  const phase = d.phases[event.id] || null;
  const tracks = d.library.filter((s) => s.kind === "music");
  const value = !phase ? "" : phase.mode === "stop" ? "__stop" : phase.sound;
  const change = async (choice) => {
    const out = choice === "" ? await run(`phase-${event.id}`, "gm.phase_clear", { event: event.id })
      : await run(`phase-${event.id}`, "gm.phase_set", { event: event.id, mode: choice === "__stop" ? "stop" : "music", sound: choice === "__stop" ? undefined : choice, volume: phase ? phase.volume : 100 });
    if (out) replace(out);
  };
  const volume = async (v) => { const out = await run(`phase-${event.id}`, "gm.phase_set", { event: event.id, mode: "music", sound: phase.sound, volume: v }); if (out) replace(out); };
  return (
    <div class="gm-cue" data-testid={`gm-phase-${event.id}`}>
      <div class="info"><strong>{event.label}</strong></div>
      <select class="select" value={value} aria-label={`Música en «${event.label}»`} data-testid={`gm-phase-select-${event.id}`} onChange={(e) => change(e.currentTarget.value)}>
        <option value="">— no cambia la música —</option>
        <option value="__stop">Parar la música</option>
        {tracks.map((s) => <option key={s.id} value={s.id}>Pone «{s.name}»</option>)}
      </select>
      {phase && phase.mode === "music" && <input class="range" type="range" min={0} max={100} step={5} value={phase.volume} aria-label={`Volumen de la música en «${event.label}»`} onChange={(e) => volume(Number(e.currentTarget.value))} />}
    </div>
  );
}

function PhasesCard({ d, run, replace }) {
  const byId = Object.fromEntries(d.events.map((e) => [e.id, e]));
  return (
    <Card title="Música del combate" icon={Music} testid="gm-phases"
      hint="La música cambia sola según el momento del combate: empieza una pista cuando aparece el jefe, otra cuando cae, o se para al terminar. Si pones música en dos momentos seguidos (aparece el jefe y empieza el combate), suena la del último.">
      {d.library.some((s) => s.kind === "music") ? null : <p class="faint">Sube música a la biblioteca (tipo «música») para poder elegirla aquí.</p>}
      {d.phaseEvents.filter((id) => byId[id]).map((id) => <PhaseRow key={id} event={byId[id]} d={d} run={run} replace={replace} />)}
    </Card>
  );
}

// ---- the library -------------------------------------------------------------------------------------------------------------------
function SoundRow({ sound, d, run, replace }) {
  const [name, setName] = useState(null);
  const save = async (patch) => { const out = await run(`sound-${sound.id}`, "gm.audio_update", { id: sound.id, ...patch }); if (out) replace(out); };
  const remove = async () => { const out = await run(`sound-${sound.id}`, "gm.audio_delete", { id: sound.id }, `«${sound.name}» borrado.`); if (out) replace(out); };
  const used = Object.entries(d.cues).filter(([, c]) => c.sound === sound.id).length;
  return (
    <div class="gm-sound" data-testid={`gm-sound-${sound.id}`}>
      <input class="input" maxLength={60} value={name === null ? sound.name : name} aria-label="Nombre del sonido" data-testid={`gm-sound-name-${sound.id}`}
        onInput={(e) => setName(e.currentTarget.value)} onBlur={() => { if (name !== null && name.trim() && name.trim() !== sound.name) save({ name: name.trim() }); setName(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
      <select class="select" value={sound.kind} aria-label="Tipo" onChange={(e) => save({ kind: e.currentTarget.value })}>
        {d.kinds.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
      </select>
      <input class="range" type="range" min={0} max={100} step={5} value={sound.volume} aria-label={`Volumen propio de «${sound.name}»`} onChange={(e) => save({ volume: Number(e.currentTarget.value) })} />
      {sound.kind === "music" && <label class="gm-check"><input type="checkbox" checked={sound.loop} onChange={(e) => save({ loop: e.currentTarget.checked })} /> repetir</label>}
      <span class="faint num">{bytes(sound.size)}</span>
      {used > 0 && <Pill tone="info">{plural(used, "aviso", "avisos")}</Pill>}
      <button class="btn btn-sm btn-ghost" type="button" onClick={() => playLocal(sound)} aria-label={`Escuchar «${sound.name}» (solo tú)`} title="Escuchar (solo tú)"><Volume2 size={14} /></button>
      <ConfirmButton icon={Trash2} confirm="Sí, borrar" onConfirm={remove} class="btn-ghost" testid={`gm-sound-delete-${sound.id}`} label={`Borrar «${sound.name}»`} />
    </div>
  );
}

function LibraryCard({ d, run, replace }) {
  const picker = useRef(null);
  const [kind, setKind] = useState("sfx");
  const [progress, setProgress] = useState(null);
  const upload = async (e) => {
    const files = [...(e.currentTarget.files || [])];
    e.currentTarget.value = "";
    let added = 0;
    for (let i = 0; i < files.length; i++) {
      setProgress({ n: i + 1, of: files.length, name: files[i].name, at: 0 });
      try { await uploadAudio(files[i], kind, (at) => setProgress({ n: i + 1, of: files.length, name: files[i].name, at })); added++; } catch (error) { toast(`${files[i].name}: ${error.message}`, "bad", 5000); }
    }
    setProgress(null);
    if (added) { toast(`${plural(added, "sonido subido", "sonidos subidos")}.`, "ok"); const out = await run("reload", "gm.audio", {}); if (out) replace(out); }
  };
  return (
    <Card title="Biblioteca" icon={Library} testid="gm-library"
      hint={`${plural(d.usage.files, "archivo", "archivos")} · ${bytes(d.usage.bytes)}. MP3, OGG, WAV, M4A, WebM, FLAC o AAC, de hasta 25 MB. Los archivos se guardan en este PC.`}>
      <div class="row wrap" style={{ gap: "8px" }}>
        <select class="select" style={{ maxWidth: "190px" }} value={kind} onChange={(e) => setKind(e.currentTarget.value)} aria-label="Tipo de lo que vas a subir" data-testid="gm-upload-kind">
          {d.kinds.map((k) => <option key={k.id} value={k.id}>Subir como: {k.label.toLowerCase()}</option>)}
        </select>
        <button class="btn btn-primary" type="button" onClick={() => picker.current && picker.current.click()} disabled={progress !== null || !d.canStore} data-testid="gm-upload"><Upload size={16} /> Subir sonidos</button>
        <input ref={picker} type="file" multiple accept="audio/*,.mp3,.ogg,.wav,.m4a,.webm,.flac,.aac" hidden onChange={upload} data-testid="gm-upload-file" />
        {progress && <span class="faint" role="status" data-testid="gm-upload-progress">Subiendo {progress.n}/{progress.of}: {progress.name} ({Math.round(progress.at * 100)} %)</span>}
      </div>
      {d.library.length === 0
        ? <Empty icon={Music} title="La biblioteca está vacía">Sube música y efectos para ponerlos a sonar o ligarlos a lo que pasa en el evento.</Empty>
        : <div class="gm-sounds">{d.library.map((s) => <SoundRow key={s.id} sound={s} d={d} run={run} replace={replace} />)}</div>}
    </Card>
  );
}

export function AudioTab() {
  const q = useLive("gm.audio", {}, 4000);
  const [busy, run] = useDo();
  return (
    <Block q={q}>
      {(d) => (
        <div class="dash-col" data-testid="gm-audio">
          <MusicCard d={d} run={run} replace={q.replace} busy={busy} />
          <BoardCard d={d} run={run} busy={busy} />
          <PhasesCard d={d} run={run} replace={q.replace} />
          <CuesCard d={d} run={run} replace={q.replace} />
          <LibraryCard d={d} run={run} replace={q.replace} />
        </div>
      )}
    </Block>
  );
}
