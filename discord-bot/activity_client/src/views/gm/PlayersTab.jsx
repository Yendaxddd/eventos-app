import { useState } from "preact/hooks";
import { ArrowLeft, Backpack, Heart, HeartPulse, Plus, RotateCcw, Search, Star, Trash2, Trophy, UserX, Users, Zap } from "lucide-preact";
import { rules, toast } from "../../state.js";
import { Avatar } from "../../ui/Avatar.jsx";
import { Block, ConfirmButton, Empty, Field, Pill } from "../../ui/Common.jsx";
import { usePanel } from "../../panel/data.js";
import { TRACK_LABEL, decimal, parseNumber, plural, rarityOf } from "../../panel/format.js";
import { cx } from "../../util.js";
import { Card, NumberInput, Sub } from "./ui.jsx";
import { useDo, useDraft } from "./hooks.js";

const DIFFS = ["easy", "medium", "hard", "impossible"];

function level(hp) {
  const pct = hp.max > 0 ? hp.current / hp.max : 0;
  return pct <= 0.25 ? "low" : pct <= 0.55 ? "mid" : "ok";
}

// ---- the list --------------------------------------------------------------------------------------------------------------------
function Row({ p, onOpen }) {
  const hp = p.hp;
  return (
    <button type="button" class="gm-player" onClick={() => onOpen(p.id)} data-testid={`gm-player-${p.id}`} data-online={p.online ? "1" : "0"}>
      <Avatar url={p.avatar} name={p.name} size="lg" />
      <div class="gm-player-main">
        <div class="row" style={{ gap: "8px" }}>
          <strong class="ellipsis">{p.name}</strong>
          {p.online && <span class="dot ok" title="Está en la Actividad" />}
          {p.afk && <Pill tone="warn" icon={UserX}>Fuera de los QTE</Pill>}
          {hp && !hp.alive && <Pill tone="bad">Caído</Pill>}
        </div>
        {hp ? (
          <div class="bar thin" role="img" aria-label={`Vida ${hp.current} de ${hp.max}`}><i style={{ width: `${hp.max ? Math.max(0, Math.min(100, (hp.current / hp.max) * 100)) : 0}%` }} data-level={level(hp)} /></div>
        ) : <span class="faint" style={{ fontSize: ".75rem" }}>Sin vida registrada</span>}
        <div class="row wrap faint num" style={{ gap: "10px", fontSize: ".75rem" }}>
          {hp && <span><Heart size={11} /> {hp.current}/{hp.max}</span>}
          <span><Zap size={11} /> {p.charges[0]} % · {p.charges[1]} %</span>
          <span><Star size={11} /> {p.points}</span>
          {p.attempts > 0 && <span>{decimal(p.rate)} % de acierto</span>}
        </div>
      </div>
    </button>
  );
}

function List({ onOpen }) {
  const q = usePanel("gm.players");
  const [filter, setFilter] = useState("");
  const [busy, run] = useDo();
  const resetAll = async () => {
    const out = await run("all", "gm.hp_reset", { id: "all" }, null);
    if (out) { toast(`Vida restaurada a ${plural(out.count, "jugador", "jugadores")}.`, "ok"); q.refresh(); }
  };
  return (
    <div class="dash-col" data-testid="gm-players">
      <Block q={q}>
        {(d) => {
          const text = filter.trim().toLowerCase();
          const shown = d.players.filter((p) => !text || p.name.toLowerCase().includes(text))
            .sort((a, b) => Number(b.online) - Number(a.online) || a.name.localeCompare(b.name));
          return (
            <>
              <div class="row wrap" style={{ gap: "10px" }}>
                <label class="gm-search grow">
                  <Search size={16} />
                  <input class="input" type="search" placeholder="Buscar a una persona…" value={filter} onInput={(e) => setFilter(e.currentTarget.value)} aria-label="Buscar a una persona" data-testid="gm-player-search" />
                </label>
                <ConfirmButton icon={HeartPulse} confirm="Sí, a todos" onConfirm={resetAll} disabled={busy !== null || d.players.length === 0} testid="gm-hp-all">Restaurar la vida de todos</ConfirmButton>
              </div>
              <p class="faint gm-hint">{plural(d.players.length, "persona", "personas")} · {d.players.filter((p) => p.online).length} en la Actividad ahora.</p>
              {shown.length === 0 ? <Empty icon={Users} title="No hay nadie con ese nombre">Prueba con otra búsqueda.</Empty>
                : <div class="gm-players">{shown.map((p) => <Row key={p.id} p={p} onOpen={onOpen} />)}</div>}
            </>
          );
        }}
      </Block>
    </div>
  );
}

