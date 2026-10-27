// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import CalendarTemplate from '../CalendarTemplate';
import { timeOffEvents } from '@/factorial/mocks/timeOff';

describe('CalendarTemplate smoke', () => {
  it('renders without throwing (guards the blank-screen regression)', () => {
    expect(() =>
      render(
        <MemoryRouter>
          <CalendarTemplate
            breadcrumb={[{ label: 'Календарь' }]}
            title="Календарь"
            events={timeOffEvents}
          />
        </MemoryRouter>,
      ),
    ).not.toThrow();
  });
});
