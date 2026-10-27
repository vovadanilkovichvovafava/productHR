// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import FactorialModule from '@/factorial/FactorialModule';

function mount(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/factorial/*" element={<FactorialModule />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Реальный путь монтирования: FactorialModule → FactorialShell (Outlet) → страница.
describe('маршруты модуля «Управление»', () => {
  it('«Отпуска» (календарь) монтируются без ошибок', () => {
    expect(() => mount('/factorial/time-off')).not.toThrow();
  });

  it('демо-экраны недоступны: старый адрес календаря — «Страница не найдена»', () => {
    mount('/factorial/calendar');
    expect(screen.getByText('Страница не найдена')).toBeTruthy();
  });
});
