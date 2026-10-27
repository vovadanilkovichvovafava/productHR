import { useState } from 'react';
import api from '@/services/api/client';

/**
 * DEV-ONLY переключатель аккаунтов для локального тестирования.
 * Рендерится только при import.meta.env.DEV (в прод-сборке его нет).
 * Клик по аккаунту логинит под ним (POST /auth/login) и перезагружает страницу —
 * чтобы не листать диалог в поисках логинов/паролей.
 *
 * Пароль у всех сид-аккаунтов локалки — Demo1234!.
 */
const DEV_ACCOUNTS: { email: string; label: string; pw: string }[] = [
  { email: 'admin@mstech.io', label: 'Super Admin (owner)', pw: 'Demo1234!' },
  { email: 'nastya@mstech.io', label: 'Настя (org admin)', pw: 'Demo1234!' },
  { email: 'maria@mstech.io', label: 'Мария (org admin)', pw: 'Demo1234!' },
  { email: 'recruiter.test@example.com', label: 'Тестовый Рекрутёр (hr)', pw: 'Demo1234!' },
  { email: 'recruiter2.test@example.com', label: 'Пётр (hr)', pw: 'Demo1234!' },
  { email: 'observer.test@example.com', label: 'Наблюдатель (readonly)', pw: 'Demo1234!' },
];

export default function DevAccountSwitcher() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  if (!import.meta.env.DEV) return null;

  const switchTo = async (email: string, pw: string) => {
    setBusy(email);
    try {
      await api.post('/auth/login', { email, password: pw });
      // Полная перезагрузка — приложение переинициализируется под новой сессией.
      window.location.href = '/';
    } catch {
      setBusy(null);
      // eslint-disable-next-line no-alert
      alert('Не удалось войти как ' + email + ' (пароль Demo1234!?)');
    }
  };

  return (
    <div style={{ position: 'fixed', bottom: 12, right: 12, zIndex: 999999 }}>
      {open && (
        <div
          style={{
            background: '#1b1b1f',
            color: '#fff',
            borderRadius: 10,
            padding: 8,
            marginBottom: 8,
            boxShadow: '0 6px 24px rgba(0,0,0,.45)',
            minWidth: 240,
            border: '1px solid #34343c',
          }}
        >
          <div style={{ fontSize: 11, opacity: 0.55, padding: '2px 6px 6px' }}>
            DEV · войти как
          </div>
          {DEV_ACCOUNTS.map((a) => (
            <button
              key={a.email}
              onClick={() => switchTo(a.email, a.pw)}
              disabled={!!busy}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '7px 8px',
                borderRadius: 7,
                background: busy === a.email ? '#3a3a44' : 'transparent',
                color: '#fff',
                border: 'none',
                cursor: busy ? 'default' : 'pointer',
                fontSize: 13,
              }}
              onMouseEnter={(e) => {
                if (!busy) (e.currentTarget as HTMLButtonElement).style.background = '#2a2a31';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background =
                  busy === a.email ? '#3a3a44' : 'transparent';
              }}
            >
              {busy === a.email ? '⏳ ' : ''}
              {a.label}
              <span style={{ display: 'block', fontSize: 10, opacity: 0.5 }}>{a.email}</span>
            </button>
          ))}
        </div>
      )}
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          background: '#6d5efc',
          color: '#fff',
          border: 'none',
          borderRadius: 20,
          padding: '8px 14px',
          fontSize: 12,
          fontWeight: 600,
          cursor: 'pointer',
          boxShadow: '0 3px 14px rgba(0,0,0,.35)',
        }}
        title="DEV-переключатель аккаунтов (только локалка)"
      >
        🔀 Аккаунт
      </button>
    </div>
  );
}
