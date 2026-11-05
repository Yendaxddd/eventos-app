// The arithmetic of the event's sound, without a browser: how loud something plays and where in a track a late arrival joins.
// (audio.js does the playing.)

const clamp01 = (v) => Math.min(1, Math.max(0, v));

// Loudness of a one-off sound: what the server says (0-100, already multiplied by the sound's own volume) × the player's effects volume.
export function effectGain(serverVolume, prefs) {
  if (!prefs.audio) return 0;
  return clamp01((serverVolume / 100) * (prefs.sfxVolume / 100));
}

// Loudness of the music: the game master's volume × the track's own × the player's music volume.
export function musicGain(music, prefs) {
  if (!music || !prefs.audio) return 0;
  const own = music.sound && Number.isFinite(music.sound.volume) ? music.sound.volume : 100;
  return clamp01((music.volume / 100) * (own / 100) * (prefs.musicVolume / 100));
}

// Where to start a track so a late arrival hears what the rest hear: seconds since the game master pressed play, as the server counts
// them (`now - startedAt`) plus the time the frame took to arrive and the time it has been here. A looping track wraps; a track that
// is not looping and has already ended gives null (there is nothing left to play).
export function musicOffset(music, { transitMs = 0, heldMs = 0, duration = null } = {}) {
  const elapsed = Math.max(0, (music.now - music.startedAt + transitMs + heldMs) / 1000);
  if (!duration || !Number.isFinite(duration) || duration <= 0) return music.loop ? elapsed : (elapsed < 1 ? elapsed : null);
  if (music.loop) return elapsed % duration;
  return elapsed < duration ? elapsed : null;
}

// A sound that arrives long after it was meant to play (a held-back tab, a locked page) is not worth playing any more.
export const STALE_MS = 4000;
export const isStale = (frame, serverNowMs) => Number.isFinite(frame.at) && serverNowMs - frame.at > STALE_MS;

// Which of the sounds the page should load before they are asked for (small ones: they play at once).
export const PRELOAD_BYTES = 3 * 1024 * 1024;
export const shouldPreload = (sound) => sound.kind !== "music" && sound.size <= PRELOAD_BYTES;
