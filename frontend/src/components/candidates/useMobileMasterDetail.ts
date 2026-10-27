import { useCallback, useState } from "react";

// Телефон: «список ИЛИ карточка» (владелец, 24.10.2026). На узком экране
// список кандидатов и карточка рядом не помещаются — имена и кнопки
// обрезались. Ниже 900 px показываем что-то одно: список на весь экран, по
// нажатию — карточка на весь экран с «← К списку». До 900 px (планшет стоя —
// тоже), шире — ничего не меняется:
// какую половину прятать, решает CSS по `data-mobile-view` у
// `.hf-candidates-master` (index.css), а этот хук только помнит выбор.
//
// Выбор лежит в sessionStorage вкладки, а не в адресе: адрес и так несёт
// `?entity=` открытого кандидата (автовыбор ставит его и при показе списка),
// поэтому по нему нельзя понять, смотрел человек список или карточку, — а
// F5 должен вернуть туда же. Без сохранённого выбора ссылка с `?entity=`
// открывает карточку: по ней пришли именно к человеку.

export type MobileView = "list" | "card";

function readInitial(storageKey: string): MobileView {
  try {
    const saved = sessionStorage.getItem(storageKey);
    if (saved === "list" || saved === "card") return saved;
  } catch {
    /* приватное окно — просто без памяти */
  }
  try {
    return new URLSearchParams(window.location.search).has("entity") ? "card" : "list";
  } catch {
    return "list";
  }
}

export function useMobileMasterDetail(storageKey: string) {
  const [view, setViewState] = useState<MobileView>(() => readInitial(storageKey));
  const setView = useCallback(
    (next: MobileView) => {
      setViewState(next);
      try {
        sessionStorage.setItem(storageKey, next);
      } catch {
        /* см. readInitial */
      }
    },
    [storageKey],
  );
  const showCard = useCallback(() => setView("card"), [setView]);
  const showList = useCallback(() => setView("list"), [setView]);
  return { view, showCard, showList };
}
