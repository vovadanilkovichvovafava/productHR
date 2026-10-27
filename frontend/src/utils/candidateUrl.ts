/**
 * Compute the next URL search params to keep the open candidate profile in the
 * address bar (shareable `?entity=ID`) WITHOUT fighting a pending deep-link load.
 *
 * - `curId`  = id of the currently open profile (selectedCard?.id ?? null)
 * - `prevId` = id from the previous render (a ref), used to tell a genuine close
 *              (selected -> null) apart from a deep-link-pending null (null -> null).
 *
 * Returns the next URLSearchParams, or `null` when nothing should change
 * (the null return is the loop guard — the caller skips setSearchParams).
 */
export function computeEntityParamUpdate(
  current: URLSearchParams,
  curId: number | null,
  prevId: number | null,
): URLSearchParams | null {
  const have = current.get('entity');

  if (curId != null) {
    // Opened or switched profile.
    if (have === String(curId)) return null; // already in sync
    const next = new URLSearchParams(current);
    next.set('entity', String(curId));
    return next;
  }

  // curId == null. Only clear on a GENUINE close (we had a selection last render).
  // A null->null transition means a deep-link select is still pending: leave it.
  if (prevId != null && (current.has('entity') || current.has('edit') || current.has('tab'))) {
    const next = new URLSearchParams(current);
    next.delete('entity');
    next.delete('edit');
    next.delete('tab');
    return next;
  }

  return null;
}

/**
 * Адрес сменился САМ (выбор при этом не менялся) — зеркалу «выбор → адрес»
 * молчать: адрес тут новее, его подхватит эффект «адрес → выбор».
 *
 * Эльвира, 19.10.2026: добавила кандидата из файла — экран секунд пятнадцать
 * прыгал между ним и тем, кто был открыт до добавления, и мог остановиться на
 * прежнем. Окно добавления ставит ?entity=<новый>, пока справа ещё прежний.
 * Эффект выбора открывал нового, а зеркало в том же проходе видело «открыт
 * прежний, в адресе другой» и писало прежнего обратно — с опозданием
 * (startTransition). Запоздалая запись выглядела как переход по ссылке, её
 * снова подхватывали, и так по кругу. Ловилось, только когда новый уже успел
 * попасть в список (загрузка файла на проде — 12 с, список обновляется раз в
 * 15 с): иначе карточка грузилась по id, и зеркало стояло на паузе.
 */
export function urlLeadsSelection(
  current: URLSearchParams,
  curId: number | null,
  prevId: number | null,
): boolean {
  const have = current.get('entity');
  return curId != null && curId === prevId && have != null && have !== String(curId);
}

/**
 * Should the URL->selection effect adopt the URL's ?entity= as the selected card?
 *
 * The click handler sets selectedCard directly (instant UI); the URL mirror writes
 * ?entity= one render later. Without this guard the effect would see selectedCard
 * already on the clicked card while ?entity= still holds the PREVIOUS id, and would
 * yank selection back — the "fight" with the URL.
 *
 * selectionChangedThisRender = the selected id changed since the previous render (a
 * click). When true the URL is merely lagging our own selection → DON'T adopt it.
 * When false, an ?entity= that differs from the selection is a genuine URL change
 * (deep-link, browser back/forward, toast-navigate) or a deep-link target that just
 * became visible → adopt it.
 */
export function shouldAdoptUrlEntity(
  selectedId: number | null,
  urlEntityId: number,
  selectionChangedThisRender: boolean,
): boolean {
  if (selectedId === urlEntityId) return false; // already in sync
  return !selectionChangedThisRender;
}

/**
 * Кого показать справа, когда человек СМЕНИЛ поиск.
 *
 * Мария, 09.10.2026: искали «елизавета муравьева», слева «Нет кандидатов», а
 * справа висела чужая карточка — первая находка промежуточного запроса, пока
 * печатали. Открытый кандидат, которого нет в выдаче нового запроса, справа
 * оставаться не должен: пусто — закрываем, есть находки — открываем первую.
 *
 * Возвращает:
 * - `undefined` — ничего не менять (поиск не менялся или открытый кандидат в
 *   выдаче). Так диплинк из расширения на кандидата, которого нет на доске, и
 *   фоновое обновление во время правки имени карточку не трогают;
 * - `null` — закрыть профиль;
 * - элемент списка — открыть его.
 */
export function cardAfterSearchChange<T extends { card: { id: number } }>(
  visible: T[],
  openId: number | null,
  searchChanged: boolean,
): T | null | undefined {
  if (!searchChanged || openId == null) return undefined;
  if (visible.some((v) => v.card.id === openId)) return undefined;
  return visible[0] ?? null;
}
