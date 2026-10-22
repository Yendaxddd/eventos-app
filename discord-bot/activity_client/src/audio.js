// The event's sound in the browser: the sounds the game masters play or bind to what happens (a Black Flash, the boss falling...),
// and the music everybody hears together. The server decides what plays and when (see eventos_app/activity/audio.py); this only plays
// it, with the player's own volumes. Browsers refuse sound until the person touches the page: whatever arrives before is kept for a
// moment and played at the first touch (and the person is told to touch).
import { signal, effect } from "@preact/signals";
import { comp, link, prefs } from "./state.js";
import { base } from "./util.js";
import { getContext } from "./sound.js";
import { STALE_MS, effectGain, isStale, musicGain, musicOffset, shouldPreload } from "./audio-model.js";

export const sounds = signal([]);                // the library, as the server announces it
export const music = signal(null);               // what plays now: { sound, startedAt, volume, loop, now } or null
export const audioBlocked = signal(false);       // the browser has not allowed sound yet

const STREAM_BYTES = 12 * 1024 * 1024;           // bigger files are streamed instead of decoded whole (a decoded track takes ten times its size)
const FADE_MS = 1200;
const buffers = new Map();                       // file -> Promise<AudioBuffer | null>
const voices = new Set();                        // one-off sounds that are playing, to cut them all at once
let pending = [];                                // sounds that arrived while the browser would not play: { frame, at }
let track = null;                                // { el, music, arrival, timer }

const fileUrl = (sound) => `${base}/${sound.file}`;
const transit = () => (comp.value.net !== null && comp.value.net !== undefined ? comp.value.net : (link.value.median || 0) / 2);
const serverNow = () => Date.now() + (link.value.offset || 0);                      // the server's clock, as this page estimates it

// ---- decoding ---------------------------------------------------------------------------------------------------------
function decode(ctx, sound) {
  if (!buffers.has(sound.file)) {
    buffers.set(sound.file, fetch(fileUrl(sound)).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(String(r.status)))))
      .then((data) => ctx.decodeAudioData(data)).catch(() => null));
  }
  return buffers.get(sound.file);
}

export function preload(list) {
  const ctx = getContext();
  if (!ctx) return;
  const wanted = (list || []).filter(shouldPreload).slice(0, 60);
  let i = 0;
  const next = () => { if (i < wanted.length) decode(ctx, wanted[i++]).then(next); };      // one at a time: the connection is for the game first
  next();
  next();
}

// ---- one-off sounds ---------------------------------------------------------------------------------------------------
export async function playSound(frame) {
  const p = prefs.value;
  const gain = effectGain(frame.volume, p);
  if (gain <= 0 || !frame.sound) return false;
  const ctx = getContext();
  if (!ctx) return false;
  if (ctx.state !== "running") {
    pending = [...pending.filter((x) => performance.now() - x.at < STALE_MS), { frame, at: performance.now() }].slice(-6);
    audioBlocked.value = true;
    return false;
  }
  if (frame.sound.size > STREAM_BYTES) return stream(frame.sound, gain);
  const buffer = await decode(ctx, frame.sound);
  if (!buffer) return stream(frame.sound, gain);
  const source = ctx.createBufferSource();
  const amp = ctx.createGain();
  source.buffer = buffer;
  amp.gain.value = gain;
  source.connect(amp).connect(ctx.destination);
  const voice = { stop: () => { try { source.stop(); } catch { /* it had ended */ } } };
  voices.add(voice);
  source.onended = () => voices.delete(voice);
  source.start();
  return true;
}

function stream(sound, gain) {
  const el = new Audio(fileUrl(sound));
  el.volume = Math.min(1, gain);
  const voice = { stop: () => { el.pause(); } };
  voices.add(voice);
  el.onended = el.onerror = () => voices.delete(voice);
  return el.play().then(() => true, () => { voices.delete(voice); return false; });
}

export function stopSounds() {
  for (const voice of [...voices]) voice.stop();
  voices.clear();
}

// ---- music ------------------------------------------------------------------------------------------------------------------
function fade(holder, to, ms, then) {
  if (holder.timer) clearInterval(holder.timer);
  const el = holder.el, from = el.volume, start = performance.now();
  if (ms <= 0 || Math.abs(to - from) < 0.005) { el.volume = to; if (then) then(); return; }
  holder.timer = setInterval(() => {
    const k = Math.min(1, (performance.now() - start) / ms);
    el.volume = Math.min(1, Math.max(0, from + (to - from) * k));
    if (k >= 1) { clearInterval(holder.timer); holder.timer = null; if (then) then(); }
  }, 40);
}

