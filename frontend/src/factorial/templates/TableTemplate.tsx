import { ReactNode, useState } from 'react';
import { ColumnDef } from '@tanstack/react-table';
import PageHeader from '@/factorial/components/PageHeader';
import SecondaryNav from '@/factorial/components/SecondaryNav';
import Toolbar from '@/factorial/components/Toolbar';
import DataTable from '@/factorial/components/DataTable';
import EmptyState from '@/factorial/components/EmptyState';

interface TableTemplateProps<T> {
  breadcrumb: { label: string; href?: string }[];
  titleIcon?: ReactNode;
  title?: string;
  secondaryNav?: { label: string; href: string; end?: boolean }[];
  stats?: { label: string; value: string | number }[];
  beforeToolbar?: ReactNode;
  toolbar?: Omit<Parameters<typeof Toolbar>[0], 'searchValue' | 'onSearchChange'> & {
    searchKey?: string;
    searchPlaceholder?: string;
  };
  columns: ColumnDef<T, any>[];
  data: T[];
  pageSize?: number;
  emptyState?: Parameters<typeof EmptyState>[0];
}

export default function TableTemplate<T>(props: TableTemplateProps<T>) {
  const [search, setSearch] = useState('');
  const {
    breadcrumb,
    titleIcon,
    title,
    secondaryNav,
    stats,
    beforeToolbar,
    toolbar,
    columns,
    data,
    pageSize = 8,
    emptyState,
  } = props;

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
        {stats && (
          <div className="flex gap-6 text-fx-base">
            {stats.map((s) => (
              <div key={s.label} className="flex items-center gap-2">
                <span className="text-text-primary">{s.label}</span>
                <span className="font-medium text-text-primary">{s.value}</span>
              </div>
            ))}
          </div>
        )}
        {beforeToolbar}
        {toolbar && (
          <Toolbar
            {...toolbar}
            searchValue={search}
            onSearchChange={toolbar.searchKey ? setSearch : undefined}
          />
        )}
        {data.length === 0 && emptyState ? (
          <EmptyState {...emptyState} />
        ) : (
          <DataTable
            columns={columns}
            data={data}
            pageSize={pageSize}
            searchKey={toolbar?.searchKey}
            searchValue={search}
          />
        )}
      </div>
    </>
  );
}
