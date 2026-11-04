import { useMemo, useState } from "preact/hooks";
import { Crown, KeyRound, Plus, ShieldCheck, Trash2, UserCog, Users } from "lucide-preact";
import { Avatar } from "../../ui/Avatar.jsx";
import { Block, ConfirmButton, Empty, Field, Pill } from "../../ui/Common.jsx";
import { usePanel } from "../../panel/data.js";
import { cx } from "../../util.js";
import { Card } from "./ui.jsx";
import { useDo } from "./hooks.js";

const presetOf = (perms, presets) => {
  const have = [...perms].sort().join(" ");
  const found = presets.find((p) => [...p.perms].sort().join(" ") === have);
  return found ? found.id : "custom";
};

// The boxes, with the presets on top to fill them in one click. A box the editor does not have themselves cannot be given.
export function PermEditor({ value, onChange, catalog, mine, testid }) {
  const preset = presetOf(value, catalog.presets);
  return (
    <div class="perm-editor" data-testid={testid}>
      <div class="row wrap gm-chips" role="group" aria-label="Preajustes">
        {catalog.presets.filter((p) => p.perms.every((b) => mine.includes(b))).map((p) => (
          <button key={p.id} type="button" class="choice" aria-pressed={preset === p.id ? "true" : "false"} title={p.hint}
            onClick={() => onChange([...p.perms])} data-testid={testid ? `${testid}-preset-${p.id}` : undefined}>{p.label}</button>
        ))}
        {preset === "custom" && <span class="choice" aria-pressed="true">Personalizado</span>}
      </div>
      <div class="perm-grid">
        {catalog.perms.map((p) => {
          const on = value.includes(p.id);
          const locked = !mine.includes(p.id);
          return (
            <label key={p.id} class={cx("perm-box", on && "on", locked && "locked")} title={locked ? "No tienes este permiso, así que no puedes darlo." : p.hint}>
              <input type="checkbox" checked={on} disabled={locked} data-testid={testid ? `${testid}-box-${p.id}` : undefined}
                onChange={(e) => onChange(e.currentTarget.checked ? [...value, p.id] : value.filter((x) => x !== p.id))} />
              <span><b>{p.label}</b><small>{p.hint}</small></span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function Summary({ perms, catalog }) {
  if (!perms.length) return <span class="faint">Sin permisos</span>;
  const preset = catalog.presets.find((p) => p.id === presetOf(perms, catalog.presets));
  if (preset && preset.id !== "none") return <Pill tone="info">{preset.label}</Pill>;
  const labels = Object.fromEntries(catalog.perms.map((p) => [p.id, p.label]));
  return <span class="faint perm-summary">{perms.map((p) => labels[p]).join(" · ")}</span>;
}

// One person or role of the team, with its boxes open to edit.
function Entry({ kind, entry, catalog, mine, run, busy, avatar, canRemove }) {
  const [open, setOpen] = useState(false);
  const [perms, setPerms] = useState(entry.perms || []);
  const dirty = JSON.stringify([...perms].sort()) !== JSON.stringify([...(entry.perms || [])].sort());
  return (
    <li class={cx("staff-row", open && "open")} data-testid={`staff-${kind}-${entry.id}`}>
      <div class="staff-head">
        {kind === "role" ? <span class="staff-role-dot" style={{ background: entry.color || "var(--text-faint)" }} /> : <Avatar url={avatar} name={entry.name || entry.id} size="sm" />}
        <strong class="ellipsis grow">{entry.name || entry.id}</strong>
        {kind === "host" ? <Pill tone="warn" icon={Crown}>Anfitrión</Pill> : <Summary perms={entry.perms} catalog={catalog} />}
        {kind !== "host" && <button type="button" class="btn btn-sm btn-ghost" onClick={() => setOpen(!open)} aria-expanded={open ? "true" : "false"}>{open ? "Cerrar" : "Editar"}</button>}
        {canRemove && (
          <ConfirmButton class="btn-sm btn-ghost" icon={Trash2} label="Quitar" confirm="Sí, quitar" disabled={busy === "rm"}
            onConfirm={() => run("rm", "gm.staff_remove", { kind, id: entry.id, name: entry.name }, "Quitado del equipo.")} />
        )}
      </div>
      {open && (
        <div class="staff-body">
          <PermEditor value={perms} onChange={setPerms} catalog={catalog} mine={mine} testid={`staff-${kind}-${entry.id}-perms`} />
          <div class="row" style={{ justifyContent: "flex-end", gap: "8px" }}>
            <button type="button" class="btn btn-sm btn-ghost" disabled={!dirty} onClick={() => setPerms(entry.perms || [])}>Deshacer</button>
            <button type="button" class="btn btn-sm btn-primary" disabled={!dirty || busy === "set"}
              onClick={async () => { const out = await run("set", "gm.staff_set", { kind, id: entry.id, name: entry.name, perms }, "Permisos guardados."); if (out) setOpen(false); }}>Guardar</button>
          </div>
        </div>
      )}
    </li>
  );
}

// Adding somebody (or a role) to the team.
function AddForm({ kind, options, catalog, mine, run, busy, onDone }) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState(null);
  const [perms, setPerms] = useState(catalog.presets.find((p) => p.id === "combat")?.perms.filter((b) => mine.includes(b)) || []);
  const found = useMemo(() => {
    const q = query.trim().toLowerCase();
    return options.filter((o) => !q || (o.name || "").toLowerCase().includes(q) || o.id.includes(q)).slice(0, 12);
  }, [query, options]);
  const manual = /^\d{15,20}$/.test(query.trim()) && !options.some((o) => o.id === query.trim());
  const who = picked || (manual ? { id: query.trim(), name: query.trim() } : null);
  return (
    <div class="staff-add" data-testid={`staff-add-${kind}`}>
      <Field label={kind === "role" ? "Rol de Discord" : "Persona"} hint={kind === "role" ? "Todos los que tengan este rol tendrán estos permisos." : "Busca por nombre, o pega su ID de Discord."}>
        <input class="input" type="search" placeholder="Buscar…" value={query} onInput={(e) => { setQuery(e.currentTarget.value); setPicked(null); }} data-testid={`staff-add-${kind}-search`} />
      </Field>
      {!picked && (
        <ul class="staff-pick">
          {found.map((o) => (
            <li key={o.id}><button type="button" class="staff-pick-item" onClick={() => setPicked(o)} data-testid={`staff-pick-${o.id}`}>
              {kind === "role" ? <span class="staff-role-dot" style={{ background: o.color || "var(--text-faint)" }} /> : <Avatar url={o.avatar} name={o.name} size="sm" />}
              <span class="ellipsis">{o.name}</span>
            </button></li>
          ))}
          {!found.length && !manual && <li class="faint" style={{ padding: "6px 2px", fontSize: ".8125rem" }}>{kind === "role" ? "No hay roles con ese nombre." : "Nadie con ese nombre (pega su ID si no ha jugado aún)."}</li>}
        </ul>
      )}
      {who && (
        <>
          <p class="row" style={{ gap: "8px" }}><UserCog size={15} /> <b>{who.name}</b> <button type="button" class="btn btn-sm btn-ghost" onClick={() => { setPicked(null); setQuery(""); }}>Cambiar</button></p>
          {kind !== "host" && <PermEditor value={perms} onChange={setPerms} catalog={catalog} mine={mine} testid={`staff-add-${kind}-perms`} />}
          <div class="row" style={{ justifyContent: "flex-end", gap: "8px" }}>
            <button type="button" class="btn btn-sm btn-ghost" onClick={onDone}>Cancelar</button>
            <button type="button" class="btn btn-sm btn-primary" disabled={busy === "add"} data-testid={`staff-add-${kind}-save`}
              onClick={async () => { const out = await run("add", "gm.staff_set", { kind, id: who.id, name: who.name, perms }, "Añadido al equipo."); if (out) onDone(); }}>
              <Plus size={14} /> Añadir
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// «Equipo de GM»: who is a game master and with which boxes. Only for who has the «Equipo de GM» box (the hosts, by default).
export function StaffTab() {
  const q = usePanel("gm.staff");
  const [busy, run0] = useDo();
  const [adding, setAdding] = useState(null);
  const run = async (name, op, args, done) => {
    const out = await run0(name, op, args, done);
    if (out) q.replace(out);
    return out;
  };
  return (
    <div class="dash-col" data-testid="gm-staff">
      <Block q={q}>
        {(d) => {
          const catalog = { perms: d.perms, presets: d.presets };
          const mine = d.me.perms;
          const avatars = Object.fromEntries(d.people_available.map((p) => [p.id, p.avatar]));
          const takenPeople = new Set([...d.people.map((p) => p.id), ...d.hosts.map((h) => h.id)]);
          const takenRoles = new Set(d.roles.map((r) => r.id));
          const roleColor = Object.fromEntries(d.roles_available.map((r) => [r.id, r.color]));
          return (
            <>
              <Card title="Cómo funciona" icon={ShieldCheck}>
                <p class="faint gm-hint">Cada permiso es una casilla. Una persona con entrada propia tiene exactamente esas casillas (aunque tenga el rol de
                  administrador); si no, suma las de sus roles y, si es administrador del bot, las de «Rol de administrador». Los anfitriones lo tienen todo.
                  Nadie puede dar un permiso que no tiene, ni cambiarse los suyos.</p>
                <div class="row wrap" style={{ gap: "6px" }}>
                  {d.me.host ? <Pill tone="warn" icon={Crown}>Eres anfitrión</Pill> : <Pill tone="info" icon={KeyRound}>{mine.length} permisos</Pill>}
                </div>
              </Card>

              <Card title="Rol de administrador del bot" icon={KeyRound} hint="Lo que tiene quien tiene el rol de administrador y no aparece abajo con permisos propios.">
                <AdminBoxes value={d.admins.perms} catalog={catalog} mine={mine} run={run} busy={busy} />
              </Card>

              <Card title="Personas" icon={Users} testid="staff-people"
                actions={adding !== "person" && <button type="button" class="btn btn-sm" onClick={() => setAdding("person")} data-testid="staff-add-person-open"><Plus size={14} /> Añadir</button>}>
                {adding === "person" && <AddForm kind="person" options={d.people_available.filter((p) => !takenPeople.has(p.id))} catalog={catalog} mine={mine} run={run} busy={busy} onDone={() => setAdding(null)} />}
                {d.people.length ? (
                  <ul class="staff-list">{d.people.map((p) => <Entry key={p.id} kind="person" entry={p} catalog={catalog} mine={mine} run={run} busy={busy} avatar={avatars[p.id]} canRemove />)}</ul>
                ) : adding !== "person" && <Empty title="Nadie con permisos propios">Añade a alguien para darle un papel concreto: narrador, ayudante de combate, moderador…</Empty>}
              </Card>

              <Card title="Roles de Discord" icon={Users} testid="staff-roles"
                actions={adding !== "role" && d.roles_available.length > 0 && <button type="button" class="btn btn-sm" onClick={() => setAdding("role")}><Plus size={14} /> Añadir</button>}>
                {adding === "role" && <AddForm kind="role" options={d.roles_available.filter((r) => !takenRoles.has(r.id))} catalog={catalog} mine={mine} run={run} busy={busy} onDone={() => setAdding(null)} />}
                {d.roles.length ? (
                  <ul class="staff-list">{d.roles.map((r) => <Entry key={r.id} kind="role" entry={{ ...r, color: roleColor[r.id] }} catalog={catalog} mine={mine} run={run} busy={busy} canRemove />)}</ul>
                ) : <p class="faint gm-hint">{d.roles_available.length ? "Ningún rol da permisos todavía." : "El bot no ve roles en el servidor del evento."}</p>}
              </Card>

              <Card title="Anfitriones" icon={Crown} testid="staff-hosts" hint="El dueño del servidor y la ventana de la app ya lo son. Un anfitrión puede hacer todo, también nombrar a otros."
                actions={d.me.host && adding !== "host" && <button type="button" class="btn btn-sm" onClick={() => setAdding("host")}><Plus size={14} /> Añadir</button>}>
                {adding === "host" && <AddForm kind="host" options={d.people_available.filter((p) => !takenPeople.has(p.id))} catalog={catalog} mine={mine} run={run} busy={busy} onDone={() => setAdding(null)} />}
                {d.hosts.length ? (
                  <ul class="staff-list">{d.hosts.map((h) => <Entry key={h.id} kind="host" entry={h} catalog={catalog} mine={mine} run={run} busy={busy} avatar={avatars[h.id]} canRemove={d.me.host} />)}</ul>
                ) : <p class="faint gm-hint">No hay coanfitriones.</p>}
              </Card>
            </>
          );
        }}
      </Block>
    </div>
  );
}

function AdminBoxes({ value, catalog, mine, run, busy }) {
  const [perms, setPerms] = useState(value);
  const dirty = JSON.stringify([...perms].sort()) !== JSON.stringify([...value].sort());
  return (
    <>
      <PermEditor value={perms} onChange={setPerms} catalog={catalog} mine={mine} testid="staff-admins" />
      <div class="row" style={{ justifyContent: "flex-end", gap: "8px" }}>
        <button type="button" class="btn btn-sm btn-ghost" disabled={!dirty} onClick={() => setPerms(value)}>Deshacer</button>
        <button type="button" class="btn btn-sm btn-primary" disabled={!dirty || busy === "admins"} data-testid="staff-admins-save"
          onClick={() => run("admins", "gm.staff_admins", { perms }, "Guardado.")}>Guardar</button>
      </div>
    </>
  );
}
