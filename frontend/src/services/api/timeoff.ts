import { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// TYPES
// ============================================================

export interface TimeOffRequest {
  id: number;
  user_id: number;
  user_name: string | null;
  type: 'vacation' | 'day_off' | 'sick_leave' | 'other';
  status: 'pending' | 'approved' | 'rejected';
  date_from: string;
  date_to: string;
  reason: string | null;
  reviewed_by: number | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
  reject_reason: string | null;
  created_at: string;
}

export interface TimeOffCalendarEntry {
  user_id: number;
  user_name: string;
  type: string;
  date_from: string;
  date_to: string;
  status: string;
}

// ============================================================
// API
// ============================================================

export const getTimeOffRequests = async (status?: string): Promise<TimeOffRequest[]> => {
  const { data } = await deduplicatedGet<TimeOffRequest[]>('/timeoff', {
    params: status ? { status } : {},
  });
  return data;
};

export const getTimeOffCalendar = async (): Promise<TimeOffCalendarEntry[]> => {
  const { data } = await deduplicatedGet<TimeOffCalendarEntry[]>('/timeoff/calendar');
  return data;
};

export const approveTimeOff = async (id: number): Promise<void> => {
  await debouncedMutation('post', `/timeoff/${id}/approve`);
};

export const rejectTimeOff = async (id: number, reason?: string): Promise<void> => {
  await debouncedMutation('post', `/timeoff/${id}/reject`, null, {
    params: reason ? { reason } : {},
  });
};
