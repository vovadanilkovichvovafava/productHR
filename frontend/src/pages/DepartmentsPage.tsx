import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Building,
  Plus,
  Trash2,
  Users,
  X,
  Crown,
  UserIcon,
  Loader2,
  Edit3,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  FolderPlus
} from 'lucide-react';
import {
  getDepartments,
  getDepartmentMembers as getDepartmentMembersAPI,
  createDepartment,
  updateDepartment,
  deleteDepartment,
  getDepartmentMembers,
  addDepartmentMember,
  updateDepartmentMember,
  removeDepartmentMember,
  getOrgMembers,
  getMyOrgRole,
  type Department,
  type DepartmentMember,
  type DeptRole,
  type OrgMember
} from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import toast from 'react-hot-toast';
import { getErrorDetail } from '@/utils';
import clsx from 'clsx';
import { backdropClose } from '@/utils/backdropClose';

const DEPT_ROLE_CONFIG: Record<DeptRole, { label: string; icon: typeof Crown; color: string; description: string }> = {
  lead: { label: 'Руководитель', icon: Crown, color: 'text-yellow-400 bg-yellow-500/20', description: 'Видит все данные департамента' },
  sub_admin: { label: 'Саб-админ', icon: Users, color: 'text-indigo-400 bg-indigo-500/20', description: 'Полный доступ, кроме удаления админов' },
  member: { label: 'Участник', icon: UserIcon, color: 'text-white/60 bg-white/10', description: 'Видит свои данные и расшаренные' },
};

// Mapping of department IDs to user's role in that department
type DeptRoleMap = Map<number, DeptRole>;

const COLORS = [
  '#ef4444', '#f97316', '#eab308', '#22c55e', '#06b6d4', '#3b82f6', '#8b5cf6', '#ec4899'
];

