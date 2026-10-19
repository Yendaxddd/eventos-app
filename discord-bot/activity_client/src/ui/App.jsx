import { Loader2, Swords, TriangleAlert } from "lucide-preact";
import { conn, pip, sheet, view, prefs } from "../state.js";
import { useLayout } from "../hooks.js";
import { Topbar } from "./Topbar.jsx";
import { Banner, FxLayer, Sheet, Toasts } from "./Overlays.jsx";
import { Feed } from "./Feed.jsx";
import { Composer } from "./Composer.jsx";
import { BossCard, MeCard, MiniHud, PlayersPanel, RightPanel } from "./Hud.jsx";
import { Actions } from "./Actions.jsx";
import { QteLayer } from "./QteLayer.jsx";
import { MenuPage } from "../views/Menu.jsx";
import { SettingsPage } from "../views/Settings.jsx";
import { HelpPage } from "../views/Help.jsx";
import { LatencyPage } from "../views/Latency.jsx";
import { PanelPage } from "../views/Panel.jsx";
import { GmPage } from "../views/Gm.jsx";
import { TutorialHost } from "../views/Tutorial.jsx";

function Splash() {
  const c = conn.value;
  const bad = c.state === "error";
  return (
    <div class={`splash ${bad ? "error" : ""}`} data-testid="splash">
      <div class="splash-card">
        <div class="splash-logo">{bad ? <TriangleAlert size={34} /> : <Swords size={34} />}</div>
        <h1>{bad ? c.text : "Entrando al evento"}</h1>
        <p>{bad ? c.detail || "No se pudo conectar con el evento." : "Preparando tu pantalla…"}</p>
        {!bad && <Loader2 class="spin-icon" size={22} />}
      </div>
    </div>
  );
}

function EventView({ layout }) {
  const p = prefs.value;
  const wide = layout.mode === "wide", narrow = layout.mode === "narrow";
  return (
    <div class="stage" data-layout={layout.mode} data-short={layout.short ? "true" : "false"} data-players={wide && p.showPlayers ? "true" : "false"}>
      {wide && p.showPlayers && <PlayersPanel />}
      <div class="center">
        <BossCard />
        {narrow && <MiniHud />}
        <div class="arena" data-arena>
          <Feed />
          <Composer />
        </div>
        {narrow && <Actions variant="bar" />}
      </div>
      {!narrow && <RightPanel />}
    </div>
  );
}

function Pages({ layout }) {
  const v = view.value;
  return (
    <div class="stage" data-layout={layout.mode} data-short={layout.short ? "true" : "false"} data-page="true">
      {v === "menu" && <MenuPage />}
      {v === "settings" && <SettingsPage />}
      {v === "latency" && <LatencyPage />}
      {v === "help" && <HelpPage />}
      {v === "panel" && <PanelPage />}
      {v === "gm" && <GmPage />}
    </div>
  );
}

// Discord's floating window: just what matters while playing from another channel (the QTE buttons come from the layer)
function PipView() {
  return (
    <div class="app pip-view" data-view="pip">
      <div class="pip-body">
        <BossCard />
        <MiniHud />
        <Actions variant="bar" />
      </div>
    </div>
  );
}

export function App() {
  const layout = useLayout();
  if (conn.value.state !== "connected") return <Splash />;
  if (pip.value) return <><PipView /><QteLayer /><Toasts /><FxLayer /></>;
  const v = view.value;
  return (
    <>
      <div class="app" data-view={v}>
        <Topbar layout={layout} />
        <Banner />
        {v === "event" ? <EventView layout={layout} /> : <Pages layout={layout} />}
      </div>
      <QteLayer />
      {sheet.value === "players" && (
        <Sheet title="Jugadores y tú" onClose={() => { sheet.value = null; }}>
          <div class="col" style={{ gap: "var(--sp-4)" }}>
            <div class="card-2"><MeCard /></div>
            <PlayersPanel />
          </div>
        </Sheet>
      )}
      <Toasts />
      <FxLayer />
      <TutorialHost />
    </>
  );
}
