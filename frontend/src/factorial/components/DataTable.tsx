import { useState } from 'react';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  SortingState,
} from '@tanstack/react-table';
import { ArrowUpDown } from 'lucide-react';
import { cn } from '@/factorial/lib/cn';
import PaginationBar from './PaginationBar';

interface DataTableProps<T> {
  columns: ColumnDef<T, any>[];
  data: T[];
  pageSize?: number;
  searchKey?: string;
  searchValue?: string;
  onRowClick?: (row: T) => void;
}

export default function DataTable<T>({
  columns,
  data,
  pageSize = 8,
  searchKey,
  searchValue,
  onRowClick,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pageIndex, setPageIndex] = useState(0);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, pagination: { pageIndex, pageSize }, globalFilter: searchValue },
    onSortingChange: setSorting,
    onPaginationChange: (updater) => {
      const next = typeof updater === 'function' ? updater({ pageIndex, pageSize }) : updater;
      setPageIndex(next.pageIndex);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    globalFilterFn: (row, _columnId, filterValue) => {
      if (!filterValue || !searchKey) return true;
      const val = (row.original as any)[searchKey];
      return String(val ?? '').toLowerCase().includes(String(filterValue).toLowerCase());
    },
  });

  const total = table.getFilteredRowModel().rows.length;

  return (
    <div className="bg-white rounded-card shadow-card overflow-hidden border border-border">
      <table className="w-full text-fx-sm">
        <thead className="bg-sidebar-hover/50 text-text-muted">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th key={header.id} className="px-4 py-2.5 text-left font-medium">
                  {header.column.getCanSort() ? (
                    <button
                      type="button"
                      onClick={header.column.getToggleSortingHandler()}
                      className="inline-flex items-center gap-1 hover:text-text-primary"
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <ArrowUpDown className="w-3 h-3" />
                    </button>
                  ) : (
                    flexRender(header.column.columnDef.header, header.getContext())
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className={cn(
                'border-t border-border hover:bg-sidebar-hover/30 transition-colors',
                onRowClick && 'cursor-pointer'
              )}
              onClick={() => onRowClick?.(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {table.getRowModel().rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-4 py-12 text-center text-text-muted">
                Ничего не найдено
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {total > pageSize && (
        <PaginationBar
          current={pageIndex + 1}
          total={total}
          pageSize={pageSize}
          onChange={(p) => setPageIndex(p - 1)}
        />
      )}
    </div>
  );
}
