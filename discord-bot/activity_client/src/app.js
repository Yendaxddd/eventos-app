// Eventos Activity client: mirrors the event channel, lets the player write and answer QTEs with buttons whose
// timing is measured here, on the player's own screen.
import { DiscordSDK, patchUrlMappings } from "@discord/embedded-app-sdk";

const params = new URLSearchParams(location.search);
const inDiscord = params.has("frame_id");           // Discord adds frame_id when it loads the Activity
const devName = params.get("dev");                  // ?dev=Ana: a test window opened from this very PC (no Discord)
const base = inDiscord ? "/.proxy" : "";            // Discord forwards /.proxy/* to the mapped server

const $ = (id) => document.getElementById(id);
const state = { you: null, users: [], rtt: null, offset: null, messages: new Map(), samples: [], ws: null, retry: 0,
  canWrite: false, characters: [], qte: null, qteResult: null };
window.__eventos = state;                           // handy for tests and for debugging from the console

// ---- status ----------------------------------------------------------------------------------------------
function setState(name, text) {
  document.body.dataset.state = name;
  $("status").textContent = text;
}
let bannerTimer = null;
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
  const kind = m.author.webhook ? (m.author.ours ? "" : "WEBHOOK") : (m.author.bot ? "BOT" : "");   // our own webhooks speak for players
  if (kind) {
    const tag = document.createElement("span");
    tag.className = "tag" + (m.author.webhook ? " hook" : ""); tag.textContent = kind;
    head.append(tag);
  }
  const time = document.createElement("span");
  time.className = "time"; time.textContent = timeLabel(m.ts);
  head.append(time);
  if (m.reply) {
    const r = document.createElement("div");
    r.className = "reply"; r.textContent = (m.reply.author ? m.reply.author + ": " : "") + m.reply.text;
    body.append(r);
  }
  body.append(head);
  if (m.text) { const t = document.createElement("div"); t.className = "text"; inline(m.text, t); body.append(t); }
  for (const a of m.attachments || []) {
    const box = document.createElement("div");
    box.className = "attach";
    if (a.image) { const img = document.createElement("img"); img.loading = "lazy"; img.alt = a.name; img.src = cdn(a.url); box.append(img); }
    else { const link = document.createElement("a"); link.textContent = "📎 " + a.name; link.href = a.url; link.target = "_blank"; link.rel = "noopener noreferrer"; box.append(link); }
    body.append(box);
  }
  for (const sticker of m.stickers || []) {
    const img = document.createElement("img");
    img.className = "sticker"; img.loading = "lazy"; img.alt = sticker.name; img.src = cdn(sticker.url);
    body.append(img);
  }
  for (const e of m.embeds || []) body.append(embedNode(e));
  if ((m.reactions || []).length) {
    const row = document.createElement("div");
    row.className = "reactions";
    for (const r of m.reactions) {
      const chip = document.createElement("span");
      if (r.emoji.id) {
        const img = document.createElement("img");
        img.alt = r.emoji.name; img.src = cdn(`https://cdn.discordapp.com/emojis/${r.emoji.id}.${r.emoji.animated ? "gif" : "png"}?size=32`);
        chip.append(img);
      } else chip.append(r.emoji.name);
      chip.append(String(r.count));
      row.append(chip);
    }
    body.append(row);
  }
  el.append(avatar(m.author.avatar, m.author.name), body);
  return el;
}

const VIDEO = /\.(mp4|webm|mov)(\?|$)/i;

