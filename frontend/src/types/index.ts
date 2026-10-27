import {
  HR_STAGES,
  STAGE_BADGE_CLASS,
  STAGE_BY_STATUS,
  STAGE_LABEL_BY_STAGE,
  STAGE_LABEL_BY_STATUS,
  STATUS_BY_STAGE,
  DEPARTED_LABELS,
} from '@/constants/hrStages';

export type UserRole = 'superadmin' | 'admin';
export type OrgRole = 'owner' | 'admin' | 'hr' | 'member';
export type DeptRole = 'lead' | 'sub_admin' | 'member';

export interface User {
  id: number;
  email: string;
  name: string;
  role: UserRole;
  org_role?: OrgRole;
  is_readonly?: boolean; // «Наблюдатель»: видит всё, но ничего не может менять
  // Скоуп по воронкам: если список непустой, человеку видны кандидаты только
  // этих вакансий (и сами вакансии тоже). Пусто — ограничения нет.
  scope_vacancy_ids?: number[];
  department_id?: number;
  department_name?: string;
  department_role?: DeptRole;
  department_names?: string[];
  telegram_id?: number;
  telegram_username?: string;
  // Additional contact identifiers for speaker matching
  additional_emails?: string[];
  additional_telegram_usernames?: string[];
  created_at: string;
  // Impersonation fields
  is_impersonating?: boolean;
  original_user_id?: number;
  original_user_name?: string;
  // Password reset flag
  must_change_password?: boolean;
}

export type ChatTypeId = 'work' | 'hr' | 'project' | 'client' | 'contractor' | 'sales' | 'support' | 'custom';

export interface ChatTypeInfo {
  id: ChatTypeId;
  name: string;
  description: string;
  icon: string;
  color: string;
}

export interface QuickAction {
  id: string;
  label: string;
  icon: string;
}

export interface ChatTypeConfig {
  type_info: ChatTypeInfo;
  quick_actions: QuickAction[];
  suggested_questions: string[];
  default_criteria: Criterion[];
}

export interface Chat {
  id: number;
  telegram_chat_id: number;
  title: string;
  custom_name?: string;
  chat_type: ChatTypeId;
  custom_type_name?: string;
  custom_type_description?: string;
  owner_id?: number;
  owner_name?: string;
  entity_id?: number;
  entity_name?: string;
  is_active: boolean;
  // Permission fields
  is_mine?: boolean;
  is_shared?: boolean;
  access_level?: 'view' | 'edit' | 'full' | null;
  messages_count: number;
  participants_count: number;
  last_activity?: string;
  created_at: string;
  has_criteria?: boolean;
  deleted_at?: string;
  days_until_permanent_delete?: number;
}

export interface DocumentMetadata {
  filename?: string;
  file_type?: string;
  file_size?: number;
  pages_count?: number;
  pages_parsed?: number;
  tables_count?: number;
  sheets?: string[];
  sheets_count?: number;
  slides_count?: number;
  extracted_files?: { name: string; status: string }[];
  ocr_method?: string;
  converted_from?: string;
  parsed_at?: string;
}

export interface Message {
  id: number;
  telegram_user_id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  content: string;
  content_type: string;
  file_id?: string;
  file_path?: string;  // Local file path for imported media
  file_name?: string;
  document_metadata?: DocumentMetadata;
  parse_status?: 'parsed' | 'partial' | 'failed' | 'skipped';
  parse_error?: string;
  timestamp: string;
}

export interface Participant {
  telegram_user_id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
  messages_count: number;
}

export interface Criterion {
  name: string;
  description: string;
  weight: number;
  category: 'basic' | 'red_flags' | 'green_flags' | 'potential';
}

export interface CriteriaPreset {
  id: number;
  name: string;
  description?: string;
  criteria: Criterion[];
  category: string;
  is_global: boolean;
  created_by?: number;
  created_at: string;
}

export interface ChatCriteria {
  id: number;
  chat_id: number;
  criteria: Criterion[];
  updated_at: string;
}

export interface EntityCriteria {
  id: number;
  entity_id: number;
  criteria: Criterion[];
  updated_at: string;
}

export interface AIMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface AIConversation {
  id: number;
  chat_id: number;
  messages: AIMessage[];
  created_at: string;
  updated_at: string;
}

export interface AnalysisResult {
  id: number;
  chat_id: number;
  result: string;
  report_type: string;
  created_at: string;
}

