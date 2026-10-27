import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Задержанное значение + возможность выставить его НЕМЕДЛЕННО.
 *
 * Немедленный сброс нужен при смене вкладки с активным поиском: иначе запрос к
 * серверу и фильтр списка ещё 400 мс живут со старым словом, и человек видит
 * мигание «кандидатов нет» (владелец, 05.10.2026).
 */
export function useDebounce<T>(value: T, delay: number): [T, (next: T) => void] {
  const [debounced, setDebounced] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    timer.current = setTimeout(() => setDebounced(value), delay);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [value, delay]);
  const setNow = useCallback((next: T) => {
    if (timer.current) clearTimeout(timer.current);
    setDebounced(next);
  }, []);
  return [debounced, setNow];
}

