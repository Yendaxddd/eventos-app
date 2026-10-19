import { ArrowLeft, Menu, Settings, Swords, Users } from "lucide-preact";
import { channelName, go, back, link, sheet, users, view } from "../state.js";
import { QUALITY } from "../terms.js";

export function ConnBadge() {
  const l = link.value;
  return (
    <button class="conn-badge" type="button" data-q={l.quality} onClick={() => go("latency")} title={`Conexión: ${QUALITY[l.quality]}. Toca para medirla.`} data-testid="conn-badge">
      <span class="dot" />
      <span class="num">{l.median === null ? "—" : `${Math.round(l.median)} ms`}</span>
    </button>
  );
}

const TITLES = { menu: "Menú", settings: "Ajustes", latency: "Prueba de latencia", help: "Ayuda y atajos", profile: "Mi personaje", gm: "Panel del GM" };

export function Topbar({ layout }) {
  const v = view.value;
  const online = users.value.length;
  return (
    <header class="topbar">
      {v === "event"
        ? <button class="icon-btn" type="button" onClick={() => go("menu")} aria-label="Abrir el menú" data-testid="menu-button"><Menu size={22} /></button>
        : <button class="icon-btn" type="button" onClick={back} aria-label="Volver" data-testid="back-button"><ArrowLeft size={22} /></button>}
      <div class="brand">
        <div class="brand-mark"><Swords size={17} /></div>
        <div class="brand-text">
          <strong class="ellipsis" data-testid="channel-name"># {channelName.value}</strong>
          <span>{v === "event" ? `${online} en la Actividad` : TITLES[v] || ""}</span>
        </div>
      </div>
      <div class="spacer" />
      <ConnBadge />
      {v === "event" && layout.mode !== "wide" && (
        <button class="icon-btn" type="button" onClick={() => { sheet.value = "players"; }} aria-label="Ver jugadores" data-testid="players-button"><Users size={20} /></button>
      )}
      <button class={`icon-btn ${v === "settings" ? "is-on" : ""}`} type="button" onClick={() => go("settings")} aria-label="Ajustes" data-testid="settings-button"><Settings size={20} /></button>
    </header>
  );
}
