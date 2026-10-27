import { create } from 'zustand';
import type { User, Session } from '@/types';
import {
  getMyPermissions,
  getMyMenu,
  getMyFeatures,
  type MenuItem,
  getSessions,
  logoutAllDevices as apiLogoutAllDevices,
  revokeSession as apiRevokeSession
} from '@/services/api';
import { setObserverMode } from '@/services/api/client';

// Polling interval for feature updates (30 seconds)
const FEATURE_POLL_INTERVAL = 30000;

interface AuthState {
  user: User | null;
  isLoading: boolean;
  originalUser: User | null;  // Store original user during impersonation
  // Permissions
  permissions: Record<string, boolean>;
  permissionsSource: string | null;
  customRoleName: string | null;
  menuItems: MenuItem[];
  permissionsLoading: boolean;
  // Features
  features: string[];
  // Sessions
  sessions: Session[];
  sessionsLoading: boolean;
  // Polling
  featurePollingInterval: ReturnType<typeof setInterval> | null;
  setUser: (user: User | null) => void;
  setLoading: (loading: boolean) => void;
  logout: () => void;
  // Permissions
  fetchPermissions: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  // Features
  hasFeature: (feature: string) => boolean;
  startFeaturePolling: () => void;
  stopFeaturePolling: () => void;
  // Sessions
  fetchSessions: () => Promise<void>;
  logoutAllDevices: () => Promise<{ sessions_revoked: number }>;
  revokeSession: (sessionId: string) => Promise<void>;
  // Impersonation
  impersonate: (userId: number) => Promise<void>;
  exitImpersonation: () => Promise<void>;
  isImpersonating: () => boolean;
  // Role helpers
  isSuperAdmin: () => boolean;
  isOwner: () => boolean;
  isAdmin: () => boolean;
  isSubAdmin: () => boolean;
  isMember: () => boolean;
  isDepartmentAdmin: () => boolean;
  canShareTo: (targetUserId: number, targetUserRole?: string, targetDepartmentId?: number) => boolean;
  canDeleteUser: (targetUserId: number, targetUserRole?: string) => boolean;
  canEditResource: (resource: { owner_id?: number; is_mine?: boolean; access_level?: string }) => boolean;
  canDeleteResource: (resource: { owner_id?: number; is_mine?: boolean; access_level?: string }) => boolean;
  canShareResource: (resource: { owner_id?: number; is_mine?: boolean; access_level?: string }) => boolean;
  // Department access check
  canAccessDepartment: (departmentId: number | undefined) => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isLoading: true,
  originalUser: null,
  // Permissions state
  permissions: {},
  permissionsSource: null,
  customRoleName: null,
  menuItems: [],
  permissionsLoading: false,
  // Features state
  features: [],
  // Sessions state
  sessions: [],
  sessionsLoading: false,
  // Polling state
  featurePollingInterval: null,
  setUser: (user) => {
    set({ user });
    // Fetch permissions and start polling when user is set
    if (user) {
      get().fetchPermissions();
      get().startFeaturePolling();
    } else {
      get().stopFeaturePolling();
    }
  },
  setLoading: (isLoading) => set({ isLoading }),
  logout: () => {
    // Stop polling before clearing user
    get().stopFeaturePolling();
    // Cookie is cleared by the /auth/logout endpoint
    set({
      user: null,
      originalUser: null,
      permissions: {},
      permissionsSource: null,
      customRoleName: null,
      menuItems: [],
      features: [],
      sessions: [],
      sessionsLoading: false,
      featurePollingInterval: null,
    });
  },

  // Fetch user's effective permissions and features
  fetchPermissions: async () => {
    const { user } = get();
    if (!user) return;

    set({ permissionsLoading: true });
    try {
      const [permissionsData, menuData, featuresData] = await Promise.all([
        getMyPermissions(),
        getMyMenu(),
        getMyFeatures(),
      ]);

      set({
        permissions: permissionsData.permissions,
        permissionsSource: permissionsData.source,
        customRoleName: permissionsData.custom_role_name,
        menuItems: menuData.items,
        features: featuresData.features,
        permissionsLoading: false,
      });
    } catch (error) {
      // Don't log full error to avoid leaking sensitive data
      console.error('Failed to fetch permissions');
      set({ permissionsLoading: false });
    }
  },

  // Check if user has a specific permission
  hasPermission: (permission: string) => {
    const { permissions, user } = get();

    // Superadmin has all permissions
    if (user?.role === 'superadmin') return true;

    // Check explicit permission
    if (permissions[permission] !== undefined) {
      return permissions[permission];
    }

    // Default fallback based on role for common permissions
    if (permission.startsWith('can_view_')) {
      // All logged in users can view by default
      return !!user;
    }

    return false;
  },

  // Check if user has access to a specific feature
  hasFeature: (feature: string) => {
    const { features, user } = get();

    // Superadmin has all features
    if (user?.role === 'superadmin') return true;

    // Check if feature is in the user's available features
    return features.includes(feature);
  },

