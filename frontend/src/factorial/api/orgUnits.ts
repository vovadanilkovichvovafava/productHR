import api from '@/services/api/client';

export interface EmployeeMini { id: number; user_name?: string; position?: string; }
export interface PersonNode { id: number; user_name?: string; position?: string; manager_id: number | null; org_unit_id: number | null; hired_at?: string | null; }
export interface OrgUnitNode {
  id: number;
  name: string;
  parent_id: number | null;
  color?: string | null;
  sort_order: number;
  employees: EmployeeMini[];
}
export interface OrgChart { units: OrgUnitNode[]; unassigned: EmployeeMini[]; people: PersonNode[]; }

export const getOrgChart = () => api.get<OrgChart>('/org-units').then((r) => r.data);

export const createOrgUnit = (b: { name: string; parent_id?: number | null; color?: string }) =>
  api.post<OrgUnitNode>('/org-units', b).then((r) => r.data);

export const updateOrgUnit = (id: number, b: { name?: string; color?: string; sort_order?: number; parent_id?: number | null }) =>
  api.patch<OrgUnitNode>(`/org-units/${id}`, b).then((r) => r.data);

export const deleteOrgUnit = (id: number) =>
  api.delete(`/org-units/${id}`).then((r) => r.data);

export const assignEmployee = (employeeId: number, orgUnitId: number | null) =>
  api.put(`/org-units/assign/${employeeId}`, { org_unit_id: orgUnitId }).then((r) => r.data);

export const setManager = (employeeId: number, managerId: number | null) =>
  api.put(`/org-units/manager/${employeeId}`, { manager_id: managerId }).then((r) => r.data);
