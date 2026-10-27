import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { History } from 'lucide-react';
import HrConfirm from '@/components/hr/HrConfirm';
import { deduplicatedGet } from '@/services/api/client';
import { parseServerDate } from '@/utils/date';

// «Был отказ» (владелец, 22.10.2026): человек уже получал у нас отказ — в
// другой воронке, в другой своей карточке-дубле или в архиве ClickUp. Раньше
// плашка дубля говорила только «Возможно тот же человек · 64%», а про отказ —
// ничего; на проде отклонённых заводили заново и вели с нуля. Решение
// владельца — ПРЕДУПРЕЖДАТЬ, не запрещать. Сервер — services/prior_rejection.py.
// Один модуль на все места: строка списка и воронки, карточка, окна
// «Добавить в воронку» / «Забрать».

export interface PriorRejection {
  /** rejected — отказ (наш); no_show — не пришёл / не отвечал (архив ClickUp). */
  kind: 'rejected' | 'no_show';
  /** funnel — этап «Отказ» в воронке, card — отказ вне воронок, archive — ClickUp. */
  source: 'funnel' | 'card' | 'archive';
  entity_id: number;
  vacancy_id?: number | null;
  vacancy_title?: string | null;
  date?: string | null;
  recruiter_name?: string | null;
  /** С какого этапа отклонили; у архива — статус ClickUp («собес (1): нет»). */
  from_stage?: string | null;
  comment?: string | null;
  reason?: string | null;
  archived?: boolean;
  /** Только в коротком виде для строки списка: сколько отказов всего. */
  count?: number;
}

export async function getPriorRejections(entityId: number): Promise<PriorRejection[]> {
  const { data } = await deduplicatedGet<{ items: PriorRejection[] }>(
    `/entities/${entityId}/prior-rejections`,
  );
  return data.items || [];
}

