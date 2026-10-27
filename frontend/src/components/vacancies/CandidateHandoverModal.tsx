// ================================================================
// CandidateHandoverModal — передача кандидатов уходящего рекрутёра (админы HR).
//
// Сотрудник уходит → его аккаунт удалят, всё владение обнулится. Здесь админ
// ПЕРЕД удалением раздаёт его воронки и остальных его кандидатов.
// С 26.10.2026 (владелец):
//  • «Отдать всё одному человеку» — одним выбором вместо каждой строки;
//  • если у получателя уже есть такая же воронка (то же название), кандидаты
//    складываются в неё, а не появляется вторая одинаковая; повторы
//    объединяются (остаётся этап, до которого человека довели позже);
//  • перед «Передать» — итог от сервера (dry_run): кто сколько получит и кто
//    уже есть во вливаемой воронке; после — отчёт; окна браузера (confirm) нет;
//  • строка «Без воронки»: раньше эти кандидаты не передавались вовсе.
// Тексты — простым языком, без длинных тире; имена только в именительном
// падеже (склонять их мы не умеем): «Мария получит 64 кандидата».
// ================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRightLeft, Briefcase, Loader2, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { getOrgMembers, getHandoverSummary, reassignSplit } from '@/services/api';
import type { HandoverSummary, ReassignSplitResult } from '@/services/api/auth';
import { getAssignableUsers } from '@/services/api/vacancies';
import { STAGE_LABEL_BY_STAGE } from '@/constants/hrStages';
import { backdropClose } from '@/utils/backdropClose';
import { pluralRu } from '@/utils/plural';
import { getErrorDetail } from '@/utils';

type Person = { id: number; name: string };
type Funnel = HandoverSummary['funnels'][number];

const candidatesWord = (n: number) => `${n} ${pluralRu(n, 'кандидат', 'кандидата', 'кандидатов')}`;
const stageLabel = (s: string | null) =>
  (s && (STAGE_LABEL_BY_STAGE as Record<string, string>)[s]) || s || '';

/** Такие же воронки получателя (он в них работает), открытые первыми.
 *  Если получатель уже работает в самой этой воронке — она и так его,
 *  второй копии не появится, сливать нечего. Отсюда же следует, что две копии
 *  одного получателя не могут слиться друг в друга. */
export function matchesFor(funnel: Funnel, recipientId: number) {
  if (funnel.participants.includes(recipientId)) return [];
  return funnel.matches
    .filter((m) => m.participants.includes(recipientId))
    .sort((a, b) => Number(b.status !== 'closed') - Number(a.status !== 'closed') || b.candidates - a.candidates);
}

