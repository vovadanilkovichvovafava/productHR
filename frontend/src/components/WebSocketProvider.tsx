import { useEffect, useCallback, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useCallStore } from '@/stores/callStore';
import { useEntityStore } from '@/stores/entityStore';
import { useChatStore } from '@/stores/chatStore';
import { useFormBadgeStore } from '@/stores/formBadgeStore';
import { useNotificationStore } from '@/stores/notificationStore';
import { logger } from '@/utils/logger';
import { getNotifications } from '@/services/api/notifications';
import { attemptTokenRefresh } from '@/services/api/client';
import type { FormSubmissionPayload } from '@/types/websocket';
import { playAnketaChime, unlockAudio, showAnketaOsNotification } from '@/utils/notificationSound';

/**
 * WebSocket Provider Component
 *
 * Connects to the backend WebSocket and dispatches events to stores.
 * Should be placed inside ProtectedRoute so it only connects when authenticated.
 *
 * Supported events:
 * - call.progress, call.completed, call.failed -> callStore
 * - entity.created, entity.updated, entity.deleted -> entityStore
 * - chat.created, chat.updated, chat.deleted, chat.message -> chatStore
 */
export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  // Call store handlers
  const {
    setWebSocketConnected,
    handleCallProgress,
    handleCallCompleted,
    handleCallFailed,
    cleanup: cleanupCallStore
  } = useCallStore();

  // Entity store handlers
  const {
    handleEntityCreated,
    handleEntityUpdated,
    handleEntityDeleted
  } = useEntityStore();

  // Chat store handlers
  const {
    handleChatCreated,
    handleChatUpdated,
    handleChatDeleted,
    handleChatMessage
  } = useChatStore();

  const bumpEntityBadge = useFormBadgeStore((s) => s.bump);
  const setUnreadCount = useNotificationStore((s) => s.setUnreadCount);
  const pushPeek = useNotificationStore((s) => s.pushPeek);

  // Must be stable: an inline fn here makes useWebSocket's `connect` change every
  // render, which (when the WS can't connect) turns reconnects into a render-loop
  // storm that freezes the page. useCallback keeps `connect` stable.
  const onFormSubmission = useCallback(
    (p: FormSubmissionPayload) => {
      // Только бейдж карточки (если WS жив). Всплывающий тост даёт поллинг уведомлений
      // ниже — он надёжнее (WS form.submission на проде не доставляет), и так без дублей.
      bumpEntityBadge(p.entity_id);
    },
    [bumpEntityBadge],
  );

  const { isConnected, status } = useWebSocket({
    // Call events
    onCallProgress: handleCallProgress,
    onCallCompleted: handleCallCompleted,
    onCallFailed: handleCallFailed,
    // Entity events
    onEntityCreated: handleEntityCreated,
    onEntityUpdated: handleEntityUpdated,
    onEntityDeleted: handleEntityDeleted,
    // Chat events
    onChatCreated: handleChatCreated,
    onChatUpdated: handleChatUpdated,
    onChatDeleted: handleChatDeleted,
    onChatMessage: handleChatMessage,
    onFormSubmission,
    // Connection settings
    autoReconnect: true,
    reconnectInterval: 3000,
  });

  // Update store when connection status changes
  useEffect(() => {
    setWebSocketConnected(isConnected);
  }, [isConnected, setWebSocketConnected]);

  // Log connection status for debugging
  useEffect(() => {
    logger.log(`[WebSocketProvider] Status: ${status}, Connected: ${isConnected}`);
  }, [status, isConnected]);

  // ПРОАКТИВНЫЙ РЕФРЕШ access-токена. Токен живёт 15 мин; без упреждающего обновления
  // каждые ~15 мин наступало окно, где WebSocket ловил 403, а API — 401 (рефреш был
  // ТОЛЬКО реактивный, на поллинге), и юзера «выкидывало» на минуту. Обновляем токен
  // заранее: каждые 12 мин (запас 3 мин до истечения) + при возврате фокуса на вкладку
  // (ноутбук проснулся — токен мог протухнуть во сне, чиним до первого 401/403).
  // Провайдер смонтирован только у залогиненных (внутри ProtectedRoute), поэтому
  // отдельного гейта по user не нужно.
  useEffect(() => {
    const REFRESH_EVERY_MS = 12 * 60 * 1000;
    const id = setInterval(() => { void attemptTokenRefresh(); }, REFRESH_EVERY_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void attemptTokenRefresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  // Браузерная autoplay-политика блокирует звук до жеста пользователя — «разблокируем»
  // AudioContext на первый pointerdown/keydown, чтобы чайм потом мог проиграться.
  useEffect(() => { unlockAudio(); }, []);

  // Realtime по WebSocket на проде НЕ доставляет form.submission (уведомления в БД
  // создаются, но событие до клиента не доходит). Поэтому popup даём поллингом:
  // счётчик колокольчика обновляем всегда + ВСПЛЫВАЮЩИЙ тост на каждое НОВОЕ
  // уведомление (анкета и пр.), независимо от состояния WS. (Тост из onFormSubmission
  // убран, чтобы не дублить.)
  const lastSeenNotifId = useRef<number>(-1);
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const list = await getNotifications();
        if (!alive) return;
        setUnreadCount(list.filter((n) => !n.is_read).length);
        const maxId = list.reduce((m, n) => Math.max(m, n.id), -1);
        const prev = lastSeenNotifId.current;
        lastSeenNotifId.current = Math.max(prev, maxId);
        if (prev < 0) return; // первый прогон — не спамим существующими уведомлениями
        let anketaArrived = false;
        let anketaNotif: (typeof list)[number] | null = null;
        for (const n of list.filter((n) => n.id > prev).sort((a, b) => a.id - b.id)) {
          const m = /entity=(\d+)/.exec(n.link || '');
          if (n.type === 'form_submitted' && m) bumpEntityBadge(parseInt(m[1], 10));
          if (n.type === 'form_submitted') { anketaArrived = true; anketaNotif = n; }
          // Вместо верхнего тоста — анимированный peek над кнопкой «+» (NotifPeek).
          pushPeek({
            id: n.id,
            type: n.type,
            title: n.title,
            message: n.message,
            link: n.link,
          });
        }
        // Звук ТОЛЬКО на новую анкету, максимум раз на батч поллинга (без двойного бипа).
        // Идёт исключительно поллингом — надёжно на проде, где WS теряет form.submission.
        if (anketaArrived) {
          playAnketaChime();  // активная вкладка: синтез-чайм
          // Вкладка в фоне/свёрнута — Web Audio молчит; шлём системное уведомление
          // (свой звук, работает вне фокуса). Только когда страница скрыта.
          if (typeof document !== 'undefined' && document.hidden && anketaNotif) {
            showAnketaOsNotification(
              anketaNotif.title || 'Новая анкета',
              anketaNotif.message || '',
              anketaNotif.link || undefined,
            );
          }
        }
      } catch { /* ignore */ }
    };
    poll();
    const id = setInterval(poll, 25000);
    return () => { alive = false; clearInterval(id); };
  }, [setUnreadCount, bumpEntityBadge, pushPeek]);

  // Cleanup polling on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      cleanupCallStore();
    };
  }, [cleanupCallStore]);

  return <>{children}</>;
}
