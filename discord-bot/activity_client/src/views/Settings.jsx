import { Eye, Gauge, MessagesSquare, Palette, RotateCcw, Shield, Swords, Volume2 } from "lucide-preact";
import { prefs, tutorial, go } from "../state.js";
import { setPrefs, resetPrefs } from "../settings-actions.js";
import { play, vibrate } from "../sound.js";
import { Page, Range, Section, Segmented, Setting, Switch } from "../ui/Controls.jsx";

// How big the floating buttons will be, drawn the way they appear in a QTE.
function Preview() {
  const scale = prefs.value.buttonScale / 100;
  const base = (window.innerWidth <= 720 ? 94 : 104);
  return (
    <div class="qte-preview" aria-hidden="true">
      {[["evade", Shield, "Esquivar", "E"], ["parry", Swords, "Parry", "P"]].map(([kind, Icon, label, key]) => (
        <div class="qw static" data-kind={kind} data-state="live" data-lead="false" key={kind} style={{ "--btn-base": `${base}px` }}>
          <div class="qw-timer"><div class="qw-track"><i class="qw-fill" style={{ animation: "none" }} /></div><span class="qw-secs num">2.4</span></div>
          <div class="qw-btn" style={{ animation: "none" }}><Icon strokeWidth={2.4} /><span>{label}</span><span class="kbd">{key}</span></div>
        </div>
      ))}
      <span class="faint" style={{ alignSelf: "center", fontSize: ".75rem" }}>{Math.round(scale * 100)} %</span>
    </div>
  );
}