// ---- one person ---------------------------------------------------------------------------------------------------------------------
function Health({ row, id, replace }) {
  const hp = row.hp || { current: 100, max: 100, alive: true };
  const form = useDraft({ current: String(hp.current), max: String(hp.max) });
  const [busy, run] = useDo();
  const { draft, edit } = form;
  const apply = async (e) => {
    e.preventDefault();
    const sent = draft;
    const out = await run("hp", "gm.hp", { id, current: parseNumber(sent.current), max: parseNumber(sent.max) }, "Vida cambiada.");
    if (out) { form.saved(sent); replace(out); }
  };
  const full = async () => {
    const out = await run("full", "gm.hp_reset", { id }, "Vida restaurada.");
    if (out) { form.saved(); replace(out); }
  };
  return (
    <Card title="Vida" icon={Heart} testid="gm-hp" actions={!row.hp ? <Pill>Sin vida registrada</Pill> : hp.alive ? hp.revenge ? <Pill tone="warn">Modo venganza</Pill> : null : <Pill tone="bad">Caído</Pill>}>
      <form noValidate class="col" style={{ gap: "var(--sp-3)" }} onSubmit={apply}>
        <div class="gm-grid">
          <Field label="Vida actual" hint={!hp.alive ? "Al fijarla, vuelve al combate." : undefined}>
            <NumberInput value={draft.current} min={1} max={9999} step={5} unit="HP" label="Vida actual" testid="gm-hp-current" onInput={(current) => edit({ current })} />
          </Field>
          <Field label="Vida máxima"><NumberInput value={draft.max} min={1} max={9999} step={5} unit="HP" label="Vida máxima" testid="gm-hp-max" onInput={(max) => edit({ max })} /></Field>
        </div>
        <div class="row wrap" style={{ gap: "8px" }}>
          <button class="btn btn-primary" type="submit" disabled={busy !== null} data-testid="gm-hp-apply">Aplicar</button>
          <button class="btn" type="button" disabled={busy !== null} onClick={full} data-testid="gm-hp-full"><HeartPulse size={16} /> Restaurar al máximo</button>
        </div>
      </form>
    </Card>
  );
}

