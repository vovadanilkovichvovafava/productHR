import { backdropClose } from '@/utils/backdropClose';
import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Building,
  Plus,
  Trash2,
  Users,
  X,
  Edit3,
  Loader2,
  FolderKanban,
  UserPlus,
  UserMinus,
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import {
  getDepartments,
  createDepartment,
  updateDepartment,
  deleteDepartment,
  getDepartmentMembers,
  addDepartmentMember,
  removeDepartmentMember,
  quickAddDepartmentMember,
  getOrgMembers,
  type Department,
  type DepartmentMember,
} from '@/services/api';

// ============================================================
// TYPES
// ============================================================

interface OrgMember {
  id: number;
  user_id: number;
  user_name: string;
  user_email: string;
  role: string;
}

// ============================================================
// COLOR PICKER
// ============================================================

const DEPT_COLORS = [
  '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7',
  '#ec4899', '#ef4444', '#f97316', '#f59e0b',
  '#eab308', '#84cc16', '#22c55e', '#10b981',
  '#14b8a6', '#06b6d4', '#0ea5e9', '#6b7280',
];

function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {DEPT_COLORS.map(c => (
        <button
          key={c}
          onClick={() => onChange(c)}
          className={clsx(
            'w-6 h-6 rounded-md transition-all',
            value === c ? 'ring-2 ring-white ring-offset-1 ring-offset-dark-900 scale-110' : 'hover:scale-110',
          )}
          style={{ backgroundColor: c }}
        />
      ))}
    </div>
  );
}

// ============================================================
// CREATE/EDIT MODAL
// ============================================================

