import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Users,
  FolderKanban,
  ChevronDown,
  ChevronRight,
  UserPlus,
  UserMinus,
  FolderPlus,
  Settings2,
  Loader2,
  X,
  Check,
  Copy,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import * as api from '@/services/api';
import {
  getMyDeptRoles,
  quickAddDepartmentMember,
  getDepartments,
  getDepartmentMembers,
  removeDepartmentMember,
  createDepartment,
  type MyDeptRole,
  type QuickAddMemberResult,
  type DepartmentMember,
} from '@/services/api/auth';
import { useAuthStore } from '@/stores/authStore';
import { backdropClose } from '@/utils/backdropClose';

// Use the type from the backend response (array of user objects)
interface ResourceUser {
  user_id: number;
  user_name: string;
  projects: {
    project_id: number;
    project_name: string;
    project_status: string;
    role: string;
    allocation_percent: number;
  }[];
  total_allocation: number;
}

// ============================================================
// MAIN PAGE
// ============================================================

export default function TeamPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isPlatformAdmin = user?.role === 'superadmin' || user?.org_role === 'owner' || user?.org_role === 'admin';
  const [resources, setResources] = useState<ResourceUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
  const [addOpen, setAddOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [myDepts, setMyDepts] = useState<MyDeptRole[]>([]);
  // Управление отделом (удаление участников + под-отделы) — только для руководителей.
  // Для platform-админов ветка ниже проставляет role:'lead' всем их отделам.
  const myLeadDepts = myDepts.filter((d) => d.role === 'lead');

  const loadResources = useCallback(() => {
    setIsLoading(true);
    api.getResourceAllocation()
      .then((data: any) => {
        const users = Array.isArray(data) ? data : (data?.users || []);
        setResources(users);
      })
      .catch(() => setResources([]))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    loadResources();
  }, [loadResources]);

  useEffect(() => {
    // Куда можно добавлять:
    //   - superadmin / owner / org-admin — любые отделы организации
    //   - dept lead / sub_admin           — только свои отделы
    if (isPlatformAdmin) {
      getDepartments(-1)
        .then((depts) =>
          setMyDepts(depts.map((d) => ({ department_id: d.id, department_name: d.name, role: 'lead' as const })))
        )
        .catch(() => setMyDepts([]));
    } else {
      getMyDeptRoles()
        .then((roles) => setMyDepts(roles.filter((r) => r.role === 'lead' || r.role === 'sub_admin')))
        .catch(() => setMyDepts([]));
    }
  }, [isPlatformAdmin]);

  const toggle = (uid: number) => {
    setCollapsed((prev) => ({ ...prev, [uid]: !prev[uid] }));
  };

  const ROLE_LABELS: Record<string, string> = {
    manager: 'Менеджер',
    developer: 'Разработчик',
    reviewer: 'Ревьюер',
    observer: 'Наблюдатель',
  };

  const STATUS_LABELS: Record<string, string> = {
    planning: 'Планирование',
    active: 'В разработке',
    on_hold: 'На паузе',
    completed: 'Завершён',
    cancelled: 'Отменён',
  };

  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <Users className="w-5 h-5 text-emerald-400" />
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-bold text-white">Команда</h1>
          <p className="text-[11px] text-white/30">Распределение ресурсов по проектам</p>
        </div>
        {myLeadDepts.length > 0 && (
          <button
            onClick={() => setManageOpen(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.1] text-white/60 text-xs font-medium transition-colors"
          >
            <Settings2 className="w-4 h-4" />
            Управление отделом
          </button>
        )}
        {myDepts.length > 0 && (
          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 text-xs font-medium transition-colors"
          >
            <UserPlus className="w-4 h-4" />
            Добавить участника
          </button>
        )}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-8 h-8 border-2 border-emerald-400 border-t-transparent rounded-full" />
        </div>
      )}

      {/* Empty */}
      {!isLoading && resources.length === 0 && (
        <div className="flex flex-col items-center py-16 text-center">
          <Users className="w-10 h-10 text-white/10 mb-3" />
          <p className="text-sm text-white/30">Нет данных о команде</p>
          <p className="text-xs text-white/15 mt-1">Добавьте участников в проекты</p>
        </div>
      )}

      {/* Resource allocation table */}
      {!isLoading && resources.length > 0 && (
        <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden">
          {/* Header */}
          <div className="grid grid-cols-[1fr_100px_100px] gap-2 px-4 py-2.5 text-[10px] uppercase tracking-wider text-white/20 border-b border-white/5">
            <span>Участник</span>
            <span>Проектов</span>
            <span>Загрузка</span>
          </div>

          {resources.map((user) => {
            const isCollapsed = collapsed[user.user_id] ?? true;
            const overloaded = user.total_allocation > 100;

            return (
              <div key={user.user_id} className="border-b border-white/[0.04] last:border-b-0">
                {/* User row */}
                <button
                  onClick={() => toggle(user.user_id)}
                  className="w-full grid grid-cols-[1fr_100px_100px] gap-2 px-4 py-3 items-center hover:bg-white/[0.03] transition-colors text-left"
                >
                  <div className="flex items-center gap-3">
                    {isCollapsed
                      ? <ChevronRight className="w-4 h-4 text-white/20" />
                      : <ChevronDown className="w-4 h-4 text-white/20" />
                    }
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500/30 to-purple-500/30 flex items-center justify-center border border-white/10">
                      <span className="text-xs text-white/70 font-medium">
                        {user.user_name?.charAt(0).toUpperCase() || '?'}
                      </span>
                    </div>
                    <span className="text-sm text-white font-medium">{user.user_name}</span>
                  </div>

                  <span className="text-xs text-white/40">{user.projects.length}</span>

                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-white/[0.06] rounded-full overflow-hidden max-w-[60px]">
                      <div
                        className={clsx('h-full rounded-full', {
                          'bg-emerald-400': user.total_allocation <= 80,
                          'bg-amber-400': user.total_allocation > 80 && user.total_allocation <= 100,
                          'bg-red-400': overloaded,
                        })}
                        style={{ width: `${Math.min(user.total_allocation, 100)}%` }}
                      />
                    </div>
                    <span className={clsx('text-xs font-medium', {
                      'text-emerald-400': user.total_allocation <= 80,
                      'text-amber-400': user.total_allocation > 80 && user.total_allocation <= 100,
                      'text-red-400': overloaded,
                    })}>
                      {user.total_allocation}%
                    </span>
                  </div>
                </button>

                {/* Projects breakdown */}
                {!isCollapsed && user.projects.map((proj) => (
                  <motion.div
                    key={proj.project_id}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className="grid grid-cols-[1fr_100px_100px] gap-2 px-4 py-2 pl-16 items-center hover:bg-white/[0.02] cursor-pointer border-t border-white/[0.02]"
                    onClick={() => navigate(`/projects/${proj.project_id}`)}
                  >
                    <div className="flex items-center gap-2">
                      <FolderKanban className="w-3.5 h-3.5 text-white/20" />
                      <span className="text-xs text-white/60">{proj.project_name}</span>
                      <span className="text-[10px] text-white/20">{STATUS_LABELS[proj.project_status] || proj.project_status}</span>
                    </div>
                    <span className="text-[10px] text-white/30">{ROLE_LABELS[proj.role] || proj.role}</span>
                    <span className="text-[10px] text-white/30">{proj.allocation_percent}%</span>
                  </motion.div>
                ))}
              </div>
            );
          })}
        </div>
      )}

      <AnimatePresence>
        {addOpen && (
          <AddMemberModal
            myDepts={myDepts}
            onClose={() => setAddOpen(false)}
            onAdded={() => {
              setAddOpen(false);
              loadResources();
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {manageOpen && (
          <ManageDeptModal
            depts={myLeadDepts}
            currentUserId={user?.id}
            onClose={() => setManageOpen(false)}
            onChanged={loadResources}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ============================================================
// ADD MEMBER MODAL
// ============================================================

const POSITION_OPTIONS: { value: 'member' | 'sub_admin' | 'lead'; label: string; hint: string }[] = [
  { value: 'member', label: 'Участник', hint: 'обычный сотрудник отдела' },
  { value: 'sub_admin', label: 'Зам. руководителя', hint: 'видит всё, ограниченное управление' },
  { value: 'lead', label: 'Руководитель', hint: 'полный доступ к данным отдела' },
];

function AddMemberModal({
  myDepts,
  onClose,
  onAdded,
}: {
  myDepts: MyDeptRole[];
  onClose: () => void;
  onAdded: () => void;
}) {
  const [deptId, setDeptId] = useState<number>(myDepts[0]?.department_id ?? 0);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [telegram, setTelegram] = useState('');
  const [position, setPosition] = useState<'member' | 'sub_admin' | 'lead'>('member');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<QuickAddMemberResult | null>(null);

  const canSubmit = deptId > 0 && name.trim().length > 0 && email.trim().includes('@') && !submitting;

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const tg = telegram.trim().replace(/^@/, '').toLowerCase() || undefined;
      const r = await quickAddDepartmentMember(deptId, {
        name: name.trim(),
        email: email.trim().toLowerCase(),
        role: position,
        ...(tg ? { telegram_username: tg } : {}),
      });
      setResult(r);
      if (!r.password_generated) {
        // existing user — без пароля, можно сразу закрыть
        toast.success('Участник добавлен в отдел');
        onAdded();
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Не удалось добавить участника';
      toast.error(typeof msg === 'string' ? msg : 'Ошибка');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.95, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 10 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md bg-white dark:bg-[#0c0c10] border border-black/10 dark:border-white/[0.08] rounded-2xl p-5 shadow-xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              {result?.password_generated ? 'Сохрани пароль' : 'Добавить участника'}
            </h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:text-white/30 dark:hover:text-white/60">
            <X className="w-4 h-4" />
          </button>
        </div>

        {result?.password_generated ? (
          <div className="space-y-3">
            <p className="text-xs text-gray-600 dark:text-white/50">
              Новый аккаунт для <span className="text-gray-900 dark:text-white">{result.email}</span> создан.
              Пароль показывается один раз — передай его сотруднику.
            </p>
            <div className="flex items-center gap-2 px-3 py-2.5 bg-gray-50 dark:bg-white/[0.04] border border-black/10 dark:border-white/[0.08] rounded-lg">
              <code className="flex-1 text-sm text-emerald-600 dark:text-emerald-300 font-mono">{result.password_generated}</code>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(result.password_generated!);
                  toast.success('Пароль скопирован');
                }}
                className="text-gray-500 hover:text-gray-900 dark:text-white/40 dark:hover:text-white"
                title="Скопировать"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>
            <button
              onClick={onAdded}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/40 text-emerald-700 dark:text-emerald-300 text-sm font-medium"
            >
              <Check className="w-4 h-4" />
              Готово
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {myDepts.length > 1 && (
              <Field label="Отдел">
                <select
                  value={deptId}
                  onChange={(e) => setDeptId(Number(e.target.value))}
                  className="w-full bg-gray-50 dark:bg-white/[0.04] border border-black/10 dark:border-white/[0.08] rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
                >
                  {myDepts.map((d) => (
                    <option key={d.department_id} value={d.department_id} className="bg-white dark:bg-[#0c0c10] text-gray-900 dark:text-white">
                      {d.department_name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {myDepts.length === 1 && (
              <p className="text-[11px] text-gray-500 dark:text-white/40">
                В отдел: <span className="text-gray-800 dark:text-white/70">{myDepts[0].department_name}</span>
              </p>
            )}

            <Field label="Имя">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Иван Петров"
                className="w-full bg-gray-50 dark:bg-white/[0.04] border border-black/10 dark:border-white/[0.08] rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
              />
            </Field>

            <Field label="Email">
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                placeholder="ivan@example.com"
                className="w-full bg-gray-50 dark:bg-white/[0.04] border border-black/10 dark:border-white/[0.08] rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
              />
              <p className="text-[10px] text-gray-500 dark:text-white/30 mt-1">
                Если такой аккаунт уже есть — добавим его в отдел; нового пользователя создадим с паролем, который покажется один раз.
              </p>
            </Field>

            <Field label="Telegram (необязательно)">
              <input
                value={telegram}
                onChange={(e) => setTelegram(e.target.value)}
                placeholder="@ivan_petrov"
                className="w-full bg-gray-50 dark:bg-white/[0.04] border border-black/10 dark:border-white/[0.08] rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
              />
              <p className="text-[10px] text-gray-500 dark:text-white/30 mt-1">
                Чтобы наш бот сразу мог писать ему задачи и уведомления. Если аккаунт уже есть и Telegram у него уже привязан — не перетираем.
              </p>
            </Field>

            <Field label="Позиция">
              <div className="space-y-1">
                {POSITION_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    className={clsx(
                      'flex items-start gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors',
                      position === opt.value
                        ? 'bg-emerald-500/10 border-emerald-500/40'
                        : 'bg-gray-50 dark:bg-white/[0.02] border-black/10 dark:border-white/[0.06] hover:bg-gray-100 dark:hover:bg-white/[0.04]'
                    )}
                  >
                    <input
                      type="radio"
                      name="position"
                      value={opt.value}
                      checked={position === opt.value}
                      onChange={() => setPosition(opt.value)}
                      className="mt-0.5 accent-emerald-500"
                    />
                    <div className="flex-1">
                      <div className="text-sm text-gray-900 dark:text-white">{opt.label}</div>
                      <div className="text-[10px] text-gray-500 dark:text-white/30">{opt.hint}</div>
                    </div>
                  </label>
                ))}
              </div>
            </Field>

            <div className="flex gap-2 pt-2">
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-white/[0.04] dark:hover:bg-white/[0.06] border border-black/10 dark:border-white/[0.06] text-gray-700 dark:text-white/60 text-sm"
              >
                Отмена
              </button>
              <button
                onClick={submit}
                disabled={!canSubmit}
                className="flex-1 px-4 py-2 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 disabled:opacity-40 disabled:cursor-not-allowed border border-emerald-500/40 text-emerald-700 dark:text-emerald-300 text-sm font-medium"
              >
                {submitting ? 'Добавляю…' : 'Добавить'}
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

// ============================================================
// MANAGE DEPARTMENT MODAL (руководитель: удаление участников + под-отделы)
// ============================================================

const DEPT_ROLE_LABELS: Record<string, string> = {
  lead: 'Руководитель',
  sub_admin: 'Зам. руководителя',
  member: 'Участник',
};

function ManageDeptModal({
  depts,
  currentUserId,
  onClose,
  onChanged,
}: {
  depts: MyDeptRole[];
  currentUserId?: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [deptId, setDeptId] = useState<number>(depts[0]?.department_id ?? 0);
  const [members, setMembers] = useState<DepartmentMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [subName, setSubName] = useState('');
  const [creatingSub, setCreatingSub] = useState(false);

  const loadMembers = useCallback(() => {
    if (!deptId) return;
    setLoading(true);
    getDepartmentMembers(deptId)
      .then(setMembers)
      .catch(() => setMembers([]))
      .finally(() => setLoading(false));
  }, [deptId]);

  useEffect(() => { loadMembers(); }, [loadMembers]);

  const removeMember = async (m: DepartmentMember) => {
    // Руководителя и себя из этого интерфейса не удаляем (бэкенд тоже запретит).
    if (!confirm(`Удалить ${m.user_name} из отдела?`)) return;
    setRemovingId(m.user_id);
    try {
      await removeDepartmentMember(deptId, m.user_id);
      toast.success('Участник удалён из отдела');
      setMembers((prev) => prev.filter((x) => x.user_id !== m.user_id));
      onChanged();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Не удалось удалить';
      toast.error(typeof msg === 'string' ? msg : 'Ошибка');
    } finally {
      setRemovingId(null);
    }
  };

  const createSub = async () => {
    const name = subName.trim();
    if (!name || creatingSub) return;
    setCreatingSub(true);
    try {
      await createDepartment({ name, parent_id: deptId });
      toast.success('Под-отдел создан');
      setSubName('');
      onChanged();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Не удалось создать под-отдел';
      toast.error(typeof msg === 'string' ? msg : 'Ошибка');
    } finally {
      setCreatingSub(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.95, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 10 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md bg-white dark:bg-[#0c0c10] border border-black/10 dark:border-white/[0.08] rounded-2xl p-5 shadow-xl max-h-[85vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Управление отделом</h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 dark:text-white/30 dark:hover:text-white/60">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4">
          {depts.length > 1 ? (
            <Field label="Отдел">
              <select
                value={deptId}
                onChange={(e) => setDeptId(Number(e.target.value))}
                className="w-full bg-gray-50 dark:bg-white/[0.04] border border-black/10 dark:border-white/[0.08] rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
              >
                {depts.map((d) => (
                  <option key={d.department_id} value={d.department_id} className="bg-white dark:bg-[#0c0c10] text-gray-900 dark:text-white">
                    {d.department_name}
                  </option>
                ))}
              </select>
            </Field>
          ) : (
            <p className="text-[11px] text-gray-500 dark:text-white/40">
              Отдел: <span className="text-gray-800 dark:text-white/70">{depts[0]?.department_name}</span>
            </p>
          )}

          {/* Members */}
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-white/30 mb-1.5">Участники</div>
            {loading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="w-5 h-5 text-emerald-400 animate-spin" />
              </div>
            ) : members.length === 0 ? (
              <p className="text-xs text-gray-400 dark:text-white/30 py-2">В отделе нет участников</p>
            ) : (
              <div className="space-y-1">
                {members.map((m) => {
                  const isLead = m.role === 'lead';
                  const isSelf = currentUserId != null && m.user_id === currentUserId;
                  const canRemove = !isLead && !isSelf;
                  return (
                    <div
                      key={m.user_id}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 dark:bg-white/[0.03] border border-black/5 dark:border-white/[0.06]"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-900 dark:text-white truncate">{m.user_name}</div>
                        <div className="text-[10px] text-gray-500 dark:text-white/30">
                          {DEPT_ROLE_LABELS[m.role] || m.role}
                        </div>
                      </div>
                      {canRemove ? (
                        <button
                          onClick={() => removeMember(m)}
                          disabled={removingId === m.user_id}
                          className="p-1.5 rounded-md text-red-500 hover:bg-red-500/10 disabled:opacity-40 transition-colors"
                          title={`Удалить ${m.user_name} из отдела`}
                        >
                          {removingId === m.user_id
                            ? <Loader2 className="w-4 h-4 animate-spin" />
                            : <UserMinus className="w-4 h-4" />}
                        </button>
                      ) : (
                        <span className="text-[10px] text-gray-400 dark:text-white/20 pr-1">
                          {isSelf ? 'вы' : 'руков.'}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Create sub-department */}
          <div className="pt-1 border-t border-black/5 dark:border-white/[0.06]">
            <div className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-white/30 mb-1.5 mt-3">Под-отдел</div>
            <div className="flex gap-2">
              <input
                value={subName}
                onChange={(e) => setSubName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') createSub(); }}
                placeholder="Название под-отдела"
                className="flex-1 bg-gray-50 dark:bg-white/[0.04] border border-black/10 dark:border-white/[0.08] rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
              />
              <button
                onClick={createSub}
                disabled={!subName.trim() || creatingSub}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 disabled:opacity-40 disabled:cursor-not-allowed border border-emerald-500/40 text-emerald-700 dark:text-emerald-300 text-sm font-medium"
              >
                {creatingSub ? <Loader2 className="w-4 h-4 animate-spin" /> : <FolderPlus className="w-4 h-4" />}
                Создать
              </button>
            </div>
            <p className="text-[10px] text-gray-500 dark:text-white/30 mt-1">
              Создаётся внутри «{depts.find((d) => d.department_id === deptId)?.department_name}». Вы станете его руководителем.
            </p>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-white/30 mb-1.5">{label}</div>
      {children}
    </div>
  );
}