export default function DepartmentsPage() {
  const { user: currentUser } = useAuthStore();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [orgMembers, setOrgMembers] = useState<OrgMember[]>([]);
  const [myRole, setMyRole] = useState<string | null>(null);
  const [myLeadDeptIds, setMyLeadDeptIds] = useState<number[]>([]);
  const [myDeptRoles, setMyDeptRoles] = useState<DeptRoleMap>(new Map());
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createParentId, setCreateParentId] = useState<number | undefined>(undefined);
  const [selectedDept, setSelectedDept] = useState<Department | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showMembersModal, setShowMembersModal] = useState(false);
  const [expandedDepts, setExpandedDepts] = useState<Set<number>>(new Set());

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [depts, members, roleData] = await Promise.all([
        getDepartments(-1), // Get all departments
        getOrgMembers(),
        getMyOrgRole()
      ]);
      setDepartments(depts);
      setOrgMembers(members);
      setMyRole(roleData.role);

      // Find departments where current user is a lead/sub_admin and track all roles
      if (currentUser) {
        const leadDeptIds: number[] = [];
        const deptRoles: DeptRoleMap = new Map();
        for (const dept of depts) {
          try {
            const deptMembers = await getDepartmentMembersAPI(dept.id);
            const myMembership = deptMembers.find(m => m.user_id === currentUser.id);
            if (myMembership) {
              deptRoles.set(dept.id, myMembership.role);
              if (myMembership.role === 'lead') {
                leadDeptIds.push(dept.id);
              }
            }
          } catch {
            // Ignore errors
          }
        }
        setMyLeadDeptIds(leadDeptIds);
        setMyDeptRoles(deptRoles);
      }
    } catch (e) {
      console.error('Failed to load departments:', e);
      toast.error('Не удалось загрузить департаменты');
    } finally {
      setLoading(false);
    }
  };

  // Build hierarchical structure
  const { topLevelDepts, childrenMap } = useMemo(() => {
    const childrenMap = new Map<number, Department[]>();
    const topLevelDepts: Department[] = [];

    for (const dept of departments) {
      if (dept.parent_id) {
        const children = childrenMap.get(dept.parent_id) || [];
        children.push(dept);
        childrenMap.set(dept.parent_id, children);
      } else {
        topLevelDepts.push(dept);
      }
    }

    // Sort children
    for (const children of childrenMap.values()) {
      children.sort((a, b) => a.name.localeCompare(b.name));
    }
    topLevelDepts.sort((a, b) => a.name.localeCompare(b.name));

    return { topLevelDepts, childrenMap };
  }, [departments]);

  const toggleExpand = (deptId: number) => {
    setExpandedDepts(prev => {
      const next = new Set(prev);
      if (next.has(deptId)) {
        next.delete(deptId);
      } else {
        next.add(deptId);
      }
      return next;
    });
  };

  const handleDelete = async (dept: Department) => {
    if (!confirm(`Удалить департамент "${dept.name}"? Контакты останутся, но потеряют привязку к департаменту.`)) return;

    try {
      await deleteDepartment(dept.id);
      toast.success('Департамент удалён');
      loadData();
    } catch (e) {
      toast.error('Не удалось удалить департамент');
    }
  };

  // Owner-only actions: create top-level depts, delete depts, set lead role
  const isOwner = myRole === 'owner' || currentUser?.role === 'superadmin';
  // Admin can edit their departments, but not create top-level or delete
  const canManage = myRole === 'owner' || myRole === 'admin' || currentUser?.role === 'superadmin';

  // Check if user can create sub-department for a given department
  // Owner can create anywhere, lead can create in their department
  const canCreateSubDept = (deptId: number) => {
    return isOwner || myLeadDeptIds.includes(deptId);
  };

  // Check if user can edit a specific department
  // Owner can edit all, admin can edit depts they belong to
  const canEditDept = (deptId: number) => {
    return isOwner || myLeadDeptIds.includes(deptId);
  };

  // Render a department with its children
  const renderDepartment = (dept: Department, level: number = 0) => {
    const children = childrenMap.get(dept.id) || [];
    const hasChildren = children.length > 0;
    const isExpanded = expandedDepts.has(dept.id);
    const isLead = myLeadDeptIds.includes(dept.id);

    return (
      <div key={dept.id}>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className={clsx(
            'p-4 rounded-xl transition-colors cursor-pointer hover:border-cyan-500/30',
            dept.is_active ? 'glass-light' : 'glass-light opacity-60'
          )}
          style={{ marginLeft: level * 24 }}
          onClick={() => {
            setSelectedDept(dept);
            setShowMembersModal(true);
          }}
        >
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              {/* Expand/collapse toggle */}
              {hasChildren ? (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleExpand(dept.id);
                  }}
                  className="p-1 rounded hover:bg-white/10 text-white/40"
                >
                  {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
              ) : (
                <div className="w-6" />
              )}
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: dept.color ? `${dept.color}20` : 'rgba(6, 182, 212, 0.2)' }}
              >
                <Building
                  size={20}
                  style={{ color: dept.color || '#06b6d4' }}
                />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-white font-medium">{dept.name}</h3>
                  {isLead && !canManage && (
                    <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded-full">
                      Лид
                    </span>
                  )}
                  {dept.parent_name && (
                    <span className="text-xs text-white/30">
                      в {dept.parent_name}
                    </span>
                  )}
                </div>
                {dept.description && (
                  <p className="text-sm text-white/40 line-clamp-1">{dept.description}</p>
                )}
              </div>
            </div>
            {!dept.is_active && (
              <span className="text-xs px-2 py-0.5 bg-red-500/20 text-red-400 rounded-full">
                Неактивен
              </span>
            )}
          </div>

          <div className="flex items-center gap-4 text-sm text-white/40 ml-10">
            <div className="flex items-center gap-1">
              <Users size={14} />
              {dept.members_count} участников
            </div>
            <div className="flex items-center gap-1">
              <UserIcon size={14} />
              {dept.entities_count} контактов
            </div>
            {dept.children_count > 0 && (
              <div className="flex items-center gap-1">
                <Building size={14} />
                {dept.children_count} под-департаментов
              </div>
            )}
          </div>

          <div className="flex gap-2 mt-3 pt-3 border-t border-white/5 ml-10">
            {/* Add sub-department button for leads/owners */}
            {canCreateSubDept(dept.id) && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setCreateParentId(dept.id);
                  setShowCreateModal(true);
                }}
                className="flex-1 py-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 text-sm flex items-center justify-center gap-1"
              >
                <FolderPlus size={14} />
                Под-департамент
              </button>
            )}
            {/* Edit button - owner can edit all, lead can edit their dept */}
            {canEditDept(dept.id) && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedDept(dept);
                  setShowEditModal(true);
                }}
                className="flex-1 py-1.5 rounded-lg glass-button text-white/60 hover:text-white text-sm flex items-center justify-center gap-1"
              >
                <Edit3 size={14} />
                Изменить
              </button>
            )}
            {/* Delete button - only owner */}
            {isOwner && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(dept);
                }}
                className="py-1.5 px-3 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 text-sm flex items-center gap-1"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </motion.div>

        {/* Render children if expanded */}
        {isExpanded && children.map(child => renderDepartment(child, level + 1))}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        </div>
      </div>
    );
  }

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
            <h1 className="text-2xl font-bold mb-2 flex items-center gap-3">
              <Building className="text-cyan-400" />
              Департаменты
            </h1>
            <p className="text-white/40">
              Управление структурой организации
            </p>
          </div>
          {/* Only owner can create top-level departments */}
          {isOwner && (
            <button
              onClick={() => {
                setCreateParentId(undefined);
                setShowCreateModal(true);
              }}
              className="px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 flex items-center gap-2"
            >
              <Plus size={18} />
              Создать
            </button>
          )}
        </div>

        {/* Departments List (Hierarchical) */}
        {departments.length === 0 ? (
          <div className="text-center py-12 glass-light rounded-xl">
            <FolderOpen className="w-16 h-16 mx-auto text-white/20 mb-4" />
            <h2 className="text-xl font-semibold mb-2 text-white/60">Нет департаментов</h2>
            <p className="text-white/40 mb-4">Создайте первый департамент для организации работы</p>
            {isOwner && (
              <button
                onClick={() => {
                  setCreateParentId(undefined);
                  setShowCreateModal(true);
                }}
                className="px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 inline-flex items-center gap-2"
              >
                <Plus size={18} />
                Создать департамент
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {topLevelDepts.map(dept => renderDepartment(dept, 0))}
          </div>
        )}
      </motion.div>

      {/* Modals */}
      <AnimatePresence>
        {showCreateModal && (
          <CreateDepartmentModal
            parentId={createParentId}
            parentName={createParentId ? departments.find(d => d.id === createParentId)?.name : undefined}
            onClose={() => {
              setShowCreateModal(false);
              setCreateParentId(undefined);
            }}
            onSuccess={() => {
              setShowCreateModal(false);
              setCreateParentId(undefined);
              loadData();
            }}
          />
        )}
        {showEditModal && selectedDept && (
          <EditDepartmentModal
            department={selectedDept}
            onClose={() => {
              setShowEditModal(false);
              setSelectedDept(null);
            }}
            onSuccess={() => {
              setShowEditModal(false);
              setSelectedDept(null);
              loadData();
            }}
          />
        )}
        {showMembersModal && selectedDept && (
          <DepartmentMembersModal
            department={selectedDept}
            orgMembers={orgMembers}
            isOrgOwner={isOwner}
            myDeptRole={myDeptRoles.get(selectedDept.id) || null}
            onClose={() => {
              setShowMembersModal(false);
              setSelectedDept(null);
            }}
            onUpdate={loadData}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// Create Department Modal
function CreateDepartmentModal({
  parentId,
  parentName,
  onClose,
  onSuccess
}: {
  parentId?: number;
  parentName?: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [color, setColor] = useState(COLORS[0]);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.error('Введите название');
      return;
    }

    setLoading(true);
    try {
      await createDepartment({ name, description, color, parent_id: parentId });
      toast.success(parentId ? 'Под-департамент создан' : 'Департамент создан');
      onSuccess();
    } catch (e: any) {
      toast.error(getErrorDetail(e, 'Ошибка создания'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        className="glass rounded-xl p-6 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            {parentId ? <FolderPlus className="text-cyan-400" size={20} /> : <Plus className="text-cyan-400" size={20} />}
            {parentId ? 'Создать под-департамент' : 'Создать департамент'}
          </h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-white/60">
            <X size={20} />
          </button>
        </div>

        {parentName && (
          <div className="mb-4 p-3 rounded-lg glass-light">
            <p className="text-sm text-white/40">
              Родительский департамент: <span className="text-white">{parentName}</span>
            </p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-white/60 mb-1">Название</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={parentId ? "Рекрутинг" : "HR отдел"}
              className="w-full px-4 py-2 glass-light rounded-lg text-white placeholder-white/40"
            />
          </div>

          <div>
            <label className="block text-sm text-white/60 mb-1">Описание</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={parentId ? "Подразделение для поиска кандидатов" : "Отдел по работе с персоналом"}
              rows={2}
              className="w-full px-4 py-2 glass-light rounded-lg text-white placeholder-white/40 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm text-white/60 mb-2">Цвет</label>
            <div className="flex gap-2">
              {COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={clsx(
                    'w-8 h-8 rounded-lg transition-all',
                    color === c ? 'ring-2 ring-white ring-offset-2 ring-offset-gray-900' : ''
                  )}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : (parentId ? <FolderPlus size={18} /> : <Plus size={18} />)}
            {parentId ? 'Создать под-департамент' : 'Создать'}
          </button>
        </form>
      </motion.div>
    </motion.div>
  );
}

// Edit Department Modal
function EditDepartmentModal({
  department,
  onClose,
  onSuccess
}: {
  department: Department;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState(department.name);
  const [description, setDescription] = useState(department.description || '');
  const [color, setColor] = useState(department.color || COLORS[0]);
  const [isActive, setIsActive] = useState(department.is_active);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.error('Введите название');
      return;
    }

    setLoading(true);
    try {
      await updateDepartment(department.id, { name, description, color, is_active: isActive });
      toast.success('Департамент обновлён');
      onSuccess();
    } catch (e: any) {
      toast.error(getErrorDetail(e, 'Ошибка обновления'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        className="glass rounded-xl p-6 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Edit3 className="text-cyan-400" size={20} />
            Редактировать департамент
          </h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-white/60">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-white/60 mb-1">Название</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-4 py-2 glass-light rounded-lg text-white"
            />
          </div>

          <div>
            <label className="block text-sm text-white/60 mb-1">Описание</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full px-4 py-2 glass-light rounded-lg text-white resize-none"
            />
          </div>

          <div>
            <label className="block text-sm text-white/60 mb-2">Цвет</label>
            <div className="flex gap-2">
              {COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={clsx(
                    'w-8 h-8 rounded-lg transition-all',
                    color === c ? 'ring-2 ring-white ring-offset-2 ring-offset-gray-900' : ''
                  )}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="isActive"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 rounded glass-light border-white/20"
            />
            <label htmlFor="isActive" className="text-white/60">
              Активен
            </label>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Edit3 size={18} />}
            Сохранить
          </button>
        </form>
      </motion.div>
    </motion.div>
  );
}

// Department Members Modal
function DepartmentMembersModal({
  department,
  orgMembers,
  isOrgOwner,
  myDeptRole,
  onClose,
  onUpdate
}: {
  department: Department;
  orgMembers: OrgMember[];
  isOrgOwner: boolean;
  myDeptRole: DeptRole | null;
  onClose: () => void;
  onUpdate: () => void;
}) {
  // Permission logic:
  // - Org owner (superadmin): can do everything including set lead role
  // - Dept lead: can add/remove sub_admin and member, change roles (except lead)
  // - Dept sub_admin: can add/remove member only
  // - Dept member: cannot manage members at all
  const canManage = isOrgOwner || myDeptRole === 'lead' || myDeptRole === 'sub_admin';
  const canSetLeadRole = isOrgOwner;
  const canManageSubAdmins = isOrgOwner || myDeptRole === 'lead';
  const [members, setMembers] = useState<DepartmentMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddMember, setShowAddMember] = useState(false);

  useEffect(() => {
    loadMembers();
  }, [department.id]);

  const loadMembers = async () => {
    setLoading(true);
    try {
      const data = await getDepartmentMembers(department.id);
      setMembers(data);
    } catch (e) {
      console.error('Failed to load members:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleRoleChange = async (userId: number, newRole: DeptRole) => {
    try {
      await updateDepartmentMember(department.id, userId, newRole);
      toast.success('Роль изменена');
      loadMembers();
      onUpdate();
    } catch (e: any) {
      toast.error(getErrorDetail(e, 'Ошибка'));
    }
  };

  const handleRemoveMember = async (member: DepartmentMember) => {
    if (!confirm(`Удалить ${member.user_name} из департамента?`)) return;

    try {
      await removeDepartmentMember(department.id, member.user_id);
      toast.success('Участник удалён');
      loadMembers();
      onUpdate();
    } catch (e: any) {
      toast.error(getErrorDetail(e, 'Ошибка'));
    }
  };

  const handleAddMember = async (userId: number, role: DeptRole) => {
    try {
      await addDepartmentMember(department.id, { user_id: userId, role });
      toast.success('Участник добавлен');
      setShowAddMember(false);
      loadMembers();
      onUpdate();
    } catch (e: any) {
      toast.error(getErrorDetail(e, 'Ошибка'));
    }
  };

  const availableMembers = orgMembers.filter(
    (om) => !members.some((m) => m.user_id === om.user_id)
  );

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        className="glass rounded-xl p-6 w-full max-w-lg max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: department.color ? `${department.color}20` : 'rgba(6, 182, 212, 0.2)' }}
            >
              <Building size={20} style={{ color: department.color || '#06b6d4' }} />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">{department.name}</h3>
              <p className="text-sm text-white/40">{members.length} участников</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-white/60">
            <X size={20} />
          </button>
        </div>

        {/* Add member button */}
        {canManage && !showAddMember && availableMembers.length > 0 && (
          <button
            onClick={() => setShowAddMember(true)}
            className="w-full py-2 mb-4 glass-button rounded-lg text-white/60 hover:text-white flex items-center justify-center gap-2 flex-shrink-0"
          >
            <Plus size={18} />
            Добавить участника
          </button>
        )}

        {/* Add member form */}
        {showAddMember && (
          <AddMemberForm
            availableMembers={availableMembers}
            canSetLeadRole={canSetLeadRole}
            canAddSubAdmin={canManageSubAdmins}
            onAdd={handleAddMember}
            onCancel={() => setShowAddMember(false)}
          />
        )}

        {/* Members list */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
            </div>
          ) : members.length === 0 ? (
            <div className="text-center py-8">
              <Users className="w-12 h-12 mx-auto text-white/20 mb-3" />
              <p className="text-white/40">Нет участников</p>
            </div>
          ) : (
            <div className="space-y-2">
              {members.map((member) => {
                const roleConfig = DEPT_ROLE_CONFIG[member.role];
                const RoleIcon = roleConfig.icon;

                return (
                  <div
                    key={member.id}
                    className="p-3 rounded-lg glass-light flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <div className={clsx('p-1.5 rounded-lg', roleConfig.color)}>
                        <RoleIcon size={16} />
                      </div>
                      <div>
                        <h4 className="text-white text-sm font-medium">{member.user_name}</h4>
                        <p className="text-xs text-white/40">{member.user_email}</p>
                      </div>
                    </div>

                    {canManage && (
                      <div className="flex items-center gap-2">
                        {/* Role selector - who can change what:
                            - Owner: can change any role
                            - Lead: can change sub_admin <-> member (not lead)
                            - Sub_admin: can only see member role (no changes to sub_admin/lead)
                        */}
                        {canSetLeadRole ? (
                          <select
                            value={member.role}
                            onChange={(e) => handleRoleChange(member.user_id, e.target.value as DeptRole)}
                            className="px-2 py-1 glass-light rounded text-white text-sm"
                          >
                            <option value="lead">Руководитель</option>
                            <option value="sub_admin">Саб-админ</option>
                            <option value="member">Участник</option>
                          </select>
                        ) : canManageSubAdmins ? (
                          <select
                            value={member.role}
                            onChange={(e) => handleRoleChange(member.user_id, e.target.value as DeptRole)}
                            className="px-2 py-1 glass-light rounded text-white text-sm"
                            disabled={member.role === 'lead'}
                          >
                            {member.role === 'lead' && <option value="lead">Руководитель</option>}
                            <option value="sub_admin">Саб-админ</option>
                            <option value="member">Участник</option>
                          </select>
                        ) : (
                          // Sub_admin: can only see role, not change it (except for members)
                          <span className={clsx('text-xs px-2 py-1 rounded-lg', roleConfig.color)}>
                            {roleConfig.label}
                          </span>
                        )}
                        {/* Delete button - who can delete whom:
                            - Owner: can delete anyone except last lead
                            - Lead: can delete sub_admin and member
                            - Sub_admin: can delete only member
                        */}
                        {(isOrgOwner ||
                          (myDeptRole === 'lead' && member.role !== 'lead') ||
                          (myDeptRole === 'sub_admin' && member.role === 'member')) && (
                          <button
                            onClick={() => handleRemoveMember(member)}
                            className="p-1.5 rounded-lg hover:bg-red-500/20 text-red-400"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    )}

                    {!canManage && (
                      <span className={clsx('text-xs px-2 py-1 rounded-lg', roleConfig.color)}>
                        {roleConfig.label}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

// Add Member Form
function AddMemberForm({
  availableMembers,
  canSetLeadRole,
  canAddSubAdmin,
  onAdd,
  onCancel
}: {
  availableMembers: OrgMember[];
  canSetLeadRole: boolean;
  canAddSubAdmin: boolean;
  onAdd: (userId: number, role: DeptRole) => void;
  onCancel: () => void;
}) {
  const [userId, setUserId] = useState<number | ''>('');
  const [role, setRole] = useState<DeptRole>('member');

  return (
    <div className="p-3 mb-4 rounded-lg glass-light flex-shrink-0">
      <div className="flex flex-col sm:flex-row gap-2 mb-2">
        <select
          value={userId}
          onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : '')}
          className="flex-1 min-w-0 px-3 py-1.5 glass-light rounded-lg text-white text-sm truncate"
        >
          <option value="">Выберите пользователя</option>
          {availableMembers.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.user_name}
            </option>
          ))}
        </select>
        {/* Role selector based on permissions:
            - Owner: can add any role
            - Lead: can add sub_admin and member
            - Sub_admin: can only add member
        */}
        {canSetLeadRole ? (
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as DeptRole)}
            className="w-full sm:w-auto px-3 py-1.5 glass-light rounded-lg text-white text-sm flex-shrink-0"
          >
            <option value="lead">Руководитель</option>
            <option value="sub_admin">Саб-админ</option>
            <option value="member">Участник</option>
          </select>
        ) : canAddSubAdmin ? (
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as DeptRole)}
            className="w-full sm:w-auto px-3 py-1.5 glass-light rounded-lg text-white text-sm flex-shrink-0"
          >
            <option value="sub_admin">Саб-админ</option>
            <option value="member">Участник</option>
          </select>
        ) : (
          // Sub_admin: can only add members
          <span className="w-full sm:w-auto px-3 py-1.5 glass-light rounded-lg text-white text-sm flex-shrink-0">
            Участник
          </span>
        )}
      </div>
      <div className="flex gap-2">
        <button
          onClick={onCancel}
          className="flex-1 py-1.5 rounded-lg glass-button text-white/60 text-sm"
        >
          Отмена
        </button>
        <button
          onClick={() => userId && onAdd(userId as number, canAddSubAdmin ? role : 'member')}
          disabled={!userId}
          className="flex-1 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-600 text-white text-sm disabled:opacity-50"
        >
          Добавить
        </button>
      </div>
    </div>
  );
}
