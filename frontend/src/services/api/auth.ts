import type { User, AuthResponse, Session, RefreshTokenResponse } from '@/types';
import api, { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// AUTH API
// ============================================================

export const login = async (email: string, password: string): Promise<User> => {
  // Backend returns { access_token, token_type, user } (cookie is also set via Set-Cookie header)
  const { data } = await api.post('/auth/login', { email, password });
  return data.user;
};

export const register = async (email: string, password: string, name: string): Promise<AuthResponse> => {
  const { data } = await api.post('/auth/register', { email, password, name });
  return data;
};

export const getCurrentUser = async (): Promise<User> => {
  // Use deduplication for getCurrentUser as it's called frequently
  const { data } = await deduplicatedGet<User>('/auth/me');
  return data;
};

export interface TelegramLinkInfo {
  is_linked: boolean;
  telegram_id: number | null;
  telegram_username: string | null;
  bot_username: string | null;
  link_url: string | null;
}

export const getTelegramLinkInfo = async (): Promise<TelegramLinkInfo> => {
  const { data } = await api.get<TelegramLinkInfo>('/auth/telegram-link');
  return data;
};

export interface OrgStage {
  key: string;
  label: string;
  color: string;
}

export const getOrgStages = async (): Promise<{ stages: OrgStage[] }> => {
  const { data } = await api.get('/auth/org-stages');
  return data;
};

/**
 * Refresh the access token using the refresh token stored in httpOnly cookie.
 * This is called automatically by the interceptor on 401 errors.
 * @returns RefreshTokenResponse with success status
 */
export const refreshToken = async (): Promise<RefreshTokenResponse> => {
  const { data } = await api.post<RefreshTokenResponse>('/auth/refresh', {});
  return data;
};

/**
 * Logout from all devices by invalidating all refresh tokens.
 * This will force re-login on all devices.
 */
export const logoutAllDevices = async (): Promise<{ success: boolean; sessions_revoked: number }> => {
  const { data } = await api.post<{ success: boolean; sessions_revoked: number }>('/auth/logout-all', {});
  return data;
};

/**
 * Get all active sessions for the current user.
 * @returns List of active sessions with device info and last activity
 */
export const getSessions = async (): Promise<Session[]> => {
  const { data } = await deduplicatedGet<Session[]>('/auth/sessions');
  return data;
};

/**
 * Revoke a specific session by its ID.
 * @param sessionId - The ID of the session to revoke
 */
export const revokeSession = async (sessionId: string): Promise<{ success: boolean }> => {
  const { data } = await api.delete<{ success: boolean }>(`/auth/sessions/${sessionId}`);
  return data;
};

export const changePassword = async (currentPassword: string, newPassword: string): Promise<void> => {
  await api.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword
  });
};

// ============================================================
// USERS API
// ============================================================

export const getUsers = async (): Promise<User[]> => {
  const { data } = await deduplicatedGet<User[]>('/users');
  return data;
};

export const createUser = async (userData: { email: string; password: string; name: string; role: string }): Promise<User> => {
  const { data } = await debouncedMutation<User>('post', '/users', userData);
  return data;
};

