import { cn } from '@/factorial/lib/cn';

type PillVariant = 'neutral' | 'success' | 'warning' | 'error';
interface StatusPillProps { label: string; variant?: PillVariant; dot?: boolean; }

const VARIANTS: Record<PillVariant, string> = {
  neutral: 'bg-white border border-card-border-soft text-text-primary',
  success: 'bg-emerald-50 text-emerald-700',
  warning: 'bg-amber-50 text-amber-700',
  error: 'bg-red-50 text-red-700',
};
const DOT_COLORS: Record<PillVariant, string> = {
  neutral: 'bg-slate-400', success: 'bg-status-progress', warning: 'bg-status-pending', error: 'bg-status-overdue',
};

export default function StatusPill({ label, variant = 'neutral', dot }: StatusPillProps) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-pill text-fx-xs font-medium', VARIANTS[variant])}>
      {dot && <span className={cn('w-1.5 h-1.5 rounded-full', DOT_COLORS[variant])} />}
      {label}
    </span>
  );
}