export interface Stats {
  total_chats: number;
  total_messages: number;
  total_participants: number;
  total_analyses: number;
  active_chats: number;
  messages_today: number;
  messages_this_week: number;
  activity_by_day: { date: string; day: string; count: number }[];
  messages_by_type: Record<string, number>;
  top_chats: { id: number; title: string; custom_name?: string | null; messages: number }[];
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// Session types for auth sessions management
export interface Session {
  id: string;
  user_agent: string;
  ip_address: string;
  created_at: string;
  last_activity: string;
  is_current: boolean;
}

export interface SessionsResponse {
  sessions: Session[];
}

export interface RefreshTokenResponse {
  success: boolean;
  message?: string;
}

// === Entity Types ===

export type EntityType = 'candidate' | 'client' | 'contractor' | 'lead' | 'partner' | 'custom';

export type EntityStatus =
  // HR Pipeline stages (must match backend EntityStatus enum)
  | 'new'             // Новый
  | 'screening'       // Скрининг
  | 'practice'        // Практика
  | 'tech_practice'   // Тех-практика
  | 'is_interview'    // ИС
  | 'offer'           // Оффер
  | 'hired'           // Принят
  | 'probation'       // Практика
  | 'transferred'     // Перешёл в отдел
  | 'rejected'        // Отклонён
  | 'reserve'         // Резерв
  | 'dismissed'       // Уволен (доска «Штат»)
  | 'quit'            // Уволился (доска «Штат»)
  // General statuses
  | 'active'
  | 'paused'
  | 'churned'
  | 'converted'
  | 'ended'
  | 'negotiation'
  | 'withdrawn'
  | 'interview'       // Legacy
  | 'applied'         // Legacy
  | 'phone_screen'    // Legacy
  | 'assessment';     // Legacy

export interface Entity {
  id: number;
  type: EntityType;
  name: string;
  status: EntityStatus;
  phone?: string;
  email?: string;
  telegram_user_id?: number;
  // Multiple identifiers support
  telegram_usernames?: string[];
  emails?: string[];
  phones?: string[];
  company?: string;
  position?: string;
  tags: string[];
  extra_data: Record<string, unknown>;
  created_by?: number;
  owner_id?: number;
  owner_name?: string;
  is_mine?: boolean;
  is_shared?: boolean;
  access_level?: 'view' | 'edit' | 'full';
  department_id?: number;
  department_name?: string;
  created_at: string;
  updated_at: string;
  chats_count?: number;
  calls_count?: number;
  // Expected salary for candidates
  expected_salary_min?: number;
  expected_salary_max?: number;
  expected_salary_currency?: string;
  // Vacancy tracking for candidates
  vacancies_count?: number;
  vacancy_names?: string[];
  /** Оптимистичная блокировка: PUT /entities сверяет присланную version с
   *  текущей и отдаёт 409, если карточку успел изменить кто-то ещё. */
  version?: number;
}

export interface EntityFile {
  id: number;
  entity_id: number;
  file_type: 'resume' | 'cover_letter' | 'test_assignment' | 'certificate' | 'portfolio' | 'other';
  file_name: string;
  file_path: string;
  file_size?: number;
  mime_type?: string;
  description?: string;
  created_at: string;
}

export interface EntityWithRelations extends Entity {
  chats: Array<{
    id: number;
    title: string;
    chat_type: ChatTypeId;
    created_at: string;
  }>;
  calls: Array<{
    id: number;
    source_type: CallSource;
    status: CallStatus;
    duration_seconds?: number;
    summary?: string;
    created_at: string;
  }>;
  transfers: EntityTransfer[];
  analyses: Array<{
    id: number;
    report_type?: string;
    result?: string;
    created_at: string;
  }>;
  files?: EntityFile[];
}

export interface EntityTransfer {
  id: number;
  entity_id: number;
  from_user_id?: number;
  to_user_id?: number;
  from_department?: string;
  to_department?: string;
  comment?: string;
  created_at: string;
  from_user_name?: string;
  to_user_name?: string;
}

// === Call Types ===

export type CallSource = 'meet' | 'zoom' | 'teams' | 'upload' | 'telegram' | 'google_doc' | 'google_drive' | 'direct_url';

export type ExternalLinkType = 'google_doc' | 'google_drive' | 'direct_media' | 'fireflies' | 'unknown';

export type CallStatus =
  | 'pending'
  | 'connecting'
  | 'recording'
  | 'processing'
  | 'transcribing'
  | 'analyzing'
  | 'done'
  | 'failed';

export interface CallRecording {
  id: number;
  title?: string;
  entity_id?: number;
  owner_id?: number;
  owner_name?: string;
  source_type: CallSource;
  source_url?: string;
  bot_name: string;
  status: CallStatus;
  // Permission fields
  is_mine?: boolean;
  is_shared?: boolean;
  access_level?: 'view' | 'edit' | 'full' | null;
  duration_seconds?: number;
  audio_file_path?: string;
  transcript?: string;
  speakers?: SpeakerSegment[];
  summary?: string;
  action_items?: string[];
  key_points?: string[];
  error_message?: string;
  created_at: string;
  started_at?: string;
  ended_at?: string;
  processed_at?: string;
  entity_name?: string;
}

export interface SpeakerSegment {
  speaker: string;
  start: number;
  end: number;
  text: string;
}

// === Report Types ===

export type ReportTypeId = 'daily_hr' | 'weekly_summary' | 'daily_calls' | 'weekly_pipeline';
export type DeliveryMethod = 'telegram' | 'email';

export interface ReportSubscription {
  id: number;
  user_id: number;
  report_type: ReportTypeId;
  delivery_method: DeliveryMethod;
  delivery_time: string;
  filters: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

// === Entity Type Configurations ===

export interface EntityTypeInfo {
  id: EntityType;
  name: string;
  namePlural: string;
  description: string;
  icon: string;
  color: string;
  statuses: EntityStatus[];
}

export const ENTITY_TYPES: Record<EntityType, EntityTypeInfo> = {
  candidate: {
    id: 'candidate',
    name: 'Кандидат',
    namePlural: 'Кандидаты',
    description: 'Соискатели на вакансии',
    icon: 'UserCheck',
    color: 'blue',
    statuses: ['new', 'screening', 'practice', 'tech_practice', 'is_interview', 'offer', 'hired', 'rejected']
  },
  client: {
    id: 'client',
    name: 'Клиент',
    namePlural: 'Клиенты',
    description: 'Заказчики и компании-клиенты',
    icon: 'Building',
    color: 'green',
    statuses: ['new', 'active', 'paused', 'churned']
  },
  contractor: {
    id: 'contractor',
    name: 'Подрядчик',
    namePlural: 'Подрядчики',
    description: 'Внешние подрядчики и фрилансеры',
    icon: 'Wrench',
    color: 'orange',
    statuses: ['new', 'active', 'paused', 'ended']
  },
  lead: {
    id: 'lead',
    name: 'Лид',
    namePlural: 'Лиды',
    description: 'Потенциальные клиенты',
    icon: 'Target',
    color: 'purple',
    statuses: ['new', 'negotiation', 'converted', 'rejected']
  },
  partner: {
    id: 'partner',
    name: 'Партнёр',
    namePlural: 'Партнёры',
    description: 'Бизнес-партнёры',
    icon: 'Users',
    color: 'cyan',
    statuses: ['new', 'active', 'paused', 'ended']
  },
  custom: {
    id: 'custom',
    name: 'Другое',
    namePlural: 'Другие',
    description: 'Другой тип контакта',
    icon: 'User',
    color: 'gray',
    statuses: ['new', 'active', 'paused', 'ended']
  }
};

/** Служебная колонка доски «Все кандидаты»: статусы вне воронки (уволен,
 *  уволился, легаси). Не статус сущности — поэтому вне EntityStatus. */
export const BOARD_OTHER_STATUS = 'other';

export const STATUS_LABELS = {
  // Этапы HR — из общего справочника (constants/hrStages.ts).
  ...STAGE_LABEL_BY_STATUS,
  ...DEPARTED_LABELS,
  // General/Legacy statuses
  active: 'Активный',
  paused: 'На паузе',
  churned: 'Ушёл',
  converted: 'Сконвертирован',
  ended: 'Завершён',
  negotiation: 'Переговоры',
  // Легаси: статусы, записанные значением этапа заявки.
  interview: STAGE_LABEL_BY_STAGE.interview,
  applied: STAGE_LABEL_BY_STAGE.applied,
  phone_screen: STAGE_LABEL_BY_STAGE.phone_screen,
  assessment: STAGE_LABEL_BY_STAGE.assessment,
} as Record<EntityStatus, string>;

export const STATUS_COLORS: Record<EntityStatus, string> = {
  // HR Pipeline
  new: 'bg-[var(--hf-status-blue-badge)] text-[var(--hf-status-blue)] border-[color:var(--hf-accent-border-30)]',
  screening: 'bg-[var(--hf-status-cyan-badge)] text-[var(--hf-status-cyan)] border-[color:var(--hf-status-cyan-badge)]',
  practice: 'bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)] border-[color:var(--hf-status-yellow-badge)]',
  tech_practice: 'bg-[var(--hf-status-orange-badge)] text-[var(--hf-status-orange)] border-[color:var(--hf-status-orange-badge)]',
  is_interview: 'bg-[var(--hf-status-purple-badge)] text-[var(--hf-status-purple)] border-[color:var(--hf-status-purple-badge)]',
  offer: 'bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)] border-[color:var(--hf-status-green-badge)]',
  hired: 'bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)] border-[color:var(--hf-status-green-badge)]',
  probation: 'bg-[var(--hf-status-teal-badge)] text-[var(--hf-status-teal)] border-[color:var(--hf-status-teal-badge)]',
  transferred: 'bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)] border-[color:var(--hf-status-green-badge)]',
  rejected: 'bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)] border-[color:var(--hf-status-red-badge)]',
  withdrawn: 'bg-[var(--hf-status-gray-badge)] text-[var(--hf-status-gray)] border-[color:var(--hf-status-gray-badge)]',
  reserve: 'bg-[var(--hf-status-gray-badge)] text-[var(--hf-status-gray)] border-[color:var(--hf-status-gray-badge)]',
  dismissed: 'bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)] border-[color:var(--hf-status-red-badge)]',
  quit: 'bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)] border-[color:var(--hf-status-red-badge)]',
  // General/Legacy
  active: 'bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)]',
  paused: 'bg-[var(--hf-status-gray-badge)] text-[var(--hf-status-gray)]',
  churned: 'bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)]',
  converted: 'bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)]',
  ended: 'bg-[var(--hf-status-gray-badge)] text-[var(--hf-status-gray)]',
  negotiation: 'bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)]',
  interview: 'bg-[var(--hf-status-orange-badge)] text-[var(--hf-status-orange)]',
  applied: 'bg-[var(--hf-status-blue-badge)] text-[var(--hf-status-blue)] border-[color:var(--hf-accent-border-30)]',
  phone_screen: 'bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)] border-[color:var(--hf-status-yellow-badge)]',
  assessment: 'bg-[var(--hf-status-purple-badge)] text-[var(--hf-status-purple)] border-[color:var(--hf-status-purple-badge)]'
};

export const CALL_STATUS_LABELS: Record<CallStatus, string> = {
  pending: 'Ожидание',
  connecting: 'Подключение',
  recording: 'Запись',
  processing: 'Обработка',
  transcribing: 'Транскрибация',
  analyzing: 'Анализ',
  done: 'Готово',
  failed: 'Ошибка'
};

export const CALL_STATUS_COLORS: Record<CallStatus, string> = {
  pending: 'bg-[var(--hf-status-gray-badge)] text-[var(--hf-status-gray)]',
  connecting: 'bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)]',
  recording: 'bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)]',
  processing: 'bg-[var(--hf-status-blue-badge)] text-[var(--hf-status-blue)]',
  transcribing: 'bg-[var(--hf-status-purple-badge)] text-[var(--hf-status-purple)]',
  analyzing: 'bg-[var(--hf-status-cyan-badge)] text-[var(--hf-status-cyan)]',
  done: 'bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)]',
  failed: 'bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)]'
};

// === Vacancy Types ===

export type VacancyStatus = 'draft' | 'pending_review' | 'open' | 'paused' | 'closed' | 'cancelled';

export type ApplicationStage =
  // Main pipeline stages (using existing PostgreSQL enum values)
  | 'applied'       // Новый (displayed as "Новый" in UI)
  | 'screening'     // Скрининг
  | 'phone_screen'  // Практика (displayed as "Практика" in UI)
  | 'interview'     // Тех-практика (displayed as "Тех-практика" in UI)
  | 'assessment'    // ИС (displayed as "ИС" in UI)
  | 'offer'         // Оффер
  | 'hired'         // Принят
  | 'probation'     // Практика
  | 'transferred'   // Перешёл в отдел
  | 'rejected'      // Отказ
  | 'withdrawn'     // Отозван
  | 'reserve';      // Резерв

// Main pipeline stages in order (using existing PostgreSQL enum values)
export const PIPELINE_STAGES: ApplicationStage[] = [
  'applied', 'screening', 'phone_screen', 'interview', 'assessment', 'offer', 'hired', 'rejected'
];

// Entity pipeline stages for candidate database kanban (using EntityStatus values)
export const ENTITY_PIPELINE_STAGES: EntityStatus[] = [
  'new', 'screening', 'practice', 'tech_practice', 'is_interview', 'offer', 'hired', 'rejected'
];

export interface Vacancy {
  id: number;
  title: string;
  description?: string;
  requirements?: string;
  responsibilities?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency: string;
  location?: string;
  employment_type?: string;
  experience_level?: string;
  status: VacancyStatus;
  priority: number;
  tags: string[];
  extra_data: Record<string, unknown>;
  visible_to_all: boolean;
  department_id?: number;
  department_name?: string;
  hiring_manager_id?: number;
  hiring_manager_name?: string;
  created_by?: number;
  created_by_name?: string;
  published_at?: string;
  closes_at?: string;
  reopened_at?: string;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  applications_count: number;
  stage_counts: Record<string, number>;
  source_url?: string;
  // Funnel customization
  custom_stages?: {
    columns: Array<{ key: string; label: string; visible: boolean; maps_to?: string }>;
  } | null;
  kanban_card_fields?: string[] | null;
  // Assignment
  assigned_to?: number[];
  assigned_to_all?: boolean;
}

export interface VacancyApplication {
  id: number;
  vacancy_id: number;
  vacancy_title?: string;
  entity_id: number;
  entity_name?: string;
  entity_type?: EntityType;
  entity_email?: string;
  entity_phone?: string;
  entity_telegram?: string;
  entity_telegrams?: string[] | null;
  entity_notes_text?: string | null;
  entity_position?: string;
  entity_company?: string;
  entity_photo?: string | null;
  // Яркие теги у ФИО — свой справочник, отдельный от меток (с 21.09.2026).
  // text оставлен для старых данных из extra_data, пока прод не устаканится.
  entity_headline_tags?: { name?: string; text?: string; color: string }[] | null;
  // «Был отказ» в другой воронке / карточке-дубле / архиве (22.10.2026).
  prior_rejection?: import('@/components/candidates/priorRejection').PriorRejection | null;
  stage: ApplicationStage;
  stage_order: number;
  rating?: number;
  notes?: string;
  rejection_reason?: string;
  source?: string;
  next_interview_at?: string;
  compatibility_score?: CompatibilityScore;
  applied_at: string;
  last_stage_change_at: string;
  updated_at: string;
  // «В предыдущих сериях»: отклик старше последнего переоткрытия вакансии.
  is_previous_series?: boolean;
  /** Только ответ «Забрать»: что произошло и у кого забрали. */
  take_outcome?: 'added' | 'transferred' | 'unchanged' | null;
  taken_from?: number | null;
  // Рекрутёр-владелец заявки (кто добавил) — для авто-метки HR.
  created_by?: number | null;
  // Общий статус кандидата ПОСЛЕ смены этапа (считает сервер по «актуальной»
  // заявке). Приходит только из PUT /vacancies/applications/{id}; по нему
  // «Все кандидаты» ставят карточку в колонку, а не по выбранному этапу.
  entity_status?: string | null;
}

// === AI Compatibility Scoring ===

export type ScoringRecommendation = 'hire' | 'maybe' | 'reject';

export interface CompatibilityScore {
  overall_score: number;       // 0-100 overall compatibility
  skills_match: number;        // 0-100 skills alignment
  experience_match: number;    // 0-100 experience fit
  salary_match: number;        // 0-100 salary expectations alignment
  culture_fit: number;         // 0-100 culture compatibility
  strengths: string[];         // Candidate strengths for this role
  weaknesses: string[];        // Potential risks/concerns
  recommendation: ScoringRecommendation;  // hire/maybe/reject
  summary: string;             // Brief assessment text
  key_factors: string[];       // Key decision factors
}

export interface CalculateScoreRequest {
  entity_id: number;
  vacancy_id: number;
}

export interface CalculateScoreResponse {
  entity_id: number;
  vacancy_id: number;
  score: CompatibilityScore;
  cached: boolean;
}

export interface EntityScoreResult {
  entity_id: number;
  entity_name: string;
  score: CompatibilityScore;
}

export interface VacancyScoreResult {
  vacancy_id: number;
  vacancy_title: string;
  score: CompatibilityScore;
}

export interface BestMatchesRequest {
  limit?: number;
  min_score?: number;
  status_filter?: string[];
}

export interface BestMatchesResponse {
  vacancy_id: number;
  vacancy_title: string;
  matches: EntityScoreResult[];
  total_evaluated: number;
}

export interface MatchingVacanciesRequest {
  limit?: number;
  min_score?: number;
}

export interface MatchingVacanciesResponse {
  entity_id: number;
  entity_name: string;
  matches: VacancyScoreResult[];
  total_evaluated: number;
}

export interface KanbanColumn {
  stage: ApplicationStage;
  title: string;
  applications: VacancyApplication[];
  count: number;
}

export interface KanbanBoard {
  vacancy_id: number;
  vacancy_title: string;
  columns: KanbanColumn[];
  total_count: number;
}


export const VACANCY_STATUS_LABELS: Record<VacancyStatus, string> = {
  draft: 'Черновик',
  pending_review: 'На рассмотрении',
  open: 'Открыта',
  paused: 'На паузе',
  closed: 'Закрыта',
  cancelled: 'Отменена'
};

export const VACANCY_STATUS_COLORS: Record<VacancyStatus, string> = {
  draft: 'bg-[var(--hf-status-gray-badge)] text-[var(--hf-status-gray)]',
  pending_review: 'bg-[var(--hf-status-purple-badge)] text-[var(--hf-status-purple)]',
  open: 'bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)]',
  paused: 'bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)]',
  closed: 'bg-[var(--hf-status-blue-badge)] text-[var(--hf-status-blue)]',
  cancelled: 'bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)]'
};

// Подписи и цвета этапов заявки — из общего справочника (constants/hrStages.ts).
export const APPLICATION_STAGE_LABELS: Record<ApplicationStage, string> = STAGE_LABEL_BY_STAGE;

export const APPLICATION_STAGE_COLORS = Object.fromEntries(
  HR_STAGES.map((st) => [st.stage, STAGE_BADGE_CLASS[st.color]]),
) as Record<ApplicationStage, string>;

// Map EntityStatus to ApplicationStage for synchronization logic
export const STATUS_TO_STAGE_MAP: Partial<Record<EntityStatus, ApplicationStage>> = {
  ...STAGE_BY_STATUS,
  // Legacy aliases
  applied: 'applied',
  phone_screen: 'phone_screen',
  interview: 'interview',
  assessment: 'assessment'
};

export const STAGE_TO_STATUS_MAP: Record<ApplicationStage, EntityStatus> = STATUS_BY_STAGE;

export const EMPLOYMENT_TYPES = [
  { value: 'full-time', label: 'Полная занятость' },
  { value: 'part-time', label: 'Частичная занятость' },
  { value: 'contract', label: 'Контракт' },
  { value: 'remote', label: 'Удалённая работа' },
  { value: 'hybrid', label: 'Гибрид' }
];

export const EXPERIENCE_LEVELS = [
  { value: 'intern', label: 'Стажёр' },
  { value: 'junior', label: 'Junior' },
  { value: 'middle', label: 'Middle' },
  { value: 'senior', label: 'Senior' },
  { value: 'lead', label: 'Lead' },
  { value: 'manager', label: 'Manager' }
];

// === Multi-currency Support ===

export const CURRENCIES = [
  { code: 'RUB', symbol: '₽', name: 'Российский рубль' },
  { code: 'USD', symbol: '$', name: 'Доллар США' },
  { code: 'EUR', symbol: '€', name: 'Евро' },
  { code: 'KZT', symbol: '₸', name: 'Казахстанский тенге' },
  { code: 'UAH', symbol: '₴', name: 'Украинская гривна' },
  { code: 'BYN', symbol: 'Br', name: 'Белорусский рубль' },
  { code: 'GEL', symbol: '₾', name: 'Грузинский лари' },
  { code: 'AED', symbol: 'د.إ', name: 'Дирхам ОАЭ' },
  { code: 'TRY', symbol: '₺', name: 'Турецкая лира' },
  { code: 'GBP', symbol: '£', name: 'Фунт стерлингов' },
] as const;

export type CurrencyCode = typeof CURRENCIES[number]['code'];

// === Vacancy Recommendations ===

export interface VacancyRecommendation {
  vacancy_id: number;
  vacancy_title: string;
  match_score: number;
  match_reasons: string[];
  missing_requirements: string[];
  salary_compatible: boolean;
  location_match: boolean;
  salary_min?: number;
  salary_max?: number;
  salary_currency: string;
  location?: string;
  employment_type?: string;
  experience_level?: string;
  department_name?: string;
  applications_count: number;
}


