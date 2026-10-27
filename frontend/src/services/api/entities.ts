import type {
  Entity, EntityWithRelations, EntityType, EntityStatus, EntityCriteria
} from '@/types';
import api, { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// ENTITIES API
// ============================================================

export type OwnershipFilter = 'all' | 'mine' | 'shared';

export const getEntities = async (params?: {
  type?: EntityType;
  status?: EntityStatus;
  search?: string;
  tags?: string;
  ownership?: OwnershipFilter;
  department_id?: number;
  limit?: number;
  offset?: number;
}): Promise<Entity[]> => {
  const searchParams: Record<string, string> = {};
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams[key] = String(value);
    });
  }
  const { data } = await deduplicatedGet<Entity[]>('/entities', { params: searchParams });
  return data;
};

export const getEntity = async (id: number): Promise<EntityWithRelations> => {
  const { data } = await deduplicatedGet<EntityWithRelations>(`/entities/${id}`);
  return data;
};

export const createEntity = async (entityData: {
  type: EntityType;
  name: string;
  status?: EntityStatus;
  // Legacy single identifiers
  phone?: string;
  email?: string;
  telegram_user_id?: number;
  // Multiple identifiers
  telegram_usernames?: string[];
  emails?: string[];
  phones?: string[];
  company?: string;
  position?: string;
  tags?: string[];
  extra_data?: Record<string, unknown>;
  department_id?: number;
  // Expected salary for candidates
  expected_salary_min?: number;
  expected_salary_max?: number;
  expected_salary_currency?: string;
}): Promise<Entity> => {
  const { data } = await debouncedMutation<Entity>('post', '/entities', entityData);
  return data;
};

export const updateEntity = async (id: number, updates: {
  name?: string;
  status?: EntityStatus;
  // Legacy single identifiers
  phone?: string;
  email?: string;
  // Multiple identifiers
  telegram_usernames?: string[];
  emails?: string[];
  phones?: string[];
  company?: string;
  position?: string;
  tags?: string[];
  extra_data?: Record<string, unknown>;
  department_id?: number | null;
  // Expected salary for candidates
  expected_salary_min?: number;
  expected_salary_max?: number;
  expected_salary_currency?: string;
  /** Оптимистичная блокировка: версия карточки, с которой начали правку.
   *  Бэк сверяет её с текущей и отдаёт 409, если кандидата уже изменили. */
  version?: number;
}): Promise<Entity> => {
  const { data } = await debouncedMutation<Entity>('put', `/entities/${id}`, updates);
  return data;
};

export const deleteEntity = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/entities/${id}`);
};

/** Корзина (20.10.2026): удалённый кандидат хранится 7 дней целиком, вернуть может админ. */
export interface TrashItem {
  id: number;
  entity_id: number;
  name: string | null;
  deleted_by_name: string | null;
  deleted_at: string | null;
  restorable_until: string | null;
  restorable: boolean;
  restored_at: string | null;
  restored_by_name: string | null;
  purged_at: string | null;
  summary: { applications?: number; history?: number; files?: number };
  /** «application» — кандидат убран из одной воронки (карточка осталась). */
  kind?: 'entity' | 'application';
  vacancy_id?: number | null;
  vacancy_title?: string | null;
  /** Чей кандидат был в воронке (автор заявки). */
  owner_name?: string | null;
  stage?: string | null;
}

export interface RestoreResult {
  success: boolean;
  entity_id: number;
  vacancy_id?: number | null;
  kind?: 'entity' | 'application';
  skipped: Record<string, number>;
}

export const getEntityTrash = async (): Promise<TrashItem[]> => {
  const { data } = await deduplicatedGet<{ items: TrashItem[] }>('/entities/trash');
  return data.items;
};

export const restoreEntityFromTrash = async (
  trashId: number,
): Promise<RestoreResult> => {
  const { data } = await debouncedMutation<RestoreResult>(
    'post', `/entities/trash/${trashId}/restore`,
  );
  return data;
};

/** Удалённый кандидат «как обычная карточка» (23.10.2026): поля карточки,
 *  блоки воронок с историей из слепка корзины, список файлов без байтов. */
export interface TrashCardView {
  card: import('./candidates').KanbanCard & { status?: string; photo_url?: string };
  blocks: VacancyActivityBlock[];
  files: EntityFile[];
  trash: TrashItem;
}

export const getTrashCard = async (trashId: number): Promise<TrashCardView> => {
  const { data } = await deduplicatedGet<TrashCardView>(`/entities/trash/${trashId}/card`);
  return data;
};

/** Файл удалённого кандидата — из слепка корзины. */
export const downloadTrashFile = async (trashId: number, fileId: number): Promise<Blob> => {
  const { data } = await api.get(`/entities/trash/${trashId}/files/${fileId}`, { responseType: 'blob' });
  return data as Blob;
};

/**
 * Quick status update for Kanban drag & drop
 */
export const updateEntityStatus = async (id: number, status: EntityStatus): Promise<{
  id: number;
  status: EntityStatus;
  previous_status: EntityStatus;
}> => {
  const { data } = await debouncedMutation<{
    id: number;
    status: EntityStatus;
    previous_status: EntityStatus;
  }>('patch', `/entities/${id}/status`, { status });
  return data;
};

export const linkChatToEntity = async (entityId: number, chatId: number): Promise<void> => {
  await debouncedMutation<void>('post', `/entities/${entityId}/link-chat/${chatId}`);
};

export const unlinkChatFromEntity = async (entityId: number, chatId: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/entities/${entityId}/unlink-chat/${chatId}`);
};

