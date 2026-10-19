import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { ChevronLeft, ChevronRight, GraduationCap, RotateCcw, X } from "lucide-preact";
import { connected, go, prefs, qtes, rules, tutorial, view } from "../state.js";
import { setPrefs } from "../settings-actions.js";
import { startQte } from "../qte-store.js";
import { practiceFrame } from "../practice.js";
import { useNow, useResize } from "../hooks.js";
import { cx } from "../util.js";

// What each step says, which part of the screen it points at, and whether it starts a practice QTE.
const STEPS = [
  { id: "hi", title: "Bienvenido al evento", target: null,
    text: "Esta pantalla es tu mesa de juego: ves el canal del evento, tu vida y tus poderes, y respondes a los QTE con botones. Te lo enseño en un minuto, con práctica." },
  { id: "chat", title: "El canal del evento", target: "[data-arena] .feed", pad: 6,
    text: "Aquí aparece todo lo que ocurre en el canal de Discord, en vivo: mensajes, ataques del jefe y resultados. Se actualiza solo." },
  { id: "write", title: "Escribir", target: "[data-testid=composer]", pad: 6,
    text: "Escribe aquí para hablar en el canal. Si tienes personajes, el selector de la izquierda te deja hablar como ellos, igual que con Tupperbox." },
  { id: "evade", title: "Práctica: esquivar", target: null, practice: { mode: "single", difficulty: "medium", expect: "evade" },
    text: "Cuando te toque un QTE aparece un botón flotante, en un sitio distinto cada vez. Empieza siendo ESQUIVAR, con un temporizador encima. Púlsalo antes de que se acabe la barra.",
    ok: "¡Bien! Esquivar vale hasta el final de su ventana, pero cuanto antes, mejor.",
    bad: "Esa vez llegó tarde o no se pulsó. No pasa nada: aquí no hay daño. Inténtalo otra vez." },
  { id: "parry", title: "Práctica: parry", target: null, practice: { mode: "single", difficulty: "medium", expect: "parry", wait: true },
    text: "Cuando se abre la ventana de parry, el botón cambia a PARRY y aparece en otro sitio. El parry solo vale dentro de la barra: si lo pulsas antes de tiempo, falla. La banda violeta es la zona de Black Flash.",
    ok: "¡Parry! Mientras más cerca de la banda violeta, más posibilidades de Black Flash.",
    bad: "Fallaste el parry: fue antes o después de la ventana. Espera a que el botón cambie y pulsa dentro de la barra." },
  { id: "help", title: "Rescatar, cargas y poderes", target: "[data-testid=actions]", pad: 6,
    text: "Si el QTE es de otro jugador verás un botón «Rescatar» arriba del canal. Tus poderes se cargan al recibir y dar daño; cuando brillan, están listos. Tras esquivar a tiempo tienes unos segundos para el contraataque." },
  { id: "menu", title: "Menú y ajustes", target: "[data-testid=menu-button]", pad: 4,
    text: "En el menú están los ajustes (tamaño de los botones, dónde aparecen, colores, sonido) y la prueba de latencia, que mide tu conexión y ajusta tus tiempos. Te recomiendo hacerla una vez." },
  { id: "done", title: "¡Listo para jugar!", target: null,
    text: "Puedes repetir este tutorial cuando quieras desde el menú. Mucha suerte en el evento." },
];

let practiceCount = 0;
export function clearPractice() {
  qtes.value = qtes.value.filter((e) => !e.practice);
}
function spawnPractice(spec) {
  clearPractice();
  const frame = practiceFrame(`practice-${++practiceCount}`, spec.difficulty, rules.value, spec.mode);
  frame.tGo = 0;
  startQte(frame, { practice: true });
}

