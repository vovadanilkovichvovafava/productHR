import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Bot,
  ListTodo,
  ChevronRight,
  ChevronDown,
  Flame,
} from 'lucide-react';
import clsx from 'clsx';
import type { AllTasksProjectGroup, AllTasksFilters, TaskStatus, ProjectTask } from '@/services/api/projects';
import * as api from '@/services/api';

// ============================================================
// CONSTANTS
// ============================================================

const TASK_STATUS_ORDER: TaskStatus[] = ['in_progress', 'review', 'todo', 'backlog', 'done'];

const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  backlog: 'Бэклог',
  todo: 'К выполнению',
  in_progress: 'В работе',
  review: 'Ревью',
  done: 'Готово',
  cancelled: 'Отменена',
};

const TASK_STATUS_COLORS: Record<TaskStatus, string> = {
  backlog: 'bg-white/10 text-white/40',
  todo: 'bg-blue-500/20 text-blue-400',
  in_progress: 'bg-amber-500/20 text-amber-400',
  review: 'bg-purple-500/20 text-purple-400',
  done: 'bg-green-500/20 text-green-400',
  cancelled: 'bg-red-500/20 text-red-400',
};

const TASK_STATUS_DOT: Record<TaskStatus, string> = {
  backlog: 'bg-white/30',
  todo: 'bg-blue-400',
  in_progress: 'bg-amber-400',
  review: 'bg-purple-400',
  done: 'bg-green-400',
  cancelled: 'bg-red-400',
};

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Низкий',
  1: 'Обычный',
  2: 'Высокий',
  3: 'Срочный',
};

const PRIORITY_COLORS: Record<number, string> = {
  0: 'text-white/20',
  1: 'text-blue-400',
  2: 'text-amber-400',
  3: 'text-red-400',
};

const PRIORITY_DOT: Record<number, string> = {
  0: 'bg-white/15',
  1: 'bg-blue-400',
  2: 'bg-amber-400',
  3: 'bg-red-400',
};

// ============================================================
// TASK ROW
// ============================================================

