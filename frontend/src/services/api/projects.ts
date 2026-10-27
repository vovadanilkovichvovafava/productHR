import api, { deduplicatedGet, debouncedMutation } from './client';

// ============================================================
// TYPES
// ============================================================

export type ProjectStatus = 'planning' | 'active' | 'on_hold' | 'completed' | 'cancelled';
export type TaskStatus = 'backlog' | 'todo' | 'in_progress' | 'review' | 'done' | 'cancelled';
export type ProjectRole = 'manager' | 'developer' | 'reviewer' | 'observer';

export interface Project {
  id: number;
  org_id: number;
  department_id?: number;
  department_name?: string;
  name: string;
  prefix?: string;
  description?: string;
  status: ProjectStatus;
  priority: number;
  client_name?: string;
  progress_percent: number;
  progress_mode: string;
  start_date?: string;
  target_date?: string;
  predicted_date?: string;
  completed_at?: string;
  tags: string[];
  color?: string;
  created_by?: number;
  creator_name?: string;
  created_at?: string;
  updated_at?: string;
  member_count: number;
  task_counts: Record<string, number>;
  current_user_role?: string; // user's role: 'manager' | 'developer' | 'reviewer' | 'observer' | 'admin' | 'dept_lead'
}

export interface ProjectMember {
  id: number;
  project_id: number;
  user_id: number;
  user_name?: string;
  user_email?: string;
  role: ProjectRole;
  allocation_percent: number;
  joined_at?: string;
}

export interface ProjectTask {
  id: number;
  project_id: number;
  task_number?: number;
  task_key?: string; // e.g. "PM-42"
  milestone_id?: number;
  title: string;
  description?: string;
  status: string;
  priority: number;
  assignee_id?: number;
  assignee_name?: string;
  estimated_hours?: number;
  due_date?: string;
  completed_at?: string;
  sort_order: number;
  tags: string[];
  total_hours_logged: number;
  parent_task_id?: number;
  subtask_count: number;
  subtasks_done: number;
  comment_count: number;
  attachment_count: number;
  created_by?: number;
  creator_name?: string;
  /** Задачу завёл бот из сообщения в чате (по кнопке «Создать») */
  created_by_bot?: boolean;
  /** Сообщение, из которого бот её достал */
  source_message?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProjectMilestone {
  id: number;
  project_id: number;
  name: string;
  description?: string;
  target_date?: string;
  completed_at?: string;
  sort_order: number;
  created_at?: string;
  task_count: number;
}

export interface TaskTimeLog {
  id: number;
  task_id: number;
  user_id: number;
  user_name?: string;
  hours: number;
  date: string;
  note?: string;
  created_at?: string;
}

export interface TaskKanbanColumn {
  status: string;
  title: string;
  tasks: ProjectTask[];
  count: number;
}

export interface TaskKanbanBoard {
  project_id: number;
  columns: TaskKanbanColumn[];
  total_count: number;
}

export interface ProjectFilters {
  status?: ProjectStatus;
  department_id?: number;
  search?: string;
}

export interface ProjectCreate {
  name: string;
  prefix?: string;
  description?: string;
  department_id?: number;
  status?: ProjectStatus;
  priority?: number;
  client_name?: string;
  progress_mode?: string;
  start_date?: string;
  target_date?: string;
  tags?: string[];
  color?: string;
}

export interface ProjectUpdate extends Partial<ProjectCreate> {
  progress_percent?: number;
  predicted_date?: string;
  extra_data?: Record<string, unknown>;
}

export interface TaskCreate {
  title: string;
  description?: string;
  milestone_id?: number;
  status?: string;
  priority?: number;
  assignee_id?: number;
  estimated_hours?: number;
  due_date?: string;
  tags?: string[];
  parent_task_id?: number;
}

export interface TaskUpdate extends Partial<TaskCreate> {
  sort_order?: number;
}

export interface MemberCreate {
  user_id: number;
  role?: ProjectRole;
  allocation_percent?: number;
}

export interface MemberUpdate {
  role?: ProjectRole;
  allocation_percent?: number;
}

export interface MilestoneCreate {
  name: string;
  description?: string;
  target_date?: string;
  sort_order?: number;
}

export interface TimeLogCreate {
  hours: number;
  date: string;
  note?: string;
}

// ============================================================
// PROJECTS API
// ============================================================

export const getProjects = async (filters?: ProjectFilters): Promise<Project[]> => {
  const params: Record<string, string> = {};
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null) params[key] = String(value);
    });
  }
  const { data } = await deduplicatedGet<Project[]>('/projects', { params });
  return data;
};

