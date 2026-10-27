import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SetURLSearchParams } from "react-router-dom";
import type { VacancyApplication } from "@/types";
import { computeEntityParamUpdate, shouldAdoptUrlEntity } from "@/utils/candidateUrl";
import { pinMovedCandidate } from "@/utils/vacancy";
import type { FunnelStagesConfig } from "./useFunnelStages";

// Вкладка воронки, выбранный кандидат и их связь с адресом (?stage=, ?entity=)
// — вынесено из RecruiterFunnelsPage (20.10.2026) без изменения поведения.
// Здесь живут правила, которые чаще всего ломались: «перехожу на статус —
// пустое окно» (Мария), «открывает последнюю, а не первую», «ссылка на
// кандидата открыла другого», «F5 сбросил вкладку», «перемещённый кандидат
// пропал из списка». Сторож — __tests__/useFunnelSelection.test.ts.
//
// ВАЖНО: в состоянии хранится id ЗАЯВКИ (selectedCandidateId), а в адресе —
// entity_id (id человека), для совместимости ссылок с «Все кандидаты».

export interface FunnelSelectionParams {
  candidates: VacancyApplication[];
  /** Кандидаты после «Только мои» и поиска. */
  filteredCandidates: VacancyApplication[];
  candidateSearch: string;
  stagesConfig: FunnelStagesConfig;
  selectedVacancyId: number | null;
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
  /** Открыт другой кандидат — страница показывает его резюме. */
  onCandidateFocused: () => void;
}

