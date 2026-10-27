import { useState, useEffect, useCallback } from 'react';

import {
  BarChart3,
  Users,
  ArrowRight,
  Download,
  Plus,
  X,
  ChevronUp,
  ChevronDown,
  TrendingUp,
  Briefcase,
  Award,
  Clock,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '@/services/api/client';
import { backdropClose } from '@/utils/backdropClose';

// ============================================================
// TYPES
// ============================================================

interface DirectionMetrics {
  traffic: number;
  development: number;
  total: number;
}

interface ConversionMetrics {
  practice_to_dept: number | null;
  dept_to_probation: number | null;
}

interface PENMetricsResponse {
  started_practice: DirectionMetrics;
  entered_department: DirectionMetrics;
  passed_probation: DirectionMetrics;
  working_1year: DirectionMetrics;
  conversions: ConversionMetrics;
}

interface RecruiterMetrics {
  recruiter_id: number;
  recruiter_name: string;
  started_practice: number;
  entered_department: number;
  passed_probation: number;
  working_1year: number;
  total_bonus: number;
}

interface SalarySheetCandidate {
  entity_id: number | null;
  entity_name: string;
  direction: string;
  stage: string;
  amount: number;
}

interface SalarySheetEntry {
  recruiter_id: number;
  recruiter_name: string;
  candidates: SalarySheetCandidate[];
  total_bonus: number;
}

interface BonusCreate {
  recruiter_id: number;
  entity_id?: number;
  direction: string;
  stage: string;
  amount: number;
  notes?: string;
}

// ============================================================
// HELPERS
// ============================================================

const DIRECTION_LABELS: Record<string, string> = {
  traffic: 'Трафик',
  development: 'Развитие',
  targeted: 'Точечный',
};

const STAGE_LABELS: Record<string, string> = {
  practice: 'Практика',
  department: 'Отдел',
  probation: 'Испытательный',
};

const formatDate = (d: Date): string => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

type SortField = 'recruiter_name' | 'started_practice' | 'entered_department' | 'passed_probation' | 'working_1year' | 'total_bonus';
type SortDir = 'asc' | 'desc';

// ============================================================
// MAIN COMPONENT
// ============================================================

export default function PENDashboardPage() {
  // --- Period filter ---
  const [periodFrom, setPeriodFrom] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 3);
    return formatDate(d);
  });
  const [periodTo, setPeriodTo] = useState(() => formatDate(new Date()));

  // --- Recruiter filter ---
  const [selectedRecruiterId, setSelectedRecruiterId] = useState<number | null>(null);

  // --- Data ---
  const [metrics, setMetrics] = useState<PENMetricsResponse | null>(null);
  const [recruiters, setRecruiters] = useState<RecruiterMetrics[]>([]);
  const [salarySheet, setSalarySheet] = useState<SalarySheetEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // --- Recruiter table sort ---
  const [sortField, setSortField] = useState<SortField>('total_bonus');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // --- Salary sheet month picker ---
  const [salaryMonth, setSalaryMonth] = useState(new Date().getMonth() + 1);
  const [salaryYear, setSalaryYear] = useState(new Date().getFullYear());

  // --- Add bonus modal ---
  const [showBonusModal, setShowBonusModal] = useState(false);
  const [bonusForm, setBonusForm] = useState<BonusCreate>({
    recruiter_id: 0,
    direction: 'traffic',
    stage: 'department',
    amount: 0,
  });
  const [submittingBonus, setSubmittingBonus] = useState(false);

  // ============================================================
  // DATA LOADING
  // ============================================================

  const loadMetrics = useCallback(async () => {
    if (periodFrom && periodTo && periodFrom > periodTo) {
      toast.error('Дата начала должна быть раньше даты конца');
      return;
    }
    try {
      setIsLoading(true);
      setError(null);
      const metricsParams: Record<string, any> = { period_from: periodFrom, period_to: periodTo };
      if (selectedRecruiterId) {
        metricsParams.recruiter_id = selectedRecruiterId;
      }
      const periodParams = { period_from: periodFrom, period_to: periodTo };

      const [metricsRes, recruitersRes] = await Promise.all([
        api.get<PENMetricsResponse>('/pen/metrics', { params: metricsParams }),
        api.get<RecruiterMetrics[]>('/pen/recruiters', { params: periodParams }),
      ]);

      setMetrics(metricsRes.data);
      setRecruiters(recruitersRes.data);
    } catch (err: any) {
      setError(err.message || 'Ошибка загрузки данных');
      toast.error('Ошибка загрузки PEN метрик');
    } finally {
      setIsLoading(false);
    }
  }, [periodFrom, periodTo, selectedRecruiterId]);

  const loadSalarySheet = useCallback(async () => {
    try {
      const res = await api.get<SalarySheetEntry[]>('/pen/salary-sheet', {
        params: { month: salaryMonth, year: salaryYear },
      });
      setSalarySheet(res.data);
    } catch {
      toast.error('Ошибка загрузки зарплатного листа');
    }
  }, [salaryMonth, salaryYear]);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  useEffect(() => {
    loadSalarySheet();
  }, [loadSalarySheet]);

  // ============================================================
  // ACTIONS
  // ============================================================

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const sortedRecruiters = [...recruiters].sort((a, b) => {
    const av = a[sortField];
    const bv = b[sortField];
    if (typeof av === 'string' && typeof bv === 'string') {
      return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    }
    return sortDir === 'asc' ? (av as number) - (bv as number) : (bv as number) - (av as number);
  });

  const handleExportCSV = async () => {
    try {
      const res = await api.get('/pen/salary-sheet/csv', {
        params: { month: salaryMonth, year: salaryYear },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `salary_sheet_${salaryYear}_${String(salaryMonth).padStart(2, '0')}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('CSV экспортирован');
    } catch {
      toast.error('Ошибка экспорта CSV');
    }
  };

  const handleSubmitBonus = async () => {
    if (!bonusForm.recruiter_id || !bonusForm.amount) {
      toast.error('Заполните все обязательные поля');
      return;
    }
    if (!bonusForm.direction) {
      toast.error('Выберите направление');
      return;
    }
    if (!bonusForm.stage) {
      toast.error('Выберите этап');
      return;
    }
    try {
      setSubmittingBonus(true);
      await api.post('/pen/bonus', bonusForm);
      toast.success('Бонус добавлен');
      setShowBonusModal(false);
      setBonusForm({ recruiter_id: 0, direction: 'traffic', stage: 'department', amount: 0 });
      loadMetrics();
      loadSalarySheet();
    } catch {
      toast.error('Ошибка добавления бонуса');
    } finally {
      setSubmittingBonus(false);
    }
  };

  // ============================================================
  // RENDER
  // ============================================================

  if (isLoading && !metrics) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[var(--hf-accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error && !metrics) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4 text-[var(--hf-white)]">
        <p className="text-[var(--hf-status-red)]">{error}</p>
        <button
          onClick={loadMetrics}
          className="px-4 py-2 bg-[var(--hf-accent)] rounded-lg hover:bg-[var(--hf-accent-hover)] transition-colors"
        >
          Повторить
        </button>
      </div>
    );
  }

  const m = metrics!;

  const funnelStages = [
    { key: 'started_practice', label: 'Практика', value: m.started_practice.total, icon: Briefcase },
    { key: 'entered_department', label: 'В отделе', value: m.entered_department.total, icon: Users },
    { key: 'passed_probation', label: 'Испытательный', value: m.passed_probation.total, icon: Award },
    { key: 'working_1year', label: '1 год', value: m.working_1year.total, icon: Clock },
  ];

  const maxFunnel = Math.max(...funnelStages.map((s) => s.value), 1);

  return (
    <div className="h-full flex flex-col bg-[var(--hf-bg-dark)] overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-[color:var(--hf-white-alpha-08)] sticky top-0 bg-[var(--hf-bg-dark)] z-10">
        <div className="flex items-center gap-3">
          <TrendingUp className="w-6 h-6 text-[var(--hf-accent)]" />
          <h1 className="text-xl font-semibold text-[var(--hf-white)]">PEN Dashboard</h1>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-sm text-[var(--hf-dark-300)]">Период:</label>
          <input
            type="date"
            value={periodFrom}
            onChange={(e) => setPeriodFrom(e.target.value)}
            className="px-3 py-1.5 bg-[var(--hf-bg-dark-panel)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
          />
          <span className="text-[var(--hf-dark-400)]">—</span>
          <input
            type="date"
            value={periodTo}
            onChange={(e) => setPeriodTo(e.target.value)}
            className="px-3 py-1.5 bg-[var(--hf-bg-dark-panel)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
          />
          <div className="w-px h-6 bg-[var(--hf-dark-600)]" />
          <label className="text-sm text-[var(--hf-dark-300)]">Рекрутер:</label>
          <select
            value={selectedRecruiterId ?? ''}
            onChange={(e) => setSelectedRecruiterId(e.target.value ? Number(e.target.value) : null)}
            className="px-3 py-1.5 bg-[var(--hf-bg-dark-panel)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)] min-w-[160px]"
          >
            <option value="">Все рекрутеры</option>
            {recruiters.map((r) => (
              <option key={r.recruiter_id} value={r.recruiter_id}>
                {r.recruiter_name}
              </option>
            ))}
          </select>
          <button
            onClick={loadMetrics}
            className="px-4 py-1.5 bg-[var(--hf-accent)] text-[var(--hf-white)] rounded-lg text-sm hover:bg-[var(--hf-accent-hover)] transition-colors"
          >
            Применить
          </button>
        </div>
      </div>

      <div className="p-4 space-y-6">
        {/* ============ METRIC CARDS ============ */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Начали практику"
            data={m.started_practice}
            color="blue"
            icon={<Briefcase className="w-5 h-5" />}
          />
          <MetricCard
            title="Вошли в отдел"
            data={m.entered_department}
            color="emerald"
            icon={<Users className="w-5 h-5" />}
          />
          <MetricCard
            title="Прошли испытательный"
            data={m.passed_probation}
            color="amber"
            icon={<Award className="w-5 h-5" />}
          />
          <MetricCard
            title="Работают 1 год"
            data={m.working_1year}
            color="purple"
            icon={<Clock className="w-5 h-5" />}
          />
        </div>

        {/* ============ CONVERSION FUNNEL ============ */}
        <div
          className="bg-[var(--hf-white-alpha-04)] rounded-xl p-5 border border-[color:var(--hf-white-alpha-08)]"
        >
          <h2 className="text-lg font-semibold text-[var(--hf-white)] mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-[var(--hf-accent)]" />
            Воронка конверсий
          </h2>

          <div className="space-y-3">
            {funnelStages.map((stage, idx) => {
              const Icon = stage.icon;
              const pct = maxFunnel > 0 ? (stage.value / maxFunnel) * 100 : 0;
              const conversion =
                idx === 1
                  ? m.conversions.practice_to_dept
                  : idx === 2
                    ? m.conversions.dept_to_probation
                    : null;

              return (
                <div key={stage.key}>
                  {idx > 0 && conversion !== null && (
                    <div className="flex items-center gap-2 ml-6 my-1 text-sm text-[var(--hf-dark-300)]">
                      <ArrowRight className="w-4 h-4 text-[var(--hf-accent)]" />
                      <span className="text-[var(--hf-accent)] font-medium">{conversion.toFixed(1)}%</span>
                    </div>
                  )}
                  {idx > 0 && conversion === null && idx < funnelStages.length && (
                    <div className="flex items-center gap-2 ml-6 my-1 text-sm text-[var(--hf-dark-300)]">
                      <ArrowRight className="w-4 h-4 text-[var(--hf-dark-500)]" />
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    <div className="w-32 flex items-center gap-2 text-sm text-[var(--hf-dark-200)] shrink-0">
                      <Icon className="w-4 h-4 text-[var(--hf-accent)]" />
                      {stage.label}
                    </div>
                    <div className="flex-1 h-8 bg-[var(--hf-bg-dark-panel)] rounded-lg overflow-hidden relative">
                      <div
                        style={{ width: `${Math.max(pct, 2)}%` }}
                        className="h-full bg-[var(--hf-accent)] rounded-lg"
                      />
                      <span className="absolute inset-0 flex items-center px-3 text-sm font-medium text-[var(--hf-white)]">
                        {stage.value}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ============ RECRUITER TABLE ============ */}
        <div
          className="bg-[var(--hf-white-alpha-04)] rounded-xl p-5 border border-[color:var(--hf-white-alpha-08)]"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-[var(--hf-white)] flex items-center gap-2">
              <Users className="w-5 h-5 text-[var(--hf-accent)]" />
              Рекрутеры
            </h2>
            <button
              onClick={() => setShowBonusModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--hf-accent)] text-[var(--hf-white)] rounded-lg text-sm hover:bg-[var(--hf-accent-hover)] transition-colors"
            >
              <Plus className="w-4 h-4" />
              Добавить бонус
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[color:var(--hf-white-alpha-10)]">
                  {([
                    ['recruiter_name', 'Рекрутер'],
                    ['started_practice', 'Практика'],
                    ['entered_department', 'Отдел'],
                    ['passed_probation', 'Испытательный'],
                    ['working_1year', '1 год'],
                    ['total_bonus', 'Бонус, руб'],
                  ] as [SortField, string][]).map(([field, label]) => (
                    <th
                      key={field}
                      onClick={() => handleSort(field)}
                      className="py-2 px-3 text-left text-[var(--hf-dark-300)] font-medium cursor-pointer hover:text-[var(--hf-white)] transition-colors select-none"
                    >
                      <span className="inline-flex items-center gap-1">
                        {label}
                        {sortField === field && (
                          sortDir === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRecruiters.map((r) => (
                  <tr
                    key={r.recruiter_id}
                    onClick={() => {
                      setSelectedRecruiterId(selectedRecruiterId === r.recruiter_id ? null : r.recruiter_id);
                    }}
                    className={`border-b border-[color:var(--hf-white-alpha-05)] hover:bg-[var(--hf-white-alpha-04)] transition-colors cursor-pointer ${
                      selectedRecruiterId === r.recruiter_id ? 'bg-[var(--hf-accent-bg-10)] border-[color:var(--hf-accent-border-30)]' : ''
                    }`}
                  >
                    <td className="py-2.5 px-3 text-[var(--hf-white)] font-medium">
                      {r.recruiter_name}
                      {selectedRecruiterId === r.recruiter_id && (
                        <span className="ml-2 text-xs text-[var(--hf-accent)]">&#x2713; выбран</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-[var(--hf-dark-200)]">{r.started_practice}</td>
                    <td className="py-2.5 px-3 text-[var(--hf-dark-200)]">{r.entered_department}</td>
                    <td className="py-2.5 px-3 text-[var(--hf-dark-200)]">{r.passed_probation}</td>
                    <td className="py-2.5 px-3 text-[var(--hf-dark-200)]">{r.working_1year}</td>
                    <td className="py-2.5 px-3 text-[var(--hf-accent)] font-medium">
                      {r.total_bonus.toLocaleString('ru-RU')}
                    </td>
                  </tr>
                ))}
                {sortedRecruiters.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-[var(--hf-dark-400)]">
                      Нет данных за выбранный период
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ============ SALARY SHEET ============ */}
        <div
          className="bg-[var(--hf-white-alpha-04)] rounded-xl p-5 border border-[color:var(--hf-white-alpha-08)]"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-[var(--hf-white)] flex items-center gap-2">
              <Award className="w-5 h-5 text-[var(--hf-accent)]" />
              Зарплатный лист
            </h2>
            <div className="flex items-center gap-3">
              <select
                value={salaryMonth}
                onChange={(e) => setSalaryMonth(Number(e.target.value))}
                className="px-3 py-1.5 bg-[var(--hf-bg-dark-panel)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
              >
                {Array.from({ length: 12 }, (_, i) => (
                  <option key={i + 1} value={i + 1}>
                    {new Date(2024, i, 1).toLocaleString('ru-RU', { month: 'long' })}
                  </option>
                ))}
              </select>
              <select
                value={salaryYear}
                onChange={(e) => setSalaryYear(Number(e.target.value))}
                className="px-3 py-1.5 bg-[var(--hf-bg-dark-panel)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
              >
                {Array.from({ length: 5 }, (_, i) => {
                  const y = new Date().getFullYear() - 2 + i;
                  return (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  );
                })}
              </select>
              <button
                onClick={handleExportCSV}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--hf-dark-700)] text-[var(--hf-white)] rounded-lg text-sm hover:bg-[var(--hf-dark-600)] transition-colors"
              >
                <Download className="w-4 h-4" />
                CSV
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[color:var(--hf-white-alpha-10)]">
                  <th className="py-2 px-3 text-left text-[var(--hf-dark-300)] font-medium">Рекрутер</th>
                  <th className="py-2 px-3 text-left text-[var(--hf-dark-300)] font-medium">Кандидат</th>
                  <th className="py-2 px-3 text-left text-[var(--hf-dark-300)] font-medium">Направление</th>
                  <th className="py-2 px-3 text-left text-[var(--hf-dark-300)] font-medium">Этап</th>
                  <th className="py-2 px-3 text-right text-[var(--hf-dark-300)] font-medium">Сумма</th>
                </tr>
              </thead>
              <tbody>
                {salarySheet.map((entry) =>
                  entry.candidates.length > 0 ? (
                    entry.candidates.map((c, ci) => (
                      <tr
                        key={`${entry.recruiter_id}-${ci}`}
                        className="border-b border-[color:var(--hf-white-alpha-05)] hover:bg-[var(--hf-white-alpha-02)] transition-colors"
                      >
                        {ci === 0 && (
                          <td
                            rowSpan={entry.candidates.length}
                            className="py-2.5 px-3 text-[var(--hf-white)] font-medium align-top"
                          >
                            {entry.recruiter_name}
                            <div className="text-xs text-[var(--hf-accent)] mt-1">
                              Итого: {entry.total_bonus.toLocaleString('ru-RU')} руб
                            </div>
                          </td>
                        )}
                        <td className="py-2.5 px-3 text-[var(--hf-dark-200)]">{c.entity_name}</td>
                        <td className="py-2.5 px-3 text-[var(--hf-dark-200)]">
                          {DIRECTION_LABELS[c.direction] || c.direction}
                        </td>
                        <td className="py-2.5 px-3 text-[var(--hf-dark-200)]">
                          {STAGE_LABELS[c.stage] || c.stage}
                        </td>
                        <td className="py-2.5 px-3 text-right text-[var(--hf-accent)] font-medium">
                          {c.amount.toLocaleString('ru-RU')}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr key={entry.recruiter_id} className="border-b border-[color:var(--hf-white-alpha-05)]">
                      <td className="py-2.5 px-3 text-[var(--hf-white)] font-medium">{entry.recruiter_name}</td>
                      <td colSpan={4} className="py-2.5 px-3 text-[var(--hf-dark-400)]">
                        Нет бонусов за этот месяц
                      </td>
                    </tr>
                  )
                )}
                {salarySheet.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-[var(--hf-dark-400)]">
                      Нет данных за выбранный месяц
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ============ ADD BONUS MODAL ============ */}
      {showBonusModal && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--hf-black-alpha-60)] backdrop-blur-sm"
            {...backdropClose(() => setShowBonusModal(false))}
          >
            <div
              className="bg-[var(--hf-bg-dark-panel)] rounded-xl border border-[color:var(--hf-white-alpha-10)] p-6 w-full max-w-md"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-lg font-semibold text-[var(--hf-white)]">Добавить бонус</h3>
                <button
                  onClick={() => setShowBonusModal(false)}
                  className="text-[var(--hf-dark-400)] hover:text-[var(--hf-white)] transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4">
                {/* Recruiter select */}
                <div>
                  <label className="block text-sm text-[var(--hf-dark-300)] mb-1">Рекрутер</label>
                  <select
                    value={bonusForm.recruiter_id}
                    onChange={(e) =>
                      setBonusForm((f) => ({ ...f, recruiter_id: Number(e.target.value) }))
                    }
                    className="w-full px-3 py-2 bg-[var(--hf-dark-700)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
                  >
                    <option value={0}>Выберите рекрутера</option>
                    {recruiters.map((r) => (
                      <option key={r.recruiter_id} value={r.recruiter_id}>
                        {r.recruiter_name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Direction */}
                <div>
                  <label className="block text-sm text-[var(--hf-dark-300)] mb-1">Направление</label>
                  <select
                    value={bonusForm.direction}
                    onChange={(e) => setBonusForm((f) => ({ ...f, direction: e.target.value }))}
                    className="w-full px-3 py-2 bg-[var(--hf-dark-700)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
                  >
                    <option value="traffic">Трафик</option>
                    <option value="development">Развитие</option>
                    <option value="targeted">Точечный</option>
                  </select>
                </div>

                {/* Stage */}
                <div>
                  <label className="block text-sm text-[var(--hf-dark-300)] mb-1">Этап</label>
                  <select
                    value={bonusForm.stage}
                    onChange={(e) => setBonusForm((f) => ({ ...f, stage: e.target.value }))}
                    className="w-full px-3 py-2 bg-[var(--hf-dark-700)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
                  >
                    <option value="practice">Начал практику</option>
                    <option value="department">Вошёл в отдел</option>
                    <option value="probation">Прошёл испытательный</option>
                  </select>
                </div>

                {/* Amount */}
                <div>
                  <label className="block text-sm text-[var(--hf-dark-300)] mb-1">Сумма (руб)</label>
                  <input
                    type="number"
                    value={bonusForm.amount || ''}
                    onChange={(e) =>
                      setBonusForm((f) => ({ ...f, amount: Number(e.target.value) }))
                    }
                    placeholder="0"
                    className="w-full px-3 py-2 bg-[var(--hf-dark-700)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
                  />
                </div>

                {/* Notes */}
                <div>
                  <label className="block text-sm text-[var(--hf-dark-300)] mb-1">Комментарий</label>
                  <input
                    type="text"
                    value={bonusForm.notes || ''}
                    onChange={(e) => setBonusForm((f) => ({ ...f, notes: e.target.value }))}
                    placeholder="Необязательно"
                    className="w-full px-3 py-2 bg-[var(--hf-dark-700)] border border-[color:var(--hf-white-alpha-10)] rounded-lg text-[var(--hf-white)] text-sm focus:outline-none focus:border-[var(--hf-accent)]"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setShowBonusModal(false)}
                  className="px-4 py-2 bg-[var(--hf-dark-700)] text-[var(--hf-white)] rounded-lg text-sm hover:bg-[var(--hf-dark-600)] transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={handleSubmitBonus}
                  disabled={submittingBonus}
                  className="px-4 py-2 bg-[var(--hf-accent)] text-[var(--hf-white)] rounded-lg text-sm hover:bg-[var(--hf-accent-hover)] transition-colors disabled:opacity-50"
                >
                  {submittingBonus ? 'Сохранение...' : 'Сохранить'}
                </button>
              </div>
            </div>
          </div>
        )}
    </div>
  );
}

// ============================================================
// METRIC CARD COMPONENT
// ============================================================

const COLOR_MAP: Record<string, { bg: string; border: string; text: string }> = {
  blue: { bg: 'bg-[var(--hf-status-blue-bg)]', border: 'border-[color:var(--hf-accent-border-30)]', text: 'text-[var(--hf-status-blue)]' },
  emerald: { bg: 'bg-[var(--hf-status-green-bg)]', border: 'border-[color:var(--hf-status-green-badge)]', text: 'text-[var(--hf-status-green)]' },
  amber: { bg: 'bg-[var(--hf-status-yellow-bg)]', border: 'border-[color:var(--hf-status-yellow-badge)]', text: 'text-[var(--hf-status-yellow)]' },
  purple: { bg: 'bg-[var(--hf-status-purple-bg)]', border: 'border-[color:var(--hf-status-purple-badge)]', text: 'text-[var(--hf-status-purple)]' },
};

function MetricCard({
  title,
  data,
  color,
  icon,
}: {
  title: string;
  data: DirectionMetrics;
  color: string;
  icon: React.ReactNode;
}) {
  const c = COLOR_MAP[color] || COLOR_MAP.blue;

  return (
    <div
      className={`rounded-xl p-4 border ${c.bg} ${c.border}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className={c.text}>{icon}</span>
        <span className="text-sm text-[var(--hf-dark-300)]">{title}</span>
      </div>
      <div className="text-3xl font-bold text-[var(--hf-white)] mb-2">{data.total}</div>
      <div className="flex items-center gap-4 text-xs text-[var(--hf-dark-400)]">
        <span>
          Трафик: <span className="text-[var(--hf-dark-200)]">{data.traffic}</span>
        </span>
        <span>
          Развитие: <span className="text-[var(--hf-dark-200)]">{data.development}</span>
        </span>
      </div>
    </div>
  );
}
