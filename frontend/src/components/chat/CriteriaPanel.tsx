import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus,
  Trash2,
  Save,
  ChevronDown,
  AlertCircle,
  CheckCircle,
  Target,
  TrendingUp,
  Globe,
  RotateCcw,
  Bookmark,
  User,
  X,
  Settings
} from 'lucide-react';
import * as Select from '@radix-ui/react-select';
import * as Dialog from '@radix-ui/react-dialog';
import {
  getChatCriteria,
  updateChatCriteria,
  getCriteriaPresets,
  getDefaultCriteria,
  setDefaultCriteria,
  createCriteriaPreset,
  deleteCriteriaPreset,
  seedUniversalPresets
} from '@/services/api';
import type { Criterion, ChatTypeId } from '@/types';
import { useAuthStore } from '@/stores/authStore';
import { getErrorDetail } from '@/utils';
import toast from 'react-hot-toast';
import clsx from 'clsx';

interface CriteriaPanelProps {
  chatId: number;
  chatType?: ChatTypeId;
}

const categoryIcons = {
  basic: Target,
  red_flags: AlertCircle,
  green_flags: CheckCircle,
  potential: TrendingUp,
};

const categoryColors = {
  basic: 'text-blue-400 bg-blue-500/20',
  red_flags: 'text-red-400 bg-red-500/20',
  green_flags: 'text-green-400 bg-green-500/20',
  potential: 'text-purple-400 bg-purple-500/20',
};

const categoryLabels = {
  basic: 'Основные',
  red_flags: 'Негативные',
  green_flags: 'Позитивные',
  potential: 'Потенциал',
};