export function useFunnelSelection(p: FunnelSelectionParams) {
  const {
    candidates, filteredCandidates, candidateSearch, stagesConfig, selectedVacancyId,
    searchParams, setSearchParams,
  } = p;
  const onFocusedRef = useRef(p.onCandidateFocused);
  onFocusedRef.current = p.onCandidateFocused;

  const [selectedTab, setSelectedTab] = useState<string>("all");
  const [selectedCandidateId, setSelectedCandidateId] = useState<number | null>(null);
  // Заявка, которую только что двигали (или чей перевод отменили): остаётся в
  // списке текущей вкладки, пока рекрутёр сам не уйдёт с неё.
  const [stickyCandidateId, setStickyCandidateId] = useState<number | null>(null);

  // Group candidates by stage columns (handles virtual stages via maps_to)
  const groupedByStage = useMemo(() => {
    const map = new Map<string, VacancyApplication[]>();
    for (const key of stagesConfig.keys) map.set(key, []);
    for (const c of filteredCandidates) {
      // Find which column(s) this candidate's stage maps to
      const targetKeys = stagesConfig.enumToKeys[c.stage];
      if (targetKeys && targetKeys.length > 0) {
        // Put in first matching column
        map.get(targetKeys[0])!.push(c);
      } else {
        // Этап аппликации не маппится ни в одну ВИДИМУЮ колонку (например,
        // кандидата добавили со stage=applied, а в кастомной воронке нет
        // колонки «Новый»). Раньше он уезжал в отдельную группу, которой нет в
        // vacancyVisibleStageKeys → колонка не рендерилась и кандидат ИСЧЕЗАЛ.
        // Теперь кладём его в первую видимую колонку, чтобы он не пропадал.
        const fallbackKey = stagesConfig.keys[0];
        if (fallbackKey) {
          map.get(fallbackKey)!.push(c);
        } else {
          if (!map.has(c.stage)) map.set(c.stage, []);
          map.get(c.stage)!.push(c);
        }
      }
    }
    const result: [string, VacancyApplication[]][] = [];
    for (const [key, items] of map) {
      result.push([key, items]);
    }
    return result;
  }, [filteredCandidates, stagesConfig]);

  // Derive grouped as a Record for quick count lookup by key
  const groupedByStageMap = useMemo(() => {
    const map: Record<string, VacancyApplication[]> = {};
    for (const [key, items] of groupedByStage) {
      map[key] = items;
    }
    return map;
  }, [groupedByStage]);

  const vacancyWorkflowKeys = stagesConfig.keys;

  const vacancyVisibleStageKeys = useMemo(() => {
    return vacancyWorkflowKeys;
  }, [vacancyWorkflowKeys]);

  // Master-detail derived data
  const selectedCandidate = useMemo(
    () => candidates.find(c => c.id === selectedCandidateId) || null,
    [candidates, selectedCandidateId],
  );

  // Durable per-candidate deep-link (?entity=ID), как в «Все кандидаты».
  // ВАЖНО: в воронке state хранит id ЗАЯВКИ (selectedCandidateId === VacancyApplication.id),
  // а в URL пишем entity_id (id человека) — для кросс-страничной совместимости. Поэтому
  // через помощники candidateUrl мы прогоняем именно entity_id выбранного кандидата.
  const urlEntity = searchParams.get('entity');
  // Предыдущий entity_id для ЗЕРКАЛА (selection -> URL): отличает настоящее закрытие
  // (entity был -> стал null) от ещё не доехавшего диплинка (null -> null) → не стираем ?entity=.
  const prevMirrorEntityIdRef = useRef<number | null>(null);
  // Предыдущий entity_id для АДОПТА (URL -> selection): отличает смену выбора (клик) от
  // смены URL, чтобы не «бодаться» за фокус на свежем клике (см. shouldAdoptUrlEntity).
  const prevAdoptEntityIdRef = useRef<number | null>(null);
  // Чтобы не дёргать адопт повторно, когда entity из URL не найден в текущем списке
  // (кандидат ещё не загружен / другая вакансия) — пробуем один раз на каждый id.
  const adoptTriedEntityRef = useRef<number | null>(null);

  // Диплинк из URL «в процессе»: ?entity= указывает на загруженного кандидата, который
  // ещё НЕ выбран. Пока это так — эффекты авто-первого должны уступить, чтобы диплинк
  // победил на загрузке. Если entity из URL не найден (устаревшая ссылка) — null, и
  // авто-первый работает как обычно (фолбэк).
  const pendingDeepLinkEntity = useMemo(() => {
    if (!urlEntity) return null;
    const entityId = Number(urlEntity);
    if (Number.isNaN(entityId)) return null;
    if (selectedCandidate?.entity_id === entityId) return null; // уже выбран — не ждём
    return candidates.some((c) => c.entity_id === entityId) ? entityId : null;
  }, [urlEntity, candidates, selectedCandidate?.entity_id]);

  // Адопт из URL: на маунте и при РЕАЛЬНОЙ смене ?entity= (не при смене выбора) находим
  // заявку по entity_id и выбираем её. Диплинк ПОБЕЖДАЕТ авто-селект первого (см. ниже —
  // эффекты авто-первого ждут, пока есть подходящий незанятый entity из URL).
  useEffect(() => {
    if (!urlEntity) { adoptTriedEntityRef.current = null; return; }
    const entityId = Number(urlEntity);
    if (Number.isNaN(entityId)) return;

    // Гонка «клик vs URL»: клик ставит selectedCandidateId мгновенно, зеркало пишет
    // ?entity= на тик позже. selChanged=true → менялся ВЫБОР (клик), а URL отстал → НЕ
    // адоптим (иначе вернём фокус назад). Сравниваем по entity_id выбранного кандидата.
    const curEntityId = selectedCandidate?.entity_id ?? null;
    const selChanged = curEntityId !== prevAdoptEntityIdRef.current;
    prevAdoptEntityIdRef.current = curEntityId;

    if (curEntityId === entityId) { adoptTriedEntityRef.current = null; return; } // уже синхронно
    if (!shouldAdoptUrlEntity(curEntityId, entityId, selChanged)) return;

    const match = candidates.find((c) => c.entity_id === entityId);
    if (match) {
      adoptTriedEntityRef.current = null;
      // Делаем кандидата гарантированно видимым: вкладка «Все» показывает всех, поэтому
      // эффект авто-первого (фильтрует по вкладке) не перебьёт наш выбор. Исключение —
      // валидный ?stage= из URL (F5 на конкретной вкладке): его не затираем, кандидат
      // всё равно должен быть в этой вкладке, раз ссылка на него пришла с тем же ?stage=.
      const urlStage = searchParams.get('stage');
      const hasValidUrlStage =
        !!urlStage && (urlStage === 'all' || stagesConfig.keys.includes(urlStage));
      // УСТАРЕВШИЙ дип-линк: ?stage= указывает на КОНКРЕТНУЮ вкладку, а кандидат из
      // ?entity= в ДРУГОМ этапе (юзер переключил вкладку, entity остался в URL). Тогда
      // НЕ адоптим — чистим stale ?entity=; авто-первый откроет первого текущей вкладки.
      // Иначе была пустая правая панель («перехожу на статус — пустое окно», баг Марии).
      if (hasValidUrlStage && urlStage !== 'all') {
        const matchKeys = stagesConfig.enumToKeys[match.stage] || [];
        if (!matchKeys.includes(urlStage as string)) {
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev);
              next.delete('entity');
              return next;
            },
            { replace: true },
          );
          return;
        }
      }
      if (!hasValidUrlStage) {
        setSelectedTab('all');
      }
      setSelectedCandidateId(match.id);
      onFocusedRef.current();
      return;
    }
    // entity из URL ещё не загружен в этом списке (другая вакансия / не подгрузился) —
    // отмечаем попытку, чтобы не крутиться; адоптим, когда candidates приедут (deps).
    adoptTriedEntityRef.current = entityId;
  }, [urlEntity, candidates, selectedCandidate?.entity_id]);

  // Зеркалим выбранного кандидата в URL (?entity=<entity_id>) — ссылка шарящаяся.
  // Функциональная форма setSearchParams(prev => …) ПРЕСЕРВИТ v/status; чистая функция
  // вернёт null, когда менять нечего — это защита от бесконечного цикла. startTransition,
  // чтобы ререндер от смены URL не блокировал мгновенный отклик на клик.
  useEffect(() => {
    const curEntityId = selectedCandidate?.entity_id ?? null;
    // Пока есть неразрешённый диплинк из URL — НЕ стираем entity (адопт ещё не доехал).
    if (curEntityId == null && urlEntity && adoptTriedEntityRef.current != null) {
      prevMirrorEntityIdRef.current = curEntityId;
      return;
    }
    const prevId = prevMirrorEntityIdRef.current;
    prevMirrorEntityIdRef.current = curEntityId;
    // Считаем по СВЕЖИМ searchParams в функциональной форме (колбэк стабилен → эффект
    // авто-селекта не пересоздаётся на каждой смене URL); null от помощника = менять
    // нечего → возвращаем prev БЕЗ изменений, чтобы не плодить лишнюю запись в историю.
    startTransition(() => {
      setSearchParams((prev) => computeEntityParamUpdate(prev, curEntityId, prevId) ?? prev, { replace: true });
    });
  }, [selectedCandidate?.entity_id, urlEntity, setSearchParams]);

  // Зеркалим выбранную вкладку статуса воронки в URL (?stage=<key>) — чтобы F5
  // оставлял рекрутёра на той же колонке (кандидат уже переживает F5 через ?entity=
  // выше). «Все» пишем тоже (stage=all): без этого F5 на «Все» открывал первую
  // рабочую вкладку, а открытый кандидат терялся. Пока эффект авто-вкладки ниже не
  // выставил вкладку для ЭТОЙ воронки — URL не трогаем: стартовое 'all' иначе
  // перетёрло бы ?stage= из ссылки/F5. Функциональная форма setSearchParams(prev => …)
  // сохраняет v/entity/status/recruiter; no-op guard возвращает prev без изменений,
  // если значение не поменялось — защита от лишней записи в историю и от цикла с
  // эффектом восстановления вкладки.
  useEffect(() => {
    if (selectedVacancyId == null || autoTabVacancyRef.current !== selectedVacancyId) return;
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('stage', selectedTab || 'all');
      if ((prev.get('stage') || '') === (next.get('stage') || '')) return prev;
      return next;
    }, { replace: true });
  }, [selectedTab, selectedVacancyId, setSearchParams]);

  // Клик по вкладке-этапу: помимо смены стейта ПУШИМ ?stage= в историю, чтобы
  // браузерный «Назад» вернул на предыдущую вкладку вместе с открытым кандидатом
  // (?entity=). Эффект-зеркало выше — replace + no-op guard, так что второй записи
  // не будет. Обратная связь 2026-08-05: из карточки кандидата переключил вкладку —
  // Back стал серым, к кандидату не вернуться.
  const selectStageTab = useCallback((key: string) => {
    setSelectedTab(key);
    setSelectedCandidateId(null);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('stage', key || 'all');
      // Снимаем открытого кандидата из URL в том же push (он и так деселектится):
      // иначе ?entity= off-tab кандидата может отскочить/переспорить адопт при
      // смене вкладки. Предыдущая запись истории сохраняет entity — Back вернёт.
      next.delete('entity');
      next.delete('edit');
      next.delete('tab');
      return next;
    }, { replace: false });
  }, [setSearchParams]);

  // Браузерный Назад/Вперёд меняет ЗНАЧЕНИЕ ?stage= — подхватываем его в
  // selectedTab (иначе URL менялся, а видимая вкладка оставалась прежней).
  // Зависимость — извлечённая строка stage, а НЕ весь searchParams: правки
  // ?status=/?recruiter=/?entity= этот эффект не дёргают. Guard на равенство +
  // валидация по этапам текущей вакансии — без циклов с зеркалом.
  // ВАЖНО: raw (может быть null) — ОТСУТСТВИЕ ?stage= это НЕ то же, что ?stage=all.
  // Клик по ссылке вакансии в сайдбаре ведёт на ?v=&recruiter= БЕЗ stage; если бы
  // мы трактовали «нет параметра» как 'all', воронка молча переключалась бы на
  // вкладку «Все» (все этапы разом, активной вкладки нет, кандидаты из отказа и пр.).
  // Поэтому синхроним вкладку из URL ТОЛЬКО при ЯВНОМ значении stage (Back/Forward
  // между колонками); отсутствие параметра оставляет текущую вкладку — её тут же
  // дописывает обратно эффект-зеркало ?stage=.
  const urlStageParam = searchParams.get('stage');
  useEffect(() => {
    if (urlStageParam == null) return;
    if (urlStageParam === selectedTab) return;
    if (urlStageParam === 'all' || stagesConfig.keys.includes(urlStageParam)) {
      setSelectedTab(urlStageParam);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlStageParam]);

  const tabFilteredCandidates = useMemo(() => {
    // При активном поиске игнорируем выбранную вкладку — ищем по ВСЕМ статусам
    // воронки (рекрутёр не должен помнить, в какой колонке лежит кандидат).
    if (candidateSearch.trim()) return filteredCandidates;
    if (selectedTab === 'all') return filteredCandidates;
    const inTab = filteredCandidates.filter(c => {
      const mapped = stagesConfig.enumToKeys[c.stage];
      // Тот же фолбэк, что в groupedByStage: кандидат без маппинга этапа
      // относится к первой видимой колонке, иначе он невидим в любой вкладке.
      const candidateStageKeys =
        mapped && mapped.length > 0
          ? mapped
          : stagesConfig.keys[0]
            ? [stagesConfig.keys[0]]
            : [];
      return candidateStageKeys.includes(selectedTab);
    });
    // Только что перемещённый кандидат уехал на другой этап, но остаётся
    // видимым здесь, чтобы его карточка справа не подменилась чужой.
    return pinMovedCandidate(inTab, filteredCandidates, stickyCandidateId);
  }, [filteredCandidates, selectedTab, stagesConfig, candidateSearch, stickyCandidateId]);

  // Пин живёт до первого «ухода»: другая вкладка, другая воронка или клик по
  // другому кандидату.
  useEffect(() => {
    setStickyCandidateId(null);
  }, [selectedTab, selectedVacancyId]);
  useEffect(() => {
    if (stickyCandidateId != null && selectedCandidateId !== stickyCandidateId) {
      setStickyCandidateId(null);
    }
  }, [selectedCandidateId, stickyCandidateId]);

  // «В предыдущих сериях»: отклики старше последнего переоткрытия вакансии
  // (is_previous_series с бэка) уходят ВНИЗ списка под разделитель. Активные
  // сверху, порядок внутри групп сохраняется. У обычных (не переоткрытых)
  // вакансий previous всегда пуст → поведение не меняется.
  const orderedCandidates = useMemo(() => {
    // Сортируем ВИДИМЫЙ список ЯВНО по дате последнего переноса (недавние вверху) —
    // не полагаемся на порядок бэкенда, где первичный ключ stage_order (группировка
    // по этапу), из-за чего в списке из разных этапов даты выглядели вразброс.
    // Фолбэк на applied_at для тех, кого ещё не двигали.
    const byRecency = (a: typeof tabFilteredCandidates[number], b: typeof tabFilteredCandidates[number]) => {
      const ta = new Date(a.last_stage_change_at || a.applied_at || 0).getTime();
      const tb = new Date(b.last_stage_change_at || b.applied_at || 0).getTime();
      return tb - ta;
    };
    const active = tabFilteredCandidates.filter(c => !c.is_previous_series).slice().sort(byRecency);
    const previous = tabFilteredCandidates.filter(c => c.is_previous_series).slice().sort(byRecency);
    return { list: [...active, ...previous], firstPreviousId: previous[0]?.id };
  }, [tabFilteredCandidates]);

  // Дефолтная вкладка ставится ОДИН раз при открытии воронки (первая рабочая).
  // Гейт по id воронки: последующие ре-рендеры (фильтр «Только мои», перезагрузка
  // кандидатов) больше НЕ сбрасывают выбранную пользователем вкладку на «Новый».
  // Если этап-конфиг сменился и текущая вкладка стала невалидной — мягко чиним.
  const autoTabVacancyRef = useRef<number | null>(null);
  // Кастомные этапы вакансии (custom_stages) могут подгрузиться ПОСЛЕ открытия
  // воронки — на первом проходе stagesConfig.keys ещё дефолтный STAGE_ORDER, и
  // ?stage= с кастомным ключом не проходит валидацию. stageRestoredRef помнит,
  // удалось ли уже восстановить вкладку из URL для ТЕКУЩЕЙ вакансии, и разрешает
  // один повторный ретрай, когда stagesConfig.keys обновится (уже есть в deps).
  const stageRestoredRef = useRef(false);
  useEffect(() => {
    const vid = selectedVacancyId ?? null;
    // Читаем ?stage= свежим значением при каждом проходе эффекта — НЕ через deps
    // (см. комментарий у deps ниже), чтобы правки URL от ?status=/?recruiter=
    // не перезапускали восстановление вкладки.
    const urlStage = searchParams.get('stage');
    const restored =
      urlStage && (urlStage === 'all' || stagesConfig.keys.includes(urlStage)) ? urlStage : null;

    if (autoTabVacancyRef.current !== vid) {
      autoTabVacancyRef.current = vid;
      // При (пере)открытии воронки — в т.ч. при перезагрузке страницы — пробуем
      // восстановить вкладку из ?stage=, если она валидна для ТЕКУЩЕЙ вакансии.
      // Иначе — первая рабочая вкладка. Но ссылка на КАНДИДАТА без ?stage=
      // открывается на «Все»: первая вкладка его могла не содержать, и выбор
      // по ссылке тут же перебивался первым кандидатом «Нового» — ссылка на
      // Кравцова открывала Ковалёва (найдено при выносе в хук, 20.10.2026).
      stageRestoredRef.current = restored != null;
      const fallbackTab = searchParams.get('entity') ? 'all' : (vacancyWorkflowKeys[0] || 'all');
      setSelectedTab(restored ?? fallbackTab);
      return;
    }
    // Та же вакансия, но кастомные этапы могли подгрузиться ПОСЛЕ открытия —
    // даём один ретрай восстановления из URL, если он ещё не сработал.
    if (!stageRestoredRef.current && restored) {
      stageRestoredRef.current = true;
      setSelectedTab(restored);
      return;
    }
    if (selectedTab !== 'all' && !stagesConfig.keys.includes(selectedTab)) {
      setSelectedTab(vacancyWorkflowKeys[0] || 'all');
    }
    // searchParams намеренно НЕ в deps: читаем только для восстановления/ретрая
    // (гейт по autoTabVacancyRef/stageRestoredRef), чтобы правки URL от других
    // частей этой же страницы (?status=, ?recruiter=) не перезапускали логику.
    // Ретрай триггерится изменением stagesConfig.keys (уже в deps) при подгрузке
    // кастомных этапов вакансии.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedVacancyId, selectedTab, stagesConfig.keys, vacancyWorkflowKeys]);

  useEffect(() => {
    if (tabFilteredCandidates.length === 0) {
      if (selectedCandidateId !== null) setSelectedCandidateId(null);
      return;
    }
    // Диплинк из URL побеждает авто-первого — НО только если дип-линк-кандидат есть в
    // ТЕКУЩЕЙ вкладке (его и покажет адопт-эффект). Если ?entity= указывает на кандидата
    // из ДРУГОЙ вкладки (юзер переключил этап, а stale ?entity= остался в URL) — НЕ
    // блокируем: иначе правая панель пустая навсегда (адопт off-tab не показывает, а
    // авто-первый заблокирован). Это и был баг Марии «перехожу на статус — пустое окно».
    if (
      pendingDeepLinkEntity != null &&
      tabFilteredCandidates.some((c) => c.entity_id === pendingDeepLinkEntity)
    )
      return;
    // Мария (2026-08-25, уточнение): при открытии воронки/переключении этапа справа
    // ДОЛЖЕН сам открываться первый кандидат вкладки (его CV) — единая логика во всех
    // воронках. Если выбранного нет в текущей вкладке (переключили этап) — открываем
    // первого. Явный клик по кандидату и ?entity= работают как раньше.
    if (!selectedCandidateId || !tabFilteredCandidates.some((candidate) => candidate.id === selectedCandidateId)) {
      // Берём ПЕРВОГО из ОТОБРАЖАЕМОГО (отсортированного по свежести) списка, а не из
      // сырого tabFilteredCandidates — иначе выбирался не тот, кто визуально сверху
      // (Мария: «открывает последнюю, а не первую»).
      const first = orderedCandidates.list[0] || tabFilteredCandidates[0];
      setSelectedCandidateId(first.id);
      onFocusedRef.current();
    }
  }, [selectedCandidateId, tabFilteredCandidates, orderedCandidates, pendingDeepLinkEntity]);

  // Авто-выбор первого кандидата при смене вкладки (страховка к эффекту выше):
  // справа всегда открыт первый кандидат вкладки, если ничего не выбрано.
  // Блокируем только на дип-линк ТЕКУЩЕЙ вкладки (см. подробный комментарий выше).
  useEffect(() => {
    if (
      pendingDeepLinkEntity != null &&
      tabFilteredCandidates.some((c) => c.entity_id === pendingDeepLinkEntity)
    )
      return;
    if (tabFilteredCandidates.length > 0 && !selectedCandidateId) {
      // Первый из ОТОБРАЖАЕМОГО списка (по свежести), а не из сырого массива.
      const first = orderedCandidates.list[0] || tabFilteredCandidates[0];
      setSelectedCandidateId(first.id);
    }
  }, [tabFilteredCandidates, orderedCandidates, pendingDeepLinkEntity]);

  return {
    selectedTab, setSelectedTab, selectedCandidateId, setSelectedCandidateId,
    stickyCandidateId, setStickyCandidateId,
    selectedCandidate, selectStageTab,
    groupedByStageMap, vacancyVisibleStageKeys, tabFilteredCandidates, orderedCandidates,
  };
}
