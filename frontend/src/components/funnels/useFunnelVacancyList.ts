import { useEffect, useMemo, useRef, useState } from "react";
import type { SetURLSearchParams } from "react-router-dom";
import { getAllVacancies } from "@/services/api/vacancies";
import { getAssignableUsers } from "@/services/api";
import type { User, Vacancy, VacancyStatus } from "@/types";
import { getAcceptorIds, isPersonallyActive, isVacancyParticipant } from "@/utils/vacancy";
import {
  HUNTFLOW_VACANCY_STATUS_FILTERS,
  getHuntflowVacancyStatusFilterLabel,
} from "@/components/hr/huntflowVacancyStatus";

// Список вакансий «Мои вакансии»: какие воронки видит человек, фильтры по
// статусу и рекрутёру, группы рекрутёров для админа, меню фильтров
// (вынесено из RecruiterFunnelsPage, 20.10.2026, без изменения поведения).

const STATUS_FILTER_IDS = new Set<string>(HUNTFLOW_VACANCY_STATUS_FILTERS.map((f) => f.id));

// Группировка админ-вида (2026-07-09): раньше группировали по created_by (кто
// СОЗДАЛ заявку) — но создатель часто просто раздаёт заявки, не работая над
// ними лично. Реальный «владелец» воронки — тот, кто лично нажал «Взять в
// работу» (extra_data.accepted_by). Заявку могут принять НЕСКОЛЬКО
// рекрутёров (общая воронка) — тогда она показывается у КАЖДОГО из них.
// СТРОГО accepted_by, БЕЗ фолбэка на created_by (в отличие от getAcceptorIds,
// utils/vacancy.ts) — иначе старые вакансии без личного принятия
// приписывались создателю, и счётчик «N вакансий» у него расходился с тем,
// что реально показывает сайдбар «Мои вакансии» (тот же баг, что чинили в
// Layout.tsx funnelsPickerRecruiters). Пустой accepted_by → uid=0
// «Без исполнителя», чтобы заявка не выпала из группировки совсем.

export function groupAcceptorIds(v: Vacancy): number[] {
  const acceptedBy = ((v.extra_data as Record<string, unknown> | undefined)?.accepted_by as number[] | undefined) || [];
  return acceptedBy.length > 0 ? acceptedBy : [0];
}

export function resolveGroupUserName(
  uid: number,
  v: Vacancy,
  usersMap: Record<number, string>,
  currentUser: { id?: number; name?: string } | null | undefined,
): string {
  if (uid === v.created_by && v.created_by_name) return v.created_by_name;
  if (usersMap[uid]) return usersMap[uid];
  if (currentUser && uid === currentUser.id) return currentUser.name || 'Мои';
  return 'Без исполнителя';
}

// ==================== Types ====================

export interface RecruiterGroup {
  userId: number;
  userName: string;
  vacancies: Vacancy[];
  expanded: boolean;
}

export interface FunnelVacancyListParams {
  vacancies: Vacancy[];
  fetchVacancies: (silent?: boolean) => unknown;
  user: User | null;
  isHrAdmin: boolean;
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
  selectedVacancyId: number | null;
}

