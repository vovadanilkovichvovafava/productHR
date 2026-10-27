import { ReactNode } from 'react';
import { X, Bell } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/factorial/components/ui/button';
import { useAIDrawerStore } from '@/factorial/stores/useAIDrawerStore';

interface FactorialFormPageProps {
  /** Visual variant. 'card' = centered white card with floating icon plaque (for /tasks/new, /employees/new etc).
   *  'plain' = no card, no floating icon, title top-left, submit button top-right (for /dashboard/* forms). */
  variant?: 'card' | 'plain';
  /** Floating plaque icon (card variant). Ignored in plain variant. */
  icon?: ReactNode;
  /** Icon plaque bg color (card variant). */
  iconBg?: string;
  /** Title shown below icon plaque (card) or top-left (plain). */
  title: string;
  /** Subtitle */
  subtitle?: string;
  /** Breadcrumb crumbs (parent links) */
  breadcrumb: { label: string; href?: string }[];
  /** Form sections with headers + content */
  children: ReactNode;
  /** Submit button label */
  submitLabel?: string;
  /** Cancel destination, defaults to history -1 */
  cancelHref?: string;
  /** Optional right-rail tip panel (card variant) */
  tipPanel?: ReactNode;
  /** Optional left-rail step navigator (card variant) */
  stepNavigator?: ReactNode;
  /** Hint text shown below the form (used in plain variant) */
  footerHint?: string;
  /** What happens on submit — should call mockSave + navigate back */
  onSubmit?: () => void;
}

export default function FactorialFormPage({
  variant = 'card',
  icon,
  iconBg = 'bg-rose-50',
  title,
  subtitle,
  breadcrumb,
  children,
  submitLabel = 'Создать',
  cancelHref,
  tipPanel,
  stepNavigator,
  footerHint,
  onSubmit,
}: FactorialFormPageProps) {
  const navigate = useNavigate();
  const aiOpen = useAIDrawerStore((s) => s.open);
  const toggleAI = useAIDrawerStore((s) => s.toggle);
  const handleClose = () => {
    if (cancelHref) navigate(cancelHref);
    else navigate(-1);
  };

  // Top-right actions (Bell + orange-O Опе), always visible on form pages
  const headerActions = (
    <div className="flex items-center gap-3">
      <button type="button" className="p-2 rounded-fx-lg hover:bg-sidebar-hover" title="Уведомления" aria-label="Уведомления">
        <Bell className="w-4 h-4 text-text-muted" />
      </button>
      {!aiOpen && (
        <button
          type="button"
          onClick={toggleAI}
          className="w-8 h-8 rounded-full hover:scale-105 transition-transform"
          style={{ background: 'conic-gradient(from 180deg, #F5A51C, #E61A42, #F5A51C)' }}
          title="Открыть Опе"
          aria-label="Открыть Опе"
        />
      )}
    </div>
  );

  // PLAIN VARIANT — for /dashboard/* forms (kudos, event, post)
  if (variant === 'plain') {
    return (
      <div className="min-h-screen">
        {/* Breadcrumb header with right-aligned actions */}
        <div className="px-8 py-4 flex items-center justify-between text-fx-sm">
          <div className="flex items-center gap-2">
            {breadcrumb.map((c, i) => (
              <span key={i} className="flex items-center gap-2">
                {i > 0 && <span className="text-text-muted">›</span>}
                {c.href ? (
                  <Link
                    to={c.href}
                    className="text-text-primary/70 hover:text-text-primary inline-flex items-center gap-1.5"
                  >
                    {i === 0 && (
                      <span className="w-6 h-6 rounded-fx-md bg-rose-100 inline-flex items-center justify-center text-fx-xs">
                        📋
                      </span>
                    )}
                    {c.label}
                  </Link>
                ) : (
                  <span className="text-text-primary font-medium">{c.label}</span>
                )}
              </span>
            ))}
          </div>
          {headerActions}
        </div>

        {/* Title row with top-right submit */}
        <div className="px-12 pt-2 pb-6 flex items-center justify-between">
          <h1 className="text-fx-2xl font-semibold">{title}</h1>
          {onSubmit && <Button onClick={onSubmit}>{submitLabel}</Button>}
        </div>

        {/* Centered narrow column */}
        <div className="px-4 pb-16">
          <div className="max-w-[700px] mx-auto space-y-6">
            {subtitle && <p className="text-fx-sm text-text-muted">{subtitle}</p>}
            {children}
            {footerHint && <p className="text-fx-xs text-text-muted">{footerHint}</p>}
          </div>
        </div>
      </div>
    );
  }

  // CARD VARIANT — for /tasks/new, /employees/new etc
  return (
    <div className="min-h-screen">
      {/* Breadcrumb header with right-aligned actions */}
      <div className="px-8 py-4 flex items-center justify-between text-fx-sm">
        <div className="flex items-center gap-2">
          {breadcrumb.map((c, i) => (
            <span key={i} className="flex items-center gap-2">
              {i > 0 && <span className="text-text-muted">›</span>}
              {c.href ? (
                <Link
                  to={c.href}
                  className="text-text-primary/70 hover:text-text-primary inline-flex items-center gap-1.5"
                >
                  {i === 0 && (
                    <span className="w-6 h-6 rounded-fx-md bg-rose-100 inline-flex items-center justify-center text-fx-xs">
                      📋
                    </span>
                  )}
                  {c.label}
                </Link>
              ) : (
                <span className="text-text-primary font-medium">{c.label}</span>
              )}
            </span>
          ))}
        </div>
        {headerActions}
      </div>

      {/* Center card */}
      <div className="flex items-start justify-center py-12 px-4">
        <div className="relative w-full max-w-[720px] bg-white rounded-card shadow-card border border-card-border-soft p-10">
          {/* Floating icon plaque */}
          {icon && (
            <div
              className={`absolute -top-8 left-1/2 -translate-x-1/2 w-16 h-16 ${iconBg} rounded-card flex items-center justify-center shadow-card border border-card-border-soft`}
            >
              {icon}
            </div>
          )}

          {/* Close X */}
          <button
            type="button"
            onClick={handleClose}
            className="absolute top-4 right-4 p-1 rounded hover:bg-sidebar-hover text-text-muted"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>

          {/* Title block */}
          <div className="mt-4 mb-6">
            <h1 className="text-fx-2xl font-semibold">{title}</h1>
            {subtitle && <p className="text-fx-sm text-text-muted mt-1">{subtitle}</p>}
          </div>

          {/* 2-col with optional step navigator + tip */}
          <div className={stepNavigator || tipPanel ? 'grid grid-cols-[200px_1fr_180px] gap-6' : ''}>
            {stepNavigator && <div className="space-y-1">{stepNavigator}</div>}
            <div className="space-y-6 min-w-0">{children}</div>
            {tipPanel && <aside className="text-fx-xs text-text-muted leading-relaxed">{tipPanel}</aside>}
          </div>

          {/* Footer */}
          <div className="mt-8 pt-6 border-t border-card-border-soft flex justify-end gap-2">
            <Button variant="ghost" onClick={handleClose}>
              Отмена
            </Button>
            {onSubmit && <Button onClick={onSubmit}>{submitLabel}</Button>}
          </div>
        </div>
      </div>
    </div>
  );
}