function TaskRow({ task, onClick }: { task: ProjectTask; onClick?: () => void }) {
  return (
    <div
      onClick={onClick}
      className="grid grid-cols-[1fr_120px_100px_80px] gap-2 px-4 py-2.5 items-center hover:bg-white/[0.03] transition-colors cursor-pointer border-b border-white/[0.02] last:border-b-0 group"
    >
      {/* Title */}
      <div className="flex items-center gap-2 min-w-0 pl-7">
        <div className={clsx('w-2 h-2 rounded-full flex-shrink-0', PRIORITY_DOT[task.priority])} />
        <span className="text-sm text-white truncate group-hover:text-blue-400 transition-colors">
          {task.title}
        </span>
        {task.description && (
          <ListTodo className="w-3 h-3 text-white/15 flex-shrink-0" />
        )}
        {task.estimated_hours && (
          <span className="text-[10px] text-white/15 flex-shrink-0">{task.estimated_hours}ч</span>
        )}
        {task.created_by_bot && (
          <span
            className="flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-purple-500/15 border border-purple-500/25 text-[10px] text-purple-200 flex-shrink-0"
            title={
              task.source_message
                ? `Бот завёл задачу из сообщения:\n\n${task.source_message.slice(0, 400)}`
                : 'Задачу завёл бот из сообщения в чате'
            }
          >
            <Bot className="w-3 h-3" />
            бот
          </span>
        )}
      </div>

      {/* Assignee */}
      <div className="flex items-center gap-1.5">
        {task.assignee_name ? (
          <>
            <div className="w-5 h-5 rounded-full bg-gradient-to-br from-blue-500/40 to-purple-500/40 flex items-center justify-center border border-white/10 flex-shrink-0">
              <span className="text-[9px] text-white/70">{task.assignee_name.charAt(0).toUpperCase()}</span>
            </div>
            <span className="text-xs text-white/50 truncate">{task.assignee_name}</span>
          </>
        ) : (
          <span className="text-xs text-white/15">—</span>
        )}
      </div>

      {/* Due date */}
      <div>
        {task.due_date ? (
          <span className="text-xs text-white/40">
            {new Date(task.due_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
          </span>
        ) : (
          <span className="text-xs text-white/10">—</span>
        )}
      </div>

      {/* Priority */}
      <div>
        <span className={clsx('text-xs font-medium', PRIORITY_COLORS[task.priority])}>
          {task.priority >= 3 && <Flame className="w-3 h-3 inline mr-0.5" />}
          {PRIORITY_LABELS[task.priority] ?? ''}
        </span>
      </div>
    </div>
  );
}

// ============================================================
// MAIN PAGE
// ============================================================

export default function AllTasksPage() {
  const navigate = useNavigate();
  const [groups, setGroups] = useState<AllTasksProjectGroup[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [collapsedProjects, setCollapsedProjects] = useState<Record<number, boolean>>({});
  const [collapsedStatuses, setCollapsedStatuses] = useState<Record<string, boolean>>({});
  // «Создано ботом»: бот заводит задачи из чата по кнопке «Создать», и иногда
  // нужно посмотреть только их — например, разобрать, что он нанёс за неделю.
  const [botOnly, setBotOnly] = useState(false);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const filters: AllTasksFilters = {};
      if (statusFilter !== 'all') filters.status = statusFilter;
      if (searchQuery) filters.search = searchQuery;
      if (botOnly) filters.created_by_bot = true;
      const data = await api.getAllTasks(filters);
      setGroups(data);
    } catch (err) {
      console.error('Failed to fetch all tasks:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [statusFilter, botOnly]);

  useEffect(() => {
    const timeout = setTimeout(() => { fetchData(); }, 300);
    return () => clearTimeout(timeout);
  }, [searchQuery]);

  const toggleProject = (pid: number) => {
    setCollapsedProjects((prev) => ({ ...prev, [pid]: !prev[pid] }));
  };

  const toggleStatus = (key: string) => {
    setCollapsedStatuses((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Total task count
  const totalTasks = useMemo(() => {
    return groups.reduce((sum, g) => {
      return sum + Object.values(g.status_groups).reduce((s, tasks) => s + tasks.length, 0);
    }, 0);
  }, [groups]);

  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20">
            <ListTodo className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Все задачи</h1>
            <p className="text-[11px] text-white/30">{totalTasks} задач по всем проектам</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4 border-b border-white/[0.06] pb-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/25" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Поиск задач..."
            className="pl-8 pr-3 py-1.5 w-full bg-white/[0.04] border border-white/[0.08] rounded-lg text-white placeholder-white/25 focus:outline-none focus:ring-1 focus:ring-purple-500/40 text-xs"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as TaskStatus | 'all')}
          className="px-3 py-1.5 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/40"
        >
          <option value="all">Все статусы</option>
          {TASK_STATUS_ORDER.map((s) => (
            <option key={s} value={s}>{TASK_STATUS_LABELS[s]}</option>
          ))}
        </select>
        <button
          onClick={() => setBotOnly((v) => !v)}
          title="Показать только задачи, которые завёл бот из чата"
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors',
            botOnly
              ? 'bg-purple-500/20 border-purple-500/40 text-purple-200'
              : 'bg-white/[0.04] border-white/[0.08] text-white/50 hover:text-white/80'
          )}
        >
          <Bot className="w-3.5 h-3.5" />
          Создано ботом
        </button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-8 h-8 border-2 border-purple-400 border-t-transparent rounded-full" />
        </div>
      )}

      {/* Content: grouped by project → status */}
      {!isLoading && (
        <div className="space-y-2">
          {groups.length === 0 && (
            <div className="flex flex-col items-center py-16 text-center">
              <ListTodo className="w-10 h-10 text-white/10 mb-3" />
              <p className="text-sm text-white/30">Нет задач</p>
            </div>
          )}

          {groups.map((group) => {
            const projectCollapsed = collapsedProjects[group.project_id] ?? false;
            const taskCount = Object.values(group.status_groups).reduce((s, t) => s + t.length, 0);

            return (
              <div key={group.project_id} className="bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden">
                {/* Project header */}
                <button
                  onClick={() => toggleProject(group.project_id)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.03] transition-colors"
                >
                  {projectCollapsed
                    ? <ChevronRight className="w-4 h-4 text-white/30" />
                    : <ChevronDown className="w-4 h-4 text-white/30" />
                  }
                  <div
                    className="w-2 h-6 rounded-full flex-shrink-0"
                    style={{ backgroundColor: group.project_color || '#3b82f6' }}
                  />
                  <span className="text-sm font-semibold text-white">{group.project_name}</span>
                  <span className="text-xs text-white/20 ml-1">{taskCount}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); navigate(`/projects/${group.project_id}`); }}
                    className="ml-auto text-[10px] text-white/20 hover:text-white/40 transition-colors"
                  >
                    Открыть проект →
                  </button>
                </button>

                {/* Status groups within project */}
                <AnimatePresence>
                  {!projectCollapsed && TASK_STATUS_ORDER.map((status) => {
                    const tasks = group.status_groups[status];
                    if (!tasks || tasks.length === 0) return null;

                    const key = `${group.project_id}-${status}`;
                    const statusCollapsed = collapsedStatuses[key] ?? false;

                    return (
                      <motion.div
                        key={key}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="border-t border-white/[0.04]"
                      >
                        {/* Status header */}
                        <button
                          onClick={() => toggleStatus(key)}
                          className="w-full flex items-center gap-2.5 px-4 pl-10 py-2 hover:bg-white/[0.02] transition-colors"
                        >
                          {statusCollapsed
                            ? <ChevronRight className="w-3.5 h-3.5 text-white/20" />
                            : <ChevronDown className="w-3.5 h-3.5 text-white/20" />
                          }
                          <div className={clsx('w-2 h-2 rounded-full', TASK_STATUS_DOT[status])} />
                          <span className={clsx('text-[11px] font-semibold uppercase tracking-wide', TASK_STATUS_COLORS[status].replace(/bg-\S+/, ''))}>
                            {TASK_STATUS_LABELS[status]}
                          </span>
                          <span className="text-[11px] text-white/20">{tasks.length}</span>
                        </button>

                        {/* Column headers */}
                        {!statusCollapsed && (
                          <div className="grid grid-cols-[1fr_120px_100px_80px] gap-2 px-4 py-1 text-[10px] uppercase tracking-wider text-white/15 border-b border-white/[0.03]">
                            <span className="pl-7">Название</span>
                            <span>Исполнитель</span>
                            <span>Дедлайн</span>
                            <span>Приоритет</span>
                          </div>
                        )}

                        {/* Task rows — клик открывает задачу через deep-link
                            (ProjectDetailPage читает ?task=ID и открывает модалку) */}
                        {!statusCollapsed && tasks.map((task) => (
                          <TaskRow
                            key={task.id}
                            task={task}
                            onClick={() => navigate(`/projects/${group.project_id}/tasks/${task.id}`)}
                          />
                        ))}
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
