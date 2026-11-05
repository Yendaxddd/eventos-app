import { Sparkles } from "lucide-preact";
import { Block } from "../../ui/Common.jsx";
import { Row } from "../gm/FxTab.jsx";
import { DEFAULT_BINDING } from "../../fx-model.js";
import { act, usePanel } from "../../panel/data.js";

const GROUPS = [
  ["Tus poderes", ["power_used", "power_1", "power_2"]],
  ["Tus respuestas", ["evade_ok", "parry_ok", "counter", "rescue_ok", "combo_step", "qte_fail"]],
  ["Lo que te pasa", ["black_flash", "combo_done", "player_hit", "low_hp", "heal"]],
];
const START = { ...DEFAULT_BINDING, preset: "impacto", scope: "target" };
const WHO = { all: "Todos lo ven", target: "Solo yo" };

// «Mi panel → Efectos»: every player can give what happens to them a look of their own (the game masters keep the rest).
export function EffectsTab() {
  const q = usePanel("fx.mine");
  return <Block q={q}>{(d) => <EffectsBody d={d} replace={q.replace} />}</Block>;
}

function EffectsBody({ d, replace }) {
  const byId = Object.fromEntries(d.events.map((e) => [e.id, e]));
  const save = (event) => async (binding) => {
    const out = await act("fx.mine_set", { event, binding });
    if (out) { replace(out); return true; }
    return false;
  };
  const clear = (event) => async () => { const out = await act("fx.mine_clear", { event }, "Efecto quitado."); if (out) replace(out); };
  return (
    <div class="dash-col" data-testid="my-fx">
      <p class="faint">Elige cómo se ve lo que te pasa a ti: color, fuerza, velocidad, un rótulo. Por defecto solo lo ves tú; si quieres, que lo vean todos. Lo que no cambies lo deciden los GM. Se guarda solo.</p>
      {GROUPS.map(([title, ids]) => (
        <section key={title} class="card">
          <h3 class="gm-sub"><Sparkles size={14} /> {title}</h3>
          {ids.filter((id) => byId[id]).map((id) => (
            <Row key={id} id={`mine-${id}`} title={byId[id].label} binding={byId[id].binding} fallback={byId[id].binding ? null : null} start={START}
              sounds={null} name={byId[id].label} scopeChoice scopeLabels={WHO} save={save(id)} clear={clear(id)} />
          ))}
        </section>
      ))}
    </div>
  );
}
