import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { Copy, Inbox, Link2, Search, X } from 'lucide-react';
import { AnketaResponses } from '@/features/forms/AnketaResponses';
import { FormsPageTabs } from '@/features/forms/FormsPageTabs';
import HrConfirm from '@/components/hr/HrConfirm';
import { useLiveSearchParams } from '@/hooks/useLiveSearchParams';
import { useDebounce } from '@/hooks/useDebounce';
import { useAuthStore } from '@/stores/authStore';
import { copyOrShowLink } from '@/utils/copyOrShowLink';
import { backdropClose } from '@/utils/backdropClose';
import {
  attachFormAnswer, getFormAnswer, getFormAnswers,
  type FormAnswerItem, type FormAnswersList, type FormAnswerView,
} from '@/services/api/formAnswers';
import { searchCandidates, type CandidateItem } from '@/services/api/candidates';
import {
  PERIODS, STATUS_TABS, formatWhen, openKey, parseAnswerFilters, sendErrorText, statusChip,
  type ChipTone,
} from '@/utils/formAnswers';

/**
 * «Анкеты → Ответы» (06.11.2026): все отправленные анкеты и ответы без
 * кандидата одним списком. Владелец: «на случай, если кандидат потеряется или
 * анкета от него не дойдёт и не отобразится». Раньше ответ был виден только в
 * карточке кандидата. Сервер — routes/form_answers.py.
 *
 * Выбранное руками (вкладка статуса, анкета, кто отправил, период, открытый
 * ответ) лежит в адресе — F5 оставляет на месте. Поиск — нет (не должен тихо
 * висеть, как на «Все кандидаты»).
 */

const CHIP: Record<ChipTone, string> = {
  ok: 'bg-green-500/15 text-green-600',
  warn: 'bg-amber-500/15 text-amber-700',
  muted: 'bg-dark-700 text-dark-300',
  bad: 'bg-red-500/15 text-red-600',
};

const linkOf = (token: string) => `${window.location.origin}/form/${token}`;

