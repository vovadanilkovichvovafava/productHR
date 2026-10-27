import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Eye, RotateCcw, Trash2 } from 'lucide-react';
import { DeletedCandidateCard } from '@/components/candidates/DeletedCandidateCard';
import toast from 'react-hot-toast';
import { getEntityTrash, restoreEntityFromTrash, type TrashItem } from '@/services/api/entities';
import { parseServerDate } from '@/utils/date';
import { STAGE_LABEL_BY_STAGE } from '@/constants/hrStages';
import { useAuthStore } from '@/stores/authStore';

// «Удалённые кандидаты» (20.10.2026). 19.10 кандидатку удалили, и ни кто, ни
// когда — не осталось, а вернуть было нечем. Теперь удаление кладёт кандидата в
// корзину целиком (воронки, история, комментарии, файлы) на 7 дней; здесь админ
// видит, кто и когда удалял, и возвращает кандидата как был. Сервер —
// services/entity_trash.py.
//
// С 21.10.2026 здесь же «Удалить с воронки»: кандидат убран из ОДНОЙ воронки
// (карточка осталась), а этап, чей был, история переводов и комментарии к ним
// лежат 7 дней и возвращаются кнопкой — прямо в ту воронку.
//
// С 23.10.2026 (владелец): корзина — всем рекрутёрам, а удалённого можно
// ОТКРЫТЬ как обычную карточку (только просмотр, файлы скачиваются):
// `?open=<номер записи>` — F5 оставляет карточку открытой.

const fmt = (iso: string | null) =>
  iso
    ? parseServerDate(iso).toLocaleString('ru', {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
      })
    : '—';

const TABLE_LABELS: Record<string, string> = {
  vacancy_applications: 'воронки',
  stage_transitions: 'записи истории',
  entity_files: 'файлы',
};

function summaryText(s: TrashItem['summary']): string {
  const parts: string[] = [];
  if (s.applications) parts.push(`воронок: ${s.applications}`);
  if (s.history) parts.push(`записей истории: ${s.history}`);
  if (s.files) parts.push(`файлов: ${s.files}`);
  return parts.join(' · ');
}

export default function DeletedCandidatesPage() {
  const navigate = useNavigate();
  const observer = useAuthStore((s) => s.user?.is_readonly === true);
  const [items, setItems] = useState<TrashItem[] | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [params, setParams] = useSearchParams();
  const openId = Number(params.get('open')) || null;
  const openCard = (id: number | null) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (id) next.set('open', String(id));
      else next.delete('open');
      return next;
    });

  const load = useCallback(async () => {
    try {
      setItems(await getEntityTrash());
    } catch {
      toast.error('Не удалось загрузить корзину');
      setItems([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const restore = async (item: TrashItem) => {
    setBusyId(item.id);
    try {
      const res = await restoreEntityFromTrash(item.id);
      const lost = Object.entries(res.skipped || {})
        .map(([t, n]) => `${TABLE_LABELS[t] || t}: ${n}`)
        .join(', ');
      const what =
        res.kind === 'application'
          ? `«${item.name}» снова в воронке «${item.vacancy_title || '—'}» — с этапом и историей`
          : `«${item.name}» возвращён со всеми воронками и историей`;
      toast.success(lost ? `${what}. Не вернулось (связанное удалили): ${lost}` : what, {
        duration: lost ? 8000 : 4000,
      });
      await load();
      if (res.kind === 'application' && res.vacancy_id) {
        navigate(`/my-funnels?v=${res.vacancy_id}&entity=${res.entity_id}`);
      } else {
        navigate(`/all-candidates?entity=${res.entity_id}`, { state: { openCreatedEntity: res.entity_id } });
      }
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Не удалось вернуть кандидата');
    } finally {
      setBusyId(null);
    }
  };

  if (openId) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <button
          type="button"
          onClick={() => openCard(null)}
          className="mb-4 inline-flex items-center gap-1.5 text-sm text-dark-400 hover:text-white"
        >
          <ArrowLeft className="w-4 h-4" /> Ко всем удалённым
        </button>
        <DeletedCandidateCard
          trashId={openId}
          restoring={busyId === openId}
          onRestore={observer ? undefined : (item) => restore(item)}
        />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Удалённые кандидаты</h1>
        <p className="text-dark-400 text-sm mt-1">
          Удалённый кандидат хранится 7 дней целиком — с воронками, историей, комментариями и
          файлами. Так же 7 дней хранится «Удалить с воронки»: этап, чей был кандидат и история
          переводов в этой воронке. За это время карточку можно открыть и вернуть как
          было. Кто и когда удалял — видно здесь всегда.
        </p>
      </div>

      {items === null ? (
        <div className="py-16 flex justify-center">
          <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="py-16 text-center text-dark-400">
          <Trash2 className="w-8 h-8 mx-auto mb-3 opacity-50" />
          За последние 90 дней никого не удаляли и не убирали из воронок.
        </div>
      ) : (
        <div className="grid gap-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="bg-dark-800 border border-dark-700 rounded-xl p-4 flex items-center justify-between gap-4"
            >
              <div className="min-w-0">
                <div className="font-semibold text-white truncate">{item.name || 'Без имени'}</div>
                {item.kind === 'application' && (
                  <div className="text-sm text-white/80 mt-1">
                    Убран из воронки «{item.vacancy_title || '—'}»
                    {item.owner_name ? ` · рекрутёр: ${item.owner_name}` : ''}
                    {item.stage ? ` · этап «${(STAGE_LABEL_BY_STAGE as Record<string, string>)[item.stage] || item.stage}»` : ''}
                  </div>
                )}
                <div className="text-sm text-dark-400 mt-1">
                  {item.kind === 'application' ? 'Убрал(а)' : 'Удалил(а)'}: {item.deleted_by_name || '—'} · {fmt(item.deleted_at)}
                </div>
                {item.kind === 'application'
                  ? !!item.summary?.history && (
                      <div className="text-xs text-dark-400 mt-1">записей истории: {item.summary.history}</div>
                    )
                  : summaryText(item.summary) && (
                      <div className="text-xs text-dark-400 mt-1">{summaryText(item.summary)}</div>
                    )}
              </div>
              <div className="shrink-0 text-right flex items-start gap-2">
                {!item.purged_at && !item.restored_at && (
                  <button
                    type="button"
                    onClick={() => openCard(item.id)}
                    className="flex items-center gap-2 px-3 py-2 rounded-xl border border-dark-600 text-white text-sm font-medium hover:bg-dark-700"
                  >
                    <Eye className="w-4 h-4" />
                    Открыть
                  </button>
                )}
                {item.restored_at ? (
                  <span className="text-sm text-dark-400">
                    Возвращён: {item.restored_by_name || '—'}, {fmt(item.restored_at)}
                  </span>
                ) : item.restorable ? (
                  <div className="flex flex-col items-end gap-1">
                    {!observer && (
                      <button
                        type="button"
                        onClick={() => restore(item)}
                        disabled={busyId === item.id}
                        className="flex items-center gap-2 px-3 py-2 rounded-xl bg-accent-500 hover:bg-accent-600 text-white text-sm font-medium disabled:opacity-50"
                      >
                        <RotateCcw className="w-4 h-4" />
                        {busyId === item.id ? 'Возвращаем…' : 'Вернуть'}
                      </button>
                    )}
                    <span className="text-xs text-dark-400">можно до {fmt(item.restorable_until)}</span>
                  </div>
                ) : (
                  <span className="text-sm text-dark-400">Срок хранения истёк</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
