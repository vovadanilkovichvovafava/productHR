/**
 * Хаб доступов — каталог ресурсов, заявки, леджер, оффбординг.
 * Секреты (пароли/ключи/карты) здесь не ходят: только факт выдачи и статус.
 */
import api from './client';

export type AccessStatus = 'new' | 'in_progress' | 'granted' | 'rejected' | 'revoked';

export interface ResourceParam {
  key: string;
  label: string;
  type: string;
  required: boolean;
  options: string[];
}

export interface CatalogResource {
  id: number;
  key: string;
  name: string;
  category: string;
  description: string | null;
  responsible_user_id: number | null;
  responsible_name: string | null;
  params_schema: ResourceParam[];
  unlock_condition: string;
  limit_per_month: number | null;
  limit_amount_month: number | null;
  currency: string | null;
  /** доступен всем сотрудникам, без привязки к роли */
  available_to_all: boolean;
  is_active: boolean;
  /** только в /available */
  locked: boolean;
  lock_reason: string | null;
  used_this_month: number;
  /** состояние кнопки доступа: granted | pending | rejected | none */
  state: 'granted' | 'pending' | 'rejected' | 'none';
  last_request_id: number | null;
  /** параметры выданного доступа — показываем на кнопке («Выдан · US») */
  granted_params: Record<string, unknown>;
}

export interface AccessRequest {
  id: number;
  resource_id: number;
  resource_name: string;
  resource_category: string;
  requester_user_id: number;
  requester_name: string | null;
  target_user_id: number | null;
  target_name: string | null;
  /** «Снабжение» для заявителя — имя ответственного скрыто намеренно */
  assignee_display: string;
  assignee_user_id: number | null;
  params: Record<string, unknown>;
  comment: string | null;
  status: AccessStatus;
  amount: number | null;
  currency: string | null;
  decision_comment: string | null;
  decided_at: string | null;
  granted_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
  can_decide: boolean;
}

export interface AccessAudit {
  id: number;
  from_status: string | null;
  to_status: string;
  action: string;
  changed_by: number | null;
  changed_by_name: string | null;
  comment: string | null;
  created_at: string | null;
}

export interface Grant {
  request_id: number;
  resource_id: number;
  resource_name: string;
  resource_category: string;
  params: Record<string, unknown>;
  granted_at: string | null;
  responsible_user_id: number | null;
  status: string;
}

// ─── Каталог ────────────────────────────────────────────────

export async function getCatalog(includeInactive = false): Promise<CatalogResource[]> {
  const { data } = await api.get('/access-hub/catalog', { params: { include_inactive: includeInactive } });
  return data;
}

export async function createResource(payload: {
  key: string; name: string; category: string; description?: string | null;
  responsible_user_id?: number | null; params_schema?: ResourceParam[];
  unlock_condition?: string; limit_per_month?: number | null;
  limit_amount_month?: number | null; currency?: string | null;
  available_to_all?: boolean;
}): Promise<CatalogResource> {
  const { data } = await api.post('/access-hub/catalog', payload);
  return data;
}

export async function updateResource(
  id: number,
  payload: Partial<Omit<CatalogResource, 'id' | 'key' | 'locked' | 'lock_reason' | 'used_this_month'>>
): Promise<CatalogResource> {
  const { data } = await api.patch(`/access-hub/catalog/${id}`, payload);
  return data;
}

export async function getAvailableResources(): Promise<CatalogResource[]> {
  const { data } = await api.get('/access-hub/available');
  return data;
}

// ─── Роли ───────────────────────────────────────────────────

export async function getRoleResources(roleId: number): Promise<number[]> {
  const { data } = await api.get(`/access-hub/roles/${roleId}/resources`);
  return data;
}

export async function setRoleResources(roleId: number, resourceIds: number[]): Promise<number[]> {
  const { data } = await api.put(`/access-hub/roles/${roleId}/resources`, resourceIds);
  return data;
}

// ─── Заявки ─────────────────────────────────────────────────

export async function getRequests(
  scope: 'my' | 'assigned' | 'all' = 'my',
  status?: AccessStatus
): Promise<AccessRequest[]> {
  const { data } = await api.get('/access-hub/requests', { params: { scope, status } });
  return data;
}

export async function createRequest(payload: {
  resource_id: number;
  params?: Record<string, unknown>;
  comment?: string | null;
  amount?: number | null;
  target_user_id?: number | null;
}): Promise<AccessRequest> {
  const { data } = await api.post('/access-hub/requests', payload);
  return data;
}

export async function takeInProgress(id: number): Promise<AccessRequest> {
  const { data } = await api.post(`/access-hub/requests/${id}/progress`);
  return data;
}

export async function grantRequest(id: number, comment?: string, amount?: number): Promise<AccessRequest> {
  const { data } = await api.post(`/access-hub/requests/${id}/grant`, { comment, amount });
  return data;
}

export async function rejectRequest(id: number, comment?: string): Promise<AccessRequest> {
  const { data } = await api.post(`/access-hub/requests/${id}/reject`, { comment });
  return data;
}

export async function revokeGrant(id: number, comment?: string): Promise<AccessRequest> {
  const { data } = await api.post(`/access-hub/requests/${id}/revoke`, { comment });
  return data;
}

export async function getRequestAudit(id: number): Promise<AccessAudit[]> {
  const { data } = await api.get(`/access-hub/requests/${id}/audit`);
  return data;
}

// ─── Леджер и оффбординг ────────────────────────────────────

export async function getLedger(userId: number, activeOnly = true): Promise<Grant[]> {
  const { data } = await api.get(`/access-hub/ledger/${userId}`, { params: { active_only: activeOnly } });
  return data;
}

export async function getOffboardingChecklist(userId: number): Promise<Grant[]> {
  const { data } = await api.get(`/access-hub/offboarding/${userId}/checklist`);
  return data;
}

// ─── Справочники для конструктора ролей ─────────────────────
//
// Хаб не заводит свою ролевую модель: роли берутся те же, что уже есть в
// Энцеладусе (CustomRole / UserCustomRole), — иначе появились бы две
// несогласованные системы прав.

export interface CustomRoleBrief {
  id: number;
  name: string;
  description?: string | null;
  base_role: string;
  is_active?: boolean;
}

export interface OrgMemberBrief {
  user_id: number;
  user_name: string | null;
  user_email: string | null;
  /** роль в организации: owner | admin | member */
  role: string | null;
  custom_role_id: number | null;
  custom_role_name: string | null;
}

export async function getCustomRoles(): Promise<CustomRoleBrief[]> {
  const { data } = await api.get('/admin/custom-roles');
  return (data || []).filter((r: CustomRoleBrief) => r.is_active !== false);
}

export async function getOrgMembers(): Promise<OrgMemberBrief[]> {
  const { data } = await api.get('/organizations/current/members');
  return data || [];
}

// ─── Анонимный чат по заявке (ТЗ п. 3.5) ────────────────────

export interface AccessMessage {
  id: number;
  text: string;
  source: string;
  created_at: string | null;
  /** подпись автора; для заявителя ответственный — «Снабжение» */
  author: string;
  mine: boolean;
}

export async function getMessages(requestId: number): Promise<AccessMessage[]> {
  const { data } = await api.get(`/access-hub/requests/${requestId}/messages`);
  return data || [];
}

export async function sendMessage(requestId: number, text: string): Promise<AccessMessage> {
  const { data } = await api.post(`/access-hub/requests/${requestId}/messages`, { text });
  return data;
}
