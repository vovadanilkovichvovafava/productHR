/**
 * Две правки адреса в одном такте не должны затирать друг друга.
 *
 * Ровно так терялась вкладка этапа на «Все кандидаты» (Мария, 14.10.2026):
 * клик писал ?stage=, следом зеркало карточки писало ?entity= от снимка прошлой
 * отрисовки — этап пропадал, и после F5 открывалась вкладка «Все».
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { BrowserRouter, useSearchParams } from 'react-router-dom';

import { useLiveSearchParams } from '../useLiveSearchParams';

function TwoWrites({ live }: { live: boolean }) {
  const liveHook = useLiveSearchParams();
  const raw = useSearchParams();
  const set = (live ? liveHook[1] : raw[1]) as (
    fn: (prev: URLSearchParams) => URLSearchParams,
  ) => void;
  return (
    <button
      type="button"
      onClick={() => {
        // Как на странице: сначала вкладка, затем зеркало открытой карточки.
        set((prev) => {
          const next = new URLSearchParams(prev);
          next.set('stage', 'screening');
          return next;
        });
        set((prev) => {
          const next = new URLSearchParams(prev);
          next.set('entity', '42');
          return next;
        });
      }}
    >
      клик
    </button>
  );
}

beforeEach(() => {
  window.history.replaceState(null, '', '/all-candidates');
});

describe('useLiveSearchParams', () => {
  it('вкладка этапа и карточка обе остаются в адресе', async () => {
    render(
      <BrowserRouter>
        <TwoWrites live />
      </BrowserRouter>,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'клик' }));
    });
    const params = new URLSearchParams(window.location.search);
    expect(params.get('stage')).toBe('screening');
    expect(params.get('entity')).toBe('42');
  });

  it('штатный useSearchParams в той же ситуации теряет первую правку — поэтому и нужен хук', async () => {
    render(
      <BrowserRouter>
        <TwoWrites live={false} />
      </BrowserRouter>,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'клик' }));
    });
    const params = new URLSearchParams(window.location.search);
    expect(params.get('entity')).toBe('42');
    expect(params.get('stage')).toBeNull();
  });
});
