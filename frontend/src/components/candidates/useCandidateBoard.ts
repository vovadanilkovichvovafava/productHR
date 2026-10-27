import { useCallback, useEffect, useRef, useState } from "react";
import { getCandidatesKanban, type KanbanBoardResponse } from "@/services/api/candidates";

// Доска «Все кандидаты»: загрузка под запрос поиска, фоновое обновление и
// «последняя доска без поиска» (вынесено из AllCandidatesPage, 20.10.2026).
//
// boardQuery — запрос, под который получена ТЕКУЩАЯ доска. Пока он не совпал с
// запросом в поле, доску показывать нельзя: это она мигала «кандидатов нет» при
// смене вкладки с поиском, и выбор карточки на ней пересчитывать нельзя —
// справа мелькал чужой человек (владелец, 05.10.2026).

export function useCandidateBoard(search: string) {
  const [board, setBoard] = useState<KanbanBoardResponse | null>(null);
  const [boardQuery, setBoardQuery] = useState("");
  const [loading, setLoading] = useState(true);
  // Последняя доска БЕЗ поиска. Сбросили поиск — возвращаем её мгновенно, и
  // человек сразу видит нормальные счётчики и список, пока с сервера едет
  // свежая. Без этого между сбросом и ответом мелькали нули и «кандидатов нет».
  const fullBoardRef = useRef<KanbanBoardResponse | null>(null);
  // Счётчик правок доски на месте (перевод этапа, правка, удаление). Ответ
  // сервера, запрошенный ДО правки, её не знает: раньше он приходил следом и
  // возвращал строке старый этап до следующего обновления, до 15 с (проверка
  // прода 21.10.2026 — список на проде грузится 1–3 с). Такой ответ не
  // показываем и сразу запрашиваем свежий: сама правка на сервере уже сделана.
  const editsRef = useRef(0);
  const setBoardLocal = useCallback<typeof setBoard>((update) => {
    editsRef.current += 1;
    setBoard(update);
  }, []);

  // Запрос, который СЕЙЧАС в поле. Ответ, запрошенный под другой текст, на
  // экран не попадает: фоновое обновление без поиска (вся база, на проде
  // 3–5 МБ) идёт дольше, чем поиск, и, уйдя ДО набора, приходило ПОСЛЕ —
  // список «сбрасывался» на всех кандидатов, а через 15 с поиск возвращался
  // (владелец, 21.10.2026: искал по почте, нашёл, а слева показало всех).
  const searchRef = useRef(search);
  searchRef.current = search;

  const fetchBoard = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const edits = editsRef.current;
        const data = await getCandidatesKanban({
          q: search || undefined,
          // Без поиска — до 2000 на колонку, чтобы «Все кандидаты» показывали ВСЕХ
          // (при 500 «Новый» с 468 вот-вот начал бы терять хвост при верном бейдже).
          // «Показать ещё» лишь дорисовывает загруженное. При ПОИСКЕ — 500 лучших
          // на колонку: туда подмешивается архив (тысячи совпадений), выдача
          // отсортирована по релевантности.
          per_column: search ? 500 : 2000,
        });
        if (search !== searchRef.current) {
          // Полную доску всё же запоминаем: при сбросе поиска она нужна сразу.
          if (!search) fullBoardRef.current = data;
          break;
        }
        if (edits !== editsRef.current) continue;
        setBoard(data);
        setBoardQuery(search);
        if (!search) fullBoardRef.current = data;
        break;
      }
    } catch {
      /* ignore */
    } finally {
      if (!silent) setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    fetchBoard();
  }, [fetchBoard]);

  // Лёгкий поллинг: WebSocket на проде НЕ доставляет события надёжно. Новые
  // кандидаты (парсинг, бот, импорт) и внешние смены статуса появляются сами
  // за ~15с. silent — без спиннера, выделение и скролл сохраняются. Скрытая
  // вкладка не опрашивает.
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible") fetchBoard(true);
    }, 15000);
    return () => clearInterval(id);
  }, [fetchBoard]);

  // Вернулись на вкладку/в окно — обновляем сразу: кандидат, добавленный
  // расширением с HH.ru или ботом, появляется, как только смотришь на HR-bot
  // («добавил через расширение → появился только после F5»).
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") fetchBoard(true);
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [fetchBoard]);

  // Поиск сброшен — сразу показать последнюю полную доску (свежая придёт
  // следом: fetchBoard сработает на смену запроса).
  const showFullBoard = useCallback(() => {
    if (fullBoardRef.current) {
      setBoard(fullBoardRef.current);
      setBoardQuery("");
    }
  }, []);

  // Доска получена под ДРУГОЙ запрос, чем сейчас.
  const boardStale = boardQuery !== search;
  // Прятать список нужно, только когда устаревшая доска ОТФИЛЬТРОВАНА поиском:
  // пока набирают первый запрос, доска полная — она не врёт.
  const staleFiltered = boardStale && boardQuery !== "";

  return { board, setBoard: setBoardLocal, loading, fetchBoard, showFullBoard, boardStale, staleFiltered };
}
