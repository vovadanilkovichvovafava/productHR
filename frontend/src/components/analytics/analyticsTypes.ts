// Ответы отчётов «Аналитики» (/analytics/reports/*) — вынесено из DashboardPage, 20.10.2026.

export interface TimeToFillSummary {
  avg_days_to_close: number | null;
  avg_delay_days: number | null;
  closed_positions: number;
  total_positions: number;
}

export interface StageTimingItem {
  stage: string;
  label: string;
  avg_days: number;
}

export interface LastClosing {
  candidate_name: string;
  vacancy_title: string;
  recruiter_name: string | null;
  closed_date: string | null;
  days_to_close: number | null;
  start_date: string | null;
}

export interface TimeToFillReport {
  summary: TimeToFillSummary;
  stage_timings: StageTimingItem[];
  last_closings: LastClosing[];
}

export interface FunnelStageData {
  stage: string;
  label: string;
  candidate_count: number;
  rejection_count: number;
}

export interface SourceBreakdown {
  source: string;
  count: number;
}

export interface RejectionReasonItem {
  reason: string;
  count: number;
}

export interface FunnelReport {
  stages: FunnelStageData[];
  total_candidates: number;
  total_rejections: number;
  sources: SourceBreakdown[];
  rejection_reasons: RejectionReasonItem[];
}

export interface RecruiterFunnelItem {
  recruiter_id: number;
  recruiter_name: string;
  stages: FunnelStageData[];
  total_candidates: number;
  total_rejections: number;
}

export interface FunnelByRecruiterReport {
  summary: FunnelReport;
  by_recruiter: RecruiterFunnelItem[];
}

export interface SourcerStat {
  tag_id: number;
  name: string;
  color: string;
  /** Метку убрали из списка выбора — из отчёта она не пропадает. */
  archived: boolean;
  brought: number;
  in_work: number;
  reached_offer: number;
  hired: number;
  rejected: number;
  conversion: number;
}

export interface SourcersReport {
  items: SourcerStat[];
  total_brought: number;
  total_hired: number;
}

export interface RejectionsByStage {
  stage: string;
  label: string;
  count: number;
  reasons: RejectionReasonItem[];
}

export interface RejectionsReport {
  total_rejections: number;
  by_stage: RejectionsByStage[];
  top_reasons: RejectionReasonItem[];
}

export interface SourceReport {
  total_candidates: number;
  sources: SourceBreakdown[];
  by_stage: Record<string, SourceBreakdown[]>;
}

export interface StageMovementItem {
  from_stage: string;
  from_label: string;
  to_stage: string;
  to_label: string;
  count: number;
}

export interface MovementReport {
  total_movements: number;
  movements: StageMovementItem[];
}

export interface DepartmentSummary {
  id: number;
  name: string;
  vacancies: number;
  open_vacancies: number;
  applications: number;
  hires: number;
}

/** Какой отчёт → какие данные. Ключи — id отчётов из REPORT_CATEGORIES. */
export interface ReportDataMap {
  ttf: TimeToFillReport;
  funnel: FunnelReport;
  'funnel-recruiter': FunnelByRecruiterReport;
  sourcers: SourcersReport;
  rejections: RejectionsReport;
  sources: SourceReport;
  movement: MovementReport;
}

export type ReportId = keyof ReportDataMap;
