import { Gauge, GraduationCap, LifeBuoy, Settings, Swords } from "lucide-preact";
import { go, link, tutorial, you, version, perms } from "../state.js";
import { QUALITY } from "../terms.js";
import { Avatar } from "../ui/Avatar.jsx";
import { Page } from "../ui/Controls.jsx";

function Tile({ icon: Icon, title, sub, color, glow, onClick, id }) {
  return (
    <button class="tile" type="button" onClick={onClick} style={{ "--tile-color": color, "--tile-glow": glow }} data-testid={`tile-${id}`}>
      <span class="tile-icon"><Icon size={22} /></span>
      <strong>{title}</strong>
      <span class="sub">{sub}</span>
    </button>
  );
}

export function MenuPage() {
  const who = you.value;
  const l = link.value;
  return (
    <Page title="Menú" icon={Swords}>
      <div class="card-2 row" style={{ marginBottom: "var(--sp-4)", gap: "var(--sp-3)" }}>
        <Avatar url={who && who.avatar} name={who ? who.name : "?"} size="lg" />
        <div class="grow">
          <strong class="display" style={{ fontSize: "1.0625rem" }}>{who ? who.name : "—"}</strong>
          <div class="faint" style={{ fontSize: ".8125rem" }}>
            {perms.value.gm ? "Game master · " : ""}Conexión {QUALITY[l.quality].toLowerCase()}{l.median !== null ? ` · ${Math.round(l.median)} ms` : ""}
          </div>
        </div>
        <button class="btn btn-sm" type="button" onClick={() => go("event")}>Volver al evento</button>
      </div>

      <div class="tiles">
        <Tile id="settings" icon={Settings} title="Ajustes" sub="Pantalla, botones de QTE, sonido y chat." color="#a78bfa" glow="rgb(167 139 250 / .5)" onClick={() => go("settings")} />
        <Tile id="latency" icon={Gauge} title="Prueba de latencia" sub="Mide tu conexión y tu dispositivo para ajustar tus tiempos." color="#34d399" glow="rgb(52 211 153 / .5)" onClick={() => go("latency")} />
        <Tile id="tutorial" icon={GraduationCap} title="Tutorial" sub="Aprende a jugar y practica un QTE sin riesgo." color="#fbbf24" glow="rgb(251 191 36 / .5)" onClick={() => { tutorial.value = { active: true, step: 0 }; go("event"); }} />
        <Tile id="help" icon={LifeBuoy} title="Ayuda y atajos" sub="Teclas, reglas de los QTE y datos para soporte." color="#60a5fa" glow="rgb(96 165 250 / .5)" onClick={() => go("help")} />
      </div>

      <p class="faint" style={{ marginTop: "var(--sp-5)", fontSize: ".75rem", textAlign: "center" }}>Eventos App{version.value ? ` ${version.value}` : ""}</p>
    </Page>
  );
}
