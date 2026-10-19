import { Backpack, Check, Circle, Gem, Lock, Package } from "lucide-preact";
import { Bar } from "../../ui/Hud.jsx";
import { Block, Empty, Pill } from "../../ui/Common.jsx";
import { usePanel } from "../../panel/data.js";
import { OBJECT_TYPE, TRACK_LABEL, plural, rarityOf, readable } from "../../panel/format.js";
import { cdn } from "../../util.js";

// one line of adaptation: how many spins, how far the next step is, and what each step gives
function Track({ row }) {
  const target = row.next ?? row.max ?? Math.max(row.spins, 1);
  const done = row.next === null && row.max !== null;
  return (
    <div class="track" data-testid={`track-${row.key}`}>
      <div class="track-head">
        <strong>{TRACK_LABEL[row.key] || row.key}</strong>
        {done ? <Pill tone="ok" icon={Check}>Completo</Pill> : row.next !== null ? <Pill tone="info">Siguiente: {row.next}</Pill> : null}
        <span class="num">{row.spins}{row.max !== null ? ` / ${row.max}` : ""}</span>
      </div>
      <Bar kind="charge" value={Math.min(row.spins, target)} max={target} thin ready={done} />
      {row.steps.length > 0 && (
        <details class="steps">
          <summary>Ver las recompensas ({row.steps.filter((s) => s.done).length} de {row.steps.length})</summary>
          <ul>
            {row.steps.map((s) => (
              <li key={s.spins} data-done={s.done ? "1" : "0"}>
                <span class="step-mark" aria-hidden="true">{s.done ? <Check size={14} /> : <Circle size={12} />}</span>
                <b class="num">{s.spins}</b>
                <span>{s.effects.join(" · ") || "—"}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function ObjectCard({ o }) {
  const rarity = rarityOf(o.rarity);
  return (
    <article class="obj" style={{ "--rarity": readable(o.color, rarity.color), "--rarity-kind": rarity.color }} data-testid={`obj-${o.id}`} data-rarity={o.rarity}>
      <header class="obj-head">
        <span class="obj-icon">{o.image ? <img src={cdn(o.image)} alt="" /> : o.emoji}</span>
        <div class="grow">
          <strong class="display">{o.name}</strong>
          <div class="row wrap" style={{ gap: "6px", marginTop: "4px" }}>
            <Pill class="rarity-pill">{rarity.label}</Pill>
            <Pill>{OBJECT_TYPE[o.type] || o.type}</Pill>
            <Pill icon={Package}>{plural(o.slots, "espacio", "espacios")}</Pill>
            {o.unique && <Pill tone="primary" icon={Gem}>Único</Pill>}
            {!o.tradeable && <Pill tone="warn" icon={Lock}>No se intercambia</Pill>}
          </div>
        </div>
      </header>
      {o.description && <p>{o.description}</p>}
      {o.lore && <p class="lore">{o.lore}</p>}
      {o.tracking.rows.length > 0 && (
        <div class="tracks">
          <span class="field-label">Progreso de adaptación</span>
          {o.tracking.rows.map((r) => <Track key={r.key} row={r} />)}
        </div>
      )}
    </article>
  );
}

function Inventory({ d }) {
  const [used, max] = d.slots;
  return (
    <div class="dash-col" data-testid="inventory">
      <section class="card-2">
        <div class="row" style={{ gap: "var(--sp-3)" }}>
          <span class="points-orb"><Backpack size={22} /></span>
          <div class="grow">
            <strong class="display" style={{ fontSize: "1.125rem" }}>Espacios de inventario</strong>
            <div class="faint" style={{ fontSize: ".8125rem" }}>Los objetos especiales los da quien dirige el evento.</div>
          </div>
          <b class="num big" data-testid="slots">{used}<small> / {max}</small></b>
        </div>
        <Bar kind="charge" value={used} max={max || 1} thin class="mt" />
      </section>
      {d.objects.length === 0
        ? <Empty icon={Backpack} title="No tienes objetos especiales">Cuando quien dirige el evento te dé uno, aparecerá aquí con su progreso.</Empty>
        : <div class="cards wide">{d.objects.map((o) => <ObjectCard key={o.id} o={o} />)}</div>}
    </div>
  );
}

export function InventoryTab() {
  const q = usePanel("panel.inventory");
  return <Block q={q}>{(d) => <Inventory d={d} />}</Block>;
}
