import type { LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/factorial/lib/cn';
import { useSidebarStore } from '@/factorial/stores/useSidebarStore';

interface SidebarItemProps {
  icon: LucideIcon;
  label: string;
  href: string;
  external?: boolean;
}

export default function SidebarItem({ icon: Icon, label, href, external }: SidebarItemProps) {
  const collapsed = useSidebarStore((s) => s.collapsed);

  if (external) {
    return (
      <button
        type="button"
        className={cn(
          'w-full flex items-center gap-2 pl-1.5 pr-2 py-1.5 rounded-fx-lg text-fx-sm font-medium text-text-primary hover:bg-sidebar-hover transition-colors',
          collapsed && 'justify-center px-0'
        )}
        title={collapsed ? label : undefined}
        onClick={() => window.alert(`«${label}» — внешний раздел Factorial. В демо-режиме недоступен.`)}
      >
        <Icon className="w-5 h-5 shrink-0" strokeWidth={1} />
        {!collapsed && <span className="truncate">{label}</span>}
      </button>
    );
  }

  return (
    <NavLink
      to={href}
      className={({ isActive }) =>
        cn(
          'w-full flex items-center gap-2 pl-1.5 pr-2 py-1.5 rounded-fx-lg text-fx-sm font-medium text-text-primary transition-colors',
          isActive
            ? 'bg-sidebar-active'
            : 'hover:bg-sidebar-hover',
          collapsed && 'justify-center px-0'
        )
      }
      title={collapsed ? label : undefined}
    >
      <Icon className="w-5 h-5 shrink-0" strokeWidth={1} />
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  );
}
