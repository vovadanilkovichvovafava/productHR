import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, Check, ClipboardList, VolumeX, Volume2, X } from "lucide-react";
import clsx from "clsx";
import { useNotificationStore } from "@/stores/notificationStore";
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  type Notification,
} from "@/services/api/notifications";
import { isAnketaSoundMuted, setAnketaSoundMuted } from "@/utils/notificationSound";
import { NotifSettings } from "@/components/NotifSettings";

// ================================================================
// NOTIF PEEK — кнопка уведомлений справа от «+» (FAB) + собственный поповер.
//  • Кнопка всегда видна: ярко-красная при непрочитанных, белая когда их нет;
//    лёгкая пульсация. Клик → СВОЙ список уведомлений над кнопкой (не трогает
//    меню аватара).
//  • При приходе НОВОГО уведомления — анимированный peek с текстом выезжает
//    НАД нижним рядом (над «+» и кнопкой), авто-сворачивается ~9с.
// Монтируется внутри .hf-hr-fab-wrap (position: relative).
// ================================================================

const AUTO_DISMISS_MS = 9000;

export function NotifPeek() {
  const peeks = useNotificationStore((s) => s.peeks);
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const setUnreadCount = useNotificationStore((s) => s.setUnreadCount);
  const dismissPeek = useNotificationStore((s) => s.dismissPeek);
  const clearPeeks = useNotificationStore((s) => s.clearPeeks);
  const navigate = useNavigate();

  // Стек: показываем максимум 3 последних карточки, остальное — «+N».
  const visiblePeeks = peeks.slice(-3);
  const overflow = peeks.length - visiblePeeks.length;

  // ── Собственный поповер списка уведомлений ──
  const [panelOpen, setPanelOpen] = useState(false);
  const [list, setList] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [soundMuted, setSoundMuted] = useState(isAnketaSoundMuted());
  const panelRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      setList(await getNotifications());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  // После смены настроек типов — перечитать список и счётчик (фильтр ретроактивный).
  const refreshAfterPrefs = useCallback(() => {
    void loadList();
    getUnreadCount()
      .then((r) => setUnreadCount(r.count))
      .catch(() => {});
  }, [loadList, setUnreadCount]);

  const openPanel = useCallback(() => {
    setPanelOpen(true);
    clearPeeks();
    void loadList();
  }, [clearPeeks, loadList]);

  // Закрытие по клику вне поповера.
  useEffect(() => {
    if (!panelOpen) return;
    const handler = (e: MouseEvent) => {
      const t = e.target as Node;
      const inPanel = panelRef.current?.contains(t);
      const inBtn = btnRef.current?.contains(t);
      if (!inPanel && !inBtn) setPanelOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [panelOpen]);

  // Авто-сворачивание: гасим самый старый peek через интервал (стек убывает).
  const oldestPeekId = peeks[0]?.id;
  useEffect(() => {
    if (oldestPeekId == null) return;
    const t = window.setTimeout(() => dismissPeek(oldestPeekId), AUTO_DISMISS_MS);
    return () => window.clearTimeout(t);
  }, [oldestPeekId, dismissPeek]);

  const handleOpenPeek = (p: { id: number; link: string | null }) => {
    // Синхрон с красной кнопкой-счётчиком: клик по всплывающему уведомлению
    // помечает его прочитанным и уменьшает счётчик. Раньше peek и unreadCount
    // жили отдельно — кнопка продолжала гореть, хотя уведомление уже открыли.
    markNotificationRead(p.id).catch(() => {});
    setUnreadCount((c) => Math.max(0, c - 1));
    dismissPeek(p.id);
    if (p.link) {
      navigate(p.link);
    } else {
      openPanel();
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
    } catch {
      /* ignore */
    }
    setUnreadCount(0);
    setList((prev) => prev.map((n) => ({ ...n, is_read: true })));
  };

  const handleItemClick = (n: Notification) => {
    if (!n.is_read) {
      markNotificationRead(n.id).catch(() => {});
      setUnreadCount((c) => Math.max(0, c - 1));
      setList((prev) =>
        prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)),
      );
    }
    if (n.link) {
      navigate(n.link);
      setPanelOpen(false);
    }
  };

  return (
    <>
      {/* Стек peek'ов — растёт ВВЕРХ над нижним рядом (над «+» и кнопкой).
          До 3 карточек, новейшая снизу (у кнопки); сверх — чип «+N». */}
      <div className="pointer-events-none absolute bottom-full left-0 z-[41] mb-2 -ml-3 flex w-[240px] flex-col items-stretch gap-1.5">
        {overflow > 0 && (
          <span className="pointer-events-none self-start rounded-full bg-[var(--hf-red-500)] px-2.5 py-1 text-[11px] font-bold leading-none text-white shadow-[0_6px_18px_rgba(225,29,72,0.45)]">
            +{overflow}
          </span>
        )}
        <AnimatePresence initial={false} mode="popLayout">
          {visiblePeeks.map((p) => {
            const PIcon = p.type === "form_submitted" ? ClipboardList : Bell;
            return (
              <motion.div
                key={p.id}
                layout
                role="button"
                tabIndex={0}
                onClick={() => handleOpenPeek(p)}
                initial={{ opacity: 0, y: 10, scale: 0.94 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: -12, scale: 0.96 }}
                transition={{ type: "spring", stiffness: 460, damping: 30 }}
                className="pointer-events-auto relative flex w-full cursor-pointer items-start gap-2 overflow-hidden rounded-[var(--hf-radius-s)] border border-[var(--hf-ui-border)] bg-[var(--hf-white)] px-3 py-2.5 text-left shadow-[0_14px_44px_var(--hf-alpha-300)]"
              >
                <span
                  aria-hidden
                  className="absolute inset-y-0 left-0 w-[3px] bg-[var(--hf-cyan-500)]"
                />
                <span className="mt-[1px] flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--hf-bg-panel)] text-[var(--hf-cyan-700)]">
                  <PIcon className="h-3.5 w-3.5" strokeWidth={1.9} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[11px] font-semibold uppercase tracking-wide text-[var(--hf-main-500)]">
                    {p.type === "form_submitted" ? "Ответ на анкету" : p.title}
                  </span>
                  <span className="mt-0.5 block truncate text-[13px] font-medium leading-snug text-[var(--hf-main-900)]">
                    {p.message || p.title}
                  </span>
                </span>
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={(e) => {
                    e.stopPropagation();
                    dismissPeek(p.id);
                  }}
                  className="ml-0.5 mt-[1px] inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[var(--hf-main-400)] transition-colors hover:bg-[var(--hf-black-alpha-04)] hover:text-[var(--hf-main-700)]"
                  title="Скрыть"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Поповер списка уведомлений — НАД нижним рядом (над «+» и кнопкой),
          в той же привязке, что и peek. */}
      <div className="absolute bottom-full left-0 z-[45] mb-2 -ml-3">
        <AnimatePresence>
          {panelOpen && (
            <motion.div
              ref={panelRef}
              initial={{ opacity: 0, y: 8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.97 }}
              transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
              className="hf-hr-notifications-popover max-h-96 w-80 overflow-hidden rounded-xl shadow-[var(--hf-shadow-2xl)]"
            >
                <div className="hf-hr-notifications-header flex items-center justify-between px-4 py-3">
                  <span className="hf-hr-notifications-title text-sm font-medium">
                    Уведомления
                  </span>
                  <div className="flex items-center gap-3">
                    <NotifSettings onChanged={refreshAfterPrefs} />
                    <button
                      type="button"
                      onClick={() => {
                        const next = !soundMuted;
                        setAnketaSoundMuted(next);
                        setSoundMuted(next);
                      }}
                      title={soundMuted ? "Включить звук" : "Выключить звук"}
                      aria-label={soundMuted ? "Включить звук" : "Выключить звук"}
                      className="flex items-center text-[var(--hf-dark-300)] transition-colors hover:text-[var(--hf-dark-100)]"
                    >
                      {soundMuted ? (
                        <VolumeX className="h-4 w-4" />
                      ) : (
                        <Volume2 className="h-4 w-4" />
                      )}
                    </button>
                    {unreadCount > 0 && (
                      <button
                        type="button"
                        onClick={handleMarkAllRead}
                        className="flex items-center gap-1 text-xs text-[var(--hf-status-blue)] transition-colors hover:text-[var(--hf-cyan-400)]"
                      >
                        <Check className="h-3 w-3" />
                        Прочитать все
                      </button>
                    )}
                  </div>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  {loading ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="hf-loading-spinner h-5 w-5 border-2" />
                    </div>
                  ) : list.length === 0 ? (
                    <div className="hf-hr-notifications-empty py-8 text-center text-xs">
                      Нет уведомлений
                    </div>
                  ) : (
                    list.map((notif) => (
                      <button
                        key={notif.id}
                        type="button"
                        onClick={() => handleItemClick(notif)}
                        className={clsx(
                          "hf-hr-notifications-item w-full px-4 py-3 text-left transition-colors",
                          !notif.is_read && "hf-hr-notifications-item-unread",
                        )}
                      >
                        <div className="flex items-start gap-2">
                          {!notif.is_read && (
                            <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-[var(--hf-status-blue)]" />
                          )}
                          <div
                            className={clsx(
                              "min-w-0 flex-1",
                              notif.is_read && "ml-4",
                            )}
                          >
                            <p className="hf-hr-notifications-item-title truncate text-xs font-medium">
                              {notif.title}
                            </p>
                            {notif.message && (
                              <p className="hf-hr-notifications-item-message mt-0.5 truncate text-[length:var(--hf-fs-4xs)]">
                                {notif.message}
                              </p>
                            )}
                            <p className="hf-hr-notifications-item-time mt-1 text-[length:var(--hf-fs-5xs)]">
                              {new Date(notif.created_at).toLocaleString("ru-RU", {
                                day: "numeric",
                                month: "short",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </p>
                          </div>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </motion.div>
            )}
        </AnimatePresence>
      </div>

      {/* Постоянная кнопка уведомлений — справа от «+». z ниже модалок (50),
          чтобы не светиться поверх окна «Добавить на вакансию» и т.п. */}
      <div className="absolute left-full top-1/2 z-[40] ml-2 -translate-y-1/2">
        <motion.button
          ref={btnRef}
          type="button"
          onClick={() => (panelOpen ? setPanelOpen(false) : openPanel())}
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: [1, 1.05, 1] }}
          transition={{
            opacity: { duration: 0.2 },
            scale: { duration: 2, repeat: Infinity, ease: "easeInOut" },
          }}
          className={
            unreadCount > 0
              ? "inline-flex items-center gap-1.5 rounded-full border-2 border-[var(--hf-red-500)] bg-[var(--hf-red-500)] px-3 py-1.5 text-[12px] font-bold text-white shadow-[0_0_18px_rgba(225,29,72,0.7)]"
              : "inline-flex h-11 w-11 items-center justify-center rounded-full border border-[var(--hf-ui-border)] bg-white text-[var(--hf-main-800)] shadow-[0_0_16px_rgba(255,255,255,0.55)]"
          }
          title="Открыть уведомления"
        >
          {/* Без уведомлений — крупнее (была слишком маленькая иконка). */}
          <Bell className={unreadCount > 0 ? "h-3.5 w-3.5" : "h-5 w-5"} strokeWidth={2.2} />
          {unreadCount > 0 && (
            <span>{unreadCount > 99 ? "99+" : unreadCount} новых</span>
          )}
        </motion.button>
      </div>
    </>
  );
}

export default NotifPeek;
