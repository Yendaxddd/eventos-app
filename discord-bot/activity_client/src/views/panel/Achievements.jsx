import { useState } from "preact/hooks";
import { Check, CircleCheck, Crown, Lock, Orbit, Sparkles } from "lucide-preact";
import { Bar } from "../../ui/Hud.jsx";
import { Block, Empty, Pill } from "../../ui/Common.jsx";
import { act, usePanel } from "../../panel/data.js";
import { DOMAIN_TYPE, duration, plural } from "../../panel/format.js";
import { cx } from "../../util.js";

function Achievement({ a }) {
  const state = a.unlocked ? "done" : a.secret ? "secret" : "locked";
  const r = a.reward || {};
  return (
    <article class="ach" data-state={state} data-testid={`ach-${a.id}`}>
      <span class="ach-icon" aria-hidden="true">{state === "secret" ? <Lock size={22} /> : a.icon}</span>
      <div class="ach-main">
        <strong>{a.name}</strong>
        <p>{a.description}</p>
        {a.progress && (
          <div class="ach-progress" data-testid={`ach-progress-${a.id}`}>
            <Bar kind="charge" value={a.progress.have} max={a.progress.need} thin />
            <span class="num">{a.progress.have} / {a.progress.need}</span>
          </div>
        )}
        {state !== "secret" && (r.points > 0 || r.title || r.domain) && (
          <div class="row wrap" style={{ gap: "6px" }}>
            {r.points > 0 && <Pill tone="info" icon={Sparkles}>+{plural(r.points, "punto", "puntos")}</Pill>}
            {r.title && <Pill icon={Crown}>{r.title}</Pill>}
            {r.domain && <Pill tone="primary" icon={Orbit}>{r.domain}</Pill>}
          </div>
        )}
        {a.unlocked && a.date && <small class="faint">Conseguido el {a.date.slice(0, 10)}</small>}
      </div>
      {a.unlocked && <CircleCheck class="ach-check" size={20} aria-label="Conseguido" />}
    </article>
  );
}

function Titles({ d, replace }) {
  const pick = async (title) => {
    const out = await act("panel.title", { title }, title ? "Título cambiado." : "Título quitado.");
    if (out) replace({ ...d, activeTitle: out.activeTitle });
  };
  return (
    <section class="card-2" data-testid="titles">
      <div class="card-title"><Crown size={16} /><strong class="display">Tu título</strong><span class="faint" style={{ fontSize: ".75rem" }}>Se muestra junto a tus acciones</span></div>
      {d.titles.length === 0
        ? <p class="faint" style={{ fontSize: ".875rem" }}>Aún no has ganado títulos. Los dan algunos logros.</p>
        : (
          <div class="row wrap" style={{ gap: "8px" }}>
            <button type="button" class="choice" aria-pressed={d.activeTitle ? "false" : "true"} onClick={() => pick(null)} data-testid="title-none">Sin título</button>
            {d.titles.map((t) => (
              <button key={t.id} type="button" class="choice" aria-pressed={d.activeTitle === t.id ? "true" : "false"} onClick={() => pick(t.id)} data-testid={`title-${t.id}`}>
                {d.activeTitle === t.id && <Check size={14} />}{t.name}
              </button>
            ))}
          </div>
        )}
    </section>
  );
}

function Domains({ d, replace }) {
  const pick = async (id) => {
    const out = await act("panel.domain", { id }, "Dominio cambiado.");
    if (out) replace({ ...d, domains: d.domains.map((x) => ({ ...x, active: x.id === out.activeDomain })) });
  };
  return (
    <section class="card-2" data-testid="domains">
      <div class="card-title"><Orbit size={16} /><strong class="display">Tu expansión de dominio</strong><span class="faint" style={{ fontSize: ".75rem" }}>La que se lanza con <span class="kbd">*domain*</span></span></div>
      {d.domains.length === 0
        ? <p class="faint" style={{ fontSize: ".875rem" }}>Todavía no tienes ningún dominio. Se consiguen con los logros de la categoría «Expansión de dominio».</p>
        : (
          <div class="cards">
            {d.domains.map((x) => (
              <article key={x.id} class={cx("domain", x.active && "is-active")} data-testid={`domain-${x.id}`} data-active={x.active ? "1" : "0"}>
                <div class="row" style={{ gap: "8px" }}>
                  <strong class="display grow">{x.name}</strong>
                  <Pill>{DOMAIN_TYPE[x.type] || x.type}</Pill>
                </div>
                {x.japanese && <small class="faint">{x.japanese}</small>}
                <p>{x.description}</p>
                <div class="row wrap" style={{ gap: "6px" }}>
                  <Pill>Preparación {duration(x.cast)}</Pill>
                  <Pill tone={x.left ? "warn" : "ok"}>{x.left ? `Disponible en ${duration(x.left)}` : `Recarga ${duration(x.cooldown)} · lista`}</Pill>
                </div>
                <button class={cx("btn btn-sm", x.active ? "btn-ghost" : "btn-primary")} type="button" disabled={x.active} onClick={() => pick(x.id)} data-testid={`domain-use-${x.id}`}>
                  {x.active ? <><Check size={14} /> En uso</> : "Usar este dominio"}
                </button>
              </article>
            ))}
          </div>
        )}
    </section>
  );
}

function Achievements({ d, replace }) {
  const [cat, setCat] = useState("all");
  const shown = cat === "all" ? d.categories : d.categories.filter((c) => c.id === cat);
  return (
    <div class="dash-col" data-testid="achievements">
      <section class="card-2">
        <div class="row" style={{ gap: "var(--sp-3)" }}>
          <div class="grow">
            <strong class="display" style={{ fontSize: "1.125rem" }}>Logros conseguidos</strong>
            <div class="faint" style={{ fontSize: ".8125rem" }}>Dan puntos de habilidad, títulos y dominios.</div>
          </div>
          <b class="num big" data-testid="ach-count">{d.unlocked}<small> / {d.total}</small></b>
        </div>
        <Bar kind="charge" value={d.unlocked} max={d.total || 1} tall class="mt" />
      </section>

      <Titles d={d} replace={replace} />
      <Domains d={d} replace={replace} />

      {d.categories.length > 1 && (
        <div class="row wrap" style={{ gap: "8px" }} role="group" aria-label="Categoría">
          <button type="button" class="choice" aria-pressed={cat === "all" ? "true" : "false"} onClick={() => setCat("all")}>Todos</button>
          {d.categories.map((c) => (
            <button key={c.id} type="button" class="choice" aria-pressed={cat === c.id ? "true" : "false"} onClick={() => setCat(c.id)} data-testid={`cat-${c.id}`}>{c.icon} {c.name}</button>
          ))}
        </div>
      )}

      {d.categories.length === 0 && <Empty title="No hay logros configurados">Quien dirige el evento todavía no ha creado ninguno.</Empty>}
      {shown.map((c) => (
        <section key={c.id} class="ach-cat" data-testid={`ach-cat-${c.id}`}>
          <h3 class="ach-cat-title" style={{ "--cat": c.color }}><span>{c.icon}</span> {c.name} <small class="num">{c.items.filter((i) => i.unlocked).length} / {c.items.length}</small></h3>
          <div class="cards">{c.items.map((a) => <Achievement key={a.id} a={a} />)}</div>
        </section>
      ))}
    </div>
  );
}

export function AchievementsTab() {
  const q = usePanel("panel.achievements");
  return <Block q={q}>{(d) => <Achievements d={d} replace={q.replace} />}</Block>;
}
