import { useState, useEffect, useRef } from 'react';
import { useUrlTab } from '@/hooks/useUrlTab';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import * as Dialog from '@radix-ui/react-dialog';
import {
  Users,
  Plus,
  Trash2,
  Shield,
  User as UserIcon,
  UserCheck,
  X,
  Crown,
  Building2,
  Loader2,
  Link as LinkIcon,
  Copy,
  Check,
  Clock,
  Send,
  Sparkles,
  Key,
  Database,
  Pencil,
  MessageCircle
} from 'lucide-react';
import { getUsers, createUser, deleteUser, adminResetPassword, adminUpdateUser, getOrgMembers, removeMember, updateMemberRole, toggleMemberFullAccess, getCurrentOrganization, getMyOrgRole, getDepartments, getMyDepartments, getMyManagedUserIds, createInvitation, getInvitations, revokeInvitation, addDepartmentMember, type Department, type DeptRole, type Invitation } from '@/services/api';
import type { OrgMember, OrgRole, Organization } from '@/services/api';
import type { User } from '@/types';
import { getVacancies } from '@/services/api/vacancies';
import { useAuthStore } from '@/stores/authStore';
import toast from 'react-hot-toast';
import { getErrorDetail } from '@/utils';
import clsx from 'clsx';
import { backdropClose } from '@/utils/backdropClose';

const ORG_ROLE_CONFIG: Record<OrgRole, { label: string; icon: typeof Crown; color: string; description: string }> = {
  owner: { label: 'Владелец', icon: Crown, color: 'text-yellow-400 bg-yellow-500/20', description: 'Полный доступ, управление организацией' },
  admin: { label: 'HR Админ', icon: Shield, color: 'text-cyan-400 bg-cyan-500/20', description: 'Полный HR доступ: ПЭН, аналитика, экспорт, сотрудники' },
  hr: { label: 'HR Рекрутер', icon: UserCheck, color: 'text-purple-400 bg-purple-500/20', description: 'Кандидаты, воронки, вакансии, созвоны' },
  member: { label: 'Сотрудник', icon: UserIcon, color: 'text-white/60 bg-white/10', description: 'Профиль, проекты, документы' },
};

