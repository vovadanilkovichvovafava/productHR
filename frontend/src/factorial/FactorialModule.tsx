import { type ReactElement } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import FactorialShell from './layouts/FactorialShell';

// Только настоящие экраны: кабинет, кадры, документы, отпуска. Демо-клоны
// (входящие с фильтрами, календарь, задачи, «Что нового», аналитика,
// процессы, настройки, формы «Demo mode») убраны 27.10.2026: в них были
// данные первого клиента и кнопки, которые ничего не сохраняли.
import ProfileOverviewPage from './pages/profile/ProfileOverviewPage';
import ProfileWorkDetailsPage from './pages/profile/ProfileWorkDetailsPage';
import ProfilePersonalPage from './pages/profile/ProfilePersonalPage';
import ProfilePlanningPage from './pages/profile/ProfilePlanningPage';
import ProfileCustomPage from './pages/profile/ProfileCustomPage';
import ProfileDocumentsPage from './pages/profile/ProfileDocumentsPage';
import TimeOffPage from './pages/TimeOffPage';
import MyDocumentsPage from './pages/MyDocumentsPage';
import MyTeamPage from './pages/MyTeamPage';
import EmployeesPage from './pages/EmployeesPage';
import EmployeesImportPage from './pages/EmployeesImportPage';
import EmployeesOrgChartPage from './pages/EmployeesOrgChartPage';
import EmployeesTeamsPage from './pages/EmployeesTeamsPage';
import FilesPage from './pages/FilesPage';
import NotFoundPage from './pages/NotFoundPage';
import AddEmployeeFormPage from './pages/forms/AddEmployeeFormPage';

/**
 * Модуль «Управление» (кадры). Смонтирован в App.tsx как <Route path="factorial/*">.
 * Пути здесь — ОТНОСИТЕЛЬНЫЕ (без /factorial), т.к. это вложенный роутер.
 * Боковая навигация и переходы используют АБСОЛЮТНЫЕ /factorial/* (см. lib/routes.ts).
 */
export default function FactorialModule() {
  const user = useAuthStore((s) => s.user);
  // «Сотрудники» и «Документы» — только суперадмин и админы организации
  // (owner/admin): так же решает сервер. Рекрутёр (hr) и сотрудник (member)
  // попадают в «Личный кабинет»; до 27.10.2026 hr пускали сюда, и он видел
  // пустые экраны с 403 от сервера.
  const canManage =
    user?.role === 'superadmin' ||
    user?.org_role === 'owner' ||
    user?.org_role === 'admin';
  const home = canManage ? '/factorial/employees' : '/factorial/profile';
  const guard = (el: ReactElement): ReactElement =>
    canManage ? el : <Navigate to="/factorial/profile" replace />;

  return (
    <Routes>
      <Route element={<FactorialShell />}>
        {/* Вход: админ кадров → «Сотрудники», остальные → «Личный кабинет» */}
        <Route index element={<Navigate to={home} replace />} />
        <Route path="dashboard" element={<Navigate to={home} replace />} />

        {/* Личное */}
        <Route path="profile" element={<ProfileOverviewPage />} />
        <Route path="profile/work-details" element={<ProfileWorkDetailsPage />} />
        <Route path="profile/personal" element={<ProfilePersonalPage />} />
        {/* Старые адреса вкладок — на настоящие экраны */}
        <Route path="profile/contract_versions" element={<Navigate to="/factorial/my-documents" replace />} />
        <Route path="profile/planning_versions" element={<ProfilePlanningPage />} />
        <Route path="profile/custom_tables" element={<ProfileCustomPage />} />
        <Route path="profile/documents" element={<ProfileDocumentsPage />} />
        <Route path="profile/time-off" element={<ProfilePlanningPage />} />
        <Route path="time-off" element={<TimeOffPage />} />
        <Route path="my-documents" element={<MyDocumentsPage />} />
        <Route path="my-team" element={<MyTeamPage />} />

        {/* Компания — только админы кадров; остальные редиректятся в «Личный кабинет» */}
        <Route path="employees" element={guard(<EmployeesPage />)} />
        <Route path="employees/new" element={guard(<AddEmployeeFormPage />)} />
        <Route path="employees/import" element={guard(<EmployeesImportPage />)} />
        <Route path="employees/teams" element={guard(<EmployeesTeamsPage />)} />
        <Route path="employees/org-chart" element={guard(<EmployeesOrgChartPage />)} />
        {/* Вакансии ведутся в HR-разделе (общая форма вакансии); старый адрес — туда. */}
        <Route path="employees/vacancies" element={<Navigate to="/vacancies" replace />} />
        {/* Карточка сотрудника по ID (6 вкладок) */}
        <Route path="employees/:id" element={guard(<ProfileOverviewPage />)} />
        <Route path="employees/:id/work-details" element={guard(<ProfileWorkDetailsPage />)} />
        <Route path="employees/:id/personal" element={guard(<ProfilePersonalPage />)} />
        <Route path="employees/:id/agreements" element={guard(<MyDocumentsPage />)} />
        <Route path="employees/:id/documents" element={guard(<ProfileDocumentsPage />)} />
        <Route path="employees/:id/time-off" element={guard(<ProfilePlanningPage />)} />
        <Route path="files" element={guard(<FilesPage />)} />

        {/* 404 внутри модуля */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
