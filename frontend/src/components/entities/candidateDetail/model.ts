// ================================================================
// CandidateDetail — pure domain model for the candidate detail panel.
//
// Extracted VERBATIM from AllCandidatesPage's InfoTab so the panel can be
// reused (funnel + «Все кандидаты») WITHOUT forking behaviour. These are the
// "key methods": container/history assembly, note dedup, file classification,
// résumé-source derivation, stage-label resolution. They are PURE (no React,
// no I/O) and unit-tested in ./__tests__/model.test.ts — the safety net that
// guards the upcoming component extraction (zero-regression requirement).
// ================================================================
import { BOARD_OTHER_LABEL, STAGE_LABEL_BY_STAGE } from "@/constants/hrStages";
import type { KanbanCard, KanbanColumn } from "@/services/api/candidates";
import type { ActivityEvent, EntityFile } from "@/services/api/entities";
import {
  STATUS_LABELS,
  STATUS_TO_STAGE_MAP,
  BOARD_OTHER_STATUS,
  type EntityStatus,
} from "@/types";

// ── Types (moved from AllCandidatesPage — the panel's domain shapes) ──

export type DetailSection = "info" | "resume" | "anketa";

/** Комментарий (лог) одного контейнера. */
export type ContainerNote = {
  id?: string;
  text?: string;
  date?: string;
  stage?: string;
  stage_label?: string;
  author_id?: number;
  author_name?: string;
  edited_at?: string;
  /** Кто правил комментарий — для подсказки у пометки «Изменено». */
  edited_by_name?: string;
  // Дописка коммента к прошлой статусной записи: reactionKey родителя +
  // метка этапа на момент написания (плашка «оставлен на этапе X»).
  parent_key?: string;
  stage_at_write_label?: string;
  // Воронка (вакансия), в которой написан коммент; отсутствует = «Общий».
  vacancy_id?: number | null;
};

/** Резюме-демо одного контейнера (минимально нужные поля). */
export type ContainerResumeDemo = {
  title?: string;
  subtitle?: string;
  saved_at?: string;
  vacancy_title?: string;
};

/**
 * «Контейнер» = исторический блок-статус с собственным логом. Стек кандидата =
 * [ собственный живой контейнер ] + card.extra_data.merged_from[]. Это НЕ
 * вакансии: каждый контейнер изолирован своим status (цвет/лейбл) и notes (лог).
 */
export type StageContainer = {
  origin: "live" | "merged";
  applicationId: number;
  status: string;
  name: string | null;
  notes: ContainerNote[];
  resumeDemos: ContainerResumeDemo[];
  vacancyTitle: string | null;
  addedAt?: string;
  events?: ActivityEvent[];
  fileIds?: number[];
  files?: EntityFile[];
  /** Закреплённая запись ленты ЭТОЙ воронки («e:<id>» / «n:<uuid>»). */
  pinnedEntryKey?: string | null;
  /** Импортированное прохождение (ClickUp-архив): рекрутёр (текст) + анкета (Q&A). Read-only. */
  recruiter?: string;
  anketa?: Array<{ question: string; answer: string }>;
};

export type ResumeSource =
  | { kind: "parsed" }
  | { kind: "pdf"; file: EntityFile }
  | { kind: "images" }
  // Текст резюме, вписанный руками в форму «Новый кандидат» / «Редактировать».
  | { kind: "text"; text: string };

export type ResumeDemoData = {
  title?: string;
  subtitle?: string;
  salary?: string;
  saved_at?: string;
  vacancy_title?: string;
  sections?: Array<{ title: string; lines: string[] }>;
};

// ── Stage status helpers ──

/** Этапы, при которых карточка остаётся нейтрально-серой (не «в процессе»). */
export const NEUTRAL_STAGE_STATUSES = new Set([
  "rejected",
  "fired",
  "archived",
]);

/** Этап считается «отклонённым» (серая карточка даже когда она единственная). */
export const isRejectedStage = (stage: string): boolean =>
  NEUTRAL_STAGE_STATUSES.has(stage);

/** Этапы, после которых «следующего» не бывает: отказ, резерв, архив. */
export const TERMINAL_STAGE_STATUSES = new Set([
  ...NEUTRAL_STAGE_STATUSES,
  "reserve",
  "withdrawn",
]);

/**
 * Варианты для окна «Сменить этап подбора» на «Все кандидаты». Колонки доски —
 * это статусы кандидата, и среди них есть служебная «Вне воронки»
 * (BOARD_OTHER_STATUS): она значит «кандидат не в воронке», а не этап. У заявки
 * такого этапа нет — выбрать её было можно, но сохранить некуда: заявка не
 * менялась, а карточка на доске всё равно переезжала (жалоба Марии, Гром
 * Виктор, 24.09.2026). Поэтому в пикер она не попадает вовсе.
 */