export default function FormAnswersPage() {
  const [params, setParams] = useLiveSearchParams();
  const filters = useMemo(() => parseAnswerFilters(params), [params]);
  const observer = !!useAuthStore((s) => s.user?.is_readonly);

  const [search, setSearch] = useState('');
  const [debounced] = useDebounce(search, 300);
  const [data, setData] = useState<FormAnswersList | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const reqRef = useRef(0);

  const load = useCallback(async () => {
    const req = ++reqRef.current;
    setFailed(false);
    try {
      const res = await getFormAnswers({
        status: filters.status === 'all' ? undefined : filters.status,
        form_id: filters.formId ?? undefined,
        sent_by: filters.sentBy ?? undefined,
        days: filters.days ?? undefined,
        q: debounced.trim() || undefined,
      });
      if (req === reqRef.current) setData(res); // опоздавший ответ старого фильтра не рисуем
    } catch {
      if (req === reqRef.current) setFailed(true);
    } finally {
      if (req === reqRef.current) setLoading(false);
    }
  }, [filters.status, filters.formId, filters.sentBy, filters.days, debounced]);

  useEffect(() => { void load(); }, [load]);

  const setParam = (key: string, value: string | null) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value); else next.delete(key);
      return next;
    }, { replace: key !== 'open' });

  const items = data?.items ?? [];
  const counts = data?.counts;

  return (
    <div className="p-6 max-w-[1248px] mx-auto">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mb-2">
        <h1 className="text-2xl font-bold text-white">Анкеты</h1>
        <FormsPageTabs />
      </div>
      <p className="text-dark-400 text-sm mb-5">
        Все отправленные анкеты: что заполнено, что открыто и не отправлено, и ответы, у которых нет карточки кандидата.
      </p>

      <div className="flex flex-wrap gap-2 mb-3" role="tablist" aria-label="Статус анкеты">
        {STATUS_TABS.map((t) => {
          const active = filters.status === t.key;
          const n = counts?.[t.key];
          const alarm = t.key === 'orphan' && !!n;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setParam('status', t.key === 'all' ? null : t.key)}
              className={clsx(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm transition-colors',
                active ? 'border-white text-white font-semibold' : 'border-dark-700 text-dark-300 hover:border-dark-500',
                alarm && !active && 'border-red-300 bg-red-500/10 text-red-600',
                alarm && active && 'text-red-600',
              )}
            >
              {t.label}
              <span className="tabular-nums opacity-70">{n ?? '…'}</span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        <label className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-dark-400" />
          <input
            id="form-answers-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Escape') setSearch(''); }}
            placeholder="Поиск по кандидату, анкете или тому, что он вписал"
            className="w-full pl-9 pr-8 py-2 rounded-xl bg-dark-800 border border-dark-700 text-sm text-white placeholder:text-dark-400 focus:outline-none focus:border-accent-500"
          />
          {search && (
            <button type="button" aria-label="Очистить поиск" onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-dark-400 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          )}
        </label>
        <select
          id="form-answers-form"
          value={filters.formId ?? ''}
          onChange={(e) => setParam('form', e.target.value || null)}
          className="px-3 py-2 rounded-xl bg-dark-800 border border-dark-700 text-sm text-white max-w-[260px]"
          aria-label="Анкета"
        >
          <option value="">Анкета: все</option>
          {(data?.forms ?? []).map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
        </select>
        <select
          id="form-answers-sender"
          value={filters.sentBy ?? ''}
          onChange={(e) => setParam('sender', e.target.value || null)}
          className="px-3 py-2 rounded-xl bg-dark-800 border border-dark-700 text-sm text-white"
          aria-label="Кто отправил"
        >
          <option value="">Отправил: все</option>
          {(data?.senders ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <select
          id="form-answers-period"
          value={filters.days ?? ''}
          onChange={(e) => setParam('days', e.target.value || null)}
          className="px-3 py-2 rounded-xl bg-dark-800 border border-dark-700 text-sm text-white"
          aria-label="Период"
        >
          {PERIODS.map((p) => <option key={p.label} value={p.days ?? ''}>{p.label}</option>)}
        </select>
      </div>

      {loading && !data ? (
        <div className="py-16 flex justify-center">
          <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : failed && !data ? (
        <div className="py-16 text-center text-dark-400">
          Не удалось загрузить анкеты.{' '}
          <button type="button" className="text-accent-500 hover:underline" onClick={() => void load()}>Повторить</button>
        </div>
      ) : items.length === 0 ? (
        <div className="py-16 text-center text-dark-400">
          <Inbox className="w-8 h-8 mx-auto mb-3 opacity-50" />
          {search || filters.formId || filters.sentBy || filters.days || filters.status !== 'all'
            ? 'По этим условиям анкет нет'
            : 'Анкеты ещё не отправлялись'}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-dark-700 bg-dark-800">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-dark-400 border-b border-dark-700">
                <th className="px-4 py-2.5 font-semibold">Кандидат</th>
                <th className="px-4 py-2.5 font-semibold">Анкета</th>
                <th className="px-4 py-2.5 font-semibold">Отправил</th>
                <th className="px-4 py-2.5 font-semibold">Отправлена</th>
                <th className="px-4 py-2.5 font-semibold">Статус</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <AnswerRow
                  key={openKey(item)}
                  item={item}
                  active={!!filters.open && openKey(filters.open) === openKey(item)}
                  onOpen={() => setParam('open', openKey(item))}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {filters.open && (
        <AnswerDrawer
          kind={filters.open.kind}
          id={filters.open.id}
          canAttach={!!data?.can_attach && !observer}
          onClose={() => setParam('open', null)}
          onAttached={() => { setParam('open', null); void load(); }}
        />
      )}
    </div>
  );
}

function AnswerRow({ item, active, onOpen }: { item: FormAnswerItem; active: boolean; onOpen: () => void }) {
  const chip = statusChip(item);
  const sentAt = item.kind === 'orphan' ? `ответ ${formatWhen(item.submitted_at)}` : formatWhen(item.created_at);
  return (
    <tr className={clsx('border-b border-dark-700 last:border-0 align-middle', active && 'bg-accent-500/5', item.status === 'orphan' && 'bg-red-500/[0.03]')}>
      <td className="px-4 py-3">
        {item.entity_id && item.entity_name ? (
          <Link to={`/all-candidates?entity=${item.entity_id}`} className="font-semibold text-white hover:underline">
            {item.entity_name}
          </Link>
        ) : (
          <span className="font-semibold text-white">Кандидат не найден</span>
        )}
        <div className="text-xs text-dark-400">
          {item.kind === 'orphan'
            ? (item.hint ? `в ответе: ${item.hint}` : 'имени в ответе нет')
            : item.entity_status}
        </div>
      </td>
      <td className="px-4 py-3 text-white">{item.form_title || 'Анкета'}</td>
      <td className="px-4 py-3 text-dark-300">{item.sent_by_name || '—'}</td>
      <td className="px-4 py-3 text-dark-300 tabular-nums whitespace-nowrap">{sentAt}</td>
      <td className="px-4 py-3">
        <span className={clsx('inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap', CHIP[chip.tone])}>
          {chip.label}
        </span>
        {item.error && <div className="text-xs text-red-600 mt-1 max-w-[320px]">{sendErrorText(item.error)}</div>}
      </td>
      <td className="px-4 py-3 text-right whitespace-nowrap">
        {item.status === 'submitted' || item.status === 'orphan' ? (
          <button type="button" onClick={onOpen}
            className="px-3 py-1.5 rounded-lg bg-accent-500 hover:bg-accent-600 text-white text-xs font-medium">
            Ответы
          </button>
        ) : (
          <div className="inline-flex gap-2">
            {item.token && (
              <button type="button" onClick={() => void copyOrShowLink(linkOf(item.token!), 'Ссылка скопирована')}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-dark-600 text-white text-xs hover:bg-dark-700">
                <Copy className="w-3.5 h-3.5" /> Скопировать ссылку
              </button>
            )}
            <button type="button" onClick={onOpen}
              className="px-3 py-1.5 rounded-lg border border-dark-600 text-white text-xs hover:bg-dark-700">
              Подробно
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}

function AnswerDrawer({
  kind, id, canAttach, onClose, onAttached,
}: {
  kind: 'dispatch' | 'orphan'; id: number; canAttach: boolean; onClose: () => void; onAttached: () => void;
}) {
  const [view, setView] = useState<FormAnswerView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setView(null);
    setError(null);
    getFormAnswer(kind, id)
      .then((v) => { if (alive) setView(v); })
      .catch((e) => {
        if (alive) setError(e?.response?.status === 404 ? 'Анкета не найдена или недоступна' : 'Не удалось загрузить ответ');
      });
    return () => { alive = false; };
  }, [kind, id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/30 flex justify-end" {...backdropClose(onClose)}>
      <aside className="h-full w-full max-w-[560px] bg-dark-800 shadow-2xl overflow-y-auto" aria-label="Ответ на анкету">
        <div className="sticky top-0 bg-dark-800 border-b border-dark-700 px-5 py-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-semibold text-white truncate">{view?.form_title || 'Анкета'}</div>
            {view && (
              view.entity_id && view.entity_name ? (
                <Link to={`/all-candidates?entity=${view.entity_id}`} className="text-sm text-accent-500 hover:underline">
                  {view.entity_name} — открыть карточку
                </Link>
              ) : (
                <div className="text-sm text-red-600">Карточки кандидата нет</div>
              )
            )}
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть" className="p-1 text-dark-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>
        {error && <div className="p-6 text-dark-400">{error}</div>}
        {!view && !error && (
          <div className="py-16 flex justify-center">
            <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {view && (
          <>
            {view.errors.length > 0 && (
              <div className="mx-5 mt-4 rounded-xl border border-red-200 bg-red-500/5 p-3 text-sm">
                <div className="font-semibold text-red-600 mb-1">У кандидата не отправилось</div>
                <ul className="space-y-0.5 text-red-600/90">
                  {view.errors.map((e, i) => <li key={i}>{sendErrorText(e)}</li>)}
                </ul>
                <div className="text-xs text-dark-400 mt-2">
                  Ответы у кандидата сохранены на его устройстве: перешлите ему ту же ссылку, после обновления страницы они вернутся.
                </div>
              </div>
            )}
            {view.status !== 'submitted' && view.token && (
              <div className="mx-5 mt-4 flex items-center gap-3 text-sm">
                <span className="text-dark-400">{view.status === 'opened' ? 'Открыта, ответа пока нет.' : 'Ссылку ещё не открывали.'}</span>
                <button type="button" onClick={() => void copyOrShowLink(linkOf(view.token), 'Ссылка скопирована')}
                  className="inline-flex items-center gap-1 text-accent-500 hover:underline">
                  <Copy className="w-3.5 h-3.5" /> Скопировать ссылку
                </button>
              </div>
            )}
            {view.answers && <AnketaResponses dispatches={[view]} readonly />}
            {kind === 'orphan' && canAttach && <AttachPicker submissionId={id} onAttached={onAttached} />}
          </>
        )}
      </aside>
    </div>
  );
}

function AttachPicker({ submissionId, onAttached }: { submissionId: number; onAttached: () => void }) {
  const [q, setQ] = useState('');
  const [debounced] = useDebounce(q, 300);
  const [found, setFound] = useState<CandidateItem[]>([]);
  const [target, setTarget] = useState<CandidateItem | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const text = debounced.trim();
    if (text.length < 2) { setFound([]); return; }
    let alive = true;
    searchCandidates({ q: text, per_page: 8 })
      .then((r) => { if (alive) setFound(r.items); })
      .catch(() => { if (alive) setFound([]); });
    return () => { alive = false; };
  }, [debounced]);

  const attach = async () => {
    if (!target) return;
    setBusy(true);
    try {
      await attachFormAnswer(submissionId, target.id);
      toast.success(`Ответ теперь в карточке: ${target.name}`);
      onAttached();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Не удалось привязать ответ');
    } finally {
      setBusy(false);
      setTarget(null);
    }
  };

  return (
    <div className="mx-5 mb-6 rounded-xl border border-dark-700 p-4">
      {target && (
        <HrConfirm
          title="Привязать ответ к кандидату?"
          subtitle={target.name}
          confirmLabel="Привязать"
          busy={busy}
          onCancel={() => setTarget(null)}
          onConfirm={() => void attach()}
        />
      )}
      <div className="flex items-center gap-2 font-semibold text-white mb-1">
        <Link2 className="w-4 h-4" /> Привязать к кандидату
      </div>
      <p className="text-xs text-dark-400 mb-3">Ответ появится во вкладке «Анкета» выбранной карточки.</p>
      <input
        id="form-answers-attach-search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Имя, телефон или почта кандидата"
        className="w-full px-3 py-2 rounded-xl bg-dark-800 border border-dark-700 text-sm text-white placeholder:text-dark-400 focus:outline-none focus:border-accent-500"
      />
      {found.length > 0 && (
        <ul className="mt-2 divide-y divide-dark-700 rounded-xl border border-dark-700">
          {found.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0">
                <div className="text-sm text-white truncate">{c.name}</div>
                <div className="text-xs text-dark-400 truncate">{[c.phone, c.email].filter(Boolean).join(' · ')}</div>
              </div>
              <button type="button" onClick={() => setTarget(c)}
                className="shrink-0 px-3 py-1.5 rounded-lg bg-accent-500 hover:bg-accent-600 text-white text-xs font-medium">
                Привязать
              </button>
            </li>
          ))}
        </ul>
      )}
      {debounced.trim().length >= 2 && found.length === 0 && (
        <div className="text-xs text-dark-400 mt-2">Никого не нашли</div>
      )}
    </div>
  );
}
