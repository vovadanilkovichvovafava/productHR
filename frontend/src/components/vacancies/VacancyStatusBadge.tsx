import clsx from 'clsx';
import type { VacancyStatus } from '@/types';

/**
 * Status badge component for vacancies with colored backgrounds.
 * Colors are optimized for dark theme backgrounds.
 */

interface VacancyStatusBadgeProps {
  status: VacancyStatus;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * Status colors mapping:
 * - draft: gray
 * - open: green
 * - paused: yellow
 * - closed: red
 * - cancelled: red
 */
export const VACANCY_STATUS_BADGE_COLORS: Record<VacancyStatus, string> = {
  draft: 'bg-[var(--hf-main-100)] text-[var(--hf-main-700)] dark:bg-[var(--hf-status-gray-badge)] dark:text-[var(--hf-main-300)]',
  pending_review: 'bg-[var(--hf-status-purple-bg)] text-[var(--hf-status-purple)] dark:bg-[var(--hf-status-purple-badge)] dark:text-[var(--hf-status-purple)]',
  open: 'bg-[var(--hf-status-green-bg)] text-[var(--hf-status-green)] dark:bg-[var(--hf-status-green-badge)] dark:text-[var(--hf-status-green)]',
  paused: 'bg-[var(--hf-status-yellow-bg)] text-[var(--hf-status-yellow)] dark:bg-[var(--hf-status-yellow-badge)] dark:text-[var(--hf-status-yellow)]',
  closed: 'bg-[var(--hf-status-red-bg)] text-[var(--hf-red-700)] dark:bg-[var(--hf-status-red-badge)] dark:text-[var(--hf-red-300)]',
  cancelled: 'bg-[var(--hf-status-red-bg)] text-[var(--hf-red-700)] dark:bg-[var(--hf-status-red-badge)] dark:text-[var(--hf-red-300)]',
};

/**
 * English status labels for display.
 */
export const VACANCY_STATUS_BADGE_LABELS: Record<VacancyStatus, string> = {
  draft: 'Draft',
  pending_review: 'Pending review',
  open: 'Open',
  paused: 'Paused',
  closed: 'Closed',
  cancelled: 'Cancelled',
};

/**
 * Russian status labels (for backward compatibility).
 */
export const VACANCY_STATUS_BADGE_LABELS_RU: Record<VacancyStatus, string> = {
  draft: 'Черновик',
  pending_review: 'На рассмотрении',
  open: 'Открыта',
  paused: 'На паузе',
  closed: 'Закрыта',
  cancelled: 'Отменена',
};

const sizeClasses = {
  sm: 'text-xs px-1.5 py-0.5',
  md: 'text-xs px-2 py-0.5',
  lg: 'text-sm px-2.5 py-1',
};

export default function VacancyStatusBadge({
  status,
  size = 'md',
  className,
}: VacancyStatusBadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center font-medium rounded-full',
        sizeClasses[size],
        VACANCY_STATUS_BADGE_COLORS[status],
        className
      )}
    >
      {VACANCY_STATUS_BADGE_LABELS_RU[status]}
    </span>
  );
}