export default function UsersPage() {
  const { user: currentUser } = useAuthStore();
  const isSuperadmin = currentUser?.role === 'superadmin';
  // Вкладка в URL (?tab=) — браузерный «Назад/Вперёд» между «Организация»/«Система».
  const [activeTab, setActiveTab] = useUrlTab<'org' | 'system'>('tab', isSuperadmin ? 'system' : 'org');

  return (
    <div className="h-full w-full max-w-full overflow-y-auto overflow-x-hidden p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-4xl mx-auto space-y-6 w-full"
      >
        {/* Header with tabs */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold mb-2 flex items-center gap-3">
              <Users className="text-cyan-400" />
              Управление пользователями
            </h1>
            {isSuperadmin && (
              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => setActiveTab('org')}
                  className={clsx(
                    'px-4 py-2 rounded-lg text-sm transition-colors flex items-center gap-2',
                    activeTab === 'org'
                      ? 'bg-cyan-500/20 text-cyan-400'
                      : 'glass-light text-white/60 hover:bg-white/10'
                  )}
                >
                  <Building2 size={16} />
                  Организация
                </button>
                <button
                  onClick={() => setActiveTab('system')}
                  className={clsx(
                    'px-4 py-2 rounded-lg text-sm transition-colors flex items-center gap-2',
                    activeTab === 'system'
                      ? 'bg-cyan-500/20 text-cyan-400'
                      : 'glass-light text-white/60 hover:bg-white/10'
                  )}
                >
                  <Shield size={16} />
                  Система
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Content */}
        <AnimatePresence mode="wait">
          {activeTab === 'org' ? (
            <OrganizationMembers key="org" currentUser={currentUser} />
          ) : (
            <SystemUsers key="system" currentUser={currentUser} />
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

// Organization Members Component
function OrganizationMembers({ currentUser }: { currentUser: any }) {
  const { hasFeature } = useAuthStore();
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [myRole, setMyRole] = useState<OrgRole | null>(null);
  const [myDepartmentIds, setMyDepartmentIds] = useState<number[]>([]);
  const [myManagedUserIds, setMyManagedUserIds] = useState<number[]>([]); // Users that dept lead/sub_admin can manage
  const [loading, setLoading] = useState(true);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [showInvitationsTab, setShowInvitationsTab] = useState(false);

  // Check if current user's department has candidate_database feature
  const canManageFullAccess = hasFeature('candidate_database');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [orgData, membersData, roleData, invitationsData, myDepts, managedUsers] = await Promise.all([
        getCurrentOrganization(),
        getOrgMembers(),
        getMyOrgRole(),
        getInvitations(),
        getMyDepartments(),
        getMyManagedUserIds()
      ]);
      setOrganization(orgData);
      setMembers(membersData);
      setMyRole(roleData.role);
      setInvitations(invitationsData);
      setMyDepartmentIds(myDepts.map(d => d.id));
      setMyManagedUserIds(managedUsers);
    } catch (e) {
      console.error('Failed to load organization data:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleChangeRole = async (userId: number, newRole: OrgRole) => {
    try {
      await updateMemberRole(userId, newRole);
      toast.success('Роль изменена');
      loadData();
    } catch (e) {
      toast.error('Не удалось изменить роль');
    }
  };

  const handleRemoveMember = async (member: OrgMember) => {
    if (!confirm(`Удалить ${member.user_name} из организации?`)) return;

    try {
      await removeMember(member.user_id);
      toast.success('Пользователь удалён');
      loadData();
    } catch (e) {
      toast.error('Не удалось удалить пользователя');
    }
  };

  const handleToggleFullAccess = async (member: OrgMember) => {
    const newValue = !member.has_full_access;
    const action = newValue ? 'Включить' : 'Отключить';
    if (!confirm(`${action} полный доступ к базе для ${member.user_name}?\n\nЭто даст/уберёт доступ ко всем вакансиям и кандидатам организации.`)) return;

    try {
      await toggleMemberFullAccess(member.user_id, newValue);
      toast.success(newValue ? 'Полный доступ включён' : 'Полный доступ отключён');
      loadData();
    } catch (e: any) {
      toast.error(getErrorDetail(e, 'Не удалось изменить доступ'));
    }
  };

  const handleRevokeInvitation = async (invitation: Invitation) => {
    if (!confirm('Отменить приглашение?')) return;

    try {
      await revokeInvitation(invitation.id);
      toast.success('Приглашение отменено');
      loadData();
    } catch (e) {
      toast.error('Не удалось отменить приглашение');
    }
  };

  const canManageUsers = myRole === 'owner' || myRole === 'admin' || currentUser?.role === 'superadmin';
  const canChangeRoles = myRole === 'owner' || currentUser?.role === 'superadmin';

  if (loading) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="flex items-center justify-center py-12"
      >
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="space-y-6"
    >
      {/* Organization Info */}
      {organization && (
        <div className="glass-light rounded-xl p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Building2 className="text-cyan-400" size={20} />
                {organization.name}
              </h3>
              <p className="text-sm text-white/40">{members.length} участников</p>
            </div>
            {canManageUsers && (
              <button
                onClick={() => setShowInviteModal(true)}
                className="px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 flex items-center gap-2"
              >
                <LinkIcon size={18} />
                Пригласить
              </button>
            )}
          </div>
          {/* Tabs */}
          <div className="flex gap-2 border-t border-white/5 pt-3">
            <button
              onClick={() => setShowInvitationsTab(false)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2',
                !showInvitationsTab
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'glass-light text-white/60 hover:bg-white/10'
              )}
            >
              <Users size={14} />
              Участники ({members.length})
            </button>
            {canManageUsers && (
              <button
                onClick={() => setShowInvitationsTab(true)}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2',
                  showInvitationsTab
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'glass-light text-white/60 hover:bg-white/10'
                )}
              >
                <Send size={14} />
                Приглашения ({invitations.length})
              </button>
            )}
          </div>
        </div>
      )}

      {/* My Role */}
      {myRole && (
        <div className="glass-light rounded-xl p-4">
          <p className="text-sm text-white/40 mb-1">Ваша роль в организации</p>
          <div className="flex items-center gap-2">
            {(() => {
              const config = ORG_ROLE_CONFIG[myRole];
              const Icon = config.icon;
              return (
                <>
                  <span className={clsx('p-1.5 rounded-lg', config.color)}>
                    <Icon size={16} />
                  </span>
                  <span className="text-white font-medium">{config.label}</span>
                  <span className="text-white/40 text-sm">— {config.description}</span>
                </>
              );
            })()}
          </div>
        </div>
      )}

      {/* Members List */}
      {!showInvitationsTab && (
        <div className="space-y-3">
          {members.map((member) => {
            const roleConfig = ORG_ROLE_CONFIG[member.role];
            const RoleIcon = roleConfig.icon;
            const isMe = member.user_id === currentUser?.id;

            return (
              <motion.div
                key={member.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={clsx(
                  'p-4 rounded-xl border transition-colors',
                  isMe ? 'bg-cyan-500/10 border-cyan-500/20' : 'glass-light'
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={clsx('p-2 rounded-lg', roleConfig.color)}>
                      <RoleIcon size={20} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-white font-medium">{member.user_name}</h3>
                        {isMe && (
                          <span className="text-xs px-2 py-0.5 bg-cyan-500/20 text-cyan-400 rounded-full">
                            Это вы
                          </span>
                        )}
                        {member.has_full_access && !isMe && (
                          <span className="text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded-full flex items-center gap-1">
                            <Database size={10} />
                            Полный доступ
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-white/40">{member.user_email}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {canChangeRoles && !isMe && member.role !== 'owner' && (
                      <select
                        value={member.role}
                        onChange={(e) => handleChangeRole(member.user_id, e.target.value as OrgRole)}
                        className="px-3 py-1.5 glass-light rounded-lg text-white text-sm"
                      >
                        <option value="admin">HR Админ</option>
                        <option value="hr">HR Рекрутер</option>
                        <option value="member">Сотрудник</option>
                      </select>
                    )}

                    {!canChangeRoles && (
                      <span className={clsx('text-sm px-2 py-1 rounded-lg', roleConfig.color)}>
                        {roleConfig.label}
                      </span>
                    )}

                    {/* Full Access Toggle - for non-owners only */}
                    {/* Can be toggled by: org admin/owner OR dept lead/sub_admin for their dept members */}
                    {/* Only show if current user's department has candidate_database feature */}
                    {!isMe && member.role !== 'owner' && canManageFullAccess && (canManageUsers || myManagedUserIds.includes(member.user_id)) && (
                      <button
                        onClick={() => handleToggleFullAccess(member)}
                        className={clsx(
                          'p-2 rounded-lg transition-colors flex items-center gap-1.5',
                          member.has_full_access
                            ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                            : 'glass-light text-white/40 hover:bg-white/10 hover:text-white/60'
                        )}
                        title={member.has_full_access ? 'Полный доступ к базе (нажмите чтобы отключить)' : 'Дать полный доступ к базе'}
                      >
                        <Database size={16} />
                        {member.has_full_access && <span className="text-xs">Полный</span>}
                      </button>
                    )}

                    {canManageUsers && !isMe && (() => {
                      // Permission logic for delete button:
                      // - Superadmin: can delete anyone
                      // - Owner: can delete admins and members (not other owners)
                      // - Lead: can delete sub_admins and members in own department (not other leads)
                      // - Sub_admin: can delete only members in own department (not leads or other sub_admins)

                      const isSuperadmin = currentUser?.role === 'superadmin';
                      const isOwner = myRole === 'owner';
                      const isAdmin = myRole === 'admin';
                      const myDeptRole = currentUser?.department_role;
                      const inSameDept = member.department_id && myDepartmentIds.includes(member.department_id);

                      if (isSuperadmin) return true;
                      if (isOwner && member.role !== 'owner') return true;
                      if (isAdmin && inSameDept) {
                        // Lead can delete sub_admin and member
                        if (myDeptRole === 'lead') {
                          return member.department_role !== 'lead';
                        }
                        // Sub_admin can only delete member
                        if (myDeptRole === 'sub_admin') {
                          return member.department_role === 'member';
                        }
                      }
                      return false;
                    })() && (
                        <button
                          onClick={() => handleRemoveMember(member)}
                          className="p-2 rounded-lg hover:bg-red-500/20 text-red-400 transition-colors"
                          title={`Удалить ${member.user_name}`}
                        >
                          <Trash2 size={16} />
                        </button>
                      )
                    }
                  </div>
                </div>

                {member.invited_by_name && (
                  <p className="text-xs text-white/30 mt-2">
                    Приглашён: {member.invited_by_name} • {new Date(member.created_at).toLocaleDateString('ru-RU')}
                  </p>
                )}
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Invitations List */}
      {showInvitationsTab && (
        <div className="space-y-3">
          {invitations.length === 0 ? (
            <div className="text-center py-8">
              <Send className="w-12 h-12 mx-auto text-white/20 mb-3" />
              <p className="text-white/40">Нет активных приглашений</p>
              <p className="text-sm text-white/30 mt-1">Создайте приглашение для добавления нового участника</p>
            </div>
          ) : (
            invitations.map((invitation) => (
              <InvitationCard
                key={invitation.id}
                invitation={invitation}
                onRevoke={() => handleRevokeInvitation(invitation)}
              />
            ))
          )}
        </div>
      )}

      {/* Invite Modal */}
      <AnimatePresence>
        {showInviteModal && (
          <InviteMemberModal
            onClose={() => setShowInviteModal(false)}
            onSuccess={() => {
              setShowInviteModal(false);
              loadData();
            }}
            canSetRole={canChangeRoles}
            myDepartmentIds={myDepartmentIds}
            isOwner={myRole === 'owner' || currentUser?.role === 'superadmin'}
          />
        )}
      </AnimatePresence>

    </motion.div>
  );
}

// Invitation Card Component
function InvitationCard({ invitation, onRevoke }: { invitation: Invitation; onRevoke: () => void }) {
  const [copied, setCopied] = useState(false);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  // Cleanup timeout on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  const inviteUrl = `${window.location.origin}${invitation.invitation_url}`;
  const isExpired = invitation.expires_at && new Date(invitation.expires_at) < new Date();

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      toast.success('Ссылка скопирована');
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Не удалось скопировать');
    }
  };

  const roleConfig = ORG_ROLE_CONFIG[invitation.org_role];
  const RoleIcon = roleConfig.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'p-4 rounded-xl border',
        isExpired ? 'bg-red-500/5 border-red-500/20' : 'glass-light'
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <div className={clsx('p-1.5 rounded-lg', roleConfig.color)}>
              <RoleIcon size={16} />
            </div>
            <span className="text-white font-medium">
              {invitation.name || invitation.email || 'Новый участник'}
            </span>
            {isExpired && (
              <span className="text-xs px-2 py-0.5 bg-red-500/20 text-red-400 rounded-full">
                Истекло
              </span>
            )}
          </div>

          {invitation.email && (
            <p className="text-sm text-white/40 mb-2">{invitation.email}</p>
          )}

          {/* Invite Link */}
          <div className="flex items-center gap-2 p-2 glass-light rounded-lg">
            <input
              type="text"
              value={inviteUrl}
              readOnly
              className="flex-1 bg-transparent text-white/60 text-xs truncate border-none outline-none"
            />
            <button
              onClick={copyLink}
              className="p-1.5 rounded hover:bg-white/10 text-white/60 hover:text-cyan-400 transition-colors"
              title="Копировать ссылку"
            >
              {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
            </button>
          </div>

          <div className="flex items-center gap-4 mt-2 text-xs text-white/30">
            {invitation.invited_by_name && (
              <span>От: {invitation.invited_by_name}</span>
            )}
            {invitation.expires_at && (
              <span className="flex items-center gap-1">
                <Clock size={12} />
                До: {new Date(invitation.expires_at).toLocaleDateString('ru-RU')}
              </span>
            )}
          </div>
        </div>

        <button
          onClick={onRevoke}
          className="p-2 rounded-lg hover:bg-red-500/20 text-red-400 transition-colors"
          title="Отменить приглашение"
        >
          <Trash2 size={16} />
        </button>
      </div>
    </motion.div>
  );
}

// Invite Member Modal - Creates invitation link
function InviteMemberModal({
  onClose,
  onSuccess,
  canSetRole,
  myDepartmentIds,
  isOwner
}: {
  onClose: () => void;
  onSuccess: () => void;
  canSetRole: boolean;
  myDepartmentIds: number[];
  isOwner: boolean;
}) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<OrgRole>('member');
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [loading, setLoading] = useState(false);
  const [createdInvitation, setCreatedInvitation] = useState<Invitation | null>(null);
  const [copied, setCopied] = useState(false);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedDepartments, setSelectedDepartments] = useState<{ id: number; role: DeptRole }[]>([]);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  // Cleanup timeout on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  // Load departments on mount - filter for non-owners
  useEffect(() => {
    const loadDepartments = async () => {
      try {
        const depts = await getDepartments(-1); // Get all departments
        // Owner sees all, admin sees only their departments
        if (isOwner) {
          setDepartments(depts);
        } else {
          setDepartments(depts.filter(d => myDepartmentIds.includes(d.id)));
        }
      } catch (e) {
        console.error('Failed to load departments:', e);
      }
    };
    loadDepartments();
  }, [isOwner, myDepartmentIds]);

  const toggleDepartment = (deptId: number) => {
    setSelectedDepartments(prev => {
      const exists = prev.find(d => d.id === deptId);
      if (exists) {
        return prev.filter(d => d.id !== deptId);
      }
      return [...prev, { id: deptId, role: 'member' as DeptRole }];
    });
  };

  const setDepartmentRole = (deptId: number, newRole: DeptRole) => {
    setSelectedDepartments(prev =>
      prev.map(d => d.id === deptId ? { ...d, role: newRole } : d)
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    setLoading(true);
    try {
      const invitation = await createInvitation({
        email: email || undefined,
        name: name || undefined,
        org_role: role,
        department_ids: selectedDepartments.length > 0 ? selectedDepartments : undefined,
        expires_in_days: expiresInDays
      });
      setCreatedInvitation(invitation);
      toast.success('Приглашение создано!');
    } catch (e: any) {
      toast.error(getErrorDetail(e, 'Ошибка создания приглашения'));
    } finally {
      setLoading(false);
    }
  };

  const inviteUrl = createdInvitation ? `${window.location.origin}${createdInvitation.invitation_url}` : '';

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      toast.success('Ссылка скопирована');
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Не удалось скопировать');
    }
  };

  // If invitation created, show success screen with link
  if (createdInvitation) {
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
          className="glass rounded-xl p-6 w-full max-w-md max-w-[calc(100%-2rem)]"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="text-center mb-6">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green-500/20 flex items-center justify-center">
              <Check className="w-8 h-8 text-green-400" />
            </div>
            <h3 className="text-lg font-semibold text-white">Приглашение создано!</h3>
            <p className="text-sm text-white/60 mt-1">Отправьте ссылку новому участнику</p>
          </div>

          {/* Invite Link */}
          <div className="mb-6">
            <label className="block text-sm text-white/60 mb-2">Ссылка для приглашения</label>
            <div className="flex items-center gap-2 p-3 glass-light rounded-lg">
              <input
                type="text"
                value={inviteUrl}
                readOnly
                className="flex-1 bg-transparent text-white text-sm truncate border-none outline-none"
              />
              <button
                onClick={copyLink}
                className="p-2 rounded-lg hover:bg-white/10 text-cyan-400 transition-colors flex items-center gap-2"
              >
                {copied ? <Check size={18} /> : <Copy size={18} />}
                <span className="text-sm">{copied ? 'Скопировано' : 'Копировать'}</span>
              </button>
            </div>
          </div>

          {createdInvitation.expires_at && (
            <p className="text-xs text-white/40 text-center mb-4 flex items-center justify-center gap-1">
              <Clock size={12} />
              Действует до: {new Date(createdInvitation.expires_at).toLocaleDateString('ru-RU')}
            </p>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => {
                setCreatedInvitation(null);
                setName('');
                setEmail('');
                setSelectedDepartments([]);
              }}
              className="flex-1 py-2.5 glass-light text-white rounded-lg hover:bg-white/10 transition-colors"
            >
              Создать ещё
            </button>
            <button
              onClick={() => {
                onSuccess();
              }}
              className="flex-1 py-2.5 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 transition-colors"
            >
              Готово
            </button>
          </div>
        </motion.div>
      </motion.div>
    );
  }

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
        className="glass rounded-xl p-6 w-full max-w-md max-w-[calc(100%-2rem)] max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6 flex-shrink-0">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <LinkIcon className="text-cyan-400" size={20} />
            Создать приглашение
          </h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-white/60">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto flex-1">
          <div>
            <label className="block text-sm text-white/60 mb-1">Имя (необязательно)</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Иван Иванов"
              className="w-full px-4 py-2 glass-light rounded-lg text-white placeholder-white/40"
            />
            <p className="text-xs text-white/30 mt-1">Будет предзаполнено в форме регистрации</p>
          </div>

          <div>
            <label className="block text-sm text-white/60 mb-1">Email (необязательно)</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@company.com"
              className="w-full px-4 py-2 glass-light rounded-lg text-white placeholder-white/40"
            />
          </div>

          {canSetRole && (
            <div>
              <label className="block text-sm text-white/60 mb-1">Роль</label>
              <div className="grid grid-cols-2 gap-2">
                {(['admin', 'hr', 'member'] as OrgRole[]).map((r) => {
                  const config = ORG_ROLE_CONFIG[r];
                  const Icon = config.icon;
                  return (
                    <button
                      key={r}
                      type="button"
                      onClick={() => setRole(r)}
                      className={clsx(
                        'p-3 rounded-lg border transition-colors text-left',
                        role === r
                          ? 'bg-cyan-500/20 border-cyan-500/50'
                          : 'glass-light border-white/10 hover:bg-white/10'
                      )}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Icon size={16} className={role === r ? 'text-cyan-400' : 'text-white/60'} />
                        <span className={role === r ? 'text-cyan-400' : 'text-white'}>{config.label}</span>
                      </div>
                      <p className="text-xs text-white/40">{config.description}</p>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Department Selection */}
          {departments.length > 0 && (
            <div className="flex-shrink-0">
              <label className="block text-sm text-white/60 mb-2">Департаменты</label>
              <div className="max-h-40 overflow-y-auto space-y-1.5 mb-2">
                {departments.map((dept) => {
                  const selected = selectedDepartments.find(d => d.id === dept.id);
                  return (
                    <div
                      key={dept.id}
                      className={clsx(
                        'flex items-center gap-3 p-2.5 rounded-lg transition-colors',
                        selected
                          ? 'bg-cyan-500/20 border border-cyan-500/50'
                          : 'glass-light border border-transparent hover:bg-white/10'
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={!!selected}
                        onChange={() => toggleDepartment(dept.id)}
                        className="w-4 h-4 rounded border-white/20 glass-light text-cyan-500 focus:ring-cyan-500"
                      />
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: dept.color || '#06b6d4' }}
                      />
                      <span className="text-white text-sm flex-1">{dept.name}</span>
                      {/* Owner/superadmin can set department role */}
                      {selected && isOwner && (
                        <select
                          value={selected.role}
                          onChange={(e) => setDepartmentRole(dept.id, e.target.value as DeptRole)}
                          onClick={(e) => e.stopPropagation()}
                          className="px-2 py-0.5 glass-light rounded text-white text-xs"
                        >
                          <option value="member">Участник</option>
                          <option value="sub_admin">Саб-админ</option>
                          <option value="lead">Руководитель</option>
                        </select>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Expiration */}
          <div>
            <label className="block text-sm text-white/60 mb-1">Срок действия</label>
            <select
              value={expiresInDays}
              onChange={(e) => setExpiresInDays(Number(e.target.value))}
              className="w-full px-4 py-2 glass-light rounded-lg text-white"
            >
              <option value={1}>1 день</option>
              <option value={3}>3 дня</option>
              <option value={7}>7 дней</option>
              <option value={14}>14 дней</option>
              <option value={30}>30 дней</option>
              <option value={0}>Без ограничения</option>
            </select>
          </div>

          <div className="flex-shrink-0 pt-4">
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <LinkIcon size={18} />}
            Создать приглашение
          </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}

// System Users Component (for superadmin)
function SystemUsers({ currentUser }: { currentUser: any }) {
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [newUser, setNewUser] = useState({ email: '', password: '', name: '', role: 'member' });
  const [selectedDeptId, setSelectedDeptId] = useState<number | ''>('');
  const [selectedDeptRole, setSelectedDeptRole] = useState('member');
  const [deptsList, setDeptsList] = useState<{id: number; name: string}[]>([]);

  // Load departments
  useEffect(() => {
    getDepartments().then((d: any[]) => setDeptsList(d.map(x => ({id: x.id, name: x.name})))).catch(() => {});
  }, []);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [passwordResetResult, setPasswordResetResult] = useState<{ email: string; password: string } | null>(null);
  const [copiedPassword, setCopiedPassword] = useState(false);
  const queryClient = useQueryClient();

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: getUsers,
    enabled: currentUser?.role === 'superadmin',
    staleTime: 30000, // Consider data stale after 30 seconds
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const user = await createUser(newUser);
      // Add to department if selected
      if (selectedDeptId && user?.id) {
        try {
          await addDepartmentMember(Number(selectedDeptId), { user_id: user.id, role: selectedDeptRole as any });
        } catch (e) {
          console.error('Failed to add to department:', e);
        }
      }
      // Update telegram_username if provided
      const tgUsername = (newUser as any).telegram_username;
      if (tgUsername && user?.id) {
        try {
          await adminUpdateUser(user.id, { telegram_username: tgUsername.replace('@', '') });
        } catch (e) {
          console.error('Failed to set telegram_username:', e);
        }
      }
      return user;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setIsDialogOpen(false);
      setNewUser({ email: '', password: '', name: '', role: 'member' });
      setSelectedDeptId('');
      setSelectedDeptRole('member');
      toast.success('Пользователь создан');
    },
    onError: (error: any) => {
      toast.error(getErrorDetail(error, 'Ошибка создания'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.success('Пользователь удалён');
    },
    onError: (error: any) => {
      toast.error(getErrorDetail(error, 'Ошибка удаления'));
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: (userId: number) => adminResetPassword(userId),
    onSuccess: (data) => {
      setPasswordResetResult({ email: data.user_email, password: data.temporary_password });
      toast.success('Пароль сброшен');
    },
    onError: (error: any) => {
      toast.error(getErrorDetail(error, 'Ошибка сброса пароля'));
    },
  });

  if (currentUser?.role !== 'superadmin') {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="text-center py-12"
      >
        <Shield className="w-16 h-16 mx-auto text-white/20 mb-4" />
        <h2 className="text-xl font-semibold mb-2 text-white/60">Доступ ограничен</h2>
        <p className="text-white/40">Только суперадмины могут управлять системными пользователями</p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <p className="text-white/60">Системные пользователи ({users.length})</p>
        <div className="flex items-center gap-2">
          <button
            onClick={async () => {
              if (!confirm('Очистить висящие расшаривания чатов/звонков?\n\nЭто удалит shares для чатов/звонков, у которых нет активного share на контакт.')) return;
              try {
                const token = localStorage.getItem('token');
                // First dry run
                const dryRes = await fetch('/api/sharing/cleanup/orphaned', {
                  method: 'DELETE',
                  headers: { 'Authorization': `Bearer ${token}` }
                });
                const dryData = await dryRes.json();

                if (dryData.orphaned_chat_shares === 0 && dryData.orphaned_call_shares === 0) {
                  toast.success('Нет висящих расшариваний');
                  return;
                }

                if (!confirm(`Найдено:\n- Чатов: ${dryData.orphaned_chat_shares}\n- Звонков: ${dryData.orphaned_call_shares}\n\nУдалить?`)) return;

                // Actually delete
                const res = await fetch('/api/sharing/cleanup/orphaned?dry_run=false', {
                  method: 'DELETE',
                  headers: { 'Authorization': `Bearer ${token}` }
                });
                const data = await res.json();
                toast.success(`Удалено: ${data.deleted?.chats || 0} чатов, ${data.deleted?.calls || 0} звонков`);
              } catch (e) {
                toast.error('Ошибка очистки');
              }
            }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-orange-500/20 text-orange-400 hover:bg-orange-500/30 text-sm"
          >
            <Sparkles className="w-4 h-4" />
            Cleanup
          </button>
          <Dialog.Root open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <Dialog.Trigger asChild>
              <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500 text-white hover:bg-cyan-600">
                <Plus className="w-5 h-5" />
                Создать
              </button>
            </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
            <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md max-w-[calc(100%-2rem)] max-h-[90vh] overflow-y-auto glass rounded-2xl p-6 shadow-xl z-50">
              <Dialog.Title className="text-xl font-semibold mb-4">
                Создать пользователя
              </Dialog.Title>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  createMutation.mutate();
                }}
                className="space-y-4"
              >
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Имя</label>
                  <input
                    type="text"
                    value={newUser.name}
                    onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
                    required
                    className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                  />
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Email</label>
                  <input
                    type="email"
                    value={newUser.email}
                    onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                    required
                    className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                  />
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Пароль</label>
                  <input
                    type="password"
                    value={newUser.password}
                    onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                    required
                    className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                  />
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Системная роль</label>
                  <select
                    value={newUser.role}
                    onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                    className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                  >
                    <option value="member">Сотрудник</option>
                    <option value="admin">Админ</option>
                    <option value="superadmin">Суперадмин</option>
                  </select>
                </div>
                {deptsList.length > 0 && (
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Отдел</label>
                    <select
                      value={selectedDeptId}
                      onChange={(e) => setSelectedDeptId(e.target.value ? Number(e.target.value) : '')}
                      className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                    >
                      <option value="">Без отдела</option>
                      {deptsList.map(d => (
                        <option key={d.id} value={d.id}>{d.name}</option>
                      ))}
                    </select>
                  </div>
                )}
                {selectedDeptId && (
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Роль в отделе</label>
                    <select
                      value={selectedDeptRole}
                      onChange={(e) => setSelectedDeptRole(e.target.value)}
                      className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                    >
                      <option value="member">Участник</option>
                      <option value="lead">Лид отдела</option>
                      <option value="sub_admin">Зам. лида</option>
                    </select>
                  </div>
                )}
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Telegram username</label>
                  <input
                    type="text"
                    value={(newUser as any).telegram_username || ''}
                    onChange={(e) => setNewUser({ ...newUser, telegram_username: e.target.value } as any)}
                    placeholder="@username"
                    className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                  />
                </div>
                <div className="flex gap-3 pt-4">
                  <Dialog.Close asChild>
                    <button type="button" className="flex-1 py-2.5 rounded-xl glass-light hover:bg-white/10 transition-colors">
                      Отмена
                    </button>
                  </Dialog.Close>
                  <button
                    type="submit"
                    disabled={createMutation.isPending}
                    className="flex-1 py-2.5 rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 transition-colors"
                  >
                    {createMutation.isPending ? 'Создание...' : 'Создать'}
                  </button>
                </div>
              </form>
              <Dialog.Close asChild>
                <button className="absolute top-4 right-4 p-2 rounded-lg hover:bg-dark-800/50 text-dark-400">
                  <X className="w-5 h-5" />
                </button>
              </Dialog.Close>
            </Dialog.Content>
          </Dialog.Portal>
          </Dialog.Root>
        </div>
      </div>

      {/* Users List */}
      <div className="glass-light rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
          </div>
        ) : users.length === 0 ? (
          <div className="text-center py-8">
            <Users className="w-12 h-12 mx-auto text-white/20 mb-3" />
            <p className="text-white/40">Нет пользователей</p>
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {users.map((user, index) => (
              <motion.div
                key={user.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className="flex items-center gap-4 p-4 hover:bg-dark-800/50 transition-colors"
              >
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
                  <span className="text-lg font-semibold text-cyan-400">
                    {user.name?.[0]?.toUpperCase() || 'U'}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-white truncate">{user.name}</h3>
                    <span
                      className={clsx(
                        'px-2 py-0.5 rounded-full text-xs font-medium',
                        user.role === 'superadmin'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-cyan-500/20 text-cyan-400'
                      )}
                    >
                      {user.role}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <p className="text-sm text-white/40 truncate">{user.email}</p>
                    {user.telegram_username ? (
                      <span className="flex items-center gap-1 text-xs text-green-400">
                        <MessageCircle size={12} />
                        @{user.telegram_username}
                      </span>
                    ) : (
                      <span className="text-xs text-white/25">Нет TG</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {user.id !== currentUser?.id && (
                    <button
                      onClick={() => setEditingUser(user)}
                      className="p-2 rounded-lg text-white/40 hover:text-cyan-400 hover:bg-cyan-500/10 transition-colors"
                      title="Редактировать"
                    >
                      <Pencil className="w-5 h-5" />
                    </button>
                  )}
                  {user.id !== currentUser?.id && (
                    <>
                      <button
                        onClick={() => {
                          if (confirm(`Сбросить пароль для ${user.email}?\n\nБудет сгенерирован временный пароль.`)) {
                            resetPasswordMutation.mutate(user.id);
                          }
                        }}
                        disabled={resetPasswordMutation.isPending}
                        className="p-2 rounded-lg text-white/40 hover:text-cyan-400 hover:bg-cyan-500/10 transition-colors disabled:opacity-50"
                        title="Сбросить пароль"
                      >
                        <Key className="w-5 h-5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm('Удалить пользователя?')) {
                            deleteMutation.mutate(user.id);
                          }
                        }}
                        className="p-2 rounded-lg text-white/40 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    </>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      {/* Password Reset Result Dialog */}
      <Dialog.Root open={!!passwordResetResult} onOpenChange={(open) => !open && setPasswordResetResult(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md glass rounded-2xl p-6 shadow-xl z-50">
            <Dialog.Title className="text-xl font-semibold mb-4 flex items-center gap-2">
              <Key className="text-cyan-400" />
              Пароль сброшен
            </Dialog.Title>
            {passwordResetResult && (
              <div className="space-y-4">
                <p className="text-dark-400 text-sm">
                  Временный пароль для <span className="text-dark-100 font-medium">{passwordResetResult.email}</span>:
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 glass-light rounded-lg py-3 px-4 text-cyan-400 font-mono text-lg">
                    {passwordResetResult.password}
                  </code>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(passwordResetResult.password);
                      setCopiedPassword(true);
                      setTimeout(() => setCopiedPassword(false), 2000);
                      toast.success('Пароль скопирован');
                    }}
                    className="p-3 rounded-lg glass-light hover:bg-white/10 transition-colors"
                  >
                    {copiedPassword ? <Check className="w-5 h-5 text-green-400" /> : <Copy className="w-5 h-5 text-dark-400" />}
                  </button>
                </div>
                <p className="text-yellow-400/80 text-sm bg-yellow-500/10 rounded-lg p-3">
                  ⚠️ Пользователь должен будет сменить пароль при следующем входе
                </p>
                <Dialog.Close asChild>
                  <button className="w-full py-2.5 rounded-xl bg-accent-500 text-white hover:bg-accent-600 transition-colors">
                    Закрыть
                  </button>
                </Dialog.Close>
              </div>
            )}
            <Dialog.Close asChild>
              <button className="absolute top-4 right-4 p-2 rounded-lg hover:bg-dark-800/50 text-dark-400">
                <X className="w-5 h-5" />
              </button>
            </Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Edit User Modal */}
      <AnimatePresence>
        {editingUser && (
          <EditUserModal
            user={editingUser}
            departments={deptsList}
            onClose={() => setEditingUser(null)}
            onSuccess={() => {
              setEditingUser(null);
              queryClient.invalidateQueries({ queryKey: ['users'] });
            }}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// Edit User Modal
function EditUserModal({
  user,
  departments,
  onClose,
  onSuccess,
}: {
  user: User;
  departments: { id: number; name: string }[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const currentUser = useAuthStore((s) => s.user);
  const isSuperAdmin = currentUser?.role === 'superadmin';

  const [name, setName] = useState(user.name || '');
  const [email, setEmail] = useState(user.email || '');
  const [role, setRole] = useState<string>(user.role || 'member');
  const [orgRole, setOrgRole] = useState<string>('');
  const [deptRole, setDeptRole] = useState<string>('');
  const [telegramUsername, setTelegramUsername] = useState(user.telegram_username || '');
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [saving, setSaving] = useState(false);
  // Скоуп наблюдателя по воронкам (01.10.2026, запрос Марии): «мы им нанимаем в
  // трафик, значит доступ только к трафику». Пусто = ограничения нет.
  const [scopeIds, setScopeIds] = useState<number[]>(user.scope_vacancy_ids || []);
  const [vacancies, setVacancies] = useState<{ id: number; title: string }[]>([]);
  const isObserver = orgRole === 'observer' || (!orgRole && !!user.is_readonly);

  useEffect(() => {
    if (!isObserver || vacancies.length) return;
    getVacancies()
      .then((list) => setVacancies(list.map((v) => ({ id: v.id, title: v.title }))))
      .catch(() => setVacancies([]));
  }, [isObserver, vacancies.length]);

  // Try to determine the user's current department from departments list
  // The user object doesn't carry department_id directly, so we leave it as ''
  // unless we can infer it. The admin can set/change it here.

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      if (name.trim() !== (user.name || '')) payload.name = name.trim();
      if (email.trim() !== (user.email || '')) payload.email = email.trim();
      if (role !== user.role) payload.role = role;

      // Normalize telegram username
      const normalizedTg = telegramUsername.trim().replace(/^@/, '').toLowerCase() || null;
      const currentTg = user.telegram_username || null;
      if (normalizedTg !== currentTg) payload.telegram_username = normalizedTg;

      if (departmentId) payload.department_id = departmentId;
      if (orgRole) payload.org_role = orgRole;
      const prevScope = [...(user.scope_vacancy_ids || [])].sort().join(',');
      if (isObserver && scopeIds.slice().sort().join(',') !== prevScope) {
        payload.scope_vacancy_ids = scopeIds;
      }
      if (deptRole) payload.dept_role = deptRole;

      if (Object.keys(payload).length === 0) {
        onClose();
        return;
      }

      await adminUpdateUser(user.id, payload as any);
      toast.success('Пользователь обновлён');
      onSuccess();
    } catch (err: any) {
      toast.error(getErrorDetail(err, 'Ошибка обновления'));
    } finally {
      setSaving(false);
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
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="glass rounded-2xl p-6 w-full max-w-md max-w-[calc(100%-2rem)] max-h-[90vh] overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Pencil className="text-cyan-400" size={20} />
            Редактировать пользователя
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-white/10 text-white/40 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-dark-400 mb-1">Имя</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
            />
          </div>

          {isSuperAdmin && (
            <div>
              <label className="block text-sm text-dark-400 mb-1">
                Системная роль <span className="text-xs text-white/30">(только для superadmin)</span>
              </label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
              >
                <option value="member">Сотрудник</option>
                <option value="superadmin">Суперадмин</option>
              </select>
            </div>
          )}

          <div>
            <label className="block text-sm text-dark-400 mb-1">Роль в организации (HR блок)</label>
            <select
              value={orgRole}
              onChange={(e) => setOrgRole(e.target.value)}
              className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
            >
              <option value="">Не менять</option>
              <option value="admin">HR Админ</option>
              <option value="hr">HR Рекрутер</option>
              <option value="member">Сотрудник (не HR)</option>
              <option value="observer">Наблюдатель (только чтение)</option>
            </select>
            <p className="text-xs text-white/30 mt-1">
              Определяет доступ к HR-фичам (кандидаты/вакансии/созвоны).
              «Наблюдатель» — видит всё как админ, но ничего не может менять.
            </p>
          </div>

          {/* Воронки наблюдателя. Пока не отмечено ничего — он видит весь пул,
              как раньше; отмеченные воронки сужают видимость и в списке
              кандидатов, и в поиске, и по прямой ссылке на карточку. */}
          {isObserver && (
            <div>
              <label className="block text-sm text-dark-400 mb-1">Какие воронки видит</label>
              <div className="max-h-44 overflow-y-auto rounded-xl glass-light p-2 space-y-1">
                {vacancies.length === 0 ? (
                  <p className="text-xs text-white/30 px-2 py-1">Вакансий нет</p>
                ) : (
                  vacancies.map((v) => {
                    const checked = scopeIds.includes(v.id);
                    return (
                      <label
                        key={v.id}
                        className="flex items-center gap-2 px-2 py-1 rounded-lg cursor-pointer hover:bg-white/5"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() =>
                            setScopeIds((prev) =>
                              checked ? prev.filter((id) => id !== v.id) : [...prev, v.id],
                            )
                          }
                        />
                        <span className="text-sm text-white/80 truncate">{v.title}</span>
                      </label>
                    );
                  })
                )}
              </div>
              <p className="text-xs text-white/30 mt-1">
                {scopeIds.length === 0
                  ? 'Ничего не отмечено — видит всех кандидатов организации.'
                  : `Видит только кандидатов этих воронок (${scopeIds.length}), остальные не откроются даже по ссылке.`}
              </p>
            </div>
          )}

          {departments.length > 0 && (
            <>
              <div>
                <label className="block text-sm text-dark-400 mb-1">Отдел (Dev блок)</label>
                <select
                  value={departmentId}
                  onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : '')}
                  className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                >
                  <option value="">Не менять</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm text-dark-400 mb-1">Роль в отделе</label>
                <select
                  value={deptRole}
                  onChange={(e) => setDeptRole(e.target.value)}
                  className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
                >
                  <option value="">Не менять</option>
                  <option value="lead">Lead (руководитель)</option>
                  <option value="sub_admin">Sub-admin</option>
                  <option value="member">Разработчик / участник</option>
                </select>
                <p className="text-xs text-white/30 mt-1">Для разработчиков: отдел «Разработка» + роль «member»; тимлида — «lead»</p>
              </div>
            </>
          )}

          <div>
            <label className="block text-sm text-dark-400 mb-1">Telegram</label>
            <input
              type="text"
              value={telegramUsername}
              onChange={(e) => setTelegramUsername(e.target.value)}
              placeholder="@username"
              className="w-full glass-light rounded-xl py-2.5 px-4 focus:outline-none focus:ring-2 focus:ring-accent-500/50"
            />
            <p className="text-xs text-white/30 mt-1">Юзернейм без @, например: Vova_Danilkovich</p>
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 rounded-xl glass-light hover:bg-white/10 transition-colors"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 py-2.5 rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}
