/**
 * Клиент удаления записи истории отдаёт ТЕЛО ответа (23.09.2026).
 *
 * Раньше функция возвращала void, и страница не знала, откатил ли бэкенд этап —
 * приходилось перезагружать список. Теперь по `rolled_back`/`stage` карточка и
 * строка списка переставляются на месте, поэтому тело ответа терять нельзя.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const debouncedMutation = vi.fn();

vi.mock('../client', () => ({
  debouncedMutation: (...args: unknown[]) => debouncedMutation(...args),
  deduplicatedGet: vi.fn(),
}));

import { deleteApplicationHistory } from '../vacancies';

describe('deleteApplicationHistory', () => {
  beforeEach(() => debouncedMutation.mockReset());

  it('шлёт DELETE по заявке и записи и возвращает результат отката', async () => {
    debouncedMutation.mockResolvedValue({
      data: { success: true, rolled_back: true, stage: 'screening', entity_status: 'practice' },
    });

    const res = await deleteApplicationHistory(42, 555);

    expect(debouncedMutation).toHaveBeenCalledWith(
      'delete',
      '/vacancies/applications/42/history/555',
    );
    expect(res.rolled_back).toBe(true);
    expect(res.stage).toBe('screening');
    expect(res.entity_status).toBe('practice');
  });

  it('старая запись — отката нет, этап в ответе прежний', async () => {
    debouncedMutation.mockResolvedValue({
      data: { success: true, rolled_back: false, stage: 'interview', entity_status: 'is_interview' },
    });

    const res = await deleteApplicationHistory(1, 2);
    expect(res.rolled_back).toBe(false);
    expect(res.stage).toBe('interview');
  });
});
