// The bodies of the Activity's own QTEs (arena.py on the server): swipe, drag and tap. Each one measures the gesture and hands it to
// `press(id, "gesture", data)`; the keyboard can do all three (arrows, arrows + Enter, space bar) when this QTE is the one keys answer.
import { useEffect, useRef, useState } from "preact/hooks";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Hand, Move, Target } from "lucide-preact";
import { press } from "../qte-store.js";
import { vibrate, play } from "../sound.js";
import { clamp } from "../util.js";

const ARROW = { up: ArrowUp, down: ArrowDown, left: ArrowLeft, right: ArrowRight };
const KEY_DIR = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
const DIR_ES = { up: "arriba", down: "abajo", left: "a la izquierda", right: "a la derecha" };
const typing = (e) => { const t = e.target; return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable); };

// keys for the QTE keys answer now (see keys.js, which leaves these to the widget)
function useKeys(active, onKey) {
  const fn = useRef(onKey);
  fn.current = onKey;
  useEffect(() => {
    if (!active) return undefined;
    const handler = (e) => { if (!e.repeat && !typing(e) && !e.ctrlKey && !e.metaKey) fn.current(e); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active]);
}

export function directionOf(dx, dy, min = 28) {
  if (Math.hypot(dx, dy) < min) return null;
  return Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
}

// A swipe counts as soon as the finger has clearly gone one way (it does not wait for the finger to lift): Discord's phone app may
// take the touch over mid-swipe (a cancel instead of a lift), and a slow lift must not cost the QTE. A short swipe still counts on lift.
export const FLICK_NOW_PX = 40;
export const FLICK_MIN_PX = 22;

export function FlickPad({ entry, live, lead }) {
  const dir = (entry.q.arena || {}).dir || "up";
  const A = ARROW[dir];
  const start = useRef(null);
  const sent = useRef(false);
  const [trail, setTrail] = useState(null);
  const send = (d) => {
    if (!live || sent.current) return;
    sent.current = true;
    vibrate(14);
    press(entry.id, "gesture", { dir: d });
  };
  const finish = (e, min) => {
    const s = start.current; start.current = null; setTrail(null);
    if (!s || !e) return;
    const d = directionOf(e.clientX - s.x, e.clientY - s.y, min);
    if (d) send(d);
  };
  useKeys(live && lead, (e) => { if (KEY_DIR[e.key]) { e.preventDefault(); send(KEY_DIR[e.key]); } });
  return (
    <div class="gx-pad gx-flick" data-dir={dir} data-testid="gesture-flick" role="button" tabIndex={0} aria-label={`Desliza ${DIR_ES[dir]}`}
      onPointerDown={(e) => {
        if (!live) return;
        e.preventDefault();
        try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* the pointer is already gone */ }
        start.current = { x: e.clientX, y: e.clientY }; setTrail({ dx: 0, dy: 0 });
      }}
      onPointerMove={(e) => {
        const s = start.current;
        if (!s) return;
        const dx = e.clientX - s.x, dy = e.clientY - s.y;
        const d = directionOf(dx, dy, FLICK_NOW_PX);
        if (d) { start.current = null; setTrail(null); send(d); return; }
        setTrail({ dx, dy, x: e.clientX, y: e.clientY });
      }}
      onPointerUp={(e) => finish(e, FLICK_MIN_PX)}
      onPointerCancel={(e) => finish(trail && trail.x !== undefined ? { clientX: trail.x, clientY: trail.y } : e, FLICK_MIN_PX)}
      onLostPointerCapture={(e) => { if (start.current) finish(e, FLICK_MIN_PX); }}>
      <A class="gx-arrow" strokeWidth={2.6} />
      <span class="gx-label">Desliza</span>
      {trail && <i class="gx-trail" style={{ transform: `translate(${clamp(trail.dx, -80, 80)}px, ${clamp(trail.dy, -80, 80)}px)` }} />}
    </div>
  );
}

