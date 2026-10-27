// TS types mirroring backend schemas (api/routes/employees.py, documents.py, invitations.py).
export interface Employee {
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
  cycle_start: string | null;
  cycle_end: string | null;
}

export type LeaveType = 'vacation' | 'sick' | 'family_leave' | 'bereavement';

export interface LeaveRequest {
  id: number;
  employee_id: number;
  type: string;
  start_date: string;
  end_date: string;
  days: number;
  reason: string | null;
  status: string; // pending | approved | rejected
  approved_by: number | null;
  approved_at: string | null;
  created_at: string | null;
  employee_name: string | null;
}

export interface Reminder {
  employee_id: number;
  employee_name: string;
  type: 'probation_ending' | 'one_year_anniversary';
  date: string;
  days_remaining: number;
}

export interface DocTemplate {
  id: number;
  org_id: number;
  name: string;
  content: string;
  variables: string[] | null;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface SignedDoc {
  id: number;
  template_id: number | null;
  employee_id: number;
  title: string;
  content_rendered: string;
  signature_data: string | null;
  signed_at: string | null;
  signer_ip: string | null;
  status: string; // pending | signed
  created_at: string | null;
  employee_name: string | null;
}

export interface Invitation {
  id: number;
  token: string;
  email: string | null;
  name: string | null;
  org_role: string;
  department_ids: { id: number; role: string }[];
  invitation_url: string;
  expires_at: string | null;
  used_at: string | null;
}

export interface EmployeeDocument {
  id: number;
  filename: string;
  content_type: string | null;
  size: number | null;
  uploaded_at: string;
}

export interface BulkImportResult { updated: number; skipped: string[]; errors: string[]; }
