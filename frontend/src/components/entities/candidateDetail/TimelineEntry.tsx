import { Trash2, ChevronDown, PenLine, Pin, Briefcase, Copy } from "lucide-react";
import clsx from "clsx";

import { HuntflowRichInput } from "@/components/hr/HuntflowRichInput";

import { sanitizeHtml } from "@/utils/sanitizeHtml";

import type { KanbanCard } from "@/services/api/candidates";
import { trimTrailingEmptyHtml, type EntryReaction } from "@/components/entities/candidateDetail/model";

import {
  REACTION_EMOJIS,
  TimelineDot,
  TimelineMetaIcon,
  TimelineUserGlyph,
  formatTimelineDate,
  htmlToPlainText,
  localZoneLabel,
} from "@/components/entities/candidateDetail/timelineParts";
import { useTimelineRowActions } from "@/components/entities/candidateDetail/useTimelineRowActions";

import type { TimelineRow } from "@/components/entities/candidateDetail/timeline";

// Одна строка ленты карточки воронки: автор и время, статус и комментарий,
// пометка «Изменено», закреп, реакции, меню строки и инлайн-правка
// (вынесено из CandidateVacancyCard, 20.10.2026, без изменения поведения).

type RowActions = ReturnType<typeof useTimelineRowActions>;

