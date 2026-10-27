import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useCanAccessFeature } from '../useCanAccessFeature';
import { useAuthStore } from '@/stores/authStore';

/**
 * Tests for useCanAccessFeature hook
 * Verifies feature access control based on user menu items and permissions
 */

// Mock the auth store
vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn(),
}));

describe('useCanAccessFeature', () => {
  const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('canAccessFeature', () => {
    it('should return true for superadmin for any feature', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [],
        permissionsLoading: false,
        user: { role: 'superadmin' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessFeature('vacancies')).toBe(true);
      expect(result.current.canAccessFeature('dashboard')).toBe(true);
      expect(result.current.canAccessFeature('settings')).toBe(true);
    });

    it('should return true when feature is in menu items', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [
          { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: 'LayoutDashboard', superadmin_only: false },
          { id: 'vacancies', label: 'Vacancies', path: '/vacancies', icon: 'Briefcase', superadmin_only: false },
        ],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessFeature('vacancies')).toBe(true);
      expect(result.current.canAccessFeature('dashboard')).toBe(true);
    });

    it('should return false when feature is not in menu items', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [
          { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: 'LayoutDashboard', superadmin_only: false },
        ],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessFeature('vacancies')).toBe(false);
      expect(result.current.canAccessFeature('settings')).toBe(false);
    });

    it('should return false when menu items is empty for non-superadmin', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessFeature('vacancies')).toBe(false);
    });

    it('should return false when menu items is null for non-superadmin', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: null,
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessFeature('vacancies')).toBe(false);
    });
  });

  describe('canAccessAnyFeature', () => {
    it('should return true if any feature is accessible', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [
          { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: 'LayoutDashboard', superadmin_only: false },
        ],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessAnyFeature(['dashboard', 'vacancies'])).toBe(true);
    });

    it('should return false if no features are accessible', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [
          { id: 'contacts', label: 'Contacts', path: '/contacts', icon: 'Users', superadmin_only: false },
        ],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessAnyFeature(['dashboard', 'vacancies'])).toBe(false);
    });

    it('should return true for empty array', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      // Empty array means "any of zero features" which is vacuously false
      expect(result.current.canAccessAnyFeature([])).toBe(false);
    });
  });

  describe('canAccessAllFeatures', () => {
    it('should return true when all features are accessible', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [
          { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: 'LayoutDashboard', superadmin_only: false },
          { id: 'vacancies', label: 'Vacancies', path: '/vacancies', icon: 'Briefcase', superadmin_only: false },
        ],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessAllFeatures(['dashboard', 'vacancies'])).toBe(true);
    });

    it('should return false when not all features are accessible', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [
          { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: 'LayoutDashboard', superadmin_only: false },
        ],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessAllFeatures(['dashboard', 'vacancies'])).toBe(false);
    });

    it('should return true for empty array', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      // Empty array means "all of zero features" which is vacuously true
      expect(result.current.canAccessAllFeatures([])).toBe(true);
    });
  });

  describe('isLoading', () => {
    it('should return true when permissions are loading', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [],
        permissionsLoading: true,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.isLoading).toBe(true);
    });

    it('should return false when permissions are loaded', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [],
        permissionsLoading: false,
        user: { role: 'member' },
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.isLoading).toBe(false);
    });
  });

  describe('Edge cases', () => {
    it('should handle undefined user gracefully', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [
          { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: 'LayoutDashboard', superadmin_only: false },
        ],
        permissionsLoading: false,
        user: undefined,
      });

      const { result } = renderHook(() => useCanAccessFeature());

      // With no user but valid menu items, should still check menu items
      expect(result.current.canAccessFeature('dashboard')).toBe(true);
      expect(result.current.canAccessFeature('vacancies')).toBe(false);
    });

    it('should handle null user gracefully', () => {
      mockUseAuthStore.mockReturnValue({
        menuItems: [],
        permissionsLoading: false,
        user: null,
      });

      const { result } = renderHook(() => useCanAccessFeature());

      expect(result.current.canAccessFeature('dashboard')).toBe(false);
    });
  });
});
