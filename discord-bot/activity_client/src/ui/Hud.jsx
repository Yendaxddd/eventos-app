import { useState } from "preact/hooks";
import { Crown, Flame, Skull, Swords, UserRound } from "lucide-preact";
import { GmDeck } from "./GmDeck.jsx";
import { activeAs, charAvatars, game, me, myHp, perms, users, you } from "../state.js";
import { clamp, cx, store } from "../util.js";
import { Avatar } from "./Avatar.jsx";
import { Actions } from "./Actions.jsx";
import { EffectChips, EffectIcons, Pops } from "./Effects.jsx";

const levelOf = (hp, max) => {
  const pct = max ? hp / max : 0;
  return pct <= 0.25 ? "low" : pct <= 0.5 ? "mid" : "ok";
};

export function Bar({ value, max, kind = "hp", label, thin, tall, ready, class: className }) {
  const pct = max ? clamp((value / max) * 100, 0, 100) : 0;
  return (
    <div class={cx("bar", kind !== "hp" && kind, thin && "thin", tall && "tall", ready && "ready", className)}
      role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
      <i style={{ width: `${pct}%` }} data-level={kind === "hp" ? levelOf(value, max) : undefined} />
      {label && <em>{label}</em>}
    </div>
  );
}

export function BossCard() {
  const g = game.value;
  const boss = g && g.boss;
  if (!boss) return null;
  return (
    <div class="boss-card" data-testid="boss">
      <div class="boss-ico"><Skull size={22} /></div>
      <div class="boss-main">
        <Pops target="boss" />
        <div class="boss-top">
          <strong class="ellipsis">{boss.name}</strong>
          <EffectIcons kinds={(boss.effects || []).map((e) => e.kind)} />
          {g.fight && <span class="chip bad"><Swords size={12} /> En combate</span>}
          <span class="num">{boss.hp} / {boss.max}</span>
        </div>
        <Bar kind="boss" value={boss.hp} max={boss.max} />
      </div>
    </div>
  );
}

// one power's charge: a bar, and a glow when it is ready
function Charge({ label, pct, cost }) {
  const ready = pct >= cost;
  return (
    <div class="stat-line">
      <span class="label">{label}</span>
      <Bar kind="charge" value={pct} max={cost} thin ready={ready} />
      <span class="val num" style={ready ? { color: "var(--charge-hi)" } : undefined}>{ready ? "LISTO" : `${Math.round(pct)} %`}</span>
    </div>
  );
}

export function MeCard() {
  const who = you.value;
  const hp = myHp.value;
  const m = me.value;
  const as = activeAs.value;
  const name = as === "me" ? (who ? who.name : "—") : as;
  const avatar = as === "me" ? who && who.avatar : charAvatars.value[as];
  return (
    <div class="me-card" data-testid="me-card">
      <div class="me-id">
        <Avatar url={avatar} name={name} size="lg" />
        <div class="names">
          <strong class="ellipsis">{name}</strong>
          <small>{as === "me" ? "Tú" : `Tú, como ${as}`}</small>
        </div>
        {m && m.streak > 1 && <span class="streak" title="Esquivas seguidas" style={{ marginLeft: "auto" }}><Flame size={16} /> {m.streak}</span>}
      </div>
      {hp && hp.revenge && <div class="stat-line"><span class="revenge">REVENGE · +daño, parry más estrecho</span></div>}
      {hp ? (
        <div class="stat-line" style={{ position: "relative" }}>
          <span class="label">HP</span>
          <Bar value={hp.hp} max={hp.max} tall />
          <span class="val num">{hp.hp}/{hp.max}</span>
          {who && <Pops target={String(who.id)} />}
        </div>
      ) : (
        <div class="stat-line faint">Sin HP todavía: aparecerá cuando participes en un QTE.</div>
      )}
      {m && <EffectChips effects={m.effects} buffs={m.buffs} />}
      {m && m.charges && (
        <>
          <Charge label="Poder 1" pct={m.charges.power1} cost={m.cost || 100} />
          <Charge label="Poder 2" pct={m.charges.power2} cost={m.cost || 100} />
        </>
      )}
    </div>
  );
}

