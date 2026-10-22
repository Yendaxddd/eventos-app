// The cinematic that is playing on this screen. The server starts one for everybody (`cine` frames) and each screen plays it by its own clock,
// counted from when the server started it (see cinema-model.js). Nothing here touches the DOM: CinemaLayer draws it.
import { signal } from "@preact/signals";
import { comp, link, prefs } from "./state.js";

export const cine = signal(null);        // { run: { id, cinema, startedAt, now }, arrival, preview } or null

const transit = () => (comp.value.net !== null && comp.value.net !== undefined ? comp.value.net : (link.value.median || 0) / 2);

export function startCine(run, { arrival = performance.now(), preview = false } = {}) {
  if (!run || !run.cinema) { cine.value = null; return; }
  // cinematics switched off: nothing is drawn, but its sounds and music still play (they are part of the event)
  const hidden = !prefs.value.cinema && !preview;
  cine.value = { run, arrival, preview, hidden, transitMs: preview ? 0 : transit(), skipped: false };
}

export function stopCine() { cine.value = null; }

export function onCineFrame(frame, arrival = performance.now()) {
  if (frame.op === "start") startCine(frame.run, { arrival });
  else if (frame.op === "stop") stopCine();
}

// For the editor: play a script that is not saved, only here (from second `from`, to see one part without waiting).
let previews = 0;
export function previewCine(cinema, from = 0) {
  const now = Date.now();
  startCine({ id: `preview-${++previews}`, cinema, startedAt: now - Math.max(0, from) * 1000, now }, { preview: true });
}
