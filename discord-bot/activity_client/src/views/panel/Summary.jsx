import { Award, Backpack, Crown, Drama, Flame, GitBranch, Orbit, Sparkles, Target, Timer, Trophy, Zap } from "lucide-preact";
import { openTab, you } from "../../state.js";
import { Avatar } from "../../ui/Avatar.jsx";
import { Bar } from "../../ui/Hud.jsx";
import { Block, Pill, Stat } from "../../ui/Common.jsx";
import { Switch } from "../../ui/Controls.jsx";
import { act, usePanel } from "../../panel/data.js";
import { BOARD, chartPoints, decimal, num, plural } from "../../panel/format.js";

// the response times of the last QTEs, faster answers higher
function TimesChart({ times, best, avg }) {
  const W = 600, H = 120;
  const { points } = chartPoints(times, W, H, 8);
  if (points.length < 2) return <p class="faint" style={{ fontSize: ".8125rem" }}>Todavía no hay suficientes respuestas para dibujar la gráfica.</p>;
  const line = points.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `${points[0][0]},${H} ${line} ${points[points.length - 1][0]},${H}`;
  return (
    <div class="chart" data-testid="times-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`Tus últimos ${times.length} tiempos de respuesta${best ? `; el mejor, ${decimal(best, 2)} segundos` : ""}`}>
        <defs>
          <linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--primary-2)" stop-opacity=".45" /><stop offset="1" stop-color="var(--primary-2)" stop-opacity="0" /></linearGradient>
        </defs>
        <polygon points={area} fill="url(#chart-fill)" />
        <polyline points={line} fill="none" stroke="var(--primary-2)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
        {points.map(([x, y], i) => (i === points.length - 1 ? <circle key={i} cx={x} cy={y} r="4.5" fill="var(--parry)" stroke="var(--surface-2)" stroke-width="2" vector-effect="non-scaling-stroke" /> : null))}
      </svg>
      <div class="chart-legend"><span>Más arriba = más rápido</span><span>{best ? `Mejor ${decimal(best, 2)} s` : ""}{best && avg ? " · " : ""}{avg ? `Media ${decimal(avg, 2)} s` : ""}</span></div>
    </div>
  );
}

