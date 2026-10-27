import type {
  Vacancy, VacancyStatus, VacancyApplication, ApplicationStage,
  VacancyRecommendation,
  CalculateScoreRequest, CalculateScoreResponse, EntityScoreResult,
  BestMatchesRequest, BestMatchesResponse, MatchingVacanciesRequest, MatchingVacanciesResponse
} from '@/types';
import { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// VACANCIES API
// ============================================================

export interface VacancyFilters {
  status?: VacancyStatus;
  deleted?: boolean;
  department_id?: number;
  search?: string;
  skip?: number;
  limit?: number;
}

export interface VacancyCreate {
  title: string;
  description?: string;
  requirements?: string;
  responsibilities?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  location?: string;
  employment_type?: string;
  experience_level?: string;
  status?: VacancyStatus;
  priority?: number;
  tags?: string[];
  extra_data?: Record<string, unknown>;
  visible_to_all?: boolean;
  department_id?: number;
  hiring_manager_id?: number | null;
  closes_at?: string | null;
}

export interface VacancyUpdate {
  title?: string;
  description?: string;
  requirements?: string;
  responsibilities?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  location?: string;
  employment_type?: string;
  experience_level?: string;
  status?: VacancyStatus;
  priority?: number;
  tags?: string[];
  extra_data?: Record<string, unknown>;
  visible_to_all?: boolean;
  department_id?: number;
  hiring_manager_id?: number | null;
  closes_at?: string | null;
  custom_stages?: {
    columns: Array<{ key: string; label: string; visible: boolean; maps_to?: string }>;
  } | null;
  kanban_card_fields?: string[] | null;
}

export interface ApplicationCreate {
  vacancy_id: number;
  entity_id: number;
  stage?: ApplicationStage;
  rating?: number;
  notes?: string;
  source?: string;
}

export interface ApplicationUpdate {
  stage?: ApplicationStage;
  stage_order?: number;
  rating?: number;
  notes?: string;
  rejection_reason?: string;
  next_interview_at?: string;
  comment?: string;
  // Кому фронт СОБИРАЛСЯ менять этап. Бэк сверяет с заявкой и отвечает 409,
  // если карточка держала чужую заявку (страховка после бага 15.09).
  expected_entity_id?: number;
}

export const getVacancies = async (filters?: VacancyFilters): Promise<Vacancy[]> => {
  const params: Record<string, string> = {};
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null) params[key] = String(value);
    });
  }
  const { data } = await deduplicatedGet<Vacancy[]>('/vacancies', { params });
  return data;
};

/**
 * Загрузить ВСЕ вакансии постранично. Бэк /vacancies отдаёт максимум 100 за
 * запрос (limit le=100); один запрос без skip/limit молча обрезался на 50, и
 * вакансии пропадали из сайдбара/модалок/дропдаунов, когда их стало >50
 * (обратная связь: «пропал Трафик»). Используй там, где нужен ПОЛНЫЙ список.
 */
export const getAllVacancies = async (filters?: VacancyFilters): Promise<Vacancy[]> => {
  const PAGE = 100;
  const MAX_PAGES = 50; // предохранитель (до 5000 вакансий)
  const all: Vacancy[] = [];
  for (let page = 0; page < MAX_PAGES; page++) {
    const chunk = await getVacancies({ ...(filters || {}), skip: page * PAGE, limit: PAGE });
    all.push(...chunk);
    if (chunk.length < PAGE) break;
  }
  return all;
};

export const getVacancy = async (id: number): Promise<Vacancy> => {
  const { data } = await deduplicatedGet<Vacancy>(`/vacancies/${id}`);
  return data;
};

export const createVacancy = async (vacancyData: VacancyCreate): Promise<Vacancy> => {
  const { data } = await debouncedMutation<Vacancy>('post', '/vacancies', vacancyData);
  return data;
};

export const updateVacancy = async (id: number, updates: VacancyUpdate): Promise<Vacancy> => {
  const { data } = await debouncedMutation<Vacancy>('put', `/vacancies/${id}`, updates);
  return data;
};

