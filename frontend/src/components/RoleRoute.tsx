/**
 * RoleRoute — route-level access guard based on user role.
 *
 * Role hierarchy (OrgRole):
 *   superadmin  — Витя, Саша (system-wide, sees everything)
 *   owner       — org owner (full org access)
 *   admin       — Настя = HR Admin (всё кроме /users: ПЭН, экспорт, импорт, сотрудники, настройки)
 *   hr          — Мария = HR рекрутер (кандидаты, воронки, вакансии, созвоны, практиканты)
 *   member      — сотрудники (профиль, проекты, документы)
 *
 * Shortcuts:
 *   'hr_all'    — superadmin | owner | admin | hr  (anyone with HR access)
 *   'hr_admin'  — superadmin | owner | admin       (HR admin level: PEN, exports, settings)
 *   'management'— superadmin | owner               (org management: users, departments)
 *   'practice'  — член департамента 'Практика' (любой org_role)
 *   'any'       — any authenticated user
 */

import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

interface RoleRouteProps {
  children: React.ReactNode;
  allow: string[];
  feature?: string;
}

export default function RoleRoute({ children, allow, feature }: RoleRouteProps) {
  const { user, hasFeature } = useAuthStore();

  if (!user) return <Navigate to="/login" replace />;

  // Feature check
  if (feature && !hasFeature(feature) && user.role !== 'superadmin') {
    return <AccessDenied />;
  }

  // 'any' / 'member' = any authenticated user
  if (allow.includes('any') || allow.includes('member')) return <>{children}</>;

  // Expand shortcuts
  const roles = new Set(allow);
  if (roles.has('hr_all') || roles.has('hr')) {
    roles.add('superadmin');
    roles.add('owner');
    roles.add('admin');
    roles.add('hr_role');  // matches org_role === 'hr'
  }
  if (roles.has('hr_admin')) {
    roles.add('superadmin');
    roles.add('owner');
    roles.add('admin');
  }
  if (roles.has('management')) {
    roles.add('superadmin');
    roles.add('owner');
  }

  // Check access
  const isPracticeMember = (user.department_names || []).some(n => n.trim().toLowerCase() === 'практика');
  const hasAccess =
    // System superadmin
    (roles.has('superadmin') && user.role === 'superadmin') ||
    // Org owner (or superadmin inherits owner)
    (roles.has('owner') && (user.org_role === 'owner' || user.role === 'superadmin')) ||
    // Org admin = HR Admin (owner inherits admin, superadmin inherits admin)
    (roles.has('admin') && (user.org_role === 'admin' || user.org_role === 'owner' || user.role === 'superadmin')) ||
    // Org hr = HR recruiter
    (roles.has('hr_role') && (user.org_role === 'hr' || user.org_role === 'admin' || user.org_role === 'owner' || user.role === 'superadmin')) ||
    // Наблюдатель (is_readonly) — ментор с ЧИТАЮЩИМ доступом к HR. Пускаем на
    // любой роут, открытый рекрутёрам ('hr'/'hr_all' → добавляет 'hr_role'):
    // кандидаты/статусы/воронки/аналитика/заявки. Управленческие 'hr_admin'-роуты
    // (экспорт/импорт/корзина) сюда НЕ входят — они не добавляют 'hr_role'. Любая
    // запись всё равно блокируется на бэке (403) и баннером «Режим наблюдателя».
    (user.is_readonly === true && roles.has('hr_role')) ||
    // Department-based: член депта 'Практика'
    (roles.has('practice') && isPracticeMember);

  if (!hasAccess) return <AccessDenied />;

  return <>{children}</>;
}

function AccessDenied() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-8">
      <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-4">
        <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728L5.636 5.636" />
        </svg>
      </div>
      <h2 className="text-xl font-semibold text-white mb-2">Доступ запрещён</h2>
      <p className="text-white/40 text-sm max-w-md">
        У вас нет прав для просмотра этой страницы. Обратитесь к администратору.
      </p>
    </div>
  );
}
