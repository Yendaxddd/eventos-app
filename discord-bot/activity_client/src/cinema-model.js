// A cinematic as the screen plays it: what is showing at a second of its timeline. Pure functions (no DOM, no clock), so they can be tested.
// The server keeps and checks the scripts (eventos_app/activity/cinema.py); a script arrives here with its steps in time order.

export const TYPE_SPEED = 32;                      // characters per second while a caption is being typed

export const stepEnd = (step) => step.at + (step.duration || 0);

export function durationOf(steps) {
  return Math.round((steps.reduce((end, s) => Math.max(end, stepEnd(s)), 0) + 1) * 100) / 100;
}

// The background from the latest «scene» step on: { color, image, dim (0–100), camera, cameraTime, transition, at, prev }. `prev` is the
// scene before it while a «fade» transition is still blending them (the first second), so the screen can cross-fade.
export function sceneAt(cinema, t) {
  let scene = { color: cinema.see ? "transparent" : cinema.bg || "#000000", image: null, dim: 0, camera: "none", cameraTime: 12, transition: "cut", at: 0, prev: null };
  for (const s of cinema.steps) {
    if (s.type !== "scene" || s.at > t) continue;
    const before = { ...scene, prev: null };
    scene = { color: s.color || scene.color, image: s.image || null, dim: s.dim ?? 40, camera: s.camera || "none", cameraTime: s.camera_time || 12,
      transition: s.transition || "fade", at: s.at, prev: before };
  }
  if (scene.prev && !(scene.transition === "fade" && t - scene.at < 1)) scene.prev = null;
  return scene;
}

// ---- screen effects -------------------------------------------------------------------------------------------------------
// An effect rises quickly, holds and fades: its strength at a point of its life (0..1). A flash is all at once and then fades.
export function envelope(effect, p) {
  if (p <= 0 || p >= 1) return 0;
  if (effect === "flash") return 1 - p;
  if (effect === "pulse") return Math.sin(p * Math.PI * 4) ** 2 * (1 - p * 0.5);
  const rise = 0.15, fall = 0.25;
  return p < rise ? p / rise : p > 1 - fall ? (1 - p) / fall : 1;
}

// The effect steps running at `t`, each with how far it has got (p) and its strength now (k, 0..1, its intensity already in).
export function effectsAt(cinema, t) {
  const out = [];
  for (const s of cinema.steps) {
    if (s.type !== "effect" || s.at > t || t >= stepEnd(s)) continue;
    const p = (t - s.at) / Math.max(0.05, s.duration || 0.6);
    out.push({ step: s, p, k: envelope(s.effect, p) * ((s.intensity ?? 60) / 100) });
  }
  return out;
}

// What the effects do to the picture right now: a CSS filter, a transform, and the layers drawn over it ({ kind, color, opacity }).
// `calm` (the player asked for less motion): nothing moves or flickers, colours and fades still happen.
export function screenLook(effects, t, calm = false) {
  const filter = [], transform = [], layers = [];
  for (const { step, k } of effects) {
    if (k <= 0.001) continue;
    switch (step.effect) {
      case "blur": filter.push(`blur(${(k * 12).toFixed(1)}px)`); break;
      case "grayscale": filter.push(`grayscale(${k.toFixed(2)})`); break;
      case "sepia": filter.push(`sepia(${k.toFixed(2)})`); break;
      case "invert": filter.push(`invert(${k.toFixed(2)})`); break;
      case "chromatic": if (!calm) filter.push(`drop-shadow(${(k * 6).toFixed(1)}px 0 rgb(255 0 60 / .7)) drop-shadow(${(-k * 6).toFixed(1)}px 0 rgb(0 220 255 / .7))`); break;
      case "zoom": if (!calm) transform.push(`scale(${(1 + k * 0.3).toFixed(3)})`); break;
      case "shake": if (!calm) { const a = k * 18; transform.push(`translate(${(Math.sin(t * 91) * a).toFixed(1)}px, ${(Math.cos(t * 77) * a * 0.7).toFixed(1)}px)`); } break;
      case "glitch": if (!calm && Math.sin(t * 53) > 0.2) { transform.push(`translateX(${(Math.sin(t * 211) * k * 24).toFixed(1)}px) skewX(${(Math.sin(t * 97) * k * 8).toFixed(1)}deg)`); filter.push(`hue-rotate(${Math.round(Math.sin(t * 31) * 90 * k)}deg)`); } break;
      case "pulse": layers.push({ kind: "tint", color: step.color || "#ff0000", opacity: k * 0.45 }); break;
      case "tint": layers.push({ kind: "tint", color: step.color || "#ff0000", opacity: k * 0.55 }); break;
      case "vignette": layers.push({ kind: "vignette", color: step.color || "#000000", opacity: k }); break;
      case "blackout": layers.push({ kind: "fill", color: step.color && step.color !== "#ffffff" ? step.color : "#000000", opacity: k }); break;
      case "whiteout": layers.push({ kind: "fill", color: step.color || "#ffffff", opacity: k }); break;
      default: if (!calm) layers.push({ kind: "fill", color: step.color || "#ffffff", opacity: k * 0.9 });         // flash
    }
  }
  return { filter: filter.join(" "), transform: transform.join(" "), layers };
}

