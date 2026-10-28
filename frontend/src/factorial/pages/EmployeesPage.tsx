import { useMemo, useState } from 'react';
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
import { backdropClose } from '@/utils/backdropClose';
import HrConfirm from '@/components/hr/HrConfirm';
import { getErrorDetail } from '@/utils';
import { matchesSearch, allVisibleSelected, toggleAllVisible } from '@/factorial/lib/tableSelection';

// Строка таблицы сотрудников.
interface EmployeeRow {
  id: number;
  fullName: string;
  position: string;
  location: string;
  hiredAt: string;
  accessStatus: 'active' | 'inactive';
  contractStatus: 'completed' | 'in_progress';
}

const SEARCH_KEY = 'fullName';

export default function EmployeesPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [invite, setInvite] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveUnit, setMoveUnit] = useState('');
  const [editId, setEditId] = useState<number | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [confirmDismiss, setConfirmDismiss] = useState(false);
  const [exportingAll, setExportingAll] = useState(false);

  const { data: rowsData, isLoading, isError, error } = useQuery({ queryKey: ['fx', 'employees', 'table'], queryFn: () => listEmployees(true) });
  const rows = useMemo(() => rowsData ?? [], [rowsData]);
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
  // useMemo: новый массив на каждый рендер сбрасывал бы таблицу на первую
  // страницу (autoResetPageIndex у TanStack срабатывает на смену data).
  const employees: EmployeeRow[] = useMemo(() => rows.map((e) => ({
    id: e.id,
    fullName: e.user_name || '—',
    position: e.position || '',
    location: e.department_name || '',
    hiredAt: e.department_start_date || e.practice_start_date || e.created_at || '',
    accessStatus: e.is_active ? 'active' : 'inactive',
    contractStatus: e.contract_signed ? 'completed' : 'in_progress',
  })), [rows]);

  // Выделение строк (по id, сохраняется между страницами/поиском).
  // «Выбрать всех» — только найденные поиском (тем же отбором, что и таблица).
  const toggle = (id: number) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const visibleIds = useMemo(
    () => employees.filter((e) => matchesSearch(e, SEARCH_KEY, search)).map((e) => e.id),
    [employees, search],
  );
  const allSelected = allVisibleSelected(selected, visibleIds);
  const toggleAll = () => setSelected((s) => toggleAllVisible(s, visibleIds));
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
      refresh(); clear(); setConfirmDismiss(false);
      if (failed) toast.error(`Уволено ${total - failed} из ${total}, ошибок: ${failed}`);
      else toast.success(`Уволено: ${total}`);
    },
    onError: (e) => { setConfirmDismiss(false); toast.error(getErrorDetail(e, 'Не удалось уволить выбранных')); },
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
    onError: (e) => toast.error(getErrorDetail(e, 'Не удалось переместить выбранных')),
  });

  const onDismiss = () => {
    if (!selected.size) return;
    setConfirmDismiss(true);
  };
  const onExportAll = async () => {
    setExportingAll(true);
    try {
      await downloadEmployeeTemplate({ filled: true });
    } catch (e) {
      toast.error(getErrorDetail(e, 'Не удалось выгрузить сотрудников'));
    } finally {
      setExportingAll(false);
    }
  };

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

  const columns: ColumnDef<EmployeeRow, any>[] = [
    {
      id: 'select',
      enableSorting: false,
      header: () => (
        <input type="checkbox" className="rounded border-border" checked={allSelected} onChange={toggleAll} onClick={(e) => e.stopPropagation()} aria-label="Выбрать всех" />
      ),
      cell: ({ row }) => (
        <input type="checkbox" className="rounded border-border" checked={selected.has(row.original.id)} onChange={() => toggle(row.original.id)} onClick={(e) => e.stopPropagation()} aria-label={`Выбрать: ${row.original.fullName}`} />
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
    { accessorKey: 'location', header: 'Место работы', cell: ({ getValue }) => (getValue() as string) || '—' },
    { accessorKey: 'hiredAt', header: 'Нанят', cell: ({ getValue }) => { const v = getValue() as string; return v ? formatHiredAgo(v) : '—'; } },
    {
      accessorKey: 'accessStatus',
      header: 'Доступ',
      cell: ({ getValue }) => <StatusPill label={getValue() === 'active' ? 'Активен' : 'Неактивен'} />,
    },
    {
      accessorKey: 'contractStatus',
      header: 'Статус контракта',
      cell: ({ getValue }) =>
        getValue() === 'completed'
          ? <StatusPill label="Подписан" variant="success" dot />
          : <StatusPill label="Не подписан" variant="warning" dot />,
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
        toolbar={{
          searchKey: SEARCH_KEY,
          searchPlaceholder: 'Поиск сотрудника...',
          moreActions: (
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-fx-lg border border-border bg-white hover:bg-sidebar-hover text-fx-sm"
                onClick={onExportAll}
                disabled={exportingAll}
              >
                {exportingAll ? 'Выгружаем…' : 'Экспорт'}
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
        search={search}
        onSearchChange={setSearch}
        loading={isLoading}
        error={isError ? `Не удалось загрузить сотрудников: ${getErrorDetail(error, 'ошибка сервера')}` : undefined}
      />

      {confirmDismiss && (
        <HrConfirm
          title={`Уволить выбранных (${selected.size})?`}
          subtitle="Сотрудники станут неактивными, данные не удаляются."
          danger={selected.size > visibleIds.filter((id) => selected.has(id)).length
            ? 'Среди выбранных есть сотрудники, скрытые текущим поиском.'
            : undefined}
          confirmLabel="Уволить"
          busy={dismissM.isPending}
          onCancel={() => setConfirmDismiss(false)}
          onConfirm={() => dismissM.mutate()}
        />
      )}

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
        <div className="fx-modal-overlay" {...backdropClose(() => setMoveOpen(false))}>
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
