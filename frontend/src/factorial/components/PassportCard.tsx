import { useRef, useState, ChangeEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { uploadMyPassport, getMyPassport } from '../api/employees';
import { FxCard, FxButton, FxPill } from './ui';

export default function PassportCard({ passport }: { passport?: { filename?: string; uploaded_at?: string } }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState('');

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
    onError: () => setErr('Не удалось загрузить файл.'),
  });

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) { setErr(''); upload.mutate(f); }
  };

  const view = async () => {
    setErr('');
    try {
      const d = await getMyPassport();
      const w = window.open();
      if (!w) return;
      if ((d.content_type || '').startsWith('image/')) {
        w.document.write(`<title>${d.filename || 'Паспорт'}</title><img src="data:${d.content_type};base64,${d.data_base64}" style="max-width:100%" />`);
      } else {
        const a = w.document.createElement('a');
        a.href = `data:${d.content_type};base64,${d.data_base64}`;
        a.download = d.filename || 'passport';
        a.textContent = 'Скачать ' + (d.filename || 'файл');
        w.document.body.appendChild(a);
      }
    } catch {
      setErr('Не удалось открыть файл.');
    }
  };

  return (
    <FxCard title="Паспорт" action={passport?.filename ? <FxPill tone="green" dot>Загружен</FxPill> : <FxPill tone="amber">Не загружен</FxPill>}>
      <div className="fx-sub">Файл шифруется и доступен только вам.</div>
      {passport?.filename && (
        <div className="fx-doc" style={{ marginTop: 8 }}>
          <span className="fx-doc-title">{passport.filename}</span>
          <button className="fx-btn fx-btn--ghost" onClick={view}>Просмотреть</button>
        </div>
      )}
      <input ref={fileRef} type="file" accept="image/*,.pdf" style={{ display: 'none' }} onChange={onPick} />
      <div style={{ marginTop: 12 }}>
        <FxButton variant="secondary" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
          {upload.isPending ? 'Загрузка…' : passport?.filename ? 'Заменить файл' : 'Загрузить паспорт'}
        </FxButton>
      </div>
      {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}
    </FxCard>
  );
}
