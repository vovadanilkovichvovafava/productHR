import { parseServerDate } from "@/utils/date";
import type { ActivityEvent } from "@/services/api/entities";
import type { ContainerNote } from "./model";

// Лента карточки воронки (CandidateVacancyCard): какие строки и в каком порядке
// — вынесено из карточки (20.10.2026) чистыми функциями, под тестами
// (__tests__/timeline.test.ts). Правила — из разбора с Марией 24.09.2026:
// одна запись = одно событие «СТАТУС — комментарий», без стрелок «из → в».

// Таймлайн контейнера = его СОБСТВЕННЫЕ notes (комментарии) как строки лога,
// плюс — только для живого контейнера — реальная история переходов (events).
// Merged-контейнеры показывают строго свои notes (read-only).
export type TimelineRow = {
  date?: string;
  title?: string;
  body?: string;
  author?: string;
  historyId?: number;
  // Заметки (extra_data.notes) удаляются НЕ через историю переходов
  // (StageTransition), а отдельным DELETE /entities/{id}/notes/{note_id}.
  noteId?: string;
  // Исходный текст заметки (без "Этап: X" префикса) — нужен только для
  // предзаполнения инлайн-редактора, не для отображения.
  rawText?: string;
  // Автор заметки — для проверки прав редактирования/удаления на фронте
  // (бэк и так это проверяет, но кнопки не должны показываться тем, кому
  // всё равно откажут: правит/удаляет только автор либо admin/owner/superadmin).
  authorId?: number;
  // Когда заметка последний раз отредактирована (бэк проставляет сам).
  editedAt?: string;
  reactionKey: string;
  // Тип записи для фильтра «Действия»: смена этапа vs свободный комментарий.
  kind: "stage" | "comment";
  // Статусная запись (переход или заметка-этап) — к ней можно дописывать
  // комментарии (кнопка «+коммент»).
  isStage?: boolean;
  // Дописанный коммент, привязанный к родительской статусной записи:
  // parentKey — reactionKey родителя, stageAtWrite — метка этапа на момент
  // написания (жёлтая плашка), indented — рисуем с отступом под родителем.
  parentKey?: string;
  stageAtWrite?: string;
  indented?: boolean;
  // Этап, ИЗ которого перевели (подсказка при наведении на статус).
  fromLabel?: string;
  // Кто правил комментарий (для подсказки у пометки «Изменено»).
  editedByName?: string;
  // Строка закреплена: показывается первой, со своего места по дате уходит.
  pinned?: boolean;
  // «Все кандидаты»: воронка, в которой оставлен коммент (бейдж + сворачивание
  // длинного текста). null = нет привязки/не тот контекст → без бейджа.
  vacancyLabel?: string | null;
};

export interface TimelineSource {
  notes: ContainerNote[];
  events?: ActivityEvent[];
  /** Снапшот влитого дубля: только свои заметки, без переходов и «Кандидат добавлен». */
  snapshot: boolean;
  getStageLabel: (stage: string) => string;
  addedAt?: string;
  createdAt?: string;
  recruiterName?: string;
  resolveNoteVacancyLabel?: (vacancyId?: number | null) => string | null;
}

