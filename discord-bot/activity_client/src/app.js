// Eventos Activity client (phase 0): connects to the app, measures the clock offset and mirrors the event channel.
import { DiscordSDK, patchUrlMappings } from "@discord/embedded-app-sdk";

const params = new URLSearchParams(location.search);
const inDiscord = params.has("frame_id");           // Discord adds frame_id when it loads the Activity
const devName = params.get("dev");                  // ?dev=Ana: a test window opened from this very PC (no Discord)
const base = inDiscord ? "/.proxy" : "";            // Discord forwards /.proxy/* to the mapped server

const $ = (id) => document.getElementById(id);
const state = { you: null, users: [], rtt: null, offset: null, messages: new Map(), samples: [], ws: null, retry: 0 };
window.__eventos = state;                           // handy for tests and for debugging from the console

// ---- status ----------------------------------------------------------------------------------------------
function setState(name, text) {
  document.body.dataset.state = name;
  $("status").textContent = text;
}
function banner(text) {
  const el = $("banner");
  el.hidden = !text;
  el.textContent = text || "";
}

// ---- images through Discord's proxy ------------------------------------------------------------------------
function cdn(url) {
  if (!inDiscord || !url) return url;
  return url
    .replace(/^https:\/\/cdn\.discordapp\.com\//, "/.proxy/cdn/")
    .replace(/^https:\/\/media\.discordapp\.net\//, "/.proxy/media/");
}

// A picture, or the person's initial on a coloured disc when there is none (or it does not load).
function avatar(url, name) {
  const disc = document.createElement("span");
  disc.className = "avatar";
  disc.textContent = (name || "?").trim().charAt(0).toUpperCase();
  disc.style.background = `hsl(${[...(name || "?")].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7)} 45% 40%)`;
  if (url) {
    const img = document.createElement("img");
    img.className = "avatar"; img.alt = ""; img.loading = "lazy"; img.src = cdn(url);
    img.onload = () => disc.replaceWith(img);
  }
  return disc;
}

// ---- a small, safe markdown renderer (everything goes in as text nodes, never as HTML) -----------------------
const TOKEN = /(\|\|[^|]+\|\|)|(\*\*[^*]+\*\*)|(__[^_]+__)|(~~[^~]+~~)|(`[^`\n]+`)|(\*[^*\n]+\*)|(_[^_\n]+_)|(<a?:\w+:\d+>)|(https?:\/\/[^\s<>()]+)/g;

function inline(text, into) {
  let last = 0;
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) into.append(text.slice(last, m.index));
    const t = m[0];
    let node;
    if (m[1]) { node = document.createElement("span"); node.className = "spoiler"; inline(t.slice(2, -2), node); node.onclick = () => node.classList.toggle("open"); }
    else if (m[2]) { node = document.createElement("strong"); inline(t.slice(2, -2), node); }
    else if (m[3]) { node = document.createElement("u"); inline(t.slice(2, -2), node); }
    else if (m[4]) { node = document.createElement("s"); inline(t.slice(2, -2), node); }
    else if (m[5]) { node = document.createElement("code"); node.textContent = t.slice(1, -1); }
    else if (m[6] || m[7]) { node = document.createElement("em"); inline(t.slice(1, -1), node); }
    else if (m[8]) {
      const id = t.match(/:(\d+)>/)[1];
      node = document.createElement("img"); node.className = "emoji"; node.alt = t.match(/:(\w+):/)[1];
      node.src = cdn(`https://cdn.discordapp.com/emojis/${id}.${t.startsWith("<a:") ? "gif" : "png"}?size=48`);
    } else {
      node = document.createElement("a"); node.textContent = t; node.href = t; node.target = "_blank"; node.rel = "noopener noreferrer";
    }
    into.append(node);
    last = m.index + t.length;
  }
  if (last < text.length) into.append(text.slice(last));
}

