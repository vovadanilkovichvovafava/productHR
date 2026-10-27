import { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// TYPES
// ============================================================

export interface Blocker {
  id: number;
  user_id: number;
  user_name: string | null;
  project_id: number | null;
  description: string;
  status: 'open' | 'resolved';
  resolved_by: number | null;
  resolver_name: string | null;
  resolved_at: string | null;
  resolve_comment: string | null;
  created_at: string;
}

// ============================================================
// API
// ============================================================

export const getBlockers = async (status?: string): Promise<Blocker[]> => {
  const { data } = await deduplicatedGet<Blocker[]>('/blockers', {
    params: status ? { status } : {},
  });
  return data;
};

export const resolveBlocker = async (id: number, comment?: string): Promise<void> => {
  await debouncedMutation('post', `/blockers/${id}/resolve`, null, {
    params: comment ? { comment } : {},
  });
};
