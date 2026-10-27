import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { History } from 'lucide-react';
import toast from 'react-hot-toast';
import { getAuditLog, getAuditUsers, type AuditItem } from '@/services/api/audit';
import { useLiveSearchParams } from '@/hooks/useLiveSearchParams';
import { parseServerDate } from '@/utils/date';

// «Журнал действий» (21.10.2026). Владелец: «максимально детальное
// логирование… каждый их чих, чтобы не было расхождения, в котором непонятно,
// кто что делал, кто редактировал». Каждое изменение в HR — строка: кто, когда,
// что, над каким кандидатом / воронкой и с какими данными. Пишет сервер сам
// (middleware), поэтому новые кнопки попадают сюда без доработок. Фильтры — в
// адресе (F5 оставляет на месте): ?user= &entity= &errors=1.

const fmt = (iso: string | null) =>
  iso
    ? parseServerDate(iso).toLocaleString('ru', {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
      })
    : '—';

const num = (v: string | null) => {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
};

export default function AuditLogPage() {
  const [searchParams, setSearchParams] = useLiveSearchParams();
  const userId = num(searchParams.get('user'));
  const entityId = num(searchParams.get('entity'));
  const onlyErrors = searchParams.get('errors') === '1';

  const [items, setItems] = useState<AuditItem[] | null>(null);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [users, setUsers] = useState<Array<{ user_id: number; name: string; count: number }>>([]);
  const [entityInput, setEntityInput] = useState(entityId ? String(entityId) : '');

  const setFilter = useCallback(
    (key: string, value: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      }, { replace: true });
    },
    [setSearchParams],
  );

  useEffect(() => {
    getAuditUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  useEffect(() => {
    let alive = true;
    setItems(null);
    getAuditLog({ userId, entityId, onlyErrors })
      .then((res) => {
        if (!alive) return;
        setItems(res.items);
        setNextBefore(res.next_before_id);
      })
      .catch(() => {
        if (!alive) return;
        toast.error('Не удалось загрузить журнал');
        setItems([]);
      });
    return () => {
      alive = false;
    };
  }, [userId, entityId, onlyErrors]);

  const loadMore = async () => {
    if (!nextBefore) return;
    setLoadingMore(true);
    try {
      const res = await getAuditLog({ userId, entityId, onlyErrors, beforeId: nextBefore });
      setItems((prev) => [...(prev || []), ...res.items]);
      setNextBefore(res.next_before_id);
    } catch {
      toast.error('Не удалось загрузить ещё');
    } finally {
      setLoadingMore(false);
    }
  };

  const applyEntity = () => setFilter('entity', num(entityInput) ? String(num(entityInput)) : null);
  const filtered = useMemo(() => items || [], [items]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-white">Журнал действий</h1>
        <p className="text-dark-400 text-sm mt-1">
          Каждое изменение в HR: кто, когда, что сделал и над кем — этапы, комментарии, правки карточки,
          воронки, удаления. Записывается само, хранится год. Просмотры сюда не пишутся.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3 mb-4">
        <label className="text-sm text-dark-400 flex flex-col gap-1">
          Кто
          <select
            value={userId ?? ''}
            onChange={(e) => setFilter('user', e.target.value || null)}
            className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-white min-w-[220px]"
          >
            <option value="">Все</option>
            {users.map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.name} · {u.count}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-dark-400 flex flex-col gap-1">
          Кандидат №
          <span className="flex gap-2">
            <input
              value={entityInput}
              onChange={(e) => setEntityInput(e.target.value.replace(/\D/g, ''))}
              onKeyDown={(e) => e.key === 'Enter' && applyEntity()}
              onBlur={applyEntity}
              placeholder="например, 9509"
              inputMode="numeric"
              className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-white w-40"
            />
            {entityId && (
              <button
                type="button"
                onClick={() => {
                  setEntityInput('');
                  setFilter('entity', null);
                }}
                className="text-sm text-dark-400 hover:text-white"
              >
                Сбросить
              </button>
            )}
          </span>
        </label>
        <label className="text-sm text-dark-400 flex items-center gap-2 pb-2">
          <input type="checkbox" checked={onlyErrors} onChange={(e) => setFilter('errors', e.target.checked ? '1' : null)} />
          Только неудачные (отказ сервера)
        </label>
      </div>

      {items === null ? (
        <div className="py-16 flex justify-center">
          <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-16 text-center text-dark-400">
          <History className="w-8 h-8 mx-auto mb-3 opacity-50" />
          Ничего не найдено.
        </div>
      ) : (
        <div className="bg-dark-800 border border-dark-700 rounded-xl divide-y divide-dark-700">
          {filtered.map((it) => (
            <AuditRow key={it.id} it={it} />
          ))}
        </div>
      )}

      {nextBefore && (
        <div className="flex justify-center mt-4">
          <button
            type="button"
            onClick={loadMore}
            disabled={loadingMore}
            className="px-4 py-2 rounded-xl border border-dark-700 text-sm text-white hover:bg-dark-700 disabled:opacity-50"
          >
            {loadingMore ? 'Загружаем…' : 'Показать ещё'}
          </button>
        </div>
      )}
    </div>
  );
}

function AuditRow({ it }: { it: AuditItem }) {
  const failed = (it.status ?? 0) >= 400;
  const bodyText = it.body == null ? null : JSON.stringify(it.body, null, 2);
  return (
    <details className="group px-4 py-3">
      <summary className="flex flex-wrap items-baseline gap-x-3 gap-y-1 cursor-pointer list-none">
        <span className="text-xs text-dark-400 w-36 shrink-0 tabular-nums">{fmt(it.at)}</span>
        <span className="text-sm text-white font-medium">{it.user_name || 'Без входа'}</span>
        <span className="text-sm text-white/80">{it.action || `${it.method} ${it.path}`}</span>
        {it.entity_id && (
          <Link
            to={`/all-candidates?entity=${it.entity_id}`}
            onClick={(e) => e.stopPropagation()}
            className="text-sm text-accent-400 hover:underline"
          >
            {it.entity_name || `кандидат №${it.entity_id}`}
          </Link>
        )}
        {it.vacancy_id && (
          <Link
            to={`/my-funnels?v=${it.vacancy_id}`}
            onClick={(e) => e.stopPropagation()}
            className="text-sm text-dark-400 hover:text-white hover:underline"
          >
            «{it.vacancy_title || `воронка №${it.vacancy_id}`}»
          </Link>
        )}
        {failed && (
          <span className="text-xs rounded-full px-2 py-0.5 bg-red-500/15 text-red-400">
            не выполнено · {it.status}
          </span>
        )}
      </summary>
      <div className="mt-2 ml-0 sm:ml-[9.75rem] text-xs text-dark-400 space-y-1">
        <div className="font-mono">
          {it.method} {it.path} → {it.status ?? '—'}
          {it.duration_ms != null ? ` · ${it.duration_ms} мс` : ''}
        </div>
        {bodyText && (
          <pre className="whitespace-pre-wrap break-words bg-dark-900/60 rounded-lg p-3 text-[11px] text-white/80 max-h-80 overflow-auto">
            {bodyText}
          </pre>
        )}
      </div>
    </details>
  );
}