export function buildStagePickerOptions(
  columns: Array<{ status: string; label: string }>,
): Array<{ status: string; label: string; isRealStage: true }> {
  return columns
    .filter((c) => c.status !== BOARD_OTHER_STATUS)
    .map((c) => ({ status: c.status, label: c.label, isRealStage: true as const }));
}

/**
 * Какой этап пикер помечает при ОТКРЫТИИ — следующий за текущим (Huntflow:
 * «переместить» почти всегда значит «на шаг вперёд», рекрутёру остаётся
 * нажать «Сохранить»). Отказ/резерв/архив пропускаем: подставлять их сам
 * пикер не должен, такое решение выбирают руками. Если следующего нет
 * (кандидат уже на последнем или на отказе) — остаётся текущий, и карточка
 * показывает серую плашку «уже на этом этапе».
 */
export function nextStageStatus(
  options: Array<{ status: string }>,
  current: string,
): string {
  if (TERMINAL_STAGE_STATUSES.has(current)) return current;
  const idx = options.findIndex((o) => o.status === current);
  if (idx < 0) return current;
  const next = options
    .slice(idx + 1)
    .find((o) => !TERMINAL_STAGE_STATUSES.has(o.status));
  return next ? next.status : current;
}

/** Подписи этапов карточки вакансии — общий справочник (constants/hrStages.ts). */
export const CANDIDATE_VACANCY_STAGE_LABELS: Record<string, string> = STAGE_LABEL_BY_STAGE;

/**
 * Лейбл статуса контейнера (EntityStatus → русский). Приоритет: org-override из
 * колонок доски → канон STATUS_LABELS → локальный CANDIDATE_VACANCY_STAGE_LABELS
 * → сам ключ.
 */
export function resolveContainerStatusLabel(
  status: string,
  columns: KanbanColumn[],
): string {
  const col = columns.find((c) => c.status === status);
  return (
    col?.label ||
    (STATUS_LABELS as Record<string, string>)[status] ||
    CANDIDATE_VACANCY_STAGE_LABELS[status] ||
    (status === BOARD_OTHER_STATUS ? BOARD_OTHER_LABEL : status)
  );
}

/** Чип этапа в СТРОКЕ списка «Все кандидаты». */
export type ListRowStage = {
  /** Ключ этапа заявки — по нему берётся цвет чипа. */
  stage: string;
  label: string;
  /** Воронка, к которой относится этап; null — кандидат ни в одной воронке. */
  vacancyTitle: string | null;
};

/**
 * Этапы для строки списка: по одному на воронку, а если воронок НЕТ — общий
 * статус самого кандидата (запрос владельца 23.09.2026: «пусть этап
 * отображается у всех, для удобства»). Раньше строка кандидата вне воронок
 * была без чипа вообще, и по списку нельзя было понять, где человек.
 */
export function buildListRowStages(
  funnels: Array<{ vacancy_title: string; stage: string }> | undefined,
  entityStatus: string | undefined,
  columns: KanbanColumn[],
  stageLabels: Record<string, string>,
): ListRowStage[] {
  const list = funnels || [];
  if (list.length > 0) {
    return list.map((f) => ({
      stage: f.stage,
      label: stageLabels[f.stage] || f.stage,
      vacancyTitle: f.vacancy_title,
    }));
  }
  if (!entityStatus) return [];
  return [
    {
      // Цвет чипа берётся по ЭТАПУ заявки, а статусы кандидата называются
      // иначе (probation ↔ phone_screen и т.п.) — переводим по общей карте.
      stage: STATUS_TO_STAGE_MAP[entityStatus as EntityStatus] || entityStatus,
      label: resolveContainerStatusLabel(entityStatus, columns),
      vacancyTitle: null,
    },
  ];
}

/**
 * Убирает ПУСТОЙ хвост богатого текста: `<br>`, `<div><br></div>`, `<p></p>`
 * и пробелы в конце. Редактор оставляет их после Enter, и строка ленты
 * раздувалась на лишнюю строку — из-за этого подсказка «Изменено» висела
 * далеко под текстом (замечание владельца 24.09.2026).
 */
export function trimTrailingEmptyHtml(html: string): string {
  let out = (html || "").trim();
  let prev = "";
  while (out !== prev) {
    prev = out;
    out = out
      .replace(/(?:\s|&nbsp;|<br\s*\/?>)+$/i, "")
      .replace(/<(div|p)>(?:\s|&nbsp;|<br\s*\/?>)*<\/\1>$/i, "")
      .trim();
  }
  return out;
}

// ── File classification ──

/**
 * Авто-файл = постраничный скан резюме у КАРТИНКИ («…стр. N…», «cv_page»,
 * «_page») ИЛИ авто-извлечённое фото-аватар («Фото_…»). Такие файлы — это
 * рендеры/аватар, а не вложения, и в список «Файлы» не идут.
 */
