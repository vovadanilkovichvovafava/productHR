import { copyOrShowLink } from '@/utils/copyOrShowLink';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { Copy, ExternalLink, Trash2 } from 'lucide-react';
import { deleteDispatch, type FormDispatchInfo } from '@/services/api/forms';
import HrConfirm from '@/components/hr/HrConfirm';

// Бэкенд отдаёт наивный UTC ("2026-06-24T22:18:32" без зоны) — трактуем как UTC,
// чтобы toLocaleString показал корректное локальное время.
function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '';
  const norm = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + 'Z';
  const d = new Date(norm);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function AnketaResponses({
  dispatches,
  onDeleted,
}: {
  dispatches: (FormDispatchInfo & { source_entity_id?: number; source_name?: string | null })[];
  onDeleted?: (dispatchId: number) => void;
}) {
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [pendingDelete, setPendingDelete] = useState<FormDispatchInfo | null>(null);
  const handleDelete = async (d: FormDispatchInfo) => {
    setDeletingId(d.id);
    try {
      await deleteDispatch(d.id);
      toast.success('Анкета удалена');
      onDeleted?.(d.id);
      setPendingDelete(null);
    } catch {
      toast.error('Не удалось удалить анкету');
    } finally {
      setDeletingId(null);
    }
  };

  if (dispatches.length === 0) {
    return <div className="p-8 text-center text-gray-400 text-sm">Анкеты ещё не присылались</div>;
  }
  return (
    <div className="p-5 space-y-3">
      {pendingDelete && (
        <HrConfirm
          title="Удалить анкету?"
          subtitle={`«${pendingDelete.form_title || 'Анкета'}»`}
          danger="Ответы кандидата будут стёрты без возможности восстановления."
          confirmLabel="Удалить"
          busy={deletingId === pendingDelete.id}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => handleDelete(pendingDelete)}
        />
      )}
      {dispatches.map(d => (
        <div key={d.id} className="border rounded-xl p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-sm text-gray-900">{d.form_title || 'Анкета'}</p>
              {d.source_name && <p className="text-xs text-gray-500 mt-0.5">{d.source_name}</p>}
            </div>
            <div className="text-right shrink-0">
              <span className="text-xs text-gray-500">
                {d.status === 'submitted' ? 'Заполнена' : d.status === 'opened' ? 'Открыта' : 'Отправлена'}
              </span>
              {/* Когда проходил анкету: дата заполнения (или отправки, если ещё не заполнена) */}
              {(d.submitted_at || d.created_at) && (
                <p className="text-[11px] text-gray-400 mt-0.5">
                  {d.submitted_at ? formatWhen(d.submitted_at) : formatWhen(d.created_at)}
                </p>
              )}
            </div>
          </div>
          <div className="mt-1 flex items-center gap-3">
            <a
              href={`${window.location.origin}/form/${d.token}`}
              target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
            >
              <ExternalLink className="w-3 h-3" /> Открыть анкету
            </a>
            <button
              onClick={() => copyOrShowLink(`${window.location.origin}/form/${d.token}`, 'Ссылка скопирована')}
              className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
            >
              <Copy className="w-3 h-3" /> Скопировать ссылку
            </button>
            <button
              onClick={() => setPendingDelete(d)}
              disabled={deletingId === d.id}
              className="inline-flex items-center gap-1 text-xs text-red-500 hover:text-red-600 disabled:opacity-50"
            >
              <Trash2 className="w-3 h-3" /> {deletingId === d.id ? 'Удаляем…' : 'Удалить'}
            </button>
          </div>
          {d.answers && (
            <div className="mt-3 border-t pt-2 space-y-1">
              {Object.entries(d.answers).map(([k, v]) => {
                const fileUrl = d.file_links?.[k];
                const vs = String(v);
                // Видео/картинку показываем прямо в анкете (плеер/превью), а не ссылкой.
                const isVid = !!fileUrl && (/\.(mp4|mov|avi|webm|m4v)(\?|#|$)/i.test(vs) || /\.(mp4|mov|avi|webm|m4v)(\?|#|$)/i.test(fileUrl));
                const isImg = !!fileUrl && !isVid && (/\.(jpe?g|png|webp|gif)(\?|#|$)/i.test(vs) || /\.(jpe?g|png|webp|gif)(\?|#|$)/i.test(fileUrl));
                return (
                  <div key={k} className={isVid || isImg ? "text-xs" : "flex gap-2 text-xs"}>
                    <span className="text-gray-400">{d.field_labels?.[k] || k}:</span>
                    {isVid ? (
                      <video src={fileUrl} controls preload="metadata" className="mt-1 block max-h-[220px] max-w-[320px] rounded-lg border border-gray-200" />
                    ) : isImg ? (
                      <a href={fileUrl} target="_blank" rel="noopener noreferrer" className="mt-1 block w-fit">
                        <img src={fileUrl} alt={vs || 'файл'} className="max-h-[180px] max-w-[240px] rounded-lg border border-gray-200 object-cover" />
                      </a>
                    ) : fileUrl ? (
                      <a href={fileUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline break-all">
                        {vs || 'Открыть файл'}
                      </a>
                    ) : /^https?:\/\//i.test(vs) ? (
                      <a href={vs} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline break-all">{vs}</a>
                    ) : (
                      <span className="text-gray-800 break-all">{vs}</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
