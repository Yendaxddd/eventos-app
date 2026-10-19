import { Crosshair, Orbit, Sparkles, Zap } from "lucide-preact";
import { activeAs, canWrite, me, you } from "../state.js";
import { send } from "../net.js";
import { useNow } from "../hooks.js";
import { cx } from "../util.js";
import { KEYS } from "../terms.js";

const seconds = (at, now) => (at ? Math.max(0, (at - now) / 1000) : 0);

// The commands that are not an answer to one QTE: adapt, counter-attack, powers, domain.
export function pressCommand(command) {
  send({ t: "press", id: "", command, as: activeAs.value });
}

export function Actions({ variant = "grid" }) {
  const now = useNow(250);
  const m = me.value || {};
  const as = activeAs.value;
  const open = canWrite.value && !!you.value;
  const powers = (m.powers && m.powers[as]) || {};
  const counterLeft = seconds(m.counterAt, now);

  const items = [];
  items.push({ cmd: "adapt", cls: "act-adapt", icon: Sparkles, label: "Adaptar", sub: "", key: KEYS.adapt });
  items.push({ cmd: "attack", cls: "act-attack", icon: Crosshair, label: "Ataque", sub: counterLeft > 0 ? `¡ya! ${counterLeft.toFixed(1)} s` : "tras esquivar", key: KEYS.attack, hot: counterLeft > 0 });
  for (const [n, slot] of [[1, "power1"], [2, "power2"]]) {
    const info = powers[slot];
    if (as !== "me" && !info) continue;                                  // that character has no such power
    const pct = m.charges ? m.charges[slot] : null;
    const left = info ? seconds(info.at, now) : 0;
    const ready = pct !== null && pct >= (m.cost || 100) && left <= 0 && !(info && info.paused);
    const sub = left > 0 ? `${Math.ceil(left)} s` : info && info.paused ? `en pausa ${info.paused} s` : pct !== null && pct !== undefined ? `${Math.round(pct)} %` : "";
    items.push({ cmd: slot, cls: "act-power", icon: Zap, label: info ? info.name : `Poder ${n}`, sub, key: String(n), ready });
  }
  if (m.domain) items.push({ cmd: "domain", cls: "act-domain", icon: Orbit, label: "Dominio", sub: "Expansión", key: KEYS.domain });

  return (
    <div class={variant === "bar" ? "action-bar" : "actions"} data-testid="actions">
      {items.map(({ cmd, cls, icon: Icon, label, sub, key, ready, hot }) => (
        <button key={cmd} type="button" class={cx("act", cls, ready && "ready", hot && "hot")} data-cmd={cmd} disabled={!open}
          onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button !== 0) return; e.preventDefault(); pressCommand(cmd); }}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pressCommand(cmd); } }}>
          <span class="a-top"><span class="a-ico"><Icon size={17} /></span>{variant === "grid" && <span class="a-key kbd">{key}</span>}</span>
          <span class="a-txt"><b>{label}</b><small class="num">{sub}</small></span>
        </button>
      ))}
    </div>
  );
}
