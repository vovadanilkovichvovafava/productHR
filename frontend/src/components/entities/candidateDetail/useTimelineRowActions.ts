import { useCallback, useState } from "react";
import toast from "react-hot-toast";
import { useAuthStore } from "@/stores/authStore";
import { sanitizeHtml } from "@/utils/sanitizeHtml";
import type { KanbanCard } from "@/services/api/candidates";
import type { EntryReaction } from "./model";
import { htmlToPlainText } from "./timelineParts";

// Действия со строками ленты карточки воронки: раскрытие длинного комментария,
// правка комментария и записи о переводе, меню строки, реакции, закреп,
// копирование (вынесено из CandidateVacancyCard, 20.10.2026, без изменения
// поведения).

export interface TimelineRowActionsParams {
  card: KanbanCard;
  applicationId: number;
  pinnedEntryKey?: string | null;
  onReact?: (entryKey: string, emoji: string) => Promise<EntryReaction[] | null>;
  onEditHistory?: (applicationId: number, historyId: number, comment: string) => Promise<void> | void;
  onEditNote?: (entityId: number, noteId: string, text: string) => Promise<void> | void;
  onPin?: (applicationId: number, entryKey: string | null) => Promise<void> | void;
}

export function useTimelineRowActions({
  card, applicationId, pinnedEntryKey, onReact, onEditHistory, onEditNote, onPin,
}: TimelineRowActionsParams) {
  // «Все кандидаты»: длинные комменты с бейджем воронки свёрнуты (виден только
  // бейдж); клик по бейджу раскрывает текст. Множество раскрытых — по reactionKey.
  const [expandedFunnelNotes, setExpandedFunnelNotes] = useState<Set<string>>(
    () => new Set(),
  );
  const toggleFunnelNote = (key: string) =>
    setExpandedFunnelNotes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  // Инлайн-редактирование комментария: id заметки, которая сейчас редактируется.
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  // Правка комментария у записи о ПЕРЕВОДЕ — та же форма, что у комментария,
  // поэтому текст и флаг сохранения общие (24.09.2026).
  const [editingHistoryId, setEditingHistoryId] = useState<number | null>(null);
  const [editingNoteText, setEditingNoteText] = useState("");
  const [savingNoteEdit, setSavingNoteEdit] = useState(false);
  // Меню строки ленты (шеврон): Редактировать / Закрепить / Удалить.
  const [rowMenuKey, setRowMenuKey] = useState<string | null>(null);

  // --- Эмодзи-реакции на записи таймлайна ---
  const { user: reactionUser } = useAuthStore();
  // Правка/удаление комментария — только автор либо admin/owner/superadmin
  // (зеркалит бэковую _note_can_modify): показывать кнопки остальным бессмысленно,
  // сервер всё равно ответит 403.
  const canModifyNote = (authorId?: number) => {
    if (!reactionUser) return false;
    if (reactionUser.role === "superadmin") return true;
    if (reactionUser.org_role === "owner" || reactionUser.org_role === "admin")
      return true;
    return authorId !== undefined && authorId === reactionUser.id;
  };
  const [reactionPickerKey, setReactionPickerKey] = useState<string | null>(null);
  const [localReactions, setLocalReactions] = useState<
    Record<string, EntryReaction[]>
  >(
    () =>
      (card.extra_data?.timeline_reactions as
        | Record<string, EntryReaction[]>
        | undefined) || {},
  );
  const handleReact = useCallback(
    async (entryKey: string, emoji: string) => {
      setReactionPickerKey(null);
      if (!onReact) return;
      const updated = await onReact(entryKey, emoji);
      if (updated === null) return;
      setLocalReactions((prev) => {
        const next = { ...prev };
        if (updated.length) next[entryKey] = updated;
        else delete next[entryKey];
        return next;
      });
    },
    [onReact],
  );

  const startEditNote = (noteId: string, rawText: string) => {
    setEditingHistoryId(null);
    setEditingNoteId(noteId);
    setEditingNoteText(rawText);
  };

  const startEditHistory = (historyId: number, rawText: string) => {
    setEditingNoteId(null);
    setEditingHistoryId(historyId);
    setEditingNoteText(rawText);
  };

  const cancelEditNote = () => {
    setEditingNoteId(null);
    setEditingHistoryId(null);
    setEditingNoteText("");
  };

  const saveEditNote = async () => {
    const text = editingNoteText.trim();
    setSavingNoteEdit(true);
    try {
      if (editingHistoryId != null) {
        // У перевода комментарий можно и стереть целиком — останется чистая
        // строка со статусом, поэтому пустой текст здесь допустим.
        if (!onEditHistory) return;
        await onEditHistory(applicationId, editingHistoryId, text);
      } else {
        if (!editingNoteId || !text || !onEditNote) return;
        await onEditNote(card.id, editingNoteId, text);
      }
      cancelEditNote();
    } finally {
      setSavingNoteEdit(false);
    }
  };

  // Закрепить/открепить строку: закреп один на воронку, поэтому повторный
  // клик по уже закреплённой снимает его.
  const togglePinned = async (entryKey: string) => {
    if (!onPin) return;
    setRowMenuKey(null);
    // applicationId = 0 — кандидат вне воронок: страница сама положит закреп на
    // карточку, а не на заявку (закреплять всё равно нужно, 24.09.2026).
    await onPin(applicationId, pinnedEntryKey === entryKey ? null : entryKey);
  };

  // --- Дописка комментария к прошлой статусной записи (запрос Марии) ---
  // Копировать текст записи таймлайна (статус/комментарий/отчёт после звонка)
  // в буфер обмена — доступно ВСЕМ, включая наблюдателя (просмотр без права
  // редактировать всё равно должен уметь забрать текст себе).
  const copyTimelineEntry = async (row: {
    title?: string;
    body?: string;
  }) => {
    const parts = [
      htmlToPlainText(sanitizeHtml(row.title || "")),
      row.body ? htmlToPlainText(sanitizeHtml(row.body)) : "",
    ].filter(Boolean);
    const text = parts.join("\n\n");
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Скопировано");
    } catch {
      toast.error("Не удалось скопировать");
    }
  };

  return {
    reactionUser, canModifyNote, cancelEditNote, copyTimelineEntry, editingHistoryId, editingNoteId,
    editingNoteText, expandedFunnelNotes, handleReact, localReactions, reactionPickerKey,
    rowMenuKey, saveEditNote, savingNoteEdit, setEditingNoteText, setReactionPickerKey,
    setRowMenuKey, startEditHistory, startEditNote, toggleFunnelNote, togglePinned,
  };
}