export default function CriteriaPanel({ chatId, chatType }: CriteriaPanelProps) {
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [hasChanges, setHasChanges] = useState(false);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [managePresetsOpen, setManagePresetsOpen] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const queryClient = useQueryClient();
  const { isSuperAdmin } = useAuthStore();

  const { data: chatCriteria, isLoading } = useQuery({
    queryKey: ['chat-criteria', chatId],
    queryFn: () => getChatCriteria(chatId),
  });

  const { data: presets = [] } = useQuery({
    queryKey: ['criteria-presets'],
    queryFn: getCriteriaPresets,
  });

  useEffect(() => {
    if (chatCriteria?.criteria) {
      setCriteria(chatCriteria.criteria.map((c) => ({
        name: c.name || '',
        description: c.description || '',
        weight: c.weight ?? 5,
        category: (c.category || 'basic') as Criterion['category'],
      })));
    }
  }, [chatCriteria]);

  const saveMutation = useMutation({
    mutationFn: () => updateChatCriteria(chatId, criteria),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-criteria', chatId] });
      setHasChanges(false);
      toast.success('Критерии сохранены');
    },
    onError: (error: unknown) => {
      const axiosErr = error as { response?: { status?: number } };
      const status = axiosErr?.response?.status;
      if (status === 401) {
        toast.error('Сессия истекла. Перезайдите в систему');
      } else if (status === 403) {
        toast.error(getErrorDetail(error, 'Нет прав для сохранения критериев'));
      } else {
        toast.error(getErrorDetail(error, 'Ошибка сохранения'));
      }
    },
  });

  const saveAsDefaultMutation = useMutation({
    mutationFn: () => setDefaultCriteria(chatType!, criteria),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['default-criteria', chatType] });
      toast.success('Сохранено как критерии по умолчанию');
    },
    onError: () => {
      toast.error('Ошибка сохранения');
    },
  });

  const saveAsTemplateMutation = useMutation({
    mutationFn: (name: string) => createCriteriaPreset({
      name,
      description: `Личный шаблон критериев`,
      criteria: criteria,
      category: 'basic',
      is_global: false,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['criteria-presets'] });
      setSaveDialogOpen(false);
      setTemplateName('');
      toast.success('Шаблон сохранён');
    },
    onError: () => {
      toast.error('Ошибка сохранения шаблона');
    },
  });

  const seedUniversalMutation = useMutation({
    mutationFn: seedUniversalPresets,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['criteria-presets'] });
      if (data.created.length > 0) {
        toast.success(`Загружено ${data.created.length} универсальных шаблонов`);
      } else {
        toast.success('Все универсальные шаблоны уже загружены');
      }
    },
    onError: () => {
      toast.error('Ошибка загрузки шаблонов');
    },
  });

  const deletePresetMutation = useMutation({
    mutationFn: deleteCriteriaPreset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['criteria-presets'] });
      toast.success('Шаблон удалён');
    },
    onError: () => {
      toast.error('Ошибка удаления шаблона');
    },
  });

  const handleSaveAsTemplate = () => {
    if (!templateName.trim()) {
      toast.error('Введите название шаблона');
      return;
    }
    saveAsTemplateMutation.mutate(templateName.trim());
  };

  const handleLoadDefaults = async () => {
    if (!chatType) return;
    try {
      const defaults = await getDefaultCriteria(chatType);
      if (defaults.criteria.length > 0) {
        setCriteria(defaults.criteria.map((c: Record<string, unknown>) => ({
          name: (c.name as string) || '',
          description: (c.description as string) || '',
          weight: (c.weight as number) ?? 5,
          category: ((c.category as string) || 'basic') as Criterion['category'],
        })));
        setHasChanges(true);
        toast.success(defaults.is_custom ? 'Загружены пользовательские критерии' : 'Загружены стандартные критерии');
      } else {
        toast.error('Нет критериев по умолчанию для этого типа');
      }
    } catch {
      toast.error('Ошибка загрузки критериев');
    }
  };

  const handleAddCriterion = () => {
    setCriteria([
      ...criteria,
      {
        name: '',
        description: '',
        weight: 5,
        category: 'basic',
      },
    ]);
    setHasChanges(true);
  };

  const handleRemoveCriterion = (index: number) => {
    setCriteria(criteria.filter((_, i) => i !== index));
    setHasChanges(true);
  };

  const handleUpdateCriterion = (index: number, updates: Partial<Criterion>) => {
    setCriteria(
      criteria.map((c, i) => (i === index ? { ...c, ...updates } : c))
    );
    setHasChanges(true);
  };

  const handleApplyPreset = (presetId: string) => {
    const preset = presets.find((p) => p.id === parseInt(presetId));
    if (preset) {
      const normalizedCriteria = preset.criteria.map((c) => ({
        name: c.name || '',
        description: c.description || '',
        weight: c.weight ?? 5,
        category: (c.category || 'basic') as Criterion['category'],
      }));
      setCriteria([...criteria, ...normalizedCriteria]);
      setHasChanges(true);
      toast.success(`Применён шаблон: ${preset.name}`);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Group presets by global vs personal
  const globalPresets = presets.filter(p => p.is_global);
  const personalPresets = presets.filter(p => !p.is_global);

  return (
    <div className="p-4 space-y-4 overflow-hidden">
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h3 className="font-semibold text-sm sm:text-base">Критерии оценки</h3>
            <p className="text-xs sm:text-sm text-dark-400">
              {criteria.length} {criteria.length === 1 ? 'критерий' : criteria.length < 5 ? 'критерия' : 'критериев'}
            </p>
          </div>
          <button
            onClick={handleAddCriterion}
            className="flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg bg-accent-500/20 text-accent-400 hover:bg-accent-500/30 text-xs sm:text-sm transition-colors flex-shrink-0"
          >
            <Plus className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
            <span className="hidden sm:inline">Добавить</span>
            <span className="sm:hidden">+</span>
          </button>
        </div>

        {/* Buttons row */}
        <div className="flex gap-2 flex-wrap">
          {chatType && (
            <button
              onClick={handleLoadDefaults}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg glass-light text-xs hover:bg-white/10 transition-colors"
              title="Загрузить критерии по умолчанию"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>По умолч.</span>
            </button>
          )}

          {(globalPresets.length > 0 || personalPresets.length > 0) && (
            <Select.Root onValueChange={handleApplyPreset}>
              <Select.Trigger className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg glass-light text-xs hover:bg-white/10 transition-colors">
                <Bookmark className="w-3.5 h-3.5" />
                <Select.Value placeholder="Шаблоны" />
                <ChevronDown className="w-3 h-3" />
              </Select.Trigger>
              <Select.Portal>
                <Select.Content className="glass rounded-xl overflow-hidden shadow-xl z-50 max-w-[280px]">
                  <Select.Viewport className="p-1">
                    {globalPresets.length > 0 && (
                      <>
                        <div className="px-3 py-1.5 text-xs text-dark-500 flex items-center gap-1.5">
                          <Globe className="w-3 h-3" />
                          Общие шаблоны
                        </div>
                        {globalPresets.map((preset) => (
                          <Select.Item
                            key={preset.id}
                            value={String(preset.id)}
                            className="px-3 py-2 rounded-lg cursor-pointer hover:bg-white/10 text-xs outline-none truncate"
                          >
                            <Select.ItemText>{preset.name}</Select.ItemText>
                          </Select.Item>
                        ))}
                      </>
                    )}
                    {personalPresets.length > 0 && (
                      <>
                        <div className="px-3 py-1.5 text-xs text-dark-500 flex items-center gap-1.5 mt-1 border-t border-white/10 pt-2">
                          <User className="w-3 h-3" />
                          Мои шаблоны
                        </div>
                        {personalPresets.map((preset) => (
                          <Select.Item
                            key={preset.id}
                            value={String(preset.id)}
                            className="px-3 py-2 rounded-lg cursor-pointer hover:bg-white/10 text-xs outline-none truncate"
                          >
                            <Select.ItemText>{preset.name}</Select.ItemText>
                          </Select.Item>
                        ))}
                      </>
                    )}
                  </Select.Viewport>
                </Select.Content>
              </Select.Portal>
            </Select.Root>
          )}

          {/* Manage presets button */}
          {(globalPresets.length > 0 || personalPresets.length > 0 || isSuperAdmin()) && (
            <button
              onClick={() => setManagePresetsOpen(true)}
              className="p-1.5 rounded-lg glass-light hover:bg-white/10 transition-colors text-dark-400 hover:text-white"
              title="Управление шаблонами"
            >
              <Settings className="w-3.5 h-3.5" />
            </button>
          )}

          {criteria.length > 0 && (
            <button
              onClick={() => setSaveDialogOpen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg glass-light text-xs hover:bg-white/10 transition-colors text-accent-400"
              title="Сохранить как личный шаблон"
            >
              <Bookmark className="w-3.5 h-3.5" />
              <span>Сохр. шаблон</span>
            </button>
          )}

          {isSuperAdmin() && globalPresets.length < 6 && !(globalPresets.length > 0 || personalPresets.length > 0) && (
            <button
              onClick={() => seedUniversalMutation.mutate()}
              disabled={seedUniversalMutation.isPending}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg glass-light text-xs hover:bg-white/10 transition-colors text-green-400"
              title="Загрузить универсальные шаблоны (6 шт)"
            >
              <Globe className="w-3.5 h-3.5" />
              <span>{seedUniversalMutation.isPending ? '...' : '+ Шаблоны'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Criteria List */}
      <div className="space-y-3">
        <AnimatePresence mode="popLayout">
          {criteria.length === 0 ? (
            <div className="text-center py-8 glass-light rounded-xl">
              <Target className="w-12 h-12 mx-auto text-dark-600 mb-3" />
              <p className="text-dark-400">Критерии не настроены</p>
              <p className="text-dark-500 text-sm mt-1">
                Добавьте критерии или выберите шаблон
              </p>
            </div>
          ) : (
            criteria.map((criterion, index) => {
              const Icon = categoryIcons[criterion.category as keyof typeof categoryIcons] || Target;
              const colorClass = categoryColors[criterion.category as keyof typeof categoryColors] || categoryColors.basic;

              return (
                <motion.div
                  key={index}
                  layout
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="glass-light rounded-xl p-3 space-y-2 overflow-hidden"
                >
                  <div className="flex items-start gap-2">
                    <div className={clsx('p-1.5 rounded-lg flex-shrink-0', colorClass)}>
                      <Icon className="w-3.5 h-3.5" />
                    </div>
                    <div className="flex-1 min-w-0 space-y-2 overflow-hidden">
                      <input
                        type="text"
                        value={criterion.name}
                        onChange={(e) =>
                          handleUpdateCriterion(index, { name: e.target.value })
                        }
                        placeholder="Название критерия"
                        className="w-full bg-transparent border-b border-white/10 pb-1 text-xs sm:text-sm font-medium focus:outline-none focus:border-accent-500"
                      />
                      <textarea
                        value={criterion.description}
                        onChange={(e) =>
                          handleUpdateCriterion(index, { description: e.target.value })
                        }
                        placeholder="Описание..."
                        rows={2}
                        className="w-full bg-transparent text-xs text-dark-300 resize-none focus:outline-none"
                      />
                      <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                        <div className="flex items-center gap-1.5">
                          <select
                            value={criterion.category}
                            onChange={(e) =>
                              handleUpdateCriterion(index, {
                                category: e.target.value as Criterion['category'],
                              })
                            }
                            className="bg-dark-800 rounded-lg px-1.5 py-1 text-[10px] sm:text-xs focus:outline-none focus:ring-1 focus:ring-accent-500"
                          >
                            {Object.entries(categoryLabels).map(([value, label]) => (
                              <option key={value} value={value}>
                                {label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="flex items-center gap-1.5 flex-1 min-w-0">
                          <span className="text-[10px] sm:text-xs text-dark-500">Вес:</span>
                          <input
                            type="range"
                            min="1"
                            max="10"
                            value={criterion.weight}
                            onChange={(e) =>
                              handleUpdateCriterion(index, {
                                weight: parseInt(e.target.value),
                              })
                            }
                            className="flex-1 min-w-[60px] max-w-[100px] accent-accent-500"
                          />
                          <span className="text-xs font-medium w-4">{criterion.weight}</span>
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleRemoveCriterion(index)}
                      className="p-1.5 rounded-lg text-dark-400 hover:text-red-400 hover:bg-red-500/10 transition-colors flex-shrink-0"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </motion.div>
              );
            })
          )}
        </AnimatePresence>
      </div>

      {/* Save Buttons */}
      {hasChanges && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="sticky bottom-0 pt-4 space-y-2"
        >
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 transition-colors"
          >
            <Save className="w-4 h-4" />
            {saveMutation.isPending ? 'Сохранение...' : 'Сохранить'}
          </button>
        </motion.div>
      )}

      {/* Save as Default Button - Superadmin only */}
      {isSuperAdmin() && chatType && criteria.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="pt-2 border-t border-white/10"
        >
          <button
            onClick={() => saveAsDefaultMutation.mutate()}
            disabled={saveAsDefaultMutation.isPending}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl glass-light text-xs sm:text-sm hover:bg-white/10 disabled:opacity-50 transition-colors"
            title={`Сохранить как критерии по умолчанию для всех чатов типа "${chatType}"`}
          >
            <Globe className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
            {saveAsDefaultMutation.isPending ? 'Сохранение...' : 'Глобальные для типа'}
          </button>
          <p className="text-[10px] sm:text-xs text-dark-500 text-center mt-1">
            Для всех новых чатов типа «{chatType}»
          </p>
        </motion.div>
      )}

      {/* Save Template Dialog */}
      <Dialog.Root open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 glass rounded-2xl p-6 w-[90%] max-w-md z-50 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <Dialog.Title className="text-lg font-semibold">
                Сохранить шаблон
              </Dialog.Title>
              <Dialog.Close className="p-2 rounded-lg hover:bg-white/10 transition-colors">
                <X className="w-4 h-4" />
              </Dialog.Close>
            </div>

            <Dialog.Description className="text-sm text-dark-400 mb-4">
              Шаблон будет доступен только вам и может применяться к любому чату
            </Dialog.Description>

            <input
              type="text"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="Название шаблона..."
              className="w-full bg-dark-800/50 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 mb-4"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveAsTemplate();
              }}
            />

            <div className="flex gap-3">
              <Dialog.Close className="flex-1 px-4 py-2.5 rounded-xl glass-light text-sm hover:bg-white/10 transition-colors">
                Отмена
              </Dialog.Close>
              <button
                onClick={handleSaveAsTemplate}
                disabled={saveAsTemplateMutation.isPending || !templateName.trim()}
                className="flex-1 px-4 py-2.5 rounded-xl bg-accent-500 text-white text-sm hover:bg-accent-600 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                <Bookmark className="w-4 h-4" />
                {saveAsTemplateMutation.isPending ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Manage Presets Dialog */}
      <Dialog.Root open={managePresetsOpen} onOpenChange={setManagePresetsOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 glass rounded-2xl p-6 w-[90%] max-w-md z-50 shadow-xl max-h-[80vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <Dialog.Title className="text-lg font-semibold">
                Управление шаблонами
              </Dialog.Title>
              <Dialog.Close className="p-2 rounded-lg hover:bg-white/10 transition-colors">
                <X className="w-4 h-4" />
              </Dialog.Close>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4">
              {/* Global presets */}
              {globalPresets.length > 0 && (
                <div>
                  <div className="text-xs text-dark-500 flex items-center gap-1.5 mb-2">
                    <Globe className="w-3 h-3" />
                    Общие шаблоны
                  </div>
                  <div className="space-y-2">
                    {globalPresets.map((preset) => (
                      <div
                        key={preset.id}
                        className="flex items-center justify-between glass-light rounded-lg p-3"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{preset.name}</p>
                          {preset.description && (
                            <p className="text-xs text-dark-400 truncate">{preset.description}</p>
                          )}
                        </div>
                        {isSuperAdmin() && (
                          <button
                            onClick={() => deletePresetMutation.mutate(preset.id)}
                            disabled={deletePresetMutation.isPending}
                            className="p-2 rounded-lg hover:bg-red-500/20 text-red-400 transition-colors ml-2 flex-shrink-0"
                            title="Удалить шаблон"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Personal presets */}
              {personalPresets.length > 0 && (
                <div>
                  <div className="text-xs text-dark-500 flex items-center gap-1.5 mb-2">
                    <User className="w-3 h-3" />
                    Мои шаблоны
                  </div>
                  <div className="space-y-2">
                    {personalPresets.map((preset) => (
                      <div
                        key={preset.id}
                        className="flex items-center justify-between glass-light rounded-lg p-3"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{preset.name}</p>
                          {preset.description && (
                            <p className="text-xs text-dark-400 truncate">{preset.description}</p>
                          )}
                        </div>
                        <button
                          onClick={() => deletePresetMutation.mutate(preset.id)}
                          disabled={deletePresetMutation.isPending}
                          className="p-2 rounded-lg hover:bg-red-500/20 text-red-400 transition-colors ml-2 flex-shrink-0"
                          title="Удалить шаблон"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {globalPresets.length === 0 && personalPresets.length === 0 && (
                <div className="text-center py-8 text-dark-400">
                  <p>Нет сохранённых шаблонов</p>
                </div>
              )}
            </div>

            {isSuperAdmin() && globalPresets.length < 6 && (
              <div className="pt-4 border-t border-white/10 mt-4">
                <button
                  onClick={() => seedUniversalMutation.mutate()}
                  disabled={seedUniversalMutation.isPending}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-green-600 text-white text-sm hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  <Globe className="w-4 h-4" />
                  {seedUniversalMutation.isPending ? 'Загрузка...' : 'Загрузить универсальные шаблоны'}
                </button>
              </div>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
