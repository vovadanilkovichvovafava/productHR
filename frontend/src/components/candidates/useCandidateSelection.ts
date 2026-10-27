import { startTransition, useCallback, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import type { useLiveSearchParams } from "@/hooks/useLiveSearchParams";
import type { KanbanBoardResponse, KanbanCard } from "@/services/api/candidates";
import { getEntity } from "@/services/api/entities";
import { STATUS_LABELS } from "@/types";
import { calculateAge } from "@/utils/date";
import {
  cardAfterSearchChange,
  computeEntityParamUpdate,
  shouldAdoptUrlEntity,
  urlLeadsSelection,
} from "@/utils/candidateUrl";
import { entityToKanbanCard, type VisibleCard } from "@/components/entities/candidateDetail/model";

// Какой кандидат открыт справа на «Все кандидаты» и как это связано с адресом
// (?entity=, разовые ?edit=1 / ?tab=anketa / ?archived=1). Вынесено из
// AllCandidatesPage (20.10.2026) БЕЗ изменения поведения: здесь живут правила,
// которые ломались чаще всего («справа чужая карточка», «ссылка из расширения
// открыла не того», «фоновое обновление выкинуло из карточки»), — теперь они в
// одном месте и под тестами (__tests__/useCandidateSelection.test.ts).

export interface CandidateSelectionParams {
  board: KanbanBoardResponse | null;
  /** Доска получена под другой запрос, чем в поле поиска. */
  boardStale: boolean;
  /** Карточки, которые сейчас видны в списке слева. */
  filteredCards: VisibleCard[];
  /** Контекст выбора, который задаёт ЧЕЛОВЕК: вкладка | скоуп | поиск. */
  activeTab: string;
  scope: string;
  search: string;
  searchParams: URLSearchParams;
  /** Сеттер из useLiveSearchParams: правит ЖИВОЙ адрес, а не снимок рендера. */
  setSearchParams: ReturnType<typeof useLiveSearchParams>[1];
  /** Ссылка просит открыть окно «Редактировать» (?edit=1). */
  onEditRequested: () => void;
  /** Ссылка просит открыть вкладку «Анкета» (?tab=anketa). */
  onAnketaRequested: () => void;
}

export function useCandidateSelection(p: CandidateSelectionParams) {
  const { board, boardStale, filteredCards, searchParams, setSearchParams } = p;
  const [selectedCard, setSelectedCard] = useState<KanbanCard | null>(null);
  const [selectedStatus, setSelectedStatus] = useState("");

  // Колбэки страницы — через ref: эффект ниже не должен перезапускаться от
  // того, что страница пересоздала свои обработчики.
  const onEditRef = useRef(p.onEditRequested);
  onEditRef.current = p.onEditRequested;
  const onAnketaRef = useRef(p.onAnketaRequested);
  onAnketaRef.current = p.onAnketaRequested;

  // Клик по карточке: выбираем + ПУШИМ ?entity= в историю, чтобы «Назад/Вперёд»
  // листали кандидатов. Зеркало ниже (replace + no-op guard) второй записи не
  // даёт; авто-выбор и диплинк — на replace (без спама историей).
  const openCandidate = useCallback((card: KanbanCard, status: string) => {
    setSelectedCard(card);
    setSelectedStatus(status);
    setSearchParams((prev) => {
      if (prev.get("entity") === String(card.id)) return prev;
      const next = new URLSearchParams(prev);
      next.set("entity", String(card.id));
      next.delete("edit");
      next.delete("archived");
      next.delete("tab");
      return next;
    }, { replace: false });
  }, [setSearchParams]);

  const entityParam = searchParams.get("entity");
  const editParam = searchParams.get("edit");
  const archivedParam = searchParams.get("archived");
  const tabParam = searchParams.get("tab");

  // Функциональная форма setSearchParams → колбэк СТАБИЛЕН. Иначе он
  // пересоздаётся на каждой смене URL, а эффект авто-выбора (где он в deps)
  // перезапускается — лишний «churn» при каждом клике.
  const clearCandidateDeepLink = useCallback(() => {
    setSearchParams((prev) => {
      if (!prev.has("entity") && !prev.has("edit") && !prev.has("archived") && !prev.has("tab")) return prev;
      const next = new URLSearchParams(prev);
      next.delete("entity");
      next.delete("edit");
      next.delete("archived");
      next.delete("tab");
      return next;
    }, { replace: true });
  }, [setSearchParams]);
  // Как clearCandidateDeepLink, но СОХРАНЯЕТ entity (ссылка на профиль остаётся в
  // адресной строке) — гасим только разовые триггеры edit/tab/archived.
  const consumeOneShotParams = useCallback(() => {
    setSearchParams((prev) => {
      if (!prev.has("edit") && !prev.has("tab") && !prev.has("archived")) return prev;
      const next = new URLSearchParams(prev);
      next.delete("edit");
      next.delete("tab");
      next.delete("archived");
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  // id только что добавленного. Его ещё нет на доске (список догружается), и
  // открытие «по id» сопровождалось тостом «Карточка открыта отдельно…» —
  // неправда, он просто не успел подгрузиться.
  const justCreatedRef = useRef<number | null>(null);
  // Чтобы не тянуть entity повторно после неудачной попытки выбора.
  const entityFetchTriedRef = useRef<number | null>(null);
  // id кандидата, которого сейчас открываем по ссылке. Пока не разрешён —
  // зеркало «выбор → ?entity=» молчит, чтобы адрес не уехал на прошлую карточку.
  const deepLinkPendingRef = useRef<number | null>(null);
  // Предыдущий выбранный id — чтобы зеркало URL отличало настоящее закрытие
  // (selected->null) от ещё не завершённого диплинка (null->null).
  const prevSelectedIdRef = useRef<number | null>(null);
  // Предыдущий выбранный id ДЛЯ эффекта авто-выбора (отдельно от зеркала) — чтобы
  // отличать смену выбора (клик) от смены URL и не «бодаться» за фокус.
  const prevAutoSelIdRef = useRef<number | null>(null);
  // Контекст выбора — вкладка / скоуп / поиск. По нему отличаем «человек сам
  // сменил фильтр» от «прилетело фоновое обновление доски» (поллинг 15с). Во
  // втором случае трогать открытый профиль нельзя: рекрутёра выкидывало из
  // карточки прямо во время правки имени при активном поиске.
  const prevSelectionCtxRef = useRef<string | null>(null);
  // Запрос, под который в последний раз выбиралась карточка. Смена ПОИСКА —
  // единственная смена фильтра, которая сама карточку не сбрасывает (клик по
  // вкладке делает setSelectedCard(null) явно).
  const prevSearchForSelectionRef = useRef<string | null>(null);

  // Последние значения контекста — в ref: activeTab/scope/search намеренно НЕ в
  // deps эффекта. Он должен просыпаться только на filteredCards/board, иначе смена
  // поиска запустит его дважды — до и после перезагрузки доски — и первый проход
  // «съест» contextChanged.
  const ctxRef = useRef({ activeTab: p.activeTab, scope: p.scope, search: p.search });
  ctxRef.current = { activeTab: p.activeTab, scope: p.scope, search: p.search };

  useEffect(() => {
    if (!board || boardStale) return;
    const { activeTab, scope, search } = ctxRef.current;
    // Человек поменял запрос (не первый проход и не фоновое обновление: пока
    // доска не догнала запрос, сюда не доходим — boardStale выше).
    const searchChanged =
      prevSearchForSelectionRef.current !== null &&
      prevSearchForSelectionRef.current !== search;
    prevSearchForSelectionRef.current = search;
    // Гонка «клик vs URL»: клик ставит selectedCard напрямую, зеркало дописывает
    // ?entity= на тик позже. selChanged=true → менялся ВЫБОР (клик), а URL ещё
    // старый → НЕ возвращаем фокус на прошлую карточку.
    const selId = selectedCard?.id ?? null;
    const selChanged = selId !== prevAutoSelIdRef.current;
    prevAutoSelIdRef.current = selId;
    if (entityParam) {
      if (archivedParam === "1") return; // архивного открывает отдельный эффект ниже
      const entityId = parseInt(entityParam);
      if (Number.isNaN(entityId)) return;
      // Открытый кандидат не попал в выдачу НОВОГО запроса — справа ему не место
      // (Мария, 09.10.2026). Пусто — закрываем профиль, есть находки — первую.
      // Только на смене запроса: диплинк из расширения и фоновое обновление во
      // время правки имени карточку не трогают.
      const afterSearch =
        selectedCard?.id === entityId
          ? cardAfterSearchChange(filteredCards, entityId, searchChanged)
          : undefined;
      if (afterSearch !== undefined) {
        prevSelectionCtxRef.current = `${activeTab}|${scope}|${search}`;
        setSelectedCard(afterSearch ? afterSearch.card : null);
        setSelectedStatus(afterSearch ? afterSearch.status : "");
        return;
      }
      // Уже показываем этого кандидата — URL синхронен: доводим разовые edit/tab.
      if (selectedCard?.id === entityId) {
        if (editParam === "1") onEditRef.current();
        if (tabParam === "anketa") onAnketaRef.current();
        if (editParam === "1" || tabParam === "anketa" || archivedParam === "1") consumeOneShotParams();
        return;
      }
      // Не «бодаемся» с кликом — на свежем клике URL временно отстаёт.
      if (!shouldAdoptUrlEntity(selId, entityId, selChanged)) return;
      const match = filteredCards.find((fc) => fc.card.id === entityId);
      if (match) {
        setSelectedCard(match.card);
        setSelectedStatus(match.status);
        if (editParam === "1") onEditRef.current();
        if (tabParam === "anketa") onAnketaRef.current();
        // entity СОХРАНЯЕМ (шарящаяся ссылка); гасим только разовые edit/tab/archived.
        consumeOneShotParams();
        return;
      }
      // Кандидата нет на доске: архив, статус вне колонок, активный фильтр или
      // чужой скоуп. Грузим по id и открываем НАПРЯМУЮ. Раньше подставляли ФИО в
      // поиск; не находилось — оставалась ПРОШЛАЯ карточка, и рекрутёр по ссылке
      // из расширения попадал на чужого человека (Эльвира, 18.09.2026).
      if (entityFetchTriedRef.current !== entityId) {
        entityFetchTriedRef.current = entityId;
        deepLinkPendingRef.current = entityId; // запрещаем зеркалу трогать URL
        getEntity(entityId)
          .then((entity) => {
            if (!entity?.id) {
              toast.error("Кандидат не найден");
              deepLinkPendingRef.current = null;
              clearCandidateDeepLink();
              return;
            }
            setSelectedCard(entityToKanbanCard(entity, { calcAge: calculateAge }));
            setSelectedStatus((entity.status as string) || "");
            if (editParam === "1") onEditRef.current();
            if (tabParam === "anketa") onAnketaRef.current();
            consumeOneShotParams();
            deepLinkPendingRef.current = null;
            // Только что добавленный — не «открыт отдельно», его просто ещё нет в
            // загруженном списке.
            if (justCreatedRef.current === entity.id) {
              justCreatedRef.current = null;
              return;
            }
            // Говорим прямо, почему его нет в списке слева — иначе выглядит как
            // «база открыла не того».
            const why = (entity as unknown as { is_archived?: boolean }).is_archived
              ? "он в архиве"
              : `его статус «${
                  (STATUS_LABELS as Record<string, string>)[(entity.status as string) || ""] ||
                  entity.status ||
                  "—"
                }» не показывается на доске`;
            toast(`Карточка открыта отдельно: ${why}`, { icon: "ℹ️" });
          })
          .catch(() => {
            toast.error("Не удалось открыть кандидата (нет доступа?)");
            deepLinkPendingRef.current = null;
            clearCandidateDeepLink();
          });
        return;
      }
    }
    const selectionCtx = `${activeTab}|${scope}|${search}`;
    const contextChanged = prevSelectionCtxRef.current !== selectionCtx;
    prevSelectionCtxRef.current = selectionCtx;

    const selectedVisible = selectedCard
      ? filteredCards.some(({ card }) => card.id === selectedCard.id)
      : false;
    if (filteredCards.length === 0) {
      // Закрываем профиль, только если фильтр сменил сам пользователь.
      if (selectedCard && contextChanged) {
        setSelectedCard(null);
        setSelectedStatus("");
      }
      return;
    }
    // Иначе — первая видимая карточка. Только на смене контекста или когда не
    // открыто ничего (первая загрузка): фоновое обновление не имеет права
    // перебросить фокус на чужую карточку.
    if (!selectedVisible && (contextChanged || !selectedCard)) {
      const initial = filteredCards[0];
      setSelectedCard(initial.card);
      setSelectedStatus(initial.status);
    }
    // boardStale меняется только вместе с board (см. useCandidateBoard) — в deps
    // хватает board; список совпадает с тем, что был в странице до выноса.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredCards, entityParam, editParam, archivedParam, tabParam, board, selectedCard, clearCandidateDeepLink, consumeOneShotParams]);

  // Зеркалим открытый профиль в URL (?entity=ID) — ссылка на кандидата шарится.
  // replace:true → без спама истории. Чистая функция вернёт null, когда менять
  // нечего — это и есть защита от бесконечного цикла.
  useEffect(() => {
    // Пока диплинк не разрешён, НЕ трогаем адрес: иначе ?entity=<запрошенный>
    // затирается id прошлой открытой карточки.
    if (deepLinkPendingRef.current != null) return;
    const curId = selectedCard?.id ?? null;
    const prevId = prevSelectedIdRef.current;
    // Адрес сменили без нас (окно добавления открыло нового, «назад», переход из
    // тоста) — не перебиваем его прежним выбором, см. urlLeadsSelection.
    if (urlLeadsSelection(searchParams, curId, prevId)) return;
    const next = computeEntityParamUpdate(searchParams, curId, prevId);
    prevSelectedIdRef.current = curId;
    // Запись URL — НЕ срочная (startTransition), и ФУНКЦИЕЙ от текущих
    // параметров: снимок «до» мог затереть то, что в этот же момент поставил
    // другой обработчик (например ?stage= при клике по вкладке).
    if (next) {
      startTransition(() =>
        setSearchParams(
          (prev) =>
            urlLeadsSelection(prev, curId, prevId)
              ? prev
              : computeEntityParamUpdate(prev, curId, prevId) ?? prev,
          { replace: true },
        ),
      );
    }
  }, [selectedCard, searchParams, setSearchParams]);

  // Архивный кандидат (?archived=1): на доске его нет (отфильтрован is_archived),
  // поэтому грузим по id и открываем ту же стандартную карточку напрямую.
  useEffect(() => {
    if (!entityParam || archivedParam !== "1") return;
    const entityId = parseInt(entityParam);
    if (Number.isNaN(entityId) || entityFetchTriedRef.current === entityId) return;
    entityFetchTriedRef.current = entityId;
    deepLinkPendingRef.current = entityId;
    getEntity(entityId)
      .then((e) => {
        if (!e?.id) {
          toast.error("Кандидат не найден");
          deepLinkPendingRef.current = null;
          return;
        }
        setSelectedCard(entityToKanbanCard(e, { archived: true, calcAge: calculateAge }));
        setSelectedStatus((e.status as string) || "");
        deepLinkPendingRef.current = null;
      })
      .catch(() => {
        deepLinkPendingRef.current = null;
        toast.error("Не удалось открыть кандидата");
      });
  }, [entityParam, archivedParam]);

  return {
    selectedCard,
    setSelectedCard,
    selectedStatus,
    setSelectedStatus,
    openCandidate,
    justCreatedRef,
    clearCandidateDeepLink,
  };
}
