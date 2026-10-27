/**
 * Document Signing API — templates, generation, canvas signature
 */
import api from './client';

// ─── Types ──────────────────────────────────────────────────

export interface DocumentTemplate {
  id: number;
  org_id: number;
  name: string;
  content: string;
  variables: string[] | null;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface DocumentTemplateCreate {
  name: string;
  content: string;
  variables?: string[] | null;
}

export interface DocumentTemplateUpdate {
  name?: string;
  content?: string;
  variables?: string[] | null;
  is_active?: boolean;
}

export interface SignedDocument {
  id: number;
  template_id: number | null;
  employee_id: number;
  title: string;
  content_rendered: string;
  signature_data: string | null;
  signed_at: string | null;
  signer_ip: string | null;
  status: 'pending' | 'signed';
  created_at: string | null;
  employee_name: string | null;
}

export interface GenerateDocRequest {
  template_id: number;
  employee_id: number;
}

export interface SignDocRequest {
  signature_data: string;
}

// ─── API functions ──────────────────────────────────────────

// Templates (admin)

export async function getDocumentTemplates(): Promise<DocumentTemplate[]> {
  const { data } = await api.get('/documents/templates');
  return data;
}

export async function createDocumentTemplate(payload: DocumentTemplateCreate): Promise<DocumentTemplate> {
  const { data } = await api.post('/documents/templates', payload);
  return data;
}

export async function updateDocumentTemplate(id: number, payload: DocumentTemplateUpdate): Promise<DocumentTemplate> {
  const { data } = await api.put(`/documents/templates/${id}`, payload);
  return data;
}

export async function deleteDocumentTemplate(id: number): Promise<{ ok: boolean }> {
  const { data } = await api.delete(`/documents/templates/${id}`);
  return data;
}

// Documents

export async function generateDocument(payload: GenerateDocRequest): Promise<SignedDocument> {
  const { data } = await api.post('/documents/generate', payload);
  return data;
}

export async function getMyDocuments(): Promise<SignedDocument[]> {
  const { data } = await api.get('/documents/my');
  return data;
}

export async function getDocument(id: number): Promise<SignedDocument> {
  const { data } = await api.get(`/documents/${id}`);
  return data;
}

export async function signDocument(id: number, payload: SignDocRequest): Promise<SignedDocument> {
  const { data } = await api.post(`/documents/${id}/sign`, payload);
  return data;
}

export async function getEmployeeDocuments(employeeId: number): Promise<SignedDocument[]> {
  const { data } = await api.get(`/documents/employee/${employeeId}`);
  return data;
}
