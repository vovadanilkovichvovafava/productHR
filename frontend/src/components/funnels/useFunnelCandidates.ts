import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SetURLSearchParams } from "react-router-dom";
import { getApplications, getFunnelRecruiters, type FunnelRecruiters } from "@/services/api";
import type { User, Vacancy, VacancyApplication } from "@/types";
import { getAcceptorIds, isPersonallyActive } from "@/utils/vacancy";
import { funnelSearchMatch } from "@/utils/translit";

// Кандидаты открытой воронки: кого показываем (фильтр «Рекрутёр: …», рекрутёр
// из сайдбара, режим шаринг-ссылки), загрузка с защитой от опоздавших ответов и
// тихий опрос (вынесено из RecruiterFunnelsPage, 20.10.2026).

// F5 открытой воронки: документ перезагружен ровно на текущем URL. Проверка
// идемпотентна: StrictMode в dev дважды зовёт инициализатор useState, а страница
// после загрузки может смонтироваться повторно (гарды ролей/авторизации) — всё
// это та же перезагрузка. Отметка гаснет, как только адрес стал другим: значит,
// юзер уже ходил по приложению, и следующий заход с ?entity= — снова ссылка.
let documentReloadHref: string | null | undefined;
function isDocumentReloadOfCurrentUrl(): boolean {
  if (documentReloadHref === undefined) {
    try {
      const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
      documentReloadHref = nav?.type === 'reload' ? nav.name : null;
    } catch {
      documentReloadHref = null;
    }
  }
  if (documentReloadHref !== window.location.href) documentReloadHref = null;
  return documentReloadHref != null;
}

// Состояние воронки, которое должно пережить F5 в этой вкладке, но не новую
// вкладку и не новую ссылку, — sessionStorage.
const SHARED_ENTRY_KEY = 'funnel_shared_entry';
const VIEW_OWNER_KEY = 'funnel_view_owner';
function readFunnelSession<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}
function writeFunnelSession(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* приватный режим — просто не запомним */
  }
}
function removeFunnelSession(key: string) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* noop */
  }
}

/** Чьих кандидатов показываем в воронке: отмеченные рекрутёры (один или
 *  несколько, владелец 21.10.2026) или все. */
export type FunnelViewOwner = number[] | 'all';

/** Строка-ключ выбора: по ней сравниваем выборы и перезагружаем список —
 *  массив каждую отрисовку новый, и эффекты на него крутились бы по кругу. */
export function funnelViewKey(owner: FunnelViewOwner): string {
  return owner === 'all' ? 'all' : [...new Set(owner)].sort((a, b) => a - b).join(',');
}
function parseFunnelViewKey(key: string): FunnelViewOwner {
  return key === 'all' ? 'all' : key.split(',').filter(Boolean).map(Number);
}

export interface FunnelCandidatesParams {
  selectedVacancyId: number | null;
  selectedVacancy: Vacancy | undefined;
  funnelBlocked: boolean;
  user: User | null;
  isSuperadmin: boolean;
  selectedRecruiterFilter: number | null;
  candidateSearch: string;
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
  fetchVacancies: (silent?: boolean) => unknown;
  /** Открыли другую воронку — страница сбрасывает выбор. */
  onVacancyOpened: () => void;
}

