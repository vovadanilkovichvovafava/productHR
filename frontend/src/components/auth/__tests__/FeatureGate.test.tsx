import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FeatureGate, FeatureGatedButton } from '../FeatureGate';
import type { FeatureName } from '@/hooks/useCanAccessFeature';

/**
 * Tests for FeatureGate component
 * Verifies feature access control for UI elements
 */

// Mock the useCanAccessFeature hook
const mockCanAccessFeature = vi.fn();
const mockIsLoading = vi.fn();

vi.mock('@/hooks/useCanAccessFeature', () => ({
  useCanAccessFeature: () => ({
    canAccessFeature: mockCanAccessFeature,
    canAccessAnyFeature: (features: FeatureName[]) =>
      features.some((f) => mockCanAccessFeature(f)),
    canAccessAllFeatures: (features: FeatureName[]) =>
      features.every((f) => mockCanAccessFeature(f)),
    isLoading: mockIsLoading(),
  }),
}));

describe('FeatureGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLoading.mockReturnValue(false);
  });

  describe('when feature is enabled', () => {
    beforeEach(() => {
      mockCanAccessFeature.mockReturnValue(true);
    });

    it('should render children when feature is enabled', () => {
      render(
        <FeatureGate feature="vacancies">
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      expect(screen.getByText('Add Vacancy')).toBeInTheDocument();
    });

    it('should render children normally without disabled state', () => {
      render(
        <FeatureGate feature="vacancies">
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      const button = screen.getByText('Add Vacancy');
      expect(button).not.toBeDisabled();
      expect(button.className).not.toContain('opacity-50');
    });

    it('should render complex children structure', () => {
      render(
        <FeatureGate feature="contacts">
          <div data-testid="container">
            <h1>Title</h1>
            <p>Description</p>
            <button>Action</button>
          </div>
        </FeatureGate>
      );

      expect(screen.getByTestId('container')).toBeInTheDocument();
      expect(screen.getByText('Title')).toBeInTheDocument();
      expect(screen.getByText('Description')).toBeInTheDocument();
      expect(screen.getByText('Action')).toBeInTheDocument();
    });
  });

  describe('when feature is disabled', () => {
    beforeEach(() => {
      mockCanAccessFeature.mockReturnValue(false);
    });

    it('should show disabled state with tooltip by default', () => {
      render(
        <FeatureGate feature="vacancies">
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      const button = screen.getByText('Add Vacancy');
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute('title', "У вас нет доступа к этой функции");
    });

    it('should show custom disabled tooltip when provided', () => {
      const customTooltip = 'Upgrade to access vacancies';

      render(
        <FeatureGate feature="vacancies" disabledTooltip={customTooltip}>
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      const button = screen.getByText('Add Vacancy');
      expect(button).toHaveAttribute('title', customTooltip);
    });

    it('should hide children when fallbackMode is hide', () => {
      render(
        <FeatureGate feature="vacancies" fallbackMode="hide">
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      expect(screen.queryByText('Add Vacancy')).not.toBeInTheDocument();
    });

    it('should render fallback content when feature disabled and mode is hide', () => {
      render(
        <FeatureGate
          feature="vacancies"
          fallbackMode="hide"
          fallback={<span>Feature not available</span>}
        >
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      expect(screen.queryByText('Add Vacancy')).not.toBeInTheDocument();
      expect(screen.getByText('Feature not available')).toBeInTheDocument();
    });

    it('should apply disabled styling to button element', () => {
      render(
        <FeatureGate feature="vacancies">
          <button className="btn-primary">Add Vacancy</button>
        </FeatureGate>
      );

      const button = screen.getByText('Add Vacancy');
      expect(button.className).toContain('opacity-50');
      expect(button.className).toContain('cursor-not-allowed');
    });

    it('should add feature-gate-disabled class wrapper in disable mode', () => {
      const { container } = render(
        <FeatureGate feature="vacancies" fallbackMode="disable">
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      const wrapper = container.querySelector('.feature-gate-disabled');
      expect(wrapper).toBeInTheDocument();
    });

    it('should apply custom disabledClassName when provided', () => {
      const { container } = render(
        <FeatureGate
          feature="vacancies"
          fallbackMode="disable"
          disabledClassName="custom-disabled-class"
        >
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      const wrapper = container.querySelector('.custom-disabled-class');
      expect(wrapper).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('should render nothing while loading', () => {
      mockIsLoading.mockReturnValue(true);
      mockCanAccessFeature.mockReturnValue(false);

      const { container } = render(
        <FeatureGate feature="vacancies">
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      expect(container.firstChild).toBeNull();
    });

    it('should render children after loading completes with access', () => {
      mockIsLoading.mockReturnValue(false);
      mockCanAccessFeature.mockReturnValue(true);

      render(
        <FeatureGate feature="vacancies">
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      expect(screen.getByText('Add Vacancy')).toBeInTheDocument();
    });
  });

  describe('feature checks', () => {
    it('should call canAccessFeature with correct feature name', () => {
      mockCanAccessFeature.mockReturnValue(true);

      render(
        <FeatureGate feature="vacancies">
          <button>Add Vacancy</button>
        </FeatureGate>
      );

      expect(mockCanAccessFeature).toHaveBeenCalledWith('vacancies');
    });

    it('should handle different feature names', () => {
      mockCanAccessFeature.mockReturnValue(true);
      const features: FeatureName[] = ['dashboard', 'chats', 'contacts', 'calls', 'vacancies'];

      features.forEach((feature) => {
        mockCanAccessFeature.mockClear();

        render(
          <FeatureGate feature={feature}>
            <span>Content for {feature}</span>
          </FeatureGate>
        );

        expect(mockCanAccessFeature).toHaveBeenCalledWith(feature);
      });
    });
  });

  describe('disabled state behavior', () => {
    beforeEach(() => {
      mockCanAccessFeature.mockReturnValue(false);
    });

    it('should remove onClick handler when disabled', () => {
      const handleClick = vi.fn();

      render(
        <FeatureGate feature="vacancies">
          <button onClick={handleClick}>Add Vacancy</button>
        </FeatureGate>
      );

      const button = screen.getByText('Add Vacancy');
      button.click();

      expect(handleClick).not.toHaveBeenCalled();
    });

    it('should wrap non-element children in div when disabled', () => {
      const { container } = render(
        <FeatureGate feature="vacancies">
          Just some text
        </FeatureGate>
      );

      const wrapper = container.querySelector('.feature-gate-disabled div');
      expect(wrapper).toBeInTheDocument();
      expect(wrapper?.className).toContain('opacity-50');
    });
  });
});

describe('FeatureGatedButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLoading.mockReturnValue(false);
  });

  describe('when feature is enabled', () => {
    beforeEach(() => {
      mockCanAccessFeature.mockReturnValue(true);
    });

    it('should render enabled button', () => {
      render(
        <FeatureGatedButton feature="vacancies">
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button', { name: 'Add Vacancy' });
      expect(button).not.toBeDisabled();
    });

    it('should call onClick when clicked', () => {
      const handleClick = vi.fn();

      render(
        <FeatureGatedButton feature="vacancies" onClick={handleClick}>
          Add Vacancy
        </FeatureGatedButton>
      );

      screen.getByRole('button').click();
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('should preserve original className', () => {
      render(
        <FeatureGatedButton feature="vacancies" className="btn-primary">
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button');
      expect(button.className).toContain('btn-primary');
    });

    it('should show original title when feature enabled', () => {
      render(
        <FeatureGatedButton feature="vacancies" title="Click to add">
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('title', 'Click to add');
    });
  });

  describe('when feature is disabled', () => {
    beforeEach(() => {
      mockCanAccessFeature.mockReturnValue(false);
    });

    it('should render disabled button', () => {
      render(
        <FeatureGatedButton feature="vacancies">
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });

    it('should not call onClick when clicked', () => {
      const handleClick = vi.fn();

      render(
        <FeatureGatedButton feature="vacancies" onClick={handleClick}>
          Add Vacancy
        </FeatureGatedButton>
      );

      screen.getByRole('button').click();
      expect(handleClick).not.toHaveBeenCalled();
    });

    it('should show default disabled tooltip', () => {
      render(
        <FeatureGatedButton feature="vacancies">
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('title', "У вас нет доступа к этой функции");
    });

    it('should show custom disabled tooltip', () => {
      const customTooltip = 'Upgrade to access this feature';

      render(
        <FeatureGatedButton feature="vacancies" disabledTooltip={customTooltip}>
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('title', customTooltip);
    });

    it('should apply disabled styling', () => {
      render(
        <FeatureGatedButton feature="vacancies">
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button');
      expect(button.className).toContain('opacity-50');
      expect(button.className).toContain('cursor-not-allowed');
    });
  });

  describe('when already disabled via prop', () => {
    it('should remain disabled even when feature is enabled', () => {
      mockCanAccessFeature.mockReturnValue(true);

      render(
        <FeatureGatedButton feature="vacancies" disabled>
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });
  });

  describe('during loading', () => {
    it('should be disabled while loading', () => {
      mockIsLoading.mockReturnValue(true);
      mockCanAccessFeature.mockReturnValue(true);

      render(
        <FeatureGatedButton feature="vacancies">
          Add Vacancy
        </FeatureGatedButton>
      );

      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });
  });
});
