import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface SidebarState {
  collapsed: boolean;
  expandedSections: Record<string, boolean>;
  toggleCollapsed: () => void;
  toggleSection: (key: string) => void;
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      collapsed: false,
      expandedSections: { personal: true, company: true, talents: true, other: true },
      toggleCollapsed: () => set((s) => ({ collapsed: !s.collapsed })),
      toggleSection: (key) =>
        set((s) => ({ expandedSections: { ...s.expandedSections, [key]: !s.expandedSections[key] } })),
    }),
    { name: 'factorial-sidebar' }
  )
);