// ---- the mirrored channel -----------------------------------------------------------------------------------
function timeLabel(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function messageNode(m) {
  const el = document.createElement("div");
  el.className = "msg" + (m.edited ? " edited" : "");
  el.dataset.id = m.id;
  const body = document.createElement("div");
  body.className = "body";
  const head = document.createElement("div");
  head.className = "head";
  const name = document.createElement("span");
  name.className = "name"; name.textContent = m.author.name;
  if (m.author.color) name.style.color = m.author.color;
  head.append(name);
  if (m.author.bot || m.author.webhook) {
    const tag = document.createElement("span");
    tag.className = "tag"; tag.textContent = m.author.webhook && !m.author.ours ? "WEBHOOK" : "BOT";
    head.append(tag);
  }
  const time = document.createElement("span");
  time.className = "time"; time.textContent = timeLabel(m.ts);
  head.append(time);
  body.append(head);
  if (m.text) { const t = document.createElement("div"); t.className = "text"; inline(m.text, t); body.append(t); }
  for (const a of m.attachments || []) {
    const box = document.createElement("div");
    box.className = "attach";
    if (a.image) { const img = document.createElement("img"); img.loading = "lazy"; img.alt = a.name; img.src = cdn(a.url); box.append(img); }
    else { const link = document.createElement("a"); link.textContent = "📎 " + a.name; link.href = a.url; link.target = "_blank"; link.rel = "noopener noreferrer"; box.append(link); }
    body.append(box);
  }
  for (const e of m.embeds || []) {
    const box = document.createElement("div");
    box.className = "embed";
    if (e.color) box.style.borderLeftColor = e.color;
    if (e.title) { const t = document.createElement("div"); t.className = "et"; t.textContent = e.title; box.append(t); }
    if (e.description) { const d = document.createElement("div"); inline(e.description, d); box.append(d); }
    if (e.image) { const img = document.createElement("img"); img.loading = "lazy"; img.alt = ""; img.src = cdn(e.image); box.append(img); }
    body.append(box);
  }
  el.append(avatar(m.author.avatar, m.author.name), body);
  return el;
}

function nearBottom(feed) {
  return feed.scrollHeight - feed.scrollTop - feed.clientHeight < 120;
}

function addMessage(m, { replace = false } = {}) {
  const feed = $("feed");
  const stick = nearBottom(feed);
  const old = feed.querySelector(`[data-id="${CSS.escape(m.id)}"]`);
  state.messages.set(m.id, m);
  const node = messageNode(m);
  if (old) old.replaceWith(node); else if (!replace) feed.append(node);
  while (feed.children.length > 200) feed.firstChild.remove();
  if (stick) feed.scrollTop = feed.scrollHeight;
}

function removeMessage(id) {
  state.messages.delete(id);
  const old = $("feed").querySelector(`[data-id="${CSS.escape(id)}"]`);
  if (old) old.remove();
}

function renderUsers(users) {
  state.users = users;
  const list = $("users");
  list.replaceChildren();
  for (const u of users) {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = u.name;
    li.append(avatar(u.avatar, u.name), span);
    list.append(li);
  }
}

// ---- clock synchronisation ----------------------------------------------------------------------------------
// The server's clock minus ours, estimated NTP-style: of several ping/pong round trips the fastest ones are the
// most symmetric, so the offset is the median over the three quickest. Later phases show things at an absolute
// server time using this offset, so every player sees them at the same instant.
function onPong(frame) {
  const rtt = performance.now() - frame.c;
  const offset = frame.s + rtt / 2 - Date.now();
  state.samples.push({ rtt, offset });
  if (state.samples.length > 24) state.samples.shift();
  const best = [...state.samples].sort((a, b) => a.rtt - b.rtt).slice(0, 3);
  state.rtt = best[0].rtt;
  state.offset = best.map((s) => s.offset).sort((a, b) => a - b)[Math.floor(best.length / 2)];
  $("sync").textContent = `${Math.round(state.rtt)} ms · reloj ${state.offset >= 0 ? "+" : ""}${Math.round(state.offset)} ms`;
  send({ t: "sync", rtt: state.rtt, offset: state.offset });
}

function ping() {
  send({ t: "ping", c: performance.now() });
}

let burstTimer = null;
let keepTimer = null;
function startSync() {
  clearInterval(burstTimer); clearInterval(keepTimer);   // a reconnect must not stack timers
  let burst = 0;
  burstTimer = setInterval(() => {
    ping();
    if (++burst >= 8) { clearInterval(burstTimer); keepTimer = setInterval(ping, 10000); }
  }, 120);
}

// ---- connection ----------------------------------------------------------------------------------------------------
function send(frame) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(frame));
}

