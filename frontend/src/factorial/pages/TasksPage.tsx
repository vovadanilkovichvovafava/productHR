import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Target } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import TableTemplate from '@/factorial/templates/TableTemplate';
import UserAvatar from '@/factorial/components/UserAvatar';
import StatusPill from '@/factorial/components/StatusPill';
import PromoBanner from '@/factorial/components/PromoBanner';
import { tasksMock, type Task } from '@/factorial/mocks/tasks';
import { formatShortDateRu } from '@/factorial/lib/formatDate';

export default function TasksPage() {
  const navigate = useNavigate();
  const stats = useMemo(() => {
    const overdue = tasksMock.filter((t) => t.dueDate && new Date(t.dueDate) < new Date()).length;
    const due = tasksMock.filter((t) => t.dueDate).length;
    const noDate = tasksMock.filter((t) => !t.dueDate).length;
    return [
      { label: 'Всего задач', value: tasksMock.length },
      { label: 'Срок выполнения', value: due },
      { label: 'Просрочено', value: overdue },
      { label: 'Без срока', value: noDate },
    ];
  }, []);

  const columns: ColumnDef<Task, any>[] = [
    {
      id: 'select',
      header: '',
      cell: () => <input type="checkbox" className="rounded border-border" />,
      size: 32,
    },
    {
      accessorKey: 'title',
      header: 'Название задачи',
      cell: ({ row }) => (
        <Link
          to={`/tasks/${row.original.id}`}
          className="hover:underline"
          onClick={(e) => e.preventDefault()}
        >
          {row.original.title}
        </Link>
      ),
    },
    { accessorKey: 'assignee', header: 'Участник' },
    { accessorKey: 'project', header: 'Принадлежит' },
    {
      accessorKey: 'executor',
      header: 'Исполнители',
      cell: ({ row }) => <UserAvatar fullName={row.original.executor} size="sm" />,
    },
    {
      accessorKey: 'status',
      header: 'Статус',
      cell: ({ getValue }) => <StatusPill label={getValue() as string} variant="success" dot />,
    },
    {
      accessorKey: 'dueDate',
      header: 'Дата окончания',
      cell: ({ getValue }) => (getValue() ? formatShortDateRu(getValue() as string) : '—'),
    },
  ];

  return (
    <TableTemplate
      breadcrumb={[{ label: 'Задачи' }]}
      titleIcon={<div className="w-9 h-9 rounded-fx-lg bg-red-100 flex items-center justify-center"><Target className="w-5 h-5 text-red-600" /></div>}
      title="Задачи"
      stats={stats}
      beforeToolbar={
        <PromoBanner
          heading="Управляйте проектами как профессионал"
          description="Планируйте с учётом реальной загрузки команды, отслеживайте время и прибыль."
          ctaLabel="Подробнее"
          onCta={() => alert('Demo mode — Projects upsell')}
        />
      }
      toolbar={{
        searchKey: 'title',
        searchPlaceholder: 'Поиск задачи...',
        filterAction: () => alert('Demo mode — фильтры'),
        primaryCta: { label: 'Создать задачу', onClick: () => navigate('/factorial/tasks/new') },
      }}
      columns={columns}
      data={tasksMock}
      pageSize={8}
    />
  );
}
