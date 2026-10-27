import { pluralRu } from '@/utils/plural';
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useCurrencyRates } from '@/hooks';
import { AnimatePresence } from 'framer-motion';
import {
  Search,
  Plus,
  Briefcase,
  DollarSign,
  Users,
  Filter,
  X,
  Check,
  ChevronDown,
  Calendar,
  UserPlus,
  PlayCircle,
  XCircle,
  Pencil,
  Archive,
  Trash2,
  LogOut,
} from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { useVacancyStore } from '@/stores/vacancyStore';
import { useAuthStore } from '@/stores/authStore';
import { vacancyExitCopy } from '@/utils/vacancyExitCopy';
import { DATE_RANGES, SALARY_RANGES, filterVacancyRequests, type QuickFilters } from '@/utils/vacancyRequests';
import type { Vacancy, VacancyStatus } from '@/types';
import { EMPLOYMENT_TYPES } from '@/types';
import { formatSalary } from '@/utils';
import { getDepartments, takeVacancy, declineVacancy, getAssignableUsers } from '@/services/api';
import type { Department } from '@/services/api';
import { VacancyForm, VacancyStatusBadge } from '@/components/vacancies';
import AssignVacancyModal from '@/components/vacancies/AssignVacancyModal';
import { SidebarRequestPreviewModal } from '@/components/hr/SidebarRequestPreviewModal';
import { isPersonallyActive, getAcceptorIds, isExplicitlyAssigned, getVacancyExitOptions } from '@/utils/vacancy';
import {
  ContextMenu,
  createVacancyContextMenu,
  EmptyVacancies,
  ConfirmDialog,
  ErrorMessage,
} from '@/components/ui';
import { HUNTFLOW_VACANCY_STATUS_FILTERS, getHuntflowVacancyStatusFilterLabel } from '@/components/hr/huntflowVacancyStatus';