// ---- weather, titles and the two sides of a dialogue ---------------------------------------------------------------------------
export function weatherAt(cinema, t) {
  let found = null;
  for (const s of cinema.steps) if (s.type === "weather" && s.at <= t) found = s;
  return found && found.weather !== "none" ? { weather: found.weather, intensity: found.intensity ?? 60, at: found.at } : null;
}

export function titleAt(cinema, t) {
  let found = null;
  for (const s of cinema.steps) if (s.type === "title" && s.at <= t && t < stepEnd(s)) found = s;
  return found ? { step: found, local: t - found.at, left: stepEnd(found) - t } : null;
}

// The particles of a weather (where each starts, how long it takes to cross, how big): always the same for the same weather and
// strength, so the screen does not reshuffle them on every redraw.
export function particles(weather, intensity = 60, calm = false) {
  const many = { rain: 70, storm: 90, snow: 46, embers: 34, fog: 6, petals: 22, sparks: 30, stars: 40, ash: 30 }[weather] || 30;
  const n = Math.max(weather === "fog" ? 3 : 4, Math.round(many * (intensity / 100) * (calm ? 0.35 : 1)));
  let seed = 7;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
  return Array.from({ length: n }, (_, i) => ({ i, x: rnd() * 100, delay: -rnd() * 10, dur: 0.6 + rnd() * (weather === "rain" || weather === "storm" ? 0.6 : weather === "fog" ? 20 : 8), size: 0.5 + rnd(), drift: rnd() * 2 - 1 }));
}

const SIDE_GAP = 3;          // seconds without a line before the portraits of a dialogue leave

// A dialogue between characters: who stands on the left and on the right, and who is talking. Lines with a side (left/right) make up a
// dialogue; its portraits stay from its first line until a moment after its last one (or a new scene).
export function stageAt(cinema, t) {
  let left = null, right = null, lastEnd = -Infinity, sceneAtT = 0, start = null;
  for (const s of cinema.steps) if (s.type === "scene" && s.at <= t) sceneAtT = s.at;
  for (const s of cinema.steps) {
    if (s.type !== "text" || (s.side !== "left" && s.side !== "right") || s.at < sceneAtT) continue;
    if (s.at > t) {
      if (s.at - lastEnd < SIDE_GAP && start !== null) lastEnd = Math.max(lastEnd, t);       // the dialogue goes on: keep the portraits between lines
      break;
    }
    if (s.at - lastEnd >= SIDE_GAP) { left = null; right = null; start = s.at; }
    const who = { speaker: s.speaker || "", avatar: s.avatar || null, color: s.color || null };
    if (s.side === "left") left = who; else right = who;
    lastEnd = Math.max(lastEnd, stepEnd(s));
  }
  if (start === null || t > lastEnd + 0.8) return null;
  const now = captionAt(cinema, t);
  const active = now && (now.step.side === "left" || now.step.side === "right") ? now.step.side : null;
  return { left, right, active };
}

// The caption on screen: the latest text step that has started and not ended, how far it has got and how many characters are typed.
export function captionAt(cinema, t) {
  let found = null;
  for (const s of cinema.steps) if (s.type === "text" && s.at <= t && t < stepEnd(s)) found = s;
  if (!found) return null;
  const local = t - found.at;
  const typing = found.effect === "type";
  const shown = typing ? Math.min(found.text.length, Math.floor(local * TYPE_SPEED)) : found.text.length;
  return { step: found, local, shown, typing, left: stepEnd(found) - t };
}

// The picture on screen (the latest image step that is still running).
export function imageAt(cinema, t) {
  let found = null;
  for (const s of cinema.steps) if (s.type === "image" && s.at <= t && t < stepEnd(s)) found = s;
  return found ? { step: found, local: t - found.at, left: stepEnd(found) - t } : null;
}

// The one-off steps whose moment came between two readings of the clock (from, to]: sounds and effects start once.
export function crossed(cinema, from, to, types = ["audio", "effect"]) {
  return cinema.steps.filter((s) => types.includes(s.type) && s.at > from && s.at <= to);
}