export const deleteVacancy = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/vacancies/${id}`);
};

export interface AssignableUser {
  id: number;
  name: string;
}

export const getAssignableUsers = async (opts?: { includeOwners?: boolean }): Promise<AssignableUser[]> => {
  const { data } = await deduplicatedGet<AssignableUser[]>(
    opts?.includeOwners ? '/vacancies/assignable-users?include_owners=true' : '/vacancies/assignable-users',
  );
  return data;
};

export const assignVacancy = async (id: number, userIds: number[], all: boolean): Promise<Vacancy> => {
  const { data } = await debouncedMutation<Vacancy>('post', `/vacancies/${id}/assign`, { user_ids: userIds, all });
  return data;
};

export const takeVacancy = async (id: number, force = false): Promise<Vacancy> => {
  const path = force ? `/vacancies/${id}/take?force=true` : `/vacancies/${id}/take`;
  const { data } = await debouncedMutation<Vacancy>('post', path);
  return data;
};

// «Отказаться» — рекрутёр снимает себя с заявки (backend: /decline).
export const declineVacancy = async (id: number): Promise<void> => {
  await debouncedMutation('post', `/vacancies/${id}/decline`);
};

// ============================================================
// VACANCY APPLICATIONS API
// ============================================================

/** createdBy: рекрутёр или несколько — их кандидаты, 'all' — всех рекрутёров
 *  воронки (фильтр над воронкой, 21.10.2026), не задан — как решит сервер.
 *  Строку запроса собираем сами: axios превратил бы массив в created_by[]=…,
 *  а сервер ждёт created_by=1&created_by=2. */
export const getApplications = async (
  vacancyId: number,
  stage?: ApplicationStage,
  createdBy?: number | number[] | 'all',
): Promise<VacancyApplication[]> => {
  const query = new URLSearchParams();
  if (stage) query.set('stage', stage);
  if (createdBy === 'all') query.set('all_recruiters', 'true');
  else if (createdBy != null) {
    for (const id of Array.isArray(createdBy) ? createdBy : [createdBy]) query.append('created_by', String(id));
  }
  const qs = query.toString();
  const { data } = await deduplicatedGet<VacancyApplication[]>(
    `/vacancies/${vacancyId}/applications${qs ? `?${qs}` : ''}`,
  );
  return data;
};

export interface FunnelRecruiters {
  total: number;
  recruiters: Array<{ user_id: number; name: string; count: number }>;
}

/** Кто ведёт кандидатов в воронке и сколько у каждого — для фильтра над воронкой. */
export const getFunnelRecruiters = async (vacancyId: number): Promise<FunnelRecruiters> => {
  const { data } = await deduplicatedGet<FunnelRecruiters>(`/vacancies/${vacancyId}/applications/recruiters`);
  return data;
};

export const createApplication = async (vacancyId: number, applicationData: ApplicationCreate): Promise<VacancyApplication> => {
  const { data } = await debouncedMutation<VacancyApplication>('post', `/vacancies/${vacancyId}/applications`, applicationData);
  return data;
};

// «Забрать» кандидата в воронку на выбранного рекрутёра. Идемпотентно: если его
// в воронке нет — создаёт заявку на recruiter_id; если есть — меняет владельца.
export const takeApplication = async (
  vacancyId: number,
  payload: { entity_id: number; recruiter_id: number },
): Promise<VacancyApplication> => {
  const { data } = await debouncedMutation<VacancyApplication>(
    'post',
    `/vacancies/${vacancyId}/applications/take`,
    payload,
  );
  return data;
};

export const updateApplication = async (applicationId: number, updates: ApplicationUpdate): Promise<VacancyApplication> => {
  if (updates.stage) {
    // Видно в консоли браузера: кому и на какой этап ушёл запрос.
    console.info('[stage] PUT application', applicationId, '→', updates.stage, 'entity=', updates.expected_entity_id);
  }
  const { data } = await debouncedMutation<VacancyApplication>('put', `/vacancies/applications/${applicationId}`, updates);
  return data;
};

export const deleteApplication = async (applicationId: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/vacancies/applications/${applicationId}`);
};

// ============================================================
// RECRUITER STATS API
// ============================================================

export interface RecruiterStat {
  user_id: number;
  name: string;
  candidate_count: number;
}

