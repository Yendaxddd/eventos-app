// Eventos Activity client: mirrors the event channel, lets the player write and answer QTEs with buttons whose
// timing is measured here, on the player's own screen.
import { DiscordSDK } from "@discord/embedded-app-sdk";

const params = new URLSearchParams(location.search);
const inDiscord = params.has("frame_id");           // Discord adds frame_id when it loads the Activity
const devName = params.get("dev");                  // ?dev=Ana: a test window opened from this very PC (no Discord)
const base = inDiscord ? "/.proxy" : "";            // Discord forwards /.proxy/* to the mapped server

const $ = (id) => document.getElementById(id);
const state = { you: null, users: [], rtt: null, offset: null, messages: new Map(), samples: [], ws: null, retry: 0,
  canWrite: false, characters: [], game: null, me: null };
window.__eventos = state;                           // handy for tests and for debugging from the console

// ---- telling the app how far we got ------------------------------------------------------------------------------
// A blank Activity is hard to diagnose from the outside, so the page reports its progress and its errors to the app
// (which prints them in its log).
const reported = new Set();
let errorsReported = 0;
function report(stage, detail = "") {
  if (stage === "error" ? errorsReported++ >= 5 : reported.has(stage)) return;
  reported.add(stage);
  try {
    fetch(`${base}/api/report`, { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
      body: JSON.stringify({ stage, detail: String(detail).slice(0, 300) }) }).catch(() => {});
  } catch { /* reporting is a courtesy */ }
}
window.addEventListener("error", (e) => report("error", `${e.message} (${(e.filename || "").split("/").pop()}:${e.lineno})`));
window.addEventListener("unhandledrejection", (e) => report("error", (e.reason && e.reason.message) || e.reason));
report("página cargada", inDiscord ? "dentro de Discord" : "fuera de Discord");

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

// ---- pictures ---------------------------------------------------------------------------------------------------
// Discord's own pictures come through the app's server (/media), so the Developer Portal needs no extra URL Mappings.
const MEDIA_HOST = /^https:\/\/(cdn\.discordapp\.com|media\.discordapp\.net|images-ext-\d+\.discordapp\.net)\//;
function cdn(url) {
  return url && MEDIA_HOST.test(url) ? `${base}/media?u=${encodeURIComponent(url)}` : url;
}