// Somebody who joins a cinematic late (or a tab that was held back): the music state it should be in, from the last music step before `t`.
export function musicStepBefore(cinema, t) {
  let found = null;
  for (const s of cinema.steps) if (s.type === "audio" && (s.mode === "music" || s.mode === "stop_music") && s.at <= t) found = s;
  return found;
}

// Seconds into the cinematic, from how long ago the server started it and when its frame reached this page.
export function elapsedSeconds(run, { arrival, now, transitMs = 0 }) {
  return Math.max(0, (run.now - run.startedAt + transitMs + (now - arrival)) / 1000);
}

export const isOver = (cinema, t) => t >= cinema.duration;

// The Spanish name of each kind of step, for the editor.
export const STEP_LABELS = { text: "Texto", title: "Título", audio: "Sonido", image: "Imagen", scene: "Escena", weather: "Clima", effect: "Efecto de pantalla", vfx: "Efecto visual", post: "Mensaje al canal" };

// A fresh step for the editor, placed after the last one.
export function newStep(type, steps) {
  const at = steps.length ? Math.round(Math.max(...steps.map(stepEnd)) * 10) / 10 : 0;
  switch (type) {
    case "text": return { type, at, speaker: "", text: "", duration: 4, effect: "type", color: "", size: "normal", avatar: "", side: "bottom" };
    case "title": return { type, at, text: "", subtitle: "", style: "cinema", color: "", duration: 3.5 };
    case "audio": return { type, at, mode: "play", sound: "", volume: 100 };
    case "image": return { type, at, image: "", duration: 4, position: "center", enter: "pop", size: "medium", camera: "none" };
    case "scene": return { type, at, color: "#000000", image: "", dim: 40, camera: "none", camera_time: 12, transition: "fade" };
    case "weather": return { type, at, weather: "rain", intensity: 60 };
    case "effect": return { type, at, effect: "flash", color: "#ffffff", duration: 0.6, intensity: 60 };
    case "vfx": return { type, at, preset: "explosion", color: "", intensity: 100, speed: 100, banner: "", duration: 1.5 };
    default: return { type: "post", at, text: "" };
  }
}

// ---- the editor ----------------------------------------------------------------------------------------------------------
// The timeline's rows: what each kind of step sits on.
export const LANES = [["text", "Texto y títulos", ["text", "title"]], ["sound", "Sonido", ["audio"]], ["picture", "Imagen, escena y clima", ["image", "scene", "weather"]], ["fx", "Efectos", ["effect", "vfx"]], ["post", "Canal", ["post"]]];
export const laneOf = (type) => (LANES.find((l) => l[2].includes(type)) || LANES[0])[0];

const num = (v, fallback = 0) => { const n = Number(v); return Number.isFinite(n) ? n : fallback; };
export const orderOf = (steps) => steps.map((s, i) => [s, i]).sort((a, b) => num(a[0].at) - num(b[0].at) || a[1] - b[1]).map((x) => x[0]);

// Why a draft cannot be saved yet ("" when it can): the same things the server refuses, said before it is asked, naming the step as the editor numbers it.
export function validate(draft) {
  if (!String(draft.name || "").trim()) return "Ponle un nombre a la cinemática para que se guarde.";
  if (!draft.steps.length) return "Añade al menos un paso.";
  const steps = orderOf(draft.steps);
  for (let i = 0; i < steps.length; i++) {
    const s = steps[i], where = `Paso ${i + 1} (${STEP_LABELS[s.type]}, ${num(s.at)} s)`;
    if (!Number.isFinite(Number(s.at)) || Number(s.at) < 0) return `${where}: el momento debe ser un número de segundos.`;
    if (s.type === "text" && !String(s.text || "").trim()) return `${where}: escribe el texto.`;
    if (s.type === "audio" && s.mode !== "stop_music" && !s.sound) return `${where}: elige un sonido.`;
    if (s.type === "image" && !s.image) return `${where}: elige una imagen.`;
    if (s.type === "post" && !String(s.text || "").trim()) return `${where}: escribe el mensaje.`;
    if (s.type === "title" && !String(s.text || "").trim()) return `${where}: escribe el título.`;
  }
  return "";
}

// A step dragged on the timeline: where it lands, in seconds (snapped, never before 0 nor past the end of the timeline).
export function draggedTo(at, dxPixels, lanePixels, totalSeconds, snap = 0.1) {
  if (!(lanePixels > 0)) return at;
  const moved = Math.max(0, Math.min(totalSeconds, at + (dxPixels / lanePixels) * totalSeconds));
  return Math.round(Math.round(moved / snap) * snap * 100) / 100;
}

// The marks of the ruler: about eight, at a round number of seconds.
export function rulerTicks(totalSeconds) {
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300];
  const every = steps.find((s) => totalSeconds / s <= 9) || 600;
  const out = [];
  for (let t = 0; t <= totalSeconds + 1e-9; t += every) out.push(t);
  return out;
}

