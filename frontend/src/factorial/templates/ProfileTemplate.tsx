import { ReactNode } from 'react';
import PageHeader from '@/factorial/components/PageHeader';
import SecondaryNav from '@/factorial/components/SecondaryNav';

interface DetailRow { label: string; value: ReactNode; }
interface ProfileTemplateProps {
  breadcrumb: { label: string; href?: string }[];
  titleIcon?: ReactNode;
  title?: string;
  subNav: { label: string; href: string; end?: boolean }[];
  leftColumn: ReactNode;
  rightDetails: DetailRow[];
}

export default function ProfileTemplate({ breadcrumb, titleIcon, title, subNav, leftColumn, rightDetails }: ProfileTemplateProps) {
  return (
    <>
      <PageHeader breadcrumb={breadcrumb} />
      <div className="px-8 py-6 space-y-5">
        {(titleIcon || title) && (
          <div className="flex items-center gap-2">
            {titleIcon}
            {title && <h1 className="text-fx-xl font-semibold">{title}</h1>}
          </div>
        )}
        <SecondaryNav items={subNav} />
        <div className="grid grid-cols-[1fr_320px] gap-6 max-w-[1400px]">
          <div className="space-y-5 min-w-0">{leftColumn}</div>
          <aside className="space-y-4">
            <h6 className="text-fx-xs font-semibold uppercase tracking-wide text-text-muted">ДЕТАЛИ</h6>
            <div className="bg-card-translucent border border-card-border-soft rounded-card shadow-card divide-y divide-card-border-soft">
              {rightDetails.map((row, i) => (
                <div key={i} className="p-4">
                  <p className="text-fx-xs text-text-muted mb-1">{row.label}</p>
                  <div className="text-fx-sm">{row.value}</div>
                </div>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </>
  );
}