// ============================================================
// RED FLAGS ANALYSIS
// ============================================================

export interface RedFlag {
  type: string;
  type_label: string;
  severity: 'low' | 'medium' | 'high';
  description: string;
  suggestion: string;
  evidence?: string;
}

export interface RedFlagsAnalysis {
  flags: RedFlag[];
  risk_score: number;
  summary: string;
  flags_count: number;
  high_severity_count: number;
  medium_severity_count: number;
  low_severity_count: number;
}

export interface RiskScoreResponse {
  entity_id: number;
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high';
}

/**
 * Get full red flags analysis for an entity.
 * Includes AI analysis of communications.
 */
export const getEntityRedFlags = async (
  entityId: number,
  vacancyId?: number
): Promise<RedFlagsAnalysis> => {
  const params = vacancyId ? { vacancy_id: vacancyId } : undefined;
  const { data } = await deduplicatedGet<RedFlagsAnalysis>(`/entities/${entityId}/red-flags`, { params });
  return data;
};

/**
 * Get quick risk score for an entity (0-100).
 * Fast calculation without AI analysis.
 */
export const getEntityRiskScore = async (entityId: number): Promise<RiskScoreResponse> => {
  const { data } = await deduplicatedGet<RiskScoreResponse>(`/entities/${entityId}/risk-score`);
  return data;
};

export const getEntityStatsByType = async (): Promise<Record<string, number>> => {
  const { data } = await deduplicatedGet<Record<string, number>>('/entities/stats/by-type');
  return data;
};

export const getEntityStatsByStatus = async (type?: EntityType): Promise<Record<string, number>> => {
  const params = type ? { type } : undefined;
  const { data } = await deduplicatedGet<Record<string, number>>('/entities/stats/by-status', { params });
  return data;
};

// ============================================================
// SMART SEARCH
// ============================================================





// ============================================================
// ENTITY CRITERIA
// ============================================================

export const getEntityCriteria = async (entityId: number): Promise<EntityCriteria> => {
  const { data } = await deduplicatedGet<EntityCriteria>(`/criteria/entities/${entityId}`);
  return data;
};

export const updateEntityCriteria = async (entityId: number, criteria: { name: string; description: string; weight: number; category: string }[]): Promise<EntityCriteria> => {
  const { data } = await debouncedMutation<EntityCriteria>('put', `/criteria/entities/${entityId}`, { criteria });
  return data;
};

// Default criteria by entity type
export interface EntityDefaultCriteriaResponse {
  entity_type: string;
  criteria: { name: string; description: string; weight: number; category: string }[];
  is_custom: boolean;
  preset_id: number | null;
}

export const getEntityDefaultCriteria = async (entityType: string): Promise<EntityDefaultCriteriaResponse> => {
  const { data } = await deduplicatedGet<EntityDefaultCriteriaResponse>(`/criteria/entity-defaults/${entityType}`);
  return data;
};

export const setEntityDefaultCriteria = async (
  entityType: string,
  criteria: { name: string; description: string; weight: number; category: string }[]
): Promise<EntityDefaultCriteriaResponse> => {
  const { data } = await debouncedMutation<EntityDefaultCriteriaResponse>('put', `/criteria/entity-defaults/${entityType}`, { criteria });
  return data;
};