export function useFunnelCandidates(p: FunnelCandidatesParams) {
  const {
    selectedVacancyId, selectedVacancy, funnelBlocked, user, isSuperadmin,
    selectedRecruiterFilter, candidateSearch, searchParams, setSearchParams, fetchVacancies,
  } = p;
  const onVacancyOpenedRef = useRef(p.onVacancyOpened);
  onVacancyOpenedRef.current = p.onVacancyOpened;
  // Открыли по ШАРИНГ-ССЫЛКЕ на кандидата (в URL сразу есть и ?v=, и ?entity=).
  // В этом режиме грузим кандидатов БЕЗ скоупа по рекрутёру — иначе чужой кандидат
  // (added другим рекрутёром) не попадает в список и окно пустое (баг Марии по
  // ссылке) — а сам кандидат из ссылки остаётся в списке при любом фильтре.
  // Хранится id кандидата из URL на момент открытия: живой ?entity= не годится,
  // страница переписывает его при каждом выборе кандидата.
  //  • F5 — НЕ новая ссылка: ?entity= туда записала сама страница. F5 обязан
  //    вернуть ровно то, что было на экране (решение юзера 2026-09-10), поэтому
  //    кандидат из ссылки запоминается в sessionStorage вкладки и после F5
  //    восстанавливается оттуда, а не из ?entity=. Иначе после перезагрузки в
  //    «воронке Марии» застревал последний открытый чужой кандидат (прод,
  //    2026-09-10: Шатилов с меткой Влады в «Вакансии: Мария»).
  //  • Режим живёт до первого своего действия — смена воронки, рекрутёра или
  //    фильтр «Рекрутёр: …» (см. setViewOwner ниже).
  const [sharedEntryEntityId, setSharedEntryEntityId] = useState<number | null>(() => {
    const vacancyId = Number(searchParams.get('v')) || null;
    if (vacancyId == null) return null;
    if (isDocumentReloadOfCurrentUrl()) {
      const saved = readFunnelSession<{ v: number; entityId: number }>(SHARED_ENTRY_KEY);
      return saved?.v === vacancyId ? saved.entityId : null;
    }
    return Number(searchParams.get('entity')) || null;
  });
  useEffect(() => {
    if (sharedEntryEntityId == null || selectedVacancyId == null) removeFunnelSession(SHARED_ENTRY_KEY);
    else writeFunnelSession(SHARED_ENTRY_KEY, { v: selectedVacancyId, entityId: sharedEntryEntityId });
  }, [sharedEntryEntityId, selectedVacancyId]);
  const arrivedViaSharedCandidate = sharedEntryEntityId != null;
  const [candidates, setCandidates] = useState<VacancyApplication[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);

  // ШАРИНГ-ССЫЛКА без ?recruiter=: восстанавливаем «путь» воронки. Ссылка-дип-линк
  // рекрутёра обычно вида ?v=176&entity=8913&stage=applied (БЕЗ recruiter) → сайдбар
  // не знал владельца и показывал голое «Мои вакансии» вместо «Вакансии: Мария».
  // Выводим владельца из самой вакансии (accepted_by/created_by) и подставляем в URL —
  // дальше существующий механизм (?recruiter= → pickerOwnerId в Layout) поднимает
  // контекст сайдбара. Только для шаринг-сессии, только когда вакансия уже загружена.
  useEffect(() => {
    if (!arrivedViaSharedCandidate) return;
    if (searchParams.get('recruiter')) return;
    if (!selectedVacancy) return;
    const ownerId = getAcceptorIds(selectedVacancy)[0];
    if (!ownerId) return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('recruiter', String(ownerId));
        return next;
      },
      { replace: true },
    );
  }, [arrivedViaSharedCandidate, selectedVacancy, searchParams, setSearchParams]);

  // Load candidates when vacancy selected
  useEffect(() => {
    if (!selectedVacancyId || funnelBlocked) {
      setCandidates([]);
      return;
    }
    loadCandidates(selectedVacancyId);
    onVacancyOpenedRef.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedVacancyId]);

  // Счётчик-версия загрузок. Тихий focus-refresh (alt-tab) или гонка запросов
  // могли прилететь со СТАРЫМ списком и перезаписать свежее состояние — напр.
  // вернуть только что снятого кандидата («удаляй дважды»). Применяем результат
  // загрузки ТОЛЬКО если это последний запрос; любая мутация бампает счётчик.
  const loadSeqRef = useRef(0);
  // Чьих кандидатов показываем — фильтр «Рекрутёр: …» над воронкой (владелец,
  // 21.10.2026; до этого — кнопка «Только мои» / «Показать всех»):
  //  • по умолчанию — СВОИХ: тех, кого человек добавил сам. Чужие «не
  //    прилетают» (владелец: «им не должны прилетать кандидаты от других
  //    рекрутёров»);
  //  • выбран рекрутёр в сайдбаре («Вакансии: Мария», ?recruiter=) — его;
  //  • суперадмин и наблюдатель, а также воронка не в работе у человека — все:
  //    своих кандидатов там нет, иначе воронка выглядела бы пустой;
  //  • в фильтре можно выбрать любого рекрутёра воронки или «Все рекрутёры» —
  //    их кандидатов и смотрят, и правят (сервер это разрешает всем).
  // Выбор временный: ушёл из воронки или сменил рекрутёра в сайдбаре — снова
  // по умолчанию. F5 его сохраняет (sessionStorage вкладки), как и всё, что
  // человек выбрал на странице.
  const worksOnFunnel = !selectedVacancy || (!!user && isPersonallyActive(selectedVacancy, user.id));
  const defaultViewOwner: FunnelViewOwner =
    selectedRecruiterFilter != null
      ? [selectedRecruiterFilter]
      : user && worksOnFunnel && !(isSuperadmin || user.is_readonly)
        ? [user.id]
        : 'all';
  const [viewOverride, setViewOverride] = useState<FunnelViewOwner | null>(() => {
    if (!isDocumentReloadOfCurrentUrl()) return null;
    const saved = readFunnelSession<{ v: number | null; r: number | null; owner: FunnelViewOwner }>(VIEW_OWNER_KEY);
    return saved != null &&
      saved.v === (Number(searchParams.get('v')) || null) &&
      saved.r === (Number(searchParams.get('recruiter')) || null)
      && (saved.owner === 'all' || (Array.isArray(saved.owner) && saved.owner.length > 0))
      ? saved.owner
      : null;
  });
  const viewKey = funnelViewKey(viewOverride ?? defaultViewOwner);
  const viewOwner = useMemo(() => parseFunnelViewKey(viewKey), [viewKey]);
  useEffect(() => {
    if (viewOverride == null || selectedVacancyId == null) removeFunnelSession(VIEW_OWNER_KEY);
    else writeFunnelSession(VIEW_OWNER_KEY, { v: selectedVacancyId, r: selectedRecruiterFilter, owner: viewOverride });
  }, [viewOverride, selectedVacancyId, selectedRecruiterFilter]);
  const setViewOwner = useCallback((owner: FunnelViewOwner) => {
    if (owner !== 'all' && owner.length === 0) return; // пустой выбор = пустая воронка
    setSharedEntryEntityId(null);
    setViewOverride(owner);
  }, []);
  // Уход в другую воронку или к другому рекрутёру заканчивает режим шаринг-ссылки
  // и сбрасывает фильтр. null → X по рекрутёру — не уход: это URL-синк на
  // маунте и восстановление владельца для ссылки без ?recruiter= (эффект выше).
  const sharedEntryContextRef = useRef({ v: selectedVacancyId, r: selectedRecruiterFilter });
  useEffect(() => {
    const prev = sharedEntryContextRef.current;
    sharedEntryContextRef.current = { v: selectedVacancyId, r: selectedRecruiterFilter };
    const vacancyChanged = prev.v !== selectedVacancyId;
    const recruiterChanged = prev.r != null && prev.r !== selectedRecruiterFilter;
    if (vacancyChanged || recruiterChanged) {
      setSharedEntryEntityId(null);
      setViewOverride(null);
    }
  }, [selectedVacancyId, selectedRecruiterFilter]);

  // Что просим у сервера. ШАРИНГ-ССЫЛКА — всю воронку: кандидат из ссылки
  // обязан быть в списке, кто бы его ни добавил; сужаем уже на фронте
  // (recruiterScopedCandidates), оставляя его.
  const candidateScopeKey = arrivedViaSharedCandidate ? 'all' : viewKey;
  const candidateScope = useMemo(() => parseFunnelViewKey(candidateScopeKey), [candidateScopeKey]);
  const [recruiterOptions, setRecruiterOptions] = useState<FunnelRecruiters | null>(null);
  const loadCandidates = useCallback(async (vacancyId: number, silent = false) => {
    const seq = ++loadSeqRef.current;
    if (!silent) setCandidatesLoading(true);
    try {
      const [apps, recruiters] = await Promise.all([
        getApplications(vacancyId, undefined, candidateScope),
        getFunnelRecruiters(vacancyId).catch(() => null),
      ]);
      if (seq === loadSeqRef.current) {
        setCandidates(apps);
        setRecruiterOptions(recruiters);
      }
    } catch {
      if (!silent && seq === loadSeqRef.current) setCandidates([]);
    } finally {
      if (!silent) setCandidatesLoading(false);
    }
  }, [candidateScopeKey]);

  // Сменили фильтр или рекрутёра в сайдбаре при открытой воронке —
  // перезагружаем кандидатов под новый выбор (тихо, без скелетона).
  useEffect(() => {
    if (selectedVacancyId && !funnelBlocked) loadCandidates(selectedVacancyId, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateScopeKey]);

  // Авто-refresh когда юзер возвращается на вкладку браузера —
  // например, после добавления кандидата через волшебную кнопку из
  // другой вкладки. Иначе нужен F5 чтобы увидеть новых.
  // ВАЖНО: рефреш ТИХИЙ (silent) — без скелетонов-лоадеров. Раньше обычный
  // alt-tab перерисовывал список со скелетоном и выглядел как перезагрузка
  // страницы. Плюс троттл: не чаще раза в 3с.
  useEffect(() => {
    let lastRun = 0;
    const onFocus = () => {
      const now = Date.now();
      if (now - lastRun < 3000) return;
      lastRun = now;
      if (selectedVacancyId && !funnelBlocked) loadCandidates(selectedVacancyId, true);
      fetchVacancies(true);
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [selectedVacancyId, loadCandidates, fetchVacancies, funnelBlocked]);

  // Поллинг воронки каждые 15с (только когда вкладка видима): на проде WS
  // ненадёжен, поэтому тихо подтягиваем кандидатов и вакансии — иначе рекрутёр,
  // сидя на странице воронки, не видел изменений без F5 (доска «Все кандидаты»
  // уже так поллится). Тихий refresh, без скелетонов.
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      if (selectedVacancyId && !funnelBlocked) loadCandidates(selectedVacancyId, true);
      fetchVacancies(true);
    }, 15000);
    return () => clearInterval(id);
  }, [selectedVacancyId, loadCandidates, fetchVacancies, funnelBlocked]);

  // Filter candidates by search — умный матч по ИМЕНИ (транслит RU↔EN + любой
  // порядок слов + опечатки, как серверный pg_trgm в «Все кандидаты»); по
  // email/телефону — обычная подстрока; по telegram — ВСЕ ники кандидата +
  // текст комментариев карточки; запрос с «@» — строгий режим (только тг/комменты).
  // Сужение по рекрутёру делает сервер. Фронт сужает сам только в режиме
  // ШАРИНГ-ССЫЛКИ (загружена вся воронка): кандидат из ссылки остаётся в
  // списке, пока юзер не сменил контекст, — иначе ссылка на чужого кандидата
  // открывала бы пустое окно. Заявка без автора — кандидат владельца вакансии,
  // как у метки «HR: …» и серверного скоупа (recruiter_owns_application).
  const recruiterScopedCandidates = useMemo(() => {
    if (candidateScopeKey === viewKey || viewOwner === 'all') return candidates;
    const owners = new Set(viewOwner);
    const vacancyOwner = selectedVacancy?.created_by;
    return candidates.filter(
      (c) =>
        (c.created_by != null && owners.has(c.created_by)) ||
        (c.created_by == null && vacancyOwner != null && owners.has(vacancyOwner)) ||
        c.entity_id === sharedEntryEntityId,
    );
  }, [candidates, candidateScopeKey, viewKey, viewOwner, sharedEntryEntityId, selectedVacancy?.created_by]);

  const filteredCandidates = useMemo(() => {
    if (!candidateSearch.trim()) return recruiterScopedCandidates;
    return recruiterScopedCandidates.filter((c) => funnelSearchMatch(candidateSearch, c));
  }, [recruiterScopedCandidates, candidateSearch]);

  return {
    candidates, setCandidates, candidatesLoading, loadCandidates, loadSeqRef,
    recruiterScopedCandidates, filteredCandidates,
    viewOwner, setViewOwner, recruiterOptions,
  };
}
