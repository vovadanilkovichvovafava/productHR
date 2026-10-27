import api from '@/services/api/client';

export interface UnifiedTimeOff {
  source: 'timeoff' | 'leave';
  source_id: number;
  user_id: number | null;
  person_name: string | null;
  type: 'vacation' | 'day_off' | 'sick' | 'family_leave' | 'bereavement' | 'other';
  type_label: string;
  start: string; // ISO
  end: string; // ISO
  days: number;
  status: 'pending' | 'approved' | 'rejected';
  reason: string | null;
}

/**
 * Объединённый орг-обзор всех отпусков (System A + B). Доступен только admin/owner;
 * для остальных бэкенд вернёт 403 (фронт обрабатывает как «не админ»).
 */
export const getAllTimeOff = (status?: 'pending' | 'approved' | 'rejected') =>
  api
    .get<UnifiedTimeOff[]>(`/timeoff/all${status ? `?status=${status}` : ''}`)
    .then((r) => r.data);