// A picture, or the person's initial on a coloured disc when there is none (or it does not load).
function avatar(url, name) {
  const disc = document.createElement("span");
  disc.className = "avatar";
  disc.textContent = (Array.from((name || "?").trim())[0] || "?").toUpperCase();   // Array.from: names in maths letters are surrogate pairs
  disc.style.background = `hsl(${[...(name || "?")].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7)} 45% 40%)`;
  if (url) {
    const img = document.createElement("img");
    img.className = "avatar"; img.alt = ""; img.src = cdn(url);   // not lazy: it is detached until it has loaded, and a lazy image outside the page never loads
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

// ---- game state: boss, HP, charges ---------------------------------------------------------------------------
const level = (hp, max) => (max && hp / max <= 0.25 ? "low" : max && hp / max <= 0.5 ? "mid" : "ok");

function paintGame() {
  const game = state.game || { boss: null, fight: false, players: [] };
  const boss = game.boss;
  $("hud-boss").hidden = !boss;
  if (boss) {
    $("boss-name").textContent = `${game.fight ? "⚔ " : ""}${boss.name}`;
    $("boss-fill").style.width = `${boss.max ? Math.max(0, Math.min(100, boss.hp / boss.max * 100)) : 0}%`;
    $("boss-text").textContent = `${boss.hp} / ${boss.max}`;
  }
  const mine = state.you && game.players.find((p) => p.id === state.you.id);
  const me = state.me;
  $("hud-me").hidden = !(mine || (me && me.charges));
  if (mine) {
    const fill = $("me-hp-fill");
    fill.style.width = `${mine.max ? Math.max(0, Math.min(100, mine.hp / mine.max * 100)) : 0}%`;
    fill.dataset.level = level(mine.hp, mine.max);
    $("me-hp-text").textContent = `${mine.hp} / ${mine.max}${mine.revenge ? " · REVENGE" : ""}`;
  }
  if (me && me.charges) {
    for (const [i, key] of [[1, "power1"], [2, "power2"]]) {
      const pct = Math.max(0, Math.min(100, me.charges[key] / (me.cost || 100) * 100));
      $(`ch${i}-fill`).style.width = `${pct}%`;
      $(`ch${i}-fill`).parentElement.classList.toggle("ready", pct >= 100);
      $(`ch${i}-fill`).parentElement.title = `Poder ${i}: ${me.charges[key]}%`;
    }
    $("streak").textContent = me.streak > 1 ? `🔥 ${me.streak}` : "";
  }
  $("hud").hidden = $("hud-boss").hidden && $("hud-me").hidden;
  const list = $("players");
  list.replaceChildren();
  for (const p of game.players) {
    const li = document.createElement("li");
    if (state.you && p.id === state.you.id) li.className = "you";
    const nm = document.createElement("span");
    nm.className = "nm"; nm.append(Object.assign(document.createElement("span"), { textContent: p.name }), `${p.hp}/${p.max}`);
    const bar = document.createElement("div"); bar.className = "bar";
    const fill = document.createElement("i");
    fill.style.width = `${p.max ? Math.max(0, Math.min(100, p.hp / p.max * 100)) : 0}%`; fill.dataset.level = level(p.hp, p.max);
    bar.append(fill); li.append(nm, bar); list.append(li);
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
  renderActions();
}

$("as").onchange = () => { store.set("eventos.as", $("as").value); renderActions(); };
$("composer").onsubmit = (event) => {
  event.preventDefault();
  const input = $("input");
  const text = input.value.trim();
  if (!text || !state.canWrite) return;
  send({ t: "say", text, as: $("as").value });
  input.value = "";
  input.focus();                                       // keep the keyboard up on a phone
};

// ---- QTE cards and buttons ---------------------------------------------------------------------------------------
// The player's screen is the stopwatch: the clock starts the moment a QTE is painted, and the server gets the elapsed
// time (it adds back half the round trip, and refuses what a human cannot do). Several QTEs can run at once: each has
// its own card, bar and buttons, and a button answers exactly that QTE.
const serverNow = () => Date.now() + (state.offset || 0);
state.qtes = new Map();                                // id -> { q, seen, done, busy, el, step, ... }
state.floatParry = store.get("eventos.floatParry") !== "0";
const ARROWS = { up: "⬆️", down: "⬇️", left: "⬅️", right: "➡️" };
const MODE_LABEL = { combo: "COMBO", direction: "DIRECCIÓN", bf_chain: "BLACK FLASH" };
const LABELS = { evade: "Evade", parry: "Parry", save: "Salvar", adapt: "Adapt", attack: "Ataque", ...ARROWS };

function involved(q) {
  if (!state.you) return false;
  return q.target ? q.target.id === state.you.id : (q.participants || []).includes(state.you.id);
}

// Does this QTE use the floating parry button (it appears somewhere random on the screen when the parry window opens)?
const floats = (q) => state.floatParry && q.commands.includes("parry") && ["single", "group", "bf_chain"].includes(q.mode);

function meNow() { return state.me || {}; }
const secondsLeft = (until) => (until ? Math.max(0, (until - serverNow()) / 1000) : 0);

function canPress(entry, cmd) {
  const q = entry.q, me = meNow();
  if (!state.canWrite || entry.seen === null || entry.done || entry.busy || !q.commands.includes(cmd)) return false;
  if (cmd === "save") return !involved(q) && !!q.target && (me.saves ? me.saves.left > 0 || secondsLeft(me.saves.until) <= 0 : true);
  if (!involved(q)) return false;
  if (cmd === "parry" && secondsLeft(me.parryUntil) > 0) return false;
  return true;
}

function cardButtons(entry) {
  const q = entry.q, out = [];
  if (q.mode === "direction") return involved(q) ? ["up", "left", "down", "right"] : [];
  if (!involved(q)) return q.commands.includes("save") && q.target ? ["save"] : [];
  for (const cmd of q.commands) {
    if (cmd === "adapt" || cmd === "save") continue;
    if (cmd === "parry" && floats(q)) continue;          // that one floats
    out.push(cmd);
  }
  return out;
}

function buildCard(entry) {
  const q = entry.q;
  const el = document.createElement("div");
  el.className = "qcard"; el.dataset.id = q.id; el.dataset.mode = q.mode;
  const head = document.createElement("div");
  head.className = "qhead";
  const title = document.createElement("strong");
  title.textContent = `⚡ ${MODE_LABEL[q.mode] ? MODE_LABEL[q.mode] + " " : ""}QTE ${String(q.difficulty).toUpperCase()}`;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = q.target ? (involved(q) ? "¡Es para ti!" : `Para ${q.target.name}`)
    : q.mode === "fake" ? "" : (involved(q) ? "¡Responde todo el grupo!" : "QTE de grupo");
  const res = document.createElement("span");
  res.className = "res";
  head.append(title, who, res);
  el.append(head);
  if (q.windows) {
    const track = document.createElement("div");
    track.className = "track";
    const place = (cls, range) => {
      if (!range) return;
      const i = document.createElement("i");
      i.className = `zone ${cls}`;
      i.style.left = `${Math.min(100, range[0] / q.timeout * 100)}%`;
      i.style.width = `${Math.max(0.5, Math.min(100, range[1] / q.timeout * 100) - range[0] / q.timeout * 100)}%`;
      track.append(i);
    };
    place("evade", q.windows.evade); place("parry", q.windows.parry); place("bf", q.windows.bf);
    const cursor = document.createElement("b");
    cursor.className = "cursor"; track.append(cursor);
    el.append(track);
  }
  if (q.mode === "combo") {
    const combo = document.createElement("div");
    combo.className = "combo"; el.append(combo);
  }
  if (q.mode === "direction") {
    const hint = document.createElement("div");
    hint.className = "dirhint";
    hint.textContent = `Flecha: ${q.arrow || "?"} — ¡pulsa la OPUESTA!`;
    el.append(hint);
  }
  const buttons = document.createElement("div");
  buttons.className = "qbtns";
  for (const cmd of cardButtons(entry)) {
    const b = actionButton(cmd, cmd === "save" ? `🛡 Salvar a ${q.target ? q.target.name : ""}` : LABELS[cmd]);
    b.dataset.qte = q.id;
    buttons.append(b);
  }
  if (buttons.children.length) el.append(buttons);
  entry.el = el; entry.res = res;
  return el;
}

function actionButton(cmd, label, hint = "") {
  const b = document.createElement("button");
  b.type = "button"; b.className = "act"; b.dataset.cmd = cmd;
  const name = document.createElement("b"); name.textContent = label;
  const small = document.createElement("small"); small.className = "cd"; small.textContent = hint;
  b.append(name, small);
  return b;
}

function paintCombo(entry) {
  const box = entry.el && entry.el.querySelector(".combo");
  if (!box) return;
  const { length } = entry.q.combo || { length: 0 };
  box.textContent = entry.step ? `${entry.index + 1}/${length} · ahora: ${LABELS[entry.step] || entry.step}` : "";
  box.dataset.step = entry.step || "";
}

function startQte(q) {
  if (state.qtes.has(q.id)) return;
  const entry = { q, seen: null, done: false, busy: false, el: null, step: q.combo ? q.combo.step : null,
    index: q.combo ? q.combo.index : 0, floatEl: null, floatTimer: null, pressed: false };
  state.qtes.set(q.id, entry);
  $("qtes").append(buildCard(entry));
  paintCombo(entry);
  syncIdle(); paintAll();
  requestAnimationFrame(() => {                        // painted: from here on the player can see it
    if (!state.qtes.has(q.id)) return;
    entry.seen = performance.now();
    const gone = Math.max(0, (serverNow() - q.tGo) / 1000);
    const cursor = entry.el.querySelector(".cursor");
    if (cursor) {
      cursor.style.left = `${Math.min(100, gone / q.timeout * 100)}%`;
      void cursor.offsetWidth;                         // apply the start before animating
      cursor.style.transition = `left ${Math.max(0, q.timeout - gone)}s linear`;
      cursor.style.left = "100%";
    }
    if (navigator.vibrate && involved(q)) navigator.vibrate(40);
    if (involved(q) && floats(q)) scheduleFloat(entry);
    paintAll();
  });
}

// The parry button appears at a random place of the screen when the parry window opens.
function scheduleFloat(entry) {
  const open = entry.q.windows && entry.q.windows.parry ? entry.q.windows.parry[0] : 0;
  const wait = Math.max(0, entry.q.tGo + open * 1000 - serverNow());
  entry.floatTimer = setTimeout(() => showFloat(entry), wait);
}

function showFloat(entry) {
  if (!state.qtes.has(entry.q.id) || entry.done || entry.floatEl) return;
  const area = $("feed").getBoundingClientRect();
  const width = 110, height = 64;
  const left = area.left + 8 + Math.random() * Math.max(0, area.width - width - 16);
  const top = area.top + 8 + Math.random() * Math.max(0, area.height - height - 16);
  const b = actionButton("parry", state.qtes.size > 1 ? `Parry #${entry.q.id}` : "Parry", "P");
  b.classList.add("float-parry");
  b.dataset.qte = entry.q.id;
  b.style.left = `${left}px`; b.style.top = `${top}px`;
  $("float").append(b);
  entry.floatEl = b;
  paintAll();
}

function removeFloat(entry) {
  clearTimeout(entry.floatTimer);
  if (entry.floatEl) { entry.floatEl.remove(); entry.floatEl = null; }
}

function endQte(id) {
  const entry = state.qtes.get(id);
  if (!entry) return;
  removeFloat(entry);
  entry.ended = true;
  const keep = entry.pressed ? 2500 : 400;              // a verdict stays on screen a moment
  setTimeout(() => { if (entry.el) entry.el.remove(); state.qtes.delete(id); syncIdle(); paintAll(); }, keep);
  paintAll();
}

function clearQtes() {
  for (const entry of state.qtes.values()) { removeFloat(entry); if (entry.el) entry.el.remove(); }
  state.qtes.clear(); syncIdle();
}

function syncIdle() { $("idle").hidden = state.qtes.size > 0; $("legend").hidden = ![...state.qtes.values()].some((e) => e.q.windows); }

function showResult(frame) {
  const entry = state.qtes.get(frame.id);
  if (!entry || frame.ok === null || frame.ok === undefined) return;
  entry.res.textContent = `${frame.ok ? "✅" : "❌"}${frame.ms != null ? " " + frame.ms + " ms" : ""}`;
  entry.el.dataset.result = frame.ok ? "ok" : "bad";
}

function onStep(frame) {
  const entry = state.qtes.get(frame.id);
  if (!entry) return;
  entry.step = frame.step; entry.index = frame.index; entry.busy = false;
  paintCombo(entry); paintAll();
}

function press(cmd, entry = null) {
  const timed = ["evade", "parry", "save", "up", "down", "left", "right"].includes(cmd);
  if (!timed) { send({ t: "press", id: "", command: cmd, as: $("as").value }); return; }
  if (!entry || !canPress(entry, cmd)) return;
  entry.pressed = true;
  if (entry.q.mode === "combo") entry.busy = true;     // wait for the next step before answering again
  else entry.done = true;                              // one answer per QTE
  if (cmd === "parry") removeFloat(entry);
  send({ t: "press", id: entry.q.id, command: cmd, as: $("as").value, dt: Math.round(performance.now() - entry.seen) });
  paintAll();
}

// ---- global buttons (adapt, counter, powers, domain) and every countdown --------------------------------------------
function renderActions() {
  const box = $("actions"), me = meNow();
  box.replaceChildren();
  const chosen = $("as") ? $("as").value : "me";
  const powers = (me.powers && me.powers[chosen]) || {};
  const add = (cmd, label, hint, key) => { const b = actionButton(cmd, label, hint); b.dataset.key = key; box.append(b); return b; };
  add("adapt", "Adapt", "A", "A");
  add("attack", "Ataque", "Q", "Q").dataset.counter = "1";
  for (const [i, slot] of [[1, "power1"], [2, "power2"]]) {
    const info = powers[slot];
    if (chosen !== "me" && !info) continue;            // that character has no such power
    const b = add(slot, info ? info.name : `Poder ${i}`, String(i), String(i));
    b.dataset.slot = slot;
  }
  if (me.domain) add("domain", "Dominio", "3", "3");
  paintAll();
}

function paintAll() {
  const me = meNow(), open = state.canWrite && !!state.you;
  for (const b of document.querySelectorAll("#actions .act")) {
    b.disabled = !open;
    const cd = b.querySelector(".cd");
    if (b.dataset.counter) {                           // the counter window: 5 s after an evade
      const left = secondsLeft(me.counterUntil);
      b.classList.toggle("hot", left > 0);
      cd.textContent = left > 0 ? `${left.toFixed(1)} s` : "Q";
    } else if (b.dataset.slot) {
      const chargePct = me.charges ? me.charges[b.dataset.slot] : null;
      const info = ((me.powers || {})[$("as").value] || {})[b.dataset.slot] || {};
      const left = secondsLeft(info.until);
      b.classList.toggle("ready", chargePct !== null && chargePct >= (me.cost || 100) && left <= 0 && !info.paused);
      cd.textContent = left > 0 ? `⏱ ${Math.ceil(left)} s` : info.paused ? `⏸ ${info.paused} s` : chargePct !== null && chargePct !== undefined ? `${Math.round(chargePct)} %` : "";
    }
  }
  for (const entry of state.qtes.values()) {
    if (!entry.el) continue;
    for (const b of [...entry.el.querySelectorAll(".qbtns .act"), ...(entry.floatEl ? [entry.floatEl] : [])]) {
      const cmd = b.dataset.cmd;
      b.disabled = !canPress(entry, cmd);
      const cd = b.querySelector(".cd");
      if (cmd === "parry" && secondsLeft(me.parryUntil) > 0) cd.textContent = `⏱ ${secondsLeft(me.parryUntil).toFixed(1)} s`;
      else if (cmd === "save" && me.saves) {
        const wait = secondsLeft(me.saves.until);
        cd.textContent = me.saves.left > 0 ? `${me.saves.left}/${me.saves.limit}` : wait > 0 ? `⏱ ${Math.ceil(wait)} s` : "";
      } else if (cmd === "parry") cd.textContent = "P";
      else if (cmd === "evade") cd.textContent = "E";
    }
  }
}
setInterval(paintAll, 250);                            // countdowns

document.addEventListener("pointerdown", (event) => {
  const button = event.target.closest && event.target.closest(".act");
  if (!button || button.disabled || (event.pointerType === "mouse" && event.button !== 0)) return;
  event.preventDefault();
  const entry = button.dataset.qte ? state.qtes.get(button.dataset.qte) : null;
  press(button.dataset.cmd, entry);
});
document.addEventListener("keydown", (event) => {            // Enter / Space on a focused button
  const button = event.target.closest && event.target.closest(".act");
  if (button && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    if (!button.disabled) press(button.dataset.cmd, button.dataset.qte ? state.qtes.get(button.dataset.qte) : null);
  }
});

$("float-parry").checked = state.floatParry;
$("float-parry").onchange = () => {
  state.floatParry = $("float-parry").checked;
  store.set("eventos.floatParry", state.floatParry ? "1" : "0");
};

// Keyboard: the oldest QTE that can take the answer gets it. In the box, Alt+letter; Esc leaves the box.
const KEYS = { KeyE: "evade", KeyP: "parry", KeyS: "save", KeyA: "adapt", KeyQ: "attack", Digit1: "power1", Digit2: "power2",
  Digit3: "domain", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
document.addEventListener("keydown", (event) => {
  if (event.repeat || event.ctrlKey || event.metaKey) return;
  const tag = (event.target && event.target.tagName) || "";
  const typing = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
  if (event.key === "Escape" && typing) { event.target.blur(); return; }
  if (typing && !event.altKey) return;                  // typing: the letters are letters (Alt+letter works even then)
  const cmd = KEYS[event.code];
  if (!cmd) return;
  if (["evade", "parry", "save", "up", "down", "left", "right"].includes(cmd)) {
    const entry = [...state.qtes.values()].sort((a, b) => a.q.tGo - b.q.tGo).find((e) => canPress(e, cmd) && (cmd !== "parry" || !floats(e.q) || e.floatEl));
    if (entry) { event.preventDefault(); press(cmd, entry); }
  } else {
    const button = document.querySelector(`#actions .act[data-cmd="${cmd}"]`);
    if (button && !button.disabled) { event.preventDefault(); press(cmd); }
  }
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
    report("SDK de Discord listo");
    const { code } = await sdk.commands.authorize({
      client_id: config.clientId, response_type: "code", state: "", prompt: "none", scope: ["identify"],
    });
    report("autorizado por Discord");
    const reply = await fetch(`${base}/api/token`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) });
    const data = await reply.json();
    if (!reply.ok) throw new Error(data.error || "No se pudo iniciar sesión");
    report("token canjeado");
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
  ws.onopen = () => { report("websocket abierto"); ws.send(JSON.stringify(hello)); setState("starting", "Entrando…"); };
  ws.onmessage = (event) => {
    const frame = JSON.parse(event.data);
    switch (frame.t) {
      case "welcome":
        report("conectado"); welcomed = true; state.retry = 0; state.you = frame.you; state.samples = [];
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
        state.game = frame.state && frame.state.players ? frame.state : null; state.me = frame.me && frame.me.charges ? frame.me : null;
        paintGame(); renderActions();
        clearQtes();
        for (const running of frame.qtes || []) startQte(running);
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
      case "state": state.game = frame.s; paintGame(); break;
      case "me": state.me = frame.me; paintGame(); renderActions(); break;
      case "qte": startQte(frame.q); break;
      case "qte_end": endQte(frame.id); break;
      case "qte_result": showResult(frame); break;
      case "qte_step": onStep(frame); break;
      case "pong": onPong(frame); break;
      case "slow": banner("Vas demasiado rápido: espera un momento."); setTimeout(() => banner(""), 2000); break;
      case "error":
        if (frame.code === "auth") { setState("error", "No se pudo entrar"); banner(frame.reason); ws.close(); state.retry = -1; }
        else {
          banner(frame.reason); clearTimeout(bannerTimer); bannerTimer = setTimeout(() => banner(""), 3500);
          if (frame.code === "press" && frame.id) {            // the answer was not taken: the buttons come back
            const entry = state.qtes.get(String(frame.id));
            if (entry) { entry.busy = false; entry.done = false; paintAll(); if (/terminó/.test(frame.reason || "")) endQte(entry.q.id); }
          }
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
  report("fallo", (error && error.message) || error);
  setState("error", "Error");
  banner(error.message || String(error));
}

login().then(connect).catch(fail);
