import { useEffect } from "preact/hooks";
import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from "lucide-preact";
import { banner, fx, toasts } from "../state.js";
import { useEscape } from "../hooks.js";
import { cx } from "../util.js";

const TOAST_ICON = { ok: CircleCheck, bad: CircleAlert, warn: TriangleAlert, info: Info };

export function Toasts() {
  return (
    <div class="toasts" aria-live="polite">
      {toasts.value.map((t) => {
        const Icon = TOAST_ICON[t.kind] || Info;
        return <div key={t.id} class={cx("toast", t.kind)}><Icon size={18} /><span>{t.text}</span></div>;
      })}
    </div>
  );
}

// always one element (the app's grid has a row for it), empty when there is nothing to say
export function Banner() {
  const b = banner.value;
  return (
    <div class="banner-slot">
      {b && <div class={cx("banner", b.kind === "info" && "info")} role="status"><Info size={16} /><span class="grow">{b.text}</span></div>}
    </div>
  );
}

// A red edge when the player is hurt, green when healed, a violet flash on a Black Flash.
export function FxLayer() {
  const current = fx.value;
  useEffect(() => {
    if (!current) return undefined;
    const id = setTimeout(() => { if (fx.value && fx.value.n === current.n) fx.value = null; }, 900);
    return () => clearTimeout(id);
  }, [current && current.n]);
  if (!current) return null;
  return <div key={current.n} class={`fx fx-${current.kind}`} aria-hidden="true" />;
}

export function Sheet({ title, onClose, children }) {
  useEscape(onClose);
  return (
    <>
      <div class="scrim" onClick={onClose} />
      <div class="sheet" role="dialog" aria-label={title}>
        <div class="sheet-grab" />
        <div class="sheet-head">
          <strong class="display grow" style={{ fontSize: "1.0625rem" }}>{title}</strong>
          <button class="icon-btn" type="button" onClick={onClose} aria-label="Cerrar"><X size={20} /></button>
        </div>
        <div class="sheet-body">{children}</div>
      </div>
    </>
  );
}

export function Modal({ title, onClose, children, actions }) {
  useEscape(onClose);
  return (
    <>
      <div class="scrim" onClick={onClose} />
      <div class="modal">
        <div class="modal-card" role="dialog" aria-label={title}>
          <div class="row" style={{ marginBottom: "var(--sp-3)" }}>
            <strong class="display grow" style={{ fontSize: "1.125rem" }}>{title}</strong>
            <button class="icon-btn" type="button" onClick={onClose} aria-label="Cerrar"><X size={20} /></button>
          </div>
          {children}
          {actions && <div class="row" style={{ justifyContent: "flex-end", marginTop: "var(--sp-4)" }}>{actions}</div>}
        </div>
      </div>
    </>
  );
}
