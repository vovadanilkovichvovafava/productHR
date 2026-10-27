import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  Users,
  AlertTriangle,
  TrendingUp,
  Star,
  Activity,
  Clock,
  Award,
  ClipboardCheck,
  ChevronDown,
  Loader2,
  RefreshCw,
  BarChart3,
  Info,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  AreaChart,
  Area,
} from 'recharts';
import clsx from 'clsx';
import { getPrometheusAnalytics } from '@/services/api';

// Chart colors
const SCORE_COLORS = ['#8b5cf6', '#3b82f6', '#f59e0b', '#ef4444'];
const CHURN_COLORS = ['#ef4444', '#f59e0b', '#10b981'];
const FUNNEL_COLOR = '#6366f1';
const TREND_COLORS = { activeUsers: '#10b981', totalActions: '#3b82f6' };

const PERIOD_OPTIONS = [
  { value: '7', label: '7 дней' },
  { value: '14', label: '14 дней' },
  { value: '30', label: '30 дней' },
  { value: '60', label: '60 дней' },
  { value: '90', label: '90 дней' },
];

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number; payload: { fill: string } }> }) {
  if (!active || !payload?.length) return null;
  const item = payload[0];
  return (
    <div className="bg-dark-800 border border-white/10 rounded-lg px-3 py-2 shadow-xl">
      <div className="flex items-center gap-2 text-sm">
        <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.payload.fill }} />
        <span className="text-white/80">{item.name}</span>
        <span className="font-semibold">{item.value}</span>
      </div>
    </div>
  );
}

function DonutCenterLabel({ value, label }: { value: string; label: string }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
      <span className="text-2xl font-bold">{value}</span>
      <span className="text-xs text-white/50">{label}</span>
    </div>
  );
}