// ---- templates: a starting point for the usual scenes, with the steps already in place -----------------------------------------
// Each one gives its steps from second `at` on; the editor adds them where the cursor is, and the creator changes the words and pictures.
export const TEMPLATES = [
  { id: "dialogue", name: "Diálogo entre dos", hint: "Dos personajes, uno a cada lado, hablando por turnos",
    steps: (at) => [
      { type: "text", at, side: "left", speaker: "Personaje A", text: "¿Así que has vuelto?", duration: 3, effect: "type" },
      { type: "text", at: at + 3.2, side: "right", speaker: "Personaje B", text: "Nunca me fui.", duration: 3, effect: "type" },
      { type: "text", at: at + 6.4, side: "left", speaker: "Personaje A", text: "Entonces termina lo que empezaste.", duration: 3.5, effect: "type" },
    ] },
  { id: "boss", name: "Entrada del jefe", hint: "Temblor, destello, título y una frase",
    steps: (at) => [
      { type: "effect", at, effect: "vignette", color: "#000000", duration: 7, intensity: 80 },
      { type: "effect", at: at + 0.4, effect: "shake", duration: 1.6, intensity: 70 },
      { type: "effect", at: at + 2, effect: "flash", color: "#ffffff", duration: 0.5, intensity: 90 },
      { type: "title", at: at + 2.1, text: "EL REY CAÍDO", subtitle: "Señor de la ceniza", style: "impact", duration: 3 },
      { type: "text", at: at + 5.2, speaker: "Jefe", text: "Arrodillaos.", duration: 2.5, effect: "shake", size: "big" },
    ] },
  { id: "chapter", name: "Capítulo", hint: "Fundido a negro y un título de capítulo",
    steps: (at) => [
      { type: "effect", at, effect: "blackout", duration: 5, intensity: 100 },
      { type: "title", at: at + 0.6, text: "Capítulo I", subtitle: "El comienzo", style: "chapter", duration: 3.8 },
    ] },
  { id: "flashback", name: "Recuerdo", hint: "Sepia, desenfoque suave y un narrador",
    steps: (at) => [
      { type: "effect", at, effect: "sepia", duration: 8, intensity: 90 },
      { type: "effect", at, effect: "vignette", duration: 8, intensity: 60 },
      { type: "effect", at, effect: "blur", duration: 1.2, intensity: 50 },
      { type: "text", at: at + 1, text: "Hace muchos años…", duration: 4, effect: "fade" },
    ] },
  { id: "victory", name: "Victoria", hint: "Destello dorado, chispas y un título",
    steps: (at) => [
      { type: "effect", at, effect: "flash", color: "#fde68a", duration: 0.7, intensity: 90 },
      { type: "weather", at, weather: "sparks", intensity: 70 },
      { type: "title", at: at + 0.3, text: "¡VICTORIA!", subtitle: "", style: "impact", color: "#fde68a", duration: 4 },
      { type: "weather", at: at + 5, weather: "none", intensity: 0 },
    ] },
  { id: "storm", name: "Tormenta", hint: "Lluvia, relámpagos y oscuridad",
    steps: (at) => [
      { type: "weather", at, weather: "storm", intensity: 80 },
      { type: "effect", at: at + 1.5, effect: "flash", color: "#e0f2fe", duration: 0.35, intensity: 80 },
      { type: "effect", at: at + 1.6, effect: "shake", duration: 0.6, intensity: 30 },
      { type: "effect", at: at + 4.2, effect: "flash", color: "#e0f2fe", duration: 0.3, intensity: 70 },
    ] },
  { id: "place", name: "Lugar", hint: "Un rótulo de lugar sobre un fondo con cámara lenta",
    steps: (at) => [
      { type: "scene", at, color: "#0b1020", image: "", dim: 30, camera: "drift", camera_time: 14, transition: "fade" },
      { type: "title", at: at + 0.8, text: "Ruinas de Velkar", subtitle: "Frontera norte", style: "location", duration: 4 },
    ] },
];

// The steps of a template, from second `at`.
export function templateSteps(id, at = 0) {
  const tpl = TEMPLATES.find((x) => x.id === id);
  return tpl ? tpl.steps(Math.round(Math.max(0, at) * 10) / 10).map((s) => ({ ...newStep(s.type, []), ...s })) : [];
}

// Steps copied to be pasted elsewhere (in this cinematic or another): they keep their spacing, the first one lands on `at`.
export function pasteAt(copied, at) {
  if (!copied || !copied.length) return [];
  const first = Math.min(...copied.map((s) => num(s.at)));
  return copied.map((s) => ({ ...s, at: Math.round((num(s.at) - first + Math.max(0, num(at))) * 100) / 100 }));
}
