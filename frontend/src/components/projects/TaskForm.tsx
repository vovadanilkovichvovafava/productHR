import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ListTodo, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import type { ProjectTask, TaskCreate, TaskUpdate, TaskStatus } from '@/services/api/projects';
import type { ProjectMember } from '@/services/api/projects';
import { backdropClose } from '@/utils/backdropClose';

const TASK_STATUS_OPTIONS: { value: TaskStatus; label: string }[] = [
  { value: 'backlog', label: 'Бэклог' },
  { value: 'todo', label: 'К выполнению' },
  { value: 'in_progress', label: 'В работе' },
  { value: 'review', label: 'Ревью' },
  { value: 'done', label: 'Готово' },
  { value: 'cancelled', label: 'Отменена' },
];

const PRIORITY_OPTIONS = [
  { value: 0, label: 'Низкий' },
  { value: 1, label: 'Нормальный' },
  { value: 2, label: 'Высокий' },
  { value: 3, label: 'Критический' },
];

interface TaskFormProps {
  task?: ProjectTask | null;
  members?: ProjectMember[];
  parentTaskId?: number;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: TaskCreate | TaskUpdate) => Promise<void>;
}

export default function TaskForm({ task, members = [], parentTaskId, isOpen, onClose, onSubmit }: TaskFormProps) {
  const isEditing = !!task;

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<string>('todo');
  const [priority, setPriority] = useState(1);
  const [assigneeId, setAssigneeId] = useState<number | ''>('');
  const [estimatedHours, setEstimatedHours] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (task) {
      setTitle(task.title);
      setDescription(task.description || '');
      setStatus(task.status);
      setPriority(task.priority);
      setAssigneeId(task.assignee_id || '');
      setEstimatedHours(task.estimated_hours != null ? String(task.estimated_hours) : '');
      setDueDate(task.due_date?.slice(0, 10) || '');
    } else {
      setTitle('');
      setDescription('');
      setStatus('todo');
      setPriority(1);
      setAssigneeId('');
      setEstimatedHours('');
      setDueDate('');
    }
  }, [task, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      toast.error('Название задачи обязательно');
      return;
    }

    const data: TaskCreate = {
      title: title.trim(),
      description: description.trim() || undefined,
      status,
      priority,
      assignee_id: assigneeId ? Number(assigneeId) : undefined,
      estimated_hours: estimatedHours ? Number(estimatedHours) : undefined,
      due_date: dueDate || undefined,
      parent_task_id: parentTaskId || undefined,
    };

    setIsSubmitting(true);
    try {
      await onSubmit(data);
      onClose();
    } catch {
      // error handled by caller
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50"
            {...backdropClose(onClose)}
          />
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className="relative w-full max-w-lg max-h-[90vh] bg-white dark:bg-dark-900 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-white/[0.08]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-purple-50">
                  <ListTodo className="w-5 h-5 text-purple-600" />
                </div>
                <h2 className="text-lg font-bold text-gray-900 dark:text-dark-100">
                  {isEditing ? 'Редактировать задачу' : 'Новая задача'}
                </h2>
              </div>
              <button onClick={onClose} className="p-2 text-gray-400 dark:text-dark-500 hover:text-gray-600 dark:text-dark-300 hover:bg-gray-100 dark:hover:bg-dark-800 dark:bg-dark-800 rounded-lg transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <form id="task-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* Title */}
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Название *</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Название задачи"
                  className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                  required
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Описание</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Описание задачи..."
                  rows={3}
                  className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-y min-h-[80px]"
                />
              </div>

              {/* Status & Priority row */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Статус</label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value as TaskStatus)}
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                  >
                    {TASK_STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Приоритет</label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(Number(e.target.value))}
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                  >
                    {PRIORITY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Assignee */}
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Исполнитель</label>
                <select
                  value={assigneeId}
                  onChange={(e) => setAssigneeId(e.target.value ? Number(e.target.value) : '')}
                  className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                >
                  <option value="">Не назначен</option>
                  {members.map((m) => (
                    <option key={m.user_id} value={m.user_id}>{m.user_name || m.user_email || `User ${m.user_id}`}</option>
                  ))}
                </select>
              </div>

              {/* Estimated hours & Due date row */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Оценка (часы)</label>
                  <input
                    type="number"
                    min="0"
                    step="0.5"
                    value={estimatedHours}
                    onChange={(e) => setEstimatedHours(e.target.value)}
                    placeholder="0"
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Дедлайн</label>
                  <input
                    type="date"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                  />
                </div>
              </div>
            </form>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-white/[0.08] bg-gray-50 dark:bg-dark-800">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-dark-100 dark:text-dark-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                Отмена
              </button>
              <button
                type="submit"
                form="task-form"
                disabled={isSubmitting}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg transition-colors shadow-sm"
              >
                <Save className="w-4 h-4" />
                {isSubmitting ? 'Сохранение...' : isEditing ? 'Сохранить' : 'Создать'}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
