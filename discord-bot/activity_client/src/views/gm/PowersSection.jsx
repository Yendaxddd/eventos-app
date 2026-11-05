// Every character's powers in one list (what /manageultimates showed), each editable with the players' own power builder.
import { useState } from "preact/hooks";
import { Pencil, Plus, Zap } from "lucide-preact";
import { Block, Pill } from "../../ui/Common.jsx";
import { usePanel } from "../../panel/data.js";
import { POWER_TYPE, duration } from "../../panel/format.js";
import { effectSummary } from "../../power-model.js";
import { PowerEditor } from "../panel/Characters.jsx";
import { Card } from "./ui.jsx";

export function PowersSection() {
  const q = usePanel("gm.powers");
  const [editing, setEditing] = useState(null);           // { character, slot, power }
  const [filter, setFilter] = useState("");
  return (
    <Block q={q}>
      {(d) => {
        const shown = d.rows.filter((r) => !filter || `${r.character} ${r.owner}`.toLowerCase().includes(filter.toLowerCase()));
        return (
          <Card title={`Poderes de todos (${d.rows.length} personajes)`} icon={Zap} testid="gm-powers"
            hint={`Los mismos poderes que crean los jugadores. ${d.selfRecharge ? "Los poderes recargan carga al hacer daño." : "Los poderes no recargan carga al hacer daño (se cambia en Valores)."}`}>
            <input class="input" placeholder="Buscar personaje o persona…" value={filter} onInput={(e) => setFilter(e.currentTarget.value)} aria-label="Buscar" style={{ marginBottom: "8px" }} />
            <ul class="gm-list">
              {shown.map((r) => (
                <li key={r.character} class="gm-item" data-testid={`gm-powers-${r.character}`}>
                  <div class="grow col" style={{ gap: "6px", minWidth: 0 }}>
                    <div><strong>{r.character}</strong> <span class="faint">· {r.owner}</span></div>
                    {[1, 2].map((slot) => {
                      const p = r.powers[`power${slot}`];
                      return (
                        <div key={slot} class="row wrap" style={{ gap: "6px" }}>
                          <span class="faint">Poder {slot}:</span>
                          {p ? <><b>{p.name}</b><Pill>{POWER_TYPE[p.type] || p.type}</Pill><Pill tone="warn">{duration(p.cooldown)}</Pill><Pill tone="info">{effectSummary(p.effect, 1, d.cap)}</Pill></> : <span class="faint">—</span>}
                          <button class="btn btn-sm btn-ghost" type="button" onClick={() => setEditing({ character: r.character, slot, power: p })} data-testid={`gm-power-edit-${r.character}-${slot}`}>
                            {p ? <><Pencil size={13} /> Editar</> : <><Plus size={13} /> Crear</>}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </li>
              ))}
            </ul>
            {editing && <PowerEditor character={editing.character} slot={editing.slot} power={editing.power} types={d.types} meta={d}
              onClose={() => setEditing(null)} onSaved={() => { setEditing(null); q.refresh(); }} />}
          </Card>
        );
      }}
    </Block>
  );
}
