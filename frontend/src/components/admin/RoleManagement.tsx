import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import * as Dialog from '@radix-ui/react-dialog';
import {
  Shield,
  Plus,
  Trash2,
  Edit3,
  Check,
  X,
  AlertCircle,
  Users,
  History,
  ChevronDown,
  ChevronRight,
  Save,
  Crown,
  User,
  UserCog,
  Grid3X3
} from 'lucide-react';
import {
  getCustomRoles,
  createCustomRole,
  updateCustomRole,
  deleteCustomRole,
  setRolePermission,
  removeRolePermission,
  getUsers,
  assignCustomRole,
  unassignCustomRole,
  getPermissionAuditLogs,
  getOrgMembers,
  updateMemberRole,
  getMyOrgRole,
  type CustomRole,
  type OrgRole
} from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import toast from 'react-hot-toast';
import clsx from 'clsx';

// Available permissions that can be configured
const AVAILABLE_PERMISSIONS = [
  { id: 'can_view_all_users', label: 'Просмотр всех пользователей', category: 'Пользователи' },
  { id: 'can_delete_users', label: 'Удаление пользователей', category: 'Пользователи' },
  { id: 'can_change_roles', label: 'Изменение ролей пользователей', category: 'Пользователи' },
  { id: 'can_invite_users', label: 'Приглашение пользователей', category: 'Организация' },
  { id: 'can_manage_org_settings', label: 'Управление настройками организации', category: 'Организация' },
  { id: 'can_create_departments', label: 'Создание департаментов', category: 'Департаменты' },
  { id: 'can_manage_dept_members', label: 'Управление участниками департамента', category: 'Департаменты' },
  { id: 'can_create_resources', label: 'Создание ресурсов', category: 'Ресурсы' },
  { id: 'can_share_resources', label: 'Расшаривание ресурсов', category: 'Ресурсы' },
  { id: 'can_transfer_resources', label: 'Передача ресурсов', category: 'Ресурсы' },
  { id: 'can_delete_resources', label: 'Удаление ресурсов', category: 'Ресурсы' },
  { id: 'can_view_audit_logs', label: 'Просмотр журнала аудита', category: 'Админ' },
  { id: 'can_impersonate', label: 'Вход под другим пользователем', category: 'Админ' },
];

const BASE_ROLES = [
  { value: 'owner', label: 'Владелец', color: 'text-amber-400' },
  { value: 'admin', label: 'Администратор', color: 'text-blue-400' },
  { value: 'sub_admin', label: 'Саб-админ', color: 'text-cyan-400' },
  { value: 'member', label: 'Участник', color: 'text-green-400' },
];

interface RoleCardProps {
  role: CustomRole;
  onEdit: (role: CustomRole) => void;
  onDelete: (role: CustomRole) => void;
  onManagePermissions: (role: CustomRole) => void;
  onManageUsers: (role: CustomRole) => void;
}

function RoleCard({ role, onEdit, onDelete, onManagePermissions, onManageUsers }: RoleCardProps) {
  const baseRoleConfig = BASE_ROLES.find(r => r.value === role.base_role);
  const permissionCount = role.permission_overrides?.length || 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'glass rounded-xl p-4 border transition-all',
        role.is_active ? 'border-white/10' : 'border-red-500/30 opacity-60'
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-accent-500/20 rounded-lg">
            <Shield className="w-5 h-5 text-accent-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">{role.name}</h3>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={clsx('text-xs', baseRoleConfig?.color)}>
                Основа: {baseRoleConfig?.label}
              </span>
              {!role.is_active && (
                <span className="px-1.5 py-0.5 text-xs bg-red-500/20 text-red-400 rounded">
                  Неактивна
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onManageUsers(role)}
            className="p-2 rounded-lg text-dark-400 hover:text-blue-400 hover:bg-blue-500/10 transition-colors"
            title="Пользователи"
          >
            <Users className="w-4 h-4" />
          </button>
          <button
            onClick={() => onEdit(role)}
            className="p-2 rounded-lg text-dark-400 hover:text-accent-400 hover:bg-accent-500/10 transition-colors"
            title="Редактировать"
          >
            <Edit3 className="w-4 h-4" />
          </button>
          <button
            onClick={() => onDelete(role)}
            className="p-2 rounded-lg text-dark-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            title="Удалить"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {role.description && (
        <p className="text-sm text-dark-400 mb-3">{role.description}</p>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-dark-500">
          {permissionCount} {permissionCount === 1 ? 'переопределение' : 'переопределений'}
        </span>
        <button
          onClick={() => onManagePermissions(role)}
          className="text-xs text-accent-400 hover:text-accent-300 transition-colors"
        >
          Настроить права
        </button>
      </div>
    </motion.div>
  );
}

