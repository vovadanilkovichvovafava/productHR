import api, { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// TYPES
// ============================================================

export interface Notification {
  id: number;
  user_id: number;
  type: string;
  title: string;
  message: string | null;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

export interface UnreadCountResponse {
  count: number;
}

// ============================================================
// API
// ============================================================

export const getNotifications = async (): Promise<Notification[]> => {
  const { data } = await deduplicatedGet<Notification[]>('/notifications');
  return data;
};

export const getUnreadCount = async (): Promise<UnreadCountResponse> => {
  const { data } = await deduplicatedGet<UnreadCountResponse>('/notifications/unread-count');
  return data;
};

export const markNotificationRead = async (id: number): Promise<void> => {
  await debouncedMutation('put', `/notifications/${id}/read`, {});
};

export const markAllNotificationsRead = async (): Promise<void> => {
  await debouncedMutation('put', '/notifications/read-all', {});
};

// Настройки типов уведомлений (тип → вкл/выкл), хранятся на аккаунте.
export type NotificationPrefs = Record<string, boolean>;

export const getNotificationPrefs = async (): Promise<NotificationPrefs> => {
  const { data } = await api.get<{ prefs: NotificationPrefs }>('/notifications/prefs');
  return data.prefs;
};

export const updateNotificationPrefs = async (
  prefs: NotificationPrefs,
): Promise<NotificationPrefs> => {
  const { data } = await api.put<{ prefs: NotificationPrefs }>('/notifications/prefs', { prefs });
  return data.prefs;
};
