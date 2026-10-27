import { type ReactElement } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import FactorialShell from './layouts/FactorialShell';

// Основные страницы (порядок — как в боковой навигации Factorial)
import InboxPage from './pages/InboxPage';
import CalendarPage from './pages/CalendarPage';
import DiscoverPage from './pages/DiscoverPage';
import ProfileOverviewPage from './pages/profile/ProfileOverviewPage';
import ProfileWorkDetailsPage from './pages/profile/ProfileWorkDetailsPage';
import ProfilePersonalPage from './pages/profile/ProfilePersonalPage';
import ProfileContractsPage from './pages/profile/ProfileContractsPage';
import ProfilePlanningPage from './pages/profile/ProfilePlanningPage';
import ProfileCustomPage from './pages/profile/ProfileCustomPage';
import ProfileDocumentsPage from './pages/profile/ProfileDocumentsPage';
import TimeOffPage from './pages/TimeOffPage';
import TasksPage from './pages/TasksPage';
import MyDocumentsPage from './pages/MyDocumentsPage';
import MyTeamPage from './pages/MyTeamPage';
import EmployeesPage from './pages/EmployeesPage';
import EmployeesImportPage from './pages/EmployeesImportPage';
import EmployeesOrgChartPage from './pages/EmployeesOrgChartPage';
import EmployeesTeamsPage from './pages/EmployeesTeamsPage';
import EmployeesVacanciesPage from './pages/EmployeesVacanciesPage';
import FilesPage from './pages/FilesPage';
import PagesPage from './pages/PagesPage';
import TicketingPage from './pages/TicketingPage';
import TalentAnalyticsPage from './pages/TalentAnalyticsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import WorkflowsPage from './pages/WorkflowsPage';
import SettingsPage from './pages/SettingsPage';
import NotFoundPage from './pages/NotFoundPage';

// Полностраничные формы (открываются по кнопкам со страниц)
import AddEmployeeFormPage from './pages/forms/AddEmployeeFormPage';
import ExportDataFormPage from './pages/forms/ExportDataFormPage';
import CreateTaskFormPage from './pages/forms/CreateTaskFormPage';
import RequestTimeOffFormPage from './pages/forms/RequestTimeOffFormPage';
import AddTimeOffFormPage from './pages/forms/AddTimeOffFormPage';
import AddEventFormPage from './pages/forms/AddEventFormPage';
import WritePostFormPage from './pages/forms/WritePostFormPage';
import KudosFormPage from './pages/forms/KudosFormPage';

/**
 * Модуль Факториал внутри Энцеладуса. Смонтирован в App.tsx как <Route path="factorial/*">.
 * Пути здесь — ОТНОСИТЕЛЬНЫЕ (без /factorial), т.к. это вложенный роутер.
 * Боковая навигация и переходы используют АБСОЛЮТНЫЕ /factorial/* (см. lib/routes.ts).
 */
export default function FactorialModule() {
  const user = useAuthStore((s) => s.user);
  // «Сотрудники» и «Документы» — только HR/админ/рекрутёр. Обычный сотрудник (member)
  // их не видит и не может открыть по URL: дефолтная посадка и guard ведут в «Личный кабинет».
  const canManage =
    user?.role === 'superadmin' ||
    user?.org_role === 'owner' ||
    user?.org_role === 'admin' ||
    user?.org_role === 'hr';
  const home = canManage ? '/factorial/employees' : '/factorial/profile';
  const guard = (el: ReactElement): ReactElement =>
    canManage ? el : <Navigate to="/factorial/profile" replace />;

  return (
    <Routes>
      <Route element={<FactorialShell />}>
        {/* Вход в Факториал: HR → «Сотрудники», обычный сотрудник → «Личный кабинет» */}
        <Route index element={<Navigate to={home} replace />} />
        <Route path="dashboard" element={<Navigate to={home} replace />} />
        <Route path="dashboard/event/new" element={<AddEventFormPage />} />
        <Route path="dashboard/post/new" element={<WritePostFormPage />} />
        <Route path="dashboard/kudos/new" element={<KudosFormPage />} />

        {/* Верхние пункты */}
        <Route path="inbox" element={<InboxPage />} />
        <Route path="inbox/*" element={<InboxPage />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="calendar/team-view" element={<CalendarPage />} />
        <Route path="calendar/add-time-off" element={<AddTimeOffFormPage />} />
        <Route path="discover" element={<DiscoverPage />} />

        {/* Личное */}
        <Route path="profile" element={<ProfileOverviewPage />} />
        <Route path="profile/work-details" element={<ProfileWorkDetailsPage />} />
        <Route path="profile/personal" element={<ProfilePersonalPage />} />
        <Route path="profile/contract_versions" element={<ProfileContractsPage />} />
        <Route path="profile/planning_versions" element={<ProfilePlanningPage />} />
        <Route path="profile/custom_tables" element={<ProfileCustomPage />} />
        <Route path="profile/documents" element={<ProfileDocumentsPage />} />
        <Route path="profile/time-off" element={<ProfilePlanningPage />} />
        <Route path="time-off" element={<TimeOffPage />} />
        <Route path="time-off/new" element={<RequestTimeOffFormPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="tasks/new" element={<CreateTaskFormPage />} />
        <Route path="my-documents" element={<MyDocumentsPage />} />
        <Route path="my-team" element={<MyTeamPage />} />

        {/* Компания — только HR/админ; обычный сотрудник редиректится в «Личный кабинет» */}
        <Route path="employees" element={guard(<EmployeesPage />)} />
        <Route path="employees/new" element={guard(<AddEmployeeFormPage />)} />
        <Route path="employees/export" element={guard(<ExportDataFormPage />)} />
        <Route path="employees/import" element={guard(<EmployeesImportPage />)} />
        <Route path="employees/teams" element={guard(<EmployeesTeamsPage />)} />
        <Route path="employees/org-chart" element={guard(<EmployeesOrgChartPage />)} />
        <Route path="employees/vacancies" element={guard(<EmployeesVacanciesPage />)} />
        {/* HR/руководитель: карточка сотрудника по ID (6 вкладок) */}
        <Route path="employees/:id" element={guard(<ProfileOverviewPage />)} />
        <Route path="employees/:id/work-details" element={guard(<ProfileWorkDetailsPage />)} />
        <Route path="employees/:id/personal" element={guard(<ProfilePersonalPage />)} />
        <Route path="employees/:id/agreements" element={guard(<MyDocumentsPage />)} />
        <Route path="employees/:id/documents" element={guard(<ProfileDocumentsPage />)} />
        <Route path="employees/:id/time-off" element={guard(<ProfilePlanningPage />)} />
        <Route path="files" element={guard(<FilesPage />)} />
        <Route path="pages" element={<PagesPage />} />
        <Route path="ticketing" element={<TicketingPage />} />

        {/* Таланты / Другое */}
        <Route path="talent_analytics" element={<TalentAnalyticsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="analytics/*" element={<AnalyticsPage />} />
        <Route path="workflows" element={<WorkflowsPage />} />
        <Route path="workflows/*" element={<WorkflowsPage />} />
        <Route path="settings" element={<SettingsPage />} />

        {/* 404 внутри модуля */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
