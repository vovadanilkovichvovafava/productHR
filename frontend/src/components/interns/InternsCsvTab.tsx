import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  Download,
  GraduationCap,
  BarChart3,
  GitBranch,
  ArrowLeft,
  AlertTriangle,
  FileSpreadsheet,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import {
  getPrometheusInterns,
  getPrometheusAnalytics,
} from '@/services/api';
import type {
  PrometheusIntern,
  PrometheusAnalyticsResponse,
  TrailProgressItem,
} from '@/services/api';

type CsvPanel = 'overview' | 'interns' | 'analytics' | 'trails';

interface ExportCard {
  id: 'interns' | 'analytics' | 'trails';
  icon: typeof GraduationCap;
  title: string;
  description: string;
  columns: { name: string; desc: string }[];
}

const EXPORT_CARDS: ExportCard[] = [
  {
    id: 'interns',
    icon: GraduationCap,
    title: 'Практиканты CSV',
    description:
      'Список практикантов: имя, email, Telegram, XP, серия дней, последняя активность, трейлы и прогресс по модулям.',
    columns: [
      { name: 'ID', desc: 'Идентификатор практиканта' },
      { name: 'ФИО', desc: 'Имя практиканта' },
      { name: 'Email', desc: 'Электронная почта' },
      { name: 'Telegram', desc: 'Telegram username' },
      { name: 'Общий XP', desc: 'Общее количество XP' },
      { name: 'Текущая серия (дней)', desc: 'Текущая серия активности' },
      { name: 'Последняя активность', desc: 'Дата последней активности' },
      { name: 'Дней с последней активности', desc: 'Количество дней неактивности' },
      { name: 'Количество трейлов', desc: 'Сколько трейлов назначено' },
      { name: 'Названия трейлов', desc: 'Перечень трейлов' },
      { name: 'Завершённых модулей', desc: 'Модулей завершено (всего)' },
      { name: 'Всего модулей', desc: 'Общее количество модулей' },
      { name: 'Дата регистрации', desc: 'Когда зарегистрирован' },
    ],
  },
  {
    id: 'analytics',
    icon: BarChart3,
    title: 'Аналитика CSV',
    description:
      'Ключевые метрики практикантов: общее количество, риск оттока, конверсия, активность, распределение оценок.',
    columns: [
      { name: 'Метрика', desc: 'Код метрики' },
      { name: 'Значение', desc: 'Значение метрики' },
      { name: 'Описание', desc: 'Описание метрики' },
    ],
  },
  {
    id: 'trails',
    icon: GitBranch,
    title: 'Трейлы CSV',
    description:
      'Прогресс по трейлам: записано, сертификатов, модулей, завершено, работ, одобрено, процент завершения и одобрения.',
    columns: [
      { name: 'ID трейла', desc: 'Идентификатор трейла' },
      { name: 'Название', desc: 'Название трейла' },
      { name: 'Записано студентов', desc: 'Количество записанных' },
      { name: 'Сертификатов', desc: 'Выдано сертификатов' },
      { name: 'Всего модулей', desc: 'Общее количество модулей' },
      { name: 'Завершено модулей', desc: 'Завершено модулей' },
      { name: 'Работ отправлено', desc: 'Количество отправленных работ' },
      { name: 'Работ одобрено', desc: 'Количество одобренных работ' },
      { name: 'Завершение (%)', desc: 'Процент завершения' },
      { name: 'Одобрение (%)', desc: 'Процент одобрения' },
    ],
  },
];

/** Escape a CSV value (wrap in quotes, escape internal quotes) */
function escapeCsvValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/** Convert rows to CSV string with BOM for Excel */
function toCsvString(headers: string[], rows: unknown[][]): string {
  const bom = '\uFEFF';
  const headerLine = headers.map(escapeCsvValue).join(',');
  const dataLines = rows.map(row => row.map(escapeCsvValue).join(','));
  return bom + [headerLine, ...dataLines].join('\r\n');
}