export const deleteUser = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/users/${id}`);
};

export interface HandoverMatch {
  vacancy_id: number;
  title: string;
  status: string | null;
  candidates: number;
  /** Кто работает в этой воронке — по нему окно ищет «такую же у получателя». */
  participants: number[];
}

export interface HandoverSummary {
  funnels: {
    vacancy_id: number;
    title: string;
    status: string | null;
    candidates: number;
    /** Кто в ней работает: получателю из этого списка сливать незачем. */
    participants: number[];
    /** Воронки с тем же названием — куда можно влить кандидатов у получателя. */
    matches: HandoverMatch[];
  }[];
  pool_candidates: number;
}

/** Что можно передать от уходящего: его воронки + его остальные кандидаты. */
export const getHandoverSummary = async (fromUserId: number): Promise<HandoverSummary> => {
  const { data } = await api.get<HandoverSummary>(`/users/${fromUserId}/handover-summary`);
  return data;
};

export interface HandoverAssignment {
  vacancy_id: number;
  to_user_id: number;
  /** Влить в такую же воронку получателя, а не заводить ему вторую. */
  merge_into_vacancy_id?: number | null;
}

export interface ReassignSplitResult {
  success: boolean;
  vacancies: number;
  applications: number;
  candidates: number;
  merged: number;
  pool: number;
  /** user_id (строкой) → сколько кандидатов ему перейдёт. */
  per_recipient: Record<string, number>;
  merges: {
    vacancy_id: number;
    into_vacancy_id: number;
    into_title: string;
    to_user_id: number;
    /** Уже есть в воронке, куда вливаем: этап, который останется. */
    overlapping: { entity_id: number; name: string | null; stage: string | null }[];
  }[];
}

/** Передача дел уходящего: каждой воронке — свой получатель, остальные — отдельно.
 *  dryRun — только посчитать итог для окна, ничего не меняя. */
export const reassignSplit = async (
  fromUserId: number,
  assignments: HandoverAssignment[],
  poolToUserId?: number | null,
  dryRun = false,
): Promise<ReassignSplitResult> => {
  const body = {
    from_user_id: fromUserId, assignments,
    pool_to_user_id: poolToUserId ?? null, dry_run: dryRun,
  };
  if (dryRun) {
    // Итог пересчитывается на каждое изменение в окне — без «защиты от двойного
    // клика», иначе свежий запрос отбрасывался бы как повтор.
    const { data } = await api.post<ReassignSplitResult>('/users/reassign-split', body);
    return data;
  }
  const { data } = await debouncedMutation<ReassignSplitResult>('post', '/users/reassign-split', body);
  return data as ReassignSplitResult;
};

export interface AdminUserUpdate {
  name?: string;
  email?: string;
  role?: string;
  org_role?: string;
  dept_role?: string;
  telegram_username?: string | null;
  department_id?: number | null;
  is_active?: boolean;
}

export const adminUpdateUser = async (userId: number, data: AdminUserUpdate): Promise<User> => {
  const { data: user } = await api.patch(`/users/${userId}`, data);
  return user;
};

export interface PasswordResetResponse {
  message: string;
  temporary_password: string;
  user_email: string;
}

export const adminResetPassword = async (userId: number, newPassword?: string): Promise<PasswordResetResponse> => {
  const { data } = await api.post(`/admin/users/${userId}/reset-password`,
    newPassword ? { new_password: newPassword } : {}
  );
  return data;
};

export interface UserProfileUpdate {
  name?: string;
  telegram_username?: string;
  additional_emails?: string[];
  additional_telegram_usernames?: string[];
}

export const updateUserProfile = async (data: UserProfileUpdate): Promise<User> => {
  const { data: user } = await api.patch('/users/me/profile', data);
  return user;
};

// ============================================================
// ORGANIZATIONS API
// ============================================================

export type OrgRole = 'owner' | 'admin' | 'hr' | 'member';

export interface Organization {
  id: number;
  name: string;
  slug: string;
  members_count: number;
  my_role?: OrgRole;
}

export interface OrgMember {
  id: number;
  user_id: number;
  user_name: string;
  user_email: string;
  role: OrgRole;
  has_full_access: boolean;  // Full database access (can see all vacancies/candidates)
  invited_by_name?: string;
  created_at: string;
  custom_role_id?: number;
  custom_role_name?: string;
  // Department info
  department_id?: number;
  department_name?: string;
  department_role?: DeptRole;
}

export type DeptRole = 'lead' | 'sub_admin' | 'member';

export interface InviteMemberRequest {
  email: string;
  name: string;
  password: string;
  role?: OrgRole;
  department_ids?: number[];
  department_role?: DeptRole;
}

export const getCurrentOrganization = async (): Promise<Organization> => {
  const { data } = await deduplicatedGet<Organization>('/organizations/current');
  return data;
};

export const getOrgMembers = async (): Promise<OrgMember[]> => {
  const { data } = await deduplicatedGet<OrgMember[]>('/organizations/current/members');
  return data;
};

export const inviteMember = async (memberData: InviteMemberRequest): Promise<OrgMember> => {
  const { data } = await debouncedMutation<OrgMember>('post', '/organizations/current/members', memberData);
  return data;
};

export const updateMemberRole = async (userId: number, role: OrgRole): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>('patch', `/organizations/current/members/${userId}/role`, { role });
  return data;
};

export const toggleMemberFullAccess = async (userId: number, hasFullAccess: boolean): Promise<{ success: boolean; has_full_access: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean; has_full_access: boolean }>(
    'put',
    `/organizations/current/members/${userId}/full-access?has_full_access=${hasFullAccess}`
  );
  return data;
};

export const removeMember = async (userId: number): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>('delete', `/organizations/current/members/${userId}`);
  return data;
};

export const getMyOrgRole = async (): Promise<{ role: OrgRole }> => {
  const { data } = await deduplicatedGet<{ role: OrgRole }>('/organizations/current/my-role');
  return data;
};

// ============================================================
// INVITATIONS API
// ============================================================

export interface Invitation {
  id: number;
  token: string;
  email?: string;
  name?: string;
  org_role: OrgRole;
  department_ids: { id: number; role: DeptRole }[];
  invited_by_name?: string;
  expires_at?: string;
  used_at?: string;
  used_by_name?: string;
  created_at: string;
  invitation_url: string;
}

export interface InvitationValidation {
  valid: boolean;
  expired: boolean;
  used: boolean;
  email?: string;
  name?: string;
  org_name?: string;
  org_role: string;
}

export interface AcceptInvitationRequest {
  email: string;
  name: string;
  password: string;
}

export interface AcceptInvitationResponse {
  success: boolean;
  access_token: string;
  user_id: number;
  telegram_bind_url?: string;
}

export const createInvitation = async (inviteData: {
  email?: string;
  name?: string;
  org_role?: OrgRole;
  department_ids?: { id: number; role: DeptRole }[];
  expires_in_days?: number;
}): Promise<Invitation> => {
  const { data } = await debouncedMutation<Invitation>('post', '/invitations', inviteData);
  return data;
};

export const getInvitations = async (includeUsed: boolean = false): Promise<Invitation[]> => {
  const { data } = await deduplicatedGet<Invitation[]>('/invitations', { params: { include_used: includeUsed } });
  return data;
};

export const validateInvitation = async (token: string): Promise<InvitationValidation> => {
  const { data } = await deduplicatedGet<InvitationValidation>(`/invitations/validate/${token}`);
  return data;
};

export const acceptInvitation = async (token: string, acceptData: AcceptInvitationRequest): Promise<AcceptInvitationResponse> => {
  const { data } = await debouncedMutation<AcceptInvitationResponse>('post', `/invitations/accept/${token}`, acceptData);
  return data;
};

export const revokeInvitation = async (id: number): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>('delete', `/invitations/${id}`);
  return data;
};

// ============================================================
// DEPARTMENTS API
// ============================================================

export interface Department {
  id: number;
  name: string;
  description?: string;
  color?: string;
  is_active: boolean;
  parent_id?: number;
  parent_name?: string;
  members_count: number;
  entities_count: number;
  children_count: number;
  created_at: string;
}

export interface DepartmentMember {
  id: number;
  user_id: number;
  user_name: string;
  user_email: string;
  role: DeptRole;
  created_at: string;
}

export const getDepartments = async (parentId?: number | null): Promise<Department[]> => {
  const params: Record<string, string> = {};
  // parentId = undefined -> get top-level (default)
  // parentId = null -> same as undefined
  // parentId = -1 -> get all departments
  // parentId = number -> get children of that department
  if (parentId !== undefined && parentId !== null) {
    params.parent_id = String(parentId);
  }
  const { data } = await deduplicatedGet<Department[]>('/departments', { params });
  return data;
};

export const getDepartment = async (id: number): Promise<Department> => {
  const { data } = await deduplicatedGet<Department>(`/departments/${id}`);
  return data;
};

export const createDepartment = async (dept: {
  name: string;
  description?: string;
  color?: string;
  parent_id?: number;
}): Promise<Department> => {
  const { data } = await debouncedMutation<Department>('post', '/departments', dept);
  return data;
};

export const updateDepartment = async (id: number, updates: {
  name?: string;
  description?: string;
  color?: string;
  is_active?: boolean;
}): Promise<Department> => {
  const { data } = await debouncedMutation<Department>('patch', `/departments/${id}`, updates);
  return data;
};

export const deleteDepartment = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/departments/${id}`);
};

