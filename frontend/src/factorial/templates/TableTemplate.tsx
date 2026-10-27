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
  /** Управляемый поиск: страница сама держит строку, чтобы знать, какие строки
   *  видны (например, для «Выбрать всех»). Без них поиск живёт внутри. */
  search?: string;
  onSearchChange?: (v: string) => void;
  /** Данные не загрузились — показываем причину вместо «Ничего не найдено». */
  error?: ReactNode;
  loading?: boolean;
}

export default function TableTemplate<T>(props: TableTemplateProps<T>) {
  const [innerSearch, setInnerSearch] = useState('');
  const search = props.search ?? innerSearch;
  const setSearch = props.onSearchChange ?? setInnerSearch;
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
    error,
    loading,
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
        {error ? (
          <div className="bg-white rounded-card shadow-card border border-border px-4 py-10 text-center text-fx-sm" style={{ color: '#B91C1C' }}>
            {error}
          </div>
        ) : loading ? (
          <div className="bg-white rounded-card shadow-card border border-border px-4 py-10 text-center text-fx-sm text-text-muted">
            Загрузка…
          </div>
        ) : data.length === 0 && emptyState ? (
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
