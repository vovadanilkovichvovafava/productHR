import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Flame,
  Zap,
  AlertTriangle,
  GitBranch,
  RefreshCw,
  ChevronDown,
  BookOpen,
  Activity,
  Target,
  Users,
  TrendingUp,
  Shield,
  Star,
  Brain,
  FileText,
  Medal,
} from 'lucide-react';
import clsx from 'clsx';
import { getContactDetailedReview } from '@/services/api';
import type {
  DetailedReviewResponse,
  DetailedPrometheusReview,
  ContactPrometheusReview,
  ContactReviewTrail,
  CompetencyScore,
  Certificate,
} from '@/services/api';
import { usePrometheusSingleSync } from '@/hooks';

// ── HR Status badge ──

const HR_STATUS_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  'Обучается': { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30' },
  'Принят': { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  'Отклонен': { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30' },
};

function DetailedReviewStatusBadge({ status }: { status: string }) {
  const style = HR_STATUS_STYLES[status] || { bg: 'bg-white/10', text: 'text-white/60', border: 'border-white/10' };
  return (
    <span className={clsx('px-2 py-0.5 text-[10px] rounded-full border whitespace-nowrap', style.bg, style.text, style.border)}>
      {status}
    </span>
  );
}

// In-flight prefetch tracker — avoids duplicate concurrent requests
const prefetchInFlight = new Set<number>();

/** Prefetch review in background (called from ContactDetail on mount).
 *  The backend caches in DB, so this just warms the server-side cache. */
export function prefetchPrometheusReview(entityId: number): void {
  if (prefetchInFlight.has(entityId)) return;
  prefetchInFlight.add(entityId);
  getContactDetailedReview(entityId)
    .catch(() => {
      // silently fail on prefetch
    })
    .finally(() => {
      prefetchInFlight.delete(entityId);
    });
}

interface PrometheusDetailedReviewProps {
  entityId: number;
}

// ── Skeleton ──

function ReviewSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-orange-500/20">
          <Flame size={18} className="text-orange-400" />
        </div>
        <div>
          <div className="h-5 w-48 bg-white/10 rounded mb-1" />
          <div className="h-3 w-72 bg-white/10 rounded" />
        </div>
      </div>
      {/* Profile card */}
      <div className="glass-light rounded-xl p-4">
        <div className="h-5 w-64 bg-white/10 rounded mb-3" />
        <div className="space-y-2">
          <div className="h-4 w-full bg-white/10 rounded" />
          <div className="h-4 w-5/6 bg-white/10 rounded" />
          <div className="h-4 w-4/6 bg-white/10 rounded" />
        </div>
        <div className="flex gap-2 mt-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-6 w-24 bg-white/10 rounded-full" />
          ))}
        </div>
      </div>
      {/* Competencies */}
      <div className="grid grid-cols-2 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="glass-light rounded-lg p-3">
            <div className="h-3 w-20 bg-white/10 rounded mb-2" />
            <div className="h-6 w-12 bg-white/10 rounded mb-1" />
            <div className="h-2 w-full bg-white/10 rounded-full" />
          </div>
        ))}
      </div>
      {/* Trails */}
      <div className="space-y-2">
        {[1, 2].map((i) => (
          <div key={i} className="glass-light rounded-lg p-3">
            <div className="h-4 w-40 bg-white/10 rounded mb-2" />
            <div className="h-3 w-full bg-white/10 rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Competency Gauge ──

function CompetencyGauge({
  label,
  icon: Icon,
  data,
  color,
}: {
  label: string;
  icon: typeof Zap;
  data: CompetencyScore;
  color: string;
}) {
  const barColor =
    data.score >= 75
      ? 'bg-emerald-400'
      : data.score >= 50
        ? 'bg-amber-400'
        : data.score >= 25
          ? 'bg-blue-400'
          : 'bg-red-400';

  return (
    <div className="glass-light rounded-lg p-3">
      <div className="flex items-center gap-1.5 text-dark-400 mb-1.5">
        <Icon className={clsx('w-3.5 h-3.5', color)} />
        <span className="text-xs">{label}</span>
      </div>
      <div className="flex items-baseline gap-2 mb-1.5">
        <span className="text-lg font-bold">{data.score}</span>
        <span className="text-[10px] text-dark-400 uppercase tracking-wide">
          {data.label}
        </span>
      </div>
      <div className="w-full h-1.5 bg-dark-600/30 rounded-full overflow-hidden mb-1.5">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${data.score}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className={clsx('h-full rounded-full', barColor)}
        />
      </div>
      <p className="text-[10px] text-dark-400 leading-relaxed">{typeof data.detail === 'string' ? data.detail : ''}</p>
    </div>
  );
}

// ── Trail Card (enhanced) ──

function TrailDetailCard({
  trail,
  insight,
}: {
  trail: ContactReviewTrail;
  insight?: { verdict: string; relevantSkills: string[] };
}) {
  const [expanded, setExpanded] = useState(false);

  const pctColor =
    trail.completionPercent >= 80
      ? 'bg-emerald-400'
      : trail.completionPercent >= 50
        ? 'bg-amber-400'
        : 'bg-blue-400';

  return (
    <div className="glass-light rounded-lg p-3 overflow-hidden">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <GitBranch className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span className="text-sm font-medium truncate">{trail.trailName}</span>
            <ChevronDown
              className={clsx(
                'w-3.5 h-3.5 text-white/30 transition-transform flex-shrink-0',
                expanded && 'rotate-180',
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

      {/* AI insight (always visible if available) */}
      {insight && (
        <p className="text-xs text-white/50 mt-2 italic break-words">{insight.verdict}</p>
      )}

      {/* Expanded details */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-3 pt-3 border-t border-white/5 space-y-2">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="text-white/40">XP</div>
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
              {/* Skills from AI */}
              {insight && insight.relevantSkills.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap mt-1">
                  <span className="text-[10px] text-white/30">Навыки:</span>
                  {insight.relevantSkills.map((skill) => (
                    <span
                      key={skill}
                      className="text-[10px] px-1.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400 border border-cyan-500/20"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Certificate Card ──

function CertificateCard({ cert }: { cert: Certificate }) {
  const levelColors: Record<string, string> = {
    Senior: 'text-amber-400 bg-amber-500/15 border-amber-500/30',
    Middle: 'text-blue-400 bg-blue-500/15 border-blue-500/30',
    Junior: 'text-emerald-400 bg-emerald-500/15 border-emerald-500/30',
  };
  const style = levelColors[cert.level] || levelColors.Junior;

  return (
    <div className="glass-light rounded-lg p-3 flex items-center gap-3">
      <div className="p-2 rounded-lg bg-amber-500/15">
        <Medal className="w-4 h-4 text-amber-400" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white truncate">
          {cert.trail?.title || 'Сертификат'}
        </p>
        <p className="text-[10px] text-white/40">
          Выдан: {new Date(cert.issuedAt).toLocaleDateString('ru-RU')} | XP:{' '}
          {cert.totalXP}
        </p>
      </div>
      <span
        className={clsx(
          'px-2 py-0.5 text-[10px] rounded-full border font-medium',
          style,
        )}
      >
        {cert.level}
      </span>
    </div>
  );
}

// ── Readiness badge ──

function ReadinessBadge({ level }: { level: string }) {
  const config: Record<string, { label: string; color: string }> = {
    highly_ready: {
      label: 'Высокая готовность',
      color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    },
    ready: {
      label: 'Готов к интеграции',
      color: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    },
    developing: {
      label: 'В процессе развития',
      color: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    },
    not_ready: {
      label: 'Не готов',
      color: 'bg-red-500/20 text-red-400 border-red-500/30',
    },
  };
  const c = config[level] || config.not_ready;

  return (
    <span
      className={clsx(
        'px-2.5 py-1 text-xs rounded-full border font-medium',
        c.color,
      )}
    >
      {c.label}
    </span>
  );
}

// ── Main Component ──

export default function PrometheusDetailedReview({
  entityId,
}: PrometheusDetailedReviewProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<DetailedReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // 30-second status sync (uses email from loaded intern data)
  const resolvedEmail = data?.intern?.email || undefined;
  const { status: syncStatus } = usePrometheusSingleSync(
    { email: resolvedEmail },
    !!resolvedEmail && !loading,
  );
  const currentHrStatus = syncStatus?.hrStatus;

  const fetchData = async (forceRefresh = false) => {
    if (forceRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const result = await getContactDetailedReview(entityId, forceRefresh);
      setData(result);
    } catch {
      if (!forceRefresh) {
        setError('Не удалось загрузить данные из Prometheus');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [entityId]);

  // ── Loading ──
  if (loading) {
    return (
      <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
        <ReviewSkeleton />
      </div>
    );
  }

  // ── Error ──
  if (error) {
    return (
      <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
        <Header />
        <div className="text-center py-8">
          <AlertTriangle className="w-12 h-12 mx-auto mb-3 text-red-400/50" />
          <p className="text-sm text-white/40">{error}</p>
          <button
            onClick={() => fetchData()}
            className="mt-3 flex items-center gap-2 mx-auto px-4 py-2 glass-light hover:bg-white/10 rounded-lg text-sm transition-colors text-white/70"
          >
            <RefreshCw className="w-4 h-4" />
            Повторить
          </button>
        </div>
      </div>
    );
  }

  // ── Not linked / not found ──
  if (
    data &&
    (data.status === 'not_linked' ||
      data.status === 'not_found' ||
      data.status === 'error')
  ) {
    return (
      <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
        <Header />
        <div className="text-center py-8">
          <Flame className="w-12 h-12 mx-auto mb-3 text-orange-400/30" />
          <p className="text-sm text-white/40">
            {data.message || 'Не удалось найти кандидата в Prometheus'}
          </p>
          <p className="text-xs text-white/30 mt-1">
            Проверьте email контакта или связку с Prometheus.
          </p>
          <button
            onClick={() => fetchData()}
            className="mt-3 flex items-center gap-2 mx-auto px-3 py-1.5 glass-light hover:bg-white/10 rounded-lg text-xs transition-colors text-white/60"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Обновить
          </button>
        </div>
      </div>
    );
  }

  // ── Success ──
  const review = data?.review as ContactPrometheusReview;
  const detailed = data?.detailedReview as DetailedPrometheusReview;
  const intern = data?.intern;
  const achievements = data?.achievements;
  const m = review.metrics;
  const flags = review.flags;

  const certificates = achievements?.certificates || [];

  // Map trail insights by name for quick lookup
  const insightMap = new Map<string, { verdict: string; relevantSkills: string[] }>();
  if (detailed?.trailInsights) {
    for (const ti of detailed.trailInsights) {
      insightMap.set(ti.trailName, {
        verdict: ti.verdict,
        relevantSkills: ti.relevantSkills,
      });
    }
  }

  return (
    <div className="space-y-4 min-w-0">
      {/* ── Team Fit Recommendation (AI) — shown first for HR ── */}
      {detailed?.teamFitRecommendation && (
        <div className="glass rounded-xl p-4 sm:p-6">
          <h4 className="text-sm font-medium text-dark-400 mb-3 flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-400" />
            Рекомендация по интеграции в команду
          </h4>
          <div className="glass-light rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-3">
              <ReadinessBadge level={detailed.teamFitRecommendation.readinessLevel} />
            </div>

            {detailed.teamFitRecommendation.recommendedRoles.length > 0 && (
              <div>
                <span className="text-[10px] text-dark-400 uppercase tracking-wide">
                  Рекомендуемые роли
                </span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {detailed.teamFitRecommendation.recommendedRoles.map((role) => (
                    <span
                      key={role}
                      className="text-xs px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/20"
                    >
                      {role}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <p className="text-sm text-dark-300 leading-relaxed">
              {detailed.teamFitRecommendation.integrationAdvice}
            </p>

            {detailed.teamFitRecommendation.watchPoints.length > 0 && (
              <div>
                <span className="text-[10px] text-amber-400 uppercase tracking-wide font-medium">
                  На что обратить внимание
                </span>
                <ul className="mt-1 space-y-1">
                  {detailed.teamFitRecommendation.watchPoints.map((wp, i) => (
                    <li
                      key={i}
                      className="text-xs text-dark-400 flex items-start gap-1.5"
                    >
                      <AlertTriangle className="w-3 h-3 text-amber-400 flex-shrink-0 mt-0.5" />
                      <span>{wp}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main glass card */}
      <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-orange-500/20">
              <Flame size={18} className="text-orange-400" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">
                Prometheus — Детальное ревью
              </h3>
              <p className="text-xs text-white/50">
                AI-анализ обучения и готовности кандидата
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* HR status badge from sync */}
            {currentHrStatus && <DetailedReviewStatusBadge status={currentHrStatus} />}
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
          </div>
        </div>

        {/* ── Professional Profile (AI) ── */}
        {detailed?.professionalProfile && (
          <div className="bg-gradient-to-br from-cyan-500/10 to-blue-500/5 rounded-xl p-4 border border-cyan-500/15 mb-4">
            <div className="flex items-center gap-2 mb-2">
              <Brain className="w-4 h-4 text-cyan-400" />
              <h4 className="text-sm font-semibold text-white">
                {detailed.professionalProfile.title}
              </h4>
            </div>
            <p className="text-sm text-white/60 leading-relaxed mb-3">
              {detailed.professionalProfile.summary}
            </p>

            {/* Strengths + growth */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {detailed.professionalProfile.keyStrengths.length > 0 && (
                <div>
                  <span className="text-[10px] text-emerald-400 uppercase tracking-wide font-medium">
                    Сильные стороны
                  </span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {detailed.professionalProfile.keyStrengths.map((s) => (
                      <span
                        key={s}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {detailed.professionalProfile.growthAreas.length > 0 && (
                <div>
                  <span className="text-[10px] text-amber-400 uppercase tracking-wide font-medium">
                    Зоны роста
                  </span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {detailed.professionalProfile.growthAreas.map((g) => (
                      <span
                        key={g}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/20"
                      >
                        {g}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Key Metrics ── */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="glass-light rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-white/40 mb-1">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-xs">XP</span>
            </div>
            <p className="text-lg font-semibold text-white">
              {m.totalXP.toLocaleString()}
            </p>
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

        {/* ── Overall Progress ── */}
        <div className="glass-light rounded-xl p-4 mb-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <span className="text-sm font-medium text-white">Общий прогресс</span>
            </div>
            <span className="text-sm font-semibold text-white">
              {m.overallCompletionPercent}%
            </span>
          </div>
          <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${m.overallCompletionPercent}%` }}
              transition={{ duration: 1, ease: 'easeOut' }}
              className={clsx('h-full rounded-full', {
                'bg-emerald-400': m.overallCompletionPercent >= 80,
                'bg-amber-400':
                  m.overallCompletionPercent >= 50 &&
                  m.overallCompletionPercent < 80,
                'bg-blue-400': m.overallCompletionPercent < 50,
              })}
            />
          </div>
          <p className="text-xs text-white/40 mt-1">
            {m.completedModules} из {m.totalModules} модулей по {m.trailCount}{' '}
            трейл(ам)
          </p>
        </div>

        {/* ── Competency Analysis (AI) ── */}
        {detailed?.competencyAnalysis && (
          <div className="mb-4">
            <h4 className="text-sm font-medium text-dark-400 mb-3 flex items-center gap-2">
              <Target className="w-4 h-4 text-purple-400" />
              Компетенции
            </h4>
            <div className="grid grid-cols-2 gap-3">
              <CompetencyGauge
                label="Техническая готовность"
                icon={Shield}
                data={detailed.competencyAnalysis.technicalReadiness}
                color="text-blue-400"
              />
              <CompetencyGauge
                label="Обучаемость"
                icon={TrendingUp}
                data={detailed.competencyAnalysis.learningAbility}
                color="text-emerald-400"
              />
              <CompetencyGauge
                label="Стабильность"
                icon={Activity}
                data={detailed.competencyAnalysis.consistency}
                color="text-amber-400"
              />
              <CompetencyGauge
                label="Вовлечённость"
                icon={Star}
                data={detailed.competencyAnalysis.engagement}
                color="text-purple-400"
              />
            </div>
          </div>
        )}
      </div>

      {/* ── Trail Progress ── */}
      {review.trails.length > 0 && (
        <div className="glass rounded-xl border border-white/10 p-4 sm:p-6 overflow-hidden">
          <h4 className="text-sm font-medium text-white/50 mb-3 flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-emerald-400" />
            Прогресс по трейлам ({review.trails.length})
          </h4>
          <div className="space-y-2">
            {review.trails.map((trail) => (
              <TrailDetailCard
                key={trail.trailId || trail.trailName}
                trail={trail}
                insight={insightMap.get(trail.trailName)}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Certificates ── */}
      {certificates.length > 0 && (
        <div className="glass rounded-xl border border-white/10 p-4 sm:p-6 overflow-hidden">
          <h4 className="text-sm font-medium text-white/50 mb-3 flex items-center gap-2">
            <Medal className="w-4 h-4 text-amber-400" />
            Сертификаты ({certificates.length})
          </h4>
          <div className="space-y-2">
            {certificates.map((cert) => (
              <CertificateCard key={cert.id} cert={cert} />
            ))}
          </div>
        </div>
      )}

      {/* ── Overall Verdict (AI) ── */}
      {detailed?.overallVerdict && (
        <div className="glass rounded-xl border border-white/10 p-4 sm:p-6">
          <h4 className="text-sm font-medium text-white/50 mb-2 flex items-center gap-2">
            <FileText className="w-4 h-4 text-cyan-400" />
            Итоговое заключение
          </h4>
          <p className="text-sm text-white/60 leading-relaxed">
            {detailed.overallVerdict}
          </p>
        </div>
      )}

      {/* ── Footer ── */}
      {intern && (
        <div className="flex items-center gap-4 text-[10px] text-white/30 flex-wrap px-1">
          {intern.email && <span>Email: {intern.email}</span>}
          {intern.telegramUsername && <span>TG: @{intern.telegramUsername}</span>}
          {intern.createdAt && (
            <span>
              На платформе с:{' '}
              {new Date(intern.createdAt).toLocaleDateString('ru-RU')}
            </span>
          )}
          <span className="flex items-center gap-1">
            <Brain className="w-3 h-3" />
            AI-ревью
          </span>
          <button
            onClick={() => fetchData(true)}
            disabled={refreshing}
            className="flex items-center gap-1 text-white/40 hover:text-white/70 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={clsx('w-3 h-3', refreshing && 'animate-spin')} />
            Перегенерировать
          </button>
        </div>
      )}
    </div>
  );
}

// ── Header (reusable) ──

function Header() {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className="p-2 rounded-lg bg-orange-500/20">
        <Flame size={18} className="text-orange-400" />
      </div>
      <div>
        <h3 className="text-base font-semibold text-white">
          Prometheus — Детальное ревью
        </h3>
        <p className="text-xs text-white/50">
          AI-анализ обучения и готовности кандидата
        </p>
      </div>
    </div>
  );
}
