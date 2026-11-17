import { useMemo } from "react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import clsx from "clsx";
import { useHorizontalScroll } from "@/hooks/useHorizontalScroll";
import { HuntflowOptionsIcon } from "@/components/hr/HuntflowControls";
import type { KanbanColumn } from "@/services/api/candidates";
import { boardColumnOf } from "@/constants/hrStages";

// Полоса этапов «Все кандидаты»: «Все», вкладки этапов со счётчиками (пустые
// не показываются — 16.11.2026), стрелки прокрутки и кнопка настроек списка
// (вынесено из AllCandidatesPage, 20.10.2026).

const HUNTFLOW_STAGE_LAYOUT_TRANSITION = {
  duration: 0.42,
  ease: [0.22, 1, 0.36, 1] as const,
};

/**
 * Скоуп по этапам (09.11.2026): человеку, которому открыта только «Практика»,
 * остальные вкладки ни к чему. Свёрнутые «7 этапов без кандидатов» и «5 этапов
 * без кандидатов» по обе стороны от «Практики» читались как число людей
 * (владелец: «в одном месте 7 кандидатов, в другом 5, а видно только 2»).
 */
export function limitBoardColumnsToStatuses(
  columns: KanbanColumn[],
  allowedStatuses: readonly string[] | undefined,
): KanbanColumn[] {
  if (!allowedStatuses || allowedStatuses.length === 0) return columns;
  const allowed = new Set(allowedStatuses.map((s) => boardColumnOf(s)));
  const kept = columns.filter((c) => allowed.has(c.status));
  return kept.length ? kept : columns;
}

/**
 * Пустые этапы в полосе НЕ показываются (Мария, 16.11.2026, «трек АТС»: «не
 * совсем понятны статусы… не хочется визуально лишней информации»). Раньше
 * подряд идущие пустые сворачивались в кнопку «N этапов без кандидатов» —
 * её читали как ещё один этап. Открытая вкладка остаётся на месте, даже если
 * в ней никого не осталось: иначе человек терял бы, где стоит.
 */
export function visibleStageColumns(columns: KanbanColumn[], activeTab: string): KanbanColumn[] {
  return columns.filter((c) => (c.count ?? c.cards.length) > 0 || c.status === activeTab);
}

export function CandidateStageTabs({
  columns,
  activeTab,
  totalCount,
  searchOpen,
  searchActive,
  onToggleSearch,
  onSelectTab,
  settingsOpen,
  onOpenSettings,
  isAdmin,
}: {
  columns: KanbanColumn[];
  activeTab: string;
  totalCount: number;
  /** Строка поиска показана. */
  searchOpen: boolean;
  /** Поиск показан или в нём что-то набрано — лупа подсвечена. */
  searchActive: boolean;
  onToggleSearch: () => void;
  /** Клик по вкладке (страница сбрасывает поиск и открытую карточку). */
  onSelectTab: (status: string) => void;
  settingsOpen: boolean;
  onOpenSettings: () => void;
  isAdmin: boolean;
}) {
  // Горизонтальный скролл табов: стрелки сами пересчитываются на
  // скролл/ресайз/смену набора этапов.
  const {
    ref: topStageScrollRef,
    canScrollLeft: topStageCanScrollLeft,
    canScrollRight: topStageCanScrollRight,
    scrollLeft: scrollTopStagesLeft,
    scrollRight: scrollTopStagesRight,
  } = useHorizontalScroll<HTMLDivElement>({ step: 520 });
  const stageColumns = useMemo(() => visibleStageColumns(columns, activeTab), [columns, activeTab]);
  const totalCandidateCount = totalCount;

  return (
    <div className="hf-top-stage-shell">
      {/* Stage tabs */}
      <div
        ref={topStageScrollRef}
        className={clsx(
          "hf-top-stage-tabs no-scrollbar",
          "hf-top-stage-tabs-padded",
        )}
      >
        <motion.button
          layout="position"
          transition={{ layout: HUNTFLOW_STAGE_LAYOUT_TRANSITION }}
          type="button"
          onClick={onToggleSearch}
          className={clsx(
            "hf-top-stage-search-toggle",
            searchActive && "hf-top-stage-search-toggle-active",
          )}
          title={searchOpen ? "Скрыть поиск" : "Открыть поиск"}
          aria-pressed={searchOpen}
        >
          <Search className="h-[var(--hf-candidates-search-icon)] w-[var(--hf-candidates-search-icon)]" />
        </motion.button>

        {(
          <>
            <motion.button
              layout="position"
              transition={{ layout: HUNTFLOW_STAGE_LAYOUT_TRANSITION }}
              onClick={() => onSelectTab("all")}
              className={clsx(
                "hf-top-stage-item hf-top-stage-all",
                activeTab === "all"
                  ? "hf-top-stage-item-active"
                  : "hf-top-stage-item-idle",
              )}
            >
              Все
              <span
                className={clsx(
                  "hf-top-stage-badge",
                  activeTab === "all"
                    ? "hf-top-stage-badge-active"
                    : "",
                )}
              >
                {totalCandidateCount}
              </span>
              {activeTab === "all" && (
                <span className="hf-top-stage-underline-all" />
              )}
            </motion.button>

            {stageColumns.map((col) => {
              const isActive = activeTab === col.status;
              const stageLabel = col.label;
              return (
                <motion.button
                  key={col.status}
                  layout="position"
                  transition={{ layout: HUNTFLOW_STAGE_LAYOUT_TRANSITION }}
                  type="button"
                  onClick={() => onSelectTab(col.status)}
                  className={clsx(
                    "hf-top-stage-item",
                    isActive
                      ? "hf-top-stage-item-active"
                      : "hf-top-stage-item-idle",
                  )}
                >
                  {stageLabel}
                  <span className="hf-top-stage-badge hf-top-stage-badge-muted">
                    {String(col.count)}
                  </span>
                  {isActive && (
                    <span className="hf-top-stage-underline" />
                  )}
                </motion.button>
              );
            })}
          </>
        )}
      </div>
      <div className="hf-top-stage-action-cell">
        <button
          type="button"
          onClick={onOpenSettings}
          className="hf-top-stage-action-btn"
          title="Настройки"
          aria-label="Настройки списков кандидатов"
          aria-expanded={settingsOpen}
        >
          <HuntflowOptionsIcon className="hf-top-stage-options-icon" />
        </button>
      </div>
      {topStageCanScrollLeft ? (
        <button
          type="button"
          onClick={scrollTopStagesLeft}
          className="hf-top-stage-arrow hf-top-stage-arrow-left"
          title="Прокрутить этапы влево"
        >
          <ChevronLeft className="hf-top-stage-arrow-icon" />
        </button>
      ) : null}
      {topStageCanScrollRight ? (
        <button
          type="button"
          onClick={scrollTopStagesRight}
          className={clsx(
            "hf-top-stage-arrow",
            isAdmin ? "hf-top-stage-arrow-right-admin" : "hf-top-stage-arrow-right",
          )}
          title="Прокрутить этапы вправо"
        >
          <ChevronRight className="hf-top-stage-arrow-icon" />
        </button>
      ) : null}
    </div>
  );
}
