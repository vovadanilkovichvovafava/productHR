import { useState, FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { createInvitation } from '../api/invitations';
import type { Invitation } from '../api/types';
import { getErrorDetail } from '@/utils';

export default function InviteEmployeeModal({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [link, setLink] = useState('');
  const [err, setErr] = useState('');

  const m = useMutation({
    mutationFn: () => createInvitation({ email: email || undefined, name: name || undefined, org_role: 'member' }),
    onSuccess: (inv: Invitation) => setLink(window.location.origin + inv.invitation_url),
    onError: (e: unknown) => {
      const d = getErrorDetail(e, '');
      setErr(/already a member/i.test(d)
        ? 'Этот email уже зарегистрирован в организации — введите другой или оставьте поле пустым.'
        : (d || 'Не удалось создать приглашение.'));
    },
  });

  const submit = (e: FormEvent) => { e.preventDefault(); setErr(''); m.mutate(); };
  const copy = () => { navigator.clipboard?.writeText(link); };

  return (
    <div className="fx-modal-overlay" onClick={onClose}>
      <form className="fx-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Пригласить сотрудника</h3>
        {!link ? (
          <>
            <div className="fx-field"><label>Имя</label><input className="fx-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Иван Иванов" /></div>
            <div className="fx-field"><label>Email</label><input className="fx-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ivan@example.com" /></div>
            <div className="fx-sub">Сотрудник перейдёт по ссылке, задаст пароль и попадёт в свой личный кабинет.</div>
            {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}
            <div className="fx-modal-actions">
              <button type="button" className="fx-btn fx-btn--secondary" onClick={onClose}>Отмена</button>
              <button type="submit" className="fx-btn fx-btn--primary" disabled={m.isPending}>{m.isPending ? 'Создание…' : 'Создать ссылку'}</button>
            </div>
          </>
        ) : (
          <>
            <div className="fx-sub">Ссылка-приглашение готова — отправьте её сотруднику (веб или Telegram):</div>
            <div className="fx-field" style={{ marginTop: 8 }}>
              <input className="fx-input" readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
            </div>
            <div className="fx-modal-actions">
              <button type="button" className="fx-btn fx-btn--secondary" onClick={copy}>Копировать</button>
              <button type="button" className="fx-btn fx-btn--primary" onClick={onClose}>Готово</button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}
