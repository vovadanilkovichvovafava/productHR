import { useState } from 'react';
import { AtSign, Loader2, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { setEmailDomain, updateMemberEmail, type EmailDomainMember } from '@/services/api/auth';
import { getErrorDetail } from '@/utils';

// «Вход только с корпоративной почтой» (Мария, 09.11.2026). Включает админ
// организации. До сохранения сервер считает, кто потеряет вход (dry_run), и
// список показывается здесь — молча запереть коллег нельзя. Себя запереть
// сервер не даст. Суперадминов правило не касается.

export function emailFitsDomains(email: string, domains: string[], exceptions: string[] = []): boolean {
  if (!domains.length) return true;
  const normalized = (email || '').trim().toLowerCase();
  if (exceptions.includes(normalized)) return true;
  const domain = normalized.split('@').pop() || '';
  return domains.includes(domain);
}

const at = (domains: string[]) => domains.map((d) => `@${d}`).join(', ');

function OutsideList({ people, title }: { people: EmailDomainMember[]; title: string }) {
  if (!people.length) return null;
  return (
    <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
      <p className="text-sm text-amber-300 flex items-center gap-2">
        <AlertTriangle size={14} className="shrink-0" />
        {title}
      </p>
      <ul className="mt-2 space-y-1">
        {people.map((p) => (
          <li key={p.user_id} className="text-sm text-white/70">
            {p.name} <span className="text-white/40">· {p.email}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EmailDomainCard({
  domains,
  exceptions = [],
  outside,
  onChanged,
}: {
  domains: string[];
  exceptions?: string[];
  outside: EmailDomainMember[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState('');
  // Исключения по адресу (тестовые аккаунты, 09.11.2026): входят вне домена,
  // роль у них прежняя — суперадмином их делать не нужно.
  const [extra, setExtra] = useState('');
  const [preview, setPreview] = useState<{ domains: string[]; outside: EmailDomainMember[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const enabled = domains.length > 0;

  const startEdit = () => {
    setValue(domains.join(', '));
    setExtra(exceptions.join(', '));
    setPreview(null);
    setError(null);
    setEditing(true);
  };

  const check = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await setEmailDomain(value, true, extra);
      if (!res.domains.length) {
        setError('Впишите домен, например agency-mst.com');
        setPreview(null);
      } else {
        setPreview({ domains: res.domains, outside: res.outside });
      }
    } catch (e) {
      setPreview(null);
      setError(getErrorDetail(e, 'Не удалось проверить'));
    } finally {
      setBusy(false);
    }
  };

  const save = async (raw: string, rawExtra?: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await setEmailDomain(raw, false, rawExtra);
      toast.success(res.domains.length ? `Вход только с почтой ${at(res.domains)}` : 'Ограничение снято');
      setEditing(false);
      setPreview(null);
      onChanged();
    } catch (e) {
      setError(getErrorDetail(e, 'Не удалось сохранить'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="glass-light rounded-xl p-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <h3 className="text-white font-medium flex items-center gap-2">
            <AtSign size={16} className="text-cyan-400" />
            Вход только с корпоративной почтой
          </h3>
          <p className="text-sm text-white/40 mt-1">
            {enabled
              ? <>
                  Включено: войти могут только адреса <span className="text-white/80">{at(domains)}</span>
                  {exceptions.length > 0 && <> и исключения: <span className="text-white/80">{exceptions.join(', ')}</span></>}
                  . Администраторов платформы это не касается.
                </>
              : 'Выключено: войти можно с любой почтой.'}
          </p>
        </div>
        {!editing && (
          <div className="flex gap-2">
            <button
              onClick={startEdit}
              className="px-3 py-1.5 rounded-lg text-sm bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30"
            >
              {enabled ? 'Изменить' : 'Включить'}
            </button>
            {enabled && (
              <button
                onClick={() => save('')}
                disabled={busy}
                className="px-3 py-1.5 rounded-lg text-sm glass-light text-white/60 hover:bg-white/10 disabled:opacity-50"
              >
                Снять
              </button>
            )}
          </div>
        )}
      </div>

      {!editing && enabled && (
        <OutsideList
          people={outside}
          title={`Не могут войти — почта не на ${at(domains)}. Смените им почту — «изменить» рядом с адресом в списке ниже:`}
        />
      )}

      {editing && (
        <div className="mt-3 space-y-3">
          <div className="flex gap-2 flex-wrap">
            <input
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                setPreview(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  check();
                }
              }}
              placeholder="agency-mst.com"
              autoFocus
              className="flex-1 min-w-[200px] px-3 py-2 glass-light rounded-lg text-white text-sm"
            />
            <button
              onClick={check}
              disabled={busy || !value.trim()}
              className="px-3 py-2 rounded-lg text-sm bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-50 flex items-center gap-2"
            >
              {busy && !preview && <Loader2 size={14} className="animate-spin" />}
              Проверить
            </button>
            <button
              onClick={() => setEditing(false)}
              className="px-3 py-2 rounded-lg text-sm glass-light text-white/60 hover:bg-white/10"
            >
              Отмена
            </button>
          </div>

          <div>
            <label className="block text-xs text-white/40 mb-1">
              Исключения — адреса, которым можно входить с другой почтой (например, тестовый аккаунт)
            </label>
            <input
              value={extra}
              onChange={(e) => {
                setExtra(e.target.value);
                setPreview(null);
              }}
              placeholder="test@gmail.com, другой@mail.ru"
              className="w-full px-3 py-2 glass-light rounded-lg text-white text-sm"
            />
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          {preview && (
            <div>
              {preview.outside.length ? (
                <OutsideList
                  people={preview.outside}
                  title={`После сохранения не смогут войти (${preview.outside.length}) — их почта не на ${at(preview.domains)}:`}
                />
              ) : (
                <p className="text-sm text-green-400">
                  У всех участников почта {at(preview.domains)} — никто не потеряет вход.
                </p>
              )}
              <button
                onClick={() => save(preview.domains.join(','), extra)}
                disabled={busy}
                className={clsx(
                  'mt-3 px-4 py-2 rounded-lg text-sm text-white flex items-center gap-2 disabled:opacity-50',
                  preview.outside.length ? 'bg-amber-600 hover:bg-amber-700' : 'bg-cyan-500 hover:bg-cyan-600',
                )}
              >
                {busy && <Loader2 size={14} className="animate-spin" />}
                {preview.outside.length ? 'Всё равно включить' : 'Включить'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Почта участника в списке: метка «не корпоративная» и правка карандашом.
export function MemberEmail({
  userId,
  email,
  domains,
  exceptions = [],
  canEdit,
  onChanged,
}: {
  userId: number;
  email: string;
  domains: string[];
  exceptions?: string[];
  canEdit: boolean;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(email);
  const [busy, setBusy] = useState(false);
  const fits = emailFitsDomains(email, domains, exceptions);

  const save = async () => {
    const next = value.trim();
    if (!next || next.toLowerCase() === email.toLowerCase()) {
      setEditing(false);
      return;
    }
    setBusy(true);
    try {
      const res = await updateMemberEmail(userId, next);
      toast.success(`Почта изменена: ${res.email}. Пароль прежний.`);
      setEditing(false);
      onChanged();
    } catch (e) {
      toast.error(getErrorDetail(e, 'Не удалось сменить почту'));
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <div className="flex items-center gap-2 mt-1">
        <input
          type="email"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') save();
            if (e.key === 'Escape') setEditing(false);
          }}
          autoFocus
          className="px-2 py-1 glass-light rounded-lg text-white text-sm min-w-0 w-64"
        />
        <button
          onClick={save}
          disabled={busy}
          className="px-2 py-1 rounded-lg text-xs bg-cyan-500 text-white hover:bg-cyan-600 disabled:opacity-50"
        >
          Сохранить
        </button>
        <button onClick={() => setEditing(false)} className="px-2 py-1 rounded-lg text-xs text-white/50 hover:text-white/80">
          Отмена
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <p className="text-sm text-white/40">{email}</p>
      {!fits && (
        <span
          className="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300"
          title={`Вход разрешён только с почтой ${at(domains)}`}
        >
          не {at(domains)} — войти не сможет
        </span>
      )}
      {canEdit && (
        <button
          onClick={() => {
            setValue(email);
            setEditing(true);
          }}
          className="text-xs text-white/40 hover:text-cyan-400"
          title="Сменить почту (логин). Пароль останется прежним."
        >
          изменить
        </button>
      )}
    </div>
  );
}