export function buildTimelineRows({
  notes, events, snapshot, getStageLabel, addedAt, createdAt, recruiterName, resolveNoteVacancyLabel,
}: TimelineSource): TimelineRow[] {
  const noteRows = (Array.isArray(notes) ? notes : [])
    .filter((note) => note && (note.text || note.stage_label))
    .map((note) => ({
      date: note.date || undefined,
      // Строка ленты = СТАТУС, а под ним/через тире — комментарий (запрос
      // Марии 24.09.2026: «мне нужен статус и под ним коммент»). Приставки
      // «Этап:» больше нет. У дописки статус свой — тот, на котором её
      // написали (stage_at_write_label), поэтому она встаёт в общий поток
      // наравне с остальными, без отступа и жёлтой плашки.
      title:
        note.stage_at_write_label ||
        note.stage_label ||
        note.text ||
        "Комментарий",
      body:
        note.stage_at_write_label || note.stage_label
          ? note.text || undefined
          : undefined,
      author: note.author_name || undefined,
      noteId: note.id ? String(note.id) : undefined,
      rawText: note.text || "",
      authorId: typeof note.author_id === "number" ? note.author_id : undefined,
      editedAt: note.edited_at || undefined,
      editedByName: note.edited_by_name || undefined,
      reactionKey: note.id ? `n:${note.id}` : `nd:${note.date || ""}`,
      // Заметки (extra_data.notes) — это КОММЕНТАРИИ (даже если несут stage_label
      // текущего этапа). Смена этапа — отдельные события (eventRows, kind=stage).
      kind: "comment" as const,
      // Заметка-этап (несёт stage_label) — тоже статусная запись, к ней можно
      // дописывать комменты (напр. стартовое «Этап: Новый»).
      isStage: !!note.stage_label,
      parentKey: note.parent_key || undefined,
      stageAtWrite: note.stage_at_write_label || undefined,
      vacancyLabel: resolveNoteVacancyLabel
        ? resolveNoteVacancyLabel(note.vacancy_id)
        : null,
    }));

  const eventRows = (!snapshot && Array.isArray(events) ? events : []).map(
    (ev) => {
      const to = getStageLabel(ev.to_stage);
      const from = ev.from_stage ? getStageLabel(ev.from_stage) : null;
      return {
        date: ev.created_at || undefined,
        // Только новый этап: стрелки «Новый → Интервью с HR» убрали — смена
        // этапа теперь просто новая строка (решение владельца 24.09.2026).
        // Прежний этап не теряем: показываем подсказкой при наведении, это
        // спасает, когда соседнюю запись удалили и не понять, откуда пришёл.
        title: to,
        fromLabel: from || undefined,
        body: ev.comment || undefined,
        author: ev.changed_by_name || undefined,
        historyId: ev.id as number | undefined,
        reactionKey: `e:${ev.id}`,
        kind: "stage" as const,
        isStage: true,
        editedAt: ev.edited_at || undefined,
        editedByName: ev.edited_by_name || undefined,
      };
    },
  );

  // Дописки (parentKey) раньше вкладывались под родительскую запись с
  // отступом — рекрутёры путались, к какому статусу относится текст. Теперь
  // они идут общим потоком по дате, а их собственный этап уже стоит в
  // заголовке строки (24.09.2026).
  const topLevelNotes = noteRows;

  const tsOf = (d?: string) => (d ? parseServerDate(d).getTime() : 0);
  // parseServerDate, а НЕ new Date: у заметок время aware-UTC («…+00:00»), а у
  // событий этапа — naive из БД («…T14:34:00»). Сырой new Date() читает naive как
  // ЛОКАЛЬНОЕ, а aware как UTC — записи из двух источников сравнивались в разных
  // системах отсчёта, и лента шла вразброс.
  const base: TimelineRow[] = [...eventRows, ...topLevelNotes].sort(
    (a, b) => tsOf(b.date) - tsOf(a.date),
  );
  if (base.length === 0) {
    // Влитые (read-only) контейнеры без заметок/событий НЕ показывают
    // синтетическое «Кандидат добавлен»: иначе каждый объединённый дубль
    // плодит свой зелёный «new», и лента засоряется N одинаковыми записями.
    if (snapshot) return [];
    return [
      {
        date: addedAt || createdAt,
        title: "Кандидат добавлен",
        author: recruiterName || undefined,
        reactionKey: "created",
        kind: "stage" as const,
        isStage: true,
      },
    ];
  }
  return base;
}

/** Закреплённая запись — в самый верх; со своего места по дате уходит (24.09.2026). */
export function pinTimelineRow(rows: TimelineRow[], pinnedEntryKey?: string | null): TimelineRow[] {
  if (!pinnedEntryKey) return rows;
  const idx = rows.findIndex((row) => row.reactionKey === pinnedEntryKey);
  if (idx < 0) return rows;
  return [{ ...rows[idx], pinned: true }, ...rows.filter((_, i) => i !== idx)];
}