export function isAutoGeneratedFile(file: EntityFile): boolean {
  const name = file.file_name || "";
  const isImage = (file.mime_type || "").startsWith("image/");
  return (
    (isImage && /стр\.?\s*\d|cv_page|_page\b/i.test(name)) ||
    /^Фото_/i.test(name)
  );
}

// ── Résumé sources (pure part of useResumeSources) ──

/**
 * Из файлов кандидата + extra_data собирает список вкладок «Резюме»:
 * [распарсенное] + [каждый PDF, новое сверху] + [сканы-картинки — ТОЛЬКО если
 * другого резюме нет, иначе это дубль].
 */
export function buildResumeSources(
  files: EntityFile[],
  extraData: Record<string, unknown> | undefined,
): ResumeSource[] {
  const resumeFiles = files.filter((f) => f.file_type === "resume");
  const pdfFiles = resumeFiles
    .filter((f) => f.mime_type === "application/pdf")
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  const imageFiles = resumeFiles.filter((f) =>
    f.mime_type?.startsWith("image/"),
  );
  const resumeDemo = extraData?.resume_demo as ResumeDemoData | undefined;
  const resumeDemos = (
    Array.isArray(extraData?.resume_demos)
      ? (extraData?.resume_demos as ResumeDemoData[])
      : resumeDemo
        ? [resumeDemo]
        : []
  ).filter(Boolean);

  // Текст резюме из формы (`resume_text`). Раньше карточка его не показывала
  // вовсе: Мария вставила резюме текстом при создании, оно сохранилось, а во
  // вкладке «Резюме» было пусто — «добавляю текст резюме, он не добавляется к
  // карточке» (15.10.2026). Окно разбора файла кладёт сюда же краткое `summary`
  // (resume_text === summary) — это пересказ уже показанного PDF, его не дублируем.
  const resumeText =
    typeof extraData?.resume_text === "string" ? extraData.resume_text.trim() : "";
  const summary =
    typeof extraData?.summary === "string" ? extraData.summary.trim() : "";
  const textSource =
    resumeText && resumeText !== summary
      ? [{ kind: "text" as const, text: resumeText }]
      : [];

  return [
    ...(resumeDemos.length > 0 ? [{ kind: "parsed" as const }] : []),
    ...pdfFiles.map((file) => ({ kind: "pdf" as const, file })),
    ...(imageFiles.length > 0 &&
    resumeDemos.length === 0 &&
    pdfFiles.length === 0
      ? [{ kind: "images" as const }]
      : []),
    ...textSource,
  ];
}

// ── Stage containers (pure part of the `containers` useMemo) ──

/**
 * Собирает стек контейнеров кандидата: [ собственный живой ] + merged_from[].
 * Живой контейнер — из самого кандидата (card); merged — плоский массив влитых
 * дублей (транзитивные слияния уже подняты в корень бэкендом). Заметки источника
 * вычитаются из живого (flat-merge на бэкенде их задваивает). Авто-файлы
 * (постраничные сканы / фото-аватар) исключаются из списков файлов контейнеров.
 *
 * `liveApplicationId` / `liveEvents` / `liveVacancyTitle` вычисляет вызывающая
 * сторона (primaryBlock + getVacancyStageLabel) — модель остаётся чистой.
 *
 * `liveBlocks` (заявки кандидата по воронкам) — если переданы, живой контейнер
 * разворачивается в ОТДЕЛЬНУЮ карточку на каждую воронку: своя заявка, свой этап,
 * своя история и свои комментарии. Без этого кандидат в двух воронках показывал
 * одну карточку: комментарии второй воронки не появлялись на «Все кандидаты», а
 * смена этапа там меняла только одну заявку (2026-09-17, Мария).
 */
