import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import VacanciesPage from '../VacanciesPage';
import { useVacancyStore } from '@/stores/vacancyStore';
import type { Vacancy, VacancyStatus } from '@/types';

// Mock the vacancy store
vi.mock('@/stores/vacancyStore', () => ({
  useVacancyStore: vi.fn(),
}));

// Mock the API
vi.mock('@/services/api', () => ({
  getDepartments: vi.fn().mockResolvedValue([]),
  getAssignableUsers: vi.fn().mockResolvedValue([]),
  assignVacancy: vi.fn().mockResolvedValue({}),
  takeVacancy: vi.fn().mockResolvedValue({}),
  declineVacancy: vi.fn().mockResolvedValue({}),
  getExchangeRates: vi.fn().mockResolvedValue({ base: 'RUB', rates: {} }),
}));

// Mock framer-motion to avoid animation issues in tests
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
      <div {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => <>{children}</>,
}));

const mockVacancies: Vacancy[] = [
  {
    id: 1,
    title: 'Software Engineer',
    description: 'Build great software',
    requirements: '',
    responsibilities: '',
    status: 'open' as VacancyStatus,
    salary_min: 150000,
    salary_max: 200000,
    salary_currency: 'USD',
    location: 'Remote',
    employment_type: 'full-time',
    experience_level: 'senior',
    priority: 0,
    applications_count: 5,
    stage_counts: {},
    tags: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    closed_at: null,
    department_id: null,
    created_by: 1,
  },
  {
    id: 2,
    title: 'Product Manager',
    description: 'Manage products',
    requirements: '',
    responsibilities: '',
    status: 'draft' as VacancyStatus,
    salary_min: 80000,
    salary_max: 120000,
    salary_currency: 'USD',
    location: 'New York',
    employment_type: 'full-time',
    experience_level: 'mid',
    priority: 1,
    applications_count: 3,
    stage_counts: {},
    tags: ['product', 'management'],
    created_at: new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toISOString(), // 60 days ago
    updated_at: new Date().toISOString(),
    closed_at: null,
    department_id: null,
    created_by: 1,
  },
  {
    id: 3,
    title: 'Senior Designer',
    description: 'Design beautiful things',
    requirements: '',
    responsibilities: '',
    status: 'closed' as VacancyStatus,
    salary_min: 250000,
    salary_max: 350000,
    salary_currency: 'USD',
    location: 'San Francisco',
    employment_type: 'full-time',
    experience_level: 'senior',
    priority: 2,
    applications_count: 10,
    stage_counts: {},
    tags: ['design', 'ui', 'ux'],
    created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(), // 5 days ago
    updated_at: new Date().toISOString(),
    closed_at: new Date().toISOString(),
    department_id: null,
    created_by: 1,
  },
];

const mockStore = {
  vacancies: mockVacancies,
  currentVacancy: null,
  loading: false,
  error: null,
  fetchVacancies: vi.fn(),
  fetchVacancy: vi.fn(),
  deleteVacancy: vi.fn(),
  setFilters: vi.fn(),
  clearCurrentVacancy: vi.fn(),
  clearError: vi.fn(),
};

