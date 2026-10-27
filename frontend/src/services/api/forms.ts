/**
 * Form Constructor API — CRUD for form templates and public submission
 */
import api from './client';

// ============================================================
// Types
// ============================================================

export interface FormField {
  id: string;
  type: 'text' | 'email' | 'phone' | 'textarea' | 'select' | 'multiselect' | 'radio' | 'file' | 'url' | 'scale' | 'date';
  label: string;
  required: boolean;
  placeholder?: string;
  options?: string[];
  min?: number;   // для scale
  max?: number;   // для scale
}

export interface FormTemplate {
  id: number;
  title: string;
  description: string | null;
  slug: string;
  vacancy_id: number | null;
  vacancy_ids: number[];
  is_active: boolean;
  is_template: boolean;
  fields: FormField[];
  submissions_count: number;
  created_at: string | null;
  updated_at: string | null;
  created_by: number | null;
}


export interface PublicFormData {
  id: number;
  title: string;
  description: string | null;
  fields: FormField[];
  vacancy_title: string | null;
  already_submitted?: boolean;
  answers?: Record<string, unknown> | null;
  file_links?: Record<string, string>; // field_id → URL скачивания файла
}

export interface FormCreateData {
  title: string;
  description?: string;
  vacancy_id?: number | null;
  vacancy_ids?: number[];
  fields: FormField[];
  is_active?: boolean;
  is_template?: boolean;
}

export interface FormUpdateData {
  title?: string;
  description?: string;
  vacancy_id?: number | null;
  vacancy_ids?: number[];
  fields?: FormField[];
  is_active?: boolean;
  is_template?: boolean;
}

// ============================================================
// Authenticated API (recruiter)
// ============================================================

export const getMyForms = async (): Promise<FormTemplate[]> => {
  const { data } = await api.get('/forms');
  return data;
};

export const getFormTemplates = async (): Promise<FormTemplate[]> => {
  const { data } = await api.get('/forms/templates');
  return data;
};

export const createForm = async (body: FormCreateData): Promise<FormTemplate> => {
  const { data } = await api.post('/forms', body);
  return data;
};

export const getForm = async (id: number): Promise<FormTemplate> => {
  const { data } = await api.get(`/forms/${id}`);
  return data;
};

export const updateForm = async (id: number, body: FormUpdateData): Promise<FormTemplate> => {
  const { data } = await api.put(`/forms/${id}`, body);
  return data;
};

export const deleteForm = async (id: number): Promise<void> => {
  await api.delete(`/forms/${id}`);
};


// ============================================================
// Public API (no auth — candidate fills form)
// ============================================================

export const getPublicForm = async (slug: string): Promise<PublicFormData> => {
  const { data } = await api.get(`/forms/public/${slug}`);
  return data;
};

export const submitPublicForm = async (
  slug: string,
  formData: Record<string, unknown>
): Promise<{ message: string }> => {
  const { data } = await api.post(`/forms/public/${slug}/submit`, { data: formData });
  return data;
};

export interface SkippedFile { name: string; reason: string }
export interface SubmitWithFilesResult {
  message: string;
  entity_id?: number;
  files_saved?: number;
  skipped_files?: SkippedFile[];
}

export const submitPublicFormWithFiles = async (
  slug: string,
  formData: Record<string, unknown>,
  files: File[]
): Promise<SubmitWithFilesResult> => {
  const body = new FormData();
  body.append('data', JSON.stringify(formData));
  for (const file of files) {
    body.append('files', file);
  }
  const { data } = await api.post(`/forms/public/${slug}/submit-with-files`, body, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

export interface FormDispatchInfo {
  id: number; form_id: number; form_title: string | null; token: string;
  status: 'sent' | 'opened' | 'submitted'; seen_by_recruiter: boolean;
  submission_id: number | null; answers: Record<string, unknown> | null;
  field_labels?: Record<string, string>;
  file_links?: Record<string, string>; // field_id → URL скачивания файла анкеты

  created_at: string | null; submitted_at: string | null;
}

export const createDispatch = async (formId: number, entityId: number): Promise<{ token: string; url: string; id: number }> => {
  const { data } = await api.post(`/forms/${formId}/dispatch`, { entity_id: entityId });
  return data;
};


export const getEntityAllDispatches = async (entityId: number): Promise<(FormDispatchInfo & { source_entity_id: number; source_name: string | null })[]> => {
  const { data } = await api.get(`/forms/entity/${entityId}/all-dispatches`);
  return data;
};

export const getEntityFormsUnreadCount = async (entityId: number): Promise<{ count: number }> => {
  const { data } = await api.get(`/forms/entity/${entityId}/unread-count`);
  return data;
};

export const markEntityDispatchesSeen = async (entityId: number): Promise<void> => {
  await api.patch(`/forms/entity/${entityId}/dispatches/seen`);
};

export const deleteDispatch = async (dispatchId: number): Promise<void> => {
  await api.delete(`/forms/dispatch/${dispatchId}`);
};

export const getPublicFormByToken = async (token: string): Promise<PublicFormData & { candidate_name: string | null; already_submitted: boolean }> => {
  const { data } = await api.get(`/forms/public/d/${token}`);
  return data;
};

export const submitPublicFormByToken = async (token: string, formData: Record<string, unknown>): Promise<{ message: string }> => {
  const { data } = await api.post(`/forms/public/d/${token}/submit`, { data: formData });
  return data;
};

export const submitPublicFormByTokenWithFiles = async (
  token: string,
  formData: Record<string, unknown>,
  files: File[]
): Promise<SubmitWithFilesResult> => {
  const body = new FormData();
  body.append('data', JSON.stringify(formData));
  for (const file of files) {
    body.append('files', file);
  }
  const { data } = await api.post(`/forms/public/d/${token}/submit-with-files`, body, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

export interface AIChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AIChatResponse {
  message: string;
  fields: Omit<FormField, 'id'>[] | null;
  has_resume: boolean;
}

export const aiFormChat = async (
  entityId: number,
  messages: AIChatMessage[],
): Promise<AIChatResponse> => {
  const { data } = await api.post('/forms/ai-chat', { entity_id: entityId, messages });
  return data;
};

