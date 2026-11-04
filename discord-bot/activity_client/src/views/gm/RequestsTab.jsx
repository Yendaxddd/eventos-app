// GM · Solicitudes: the cinematics players ask for their powers and actions. Watch it, then approve it (it plays each time that player
// does that) or send it back with a note. Only the game masters with this box see what is inside.
import { useEffect, useState } from "preact/hooks";
import { Check, Clapperboard, Eye, Inbox, Undo2 } from "lucide-preact";
import { usePanel } from "../../panel/data.js";
import { creqRev } from "../../state.js";
import { previewCine } from "../../cine.js";
import { Block, Empty, Pill } from "../../ui/Common.jsx";
import { STATUS } from "../panel/MyCinemas.jsx";
import { playable } from "./CinemaTab.jsx";
import { Card } from "./ui.jsx";
import { useDo } from "./hooks.js";

function Request({ c, run, busy }) {
  const [review, setReview] = useState(c.review || "");
  const [label, tone, Icon] = STATUS[c.status] || STATUS.pending;
  const decide = (status, done) => run(`${status}-${c.id}`, "gm.request_decide", { id: c.id, status, review }, done);
  return (
    <div class="creq-gm" data-testid={`request-${c.id}`}>
      <div class="row wrap" style={{ gap: "8px", alignItems: "flex-start" }}>
        <div class="grow" style={{ minWidth: 0 }}>
          <strong>{c.name}</strong> <span class="faint">de {c.owner?.name || "?"}</span>
          <div class="faint" style={{ fontSize: ".78rem" }}>{c.bindLabel} · {Math.round(c.duration - 1)} s · {c.steps.length} pasos · una vez cada {Math.round((c.bind?.cooldown ?? 300) / 60)} min</div>
          {c.note && <p class="creq-note">«{c.note}»</p>}
        </div>
        <Pill tone={tone} icon={Icon}>{label}</Pill>
      </div>
      <div class="row wrap" style={{ gap: "8px" }}>
        <button class="btn btn-sm" type="button" onClick={() => previewCine(playable(c))} data-testid={`request-watch-${c.id}`}><Eye size={14} /> Ver</button>
        <input class="input input-sm grow" maxLength={300} value={review} placeholder="Nota para el jugador (opcional): qué cambiar, o ¡qué buena!" onInput={(e) => setReview(e.currentTarget.value)} />
        {c.status !== "rejected" && <button class="btn btn-sm" type="button" disabled={busy !== null} onClick={() => decide("rejected", "Devuelta al jugador.")}><Undo2 size={14} /> Devolver</button>}
        {c.status !== "approved" && <button class="btn btn-sm btn-primary" type="button" disabled={busy !== null} onClick={() => decide("approved", "Aprobada: saldrá cuando la use.")} data-testid={`request-approve-${c.id}`}><Check size={14} /> Aprobar</button>}
      </div>
    </div>
  );
}

export function RequestsTab() {
  const q = usePanel("gm.requests");
  const [busy, run0] = useDo();
  const rev = creqRev.value;
  useEffect(() => { if (rev) q.refresh(); }, [rev]);
  const run = async (...args) => { const out = await run0(...args); if (out) q.replace(out); return out; };
  return (
    <Block q={q}>
      {(d) => {
        const pending = d.requests.filter((c) => c.status === "pending");
        const rest = d.requests.filter((c) => c.status !== "pending");
        return (
          <div class="col gm-stack" data-testid="gm-requests">
            <Card title={`Por revisar (${pending.length})`} icon={Inbox}
              hint="Cinemáticas que los jugadores piden para sus poderes y acciones. Aprobada, sale para todos cada vez que ese jugador hace eso (con su espera entre una y otra).">
              {pending.length === 0 && <Empty icon={Inbox} title="Nada por revisar">Cuando un jugador envíe una, aparecerá aquí (y te llegará un aviso).</Empty>}
              {pending.map((c) => <Request key={c.id} c={c} run={run} busy={busy} />)}
            </Card>
            {rest.length > 0 && (
              <Card title="Ya revisadas" icon={Clapperboard}>
                {rest.map((c) => <Request key={c.id} c={c} run={run} busy={busy} />)}
              </Card>
            )}
          </div>
        );
      }}
    </Block>
  );
}
