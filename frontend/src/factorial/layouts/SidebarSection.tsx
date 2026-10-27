import type { LucideIcon } from 'lucide-react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/factorial/lib/cn';
import { useSidebarStore } from '@/factorial/stores/useSidebarStore';
import SidebarItem from './SidebarItem';

interface Section {
  key: string;
  label: string;
  items: { icon: LucideIcon; label: string; href: string; external?: boolean }[];
}

export default function SidebarSection({ section }: { section: Section }) {
  const { collapsed, expandedSections, toggleSection } = useSidebarStore();
  const expanded = expandedSections[section.key] ?? true;

  if (collapsed) {
    return (
      <div className="space-y-1">
        {section.items.map((item) => (
          <SidebarItem key={item.label + item.href} {...item} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={() => toggleSection(section.key)}
        className="w-full flex items-center justify-between px-3 py-1.5 text-fx-xs font-medium tracking-tight hover:text-text-primary transition-colors"
        style={{ color: 'rgba(1, 22, 55, 0.61)' }}
      >
        <span>{section.label}</span>
        <ChevronDown
          className={cn('w-3 h-3 transition-transform', !expanded && '-rotate-90')}
        />
      </button>
      {expanded && (
        <div className="space-y-0.5">
          {section.items.map((item) => (
            <SidebarItem key={item.label + item.href} {...item} />
          ))}
        </div>
      )}
    </div>
  );
}