function Charges({ row, id, replace }) {
  const top = Math.max(100, Number(rules.value && rules.value.ultimateCost) || 100);
  const form = useDraft({ p1: String(row.charges[0]), p2: String(row.charges[1]) });
  const [busy, run] = useDo();
  const { draft, edit } = form;
  const save = async (e) => {
    e.preventDefault();
    const sent = draft;
    const out = await run("charges", "gm.charges", { id, power1: parseNumber(sent.p1), power2: parseNumber(sent.p2) }, "Cargas cambiadas.");
    if (out) { form.saved(sent); replace(out); }
  };
  const act = async (name, op, args, done) => {
    const out = await run(name, op, { id, ...args }, done);
    if (out) replace(out);
  };
  return (
    <Card title="Poderes y participación" icon={Zap} testid="gm-charges">
      <form noValidate class="col" style={{ gap: "var(--sp-3)" }} onSubmit={save}>
        <div class="gm-grid">
          <Field label="Carga del poder 1"><NumberInput value={draft.p1} min={0} max={top} step={5} unit="%" label="Carga del poder 1" testid="gm-charge-1" onInput={(p1) => edit({ p1 })} /></Field>
          <Field label="Carga del poder 2"><NumberInput value={draft.p2} min={0} max={top} step={5} unit="%" label="Carga del poder 2" testid="gm-charge-2" onInput={(p2) => edit({ p2 })} /></Field>
        </div>
        <div class="row wrap" style={{ gap: "8px" }}>
          <button class="btn btn-primary" type="submit" disabled={busy !== null} data-testid="gm-charges-save">Guardar cargas</button>
          <button class="btn" type="button" disabled={busy !== null} onClick={() => act("cooldowns", "gm.cooldowns", {}, "Recargas reiniciadas.")} data-testid="gm-cooldowns"><RotateCcw size={16} /> Reiniciar recargas</button>
        </div>
      </form>
      <div class="setting" style={{ marginTop: "var(--sp-3)" }}>
        <div class="info"><strong>Participa en los QTE</strong><span>Si lo apagas, el bot no le lanza QTE al azar.</span></div>
        <button type="button" role="switch" class="switch" aria-checked={row.afk ? "false" : "true"} aria-label="Participa en los QTE" disabled={busy !== null}
          onClick={() => act("afk", "gm.afk", { afk: !row.afk }, row.afk ? "Vuelve a los QTE." : "Queda fuera de los QTE.")} data-testid="gm-afk" />
      </div>
    </Card>
  );
}

// What /support did, as buttons: heal, a boost, charge, shorter cooldowns or a shield, for this player.
const SUPPORT = [["heal", "Curar", "PV", 30, false], ["shield", "Escudo", "%", 40, true], ["damage_boost", "Más daño", "%", 25, true], ["bf_boost", "Más Black Flash", "%", 10, true],
  ["ult_charge", "Carga de poder", "%", 25, false], ["cd_reduce", "Reducir recargas", "s", 60, false]];

function Support({ id, replace }) {
  const [kind, setKind] = useState("heal");
  const [value, setValue] = useState("30");
  const [seconds, setSeconds] = useState("30");
  const [busy, run] = useDo();
  const spec = SUPPORT.find((x) => x[0] === kind);
  const pick = (k) => { const s = SUPPORT.find((x) => x[0] === k); setKind(k); setValue(String(s[3])); };
  const give = async () => {
    const out = await run("support", "gm.support", { id, kind, value: parseNumber(value), duration: spec[4] ? parseNumber(seconds) ?? 0 : 0 }, "Apoyo aplicado.");
    if (out) replace(out);
  };
  return (
    <Card title="Apoyo" icon={Heart} testid="gm-support" hint="Lo que hacía /support: una ayuda inmediata para esta persona.">
      <div class="col" style={{ gap: "var(--sp-3)" }}>
        <div class="row wrap gm-chips" role="group" aria-label="Tipo de apoyo">
          {SUPPORT.map(([k, label]) => <button key={k} type="button" class="choice" aria-pressed={kind === k ? "true" : "false"} onClick={() => pick(k)} data-testid={`gm-support-${k}`}>{label}</button>)}
        </div>
        <div class="row wrap" style={{ gap: "8px", alignItems: "flex-end" }}>
          <Field label="Cantidad"><NumberInput value={value} min={1} max={1000} unit={spec[2]} label="Cantidad" testid="gm-support-value" onInput={setValue} /></Field>
          {spec[4] && <Field label="Durante (0 = el próximo golpe)"><NumberInput value={seconds} min={0} max={3600} unit="s" label="Duración" onInput={setSeconds} /></Field>}
          <button class="btn btn-primary" type="button" disabled={busy !== null} onClick={give} data-testid="gm-support-give">Aplicar</button>
        </div>
      </div>
    </Card>
  );
}