export function SettingsPage() {
  const p = prefs.value;
  return (
    <Page title="Ajustes" icon={Palette} actions={<button class="btn btn-sm btn-ghost" type="button" onClick={resetPrefs}><RotateCcw size={14} /> Restablecer</button>}>
      <Section title="Pantalla">
        <Setting title="Tema" hint="Muy oscuro ahorra batería en pantallas OLED; alto contraste ayuda si cuesta leer." stack>
          <Segmented label="Tema" value={p.theme} onChange={(v) => setPrefs({ theme: v })} options={[["dark", "Oscuro"], ["oled", "Muy oscuro"], ["contrast", "Alto contraste"]]} />
        </Setting>
        <Setting title="Colores del juego" hint="La opción para daltonismo cambia verde y amarillo por azul y naranja." stack>
          <Segmented label="Paleta" value={p.palette} onChange={(v) => setPrefs({ palette: v })} options={[["default", "Estándar"], ["cb", "Daltonismo"]]} />
        </Setting>
        <Setting title="Tamaño del texto" stack>
          <Range label="Tamaño del texto" min={85} max={140} step={5} value={p.textScale} onChange={(v) => setPrefs({ textScale: v })} format={(v) => `${v} %`} />
        </Setting>
        <Setting title="Espaciado" hint="Cuánto aire hay entre los elementos." stack>
          <Segmented label="Espaciado" value={p.density} onChange={(v) => setPrefs({ density: v })} options={[["compact", "Compacto"], ["comfortable", "Cómodo"], ["spacious", "Amplio"]]} />
        </Setting>
        <Setting title="Animaciones" hint="Reducidas quita los efectos de movimiento. Los temporizadores de los QTE siguen funcionando." stack>
          <Segmented label="Animaciones" value={p.motion} onChange={(v) => setPrefs({ motion: v })} options={[["full", "Normales"], ["reduced", "Reducidas"]]} />
        </Setting>
      </Section>

      <Section title="Botones de los QTE">
        <Preview />
        <Setting title="Tamaño de los botones" stack>
          <Range label="Tamaño de los botones" min={70} max={160} step={5} value={p.buttonScale} onChange={(v) => setPrefs({ buttonScale: v })} format={(v) => `${v} %`} />
        </Setting>
        <Setting title="Dónde aparecen" hint="Al azar por la pantalla, o siempre en el mismo borde (más cómodo con una mano)." stack>
          <Segmented label="Posición" value={p.buttonPlacement} onChange={(v) => setPrefs({ buttonPlacement: v })}
            options={[["random", "Al azar"], ["bottom", "Abajo"], ["left", "Izquierda"], ["right", "Derecha"]]} />
        </Setting>
        <Setting title="Mantener «Esquivar» durante el parry" hint="Mientras la ventana de parry está abierta, deja un botón pequeño para esquivar.">
          <Switch label="Mantener esquivar" checked={p.keepEvade} onChange={(v) => setPrefs({ keepEvade: v })} />
        </Setting>
        <Setting title="Un QTE a la vez" hint="Muestra solo el más urgente; los demás esperan en cola. Sus tiempos siguen corriendo.">
          <Switch label="Un QTE a la vez" checked={p.queueMode} onChange={(v) => setPrefs({ queueMode: v })} />
        </Setting>
      </Section>

      <Section title="Sonido y vibración">
        <Setting title="Sonidos">
          <button class="btn btn-sm btn-ghost" type="button" onClick={() => { play("qte"); setTimeout(() => play("parry"), 350); setTimeout(() => play("ok"), 700); }}><Volumen /> Probar</button>
          <Switch label="Sonidos" checked={p.sound} onChange={(v) => setPrefs({ sound: v })} />
        </Setting>
        <Setting title="Volumen" stack>
          <Range label="Volumen" min={0} max={100} step={5} value={p.volume} disabled={!p.sound} onChange={(v) => setPrefs({ volume: v })} format={(v) => `${v} %`} />
        </Setting>
        <Setting title="Vibración" hint="En el móvil, un toque corto cuando llega un QTE.">
          <button class="btn btn-sm btn-ghost" type="button" onClick={() => vibrate([40, 60, 40])}>Probar</button>
          <Switch label="Vibración" checked={p.haptics} onChange={(v) => setPrefs({ haptics: v })} />
        </Setting>
      </Section>

      <Section title="Chat">
        <Setting title="Mostrar fotos de perfil"><Switch label="Fotos de perfil" checked={p.showAvatars} onChange={(v) => setPrefs({ showAvatars: v })} /></Setting>
        <Setting title="Mostrar la hora de cada mensaje"><Switch label="Hora" checked={p.showTimestamps} onChange={(v) => setPrefs({ showTimestamps: v })} /></Setting>
        <Setting title="Cargar imágenes solas" hint="Si lo apagas, cada imagen se carga al tocarla (ahorra datos)."><Switch label="Imágenes" checked={p.showMedia} onChange={(v) => setPrefs({ showMedia: v })} /></Setting>
        <Setting title="Panel de jugadores" hint="En pantallas anchas, la columna con la vida del equipo."><Switch label="Panel de jugadores" checked={p.showPlayers} onChange={(v) => setPrefs({ showPlayers: v })} /></Setting>
        <Setting title="Mensajes en pantalla" hint="Cuántos mensajes se guardan. Menos mensajes, menos carga en móviles lentos." stack>
          <Range label="Mensajes en pantalla" min={50} max={400} step={10} value={p.messageLimit} onChange={(v) => setPrefs({ messageLimit: v })} format={(v) => `${v}`} />
        </Setting>
      </Section>

      <Section title="Más">
        <Setting title="Prueba de latencia" hint="Mide tu conexión y tu dispositivo para ajustar tus tiempos."><button class="btn btn-sm" type="button" onClick={() => go("latency")}><Gauge size={14} /> Medir</button></Setting>
        <Setting title="Tutorial" hint="Repite la explicación con práctica."><button class="btn btn-sm" type="button" onClick={() => { tutorial.value = { active: true, step: 0 }; go("event"); }}><Eye size={14} /> Ver</button></Setting>
        <Setting title="Ayuda y atajos de teclado"><button class="btn btn-sm" type="button" onClick={() => go("help")}><MessagesSquare size={14} /> Abrir</button></Setting>
      </Section>
    </Page>
  );
}

const Volumen = () => <Volume2 size={14} />;