async function login() {
  const config = await (await fetch(`${base}/api/config`)).json();
  $("channel").textContent = config.channel || "Evento";
  if (inDiscord) {
    const sdk = new DiscordSDK(config.clientId);
    await sdk.ready();
    try {
      patchUrlMappings([{ prefix: "/cdn", target: "cdn.discordapp.com" }, { prefix: "/media", target: "media.discordapp.net" }]);
    } catch (e) { console.warn("patchUrlMappings", e); }
    const { code } = await sdk.commands.authorize({
      client_id: config.clientId, response_type: "code", state: "", prompt: "none", scope: ["identify"],
    });
    const reply = await fetch(`${base}/api/token`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) });
    const data = await reply.json();
    if (!reply.ok) throw new Error(data.error || "No se pudo iniciar sesión");
    await sdk.commands.authenticate({ access_token: data.access_token });
    return { t: "hello", token: data.access_token };
  }
  if (devName && config.dev) return { t: "hello", dev: devName };
  throw new Error("Esta página está pensada para abrirse desde Discord. Para probarla en este PC añade ?dev=TuNombre a la dirección.");
}

function connect(hello) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}${base}/ws`);
  state.ws = ws;
  let welcomed = false;
  ws.onopen = () => { ws.send(JSON.stringify(hello)); setState("starting", "Entrando…"); };
  ws.onmessage = (event) => {
    const frame = JSON.parse(event.data);
    switch (frame.t) {
      case "welcome":
        welcomed = true; state.retry = 0; state.you = frame.you; state.samples = [];
        banner("");
        setState("connected", "Conectado");
        $("channel").textContent = frame.channel || "Evento";
        $("hint").textContent = "Esta es una versión de prueba: el espejo del canal es de solo lectura.";
        renderUsers(frame.users);
        $("feed").replaceChildren(); state.messages.clear();
        for (const m of frame.backlog) addMessage(m);
        $("feed").scrollTop = $("feed").scrollHeight;
        startSync();
        break;
      case "users": renderUsers(frame.users); break;
      case "reset":
        $("channel").textContent = frame.channel || "Evento";
        $("feed").replaceChildren(); state.messages.clear();
        for (const m of frame.backlog) addMessage(m);
        $("feed").scrollTop = $("feed").scrollHeight;
        break;
      case "msg": addMessage(frame.m); break;
      case "edit": addMessage(frame.m, { replace: true }); break;
      case "del": removeMessage(frame.id); break;
      case "pong": onPong(frame); break;
      case "slow": banner("Vas demasiado rápido: espera un momento."); setTimeout(() => banner(""), 2000); break;
      case "error":
        if (frame.code === "auth") { setState("error", "No se pudo entrar"); banner(frame.reason); ws.close(); state.retry = -1; }
        else banner(frame.reason);
        break;
    }
  };
  ws.onclose = () => {
    if (state.retry < 0) return;                          // refused on purpose: do not hammer the server
    setState("error", welcomed ? "Conexión perdida" : "Sin conexión");
    const wait = Math.min(15000, 1000 * 2 ** state.retry++);
    banner(`Reconectando en ${Math.round(wait / 1000)} s…`);
    setTimeout(() => login().then(connect).catch(fail), wait);
  };
}

function fail(error) {
  console.error(error);
  setState("error", "Error");
  banner(error.message || String(error));
}

login().then(connect).catch(fail);