export function PlayersPanel() {
  const g = game.value;
  const players = g ? g.players : [];
  const mine = you.value && you.value.id;
  return (
    <div class="panel" data-testid="players-panel">
      <div class="panel-head"><span class="eyebrow">Jugadores</span><span class="chip" style={{ marginLeft: "auto" }}>{players.length}</span></div>
      <div class="panel-body tight">
        <ul class="players">
          {players.length === 0 && <li class="faint" style={{ padding: "8px" }}>Nadie ha entrado en combate todavía.</li>}
          {players.map((p) => (
            <li key={p.id} class={cx("player", p.id === mine && "is-me")}>
              <Avatar name={p.name} size="sm" />
              <div class="p-main">
                <div class="p-top"><b>{p.name}</b><EffectIcons kinds={p.effects || []} /><span class="num">{p.hp}/{p.max}</span></div>
                <Pops target={p.id} />
                <Bar value={p.hp} max={p.max} />
              </div>
            </li>
          ))}
        </ul>
        <div class="eyebrow" style={{ padding: "10px 8px 4px" }}>En la Actividad</div>
        <ul class="online">
          {users.value.map((u) => (
            <li key={u.id}><Avatar url={u.avatar} name={u.name} size="sm" /><span class="ellipsis">{u.name}</span></li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function RightPanel() {
  const isGm = perms.value.gm;
  const [tab, setTab] = useState(() => store.get("eventos.rightTab") || "me");
  const shown = isGm ? tab : "me";
  const choose = (value) => { setTab(value); store.set("eventos.rightTab", value); };
  return (
    <div class="panel" data-testid="right-panel">
      {isGm ? (
        <div class="panel-tabs" role="tablist" aria-label="Panel lateral">
          <button type="button" role="tab" aria-selected={shown === "me" ? "true" : "false"} onClick={() => choose("me")} data-testid="side-tab-me"><UserRound size={13} /> Mi personaje</button>
          <button type="button" role="tab" aria-selected={shown === "gm" ? "true" : "false"} onClick={() => choose("gm")} data-testid="side-tab-gm"><Crown size={13} /> Mando del GM</button>
        </div>
      ) : (
        <div class="panel-head"><span class="eyebrow"><UserRound size={12} style={{ verticalAlign: "-2px" }} /> Mi personaje</span></div>
      )}
      <div class="panel-body">
        {shown === "gm" ? <GmDeck /> : (
          <>
            <MeCard />
            <Actions variant="grid" />
          </>
        )}
      </div>
    </div>
  );
}

// small screens: the essentials in one strip
export function MiniHud() {
  const hp = myHp.value, m = me.value, who = you.value, as = activeAs.value;
  const name = as === "me" ? (who ? who.name : "—") : as;
  const avatar = as === "me" ? who && who.avatar : charAvatars.value[as];
  return (
    <div class="mini-hud" data-testid="mini-hud">
      <Avatar url={avatar} name={name} />
      <div class="mh-main">
        <div class="mh-row">
          {hp ? <><Bar value={hp.hp} max={hp.max} /><span class="tiny num">{hp.hp}/{hp.max}</span></> : <span class="faint" style={{ fontSize: ".75rem" }}>Sin HP todavía</span>}
          {hp && hp.revenge && <span class="revenge">REVENGE</span>}
          {who && <Pops target={String(who.id)} />}
        </div>
        {m && ((m.effects && m.effects.length) || (m.buffs && m.buffs.length)) ? <EffectChips effects={m.effects} buffs={m.buffs} compact /> : null}
        {m && m.charges && (
          <div class="mh-row">
            <Bar kind="charge" thin value={m.charges.power1} max={m.cost || 100} ready={m.charges.power1 >= (m.cost || 100)} />
            <Bar kind="charge" thin value={m.charges.power2} max={m.cost || 100} ready={m.charges.power2 >= (m.cost || 100)} />
            {m.streak > 1 && <span class="streak"><Flame size={13} /> {m.streak}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