// Entity Report Download
export const downloadEntityReport = async (entityId: number, reportType: string, format: string): Promise<Blob> => {
  const response = await fetch(`/api/entities/${entityId}/report`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({ report_type: reportType, format }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.blob();
};

// ============================================================
// SIMILAR CANDIDATES & DUPLICATES
// ============================================================

export interface SimilarCandidateResult {
  entity_id: number;
  entity_name: string;
  similarity_score: number;
  common_skills: string[];
  similar_experience: boolean;
  similar_salary: boolean;
  similar_location: boolean;
  match_reasons: string[];
  // Detailed comparison data for both candidates
  entity1_skills?: string[];
  entity2_skills?: string[];
  entity1_experience?: number | null;
  entity2_experience?: number | null;
  entity1_salary_min?: number | null;
  entity1_salary_max?: number | null;
  entity2_salary_min?: number | null;
  entity2_salary_max?: number | null;
  entity1_location?: string | null;
  entity2_location?: string | null;
  entity1_position?: string | null;
  entity2_position?: string | null;
}

/**
 * Один факт, из-за которого бэк считает пару дублем. Приходит из единого ядра
 * (services/duplicate_matcher): окно сравнения подсвечивает ровно эти поля,
 * вместо того чтобы заново сравнивать значения на фронте.
 */
export interface DuplicateSignal {
  field: string;      // phone | email | telegram | name | birth_date | city | …
  label: string;      // человекочитаемая причина (RU)
  weight: number;     // 100 — идентификатор, 0 — мягкий/контекстный сигнал
  identity: boolean;
  left: string;
  right: string;
}

export interface DuplicateCandidateResult {
  entity_id: number;
  entity_name: string;
  /** Та же шкала, что у баннера: 100 — точное совпадение, иначе балл/процент. */
  confidence: number;
  match_reasons: string[];
  matched_fields: Record<string, string[]>;
  /** Тир совпадения — те же значения, что у HiddenDuplicateMeta.strength. */
  strength?: HiddenDuplicateMeta["strength"];
  /** exact — совпало ≥2 признака личности (красный), possible — один (жёлтый). */
  level?: DuplicateLevel;
  signals?: DuplicateSignal[];
}

export interface MergeEntitiesResponse {
  success: boolean;
  message: string;
  merged_entity_id: number;
  deleted_entity_id: number;
}

/**
 * Get similar candidates for an entity.
 *
 * Searches by:
 * - Skills (50% weight)
 * - Work experience (20% weight)
 * - Salary expectations (15% weight)
 * - Location (15% weight)
 *
 * @param entityId ID of the source candidate
 * @param limit Maximum number of results (1-50)
 * @returns List of similar candidates sorted by similarity_score descending
 */
export const getSimilarCandidates = async (
  entityId: number,
  limit: number = 10
): Promise<SimilarCandidateResult[]> => {
  const { data } = await deduplicatedGet<SimilarCandidateResult[]>(
    `/entities/${entityId}/similar`,
    { params: { limit: String(limit) } }
  );
  return data;
};

/**
 * Get possible duplicates for an entity.
 *
 * Checks:
 * - Name (with transliteration support Rus<->Eng)
 * - Email
 * - Phone
 * - Skills + company combination
 *
 * @param entityId ID of the entity to check
 * @param includeArchived If true, also detect archived entities as duplicates
 * @returns List of possible duplicates with confidence scores
 */
export const getDuplicateCandidates = async (
  entityId: number,
  includeArchived = false
): Promise<DuplicateCandidateResult[]> => {
  const url = includeArchived
    ? `/entities/${entityId}/duplicates?include_archived=true`
    : `/entities/${entityId}/duplicates`;
  const { data } = await deduplicatedGet<DuplicateCandidateResult[]>(url);
  return data;
};

/**
 * Merge two entities (duplicates).
 *
 * The target entity remains, source entity is deleted.
 * All related data (chats, calls, analyses) is transferred to target.
 *
 * @param targetEntityId ID of entity to keep
 * @param sourceEntityId ID of entity to merge and delete
 * @param keepSourceData If true, source data has priority on conflicts
 * @returns Merge operation result
 */
export const mergeEntities = async (
  targetEntityId: number,
  sourceEntityId: number,
  keepSourceData: boolean = false
): Promise<MergeEntitiesResponse> => {
  const { data } = await debouncedMutation<MergeEntitiesResponse>(
    'post',
    `/entities/${targetEntityId}/merge`,
    { source_entity_id: sourceEntityId, keep_source_data: keepSourceData }
  );
  return data;
};

/**
 * Meta written by the backend's duplicate matcher (similarity.py) into
 * `extra_data.hidden_duplicate_meta` on the newly-created/updated candidate.
 * `strength` 'soft' is the Level-2 anti-evasion tier (fuzzy name/DOB/phone/email/
 * city combo score); the other values are Level-1 exact-identifier matches.
 * `extra_data` on Entity/SmartSearchResult stays loosely typed
 * (Record<string, unknown>) — read this via
 * `card.extra_data?.hidden_duplicate_meta as HiddenDuplicateMeta | undefined`.
 */
export type DuplicateLevel = "exact" | "possible";

export interface HiddenDuplicateMeta {
  strength: "source" | "email" | "telegram" | "name" | "phone" | "soft" | "text";
  confidence: number;
  reasons: string[];
  matched_id: number;
  /** Нет у флагов, записанных до 21.09.2026 — такие карточка пересчитывает при открытии. */
  level?: DuplicateLevel;
}

/**
 * Meta written by the backend's resume-text-copy detector
 * (resume_text_twin.py) into `extra_data.text_twin`. Independent of
 * `hidden_duplicate_meta`/`hidden_duplicate_id` — a candidate can have a
 * text_twin flag WITHOUT any identity-match duplicate, and vice versa.
 * Read via `card.extra_data?.text_twin as TextTwinMeta | undefined`.
 */
export interface TextTwinMeta {
  twin_id: number;
  similarity: number; // 0..1
}

/**
 * Shadow dedup «Объединить»: merge the archived (shadow) duplicate INTO the
 * active candidate. Survivor = active (entityId); the archived duplicate is
 * deleted, its whole history moved over, and the hidden_duplicate_id flag cleared.
 */
export const mergeShadowDuplicate = async (
  entityId: number,
  duplicateId: number
): Promise<{ success: boolean; merged_entity_id: number; deleted_entity_id: number }> => {
  const { data } = await debouncedMutation<{
    success: boolean; merged_entity_id: number; deleted_entity_id: number;
  }>('post', `/entities/${entityId}/merge-shadow`, { duplicate_id: duplicateId });
  return data;
};

/**
 * Shadow dedup «Нет, это разные люди»: break the link with the archived
 * duplicate. Adds it to dismissed_duplicate_ids and clears the banner flag.
 */
export const dismissDuplicate = async (
  entityId: number,
  duplicateId: number
): Promise<{ success: boolean; dismissed_duplicate_id: number }> => {
  const { data } = await debouncedMutation<{
    success: boolean; dismissed_duplicate_id: number;
  }>('post', `/entities/${entityId}/dismiss-duplicate`, { duplicate_id: duplicateId });
  return data;
};

// ============================================================
// ENTITY ACTIVITY FEED
// ============================================================

export interface ActivityEvent {
  id: number;
  from_stage: string | null;
  to_stage: string;
  comment: string | null;
  changed_by_name: string | null;
  created_at: string;
  /** Комментарий правили: в строке остаётся автор и время написания, а эти
   *  два поля дают пометку «Изменено» и подсказку «кто и когда правил». */
  edited_at?: string | null;
  edited_by_name?: string | null;
}

// Закреп записи ленты у кандидата БЕЗ заявок: у воронки закреп лежит на
// заявке, а вне воронок хранить негде — кладём на саму карточку.
export const setEntityPinnedEntry = async (
  entityId: number,
  entryKey: string | null,
): Promise<{ pinned_entry_key: string | null }> => {
  const { data } = await api.put<{ pinned_entry_key: string | null }>(
    `/entities/${entityId}/pin`,
    { entry_key: entryKey },
  );
  return data;
};

export interface VacancyActivityBlock {
  application_id: number;
  vacancy_id: number;
  vacancy_title: string;
  current_stage: string;
  applied_at: string;
  last_stage_change_at: string;
  events: ActivityEvent[];
  /** Закреплённая запись этой воронки: «e:<id>» (перевод) или «n:<uuid>»
   *  (комментарий). Одна на воронку — у кандидата в двух воронках их две. */
  pinned_entry_key?: string | null;
  /** Кто ведёт кандидата в этой воронке (для окна «Забрать»). */
  owner_id?: number | null;
  owner_name?: string | null;
}

export const getEntityActivity = async (
  entityId: number
): Promise<VacancyActivityBlock[]> => {
  const { data } = await deduplicatedGet<VacancyActivityBlock[]>(
    `/entities/${entityId}/activity`
  );
  return data;
};

/**
 * Живой поиск дубля при ОТКРЫТИИ карточки. Ловит уже существующих дублей,
 * созданных до появления детекта (импорт/другой источник), без ручного
 * «Сверить». Помечает обе стороны, возвращает id найденного дубля или null.
 */
export const detectDuplicate = async (
  entityId: number
): Promise<{ duplicate_id: number | null; hidden_duplicate_meta?: HiddenDuplicateMeta | null }> => {
  const { data } = await debouncedMutation<{
    duplicate_id: number | null;
    hidden_duplicate_meta?: HiddenDuplicateMeta | null;
  }>('post', `/entities/${entityId}/detect-duplicate`, {});
  return data;
};

// === Теневая база (архив) ===

export interface ArchivedCandidate {
  id: number;
  name: string;
  email?: string | null;
  phone?: string | null;
  position?: string | null;
  company?: string | null;
  status?: string | null;
  tags: string[];
  photo_url?: string | null;
  source?: string | null;
  created_at?: string | null;
}

export interface ArchivedCandidatesPage {
  items: ArchivedCandidate[];
  total: number;
  page: number;
  per_page: number;
}

/** Список архивных (теневых) кандидатов. Только суперадмин. */
export const listArchivedCandidates = async (params?: {
  q?: string;
  page?: number;
  per_page?: number;
}): Promise<ArchivedCandidatesPage> => {
  const search: Record<string, string> = {};
  if (params?.q) search.q = params.q;
  if (params?.page) search.page = String(params.page);
  if (params?.per_page) search.per_page = String(params.per_page);
  const { data } = await deduplicatedGet<ArchivedCandidatesPage>('/entities/archive/list', {
    params: search,
  });
  return data;
};

/** «В архив»: убрать кандидата в теневую базу. */
export const archiveEntity = async (entityId: number): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>(
    'post', `/entities/${entityId}/archive`, {}
  );
  return data;
};

/** Вернуть кандидата из архива в активную базу. Только суперадмин. */
export const unarchiveEntity = async (entityId: number): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>(
    'post', `/entities/${entityId}/unarchive`, {}
  );
  return data;
};

