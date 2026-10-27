import api from '@/services/api/client';
import type { DocTemplate, SignedDoc } from './types';

export const listTemplates = () =>
  api.get<DocTemplate[]>('/documents/templates').then((r) => r.data);

export const createTemplate = (b: { name: string; content: string; variables?: string[] }) =>
  api.post<DocTemplate>('/documents/templates', b).then((r) => r.data);

export const updateTemplate = (id: number, b: Partial<DocTemplate>) =>
  api.put<DocTemplate>(`/documents/templates/${id}`, b).then((r) => r.data);

export const deleteTemplate = (id: number) =>
  api.delete(`/documents/templates/${id}`).then((r) => r.data);

export const generateDoc = (template_id: number, employee_id: number) =>
  api.post<SignedDoc>('/documents/generate', { template_id, employee_id }).then((r) => r.data);

export const myDocuments = () =>
  api.get<SignedDoc[]>('/documents/my').then((r) => r.data);

export const getDocument = (id: number) =>
  api.get<SignedDoc>(`/documents/${id}`).then((r) => r.data);

export const signDocument = (id: number, signature_data: string) =>
  api.post<SignedDoc>(`/documents/${id}/sign`, { signature_data }).then((r) => r.data);

export const employeeDocuments = (employeeId: number) =>
  api.get<SignedDoc[]>(`/documents/employee/${employeeId}`).then((r) => r.data);
