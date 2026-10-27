import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '@/factorial/lib/cn';

interface BreadcrumbItem { label: string; href?: string; }
export default function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  if (items.length === 0) return null;
  return (
    <nav aria-label="breadcrumb" className="flex items-center gap-1.5 text-fx-sm">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-1.5">
          {item.href ? (
            <Link to={item.href} className="text-text-secondary hover:text-text-primary">
              {item.label}
            </Link>
          ) : (
            <span className={cn('text-text-secondary', i === items.length - 1 && 'text-text-primary font-medium')}>
              {item.label}
            </span>
          )}
          {i < items.length - 1 && <ChevronRight className="w-3.5 h-3.5 text-text-muted" />}
        </div>
      ))}
    </nav>
  );
}
