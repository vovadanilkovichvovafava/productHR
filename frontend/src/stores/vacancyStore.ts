import { create } from 'zustand';
import type { Vacancy, VacancyStatus } from '@/types';
import * as api from '@/services/api';

interface VacancyFilters {
  status?: VacancyStatus;
  department_id?: number;
  search?: string;
}

interface VacancyState {
  // Vacancies list
  vacancies: Vacancy[];
  vacanciesForSelect: Vacancy[]; // Open vacancies for dropdown selection
  currentVacancy: Vacancy | null;
  isLoading: boolean;
  error: string | null;
  filters: VacancyFilters;


  // Actions - Vacancies
  fetchVacancies: (silent?: boolean) => Promise<void>;
  fetchVacanciesForSelect: () => Promise<void>;
  fetchVacancy: (id: number) => Promise<void>;
  createVacancy: (data: api.VacancyCreate) => Promise<Vacancy>;
  updateVacancy: (id: number, data: api.VacancyUpdate) => Promise<void>;
  deleteVacancy: (id: number) => Promise<void>;
  setFilters: (filters: Partial<VacancyFilters>) => void;
  clearFilters: () => void;
  clearCurrentVacancy: () => void;


  // Utility
  clearError: () => void;
}

export const useVacancyStore = create<VacancyState>((set, get) => ({
  vacancies: [],
  vacanciesForSelect: [],
  currentVacancy: null,
  isLoading: false,
  error: null,
  filters: {},

  // === VACANCIES ===

  fetchVacancies: async (silent = false) => {
    // silent=true: фоновый рефреш без скелетона (например, при возврате на вкладку),
    // чтобы список не «моргал» как перезагрузка страницы.
    if (!silent) set({ isLoading: true });
    set({ error: null });
    try {
      const raw = await api.getAllVacancies(get().filters);
      // Бэк может вернуть клоны одной вакансии (JOIN с откликами: N откликов →
      // N строк). Дедуплим по id, иначе списки/дропдауны («Переместить» и т.п.)
      // показывают «Mob dev ×2, Трафик ×2» вместо двух реальных вакансий.
      const seen = new Set<number>();
      const vacancies = raw.filter((v) => {
        if (seen.has(v.id)) return false;
        seen.add(v.id);
        return true;
      });
      set(silent ? { vacancies } : { vacancies, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch vacancies';
      set(silent ? { error: message } : { error: message, isLoading: false });
    }
  },

  fetchVacanciesForSelect: async () => {
    try {
      // Fetch only open vacancies for dropdown selection (все страницы, не первые 50).
      const vacancies = await api.getAllVacancies({ status: 'open' });
      set({ vacanciesForSelect: vacancies });
    } catch (err) {
      console.error('Failed to fetch vacancies for select:', err);
    }
  },

  fetchVacancy: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const vacancy = await api.getVacancy(id);
      set({ currentVacancy: vacancy, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch vacancy';
      set({ error: message, isLoading: false });
    }
  },

  createVacancy: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const vacancy = await api.createVacancy(data);
      set((state) => ({
        vacancies: [vacancy, ...state.vacancies],
        isLoading: false
      }));
      return vacancy;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create vacancy';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  updateVacancy: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.updateVacancy(id, data);
      set((state) => ({
        vacancies: state.vacancies.map((v) => (v.id === id ? updated : v)),
        currentVacancy: state.currentVacancy?.id === id ? updated : state.currentVacancy,
        isLoading: false
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update vacancy';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  deleteVacancy: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await api.deleteVacancy(id);
      set((state) => ({
        vacancies: state.vacancies.filter((v) => v.id !== id),
        currentVacancy: state.currentVacancy?.id === id ? null : state.currentVacancy,
        isLoading: false
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete vacancy';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  setFilters: (filters) => {
    set((state) => ({
      filters: { ...state.filters, ...filters }
    }));
  },

  clearFilters: () => {
    set({ filters: {} });
  },

  clearCurrentVacancy: () => {
    set({ currentVacancy: null });
  },

  // === STATS ===

  // === UTILITY ===

  clearError: () => {
    set({ error: null });
  }
}));
