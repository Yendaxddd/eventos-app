import { useState } from "preact/hooks";
import { Backpack, BookOpen, Check, Circle, Gem, Lock, Package, Sparkles } from "lucide-preact";
import { me } from "../../state.js";
import { EffectChips, STATUS } from "../../ui/Effects.jsx";
import { Bar } from "../../ui/Hud.jsx";
import { Block, Empty, Pill } from "../../ui/Common.jsx";
import { act, usePanel } from "../../panel/data.js";
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

function UseButton({ use, replace }) {
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    const out = await act("panel.object_use", { use: use.id }, "¡Invocado!");
    setBusy(false);
    if (out) replace(out);
  };
  return (
    <div class="obj-use">
      <button class="btn btn-primary btn-sm" type="button" disabled={!!use.problem || busy} onClick={go} data-testid={`obj-use-${use.id}`}><Sparkles size={14} /> {use.label}</button>
      {use.problem && <small class="faint">{use.problem}</small>}
    </div>
  );
}

function ObjectCard({ o, replace }) {
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
      {o.use && <UseButton use={o.use} replace={replace} />}
    </article>
  );
}

// What is on you right now (from the bot's status effects and boosts), with what each one does.
function ActiveEffects() {
  const m = me.value;
  const all = m ? [...(m.effects || []), ...(m.buffs || [])] : [];
  return (
    <section class="card-2" data-testid="active-effects">
      <strong class="display">Efectos activos</strong>
      {all.length === 0 ? <p class="faint" style={{ marginTop: "6px" }}>Ninguno ahora mismo. Aquí verás venenos, quemaduras, escudos o mejoras, con el tiempo que les queda.</p> : (
        <div class="col" style={{ gap: "8px", marginTop: "8px" }}>
          <EffectChips effects={m.effects} buffs={m.buffs} />
          <ul class="effect-help">{all.map((e) => (STATUS[e.kind] && STATUS[e.kind][2] ? <li key={e.kind}><b>{STATUS[e.kind][1]}:</b> {STATUS[e.kind][2]}</li> : null))}</ul>
        </div>
      )}
    </section>
  );
}

function Catalog({ items }) {
  if (!items || !items.length) return null;
  return (
    <details class="card-2 catalog" data-testid="catalog">
      <summary><BookOpen size={16} style={{ verticalAlign: "-3px" }} /> Todos los objetos del evento ({items.length})</summary>
      <div class="catalog-grid">
        {items.map((o) => (
          <div key={o.id} class="catalog-item" data-rarity={o.rarity}>
            <span class="obj-icon">{o.image ? <img src={cdn(o.image)} alt="" /> : o.emoji}</span>
            <div class="grow" style={{ minWidth: 0 }}>
              <b>{o.name}</b>{o.mine ? <Pill tone="ok">Tuyo</Pill> : o.unique && o.taken ? <Pill tone="warn">Ya tiene dueño</Pill> : null}
              <small class="faint">{rarityOf(o.rarity).label} · {OBJECT_TYPE[o.type] || o.type}</small>
              {o.description && <p>{o.description}</p>}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function Inventory({ d, replace }) {
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
        : <div class="cards wide">{d.objects.map((o) => <ObjectCard key={o.id} o={o} replace={replace} />)}</div>}
      <ActiveEffects />
      <Catalog items={d.catalog} />
    </div>
  );
}

export function InventoryTab() {
  const q = usePanel("panel.inventory");
  return <Block q={q}>{(d) => <Inventory d={d} replace={q.replace} />}</Block>;
}