export const getDepartmentMembers = async (departmentId: number): Promise<DepartmentMember[]> => {
  const { data } = await deduplicatedGet<DepartmentMember[]>(`/departments/${departmentId}/members`);
  return data;
};

export const addDepartmentMember = async (departmentId: number, memberData: {
  user_id: number;
  role?: DeptRole;
}): Promise<DepartmentMember> => {
  const { data } = await debouncedMutation<DepartmentMember>('post', `/departments/${departmentId}/members`, memberData);
  return data;
};

export const updateDepartmentMember = async (departmentId: number, userId: number, role: DeptRole): Promise<DepartmentMember> => {
  const { data } = await debouncedMutation<DepartmentMember>('patch', `/departments/${departmentId}/members/${userId}`, { role });
  return data;
};

export const removeDepartmentMember = async (departmentId: number, userId: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/departments/${departmentId}/members/${userId}`);
};

export interface QuickAddMemberResult {
  user_id: number;
  name: string;
  email: string;
  password_generated: string | null;
  already_existed: boolean;
}

export const quickAddDepartmentMember = async (
  departmentId: number,
  memberData: { name: string; email: string; role: string; telegram_username?: string }
): Promise<QuickAddMemberResult> => {
  const { data } = await debouncedMutation<QuickAddMemberResult>(
    'post',
    `/departments/${departmentId}/quick-add-member`,
    memberData
  );
  return data;
};

export const getMyDepartments = async (): Promise<Department[]> => {
  const { data } = await deduplicatedGet<Department[]>('/departments/my/departments');
  return data;
};

export interface MyDeptRole {
  department_id: number;
  department_name: string;
  role: DeptRole;
}

export const getMyDeptRoles = async (): Promise<MyDeptRole[]> => {
  const { data } = await deduplicatedGet<MyDeptRole[]>('/departments/my/roles');
  return data;
};

export const getMyManagedUserIds = async (): Promise<number[]> => {
  const { data } = await deduplicatedGet<number[]>('/departments/my/managed-users');
  return data;
};

// ============================================================
// CUSTOM ROLES API (Superadmin only)
// ============================================================

export interface CustomRole {
  id: number;
  name: string;
  description?: string;
  base_role: 'owner' | 'admin' | 'sub_admin' | 'member';
  org_id?: number;
  created_by?: number;
  created_at: string;
  is_active: boolean;
  permission_overrides?: PermissionOverride[];
}

export interface PermissionOverride {
  id: number;
  role_id: number;
  permission: string;
  allowed: boolean;
}

export interface PermissionAuditLog {
  id: number;
  changed_by?: number;
  role_id?: number;
  action: string;
  permission?: string;
  old_value?: boolean;
  new_value?: boolean;
  details?: Record<string, unknown>;
  created_at: string;
}

export const getCustomRoles = async (): Promise<CustomRole[]> => {
  const { data } = await deduplicatedGet<CustomRole[]>('/admin/custom-roles');
  return data;
};

export const getCustomRole = async (id: number): Promise<CustomRole> => {
  const { data } = await deduplicatedGet<CustomRole>(`/admin/custom-roles/${id}`);
  return data;
};

export const createCustomRole = async (roleData: {
  name: string;
  description?: string;
  base_role: string;
  org_id?: number;
}): Promise<CustomRole> => {
  const { data } = await debouncedMutation<CustomRole>('post', '/admin/custom-roles', roleData);
  return data;
};

export const updateCustomRole = async (id: number, updates: {
  name?: string;
  description?: string;
  is_active?: boolean;
}): Promise<CustomRole> => {
  const { data } = await debouncedMutation<CustomRole>('patch', `/admin/custom-roles/${id}`, updates);
  return data;
};

export const deleteCustomRole = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/admin/custom-roles/${id}`);
};

