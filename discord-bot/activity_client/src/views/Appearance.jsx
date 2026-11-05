// The «Estilo» part of the settings: ready-made styles drawn as small previews, everything a style is made of to tune by hand
// (with free colours), how the event screen is arranged, and, for the game masters, giving the event one style for everybody.
import { Check, Columns3, Crown, LayoutPanelLeft, PanelLeftClose, PanelRightClose, Sparkles, Undo2 } from "lucide-preact";
import { useState } from "preact/hooks";
import { canDo, eventLook, prefs, toast } from "../state.js";
import { setPrefs } from "../settings-actions.js";
import { rpc } from "../net.js";
import { LOOK_KEYS } from "../prefs.js";
import { ACCENT_NAMES, ACCENT_SWATCH, ARRANGEMENTS, STYLES, THEME_NAMES, THEME_SWATCH, styleOf, swatchOf } from "../looks.js";
import { Segmented, Setting, Switch } from "../ui/Controls.jsx";

const lookOf = (p) => Object.fromEntries(LOOK_KEYS.map((k) => [k, p[k]]));
const own = (patch) => setPrefs({ ...patch, followEvent: false });          // touching the look means «my own look» from now on

// A little screen in a style's colours: the top bar, a side panel, the chat and a button.
export function LookPreview({ look }) {
  const s = swatchOf(look);
  const r = look.corners === "sharp" ? 2 : look.corners === "soft" ? 9 : 5;
  const panel = look.surface === "outline" ? "transparent" : look.surface === "glass" ? `${s.panel}b3` : s.panel;
  const glow = look.bg === "aurora" || look.bg === "glow" ? `radial-gradient(120% 80% at 10% 0%, ${s.accent}40, transparent 60%),` : "";
  return (
    <div class="look-prev" aria-hidden="true" style={{ background: `${glow} ${s.bg}`, "--lp-r": `${r}px`, "--lp-line": s.line }}>
      <i class="lp-top" style={{ background: s.panel, borderColor: s.line }}><b style={{ background: `linear-gradient(135deg, ${s.accent}, ${s.partner})` }} /></i>
      <i class="lp-side" style={{ background: panel, borderColor: s.line }}><u style={{ background: s.faint }} /><u style={{ background: s.faint }} /><u style={{ background: s.accent }} /></i>
      <i class="lp-main" style={{ background: panel, borderColor: s.line }}>
        <u style={{ background: s.text, width: "70%" }} /><u style={{ background: s.faint, width: "52%" }} /><u style={{ background: s.faint, width: "62%" }} />
        <em style={{ background: s.accent }} />
      </i>
    </div>
  );
}

function StyleCard({ style, on, onPick }) {
  return (
    <button type="button" class="look-card" aria-pressed={on ? "true" : "false"} onClick={onPick} data-testid={`style-${style.id}`}>
      <LookPreview look={style.look} />
      <span class="look-name">{style.name}{on && <Check class="look-check" size={14} />}</span>
      <span class="look-hint">{style.hint}</span>
    </button>
  );
}

function Swatch({ colors, label, on, onPick, children }) {
  return (
    <button type="button" class="swatch" aria-pressed={on ? "true" : "false"} onClick={onPick} title={label}>
      <span class="swatch-dot" style={{ background: colors.length > 1 ? `linear-gradient(135deg, ${colors[0]} 50%, ${colors[1]} 50%)` : colors[0] }}>{on && <Check size={13} />}</span>
      <span class="swatch-label">{label}</span>
      {children}
    </button>
  );
}

// A free colour: a swatch that opens the system picker. The colour applies while it is being chosen.
function ColorSwatch({ value, label, on, onPick }) {
  return (
    <label class="swatch" aria-pressed={on ? "true" : "false"} title={label}>
      <span class="swatch-dot swatch-free" style={{ background: on ? value : "conic-gradient(#ef4444, #f59e0b, #22c55e, #06b6d4, #8b5cf6, #ec4899, #ef4444)" }}>{on && <Check size={13} />}</span>
      <span class="swatch-label">{label}</span>
      <input type="color" value={value} aria-label={label} onInput={(e) => onPick(e.currentTarget.value)} onClick={() => !on && onPick(value)} />
    </label>
  );
}

const ARRANGE_ICON = { classic: Columns3, mirror: LayoutPanelLeft, focus: PanelLeftClose, compact: PanelRightClose };

function ArrangeCard({ item, on }) {
  const Icon = ARRANGE_ICON[item.id] || Columns3;
  return (
    <button type="button" class="arrange-card" aria-pressed={on ? "true" : "false"} onClick={() => setPrefs({ arrange: item.id })} data-testid={`arrange-${item.id}`}>
      <span class={`arrange-map am-${item.id}`} aria-hidden="true"><i /><i /><i /></span>
      <span class="look-name"><Icon size={14} /> {item.name}{on && <Check class="look-check" size={14} />}</span>
      <span class="look-hint">{item.hint}</span>
    </button>
  );
}

