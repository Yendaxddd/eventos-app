// A results screen: what the game masters put on everybody's screen after a fight, a chapter or a decision (results.py).
// The same drawing serves the overlay players see, the copy they reopen from the menu and the game masters' live preview.
import { useEffect } from "preact/hooks";
import {
  Crown, Flame, HeartHandshake, Medal, Mountain, Shield, Sparkles, Swords, Timer, Trophy, Wind, X, Zap,
} from "lucide-preact";
import { resultsScreen, resultsOpen } from "../state.js";
import { useEscape } from "../hooks.js";

export const AWARD_ICONS = {
  crown: Crown, swords: Swords, zap: Zap, shield: Shield, "heart-handshake": HeartHandshake, wind: Wind, timer: Timer,
  flame: Flame, mountain: Mountain, sparkles: Sparkles, trophy: Trophy, medal: Medal,
};

function Podium({ block }) {
  const [first, second, third] = block.entries;
  const order = [[second, 2], [first, 1], [third, 3]].filter(([e]) => e && e.name);
  return (
    <div class="rs-podium">
      {order.map(([e, place]) => (
        <div class={`rs-step p${place}`} key={place} style={{ "--d": `${(3 - place) * 120 + 150}ms` }}>
          {place === 1 && <Crown class="rs-crown" size={22} />}
          <strong>{e.name}</strong>
          <span class="num">{e.value}</span>
          <i class="num">{place}</i>
        </div>
      ))}
    </div>
  );
}

function Awards({ block }) {
  return (
    <div class="rs-awards">
      {block.items.map((a, i) => {
        const Icon = AWARD_ICONS[a.icon] || Trophy;
        return (
          <div class="rs-award" key={i} style={{ "--d": `${i * 70 + 250}ms` }}>
            <span class="rs-award-ico"><Icon size={18} /></span>
            <span class="grow"><small>{a.title}</small><strong>{a.name || "—"}</strong></span>
            {a.value && <em class="num">{a.value}</em>}
          </div>
        );
      })}
    </div>
  );
}

function Stats({ block }) {
  if (!block.rows.length) return null;
  return (
    <div class="rs-table-wrap">
      <table class="rs-table">
        <thead><tr><th>Jugador</th>{block.columns.map(([k, label]) => <th key={k} class="num">{label}</th>)}</tr></thead>
        <tbody>{block.rows.map((r, i) => <tr key={i}><td>{r.name}</td>{r.values.map((v, j) => <td key={j} class="num">{v || (v === 0 ? "·" : v)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function List({ block }) {
  return (
    <ul class="rs-list">
      {block.items.map((it, i) => <li key={i}>{it.name && <b>{it.name}</b>}<span>{it.text}</span></li>)}
    </ul>
  );
}

export function ResultsBody({ screen }) {
  return (
    <div class="rs-body">
      <header class="rs-head">
        <span class="rs-eyebrow"><Trophy size={14} /> Resultados</span>
        <h2>{screen.title}</h2>
        {screen.subtitle && <p>{screen.subtitle}</p>}
      </header>
      {screen.blocks.map((b, i) => (
        <section class={`rs-block rs-${b.type}-block`} key={b.id || i} style={{ "--d": `${i * 90}ms` }}>
          {b.title && b.type !== "podium" && <h3>{b.title}</h3>}
          {b.type === "podium" && <Podium block={b} />}
          {b.type === "awards" && <Awards block={b} />}
          {b.type === "stats" && <Stats block={b} />}
          {b.type === "text" && <p class="rs-text">{b.body}</p>}
          {b.type === "list" && <List block={b} />}
        </section>
      ))}
    </div>
  );
}

// The overlay: opens by itself when a game master shows a screen (and follows their edits), closes with ✕ or Escape.
export function ResultsLayer() {
  const screen = resultsScreen.value;
  const open = resultsOpen.value && screen;
  useEscape(() => { if (open) resultsOpen.value = false; });
  useEffect(() => { if (open) document.querySelector(".rs-close")?.focus({ preventScroll: true }); }, [open && screen.id]);
  if (!open) return null;
  return (
    <div class="rs-layer" role="dialog" aria-modal="true" aria-label={`Resultados: ${screen.title}`} data-testid="results-layer" onClick={(e) => { if (e.target === e.currentTarget) resultsOpen.value = false; }}>
      <div class="rs-card" key={screen.id}>
        <button class="btn btn-sm btn-ghost rs-close" type="button" aria-label="Cerrar" onClick={() => { resultsOpen.value = false; }}><X size={16} /></button>
        <ResultsBody screen={screen} />
      </div>
    </div>
  );
}
