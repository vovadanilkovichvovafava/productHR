import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { NavigateOptions, SetURLSearchParams, URLSearchParamsInit } from 'react-router-dom';

/**
 * `useSearchParams`, у которого функциональная правка строится от ЖИВОГО адреса.
 *
 * react-router отдаёт в `setSearchParams(prev => …)` адрес С ПРОШЛОЙ ОТРИСОВКИ.
 * Две правки подряд в одном такте — и вторая затирает первую. Так на «Все
 * кандидаты» терялась вкладка этапа: клик писал ?stage=, следом зеркало открытой
 * карточки писало ?entity= от старого снимка, этап пропадал из адреса, и после
 * F5 открывалась вкладка «Все» (Мария, 14.10.2026: «при обновлении страницы
 * остаёмся на той же странице»). В воронках так «отскакивал» этап: щёлкнул по
 * вкладке — зеркало кандидата вернуло в адрес прежний ?stage=, и вкладка
 * переключалась только со второго раза (прод, 21.10.2026, воронка на 722
 * кандидата — чем тяжелее отрисовка, тем шире окно гонки).
 *
 * Подпись та же, что у react-router, — можно подставлять вместо него.
 */
export function useLiveSearchParams() {
  const [searchParams, setSearchParamsRaw] = useSearchParams();
  const setSearchParams = useCallback<SetURLSearchParams>(
    (
      next?: URLSearchParamsInit | ((prev: URLSearchParams) => URLSearchParamsInit),
      opts?: NavigateOptions,
    ) =>
      setSearchParamsRaw(
        typeof next === 'function'
          ? () => next(new URLSearchParams(window.location.search))
          : next,
        opts,
      ),
    [setSearchParamsRaw],
  );
  return [searchParams, setSearchParams] as const;
}
