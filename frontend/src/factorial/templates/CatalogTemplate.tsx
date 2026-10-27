import { ReactNode, useState } from 'react';
import { Search } from 'lucide-react';
import PageHeader from '@/factorial/components/PageHeader';
import SecondaryNav from '@/factorial/components/SecondaryNav';

export interface CatalogItem {
  title: string;
  description: string;
  href: string;
  locked?: boolean;
  icon?: ReactNode;
}

export interface CatalogSection { heading?: string; items: CatalogItem[]; }

interface CatalogTemplateProps {
  breadcrumb: { label: string; href?: string }[];
  secondaryNav?: { label: string; href: string; end?: boolean }[];
  searchPlaceholder?: string;
  sections: CatalogSection[];
}

export default function CatalogTemplate({ breadcrumb, secondaryNav, searchPlaceholder, sections }: CatalogTemplateProps) {
  const [query, setQuery] = useState('');

  const filteredSections = sections
    .map((s) => ({ ...s, items: s.items.filter((i) =>
      !query || i.title.toLowerCase().includes(query.toLowerCase()) || i.description.toLowerCase().includes(query.toLowerCase())
    ) }))
    .filter((s) => s.items.length > 0);

  return (
    <>
      <PageHeader breadcrumb={breadcrumb} />
      <div className="px-8 py-6 space-y-6">
        {secondaryNav && <SecondaryNav items={secondaryNav} />}
        {searchPlaceholder && (
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full pl-9 pr-3 py-2 rounded-fx-lg border border-border bg-white text-fx-sm focus:border-border-hover focus:outline-none"
            />
          </div>
        )}
        {filteredSections.length === 0 && (
          <p className="text-fx-sm text-text-muted">Ничего не найдено.</p>
        )}
        {filteredSections.map((s, idx) => (
          <section key={idx} className="space-y-3">
            {s.heading && <h2 className="text-[21px] font-medium leading-tight">{s.heading}</h2>}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {s.items.map((item) => (
                <a
                  key={item.title}
                  href={item.href}
                  className="bg-white rounded-card border border-border p-4 hover:shadow-card-hover hover:border-border-hover transition-all group"
                  onClick={(e) => { e.preventDefault(); alert(`Demo mode — переход на ${item.href}`); }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-text-primary group-hover:text-primary transition-colors">{item.title}</h3>
                      <p className="text-fx-sm text-text-muted mt-1">{item.description}</p>
                    </div>
                    {item.locked && (
                      <button type="button" className="px-2.5 py-1 text-fx-xs font-medium border border-border rounded-pill hover:bg-primary hover:text-white hover:border-primary transition-colors shrink-0">
                        Обновить
                      </button>
                    )}
                    {item.icon && <div className="shrink-0">{item.icon}</div>}
                  </div>
                </a>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
