// A cinematic as the screen plays it: what is showing at a second of its timeline. Pure functions (no DOM, no clock), so they can be tested.
// The server keeps and checks the scripts (eventos_app/activity/cinema.py); a script arrives here with its steps in time order.

export const TYPE_SPEED = 32;                      // characters per second while a caption is being typed

export const stepEnd = (step) => step.at + (step.duration || 0);

export function durationOf(steps) {
  return Math.round((steps.reduce((end, s) => Math.max(end, stepEnd(s)), 0) + 1) * 100) / 100;
}

// The background from the latest «scene» step on: { color, image, dim (0–100) }.
export function sceneAt(cinema, t) {
  let scene = { color: cinema.bg || "#000000", image: null, dim: 0 };
  for (const s of cinema.steps) if (s.type === "scene" && s.at <= t) scene = { color: s.color || scene.color, image: s.image || null, dim: s.dim ?? 40 };
  return scene;
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
export const STEP_LABELS = { text: "Texto", audio: "Sonido", image: "Imagen", scene: "Escena", effect: "Efecto", post: "Mensaje al canal" };

// A fresh step for the editor, placed after the last one.
export function newStep(type, steps) {
  const at = steps.length ? Math.round(Math.max(...steps.map(stepEnd)) * 10) / 10 : 0;
  switch (type) {
    case "text": return { type, at, speaker: "", text: "", duration: 4, effect: "type", color: "", size: "normal", avatar: "" };
    case "audio": return { type, at, mode: "play", sound: "", volume: 100 };
    case "image": return { type, at, image: "", duration: 4, position: "center" };
    case "scene": return { type, at, color: "#000000", image: "", dim: 40 };
    case "effect": return { type, at, effect: "flash", color: "#ffffff", duration: 0.6 };
    default: return { type: "post", at, text: "" };
  }
}
