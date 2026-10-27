import { useState, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import * as Dialog from '@radix-ui/react-dialog';
import {
  Settings,
  Plus,
  Trash2,
  Target,
  AlertCircle,
  CheckCircle,
  X,
  Save,
  Globe,
  User as UserIcon,
  Mail,
  AtSign,
  Edit3,
  Shield,
  Building2,
  ToggleLeft,
  ToggleRight,
  Briefcase,
  Brain,
  Users
} from 'lucide-react';
import {
  getCriteriaPresets,
  createCriteriaPreset,
  updateCriteriaPreset,
  deleteCriteriaPreset,
  updateUserProfile,
  getFeatureSettings,
  setFeatureAccess,
  deleteFeatureSetting,
  getDepartments,
  type FeatureSetting,
  type Department
} from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { useUrlTab } from '@/hooks/useUrlTab';
import type { Criterion, CriteriaPreset } from '@/types';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import RoleManagement from '@/components/admin/RoleManagement';
import { lazy, Suspense } from 'react';

// Lazy load EmailTemplates component to keep settings page light
const EmailTemplatesSection = lazy(() => import('./EmailTemplatesPage'));

const categoryConfig = {
  basic: { icon: Target, color: 'text-blue-400 bg-blue-500/20', label: 'Basic' },
  red_flags: { icon: AlertCircle, color: 'text-red-400 bg-red-500/20', label: 'Red Flags' },
  green_flags: { icon: CheckCircle, color: 'text-green-400 bg-green-500/20', label: 'Green Flags' },
};

type SettingsTab = 'general' | 'presets' | 'roles' | 'features' | 'email-templates';

// Feature display configuration
// Note: Feature names must match backend RESTRICTED_FEATURES in services/features.py
const featureConfig: Record<string, { icon: typeof Briefcase; label: string; description: string }> = {
  ai_analysis: {
    icon: Brain,
    label: 'AI Анализ',
    description: 'AI-анализ для контактов и звонков'
  },
  candidate_database: {
    icon: Users,
    label: 'Вакансии и База кандидатов',
    description: 'Доступ к вакансиям, Kanban доске и базе кандидатов'
  }
};

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useUrlTab<SettingsTab>('tab', 'general');
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [animationsEnabled, setAnimationsEnabled] = useState(() =>
    localStorage.getItem('animations-enabled') === 'true'
  );
  const { user, setUser, isSuperAdmin, fetchPermissions } = useAuthStore();
  const queryClient = useQueryClient();

  // Profile editing state
  const [profileData, setProfileData] = useState({
    name: '',
    telegram_username: '',
    additional_emails: [] as string[],
    additional_telegram_usernames: [] as string[],
  });
  const [newEmail, setNewEmail] = useState('');
  const [newTelegramUsername, setNewTelegramUsername] = useState('');

  // Initialize profile data from user
  useEffect(() => {
    if (user) {
      setProfileData({
        name: user.name || '',
        telegram_username: user.telegram_username || '',
        additional_emails: user.additional_emails || [],
        additional_telegram_usernames: user.additional_telegram_usernames || [],
      });
    }
  }, [user]);

  const [newPreset, setNewPreset] = useState({
    name: '',
    description: '',
    category: 'general',
    is_global: false,
    criteria: [] as Criterion[],
  });

  // Editing preset state
  const [editingPresetId, setEditingPresetId] = useState<number | null>(null);

  const resetPresetForm = () => {
    setEditingPresetId(null);
    setNewPreset({
      name: '',
      description: '',
      category: 'general',
      is_global: false,
      criteria: [],
    });
  };

  const startEditPreset = (preset: CriteriaPreset) => {
    setEditingPresetId(preset.id);
    setNewPreset({
      name: preset.name,
      description: preset.description || '',
      category: preset.category || 'general',
      is_global: preset.is_global,
      criteria: preset.criteria.map(c => ({
        name: c.name || '',
        description: c.description || '',
        weight: c.weight ?? 5,
        category: (c.category || 'basic') as Criterion['category'],
      })),
    });
    setIsDialogOpen(true);
  };

  const { data: presets = [], isLoading } = useQuery({
    queryKey: ['criteria-presets'],
    queryFn: getCriteriaPresets,
    staleTime: 60000,
  });

  const createMutation = useMutation({
    mutationFn: () => createCriteriaPreset(newPreset),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['criteria-presets'] });
      setIsDialogOpen(false);
      resetPresetForm();
      toast.success('Preset created');
    },
    onError: () => {
      toast.error('Failed to create preset');
    },
  });

  const updateMutation = useMutation({
    mutationFn: () => updateCriteriaPreset(editingPresetId!, newPreset),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['criteria-presets'] });
      setIsDialogOpen(false);
      resetPresetForm();
      toast.success('Preset updated');
    },
    onError: () => {
      toast.error('Failed to update preset');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCriteriaPreset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['criteria-presets'] });
      toast.success('Preset deleted');
    },
  });

  // Profile update mutation
  const profileMutation = useMutation({
    mutationFn: updateUserProfile,
    onSuccess: (updatedUser) => {
      setUser(updatedUser);
      setIsEditingProfile(false);
      toast.success('Профиль обновлён');
    },
    onError: () => {
      toast.error('Ошибка обновления профиля');
    },
  });

  // Feature access queries
  const { data: featureSettingsData, isLoading: isLoadingFeatures } = useQuery({
    queryKey: ['feature-settings'],
    queryFn: getFeatureSettings,
    staleTime: 30000,
    enabled: isSuperAdmin() || user?.org_role === 'owner',
  });

  const { data: departments = [] } = useQuery({
    queryKey: ['departments', -1],
    queryFn: () => getDepartments(-1),
    staleTime: 60000,
    enabled: isSuperAdmin() || user?.org_role === 'owner',
  });

  // Feature mutations
  const featureMutation = useMutation({
    mutationFn: ({ featureName, request }: { featureName: string; request: { department_ids?: number[] | null; enabled: boolean } }) =>
      setFeatureAccess(featureName, request),
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['feature-settings'] });
      // Sync user's features after changing feature settings
      await fetchPermissions();
      toast.success('Feature settings updated');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update feature settings');
    },
  });

  const deleteFeatureMutation = useMutation({
    mutationFn: ({ featureName, departmentId }: { featureName: string; departmentId?: number | null }) =>
      deleteFeatureSetting(featureName, departmentId),
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['feature-settings'] });
      // Sync user's features after removing feature setting
      await fetchPermissions();
      toast.success('Feature setting removed');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to remove feature setting');
    },
  });

  // Selected departments for multi-select
  const [selectedDepartments, setSelectedDepartments] = useState<Record<string, number[]>>({});

  // Group feature settings by feature name
  const groupedFeatures = useMemo(() => {
    if (!featureSettingsData) return {};
    const grouped: Record<string, { orgWide: FeatureSetting | null; departmentSettings: FeatureSetting[] }> = {};

    // Initialize for all restricted features
    featureSettingsData.restricted_features.forEach(featureName => {
      grouped[featureName] = { orgWide: null, departmentSettings: [] };
    });

    // Group existing settings
    featureSettingsData.features.forEach(setting => {
      if (!grouped[setting.feature_name]) {
        grouped[setting.feature_name] = { orgWide: null, departmentSettings: [] };
      }
      if (setting.department_id === null) {
        grouped[setting.feature_name].orgWide = setting;
      } else {
        grouped[setting.feature_name].departmentSettings.push(setting);
      }
    });

    return grouped;
  }, [featureSettingsData]);

  // Handle org-wide toggle
  const handleOrgWideToggle = (featureName: string, enabled: boolean) => {
    const orgWideSetting = groupedFeatures[featureName]?.orgWide;

    if (enabled) {
      // Turn ON: create/update org-wide setting with enabled=true
      featureMutation.mutate({
        featureName,
        request: { department_ids: null, enabled: true }
      });
    } else {
      // Turn OFF: delete org-wide setting if it exists
      if (orgWideSetting) {
        deleteFeatureMutation.mutate({ featureName, departmentId: null });
      }
      // If no setting exists, feature is already disabled by default - do nothing
    }
  };

  // Handle adding department-specific setting
  const handleAddDepartmentSetting = (featureName: string) => {
    const deptIds = selectedDepartments[featureName] || [];
    if (deptIds.length === 0) {
      toast.error('Please select at least one department');
      return;
    }
    featureMutation.mutate({
      featureName,
      request: { department_ids: deptIds, enabled: true }
    });
    setSelectedDepartments(prev => ({ ...prev, [featureName]: [] }));
  };

  // Handle removing department-specific setting
  const handleRemoveDepartmentSetting = (featureName: string, departmentId: number) => {
    deleteFeatureMutation.mutate({ featureName, departmentId });
  };

  const handleSaveProfile = () => {
    profileMutation.mutate({
      name: profileData.name.trim() || undefined,
      telegram_username: profileData.telegram_username.trim() || undefined,
      additional_emails: profileData.additional_emails,
      additional_telegram_usernames: profileData.additional_telegram_usernames,
    });
  };

  const handleAddEmail = () => {
    const email = newEmail.trim().toLowerCase();
    if (email && !profileData.additional_emails.includes(email)) {
      setProfileData({
        ...profileData,
        additional_emails: [...profileData.additional_emails, email],
      });
      setNewEmail('');
    }
  };

  const handleRemoveEmail = (email: string) => {
    setProfileData({
      ...profileData,
      additional_emails: profileData.additional_emails.filter(e => e !== email),
    });
  };

  const handleAddTelegramUsername = () => {
    const username = newTelegramUsername.trim().replace('@', '').toLowerCase();
    if (username && !profileData.additional_telegram_usernames.includes(username)) {
      setProfileData({
        ...profileData,
        additional_telegram_usernames: [...profileData.additional_telegram_usernames, username],
      });
      setNewTelegramUsername('');
    }
  };

  const handleRemoveTelegramUsername = (username: string) => {
    setProfileData({
      ...profileData,
      additional_telegram_usernames: profileData.additional_telegram_usernames.filter(u => u !== username),
    });
  };

  const handleCancelEdit = () => {
    setIsEditingProfile(false);
    // Reset to user values
    if (user) {
      setProfileData({
        name: user.name || '',
        telegram_username: user.telegram_username || '',
        additional_emails: user.additional_emails || [],
        additional_telegram_usernames: user.additional_telegram_usernames || [],
      });
    }
    setNewEmail('');
    setNewTelegramUsername('');
  };

  const handleAddCriterion = () => {
    setNewPreset({
      ...newPreset,
      criteria: [
        ...newPreset.criteria,
        { name: '', description: '', weight: 5, category: 'basic' },
      ],
    });
  };

  const handleUpdateCriterion = (index: number, updates: Partial<Criterion>) => {
    setNewPreset({
      ...newPreset,
      criteria: newPreset.criteria.map((c, i) =>
        i === index ? { ...c, ...updates } : c
      ),
    });
  };

  const handleRemoveCriterion = (index: number) => {
    setNewPreset({
      ...newPreset,
      criteria: newPreset.criteria.filter((_, i) => i !== index),
    });
  };

  const groupedPresets = presets.reduce((acc, preset) => {
    const key = preset.is_global ? 'Global' : 'Personal';
    if (!acc[key]) acc[key] = [];
    acc[key].push(preset);
    return acc;
  }, {} as Record<string, CriteriaPreset[]>);

  return (
    <div className="h-full w-full max-w-full overflow-y-auto overflow-x-hidden p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-4xl mx-auto space-y-6 w-full"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold mb-2">Настройки</h1>
            <p className="text-dark-400">Управление настройками и шаблонами</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setActiveTab('general')}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors',
              activeTab === 'general'
                ? 'bg-accent-500/20 text-accent-400'
                : 'glass-light text-white/60 hover:bg-white/10'
            )}
          >
            <UserIcon className="w-4 h-4" />
            Профиль
          </button>
          <button
            onClick={() => setActiveTab('presets')}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors',
              activeTab === 'presets'
                ? 'bg-accent-500/20 text-accent-400'
                : 'glass-light text-white/60 hover:bg-white/10'
            )}
          >
            <Target className="w-4 h-4" />
            Шаблоны критериев
          </button>
          {isSuperAdmin() && (
            <button
              onClick={() => setActiveTab('roles')}
              className={clsx(
                'flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors',
                activeTab === 'roles'
                  ? 'bg-accent-500/20 text-accent-400'
                  : 'glass-light text-white/60 hover:bg-white/10'
              )}
            >
              <Shield className="w-4 h-4" />
              Роли и права
            </button>
          )}
          {(isSuperAdmin() || user?.org_role === 'owner') && (
            <button
              onClick={() => setActiveTab('features')}
              className={clsx(
                'flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors',
                activeTab === 'features'
                  ? 'bg-accent-500/20 text-accent-400'
                  : 'glass-light text-white/60 hover:bg-white/10'
              )}
            >
              <ToggleRight className="w-4 h-4" />
              Управление доступом
            </button>
          )}
          {(isSuperAdmin() || user?.org_role === 'owner') && (
            <button
              onClick={() => setActiveTab('email-templates')}
              className={clsx(
                'flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors',
                activeTab === 'email-templates'
                  ? 'bg-accent-500/20 text-accent-400'
                  : 'glass-light text-white/60 hover:bg-white/10'
              )}
            >
              <Mail className="w-4 h-4" />
              Email шаблоны
            </button>
          )}
        </div>

        {/* Roles Tab - Fine-grained access control */}
        {activeTab === 'roles' && isSuperAdmin() && (
          <div className="glass rounded-2xl p-6">
            <RoleManagement />
          </div>
        )}

        {/* Feature Access Tab */}
        {activeTab === 'features' && (isSuperAdmin() || user?.org_role === 'owner') && (
          <div className="glass rounded-2xl p-6">
            <div className="mb-6">
              <h2 className="text-lg font-semibold">Управление доступом к функциям</h2>
              <p className="text-sm text-dark-400">
                Настройте доступ к функциям для всей организации или отдельных отделов
              </p>
            </div>

            {isLoadingFeatures ? (
              <div className="flex items-center justify-center py-8">
                <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : featureSettingsData?.restricted_features.length === 0 ? (
              <div className="text-center py-8">
                <ToggleLeft className="w-12 h-12 mx-auto text-dark-600 mb-3" />
                <p className="text-dark-400">Нет настраиваемых функций</p>
              </div>
            ) : (
              <div className="space-y-6">
                {Object.entries(groupedFeatures).map(([featureName, { orgWide, departmentSettings }]) => {
                  const config = featureConfig[featureName] || {
                    icon: ToggleRight,
                    label: featureName.charAt(0).toUpperCase() + featureName.slice(1).replace(/_/g, ' '),
                    description: 'Управление доступом к функции'
                  };
                  const FeatureIcon = config.icon;
                  const isOrgWideEnabled = orgWide?.enabled ?? false;

                  return (
                    <div key={featureName} className="glass-light rounded-xl p-5">
                      {/* Feature Header */}
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-accent-500/20 flex items-center justify-center">
                            <FeatureIcon className="w-5 h-5 text-accent-400" />
                          </div>
                          <div>
                            <h3 className="font-medium">{config.label}</h3>
                            <p className="text-sm text-dark-400">{config.description}</p>
                          </div>
                        </div>
                      </div>

                      {/* Org-wide Toggle */}
                      <div className="p-3 glass-light rounded-lg mb-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Globe className="w-4 h-4 text-purple-400" />
                            <span className="text-sm font-medium">Для всей организации</span>
                          </div>
                          <button
                            onClick={() => handleOrgWideToggle(featureName, !isOrgWideEnabled)}
                            disabled={featureMutation.isPending || deleteFeatureMutation.isPending}
                            className={clsx(
                              'relative w-12 h-6 rounded-full transition-colors',
                              isOrgWideEnabled ? 'bg-accent-500' : 'bg-white/10'
                            )}
                          >
                            <span
                              className={clsx(
                                'absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform',
                                isOrgWideEnabled ? 'translate-x-6' : 'translate-x-0'
                              )}
                            />
                          </button>
                        </div>
                        <p className="text-xs text-dark-500 mt-2">
                          {isOrgWideEnabled
                            ? '✓ Все сотрудники имеют доступ (кроме тех, у кого есть индивидуальные настройки отдела)'
                            : 'Функция отключена для всех, кроме указанных отделов ниже'}
                        </p>
                      </div>

                      {/* Department-specific Settings */}
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Building2 className="w-4 h-4 text-blue-400" />
                            <span className="text-sm font-medium text-dark-300">Доступ для отделов</span>
                          </div>
                          {departmentSettings.length > 0 && (
                            <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded">
                              {departmentSettings.length} отдел{departmentSettings.length === 1 ? '' : departmentSettings.length < 5 ? 'а' : 'ов'}
                            </span>
                          )}
                        </div>

                        {/* Info about department settings */}
                        {!isOrgWideEnabled && departmentSettings.length === 0 && (
                          <p className="text-xs text-yellow-400/80 bg-yellow-500/10 px-3 py-2 rounded-lg">
                            ⚠️ Функция полностью отключена. Добавьте отделы ниже, чтобы дать им доступ.
                          </p>
                        )}

                        {isOrgWideEnabled && departmentSettings.length > 0 && (
                          <p className="text-xs text-blue-400/80 bg-blue-500/10 px-3 py-2 rounded-lg">
                            ℹ️ Указанные отделы имеют собственные настройки, которые переопределяют общую настройку.
                          </p>
                        )}

                        {/* Existing department settings */}
                        {departmentSettings.length > 0 && (
                          <div className="flex flex-wrap gap-2 mb-3">
                            {departmentSettings.map(setting => (
                              <span
                                key={setting.id}
                                className={clsx(
                                  "inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm",
                                  setting.enabled
                                    ? "bg-green-500/20 text-green-400"
                                    : "bg-red-500/20 text-red-400"
                                )}
                              >
                                {setting.enabled ? '✓' : '✗'} {setting.department_name || `Dept #${setting.department_id}`}
                                <button
                                  onClick={() => handleRemoveDepartmentSetting(featureName, setting.department_id!)}
                                  disabled={deleteFeatureMutation.isPending}
                                  className="ml-1 hover:text-white transition-colors"
                                  title="Удалить настройку (будет использоваться общая настройка организации)"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Add department select */}
                        <div className="flex gap-2">
                          <select
                            multiple
                            value={selectedDepartments[featureName]?.map(String) || []}
                            onChange={(e) => {
                              const values = Array.from(e.target.selectedOptions, option => parseInt(option.value));
                              setSelectedDepartments(prev => ({ ...prev, [featureName]: values }));
                            }}
                            className="flex-1 glass-light rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-500 min-h-[80px]"
                          >
                            {departments
                              .filter((dept): dept is Department & { id: number } =>
                                'id' in dept &&
                                typeof dept.id === 'number' &&
                                !departmentSettings.some(s => s.department_id === dept.id)
                              )
                              .map(dept => (
                                <option key={dept.id} value={dept.id}>
                                  {dept.name}
                                </option>
                              ))}
                          </select>
                          <button
                            onClick={() => handleAddDepartmentSetting(featureName)}
                            disabled={featureMutation.isPending || !selectedDepartments[featureName]?.length}
                            className="px-4 py-2 bg-accent-500 text-white rounded-lg hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                          >
                            <Plus className="w-4 h-4" />
                            Добавить
                          </button>
                        </div>
                        <p className="text-xs text-dark-500">
                          Удерживайте Ctrl/Cmd для выбора нескольких отделов
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Email Templates Section */}
        {activeTab === 'email-templates' && (isSuperAdmin() || user?.org_role === 'owner') && (
          <div className="glass rounded-2xl p-6">
            <div className="mb-4">
              <h2 className="text-lg font-semibold">Email шаблоны</h2>
              <p className="text-sm text-dark-400">
                Настройте шаблоны писем для автоматической отправки кандидатам
              </p>
            </div>
            <Suspense fallback={
              <div className="flex items-center justify-center py-12">
                <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
              </div>
            }>
              <EmailTemplatesSection embedded />
            </Suspense>
          </div>
        )}

        {/* Criteria Presets Section */}
        {activeTab === 'presets' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-lg font-semibold">Criteria Presets</h2>
              <p className="text-sm text-dark-400">
                Create reusable evaluation criteria templates
              </p>
            </div>
            <Dialog.Root open={isDialogOpen} onOpenChange={(open) => { setIsDialogOpen(open); if (!open) resetPresetForm(); }}>
              <Dialog.Trigger asChild>
                <button className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent-500 text-white hover:bg-accent-600 transition-colors">
                  <Plus className="w-5 h-5" />
                  New Preset
                </button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm" />
                <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl max-w-[calc(100%-2rem)] max-h-[90vh] glass rounded-2xl p-6 shadow-xl overflow-hidden flex flex-col">
                  <Dialog.Title className="text-xl font-semibold mb-4 flex-shrink-0">
                    {editingPresetId ? 'Edit Criteria Preset' : 'Create Criteria Preset'}
                  </Dialog.Title>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (editingPresetId) {
                        updateMutation.mutate();
                      } else {
                        createMutation.mutate();
                      }
                    }}
                    className="space-y-4 overflow-y-auto flex-1"
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm text-dark-400 mb-1">Name</label>
                        <input
                          type="text"
                          value={newPreset.name}
                          onChange={(e) => setNewPreset({ ...newPreset, name: e.target.value })}
                          required
                          className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                        />
                      </div>
                      <div>
                        <label className="block text-sm text-dark-400 mb-1">Category</label>
                        <input
                          type="text"
                          value={newPreset.category}
                          onChange={(e) => setNewPreset({ ...newPreset, category: e.target.value })}
                          className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm text-dark-400 mb-1">Description</label>
                      <textarea
                        value={newPreset.description}
                        onChange={(e) => setNewPreset({ ...newPreset, description: e.target.value })}
                        rows={2}
                        className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50 resize-none"
                      />
                    </div>

                    {user?.role === 'superadmin' && (
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={newPreset.is_global}
                          onChange={(e) => setNewPreset({ ...newPreset, is_global: e.target.checked })}
                          className="w-4 h-4 rounded accent-accent-500"
                        />
                        <span className="text-sm">Make this preset available to all users</span>
                      </label>
                    )}

                    {/* Criteria */}
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <label className="text-sm text-dark-400">Criteria</label>
                        <button
                          type="button"
                          onClick={handleAddCriterion}
                          className="flex items-center gap-1 text-xs text-accent-400 hover:text-accent-300"
                        >
                          <Plus className="w-3 h-3" />
                          Add
                        </button>
                      </div>
                      <div className="space-y-3 max-h-64 overflow-y-auto">
                        {newPreset.criteria.map((criterion, index) => (
                          <div key={index} className="glass-light rounded-xl p-3 space-y-2">
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={criterion.name}
                                onChange={(e) => handleUpdateCriterion(index, { name: e.target.value })}
                                placeholder="Criterion name"
                                className="flex-1 bg-transparent border-b border-white/10 pb-1 text-sm focus:outline-none focus:border-accent-500"
                              />
                              <button
                                type="button"
                                onClick={() => handleRemoveCriterion(index)}
                                className="text-dark-500 hover:text-red-400"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                            <textarea
                              value={criterion.description}
                              onChange={(e) => handleUpdateCriterion(index, { description: e.target.value })}
                              placeholder="Description"
                              rows={1}
                              className="w-full bg-transparent text-xs text-dark-400 resize-none focus:outline-none"
                            />
                            <div className="flex gap-4">
                              <select
                                value={criterion.category}
                                onChange={(e) => handleUpdateCriterion(index, { category: e.target.value as Criterion['category'] })}
                                className="bg-dark-800 rounded-lg px-2 py-1 text-xs focus:outline-none"
                              >
                                <option value="basic">Basic</option>
                                <option value="red_flags">Red Flags</option>
                                <option value="green_flags">Green Flags</option>
                              </select>
                              <div className="flex items-center gap-1">
                                <span className="text-xs text-dark-500">Weight:</span>
                                <input
                                  type="number"
                                  min="1"
                                  max="10"
                                  value={criterion.weight}
                                  onChange={(e) => handleUpdateCriterion(index, { weight: parseInt(e.target.value) })}
                                  className="w-12 bg-dark-800 rounded-lg px-2 py-1 text-xs focus:outline-none"
                                />
                              </div>
                            </div>
                          </div>
                        ))}
                        {newPreset.criteria.length === 0 && (
                          <p className="text-center text-dark-500 text-sm py-4">
                            No criteria added yet
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex gap-3 pt-4 flex-shrink-0">
                      <Dialog.Close asChild>
                        <button
                          type="button"
                          className="flex-1 py-2.5 rounded-xl glass-light hover:bg-white/10 transition-colors"
                        >
                          Cancel
                        </button>
                      </Dialog.Close>
                      <button
                        type="submit"
                        disabled={(editingPresetId ? updateMutation.isPending : createMutation.isPending) || newPreset.criteria.length === 0}
                        className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 transition-colors"
                      >
                        <Save className="w-4 h-4" />
                        {editingPresetId
                          ? (updateMutation.isPending ? 'Saving...' : 'Save')
                          : (createMutation.isPending ? 'Creating...' : 'Create')}
                      </button>
                    </div>
                  </form>
                  <Dialog.Close asChild>
                    <button className="absolute top-4 right-4 p-2 rounded-lg hover:bg-dark-800/50">
                      <X className="w-5 h-5" />
                    </button>
                  </Dialog.Close>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : presets.length === 0 ? (
            <div className="text-center py-8">
              <Settings className="w-12 h-12 mx-auto text-dark-600 mb-3" />
              <p className="text-dark-400">No presets yet</p>
              <p className="text-dark-500 text-sm mt-1">
                Create your first criteria preset
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {Object.entries(groupedPresets).map(([group, items]) => (
                <div key={group}>
                  <div className="flex items-center gap-2 mb-3">
                    {group === 'Global' ? (
                      <Globe className="w-4 h-4 text-purple-400" />
                    ) : (
                      <UserIcon className="w-4 h-4 text-blue-400" />
                    )}
                    <h3 className="text-sm font-medium text-dark-400">{group} Presets</h3>
                  </div>
                  <div className="space-y-2">
                    {items.map((preset) => (
                      <motion.div
                        key={preset.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="flex items-start gap-4 glass-light rounded-xl p-4"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="font-medium">{preset.name}</h4>
                            <span className="px-2 py-0.5 rounded-full text-xs bg-dark-700 text-dark-400">
                              {preset.criteria.length} criteria
                            </span>
                          </div>
                          {preset.description && (
                            <p className="text-sm text-dark-400 mb-2">{preset.description}</p>
                          )}
                          <div className="flex flex-wrap gap-1">
                            {preset.criteria.slice(0, 3).map((c, i) => {
                              const config = categoryConfig[c.category as keyof typeof categoryConfig];
                              return (
                                <span
                                  key={i}
                                  className={clsx('px-2 py-0.5 rounded-full text-xs', config?.color)}
                                >
                                  {c.name}
                                </span>
                              );
                            })}
                            {preset.criteria.length > 3 && (
                              <span className="text-xs text-dark-500">
                                +{preset.criteria.length - 3} more
                              </span>
                            )}
                          </div>
                        </div>
                        {(preset.created_by === user?.id || user?.role === 'superadmin') && (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => startEditPreset(preset)}
                              className="p-2 rounded-lg text-dark-400 hover:text-accent-400 hover:bg-accent-500/10 transition-colors"
                              title="Edit preset"
                            >
                              <Edit3 className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm('Delete this preset?')) {
                                  deleteMutation.mutate(preset.id);
                                }
                              }}
                              className="p-2 rounded-lg text-dark-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                              title="Delete preset"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        )}
                      </motion.div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        )}

        {/* Account Info */}
        {activeTab === 'general' && (
        <>
        <div className="glass rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Аккаунт</h2>
            {!isEditingProfile ? (
              <button
                onClick={() => setIsEditingProfile(true)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-accent-400 hover:bg-accent-500/10 transition-colors"
              >
                <Edit3 className="w-4 h-4" />
                Редактировать
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={handleCancelEdit}
                  className="px-3 py-1.5 rounded-lg text-sm text-dark-400 hover:bg-dark-800/50 transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={handleSaveProfile}
                  disabled={profileMutation.isPending}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 transition-colors"
                >
                  <Save className="w-4 h-4" />
                  {profileMutation.isPending ? 'Сохранение...' : 'Сохранить'}
                </button>
              </div>
            )}
          </div>

          <div className="space-y-4">
            {/* Basic Info */}
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-500/20 to-purple-500/20 flex items-center justify-center">
                <span className="text-2xl font-bold text-accent-400">
                  {(isEditingProfile ? profileData.name : user?.name)?.[0]?.toUpperCase() || 'U'}
                </span>
              </div>
              <div className="flex-1">
                {isEditingProfile ? (
                  <input
                    type="text"
                    value={profileData.name}
                    onChange={(e) => setProfileData({ ...profileData, name: e.target.value })}
                    placeholder="Ваше имя"
                    className="w-full glass-light rounded-lg py-2 px-3 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                  />
                ) : (
                  <h3 className="font-semibold text-lg">{user?.name}</h3>
                )}
                <p className="text-dark-400">{user?.email}</p>
                <span
                  className={clsx(
                    'inline-block mt-1 px-2 py-0.5 rounded-full text-xs font-medium',
                    user?.role === 'superadmin'
                      ? 'bg-purple-500/20 text-purple-400'
                      : 'bg-blue-500/20 text-blue-400'
                  )}
                >
                  {user?.role}
                </span>
              </div>
            </div>

            {/* Telegram Username */}
            <div className="glass-light rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <AtSign className="w-4 h-4 text-blue-400" />
                <p className="text-sm text-dark-400">Telegram</p>
              </div>
              {isEditingProfile ? (
                <input
                  type="text"
                  value={profileData.telegram_username}
                  onChange={(e) => setProfileData({ ...profileData, telegram_username: e.target.value })}
                  placeholder="@username"
                  className="w-full bg-transparent border-b border-white/10 pb-1 focus:outline-none focus:border-accent-500"
                />
              ) : (
                <p className="font-medium">
                  {user?.telegram_username ? `@${user.telegram_username}` : 'Не указан'}
                </p>
              )}
            </div>

            {/* Additional Emails */}
            <div className="glass-light rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <Mail className="w-4 h-4 text-cyan-400" />
                <p className="text-sm text-dark-400">Дополнительные Email (для распознавания спикера)</p>
              </div>

              {isEditingProfile ? (
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddEmail())}
                      placeholder="email@example.com"
                      className="flex-1 glass-light rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-500"
                    />
                    <button
                      onClick={handleAddEmail}
                      className="px-3 py-2 bg-accent-500/20 text-accent-400 rounded-lg hover:bg-accent-500/30 transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {profileData.additional_emails.map((email) => (
                      <span
                        key={email}
                        className="flex items-center gap-1 px-2 py-1 bg-cyan-500/20 text-cyan-400 rounded-lg text-sm"
                      >
                        {email}
                        <button
                          onClick={() => handleRemoveEmail(email)}
                          className="hover:text-red-400"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                    {profileData.additional_emails.length === 0 && (
                      <span className="text-sm text-dark-500">Нет дополнительных email</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {(user?.additional_emails || []).map((email) => (
                    <span
                      key={email}
                      className="px-2 py-1 bg-cyan-500/20 text-cyan-400 rounded-lg text-sm"
                    >
                      {email}
                    </span>
                  ))}
                  {(!user?.additional_emails || user.additional_emails.length === 0) && (
                    <span className="text-sm text-dark-500">Нет дополнительных email</span>
                  )}
                </div>
              )}
            </div>

            {/* Additional Telegram Usernames */}
            <div className="glass-light rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <AtSign className="w-4 h-4 text-purple-400" />
                <p className="text-sm text-dark-400">Дополнительные Telegram (для распознавания спикера)</p>
              </div>

              {isEditingProfile ? (
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newTelegramUsername}
                      onChange={(e) => setNewTelegramUsername(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddTelegramUsername())}
                      placeholder="@username"
                      className="flex-1 glass-light rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent-500"
                    />
                    <button
                      onClick={handleAddTelegramUsername}
                      className="px-3 py-2 bg-accent-500/20 text-accent-400 rounded-lg hover:bg-accent-500/30 transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {profileData.additional_telegram_usernames.map((username) => (
                      <span
                        key={username}
                        className="flex items-center gap-1 px-2 py-1 bg-purple-500/20 text-purple-400 rounded-lg text-sm"
                      >
                        @{username}
                        <button
                          onClick={() => handleRemoveTelegramUsername(username)}
                          className="hover:text-red-400"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                    {profileData.additional_telegram_usernames.length === 0 && (
                      <span className="text-sm text-dark-500">Нет дополнительных Telegram</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {(user?.additional_telegram_usernames || []).map((username) => (
                    <span
                      key={username}
                      className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded-lg text-sm"
                    >
                      @{username}
                    </span>
                  ))}
                  {(!user?.additional_telegram_usernames || user.additional_telegram_usernames.length === 0) && (
                    <span className="text-sm text-dark-500">Нет дополнительных Telegram</span>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Performance Settings */}
        <div className="glass rounded-2xl p-6 mt-6">
          <h2 className="text-lg font-semibold mb-4">Производительность</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Анимации фона</p>
                <p className="text-xs text-dark-400">Aurora, частицы и другие эффекты (увеличивает нагрузку на CPU/GPU)</p>
              </div>
              <button
                onClick={() => {
                  const newValue = !animationsEnabled;
                  setAnimationsEnabled(newValue);
                  if (newValue) {
                    document.body.classList.remove('performance-mode');
                  } else {
                    document.body.classList.add('performance-mode');
                  }
                  localStorage.setItem('animations-enabled', newValue ? 'true' : 'false');
                  toast.success(newValue ? 'Анимации включены' : 'Анимации отключены');
                }}
                className={clsx(
                  'relative w-12 h-6 rounded-full transition-colors',
                  animationsEnabled ? 'bg-accent-500' : 'bg-white/10'
                )}
              >
                <span
                  className={clsx(
                    'absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform',
                    animationsEnabled ? 'translate-x-6' : 'translate-x-0'
                  )}
                />
              </button>
            </div>
          </div>
        </div>
        </>
        )}
      </motion.div>
    </div>
  );
}