/** Результат разовой сверки активных кандидатов с архивом. */
export interface RescanResult {
  scanned: number;
  flagged: number;
  newly_flagged: number;
  matches: {
    id: number;
    name: string;
    duplicate_id: number;
    duplicate_name?: string | null;
  }[];
}

/** Сверка всей базы: 2 минуты вместо общих 30 секунд. */
const LONG_SCAN_TIMEOUT = 120_000;

/** Прогнать детект по всем активным кандидатам против архива. Только суперадмин. */
export const rescanArchiveDuplicates = async (): Promise<RescanResult> => {
  // Сверка всей базы (тысячи анкет) — дольше обычного запроса: общий лимит 30 с
  // обрывал её на клиенте, хотя сервер продолжал считать.
  const { data } = await debouncedMutation<RescanResult>(
    'post', '/entities/archive/rescan', {}, { timeout: LONG_SCAN_TIMEOUT }
  );
  return data;
};

/** Дубликаты ВНУТРИ архива — группы совпадающих профилей. */
export interface ArchiveDupMember {
  id: number;
  name: string;
  email?: string | null;
  phone?: string | null;
  telegram?: string | null;
  position?: string | null;
}
export interface ArchiveDupGroups {
  groups: ArchiveDupMember[][];
  total_groups: number;
  total_dupes: number;
}

