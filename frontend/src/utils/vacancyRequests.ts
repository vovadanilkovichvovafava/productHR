import type { User, Vacancy, VacancyStatus } from "@/types";

// Какие заявки видны в разделе «Заявки» и как работают его фильтры — чистая
// функция (вынесено из VacanciesPage, 20.10.2026, без изменения поведения),
// под тестами (__tests__/vacancyRequests.test.ts).

export const SALARY_RANGES = [
  { id: 'any', label: 'Любая зарплата', min: undefined, max: undefined },
  { id: 'under100k', label: 'До 100k', min: undefined, max: 100000 },
  { id: '100k-200k', label: '100k - 200k', min: 100000, max: 200000 },
  { id: '200k-300k', label: '200k - 300k', min: 200000, max: 300000 },
  { id: '300k+', label: '300k+', min: 300000, max: undefined },
];

export const DATE_RANGES = [
  { id: 'any', label: 'За всё время', days: undefined },
  { id: '7days', label: 'За 7 дней', days: 7 },
  { id: '30days', label: 'За 30 дней', days: 30 },
  { id: '90days', label: 'За 90 дней', days: 90 },
];

export interface QuickFilters {
  statuses: VacancyStatus[];
  salaryRange: string;
  dateRange: string;
}

export interface VacancyRequestFilters {
  search: string;
  user: User | null;
  isAdmin: boolean;
  /** «Только мои»: у не-админа всегда включено. */
  onlyMine: boolean;
  assignmentFilter: "all" | "unassigned";
  departmentFilter: number | "all";
  statusFilter: VacancyStatus | "all";
  quickFilters: QuickFilters;
  /** Зарплата вакансии в рублях для сравнения с диапазоном (0 — не указана). */
  getComparableSalary: (min: number | null | undefined, max: number | null | undefined, currency: string) => number;
}

export function filterVacancyRequests(
  vacancies: Vacancy[],
  { search, user, isAdmin, onlyMine, assignmentFilter, departmentFilter, statusFilter, quickFilters, getComparableSalary }: VacancyRequestFilters,
): Vacancy[] {
  const normalizedSearch = search.trim().toLowerCase();

  return vacancies.filter((vacancy) => {
    // Заявки page = только заявки, не персональные клоны рекрутёров.
    // Личные вакансии (включая клоны) живут в "Мои вакансии".
    const extra = vacancy.extra_data as Record<string, unknown> | undefined;
    const cloneSrc = extra?.cloned_from_request_id;
    if (typeof cloneSrc === 'number') return false;

    // Рекрутёр, который «отказался»/закрыл свой клон, больше не видит заявку
    // (бэкенд кладёт его id в dismissed_by). НО админ/hr/owner видят ВСЕ
    // заявки (оверсайт) — на них dismissed_by не распространяем, иначе после
    // назначения заявка могла «пропасть» и у админа.
    if (user && !isAdmin) {
      const dismissedBy = extra?.dismissed_by;
      if (Array.isArray(dismissedBy) && dismissedBy.includes(user.id)) return false;
    }

    // Task 9: "My vacancies" filter
    if (onlyMine && user) {
      const isMine = vacancy.created_by === user.id
        || (vacancy.assigned_to && vacancy.assigned_to.includes(user.id))
        || vacancy.assigned_to_all === true;
      if (!isMine) return false;
    }

    // Task 12: Unassigned requests filter
    if (assignmentFilter === 'unassigned') {
      const hasAssignment = (vacancy.assigned_to && vacancy.assigned_to.length > 0) || vacancy.assigned_to_all;
      if (hasAssignment) return false;
    }

    if (departmentFilter !== 'all' && vacancy.department_id !== departmentFilter) {
      return false;
    }

    if (normalizedSearch) {
      const searchableText = [
        vacancy.title,
        vacancy.description,
        vacancy.requirements,
        vacancy.responsibilities,
        vacancy.location,
        vacancy.department_name,
        vacancy.created_by_name,
        vacancy.hiring_manager_name,
        ...(vacancy.tags || []),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      if (!searchableText.includes(normalizedSearch)) {
        return false;
      }
    }

    // Main status tab filter (top tabs)
    if (statusFilter !== 'all' && vacancy.status !== statusFilter) {
      return false;
    }

    // Quick filter statuses (multi-select inside dropdown)
    if (quickFilters.statuses.length > 0 && !quickFilters.statuses.includes(vacancy.status)) {
      return false;
    }

    // Salary range filter (with currency conversion)
    if (quickFilters.salaryRange !== 'any') {
      const salaryConfig = SALARY_RANGES.find(s => s.id === quickFilters.salaryRange);
      if (salaryConfig) {
        // Convert vacancy salary to RUB for comparison
        // This allows comparing salaries across different currencies
        const vacancySalaryInRUB = getComparableSalary(
          vacancy.salary_min,
          vacancy.salary_max,
          vacancy.salary_currency || 'RUB'
        );

        if (vacancySalaryInRUB === 0) {
          // No salary specified - exclude from salary filter
          return false;
        }

        if (salaryConfig.min !== undefined && vacancySalaryInRUB < salaryConfig.min) return false;
        if (salaryConfig.max !== undefined && vacancySalaryInRUB > salaryConfig.max) return false;
      }
    }

    // Date range filter
    if (quickFilters.dateRange !== 'any') {
      const dateConfig = DATE_RANGES.find(d => d.id === quickFilters.dateRange);
      if (dateConfig?.days) {
        const vacancyDate = new Date(vacancy.created_at);
        const cutoffDate = new Date();
        cutoffDate.setDate(cutoffDate.getDate() - dateConfig.days);
        if (vacancyDate < cutoffDate) return false;
      }
    }

    return true;
  });
}
