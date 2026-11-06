import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { Copy, Inbox, Link2, Loader2, Search, X } from 'lucide-react';
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
  ok: 'hf-forms-pill-ok',
  warn: 'hf-forms-pill-warn',
  muted: 'hf-forms-pill-muted',
  bad: 'hf-forms-pill-bad',
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

  const filtered = !!(search || filters.formId || filters.sentBy || filters.days || filters.status !== 'all');

  return (
    <div className="hf-forms-page">
      <div className="hf-forms-header">
        <div>
          <div className="hf-forms-heading">
            <h1 className="hf-forms-title">Анкеты</h1>
            <FormsPageTabs />
          </div>
          <p className="hf-forms-subtitle">Отправленные анкеты и ответы кандидатов</p>
        </div>
        <div className="hf-forms-tools">
          <div className="hf-forms-search">
            <Search className="hf-forms-search-icon" size={15} />
            <input
              id="form-answers-search"
              className="hf-forms-search-input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Escape') setSearch(''); }}
              placeholder="Поиск по кандидату, анкете…"
            />
            {search && (
              <button type="button" className="hf-forms-search-clear" aria-label="Очистить поиск" onClick={() => setSearch('')}>
                <X size={14} />
              </button>
            )}
          </div>
          <select
            id="form-answers-form"
            className={clsx('hf-forms-select', filters.formId && 'hf-forms-select-on')}
            value={filters.formId ?? ''}
            onChange={(e) => setParam('form', e.target.value || null)}
            aria-label="Анкета"
          >
            <option value="">Анкета: все</option>
            {(data?.forms ?? []).map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
          </select>
          <select
            id="form-answers-sender"
            className={clsx('hf-forms-select', filters.sentBy && 'hf-forms-select-on')}
            value={filters.sentBy ?? ''}
            onChange={(e) => setParam('sender', e.target.value || null)}
            aria-label="Кто отправил"
          >
            <option value="">Отправил: все</option>
            {(data?.senders ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <select
            id="form-answers-period"
            className={clsx('hf-forms-select', filters.days && 'hf-forms-select-on')}
            value={filters.days ?? ''}
            onChange={(e) => setParam('days', e.target.value || null)}
            aria-label="Период"
          >
            {PERIODS.map((p) => <option key={p.label} value={p.days ?? ''}>{p.label}</option>)}
          </select>
        </div>
      </div>

      <div className="hf-forms-body">
        <nav className="hf-forms-sidebar" aria-label="Статус анкеты">
          {STATUS_TABS.map((t) => {
            const n = counts?.[t.key];
            return (
              <button
                key={t.key}
                type="button"
                aria-current={filters.status === t.key ? 'true' : undefined}
                onClick={() => setParam('status', t.key === 'all' ? null : t.key)}
                className={clsx(
                  'hf-forms-folder',
                  filters.status === t.key && 'hf-forms-folder-active',
                  t.key === 'orphan' && !!n && 'hf-forms-folder-alarm',
                )}
              >
                <span className="hf-forms-folder-name">{t.label}</span>
                <span className="hf-forms-folder-count">{n ?? '…'}</span>
              </button>
            );
          })}
        </nav>

        {loading && !data ? (
          <div className="hf-forms-spinner" style={{ flex: 1 }}><Loader2 className="animate-spin" size={26} /></div>
        ) : failed && !data ? (
          <div className="hf-forms-empty">
            Не удалось загрузить анкеты. <button type="button" onClick={() => void load()}>Повторить</button>
          </div>
        ) : items.length === 0 ? (
          <div className="hf-forms-empty">
            <Inbox size={28} style={{ margin: '0 auto 8px', opacity: 0.5 }} />
            {filtered ? 'По этим условиям анкет нет' : 'Анкеты ещё не отправлялись'}
          </div>
        ) : (
          <div className="hf-forms-table-wrap">
            <table className="hf-forms-table">
              <thead>
                <tr>
                  <th className="hf-forms-th">Кандидат</th>
                  <th className="hf-forms-th">Анкета</th>
                  <th className="hf-forms-th">Отправил</th>
                  <th className="hf-forms-th">Отправлена</th>
                  <th className="hf-forms-th">Статус</th>
                  <th className="hf-forms-th" aria-label="Действия" />
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
      </div>

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
  const hasAnswer = item.status === 'submitted' || item.status === 'orphan';
  return (
    // Клик по строке открывает ответ (или подробности ссылки); ссылки и кнопки внутри — сами по себе.
    <tr
      className={clsx('hf-forms-row hf-forms-row-click', active && 'hf-forms-row-active')}
      onClick={(e) => { if (!(e.target as HTMLElement).closest('a,button')) onOpen(); }}
    >
      <td className="hf-forms-td">
        {item.entity_id && item.entity_name ? (
          <Link to={`/all-candidates?entity=${item.entity_id}`} className="hf-forms-name hf-forms-nowrap">{item.entity_name}</Link>
        ) : (
          <span className="hf-forms-name">Кандидат не найден</span>
        )}
        <div className="hf-forms-sub">
          {item.kind === 'orphan'
            ? (item.hint ? `в ответе: ${item.hint}` : 'имени в ответе нет')
            : item.entity_status}
        </div>
      </td>
      <td className="hf-forms-td hf-forms-td-clip" title={item.form_title || undefined}>{item.form_title || 'Анкета'}</td>
      <td className="hf-forms-td hf-forms-td-num">{item.sent_by_name || '—'}</td>
      <td className="hf-forms-td hf-forms-td-num">{sentAt}</td>
      <td className="hf-forms-td">
        <span className={clsx('hf-forms-pill', CHIP[chip.tone])}>{chip.label}</span>
        {item.error && <div className="hf-forms-error">{sendErrorText(item.error)}</div>}
      </td>
      <td className="hf-forms-td hf-forms-td-actions">
        {hasAnswer ? (
          <button type="button" className="hf-forms-action hf-forms-action-primary" onClick={onOpen}>Ответы</button>
        ) : item.token ? (
          <button type="button" className="hf-forms-action" title="Скопировать ссылку на анкету, чтобы переслать кандидату"
            onClick={() => void copyOrShowLink(linkOf(item.token!), 'Ссылка скопирована')}>
            <Copy size={13} /> Ссылка
          </button>
        ) : null}
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
    <div className="hf-forms-drawer-backdrop" {...backdropClose(onClose)}>
      <aside className="hf-forms-drawer" aria-label="Ответ на анкету">
        <div className="hf-forms-drawer-head">
          <div style={{ minWidth: 0 }}>
            <div className="hf-forms-drawer-title">{view?.form_title || 'Анкета'}</div>
            {view && (
              view.entity_id && view.entity_name ? (
                <Link to={`/all-candidates?entity=${view.entity_id}`} className="hf-forms-drawer-link">
                  {view.entity_name} — открыть карточку
                </Link>
              ) : (
                <div className="hf-forms-drawer-missing">Карточки кандидата нет</div>
              )
            )}
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть" className="hf-forms-drawer-close">
            <X size={18} />
          </button>
        </div>
        {error && <div className="hf-forms-drawer-section hf-forms-note">{error}</div>}
        {!view && !error && <div className="hf-forms-spinner"><Loader2 className="animate-spin" size={22} /></div>}
        {view && (
          <>
            {view.errors.length > 0 && (
              <div className="hf-forms-drawer-section hf-forms-alert">
                <div className="hf-forms-alert-title">У кандидата не отправилось</div>
                <ul>
                  {view.errors.map((e, i) => <li key={i}>{sendErrorText(e)}</li>)}
                </ul>
                <div className="hf-forms-alert-hint">
                  Ответы у кандидата сохранены на его устройстве: перешлите ему ту же ссылку, после обновления страницы они вернутся.
                </div>
              </div>
            )}
            {view.status !== 'submitted' && view.token && (
              <div className="hf-forms-drawer-section hf-forms-note">
                <span>{view.status === 'opened' ? 'Открыта, ответа пока нет.' : 'Ссылку ещё не открывали.'}</span>
                <button type="button" className="hf-forms-action"
                  onClick={() => void copyOrShowLink(linkOf(view.token), 'Ссылка скопирована')}>
                  <Copy size={13} /> Скопировать ссылку
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
    <div className="hf-forms-attach">
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
      <div className="hf-forms-attach-title"><Link2 size={15} /> Привязать к кандидату</div>
      <p className="hf-forms-attach-hint">Ответ появится во вкладке «Анкета» выбранной карточки.</p>
      <input
        id="form-answers-attach-search"
        className="hf-forms-input"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Имя, телефон или почта кандидата"
      />
      {found.length > 0 && (
        <ul className="hf-forms-found">
          {found.map((c) => (
            <li key={c.id}>
              <div style={{ minWidth: 0 }}>
                <div className="hf-forms-name">{c.name}</div>
                <div className="hf-forms-sub">{[c.phone, c.email].filter(Boolean).join(' · ')}</div>
              </div>
              <button type="button" className="hf-forms-action hf-forms-action-primary" onClick={() => setTarget(c)}>
                Привязать
              </button>
            </li>
          ))}
        </ul>
      )}
      {debounced.trim().length >= 2 && found.length === 0 && (
        <div className="hf-forms-sub" style={{ marginTop: 8 }}>Никого не нашли</div>
      )}
    </div>
  );
}
