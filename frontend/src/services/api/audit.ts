import { deduplicatedGet } from './client';

// Журнал действий (21.10.2026): кто, когда и что менял. Пишет сервер
// (middleware + services/audit.py), здесь только чтение — для админов HR.

export interface AuditItem {
  id: number;
  at: string | null;
  user_id: number | null;
  user_name: string | null;
  action: string | null;
  method: string;
  path: string;
  status: number | null;
  duration_ms: number | null;
  entity_id: number | null;
  entity_name: string | null;
  vacancy_id: number | null;
  vacancy_title: string | null;
  application_id: number | null;
  body: unknown;
}

export interface AuditFilters {
  userId?: number | null;
  entityId?: number | null;
  vacancyId?: number | null;
  onlyErrors?: boolean;
  beforeId?: number | null;
  limit?: number;
}

export const getAuditLog = async (
  f: AuditFilters,
): Promise<{ items: AuditItem[]; next_before_id: number | null }> => {
  const params: Record<string, string | number | boolean> = { limit: f.limit ?? 100 };
  if (f.userId) params.user_id = f.userId;
  if (f.entityId) params.entity_id = f.entityId;
  if (f.vacancyId) params.vacancy_id = f.vacancyId;
  if (f.onlyErrors) params.only_errors = true;
  if (f.beforeId) params.before_id = f.beforeId;
  const { data } = await deduplicatedGet<{ items: AuditItem[]; next_before_id: number | null }>('/audit', { params });
  return data;
};

export const getAuditUsers = async (): Promise<Array<{ user_id: number; name: string; count: number }>> => {
  const { data } = await deduplicatedGet<{ items: Array<{ user_id: number; name: string; count: number }> }>(
    '/audit/users',
  );
  return data.items;
};
