import type { MouseEventHandler } from 'react';
import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Loader2, Bold, Italic, List, ListOrdered, Link2, AtSign } from 'lucide-react';
import clsx from 'clsx';

const HUNTFLOW_ACTION_ICON_BY_LABEL: Record<
  string,
  { id: string; viewBox: string; label: string }
> = {
  'Письмо': { id: 'mail-usage', viewBox: '0 0 18 18', label: 'mail' },
  'Интервью': {
    id: 'calendar-usage',
    viewBox: '0 0 20 20',
    label: 'calendar',
  },
  'Оффер': {
    id: 'thumbs-up-usage',
    viewBox: '0 0 18 18',
    label: 'thumbs-up',
  },
  'Файл': { id: 'clip-usage', viewBox: '0 0 18 18', label: 'clip' },
};

// Иконки тулбара редактора — модерн-набор lucide (заменили старые «вордовские»
// из спрайта). Те же действия (B/I/списки/ссылка/упоминание), другой стиль.
const EDITOR_LUCIDE_BY_NAME: Record<string, LucideIcon> = {
  bold: Bold,
  italic: Italic,
  'bullet-list': List,
  'numbered-list': ListOrdered,
  link: Link2,
  at: AtSign,
};

type SvgSpriteIconProps = {
  icon: { id: string; viewBox: string; label: string };
  className: string;
};

function SvgSpriteIcon({ icon, className }: SvgSpriteIconProps) {
  return (
    <svg aria-label={icon.label} className={className} viewBox={icon.viewBox} role="img">
      <use
        href={`/huntflow-sprite.svg#${icon.id}`}
        xlinkHref={`/huntflow-sprite.svg#${icon.id}`}
      />
    </svg>
  );
}

export function HuntflowEditorIcon({ name }: { name: string }) {
  const Icon = EDITOR_LUCIDE_BY_NAME[name];
  if (!Icon) return null;
  return <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} aria-hidden />;
}

function HuntflowActionIcon({ label }: { label: string }) {
  const icon = HUNTFLOW_ACTION_ICON_BY_LABEL[label];
  if (!icon) return null;
  return <SvgSpriteIcon icon={icon} className="h-[18px] w-[18px]" />;
}

function HuntflowUnavailableIcon() {
  return (
    <svg
      aria-label="unavailable"
      className="h-[8px] w-[12px]"
      viewBox="0 0 11 13"
      role="img"
    >
      <use
        href="/huntflow-sprite.svg#unavailable-usage"
        xlinkHref="/huntflow-sprite.svg#unavailable-usage"
      />
    </svg>
  );
}

export type HuntflowActionChipProps = {
  icon: LucideIcon;
  label: string;
  displayLabel?: string;
  onClick?: MouseEventHandler<HTMLButtonElement>;
  danger?: boolean;
  loading?: boolean;
  disabled?: boolean;
  hasNotification?: boolean;
  notificationCount?: number;
  className?: string;
};

export function HuntflowActionChip({
  icon: Icon,
  label,
  displayLabel,
  onClick,
  danger,
  loading,
  disabled,
  hasNotification,
  notificationCount,
  className,
}: HuntflowActionChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      className={clsx(
        'hf-action-chip',
        danger && 'hf-action-chip-danger',
        loading && 'hf-action-chip-loading',
        className,
      )}
    >
      <span className="hf-action-chip-icon">
        {loading ? (
          <Loader2 className="hf-action-chip-lucide animate-spin" />
        ) : HUNTFLOW_ACTION_ICON_BY_LABEL[label] ? (
          <HuntflowActionIcon label={label} />
        ) : (
          <Icon className="hf-action-chip-lucide" />
        )}
        {hasNotification && (
          <span className="hf-action-chip-unavailable">
            <HuntflowUnavailableIcon />
          </span>
        )}
        {!loading && typeof notificationCount === 'number' && notificationCount > 0 && (
          <span className="hf-action-chip-badge" aria-label={`${notificationCount} новых ответов`}>
            {notificationCount > 9 ? '9+' : notificationCount}
          </span>
        )}
      </span>
      {displayLabel || label}
    </button>
  );
}

export function HuntflowOptionsIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3 8h12m0 0a3 3 0 1 0 6 0 3 3 0 0 0-6 0Zm-6 8h12M9 16a3 3 0 1 1-6 0"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HuntflowInfoRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="hf-info-row group">
      <span className="hf-info-label">
        <span className="hf-info-label-text">{label}</span>
        <span className="hf-info-label-line" />
      </span>
      <div className="hf-info-value">{children}</div>
    </div>
  );
}
