import { useRef, useState } from 'react';
import toast from 'react-hot-toast';
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
import { openBase64File } from '@/factorial/lib/fileOpen';
import { useAuthStore } from '@/stores/authStore';
import HrConfirm from '@/components/hr/HrConfirm';
import { getErrorDetail } from '@/utils';

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

  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'superadmin' || user?.org_role === 'owner' || user?.org_role === 'admin';
  const [toDelete, setToDelete] = useState<{ id: number; filename: string } | null>(null);

  const { data: docs = [], isError, error } = useQuery({
    queryKey: ['fx', 'docs', empId],
    queryFn: () => listEmployeeDocuments(empId!),
    enabled: !!empId,
  });
  const up = useMutation({
    mutationFn: (f: File) => uploadEmployeeDocument(empId!, f),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fx', 'docs', empId] }),
    onError: (e) => toast.error(getErrorDetail(e, 'Не удалось загрузить файл')),
  });
  const del = useMutation({
    mutationFn: (docId: number) => deleteEmployeeDocument(empId!, docId),
    onSuccess: () => { setToDelete(null); qc.invalidateQueries({ queryKey: ['fx', 'docs', empId] }); },
    onError: (e) => { setToDelete(null); toast.error(getErrorDetail(e, 'Не удалось удалить файл')); },
  });
  const download = async (docId: number) => {
    try {
      const d = await downloadEmployeeDocument(empId!, docId);
      openBase64File(d, { download: true, fallbackName: 'document' });
    } catch (e) {
      toast.error(getErrorDetail(e, 'Не удалось скачать файл'));
    }
  };
  // Сотрудник удаляет только загруженное им самим, админ HR — любое (так же
  // решает сервер). Старый ответ без uploaded_by — кнопку оставляем, отказ
  // сервера покажет тост.
  const canDelete = (d: { uploaded_by?: number | null }) =>
    isAdmin || d.uploaded_by === undefined || (user != null && d.uploaded_by === user.id);

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
          {isError ? (
            <p className="text-fx-sm" style={{ color: '#B91C1C' }}>
              Не удалось загрузить список: {getErrorDetail(error, 'ошибка сервера')}
            </p>
          ) : docs.length === 0 ? (
            <p className="text-fx-sm text-text-muted">Файлов пока нет.</p>
          ) : (
            <ul className="divide-y divide-card-border-soft">
              {docs.map((d) => (
                <li key={d.id} className="flex items-center justify-between py-2 text-fx-sm">
                  <span className="truncate">{d.filename}</span>
                  <span className="flex items-center gap-3 shrink-0">
                    <button type="button" className="text-pink-600 hover:underline" onClick={() => download(d.id)}>Скачать</button>
                    {canDelete(d as { uploaded_by?: number | null }) && (
                      <button type="button" className="text-text-muted hover:text-red-600" onClick={() => setToDelete({ id: d.id, filename: d.filename })}>Удалить</button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {up.isPending && <p className="text-fx-xs text-text-muted mt-2">Загрузка файла…</p>}
          {toDelete && (
            <HrConfirm
              title="Удалить файл?"
              subtitle={toDelete.filename}
              danger="Файл удалится без возможности восстановления."
              confirmLabel="Удалить"
              busy={del.isPending}
              onCancel={() => setToDelete(null)}
              onConfirm={() => del.mutate(toDelete.id)}
            />
          )}
        </article>
      }
      rightDetails={[{ label: 'Электронная почта', value: <span>{me?.user_email || '—'}</span> }]}
    />
  );
}
