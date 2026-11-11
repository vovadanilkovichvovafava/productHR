// «Пришла заявка» в левой панели (Мария, 11.11.2026: «было уведомление
// стандартно, как у нас сейчас, и ярким каким-то светом подсвечивать, что
// пришла задача»). Пункт «Заявки» подсвечивается, пока в списке есть заявка,
// которую человек ещё не видел. Увидел = нажал на «Заявки» или открыл заявку.
//
// Что видел — список номеров на устройстве (localStorage, у каждого
// пользователя свой ключ). Хранилища может не быть (приватное окно) — тогда
// просто ничего не подсвечиваем, страница работает как раньше.

const KEY_PREFIX = "hf-seen-requests:";

export function seenRequestsKey(userId: number): string {
  return `${KEY_PREFIX}${userId}`;
}

/** Прочитать «видел» с устройства. null — записи нет (первый заход) или
 * хранилище недоступно. */
export function loadSeenRequests(userId: number): number[] | null {
  try {
    const raw = localStorage.getItem(seenRequestsKey(userId));
    if (raw == null) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x): x is number => typeof x === "number") : [];
  } catch {
    return null;
  }
}

export function saveSeenRequests(userId: number, ids: number[]): void {
  try {
    localStorage.setItem(seenRequestsKey(userId), JSON.stringify(ids));
  } catch {
    // нет хранилища — подсветка просто не запомнится
  }
}

/** Заявки из списка, которых человек ещё не видел. */
export function unseenRequestIds(current: number[], seen: number[] | null): number[] {
  if (seen == null) return [];
  const known = new Set(seen);
  return current.filter((id) => !known.has(id));
}

/**
 * Что запомнить как «видел». Храним только то, что сейчас в списке, плюс
 * отмеченное: ушедшие заявки (взяли, закрыли) из памяти выпадают, иначе
 * список рос бы бесконечно.
 */
export function markRequestsSeen(current: number[], seen: number[] | null, ids: number[] = current): number[] {
  const inList = new Set(current);
  const out = new Set((seen ?? []).filter((id) => inList.has(id)));
  ids.forEach((id) => out.add(id));
  return Array.from(out).sort((a, b) => a - b);
}

// Свернуть/развернуть блоки панели — тоже на устройстве (просьба Марии:
// у Эльвиры длинный список вакансий, «возможность раскрытия»).
export function loadPanelFlag(key: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : raw === "1";
  } catch {
    return fallback;
  }
}

export function savePanelFlag(key: string, value: boolean): void {
  try {
    localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // без хранилища — просто не запомнится
  }
}
