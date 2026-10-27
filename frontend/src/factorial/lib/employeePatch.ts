// Что отправлять при сохранении сотрудника.
//
// Шлём ТОЛЬКО поля, которые человек поменял в окне, а очищенное поле — явным
// `null`. Раньше пустое поле превращалось в `undefined`, JSON его выбрасывал, и
// сервер оставлял старое значение: стёр адрес — после «Сохранить» он на месте.
// А нетронутые поля уходили целиком (вместе со всей старой extra_data), так что
// окно, открытое до чужой правки, затирало её своими устаревшими значениями.

export type FormValues = Record<string, string>;

/** Изменённые поля: новое значение (обрезанное) или null, если поле очистили. */
export function changedFields(
  initial: FormValues,
  current: FormValues,
  keys: readonly string[],
): Record<string, string | null> {
  const out: Record<string, string | null> = {};
  for (const k of keys) {
    const before = (initial[k] ?? '').trim();
    const after = (current[k] ?? '').trim();
    if (before === after) continue;
    out[k] = after ? after : null;
  }
  return out;
}

/** Дата из поля (YYYY-MM-DD) в формат сервера; null — очищено. */
export function dateFieldToServer(v: string | null): string | null {
  return v ? `${v}T00:00:00` : null;
}
