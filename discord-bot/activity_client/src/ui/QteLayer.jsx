import { useEffect, useRef, useState } from "preact/hooks";
import {
  ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, Crosshair, Hand, Hourglass, Lock, Shield, ShieldPlus, Swords, X, Zap,
} from "lucide-preact";
import { qtes, prefs, me, rules, canWrite } from "../state.js";
import { GESTURE_MODES, byUrgency, canPress, elapsedSeconds, leadOf, phaseAt } from "../qte-model.js";
import { DragPad, FlickPad, MashButton } from "./Gestures.jsx";
import { press, context } from "../qte-store.js";
import { pickSpotFit, clampSpot, packAll, anyOverlap } from "../layout.js";
import { pressCommand } from "./Actions.jsx";
import { Avatar } from "./Avatar.jsx";
import { play, vibrate } from "../sound.js";
import { useNow, useResize } from "../hooks.js";
import { clamp, cx } from "../util.js";
import { CMD, DIFFICULTY, KEYS, MODE } from "../terms.js";

const ARROW_ICON = { up: ArrowUp, down: ArrowDown, left: ArrowLeft, right: ArrowRight };
const ARROW_OF = { "⬆": "up", "⬇": "down", "⬅": "left", "➡": "right" };
const GLYPH = { up: "⬆", down: "⬇", left: "⬅", right: "➡" };
const arrowName = (glyph) => ARROW_OF[String(glyph || "").replace(/️/g, "")] || (ARROW_ICON[glyph] ? glyph : "up");      // the bot sends the glyph; a practice QTE the name

// ---- geometry ---------------------------------------------------------------------------------------------------------
const touch = () => typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
function baseSize() {
  const phone = window.innerWidth <= 720;
  const base = touch() ? 108 : phone ? 94 : 104;
  return Math.round(base * (prefs.value.buttonScale / 100));
}
const LEAD = 1.14;
function boxFor(kind, size, lead) {
  const s = size * (lead ? LEAD : 1);
  if (kind === "flick") return { w: Math.round(s * 1.6 + 36), h: Math.round(s * 1.6 + 28 + 8 + 8 + 44) };
  if (kind === "drag") return { w: Math.round(s * 2.4 + 36), h: Math.round(s * 1.6 + 28 + 8 + 8 + 44) };
  if (kind === "arrows") { const pad = s * 0.58 * 3 + 12; return { w: Math.round(pad + 36), h: Math.round(pad + 28 + 8 + 44 + 8 + 8 + 44) }; }   // pad + timer + hint + meta
  return { w: Math.round(s + 36), h: Math.round(s + 28 + 8 + 8 + 44) };
}

// The playing area: the chat (any page without one gets the whole screen below the top bar).
export function playArea() {
  const el = document.querySelector("[data-arena]");
  const r = el ? el.getBoundingClientRect() : null;
  if (r && r.width > 140 && r.height > 140) return { left: r.left, top: r.top, width: r.width, height: r.height };
  const top = 56;
  return { left: 0, top, width: window.innerWidth, height: Math.max(200, window.innerHeight - top) };
}

// Parts of the screen the widgets should not land on (the tutorial's card, for one): anything with data-avoid.
function avoidBoxes() {
  return [...document.querySelectorAll("[data-avoid]")].map((el) => {
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  }).filter((b) => b.w > 0 && b.h > 0);
}

// ---- the timer on top of every button -----------------------------------------------------------------------------------
// The bar is animated by CSS from where the clock is when it appears (so it never restarts when the page redraws).
function Timer({ entry, from, to, variant = "drain", bf = null, paused = false, left }) {
  const [anim] = useState(() => {
    const total = Math.max(0.05, to - from);
    const gone = clamp(elapsedSeconds(entry, performance.now()) - from, 0, total);
    return { total, delay: -gone };
  });
  const style = { animationDuration: `${anim.total}s`, animationDelay: `${anim.delay}s`, animationPlayState: paused ? "paused" : "running" };
  return (
    <div class="qw-timer" data-testid="qte-timer">
      {variant === "window" ? (
        <div class="qw-track window">
          <i class="qw-spent" data-keep-motion style={style} />
          {bf && <i class="qw-zone" style={{ left: `${bf[0] * 100}%`, width: `${Math.max(1.5, (bf[1] - bf[0]) * 100)}%` }} />}
          <i class="qw-cursor" data-keep-motion style={style} />
        </div>
      ) : (
        <div class="qw-track"><i class="qw-fill" data-keep-motion style={style} /></div>
      )}
      <span class="qw-secs num">{left.toFixed(1)}</span>
    </div>
  );
}