function shortDate(iso?: string | null): string {
  if (!iso) return '';
  const d = parseServerDate(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.getFullYear() === new Date().getFullYear()
    ? d.toLocaleDateString('ru', { day: 'numeric', month: 'short' }).replace('.', '')
    : d.toLocaleDateString('ru', { month: 'short', year: 'numeric' }).replace('.', '').replace(' г', '');
}

function fullDate(iso?: string | null): string {
  if (!iso) return '';
  const d = parseServerDate(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('ru', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** «Был отказ · 28 авг · Трафик» — для строки списка. */
export function priorRejectionLabel(pr: PriorRejection): string {
  return [
    pr.kind === 'no_show' ? 'Не пришёл' : 'Был отказ',
    shortDate(pr.date),
    pr.vacancy_title,
  ].filter(Boolean).join(' · ');
}

/** Подробности одной строкой-абзацем: когда, где, кто, с какого этапа. */
export function priorRejectionWhere(pr: PriorRejection): string {
  const head = pr.kind === 'no_show' ? 'Не пришёл' : 'Отказ';
  return [
    [head, fullDate(pr.date)].filter(Boolean).join(' '),
    pr.vacancy_title ? `«${pr.vacancy_title}»` : pr.source === 'card' ? 'вне воронок' : '',
    pr.recruiter_name ? `рекрутёр ${pr.recruiter_name}` : '',
    pr.source === 'archive' ? `ClickUp: ${pr.from_stage || 'архив'}` : pr.from_stage ? `с этапа «${pr.from_stage}»` : '',
  ].filter(Boolean).join(' · ');
}

export function priorRejectionTooltip(pr: PriorRejection): string {
  return [
    priorRejectionWhere(pr),
    pr.comment ? `«${pr.comment}»` : '',
    pr.reason ? `Причина: ${pr.reason}` : '',
    (pr.count || 0) > 1 ? `Всего отказов: ${pr.count}` : '',
  ].filter(Boolean).join('\n');
}

export function PriorRejectionChip({ pr }: { pr: PriorRejection }) {
  return (
    <span
      className="inline-flex max-w-full items-center gap-[4px] rounded-[20px] px-[7px] py-[1px] text-[length:var(--hf-fs-2xs)] font-semibold"
      style={{ background: '#fdecec', color: '#a32d2d' }}
      title={priorRejectionTooltip(pr)}
    >
      <History className="h-[10px] w-[10px] shrink-0" aria-hidden="true" />
      <span className="truncate">{priorRejectionLabel(pr)}</span>
      {(pr.count || 0) > 1 && <span className="shrink-0 opacity-70">+{(pr.count || 1) - 1}</span>}
    </span>
  );
}

/** Красная плашка в карточке: последний отказ подробно, остальные строкой. */
export function PriorRejectionBanner({
  items,
  onOpenCard,
  currentEntityId,
}: {
  items: PriorRejection[];
  onOpenCard?: (entityId: number) => void;
  currentEntityId?: number;
}) {
  if (!items.length) return null;
  const [top, ...rest] = items;
  const otherCard = top.entity_id !== currentEntityId ? top.entity_id : null;
  return (
    <div
      className="rounded-xl px-3 py-2 text-[13px] leading-snug"
      style={{ background: '#fdecec', color: '#791f1f' }}
      role="status"
    >
      <div className="flex items-center gap-1.5 font-semibold">
        <History className="h-4 w-4 shrink-0" aria-hidden="true" />
        {top.kind === 'no_show' ? 'Уже был у нас — не пришёл' : 'Уже был у нас — отказ'}
        {top.date ? ` ${fullDate(top.date)}` : ''}
      </div>
      <div className="mt-1" style={{ color: '#a32d2d' }}>{priorRejectionWhere(top)}</div>
      {top.comment && <div className="mt-0.5" style={{ color: '#a32d2d' }}>«{top.comment}»</div>}
      {top.reason && <div className="mt-0.5" style={{ color: '#a32d2d' }}>Причина: {top.reason}</div>}
      {rest.length > 0 && (
        <div className="mt-1 text-[12px]" style={{ color: '#a32d2d' }}>
          Ещё: {rest.slice(0, 3).map(priorRejectionLabel).join('; ')}
          {rest.length > 3 ? ` и ещё ${rest.length - 3}` : ''}
        </div>
      )}
      {otherCard && onOpenCard && (
        <button
          type="button"
          className="mt-1.5 text-[12px] font-semibold underline"
          style={{ color: '#791f1f' }}
          onClick={() => onOpenCard(otherCard)}
        >
          {top.archived ? 'Открыть карточку из архива' : 'Открыть ту карточку'}
        </button>
      )}
    </div>
  );
}

/**
 * Отказы для плашки открытой карточки («Все кандидаты» и воронка). Свои
 * воронки не берём — их отказ виден блоком воронки в самой карточке; только
 * другие карточки того же человека и прохождения архива. `ownFunnelsExcept` —
 * воронка: там карточка показывает только СВОЙ блок, поэтому нужны и отказы
 * этого кандидата в других воронках.
 */
export function useVisiblePriorRejections(entityId?: number | null, ownFunnelsExcept?: number): PriorRejection[] {
  const [items, setItems] = useState<PriorRejection[]>([]);
  useEffect(() => {
    if (!entityId) return;
    let alive = true;
    setItems([]);
    getPriorRejections(entityId)
      .then((list) => {
        if (!alive) return;
        setItems(list.filter((i) =>
          i.entity_id !== entityId
          || i.source === 'archive'
          || (ownFunnelsExcept != null && i.source === 'funnel' && i.vacancy_id !== ownFunnelsExcept)));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [entityId, ownFunnelsExcept]);
  return items;
}

/** Короткие слова для «дубль: имя + телефон» из подписей причин бэка. */
export function duplicateReasonWords(reasons: string[]): string {
  const words = reasons.map((r) => {
    const t = r.toLowerCase();
    if (t.includes('имен')) return 'имя';
    if (t.includes('телефон')) return 'телефон';
    if (t.includes('email') || t.includes('почт')) return 'почта';
    if (t.includes('telegram')) return 'Telegram';
    if (t.includes('рожд')) return 'дата рождения';
    if (t.includes('ссылк')) return 'ссылка на резюме';
    if (t.includes('текст')) return 'текст резюме';
    return r;
  });
  return [...new Set(words)].join(' + ');
}

/**
 * ОДНА карточка вместо двух плашек над карточкой кандидата (владелец,
 * 22.10.2026: «занимает много места, красная плашка некрасивая»). Было:
 * розовый блок «Уже был у нас — отказ…» на пять строк и под ним красная полоса
 * во всю ширину «Точное совпадение — кандидат уже в базе». Стало — мягкая
 * карточка в две строки: отказ (или дубль) + кнопка; ниже комментарий и
 * «дубль: имя + телефон».
 */
export function CandidateAlertCard({
  rejections = [],
  duplicate,
  actionLabel,
  onAction,
}: {
  rejections?: PriorRejection[];
  duplicate?: { exact: boolean; confidence?: number; text?: boolean; reasons: string[] } | null;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const top = rejections[0];
  if (!top && !duplicate) return null;
  const red = !!top || !!duplicate?.exact;
  // Ярко, но не криком (владелец, 22.10.2026: «более яркой и видной»): насыщенный
  // фон, цветная рамка, иконка в залитом кружке, залитая кнопка.
  const palette = red
    ? { bg: '#fde3e3', border: '#f19a9a', strong: '#7f1d1d', soft: '#b42323', accent: '#dc2626' }
    : { bg: '#fff1cc', border: '#f2c25c', strong: '#713f00', soft: '#92400e', accent: '#d97706' };
  const dupLabel = duplicate
    ? duplicate.exact
      ? 'точный дубль'
      : duplicate.text
        ? `текст резюме совпадает · ${Math.round(duplicate.confidence || 0)}%`
        : `возможно тот же · ${Math.round(duplicate.confidence || 0)}%`
    : '';
  const dupWords = duplicate ? duplicateReasonWords(duplicate.reasons) : '';
  const title = top
    ? `${top.kind === 'no_show' ? 'Уже был у нас — не пришёл' : 'Уже был у нас — отказ'}${top.date ? ` ${shortDate(top.date)}` : ''}`
    : duplicate?.exact
      ? 'Точное совпадение — кандидат уже в базе'
      : `Возможно, тот же человек · ${Math.round(duplicate?.confidence || 0)}%`;
  const meta = top
    ? [top.vacancy_title ? `«${top.vacancy_title}»` : top.source === 'card' ? 'вне воронок' : '', top.recruiter_name,
       top.source === 'archive' ? `ClickUp: ${top.from_stage || 'архив'}` : ''].filter(Boolean).join(' · ')
    : '';
  const second: string[] = [];
  if (top?.comment) second.push(`«${top.comment}»`);
  if (top?.reason) second.push(`причина: ${top.reason}`);
  if (rejections.length > 1) second.push(`всего отказов: ${rejections.length}`);
  return (
    <div
      className="flex flex-wrap items-start gap-3 rounded-xl border-[1.5px] px-3.5 py-2.5 text-[13px] leading-snug shadow-[0_1px_6px_rgba(220,38,38,0.12)]"
      style={{ background: palette.bg, borderColor: palette.border, color: palette.strong }}
      role="status"
    >
      <span
        className="mt-[1px] flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white"
        style={{ background: palette.accent }}
        aria-hidden="true"
      >
        <History className="h-4 w-4" />
      </span>
      {/* На узком экране кнопка уходит под текст, а не сжимает его в столбик. */}
      <div className="min-w-[170px] flex-1">
        <div className="flex flex-wrap items-baseline gap-x-1.5">
          <span className="text-[14px] font-bold">{title}</span>
          {meta && <span style={{ color: palette.soft }}>· {meta}</span>}
        </div>
        {(second.length > 0 || (top && duplicate)) && (
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px]" style={{ color: palette.soft }}>
            {second.length > 0 && <span className="min-w-0">{second.join(' · ')}</span>}
            {top && duplicate && (
              <span
                className="rounded-full border bg-white px-2 py-[1px] text-[11px] font-medium"
                style={{ borderColor: palette.border, color: palette.strong }}
                title={duplicate.reasons.join(', ')}
              >
                {dupLabel}{dupWords ? `: ${dupWords}` : ''}
              </span>
            )}
          </div>
        )}
        {!top && duplicate && dupWords && (
          <div className="mt-0.5 text-[12px]" style={{ color: palette.soft }}>совпало: {dupWords}</div>
        )}
      </div>
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="ml-auto shrink-0 self-center rounded-lg px-3.5 py-1.5 text-[12.5px] font-semibold text-white transition-opacity hover:opacity-90"
          style={{ background: palette.accent }}
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}

/** Только отказ, без дубля (у карточки нет пометки дубля): ссылка на ту карточку. */
export function PriorRejectionPanel({
  entityId,
  ownFunnelsExcept,
}: {
  entityId: number;
  ownFunnelsExcept?: number;
}) {
  const items = useVisiblePriorRejections(entityId, ownFunnelsExcept);
  const navigate = useNavigate();
  const top = items[0];
  if (!top) return null;
  const other = top.entity_id !== entityId ? top.entity_id : null;
  return (
    <CandidateAlertCard
      rejections={items}
      actionLabel={other ? (top.archived ? 'Открыть из архива' : 'Открыть ту карточку') : undefined}
      onAction={other ? () => navigate(`/all-candidates?entity=${other}${top.archived ? '&archived=1' : ''}`) : undefined}
    />
  );
}

/**
 * Вопрос «Всё равно добавить?» перед «Добавить в воронку» / «Забрать», если
 * у человека был отказ. `gate(entityId)` → true, если можно продолжать.
 * Сбой запроса не мешает добавить: предупреждение — подсказка, не замок.
 */
export function usePriorRejectionGate() {
  const [pending, setPending] = useState<PriorRejection[] | null>(null);
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  const gate = useCallback(async (entityId: number): Promise<boolean> => {
    let items: PriorRejection[] = [];
    try {
      items = await getPriorRejections(entityId);
    } catch {
      return true;
    }
    if (!items.length) return true;
    setPending(items);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const finish = (ok: boolean) => {
    setPending(null);
    resolver.current?.(ok);
    resolver.current = null;
  };

  const element = pending ? (
    <HrConfirm
      title={pending[0].kind === 'no_show' ? 'Этот кандидат уже не приходил к нам' : 'Этот кандидат уже получал отказ'}
      subtitle={[
        priorRejectionWhere(pending[0]),
        pending[0].comment ? `«${pending[0].comment}»` : '',
        pending.length > 1 ? `всего записей: ${pending.length}` : '',
      ].filter(Boolean).join(' — ')}
      confirmLabel="Всё равно добавить"
      inDialog
      onCancel={() => finish(false)}
      onConfirm={() => finish(true)}
    />
  ) : null;

  return { gate, element };
}