export function useFunnelVacancyList(p: FunnelVacancyListParams) {
  const { vacancies, fetchVacancies, user, isHrAdmin, searchParams, setSearchParams, selectedVacancyId } = p;
  const [search, setSearch] = useState('');
  const [recruiterSearch, setRecruiterSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<VacancyStatus | 'all' | 'deleted'>('all');
  const [selectedRecruiterFilter, setSelectedRecruiterFilter] = useState<number | null>(null);
  // «Удалённые»: мягко-удалённые вакансии тянем отдельным запросом (deleted=true).
  const [deletedVacancies, setDeletedVacancies] = useState<Vacancy[]>([]);
  useEffect(() => {
    if (statusFilter === 'deleted') {
      getAllVacancies({ deleted: true }).then(setDeletedVacancies).catch(() => setDeletedVacancies([]));
    }
  }, [statusFilter]);
  const [showStatusMenu, setShowStatusMenu] = useState(false);
  const [showRecruiterMenu, setShowRecruiterMenu] = useState(false);
  const [usersMap, setUsersMap] = useState<Record<number, string>>({});
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const recruiterAutoExpandedRef = useRef(false);
  const statusMenuRef = useRef<HTMLDivElement>(null);
  const recruiterMenuRef = useRef<HTMLDivElement>(null);


  // Load data
  useEffect(() => {
    fetchVacancies();
  }, [fetchVacancies]);

  useEffect(() => {
    const urlStatus = searchParams.get('status');
    const nextStatus =
      urlStatus && STATUS_FILTER_IDS.has(urlStatus)
        ? (urlStatus as VacancyStatus | 'all' | 'deleted')
        : 'all';
    if (nextStatus !== statusFilter) {
      setStatusFilter(nextStatus);
    }
  }, [searchParams, statusFilter]);

  // Выбор рекрутёра в попапе «Мои вакансии» сайдбара (Layout.tsx) шлёт сюда
  // ?recruiter=<id> — раньше он просто делал navigate("/my-funnels") без
  // параметра, поэтому клик по ЛЮБОМУ рекрутёру в попапе визуально ничего не
  // менял на этой странице (уже открытый общий вид «Все вакансии» оставался
  // как есть). Теперь синхронизируем с тем же selectedRecruiterFilter, что и
  // родное меню «Рекрутеры» этой страницы.
  useEffect(() => {
    const urlRecruiter = searchParams.get('recruiter');
    const parsed = urlRecruiter ? Number(urlRecruiter) : NaN;
    const nextFilter = Number.isFinite(parsed) ? parsed : null;
    if (nextFilter !== selectedRecruiterFilter) {
      setSelectedRecruiterFilter(nextFilter);
    }
  }, [searchParams]);

  useEffect(() => {
    // Резолвер id → имя нужен ВСЕМ, не только admin-виду: обычный рекрутёр
    // тоже видит «Рекрутер: ...» с именами других принявших (общая воронка,
    // 2026-07-09). getUsers() отдаёт список по ОТДЕЛУ (для member — пусто,
    // если отдел не назначен), поэтому берём assignable-users — тот же
    // org-wide HR-пул, что и в дропдауне «Назначить рекрутёрам», без гейта.
    getAssignableUsers().then((users) => {
      const map: Record<number, string> = {};
      users.forEach((u) => { map[u.id] = u.name; });
      setUsersMap(map);
    }).catch(() => {});
  }, []);

  const scopedVacancies = useMemo(() => {
    if (statusFilter === 'deleted') {
      return (!isHrAdmin && user)
        ? deletedVacancies.filter((v) => isVacancyParticipant(v, user.id))
        : deletedVacancies;
    }
    let result = vacancies;
    // Исходные заявки, у которых уже есть клон («взяли в работу»), —
    // это НЕ рабочие вакансии, а заявки. После «Взять в работу» оригинал
    // переходит в status=open и без этого фильтра дублировал клон в списке
    // вакансий рекрутёра (видно как два одинаковых «Тест»).
    const clonedSourceIds = new Set<number>();
    vacancies.forEach((v) => {
      const src = (v.extra_data as Record<string, unknown> | undefined)
        ?.cloned_from_request_id;
      if (typeof src === 'number') clonedSourceIds.add(src);
    });
    result = result.filter((v) => !clonedSourceIds.has(v.id));
    // Общая модель (2026-07-02): рекрутёр видит воронки, где он УЧАСТНИК —
    // создатель ИЛИ назначенный (assigned_to/assigned_to_all), минус те, из
    // которых он «закрыл у себя» (dismissed_by). Клонов больше нет — все
    // участники работают в одной воронке и видят всех её кандидатов.
    // 2026-07-08: но «Мои вакансии» показывает только ЛИЧНО принятые
    // (isPersonallyActive) — назначенный, ещё не нажавший «Взять в работу»,
    // видит её в «Заявки», а не здесь, даже если статус уже open (её взял
    // кто-то другой из назначенных).
    // Наблюдатель (is_readonly) — ментор: видит ВСЕ воронки, а не только личные,
    // поэтому его этот фильтр не касается (бэк уже отдаёт ему все вакансии).
    if (!isHrAdmin && !user?.is_readonly && user) {
      result = result.filter((v) => isPersonallyActive(v, user.id));
    }
    if (statusFilter !== 'all') {
      result = result.filter((v) => v.status === statusFilter);
    } else {
      // Заявки (pending_review/draft) живут в разделе «Заявки», а НЕ в активных
      // воронках «Мои вакансии». Иначе только что созданная заявка сразу висела
      // как «в работе» под создателем, будто он её уже взял. Принятой (взятой в
      // работу) она становится через «Взять в работу» → клон со статусом open.
      result = result.filter(
        (v) => v.status !== 'pending_review' && v.status !== 'draft',
      );
    }
    return result;
  }, [vacancies, deletedVacancies, user, isHrAdmin, statusFilter]);

  // Filter vacancies
  const filteredVacancies = useMemo(() => {
    let result = scopedVacancies;
    if (isHrAdmin && selectedRecruiterFilter !== null) {
      result = result.filter((v) => groupAcceptorIds(v).includes(selectedRecruiterFilter));
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((v) => {
        return v.title.toLowerCase().includes(q) || Boolean(v.department_name?.toLowerCase().includes(q));
      });
    }
    return result;
  }, [scopedVacancies, isHrAdmin, selectedRecruiterFilter, search]);

  useEffect(() => {
    if (!isHrAdmin || recruiterAutoExpandedRef.current || scopedVacancies.length === 0) return;

    const groups = new Map<number, string>();
    scopedVacancies.forEach((v) => {
      groupAcceptorIds(v).forEach((uid) => {
        if (!groups.has(uid)) {
          groups.set(uid, resolveGroupUserName(uid, v, usersMap, user));
        }
      });
    });

    const firstGroup = Array.from(groups.entries()).sort((a, b) => a[1].localeCompare(b[1]))[0];
    if (!firstGroup) return;

    recruiterAutoExpandedRef.current = true;
    setExpandedGroups(new Set([firstGroup[0]]));
  }, [isHrAdmin, scopedVacancies, user, usersMap]);

  // Группировка по тому, кто ЛИЧНО принял заявку в работу (accepted_by), а не
  // по создателю — см. getAcceptorIds выше. Заявка с несколькими принявшими
  // показывается у КАЖДОГО (сумма счётчиков по группам может быть больше
  // общего числа заявок — это ожидаемо; «Найдено вакансий: N» ниже считает
  // по scopedVacancies/filteredVacancies напрямую, без дублей).
  const recruiterGroups = useMemo((): RecruiterGroup[] => {
    const groups: Record<number, RecruiterGroup> = {};
    const vacs = scopedVacancies;
    vacs.forEach((v) => {
      groupAcceptorIds(v).forEach((uid) => {
        if (!groups[uid]) {
          groups[uid] = {
            userId: uid,
            userName: resolveGroupUserName(uid, v, usersMap, user),
            vacancies: [],
            expanded: !isHrAdmin || expandedGroups.has(uid),
          };
        }
        groups[uid].vacancies.push(v);
      });
    });
    return Object.values(groups).sort((a, b) => a.userName.localeCompare(b.userName));
  }, [scopedVacancies, isHrAdmin, usersMap, expandedGroups, user]);

  const filteredRecruiterCount = useMemo(() => {
    const ids = new Set<number>();
    filteredVacancies.forEach((vacancy) => {
      getAcceptorIds(vacancy).forEach((uid) => ids.add(uid));
    });
    return ids.size;
  }, [filteredVacancies]);

  const recruiterFilterOptions = useMemo(() => (
    recruiterGroups.map((group) => ({
      id: group.userId,
      name: group.userName,
      count: group.vacancies.length,
    }))
  ), [recruiterGroups]);

  const statusFilterLabel = useMemo(() => {
    if (statusFilter === 'all') return 'Все вакансии';
    return getHuntflowVacancyStatusFilterLabel(statusFilter) || 'Все вакансии';
  }, [statusFilter]);

  const recruiterFilterLabel = useMemo(() => {
    if (selectedRecruiterFilter === null) return 'Все';
    return recruiterFilterOptions.find((item) => item.id === selectedRecruiterFilter)?.name || 'Все';
  }, [recruiterFilterOptions, selectedRecruiterFilter]);

  const visibleRecruiterGroups = useMemo(() => {
    if (!recruiterSearch.trim()) return recruiterGroups;
    const q = recruiterSearch.trim().toLowerCase();
    return recruiterGroups.filter((group) => group.userName.toLowerCase().includes(q));
  }, [recruiterGroups, recruiterSearch]);

  const toggleGroup = (userId: number) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  };

  const handleStatusFilterChange = (nextStatus: VacancyStatus | 'all' | 'deleted') => {
    setStatusFilter(nextStatus);
    setShowStatusMenu(false);
    if (!selectedVacancyId) {
      setSearchParams(nextStatus === 'all' ? {} : { status: nextStatus });
    }
  };

  const handleRecruiterFilterChange = (userId: number | null) => {
    setShowRecruiterMenu(false);
    if (!isHrAdmin) {
      setSelectedRecruiterFilter(null);
      return;
    }
    setSelectedRecruiterFilter(userId);
    if (userId !== null) {
      setExpandedGroups((prev) => new Set(prev).add(userId));
    }
    // ?recruiter — единый источник истины для скоупа кандидатов по рекрутёру.
    // Пишем его в URL и закрываем вакансию (смена рекрутёра = новый контекст).
    const params: Record<string, string> = {};
    if (statusFilter !== 'all') params.status = statusFilter;
    if (userId !== null) params.recruiter = String(userId);
    setSearchParams(params);
  };

  // Своё меню «Рекрутеры» этой страницы — только для HR-админа. Выбор владельца
  // из сайдбара (?recruiter=) при этом действует для ВСЕХ ролей: рекрутёр в
  // «Вакансии: Мария» видит кандидатов Марии (решение юзера 2026-09-10; раньше
  // здесь фильтр у не-админа сбрасывался и он видел всю воронку).
  useEffect(() => {
    if (isHrAdmin) return;
    setShowRecruiterMenu(false);
    setRecruiterSearch('');
  }, [isHrAdmin]);

  useEffect(() => {
    if (!showStatusMenu && !showRecruiterMenu) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as Node;
      if (statusMenuRef.current && !statusMenuRef.current.contains(target)) {
        setShowStatusMenu(false);
      }
      if (recruiterMenuRef.current && !recruiterMenuRef.current.contains(target)) {
        setShowRecruiterMenu(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showStatusMenu, showRecruiterMenu]);

  return { deletedVacancies, expandedGroups, filteredRecruiterCount, filteredVacancies, handleRecruiterFilterChange, handleStatusFilterChange, recruiterAutoExpandedRef, recruiterFilterLabel, recruiterFilterOptions, recruiterGroups, recruiterMenuRef, recruiterSearch, scopedVacancies, search, selectedRecruiterFilter, setDeletedVacancies, setExpandedGroups, setRecruiterSearch, setSearch, setSelectedRecruiterFilter, setShowRecruiterMenu, setShowStatusMenu, setStatusFilter, setUsersMap, showRecruiterMenu, showStatusMenu, statusFilter, statusFilterLabel, statusMenuRef, toggleGroup, usersMap, visibleRecruiterGroups };
}
