/**
 * «Наблюдатель» (is_readonly) — клиентский запрет записи (01.10.2026).
 *
 * Сервер и так режет любой не-GET у наблюдателя (403), но на клиенте этот отказ
 * был ТИХИМ: кнопка нажималась, комментарий «уходил», этап «менялся» и
 * возвращался после F5. Теперь запрос не уходит вовсе, а человек видит одно
 * понятное сообщение. Белый список доменов обязан совпадать с
 * `_ro_writable_prefixes` в backend/api/services/auth.py — иначе ментор,
 * который наблюдает HR, но работает в Практике, потеряет свой раздел.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import toast from 'react-hot-toast';

import { OBSERVER_BLOCK_MESSAGE, isObserverBlocked, setObserverMode } from '../client';

afterEach(() => setObserverMode(false));

describe('isObserverBlocked', () => {
  it('обычному пользователю не мешает', () => {
    expect(isObserverBlocked('put', '/vacancies/applications/42')).toBe(false);
  });

  it('наблюдателю режет запись в HR', () => {
    setObserverMode(true);
    expect(isObserverBlocked('put', '/vacancies/applications/42')).toBe(true);
    expect(isObserverBlocked('post', '/entities/9/notes')).toBe(true);
    expect(isObserverBlocked('delete', '/vacancies/applications/42/history/7')).toBe(true);
    expect(isObserverBlocked('patch', '/candidates/9267/status')).toBe(true);
  });

  it('чтение не трогает', () => {
    setObserverMode(true);
    expect(isObserverBlocked('get', '/entities/9')).toBe(false);
    expect(isObserverBlocked(undefined, '/entities/9')).toBe(false);
    expect(isObserverBlocked('head', '/entities/9')).toBe(false);
  });

  it('свой рабочий домен наблюдатель по-прежнему меняет', () => {
    setObserverMode(true);
    for (const url of [
      '/chats/5/messages',
      '/calls/3',
      '/interns/8',
      '/criteria',
      '/projects/2/tasks',
      '/project-statuses',
      '/timeoff/1',
      '/blockers',
      '/notifications/read',
      '/auth/logout',
    ]) {
      expect(isObserverBlocked('post', url), url).toBe(false);
    }
  });

  it('префикс /api и абсолютный адрес разбираются так же', () => {
    setObserverMode(true);
    expect(isObserverBlocked('post', '/api/entities/9/notes')).toBe(true);
    expect(isObserverBlocked('post', 'https://enceladus.site/api/projects/2/tasks')).toBe(false);
    expect(isObserverBlocked('post', '/vacancies?dry_run=true')).toBe(true);
    // «/api» срезается только как целый сегмент: иначе «/apiary» превратилось бы
    // в «ary» и не совпало ни с одним префиксом.
    expect(isObserverBlocked('post', '/api/projects/2/tasks')).toBe(false);
  });
});

describe('Плашка — только на то, что человек нажал', () => {
  // Карточка при открытии сама просит проверку дублей (POST), и наблюдателю
  // сыпались плашки без единого клика — жалоба владельца 01.10.2026.
  it('фоновый запрос режется молча', async () => {
    setObserverMode(true);
    const api = (await import('../client')).default;
    await expect(api.post('/entities/9/detect-duplicate', {})).rejects.toThrow(
      OBSERVER_BLOCK_MESSAGE,
    );
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('после нажатия — объясняем, иначе «нажал, ничего не произошло»', async () => {
    setObserverMode(true);
    document.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    const api = (await import('../client')).default;
    await expect(api.post('/entities/9/notes', { text: 'x' })).rejects.toThrow(
      OBSERVER_BLOCK_MESSAGE,
    );
    expect(toast.error).toHaveBeenCalledWith(OBSERVER_BLOCK_MESSAGE);
  });
});
