import { useRef, useState, ChangeEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { uploadMyPassport, getMyPassport, getEmployeePassport } from '../api/employees';
import { openBase64File, canViewInline } from '../lib/fileOpen';
import { getErrorDetail } from '@/utils';
import { FxCard, FxButton, FxPill } from './ui';

/**
 * Скан паспорта.
 *
 * Без `employeeId` — свой паспорт (личный кабинет): просмотр и загрузка.
 * С `employeeId` — HR смотрит карточку сотрудника: только статус и
 * «Просмотреть»/«Скачать» ЕГО скана. До 27.10.2026 карточка всегда ходила в
 * `/employees/me/passport`: HR в карточке сотрудника видел СВОЙ паспорт, а
 * «Загрузить» заменял скан самого HR.
 */
export default function PassportCard({
  passport,
  employeeId,
}: {
  passport?: { filename?: string; uploaded_at?: string; content_type?: string };
  employeeId?: number;
}) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const foreign = employeeId !== undefined;

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const dataUrl: string = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result as string);
        r.onerror = rej;
        r.readAsDataURL(file);
      });
      const base64 = dataUrl.split(',')[1] || '';
      return uploadMyPassport(file.name, file.type || 'application/octet-stream', base64);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fx', 'me'] }),
    onError: (e) => setErr(getErrorDetail(e, 'Не удалось загрузить файл.')),
  });

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (f) { setErr(''); upload.mutate(f); }
  };

  const open = async (download: boolean) => {
    setErr('');
    setBusy(true);
    try {
      const d = foreign ? await getEmployeePassport(employeeId!) : await getMyPassport();
      openBase64File(d, { download, fallbackName: 'passport' });
    } catch (e) {
      setErr(getErrorDetail(e, 'Не удалось открыть файл.'));
    } finally {
      setBusy(false);
    }
  };

  // Тип файла известен заранее не всегда: тогда «Просмотреть» сам решит
  // (картинка/PDF — во вкладке, прочее — скачается).
  const viewable = !passport?.content_type || canViewInline(passport.content_type);

  return (
    <FxCard title="Паспорт" action={passport?.filename ? <FxPill tone="green" dot>Загружен</FxPill> : <FxPill tone="amber">Не загружен</FxPill>}>
      <div className="fx-sub">
        {foreign
          ? 'Скан видят сотрудник, HR и его непосредственный руководитель. Загружает его сам сотрудник.'
          : 'Скан видите вы, HR и ваш непосредственный руководитель.'}
      </div>
      {passport?.filename && (
        <div className="fx-doc" style={{ marginTop: 8 }}>
          <span className="fx-doc-title">{passport.filename}</span>
          {viewable && (
            <button className="fx-btn fx-btn--ghost" onClick={() => open(false)} disabled={busy}>Просмотреть</button>
          )}
          <button className="fx-btn fx-btn--ghost" onClick={() => open(true)} disabled={busy}>Скачать</button>
        </div>
      )}
      {!foreign && (
        <>
          <input ref={fileRef} type="file" accept="image/*,.pdf" style={{ display: 'none' }} onChange={onPick} />
          <div style={{ marginTop: 12 }}>
            <FxButton variant="secondary" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
              {upload.isPending ? 'Загрузка…' : passport?.filename ? 'Заменить файл' : 'Загрузить паспорт'}
            </FxButton>
          </div>
        </>
      )}
      {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}
    </FxCard>
  );
}
