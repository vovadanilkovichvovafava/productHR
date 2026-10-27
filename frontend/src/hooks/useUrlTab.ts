import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Вкладка-переключатель вида, живущая в URL (?<param>=<value>), чтобы работали
 * браузерные «Назад/Вперёд»: клик по вкладке добавляет запись истории (push), а
 * стрелки браузера возвращают предыдущую вкладку. Значение ПРОИЗВОДНОЕ от URL —
 * никакого локального useState, поэтому Back/Forward меняют URL, а вкладка
 * следует автоматически (единый источник истины).
 *
 * Единый паттерн для всего HR-раздела (обратная связь 2026-08-05: переключение
 * вкладки делало браузерный «Назад» серым — к предыдущему виду не вернуться).
 *
 * @param param        имя query-параметра (напр. "tab", "stage", "section")
 * @param defaultValue значение по умолчанию; при нём параметр НЕ пишется в URL
 *                     (чистый адрес), клик на дефолт просто удаляет параметр.
 *
 * setValue(next, { push:false }) — обновить БЕЗ записи в историю (replace):
 * для программных/деплинковых переходов, чтобы не плодить записи.
 */
export function useUrlTab<T extends string = string>(
  param: string,
  defaultValue: T,
): readonly [T, (next: T, opts?: { push?: boolean }) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const value = (searchParams.get(param) as T) || defaultValue;

  const setValue = useCallback(
    (next: T, opts?: { push?: boolean }) => {
      setSearchParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          if (!next || next === defaultValue) p.delete(param);
          else p.set(param, next);
          return p;
        },
        { replace: opts?.push === false },
      );
    },
    [setSearchParams, param, defaultValue],
  );

  return [value, setValue] as const;
}