export function buildStageContainers(params: {
  card: KanbanCard;
  status: string;
  liveApplicationId: number;
  liveEvents?: ActivityEvent[];
  liveVacancyTitle: string | null;
  liveBlocks?: Array<{
    application_id: number;
    vacancy_id?: number | null;
    vacancy_title?: string | null;
    current_stage?: string | null;
    events?: ActivityEvent[];
    pinned_entry_key?: string | null;
  }>;
  allEntityFiles: EntityFile[];
  /** Закреп живой заявки, когда блоков ленты не передают (страница воронки). */
  livePinnedEntryKey?: string | null;
}): StageContainer[] {
  const {
    card,
    status,
    liveApplicationId,
    liveEvents,
    liveVacancyTitle,
    liveBlocks,
    allEntityFiles,
    livePinnedEntryKey,
  } = params;

  const mergedRaw = Array.isArray(
    (card.extra_data as Record<string, unknown> | undefined)?.merged_from,
  )
    ? ((card.extra_data as Record<string, unknown>)
        .merged_from as Array<Record<string, unknown>>)
    : [];

  const mergedContainers: StageContainer[] = mergedRaw.map((m, i) => {
    const ed = (m.extra_data as Record<string, unknown> | undefined) || {};
    return {
      origin: "merged" as const,
      // Фиктивный (отрицательный) ключ — merged read-only, действий нет.
      applicationId: -(i + 1),
      status: typeof m.status === "string" ? m.status : "new",
      name: typeof m.name === "string" ? m.name : null,
      notes: Array.isArray(ed.notes) ? (ed.notes as ContainerNote[]) : [],
      resumeDemos: Array.isArray(ed.resume_demos)
        ? (ed.resume_demos as ContainerResumeDemo[])
        : [],
      vacancyTitle:
        typeof m.vacancy_title === "string" ? m.vacancy_title : null,
      addedAt: typeof m.added_at === "string" ? m.added_at : undefined,
      fileIds: Array.isArray(m.file_ids) ? (m.file_ids as number[]) : [],
    };
  });

  // Вычитаем из живого все заметки, уже показанные во влитых контейнерах — иначе
  // flat-merge их задваивает на «Новом». Ключ — id; при его отсутствии (легаси/
  // импорт ClickUp/CSV) добавляем author_id к text+date: без автора две РАЗНЫЕ
  // заметки с одинаковым текстом и датой схлопывались как «дубль» и одна пропадала.
  const _noteSig = (n?: ContainerNote) =>
    (n && n.id) || `${n?.author_id ?? ""}|${n?.text ?? ""}|${n?.date ?? ""}`;
  const _mergedNoteSigs = new Set(
    mergedContainers.flatMap((c) => c.notes.map(_noteSig)),
  );
  const _liveNotes = (
    Array.isArray(card.extra_data?.notes)
      ? (card.extra_data.notes as ContainerNote[])
      : []
  ).filter((n) => !_mergedNoteSigs.has(_noteSig(n)));

  const _resumeDemos = Array.isArray(card.extra_data?.resume_demos)
    ? (card.extra_data.resume_demos as ContainerResumeDemo[])
    : [];

  // Заявки по воронкам: карточка на каждую. Комментарии раскладываем по своей
  // воронке (note.vacancy_id); «общие» (без воронки, легаси) — в первую карточку,
  // чтобы не задваивались.
  const _blocks = (liveBlocks || []).filter((b) => b && b.application_id);
  const liveContainers: StageContainer[] = _blocks.length
    ? _blocks.map((b, i) => ({
        origin: "live" as const,
        applicationId: b.application_id,
        status: b.current_stage || status,
        name: card.name,
        notes: _liveNotes.filter((n) => {
          const nv = (n as { vacancy_id?: number | null })?.vacancy_id;
          return nv == null ? i === 0 : nv === b.vacancy_id;
        }),
        resumeDemos: i === 0 ? _resumeDemos : [],
        vacancyTitle: b.vacancy_title ?? null,
        addedAt: i === 0 ? card.created_at : undefined,
        events: b.events,
        pinnedEntryKey: b.pinned_entry_key ?? null,
      }))
    : [
        {
          origin: "live" as const,
          applicationId: liveApplicationId,
          status,
          name: card.name,
          notes: _liveNotes,
          resumeDemos: _resumeDemos,
          vacancyTitle: liveVacancyTitle,
          addedAt: card.created_at,
          events: liveEvents,
          pinnedEntryKey: livePinnedEntryKey ?? null,
        },
      ];
  const liveContainer = liveContainers[0];

  // Файлы по контейнерам: исключаем авто-файлы; merged показывает СВОИ file_ids;
  // живой — остальные (не смёрдженные), т.е. свои собственные документы.
  const _docFiles = (allEntityFiles || []).filter(
    (f) => !isAutoGeneratedFile(f),
  );
  const _mergedFileIds = new Set(
    mergedContainers.flatMap((c) => c.fileIds || []),
  );
  // Один и тот же документ (то же имя+тип) часто прилетает ПОВТОРНО из каждого
  // влитого дубля как отдельная EntityFile-строка — показываем его ОДИН раз, в
  // первом «забравшем» контейнере. Иначе резюме «Иванов.pdf» дублируется N раз
  // (по числу объединений) и в ленте, и в списке «Файлы».
  const _fileSig = (f: EntityFile) =>
    `${f.file_name ?? ""}|${f.file_type ?? ""}|${f.mime_type ?? ""}`;
  const _claimedSigs = new Set<string>();
  const _takeUnique = (files: EntityFile[]) =>
    files.filter((f) => {
      const sig = _fileSig(f);
      if (_claimedSigs.has(sig)) return false;
      _claimedSigs.add(sig);
      return true;
    });
  mergedContainers.forEach((c) => {
    const ids = new Set(c.fileIds || []);
    c.files = _takeUnique(_docFiles.filter((f) => ids.has(f.id)));
  });
  liveContainer.files = _takeUnique(
    _docFiles.filter((f) => !_mergedFileIds.has(f.id)),
  );

  // ── Импортированные прохождения (ClickUp-архив) ──
  // extra_data.participations[] — отдельный от merged_from массив: каждое прохождение
  // человека = вакансия + рекрутёр + статус + анкета (Q&A). Рисуем их теми же
  // read-only контейнерами. Отдельный ключ (не merged_from), чтобы не путать
  // консьюмеров слияния (/all-dispatches, merge-flow).
  const participationsRaw = Array.isArray(
    (card.extra_data as Record<string, unknown> | undefined)?.participations,
  )
    ? ((card.extra_data as Record<string, unknown>)
        .participations as Array<Record<string, unknown>>)
    : [];

  const participationContainers: StageContainer[] = participationsRaw.map((p, i) => ({
    origin: "merged" as const,
    // Фиктивный отрицательный ключ ниже merged_from — read-only, действий нет.
    applicationId: -(mergedContainers.length + i + 1),
    status: typeof p.status === "string" && p.status ? p.status : "reserve",
    name: null,
    // Комментарии рекрутёра/HR из импорта (parse_comments → participations[].notes):
    // родными плашками таймлайна, как у merged-контейнеров. Без этой строки заметки
    // прохождения выбрасывались бы и не показывались.
    notes: Array.isArray(p.notes) ? (p.notes as ContainerNote[]) : [],
    resumeDemos: [],
    vacancyTitle: typeof p.vacancy_title === "string" ? p.vacancy_title : null,
    addedAt: typeof p.date === "string" ? p.date : undefined,
    recruiter: typeof p.recruiter === "string" ? p.recruiter : undefined,
    anketa: Array.isArray(p.anketa)
      ? (p.anketa as Array<{ question: string; answer: string }>)
      : [],
  }));

  // Архивный импорт: живой заявки нет (liveApplicationId===0) и live-контейнер пуст
  // (нет лога/событий/вакансии), но есть участия → не показываем вырожденный live.
  const _liveEmpty =
    liveApplicationId === 0 &&
    _liveNotes.length === 0 &&
    !(liveEvents && liveEvents.length) &&
    !liveVacancyTitle;
  const _head =
    _liveEmpty && participationContainers.length > 0 ? [] : liveContainers;

  return [..._head, ...mergedContainers, ...participationContainers];
}

