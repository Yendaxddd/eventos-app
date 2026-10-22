import { ArrowLeft, Crown, Menu, Music, Settings, Swords, Users, Volume2, VolumeX } from "lucide-preact";
import { channelName, go, back, link, perms, prefs, sheet, users, view } from "../state.js";
import { audioBlocked, music } from "../audio.js";
import { setPrefs } from "../settings-actions.js";
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

// What the game masters are playing, with a button to silence the event's sound for this player (or, if the browser is waiting for a touch, to allow it).
let blockedAtPress = false;      // the tap that unlocks the sound also ends with a click: that click must not turn it off

function NowPlaying() {
  const m = music.value;
  const on = prefs.value.audio;
  if (!m && !audioBlocked.value) return null;
  const title = m ? m.sound.name : "Sonido del evento";
  return (
    <button class={`now-playing ${on ? "" : "is-off"} ${audioBlocked.value ? "is-blocked" : ""}`} type="button" data-testid="now-playing"
      title={audioBlocked.value ? "Toca para activar el sonido" : on ? `Suena: ${title}. Toca para silenciar` : "Sonido del evento apagado. Toca para activarlo"}
      onPointerDown={() => { blockedAtPress = audioBlocked.value; }}
      onClick={() => { if (blockedAtPress || audioBlocked.value) { blockedAtPress = false; if (!on) setPrefs({ audio: true }); return; } setPrefs({ audio: !on }); }}>
      {on ? (audioBlocked.value ? <Volume2 size={16} /> : <Music size={16} />) : <VolumeX size={16} />}
      <span class="ellipsis">{audioBlocked.value ? "Toca para activar el sonido" : title}</span>
    </button>
  );
}

const TITLES = { menu: "Menú", settings: "Ajustes", latency: "Prueba de latencia", training: "Entrenamiento", help: "Ayuda y atajos", panel: "Mi panel", gm: "Panel del GM" };

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
      <NowPlaying />
      <ConnBadge />
      {v === "event" && layout.mode !== "wide" && (
        <button class="icon-btn" type="button" onClick={() => { sheet.value = "players"; }} aria-label="Ver jugadores" data-testid="players-button"><Users size={20} /></button>
      )}
      {v === "event" && layout.mode === "narrow" && perms.value.gm && (
        <button class="icon-btn" type="button" onClick={() => { sheet.value = "gm"; }} aria-label="Mando del GM" data-testid="gm-deck-button"><Crown size={20} /></button>
      )}
      <button class={`icon-btn ${v === "settings" ? "is-on" : ""}`} type="button" onClick={() => go("settings")} aria-label="Ajustes" data-testid="settings-button"><Settings size={20} /></button>
    </header>
  );
}
