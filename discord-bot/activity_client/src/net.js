// The connection to the app: sign in (through Discord when we are inside it), open the WebSocket, keep clocks and
// settings in step, and turn every frame into changes of the client's state.
import { batch } from "@preact/signals";
import { initSdk, afterAuth, sdk } from "./discord.js";
import { inDiscord, devName, devGm, devHost, base, store } from "./util.js";
import { SyncEstimator, qualityOf } from "./clock.js";
import {
  conn, banner, you, perms, channelName, users, canWrite, version, messages, game, me, characters, charAvatars, activeAs,
  rules, link, comp, calib, prefs, toast, flash, myHp, sayRefused,
} from "./state.js";
import { DEFAULT_PREFS, sanitizePrefs, saveLocalPrefs } from "./prefs.js";
import { flushPrefs } from "./settings-actions.js";
import {
  bindSender, startQte, endQte, clearQtes, onResult, onStep, onPressError, netMs,
} from "./qte-store.js";
import { clearPanelCache } from "./panel/cache.js";
import { describeNotice } from "./notices.js";
import { onAudioFrame, onWelcomeAudio } from "./audio.js";
import { onCineFrame, startCine, stopCine } from "./cine.js";
import { playBinding } from "./vfx.js";
import { onMobHit, setMobs } from "./mobs.js";

function showNotice(kind, data) {
  const notice = describeNotice(kind, data);
  if (notice) toast(notice.text, notice.tone === "bf" ? "ok" : notice.tone, notice.tone === "bf" ? 4200 : 3600);
}

// ---- telling the app how far we got ---------------------------------------------------------------------------
// A blank Activity is hard to diagnose from the outside, so the page reports its progress and its errors to the app
// (which prints them in its log).
const reported = new Set();
let errorsReported = 0;
export function report(stage, detail = "") {
  if (stage === "error" ? errorsReported++ >= 5 : reported.has(stage)) return;
  reported.add(stage);
  try {
    fetch(`${base}/api/report`, {
      method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
      body: JSON.stringify({ stage, detail: String(detail).slice(0, 300) }),
    }).catch(() => {});
  } catch { /* reporting is a courtesy */ }
}
window.addEventListener("error", (e) => report("error", `${e.message} (${(e.filename || "").split("/").pop()}:${e.lineno})`));
window.addEventListener("unhandledrejection", (e) => report("error", (e.reason && e.reason.message) || e.reason));

// ---- socket -----------------------------------------------------------------------------------------------------
let ws = null;
let retry = 0;
let welcomed = false;
let everWelcomed = false;                // after the first welcome, a reconnection keeps the screen as it is (with a banner)
let hello = null;
export const sync = new SyncEstimator();
let burstTimer = null, keepTimer = null;

export function send(frame) {
  if (ws && ws.readyState === WebSocket.OPEN) { ws.send(JSON.stringify(frame)); return true; }
  return false;
}
bindSender(send);

// A picture chosen on the device goes up over plain HTTP (the socket carries small frames only). The server checks it is
// a real picture, keeps it on Discord and answers its address.
let accessToken = null;
export async function uploadImage(file) {
  const headers = { "Content-Type": file.type || "application/octet-stream", "X-Filename": encodeURIComponent(file.name || "imagen") };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  else if (devName) headers["X-Dev"] = devName;
  let reply;
  try { reply = await fetch(`${base}/api/upload`, { method: "POST", headers, body: file }); }
  catch { throw new Error("No se pudo enviar la imagen. Revisa tu conexión."); }
  let data = {};
  try { data = await reply.json(); } catch { /* the answer was not JSON */ }
  if (!reply.ok) throw new Error(data.error || "No se pudo subir la imagen.");
  return data.url;
}

// A picture for a cinematic (game masters only): it stays on the host's PC and the answer is its path («files/images/…»).
export async function uploadCinemaImage(file) {
  const headers = { "Content-Type": file.type || "application/octet-stream", "X-Filename": encodeURIComponent(file.name || "imagen") };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  else if (devName) { headers["X-Dev"] = devName; if (devGm) headers["X-Gm"] = "1"; }
  let reply;
  try { reply = await fetch(`${base}/api/image`, { method: "POST", headers, body: file }); }
  catch { throw new Error("No se pudo enviar la imagen. Revisa tu conexión."); }
  let data = {};
  try { data = await reply.json(); } catch { /* the answer was not JSON */ }
  if (!reply.ok) throw new Error(data.error || "No se pudo subir la imagen.");
  return data.path;
}

