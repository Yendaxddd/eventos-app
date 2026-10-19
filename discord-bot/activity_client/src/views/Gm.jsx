import { Clapperboard, Database, History, Music, Skull, SlidersHorizontal, Swords, Users } from "lucide-preact";
import { perms } from "../state.js";
import { TabbedPage } from "../ui/Tabbed.jsx";
import { Empty } from "../ui/Common.jsx";
import { EventTab } from "./gm/EventTab.jsx";
import { BossTab } from "./gm/BossTab.jsx";
import { PlayersTab } from "./gm/PlayersTab.jsx";
import { AudioTab } from "./gm/AudioTab.jsx";
import { CinemaTab } from "./gm/CinemaTab.jsx";
import { ValuesTab } from "./gm/ValuesTab.jsx";
import { DataTab } from "./gm/DataTab.jsx";
import { HistoryTab } from "./gm/HistoryTab.jsx";

export const GM_TABS = [
  ["event", "Evento", Swords, EventTab],
  ["boss", "Jefe", Skull, BossTab],
  ["players", "Jugadores", Users, PlayersTab],
  ["audio", "Audio", Music, AudioTab],
  ["cinema", "Cinemáticas", Clapperboard, CinemaTab],
  ["values", "Valores", SlidersHorizontal, ValuesTab],
  ["data", "Contenido", Database, DataTab],
  ["history", "Historial", History, HistoryTab],
];

// The game masters' panel: the same things the bot's commands and hotkeys do, in one place. The server checks the role again on
// every action, so hiding this page from everybody else is only politeness.
export function GmPage() {
  if (!perms.value.gm) {
    return (
      <div class="page" data-testid="gm-denied">
        <div class="page-body"><Empty title="Esto es solo para el equipo de GM">Si deberías tener acceso, pide que te den el rol de game master en el servidor.</Empty></div>
      </div>
    );
  }
  return <TabbedPage tabs={GM_TABS} prefix="gm" label="Secciones del panel del GM" testid="gm" />;
}
