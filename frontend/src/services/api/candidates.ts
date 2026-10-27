import type { PriorRejection } from '@/components/candidates/priorRejection';
import api, { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// CANDIDATE SEARCH CRM API
// ============================================================

export interface CandidateSearchParams {
  q?: string;
  status?: string;
  source?: string;
  recruiter_id?: number;
  date_from?: string;
  date_to?: string;
  tags?: string;
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_order?: string;
}

export interface CandidateItem {
  id: number;
  name: string;
  email?: string;
  phone?: string;
  telegram_username?: string;
  status: string;
  source?: string;
  recruiter_id?: number;
  recruiter_name?: string;
  created_at: string;
  tags: string[];
  position?: string;
  company?: string;
  vacancy_count: number;
  is_duplicate: boolean;
}

export interface CandidateStats {
  total: number;
  new: number;
  screening: number;
  practice: number;
  hired: number;
  rejected: number;
}

export interface CandidateSearchResult {
  items: CandidateItem[];
  total: number;
  page: number;
  per_page: number;
  stats: CandidateStats;
}

export interface RecruiterOption {
  id: number;
  name: string;
}

export interface BulkActionPayload {
  entity_ids: number[];
  action: string;
  vacancy_id?: number;
  status?: string;
  tag?: string;
}

export interface BulkActionResult {
  success: boolean;
  action: string;
  affected: number;
  skipped?: number;
}

/**
 * Search candidates with filters, pagination, stats.
 */
export const searchCandidates = async (
  params: CandidateSearchParams,
): Promise<CandidateSearchResult> => {
  const searchParams: Record<string, string> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams[key] = String(value);
    }
  });
  const { data } = await deduplicatedGet<CandidateSearchResult>('/candidates/search', {
    params: searchParams,
  });
  return data;
};

/**
 * Perform bulk action on selected candidates.
 * For export_csv the response is a blob.
 */
export const bulkCandidateAction = async (
  payload: BulkActionPayload,
): Promise<BulkActionResult | Blob> => {
  if (payload.action === 'export_csv') {
    const response = await api.post('/candidates/bulk-action', payload, {
      responseType: 'blob',
    });
    return response.data as Blob;
  }
  const { data } = await debouncedMutation<BulkActionResult>(
    'post',
    '/candidates/bulk-action',
    payload,
  );
  return data;
};

/**
 * Get list of recruiters for the filter dropdown.
 */
export const getCandidateRecruiters = async (): Promise<RecruiterOption[]> => {
  const { data } = await deduplicatedGet<RecruiterOption[]>('/candidates/recruiters');
  return data;
};

/**
 * Get all existing tags for autocomplete.
 */
export const getCandidateTags = async (): Promise<string[]> => {
  const { data } = await deduplicatedGet<string[]>('/candidates/tags');
  return data;
};


// ============================================================
// KANBAN BOARD API
// ============================================================

export interface KanbanCard {
  id: number;
  name: string;
  email?: string;
  phone?: string;
  telegram_username?: string;
  // Полные списки контактов (после склейки дублей у человека их может быть
  // несколько — разные телефоны/телеграмы/почты из разных записей). Заполняются
  // там, где грузится полный Entity (архивная карточка, дедуп-баннер).
  phones?: string[];
  emails?: string[];
  telegram_usernames?: string[];
  position?: string;
  source?: string;
  source_url?: string;
  recruiter_id?: number | null;
  recruiter_name?: string;
  created_at: string;
  /** Когда кандидата перевели на ТЕКУЩИЙ статус: строка списка показывает эту
   *  дату рядом с этапом, по ней же сервер сортирует список. null — перевода в
   *  истории нет, тогда показываем дату добавления. */
  status_changed_at?: string | null;
  /** Место в общем порядке доски: дата этапа, при поиске — совпадение. */
  rank?: number | null;
  tags: string[];
  photo_url?: string;
  company?: string;
  city?: string;
  age?: string;
  salary?: string;
  total_experience?: string;
  vacancy_name?: string;
  // Воронка, по которой сейчас показан статус кандидата, и сколько у него воронок
  // всего — список рисует подпись «воронка (+N)», чтобы было видно, где он сейчас.
  status_vacancy_name?: string | null;
  funnel_count?: number;
  // Этапы по всем живым воронкам кандидата (живые впереди) — строка списка
  // показывает «Выполняет ТЗ · Трафик, Отказ · UAM».
  funnels?: Array<{ vacancy_title: string; stage: string }>;
  rejection_reason?: string;
  /** Карточка из теневой базы — приходит в выдачу ТОЛЬКО при поиске, метится «Архив». */
  is_archived?: boolean;
  /** «Был отказ»: последний отказ человека в другой его карточке / архиве
   *  (+ count) — components/candidates/priorRejection.tsx. */
  prior_rejection?: PriorRejection | null;
  /** Версия для оптимистичной блокировки: форма правки шлёт её в PUT /entities,
   *  бэк отвечает 409, если кандидата успел изменить кто-то ещё. */
  version?: number;
  /** Яркие ярлыки у ФИО — метки справочника, поднятые к имени у этого кандидата. */
  headline_tags?: { name: string; color: string }[];
  extra_data?: Record<string, any>;
}