  // Start polling for feature updates
  startFeaturePolling: () => {
    const { featurePollingInterval } = get();

    // Don't start if already polling
    if (featurePollingInterval) return;

    const interval = setInterval(async () => {
      const { user } = get();
      if (!user) {
        get().stopFeaturePolling();
        return;
      }

      try {
        // Only fetch features (lighter than full fetchPermissions)
        const featuresData = await getMyFeatures();
        const currentFeatures = get().features;

        // Only update if features have changed
        const featuresChanged =
          featuresData.features.length !== currentFeatures.length ||
          featuresData.features.some(f => !currentFeatures.includes(f)) ||
          currentFeatures.some(f => !featuresData.features.includes(f));

        if (featuresChanged) {
          set({ features: featuresData.features });
          // Features updated silently in background
        }
      } catch (error) {
        // Silently fail - don't interrupt user experience for background polling
        console.debug('Feature polling failed:', error);
      }
    }, FEATURE_POLL_INTERVAL);

    set({ featurePollingInterval: interval });
  },

  // Stop polling for feature updates
  stopFeaturePolling: () => {
    const { featurePollingInterval } = get();
    if (featurePollingInterval) {
      clearInterval(featurePollingInterval);
      set({ featurePollingInterval: null });
    }
  },

  // Fetch all active sessions for the current user
  fetchSessions: async () => {
    const { user } = get();
    if (!user) return;

    set({ sessionsLoading: true });
    try {
      const sessions = await getSessions();
      set({ sessions, sessionsLoading: false });
    } catch (error) {
      console.error('Failed to fetch sessions');
      set({ sessionsLoading: false });
    }
  },

  // Logout from all devices (invalidate all refresh tokens)
  logoutAllDevices: async () => {
    const { user } = get();
    if (!user) {
      throw new Error('Not authenticated');
    }

    try {
      const result = await apiLogoutAllDevices();
      // Clear local sessions after successful logout
      set({ sessions: [] });
      return { sessions_revoked: result.sessions_revoked };
    } catch (error) {
      console.error('Failed to logout all devices');
      throw error;
    }
  },

  // Revoke a specific session
  revokeSession: async (sessionId: string) => {
    const { user, sessions } = get();
    if (!user) {
      throw new Error('Not authenticated');
    }

    try {
      await apiRevokeSession(sessionId);
      // Remove the session from local state
      set({ sessions: sessions.filter(s => s.id !== sessionId) });
    } catch (error) {
      console.error('Failed to revoke session');
      throw error;
    }
  },

