import { useState, Fragment } from 'react';

import { Plus, X, Check } from 'lucide-react';
import clsx from 'clsx';

import type { VacancyApplication } from '@/types';
import { readHeadlineTags, HeadlineTagChip } from '@/components/entities/headlineTags';
import { PriorRejectionChip } from '@/components/candidates/priorRejection';

import { BulkSelectionBar } from '@/components/entities/BulkSelectionBar';
import AddToVacancyModal from '@/components/entities/AddToVacancyModal';

import type { SetURLSearchParams } from 'react-router-dom';
import { avatarThumbUrl } from '@/utils/avatarThumb';

// Список кандидатов воронки слева: строки, выбор галочками, массовые действия
// («Перенести», «Удалить с воронки») — вынесено из RecruiterFunnelsPage, 20.10.2026.

export function FunnelCandidateList({
  anySelected,
  bulkMoving,
  candidates,
  fetchVacancies,
  handleBulkRemoveFromVacancy,
  hlReadonly,
  loadCandidates,
  orderedCandidates,
  selectedCandidateId,
  selectedIds,
  selectedVacancyId,
  setDetailTab,
  setSearchParams,
  setSelectedCandidateId,
  setSelectedIds,
  tabFilteredCandidates,
  toggleCandidateSelection,
}: {
  anySelected: boolean;
  bulkMoving: boolean;
  candidates: VacancyApplication[];
  fetchVacancies: (silent?: boolean) => unknown;
  handleBulkRemoveFromVacancy: () => void | Promise<void>;
  hlReadonly: boolean;
  loadCandidates: (vacancyId: number, silent?: boolean) => Promise<void>;
  orderedCandidates: { list: VacancyApplication[]; firstPreviousId?: number };
  selectedCandidateId: number | null;
  selectedIds: Set<number>;
  selectedVacancyId: number | null;
  setDetailTab: (t: 'info' | 'resume' | 'anketa') => void;
  setSearchParams: SetURLSearchParams;
  setSelectedCandidateId: (id: number | null) => void;
  setSelectedIds: (ids: Set<number>) => void;
  tabFilteredCandidates: VacancyApplication[];
  toggleCandidateSelection: (id: number) => void;
}) {
  // Окно массового переноса в другую воронку.
  const [showBulkMove, setShowBulkMove] = useState(false);
  return (
    <div className="hf-candidates-list-panel relative">
      <div className={clsx('hf-candidates-list-scroll', anySelected && 'pb-14')}>
      {tabFilteredCandidates.length === 0 ? (
        <div className="flex items-center justify-center h-40 text-hf-xxs text-[var(--hf-main-500)] hf-dark-disabled:text-[color:var(--hf-white-alpha-40)]">
          Нет кандидатов
        </div>
      ) : (
        orderedCandidates.list.map(candidate => {
          const isSelected = candidate.id === selectedCandidateId;
          const isChecked = selectedIds.has(candidate.id);
          const listMetaPrimary = candidate.entity_company || candidate.source;
          return (
            <Fragment key={candidate.id}>
            {candidate.id === orderedCandidates.firstPreviousId && (
              <div className="hf-prev-series-divider">В предыдущих сериях</div>
            )}
            <div
              onClick={() => {
                setSelectedCandidateId(candidate.id);
                setDetailTab('resume');
                // ПУШ ?entity= в историю — браузерные «Назад/Вперёд»
                // листают кандидатов (иначе Back выкидывал из воронки).
                // Зеркало ?entity= (replace + guard) второй записи не даёт.
                const eid = candidate.entity_id;
                if (eid != null) {
                  setSearchParams((prev) => {
                    if (prev.get('entity') === String(eid)) return prev;
                    const next = new URLSearchParams(prev);
                    next.set('entity', String(eid));
                    return next;
                  }, { replace: false });
                }
              }}
              className={clsx(
                'hf-candidate-row',
                candidate.is_previous_series && 'hf-candidate-row-prev-series',
                isChecked || isSelected
                  ? 'hf-candidate-row-selected'
                  : 'hf-candidate-row-idle',
              )}
            >
              {/* Avatar / checkmark zone — same interaction as /all-candidates */}
              <div
                onClick={(e) => { e.stopPropagation(); toggleCandidateSelection(candidate.id); }}
                className="hf-candidate-avatar-zone"
              >
                {isChecked ? (
                  (candidate as { entity_photo?: string }).entity_photo ? (
                    <div className="hf-candidate-avatar-check">
                      <img
                        src={avatarThumbUrl((candidate as { entity_photo?: string }).entity_photo)}
                        alt={candidate.entity_name || ''}
                        referrerPolicy="no-referrer"
                        className="hf-candidate-avatar-check-img"
                        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                      />
                      <div className="hf-candidate-avatar-check-overlay">
                        <Check className="hf-candidate-check-icon" />
                      </div>
                    </div>
                  ) : (
                    <div className="hf-candidate-avatar-check">
                      <Check className="hf-candidate-check-icon" />
                    </div>
                  )
                ) : (
                  <>
                    {(candidate as { entity_photo?: string }).entity_photo ? (
                      <img
                        src={avatarThumbUrl((candidate as { entity_photo?: string }).entity_photo)}
                        alt={candidate.entity_name || ''}
                        loading="lazy"
                        decoding="async"
                        referrerPolicy="no-referrer"
                        className="hf-candidate-avatar"
                        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                      />
                    ) : (
                      <div className="hf-candidate-avatar-fallback">
                        <span className="hf-candidate-avatar-head" />
                        <span className="hf-candidate-avatar-body" />
                      </div>
                    )}
                    <div className="hf-candidate-avatar-hover">
                      <Check className="hf-candidate-check-icon" />
                    </div>
                  </>
                )}
              </div>
              <div className="hf-candidate-row-copy">
                <div className="flex flex-wrap items-center gap-1.5 min-w-0">
                  <div className="hf-candidate-row-name">
                    {candidate.entity_name || 'Без имени'}
                  </div>
                  {/* Яркие теги у имени — ВСЕ, как в «Все кандидаты»
                      (запрос HR 16.09). Не влезли — переносятся строкой
                      ниже, имя не сжимается. */}
                  {readHeadlineTags(candidate.entity_headline_tags).map((t, i) => (
                    <span key={i} className="shrink-0">
                      <HeadlineTagChip tag={t} small />
                    </span>
                  ))}
                </div>
                {candidate.entity_position && (
                  <div className="hf-candidate-row-subtitle">
                    {candidate.entity_position}
                  </div>
                )}
                {/* «Был отказ» в другой воронке / карточке / архиве (22.10.2026). */}
                {candidate.prior_rejection && (
                  <div className="mt-[3px] flex min-w-0">
                    <PriorRejectionChip pr={candidate.prior_rejection} />
                  </div>
                )}
                <div className="hf-candidate-row-meta">
                  {listMetaPrimary && (
                    <span
                      className="hf-candidate-row-meta-text"
                      title={listMetaPrimary}
                    >
                      {listMetaPrimary}
                    </span>
                  )}
                  {listMetaPrimary && (candidate.last_stage_change_at || candidate.applied_at) && (
                    <span className="hf-candidate-row-meta-dot">·</span>
                  )}
                  {(candidate.last_stage_change_at || candidate.applied_at) && (
                    <span className="hf-candidate-row-date" title="Дата последнего переноса статуса">
                      {new Date(candidate.last_stage_change_at || candidate.applied_at).toLocaleDateString('ru')}
                    </span>
                  )}
                </div>
                <div className="sr-only">
                  {candidate.entity_name || 'Без имени'}
                </div>
              </div>
            </div>
            </Fragment>
          );
        })
      )}
      </div>

      {/* Bulk actions floating bar — единая плашка (как «Все кандидаты»).
          Прячем, пока открыта модалка перемещения, иначе плашка
          перекрывает её футер с кнопкой «Добавить». */}
      <BulkSelectionBar
        open={anySelected && !showBulkMove && !hlReadonly}
        count={selectedIds.size}
        avatars={candidates
          .filter((c) => selectedIds.has(c.id))
          .map((c) => ({
            id: c.id,
            name: c.entity_name || 'Без имени',
            photo_url: (c as { entity_photo?: string }).entity_photo,
          }))}
        onSelectAll={() =>
          setSelectedIds(
            new Set(tabFilteredCandidates.slice(0, 1000).map((c) => c.id)),
          )
        }
        onClear={() => setSelectedIds(new Set())}
        onClose={() => setSelectedIds(new Set())}
        actions={[
          {
            label: 'Добавить в воронку',
            icon: Plus,
            variant: 'neutral',
            onClick: () => setShowBulkMove(true),
            disabled: bulkMoving,
          },
          {
            label: 'Удалить с воронки',
            icon: X,
            variant: 'danger',
            onClick: handleBulkRemoveFromVacancy,
            disabled: bulkMoving,
          },
        ]}
      />
      {showBulkMove && (
        <AddToVacancyModal
          entityId={
            candidates.find((c) => selectedIds.has(c.id))?.entity_id ?? 0
          }
          entityName={`${selectedIds.size} кандидат(ов)`}
          bulkEntityIds={candidates
            .filter((c) => selectedIds.has(c.id))
            .map((c) => c.entity_id)}
          bulkEntities={candidates
            .filter((c) => selectedIds.has(c.id))
            .map((c) => ({
              id: c.entity_id,
              name: c.entity_name || 'Без имени',
            }))}
          // Прячем текущую воронку из назначений — перемещаем ИЗ неё.
          excludeVacancyIds={selectedVacancyId ? [selectedVacancyId] : undefined}
          onClose={() => setShowBulkMove(false)}
          onSuccess={() => {
            setShowBulkMove(false);
            setSelectedIds(new Set());
            if (selectedVacancyId) loadCandidates(selectedVacancyId);
            fetchVacancies();
          }}
        />
      )}
    </div>
  );
}
