import { useState, useEffect, useRef } from 'react';
import { useHorizontalScroll } from '@/hooks/useHorizontalScroll';
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import clsx from 'clsx';
import type { Vacancy, VacancyApplication } from '@/types';
import { HuntflowOptionsIcon } from '@/components/hr/HuntflowControls';
import type { FunnelStagesConfig } from '@/components/funnels/useFunnelStages';

// Полоса этапов воронки: «Все», вкладки этапов со счётчиками, поиск по
// воронке, настройки вакансии (вынесено из RecruiterFunnelsPage, 20.10.2026).

export function FunnelStageTabs({
  candidateSearch,
  setCandidateSearch,
  groupedByStageMap,
  selectStageTab,
  selectedTab,
  selectedVacancy,
  setEditingVacancy,
  stagesConfig,
  vacancyVisibleStageKeys,
}: {
  candidateSearch: string;
  setCandidateSearch: (v: string) => void;
  groupedByStageMap: Record<string, VacancyApplication[]>;
  selectStageTab: (key: string) => void;
  selectedTab: string;
  selectedVacancy: Vacancy;
  setEditingVacancy: (v: Vacancy | null) => void;
  stagesConfig: FunnelStagesConfig;
  vacancyVisibleStageKeys: string[];
}) {
  // Горизонтальный скролл табов этапов — единый хук.
  const {
    ref: vacancyStageScrollRef,
    canScrollLeft: vacancyStageCanScrollLeft,
    canScrollRight: vacancyStageCanScrollRight,
    scrollLeft: scrollVacancyStagesLeft,
    scrollRight: scrollVacancyStagesRight,
  } = useHorizontalScroll<HTMLDivElement>({ step: 520 });
  const [showVacancyTopSearch, setShowVacancyTopSearch] = useState(false);
  const vacancyTopSearchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (showVacancyTopSearch) {
      vacancyTopSearchRef.current?.focus();
    }
  }, [showVacancyTopSearch]);
  // Тот же вид, что у полосы этапов «Все кандидаты», содержимое — воронки.
  return (
    <div className="hf-vacancy-stage-shell hf-top-stage-shell">
      <div
        ref={vacancyStageScrollRef}
        className={clsx(
          'hf-vacancy-stage-tabs hf-top-stage-tabs no-scrollbar',
          !showVacancyTopSearch && 'hf-top-stage-tabs-padded',
        )}
      >
        <button
          type="button"
          onClick={() => {
            if (showVacancyTopSearch || candidateSearch) {
              setCandidateSearch('');
              setShowVacancyTopSearch(false);
              return;
            }
            setShowVacancyTopSearch(true);
          }}
          className={clsx(
            'hf-top-stage-search-toggle hf-vacancy-stage-search-toggle',
            (showVacancyTopSearch || candidateSearch) && 'hf-top-stage-search-toggle-active',
          )}
          title={showVacancyTopSearch ? 'Скрыть поиск' : 'Открыть поиск'}
          aria-pressed={showVacancyTopSearch}
        >
          <Search className="h-[var(--hf-candidates-search-icon)] w-[var(--hf-candidates-search-icon)]" />
        </button>

        {showVacancyTopSearch || candidateSearch ? (
          <div className="hf-top-stage-search hf-vacancy-stage-search">
            <input
              ref={vacancyTopSearchRef}
              value={candidateSearch}
              onChange={(event) => setCandidateSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  if (candidateSearch) setCandidateSearch('');
                  else setShowVacancyTopSearch(false);
                }
              }}
              placeholder="Поиск по имени, должности..."
              className="hf-top-stage-search-input"
            />
            {candidateSearch ? (
              <button
                type="button"
                onClick={() => {
                  setCandidateSearch('');
                  vacancyTopSearchRef.current?.focus();
                }}
                className="hf-top-stage-search-action hf-top-stage-search-clear"
                title="Очистить поиск"
              >
                <X className="h-5 w-5" />
              </button>
            ) : null}
          </div>
        ) : (
          <>
            {vacancyVisibleStageKeys.map(key => {
              // Счётчик вкладки считает ТОЛЬКО активных — «предыдущие
              // серии» не входят в тотал, пока их не тронут (как в референсе:
              // бейдж «1» при нескольких серых карточках под плашкой).
              const count = (groupedByStageMap[key] || []).filter(c => !c.is_previous_series).length;
              const vacancyStageLabel = stagesConfig.labels[key];
              const isActive = selectedTab === key;
              return (
                <button
                  key={key}
                  onClick={() => selectStageTab(key)}
                  className={clsx(
                    'hf-top-stage-item',
                    isActive
                      ? 'hf-top-stage-item-active'
                      : 'hf-top-stage-item-idle',
                  )}
                >
                  {vacancyStageLabel}
                  {count > 0 && <span className="hf-top-stage-badge hf-top-stage-badge-muted">{count}</span>}
                  {isActive && <span className="hf-top-stage-underline" />}
                </button>
              );
            })}
          </>
        )}
      </div>
      {/* Полная форма редактирования (в т.ч. закрыть вакансию) —
          доступна и рекрутёрам (гейт «только админ» снят 2026-07-02). */}
      <div className="hf-top-stage-action-cell">
        <button
          type="button"
          onClick={() => setEditingVacancy(selectedVacancy)}
          className="hf-top-stage-action-btn"
          title="Действия с вакансией"
          aria-label="Действия с вакансией"
        >
          <HuntflowOptionsIcon className="hf-top-stage-options-icon" />
        </button>
      </div>
      {vacancyStageCanScrollLeft && !showVacancyTopSearch && !candidateSearch ? (
        <button
          type="button"
          onClick={scrollVacancyStagesLeft}
          className="hf-top-stage-arrow hf-top-stage-arrow-left"
          title="Прокрутить этапы влево"
        >
          <ChevronLeft className="hf-top-stage-arrow-icon" />
        </button>
      ) : null}
      {vacancyStageCanScrollRight && !showVacancyTopSearch && !candidateSearch ? (
        <button
          type="button"
          onClick={scrollVacancyStagesRight}
          className="hf-top-stage-arrow hf-top-stage-arrow-right"
          title="Прокрутить этапы вправо"
        >
          <ChevronRight className="hf-top-stage-arrow-icon" />
        </button>
      ) : null}
    </div>
  );
}
