import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AIDrawerState {
  open: boolean;
  toggle: () => void;
  setOpen: (open: boolean) => void;
}

export const useAIDrawerStore = create<AIDrawerState>()(
  persist(
    (set) => ({
      open: false,
      toggle: () => set((s) => ({ open: !s.open })),
      setOpen: (open) => set({ open }),
    }),
    { name: 'factorial-ai-drawer-v2' }
  )
);
