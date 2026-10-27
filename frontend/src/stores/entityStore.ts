import { create } from 'zustand';
import type { Entity, EntityType, EntityStatus, EntityWithRelations } from '@/types';
import type { EntityCreatedPayload, EntityUpdatedPayload, EntityDeletedPayload } from '@/types/websocket';
import * as api from '@/services/api';
import type { OwnershipFilter } from '@/services/api';
import { logger } from '@/utils/logger';

interface EntityFilters {
  type?: EntityType;
  status?: EntityStatus;
  search?: string;
  tags?: string;
  ownership?: OwnershipFilter;
  department_id?: number;
}

interface TypeCounts {
  all: number;
  candidate: number;
  client: number;
  contractor: number;
  lead: number;
  partner: number;
  custom: number;
}

interface EntityState {
  entities: Entity[];
  currentEntity: EntityWithRelations | null;
  isLoading: boolean;
  error: string | null;
  filters: EntityFilters;
  fetchVersion: number; // Track request version to discard stale responses
  typeCounts: TypeCounts; // Counts for each type (not affected by type filter)

  // Actions
  fetchEntities: () => Promise<void>;
  fetchTypeCounts: () => Promise<void>;
  fetchEntity: (id: number) => Promise<void>;
  createEntity: (data: Parameters<typeof api.createEntity>[0]) => Promise<Entity>;
  updateEntity: (id: number, data: Parameters<typeof api.updateEntity>[1]) => Promise<void>;
  deleteEntity: (id: number) => Promise<void>;
  setFilters: (filters: Partial<EntityFilters>) => void;
  clearFilters: () => void;
  clearCurrentEntity: () => void;
  clearError: () => void;

  // WebSocket handlers
  handleEntityCreated: (data: EntityCreatedPayload) => void;
  handleEntityUpdated: (data: EntityUpdatedPayload) => void;
  handleEntityDeleted: (data: EntityDeletedPayload) => void;
}

const initialTypeCounts: TypeCounts = {
  all: 0,
  candidate: 0,
  client: 0,
  contractor: 0,
  lead: 0,
  partner: 0,
  custom: 0,
};

