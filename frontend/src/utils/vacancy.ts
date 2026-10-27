import type { Vacancy } from '@/types';

/**
 * Активный участник общей воронки (модель без клонов, 2026-07-02):
 * создатель ИЛИ назначенный (assigned_to / assigned_to_all), МИНУС те, кто
 * «закрыл у себя» (extra_data.dismissed_by). Используется для видимости
 * воронок («Мои вакансии», дропдауны добавления кандидата) и для решения
 * «выход vs полное закрытие» на кнопке «Закрыть вакансию».
 */
export function isVacancyParticipant(v: Vacancy, userId: number | undefined | null): boolean {
  if (!userId) return false;
  const dismissed = ((v.extra_data as Record<string, unknown> | undefined)?.dismissed_by as number[] | undefined) || [];
  if (dismissed.includes(userId)) return false;
  if (v.created_by === userId) return true;
  if ((v.assigned_to || []).includes(userId)) return true;
  if (v.assigned_to_all) return true;
  return false;
}

/**
 * Юзера ЯВНО назначили на вакансию (он в assigned_to и не «закрыл у себя»).
 * Без создателя и без assigned_to_all — для админа это разные вещи: заявку он
 * мог создать чисто для раздачи, а «всем рекрутёрам» его не касается.
 */
export function isExplicitlyAssigned(v: Vacancy, userId: number | undefined | null): boolean {
  if (!userId) return false;
  const dismissed = ((v.extra_data as Record<string, unknown> | undefined)?.dismissed_by as number[] | undefined) || [];
  if (dismissed.includes(userId)) return false;
  return (v.assigned_to || []).includes(userId);
}

/**
 * Личное принятие заявки, 2026-07-08: «воронка общая, но заявку каждый
 * берёт сам». Взятие статуса вакансии в open происходит один раз (при
 * первом чьём-либо «Взять в работу»), но это НЕ означает, что все
 * назначенные автоматически согласились работать над ней — трекается
 * отдельно в extra_data.accepted_by (backend: take_vacancy/decline_vacancy).
 */
export function hasPersonallyAccepted(v: Vacancy, userId: number | undefined | null): boolean {
  if (!userId) return false;
  const acceptedBy = ((v.extra_data as Record<string, unknown> | undefined)?.accepted_by as number[] | undefined) || [];
  return acceptedBy.includes(userId);
}

/**
 * «Моя» ли эта воронка ЛИЧНО для юзера прямо сейчас: только через личное
 * «Взять в работу» (accepted_by) — БЕЗ исключения для создателя. 2026-07-09:
 * раньше создатель считался «неявно согласившимся» автоматически, из-за чего
 * админ, создавший заявку чисто для раздачи рекрутёрам, видел её в «Мои
 * вакансии» сразу как только её принимал КТО-ТО ДРУГОЙ — хотя сам её не брал.
 * Новые заявки всегда стартуют как pending_review (см. VacancyForm.tsx) — их
 * переводит в open только «Взять в работу», и создателю это правило теперь
 * тоже применяется без исключений (сам создатель тоже может нажать «Взять
 * в работу» на своей заявке — take_vacancy это явно разрешает).
 */
export function isPersonallyActive(v: Vacancy, userId: number | undefined | null): boolean {
  return hasPersonallyAccepted(v, userId);
}

/**
 * Видимость ЗАЯВКИ в быстром списке «Заявки» (сайдбар), 2026-07-08:
 * - admin/owner/superadmin/hr → только НЕРАСПРЕДЕЛЁННЫЕ заявки (нужно раздать).
 *   Как только админ назначил рекрутёра — заявка уходит из сайдбара (она целиком
 *   есть в «Перейти к заявкам», ничего не теряется).
 * - рекрутёр (member) → заявки, где он участник (создал ИЛИ назначен), но
 *   ЕЩЁ НЕ принял лично — даже если статус уже open (кто-то ДРУГОЙ из
 *   назначенных уже взял её в работу). Как только сам принял —
 *   isPersonallyActive становится true и заявка пропадает отсюда, появляясь
 *   в «Мои вакансии».
 * ВНИМАНИЕ: правило для САЙДБАРА. Полная страница /vacancies («Перейти к
 * заявкам») показывает админу ВСЕ заявки независимо от назначения.
 */
