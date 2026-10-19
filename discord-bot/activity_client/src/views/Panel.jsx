import { Backpack, Drama, GitBranch, Image as ImageIcon, LayoutDashboard, Medal, Trophy } from "lucide-preact";
import { TabbedPage } from "../ui/Tabbed.jsx";
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
  return <TabbedPage tabs={TABS} prefix="dash" label="Secciones de tu panel" testid="panel" />;
}