// A sound for the library (game masters only; the server checks the role again). `onProgress` gets 0–1 while it goes up.
export function uploadAudio(file, kind, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${base}/api/audio`);
    xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name || "sonido"));
    xhr.setRequestHeader("X-Kind", kind || "");
    if (accessToken) xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
    else if (devName) { xhr.setRequestHeader("X-Dev", devName); if (devGm) xhr.setRequestHeader("X-Gm", "1"); }
    if (onProgress) xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onerror = () => reject(new Error("No se pudo enviar el archivo. Revisa tu conexión."));
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* the answer was not JSON */ }
      if (xhr.status === 200 && data.sound) resolve(data.sound); else reject(new Error(data.error || "No se pudo subir el sonido."));
    };
    xhr.send(file);
  });
}

// request/answer over the socket (profile data, GM actions...)
const pending = new Map();
let rpcCount = 0;
export function rpc(op, args = {}, timeout = 12000) {
  return new Promise((resolve, reject) => {
    const id = `r${++rpcCount}`;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error("El servidor tardó demasiado en responder.")); }, timeout);
    pending.set(id, { resolve, reject, timer });
    if (!send({ t: "rpc", id, op, args })) {
      clearTimeout(timer); pending.delete(id); reject(new Error("Sin conexión con el evento."));
    }
  });
}

// ---- clock + round trips -----------------------------------------------------------------------------------------
export const pongListeners = new Set();            // the latency test listens to every pong, to keep each sample
function onPong(frame) {
  const rtt = performance.now() - frame.c;
  pongListeners.forEach((fn) => fn(frame.c, rtt));
  sync.add(rtt, frame.s + rtt / 2 - Date.now());
  const median = sync.median;
  link.value = { min: sync.min, median, jitter: sync.jitter, offset: sync.offset, quality: qualityOf(median), samples: sync.count };
  send({ t: "sync", rtt: sync.min, rttMedian: median, jitter: sync.jitter, offset: sync.offset });
}
export const ping = () => { const c = performance.now(); return send({ t: "ping", c }) ? c : null; };

function startSync() {
  clearInterval(burstTimer); clearInterval(keepTimer);          // a reconnect must not stack timers
  let burst = 0;
  burstTimer = setInterval(() => {
    ping();
    if (++burst >= 8) { clearInterval(burstTimer); keepTimer = setInterval(ping, 8000); }
  }, 120);
}

// ---- turning the server's `me` into local times ----------------------------------------------------------------------
function localMe(frame, arrival) {
  const raw = frame.me || {};
  if (!raw.charges) return null;
  const now = frame.now ?? frame.serverTime ?? Date.now() + link.value.offset;
  const net = netMs();
  const at = (until) => (until ? arrival + (until - now) - net : null);
  const powers = {};
  for (const [name, slots] of Object.entries(raw.powers || {})) {
    powers[name] = {};
    for (const [slot, info] of Object.entries(slots)) powers[name][slot] = { ...info, at: at(info.until) };
  }
  return {
    ...raw, powers,
    parryAt: at(raw.parryUntil), counterAt: at(raw.counterUntil),
    saves: raw.saves ? { ...raw.saves, at: at(raw.saves.until) } : null,
  };
}

// ---- frames ------------------------------------------------------------------------------------------------------------
function setPrefsFromServer(next) {
  const clean = sanitizePrefs(next);
  prefs.value = clean;
  saveLocalPrefs(clean);
}

function trimMessages(list) {
  const cap = prefs.value.messageLimit || 150;
  return list.length > cap ? list.slice(list.length - cap) : list;
}

function onFrame(frame, arrival) {
  switch (frame.t) {
    case "welcome": {
      report("conectado");
      welcomed = true; everWelcomed = true; retry = 0; sync.samples.length = 0;
      clearPanelCache();                                    // what the dashboards remembered may be from before a reconnect
      batch(() => {
        conn.value = { state: "connected", text: "Conectado", detail: "" };
        banner.value = null;
        you.value = frame.you;
        perms.value = frame.perms || { gm: false };
        channelName.value = frame.channel || "Evento";
        users.value = frame.users || [];
        canWrite.value = !!frame.canWrite;
        version.value = frame.version || "";
        characters.value = frame.characters || [];
        charAvatars.value = frame.charAvatars || {};
        if (activeAs.value !== "me" && !(frame.characters || []).includes(activeAs.value)) activeAs.value = "me";
        const saved = store.get("eventos.as");
        if (saved && (frame.characters || []).includes(saved)) activeAs.value = saved;
        rules.value = frame.rules || null;
        onWelcomeAudio(frame.audio, arrival);
        if (frame.cine) startCine(frame.cine, { arrival }); else stopCine();
        setMobs(frame.mobs, arrival);
        comp.value = { ...comp.value, ...(frame.comp || {}) };
        calib.value = frame.calib || null;
        if (flushPrefs()) { /* this device changed settings while offline: they win over the server's copy */ }
        else if (frame.prefs) setPrefsFromServer(frame.prefs);
        else if (frame.prefs === null && JSON.stringify(prefs.value) !== JSON.stringify(DEFAULT_PREFS)) send({ t: "prefs", prefs: prefs.value });   // the server knows nothing about this person yet: it learns from this device
        messages.value = trimMessages(frame.backlog || []);
        game.value = frame.state && frame.state.players ? frame.state : null;
        me.value = localMe(frame, arrival);
        clearQtes();
      });
      for (const running of frame.qtes || []) startQte(running, { ago: Math.max(0, (frame.serverTime - running.tGo) / 1000) });   // QTEs already running when we came in
      startSync();
      break;
    }
    case "users": users.value = frame.users || []; break;
    case "chars":                                           // the player registered or dropped a character (maybe from another screen)
      batch(() => {
        characters.value = frame.characters || [];
        charAvatars.value = frame.charAvatars || {};
        if (activeAs.value !== "me" && !characters.value.includes(activeAs.value)) activeAs.value = "me";
      });
      break;
    case "reset":
      batch(() => { channelName.value = frame.channel || "Evento"; messages.value = trimMessages(frame.backlog || []); });
      break;
    case "msg": {
      const list = messages.value;
      messages.value = trimMessages(list.some((m) => m.id === frame.m.id) ? list.map((m) => (m.id === frame.m.id ? frame.m : m)) : [...list, frame.m]);
      break;
    }
    case "edit": messages.value = messages.value.map((m) => (m.id === frame.m.id ? frame.m : m)); break;
    case "del": messages.value = messages.value.filter((m) => m.id !== frame.id); break;
    case "state": {
      const before = myHp.value;
      game.value = frame.s;
      const after = myHp.value;
      if (before && after && after.hp < before.hp) flash("hit");
      else if (before && after && after.hp > before.hp) flash("heal");
      break;
    }
    case "me": me.value = localMe(frame, arrival); break;
    case "qte": startQte(frame.q, { ago: frame.now ? Math.max(0, (frame.now - frame.q.tGo) / 1000) : 0 }); break;
    case "qte_end": endQte(frame.id); break;
    case "qte_result": onResult(frame); break;
    case "qte_step": onStep(frame); break;
    case "pong": onPong(frame); break;
    case "sp": send({ t: "sq", n: frame.n }); break;                       // the server measures our round trip too
    case "comp": comp.value = { ...comp.value, ...frame.comp }; break;
    case "prefs": setPrefsFromServer(frame.prefs); break;
    case "calib": calib.value = frame.calib || null; break;
    case "toast": toast(frame.text, frame.kind || "info"); break;
    case "notice": showNotice(frame.kind, frame.data); break;
    case "audio": onAudioFrame(frame, arrival); break;
    case "cine": onCineFrame(frame, arrival); break;
    case "fx": playBinding(frame.fx, frame.ctx || {}); break;
    case "mobs": setMobs(frame, arrival); break;
    case "mob_hit": onMobHit(frame); break;
    case "slow": toast("Vas demasiado rápido: espera un momento.", "warn", 2000); break;
    case "rpc_ok": case "rpc_err": {
      const job = pending.get(frame.id);
      if (!job) break;
      clearTimeout(job.timer); pending.delete(frame.id);
      if (frame.t === "rpc_ok") job.resolve(frame.data); else job.reject(new Error(frame.reason || "No se pudo completar."));
      break;
    }
    case "error":
      if (frame.code === "auth" && everWelcomed && hello && hello.token && !hello.fresh) {
        accessToken = null;                                  // the session we kept expired: sign in again on the next try
        ws.close();
      } else if (frame.code === "auth") {
        conn.value = { state: "error", text: "No se pudo entrar", detail: frame.reason };
        retry = -1;
        ws.close();
      } else {
        toast(frame.reason, "bad");
        if (frame.code === "press" && frame.id) onPressError(String(frame.id), frame.reason);
        if (frame.code === "say") sayRefused.value++;
      }
      break;
  }
}

function connect(helloFrame) {
  hello = helloFrame;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}${base}/ws`);
  welcomed = false;
  ws.onopen = () => {
    report("websocket abierto");
    const { fresh, ...frame } = hello;
    ws.send(JSON.stringify(frame));
    if (!everWelcomed) conn.value = { state: "starting", text: "Entrando…", detail: "" };     // a reconnection keeps the screen
  };
  ws.onmessage = (event) => {
    const arrival = performance.now();
    let frame;
    try { frame = JSON.parse(event.data); } catch { return; }
    try { onFrame(frame, arrival); } catch (error) { console.error(error); report("error", `frame ${frame.t}: ${error.message}`); }
  };
  ws.onclose = () => {
    if (retry < 0) return;                                   // refused on purpose: do not hammer the server
    const wait = Math.min(15000, 1000 * 2 ** retry++);
    batch(() => {
      if (welcomed) banner.value = { text: `Conexión perdida. Reconectando en ${Math.round(wait / 1000)} s…`, kind: "bad" };
      else conn.value = { state: "error", text: "Sin conexión", detail: `Reintentando en ${Math.round(wait / 1000)} s…` };
    });
    setTimeout(() => {
      login().then(connect).catch((error) => {
        if (!everWelcomed) { fail(error); return; }
        report("reconexión fallida", (error && error.message) || String(error));      // no network yet: keep trying, the screen stays
        ws.onclose();
      });
    }, wait);
  };
}

