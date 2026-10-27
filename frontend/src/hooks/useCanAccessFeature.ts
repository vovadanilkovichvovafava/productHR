import { useAuthStore } from '@/stores/authStore';
import { useCallback } from 'react';

/**
 * Feature names that can be checked for access
 * These correspond to menu item IDs from the backend
 */
export type FeatureName =
  | 'dashboard'
  | 'chats'
  | 'contacts'
  | 'calls'
  | 'vacancies'
  | 'candidate_database'
  | 'candidates'
  | 'departments'
  | 'users'
  | 'invite'
  | 'settings'
  | 'admin'
  | 'trash';

/**
 * Return type for the useCanAccessFeature hook
 */
export interface UseCanAccessFeatureReturn {
  /** Check if the current user can access a specific feature */
  canAccessFeature: (feature: FeatureName) => boolean;
  /** Check if any of the given features are accessible */
  canAccessAnyFeature: (features: FeatureName[]) => boolean;
  /** Check if all of the given features are accessible */
  canAccessAllFeatures: (features: FeatureName[]) => boolean;
  /** Whether permissions are still loading */
  isLoading: boolean;
}

/**
 * Hook for checking if the current user can access specific features
 *
 * Uses the menuItems from the auth store to determine feature access.
 * Menu items are fetched from the backend and filtered based on user permissions.
 *
 * @example
 * ```tsx
 * const { canAccessFeature, isLoading } = useCanAccessFeature();
 *
 * if (canAccessFeature('vacancies')) {
 *   // Show vacancy-related content
 * }
 * ```
 */
export function useCanAccessFeature(): UseCanAccessFeatureReturn {
  const { menuItems, permissionsLoading, user } = useAuthStore();

  /**
   * Check if the current user can access a specific feature
   */
  const canAccessFeature = useCallback(
    (feature: FeatureName): boolean => {
      // Superadmin always has access to all features
      if (user?.role === 'superadmin') {
        return true;
      }

      // If no menu items loaded yet, assume no access (safer default)
      if (!menuItems || menuItems.length === 0) {
        return false;
      }

      // Check if the feature exists in the user's menu items
      return menuItems.some((item) => item.id === feature);
    },
    [menuItems, user?.role]
  );

  /**
   * Check if any of the given features are accessible
   */
  const canAccessAnyFeature = useCallback(
    (features: FeatureName[]): boolean => {
      return features.some((feature) => canAccessFeature(feature));
    },
    [canAccessFeature]
  );

  /**
   * Check if all of the given features are accessible
   */
  const canAccessAllFeatures = useCallback(
    (features: FeatureName[]): boolean => {
      return features.every((feature) => canAccessFeature(feature));
    },
    [canAccessFeature]
  );

  return {
    canAccessFeature,
    canAccessAnyFeature,
    canAccessAllFeatures,
    isLoading: permissionsLoading,
  };
}

export default useCanAccessFeature;
