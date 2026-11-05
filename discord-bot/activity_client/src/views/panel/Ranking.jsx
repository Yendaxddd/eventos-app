import { useState } from "preact/hooks";
import { Crown } from "lucide-preact";
import { Avatar } from "../../ui/Avatar.jsx";
import { Block, Empty } from "../../ui/Common.jsx";
import { usePanel } from "../../panel/data.js";
import { BOARD, plural } from "../../panel/format.js";
import { cx } from "../../util.js";

const MEDAL = ["🥇", "🥈", "🥉"];

function Row({ r }) {
  return (
    <li class={cx("board-row", r.me && "is-me")} data-testid={`board-${r.rank}`}>
      <b class="place num">{r.rank <= 3 ? MEDAL[r.rank - 1] : r.rank}</b>
      <Avatar url={r.avatar} name={r.name} />
      <span class="grow ellipsis">{r.name}{r.me && <em> (tú)</em>}</span>
      <b class="num value">{r.text}</b>
    </li>
  );
}

function Board({ d, category }) {
  const meta = BOARD.find(([id]) => id === category);
  const podium = d.rows.length >= 3;                       // with fewer than three people a podium looks empty: a plain list instead
  const top = d.rows.slice(0, 3);
  return (
    <div class="col" style={{ gap: "var(--sp-4)" }}>
      <p class="faint" style={{ fontSize: ".875rem" }}>{meta ? meta[2] : ""} · {plural(d.total, "jugador", "jugadores")} con datos</p>
      {d.rows.length === 0
        ? <Empty icon={Crown} title="Nadie aparece todavía">En cuanto alguien participe en un QTE, el ranking se llena.</Empty>
        : (
          <>
            {podium && (
              <div class="podium" data-testid="podium">
                {[top[1], top[0], top[2]].map((r) => (
                  <div key={r.id} class={cx("podium-step", `p${r.rank}`, r.me && "is-me")} data-testid={`podium-${r.rank}`}>
                    <span class="step" aria-hidden="true">{MEDAL[r.rank - 1]}</span>
                    <Avatar url={r.avatar} name={r.name} size="lg" />
                    <strong class="ellipsis">{r.name}{r.me && " (tú)"}</strong>
                    <b class="num">{r.text}</b>
                  </div>
                ))}
              </div>
            )}
            <ol class="board" data-testid="board">{d.rows.slice(podium ? 3 : 0).map((r) => <Row key={r.id} r={r} />)}</ol>
          </>
        )}
      {d.me && (
        <div class="board-me" data-testid="board-me">
          <span class="faint" style={{ fontSize: ".75rem" }}>Tu puesto</span>
          <ol class="board"><Row r={d.me} /></ol>
        </div>
      )}
    </div>
  );
}

export function RankingTab() {
  const [category, setCategory] = useState("success_rate");
  const q = usePanel("panel.board", { category });
  return (
    <div class="dash-col" data-testid="ranking">
      <div class="row wrap" style={{ gap: "8px" }} role="group" aria-label="Clasificación">
        {BOARD.map(([id, label]) => <button key={id} type="button" class="choice" aria-pressed={category === id ? "true" : "false"} onClick={() => setCategory(id)} data-testid={`board-tab-${id}`}>{label}</button>)}
      </div>
      <Block q={q}>{(d) => <Board d={d} category={category} />}</Block>
    </div>
  );
}
