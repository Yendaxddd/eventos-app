import { useEffect, useRef } from "preact/hooks";
import { FastForward, X } from "lucide-preact";
import { cine, stopCine } from "../cine.js";
import { perms, prefs, view } from "../state.js";
import { musicSnapshot, playSound, restoreMusic, setMusic, sounds } from "../audio.js";
import {
  captionAt, crossed, effectsAt, elapsedSeconds, imageAt, isOver, musicStepBefore, particles, sceneAt, screenLook, stageAt, titleAt, weatherAt,
} from "../cinema-model.js";
import { rpc } from "../net.js";
import { playBinding } from "../vfx.js";
import { useNow } from "../hooks.js";
import { cdn, cx, initial } from "../util.js";
import { Avatar } from "./Avatar.jsx";

const soundOf = (id) => sounds.value.find((s) => s.id === id) || null;

// The one-off steps whose moment has come: a sound plays once, an effect of the powers' kind starts once. Everything else (captions,
// screen effects, weather...) is worked out from the clock on every frame, so somebody who joins late sees it as everybody else does.
function useOneShots(state, t, music) {
  const last = useRef(null);
  const cinema = state.run.cinema;
  let from = last.current;
  last.current = from === null ? t : Math.max(from, t);
  if (from === null) {
    if (t >= 1) {                                                       // joining late: no sound that already played, but the music is the one it should be
      const before = musicStepBefore(cinema, t);
      if (before) { music.touch(); applyMusic(before); }
      return;
    }
    from = -0.001;                                                      // a fresh start: what is at second 0 plays
  }
  for (const step of crossed(cinema, from, t, ["audio", "vfx"])) {
    if (step.type === "audio") { if (step.mode !== "play") music.touch(); playStep(step); }
    else if (!state.hidden) playBinding(step, {}, { force: state.preview });
  }
}

function playStep(step) {
  if (step.mode === "stop_music") { setMusic(null); return; }
  const sound = soundOf(step.sound);
  if (!sound) return;
  if (step.mode === "music") applyMusic(step);
  else playSound({ sound, volume: Math.round(((step.volume ?? 100) * sound.volume) / 100) });
}
function applyMusic(step) {
  if (step.mode === "stop_music") { setMusic(null); return; }
  const sound = soundOf(step.sound);
  if (sound) setMusic({ sound, startedAt: Date.now(), now: Date.now(), volume: step.volume ?? 100, loop: true }, { arrival: performance.now() });
}

export function CinemaLayer() {
  const state = cine.value;
  const now = useNow(50, !!state);                                      // the clock goes down as a prop: about 20 redraws a second while one plays
  if (!state) return null;
  // a new run (the same cinematic played again, a new preview) starts from scratch: what it already played is not remembered
  return <Playing key={`${state.run.id}:${state.run.startedAt}`} state={state} now={now} />;
}

// The music this cinematic changed on this screen goes back to the event's when it ends (a preview, above all, must not steal it).
function useMusicGuard() {
  const snap = useRef(null);
  useEffect(() => () => { if (snap.current) restoreMusic(snap.current); }, []);
  return { touch: () => { if (!snap.current) snap.current = musicSnapshot(); } };
}

