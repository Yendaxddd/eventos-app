import { useEffect, useRef, useState } from "preact/hooks";
import { Gauge, Hand, Loader2, Play, RefreshCw, RotateCcw, Smartphone, Wifi } from "lucide-preact";
import { calib, comp, go, link, toast } from "../state.js";
import { ping, pongListeners, send } from "../net.js";
import { deviceLag, qualityOf, tapSpread } from "../clock.js";
import { matchTaps, summarizeNet, MIN_TAPS, UNSTEADY_MS } from "../latency-model.js";
import { QUALITY } from "../terms.js";
import { Page, Section } from "../ui/Controls.jsx";
import { vibrate } from "../sound.js";

const FAST = typeof window !== "undefined" && window.__fastLatency;     // tests shorten the whole thing
const PINGS = FAST ? 6 : 24;
const PING_EVERY = FAST ? 40 : 180;       // ms
const LOST_AFTER = FAST ? 400 : 1500;     // a pong later than this counts as lost
const BEATS = FAST ? 8 : 12;              // flashes in the tap test (the first WARMUP are practice)
const WARMUP = FAST ? 2 : 3;
const BEAT_MS = FAST ? 300 : 1000;
const SAVE_WAIT = FAST ? 1200 : 5000;        // how long to wait for the server to say it kept the result
const LIT_MS = FAST ? 120 : 200;          // how long the circle stays lit: a flash, not a state

const bar = (rtt) => (rtt === undefined ? "wait" : rtt === null ? "lost" : rtt < 90 ? "great" : rtt < 200 ? "fair" : "poor");

// ---- step 1: the connection --------------------------------------------------------------------------------------
// Sends PINGS pings and resolves with the summary. `cancel()` stops it (the page was left); a pong slower than LOST_AFTER counts as lost.
function runNetwork(onSample) {
  let cancel = () => {};
  const promise = new Promise((resolve) => {
    const sent = new Map();                 // stamp -> index
    const rtts = new Array(PINGS).fill(undefined);   // undefined = not answered yet, null = lost
    let answered = 0, count = 0, finished = false, closing = 0;
    const done = () => {
      if (finished) return;
      finished = true;
      pongListeners.delete(listener);
      clearInterval(timer); clearTimeout(closing);
      resolve(summarizeNet(rtts, LOST_AFTER));
    };
    const listener = (stamp, rtt) => {
      if (finished || !sent.has(stamp)) return;
      const i = sent.get(stamp);
      if (rtts[i] !== undefined) return;
      rtts[i] = rtt; answered++;
      onSample(rtts.slice());
      if (answered >= PINGS) done();
    };
    pongListeners.add(listener);
    const timer = setInterval(() => {
      if (count >= PINGS) { clearInterval(timer); closing = setTimeout(done, LOST_AFTER); return; }
      const stamp = ping();
      if (stamp !== null) sent.set(stamp, count);
      else rtts[count] = null;              // no connection at that moment: lost, and shown as such
      count++;
    }, PING_EVERY);
    cancel = () => { finished = true; pongListeners.delete(listener); clearInterval(timer); clearTimeout(closing); };
  });
  return { promise, cancel };
}

// ---- the page ---------------------------------------------------------------------------------------------------------
// The time of an input event on the same clock as performance.now(); the handler can run a little after the finger touched the glass,
// so the event's own stamp is better than "now" (when it looks wrong, now is used).
const stampOf = (e) => {
  const now = performance.now();
  return e && Number.isFinite(e.timeStamp) && e.timeStamp > 0 && e.timeStamp <= now + 5 && e.timeStamp > now - 1000 ? e.timeStamp : now;
};

const FAILS = {
  few: ["No se detectaron suficientes toques", `Hacen falta al menos ${MIN_TAPS} toques cerca de los destellos. Toca el círculo (o pulsa Espacio) justo cuando se ilumine.`],
  unsteady: ["Los toques fueron muy irregulares", "Para medir tu dispositivo hace falta un ritmo parecido en todos los toques. Inténtalo otra vez, sin prisa, siguiendo el destello."],
  hidden: ["La pantalla se ocultó durante la prueba", "Mientras la ventana está en segundo plano los destellos se detienen. Repite el ritmo sin cambiar de pantalla."],
};

