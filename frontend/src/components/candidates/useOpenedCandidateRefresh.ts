import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import type { KanbanCard } from "@/services/api/candidates";
import { detectDuplicate, getEntity, type HiddenDuplicateMeta } from "@/services/api/entities";

// Открытая на «Все кандидаты» карточка берётся из доски, которая могла устареть.
// При ОТКРЫТИИ: проверяем дубль и подтягиваем свежие данные кандидата
// (вынесено из AllCandidatesPage, 20.10.2026, без изменения поведения).

export function useOpenedCandidateRefresh(
  selectedCard: KanbanCard | null,
  setSelectedCard: Dispatch<SetStateAction<KanbanCard | null>>,
  setSelectedStatus: (status: string) => void,
  observer: boolean,
) {
  const detectTriedRef = useRef<number | null>(null);
  // id карточки, которой флаг дубля поставил локальный детект (а не сервер в
  // списке) — только такой флаг переживает рефетч профиля, см. ниже.
  const detectSetFlagRef = useRef<number | null>(null);

  // Живой детект дубля. Если флаг ещё не стоит — спрашиваем бэкенд: ловит уже
  // существующих дублей (импорт/другой источник), созданных до появления
  // детекта, без ручного «Сверить». Нашёлся — ставим hidden_duplicate_id
  // локально, и баннер появляется сам (бэкенд помечает и вторую сторону).
  useEffect(() => {
    const card = selectedCard;
    if (!card) return;
    // Наблюдателю проверку не запускаем: она ПИШЕТ найденного дубля в карточку,
    // ему запись запрещена — и на каждое открытие он получал отказ (01.10.2026).
    // Уже найденные дубли он по-прежнему видит: они лежат в карточке.
    if (observer) return;
    const extra = (card.extra_data || {}) as Record<string, unknown>;
    // Флаг с уровнем — баннер покажется и так. Флаг без level записан старым
    // правилом («одно совпадение = точный дубль») — пересчитываем его.
    const flagMeta = extra.hidden_duplicate_meta as HiddenDuplicateMeta | undefined;
    if (extra.hidden_duplicate_id && flagMeta?.level) return;
    if (detectTriedRef.current === card.id) return; // эту карточку уже проверяли
    detectTriedRef.current = card.id;
    let cancelled = false;
    detectDuplicate(card.id)
      .then((r) => {
        if (cancelled || !r?.duplicate_id) return;
        detectSetFlagRef.current = card.id;
        setSelectedCard((prev) =>
          prev && prev.id === card.id
            ? {
                ...prev,
                extra_data: {
                  ...(prev.extra_data || {}),
                  hidden_duplicate_id: r.duplicate_id,
                  ...(r.hidden_duplicate_meta
                    ? { hidden_duplicate_meta: r.hidden_duplicate_meta }
                    : {}),
                },
              }
            : prev,
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCard?.id, observer]);

  // Свежесть профиля: статус/этап/коммент могли сменить в другом месте (в
  // воронке) или прод-WebSocket не доставил апдейт. Без этого актуальность была
  // видна только после F5.
  useEffect(() => {
    const id = selectedCard?.id;
    if (!id) return;
    let cancelled = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    getEntity(id).then((e: any) => {
      if (cancelled || !e?.id || e.id !== id) return;
      // Отметка детекта одноразовая: она прикрывает только гонку этого открытия.
      const keepDetectedFlag = detectSetFlagRef.current === id;
      if (keepDetectedFlag) detectSetFlagRef.current = null;
      setSelectedCard((prev) => {
        if (!prev || prev.id !== id) return prev;
        const prevExtra = (prev.extra_data || {}) as Record<string, unknown>;
        const mergedExtra = { ...((e.extra_data || {}) as Record<string, unknown>) };
        // hidden_duplicate_id (детект дубля) и is_archived (диплинк архивного)
        // проставляются локально — не теряем их при рефетче. Флаг и мета — парой:
        // рефетч мог прийти раньше, чем детект их записал. Держимся только за
        // флаг, который поставил детект этой карточки: флаг из списка мог
        // устареть — сервер снимает его при правке второй анкеты пары.
        if (
          prevExtra.hidden_duplicate_id &&
          !mergedExtra.hidden_duplicate_id &&
          keepDetectedFlag
        ) {
          mergedExtra.hidden_duplicate_id = prevExtra.hidden_duplicate_id;
          if (prevExtra.hidden_duplicate_meta) {
            mergedExtra.hidden_duplicate_meta = prevExtra.hidden_duplicate_meta;
          }
        }
        if (prevExtra.is_archived && !mergedExtra.is_archived) {
          mergedExtra.is_archived = prevExtra.is_archived;
        }
        return {
          ...prev,
          name: e.name ?? prev.name,
          email: e.email ?? prev.email,
          phone: e.phone ?? prev.phone,
          position: e.position ?? prev.position,
          company: e.company ?? prev.company,
          tags: e.tags ?? prev.tags,
          photo_url: e.photo_url ?? prev.photo_url,
          extra_data: mergedExtra,
        } as KanbanCard;
      });
      if (typeof e.status === "string" && e.status) setSelectedStatus(e.status);
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCard?.id]);
}
