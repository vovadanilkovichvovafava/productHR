import { Plus, ChevronRight, ChevronDown, Search, X, FolderOpen, PanelLeftClose } from 'lucide-react';
import clsx from 'clsx';
import { useFunnelVacancyList } from '@/components/funnels/useFunnelVacancyList';
import type { VacancyStatus } from '@/types';
const getRecruiterStatusDotClass = (status: VacancyStatus) => {
  if (status === 'open') return 'hf-recruiter-status-dot-open';
  if (status === 'paused') return 'hf-recruiter-status-dot-paused';
  if (status === 'closed') return 'hf-recruiter-status-dot-closed';
  if (status === 'pending_review') return 'hf-recruiter-status-dot-pending';
  if (status === 'cancelled') return 'hf-recruiter-status-dot-cancelled';
  return 'hf-recruiter-status-dot-default';
};

// Дерево рекрутёров слева в «Мои вакансии» (только админ): поиск, группы по
// принявшему вакансию, переход в воронку (вынесено из RecruiterFunnelsPage, 20.10.2026).

type FunnelVacancyList = ReturnType<typeof useFunnelVacancyList>;

export function FunnelsRecruiterSidebar({
  list,
  isLoading,
  isHrAdmin,
  selectedVacancyId,
  selectVacancy,
  sidebarCollapsed,
  setSidebarCollapsed,
  mobileSidebar,
  setMobileSidebar,
  hlReadonly,
  setShowCreateModal,
}: {
  list: FunnelVacancyList;
  isLoading: boolean;
  isHrAdmin: boolean;
  selectedVacancyId: number | null;
  selectVacancy: (vacancyId: number) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
  mobileSidebar: boolean;
  setMobileSidebar: (v: boolean) => void;
  hlReadonly: boolean;
  setShowCreateModal: (v: boolean) => void;
}) {
  const { recruiterSearch, setRecruiterSearch, visibleRecruiterGroups, toggleGroup } = list;
  return (
    <aside className={clsx(
      'hf-recruiter-sidebar flex-shrink-0 flex flex-col overflow-hidden z-50 transition-all duration-200',
      // Desktop: collapsible
      sidebarCollapsed
        ? 'lg:relative lg:translate-x-0 lg:w-0 lg:border-r-0 lg:overflow-hidden'
        : 'lg:relative lg:translate-x-0 lg:w-[260px]',
      // Mobile: slide-in overlay
      'fixed inset-y-0 left-0 w-[280px]',
      mobileSidebar ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
    )}>
      {/* Header */}
      <div className="hf-recruiter-sidebar-head">
        <span className="hf-recruiter-sidebar-title">
          {isHrAdmin ? 'Рекрутеры' : 'Мои вакансии'}
        </span>
        <div className="flex items-center gap-1">
          {/* Создание доступно всем, включая рекрутёров (гейт снят 2026-07-02),
              кроме наблюдателя — он ничего не создаёт. */}
          {!hlReadonly && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="hf-recruiter-sidebar-icon-btn"
              title="Новая вакансия"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={() => setSidebarCollapsed(true)}
            className="hf-recruiter-sidebar-icon-btn hidden lg:block"
            title="Свернуть панель"
          >
            <PanelLeftClose className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setMobileSidebar(false)}
            className="hf-recruiter-sidebar-icon-btn lg:hidden"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="hf-recruiter-search-wrap">
        <div className="relative">
          <Search className="hf-recruiter-search-icon" />
          <input
            type="text"
            placeholder={isHrAdmin ? "Поиск по рекрутеру..." : "Поиск вакансий..."}
            value={recruiterSearch}
            onChange={(e) => setRecruiterSearch(e.target.value)}
            className="hf-recruiter-search-input"
          />
        </div>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="w-5 h-5 border-2 border-[var(--hf-accent)] border-t-transparent rounded-full animate-spin" />
          </div>
        ) : visibleRecruiterGroups.length === 0 ? (
          <div className="hf-recruiter-empty">
            {recruiterSearch ? 'Ничего не найдено' : 'Нет вакансий'}
          </div>
        ) : (
          visibleRecruiterGroups.map((group) => (
            <div key={group.userId}>
              {/* Recruiter folder header */}
              {isHrAdmin && (
                <button
                  onClick={() => toggleGroup(group.userId)}
                  className="hf-recruiter-group-btn group"
                >
                  {group.expanded ? (
                    <ChevronDown className="hf-recruiter-chevron" />
                  ) : (
                    <ChevronRight className="hf-recruiter-chevron" />
                  )}
                  <FolderOpen className="hf-recruiter-folder-icon" />
                  <span className="hf-recruiter-group-name">
                    {group.userName}
                  </span>
                  <span className="hf-recruiter-count">
                    {group.vacancies.length}
                  </span>
                </button>
              )}

              {/* Vacancy list */}
              {(group.expanded || !isHrAdmin) && (
                <div className={isHrAdmin ? 'ml-3' : ''}>
                  {group.vacancies.map((v) => {
                    const isSelected = selectedVacancyId === v.id;
                    const count = v.applications_count ?? 0;
                    return (
                      <button
                        key={v.id}
                        onClick={() => selectVacancy(v.id)}
                        className={clsx(
                          'hf-recruiter-vacancy-btn',
                          isHrAdmin ? 'pl-6' : 'pl-3',
                          isSelected && 'hf-recruiter-vacancy-btn-active',
                        )}
                      >
                        <span className={clsx(
                          'hf-recruiter-status-dot',
                          getRecruiterStatusDotClass(v.status),
                        )} />
                        <span className={clsx('hf-recruiter-vacancy-title', !v.title?.trim() && 'hf-recruiter-vacancy-title-empty')}>{v.title?.trim() || 'Без названия'}</span>
                        <span className={clsx(
                          'hf-recruiter-count',
                          isSelected && 'hf-recruiter-count-active',
                        )}>
                          {count}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
