import { LineChart as ChartLine } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import TableTemplate from '@/factorial/templates/TableTemplate';

export default function TalentAnalyticsPage() {
  return (
    <TableTemplate breadcrumb={[{ label: 'Аналитика' }]}
      titleIcon={
        <div className="w-9 h-9 rounded-fx-lg bg-violet-100 flex items-center justify-center">
          <ChartLine className="w-5 h-5 text-violet-600" />
        </div>
      }
      title="Аналитика"
      toolbar={{ searchKey: 'name', searchPlaceholder: 'Поиск...', primaryCta: { label: 'Создать главную', onClick: () => alert('Demo mode') } }}
      columns={[
        { accessorKey: 'name', header: 'Имя' },
        { accessorKey: 'author', header: 'Создано' },
        { accessorKey: 'createdAt', header: 'Создано (дата)' },
        { accessorKey: 'updatedAt', header: 'Последнее обновление' },
      ] as ColumnDef<any, any>[]}
      data={[]}
      emptyState={{ emoji: '📊', heading: 'Главные не найдены', description: 'Создайте первую панель управления для отслеживания талантов.' }}
    />
  );
}
