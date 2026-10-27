import { describe, it, expect, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { cacheActionOnUserChange, bindQueryCacheToUser } from '../queryCacheAuth';

describe('cacheActionOnUserChange', () => {
  it('первый вход не трогает кэш', () => {
    expect(cacheActionOnUserChange(null, 5)).toBe('none');
  });
  it('выход стирает кэш', () => {
    expect(cacheActionOnUserChange(5, null)).toBe('clear');
  });
  it('другой пользователь (имперсонация, смена аккаунта) — сброс', () => {
    expect(cacheActionOnUserChange(5, 7)).toBe('reset');
  });
  it('тот же пользователь — ничего', () => {
    expect(cacheActionOnUserChange(5, 5)).toBe('none');
  });
});

describe('bindQueryCacheToUser', () => {
  it('после выхода данные прежнего пользователя не остаются в кэше', () => {
    const qc = new QueryClient();
    let state: { user: { id: number } | null } = { user: { id: 1 } };
    const listeners: Array<(s: typeof state) => void> = [];
    const store = {
      getState: () => state,
      subscribe: (l: (s: typeof state) => void) => { listeners.push(l); return () => {}; },
    };
    bindQueryCacheToUser(qc, store);
    qc.setQueryData(['fx', 'me'], { id: 1, name: 'A' });
    state = { user: null };
    listeners.forEach((l) => l(state));
    expect(qc.getQueryData(['fx', 'me'])).toBeUndefined();
  });

  it('смена пользователя сбрасывает запросы', () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'resetQueries');
    let state: { user: { id: number } | null } = { user: { id: 1 } };
    const listeners: Array<(s: typeof state) => void> = [];
    bindQueryCacheToUser(qc, {
      getState: () => state,
      subscribe: (l) => { listeners.push(l); return () => {}; },
    });
    state = { user: { id: 2 } };
    listeners.forEach((l) => l(state));
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
