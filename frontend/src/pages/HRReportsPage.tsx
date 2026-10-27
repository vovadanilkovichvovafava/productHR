import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  BarChart3, Clock, Users, Filter, ChevronDown, Download,
  FileDown, UserCheck, XCircle, ArrowRight,
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import * as XLSX from 'xlsx';
import api from '@/services/api/client';

// ===== TYPES =====

interface TimeToFillSummary {
  avg_days_to_close: number | null;
  avg_delay_days: number | null;
  closed_positions: number;
  total_positions: number;
}

interface StageTimingItem {
  stage: string;
  label: string;
  avg_days: number;
}

interface LastClosing {
  candidate_name: string;
  vacancy_title: string;
  recruiter_name: string | null;
  closed_date: string | null;
  days_to_close: number | null;
  start_date: string | null;
}

interface TimeToFillReport {
  summary: TimeToFillSummary;
  stage_timings: StageTimingItem[];
  last_closings: LastClosing[];
}

interface FunnelStageData {
  stage: string;
  label: string;
  candidate_count: number;
  rejection_count: number;
}

interface SourceBreakdown {
  source: string;
  count: number;
}

interface RejectionReasonItem {
  reason: string;
  count: number;
}

interface FunnelReport {
  stages: FunnelStageData[];
  total_candidates: number;
  total_rejections: number;
  sources: SourceBreakdown[];
  rejection_reasons: RejectionReasonItem[];
}

interface RecruiterFunnelItem {
  recruiter_id: number;
  recruiter_name: string;
  stages: FunnelStageData[];
  total_candidates: number;
  total_rejections: number;
}

interface FunnelByRecruiterReport {
  summary: FunnelReport;
  by_recruiter: RecruiterFunnelItem[];
}

interface RejectionsByStage {
  stage: string;
  label: string;
  count: number;
  reasons: RejectionReasonItem[];
}

interface RejectionsReport {
  total_rejections: number;
  by_stage: RejectionsByStage[];
  top_reasons: RejectionReasonItem[];
}

interface SourceReport {
  total_candidates: number;
  sources: SourceBreakdown[];
  by_stage: Record<string, SourceBreakdown[]>;
}

interface StageMovementItem {
  from_stage: string;
  from_label: string;
  to_stage: string;
  to_label: string;
  count: number;
}

interface MovementReport {
  total_movements: number;
  movements: StageMovementItem[];
}

// ===== CONSTANTS =====

const CATEGORIES = [
  { id: 'vacancy', label: 'Вакансии' },
  { id: 'recruiter', label: 'Рекрутеры' },
] as const;

const VACANCY_REPORTS = [
  { id: 'ttf', label: 'Время закрытия позиций', icon: Clock },
  { id: 'funnel', label: 'Воронка', icon: Filter },
  { id: 'funnel-recruiter', label: 'Воронка по рекрутерам', icon: Users },
  { id: 'sources', label: 'Источники резюме', icon: FileDown },
  { id: 'rejections', label: 'Отказы', icon: XCircle },
  { id: 'movement', label: 'Движение кандидатов', icon: ArrowRight },
] as const;

const PERIOD_OPTIONS = [
  { id: 'current', label: 'Текущая ситуация' },
  { id: 'month', label: 'За месяц' },
  { id: 'quarter', label: 'За квартал' },
  { id: 'half_year', label: 'За полгода' },
  { id: 'year', label: 'За год' },
] as const;

const VACANCY_STATUS_OPTIONS = [
  { id: 'open', label: 'В работе' },
  { id: 'all', label: 'Все' },
  { id: 'closed', label: 'Закрытые' },
] as const;

const BAR_COLORS = {
  candidate: 'var(--hf-report-candidate)',
  rejection_light: 'var(--hf-report-rejection-light)',
  rejection_medium: 'var(--hf-report-rejection-medium)',
  rejection_dark: 'var(--hf-report-rejection-dark)',
  source_green: 'var(--hf-report-source-green)',
  source_red: 'var(--hf-report-source-red)',
};

// ===== MAIN COMPONENT =====