export const getVacancyRecruiterStats = async (vacancyId: number): Promise<RecruiterStat[]> => {
  const { data } = await deduplicatedGet<RecruiterStat[]>(`/vacancies/${vacancyId}/recruiter-stats`);
  return data;
};

// ============================================================
// KANBAN BOARD API
// ============================================================



export const bulkMoveApplications = async (applicationIds: number[], stage: ApplicationStage): Promise<VacancyApplication[]> => {
  const { data } = await debouncedMutation<VacancyApplication[]>('post', '/vacancies/applications/bulk-move', {
    application_ids: applicationIds,
    stage
  });
  return data;
};

// ============================================================
// ENTITY-VACANCY INTEGRATION
// ============================================================

export const getEntityVacancies = async (entityId: number): Promise<VacancyApplication[]> => {
  const { data } = await deduplicatedGet<VacancyApplication[]>(`/entities/${entityId}/vacancies`);
  return data;
};


// ============================================================
// VACANCY RECOMMENDATIONS API
// ============================================================

export const getRecommendedVacancies = async (
  entityId: number,
  limit: number = 5
): Promise<VacancyRecommendation[]> => {
  const { data } = await deduplicatedGet<VacancyRecommendation[]>(
    `/entities/${entityId}/recommended-vacancies`,
    { params: { limit } }
  );
  return data;
};

export const autoApplyToVacancy = async (
  entityId: number,
  vacancyId: number
): Promise<{ id: number; vacancy_id: number; entity_id: number; stage: string; message: string }> => {
  const { data } = await debouncedMutation<{ id: number; vacancy_id: number; entity_id: number; stage: string; message: string }>('post', `/entities/${entityId}/auto-apply/${vacancyId}`);
  return data;
};

// ============================================================
// AI SCORING API
// ============================================================

/**
 * Calculate AI compatibility score between a candidate and vacancy.
 * @param request - Entity ID and Vacancy ID
 * @returns Detailed compatibility score
 */
export const calculateCompatibilityScore = async (
  request: CalculateScoreRequest
): Promise<CalculateScoreResponse> => {
  const { data } = await debouncedMutation<CalculateScoreResponse>(
    'post',
    '/scoring/calculate',
    request
  );
  return data;
};

/**
 * Find best matching candidates for a vacancy.
 * @param vacancyId - Vacancy ID
 * @param request - Limit and filter options
 * @returns List of top matching candidates with scores
 */
export const findBestMatchesForVacancy = async (
  vacancyId: number,
  request: BestMatchesRequest = {}
): Promise<BestMatchesResponse> => {
  const { data } = await debouncedMutation<BestMatchesResponse>(
    'post',
    `/scoring/vacancy/${vacancyId}/matches`,
    request
  );
  return data;
};

/**
 * Find matching vacancies for a candidate.
 * @param entityId - Entity (candidate) ID
 * @param request - Limit and filter options
 * @returns List of matching vacancies with scores
 */
export const findMatchingVacanciesForEntity = async (
  entityId: number,
  request: MatchingVacanciesRequest = {}
): Promise<MatchingVacanciesResponse> => {
  const { data } = await debouncedMutation<MatchingVacanciesResponse>(
    'post',
    `/scoring/entity/${entityId}/vacancies`,
    request
  );
  return data;
};

/**
 * Get compatibility score for an application.
 * @param applicationId - Application ID
 * @param recalculate - Force recalculation
 * @returns Compatibility score
 */
export const getApplicationScore = async (
  applicationId: number,
  recalculate: boolean = false
): Promise<CalculateScoreResponse> => {
  const { data } = await deduplicatedGet<CalculateScoreResponse>(
    `/scoring/application/${applicationId}`,
    { params: { recalculate } }
  );
  return data;
};

/**
 * Recalculate compatibility score for an application.
 * @param applicationId - Application ID
 * @returns Updated compatibility score
 */
export const recalculateApplicationScore = async (
  applicationId: number
): Promise<CalculateScoreResponse> => {
  const { data } = await debouncedMutation<CalculateScoreResponse>(
    'post',
    `/scoring/application/${applicationId}/recalculate`,
    {}
  );
  return data;
};