export default function CandidateHandoverModal({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone?: () => void;
}) {
  const [leavers, setLeavers] = useState<Person[]>([]);
  const [recipients, setRecipients] = useState<Person[]>([]);
  const [fromId, setFromId] = useState<number | ''>('');
  const [summary, setSummary] = useState<HandoverSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [busy, setBusy] = useState(false);
  // vacancy_id → получатель; ключ 'pool' → кандидаты без воронки.
  const [assign, setAssign] = useState<Record<string, number | ''>>({});
  // vacancy_id → в какую воронку получателя сложить ('' — оставить отдельной).
  const [mergeInto, setMergeInto] = useState<Record<string, number | ''>>({});
  const [preview, setPreview] = useState<ReassignSplitResult | null>(null);
  const [openOverlap, setOpenOverlap] = useState<number | null>(null);
  const [done, setDone] = useState<ReassignSplitResult | null>(null);
  const previewSeq = useRef(0);

  useEffect(() => {
    // Получатели — те, кому можно передавать (рекрутёры и админы, без
    // наблюдателей; сервер проверяет то же самое). Уходящий — они же плюс
    // остальные из списка организации: админу этот список приходит не целиком
    // (только его отдел), поэтому складываем оба.
    Promise.allSettled([getAssignableUsers({ includeOwners: true }), getOrgMembers()]).then(([a, m]) => {
      const fromAssignable = a.status === 'fulfilled' ? a.value.map((u) => ({ id: u.id, name: u.name })) : [];
      const fromMembers = m.status === 'fulfilled'
        ? m.value.filter((x) => ['owner', 'admin', 'hr'].includes(x.role)).map((x) => ({ id: x.user_id, name: x.user_name }))
        : [];
      if (a.status === 'rejected' && m.status === 'rejected') toast.error('Не удалось загрузить рекрутёров');
      setRecipients(fromAssignable);
      const byId = new Map<number, Person>();
      [...fromAssignable, ...fromMembers].forEach((p) => byId.set(p.id, p));
      setLeavers([...byId.values()].sort((x, y) => x.name.localeCompare(y.name, 'ru')));
    });
  }, []);

  useEffect(() => {
    setSummary(null);
    setAssign({});
    setMergeInto({});
    setPreview(null);
    if (fromId === '') return;
    setLoadingSummary(true);
    getHandoverSummary(Number(fromId))
      .then(setSummary)
      .catch(() => toast.error('Не удалось загрузить воронки рекрутёра'))
      .finally(() => setLoadingSummary(false));
  }, [fromId]);

  const fromName = leavers.find((r) => r.id === fromId)?.name || '';
  const nameOf = (id: number) => recipients.find((r) => r.id === id)?.name || 'Получатель';
  const choices = recipients.filter((r) => r.id !== fromId);

  const pickRecipient = (key: string, to: number | '') => {
    setAssign((prev) => ({ ...prev, [key]: to }));
    if (key === 'pool' || !summary) return;
    // По умолчанию складываем в такую же воронку, если она у получателя одна.
    const f = summary.funnels.find((x) => String(x.vacancy_id) === key);
    const m = f && to !== '' ? matchesFor(f, to) : [];
    setMergeInto((prev) => ({ ...prev, [key]: m.length === 1 ? m[0].vacancy_id : '' }));
  };

  const giveAllTo = (to: number | '') => {
    if (!summary) return;
    summary.funnels.forEach((f) => pickRecipient(String(f.vacancy_id), to));
    if (summary.pool_candidates > 0) pickRecipient('pool', to);
  };

  const assignments = useMemo(
    () =>
      (summary?.funnels || [])
        .filter((f) => assign[String(f.vacancy_id)])
        .map((f) => ({
          vacancy_id: f.vacancy_id,
          to_user_id: Number(assign[String(f.vacancy_id)]),
          merge_into_vacancy_id: mergeInto[String(f.vacancy_id)] || null,
        })),
    [summary, assign, mergeInto],
  );
  const poolTo = assign.pool ? Number(assign.pool) : null;
  const hasChoice = assignments.length > 0 || poolTo !== null;

  // Итог «что будет» — от сервера, без изменений; пересчитывается на каждый выбор.
  useEffect(() => {
    if (fromId === '' || !hasChoice) {
      setPreview(null);
      return;
    }
    const seq = ++previewSeq.current;
    const t = window.setTimeout(() => {
      reassignSplit(Number(fromId), assignments, poolTo, true)
        .then((r) => seq === previewSeq.current && setPreview(r))
        .catch(() => seq === previewSeq.current && setPreview(null));
    }, 250);
    return () => window.clearTimeout(t);
  }, [fromId, assignments, poolTo, hasChoice]);

  const submit = async () => {
    if (fromId === '' || !hasChoice) return;
    setBusy(true);
    try {
      const r = await reassignSplit(Number(fromId), assignments, poolTo);
      setDone(r);
      onDone?.();
    } catch (e) {
      toast.error(getErrorDetail(e, 'Не удалось передать, попробуйте ещё раз'));
    } finally {
      setBusy(false);
    }
  };

  const selectCls =
    'px-3 py-2 rounded-lg text-sm bg-[var(--hf-bg-panel)] border border-[color:var(--hf-main-200)] text-[var(--hf-main-900)] focus:outline-none focus:border-[color:var(--hf-cyan-500)] disabled:opacity-50';
  const recipientSelect = (key: string, value: number | '', onChange: (v: number | '') => void, placeholder = 'Не передавать') => (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
      disabled={busy}
      className={`${selectCls} w-full sm:w-[190px]`}
      aria-label={key === 'all' ? 'Отдать всё одному человеку' : 'Кому передать'}
    >
      <option value="">{placeholder}</option>
      {choices.map((r) => (
        <option key={r.id} value={r.id}>{r.name}</option>
      ))}
    </select>
  );

  const perRecipient = Object.entries(preview?.per_recipient || {}).filter(([, n]) => n > 0);

  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 p-4" {...backdropClose(() => !busy && onClose())}>
      <div className="w-[640px] max-w-full max-h-[88vh] flex flex-col rounded-2xl bg-[var(--hf-bg-body,#fff)] border border-[color:var(--hf-main-200)] shadow-xl">
        <div className="flex items-start justify-between gap-3 p-5 sm:p-6 pb-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 mb-1">
              <ArrowRightLeft className="w-5 h-5 shrink-0 text-[var(--hf-cyan-700)]" />
              <h2 className="text-base font-semibold text-[var(--hf-main-900)]">
                {fromName ? `Кому отдать кандидатов: ${fromName}` : 'Передать кандидатов уходящего рекрутёра'}
              </h2>
            </div>
            <p className="text-sm text-[var(--hf-main-600)]">
              Сделайте это до удаления аккаунта, иначе его кандидаты останутся ни за кем.
            </p>
          </div>
          <button onClick={onClose} disabled={busy} className="p-1 rounded-lg hover:bg-[var(--hf-main-100)] text-[var(--hf-main-500)]" aria-label="Закрыть">
            <X className="w-4 h-4" />
          </button>
        </div>

        {done ? (
          <div className="px-5 sm:px-6 pb-6">
            <p className="text-[15px] font-semibold text-[var(--hf-main-900)] mb-2">Готово</p>
            <ul className="space-y-1 text-sm text-[var(--hf-main-700)]">
              {Object.entries(done.per_recipient || {}).filter(([, n]) => n > 0).map(([uid, n]) => (
                <li key={uid}>{nameOf(Number(uid))} получит {candidatesWord(n)}</li>
              ))}
              {done.merges.map((m) => (
                <li key={m.vacancy_id}>Кандидаты сложены в воронку «{m.into_title}»</li>
              ))}
            </ul>
            <div className="flex justify-end mt-5">
              <button onClick={onClose} className="px-5 py-2 rounded-lg text-sm font-medium bg-[var(--hf-cyan-700)] text-white hover:opacity-90">
                Закрыть
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="px-5 sm:px-6">
              <label className="block text-xs font-medium text-[var(--hf-main-600)] mb-1.5" htmlFor="handover-from">
                Чьих кандидатов передаём
              </label>
              <select
                id="handover-from"
                value={fromId}
                onChange={(e) => setFromId(e.target.value ? Number(e.target.value) : '')}
                disabled={busy}
                className={`${selectCls} w-full`}
              >
                <option value="">Выберите рекрутёра</option>
                {leavers.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
            </div>

            <div className="flex-1 overflow-y-auto px-5 sm:px-6 py-4 mt-1">
              {fromId === '' ? (
                <div className="text-sm text-[var(--hf-main-400)] py-6 text-center">Выберите рекрутёра, и появятся его воронки.</div>
              ) : loadingSummary ? (
                <div className="flex items-center gap-2 text-[var(--hf-main-500)] py-4">
                  <Loader2 className="w-4 h-4 animate-spin" /> Загружаем воронки…
                </div>
              ) : summary && (summary.funnels.length > 0 || summary.pool_candidates > 0) ? (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-[var(--hf-bg-panel)] px-3 py-2.5">
                    <span className="text-sm text-[var(--hf-main-900)]">Отдать всё одному человеку</span>
                    {recipientSelect('all', '', giveAllTo, 'Выберите')}
                  </div>

                  {summary.funnels.map((f) => {
                    const key = String(f.vacancy_id);
                    const to = assign[key] ?? '';
                    const matches = to === '' ? [] : matchesFor(f, Number(to));
                    const into = mergeInto[key] ?? '';
                    return (
                      <div key={key} className="rounded-xl border border-[color:var(--hf-main-200)] p-3">
                        <div className="flex flex-wrap items-center gap-3">
                          <Briefcase className="w-4 h-4 text-[var(--hf-main-400)] shrink-0" />
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-[var(--hf-main-900)] truncate">{f.title}</div>
                            <div className="text-xs text-[var(--hf-main-500)]">
                              {candidatesWord(f.candidates)}
                              {f.status === 'closed' ? ' · закрыта' : ''}
                            </div>
                          </div>
                          {recipientSelect(key, to, (v) => pickRecipient(key, v))}
                        </div>
                        {to !== '' && matches.length > 0 && (
                          <div className="mt-2.5 rounded-lg bg-[var(--hf-status-green-bg,#eaf3de)] px-3 py-2 text-[13px] text-[var(--hf-main-900)]">
                            {matches.length === 1
                              ? <>Такая же воронка «{matches[0].title}» уже есть, её ведёт {nameOf(Number(to))}. Сложить кандидатов туда?</>
                              : <>Таких же воронок несколько. Куда сложить кандидатов?</>}
                            <div className="mt-2 flex flex-wrap gap-2">
                              {matches.map((m) => (
                                <button
                                  key={m.vacancy_id}
                                  type="button"
                                  onClick={() => setMergeInto((p) => ({ ...p, [key]: m.vacancy_id }))}
                                  className={`rounded-lg border px-2.5 py-1 text-[12.5px] ${into === m.vacancy_id ? 'border-[color:var(--hf-cyan-700)] bg-white font-medium' : 'border-[color:var(--hf-main-200)] bg-white/60'}`}
                                >
                                  {matches.length === 1 ? 'Да, сложить в одну' : `«${m.title}» · ${candidatesWord(m.candidates)}${m.status === 'closed' ? ' · закрыта' : ''}`}
                                </button>
                              ))}
                              <button
                                type="button"
                                onClick={() => setMergeInto((p) => ({ ...p, [key]: '' }))}
                                className={`rounded-lg border px-2.5 py-1 text-[12.5px] ${into === '' ? 'border-[color:var(--hf-cyan-700)] bg-white font-medium' : 'border-[color:var(--hf-main-200)] bg-white/60'}`}
                              >
                                Нет, оставить отдельно
                              </button>
                            </div>
                          </div>
                        )}
                        {to !== '' && matches.length === 0 && (
                          <p className="mt-2 text-xs text-[var(--hf-main-500)]">
                            {f.participants.includes(Number(to))
                              ? 'Получатель уже работает в этой воронке, кандидаты просто перейдут к нему.'
                              : 'Такой воронки у получателя нет, эта станет его.'}
                          </p>
                        )}
                      </div>
                    );
                  })}

                  {summary.pool_candidates > 0 && (
                    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[color:var(--hf-main-200)] p-3">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-[var(--hf-main-900)]">Без воронки</div>
                        <div className="text-xs text-[var(--hf-main-500)]">{candidatesWord(summary.pool_candidates)}</div>
                      </div>
                      {recipientSelect('pool', assign.pool ?? '', (v) => pickRecipient('pool', v))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-[var(--hf-main-400)] py-6 text-center">У этого рекрутёра нет кандидатов для передачи.</div>
              )}
            </div>

            <div className="border-t border-[color:var(--hf-main-200)] p-5 sm:p-6 pt-3">
              {perRecipient.length > 0 && (
                <div className="mb-3 space-y-1" data-testid="handover-summary">
                  {perRecipient.map(([uid, n]) => (
                    <p key={uid} className="text-[14px] font-medium text-[var(--hf-main-900)]">
                      {nameOf(Number(uid))} получит {candidatesWord(n)}
                    </p>
                  ))}
                  {(preview?.merges || []).filter((m) => m.overlapping.length > 0).map((m) => (
                    <div key={m.vacancy_id} className="text-[13px] text-[var(--hf-main-600)]">
                      {m.overlapping.length} уже есть в воронке «{m.into_title}», их карточки объединятся.{' '}
                      <button type="button" className="text-[var(--hf-cyan-700)] hover:underline" onClick={() => setOpenOverlap(openOverlap === m.vacancy_id ? null : m.vacancy_id)}>
                        {openOverlap === m.vacancy_id ? 'Скрыть' : 'Показать'}
                      </button>
                      {openOverlap === m.vacancy_id && (
                        <div className="mt-2 rounded-lg bg-[var(--hf-bg-panel)] p-3">
                          <p className="mb-1.5 text-[13px] font-medium text-[var(--hf-main-900)]">Уже есть в воронке «{m.into_title}»</p>
                          {m.overlapping.map((o) => (
                            <div key={o.entity_id} className="flex justify-between gap-3 py-0.5">
                              <span className="text-[var(--hf-main-900)]">{o.name || `Кандидат ${o.entity_id}`}</span>
                              <span>{stageLabel(o.stage)}</span>
                            </div>
                          ))}
                          <p className="mt-2 text-xs text-[var(--hf-main-500)]">
                            Карточки объединятся в одну. Останется этап, указанный справа. Комментарии и история сохранятся.
                          </p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <div className="flex justify-end gap-2">
                <button onClick={onClose} disabled={busy} className="px-4 py-2 rounded-lg text-sm text-[var(--hf-main-600)] hover:bg-[var(--hf-main-100)]">
                  Отмена
                </button>
                <button
                  onClick={submit}
                  disabled={busy || !hasChoice}
                  className="px-5 py-2 rounded-lg text-sm font-medium bg-[var(--hf-cyan-700)] text-white hover:opacity-90 disabled:opacity-40 inline-flex items-center gap-2"
                >
                  {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                  Передать
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
