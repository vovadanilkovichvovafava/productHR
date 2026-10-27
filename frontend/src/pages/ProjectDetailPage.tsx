import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  DndContext,
  DragOverlay,
  closestCorners,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { useDroppable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import {
  ChevronLeft,
  FolderKanban,
  Users,
  ListTodo,
  LayoutDashboard,
  Calendar,
  Clock,
  Target,
  Plus,
  Edit,
  Trash2,
  CheckCircle2,
  Pause,
  XCircle,
  AlertTriangle,
  BarChart3,
  LayoutGrid,
  List,
  ChevronDown,
  ChevronRight as ChevronRightIcon,
  MessageSquare,
  Paperclip,
  Sparkles,
  Filter,
  X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { useProjectStore } from '@/stores/projectStore';
import { useUrlTab } from '@/hooks/useUrlTab';
import type {
  Project,
  ProjectStatus,
  TaskStatus,
  ProjectMember,
  ProjectMilestone,
  ProjectRole,
  ProjectTaskStatusDef,
} from '@/services/api/projects';
import * as api from '@/services/api';
import { ProjectForm, TaskDetailModal, AITaskModal } from '@/components/projects';
import { backdropClose } from '@/utils/backdropClose';

// ============================================================
// CONSTANTS
// ============================================================

const STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: 'Планирование',
  active: 'В разработке',
  on_hold: 'На паузе',
  completed: 'Завершён',
  cancelled: 'Отменён',
};

const STATUS_COLORS: Record<ProjectStatus, string> = {
  planning: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  on_hold: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  completed: 'bg-green-500/20 text-green-400 border-green-500/30',
  cancelled: 'bg-red-500/20 text-red-400 border-red-500/30',
};

const STATUS_ICONS: Record<ProjectStatus, React.ReactNode> = {
  planning: <Clock className="w-4 h-4" />,
  active: <FolderKanban className="w-4 h-4" />,
  on_hold: <Pause className="w-4 h-4" />,
  completed: <CheckCircle2 className="w-4 h-4" />,
  cancelled: <XCircle className="w-4 h-4" />,
};

const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  backlog: 'Бэклог',
  todo: 'К выполнению',
  in_progress: 'В работе',
  review: 'Ревью',
  done: 'Готово',
  cancelled: 'Отменена',
};

const TASK_STATUS_COLORS: Record<TaskStatus, string> = {
  backlog: 'bg-white/10 text-white/50 border-white/10',
  todo: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  in_progress: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  review: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  done: 'bg-green-500/20 text-green-400 border-green-500/30',
  cancelled: 'bg-red-500/20 text-red-400 border-red-500/30',
};

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Низкий',
  1: 'Нормальный',
  2: 'Высокий',
  3: 'Критический',
};

const PRIORITY_COLORS: Record<number, string> = {
  0: 'text-white/40',
  1: 'text-blue-400',
  2: 'text-amber-400',
  3: 'text-red-400',
};

const ROLE_LABELS: Record<ProjectRole, string> = {
  manager: 'Менеджер',
  developer: 'Разработчик',
  reviewer: 'Ревьюер',
  observer: 'Наблюдатель',
};

type Tab = 'overview' | 'tasks' | 'team';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Обзор', icon: <LayoutDashboard className="w-4 h-4" /> },
  { id: 'tasks', label: 'Задачи', icon: <ListTodo className="w-4 h-4" /> },
  { id: 'team', label: 'Команда', icon: <Users className="w-4 h-4" /> },
];

// ============================================================
// OVERVIEW TAB
// ============================================================

