import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  GitBranch,
  ChevronDown,
  Users,
  BookOpen,
  CheckCircle2,
  AlertTriangle,
  Filter,
  X,
  Loader2,
  RefreshCw,
  TrendingDown,
  Search,
} from 'lucide-react';
import clsx from 'clsx';
import { getPrometheusAnalytics } from '@/services/api';
import type {
  DropoffTrail,
  DropoffModule,
  StudentsByTrailItem,
  StudentByTrail,
} from '@/services/api';

type SortField = 'name' | 'students' | 'completion' | 'modules';
type SortDir = 'asc' | 'desc';

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

const TRAIL_STATUS_LABELS: Record<string, string> = {
  LEARNING: 'Обучается',
  GRADUATED: 'Выпускник',
  DROPPED: 'Отчислен',
};

const TRAIL_STATUS_COLORS: Record<string, string> = {
  LEARNING: 'bg-blue-500/20 text-blue-400',
  GRADUATED: 'bg-emerald-500/20 text-emerald-400',
  DROPPED: 'bg-red-500/20 text-red-400',
};

function getAvatarInitials(name: string) {
  return name
    .split(' ')
    .slice(0, 2)
    .map(n => n[0])
    .join('')
    .toUpperCase();
}

function getTrailCompletion(trail: DropoffTrail): number {
  if (trail.modules.length === 0) return 0;
  const avg = trail.modules.reduce((s, m) => s + m.completionRate, 0) / trail.modules.length;
  return Math.round(avg);
}