function Points({ d, id, replace }) {
  const [amount, setAmount] = useState("1");
  const [busy, run] = useDo();
  const ranks = Object.values(d.skills).reduce((sum, r) => sum + r, 0);
  const change = async (sign) => {
    const n = parseNumber(amount);
    const out = await run("points", "gm.points", { id, amount: n === null ? null : sign * Math.abs(n) }, sign > 0 ? "Puntos dados." : "Puntos quitados.");
    if (out) replace(out);
  };
  const reset = async () => {
    const out = await run("skills", "gm.skills_reset", { id }, "Habilidades reiniciadas.");
    if (out) replace(out);
  };
  return (
    <Card title="Puntos de habilidad" icon={Star} testid="gm-points" actions={<Pill tone="primary" title="Puntos sin gastar"><b class="num" data-testid="gm-points-now">{d.row.points}</b>&nbsp;disponibles</Pill>}>
      <div class="col" style={{ gap: "var(--sp-3)" }}>
        <div class="row wrap" style={{ gap: "8px" }}>
          <NumberInput value={amount} min={1} max={9999} step={1} label="Cantidad de puntos" testid="gm-points-amount" onInput={setAmount} width="120px" />
          <button class="btn" type="button" disabled={busy !== null} onClick={() => change(1)} data-testid="gm-points-give"><Plus size={16} /> Dar</button>
          <button class="btn" type="button" disabled={busy !== null} onClick={() => change(-1)} data-testid="gm-points-take">Quitar</button>
        </div>
        <div class="row wrap" style={{ gap: "8px", alignItems: "center" }}>
          <ConfirmButton icon={RotateCcw} confirm="Sí, reiniciar" onConfirm={reset} disabled={busy !== null || ranks === 0} testid="gm-skills-reset">Reiniciar habilidades</ConfirmButton>
          <span class="faint gm-hint">{ranks ? `Tiene ${plural(ranks, "rango aprendido", "rangos aprendidos")}; se le devuelven sus puntos.` : "No ha aprendido habilidades."}</span>
        </div>
      </div>
    </Card>
  );
}

function Achievements({ d, id, replace }) {
  const owned = new Set(d.achievements.map((a) => a.id));
  const options = d.catalog.achievements.filter((a) => !owned.has(a.id));
  const [pick, setPick] = useState("");
  const [busy, run] = useDo();
  const give = async () => {
    const out = await run("give", "gm.ach_give", { id, achievement: pick }, "Logro dado.");
    if (out) { setPick(""); replace(out); }
  };
  const remove = async (achievement) => {
    const out = await run(`rm-${achievement}`, "gm.ach_remove", { id, achievement }, "Logro quitado.");
    if (out) replace(out);
  };
  return (
    <Card title="Logros" icon={Trophy} testid="gm-achievements" actions={<span class="faint num" style={{ fontSize: ".75rem" }}>{d.achievements.length} de {d.catalog.achievements.length}</span>}>
      <div class="col" style={{ gap: "var(--sp-3)" }}>
        <div class="row wrap" style={{ gap: "8px" }}>
          <select class="select grow" value={pick} onChange={(e) => setPick(e.currentTarget.value)} aria-label="Logro que dar" data-testid="gm-ach-pick">
            <option value="">Elige un logro para darle…</option>
            {options.map((a) => <option key={a.id} value={a.id}>{a.icon} {a.name}{a.hidden ? " (secreto)" : ""}</option>)}
          </select>
          <button class="btn btn-primary" type="button" disabled={busy !== null || !pick} onClick={give} data-testid="gm-ach-give"><Plus size={16} /> Dar</button>
        </div>
        {d.achievements.length === 0 ? <p class="faint gm-hint">Todavía no tiene logros.</p> : (
          <ul class="gm-list">
            {d.achievements.map((a) => (
              <li key={a.id} class="gm-item" data-testid={`gm-ach-${a.id}`}>
                <Trophy size={16} />
                <div class="grow"><strong>{a.name}</strong>{a.date && <div class="faint" style={{ fontSize: ".75rem" }}>{a.date}</div>}</div>
                <ConfirmButton icon={Trash2} confirm="Quitar" label={`Quitar el logro ${a.name}`} onConfirm={() => remove(a.id)} disabled={busy !== null} testid={`gm-ach-remove-${a.id}`} />
              </li>
            ))}
          </ul>
        )}
        {d.titles.length > 0 && <div class="row wrap" style={{ gap: "6px" }}><span class="faint gm-hint">Títulos:</span>{d.titles.map((t) => <Pill key={t}>{t}</Pill>)}</div>}
      </div>
    </Card>
  );
}

