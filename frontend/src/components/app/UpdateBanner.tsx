import { RefreshCw } from 'lucide-react';
import { useNewBuild } from '@/hooks/useNewBuild';

/**
 * Плашка «Вышло обновление» (Эльвира и владелец, 19.10.2026): исправления
 * доходят до открытой вкладки только после перезагрузки, а о деплое никто не
 * знает. Обновление безопасно: черновики комментариев и ответы анкет хранятся в
 * браузере и переживают перезагрузку.
 *
 * 21.10.2026 (владелец): карточкой на линиях страницы, как плашка наблюдателя
 * (полосой во всю ширину она прилипала к сайдбару и уходила за край), и БЕЗ
 * крестика — висит, пока не обновят. Крестик откладывал на два часа, и плашку
 * закрывали, не прочитав: после деплоя её «так и не увидели». Голубая — чтобы
 * не путать с жёлтой плашкой наблюдателя.
 *
 * «Обновить» — обычная перезагрузка (как F5), кэш чистить не нужно: index.html
 * отдаётся с no-store, а у файлов новой сборки другие имена.
 */
export default function UpdateBanner() {
  const build = useNewBuild();
  if (!build) return null;

  return (
    <div
      className="flex-shrink-0"
      // Те же линии, что у полосы этапов (.hf-top-stage-shell): сверху и справа
      // var(--hf-space-s), слева 0.
      style={{ padding: 'var(--hf-space-s) var(--hf-space-s) 0 0' }}
      role="status"
      aria-live="polite"
    >
      <div
        className="flex items-center justify-center gap-2.5 rounded-2xl px-3 py-1.5 text-[13px]"
        style={{ background: '#e0edff', color: '#1e3a8a', border: '1px solid #bfd4fb' }}
      >
        <RefreshCw className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <span className="font-semibold">Вышло обновление Enceladus</span>
        <span className="min-w-0 truncate">— обновите страницу, набранное не пропадёт</span>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="flex-shrink-0 rounded-full px-3 py-1 text-xs font-semibold text-white"
          style={{ background: '#2563eb' }}
        >
          Обновить
        </button>
      </div>
    </div>
  );
}
