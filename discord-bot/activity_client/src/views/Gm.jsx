import { BookOpen, Bug, ClipboardList, Clapperboard, Database, History, Music, ShieldCheck, Skull, SlidersHorizontal, Sparkles, Swords, Users } from "lucide-preact";
import { perms } from "../state.js";
import { TabbedPage } from "../ui/Tabbed.jsx";
import { Empty } from "../ui/Common.jsx";
import { EventTab } from "./gm/EventTab.jsx";
import { BossTab } from "./gm/BossTab.jsx";
import { PlayersTab } from "./gm/PlayersTab.jsx";
import { AudioTab } from "./gm/AudioTab.jsx";
import { CinemaTab } from "./gm/CinemaTab.jsx";
import { FxTab } from "./gm/FxTab.jsx";
import { MobsTab } from "./gm/MobsTab.jsx";
import { ValuesTab } from "./gm/ValuesTab.jsx";
import { DataTab } from "./gm/DataTab.jsx";
import { HistoryTab } from "./gm/HistoryTab.jsx";
import { StaffTab } from "./gm/StaffTab.jsx";
import { ResultsTab } from "./gm/ResultsTab.jsx";
import { SummaryTab } from "./gm/SummaryTab.jsx";

// [id, label, Icon, Component, the boxes that open it (any of them)]
export const GM_TABS = [
  ["event", "Evento", Swords, EventTab, ["event"]],
  ["boss", "Jefe", Skull, BossTab, ["boss"]],
  ["players", "Jugadores", Users, PlayersTab, ["players"]],
  ["mobs", "Enemigos", Bug, MobsTab, ["mobs"]],
  ["results", "Resultados", ClipboardList, ResultsTab, ["results"]],
  ["summary", "Resúmenes", BookOpen, SummaryTab, ["summary"]],
  ["cinema", "Cinemáticas", Clapperboard, CinemaTab, ["cinema", "stage"]],
  ["audio", "Audio", Music, AudioTab, ["media"]],
  ["fx", "Efectos", Sparkles, FxTab, ["media"]],
  ["values", "Valores", SlidersHorizontal, ValuesTab, ["values"]],
  ["data", "Contenido", Database, DataTab, ["content"]],
  ["history", "Historial", History, HistoryTab, ["history"]],
  ["staff", "Equipo", ShieldCheck, StaffTab, ["staff"]],
];

export const allowedGmTabs = () => {
  const can = perms.value.can || [];
  return GM_TABS.filter((t) => t[4].some((b) => can.includes(b)));
};
export const firstGmTab = () => (allowedGmTabs()[0] || GM_TABS[0])[0];

// The game masters' panel: the same things the bot's commands and hotkeys do, in one place. Each person sees the tabs of the boxes the
// host gave them; the server checks the box again on every action, so hiding a tab is only politeness.
export function GmPage() {
  const tabs = allowedGmTabs();
  if (!perms.value.gm || !tabs.length) {
    return (
      <div class="page" data-testid="gm-denied">
        <div class="page-body"><Empty title="Esto es solo para el equipo de GM">Si deberías tener acceso, pide al anfitrión del evento que te añada al equipo.</Empty></div>
      </div>
    );
  }
  return <TabbedPage tabs={tabs} prefix="gm" label="Secciones del panel del GM" testid="gm" />;
}
