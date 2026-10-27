/**
 * Employee Personal Cabinet, Leave Counter, and Auto-Reminders API
 */
import api from './client';

// ─── Types ──────────────────────────────────────────────────

export interface EmployeeData {
  id: number;
  user_id: number;
  org_id: number;
  entity_id: number | null;
  department_id: number | null;
  position: string | null;
  phone: string | null;
  telegram_username: string | null;
  practice_start_date: string | null;
  department_start_date: string | null;
  probation_end_date: string | null;
  one_year_date: string | null;
  vacation_days_total: number;
  vacation_days_used: number;
  sick_days_total: number;
  sick_days_used: number;
  family_leave_days_total: number;
  family_leave_days_used: number;
  nda_signed: boolean;
  nda_signed_at: string | null;
  contract_signed: boolean;
  contract_signed_at: string | null;
  is_active: boolean;
  dismissed_at: string | null;
  dismissal_reason: string | null;
  extra_data: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
  user_name: string | null;
  user_email: string | null;
  department_name: string | null;
}

export interface EmployeeCreate {
  user_id: number;
  entity_id?: number | null;
  department_id?: number | null;
  position?: string | null;
  phone?: string | null;
  telegram_username?: string | null;
  practice_start_date?: string | null;
  department_start_date?: string | null;
  nda_signed?: boolean;
  contract_signed?: boolean;
  extra_data?: Record<string, unknown> | null;
}

export interface EmployeeUpdate {
  department_id?: number | null;
  position?: string | null;
  phone?: string | null;
  telegram_username?: string | null;
  practice_start_date?: string | null;
  department_start_date?: string | null;
  nda_signed?: boolean;
  nda_signed_at?: string | null;
  contract_signed?: boolean;
  contract_signed_at?: string | null;
  vacation_days_total?: number;
  vacation_days_used?: number;
  sick_days_total?: number;
  sick_days_used?: number;
  family_leave_days_total?: number;
  family_leave_days_used?: number;
  extra_data?: Record<string, unknown> | null;
}

export interface LeaveBalance {
  vacation_total: number;
  vacation_used: number;
  vacation_remaining: number;
  sick_total: number;
  sick_used: number;
  sick_remaining: number;
  family_leave_total: number;
  family_leave_used: number;
  family_leave_remaining: number;
}

export interface LeaveRequestCreate {
  type: 'vacation' | 'sick' | 'family_leave' | 'bereavement';
  start_date: string;
  end_date: string;
  days: number;
  reason?: string | null;
}

export interface LeaveRequestData {
  id: number;
  employee_id: number;
  type: string;
  start_date: string;
  end_date: string;
  days: number;
  reason: string | null;
  status: string;
  approved_by: number | null;
  approved_at: string | null;
  created_at: string | null;
  employee_name: string | null;
}

export interface ReminderItem {
  employee_id: number;
  employee_name: string;
  type: 'probation_ending' | 'one_year_anniversary';
  date: string;
  days_remaining: number;
}

// ─── API functions ──────────────────────────────────────────

export async function getEmployees(activeOnly = true): Promise<EmployeeData[]> {
  const { data } = await api.get('/employees', { params: { active_only: activeOnly } });
  return data;
}

export async function getMyEmployeeProfile(): Promise<EmployeeData> {
  const { data } = await api.get('/employees/me');
  return data;
}

export async function getEmployee(id: number): Promise<EmployeeData> {
  const { data } = await api.get(`/api/employees/${id}`);
  return data;
}

export async function createEmployee(payload: EmployeeCreate): Promise<EmployeeData> {
  const { data } = await api.post('/employees', payload);
  return data;
}

export async function updateEmployee(id: number, payload: EmployeeUpdate): Promise<EmployeeData> {
  const { data } = await api.put(`/api/employees/${id}`, payload);
  return data;
}

export async function dismissEmployee(id: number, reason?: string): Promise<{ ok: boolean }> {
  const { data } = await api.delete(`/api/employees/${id}`, { params: { reason } });
  return data;
}

export async function getLeaveBalance(employeeId: number): Promise<LeaveBalance> {
  const { data } = await api.get(`/api/employees/${employeeId}/leave-balance`);
  return data;
}

export async function createLeaveRequest(employeeId: number, payload: LeaveRequestCreate): Promise<LeaveRequestData> {
  const { data } = await api.post(`/api/employees/${employeeId}/leave-request`, payload);
  return data;
}

export async function getAllLeaveRequests(statusFilter?: string): Promise<LeaveRequestData[]> {
  const { data } = await api.get('/employees/leave-requests', {
    params: statusFilter ? { status_filter: statusFilter } : undefined,
  });
  return data;
}

export async function approveLeaveRequest(requestId: number): Promise<{ ok: boolean }> {
  const { data } = await api.put(`/api/employees/leave-requests/${requestId}/approve`);
  return data;
}

export async function rejectLeaveRequest(requestId: number): Promise<{ ok: boolean }> {
  const { data } = await api.put(`/api/employees/leave-requests/${requestId}/reject`);
  return data;
}

export async function getEmployeeReminders(): Promise<ReminderItem[]> {
  const { data } = await api.get('/employees/reminders');
  return data;
}
