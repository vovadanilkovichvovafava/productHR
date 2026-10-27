import { ReactNode } from 'react';
import { initials } from '../lib/format';

export function FxCard({ title, action, children, className = '' }: {
  title?: string; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <div className={`fx-card ${className}`}>
      {(title || action) && (
        <div className="fx-card-head">
          {title && <h3 className="fx-card-title">{title}</h3>}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function FxStat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="fx-stat">
      <div className="fx-stat-value">{value}</div>
      <div className="fx-stat-label">{label}</div>
      {hint && <div className="fx-stat-hint">{hint}</div>}
    </div>
  );
}

type Tone = 'gray' | 'green' | 'red' | 'amber';
export function FxPill({ children, tone = 'gray', dot = false }: { children: ReactNode; tone?: Tone; dot?: boolean }) {
  return (
    <span className={`fx-pill fx-pill--${tone}`}>
      {dot && <span className="fx-pill-dot" />}
      {children}
    </span>
  );
}

export function FxAvatar({ name, size = 36 }: { name: string | null | undefined; size?: number }) {
  return (
    <span className="fx-avatar" style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}>
      {initials(name)}
    </span>
  );
}

export function FxButton({ children, onClick, variant = 'primary', type = 'button', disabled = false }: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'secondary' | 'ghost'; type?: 'button' | 'submit'; disabled?: boolean;
}) {
  return (
    <button type={type} disabled={disabled} onClick={onClick} className={`fx-btn fx-btn--${variant}`}>
      {children}
    </button>
  );
}

export function FxSpinner({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div className="fx-loading">
      <div className="fx-spinner" />
      <span>{label}</span>
    </div>
  );
}

export function FxEmpty({ emoji = '📭', title, hint }: { emoji?: string; title: string; hint?: string }) {
  return (
    <div className="fx-empty">
      <div className="fx-empty-emoji">{emoji}</div>
      <div className="fx-empty-title">{title}</div>
      {hint && <div className="fx-empty-hint">{hint}</div>}
    </div>
  );
}
