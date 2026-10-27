import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, FolderPlus, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import type { Project, ProjectCreate, ProjectUpdate, ProjectStatus } from '@/services/api/projects';
import { getDepartments } from '@/services/api';
import type { Department } from '@/services/api';
import { backdropClose } from '@/utils/backdropClose';

const STATUS_OPTIONS: { value: ProjectStatus; label: string }[] = [
  { value: 'planning', label: 'Планирование' },
  { value: 'active', label: 'В разработке' },
  { value: 'on_hold', label: 'На паузе' },
  { value: 'completed', label: 'Завершён' },
  { value: 'cancelled', label: 'Отменён' },
];

const PRIORITY_OPTIONS = [
  { value: 0, label: 'Низкий' },
  { value: 1, label: 'Нормальный' },
  { value: 2, label: 'Высокий' },
  { value: 3, label: 'Критический' },
];

const COLOR_OPTIONS = [
  '#3b82f6', '#8b5cf6', '#ec4899', '#ef4444',
  '#f59e0b', '#10b981', '#06b6d4', '#6366f1',
];

interface ProjectFormProps {
  project?: Project | null;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: ProjectCreate | ProjectUpdate) => Promise<void>;
}

export default function ProjectForm({ project, isOpen, onClose, onSubmit }: ProjectFormProps) {
  const isEditing = !!project;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [priority, setPriority] = useState(1);
  const [status, setStatus] = useState<ProjectStatus>('planning');
  const [clientName, setClientName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [targetDate, setTargetDate] = useState('');
  const [color, setColor] = useState('#3b82f6');
  const [tagsInput, setTagsInput] = useState('');
  const [departments, setDepartments] = useState<Department[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    getDepartments().then(setDepartments).catch(() => {});
  }, []);

  useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description || '');
      setDepartmentId(project.department_id || '');
      setPriority(project.priority);
      setStatus(project.status);
      setClientName(project.client_name || '');
      setStartDate(project.start_date?.slice(0, 10) || '');
      setTargetDate(project.target_date?.slice(0, 10) || '');
      setColor(project.color || '#3b82f6');
      setTagsInput((project.tags || []).join(', '));
    } else {
      setName('');
      setDescription('');
      setDepartmentId('');
      setPriority(1);
      setStatus('planning');
      setClientName('');
      setStartDate('');
      setTargetDate('');
      setColor('#3b82f6');
      setTagsInput('');
    }
  }, [project, isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.error('Название проекта обязательно');
      return;
    }

    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const data: ProjectCreate = {
      name: name.trim(),
      description: description.trim() || undefined,
      department_id: departmentId ? Number(departmentId) : undefined,
      priority,
      status,
      client_name: clientName.trim() || undefined,
      start_date: startDate || undefined,
      target_date: targetDate || undefined,
      color,
      tags: tags.length > 0 ? tags : undefined,
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
                <div className="p-2 rounded-xl bg-blue-50">
                  <FolderPlus className="w-5 h-5 text-blue-600" />
                </div>
                <h2 className="text-lg font-bold text-gray-900 dark:text-dark-100">
                  {isEditing ? 'Редактировать проект' : 'Новый проект'}
                </h2>
              </div>
              <button onClick={onClose} className="p-2 text-gray-400 dark:text-dark-500 hover:text-gray-600 dark:text-dark-300 hover:bg-gray-100 dark:hover:bg-dark-800 dark:bg-dark-800 rounded-lg transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form */}
            <form id="project-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* Name */}
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Название *</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Название проекта"
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
                  placeholder="Описание проекта..."
                  rows={3}
                  className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-y min-h-[80px]"
                />
              </div>

              {/* Department & Priority row */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Отдел</label>
                  <select
                    value={departmentId}
                    onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : '')}
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                  >
                    <option value="">Не указан</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
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

              {/* Status (only in edit mode) */}
              {isEditing && (
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Статус</label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value as ProjectStatus)}
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                  >
                    {STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Client name */}
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Клиент</label>
                <input
                  type="text"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  placeholder="Название клиента"
                  className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>

              {/* Dates row */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Дата начала</label>
                  <input
                    type="date"
                    value={startDate ? startDate.slice(0, 10) : ''}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Целевая дата</label>
                  <input
                    type="date"
                    value={targetDate ? targetDate.slice(0, 10) : ''}
                    min={startDate ? startDate.slice(0, 10) : new Date().toISOString().slice(0, 10)}
                    onChange={(e) => setTargetDate(e.target.value)}
                    className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                  />
                </div>
              </div>

              {/* Color */}
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Цвет</label>
                <div className="flex gap-2">
                  {COLOR_OPTIONS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setColor(c)}
                      className={`w-8 h-8 rounded-lg transition-all ${color === c ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-white scale-110' : 'hover:scale-105'}`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>

              {/* Tags */}
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-dark-400 uppercase tracking-wider mb-1.5">Теги</label>
                <input
                  type="text"
                  value={tagsInput}
                  onChange={(e) => setTagsInput(e.target.value)}
                  placeholder="frontend, backend, design (через запятую)"
                  className="w-full bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
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
                form="project-form"
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