export function TimelineEntry({
  event, i, actions, card, applicationId, readonly,
  onDeleteHistory, onDeleteNote, onEditHistory, onEditNote, onPin, onReact,
}: {
  event: TimelineRow;
  /** Номер строки в видимой ленте: у первой — аватар, у остальных — точка. */
  i: number;
  actions: RowActions;
  card: KanbanCard;
  applicationId: number;
  readonly: boolean;
  onDeleteHistory: (applicationId: number, historyId: number) => Promise<void> | void;
  onDeleteNote?: (entityId: number, noteId: string) => Promise<void> | void;
  onEditHistory?: (applicationId: number, historyId: number, comment: string) => Promise<void> | void;
  onEditNote?: (entityId: number, noteId: string, text: string) => Promise<void> | void;
  onPin?: (applicationId: number, entryKey: string | null) => Promise<void> | void;
  onReact?: (entryKey: string, emoji: string) => Promise<EntryReaction[] | null>;
}) {
  const {
    reactionUser, canModifyNote, cancelEditNote, copyTimelineEntry, editingHistoryId, editingNoteId,
    editingNoteText, expandedFunnelNotes, handleReact, localReactions, reactionPickerKey,
    rowMenuKey, saveEditNote, savingNoteEdit, setEditingNoteText, setReactionPickerKey,
    setRowMenuKey, startEditHistory, startEditNote, toggleFunnelNote, togglePinned,
  } = actions;
  return (
    <div
      className="relative group/timeline first:mt-0 mt-[20px]"
    >
      {/* Лента: сплошная линия слева, кружок у каждой записи и
          аватар у самой верхней (как в Huntflow, 24.09.2026).
          Отступов у дописок больше нет — все строки в один ряд. */}
      {i === 0 ? <TimelineUserGlyph /> : <TimelineDot />}
      <div className="flex flex-wrap items-center gap-x-0 gap-y-[2px] text-[length:var(--hf-fs-xxs)] leading-[var(--hf-lh-field)] font-normal text-[color:var(--hf-alpha-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
        {event.author && (
          <span className="mr-[8px] min-w-[10px] whitespace-nowrap font-medium text-[color:var(--hf-alpha-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
            {event.author}
          </span>
        )}
        <span className="whitespace-nowrap">
          {formatTimelineDate(event.date || card.created_at)}
        </span>
        {/* «Изменено» — только пометка: автор и время в строке
            остаются от НАПИСАНИЯ, а кто и когда правил показывается
            подсказкой при наведении (требование 24.09.2026). */}
        {event.editedAt && (
          <span className="ml-[6px] whitespace-nowrap cursor-default">
            · Изменено
          </span>
        )}
        {event.pinned && (
          <span className="ml-[6px] inline-flex items-center gap-[3px] whitespace-nowrap font-medium text-[var(--hf-accent)]">
            <Pin className="h-[11px] w-[11px]" />
            Закреплено
          </span>
        )}
        {/* Смайлик-реакция у наблюдателя не рендерим вовсе: раньше
            кнопка оставалась, но без обработчика — «нажимаю, ничего не
            происходит». Уже поставленные реакции он видит ниже. */}
        {!readonly && onReact && (
        <button
          type="button"
          onClick={() =>
            setReactionPickerKey((k) =>
              k === event.reactionKey ? null : event.reactionKey,
            )
          }
          title="Поставить реакцию"
          className="inline-flex h-[18px] w-[18px] items-center justify-center rounded-full transition-colors hover:bg-[var(--hf-black-alpha-04)] focus:outline-none focus-visible:outline-none hf-dark-disabled:hover:bg-[var(--hf-white-alpha-06)]"
        >
          <TimelineMetaIcon />
        </button>
        )}
        {reactionPickerKey === event.reactionKey && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setReactionPickerKey(null)}
            />
            <div className="absolute left-[38px] top-[16px] z-20 flex items-center gap-[2px] rounded-[var(--hf-radius-s)] border border-[var(--hf-main-200)] bg-[var(--hf-white)] px-[6px] py-[3px] shadow-md hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-[var(--hf-bg-dark)]">
              {REACTION_EMOJIS.map((em) => (
                <button
                  key={em}
                  type="button"
                  onClick={() => handleReact(event.reactionKey, em)}
                  className="inline-flex h-[24px] w-[24px] items-center justify-center rounded-full text-[16px] leading-none transition-transform hover:scale-125"
                >
                  {em}
                </button>
              ))}
            </div>
          </>
        )}
        {/* Копирование и меню стоят ВПЛОТНУЮ к смайлику, а не
            улетают к правому краю: рекрутёру не нужно вести мышь
            через всю карточку (замечание владельца 24.09.2026). */}
        <div className="ml-[2px] flex items-center gap-[2px] opacity-0 transition-opacity group-hover/timeline:opacity-100">
            <button
              type="button"
              onClick={() => copyTimelineEntry(event)}
              title="Скопировать текст"
              className="inline-flex h-[18px] w-[18px] items-center justify-center rounded-full text-[var(--hf-main-500)] transition-colors hover:text-[var(--hf-main-900)] focus:outline-none focus-visible:outline-none"
            >
              <Copy className="h-[13px] w-[13px]" />
            </button>
            {(() => {
              // Одно меню на строку вместо россыпи иконок: рекрутёры
              // путались, какая из них что делает (Мария, 24.09.2026).
              const isNote = !!event.noteId;
              const mayTouchNote = isNote && canModifyNote(event.authorId);
              const canEditRow = !readonly && (
                (event.historyId != null && !!onEditHistory) ||
                (mayTouchNote && !!onEditNote)
              );
              const canPinRow =
                !readonly && !!onPin && (event.historyId != null || isNote);
              const canDeleteRow = !readonly && (
                event.historyId != null || (mayTouchNote && !!onDeleteNote)
              );
              if (!canEditRow && !canPinRow && !canDeleteRow) return null;
              const open = rowMenuKey === event.reactionKey;
              return (
                <div className="relative">
                  <button
                    type="button"
                    title="Действия с записью"
                    onClick={() =>
                      setRowMenuKey(open ? null : event.reactionKey)
                    }
                    className="inline-flex h-[18px] w-[18px] items-center justify-center rounded-full text-[var(--hf-main-500)] transition-colors hover:text-[var(--hf-main-900)] focus:outline-none focus-visible:outline-none"
                  >
                    <ChevronDown className="h-[13px] w-[13px]" />
                  </button>
                  {open && (
                    <>
                      <div
                        className="fixed inset-0 z-10"
                        onClick={() => setRowMenuKey(null)}
                      />
                      <div className="absolute right-0 top-[20px] z-20 w-[196px] overflow-hidden rounded-[var(--hf-radius-s)] border border-[var(--hf-main-200)] bg-[var(--hf-white)] py-[4px] shadow-md hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-[var(--hf-bg-dark)]">
                        {canEditRow && (
                          <button
                            type="button"
                            onClick={() => {
                              setRowMenuKey(null);
                              if (event.historyId != null) {
                                startEditHistory(
                                  event.historyId,
                                  event.body || "",
                                );
                              } else {
                                startEditNote(
                                  event.noteId as string,
                                  event.rawText || "",
                                );
                              }
                            }}
                            className="flex w-full items-center gap-[8px] px-[12px] py-[7px] text-left text-[length:var(--hf-fs-xs)] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-ui-hover)] hf-dark-disabled:text-[var(--hf-white)]"
                          >
                            <PenLine className="h-[13px] w-[13px]" />
                            Редактировать
                          </button>
                        )}
                        {canPinRow && (
                          <button
                            type="button"
                            onClick={() => togglePinned(event.reactionKey)}
                            className="flex w-full items-center gap-[8px] px-[12px] py-[7px] text-left text-[length:var(--hf-fs-xs)] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-ui-hover)] hf-dark-disabled:text-[var(--hf-white)]"
                          >
                            <Pin className="h-[13px] w-[13px]" />
                            {event.pinned ? "Открепить" : "Закрепить"}
                          </button>
                        )}
                        {canDeleteRow && (
                          <button
                            type="button"
                            onClick={() => {
                              setRowMenuKey(null);
                              if (event.historyId != null) {
                                onDeleteHistory(
                                  applicationId,
                                  event.historyId as number,
                                );
                              } else {
                                onDeleteNote?.(
                                  card.id,
                                  event.noteId as string,
                                );
                              }
                            }}
                            className="flex w-full items-center gap-[8px] px-[12px] py-[7px] text-left text-[length:var(--hf-fs-xs)] text-[var(--hf-status-red)] transition-colors hover:bg-[var(--hf-ui-hover)]"
                          >
                            <Trash2 className="h-[13px] w-[13px]" />
                            Удалить
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </div>
              );
            })()}
        </div>
      </div>
      {(editingNoteId && editingNoteId === event.noteId) ||
      (editingHistoryId != null &&
        editingHistoryId === event.historyId) ? (
        <div className="mt-[4px] overflow-hidden rounded-[var(--hf-radius-s)] border border-[var(--hf-cyan-500)] bg-[var(--hf-white)] hf-dark-disabled:bg-[var(--hf-bg-dark)]">
          {/* Панель форматирования ЗАКРЕПЛЕНА сверху, текст скроллится
              ВНУТРИ (до 240px) — иначе у длинного коммента (напр. отчёт
              после звонка) панель и «Сохранить» разъезжались в разные
              концы страницы и приходилось листать, чтобы дотянуться. */}
          <HuntflowRichInput
            value={editingNoteText}
            onChange={setEditingNoteText}
            placeholder="Текст комментария"
            toolbarClassName="flex h-[36px] items-center gap-[2px] border-b border-[var(--hf-ui-border)] px-[8px]"
            editableClassName="hf-stage-picker-textarea block max-h-[240px] w-full overflow-y-auto"
          />
          <div className="flex items-center gap-[8px] border-t border-[var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] px-[10px] py-[8px]">
            <button
              type="button"
              onClick={saveEditNote}
              disabled={
                savingNoteEdit ||
                (editingHistoryId == null && !editingNoteText.trim())
              }
              className="inline-flex h-[28px] items-center justify-center rounded-[var(--hf-radius-s)] border border-[var(--hf-main-900)] bg-[var(--hf-main-900)] px-[10px] text-[length:var(--hf-fs-xxs)] font-medium !text-[var(--hf-white)] transition-colors hover:bg-[var(--hf-main-800)] disabled:opacity-60"
            >
              Сохранить
            </button>
            <button
              type="button"
              onClick={cancelEditNote}
              disabled={savingNoteEdit}
              className="inline-flex h-[28px] items-center justify-center rounded-[var(--hf-radius-s)] border border-[var(--hf-alpha-200)] bg-[var(--hf-white)] px-[10px] text-[length:var(--hf-fs-xxs)] font-medium text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-ui-hover)]"
            >
              Отмена
            </button>
          </div>
        </div>
      ) : (
      <div className="relative text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-primary)] text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)] whitespace-pre-wrap hf-rich-content">
        {/* Своя подсказка о правке, а не нативный title: браузерный
            всплывает через ~секунду, а рекрутёру нужно сразу. Висит
            вплотную под текстом комментария, к которому относится
            (замечания владельца 24.09.2026). */}
        {event.editedAt && (
          <span className="pointer-events-none absolute left-[0px] top-full z-30 hidden whitespace-nowrap rounded-[6px] bg-[var(--hf-main-900)] px-[8px] py-[4px] text-[length:var(--hf-fs-2xs)] leading-none text-[var(--hf-white)] shadow-md group-hover/timeline:block">
            Изменено: {event.editedByName || "неизвестно"},{" "}
            {formatTimelineDate(event.editedAt)} ({localZoneLabel})
          </span>
        )}
        {(() => {
          // Одна строка: СТАТУС — комментарий. Ни стрелок «из → в»,
          // ни приставки «Этап:» (решение владельца 24.09.2026).
          // Прежний этап не пропадает совсем — он в подсказке.
          const funnelLabel = event.vacancyLabel;
          const titleText = htmlToPlainText(
            sanitizeHtml(event.title || "Событие"),
          );
          // Пустой хвост редактора («<div><br></div>») режем: иначе
          // строка занимает лишнюю высоту, а подсказка о правке
          // уезжает вниз.
          const bodyHtml = event.body
            ? trimTrailingEmptyHtml(event.body)
            : "";
          const plainBody = bodyHtml
            ? htmlToPlainText(sanitizeHtml(bodyHtml))
            : "";
          const collapsible = plainBody.length > 220;
          const collapsed =
            collapsible && !expandedFunnelNotes.has(event.reactionKey);
          const stageNode = (
            <span
              className={event.fromLabel ? "cursor-default" : undefined}
              title={
                event.fromLabel
                  ? `Перевели из этапа «${event.fromLabel}»`
                  : undefined
              }
            >
              {titleText}
            </span>
          );
          return (
            <>
              {funnelLabel && (
                <div
                  className="mb-[4px] inline-flex w-fit items-center gap-[4px] rounded-[6px] px-[7px] py-[1px] text-[length:var(--hf-fs-2xs)] font-medium"
                  style={{ background: "#e8effb", color: "#28518f" }}
                >
                  <Briefcase className="h-[11px] w-[11px]" />
                  воронка «{funnelLabel}»
                </div>
              )}
              <div>
                {bodyHtml ? (
                  <>
                    {stageNode}
                    <span className="mx-[6px] text-[var(--hf-main-500)]">
                      —
                    </span>
                    {collapsed ? (
                      <span>{plainBody.slice(0, 220).trimEnd()}…</span>
                    ) : (
                      <span
                        dangerouslySetInnerHTML={{
                          __html: sanitizeHtml(bodyHtml),
                        }}
                      />
                    )}
                    {collapsible && (
                      <button
                        type="button"
                        onClick={() => toggleFunnelNote(event.reactionKey)}
                        className="ml-[6px] align-baseline text-[length:var(--hf-fs-xs)] font-medium text-[var(--hf-accent)] underline underline-offset-2 hover:no-underline"
                      >
                        {collapsed ? "Показать ещё" : "Свернуть"}
                      </button>
                    )}
                  </>
                ) : event.isStage ? (
                  // Запись о переводе без комментария — только статус,
                  // прежний этап так же доступен подсказкой.
                  stageNode
                ) : (
                  <span
                    dangerouslySetInnerHTML={{
                      __html: sanitizeHtml(event.title || "Событие"),
                    }}
                  />
                )}
              </div>
            </>
          );
        })()}
      </div>
      )}
      {(() => {
        const rs = localReactions[event.reactionKey] || [];
        if (rs.length === 0) return null;
        const byEmoji: Record<string, string[]> = {};
        for (const r of rs)
          (byEmoji[r.emoji] ||= []).push(r.user_name || "—");
        return (
          <div className="mt-[5px] flex flex-wrap gap-[4px]">
            {Object.entries(byEmoji).map(([em, names]) => {
              const mine = rs.some(
                (r) =>
                  r.emoji === em && r.user_id === reactionUser?.id,
              );
              return (
                <button
                  key={em}
                  type="button"
                  onClick={
                    !readonly && onReact
                      ? () => handleReact(event.reactionKey, em)
                      : undefined
                  }
                  title={names.join(", ")}
                  className={clsx(
                    "inline-flex items-center gap-[3px] rounded-full border px-[7px] py-[1px] text-[12px] leading-[18px] transition-colors",
                    mine
                      ? "border-[var(--hf-cyan-500)] bg-[var(--hf-black-alpha-04)] text-[var(--hf-main-900)]"
                      : "border-[var(--hf-main-200)] text-[var(--hf-main-700)] hover:bg-[var(--hf-black-alpha-04)]",
                  )}
                >
                  <span>{em}</span>
                  <span>{names.length}</span>
                </button>
              );
            })}
          </div>
        );
      })()}
    </div>
  );
}
