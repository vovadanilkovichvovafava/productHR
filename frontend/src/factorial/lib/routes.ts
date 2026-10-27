// Все пути под /factorial (модуль смонтирован в Энцеладусе как /factorial/*).
export const ROUTES = {
  dashboard: '/factorial',
  inbox: '/factorial/inbox',
  inboxTodo: '/factorial/inbox/todo',
  inboxCompleted: '/factorial/inbox/completed',
  calendar: '/factorial/calendar',
  calendarTeam: '/factorial/calendar/team-view',
  discover: '/factorial/discover',
  profile: '/factorial/profile',
  profileWorkDetails: '/factorial/profile/work-details',
  profilePersonal: '/factorial/profile/personal',
  profileContracts: '/factorial/profile/contract_versions',
  profilePlanning: '/factorial/profile/planning_versions',
  profileCustom: '/factorial/profile/custom_tables',
  timeOff: '/factorial/time-off',
  tasks: '/factorial/tasks',
  myDocuments: '/factorial/my-documents',
  employees: '/factorial/employees',
  employeesTeams: '/factorial/employees/teams',
  employeesOrgChart: '/factorial/employees/org-chart',
  employeesVacancies: '/factorial/employees/vacancies',
  files: '/factorial/files',
  pages: '/factorial/pages',
  ticketing: '/factorial/ticketing',
  talentAnalytics: '/factorial/talent_analytics',
  analytics: '/factorial/analytics',
  analyticsAdvanced: '/factorial/analytics/reports/dashboards/list',
  analyticsInsights: '/factorial/analytics/insights',
  workflows: '/factorial/workflows',
  workflowsSurveys: '/factorial/workflows/surveys',
  workflowsOnboarding: '/factorial/workflows/onboarding',
  workflowsOffboarding: '/factorial/workflows/offboarding',
  workflowsCustom: '/factorial/workflows/custom',
  settings: '/factorial/settings',
} as const;

// Вкладки профиля (6 шт.). base = '/factorial/profile' (свой ЛК) или '/factorial/employees/:id' (HR-вид).
export function buildProfileTabs(base: string) {
  return [
    { label: 'Обзор', href: base, end: true },
    { label: 'Детали работы', href: `${base}/work-details` },
    { label: 'Личные данные', href: `${base}/personal` },
    { label: 'Соглашения', href: base === '/factorial/profile' ? '/factorial/my-documents' : `${base}/agreements` },
    { label: 'Документы', href: `${base}/documents` },
    { label: 'Отпуска', href: `${base}/time-off` },
  ];
}
export const CABINET_TABS = buildProfileTabs('/factorial/profile');
