import { useRef } from 'react';
import { User } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ProfileTemplate from '@/factorial/templates/ProfileTemplate';
import { buildProfileTabs } from '@/factorial/lib/routes';
import { useProfileEmployee } from '@/factorial/lib/useProfileEmployee';
import {
  listEmployeeDocuments,
  uploadEmployeeDocument,
  downloadEmployeeDocument,
  deleteEmployeeDocument,
} from '@/factorial/api/employees';

const TITLE_ICON = (
  <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
    <User className="w-5 h-5 text-pink-600" />
  </div>
);

export default function ProfileDocumentsPage() {
  const { data: me, byId, employeeId } = useProfileEmployee();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const empId = byId ? employeeId : me?.id;
  const base = byId ? `/factorial/employees/${employeeId}` : '/factorial/profile';

  const { data: docs = [] } = useQuery({
    queryKey: ['fx', 'docs', empId],
    queryFn: () => listEmployeeDocuments(empId!),
    enabled: !!empId,
  });
  const up = useMutation({
    mutationFn: (f: File) => uploadEmployeeDocument(empId!, f),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fx', 'docs', empId] }),
  });
  const del = useMutation({
    mutationFn: (docId: number) => deleteEmployeeDocument(empId!, docId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fx', 'docs', empId] }),
  });
  const download = async (docId: number) => {
    const d = await downloadEmployeeDocument(empId!, docId);
    const a = document.createElement('a');
    a.href = `data:${d.content_type || 'application/octet-stream'};base64,${d.data_base64}`;
    a.download = d.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <ProfileTemplate
      breadcrumb={byId ? [{ label: 'Сотрудники', href: '/factorial/employees' }, { label: me?.user_name || 'Документы' }] : [{ label: 'Профиль' }, { label: 'Документы' }]}
      titleIcon={TITLE_ICON}
      title={byId ? (me?.user_name || 'Профиль') : 'Профиль'}
      subNav={buildProfileTabs(base)}
      leftColumn={
        <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Документы</h2>
            <button
              type="button"
              className="px-3 py-1.5 text-fx-xs font-medium border border-card-border-soft rounded-fx-lg hover:bg-sidebar-hover"
              onClick={() => fileRef.current?.click()}
            >
              Загрузить файл
            </button>
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) up.mutate(f);
                e.currentTarget.value = '';
              }}
            />
          </div>
          {docs.length === 0 ? (
            <p className="text-fx-sm text-text-muted">Файлов пока нет.</p>
          ) : (
            <ul className="divide-y divide-card-border-soft">
              {docs.map((d) => (
                <li key={d.id} className="flex items-center justify-between py-2 text-fx-sm">
                  <span className="truncate">{d.filename}</span>
                  <span className="flex items-center gap-3 shrink-0">
                    <button type="button" className="text-pink-600 hover:underline" onClick={() => download(d.id)}>Скачать</button>
                    <button type="button" className="text-text-muted hover:text-red-600" onClick={() => { if (confirm('Удалить файл?')) del.mutate(d.id); }}>Удалить</button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </article>
      }
      rightDetails={[{ label: 'Электронная почта', value: <span>{me?.user_email || '—'}</span> }]}
    />
  );
}
