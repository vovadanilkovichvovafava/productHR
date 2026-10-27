/**
 * Фильтры раздела «Заявки» (utils/vacancyRequests.ts, 20.10.2026).
 */
import { describe, it, expect } from "vitest";
import { filterVacancyRequests, type VacancyRequestFilters } from "../vacancyRequests";
import type { User, Vacancy } from "@/types";

const me = { id: 2 } as User;
const daysAgo = (n: number) => new Date(Date.now() - n * 86400000).toISOString();

const vac = (id: number, over: Partial<Vacancy> = {}) =>
  ({
    id, title: `Заявка ${id}`, status: "open", created_by: 1, assigned_to: [],
    extra_data: {}, created_at: daysAgo(1), ...over,
  }) as unknown as Vacancy;

const opts = (over: Partial<VacancyRequestFilters> = {}): VacancyRequestFilters => ({
  search: "", user: me, isAdmin: true, onlyMine: false, assignmentFilter: "all",
  departmentFilter: "all", statusFilter: "all",
  quickFilters: { statuses: [], salaryRange: "any", dateRange: "any" },
  // в тестах зарплата уже «в рублях»
  getComparableSalary: (min, max) => max || min || 0,
  ...over,
});

const ids = (list: Vacancy[]) => list.map((v) => v.id);

describe("filterVacancyRequests", () => {
  it("личные клоны рекрутёров в «Заявки» не попадают", () => {
    const list = [vac(1), vac(2, { extra_data: { cloned_from_request_id: 1 } } as Partial<Vacancy>)];
    expect(ids(filterVacancyRequests(list, opts()))).toEqual([1]);
  });

  it("«отказался» скрывает заявку у рекрутёра, но не у админа", () => {
    const list = [vac(1, { extra_data: { dismissed_by: [2] } } as Partial<Vacancy>)];
    expect(ids(filterVacancyRequests(list, opts({ isAdmin: false })))).toEqual([]);
    expect(ids(filterVacancyRequests(list, opts({ isAdmin: true })))).toEqual([1]);
  });

  it("«Только мои»: создал, назначен или назначена всем", () => {
    const list = [
      vac(1, { created_by: 2 }),
      vac(2, { assigned_to: [2] }),
      vac(3, { assigned_to_all: true } as Partial<Vacancy>),
      vac(4),
    ];
    expect(ids(filterVacancyRequests(list, opts({ onlyMine: true })))).toEqual([1, 2, 3]);
  });

  it("«Нераспределённые» — без назначений вообще", () => {
    const list = [vac(1), vac(2, { assigned_to: [5] }), vac(3, { assigned_to_all: true } as Partial<Vacancy>)];
    expect(ids(filterVacancyRequests(list, opts({ assignmentFilter: "unassigned" })))).toEqual([1]);
  });

  it("поиск — без регистра, по названию, отделу и тегам", () => {
    const list = [
      vac(1, { title: "Медиабайер" }),
      vac(2, { department_name: "Трафик" } as Partial<Vacancy>),
      vac(3, { tags: ["Facebook"] } as Partial<Vacancy>),
      vac(4),
    ];
    expect(ids(filterVacancyRequests(list, opts({ search: "  медиа " })))).toEqual([1]);
    expect(ids(filterVacancyRequests(list, opts({ search: "трафик" })))).toEqual([2]);
    expect(ids(filterVacancyRequests(list, opts({ search: "facebook" })))).toEqual([3]);
  });

  it("отдел, вкладка статуса и статусы быстрого фильтра", () => {
    const list = [
      vac(1, { department_id: 7, status: "open" } as Partial<Vacancy>),
      vac(2, { department_id: 8, status: "paused" } as Partial<Vacancy>),
    ];
    expect(ids(filterVacancyRequests(list, opts({ departmentFilter: 7 })))).toEqual([1]);
    expect(ids(filterVacancyRequests(list, opts({ statusFilter: "paused" })))).toEqual([2]);
    expect(
      ids(filterVacancyRequests(list, opts({ quickFilters: { statuses: ["open"], salaryRange: "any", dateRange: "any" } }))),
    ).toEqual([1]);
  });

  it("зарплата: без зарплаты под фильтр не попадает, границы включительно", () => {
    const list = [
      vac(1, { salary_max: 100000 } as Partial<Vacancy>),
      vac(2, { salary_max: 150000 } as Partial<Vacancy>),
      vac(3),
    ];
    const f = (salaryRange: string) =>
      ids(filterVacancyRequests(list, opts({ quickFilters: { statuses: [], salaryRange, dateRange: "any" } })));
    expect(f("under100k")).toEqual([1]);
    expect(f("100k-200k")).toEqual([1, 2]);
    expect(f("any")).toEqual([1, 2, 3]);
  });

  it("дата: «за 7 дней» отсекает старые", () => {
    const list = [vac(1, { created_at: daysAgo(3) }), vac(2, { created_at: daysAgo(30) })];
    expect(
      ids(filterVacancyRequests(list, opts({ quickFilters: { statuses: [], salaryRange: "any", dateRange: "7days" } }))),
    ).toEqual([1]);
  });
});