function DeptFormModal({
  isOpen,
  dept,
  onClose,
  onSave,
}: {
  isOpen: boolean;
  dept: Department | null;
  onClose: () => void;
  onSave: (data: { name: string; description?: string; color?: string }) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [color, setColor] = useState('#3b82f6');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (dept) {
      setName(dept.name);
      setDescription(dept.description || '');
      setColor(dept.color || '#3b82f6');
    } else {
      setName('');
      setDescription('');
      setColor('#3b82f6');
    }
  }, [dept, isOpen]);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave({ name: name.trim(), description: description.trim() || undefined, color });
      onClose();
    } catch {
      // error handled by caller
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" {...backdropClose(onClose)}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        onClick={e => e.stopPropagation()}
        className="bg-dark-800 border border-white/10 rounded-2xl p-6 w-full max-w-md shadow-2xl"
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-white">
            {dept ? 'Редактировать отдел' : 'Новый отдел'}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/10 text-white/40 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs text-white/40 mb-1.5">Название</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Название отдела"
              className="w-full px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white text-sm placeholder-white/25 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs text-white/40 mb-1.5">Описание</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Описание (необязательно)"
              rows={2}
              className="w-full px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-white text-sm placeholder-white/25 focus:outline-none focus:ring-1 focus:ring-blue-500/40 resize-none"
            />
          </div>

          <div>
            <label className="block text-xs text-white/40 mb-1.5">Цвет</label>
            <ColorPicker value={color} onChange={setColor} />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs text-white/50 hover:text-white/70 transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || saving}
            className="flex items-center gap-2 px-4 py-2 text-xs font-medium text-white bg-blue-500 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            {saving && <Loader2 className="w-3 h-3 animate-spin" />}
            {dept ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ============================================================
// MEMBERS PANEL
// ============================================================

function MembersPanel({
  dept,
  members,
  orgMembers,
  onAdd,
  onRemove,
  onQuickAdd,
  onClose,
}: {
  dept: Department;
  members: DepartmentMember[];
  orgMembers: OrgMember[];
  onAdd: (userId: number) => void;
  onRemove: (userId: number) => void;
  onQuickAdd: (data: { name: string; email: string; role: string }) => Promise<void>;
  onClose: () => void;
}) {
  const [showAddDropdown, setShowAddDropdown] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState('member');
  const [quickAdding, setQuickAdding] = useState(false);
  const memberUserIds = new Set(members.map(m => m.user_id));
  const availableMembers = orgMembers.filter(m => !memberUserIds.has(m.user_id));

  const handleQuickAdd = async () => {
    if (!newName.trim() || !newEmail.trim()) return;
    setQuickAdding(true);
    try {
      await onQuickAdd({ name: newName.trim(), email: newEmail.trim(), role: newRole });
      setNewName('');
      setNewEmail('');
      setNewRole('member');
    } finally {
      setQuickAdding(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      className="bg-white/[0.03] border border-white/10 rounded-2xl p-5"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: dept.color || '#6b7280' }} />
          <h3 className="text-sm font-semibold text-white">{dept.name}</h3>
          <span className="text-xs text-white/25">{members.length} чел.</span>
        </div>
        <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/10 text-white/40">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Add member */}
      <div className="relative mb-3">
        <button
          onClick={() => setShowAddDropdown(!showAddDropdown)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-blue-400 hover:bg-blue-500/10 rounded-lg transition-colors"
        >
          <UserPlus className="w-3.5 h-3.5" />
          Добавить участника
        </button>
        {showAddDropdown && availableMembers.length > 0 && (
          <div className="absolute top-full left-0 mt-1 w-64 bg-dark-800 border border-white/10 rounded-xl shadow-xl z-10 max-h-48 overflow-y-auto">
            {availableMembers.map(m => (
              <button
                key={m.user_id}
                onClick={() => { onAdd(m.user_id); setShowAddDropdown(false); }}
                className="w-full text-left px-3 py-2 text-xs text-white/70 hover:bg-white/[0.06] transition-colors flex items-center gap-2"
              >
                <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center text-[10px] text-white/50 font-medium">
                  {m.user_name?.charAt(0) || m.user_email?.charAt(0) || '?'}
                </div>
                <div className="min-w-0">
                  <div className="truncate">{m.user_name || m.user_email}</div>
                  {m.user_name && <div className="text-[10px] text-white/30 truncate">{m.user_email}</div>}
                </div>
              </button>
            ))}
            {availableMembers.length === 0 && (
              <div className="px-3 py-2 text-xs text-white/30">Все уже добавлены</div>
            )}
          </div>
        )}
      </div>

      {/* Members list */}
      <div className="space-y-1">
        {members.map(m => (
          <div key={m.id} className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-white/[0.04] group">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-xs text-white/50 font-medium flex-shrink-0">
                {m.user_name?.charAt(0) || '?'}
              </div>
              <div className="min-w-0">
                <div className="text-xs text-white truncate">{m.user_name}</div>
                <div className="text-[10px] text-white/25 truncate">{m.user_email}</div>
              </div>
            </div>
            <button
              onClick={() => onRemove(m.user_id)}
              className="p-1 rounded-lg text-white/10 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all"
            >
              <UserMinus className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
        {members.length === 0 && (
          <div className="text-xs text-white/20 text-center py-6">Нет участников</div>
        )}
      </div>

      {/* Quick add new user */}
      <div className="border-t border-white/10 pt-3 mt-3">
        <p className="text-[10px] text-white/30 uppercase tracking-wider mb-2">Новый сотрудник</p>
        <input
          placeholder="Имя"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-white/25 mb-2 focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
        />
        <input
          placeholder="Email"
          value={newEmail}
          onChange={e => setNewEmail(e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-white/25 mb-2 focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
        />
        <select
          value={newRole}
          onChange={e => setNewRole(e.target.value)}
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white mb-2 focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
        >
          <option value="member">Участник</option>
          <option value="lead">Лид</option>
          <option value="sub_admin">Зам. лида</option>
        </select>
        <button
          onClick={handleQuickAdd}
          disabled={!newName.trim() || !newEmail.trim() || quickAdding}
          className="w-full flex items-center justify-center gap-2 py-2 text-xs font-medium text-white bg-emerald-500 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg transition-colors"
        >
          {quickAdding && <Loader2 className="w-3 h-3 animate-spin" />}
          Создать и добавить
        </button>
      </div>
    </motion.div>
  );
}

// ============================================================
// MAIN PAGE
// ============================================================

export default function DeptManagerPage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editDept, setEditDept] = useState<Department | null>(null);
  const [selectedDeptId, setSelectedDeptId] = useState<number | null>(null);
  const [members, setMembers] = useState<DepartmentMember[]>([]);
  const [orgMembers, setOrgMembers] = useState<OrgMember[]>([]);

  const fetchDepts = useCallback(async () => {
    try {
      const depts = await getDepartments(-1);
      setDepartments(depts);
    } catch {
      toast.error('Не удалось загрузить отделы');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDepts(); }, [fetchDepts]);

  useEffect(() => {
    getOrgMembers().then((m: any[]) => setOrgMembers(m)).catch(() => {});
  }, []);

  useEffect(() => {
    if (selectedDeptId) {
      getDepartmentMembers(selectedDeptId).then(setMembers).catch(() => setMembers([]));
    }
  }, [selectedDeptId]);

  const handleCreate = async (data: { name: string; description?: string; color?: string }) => {
    await createDepartment(data);
    toast.success('Отдел создан');
    fetchDepts();
  };

  const handleUpdate = async (data: { name: string; description?: string; color?: string }) => {
    if (!editDept) return;
    await updateDepartment(editDept.id, data);
    toast.success('Отдел обновлён');
    fetchDepts();
    if (selectedDeptId === editDept.id) {
      setSelectedDeptId(null);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteDepartment(id);
      toast.success('Отдел удалён');
      if (selectedDeptId === id) setSelectedDeptId(null);
      fetchDepts();
    } catch {
      toast.error('Не удалось удалить');
    }
  };

  const handleAddMember = async (userId: number) => {
    if (!selectedDeptId) return;
    try {
      await addDepartmentMember(selectedDeptId, { user_id: userId });
      const updated = await getDepartmentMembers(selectedDeptId);
      setMembers(updated);
      fetchDepts();
      toast.success('Участник добавлен');
    } catch {
      toast.error('Не удалось добавить');
    }
  };

  const handleRemoveMember = async (userId: number) => {
    if (!selectedDeptId) return;
    try {
      await removeDepartmentMember(selectedDeptId, userId);
      const updated = await getDepartmentMembers(selectedDeptId);
      setMembers(updated);
      fetchDepts();
      toast.success('Участник удалён');
    } catch {
      toast.error('Не удалось удалить');
    }
  };

  const handleQuickAddMember = async (data: { name: string; email: string; role: string }) => {
    if (!selectedDeptId) return;
    try {
      const result = await quickAddDepartmentMember(selectedDeptId, data);
      if (result.already_existed) {
        toast.success('Пользователь уже существует, добавлен в отдел');
      } else if (result.password_generated) {
        toast.success(`Пользователь создан! Пароль: ${result.password_generated}`, { duration: 15000 });
      }
      const updated = await getDepartmentMembers(selectedDeptId);
      setMembers(updated);
      // Refresh org members list so the new user appears in the dropdown too
      getOrgMembers().then((m: OrgMember[]) => setOrgMembers(m)).catch(() => {});
      fetchDepts();
    } catch {
      toast.error('Не удалось создать пользователя');
    }
  };

  const selectedDept = departments.find(d => d.id === selectedDeptId);

  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20">
            <Building className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Отделы</h1>
            <p className="text-[11px] text-white/30">Управление отделами и участниками</p>
          </div>
        </div>
        <button
          onClick={() => { setEditDept(null); setShowForm(true); }}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-500 hover:bg-blue-600 rounded-xl transition-colors shadow-lg shadow-blue-500/20"
        >
          <Plus className="w-4 h-4" />
          Отдел
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full" />
        </div>
      )}

      {/* Content */}
      {!loading && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
          {/* Departments list */}
          <div className="space-y-2">
            {departments.length === 0 && (
              <div className="flex flex-col items-center py-16 text-center">
                <Building className="w-10 h-10 text-white/10 mb-3" />
                <p className="text-sm text-white/30">Нет отделов</p>
                <p className="text-xs text-white/15 mt-1">Создайте первый отдел</p>
              </div>
            )}

            <AnimatePresence>
              {departments.map(dept => (
                <motion.div
                  key={dept.id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className={clsx(
                    'flex items-center gap-4 p-4 rounded-xl border transition-all cursor-pointer group',
                    selectedDeptId === dept.id
                      ? 'bg-white/[0.06] border-white/15'
                      : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04] hover:border-white/10',
                  )}
                  onClick={() => setSelectedDeptId(selectedDeptId === dept.id ? null : dept.id)}
                >
                  {/* Color dot */}
                  <div className="w-3 h-8 rounded-full flex-shrink-0" style={{ backgroundColor: dept.color || '#6b7280' }} />

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{dept.name}</p>
                    {dept.description && (
                      <p className="text-[11px] text-white/25 truncate mt-0.5">{dept.description}</p>
                    )}
                  </div>

                  {/* Stats */}
                  <div className="flex items-center gap-4 text-[11px] text-white/30 flex-shrink-0">
                    <div className="flex items-center gap-1">
                      <Users className="w-3.5 h-3.5" />
                      <span>{dept.members_count}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <FolderKanban className="w-3.5 h-3.5" />
                      <span>{dept.entities_count}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    <button
                      onClick={e => { e.stopPropagation(); setEditDept(dept); setShowForm(true); }}
                      className="p-1.5 rounded-lg hover:bg-white/10 text-white/30 hover:text-white transition-colors"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={e => { e.stopPropagation(); handleDelete(dept.id); }}
                      className="p-1.5 rounded-lg hover:bg-red-500/10 text-white/30 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          {/* Members panel */}
          <AnimatePresence>
            {selectedDept && (
              <MembersPanel
                dept={selectedDept}
                members={members}
                orgMembers={orgMembers}
                onAdd={handleAddMember}
                onRemove={handleRemoveMember}
                onQuickAdd={handleQuickAddMember}
                onClose={() => setSelectedDeptId(null)}
              />
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Create/Edit modal */}
      <DeptFormModal
        isOpen={showForm}
        dept={editDept}
        onClose={() => { setShowForm(false); setEditDept(null); }}
        onSave={editDept ? handleUpdate : handleCreate}
      />
    </div>
  );
}
