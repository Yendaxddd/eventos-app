// What is on a player (or the boss) right now: bleeding, burning, a shield, a damage boost... each with its countdown.
import { useNow } from "../hooks.js";
import { popsFor } from "../hits.js";
import { cx } from "../util.js";

export const STATUS = {
  bleed: ["🩸", "Sangrado", "Pierdes vida cada segundo (más por acumulación)", "bad"],
  burn: ["🔥", "Quemadura", "Pierdes vida cada segundo", "bad"],
  poison: ["☠️", "Veneno", "Pierdes vida poco a poco (se acumula)", "bad"],
  weakened: ["🥀", "Debilitado", "Haces menos daño", "bad"],
  stunned: ["💫", "Aturdido", "No puedes reaccionar a los QTE", "bad"],
  cursed: ["🕯️", "Maldito", "Ganas menos carga de poder", "bad"],
  damage_boost: ["⚔️", "Más daño", "", "good"],
  bf_boost: ["⚡", "Más Black Flash", "", "good"],
  shield: ["🛡️", "Escudo", "", "good"],
};

function label(e) {
  const [, name] = STATUS[e.kind] || ["", e.kind];
  if (e.kind === "shield") return `${name} ${Math.round(e.value)} %`;
  if (e.kind === "damage_boost" || e.kind === "bf_boost") return `${name} +${Math.round(e.value)} %`;
  return e.stacks > 1 ? `${name} ×${e.stacks}` : name;
}

// chips with a countdown (the player's own effects and boosts, with local times `at`)
export function EffectChips({ effects = [], buffs = [], compact = false }) {
  const all = [...effects, ...buffs];
  const now = useNow(500, all.length > 0);
  if (!all.length) return null;
  return (
    <div class={cx("effect-chips", compact && "compact")} data-testid="effects">
      {all.map((e) => {
        const [icon, , hint, tone] = STATUS[e.kind] || ["✨", e.kind, "", "info"];
        const left = e.at ? Math.max(0, Math.ceil((e.at - now) / 1000)) : null;
        return (
          <span key={e.kind} class={cx("effect-chip", tone)} title={hint || label(e)} data-kind={e.kind}>
            <i aria-hidden="true">{icon}</i>{!compact && <b>{label(e)}</b>}
            <em class="num">{left !== null ? `${left} s` : e.kind === "shield" || e.kind.endsWith("boost") ? "1 golpe" : ""}</em>
          </span>
        );
      })}
    </div>
  );
}

// just the icons (another player in the list, the boss)
export function EffectIcons({ kinds = [] }) {
  if (!kinds.length) return null;
  return <span class="effect-icons" aria-label={kinds.map((k) => (STATUS[k] || ["", k])[1]).join(", ")}>{kinds.map((k) => <i key={k}>{(STATUS[k] || ["✨"])[0]}</i>)}</span>;
}

// the numbers rising over something when its HP changes
export function Pops({ target }) {
  const list = popsFor(target);
  if (!list.length) return null;
  return (
    <span class="hp-pops" aria-hidden="true">
      {list.map((p) => <b key={p.key} class={cx("hp-pop num", p.amount > 0 ? "heal" : "dmg")}>{p.amount > 0 ? `+${p.amount}` : p.amount}</b>)}
    </span>
  );
}
