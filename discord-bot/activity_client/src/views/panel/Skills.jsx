import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { Check, GitBranch, Lock, Sparkles } from "lucide-preact";
import { toast } from "../../state.js";
import { Modal } from "../../ui/Overlays.jsx";
import { Block, Empty, Pill } from "../../ui/Common.jsx";
import { act, usePanel } from "../../panel/data.js";
import { plural, skillStatus, tiersOf } from "../../panel/format.js";
import { cx } from "../../util.js";

// The lines from each skill to the ones it needs, measured from where the cards really are (they wrap on a phone).
function Lines({ boxRef, skills }) {
  const [paths, setPaths] = useState([]);
  useLayoutEffect(() => {
    const box = boxRef.current;
    if (!box) return undefined;
    const measure = () => {
      const origin = box.getBoundingClientRect();
      const next = [];
      for (const s of skills) {
        for (const need of s.needs) {
          const from = box.querySelector(`[data-id="${CSS.escape(need.id)}"]`), to = box.querySelector(`[data-id="${CSS.escape(s.id)}"]`);
          if (!from || !to) continue;          // it needs something from another branch: no line
          const a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
          const x1 = a.left - origin.left + a.width / 2, y1 = a.bottom - origin.top, x2 = b.left - origin.left + b.width / 2, y2 = b.top - origin.top;
          const mid = (y1 + y2) / 2;
          next.push({ key: `${need.id}>${s.id}`, d: `M${x1},${y1} C${x1},${mid} ${x2},${mid} ${x2},${y2}`, met: need.met });
        }
      }
      setPaths(next);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const watcher = new ResizeObserver(measure);
    watcher.observe(box);
    return () => watcher.disconnect();
  }, [skills]);
  return (
    <svg class="skill-lines" aria-hidden="true">
      {paths.map((p) => <path key={p.key} d={p.d} class={p.met ? "met" : ""} fill="none" />)}
    </svg>
  );
}

function SkillCard({ s, onOpen }) {
  return (
    <button type="button" class="skill" data-id={s.id} data-state={s.state} data-testid={`skill-${s.id}`} onClick={() => onOpen(s)} aria-label={`${s.name}, rango ${s.rank} de ${s.max}`}>
      <span class="skill-state" aria-hidden="true">{s.state === "locked" ? <Lock size={14} /> : s.state === "maxed" ? <Check size={14} /> : null}</span>
      <strong>{s.name}</strong>
      <small>{s.description}</small>
      <span class="pips" aria-hidden="true">{Array.from({ length: s.max }, (_, i) => <i key={i} class={i < s.rank ? "on" : ""} />)}</span>
    </button>
  );
}

function SkillDialog({ s, points, onClose, onLearn, busy }) {
  const can = s.state === "available";
  return (
    <Modal title={s.name} onClose={onClose}
      actions={<><button class="btn btn-ghost" type="button" onClick={onClose}>Cerrar</button>
        <button class="btn btn-primary" type="button" disabled={!can || busy} onClick={() => onLearn(s)} data-testid="skill-learn">
          <Sparkles size={16} />{s.rank > 0 ? "Mejorar" : "Aprender"}{can ? ` · ${s.cost}` : ""}
        </button></>}>
      <div class="col" style={{ gap: "var(--sp-3)" }} data-testid="skill-dialog">
        <p>{s.description}</p>
        <div class="row wrap" style={{ gap: "6px" }}>
          <Pill tone={s.rank >= s.max ? "ok" : undefined}>Rango {s.rank} de {s.max}</Pill>
          <Pill tone="info" icon={Sparkles}>Cuesta {plural(s.cost, "punto", "puntos")}</Pill>
          <Pill>Nivel {s.tier}</Pill>
        </div>
        {s.needs.length > 0 && (
          <div class="col" style={{ gap: "4px" }}>
            <span class="field-label">Requiere</span>
            {s.needs.map((n) => <span key={n.id} class={cx("need", n.met && "met")}>{n.met ? <Check size={14} /> : <Lock size={14} />} {n.name}</span>)}
          </div>
        )}
        <p class="faint" style={{ fontSize: ".8125rem" }} data-testid="skill-status">{skillStatus(s, points)}. Tienes {plural(points, "punto", "puntos")}.</p>
      </div>
    </Modal>
  );
}

function Branch({ branch, points, onOpen }) {
  const boxRef = useRef(null);
  const tiers = tiersOf(branch.skills);
  return (
    <section class="branch" style={{ "--branch": branch.color }} data-testid={`branch-${branch.id}`}>
      <header class="branch-head">
        <span class="branch-icon">{branch.icon}</span>
        <div class="grow"><strong class="display">{branch.name}</strong>{branch.description && <small>{branch.description}</small>}</div>
        <Pill>{branch.skills.filter((s) => s.rank > 0).length} / {branch.skills.length}</Pill>
      </header>
      <div class="skill-tree" ref={boxRef}>
        <Lines boxRef={boxRef} skills={branch.skills} />
        {tiers.map((row) => (
          <div class="skill-row" key={row[0].tier}>
            {row.map((s) => <SkillCard key={s.id} s={s} onOpen={onOpen} />)}
          </div>
        ))}
      </div>
    </section>
  );
}

function Skills({ d, replace }) {
  const [treeId, setTreeId] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [busy, setBusy] = useState(false);
  const tree = d.trees.find((t) => t.id === treeId) || d.trees[0];
  const open = openId && d.trees.flatMap((t) => t.branches).flatMap((b) => b.skills).find((s) => s.id === openId);
  const learn = async (s) => {
    setBusy(true);
    const out = await act("panel.learn", { id: s.id });
    setBusy(false);
    if (out) {
      replace(out.skills);
      toast(`${s.name}: rango ${out.rank}.`, "ok");
    }
  };
  return (
    <div class="dash-col" data-testid="skills">
      <section class="card-2 row" style={{ gap: "var(--sp-4)" }}>
        <span class="points-orb" aria-hidden="true"><Sparkles size={22} /></span>
        <div class="grow">
          <strong class="display" style={{ fontSize: "1.125rem" }}>Puntos de habilidad</strong>
          <div class="faint" style={{ fontSize: ".8125rem" }}>Se ganan con los logros y los reparte quien dirige el evento.</div>
        </div>
        <b class="num big" data-testid="skill-points">{d.points}</b>
      </section>
      {d.trees.length === 0 && <Empty icon={GitBranch} title="No hay árbol de habilidades">Quien dirige el evento todavía no ha creado ninguno.</Empty>}
      {d.trees.length > 1 && (
        <div class="row wrap" style={{ gap: "8px" }} role="group" aria-label="Árbol">
          {d.trees.map((t) => <button key={t.id} type="button" class="choice" aria-pressed={tree && t.id === tree.id ? "true" : "false"} onClick={() => setTreeId(t.id)}>{t.name}</button>)}
        </div>
      )}
      {tree && (
        <>
          {tree.description && <p class="faint" style={{ fontSize: ".875rem" }}>{tree.name} · {tree.description}</p>}
          <div class="branches">{tree.branches.map((b) => <Branch key={b.id} branch={b} points={d.points} onOpen={(s) => setOpenId(s.id)} />)}</div>
        </>
      )}
      {open && <SkillDialog s={open} points={d.points} busy={busy} onClose={() => setOpenId(null)} onLearn={learn} />}
    </div>
  );
}

export function SkillsTab() {
  const q = usePanel("panel.skills");
  return <Block q={q}>{(d) => <Skills d={d} replace={q.replace} />}</Block>;
}