// ---- one widget --------------------------------------------------------------------------------------------------------
function visual(entry, phase, ctx) {
  const q = entry.q;
  if (phase.kind === "evade") return { kind: "evade", icon: Shield, label: CMD.evade, key: KEYS.evade };
  if (phase.kind === "save") return { kind: "save", icon: ShieldPlus, label: CMD.save, key: KEYS.save };
  if (phase.kind === "parry") return { kind: "parry", icon: Swords, label: CMD.parry, key: KEYS.parry };
  if (phase.kind === "bf") return { kind: "bf", icon: Zap, label: "Parry", key: KEYS.parry };
  if (phase.kind === "combo") {
    const isParry = phase.cmd === "parry";
    return { kind: isParry ? "parry" : "evade", icon: isParry ? Swords : Shield, label: CMD[phase.cmd] || phase.cmd, key: KEYS[phase.cmd] };
  }
  if (phase.kind === "arrows") return { kind: "arrows" };
  if (phase.kind === "flick" || phase.kind === "drag" || phase.kind === "mash") return { kind: phase.kind, icon: Hand, label: MODE[phase.kind], key: "" };
  if (phase.kind === "wait") return { kind: q.mode === "bf_chain" ? "bf" : "parry", icon: Hourglass, label: q.mode === "bf_chain" ? "Prepárate" : "Espera", key: "" };
  return { kind: "parry", icon: X, label: "Tarde", key: "" };
}

function metaText(entry, rank) {
  const q = entry.q;
  const diff = DIFFICULTY[q.difficulty] || q.difficulty;
  if (q.mode === "combo") return `Combo · ${diff}`;
  if (q.mode === "bf_chain") return `Black Flash ×${q.chain || 1}`;
  if (q.mode === "fake") return diff;                                // a fake one must look like any other
  return `${MODE[q.mode] === "Individual" ? "" : MODE[q.mode] + " · "}${diff}`;
}

