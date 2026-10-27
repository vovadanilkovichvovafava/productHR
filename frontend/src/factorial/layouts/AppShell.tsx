import { Outlet } from 'react-router-dom';
import { useSidebarStore } from '@/factorial/stores/useSidebarStore';
import { useAIDrawerStore } from '@/factorial/stores/useAIDrawerStore';
import Sidebar from './Sidebar';
import AIDrawer from './AIDrawer';
import HelpButton from './HelpButton';

export default function AppShell() {
  const sidebarCollapsed = useSidebarStore((s) => s.collapsed);
  const aiOpen = useAIDrawerStore((s) => s.open);

  const sidebarWidth = sidebarCollapsed ? 64 : 240;
  const aiWidth = aiOpen ? 380 : 0;

  return (
    <div className="min-h-screen flex">
      <aside
        style={{ width: sidebarWidth }}
        className="shrink-0 h-screen sticky top-0 transition-all duration-200"
      >
        <Sidebar />
      </aside>

      <main className="flex-1 min-w-0 overflow-y-auto h-screen">
        <Outlet />
      </main>

      <aside
        style={{ width: aiWidth }}
        className="shrink-0 h-screen sticky top-0 overflow-hidden transition-all duration-200"
      >
        {aiOpen && <AIDrawer />}
      </aside>

      {/* Help launcher (Intercom-style) — bottom-right floating with popup menu */}
      <HelpButton />
    </div>
  );
}