export interface KanbanColumn {
  status: string;
  label: string;
  cards: KanbanCard[];
  count: number;
}

export interface KanbanBoardResponse {
  columns: KanbanColumn[];
  total: number;
  // Искали «@ник», совпадений по нику нет → сервер вернул обычный поиск
  // (имя/контакты). Окно подписывает это строкой под вкладками.
  nick_fallback?: boolean;
}

/**
 * Get candidates kanban board grouped by status.
 */
export const getCandidatesKanban = async (params?: {
  q?: string;
  recruiter_id?: number;
  date_from?: string;
  date_to?: string;
  per_column?: number;
}): Promise<KanbanBoardResponse> => {
  const searchParams: Record<string, string> = {};
  if (params?.q) searchParams.q = params.q;
  if (params?.recruiter_id) searchParams.recruiter_id = String(params.recruiter_id);
  if (params?.date_from) searchParams.date_from = params.date_from;
  if (params?.date_to) searchParams.date_to = params.date_to;
  if (params?.per_column) searchParams.per_column = String(params.per_column);
  const { data } = await deduplicatedGet<KanbanBoardResponse>('/candidates/kanban', {
    params: searchParams,
  });
  return data;
};

/**
 * Полный список id кандидатов по фильтру доски — для «Выбрать всех».
 * Доска грузит лишь per_column карточек/колонку, поэтому select-all по
 * загруженным карточкам брал не всех. Здесь берём все id того же набора.
 */
export const getCandidateIds = async (params?: {
  q?: string;
  recruiter_id?: number;
  status?: string;
}): Promise<number[]> => {
  const searchParams: Record<string, string> = {};
  if (params?.q) searchParams.q = params.q;
  if (params?.recruiter_id) searchParams.recruiter_id = String(params.recruiter_id);
  if (params?.status && params.status !== 'all') searchParams.status = params.status;
  const { data } = await deduplicatedGet<{ ids: number[] }>('/candidates/ids', {
    params: searchParams,
  });
  return data.ids;
};

export type ChangeCandidateStatusResult = {
  success: boolean;
  /** Итоговый общий статус кандидата — по нему карточку ставят в колонку. */
  entity_status: string | null;
  /** Кандидат был в одной открытой воронке — перевели заявку. */
  application_id: number | null;
  /** Кандидат вне воронок — запись о переводе, добавленная в ленту. */
  note: Record<string, unknown> | null;
};

/**
 * Перевод кандидата из карточки «Все кандидаты». У кандидата вне воронок
 * сервер в той же транзакции пишет запись о переводе в ленту (с комментарием).
 */
export const changeCandidateStatus = async (
  entityId: number,
  status: string,
  opts?: { comment?: string; stage_label?: string },
): Promise<ChangeCandidateStatusResult> => {
  const { data } = await debouncedMutation<ChangeCandidateStatusResult>(
    'patch',
    `/candidates/${entityId}/status`,
    { status, ...(opts?.comment ? { comment: opts.comment } : {}), stage_label: opts?.stage_label },
  );
  return data;
};

export type CandidateStageHistoryEntry = {
  id: number;
  application_id: number;
  vacancy_title: string | null;
  from_stage: string | null;
  to_stage: string;
  changed_by: number | null;
  changed_by_name: string | null;
  comment: string | null;
  created_at: string | null;
};

/**
 * Сквозная история смены этапов кандидата по всем его откликам.
 * Тот же лог, что и в карточке воронки, но по entity_id (для «Все кандидаты»).
 */
export const getCandidateStageHistory = async (
  entityId: number,
): Promise<CandidateStageHistoryEntry[]> => {
  const { data } = await deduplicatedGet<CandidateStageHistoryEntry[]>(
    `/candidates/${entityId}/stage-history`,
  );
  return data;
};
