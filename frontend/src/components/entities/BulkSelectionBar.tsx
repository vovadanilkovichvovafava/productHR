import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

// ================================================================
// BULK SELECTION BAR — единая плавающая плашка массового выделения.
// Извлечена из «Все кандидаты» (эталонный богатый вид: «Выбрано
// кандидатов: N/1000», «Выбрать всех», «Сбросить», стопка аватарок,
// одна кнопка действия). Переиспользуется в «Все кандидаты» и в
// воронках — отличается только проп `action` (label/иконка/цвет/onClick).
// ================================================================

export interface BulkSelectionAvatar {
  id: number;
  name: string;
  photo_url?: string;
}

export interface BulkSelectionAction {
  label: string;
  icon: LucideIcon;
  // neutral — как «Взять на вакансию»; danger — красная, как «Удалить с воронки».
  variant: "neutral" | "danger";
  onClick: () => void;
  disabled?: boolean;
}

export function BulkSelectionBar({
  open,
  count,
  total = 1000,
  avatars,
  onSelectAll,
  onClear,
  onClose,
  actions,
}: {
  open: boolean;
  count: number;
  total?: number;
  avatars: BulkSelectionAvatar[];
  onSelectAll: () => void;
  onClear: () => void;
  onClose: () => void;
  actions: BulkSelectionAction[];
}) {
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ y: 28, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 28, opacity: 0 }}
          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          className="fixed bottom-[16px] inset-x-[16px] mx-auto z-[85] min-h-[198px] max-w-[680px] overflow-hidden rounded-t-[12px] rounded-b-[8px] border border-[var(--hf-ui-divider-soft)] border-t-[3px] border-t-[var(--hf-main-900)] bg-[var(--hf-white)] px-[var(--hf-space-xxl)] py-[20px] shadow-[0_18px_60px_var(--hf-alpha-300)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:border-t-white hf-dark-disabled:bg-[var(--hf-bg-dark)]"
        >
          <button
            type="button"
            onClick={onClose}
            className="absolute right-[22px] top-[20px] inline-flex h-[28px] w-[28px] items-center justify-center rounded-full text-[var(--hf-main-500)] transition-colors hover:bg-[var(--hf-black-alpha-04)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-06)] hf-dark-disabled:hover:text-[var(--hf-white)]"
            title="Закрыть"
          >
            <X className="h-[20px] w-[20px]" strokeWidth={1.75} />
          </button>

          <div className="flex items-center gap-[10px] pr-[54px]">
            <span className="text-[length:var(--hf-fs-m)] leading-[26px] font-medium text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
              Выбрано кандидатов: {count}
              <span className="ml-[2px] text-[var(--hf-main-500)]">/{total}</span>
            </span>
            <button
              type="button"
              onClick={onSelectAll}
              className="inline-flex h-[28px] items-center rounded-full bg-[var(--hf-bg-panel)] px-[10px] text-[length:var(--hf-fs-2xs)] leading-[18px] font-medium text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-main-200)] active:bg-[var(--hf-ui-muted-8)]"
            >
              Выбрать всех
            </button>
            <button
              type="button"
              onClick={onClear}
              className="inline-flex h-[28px] items-center rounded-full bg-[var(--hf-bg-panel)] px-[10px] text-[length:var(--hf-fs-2xs)] leading-[18px] font-medium text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-main-200)] active:bg-[var(--hf-ui-muted-8)]"
            >
              Сбросить
            </button>
          </div>

          <div className="mt-[22px] flex h-[58px] items-center">
            <div className="flex items-center">
              <AnimatePresence initial={false}>
                {avatars.slice(0, 12).map((avatar, index) => (
                  <motion.div
                    key={avatar.id}
                    layout
                    transition={{
                      layout: { duration: 0.28, ease: [0.22, 1, 0.36, 1] },
                    }}
                    className={clsx(
                      "relative h-[56px] w-[56px] rounded-full",
                      index > 0 && "-ml-[15px]",
                    )}
                    style={{ zIndex: avatars.length - index }}
                    title={avatar.name}
                  >
                    <motion.div
                      initial={{ opacity: 0, x: -22 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -16 }}
                      transition={{
                        duration: 0.26,
                        ease: [0.22, 1, 0.36, 1],
                      }}
                      className="relative h-full w-full overflow-hidden rounded-full border-[2px] border-[color:var(--hf-white)] bg-[var(--hf-ui-hover)] hf-dark-disabled:border-[var(--hf-bg-dark)] hf-dark-disabled:bg-[var(--hf-white-alpha-10)]"
                    >
                      {avatar.photo_url ? (
                        <img
                          src={avatar.photo_url}
                          alt={avatar.name}
                          referrerPolicy="no-referrer"
                          className="h-full w-full object-cover"
                          onError={(e) => {
                            (
                              e.currentTarget as HTMLImageElement
                            ).style.display = "none";
                          }}
                        />
                      ) : (
                        <>
                          <span className="absolute left-1/2 top-[13px] h-[14px] w-[14px] -translate-x-1/2 rounded-full bg-[var(--hf-ui-border)]" />
                          <span className="absolute left-1/2 top-[32px] h-[9px] w-[26px] -translate-x-1/2 rounded-[50%] bg-[var(--hf-ui-border)]" />
                        </>
                      )}
                    </motion.div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>

          <div className="mt-[24px] flex flex-wrap items-center gap-[var(--hf-space-s)]">
            {actions.map((action) => {
              const ActionIcon = action.icon;
              return (
                <button
                  key={action.label}
                  onClick={action.onClick}
                  disabled={action.disabled}
                  className={clsx(
                    "inline-flex h-[40px] items-center gap-[var(--hf-space-s)] rounded-[var(--hf-radius-s)] border px-[15px] text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-primary)] font-medium shadow-[0_1px_4px_var(--hf-alpha-150)] transition-colors disabled:opacity-50",
                    action.variant === "danger"
                      ? "border-[var(--hf-status-red-badge)] bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)] hover:brightness-95"
                      : "border-[var(--hf-ui-card-border)] bg-[var(--hf-white)] text-[var(--hf-main-900)] hover:border-[var(--hf-ui-border)] hover:bg-[var(--hf-white)] active:bg-[var(--hf-bg-panel)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-[var(--hf-white-alpha-10)] hf-dark-disabled:text-[var(--hf-white)]",
                  )}
                >
                  <ActionIcon className="h-[20px] w-[20px]" strokeWidth={1.8} />
                  {action.label}
                </button>
              );
            })}
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

export default BulkSelectionBar;