function dispose(holder) {
  if (holder.timer) clearInterval(holder.timer);
  holder.el.pause();
  holder.el.removeAttribute("src");
  holder.el.load();
}

function play(holder) {
  const start = holder.el.play();
  if (start && start.catch) start.catch(() => { audioBlocked.value = true; });
}

function seek(holder) {
  const m = holder.music;
  const offset = musicOffset(m, { transitMs: transit(), heldMs: performance.now() - holder.arrival, duration: holder.el.duration });
  if (offset === null) { fade(holder, 0, 200, () => { if (track === holder) track = null; dispose(holder); }); return; }
  try { holder.el.currentTime = offset; } catch { /* not seekable yet: it plays from the start */ }
}

function startTrack(m, arrival) {
  const el = new Audio();
  el.preload = "auto";
  el.loop = !!m.loop;
  el.src = fileUrl(m.sound);
  el.volume = 0;
  const holder = { el, music: m, arrival, timer: null };
  el.addEventListener("loadedmetadata", () => seek(holder), { once: true });
  el.addEventListener("error", () => { if (track === holder) track = null; }, { once: true });
  const old = track;
  track = holder;
  if (old) fade(old, 0, FADE_MS, () => dispose(old));
  play(holder);
  fade(holder, musicGain(m, prefs.value), FADE_MS);
}

// `keep`: the same track with another volume, nothing restarts.
export function setMusic(m, { keep = false, arrival = performance.now() } = {}) {
  music.value = m;
  if (!m) {
    if (track) { const old = track; track = null; fade(old, 0, FADE_MS, () => dispose(old)); }
    return;
  }
  if (track && track.music.sound.id === m.sound.id && (keep || track.music.startedAt === m.startedAt)) {
    track.music = m;
    track.el.loop = !!m.loop;
    fade(track, musicGain(m, prefs.value), 300);
    return;
  }
  startTrack(m, arrival);
}

// What plays now, to put it back later (a cinematic that changed the music on this screen gives the event's music back when it ends).
export function musicSnapshot() {
  return { music: music.value, arrival: track ? track.arrival : performance.now() };
}
export function restoreMusic(snap) {
  if (!snap) return;
  if (!snap.music) { setMusic(null); return; }
  setMusic(snap.music, { arrival: snap.arrival });
}

// The player moved a volume or switched the event sound off: the music follows at once.
effect(() => {
  const p = prefs.value;
  const m = music.value;
  if (track && m) fade(track, musicGain(m, p), 150);
  if (!p.audio) { pending = []; stopSounds(); }
});

// ---- frames from the server ---------------------------------------------------------------------------------------------
export function onAudioFrame(frame, arrival = performance.now()) {
  switch (frame.op) {
    case "play":
      if (!isStale(frame, serverNow())) playSound(frame);
      break;
    case "stop": stopSounds(); break;
    case "music": setMusic(frame.music, { keep: !!frame.keep, arrival }); break;
    case "library": sounds.value = frame.sounds || []; preload(sounds.value); break;
    default: break;
  }
}

export function onWelcomeAudio(info, arrival = performance.now()) {
  if (!info) return;
  sounds.value = info.library || [];
  preload(sounds.value);
  setMusic(info.music || null, { arrival });
}

// ---- the first touch --------------------------------------------------------------------------------------------------------
function unlock() {
  const ctx = getContext();
  if (!ctx) return;
  const resumed = ctx.state === "running" ? Promise.resolve() : ctx.resume();
  resumed.then(() => {
    if (ctx.state !== "running") return;
    audioBlocked.value = false;
    const now = performance.now();
    const queued = pending.filter((x) => now - x.at < STALE_MS);
    pending = [];
    for (const { frame } of queued) playSound(frame);
    if (track) {                                     // the music went on without us: it joins at the second everybody else is at
      if (track.el.readyState >= 1) seek(track);
      if (track) play(track);
    }
  }).catch(() => {});
}
if (typeof document !== "undefined") {
  document.addEventListener("pointerdown", unlock, { passive: true });
  document.addEventListener("keydown", unlock);
}

// For the game masters' «probar»: the sound as it would play, only here.
export const playLocal = (sound, volume = 100) => playSound({ sound, volume: Math.round(volume * sound.volume / 100) });