// For the game masters who direct live: give the event a style (theirs) or take it away.
function EventStyle() {
  const [busy, setBusy] = useState(false);
  const p = prefs.value;
  const ev = eventLook.value;
  const send = async (look) => {
    setBusy(true);
    try {
      const name = look ? (STYLES.find((s) => s.id === styleOf(look))?.name || "Personalizado") : "";
      await rpc("gm.look_set", { look, name });
      toast(look ? "Ahora todo el evento ve este estilo (quien no eligió el suyo)." : "El evento ya no impone estilo.", "ok");
    } catch (err) { toast(err.message || String(err), "bad"); } finally { setBusy(false); }
  };
  return (
    <div class="setting stack look-gm" data-testid="event-style">
      <div class="info">
        <strong><Crown size={14} /> Estilo del evento</strong>
        <span>{ev ? "Hay un estilo para todo el evento. Lo ve cada jugador que sigue el estilo del evento." : "Nadie impone estilo: cada jugador ve el suyo."} Puedes poner el que tienes ahora en pantalla.</span>
      </div>
      <div class="row" style={{ gap: "8px", flexWrap: "wrap" }}>
        <button class="btn btn-sm btn-primary" type="button" disabled={busy} onClick={() => send(lookOf(p.followEvent && ev ? { ...p, ...ev } : p))} data-testid="event-style-set"><Sparkles size={14} /> Usar este estilo para el evento</button>
        {ev && <button class="btn btn-sm btn-ghost" type="button" disabled={busy} onClick={() => send(null)} data-testid="event-style-clear"><Undo2 size={14} /> Quitar</button>}
      </div>
    </div>
  );
}

export function AppearanceSection() {
  const p = prefs.value;
  const ev = eventLook.value;
  const following = p.followEvent && !!ev;
  const current = following ? null : styleOf(p);
  return (
    <>
      {ev && (
        <Setting title="Seguir el estilo del evento" hint={following ? "Ves el estilo que eligió el equipo de GM. Si cambias algo de aquí abajo, pasas a ver el tuyo." : "Ves tu propio estilo. Enciéndelo para ver el que eligió el equipo de GM."}>
          <Switch label="Seguir el estilo del evento" checked={p.followEvent} onChange={(v) => setPrefs({ followEvent: v })} />
        </Setting>
      )}
      {canDo("stage") && <EventStyle />}

      <div class="look-block">
        <div class="look-head"><strong>Estilos</strong><span class="faint">Un toque y todo combina: colores, esquinas, fondo y letra.</span></div>
        <div class="look-grid" role="group" aria-label="Estilos">
          {STYLES.map((s) => <StyleCard key={s.id} style={s} on={current === s.id} onPick={() => own(s.look)} />)}
        </div>
      </div>

      <div class="look-block">
        <div class="look-head"><strong>Personalizar</strong><span class="faint">{current ? "Parte del estilo elegido; cambia lo que quieras." : following ? "Ahora ves el estilo del evento." : "Tu propia mezcla."}</span></div>
        <Setting title="Fondo de la interfaz" hint="El color de base. «Mi color» acepta cualquiera: las tarjetas y los bordes se calculan solos." stack>
          <div class="swatches" role="group" aria-label="Tema">
            {Object.keys(THEME_SWATCH).map((id) => (
              <Swatch key={id} colors={[THEME_SWATCH[id][0], THEME_SWATCH[id][1]]} label={THEME_NAMES[id]} on={!following && p.theme === id} onPick={() => own({ theme: id })} />
            ))}
            <ColorSwatch value={p.baseColor} label={THEME_NAMES.custom} on={!following && p.theme === "custom"} onPick={(c) => own({ theme: "custom", baseColor: c })} />
          </div>
        </Setting>
        <Setting title="Color de acento" hint="Botones, resaltados y barras. Cada acento trae un color pareja para los degradados." stack>
          <div class="swatches" role="group" aria-label="Acento">
            {Object.keys(ACCENT_SWATCH).map((id) => (
              <Swatch key={id} colors={ACCENT_SWATCH[id]} label={ACCENT_NAMES[id]} on={!following && p.accent === id} onPick={() => own({ accent: id })} />
            ))}
            <ColorSwatch value={p.accentColor} label={ACCENT_NAMES.custom} on={!following && p.accent === "custom"} onPick={(c) => own({ accent: "custom", accentColor: c })} />
          </div>
        </Setting>
        <Setting title="Paneles" hint="Sólidos, de cristal (dejan ver el fondo) o solo con borde." stack>
          <Segmented label="Paneles" value={p.surface} onChange={(v) => own({ surface: v })} options={[["solid", "Sólidos"], ["glass", "Cristal"], ["outline", "Borde"]]} />
        </Setting>
        <Setting title="Letra de los títulos" stack>
          <Segmented label="Letra" value={p.font} onChange={(v) => own({ font: v })} options={[["tech", "Técnica"], ["clean", "Limpia"], ["serif", "Libro"], ["mono", "Consola"]]} />
        </Setting>
        <Setting title="Esquinas" stack>
          <Segmented label="Esquinas" value={p.corners} onChange={(v) => own({ corners: v })} options={[["sharp", "Rectas"], ["round", "Redondas"], ["soft", "Muy redondas"]]} />
        </Setting>
        <Setting title="Detalle del fondo" stack>
          <Segmented label="Fondo" value={p.bg} onChange={(v) => own({ bg: v })} options={[["plain", "Liso"], ["grid", "Cuadrícula"], ["dots", "Puntos"], ["aurora", "Aurora"], ["glow", "Resplandor"]]} />
        </Setting>
      </div>

      <div class="look-block">
        <div class="look-head"><strong>Distribución del evento</strong><span class="faint">Dónde va cada cosa en la pantalla del evento (en el móvil siempre es una columna).</span></div>
        <div class="arrange-grid" role="group" aria-label="Distribución">
          {ARRANGEMENTS.map((a) => <ArrangeCard key={a.id} item={a} on={p.arrange === a.id} />)}
        </div>
      </div>
    </>
  );
}
