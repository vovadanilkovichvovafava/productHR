import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { useLiveSearchParams } from "@/hooks/useLiveSearchParams";
import { AnimatePresence } from "framer-motion";
import { X, Users, PlusCircle } from "lucide-react";
import clsx from "clsx";

import { HfLoadingSpinner } from "@/components/ui/HfLoadingSpinner";
import {
  cardMatchesMentor,
  countHiddenByScope,
  countPracticeMentors,
  PRACTICE_STATUS,
  type MentorFilter,
  loadCandidateListSettings,
  selectVisibleCards,
  entityToKanbanCard,
  insertByCreatedAt,
  type CandidateListSettings,
} from "@/components/entities/candidateDetail/model";
import { calculateAge } from "@/utils/date";

import { getCandidateIds } from "@/services/api/candidates";
import type { KanbanCard } from "@/services/api/candidates";
import { getEntity } from "@/services/api/entities";

import AddToVacancyModal from "@/components/entities/AddToVacancyModal";
import ParserModal from "@/components/parser/ParserModal";
import { useAuthStore } from "@/stores/authStore";

import { BulkSelectionBar } from "@/components/entities/BulkSelectionBar";
import { useCandidateBoard } from "@/components/candidates/useCandidateBoard";
import { useCandidateSelection } from "@/components/candidates/useCandidateSelection";
import { useOpenedCandidateRefresh } from "@/components/candidates/useOpenedCandidateRefresh";
import { CandidateStageTabs } from "@/components/candidates/CandidateStageTabs";
import { CandidateListRow } from "@/components/candidates/CandidateListRow";

import { useDebounce } from "@/hooks/useDebounce";
import { InfoTab } from "@/components/entities/candidateDetail/CandidateInfoPanel";
import { NewCandidateModal } from "@/components/candidates/NewCandidateModal";
import { EditCandidateModal } from "@/components/candidates/EditCandidateModal";
import { ListSettingsModal } from "@/components/candidates/ListSettingsModal";
import { useMobileMasterDetail } from "@/components/candidates/useMobileMasterDetail";
import { MobileBackToList } from "@/components/candidates/MobileBackToList";
import { type DetailSection } from "@/components/entities/candidateDetail/model";
import { boardColumnOf } from "@/constants/hrStages";

// HfLoadingSpinner вынесён в components/ui/HfLoadingSpinner (общий — и страница,
// и CandidateVacancyCard импортируют его оттуда, без цикла page↔card).

function HfSkeletonBlock({
  className,
}: {
  className: string;
}) {
  return <div className={clsx("hf-loading-skeleton", className)} />;
}

function HfCandidatesLoadingLayout() {
  return (
    <div className="flex-1 flex overflow-hidden pl-0 pr-hf-s pb-hf-s gap-hf-s">
      <div className="hf-candidates-loading-list">
        <div className="hf-candidates-loading-list-inner">
          {Array.from({ length: 9 }).map((_, index) => (
            <div
              key={index}
              className="hf-candidates-loading-row"
            >
              <HfSkeletonBlock className="hf-candidates-loading-avatar" />
              <div className="hf-candidates-loading-lines">
                <HfSkeletonBlock className="hf-candidates-loading-title" />
                <HfSkeletonBlock className="hf-candidates-loading-role" />
                <HfSkeletonBlock className="hf-candidates-loading-company" />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="hf-candidates-loading-detail">
        <div className="hf-candidates-loading-head">
          <div className="hf-candidates-loading-head-copy">
            <div className="hf-candidates-loading-actions">
              <HfSkeletonBlock className="hf-candidates-loading-action hf-candidates-loading-action-1" />
              <HfSkeletonBlock className="hf-candidates-loading-action hf-candidates-loading-action-2" />
              <HfSkeletonBlock className="hf-candidates-loading-action hf-candidates-loading-action-3" />
            </div>
            <HfSkeletonBlock className="hf-candidates-loading-name" />
            <HfSkeletonBlock className="hf-candidates-loading-subtitle" />
            <div className="hf-candidates-loading-meta">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="hf-candidates-loading-meta-row">
                  <HfSkeletonBlock className="hf-candidates-loading-meta-label" />
                  <HfSkeletonBlock className="hf-candidates-loading-meta-value" />
                </div>
              ))}
            </div>
          </div>
          <HfSkeletonBlock className="hf-candidates-loading-photo" />
        </div>
        <HfSkeletonBlock className="hf-candidates-loading-panel" />
      </div>
    </div>
  );
}

