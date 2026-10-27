import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
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
  Search,
  Plus,
  FolderKanban,
  Users,
  ChevronRight,
  ChevronDown,
  AlertTriangle,
  TrendingUp,
  Flame,
  BarChart3,
  LayoutGrid,
  List,
  ListTodo,
  Calendar,
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { useProjectStore } from '@/stores/projectStore';
import type { ProjectStatus, Project, ProjectCreate, ProjectUpdate, ProjectStatusDef2 } from '@/services/api/projects';
import { updateProject as apiUpdateProject, getProjectStatusDefs } from '@/services/api/projects';
import { ProjectForm } from '@/components/projects';

// ============================================================
// CONSTANTS & FALLBACKS
// ============================================================

const FALLBACK_STATUSES: ProjectStatusDef2[] = [
  { id: 0, org_id: 0, name: 'В разработке', slug: 'active', color: '#10b981', sort_order: 0, is_done: false },
  { id: 0, org_id: 0, name: 'Планирование', slug: 'planning', color: '#3b82f6', sort_order: 1, is_done: false },
  { id: 0, org_id: 0, name: 'На паузе', slug: 'on_hold', color: '#f59e0b', sort_order: 2, is_done: false },
  { id: 0, org_id: 0, name: 'Завершён', slug: 'completed', color: '#22c55e', sort_order: 3, is_done: true },
  { id: 0, org_id: 0, name: 'Отменён', slug: 'cancelled', color: '#ef4444', sort_order: 4, is_done: false },
];

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Низкий',
  1: 'Обычный',
  2: 'Высокий',
  3: 'Срочный',
};

const PRIORITY_DOT_COLORS: Record<number, string> = {
  0: 'bg-white/20',
  1: 'bg-blue-400',
  2: 'bg-amber-400',
  3: 'bg-red-400',
};

/** Convert hex color to a Tailwind-like bg class (returns inline style instead) */
function hexToBgClass(hex: string): string {
  // Map common hex colors to Tailwind classes for backward compat
  const map: Record<string, string> = {
    '#3b82f6': 'bg-blue-400',
    '#10b981': 'bg-emerald-400',
    '#f59e0b': 'bg-amber-400',
    '#22c55e': 'bg-green-400',
    '#ef4444': 'bg-red-400',
  };
  return map[hex?.toLowerCase()] || '';
}

type ViewMode = 'board' | 'list';

// ============================================================
// HEALTH
// ============================================================

type HealthStatus = 'good' | 'warning' | 'critical' | 'completed' | 'neutral';

