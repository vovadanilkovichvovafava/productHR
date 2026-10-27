import { create } from 'zustand';

interface FormBadgeState {
  counts: Record<number, number>;
  setCount: (entityId: number, count: number) => void;
  bump: (entityId: number) => void;
  clear: (entityId: number) => void;
}

export const useFormBadgeStore = create<FormBadgeState>((set) => ({
  counts: {},
  setCount: (entityId, count) => set((s) => ({ counts: { ...s.counts, [entityId]: count } })),
  bump: (entityId) => set((s) => ({ counts: { ...s.counts, [entityId]: (s.counts[entityId] || 0) + 1 } })),
  clear: (entityId) => set((s) => ({ counts: { ...s.counts, [entityId]: 0 } })),
}));
