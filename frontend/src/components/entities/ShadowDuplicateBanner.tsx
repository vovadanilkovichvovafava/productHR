import { backdropClose } from '@/utils/backdropClose';
import { useState, useEffect, useRef, useCallback } from "react";
import { Loader2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { CandidateAlertCard, type PriorRejection } from "@/components/candidates/priorRejection";
import toast from "react-hot-toast";
import type { KanbanCard } from "@/services/api/candidates";
import type { EntityWithRelations } from "@/types";
import {
  getEntity,
  mergeShadowDuplicate,
  dismissDuplicate,
  getDuplicateCandidates,
  type DuplicateCandidateResult,
  type HiddenDuplicateMeta,
} from "@/services/api/entities";
import { clearCompareFilesCache } from "./CompareResumePreview";
import { STATUS_LABELS } from "@/types";
import {
  CompareTable,
  DupCarousel,
  signalWords,
  type CarouselItem,
  sideFromCard,
  sideFromEntity,
  matchSide,
  matchKindOf,
  type FieldKey,
  type MatchKind,
  type SystemHrTag,
} from "./CandidateCompareCard";

/**
 * Баннер «Похожий кандидат есть в базе» + окно сравнения.
 *
 * Окно (переделано 22.10.2026, владелец: «не нравится, как выглядит»): сверху
 * вкладки похожих анкет («точно» / «возможно N%» / решение), в середине
 * таблица «поле в строку» (CompareTable), внизу — что сделает «Объединить» и
 * три кнопки. Раньше: две карточки рядом с несовпадающими строками, карусель
 * со стрелками И чипами снизу, обрезанная третья карточка у края.
 */

interface ShadowDuplicateBannerProps {
  card: KanbanCard;
  status?: string; // текущий этап открытой карточки (ключ EntityStatus)
  onResolved?: () => void;
  /** «Был отказ» этого человека (useVisiblePriorRejections) — рисуются в той
   *  же карточке, что и дубль: одна плашка вместо двух (22.10.2026). */
  rejections?: PriorRejection[];
}

export default function ShadowDuplicateBanner({ card, status, onResolved, rejections = [] }: ShadowDuplicateBannerProps) {
  const navigate = useNavigate();
  const hiddenId = (card.extra_data?.hidden_duplicate_id as number | undefined) ?? null;
  const meta = (card.extra_data?.hidden_duplicate_meta ?? null) as HiddenDuplicateMeta | null;
  // Красный — только когда совпало НЕСКОЛЬКО признаков личности (level=exact).
  // Одиночное совпадение (только почта, только ФИО, только текст резюме) — жёлтое
  // «возможно тот же человек» с процентом и причинами. Старые флаги без level
  // считаем «возможными», пока карточка не пересчитает их при открытии.
  const isText = meta?.strength === "text";
  const isExact = meta?.level === "exact";
  const bannerReasons = meta?.reasons ?? [];
  const [resolved, setResolved] = useState(false);
  const [open, setOpen] = useState(false);
  // triggerEntity — профиль hiddenId, по которому решается ПОКАЗ баннера (стабилен,
  // не зависит от выбора в карусели).
  const [triggerEntity, setTriggerEntity] = useState<EntityWithRelations | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  // Полный список похожих кандидатов (трек-карусель) + выбранный для сравнения справа.
  const [duplicates, setDuplicates] = useState<DuplicateCandidateResult[]>([]);
  const [selectedDupId, setSelectedDupId] = useState<number | null>(hiddenId);
  // Полные профили ВСЕХ дубликатов в STATE — именно они рендерят трек (карточки
  // въезжают, как только соответствующий профиль подгрузился префетчем).
  const [entities, setEntities] = useState<Record<number, EntityWithRelations>>({});
  // Кэш тех же профилей в ref — для СИНХРОННого сидинга (предвыбор/triggerEntity),
  // чтобы трек не моргал спиннером там, где профиль уже под рукой.
  const entityCache = useRef<Map<number, EntityWithRelations>>(new Map());
  // Решения ПО ПАРАМ (2026-09-15, Эльвира): кнопки действуют только на анкету,
  // открытую справа. Решённые помечаются и пропускаются, окно закрывается само,
  // только когда решены все — раньше решение по последней в карусели закрывало
  // окно, и непролистанные анкеты молча оставались непроверенными.
  const [decisions, setDecisions] = useState<Record<number, "merged" | "dismissed">>({});
  // Карусель сворачивается, когда таблицу прокрутили вниз, и возвращается,
  // когда прокрутили до самого верха (владелец, 24.10.2026: «больше места»).
  // Сворачиваем, только если таблица длиннее окна с запасом на высоту самой
  // карусели — иначе свёрнутая карусель освобождает место, прокрутка
  // обнуляется, карусель разворачивается, и так по кругу.
  const [carouselCollapsed, setCarouselCollapsed] = useState(false);
  const carouselRef = useRef<HTMLDivElement | null>(null);
  const compareScrollRef = useRef<HTMLDivElement | null>(null);
  // Раскрыли руками («сравниваем с: … ▾») внизу таблицы — не сворачиваем
  // обратно, пока человек сам не прокрутит дальше вниз. Иначе раскрытие
  // сдвигало прокрутку, срабатывало сворачивание, и полоса тут же исчезала
  // (владелец, 24.10.2026).
  const keepOpenUntilRef = useRef<number | null>(null);
  const onCompareScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    if (el.scrollTop <= 2) {
      keepOpenUntilRef.current = null;
      setCarouselCollapsed(false);
      return;
    }
    if (keepOpenUntilRef.current != null) {
      if (el.scrollTop < keepOpenUntilRef.current) return;
      keepOpenUntilRef.current = null;
    }
    const spare = el.scrollHeight - el.clientHeight;
    const carouselH = carouselRef.current?.offsetHeight ?? 0;
    if (el.scrollTop > 24 && spare > carouselH + 48) setCarouselCollapsed(true);
  }, []);
  const expandCarousel = useCallback(() => {
    // Пока полоса раскрывается, браузер сам сдвигает прокрутку (на высоту
    // полосы), а клик по тачпаду даёт мелкую прокрутку — считать от позиции
    // ДО раскрытия нельзя: полоса тут же сворачивалась от клика по карточке.
    // Поэтому порог ставим, когда раскрытие закончилось, и с запасом.
    keepOpenUntilRef.current = Number.POSITIVE_INFINITY;
    setCarouselCollapsed(false);
    window.setTimeout(() => {
      if (keepOpenUntilRef.current === Number.POSITIVE_INFINITY) {
        keepOpenUntilRef.current = (compareScrollRef.current?.scrollTop ?? 0) + 200;
      }
    }, 350);
  }, []);

  // Подгружаем профиль дубля сразу (не только по клику «Проверить»), чтобы заранее
  // понять — это реальное совпадение или мусорный/устаревший флаг. Баннер по-прежнему
  // триггерится по hiddenId, поэтому грузим именно его для предпросмотра.
  useEffect(() => {
    if (hiddenId && !triggerEntity) {
      getEntity(hiddenId)
        .then((e) => {
          setTriggerEntity(e);
          // Предзаполняем кэш + STATE загруженным hiddenId, чтобы трек сразу имел
          // профиль предвыбранного дубликата и не перезапрашивал его.
          entityCache.current.set(e.id, e);
          setEntities((prev) => (prev[e.id] ? prev : { ...prev, [e.id]: e }));
        })
        .catch(() => {});
    }
  }, [hiddenId, triggerEntity]);

  // Выбирает дубликат для сравнения + добирает его профиль в STATE/кэш, если
  // префетч ещё не доставил. Трек сам подменит плейсхолдер на карточку, как только
  // entities обновится — отдельный right-спиннер больше не нужен.
  // Объявлено ДО ранних return'ов: на неё ссылаются эффекты карусели ниже.
  const loadSelected = useCallback(async (id: number) => {
    setSelectedDupId(id);
    if (entityCache.current.has(id)) return;
    try {
      const e = await getEntity(id);
      entityCache.current.set(id, e);
      setEntities((prev) => (prev[id] ? prev : { ...prev, [id]: e }));
    } catch {
      toast.error("Не удалось загрузить профиль дубликата");
    }
  }, []);

  // Стрелки клавиатуры листают вкладки похожих анкет.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const pos = duplicates.findIndex((d) => d.entity_id === selectedDupId);
      const next = Math.max(0, Math.min(duplicates.length - 1, pos + (e.key === "ArrowRight" ? 1 : -1)));
      if (next === pos || !duplicates[next]) return;
      e.preventDefault();
      void loadSelected(duplicates[next].entity_id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, duplicates, selectedDupId, loadSelected]);

  // Дубля нет (или решён) — остаётся только отказ, со ссылкой на ту карточку.
  const rejectionOnly = () => {
    const top = rejections[0];
    if (!top) return null;
    const other = top.entity_id !== card.id ? top.entity_id : null;
    return (
      <div className="mb-3">
        <CandidateAlertCard
          rejections={rejections}
          actionLabel={other ? (top.archived ? "Открыть из архива" : "Открыть ту карточку") : undefined}
          onAction={other ? () => navigate(`/all-candidates?entity=${other}${top.archived ? "&archived=1" : ""}`) : undefined}
        />
      </div>
    );
  };

  if (!hiddenId || resolved) return rejectionOnly();

  // Профиль ВЫБРАННОГО в треке дубликата (центрированная правая карточка). Дерайвится
  // из entities-state по selectedDupId; до подгрузки — fallback на triggerEntity
  // (hiddenId), чтобы «Совпадение по»/right/matched работали с первого кадра.
  const archived: EntityWithRelations | null =
    (selectedDupId != null ? entities[selectedDupId] : undefined) ?? triggerEntity ?? null;

  const openModal = async () => {
    // Резюме могли догрузить с прошлой проверки — читаем файлы заново.
    clearCompareFilesCache();
    setDecisions({});
    setOpen(true);
    setLoading(true);
    try {
      // Тянем ВСЕХ похожих кандидатов (включая архив) для карусели.
      const list = await getDuplicateCandidates(card.id, true);
      setDuplicates(list);
      // Префетч полных профилей ВСЕХ дубликатов в фоне (не ждём перед показом
      // модалки) — каждый въезжает в трек, как только entities-state обновится.
      try {
        void Promise.allSettled(
          list.map((d) =>
            entityCache.current.has(d.entity_id)
              ? Promise.resolve()
              : getEntity(d.entity_id)
                  .then((e) => {
                    entityCache.current.set(d.entity_id, e);
                    setEntities((prev) => (prev[d.entity_id] ? prev : { ...prev, [d.entity_id]: e }));
                  })
                  .catch(() => {}),
          ),
        );
      } catch {
        /* префетч best-effort — не блокирует и не ломает открытие модалки */
      }
      // Предвыбор: существующий hiddenId, если он в списке; иначе — самый
      // вероятный (список отсортирован по убыванию confidence на бэке).
      const preset =
        list.find((d) => d.entity_id === hiddenId)?.entity_id ?? list[0]?.entity_id ?? hiddenId;
      if (preset != null) {
        await loadSelected(preset);
      }
    } catch {
      // Если список не получили — не регрессируем: центрируем одиночный hiddenId
      // (archived дерайвится из triggerEntity/entities, поэтому достаточно выбрать id).
      setSelectedDupId(hiddenId);
      if (!entityCache.current.has(hiddenId)) {
        try {
          const e = triggerEntity ?? (await getEntity(hiddenId));
          entityCache.current.set(hiddenId, e);
          setEntities((prev) => (prev[hiddenId] ? prev : { ...prev, [hiddenId]: e }));
        } catch {
          toast.error("Не удалось загрузить профиль дубликата");
        }
      }
    } finally {
      setLoading(false);
    }
  };

  // После решения по текущей паре — к следующей НЕрешённой (сначала вперёд по
  // карусели, потом назад). Нерешённых нет — всё проверено, закрываем окно.
  const afterDecision = (targetId: number, kind: "merged" | "dismissed") => {
    const next = { ...decisions, [targetId]: kind };
    setDecisions(next);
    const pos = duplicates.findIndex((d) => d.entity_id === targetId);
    const undecided = (d: DuplicateCandidateResult) => !next[d.entity_id];
    const forward = duplicates.slice(pos + 1).find(undecided);
    const backward = duplicates.slice(0, Math.max(pos, 0)).reverse().find(undecided);
    const nextDup = forward ?? backward;
    if (nextDup) {
      loadSelected(nextDup.entity_id);
    } else {
      setOpen(false);
      setResolved(true);
      onResolved?.();
    }
  };

  const handleMerge = async () => {
    const targetId = selectedDupId ?? hiddenId;
    if (targetId == null || decisions[targetId]) return;
    setBusy(true);
    try {
      await mergeShadowDuplicate(card.id, targetId);
      toast.success("Анкета объединена с новым кандидатом");
      afterDecision(targetId, "merged");
    } catch (err) {
      const detail = (err as { response?: { status?: number; data?: { detail?: string } } })?.response;
      toast.error(detail?.status === 409 && detail.data?.detail ? detail.data.detail : "Не удалось объединить профили");
    } finally {
      setBusy(false);
    }
  };

  const handleDismiss = async () => {
    const targetId = selectedDupId ?? hiddenId;
    if (targetId == null || decisions[targetId]) return;
    setBusy(true);
    try {
      await dismissDuplicate(card.id, targetId);
      toast.success("Отмечено: эта анкета — другой человек");
      afterDecision(targetId, "dismissed");
    } catch {
      toast.error("Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  };

  // «Закрыть» при частично решённых: решения сохранены, остальные ждут —
  // говорим прямо, чтобы не казалось, что закрытие разделило всех.
  const closeModal = () => {
    const decidedCount = Object.keys(decisions).length;
    const left = duplicates.length - decidedCount;
    if (decidedCount > 0 && left > 0) {
      toast(`Решения сохранены. Ещё не проверено анкет: ${left}`);
    }
    setOpen(false);
  };

  const left = sideFromCard(card, status);
  const right = archived ? sideFromEntity(archived) : null;

  // Сигналы ВЫБРАННОЙ пары — общий источник подсветки для обеих карточек:
  // подсвечиваем ровно те поля, из-за которых бэк считает пару дублем, и отличаем
  // точное совпадение от частичного. matchSide остаётся фолбэком, пока список
  // дублей ещё не пришёл.
  const selectedSignals = duplicates.find((d) => d.entity_id === selectedDupId)?.signals;
  const matched = (key: FieldKey | "name"): MatchKind =>
    matchKindOf(selectedSignals, key, () => matchSide(left, right, key));

  // Баннер показываем только если есть triggerEntity (найден возможный дубликат)
  if (!triggerEntity) return rejectionOnly();

  const selectedDecision = selectedDupId != null ? decisions[selectedDupId] : undefined;
  const undecidedCount = duplicates.filter((d) => !decisions[d.entity_id]).length;
  const selectedDup = duplicates.find((d) => d.entity_id === selectedDupId);
  const rightId = selectedDupId ?? hiddenId;
  const hrTags = (extra: unknown): SystemHrTag[] | undefined => {
    const t = (extra as { system_hr_tags?: unknown } | null | undefined)?.system_hr_tags;
    return Array.isArray(t) ? (t as SystemHrTag[]) : undefined;
  };

  return (
    <>
      {/* Одна мягкая карточка над action-баром: отказ + дубль + «Сравнить». */}
      <div className="mb-3">
        <CandidateAlertCard
          rejections={rejections}
          duplicate={{ exact: isExact, confidence: meta?.confidence, text: isText, reasons: bannerReasons }}
          actionLabel="Сравнить"
          onAction={openModal}
        />
      </div>

      {/* Окно сравнения */}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          {...backdropClose(() => !busy && closeModal())}
        >
          {loading ? (
            <div className="text-white flex items-center justify-center" onClick={(e) => e.stopPropagation()}>
              <Loader2 className="w-8 h-8 animate-spin" />
            </div>
          ) : (
            <div
              className="bg-[#f2f2f2] rounded-2xl shadow-2xl flex flex-col w-full max-w-6xl max-h-[94vh] overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Карусель похожих анкет — единственная навигация. */}
              {/* Карусель компактная (владелец, 24.10.2026: крупная съедала место
                  у самого сравнения; вид карточки при этом нравился — оставлен). */}
              <div className="shrink-0 px-5 pt-3 pb-2.5">
                <div className={`flex items-center gap-2 transition-[margin] duration-200 ${carouselCollapsed ? "mb-0" : "mb-2"}`}>
                  <span className="text-[15px] font-semibold text-slate-900">Похожие анкеты</span>
                  <span className="text-[12px] text-slate-400">
                    {duplicates.length > 1
                      ? `${duplicates.length} · ${undecidedCount > 0 ? `не проверено ${undecidedCount}` : "все проверены"}`
                      : ""}
                  </span>
                  {carouselCollapsed && (
                    <button
                      type="button"
                      onClick={expandCarousel}
                      className="min-w-0 truncate rounded-full bg-white px-2.5 py-0.5 text-[12px] text-slate-600 hover:text-slate-900"
                      title="Показать похожие анкеты"
                    >
                      сравниваем с: {(rightId != null && (duplicates.find((d) => d.entity_id === rightId)?.entity_name || entities[rightId]?.name)) || "—"} ▾
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => !busy && closeModal()}
                    className="ml-auto rounded-lg p-1.5 text-slate-400 hover:bg-white hover:text-slate-700"
                    aria-label="Закрыть"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <div
                  ref={carouselRef}
                  className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out ${carouselCollapsed ? "grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] opacity-100"}`}
                  aria-hidden={carouselCollapsed}
                >
                <div className="min-h-0 overflow-hidden">
                <DupCarousel
                  items={(duplicates.length ? duplicates : [{ entity_id: hiddenId, entity_name: archived?.name || "", confidence: meta?.confidence ?? 0, level: meta?.level } as DuplicateCandidateResult]).map((d): CarouselItem => {
                    const ent = entities[d.entity_id] as (EntityWithRelations & { is_archived?: boolean }) | undefined;
                    const st = (ent?.status as string | undefined) || "";
                    return {
                      id: d.entity_id,
                      name: d.entity_name || ent?.name || `Анкета ${d.entity_id}`,
                      confidence: d.confidence,
                      level: d.level,
                      strength: d.strength,
                      reason: signalWords(d.signals),
                      decision: decisions[d.entity_id],
                      details: [
                        ent?.position,
                        ((ent as unknown as { city?: string } | undefined)?.city) || ((ent?.extra_data as { city?: string } | undefined)?.city),
                        ent?.created_at ? `добавлена ${new Date(ent.created_at).toLocaleDateString("ru", { day: "numeric", month: "short", year: "numeric" })}` : null,
                      ].filter(Boolean).join(" · ") || undefined,
                      badge: ent?.is_archived
                        ? { text: "архив", tone: "gray" }
                        : st === "rejected"
                          ? { text: "Был отказ", tone: "red" }
                          : st
                            ? { text: (STATUS_LABELS as Record<string, string>)[st] || st, tone: "blue" }
                            : null,
                    };
                  })}
                  selectedId={rightId}
                  onSelect={(id) => id !== selectedDupId && void loadSelected(id)}
                />
                </div>
                </div>
              </div>

              <div ref={compareScrollRef} className="flex-1 overflow-y-auto px-5 pb-4" onScroll={onCompareScroll}>
                <CompareTable
                  left={{
                    side: left,
                    entityId: card.id,
                    caption: "Открыта сейчас",
                    createdAt: card.created_at,
                    createdBy: card.recruiter_name,
                    vacancies: hrTags(card.extra_data),
                    extraData: card.extra_data as Record<string, unknown> | undefined,
                  }}
                  right={right && rightId != null ? {
                    side: right,
                    entityId: rightId,
                    caption: "похожая анкета",
                    archived: Boolean((archived as unknown as { is_archived?: boolean })?.is_archived),
                    createdAt: archived?.created_at,
                    createdBy: (archived as unknown as { owner_name?: string | null })?.owner_name,
                    vacancies: hrTags(archived?.extra_data),
                    extraData: archived?.extra_data as Record<string, unknown> | undefined,
                  } : null}
                  matched={matched}
                  signals={selectedDup?.signals}
                  level={selectedDup?.level ?? meta?.level}
                />
              </div>

              <div className="shrink-0 flex items-center gap-3 border-t border-slate-200 bg-white px-5 py-3 flex-wrap">
                <span className="flex-1 min-w-[240px] text-[13px] text-slate-500">
                  {selectedDecision
                    ? "По этой анкете решение уже принято — выберите непроверенную вкладку сверху."
                    : <>«Объединить»: останется открытая карточка (ID {card.id}). Воронки, история, комментарии и отказы из ID {rightId} переедут в неё.</>}
                </span>
                <button
                  disabled={busy}
                  onClick={closeModal}
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  Закрыть
                </button>
                <button
                  disabled={busy || !!selectedDecision}
                  onClick={handleDismiss}
                  className="rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  Это разные люди
                </button>
                <button
                  disabled={busy || !!selectedDecision}
                  onClick={handleMerge}
                  className="inline-flex items-center gap-2 rounded-lg bg-[var(--hf-cyan-700)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
                >
                  {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                  Объединить
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