export default function InternsStagesTab() {
  // Period & trail filters
  const [period, setPeriod] = useState('30');
  const [selectedTrail, setSelectedTrail] = useState('all');

  // Search & filter state
  const [showFilters, setShowFilters] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [onlyBottlenecks, setOnlyBottlenecks] = useState(false);

  // Sort state
  const [sortField, setSortField] = useState<SortField>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  // Expanded trails & modules
  const [expandedTrails, setExpandedTrails] = useState<Set<string>>(new Set());
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set());

  // Fetch analytics
  const {
    data: analytics,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['prometheus-analytics-stages', selectedTrail, period],
    queryFn: () => getPrometheusAnalytics(selectedTrail, period),
    staleTime: 60000,
    retry: 1,
  });

  const dropoffTrails = analytics?.dropoffAnalysis ?? [];
  const studentsByTrail = analytics?.studentsByTrail ?? [];
  const trailFilters = analytics?.filters?.trails ?? [];

  // Build a map from trailId -> StudentsByTrailItem for student lookup
  const studentsByTrailMap = useMemo(() => {
    const map = new Map<string, StudentsByTrailItem>();
    studentsByTrail.forEach(item => map.set(item.trailId, item));
    return map;
  }, [studentsByTrail]);

  // Active filters count
  const activeFiltersCount = useMemo(() => {
    let count = 0;
    if (searchQuery) count++;
    if (onlyBottlenecks) count++;
    return count;
  }, [searchQuery, onlyBottlenecks]);

  // Filter and sort trails
  const filteredTrails = useMemo(() => {
    let trails = dropoffTrails;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      trails = trails.filter(t => t.trailTitle.toLowerCase().includes(q));
    }

    if (onlyBottlenecks) {
      trails = trails.filter(t => t.modules.some(m => m.isBottleneck));
    }

    trails = [...trails].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'name':
          cmp = a.trailTitle.localeCompare(b.trailTitle);
          break;
        case 'students':
          cmp = a.totalEnrolled - b.totalEnrolled;
          break;
        case 'modules':
          cmp = a.modules.length - b.modules.length;
          break;
        case 'completion':
          cmp = getTrailCompletion(a) - getTrailCompletion(b);
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return trails;
  }, [dropoffTrails, searchQuery, onlyBottlenecks, sortField, sortDir]);

  // Aggregate stats
  const totalStudents = useMemo(() => {
    return filteredTrails.reduce((sum, t) => sum + t.totalEnrolled, 0);
  }, [filteredTrails]);

  const totalModules = useMemo(() => {
    return filteredTrails.reduce((sum, t) => sum + t.modules.length, 0);
  }, [filteredTrails]);

  const bottleneckCount = useMemo(() => {
    return filteredTrails.reduce(
      (sum, t) => sum + t.modules.filter(m => m.isBottleneck).length,
      0,
    );
  }, [filteredTrails]);

  const toggleTrail = (trailId: string) => {
    setExpandedTrails(prev => {
      const next = new Set(prev);
      if (next.has(trailId)) next.delete(trailId);
      else next.add(trailId);
      return next;
    });
  };

  const toggleModule = (key: string) => {
    setExpandedModules(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const clearFilters = () => {
    setSearchQuery('');
    setOnlyBottlenecks(false);
  };

  // Find students in a given trail+module
  const getModuleStudents = (trailId: string, moduleId: string): StudentByTrail[] => {
    const trailData = studentsByTrailMap.get(trailId);
    if (!trailData) return [];
    return trailData.students.filter(student =>
      student.modules.some(m => m.id === moduleId && m.status !== 'NOT_STARTED'),
    );
  };

  // Get a student's status for a specific module
  const getStudentModuleStatus = (student: StudentByTrail, moduleId: string) => {
    return student.modules.find(m => m.id === moduleId);
  };

  // Period buttons
  const PERIODS = [
    { value: '7', label: '7д' },
    { value: '14', label: '14д' },
    { value: '30', label: '30д' },
    { value: '60', label: '60д' },
    { value: '90', label: '90д' },
  ];

  // Loading
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="text-center text-white/40">
          <Loader2 className="w-10 h-10 mx-auto mb-3 animate-spin opacity-60" />
          <p className="text-sm">Загрузка данных...</p>
        </div>
      </div>
    );
  }

  // Error
  if (isError) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="text-center text-white/40">
          <AlertTriangle className="w-10 h-10 mx-auto mb-3 text-red-400/60" />
          <p className="text-sm mb-3">{(error as Error)?.message || 'Ошибка загрузки'}</p>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 mx-auto px-4 py-2 glass-button rounded-lg text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Повторить
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-3">
      {/* Trail & Period selectors */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <select
          value={selectedTrail}
          onChange={e => setSelectedTrail(e.target.value)}
          className="px-3 py-2 glass-light rounded-xl text-sm focus:outline-none focus:border-emerald-500/50 [&>option]:bg-dark-900 [&>option]:text-white"
        >
          <option value="all">Все трейлы</option>
          {trailFilters.map(t => (
            <option key={t.id} value={t.id}>
              {t.title}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-1">
          {PERIODS.map(p => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={clsx(
                'px-3 py-1.5 text-xs rounded-lg border transition-colors',
                period === p.value
                  ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400'
                  : 'glass-light text-white/50 hover:border-emerald-500/20',
              )}
            >
              {p.label}
            </button>
          ))}
        </div>

        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 px-3 py-2 glass-button rounded-xl text-xs transition-colors ml-auto"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Обновить
        </button>
      </div>

      {/* Filter & sort bar */}
      <div className="space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2.5 border rounded-xl text-sm font-medium transition-all active:scale-95',
              activeFiltersCount > 0
                ? 'bg-emerald-600/20 border-emerald-500/50 text-emerald-300'
                : 'glass-light hover:border-emerald-500/20',
            )}
          >
            <Filter className="w-4 h-4" />
            <span>Фильтры</span>
            {activeFiltersCount > 0 && (
              <span className="px-1.5 py-0.5 bg-emerald-600 text-white text-[10px] rounded-full">
                {activeFiltersCount}
              </span>
            )}
          </button>
          {activeFiltersCount > 0 && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1.5 px-3 py-2.5 text-sm text-white/50 hover:text-white/80 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              Сбросить
            </button>
          )}

          {/* Sort buttons */}
          <div className="flex items-center gap-1 ml-auto">
            <span className="text-xs text-white/40 mr-1">Сортировка:</span>
            {(
              [
                { field: 'name' as SortField, label: 'Название' },
                { field: 'students' as SortField, label: 'Студенты' },
                { field: 'modules' as SortField, label: 'Модули' },
                { field: 'completion' as SortField, label: 'Прогресс' },
              ] as const
            ).map(item => (
              <button
                key={item.field}
                onClick={() => handleSort(item.field)}
                className={clsx(
                  'px-2 py-1 text-xs rounded-lg border transition-colors flex items-center gap-1',
                  sortField === item.field
                    ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400'
                    : 'glass-light text-white/50 hover:border-emerald-500/20',
                )}
              >
                {item.label}
                {sortField === item.field && (
                  <ChevronDown
                    className={clsx(
                      'w-3 h-3 transition-transform',
                      sortDir === 'asc' ? 'rotate-180' : '',
                    )}
                  />
                )}
              </button>
            ))}
          </div>
        </div>

        {showFilters && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="p-4 glass-light rounded-xl space-y-4 overflow-hidden"
          >
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Trail name search */}
              <div>
                <label className="text-xs text-white/50 mb-1.5 block">Поиск по названию трейла</label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
                  <input
                    type="text"
                    placeholder="Название трейла..."
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 glass-light rounded-lg focus:outline-none focus:border-emerald-500/50 text-sm"
                  />
                </div>
              </div>

              {/* Trail dropdown selector */}
              <div>
                <label className="text-xs text-white/50 mb-1.5 block">Выбрать трейл из списка</label>
                <div className="relative">
                  <select
                    value=""
                    onChange={e => {
                      if (e.target.value) {
                        setSearchQuery(e.target.value);
                      }
                    }}
                    className="w-full appearance-none pl-3 pr-8 py-2 glass-light rounded-lg text-sm focus:outline-none focus:border-emerald-500/50 cursor-pointer [&>option]:bg-dark-900 [&>option]:text-white"
                  >
                    <option value="">Выберите трейл...</option>
                    {dropoffTrails.map(t => (
                      <option key={t.trailId} value={t.trailTitle}>
                        {t.trailTitle}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
                </div>
              </div>

              {/* Bottleneck filter */}
              <div>
                <label className="text-xs text-white/50 mb-1.5 block">Фильтр</label>
                <button
                  onClick={() => setOnlyBottlenecks(!onlyBottlenecks)}
                  className={clsx(
                    'flex items-center gap-2 px-3 py-2 text-sm rounded-lg border transition-colors',
                    onlyBottlenecks
                      ? 'bg-red-500/20 border-red-500/30 text-red-400'
                      : 'glass-light text-white/60 hover:border-red-500/20',
                  )}
                >
                  <TrendingDown className="w-4 h-4" />
                  Только с узкими местами
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="glass-light rounded-xl p-3"
        >
          <div className="flex items-center gap-2 text-white/50 mb-1">
            <GitBranch className="w-4 h-4 text-emerald-400" />
            <span className="text-xs">Трейлов</span>
          </div>
          <p className="text-xl font-bold">{filteredTrails.length}</p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-light rounded-xl p-3"
        >
          <div className="flex items-center gap-2 text-white/50 mb-1">
            <Users className="w-4 h-4 text-blue-400" />
            <span className="text-xs">Студентов</span>
          </div>
          <p className="text-xl font-bold">{totalStudents}</p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass-light rounded-xl p-3"
        >
          <div className="flex items-center gap-2 text-white/50 mb-1">
            <BookOpen className="w-4 h-4 text-amber-400" />
            <span className="text-xs">Модулей</span>
          </div>
          <p className="text-xl font-bold">{totalModules}</p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-light rounded-xl p-3"
        >
          <div className="flex items-center gap-2 text-white/50 mb-1">
            <TrendingDown className="w-4 h-4 text-red-400" />
            <span className="text-xs">Узких мест</span>
          </div>
          <p className="text-xl font-bold">{bottleneckCount}</p>
        </motion.div>
      </div>

      {/* Trail Cards */}
      {filteredTrails.length === 0 ? (
        <div className="py-16 text-center text-white/40">
          <GitBranch className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium mb-2">Нет трейлов</h3>
          <p className="text-sm">
            {dropoffTrails.length === 0
              ? 'Данные о прохождении отсутствуют'
              : 'Попробуйте изменить параметры фильтров'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredTrails.map((trail, trailIndex) => {
            const isExpanded = expandedTrails.has(trail.trailId);
            const completion = getTrailCompletion(trail);
            const completedModules = trail.modules.filter(m => m.completionRate === 100).length;
            const hasBottlenecks = trail.modules.some(m => m.isBottleneck);

            return (
              <motion.div
                key={trail.trailId}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: trailIndex * 0.05 }}
                className="glass-light rounded-xl overflow-hidden"
              >
                {/* Trail Header */}
                <button
                  onClick={() => toggleTrail(trail.trailId)}
                  className="w-full flex items-center justify-between p-4 hover:bg-dark-800/50 transition-colors text-left"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <GitBranch className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h4 className="font-medium text-sm truncate">{trail.trailTitle}</h4>
                        {hasBottlenecks && (
                          <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-red-500/20 text-red-400 flex-shrink-0">
                            Узкие места
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-white/40">
                        <span className="flex items-center gap-1">
                          <Users className="w-3 h-3" />
                          {trail.totalEnrolled} студ.
                        </span>
                        <span className="flex items-center gap-1">
                          <BookOpen className="w-3 h-3" />
                          {trail.modules.length} мод.
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 flex-shrink-0">
                    <div className="hidden sm:flex items-center gap-2">
                      <div className="w-20 h-1.5 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className={clsx('h-full rounded-full', {
                            'bg-emerald-400': completion >= 80,
                            'bg-amber-400': completion >= 50 && completion < 80,
                            'bg-blue-400': completion < 50,
                          })}
                          style={{ width: `${completion}%` }}
                        />
                      </div>
                      <span className="text-xs text-white/50 w-8 text-right">{completion}%</span>
                    </div>
                    <div className="hidden sm:block">
                      <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/20 text-emerald-400">
                        {completedModules}/{trail.modules.length}
                      </span>
                    </div>
                    <ChevronDown
                      className={clsx(
                        'w-4 h-4 text-white/40 transition-transform',
                        isExpanded ? 'rotate-180' : '',
                      )}
                    />
                  </div>
                </button>

                {/* Trail Content - Modules */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-4 pb-4 border-t border-white/5 space-y-2 pt-3">
                        {trail.modules
                          .sort((a, b) => a.order - b.order)
                          .map((mod: DropoffModule) => {
                            const moduleKey = `${trail.trailId}-${mod.id}`;
                            const isModExpanded = expandedModules.has(moduleKey);
                            const modStudents = getModuleStudents(trail.trailId, mod.id);

                            return (
                              <div key={mod.id} className="glass-light rounded-lg overflow-hidden">
                                <button
                                  onClick={() => toggleModule(moduleKey)}
                                  className="w-full flex items-center justify-between p-3 hover:bg-dark-800/50 transition-colors text-left"
                                >
                                  <div className="flex items-center gap-2 min-w-0 flex-1">
                                    {mod.completionRate === 100 ? (
                                      <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                                    ) : mod.isBottleneck ? (
                                      <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                                    ) : (
                                      <BookOpen className="w-4 h-4 text-amber-400 flex-shrink-0" />
                                    )}
                                    <span className="text-sm truncate">{mod.title}</span>
                                    <span
                                      className={clsx(
                                        'px-1.5 py-0.5 text-[10px] rounded-full flex-shrink-0',
                                        MODULE_TYPE_COLORS[mod.type] || 'bg-white/10 text-white/50',
                                      )}
                                    >
                                      {MODULE_TYPE_LABELS[mod.type] || mod.type}
                                    </span>
                                    {mod.isBottleneck && (
                                      <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-red-500/20 text-red-400 flex-shrink-0">
                                        Узкое место
                                      </span>
                                    )}
                                    <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-white/10 text-white/50 flex-shrink-0">
                                      {modStudents.length} студ.
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-3 flex-shrink-0">
                                    {/* Drop rate indicator */}
                                    {mod.dropRate > 0 && (
                                      <span
                                        className={clsx('text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0', {
                                          'bg-red-500/20 text-red-400': mod.dropRate >= 30,
                                          'bg-amber-500/20 text-amber-400':
                                            mod.dropRate >= 15 && mod.dropRate < 30,
                                          'bg-white/10 text-white/40': mod.dropRate < 15,
                                        })}
                                      >
                                        Отсев {Math.round(mod.dropRate)}%
                                      </span>
                                    )}
                                    {/* Completion bar */}
                                    <div className="flex items-center gap-2">
                                      <div className="w-16 h-1.5 bg-white/10 rounded-full overflow-hidden">
                                        <div
                                          className={clsx('h-full rounded-full', {
                                            'bg-emerald-400': mod.completionRate >= 80,
                                            'bg-amber-400':
                                              mod.completionRate >= 50 && mod.completionRate < 80,
                                            'bg-blue-400': mod.completionRate < 50,
                                          })}
                                          style={{ width: `${mod.completionRate}%` }}
                                        />
                                      </div>
                                      <span className="text-xs text-white/40 w-8 text-right">
                                        {Math.round(mod.completionRate)}%
                                      </span>
                                    </div>
                                    <ChevronDown
                                      className={clsx(
                                        'w-3.5 h-3.5 text-white/30 transition-transform',
                                        isModExpanded ? 'rotate-180' : '',
                                      )}
                                    />
                                  </div>
                                </button>

                                {/* Module details + students */}
                                <AnimatePresence>
                                  {isModExpanded && (
                                    <motion.div
                                      initial={{ height: 0, opacity: 0 }}
                                      animate={{ height: 'auto', opacity: 1 }}
                                      exit={{ height: 0, opacity: 0 }}
                                      transition={{ duration: 0.15 }}
                                      className="overflow-hidden"
                                    >
                                      {/* Module stats row */}
                                      <div className="px-3 pb-2 flex flex-wrap gap-3 text-xs text-white/50">
                                        <span>
                                          Записано: <strong className="text-white/70">{mod.totalEnrolled}</strong>
                                        </span>
                                        <span>
                                          Начали: <strong className="text-white/70">{mod.startedCount}</strong>
                                        </span>
                                        <span>
                                          В процессе: <strong className="text-white/70">{mod.inProgressCount}</strong>
                                        </span>
                                        <span>
                                          Завершили: <strong className="text-emerald-400">{mod.completedCount}</strong>
                                        </span>
                                        {mod.avgTimeDays > 0 && (
                                          <span>
                                            Среднее время: <strong className="text-white/70">{mod.avgTimeDays} дн.</strong>
                                          </span>
                                        )}
                                      </div>

                                      {/* Students list */}
                                      <div className="px-3 pb-3 space-y-1.5">
                                        {modStudents.length === 0 ? (
                                          <p className="text-xs text-white/30 py-2 text-center">
                                            Нет студентов, начавших этот модуль
                                          </p>
                                        ) : (
                                          modStudents.map((student: StudentByTrail) => {
                                            const moduleStatus = getStudentModuleStatus(student, mod.id);

                                            return (
                                              <div
                                                key={student.id}
                                                className="flex items-center gap-3 p-2 glass-light rounded-lg"
                                              >
                                                <div className="w-7 h-7 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400 text-xs font-medium flex-shrink-0">
                                                  {getAvatarInitials(student.name)}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                  <div className="flex items-center gap-2">
                                                    <span className="text-xs font-medium truncate">
                                                      {student.name}
                                                    </span>
                                                    <span
                                                      className={clsx(
                                                        'px-1.5 py-0.5 text-[10px] rounded-full flex-shrink-0',
                                                        TRAIL_STATUS_COLORS[student.trailStatus] ||
                                                          'bg-white/10 text-white/50',
                                                      )}
                                                    >
                                                      {TRAIL_STATUS_LABELS[student.trailStatus] ||
                                                        student.trailStatus}
                                                    </span>
                                                  </div>
                                                  <div className="flex items-center gap-2 mt-1">
                                                    <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
                                                      <div
                                                        className={clsx('h-full rounded-full', {
                                                          'bg-emerald-400': student.completionPercent >= 80,
                                                          'bg-amber-400':
                                                            student.completionPercent >= 50 &&
                                                            student.completionPercent < 80,
                                                          'bg-blue-400': student.completionPercent < 50,
                                                        })}
                                                        style={{
                                                          width: `${student.completionPercent}%`,
                                                        }}
                                                      />
                                                    </div>
                                                    <span className="text-[10px] text-white/40 w-8 text-right flex-shrink-0">
                                                      {student.completionPercent}%
                                                    </span>
                                                  </div>
                                                </div>
                                                {/* Module-specific status */}
                                                {moduleStatus && (
                                                  <span
                                                    className={clsx(
                                                      'text-[10px] font-medium px-1.5 py-0.5 rounded flex-shrink-0',
                                                      {
                                                        'bg-emerald-500/20 text-emerald-400':
                                                          moduleStatus.status === 'COMPLETED',
                                                        'bg-blue-500/20 text-blue-400':
                                                          moduleStatus.status === 'IN_PROGRESS',
                                                        'bg-white/10 text-white/40':
                                                          moduleStatus.status === 'NOT_STARTED',
                                                      },
                                                    )}
                                                  >
                                                    {moduleStatus.status === 'COMPLETED'
                                                      ? 'Завершён'
                                                      : moduleStatus.status === 'IN_PROGRESS'
                                                        ? 'В процессе'
                                                        : 'Не начат'}
                                                  </span>
                                                )}
                                                {/* Avg score */}
                                                {student.avgScore !== null && (
                                                  <span
                                                    className={clsx(
                                                      'text-xs font-medium px-1.5 py-0.5 rounded flex-shrink-0',
                                                      {
                                                        'bg-emerald-500/20 text-emerald-400':
                                                          student.avgScore >= 90,
                                                        'bg-blue-500/20 text-blue-400':
                                                          student.avgScore >= 75 && student.avgScore < 90,
                                                        'bg-amber-500/20 text-amber-400':
                                                          student.avgScore >= 60 && student.avgScore < 75,
                                                        'bg-red-500/20 text-red-400': student.avgScore < 60,
                                                      },
                                                    )}
                                                  >
                                                    {Math.round(student.avgScore)}
                                                  </span>
                                                )}
                                              </div>
                                            );
                                          })
                                        )}
                                      </div>
                                    </motion.div>
                                  )}
                                </AnimatePresence>
                              </div>
                            );
                          })}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
