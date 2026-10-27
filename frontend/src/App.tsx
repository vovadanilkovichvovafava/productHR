import { useEffect, lazy, Suspense, ComponentType } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import ErrorBoundary from '@/components/ErrorBoundary';
import { useAuthStore } from '@/stores/authStore';
import { getCurrentUser } from '@/services/api';
import Layout from '@/components/Layout';
import RoleRoute from '@/components/RoleRoute';
import { WebSocketProvider } from '@/components/WebSocketProvider';
import { getDefaultLandingPath } from '@/utils/landing';

/**
 * Редирект на дефолтный лендинг — зависит от роли/депта юзера.
 * Practice-only → /chats, остальные → /dashboard.
 */
function DefaultRedirect() {
  const user = useAuthStore((s) => s.user);
  return <Navigate to={getDefaultLandingPath(user)} replace />;
}

// Code splitting: Lazy load pages for better initial bundle size
// Login and Invite are loaded eagerly since they're entry points
import DevAccountSwitcher from '@/components/DevAccountSwitcher';
import LoginPage from '@/pages/LoginPage';
import InvitePage from '@/pages/InvitePage';

/**
 * Retry wrapper for lazy imports - handles chunk loading failures after deployments
 * Retries up to 3 times with exponential backoff before giving up
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function lazyWithRetry<T extends ComponentType<any>>(
  importFn: () => Promise<{ default: T }>,
  retries = 3,
  interval = 1000
): React.LazyExoticComponent<T> {
  return lazy(async () => {
    for (let i = 0; i < retries; i++) {
      try {
        return await importFn();
      } catch (error) {
        // Only retry on chunk loading errors
        const isChunkError =
          error instanceof Error &&
          (error.message.includes('Failed to fetch dynamically imported module') ||
            error.message.includes('Loading chunk') ||
            error.message.includes('ChunkLoadError'));

        if (!isChunkError || i === retries - 1) {
          // На финальном провале — пробрасываем ошибку в ErrorBoundary, который УЖЕ
          // умеет ловить chunk-ошибки и делать одну перезагрузку (см. ErrorBoundary.tsx,
          // componentDidCatch). Свой дубль-reload здесь убран, чтобы не было двойной
          // перезагрузки/мерцания на одном и том же chunk-сбое.
          throw error;
        }

        // Wait before retrying with exponential backoff
        console.warn(`Chunk load failed, retrying (${i + 1}/${retries})...`);
        await new Promise((resolve) => setTimeout(resolve, interval * (i + 1)));

        // Add cache-busting query param on retry
        // This helps when the old chunk URL returns 404 after deployment
      }
    }
    // This should never be reached, but TypeScript needs it
    throw new Error('Failed to load module after retries');
  });
}

// Lazy loaded pages - only loaded when navigated to
// Using lazyWithRetry to handle chunk loading failures gracefully
const DashboardPage = lazyWithRetry(() => import('@/pages/DashboardPage'));
// ContactsPage lazy import removed — /contacts routes now redirect to /all-candidates
const TrashPage = lazyWithRetry(() => import('@/pages/TrashPage'));
const UsersPage = lazyWithRetry(() => import('@/pages/UsersPage'));
const DepartmentsPage = lazyWithRetry(() => import('@/pages/DepartmentsPage'));
const SettingsPage = lazyWithRetry(() => import('@/pages/SettingsPage'));
const AdminSimulatorPage = lazyWithRetry(() => import('@/pages/AdminSimulatorPage'));
const VacanciesPage = lazyWithRetry(() => import('@/pages/VacanciesPage'));
const EmailTemplatesPage = lazyWithRetry(() => import('@/pages/EmailTemplatesPage'));
const ExportsPage = lazyWithRetry(() => import('@/pages/ExportsPage'));
const ProjectsPage = lazyWithRetry(() => import('@/pages/ProjectsPage'));
const ProjectDetailPage = lazyWithRetry(() => import('@/pages/ProjectDetailPage'));
const ProjectTaskPage = lazyWithRetry(() => import('@/pages/ProjectTaskPage'));
const AllTasksPage = lazyWithRetry(() => import('@/pages/AllTasksPage'));
const SaturnPage = lazyWithRetry(() => import('@/pages/SaturnPage'));
const TeamPage = lazyWithRetry(() => import('@/pages/TeamPage'));
const DeptManagerPage = lazyWithRetry(() => import('@/pages/DeptManagerPage'));
const AllCandidatesPage = lazyWithRetry(() => import('@/pages/AllCandidatesPage'));
const StatusesPage = lazyWithRetry(() => import('@/pages/StatusesPage'));
const RecruiterFunnelsPage = lazyWithRetry(() => import('@/pages/RecruiterFunnelsPage'));
const RecruiterWorkspacePage = lazyWithRetry(() => import('@/pages/RecruiterWorkspacePage'));
const FormBuilderPage = lazyWithRetry(() => import('@/pages/FormBuilderPage'));
const DeletedCandidatesPage = lazyWithRetry(() => import('@/pages/DeletedCandidatesPage'));
const AuditLogPage = lazyWithRetry(() => import('@/pages/AuditLogPage'));
const AiUsagePage = lazyWithRetry(() => import('@/pages/AiUsagePage'));
const PublicFormPage = lazyWithRetry(() => import('@/pages/PublicFormPage'));
const CandidatePreviewPage = lazyWithRetry(() => import('@/pages/CandidatePreviewPage'));
const DocumentTemplatesPage = lazyWithRetry(() => import('@/pages/DocumentTemplatesPage'));
const EmployeePortalPage = lazyWithRetry(() => import('@/pages/EmployeePortalPage'));
const PENDashboardPage = lazyWithRetry(() => import('@/pages/PENDashboardPage'));
const ExtensionPage = lazyWithRetry(() => import('@/pages/ExtensionPage'));
const CsvImportPage = lazyWithRetry(() => import('@/pages/CsvImportPage'));
const TimeOffPage = lazyWithRetry(() => import('@/pages/TimeOffPage'));
const BlockersPage = lazyWithRetry(() => import('@/pages/BlockersPage'));
const HRReportsPage = lazyWithRetry(() => import('@/pages/HRReportsPage'));
const FactorialModule = lazyWithRetry(() => import('@/factorial/FactorialModule'));
const CandidateArchivePage = lazyWithRetry(() => import('@/pages/CandidateArchivePage'));

// Loading fallback component for Suspense
function PageLoader() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
        <span className="text-sm text-dark-400">Загрузка...</span>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  const { setUser, setLoading } = useAuthStore();

  useEffect(() => {
    // Try to get current user - cookie is sent automatically
    getCurrentUser()
      .then(setUser)
      .catch(() => {
        // Not authenticated or session expired - just set loading to false
        // Don't call logout() here as it could clear a user that was just set
        // by a concurrent login (race condition)
      })
      .finally(() => setLoading(false));
  }, [setUser, setLoading]);

  // Pause animations when tab is not visible to save CPU/GPU
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        document.body.classList.add('animations-paused');
      } else {
        document.body.classList.remove('animations-paused');
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  // Performance mode is ON by default (saves battery/CPU)
  // Only disable if user explicitly enabled animations
  useEffect(() => {
    const animationsEnabled = localStorage.getItem('animations-enabled');
    if (animationsEnabled !== 'true') {
      document.body.classList.add('performance-mode');
    }
  }, []);

  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/invite/:token" element={<InvitePage />} />
        {/* /form/:key — короткий путь и для персональных анкет (токен), и для общих
            (slug): PublicFormPage сам определяет, что в ссылке. /form/d/:token —
            алиас для уже разосланных персональных ссылок, не ломаем. */}
        <Route path="/form/d/:token" element={<Suspense fallback={<PageLoader />}><PublicFormPage /></Suspense>} />
        <Route path="/form/:key" element={<Suspense fallback={<PageLoader />}><PublicFormPage /></Suspense>} />
        {/* Публичный предпросмотр кандидата для заказчика — вне Layout, без авторизации. */}
        <Route path="/candidate-preview/:token" element={<Suspense fallback={<PageLoader />}><CandidatePreviewPage /></Suspense>} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <WebSocketProvider>
                <Layout />
              </WebSocketProvider>
            </ProtectedRoute>
          }
        >
          {/* Wrap lazy-loaded routes in Suspense for loading state */}
          {/* Open routes — any authenticated user */}
          <Route index element={<DefaultRedirect />} />
          <Route path="dashboard" element={<Suspense fallback={<PageLoader />}><DashboardPage /></Suspense>} />
          <Route path="projects" element={<Suspense fallback={<PageLoader />}><ProjectsPage /></Suspense>} />
          <Route path="projects/:projectId" element={<Suspense fallback={<PageLoader />}><ProjectDetailPage /></Suspense>} />
          <Route path="projects/:projectId/tasks/:taskId" element={<Suspense fallback={<PageLoader />}><ProjectTaskPage /></Suspense>} />
          <Route path="all-tasks" element={<Suspense fallback={<PageLoader />}><AllTasksPage /></Suspense>} />
          <Route path="team" element={<Suspense fallback={<PageLoader />}><TeamPage /></Suspense>} />
          <Route path="timeoff" element={<Suspense fallback={<PageLoader />}><TimeOffPage /></Suspense>} />
          <Route path="blockers" element={<Suspense fallback={<PageLoader />}><BlockersPage /></Suspense>} />
          <Route path="my-profile" element={<Suspense fallback={<PageLoader />}><EmployeePortalPage /></Suspense>} />
          <Route path="factorial/*" element={<Suspense fallback={<PageLoader />}><FactorialModule /></Suspense>} />

          {/* HR routes — superadmin, owner, admin, hr (recruiter like Мария) */}
          {/* /candidates and /candidate-database removed — use /all-candidates */}
          <Route path="all-candidates" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><AllCandidatesPage /></RoleRoute></Suspense>} />
          <Route path="statuses" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><StatusesPage /></RoleRoute></Suspense>} />
          <Route path="vacancies" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><VacanciesPage /></RoleRoute></Suspense>} />
          <Route path="vacancies/:vacancyId" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><VacanciesPage /></RoleRoute></Suspense>} />
          <Route path="contacts" element={<Navigate to="/all-candidates" replace />} />
          <Route path="contacts/:entityId" element={<Navigate to="/all-candidates" replace />} />
          <Route path="my-funnels" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><RecruiterFunnelsPage /></RoleRoute></Suspense>} />
          <Route path="workspaces" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><RecruiterWorkspacePage /></RoleRoute></Suspense>} />
          <Route path="deleted-candidates" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><DeletedCandidatesPage /></RoleRoute></Suspense>} />
          <Route path="audit-log" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr_admin']}><AuditLogPage /></RoleRoute></Suspense>} />
          <Route path="ai-usage" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr_admin']}><AiUsagePage /></RoleRoute></Suspense>} />
          <Route path="form-builder" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><FormBuilderPage /></RoleRoute></Suspense>} />
          <Route path="form-builder/:formId" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><FormBuilderPage /></RoleRoute></Suspense>} />
          <Route path="document-templates" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><DocumentTemplatesPage /></RoleRoute></Suspense>} />
          <Route path="email-templates" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><EmailTemplatesPage /></RoleRoute></Suspense>} />
          <Route path="extension" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><ExtensionPage /></RoleRoute></Suspense>} />
          <Route path="analytics" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><DashboardPage /></RoleRoute></Suspense>} />
          <Route path="hr-reports" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr']}><HRReportsPage /></RoleRoute></Suspense>} />
          <Route path="saturn" element={<Suspense fallback={<PageLoader />}><SaturnPage /></Suspense>} />

          {/* HR Admin routes — superadmin, owner, admin (Настя). NOT for hr recruiter */}
          <Route path="pen" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr_admin']}><PENDashboardPage /></RoleRoute></Suspense>} />
          <Route path="exports" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr_admin']}><ExportsPage /></RoleRoute></Suspense>} />
          <Route path="import" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr_admin']}><CsvImportPage /></RoleRoute></Suspense>} />
          <Route path="employees" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr_admin']}><EmployeePortalPage /></RoleRoute></Suspense>} />
          <Route path="dept-manager" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr_admin']}><DeptManagerPage /></RoleRoute></Suspense>} />
          <Route path="trash" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['hr_admin']}><TrashPage /></RoleRoute></Suspense>} />

          {/* Management routes — superadmin and owner only */}
          <Route path="departments" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['management']}><DepartmentsPage /></RoleRoute></Suspense>} />
          <Route path="settings" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['management']}><SettingsPage /></RoleRoute></Suspense>} />

          {/* Superadmin only */}
          <Route path="users" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['superadmin']}><UsersPage /></RoleRoute></Suspense>} />
          <Route path="candidate-archive" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['superadmin']}><CandidateArchivePage /></RoleRoute></Suspense>} />
          <Route path="admin" element={<Navigate to="/admin/simulator" replace />} />
          <Route path="admin/simulator" element={<Suspense fallback={<PageLoader />}><RoleRoute allow={['superadmin']}><AdminSimulatorPage /></RoleRoute></Suspense>} />
          {/* Catch-all for unknown routes */}
          <Route path="*" element={<DefaultRedirect />} />
        </Route>
      </Routes>
      <DevAccountSwitcher />
    </ErrorBoundary>
  );
}