export const useEntityStore = create<EntityState>((set, get) => ({
  entities: [],
  currentEntity: null,
  isLoading: false,
  error: null,
  filters: {},
  fetchVersion: 0,
  typeCounts: initialTypeCounts,

  fetchEntities: async () => {
    // Increment version to track this request
    const version = get().fetchVersion + 1;
    set({ isLoading: true, error: null, fetchVersion: version });
    try {
      const entities = await api.getEntities(get().filters);
      // Only update if this is still the latest request
      if (get().fetchVersion === version) {
        set({ entities, isLoading: false });
      }
    } catch (err) {
      // Only update error if this is still the latest request
      if (get().fetchVersion === version) {
        const message = err instanceof Error ? err.message : 'Failed to fetch entities';
        set({ error: message, isLoading: false });
      }
    }
  },

  // Fetch counts without type filter to get accurate totals
  fetchTypeCounts: async () => {
    try {
      const { filters } = get();
      // Fetch all entities without type filter to count
      const allEntities = await api.getEntities({
        ownership: filters.ownership,
        department_id: filters.department_id,
        search: filters.search,
        // Explicitly NOT passing type filter
      });

      // Count by type
      const counts: TypeCounts = {
        all: allEntities.length,
        candidate: 0,
        client: 0,
        contractor: 0,
        lead: 0,
        partner: 0,
        custom: 0,
      };

      for (const entity of allEntities) {
        if (entity.type in counts) {
          counts[entity.type as keyof Omit<TypeCounts, 'all'>]++;
        }
      }

      set({ typeCounts: counts });
    } catch (err) {
      logger.error('Failed to fetch type counts:', err);
    }
  },

  fetchEntity: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const entity = await api.getEntity(id);
      set({ currentEntity: entity, isLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch entity';
      set({ error: message, isLoading: false });
    }
  },

  createEntity: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const entity = await api.createEntity(data);
      set((state) => ({
        entities: [entity, ...state.entities],
        isLoading: false
      }));
      return entity;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create entity';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  updateEntity: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await api.updateEntity(id, data);
      set((state) => ({
        entities: state.entities.map((e) => (e.id === id ? { ...e, ...updated } : e)),
        currentEntity:
          state.currentEntity?.id === id
            ? { ...state.currentEntity, ...updated }
            : state.currentEntity,
        isLoading: false
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update entity';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  deleteEntity: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await api.deleteEntity(id);
      set((state) => ({
        entities: state.entities.filter((e) => e.id !== id),
        currentEntity: state.currentEntity?.id === id ? null : state.currentEntity,
        isLoading: false
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete entity';
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  setFilters: (filters) => {
    const oldFilters = get().filters;
    set((state) => ({ filters: { ...state.filters, ...filters } }));
    get().fetchEntities();

    // Refetch type counts if ownership, department, or search changed (not type)
    const countsAffectingFiltersChanged =
      filters.ownership !== undefined ||
      filters.department_id !== undefined ||
      filters.search !== undefined ||
      // Also refetch if type filter is being cleared (going back to 'all')
      (filters.type === undefined && oldFilters.type !== undefined);

    if (countsAffectingFiltersChanged) {
      get().fetchTypeCounts();
    }
  },

  clearFilters: () => {
    set({ filters: {} });
    get().fetchEntities();
    get().fetchTypeCounts();
  },

  clearCurrentEntity: () => set({ currentEntity: null }),

  clearError: () => set({ error: null }),

  // WebSocket handlers for real-time updates
  handleEntityCreated: (entity: EntityCreatedPayload) => {
    logger.log('[EntityStore] Entity created via WebSocket:', entity.id, entity.name);

    set((state) => {
      // Check if entity already exists (avoid duplicates)
      if (state.entities.some((e) => e.id === entity.id)) {
        return state;
      }

      // Check if entity matches current filters
      const { filters } = state;
      let shouldAdd = true;

      if (filters.type && entity.type !== filters.type) {
        shouldAdd = false;
      }
      if (filters.status && entity.status !== filters.status) {
        shouldAdd = false;
      }
      if (filters.search && !entity.name.toLowerCase().includes(filters.search.toLowerCase())) {
        shouldAdd = false;
      }

      if (shouldAdd) {
        return {
          entities: [entity, ...state.entities],
          typeCounts: {
            ...state.typeCounts,
            all: state.typeCounts.all + 1,
            [entity.type as keyof Omit<TypeCounts, 'all'>]:
              (state.typeCounts[entity.type as keyof Omit<TypeCounts, 'all'>] || 0) + 1,
          },
        };
      }

      // Update counts even if not visible (entity created but filtered out)
      return {
        typeCounts: {
          ...state.typeCounts,
          all: state.typeCounts.all + 1,
          [entity.type as keyof Omit<TypeCounts, 'all'>]:
            (state.typeCounts[entity.type as keyof Omit<TypeCounts, 'all'>] || 0) + 1,
        },
      };
    });
  },

  handleEntityUpdated: (entity: EntityUpdatedPayload) => {
    logger.log('[EntityStore] Entity updated via WebSocket:', entity.id, entity.name);

    set((state) => ({
      entities: state.entities.map((e) => (e.id === entity.id ? { ...e, ...entity } : e)),
      currentEntity:
        state.currentEntity?.id === entity.id
          ? { ...state.currentEntity, ...entity }
          : state.currentEntity,
    }));
  },

  handleEntityDeleted: (data: EntityDeletedPayload) => {
    logger.log('[EntityStore] Entity deleted via WebSocket:', data.id);

    set((state) => {
      const deletedEntity = state.entities.find((e) => e.id === data.id);
      if (!deletedEntity) {
        return state;
      }

      return {
        entities: state.entities.filter((e) => e.id !== data.id),
        currentEntity: state.currentEntity?.id === data.id ? null : state.currentEntity,
        typeCounts: {
          ...state.typeCounts,
          all: Math.max(0, state.typeCounts.all - 1),
          [deletedEntity.type as keyof Omit<TypeCounts, 'all'>]:
            Math.max(0, (state.typeCounts[deletedEntity.type as keyof Omit<TypeCounts, 'all'>] || 0) - 1),
        },
      };
    });
  },
}));