interface PermissionEditorProps {
  role: CustomRole;
  onClose: () => void;
}

function PermissionEditor({ role, onClose }: PermissionEditorProps) {
  const queryClient = useQueryClient();
  const [expandedCategories, setExpandedCategories] = useState<string[]>(['Users', 'Organization', 'Resources']);

  const permissionMap = new Map(
    role.permission_overrides?.map(p => [p.permission, p.allowed]) || []
  );

  const setPermissionMutation = useMutation({
    mutationFn: ({ permission, allowed }: { permission: string; allowed: boolean }) =>
      setRolePermission(role.id, permission, allowed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles'] });
      toast.success('Право обновлено');
    },
    onError: () => {
      toast.error('Не удалось обновить право');
    },
  });

  const removePermissionMutation = useMutation({
    mutationFn: (permission: string) => removeRolePermission(role.id, permission),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles'] });
      toast.success('Право сброшено к значению по умолчанию');
    },
    onError: () => {
      toast.error('Не удалось сбросить право');
    },
  });

  const toggleCategory = (category: string) => {
    setExpandedCategories(prev =>
      prev.includes(category)
        ? prev.filter(c => c !== category)
        : [...prev, category]
    );
  };

  const categories = [...new Set(AVAILABLE_PERMISSIONS.map(p => p.category))];

  return (
    <Dialog.Root open onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl max-h-[85vh] glass rounded-2xl p-6 shadow-xl overflow-hidden flex flex-col z-50">
          <Dialog.Title className="text-xl font-semibold mb-4 flex items-center gap-3">
            <Shield className="w-6 h-6 text-accent-400" />
            Права доступа: {role.name}
          </Dialog.Title>

          <div className="flex-1 overflow-y-auto space-y-4">
            {categories.map(category => (
              <div key={category} className="glass-light rounded-xl overflow-hidden">
                <button
                  onClick={() => toggleCategory(category)}
                  className="w-full flex items-center justify-between p-4 hover:bg-dark-800/50 transition-colors"
                >
                  <span className="font-medium">{category}</span>
                  {expandedCategories.includes(category) ? (
                    <ChevronDown className="w-4 h-4 text-dark-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-dark-400" />
                  )}
                </button>

                <AnimatePresence>
                  {expandedCategories.includes(category) && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t border-white/5"
                    >
                      {AVAILABLE_PERMISSIONS.filter(p => p.category === category).map(perm => {
                        const currentValue = permissionMap.get(perm.id);
                        const hasOverride = currentValue !== undefined;

                        return (
                          <div
                            key={perm.id}
                            className="flex items-center justify-between px-4 py-3 hover:bg-dark-800/50 transition-colors"
                          >
                            <div>
                              <span className="text-sm font-medium">{perm.label}</span>
                              {hasOverride && (
                                <span className={clsx(
                                  'ml-2 text-xs px-1.5 py-0.5 rounded',
                                  currentValue ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                                )}>
                                  {currentValue ? 'Разрешено' : 'Запрещено'}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => setPermissionMutation.mutate({ permission: perm.id, allowed: true })}
                                className={clsx(
                                  'p-1.5 rounded-lg transition-colors',
                                  currentValue === true
                                    ? 'bg-green-500/20 text-green-400'
                                    : 'text-dark-500 hover:text-green-400 hover:bg-green-500/10'
                                )}
                                title="Разрешить"
                              >
                                <Check className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => setPermissionMutation.mutate({ permission: perm.id, allowed: false })}
                                className={clsx(
                                  'p-1.5 rounded-lg transition-colors',
                                  currentValue === false
                                    ? 'bg-red-500/20 text-red-400'
                                    : 'text-dark-500 hover:text-red-400 hover:bg-red-500/10'
                                )}
                                title="Запретить"
                              >
                                <X className="w-4 h-4" />
                              </button>
                              {hasOverride && (
                                <button
                                  onClick={() => removePermissionMutation.mutate(perm.id)}
                                  className="p-1.5 rounded-lg text-dark-500 hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
                                  title="Сбросить"
                                >
                                  <AlertCircle className="w-4 h-4" />
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>

          <div className="flex justify-end pt-4 mt-4 border-t border-white/5">
            <Dialog.Close asChild>
              <button className="px-4 py-2 rounded-xl glass-light hover:bg-white/10 transition-colors">
                Закрыть
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

interface UserAssignmentDialogProps {
  role: CustomRole;
  onClose: () => void;
}

function UserAssignmentDialog({ role, onClose }: UserAssignmentDialogProps) {
  const queryClient = useQueryClient();
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: getUsers,
  });

  const assignMutation = useMutation({
    mutationFn: (userId: number) => assignCustomRole(role.id, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles'] });
      toast.success('Пользователь назначен на роль');
      setSelectedUserId(null);
    },
    onError: () => {
      toast.error('Не удалось назначить пользователя');
    },
  });


  return (
    <Dialog.Root open onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-lg max-h-[85vh] glass rounded-2xl p-6 shadow-xl overflow-hidden flex flex-col z-50">
          <Dialog.Title className="text-xl font-semibold mb-4 flex items-center gap-3">
            <Users className="w-6 h-6 text-blue-400" />
            Пользователи с ролью: {role.name}
          </Dialog.Title>

          <div className="flex-1 overflow-y-auto space-y-4">
            {/* Add user */}
            <div className="flex gap-2">
              <select
                value={selectedUserId || ''}
                onChange={(e) => setSelectedUserId(e.target.value ? Number(e.target.value) : null)}
                className="flex-1 glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
              >
                <option value="">Выберите пользователя...</option>
                {users.map(user => (
                  <option key={user.id} value={user.id}>
                    {user.name || user.email}
                  </option>
                ))}
              </select>
              <button
                onClick={() => selectedUserId && assignMutation.mutate(selectedUserId)}
                disabled={!selectedUserId || assignMutation.isPending}
                className="px-4 py-2 rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 transition-colors"
              >
                <Plus className="w-5 h-5" />
              </button>
            </div>

            {/* Current users placeholder - would need to extend API */}
            <div className="glass-light rounded-xl p-4 text-center text-dark-400">
              <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Пользователи с этой ролью появятся здесь</p>
            </div>
          </div>

          <div className="flex justify-end pt-4 mt-4 border-t border-white/5">
            <Dialog.Close asChild>
              <button className="px-4 py-2 rounded-xl glass-light hover:bg-white/10 transition-colors">
                Закрыть
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// Org role configuration
const ORG_ROLE_CONFIG: Record<OrgRole, { label: string; icon: typeof Crown; color: string }> = {
  owner: { label: 'Владелец', icon: Crown, color: 'text-yellow-400 bg-yellow-500/20' },
  admin: { label: 'HR Админ', icon: Shield, color: 'text-cyan-400 bg-cyan-500/20' },
  hr: { label: 'HR Рекрутер', icon: User, color: 'text-purple-400 bg-purple-500/20' },
  member: { label: 'Сотрудник', icon: User, color: 'text-white/60 bg-white/10' },
};

export default function RoleManagement() {
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<CustomRole | null>(null);
  const [permissionRole, setPermissionRole] = useState<CustomRole | null>(null);
  const [userAssignRole, setUserAssignRole] = useState<CustomRole | null>(null);
  const [showAuditLog, setShowAuditLog] = useState(false);
  const [activeTab, setActiveTab] = useState<'roles' | 'users' | 'matrix'>('users');

  const [newRole, setNewRole] = useState({
    name: '',
    description: '',
    base_role: 'member',
  });

  // Get user's organization role
  const { data: myOrgRole, isLoading: orgRoleLoading } = useQuery({
    queryKey: ['my-org-role'],
    queryFn: getMyOrgRole,
  });

  // Check if user has admin access (superadmin system role OR org owner/admin)
  const hasAdminAccess = user?.role === 'superadmin' ||
    myOrgRole?.role === 'owner' ||
    myOrgRole?.role === 'admin';

  const { data: roles = [], isLoading } = useQuery({
    queryKey: ['custom-roles'],
    queryFn: getCustomRoles,
  });

  const { data: orgMembers = [], isLoading: membersLoading } = useQuery({
    queryKey: ['org-members'],
    queryFn: getOrgMembers,
  });

  const { data: auditLogs = [] } = useQuery({
    queryKey: ['permission-audit-logs'],
    queryFn: () => getPermissionAuditLogs({ limit: 50 }),
    enabled: showAuditLog,
  });

  // Mutation for changing org role
  const changeOrgRoleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: OrgRole }) =>
      updateMemberRole(userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-members'] });
      toast.success('Роль изменена');
    },
    onError: () => {
      toast.error('Не удалось изменить роль');
    },
  });

  // Mutation for assigning custom role
  const assignRoleMutation = useMutation({
    mutationFn: ({ roleId, userId }: { roleId: number; userId: number }) =>
      assignCustomRole(roleId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-members'] });
      toast.success('Кастомная роль назначена');
    },
    onError: () => {
      toast.error('Не удалось назначить роль');
    },
  });

  // Mutation for removing custom role
  const unassignRoleMutation = useMutation({
    mutationFn: ({ roleId, userId }: { roleId: number; userId: number }) =>
      unassignCustomRole(roleId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-members'] });
      toast.success('Кастомная роль снята');
    },
    onError: () => {
      toast.error('Не удалось снять роль');
    },
  });

  // Create personal role for a user and assign it
  const createPersonalRoleMutation = useMutation({
    mutationFn: async ({ userName, baseRole, userId }: { userName: string; baseRole: string; userId: number }) => {
      const role = await createCustomRole({
        name: `Роль: ${userName}`,
        description: `Персональная роль для ${userName}`,
        base_role: baseRole,
      });
      await assignCustomRole(role.id, userId);
      return role;
    },
    onSuccess: (role) => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles'] });
      queryClient.invalidateQueries({ queryKey: ['org-members'] });
      toast.success('Персональная роль создана');
      // Open permission editor for the new role
      setPermissionRole(role);
    },
    onError: () => {
      toast.error('Не удалось создать роль');
    },
  });

  // Toggle permission directly in matrix
  const togglePermissionMutation = useMutation({
    mutationFn: async ({ roleId, permission, currentValue, baseValue }: {
      roleId: number;
      permission: string;
      currentValue: boolean;
      baseValue: boolean;
    }) => {
      // If current value equals base value and we're changing it, set the override
      // If current value differs from base and we're changing back to base, remove the override
      const newValue = !currentValue;
      if (newValue === baseValue) {
        // Remove override - go back to base role default
        await removeRolePermission(roleId, permission);
      } else {
        // Set override
        await setRolePermission(roleId, permission, newValue);
      }
      return { roleId, permission, newValue };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles'] });
    },
    onError: () => {
      toast.error('Не удалось изменить право');
    },
  });

  const createMutation = useMutation({
    mutationFn: () => createCustomRole(newRole),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles'] });
      setIsCreateDialogOpen(false);
      setNewRole({ name: '', description: '', base_role: 'member' });
      toast.success('Роль создана');
    },
    onError: () => {
      toast.error('Не удалось создать роль');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, updates }: { id: number; updates: Parameters<typeof updateCustomRole>[1] }) =>
      updateCustomRole(id, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles'] });
      setEditingRole(null);
      toast.success('Роль обновлена');
    },
    onError: () => {
      toast.error('Не удалось обновить роль');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCustomRole,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-roles'] });
      toast.success('Роль удалена');
    },
    onError: () => {
      toast.error('Не удалось удалить роль');
    },
  });

  const handleDelete = (role: CustomRole) => {
    if (confirm(`Удалить роль "${role.name}"? Это действие нельзя отменить.`)) {
      deleteMutation.mutate(role.id);
    }
  };

  // Loading state
  if (orgRoleLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Check access - allow superadmin, org owner, or org admin
  if (!hasAdminAccess) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <Shield className="w-12 h-12 mx-auto text-dark-500 mb-3" />
          <p className="text-dark-400">Требуется доступ администратора или владельца организации</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <UserCog className="w-6 h-6 text-accent-400" />
            Управление ролями и пользователями
          </h2>
          <p className="text-sm text-dark-400 mt-1">
            Настройка ролей пользователей и создание кастомных ролей
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAuditLog(!showAuditLog)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-xl transition-colors',
              showAuditLog ? 'bg-accent-500/20 text-accent-400' : 'glass-light hover:bg-white/10'
            )}
          >
            <History className="w-5 h-5" />
            Журнал
          </button>
          {activeTab === 'roles' && (
            <button
              onClick={() => setIsCreateDialogOpen(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent-500 text-white hover:bg-accent-600 transition-colors"
            >
              <Plus className="w-5 h-5" />
              Новая роль
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/10 pb-2">
        <button
          onClick={() => setActiveTab('users')}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded-t-lg transition-colors',
            activeTab === 'users'
              ? 'bg-accent-500/20 text-accent-400 border-b-2 border-accent-400'
              : 'text-dark-400 hover:text-white hover:bg-dark-800/50'
          )}
        >
          <Users className="w-5 h-5" />
          Пользователи ({orgMembers.length})
        </button>
        <button
          onClick={() => setActiveTab('roles')}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded-t-lg transition-colors',
            activeTab === 'roles'
              ? 'bg-accent-500/20 text-accent-400 border-b-2 border-accent-400'
              : 'text-dark-400 hover:text-white hover:bg-dark-800/50'
          )}
        >
          <Shield className="w-5 h-5" />
          Кастомные роли ({roles.length})
        </button>
        <button
          onClick={() => setActiveTab('matrix')}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded-t-lg transition-colors',
            activeTab === 'matrix'
              ? 'bg-accent-500/20 text-accent-400 border-b-2 border-accent-400'
              : 'text-dark-400 hover:text-white hover:bg-dark-800/50'
          )}
        >
          <Grid3X3 className="w-5 h-5" />
          Матрица прав
        </button>
      </div>

      {/* Users Tab */}
      {activeTab === 'users' && (
        <div className="space-y-4">
          {membersLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : orgMembers.length === 0 ? (
            <div className="glass rounded-xl p-8 text-center">
              <Users className="w-12 h-12 mx-auto text-dark-500 mb-3" />
              <p className="text-dark-400">Нет пользователей</p>
            </div>
          ) : (
            <div className="space-y-3">
              {orgMembers.map((member) => {
                const roleConfig = ORG_ROLE_CONFIG[member.role];
                const RoleIcon = roleConfig?.icon || User;
                const isCurrentUser = member.user_id === user?.id;

                return (
                  <motion.div
                    key={member.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={clsx(
                      'glass rounded-xl p-4 border transition-colors',
                      isCurrentUser ? 'border-accent-500/30' : 'border-white/5'
                    )}
                  >
                    <div className="flex items-center justify-between flex-wrap gap-4">
                      {/* User info */}
                      <div className="flex items-center gap-4 min-w-0">
                        <div className={clsx('p-2 rounded-lg', roleConfig?.color || 'bg-white/10')}>
                          <RoleIcon className="w-5 h-5" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium text-white truncate">{member.user_name}</h3>
                            {isCurrentUser && (
                              <span className="text-xs px-2 py-0.5 bg-accent-500/20 text-accent-400 rounded-full">
                                Это вы
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-dark-400 truncate">{member.user_email}</p>
                        </div>
                      </div>

                      {/* Role controls */}
                      <div className="flex items-center gap-3 flex-wrap">
                        {/* Base org role */}
                        <div className="flex flex-col gap-1">
                          <span className="text-xs text-dark-500">Базовая роль</span>
                          {!isCurrentUser && member.role !== 'owner' ? (
                            <select
                              value={member.role}
                              onChange={(e) => changeOrgRoleMutation.mutate({
                                userId: member.user_id,
                                role: e.target.value as OrgRole
                              })}
                              disabled={changeOrgRoleMutation.isPending}
                              className="px-3 py-1.5 glass-light rounded-lg text-white text-sm min-w-[140px]"
                            >
                              <option value="admin">Администратор</option>
                              <option value="member">Участник</option>
                            </select>
                          ) : (
                            <span className={clsx(
                              'px-3 py-1.5 rounded-lg text-sm',
                              roleConfig?.color || 'bg-white/10'
                            )}>
                              {roleConfig?.label || member.role}
                            </span>
                          )}
                        </div>

                        {/* Custom role */}
                        <div className="flex flex-col gap-1">
                          <span className="text-xs text-dark-500">Кастомная роль</span>
                          {!isCurrentUser ? (
                            <div className="flex items-center gap-2">
                              <select
                                value={member.custom_role_id || ''}
                                onChange={(e) => {
                                  const newRoleId = e.target.value ? Number(e.target.value) : null;
                                  if (newRoleId && !member.custom_role_id) {
                                    // Assign new role
                                    assignRoleMutation.mutate({ roleId: newRoleId, userId: member.user_id });
                                  } else if (newRoleId && member.custom_role_id) {
                                    // Change role: unassign old, assign new
                                    unassignRoleMutation.mutate(
                                      { roleId: member.custom_role_id, userId: member.user_id },
                                      { onSuccess: () => assignRoleMutation.mutate({ roleId: newRoleId, userId: member.user_id }) }
                                    );
                                  } else if (!newRoleId && member.custom_role_id) {
                                    // Remove role
                                    unassignRoleMutation.mutate({ roleId: member.custom_role_id, userId: member.user_id });
                                  }
                                }}
                                disabled={assignRoleMutation.isPending || unassignRoleMutation.isPending}
                                className="px-3 py-1.5 glass-light rounded-lg text-white text-sm min-w-[140px]"
                              >
                                <option value="">— Нет —</option>
                                {roles.filter(r => r.is_active).map(role => (
                                  <option key={role.id} value={role.id}>
                                    {role.name}
                                  </option>
                                ))}
                              </select>
                              {/* Quick create personal role button */}
                              {!member.custom_role_id && (
                                <button
                                  onClick={() => createPersonalRoleMutation.mutate({
                                    userName: member.user_name,
                                    baseRole: member.role,
                                    userId: member.user_id
                                  })}
                                  disabled={createPersonalRoleMutation.isPending}
                                  title="Создать персональную роль"
                                  className="p-1.5 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors disabled:opacity-50"
                                >
                                  <Plus className="w-4 h-4" />
                                </button>
                              )}
                            </div>
                          ) : (
                            <span className={clsx(
                              'px-3 py-1.5 rounded-lg text-sm',
                              member.custom_role_name ? 'bg-purple-500/20 text-purple-400' : 'glass-light text-dark-500'
                            )}>
                              {member.custom_role_name || '— Нет —'}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Custom role info and edit button */}
                    {member.custom_role_id && member.custom_role_name && (
                      <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
                        <span className="text-xs text-dark-400">
                          Кастомная роль <span className="text-purple-400">{member.custom_role_name}</span> переопределяет права базовой роли
                        </span>
                        <button
                          onClick={() => {
                            const role = roles.find(r => r.id === member.custom_role_id);
                            if (role) setPermissionRole(role);
                          }}
                          className="text-xs px-3 py-1 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors flex items-center gap-1"
                        >
                          <Edit3 className="w-3 h-3" />
                          Настроить права
                        </button>
                      </div>
                    )}
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Hint about custom roles */}
          {roles.length === 0 && (
            <div className="glass rounded-xl p-4 border border-amber-500/20 bg-amber-500/5">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm text-amber-400 font-medium">Кастомных ролей пока нет</p>
                  <p className="text-xs text-dark-400 mt-1">
                    Перейдите на вкладку "Кастомные роли" чтобы создать роль с тонкой настройкой прав доступа
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Roles Tab - Roles Grid */}
      {activeTab === 'roles' && (
        <>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : roles.length === 0 ? (
            <div className="glass rounded-xl p-8 text-center">
              <Shield className="w-12 h-12 mx-auto text-dark-500 mb-3" />
              <p className="text-dark-400">Кастомных ролей пока нет</p>
              <p className="text-sm text-dark-500 mt-1">
                Создайте первую кастомную роль для начала работы
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {roles.map(role => (
                <RoleCard
                  key={role.id}
                  role={role}
                  onEdit={setEditingRole}
                  onDelete={handleDelete}
                  onManagePermissions={setPermissionRole}
                  onManageUsers={setUserAssignRole}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Matrix Tab - Permission Matrix */}
      {activeTab === 'matrix' && (
        <div className="space-y-4">
          {/* Info about base roles */}
          <div className="glass rounded-xl p-4 border border-amber-500/20 bg-amber-500/5">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-amber-400 font-medium">Базовые роли (Владелец, Админ, Участник) имеют фиксированные права</p>
                <p className="text-xs text-dark-400 mt-1">
                  Чтобы изменить права пользователя - назначьте ему кастомную роль на вкладке "Пользователи".
                  Кастомные роли можно редактировать прямо в матрице (клик на ячейку).
                </p>
              </div>
            </div>
          </div>

          <div className="glass rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[800px]">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left p-4 text-sm font-medium text-dark-400 sticky left-0 bg-dark-900/95 backdrop-blur z-10">
                      Право доступа
                    </th>
                    {/* Base roles */}
                    <th className="p-4 text-center min-w-[100px]">
                      <div className="flex flex-col items-center gap-1">
                        <Crown className="w-4 h-4 text-yellow-400" />
                        <span className="text-xs text-yellow-400">Владелец</span>
                      </div>
                    </th>
                    <th className="p-4 text-center min-w-[100px]">
                      <div className="flex flex-col items-center gap-1">
                        <Shield className="w-4 h-4 text-cyan-400" />
                        <span className="text-xs text-cyan-400">Админ</span>
                      </div>
                    </th>
                    <th className="p-4 text-center min-w-[100px]">
                      <div className="flex flex-col items-center gap-1">
                        <User className="w-4 h-4 text-white/60" />
                        <span className="text-xs text-white/60">Участник</span>
                      </div>
                    </th>
                    {/* Custom roles */}
                    {roles.filter(r => r.is_active).map(role => (
                      <th key={role.id} className="p-4 text-center min-w-[100px]">
                        <div className="flex flex-col items-center gap-1">
                          <Shield className="w-4 h-4 text-purple-400" />
                          <span className="text-xs text-purple-400 truncate max-w-[80px]" title={role.name}>
                            {role.name}
                          </span>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {AVAILABLE_PERMISSIONS.map((perm, idx) => {
                    // Get permission values for each role
                    // Владелец - всё
                    const ownerHas = true;
                    // Админ - управление своим департаментом, НЕ может создавать новые департаменты
                    // Видит: свой депт + других админов. НЕ видит: участников чужих департаментов
                    const adminHas = [
                      // 'can_view_all_users' - НЕТ, видит только свой депт + других админов (логика на бэкенде)
                      'can_invite_users',        // приглашает в свой департамент
                      'can_manage_dept_members', // управляет участниками своего департамента
                      'can_create_resources',    // создаёт ресурсы
                      'can_share_resources',     // расшаривает
                      'can_transfer_resources',  // передаёт
                      'can_delete_resources'     // удаляет
                    ].includes(perm.id);
                    // Участник - работа со своими ресурсами, расшаривание/передача внутри департамента
                    const memberHas = [
                      'can_create_resources',    // создаёт свои ресурсы
                      'can_share_resources',     // расшаривает внутри департамента
                      'can_transfer_resources'   // передаёт внутри департамента
                    ].includes(perm.id);

                    return (
                      <tr key={perm.id} className={idx % 2 === 0 ? 'bg-white/[0.02]' : ''}>
                        <td className="p-4 sticky left-0 bg-dark-900/95 backdrop-blur z-10">
                          <div>
                            <span className="text-sm text-white">{perm.label}</span>
                            <span className="text-xs text-dark-500 ml-2">({perm.category})</span>
                          </div>
                        </td>
                        {/* Owner */}
                        <td className="p-4 text-center">
                          <div
                            className={clsx(
                              'inline-flex items-center justify-center w-6 h-6 rounded cursor-not-allowed opacity-70',
                              ownerHas ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                            )}
                            title="Базовая роль - нельзя изменить. Создайте кастомную роль."
                          >
                            {ownerHas ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                          </div>
                        </td>
                        {/* Admin */}
                        <td className="p-4 text-center">
                          <div
                            className={clsx(
                              'inline-flex items-center justify-center w-6 h-6 rounded cursor-not-allowed opacity-70',
                              adminHas ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                            )}
                            title="Базовая роль - нельзя изменить. Создайте кастомную роль."
                          >
                            {adminHas ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                          </div>
                        </td>
                        {/* Member */}
                        <td className="p-4 text-center">
                          <div
                            className={clsx(
                              'inline-flex items-center justify-center w-6 h-6 rounded cursor-not-allowed opacity-70',
                              memberHas ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                            )}
                            title="Базовая роль - нельзя изменить. Создайте кастомную роль."
                          >
                            {memberHas ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                          </div>
                        </td>
                        {/* Custom roles */}
                        {roles.filter(r => r.is_active).map(role => {
                          const override = role.permission_overrides?.find(o => o.permission === perm.id);
                          // Calculate base value from the role's base_role
                          const baseValue = role.base_role === 'owner' ? true :
                            role.base_role === 'admin' ? adminHas :
                            memberHas;
                          const hasPermission = override ? override.allowed : baseValue;
                          const isToggling = togglePermissionMutation.isPending &&
                            togglePermissionMutation.variables?.roleId === role.id &&
                            togglePermissionMutation.variables?.permission === perm.id;

                          return (
                            <td key={role.id} className="p-4 text-center">
                              <button
                                onClick={() => togglePermissionMutation.mutate({
                                  roleId: role.id,
                                  permission: perm.id,
                                  currentValue: hasPermission,
                                  baseValue
                                })}
                                disabled={isToggling}
                                className={clsx(
                                  'inline-flex items-center justify-center w-6 h-6 rounded cursor-pointer hover:ring-2 hover:ring-purple-400/50 transition-all',
                                  hasPermission ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400',
                                  override && 'ring-1 ring-purple-400/30',
                                  isToggling && 'opacity-50 animate-pulse'
                                )}
                                title={`${hasPermission ? 'Разрешено' : 'Запрещено'}${override ? ' (переопределено)' : ' (по умолчанию)'} - клик для изменения`}
                              >
                                {hasPermission ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-6 text-xs text-dark-400">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-green-500/20 flex items-center justify-center">
                <Check className="w-3 h-3 text-green-400" />
              </div>
              <span>Разрешено</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-red-500/20 flex items-center justify-center">
                <X className="w-3 h-3 text-red-400" />
              </div>
              <span>Запрещено</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-green-500/20 ring-1 ring-purple-400/30 flex items-center justify-center">
                <Check className="w-3 h-3 text-green-400" />
              </div>
              <span>Переопределено</span>
            </div>
          </div>

          {roles.length === 0 && (
            <div className="glass rounded-xl p-4 border border-amber-500/20 bg-amber-500/5">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm text-amber-400 font-medium">Создайте кастомную роль</p>
                  <p className="text-xs text-dark-400 mt-1">
                    Базовые роли (Владелец, Админ, Участник) имеют фиксированные права.
                    Создайте кастомную роль чтобы настроить права под ваши нужды.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Audit Log Panel */}
      <AnimatePresence>
        {showAuditLog && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="glass rounded-xl overflow-hidden"
          >
            <div className="p-4 border-b border-white/5">
              <h3 className="font-semibold flex items-center gap-2">
                <History className="w-5 h-5 text-amber-400" />
                Журнал изменений прав
              </h3>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {auditLogs.length === 0 ? (
                <p className="p-4 text-center text-dark-500">Журнал пока пуст</p>
              ) : (
                <div className="divide-y divide-white/5">
                  {auditLogs.map(log => (
                    <div key={log.id} className="p-3 hover:bg-dark-800/50">
                      <div className="flex items-center justify-between text-sm">
                        <span className={clsx(
                          'px-2 py-0.5 rounded text-xs',
                          log.action === 'create' && 'bg-green-500/20 text-green-400',
                          log.action === 'update' && 'bg-blue-500/20 text-blue-400',
                          log.action === 'delete' && 'bg-red-500/20 text-red-400'
                        )}>
                          {log.action === 'create' ? 'создание' : log.action === 'update' ? 'изменение' : 'удаление'}
                        </span>
                        <span className="text-dark-500 text-xs">
                          {new Date(log.created_at).toLocaleString()}
                        </span>
                      </div>
                      {log.permission && (
                        <p className="text-sm text-dark-400 mt-1">
                          Право: {log.permission}
                          {log.old_value !== null && log.new_value !== null && (
                            <span className="ml-2">
                              {log.old_value ? 'разрешено' : 'запрещено'} &rarr; {log.new_value ? 'разрешено' : 'запрещено'}
                            </span>
                          )}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create Role Dialog */}
      <Dialog.Root open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md glass rounded-2xl p-6 shadow-xl z-50">
            <Dialog.Title className="text-xl font-semibold mb-4">
              Создать кастомную роль
            </Dialog.Title>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate();
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-sm text-dark-400 mb-1">Название</label>
                <input
                  type="text"
                  value={newRole.name}
                  onChange={(e) => setNewRole({ ...newRole, name: e.target.value })}
                  required
                  placeholder="Например: Контент-менеджер"
                  className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                />
              </div>
              <div>
                <label htmlFor="base-role-select" className="block text-sm text-dark-400 mb-1">Базовая роль</label>
                <select
                  id="base-role-select"
                  value={newRole.base_role}
                  onChange={(e) => setNewRole({ ...newRole, base_role: e.target.value })}
                  className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                >
                  {BASE_ROLES.map(role => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-dark-500 mt-1">
                  Наследует права от выбранной роли
                </p>
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">Описание</label>
                <textarea
                  value={newRole.description}
                  onChange={(e) => setNewRole({ ...newRole, description: e.target.value })}
                  rows={2}
                  placeholder="Необязательное описание..."
                  className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50 resize-none"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="flex-1 py-2.5 rounded-xl glass-light hover:bg-white/10 transition-colors"
                  >
                    Отмена
                  </button>
                </Dialog.Close>
                <button
                  type="submit"
                  disabled={createMutation.isPending || !newRole.name.trim()}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 transition-colors"
                >
                  <Save className="w-4 h-4" />
                  {createMutation.isPending ? 'Создание...' : 'Создать'}
                </button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Edit Role Dialog */}
      {editingRole && (
        <Dialog.Root open onOpenChange={() => setEditingRole(null)}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
            <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md glass rounded-2xl p-6 shadow-xl z-50">
              <Dialog.Title className="text-xl font-semibold mb-4">
                Редактировать: {editingRole.name}
              </Dialog.Title>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.target as HTMLFormElement;
                  const formData = new FormData(form);
                  updateMutation.mutate({
                    id: editingRole.id,
                    updates: {
                      name: formData.get('name') as string,
                      description: formData.get('description') as string,
                      is_active: formData.get('is_active') === 'on',
                    },
                  });
                }}
                className="space-y-4"
              >
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Название</label>
                  <input
                    type="text"
                    name="name"
                    defaultValue={editingRole.name}
                    required
                    className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                  />
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Описание</label>
                  <textarea
                    name="description"
                    defaultValue={editingRole.description}
                    rows={2}
                    className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50 resize-none"
                  />
                </div>
                <label className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    name="is_active"
                    defaultChecked={editingRole.is_active}
                    className="w-5 h-5 rounded accent-accent-500"
                  />
                  <span>Активна</span>
                </label>
                <div className="flex gap-3 pt-2">
                  <Dialog.Close asChild>
                    <button
                      type="button"
                      className="flex-1 py-2.5 rounded-xl glass-light hover:bg-white/10 transition-colors"
                    >
                      Отмена
                    </button>
                  </Dialog.Close>
                  <button
                    type="submit"
                    disabled={updateMutation.isPending}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 transition-colors"
                  >
                    <Save className="w-4 h-4" />
                    {updateMutation.isPending ? 'Сохранение...' : 'Сохранить'}
                  </button>
                </div>
              </form>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}

      {/* Permission Editor Dialog */}
      {permissionRole && (
        <PermissionEditor role={permissionRole} onClose={() => setPermissionRole(null)} />
      )}

      {/* User Assignment Dialog */}
      {userAssignRole && (
        <UserAssignmentDialog role={userAssignRole} onClose={() => setUserAssignRole(null)} />
      )}
    </div>
  );
}
