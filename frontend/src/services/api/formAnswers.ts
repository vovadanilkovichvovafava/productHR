import api from './client';
import type { FormDispatchInfo } from './forms';

/** Страница «Анкеты → Ответы» (06.11.2026), сервер — routes/form_answers.py. */
export type FormAnswerStatus = 'submitted' | 'opened' | 'sent' | 'orphan';

export interface FormSendError {
  at: string | null;
  kind: string | null;
  status: number | null;
  message: string | null;
  online: boolean | null;
  count?: number;
}

export interface FormAnswerItem {
  kind: 'dispatch' | 'orphan';
  id: number;
  form_id: number;
  form_title: string | null;
  entity_id: number | null;
  entity_name: string | null;
  entity_status: string | null;
  sent_by_id: number | null;
  sent_by_name: string | null;
  created_at: string | null;
  opened_at: string | null;
  submitted_at: string | null;
  status: FormAnswerStatus;
  token: string | null;
  error: FormSendError | null;
  hint?: string | null;
}

export interface FormAnswersList {
  items: FormAnswerItem[];
  counts: Record<FormAnswerStatus | 'all', number>;
  forms: { id: number; title: string }[];
  senders: { id: number; name: string }[];
  can_attach: boolean;
}

export interface FormAnswerView extends FormDispatchInfo {
  entity_id: number | null;
  entity_name: string | null;
  errors: FormSendError[];
}

export const getFormAnswers = async (params: {
  status?: string; form_id?: number; sent_by?: number; days?: number; q?: string;
}): Promise<FormAnswersList> => {
  const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && v !== null));
  const { data } = await api.get('/form-answers', { params: clean });
  return data;
};

export const getFormAnswer = async (kind: 'dispatch' | 'orphan', id: number): Promise<FormAnswerView> => {
  const { data } = await api.get(kind === 'dispatch' ? `/form-answers/dispatch/${id}` : `/form-answers/submission/${id}`);
  return data;
};

export const attachFormAnswer = async (submissionId: number, entityId: number): Promise<{ dispatch_id: number; entity_id: number }> => {
  const { data } = await api.post(`/form-answers/submission/${submissionId}/attach`, { entity_id: entityId });
  return data;
};
