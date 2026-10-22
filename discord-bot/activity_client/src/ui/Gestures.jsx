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

export function FlickPad({ entry, live, lead }) {
  const dir = (entry.q.arena || {}).dir || "up";
  const A = ARROW[dir];
  const start = useRef(null);
  const [trail, setTrail] = useState(null);
  const send = (d) => { if (live) press(entry.id, "gesture", { dir: d }); };
  useKeys(live && lead, (e) => { if (KEY_DIR[e.key]) { e.preventDefault(); send(KEY_DIR[e.key]); } });
  return (
    <div class="gx-pad gx-flick" data-dir={dir} data-testid="gesture-flick" role="button" tabIndex={0} aria-label={`Desliza ${DIR_ES[dir]}`}
      onPointerDown={(e) => { if (!live) return; e.preventDefault(); e.currentTarget.setPointerCapture && e.currentTarget.setPointerCapture(e.pointerId); start.current = { x: e.clientX, y: e.clientY }; setTrail({ dx: 0, dy: 0 }); }}
      onPointerMove={(e) => { if (start.current) setTrail({ dx: e.clientX - start.current.x, dy: e.clientY - start.current.y }); }}
      onPointerUp={(e) => {
        const s = start.current; start.current = null; setTrail(null);
        if (!s) return;
        const d = directionOf(e.clientX - s.x, e.clientY - s.y);
        if (d) { vibrate(14); send(d); }
      }}
      onPointerCancel={() => { start.current = null; setTrail(null); }}>
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
  const at = (e) => {
    const r = box.current.getBoundingClientRect();
    return [clamp((e.clientX - r.left) / r.width, 0, 1), clamp((e.clientY - r.top) / r.height, 0, 1)];
  };
  const drop = (where) => { if (live) { vibrate(14); press(entry.id, "gesture", { x: Math.round(where[0] * 1000) / 1000, y: Math.round(where[1] * 1000) / 1000 }); } };
  useKeys(live && lead, (e) => {
    const step = 0.06;
    const move = { ArrowUp: [0, -step], ArrowDown: [0, step], ArrowLeft: [-step, 0], ArrowRight: [step, 0] }[e.key];
    if (move) { e.preventDefault(); setPos((old) => [clamp(old[0] + move[0], 0, 1), clamp(old[1] + move[1], 0, 1)]); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPos((old) => { drop(old); return old; }); }
  });
  const near = Math.hypot(pos[0] - p.to[0], pos[1] - p.to[1]) <= p.tolerance;
  return (
    <div class="gx-pad gx-drag" ref={box} data-testid="gesture-drag" aria-label="Arrastra la ficha hasta la diana (o muévela con las flechas y pulsa Enter)" role="group"
      onPointerMove={(e) => { if (dragging.current) setPos(at(e)); }}
      onPointerUp={(e) => { if (dragging.current) { dragging.current = false; const where = at(e); setPos(where); drop(where); } }}
      onPointerCancel={() => { dragging.current = false; }}>
      <i class="gx-goal" style={{ left: `${p.to[0] * 100}%`, top: `${p.to[1] * 100}%`, "--tol": p.tolerance }} data-near={near ? "true" : "false"}><Target /></i>
      <button type="button" class="gx-token" style={{ left: `${pos[0] * 100}%`, top: `${pos[1] * 100}%` }} aria-label="Ficha" data-testid="gesture-token" disabled={!live}
        onPointerDown={(e) => { if (!live) return; e.preventDefault(); e.stopPropagation(); box.current.setPointerCapture && box.current.setPointerCapture(e.pointerId); dragging.current = true; vibrate(8); }}>
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