/** Найти группы дубликатов внутри архива. Только суперадмин. */
export const findArchiveDuplicates = async (): Promise<ArchiveDupGroups> => {
  const { data } = await debouncedMutation<ArchiveDupGroups>(
    'post', '/entities/archive/find-duplicates', {}, { timeout: LONG_SCAN_TIMEOUT }
  );
  return data;
};

/** Объединить два архивных профиля (source → survivor). Только суперадмин. */
export const mergeArchivedInto = async (
  survivorId: number,
  sourceId: number,
): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>(
    'post', `/entities/${survivorId}/merge-archived`, { source_id: sourceId }
  );
  return data;
};

/**
 * Compare two candidates.
 *
 * @param entityId ID of first candidate
 * @param otherEntityId ID of second candidate
 * @returns Comparison result with similarity score
 */
export const compareCandidates = async (
  entityId: number,
  otherEntityId: number
): Promise<SimilarCandidateResult> => {
  const { data } = await deduplicatedGet<SimilarCandidateResult>(
    `/entities/${entityId}/compare/${otherEntityId}`
  );
  return data;
};

/**
 * AI-powered comparison of two candidates using full context.
 * Uses files (resumes), chats, and calls for intelligent comparison.
 *
 * @param entityId ID of first candidate
 * @param otherEntityId ID of second candidate
 * @param onChunk Callback for each streaming chunk
 * @returns Promise that resolves when streaming is complete
 */
export const compareCandidatesAI = async (
  entityId: number,
  otherEntityId: number,
  onChunk: (chunk: string) => void
): Promise<void> => {
  const response = await fetch(
    `${api.defaults.baseURL}/entities/${entityId}/compare/${otherEntityId}/ai`,
    {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
      },
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Ошибка сравнения' }));
    throw new Error(error.detail || 'Ошибка сравнения');
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Streaming not supported');
  }

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    onChunk(chunk);
  }
};

/**
 * Download comparison report for two candidates as PDF, DOCX, or Markdown.
 *
 * @param entityId ID of first candidate
 * @param otherEntityId ID of second candidate
 * @param format Report format: 'pdf', 'docx', or 'markdown'
 * @returns Blob with report file
 */
export const downloadComparisonReport = async (
  entityId: number,
  otherEntityId: number,
  format: 'pdf' | 'docx' | 'markdown' = 'pdf'
): Promise<Blob> => {
  const response = await fetch(
    `${api.defaults.baseURL}/entities/${entityId}/compare/${otherEntityId}/report?format=${format}`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
      },
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Ошибка генерации отчёта' }));
    throw new Error(error.detail || 'Ошибка генерации отчёта');
  }

  return response.blob();
};

// ============================================================
// ENTITY FILES
// ============================================================

export interface EntityFile {
  id: number;
  entity_id: number;
  file_type: 'resume' | 'cover_letter' | 'test_assignment' | 'certificate' | 'portfolio' | 'other';
  file_name: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  description?: string;
  uploaded_by?: number;
  created_at: string;
}

export const getEntityFiles = async (entityId: number): Promise<EntityFile[]> => {
  const { data } = await deduplicatedGet<EntityFile[]>(`/entities/${entityId}/files`);
  return data;
};

export const uploadEntityFile = async (
  entityId: number,
  file: File,
  fileType: string,
  description?: string
): Promise<EntityFile> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('file_type', fileType);
  if (description) formData.append('description', description);

  const { data } = await api.post(`/entities/${entityId}/files`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000 // 2 мин — конвертация PDF→картинки на бэке бывает долгой
  });
  return data;
};

