import { useState, useMemo, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft,
  BarChart3,
  Mail,
  AtSign,
  User,
  Calendar,
  GitBranch,
  ClipboardCheck,
  ChevronDown,
  CheckCircle2,
  Zap,
  Star,
  Award,
  Loader2,
  RefreshCw,
  AlertTriangle,
  BookOpen,
  FileCheck,
  TrendingUp,
  Clock,
  ExternalLink,
  Flame,
  UserPlus,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import clsx from 'clsx';
import { getStudentAchievements, getPrometheusInterns, getPrometheusAnalytics, getEntities, exportInternToContact } from '@/services/api';
import type { StudentTrailProgress, StudentModuleStatus } from '@/services/api';
import { usePrometheusSingleSync } from '@/hooks';
import { formatDate } from '@/utils';

// ── Status badge helper ──

const HR_STATUS_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  'Обучается': { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30' },
  'Принят': { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  'Отклонен': { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30' },
};

function InternStatusBadge({ status }: { status: string }) {
  const style = HR_STATUS_STYLES[status] || { bg: 'bg-white/10', text: 'text-white/60', border: 'border-white/10' };
  return (
    <span className={clsx('px-2 py-0.5 text-xs rounded-full border whitespace-nowrap', style.bg, style.text, style.border)}>
      {status}
    </span>
  );
}

// ── Constants ──

const SUBMISSION_COLORS = ['#10b981', '#f59e0b', '#8b5cf6', '#ef4444'];
const MODULE_TYPE_LABELS: Record<string, string> = {
  THEORY: 'Теория',
  PRACTICE: 'Практика',
  PROJECT: 'Проект',
};

const MODULE_TYPE_COLORS: Record<string, string> = {
  THEORY: 'bg-blue-500/20 text-blue-400',
  PRACTICE: 'bg-amber-500/20 text-amber-400',
  PROJECT: 'bg-purple-500/20 text-purple-400',
};

const ROLE_LABELS: Record<string, string> = {
  STUDENT: 'Студент',
  TEACHER: 'Преподаватель',
  HR: 'HR',
  CO_ADMIN: 'Со-админ',
  ADMIN: 'Администратор',
};

const PROMETHEUS_URL = (import.meta.env.VITE_PROMETHEUS_URL || '').replace(/\/$/, '');

function getSubmissionUrl(submissionId: string): string | null {
  if (!PROMETHEUS_URL) return null;
  return `${PROMETHEUS_URL}/admin/submissions/${submissionId}`;
}

// ── Shared helper components ──

function getAvatarInitials(name: string) {
  return name
    .split(' ')
    .slice(0, 2)
    .map(n => n[0])
    .join('')
    .toUpperCase();
}

function MetaCard({
  icon: Icon,
  label,
  value,
  valueColor,
}: {
  icon: typeof Mail;
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <div className="glass-light rounded-xl p-3">
      <div className="flex items-center gap-2 text-white/40 mb-1">
        <Icon className="w-3.5 h-3.5" />
        <span className="text-xs">{label}</span>
      </div>
      <p className={clsx('text-sm font-medium truncate', valueColor)} title={value}>{value}</p>
    </div>
  );
}

function CollapsibleSection({
  title,
  icon: Icon,
  children,
  defaultOpen = false,
  badge,
}: {
  title: string;
  icon: typeof BookOpen;
  children: React.ReactNode;
  defaultOpen?: boolean;
  badge?: string | number;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="glass-light rounded-xl overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 hover:bg-dark-800/50 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <Icon className="w-5 h-5 text-amber-400 flex-shrink-0" />
          <span className="font-medium text-sm">{title}</span>
          {badge !== undefined && (
            <span className="px-2 py-0.5 text-xs rounded-full bg-white/10 text-white/60">
              {badge}
            </span>
          )}
        </div>
        <ChevronDown
          className={`w-4 h-4 text-white/40 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 border-t border-white/5">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
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

function SubmissionBadge({
  label,
  count,
  color,
  icon: Icon,
}: {
  label: string;
  count: number;
  color: string;
  icon: typeof CheckCircle2;
}) {
  return (
    <div className={clsx('flex items-center gap-2 px-3 py-2 rounded-lg', color)}>
      <Icon className="w-4 h-4" />
      <span className="text-sm font-medium">{count}</span>
      <span className="text-xs opacity-80">{label}</span>
    </div>
  );
}

function TrailProgressCard({
  trail,
  modules,
  submissions,
}: {
  trail: StudentTrailProgress;
  modules?: StudentModuleStatus[];
  submissions?: { approved: number; pending: number; revision: number; total: number };
}) {
  const [showModules, setShowModules] = useState(false);
  const hasModules = modules && modules.length > 0;

  return (
    <div className="p-3 glass-light rounded-lg">
      <button
        onClick={() => hasModules && setShowModules(!showModules)}
        className={clsx('w-full text-left', hasModules && 'cursor-pointer')}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <GitBranch className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span className="text-sm font-medium truncate">{trail.trailTitle}</span>
            {hasModules && (
              <ChevronDown
                className={clsx(
                  'w-3.5 h-3.5 text-white/30 transition-transform flex-shrink-0',
                  showModules ? 'rotate-180' : '',
                )}
              />
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="text-xs text-white/40">
              {trail.completedModules}/{trail.totalModules}
            </span>
            <span className="text-xs text-white/50">{trail.completionPercent}%</span>
          </div>
        </div>
      </button>
      <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all', {
            'bg-emerald-400': trail.completionPercent >= 80,
            'bg-amber-400': trail.completionPercent >= 50 && trail.completionPercent < 80,
            'bg-blue-400': trail.completionPercent < 50,
          })}
          style={{ width: `${trail.completionPercent}%` }}
        />
      </div>
      <div className="flex items-center gap-3 mt-1.5 text-[10px] text-white/30 flex-wrap">
        <span className="flex items-center gap-1">
          <Calendar className="w-3 h-3" />
          Начало: {formatDate(trail.enrolledAt, 'short')}
        </span>
        {trail.completedAt && (
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            Завершён: {formatDate(trail.completedAt, 'short')}
          </span>
        )}
      </div>

      {/* Submission badges */}
      {submissions && submissions.total > 0 && (
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          {submissions.approved > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400">
              Одобрено: {submissions.approved}
            </span>
          )}
          {submissions.pending > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400">
              На проверке: {submissions.pending}
            </span>
          )}
          {submissions.revision > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/20 text-purple-400">
              На доработке: {submissions.revision}
            </span>
          )}
        </div>
      )}

      {/* Expandable module list */}
      <AnimatePresence>
        {showModules && hasModules && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-2 pt-2 border-t border-white/5 space-y-1.5">
              <p className="text-[10px] text-white/40 font-medium uppercase tracking-wider">Модули:</p>
              {modules
                .sort((a, b) => a.order - b.order)
                .map((mod) => (
                  <div
                    key={mod.id}
                    className="p-1.5 rounded-md bg-white/[0.03] space-y-1"
                  >
                    <div className="flex items-center gap-2">
                      {mod.status === 'COMPLETED' ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                      ) : mod.status === 'IN_PROGRESS' ? (
                        <Clock className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                      ) : (
                        <div className="w-3.5 h-3.5 rounded-full border border-white/20 flex-shrink-0" />
                      )}
                      <span className="text-xs text-white/60 truncate flex-1">{mod.title}</span>
                      <span
                        className={clsx(
                          'text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0',
                          MODULE_TYPE_COLORS[mod.type] || 'bg-white/10 text-white/50',
                        )}
                      >
                        {MODULE_TYPE_LABELS[mod.type] || mod.type}
                      </span>
                      <span
                        className={clsx('text-[10px] font-medium flex-shrink-0', {
                          'text-emerald-400': mod.status === 'COMPLETED',
                          'text-blue-400': mod.status === 'IN_PROGRESS',
                          'text-white/30': mod.status === 'NOT_STARTED',
                        })}
                      >
                        {mod.status === 'COMPLETED' ? 'Завершён' : mod.status === 'IN_PROGRESS' ? 'В процессе' : 'Не начат'}
                      </span>
                      {mod.submissionId && (() => {
                        const url = getSubmissionUrl(mod.submissionId);
                        return url ? (
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors flex-shrink-0"
                            title="Открыть работу"
                          >
                            <FileCheck className="w-3 h-3" />
                            <ExternalLink className="w-2.5 h-2.5" />
                          </a>
                        ) : (
                          <span className="text-[10px] px-1 py-0.5 rounded bg-emerald-500/10 text-emerald-400 flex-shrink-0" title="Работа сдана">
                            <FileCheck className="w-3 h-3 inline" />
                          </span>
                        );
                      })()}
                    </div>
                    {(mod.startedAt || mod.completedAt) && (
                      <div className="flex items-center gap-3 ml-[22px] text-[10px] text-white/30">
                        {mod.startedAt && (
                          <span className="flex items-center gap-1">
                            <Clock className="w-2.5 h-2.5" />
                            Начало: {formatDate(mod.startedAt, 'short')}
                          </span>
                        )}
                        {mod.completedAt && (
                          <span className="flex items-center gap-1">
                            <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" />
                            Завершён: {formatDate(mod.completedAt, 'short')}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Main page component ──

export default function InternStatsPage() {
  const { internId } = useParams<{ internId: string }>();
  const navigate = useNavigate();

  // Student achievements data (main data source)
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['student-achievements', internId],
    queryFn: () => getStudentAchievements(internId!),
    enabled: !!internId,
    staleTime: 60000,
    retry: 1,
  });

  // 30-second Prometheus status sync for this single intern
  const studentEmail = data?.student?.email;
  const { status: promSyncStatus } = usePrometheusSingleSync(
    { email: studentEmail, internId: internId },
    !!internId && !isLoading,
  );
  const currentHrStatus = promSyncStatus?.hrStatus;

  // Pull telegram username from cached interns list
  const { data: interns } = useQuery({
    queryKey: ['prometheus-interns'],
    queryFn: getPrometheusInterns,
    staleTime: 300000,
    retry: 0,
  });
  const internFromList = interns?.find(i => i.id === internId);

  // Fetch analytics to get module-level data per student
  const { data: analyticsData } = useQuery({
    queryKey: ['prometheus-analytics', 'all', '90'],
    queryFn: () => getPrometheusAnalytics('all', '90'),
    staleTime: 120000,
    retry: 0,
  });

  // Build a map: trailId -> { modules, submissions } for this student from analytics
  const studentTrailModules = useMemo(() => {
    if (!analyticsData?.studentsByTrail || !internId) return new Map<string, { modules: StudentModuleStatus[]; submissions: { approved: number; pending: number; revision: number; total: number } }>();
    const map = new Map<string, { modules: StudentModuleStatus[]; submissions: { approved: number; pending: number; revision: number; total: number } }>();
    analyticsData.studentsByTrail.forEach(trailItem => {
      const student = trailItem.students.find(s => s.id === internId);
      if (student) {
        map.set(trailItem.trailId, {
          modules: student.modules,
          submissions: student.submissions,
        });
      }
    });
    return map;
  }, [analyticsData, internId]);

  // Chart data: submission stats
  const submissionChartData = useMemo(() => {
    if (!data) return [];
    const { submissionStats: ss } = data;
    return [
      { name: 'Одобрено', value: ss.approved, fill: SUBMISSION_COLORS[0] },
      { name: 'На проверке', value: ss.pending, fill: SUBMISSION_COLORS[1] },
      { name: 'На доработке', value: ss.revision, fill: SUBMISSION_COLORS[2] },
      { name: 'Отклонено', value: ss.failed, fill: SUBMISSION_COLORS[3] },
    ].filter(d => d.value > 0);
  }, [data]);

  // Chart data: trail completion aggregated
  const trailCompletion = useMemo(() => {
    if (!data || data.trailProgress.length === 0) return null;
    const totalCompleted = data.trailProgress.reduce((sum, t) => sum + t.completedModules, 0);
    const totalModules = data.trailProgress.reduce((sum, t) => sum + t.totalModules, 0);
    return { completed: totalCompleted, total: totalModules, percent: totalModules > 0 ? Math.round((totalCompleted / totalModules) * 100) : 0 };
  }, [data]);

  // Collect all modules with submissions across all trails
  const allSubmissions = useMemo(() => {
    if (!data || !studentTrailModules.size) return [];
    const items: Array<{
      trailTitle: string;
      moduleTitle: string;
      moduleType: string;
      moduleStatus: string;
      submissionId: string;
      startedAt?: string | null;
      completedAt?: string | null;
      updatedAt?: string | null;
    }> = [];

    studentTrailModules.forEach((trailData, trailId) => {
      const trail = data.trailProgress.find(t => t.trailId === trailId);
      trailData.modules.forEach(mod => {
        if (mod.submissionId) {
          items.push({
            trailTitle: trail?.trailTitle || '',
            moduleTitle: mod.title,
            moduleType: mod.type,
            moduleStatus: mod.status,
            submissionId: mod.submissionId,
            startedAt: mod.startedAt,
            completedAt: mod.completedAt,
            updatedAt: mod.updatedAt,
          });
        }
      });
    });

    return items;
  }, [data, studentTrailModules]);

  const [showSubmissions, setShowSubmissions] = useState(false);

  // Try to find a matching contact (entity) by email for "Open in contact" link
  const [linkedContactId, setLinkedContactId] = useState<number | null>(null);
  useEffect(() => {
    if (!data?.student?.email) return;
    let cancelled = false;
    getEntities({ search: data.student.email, limit: 1 })
      .then((entities) => {
        if (!cancelled && entities.length > 0) {
          setLinkedContactId(entities[0].id);
        }
      })
      .catch(() => { /* ignore — link just won't show */ });
    return () => { cancelled = true; };
  }, [data?.student?.email]);

  // Update linkedContactId from sync results (auto-export on "Принят")
  useEffect(() => {
    if (promSyncStatus?.contactId && !linkedContactId) {
      setLinkedContactId(promSyncStatus.contactId);
    }
  }, [promSyncStatus?.contactId, linkedContactId]);

  // Export to contacts state
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExportToContact = useCallback(async () => {
    if (!internId || exportLoading) return;
    setExportLoading(true);
    setExportError(null);
    try {
      const result = await exportInternToContact(internId);
      if (result.ok && result.contact_id) {
        setLinkedContactId(result.contact_id);
      } else {
        setExportError(result.error || 'Не удалось экспортировать');
      }
    } catch {
      setExportError('Ошибка сети при экспорте');
    } finally {
      setExportLoading(false);
    }
  }, [internId, exportLoading]);

  // Loading state
  if (isLoading) {
    return (
      <div className="h-full flex flex-col">
        <div className="p-4 border-b border-white/10">
          <button onClick={() => navigate('/interns')} className="flex items-center gap-2 text-white/60 hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
            <span className="text-sm">Назад к списку</span>
          </button>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-white/40">
            <Loader2 className="w-12 h-12 mx-auto mb-4 animate-spin opacity-50" />
            <h3 className="text-lg font-medium mb-2">Загрузка статистики...</h3>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (isError || !data) {
    return (
      <div className="h-full flex flex-col">
        <div className="p-4 border-b border-white/10">
          <button onClick={() => navigate('/interns')} className="flex items-center gap-2 text-white/60 hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
            <span className="text-sm">Назад к списку</span>
          </button>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-white/40">
            <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-red-400/60" />
            <h3 className="text-lg font-medium mb-2 text-red-400/80">
              {(error as Error)?.message?.includes('404') ? 'Студент не найден' : 'Ошибка загрузки'}
            </h3>
            <p className="text-sm mb-4">{(error as Error)?.message || 'Не удалось загрузить данные'}</p>
            <button onClick={() => refetch()} className="flex items-center gap-2 mx-auto px-4 py-2 glass-button rounded-lg text-sm transition-colors">
              <RefreshCw className="w-4 h-4" />
              Попробовать снова
            </button>
          </div>
        </div>
      </div>
    );
  }

  const { student, submissionStats, trailProgress, certificates } = data;

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-white/10">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/interns')} className="p-2 hover:bg-dark-800/50 rounded-lg transition-colors">
            <ArrowLeft className="w-5 h-5 text-white/60" />
          </button>
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400 font-medium text-sm flex-shrink-0">
              {getAvatarInitials(student.name)}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                <h1 className="text-lg font-bold truncate">Статистика</h1>
                {currentHrStatus && <InternStatusBadge status={currentHrStatus} />}
              </div>
              <p className="text-sm text-white/50 truncate">{student.name}</p>
            </div>
          </div>
          {linkedContactId ? (
            <button
              onClick={() => navigate(`/all-candidates?entity=${linkedContactId}`)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-500/20 hover:bg-orange-500/30 text-orange-400 border border-orange-500/30 rounded-lg text-xs font-medium transition-colors flex-shrink-0"
              title="Открыть Prometheus в карточке контакта"
            >
              <Flame className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Prometheus в контакте</span>
              <span className="sm:hidden">Контакт</span>
            </button>
          ) : (
            <button
              onClick={handleExportToContact}
              disabled={exportLoading}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex-shrink-0 border',
                exportLoading
                  ? 'glass-light text-white/30 border-white/10 cursor-wait'
                  : 'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border-emerald-500/30'
              )}
              title="Экспортировать кандидата в контакты"
            >
              {exportLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <UserPlus className="w-3.5 h-3.5" />
              )}
              <span className="hidden sm:inline">
                {exportLoading ? 'Экспорт...' : 'В контакты'}
              </span>
              <span className="sm:hidden">
                {exportLoading ? '...' : 'Контакт'}
              </span>
            </button>
          )}
        </div>
      </div>

      {/* Export error banner */}
      {exportError && (
        <div className="mx-4 mt-2 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2 text-xs text-red-400">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>{exportError}</span>
          <button onClick={() => setExportError(null)} className="ml-auto text-white/40 hover:text-white/70">&times;</button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 pb-7 space-y-6">
        {/* Personal data */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <h3 className="text-sm font-medium text-white/50 mb-3">Личные данные</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetaCard icon={User} label="ФИО" value={student.name} />
            <MetaCard icon={Mail} label="Email" value={student.email || '—'} />
            <MetaCard icon={AtSign} label="Telegram" value={internFromList?.telegramUsername || '—'} />
            <MetaCard icon={User} label="Роль" value={ROLE_LABELS[student.role] || student.role} />
            <MetaCard icon={Calendar} label="Регистрация" value={formatDate(student.registeredAt, 'medium')} />
            <MetaCard icon={Calendar} label="Последняя активность" value={formatDate(student.lastActiveAt, 'medium')} />
            <MetaCard
              icon={AlertTriangle}
              label="Дней без активности"
              value={`${student.daysSinceActive} дн.`}
              valueColor={
                student.daysSinceActive <= 3 ? 'text-emerald-400' :
                student.daysSinceActive <= 7 ? 'text-amber-400' :
                'text-red-400'
              }
            />
            <MetaCard icon={Star} label="Позиция в рейтинге" value={`#${student.leaderboardRank}`} />
          </div>
        </motion.div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Submission Stats Chart */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-light rounded-xl p-4">
            <h3 className="text-sm font-medium text-white/70 mb-3 text-center">Статистика работ</h3>
            {submissionChartData.length > 0 ? (
              <>
                <div className="relative h-[180px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={submissionChartData} cx="50%" cy="50%" innerRadius={55} outerRadius={75} paddingAngle={3} dataKey="value" stroke="none">
                        {submissionChartData.map((entry, index) => (
                          <Cell key={index} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip content={<ChartTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <DonutCenterLabel value={String(submissionStats.total)} label="всего" />
                </div>
                <div className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1">
                  {submissionChartData.map((item, index) => (
                    <div key={index} className="flex items-center gap-1.5 text-xs text-white/60">
                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.fill }} />
                      <span>{item.name}: {item.value}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="h-[180px] flex items-center justify-center text-white/30 text-sm">Нет работ</div>
            )}
          </motion.div>

          {/* Trail Completion Chart */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass-light rounded-xl p-4">
            <h3 className="text-sm font-medium text-white/70 mb-3 text-center">Прохождение трейлов</h3>
            {trailCompletion ? (
              <>
                <div className="relative h-[180px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={[
                          { name: 'Завершено', value: trailCompletion.completed, fill: '#10b981' },
                          { name: 'Осталось', value: trailCompletion.total - trailCompletion.completed, fill: '#1f2937' },
                        ]}
                        cx="50%" cy="50%" innerRadius={55} outerRadius={75} paddingAngle={0} dataKey="value" stroke="none" startAngle={90} endAngle={-270}
                      >
                        <Cell fill="#10b981" />
                        <Cell fill="#1f2937" />
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <DonutCenterLabel value={`${trailCompletion.percent}%`} label="модулей" />
                </div>
                <div className="mt-3 flex justify-center gap-4">
                  <div className="flex items-center gap-1.5 text-xs text-white/60">
                    <BookOpen className="w-3.5 h-3.5 text-emerald-400" />
                    <span>{trailCompletion.completed} из {trailCompletion.total} модулей</span>
                  </div>
                </div>
              </>
            ) : (
              <div className="h-[180px] flex items-center justify-center text-white/30 text-sm">Нет трейлов</div>
            )}
          </motion.div>
        </div>

        {/* Stats cards */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
          <h3 className="text-sm font-medium text-white/50 mb-3">Показатели</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="glass-light rounded-xl p-3">
              <div className="flex items-center gap-2 text-white/50 mb-1">
                <Zap className="w-4 h-4 text-amber-400" />
                <span className="text-xs">Опыт (XP)</span>
              </div>
              <p className="text-xl font-bold">{student.totalXP}</p>
            </div>
            <div className="glass-light rounded-xl p-3">
              <div className="flex items-center gap-2 text-white/50 mb-1">
                <BookOpen className="w-4 h-4 text-blue-400" />
                <span className="text-xs">Модулей пройдено</span>
              </div>
              <p className="text-xl font-bold">{student.modulesCompleted}</p>
            </div>
            <div className="glass-light rounded-xl p-3">
              <div className="flex items-center gap-2 text-white/50 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span className="text-xs">Работ одобрено</span>
              </div>
              <p className="text-xl font-bold">{submissionStats.approved}</p>
            </div>
            <div className="glass-light rounded-xl p-3">
              <div className="flex items-center gap-2 text-white/50 mb-1">
                <TrendingUp className="w-4 h-4 text-purple-400" />
                <span className="text-xs">Всего работ</span>
              </div>
              <p className="text-xl font-bold">{submissionStats.total}</p>
            </div>
          </div>
        </motion.div>

        {/* Submission status breakdown */}
        {submissionStats.total > 0 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <h3 className="text-sm font-medium text-white/50 mb-3">Статус работ</h3>
            <div className="glass-light rounded-xl p-4">
              <div className="flex items-center gap-3 flex-wrap">
                <SubmissionBadge label="Одобрено" count={submissionStats.approved} color="bg-emerald-500/20 text-emerald-400" icon={CheckCircle2} />
                <SubmissionBadge label="На проверке" count={submissionStats.pending} color="bg-amber-500/20 text-amber-400" icon={FileCheck} />
                <SubmissionBadge label="На доработке" count={submissionStats.revision} color="bg-purple-500/20 text-purple-400" icon={ClipboardCheck} />
                {submissionStats.failed > 0 && (
                  <SubmissionBadge label="Отклонено" count={submissionStats.failed} color="bg-red-500/20 text-red-400" icon={AlertTriangle} />
                )}
              </div>
              <div className="mt-3">
                <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden flex">
                  {submissionStats.approved > 0 && (
                    <div className="h-full bg-emerald-400" style={{ width: `${(submissionStats.approved / submissionStats.total) * 100}%` }} />
                  )}
                  {submissionStats.pending > 0 && (
                    <div className="h-full bg-amber-400" style={{ width: `${(submissionStats.pending / submissionStats.total) * 100}%` }} />
                  )}
                  {submissionStats.revision > 0 && (
                    <div className="h-full bg-purple-400" style={{ width: `${(submissionStats.revision / submissionStats.total) * 100}%` }} />
                  )}
                  {submissionStats.failed > 0 && (
                    <div className="h-full bg-red-400" style={{ width: `${(submissionStats.failed / submissionStats.total) * 100}%` }} />
                  )}
                </div>
              </div>

              {/* Expandable list of individual submissions */}
              {allSubmissions.length > 0 && (
                <div className="mt-4 pt-3 border-t border-white/5">
                  <button
                    onClick={() => setShowSubmissions(!showSubmissions)}
                    className="flex items-center gap-2 text-xs text-white/50 hover:text-white/80 transition-colors"
                  >
                    <FileCheck className="w-3.5 h-3.5" />
                    <span>Показать работы ({allSubmissions.length})</span>
                    <ChevronDown
                      className={clsx(
                        'w-3.5 h-3.5 transition-transform',
                        showSubmissions ? 'rotate-180' : '',
                      )}
                    />
                  </button>
                  <AnimatePresence>
                    {showSubmissions && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="mt-2 space-y-1.5">
                          {allSubmissions.map((sub) => {
                            const url = getSubmissionUrl(sub.submissionId);
                            const hasTimings = sub.startedAt || sub.completedAt || sub.updatedAt;
                            return (
                              <div
                                key={sub.submissionId}
                                className={clsx(
                                  'p-2 rounded-md bg-white/[0.03] space-y-1',
                                  url && 'hover:bg-white/[0.06] transition-colors',
                                )}
                              >
                                <div className="flex items-center gap-2">
                                  {sub.moduleStatus === 'COMPLETED' ? (
                                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                                  ) : sub.moduleStatus === 'IN_PROGRESS' ? (
                                    <Clock className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                                  ) : (
                                    <div className="w-3.5 h-3.5 rounded-full border border-white/20 flex-shrink-0" />
                                  )}
                                  <div className="flex-1 min-w-0">
                                    <span className="text-xs text-white/70 truncate block">{sub.moduleTitle}</span>
                                    <span className="text-[10px] text-white/30 truncate block">{sub.trailTitle}</span>
                                  </div>
                                  <span
                                    className={clsx(
                                      'text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0',
                                      MODULE_TYPE_COLORS[sub.moduleType] || 'bg-white/10 text-white/50',
                                    )}
                                  >
                                    {MODULE_TYPE_LABELS[sub.moduleType] || sub.moduleType}
                                  </span>
                                  {url ? (
                                    <a
                                      href={url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors flex-shrink-0"
                                      title="Открыть работу"
                                    >
                                      <ExternalLink className="w-3 h-3" />
                                      <span>Открыть</span>
                                    </a>
                                  ) : (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 flex-shrink-0" title="Работа сдана">
                                      <FileCheck className="w-3 h-3 inline" />
                                    </span>
                                  )}
                                </div>
                                {hasTimings && (
                                  <div className="flex items-center gap-3 ml-[22px] text-[10px] text-white/30">
                                    {sub.startedAt && (
                                      <span className="flex items-center gap-1">
                                        <Clock className="w-2.5 h-2.5" />
                                        Начало: {formatDate(sub.startedAt, 'short')}
                                      </span>
                                    )}
                                    {sub.completedAt && (
                                      <span className="flex items-center gap-1">
                                        <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" />
                                        Завершено: {formatDate(sub.completedAt, 'short')}
                                      </span>
                                    )}
                                    {sub.updatedAt && (
                                      <span className="flex items-center gap-1">
                                        <Calendar className="w-2.5 h-2.5" />
                                        Изменено: {formatDate(sub.updatedAt, 'short')}
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* Collapsible sections */}
        <div className="space-y-3">
          {/* Trail Progress */}
          {trailProgress.length > 0 && (
            <CollapsibleSection
              title="Прогресс по трейлам"
              icon={GitBranch}
              badge={trailProgress.length}
              defaultOpen
            >
              <div className="mt-3 space-y-2">
                {trailProgress.map(trail => {
                  const trailData = studentTrailModules.get(trail.trailId);
                  return (
                    <TrailProgressCard
                      key={trail.trailId}
                      trail={trail}
                      modules={trailData?.modules}
                      submissions={trailData?.submissions}
                    />
                  );
                })}
              </div>
            </CollapsibleSection>
          )}

          {/* Certificates */}
          {certificates.length > 0 && (
            <CollapsibleSection
              title="Сертификаты"
              icon={Award}
              badge={certificates.length}
            >
              <div className="mt-3 space-y-2">
                {certificates.map(cert => (
                  <div key={cert.id} className="p-3 glass-light rounded-lg flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ backgroundColor: cert.trail.color ? `${cert.trail.color}20` : 'rgba(255,255,255,0.1)' }}
                    >
                      <Award className="w-5 h-5" style={{ color: cert.trail.color || '#f59e0b' }} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium truncate">{cert.trail.title}</span>
                        <span className={clsx('text-[10px] px-1.5 py-0.5 rounded-full', {
                          'bg-emerald-500/20 text-emerald-400': cert.level === 'Senior',
                          'bg-blue-500/20 text-blue-400': cert.level === 'Middle',
                          'bg-gray-500/20 text-gray-400': cert.level === 'Junior',
                        })}>
                          {cert.level}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-[10px] text-white/40">
                        <span className="flex items-center gap-1">
                          <FileCheck className="w-3 h-3" />
                          Код: {cert.code}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {formatDate(cert.issuedAt, 'short')}
                        </span>
                        <span className="flex items-center gap-1">
                          <Zap className="w-3 h-3" />
                          {cert.totalXP} XP
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CollapsibleSection>
          )}
        </div>
      </div>
    </div>
  );
}
