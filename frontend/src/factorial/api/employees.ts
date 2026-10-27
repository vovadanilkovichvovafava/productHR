import api from '@/services/api/client';
import type { Employee, EmployeeDocument, LeaveBalance, LeaveRequest, Reminder, BulkImportResult } from './types';

export const listEmployees = (activeOnly = true) =>
  api.get<Employee[]>(`/employees?active_only=${activeOnly}`).then((r) => r.data);

export const getMyProfile = () =>
  api.get<Employee>('/employees/me').then((r) => r.data);

export const getEmployee = (id: number) =>
  api.get<Employee>(`/employees/${id}`).then((r) => r.data);

export const createEmployee = (body: Partial<Employee> & { user_id: number }) =>
  api.post<Employee>('/employees', body).then((r) => r.data);

export const updateEmployee = (id: number, body: Partial<Employee>) =>
  api.put<Employee>(`/employees/${id}`, body).then((r) => r.data);

// Сотрудник правит СВОЙ профиль (личный кабинет) — PUT /employees/me.
export const updateMyProfile = (body: Partial<Employee>) =>
  api.put<Employee>('/employees/me', body).then((r) => r.data);

// Сгенерировать сотруднику новый временный пароль (показывается один раз). Доступ
// выдаётся здесь, а не при «Взять в штат», — когда сотрудник реально выходит.
export const resetEmployeePassword = (id: number) =>
  api.post<{ temporary_password: string }>(`/employees/${id}/reset-password`).then((r) => r.data);

export const dismissEmployee = (id: number, reason?: string) =>
  api
    .delete(`/employees/${id}${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`)
    .then((r) => r.data);

export const getLeaveBalance = (id: number) =>
  api.get<LeaveBalance>(`/employees/${id}/leave-balance`).then((r) => r.data);

export const createLeaveRequest = (
  id: number,
  body: { type: string; start_date: string; end_date: string; days: number; reason?: string },
) => api.post<LeaveRequest>(`/employees/${id}/leave-request`, body).then((r) => r.data);

export const listLeaveRequests = (status?: string) =>
  api
    .get<LeaveRequest[]>(`/employees/leave-requests${status ? `?status_filter=${status}` : ''}`)
    .then((r) => r.data);

export const approveLeave = (rid: number) =>
  api.put(`/employees/leave-requests/${rid}/approve`).then((r) => r.data);

export const rejectLeave = (rid: number) =>
  api.put(`/employees/leave-requests/${rid}/reject`).then((r) => r.data);

export const getReminders = () =>
  api.get<Reminder[]>('/employees/reminders').then((r) => r.data);

export const uploadMyPassport = (filename: string, content_type: string, data_base64: string) =>
  api.post('/employees/me/passport', { filename, content_type, data_base64 }).then((r) => r.data);

export const getMyPassport = () =>
  api.get<{ filename: string; content_type: string; data_base64: string }>('/employees/me/passport').then((r) => r.data);

// Скан паспорта сотрудника — для HR/руководителя (бэкенд проверяет доступ: self/HR/руководитель).
export const getEmployeePassport = (id: number) =>
  api.get<{ filename: string; content_type: string; data_base64: string }>(`/employees/${id}/passport`).then((r) => r.data);

export const listEmployeeDocuments = (id: number) =>
  api.get<EmployeeDocument[]>(`/employees/${id}/documents`).then((r) => r.data);

export const uploadEmployeeDocument = (id: number, file: File) => {
  const fd = new FormData();
  fd.append('file', file);
  return api.post(`/employees/${id}/documents`, fd).then((r) => r.data);
};

export const downloadEmployeeDocument = (id: number, docId: number) =>
  api.get<{ filename: string; content_type: string | null; data_base64: string }>(`/employees/${id}/documents/${docId}`).then((r) => r.data);

export const deleteEmployeeDocument = (id: number, docId: number) =>
  api.delete(`/employees/${id}/documents/${docId}`).then((r) => r.data);

export const bulkImportEmployees = (rows: Record<string, unknown>[]) =>
  api.post<BulkImportResult>('/employees/bulk-import', rows).then((r) => r.data);

export const downloadEmployeeTemplate = async (params?: { filled?: boolean; id?: number }) => {
  const qs = params?.id != null ? `?id=${params.id}` : params?.filled ? '?filled=1' : '';
  const res = await api.get(`/employees/import-template${qs}`, { responseType: 'blob' });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = params?.id != null || params?.filled ? 'employees.xlsx' : 'template_employees.xlsx';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};