  // Impersonate a user
  impersonate: async (userId: number) => {
    const { user: currentUser } = get();
    if (!currentUser) {
      throw new Error('Not authenticated');
    }

    try {
      const response = await fetch(`/api/admin/impersonate/${userId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',  // Send cookies with request
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to impersonate user');
      }

      const data = await response.json();

      // Store original user before impersonation
      set({ originalUser: currentUser });

      // Set new user with impersonation flag (cookie is set by backend)
      const impersonatedUser = {
        ...data.user,
        is_impersonating: true,
        original_user_id: currentUser.id,
        original_user_name: currentUser.name,
      };

      set({
        user: impersonatedUser,
      });
    } catch (error) {
      console.error('Impersonation failed');
      throw error;
    }
  },

  // Exit impersonation and return to original user
  exitImpersonation: async () => {
    const { originalUser } = get();
    if (!originalUser) {
      throw new Error('Not currently impersonating');
    }

    try {
      const response = await fetch('/api/admin/exit-impersonation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',  // Send cookies with request
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to exit impersonation');
      }

      const data = await response.json();

      // Restore original user (cookie is set by backend)
      set({
        user: data.user,
        originalUser: null,
      });
    } catch (error) {
      console.error('Exit impersonation failed');
      throw error;
    }
  },

  // Check if currently impersonating
  isImpersonating: () => {
    const { user } = get();
    return user?.is_impersonating === true;
  },

  // Role helper methods
  isSuperAdmin: () => {
    const { user } = get();
    return user?.role === 'superadmin';
  },

  isOwner: () => {
    const { user } = get();
    return user?.org_role === 'owner';
  },

  isAdmin: () => {
    const { user } = get();
    // Org admin or department lead/sub_admin
    return user?.org_role === 'admin' || user?.department_role === 'lead' || user?.department_role === 'sub_admin';
  },

  isSubAdmin: () => {
    const { user } = get();
    return user?.department_role === 'sub_admin';
  },

  isMember: () => {
    const { user } = get();
    return user?.org_role === 'member' && user?.department_role === 'member';
  },

  isDepartmentAdmin: () => {
    const { user } = get();
    return user?.department_role === 'lead' || user?.department_role === 'sub_admin';
  },

  // Check if current user can share to target user
  // Logic mirrors backend auth.py can_share_to()
  canShareTo: (targetUserId: number, targetUserRole?: string, targetDepartmentId?: number) => {
    const { user, isSuperAdmin, isOwner } = get();
    if (!user) return false;

    // Can't share to yourself
    if (user.id === targetUserId) return false;

    // 1. SUPERADMIN can share to anyone
    if (isSuperAdmin()) return true;

    // 2. OWNER can share to anyone in organization
    if (isOwner()) return true;

    // Determine if target is OWNER or SUPERADMIN
    const targetIsOwner = targetUserRole === 'owner';
    const targetIsSuperAdmin = targetUserRole === 'superadmin';

    // Determine if target is department admin (lead or sub_admin)
    const targetIsDeptAdmin = targetUserRole === 'lead' || targetUserRole === 'sub_admin';

    // Determine if current user is department admin
    const currentUserIsDeptAdmin = user.department_role === 'lead' || user.department_role === 'sub_admin';

    // 3. ADMIN/SUB_ADMIN (department_role === 'lead' or 'sub_admin') can share to:
    //    - OWNER and SUPERADMIN
    //    - Other ADMIN/SUB_ADMIN (any department)
    //    - Members in their department
    if (currentUserIsDeptAdmin) {
      // Can share to OWNER or SUPERADMIN
      if (targetIsOwner || targetIsSuperAdmin) return true;

      // Can share to other department admins (any department)
      if (targetIsDeptAdmin) return true;

      // Can share to members in same department
      if (targetDepartmentId && user.department_id && targetDepartmentId === user.department_id) {
        return true;
      }

      return false;
    }

    // 4. MEMBER can only share within their department
    return targetDepartmentId !== undefined &&
           user.department_id !== undefined &&
           targetDepartmentId === user.department_id;
  },

  // Check if current user can delete target user
  canDeleteUser: (targetUserId: number, targetUserRole?: string) => {
    const { user, isSuperAdmin, isOwner } = get();
    if (!user || user.id === targetUserId) return false;

    // SUPERADMIN can delete anyone except other superadmins
    if (isSuperAdmin()) {
      return targetUserRole !== 'superadmin';
    }

    // OWNER can delete anyone except superadmin and other owners
    if (isOwner()) {
      return targetUserRole !== 'superadmin' && targetUserRole !== 'owner';
    }

    // Department LEAD can delete sub_admins and members (but not other leads)
    if (user.department_role === 'lead') {
      return targetUserRole === 'sub_admin' || targetUserRole === 'member';
    }

    // SUB_ADMIN cannot delete other users
    return false;
  },

  // Check if user can edit a resource
  canEditResource: (resource: { owner_id?: number; is_mine?: boolean; access_level?: string }) => {
    const { user, isSuperAdmin, isOwner } = get();
    if (!user) return false;

    // SUPERADMIN and OWNER can edit everything
    if (isSuperAdmin() || isOwner()) return true;

    // Owner can always edit
    if (resource.is_mine || resource.owner_id === user.id) return true;

    // Shared with edit or full access
    if (resource.access_level === 'edit' || resource.access_level === 'full') return true;

    return false;
  },

  // Check if user can delete a resource
  canDeleteResource: (resource: { owner_id?: number; is_mine?: boolean; access_level?: string }) => {
    const { user, isSuperAdmin, isOwner } = get();
    if (!user) return false;

    // SUPERADMIN and OWNER can delete everything
    if (isSuperAdmin() || isOwner()) return true;

    // Only owner can delete (even with full access, you can't delete shared items)
    if (resource.is_mine || resource.owner_id === user.id) return true;

    return false;
  },

  // Check if user can share a resource
  canShareResource: (resource: { owner_id?: number; is_mine?: boolean; access_level?: string }) => {
    const { user, isSuperAdmin, isOwner } = get();
    if (!user) return false;

    // SUPERADMIN and OWNER can share everything
    if (isSuperAdmin() || isOwner()) return true;

    // Owner can share
    if (resource.is_mine || resource.owner_id === user.id) return true;

    // Users with full access can re-share
    if (resource.access_level === 'full') return true;

    return false;
  },

  // Check if user has access to resources in a specific department
  // Returns true if:
  // - User is SUPERADMIN or ORG OWNER (access to all departments)
  // - User belongs to the same department
  // - departmentId is undefined (resource has no department restriction)
  canAccessDepartment: (departmentId: number | undefined) => {
    const { user, isSuperAdmin, isOwner } = get();
    if (!user) return false;

    // SUPERADMIN and ORG OWNER can access all departments
    if (isSuperAdmin() || isOwner()) return true;

    // If resource has no department restriction, allow access
    if (departmentId === undefined || departmentId === null) return true;

    // User must belong to the same department
    return user.department_id === departmentId;
  },
}));

// «Наблюдатель» (is_readonly): клиент сам не отправляет изменяющие запросы в
// HR/админке — иначе кнопка «работала», а сервер молча отвечал 403 (см.
// isObserverBlocked). Подписка, а не вызов в setUser: пользователь ставится ещё
// и при логине и при имперсонации, мимо setUser.
useAuthStore.subscribe((state) => {
  setObserverMode(!!state.user?.is_readonly && state.user?.role !== 'superadmin');
});