function embedNode(e) {
  const box = document.createElement("div");
  box.className = "embed";
  if (e.color) box.style.borderLeftColor = e.color;
  const add = (cls, text) => { const d = document.createElement("div"); d.className = cls; d.textContent = text; box.append(d); return d; };
  if (e.author) add("ea", e.author);
  if (e.thumb && e.image !== e.thumb && !(e.video && VIDEO.test(e.video))) {
    const t = document.createElement("img");
    t.className = "thumb"; t.loading = "lazy"; t.alt = ""; t.src = cdn(e.thumb); box.append(t);
  }
  if (e.title) {
    const t = add("et", "");
    if (e.url && /^https?:/.test(e.url)) { const a = document.createElement("a"); a.textContent = e.title; a.href = e.url; a.target = "_blank"; a.rel = "noopener noreferrer"; t.append(a); }
    else t.textContent = e.title;
  }
  if (e.description) { const d = document.createElement("div"); inline(e.description, d); box.append(d); }
  if ((e.fields || []).length) {
    const grid = document.createElement("div");
    grid.className = "fields";
    for (const f of e.fields) { const c = document.createElement("div"); const b = document.createElement("b"); b.textContent = f.name; c.append(b); inline(f.value, c); grid.append(c); }
    box.append(grid);
  }
  if (e.video && VIDEO.test(e.video)) {           // a GIF the sender picked (Tenor, Klipy...): a muted looping clip
    const v = document.createElement("video");
    v.src = cdn(e.video); v.muted = true; v.loop = true; v.autoplay = true; v.playsInline = true; v.preload = "metadata";
    if (e.thumb) v.poster = cdn(e.thumb);
    box.append(v);
  } else if (e.image || e.thumb) {
    const img = document.createElement("img");
    img.loading = "lazy"; img.alt = ""; img.src = cdn(e.image || e.thumb); box.append(img);
  }
  if (e.footer) add("ef", e.footer);
  return box;
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

// ---- writing ---------------------------------------------------------------------------------------------------
const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* private window: it is only a convenience */ } },
};

function setupComposer() {
  const select = $("as"), input = $("input");
  select.replaceChildren();
  const me = document.createElement("option");
  me.value = "me"; me.textContent = state.you ? state.you.name : "Yo";
  select.append(me);
  for (const name of state.characters) { const o = document.createElement("option"); o.value = name; o.textContent = name; select.append(o); }
  const saved = store.get("eventos.as");
  if (saved && state.characters.includes(saved)) select.value = saved;
  select.hidden = state.characters.length === 0;      // nothing to choose when there are no characters
  select.disabled = input.disabled = $("send").disabled = !state.canWrite;
  input.placeholder = state.canWrite ? "Escribe en el canal del evento…" : "Solo lectura: escribe en el chat de Discord";
  paintActions();
}

$("as").onchange = () => store.set("eventos.as", $("as").value);
$("composer").onsubmit = (event) => {
  event.preventDefault();
  const input = $("input");
  const text = input.value.trim();
  if (!text || !state.canWrite) return;
  send({ t: "say", text, as: $("as").value });
  input.value = "";
  input.focus();                                       // keep the keyboard up on a phone
};

// ---- QTE buttons ------------------------------------------------------------------------------------------------
// The player's screen is the stopwatch: the clock starts the moment the QTE is painted, and the server gets the
// elapsed time (it adds back half the round trip, and refuses what a human cannot do).
function involved(q) {
  if (!state.you) return false;
  return q.target ? q.target.id === state.you.id : (q.participants || []).includes(state.you.id);
}

function paintActions() {
  const q = state.qte;
  const open = state.canWrite && !!state.you;
  for (const button of document.querySelectorAll(".act")) {
    const timed = button.dataset.cmd === "evade" || button.dataset.cmd === "parry";
    button.disabled = !open || (timed && !(q && involved(q.q) && !q.pressed));
  }
}

function startQte(q) {
  endQte(true);
  clearTimeout(resultTimer);
  state.qte = { q, seen: null, pressed: false };
  const box = $("qte");
  box.dataset.active = "true"; box.dataset.result = "";
  $("qte-title").textContent = `⚡ QTE ${String(q.difficulty).toUpperCase()}`;
  $("qte-sub").textContent = q.target ? (involved(q) ? "¡Es para ti!" : `Debe responder ${q.target.name}`) : (involved(q) ? "¡Responde todo el grupo!" : "QTE de grupo");
  const fill = $("qte-fill");
  fill.style.transition = "none"; fill.style.transform = "scaleX(1)";
  paintActions();
  requestAnimationFrame((now) => {                     // painted: from here on the player can see it
    if (!state.qte || state.qte.q !== q) return;
    state.qte.seen = performance.now();
    fill.style.transition = `transform ${q.timeout}s linear`; fill.style.transform = "scaleX(0)";
    if (navigator.vibrate && involved(q)) navigator.vibrate(40);
  });
}

