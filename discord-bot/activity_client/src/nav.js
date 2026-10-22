// Every place of the Activity in one list: the bottom bar, the top bar, the menu and the «Ir a…» search all read it, so nothing is
// reachable from one and lost from the others. Pure data and a search function (tested without a browser).

// [id, label, words people may type, view, tab, gm only]
export const DESTINATIONS = [
  ["event", "Evento", "chat canal combate partida jugar inicio", "event", null, false],
  ["summary", "Mi perfil", "panel estadísticas stats cargas tiempos resumen", "panel", "summary", false],
  ["achievements", "Logros", "títulos dominios medallas", "panel", "achievements", false],
  ["characters", "Personajes", "registrar poderes creador de poderes tupperbox", "panel", "characters", false],
  ["skills", "Habilidades", "árbol puntos ramas", "panel", "skills", false],
  ["inventory", "Inventario", "objetos equipo adaptación espejo efectos", "panel", "inventory", false],
  ["images", "Imágenes", "contraataque gif", "panel", "images", false],
  ["ranking", "Ranking", "clasificación tabla líderes", "panel", "ranking", false],
  ["training", "Entrenamiento", "practicar práctica qte al azar", "training", null, false],
  ["latency", "Prueba de latencia", "ping retraso conexión dispositivo calibrar", "latency", null, false],
  ["settings", "Ajustes", "opciones tema sonido botones accesibilidad tamaño", "settings", null, false],
  ["help", "Ayuda y atajos", "teclas reglas soporte", "help", null, false],
  ["tutorial", "Tutorial", "aprender cómo se juega", "tutorial", null, false],
  ["menu", "Menú", "todo más", "menu", null, false],
  ["gm-event", "GM · Evento", "lanzar qte combate checkpoint", "gm", "event", true],
  ["gm-boss", "GM · Jefe", "boss habilidades dominio", "gm", "boss", true],
  ["gm-players", "GM · Jugadores", "vida hp cargas puntos objetos dar quitar", "gm", "players", true],
  ["gm-mobs", "GM · Enemigos", "mini enemigos bestiario mobs", "gm", "mobs", true],
  ["gm-audio", "GM · Audio", "música sonidos biblioteca", "gm", "audio", true],
  ["gm-fx", "GM · Efectos", "vfx efectos visuales poderes", "gm", "fx", true],
  ["gm-cinema", "GM · Cinemáticas", "escenas diálogo editor", "gm", "cinema", true],
  ["gm-values", "GM · Valores", "números tiempos ventanas", "gm", "values", true],
  ["gm-data", "GM · Contenido", "archivos objetos logros árboles aprobar", "gm", "data", true],
  ["gm-history", "GM · Historial", "registro cambios", "gm", "history", true],
].map(([id, label, words, view, tab, gm]) => ({ id, label, words, view, tab, gm }));

const fold = (text) => String(text || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

// The places that match what was typed (every word somewhere in the name or its words), the best first: names that start with it,
// then names that contain it, then the rest. Game-master places only for game masters.
export function searchDestinations(query, { gm = false, list = DESTINATIONS } = {}) {
  const pool = list.filter((d) => gm || !d.gm);
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return pool;
  const scored = [];
  for (const d of pool) {
    const name = fold(d.label), all = `${name} ${fold(d.words)}`;
    if (!words.every((w) => all.includes(w))) continue;
    const score = name.startsWith(words[0]) ? 0 : name.includes(words[0]) ? 1 : 2;
    scored.push([score, d]);
  }
  return scored.sort((a, b) => a[0] - b[0]).map((x) => x[1]);
}

// Which bottom-bar item a view belongs to.
export function navSection(view, tab) {
  if (view === "event") return "event";
  if (view === "panel") return "panel";
  if (view === "training") return "training";
  if (view === "gm") return "gm";
  return "more";
}
