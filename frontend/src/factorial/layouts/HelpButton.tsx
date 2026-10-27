import { useEffect, useRef, useState } from 'react';
import { HelpCircle, X, Phone, MessageCircle, ExternalLink } from 'lucide-react';

/**
 * Intercom-style support widget (bottom-right "?" button + popup menu),
 * matching Factorial's help launcher. Demo-mode: all actions show a toast/alert.
 */
export default function HelpButton() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const demo = (msg: string) => window.alert(`Demo mode — ${msg}`);

  return (
    <div ref={ref} className="fixed bottom-4 right-4 z-40">
      {open && (
        <div className="absolute bottom-12 right-0 w-[300px] bg-white rounded-2xl shadow-card-hover border border-card-border-soft overflow-hidden">
          {/* Call a specialist */}
          <button
            type="button"
            onClick={() => demo('звонок специалисту недоступен.')}
            className="w-full flex items-start gap-3 px-4 py-3 hover:bg-sidebar-hover text-left"
          >
            <div className="w-9 h-9 rounded-full bg-sidebar-hover flex items-center justify-center shrink-0">
              <Phone className="w-4 h-4 text-text-secondary" strokeWidth={1.5} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1 text-fx-sm font-semibold text-text-primary">
                Давайте поговорим <ExternalLink className="w-3 h-3 text-text-muted" />
              </div>
              <p className="text-fx-xs text-text-muted mt-0.5">
                Свяжитесь со специалистом по телефону. User ID: #3131819
              </p>
            </div>
          </button>

          {/* Chat */}
          <button
            type="button"
            onClick={() => demo('чат поддержки недоступен.')}
            className="w-full flex items-start gap-3 px-4 py-3 hover:bg-sidebar-hover text-left"
          >
            <div className="w-9 h-9 rounded-full bg-sidebar-hover flex items-center justify-center shrink-0">
              <MessageCircle className="w-4 h-4 text-text-secondary" strokeWidth={1.5} />
            </div>
            <div className="min-w-0">
              <div className="text-fx-sm font-semibold text-text-primary">Чат с нами</div>
              <p className="text-fx-xs text-text-muted mt-0.5">
                Есть вопросы? Наша команда поможет вам
              </p>
            </div>
          </button>

          <div className="border-t border-card-border-soft" />

          {/* Write us */}
          <button
            type="button"
            onClick={() => demo('внешняя ссылка недоступна.')}
            className="w-full flex items-center justify-between px-4 py-3 hover:bg-sidebar-hover text-left text-fx-sm text-text-primary"
          >
            Напишите нам <ExternalLink className="w-3.5 h-3.5 text-text-muted" />
          </button>

          {/* Help center */}
          <button
            type="button"
            onClick={() => demo('внешняя ссылка недоступна.')}
            className="w-full flex items-center justify-between px-4 py-3 hover:bg-sidebar-hover text-left text-fx-sm text-text-primary border-t border-card-border-soft"
          >
            Центр помощи <ExternalLink className="w-3.5 h-3.5 text-text-muted" />
          </button>
        </div>
      )}

      {/* Launcher button */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-9 h-9 rounded-full bg-slate-700 text-white shadow-card-hover flex items-center justify-center hover:bg-slate-800 transition-colors"
        title="Помощь"
        aria-label="Помощь"
      >
        {open ? <X className="w-4 h-4" /> : <HelpCircle className="w-4 h-4" strokeWidth={2} />}
      </button>
    </div>
  );
}
