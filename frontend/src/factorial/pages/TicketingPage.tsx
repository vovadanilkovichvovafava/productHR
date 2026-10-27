import { Ticket as TicketIcon } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import TableTemplate from '@/factorial/templates/TableTemplate';
import StatusPill from '@/factorial/components/StatusPill';
import { ticketsMock, type Ticket } from '@/factorial/mocks/tickets';

const PRIO: Record<Ticket['priority'], 'error' | 'warning' | 'neutral'> = { High: 'error', Medium: 'warning', Low: 'neutral' };
const STATUS_MAP: Record<Ticket['status'], 'success' | 'warning' | 'neutral'> = { Open: 'warning', 'In Progress': 'success', Closed: 'neutral' };

export default function TicketingPage() {
  const columns: ColumnDef<Ticket, any>[] = [
    { accessorKey: 'id', header: '№', cell: ({ getValue }) => `#${getValue()}` },
    { accessorKey: 'subject', header: 'Тема' },
    { accessorKey: 'category', header: 'Категория' },
    { accessorKey: 'priority', header: 'Приоритет', cell: ({ getValue }) => <StatusPill label={getValue() as string} variant={PRIO[getValue() as Ticket['priority']]} dot /> },
    { accessorKey: 'sla', header: 'SLA' },
    { accessorKey: 'status', header: 'Статус', cell: ({ getValue }) => <StatusPill label={getValue() as string} variant={STATUS_MAP[getValue() as Ticket['status']]} dot /> },
  ];
  return (
    <TableTemplate breadcrumb={[{ label: 'Тикеты' }]}
      titleIcon={
        <div className="w-9 h-9 rounded-fx-lg bg-purple-100 flex items-center justify-center">
          <TicketIcon className="w-5 h-5 text-purple-600" />
        </div>
      }
      title="Тикеты"
      toolbar={{ searchKey: 'subject', searchPlaceholder: 'Поиск тикета...', primaryCta: { label: 'Создать тикет', onClick: () => alert('Demo mode') } }}
      columns={columns} data={ticketsMock} />
  );
}
