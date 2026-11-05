// Small building blocks shared by the dashboards.
import { useEffect, useState } from "preact/hooks";
import { CircleAlert, Inbox, Loader2, RefreshCw } from "lucide-preact";
import { cx } from "../util.js";

export function Stat({ label, value, sub, tone, icon: Icon, testid }) {
  return (
    <div class={cx("stat", tone && `tone-${tone}`)} data-testid={testid}>
      <span class="stat-label">{Icon && <Icon size={14} />}{label}</span>
      <b class="num">{value}</b>
      {sub && <small>{sub}</small>}
    </div>
  );
}

export function Pill({ tone, icon: Icon, children, title, class: className }) {
  return <span class={cx("chip", tone, className)} title={title}>{Icon && <Icon size={12} />}{children}</span>;
}

export function Empty({ icon: Icon = Inbox, title, children, action }) {
  return (
    <div class="empty">
      <span class="empty-icon"><Icon size={26} /></span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Loading({ label = "Cargando…" }) {
  return <div class="dash-loading" role="status" data-testid="loading"><Loader2 class="spin-icon" size={20} /><span>{label}</span></div>;
}

export function ErrorBox({ message, onRetry }) {
  return (
    <div class="empty error" role="alert" data-testid="error">
      <span class="empty-icon"><CircleAlert size={26} /></span>
      <strong>No se pudo cargar</strong>
      <p>{message}</p>
      {onRetry && <button class="btn btn-sm" type="button" onClick={onRetry}><RefreshCw size={14} /> Reintentar</button>}
    </div>
  );
}

// the page of a request: spinner the first time, the error with a retry, or the content (kept while it refreshes)
export function Block({ q, children }) {
  if (q.data !== null) return children(q.data);
  if (q.error) return <ErrorBox message={q.error} onRetry={q.reload} />;
  return <Loading />;
}

// A button that asks «¿Seguro?» before doing something that cannot be undone.
export function ConfirmButton({ children, confirm = "Sí, seguro", onConfirm, class: className, icon: Icon, disabled, testid, label }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return undefined;
    const id = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(id);
  }, [armed]);
  if (armed) {
    return (
      <span class="confirm-pair">
        <button class="btn btn-sm btn-danger" type="button" data-testid={testid ? `${testid}-yes` : undefined} onClick={() => { setArmed(false); onConfirm(); }}>{confirm}</button>
        <button class="btn btn-sm btn-ghost" type="button" onClick={() => setArmed(false)}>No</button>
      </span>
    );
  }
  return (
    <button class={cx("btn btn-sm", className)} type="button" disabled={disabled} data-testid={testid} aria-label={label} title={label} onClick={() => setArmed(true)}>
      {Icon && <Icon size={14} />}{children}
    </button>
  );
}

export function Field({ label, hint, children, class: className }) {
  return (
    <label class={cx("field", className)}>
      <span class="field-label">{label}</span>
      {children}
      {hint && <span class="hint">{hint}</span>}
    </label>
  );
}