function Widget({ entry, phase, rank, lead, spot, size, ctx }) {
  const now = performance.now();
  const t = elapsedSeconds(entry, now);
  const v = visual(entry, phase, ctx);
  const p = prefs.value;
  const q = entry.q;
  const result = entry.result;
  const sent = entry.pressed && !result;
  const parryLocked = phase.cmd === "parry" && ctx.parryCooldown > 0;
  const state = result ? "done" : phase.state === "late" ? "late" : phase.state === "wait" ? "wait" : parryLocked ? "locked" : sent ? "sent" : "live";
  const left = Math.max(0, phase.to - t);
  const pressable = state === "live" && canPress(entry, phase.cmd === "arrows" ? "up" : phase.cmd, t, ctx);

  useEffect(() => {                                    // the first frame with this widget on it: from here the player can see it
    const raf = requestAnimationFrame(() => { if (entry.seen === null) entry.seen = Math.min(performance.now(), entry.arrival + 1000); });
    if (phase.kind === "parry" || phase.kind === "bf") { play("parry"); vibrate([18, 40, 18]); }
    return () => cancelAnimationFrame(raf);
  }, []);

  const fire = (cmd) => (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.preventDefault();
    press(entry.id, cmd);
  };
  const onKey = (cmd) => (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); press(entry.id, cmd); } };

  const resultKind = result ? (result.bf ? "bf" : result.ok ? "ok" : "bad") : undefined;
  const showTimer = state === "live" || state === "wait" || state === "locked";      // once answered (sent, done) or over (late) the bar goes away at once
  const windowTimer = phase.kind === "parry" || phase.kind === "bf";
  const Icon = result ? (result.ok ? (result.bf ? Zap : Check) : X) : state === "locked" ? Lock : v.icon;
  const label = result ? "" : state === "locked" ? "Parry" : state === "sent" ? "…" : v.label;      // the verdict is said once, under the button
  const sub = state === "locked" ? `${Math.ceil(ctx.parryCooldown)} s` : "";
  const keepEvade = p.keepEvade && phase.kind === "parry" && phase.evadeEnd !== undefined && t <= phase.evadeEnd;
  const lowMotion = p.motion === "reduced";

  return (
    <div class={cx("qw", lowMotion && "calm")} data-kind={v.kind} data-state={state} data-lead={lead ? "true" : "false"} data-result={resultKind}
      data-qte={entry.id} data-phase={phase.kind} data-testid="qte-widget"
      style={{ "--x": `${spot.x}px`, "--y": `${spot.y}px`, "--btn-base": `${size}px`, "--fit": spot.k }}>
      {showTimer && (
        <Timer entry={entry} from={phase.from} to={phase.to} variant={windowTimer ? "window" : "drain"} bf={phase.bf || null} paused={sent} left={left} />
      )}
      {q.mode === "combo" && q.combo && (
        <div class="qw-pips" aria-label={`Paso ${phase.index + 1} de ${phase.length}`}>
          {Array.from({ length: q.combo.length }, (_, i) => <i key={i} class={i < (entry.step ? entry.step.index : 0) ? "done" : i === (entry.step ? entry.step.index : 0) ? "now" : ""} />)}
        </div>
      )}
      {(phase.kind === "flick" || phase.kind === "drag" || phase.kind === "mash" || (GESTURE_MODES.includes(q.mode) && state !== "live")) && GESTURE_MODES.includes(q.mode) ? (
        q.mode === "flick" ? <FlickPad entry={entry} live={state === "live"} lead={lead} />
          : q.mode === "drag" ? <DragPad entry={entry} live={state === "live"} lead={lead} />
            : <MashButton entry={entry} live={state === "live"} lead={lead} />
      ) : phase.kind === "arrows" ? (
        <>
          <div class="qw-hint">Flecha: {GLYPH[arrowName(q.arrow)]} — pulsa la <b>OPUESTA</b></div>
          <div class="qw-pad">
            {["up", "left", "right", "down"].map((dir) => {
              const A = ARROW_ICON[dir];
              return (
                <button key={dir} type="button" class={dir} disabled={!(state === "live" && canPress(entry, dir, t, ctx))} data-cmd={dir}
                  aria-label={CMD[dir]} onPointerDown={fire(dir)} onKeyDown={onKey(dir)}><A /></button>
              );
            })}
            <div class="shown" aria-hidden="true">{(() => { const A = ARROW_ICON[arrowName(q.arrow)]; return <A />; })()}</div>
          </div>
        </>
      ) : (
        <button type="button" class="qw-btn" disabled={!pressable} data-cmd={phase.cmd || ""} aria-label={`${label} (${q.difficulty})`}
          onPointerDown={fire(phase.cmd)} onKeyDown={onKey(phase.cmd)}>
          <Icon strokeWidth={2.4} />
          <span>{label}</span>
          {sub && <span class="sub num">{sub}</span>}
          {state === "live" && lead && v.key && !touch() && <span class="kbd">{v.key}</span>}
        </button>
      )}
      {keepEvade && (
        <button type="button" class="qw-alt" data-cmd="evade" onPointerDown={fire("evade")} onKeyDown={onKey("evade")}><Shield size={14} /> Esquivar</button>
      )}
      {result ? (
        <div class="qw-result" data-testid="qte-result">{result.label}{result.sub ? <small class="num">{result.sub}</small> : null}</div>
      ) : (
        <div class="qw-meta"><span class="qw-rank">{rank}</span>{metaText(entry, rank)}</div>
      )}
    </div>
  );
}

// ---- the counter-attack window (5 s after an evade) --------------------------------------------------------------------------
function CounterWidget({ left, spot, size }) {
  const total = (rules.value && rules.value.counterWindow) || 5;
  const [startedLeft] = useState(left);
  const style = { animationDuration: `${total}s`, animationDelay: `${-clamp(total - startedLeft, 0, total)}s` };
  return (
    <div class="qw" data-kind="counter" data-state="live" data-lead="true" data-testid="counter-widget" style={{ "--x": `${spot.x}px`, "--y": `${spot.y}px`, "--btn-base": `${size}px`, "--fit": spot.k }}>
      <div class="qw-timer"><div class="qw-track"><i class="qw-fill" data-keep-motion style={style} /></div><span class="qw-secs num">{left.toFixed(1)}</span></div>
      <button type="button" class="qw-btn" data-cmd="attack" onPointerDown={(e) => { e.preventDefault(); pressCommand("attack"); }}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pressCommand("attack"); } }}>
        <Crosshair strokeWidth={2.4} /><span>Atacar</span>{!touch() && <span class="kbd">{KEYS.attack}</span>}
      </button>
      <div class="qw-meta"><span class="qw-rank">!</span>Contraataque</div>
    </div>
  );
}