export const createProject = async (projectData: ProjectCreate): Promise<Project> => {
  const { data } = await debouncedMutation<Project>('post', '/projects', projectData);
  return data;
};

export const getProject = async (id: number): Promise<Project> => {
  const { data } = await deduplicatedGet<Project>(`/projects/${id}`);
  return data;
};

export const updateProject = async (id: number, updates: ProjectUpdate): Promise<Project> => {
  const { data } = await debouncedMutation<Project>('put', `/projects/${id}`, updates);
  return data;
};

export const deleteProject = async (id: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/projects/${id}`);
};

// ============================================================
// PROJECT MEMBERS API
// ============================================================

export const getProjectMembers = async (id: number): Promise<ProjectMember[]> => {
  const { data } = await deduplicatedGet<ProjectMember[]>(`/projects/${id}/members`);
  return data;
};

export const addProjectMember = async (id: number, memberData: MemberCreate): Promise<ProjectMember> => {
  const { data } = await debouncedMutation<ProjectMember>('post', `/projects/${id}/members`, memberData);
  return data;
};

export const updateProjectMember = async (id: number, userId: number, updates: MemberUpdate): Promise<ProjectMember> => {
  const { data } = await debouncedMutation<ProjectMember>('put', `/projects/${id}/members/${userId}`, updates);
  return data;
};

export const removeProjectMember = async (id: number, userId: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/projects/${id}/members/${userId}`);
};

// ============================================================
// PROJECT TASKS API
// ============================================================

export const getProjectTasks = async (id: number, filters?: { status?: TaskStatus; assignee_id?: number }): Promise<ProjectTask[]> => {
  const params: Record<string, string> = {};
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null) params[key] = String(value);
    });
  }
  const { data } = await deduplicatedGet<ProjectTask[]>(`/projects/${id}/tasks`, { params });
  return data;
};

export const createProjectTask = async (id: number, taskData: TaskCreate): Promise<ProjectTask> => {
  const { data } = await debouncedMutation<ProjectTask>('post', `/projects/${id}/tasks`, taskData);
  return data;
};

export const updateProjectTask = async (id: number, taskId: number, updates: TaskUpdate): Promise<ProjectTask> => {
  const { data } = await debouncedMutation<ProjectTask>('put', `/projects/${id}/tasks/${taskId}`, updates);
  return data;
};

export const deleteProjectTask = async (id: number, taskId: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/projects/${id}/tasks/${taskId}`);
};

export const getTaskKanban = async (id: number): Promise<TaskKanbanBoard> => {
  const { data } = await deduplicatedGet<TaskKanbanBoard>(`/projects/${id}/tasks/kanban`);
  return data;
};

export const bulkMoveTasks = async (id: number, moveData: { task_ids: number[]; status: TaskStatus }): Promise<ProjectTask[]> => {
  const { data } = await debouncedMutation<ProjectTask[]>('post', `/projects/${id}/tasks/move`, moveData);
  return data;
};

export const getSubtasks = async (projectId: number, taskId: number): Promise<ProjectTask[]> => {
  const { data } = await deduplicatedGet<ProjectTask[]>(`/projects/${projectId}/tasks/${taskId}/subtasks`);
  return data;
};

// ============================================================
// PROJECT MILESTONES API
// ============================================================

export const getProjectMilestones = async (id: number): Promise<ProjectMilestone[]> => {
  const { data } = await deduplicatedGet<ProjectMilestone[]>(`/projects/${id}/milestones`);
  return data;
};

export const createMilestone = async (id: number, milestoneData: MilestoneCreate): Promise<ProjectMilestone> => {
  const { data } = await debouncedMutation<ProjectMilestone>('post', `/projects/${id}/milestones`, milestoneData);
  return data;
};

export const updateMilestone = async (id: number, mid: number, updates: Partial<MilestoneCreate>): Promise<ProjectMilestone> => {
  const { data } = await debouncedMutation<ProjectMilestone>('put', `/projects/${id}/milestones/${mid}`, updates);
  return data;
};

export const deleteMilestone = async (id: number, mid: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/projects/${id}/milestones/${mid}`);
};

// ============================================================
// TIME LOGS API
// ============================================================

export const createTimeLog = async (id: number, taskId: number, logData: TimeLogCreate): Promise<TaskTimeLog> => {
  const { data } = await debouncedMutation<TaskTimeLog>('post', `/projects/${id}/tasks/${taskId}/time-logs`, logData);
  return data;
};

