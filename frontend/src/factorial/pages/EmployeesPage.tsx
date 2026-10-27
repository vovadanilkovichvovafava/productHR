import { useState } from 'react';
import { Users, Trash2, FolderInput, Download, Pencil } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ColumnDef } from '@tanstack/react-table';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as XLSX from 'xlsx';
import TableTemplate from '@/factorial/templates/TableTemplate';
import UserAvatar from '@/factorial/components/UserAvatar';
import StatusPill from '@/factorial/components/StatusPill';
import { listEmployees, dismissEmployee, downloadEmployeeTemplate } from '@/factorial/api/employees';
import { getOrgChart, assignEmployee } from '@/factorial/api/orgUnits';
import { formatHiredAgo } from '@/factorial/lib/formatDate';
import InviteEmployeeModal from '@/factorial/components/InviteEmployeeModal';
import EmployeeEditModal from '@/factorial/components/EmployeeEditModal';
import BulkEditEmployeesModal from '@/factorial/components/BulkEditEmployeesModal';
import type { Employee } from '@/factorial/mocks/employees';

export default function EmployeesPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [invite, setInvite] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveUnit, setMoveUnit] = useState('');
  const [editId, setEditId] = useState<number | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);

  const { data: rows = [] } = useQuery({ queryKey: ['fx', 'employees', 'table'], queryFn: () => listEmployees(true) });
  const { data: chart } = useQuery({ queryKey: ['fx', 'org-chart'], queryFn: getOrgChart });
  const people = chart?.people ?? [];
  const units = chart?.units ?? [];
  const metaOf = (empId: number) => {
    const p = people.find((x) => x.id === empId);
    if (!p) return { dept: '—', manager: '—' };
    const dept = p.org_unit_id ? (units.find((u) => u.id === p.org_unit_id)?.name || '—') : '—';
    const manager = p.manager_id ? (people.find((x) => x.id === p.manager_id)?.user_name || '—') : '—';
    return { dept, manager };
  };
  const employees: Employee[] = rows.map((e) => ({
    id: e.id,
    fullName: e.user_name || '—',
    position: e.position || '',
    location: e.department_name || 'MSTech L.L.C-FZ',
    hiredAt: e.department_start_date || e.practice_start_date || e.created_at || '',
    accessStatus: e.is_active ? 'active' : 'inactive',
    contractStatus: e.contract_signed ? 'completed' : 'in_progress',
  }));

  // Выделение строк (по id, сохраняется между страницами/поиском)
  const toggle = (id: number) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const allIds = employees.map((e) => e.id);
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(allIds));
  const clear = () => setSelected(new Set());

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['fx', 'employees'] });
    qc.invalidateQueries({ queryKey: ['fx', 'org-chart'] });
  };

  // allSettled: пытаемся обработать ВСЕХ выбранных, считаем частичные ошибки и
  // всегда показываем фидбэк — деструктивное действие не должно падать молча.
  const dismissM = useMutation({
    mutationFn: async () => {
      const ids = Array.from(selected);
      const res = await Promise.allSettled(ids.map((id) => dismissEmployee(id)));
      return { total: ids.length, failed: res.filter((r) => r.status === 'rejected').length };
    },
    onSuccess: ({ total, failed }) => {
      refresh(); clear();
      if (failed) toast.error(`Уволено ${total - failed} из ${total}, ошибок: ${failed}`);
      else toast.success(`Уволено: ${total}`);
    },
    onError: () => toast.error('Не удалось уволить выбранных'),
  });
  const moveM = useMutation({
    mutationFn: async () => {
      const unitId = moveUnit ? Number(moveUnit) : null;
      const ids = Array.from(selected);
      const res = await Promise.allSettled(ids.map((id) => assignEmployee(id, unitId)));
      return { total: ids.length, failed: res.filter((r) => r.status === 'rejected').length };
    },
    onSuccess: ({ total, failed }) => {
      refresh(); clear(); setMoveOpen(false); setMoveUnit('');
      if (failed) toast.error(`Перемещено ${total - failed} из ${total}, ошибок: ${failed}`);
      else toast.success(`Перемещено: ${total}`);
    },
    onError: () => toast.error('Не удалось переместить выбранных'),
  });

  const onDismiss = () => {
    if (!selected.size) return;
    if (window.confirm(`Уволить выбранных (${selected.size})? Станут неактивными, данные не удаляются.`)) dismissM.mutate();
  };
  const onExportAll = () => { void downloadEmployeeTemplate({ filled: true }); };

  const onExport = () => {
    const sel = employees.filter((e) => selected.has(e.id));
    const data = sel.map((e) => ({
      'Сотрудник': e.fullName,
      'Должность': e.position,
      'Отдел': metaOf(e.id).dept,
      'Руководитель': metaOf(e.id).manager,
      'Место работы': e.location,
      'Доступ': e.accessStatus === 'active' ? 'Активен' : 'Неактивен',
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Сотрудники');
    XLSX.writeFile(wb, 'employees-selected.xlsx');
  };

  const columns: ColumnDef<Employee, any>[] = [
    {
      id: 'select',
      enableSorting: false,
      header: () => (
        <input type="checkbox" className="rounded border-border" checked={allSelected} onChange={toggleAll} onClick={(e) => e.stopPropagation()} aria-label="Выбрать всех" />
      ),
      cell: ({ row }) => (
        <input type="checkbox" className="rounded border-border" checked={selected.has(row.original.id)} onChange={() => toggle(row.original.id)} onClick={(e) => e.stopPropagation()} />
      ),
      size: 32,
    },
    {
      accessorKey: 'fullName',
      header: 'Сотрудник',
      cell: ({ row }) => (
        <div className="flex items-center gap-2.5">
          <UserAvatar fullName={row.original.fullName} size="sm" singleLetter />
          <button
            type="button"
            className="font-medium cursor-pointer hover:underline"
            style={{ color: '#DC2626', background: 'none', border: 'none', padding: 0 }}
            onClick={() => navigate(`/factorial/employees/${row.original.id}`)}
          >
            {row.original.fullName}
          </button>
        </div>
      ),
    },
    { accessorKey: 'position', header: 'Должность', cell: ({ getValue }) => (getValue() as string) || '' },
    { id: 'dept', header: 'Отдел', accessorFn: (r) => metaOf(r.id).dept },
    { id: 'manager', header: 'Руководитель', accessorFn: (r) => metaOf(r.id).manager },
    { accessorKey: 'location', header: 'Место работы' },
    { accessorKey: 'hiredAt', header: 'Нанят', cell: ({ getValue }) => { const v = getValue() as string; return v ? formatHiredAgo(v) : '—'; } },
    {
      accessorKey: 'accessStatus',
      header: 'Доступ',
      cell: ({ getValue }) => <StatusPill label={getValue() === 'active' ? 'Активен' : 'Неактивен'} />,
    },
    {
      accessorKey: 'contractStatus',
      header: 'Статус контракта',
      cell: () => <StatusPill label="В процессе" variant="success" dot />,
    },
  ];

  return (
    <>
      <TableTemplate
        breadcrumb={[{ label: 'Сотрудники' }]}
        titleIcon={
          <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
            <Users className="w-5 h-5 text-pink-600" />
          </div>
        }
        title="Сотрудники"
        secondaryNav={[
          { label: 'Сотрудники', href: '/factorial/employees', end: true },
          { label: 'Команды', href: '/factorial/employees/teams' },
          { label: 'Оргсхема', href: '/factorial/employees/org-chart' },
        ]}
        beforeToolbar={
          <div className="grid grid-cols-2 gap-3 max-w-md">
            <MiniCard label="0 ожидает принятия" />
            <MiniCard label="0 не приглашен" />
          </div>
        }
        toolbar={{
          searchKey: 'fullName',
          searchPlaceholder: 'Поиск сотрудника...',
          filterAction: () => alert('Demo mode — фильтры'),
          exportAction: () => navigate('/factorial/employees/export'),
          moreActions: (
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-fx-lg border border-border bg-white hover:bg-sidebar-hover text-fx-sm"
                onClick={onExportAll}
              >
                Экспорт
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-fx-lg border border-border bg-white hover:bg-sidebar-hover text-fx-sm"
                onClick={() => navigate('/factorial/employees/import')}
              >
                Импорт
              </button>
            </div>
          ),
          primaryCta: { label: 'Добавить сотрудника', onClick: () => setInvite(true) },
        }}
        columns={columns}
        data={employees}
        pageSize={20}
      />

      {invite && <InviteEmployeeModal onClose={() => setInvite(false)} />}
      {editId != null && <EmployeeEditModal employeeId={editId} onClose={() => setEditId(null)} onSaved={refresh} />}
      {bulkOpen && (
        <BulkEditEmployeesModal
          employees={rows.filter((r) => selected.has(r.id))}
          onClose={() => setBulkOpen(false)}
          onSaved={() => { refresh(); clear(); }}
        />
      )}

      {moveOpen && (
        <div className="fx-modal-overlay" onClick={() => setMoveOpen(false)}>
          <div className="fx-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Переместить в отдел ({selected.size})</h3>
            <div className="fx-field">
              <label>Отдел</label>
              <select className="fx-select" value={moveUnit} onChange={(e) => setMoveUnit(e.target.value)}>
                <option value="">— Без отдела —</option>
                {units.map((u) => (<option key={u.id} value={u.id}>{u.name}</option>))}
              </select>
            </div>
            <div className="fx-modal-actions">
              <button type="button" className="fx-btn fx-btn--secondary" onClick={() => setMoveOpen(false)}>Отмена</button>
              <button type="button" className="fx-btn fx-btn--primary" disabled={moveM.isPending} onClick={() => moveM.mutate()}>{moveM.isPending ? 'Перемещение…' : 'Переместить'}</button>
            </div>
          </div>
        </div>
      )}

      {selected.size > 0 && (
        <div
          className="fixed left-1/2 -translate-x-1/2 bottom-6 z-50 flex items-center gap-1.5 rounded-2xl px-3 py-2"
          style={{ background: '#0F172A', boxShadow: '0 14px 36px rgba(0,0,0,0.4)' }}
        >
          <span className="text-fx-sm px-2 font-semibold" style={{ color: '#FFFFFF' }}>{selected.size} выбрано</span>
          <span style={{ width: 1, height: 22, background: 'rgba(255,255,255,0.2)' }} />
          <button type="button" className="px-3 py-1.5 rounded-lg text-fx-sm font-medium hover:bg-white/15" style={{ color: '#FFFFFF' }} onClick={clear}>Снять</button>
          <button type="button" className="px-3 py-1.5 rounded-lg text-fx-sm font-medium inline-flex items-center gap-1.5 hover:bg-white/15" style={{ color: '#FFFFFF' }} onClick={() => setMoveOpen(true)}>
            <FolderInput className="w-4 h-4" />Переместить
          </button>
          <button type="button" className="px-3 py-1.5 rounded-lg text-fx-sm font-medium inline-flex items-center gap-1.5 hover:bg-white/15" style={{ color: '#FFFFFF' }} onClick={onExport}>
            <Download className="w-4 h-4" />Экспорт
          </button>
          <button type="button" className="px-3 py-1.5 rounded-lg text-fx-sm font-medium inline-flex items-center gap-1.5 hover:bg-white/15" style={{ color: '#FFFFFF' }} onClick={() => (selected.size === 1 ? setEditId(Array.from(selected)[0]) : setBulkOpen(true))}>
            <Pencil className="w-4 h-4" />Редактировать
          </button>
          <button type="button" className="px-3 py-1.5 rounded-lg text-fx-sm font-semibold inline-flex items-center gap-1.5 disabled:opacity-60 hover:brightness-110" style={{ background: '#DC2626', color: '#FFFFFF' }} onClick={onDismiss} disabled={dismissM.isPending}>
            <Trash2 className="w-4 h-4" />{dismissM.isPending ? 'Увольнение…' : 'Уволить'}
          </button>
        </div>
      )}
    </>
  );
}

function MiniCard({ label }: { label: string }) {
  return (
    <div className="bg-white rounded-fx-lg border border-border px-4 py-3 flex items-center justify-between">
      <span className="text-fx-sm">{label}</span>
      <button type="button" className="p-1 rounded hover:bg-sidebar-hover text-text-muted">⚙</button>
    </div>
  );
}