// ── Timeline reactions + «Действия» filter (pure) ──

/** Эмодзи-реакция на запись таймлайна (лог карточки). */
export type EntryReaction = {
  emoji: string;
  user_id: number;
  user_name?: string;
  date?: string;
};

/** Полный список фильтров «Действия» (показываются только непустые). */
export const TIMELINE_ACTION_FILTERS = [
  "Сопроводительное письмо",
  "Смена этапа подбора",
  "Комментарий",
  "Письмо кандидату",
  "Интервью",
  "Телефонный звонок",
  "Файл",
  "Оффер",
  "Отказ",
  "Оценка рекрутмента",
];

const getTimelineFilterAliases = (filter: string): string[] => {
  const aliases: Record<string, string[]> = {
    "Смена этапа подбора": ["смен", "этап", "перенес", "новый", "отказ"],
    "Письмо кандидату": ["письм", "email", "почт"],
    "Телефонный звонок": ["телефон", "звон"],
    "Сопроводительное письмо": ["сопровод"],
  };
  return [filter, ...(aliases[filter] || [])].map((value) =>
    value.toLowerCase(),
  );
};

/**
 * Матч записи таймлайна под фильтр «Действия». Комментарий и смена этапа — по
 * ТИПУ записи (kind); остальное (отказ и т.п.) — по тексту (title/body).
 */
export function matchesTimelineFilter(
  item: { title?: string; body?: string; kind?: string },
  filter: string,
): boolean {
  if (filter === "Комментарий") return item.kind === "comment";
  if (filter === "Смена этапа подбора") return item.kind === "stage";
  const aliases = getTimelineFilterAliases(filter);
  const hay = `${item.title || ""} ${item.body || ""}`.toLowerCase();
  return aliases.some((a) => hay.includes(a));
}

// ── System HR tags (авто-метки «HR») ───────────────────────────────────────

/**
 * Авто-метка «HR» — рекрутер, забравший кандидата в активную воронку. Read-only:
 * проставляется бэкендом по created_by активных заявок и хранится в
 * extra_data.system_hr_tags ОТДЕЛЬНО от ручных строковых card.tags, поэтому
 * никогда с ними не конфликтует и не удаляется вручную.
 */
