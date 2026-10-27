import { useAuthStore } from '@/stores/authStore';
import { useCallback } from 'react';

/**
 * Return type for the useUserFeatures hook
 */
export interface UseUserFeaturesReturn {
  /** List of features available to the current user */
  features: string[];
  /** Check if the current user has access to a specific feature */
  hasFeature: (feature: string) => boolean;
  /** Whether features are still loading */
  isLoading: boolean;
}

/**
 * Hook for accessing the current user's available features
 *
 * Features are fetched from /api/admin/me/features and include:
 * - Default features (chats, contacts, calls, dashboard)
 * - Restricted features that are enabled for user's organization/departments
 *
 * Superadmin and org owners have access to all features.
 *
 * @example
 * ```tsx
 * const { features, hasFeature, isLoading } = useUserFeatures();
 *
 * if (hasFeature('vacancies')) {
 *   // Show vacancy-related content
 * }
 * ```
 */
export function useUserFeatures(): UseUserFeaturesReturn {
  const { features, hasFeature: storeHasFeature, permissionsLoading, user } = useAuthStore();

  /**
   * Check if the current user has access to a specific feature
   */
  const hasFeature = useCallback(
    (feature: string): boolean => {
      // Superadmin always has access to all features
      if (user?.role === 'superadmin') {
        return true;
      }

      return storeHasFeature(feature);
    },
    [storeHasFeature, user?.role]
  );

  return {
    features,
    hasFeature,
    isLoading: permissionsLoading,
  };
}

export default useUserFeatures;
