import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Shield,
  Check,
  X,
  Eye,
  Edit,
  Trash2,
  Share2,
  ArrowRightLeft,
  User,
  Users,
  Building2,
  Crown,
  AlertCircle,
  CheckCircle2,
  MessageSquare,
  Phone,
  UserCheck,
  Target,
  Play,
  Plus,
  LogIn,
  Database
} from 'lucide-react';
import clsx from 'clsx';
import { useAuthStore } from '@/stores/authStore';
import api from '@/services/api';
import RoleManagement from '@/components/admin/RoleManagement';

// Типы ролей
type OrgRole = 'superadmin' | 'owner' | 'admin' | 'sub_admin' | 'member';
type ResourceType = 'entity' | 'chat' | 'call';
type ActionType = 'view' | 'edit' | 'delete' | 'share' | 'transfer';
type AccessLevel = 'view' | 'edit' | 'full';

// Конфигурация ролей
const ROLES: { id: OrgRole; name: string; icon: typeof Crown; description: string; color: string }[] = [
  {
    id: 'superadmin',
    name: 'Суперадмин',
    icon: Crown,
    description: 'Глобальный доступ ко всему',
    color: 'text-purple-400'
  },
  {
    id: 'owner',
    name: 'Владелец',
    icon: Building2,
    description: 'Доступ ко всему в организации',
    color: 'text-cyan-400'
  },
  {
    id: 'admin',
    name: 'Админ (Лид)',
    icon: Shield,
    description: 'Полный доступ к своему департаменту',
    color: 'text-blue-400'
  },
  {
    id: 'sub_admin',
    name: 'Саб-Админ',
    icon: Shield,
    description: 'Полный доступ к департаменту (кроме удаления других админов)',
    color: 'text-indigo-400'
  },
  {
    id: 'member',
    name: 'Сотрудник',
    icon: User,
    description: 'Доступ только к своим ресурсам',
    color: 'text-green-400'
  }
];

// Конфигурация действий
const ACTIONS: { id: ActionType; name: string; icon: typeof Eye; color: string }[] = [
  { id: 'view', name: 'Просмотр', icon: Eye, color: 'text-blue-400' },
  { id: 'edit', name: 'Редактирование', icon: Edit, color: 'text-yellow-400' },
  { id: 'delete', name: 'Удаление', icon: Trash2, color: 'text-red-400' },
  { id: 'share', name: 'Расшаривание', icon: Share2, color: 'text-purple-400' },
  { id: 'transfer', name: 'Передача', icon: ArrowRightLeft, color: 'text-orange-400' }
];

// Конфигурация ресурсов
const RESOURCES: { id: ResourceType; name: string; icon: typeof UserCheck }[] = [
  { id: 'entity', name: 'Контакт', icon: UserCheck },
  { id: 'chat', name: 'Чат', icon: MessageSquare },
  { id: 'call', name: 'Звонок', icon: Phone }
];

// Уровни доступа при расшаривании
const ACCESS_LEVELS: { id: AccessLevel; name: string }[] = [
  { id: 'view', name: 'Только просмотр' },
  { id: 'edit', name: 'Редактирование' },
  { id: 'full', name: 'Полный доступ' }
];

// Типы для sandbox
interface SandboxUser {
  email: string;
  role: string;
  role_label: string;
}

interface SandboxStatus {
  exists: boolean;
  department_id?: number;
  department_name?: string;
  users?: SandboxUser[];
  stats?: {
    contacts: number;
    chats: number;
    calls: number;
  };
}

