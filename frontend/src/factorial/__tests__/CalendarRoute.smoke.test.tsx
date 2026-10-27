// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import FactorialModule from '@/factorial/FactorialModule';

// Reproduces the REAL mount path: FactorialModule -> FactorialShell (Outlet)
// -> CalendarPage -> CalendarTemplate, with all real props (secondaryNav, titleIcon, cta).
describe('CalendarRoute real-path smoke', () => {
  it('mounts /factorial/calendar through the router without throwing', () => {
    expect(() =>
      render(
        <MemoryRouter initialEntries={['/factorial/calendar']}>
          <Routes>
            <Route path="/factorial/*" element={<FactorialModule />} />
          </Routes>
        </MemoryRouter>,
      ),
    ).not.toThrow();
  });
});