export const setRolePermission = async (roleId: number, permission: string, allowed: boolean): Promise<PermissionOverride> => {
  const { data } = await debouncedMutation<PermissionOverride>('post', `/admin/custom-roles/${roleId}/permissions`, { permission, allowed });
  return data;
};

export const removeRolePermission = async (roleId: number, permission: string): Promise<void> => {
  await debouncedMutation<void>('delete', `/admin/custom-roles/${roleId}/permissions/${permission}`);
};

export const assignCustomRole = async (roleId: number, userId: number): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>('post', `/admin/custom-roles/${roleId}/assign/${userId}`);
  return data;
};

export const unassignCustomRole = async (roleId: number, userId: number): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>('delete', `/admin/custom-roles/${roleId}/assign/${userId}`);
  return data;
};

export const getPermissionAuditLogs = async (params?: {
  role_id?: number;
  limit?: number;
  offset?: number;
}): Promise<PermissionAuditLog[]> => {
  const { data } = await deduplicatedGet<PermissionAuditLog[]>('/admin/permission-audit-logs', { params });
  return data;
};

// ============================================================
// USER EFFECTIVE PERMISSIONS API
// ============================================================

export interface EffectivePermissions {
  permissions: Record<string, boolean>;
  source: 'custom_role' | 'org_role' | 'default';
  custom_role_id: number | null;
  custom_role_name: string | null;
  base_role: string;
}

