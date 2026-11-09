import { Eye } from 'lucide-react';
import { STAGE_LABEL_BY_STATUS } from '@/constants/hrStages';

/**
 * Плашка «Наблюдатель» над HR-разделами (01.10.2026, вид переделан 21.10.2026 —
 * владелец: «плашка выглядит некрасиво и надпись тоже»). Была ярко-жёлтой по
 * центру, со смайликом и длинной фразой; теперь — в цветах сайта и в том же
 * ключе, что «Вышло обновление»; затем — карточкой на линиях страницы (полоса во
 * всю ширину прилипала к сайдбару и уходила за правый край). Цвет и центр —
 * прежние жёлтые, по просьбе владельца.
 *
 * Наблюдатель — сторонний отдел: своих воронок у него нет, он заходит найти и
 * посмотреть кандидата. Запись ему запрещена (сервер и клиент), здесь только
 * честная подпись: при ограничении по воронкам «видите всё» было бы неправдой.
 */
export default function ObserverBanner({ scoped, stages }: { scoped: boolean; stages?: string[] }) {
  // Скоуп по этапам (09.11.2026): «вам открыты кандидаты на этапе „Практика“».
  const stageNames = (stages || []).map((s) => `«${STAGE_LABEL_BY_STATUS[s] || s}»`);
  const text = stageNames.length
    ? `— вам открыты кандидаты на ${stageNames.length > 1 ? 'этапах' : 'этапе'} ${stageNames.join(', ')}${scoped ? ' в отдельных воронках' : ''}, менять ничего нельзя`
    : scoped
      ? '— вам открыты отдельные воронки, менять ничего нельзя'
      : '— можно искать и открывать кандидатов и воронки, менять ничего нельзя';
  // Карточка на тех же линиях, что и полоса этапов под ней
  // (.hf-top-stage-shell: сверху и справа var(--hf-space-s), слева 0) — во
  // всю ширину без скругления она прилипала к сайдбару и уходила за край.
  return (
    <div
      className="flex-shrink-0"
      style={{ padding: 'var(--hf-space-s) var(--hf-space-s) 0 0' }}
      role="status"
      aria-live="polite"
    >
      <div
        className="flex items-center justify-center gap-2.5 rounded-2xl px-3 py-2 text-[13px]"
        // Жёлтый, как был (владелец, 21.10.2026), но карточкой и по центру.
        style={{ background: '#fde68a', color: '#92400e', border: '1px solid #f5c84c' }}
      >
        <Eye className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <span className="font-semibold">Только просмотр</span>
        <span className="min-w-0 truncate">
          {text}
        </span>
      </div>
    </div>
  );
}
