import { useCallback, useMemo, useRef } from "react";
import toast from "react-hot-toast";
import {
  addEntityNote,
  deleteEntityFile,
  deleteEntityNote,
  getEntity,
  setEntityPinnedEntry,
  toggleTimelineReaction,
  updateEntityNote,
  uploadEntityFile,
} from "@/services/api/entities";
import {
  deleteApplicationHistory,
  setPinnedEntry,
  updateApplication,
  updateApplicationHistory,
} from "@/services/api/vacancies";
import { changeCandidateStatus } from "@/services/api/candidates";
import type { ApplicationStage } from "@/types";
import type { EntryReaction } from "./model";

// Действия карточки кандидата (CandidateVacancyCard) — ОДНИ на «Все кандидаты»
// и на воронку. Раньше каждая страница держала свою копию этих обработчиков,
// и копии разъезжались: починка в одной не доходила до другой (рефакторинг
// HR, 20.10.2026). Здесь — запрос, сообщения и порядок «сохранили → сверились
// с сервером → перечитали ленту». Чем страницы на самом деле отличаются (где
// лежит extra_data кандидата, как переставить карточку в своём списке),
// передаётся через CardActionsEnv.

type ExtraData = Record<string, unknown>;
type Note = Record<string, unknown>;

export type RollbackInfo = {
  /** Заявка, у которой удалили запись истории; null — запись о переводе вне воронок. */
  appId: number | null;
  /** Этап заявки после отката (только для истории заявки). */
  stage: string | null;
  /** Пересчитанный общий статус кандидата. */
  entityStatus: string | null;
};

export interface CardActionsEnv {
  /** Открытый кандидат. Нет — действия с ним не уходят на сервер. */
  entityId: number | null | undefined;
  /** true — действие запрещено (сообщение показывает сам guard). */
  isBlocked?: () => boolean;
  /** Поправить extra_data кандидата на месте (мгновенный показ в ленте). */
  patchExtra: (update: (prev: ExtraData) => ExtraData) => void;
  /** Положить extra_data, прочитанный с сервера. */
  replaceExtra: (fresh: ExtraData) => void;
  /** Перечитать ленту активности (заявки, история, закрепы). */
  refreshActivity: () => Promise<void>;
  /** Перечитать файлы кандидата. */
  reloadFiles: (entityId: number) => Promise<void> | void;
  /** Воронка, к которой привязать комментарий, написанный в карточке заявки. */
  noteVacancyId: (appId: number) => number | null | undefined;
  /**
   * Сервер отменил перевод (удалили последнюю запись истории или запись о
   * переводе вне воронок) — переставить карточку на месте. Может вернуть
   * текст сообщения вместо стандартного.
   */
  onRolledBack?: (info: RollbackInfo) => string | void;
}

/** Итог смены этапа: ok и общий статус кандидата, посчитанный сервером. */
export type StageChangeResult = { ok: boolean; entityStatus: string | null };
const STAGE_FAIL: StageChangeResult = { ok: false, entityStatus: null };

type HttpError = { response?: { status?: number; data?: { detail?: string } } };
const httpError = (err: unknown) => (err as HttpError)?.response;

const isTooLong = (err: unknown) => {
  const r = httpError(err);
  return r?.status === 400 && !!r.data?.detail?.includes("too long");
};

// 409 — сервер объяснил, почему перевод не применён (карточка устарела,
// кандидат в нескольких воронках…): показываем его текст как есть.
const stageError = (err: unknown) => {
  const r = httpError(err);
  if (r?.status === 409 && r.data?.detail) return r.data.detail;
  if (isTooLong(err)) return "Комментарий слишком длинный — сократите текст";
  return "Не удалось сменить этап";
};

const notesOf = (ed: ExtraData): Note[] =>
  Array.isArray(ed.notes) ? (ed.notes as Note[]) : [];

type EnvRef = { current: CardActionsEnv };

const isBlocked = (ref: EnvRef) => !!ref.current.isBlocked?.();

// Авторитетное состояние с сервера: запрос мог «упасть» по сети, а сервер —
// успеть сохранить (с @-упоминанием он ещё рассылает уведомления), тогда
// запись появится сразу, а не после F5.
async function syncExtra(ref: EnvRef, entityId: number) {
  try {
    const fresh = await getEntity(entityId);
    if (fresh.extra_data) ref.current.replaceExtra(fresh.extra_data);
  } catch {
    /* оптимистичной правки достаточно */
  }
}

