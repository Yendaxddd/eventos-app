import { Backpack, Crown, Drama, Dumbbell, Gauge, GitBranch, GraduationCap, Image as ImageIcon, LifeBuoy, Medal, Settings, Sparkles, Swords, Trophy, UserRound } from "lucide-preact";
import { go, link, tutorial, you, version, perms } from "../state.js";
import { QUALITY } from "../terms.js";
import { Avatar } from "../ui/Avatar.jsx";
import { Page, Section } from "../ui/Controls.jsx";

function Tile({ icon: Icon, title, sub, color, onClick, id }) {
  return (
    <button class="tile" type="button" onClick={onClick} style={{ "--tile-color": color, "--tile-glow": `color-mix(in srgb, ${color} 50%, transparent)` }} data-testid={`tile-${id}`}>
      <span class="tile-icon"><Icon size={22} /></span>
      <strong>{title}</strong>
      <span class="sub">{sub}</span>
    </button>
  );
}

// the player's own things: each opens its tab of «Mi panel»
const MINE = [
  ["summary", "Mi perfil", "Tus estadísticas, cargas y tiempos.", UserRound, "#a78bfa"],
  ["achievements", "Logros", "Títulos, dominios y lo que te falta.", Trophy, "#fbbf24"],
  ["characters", "Personajes", "Regístralos y crea sus poderes.", Drama, "#f472b6"],
  ["skills", "Habilidades", "Gasta tus puntos en el árbol.", GitBranch, "#34d399"],
  ["inventory", "Inventario", "Objetos especiales y su progreso.", Backpack, "#fb923c"],
  ["images", "Imágenes", "Las que salen cuando contraatacas.", ImageIcon, "#60a5fa"],
  ["effects", "Mis efectos", "Cómo se ve lo que te pasa a ti.", Sparkles, "#c084fc"],
  ["ranking", "Ranking", "Quién va primero en cada cosa.", Medal, "#fb7185"],
];

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

      <Section title="Mi personaje">
        <div class="tiles">
          {MINE.map(([tab, title, sub, Icon, color]) => (
            <Tile key={tab} id={tab} icon={Icon} title={title} sub={sub} color={color} onClick={() => go("panel", { tab })} />
          ))}
        </div>
      </Section>

      {perms.value.gm && (
        <Section title="Equipo de GM">
          <div class="tiles">
            <Tile id="gm" icon={Crown} title="Panel del GM" sub="Lanza QTE, controla al jefe, a los jugadores, los valores y el contenido." color="#f472b6" onClick={() => go("gm", { tab: "event" })} />
          </div>
        </Section>
      )}

      <Section title="La Actividad">
        <div class="tiles">
          <Tile id="settings" icon={Settings} title="Ajustes" sub="Pantalla, botones de QTE, sonido y chat." color="#a78bfa" onClick={() => go("settings")} />
          <Tile id="latency" icon={Gauge} title="Prueba de latencia" sub="Mide tu conexión y tu dispositivo para ajustar tus tiempos." color="#34d399" onClick={() => go("latency")} />
          <Tile id="training" icon={Dumbbell} title="Entrenamiento" sub="QTE al azar con el tipo, la dificultad y el ritmo que elijas." color="#fb923c" onClick={() => go("training")} />
          <Tile id="tutorial" icon={GraduationCap} title="Tutorial" sub="Aprende a jugar y practica un QTE sin riesgo." color="#fbbf24" onClick={() => { tutorial.value = { active: true, step: 0 }; go("event"); }} />
          <Tile id="help" icon={LifeBuoy} title="Ayuda y atajos" sub="Teclas, reglas de los QTE y datos para soporte." color="#60a5fa" onClick={() => go("help")} />
        </div>
      </Section>

      <p class="faint" style={{ marginTop: "var(--sp-5)", fontSize: ".75rem", textAlign: "center" }}>Eventos App{version.value ? ` ${version.value}` : ""}</p>
    </Page>
  );
}
