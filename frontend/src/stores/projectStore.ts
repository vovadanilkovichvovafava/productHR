import { create } from 'zustand';
import type {
  Project, ProjectFilters, TaskKanbanBoard
} from '@/services/api/projects';
import * as api from '@/services/api';

interface ProjectState {
  // Data
  projects: Project[];
  currentProject: Project | null;
  isLoading: boolean;
  error: string | null;
  filters: ProjectFilters;
  taskKanban: TaskKanbanBoard | null;
  isKanbanLoading: boolean;

  // Actions
  fetchProjects: () => Promise<void>;
  fetchProject: (id: number) => Promise<void>;
  createProject: (data: api.ProjectCreate) => Promise<Project>;
  updateProject: (id: number, data: api.ProjectUpdate) => Promise<void>;
  deleteProject: (id: number) => Promise<void>;
  setFilters: (filters: Partial<ProjectFilters>) => void;
  clearFilters: () => void;
  fetchTaskKanban: (projectId: number) => Promise<void>;
  clearCurrentProject: () => void;
  clearError: () => void;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProject: null,
  isLoading: false,
  error: null,
  filters: {},
  taskKanban: null,
  isKanbanLoading: false,

  fetchProjects: async () => {
    set({ isLoading: true, error: null });
    try {
      const projects = await api.getProjects(get().filters);
      set({ projects, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось загрузить проекты';
      set({ error: message, isLoading: false });
    }
  },

  fetchProject: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const project = await api.getProject(id);
      set({ currentProject: project, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось загрузить проект';
      set({ error: message, isLoading: false });
    }
  },

  createProject: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const project = await api.createProject(data);
      set((state) => ({
        projects: [project, ...state.projects],
        isLoading: false
      }));
      return project;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось создать проект';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  updateProject: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.updateProject(id, data);
      set((state) => ({
        projects: state.projects.map((p) => (p.id === id ? updated : p)),
        currentProject: state.currentProject?.id === id ? updated : state.currentProject,
        isLoading: false
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось обновить проект';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  deleteProject: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await api.deleteProject(id);
      set((state) => ({
        projects: state.projects.filter((p) => p.id !== id),
        currentProject: state.currentProject?.id === id ? null : state.currentProject,
        isLoading: false
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось удалить проект';
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

  fetchTaskKanban: async (projectId) => {
    set({ isKanbanLoading: true, error: null });
    try {
      const kanban = await api.getTaskKanban(projectId);
      set({ taskKanban: kanban, isKanbanLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось загрузить канбан';
      set({ error: message, isKanbanLoading: false });
    }
  },

  clearCurrentProject: () => {
    set({ currentProject: null, taskKanban: null });
  },

  clearError: () => {
    set({ error: null });
  }
}));
