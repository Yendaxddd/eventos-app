// Small pieces the game-master screens share.
import { useRef, useState } from "preact/hooks";
import { Upload } from "lucide-preact";
import { toast } from "../../state.js";
import { uploadImage } from "../../net.js";
import { cdn, cx } from "../../util.js";

export function Card({ title, icon: Icon, hint, actions, children, testid, class: className }) {
  return (
    <section class={cx("card-2 gm-card", className)} data-testid={testid}>
      <div class="card-title">
        {Icon && <Icon size={16} />}
        <strong class="display grow">{title}</strong>
        {actions}
      </div>
      {hint && <p class="faint gm-hint">{hint}</p>}
      {children}
    </section>
  );
}

// one-of-several buttons (modes, difficulties...)
export function Chips({ value, options, onChange, label, testid, disabled }) {
  return (
    <div class="row wrap gm-chips" role="group" aria-label={label} data-testid={testid}>
      {options.map(([val, text, hint]) => (
        <button key={val} type="button" class="choice" aria-pressed={value === val ? "true" : "false"} title={hint} disabled={disabled}
          data-testid={testid ? `${testid}-${val}` : undefined} onClick={() => onChange(val)}>{text}</button>
      ))}
    </div>
  );
}

// a number the person types; the unit (s, %, HP...) sits inside the field
export function NumberInput({ value, onInput, min, max, step = 1, unit, label, testid, disabled, placeholder, width }) {
  return (
    <span class="num-input" style={width ? { maxWidth: width } : undefined}>
      <input class="input num" type="number" inputMode="decimal" min={min} max={max} step={step} value={value ?? ""} disabled={disabled} placeholder={placeholder}
        aria-label={label} data-testid={testid} onInput={(e) => onInput(e.currentTarget.value)} />
      {unit && <i aria-hidden="true">{unit}</i>}
    </span>
  );
}

export function Sub({ children }) {
  return <h3 class="gm-sub">{children}</h3>;
}

export function Bar({ value, max, kind, label }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const level = pct <= 25 ? "low" : pct <= 55 ? "mid" : "ok";
  return (
    <div class={cx("bar tall", kind)} role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
      <i style={{ width: `${pct}%` }} data-level={kind === "boss" ? undefined : level} />
      <em class="num">{Math.round(value)} / {Math.round(max)}</em>
    </div>
  );
}

export const DIFFICULTIES = [["easy", "Fácil"], ["medium", "Media"], ["hard", "Difícil"], ["impossible", "Imposible"]];
export const DIFFICULTY_ES = Object.fromEntries(DIFFICULTIES);

// An address for a picture or GIF: typed or pasted, or uploaded from the device (the server gives it a lasting Discord address)
export function PictureInput({ value, onChange, testid, label = "Imagen o GIF", placeholder = "https://…", preview = true }) {
  const picker = useRef(null);
  const [busy, setBusy] = useState(false);
  const upload = async (e) => {
    const picked = e.currentTarget.files && e.currentTarget.files[0];
    e.currentTarget.value = "";
    if (!picked) return;
    setBusy(true);
    try { onChange(await uploadImage(picked)); toast("Imagen subida.", "ok"); } catch (error) { toast(error.message, "bad", 4500); }
    setBusy(false);
  };
  return (
    <div class="col" style={{ gap: "6px" }}>
      <div class="row" style={{ gap: "8px" }}>
        <input class="input" type="url" placeholder={placeholder} value={value || ""} aria-label={label} data-testid={testid} onInput={(e) => onChange(e.currentTarget.value.trim())} />
        <button class="btn" type="button" onClick={() => picker.current && picker.current.click()} disabled={busy} data-testid={testid ? `${testid}-upload` : undefined}>
          <Upload size={16} />{busy ? "Subiendo…" : "Subir"}
        </button>
        <input ref={picker} type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden onChange={upload} data-testid={testid ? `${testid}-file` : undefined} />
      </div>
      {preview && value && <img class="power-preview" src={cdn(value)} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
    </div>
  );
}
