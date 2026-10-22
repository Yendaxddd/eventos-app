// Mini enemies: the bestiary the game masters fill (what each one is like), sending them in, and handling the ones on the field.
import { useState } from "preact/hooks";
import { Bug, Heart, Pause, Pencil, Play, Plus, Save, Skull, Swords, Trash2, X } from "lucide-preact";
import { Block, ConfirmButton, Empty, Field } from "../../ui/Common.jsx";
import { mobs } from "../../mobs.js";
import { cdn, initial } from "../../util.js";
import { Card, Chips, DIFFICULTIES, DIFFICULTY_ES, NumberInput, PictureInput } from "./ui.jsx";
import { useDo, useLive } from "./hooks.js";

export const ATTACKS = [["random", "Al azar", "Cada ataque es un QTE distinto"], ["flick", "Deslizar"], ["drag", "Arrastrar"], ["mash", "Machacar"], ["single", "Esquivar (bot)", "Un QTE normal del bot, también en el canal"]];
const ATTACK_ES = Object.fromEntries(ATTACKS.map(([k, v]) => [k, v]));
const BLANK = { name: "", hp: 120, every: 12, attack: "random", difficulty: "medium", damage: "", charge: 10, color: "#fb7185", image: "" };

// "What does this enemy do", in one line
export const mobSummary = (t) => `${t.hp} PV · ataca cada ${t.every} s · ${ATTACK_ES[t.attack] || t.attack} ${(DIFFICULTY_ES[t.difficulty] || "").toLowerCase()}` +
  `${t.damage ? ` · ${t.damage} de daño` : ""}${t.charge ? ` · da ${t.charge} % de carga` : ""}`;

function Pic({ t }) {
  return <span class="mob-pic" style={{ "--mob": t.color }}>{t.image ? <img src={cdn(t.image)} alt="" /> : <b>{initial(t.name)}</b>}</span>;
}

function Editor({ start, onDone, run, busy }) {
  const [f, setF] = useState({ ...BLANK, ...start, damage: start && start.damage ? String(start.damage) : "" });
  const set = (patch) => setF((old) => ({ ...old, ...patch }));
  const save = async () => {
    const out = await run("save", "gm.mob_save", { mob: { ...f, damage: f.damage === "" ? null : f.damage } }, start && start.id ? "Enemigo guardado." : "Enemigo añadido al bestiario.");
    if (out) onDone(out);
  };
  return (
    <div class="mob-editor" data-testid="mob-editor">
      <div class="row wrap" style={{ gap: "10px", alignItems: "flex-end" }}>
        <Field label="Nombre" class="grow"><input class="input" maxLength={40} value={f.name} onInput={(e) => set({ name: e.currentTarget.value })} data-testid="mob-name" placeholder="Rata gigante" /></Field>
        <Field label="Color"><input type="color" value={f.color} onInput={(e) => set({ color: e.currentTarget.value })} aria-label="Color del enemigo" /></Field>
      </div>
      <div class="mob-editor-grid">
        <Field label="Vida"><NumberInput value={f.hp} min={1} max={100000} unit="PV" label="Vida" testid="mob-hp" onInput={(v) => set({ hp: v })} /></Field>
        <Field label="Ataca cada"><NumberInput value={f.every} min={4} max={600} unit="s" label="Ataca cada" testid="mob-every" onInput={(v) => set({ every: v })} /></Field>
        <Field label="Daño al fallar" hint="Vacío: el de la dificultad"><NumberInput value={f.damage} min={1} max={1000} unit="PV" label="Daño" placeholder="auto" testid="mob-damage" onInput={(v) => set({ damage: v })} /></Field>
        <Field label="Carga al derrotarlo"><NumberInput value={f.charge} min={0} max={100} unit="%" label="Carga" testid="mob-charge" onInput={(v) => set({ charge: v })} /></Field>
      </div>
      <Field label="Cómo ataca"><Chips value={f.attack} options={ATTACKS} onChange={(v) => set({ attack: v })} label="Cómo ataca" testid="mob-attack" /></Field>
      <Field label="Dificultad"><Chips value={f.difficulty} options={DIFFICULTIES} onChange={(v) => set({ difficulty: v })} label="Dificultad" testid="mob-difficulty" /></Field>
      <Field label="Imagen"><PictureInput value={f.image} onChange={(v) => set({ image: v })} testid="mob-image" /></Field>
      <p class="faint gm-hint">{f.name ? <>Así se verá: <b>{f.name}</b> — {mobSummary({ ...f, damage: Number(f.damage) || null })}</> : "Ponle un nombre para guardarlo."}</p>
      <div class="row" style={{ gap: "8px", justifyContent: "flex-end" }}>
        <button class="btn btn-ghost" type="button" onClick={() => onDone(null)}><X size={15} /> Cancelar</button>
        <button class="btn btn-primary" type="button" disabled={!f.name.trim() || busy === "save"} onClick={save} data-testid="mob-save"><Save size={15} /> Guardar</button>
      </div>
    </div>
  );
}

