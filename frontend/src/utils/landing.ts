/**
 * Дефолтный лендинг-путь после логина / редиректа с неизвестного маршрута.
 *
 * Логика:
 *   - HR-сторона (owner, admin, hr, superadmin)              → /dashboard
 *   - Остальные (обычные сотрудники)                        → /factorial (кабинет)
 */
import type { User } from '@/types';

export function getDefaultLandingPath(user: User | null | undefined): string {
  if (!user) return '/dashboard';

  const isPlatformAdmin = user.role === 'superadmin' || user.org_role === 'owner';
  const isHrSide = isPlatformAdmin || user.org_role === 'admin' || user.org_role === 'hr';
  if (isHrSide) return '/dashboard';
  // Сотрудник без HR-роли — в свой кабинет кадров (в Энцеладусе — /projects).
  return '/factorial';
}