describe('VacanciesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (useVacancyStore as ReturnType<typeof vi.fn>).mockReturnValue(mockStore);
  });

  const renderWithRouter = (initialEntries: string[] = ['/vacancies']) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <VacanciesPage />
      </MemoryRouter>
    );
  };

  describe('Quick Filters', () => {
    it('should render the filters button', () => {
      renderWithRouter();
      expect(screen.getByText('Фильтры')).toBeInTheDocument();
    });

    it('should open filters dropdown when clicking the button', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      await waitFor(() => {
        expect(screen.getByText('Быстрые фильтры')).toBeInTheDocument();
      });
    });

    it('should display status filter options', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      await waitFor(() => {
        expect(screen.getByText('Статус')).toBeInTheDocument();
        // Check for status options in the dropdown
        const dropdown = screen.getByText('Быстрые фильтры').parentElement?.parentElement;
        expect(dropdown).toBeInTheDocument();
      });
    });

    it('should display salary range filter options', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      await waitFor(() => {
        expect(screen.getByText('Зарплата')).toBeInTheDocument();
        expect(screen.getByText('Любая зарплата')).toBeInTheDocument();
        expect(screen.getByText('До 100k')).toBeInTheDocument();
        expect(screen.getByText('100k - 200k')).toBeInTheDocument();
        expect(screen.getByText('200k - 300k')).toBeInTheDocument();
        expect(screen.getByText('300k+')).toBeInTheDocument();
      });
    });

    it('should display date range filter options', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      await waitFor(() => {
        expect(screen.getByText('Дата создания')).toBeInTheDocument();
        expect(screen.getByText('За всё время')).toBeInTheDocument();
        expect(screen.getByText('За 7 дней')).toBeInTheDocument();
        expect(screen.getByText('За 30 дней')).toBeInTheDocument();
        expect(screen.getByText('За 90 дней')).toBeInTheDocument();
      });
    });

    it('should show active filter count badge when filters are applied', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      // Click on a salary filter
      await waitFor(() => {
        const under100kButton = screen.getByText('До 100k');
        fireEvent.click(under100kButton);
      });

      // Check for the badge with count
      await waitFor(() => {
        expect(screen.getByText('1')).toBeInTheDocument();
      });
    });

    it('should show clear all button when filters are active', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      // Apply a filter
      await waitFor(() => {
        const under100kButton = screen.getByText('До 100k');
        fireEvent.click(under100kButton);
      });

      // Check for clear all button
      await waitFor(() => {
        expect(screen.getByText('Сбросить')).toBeInTheDocument();
      });
    });

    it('should clear all filters when clear all button is clicked', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      // Apply a filter
      await waitFor(() => {
        const under100kButton = screen.getByText('До 100k');
        fireEvent.click(under100kButton);
      });

      // Click clear all
      await waitFor(() => {
        const clearAllButton = screen.getByText('Сбросить');
        fireEvent.click(clearAllButton);
      });

      // Badge should no longer show a number (no active filters)
      await waitFor(() => {
        // The badge with count should be gone
        const badges = screen.queryAllByText(/^\d$/);
        expect(badges.length === 0 || !badges.some(b => b.textContent === '1')).toBe(true);
      });
    });

    it('should display filtered vacancies count', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      await waitFor(() => {
        expect(screen.getByText(/Показано \d+ из \d+ заявок/)).toBeInTheDocument();
      });
    });

    it('should close dropdown when clicking outside', async () => {
      renderWithRouter();

      const filtersButton = screen.getByText('Фильтры');
      fireEvent.click(filtersButton);

      await waitFor(() => {
        expect(screen.getByText('Быстрые фильтры')).toBeInTheDocument();
      });

      // Click outside the dropdown
      fireEvent.mouseDown(document.body);

      await waitFor(() => {
        expect(screen.queryByText('Быстрые фильтры')).not.toBeInTheDocument();
      });
    });
  });

  describe('Vacancy List', () => {
    it('should display vacancies', () => {
      renderWithRouter();

      expect(screen.getByText('Software Engineer')).toBeInTheDocument();
      expect(screen.getByText('Product Manager')).toBeInTheDocument();
      expect(screen.getByText('Senior Designer')).toBeInTheDocument();
    });

    it('should display vacancy priority badges', () => {
      renderWithRouter();

      expect(screen.getByText('Важно')).toBeInTheDocument();
      expect(screen.getByText('Срочно')).toBeInTheDocument();
    });

    it('should display candidate counts', () => {
      renderWithRouter();

      // Число кандидатов — отдельный бейдж с иконкой, без слова «candidates».
      const counts = Array.from(
        document.querySelectorAll('.hf-vacancies-search-candidates'),
      ).map((el) => el.textContent?.trim());
      expect(counts).toEqual(expect.arrayContaining(['5', '3', '10']));
    });

    it('should show loading skeletons when loading', () => {
      (useVacancyStore as ReturnType<typeof vi.fn>).mockReturnValue({
        ...mockStore,
        loading: true,
        vacancies: [],
      });

      renderWithRouter();

      // Should show skeleton loaders
      expect(screen.queryByText('Software Engineer')).not.toBeInTheDocument();
    });

    it('should show empty state when no vacancies', () => {
      (useVacancyStore as ReturnType<typeof vi.fn>).mockReturnValue({
        ...mockStore,
        vacancies: [],
      });

      renderWithRouter();

      // Should show empty state (NoVacanciesEmpty component)
      expect(screen.queryByText('Software Engineer')).not.toBeInTheDocument();
    });
  });

  describe('Header Actions', () => {
    it('should display New Vacancy button', () => {
      renderWithRouter();
      expect(screen.getByText('Новая заявка')).toBeInTheDocument();
    });


    it('should display search input', () => {
      renderWithRouter();
      expect(screen.getByPlaceholderText('Поиск по названию...')).toBeInTheDocument();
    });
  });
});

