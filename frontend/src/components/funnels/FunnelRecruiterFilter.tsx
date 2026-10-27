import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Users, X } from 'lucide-react';
import type { FunnelRecruiters } from '@/services/api';
import { funnelViewKey, type FunnelViewOwner } from './useFunnelCandidates';

// Фильтр над воронкой: чьих кандидатов показываем (владелец, 21.10.2026).
//
// Вакансию часто ведут двое-трое. Раньше в своей воронке у человека были только
// его кандидаты, а при входе из «Мои вакансии» не было даже кнопки показать
// остальных (Мария: «очень много доп действий»). Теперь на любом этапе каждый
// отмеченный рекрутёр — плашка с полным именем и крестиком, рядом кнопка
// «Рекрутёры» со списком: каждый, кто ведёт кандидатов в этой воронке, с числом
// и галочкой (отмечать можно нескольких), и «Все рекрутёры». Отметил коллег —
// их кандидатов и смотришь, и правишь. Ушёл из воронки — снова свои
// (useFunnelCandidates).

const chip =
  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors';
const idle =
  'border-[color:var(--hf-main-300)] bg-[var(--hf-white)] text-[var(--hf-main-900)] hover:border-[color:var(--hf-accent)] hover:text-[color:var(--hf-accent)]';
const active =
  'border-[color:var(--hf-accent)] text-[color:var(--hf-accent)] bg-[var(--hf-main-50)]';

/** Плашки над воронкой: кто сейчас отмечен, с полным именем. Сначала вы,
 *  дальше в порядке списка (там у кого больше кандидатов). */
export function funnelViewChips(
  owner: FunnelViewOwner,
  myId: number | null | undefined,
  options: FunnelRecruiters | null,
): Array<{ owner: FunnelViewOwner; label: string }> {
  if (owner === 'all') return [{ owner: 'all', label: 'Все рекрутёры' }];
  const order = (options?.recruiters ?? []).map((r) => r.user_id);
  const ids = [...new Set(owner)].sort((a, b) => {
    if (a === myId) return -1;
    if (b === myId) return 1;
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia < 0 ? 1e9 : ia) - (ib < 0 ? 1e9 : ib);
  });
  return ids.map((id) => {
    const name = options?.recruiters.find((r) => r.user_id === id)?.name;
    return {
      owner: [id],
      label: id === myId ? (name ? `${name} (вы)` : 'Вы') : name ?? '…',
    };
  });
}

export function FunnelRecruiterFilter({
  viewOwner,
  setViewOwner,
  options,
  myId,
  allIsDefault = false,
}: {
  viewOwner: FunnelViewOwner;
  setViewOwner: (owner: FunnelViewOwner) => void;
  options: FunnelRecruiters | null;
  myId: number | null | undefined;
  /** Суперадмин и наблюдатель: своих кандидатов нет, «Все» — исходный вид, и
   *  крестик у него увёл бы в пустой список. */
  allIsDefault?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const selected = new Set(viewOwner === 'all' ? [] : viewOwner);
  // «Все рекрутёры» — отдельный пункт. Галочка у человека добавляет или убирает
  // его; последнюю снять нельзя — пустой выбор дал бы пустую воронку. Из «Все»
  // щелчок по человеку оставляет только его.
  const toggle = (id: number) => {
    if (viewOwner === 'all') return setViewOwner([id]);
    const next = new Set(selected);
    if (next.has(id)) {
      if (next.size === 1) return;
      next.delete(id);
    } else next.add(id);
    const owner = [...next];
    if (funnelViewKey(owner) !== funnelViewKey(viewOwner)) setViewOwner(owner);
  };

  const people = (options?.recruiters ?? []).map((r) => ({
    id: r.user_id,
    label: r.user_id === myId ? `Вы · ${r.name}` : r.name,
    count: r.count as number | null,
  }));
  // Отмеченный мог пропасть из списка (кандидатов не осталось, воронку он не
  // брал) — показываем его строкой, чтобы галочку можно было снять.
  for (const id of selected) {
    if (!people.some((p) => p.id === id)) {
      people.push({ id, label: id === myId ? 'Вы' : `Рекрутёр #${id}`, count: 0 });
    }
  }
  const chips = funnelViewChips(viewOwner, myId, options);
  // Крестик: снять этого рекрутёра. Последнюю плашку крестик возвращает к своим
  // кандидатам; у своей последней плашки крестика нет — убирать некуда.
  const removeChip = (chipOwner: FunnelViewOwner) => {
    if (chipOwner === 'all' || viewOwner === 'all') {
      if (myId != null) setViewOwner([myId]);
      return;
    }
    const id = chipOwner[0];
    const rest = viewOwner.filter((x) => x !== id);
    if (rest.length > 0) setViewOwner(rest);
    else if (myId != null && id !== myId) setViewOwner([myId]);
  };
  const canRemove = (chipOwner: FunnelViewOwner) =>
    myId != null &&
    !(chipOwner === 'all' && allIsDefault) &&
    !(chipOwner !== 'all' && viewOwner !== 'all' && viewOwner.length === 1 && chipOwner[0] === myId);

  return (
    <div ref={rootRef} className="relative flex flex-wrap items-center gap-1.5">
      {chips.map((c) => (
        <span key={String(c.owner)} className={`${chip} ${active}`}>
          {c.label}
          {canRemove(c.owner) && (
            <button
              type="button"
              onClick={() => removeChip(c.owner)}
              aria-label={`Убрать: ${c.label}`}
              title="Убрать из фильтра"
              className="-mr-1 rounded-full p-0.5 hover:bg-[var(--hf-main-100)]"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
        </span>
      ))}
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="listbox"
          aria-expanded={open}
          className={`${chip} ${idle}`}
          title="Чьих кандидатов показать в этой воронке — можно отметить нескольких. Сбросится на ваших, когда уйдёте из воронки."
        >
          <Users className="h-3.5 w-3.5" aria-hidden="true" />
          Рекрутёры
          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
        {open && (
          <ul
            role="listbox"
            aria-multiselectable="true"
            className="absolute left-0 top-full z-30 mt-1 min-w-[230px] max-h-[320px] overflow-y-auto rounded-lg border border-[color:var(--hf-main-200)] bg-[var(--hf-white)] p-1 shadow-lg"
          >
            <FilterRow
              label="Все рекрутёры"
              count={options?.total ?? null}
              checked={viewOwner === 'all'}
              onClick={() => viewOwner !== 'all' && setViewOwner('all')}
            />
            <li aria-hidden="true" className="my-1 border-t border-[color:var(--hf-main-100)]" />
            {people.map((p) => (
              <FilterRow
                key={p.id}
                label={p.label}
                count={p.count}
                checked={selected.has(p.id)}
                onClick={() => toggle(p.id)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function FilterRow({
  label,
  count,
  checked,
  onClick,
}: {
  label: string;
  count: number | null;
  checked: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        role="option"
        aria-selected={checked}
        onClick={onClick}
        className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs ${
          checked ? 'text-[color:var(--hf-accent)]' : 'text-[var(--hf-main-900)]'
        } hover:bg-[var(--hf-main-50)]`}
      >
        <span
          className={`flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded border ${
            checked
              ? 'border-[color:var(--hf-accent)] bg-[var(--hf-accent)] text-white'
              : 'border-[color:var(--hf-main-300)]'
          }`}
          aria-hidden="true"
        >
          {checked && <Check className="h-3 w-3" />}
        </span>
        <span className="flex-1 truncate">{label}</span>
        {count != null && <span className="text-[var(--hf-main-500)]">{count}</span>}
      </button>
    </li>
  );
}
