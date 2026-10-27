import { deduplicatedGet, debouncedMutation } from './client';

export interface EmailTemplate {
  id: number;
  org_id: number;
  name: string;
  template_type: string;
  subject: string;
  body_html: string;
  body_text?: string;
  variables: string[];
  is_active: boolean;
  is_default: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface EmailPreview {
  subject: string;
  body_html: string;
  body_text?: string;
  recipient_email?: string;
  recipient_name?: string;
  variables_used: Record<string, string>;
}

export interface SendEmailResponse {
  id: number;
  status: string;
  recipient_email: string;
  recipient_name?: string;
  subject: string;
  message: string;
}

export const getEmailTemplates = async (): Promise<EmailTemplate[]> => {
  const { data } = await deduplicatedGet<EmailTemplate[]>('/email-templates/templates');
  return data;
};

export const previewEmail = async (params: {
  template_id?: number;
  entity_id?: number;
  vacancy_id?: number;
  subject?: string;
  body_html?: string;
  custom_variables?: Record<string, string>;
}): Promise<EmailPreview> => {
  const { data } = await debouncedMutation<EmailPreview>('post', '/email-templates/preview', params);
  return data;
};

export const sendEmail = async (params: {
  template_id: number;
  entity_id: number;
  vacancy_id?: number;
  subject_override?: string;
  body_override?: string;
  custom_variables?: Record<string, string>;
}): Promise<SendEmailResponse> => {
  const { data } = await debouncedMutation<SendEmailResponse>('post', '/email-templates/send', params);
  return data;
};