function ObjectRow({ o, id, replace }) {
  const keys = o.tracking.kind === "total" ? ["total"] : DIFFS;
  const current = Object.fromEntries(keys.map((k) => [k, String((o.tracking.rows.find((r) => r.key === k) || { spins: 0 }).spins)]));
  const form = useDraft(current);
  const [busy, run] = useDo();
  const rarity = rarityOf(o.rarity);
  const save = async () => {
    const sent = form.draft;
    const values = Object.fromEntries(keys.map((k) => [k, parseNumber(sent[k])]));
    const out = await run("spins", "gm.obj_spins", { id, object: o.id, values }, "Vueltas cambiadas.");
    if (out) { form.saved(sent); replace(out); }
  };
  const reset = async () => {
    const out = await run("reset", "gm.obj_spins", { id, object: o.id, reset: true }, "Vueltas reiniciadas.");
    if (out) { form.saved(); replace(out); }
  };
  const take = async () => {
    const out = await run("take", "gm.obj_take", { id, object: o.id }, "Objeto quitado.");
    if (out) replace(out);
  };
  return (
    <li class="gm-obj" data-testid={`gm-obj-${o.id}`} style={{ "--rarity": rarity.color }}>
      <div class="row" style={{ gap: "10px" }}>
        <span class="gm-obj-icon">{o.emoji}</span>
        <div class="grow"><strong>{o.name}</strong><div class="row wrap" style={{ gap: "6px", marginTop: "2px" }}><Pill>{rarity.label}</Pill>{o.unique && <Pill tone="warn">Único</Pill>}</div></div>
        <ConfirmButton icon={Trash2} confirm="Quitar" label={`Quitar ${o.name}`} onConfirm={take} disabled={busy !== null} testid={`gm-obj-take-${o.id}`} />
      </div>
      <div class="gm-spins">
        {keys.map((k) => (
          <label key={k} class="field">
            <span class="field-label">{TRACK_LABEL[k] || k}</span>
            <NumberInput value={form.draft[k]} min={0} max={99999} step={1} label={`Vueltas ${TRACK_LABEL[k] || k} de ${o.name}`} testid={`gm-spins-${o.id}-${k}`} onInput={(v) => form.edit({ [k]: v })} />
          </label>
        ))}
      </div>
      <div class="row wrap" style={{ gap: "8px" }}>
        <button class="btn btn-sm btn-primary" type="button" disabled={busy !== null} onClick={save} data-testid={`gm-spins-save-${o.id}`}>Guardar vueltas</button>
        <button class="btn btn-sm" type="button" disabled={busy !== null} onClick={reset} data-testid={`gm-spins-reset-${o.id}`}><RotateCcw size={14} /> Reiniciar</button>
      </div>
    </li>
  );
}

