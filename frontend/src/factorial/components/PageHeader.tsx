import { ReactNode } from 'react';
import { Bell } from 'lucide-react';
import Breadcrumb from './Breadcrumb';
import { useAIDrawerStore } from '@/factorial/stores/useAIDrawerStore';

interface PageHeaderProps {
  breadcrumb: { label: string; href?: string }[];
  rightContent?: ReactNode;
}

export default function PageHeader({ breadcrumb, rightContent }: PageHeaderProps) {
  const aiOpen = useAIDrawerStore((s) => s.open);
  const toggleAI = useAIDrawerStore((s) => s.toggle);

  return (
    <div className="flex items-center justify-between px-8 py-4 border-b border-border bg-white/40 backdrop-blur-sm sticky top-0 z-10">
      <Breadcrumb items={breadcrumb} />
      <div className="flex items-center gap-3">
        {rightContent}
        <button type="button" className="p-2 rounded-fx-lg hover:bg-sidebar-hover" title="Уведомления">
          <Bell className="w-4 h-4 text-text-muted" />
        </button>
        {!aiOpen && (
          <button
            type="button"
            onClick={toggleAI}
            className="w-8 h-8 rounded-full hover:scale-105 transition-transform"
            style={{ background: 'conic-gradient(from 180deg, #F5A51C, #E61A42, #F5A51C)' }}
            title="Открыть Опе"
            aria-label="Открыть Опе"
          />
        )}
      </div>
    </div>
  );
}
