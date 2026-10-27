import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  Search,
  GraduationCap,
  BarChart3,
  Clock,
  GitBranch,
  Download,
  Zap,
  BookOpen,
  AlertTriangle,
  RefreshCw,
  Loader2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  UserCheck,
  ArrowUpDown,
  Send,
} from 'lucide-react';
import clsx from 'clsx';
import { formatRelativeTime } from '@/utils';
import { getPrometheusInterns, getInternLinkedContacts } from '@/services/api';
import type { PrometheusIntern } from '@/services/api';
import { usePrometheusBulkSync } from '@/hooks';
import { useUrlTab } from '@/hooks/useUrlTab';
import InternsAnalyticsTab from '@/components/interns/InternsAnalyticsTab';
import InternsStagesTab from '@/components/interns/InternsStagesTab';
import InternsCsvTab from '@/components/interns/InternsCsvTab';

// ── Status badge helper ──

const HR_STATUS_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  'Обучается': { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30' },
  'Принят': { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  'Отклонен': { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30' },
};

function StatusBadge({ status }: { status: string }) {
  const style = HR_STATUS_STYLES[status] || { bg: 'bg-white/10', text: 'text-white/60', border: 'border-white/10' };
  return (
    <span className={clsx('px-2 py-0.5 text-[10px] rounded-full border whitespace-nowrap', style.bg, style.text, style.border)}>
      {status}
    </span>
  );
}

// Tabs for interns section
type InternTab = 'interns' | 'analytics' | 'stages' | 'csv';

const INTERN_TABS: { key: InternTab; label: string; icon: typeof GraduationCap }[] = [
  { key: 'interns', label: 'Практиканты', icon: GraduationCap },
  { key: 'analytics', label: 'Аналитика', icon: BarChart3 },
  { key: 'stages', label: 'Этапы прохождения', icon: GitBranch },
  { key: 'csv', label: 'Выгрузка в CSV', icon: Download },
];

// Sort types for interns list
type InternSortField = 'name' | 'modules' | 'date' | 'status';
type SortDir = 'asc' | 'desc';

const SORT_OPTIONS: { field: InternSortField; label: string }[] = [
  { field: 'name', label: 'Имя' },
  { field: 'modules', label: 'Модули' },
  { field: 'date', label: 'Дата зачисления' },
  { field: 'status', label: 'Статус' },
];

const PAGE_SIZE_OPTIONS = [10, 15, 20, 50, 100] as const;

// Status priority for sorting (Принят first, Обучается second, Отклонен third, unknown last)
const STATUS_PRIORITY: Record<string, number> = {
  'Принят': 0,
  'Обучается': 1,
  'Отклонен': 2,
};

function getAvatarInitials(name: string) {
  return name
    .split(' ')
    .slice(0, 2)
    .map(n => n[0])
    .join('')
    .toUpperCase();
}


function formatDaysSinceActive(daysSinceActive: number | null, lastActiveAt: string | null): string {
  if (daysSinceActive === null && lastActiveAt === null) return 'Нет данных';
  if (daysSinceActive === 0) return 'Сегодня';
  if (daysSinceActive === 1) return 'Вчера';
  if (daysSinceActive !== null) {
    return `${daysSinceActive} дн. назад`;
  }
  if (lastActiveAt) return formatRelativeTime(lastActiveAt);
  return 'Нет данных';
}

export default function InternsPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useUrlTab<InternTab>("tab", "interns");
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTrailFilter, setSelectedTrailFilter] = useState('all');

  // Sorting state
  const [sortField, setSortField] = useState<InternSortField>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  // Pagination state
  const [pageSize, setPageSize] = useState<number>(20);
  const [currentPage, setCurrentPage] = useState(1);

  // Fetch interns from Prometheus via backend proxy
  const {
    data: interns = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['prometheus-interns'],
    queryFn: getPrometheusInterns,
    staleTime: 60000, // 1 min
    retry: 1,
  });

  // Fetch linked contacts (which interns are already exported)
  const { data: linkedContactsData } = useQuery({
    queryKey: ['intern-linked-contacts'],
    queryFn: getInternLinkedContacts,
    staleTime: 60000,
    retry: 0,
  });
  const linkedContacts = linkedContactsData?.links ?? {};

  // Build a global trailId -> trailName lookup from all interns
  const trailNameMap = useMemo(() => {
    const map = new Map<string, string>();
    interns.forEach(intern => {
      intern.trails.forEach(t => {
        if (t.trailId && t.trailName && t.trailName.trim() && !map.has(t.trailId)) {
          map.set(t.trailId, t.trailName);
        }
      });
    });
    return map;
  }, [interns]);

  // Extract unique trails for filter dropdown
  const availableTrails = useMemo(() => {
    return Array.from(trailNameMap.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [trailNameMap]);

  // Filter interns by search query and trail
  const filteredInterns = useMemo(() => {
    let result = interns;

    // Filter by selected trail
    if (selectedTrailFilter !== 'all') {
      result = result.filter(intern =>
        intern.trails.some(t => t.trailId === selectedTrailFilter)
      );
    }

    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(intern =>
        intern.name.toLowerCase().includes(query) ||
        (intern.email && intern.email.toLowerCase().includes(query)) ||
        (intern.telegramUsername && intern.telegramUsername.toLowerCase().includes(query)) ||
        intern.trails.some(t => t.trailName?.toLowerCase().includes(query))
      );
    }

    return result;
  }, [searchQuery, selectedTrailFilter, interns]);

  // Collect emails from currently visible (filtered) interns for Prometheus status sync
  const visibleEmails = useMemo(() => {
    return filteredInterns
      .map(i => i.email)
      .filter((e): e is string => !!e && e.trim().length > 0);
  }, [filteredInterns]);

  // 30-second Prometheus status polling
  const { statusMap, syncError: _syncError, isSyncing } = usePrometheusBulkSync(
    visibleEmails,
    activeTab === 'interns' && !isLoading && !isError,
  );

  // Sort handler (toggle direction or change field)
  const handleSort = (field: InternSortField) => {
    if (sortField === field) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
    setCurrentPage(1);
  };

  // Sort filtered interns
  const sortedInterns = useMemo(() => {
    return [...filteredInterns].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'name':
          cmp = a.name.localeCompare(b.name, 'ru');
          break;
        case 'modules': {
          const aModules = a.trails.reduce((sum, t) => sum + t.completedModules, 0);
          const bModules = b.trails.reduce((sum, t) => sum + t.completedModules, 0);
          cmp = aModules - bModules;
          break;
        }
        case 'date': {
          const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
          const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
          cmp = (isNaN(aTime) ? 0 : aTime) - (isNaN(bTime) ? 0 : bTime);
          break;
        }
        case 'status': {
          const aStatus = a.email ? statusMap[a.email.toLowerCase()]?.hrStatus : undefined;
          const bStatus = b.email ? statusMap[b.email.toLowerCase()]?.hrStatus : undefined;
          const aPriority = aStatus ? (STATUS_PRIORITY[aStatus] ?? 3) : 3;
          const bPriority = bStatus ? (STATUS_PRIORITY[bStatus] ?? 3) : 3;
          cmp = aPriority - bPriority;
          break;
        }
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filteredInterns, sortField, sortDir, statusMap]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(sortedInterns.length / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const paginatedInterns = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return sortedInterns.slice(start, start + pageSize);
  }, [sortedInterns, safePage, pageSize]);

  // Reset page when filters or search change
  const resetPage = () => setCurrentPage(1);

  // Render a single intern card (Prometheus data shape)
  const renderInternCard = (intern: PrometheusIntern) => {
    const contactId = linkedContacts[intern.id];
    const syncResult = intern.email ? statusMap[intern.email.toLowerCase()] : undefined;
    const hrStatus = syncResult?.hrStatus;
    // Prefer contactId from sync if available (auto-export may have created it)
    const resolvedContactId = syncResult?.contactId || contactId;
    // Determine which trail to display based on the filter
    const namedTrails = intern.trails.filter(t => t.trailName && t.trailName.trim());

    // If a specific trail is selected in the filter, show that trail's data
    // Otherwise, auto-detect the "current" trail
    const displayTrail = selectedTrailFilter !== 'all'
      ? intern.trails.find(t => t.trailId === selectedTrailFilter) || null
      : (namedTrails.find(t => t.completedModules > 0 && t.completedModules < t.totalModules)
        || namedTrails.find(t => t.completedModules > 0)
        || namedTrails[0]
        || intern.trails[0]
        || null);

    // Module counts and progress based on the display trail
    const completedModules = displayTrail ? (displayTrail.completedModules || 0) : 0;
    const totalModules = displayTrail ? (displayTrail.totalModules || 0) : 0;
    const completionPercent = totalModules > 0 ? Math.round((completedModules / totalModules) * 100) : 0;

    // Resolve trail name
    const trailDisplayName = displayTrail
      ? (displayTrail.trailName?.trim()
        || trailNameMap.get(displayTrail.trailId)
        || 'Без названия')
      : null;

    return (
      <motion.div
        key={intern.id}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        onClick={() => navigate(`/interns/${intern.id}/stats`)}
        className="p-3 glass-light rounded-xl transition-colors group overflow-hidden flex flex-col cursor-pointer hover:border-emerald-500/30"
      >
        {/* Name + avatar */}
        <div className="flex items-start gap-2 mb-2">
          <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400 font-medium text-sm flex-shrink-0">
            {getAvatarInitials(intern.name)}
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="font-medium text-sm truncate">{intern.name}</h4>
            {intern.email && (
              <p className="text-xs text-white/50 truncate">{intern.email}</p>
            )}
            {intern.telegramUsername && (
              <p className="text-xs text-white/50 truncate flex items-center gap-1">
                <Send className="w-3 h-3 flex-shrink-0" />
                {intern.telegramUsername.startsWith('@') ? intern.telegramUsername : `@${intern.telegramUsername}`}
              </p>
            )}
          </div>
        </div>

        {/* XP badge + status badge + contact badge */}
        <div className="flex items-center gap-2 mb-2 ml-12 flex-wrap">
          <span className="flex items-center gap-1 px-2 py-0.5 text-xs rounded-full whitespace-nowrap bg-amber-500/20 text-amber-400">
            <Zap className="w-3 h-3" />
            {intern.totalXP} XP
          </span>
          {hrStatus && <StatusBadge status={hrStatus} />}
          {resolvedContactId && (
            <span
              onClick={(e) => { e.stopPropagation(); navigate(`/all-candidates?entity=${resolvedContactId}`); }}
              className="flex items-center gap-1 px-2 py-0.5 text-xs rounded-full whitespace-nowrap bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 cursor-pointer transition-colors"
              title="Открыть контакт"
            >
              <UserCheck className="w-3 h-3" />
              В контактах
            </span>
          )}
        </div>

        {/* Last active */}
        <div className="text-xs text-white/60 ml-12 mb-2">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 flex-shrink-0" />
            <span>Активность: {formatDaysSinceActive(intern.daysSinceActive, intern.lastActiveAt)}</span>
          </div>
        </div>

        {/* Module progress summary */}
        {displayTrail ? (
          <div className="mt-1 ml-12 space-y-1.5">
            {/* Trail name */}
            <div className="flex items-center gap-1.5">
              <GitBranch className="w-3 h-3 text-blue-400 flex-shrink-0" />
              <span className="text-xs text-white/50 truncate">
                {trailDisplayName}
              </span>
            </div>

            {/* Modules progress for the trail */}
            <div className="flex items-center gap-2">
              <BookOpen className="w-3 h-3 text-emerald-400 flex-shrink-0" />
              <span className="text-xs text-white/70 font-medium">
                Модулей: {completedModules}/{totalModules}
              </span>
              <span className="text-xs text-white/40">({completionPercent}%)</span>
            </div>

            {/* Progress bar for the trail */}
            <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
              <div
                className={clsx('h-full rounded-full transition-all', {
                  'bg-emerald-400': completionPercent >= 80,
                  'bg-amber-400': completionPercent >= 50 && completionPercent < 80,
                  'bg-blue-400': completionPercent < 50,
                })}
                style={{ width: `${completionPercent}%` }}
              />
            </div>

            {/* Additional trails count (only when showing auto-detected trail, not filtered) */}
            {selectedTrailFilter === 'all' && intern.trails.length > 1 && (
              <p className="text-[10px] text-white/30">
                +{intern.trails.length - 1} {intern.trails.length - 1 === 1 ? 'трейл' : intern.trails.length - 1 < 5 ? 'трейла' : 'трейлов'}
              </p>
            )}
          </div>
        ) : (
          <div className="mt-1 ml-12">
            <p className="text-xs text-white/30 flex items-center gap-1.5">
              <BookOpen className="w-3 h-3" />
              Нет назначенных трейлов
            </p>
          </div>
        )}

        {/* Action button — pinned to the bottom */}
        <div className="mt-auto pt-4 border-t border-white/10">
          <button
            onClick={(e) => { e.stopPropagation(); navigate(`/interns/${intern.id}/stats`); }}
            className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30 rounded-lg text-xs font-medium transition-colors"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Статистика
          </button>
        </div>
      </motion.div>
    );
  };

  // Loading state
  const renderLoading = () => (
    <div className="h-full flex items-center justify-center">
      <div className="text-center text-white/40">
        <Loader2 className="w-12 h-12 mx-auto mb-4 animate-spin opacity-50" />
        <h3 className="text-lg font-medium mb-2">Загрузка практикантов...</h3>
        <p className="text-sm">Получаем данные из Prometheus</p>
      </div>
    </div>
  );

  // Error state
  const renderError = () => (
    <div className="h-full flex items-center justify-center">
      <div className="text-center text-white/40">
        <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-red-400/60" />
        <h3 className="text-lg font-medium mb-2 text-red-400/80">Ошибка загрузки</h3>
        <p className="text-sm mb-4 max-w-md mx-auto">
          {(error as Error)?.message || 'Не удалось загрузить данные практикантов'}
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

  return (
    <div className="h-full flex flex-col">
      {/* Tabs */}
      <div className="px-4 pt-4 border-b border-white/10">
        <div className="flex items-center gap-1 overflow-x-auto pb-0 scrollbar-hide">
          {INTERN_TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={clsx(
                'flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap transition-all border-b-2 -mb-[1px]',
                activeTab === tab.key
                  ? 'border-emerald-500 text-emerald-400'
                  : 'border-transparent text-white/50 hover:text-white/80 hover:border-white/20'
              )}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'interns' ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="p-4 border-b border-white/10 space-y-3">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <h2 className="text-xl font-bold flex items-center gap-2 whitespace-nowrap">
                <GraduationCap className="w-6 h-6 text-emerald-400" />
                База практикантов
                {!isLoading && !isError && (
                  <span className="text-sm font-medium text-white/40 glass-light px-2 py-0.5 rounded-full ml-1">
                    {filteredInterns.length}
                  </span>
                )}
              </h2>
              <div className="flex items-center gap-2">
                {isSyncing && (
                  <span className="text-[10px] text-white/30 flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Синхронизация
                  </span>
                )}
                <button
                  onClick={() => refetch()}
                  disabled={isLoading}
                  className="flex items-center gap-2 px-3 py-2 glass-button rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={clsx('w-3.5 h-3.5', isLoading && 'animate-spin')} />
                  Обновить
                </button>
              </div>
            </div>

            {/* Filters row */}
            <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3">
              {/* Search input */}
              <div className="relative flex-1 group">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 group-focus-within:text-emerald-400 transition-colors" />
                <input
                  type="text"
                  placeholder="Поиск по имени, email, Telegram, трекам..."
                  value={searchQuery}
                  onChange={(e) => { setSearchQuery(e.target.value); resetPage(); }}
                  className="w-full pl-10 pr-4 py-2.5 glass-light rounded-xl focus:outline-none focus:border-emerald-500/50 focus:bg-white/10 text-sm transition-all"
                />
              </div>

              {/* Trail dropdown filter */}
              <div className="flex items-center gap-2">
                <label className="text-xs text-white/40 whitespace-nowrap">
                  <GitBranch className="w-3 h-3 inline mr-1" />
                  Трейл:
                </label>
                <div className="relative">
                  <select
                    value={selectedTrailFilter}
                    onChange={e => { setSelectedTrailFilter(e.target.value); resetPage(); }}
                    className="appearance-none pl-3 pr-8 py-2.5 glass-light rounded-xl text-sm focus:outline-none focus:border-emerald-500/50 cursor-pointer min-w-[140px] [&>option]:bg-dark-900 [&>option]:text-white"
                  >
                    <option value="all">Все трейлы</option>
                    {availableTrails.map(trail => (
                      <option key={trail.id} value={trail.id}>
                        {trail.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
                </div>
              </div>

            </div>

            {/* Sort & page size row */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              {/* Sort buttons */}
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-xs text-white/40 mr-1 flex items-center gap-1">
                  <ArrowUpDown className="w-3 h-3" />
                  Сортировка:
                </span>
                {SORT_OPTIONS.map(opt => (
                  <button
                    key={opt.field}
                    onClick={() => handleSort(opt.field)}
                    className={clsx(
                      'px-2 py-1 text-xs rounded-lg border transition-colors flex items-center gap-1',
                      sortField === opt.field
                        ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400'
                        : 'glass-light text-white/50 hover:border-emerald-500/20'
                    )}
                  >
                    {opt.label}
                    {sortField === opt.field && (
                      <ChevronDown className={clsx('w-3 h-3 transition-transform', sortDir === 'asc' ? 'rotate-180' : '')} />
                    )}
                  </button>
                ))}
              </div>

              {/* Page size selector */}
              <div className="flex items-center gap-1.5 sm:ml-auto">
                <span className="text-xs text-white/40">Показывать:</span>
                {PAGE_SIZE_OPTIONS.map(size => (
                  <button
                    key={size}
                    onClick={() => { setPageSize(size); setCurrentPage(1); }}
                    className={clsx(
                      'px-2 py-1 text-xs rounded-lg border transition-colors',
                      pageSize === size
                        ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400'
                        : 'glass-light text-white/50 hover:border-emerald-500/20'
                    )}
                  >
                    {size}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Cards Grid / Loading / Error */}
          <div className="flex-1 overflow-auto p-4">
            {isLoading ? renderLoading() : isError ? renderError() : sortedInterns.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center text-white/40">
                  <GraduationCap className="w-16 h-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium mb-2">
                    {searchQuery || selectedTrailFilter !== 'all'
                      ? 'Ничего не найдено'
                      : 'Нет практикантов'}
                  </h3>
                  <p className="text-sm">
                    {searchQuery || selectedTrailFilter !== 'all'
                      ? 'Попробуйте изменить параметры поиска или фильтров'
                      : 'Практиканты появятся здесь после добавления'}
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {paginatedInterns.map(intern => renderInternCard(intern))}
                </div>

                {/* Pagination controls */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between pt-2 pb-1">
                    <span className="text-xs text-white/40">
                      {(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, sortedInterns.length)} из {sortedInterns.length}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        disabled={safePage <= 1}
                        className="p-1.5 glass-light rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed hover:border-emerald-500/20"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>
                      {Array.from({ length: totalPages }, (_, i) => i + 1)
                        .filter(page => page === 1 || page === totalPages || Math.abs(page - safePage) <= 1)
                        .reduce<(number | 'ellipsis')[]>((acc, page, idx, arr) => {
                          if (idx > 0 && page - (arr[idx - 1] as number) > 1) acc.push('ellipsis');
                          acc.push(page);
                          return acc;
                        }, [])
                        .map((item, idx) =>
                          item === 'ellipsis' ? (
                            <span key={`e-${idx}`} className="px-1 text-xs text-white/30">...</span>
                          ) : (
                            <button
                              key={item}
                              onClick={() => setCurrentPage(item)}
                              className={clsx(
                                'min-w-[28px] h-7 px-1.5 text-xs rounded-lg border transition-colors',
                                safePage === item
                                  ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400'
                                  : 'glass-light text-white/50 hover:border-emerald-500/20'
                              )}
                            >
                              {item}
                            </button>
                          )
                        )}
                      <button
                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        disabled={safePage >= totalPages}
                        className="p-1.5 glass-light rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed hover:border-emerald-500/20"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      ) : activeTab === 'analytics' ? (
        <div className="flex-1 overflow-auto p-4">
          <InternsAnalyticsTab />
        </div>
      ) : activeTab === 'stages' ? (
        <div className="flex-1 overflow-auto p-4">
          <InternsStagesTab />
        </div>
      ) : (
        <div className="flex-1 overflow-auto p-4">
          <InternsCsvTab />
        </div>
      )}
    </div>
  );
}
