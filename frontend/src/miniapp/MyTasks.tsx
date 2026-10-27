import { useEffect, useState } from "react";
import { Loader2, ListTodo } from "lucide-react";
import { getAllTasks } from "@/services/api/projects";

/** Мои задачи по всем проектам — «рабочий минимум» в телефоне. */
export default function MyTasks({ userId }: { userId: number }) {
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAllTasks({ assignee_id: userId } as any)
      .then((d) => setGroups(Array.isArray(d) ? d : []))
      .catch(() => setGroups([]))
      .finally(() => setLoading(false));
  }, [userId]);

  if (loading) return <div className="hf-ma-loading"><Loader2 className="animate-spin" size={24} /></div>;

  const total = groups.reduce((n, g) => n + (g.tasks?.length || 0), 0);
  if (!total) {
    return (
      <div className="hf-ma-empty">
        <ListTodo size={28} />
        <p>Задач на вас нет</p>
      </div>
    );
  }

  return (
    <div className="hf-ma-page">
      <h1 className="hf-ma-title">Мои задачи <span>{total}</span></h1>
      {groups.filter((g) => g.tasks?.length).map((g) => (
        <div key={g.project_id ?? g.project_name} className="hf-ma-group">
          <div className="hf-ma-group-head">{g.project_name || "Без проекта"}</div>
          {g.tasks.map((t: any) => (
            <div key={t.id} className="hf-ma-task">
              <span className="hf-ma-task-title">{t.title}</span>
              <span className="hf-ma-task-meta">
                {t.task_key ? `${t.task_key} · ` : ""}{t.status}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