function LiveCard({ run, busy }) {
  const { list, paused } = mobs.value;
  const [amount, setAmount] = useState("25");
  return (
    <Card title={`En el campo (${list.length})`} icon={Swords} testid="mobs-live"
      actions={list.length > 0 && (
        <span class="row" style={{ gap: "6px" }}>
          <button class="btn btn-sm" type="button" data-testid="mobs-pause" disabled={!!busy} onClick={() => run("pause", "gm.mob_pause", { paused: !paused }, paused ? "Los enemigos vuelven a atacar." : "Enemigos en pausa.")}>
            {paused ? <><Play size={14} /> Reanudar</> : <><Pause size={14} /> Pausar</>}
          </button>
          <ConfirmButton icon={Trash2} confirm="Sí, retirarlos" testid="mobs-clear" onConfirm={() => run("clear", "gm.mob_remove", { id: "all" }, "Enemigos retirados.")}>Retirar todos</ConfirmButton>
        </span>
      )}>
      {list.length === 0 ? <p class="faint">No hay enemigos ahora. Haz aparecer alguno del bestiario.</p> : (
        <>
          <div class="row" style={{ gap: "8px", marginBottom: "8px" }}>
            <span class="faint">Cantidad para dañar o curar</span>
            <NumberInput value={amount} min={1} max={100000} unit="PV" label="Cantidad" width="120px" onInput={setAmount} testid="mobs-amount" />
          </div>
          <ul class="mob-live">
            {list.map((m) => (
              <li key={m.id} data-testid="mob-live" data-id={m.id}>
                <Pic t={m} />
                <div class="grow" style={{ minWidth: 0 }}>
                  <div class="row" style={{ gap: "6px" }}><b class="ellipsis">{m.name}</b><span class="num faint" style={{ marginLeft: "auto" }}>{m.hp}/{m.max}</span></div>
                  <span class="mob-bar"><i style={{ width: `${(m.hp / m.max) * 100}%`, background: m.color }} /></span>
                  <small class="faint">{m.attacking ? `atacando a ${m.attacking}` : paused ? "en pausa" : `ataca cada ${m.every} s`}</small>
                </div>
                <span class="row" style={{ gap: "4px" }}>
                  <button class="btn btn-sm icon-btn" type="button" title="Dañar" aria-label={`Dañar a ${m.name}`} onClick={() => run("hp", "gm.mob_hp", { id: m.id, action: "damage", amount })}><Swords size={14} /></button>
                  <button class="btn btn-sm icon-btn" type="button" title="Curar" aria-label={`Curar a ${m.name}`} onClick={() => run("hp", "gm.mob_hp", { id: m.id, action: "heal", amount })}><Heart size={14} /></button>
                  <button class="btn btn-sm icon-btn" type="button" title="Derrotar" aria-label={`Derrotar a ${m.name}`} data-testid="mob-kill" onClick={() => run("hp", "gm.mob_hp", { id: m.id, action: "kill" })}><Skull size={14} /></button>
                  <button class="btn btn-sm icon-btn btn-ghost" type="button" title="Retirar" aria-label={`Retirar a ${m.name}`} onClick={() => run("rm", "gm.mob_remove", { id: m.id })}><X size={14} /></button>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function Bestiary({ d, run, busy, refresh }) {
  const [editing, setEditing] = useState(null);           // null | "new" | template
  const [count, setCount] = useState({});
  const done = (out) => { setEditing(null); if (out) refresh(); };
  return (
    <Card title="Bestiario" icon={Bug} testid="mobs-bestiary"
      hint="Cada enemigo ataca por su cuenta a alguien que juegue desde la Actividad. Los jugadores lo golpean tocándolo; quien lo remata se lleva la carga."
      actions={editing === null && <button class="btn btn-sm btn-primary" type="button" data-testid="mob-new" onClick={() => setEditing("new")}><Plus size={14} /> Nuevo enemigo</button>}>
      {editing !== null && <Editor start={editing === "new" ? null : editing} onDone={done} run={run} busy={busy} />}
      {d.bestiary.length === 0 && editing === null && <Empty icon={Bug} title="El bestiario está vacío">Crea un enemigo: nombre, vida, cada cuánto ataca y qué QTE lanza.</Empty>}
      <ul class="mob-list">
        {d.bestiary.map((t) => (
          <li key={t.id} data-testid="mob-template" data-id={t.id}>
            <Pic t={t} />
            <div class="grow" style={{ minWidth: 0 }}><b class="ellipsis">{t.name}</b><small class="faint">{mobSummary(t)}</small></div>
            <span class="row" style={{ gap: "4px" }}>
              <NumberInput value={count[t.id] || 1} min={1} max={d.maxSpawn} label={`Cuántos ${t.name}`} width="64px" onInput={(v) => setCount({ ...count, [t.id]: v })} />
              <button class="btn btn-sm btn-primary" type="button" data-testid="mob-spawn" disabled={busy === "spawn"}
                onClick={() => run("spawn", "gm.mob_spawn", { id: t.id, count: count[t.id] || 1 }, "¡Enemigos en el campo!")}><Play size={14} /> Aparecer</button>
              <button class="btn btn-sm icon-btn" type="button" aria-label={`Editar ${t.name}`} title="Editar" onClick={() => setEditing(t)}><Pencil size={14} /></button>
              <ConfirmButton icon={Trash2} label={`Borrar ${t.name}`} confirm="Borrar" onConfirm={async () => { if (await run("del", "gm.mob_delete", { id: t.id }, "Borrado.")) refresh(); }} />
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function MobsTab() {
  const q = useLive("gm.mobs", null, 6000);
  const [busy, run] = useDo();
  return (
    <div class="dash-col" data-testid="gm-mobs">
      <LiveCard run={run} busy={busy} />
      <Block q={q}>{(d) => <Bestiary d={d} run={run} busy={busy} refresh={q.refresh} />}</Block>
    </div>
  );
}
