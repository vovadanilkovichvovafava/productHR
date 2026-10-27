import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useAuthStore } from '../authStore';
import type { User, Session } from '@/types';
import * as api from '@/services/api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock API functions
vi.mock('@/services/api', async () => {
  const actual = await vi.importActual('@/services/api');
  return {
    ...actual,
    getMyPermissions: vi.fn().mockResolvedValue({
      permissions: {},
      source: 'default',
      custom_role_name: null,
    }),
    getMyMenu: vi.fn().mockResolvedValue({ items: [] }),
    getMyFeatures: vi.fn().mockResolvedValue({ features: [] }),
    getSessions: vi.fn(),
    logoutAllDevices: vi.fn(),
    revokeSession: vi.fn(),
  };
});

describe('authStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useAuthStore.setState({
      user: null,
      isLoading: true,
      originalUser: null,
      permissions: {},
      permissionsSource: null,
      customRoleName: null,
      menuItems: [],
      permissionsLoading: false,
      features: [],
      sessions: [],
      sessionsLoading: false,
      featurePollingInterval: null,
    });
    mockFetch.mockClear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isLoading).toBe(true);
      expect(state.originalUser).toBeNull();
    });
  });

  describe('setUser', () => {
    it('should set user', () => {
      const mockUser: User = {
        id: 1,
        email: 'test@test.com',
        name: 'Test User',
        role: 'admin',
        org_role: 'owner',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.getState().setUser(mockUser);
      expect(useAuthStore.getState().user).toEqual(mockUser);
    });

    it('should clear user when set to null', () => {
      const mockUser: User = {
        id: 1,
        email: 'test@test.com',
        name: 'Test User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.getState().setUser(mockUser);
      expect(useAuthStore.getState().user).toEqual(mockUser);

      useAuthStore.getState().setUser(null);
      expect(useAuthStore.getState().user).toBeNull();
    });
  });

  describe('setLoading', () => {
    it('should set loading state', () => {
      useAuthStore.getState().setLoading(false);
      expect(useAuthStore.getState().isLoading).toBe(false);

      useAuthStore.getState().setLoading(true);
      expect(useAuthStore.getState().isLoading).toBe(true);
    });
  });

  describe('logout', () => {
    it('should clear user and originalUser', () => {
      const mockUser: User = {
        id: 1,
        email: 'test@test.com',
        name: 'Test User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };
      const mockOriginalUser: User = {
        id: 2,
        email: 'admin@test.com',
        name: 'Admin User',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user: mockUser, originalUser: mockOriginalUser });
      useAuthStore.getState().logout();

      expect(useAuthStore.getState().user).toBeNull();
      expect(useAuthStore.getState().originalUser).toBeNull();
    });
  });

  describe('impersonate', () => {
    it('should throw error if not authenticated', async () => {
      useAuthStore.setState({ user: null });

      await expect(useAuthStore.getState().impersonate(123)).rejects.toThrow(
        'Not authenticated'
      );
    });

    it('should successfully impersonate a user', async () => {
      const currentUser: User = {
        id: 1,
        email: 'admin@test.com',
        name: 'Admin User',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      const targetUser: User = {
        id: 2,
        email: 'user@test.com',
        name: 'Target User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user: currentUser });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ user: targetUser }),
      });

      await useAuthStore.getState().impersonate(2);

      const state = useAuthStore.getState();
      expect(state.originalUser).toEqual(currentUser);
      expect(state.user?.id).toBe(2);
      expect(state.user?.is_impersonating).toBe(true);
      expect(state.user?.original_user_id).toBe(1);
      expect(state.user?.original_user_name).toBe('Admin User');
    });

    it('should handle impersonation failure', async () => {
      const currentUser: User = {
        id: 1,
        email: 'admin@test.com',
        name: 'Admin User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user: currentUser });

      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Permission denied' }),
      });

      await expect(useAuthStore.getState().impersonate(2)).rejects.toThrow(
        'Permission denied'
      );
    });

    it('should handle network error during impersonation', async () => {
      const currentUser: User = {
        id: 1,
        email: 'admin@test.com',
        name: 'Admin User',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user: currentUser });

      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      await expect(useAuthStore.getState().impersonate(2)).rejects.toThrow(
        'Network error'
      );
    });
  });

  describe('exitImpersonation', () => {
    it('should throw error if not currently impersonating', async () => {
      useAuthStore.setState({ user: null, originalUser: null });

      await expect(useAuthStore.getState().exitImpersonation()).rejects.toThrow(
        'Not currently impersonating'
      );
    });

    it('should successfully exit impersonation', async () => {
      const originalUser: User = {
        id: 1,
        email: 'admin@test.com',
        name: 'Admin User',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      const impersonatedUser: User = {
        id: 2,
        email: 'user@test.com',
        name: 'Target User',
        role: 'admin',
        is_impersonating: true,
        original_user_id: 1,
        original_user_name: 'Admin User',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user: impersonatedUser, originalUser });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ user: originalUser }),
      });

      await useAuthStore.getState().exitImpersonation();

      const state = useAuthStore.getState();
      expect(state.user).toEqual(originalUser);
      expect(state.originalUser).toBeNull();
    });

    it('should handle exit impersonation failure', async () => {
      const originalUser: User = {
        id: 1,
        email: 'admin@test.com',
        name: 'Admin User',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user: null, originalUser });

      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Session expired' }),
      });

      await expect(useAuthStore.getState().exitImpersonation()).rejects.toThrow(
        'Session expired'
      );
    });
  });

  describe('isImpersonating', () => {
    it('should return true when impersonating', () => {
      const impersonatedUser: User = {
        id: 2,
        email: 'user@test.com',
        name: 'Target User',
        role: 'admin',
        is_impersonating: true,
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user: impersonatedUser });
      expect(useAuthStore.getState().isImpersonating()).toBe(true);
    });

    it('should return false when not impersonating', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().isImpersonating()).toBe(false);
    });

    it('should return false when user is null', () => {
      useAuthStore.setState({ user: null });
      expect(useAuthStore.getState().isImpersonating()).toBe(false);
    });
  });

  describe('role helper methods', () => {
    describe('isSuperAdmin', () => {
      it('should return true for superadmin role', () => {
        const user: User = {
          id: 1,
          email: 'admin@test.com',
          name: 'Super Admin',
          role: 'superadmin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isSuperAdmin()).toBe(true);
      });

      it('should return false for non-superadmin role', () => {
        const user: User = {
          id: 1,
          email: 'admin@test.com',
          name: 'Admin',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isSuperAdmin()).toBe(false);
      });

      it('should return false when user is null', () => {
        useAuthStore.setState({ user: null });
        expect(useAuthStore.getState().isSuperAdmin()).toBe(false);
      });
    });

    describe('isOwner', () => {
      it('should return true for owner org_role', () => {
        const user: User = {
          id: 1,
          email: 'owner@test.com',
          name: 'Owner',
          role: 'admin',
          org_role: 'owner',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isOwner()).toBe(true);
      });

      it('should return false for non-owner org_role', () => {
        const user: User = {
          id: 1,
          email: 'admin@test.com',
          name: 'Admin',
          role: 'admin',
          org_role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isOwner()).toBe(false);
      });
    });

    describe('isAdmin', () => {
      it('should return true for org admin', () => {
        const user: User = {
          id: 1,
          email: 'admin@test.com',
          name: 'Admin',
          role: 'admin',
          org_role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isAdmin()).toBe(true);
      });

      it('should return true for department lead', () => {
        const user: User = {
          id: 1,
          email: 'lead@test.com',
          name: 'Lead',
          role: 'admin',
          department_role: 'lead',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isAdmin()).toBe(true);
      });

      it('should return true for department sub_admin', () => {
        const user: User = {
          id: 1,
          email: 'subadmin@test.com',
          name: 'Sub Admin',
          role: 'admin',
          department_role: 'sub_admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isAdmin()).toBe(true);
      });

      it('should return false for regular member', () => {
        const user: User = {
          id: 1,
          email: 'member@test.com',
          name: 'Member',
          role: 'admin',
          org_role: 'member',
          department_role: 'member',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isAdmin()).toBe(false);
      });
    });

    describe('isSubAdmin', () => {
      it('should return true for sub_admin department_role', () => {
        const user: User = {
          id: 1,
          email: 'subadmin@test.com',
          name: 'Sub Admin',
          role: 'admin',
          department_role: 'sub_admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isSubAdmin()).toBe(true);
      });

      it('should return false for non-sub_admin', () => {
        const user: User = {
          id: 1,
          email: 'member@test.com',
          name: 'Member',
          role: 'admin',
          department_role: 'member',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isSubAdmin()).toBe(false);
      });
    });

    describe('isMember', () => {
      it('should return true for member org_role and department_role', () => {
        const user: User = {
          id: 1,
          email: 'member@test.com',
          name: 'Member',
          role: 'admin',
          org_role: 'member',
          department_role: 'member',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isMember()).toBe(true);
      });

      it('should return false for admin org_role', () => {
        const user: User = {
          id: 1,
          email: 'admin@test.com',
          name: 'Admin',
          role: 'admin',
          org_role: 'admin',
          department_role: 'member',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isMember()).toBe(false);
      });

      it('should return false for department lead', () => {
        const user: User = {
          id: 1,
          email: 'lead@test.com',
          name: 'Lead',
          role: 'admin',
          org_role: 'member',
          department_role: 'lead',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isMember()).toBe(false);
      });
    });

    describe('isDepartmentAdmin', () => {
      it('should return true for department lead', () => {
        const user: User = {
          id: 1,
          email: 'lead@test.com',
          name: 'Lead',
          role: 'admin',
          department_role: 'lead',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isDepartmentAdmin()).toBe(true);
      });

      it('should return true for sub_admin', () => {
        const user: User = {
          id: 1,
          email: 'subadmin@test.com',
          name: 'Sub Admin',
          role: 'admin',
          department_role: 'sub_admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isDepartmentAdmin()).toBe(true);
      });

      it('should return false for member', () => {
        const user: User = {
          id: 1,
          email: 'member@test.com',
          name: 'Member',
          role: 'admin',
          department_role: 'member',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user });
        expect(useAuthStore.getState().isDepartmentAdmin()).toBe(false);
      });
    });
  });

  describe('canShareTo', () => {
    it('should return false when sharing to self', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(1)).toBe(false);
    });

    it('should return false when user is null', () => {
      useAuthStore.setState({ user: null });
      expect(useAuthStore.getState().canShareTo(2)).toBe(false);
    });

    it('should allow superadmin to share to anyone', () => {
      const user: User = {
        id: 1,
        email: 'superadmin@test.com',
        name: 'Super Admin',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2)).toBe(true);
    });

    it('should allow owner to share to anyone in organization', () => {
      const user: User = {
        id: 1,
        email: 'owner@test.com',
        name: 'Owner',
        role: 'admin',
        org_role: 'owner',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2)).toBe(true);
    });

    it('should allow department admin to share to owner', () => {
      const user: User = {
        id: 1,
        email: 'lead@test.com',
        name: 'Lead',
        role: 'admin',
        department_role: 'lead',
        department_id: 1,
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2, 'owner')).toBe(true);
    });

    it('should allow department admin to share to superadmin', () => {
      const user: User = {
        id: 1,
        email: 'lead@test.com',
        name: 'Lead',
        role: 'admin',
        department_role: 'lead',
        department_id: 1,
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2, 'superadmin')).toBe(true);
    });

    it('should allow department admin to share to other department admins', () => {
      const user: User = {
        id: 1,
        email: 'lead@test.com',
        name: 'Lead',
        role: 'admin',
        department_role: 'lead',
        department_id: 1,
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2, 'lead', 2)).toBe(true);
    });

    it('should allow department admin to share to members in same department', () => {
      const user: User = {
        id: 1,
        email: 'lead@test.com',
        name: 'Lead',
        role: 'admin',
        department_role: 'lead',
        department_id: 1,
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2, 'member', 1)).toBe(true);
    });

    it('should not allow department admin to share to members in different department', () => {
      const user: User = {
        id: 1,
        email: 'lead@test.com',
        name: 'Lead',
        role: 'admin',
        department_role: 'lead',
        department_id: 1,
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2, 'member', 2)).toBe(false);
    });

    it('should allow member to share within their department', () => {
      const user: User = {
        id: 1,
        email: 'member@test.com',
        name: 'Member',
        role: 'admin',
        org_role: 'member',
        department_role: 'member',
        department_id: 1,
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2, 'member', 1)).toBe(true);
    });

    it('should not allow member to share outside their department', () => {
      const user: User = {
        id: 1,
        email: 'member@test.com',
        name: 'Member',
        role: 'admin',
        org_role: 'member',
        department_role: 'member',
        department_id: 1,
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareTo(2, 'member', 2)).toBe(false);
    });
  });

  describe('canDeleteUser', () => {
    it('should return false when trying to delete self', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canDeleteUser(1)).toBe(false);
    });

    it('should return false when user is null', () => {
      useAuthStore.setState({ user: null });
      expect(useAuthStore.getState().canDeleteUser(2)).toBe(false);
    });

    it('should allow superadmin to delete anyone except other superadmins', () => {
      const user: User = {
        id: 1,
        email: 'superadmin@test.com',
        name: 'Super Admin',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canDeleteUser(2, 'admin')).toBe(true);
      expect(useAuthStore.getState().canDeleteUser(2, 'owner')).toBe(true);
      expect(useAuthStore.getState().canDeleteUser(2, 'superadmin')).toBe(false);
    });

    it('should allow owner to delete anyone except superadmin and other owners', () => {
      const user: User = {
        id: 1,
        email: 'owner@test.com',
        name: 'Owner',
        role: 'admin',
        org_role: 'owner',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canDeleteUser(2, 'admin')).toBe(true);
      expect(useAuthStore.getState().canDeleteUser(2, 'member')).toBe(true);
      expect(useAuthStore.getState().canDeleteUser(2, 'owner')).toBe(false);
      expect(useAuthStore.getState().canDeleteUser(2, 'superadmin')).toBe(false);
    });

    it('should allow department lead to delete sub_admins and members', () => {
      const user: User = {
        id: 1,
        email: 'lead@test.com',
        name: 'Lead',
        role: 'admin',
        department_role: 'lead',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canDeleteUser(2, 'sub_admin')).toBe(true);
      expect(useAuthStore.getState().canDeleteUser(2, 'member')).toBe(true);
      expect(useAuthStore.getState().canDeleteUser(2, 'lead')).toBe(false);
      expect(useAuthStore.getState().canDeleteUser(2, 'owner')).toBe(false);
    });

    it('should not allow sub_admin to delete other users', () => {
      const user: User = {
        id: 1,
        email: 'subadmin@test.com',
        name: 'Sub Admin',
        role: 'admin',
        department_role: 'sub_admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canDeleteUser(2, 'member')).toBe(false);
      expect(useAuthStore.getState().canDeleteUser(2, 'sub_admin')).toBe(false);
    });
  });

  describe('canEditResource', () => {
    it('should return false when user is null', () => {
      useAuthStore.setState({ user: null });
      expect(useAuthStore.getState().canEditResource({})).toBe(false);
    });

    it('should allow superadmin to edit everything', () => {
      const user: User = {
        id: 1,
        email: 'superadmin@test.com',
        name: 'Super Admin',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canEditResource({ owner_id: 2 })).toBe(true);
    });

    it('should allow owner to edit everything', () => {
      const user: User = {
        id: 1,
        email: 'owner@test.com',
        name: 'Owner',
        role: 'admin',
        org_role: 'owner',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canEditResource({ owner_id: 2 })).toBe(true);
    });

    it('should allow owner to edit their own resources', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canEditResource({ owner_id: 1 })).toBe(true);
      expect(useAuthStore.getState().canEditResource({ is_mine: true })).toBe(true);
    });

    it('should allow edit access with edit permission', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(
        useAuthStore.getState().canEditResource({ owner_id: 2, access_level: 'edit' })
      ).toBe(true);
    });

    it('should allow edit access with full permission', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(
        useAuthStore.getState().canEditResource({ owner_id: 2, access_level: 'full' })
      ).toBe(true);
    });

    it('should not allow edit access with view permission', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(
        useAuthStore.getState().canEditResource({ owner_id: 2, access_level: 'view' })
      ).toBe(false);
    });
  });

  describe('canDeleteResource', () => {
    it('should return false when user is null', () => {
      useAuthStore.setState({ user: null });
      expect(useAuthStore.getState().canDeleteResource({})).toBe(false);
    });

    it('should allow superadmin to delete everything', () => {
      const user: User = {
        id: 1,
        email: 'superadmin@test.com',
        name: 'Super Admin',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canDeleteResource({ owner_id: 2 })).toBe(true);
    });

    it('should allow owner to delete everything', () => {
      const user: User = {
        id: 1,
        email: 'owner@test.com',
        name: 'Owner',
        role: 'admin',
        org_role: 'owner',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canDeleteResource({ owner_id: 2 })).toBe(true);
    });

    it('should allow owner to delete their own resources', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canDeleteResource({ owner_id: 1 })).toBe(true);
      expect(useAuthStore.getState().canDeleteResource({ is_mine: true })).toBe(true);
    });

    it('should not allow delete even with full permission if not owner', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(
        useAuthStore.getState().canDeleteResource({ owner_id: 2, access_level: 'full' })
      ).toBe(false);
    });
  });

  describe('canShareResource', () => {
    it('should return false when user is null', () => {
      useAuthStore.setState({ user: null });
      expect(useAuthStore.getState().canShareResource({})).toBe(false);
    });

    it('should allow superadmin to share everything', () => {
      const user: User = {
        id: 1,
        email: 'superadmin@test.com',
        name: 'Super Admin',
        role: 'superadmin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareResource({ owner_id: 2 })).toBe(true);
    });

    it('should allow owner to share everything', () => {
      const user: User = {
        id: 1,
        email: 'owner@test.com',
        name: 'Owner',
        role: 'admin',
        org_role: 'owner',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareResource({ owner_id: 2 })).toBe(true);
    });

    it('should allow owner to share their own resources', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(useAuthStore.getState().canShareResource({ owner_id: 1 })).toBe(true);
      expect(useAuthStore.getState().canShareResource({ is_mine: true })).toBe(true);
    });

    it('should allow sharing with full permission', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(
        useAuthStore.getState().canShareResource({ owner_id: 2, access_level: 'full' })
      ).toBe(true);
    });

    it('should not allow sharing with edit permission', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(
        useAuthStore.getState().canShareResource({ owner_id: 2, access_level: 'edit' })
      ).toBe(false);
    });

    it('should not allow sharing with view permission', () => {
      const user: User = {
        id: 1,
        email: 'user@test.com',
        name: 'User',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user });
      expect(
        useAuthStore.getState().canShareResource({ owner_id: 2, access_level: 'view' })
      ).toBe(false);
    });
  });

  describe('sessions management', () => {
    const mockSessions: Session[] = [
      {
        id: 'session-1',
        user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        ip_address: '192.168.1.1',
        created_at: '2024-01-01T10:00:00Z',
        last_activity: '2024-01-01T12:00:00Z',
        is_current: true,
      },
      {
        id: 'session-2',
        user_agent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)',
        ip_address: '192.168.1.2',
        created_at: '2024-01-01T08:00:00Z',
        last_activity: '2024-01-01T11:00:00Z',
        is_current: false,
      },
    ];

    describe('fetchSessions', () => {
      it('should not fetch sessions when user is null', async () => {
        useAuthStore.setState({ user: null });

        await useAuthStore.getState().fetchSessions();

        expect(api.getSessions).not.toHaveBeenCalled();
        expect(useAuthStore.getState().sessions).toEqual([]);
      });

      it('should fetch and set sessions successfully', async () => {
        const mockUser: User = {
          id: 1,
          email: 'test@test.com',
          name: 'Test User',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user: mockUser });
        vi.mocked(api.getSessions).mockResolvedValueOnce(mockSessions);

        await useAuthStore.getState().fetchSessions();

        expect(api.getSessions).toHaveBeenCalled();
        expect(useAuthStore.getState().sessions).toEqual(mockSessions);
        expect(useAuthStore.getState().sessionsLoading).toBe(false);
      });

      it('should set sessionsLoading to true while fetching', async () => {
        const mockUser: User = {
          id: 1,
          email: 'test@test.com',
          name: 'Test User',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user: mockUser });

        let loadingDuringFetch = false;
        vi.mocked(api.getSessions).mockImplementationOnce(async () => {
          loadingDuringFetch = useAuthStore.getState().sessionsLoading;
          return mockSessions;
        });

        await useAuthStore.getState().fetchSessions();

        expect(loadingDuringFetch).toBe(true);
        expect(useAuthStore.getState().sessionsLoading).toBe(false);
      });

      it('should handle fetch sessions failure', async () => {
        const mockUser: User = {
          id: 1,
          email: 'test@test.com',
          name: 'Test User',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user: mockUser });
        vi.mocked(api.getSessions).mockRejectedValueOnce(new Error('Network error'));

        await useAuthStore.getState().fetchSessions();

        expect(useAuthStore.getState().sessions).toEqual([]);
        expect(useAuthStore.getState().sessionsLoading).toBe(false);
      });
    });

    describe('logoutAllDevices', () => {
      it('should throw error if not authenticated', async () => {
        useAuthStore.setState({ user: null });

        await expect(useAuthStore.getState().logoutAllDevices()).rejects.toThrow(
          'Not authenticated'
        );
      });

      it('should successfully logout from all devices', async () => {
        const mockUser: User = {
          id: 1,
          email: 'test@test.com',
          name: 'Test User',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user: mockUser, sessions: mockSessions });
        vi.mocked(api.logoutAllDevices).mockResolvedValueOnce({
          success: true,
          sessions_revoked: 2,
        });

        const result = await useAuthStore.getState().logoutAllDevices();

        expect(api.logoutAllDevices).toHaveBeenCalled();
        expect(result.sessions_revoked).toBe(2);
        expect(useAuthStore.getState().sessions).toEqual([]);
      });

      it('should handle logout all devices failure', async () => {
        const mockUser: User = {
          id: 1,
          email: 'test@test.com',
          name: 'Test User',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user: mockUser, sessions: mockSessions });
        vi.mocked(api.logoutAllDevices).mockRejectedValueOnce(new Error('Server error'));

        await expect(useAuthStore.getState().logoutAllDevices()).rejects.toThrow(
          'Server error'
        );
        // Sessions should not be cleared on failure
        expect(useAuthStore.getState().sessions).toEqual(mockSessions);
      });
    });

    describe('revokeSession', () => {
      it('should throw error if not authenticated', async () => {
        useAuthStore.setState({ user: null });

        await expect(useAuthStore.getState().revokeSession('session-1')).rejects.toThrow(
          'Not authenticated'
        );
      });

      it('should successfully revoke a session', async () => {
        const mockUser: User = {
          id: 1,
          email: 'test@test.com',
          name: 'Test User',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user: mockUser, sessions: mockSessions });
        vi.mocked(api.revokeSession).mockResolvedValueOnce({ success: true });

        await useAuthStore.getState().revokeSession('session-2');

        expect(api.revokeSession).toHaveBeenCalledWith('session-2');
        expect(useAuthStore.getState().sessions).toHaveLength(1);
        expect(useAuthStore.getState().sessions[0].id).toBe('session-1');
      });

      it('should handle revoke session failure', async () => {
        const mockUser: User = {
          id: 1,
          email: 'test@test.com',
          name: 'Test User',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user: mockUser, sessions: mockSessions });
        vi.mocked(api.revokeSession).mockRejectedValueOnce(new Error('Session not found'));

        await expect(useAuthStore.getState().revokeSession('session-3')).rejects.toThrow(
          'Session not found'
        );
        // Sessions should not be modified on failure
        expect(useAuthStore.getState().sessions).toEqual(mockSessions);
      });
    });

    describe('logout clears sessions', () => {
      it('should clear sessions on logout', () => {
        const mockUser: User = {
          id: 1,
          email: 'test@test.com',
          name: 'Test User',
          role: 'admin',
          created_at: '2024-01-01T00:00:00Z',
        };

        useAuthStore.setState({ user: mockUser, sessions: mockSessions, sessionsLoading: true });
        useAuthStore.getState().logout();

        expect(useAuthStore.getState().sessions).toEqual([]);
        expect(useAuthStore.getState().sessionsLoading).toBe(false);
      });
    });
  });
});
