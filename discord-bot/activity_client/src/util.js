// Small helpers shared by the whole client.
export const params = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
export const inDiscord = params.has("frame_id");          // Discord adds frame_id when it loads the Activity
export const devName = params.get("dev");                  // ?dev=Ana: a test window opened from this very PC (no Discord)
export const devGm = params.get("gm") === "1";             // ...and ?gm=1 asks for the game-master panel in that test window
export const devHost = params.get("host") === "1";         // ...and ?host=1 says it is the host's own window (the desktop app): not listed among the players
export const base = inDiscord ? "/.proxy" : "";            // Discord forwards /.proxy/* to the mapped server

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export const cx = (...parts) => parts.filter(Boolean).join(" ");
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function median(values) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// Discord's own pictures come through the app's server (/media), so the Developer Portal needs no extra URL Mappings.
export const MEDIA_HOST = /^https:\/\/(cdn\.discordapp\.com|media\.discordapp\.net|images-ext-\d+\.discordapp\.net)\//;
export function cdn(url) {
  return url && MEDIA_HOST.test(url) ? `${base}/media?u=${encodeURIComponent(url)}` : url;
}

// A colour per name, so people without a picture still look different from each other.
export const hueOf = (name) => [...(name || "?")].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
export const initial = (name) => (Array.from(String(name || "?").trim())[0] || "?").toUpperCase();   // Array.from: names in maths letters are surrogate pairs

export const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* private window: it is only a convenience */ } },
  json(key, fallback) { try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; } },
};

export const timeLabel = (ts) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
export const secondsText = (ms, digits = 1) => (Math.max(0, ms) / 1000).toFixed(digits);

// "hace 3 min" style, for things that happened a while ago
export function ago(ts, now = Date.now()) {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 5) return "ahora";
  if (s < 60) return `hace ${s} s`;
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return `hace ${Math.round(s / 86400)} d`;
}

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}