function OverviewTab({
  milestones,
  project,
  onProjectUpdated,
}: {
  milestones: ProjectMilestone[];
  project: Project;
  onProjectUpdated?: () => void;
}) {
  const totalTasks = Object.values(project.task_counts || {}).reduce((s: number, n: number) => s + n, 0);
  const doneTasks = project.task_counts?.done || 0;
  const [manualPercent, setManualPercent] = useState(project.progress_percent);
  const [progressMode, setProgressMode] = useState(project.progress_mode || 'auto');
  const [saving, setSaving] = useState(false);

  const handleProgressModeChange = async (mode: string) => {
    setProgressMode(mode);
    setSaving(true);
    try {
      await api.updateProject(project.id, { progress_mode: mode } as any);
      toast.success(mode === 'auto' ? 'Авто-расчёт включён' : 'Ручной режим включён');
      onProjectUpdated?.();
    } catch {
      toast.error('Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleManualSave = async () => {
    setSaving(true);
    try {
      await api.updateProject(project.id, { progress_percent: manualPercent, progress_mode: 'manual' } as any);
      toast.success(`Прогресс: ${manualPercent}%`);
      onProjectUpdated?.();
    } catch {
      toast.error('Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Info card */}
      <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div>
            <span className="text-xs text-white/40 uppercase tracking-wider">Статус</span>
            <div className="mt-1">
              <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 text-sm font-medium rounded-lg border', STATUS_COLORS[project.status])}>
                {STATUS_ICONS[project.status]}
                {STATUS_LABELS[project.status]}
              </span>
            </div>
          </div>
          <div>
            <span className="text-xs text-white/40 uppercase tracking-wider">Приоритет</span>
            <p className={clsx('mt-1 text-sm font-medium', PRIORITY_COLORS[project.priority] || PRIORITY_COLORS[1])}>
              {PRIORITY_LABELS[project.priority] ?? PRIORITY_LABELS[1]}
            </p>
          </div>
          <div>
            <span className="text-xs text-white/40 uppercase tracking-wider">Участники</span>
            <p className="mt-1 text-sm font-medium text-white">{project.member_count}</p>
          </div>
          <div>
            <span className="text-xs text-white/40 uppercase tracking-wider">Задачи</span>
            <p className="mt-1 text-sm font-medium text-white">{doneTasks} / {totalTasks}</p>
          </div>
        </div>

        {/* Description */}
        {project.description && (
          <div className="mt-6 pt-6 border-t border-white/10">
            <span className="text-xs text-white/40 uppercase tracking-wider">Описание</span>
            <p className="mt-2 text-sm text-white/60 whitespace-pre-wrap">{project.description}</p>
          </div>
        )}
      </div>

      {/* Progress */}
      <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-blue-400" />
            Прогресс
          </h3>
          {/* Auto / Manual toggle */}
          <div className="flex items-center bg-white/5 rounded-lg border border-white/10 p-0.5">
            <button
              onClick={() => handleProgressModeChange('auto')}
              disabled={saving}
              className={clsx(
                'px-3 py-1 text-[11px] font-medium rounded-md transition-all',
                progressMode === 'auto'
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-white/30 hover:text-white/50'
              )}
            >
              Авто
            </button>
            <button
              onClick={() => handleProgressModeChange('manual')}
              disabled={saving}
              className={clsx(
                'px-3 py-1 text-[11px] font-medium rounded-md transition-all',
                progressMode === 'manual'
                  ? 'bg-amber-500/20 text-amber-400'
                  : 'text-white/30 hover:text-white/50'
              )}
            >
              Вручную
            </button>
          </div>
        </div>

        {progressMode === 'auto' ? (
          <>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs text-white/40">Рассчитывается из задач ({doneTasks}/{totalTasks})</span>
              <span className="text-sm font-medium text-white">{project.progress_percent}%</span>
            </div>
            <div className="h-3 bg-white/10 rounded-full overflow-hidden">
              <motion.div
                className="h-full rounded-full"
                style={{ backgroundColor: project.color || '#3b82f6' }}
                initial={{ width: 0 }}
                animate={{ width: `${project.progress_percent}%` }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
              />
            </div>
          </>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs text-white/40">Установите вручную</span>
              <span className="text-sm font-bold text-amber-400">{manualPercent}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={manualPercent}
              onChange={(e) => setManualPercent(Number(e.target.value))}
              className="w-full h-2 bg-white/10 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-amber-400 [&::-webkit-slider-thumb]:cursor-pointer"
            />
            <div className="flex items-center justify-between mt-2 text-[10px] text-white/20">
              <span>0%</span>
              <span>25%</span>
              <span>50%</span>
              <span>75%</span>
              <span>100%</span>
            </div>
            <button
              onClick={handleManualSave}
              disabled={saving || manualPercent === project.progress_percent}
              className="mt-3 w-full py-2 text-xs font-medium text-white bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/30 rounded-lg transition-colors disabled:opacity-30"
            >
              {saving ? 'Сохранение...' : 'Сохранить прогресс'}
            </button>
          </>
        )}
      </div>

      {/* Dates */}
      <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Calendar className="w-4 h-4 text-blue-400" />
          Сроки
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <span className="text-xs text-white/40">Начало</span>
            <p className="text-sm text-white/70 mt-1">
              {project.start_date
                ? new Date(project.start_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
                : 'Не указано'}
            </p>
          </div>
          <div>
            <span className="text-xs text-white/40">Целевая дата</span>
            <p className="text-sm text-white/70 mt-1">
              {project.target_date
                ? new Date(project.target_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
                : 'Не указано'}
            </p>
          </div>
          <div>
            <span className="text-xs text-white/40">Прогноз</span>
            <p className="text-sm text-white/70 mt-1">
              {project.predicted_date
                ? new Date(project.predicted_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
                : 'Нет данных'}
            </p>
          </div>
        </div>
      </div>

      {/* Milestones */}
      <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Target className="w-4 h-4 text-blue-400" />
          Вехи ({milestones.length})
        </h3>
        {milestones.length === 0 ? (
          <p className="text-sm text-white/30">Вехи ещё не созданы</p>
        ) : (
          <div className="space-y-3">
            {milestones.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between p-3 bg-white/5 rounded-xl border border-white/5"
              >
                <div className="flex items-center gap-3">
                  {m.completed_at ? (
                    <CheckCircle2 className="w-4 h-4 text-green-400" />
                  ) : (
                    <Target className="w-4 h-4 text-white/30" />
                  )}
                  <div>
                    <p className={clsx('text-sm font-medium', m.completed_at ? 'text-white/40 line-through' : 'text-white')}>
                      {m.name}
                    </p>
                    {m.description && <p className="text-xs text-white/30 mt-0.5">{m.description}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs text-white/40">
                  {m.task_count > 0 && <span>{m.task_count} задач</span>}
                  {m.target_date && (
                    <span>{new Date(m.target_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// TASKS TAB (BOARD + LIST)
// ============================================================

const KANBAN_COLUMNS: TaskStatus[] = ['backlog', 'todo', 'in_progress', 'review', 'done'];

type TaskViewMode = 'board' | 'list';

// Shared task card for board view
function TaskCard({ task, onClick, selected, onToggleSelect }: { task: api.ProjectTask; onClick?: () => void; selected?: boolean; onToggleSelect?: (id: number) => void }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'bg-white/5 backdrop-blur-sm border rounded-xl p-3 hover:bg-white/[0.07] transition-colors cursor-pointer group/card relative',
        selected ? 'border-blue-500/50 bg-blue-500/5' : 'border-white/10'
      )}
      onClick={onClick}
    >
      {/* Selection checkbox */}
      {onToggleSelect && (
        <div
          className={clsx(
            'absolute top-2 right-2 z-10 transition-opacity',
            selected ? 'opacity-100' : 'opacity-0 group-hover/card:opacity-100'
          )}
        >
          <input
            type="checkbox"
            checked={selected || false}
            onChange={(e) => {
              e.stopPropagation();
              onToggleSelect(task.id);
            }}
            onClick={(e) => e.stopPropagation()}
            className="w-4 h-4 rounded border-white/20 bg-white/10 text-blue-500 focus:ring-blue-500/30 cursor-pointer"
          />
        </div>
      )}
      <p className="text-sm text-white font-medium mb-2">{task.title}</p>
      {task.description && (
        <p className="text-xs text-white/30 line-clamp-2 mb-2">{task.description}</p>
      )}
      <div className="flex items-center justify-between text-xs">
        <span className={clsx('font-medium', PRIORITY_COLORS[task.priority] || PRIORITY_COLORS[1])}>
          {PRIORITY_LABELS[task.priority] ?? ''}
        </span>
        <div className="flex items-center gap-2 text-white/30">
          {task.assignee_name && (
            <div className="flex items-center gap-1">
              <div className="w-4 h-4 rounded-full bg-gradient-to-br from-blue-500/40 to-purple-500/40 flex items-center justify-center border border-white/10">
                <span className="text-[8px] text-white/70">{task.assignee_name.charAt(0).toUpperCase()}</span>
              </div>
              <span className="truncate max-w-[80px]">{task.assignee_name}</span>
            </div>
          )}
          {task.due_date && (
            <span>{new Date(task.due_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 mt-2">
        {task.estimated_hours != null && task.estimated_hours > 0 && (
          <span className="text-[10px] text-white/20">{task.estimated_hours}ч</span>
        )}
        {task.subtask_count > 0 && (
          <span className="text-[10px] text-white/30">
            &#8627; {task.subtasks_done}/{task.subtask_count}
          </span>
        )}
        {task.comment_count > 0 && (
          <div className="flex items-center gap-0.5 text-white/25">
            <MessageSquare className="w-3 h-3" />
            <span className="text-[10px]">{task.comment_count}</span>
          </div>
        )}
        {task.attachment_count > 0 && (
          <div className="flex items-center gap-0.5 text-white/25">
            <Paperclip className="w-3 h-3" />
            <span className="text-[10px]">{task.attachment_count}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// Draggable wrapper for TaskCard (used in board view)
function DraggableTaskCard({ task, onTaskClick, selected, onToggleSelect }: { task: api.ProjectTask; onTaskClick?: (taskId: number) => void; selected?: boolean; onToggleSelect?: (id: number) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: task.id,
    data: { type: 'task', task, status: task.status },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <TaskCard task={task} onClick={() => onTaskClick?.(task.id)} selected={selected} onToggleSelect={onToggleSelect} />
    </div>
  );
}

// Droppable column wrapper for board view
function DroppableColumn({ status, isOver, children }: { status: string; isOver: boolean; children: React.ReactNode }) {
  const { setNodeRef } = useDroppable({ id: status });
  return (
    <div
      ref={setNodeRef}
      className={clsx(
        'space-y-2 min-h-[100px] rounded-xl transition-colors duration-200',
        isOver && 'bg-white/[0.04] ring-1 ring-white/10',
      )}
    >
      {children}
    </div>
  );
}

// List view: tasks grouped by status (like ClickUp List view)
function TaskListView({ columns, statuses, onTaskClick, selectedTaskIds, onToggleSelect }: { columns: api.TaskKanbanColumn[]; statuses: ProjectTaskStatusDef[]; onTaskClick?: (taskId: number) => void; selectedTaskIds?: Set<number>; onToggleSelect?: (id: number) => void }) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggle = (status: string) => {
    setCollapsed((prev) => ({ ...prev, [status]: !prev[status] }));
  };

  // Use custom statuses order if available, otherwise KANBAN_COLUMNS
  const statusOrder = statuses.length > 0
    ? statuses.map((s) => s.slug)
    : KANBAN_COLUMNS as string[];

  const statusColorMap: Record<string, string> = {};
  const statusLabelMap: Record<string, string> = {};
  for (const s of statuses) {
    statusColorMap[s.slug] = s.color;
    statusLabelMap[s.slug] = s.name;
  }

  return (
    <div className="bg-white/[0.02] border border-white/10 rounded-2xl overflow-hidden">
      {statusOrder.map((status) => {
        const col = columns.find((c) => c.status === status);
        const tasks = col?.tasks || [];
        const count = col?.count || 0;
        const isCollapsed = collapsed[status] ?? false;
        const label = statusLabelMap[status] || TASK_STATUS_LABELS[status as TaskStatus] || status;
        const dotColor = statusColorMap[status];
        const badgeClass = TASK_STATUS_COLORS[status as TaskStatus] || 'bg-white/10 text-white/50 border-white/10';

        return (
          <div key={status} className="border-b border-white/5 last:border-b-0">
            {/* Group header */}
            <button
              onClick={() => toggle(status)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.03] transition-colors"
            >
              {isCollapsed
                ? <ChevronRightIcon className="w-4 h-4 text-white/30" />
                : <ChevronDown className="w-4 h-4 text-white/30" />
              }
              {dotColor ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold rounded-md border border-white/10">
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: dotColor }} />
                  {label}
                </span>
              ) : (
                <span className={clsx('inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-md border', badgeClass)}>
                  {label}
                </span>
              )}
              <span className="text-xs text-white/30">{count}</span>
            </button>

            {/* Table header */}
            {!isCollapsed && tasks.length > 0 && (
              <div className="grid grid-cols-[28px_1fr_120px_100px_80px] gap-2 px-4 py-1.5 text-[10px] uppercase tracking-wider text-white/20 border-b border-white/5">
                <span />
                <span className="pl-7">Название</span>
                <span>Исполнитель</span>
                <span>Дедлайн</span>
                <span>Приоритет</span>
              </div>
            )}

            {/* Task rows */}
            <AnimatePresence>
              {!isCollapsed && tasks.map((task) => (
                <motion.div
                  key={task.id}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className={clsx(
                    'grid grid-cols-[28px_1fr_120px_100px_80px] gap-2 px-4 py-2.5 items-center hover:bg-white/[0.03] transition-colors cursor-pointer border-b border-white/[0.03] last:border-b-0',
                    selectedTaskIds?.has(task.id) && 'bg-blue-500/5'
                  )}
                  onClick={() => onTaskClick?.(task.id)}
                >
                  {/* Checkbox */}
                  <div className="flex items-center justify-center">
                    {onToggleSelect && (
                      <input
                        type="checkbox"
                        checked={selectedTaskIds?.has(task.id) || false}
                        onChange={(e) => {
                          e.stopPropagation();
                          onToggleSelect(task.id);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-blue-500 focus:ring-blue-500/30 cursor-pointer"
                      />
                    )}
                  </div>
                  {/* Name */}
                  <div className="flex items-center gap-2 min-w-0 pl-7">
                    <div className={clsx('w-2 h-2 rounded-full flex-shrink-0', {
                      'bg-red-400': task.priority >= 3,
                      'bg-amber-400': task.priority === 2,
                      'bg-blue-400': task.priority === 1,
                      'bg-white/20': task.priority === 0,
                    })} />
                    <span className="text-sm text-white truncate">{task.title}</span>
                    {task.description && (
                      <span className="text-white/20 flex-shrink-0" title="Есть описание">
                        <ListTodo className="w-3 h-3" />
                      </span>
                    )}
                    {task.estimated_hours != null && task.estimated_hours > 0 && (
                      <span className="text-[10px] text-white/20 flex-shrink-0">{task.estimated_hours}ч</span>
                    )}
                    {task.subtask_count > 0 && (
                      <span className="text-[10px] text-white/30 flex-shrink-0">
                        &#8627; {task.subtasks_done}/{task.subtask_count}
                      </span>
                    )}
                    {task.comment_count > 0 && (
                      <div className="flex items-center gap-0.5 text-white/25 flex-shrink-0">
                        <MessageSquare className="w-3 h-3" />
                        <span className="text-[10px]">{task.comment_count}</span>
                      </div>
                    )}
                    {task.attachment_count > 0 && (
                      <div className="flex items-center gap-0.5 text-white/25 flex-shrink-0">
                        <Paperclip className="w-3 h-3" />
                        <span className="text-[10px]">{task.attachment_count}</span>
                      </div>
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
                      <span className="text-xs text-white/15">—</span>
                    )}
                  </div>

                  {/* Priority */}
                  <div>
                    <span className={clsx('text-xs font-medium', PRIORITY_COLORS[task.priority] || PRIORITY_COLORS[1])}>
                      {PRIORITY_LABELS[task.priority] ?? ''}
                    </span>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>

            {/* Add task inline */}
            {!isCollapsed && (
              <div className="px-4 py-2 pl-11">
                <span className="text-xs text-white/15 hover:text-white/30 cursor-pointer transition-colors">
                  + Add Task
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// Board view: kanban columns with drag & drop
function TaskBoardView({
  columns,
  statuses,
  projectId,
  onTaskMoved,
  onTaskClick,
  selectedTaskIds,
  onToggleSelect,
}: {
  columns: api.TaskKanbanColumn[];
  statuses: ProjectTaskStatusDef[];
  projectId: number;
  onTaskMoved: () => void;
  onTaskClick?: (taskId: number) => void;
  selectedTaskIds?: Set<number>;
  onToggleSelect?: (id: number) => void;
}) {
  // Local state for optimistic updates during drag
  const [localColumns, setLocalColumns] = useState(columns);
  useEffect(() => { setLocalColumns(columns); }, [columns]);

  const [activeTask, setActiveTask] = useState<api.ProjectTask | null>(null);
  const [overColumnId, setOverColumnId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
  );

  // Build ordered status list
  const statusOrder = statuses.length > 0
    ? statuses.map((s) => s.slug)
    : KANBAN_COLUMNS as string[];

  const statusColorMap: Record<string, string> = {};
  const statusLabelMap: Record<string, string> = {};
  for (const s of statuses) {
    statusColorMap[s.slug] = s.color;
    statusLabelMap[s.slug] = s.name;
  }

  // Helper: find which column a task belongs to
  const findTaskColumn = useCallback((taskId: number): string | undefined => {
    for (const col of localColumns) {
      if (col.tasks.some((t) => t.id === taskId)) return col.status;
    }
    return undefined;
  }, [localColumns]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const task = event.active.data.current?.task as api.ProjectTask | undefined;
    if (task) setActiveTask(task);
  }, []);

  const handleDragOver = useCallback((event: { over: { id: string | number } | null }) => {
    if (!event.over) {
      setOverColumnId(null);
      return;
    }
    const overId = String(event.over.id);
    // If hovering over a column directly
    if (statusOrder.includes(overId)) {
      setOverColumnId(overId);
    } else {
      // Hovering over a task — find its column
      const col = findTaskColumn(Number(event.over.id));
      setOverColumnId(col || null);
    }
  }, [statusOrder, findTaskColumn]);

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    setActiveTask(null);
    setOverColumnId(null);

    const { active, over } = event;
    if (!over) return;

    const taskId = Number(active.id);
    const sourceStatus = findTaskColumn(taskId);
    if (!sourceStatus) return;

    // Determine target status: if dropped on a column, use that; if on a task, use the task's column
    let targetStatus: string;
    const overId = String(over.id);
    if (statusOrder.includes(overId)) {
      targetStatus = overId;
    } else {
      const col = findTaskColumn(Number(over.id));
      if (!col) return;
      targetStatus = col;
    }

    // No change
    if (sourceStatus === targetStatus) return;

    // Optimistic update: move task between columns locally
    setLocalColumns((prev) => {
      const next = prev.map((col) => {
        if (col.status === sourceStatus) {
          const remaining = col.tasks.filter((t) => t.id !== taskId);
          return { ...col, tasks: remaining, count: remaining.length };
        }
        if (col.status === targetStatus) {
          const movedTask = prev
            .find((c) => c.status === sourceStatus)
            ?.tasks.find((t) => t.id === taskId);
          if (!movedTask) return col;
          const updated = { ...movedTask, status: targetStatus };
          return { ...col, tasks: [...col.tasks, updated], count: col.tasks.length + 1 };
        }
        return col;
      });
      return next;
    });

    // Call API
    try {
      await api.updateProjectTask(projectId, taskId, { status: targetStatus as TaskStatus });
      onTaskMoved();
    } catch {
      toast.error('Не удалось переместить задачу');
      // Revert optimistic update
      setLocalColumns(columns);
    }
  }, [findTaskColumn, statusOrder, projectId, columns, onTaskMoved]);

  const columnMap = new Map(localColumns.map((c) => [c.status, c]));

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto pb-4">
        {statusOrder.map((status) => {
          const col = columnMap.get(status);
          const tasks = col?.tasks || [];
          const count = col?.count || 0;
          const label = statusLabelMap[status] || TASK_STATUS_LABELS[status as TaskStatus] || status;
          const dotColor = statusColorMap[status];
          const badgeClass = TASK_STATUS_COLORS[status as TaskStatus] || 'bg-white/10 text-white/50 border-white/10';
          const taskIds = tasks.map((t) => t.id);

          return (
            <div key={status} className="flex-shrink-0 w-72">
              <div className="flex items-center justify-between mb-3 px-1">
                <div className="flex items-center gap-2">
                  {dotColor ? (
                    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-md border border-white/10">
                      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: dotColor }} />
                      {label}
                    </span>
                  ) : (
                    <span className={clsx('inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md border', badgeClass)}>
                      {label}
                    </span>
                  )}
                  <span className="text-xs text-white/30">{count}</span>
                </div>
              </div>
              <SortableContext items={taskIds} strategy={verticalListSortingStrategy}>
                <DroppableColumn status={status} isOver={overColumnId === status}>
                  {tasks.map((task) => (
                    <DraggableTaskCard key={task.id} task={task} onTaskClick={onTaskClick} selected={selectedTaskIds?.has(task.id)} onToggleSelect={onToggleSelect} />
                  ))}
                  {tasks.length === 0 && (
                    <div className="flex items-center justify-center h-20 text-xs text-white/20 border border-dashed border-white/10 rounded-xl">
                      Нет задач
                    </div>
                  )}
                </DroppableColumn>
              </SortableContext>
            </div>
          );
        })}
      </div>

      {/* Drag overlay: floating card following cursor */}
      <DragOverlay>
        {activeTask ? (
          <div className="opacity-90 rotate-2 scale-105">
            <TaskCard task={activeTask} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

// Main tasks tab with view mode toggle
function TasksTab({
  projectId,
  members,
}: {
  projectId: number;
  members: ProjectMember[];
}) {
  const { taskKanban, isKanbanLoading, fetchTaskKanban } = useProjectStore();
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [showAIModal, setShowAIModal] = useState(false);
  const [viewMode, setViewMode] = useState<TaskViewMode>('board');
  const [statuses, setStatuses] = useState<ProjectTaskStatusDef[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  // Из notification deep-link приходим с ?task=ID&comment=ID — открываем задачу
  // и пробрасываем comment в TaskDetailModal для скролла.
  const [searchParams, setSearchParams] = useSearchParams();
  const [scrollToCommentId, setScrollToCommentId] = useState<number | null>(null);
  useEffect(() => {
    const taskParam = searchParams.get('task');
    const commentParam = searchParams.get('comment');
    if (taskParam) {
      const taskIdNum = parseInt(taskParam);
      if (!isNaN(taskIdNum)) {
        setSelectedTaskId(taskIdNum);
        if (commentParam) {
          const cid = parseInt(commentParam);
          if (!isNaN(cid)) setScrollToCommentId(cid);
        }
        // Чистим query чтобы при перезагрузке модалка не открывалась повторно
        const next = new URLSearchParams(searchParams);
        next.delete('task');
        next.delete('comment');
        setSearchParams(next, { replace: true });
      }
    }
  }, [searchParams, setSearchParams]);

  // Filters
  const [showFilters, setShowFilters] = useState(false);
  const [assigneeFilter, setAssigneeFilter] = useState<number | 'all'>('all');
  const [priorityFilter, setPriorityFilter] = useState<number | 'all'>('all');
  const [deadlineFilter, setDeadlineFilter] = useState<string>('all');

  // Bulk selection
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    fetchTaskKanban(projectId);
    api.getProjectStatuses(projectId).then(setStatuses).catch(() => setStatuses([]));
  }, [projectId, fetchTaskKanban]);

  // Filter logic
  const filterTasks = useCallback((tasks: api.ProjectTask[]) => {
    return tasks.filter((task) => {
      if (assigneeFilter !== 'all' && task.assignee_id !== assigneeFilter) return false;
      if (priorityFilter !== 'all' && task.priority !== priorityFilter) return false;
      if (deadlineFilter !== 'all') {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        const weekEnd = new Date(today);
        weekEnd.setDate(weekEnd.getDate() + 7);

        if (deadlineFilter === 'overdue') {
          if (!task.due_date || new Date(task.due_date) >= today) return false;
        } else if (deadlineFilter === 'today') {
          if (!task.due_date) return false;
          const d = new Date(task.due_date);
          if (d < today || d >= tomorrow) return false;
        } else if (deadlineFilter === 'week') {
          if (!task.due_date) return false;
          const d = new Date(task.due_date);
          if (d < today || d >= weekEnd) return false;
        } else if (deadlineFilter === 'none') {
          if (task.due_date) return false;
        }
      }
      return true;
    });
  }, [assigneeFilter, priorityFilter, deadlineFilter]);

  const activeFilterCount = (assigneeFilter !== 'all' ? 1 : 0) + (priorityFilter !== 'all' ? 1 : 0) + (deadlineFilter !== 'all' ? 1 : 0);
  const hasActiveFilters = activeFilterCount > 0;

  const resetFilters = () => {
    setAssigneeFilter('all');
    setPriorityFilter('all');
    setDeadlineFilter('all');
  };

  // Toggle selection
  const toggleSelectTask = useCallback((taskId: number) => {
    setSelectedTaskIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  }, []);

  // Bulk handlers
  const handleBulkMove = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const status = e.target.value;
    if (!status) return;
    try {
      await api.bulkMoveTasks(projectId, { task_ids: [...selectedTaskIds], status: status as api.TaskStatus });
      toast.success(`${selectedTaskIds.size} задач перемещено`);
      setSelectedTaskIds(new Set());
      fetchTaskKanban(projectId);
    } catch {
      toast.error('Ошибка перемещения задач');
    }
    e.target.value = '';
  };

  const handleBulkPriority = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val === '') return;
    const priority = Number(val);
    try {
      await Promise.all([...selectedTaskIds].map((tid) => api.updateProjectTask(projectId, tid, { priority })));
      toast.success(`Приоритет обновлён для ${selectedTaskIds.size} задач`);
      setSelectedTaskIds(new Set());
      fetchTaskKanban(projectId);
    } catch {
      toast.error('Ошибка обновления приоритета');
    }
    e.target.value = '';
  };

  const handleBulkDelete = async () => {
    if (!confirm(`Удалить ${selectedTaskIds.size} задач?`)) return;
    try {
      await Promise.all([...selectedTaskIds].map((tid) => api.deleteProjectTask(projectId, tid)));
      toast.success(`${selectedTaskIds.size} задач удалено`);
      setSelectedTaskIds(new Set());
      fetchTaskKanban(projectId);
    } catch {
      toast.error('Ошибка удаления задач');
    }
  };

  if (isKanbanLoading && !taskKanban) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full" />
      </div>
    );
  }

  const columns = taskKanban?.columns || [];
  const filteredColumns = hasActiveFilters
    ? columns.map((col) => {
        const filtered = filterTasks(col.tasks);
        return { ...col, tasks: filtered, count: filtered.length };
      })
    : columns;

  return (
    <div>
      {/* Header with view toggle */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          {/* View mode toggle */}
          <div className="flex items-center bg-white/5 rounded-lg border border-white/10 p-0.5">
            <button
              onClick={() => setViewMode('board')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all',
                viewMode === 'board'
                  ? 'bg-white/10 text-white shadow-sm'
                  : 'text-white/40 hover:text-white/60'
              )}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              Доска
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all',
                viewMode === 'list'
                  ? 'bg-white/10 text-white shadow-sm'
                  : 'text-white/40 hover:text-white/60'
              )}
            >
              <List className="w-3.5 h-3.5" />
              Список
            </button>
          </div>

          {/* Filter toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={clsx(
              'relative flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg border transition-all',
              showFilters || hasActiveFilters
                ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                : 'bg-white/5 text-white/40 border-white/10 hover:text-white/60'
            )}
          >
            <Filter className="w-3.5 h-3.5" />
            {activeFilterCount > 0 && (
              <span className="absolute -top-1.5 -right-1.5 w-4 h-4 flex items-center justify-center text-[9px] font-bold bg-blue-500 text-white rounded-full">
                {activeFilterCount}
              </span>
            )}
          </button>

          <span className="text-xs text-white/30">{taskKanban?.total_count || 0} задач</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAIModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-gradient-to-r from-purple-500 to-blue-500 hover:from-purple-600 hover:to-blue-600 rounded-lg transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5" />
            AI задачи
          </button>
          <button
            onClick={() => setShowTaskForm(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-purple-500 hover:bg-purple-600 rounded-lg transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Задача
          </button>
        </div>
      </div>

      {/* Filter bar */}
      {showFilters && (
        <div className="flex flex-wrap gap-2 mb-4 p-3 bg-white/[0.03] border border-white/10 rounded-xl">
          <select
            value={assigneeFilter === 'all' ? 'all' : String(assigneeFilter)}
            onChange={(e) => setAssigneeFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500/30"
          >
            <option value="all">Исполнитель: Все</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>{m.user_name || m.user_email || `User ${m.user_id}`}</option>
            ))}
          </select>
          <select
            value={priorityFilter === 'all' ? 'all' : String(priorityFilter)}
            onChange={(e) => setPriorityFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500/30"
          >
            <option value="all">Приоритет: Все</option>
            <option value="0">Низкий</option>
            <option value="1">Нормальный</option>
            <option value="2">Высокий</option>
            <option value="3">Критический</option>
          </select>
          <select
            value={deadlineFilter}
            onChange={(e) => setDeadlineFilter(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500/30"
          >
            <option value="all">Дедлайн: Все</option>
            <option value="overdue">Просрочено</option>
            <option value="today">Сегодня</option>
            <option value="week">Эта неделя</option>
            <option value="none">Без дедлайна</option>
          </select>
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              className="flex items-center gap-1 px-3 py-1.5 text-xs text-white/50 hover:text-white/80 bg-white/5 border border-white/10 rounded-lg transition-colors"
            >
              <X className="w-3 h-3" />
              Сбросить
            </button>
          )}
        </div>
      )}

      {/* View content */}
      {viewMode === 'board' ? (
        <TaskBoardView columns={filteredColumns} statuses={statuses} projectId={projectId} onTaskMoved={() => fetchTaskKanban(projectId)} onTaskClick={setSelectedTaskId} selectedTaskIds={selectedTaskIds} onToggleSelect={toggleSelectTask} />
      ) : (
        <TaskListView columns={filteredColumns} statuses={statuses} onTaskClick={setSelectedTaskId} selectedTaskIds={selectedTaskIds} onToggleSelect={toggleSelectTask} />
      )}

      {/* Bulk action bar */}
      <AnimatePresence>
        {selectedTaskIds.size > 0 && (
          <motion.div
            initial={{ y: 100, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 100, opacity: 0 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-dark-900/95 backdrop-blur-xl border border-white/10 rounded-2xl px-5 py-3 flex items-center gap-4 shadow-2xl"
          >
            <span className="text-sm text-white font-medium">{selectedTaskIds.size} выбрано</span>
            <select
              onChange={handleBulkMove}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none"
              defaultValue=""
            >
              <option value="">Переместить...</option>
              {statuses.length > 0
                ? statuses.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)
                : KANBAN_COLUMNS.map((s) => <option key={s} value={s}>{TASK_STATUS_LABELS[s]}</option>)
              }
            </select>
            <select
              onChange={handleBulkPriority}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none"
              defaultValue=""
            >
              <option value="">Приоритет...</option>
              <option value="0">Низкий</option>
              <option value="1">Нормальный</option>
              <option value="2">Высокий</option>
              <option value="3">Критический</option>
            </select>
            <button onClick={handleBulkDelete} className="text-red-400 hover:text-red-300 text-xs font-medium transition-colors">
              Удалить
            </button>
            <button onClick={() => setSelectedTaskIds(new Set())} className="text-white/30 hover:text-white/50 text-xs transition-colors">
              Отмена
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create task modal (same component as detail) */}
      <TaskDetailModal
        isOpen={showTaskForm}
        mode="create"
        onClose={() => setShowTaskForm(false)}
        projectId={projectId}
        members={members}
        statuses={statuses}
        onTaskCreated={() => fetchTaskKanban(projectId)}
        onTaskUpdated={() => fetchTaskKanban(projectId)}
      />

      {/* Task detail/edit modal */}
      <TaskDetailModal
        isOpen={selectedTaskId !== null && !showTaskForm}
        onClose={() => { setSelectedTaskId(null); setScrollToCommentId(null); }}
        projectId={projectId}
        taskId={selectedTaskId!}
        members={members}
        statuses={statuses}
        scrollToCommentId={scrollToCommentId}
        onTaskUpdated={() => fetchTaskKanban(projectId)}
        onTaskDeleted={() => { setSelectedTaskId(null); fetchTaskKanban(projectId); }}
      />

      {/* AI Task creation modal */}
      <AITaskModal
        isOpen={showAIModal}
        onClose={() => setShowAIModal(false)}
        projectId={projectId}
        onTasksCreated={() => fetchTaskKanban(projectId)}
      />
    </div>
  );
}

// ============================================================
// TEAM TAB
// ============================================================

function TeamTab({
  members,
  isLoading,
  projectId,
  onMemberAdded,
}: {
  members: ProjectMember[];
  isLoading: boolean;
  projectId: number;
  onMemberAdded?: () => void;
}) {
  const [showAddForm, setShowAddForm] = useState(false);
  const [addUserId, setAddUserId] = useState<number | ''>('');
  const [addRole, setAddRole] = useState('developer');
  const [orgUsers, setOrgUsers] = useState<{id: number; user_id: number; user_name: string; user_email: string}[]>([]);
  const [adding, setAdding] = useState(false);

  const loadOrgUsers = async () => {
    try {
      const users = await api.getOrgMembers();
      setOrgUsers(users as any);
    } catch {}
  };

  const handleAdd = async () => {
    if (!addUserId) return;
    setAdding(true);
    try {
      await api.addProjectMember(projectId, { user_id: Number(addUserId), role: addRole as any });
      toast.success('Участник добавлен');
      setAddUserId('');
      setShowAddForm(false);
      onMemberAdded?.();
    } catch {
      toast.error('Не удалось добавить');
    } finally {
      setAdding(false);
    }
  };

  const memberIds = new Set(members.map(m => m.user_id));
  const availableUsers = orgUsers.filter(u => !memberIds.has(u.user_id));
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-4 animate-pulse">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-white/10" />
              <div className="flex-1">
                <div className="h-4 w-32 bg-white/10 rounded mb-1" />
                <div className="h-3 w-20 bg-white/5 rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (members.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="p-4 rounded-2xl bg-white/5 mb-4">
          <Users className="w-8 h-8 text-white/20" />
        </div>
        <h3 className="text-sm font-medium text-white/50 mb-1">Нет участников</h3>
        <p className="text-xs text-white/30 mb-4">Добавьте участников в проект</p>
        {!showAddForm ? (
          <button
            onClick={() => { setShowAddForm(true); loadOrgUsers(); }}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-500 hover:bg-blue-600 rounded-xl transition-colors"
          >
            <Plus className="w-4 h-4" />
            Добавить участника
          </button>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-sm bg-white/5 border border-white/10 rounded-xl p-4 space-y-3"
          >
            <select
              value={addUserId}
              onChange={(e) => setAddUserId(e.target.value ? Number(e.target.value) : '')}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none"
            >
              <option value="">Выберите сотрудника...</option>
              {availableUsers.map(u => (
                <option key={u.user_id} value={u.user_id}>{u.user_name} ({u.user_email})</option>
              ))}
            </select>
            <select
              value={addRole}
              onChange={(e) => setAddRole(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none"
            >
              <option value="manager">Менеджер</option>
              <option value="developer">Разработчик</option>
              <option value="reviewer">Ревьюер</option>
              <option value="observer">Наблюдатель</option>
            </select>
            <div className="flex gap-2">
              <button
                onClick={handleAdd}
                disabled={!addUserId || adding}
                className="flex-1 py-2 text-xs font-medium text-white bg-emerald-500 hover:bg-emerald-600 disabled:opacity-40 rounded-lg transition-colors"
              >
                {adding ? 'Добавляю...' : 'Добавить'}
              </button>
              <button
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 text-xs text-white/50 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
              >
                Отмена
              </button>
            </div>
          </motion.div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Add member button */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-white/30">{members.length} участников</span>
        <button
          onClick={() => { setShowAddForm(true); loadOrgUsers(); }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          Добавить
        </button>
      </div>

      {/* Add member form */}
      {showAddForm && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3"
        >
          <select
            value={addUserId}
            onChange={(e) => setAddUserId(e.target.value ? Number(e.target.value) : '')}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none"
          >
            <option value="">Выберите сотрудника...</option>
            {availableUsers.map(u => (
              <option key={u.user_id} value={u.user_id}>{u.user_name} ({u.user_email})</option>
            ))}
          </select>
          <select
            value={addRole}
            onChange={(e) => setAddRole(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none"
          >
            <option value="manager">Менеджер</option>
            <option value="developer">Разработчик</option>
            <option value="reviewer">Ревьюер</option>
            <option value="observer">Наблюдатель</option>
          </select>
          <div className="flex gap-2">
            <button
              onClick={handleAdd}
              disabled={!addUserId || adding}
              className="flex-1 py-2 text-xs font-medium text-white bg-emerald-500 hover:bg-emerald-600 disabled:opacity-40 rounded-lg transition-colors"
            >
              {adding ? 'Добавляю...' : 'Добавить'}
            </button>
            <button
              onClick={() => setShowAddForm(false)}
              className="px-4 py-2 text-xs text-white/50 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
            >
              Отмена
            </button>
          </div>
        </motion.div>
      )}

      {members.map((member) => (
        <motion.div
          key={member.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-4 flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500/30 to-purple-500/30 flex items-center justify-center border border-white/10">
              <span className="text-sm font-medium text-white/70">
                {(member.user_name || member.user_email || '?').charAt(0).toUpperCase()}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-white">{member.user_name || member.user_email || `User ${member.user_id}`}</p>
              {member.user_email && member.user_name && (
                <p className="text-xs text-white/30">{member.user_email}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-white/50 bg-white/5 px-2.5 py-1 rounded-lg border border-white/10">
              {ROLE_LABELS[member.role] || member.role}
            </span>
            {member.allocation_percent > 0 && (
              <span className="text-xs text-white/30">{member.allocation_percent}%</span>
            )}
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ============================================================
// MAIN PAGE
// ============================================================

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const {
    currentProject,
    isLoading,
    error,
    fetchProject,
    updateProject,
    deleteProject,
    clearCurrentProject,
  } = useProjectStore();

  const [activeTab, setActiveTab] = useUrlTab<Tab>("tab", "overview");
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [milestones, setMilestones] = useState<ProjectMilestone[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const id = Number(projectId);

  useEffect(() => {
    if (id) {
      fetchProject(id);
      // Load members and milestones
      setMembersLoading(true);
      Promise.all([
        api.getProjectMembers(id).catch(() => []),
        api.getProjectMilestones(id).catch(() => []),
      ]).then(([m, ms]) => {
        setMembers(m);
        setMilestones(ms);
        setMembersLoading(false);
      });
    }
    return () => clearCurrentProject();
  }, [id, fetchProject, clearCurrentProject]);

  const handleUpdate = async (data: api.ProjectUpdate) => {
    try {
      await updateProject(id, data);
      toast.success('Проект обновлён');
    } catch {
      toast.error('Не удалось обновить проект');
      throw new Error('update failed');
    }
  };

  const handleDelete = async () => {
    try {
      await deleteProject(id);
      toast.success('Проект удалён');
      navigate('/projects');
    } catch {
      toast.error('Не удалось удалить проект');
    }
  };

  if (isLoading && !currentProject) {
    return (
      <div className="min-h-screen p-6 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error && !currentProject) {
    return (
      <div className="min-h-screen p-6">
        <div className="p-6 bg-red-500/10 border border-red-500/20 rounded-2xl flex items-center gap-3">
          <AlertTriangle className="w-6 h-6 text-red-400" />
          <div>
            <p className="text-red-300 font-medium">Ошибка</p>
            <p className="text-red-300/60 text-sm">{error}</p>
          </div>
          <button
            onClick={() => navigate('/projects')}
            className="ml-auto px-4 py-2 text-sm text-white/70 hover:text-white bg-white/5 hover:bg-white/10 rounded-xl transition-colors"
          >
            Назад
          </button>
        </div>
      </div>
    );
  }

  if (!currentProject) return null;

  return (
    <div className="min-h-screen p-6">
      {/* Back + Header */}
      <div className="mb-6">
        <button
          onClick={() => navigate('/projects')}
          className="flex items-center gap-1.5 text-sm text-white/40 hover:text-white/70 transition-colors mb-4"
        >
          <ChevronLeft className="w-4 h-4" />
          Проекты
        </button>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className="w-4 h-4 rounded-full flex-shrink-0"
              style={{ backgroundColor: currentProject.color || '#3b82f6' }}
            />
            <h1 className="text-2xl font-bold text-white">{currentProject.name}</h1>
            <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border', STATUS_COLORS[currentProject.status])}>
              {STATUS_ICONS[currentProject.status]}
              {STATUS_LABELS[currentProject.status]}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowEditModal(true)}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-white/60 hover:text-white hover:bg-white/5 rounded-xl transition-colors border border-white/10"
            >
              <Edit className="w-4 h-4" />
              Изменить
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-red-400/60 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-colors border border-white/10"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-white/5 rounded-xl p-1 w-fit border border-white/10">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all',
              activeTab === tab.id
                ? 'bg-white/10 text-white shadow-sm'
                : 'text-white/40 hover:text-white/70'
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
        >
          {activeTab === 'overview' && (
            <OverviewTab project={currentProject} milestones={milestones} onProjectUpdated={() => fetchProject(id)} />
          )}
          {activeTab === 'tasks' && (
            <TasksTab projectId={id} members={members} />
          )}
          {activeTab === 'team' && (
            <TeamTab members={members} isLoading={membersLoading} projectId={id} onMemberAdded={() => api.getProjectMembers(id).then(m => setMembers(m)).catch(() => {})} />
          )}
        </motion.div>
      </AnimatePresence>

      {/* Edit modal */}
      <ProjectForm
        project={currentProject}
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        onSubmit={handleUpdate}
      />

      {/* Delete confirmation */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              {...backdropClose(() => setShowDeleteConfirm(false))}
            />
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="relative w-full max-w-md bg-[#1a1a2e]/98 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl overflow-hidden"
            >
              <div className="flex items-center gap-3 p-6 pb-4">
                <div className="p-2 rounded-xl bg-red-500/20">
                  <Trash2 className="w-5 h-5 text-red-400" />
                </div>
                <h3 className="text-lg font-bold text-white">Удалить проект?</h3>
              </div>
              <div className="px-6 pb-4">
                <p className="text-sm text-white/50">
                  Проект &laquo;{currentProject.name}&raquo; будет удалён вместе со всеми задачами и данными. Это действие необратимо.
                </p>
              </div>
              <div className="flex justify-end gap-3 p-6 pt-4 border-t border-white/5">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-4 py-2 text-sm text-white/50 hover:text-white hover:bg-white/5 rounded-xl transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={handleDelete}
                  className="px-5 py-2.5 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-xl transition-colors shadow-lg shadow-red-500/20"
                >
                  Удалить
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