function Objects({ d, id, replace }) {
  const inventory = d.inventory;
  const mine = new Set(inventory.objects.map((o) => o.id));
  const options = d.catalog.objects.filter((o) => !mine.has(o.id) && (!o.unique || !o.owner));
  const [pick, setPick] = useState("");
  const slots = useDraft({ slots: String(inventory.slots[1]) });
  const [busy, run] = useDo();
  const give = async () => {
    const out = await run("give", "gm.obj_give", { id, object: pick }, "Objeto dado.");
    if (out) { setPick(""); replace(out); }
  };
  const setSlots = async () => {
    const sent = slots.draft;
    const out = await run("slots", "gm.slots", { id, slots: parseNumber(sent.slots) }, "Espacios cambiados.");
    if (out) { slots.saved(sent); replace(out); }
  };
  return (
    <Card title="Objetos especiales" icon={Backpack} testid="gm-objects" actions={<span class="faint num" style={{ fontSize: ".75rem" }}>{inventory.slots[0]} de {inventory.slots[1]} espacios</span>}>
      <div class="col" style={{ gap: "var(--sp-3)" }}>
        <div class="row wrap" style={{ gap: "8px" }}>
          <select class="select grow" value={pick} onChange={(e) => setPick(e.currentTarget.value)} aria-label="Objeto que dar" data-testid="gm-obj-pick">
            <option value="">Elige un objeto para darle…</option>
            {options.map((o) => <option key={o.id} value={o.id}>{o.name}{o.unique ? " (único)" : ""}</option>)}
          </select>
          <button class="btn btn-primary" type="button" disabled={busy !== null || !pick} onClick={give} data-testid="gm-obj-give"><Plus size={16} /> Dar</button>
        </div>
        {inventory.objects.length === 0 ? <p class="faint gm-hint">No tiene objetos.</p> : <ul class="gm-objs">{inventory.objects.map((o) => <ObjectRow key={o.id} o={o} id={id} replace={replace} />)}</ul>}
        <Sub>Espacios del inventario</Sub>
        <div class="row wrap" style={{ gap: "8px" }}>
          <NumberInput value={slots.draft.slots} min={1} max={99} step={1} label="Espacios del inventario" testid="gm-slots" onInput={(v) => slots.edit({ slots: v })} width="120px" />
          <button class="btn" type="button" disabled={busy !== null} onClick={setSlots} data-testid="gm-slots-save">Cambiar</button>
        </div>
      </div>
    </Card>
  );
}

function Person({ id, onBack }) {
  const q = usePanel("gm.player", { id });
  return (
    <div class="dash-col" data-testid="gm-person">
      <div class="row" style={{ gap: "10px" }}>
        <button class="btn btn-sm" type="button" onClick={onBack} data-testid="gm-person-back"><ArrowLeft size={14} /> Todos</button>
      </div>
      <Block q={q}>
        {(d) => (
          <>
            <div class="hero gm-hero">
              <Avatar url={d.row.avatar} name={d.row.name} size="xl" />
              <div class="hero-main">
                <h2 data-testid="gm-person-name">{d.row.name}</h2>
                <div class="row wrap" style={{ gap: "6px" }}>
                  <Pill tone={d.row.online ? "ok" : undefined}>{d.row.online ? "En la Actividad" : "Fuera de la Actividad"}</Pill>
                  <Pill>{plural(d.row.characters, "personaje", "personajes")}</Pill>
                  {d.row.attempts > 0 && <Pill>{plural(d.row.attempts, "QTE", "QTE")} · {decimal(d.row.rate)} % de acierto</Pill>}
                </div>
              </div>
            </div>
            <Health row={d.row} id={id} replace={q.replace} />
            <Charges row={d.row} id={id} replace={q.replace} />
            <Support id={id} replace={q.replace} />
            <Points d={d} id={id} replace={q.replace} />
            <Achievements d={d} id={id} replace={q.replace} />
            <Objects d={d} id={id} replace={q.replace} />
          </>
        )}
      </Block>
    </div>
  );
}

export function PlayersTab() {
  const [selected, setSelected] = useState(null);
  return selected ? <Person key={selected} id={selected} onBack={() => setSelected(null)} /> : <List onOpen={setSelected} />;
}