/** Trigger a download from a string */
function downloadCsv(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** Build CSV for interns list */
function buildInternsCsv(interns: PrometheusIntern[]): string {
  const headers = [
    'ID', 'ФИО', 'Email', 'Telegram', 'Общий XP', 'Текущая серия (дней)',
    'Последняя активность', 'Дней с последней активности', 'Количество трейлов', 'Названия трейлов',
    'Завершённых модулей', 'Всего модулей', 'Дата регистрации',
  ];
  const rows = interns.map(intern => {
    const trailNames = intern.trails.map(t => t.trailName).filter(Boolean).join('; ');
    const completedModules = intern.trails.reduce((sum, t) => sum + (t.completedModules || 0), 0);
    const totalModules = intern.trails.reduce((sum, t) => sum + (t.totalModules || 0), 0);
    return [
      intern.id,
      intern.name,
      intern.email || '',
      intern.telegramUsername || '',
      intern.totalXP,
      intern.currentStreak,
      intern.lastActiveAt || '',
      intern.daysSinceActive ?? '',
      intern.trails.length,
      trailNames,
      completedModules,
      totalModules,
      intern.createdAt || '',
    ];
  });
  return toCsvString(headers, rows);
}

/** Build CSV for analytics metrics */
function buildAnalyticsCsv(analytics: PrometheusAnalyticsResponse): string {
  const headers = ['Метрика', 'Значение', 'Описание'];
  const rows: unknown[][] = [];

  // Summary metrics
  const { summary } = analytics;
  rows.push(['total_students', summary.totalStudents, 'Всего практикантов']);
  rows.push(['at_risk_students', summary.atRiskStudents, 'Практикантов в зоне риска']);
  rows.push(['conversion_rate', `${summary.conversionRate}%`, 'Конверсия']);
  rows.push(['avg_daily_active', summary.avgDailyActiveUsers, 'Среднее активных в день']);

  // Score distribution
  const { scoreDistribution: sd } = analytics;
  rows.push(['score_excellent', sd.excellent, 'Оценки: Отлично (9-10)']);
  rows.push(['score_good', sd.good, 'Оценки: Хорошо (7-8)']);
  rows.push(['score_average', sd.average, 'Оценки: Удовлетворительно (5-6)']);
  rows.push(['score_poor', sd.poor, 'Оценки: Слабо (0-4)']);
  rows.push(['score_total', sd.total, 'Всего оценок']);
  rows.push(['score_avg', sd.avgScore, 'Средний балл']);

  // Churn risk
  const { churnRisk } = analytics;
  rows.push(['churn_risk_high', churnRisk.highCount, 'Риск оттока: Высокий (14+ дней неактивности)']);
  rows.push(['churn_risk_medium', churnRisk.mediumCount, 'Риск оттока: Средний (7-14 дней)']);
  rows.push(['churn_risk_low', churnRisk.lowCount, 'Риск оттока: Низкий (<7 дней)']);

  // Funnel stages
  analytics.funnel.forEach(stage => {
    rows.push([`funnel_${stage.stage}`, stage.count, `Воронка: ${stage.stage} (${stage.percent}%)`]);
  });

  return toCsvString(headers, rows);
}

/** Build CSV for trail progress */
function buildTrailsCsv(trailProgress: TrailProgressItem[]): string {
  const headers = [
    'ID трейла', 'Название', 'Записано студентов', 'Сертификатов', 'Всего модулей',
    'Завершено модулей', 'Работ отправлено', 'Работ одобрено',
    'Завершение (%)', 'Одобрение (%)',
  ];
  const rows = trailProgress.map(trail => [
    trail.id,
    trail.title,
    trail.enrollments,
    trail.certificates,
    trail.totalModules,
    trail.completedModules,
    trail.submissionsCount,
    trail.approvedSubmissions,
    trail.completionRate,
    trail.approvalRate,
  ]);
  return toCsvString(headers, rows);
}

export default function InternsCsvTab() {
  const [activePanel, setActivePanel] = useState<CsvPanel>('overview');
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  const activeCard = EXPORT_CARDS.find((c) => c.id === activePanel);

  // Pre-fetch data so we have it ready
  const { data: interns, isLoading: internsLoading } = useQuery({
    queryKey: ['prometheus-interns'],
    queryFn: getPrometheusInterns,
    staleTime: 60000,
    retry: 1,
  });

  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ['prometheus-analytics', 'all', '30'],
    queryFn: () => getPrometheusAnalytics('all', '30'),
    staleTime: 60000,
    retry: 1,
  });

  const dateStr = new Date().toISOString().slice(0, 10);

  const handleDownload = useCallback(async (type: 'interns' | 'analytics' | 'trails') => {
    setDownloadError(null);
    setIsDownloading(true);

    try {
      if (type === 'interns') {
        if (!interns || interns.length === 0) {
          setDownloadError('Нет данных практикантов для выгрузки. Попробуйте обновить страницу.');
          return;
        }
        const csv = buildInternsCsv(interns);
        downloadCsv(csv, `praktikanty-${dateStr}.csv`);
      } else if (type === 'analytics') {
        if (!analytics) {
          setDownloadError('Нет данных аналитики для выгрузки. Попробуйте обновить страницу.');
          return;
        }
        const csv = buildAnalyticsCsv(analytics);
        downloadCsv(csv, `analytika-praktikantov-${dateStr}.csv`);
      } else if (type === 'trails') {
        if (!analytics || !analytics.trailProgress || analytics.trailProgress.length === 0) {
          setDownloadError('Нет данных по трейлам для выгрузки. Попробуйте обновить страницу.');
          return;
        }
        const csv = buildTrailsCsv(analytics.trailProgress);
        downloadCsv(csv, `treyly-${dateStr}.csv`);
      }
    } catch {
      setDownloadError('Произошла ошибка при формировании файла. Попробуйте позже.');
    } finally {
      setIsDownloading(false);
    }
  }, [interns, analytics, dateStr]);

  const isDataLoading = internsLoading || analyticsLoading;

  return (
    <div className="max-w-4xl mx-auto space-y-6 w-full">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <FileSpreadsheet className="w-6 h-6 text-emerald-400" />
          <h2 className="text-xl font-bold">Выгрузка в CSV</h2>
        </div>
        <p className="text-sm text-white/50">
          Выберите тип данных для экспорта. Файл формируется из данных практикантов Prometheus.
        </p>
      </div>

      {/* Loading indicator */}
      {isDataLoading && (
        <div className="flex items-center gap-3 p-4 glass-light rounded-xl">
          <Loader2 className="w-5 h-5 text-emerald-400 animate-spin flex-shrink-0" />
          <p className="text-sm text-white/50">Загрузка данных практикантов...</p>
        </div>
      )}

      {/* Global error callout */}
      {downloadError && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-xl"
        >
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-red-300">{downloadError}</p>
            <button
              onClick={() => setDownloadError(null)}
              className="mt-2 text-xs text-red-400 hover:text-red-300 underline transition-colors"
            >
              Скрыть
            </button>
          </div>
        </motion.div>
      )}

      {activePanel === 'overview' ? (
        /* Cards grid */
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {EXPORT_CARDS.map((card, idx) => (
            <motion.button
              key={card.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.08 }}
              onClick={() => {
                setActivePanel(card.id);
                setDownloadError(null);
              }}
              className="glass-light hover:border-emerald-500/30 rounded-xl p-5 text-left group transition-all"
            >
              <div className="w-11 h-11 rounded-xl bg-emerald-500/20 flex items-center justify-center mb-4 group-hover:bg-emerald-500/30 transition-colors">
                <card.icon className="w-5 h-5 text-emerald-400" />
              </div>
              <h3 className="text-base font-semibold text-white mb-2">{card.title}</h3>
              <p className="text-white/40 text-sm leading-relaxed">{card.description}</p>
            </motion.button>
          ))}
        </div>
      ) : (
        /* Detail panel */
        activeCard && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-light rounded-xl p-6 space-y-6"
          >
            {/* Back button */}
            <button
              onClick={() => {
                setActivePanel('overview');
                setDownloadError(null);
              }}
              className="flex items-center gap-2 text-white/40 hover:text-white/80 transition-colors text-sm"
            >
              <ArrowLeft className="w-4 h-4" />
              Назад к выбору
            </button>

            {/* Card header */}
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                <activeCard.icon className="w-6 h-6 text-emerald-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">{activeCard.title}</h3>
                <p className="text-white/40 text-sm">{activeCard.description}</p>
              </div>
            </div>

            {/* Columns preview */}
            <div>
              <h4 className="text-sm font-medium text-white/50 mb-3">Поля в файле:</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {activeCard.columns.map((col) => (
                  <div
                    key={col.name}
                    className="flex items-center gap-2 px-3 py-2 glass-light rounded-lg"
                  >
                    <code className="text-xs text-emerald-400 font-mono">{col.name}</code>
                    <span className="text-xs text-white/30">&mdash;</span>
                    <span className="text-xs text-white/50">{col.desc}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Download */}
            <div className="pt-2 flex flex-col sm:flex-row items-start sm:items-center gap-3">
              <button
                onClick={() => handleDownload(activeCard.id)}
                disabled={isDataLoading || isDownloading}
                className={clsx(
                  'inline-flex items-center gap-3 px-6 py-3 rounded-xl font-medium transition-all',
                  'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {isDownloading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Download className="w-5 h-5" />
                )}
                {isDownloading ? 'Формирование...' : 'Скачать CSV'}
              </button>
            </div>
            <p className="text-white/30 text-xs">
              Файл формируется из данных Prometheus. Имя файла включает текущую дату.
            </p>
          </motion.div>
        )
      )}
    </div>
  );
}
