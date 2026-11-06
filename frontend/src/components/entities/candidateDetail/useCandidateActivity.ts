import { useCallback, useEffect, useState } from "react";
import type { KanbanCard } from "@/services/api/candidates";
import { getEntity, getEntityActivity, type VacancyActivityBlock } from "@/services/api/entities";

// Лента открытой карточки «Все кандидаты»: заявки по воронкам (этапы, история
// переходов, закрепы) и комментарии, которые меняются, пока карточка открыта
// (вынесено из AllCandidatesPage, 20.10.2026, без изменения поведения).
//
// card.extra_data здесь правится НА МЕСТЕ (card — снимок с доски), поэтому
// после правки нужен bumpNotes(): ссылка card не меняется, и без тика лента
// не пересчитывалась (добавленный коммент появлялся только после F5).

// staticBlocks — готовые блоки без запросов и опроса: так их отдаёт удалённая
// карточка из корзины (кандидата в базе нет, спрашивать сервер не о ком).
export function useCandidateActivity(
  card: KanbanCard,
  staticBlocks?: VacancyActivityBlock[],
) {
  const [activityBlocks, setActivityBlocks] = useState<VacancyActivityBlock[]>(
    [],
  );
  // Тик для ГАРАНТИРОВАННОГО пересчёта containers после мутаций notes. Заметки
  // мержатся в card.extra_data.notes НАПРЯМУЮ (мутация по ссылке, не setState),
  // поэтому containers (useMemo по [primaryBlock, card, …]) сам по себе не
  // пересчитывается — ссылка card не меняется. Раньше рассчитывали на побочный
  // loadActivity→activityBlocks→primaryBlock, но он ненадёжен (добавленный
  // коммент появлялся только после F5). Бампаем тик руками сразу после мутации.
  const [notesVersion, setNotesVersion] = useState(0);
  const bumpNotes = useCallback(() => setNotesVersion((v) => v + 1), []);
  // Периодический рефреш extra_data (комментарии и т.п.): card — застывший снимок
  // с момента выбора/последнего поллинга доски, сам по себе не обновляется, пока
  // профиль открыт (авто-выбор карточки намеренно не перебивает открытый фокус
  // фоновым тиком доски). Из-за этого коммент, оставленный на ТОМ ЖЕ кандидате в
  // воронке, не появлялся здесь без ручного F5/переоткрытия карточки (Мария).
  // Мутируем card.extra_data напрямую (как cardActions.patchExtra) + bumpNotes.
  useEffect(() => {
    if (!card.id || staticBlocks) return;
    let cancelled = false;
    const poll = () => {
      if (document.visibilityState !== "visible") return;
      getEntity(card.id)
        .then((fresh) => {
          if (cancelled || !fresh.extra_data) return;
          card.extra_data = fresh.extra_data;
          bumpNotes();
        })
        .catch(() => {});
      // Заявки по воронкам: этапы и история переходов. Без этого смена этапа,
      // сделанная в воронке (или коллегой), на открытой карточке появлялась
      // только после F5 (2026-09-17).
      getEntityActivity(card.id)
        .then((blocks) => {
          if (!cancelled) setActivityBlocks(Array.isArray(blocks) ? blocks : []);
        })
        .catch(() => {});
    };
    const id = setInterval(poll, 15000);
    // Вернулись на вкладку — обновляем сразу, не дожидаясь тика.
    const onVisible = () => {
      if (document.visibilityState === "visible") poll();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [card, bumpNotes, staticBlocks]);
  const loadActivity = useCallback(async () => {
    if (staticBlocks) return;
    if (!card.id) {
      setActivityBlocks([]);
      return;
    }
    try {
      const blocks = await getEntityActivity(card.id);
      setActivityBlocks(Array.isArray(blocks) ? blocks : []);
    } catch {
      setActivityBlocks([]);
    }
  }, [card.id, staticBlocks]);
  useEffect(() => {
    let cancelled = false;
    if (staticBlocks) return;
    if (!card.id) {
      setActivityBlocks([]);
      return;
    }
    getEntityActivity(card.id)
      .then((blocks) => {
        if (!cancelled) setActivityBlocks(Array.isArray(blocks) ? blocks : []);
      })
      .catch(() => {
        if (!cancelled) setActivityBlocks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [card.id, staticBlocks]);

  return {
    activityBlocks: staticBlocks ?? activityBlocks,
    loadActivity,
    notesVersion,
    bumpNotes,
  };
}