export function LatencyPage() {
  const [stage, setStage] = useState("intro");        // intro | net | tap-intro | tap | tap-failed | saving | unsent | result
  const [samples, setSamples] = useState([]);
  const [net, setNet] = useState(null);
  const [beat, setBeat] = useState(-1);
  const [fail, setFail] = useState("few");
  const [pending, setPending] = useState(null);       // a result the server has not confirmed
  const [kept, setKept] = useState(false);            // the tap step was skipped: the earlier device measurement stays
  const circle = useRef(null);
  const flashes = useRef([]);                         // when each flash was drawn (performance.now clock)
  const taps = useRef([]);
  const alive = useRef(true);
  const stageRef = useRef(stage);
  const netRef = useRef(null);
  const cancelNet = useRef(() => {});
  const raf = useRef(0);
  const interrupted = useRef(false);
  const before = useRef(null);                        // what the server had told us when we sent the result
  stageRef.current = stage;
  useEffect(() => () => { alive.current = false; cancelNet.current(); cancelAnimationFrame(raf.current); }, []);

  const startNet = async () => {
    setStage("net"); setSamples([]);
    const run = runNetwork((s) => alive.current && setSamples(s));
    cancelNet.current = run.cancel;
    const result = await run.promise;
    if (!alive.current) return;
    netRef.current = result;
    setNet(result);
    setStage("tap-intro");
  };

  const mark = (e) => {                               // a tap (finger, mouse or key) on the circle
    if (stageRef.current !== "tap") return;
    taps.current.push(stampOf(e));
    const el = circle.current;
    if (el) { el.dataset.tapped = "1"; setTimeout(() => { if (el.dataset) el.dataset.tapped = "0"; }, 110); }
    vibrate(10);
  };
  const onTap = (e) => { e.preventDefault(); mark(e); };

  useEffect(() => {
    if (stage !== "tap") return undefined;
    const onKey = (e) => {
      if (e.repeat || (e.code !== "Space" && e.code !== "Enter")) return;
      e.preventDefault(); mark(e);
    };
    const onHide = () => { if (document.hidden) interrupted.current = true; };
    window.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", onHide);
    return () => { window.removeEventListener("keydown", onKey); document.removeEventListener("visibilitychange", onHide); };
  }, [stage]);

  const startTap = () => {
    setStage("tap"); setBeat(-1); flashes.current = []; taps.current = []; interrupted.current = false;
    const start = performance.now() + 1200;
    let k = 0, litUntil = 0;
    const loop = (ts) => {
      if (!alive.current) return;
      const el = circle.current;
      if (litUntil && ts >= litUntil) { litUntil = 0; if (el) el.dataset.lit = "0"; }
      if (k < BEATS && ts >= start + k * BEAT_MS) {      // the flash is drawn straight on the element, with no render in between, and timed by this frame
        flashes.current.push(ts);
        if (el) el.dataset.lit = "1";
        litUntil = ts + LIT_MS;
        setBeat(k); k++;
      }
      if (k >= BEATS && ts > start + (BEATS - 1) * BEAT_MS + 600) { if (el) el.dataset.lit = "0"; finishTap(); return; }
      raf.current = requestAnimationFrame(loop);
    };
    raf.current = requestAnimationFrame(loop);
  };

  const finishTap = () => {
    // each tap belongs to the closest flash and to only one; the warm-up flashes are not counted
    const errs = matchTaps(flashes.current, taps.current, { skip: WARMUP });
    const device = deviceLag(errs);
    const spread = tapSpread(errs);
    if (interrupted.current) { setFail("hidden"); setStage("tap-failed"); return; }
    if (device === null || errs.length < MIN_TAPS) { setFail("few"); setStage("tap-failed"); return; }
    if (spread !== null && spread > UNSTEADY_MS) { setFail("unsteady"); setStage("tap-failed"); return; }
    setKept(false);
    save({ ...connection(), device, spread, taps: errs.length });
  };

  const connection = () => {
    const n = netRef.current;
    return { median: n.median, min: n.min, p90: n.p90, jitter: n.jitter, loss: n.loss };
  };

  const save = (result) => {
    before.current = { calib: calib.value, comp: comp.value };
    setPending(result);
    if (!send({ t: "latency", result })) { setStage("unsent"); toast("Sin conexión: el ajuste no se guardó.", "bad"); return; }
    setStage("saving");
  };

  // the server answers with the result it kept and then the adjustment: only then is it "saved" (a lost answer is not hidden)
  const calibNow = calib.value, compNow = comp.value;
  useEffect(() => {
    if (stage !== "saving" || !before.current) return undefined;
    if (calibNow !== before.current.calib && compNow !== before.current.comp) { setStage("result"); setPending(null); toast("Ajuste guardado.", "ok"); return undefined; }
    const id = setTimeout(() => { if (stageRef.current === "saving") { setStage("unsent"); toast("El servidor no confirmó el ajuste.", "bad"); } }, SAVE_WAIT);
    return () => clearTimeout(id);
  }, [stage, calibNow, compNow]);

  // no device measurement: the server keeps the one it had
  const skipTap = () => { setKept(true); save({ ...connection(), device: null, spread: null, taps: 0 }); };
  const again = () => { setStage("intro"); setNet(null); setPending(null); };

  const quality = net ? qualityOf(net.median, net.loss) : "off";
  const c = comp.value, saved = calib.value;

  return (
    <Page title="Prueba de latencia" icon={Gauge}>
      {stage === "intro" && (
        <>
          <div class="card-2 col" style={{ gap: "var(--sp-3)" }}>
            <p>El juego mide tu tiempo de reacción desde que ves el QTE hasta que lo pulsas. Una conexión lenta o una pantalla con retraso te quitan unas décimas sin que sea tu culpa.</p>
            <p class="dim">Esta prueba mide las dos cosas y el servidor las compensa solo, <b>solo en tus respuestas</b>. Son unos 25 segundos.</p>
          </div>
          <Section title="Qué se mide">
            <div class="setting"><Wifi size={20} /><div class="info"><strong>Tu conexión</strong><span>{PINGS} mensajes de ida y vuelta al servidor: tiempo típico, saltos y pérdidas.</span></div></div>
            <div class="setting"><Smartphone size={20} /><div class="info"><strong>Tu dispositivo</strong><span>Tocarás un círculo al ritmo de un destello. Así se sabe cuánto tarda tu pantalla y tu toque.</span></div></div>
          </Section>
          {saved && (
            <div class="card-2 col" data-testid="saved-calib">
              <strong>Última medición guardada</strong>
              <span class="dim">Conexión {saved.median != null ? `${Math.round(saved.median)} ms` : "—"} · dispositivo {saved.device != null ? `${saved.device} ms` : "sin medir"} · ajuste actual: red {c.net != null ? Math.round(c.net) : "—"} ms, dispositivo {c.device || 0} ms</span>
            </div>
          )}
          <button class="btn btn-primary btn-lg btn-block" type="button" onClick={startNet} data-testid="start-test"><Play size={18} /> Empezar</button>
        </>
      )}

      {stage === "net" && (
        <div class="card-2 col" style={{ gap: "var(--sp-4)" }} data-testid="net-step">
          <div class="row"><Wifi size={20} /><strong class="grow">Midiendo tu conexión…</strong><span class="num dim">{samples.filter((s) => s !== undefined && s !== null).length} / {PINGS}</span></div>
          <div class="rtt-bars" aria-hidden="true">
            {Array.from({ length: PINGS }, (_, i) => {
              const r = samples[i];
              return <i key={i} data-q={bar(r)} style={{ height: r === undefined || r === null ? "6%" : `${Math.max(8, Math.min(100, (r / 320) * 100))}%` }} />;
            })}
          </div>
          <p class="dim">Déjalo quieto un momento. No cierres esta pantalla.</p>
        </div>
      )}

      {stage === "tap-intro" && net && (
        <>
          <div class="card-2 col" style={{ gap: "var(--sp-3)" }} data-testid="net-result">
            <div class="row"><Wifi size={20} /><strong class="grow">Tu conexión: {QUALITY[quality]}</strong></div>
            {net.median === null ? (
              <div class="col" style={{ gap: "var(--sp-2)" }}>
                <p class="bad">No llegó ninguna respuesta del servidor. Revisa tu conexión e inténtalo otra vez.</p>
                <button class="btn btn-primary" type="button" onClick={startNet} data-testid="net-retry"><RefreshCw size={16} /> Volver a medir</button>
              </div>
            ) : (
              <div class="metrics">
                <div><span>Típico</span><b class="num">{Math.round(net.median)} ms</b></div>
                <div><span>Mejor</span><b class="num">{Math.round(net.min)} ms</b></div>
                <div><span>Saltos</span><b class="num">{Math.round(net.jitter)} ms</b></div>
                <div><span>Pérdida</span><b class="num">{Math.round(net.loss * 100)} %</b></div>
              </div>
            )}
          </div>
          <div class="card-2 col" style={{ gap: "var(--sp-3)" }}>
            <div class="row"><Hand size={20} /><strong>Ahora, tu dispositivo</strong></div>
            <p class="dim">Aparecerá un círculo que se ilumina cada segundo. <b>Toca el círculo justo cuando se ilumine</b>, siguiendo el ritmo. Son {BEATS} destellos; los {WARMUP} primeros son de práctica. También puedes pulsar la barra espaciadora.</p>
          </div>
          <div class="row" style={{ gap: "var(--sp-2)" }}>
            <button class="btn btn-primary btn-lg grow" type="button" onClick={startTap} disabled={net.median === null} data-testid="start-tap"><Play size={18} /> Empezar el ritmo</button>
            <button class="btn btn-lg" type="button" onClick={skipTap} disabled={net.median === null}>Saltar</button>
          </div>
        </>
      )}

      {stage === "tap" && (
        <div class="tap-stage" data-testid="tap-step">
          <p class="dim center-text">{beat < 0 ? "Prepárate…" : beat < WARMUP ? `Práctica ${beat + 1} / ${WARMUP}` : `Destello ${beat + 1 - WARMUP} / ${BEATS - WARMUP}`}</p>
          <button type="button" class="tap-target" ref={circle} data-lit="0" data-tapped="0" onPointerDown={onTap} aria-label="Toca al ritmo">
            <span class="ring" key={beat} />
            <Hand size={44} />
          </button>
          <p class="faint center-text" style={{ fontSize: ".8125rem" }}>Toca cuando veas el destello, no antes. También sirve la barra espaciadora.</p>
        </div>
      )}

      {stage === "tap-failed" && (
        <div class="card-2 col" style={{ gap: "var(--sp-3)" }} data-testid="tap-failed">
          <strong>{FAILS[fail][0]}</strong>
          <p class="dim">{FAILS[fail][1]}</p>
          <div class="row"><button class="btn btn-primary grow" type="button" onClick={startTap} data-testid="tap-retry"><RotateCcw size={16} /> Repetir el ritmo</button><button class="btn" type="button" onClick={skipTap}>Saltar</button></div>
        </div>
      )}

      {stage === "saving" && (
        <div class="card-2 row" style={{ gap: "var(--sp-3)" }} data-testid="saving-step"><Loader2 class="spin-icon" size={20} /><strong>Guardando tu ajuste…</strong></div>
      )}

      {stage === "unsent" && (
        <div class="card-2 col" style={{ gap: "var(--sp-3)" }} data-testid="unsent-step">
          <strong>El ajuste no se guardó</strong>
          <p class="dim">No hubo confirmación del servidor. La medición no se pierde: puedes reintentar el guardado.</p>
          <div class="row"><button class="btn btn-primary grow" type="button" onClick={() => pending && save(pending)} disabled={!pending}>Reintentar</button><button class="btn" type="button" onClick={again}>Empezar de nuevo</button></div>
        </div>
      )}

      {stage === "result" && (
        <div class="col" style={{ gap: "var(--sp-4)" }} data-testid="result-step">
          <div class="card-2 col" style={{ gap: "var(--sp-3)" }}>
            <div class="row"><Gauge size={20} /><strong class="grow">Ajuste aplicado a tus respuestas</strong></div>
            <div class="metrics">
              <div><span>Red</span><b class="num" data-testid="adj-net">{c.net != null ? `${Math.round(c.net)} ms` : "—"}</b></div>
              <div><span>Dispositivo</span><b class="num" data-testid="adj-device">{`${c.device || 0} ms`}</b></div>
              <div><span>Máximo</span><b class="num">{c.cap} ms</b></div>
            </div>
            {kept && <p class="dim" data-testid="kept-note">No mediste el dispositivo esta vez: se mantiene la medición anterior{c.device ? ` (${c.device} ms)` : ""}.</p>}
            <p class="dim">La red se suma a tu tiempo (tardas en ver el QTE) y el dispositivo se resta (tu pantalla y tu toque tienen retraso). El servidor lo revisa en cada respuesta.</p>
          </div>
          <div class="row" style={{ gap: "var(--sp-2)" }}>
            <button class="btn grow" type="button" onClick={again}><RotateCcw size={16} /> Repetir</button>
            <button class="btn btn-primary grow" type="button" onClick={() => go("event")}>Volver al evento</button>
          </div>
        </div>
      )}
    </Page>
  );
}
