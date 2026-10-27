import type { QueryClient } from '@tanstack/react-query';

// Кэш React Query принадлежит ПОЛЬЗОВАТЕЛЮ, а не вкладке.
//
// Ключи вроде ['fx','me'] не содержат номера пользователя, а staleTime 30 с +
// keepPreviousData держат старые данные на экране. До 27.10.2026 выход и
// вход другим аккаунтом (или имперсонация суперадмином) без перезагрузки
// страницы показывали ПРЕЖНЕГО человека: его профиль, паспорт, документы.
//
// Подписка на authStore, а не вызов в handleLogout: пользователь меняется ещё
// при имперсонации, выходе из неё и переключателе аккаунтов в dev-сборке.

export type CacheAction = 'none' | 'clear' | 'reset';

/**
 * Что сделать с кэшем при смене пользователя.
 * - первый вход (null → id): ничего — чужого в кэше нет, а запросы, ушедшие
 *   при загрузке, не стоит обрывать;
 * - выход (id → null): стереть всё;
 * - другой человек (A → B): сбросить всё, открытые экраны перезапросят своё.
 */
export function cacheActionOnUserChange(prev: number | null, next: number | null): CacheAction {
  if (prev === next) return 'none';
  if (prev === null) return 'none';
  if (next === null) return 'clear';
  return 'reset';
}

export function bindQueryCacheToUser(
  queryClient: QueryClient,
  store: {
    getState: () => { user: { id: number } | null };
    subscribe: (listener: (state: { user: { id: number } | null }) => void) => () => void;
  },
): () => void {
  let current: number | null = store.getState().user?.id ?? null;
  return store.subscribe((state) => {
    const next = state.user?.id ?? null;
    const action = cacheActionOnUserChange(current, next);
    current = next;
    if (action === 'clear') queryClient.clear();
    else if (action === 'reset') void queryClient.resetQueries();
  });
}
