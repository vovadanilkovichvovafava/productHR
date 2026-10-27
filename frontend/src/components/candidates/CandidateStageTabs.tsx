import { Fragment, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, ChevronLeft, ChevronRight, Search } from "lucide-react";
import clsx from "clsx";
import { useHorizontalScroll } from "@/hooks/useHorizontalScroll";
import { HuntflowOptionsIcon } from "@/components/hr/HuntflowControls";
import type { KanbanColumn } from "@/services/api/candidates";

// Полоса этапов «Все кандидаты»: «Все», вкладки этапов со счётчиками, свёрнутые
// группы пустых этапов, стрелки прокрутки и кнопка настроек списка
// (вынесено из AllCandidatesPage, 20.10.2026).

const HUNTFLOW_STAGE_LAYOUT_TRANSITION = {
  duration: 0.42,
  ease: [0.22, 1, 0.36, 1] as const,
};

type TopStageNavItem =
  | { type: "stage"; column: KanbanColumn }
  | { type: "empty-group"; id: string; columns: KanbanColumn[]; count: number };

// Подряд идущие пустые этапы сворачиваются в одну кнопку «N этапов без кандидатов».
// Колонку «Отозван» не прячем: кандидат, которого не видно в «Все кандидаты», для
// рекрутёра равен пропавшему (владелец 18.09.2026).
function buildNavItems(columns: KanbanColumn[]): TopStageNavItem[] {
  const items: TopStageNavItem[] = [];
  let emptyRun: KanbanColumn[] = [];
  const flushEmptyRun = () => {
    if (!emptyRun.length) return;
    items.push({
      type: "empty-group",
      id: emptyRun.map((column) => column.status).join("-"),
      columns: [...emptyRun],
      count: emptyRun.length,
    });
    emptyRun = [];
  };
  columns.forEach((column) => {
    const count = column.count ?? column.cards.length;
    if (count === 0) {
      emptyRun.push(column);
      return;
    }
    flushEmptyRun();
    items.push({ type: "stage", column });
  });
  flushEmptyRun();
  return items;
}

function getEmptyStageGroupLabel(count: number) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  const noun =
    mod10 === 1 && mod100 !== 11
      ? "этап"
      : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
        ? "этапа"
        : "этапов";
  return `${count} ${noun} без кандидатов`;
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
  const [expandedEmptyStageGroups, setExpandedEmptyStageGroups] = useState<Set<string>>(
    () => new Set(),
  );
  const topStageNavItems = useMemo(() => buildNavItems(columns), [columns]);
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

            {topStageNavItems.map((item) => {
              if (item.type === "empty-group") {
                const isExpanded = expandedEmptyStageGroups.has(item.id);
                return (
                  <Fragment key={`empty-${item.id}`}>
                    <motion.button
                      layout="position"
                      transition={{ layout: HUNTFLOW_STAGE_LAYOUT_TRANSITION }}
                      type="button"
                      className={clsx(
                        "hf-top-stage-empty-group",
                        isExpanded && "hf-top-stage-empty-group-expanded",
                      )}
                      aria-expanded={isExpanded}
                      title={isExpanded ? "Свернуть пустые этапы" : "Показать пустые этапы"}
                      onClick={() => {
                        setExpandedEmptyStageGroups((prev) => {
                          const next = new Set(prev);
                          if (next.has(item.id)) next.delete(item.id);
                          else next.add(item.id);
                          return next;
                        });
                      }}
                    >
                      <span>{getEmptyStageGroupLabel(item.count)}</span>
                      <ChevronDown className="hf-top-stage-empty-group-icon" />
                    </motion.button>
                    {isExpanded && item.columns.map((col) => {
                      const isActive = activeTab === col.status;
                      return (
                        <motion.button
                          key={col.status}
                          layout="position"
                          transition={{ layout: HUNTFLOW_STAGE_LAYOUT_TRANSITION }}
                          type="button"
                          onClick={() => onSelectTab(col.status)}
                          className={clsx(
                            "hf-top-stage-item hf-top-stage-empty-stage",
                            isActive
                              ? "hf-top-stage-item-active"
                              : "hf-top-stage-item-idle",
                          )}
                        >
                          {col.label}
                          <span className="hf-top-stage-badge hf-top-stage-badge-muted">
                            {String(col.count)}
                          </span>
                          {isActive && (
                            <span className="hf-top-stage-underline" />
                          )}
                        </motion.button>
                      );
                    })}
                  </Fragment>
                );
              }

              const col = item.column;
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
