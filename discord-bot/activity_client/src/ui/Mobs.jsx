// The mini enemies on the field, under the boss: a card each (picture, life, when it attacks next). Tapping one (or Enter on it) hits it.
import { Pause, Swords } from "lucide-preact";
import { useNow } from "../hooks.js";
import { hitMob, hitReady, mobHits, mobs, nextAttackIn } from "../mobs.js";
import { cdn, clamp, cx, initial } from "../util.js";

function MobCard({ mob, at, now, cooling }) {
  const left = nextAttackIn(mob, at, now);
  const hits = mobHits.value.filter((h) => h.id === mob.id);
  const pct = mob.max ? clamp((mob.hp / mob.max) * 100, 0, 100) : 0;
  const soon = left !== null && left <= 2;
  return (
    <button type="button" class={cx("mob", soon && "soon", mob.attacking && "attacking", cooling && "cooling")} style={{ "--mob": mob.color }}
      onClick={() => hitMob(mob.id)} data-testid="mob" data-id={mob.id}
      aria-label={`${mob.name}: ${mob.hp} de ${mob.max} de vida. ${mob.attacking ? `Atacando a ${mob.attacking}.` : left !== null ? `Ataca en ${Math.ceil(left)} segundos.` : ""} Toca para golpear.`}>
      <span class="mob-pic">{mob.image ? <img src={cdn(mob.image)} alt="" loading="lazy" /> : <b>{initial(mob.name)}</b>}</span>
      <span class="mob-main">
        <span class="mob-name ellipsis">{mob.name}</span>
        <span class="mob-bar"><i style={{ width: `${pct}%` }} /></span>
        <span class="mob-meta num">
          {mob.attacking ? <><Swords size={11} /> {mob.attacking}</> : left === null ? <><Pause size={11} /> en pausa</> : `ataca en ${Math.ceil(left)} s`}
          <em>{mob.hp}/{mob.max}</em>
        </span>
      </span>
      {hits.map((h) => <span key={h.key} class="mob-dmg num" aria-hidden="true">-{h.amount}</span>)}
    </button>
  );
}

export function MobsBar() {
  const { list, at } = mobs.value;
  const now = useNow(250, list.length > 0);
  if (!list.length) return null;
  const cooling = hitReady.value > now;
  return (
    <section class="mobs" data-testid="mobs" aria-label="Enemigos">
      {list.map((m) => <MobCard key={m.id} mob={m} at={at} now={now} cooling={cooling} />)}
    </section>
  );
}