export const getTaskTimeLogs = async (id: number, taskId: number): Promise<TaskTimeLog[]> => {
  const { data } = await deduplicatedGet<TaskTimeLog[]>(`/projects/${id}/tasks/${taskId}/time-logs`);
  return data;
};

// ============================================================
// PROJECT EFFORT & ANALYTICS API
// ============================================================

export interface ProjectEffort {
  project_id: number;
  total_hours: number;
  by_member: { user_id: number; user_name: string; hours: number }[];
  by_milestone: { milestone_id: number; milestone_name: string; hours: number }[];
}

export const getProjectEffort = async (id: number): Promise<ProjectEffort> => {
  const { data } = await deduplicatedGet<ProjectEffort>(`/projects/${id}/effort`);
  return data;
};

export interface ProjectsOverview {
  total: number;
  by_status: Record<string, number>;
  overdue_count: number;
  avg_progress: number;
}

export const getProjectsOverview = async (): Promise<ProjectsOverview> => {
  const { data } = await deduplicatedGet<ProjectsOverview>('/projects/analytics/overview');
  return data;
};

export interface ResourceAllocation {
  users: { user_id: number; user_name: string; total_allocation: number; projects: { project_id: number; project_name: string; allocation: number }[] }[];
}

export const getResourceAllocation = async (): Promise<ResourceAllocation> => {
  const { data } = await deduplicatedGet<ResourceAllocation>('/projects/analytics/resources');
  return data;
};

export interface ProjectAnalytics {
  project_id: number;
  velocity: number;
  burndown: { date: string; remaining: number; ideal: number }[];
  completion_forecast?: string;
}

export const getProjectAnalytics = async (id: number): Promise<ProjectAnalytics> => {
  const { data } = await deduplicatedGet<ProjectAnalytics>(`/projects/${id}/analytics`);
  return data;
};

// ============================================================
// ALL TASKS (cross-project)
// ============================================================

export interface AllTasksProjectGroup {
  project_id: number;
  project_name: string;
  project_color?: string;
  project_status?: string;
  status_groups: Record<string, ProjectTask[]>;
}

export interface AllTasksFilters {
  status?: TaskStatus;
  assignee_id?: number;
  search?: string;
  /** только задачи, заведённые ботом из чата */
  created_by_bot?: boolean;
}

export const getAllTasks = async (filters?: AllTasksFilters): Promise<AllTasksProjectGroup[]> => {
  const params: Record<string, string> = {};
  if (filters?.status) params.status = filters.status;
  if (filters?.assignee_id) params.assignee_id = String(filters.assignee_id);
  if (filters?.search) params.search = filters.search;
  if (filters?.created_by_bot) params.created_by_bot = 'true';
  const { data } = await deduplicatedGet<AllTasksProjectGroup[]>('/projects/all-tasks', { params });
  return data;
};

// ============================================================
// CUSTOM FIELDS API
// ============================================================

export type CustomFieldType = 'text' | 'number' | 'currency' | 'select' | 'date' | 'checkbox';

export interface ProjectCustomField {
  id: number;
  project_id: number;
  name: string;
  field_type: CustomFieldType;
  options: string[];
  currency?: string;
  sort_order: number;
  is_required: boolean;
}

export interface TaskFieldValue {
  field_id: number;
  field_name: string;
  field_type: CustomFieldType;
  value: string | null;
  currency?: string;
}

export const getCustomFields = async (projectId: number): Promise<ProjectCustomField[]> => {
  const { data } = await deduplicatedGet<ProjectCustomField[]>(`/projects/${projectId}/custom-fields`);
  return data;
};

export const createCustomField = async (projectId: number, fieldData: { name: string; field_type: CustomFieldType; options?: string[]; currency?: string; is_required?: boolean }): Promise<ProjectCustomField> => {
  const { data } = await debouncedMutation<ProjectCustomField>('post', `/projects/${projectId}/custom-fields`, fieldData);
  return data;
};

export const updateCustomField = async (projectId: number, fieldId: number, fieldData: { name?: string; field_type?: CustomFieldType; options?: string[]; currency?: string; sort_order?: number; is_required?: boolean }): Promise<ProjectCustomField> => {
  const { data } = await debouncedMutation<ProjectCustomField>('put', `/projects/${projectId}/custom-fields/${fieldId}`, fieldData);
  return data;
};

export const deleteCustomField = async (projectId: number, fieldId: number): Promise<void> => {
  await debouncedMutation<void>('delete', `/projects/${projectId}/custom-fields/${fieldId}`);
};

