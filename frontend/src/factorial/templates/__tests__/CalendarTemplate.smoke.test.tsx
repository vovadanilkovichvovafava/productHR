// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import CalendarTemplate from '../CalendarTemplate';
import type { CalendarEvent } from '../CalendarTemplate';

// Синтетические события (моки с реальными именами удалены 27.10.2026).
const events: CalendarEvent[] = [
  { id: 1, date: '2026-05-09', title: 'Праздник', color: '#10B981' },
  { id: 2, date: '2026-05-19', title: 'Отпуск: Сотрудник 1', color: '#F59E0B' },
];

describe('CalendarTemplate smoke', () => {
  it('renders without throwing (guards the blank-screen regression)', () => {
    expect(() =>
      render(
        <MemoryRouter>
          <CalendarTemplate
            breadcrumb={[{ label: 'Календарь' }]}
            title="Календарь"
            events={events}
          />
        </MemoryRouter>,
      ),
    ).not.toThrow();
  });
});