export const deleteEntityFile = async (entityId: number, fileId: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/entities/${entityId}/files/${fileId}`);
};

export interface EntityNote {
  id?: string;
  text: string;
  date: string;
  stage?: string | null;
  stage_label?: string | null;
  author_id?: number | null;
  author_name?: string | null;
  edited_at?: string | null;
  parent_key?: string | null;
  stage_at_write_label?: string | null;
  // Воронка (вакансия), в которой написан коммент; null/отсутствует = «Общий».
  vacancy_id?: number | null;
}

export const addEntityNote = async (
  entityId: number,
  payload: {
    text: string;
    stage?: string | null;
    stage_label?: string | null;
    // Дописка коммента к прошлой статусной записи таймлайна: reactionKey родителя
    // + метка этапа на момент написания (для плашки «оставлен на этапе X»).
    parent_key?: string | null;
    stage_at_write_label?: string | null;
    // Прежний этап — только для записи о смене этапа у кандидата ВНЕ воронок:
    // заявки нет, историю писать некуда, и удаление такой записи должно
    // возвращать кандидата назад так же, как корзина в воронке.
    from_status?: string | null;
    // Воронка (вакансия), в которой написан коммент — чтобы каждая воронка
    // показывала только свои комменты. null/undefined = «Общий».
    vacancy_id?: number | null;
  }
): Promise<{ success: boolean; note: EntityNote; total_notes: number }> => {
  const { data } = await api.post(`/entities/${entityId}/notes`, payload);
  return data;
};

export const updateEntityNote = async (
  entityId: number,
  noteId: string,
  text: string
): Promise<{ success: boolean; note: EntityNote }> => {
  const { data } = await api.patch(`/entities/${entityId}/notes/${encodeURIComponent(noteId)}`, { text });
  return data;
};

export const deleteEntityNote = async (
  entityId: number,
  noteId: string
): Promise<{
  success: boolean;
  total_notes: number;
  /** Удалили запись о переводе у кандидата вне воронок — он вернулся назад. */
  rolled_back?: boolean;
  /** Статус кандидата ПОСЛЕ удаления (для перестановки карточки без F5). */
  entity_status?: string | null;
}> => {
  const { data } = await api.delete(`/entities/${entityId}/notes/${encodeURIComponent(noteId)}`);
  return data;
};

export interface TimelineReaction {
  emoji: string;
  user_id: number;
  user_name: string;
  date?: string;
}

// Тоггл эмодзи-реакции на запись таймлайна. entry_key — стабильный ключ записи
// (заметка/событие/«created»). Возвращает обновлённый список реакций записи.
export const toggleTimelineReaction = async (
  entityId: number,
  entryKey: string,
  emoji: string
): Promise<{ success: boolean; entry_key: string; reactions: TimelineReaction[] }> => {
  const { data } = await api.post(`/entities/${entityId}/timeline-reaction`, {
    entry_key: entryKey,
    emoji,
  });
  return data;
};

export const reconvertResume = async (entityId: number): Promise<{ success: boolean; pages_created: number }> => {
  const { data } = await api.post(`/entities/${entityId}/files/reconvert-resume`);
  return data;
};

export const downloadEntityFile = async (entityId: number, fileId: number): Promise<Blob> => {
  const response = await fetch(`/api/entities/${entityId}/files/${fileId}/download`, {
    credentials: 'include'
  });

  if (!response.ok) {
    // 410 Gone = file_data утерян на сервере, фронт может предложить пересоздать.
    if (response.status === 410) {
      const err = new Error('Содержимое файла утрачено на сервере');
      (err as Error & { code?: string; status?: number }).code = 'file_content_lost';
      (err as Error & { code?: string; status?: number }).status = 410;
      throw err;
    }
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.blob();
};

// ============================================================
// PARSER API
// ============================================================

export interface ParsedResume {
  name?: string;
  email?: string;
  phone?: string;
  telegram?: string;
  position?: string;
  company?: string;
  experience_years?: number;
  skills: string[];
  salary_min?: number;
  salary_max?: number;
  salary_currency: string;
  location?: string;
  summary?: string;
  source_url?: string;
}

export interface ParsedVacancy {
  title: string;
  description?: string;
  requirements?: string;
  responsibilities?: string;
  skills?: string[];
  salary_min?: number;
  salary_max?: number;
  salary_currency: string;
  location?: string;
  employment_type?: string;
  experience_level?: string;
  company_name?: string;
  source_url?: string;
}

// Response wrapper from parser API
interface ParseResponse<T> {
  success: boolean;
  data?: T;
  source?: string;
  error?: string;
}

export const parseResumeFromUrl = async (url: string): Promise<ParsedResume> => {
  const { data: response } = await debouncedMutation<ParseResponse<ParsedResume>>(
    'post', '/parser/resume/url', { url }, { timeout: 120000 } // 2 minutes for URL fetch + AI parsing
  );
  if (!response.success || !response.data) {
    throw new Error(response.error || 'Error parsing resume');
  }
  return response.data;
};

export const parseResumeFromFile = async (
  file: File,
  onUploadProgress?: (pct: number) => void,
): Promise<ParsedResume> => {
  const formData = new FormData();
  formData.append('file', file);
  const { data: response } = await api.post<ParseResponse<ParsedResume>>('/parser/resume/file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000, // 2 minutes for AI parsing
    onUploadProgress: onUploadProgress
      ? (e) => { if (e.total) onUploadProgress(Math.round((e.loaded / e.total) * 100)); }
      : undefined,
  });
  if (!response.success || !response.data) {
    throw new Error(response.error || 'Error parsing file');
  }
  return response.data;
};

export const parseVacancyFromUrl = async (url: string): Promise<ParsedVacancy> => {
  const { data: response } = await debouncedMutation<ParseResponse<ParsedVacancy>>(
    'post', '/parser/vacancy/url', { url }, { timeout: 120000 } // 2 minutes for URL fetch + AI parsing
  );
  if (!response.success || !response.data) {
    throw new Error(response.error || 'Error parsing vacancy');
  }
  return response.data;
};

export const parseVacancyFromFile = async (file: File): Promise<ParsedVacancy> => {
  const formData = new FormData();
  formData.append('file', file);
  const { data: response } = await api.post<ParseResponse<ParsedVacancy>>('/parser/vacancy/file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000 // 2 minutes for AI parsing
  });
  if (!response.success || !response.data) {
    throw new Error(response.error || 'Error parsing vacancy file');
  }
  return response.data;
};

/**
 * Response from splitting vacancy description
 */
export interface SplitDescriptionResponse {
  success: boolean;
  requirements: string | null;
  responsibilities: string | null;
  short_description: string | null;
  error?: string;
}

/**
 * Split a vacancy description into requirements, responsibilities, and short description.
 * Uses AI to analyze and separate the text into structured fields.
 */
export const splitVacancyDescription = async (description: string): Promise<SplitDescriptionResponse> => {
  const { data: response } = await api.post<SplitDescriptionResponse>('/parser/vacancy/split-description', { description });
  if (!response.success) {
    throw new Error(response.error || 'Error splitting description');
  }
  return response;
};

/**
 * Result for a single resume in bulk import
 */
export interface BulkImportResult {
  filename: string;
  success: boolean;
  entity_id?: number;
  entity_name?: string;
  error?: string;
}

/**
 * Response from bulk resume import
 */
export interface BulkImportResponse {
  success: boolean;
  total_files: number;
  successful: number;
  failed: number;
  results: BulkImportResult[];
  error?: string;
}

/**
 * Bulk import resumes from a ZIP file.
 * Each resume will be parsed using AI and a candidate entity will be created.
 * @param file - ZIP file containing resume files (PDF, DOC, DOCX)
 * @returns Import results for each file
 */
export const bulkImportResumes = async (file: File): Promise<BulkImportResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post<BulkImportResponse>('/parser/resume/bulk-import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000 // 5 minutes for bulk AI parsing
  });
  return data;
};

/**
 * Response from creating entity from resume
 */
export interface CreateEntityFromResumeResponse {
  entity: {
    id: number;
    type: string;
    name: string;
    status: string;
    phone?: string;
    email?: string;
    telegram_usernames?: string[];
    emails?: string[];
    phones?: string[];
    company?: string;
    position?: string;
    tags?: string[];
    extra_data?: Record<string, unknown>;
    created_by?: number;
    department_id?: number;
    department_name?: string;
    created_at?: string;
    updated_at?: string;
    expected_salary_min?: number;
    expected_salary_max?: number;
    expected_salary_currency?: string;
  };
  parsed_data: ParsedResume;
  file_id?: number;
}

/**
 * Create a new candidate entity from uploaded resume file.
 * This will parse the resume and create an entity in one step.
 * @param file - Resume file (PDF, DOC, DOCX)
 * @returns Created entity ID and parsed data
 */
export const createEntityFromResume = async (
  file: File,
  onUploadProgress?: (pct: number) => void,
): Promise<CreateEntityFromResumeResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('auto_attach_file', 'true');
  const { data } = await api.post('/entities/from-resume', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000, // 3 мин — парсинг PDF + создание + AI-профиль
    onUploadProgress: onUploadProgress
      ? (e) => { if (e.total) onUploadProgress(Math.round((e.loaded / e.total) * 100)); }
      : undefined,
  });
  return data;
};

// ============================================================
// GLOBAL SEARCH (Command Palette)
// ============================================================

export interface GlobalSearchCandidate {
  id: number;
  name: string;
  email?: string;
  phone?: string;
  position?: string;
  company?: string;
  status: string;
  relevance_score: number;
}

export interface GlobalSearchVacancy {
  id: number;
  title: string;
  status: string;
  location?: string;
  department_name?: string;
  relevance_score: number;
}

export interface GlobalSearchResult {
  type: 'candidate' | 'vacancy';
  id: number;
  title: string;
  subtitle?: string;
  relevance_score: number;
}

export interface GlobalSearchResponse {
  candidates: GlobalSearchCandidate[];
  vacancies: GlobalSearchVacancy[];
  total: number;
}

/**
 * Global search for Command Palette.
 * Searches across candidates and vacancies.
 *
 * @param query - Search query string
 * @param limit - Maximum number of results per category (default: 5)
 * @returns Search results grouped by type
 */
export const globalSearch = async (
  query: string,
  limit: number = 5
): Promise<GlobalSearchResponse> => {
  const { data } = await deduplicatedGet<GlobalSearchResponse>('/search/global', {
    params: { query, limit: String(limit) }
  });
  return data;
};

// ============================================================
// AI PROFILES & SIMILARITY
// ============================================================

export interface AIProfile {
  skills: string[];
  experience_years: number | null;
  level: 'junior' | 'middle' | 'senior' | 'lead' | 'unknown';
  specialization: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  location: string | null;
  work_format: 'office' | 'remote' | 'hybrid' | 'unknown';
  languages: string[];
  education: string | null;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  red_flags: string[];
  communication_style: string;
  generated_at: string;
  context_sources?: {
    chats_count: number;
    calls_count: number;
    files_count: number;
  };
}

export interface ProfileResponse {
  entity_id: number;
  profile: AIProfile;
  generated_at: string | null;
}

export interface SimilarByProfileResponse {
  entity_id: number;
  entity_name: string;
  entity_position: string | null;
  entity_status: string;
  score: number;
  matches: string[];
  differences: string[];
  summary: string;
  profile_summary: string | null;
  profile_level: string | null;
  profile_specialization: string | null;
}

/**
 * Generate AI profile for entity.
 * Analyzes all context (files, chats, calls) to create structured profile.
 */
export const generateEntityProfile = async (entityId: number): Promise<ProfileResponse> => {
  const { data } = await api.post(`/entities/${entityId}/profile/generate`);
  return data;
};

/**
 * Get existing AI profile for entity.
 */
export const getEntityProfile = async (entityId: number): Promise<ProfileResponse> => {
  const { data } = await api.get(`/entities/${entityId}/profile`);
  return data;
};

/**
 * Find similar candidates using AI profile matching.
 */
export const getSimilarByProfile = async (
  entityId: number,
  minScore: number = 30,
  limit: number = 10
): Promise<SimilarByProfileResponse[]> => {
  const { data } = await api.get(`/entities/${entityId}/similar-profiles`, {
    params: { min_score: minScore, limit }
  });
  return data;
};

export interface BulkProfileResponse {
  total_candidates: number;
  profiles_generated: number;
  profiles_skipped: number;
  errors: number;
}

/**
 * Generate AI profiles for all candidates in the organization.
 */
export const generateAllProfiles = async (forceRegenerate = false): Promise<BulkProfileResponse> => {
  const { data } = await api.post('/entities/profiles/generate-all', null, {
    params: { force_regenerate: forceRegenerate }
  });
  return data;
};

// ============================================================
// BACKGROUND PARSING JOBS
// ============================================================

export type ParseJobStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface ParseJob {
  id: number;
  status: ParseJobStatus;
  file_name: string;
  progress: number;
  progress_stage?: string;
  entity_id?: number;
  entity_name?: string;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface ParseJobsListResponse {
  jobs: ParseJob[];
  total: number;
  pending_count: number;
  processing_count: number;
}

/**
 * Start a background parsing job for a resume file.
 * Returns immediately with job_id. Use getParseJob to check status.
 */
export const startParseJob = async (file: File): Promise<{ job_id: number; message: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post('/parse-jobs/start', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return data;
};

/**
 * Get list of parsing jobs for current user.
 */
export const getParseJobs = async (params?: {
  status?: ParseJobStatus;
  limit?: number;
  offset?: number;
}): Promise<ParseJobsListResponse> => {
  const { data } = await deduplicatedGet<ParseJobsListResponse>('/parse-jobs', { params });
  return data;
};

/**
 * Get status of a specific parsing job.
 */
export const getParseJob = async (jobId: number): Promise<ParseJob> => {
  const { data } = await deduplicatedGet<ParseJob>(`/parse-jobs/${jobId}`);
  return data;
};

/**
 * Cancel a pending parsing job.
 */
export const cancelParseJob = async (jobId: number): Promise<{ success: boolean; message: string }> => {
  const { data } = await api.delete(`/parse-jobs/${jobId}`);
  return data;
};

// ============================================================
// CANDIDATE SHARE LINK (публичный предпросмотр для заказчика)
// ============================================================

export interface CandidateShareLinkResult {
  token: string;
  url_path: string;
  expires_at: string;
}

export interface PublicPreviewFile {
  id: number;
  name: string;
  mime_type: string;
  size?: number | null;
  previewable: boolean;
  url: string;
}

export interface PublicCandidatePreview {
  name: string;
  position?: string | null;
  company?: string | null;
  phone?: string | null;
  email?: string | null;
  telegram?: string | null;
  city?: string | null;
  age?: string | null;
  total_experience?: string | null;
  source?: string | null;
  salary?: string | null;
  photo_url?: string | null;
  stage?: string | null;
  stage_label?: string | null;
  vacancy_title?: string | null;
  timeline: Array<{ author_name?: string | null; date?: string | null; title?: string | null; text?: string | null }>;
  resume_files: PublicPreviewFile[];
  files: PublicPreviewFile[];
  rating?: number | null;
  expires_at?: string | null;
}

/** Создать публичную ссылку предпросмотра кандидата (живёт 30 дней). */
export const createCandidateShareLink = async (entityId: number): Promise<CandidateShareLinkResult> => {
  const { data } = await api.post(`/entities/${entityId}/share-link`);
  return data;
};

/** Публичные данные кандидата по токену (без авторизации). */
export const getPublicCandidatePreview = async (token: string): Promise<PublicCandidatePreview> => {
  const { data } = await api.get(`/entities/public/candidate-preview/${encodeURIComponent(token)}`);
  return data;
};