// ================================================================
// MAIN PAGE
// ================================================================

export default function AllCandidatesPage() {
  // Функциональные правки адреса — от ЖИВОГО адреса, а не от снимка прошлой
  // отрисовки: иначе клик по вкладке (?stage=) и зеркало карточки (?entity=)
  // затирали друг друга, и этап терялся при F5 (см. useLiveSearchParams).
  const [searchParams, setSearchParams] = useLiveSearchParams();
  const [showNewCandidateModal, setShowNewCandidateModal] = useState(false);
  const [showParserModal, setShowParserModal] = useState(false);
  const { user } = useAuthStore();
  // Наблюдатель: список открыт весь, но массовых действий у него нет.
  const observer = !!user?.is_readonly;
  const [searchText, setSearchText] = useState("");
  const [debouncedSearch, setSearchNow] = useDebounce(searchText, 400);
  const [showTopSearch, setShowTopSearch] = useState(false);
  const topSearchRef = useRef<HTMLInputElement>(null);
  const { board, setBoard, loading, fetchBoard, showFullBoard, boardStale, staleFiltered } =
    useCandidateBoard(debouncedSearch);
  // Активная вкладка-этап живёт в URL (?stage=), чтобы браузерный «Назад»
  // возвращал на предыдущую вкладку вместе с открытым кандидатом (обратная связь
  // 2026-08-05: переключил вкладку — Back стал серым, к кандидату не вернуться).
  // Клик по вкладке = push истории; программные сбросы — replace (push:false).
  // Активная вкладка-этап — СТЕЙТ (переключается мгновенно по клику), синхронный с
  // URL ?stage= (та же проверенная схема, что в воронке). Раньше был derived-от-URL
  // — на проде вкладки не переключались, поэтому вернулись к стейту. Клик = стейт +
  // push ?stage= + снятие открытого кандидата (иначе авто-селект по ?entity= off-tab
  // отбрасывал вкладку обратно на «Все»). push:false — программный/деплинк-переход.
  const location = useLocation();
  const [activeTab, setActiveTabState] = useState<string>(() => searchParams.get("stage") || "all");
  const setActiveTab = useCallback(
    (status: string, opts?: { push?: boolean }) => {
      const push = opts?.push !== false;
      setActiveTabState(status || "all");
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (!status || status === "all") next.delete("stage");
        else next.set("stage", status);
        if (push) {
          next.delete("entity");
          next.delete("edit");
          next.delete("archived");
          next.delete("tab");
        }
        return next;
      }, { replace: !push });
    },
    [setSearchParams],
  );
  // Браузерный Назад/Вперёд меняет ?stage= — подхватываем в стейт (зависимость —
  // извлечённая строка stage, а не весь searchParams, чтобы правки ?entity= и др.
  // не дёргали). Guard на равенство — без циклов с сеттером выше.
  const urlStageParam = searchParams.get("stage") || "all";
  useEffect(() => {
    setActiveTabState((cur) => (cur === urlStageParam ? cur : urlStageParam));
  }, [urlStageParam]);

  // Бамп → форс-ремоунт детали (InfoTab) после слияния: useResumeSources и
  // loadActivity кэшируют по card.id, который у выжившего НЕ меняется, поэтому
  // сами не перечитают файлы/резюме/активность. Ремоунт заставляет перечитать.
  const [detailReloadKey, setDetailReloadKey] = useState(0);
  const [detailTab, setDetailTab] = useState<DetailSection>("resume");
  const [showListSettings, setShowListSettings] = useState(false);
  // F7-fix: настройки списка (scope + видимые поля) — persist + применяются к карточкам.
  const [listSettings, setListSettings] = useState<CandidateListSettings>(
    loadCandidateListSettings,
  );
  const [showEditModal, setShowEditModal] = useState(false);
  const [showAddToVacancy, setShowAddToVacancy] = useState(false);
  const [addToVacancyAnchor, setAddToVacancyAnchor] = useState<{
    left: number;
    bottom: number;
  } | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const VISIBLE_STEP = 50;
  const [visibleCount, setVisibleCount] = useState(VISIBLE_STEP);
  const isAdmin =
    user?.role === "superadmin" ||
    user?.org_role === "owner" ||
    user?.org_role === "admin";
  const anySelected = selectedIds.size > 0;

  // «Поиска нет» = пустой запрос И убранная строка (владелец, 02.10.2026):
  // пустое поле не должно занимать место под этапами.
  const closeSearch = useCallback(() => {
    setSearchText("");
    // И для данных тоже СРАЗУ, не дожидаясь задержки: иначе доска ещё успевает
    // сходить на сервер со старым словом и мигает «кандидатов нет».
    setSearchNow("");
    setShowTopSearch(false);
    // Возвращаем последнюю доску без поиска — список и счётчики верны сразу, а
    // свежая придёт следом (fetchBoard сработает на смену запроса).
    showFullBoard();
  }, [setSearchNow, showFullBoard]);

  // Открыть карточку конкретного кандидата (после добавления или прикрепления
  // резюме к существующему). Просьба Эльвиры 02.10.2026: «чтобы мы оказывались
  // после добавления на этом же кандидате» — раньше справа оставался тот, кто
  // был открыт ДО добавления, и статусы на бегу меняли не тому человеку.
  // Поиск и вкладку этапа сбрасываем: новый кандидат — «Новый», и при активном
  // фильтре его бы просто не было видно в списке.
  // id только что добавленного. Его ещё нет на доске (список догружается), и
  // открытие «по id» сопровождалось тостом «Карточка открыта отдельно: его статус
  // «Новый» не показывается на доске» — неправда, он просто не успел подгрузиться.
  // Только что добавленного открываем ЕЩЁ И напрямую: грузим карточку по id и
  // ставим выбор сами, не дожидаясь цепочки «адрес → эффект выбора». Логи
  // прода 21.10.2026 (Эльвира, кандидат 9515): после добавления браузер ни
  // разу не запросил нового — справа осталась прежняя карточка (9514), и так
  // «то есть, то нет», хотя локально цепочка срабатывала. Человек успел
  // кликнуть другого — не перебиваем (pendingCreatedRef сбрасывает клик).
  const pendingCreatedRef = useRef<number | null>(null);
  const mobile = useMobileMasterDetail("hf-mobile-view:all-candidates");
  const selectCreatedRef = useRef<(card: KanbanCard, status: string) => void>(() => {});
  const forceOpenCreated = useCallback((entityId: number) => {
    pendingCreatedRef.current = entityId;
    getEntity(entityId)
      .then((entity) => {
        if (!entity?.id || pendingCreatedRef.current !== entityId) return;
        pendingCreatedRef.current = null;
        selectCreatedRef.current(
          entityToKanbanCard(entity, { calcAge: calculateAge }),
          (entity.status as string) || "",
        );
      })
      .catch(() => {
        // Не вышло — остаётся обычная цепочка по адресу (?entity=).
      });
  }, []);

  const openCandidateCard = useCallback((entityId: number) => {
    justCreatedRef.current = entityId;
    forceOpenCreated(entityId);
    closeSearch();
    setActiveTabState("all");
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("stage");
      next.delete("edit");
      next.delete("archived");
      next.delete("tab");
      next.set("entity", String(entityId));
      return next;
    });
  }, [setSearchParams, forceOpenCreated]);

  // Переход по пункту меню (в т.ч. ПОВТОРНЫЙ клик по «Все кандидаты», когда мы
  // уже здесь) — начинаем с чистого листа: пустой поиск и вкладка «Все».
  // location.key меняется на каждый переход, даже на тот же адрес, а метка в
  // state отличает клик по меню от наших же правок адреса (?entity=…).
  const navState = location.state as
    | { resetSearch?: boolean; openCreatedEntity?: number }
    | null;
  useEffect(() => {
    // Добавили кандидата через плавающий «+» (окно разбора в Layout): адрес уже
    // ведёт на него (?entity=), остаётся то же, что делает openCandidateCard, —
    // сбросить поиск и вкладку и подтянуть свежий список.
    if (navState?.openCreatedEntity) {
      justCreatedRef.current = navState.openCreatedEntity;
      forceOpenCreated(navState.openCreatedEntity);
      closeSearch();
      setActiveTabState("all");
      fetchBoard();
      return;
    }
    if (!navState?.resetSearch) return;
    closeSearch();
    setActiveTabState("all");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key]);

  useEffect(() => {
    if (showTopSearch) {
      requestAnimationFrame(() => topSearchRef.current?.focus());
    }
  }, [showTopSearch]);

  // «Практикуются у»: фильтр по тегу-наставнику на вкладке «Практика».
  // Временный, как «Только по моим»: другая вкладка или поиск — сброс.
  const [mentorFilter, setMentorFilter] = useState<MentorFilter | null>(null);

  // Reset visible count when filters change
  useEffect(() => {
    setVisibleCount(VISIBLE_STEP);
    setMentorFilter(null);
  }, [activeTab, debouncedSearch]);

  // useMemo чтобы фильтрация была реактивной и не пересчитывалась лишний раз
  // (без него были репорты что переключение таба не обновляет список).
  const filteredCards = useMemo(
    () =>
      selectVisibleCards(board?.columns || [], {
        activeTab,
        scope: listSettings.scope,
        myId: user?.id,
        // Пока ответ поиска не пришёл (доска под другой запрос), список строим
        // по ТОЙ доске, что есть: иначе «ищем по всем этапам» включалось раньше
        // результатов, и между вкладкой и выдачей мелькала вся база
        // (20.10.2026: «Резерв» 18 → все 708 → 1 найденный). Если доска уже
        // отфильтрована старым запросом, вместо списка и так идёт загрузка.
        search: boardStale ? "" : debouncedSearch,
      }),
    [board, activeTab, listSettings.scope, user?.id, debouncedSearch, boardStale],
  );

  // Счётчики «Практикуются у» — ТОЛЬКО «Все кандидаты» → вкладка «Практика»
  // (решение владельца 21.09.2026), и не во время поиска: там список идёт по
  // всем этапам. Считаем по тому же списку, что видно слева, — цифры сходятся
  // с тем, что покажет клик.
  const showMentorStats = activeTab === PRACTICE_STATUS && !debouncedSearch.trim();
  const mentorStats = useMemo(
    () => (showMentorStats ? countPracticeMentors(filteredCards.map(({ card }) => card)) : []),
    [showMentorStats, filteredCards],
  );
  const displayedCards = useMemo(
    () =>
      showMentorStats && mentorFilter
        ? filteredCards.filter(({ card }) => cardMatchesMentor(card, mentorFilter))
        : filteredCards,
    [showMentorStats, mentorFilter, filteredCards],
  );

  // Сколько карточек доски отсеял локальный фильтр «Только мои» — нужно, чтобы
  // пустой список не выглядел пропажей кандидата.
  const hiddenByScopeCount = useMemo(
    () =>
      countHiddenByScope(board?.columns || [], {
        scope: listSettings.scope,
        myId: user?.id,
      }),
    [board, listSettings.scope, user?.id],
  );

  const selectedBulkCards = useMemo(() => {
    if (!board) return [];
    const byId = new Map<number, KanbanCard>();
    for (const column of board.columns) {
      for (const card of column.cards) {
        byId.set(card.id, card);
      }
    }
    return Array.from(selectedIds)
      .reverse()
      .map((id) => byId.get(id))
      .filter((card): card is KanbanCard => Boolean(card));
  }, [board, selectedIds]);

  // Открыть форму добавления при ?add=resume в URL (триггер из FAB-кнопки)
  useEffect(() => {
    if (searchParams.get("add") === "resume") {
      setShowNewCandidateModal(true);
      const next = new URLSearchParams(searchParams);
      next.delete("add");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Кто открыт справа и как это связано с адресом (?entity=, разовые ?edit=1 /
  // ?tab=anketa / ?archived=1) — см. useCandidateSelection.
  const {
    selectedCard,
    setSelectedCard,
    selectedStatus,
    setSelectedStatus,
    openCandidate: selectCandidate,
    justCreatedRef,
    clearCandidateDeepLink,
  } = useCandidateSelection({
    board,
    boardStale,
    filteredCards,
    activeTab,
    scope: listSettings.scope,
    search: debouncedSearch,
    searchParams,
    setSearchParams,
    onEditRequested: () => setShowEditModal(true),
    onAnketaRequested: () => setDetailTab("anketa"),
  });
  const openCandidate = useCallback((card: KanbanCard, status: string) => {
    // Клик по карточке — выбор человека: опоздавший ответ по только что
    // добавленному его уже не перебивает.
    pendingCreatedRef.current = null;
    selectCandidate(card, status);
    setDetailTab("resume");
    mobile.showCard();
  }, [selectCandidate, mobile.showCard]);
  selectCreatedRef.current = (card, status) => {
    selectCandidate(card, status);
    setDetailTab("resume");
    mobile.showCard();
  };
  // Открыли карточку — проверить дубль и подтянуть свежие данные кандидата.
  useOpenedCandidateRefresh(selectedCard, setSelectedCard, setSelectedStatus, observer);

  // Переставить карточку в колонку нового статуса — ТОЛЬКО на экране. Сам
  // перевод уже сделан на сервере (карточка зовёт PUT заявки или перевод вне
  // воронок, см. cardChangeStage), сюда приходит итоговый статус из ответа.
  // Раньше отсюда же уходил ещё и PATCH статуса — второй запрос на то же
  // действие, который выравнивал ВСЕ заявки кандидата под один этап (17.09).
  const handleStatusChange = (status: string) => {
    // Вкладка, а не сам статус: «Уволен» стоит во вкладке «Отказ» (boardColumnOf).
    // Без этого карточка с таким статусом не находила вкладку и пропадала до F5.
    const newStatus = boardColumnOf(status);
    if (!selectedCard || newStatus === selectedStatus) return;
    const old = selectedStatus;
    setBoard((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        columns: prev.columns.map((col) => {
          if (col.status === old)
            return {
              ...col,
              cards: col.cards.filter((c) => c.id !== selectedCard.id),
              count: col.count - 1,
            };
          if (col.status === newStatus)
            return {
              ...col,
              // Свежая дата этапа в подписи; место — по дате добавления, как
              // у всех (rank от сервера прежний: дата добавления не менялась).
              cards: insertByCreatedAt(col.cards, { ...selectedCard, status_changed_at: new Date().toISOString() }),
              count: col.count + 1,
            };
          return col;
        }),
      };
    });
    setSelectedStatus(newStatus);
  };

  // After editing candidate, update the card in state
  const handleCardUpdated = (updated: Partial<KanbanCard>) => {
    if (!selectedCard) return;
    const newCard = { ...selectedCard, ...updated };
    setSelectedCard(newCard);
    // Also update in board
    setBoard((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        columns: prev.columns.map((col) => ({
          ...col,
          cards: col.cards.map((c) => (c.id === newCard.id ? newCard : c)),
        })),
      };
    });
  };

  const [showBulkAddToVacancy, setShowBulkAddToVacancy] = useState(false);
  const toggleSelection = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const totalCandidateCount =
    board?.columns.reduce(
      (sum, column) => sum + (column.count ?? column.cards.length),
      0,
    ) ?? 0;
  return (
    <div className="hf-all-candidates-page hf-all-candidates-page-root font-hf-body">
      {/* Stage tabs island — huntflow tabs pattern: white island radius 16 h52,
          inline stage labels + counter pills bg var(--hf-bg-panel) var(--hf-main-600) 12/16/500 radius 56 pad 2-6.
          Активная вкладка: cyan-500 underline. */}
      <CandidateStageTabs
        columns={board?.columns || []}
        activeTab={activeTab}
        totalCount={totalCandidateCount}
        searchOpen={showTopSearch}
        searchActive={showTopSearch || !!searchText}
        onToggleSearch={() => (showTopSearch ? closeSearch() : setShowTopSearch(true))}
        onSelectTab={(status) => {
          // Клик по вкладке убирает поиск целиком (просьба Эльвиры 02.10.2026):
          // набранное имя висело незаметно, и переходы «не работали» — список
          // молча резался по старому запросу.
          closeSearch();
          setActiveTab(status);
          setSelectedCard(null);
        }}
        settingsOpen={showListSettings}
        onOpenSettings={() => setShowListSettings(true)}
        isAdmin={isAdmin}
      />

      {/* Поиск — ОТДЕЛЬНОЙ строкой ПОД этапами (предложение владельца
          02.10.2026). Раньше поле вставало НА место полосы этапов: пока ищешь —
          вкладок не видно, а чтобы вернуться к ним, поле надо свернуть, и
          набранное оставалось висеть незаметно. */}
      {showTopSearch && (
        <div className="relative mr-[var(--hf-space-s)] mb-[var(--hf-space-s)] flex min-h-[var(--hf-candidates-stagebar-h)] min-w-0 items-center rounded-[var(--hf-radius-l)] bg-[var(--hf-white)] pl-[var(--hf-space-xxl)] pr-[var(--hf-space-xl)]">
          <input
            ref={topSearchRef}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") closeSearch();
            }}
            placeholder="Поиск по имени, должности..."
            className="hf-top-stage-search-input"
          />
          {searchText && loading ? (
            <span className="hf-top-stage-search-action">
              <HfLoadingSpinner />
            </span>
          ) : searchText ? (
            <button
              type="button"
              onClick={closeSearch}
              className="hf-top-stage-search-action hf-top-stage-search-clear"
              title="Убрать поиск"
            >
              <X className="h-5 w-5" />
            </button>
          ) : null}
        </div>
      )}

      {/* Искали «@ник», по нику пусто — список показывает обычный поиск. Без
          подписи это читается как «нашёлся не тот человек» (01.10.2026). */}
      {board?.nick_fallback && debouncedSearch.trim() && (
        <div className="mx-[var(--hf-space-xxl)] mt-[6px] text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-field)] text-[var(--hf-main-600)]">
          По нику «{debouncedSearch.trim()}» ничего не нашли — показываем
          совпадения по имени и контактам.
        </div>
      )}

      {/* ===== MASTER-DETAIL (huntflow style) ===== */}
      {(loading && !board) || staleFiltered ? (
        <HfCandidatesLoadingLayout />
      ) : (
        <div className="hf-candidates-master" data-mobile-view={mobile.view}>
          {/* LEFT: Candidate list — white card */}
          <div className="hf-candidates-list-panel">
            {showMentorStats && (
              <div className="flex-shrink-0 px-3 pt-3 pb-2 border-b border-[var(--hf-ui-divider)]">
                <div className="text-hf-xxs text-[var(--hf-main-500)] mb-1.5">Практикуются у</div>
                <div className="flex flex-wrap gap-1.5">
                  {mentorStats.map(({ key, count }) => {
                    const active = mentorFilter === key;
                    const isNone = key === "none";
                    return (
                      <button
                        key={key}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setMentorFilter(active ? null : key)}
                        title={active
                          ? "Показать всех на практике"
                          : isNone
                            ? "Показать практикантов без тега Егора или Влада"
                            : `Показать практикантов с тегом «${key}»`}
                        className={clsx(
                          "inline-flex items-center rounded-full px-2.5 py-[3px] text-[12px] font-medium border transition-colors",
                          active
                            ? "border-[color:var(--hf-cyan-500)] bg-[var(--hf-status-cyan-badge)] text-[var(--hf-cyan-700)]"
                            : isNone
                              ? "border-[color:var(--hf-ui-border)] text-[var(--hf-main-600)] hover:border-[color:var(--hf-main-400)]"
                              : "border-[color:color-mix(in_srgb,var(--hf-red-500)_35%,transparent)] bg-[color:color-mix(in_srgb,var(--hf-red-500)_12%,transparent)] text-[var(--hf-red-500)] hover:border-[color:var(--hf-red-500)]",
                        )}
                      >
                        {isNone ? "без тега" : key} · {count}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {/* List */}
            <div className="hf-candidates-list-scroll">
              {displayedCards.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 h-40 px-4 text-center text-hf-xxs text-[var(--hf-main-500)] hf-dark-disabled:text-[color:var(--hf-white-alpha-40)]">
                  <span>Нет кандидатов</span>
                  {/* Счётчики колонок приходят с сервера, а список фильтруется уже
                      здесь — расхождение «Все N, а показывать нечего» выглядело
                      как потеря кандидата. Объясняем и даём снять фильтр. */}
                  {hiddenByScopeCount > 0 && (
                    <span>
                      Скрыто фильтром «Только мои»: {hiddenByScopeCount}.{" "}
                      <button
                        type="button"
                        className="underline hover:no-underline"
                        onClick={() => setListSettings((prev) => ({ ...prev, scope: "all" }))}
                      >
                        Показать всех
                      </button>
                    </span>
                  )}
                </div>
              ) : (
                <>
                  {displayedCards
                    .slice(0, visibleCount)
                    .map(({ card, status }) => (
                      <CandidateListRow
                        key={card.id}
                        card={card}
                        status={status}
                        columns={board?.columns || []}
                        fields={listSettings.fields}
                        isSelected={selectedCard?.id === card.id}
                        isChecked={selectedIds.has(card.id)}
                        onOpen={() => openCandidate(card, status)}
                        onToggleCheck={() => toggleSelection(card.id)}
                      />
                    ))}
                  {displayedCards.length > visibleCount && (
                    <button
                      onClick={() =>
                        setVisibleCount((prev) => prev + VISIBLE_STEP)
                      }
                      className="w-full py-hf-m text-hf-xxs text-[var(--hf-cyan-700)] hf-dark-disabled:text-[var(--hf-cyan-400)] hover:bg-[var(--hf-main-50)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-05)] transition-colors border-b border-[var(--hf-main-100)] hf-dark-disabled:border-[color:var(--hf-white-alpha-05)]"
                    >
                      Показать ещё ({displayedCards.length - visibleCount})
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {/* RIGHT: Detail panel */}
          <div className="hf-candidates-detail-panel flex-1 bg-[var(--hf-white)] hf-dark-disabled:bg-[var(--hf-bg-dark)] rounded-hf-l flex flex-col overflow-hidden">
            <MobileBackToList onClick={mobile.showList} />
            {selectedCard ? (
              <div className="flex-1 overflow-y-auto">
                <InfoTab
                  key={`detail-${selectedCard.id}-${detailReloadKey}`}
                  card={selectedCard}
                  status={selectedStatus}
                  columns={board?.columns || []}
                  detailSection={detailTab}
                  onDetailSectionChange={setDetailTab}
                  onStatusChange={handleStatusChange}
                onAddToVacancy={(rect) => {
                  setAddToVacancyAnchor(rect ?? null);
                  setShowAddToVacancy(true);
                }}
                  onEdit={() => setShowEditModal(true)}
                  onMerged={async () => {
                    // Слияние завершено в баннере: перечитываем доску (исчезает
                    // влитый источник), выжившего (merged_from + статус) и
                    // форс-ремоунтим деталь, чтобы перечитались файлы/резюме/
                    // активность — всё без ручного F5.
                    const id = selectedCard?.id;
                    fetchBoard();
                    if (id) {
                      try {
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        const e: any = await getEntity(id);
                        setSelectedCard((prev) =>
                          prev && prev.id === id
                            ? ({
                                ...prev,
                                extra_data: { ...(e.extra_data || {}) },
                                tags: e.tags || prev.tags,
                              } as KanbanCard)
                            : prev,
                        );
                        if (e.status) setSelectedStatus(e.status as string);
                      } catch {
                        /* профиль всё равно перечитается ремоунтом ниже */
                      }
                    }
                    // Ремоунт InfoTab → useResumeSources/loadActivity перечитают
                    // файлы/резюме/активность выжившего (включая влитые).
                    setDetailReloadKey((k) => k + 1);
                  }}
                  onRemovedFromVacancy={() => {
                    // Кандидата сняли с воронки → сбрасываем карточку + доску.
                    setSelectedCard(null);
                    fetchBoard();
                  }}
                />
              </div>
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="text-center text-[var(--hf-main-500)] hf-dark-disabled:text-[color:var(--hf-white-alpha-40)]">
                  <Users className="w-12 h-12 mx-auto mb-hf-m text-[var(--hf-main-400)] hf-dark-disabled:text-[color:var(--hf-white-alpha-30)]" />
                  <p className="text-hf-xxs">Выберите кандидата из списка</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===== BULK ACTIONS DRAWER ===== */}
      <BulkSelectionBar
        open={anySelected && !showBulkAddToVacancy && !observer}
        count={selectedIds.size}
        avatars={selectedBulkCards.map((card) => ({
          id: card.id,
          name: card.name,
          photo_url: card.photo_url,
        }))}
        onSelectAll={async () => {
          // «Выбрать всех» = ВСЕ кандидаты текущего фильтра, а не только
          // загруженные per_column карточки (бейдж показывал 115, выбиралось 75).
          const scopeMine =
            listSettings.scope === "mine" && user?.id != null;
          try {
            const ids = await getCandidateIds({
              q: debouncedSearch || undefined,
              status: activeTab !== "all" ? activeTab : undefined,
              recruiter_id: scopeMine ? user?.id : undefined,
            });
            setSelectedIds(new Set(ids.slice(0, 1000)));
          } catch {
            // Фолбэк: хотя бы загруженные карточки
            setSelectedIds(
              new Set(filteredCards.slice(0, 1000).map(({ card }) => card.id)),
            );
          }
        }}
        onClear={() => setSelectedIds(new Set())}
        onClose={() => setSelectedIds(new Set())}
        actions={[
          {
            label: "Взять на вакансию",
            icon: PlusCircle,
            variant: "neutral",
            onClick: () => setShowBulkAddToVacancy(true),
          },
        ]}
      />

      <AnimatePresence>
        {showNewCandidateModal && (
          <NewCandidateModal
            onClose={() => setShowNewCandidateModal(false)}
            // Ручное создание (форма «Новый кандидат») тоже открывает карточку
            // СОЗДАННОГО (Мария, 15.10.2026: «при создании хотелось бы оставаться
            // на карточке кандидата, а не предыдущего»). Правки 02.10 и 14.10
            // закрыли только окна разбора резюме; здесь справа оставался
            // прежний кандидат, и «Файл» с резюме нового уходил ЕМУ.
            onSaved={(createdId) => {
              setShowNewCandidateModal(false);
              fetchBoard();
              if (createdId) openCandidateCard(createdId);
            }}
            onOpenParser={() => {
              setShowNewCandidateModal(false);
              setShowParserModal(true);
            }}
          />
        )}
        {showParserModal && (
          <ParserModal
            type="resume"
            onClose={() => setShowParserModal(false)}
            onParsed={() => {
              setShowParserModal(false);
              fetchBoard();
            }}
            onCreated={(entityId) => {
              setShowParserModal(false);
              fetchBoard();
              openCandidateCard(entityId);
            }}
            onAttachedToEntity={(entityId) => {
              setShowParserModal(false);
              fetchBoard();
              openCandidateCard(entityId);
            }}
          />
        )}
        {showListSettings && (
          <ListSettingsModal
            onClose={() => setShowListSettings(false)}
            initial={listSettings}
            onApply={setListSettings}
          />
        )}
        {showEditModal && selectedCard && (
          <EditCandidateModal
            card={selectedCard}
            onClose={() => setShowEditModal(false)}
            onSaved={(updated) => {
              handleCardUpdated(updated);
              setShowEditModal(false);
            }}
            onDeleted={() => {
              const deletedId = selectedCard?.id;
              setShowEditModal(false);
              // Убираем удалённого из списка СРАЗУ, не дожидаясь обновления: иначе
              // автовыбор открывал первую карточку вкладки — а это он же (самый
              // свежий), и удалённая карточка оставалась справа (20.10.2026).
              if (deletedId != null) {
                setBoard((prev) =>
                  prev && {
                    ...prev,
                    columns: prev.columns.map((col) =>
                      col.cards.some((c) => c.id === deletedId)
                        ? { ...col, cards: col.cards.filter((c) => c.id !== deletedId), count: Math.max(0, col.count - 1) }
                        : col,
                    ),
                  },
                );
              }
              setSelectedCard(null);
              // И адрес: иначе ?entity= удалённого снова открывал его карточку.
              clearCandidateDeepLink();
              fetchBoard();
            }}
          />
        )}
        {showAddToVacancy && selectedCard && (
          <AddToVacancyModal
            entityId={selectedCard.id}
            entityName={selectedCard.name}
            onClose={() => setShowAddToVacancy(false)}
            onSuccess={() => {
              setShowAddToVacancy(false);
              fetchBoard();
            }}
            anchorRect={addToVacancyAnchor}
          />
        )}
        {showBulkAddToVacancy && (
          <AddToVacancyModal
            entityId={Array.from(selectedIds)[0]}
            entityName={`${selectedIds.size} кандидат(ов)`}
            onClose={() => setShowBulkAddToVacancy(false)}
            onSuccess={async () => {
              setShowBulkAddToVacancy(false);
              setSelectedIds(new Set());
              fetchBoard();
            }}
            bulkEntityIds={Array.from(selectedIds)}
            bulkEntities={selectedBulkCards.map((c) => ({
              id: c.id,
              name: c.name,
            }))}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
