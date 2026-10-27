import { useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import * as api from '@/services/api';
import type { ProjectMember, ProjectTaskStatusDef, Project } from '@/services/api';
import { TaskDetailModal } from '@/components/projects';

/**
 * Полноценная страница задачи: /projects/:projectId/tasks/:taskId.
 *
 * Существует чтобы task-deep-link из уведомлений был «честным URL»,
 * а не флагом для модалки на странице проекта (раньше при заходе по
 * прямой ссылке модалка иногда не открывалась из-за гонки с загрузкой
 * канбана).
 *
 * Закрытие → возврат на проект.
 */
export default function ProjectTaskPage() {
  const { projectId: projectIdRaw, taskId: taskIdRaw } = useParams<{
    projectId: string;
    taskId: string;
  }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const projectId = projectIdRaw ? parseInt(projectIdRaw) : NaN;
  const taskId = taskIdRaw ? parseInt(taskIdRaw) : NaN;
  const commentId = searchParams.get('comment')
    ? parseInt(searchParams.get('comment') as string)
    : null;

  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [statuses, setStatuses] = useState<ProjectTaskStatusDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isNaN(projectId) || isNaN(taskId)) {
      setError('Некорректная ссылка');
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [proj, mems, stats] = await Promise.all([
          api.getProject(projectId).catch(() => null),
          api.getProjectMembers(projectId).catch(() => []),
          api.getProjectStatuses(projectId).catch(() => []),
        ]);
        if (cancelled) return;
        if (!proj) {
          setError('Проект не найден или нет доступа');
          setLoading(false);
          return;
        }
        setProject(proj);
        setMembers(mems);
        setStatuses(stats);
        setLoading(false);
      } catch {
        if (!cancelled) {
          setError('Не удалось загрузить задачу');
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [projectId, taskId]);

  const goBack = () => navigate(`/projects/${projectId}`);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-accent-400" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-white/60 text-sm">{error || 'Задача недоступна'}</p>
        <button
          onClick={() => navigate('/projects')}
          className="px-4 py-2 text-sm text-accent-400 hover:text-accent-300 transition-colors"
        >
          ← К списку проектов
        </button>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Хлебные крошки сверху — пользователь видит контекст */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06] bg-dark-900/50">
        <button
          onClick={goBack}
          className="flex items-center gap-1.5 text-sm text-white/60 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          {project.name}
        </button>
        <span className="text-white/30">/</span>
        <span className="text-sm text-white/80">Задача #{taskId}</span>
      </div>

      <div className="flex-1 relative overflow-hidden">
        <TaskDetailModal
          isOpen={true}
          onClose={goBack}
          projectId={projectId}
          taskId={taskId}
          members={members}
          statuses={statuses}
          scrollToCommentId={commentId}
          onTaskUpdated={() => {
            /* можно дёрнуть refresh, но и так всё актуально внутри модалки */
          }}
          onTaskDeleted={goBack}
        />
      </div>
    </div>
  );
}