export default function AdminSimulatorPage() {
  const { user, isSuperAdmin, isLoading: authLoading } = useAuthStore();

  // Sandbox state
  const [sandboxStatus, setSandboxStatus] = useState<SandboxStatus>({ exists: false });
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);
  const [pageLoading, setPageLoading] = useState(true);

  // Matrix mode state
  const [matrixMode, setMatrixMode] = useState<'own' | 'dept' | 'shared_full' | 'shared_edit' | 'shared_view' | 'other_dept'>('own');

  // Состояние для тестирования сценариев
  const [scenario, setScenario] = useState({
    actorRole: 'member' as OrgRole,
    actorIsOwner: false,
    actorSameDepartment: true,
    action: 'view' as ActionType,
    resourceType: 'entity' as ResourceType,
    resourceOwnerRole: 'member' as OrgRole,
    resourceIsShared: false,
    resourceAccessLevel: 'view' as AccessLevel,
    targetUserRole: 'member' as OrgRole,
    targetSameDepartment: true
  });

  // Загрузка статуса sandbox при монтировании
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        await fetchSandboxStatus();
      } catch (e) {
        console.error('Failed to load sandbox status:', e);
      } finally {
        setPageLoading(false);
      }
    };

    // Timeout fallback - if auth takes too long, stop loading anyway
    const timeout = setTimeout(() => {
      if (pageLoading) {
        console.warn('AdminSimulator: Auth loading timeout, forcing page load');
        setPageLoading(false);
      }
    }, 5000);

    if (!authLoading && user) {
      loadInitialData();
    } else if (!authLoading && !user) {
      setPageLoading(false);
    }

    return () => clearTimeout(timeout);
  }, [authLoading, user, pageLoading]);

  // Функции для работы с sandbox
  // Helper to extract error message from API errors
  const getErrorMessage = (error: unknown, fallback: string): string => {
    const axiosError = error as { response?: { data?: { detail?: string } } };
    return axiosError.response?.data?.detail || fallback;
  };

  const fetchSandboxStatus = async () => {
    try {
      const response = await api.get('/admin/sandbox/status');
      setSandboxStatus(response.data);
      setSandboxError(null);
    } catch (error: unknown) {
      console.error('Error fetching sandbox status:', error);
      setSandboxError(getErrorMessage(error, 'Ошибка загрузки статуса sandbox'));
    }
  };

  const createSandbox = async () => {
    setSandboxLoading(true);
    setSandboxError(null);
    try {
      await api.post('/admin/sandbox/create');
      // Re-fetch status to get proper SandboxStatus format
      await fetchSandboxStatus();
    } catch (error: unknown) {
      console.error('Error creating sandbox:', error);
      setSandboxError(getErrorMessage(error, 'Ошибка создания sandbox'));
    } finally {
      setSandboxLoading(false);
    }
  };

  const deleteSandbox = async () => {
    if (!confirm('Вы уверены, что хотите удалить тестовое окружение?')) {
      return;
    }
    setSandboxLoading(true);
    setSandboxError(null);
    try {
      await api.delete('/admin/sandbox');
      setSandboxStatus({ exists: false });
    } catch (error: unknown) {
      console.error('Error deleting sandbox:', error);
      setSandboxError(getErrorMessage(error, 'Ошибка удаления sandbox'));
    } finally {
      setSandboxLoading(false);
    }
  };

  const switchToUser = async (email: string) => {
    // Validate sandbox exists before switching
    if (!sandboxStatus?.exists) {
      setSandboxError('Sandbox не существует. Сначала создайте sandbox.');
      return;
    }

    setSandboxLoading(true);
    setSandboxError(null);
    try {
      const response = await api.post(`/admin/sandbox/switch/${encodeURIComponent(email)}`);
      // Verify response was successful before redirecting
      if (response.status === 200) {
        // Cookie is set by backend via Set-Cookie header
        // Reload page to apply new session
        window.location.href = '/';
      } else {
        throw new Error('Неожиданный ответ сервера');
      }
    } catch (error: unknown) {
      console.error('Error switching user:', error);
      setSandboxError(getErrorMessage(error, 'Ошибка переключения пользователя'));
      setSandboxLoading(false);
    }
  };

  // Показать загрузку пока данные пользователя загружаются
  if (authLoading || pageLoading) {
    return (
      <div className="h-full flex items-center justify-center p-6 bg-dark-900">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center"
        >
          <div className="w-12 h-12 border-2 border-accent-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-white/60">Загрузка симулятора...</p>
        </motion.div>
      </div>
    );
  }

  // Проверка доступа - только для SUPERADMIN
  if (!isSuperAdmin()) {
    return (
      <div className="h-full flex items-center justify-center p-6 bg-dark-900">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass rounded-2xl p-8 max-w-md text-center"
        >
          <AlertCircle className="w-16 h-16 mx-auto mb-4 text-red-400" />
          <h2 className="text-2xl font-bold mb-2">Доступ запрещён</h2>
          <p className="text-white/60">
            Эта страница доступна только пользователям с ролью SUPERADMIN
          </p>
          <p className="text-sm text-white/40 mt-2">
            Текущая роль: {user?.role || 'не определена'}
          </p>
        </motion.div>
      </div>
    );
  }

  // Логика проверки прав доступа (имитация backend)
  const checkPermission = (
    role: OrgRole,
    action: ActionType,
    isOwner: boolean,
    isShared: boolean,
    accessLevel?: AccessLevel,
    sameDepartment?: boolean
  ): boolean => {
    // SUPERADMIN имеет доступ ко всему
    if (role === 'superadmin') return true;

    // OWNER имеет доступ ко всему в организации
    if (role === 'owner') return true;

    // Проверка для владельца ресурса
    if (isOwner) {
      return true; // Владелец может делать всё со своими ресурсами
    }

    // ADMIN и SUB_ADMIN имеют ПОЛНЫЙ доступ к ресурсам своего департамента
    if (role === 'admin' || role === 'sub_admin') {
      if (sameDepartment) {
        // Полный доступ: просмотр, редактирование, удаление, расшаривание, передача
        return true;
      }
      // Вне департамента - только если расшарено
    }

    // Проверка для расшаренных ресурсов (для любой роли)
    if (isShared) {
      if (action === 'view') return true; // Любой уровень доступа позволяет просмотр
      if (action === 'edit') return accessLevel === 'edit' || accessLevel === 'full';
      if (action === 'delete') return false; // Нельзя удалять расшаренное (только своё)
      if (action === 'share') return accessLevel === 'full';
      if (action === 'transfer') return false; // Нельзя передавать чужое
    }

    // MEMBER может работать только со своими ресурсами (isOwner уже проверено выше)
    return false;
  };

  // Проверка возможности расшаривания
  const canShareTo = (
    fromRole: OrgRole,
    toRole: OrgRole,
    sameDepartment: boolean
  ): boolean => {
    // SUPERADMIN может расшарить кому угодно
    if (fromRole === 'superadmin') return true;

    // OWNER может расшарить кому угодно в организации
    if (fromRole === 'owner') return true;

    // ADMIN и SUB_ADMIN могут расшарить:
    // - OWNER/SUPERADMIN (всегда)
    // - другим админам/саб-админам (любой департамент - между руководителями)
    // - сотрудникам своего департамента
    if (fromRole === 'admin' || fromRole === 'sub_admin') {
      if (toRole === 'owner' || toRole === 'superadmin') return true;
      if (toRole === 'admin' || toRole === 'sub_admin') return true; // Между руководителями
      if (toRole === 'member' && sameDepartment) return true;
      return false;
    }

    // MEMBER может расшарить только в своём департаменте
    if (fromRole === 'member') {
      return sameDepartment;
    }

    return false;
  };

  // Выполнение теста сценария
  const testScenario = (): { allowed: boolean; reason: string } => {
    const {
      actorRole,
      actorIsOwner,
      actorSameDepartment,
      action,
      resourceIsShared,
      resourceAccessLevel,
      targetUserRole,
      targetSameDepartment
    } = scenario;

    // Проверка расшаривания - особый случай
    if (action === 'share') {
      const canShare = checkPermission(
        actorRole,
        'share',
        actorIsOwner,
        resourceIsShared,
        resourceAccessLevel,
        actorSameDepartment
      );

      if (!canShare) {
        return {
          allowed: false,
          reason: 'У вас нет прав на расшаривание этого ресурса'
        };
      }

      const canShareToTarget = canShareTo(actorRole, targetUserRole, targetSameDepartment);

      if (!canShareToTarget) {
        let reason = 'Нельзя расшарить этому пользователю';

        if (actorRole === 'member' && !targetSameDepartment) {
          reason = 'Сотрудник может расшаривать только в своём департаменте';
        } else if (actorRole === 'admin' && targetUserRole === 'member' && !targetSameDepartment) {
          reason = 'Админ может расшарить сотруднику только в своём департаменте';
        }

        return { allowed: false, reason };
      }

      return { allowed: true, reason: 'Расшаривание разрешено' };
    }

    // Проверка других действий
    const allowed = checkPermission(
      actorRole,
      action,
      actorIsOwner,
      resourceIsShared,
      resourceAccessLevel,
      actorSameDepartment
    );

    if (allowed) {
      let reason = '';
      if (actorRole === 'superadmin') reason = 'SUPERADMIN имеет полный доступ';
      else if (actorRole === 'owner') reason = 'OWNER имеет доступ ко всему в организации';
      else if (actorIsOwner) reason = 'Вы владелец этого ресурса';
      else if ((actorRole === 'admin' || actorRole === 'sub_admin') && actorSameDepartment) {
        reason = 'Руководитель департамента имеет полный доступ к ресурсам своего отдела';
      } else if (resourceIsShared) {
        if (action === 'view') reason = 'Ресурс расшарен вам';
        else if (action === 'edit') reason = `Уровень доступа "${ACCESS_LEVELS.find(l => l.id === resourceAccessLevel)?.name}" позволяет редактирование`;
        else if ((action as ActionType) === 'share') reason = 'Уровень доступа "Полный доступ" позволяет расшаривание';
      }

      return { allowed: true, reason };
    } else {
      let reason = '';

      if ((actorRole === 'admin' || actorRole === 'sub_admin') && !actorSameDepartment && !resourceIsShared) {
        reason = 'Ресурс находится в другом департаменте и не расшарен вам';
      } else if (!actorIsOwner && !resourceIsShared && !(actorRole === 'admin' || actorRole === 'sub_admin')) {
        reason = 'Ресурс вам не принадлежит и не расшарен';
      } else if (resourceIsShared && action === 'delete') {
        reason = 'Нельзя удалять чужие ресурсы, даже расшаренные';
      } else if (resourceIsShared && action === 'transfer') {
        reason = 'Нельзя передавать чужие ресурсы';
      } else if (resourceIsShared && action === 'edit') {
        reason = `Уровень доступа "${ACCESS_LEVELS.find(l => l.id === resourceAccessLevel)?.name}" не позволяет редактирование`;
      } else if (resourceIsShared && (action as ActionType) === 'share' && resourceAccessLevel !== 'full') {
        reason = 'Только "Полный доступ" позволяет расшаривание';
      } else if (actorRole === 'member') {
        reason = 'Сотрудник может работать только со своими ресурсами';
      }

      return { allowed: false, reason };
    }
  };

  const testResult = testScenario();

  return (
    <div className="h-full w-full max-w-full overflow-y-auto overflow-x-hidden p-6 bg-dark-900 min-h-screen">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-7xl mx-auto space-y-6 w-full"
      >
        {/* Заголовок */}
        <div className="flex items-center gap-4">
          <div className="p-3 rounded-xl bg-purple-500/20">
            <Shield className="w-8 h-8 text-purple-400" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-white">Симулятор ролей и прав доступа</h1>
            <p className="text-white/60">Тестирование матрицы доступа и сценариев</p>
          </div>
        </div>

        {/* Custom Role Management */}
        <div className="glass rounded-2xl p-6">
          <RoleManagement />
        </div>

        {/* Матрица доступа */}
        <div className="glass rounded-2xl p-6">
          <div className="mb-6">
            <h2 className="text-xl font-bold text-white mb-2">Матрица доступа</h2>
            <p className="text-white/60 text-sm">
              Какие действия может выполнять каждая роль с ресурсами
            </p>
          </div>

          {/* Переключатель режима матрицы */}
          <div className="mb-4">
            <label className="block text-sm text-white/60 mb-2">Режим доступа к ресурсу:</label>
            <div className="flex flex-wrap gap-2">
              {[
                { id: 'own', label: 'Свои ресурсы', color: 'green' },
                { id: 'dept', label: 'Ресурсы департамента (чужие)', color: 'cyan' },
                { id: 'shared_full', label: 'Расшаренные (полный доступ)', color: 'blue' },
                { id: 'shared_edit', label: 'Расшаренные (редактирование)', color: 'yellow' },
                { id: 'shared_view', label: 'Расшаренные (только просмотр)', color: 'purple' },
                { id: 'other_dept', label: 'Другой департамент (не расшарено)', color: 'red' },
              ].map((mode) => (
                <button
                  key={mode.id}
                  onClick={() => setMatrixMode(mode.id as typeof matrixMode)}
                  className={clsx(
                    'px-3 py-1.5 rounded-lg text-sm font-medium transition-all',
                    matrixMode === mode.id
                      ? `bg-${mode.color}-500/30 text-${mode.color}-400 border border-${mode.color}-500/50`
                      : 'glass-light text-white/60 hover:bg-white/10'
                  )}
                  style={matrixMode === mode.id ? {
                    backgroundColor: mode.color === 'green' ? 'rgba(34, 197, 94, 0.3)' :
                                    mode.color === 'cyan' ? 'rgba(6, 182, 212, 0.3)' :
                                    mode.color === 'blue' ? 'rgba(59, 130, 246, 0.3)' :
                                    mode.color === 'yellow' ? 'rgba(234, 179, 8, 0.3)' :
                                    mode.color === 'purple' ? 'rgba(168, 85, 247, 0.3)' :
                                    'rgba(239, 68, 68, 0.3)',
                    color: mode.color === 'green' ? 'rgb(74, 222, 128)' :
                           mode.color === 'cyan' ? 'rgb(34, 211, 238)' :
                           mode.color === 'blue' ? 'rgb(96, 165, 250)' :
                           mode.color === 'yellow' ? 'rgb(250, 204, 21)' :
                           mode.color === 'purple' ? 'rgb(192, 132, 252)' :
                           'rgb(248, 113, 113)',
                    borderColor: mode.color === 'green' ? 'rgba(34, 197, 94, 0.5)' :
                                 mode.color === 'cyan' ? 'rgba(6, 182, 212, 0.5)' :
                                 mode.color === 'blue' ? 'rgba(59, 130, 246, 0.5)' :
                                 mode.color === 'yellow' ? 'rgba(234, 179, 8, 0.5)' :
                                 mode.color === 'purple' ? 'rgba(168, 85, 247, 0.5)' :
                                 'rgba(239, 68, 68, 0.5)'
                  } : undefined}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>

          {/* Легенда */}
          <div className="mb-4 flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-green-500/20 flex items-center justify-center">
                <Check size={16} className="text-green-400" />
              </div>
              <span className="text-white/60">Разрешено</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg glass-light flex items-center justify-center">
                <X size={16} className="text-white/40" />
              </div>
              <span className="text-white/60">Запрещено</span>
            </div>
          </div>

          {/* Таблица */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-3 px-4 text-white/60 font-medium">Действие</th>
                  {ROLES.map((role) => (
                    <th key={role.id} className="text-center py-3 px-4">
                      <div className="flex flex-col items-center gap-2">
                        <role.icon className={clsx('w-5 h-5', role.color)} />
                        <span className="text-sm font-medium text-white">{role.name}</span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ACTIONS.map((action) => (
                  <tr key={action.id} className="border-b border-white/5">
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-3">
                        <action.icon className={clsx('w-5 h-5', action.color)} />
                        <span className="text-white font-medium">{action.name}</span>
                      </div>
                    </td>
                    {ROLES.map((role) => {
                      // Определяем доступ в зависимости от выбранного режима
                      let allowed = false;

                      if (matrixMode === 'own') {
                        // Свои ресурсы - все могут делать всё со своими
                        allowed = checkPermission(role.id, action.id, true, false, undefined, true);
                      } else if (matrixMode === 'dept') {
                        // Ресурсы департамента (чужие) - только для admin/sub_admin
                        allowed = checkPermission(role.id, action.id, false, false, undefined, true);
                      } else if (matrixMode === 'shared_full') {
                        // Расшаренные с полным доступом
                        allowed = checkPermission(role.id, action.id, false, true, 'full', false);
                      } else if (matrixMode === 'shared_edit') {
                        // Расшаренные с правами редактирования
                        allowed = checkPermission(role.id, action.id, false, true, 'edit', false);
                      } else if (matrixMode === 'shared_view') {
                        // Расшаренные только для просмотра
                        allowed = checkPermission(role.id, action.id, false, true, 'view', false);
                      } else if (matrixMode === 'other_dept') {
                        // Другой департамент, не расшарено
                        allowed = checkPermission(role.id, action.id, false, false, undefined, false);
                      }

                      return (
                        <td key={role.id} className="py-4 px-4">
                          <div className="flex justify-center">
                            <div className={clsx(
                              'w-8 h-8 rounded-lg flex items-center justify-center',
                              allowed ? 'bg-green-500/20' : 'glass-light'
                            )}>
                              {allowed ? (
                                <Check size={16} className="text-green-400" />
                              ) : (
                                <X size={16} className="text-white/40" />
                              )}
                            </div>
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Примечания */}
          <div className="mt-4 p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl">
            <h3 className="text-sm font-semibold text-blue-400 mb-2">Правила доступа:</h3>
            <ul className="text-sm text-white/70 space-y-1">
              <li>• <strong>SUPERADMIN</strong>: полный доступ ко всему в системе</li>
              <li>• <strong>OWNER</strong>: полный доступ ко всему в организации</li>
              <li>• <strong>ADMIN (Лид)</strong>: полный доступ к своему департаменту (просмотр, редактирование, удаление, расшаривание, передача)</li>
              <li>• <strong>SUB_ADMIN</strong>: полный доступ к департаменту (как ADMIN, но не может удалять других админов)</li>
              <li>• <strong>MEMBER</strong>: работает только со своими ресурсами и расшаренными ему</li>
              <li>• Расшаривание между админами: ADMIN и SUB_ADMIN могут расшаривать друг другу (между департаментами)</li>
              <li>• Расшаренные ресурсы: нельзя удалять или передавать, даже с полным доступом</li>
            </ul>
          </div>
        </div>

        {/* Тестирование сценариев */}
        <div className="glass rounded-2xl p-6">
          <div className="mb-6">
            <h2 className="text-xl font-bold text-white mb-2">Тестирование сценария</h2>
            <p className="text-white/60 text-sm">
              Проверьте, разрешено ли конкретное действие в заданных условиях
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Настройки актёра */}
            <div className="space-y-4">
              <h3 className="font-semibold text-white flex items-center gap-2">
                <Users className="w-5 h-5 text-cyan-400" />
                Актёр (кто выполняет действие)
              </h3>

              <div>
                <label className="block text-sm text-white/60 mb-2">Роль актёра</label>
                <select
                  value={scenario.actorRole}
                  onChange={(e) => setScenario({ ...scenario, actorRole: e.target.value as OrgRole })}
                  className="w-full px-4 py-2.5 glass-light rounded-xl text-white focus:outline-none focus:border-cyan-500/50"
                >
                  {ROLES.map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm cursor-pointer group">
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={scenario.actorIsOwner}
                      onChange={(e) => setScenario({ ...scenario, actorIsOwner: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-5 h-5 border-2 border-white/30 rounded glass-light peer-checked:bg-cyan-500 peer-checked:border-cyan-500 transition-colors flex items-center justify-center">
                      {scenario.actorIsOwner && <Check size={14} className="text-white" />}
                    </div>
                  </div>
                  <span className="text-white/80 group-hover:text-white transition-colors">Актёр - владелец ресурса</span>
                </label>
              </div>

              {!scenario.actorIsOwner && (
                <div>
                  <label className="flex items-center gap-2 text-sm cursor-pointer group">
                    <div className="relative">
                      <input
                        type="checkbox"
                        checked={scenario.actorSameDepartment}
                        onChange={(e) => setScenario({ ...scenario, actorSameDepartment: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-5 h-5 border-2 border-white/30 rounded glass-light peer-checked:bg-cyan-500 peer-checked:border-cyan-500 transition-colors flex items-center justify-center">
                        {scenario.actorSameDepartment && <Check size={14} className="text-white" />}
                      </div>
                    </div>
                    <span className="text-white/80 group-hover:text-white transition-colors">Ресурс в том же департаменте</span>
                  </label>
                </div>
              )}

              {!scenario.actorIsOwner && (
                <div>
                  <label className="flex items-center gap-2 text-sm cursor-pointer group">
                    <div className="relative">
                      <input
                        type="checkbox"
                        checked={scenario.resourceIsShared}
                        onChange={(e) => setScenario({ ...scenario, resourceIsShared: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-5 h-5 border-2 border-white/30 rounded glass-light peer-checked:bg-cyan-500 peer-checked:border-cyan-500 transition-colors flex items-center justify-center">
                        {scenario.resourceIsShared && <Check size={14} className="text-white" />}
                      </div>
                    </div>
                    <span className="text-white/80 group-hover:text-white transition-colors">Ресурс расшарен актёру</span>
                  </label>
                </div>
              )}

              {scenario.resourceIsShared && !scenario.actorIsOwner && (
                <div>
                  <label className="block text-sm text-white/60 mb-2">Уровень доступа</label>
                  <select
                    value={scenario.resourceAccessLevel}
                    onChange={(e) => setScenario({ ...scenario, resourceAccessLevel: e.target.value as AccessLevel })}
                    className="w-full px-4 py-2.5 glass-light rounded-xl text-white focus:outline-none focus:border-cyan-500/50"
                  >
                    {ACCESS_LEVELS.map((level) => (
                      <option key={level.id} value={level.id}>
                        {level.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Настройки действия и цели */}
            <div className="space-y-4">
              <h3 className="font-semibold text-white flex items-center gap-2">
                <Target className="w-5 h-5 text-purple-400" />
                Действие и цель
              </h3>

              <div>
                <label className="block text-sm text-white/60 mb-2">Тип ресурса</label>
                <select
                  value={scenario.resourceType}
                  onChange={(e) => setScenario({ ...scenario, resourceType: e.target.value as ResourceType })}
                  className="w-full px-4 py-2.5 glass-light rounded-xl text-white focus:outline-none focus:border-cyan-500/50"
                >
                  {RESOURCES.map((resource) => (
                    <option key={resource.id} value={resource.id}>
                      {resource.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-2">Действие</label>
                <select
                  value={scenario.action}
                  onChange={(e) => setScenario({ ...scenario, action: e.target.value as ActionType })}
                  className="w-full px-4 py-2.5 glass-light rounded-xl text-white focus:outline-none focus:border-cyan-500/50"
                >
                  {ACTIONS.map((action) => (
                    <option key={action.id} value={action.id}>
                      {action.name}
                    </option>
                  ))}
                </select>
              </div>

              {scenario.action === 'share' && (
                <>
                  <div>
                    <label className="block text-sm text-white/60 mb-2">Роль целевого пользователя</label>
                    <select
                      value={scenario.targetUserRole}
                      onChange={(e) => setScenario({ ...scenario, targetUserRole: e.target.value as OrgRole })}
                      className="w-full px-4 py-2.5 glass-light rounded-xl text-white focus:outline-none focus:border-cyan-500/50"
                    >
                      {ROLES.map((role) => (
                        <option key={role.id} value={role.id}>
                          {role.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="flex items-center gap-2 text-sm cursor-pointer group">
                      <div className="relative">
                        <input
                          type="checkbox"
                          checked={scenario.targetSameDepartment}
                          onChange={(e) => setScenario({ ...scenario, targetSameDepartment: e.target.checked })}
                          className="sr-only peer"
                        />
                        <div className="w-5 h-5 border-2 border-white/30 rounded glass-light peer-checked:bg-cyan-500 peer-checked:border-cyan-500 transition-colors flex items-center justify-center">
                          {scenario.targetSameDepartment && <Check size={14} className="text-white" />}
                        </div>
                      </div>
                      <span className="text-white/80 group-hover:text-white transition-colors">Цель в том же департаменте</span>
                    </label>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Результат */}
          <div className="mt-6">
            <div
              className={clsx(
                'p-6 rounded-xl border-2 transition-all',
                testResult.allowed
                  ? 'bg-green-500/10 border-green-500/30'
                  : 'bg-red-500/10 border-red-500/30'
              )}
            >
              <div className="flex items-start gap-4">
                {testResult.allowed ? (
                  <CheckCircle2 className="w-8 h-8 text-green-400 flex-shrink-0" />
                ) : (
                  <X className="w-8 h-8 text-red-400 flex-shrink-0" />
                )}
                <div className="flex-1">
                  <h3 className={clsx(
                    'text-xl font-bold mb-2',
                    testResult.allowed ? 'text-green-400' : 'text-red-400'
                  )}>
                    {testResult.allowed ? 'РАЗРЕШЕНО' : 'ЗАПРЕЩЕНО'}
                  </h3>
                  <p className="text-white/80">{testResult.reason}</p>

                  {/* Детали сценария */}
                  <div className="mt-4 pt-4 border-t border-white/10 text-sm text-white/60">
                    <p>
                      <strong className="text-white">Сценарий:</strong>{' '}
                      {ROLES.find(r => r.id === scenario.actorRole)?.name}
                      {' '}пытается{' '}
                      {ACTIONS.find(a => a.id === scenario.action)?.name.toLowerCase()}
                      {' '}
                      {RESOURCES.find(r => r.id === scenario.resourceType)?.name.toLowerCase()}
                      {scenario.action === 'share' && ` → ${ROLES.find(r => r.id === scenario.targetUserRole)?.name}`}
                    </p>
                    {scenario.actorIsOwner && (
                      <p className="mt-1">• Актёр владеет ресурсом</p>
                    )}
                    {!scenario.actorIsOwner && scenario.resourceIsShared && (
                      <p className="mt-1">
                        • Ресурс расшарен с уровнем "{ACCESS_LEVELS.find(l => l.id === scenario.resourceAccessLevel)?.name}"
                      </p>
                    )}
                    {!scenario.actorIsOwner && !scenario.resourceIsShared && scenario.actorSameDepartment && (
                      <p className="mt-1">• Ресурс находится в том же департаменте</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Правила расшаривания */}
        <div className="glass rounded-2xl p-6">
          <div className="mb-6">
            <h2 className="text-xl font-bold text-white mb-2">Правила расшаривания</h2>
            <p className="text-white/60 text-sm">
              Кто кому может расшарить ресурсы
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-3 px-4 text-white/60 font-medium">Роль</th>
                  <th className="text-left py-3 px-4 text-white/60 font-medium">Может расшарить</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-white/5">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <Crown className="w-5 h-5 text-purple-400" />
                      <span className="font-medium text-white">Суперадмин</span>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-white/70">
                    Кому угодно (глобальный доступ)
                  </td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-5 h-5 text-cyan-400" />
                      <span className="font-medium text-white">Владелец</span>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-white/70">
                    Всем в организации
                  </td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <Shield className="w-5 h-5 text-blue-400" />
                      <span className="font-medium text-white">Админ (Лид)</span>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-white/70">
                    <ul className="list-disc list-inside space-y-1">
                      <li>Владельцу и Суперадмину</li>
                      <li>Другим админам и саб-админам (любой департамент)</li>
                      <li>Сотрудникам своего департамента</li>
                    </ul>
                  </td>
                </tr>
                <tr className="border-b border-white/5">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <Shield className="w-5 h-5 text-indigo-400" />
                      <span className="font-medium text-white">Саб-Админ</span>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-white/70">
                    <ul className="list-disc list-inside space-y-1">
                      <li>Владельцу и Суперадмину</li>
                      <li>Другим админам и саб-админам (любой департамент)</li>
                      <li>Сотрудникам своего департамента</li>
                    </ul>
                  </td>
                </tr>
                <tr>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <User className="w-5 h-5 text-green-400" />
                      <span className="font-medium text-white">Сотрудник</span>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-white/70">
                    Только в своём департаменте
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Тестовое окружение (Sandbox) */}
        <div className="glass rounded-2xl p-6">
          <div className="mb-6">
            <h2 className="text-xl font-bold text-white mb-2 flex items-center gap-2">
              <Database className="w-6 h-6 text-cyan-400" />
              Тестовое окружение (Sandbox)
            </h2>
            <p className="text-white/60 text-sm">
              Создайте изолированную среду для тестирования ролей и прав доступа
            </p>
          </div>

          {/* Error message */}
          {sandboxError && (
            <div className="mb-4 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-red-400 text-sm">{sandboxError}</p>
              </div>
              <button
                onClick={() => setSandboxError(null)}
                className="text-red-400 hover:text-red-300"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Status indicator */}
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={clsx(
                'w-3 h-3 rounded-full',
                sandboxStatus.exists ? 'bg-green-400' : 'bg-white/20'
              )}></div>
              <span className="text-white font-medium">
                {sandboxStatus.exists ? 'Sandbox активен' : 'Sandbox не создан'}
              </span>
            </div>

            {sandboxStatus.exists ? (
              <button
                onClick={deleteSandbox}
                disabled={sandboxLoading}
                className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 rounded-lg text-red-400 font-medium transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Trash2 className="w-4 h-4" />
                Удалить Sandbox
              </button>
            ) : (
              <button
                onClick={createSandbox}
                disabled={sandboxLoading}
                className="px-4 py-2 bg-green-500/20 hover:bg-green-500/30 border border-green-500/30 rounded-lg text-green-400 font-medium transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus className="w-4 h-4" />
                Создать Sandbox
              </button>
            )}
          </div>

          {/* Sandbox details */}
          {sandboxStatus.exists && sandboxStatus.users && (
            <div className="space-y-6">
              {/* Department info */}
              <div className="p-4 glass-light rounded-xl">
                <div className="flex items-center gap-2 text-cyan-400 mb-1">
                  <Building2 className="w-5 h-5" />
                  <span className="font-semibold">Департамент</span>
                </div>
                <p className="text-white">
                  {sandboxStatus.department_name || 'Sandbox Test Department'} <span className="text-white/40">(ID: {sandboxStatus.department_id ?? 'N/A'})</span>
                </p>
              </div>

              {/* Users table */}
              <div>
                <h3 className="text-white font-semibold mb-3">Тестовые пользователи</h3>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left py-3 px-4 text-white/60 font-medium">Email</th>
                        <th className="text-left py-3 px-4 text-white/60 font-medium">Роль</th>
                        <th className="text-right py-3 px-4 text-white/60 font-medium">Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sandboxStatus.users?.map((user) => (
                        <tr key={user.email} className="border-b border-white/5 hover:bg-dark-800/50">
                          <td className="py-3 px-4">
                            <span className="text-white font-mono text-sm">{user.email}</span>
                          </td>
                          <td className="py-3 px-4">
                            <span className={clsx(
                              'px-2 py-1 rounded text-sm font-medium',
                              user.role === 'owner' && 'bg-cyan-500/20 text-cyan-400',
                              user.role === 'admin' && 'bg-blue-500/20 text-blue-400',
                              user.role === 'sub_admin' && 'bg-purple-500/20 text-purple-400',
                              user.role === 'member' && 'bg-green-500/20 text-green-400'
                            )}>
                              {user.role_label}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={() => switchToUser(user.email)}
                              disabled={sandboxLoading}
                              className="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 font-medium transition-colors flex items-center gap-2 ml-auto disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              <LogIn className="w-4 h-4" />
                              Войти как
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Stats */}
              {sandboxStatus.stats && (
                <div className="p-4 glass-light rounded-xl">
                  <div className="flex items-center gap-2 text-white/60 mb-2">
                    <CheckCircle2 className="w-5 h-5" />
                    <span className="font-semibold">Статистика</span>
                  </div>
                  <div className="flex items-center gap-6 text-sm">
                    <div className="flex items-center gap-2">
                      <UserCheck className="w-4 h-4 text-green-400" />
                      <span className="text-white">{sandboxStatus.stats.contacts} контактов</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <MessageSquare className="w-4 h-4 text-blue-400" />
                      <span className="text-white">{sandboxStatus.stats.chats} чата</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Phone className="w-4 h-4 text-purple-400" />
                      <span className="text-white">{sandboxStatus.stats.calls} звонка</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Quick scenario buttons */}
              <div>
                <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
                  <Play className="w-5 h-5 text-orange-400" />
                  Быстрые сценарии
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <button
                    onClick={() => switchToUser('sandbox_owner@test.local')}
                    disabled={sandboxLoading}
                    className="p-4 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 rounded-xl text-left transition-colors disabled:opacity-50 disabled:cursor-not-allowed group"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-cyan-400">Тест: Owner видит всё</span>
                      <ArrowRightLeft className="w-4 h-4 text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <p className="text-sm text-white/60">
                      Проверить доступ владельца ко всем ресурсам организации
                    </p>
                  </button>

                  <button
                    onClick={() => switchToUser('sandbox_admin@test.local')}
                    disabled={sandboxLoading}
                    className="p-4 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 rounded-xl text-left transition-colors disabled:opacity-50 disabled:cursor-not-allowed group"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-blue-400">Тест: Admin видит только свой отдел</span>
                      <ArrowRightLeft className="w-4 h-4 text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <p className="text-sm text-white/60">
                      Проверить ограничения админа по департаменту
                    </p>
                  </button>

                  <button
                    onClick={() => switchToUser('sandbox_member@test.local')}
                    disabled={sandboxLoading}
                    className="p-4 bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 rounded-xl text-left transition-colors disabled:opacity-50 disabled:cursor-not-allowed group"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-green-400">Тест: Member видит только своё</span>
                      <ArrowRightLeft className="w-4 h-4 text-green-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <p className="text-sm text-white/60">
                      Проверить базовый доступ сотрудника
                    </p>
                  </button>
                </div>
              </div>

              {/* Info block */}
              <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl">
                <h3 className="text-sm font-semibold text-blue-400 mb-2">Как использовать:</h3>
                <ul className="text-sm text-white/70 space-y-1">
                  <li>• Нажмите "Войти как" чтобы переключиться на тестового пользователя</li>
                  <li>• Используйте быстрые сценарии для проверки типичных кейсов</li>
                  <li>• Sandbox изолирован и не влияет на основные данные</li>
                  <li>• После тестирования удалите sandbox для очистки</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