// ---- rescues: somebody else's QTE that this player can answer with Save ---------------------------------------------------------
function RescueChip({ entry, ctx }) {
  const t = elapsedSeconds(entry, performance.now());
  const phase = phaseAt(entry, t);
  const live = phase.state === "live";
  const noSaves = ctx.saves && ctx.saves.left <= 0;
  const result = entry.result;
  const [anim] = useState(() => ({ total: Math.max(0.05, phase.to - phase.from), delay: -clamp(t - phase.from, 0, Math.max(0.05, phase.to - phase.from)) }));
  const left = Math.max(0, phase.to - t);
  const disabled = !live || noSaves || entry.pressed || !canWrite.value;
  useEffect(() => {
    const raf = requestAnimationFrame(() => { if (entry.seen === null) entry.seen = performance.now(); });
    return () => cancelAnimationFrame(raf);
  }, []);
  const sub = result ? result.label : noSaves ? `Sin rescates · ${Math.ceil(ctx.saves.wait)} s` : live ? `${left.toFixed(1)} s${ctx.saves ? ` · ${ctx.saves.left}/${ctx.saves.limit}` : ""}` : "Demasiado tarde";
  return (
    <button type="button" class={cx("rescue-chip", result && (result.ok ? "ok" : "bad"))} data-qte={entry.id} data-cmd="save" data-testid="rescue-chip" disabled={disabled}
      onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button !== 0) return; e.preventDefault(); press(entry.id, "save"); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); press(entry.id, "save"); } }}>
      <Avatar name={entry.q.target ? entry.q.target.name : "?"} size="sm" />
      <span class="r-txt"><b>Rescatar a {entry.q.target ? entry.q.target.name : "…"}</b><small class="num">{sub}</small></span>
      {live && !entry.pressed && <span class="r-bar"><i data-keep-motion style={{ animationDuration: `${anim.total}s`, animationDelay: `${anim.delay}s` }} /></span>}
    </button>
  );
}

// ---- where every widget goes ----------------------------------------------------------------------------------------------------
// Widgets that already have a place keep it (nothing moves under a finger); new ones get a free place, made smaller if the
// screen is crowded; and if even that cannot keep them apart, everybody is laid out again in rows.
const kindOf = (it) => (it.phase.kind === "arrows" ? "arrows" : it.entry.q.mode === "flick" ? "flick" : it.entry.q.mode === "drag" ? "drag" : "button");
const asBox = (s) => ({ x: s.x, y: s.y, w: s.w, h: s.h });

function allocate({ items, counterShown, area, avoid, spots, lastSpot, size, placement }) {
  const liveKeys = new Set(items.map((it) => it.key).filter(Boolean));
  for (const k of [...spots.keys()]) if (!liveKeys.has(k) && k !== "counter") spots.delete(k);
  const placed = [...avoid];
  for (const it of items) {
    const spot = it.key ? spots.get(it.key) : lastSpot.get(it.entry.id);
    if (spot) { it.spot = spot; placed.push(asBox(spot)); }
  }
  if (!counterShown) spots.delete("counter");
  else if (!spots.has("counter")) spots.set("counter", pickSpotFit(area, placed, (k) => boxFor("button", size * k, true), placement));
  const counter = counterShown ? spots.get("counter") : null;
  if (counter) placed.push(asBox(counter));
  for (const it of items) {
    if (it.spot) continue;
    const old = lastSpot.get(it.entry.id);               // the new widget of the same QTE (evade -> parry) lands away from the old one
    it.spot = pickSpotFit(area, old ? [...placed, asBox(old)] : placed, (k) => boxFor(kindOf(it), size * k, it.lead), placement);
    if (it.key) spots.set(it.key, it.spot);
    placed.push(asBox(it.spot));
  }
  const boxes = [...(counter ? [counter] : []), ...items.map((it) => it.spot)].map(asBox);
  if (anyOverlap(boxes)) {
    const packed = packAll(area, [...(counter ? [(k) => boxFor("button", size * k, true)] : []), ...items.map((it) => (k) => boxFor(kindOf(it), size * k, it.lead))]);
    if (packed) {
      let i = 0;
      if (counter) spots.set("counter", packed[i++]);
      for (const it of items) { it.spot = packed[i++]; if (it.key) spots.set(it.key, it.spot); }
    }
  }
  for (const it of items) lastSpot.set(it.entry.id, it.spot);
}

