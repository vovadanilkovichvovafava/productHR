import { pluralRu } from '@/utils/plural';
import {
  Plus,
  Briefcase,
  Users,
  ArrowRightLeft,
  ChevronDown,
  Search,
  X,
  Menu,
  Check,
  Pencil,
  Archive,
  Trash2,
  LogOut,
} from 'lucide-react';
import clsx from 'clsx';
import { resolveGroupUserName, useFunnelVacancyList } from '@/components/funnels/useFunnelVacancyList';
import { getAcceptorIds, getVacancyExitOptions } from '@/utils/vacancy';
import type { Vacancy, User } from '@/types';
import { VacancyStatusBadge } from '@/components/vacancies';
import { HUNTFLOW_VACANCY_STATUS_FILTERS } from '@/components/hr/huntflowVacancyStatus';
const formatVacancyListDate = (date?: string | null) => {
  if (!date) return 'не указана';
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return 'не указана';
  return parsed.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).replace(/\sг\.$/, '');
};

// Список вакансий «Мои вакансии»: фильтры по статусу и рекрутёру, поиск,
// карточки вакансий с действиями (вынесено из RecruiterFunnelsPage, 20.10.2026).

type FunnelVacancyList = ReturnType<typeof useFunnelVacancyList>;

export function FunnelsVacancyOverview({
  list,
  user,
  isHrAdmin,
  hlReadonly,
  selectVacancy,
  setMobileSidebar,
  setShowCreateModal,
  setShowHandover,
  setEditingVacancy,
  onCloseVacancy,
  onLeaveVacancy,
  onDeleteVacancy,
}: {
  list: FunnelVacancyList;
  user: User | null;
  isHrAdmin: boolean;
  hlReadonly: boolean;
  selectVacancy: (vacancyId: number) => void;
  setMobileSidebar: (v: boolean) => void;
  setShowCreateModal: (v: boolean) => void;
  setShowHandover: (v: boolean) => void;
  setEditingVacancy: (v: Vacancy | null) => void;
  onCloseVacancy: (v: Vacancy) => void;
  onLeaveVacancy: (v: Vacancy) => void;
  onDeleteVacancy: (v: Vacancy) => void;
}) {
  const { search, setSearch, statusFilter, selectedRecruiterFilter, scopedVacancies, showStatusMenu, setShowStatusMenu, showRecruiterMenu, setShowRecruiterMenu, usersMap, statusMenuRef, recruiterMenuRef, filteredVacancies, filteredRecruiterCount, recruiterFilterOptions, statusFilterLabel, recruiterFilterLabel, handleStatusFilterChange, handleRecruiterFilterChange } = list;
  return (
  <div className="vacancies-page flex-1 w-full max-w-full flex flex-col overflow-hidden text-[var(--hf-vacancies-page-text)]">
    <div className="hf-funnels-overview-head">
      <div className="hf-funnels-toolbar-shell">
        <div className="hf-funnels-toolbar">
          <button
            onClick={() => setMobileSidebar(true)}
            className="hf-funnels-mobile-sidebar-btn lg:hidden"
            aria-label="Открыть список рекрутеров"
          >
            <Menu className="hf-funnels-mobile-sidebar-icon" />
          </button>
          <label className={clsx('hf-funnels-search', search && 'hf-funnels-search-active')}>
            <Search className="hf-funnels-search-icon" />
            <input
              type="text"
              placeholder="Поиск по названию..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="hf-funnels-search-input"
            />
            {search && (
              <button
                type="button"
                onClick={() => {
                  setSearch('');
                }}
                className="hf-funnels-search-clear"
                title="Очистить поиск"
              >
                <X className="hf-funnels-search-clear-icon" />
              </button>
            )}
          </label>

          <div className="hf-funnels-filter-wrap" ref={statusMenuRef}>
          <button
            type="button"
            onClick={() => setShowStatusMenu((value) => !value)}
            className="hf-funnels-filter"
            aria-haspopup="menu"
            aria-expanded={showStatusMenu}
          >
            <span>{statusFilterLabel}</span>
            <ChevronDown className={clsx('hf-funnels-filter-icon', showStatusMenu && 'hf-funnels-filter-icon-open')} />
          </button>
          {showStatusMenu && (
            <div className="hf-funnels-menu hf-funnels-status-menu" role="menu">
              {HUNTFLOW_VACANCY_STATUS_FILTERS.map((status) => (
                <button
                  key={status.id}
                  type="button"
                  role="menuitem"
                  onClick={() => handleStatusFilterChange(status.id)}
                  className={clsx(
                    'hf-funnels-menu-option',
                    statusFilter === status.id && 'hf-funnels-menu-option-active',
                  )}
                >
                  <Check className="hf-funnels-menu-check" />
                  <span>{status.id === 'all' ? 'Все вакансии' : status.label}</span>
                </button>
              ))}
            </div>
          )}
          </div>

          {isHrAdmin && (
            <div className="hf-funnels-filter-wrap" ref={recruiterMenuRef}>
              <button
                type="button"
                onClick={() => setShowRecruiterMenu((value) => !value)}
                className="hf-funnels-filter"
                aria-haspopup="menu"
                aria-expanded={showRecruiterMenu}
              >
                <Users className="hf-funnels-filter-leading-icon" />
                <span>Рекрутеры: {recruiterFilterLabel}</span>
                <ChevronDown className={clsx('hf-funnels-filter-icon', showRecruiterMenu && 'hf-funnels-filter-icon-open')} />
              </button>
              {showRecruiterMenu && (
                <div className="hf-funnels-menu hf-funnels-recruiter-menu" role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => handleRecruiterFilterChange(null)}
                    className={clsx(
                      'hf-funnels-menu-option',
                      selectedRecruiterFilter === null && 'hf-funnels-menu-option-active',
                    )}
                  >
                    <Check className="hf-funnels-menu-check" />
                    <span className="hf-funnels-recruiter-avatar">Все</span>
                    <span className="hf-funnels-recruiter-menu-text">
                      <span>Все рекрутеры</span>
                      <span>{scopedVacancies.length} {pluralRu(scopedVacancies.length, 'вакансия', 'вакансии', 'вакансий')}</span>
                    </span>
                  </button>
                  {recruiterFilterOptions.length === 0 ? (
                    <div className="hf-funnels-menu-empty">Нет рекрутеров</div>
                  ) : (
                    recruiterFilterOptions.map((recruiter) => (
                      <button
                        key={recruiter.id}
                        type="button"
                        role="menuitem"
                        onClick={() => handleRecruiterFilterChange(recruiter.id)}
                        className={clsx(
                          'hf-funnels-menu-option',
                          selectedRecruiterFilter === recruiter.id && 'hf-funnels-menu-option-active',
                        )}
                      >
                        <Check className="hf-funnels-menu-check" />
                        <span className="hf-funnels-recruiter-avatar">
                          {recruiter.name[0]?.toUpperCase() || 'Р'}
                        </span>
                        <span className="hf-funnels-recruiter-menu-text">
                          <span>{recruiter.name}</span>
                          <span>{recruiter.count} {pluralRu(recruiter.count, 'вакансия', 'вакансии', 'вакансий')}</span>
                        </span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}

          {/* «Перенос кандидатов» — справа от фильтра рекрутёров. Уходит
              сотрудник → передать его воронки и кандидатов другому. Только
              админ/суперадмин (isHrAdmin). */}
          {isHrAdmin && !hlReadonly && (
            <button
              type="button"
              onClick={() => setShowHandover(true)}
              className="hf-funnels-filter"
              title="Передать все воронки и кандидатов уходящего рекрутёра другому"
            >
              <ArrowRightLeft className="hf-funnels-filter-leading-icon" />
              <span>Перенос кандидатов</span>
            </button>
          )}
        </div>

        {/* Создание доступно всем, включая рекрутёров (гейт снят 2026-07-02),
            кроме наблюдателя. */}
        {!hlReadonly && (
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            data-tour="create-vacancy"
            aria-label="Создать вакансию"
            title="Создать вакансию"
            className="hf-funnels-icon-action-btn hf-funnels-overview-create"
          >
            <Plus className="hf-funnels-icon-action" strokeWidth={2.25} />
          </button>
        )}
      </div>
    </div>

    <div className="hf-vacancies-search-body">
      <section className="hf-vacancies-search-results">
        <div className="hf-vacancies-search-count">
          Найдено вакансий: {filteredVacancies.length}
          {isHrAdmin && ` у ${filteredRecruiterCount} рекрутеров`}
        </div>
        <div className="hf-vacancies-search-list">
          {filteredVacancies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
              <Briefcase className="w-10 h-10 text-[var(--hf-vacancies-page-faint)]" />
              <div>
                <p className="text-[var(--hf-vacancies-page-text)] font-medium">
                  {search ? 'Ничего не найдено' : 'Пока нет вакансий'}
                </p>
                <p className="text-[var(--hf-vacancies-page-muted)] text-sm mt-1">
                  {search ? 'Измените поиск или фильтр статуса' : 'Создайте первую вакансию для начала работы'}
                </p>
              </div>
              {!search && !hlReadonly && (
                <button
                  onClick={() => setShowCreateModal(true)}
                  className="flex items-center gap-2 px-4 py-2 bg-[var(--hf-cyan-600)] hover:bg-[var(--hf-cyan-400)] text-[var(--hf-white)] text-sm font-medium rounded-lg transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  Создать вакансию
                </button>
              )}
            </div>
          ) : (
            filteredVacancies.map((v) => {
              const count = v.applications_count ?? 0;
              return (
                <div
                  key={v.id}
                  onClick={() => selectVacancy(v.id)}
                  className="hf-vacancies-search-row"
                >
                  <div className="hf-vacancies-search-main">
                    <div className="hf-vacancies-search-title-row">
                      <VacancyStatusBadge status={v.status} size="sm" />
                      <span
                        className={clsx(
                          'hf-vacancies-search-title',
                          !v.title?.trim() && 'hf-vacancies-search-title-empty',
                        )}
                      >
                        {v.title?.trim() || 'Без названия'}
                      </span>
                      <span className="hf-vacancies-search-kind">Вакансия</span>
                      {count > 0 && (
                        <span className="hf-vacancies-search-candidates">
                          <Users className="hf-vacancies-search-candidates-icon" />
                          {count}
                        </span>
                      )}
                    </div>
                    <div className="hf-vacancies-search-meta">
                      <span>Открыта: {formatVacancyListDate(v.created_at)}</span>
                      {v.updated_at && (
                        <span>Последнее действие: {formatVacancyListDate(v.updated_at)}</span>
                      )}
                      <span>Рекрутер: {getAcceptorIds(v).map((uid) => resolveGroupUserName(uid, v, usersMap, user)).join(', ')}</span>
                    </div>
                    <div className="hf-vacancies-search-department">
                      {v.department_name || 'Общая'}
                    </div>
                  </div>
                  <div className="hf-vacancies-search-side">
                    <span className="hf-vacancies-search-chip">
                      {count} {pluralRu(count, 'кандидат', 'кандидата', 'кандидатов')}
                    </span>
                    <div className="flex items-center gap-2">
                      {!hlReadonly && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setEditingVacancy(v);
                        }}
                        className="hf-vacancies-search-action"
                        title="Редактировать"
                      >
                        <Pencil className="hf-vacancies-search-action-icon" />
                      </button>
                      )}
                      {!hlReadonly && v.status !== 'closed' && getVacancyExitOptions(v, user?.id, isHrAdmin).canLeave && (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onLeaveVacancy(v);
                          }}
                          className="hf-vacancies-search-action"
                          title="Выйти из вакансии — у остальных она останется в работе"
                        >
                          <LogOut className="hf-vacancies-search-action-icon" />
                        </button>
                      )}
                      {!hlReadonly && v.status !== 'closed' && getVacancyExitOptions(v, user?.id, isHrAdmin).canClose && (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onCloseVacancy(v);
                          }}
                          className="hf-vacancies-search-action"
                          title={getVacancyExitOptions(v, user?.id, isHrAdmin).canLeave ? 'Закрыть вакансию для всех участников' : 'Закрыть вакансию'}
                        >
                          <Archive className="hf-vacancies-search-action-icon" />
                        </button>
                      )}
                      {user?.role === 'superadmin' && !hlReadonly && (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onDeleteVacancy(v);
                          }}
                          className="hf-vacancies-search-action"
                          title="Удалить"
                          style={{ color: 'var(--hf-status-red)' }}
                        >
                          <Trash2 className="hf-vacancies-search-action-icon" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>
    </div>
  </div>
  );
}