describe('Quick Filters Logic', () => {
  // Test the filtering logic with different scenarios
  const filterVacancies = (
    vacancies: Vacancy[],
    filters: {
      statuses: VacancyStatus[];
      salaryRange: string;
      dateRange: string;
    }
  ) => {
    const SALARY_RANGES: Record<string, { min?: number; max?: number }> = {
      any: { min: undefined, max: undefined },
      under100k: { min: undefined, max: 100000 },
      '100k-200k': { min: 100000, max: 200000 },
      '200k-300k': { min: 200000, max: 300000 },
      '300k+': { min: 300000, max: undefined },
    };

    const DATE_RANGES: Record<string, number | undefined> = {
      any: undefined,
      '7days': 7,
      '30days': 30,
      '90days': 90,
    };

    return vacancies.filter((vacancy) => {
      // Status filter
      if (filters.statuses.length > 0 && !filters.statuses.includes(vacancy.status)) {
        return false;
      }

      // Salary range filter
      if (filters.salaryRange !== 'any') {
        const salaryConfig = SALARY_RANGES[filters.salaryRange];
        if (salaryConfig) {
          const vacancySalary = vacancy.salary_max || vacancy.salary_min || 0;
          if (salaryConfig.min !== undefined && vacancySalary < salaryConfig.min) return false;
          if (salaryConfig.max !== undefined && vacancySalary > salaryConfig.max) return false;
        }
      }

      // Date range filter
      if (filters.dateRange !== 'any') {
        const days = DATE_RANGES[filters.dateRange];
        if (days) {
          const vacancyDate = new Date(vacancy.created_at);
          const cutoffDate = new Date();
          cutoffDate.setDate(cutoffDate.getDate() - days);
          if (vacancyDate < cutoffDate) return false;
        }
      }

      return true;
    });
  };

  it('should filter by status', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: ['open'],
      salaryRange: 'any',
      dateRange: 'any',
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0].title).toBe('Software Engineer');
  });

  it('should filter by multiple statuses', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: ['open', 'draft'],
      salaryRange: 'any',
      dateRange: 'any',
    });

    expect(filtered).toHaveLength(2);
  });

  it('should filter by salary range - under 100k', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: [],
      salaryRange: 'under100k',
      dateRange: 'any',
    });

    // Product Manager has max 120k, so it should not match
    expect(filtered).toHaveLength(0);
  });

  it('should filter by salary range - 100k to 200k', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: [],
      salaryRange: '100k-200k',
      dateRange: 'any',
    });

    // Software Engineer (200k max) and Product Manager (120k max)
    expect(filtered).toHaveLength(2);
  });

  it('should filter by salary range - 300k+', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: [],
      salaryRange: '300k+',
      dateRange: 'any',
    });

    // Senior Designer has 350k max
    expect(filtered).toHaveLength(1);
    expect(filtered[0].title).toBe('Senior Designer');
  });

  it('should filter by date range - last 7 days', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: [],
      salaryRange: 'any',
      dateRange: '7days',
    });

    // Software Engineer (today) and Senior Designer (5 days ago)
    expect(filtered).toHaveLength(2);
  });

  it('should filter by date range - last 30 days', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: [],
      salaryRange: 'any',
      dateRange: '30days',
    });

    // Software Engineer (today) and Senior Designer (5 days ago)
    // Product Manager is 60 days ago, should be excluded
    expect(filtered).toHaveLength(2);
  });

  it('should combine multiple filters', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: ['open', 'closed'],
      salaryRange: '100k-200k',
      dateRange: '7days',
    });

    // Only Software Engineer matches all criteria
    expect(filtered).toHaveLength(1);
    expect(filtered[0].title).toBe('Software Engineer');
  });

  it('should return all vacancies with no filters', () => {
    const filtered = filterVacancies(mockVacancies, {
      statuses: [],
      salaryRange: 'any',
      dateRange: 'any',
    });

    expect(filtered).toHaveLength(3);
  });
});