export interface MenuItem {
  id: string;
  label: string;
  path: string;
  icon: string;
  required_permission?: string;
  required_feature?: string;
  superadmin_only: boolean;
}

export interface MenuConfig {
  items: MenuItem[];
}

export interface UserFeatures {
  features: string[];
}

export const getMyPermissions = async (): Promise<EffectivePermissions> => {
  const { data } = await deduplicatedGet<EffectivePermissions>('/admin/me/permissions');
  return data;
};

export const getMyMenu = async (): Promise<MenuConfig> => {
  const { data } = await deduplicatedGet<MenuConfig>('/admin/me/menu');
  return data;
};

export const getMyFeatures = async (): Promise<UserFeatures> => {
  const { data } = await deduplicatedGet<UserFeatures>('/admin/me/features');
  return data;
};

// ============================================================
// SHARING API
// ============================================================

export type ResourceType = 'chat' | 'entity' | 'call' | 'vacancy';
export type AccessLevel = 'view' | 'edit' | 'full';

export interface ShareRequest {
  resource_type: ResourceType;
  resource_id: number;
  shared_with_id: number;
  access_level?: AccessLevel;
  note?: string;
  expires_at?: string;
}

export interface ShareResponse {
  id: number;
  resource_type: ResourceType;
  resource_id: number;
  resource_name?: string;
  shared_by_id: number;
  shared_by_name: string;
  shared_with_id: number;
  shared_with_name: string;
  access_level: AccessLevel;
  note?: string;
  expires_at?: string;
  created_at: string;
}

export interface UserSimple {
  id: number;
  name: string;
  email: string;
  org_role?: string;
  department_id?: number;
  department_name?: string;
  department_role?: string;
}

export const shareResource = async (shareData: ShareRequest): Promise<ShareResponse> => {
  const { data } = await debouncedMutation<ShareResponse>('post', '/sharing', shareData);
  return data;
};

export const revokeShare = async (shareId: number): Promise<{ success: boolean }> => {
  const { data } = await debouncedMutation<{ success: boolean }>('delete', `/sharing/${shareId}`);
  return data;
};