export default function HRReportsPage() {
  const [category, setCategory] = useState<string>('vacancy');
  const [report, setReport] = useState<string>('ttf');
  const [period, setPeriod] = useState<string>('current');
  const [vacancyStatus, setVacancyStatus] = useState<string>('open');
  const [isLoading, setIsLoading] = useState(false);

  // Report data
  const [ttfData, setTtfData] = useState<TimeToFillReport | null>(null);
  const [funnelData, setFunnelData] = useState<FunnelReport | null>(null);
  const [funnelByRecruiter, setFunnelByRecruiter] = useState<FunnelByRecruiterReport | null>(null);
  const [rejectionsData, setRejectionsData] = useState<RejectionsReport | null>(null);
  const [sourcesData, setSourcesData] = useState<SourceReport | null>(null);
  const [movementData, setMovementData] = useState<MovementReport | null>(null);

  // Dropdowns
  const [showCategoryDD, setShowCategoryDD] = useState(false);
  const [showReportDD, setShowReportDD] = useState(false);
  const [showPeriodDD, setShowPeriodDD] = useState(false);
  const [showStatusDD, setShowStatusDD] = useState(false);

  const loadReport = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = { period, vacancy_status: vacancyStatus };

      switch (report) {
        case 'ttf': {
          const res = await api.get<TimeToFillReport>('/analytics/reports/time-to-fill', { params });
          setTtfData(res.data);
          break;
        }
        case 'funnel': {
          const res = await api.get<FunnelReport>('/analytics/reports/funnel', { params });
          setFunnelData(res.data);
          break;
        }
        case 'funnel-recruiter': {
          const res = await api.get<FunnelByRecruiterReport>('/analytics/reports/funnel-by-recruiter', { params });
          setFunnelByRecruiter(res.data);
          break;
        }
        case 'rejections': {
          const res = await api.get<RejectionsReport>('/analytics/reports/rejections', { params });
          setRejectionsData(res.data);
          break;
        }
        case 'sources': {
          const res = await api.get<SourceReport>('/analytics/reports/sources', { params });
          setSourcesData(res.data);
          break;
        }
        case 'movement': {
          const res = await api.get<MovementReport>('/analytics/reports/movement', { params });
          setMovementData(res.data);
          break;
        }
      }
    } catch (err: any) {
      toast.error('Ошибка загрузки отчёта');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [report, period, vacancyStatus]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const currentCategory = CATEGORIES.find(c => c.id === category);
  const currentReport = VACANCY_REPORTS.find(r => r.id === report);
  const currentPeriod = PERIOD_OPTIONS.find(p => p.id === period);
  const currentStatus = VACANCY_STATUS_OPTIONS.find(s => s.id === vacancyStatus);

  const exportToExcel = () => {
    const wb = XLSX.utils.book_new();
    const reportLabel = currentReport?.label || 'Отчёт';

    if (report === 'ttf' && ttfData) {
      // Summary sheet
      const summaryRows = [
        ['Ср. срок закрытия, дн', ttfData.summary.avg_days_to_close ?? '—'],
        ['Ср. просрочка, дн', ttfData.summary.avg_delay_days ?? '—'],
        ['Закрытых позиций', `${ttfData.summary.closed_positions}/${ttfData.summary.total_positions}`],
      ];
      const wsSummary = XLSX.utils.aoa_to_sheet([['Показатель', 'Значение'], ...summaryRows]);
      XLSX.utils.book_append_sheet(wb, wsSummary, 'Сводка');

      // Stage timings
      const stageRows = ttfData.stage_timings.map(s => [s.label, s.avg_days || '—']);
      const wsStages = XLSX.utils.aoa_to_sheet([['Этап', 'Ср. дней'], ...stageRows]);
      XLSX.utils.book_append_sheet(wb, wsStages, 'Время на этапе');

      // Last closings
      const closingRows = ttfData.last_closings.map(c => [
        c.candidate_name, c.vacancy_title, c.recruiter_name || '—',
        c.start_date || '—', c.closed_date || '—', c.days_to_close ?? '—',
      ]);
      const wsClosings = XLSX.utils.aoa_to_sheet([
        ['Кандидат', 'Вакансия', 'Рекрутер', 'Дата начала', 'Дата закрытия', 'Дней'],
        ...closingRows,
      ]);
      XLSX.utils.book_append_sheet(wb, wsClosings, 'Последние закрытия');

    } else if (report === 'funnel' && funnelData) {
      const rows = funnelData.stages.map(s => [s.label, s.candidate_count, s.rejection_count]);
      const ws = XLSX.utils.aoa_to_sheet([['Этап', 'Кандидатов', 'Отказов'], ...rows]);
      XLSX.utils.book_append_sheet(wb, ws, 'Воронка');

      if (funnelData.sources.length > 0) {
        const srcRows = funnelData.sources.map(s => [s.source, s.count]);
        const wsSrc = XLSX.utils.aoa_to_sheet([['Источник', 'Кол-во'], ...srcRows]);
        XLSX.utils.book_append_sheet(wb, wsSrc, 'Источники');
      }

    } else if (report === 'funnel-recruiter' && funnelByRecruiter) {
      for (const rec of funnelByRecruiter.by_recruiter) {
        const rows = rec.stages.map(s => [s.label, s.candidate_count, s.rejection_count]);
        const ws = XLSX.utils.aoa_to_sheet([['Этап', 'Кандидатов', 'Отказов'], ...rows]);
        const sheetName = rec.recruiter_name.substring(0, 31); // Excel limit 31 chars
        XLSX.utils.book_append_sheet(wb, ws, sheetName);
      }

    } else if (report === 'rejections' && rejectionsData) {
      const reasonRows = rejectionsData.top_reasons.map(r => [r.reason, r.count]);
      const ws = XLSX.utils.aoa_to_sheet([['Причина отказа', 'Кол-во'], ...reasonRows]);
      XLSX.utils.book_append_sheet(wb, ws, 'Причины отказов');

      const stageRows = rejectionsData.by_stage.map(s => [s.label, s.count]);
      const wsStage = XLSX.utils.aoa_to_sheet([['Этап', 'Отказов'], ...stageRows]);
      XLSX.utils.book_append_sheet(wb, wsStage, 'По этапам');

    } else if (report === 'sources' && sourcesData) {
      const rows = sourcesData.sources.map(s => [s.source, s.count]);
      const ws = XLSX.utils.aoa_to_sheet([['Источник', 'Кандидатов'], ...rows]);
      XLSX.utils.book_append_sheet(wb, ws, 'Источники');

    } else if (report === 'movement' && movementData) {
      const rows = movementData.movements.map(m => [m.from_label, m.to_label, m.count]);
      const ws = XLSX.utils.aoa_to_sheet([['Из этапа', 'В этап', 'Кол-во'], ...rows]);
      XLSX.utils.book_append_sheet(wb, ws, 'Движение');

    } else {
      toast.error('Нет данных для выгрузки');
      return;
    }

    XLSX.writeFile(wb, `${reportLabel} — ${currentPeriod?.label || ''}.xlsx`);
    toast.success('Файл выгружен');
  };

  return (
    <div className="min-h-screen bg-[var(--hf-main-50)]">
      {/* Header */}
      <div className="bg-[var(--hf-white)] border-b px-6 py-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <BarChart3 className="w-6 h-6 text-[var(--hf-main-700)]" />
            <h1 className="text-xl font-bold text-[var(--hf-main-900)]">Центр аналитики</h1>
          </div>
        </div>

        {/* Category + Report dropdowns */}
        <div className="flex items-center gap-3 mb-3">
          {/* Category dropdown */}
          <div className="relative">
            <button
              onClick={() => { setShowCategoryDD(!showCategoryDD); setShowReportDD(false); }}
              className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-[var(--hf-main-50)] font-medium"
            >
              {currentCategory?.label}
              <ChevronDown className="w-4 h-4" />
            </button>
            {showCategoryDD && (
              <div className="absolute z-20 mt-1 bg-[var(--hf-white)] border rounded-lg shadow-[var(--hf-shadow-lg)] py-1 min-w-[180px]">
                {CATEGORIES.map(c => (
                  <button
                    key={c.id}
                    onClick={() => {
                      setCategory(c.id);
                      if (c.id === 'recruiter') setReport('funnel-recruiter');
                      else setReport('ttf');
                      setShowCategoryDD(false);
                    }}
                    className={clsx(
                      'w-full text-left px-4 py-2 hover:bg-[var(--hf-main-50)]',
                      category === c.id && 'font-semibold'
                    )}
                  >
                    {category === c.id && <span className="mr-2">&#10003;</span>}
                    {c.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Report type dropdown */}
          <div className="relative">
            <button
              onClick={() => { setShowReportDD(!showReportDD); setShowCategoryDD(false); }}
              className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-[var(--hf-main-50)] font-medium"
            >
              {currentReport?.label}
              <ChevronDown className="w-4 h-4" />
            </button>
            {showReportDD && (
              <div className="absolute z-20 mt-1 bg-[var(--hf-white)] border rounded-lg shadow-[var(--hf-shadow-lg)] py-1 min-w-[300px]">
                {VACANCY_REPORTS.map(r => (
                  <button
                    key={r.id}
                    onClick={() => { setReport(r.id); setShowReportDD(false); }}
                    className={clsx(
                      'w-full text-left px-4 py-2.5 hover:bg-[var(--hf-main-50)] flex items-center gap-2',
                      report === r.id && 'font-semibold'
                    )}
                  >
                    {report === r.id && <span>&#10003;</span>}
                    {r.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Filters row */}
        <div className="flex items-center gap-4 text-sm">
          {/* Period */}
          <div className="relative">
            <button
              onClick={() => setShowPeriodDD(!showPeriodDD)}
              className="flex items-center gap-1 text-[var(--hf-main-600)] hover:text-[var(--hf-main-900)]"
            >
              За период: {currentPeriod?.label}
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
            {showPeriodDD && (
              <div className="absolute z-20 mt-1 bg-[var(--hf-white)] border rounded-lg shadow-[var(--hf-shadow-lg)] py-1 min-w-[200px]">
                {PERIOD_OPTIONS.map(p => (
                  <button
                    key={p.id}
                    onClick={() => { setPeriod(p.id); setShowPeriodDD(false); }}
                    className={clsx(
                      'w-full text-left px-4 py-2 hover:bg-[var(--hf-main-50)]',
                      period === p.id && 'font-semibold'
                    )}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Vacancy status */}
          <div className="relative">
            <button
              onClick={() => setShowStatusDD(!showStatusDD)}
              className="flex items-center gap-1 text-[var(--hf-main-600)] hover:text-[var(--hf-main-900)]"
            >
              Вакансии: {currentStatus?.label}
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
            {showStatusDD && (
              <div className="absolute z-20 mt-1 bg-[var(--hf-white)] border rounded-lg shadow-[var(--hf-shadow-lg)] py-1 min-w-[160px]">
                {VACANCY_STATUS_OPTIONS.map(s => (
                  <button
                    key={s.id}
                    onClick={() => { setVacancyStatus(s.id); setShowStatusDD(false); }}
                    className={clsx(
                      'w-full text-left px-4 py-2 hover:bg-[var(--hf-main-50)]',
                      vacancyStatus === s.id && 'font-semibold'
                    )}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Report content */}
      <div className="p-6">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-8 h-8 border-2 border-[color:var(--hf-status-yellow)] border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <motion.div
            key={report}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            {/* Title */}
            <div className="bg-[var(--hf-white)] rounded-xl shadow-[var(--hf-shadow-sm)] p-6 mb-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-semibold text-[var(--hf-main-900)]">
                  {currentCategory?.label} &rarr; {currentReport?.label}
                </h2>
                <button
                  onClick={exportToExcel}
                  className="flex items-center gap-2 px-3 py-2 hover:bg-[var(--hf-main-100)] rounded-lg text-sm text-[var(--hf-main-600)]"
                  title="Выгрузить в Excel"
                >
                  <Download className="w-5 h-5 text-[var(--hf-status-gray)]" />
                  <span>Excel</span>
                </button>
              </div>

              {report === 'ttf' && ttfData && <TTFContent data={ttfData} />}
              {report === 'funnel' && funnelData && <FunnelContent data={funnelData} />}
              {report === 'funnel-recruiter' && funnelByRecruiter && <FunnelByRecruiterContent data={funnelByRecruiter} />}
              {report === 'rejections' && rejectionsData && <RejectionsContent data={rejectionsData} />}
              {report === 'sources' && sourcesData && <SourcesContent data={sourcesData} />}
              {report === 'movement' && movementData && <MovementContent data={movementData} />}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

// ===== TTF REPORT =====

function TTFContent({ data }: { data: TimeToFillReport }) {
  const { summary, stage_timings, last_closings } = data;
  const maxDays = Math.max(...stage_timings.map(s => s.avg_days), 1);

  return (
    <>
      {/* KPI Cards */}
      <div className="grid grid-cols-3 gap-8 mb-10">
        <div>
          <div className="text-5xl font-bold text-[var(--hf-main-900)]">
            {summary.avg_days_to_close ?? '—'}
          </div>
          <div className="text-sm text-[var(--hf-main-500)] mt-1">Ср. срок закрытия, дн</div>
        </div>
        <div>
          <div className="text-5xl font-bold text-[var(--hf-main-900)]">
            {summary.avg_delay_days ?? '—'}
          </div>
          <div className="text-sm text-[var(--hf-main-500)] mt-1">Ср. просрочка, дн</div>
        </div>
        <div>
          <div className="text-5xl font-bold text-[var(--hf-main-900)]">
            {summary.closed_positions}
            <span className="text-2xl text-[var(--hf-status-gray)] font-normal">/{summary.total_positions}</span>
          </div>
          <div className="text-sm text-[var(--hf-main-500)] mt-1">Закрытых позиций</div>
        </div>
      </div>

      <hr className="mb-8" />

      {/* Stage timings chart */}
      <div className="mb-10">
        <h3 className="text-base font-semibold mb-1">Среднее время на этапе</h3>
        <p className="text-sm text-[var(--hf-main-500)] mb-6">
          Среднее время нахождения кандидатов на каждом этапе воронки
        </p>
        <div className="space-y-3">
          {stage_timings.map(st => (
            <div key={st.stage} className="flex items-center gap-4">
              <div className="w-48 text-sm text-[var(--hf-main-700)] text-right">{st.label}</div>
              <div className="flex-1 flex items-center gap-3">
                <div
                  className="h-8 rounded-sm"
                  style={{
                    width: `${Math.max((st.avg_days / maxDays) * 100, 2)}%`,
                    backgroundColor: BAR_COLORS.candidate,
                  }}
                />
                <span className="text-sm font-medium text-[var(--hf-main-700)]">{st.avg_days}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Last closings */}
      {last_closings.length > 0 && (
        <>
          <hr className="mb-8" />
          <div>
            <h3 className="text-base font-semibold mb-4">Последние закрытия</h3>
            <div className="space-y-3">
              {last_closings.map((lc, i) => (
                <div key={i} className="flex items-start gap-4 py-3 border-b border-[color:var(--hf-main-100)] last:border-0">
                  <UserCheck className="w-5 h-5 text-[var(--hf-green-500)] mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <div className="font-medium text-[var(--hf-main-900)]">{lc.candidate_name}</div>
                    <div className="text-sm text-[var(--hf-main-500)]">{lc.vacancy_title}</div>
                    <div className="text-xs text-[var(--hf-status-gray)] mt-1">
                      {lc.recruiter_name && <span>{lc.recruiter_name}, </span>}
                      {lc.closed_date}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-[var(--hf-main-600)]">Срок закрытия: <b>{lc.days_to_close}</b> дн</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ===== FUNNEL REPORT =====

function FunnelContent({ data }: { data: FunnelReport }) {
  const maxCount = Math.max(...data.stages.map(s => s.candidate_count), 1);
  const maxRej = Math.max(...data.stages.map(s => s.rejection_count), 1);

  return (
    <>
      <h3 className="text-base font-semibold mb-4">Сводка</h3>
      <div className="flex gap-8">
        {/* Funnel bars */}
        <div className="flex-1">
          <div className="flex gap-12 mb-6">
            <div className="text-sm font-medium text-[var(--hf-main-600)] w-48" />
            <div className="flex-1 text-sm font-medium text-[var(--hf-main-600)]">Воронка кандидатов</div>
            <div className="w-48 text-sm font-medium text-[var(--hf-main-600)]">Отказы после этапов</div>
          </div>
          <div className="space-y-2">
            {data.stages.map(st => (
              <div key={st.stage} className="flex items-center gap-4">
                <div className="w-48 text-sm text-[var(--hf-main-700)] text-right flex-shrink-0">{st.label}</div>
                {/* Candidate bar */}
                <div className="flex-1 flex items-center gap-2">
                  <div
                    className="h-7 rounded-sm"
                    style={{
                      width: `${Math.max((st.candidate_count / maxCount) * 100, 1)}%`,
                      backgroundColor: BAR_COLORS.source_green,
                    }}
                  />
                  <span className="text-xs text-[var(--hf-main-600)]">{st.candidate_count || ''}</span>
                </div>
                {/* Rejection bar */}
                <div className="w-48 flex items-center gap-2">
                  {st.rejection_count > 0 && (
                    <>
                      <div
                        className="h-7 rounded-sm"
                        style={{
                          width: `${(st.rejection_count / maxRej) * 100}%`,
                          backgroundColor: BAR_COLORS.rejection_light,
                        }}
                      />
                      <span className="text-xs text-[var(--hf-main-500)]">{st.rejection_count}</span>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="w-56 flex-shrink-0">
          <div className="mb-4">
            <div className="flex items-center justify-between font-semibold">
              <span>Все</span>
              <span>{data.total_candidates}</span>
            </div>
            {data.sources.map((s, i) => (
              <div key={i} className="flex items-center justify-between text-sm mt-1">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: i === 0 ? BAR_COLORS.source_green : BAR_COLORS.source_red }}
                  />
                  <span className="text-[var(--hf-main-600)]">{s.source === 'unknown' ? 'Не указан' : s.source}</span>
                </div>
                <span className="text-[var(--hf-main-700)]">{s.count}</span>
              </div>
            ))}
          </div>

          {data.rejection_reasons.length > 0 && (
            <div className="mt-6">
              <div className="flex items-center justify-between font-semibold">
                <span>Отказы</span>
                <span>{data.total_rejections}</span>
              </div>
              {data.rejection_reasons.map((r, i) => (
                <div key={i} className="flex items-center justify-between text-sm mt-1">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{
                        backgroundColor: i === 0 ? BAR_COLORS.rejection_light :
                          i === 1 ? BAR_COLORS.rejection_medium : BAR_COLORS.rejection_dark
                      }}
                    />
                    <span className="text-[var(--hf-main-600)] truncate max-w-[140px]">{r.reason}</span>
                  </div>
                  <span className="text-[var(--hf-main-700)]">{r.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ===== FUNNEL BY RECRUITER =====

function FunnelByRecruiterContent({ data }: { data: FunnelByRecruiterReport }) {
  return (
    <>
      <FunnelContent data={data.summary} />

      {data.by_recruiter.length > 0 && (
        <>
          <hr className="my-8" />
          <h3 className="text-base font-semibold mb-4">По рекрутерам</h3>
          <div className="space-y-6">
            {data.by_recruiter.map(rec => {
              const maxCount = Math.max(...rec.stages.map(s => s.candidate_count), 1);
              return (
                <div key={rec.recruiter_id} className="border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="font-medium text-[var(--hf-main-900)]">{rec.recruiter_name}</div>
                    <div className="text-sm text-[var(--hf-main-500)]">
                      {rec.total_candidates} кандидатов / {rec.total_rejections} отказов
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {rec.stages.map(st => (
                      <div key={st.stage} className="flex items-center gap-3">
                        <div className="w-40 text-xs text-[var(--hf-main-600)] text-right">{st.label}</div>
                        <div className="flex-1 flex items-center gap-2">
                          <div
                            className="h-5 rounded-sm"
                            style={{
                              width: `${Math.max((st.candidate_count / maxCount) * 100, 1)}%`,
                              backgroundColor: BAR_COLORS.source_green,
                            }}
                          />
                          {st.candidate_count > 0 && (
                            <span className="text-xs text-[var(--hf-main-500)]">{st.candidate_count}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}

// ===== REJECTIONS =====

function RejectionsContent({ data }: { data: RejectionsReport }) {
  const maxCount = Math.max(...data.by_stage.map(s => s.count), 1);

  return (
    <>
      <h3 className="text-base font-semibold mb-4">Сводка</h3>
      <div className="flex gap-8">
        <div className="flex-1">
          <div className="mb-2 text-sm text-[var(--hf-main-500)]">Отказы после этапов</div>
          <div className="space-y-2">
            {data.by_stage.map(st => (
              <div key={st.stage} className="flex items-center gap-4">
                <div className="w-48 text-sm text-[var(--hf-main-700)] text-right">{st.label}</div>
                <div className="flex-1 flex items-center gap-2">
                  <div
                    className="h-7 rounded-sm"
                    style={{
                      width: `${Math.max((st.count / maxCount) * 100, 2)}%`,
                      backgroundColor: BAR_COLORS.rejection_light,
                    }}
                  />
                  <span className="text-sm text-[var(--hf-main-600)]">{st.count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="w-56 flex-shrink-0">
          <div className="flex items-center justify-between font-semibold mb-2">
            <span>Отказы</span>
            <span>{data.total_rejections}</span>
          </div>
          {data.top_reasons.map((r, i) => (
            <div key={i} className="flex items-center justify-between text-sm mt-1">
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{
                    backgroundColor: i === 0 ? BAR_COLORS.rejection_light :
                      i === 1 ? BAR_COLORS.rejection_medium : BAR_COLORS.rejection_dark
                  }}
                />
                <span className="text-[var(--hf-main-600)] truncate max-w-[140px]">{r.reason}</span>
              </div>
              <span className="text-[var(--hf-main-700)]">{r.count}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

// ===== SOURCES =====

function SourcesContent({ data }: { data: SourceReport }) {
  const maxCount = Math.max(...data.sources.map(s => s.count), 1);
  const colors = ['var(--hf-report-source-green)', 'var(--hf-report-source-red)', 'var(--hf-report-candidate)', 'var(--hf-report-source-blue)', 'var(--hf-report-source-purple)', 'var(--hf-report-source-orange)'];

  return (
    <>
      <div className="mb-2 text-sm text-[var(--hf-main-500)]">
        Всего кандидатов: <b>{data.total_candidates}</b>
      </div>
      <div className="space-y-3 mt-6">
        {data.sources.map((s, i) => (
          <div key={i} className="flex items-center gap-4">
            <div className="w-48 text-sm text-[var(--hf-main-700)] text-right">{s.source}</div>
            <div className="flex-1 flex items-center gap-3">
              <div
                className="h-8 rounded-sm"
                style={{
                  width: `${Math.max((s.count / maxCount) * 100, 2)}%`,
                  backgroundColor: colors[i % colors.length],
                }}
              />
              <span className="text-sm font-medium">{s.count}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// ===== MOVEMENT =====

function MovementContent({ data }: { data: MovementReport }) {
  const maxCount = Math.max(...data.movements.map(m => m.count), 1);

  return (
    <>
      <div className="mb-2 text-sm text-[var(--hf-main-500)]">
        Всего перемещений: <b>{data.total_movements}</b>
      </div>
      <div className="space-y-2 mt-6">
        {data.movements.map((m, i) => (
          <div key={i} className="flex items-center gap-4">
            <div className="w-64 text-sm text-[var(--hf-main-700)] text-right flex items-center justify-end gap-1.5">
              <span>{m.from_label}</span>
              <ArrowRight className="w-3 h-3 text-[var(--hf-status-gray)] flex-shrink-0" />
              <span>{m.to_label}</span>
            </div>
            <div className="flex-1 flex items-center gap-3">
              <div
                className="h-7 rounded-sm"
                style={{
                  width: `${Math.max((m.count / maxCount) * 100, 2)}%`,
                  backgroundColor: m.to_stage === 'rejected' ? BAR_COLORS.rejection_light :
                    m.to_stage === 'hired' ? BAR_COLORS.source_green : BAR_COLORS.candidate,
                }}
              />
              <span className="text-sm font-medium">{m.count}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
