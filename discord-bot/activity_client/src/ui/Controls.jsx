// Small form controls shared by the settings pages.
import { cx } from "../util.js";

export function Switch({ checked, onChange, label, disabled }) {
  return <button type="button" role="switch" class="switch" aria-checked={checked ? "true" : "false"} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)} />;
}

export function Segmented({ value, options, onChange, label }) {
  return (
    <div class="segmented" role="group" aria-label={label}>
      {options.map(([val, text]) => (
        <button key={val} type="button" aria-pressed={value === val ? "true" : "false"} onClick={() => onChange(val)}>{text}</button>
      ))}
    </div>
  );
}

export function Range({ value, min, max, step = 1, onChange, label, format = (v) => `${v}`, disabled }) {
  return (
    <div class="row" style={{ gap: "var(--sp-3)" }}>
      <input class="range" type="range" min={min} max={max} step={step} value={value} disabled={disabled} aria-label={label}
        onInput={(e) => onChange(Number(e.currentTarget.value))} />
      <span class="value num">{format(value)}</span>
    </div>
  );
}

// a labelled row: text on the left, the control on the right (or underneath when `stack`)
export function Setting({ title, hint, children, stack, testid }) {
  return (
    <div class={cx("setting", stack && "stack")} data-testid={testid}>
      <div class="info"><strong>{title}</strong>{hint && <span>{hint}</span>}</div>
      {children}
    </div>
  );
}

export function Section({ title, children }) {
  return <section class="section"><h2>{title}</h2>{children}</section>;
}

export function Page({ title, icon: Icon, children, actions, narrow = true }) {
  return (
    <div class="page" data-testid="page">
      <div class="page-head">
        {Icon && <Icon size={20} />}
        <h1 class="grow">{title}</h1>
        {actions}
      </div>
      <div class={cx("page-body", narrow && "narrow")}>{children}</div>
    </div>
  );
}