export type SystemHrTag = {
  hr_id: number;
  name: string;
  /** Воронка (вакансия), в которую этот HR забрал кандидата. */
  vacancy_id?: number;
  vacancy_title?: string;
  /** 'board' — HR не из воронки, а назначенный руками на доске «Штат». */
  source?: "board";
};

/**
 * Достаёт авто-метки HR из extra_data кандидата, отбрасывая мусор (на случай
 * частично заполненного/легаси extra_data). Поля воронки (vacancy_*)
 * опциональны — у легаси-данных их нет, тогда метка показывается без воронки.
 * Порядок сохраняется как пришёл с бэкенда (там он стабилен — по hr_id, vacancy).
 */
export function readSystemHrTags(
  extraData: Record<string, unknown> | undefined | null,
): SystemHrTag[] {
  const fromFunnels = readHrTagList(extraData?.system_hr_tags);
  // HR, назначенный на доске «Штат» (extra_data.board_hr_tags): воронки у него
  // нет, поэтому метка показывается без названия — «HR: Имя». Если этот же
  // человек уже значится по воронке, второй раз не повторяем: в карточке
  // хватает одной строки на человека (просьба владельца 20.10.2026 — «добавляю
  // HR в штате, в метках он тоже должен появиться»).
  const seen = new Set(fromFunnels.map((t) => t.hr_id));
  const fromBoard = readHrTagList(extraData?.board_hr_tags)
    .filter((t) => !seen.has(t.hr_id))
    .map((t) => ({ hr_id: t.hr_id, name: t.name, source: "board" as const }));
  return [...fromFunnels, ...fromBoard];
}

/** Разбор одного массива меток HR: мусор и записи без имени отбрасываем. */
function readHrTagList(raw: unknown): SystemHrTag[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (t): t is SystemHrTag =>
        !!t &&
        typeof t === "object" &&
        typeof (t as SystemHrTag).hr_id === "number" &&
        typeof (t as SystemHrTag).name === "string" &&
        (t as SystemHrTag).name.trim().length > 0,
    )
    .map((t) => {
      const tag: SystemHrTag = { hr_id: t.hr_id, name: t.name };
      if (typeof t.vacancy_id === "number") tag.vacancy_id = t.vacancy_id;
      if (typeof t.vacancy_title === "string" && t.vacancy_title.trim()) {
        tag.vacancy_title = t.vacancy_title.trim();
      }
      return tag;
    });
}

// ── Deep-link: карточка из «сырой» сущности ──

/**
 * Собрать KanbanCard из ответа GET /entities/{id}.
 *
 * Нужна, когда кандидата НЕТ на доске: архив, статус вне колонок («Отозван»
 * скрыт), фильтр или чужой скоуп. Раньше диплинк из расширения в таком случае
 * подставлял ФИО в поиск и надеялся, что доска его найдёт; если доска не
 * находила — на экране оставалась ПРОШЛАЯ карточка, а адрес переписывался на
 * неё же (жалоба Эльвиры 18.09.2026: «перехожу по ссылке — открывается другой
 * кандидат»). Теперь карточка собирается напрямую из сущности.
 *
 * Импорт (ClickUp/CSV) кладёт location/birth_date, а шапка карточки показывает
 * city/age — маппим с фолбэком, иначе шапка пустая, хотя данные есть.
 */
// Каналы порталов и ярлыки источника — не ник человека (тот же список, что
// JUNK_TELEGRAM_USERNAMES на бэке). Расширение старых версий сохраняло
// t.me/hh_b2b со страницы hh.ru, и карточка показывала «hh_b2b» вместо ника.
const JUNK_TELEGRAM = new Set([
  "telegram", "tg", "telega", "hh", "hh_b2b", "hh_news", "hh_news_hr", "hhnews",
  "headhunter", "hhru", "vk", "vkontakte", "avito", "superjob", "habr", "linkedin",
  "email", "mail", "phone", "tel", "resume", "cv", "source", "none", "no",
  "n/a", "na", "null", "-", "—",
]);

/** Первый настоящий ник из списка (без каналов порталов). */
export function pickTelegram(list: readonly (string | null | undefined)[] | null | undefined): string | undefined {
  for (const t of list || []) {
    const v = (t || "").trim();
    if (v && !JUNK_TELEGRAM.has(v.replace(/^@/, "").toLowerCase())) return v;
  }
  return undefined;
}

