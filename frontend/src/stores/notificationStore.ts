import { create } from 'zustand';

// Транзиентное «зазывное» уведомление, выезжающее над кнопкой «+» (NotifPeek).
export interface PeekItem {
  id: number;
  type: string;
  title: string;
  message: string | null;
  link: string | null;
}

interface NotificationState {
  unreadCount: number;
  setUnreadCount: (n: number | ((prev: number) => number)) => void;
  bumpUnread: () => void;
  // Очередь входящих peek'ов (показываем последние, ограничиваем длину).
  peeks: PeekItem[];
  pushPeek: (item: PeekItem) => void;
  dismissPeek: (id: number) => void;
  clearPeeks: () => void;
}

// Храним больше, чем показываем (NotifPeek рендерит 3 карточки + «+N»).
const MAX_PEEKS = 12;

export const useNotificationStore = create<NotificationState>((set) => ({
  unreadCount: 0,
  setUnreadCount: (n) => set((s) => ({ unreadCount: Math.max(0, typeof n === 'function' ? n(s.unreadCount) : n) })),
  bumpUnread: () => set((s) => ({ unreadCount: s.unreadCount + 1 })),
  peeks: [],
  pushPeek: (item) =>
    set((s) => ({
      // Без дублей по id; держим только последние MAX_PEEKS.
      peeks: [...s.peeks.filter((p) => p.id !== item.id), item].slice(-MAX_PEEKS),
    })),
  dismissPeek: (id) => set((s) => ({ peeks: s.peeks.filter((p) => p.id !== id) })),
  clearPeeks: () => set({ peeks: [] }),
}));