export function DragPad({ entry, live, lead }) {
  const p = entry.q.arena || { from: [0.2, 0.5], to: [0.8, 0.5], tolerance: 0.12 };
  const [pos, setPos] = useState(p.from);
  const box = useRef(null);
  const dragging = useRef(false);
  const last = useRef(p.from);
  const sent = useRef(false);
  const at = (e) => {
    const el = box.current;
    if (!el) return last.current;                       // the QTE ended under the finger
    const r = el.getBoundingClientRect();
    return [clamp((e.clientX - r.left) / r.width, 0, 1), clamp((e.clientY - r.top) / r.height, 0, 1)];
  };
  const place = (where) => { last.current = where; setPos(where); };
  const drop = (where) => {
    if (!live || sent.current) return;
    sent.current = true;
    vibrate(14);
    press(entry.id, "gesture", { x: Math.round(where[0] * 1000) / 1000, y: Math.round(where[1] * 1000) / 1000 });
  };
  // the finger let go (or Discord took the touch over): the token is dropped where it was last seen
  const release = (e) => { if (!dragging.current) return; dragging.current = false; const where = e ? at(e) : last.current; place(where); drop(where); };
  useKeys(live && lead, (e) => {
    const step = 0.06;
    const move = { ArrowUp: [0, -step], ArrowDown: [0, step], ArrowLeft: [-step, 0], ArrowRight: [step, 0] }[e.key];
    if (move) { e.preventDefault(); place([clamp(last.current[0] + move[0], 0, 1), clamp(last.current[1] + move[1], 0, 1)]); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drop(last.current); }
  });
  const near = Math.hypot(pos[0] - p.to[0], pos[1] - p.to[1]) <= p.tolerance;
  const grab = (e) => {
    if (!live) return;
    e.preventDefault(); e.stopPropagation();
    try { box.current.setPointerCapture(e.pointerId); } catch { /* the pointer is already gone */ }
    dragging.current = true; vibrate(8);
  };
  return (
    <div class="gx-pad gx-drag" ref={box} data-testid="gesture-drag" aria-label="Arrastra la ficha hasta la diana (o muévela con las flechas y pulsa Enter)" role="group"
      onPointerMove={(e) => { if (dragging.current) place(at(e)); }}
      onPointerUp={release}
      onPointerCancel={() => release(null)}
      onLostPointerCapture={() => release(null)}>
      <i class="gx-goal" style={{ left: `${p.to[0] * 100}%`, top: `${p.to[1] * 100}%`, "--tol": p.tolerance }} data-near={near ? "true" : "false"}><Target /></i>
      <button type="button" class="gx-token" style={{ left: `${pos[0] * 100}%`, top: `${pos[1] * 100}%` }} aria-label="Ficha" data-testid="gesture-token" disabled={!live}
        onPointerDown={grab}>
        <Move />
      </button>
      <span class="gx-label">Arrastra a la diana</span>
    </div>
  );
}

export function MashButton({ entry, live, lead }) {
  const need = (entry.q.arena || {}).count || 12;
  const [count, setCount] = useState(0);
  const tap = () => {
    if (!live) return;
    setCount((n) => {
      const next = n + 1;
      vibrate(6);
      if (next === need) { play("ok"); press(entry.id, "gesture", { count: next }); }
      return next;
    });
  };
  useKeys(live && lead, (e) => { if (e.key === " " || e.key === "Enter" || e.code === "KeyE") { e.preventDefault(); tap(); } });
  const pct = Math.min(1, count / need);
  return (
    <button type="button" class="qw-btn gx-mash" data-testid="gesture-mash" disabled={!live} aria-label={`Machaca: ${count} de ${need}`}
      style={{ "--pct": pct }} onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button !== 0) return; e.preventDefault(); tap(); }}>
      <Hand strokeWidth={2.4} />
      <span class="num">{Math.min(count, need)} / {need}</span>
      <i class="gx-ring" aria-hidden="true" />
    </button>
  );
}