export function entityToKanbanCard(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  e: any,
  opts: { archived?: boolean; calcAge?: (birth?: string) => number | null } = {},
): KanbanCard {
  const extra: Record<string, unknown> = { ...((e?.extra_data as Record<string, unknown>) || {}) };
  // CSV-импорт кладёт единственный комментарий в extra_data.comment — показываем
  // его как личную заметку, иначе карточка выглядит пустой.
  if ((!Array.isArray(extra.notes) || (extra.notes as unknown[]).length === 0) && extra.comment) {
    extra.notes = [{ text: String(extra.comment), date: e.created_at, author_name: "Импорт" }];
  }
  if (opts.archived) extra.is_archived = true;

  const age =
    (extra.age as number | string | undefined) ??
    (opts.calcAge ? opts.calcAge(extra.birth_date as string | undefined) ?? undefined : undefined);

  return {
    id: e.id,
    name: e.name,
    email: e.email || undefined,
    phone: e.phone || undefined,
    telegram_username: pickTelegram(e.telegram_usernames),
    // Полные списки: у склеенного человека контактов может быть несколько.
    phones: Array.isArray(e.phones) ? e.phones : undefined,
    emails: Array.isArray(e.emails) ? e.emails : undefined,
    telegram_usernames: Array.isArray(e.telegram_usernames) ? e.telegram_usernames : undefined,
    position: e.position || undefined,
    company: e.company || undefined,
    source: e.source || (extra.source as string) || undefined,
    created_at: e.created_at || "",
    tags: e.tags || [],
    photo_url: e.photo_url || undefined,
    city: (extra.city as string) || (extra.location as string) || undefined,
    age: age != null ? String(age) : undefined,
    salary: extra.salary != null ? String(extra.salary) : undefined,
    total_experience: extra.total_experience != null ? String(extra.total_experience) : undefined,
    is_archived: Boolean(opts.archived || e.is_archived),
    extra_data: extra,
  } as KanbanCard;
}

// ── Список «Все кандидаты»: какие карточки доски показывать ──

export type VisibleCard = { card: KanbanCard; status: string; label: string };

/**
 * Отбор карточек доски для левого списка.
 *
 * Два правила, и оба про ПОИСК: когда рекрутёр что-то ищет, ни вкладка-этап, ни
 * скоуп «Только мои» не должны резать выдачу — человек ищет конкретного человека
 * и ждёт его найти, чей бы он ни был. Раньше скоуп применялся всегда, и выходило
 * «сервер нашёл 1, а список пуст»: кандидат в базе есть, кнопка расширения его
 * видит, а поиск — нет (Эльвира, 18.09.2026).
 */
export function selectVisibleCards(
  columns: KanbanColumn[],
  opts: { activeTab: string; scope: "mine" | "all"; myId: number | null | undefined; search: string },
): VisibleCard[] {
  const searching = opts.search.trim().length > 0;
  // «Мой» — по номеру аккаунта (кто добавил), а не по имени: два рекрутёра с
  // одинаковым именем видели бы кандидатов друг друга, а переименование в
  // профиле прятало бы своих.
  const scopeMine = opts.scope === "mine" && opts.myId != null && !searching;

  const items: VisibleCard[] = [];
  for (const col of columns) {
    if (!(searching || opts.activeTab === "all" || col.status === opts.activeTab)) continue;
    for (const c of col.cards || []) {
      if (scopeMine && c.recruiter_id !== opts.myId) continue;
      items.push({ card: c, status: col.status, label: col.label });
    }
  }
  if (searching || opts.activeTab === "all") {
    // Порядок задаёт сервер (rank): во «Все» — по дате ДОБАВЛЕНИЯ, свежие
    // сверху (владелец, 21.10.2026), в поиске — по совпадению (раньше тут
    // пересортировывали по дате, и лучшее совпадение уезжало вниз). Без rank —
    // по дате добавления.
    return items.sort((a, b) => {
      const ra = a.card.rank;
      const rb = b.card.rank;
      if (ra != null && rb != null && ra !== rb) return ra - rb;
      return cardOrderTime(b.card) - cardOrderTime(a.card);
    });
  }
  return items;
}

/** Время, по которому выстраивается список: добавление карточки (владелец,
 *  21.10.2026: «не по дате изменения, а по дате добавления»). Подпись в строке
 *  при этом — дата перевода на текущий статус (CandidateListRow). */
export function cardOrderTime(card: Pick<KanbanCard, "created_at">): number {
  const raw = card.created_at;
  const t = raw ? new Date(raw).getTime() : NaN;
  return Number.isNaN(t) ? 0 : t;
}

/** Вставить карточку в колонку на её место по дате добавления (колонки с
 *  сервера идут свежими сверху). Нужно после смены этапа на месте: раньше
 *  переведённый вставал первым, а после обновления доски уезжал на своё место. */
export function insertByCreatedAt<T extends Pick<KanbanCard, "created_at">>(cards: T[], card: T): T[] {
  const t = cardOrderTime(card);
  const at = cards.findIndex((c) => cardOrderTime(c) < t);
  return at < 0 ? [...cards, card] : [...cards.slice(0, at), card, ...cards.slice(at)];
}

