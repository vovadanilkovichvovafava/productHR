// Поиск по строкам таблицы и «Выбрать всех» по найденным.
//
// До 27.10.2026 галочка «Выбрать всех» в списке сотрудников отмечала ВСЕХ
// сотрудников, а не найденных поиском: искали «Иванов», жали «Выбрать всех» →
// «Уволить» — и увольнялась вся компания. Отбор поиска и выбор теперь считает
// одна функция (её же использует DataTable).

export function matchesSearch<T>(row: T, searchKey: string | undefined, query: string | undefined): boolean {
  if (!query || !searchKey) return true;
  const val = (row as Record<string, unknown>)[searchKey];
  return String(val ?? '').toLowerCase().includes(String(query).toLowerCase());
}

/** Отмечены ли все видимые строки (пустой список — нет). */
export function allVisibleSelected(selected: ReadonlySet<number>, visibleIds: readonly number[]): boolean {
  return visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));
}

/**
 * Галочка в шапке: если все видимые уже отмечены — снять их, иначе добавить.
 * Отмеченные раньше и сейчас скрытые поиском остаются как были.
 */
export function toggleAllVisible(selected: ReadonlySet<number>, visibleIds: readonly number[]): Set<number> {
  const next = new Set(selected);
  if (allVisibleSelected(selected, visibleIds)) visibleIds.forEach((id) => next.delete(id));
  else visibleIds.forEach((id) => next.add(id));
  return next;
}
