import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Flame,
  Zap,
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  RefreshCw,
  ChevronDown,
  BookOpen,
  Activity,
} from 'lucide-react';
import clsx from 'clsx';
import { getContactPrometheusReview } from '@/services/api';
import type { ContactPrometheusResponse, ContactPrometheusReview, ContactReviewTrail } from '@/services/api';
import { usePrometheusSingleSync } from '@/hooks';

interface PrometheusTabProps {
  entityId: number;
  /** Contact email — used for Prometheus status sync polling */
  email?: string;
}

// ── HR Status badge ──

const HR_STATUS_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  'Обучается': { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30' },
  'Принят': { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  'Отклонен': { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30' },
};

function PrometheusStatusBadge({ status }: { status: string }) {
  const style = HR_STATUS_STYLES[status] || { bg: 'bg-white/10', text: 'text-white/60', border: 'border-white/10' };
  return (
    <span className={clsx('px-2 py-0.5 text-[10px] rounded-full border whitespace-nowrap', style.bg, style.text, style.border)}>
      {status}
    </span>
  );
}

// ── Skeleton shown during loading ──

function PrometheusTabSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-orange-500/20">
          <Flame size={18} className="text-orange-400" />
        </div>
        <div>
          <div className="h-5 w-32 bg-white/10 rounded mb-1" />
          <div className="h-3 w-56 bg-white/10 rounded" />
        </div>
      </div>
      {/* Metrics cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="glass-light rounded-lg p-3">
            <div className="h-3 w-16 bg-white/10 rounded mb-2" />
            <div className="h-6 w-12 bg-white/10 rounded" />
          </div>
        ))}
      </div>
      {/* Review block */}
      <div className="glass-light rounded-xl p-4">
        <div className="h-5 w-48 bg-white/10 rounded mb-3" />
        <div className="space-y-2">
          <div className="h-4 w-full bg-white/10 rounded" />
          <div className="h-4 w-5/6 bg-white/10 rounded" />
          <div className="h-4 w-4/6 bg-white/10 rounded" />
        </div>
      </div>
      {/* Trails */}
      <div className="space-y-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="glass-light rounded-lg p-3">
            <div className="h-4 w-40 bg-white/10 rounded mb-2" />
            <div className="h-1.5 w-full bg-white/10 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Trail card ──

function TrailCard({ trail }: { trail: ContactReviewTrail }) {
  const [expanded, setExpanded] = useState(false);

  const pctColor =
    trail.completionPercent >= 80 ? 'bg-emerald-400' :
    trail.completionPercent >= 50 ? 'bg-amber-400' :
    'bg-blue-400';

  return (
    <div className="glass-light rounded-lg p-3 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left"
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <GitBranch className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span className="text-sm font-medium truncate">{trail.trailName}</span>
            <ChevronDown
              className={clsx(
                'w-3.5 h-3.5 text-white/30 transition-transform flex-shrink-0',
                expanded ? 'rotate-180' : '',
              )}
            />
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="text-xs text-white/40">
              {trail.completedModules}/{trail.totalModules}
            </span>
            <span className="text-xs text-white/50">{trail.completionPercent}%</span>
          </div>
        </div>
      </button>
      {/* Progress bar */}
      <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all', pctColor)}
          style={{ width: `${trail.completionPercent}%` }}
        />
      </div>

      {/* Expanded details */}
      {expanded && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          transition={{ duration: 0.2 }}
          className="mt-3 pt-3 border-t border-white/5 space-y-2"
        >
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="text-white/40">Заработано XP</div>
            <div className="text-white/70 font-medium">{trail.earnedXP}</div>
            {trail.avgScore !== null && trail.avgScore !== undefined && (
              <>
                <div className="text-white/40">Средний балл</div>
                <div className="text-white/70 font-medium">{trail.avgScore}</div>
              </>
            )}
          </div>
          {trail.submissions && trail.submissions.total > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              {trail.submissions.approved > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400">
                  Одобрено: {trail.submissions.approved}
                </span>
              )}
              {trail.submissions.pending > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400">
                  На проверке: {trail.submissions.pending}
                </span>
              )}
              {trail.submissions.revision > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/20 text-purple-400">
                  На доработке: {trail.submissions.revision}
                </span>
              )}
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}

// ── Main component ──

export default function PrometheusTab({ entityId, email }: PrometheusTabProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ContactPrometheusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Resolve email from props or from loaded data (intern's email)
  const resolvedEmail = email || data?.intern?.email || undefined;

  // 30-second status sync polling (only when tab is active & email is known)
  const { status: syncStatus } = usePrometheusSingleSync(
    { email: resolvedEmail },
    !!resolvedEmail,
  );
  const currentHrStatus = syncStatus?.hrStatus;

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getContactPrometheusReview(entityId);
      setData(result);
    } catch (e) {
      setError('Не удалось загрузить данные из Prometheus');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [entityId]);

  // Loading state
  if (loading) {
    return (
      <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
        <PrometheusTabSkeleton />
      </div>
    );
  }

  // Network error
  if (error) {
    return (
      <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-lg bg-orange-500/20">
            <Flame size={18} className="text-orange-400" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">Prometheus</h3>
            <p className="text-xs text-white/50">Итоговое ревью обучения на платформе</p>
          </div>
        </div>
        <div className="text-center py-8">
          <AlertTriangle className="w-12 h-12 mx-auto mb-3 text-red-400/50" />
          <p className="text-sm text-white/40">{error}</p>
          <button
            onClick={fetchData}
            className="mt-3 flex items-center gap-2 mx-auto px-4 py-2 glass-light hover:bg-white/10 rounded-lg text-sm transition-colors text-white/70"
          >
            <RefreshCw className="w-4 h-4" />
            Повторить
          </button>
        </div>
      </div>
    );
  }

  // Not linked / not found
  if (data && (data.status === 'not_linked' || data.status === 'not_found' || data.status === 'error')) {
    return (
      <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-lg bg-orange-500/20">
            <Flame size={18} className="text-orange-400" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">Prometheus</h3>
            <p className="text-xs text-white/50">Итоговое ревью обучения на платформе</p>
          </div>
        </div>
        <div className="text-center py-8">
          <Flame className="w-12 h-12 mx-auto mb-3 text-orange-400/30" />
          <p className="text-sm text-white/40">
            {data.message || 'Не удалось найти кандидата в Prometheus'}
          </p>
          <p className="text-xs text-white/30 mt-1">
            Проверьте email контакта или связку с Prometheus.
          </p>
          <button
            onClick={fetchData}
            className="mt-3 flex items-center gap-2 mx-auto px-3 py-1.5 glass-light hover:bg-white/10 rounded-lg text-xs transition-colors text-white/60"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Обновить
          </button>
        </div>
      </div>
    );
  }

  // Success — render full review
  const review = data?.review as ContactPrometheusReview;
  const intern = data?.intern;
  const m = review.metrics;
  const flags = review.flags;

  return (
    <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-orange-500/20">
            <Flame size={18} className="text-orange-400" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">Prometheus</h3>
            <p className="text-xs text-white/50">Итоговое ревью обучения на платформе</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* HR status badge from sync */}
          {currentHrStatus && <PrometheusStatusBadge status={currentHrStatus} />}
          {/* Activity badges */}
          {flags.active ? (
            <span className="px-2 py-0.5 text-[10px] rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              Активен
            </span>
          ) : (
            <span className="px-2 py-0.5 text-[10px] rounded-full bg-white/10 text-white/50 border border-white/10">
              Неактивен
            </span>
          )}
          {flags.risk && (
            <span className="px-2 py-0.5 text-[10px] rounded-full bg-red-500/20 text-red-400 border border-red-500/30">
              Риск отсева
            </span>
          )}
          <button
            onClick={fetchData}
            className="p-1.5 hover:bg-dark-800/50 rounded-lg transition-colors text-white/40 hover:text-white/70"
            title="Обновить данные"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="space-y-4">
        {/* Overview metrics */}
        <div className="grid grid-cols-3 gap-3">
          <div className="glass-light rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-white/40 mb-1">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-xs">XP</span>
            </div>
            <p className="text-lg font-semibold text-white">{m.totalXP.toLocaleString()}</p>
          </div>
          <div className="glass-light rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-white/40 mb-1">
              <GitBranch className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-xs">Трейлов</span>
            </div>
            <p className="text-lg font-semibold text-white">{m.trailCount}</p>
          </div>
          <div className="glass-light rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-white/40 mb-1">
              <BookOpen className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-xs">Модулей</span>
            </div>
            <p className="text-lg font-semibold text-white">
              {m.completedModules}/{m.totalModules}
            </p>
          </div>
        </div>

        {/* Overall progress bar */}
        <div className="glass-light rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <span className="text-sm font-medium text-white">Общий прогресс</span>
            </div>
            <span className="text-sm font-semibold text-white">{m.overallCompletionPercent}%</span>
          </div>
          <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              className={clsx('h-full rounded-full transition-all', {
                'bg-emerald-400': m.overallCompletionPercent >= 80,
                'bg-amber-400': m.overallCompletionPercent >= 50 && m.overallCompletionPercent < 80,
                'bg-blue-400': m.overallCompletionPercent < 50,
              })}
              style={{ width: `${m.overallCompletionPercent}%` }}
            />
          </div>
          <p className="text-xs text-white/40 mt-1">
            {m.completedModules} из {m.totalModules} модулей по {m.trailCount} трейл(ам)
          </p>
        </div>

        {/* HR Review */}
        <div className="glass-light rounded-xl p-4">
          <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-cyan-400" />
            HR-ревью: {review.headline}
          </h4>

          {/* Bullets */}
          <ul className="space-y-1.5 mb-3">
            {review.bullets.map((bullet, i) => (
              <li key={i} className="text-sm text-white/60 flex items-start gap-2">
                <span className="text-cyan-400 flex-shrink-0 mt-0.5">-</span>
                <span>{bullet}</span>
              </li>
            ))}
          </ul>

          {/* Summary paragraph */}
          <p className="text-sm text-white/50 leading-relaxed">{review.summary}</p>

          {/* Top trails badges */}
          {flags.topTrails.length > 0 && (
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <span className="text-xs text-white/40">Сильные:</span>
              {flags.topTrails.map((name) => (
                <span
                  key={name}
                  className="px-2 py-0.5 text-[10px] rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                >
                  {name}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Trails list */}
        {review.trails.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-white/50 mb-3 flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-emerald-400" />
              Прогресс по трейлам ({review.trails.length})
            </h4>
            <div className="space-y-2">
              {review.trails.map((trail) => (
                <TrailCard key={trail.trailId || trail.trailName} trail={trail} />
              ))}
            </div>
          </div>
        )}

        {/* Intern info footer */}
        {intern && (
          <div className="pt-3 border-t border-white/5 flex items-center gap-4 text-[10px] text-white/30 flex-wrap">
            {intern.email && <span>Email: {intern.email}</span>}
            {intern.telegramUsername && <span>TG: @{intern.telegramUsername}</span>}
            {intern.createdAt && <span>На платформе с: {new Date(intern.createdAt).toLocaleDateString('ru-RU')}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