/** Сколько карточек доски прячет скоуп «Только мои» — для объяснения пустого списка. */
export function countHiddenByScope(
  columns: KanbanColumn[],
  opts: { scope: "mine" | "all"; myId: number | null | undefined },
): number {
  if (opts.scope !== "mine" || opts.myId == null) return 0;
  let hidden = 0;
  for (const col of columns) {
    for (const c of col.cards || []) {
      if (c.recruiter_id !== opts.myId) hidden += 1;
    }
  }
  return hidden;
}

// ================================================================
// Настройки списка «Все кандидаты» (окно с ползунками справа сверху)
// ================================================================

export type CandidateListFields = {
  name: boolean;
  desiredPosition: boolean;
  desiredSalary: boolean;
  age: boolean;
  experience: boolean;
  lastPosition: boolean;
  lastCompany: boolean;
  source: boolean;
  vacanciesCount: boolean;
  tags: boolean;
};
export type CandidateListSettings = {
  scope: "mine" | "all";
  fields: CandidateListFields;
};

export const CANDIDATE_LIST_SETTINGS_KEY = "hf.candidateListSettings.v2";
const LEGACY_CANDIDATE_LIST_SETTINGS_KEY = "hf.candidateListSettings";
export const DEFAULT_CANDIDATE_LIST_SETTINGS: CandidateListSettings = {
  scope: "all",
  fields: {
    name: true,
    desiredPosition: false,
    desiredSalary: false,
    age: false,
    experience: false,
    lastPosition: true,
    lastCompany: true,
    source: false,
    vacanciesCount: false,
    tags: false,
  },
};

/**
 * Поля списка запоминаются (localStorage), а фильтр «Только по моим вакансиям»
 * — НИКОГДА. «Все кандидаты» по умолчанию показывают всех: выбор «только мои»
 * живёт, пока открыта страница (переключение этапов его не сбрасывает), а
 * обновление, уход в воронку, новая вкладка или браузер — снова «все».
 * Раньше scope хранился в браузере: рекрутёр однажды выбирал «мои», и потом
 * вкладка «Практика 9» показывала ему 4 карточки без объяснения (прод 2026-09-21).
 */
export function loadCandidateListSettings(): CandidateListSettings {
  try {
    const raw =
      localStorage.getItem(CANDIDATE_LIST_SETTINGS_KEY) ??
      localStorage.getItem(LEGACY_CANDIDATE_LIST_SETTINGS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        scope: "all",
        fields: { ...DEFAULT_CANDIDATE_LIST_SETTINGS.fields, ...(parsed?.fields || {}) },
      };
    }
  } catch {
    /* битый JSON / недоступный storage — дефолт */
  }
  return DEFAULT_CANDIDATE_LIST_SETTINGS;
}

/** Сохраняет ТОЛЬКО поля списка; scope в браузер не пишется. */
export function saveCandidateListSettings(settings: CandidateListSettings): void {
  try {
    localStorage.setItem(
      CANDIDATE_LIST_SETTINGS_KEY,
      JSON.stringify({ fields: settings.fields }),
    );
  } catch {
    /* ignore */
  }
}

// ================================================================
// «Практикуются у»: счётчик по тегам-наставникам на вкладке «Практика»
// ================================================================

/** Ключ этапа «Практика» на доске «Все кандидаты» (подпись орг может сменить). */
export const PRACTICE_STATUS = "probation";

/** Теги у имени, по которым считается, у кого практикуется кандидат (решение
 * владельца 21.09.2026). Остальные теги только отображаются. */
export const PRACTICE_MENTOR_TAGS = ["Егор", "Влад"] as const;

/** Значение фильтра: имя наставника или «без тега» (нет ни одного из них). */
export type MentorFilter = (typeof PRACTICE_MENTOR_TAGS)[number] | "none";

function mentorsOf(card: KanbanCard): string[] {
  const names = (card.headline_tags || []).map((t) => (t.name || "").trim().toLowerCase());
  return PRACTICE_MENTOR_TAGS.filter((m) => names.includes(m.toLowerCase()));
}

export function cardMatchesMentor(card: KanbanCard, filter: MentorFilter): boolean {
  const mentors = mentorsOf(card);
  return filter === "none" ? mentors.length === 0 : mentors.includes(filter);
}

/** Сколько карточек у каждого наставника и сколько ни у кого. Кандидат с
 * обоими тегами считается у обоих. */
export function countPracticeMentors(cards: KanbanCard[]): { key: MentorFilter; count: number }[] {
  const out: { key: MentorFilter; count: number }[] = PRACTICE_MENTOR_TAGS.map((m) => ({
    key: m,
    count: cards.filter((c) => cardMatchesMentor(c, m)).length,
  }));
  out.push({ key: "none", count: cards.filter((c) => cardMatchesMentor(c, "none")).length });
  return out;
}