// ---- the layer -------------------------------------------------------------------------------------------------------------------
// One place per QTE for its whole life: the Parry button appears exactly where the Evade button was (a player aiming at it never
// finds it moved), and a late widget stays there too.
const spotKey = (entry, phase) => (phase.kind === "none" ? null : `${entry.id}:fixed`);

export function QteLayer() {
  const list = qtes.value;
  const counterAt = me.value ? me.value.counterAt : null;
  const active = list.length > 0 || !!counterAt;
  useNow(100, active);                                   // redraws the countdown numbers
  const spots = useRef(new Map());                       // widget key -> where it is on screen
  const lastSpot = useRef(new Map());                    // entry id -> where its last widget was (a late widget stays there)
  const [, setSize] = useState(0);
  useResize(() => {                                      // rotating the phone, opening the keyboard...: keep everything inside the area
    const area = playArea();
    spots.current.forEach((s, k) => spots.current.set(k, { ...s, ...clampSpot(area, s, { w: s.w, h: s.h }) }));
    setSize((n) => n + 1);
  });

  const now = performance.now();
  const p = prefs.value;
  const size = baseSize();
  const ctx = context();
  const targets = byUrgency(list.filter((e) => e.role === "target"), now);
  const shown = p.queueMode ? targets.filter((e) => !e.pressed && !e.ended).slice(0, 1).concat(targets.filter((e) => e.pressed || e.ended)) : targets;
  const queued = targets.length - shown.length;
  const rescues = list.filter((e) => e.role === "rescuer" && !e.ended);

  // when the next phase of any widget starts, redraw right then (not at the next 100 ms tick)
  useEffect(() => {
    let next = Infinity;
    const t0 = performance.now();
    for (const e of shown) {
      const ph = phaseAt(e, elapsedSeconds(e, t0));
      if (ph.state !== "late") next = Math.min(next, (ph.to - elapsedSeconds(e, t0)) * 1000);
    }
    if (!Number.isFinite(next)) return undefined;
    const id = setTimeout(() => setSize((n) => n + 1), Math.max(2, next + 3));
    return () => clearTimeout(id);
  });

  const area = playArea();
  const leader = leadOf(list, now);
  const items = shown.map((entry, i) => {
    const phase = phaseAt(entry, elapsedSeconds(entry, now));
    return { entry, phase, lead: !!leader && leader.id === entry.id, key: spotKey(entry, phase), rank: i + 1 };
  });
  const counterLeft = counterAt ? Math.max(0, (counterAt - now) / 1000) : 0;
  const counterShown = counterLeft > 0;
  allocate({ items, counterShown, area, avoid: avoidBoxes(), spots: spots.current, lastSpot: lastSpot.current, size, placement: p.buttonPlacement });
  for (const id of [...lastSpot.current.keys()]) if (!list.some((e) => e.id === id)) lastSpot.current.delete(id);

  return (
    <>
      <div class="qlayer" data-testid="qte-layer" aria-live="assertive">
        {items.map((it) => (
          <Widget key={`${it.entry.id}:${it.phase.kind === "bf" ? "parry" : it.phase.kind === "none" ? "late" : it.phase.kind}:${it.entry.q.mode === "combo" && it.entry.step ? it.entry.step.index : ""}`}
            entry={it.entry} phase={it.phase} rank={it.rank} lead={it.lead} spot={it.spot} size={size} ctx={ctx} />
        ))}
        {counterShown && <CounterWidget left={counterLeft} spot={spots.current.get("counter")} size={size} />}
      </div>
      {queued > 0 && <div class="qqueue" data-testid="qte-queue">+{queued} en cola</div>}
      {rescues.length > 0 && <RescueRail rescues={rescues} ctx={ctx} />}
    </>
  );
}

function RescueRail({ rescues, ctx }) {
  const sorted = byUrgency(rescues, performance.now());
  const shown = sorted.slice(0, 3);
  const area = playArea();
  return (
    <div class="rescue-dock" data-testid="rescue-rail" style={{ left: `${area.left}px`, top: `${area.top + 10}px`, width: `${area.width}px` }}>
      {shown.map((e) => <RescueChip key={e.id} entry={e} ctx={ctx} />)}
      {sorted.length > shown.length && <span class="chip">+{sorted.length - shown.length}</span>}
    </div>
  );
}