function Summary({ p, replace }) {
  const who = you.value;
  const s = p.stats;
  const setActive = async (active) => {
    const out = await act("panel.active", { active }, active ? "Vuelves a participar en los QTE." : "Ya no te elegirán en los QTE.");
    if (out) replace({ ...p, active: out.active });
  };
  const [done, total] = p.counts.achievements;
  return (
    <div class="dash-col" data-testid="summary">
      <section class="hero">
        <Avatar url={who && who.avatar} name={who ? who.name : "?"} size="xl" />
        <div class="hero-main">
          <h2 class="display" data-testid="hero-name">{who ? who.name : "—"}</h2>
          <div class="row wrap" style={{ gap: "6px" }}>
            {p.title ? <Pill tone="primary" icon={Crown}>{p.title}</Pill> : <Pill>Sin título</Pill>}
            {p.domain && <Pill icon={Orbit}>{p.domain.name}</Pill>}
            <Pill tone="info" icon={Sparkles}>{plural(p.points, "punto", "puntos")} de habilidad</Pill>
          </div>
        </div>
        <div class="hero-active">
          <Switch label="Participar en los QTE" checked={p.active} onChange={setActive} />
          <span>{p.active ? "Participas en los QTE" : "Fuera de los QTE"}</span>
        </div>
      </section>

      <div class="stat-grid">
        <Stat testid="stat-rate" icon={Target} label="Aciertos" tone="ok" value={`${num(s.rate)} %`} sub={`${s.ok} de ${plural(s.attempts, "QTE", "QTE")}`} />
        <Stat testid="stat-bf" icon={Zap} label="Black Flash" tone="bf" value={s.bf} sub={`Probabilidad ${num(s.bfChance)} %`} />
        <Stat testid="stat-streak" icon={Flame} label="Racha" tone="warn" value={s.streak} sub={`Mejor racha: ${s.bestStreak}`} />
        <Stat testid="stat-time" icon={Timer} label="Mejor tiempo" value={s.best ? `${decimal(s.best, 2)} s` : "—"} sub={s.avg ? `Media ${decimal(s.avg, 2)} s` : "Sin datos"} />
      </div>

      <div class="stat-grid small">
        <Stat label="Esquives" value={s.evades} sub={`Racha ${s.evadeStreak} · mejor ${s.bestEvadeStreak}`} />
        <Stat label="Parries" value={s.parries} sub={`Racha ${s.parryStreak} · ×${num(s.multiplier)} de daño`} />
        <Stat label="Rescates" value={s.saves} />
        <Stat label="Adaptaciones" value={s.adapts} />
        <Stat label="Fallos" value={s.failed} />
      </div>

      <section class="card-2">
        <div class="card-title"><Zap size={16} /><strong class="display">Cargas de poder</strong></div>
        <div class="col" style={{ gap: "var(--sp-3)" }}>
          {p.charges.map((c) => (
            <div key={c.slot} class="charge-row" data-testid={`charge-${c.slot}`} data-ready={c.ready ? "1" : "0"}>
              <div class="charge-head">
                <strong>{c.name}</strong>
                {c.character && <span class="faint">{c.character}</span>}
                <span class="grow" />
                <span class="num charge-pct">{c.ready ? "¡LISTA!" : `${Math.round(c.pct)} %`}</span>
              </div>
              <Bar kind="charge" value={c.pct} max={p.cost} ready={c.ready} tall />
            </div>
          ))}
          <p class="faint" style={{ fontSize: ".75rem" }}>Se usan en combate escribiendo <span class="kbd">*power1*</span> o <span class="kbd">*power2*</span> con la carga al {p.cost} %.</p>
        </div>
      </section>

      <section class="card-2">
        <div class="card-title"><Timer size={16} /><strong class="display">Tus últimos tiempos de respuesta</strong></div>
        <TimesChart times={s.times} best={s.best} avg={s.avg} />
      </section>

      <div class="shortcuts">
        <button class="shortcut" type="button" onClick={() => openTab("achievements")} data-testid="go-achievements">
          <Trophy size={20} /><b class="num">{done}<small> / {total}</small></b><span>Logros</span>
          <Bar kind="charge" value={done} max={total || 1} thin />
        </button>
        <button class="shortcut" type="button" onClick={() => openTab("skills")} data-testid="go-skills">
          <GitBranch size={20} /><b class="num">{p.points}</b><span>Puntos de habilidad</span><small>{plural(p.counts.skills, "habilidad aprendida", "habilidades aprendidas")}</small>
        </button>
        <button class="shortcut" type="button" onClick={() => openTab("characters")} data-testid="go-characters">
          <Drama size={20} /><b class="num">{p.counts.characters}</b><span>Personajes</span><small>registrados</small>
        </button>
        <button class="shortcut" type="button" onClick={() => openTab("inventory")} data-testid="go-inventory">
          <Backpack size={20} /><b class="num">{p.counts.objects}</b><span>Objetos</span><small>{p.counts.slots[0]} de {p.counts.slots[1]} espacios</small>
        </button>
      </div>

      <section class="card-2">
        <div class="card-title"><Award size={16} /><strong class="display">Tus puestos</strong><span class="faint" style={{ fontSize: ".75rem" }}>entre {plural(p.players, "jugador", "jugadores")}</span></div>
        {Object.keys(p.ranks).length === 0
          ? <p class="faint" style={{ fontSize: ".875rem" }}>Participa en algún QTE y aparecerás en el ranking.</p>
          : <div class="row wrap" style={{ gap: "8px" }}>
              {BOARD.filter(([id]) => p.ranks[id]).map(([id, label]) => (
                <button key={id} type="button" class={`chip rank-chip ${p.ranks[id] <= 3 ? "ok" : ""}`} onClick={() => openTab("ranking")}>
                  <b class="num">#{p.ranks[id]}</b> {label}
                </button>
              ))}
            </div>}
      </section>
    </div>
  );
}

export function SummaryTab() {
  const q = usePanel("panel.profile");
  return <Block q={q}>{(p) => <Summary p={p} replace={q.replace} />}</Block>;
}