export const getMyShares = async (resourceType?: ResourceType): Promise<ShareResponse[]> => {
  const params = resourceType ? { resource_type: resourceType } : undefined;
  const { data } = await deduplicatedGet<ShareResponse[]>('/sharing/my-shares', { params });
  return data;
};

export const getSharedWithMe = async (resourceType?: ResourceType): Promise<ShareResponse[]> => {
  const params = resourceType ? { resource_type: resourceType } : undefined;
  const { data } = await deduplicatedGet<ShareResponse[]>('/sharing/shared-with-me', { params });
  return data;
};

export const getResourceShares = async (resourceType: ResourceType, resourceId: number): Promise<ShareResponse[]> => {
  const { data } = await deduplicatedGet<ShareResponse[]>(`/sharing/resource/${resourceType}/${resourceId}`);
  return data;
};

export const getSharableUsers = async (): Promise<UserSimple[]> => {
  const { data } = await deduplicatedGet<UserSimple[]>('/sharing/users');
  return data;
};

// Convenience methods for sharing
export const shareChat = async (
  chatId: number,
  userId: number,
  accessLevel: AccessLevel = 'view',
  note?: string
): Promise<ShareResponse> => {
  return shareResource({
    resource_type: 'chat',
    resource_id: chatId,
    shared_with_id: userId,
    access_level: accessLevel,
    note
  });
};

export const shareCall = async (
  callId: number,
  userId: number,
  accessLevel: AccessLevel = 'view',
  note?: string
): Promise<ShareResponse> => {
  return shareResource({
    resource_type: 'call',
    resource_id: callId,
    shared_with_id: userId,
    access_level: accessLevel,
    note
  });
};

export const shareEntity = async (
  entityId: number,
  userId: number,
  accessLevel: AccessLevel = 'view',
  note?: string
): Promise<ShareResponse> => {
  return shareResource({
    resource_type: 'entity',
    resource_id: entityId,
    shared_with_id: userId,
    access_level: accessLevel,
    note
  });
};

// ============================================================
// FEATURE ACCESS CONTROL API
// ============================================================

export interface FeatureSetting {
  id: number;
  feature_name: string;
  enabled: boolean;
  department_id: number | null;
  department_name: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface FeatureSettingsResponse {
  features: FeatureSetting[];
  available_features: string[];
  restricted_features: string[];
}

export interface UserFeaturesResponse {
  features: string[];
}

export interface SetFeatureAccessRequest {
  department_ids?: number[] | null;
  enabled: boolean;
}

export const getFeatureSettings = async (): Promise<FeatureSettingsResponse> => {
  const { data } = await deduplicatedGet<FeatureSettingsResponse>('/admin/features');
  return data;
};

export const setFeatureAccess = async (
  featureName: string,
  request: SetFeatureAccessRequest
): Promise<FeatureSettingsResponse> => {
  const { data } = await debouncedMutation<FeatureSettingsResponse>('put', `/admin/features/${featureName}`, request);
  return data;
};

export const deleteFeatureSetting = async (
  featureName: string,
  departmentId?: number | null
): Promise<{ success: boolean }> => {
  const params = departmentId !== undefined && departmentId !== null
    ? `?department_id=${departmentId}`
    : '';
  const { data } = await debouncedMutation<{ success: boolean }>('delete', `/admin/features/${featureName}${params}`);
  return data;
};

// Feature Audit Logs
export interface FeatureAuditLog {
  id: number;
  org_id: number;
  changed_by: number | null;
  changed_by_name: string | null;
  changed_by_email: string | null;
  feature_name: string;
  action: string;
  department_id: number | null;
  department_name: string | null;
  old_value: boolean | null;
  new_value: boolean | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export const getFeatureAuditLogs = async (params?: {
  feature_name?: string;
  limit?: number;
  offset?: number;
}): Promise<FeatureAuditLog[]> => {
  const { data } = await deduplicatedGet<FeatureAuditLog[]>('/admin/features/audit-logs', { params });
  return data;
};
