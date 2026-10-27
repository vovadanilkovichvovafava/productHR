/**
 * Дефолтный лендинг-путь после логина / редиректа с неизвестного маршрута.
 *
 * Логика:
 *   - Практика-only (член депта 'Практика', не платформ-админ) → /chats
 *   - HR-сторона (owner, admin, hr, superadmin)              → /dashboard
 *   - Остальные (лиды отделов, обычные не-HR работники)      → /projects
 */
import type { User } from '@/types';

export function getDefaultLandingPath(user: User | null | undefined): string {
  if (!user) return '/dashboard';

  const isPlatformAdmin = user.role === 'superadmin' || user.org_role === 'owner';
  const isHrSide = isPlatformAdmin || user.org_role === 'admin' || user.org_role === 'hr';
  const isPracticeMember = (user.department_names || []).some(
    (n) => n.trim().toLowerCase() === 'практика'
  );

  if (isPracticeMember && !isPlatformAdmin) return '/chats';
  if (isHrSide) return '/dashboard';
  return '/projects';
}
