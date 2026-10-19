import { useState } from "preact/hooks";
import { Crown, Flame, Image as ImageIcon, Pencil, Play, Plus, Skull, Sparkles, Trash2, Wand2 } from "lucide-preact";
import { Modal } from "../../ui/Overlays.jsx";
import { Block, ConfirmButton, Empty, Field, Pill } from "../../ui/Common.jsx";
import { cdn } from "../../util.js";
import { duration, num, parseNumber } from "../../panel/format.js";
import { Bar, Card, NumberInput, PictureInput } from "./ui.jsx";
import { useDo, useDraft, useLive } from "./hooks.js";

const DOMAIN_KINDS = [["simple", "Simple", "Daña a todos una vez."], ["dps", "Daño continuo", "Daña a todos cada pocos segundos mientras dura."], ["stun", "Aturdimiento", "Impide actuar a quien lo sufre."]];

// ---- the boss that is fighting now ---------------------------------------------------------------------------------------
function Active({ d, replace }) {
  const boss = d.active;
  const [amount, setAmount] = useState("100");
  const [busy, run] = useDo();
  const hp = async (action, done) => {
    const out = await run(action, "gm.boss_hp", { action, amount: parseNumber(amount) ?? 0 }, done);
    if (out) replace(out);
  };
  const drop = async (op, done) => {
    const out = await run(op, `gm.${op}`, {}, done);
    if (out) replace(out);
  };
  if (!boss) {
    return (
      <Card title="Jefe en combate" icon={Skull} testid="gm-boss-active">
        <Empty icon={Skull} title="No hay un jefe en combate">Registra uno aquí abajo o haz aparecer al personaje de Tupperbox.</Empty>
      </Card>
    );
  }
  return (
    <Card title="Jefe en combate" icon={Skull} testid="gm-boss-active" actions={<Pill tone={boss.tupper ? "info" : "primary"}>{boss.tupper ? "Tupperbox" : "Registrado"}</Pill>}>
      <div class="gm-boss">
        {boss.image && <img class="gm-boss-pic" src={cdn(boss.image)} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
        <div class="grow col" style={{ gap: "var(--sp-3)" }}>
          <strong class="display" style={{ fontSize: "1.25rem" }} data-testid="gm-boss-name">{boss.name}</strong>
          <Bar value={boss.hp} max={boss.max} kind="boss" label={`Vida de ${boss.name}`} />
          <div class="row wrap" style={{ gap: "8px" }}>
            <NumberInput value={amount} min={0} max={9999999} step={50} unit="HP" label="Cantidad de vida" testid="gm-boss-amount" onInput={setAmount} width="150px" />
            <button class="btn" type="button" disabled={busy !== null} onClick={() => hp("damage", "Daño hecho al jefe.")} data-testid="gm-boss-damage">Hacer daño</button>
            <button class="btn" type="button" disabled={busy !== null} onClick={() => hp("heal", "Jefe curado.")} data-testid="gm-boss-heal">Curar</button>
            <button class="btn" type="button" disabled={busy !== null} onClick={() => hp("set", "Vida cambiada.")} data-testid="gm-boss-set">Fijar la vida</button>
          </div>
          <div class="row wrap" style={{ gap: "8px" }}>
            <ConfirmButton icon={Flame} confirm="Sí, derrotarlo" onConfirm={() => hp("defeat", "Jefe derrotado.")} disabled={busy !== null} testid="gm-boss-defeat">Derrotar</ConfirmButton>
            <ConfirmButton icon={Trash2} confirm="Sí, retirarlo" onConfirm={() => drop("boss_remove", "Jefe retirado.")} disabled={busy !== null} testid="gm-boss-remove">Retirar sin derrotarlo</ConfirmButton>
          </div>
        </div>
      </div>
    </Card>
  );
}

// ---- a new boss ----------------------------------------------------------------------------------------------------------------
function Register({ d, replace }) {
  const [f, setF] = useState({ name: "", hp: "1000", image: "" });
  const [busy, run] = useDo();
  const set = (patch) => setF((old) => ({ ...old, ...patch }));
  const register = async (e) => {
    e.preventDefault();
    const out = await run("register", "gm.boss_register", { name: f.name, hp: parseNumber(f.hp), image: f.image }, "Jefe registrado: empieza el combate.");
    if (out) { replace(out); setF({ name: "", hp: f.hp, image: "" }); }
  };
  const spawn = async () => {
    const out = await run("spawn", "gm.boss_spawn", {}, "El jefe aparece.");
    if (out) replace(out);
  };
  const mode = async (on) => {
    const out = await run("mode", "gm.boss_mode", { on }, on ? "Modo jefe de Tupperbox activado." : "Modo jefe de Tupperbox desactivado.");
    if (out) replace(out);
  };
  const character = d.config.character;
  return (
    <>
      <Card title="Registrar un jefe" icon={Crown} hint="Como /registerboss: se anuncia en el canal y el combate empieza." testid="gm-boss-register">
        <form noValidate class="col" style={{ gap: "var(--sp-3)" }} onSubmit={register}>
          <div class="gm-grid">
            <Field label="Nombre"><input class="input" maxLength={80} value={f.name} onInput={(e) => set({ name: e.currentTarget.value })} placeholder="p. ej. Rey de las Maldiciones" data-testid="gm-register-name" /></Field>
            <Field label="Vida"><NumberInput value={f.hp} min={1} max={9999999} step={100} unit="HP" label="Vida del jefe" testid="gm-register-hp" onInput={(hp) => set({ hp })} /></Field>
          </div>
          <Field label="Imagen (opcional)" hint="Se muestra en el anuncio. Pega un enlace https o sube una imagen.">
            <PictureInput value={f.image} onChange={(image) => set({ image })} testid="gm-register-image" label="Imagen del jefe" />
          </Field>
          <div><button class="btn btn-primary" type="submit" disabled={busy !== null || !f.name.trim()} data-testid="gm-register-go"><Play size={16} /> Registrar y empezar</button></div>
        </form>
      </Card>
      <Card title="Jefe de Tupperbox" icon={Wand2} testid="gm-boss-tupper"
        hint={character ? `El personaje «${character}» hace de jefe. Ajusta su vida y sus probabilidades en «Ajustes del jefe».` : "Primero elige el personaje de Tupperbox que hace de jefe, en «Ajustes del jefe»."}>
        <div class="row wrap" style={{ gap: "10px" }}>
          <button class="btn btn-primary" type="button" onClick={spawn} disabled={busy !== null || !character} data-testid="gm-boss-spawn"><Sparkles size={16} /> Hacer aparecer al jefe</button>
          <label class="row" style={{ gap: "10px" }}>
            <button type="button" role="switch" class="switch" aria-checked={d.mode ? "true" : "false"} aria-label="Modo jefe de Tupperbox" disabled={busy !== null} onClick={() => mode(!d.mode)} data-testid="gm-boss-mode" />
            <span>Modo jefe de Tupperbox {d.mode ? "activado" : "desactivado"}</span>
          </label>
        </div>
      </Card>
    </>
  );
}

// ---- the Tupperbox boss's numbers ---------------------------------------------------------------------------------------
function Settings({ d, replace }) {
  const c = d.config;
  const form = useDraft({ character: c.character || "", hp: String(c.hp), evade: String(c.evade), counter: String(c.counter), counterDamage: String(c.counterDamage) });
  const [busy, run] = useDo();
  const { draft, edit } = form;
  const save = async (e) => {
    e.preventDefault();
    const sent = draft;
    const out = await run("config", "gm.boss_config", { character: sent.character, hp: parseNumber(sent.hp), evade: parseNumber(sent.evade), counter: parseNumber(sent.counter), counterDamage: parseNumber(sent.counterDamage) }, "Ajustes del jefe guardados.");
    if (out) { form.saved(sent); replace(out); }
  };
  return (
    <Card title="Ajustes del jefe" icon={Crown} testid="gm-boss-settings" hint="Valen para el jefe de Tupperbox: el personaje, su vida y cómo se defiende.">
      <form noValidate class="col" style={{ gap: "var(--sp-3)" }} onSubmit={save}>
        <Field label="Personaje de Tupperbox" hint="Tal como se llama en Tupperbox (se distingue entre mayúsculas y minúsculas).">
          <input class="input" maxLength={100} value={draft.character} onInput={(e) => edit({ character: e.currentTarget.value })} data-testid="gm-boss-character" />
        </Field>
        <div class="gm-grid">
          <Field label="Vida"><NumberInput value={draft.hp} min={1} max={9999999} step={100} unit="HP" label="Vida del jefe" testid="gm-boss-hp" onInput={(hp) => edit({ hp })} /></Field>
          <Field label="Esquiva"><NumberInput value={draft.evade} min={0} max={100} step={1} unit="%" label="Probabilidad de esquivar" testid="gm-boss-evade" onInput={(evade) => edit({ evade })} /></Field>
          <Field label="Contraataque"><NumberInput value={draft.counter} min={0} max={100} step={1} unit="%" label="Probabilidad de contraatacar" testid="gm-boss-counter" onInput={(counter) => edit({ counter })} /></Field>
          <Field label="Daño del contraataque"><NumberInput value={draft.counterDamage} min={0} max={9999} step={5} unit="HP" label="Daño del contraataque" testid="gm-boss-counterdamage" onInput={(counterDamage) => edit({ counterDamage })} /></Field>
        </div>
        <div><button class="btn btn-primary" type="submit" disabled={busy !== null} data-testid="gm-boss-settings-save">Guardar ajustes</button></div>
      </form>
    </Card>
  );
}

// ---- abilities --------------------------------------------------------------------------------------------------------------------
function AbilityEditor({ ability, statusTypes, onClose, onSaved }) {
  const [f, setF] = useState({
    name: ability ? ability.name : "", damage: ability ? String(ability.damage) : "25", gif: ability && ability.gif ? ability.gif : "",
    statusType: ability && ability.status ? ability.status.type : "", statusChance: ability && ability.status ? String(ability.status.chance) : "100",
    statusDuration: ability && ability.status ? String(ability.status.duration) : "60",
  });
  const [busy, run] = useDo();
  const set = (patch) => setF((old) => ({ ...old, ...patch }));
  const save = async () => {
    const out = await run("save", "gm.ability_save", { name: f.name, damage: parseNumber(f.damage), gif: f.gif, statusType: f.statusType, statusChance: parseNumber(f.statusChance), statusDuration: parseNumber(f.statusDuration) }, "Habilidad guardada.");
    if (out) onSaved(out);
  };
  return (
    <Modal title={ability ? `Editar «${ability.name}»` : "Nueva habilidad del jefe"} onClose={onClose}
      actions={<><button class="btn btn-ghost" type="button" onClick={onClose}>Cancelar</button>
        <button class="btn btn-primary" type="button" onClick={save} disabled={busy !== null || !f.name.trim()} data-testid="gm-ability-save">Guardar</button></>}>
      <div class="col" style={{ gap: "var(--sp-3)" }} data-testid="gm-ability-editor">
        <Field label="Nombre"><input class="input" maxLength={50} value={f.name} disabled={!!ability} onInput={(e) => set({ name: e.currentTarget.value })} data-testid="gm-ability-name" /></Field>
        <Field label="Daño a cada jugador"><NumberInput value={f.damage} min={0} max={9999} step={5} unit="HP" label="Daño" testid="gm-ability-damage" onInput={(damage) => set({ damage })} /></Field>
        <Field label="Imagen o GIF (opcional)"><PictureInput value={f.gif} onChange={(gif) => set({ gif })} testid="gm-ability-gif" label="Imagen de la habilidad" /></Field>
        <Field label="Estado alterado (opcional)" hint="Lo que sufre quien reciba el golpe.">
          <select class="select" value={f.statusType} onChange={(e) => set({ statusType: e.currentTarget.value })} data-testid="gm-ability-status">
            <option value="">Ninguno</option>
            {statusTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </Field>
        {f.statusType && (
          <div class="gm-grid">
            <Field label="Probabilidad"><NumberInput value={f.statusChance} min={0} max={100} step={5} unit="%" label="Probabilidad del estado" testid="gm-ability-chance" onInput={(statusChance) => set({ statusChance })} /></Field>
            <Field label="Duración"><NumberInput value={f.statusDuration} min={1} max={3600} step={5} unit="s" label="Duración del estado" testid="gm-ability-duration" onInput={(statusDuration) => set({ statusDuration })} /></Field>
          </div>
        )}
      </div>
    </Modal>
  );
}

function Abilities({ d, replace }) {
  const [editing, setEditing] = useState(null);                  // null | "new" | an ability
  const [busy, run] = useDo();
  const list = d.config.abilities;
  const use = (name) => run(`use-${name}`, "gm.ability_use", { name }, `«${name}» lanzada.`);
  const remove = async (name) => {
    const out = await run(`rm-${name}`, "gm.ability_remove", { name }, "Habilidad quitada.");
    if (out) replace(out);
  };
  return (
    <Card title="Habilidades del jefe" icon={Flame} testid="gm-abilities" hint="Ataques que el jefe puede lanzar a todos los jugadores."
      actions={<button class="btn btn-sm" type="button" onClick={() => setEditing("new")} data-testid="gm-ability-new"><Plus size={14} /> Nueva</button>}>
      {list.length === 0 ? <Empty icon={Flame} title="Sin habilidades">Crea la primera con «Nueva».</Empty> : (
        <ul class="gm-list">
          {list.map((a) => (
            <li key={a.name} class="gm-item" data-testid={`gm-ability-${a.name}`}>
              {a.gif ? <img class="gm-thumb" src={cdn(a.gif)} alt="" /> : <span class="gm-thumb gm-thumb-empty"><Flame size={16} /></span>}
              <div class="grow">
                <strong>{a.name}</strong>
                <div class="row wrap" style={{ gap: "6px", marginTop: "4px" }}>
                  <Pill tone="bad">{a.damage} de daño</Pill>
                  {a.status && <Pill tone="warn">{a.status.type} · {a.status.chance} % · {duration(a.status.duration)}</Pill>}
                </div>
              </div>
              <button class="btn btn-sm" type="button" disabled={busy !== null || !d.active} title={d.active ? "Lanzarla ahora" : "Necesita un jefe en combate"} onClick={() => use(a.name)} data-testid={`gm-ability-use-${a.name}`}><Play size={14} /> Usar</button>
              <button class="icon-btn" type="button" aria-label={`Editar ${a.name}`} onClick={() => setEditing(a)} data-testid={`gm-ability-edit-${a.name}`}><Pencil size={17} /></button>
              <ConfirmButton icon={Trash2} confirm="Quitar" label={`Quitar ${a.name}`} onConfirm={() => remove(a.name)} disabled={busy !== null} testid={`gm-ability-remove-${a.name}`} />
            </li>
          ))}
        </ul>
      )}
      {editing && <AbilityEditor ability={editing === "new" ? null : editing} statusTypes={d.statusTypes} onClose={() => setEditing(null)} onSaved={(out) => { setEditing(null); replace(out); }} />}
    </Card>
  );
}

// ---- GIFs --------------------------------------------------------------------------------------------------------------------------
const GIFS = [
  ["evade", "Cuando el jefe esquiva", "evadeGifs"], ["counter", "Cuando el jefe contraataca", "counterGifs"], ["defeat", "Cuando el jefe es derrotado", "defeatGifs"],
];

function GifList({ kind, title, urls, replace }) {
  const [address, setAddress] = useState("");
  const [busy, run] = useDo();
  const add = async (e) => {
    e.preventDefault();
    const out = await run("add", "gm.gif_add", { kind, url: address }, "Imagen añadida.");
    if (out) { replace(out); setAddress(""); }
  };
  const remove = async (index) => {
    const out = await run("rm", "gm.gif_remove", { kind, index }, "Imagen quitada.");
    if (out) replace(out);
  };
  return (
    <div class="col" style={{ gap: "var(--sp-2)" }} data-testid={`gm-gifs-${kind}`}>
      <div class="row"><strong class="grow">{title}</strong><span class="faint num" style={{ fontSize: ".75rem" }}>{urls.length} / 30</span></div>
      {urls.length > 0 && (
        <div class="gallery gm-gallery">
          {urls.map((u, i) => (
            <figure key={u} class="shot">
              <img src={cdn(u)} alt="" loading="lazy" />
              <figcaption><span /><button class="icon-btn" type="button" aria-label="Quitar imagen" disabled={busy !== null} onClick={() => remove(i)} data-testid={`gm-gif-remove-${kind}-${i}`}><Trash2 size={16} /></button></figcaption>
            </figure>
          ))}
        </div>
      )}
      <form noValidate class="col" style={{ gap: "6px" }} onSubmit={add}>
        <PictureInput value={address} onChange={setAddress} testid={`gm-gif-${kind}`} label={`Añadir imagen: ${title}`} preview={false} />
        <div><button class="btn btn-sm" type="submit" disabled={busy !== null || !address} data-testid={`gm-gif-add-${kind}`}><Plus size={14} /> Añadir a la lista</button></div>
      </form>
    </div>
  );
}

function Gifs({ d, replace }) {
  return (
    <Card title="Imágenes del jefe" icon={ImageIcon} testid="gm-gifs" hint="El bot muestra una de la lista al azar en cada situación.">
      <div class="col" style={{ gap: "var(--sp-5)" }}>
        {GIFS.map(([kind, title, key]) => <GifList key={kind} kind={kind} title={title} urls={key === "defeatGifs" ? d.defeatGifs : d.config[key]} replace={replace} />)}
      </div>
    </Card>
  );
}

// ---- domain -----------------------------------------------------------------------------------------------------------------------------
function Domain({ d, replace }) {
  const dom = d.config.domain;
  const form = useDraft({ name: dom ? dom.name : "", type: dom ? dom.type : "simple", duration: dom ? String(dom.duration) : "30", effect: dom ? String(dom.effect) : "10", gif: dom && dom.gif ? dom.gif : "" });
  const [busy, run] = useDo();
  const { draft, edit } = form;
  const save = async (e) => {
    e.preventDefault();
    const sent = draft;
    const out = await run("save", "gm.domain_save", { name: sent.name, type: sent.type, duration: parseNumber(sent.duration), effect: parseNumber(sent.effect), gif: sent.gif }, "Dominio guardado.");
    if (out) { form.saved(sent); replace(out); }
  };
  const expand = () => run("expand", "gm.domain_expand", {}, "El jefe expande su dominio.");
  const clear = async () => {
    const out = await run("clear", "gm.domain_clear", {}, "Dominio quitado.");
    if (out) replace(out);
  };
  const kind = DOMAIN_KINDS.find(([id]) => id === draft.type);
  return (
    <Card title="Dominio del jefe" icon={Sparkles} testid="gm-domain" hint="Un ataque especial que afecta a todos durante un tiempo.">
      <form noValidate class="col" style={{ gap: "var(--sp-3)" }} onSubmit={save}>
        <div class="gm-grid">
          <Field label="Nombre"><input class="input" maxLength={100} value={draft.name} onInput={(e) => edit({ name: e.currentTarget.value })} data-testid="gm-domain-name" /></Field>
          <Field label="Tipo" hint={kind ? kind[2] : undefined}>
            <select class="select" value={draft.type} onChange={(e) => edit({ type: e.currentTarget.value })} data-testid="gm-domain-type">
              {DOMAIN_KINDS.map(([id, text]) => <option key={id} value={id}>{text}</option>)}
            </select>
          </Field>
          <Field label="Duración"><NumberInput value={draft.duration} min={1} max={3600} step={5} unit="s" label="Duración del dominio" testid="gm-domain-duration" onInput={(v) => edit({ duration: v })} /></Field>
          <Field label="Fuerza" hint={`Daño o efecto por golpe: ${num(parseNumber(draft.effect) ?? 0)}.`}><NumberInput value={draft.effect} min={0} max={9999} step={1} label="Fuerza del dominio" testid="gm-domain-effect" onInput={(v) => edit({ effect: v })} /></Field>
        </div>
        <Field label="Imagen o GIF (opcional)"><PictureInput value={draft.gif} onChange={(gif) => edit({ gif })} testid="gm-domain-gif" label="Imagen del dominio" /></Field>
        <div class="row wrap" style={{ gap: "8px" }}>
          <button class="btn btn-primary" type="submit" disabled={busy !== null || !draft.name.trim()} data-testid="gm-domain-save">Guardar dominio</button>
          <button class="btn" type="button" disabled={busy !== null || !dom} onClick={expand} data-testid="gm-domain-expand"><Sparkles size={16} /> Expandir ahora</button>
          {dom && <ConfirmButton icon={Trash2} confirm="Sí, quitarlo" onConfirm={clear} disabled={busy !== null} testid="gm-domain-clear">Quitar dominio</ConfirmButton>}
        </div>
      </form>
    </Card>
  );
}

export function BossTab() {
  const q = useLive("gm.boss", null, 4000);
  return (
    <div class="dash-col" data-testid="gm-boss">
      <Block q={q}>
        {(d) => (
          <>
            <Active d={d} replace={q.replace} />
            <Register d={d} replace={q.replace} />
            <Settings d={d} replace={q.replace} />
            <Abilities d={d} replace={q.replace} />
            <Gifs d={d} replace={q.replace} />
            <Domain d={d} replace={q.replace} />
          </>
        )}
      </Block>
    </div>
  );
}