/**
 * Bulk calculate compatibility scores for multiple candidates against a vacancy.
 * @param vacancyId - Vacancy ID
 * @param entityIds - List of entity IDs to score
 * @returns List of entity scores
 */
export const bulkCalculateScores = async (
  vacancyId: number,
  entityIds: number[]
): Promise<EntityScoreResult[]> => {
  const params = new URLSearchParams();
  params.append('vacancy_id', String(vacancyId));
  entityIds.forEach(id => params.append('entity_ids', String(id)));

  const { data } = await debouncedMutation<EntityScoreResult[]>(
    'post',
    `/scoring/bulk?${params.toString()}`,
    {}
  );
  return data;
};

// ============================================================
// APPLICATION HISTORY API
// ============================================================

export interface ApplicationHistoryEntry {
  id: number;
  from_stage: string | null;
  to_stage: string;
  changed_by: string | null;
  comment: string | null;
  created_at: string;
}

export const getApplicationHistory = async (
  applicationId: number
): Promise<ApplicationHistoryEntry[]> => {
  const { data } = await deduplicatedGet<ApplicationHistoryEntry[]>(
    `/vacancies/applications/${applicationId}/history`
  );
  return data;
};

// Правка комментария к переводу. Этап не меняется — это исправление текста.
// Бэкенд сам проставит «кто и когда правил» (edited_by/edited_at).
export const updateApplicationHistory = async (
  applicationId: number,
  historyId: number,
  comment: string,
): Promise<{ comment: string | null; edited_at: string; edited_by_name: string | null }> => {
  const { data } = await debouncedMutation<{
    comment: string | null;
    edited_at: string;
    edited_by_name: string | null;
  }>('patch', `/vacancies/applications/${applicationId}/history/${historyId}`, { comment });
  return data;
};

// Закрепить запись ленты наверху (или снять закреп: entryKey = null).
// Закреп ОДИН на воронку и общий для всех, кто эту воронку видит.
export const setPinnedEntry = async (
  applicationId: number,
  entryKey: string | null,
): Promise<{ pinned_entry_key: string | null }> => {
  const { data } = await debouncedMutation<{ pinned_entry_key: string | null }>(
    'put',
    `/vacancies/applications/${applicationId}/pin`,
    { entry_key: entryKey },
  );
  return data;
};

export interface DeleteHistoryResult {
  success: boolean;
  /** Запись была последней — заявка вернулась на from_stage. */
  rolled_back: boolean;
  /** Этап заявки ПОСЛЕ удаления (для перестановки карточки без перезагрузки). */
  stage: string | null;
  /** Пересчитанный общий статус кандидата (Entity.status). */
  entity_status: string | null;
}

// Удаление ПОСЛЕДНЕЙ записи = отмена перевода: заявка едет обратно на from_stage
// (запрос рекрутёров 2026-09-23). Старые записи удаляются из лога без смены этапа.
export const deleteApplicationHistory = async (
  applicationId: number,
  historyId: number
): Promise<DeleteHistoryResult> => {
  const { data } = await debouncedMutation<DeleteHistoryResult>(
    'delete',
    `/vacancies/applications/${applicationId}/history/${historyId}`
  );
  return data;
};

// ============================================================
// LEGACY CLONE RECONCILIATION (superadmin one-off)
// ============================================================

export interface CloneReconcileItem {
  clone_id: number;
  original_id: number | null;
  title: string;
  action: 'merge' | 'skip';
  reason: string | null;
  moved: number;
  deduped: number;
  accepted_rescued: boolean;
}

export interface CloneReconcileReport {
  dry_run: boolean;
  clones_found: number;
  merged: number;
  skipped: number;
  apps_moved: number;
  apps_deduped: number;
  items: CloneReconcileItem[];
}

/**
 * Схлопнуть легаси-клоны вакансий в оригиналы (только superadmin).
 * dryRun=true — отчёт без изменений; false — выполнить перенос+удаление клонов.
 */
export const reconcileVacancyClones = async (dryRun: boolean): Promise<CloneReconcileReport> => {
  const { data } = await debouncedMutation<CloneReconcileReport>(
    'post',
    `/vacancies/admin/reconcile-clones?dry_run=${dryRun}`
  );
  return data;
};