function Playing({ state, now }) {
  const cinema = state.run.cinema;
  const t = elapsedSeconds(state.run, { arrival: state.arrival, now, transitMs: state.transitMs });
  const over = isOver(cinema, t);
  const music = useMusicGuard();
  useOneShots(state, Math.min(t, cinema.duration), music);
  useEffect(() => { if (over) { const id = setTimeout(() => { if (cine.value === state) stopCine(); }, 600); return () => clearTimeout(id); } return undefined; }, [over]);
  const calm = prefs.value.motion === "reduced";
  const look = screenLook(effectsAt(cinema, t), t, calm);
  useSeeThrough(cinema.see && !state.hidden, look);
  if (state.hidden) return null;                                        // cinematics off on this screen: only their sound

  const scene = sceneAt(cinema, t);
  const caption = captionAt(cinema, t);
  const picture = imageAt(cinema, t);
  const title = titleAt(cinema, t);
  const weather = weatherAt(cinema, t);
  const stage = stageAt(cinema, t);
  const closing = over || t > cinema.duration - 0.6;
  const text = caption ? (caption.typing ? caption.step.text.slice(0, caption.shown) : caption.step.text) : "";
  const stopForAll = async () => { try { await rpc("gm.cinema_stop", {}); } catch { /* the page will be told when it stops */ } stopCine(); };
  const side = caption ? caption.step.side || "bottom" : "bottom";

  return (
    // in the game, a cinematic takes the taps (nothing under it is pressed by mistake); on the panel the game master keeps working under it
    <div class={cx("cine", closing && "closing", cinema.bars && "bars", (cinema.see || view.value === "gm") && "see")} data-testid="cine" data-t={t.toFixed(2)}>
      <div class="cine-stage" style={cinema.see ? undefined : { filter: look.filter || undefined, transform: look.transform || undefined }} data-testid="cine-stage">
        {!cinema.see && (
          <div class="cine-bg" style={{ background: scene.color }}>
            {scene.prev && scene.prev.image && <img class="cine-bg-img" src={cdn(scene.prev.image)} alt="" style={{ opacity: (1 - scene.prev.dim / 100) * (1 - (t - scene.at)) }} />}
            {scene.image && <SceneImage key={scene.at} scene={scene} t={t} calm={calm} />}
          </div>
        )}
        {cinema.see && scene.image && <div class="cine-bg see"><SceneImage key={scene.at} scene={scene} t={t} calm={calm} /></div>}
        {scene.transition === "flash" && t - scene.at < 0.5 && scene.at > 0 && <i class="cine-fill" style={{ background: "#fff", opacity: 1 - (t - scene.at) / 0.5 }} />}
        {weather && <Weather key={`${weather.weather}:${weather.intensity}`} w={weather} calm={calm} />}
        {picture && (
          <div key={picture.step.at} class={cx("cine-image", picture.step.position, `size-${picture.step.size || "medium"}`, `enter-${picture.step.enter || "pop"}`, picture.left < 0.4 && "leaving")}>
            <img class={cx(!calm && picture.step.camera && picture.step.camera !== "none" && `cam-${picture.step.camera}`)} src={cdn(picture.step.image)} alt=""
              data-testid="cine-image" style={{ "--cam-time": `${picture.step.duration}s` }} />
          </div>
        )}
        {stage && <Portraits stage={stage} />}
      </div>
      {/* colour over the picture (tints, vignettes, fades), under the words */}
      {look.layers.map((l, i) => <i key={i} class={cx("cine-fill", l.kind === "vignette" && "vignette")} style={l.kind === "vignette" ? { "--vc": l.color, opacity: l.opacity } : { background: l.color, opacity: l.opacity, mixBlendMode: l.kind === "tint" ? "color" : undefined }} />)}
      {/* the words stay readable: they shake with the screen but are never blurred or discoloured */}
      <div class="cine-front" style={cinema.see || !look.transform ? undefined : { transform: look.transform }}>
        {title && <TitleCard key={title.step.at} title={title} />}
        {caption && (
          <div key={caption.step.at} class={cx("cine-caption", `size-${caption.step.size}`, `fx-${caption.step.effect}`, `side-${side}`, caption.left < 0.4 && "leaving")} data-testid="cine-caption"
            style={caption.step.color ? { "--caption": caption.step.color } : undefined}>
            {(caption.step.speaker || (caption.step.avatar && !stage)) && (
              <div class="cine-speaker">{caption.step.avatar && !stage && <Avatar url={caption.step.avatar} name={caption.step.speaker || "?"} size="sm" />}<b>{caption.step.speaker}</b></div>
            )}
            <p aria-hidden="true">{text}{caption.typing && caption.shown < caption.step.text.length && <i class="cine-caret" />}</p>
          </div>
        )}
      </div>
      {cinema.bars && <><i class="cine-bar top" /><i class="cine-bar bottom" /></>}
      {/* a screen reader hears each line once, whole (not every letter as it is typed) */}
      <div class="sr-only" aria-live="polite">{caption ? `${caption.step.speaker ? `${caption.step.speaker}: ` : ""}${caption.step.text}` : title ? `${title.step.text}. ${title.step.subtitle || ""}` : ""}</div>
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

// A see-through cinematic (over the game): its screen effects apply to the page itself, and leave it as it was afterwards.
function useSeeThrough(on, look) {
  const el = typeof document !== "undefined" ? document.querySelector(".app") : null;
  useEffect(() => () => { if (el) { el.style.filter = ""; el.style.transform = ""; } }, [el]);
  if (!on || !el) return;
  el.style.filter = look.filter;
  el.style.transform = look.transform;
}

// The background picture with its slow camera move, started at the second of its scene (a late joiner sees it where it is).
function SceneImage({ scene, t, calm }) {
  const delay = useRef(-(t - scene.at)).current;
  const moving = !calm && scene.camera && scene.camera !== "none";
  return (
    <img class={cx("cine-bg-img", moving && `cam-${scene.camera}`)} src={cdn(scene.image)} alt=""
      style={{ opacity: 1 - scene.dim / 100, "--cam-time": `${scene.cameraTime}s`, animationDelay: moving ? `${delay}s` : undefined }} />
  );
}

function Weather({ w, calm }) {
  const list = particles(w.weather, w.intensity, calm);
  return (
    <div class={cx("cine-weather", `w-${w.weather}`, calm && "calm")} aria-hidden="true" data-testid="cine-weather" data-weather={w.weather}>
      {list.map((p) => <i key={p.i} style={{ left: `${p.x}%`, animationDelay: `${p.delay}s`, animationDuration: `${p.dur}s`, "--s": p.size, "--d": p.drift }} />)}
      {w.weather === "storm" && !calm && <b class="cine-lightning" />}
    </div>
  );
}

function TitleCard({ title }) {
  const { step, left } = title;
  return (
    <div class={cx("cine-title", `st-${step.style || "cinema"}`, left < 0.5 && "leaving")} data-testid="cine-title" style={step.color ? { "--title": step.color } : undefined}>
      <strong>{step.text}</strong>
      {step.subtitle && <span>{step.subtitle}</span>}
    </div>
  );
}

// The two sides of a dialogue: whoever talks comes forward and lights up, the other waits a little back and darker.
function Portraits({ stage }) {
  const one = (who, side) => who && (
    <div class={cx("cine-portrait", side, stage.active === side && "talking", stage.active && stage.active !== side && "waiting")} data-testid={`cine-portrait-${side}`}>
      {who.avatar ? <img src={cdn(who.avatar)} alt="" /> : <b style={who.color ? { background: who.color } : undefined}>{initial(who.speaker)}</b>}
      {who.speaker && <span class="cine-nameplate">{who.speaker}</span>}
    </div>
  );
  return <div class="cine-portraits" aria-hidden="true">{one(stage.left, "left")}{one(stage.right, "right")}</div>;
}