function getProjectHealth(project: Project, statusMap?: Record<string, ProjectStatusDef2>): { status: HealthStatus; label: string } {
  const def = statusMap?.[project.status];
  // If status is marked as "done" in custom defs, treat as completed
  if (def?.is_done) return { status: 'completed', label: def.name };
  // For non-active statuses (not "active" slug and not marked is_done), treat as neutral
  if (project.status !== 'active' && def) return { status: 'neutral', label: def.name };
  // Fallback for hardcoded slugs when no custom defs loaded
  if (!def) {
    if (project.status === 'completed') return { status: 'completed', label: 'Завершён' };
    if (project.status === 'cancelled') return { status: 'neutral', label: 'Отменён' };
    if (project.status === 'on_hold') return { status: 'neutral', label: 'На паузе' };
    if (project.status === 'planning') return { status: 'neutral', label: 'Планирование' };
  }

  if (!project.start_date || !project.target_date) {
    return { status: 'good', label: 'В норме' };
  }

  const now = new Date();
  const start = new Date(project.start_date);
  const target = new Date(project.target_date);
  const totalDays = Math.max((target.getTime() - start.getTime()) / (1000 * 60 * 60 * 24), 1);
  const elapsedDays = Math.max((now.getTime() - start.getTime()) / (1000 * 60 * 60 * 24), 0);
  const expectedProgress = Math.min((elapsedDays / totalDays) * 100, 100);
  const ratio = project.progress_percent / Math.max(expectedProgress, 1);

  if (now > target && project.progress_percent < 100) return { status: 'critical', label: 'Просрочен' };
  const daysLeft = (target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  if (daysLeft <= 7 && project.progress_percent < 80) return { status: 'critical', label: 'Горит' };
  if (ratio < 0.7) return { status: 'critical', label: 'Отстаёт' };
  if (ratio < 0.9) return { status: 'warning', label: 'Есть риски' };
  return { status: 'good', label: 'По плану' };
}

const HEALTH_STYLES: Record<HealthStatus, { dot: string; text: string }> = {
  good: { dot: 'bg-emerald-400', text: 'text-emerald-400' },
  warning: { dot: 'bg-amber-400', text: 'text-amber-400' },
  critical: { dot: 'bg-red-400', text: 'text-red-400' },
  completed: { dot: 'bg-green-400', text: 'text-green-400' },
  neutral: { dot: 'bg-white/30', text: 'text-white/40' },
};

// ============================================================
// METRIC CARDS
// ============================================================

function MetricCard({
  label, value, icon, color = 'blue', subtext,
}: {
  label: string; value: number; icon: React.ReactNode; color?: 'blue' | 'emerald' | 'red' | 'amber'; subtext?: string;
}) {
  const styles = {
    blue: 'bg-blue-500/10 border-blue-500/20 text-blue-400',
    emerald: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
    red: 'bg-red-500/10 border-red-500/20 text-red-400',
    amber: 'bg-amber-500/10 border-amber-500/20 text-amber-400',
  };
  const iconBg = {
    blue: 'bg-blue-500/20', emerald: 'bg-emerald-500/20', red: 'bg-red-500/20', amber: 'bg-amber-500/20',
  };

  return (
    <div className={clsx('rounded-2xl border p-4', styles[color])}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase tracking-wider text-white/40">{label}</span>
        <div className={clsx('p-1.5 rounded-lg', iconBg[color])}>{icon}</div>
      </div>
      <p className="text-2xl font-bold text-white">{value}</p>
      {subtext && <p className="text-[10px] mt-0.5 text-white/30">{subtext}</p>}
    </div>
  );
}

// ============================================================
// BOARD VIEW — kanban columns by project status
// ============================================================

function BoardProjectCard({ project, onClick, statusMap }: { project: Project; onClick: () => void; statusMap?: Record<string, ProjectStatusDef2> }) {
  const health = getProjectHealth(project, statusMap);
  const hs = HEALTH_STYLES[health.status];
  const totalTasks = Object.values(project.task_counts || {}).reduce((s: number, n: number) => s + n, 0);
  const doneTasks = project.task_counts?.done || 0;
  const priority = project.priority;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -1 }}
      onClick={onClick}
      className={clsx(
        'relative bg-white/[0.04] border border-white/[0.08] rounded-xl p-3.5 cursor-pointer hover:bg-white/[0.07] hover:border-white/15 transition-all group',
        priority === 1 && 'border-l-2 border-l-blue-400',
        priority === 2 && 'border-l-2 border-l-amber-400',
        priority === 3 && 'border-l-2 border-l-red-400 shadow-[0_0_10px_rgba(239,68,68,0.15)]',
      )}
    >
      {/* Priority badge */}
      <div className={clsx('absolute top-3 right-3 flex items-center gap-1 text-[10px] font-medium rounded-md px-1.5 py-0.5', {
        'text-white/20': priority === 0,
        'text-blue-400 bg-blue-500/10': priority === 1,
        'text-amber-400 bg-amber-500/10': priority === 2,
        'text-red-400 bg-red-500/10 animate-pulse': priority === 3,
      })}>
        {priority >= 2 && <Flame className="w-3 h-3" />}
        {PRIORITY_LABELS[priority]}
      </div>

      {/* Title row */}
      <div className="flex items-start gap-2.5 mb-2 pr-16">
        <div
          className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0"
          style={{ backgroundColor: project.color || '#3b82f6' }}
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-white font-medium truncate group-hover:text-blue-400 transition-colors">{project.name}</p>
          {(project.department_name || project.client_name) && (
            <p className="text-[11px] text-white/25 truncate">
              {project.department_name}{project.department_name && project.client_name ? ' · ' : ''}{project.client_name}
            </p>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
          <div
            className={clsx('h-full rounded-full transition-all', {
              'bg-emerald-400': health.status === 'good' || health.status === 'completed',
              'bg-amber-400': health.status === 'warning',
              'bg-red-400': health.status === 'critical',
              'bg-white/20': health.status === 'neutral',
            })}
            style={{ width: `${project.progress_percent}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-1">
          <span className={clsx('text-[10px] font-medium', hs.text)}>{health.label}</span>
          <span className="text-[10px] text-white/30">{project.progress_percent}%</span>
        </div>
      </div>

      {/* Meta row */}
      <div className="flex items-center gap-3 text-[11px] text-white/30">
        {/* Assignees */}
        <div className="flex items-center gap-1">
          <Users className="w-3 h-3" />
          <span>{project.member_count}</span>
        </div>
        {/* Tasks */}
        <div className="flex items-center gap-1">
          <ListTodo className="w-3 h-3" />
          <span>{doneTasks}/{totalTasks}</span>
        </div>
        {/* Due date */}
        {project.target_date && (
          <div className="flex items-center gap-1 ml-auto">
            <Calendar className="w-3 h-3" />
            <span>{new Date(project.target_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// Draggable wrapper for BoardProjectCard
function DraggableProjectCard({ project, onClick, statusMap }: { project: Project; onClick: () => void; statusMap?: Record<string, ProjectStatusDef2> }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: project.id,
    data: { type: 'project', project, status: project.status },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <BoardProjectCard project={project} onClick={onClick} statusMap={statusMap} />
    </div>
  );
}

// Droppable column for project board
function DroppableStatusColumn({ status, isOver, children }: { status: string; isOver: boolean; children: React.ReactNode }) {
  const { setNodeRef } = useDroppable({ id: status });
  return (
    <div
      ref={setNodeRef}
      className={clsx(
        'space-y-2.5 min-h-[120px] rounded-xl transition-colors duration-200 p-1 -m-1',
        isOver && 'bg-white/[0.04] ring-1 ring-white/10',
      )}
    >
      {children}
    </div>
  );
}

function BoardView({ projects, onProjectClick, onAddProject, onProjectMoved, projectStatuses }: {
  projects: Project[];
  onProjectClick: (id: number) => void;
  onAddProject: (status: string) => void;
  onProjectMoved: () => void;
  projectStatuses: ProjectStatusDef2[];
}) {
  // Local state for optimistic updates during drag
  const [localProjects, setLocalProjects] = useState(projects);
  useEffect(() => { setLocalProjects(projects); }, [projects]);

  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [overColumnId, setOverColumnId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
  );

  const statusSlugs = useMemo(() => projectStatuses.map(s => s.slug), [projectStatuses]);
  const statusMap = useMemo(() => {
    const map: Record<string, ProjectStatusDef2> = {};
    projectStatuses.forEach(s => { map[s.slug] = s; });
    return map;
  }, [projectStatuses]);

  // Helper: find which status column a project belongs to
  const findProjectStatus = useCallback((projectId: number): string | undefined => {
    const p = localProjects.find((proj) => proj.id === projectId);
    return p?.status;
  }, [localProjects]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const project = event.active.data.current?.project as Project | undefined;
    if (project) setActiveProject(project);
  }, []);

  const handleDragOver = useCallback((event: { over: { id: string | number } | null }) => {
    if (!event.over) {
      setOverColumnId(null);
      return;
    }
    const overId = String(event.over.id);
    // If hovering over a column directly
    if (statusSlugs.includes(overId)) {
      setOverColumnId(overId);
    } else {
      // Hovering over a project card — find its column
      const status = findProjectStatus(Number(event.over.id));
      setOverColumnId(status || null);
    }
  }, [findProjectStatus, statusSlugs]);

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    setActiveProject(null);
    setOverColumnId(null);

    const { active, over } = event;
    if (!over) return;

    const projectId = Number(active.id);
    const sourceStatus = findProjectStatus(projectId);
    if (!sourceStatus) return;

    // Determine target status
    let targetStatus: string;
    const overId = String(over.id);
    if (statusSlugs.includes(overId)) {
      targetStatus = overId;
    } else {
      const col = findProjectStatus(Number(over.id));
      if (!col) return;
      targetStatus = col;
    }

    // No change
    if (sourceStatus === targetStatus) return;

    // Optimistic update
    setLocalProjects((prev) =>
      prev.map((p) =>
        p.id === projectId ? { ...p, status: targetStatus as ProjectStatus } : p,
      ),
    );

    // Call API
    try {
      await apiUpdateProject(projectId, { status: targetStatus as ProjectStatus });
      onProjectMoved();
    } catch {
      toast.error('Не удалось переместить проект');
      // Revert
      setLocalProjects(projects);
    }
  }, [findProjectStatus, projects, onProjectMoved, statusSlugs]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto pb-4">
        {projectStatuses.map((statusDef) => {
          const statusProjects = localProjects.filter((p) => p.status === statusDef.slug);
          const projectIds = statusProjects.map((p) => p.id);
          const dotClass = hexToBgClass(statusDef.color);

          return (
            <div key={statusDef.slug} className="flex-shrink-0 w-72">
              {/* Column header */}
              <div className="flex items-center justify-between mb-3 px-1">
                <div className="flex items-center gap-2">
                  <div
                    className={clsx('w-2.5 h-2.5 rounded-sm', dotClass)}
                    style={dotClass ? undefined : { backgroundColor: statusDef.color }}
                  />
                  <span className="text-xs font-semibold text-white uppercase tracking-wide">
                    {statusDef.name}
                  </span>
                  <span className="text-xs text-white/25 font-medium">{statusProjects.length}</span>
                </div>
              </div>

              {/* Cards */}
              <SortableContext items={projectIds} strategy={verticalListSortingStrategy}>
                <DroppableStatusColumn status={statusDef.slug} isOver={overColumnId === statusDef.slug}>
                  <AnimatePresence mode="popLayout">
                    {statusProjects.map((project) => (
                      <DraggableProjectCard
                        key={project.id}
                        project={project}
                        onClick={() => onProjectClick(project.id)}
                        statusMap={statusMap}
                      />
                    ))}
                  </AnimatePresence>

                  {statusProjects.length === 0 && !activeProject && (
                    <div className="flex items-center justify-center h-20 text-xs text-white/20 border border-dashed border-white/10 rounded-xl">
                      Перетащите сюда
                    </div>
                  )}
                </DroppableStatusColumn>
              </SortableContext>

              {/* Add project button */}
              <button
                onClick={() => onAddProject(statusDef.slug)}
                className="w-full py-2 mt-1 text-xs text-white/20 hover:text-white/40 hover:bg-white/[0.03] rounded-lg transition-colors flex items-center justify-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                Добавить
              </button>
            </div>
          );
        })}
      </div>

      {/* Drag overlay: floating card following cursor */}
      <DragOverlay>
        {activeProject ? (
          <div className="opacity-90 rotate-2 scale-105 w-72">
            <BoardProjectCard project={activeProject} onClick={() => {}} statusMap={statusMap} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

// ============================================================
// LIST VIEW — table grouped by status (ClickUp style)
// ============================================================

function ListView({ projects, onProjectClick, projectStatuses }: {
  projects: Project[];
  onProjectClick: (id: number) => void;
  projectStatuses: ProjectStatusDef2[];
}) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const statusMap = useMemo(() => {
    const map: Record<string, ProjectStatusDef2> = {};
    projectStatuses.forEach(s => { map[s.slug] = s; });
    return map;
  }, [projectStatuses]);

  const toggle = (status: string) => {
    setCollapsed((prev) => ({ ...prev, [status]: !prev[status] }));
  };

  return (
    <div className="bg-white/[0.02] border border-white/10 rounded-2xl overflow-hidden">
      {projectStatuses.map((statusDef) => {
        const status = statusDef.slug;
        const statusProjects = projects.filter((p) => p.status === status);
        if (statusProjects.length === 0) return null;
        const isCollapsed = collapsed[status] ?? false;
        const dotClass = hexToBgClass(statusDef.color);

        return (
          <div key={status} className="border-b border-white/5 last:border-b-0">
            {/* Group header */}
            <button
              onClick={() => toggle(status)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.03] transition-colors"
            >
              {isCollapsed
                ? <ChevronRight className="w-4 h-4 text-white/30" />
                : <ChevronDown className="w-4 h-4 text-white/30" />
              }
              <div
                className={clsx('w-2.5 h-2.5 rounded-sm', dotClass)}
                style={dotClass ? undefined : { backgroundColor: statusDef.color }}
              />
              <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: statusDef.color }}>
                {statusDef.name}
              </span>
              <span className="text-xs text-white/25">{statusProjects.length}</span>
            </button>

            {/* Column headers */}
            {!isCollapsed && (
              <div className="grid grid-cols-[1fr_100px_120px_90px_80px_90px_30px] gap-2 px-4 py-1.5 text-[10px] uppercase tracking-wider text-white/20 border-b border-white/5">
                <span className="pl-8">Название</span>
                <span>Health</span>
                <span>Прогресс</span>
                <span>Задачи</span>
                <span>Команда</span>
                <span>Дедлайн</span>
                <span />
              </div>
            )}

            {/* Rows */}
            <AnimatePresence>
              {!isCollapsed && statusProjects.map((project) => {
                const health = getProjectHealth(project, statusMap);
                const hs = HEALTH_STYLES[health.status];
                const totalTasks = Object.values(project.task_counts || {}).reduce((s: number, n: number) => s + n, 0);
                const doneTasks = project.task_counts?.done || 0;
                const daysLeft = project.target_date
                  ? Math.ceil((new Date(project.target_date).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
                  : null;

                return (
                  <motion.div
                    key={project.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={() => onProjectClick(project.id)}
                    className="grid grid-cols-[1fr_100px_120px_90px_80px_90px_30px] gap-2 px-4 py-3 items-center hover:bg-white/[0.03] transition-colors cursor-pointer border-b border-white/[0.03] last:border-b-0 group"
                  >
                    {/* Name */}
                    <div className="flex items-center gap-2.5 min-w-0 pl-8">
                      <div className={clsx('w-2 h-2 rounded-full flex-shrink-0', PRIORITY_DOT_COLORS[project.priority])} />
                      <div
                        className="w-1.5 h-6 rounded-full flex-shrink-0"
                        style={{ backgroundColor: project.color || '#3b82f6' }}
                      />
                      <div className="min-w-0">
                        <span className="text-sm text-white truncate block group-hover:text-blue-400 transition-colors">
                          {project.name}
                        </span>
                        {project.client_name && (
                          <span className="text-[10px] text-white/20 truncate block">{project.client_name}</span>
                        )}
                      </div>
                    </div>

                    {/* Health */}
                    <div className="flex items-center gap-1.5">
                      <div className={clsx('w-1.5 h-1.5 rounded-full', hs.dot)} />
                      <span className={clsx('text-[11px] font-medium', hs.text)}>{health.label}</span>
                    </div>

                    {/* Progress */}
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1 bg-white/[0.06] rounded-full overflow-hidden">
                        <div
                          className={clsx('h-full rounded-full', {
                            'bg-emerald-400': health.status === 'good' || health.status === 'completed',
                            'bg-amber-400': health.status === 'warning',
                            'bg-red-400': health.status === 'critical',
                            'bg-white/20': health.status === 'neutral',
                          })}
                          style={{ width: `${project.progress_percent}%` }}
                        />
                      </div>
                      <span className="text-[11px] text-white/40 w-7 text-right">{project.progress_percent}%</span>
                    </div>

                    {/* Tasks */}
                    <div className="text-[11px] text-white/40">
                      <span className="text-white/60">{doneTasks}</span>/{totalTasks}
                    </div>

                    {/* Team */}
                    <div className="flex items-center gap-1 text-[11px] text-white/40">
                      <Users className="w-3 h-3" />
                      {project.member_count}
                    </div>

                    {/* Deadline */}
                    <div>
                      {project.target_date ? (
                        <span className={clsx('text-[11px]', {
                          'text-red-400': daysLeft !== null && daysLeft <= 7,
                          'text-white/40': !daysLeft || daysLeft > 7,
                        })}>
                          {new Date(project.target_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
                        </span>
                      ) : (
                        <span className="text-[11px] text-white/15">—</span>
                      )}
                    </div>

                    {/* Arrow */}
                    <ChevronRight className="w-4 h-4 text-white/10 group-hover:text-white/30 transition-colors" />
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        );
      })}

      {/* Empty */}
      {projects.length === 0 && (
        <div className="py-16 text-center">
          <FolderKanban className="w-10 h-10 text-white/10 mx-auto mb-3" />
          <p className="text-sm text-white/30">Нет проектов</p>
        </div>
      )}
    </div>
  );
}

// ============================================================
// DEPARTMENT BOARD VIEW — kanban columns by department
// ============================================================

function DroppableDeptColumn({ deptId, isOver, children }: { deptId: string; isOver: boolean; children: React.ReactNode }) {
  const { setNodeRef } = useDroppable({ id: `dept-${deptId}` });
  return (
    <div
      ref={setNodeRef}
      className={clsx(
        'space-y-2.5 min-h-[120px] rounded-xl transition-colors duration-200 p-1 -m-1',
        isOver && 'bg-white/[0.04] ring-1 ring-white/10',
      )}
    >
      {children}
    </div>
  );
}

function DeptColumn({
  deptId,
  name,
  color,
  projects,
  isOver,
  onProjectClick,
}: {
  deptId: string;
  name: string;
  color?: string;
  projects: Project[];
  isOver: boolean;
  onProjectClick: (id: number) => void;
}) {
  return (
    <div className="flex-shrink-0 w-72">
      <div className="flex items-center gap-2 mb-3 px-1">
        <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color || '#6b7280' }} />
        <span className="text-xs font-semibold text-white uppercase tracking-wide">{name}</span>
        <span className="text-xs text-white/25">{projects.length}</span>
      </div>
      <SortableContext items={projects.map(p => p.id)} strategy={verticalListSortingStrategy}>
        <DroppableDeptColumn deptId={deptId} isOver={isOver}>
          <div className={clsx('space-y-2.5', projects.length > 5 && 'max-h-[600px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10')}>
            <AnimatePresence mode="popLayout">
              {projects.map(p => (
                <DraggableProjectCard key={p.id} project={p} onClick={() => onProjectClick(p.id)} />
              ))}
            </AnimatePresence>
          </div>
          {projects.length === 0 && (
            <div className="text-xs text-white/15 text-center py-8 border border-dashed border-white/10 rounded-xl">Нет проектов</div>
          )}
        </DroppableDeptColumn>
      </SortableContext>
    </div>
  );
}

function DepartmentBoardView({
  projects,
  departments,
  onProjectClick,
  onProjectMoved,
}: {
  projects: Project[];
  departments: { id: number; name: string; color?: string }[];
  onProjectClick: (id: number) => void;
  onProjectMoved: () => void;
}) {
  const [localProjects, setLocalProjects] = useState(projects);
  useEffect(() => { setLocalProjects(projects); }, [projects]);

  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [overColumnId, setOverColumnId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const groups = useMemo(() => {
    const map: Record<string, Project[]> = { '0': [] };
    departments.forEach(d => { map[String(d.id)] = []; });
    localProjects.forEach(p => {
      const key = String(p.department_id || 0);
      if (!map[key]) map[key] = [];
      map[key].push(p);
    });
    return map;
  }, [localProjects, departments]);

  const findProjectDeptKey = useCallback((projectId: number): string | undefined => {
    const p = localProjects.find(proj => proj.id === projectId);
    return p ? String(p.department_id || 0) : undefined;
  }, [localProjects]);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const project = event.active.data.current?.project as Project | undefined;
    if (project) setActiveProject(project);
  }, []);

  const handleDragOver = useCallback((event: { over: { id: string | number } | null }) => {
    if (!event.over) { setOverColumnId(null); return; }
    const overId = String(event.over.id);
    // Check if hovering over a dept column directly
    if (overId.startsWith('dept-')) {
      setOverColumnId(overId.replace('dept-', ''));
    } else {
      // Hovering over a project card
      const deptKey = findProjectDeptKey(Number(event.over.id));
      setOverColumnId(deptKey || null);
    }
  }, [findProjectDeptKey]);

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    setActiveProject(null);
    setOverColumnId(null);

    const { active, over } = event;
    if (!over) return;

    const projectId = Number(active.id);
    const sourceDeptKey = findProjectDeptKey(projectId);
    if (sourceDeptKey === undefined) return;

    let targetDeptKey: string;
    const overId = String(over.id);
    if (overId.startsWith('dept-')) {
      targetDeptKey = overId.replace('dept-', '');
    } else {
      const dk = findProjectDeptKey(Number(over.id));
      if (!dk) return;
      targetDeptKey = dk;
    }

    if (sourceDeptKey === targetDeptKey) return;

    const newDeptId = targetDeptKey === '0' ? null : Number(targetDeptKey);

    // Optimistic update
    setLocalProjects(prev =>
      prev.map(p => p.id === projectId ? { ...p, department_id: newDeptId ?? undefined } : p),
    );

    try {
      await apiUpdateProject(projectId, { department_id: newDeptId as number | undefined });
      onProjectMoved();
    } catch {
      toast.error('Не удалось переместить проект');
      setLocalProjects(projects);
    }
  }, [findProjectDeptKey, projects, onProjectMoved]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto pb-4">
        {/* No department column */}
        <DeptColumn
          deptId="0"
          name="Без отдела"
          projects={groups['0'] || []}
          isOver={overColumnId === '0'}
          onProjectClick={onProjectClick}
        />
        {/* Department columns */}
        {departments.map(dept => (
          <DeptColumn
            key={dept.id}
            deptId={String(dept.id)}
            name={dept.name}
            color={dept.color}
            projects={groups[String(dept.id)] || []}
            isOver={overColumnId === String(dept.id)}
            onProjectClick={onProjectClick}
          />
        ))}
      </div>

      <DragOverlay>
        {activeProject ? (
          <div className="opacity-90 rotate-2 scale-105 w-72">
            <BoardProjectCard project={activeProject} onClick={() => {}} statusMap={undefined} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

// ============================================================
// MAIN PAGE
// ============================================================

export default function ProjectsPage() {
  const navigate = useNavigate();
  const {
    projects,
    isLoading,
    error,
    filters,
    fetchProjects,
    createProject,
    setFilters,
    clearError,
  } = useProjectStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<ProjectStatus | 'all'>('all');
  const [deptFilter, setDeptFilter] = useState<number | 'all'>('all');
  const [departments, setDepartments] = useState<{ id: number; name: string; color?: string }[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('board');
  const [groupBy, setGroupBy] = useState<'status' | 'department'>('status');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [, setDefaultStatus] = useState<ProjectStatus>('planning');
  const [projectStatuses, setProjectStatuses] = useState<ProjectStatusDef2[]>(FALLBACK_STATUSES);

  // Load project statuses
  useEffect(() => {
    getProjectStatusDefs().then(s => { if (s.length > 0) setProjectStatuses(s); }).catch(() => {});
  }, []);

  // Derived from custom statuses — replaces hardcoded STATUS_ORDER etc.
  const STATUS_ORDER = projectStatuses.map(s => s.slug as ProjectStatus);
  const STATUS_LABELS: Record<string, string> = {};
  const STATUS_DOT_COLORS: Record<string, string> = {};
  projectStatuses.forEach(s => {
    STATUS_LABELS[s.slug] = s.name;
    STATUS_DOT_COLORS[s.slug] = s.color;
  });

  // Load departments
  useEffect(() => {
    import('@/services/api').then(api => {
      api.getDepartments().then((depts: any[]) => setDepartments(depts.map(d => ({ id: d.id, name: d.name, color: d.color })))).catch(() => {});
    });
  }, []);

  useEffect(() => { fetchProjects(); }, [filters, fetchProjects]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      setFilters({ search: searchQuery || undefined });
    }, 300);
    return () => clearTimeout(timeout);
  }, [searchQuery, setFilters]);

  useEffect(() => {
    setFilters({ status: statusFilter === 'all' ? undefined : statusFilter });
  }, [statusFilter, setFilters]);

  const filteredProjects = useMemo(() => {
    let list = projects;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      list = list.filter((p) =>
        p.name.toLowerCase().includes(q) ||
        p.description?.toLowerCase().includes(q) ||
        p.client_name?.toLowerCase().includes(q)
      );
    }
    if (statusFilter !== 'all') {
      list = list.filter((p) => p.status === statusFilter);
    }
    if (deptFilter !== 'all') {
      list = list.filter((p) => p.department_id === deptFilter);
    }
    return list;
  }, [projects, searchQuery, statusFilter, deptFilter]);

  const metrics = useMemo(() => {
    const active = projects.filter((p) => p.status === 'active').length;
    const totalTasks = projects.reduce((sum, p) =>
      sum + Object.values(p.task_counts || {}).reduce((s: number, n: number) => s + n, 0), 0);
    const inProgressTasks = projects.reduce((sum, p) => sum + (p.task_counts?.in_progress || 0), 0);
    // Открытые задачи — всё что не done / cancelled (по запросу из QA-отчёта).
    // Раньше тут был виджет "Горящие" — 5/5 опрошенных сказали "не смотрю",
    // заменил на полезную метрику открытых задач.
    const openTasks = projects.reduce((sum, p) => {
      const counts = p.task_counts || {};
      return sum + Object.entries(counts).reduce(
        (s, [status, n]) => (status === 'done' || status === 'cancelled') ? s : s + (n as number),
        0,
      );
    }, 0);
    return { active, openTasks, totalTasks, inProgressTasks };
  }, [projects]);

  const handleCreate = async (data: ProjectCreate | ProjectUpdate) => {
    try {
      const project = await createProject(data as ProjectCreate);
      toast.success('Проект создан');
      navigate(`/projects/${project.id}`);
    } catch {
      toast.error('Не удалось создать проект');
      throw new Error('create failed');
    }
  };

  const handleAddFromBoard = (status: string) => {
    setDefaultStatus(status as ProjectStatus);
    setShowCreateModal(true);
  };

  return (
    <div className="min-h-screen p-6">
      {/* Header — ClickUp style */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-blue-500/10 border border-blue-500/20">
            <FolderKanban className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Проекты</h1>
            <p className="text-[11px] text-white/30">Отслеживание прогресса и ресурсов</p>
          </div>
        </div>

        <button
          onClick={() => { setDefaultStatus('planning'); setShowCreateModal(true); }}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-500 hover:bg-blue-600 rounded-xl transition-colors shadow-lg shadow-blue-500/20"
        >
          <Plus className="w-4 h-4" />
          Проект
        </button>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <MetricCard
          label="Активные" value={metrics.active}
          icon={<TrendingUp className="w-4 h-4" />} color="blue"
          subtext={`из ${projects.length} всего`}
        />
        <MetricCard
          label="Открытые задачи" value={metrics.openTasks}
          icon={<ListTodo className="w-4 h-4" />}
          color="amber"
          subtext={`из ${metrics.totalTasks} всего`}
        />
        <MetricCard
          label="Задач в работе" value={metrics.inProgressTasks}
          icon={<BarChart3 className="w-4 h-4" />} color="amber"
          subtext={`из ${metrics.totalTasks} всего`}
        />
        <MetricCard
          label="Участников"
          value={projects.reduce((sum, p) => sum + p.member_count, 0)}
          icon={<Users className="w-4 h-4" />} color="emerald"
          subtext="задействовано"
        />
      </div>

      {/* Tabs bar — ClickUp style: Board | List + Search + Filter */}
      <div className="flex items-center justify-between mb-4 border-b border-white/[0.06] pb-3">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setViewMode('board')}
            className={clsx(
              'flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium rounded-lg transition-all',
              viewMode === 'board'
                ? 'bg-white/10 text-white'
                : 'text-white/40 hover:text-white/60 hover:bg-white/[0.03]'
            )}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            Доска
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={clsx(
              'flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium rounded-lg transition-all',
              viewMode === 'list'
                ? 'bg-white/10 text-white'
                : 'text-white/40 hover:text-white/60 hover:bg-white/[0.03]'
            )}
          >
            <List className="w-3.5 h-3.5" />
            Список
          </button>

          {viewMode === 'board' && departments.length > 0 && (
            <>
              <div className="w-px h-5 bg-white/10 mx-1" />
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value as 'status' | 'department')}
                className="px-2.5 py-1.5 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white/60 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500/40"
              >
                <option value="status">По статусу</option>
                <option value="department">По отделам</option>
              </select>
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/25" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск..."
              className="pl-8 pr-3 py-1.5 w-48 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white placeholder-white/25 focus:outline-none focus:ring-1 focus:ring-blue-500/40 text-xs"
            />
          </div>

          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as ProjectStatus | 'all')}
            className="px-3 py-1.5 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white text-xs focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          >
            <option value="all">Все статусы</option>
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>{STATUS_LABELS[s]}</option>
            ))}
          </select>

          {/* Department filter */}
          {departments.length > 0 && (
            <select
              value={deptFilter}
              onChange={(e) => setDeptFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
              className="px-3 py-1.5 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white text-xs focus:outline-none focus:ring-1 focus:ring-blue-500/40"
            >
              <option value="all">Все отделы</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <span className="text-red-300 text-xs">{error}</span>
          <button onClick={clearError} className="ml-auto text-red-400 hover:text-red-300 text-xs">Закрыть</button>
        </div>
      )}

      {/* Loading */}
      {isLoading && projects.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full" />
        </div>
      )}

      {/* Content */}
      {!isLoading && viewMode === 'board' && groupBy === 'status' && (
        <BoardView
          projects={filteredProjects}
          onProjectClick={(id) => navigate(`/projects/${id}`)}
          onAddProject={handleAddFromBoard}
          onProjectMoved={() => fetchProjects()}
          projectStatuses={projectStatuses}
        />
      )}

      {!isLoading && viewMode === 'board' && groupBy === 'department' && (
        <DepartmentBoardView
          projects={filteredProjects}
          departments={departments}
          onProjectClick={(id) => navigate(`/projects/${id}`)}
          onProjectMoved={() => fetchProjects()}
        />
      )}

      {!isLoading && viewMode === 'list' && (
        <ListView
          projects={filteredProjects}
          onProjectClick={(id) => navigate(`/projects/${id}`)}
          projectStatuses={projectStatuses}
        />
      )}

      {/* Empty state for filtered results */}
      {!isLoading && filteredProjects.length === 0 && projects.length > 0 && (
        <div className="flex flex-col items-center py-16 text-center">
          <Search className="w-8 h-8 text-white/10 mb-3" />
          <p className="text-sm text-white/30">Проекты не найдены</p>
          <p className="text-xs text-white/15 mt-1">Попробуйте изменить фильтры</p>
        </div>
      )}

      {/* Create modal */}
      <ProjectForm
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSubmit={handleCreate}
      />
    </div>
  );
}
