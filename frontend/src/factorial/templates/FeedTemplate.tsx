import { ReactNode } from 'react';
import PageHeader from '@/factorial/components/PageHeader';
import SecondaryNav from '@/factorial/components/SecondaryNav';
import EmptyState from '@/factorial/components/EmptyState';

interface FeedTemplateProps {
  breadcrumb: { label: string; href?: string }[];
  titleIcon?: ReactNode;
  title?: string;
  secondaryNav?: { label: string; href: string; end?: boolean }[];
  toolbar?: ReactNode;
  items?: ReactNode[];
  emptyState?: Parameters<typeof EmptyState>[0];
}

export default function FeedTemplate({ breadcrumb, titleIcon, title, secondaryNav, toolbar, items, emptyState }: FeedTemplateProps) {
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
        {secondaryNav && <SecondaryNav items={secondaryNav} />}
        {toolbar}
        {(!items || items.length === 0) && emptyState ? (
          <EmptyState {...emptyState} />
        ) : (
          <div className="max-w-3xl space-y-4">{items?.map((it, i) => <div key={i}>{it}</div>)}</div>
        )}
      </div>
    </>
  );
}
