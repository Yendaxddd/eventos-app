import { useEffect } from "preact/hooks";
import { openTab, viewArgs } from "../state.js";

// A page of tabs: a column on the left on a computer, a row on top on a phone (it scrolls sideways).
// `tabs` is [[id, label, Icon, Component]]; the chosen one lives in the view's arguments, so Back and the menu keep working.
export function TabbedPage({ tabs, prefix, label, testid }) {
  const current = (viewArgs.value && viewArgs.value.tab) || tabs[0][0];
  const found = tabs.find(([id]) => id === current) || tabs[0];
  const Body = found[3];
  useEffect(() => {                                   // on a phone the tabs scroll sideways: keep the chosen one in view
    const el = document.getElementById(`${prefix}-tab-${found[0]}`);
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
  }, [found[0]]);
  useEffect(() => {                                   // a new page: the keyboard starts on its chosen tab
    if (document.querySelector(".modal-card, .palette")) return;
    const el = document.getElementById(`${prefix}-tab-${found[0]}`);
    if (el) el.focus({ preventScroll: true });
  }, [prefix]);
  const move = (e, index) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = tabs[(index + step + tabs.length) % tabs.length];
    openTab(next[0]);
    requestAnimationFrame(() => document.querySelector(`[data-testid="${prefix}-tab-${next[0]}"]`)?.focus());
  };
  return (
    <div class="page dash-page" data-testid={testid}>
      <div class="dash">
        <nav class="dash-nav" role="tablist" aria-label={label} aria-orientation="vertical">
          {tabs.map(([id, text, Icon], index) => (
            <button key={id} type="button" role="tab" id={`${prefix}-tab-${id}`} class="dash-tab" aria-selected={id === found[0] ? "true" : "false"} aria-controls={`${prefix}-body`}
              tabIndex={id === found[0] ? 0 : -1} data-testid={`${prefix}-tab-${id}`} onClick={() => openTab(id)} onKeyDown={(e) => move(e, index)}>
              <Icon size={19} /><span>{text}</span>
            </button>
          ))}
        </nav>
        <div class="dash-body" id={`${prefix}-body`} role="tabpanel" aria-labelledby={`${prefix}-tab-${found[0]}`} data-tab={found[0]}>
          <Body />
        </div>
      </div>
    </div>
  );
}
