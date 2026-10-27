import { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// INTERNS API (Prometheus proxy)
// ============================================================

/** Trail summary from Prometheus */
export interface PrometheusTrailSummary {
  trailId: string;
  trailName: string;
  completedModules: number;
  totalModules: number;
  earnedXP: number;
}

/** Intern DTO from Prometheus */
export interface PrometheusIntern {
  id: string;
  name: string;
  email: string | null;
  telegramUsername: string | null;
  totalXP: number;
  currentStreak: number;
  lastActiveAt: string | null;
  daysSinceActive: number | null;
  trails: PrometheusTrailSummary[];
  createdAt: string;
}

/** Response from /api/interns (backend proxy to Prometheus) */
export interface PrometheusInternsResponse {
  interns: PrometheusIntern[];
}

/**
 * Normalize raw trail object from Prometheus API.
 *
 * Prometheus uses inconsistent field names across endpoints:
 *   - student-achievements → trailTitle
 *   - analytics            → title / trailTitle
 *   - interns list          → trailTitle (not trailName)
 *
 * This normalizer maps whatever Prometheus returns to our
 * PrometheusTrailSummary shape so the UI always gets the right data.
 */
function normalizeTrail(raw: Record<string, unknown>): PrometheusTrailSummary {
  return {
    trailId: (raw.trailId ?? raw.id ?? '') as string,
    trailName: ((raw.trailName as string) || (raw.trailTitle as string) || (raw.title as string) || ''),
    completedModules: ((raw.completedModules as number) ?? (raw.modulesCompleted as number) ?? 0),
    totalModules: ((raw.totalModules as number) ?? 0),
    earnedXP: ((raw.earnedXP as number) ?? (raw.xp as number) ?? 0),
  };
}

/**
 * Fetch interns data from backend proxy (which fetches from Prometheus).
 * The API key stays server-side — the frontend never touches it.
 */
export const getPrometheusInterns = async (): Promise<PrometheusIntern[]> => {
  const { data } = await deduplicatedGet<PrometheusInternsResponse>('/interns');
  return (data.interns ?? []).map(intern => ({
    ...intern,
    trails: (intern.trails ?? []).map(t => normalizeTrail(t as unknown as Record<string, unknown>)),
  }));
};

// ============================================================
// ANALYTICS API (Prometheus proxy)
// ============================================================

export interface ChurnRiskStudent {
  id: string;
  name: string;
  email: string;
  telegramUsername: string | null;
  lastActive: string;
  daysSinceActive: number;
  modulesCompleted: number;
  xp: number;
}

export interface ChurnRisk {
  high: ChurnRiskStudent[];
  highCount: number;
  medium: ChurnRiskStudent[];
  mediumCount: number;
  low: ChurnRiskStudent[];
  lowCount: number;
}

export interface FunnelStage {
  stage: string;
  count: number;
  percent: number;
}

export interface TrendPoint {
  date: string;
  activeUsers: number;
  totalActions: number;
}

export interface ModuleDifficulty {
  id: string;
  title: string;
  slug: string;
  type: 'THEORY' | 'PRACTICE' | 'PROJECT';
  trailId: string;
  trailTitle: string;
  trailSlug: string;
  completedCount: number;
  submissionCount: number;
  avgScore: number | null;
  difficulty: 'hard' | 'medium' | 'easy' | 'unknown';
}

export interface AnalyticsSummary {
  totalStudents: number;
  atRiskStudents: number;
  conversionRate: number;
  avgDailyActiveUsers: number;
}

export interface TrailProgressItem {
  id: string;
  title: string;
  slug: string;
  enrollments: number;
  certificates: number;
  totalModules: number;
  completedModules: number;
  submissionsCount: number;
  approvedSubmissions: number;
  completionRate: number;
  approvalRate: number;
}

export interface AnalyticsTopStudent {
  id: string;
  name: string;
  totalXP: number;
  modulesCompleted: number;
  approvedWorks: number;
  certificates: number;
}

export interface ScoreDistribution {
  excellent: number;
  good: number;
  average: number;
  poor: number;
  total: number;
  avgScore: number;
  filteredByTrail: boolean;
}

export interface DropoffModule {
  id: string;
  title: string;
  slug: string;
  order: number;
  type: 'THEORY' | 'PRACTICE' | 'PROJECT';
  totalEnrolled: number;
  startedCount: number;
  inProgressCount: number;
  completedCount: number;
  completionRate: number;
  dropRate: number;
  avgTimeDays: number;
  isBottleneck: boolean;
}

export interface DropoffTrail {
  trailId: string;
  trailTitle: string;
  trailSlug: string;
  totalEnrolled: number;
  modules: DropoffModule[];
}

export interface StudentModuleStatus {
  id: string;
  title: string;
  order: number;
  type: 'THEORY' | 'PRACTICE' | 'PROJECT';
  status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  submissionId: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  updatedAt?: string | null;
}

export interface StudentByTrail {
  id: string;
  name: string;
  telegramUsername: string | null;
  totalXP: number;
  modulesCompleted: number;
  totalModules: number;
  completionPercent: number;
  submissions: {
    approved: number;
    pending: number;
    revision: number;
    total: number;
  };
  avgScore: number | null;
  dateStart: string;
  dateEnd: string | null;
  modules: StudentModuleStatus[];
  trailStatus: 'LEARNING' | 'GRADUATED' | 'DROPPED';
}

export interface StudentsByTrailItem {
  trailId: string;
  trailTitle: string;
  trailSlug: string;
  students: StudentByTrail[];
}

export interface AnalyticsTrailFilter {
  id: string;
  title: string;
  slug: string;
}

export interface AnalyticsFilters {
  trails: AnalyticsTrailFilter[];
  currentTrail: string;
  currentPeriod: string;
}

export interface PrometheusAnalyticsResponse {
  churnRisk: ChurnRisk;
  funnel: FunnelStage[];
  trends: TrendPoint[];
  difficultyAnalysis: ModuleDifficulty[];
  summary: AnalyticsSummary;
  trailProgress: TrailProgressItem[];
  topStudents: AnalyticsTopStudent[];
  scoreDistribution: ScoreDistribution;
  dropoffAnalysis: DropoffTrail[];
  studentsByTrail: StudentsByTrailItem[];
  filters: AnalyticsFilters;
}

/**
 * Fetch platform analytics from Prometheus via backend proxy.
 */
export const getPrometheusAnalytics = async (
  trail: string = 'all',
  period: string = '30',
): Promise<PrometheusAnalyticsResponse> => {
  const { data } = await deduplicatedGet<PrometheusAnalyticsResponse>(
    '/interns/analytics',
    { params: { trail, period } },
  );
  return data;
};

// ============================================================
// STUDENT ACHIEVEMENTS API (Prometheus proxy)
// ============================================================

export interface StudentInfo {
  id: string;
  name: string;
  email: string;
  role: 'STUDENT' | 'TEACHER' | 'HR' | 'CO_ADMIN' | 'ADMIN';
  totalXP: number;
  currentStreak: number;
  registeredAt: string;
  lastActiveAt: string;
  daysSinceActive: number;
  leaderboardRank: number;
  modulesCompleted: number;
}

export interface Achievement {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  rarity: 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary';
  earned: boolean;
  earnedAt: string | null;
}

export interface AchievementsData {
  stats: {
    earned: number;
    total: number;
    percentage: number;
  };
  earned: Achievement[];
  all: Achievement[];
}

export interface SubmissionStats {
  approved: number;
  pending: number;
  revision: number;
  failed: number;
  total: number;
}

export interface StudentTrailProgress {
  trailId: string;
  trailTitle: string;
  trailSlug: string;
  enrolledAt: string;
  completedAt?: string | null;
  totalModules: number;
  completedModules: number;
  completionPercent: number;
}

export interface Certificate {
  id: string;
  code: string;
  issuedAt: string;
  totalXP: number;
  level: 'Junior' | 'Middle' | 'Senior';
  trail: {
    id: string;
    title: string;
    slug: string;
    color: string;
  };
}

export interface StudentAchievementsResponse {
  student: StudentInfo;
  achievements: AchievementsData;
  submissionStats: SubmissionStats;
  trailProgress: StudentTrailProgress[];
  certificates: Certificate[];
}

/**
 * Fetch achievements for a specific student from Prometheus via backend proxy.
 */
export const getStudentAchievements = async (
  studentId: string,
): Promise<StudentAchievementsResponse> => {
  const { data } = await deduplicatedGet<StudentAchievementsResponse>(
    `/interns/student-achievements/${studentId}`,
  );
  return data;
};

// ============================================================
// CONTACT ↔ PROMETHEUS REVIEW API
// ============================================================

/** Trail view returned in the contact review */
export interface ContactReviewTrail {
  trailId: string;
  trailName: string;
  completedModules: number;
  totalModules: number;
  completionPercent: number;
  earnedXP: number;
  avgScore: number | null;
  submissions: {
    approved: number;
    pending: number;
    revision: number;
    total: number;
  } | null;
}

/** Review generated server-side from Prometheus data */
export interface ContactPrometheusReview {
  headline: string;
  bullets: string[];
  summary: string;
  metrics: {
    totalXP: number;
    daysSinceActive: number | null;
    lastActiveAt: string | null;
    totalModules: number;
    completedModules: number;
    overallCompletionPercent: number;
    trailCount: number;
  };
  trails: ContactReviewTrail[];
  flags: {
    active: boolean;
    risk: boolean;
    riskReason: string | null;
    topTrails: string[];
  };
}

/** Intern DTO returned in contact review response */
export interface ContactPrometheusIntern {
  id: string;
  name: string;
  email: string | null;
  telegramUsername: string | null;
  totalXP: number;
  lastActiveAt: string | null;
  daysSinceActive: number | null;
  createdAt: string | null;
}

/** Response from GET /api/interns/contact/{entity_id} */
export interface ContactPrometheusResponse {
  status: 'ok' | 'not_found' | 'not_linked' | 'error';
  intern?: ContactPrometheusIntern;
  review?: ContactPrometheusReview;
  message?: string;
}

/**
 * Fetch Prometheus review for a contact (entity).
 * The backend matches contact email to a Prometheus intern,
 * then generates a deterministic HR review.
 */
export const getContactPrometheusReview = async (
  entityId: number,
): Promise<ContactPrometheusResponse> => {
  const { data } = await deduplicatedGet<ContactPrometheusResponse>(
    `/interns/contact/${entityId}`,
  );
  return data;
};

// ============================================================
// DETAILED AI REVIEW FOR CONTACT
// ============================================================

/** Competency score block */
export interface CompetencyScore {
  score: number;
  label: string;
  detail: string;
}

/** Professional profile section of the detailed review */
export interface ProfessionalProfile {
  title: string;
  summary: string;
  keyStrengths: string[];
  growthAreas: string[];
}

/** Competency analysis section */
export interface CompetencyAnalysis {
  technicalReadiness: CompetencyScore;
  learningAbility: CompetencyScore;
  consistency: CompetencyScore;
  engagement: CompetencyScore;
}

/** Trail insight from AI analysis */
export interface TrailInsight {
  trailName: string;
  verdict: string;
  relevantSkills: string[];
}

/** Team fit recommendation */
export interface TeamFitRecommendation {
  readinessLevel: 'not_ready' | 'developing' | 'ready' | 'highly_ready';
  recommendedRoles: string[];
  integrationAdvice: string;
  watchPoints: string[];
}

/** Full AI-generated detailed review */
export interface DetailedPrometheusReview {
  professionalProfile: ProfessionalProfile;
  competencyAnalysis: CompetencyAnalysis;
  trailInsights: TrailInsight[];
  teamFitRecommendation: TeamFitRecommendation;
  overallVerdict: string;
}

/** Response from GET /api/interns/contact/{entity_id}/detailed-review */
export interface DetailedReviewResponse {
  status: 'ok' | 'not_found' | 'not_linked' | 'error';
  intern?: ContactPrometheusIntern;
  review?: ContactPrometheusReview;
  detailedReview?: DetailedPrometheusReview;
  achievements?: StudentAchievementsResponse;
  message?: string;
}

/**
 * Fetch detailed AI-powered Prometheus review for a contact.
 * Combines intern data + student achievements + Claude AI analysis.
 *
 * Results are cached in the database. Pass force=true to regenerate.
 */
export const getContactDetailedReview = async (
  entityId: number,
  force: boolean = false,
): Promise<DetailedReviewResponse> => {
  const { data } = await deduplicatedGet<DetailedReviewResponse>(
    `/interns/contact/${entityId}/detailed-review`,
    { params: force ? { force: 'true' } : undefined },
  );
  return data;
};

// ============================================================
// EXPORT INTERN TO CONTACT
// ============================================================

/** Response from POST /api/interns/export-to-contact/{internId} */
export interface ExportInternResponse {
  ok: boolean;
  contact_id?: number;
  created?: boolean;
  error?: string;
}

/**
 * Export a Prometheus intern to HR Contacts (Entity).
 * Idempotent: won't create duplicates if the contact already exists.
 */
export const exportInternToContact = async (
  internId: string,
): Promise<ExportInternResponse> => {
  const { data } = await debouncedMutation<ExportInternResponse>(
    'post',
    `/interns/export-to-contact/${internId}`,
  );
  return data;
};

/** Response from GET /api/interns/linked-contacts */
export interface LinkedContactsResponse {
  links: Record<string, number>; // prometheus_intern_id -> entity_id
}

/**
 * Get mapping of prometheus intern IDs to entity (contact) IDs.
 * Used to show which interns are already exported.
 */
export const getInternLinkedContacts = async (): Promise<LinkedContactsResponse> => {
  const { data } = await deduplicatedGet<LinkedContactsResponse>(
    '/interns/linked-contacts',
  );
  return data;
};

// ============================================================
// PROMETHEUS STATUS SYNC
// ============================================================

/** Single result from the sync endpoint */
export interface SyncStatusResult {
  email: string;
  found: boolean;
  statusCode?: string;
  statusLabel?: string;
  statusUpdatedAt?: string;
  hrStatus?: string;
  changed?: boolean;
  contactId?: number | null;
  error?: string;
}

/** Response from POST /api/interns/sync-prometheus-statuses */
export interface SyncStatusesResponse {
  ok: boolean;
  syncedAt: string;
  results: SyncStatusResult[];
  errors?: Array<{
    type: string;
    message: string;
    email?: string;
    statusCode?: number;
  }>;
}

/** Response from POST /api/interns/sync-prometheus-status-single */
export interface SyncSingleStatusResponse {
  ok: boolean;
  syncedAt: string;
  found: boolean;
  email?: string;
  internId?: string;
  name?: string;
  statusCode?: string;
  statusLabel?: string;
  statusUpdatedAt?: string;
  hrStatus?: string;
  changed?: boolean;
  contactId?: number | null;
  error?: string;
}

/**
 * Sync Prometheus statuses for a list of interns (bulk).
 * Calls POST /api/interns/sync-prometheus-statuses
 */
export const syncPrometheusStatuses = async (
  emails?: string[],
): Promise<SyncStatusesResponse> => {
  const { data } = await debouncedMutation<SyncStatusesResponse>(
    'post',
    '/interns/sync-prometheus-statuses',
    emails && emails.length > 0 ? { emails } : undefined,
  );
  return data;
};

/**
 * Sync a single intern's status from Prometheus.
 * Calls POST /api/interns/sync-prometheus-status-single?email=...&internId=...
 */
export const syncPrometheusStatusSingle = async (
  params: { email?: string; internId?: string },
): Promise<SyncSingleStatusResponse> => {
  const queryParams = new URLSearchParams();
  if (params.email) queryParams.set('email', params.email);
  if (params.internId) queryParams.set('internId', params.internId);
  const { data } = await debouncedMutation<SyncSingleStatusResponse>(
    'post',
    `/interns/sync-prometheus-status-single?${queryParams.toString()}`,
  );
  return data;
};