export function useCardActions(env: CardActionsEnv) {
  // Обработчики не пересоздаются на каждую смену окружения: карточка memo,
  // а страницы передают сюда свежие замыкания на каждом рендере.
  const envRef = useRef(env);
  envRef.current = env;

  const comment = useCallback(
    async (
      appId: number,
      stage: string,
      stageLabel: string,
      text: string,
      opts?: {
        // Дописка к прошлой статусной записи + этап на момент написания.
        parent_key?: string;
        stage_at_write_label?: string;
        from_status?: string;
      },
    ): Promise<boolean> => {
      const e = envRef.current;
      if (isBlocked(envRef)) return false;
      // Пустой текст — только у записи о переводе вне воронок (from_status):
      // такая строка показывает сам факт перемещения.
      if (!text.trim() && !opts?.from_status) return false;
      if (!e.entityId) {
        // Молчаливый выход здесь стоил набранного комментария (07.10.2026).
        toast.error("Кандидат не выбран — обновите страницу и повторите");
        return false;
      }
      const entityId = e.entityId;
      let saved = true;
      try {
        const resp = await addEntityNote(entityId, {
          text: text.trim(),
          stage,
          stage_label: stageLabel,
          parent_key: opts?.parent_key,
          stage_at_write_label: opts?.stage_at_write_label,
          from_status: opts?.from_status,
          vacancy_id: e.noteVacancyId(appId) ?? undefined,
        });
        e.patchExtra((prev) => ({ ...prev, notes: [...notesOf(prev), resp.note] }));
        toast.success("Комментарий сохранён");
      } catch (err) {
        saved = false;
        console.error("Failed to save comment:", err);
        toast.error(
          isTooLong(err)
            ? "Комментарий слишком длинный — сократите текст"
            : "Не удалось сохранить комментарий",
        );
      }
      await syncExtra(envRef, entityId);
      await envRef.current.refreshActivity();
      return saved;
    },
    [],
  );

  // Перевести заявку (воронку) на этап. Сервер сверит заявку с кандидатом,
  // которого человек ВИДИТ открытым (expected_entity_id): appId из устаревшей
  // ленты мог принадлежать другому кандидату той же воронки, и «Отказ» уходил
  // не тому (баг Марии 15.09.2026). Не перечитывает ленту — это делает
  // страница после своей перестановки карточки.
  const changeApplicationStage = useCallback(
    async (
      appId: number,
      stage: ApplicationStage,
      comment?: string,
    ): Promise<StageChangeResult> => {
      if (isBlocked(envRef)) return STAGE_FAIL;
      const entityId = envRef.current.entityId;
      if (!entityId) {
        toast.error("Кандидат не выбран — обновите страницу и повторите");
        return STAGE_FAIL;
      }
      try {
        const updated = await updateApplication(appId, {
          stage,
          ...(comment ? { comment } : {}),
          expected_entity_id: entityId,
        });
        return { ok: true, entityStatus: updated?.entity_status ?? null };
      } catch (err) {
        toast.error(stageError(err));
        return STAGE_FAIL;
      }
    },
    [],
  );

  // Перевести кандидата ВНЕ воронок. Запись о переводе в ленте сервер пишет в
  // той же транзакции — раньше это были два запроса, и при сбое второго в
  // ленте оставался перевод, которого не было.
  const changeStatusOutOfFunnel = useCallback(
    async (
      status: string,
      stageLabel: string,
      comment?: string,
    ): Promise<StageChangeResult> => {
      if (isBlocked(envRef)) return STAGE_FAIL;
      const e = envRef.current;
      if (!e.entityId) {
        toast.error("Кандидат не выбран — обновите страницу и повторите");
        return STAGE_FAIL;
      }
      try {
        const res = await changeCandidateStatus(e.entityId, status, {
          comment: comment?.trim() || undefined,
          stage_label: stageLabel,
        });
        if (res.note) {
          const note = res.note as Note;
          e.patchExtra((prev) => ({ ...prev, notes: [...notesOf(prev), note] }));
        }
        return { ok: true, entityStatus: res.entity_status ?? null };
      } catch (err) {
        toast.error(stageError(err));
        return STAGE_FAIL;
      }
    },
    [],
  );

  const react = useCallback(
    async (entryKey: string, emoji: string): Promise<EntryReaction[] | null> => {
      const entityId = envRef.current.entityId;
      if (!entityId) return null;
      try {
        const resp = await toggleTimelineReaction(entityId, entryKey, emoji);
        envRef.current.patchExtra((prev) => {
          const tr = { ...((prev.timeline_reactions as ExtraData | undefined) || {}) };
          if (resp.reactions?.length) tr[entryKey] = resp.reactions;
          else delete tr[entryKey];
          return { ...prev, timeline_reactions: tr };
        });
        return (resp.reactions as EntryReaction[]) || [];
      } catch {
        toast.error("Не удалось поставить реакцию");
        return null;
      }
    },
    [],
  );

  const deleteHistory = useCallback(async (appId: number, historyId: number) => {
    if (isBlocked(envRef)) return;
    try {
      const res = await deleteApplicationHistory(appId, historyId);
      // Удалили ПОСЛЕДНЮЮ запись = отменили перевод: сервер вернул заявку на
      // прежний этап и пересчитал общий статус кандидата.
      if (res?.rolled_back) {
        const msg = envRef.current.onRolledBack?.({
          appId,
          stage: res.stage,
          entityStatus: res.entity_status,
        });
        toast.success(msg || "Перевод отменён — кандидат вернулся на прежний этап");
      } else {
        toast.success("Запись удалена");
      }
    } catch {
      toast.error("Не удалось удалить запись");
    }
    await envRef.current.refreshActivity();
  }, []);

  // Текст записи о переводе живёт в самой истории (с 24.09.2026 смена этапа и
  // её комментарий — одна строка), а не в заметке.
  const editHistory = useCallback(
    async (appId: number, historyId: number, text: string) => {
      if (isBlocked(envRef)) return;
      try {
        await updateApplicationHistory(appId, historyId, text);
        toast.success("Комментарий обновлён");
      } catch (err) {
        toast.error(
          httpError(err)?.status === 403
            ? "Редактировать можно только свою запись"
            : "Не удалось отредактировать запись",
        );
      }
      await envRef.current.refreshActivity();
    },
    [],
  );

  // Закреп — один на воронку, общий для всех. Кандидат вне воронок: заявки
  // нет, закреп лежит на самой карточке.
  const pin = useCallback(async (appId: number, entryKey: string | null) => {
    if (isBlocked(envRef)) return;
    const e = envRef.current;
    try {
      if (appId > 0) {
        await setPinnedEntry(appId, entryKey);
      } else if (e.entityId) {
        await setEntityPinnedEntry(e.entityId, entryKey);
        e.patchExtra((prev) => {
          const next = { ...prev };
          if (entryKey) next.pinned_entry_key = entryKey;
          else delete next.pinned_entry_key;
          return next;
        });
      } else {
        return;
      }
      toast.success(entryKey ? "Закреплено" : "Откреплено");
    } catch {
      toast.error("Не удалось закрепить запись");
    }
    await envRef.current.refreshActivity();
  }, []);

  const deleteNote = useCallback(async (entityId: number, noteId: string) => {
    if (isBlocked(envRef)) return;
    try {
      const res = await deleteEntityNote(entityId, noteId);
      // Удалили запись о переводе у кандидата вне воронок — сервер вернул его
      // на прежний этап.
      if (res?.rolled_back && res.entity_status) {
        envRef.current.onRolledBack?.({
          appId: null,
          stage: null,
          entityStatus: res.entity_status,
        });
      }
      envRef.current.patchExtra((prev) => ({
        ...prev,
        notes: notesOf(prev).filter((n) => String(n.id) !== noteId),
      }));
      toast.success("Комментарий удалён");
    } catch {
      toast.error("Не удалось удалить комментарий");
    }
    await syncExtra(envRef, entityId);
    await envRef.current.refreshActivity();
  }, []);

  const editNote = useCallback(
    async (entityId: number, noteId: string, text: string) => {
      if (isBlocked(envRef)) return;
      try {
        const { note } = await updateEntityNote(entityId, noteId, text);
        envRef.current.patchExtra((prev) => ({
          ...prev,
          notes: notesOf(prev).map((n) =>
            String(n.id) === noteId ? (note as unknown as Note) : n,
          ),
        }));
        toast.success("Комментарий обновлён");
      } catch (err) {
        toast.error(
          isTooLong(err)
            ? "Комментарий слишком длинный — сократите текст"
            : "Не удалось отредактировать комментарий",
        );
      }
      await envRef.current.refreshActivity();
    },
    [],
  );

  const uploadFile = useCallback(async (entityId: number, file: File) => {
    if (isBlocked(envRef)) return;
    try {
      // Чип «Файл» везде грузит РЕЗЮМЕ: из него достаётся текст, по нему ищутся
      // дубли, сканы распознаются. В воронке раньше уходило «other» — та же
      // кнопка вела себя по-разному (решение владельца 20.10.2026).
      await uploadEntityFile(entityId, file, "resume");
      toast.success(`Файл "${file.name}" загружен`);
      await envRef.current.reloadFiles(entityId);
    } catch (err) {
      toast.error(httpError(err)?.data?.detail || "Ошибка загрузки файла");
    }
    await envRef.current.refreshActivity();
  }, []);

  const deleteFile = useCallback(async (fileId: number) => {
    if (isBlocked(envRef)) return;
    const entityId = envRef.current.entityId;
    if (!entityId) return;
    if (!window.confirm("Удалить этот файл?")) return;
    try {
      await deleteEntityFile(entityId, fileId);
      toast.success("Файл удалён");
      await envRef.current.reloadFiles(entityId);
    } catch {
      toast.error("Не удалось удалить файл");
    }
  }, []);

  return useMemo(
    () => ({
      changeApplicationStage,
      changeStatusOutOfFunnel,
      comment,
      react,
      deleteHistory,
      editHistory,
      pin,
      deleteNote,
      editNote,
      uploadFile,
      deleteFile,
    }),
    [changeApplicationStage, changeStatusOutOfFunnel, comment, react, deleteHistory, editHistory, pin, deleteNote, editNote, uploadFile, deleteFile],
  );
}
