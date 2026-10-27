import React, { ReactNode, ReactElement, cloneElement, isValidElement } from 'react';
import clsx from 'clsx';
import { useCanAccessFeature, type FeatureName } from '@/hooks/useCanAccessFeature';

/**
 * Props for the FeatureGate component
 */
export interface FeatureGateProps {
  /** The feature name to check access for */
  feature: FeatureName;
  /** The content to render when access is granted */
  children: ReactNode;
  /**
   * Behavior when access is denied:
   * - 'hide': Completely hide the content (render nothing)
   * - 'disable': Show disabled state with tooltip
   * Default: 'disable' for better UX
   */
  fallbackMode?: 'hide' | 'disable';
  /**
   * Custom tooltip message for disabled state
   * Default: "You don't have access to this feature"
   */
  disabledTooltip?: string;
  /**
   * Optional fallback content to show when access is denied and mode is 'hide'
   */
  fallback?: ReactNode;
  /**
   * Additional class name to apply to the wrapper when in disabled mode
   */
  disabledClassName?: string;
}

/**
 * A wrapper component that conditionally renders children based on feature access.
 *
 * When the user doesn't have access to the specified feature:
 * - In 'hide' mode: The content is completely hidden (or fallback is shown)
 * - In 'disable' mode: The content is shown but disabled with a tooltip
 *
 * @example
 * ```tsx
 * // Hide content completely
 * <FeatureGate feature="vacancies" fallbackMode="hide">
 *   <VacancyButton />
 * </FeatureGate>
 *
 * // Show disabled with tooltip (default)
 * <FeatureGate feature="vacancies">
 *   <button onClick={handleAddToVacancy}>Add to Vacancy</button>
 * </FeatureGate>
 *
 * // With custom tooltip
 * <FeatureGate
 *   feature="vacancies"
 *   disabledTooltip="Upgrade your plan to access vacancies"
 * >
 *   <button>Add to Vacancy</button>
 * </FeatureGate>
 * ```
 */
export function FeatureGate({
  feature,
  children,
  fallbackMode = 'disable',
  disabledTooltip = "У вас нет доступа к этой функции",
  fallback = null,
  disabledClassName,
}: FeatureGateProps): ReactElement | null {
  const { canAccessFeature, isLoading } = useCanAccessFeature();

  // While permissions are loading, show nothing to prevent flicker
  if (isLoading) {
    return null;
  }

  const hasAccess = canAccessFeature(feature);

  // If user has access, render children normally
  if (hasAccess) {
    return <>{children}</>;
  }

  // Handle 'hide' mode
  if (fallbackMode === 'hide') {
    return fallback ? <>{fallback}</> : null;
  }

  // Handle 'disable' mode - wrap children in a disabled state
  return (
    <div
      className={clsx('feature-gate-disabled', disabledClassName)}
      title={disabledTooltip}
    >
      <DisabledWrapper tooltip={disabledTooltip}>
        {children}
      </DisabledWrapper>
    </div>
  );
}

/**
 * Props for the DisabledWrapper component
 */
interface DisabledWrapperProps {
  children: ReactNode;
  tooltip: string;
}

/**
 * Internal component that wraps children with disabled styling and tooltip
 */
function DisabledWrapper({ children, tooltip }: DisabledWrapperProps): ReactElement {
  // Try to clone the element and add disabled props if it's a valid element
  if (isValidElement(children)) {
    const element = children as ReactElement<{
      disabled?: boolean;
      className?: string;
      onClick?: () => void;
      title?: string;
      style?: React.CSSProperties;
    }>;

    // Clone the element with disabled state
    return cloneElement(element, {
      disabled: true,
      title: tooltip,
      onClick: undefined, // Remove click handler
      className: clsx(
        element.props.className,
        'opacity-50 cursor-not-allowed pointer-events-auto'
      ),
      style: {
        ...element.props.style,
        pointerEvents: 'auto', // Allow hover for tooltip
      },
    });
  }

  // If children is not a valid element, wrap in a div
  return (
    <div
      className="inline-block opacity-50 cursor-not-allowed"
      title={tooltip}
    >
      {children}
    </div>
  );
}

/**
 * A button-specific variant of FeatureGate for convenience
 *
 * @example
 * ```tsx
 * <FeatureGatedButton
 *   feature="vacancies"
 *   onClick={handleAddToVacancy}
 *   className="btn-primary"
 * >
 *   Add to Vacancy
 * </FeatureGatedButton>
 * ```
 */
export interface FeatureGatedButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** The feature name to check access for */
  feature: FeatureName;
  /** Custom tooltip message for disabled state */
  disabledTooltip?: string;
}

export function FeatureGatedButton({
  feature,
  disabledTooltip = "У вас нет доступа к этой функции",
  children,
  className,
  disabled,
  onClick,
  ...props
}: FeatureGatedButtonProps): ReactElement {
  const { canAccessFeature, isLoading } = useCanAccessFeature();

  const hasAccess = canAccessFeature(feature);
  const isDisabled = disabled || !hasAccess || isLoading;

  return (
    <button
      {...props}
      className={clsx(
        className,
        !hasAccess && 'opacity-50 cursor-not-allowed'
      )}
      disabled={isDisabled}
      onClick={hasAccess ? onClick : undefined}
      title={hasAccess ? props.title : disabledTooltip}
    >
      {children}
    </button>
  );
}

export default FeatureGate;
