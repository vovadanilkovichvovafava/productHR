import { NavLink } from 'react-router-dom';
import { cn } from '@/factorial/lib/cn';

interface SecondaryNavItem { label: string; href: string; end?: boolean; }
export default function SecondaryNav({ items }: { items: SecondaryNavItem[] }) {
  return (
    <div className="border-b border-card-border-soft overflow-x-auto scrollbar-thin">
      <nav className="flex gap-1 whitespace-nowrap min-w-fit">
        {items.map((item) => (
          <NavLink
            key={item.href}
            to={item.href}
            end={item.end}
            className={({ isActive }) =>
              cn(
                'px-4 py-2.5 text-fx-base font-normal transition-colors relative',
                isActive
                  ? 'text-text-primary after:content-[""] after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-primary'
                  : 'text-text-primary/60 hover:text-text-primary'
              )
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