function Spotlight({ selector, pad = 6 }) {
  const [box, setBox] = useState(null);
  const measure = () => {
    const el = selector ? document.querySelector(selector) : null;
    if (!el) { setBox(null); return; }
    const r = el.getBoundingClientRect();
    setBox(r.width && r.height ? { left: r.left - pad, top: r.top - pad, width: r.width + pad * 2, height: r.height + pad * 2 } : null);
  };
  useLayoutEffect(measure, [selector]);
  useResize(measure);
  useEffect(() => { const id = setInterval(measure, 500); return () => clearInterval(id); }, [selector]);
  if (!box) return <div class="tut-dim" />;
  return <div class="tut-spot" style={{ left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` }} />;
}

function Tutorial() {
  const state = tutorial.value;
  const step = STEPS[state.step];
  const [verdict, setVerdict] = useState(null);     // "ok" | "bad" | null, for the practice steps
  const last = useRef(null);
  useNow(250, true);

  const close = (finished) => {
    clearPractice();
    tutorial.value = { active: false, step: 0 };
    if (!prefs.value.tutorialDone) setPrefs({ tutorialDone: true });
    if (finished) go("event");
  };
  const goTo = (n) => { setVerdict(null); tutorial.value = { active: true, step: Math.max(0, Math.min(STEPS.length - 1, n)) }; };

  useEffect(() => {                                  // entering a practice step starts its QTE; leaving it removes it
    if (step.practice) { const t = setTimeout(() => spawnPractice(step.practice), 600); return () => { clearTimeout(t); clearPractice(); }; }
    clearPractice();
    return undefined;
  }, [state.step]);

  // read the verdict of the practice QTE as soon as it has one
  const practiceEntry = qtes.value.find((e) => e.practice);
  useEffect(() => {
    if (practiceEntry && practiceEntry.result && last.current !== practiceEntry.id + practiceEntry.pressedCmd) {
      last.current = practiceEntry.id + practiceEntry.pressedCmd;
      const expected = step.practice && step.practice.expect;
      setVerdict(practiceEntry.result.ok && practiceEntry.pressedCmd === expected ? "ok" : "bad");
    }
  }, [practiceEntry && practiceEntry.result]);

  const again = () => { setVerdict(null); spawnPractice(step.practice); };
  const progress = Math.round((state.step / (STEPS.length - 1)) * 100);

  return (
    <div class="tut" data-testid="tutorial" data-step={step.id}>
      <Spotlight selector={step.target} pad={step.pad} />
      <div class="tut-card" role="dialog" aria-label="Tutorial" data-avoid>
        <div class="tut-head">
          <span class="chip primary"><GraduationCap size={13} /> Tutorial</span>
          <span class="faint num" style={{ fontSize: ".75rem" }}>{state.step + 1} / {STEPS.length}</span>
          <button class="icon-btn" type="button" style={{ marginLeft: "auto", width: 32, height: 32 }} onClick={() => close(false)} aria-label="Cerrar el tutorial" data-testid="tutorial-close"><X size={18} /></button>
        </div>
        <div class="tut-progress"><i style={{ width: `${progress}%` }} /></div>
        <h2>{step.title}</h2>
        <p>{step.text}</p>
        {step.practice && (
          <div class={cx("tut-verdict", verdict)} data-testid="tutorial-verdict">
            {verdict === "ok" ? step.ok : verdict === "bad" ? step.bad : step.practice.expect === "evade" ? "Esperando el QTE de práctica…" : "Esperando el QTE de práctica… no pulses hasta que el botón cambie a PARRY."}
            {verdict && <button class="btn btn-sm" type="button" onClick={again}><RotateCcw size={13} /> Otra vez</button>}
          </div>
        )}
        <div class="tut-actions">
          <button class="btn btn-ghost" type="button" disabled={state.step === 0} onClick={() => goTo(state.step - 1)}><ChevronLeft size={16} /> Atrás</button>
          {state.step < STEPS.length - 1
            ? <button class="btn btn-primary" type="button" onClick={() => goTo(state.step + 1)} data-testid="tutorial-next">{state.step === 0 ? "Empezar" : "Siguiente"} <ChevronRight size={16} /></button>
            : <button class="btn btn-primary" type="button" onClick={() => close(true)} data-testid="tutorial-finish">Terminar</button>}
        </div>
      </div>
    </div>
  );
}

// Shows the tutorial when it is on, and starts it by itself the first time somebody comes in.
export function TutorialHost() {
  const t = tutorial.value;
  const ok = connected.value;
  useEffect(() => {
    if (!ok || prefs.value.tutorialDone || tutorial.value.active) return undefined;
    const id = setTimeout(() => {
      if (!prefs.value.tutorialDone && view.value === "event" && !qtes.value.length) tutorial.value = { active: true, step: 0 };
    }, 2200);
    return () => clearTimeout(id);
  }, [ok]);
  if (!t.active || !ok) return null;
  return <Tutorial />;
}
