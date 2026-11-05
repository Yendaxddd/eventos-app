import { Gauge, SlidersHorizontal, Timer } from "lucide-preact";
import { Block } from "../../ui/Common.jsx";
import { usePanel } from "../../panel/data.js";
import { num, parseNumber } from "../../panel/format.js";
import { Card, NumberInput } from "./ui.jsx";
import { useDo, useDraft } from "./hooks.js";

// one number of the game: saved with its button (or Enter), checked by the bot's own limits
function ValueRow({ item, replace }) {
  const form = useDraft({ v: String(item.value) });
  const [busy, run] = useDo();
  const shown = String(item.value);
  const dirty = form.draft.v !== shown;
  const save = async (value) => {
    const sent = form.draft;
    const out = await run(item.key, "gm.value_set", { key: item.key, value }, `«${item.label}» guardado.`);
    if (out) { form.saved(sent); replace(out); }
  };
  if (item.kind === "bool") {
    return (
      <div class="setting" data-testid={`gm-value-${item.key}`}>
        <div class="info"><strong>{item.label}</strong><span>{item.hint}</span></div>
        <button type="button" role="switch" class="switch" aria-checked={item.value ? "true" : "false"} aria-label={item.label} disabled={busy !== null} onClick={() => save(!item.value)} data-testid={`gm-value-input-${item.key}`} />
      </div>
    );
  }
  return (
    <form noValidate class="setting gm-value" data-testid={`gm-value-${item.key}`} onSubmit={(e) => { e.preventDefault(); if (dirty) save(parseNumber(form.draft.v)); }}>
      <div class="info"><strong>{item.label}</strong><span>{item.hint}</span><span class="faint">De {num(item.min)} a {num(item.max)}{item.unit ? ` ${item.unit}` : ""}.</span></div>
      <NumberInput value={form.draft.v} min={item.min} max={item.max} step={item.step} unit={item.unit} label={item.label} testid={`gm-value-input-${item.key}`} onInput={(v) => form.edit({ v })} width="150px" />
      <button class="btn btn-sm btn-primary" type="submit" disabled={busy !== null || !dirty} data-testid={`gm-value-save-${item.key}`}>Guardar</button>
    </form>
  );
}

const QTE_FIELDS = [
  ["evade", "Ventana de esquive", "s", 0.1, 30, 0.1], ["parryStart", "El parry empieza a los", "s", 0, 30, 0.1], ["parryEnd", "El parry termina a los", "s", 0.1, 30, 0.1],
  ["perfect", "Parry perfecto a los", "s", 0, 30, 0.05], ["timeout", "Tiempo límite", "s", 0.5, 60, 0.25], ["damageMin", "Daño mínimo", "HP", 0, 9999, 1], ["damageMax", "Daño máximo", "HP", 0, 9999, 1],
];

function QteTimes({ difficulty, label, values, replace }) {
  const form = useDraft(Object.fromEntries(QTE_FIELDS.map(([k]) => [k, String(values[k])])));
  const [busy, run] = useDo();
  const { draft, edit } = form;
  const dirty = QTE_FIELDS.some(([k]) => draft[k] !== String(values[k]));
  const save = async (e) => {
    e.preventDefault();
    const sent = draft;
    const out = await run(difficulty, "gm.qte_set", { difficulty, ...Object.fromEntries(QTE_FIELDS.map(([k]) => [k, parseNumber(sent[k])])) }, `QTE ${label.toLowerCase()}: guardado.`);
    if (out) { form.saved(sent); replace(out); }
  };
  return (
    <Card title={`QTE ${label}`} icon={Timer} testid={`gm-qte-${difficulty}`}>
      <form noValidate class="col" style={{ gap: "var(--sp-3)" }} onSubmit={save}>
        <div class="gm-grid">
          {QTE_FIELDS.map(([key, text, unit, min, max, step]) => (
            <label key={key} class="field">
              <span class="field-label">{text}</span>
              <NumberInput value={draft[key]} min={min} max={max} step={step} unit={unit} label={`${text} (${label})`} testid={`gm-qte-${difficulty}-${key}`} onInput={(v) => edit({ [key]: v })} />
            </label>
          ))}
        </div>
        <div><button class="btn btn-primary" type="submit" disabled={busy !== null || !dirty} data-testid={`gm-qte-save-${difficulty}`}>Guardar {label.toLowerCase()}</button></div>
      </form>
    </Card>
  );
}

export function ValuesTab() {
  const q = usePanel("gm.values");
  return (
    <div class="dash-col" data-testid="gm-values">
      <Block q={q}>
        {(d) => (
          <>
            <p class="faint gm-hint">Los cambios valen desde ya y se conservan cuando el bot se reinicia. Cada número tiene los mismos límites que los comandos del bot.</p>
            {d.groups.map((g) => (
              <Card key={g.id} title={g.title} icon={g.id === "combat" ? Gauge : SlidersHorizontal} testid={`gm-values-${g.id}`}>
                <div class="col" style={{ gap: "var(--sp-2)" }}>
                  {g.items.map((item) => <ValueRow key={item.key} item={item} replace={q.replace} />)}
                </div>
              </Card>
            ))}
            <h2 class="gm-section">Tiempos y daño de los QTE</h2>
            <p class="faint gm-hint">Los segundos se cuentan desde que sale el QTE. El tiempo límite debe ser mayor que el final del parry.</p>
            {d.difficulties.map(([id, label]) => <QteTimes key={id} difficulty={id} label={label[0].toUpperCase() + label.slice(1)} values={d.qte[id]} replace={q.replace} />)}
          </>
        )}
      </Block>
    </div>
  );
}