export default function VacanciesPage() {
  const { vacancyId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [searchQuery, setSearchQuery] = useState('');
  // Дефолтный таб 'Все' — иначе только что созданная заявка (status=pending_review)
  // не видна в открытом по умолчанию 'Открыта', и юзер думает что она пропала.
  const [statusFilter, setStatusFilter] = useState<VacancyStatus | 'all'>('all');
  const [departmentFilter, setDepartmentFilter] = useState<number | 'all'>('all');
  const [departments, setDepartments] = useState<Department[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingVacancy, setEditingVacancy] = useState<Vacancy | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Confirmation dialog state
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    vacancy: Vacancy | null;
    type: 'delete' | 'close' | 'leave';
  }>({ open: false, vacancy: null, type: 'delete' });
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Quick filters state
  const [showFiltersDropdown, setShowFiltersDropdown] = useState(false);
  const [quickFilters, setQuickFilters] = useState<QuickFilters>(() => {
    // Initialize from URL params
    const statusesParam = searchParams.get('statuses');
    const salaryParam = searchParams.get('salary');
    const dateParam = searchParams.get('date');
    return {
      statuses: statusesParam ? statusesParam.split(',') as VacancyStatus[] : [],
      salaryRange: salaryParam || 'any',
      dateRange: dateParam || 'any',
    };
  });
  const filtersDropdownRef = useRef<HTMLDivElement>(null);

  const {
    vacancies,
    currentVacancy,
    isLoading,
    error,
    fetchVacancies,
    fetchVacancy,
    updateVacancy,
    deleteVacancy,
    setFilters,
    clearCurrentVacancy,
    clearError
  } = useVacancyStore();

  // Auth state for role-based UI
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'superadmin' || user?.org_role === 'owner' || user?.org_role === 'admin';
  // Наблюдатель (is_readonly) обычно с правами админа — без этого флага ему
  // показывались «Назначить», «Взять в работу», «Удалить» и т.д. (01.10.2026).
  const observer = !!user?.is_readonly;

  // Task 9: "My vacancies" filter — non-admin users see only their vacancies by default
  const [showOnlyMine, setShowOnlyMine] = useState(false);
  const effectiveShowOnlyMine = !isAdmin || showOnlyMine;

  // Task 12: Assignment filter for unassigned requests
  const [assignmentFilter, setAssignmentFilter] = useState<'all' | 'unassigned'>('all');

  // Assign modal state
  const [assigningVacancy, setAssigningVacancy] = useState<Vacancy | null>(null);
  const [previewVacancy, setPreviewVacancy] = useState<Vacancy | null>(null);

  // Take vacancy handler
  const [takingVacancyId, setTakingVacancyId] = useState<number | null>(null);
  const handleTakeVacancy = useCallback(async (vacancy: Vacancy) => {
    setTakingVacancyId(vacancy.id);
    try {
      await takeVacancy(vacancy.id);
      toast.success('Заявка взята в работу');
      fetchVacancies();
    } catch {
      toast.error('Не удалось взять заявку');
    } finally {
      setTakingVacancyId(null);
    }
  }, [fetchVacancies]);

  // Check if a vacancy is assigned to the current user
  const isAssignedToMe = useCallback((vacancy: Vacancy) => {
    if (!user) return false;
    if (vacancy.assigned_to_all) return true;
    if (vacancy.assigned_to && vacancy.assigned_to.includes(user.id)) return true;
    return false;
  }, [user]);

  // Уже ли ЭТОТ юзер лично взял заявку в работу (2026-07-08: extra_data.accepted_by —
  // воронка общая, но принятие личное; легаси-проверка через клон
  // (cloned_from_request_id) больше не применима — клонов не создаётся).
  const hasAlreadyTaken = useCallback((vacancy: Vacancy) => {
    if (!user) return false;
    return isPersonallyActive(vacancy, user.id);
  }, [user]);

  // Currency rates for salary conversion during filtering
  const { getComparableSalary } = useCurrencyRates();

  // Calculate active filter count
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (quickFilters.statuses.length > 0) count++;
    if (quickFilters.salaryRange !== 'any') count++;
    if (quickFilters.dateRange !== 'any') count++;
    return count;
  }, [quickFilters]);

  // Filter vacancies based on quick filters
  // Note: Salary ranges are in RUB, so we convert vacancy salaries to RUB for comparison
  const filteredVacancies = useMemo(
    () =>
      filterVacancyRequests(vacancies, {
        search: searchQuery, user, isAdmin, onlyMine: effectiveShowOnlyMine,
        assignmentFilter, departmentFilter, statusFilter, quickFilters, getComparableSalary,
      }),
    [vacancies, searchQuery, departmentFilter, quickFilters, getComparableSalary, effectiveShowOnlyMine, assignmentFilter, statusFilter, user, isAdmin],
  );

  // Sync quick filters to URL
  useEffect(() => {
    const newParams = new URLSearchParams(searchParams);

    if (quickFilters.statuses.length > 0) {
      newParams.set('statuses', quickFilters.statuses.join(','));
    } else {
      newParams.delete('statuses');
    }

    if (quickFilters.salaryRange !== 'any') {
      newParams.set('salary', quickFilters.salaryRange);
    } else {
      newParams.delete('salary');
    }

    if (quickFilters.dateRange !== 'any') {
      newParams.set('date', quickFilters.dateRange);
    } else {
      newParams.delete('date');
    }

    setSearchParams(newParams, { replace: true });
  }, [quickFilters, setSearchParams, searchParams]);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (filtersDropdownRef.current && !filtersDropdownRef.current.contains(event.target as Node)) {
        setShowFiltersDropdown(false);
      }
    };

    if (showFiltersDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showFiltersDropdown]);

  // Quick filter handlers
  const handleToggleStatusFilter = (status: VacancyStatus) => {
    setQuickFilters(prev => ({
      ...prev,
      statuses: prev.statuses.includes(status)
        ? prev.statuses.filter(s => s !== status)
        : [...prev.statuses, status]
    }));
  };

  const handleSalaryRangeChange = (rangeId: string) => {
    setQuickFilters(prev => ({ ...prev, salaryRange: rangeId }));
  };

  const handleDateRangeChange = (rangeId: string) => {
    setQuickFilters(prev => ({ ...prev, dateRange: rangeId }));
  };

  const handleClearAllFilters = () => {
    setQuickFilters({
      statuses: [],
      salaryRange: 'any',
      dateRange: 'any',
    });
  };

  // Load departments
  useEffect(() => {
    const loadDepartments = async () => {
      try {
        const data = await getDepartments(-1);
        setDepartments(data);
      } catch (error) {
        console.error('Failed to load departments', error);
      }
    };
    loadDepartments();
  }, []);

  // Резолвер id → имя для «Рекрутер: ...» (accepted_by может ссылаться на
  // любого назначаемого пользователя, не только создателя заявки).
  const [usersById, setUsersById] = useState<Record<number, string>>({});
  useEffect(() => {
    getAssignableUsers()
      .then((list) => {
        const map: Record<number, string> = {};
        list.forEach((u) => { map[u.id] = u.name; });
        setUsersById(map);
      })
      .catch(() => {});
  }, []);

  // Update filters when search/filters change
  useEffect(() => {
    setFilters({
      search: searchQuery || undefined,
      status: statusFilter !== 'all' ? statusFilter : undefined,
      department_id: departmentFilter !== 'all' ? departmentFilter : undefined
    });
  }, [searchQuery, statusFilter, departmentFilter, setFilters]);

  // Fetch vacancies when filters change
  useEffect(() => {
    fetchVacancies();
  }, [fetchVacancies]);

  // Load specific vacancy if URL has vacancyId
  useEffect(() => {
    if (vacancyId) {
      fetchVacancy(parseInt(vacancyId));
    } else {
      clearCurrentVacancy();
    }
  }, [vacancyId, fetchVacancy, clearCurrentVacancy]);

  const handleVacancyClick = (vacancy: Vacancy) => {
    // «Заявки» показывает и ещё не взятые (pending_review/draft), и уже
    // активные (open/paused) вакансии вперемешку. Для НЕ взятых — сводка
    // (SidebarRequestPreviewModal: приоритет/заказчик + «Взять в работу»).
    // Для уже активных внутри есть кандидаты/этапы/комментарии — их видно
    // только в воронке, поэтому сразу ведём туда вместо той же карточки-сводки.
    // 2026-07-08: НО если статус уже open/paused (кто-то ДРУГОЙ из назначенных
    // уже взял её в работу), а ТЕКУЩИЙ юзер сам ещё не принял лично — ведём
    // на ту же сводку с «Взять в работу», а не в чужую пока воронку.
    const canEnterFunnel = isAdmin || !user || isPersonallyActive(vacancy, user.id);
    if ((vacancy.status === 'open' || vacancy.status === 'paused') && canEnterFunnel) {
      navigate(`/my-funnels?v=${vacancy.id}`);
      return;
    }
    setPreviewVacancy(vacancy);
  };

  const handleBack = () => {
    navigate('/vacancies');
  };

  const handleDeleteClick = (vacancy: Vacancy) => {
    setConfirmDialog({ open: true, vacancy, type: 'delete' });
  };

  // «Отказаться» — рекрутёр (member) снимает СЕБЯ с заявки (вместо удаления).
  const [decliningId, setDecliningId] = useState<number | null>(null);
  const handleDecline = async (vacancy: Vacancy) => {
    setDecliningId(vacancy.id);
    try {
      await declineVacancy(vacancy.id);
      toast.success('Вы отказались от заявки');
      fetchVacancies();
    } catch {
      toast.error('Не удалось отказаться от заявки');
    } finally {
      setDecliningId(null);
    }
  };

  // Task 14: Close vacancy handler
  const handleCloseClick = (vacancy: Vacancy) => {
    setConfirmDialog({ open: true, vacancy, type: 'close' });
  };

  // «Выйти из заявки» — снять себя, у остальных участников она остаётся в работе.
  // Отдельно от «Закрыть заявку», которая закрывает у всех (2026-09-10).
  const handleLeaveClick = (vacancy: Vacancy) => {
    setConfirmDialog({ open: true, vacancy, type: 'leave' });
  };

  const handleConfirmDelete = async () => {
    if (!confirmDialog.vacancy) return;
    setDeleteLoading(true);
    try {
      if (confirmDialog.type === 'leave') {
        await declineVacancy(confirmDialog.vacancy.id);
        toast.success('Вы вышли из заявки — у остальных она осталась в работе');
        fetchVacancies();
      } else if (confirmDialog.type === 'close') {
        // Task 14: Close vacancy and auto-switch to "open" filter
        await updateVacancy(confirmDialog.vacancy.id, { status: 'closed' });
        toast.success('Заявка закрыта');
        setStatusFilter('open');
        fetchVacancies();
      } else {
        await deleteVacancy(confirmDialog.vacancy.id);
        toast.success('Заявка удалена');
        if (currentVacancy?.id === confirmDialog.vacancy.id) {
          navigate('/vacancies');
        }
      }
      setConfirmDialog({ open: false, vacancy: null, type: 'delete' });
    } catch {
      toast.error(
        confirmDialog.type === 'leave' ? 'Не удалось выйти из заявки'
          : confirmDialog.type === 'close' ? 'Не удалось закрыть заявку' : 'Не удалось удалить заявку',
      );
    } finally {
      setDeleteLoading(false);
    }
  };

  // Тексты подтверждения — общие с «Мои вакансии» (vacancyExitCopy).
  const confirmCopy = (() => {
    const v = confirmDialog.vacancy;
    if (confirmDialog.type === 'delete' || !v) {
      return {
        title: 'Удалить заявку',
        message: 'Вы уверены, что хотите удалить эту заявку? Это действие невозможно отменить.',
        confirmLabel: 'Удалить',
        variant: 'danger' as const,
      };
    }
    const copy = vacancyExitCopy(confirmDialog.type, v, user?.id, 'request');
    // У «Выйти» текста нет — только вопрос; в окне показываем, из какой заявки.
    return { title: copy.title, message: copy.text || `«${v.title?.trim() || 'Без названия'}»`, confirmLabel: copy.confirmLabel, variant: 'warning' as const };
  })();

  const handleCancelConfirm = () => {
    if (!deleteLoading) {
      setConfirmDialog({ open: false, vacancy: null, type: 'delete' });
    }
  };

  const handleRetryFetch = () => {
    clearError();
    if (vacancyId) {
      fetchVacancy(parseInt(vacancyId));
    } else {
      fetchVacancies();
    }
  };

  const handleCopyLink = (vacancy: Vacancy) => {
    const url = `${window.location.origin}/vacancies/${vacancy.id}`;
    navigator.clipboard.writeText(url);
    toast.success('Ссылка скопирована');
  };

  const getSalaryDisplay = (vacancy: Vacancy) => {
    if (!vacancy.salary_min && !vacancy.salary_max) return null;
    return formatSalary(vacancy.salary_min, vacancy.salary_max, vacancy.salary_currency);
  };

  const formatVacancyDate = (value?: string) => {
    if (!value) return '—';
    return new Intl.DateTimeFormat('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(new Date(value));
  };

  const getVacancyStatusLabel = (status: VacancyStatus) =>
    getHuntflowVacancyStatusFilterLabel(status);

  // Страница /vacancies — это раздел «Заявки». Всё что здесь лежит и
  // создаётся — заявки (вакансия становится «вакансией» только когда
  // рекрутёр взял её в работу → клон в «Мои вакансии»).
  const getVacancyKindLabel = (_vacancy: Vacancy) => 'Заявка';

  const getClosedVacancyDate = (vacancy: Vacancy) =>
    vacancy.status === 'closed' ? vacancy.closes_at || vacancy.updated_at : null;

  const getEmploymentTypeLabel = (value?: string) => {
    if (!value) return null;
    const normalizedValue = value.replace(/_/g, '-');
    return EMPLOYMENT_TYPES.find((type) => type.value === normalizedValue)?.label || value;
  };

  // Handle main tab change
  // Detail view — directly show edit form for the vacancy
  if (currentVacancy && vacancyId) {
    return (
      <div className="h-full w-full max-w-full flex flex-col overflow-hidden">
        <VacancyForm
          key={`edit-${currentVacancy.id}`}
          vacancy={currentVacancy}
          onClose={handleBack}
          onSuccess={() => {
            fetchVacancy(currentVacancy.id);
            fetchVacancies();
            toast.success('Заявка обновлена');
          }}
        />
      </div>
    );
  }

  // List view
  return (
    <div className="vacancies-page h-full w-full max-w-full flex flex-col overflow-hidden text-[var(--hf-vacancies-page-text)]">
      <div className="hf-vacancies-page-head">
        <div className="hf-vacancies-title-row">
          <h1 className="hf-vacancies-title">
            <Briefcase className="hf-vacancies-title-icon" />
            Заявки
          </h1>

          {/* Создание заявок доступно всем, включая рекрутёров (гейт снят 2026-07-02),
              кроме наблюдателя. */}
          {!observer && (
          <button
            onClick={() => {
              setShowCreateModal(true);
            }}
            data-tour="create-vacancy"
            title="Создать заявку"
            className="hf-funnels-primary-btn"
          >
            <Plus className="hf-funnels-primary-icon" strokeWidth={2.5} />
            Новая заявка
          </button>
          )}
        </div>

        <div className="hf-vacancies-toolbar">
          <label className={clsx('hf-funnels-search', searchQuery && 'hf-funnels-search-active')}>
            <Search className="hf-funnels-search-icon" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Поиск по названию..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="hf-funnels-search-input"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="hf-funnels-search-clear"
                title="Очистить поиск"
              >
                <X className="hf-funnels-search-clear-icon" />
              </button>
            )}
          </label>

          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as VacancyStatus | 'all')}
            className="hf-vacancies-select"
            aria-label="Статус заявки"
          >
            {HUNTFLOW_VACANCY_STATUS_FILTERS.map((status) => (
              <option key={status.id} value={status.id}>
                {status.id === 'all' ? 'Все заявки' : status.label}
              </option>
            ))}
          </select>

          <select
            value={departmentFilter}
            onChange={(e) => setDepartmentFilter(e.target.value === 'all' ? 'all' : parseInt(e.target.value))}
            className="hf-vacancies-select"
            aria-label="Отдел"
          >
            <option value="all">Все отделы</option>
            {departments.map((dept) => (
              <option key={dept.id} value={dept.id}>
                {dept.name}
              </option>
            ))}
          </select>

          {isAdmin && (
            <button
              onClick={() => setShowOnlyMine(!showOnlyMine)}
              className={clsx(
                'hf-funnels-filter hf-vacancies-toolbar-button',
                showOnlyMine && 'hf-vacancies-toolbar-button-active'
              )}
            >
              <Users className="hf-funnels-filter-leading-icon" />
              {showOnlyMine ? 'Только мои' : 'Доступ: все'}
            </button>
          )}

          {isAdmin && (
            <button
              onClick={() => setAssignmentFilter(prev => prev === 'all' ? 'unassigned' : 'all')}
              className={clsx(
                'hf-funnels-filter hf-vacancies-toolbar-button',
                assignmentFilter === 'unassigned' && 'hf-vacancies-toolbar-button-active'
              )}
            >
              <UserPlus className="hf-funnels-filter-leading-icon" />
              {assignmentFilter === 'unassigned' ? 'Без рекрутера' : 'Все назначения'}
            </button>
          )}

          <div className="relative" ref={filtersDropdownRef}>
            <button
              onClick={() => setShowFiltersDropdown(!showFiltersDropdown)}
              className={clsx(
                'hf-funnels-filter hf-vacancies-toolbar-button',
                activeFilterCount > 0 && 'hf-vacancies-toolbar-button-active'
              )}
            >
              <Filter className="hf-funnels-filter-leading-icon" />
              Фильтры
              {activeFilterCount > 0 && (
                <span className="hf-vacancies-filter-count">
                  {activeFilterCount}
                </span>
              )}
              <ChevronDown className={clsx('hf-funnels-filter-icon', showFiltersDropdown && 'hf-funnels-filter-icon-open')} />
            </button>

            <>
              {showFiltersDropdown && (
                <div
                  className="hf-vacancies-filter-menu"
                >
                  <div className="hf-vacancies-filter-menu-head">
                    <span className="font-medium text-sm">Быстрые фильтры</span>
                    {activeFilterCount > 0 && (
                      <button
                        onClick={handleClearAllFilters}
                        className="flex items-center gap-1 text-xs text-[var(--hf-status-red)] hover:text-[var(--hf-red-300)] transition-colors"
                      >
                        <X className="w-3 h-3" />
                        Сбросить
                      </button>
                    )}
                  </div>

                  <div className="p-3 space-y-4 max-h-96 overflow-y-auto">
                    {/* Status Filter (Multi-select) */}
                    <div>
                      <label className="flex items-center gap-2 text-xs font-medium text-[color:var(--hf-vacancies-page-muted)] mb-2">
                        <Briefcase className="w-3.5 h-3.5" />
                        Статус
                      </label>
                      <div className="flex flex-wrap gap-1.5">
                        {(['open', 'pending_review', 'paused', 'closed'] as VacancyStatus[]).map((status) => (
                          <button
                            key={status}
                            onClick={() => handleToggleStatusFilter(status)}
                            className={clsx(
                              'flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg transition-colors',
                              quickFilters.statuses.includes(status)
                                ? 'bg-[var(--hf-status-blue-badge)] border border-[color:var(--hf-status-blue-badge)] text-[var(--hf-status-blue)]'
                                : 'border border-[color:var(--hf-vacancies-page-border)] bg-[var(--hf-vacancies-page-surface)] text-[color:var(--hf-vacancies-page-muted)] hover:bg-[var(--hf-vacancies-page-chip)]'
                            )}
                          >
                            {quickFilters.statuses.includes(status) && <Check className="w-3 h-3" />}
                            {getHuntflowVacancyStatusFilterLabel(status)}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Salary Range Filter */}
                    <div>
                      <label className="flex items-center gap-2 text-xs font-medium text-[color:var(--hf-vacancies-page-muted)] mb-2">
                        <DollarSign className="w-3.5 h-3.5" />
                        Зарплата
                      </label>
                      <div className="flex flex-wrap gap-1.5">
                        {SALARY_RANGES.map((range) => (
                          <button
                            key={range.id}
                            onClick={() => handleSalaryRangeChange(range.id)}
                            className={clsx(
                              'px-2.5 py-1.5 text-xs rounded-lg transition-colors',
                              quickFilters.salaryRange === range.id
                                ? 'bg-[var(--hf-status-blue-badge)] border border-[color:var(--hf-status-blue-badge)] text-[var(--hf-status-blue)]'
                                : 'border border-[color:var(--hf-vacancies-page-border)] bg-[var(--hf-vacancies-page-surface)] text-[color:var(--hf-vacancies-page-muted)] hover:bg-[var(--hf-vacancies-page-chip)]'
                            )}
                          >
                            {range.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Date Range Filter */}
                    <div>
                      <label className="flex items-center gap-2 text-xs font-medium text-[color:var(--hf-vacancies-page-muted)] mb-2">
                        <Calendar className="w-3.5 h-3.5" />
                        Дата создания
                      </label>
                      <div className="flex flex-wrap gap-1.5">
                        {DATE_RANGES.map((range) => (
                          <button
                            key={range.id}
                            onClick={() => handleDateRangeChange(range.id)}
                            className={clsx(
                              'px-2.5 py-1.5 text-xs rounded-lg transition-colors',
                              quickFilters.dateRange === range.id
                                ? 'bg-[var(--hf-status-blue-badge)] border border-[color:var(--hf-status-blue-badge)] text-[var(--hf-status-blue)]'
                                : 'border border-[color:var(--hf-vacancies-page-border)] bg-[var(--hf-vacancies-page-surface)] text-[color:var(--hf-vacancies-page-muted)] hover:bg-[var(--hf-vacancies-page-chip)]'
                            )}
                          >
                            {range.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Results count */}
                  <div className="p-3 border-t border-[color:var(--hf-vacancies-page-border)] bg-[var(--hf-vacancies-page-surface-soft)]">
                    <span className="text-xs text-[color:var(--hf-vacancies-page-soft)]">
                      Показано {filteredVacancies.length} из {vacancies.length} {pluralRu(vacancies.length, 'заявки', 'заявок', 'заявок')}
                    </span>
                  </div>
                </div>
              )}
            </>
          </div>
        </div>
      </div>

      {/* Vacancies list */}
      <div className="hf-vacancies-search-body">
        {error ? (
          <ErrorMessage
            error={error}
            onRetry={handleRetryFetch}
          />
        ) : isLoading ? (
          <div className="hf-vacancies-search-list" aria-label="Загрузка заявок">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="hf-vacancies-search-row hf-vacancies-search-row-skeleton">
                <div className="hf-vacancies-search-skeleton-line hf-vacancies-search-skeleton-title" />
                <div className="hf-vacancies-search-skeleton-line" />
                <div className="hf-vacancies-search-skeleton-line hf-vacancies-search-skeleton-short" />
              </div>
            ))}
          </div>
        ) : filteredVacancies.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <EmptyVacancies
              variant={searchQuery ? 'search' : activeFilterCount > 0 ? 'filter' : 'primary'}
              query={searchQuery}
              onCreate={observer ? undefined : () => setShowCreateModal(true)}
            />
          </div>
        ) : (
          <section className="hf-vacancies-search-results" aria-label="Заявки">
            <div className="hf-vacancies-search-count">
              Найдено заявок: {filteredVacancies.length}
            </div>
            <div className="hf-vacancies-search-list">
              {filteredVacancies.map((vacancy) => {
                const closedDate = getClosedVacancyDate(vacancy);
                const salaryDisplay = getSalaryDisplay(vacancy);
                const employmentLabel = getEmploymentTypeLabel(vacancy.employment_type);
                // Админ — как рекрутёр, если его ЯВНО назначили: тоже может взять заявку в
                // работу (раньше кнопки у админа не было вовсе, 2026-09-10).
                const isRequestForMe = !!user && vacancy.created_by !== user.id &&
                  (isAdmin ? isExplicitlyAssigned(vacancy, user.id) : isAssignedToMe(vacancy));
                const isAlreadyAssigned = vacancy.assigned_to_all || (vacancy.assigned_to && vacancy.assigned_to.length > 0);
                const showAdminAssign = isAdmin && !observer && (
                  vacancy.status === 'pending_review' ||
                  vacancy.status === 'draft' ||
                  (vacancy.status === 'open' && !isAlreadyAssigned)
                );
                const showAdminReassign = isAdmin && !observer && vacancy.status === 'open' && isAlreadyAssigned;
                const showTakeBtn = isRequestForMe && !observer && !hasAlreadyTaken(vacancy);
                const exitOptions = getVacancyExitOptions(vacancy, user?.id, isAdmin);
                const isLive = vacancy.status === 'open' || vacancy.status === 'paused';
                const acceptedCount = vacancy.stage_counts.hired || 0;

                return (
                <ContextMenu
                  key={vacancy.id}
                  items={[
                    ...createVacancyContextMenu(
                      () => handleVacancyClick(vacancy),
                      () => setEditingVacancy(vacancy),
                      () => (isAdmin ? handleDeleteClick(vacancy) : handleDecline(vacancy)),
                      () => handleCopyLink(vacancy)
                    ).flatMap((it) =>
                      // «Отказаться» — только от ещё не взятой заявки; из взятой
                      // выходят через «Выйти из заявки».
                      it.id === 'delete' && !isAdmin
                        ? (hasAlreadyTaken(vacancy) ? [] : [{ ...it, label: 'Отказаться', icon: X }])
                        : [it]
                    ),
                    // Назначенный админ может и отказаться (удаление у него остаётся).
                    ...(isAdmin && user && isExplicitlyAssigned(vacancy, user.id) && !hasAlreadyTaken(vacancy) ? [{
                      id: 'decline',
                      label: 'Отказаться',
                      icon: X,
                      onClick: () => handleDecline(vacancy),
                    }] : []),
                    ...(isLive && exitOptions.canLeave ? [{
                      id: 'leave',
                      label: 'Выйти из заявки',
                      icon: LogOut,
                      onClick: () => handleLeaveClick(vacancy),
                      divider: true,
                    }] : []),
                    ...(isLive && exitOptions.canClose ? [{
                      id: 'close',
                      label: exitOptions.canLeave ? 'Закрыть заявку для всех' : 'Закрыть заявку',
                      icon: XCircle,
                      onClick: () => handleCloseClick(vacancy),
                      divider: !exitOptions.canLeave,
                    }] : []),
                  ]}
                >
                  <article
                    onClick={() => handleVacancyClick(vacancy)}
                    className="hf-vacancies-search-row"
                    aria-label={`${getVacancyStatusLabel(vacancy.status)}: ${vacancy.title?.trim() || 'Без названия'}`}
                  >
                    <div className="hf-vacancies-search-main">
                      <div className="hf-vacancies-search-title-row">
                          <VacancyStatusBadge status={vacancy.status} size="sm" />
                        <button
                          type="button"
                          className={clsx(
                            'hf-vacancies-search-title',
                            !vacancy.title?.trim() && 'hf-vacancies-search-title-empty',
                          )}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleVacancyClick(vacancy);
                          }}
                        >
                          {vacancy.title?.trim() || 'Без названия'}
                        </button>
                        <span className="hf-vacancies-search-kind">{getVacancyKindLabel(vacancy)}</span>
                          {vacancy.applications_count > 0 && (
                          <span className="hf-vacancies-search-candidates">
                            <Users className="hf-vacancies-search-candidates-icon" />
                              {vacancy.applications_count}
                            </span>
                          )}
                        </div>

                      {vacancy.department_name && (
                        <div className="hf-vacancies-search-department">{vacancy.department_name}</div>
                      )}

                      <div className="hf-vacancies-search-meta">
                        <span>Открыта: {formatVacancyDate(vacancy.published_at || vacancy.created_at)}</span>
                        {closedDate && (
                          <>
                            <span className="hf-vacancies-search-dot">·</span>
                            <span>Закрыта: {formatVacancyDate(closedDate)}</span>
                          </>
                        )}
                        </div>

                      <div className="hf-vacancies-search-meta">
                        <span>Последнее действие: {formatVacancyDate(vacancy.updated_at)}</span>
                        </div>

                        {(() => {
                          // «Рекрутер:» = кто ЛИЧНО принял заявку (accepted_by), а не
                          // создатель — 2026-07-09, см. utils/vacancy.ts getAcceptorIds.
                          const names = getAcceptorIds(vacancy).map((uid) =>
                            uid === vacancy.created_by && vacancy.created_by_name
                              ? vacancy.created_by_name
                              : usersById[uid]
                          ).filter((n): n is string => Boolean(n));
                          return names.length > 0 && (
                            <div className="hf-vacancies-search-meta">
                              <span>Рекрутер: {names.join(', ')}</span>
                            </div>
                          );
                        })()}

                      {vacancy.hiring_manager_name && (
                        <div className="hf-vacancies-search-meta">
                          <span>Заказчик: {vacancy.hiring_manager_name}</span>
                        </div>
                        )}

                      {(vacancy.location || salaryDisplay || employmentLabel) && (
                        <div className="hf-vacancies-search-meta hf-vacancies-search-extra">
                          {vacancy.location && <span>{vacancy.location}</span>}
                          {salaryDisplay && <span>{salaryDisplay}</span>}
                          {employmentLabel && <span>{employmentLabel}</span>}
                        </div>
                      )}

                      {acceptedCount > 0 && (
                        <div className="hf-vacancies-search-meta">
                          <span>Оффер принят: {acceptedCount}</span>
                        </div>
                      )}

                      {vacancy.tags.length > 0 && (
                        <div className="hf-vacancies-search-tags">
                          {vacancy.tags.slice(0, 4).map((tag) => (
                            <span key={tag}>{tag}</span>
                          ))}
                          {vacancy.tags.length > 4 && <span>+{vacancy.tags.length - 4}</span>}
                        </div>
                      )}
                    </div>

                    <div className="hf-vacancies-search-side">
                        {vacancy.visible_to_all && (
                          <span className="hf-vacancies-search-chip" title="Видна всем сотрудникам">
                            Общая
                          </span>
                        )}
                        {vacancy.priority > 0 && (
                          <span className={clsx('hf-vacancies-search-chip', vacancy.priority === 2 && 'hf-vacancies-search-chip-urgent')}>
                            {vacancy.priority === 2 ? 'Срочно' : 'Важно'}
                          </span>
                        )}
                          {showAdminAssign && (
                            <button
                              onClick={(e) => { e.stopPropagation(); setAssigningVacancy(vacancy); }}
                            className="hf-vacancies-search-action hf-vacancies-search-action-wide"
                            title={isAlreadyAssigned ? 'Переназначить' : 'Назначить'}
                            >
                            <UserPlus className="hf-vacancies-search-action-icon" />
                              {isAlreadyAssigned ? 'Переназначить' : 'Назначить'}
                            </button>
                          )}
                          {showAdminReassign && (
                            <button
                              onClick={(e) => { e.stopPropagation(); setAssigningVacancy(vacancy); }}
                            className="hf-vacancies-search-action hf-vacancies-search-action-wide"
                            title="Переназначить"
                            >
                            <UserPlus className="hf-vacancies-search-action-icon" />
                              Переназначить
                            </button>
                          )}
                          {showTakeBtn && (
                            <button
                              onClick={(e) => { e.stopPropagation(); handleTakeVacancy(vacancy); }}
                              disabled={takingVacancyId === vacancy.id}
                            className="hf-vacancies-search-action hf-vacancies-search-action-green hf-vacancies-search-action-wide"
                            title="Взять в работу"
                            >
                              {takingVacancyId === vacancy.id ? (
                              <div className="hf-vacancies-search-spinner" />
                              ) : (
                              <PlayCircle className="hf-vacancies-search-action-icon" />
                              )}
                            </button>
                          )}
                        {!observer && (
                        <div className="hf-vacancies-row-actions">
                          <button
                            type="button"
                            className="hf-vacancies-search-action"
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingVacancy(vacancy);
                            }}
                            title="Редактировать"
                          >
                            <Pencil className="hf-vacancies-search-action-icon" />
                          </button>
                          {isLive && exitOptions.canLeave && (
                            <button
                              type="button"
                              className="hf-vacancies-search-action"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleLeaveClick(vacancy);
                              }}
                              title="Выйти из заявки — у остальных она останется в работе"
                            >
                              <LogOut className="hf-vacancies-search-action-icon" />
                            </button>
                          )}
                          {isLive && exitOptions.canClose && (
                            <button
                              type="button"
                              className="hf-vacancies-search-action"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleCloseClick(vacancy);
                              }}
                              title={exitOptions.canLeave ? 'Закрыть заявку для всех участников' : 'Закрыть заявку'}
                            >
                              <Archive className="hf-vacancies-search-action-icon" />
                            </button>
                          )}
                          {isAdmin ? (
                            <button
                              type="button"
                              className="hf-vacancies-search-action"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteClick(vacancy);
                              }}
                              title="Удалить"
                              style={{ color: 'var(--hf-status-red)' }}
                            >
                              <Trash2 className="hf-vacancies-search-action-icon" />
                            </button>
                          ) : !hasAlreadyTaken(vacancy) && (
                            <button
                              type="button"
                              className="hf-vacancies-search-action"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDecline(vacancy);
                              }}
                              disabled={decliningId === vacancy.id}
                              title="Отказаться от заявки"
                              style={{ color: 'var(--hf-status-red)' }}
                            >
                              <X className="hf-vacancies-search-action-icon" />
                            </button>
                          )}
                        </div>
                        )}
                    </div>
                  </article>
                </ContextMenu>
                );
              })}
            </div>
          </section>
        )}
      </div>

      {/* Create/Edit Modal */}
      <AnimatePresence mode="wait">
        {(showCreateModal || editingVacancy) && (
          <VacancyForm
            key={editingVacancy ? `edit-list-${editingVacancy.id}` : 'create'}
            vacancy={editingVacancy || undefined}
            onClose={() => {
              setShowCreateModal(false);
              setEditingVacancy(null);
            }}
            onSuccess={() => {
              setShowCreateModal(false);
              setEditingVacancy(null);
              fetchVacancies();
            }}
          />
        )}
      </AnimatePresence>

      {/* Confirmation Dialog */}
      <ConfirmDialog
        open={confirmDialog.open}
        title={confirmCopy.title}
        message={confirmCopy.message}
        confirmLabel={confirmCopy.confirmLabel}
        cancelLabel="Отмена"
        variant={confirmCopy.variant}
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelConfirm}
        loading={deleteLoading}
      />

      {/* Assign Modal */}
      {assigningVacancy && (
        <AssignVacancyModal
          vacancy={assigningVacancy}
          onClose={() => setAssigningVacancy(null)}
          onAssigned={() => {
            setAssigningVacancy(null);
            fetchVacancies();
          }}
        />
      )}

      {previewVacancy && (
        <SidebarRequestPreviewModal
          vacancy={previewVacancy}
          onClose={() => setPreviewVacancy(null)}
          onEdit={() => {
            setPreviewVacancy(null);
            setEditingVacancy(previewVacancy);
          }}
          onTaken={() => {
            setPreviewVacancy(null);
            fetchVacancies();
          }}
        />
      )}
    </div>
  );
}
