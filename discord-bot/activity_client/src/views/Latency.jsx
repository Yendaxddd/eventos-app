import { useEffect, useRef, useState } from "preact/hooks";
import { Gauge, Hand, Play, RotateCcw, Smartphone, Wifi } from "lucide-preact";
import { calib, comp, go, link, toast } from "../state.js";
import { ping, pongListeners, send } from "../net.js";
import { deviceLag, qualityOf, tapSpread } from "../clock.js";
import { median } from "../util.js";
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

const bar = (rtt) => (rtt === undefined ? "wait" : rtt === null ? "lost" : rtt < 90 ? "great" : rtt < 200 ? "fair" : "poor");

// ---- step 1: the connection --------------------------------------------------------------------------------------
function runNetwork(onSample) {
  return new Promise((resolve) => {
    const sent = new Map();                 // stamp -> index
    const rtts = new Array(PINGS).fill(undefined);   // undefined = not answered yet, null = lost
    let answered = 0, count = 0;
    const done = () => {
      pongListeners.delete(listener);
      clearInterval(timer);
      for (let i = 0; i < rtts.length; i++) if (rtts[i] === undefined) rtts[i] = null;
      const ok = rtts.filter((r) => r !== null);
      const sorted = [...ok].sort((a, b) => a - b);
      const med = median(ok);
      resolve({
        samples: rtts, median: med, min: sorted[0] ?? null, p90: sorted[Math.floor(sorted.length * 0.9)] ?? null,
        jitter: med === null ? null : ok.reduce((s, r) => s + Math.abs(r - med), 0) / ok.length,
        loss: (PINGS - ok.length) / PINGS,
      });
    };
    const listener = (stamp, rtt) => {
      if (!sent.has(stamp)) return;
      rtts[sent.get(stamp)] = rtt; answered++;
      onSample(rtts.slice());
      if (answered >= PINGS) done();
    };
    pongListeners.add(listener);
    const timer = setInterval(() => {
      if (count >= PINGS) { clearInterval(timer); setTimeout(done, LOST_AFTER); return; }
      const stamp = ping();
      if (stamp !== null) sent.set(stamp, count);
      count++;
    }, PING_EVERY);
  });
}

// ---- the page ---------------------------------------------------------------------------------------------------------
export function LatencyPage() {
  const [stage, setStage] = useState("intro");        // intro | net | tap | result
  const [samples, setSamples] = useState([]);
  const [net, setNet] = useState(null);
  const [errors, setErrors] = useState([]);
  const [beat, setBeat] = useState(-1);
  const [tapped, setTapped] = useState(false);
  const flashes = useRef([]);                         // when each flash was drawn (performance.now)
  const taps = useRef([]);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const startNet = async () => {
    setStage("net"); setSamples([]);
    const result = await runNetwork((s) => alive.current && setSamples(s));
    if (!alive.current) return;
    setNet(result);
    setStage("tap-intro");
  };

  const startTap = () => {
    setStage("tap"); setErrors([]); setBeat(-1); flashes.current = []; taps.current = [];
    const start = performance.now() + 1200;
    let k = 0, raf = 0;
    const loop = () => {
      if (!alive.current) return;
      const now = performance.now();
      if (k < BEATS && now >= start + k * BEAT_MS) { flashes.current.push(now); setBeat(k); k++; }
      if (k >= BEATS && now > start + BEATS * BEAT_MS + 500) { finishTap(); return; }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
  };

  const onTap = (e) => {
    e.preventDefault();
    const now = performance.now();
    taps.current.push(now);
    setTapped(true); setTimeout(() => setTapped(false), 120);
    vibrate(10);
  };

  const finishTap = () => {
    // each tap belongs to the closest flash; the warm-up flashes are not counted
    const errs = [];
    flashes.current.forEach((flash, i) => {
      if (i < WARMUP) return;
      let best = null;
      for (const t of taps.current) { const e = t - flash; if (Math.abs(e) < 450 && (best === null || Math.abs(e) < Math.abs(best))) best = e; }
      if (best !== null) errs.push(Math.round(best));
    });
    setErrors(errs);
    const device = deviceLag(errs);
    if (device === null) { setStage("tap-failed"); return; }
    save(device, errs);
  };

  const save = (device, errs) => {
    const result = {
      median: net.median, min: net.min, p90: net.p90, jitter: net.jitter, loss: net.loss, device, spread: tapSpread(errs), taps: errs.length,
    };
    send({ t: "latency", result });
    setStage("result");
    toast("Ajuste guardado.", "ok");
  };

  const skipTap = () => { setStage("result"); send({ t: "latency", result: { median: net.median, min: net.min, p90: net.p90, jitter: net.jitter, loss: net.loss, device: null, spread: null, taps: 0 } }); };

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
            <div class="setting"><Wifi size={20} /><div class="info"><strong>Tu conexión</strong><span>24 mensajes de ida y vuelta al servidor: tiempo típico, saltos y pérdidas.</span></div></div>
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
            {net.median === null ? <p class="bad">No llegó ninguna respuesta del servidor. Revisa tu conexión e inténtalo otra vez.</p> : (
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
            <p class="dim">Aparecerá un círculo que se ilumina cada segundo. <b>Toca el círculo justo cuando se ilumine</b>, siguiendo el ritmo. Son 12 destellos; los 3 primeros son de práctica.</p>
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
          <button type="button" class="tap-target" data-flash={beat >= 0 && !tapped ? beat % 2 : "off"} data-tapped={tapped ? "1" : "0"} onPointerDown={onTap} aria-label="Toca al ritmo">
            <span class="ring" key={beat} />
            <Hand size={44} />
          </button>
          <p class="faint center-text" style={{ fontSize: ".8125rem" }}>Toca cuando veas el destello, no antes.</p>
        </div>
      )}

      {stage === "tap-failed" && (
        <div class="card-2 col" style={{ gap: "var(--sp-3)" }}>
          <strong>No se detectaron suficientes toques</strong>
          <p class="dim">Hacen falta al menos 4 toques cerca de los destellos. Inténtalo otra vez, tocando el círculo con el ritmo.</p>
          <div class="row"><button class="btn btn-primary grow" type="button" onClick={startTap}><RotateCcw size={16} /> Repetir el ritmo</button><button class="btn" type="button" onClick={skipTap}>Saltar</button></div>
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
            <p class="dim">La red se suma a tu tiempo (tardas en ver el QTE) y el dispositivo se resta (tu pantalla y tu toque tienen retraso). El servidor lo revisa en cada respuesta.</p>
          </div>
          <div class="row" style={{ gap: "var(--sp-2)" }}>
            <button class="btn grow" type="button" onClick={() => { setStage("intro"); setNet(null); }}><RotateCcw size={16} /> Repetir</button>
            <button class="btn btn-primary grow" type="button" onClick={() => go("event")}>Volver al evento</button>
          </div>
        </div>
      )}
    </Page>
  );
}