export const getTaskFieldValues = async (projectId: number, taskId: number): Promise<TaskFieldValue[]> => {
  const { data } = await deduplicatedGet<TaskFieldValue[]>(`/projects/${projectId}/tasks/${taskId}/field-values`);
  return data;
};

export const setTaskFieldValue = async (projectId: number, taskId: number, fieldId: number, value: string): Promise<void> => {
  await debouncedMutation('put', `/projects/${projectId}/tasks/${taskId}/field-values/${fieldId}`, { value });
};

// ============================================================
// PROJECT TASK STATUSES API
// ============================================================

export interface ProjectTaskStatusDef {
  id: number;
  project_id: number;
  name: string;
  slug: string;
  color: string;
  sort_order: number;
  is_done: boolean;
  is_default: boolean;
}

export const getProjectStatuses = async (projectId: number): Promise<ProjectTaskStatusDef[]> => {
  const { data } = await deduplicatedGet<ProjectTaskStatusDef[]>(`/projects/${projectId}/statuses`);
  return data;
};

export const createProjectStatus = async (projectId: number, statusData: { name: string; color?: string; sort_order?: number; is_done?: boolean; is_default?: boolean }): Promise<ProjectTaskStatusDef> => {
  const { data } = await debouncedMutation<ProjectTaskStatusDef>('post', `/projects/${projectId}/statuses`, statusData);
  return data;
};

export const updateProjectStatus = async (projectId: number, statusId: number, statusData: Partial<{ name: string; color: string; sort_order: number; is_done: boolean; is_default: boolean }>): Promise<ProjectTaskStatusDef> => {
  const { data } = await debouncedMutation<ProjectTaskStatusDef>('put', `/projects/${projectId}/statuses/${statusId}`, statusData);
  return data;
};

export const deleteProjectStatus = async (projectId: number, statusId: number): Promise<void> => {
  await debouncedMutation('delete', `/projects/${projectId}/statuses/${statusId}`, {});
};

export const reorderProjectStatuses = async (projectId: number, statuses: { id: number; sort_order: number }[]): Promise<ProjectTaskStatusDef[]> => {
  const { data } = await debouncedMutation<ProjectTaskStatusDef[]>('put', `/projects/${projectId}/statuses/reorder`, { statuses });
  return data;
};

// ============================================================
// TASK COMMENTS API
// ============================================================

export interface TaskComment {
  id: number;
  task_id: number;
  user_id: number;
  user_name?: string;
  content: string;
  edited_at?: string;
  created_at?: string;
}

export const getTaskComments = async (projectId: number, taskId: number): Promise<TaskComment[]> => {
  const { data } = await deduplicatedGet<TaskComment[]>(`/projects/${projectId}/tasks/${taskId}/comments`);
  return data;
};

export const createTaskComment = async (projectId: number, taskId: number, content: string): Promise<TaskComment> => {
  const { data } = await debouncedMutation<TaskComment>('post', `/projects/${projectId}/tasks/${taskId}/comments`, { content });
  return data;
};

export const updateTaskComment = async (projectId: number, taskId: number, commentId: number, content: string): Promise<TaskComment> => {
  const { data } = await debouncedMutation<TaskComment>('put', `/projects/${projectId}/tasks/${taskId}/comments/${commentId}`, { content });
  return data;
};

export const deleteTaskComment = async (projectId: number, taskId: number, commentId: number): Promise<void> => {
  await debouncedMutation('delete', `/projects/${projectId}/tasks/${taskId}/comments/${commentId}`, {});
};

// ============================================================
// TASK ATTACHMENTS API
// ============================================================

export interface TaskAttachment {
  id: number;
  task_id: number;
  user_id: number;
  user_name?: string;
  filename: string;
  original_filename: string;
  file_size: number;
  content_type?: string;
  created_at?: string;
}

export const getTaskAttachments = async (projectId: number, taskId: number): Promise<TaskAttachment[]> => {
  const { data } = await deduplicatedGet<TaskAttachment[]>(`/projects/${projectId}/tasks/${taskId}/attachments`);
  return data;
};

