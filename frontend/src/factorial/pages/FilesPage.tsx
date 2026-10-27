import { useState } from 'react';
import { Folder } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import TableTemplate from '@/factorial/templates/TableTemplate';
import TemplateEditorModal from '@/factorial/components/TemplateEditorModal';
import { listTemplates, generateDoc } from '@/factorial/api/documents';
import { listEmployees } from '@/factorial/api/employees';
import type { DocTemplate } from '@/factorial/api/types';
import { formatDateRu } from '@/factorial/lib/formatDate';

/** Модалка генерации документа из шаблона для выбранного сотрудника. */
function GenerateModal({ template, onClose }: { template: DocTemplate; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: emps = [] } = useQuery({ queryKey: ['fx', 'employees', 'pick'], queryFn: () => listEmployees(true) });
  const [empId, setEmpId] = useState<number | ''>('');
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState('');

  const m = useMutation({
    mutationFn: () => generateDoc(template.id, Number(empId)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['fx'] }); setOk(true); },
    onError: () => setErr('Не удалось сгенерировать документ (нужны права администратора).'),
  });

  return (
    <div className="fx-modal-overlay" onClick={onClose}>
      <div className="fx-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Сгенерировать: {template.name}</h3>
        {ok ? (
          <>
            <div className="fx-sub">Документ создан и отправлен сотруднику на подпись (раздел «Мои документы»).</div>
            <div className="fx-modal-actions">
              <button className="fx-btn fx-btn--primary" onClick={onClose}>Готово</button>
            </div>
          </>
        ) : (
          <>
            <div className="fx-field">
              <label>Сотрудник</label>
              <select className="fx-select" value={empId} onChange={(e) => setEmpId(e.target.value ? Number(e.target.value) : '')}>
                <option value="">— выберите сотрудника —</option>
                {emps.map((e) => (
                  <option key={e.id} value={e.id}>{e.user_name || `#${e.id}`}</option>
                ))}
              </select>
            </div>
            {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}
            <div className="fx-modal-actions">
              <button className="fx-btn fx-btn--secondary" onClick={onClose}>Отмена</button>
              <button className="fx-btn fx-btn--primary" disabled={!empId || m.isPending} onClick={() => m.mutate()}>
                {m.isPending ? 'Генерация…' : 'Сгенерировать'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function FilesPage() {
  // Реальные шаблоны документов из бэкенда Энцеладуса.
  const { data: templates = [] } = useQuery({ queryKey: ['fx', 'templates'], queryFn: listTemplates });
  const [editing, setEditing] = useState<DocTemplate | null | undefined>(undefined); // undefined=закрыто, null=новый, объект=правка
  const [genTpl, setGenTpl] = useState<DocTemplate | null>(null);

  const columns: ColumnDef<DocTemplate, any>[] = [
    { accessorKey: 'name', header: 'Название' },
    { id: 'vars', header: 'Переменные', cell: ({ row }) => (row.original.variables || []).join(', ') || '—' },
    { accessorKey: 'created_at', header: 'Создан', cell: ({ getValue }) => { const v = getValue() as string; return v ? formatDateRu(v) : '—'; } },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={() => setGenTpl(row.original)} className="px-3 py-1.5 rounded-fx-lg text-fx-sm font-medium bg-primary text-white hover:bg-primary-hover">Сгенерировать</button>
          <button type="button" onClick={() => setEditing(row.original)} className="px-3 py-1.5 rounded-fx-lg text-fx-sm font-medium border border-border bg-white hover:bg-sidebar-hover">Изменить</button>
        </div>
      ),
      size: 220,
    },
  ];

  return (
    <>
      <TableTemplate
        breadcrumb={[{ label: 'Документы' }]}
        titleIcon={
          <div className="w-9 h-9 rounded-fx-lg bg-blue-100 flex items-center justify-center">
            <Folder className="w-5 h-5 text-blue-600" />
          </div>
        }
        title="Документы"
        secondaryNav={[{ label: 'Шаблоны', href: '/factorial/files', end: true }]}
        toolbar={{ searchKey: 'name', searchPlaceholder: 'Поиск шаблона...', primaryCta: { label: 'Создать шаблон', onClick: () => setEditing(null) } }}
        columns={columns}
        data={templates}
        emptyState={{ emoji: '📑', heading: 'Шаблонов пока нет', description: 'Создайте шаблон документа с переменными ({{name}}, {{position}}…) — затем генерируйте его для сотрудников на подпись.' }}
      />
      {editing !== undefined && <TemplateEditorModal template={editing ?? null} onClose={() => setEditing(undefined)} />}
      {genTpl && <GenerateModal template={genTpl} onClose={() => setGenTpl(null)} />}
    </>
  );
}
