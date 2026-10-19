import { useEffect, useRef } from "preact/hooks";
import { FastForward, X } from "lucide-preact";
import { cine, stopCine } from "../cine.js";
import { perms, prefs } from "../state.js";
import { playSound, setMusic, sounds } from "../audio.js";
import { captionAt, crossed, elapsedSeconds, imageAt, isOver, musicStepBefore, sceneAt } from "../cinema-model.js";
import { rpc } from "../net.js";
import { useNow } from "../hooks.js";
import { cdn, cx } from "../util.js";
import { Avatar } from "./Avatar.jsx";

const soundOf = (id) => sounds.value.find((s) => s.id === id) || null;

// The one-off steps whose moment has come: a sound plays once, an effect starts once.
function useOneShots(state, t) {
  const last = useRef({ id: null, t: null });
  const effect = useRef(null);
  if (last.current.id !== state.run.id) last.current = { id: state.run.id, t: null };
  const cinema = state.run.cinema;
  let from = last.current.t;
  last.current.t = from === null ? t : Math.max(from, t);
  if (from === null) {
    if (t >= 1) {                                                       // joining late: no sound that already played, but the music is the one it should be
      const before = musicStepBefore(cinema, t);
      if (before) restoreMusic(before);
      return effect.current;
    }
    from = -0.001;                                                      // a fresh start: what is at second 0 plays
  }
  for (const step of crossed(cinema, from, t)) {
    if (step.type === "audio") playStep(step);
    else effect.current = { ...step, n: (effect.current ? effect.current.n : 0) + 1, started: t };
  }
  return effect.current;
}

function playStep(step) {
  if (step.mode === "stop_music") { setMusic(null); return; }
  const sound = soundOf(step.sound);
  if (!sound) return;
  if (step.mode === "music") setMusic({ sound, startedAt: Date.now(), now: Date.now(), volume: step.volume ?? 100, loop: true }, { arrival: performance.now() });
  else playSound({ sound, volume: Math.round(((step.volume ?? 100) * sound.volume) / 100) });
}
function restoreMusic(step) {
  if (step.mode === "stop_music") return;
  const sound = soundOf(step.sound);
  if (sound) setMusic({ sound, startedAt: Date.now(), now: Date.now(), volume: step.volume ?? 100, loop: true });
}

export function CinemaLayer() {
  const state = cine.value;
  const now = useNow(50, !!state);                                      // the clock goes down as a prop: a component whose props do not change is not redrawn                                                  // the picture is redrawn about 20 times a second while a cinematic plays
  if (!state) return null;
  return <Playing state={state} now={now} />;
}

function Playing({ state, now }) {
  const cinema = state.run.cinema;
  const t = elapsedSeconds(state.run, { arrival: state.arrival, now, transitMs: state.transitMs });
  const over = isOver(cinema, t);
  const fired = useOneShots(state, Math.min(t, cinema.duration));
  useEffect(() => { if (over) { const id = setTimeout(() => { if (cine.value === state) stopCine(); }, 600); return () => clearTimeout(id); } return undefined; }, [over]);

  const scene = sceneAt(cinema, t);
  const caption = captionAt(cinema, t);
  const picture = imageAt(cinema, t);
  const calm = prefs.value.motion === "reduced";
  const live = fired && t - fired.started < (fired.duration || 0.6) ? fired : null;
  const closing = over || t > cinema.duration - 0.6;
  const text = caption ? (caption.typing ? caption.step.text.slice(0, caption.shown) : caption.step.text) : "";
  const stopForAll = async () => { try { await rpc("gm.cinema_stop", {}); } catch { /* the page will be told when it stops */ } stopCine(); };

  return (
    <div class={cx("cine", closing && "closing", cinema.bars && "bars", live && live.effect === "shake" && !calm && "shake")} data-testid="cine" data-t={t.toFixed(2)} aria-live="polite">
      <div class="cine-bg" style={{ background: scene.color }}>
        {scene.image && <img src={cdn(scene.image)} alt="" style={{ opacity: 1 - scene.dim / 100 }} />}
      </div>
      {cinema.bars && <><i class="cine-bar top" /><i class="cine-bar bottom" /></>}
      {picture && <img key={picture.step.at} class={cx("cine-image", picture.step.position)} src={cdn(picture.step.image)} alt="" data-testid="cine-image" />}
      {caption && (
        <div key={caption.step.at} class={cx("cine-caption", `size-${caption.step.size}`, `fx-${caption.step.effect}`, caption.left < 0.4 && "leaving")} data-testid="cine-caption"
          style={caption.step.color ? { "--caption": caption.step.color } : undefined}>
          {(caption.step.speaker || caption.step.avatar) && (
            <div class="cine-speaker">{caption.step.avatar && <Avatar url={caption.step.avatar} name={caption.step.speaker || "?"} size="sm" />}<b>{caption.step.speaker}</b></div>
          )}
          <p>{text}{caption.typing && caption.shown < caption.step.text.length && <i class="cine-caret" />}</p>
        </div>
      )}
      {live && live.effect === "flash" && !calm && <i key={`f${live.n}`} class="cine-flash" style={{ background: live.color, animationDuration: `${live.duration}s` }} />}
      {live && live.effect === "blackout" && <i key={`b${live.n}`} class="cine-blackout" style={{ background: live.color || "#000", animationDuration: `${live.duration}s` }} />}
      <div class="cine-controls">
        {state.preview && <span class="chip">Vista previa</span>}
        {(cinema.skippable || state.preview) && (
          <button class="btn btn-sm cine-skip" type="button" onClick={() => stopCine()} data-testid="cine-skip"><FastForward size={14} /> Saltar</button>
        )}
        {perms.value.gm && !state.preview && (
          <button class="btn btn-sm btn-danger" type="button" onClick={stopForAll} data-testid="cine-stop-all"><X size={14} /> Parar para todos</button>
        )}
      </div>
    </div>
  );
}