export default function InternsAnalyticsTab() {
  const [selectedTrail, setSelectedTrail] = useState('all');
  const [selectedPeriod, setSelectedPeriod] = useState('30');

  const {
    data: analytics,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['prometheus-analytics', selectedTrail, selectedPeriod],
    queryFn: () => getPrometheusAnalytics(selectedTrail, selectedPeriod),
    staleTime: 60000,
    retry: 1,
  });

  // Score distribution chart data
  const scoreChartData = useMemo(() => {
    if (!analytics) return [];
    const { scoreDistribution: sd } = analytics;
    return [
      { name: 'Отлично (9-10)', value: sd.excellent, fill: SCORE_COLORS[0] },
      { name: 'Хорошо (7-8)', value: sd.good, fill: SCORE_COLORS[1] },
      { name: 'Удовл. (5-6)', value: sd.average, fill: SCORE_COLORS[2] },
      { name: 'Слабо (0-4)', value: sd.poor, fill: SCORE_COLORS[3] },
    ].filter(d => d.value > 0);
  }, [analytics]);

  // Churn risk chart data
  const churnChartData = useMemo(() => {
    if (!analytics) return [];
    const { churnRisk } = analytics;
    return [
      { name: 'Высокий (14+ дн.)', value: churnRisk.highCount, fill: CHURN_COLORS[0] },
      { name: 'Средний (7-14 дн.)', value: churnRisk.mediumCount, fill: CHURN_COLORS[1] },
      { name: 'Низкий (<7 дн.)', value: churnRisk.lowCount, fill: CHURN_COLORS[2] },
    ].filter(d => d.value > 0);
  }, [analytics]);

  // Funnel chart data
  const funnelChartData = useMemo(() => {
    if (!analytics) return [];
    return analytics.funnel.map(stage => ({
      name: stage.stage,
      count: stage.count,
      percent: stage.percent,
      fill: FUNNEL_COLOR,
    }));
  }, [analytics]);

  // Trail completion bar data
  const trailBarData = useMemo(() => {
    if (!analytics) return [];
    return analytics.trailProgress.map(t => ({
      name: t.title.length > 20 ? t.title.slice(0, 20) + '…' : t.title,
      fullName: t.title,
      completionRate: t.completionRate,
      approvalRate: t.approvalRate,
      enrollments: t.enrollments,
    }));
  }, [analytics]);

  // Trends chart data
  const trendsChartData = useMemo(() => {
    if (!analytics) return [];
    return analytics.trends.map(t => ({
      date: t.date.slice(5), // "02-01"
      activeUsers: t.activeUsers,
      totalActions: t.totalActions,
    }));
  }, [analytics]);

  // Average completion time per trail (from dropoff analysis)
  const trailAvgTimeMap = useMemo(() => {
    const map = new Map<string, number>();
    if (!analytics) return map;
    analytics.dropoffAnalysis.forEach(trail => {
      const modulesWithTime = trail.modules.filter(m => m.avgTimeDays > 0);
      if (modulesWithTime.length > 0) {
        const avg = modulesWithTime.reduce((sum, m) => sum + m.avgTimeDays, 0) / modulesWithTime.length;
        map.set(trail.trailId, Math.round(avg * 10) / 10);
      }
    });
    return map;
  }, [analytics]);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center py-20">
        <div className="text-center text-white/40">
          <Loader2 className="w-12 h-12 mx-auto mb-4 animate-spin opacity-50" />
          <h3 className="text-lg font-medium mb-2">Загрузка аналитики...</h3>
          <p className="text-sm">Получаем данные из Prometheus</p>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="h-full flex items-center justify-center py-20">
        <div className="text-center text-white/40">
          <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-red-400/60" />
          <h3 className="text-lg font-medium mb-2 text-red-400/80">Ошибка загрузки</h3>
          <p className="text-sm mb-4 max-w-md mx-auto">
            {(error as Error)?.message || 'Не удалось загрузить аналитику'}
          </p>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 mx-auto px-4 py-2 glass-button rounded-lg text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  if (!analytics) return null;

  const { summary, scoreDistribution, filters } = analytics;

  return (
    <div className="space-y-6 pb-3">
      {/* Filter Bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Trail filter */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-white/40">Трейл:</label>
          <div className="relative">
            <select
              value={selectedTrail}
              onChange={e => setSelectedTrail(e.target.value)}
              className="appearance-none pl-3 pr-8 py-2 glass-light rounded-lg text-sm focus:outline-none focus:border-emerald-500/50 cursor-pointer [&>option]:bg-dark-900 [&>option]:text-white"
            >
              <option value="all">Все трейлы</option>
              {filters.trails.map(trail => (
                <option key={trail.id} value={trail.id}>
                  {trail.title}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
          </div>
        </div>

        {/* Period filter */}
        <div className="flex items-center gap-1">
          <label className="text-xs text-white/40 mr-1">Период:</label>
          {PERIOD_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setSelectedPeriod(opt.value)}
              className={clsx(
                'px-2.5 py-1.5 text-xs rounded-lg border transition-colors',
                selectedPeriod === opt.value
                  ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400'
                  : 'glass-light text-white/50 hover:border-emerald-500/20'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <button
          onClick={() => refetch()}
          disabled={isLoading}
          className="ml-auto flex items-center gap-2 px-3 py-2 glass-button rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
        >
          <RefreshCw className={clsx('w-3.5 h-3.5', isLoading && 'animate-spin')} />
          Обновить
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KPICard icon={Users} iconColor="text-emerald-400" label="Всего студентов" value={String(summary.totalStudents)} delay={0.05} />
        <KPICard icon={AlertTriangle} iconColor="text-red-400" label="В зоне риска" value={String(summary.atRiskStudents)} delay={0.1} />
        <KPICard icon={TrendingUp} iconColor="text-blue-400" label="Конверсия" value={`${summary.conversionRate}%`} delay={0.15} />
        <KPICard icon={Activity} iconColor="text-purple-400" label="Активных в день" value={String(summary.avgDailyActiveUsers)} delay={0.2} />
        <KPICard icon={Star} iconColor="text-amber-400" label="Средний балл" value={scoreDistribution.avgScore?.toFixed(1) ?? '—'} delay={0.25} />
        <KPICard icon={ClipboardCheck} iconColor="text-cyan-400" label="Всего оценок" value={String(scoreDistribution.total)} delay={0.3} />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Score Distribution */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-light rounded-xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-3 text-center">Распределение оценок</h3>
          {scoreChartData.length > 0 ? (
            <>
              <div className="relative h-[160px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={scoreChartData} cx="50%" cy="50%" innerRadius={45} outerRadius={65} paddingAngle={3} dataKey="value" stroke="none">
                      {scoreChartData.map((entry, index) => (
                        <Cell key={index} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <DonutCenterLabel value={scoreDistribution.avgScore?.toFixed(1) ?? '—'} label="ср. балл" />
              </div>
              <ChartLegend items={scoreChartData} />
            </>
          ) : (
            <EmptyChart />
          )}
        </motion.div>

        {/* Churn Risk */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass-light rounded-xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-3 text-center">Риск оттока</h3>
          {churnChartData.length > 0 ? (
            <>
              <div className="relative h-[160px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={churnChartData} cx="50%" cy="50%" innerRadius={45} outerRadius={65} paddingAngle={3} dataKey="value" stroke="none">
                      {churnChartData.map((entry, index) => (
                        <Cell key={index} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <DonutCenterLabel value={String(summary.totalStudents)} label="всего" />
              </div>
              <ChartLegend items={churnChartData} />
            </>
          ) : (
            <EmptyChart />
          )}
        </motion.div>

        {/* Conversion Funnel */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass-light rounded-xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-3 text-center">Воронка конверсии</h3>
          {funnelChartData.length > 0 ? (
            <div className="h-[190px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={funnelChartData} layout="vertical" margin={{ left: 0, right: 10, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis type="number" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 9 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#2d2d3a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                    labelStyle={{ color: 'rgba(255,255,255,0.7)' }}
                    formatter={(value: number, _name: string, props: { payload?: { percent: number } }) => [`${value} (${props.payload?.percent ?? 0}%)`, 'Студентов']}
                  />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={14} fill={FUNNEL_COLOR} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChart />
          )}
        </motion.div>

        {/* Trail Completion */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass-light rounded-xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-3 text-center">Прогресс по трейлам</h3>
          {trailBarData.length > 0 ? (
            <div className="h-[190px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trailBarData} layout="vertical" margin={{ left: 0, right: 10, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis type="number" domain={[0, 100]} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 9 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#2d2d3a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                    labelStyle={{ color: 'rgba(255,255,255,0.7)' }}
                    formatter={(value: number) => [`${value}%`, 'Завершение']}
                  />
                  <Bar dataKey="completionRate" radius={[0, 4, 4, 0]} barSize={14}>
                    {trailBarData.map((entry, index) => (
                      <Cell key={index} fill={entry.completionRate >= 60 ? '#10b981' : entry.completionRate >= 30 ? '#f59e0b' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChart />
          )}
        </motion.div>
      </div>

      {/* Trends Chart */}
      {trendsChartData.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }} className="glass-light rounded-xl p-4">
          <h3 className="text-sm font-medium text-white/70 mb-3">Активность за период</h3>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendsChartData} margin={{ left: 0, right: 10, top: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#2d2d3a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                  labelStyle={{ color: 'rgba(255,255,255,0.7)' }}
                />
                <Area type="monotone" dataKey="activeUsers" name="Активные" stroke={TREND_COLORS.activeUsers} fill={TREND_COLORS.activeUsers} fillOpacity={0.15} strokeWidth={2} />
                <Area type="monotone" dataKey="totalActions" name="Действия" stroke={TREND_COLORS.totalActions} fill={TREND_COLORS.totalActions} fillOpacity={0.1} strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex justify-center gap-4">
            <div className="flex items-center gap-1.5 text-xs text-white/60">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: TREND_COLORS.activeUsers }} />
              <span>Активные пользователи</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-white/60">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: TREND_COLORS.totalActions }} />
              <span>Действия</span>
            </div>
          </div>
        </motion.div>
      )}

      {/* Trail Progress Details */}
      {analytics.trailProgress.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="glass-light rounded-xl">
          <div className="p-4 border-b border-white/10">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-emerald-400" />
              Детали по трейлам
              <span className="px-1.5 py-0.5 text-xs rounded-full bg-white/10 text-white/50">{analytics.trailProgress.length}</span>
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/5">
                  <ColumnHeaderWithTooltip label="Трейл" tooltip="Название учебного трейла (образовательной программы) в Prometheus." />
                  <ColumnHeaderWithTooltip label="Записано" tooltip="Количество студентов, зачисленных на данный трейл. Учитываются все, кто начал обучение." />
                  <ColumnHeaderWithTooltip label="Заверш. модулей" tooltip="Общее количество завершённых модулей по трейлу среди всех студентов." />
                  <ColumnHeaderWithTooltip label="Работ отправлено" tooltip="Суммарное количество работ (submissions), отправленных студентами на проверку по трейлу." />
                  <ColumnHeaderWithTooltip label="Одобрено" tooltip="Количество работ, получивших статус «одобрено» после проверки ментором." />
                  <ColumnHeaderWithTooltip label="% одобрения" tooltip="Процент одобренных работ от общего числа отправленных. Рассчитывается как (одобрено / отправлено) × 100%." />
                  <ColumnHeaderWithTooltip label="Ср. время прохождения" tooltip="Среднее время прохождения модулей трейла в днях. Рассчитывается на основе данных dropoff-анализа по модулям с ненулевым временем." />
                  <ColumnHeaderWithTooltip label="Сертификатов" tooltip="Количество выданных сертификатов об успешном завершении трейла." />
                </tr>
              </thead>
              <tbody>
                {analytics.trailProgress.map(trail => {
                  const avgTime = trailAvgTimeMap.get(trail.id);
                  return (
                    <tr key={trail.id} className="border-b border-white/5 hover:bg-dark-800/50 transition-colors">
                      <td className="px-4 py-3 font-medium truncate max-w-[200px]">{trail.title}</td>
                      <td className="px-4 py-3 text-white/60">{trail.enrollments}</td>
                      <td className="px-4 py-3 text-white/60">{trail.completedModules}</td>
                      <td className="px-4 py-3 text-white/60">{trail.submissionsCount}</td>
                      <td className="px-4 py-3 text-white/60">{trail.approvedSubmissions}</td>
                      <td className="px-4 py-3">
                        <span className={clsx('text-xs font-medium', {
                          'text-emerald-400': trail.approvalRate >= 70,
                          'text-amber-400': trail.approvalRate >= 40 && trail.approvalRate < 70,
                          'text-red-400': trail.approvalRate < 40,
                        })}>
                          {trail.approvalRate}%
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {avgTime != null ? (
                          <span className="flex items-center gap-1 text-white/60">
                            <Clock className="w-3.5 h-3.5 text-blue-400" />
                            {avgTime} дн.
                          </span>
                        ) : (
                          <span className="text-white/30">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {trail.certificates > 0 ? (
                          <span className="flex items-center gap-1 text-amber-400">
                            <Award className="w-3.5 h-3.5" />
                            {trail.certificates}
                          </span>
                        ) : (
                          <span className="text-white/30">0</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

    </div>
  );
}

// Helper components

function KPICard({
  icon: Icon,
  iconColor,
  label,
  value,
  delay,
}: {
  icon: typeof Users;
  iconColor: string;
  label: string;
  value: string;
  delay: number;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }} className="glass-light rounded-xl p-3">
      <div className="flex items-center gap-2 text-white/50 mb-1">
        <Icon className={clsx('w-4 h-4', iconColor)} />
        <span className="text-xs">{label}</span>
      </div>
      <p className="text-xl font-bold">{value}</p>
    </motion.div>
  );
}

function ChartLegend({ items }: { items: Array<{ name: string; value: number; fill: string }> }) {
  return (
    <div className="mt-2 flex flex-wrap justify-center gap-x-3 gap-y-1">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-1.5 text-xs text-white/60">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.fill }} />
          <span>{item.name}: {item.value}</span>
        </div>
      ))}
    </div>
  );
}

function EmptyChart() {
  return (
    <div className="h-[160px] flex items-center justify-center text-white/30 text-sm">Нет данных</div>
  );
}

function ColumnHeaderWithTooltip({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <th className="px-4 py-3 text-left text-xs font-medium text-white/40">
      <span className="group/tip relative inline-flex items-center gap-1 cursor-help">
        <span>{label}</span>
        <Info className="w-3 h-3 text-white/20 group-hover/tip:text-white/50 transition-colors flex-shrink-0" />
        <span className="absolute bottom-full left-0 mb-2 px-3 py-2 bg-dark-800 border border-white/10 rounded-lg text-xs text-white/80 font-normal whitespace-normal w-56 text-left opacity-0 invisible group-hover/tip:opacity-100 group-hover/tip:visible transition-all duration-200 z-50 shadow-xl pointer-events-none leading-relaxed">
          {tooltip}
        </span>
      </span>
    </th>
  );
}
