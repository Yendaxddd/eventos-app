import { useMemo, useRef, useState } from "preact/hooks";
import { Check, FileUp, Search, TriangleAlert } from "lucide-preact";
import { toast } from "../../state.js";
import { rpc } from "../../net.js";
import { Avatar } from "../../ui/Avatar.jsx";
import { Modal } from "../../ui/Overlays.jsx";
import { Pill } from "../../ui/Common.jsx";
import { MAX_IMPORT, describeResult, parseTupperExport } from "../../tupper.js";

const FILE_LIMIT = 6 * 1024 * 1024;

// The first of the file that fit: the ones already yours (only their picture changes) and as many new ones as there are free places.
function firstThatFit(items, mine, slots) {
  const picked = [];
  let added = 0;
  for (const item of items) {
    if (picked.length >= MAX_IMPORT) break;
    if (mine.has(item.name)) picked.push(item.name);
    else if (added < slots) { picked.push(item.name); added++; }
  }
  return new Set(picked);
}

// Bring characters (and their pictures) from Tupperbox: pick the file it exported, choose which ones, and they are registered to you with
// their pictures kept on the host's PC.
export function TupperImport({ d, replace, onClose }) {
  const [stage, setStage] = useState("pick");            // pick -> choose -> working -> done
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [parsed, setParsed] = useState(null);
  const [chosen, setChosen] = useState(() => new Set());
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const picker = useRef(null);
  const mine = useMemo(() => new Set(d.characters.map((c) => c.name)), [d]);
  const slots = Math.max(0, d.max - d.characters.length);

  const read = (source) => {
    const out = parseTupperExport(source);
    if (out.error) { setError(out.error); return; }
    setError("");
    setParsed(out);
    setChosen(firstThatFit(out.items, mine, slots));
    setStage("choose");
  };
  const onFile = async (e) => {
    const file = e.currentTarget.files && e.currentTarget.files[0];
    e.currentTarget.value = "";
    if (!file) return;
    if (file.size > FILE_LIMIT) { setError("Ese archivo es demasiado grande para ser de Tupperbox."); return; }
    try { read(await file.text()); } catch { setError("No se pudo leer el archivo."); }
  };

  const fresh = [...chosen].filter((n) => !mine.has(n)).length;
  const canAdd = (item) => chosen.has(item.name) || (chosen.size < MAX_IMPORT && (mine.has(item.name) || fresh < slots));
  const toggle = (item) => setChosen((old) => {
    const next = new Set(old);
    if (next.has(item.name)) next.delete(item.name); else if (canAdd(item)) next.add(item.name);
    return next;
  });
  const shown = parsed ? parsed.items.filter((i) => !query.trim() || i.name.toLowerCase().includes(query.trim().toLowerCase())) : [];

  const run = async () => {
    setStage("working");
    try {
      const out = await rpc("panel.tupper_import", { tuppers: parsed.items.filter((i) => chosen.has(i.name)) });
      replace(out.characters);
      setResults(out.results);
      setStage("done");
    } catch (failure) {
      toast(failure.message, "bad", 5000);
      setStage("choose");
    }
  };

  const ok = results.filter((r) => r.status === "new" || r.status === "mine").length;
  const actions = stage === "choose"
    ? <><button class="btn btn-ghost" type="button" onClick={() => setStage("pick")}>Atrás</button>
        <button class="btn btn-primary" type="button" disabled={chosen.size === 0} onClick={run} data-testid="tupper-go"><Check size={16} /> Importar {chosen.size}</button></>
    : stage === "done" ? <button class="btn btn-primary" type="button" onClick={onClose} data-testid="tupper-close">Listo</button> : null;

  return (
    <Modal title="Importar de Tupperbox" onClose={stage === "working" ? () => {} : onClose} actions={actions}>
      <div class="col" style={{ gap: "var(--sp-3)" }} data-testid="tupper-import">
        {stage === "pick" && (
          <>
            <ol class="steps faint">
              <li>En Discord, donde esté Tupperbox, escribe <span class="kbd">tul!export</span>.</li>
              <li>Descarga el archivo <b>tuppers.json</b> que te manda.</li>
              <li>Elígelo aquí (o pega su contenido abajo). Solo se leen los nombres y las imágenes.</li>
            </ol>
            <div class="row" style={{ gap: "8px" }}>
              <button class="btn btn-primary" type="button" onClick={() => picker.current && picker.current.click()} data-testid="tupper-pick"><FileUp size={16} /> Elegir tuppers.json</button>
              <input ref={picker} type="file" accept=".json,.txt,application/json,text/plain" hidden onChange={onFile} data-testid="tupper-file" />
            </div>
            <textarea class="textarea" placeholder="…o pega aquí el contenido del archivo" value={text} onInput={(e) => setText(e.currentTarget.value)} data-testid="tupper-text" aria-label="Contenido de tuppers.json" />
            <div><button class="btn" type="button" disabled={!text.trim()} onClick={() => read(text)} data-testid="tupper-read">Leer</button></div>
            {error && <p class="tupper-error" role="alert" data-testid="tupper-error"><TriangleAlert size={14} /> {error}</p>}
          </>
        )}
        {stage === "choose" && parsed && (
          <>
            <p class="faint" style={{ fontSize: ".8125rem" }}>
              {parsed.items.length} {parsed.items.length === 1 ? "personaje" : "personajes"} en el archivo{parsed.ignored ? ` (${parsed.ignored} sin nombre o repetidos, ignorados)` : ""}.
              Puedes importar hasta {MAX_IMPORT} a la vez y tienes {slots} {slots === 1 ? "plaza" : "plazas"} libres para personajes nuevos.
            </p>
            <label class="tupper-search"><Search size={14} /><input class="input" placeholder="Buscar…" value={query} onInput={(e) => setQuery(e.currentTarget.value)} aria-label="Buscar personaje" /></label>
            <div class="row" style={{ gap: "6px" }}>
              <button class="choice" type="button" onClick={() => setChosen(new Set())}>Ninguno</button>
              <button class="choice" type="button" onClick={() => setChosen(firstThatFit(parsed.items, mine, slots))} data-testid="tupper-first">Los primeros</button>
              <span class="grow" /><span class="faint" style={{ fontSize: ".75rem" }}>{chosen.size} elegidos</span>
            </div>
            <div class="tupper-list" role="listbox" aria-label="Personajes del archivo" data-testid="tupper-list">
              {shown.map((item) => (
                <label key={item.name} class="tupper-row" data-testid={`tupper-${item.name}`}>
                  <input type="checkbox" checked={chosen.has(item.name)} disabled={!canAdd(item)} onChange={() => toggle(item)} />
                  <Avatar url={item.avatar} name={item.name} size="sm" />
                  <span class="grow ellipsis" title={item.name}>{item.name}</span>
                  {mine.has(item.name) && <Pill tone="info">ya es tuyo</Pill>}
                  {!item.avatar && <Pill>sin imagen</Pill>}
                </label>
              ))}
              {shown.length === 0 && <p class="faint" style={{ padding: "var(--sp-3)" }}>Ninguno coincide.</p>}
            </div>
          </>
        )}
        {stage === "working" && <p class="faint" data-testid="tupper-working">Importando y descargando las imágenes… puede tardar unos segundos.</p>}
        {stage === "done" && (
          <>
            <p data-testid="tupper-summary"><b>{ok}</b> {ok === 1 ? "personaje listo" : "personajes listos"}{results.length - ok > 0 ? ` · ${results.length - ok} omitidos` : ""}.</p>
            <div class="tupper-list" data-testid="tupper-results">
              {results.map((r, i) => {
                const said = describeResult(r);
                return <div key={i} class="tupper-row"><span class="grow ellipsis" title={r.name}>{r.name}</span><Pill tone={said.tone}>{said.text}</Pill></div>;
              })}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
