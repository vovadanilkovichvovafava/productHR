/**
 * «Управление ролями и пользователями» (Настройки → роли).
 *
 * Экран из трёх вкладок: «Пользователи» (по умолчанию), «Кастомные роли»,
 * «Матрица прав». Доступ — суперадмин или владелец/админ организации.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RoleManagement from '../RoleManagement';
import * as api from '@/services/api';

vi.mock('@/services/api', async () => {
  const actual = await vi.importActual('@/services/api');
  return {
    ...actual,
    getCustomRoles: vi.fn(),
    createCustomRole: vi.fn(),
    updateCustomRole: vi.fn(),
    deleteCustomRole: vi.fn(),
    setRolePermission: vi.fn(),
    removeRolePermission: vi.fn(),
    getUsers: vi.fn(),
    assignCustomRole: vi.fn(),
    unassignCustomRole: vi.fn(),
    getPermissionAuditLogs: vi.fn(),
    getOrgMembers: vi.fn(),
    updateMemberRole: vi.fn(),
    getMyOrgRole: vi.fn(),
  };
});

const authState: { user: { id: number; role: string } } = {
  user: { id: 1, role: 'superadmin' },
};
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => authState,
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

const mockFn = <T,>(f: T) => f as unknown as ReturnType<typeof vi.fn>;

const roles: api.CustomRole[] = [
  {
    id: 1,
    name: 'Контент-менеджер',
    description: 'Ведёт контент',
    base_role: 'admin',
    created_at: '2026-01-01T00:00:00Z',
    is_active: true,
    permission_overrides: [{ id: 1, role_id: 1, permission: 'can_create_resources', allowed: true }],
  },
  {
    id: 2,
    name: 'Наблюдатель',
    description: 'Только смотрит',
    base_role: 'member',
    created_at: '2026-01-01T00:00:00Z',
    is_active: false,
    permission_overrides: [],
  },
];

const members = [
  { id: 10, user_id: 1, user_name: 'Ильнар', user_email: 'ilnar@test.ru', role: 'owner', has_full_access: true, created_at: '' },
  { id: 11, user_id: 2, user_name: 'Мария', user_email: 'maria@test.ru', role: 'admin', has_full_access: true, created_at: '' },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RoleManagement />
    </QueryClientProvider>,
  );
}

async function openRolesTab() {
  fireEvent.click(await screen.findByRole('button', { name: /Кастомные роли/ }));
}

describe('RoleManagement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = { id: 1, role: 'superadmin' };
    mockFn(api.getMyOrgRole).mockResolvedValue({ role: 'owner' });
    mockFn(api.getCustomRoles).mockResolvedValue(roles);
    mockFn(api.getOrgMembers).mockResolvedValue(members);
    mockFn(api.getPermissionAuditLogs).mockResolvedValue([]);
    mockFn(api.createCustomRole).mockResolvedValue({ ...roles[0], id: 3 });
  });

  describe('доступ', () => {
    it('обычному участнику экран закрыт', async () => {
      authState.user = { id: 5, role: 'member' };
      mockFn(api.getMyOrgRole).mockResolvedValue({ role: 'member' });
      renderPage();
      expect(
        await screen.findByText('Требуется доступ администратора или владельца организации'),
      ).toBeInTheDocument();
    });

    it('админу организации открыт', async () => {
      authState.user = { id: 2, role: 'member' };
      mockFn(api.getMyOrgRole).mockResolvedValue({ role: 'admin' });
      renderPage();
      expect(await screen.findByText('Управление ролями и пользователями')).toBeInTheDocument();
    });
  });

  describe('вкладка «Пользователи» (по умолчанию)', () => {
    it('показывает участников и отмечает текущего', async () => {
      renderPage();
      expect(await screen.findByText('Мария')).toBeInTheDocument();
      expect(screen.getByText('Ильнар')).toBeInTheDocument();
      expect(screen.getByText('Это вы')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Пользователи \(2\)/ })).toBeInTheDocument();
    });

    it('кнопка «Новая роль» есть только на вкладке ролей', async () => {
      renderPage();
      await screen.findByText('Мария');
      expect(screen.queryByRole('button', { name: /Новая роль/ })).not.toBeInTheDocument();
      await openRolesTab();
      expect(screen.getByRole('button', { name: /Новая роль/ })).toBeInTheDocument();
    });
  });

  describe('вкладка «Кастомные роли»', () => {
    it('показывает карточки ролей с описанием, основой и числом переопределений', async () => {
      renderPage();
      await openRolesTab();
      expect(await screen.findByText('Контент-менеджер')).toBeInTheDocument();
      expect(screen.getByText('Ведёт контент')).toBeInTheDocument();
      expect(screen.getByText('Основа: Администратор')).toBeInTheDocument();
      expect(screen.getByText('1 переопределение')).toBeInTheDocument();
      expect(screen.getByText('0 переопределений')).toBeInTheDocument();
      expect(screen.getAllByText('Настроить права')).toHaveLength(2);
    });

    it('помечает неактивную роль', async () => {
      renderPage();
      await openRolesTab();
      await screen.findByText('Наблюдатель');
      expect(screen.getByText('Неактивна')).toBeInTheDocument();
    });

    it('пустое состояние, если ролей нет', async () => {
      mockFn(api.getCustomRoles).mockResolvedValue([]);
      renderPage();
      await openRolesTab();
      expect(await screen.findByText('Создайте первую кастомную роль для начала работы')).toBeInTheDocument();
    });
  });

  describe('создание роли', () => {
    it('создаёт роль с введённым названием и выбранной основой', async () => {
      renderPage();
      await openRolesTab();
      fireEvent.click(screen.getByRole('button', { name: /Новая роль/ }));

      expect(await screen.findByText('Создать кастомную роль')).toBeInTheDocument();
      const submit = screen.getByRole('button', { name: /^Создать$/ });
      expect(submit).toBeDisabled();

      await userEvent.type(screen.getByPlaceholderText('Например: Контент-менеджер'), 'Сорсер');
      await userEvent.selectOptions(screen.getByLabelText('Базовая роль'), 'admin');
      expect(submit).not.toBeDisabled();
      fireEvent.click(submit);

      await waitFor(() =>
        expect(api.createCustomRole).toHaveBeenCalledWith({
          name: 'Сорсер',
          description: '',
          base_role: 'admin',
        }),
      );
    });
  });

  describe('журнал', () => {
    it('открывается кнопкой «Журнал» и грузит записи только тогда', async () => {
      renderPage();
      await screen.findByText('Мария');
      expect(api.getPermissionAuditLogs).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: /Журнал/ }));
      expect(await screen.findByText('Журнал изменений прав')).toBeInTheDocument();
      await waitFor(() => expect(api.getPermissionAuditLogs).toHaveBeenCalledWith({ limit: 50 }));
      expect(await screen.findByText('Журнал пока пуст')).toBeInTheDocument();
    });
  });
});