export const uploadTaskAttachment = async (projectId: number, taskId: number, file: File): Promise<TaskAttachment> => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post<TaskAttachment>(`/projects/${projectId}/tasks/${taskId}/attachments`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

export const deleteTaskAttachment = async (projectId: number, taskId: number, attachmentId: number): Promise<void> => {
  await debouncedMutation('delete', `/projects/${projectId}/tasks/${taskId}/attachments/${attachmentId}`, {});
};

// ============================================================
// AI TASK CREATION
// ============================================================

export interface ParsedTaskItem {
  action: 'create' | 'update' | 'skip';
  title: string;
  description?: string;
  priority: number;
  estimated_hours?: number;
  assignee_hint?: string;
  existing_task_id?: number;
  existing_task_title?: string;
  reason?: string;
}

export interface AIParsePlanResponse {
  items: ParsedTaskItem[];
  raw_ai_response?: string;
}

export const aiParsePlan = async (projectId: number, text: string, defaultStatus?: string): Promise<AIParsePlanResponse> => {
  const { data } = await debouncedMutation<AIParsePlanResponse>('post', `/projects/${projectId}/ai/parse-plan`, {
    text,
    default_status: defaultStatus || 'todo',
  });
  return data;
};

export const aiCreateTasks = async (projectId: number, items: ParsedTaskItem[], defaultStatus?: string): Promise<{ created: number; updated: number; skipped: number; total: number }> => {
  const { data } = await debouncedMutation<{ created: number; updated: number; skipped: number; total: number }>('post', `/projects/${projectId}/ai/create-tasks`, {
    items,
    default_status: defaultStatus || 'todo',
  });
  return data;
};

// ============================================================
// PROJECT STATUS DEFINITIONS (org-level, for kanban board)
// ============================================================

export interface ProjectStatusDef2 {
  id: number;
  org_id: number;
  name: string;
  slug: string;
  color: string;
  sort_order: number;
  is_done: boolean;
}

export const getProjectStatusDefs = async (): Promise<ProjectStatusDef2[]> => {
  const { data } = await deduplicatedGet<ProjectStatusDef2[]>('/project-statuses');
  return data;
};

export const createProjectStatusDef = async (statusData: { name: string; color?: string; sort_order?: number; is_done?: boolean }): Promise<ProjectStatusDef2> => {
  const { data } = await debouncedMutation<ProjectStatusDef2>('post', '/project-statuses', statusData);
  return data;
};

export const updateProjectStatusDef = async (statusId: number, statusData: Partial<{ name: string; color: string; sort_order: number; is_done: boolean }>): Promise<ProjectStatusDef2> => {
  const { data } = await debouncedMutation<ProjectStatusDef2>('put', `/project-statuses/${statusId}`, statusData);
  return data;
};

export const deleteProjectStatusDef = async (statusId: number): Promise<void> => {
  await debouncedMutation('delete', `/project-statuses/${statusId}`, {});
};

export const reorderProjectStatusDefs = async (statuses: { id: number; sort_order: number }[]): Promise<ProjectStatusDef2[]> => {
  const { data } = await debouncedMutation<ProjectStatusDef2[]>('put', '/project-statuses/reorder', { statuses });
  return data;
};

// ============================================================
// SATURN INTEGRATION
// ============================================================

export interface SaturnProject {
  id: number;
  saturn_uuid: string;
  saturn_id: number;
  name: string;
  description?: string;
  is_archived: boolean;
  enceladus_project_id?: number;
  last_synced_at?: string;
}

export interface SaturnApplication {
  id: number;
  saturn_uuid: string;
  name: string;
  fqdn?: string;
  status?: string;
  build_pack?: string;
  git_repository?: string;
  git_branch?: string;
  environment_name?: string;
}

export interface SaturnSyncStatus {
  last_sync?: {
    type: string;
    projects_synced: number;
    apps_synced: number;
    errors: unknown[];
    at: string;
  };
  total_saturn_projects: number;
  total_saturn_apps: number;
}

export const getSaturnProjects = async (): Promise<SaturnProject[]> => {
  const { data } = await deduplicatedGet<SaturnProject[]>('/saturn');
  return data;
};

export const getSaturnProject = async (uuid: string): Promise<SaturnProject & { applications: SaturnApplication[] }> => {
  const { data } = await deduplicatedGet<SaturnProject & { applications: SaturnApplication[] }>(`/saturn/${uuid}`);
  return data;
};

export const triggerSaturnSync = async (): Promise<{ projects_synced: number; apps_synced: number; errors: unknown[] }> => {
  const { data } = await debouncedMutation<{ projects_synced: number; apps_synced: number; errors: unknown[] }>('post', '/saturn/sync', {});
  return data;
};

export const getSaturnSyncStatus = async (): Promise<SaturnSyncStatus> => {
  const { data } = await deduplicatedGet<SaturnSyncStatus>('/saturn/sync/status');
  return data;
};