async function login() {
  const reply = await fetch(`${base}/api/config`);
  if (!reply.ok) throw new Error(`El servidor del evento respondió ${reply.status}.`);
  const config = await reply.json();
  channelName.value = config.channel || "Evento";
  if (inDiscord && accessToken) return { t: "hello", token: accessToken };        // a reconnection: the session we have still works
  if (inDiscord) {
    const discord = await initSdk(config.clientId);
    report("SDK de Discord listo");
    const { code } = await discord.commands.authorize({
      client_id: config.clientId, response_type: "code", state: "", prompt: "none", scope: ["identify"],
    });
    report("autorizado por Discord");
    const reply = await fetch(`${base}/api/token`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) });
    const data = await reply.json();
    if (!reply.ok) throw new Error(data.error || "No se pudo iniciar sesión");
    report("token canjeado");
    await discord.commands.authenticate({ access_token: data.access_token });
    afterAuth();
    accessToken = data.access_token;
    return { t: "hello", token: data.access_token, fresh: true };
  }
  if (devName && config.dev) return { t: "hello", dev: devName, gm: devGm, host: devHost };
  throw new Error("Esta página está pensada para abrirse desde Discord. Para probarla en este PC añade ?dev=TuNombre a la dirección.");
}

function fail(error) {
  console.error(error);
  report("fallo", (error && error.message) || error);
  conn.value = { state: "error", text: "No se pudo entrar", detail: (error && error.message) || String(error) };
}

export function boot() {
  report("página cargada", inDiscord ? "dentro de Discord" : "fuera de Discord");
  login().then(connect).catch(fail);
}

export { sdk };