export function isRequestVisibleTo(
  v: Vacancy,
  userId: number | undefined | null,
  isAdmin: boolean,
): boolean {
  if (isAdmin) {
    // Админ видит заявку, ПОКА её не взяли в работу (статус ещё pending_review/draft),
    // независимо от того, назначена она кому-то или нет. Как только рекрутёр берёт её
    // в работу (take_into_work: pending_review/draft → open), заявка уходит из сайдбара
    // админа. Раньше здесь было `return !assigned` — заявка пропадала сразу после
    // НАЗНАЧЕНИЯ, хотя в работу её ещё не взяли (жалоба Марии: назначаю → исчезает).
    if (v.status === "pending_review" || v.status === "draft") return true;
    // Плюс — как у рекрутёра — вакансии, куда админа ЯВНО назначили, а он её ещё
    // лично не взял (взял кто-то другой, статус уже open). Раньше админ их не видел
    // нигде — ни тут, ни в «Мои вакансии» — и не мог присоединиться к общей
    // воронке, хотя рядовой рекрутёр мог (2026-09-10, «даунгрейд Марии»).
    return isExplicitlyAssigned(v, userId) && !isPersonallyActive(v, userId);
  }
  return isVacancyParticipant(v, userId) && !isPersonallyActive(v, userId);
}

/**
 * Кто реально ведёт заявку прямо сейчас — те, кто лично нажал «Взять в
 * работу» (extra_data.accepted_by), а НЕ создатель (2026-07-09: раньше
 * группировки/подписи «Рекрутер: ...» показывали создателя, что вводило в
 * заблуждение — админ, раздающий заявки, не обязательно сам их ведёт).
 * Если ещё никто не принял (pending_review/draft, либо старые данные до
 * личного принятия) — откатываемся на создателя, чтобы заявка не «терялась»
 * без исполнителя вообще.
 */
export function getAcceptorIds(v: Vacancy): number[] {
  const acceptedBy = ((v.extra_data as Record<string, unknown> | undefined)?.accepted_by as number[] | undefined) || [];
  if (acceptedBy.length > 0) return acceptedBy;
  return v.created_by ? [v.created_by] : [];
}

/**
 * Что предлагать вместо одной двусмысленной «Закрыть» (решение юзера 2026-09-10):
 * две кнопки с однозначными названиями.
 *  • «Выйти из вакансии» — снимаешь себя, у остальных участников она остаётся в
 *    работе (POST /decline). Есть, пока в вакансии кроме тебя кто-то работает.
 *  • «Закрыть вакансию» — закрывается у всех. Админу — всегда; остальным — когда
 *    выйти нельзя (последний участник или не участник): закрытие рядовым
 *    участником при других участниках бэкенд всё равно превращает в выход.
 */
export function getVacancyExitOptions(
  v: Vacancy,
  userId: number | undefined | null,
  isAdmin: boolean,
): { canLeave: boolean; canClose: boolean; others: number[] } {
  const participant = isVacancyParticipant(v, userId);
  const others = participant ? otherActiveParticipants(v, userId) : [];
  const canLeave = participant && others.length > 0;
  // Не участник и не админ — закрыть нельзя, пока в вакансии кто-то работает:
  // раньше такому рекрутёру предлагалось «Закрыть», и вакансия закрывалась у
  // всех (20.10.2026; сервер теперь отвечает 403).
  const canClose = isAdmin || (participant ? !canLeave : otherActiveParticipants(v, userId).length === 0);
  return { canLeave, canClose, others };
}

/** Активные участники, кроме указанного юзера (для вопроса «ты последний?»). */
export function otherActiveParticipants(v: Vacancy, userId: number | undefined | null): number[] {
  const dismissed = new Set(
    (((v.extra_data as Record<string, unknown> | undefined)?.dismissed_by as number[] | undefined) || []),
  );
  const participants = new Set<number>(v.assigned_to || []);
  if (v.created_by) participants.add(v.created_by);
  return Array.from(participants).filter((id) => !dismissed.has(id) && id !== userId);
}

/**
 * Только что перемещённый кандидат остаётся видимым во вкладке, из которой его
 * увезли (23.09.2026): раньше он мгновенно пропадал из списка, справа сам
 * открывался СЛЕДУЮЩИЙ человек, и рекрутёр терял из виду того, кого двигал.
 *
 * Возвращает список вкладки с «прикреплённым» кандидатом первым; если он и так
 * подходит под вкладку (или его нет вовсе) — список не меняется.
 */
export function pinMovedCandidate<T extends { id: number }>(
  inTab: T[],
  all: T[],
  pinnedId: number | null,
): T[] {
  if (pinnedId == null) return inTab;
  if (inTab.some((c) => c.id === pinnedId)) return inTab;
  const pinned = all.find((c) => c.id === pinnedId);
  return pinned ? [pinned, ...inTab] : inTab;
}
