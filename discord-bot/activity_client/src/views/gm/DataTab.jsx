import { useEffect, useMemo, useState } from "preact/hooks";
import { Check, FilePlus2, FileText, History, Package, Pencil, Plus, RefreshCw, Search, Trash2, Trophy, X } from "lucide-preact";
import { Modal } from "../../ui/Overlays.jsx";
import { Switch } from "../../ui/Controls.jsx";
import { Block, ConfirmButton, Empty, Field, Pill } from "../../ui/Common.jsx";
import { rpc } from "../../net.js";
import { toast } from "../../state.js";
import { usePanel } from "../../panel/data.js";
import { OBJECT_TYPE, parseNumber, plural, rarityOf } from "../../panel/format.js";
import { ago } from "../../util.js";
import { Card, NumberInput } from "./ui.jsx";
import { ObjectForm } from "./ObjectForm.jsx";
import { PowersSection } from "./PowersSection.jsx";
import { useDo } from "./hooks.js";

const STARTER_I18N = '{\n  "exact": {},\n  "patterns": []\n}\n';

// ---- achievements, as a list and a form -------------------------------------------------------------------------------------------
function AchievementForm({ initial, categories, domains, triggers, onClose, onSaved }) {
  const [f, setF] = useState(() => initial ? {
    id: initial.id, name: initial.name, description: initial.description, category: initial.category, icon: initial.icon, trigger: initial.trigger === "manual" ? "" : initial.trigger,
    hidden: initial.hidden, announce: initial.announce, message: initial.message, points: String(initial.reward.points), title: initial.reward.title || "", domain: initial.reward.domain || "",
  } : { id: "", name: "", description: "", category: categories[0] ? categories[0].id : "", icon: "🏆", trigger: "", hidden: false, announce: true, message: "", points: "0", title: "", domain: "" });
  const [busy, run] = useDo();
  const set = (patch) => setF((old) => ({ ...old, ...patch }));
  const save = async () => {
    const out = await run("save", "gm.ach_save", {
      id: f.id, name: f.name, description: f.description, category: f.category, icon: f.icon, trigger: f.trigger, hidden: f.hidden, announce: f.announce, message: f.message,
      reward: { points: parseNumber(f.points) ?? 0, title: f.title, domain: f.domain },
    }, initial ? "Logro guardado." : "Logro creado.");
    if (out) onSaved(out);
  };
  return (
    <Modal title={initial ? `Editar «${initial.name}»` : "Nuevo logro"} onClose={onClose}
      actions={<><button class="btn btn-ghost" type="button" onClick={onClose}>Cancelar</button>
        <button class="btn btn-primary" type="button" onClick={save} disabled={busy !== null || !f.name.trim() || !f.id.trim()} data-testid="gm-achform-save">Guardar</button></>}>
      <div class="col" style={{ gap: "var(--sp-3)" }} data-testid="gm-achform">
        <div class="gm-grid">
          <Field label="Identificador" hint="Minúsculas, números y _. No se puede cambiar después.">
            <input class="input" maxLength={40} value={f.id} disabled={!!initial} onInput={(e) => set({ id: e.currentTarget.value.toLowerCase() })} data-testid="gm-achform-id" />
          </Field>
          <Field label="Icono"><input class="input" maxLength={8} value={f.icon} onInput={(e) => set({ icon: e.currentTarget.value })} data-testid="gm-achform-icon" /></Field>
        </div>
        <Field label="Nombre"><input class="input" maxLength={80} value={f.name} onInput={(e) => set({ name: e.currentTarget.value })} data-testid="gm-achform-name" /></Field>
        <Field label="Descripción"><textarea class="textarea" maxLength={300} value={f.description} onInput={(e) => set({ description: e.currentTarget.value })} data-testid="gm-achform-description" /></Field>
        <Field label="Categoría">
          <select class="select" value={f.category} onChange={(e) => set({ category: e.currentTarget.value })} data-testid="gm-achform-category">
            {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
          </select>
        </Field>
        <Field label="Cómo se consigue" hint="Déjalo vacío si solo lo da un GM. Ejemplos: evade_count:100 · parry_count:25 · boss_kills:10 (varios unidos con «|»).">
          <input class="input" list="gm-triggers" maxLength={120} value={f.trigger} placeholder="manual" onInput={(e) => set({ trigger: e.currentTarget.value.trim() })} data-testid="gm-achform-trigger" />
          <datalist id="gm-triggers">{triggers.map((t) => <option key={t} value={t} />)}</datalist>
        </Field>
        <div class="setting"><div class="info"><strong>Secreto</strong><span>No se ve hasta conseguirlo.</span></div><Switch checked={f.hidden} onChange={(hidden) => set({ hidden })} label="Logro secreto" /></div>
        <div class="setting"><div class="info"><strong>Anunciarlo en el canal</strong><span>Cuando alguien lo consigue.</span></div><Switch checked={f.announce} onChange={(announce) => set({ announce })} label="Anunciar el logro" /></div>
        <Field label="Mensaje del anuncio (opcional)"><textarea class="textarea" maxLength={300} value={f.message} onInput={(e) => set({ message: e.currentTarget.value })} data-testid="gm-achform-message" /></Field>
        <div class="gm-grid">
          <Field label="Puntos de habilidad"><NumberInput value={f.points} min={0} max={999} step={1} label="Puntos de habilidad" testid="gm-achform-points" onInput={(points) => set({ points })} /></Field>
          <Field label="Título que da"><input class="input" maxLength={60} value={f.title} onInput={(e) => set({ title: e.currentTarget.value })} data-testid="gm-achform-title" /></Field>
        </div>
        <Field label="Dominio que da">
          <select class="select" value={f.domain} onChange={(e) => set({ domain: e.currentTarget.value })} data-testid="gm-achform-domain">
            <option value="">Ninguno</option>
            {domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
      </div>
    </Modal>
  );
}

function Achievements() {
  const q = usePanel("gm.achievements");
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState(null);                  // null | "new" | an achievement
  const [busy, run] = useDo();
  const remove = async (id) => {
    const out = await run("rm", "gm.ach_delete", { id }, "Logro borrado. Quien ya lo tenía lo conserva.");
    if (out) q.replace(out);
  };
  return (
    <Block q={q}>
      {(d) => {
        const text = filter.trim().toLowerCase();
        const shown = d.achievements.filter((a) => !text || `${a.name} ${a.id} ${a.description}`.toLowerCase().includes(text));
        const triggers = [...new Set(d.achievements.map((a) => a.trigger).filter((t) => t && t !== "manual"))].sort();
        return (
          <>
            <div class="row wrap" style={{ gap: "10px" }}>
              <label class="gm-search grow"><Search size={16} /><input class="input" type="search" placeholder="Buscar un logro…" value={filter} onInput={(e) => setFilter(e.currentTarget.value)} aria-label="Buscar un logro" data-testid="gm-ach-search" /></label>
              <button class="btn btn-primary" type="button" onClick={() => setEditing("new")} data-testid="gm-ach-new"><Plus size={16} /> Nuevo logro</button>
            </div>
            <p class="faint gm-hint">{plural(d.achievements.length, "logro", "logros")}. Se guardan en el archivo de logros (con copia de seguridad) y valen desde ya.</p>
            {d.categories.map((c) => {
              const mine = shown.filter((a) => a.category === c.id);
              if (!mine.length) return null;
              return (
                <section key={c.id} data-testid={`gm-achcat-${c.id}`}>
                  <div class="ach-cat-title" style={{ "--cat": c.color }}>{c.icon} {c.name}<small>{mine.length}</small></div>
                  <ul class="gm-list">
                    {mine.map((a) => (
                      <li key={a.id} class="gm-item" data-testid={`gm-achrow-${a.id}`}>
                        <span class="gm-icon">{a.icon}</span>
                        <div class="grow">
                          <strong>{a.name}</strong> <code class="faint">{a.id}</code>
                          <div class="row wrap" style={{ gap: "6px", marginTop: "4px" }}>
                            <Pill>{a.trigger || "manual"}</Pill>
                            {a.hidden && <Pill tone="primary">Secreto</Pill>}
                            {a.reward.points > 0 && <Pill tone="info">+{a.reward.points} puntos</Pill>}
                            {a.reward.title && <Pill tone="warn">Título: {a.reward.title}</Pill>}
                            {a.reward.domain && <Pill tone="primary">Dominio</Pill>}
                          </div>
                        </div>
                        <button class="icon-btn" type="button" aria-label={`Editar ${a.name}`} onClick={() => setEditing(a)} data-testid={`gm-ach-edit-${a.id}`}><Pencil size={17} /></button>
                        <ConfirmButton icon={Trash2} confirm="Borrar" label={`Borrar ${a.name}`} onConfirm={() => remove(a.id)} disabled={busy !== null} testid={`gm-ach-delete-${a.id}`} />
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
            {shown.length === 0 && <Empty icon={Trophy} title="No hay logros que coincidan">Prueba con otra búsqueda o crea uno nuevo.</Empty>}
            {editing && (
              <AchievementForm initial={editing === "new" ? null : editing} categories={d.categories} domains={d.domains} triggers={triggers}
                onClose={() => setEditing(null)} onSaved={(out) => { setEditing(null); q.replace(out); }} />
            )}
          </>
        );
      }}
    </Block>
  );
}

// ---- objects waiting for approval, and approved ones ---------------------------------------------------------------------------------------
function Pending({ p, onChanged, openFile }) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, run] = useDo();
  const approve = async () => {
    const out = await run("approve", "gm.obj_approve", { file: p.file }, `«${p.name}» aprobado.`);
    if (out) onChanged(out);
  };
  const reject = async () => {
    const out = await run("reject", "gm.obj_reject", { file: p.file, reason }, `«${p.name}» rechazado.`);
    if (out) { setRejecting(false); onChanged(out); }
  };
  return (
    <li class="gm-item gm-pending" data-testid={`gm-pending-${p.file}`}>
      <div class="grow col" style={{ gap: "6px" }}>
        <div class="row wrap" style={{ gap: "8px" }}><strong>{p.name}</strong><code class="faint">{p.file}</code><Pill tone={p.ok ? "ok" : "bad"}>{p.ok ? "Listo para aprobar" : "Tiene errores"}</Pill></div>
        {p.errors.length > 0 && <ul class="gm-errors">{p.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
        {rejecting && (
          <div class="row wrap" style={{ gap: "8px" }}>
            <input class="input grow" maxLength={200} placeholder="Motivo (opcional)" value={reason} onInput={(e) => setReason(e.currentTarget.value)} aria-label="Motivo del rechazo" data-testid={`gm-reject-reason-${p.file}`} />
            <button class="btn btn-sm btn-danger" type="button" onClick={reject} disabled={busy !== null} data-testid={`gm-reject-confirm-${p.file}`}>Rechazar</button>
            <button class="btn btn-sm btn-ghost" type="button" onClick={() => setRejecting(false)}>No</button>
          </div>
        )}
        <div class="row wrap" style={{ gap: "8px" }}>
          <button class="btn btn-sm btn-primary" type="button" onClick={approve} disabled={busy !== null || !p.ok} data-testid={`gm-approve-${p.file}`}><Check size={14} /> Aprobar</button>
          {!rejecting && <button class="btn btn-sm" type="button" onClick={() => setRejecting(true)} disabled={busy !== null} data-testid={`gm-reject-${p.file}`}><X size={14} /> Rechazar</button>}
          <button class="btn btn-sm btn-ghost" type="button" onClick={() => openFile(`pending:${p.file.replace(/\.json$/, "")}`)} data-testid={`gm-pending-edit-${p.file}`}><Pencil size={14} /> Revisar el archivo</button>
        </div>
      </div>
    </li>
  );
}

function Objects({ openFile }) {
  const q = usePanel("gm.objects");
  const [busy, run] = useDo();
  const [form, setForm] = useState(null);                  // null | { loaded } (an object to edit) | { loaded: null } (a new one)
  const [players, setPlayers] = useState([]);
  const openForm = async (id) => {
    try {
      const [loaded, list] = await Promise.all([id ? rpc("gm.object", { id }) : Promise.resolve(null), rpc("gm.players", {})]);
      setPlayers((list.players || []).map((p) => ({ id: String(p.id), name: p.name })));
      setForm({ loaded });
    } catch (error) { toast(error.message, "bad"); }
  };
  const reload = async () => {
    const out = await run("reload", "gm.obj_reload", {}, null);
    if (out) {
      q.replace({ approved: out.approved, pending: out.pending, effects: out.effects });
      if (out.errors.length) toast(`Se cargaron ${out.loaded}; ${plural(out.errors.length, "archivo con error", "archivos con error")}: ${out.errors[0]}`, "warn", 6000);
      else toast(`Objetos recargados: ${plural(out.loaded, "cargado", "cargados")}.`, "ok");
    }
  };
  return (
    <Block q={q}>
      {(d) => (
        <>
          <div class="row wrap" style={{ gap: "10px" }}>
            <button class="btn btn-primary" type="button" onClick={() => openForm(null)} data-testid="gm-obj-new"><Plus size={16} /> Nuevo objeto</button>
            <button class="btn" type="button" onClick={reload} disabled={busy !== null} data-testid="gm-obj-reload"><RefreshCw size={16} /> Recargar objetos</button>
          </div>
          {form && <ObjectForm loaded={form.loaded} players={players} effects={d.effects} onClose={() => setForm(null)}
            onSaved={(out) => { q.replace({ approved: out.approved, pending: out.pending, effects: out.effects }); if (!form.loaded) setForm(null); }} />}
          <Card title="Esperando aprobación" icon={Package} testid="gm-pending" hint="Objetos enviados por el equipo. Se revisan antes de que los jugadores puedan tenerlos.">
            {d.pending.length === 0 ? <Empty icon={Check} title="No hay objetos pendientes">Cuando alguien envíe uno, aparecerá aquí.</Empty>
              : <ul class="gm-list">{d.pending.map((p) => <Pending key={p.file} p={p} onChanged={(out) => q.replace(out)} openFile={openFile} />)}</ul>}
          </Card>
          <Card title="Objetos aprobados" icon={Package} testid="gm-approved" actions={<span class="faint num" style={{ fontSize: ".75rem" }}>{d.approved.length}</span>}>
            {d.approved.length === 0 ? <p class="faint gm-hint">Todavía no hay objetos aprobados.</p> : (
              <ul class="gm-list">
                {d.approved.map((o) => (
                  <li key={o.id} class="gm-item" data-testid={`gm-approved-${o.id}`} style={{ "--rarity": rarityOf(o.rarity).color }}>
                    <span class="gm-rarity" />
                    <div class="grow"><strong>{o.name}</strong> <code class="faint">{o.id}</code>
                      <div class="row wrap" style={{ gap: "6px", marginTop: "4px" }}><Pill>{rarityOf(o.rarity).label}</Pill><Pill>{OBJECT_TYPE[o.type] || o.type}</Pill></div>
                    </div>
                    <button class="btn btn-sm" type="button" onClick={() => openForm(o.id)} data-testid={`gm-approved-form-${o.id}`}><Pencil size={14} /> Editar</button>
                    <button class="btn btn-sm btn-ghost" type="button" onClick={() => openFile(`object:${o.id}`)} data-testid={`gm-approved-edit-${o.id}`} title="Editar el archivo JSON"><FileText size={14} /> JSON</button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </Block>
  );
}

// ---- the files themselves ----------------------------------------------------------------------------------------------------------------------
function jsonProblem(text) {
  try { JSON.parse(text); return null; } catch (error) { return String(error.message).replace(/^JSON\.parse: /, ""); }
}

function Backups({ backups, onRestore, busy }) {
  if (!backups.length) return <p class="faint gm-hint">Aún no hay copias de seguridad de este archivo. Se crea una cada vez que se guarda.</p>;
  return (
    <ul class="gm-list" data-testid="gm-backups">
      {backups.map((b) => (
        <li key={b.name} class="gm-item">
          <History size={16} />
          <div class="grow"><code>{b.name}</code><div class="faint" style={{ fontSize: ".75rem" }}>{ago(b.ts)} · {Math.max(1, Math.round(b.size / 1024))} KB</div></div>
          <ConfirmButton confirm="Sí, recuperar" onConfirm={() => onRestore(b.name)} disabled={busy} testid={`gm-restore-${b.name}`}>Recuperar</ConfirmButton>
        </li>
      ))}
    </ul>
  );
}

function Editor({ item, first, onDeleted }) {
  const [loaded, setLoaded] = useState(first.text);
  const [value, setValue] = useState(first.text);
  const [backups, setBackups] = useState(first.backups);
  const [warnings, setWarnings] = useState([]);
  const [busy, run] = useDo();
  const problem = useMemo(() => jsonProblem(value), [value]);
  const dirty = value !== loaded;
  const keep = (out) => { setLoaded(out.text); setValue(out.text); setBackups(out.backups); setWarnings(out.warnings || []); };
  const save = async () => {
    const out = await run("save", "gm.file_save", { key: item.key, text: value }, "Archivo guardado y cargado en el bot.");
    if (out) keep(out);
  };
  const restore = async (name) => {
    const out = await run("restore", "gm.file_restore", { key: item.key, name }, "Copia recuperada.");
    if (out) keep(out);
  };
  const remove = async () => {
    const out = await run("delete", "gm.file_delete", { key: item.key }, "Archivo borrado. Queda una copia.");
    if (out) onDeleted(out.files);
  };
  const pretty = () => { if (!problem) setValue(JSON.stringify(JSON.parse(value), null, 2) + "\n"); };
  const deletable = /^(tree|object|pending):/.test(item.key);
  return (
    <div class="col" style={{ gap: "var(--sp-3)" }} data-testid="gm-editor">
      <textarea class="textarea gm-code" spellCheck={false} wrap="off" value={value} onInput={(e) => setValue(e.currentTarget.value)} aria-label={`Contenido de ${item.label}`} data-testid="gm-editor-text" />
      <p class={problem ? "gm-warn" : "gm-ok"} role="status" data-testid="gm-editor-status">{problem ? `El JSON no es válido: ${problem}` : dirty ? "El JSON es válido. Hay cambios sin guardar." : "Sin cambios."}</p>
      {warnings.length > 0 && <ul class="gm-errors" data-testid="gm-editor-warnings">{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
      <div class="row wrap" style={{ gap: "8px" }}>
        <button class="btn btn-primary" type="button" onClick={save} disabled={busy !== null || !dirty || !!problem} data-testid="gm-editor-save">Guardar y cargar</button>
        <button class="btn" type="button" onClick={pretty} disabled={!!problem} data-testid="gm-editor-pretty">Dar formato</button>
        <button class="btn btn-ghost" type="button" onClick={() => setValue(loaded)} disabled={!dirty} data-testid="gm-editor-discard">Descartar cambios</button>
        {deletable && <ConfirmButton icon={Trash2} confirm="Sí, borrar" onConfirm={remove} disabled={busy !== null} testid="gm-editor-delete">Borrar archivo</ConfirmButton>}
      </div>
      <h3 class="gm-sub">Copias de seguridad</h3>
      <Backups backups={backups} onRestore={restore} busy={busy !== null} />
    </div>
  );
}

// a file's text, fetched fresh each time one is chosen (the editor must never start from a stale copy)
function FileEditor({ item, onDeleted }) {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    rpc("gm.file_get", { key: item.key }).then(
      (out) => alive && setState({ first: out }),
      (error) => alive && setState(item.exists ? { error: error.message } : { first: { text: item.key === "i18n" ? STARTER_I18N : "{}\n", backups: [] } }),
    );
    return () => { alive = false; };
  }, [item.key, item.exists]);
  if (state.loading) return <div class="dash-loading" role="status"><span class="spinner" /><span>Abriendo el archivo…</span></div>;
  if (state.error) return <p class="gm-warn" role="alert">{state.error}</p>;
  return <Editor key={item.key} item={item} first={state.first} onDeleted={onDeleted} />;
}

function NewFile({ templates, onCreated }) {
  const [template, setTemplate] = useState(templates[0] ? templates[0].key : "");
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, run] = useDo();
  const kind = template === "template:skill_tree_template" ? "tree" : "object";
  useEffect(() => {
    if (!template) return undefined;
    let alive = true;
    setLoading(true);
    rpc("gm.file_get", { key: template }).then((out) => { if (alive) { setText(out.text); setLoading(false); } }, (error) => { if (alive) { toast(error.message, "bad", 4500); setLoading(false); } });
    return () => { alive = false; };
  }, [template]);
  const problem = useMemo(() => jsonProblem(text), [text]);
  const create = async () => {
    let body = text;
    if (kind === "object") {                          // the object's id must be its file name: fill it in
      try { body = JSON.stringify({ ...JSON.parse(text), id: name.trim().toLowerCase() }, null, 2); } catch { /* the server explains */ }
    }
    const out = await run("create", "gm.file_create", { kind, name, text: body }, "Archivo creado y cargado en el bot.");
    if (out) onCreated(`${kind}:${name.trim().toLowerCase()}`, out.files, out.warnings || []);
  };
  return (
    <Card title="Crear un archivo nuevo" icon={FilePlus2} testid="gm-newfile" hint="Parte de una plantilla, cámbiala y dale un nombre. Los objetos nuevos se crean ya aprobados.">
      <div class="col" style={{ gap: "var(--sp-3)" }}>
        <div class="gm-grid">
          <Field label="Plantilla">
            <select class="select" value={template} onChange={(e) => setTemplate(e.currentTarget.value)} data-testid="gm-template">
              {templates.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>
          </Field>
          <Field label="Nombre del archivo" hint="Minúsculas, números y _ (entre 2 y 40).">
            <input class="input" maxLength={40} value={name} onInput={(e) => setName(e.currentTarget.value.toLowerCase())} placeholder={kind === "tree" ? "arbol_nuevo" : "objeto_nuevo"} data-testid="gm-newfile-name" />
          </Field>
        </div>
        <textarea class="textarea gm-code" spellCheck={false} wrap="off" value={loading ? "Cargando la plantilla…" : text} disabled={loading} onInput={(e) => setText(e.currentTarget.value)} aria-label="Contenido del archivo nuevo" data-testid="gm-newfile-text" />
        <p class={problem ? "gm-warn" : "gm-ok"} role="status">{problem ? `El JSON no es válido: ${problem}` : "El JSON es válido."}</p>
        <div><button class="btn btn-primary" type="button" onClick={create} disabled={busy !== null || loading || !name.trim() || !!problem} data-testid="gm-newfile-create"><FilePlus2 size={16} /> Crear {kind === "tree" ? "el árbol" : "el objeto"}</button></div>
      </div>
    </Card>
  );
}

function Files({ pick, onPicked }) {
  const index = usePanel("gm.data");
  const [key, setKey] = useState(pick || "");
  const [files, setFiles] = useState(null);
  useEffect(() => { if (pick) { setKey(pick); onPicked && onPicked(); } }, [pick]);
  return (
    <Block q={index}>
      {(d) => {
        const list = files || d.files;
        const groups = [...new Set(list.map((f) => f.group))];
        const item = list.find((f) => f.key === key);
        return (
          <>
            <Card title="Editar un archivo" icon={FileText} testid="gm-files" hint="Los cambios se comprueban antes de guardarse; si algo está mal, no se toca nada. Siempre queda una copia del archivo anterior.">
              <div class="col" style={{ gap: "var(--sp-3)" }}>
                <Field label="Archivo">
                  <select class="select" value={key} onChange={(e) => setKey(e.currentTarget.value)} data-testid="gm-file-select">
                    <option value="">Elige un archivo…</option>
                    {groups.map((g) => (
                      <optgroup key={g} label={g}>{list.filter((f) => f.group === g).map((f) => <option key={f.key} value={f.key}>{f.label}{f.exists ? "" : " (aún no existe)"}</option>)}</optgroup>
                    ))}
                  </select>
                </Field>
                {item ? <FileEditor key={item.key} item={item} onDeleted={(fresh) => { setFiles(fresh); setKey(""); index.refresh(); }} />
                  : <Empty icon={FileText} title="Elige un archivo">Logros, árboles de habilidades, objetos o traducciones.</Empty>}
              </div>
            </Card>
            <NewFile templates={d.templates} onCreated={(created, fresh, warnings) => { setFiles(fresh); setKey(created); index.refresh(); if (warnings.length) toast(warnings[0], "warn", 6000); }} />
          </>
        );
      }}
    </Block>
  );
}

const SECTIONS = [["achievements", "Logros"], ["objects", "Objetos"], ["powers", "Poderes"], ["files", "Archivos"]];

export function DataTab() {
  const [section, setSection] = useState("achievements");
  const [pick, setPick] = useState(null);
  const openFile = (key) => { setPick(key); setSection("files"); };
  return (
    <div class="dash-col" data-testid="gm-data">
      <div class="segmented gm-sections" role="group" aria-label="Qué contenido editar">
        {SECTIONS.map(([id, text]) => <button key={id} type="button" aria-pressed={section === id ? "true" : "false"} data-testid={`gm-section-${id}`} onClick={() => setSection(id)}>{text}</button>)}
      </div>
      {section === "achievements" && <Achievements />}
      {section === "objects" && <Objects openFile={openFile} />}
      {section === "powers" && <PowersSection />}
      {section === "files" && <Files pick={pick} onPicked={() => setPick(null)} />}
    </div>
  );
}
