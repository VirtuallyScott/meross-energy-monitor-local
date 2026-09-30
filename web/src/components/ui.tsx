import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";
import { useId } from "react";

import "./ui.css";

type Tone = "primary" | "quiet" | "danger";

export function Button({
  tone = "quiet",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone }) {
  return <button className={`btn btn-${tone} ${className}`} {...rest} />;
}

export function Panel({
  title,
  eyebrow,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <section className={`panel ${className}`} aria-labelledby={title ? id : undefined}>
      {(title || actions) && (
        <header className="panel-head">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && <h2 id={id}>{title}</h2>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Field({
  label,
  hint,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} aria-describedby={hint ? `${id}-hint` : undefined} {...rest} />
      {hint && (
        <p className="field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function Select({
  label,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} {...rest}>
        {children}
      </select>
    </div>
  );
}

export function StatusDot({ online, label }: { online: boolean; label?: string }) {
  return (
    <span className={`status ${online ? "status-on" : "status-off"}`}>
      <span className="status-dot" aria-hidden="true" />
      {label ?? (online ? "Online" : "Offline")}
    </span>
  );
}

export function Alert({
  children,
  tone = "danger",
}: {
  children: ReactNode;
  tone?: "danger" | "info";
}) {
  return (
    <p className={`alert alert-${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {children}
    </p>
  );
}
