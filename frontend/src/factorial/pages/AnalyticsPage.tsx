import { BarChart3 as ChartBar } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import TableTemplate from '@/factorial/templates/TableTemplate';

export default function AnalyticsPage() {
  return (
    <TableTemplate breadcrumb={[{ label: 'Аналитика' }]}
      titleIcon={
        <div className="w-9 h-9 rounded-fx-lg bg-emerald-100 flex items-center justify-center">
          <ChartBar className="w-5 h-5 text-emerald-600" />
        </div>
      }
      title="Главные"
      secondaryNav={[
        { label: 'Расширенные отчеты', href: '/analytics/reports/dashboards/list', end: true },
        { label: 'Аналитика', href: '/analytics/insights' },
      ]}
      toolbar={{ searchKey: 'name', searchPlaceholder: 'Поиск...', primaryCta: { label: 'Создать главную', onClick: () => alert('Demo mode') } }}
      columns={[
        { accessorKey: 'name', header: 'Имя' },
        { accessorKey: 'author', header: 'Создано' },
        { accessorKey: 'createdAt', header: 'Создано (дата)' },
        { accessorKey: 'updatedAt', header: 'Последнее обновление' },
      ] as ColumnDef<any, any>[]}
      data={[]}
      emptyState={{ emoji: '📊', heading: 'Главные не найдены', description: 'Здесь отображаются все панели управления вашей организации.' }}
    />
  );
}
