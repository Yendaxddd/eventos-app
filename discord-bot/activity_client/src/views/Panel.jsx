import { useEffect } from "preact/hooks";
import { Backpack, Drama, GitBranch, Image as ImageIcon, LayoutDashboard, Medal, Trophy } from "lucide-preact";
import { openTab, viewArgs } from "../state.js";
import { cx } from "../util.js";
import { SummaryTab } from "./panel/Summary.jsx";
import { AchievementsTab } from "./panel/Achievements.jsx";
import { CharactersTab } from "./panel/Characters.jsx";
import { SkillsTab } from "./panel/Skills.jsx";
import { InventoryTab } from "./panel/Inventory.jsx";
import { ImagesTab } from "./panel/Images.jsx";
import { RankingTab } from "./panel/Ranking.jsx";

export const TABS = [
  ["summary", "Resumen", LayoutDashboard, SummaryTab],
  ["achievements", "Logros", Trophy, AchievementsTab],
  ["characters", "Personajes", Drama, CharactersTab],
  ["skills", "Habilidades", GitBranch, SkillsTab],
  ["inventory", "Inventario", Backpack, InventoryTab],
  ["images", "Imágenes", ImageIcon, ImagesTab],
  ["ranking", "Ranking", Medal, RankingTab],
];

// «Mi panel»: everything the old /dashboard (and /skills, /achievements, /inventory, /leaderboard...) showed, in one place.
export function PanelPage() {
  const current = (viewArgs.value && viewArgs.value.tab) || "summary";
  const found = TABS.find(([id]) => id === current) || TABS[0];
  const Body = found[3];
  useEffect(() => {                                   // on a phone the tabs scroll sideways: keep the chosen one in view
    const el = document.getElementById(`dash-tab-${found[0]}`);
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
  }, [found[0]]);
  const move = (e, index) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = TABS[(index + step + TABS.length) % TABS.length];
    openTab(next[0]);
    requestAnimationFrame(() => document.querySelector(`[data-testid="dash-tab-${next[0]}"]`)?.focus());
  };
  return (
    <div class="page dash-page" data-testid="panel">
      <div class="dash">
        <nav class="dash-nav" role="tablist" aria-label="Secciones de tu panel" aria-orientation="vertical">
          {TABS.map(([id, label, Icon], index) => (
            <button key={id} type="button" role="tab" id={`dash-tab-${id}`} class="dash-tab" aria-selected={id === found[0] ? "true" : "false"} aria-controls="dash-body"
              tabIndex={id === found[0] ? 0 : -1} data-testid={`dash-tab-${id}`} onClick={() => openTab(id)} onKeyDown={(e) => move(e, index)}>
              <Icon size={19} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div class={cx("dash-body")} id="dash-body" role="tabpanel" aria-labelledby={`dash-tab-${found[0]}`} data-tab={found[0]}>
          <Body />
        </div>
      </div>
    </div>
  );
}
