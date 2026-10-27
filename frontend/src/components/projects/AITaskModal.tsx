import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Sparkles,
  Plus,
  RefreshCw,
  SkipForward,
  Check,
  AlertCircle,
  Clock,
  User,
  Loader2,
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { aiParsePlan, aiCreateTasks } from '@/services/api/projects';
import type { ParsedTaskItem } from '@/services/api/projects';
import { backdropClose } from '@/utils/backdropClose';

interface AITaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: number;
  onTasksCreated?: () => void;
}

const PRIORITY_LABELS: Record<number, { label: string; color: string }> = {
  0: { label: 'Низкий', color: 'bg-gray-100 dark:bg-dark-800 text-gray-500 dark:text-dark-400' },
  1: { label: 'Обычный', color: 'bg-blue-50 text-blue-600' },
  2: { label: 'Высокий', color: 'bg-amber-50 text-amber-600' },
  3: { label: 'Критический', color: 'bg-red-50 text-red-600' },
};

const ACTION_CONFIG = {
  create: { icon: Plus, label: 'Создать', color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
  update: { icon: RefreshCw, label: 'Обновить', color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200' },
  skip: { icon: SkipForward, label: 'Пропустить', color: 'text-gray-400 dark:text-dark-500', bg: 'bg-gray-50 dark:bg-dark-800 border-gray-200 dark:border-white/[0.08]' },
} as const;

export default function AITaskModal({ isOpen, onClose, projectId, onTasksCreated }: AITaskModalProps) {
  const [text, setText] = useState('');
  const [items, setItems] = useState<ParsedTaskItem[]>([]);
  const [checkedItems, setCheckedItems] = useState<Set<number>>(new Set());
  const [isParsing, setIsParsing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [step, setStep] = useState<'input' | 'preview'>('input');

  const handleParse = useCallback(async () => {
    if (!text.trim()) {
      toast.error('Введите текст плана');
      return;
    }
    setIsParsing(true);
    try {
      const response = await aiParsePlan(projectId, text.trim());
      setItems(response.items);
      // Check all non-skip items by default
      const checked = new Set<number>();
      response.items.forEach((item, idx) => {
        if (item.action !== 'skip') checked.add(idx);
      });
      setCheckedItems(checked);
      setStep('preview');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Ошибка разбора плана';
      toast.error(message);
    } finally {
      setIsParsing(false);
    }
  }, [text, projectId]);

  const handleCreate = useCallback(async () => {
    const selectedItems = items.filter((_, idx) => checkedItems.has(idx));
    if (selectedItems.length === 0) {
      toast.error('Выберите хотя бы одну задачу');
      return;
    }
    setIsCreating(true);
    try {
      const result = await aiCreateTasks(projectId, selectedItems);
      const parts: string[] = [];
      if (result.created > 0) parts.push(`создано: ${result.created}`);
      if (result.updated > 0) parts.push(`обновлено: ${result.updated}`);
      if (result.skipped > 0) parts.push(`пропущено: ${result.skipped}`);
      toast.success(`Готово! ${parts.join(', ')}`);
      onTasksCreated?.();
      handleClose();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Ошибка создания задач';
      toast.error(message);
    } finally {
      setIsCreating(false);
    }
  }, [items, checkedItems, projectId, onTasksCreated]);

  const handleClose = useCallback(() => {
    setText('');
    setItems([]);
    setCheckedItems(new Set());
    setStep('input');
    setIsParsing(false);
    setIsCreating(false);
    onClose();
  }, [onClose]);

  const toggleCheck = (idx: number) => {
    setCheckedItems((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const cycleAction = (idx: number) => {
    const actions: Array<'create' | 'update' | 'skip'> = ['create', 'update', 'skip'];
    setItems((prev) =>
      prev.map((item, i) => {
        if (i !== idx) return item;
        const currentIdx = actions.indexOf(item.action as 'create' | 'update' | 'skip');
        const nextAction = actions[(currentIdx + 1) % actions.length];
        return { ...item, action: nextAction };
      })
    );
  };

  const checkedCount = items.filter((_, idx) => checkedItems.has(idx)).length;

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50"
            {...backdropClose(handleClose)}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="relative w-full max-w-2xl max-h-[85vh] overflow-hidden rounded-2xl bg-white dark:bg-dark-900 shadow-2xl flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-white/[0.08]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-purple-50 border border-purple-100">
                  <Sparkles className="w-5 h-5 text-purple-600" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-900 dark:text-dark-100">AI-создание задач</h2>
                  <p className="text-xs text-gray-400 dark:text-dark-500">
                    {step === 'input'
                      ? 'Вставьте текст плана — AI разберёт на задачи'
                      : `Найдено ${items.length} задач — проверьте и подтвердите`}
                  </p>
                </div>
              </div>
              <button onClick={handleClose} className="p-2 text-gray-400 dark:text-dark-500 hover:text-gray-600 dark:text-dark-300 hover:bg-gray-100 dark:hover:bg-dark-800 dark:bg-dark-800 rounded-lg transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-6">
              <AnimatePresence mode="wait">
                {step === 'input' ? (
                  <motion.div
                    key="input"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                  >
                    <textarea
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      placeholder={`Вставьте ваш план на день, например:\n\n1. Провести код-ревью PR #42 (Иван, 2ч)\n2. Доделать фичу авторизации — критично!\n3. Созвон с дизайнерами по новому UI\n4. Написать тесты для API эндпоинтов`}
                      className="w-full h-64 bg-white dark:bg-dark-900 border border-gray-300 dark:border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-dark-100 placeholder-gray-400 dark:placeholder-dark-500 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500 transition-all"
                      autoFocus
                    />
                    <p className="mt-2 text-xs text-gray-400 dark:text-dark-500">
                      AI определит приоритеты, исполнителей и найдёт дубликаты среди существующих задач.
                    </p>
                  </motion.div>
                ) : (
                  <motion.div
                    key="preview"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    className="space-y-2"
                  >
                    {items.map((item, idx) => {
                      const actionCfg = ACTION_CONFIG[item.action as keyof typeof ACTION_CONFIG] || ACTION_CONFIG.create;
                      const ActionIcon = actionCfg.icon;
                      const priorityCfg = PRIORITY_LABELS[item.priority] || PRIORITY_LABELS[1];
                      const isChecked = checkedItems.has(idx);

                      return (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: idx * 0.05 }}
                          className={clsx(
                            'rounded-xl border p-3 transition-all',
                            isChecked
                              ? 'bg-gray-50 dark:bg-dark-800 border-gray-200 dark:border-white/[0.08]'
                              : 'bg-white dark:bg-dark-900 border-gray-100 dark:border-white/[0.06] opacity-50'
                          )}
                        >
                          <div className="flex items-start gap-3">
                            {/* Checkbox */}
                            <button
                              onClick={() => toggleCheck(idx)}
                              className={clsx(
                                'mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-colors',
                                isChecked
                                  ? 'bg-purple-600 border-purple-600'
                                  : 'border-gray-300 dark:border-white/10 hover:border-gray-400'
                              )}
                            >
                              {isChecked && <Check className="w-3 h-3 text-white" />}
                            </button>

                            {/* Content */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                {/* Action badge */}
                                <button
                                  onClick={() => cycleAction(idx)}
                                  className={clsx(
                                    'flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium border cursor-pointer hover:opacity-80 transition-opacity',
                                    actionCfg.bg
                                  )}
                                  title="Нажмите для смены действия"
                                >
                                  <ActionIcon className={clsx('w-3 h-3', actionCfg.color)} />
                                  {actionCfg.label}
                                </button>

                                {/* Priority */}
                                <span className={clsx('px-1.5 py-0.5 rounded text-[10px] font-medium', priorityCfg.color)}>
                                  {priorityCfg.label}
                                </span>

                                {/* Hours */}
                                {item.estimated_hours && (
                                  <span className="flex items-center gap-0.5 text-[10px] text-gray-400 dark:text-dark-500">
                                    <Clock className="w-3 h-3" />
                                    {item.estimated_hours}ч
                                  </span>
                                )}

                                {/* Assignee */}
                                {item.assignee_hint && (
                                  <span className="flex items-center gap-0.5 text-[10px] text-gray-400 dark:text-dark-500">
                                    <User className="w-3 h-3" />
                                    {item.assignee_hint}
                                  </span>
                                )}
                              </div>

                              {/* Title */}
                              <p className="mt-1 text-sm text-gray-900 dark:text-dark-100 font-medium">{item.title}</p>

                              {/* Description */}
                              {item.description && (
                                <p className="mt-0.5 text-xs text-gray-400 dark:text-dark-500 line-clamp-2">{item.description}</p>
                              )}

                              {/* Existing task reference */}
                              {item.existing_task_title && (
                                <p className="mt-1 text-[10px] text-gray-400 dark:text-dark-500 flex items-center gap-1">
                                  <AlertCircle className="w-3 h-3" />
                                  Связана с: &quot;{item.existing_task_title}&quot;
                                </p>
                              )}

                              {/* Reason */}
                              {item.reason && (
                                <p className="mt-0.5 text-[10px] text-gray-300 italic">{item.reason}</p>
                              )}
                            </div>
                          </div>
                        </motion.div>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-gray-200 dark:border-white/[0.08] bg-gray-50 dark:bg-dark-800 flex items-center justify-between">
              {step === 'preview' && (
                <button
                  onClick={() => setStep('input')}
                  className="px-4 py-2 text-sm text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-dark-100 dark:text-dark-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  Назад к тексту
                </button>
              )}
              {step === 'input' && <div />}

              <div className="flex items-center gap-3">
                <button
                  onClick={handleClose}
                  className="px-4 py-2 text-sm text-gray-600 dark:text-dark-300 hover:text-gray-900 dark:hover:text-dark-100 dark:text-dark-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  Отмена
                </button>

                {step === 'input' ? (
                  <button
                    onClick={handleParse}
                    disabled={isParsing || !text.trim()}
                    className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
                  >
                    {isParsing ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        AI разбирает...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        Разобрать
                      </>
                    )}
                  </button>
                ) : (
                  <button
                    onClick={handleCreate}
                    disabled={isCreating || checkedCount === 0}
                    className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
                  >
                    {isCreating ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Создаю...
                      </>
                    ) : (
                      <>
                        <Check className="w-4 h-4" />
                        Создать ({checkedCount})
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
