// Getting around: the bar at the bottom of a phone, the shortcuts in the top bar of a computer, and «Ir a…» (Ctrl+K, or /) that
// finds any page or panel tab by typing a few letters.
import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { signal } from "@preact/signals";
import { Crown, Dumbbell, LayoutGrid, Search, Swords, UserRound } from "lucide-preact";
import { go, perms, tutorial, view, viewArgs } from "../state.js";
import { DESTINATIONS, navSection, searchDestinations } from "../nav.js";
import { cx } from "../util.js";

export const palette = signal(false);

export function goTo(d) {
  palette.value = false;
  if (d.view === "tutorial") { tutorial.value = { active: true, step: 0 }; go("event"); return; }
  go(d.view, d.tab ? { tab: d.tab } : null);
}

const ITEMS = [
  ["event", "Evento", Swords, () => go("event")],
  ["panel", "Mi panel", UserRound, () => go("panel", { tab: "summary" })],
  ["training", "Entrenar", Dumbbell, () => go("training")],
  ["gm", "GM", Crown, () => go("gm", { tab: "event" }), true],
  ["more", "Más", LayoutGrid, () => go("menu")],
];

// A phone: the main places one tap away, at the bottom where the thumb is.
export function BottomNav() {
  const here = navSection(view.value, viewArgs.value && viewArgs.value.tab);
  return (
    <nav class="bottom-nav" aria-label="Navegación" data-testid="bottom-nav">
      {ITEMS.filter((it) => !it[4] || perms.value.gm).map(([id, label, Icon, open]) => (
        <button key={id} type="button" class={cx("bn-item", here === id && "on")} aria-current={here === id ? "page" : undefined} onClick={open} data-testid={`nav-${id}`}>
          <Icon size={21} /><span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

// A computer: the same places as buttons in the top bar, and the search.
export function TopNav() {
  const here = navSection(view.value, viewArgs.value && viewArgs.value.tab);
  return (
    <nav class="top-nav" aria-label="Navegación" data-testid="top-nav">
      {ITEMS.filter((it) => it[0] !== "more" && (!it[4] || perms.value.gm)).map(([id, label, Icon, open]) => (
        <button key={id} type="button" class={cx("tn-item", here === id && "on")} aria-current={here === id ? "page" : undefined} onClick={open} data-testid={`topnav-${id}`}>
          <Icon size={16} /><span>{label}</span>
        </button>
      ))}
      <button type="button" class="tn-search" onClick={() => { palette.value = true; }} aria-label="Ir a… (Ctrl+K)" title="Ir a… (Ctrl+K)" data-testid="open-palette">
        <Search size={15} /><span>Ir a…</span><kbd class="kbd">Ctrl K</kbd>
      </button>
    </nav>
  );
}

export function installPaletteKeys() {
  document.addEventListener("keydown", (e) => {
    const target = e.target;
    const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "k" || e.key === "K")) { e.preventDefault(); palette.value = !palette.value; return; }
    if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey) { e.preventDefault(); palette.value = true; }
  });
}

// «Ir a…»: type, move with the arrows, Enter to go.
export function Palette() {
  if (!palette.value) return null;
  return <PaletteBox />;
}

function PaletteBox() {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef(null);
  const found = searchDestinations(query, { gm: perms.value.gm }).filter((d) => d.view !== "menu" || !query);
  const pick = Math.min(index, Math.max(0, found.length - 1));
  useLayoutEffect(() => { input.current && input.current.focus(); }, []);          // at once: the first letters typed must land in it
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIndex((pick + 1) % Math.max(1, found.length)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((pick - 1 + found.length) % Math.max(1, found.length)); }
    else if (e.key === "Enter" && found[pick]) { e.preventDefault(); goTo(found[pick]); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); palette.value = false; }
  };
  return (
    <>
      <div class="scrim" onClick={() => { palette.value = false; }} />
      <div class="palette" role="dialog" aria-modal="true" aria-label="Ir a…" data-testid="palette">
        <div class="palette-input"><Search size={18} />
          <input ref={input} autoFocus class="input" value={query} placeholder="¿Adónde quieres ir? (inventario, ajustes, jefe…)" onInput={(e) => { setQuery(e.currentTarget.value); setIndex(0); }} onKeyDown={onKey}
            role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={found[pick] ? `pal-${found[pick].id}` : undefined} data-testid="palette-input" />
        </div>
        <ul class="palette-list" id="palette-list" role="listbox">
          {found.length === 0 && <li class="faint palette-empty">Nada con ese nombre.</li>}
          {found.map((d, i) => (
            <li key={d.id} id={`pal-${d.id}`} role="option" aria-selected={i === pick ? "true" : "false"} class={cx(i === pick && "on")}
              onMouseEnter={() => setIndex(i)} onClick={() => goTo(d)} data-testid={`pal-${d.id}`}>
              <span>{d.label}</span>{d.gm && <span class="chip">GM</span>}
            </li>
          ))}
        </ul>
        <p class="faint palette-hint">↑ ↓ para moverte · Enter para ir · Esc para cerrar</p>
      </div>
    </>
  );
}

export { DESTINATIONS };