function idle() {
  const box = $("qte");
  box.dataset.active = "false"; box.dataset.result = "";
  $("qte-fill").style.transition = "none";
  $("qte-title").textContent = "Sin QTE por ahora";
  $("qte-sub").textContent = "Los botones se activan cuando te toque responder.";
}

function endQte(replacing = false) {
  state.qte = null;
  $("qte").dataset.active = "false";
  $("qte-fill").style.transition = "none";
  if (!replacing && !$("qte").dataset.result) idle();      // a verdict on screen stays a moment (see showResult)
  paintActions();
}

let resultTimer = null;
function showResult(frame) {
  if (frame.ok === null || frame.ok === undefined) return;
  const box = $("qte");
  box.dataset.result = frame.ok ? "ok" : "bad";
  $("qte-title").textContent = frame.ok ? "✅ ¡Bien!" : "❌ Fallaste";
  $("qte-sub").textContent = frame.ms != null ? `${frame.ms} ms` : "";
  clearTimeout(resultTimer);
  resultTimer = setTimeout(() => { if (!state.qte) idle(); }, 3000);
}

function press(cmd) {
  const q = state.qte;
  const timed = cmd === "evade" || cmd === "parry";
  if (timed) {
    if (!q || q.pressed || !involved(q.q) || q.seen === null) return;
    q.pressed = true;
    send({ t: "press", id: q.q.id, command: cmd, dt: Math.round(performance.now() - q.seen) });
    paintActions();
  } else {
    send({ t: "press", id: q ? q.q.id : "", command: cmd });
  }
}

for (const button of document.querySelectorAll(".act")) {
  button.addEventListener("pointerdown", (event) => { if (event.button === 0 || event.pointerType !== "mouse") { event.preventDefault(); if (!button.disabled) press(button.dataset.cmd); } });
  button.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); if (!button.disabled) press(button.dataset.cmd); } });
}
const KEYS = { KeyE: "evade", KeyP: "parry", KeyA: "adapt", KeyQ: "attack" };
document.addEventListener("keydown", (event) => {
  if (event.repeat || event.ctrlKey || event.metaKey) return;
  const tag = (event.target && event.target.tagName) || "";
  const typing = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
  if (event.key === "Escape" && typing) { event.target.blur(); return; }
  if (typing && !event.altKey) return;                  // typing: the letters are letters (Alt+letter works even then)
  const cmd = KEYS[event.code];
  const button = cmd && document.querySelector(`.act[data-cmd="${cmd}"]`);
  if (button && !button.disabled) { event.preventDefault(); press(cmd); }
});

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
        $("hint").textContent = "";
        state.canWrite = !!frame.canWrite; state.characters = frame.characters || [];
        setupComposer();
        renderUsers(frame.users);
        $("feed").replaceChildren(); state.messages.clear();
        for (const m of frame.backlog) addMessage(m);
        $("feed").scrollTop = $("feed").scrollHeight;
        startSync();
        const running = (frame.qtes || [])[0];
        if (running) startQte(running); else endQte();
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
      case "qte": startQte(frame.q); break;
      case "qte_end": if (state.qte && state.qte.q.id === frame.id) endQte(); break;
      case "qte_result": showResult(frame); break;
      case "pong": onPong(frame); break;
      case "slow": banner("Vas demasiado rápido: espera un momento."); setTimeout(() => banner(""), 2000); break;
      case "error":
        if (frame.code === "auth") { setState("error", "No se pudo entrar"); banner(frame.reason); ws.close(); state.retry = -1; }
        else {
          banner(frame.reason); clearTimeout(bannerTimer); bannerTimer = setTimeout(() => banner(""), 3500);
          if (frame.code === "press" && state.qte) { state.qte.pressed = false; paintActions(); }
        }
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
