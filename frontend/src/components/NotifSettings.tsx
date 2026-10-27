import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Settings, Check, Loader2 } from "lucide-react";
import {
  getNotificationPrefs,
  updateNotificationPrefs,
  type NotificationPrefs,
} from "@/services/api/notifications";

// Группы типов уведомлений для UI. «Упоминания» = два бэкенд-типа сразу.
const GROUPS: { label: string; types: string[] }[] = [
  { label: "Упоминания", types: ["comment_mentioned", "comment_mention"] },
  { label: "Ответ на анкету", types: ["form_submitted"] },
  { label: "Новая заявка", types: ["new_request"] },
  { label: "Назначена заявка", types: ["request_assigned"] },
  { label: "Новый кандидат", types: ["new_candidate"] },
  { label: "Смена этапа", types: ["stage_change"] },
  { label: "Интервью", types: ["interview_scheduled"] },
  { label: "Практика", types: ["practice_started"] },
  { label: "Испытательный срок", types: ["probation_ending"] },
  { label: "Назначена задача", types: ["task_assigned"] },
  { label: "Блокер снят", types: ["blocker_resolved"] },
];

// Шестерёнка рядом с громкостью: открывает список типов уведомлений с
// чекбоксами (галочка = тип включён). Настройки хранятся на аккаунте; после
// изменения зовётся onChanged, чтобы родитель перечитал список и счётчик.
export function NotifSettings({ onChanged }: { onChanged?: () => void }) {
  const [open, setOpen] = useState(false);
  const [prefs, setPrefs] = useState<NotificationPrefs>({});
  const [loading, setLoading] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const ddRef = useRef<HTMLDivElement>(null);

  const openDropdown = async () => {
    const r = btnRef.current?.getBoundingClientRect();
    if (r) setPos({ top: r.bottom + 6, left: Math.max(8, r.right - 240) });
    setOpen(true);
    setLoading(true);
    try {
      setPrefs(await getNotificationPrefs());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      const t = e.target as Node;
      if (ddRef.current?.contains(t) || btnRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const groupEnabled = (g: (typeof GROUPS)[number]) => g.types.every((t) => prefs[t]);

  const toggleGroup = async (g: (typeof GROUPS)[number]) => {
    const next = !groupEnabled(g);
    const patch: NotificationPrefs = {};
    g.types.forEach((t) => {
      patch[t] = next;
    });
    setPrefs((p) => ({ ...p, ...patch }));
    try {
      await updateNotificationPrefs(patch);
      onChanged?.();
    } catch {
      // откат при ошибке
      setPrefs((p) => {
        const r = { ...p };
        g.types.forEach((t) => {
          r[t] = !next;
        });
        return r;
      });
    }
  };

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={() => (open ? setOpen(false) : openDropdown())}
        title="Настройки уведомлений"
        aria-label="Настройки уведомлений"
        className="flex items-center text-[var(--hf-dark-300)] transition-colors hover:text-[var(--hf-dark-100)]"
      >
        <Settings className="h-4 w-4" />
      </button>
      {open &&
        pos &&
        createPortal(
          <div
            ref={ddRef}
            style={{ top: pos.top, left: pos.left }}
            // Гасим mousedown, чтобы клик по чекбоксу не считался «вне» родительского
            // поповера и не закрывал его — можно отметить сразу несколько типов.
            onMouseDown={(e) => e.stopPropagation()}
            className="fixed z-[2000] w-[240px] overflow-hidden rounded-xl border border-[var(--hf-ui-border)] bg-[var(--hf-white)] py-1 shadow-[var(--hf-shadow-2xl)]"
          >
            <div className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--hf-main-500)]">
              Типы уведомлений
            </div>
            {loading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-4 w-4 animate-spin text-[var(--hf-main-400)]" />
              </div>
            ) : (
              GROUPS.map((g) => {
                const on = groupEnabled(g);
                return (
                  <button
                    key={g.label}
                    type="button"
                    onClick={() => toggleGroup(g)}
                    className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-bg-panel)]"
                  >
                    <span
                      className={
                        on
                          ? "flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] bg-[var(--hf-status-blue)] text-white"
                          : "flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] border border-[var(--hf-ui-border)] bg-white"
                      }
                    >
                      {on && <Check className="h-3 w-3" strokeWidth={3} />}
                    </span>
                    <span className="flex-1 truncate">{g.label}</span>
                  </button>
                );
              })
            )}
          </div>,
          document.body,
        )}
    </>
  );
}

export default NotifSettings;
