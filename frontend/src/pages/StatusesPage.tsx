import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Search, Loader2, Plus, Pencil, Check, Copy, Download, X, MoreHorizontal, Trash2,
  Settings, Calendar, ChevronDownSquare, Type, User as UserIcon, GripVertical, Hash, CheckSquare,
  ChevronRight, ChevronDown, Paperclip, Upload, SlidersHorizontal,
} from "lucide-react";
import clsx from "clsx";
import * as XLSX from "xlsx";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  getBoardRows, updateBoardRow, addBoardPlacement, removeBoardPlacement,
  getBoardDepartments, createBoardDepartment, updateBoardDepartment, deleteBoardDepartment,
  getCatalog, addCatalogItem, renameCatalogItem, deleteCatalogItem,
  type CatalogItem, type CatalogKind,
  type BoardDepartment, type BoardRow, type BoardRowUpdate, type BoardTeamStint,
} from "@/services/api/staffBoard";
import { uploadEntityFile, deleteEntityFile, downloadEntityFile } from "@/services/api/entities";
import {
  getBoardView, saveBoardView, EMPTY_BOARD_VIEW, type BoardView,
  getCustomFields, createCustomField, updateCustomField, deleteCustomField,
  getDropdownMeta, saveDropdownMeta, type DropdownMeta,
  type CustomField, type CustomFieldType,
} from "@/services/api/staffBoard";
import { getOrgMembers } from "@/services/api/accessHub";
import {
  addTagToEntity, archiveTag, createTag, getTags, removeTagFromEntity, updateTag, type Tag,
} from "@/services/api/tags";
import { useUrlTab } from "@/hooks/useUrlTab";
import { useAuthStore } from "@/stores/authStore";
import { STATUS_LABELS } from "@/types";

/**
 * Страница «Статусы» — доска жизненного цикла сотрудника внутри направления.
 *
 * Слева — отделы оргструктуры (бывшие «направления»; «+ Отдел» заводит новый).
 * Справа — таблица, сгруппированная в сворачиваемые секции по статусам
 * ПРАКТИКА / ПЕРЕВЁЛСЯ / УВОЛЕН / УВОЛИЛСЯ. Все колонки редактируются инлайн,
 * у каждой — свой фильтр. Вехи 1/3/12 мес считаются от «выход в отдел»
 * автоматически (авто-значение показано курсивом), но их можно перебить.
 *
 * Оформление — семейство .hf-statuses-* в index.css (HR-дизайн-система).
 */

/** Порядок групп повторяет доску ClickUp: там сверху «Перевёлся», а
 *  «Практика» замыкает список. */
const STATUSES = [
  { key: "transferred", label: "ПЕРЕВЁЛСЯ",          members: ["transferred"] },
  // «Уволен» и «Уволился» — две секции (владелец, 10.11.2026). С 06.10 по
  // 10.11.2026 они были одной группой «Уволен / Уволился».
  // В «Уволен» — ещё «Отказ» и «Отозван» у тех, кто уже был в отделе: для доски
  // это уход, а не работа воронки (владелец, 06.10.2026: «поменял статус на
  // отозван — он просто исчез из статусов, это неверно»). В «Уволился» таких
  // людей HR переносит руками (решение 10.11.2026). Кандидата без отдела с
  // такими статусами сервер на доску не отдаёт вовсе.
  { key: "dismissed",   label: "УВОЛЕН",
    members: ["dismissed", "rejected", "withdrawn"] },
  { key: "quit",        label: "УВОЛИЛСЯ",           members: ["quit"] },
  { key: "probation",   label: "ПРАКТИКА",           members: ["probation"] },
  // «Оффер принят» приходит с этапа воронки hired — своего статуса доска не
  // заводит. «Оффер выслан» и прочие этапы подбора здесь не показываются:
  // доска — про своих (владелец, 06.10.2026: «нам нужны только те, кто на
  // практике, кто принял оффер, кто перешёл в штат и кого уволили или ушёл»).
  { key: "hired",       label: "ОФФЕР ПРИНЯТ",       members: ["hired"] },
] as const;

/** В какую группу попадает статус строки. */
const groupOf = (status: string) =>
  STATUSES.find((g) => (g.members as readonly string[]).includes(status))?.key ?? status;

const UNASSIGNED = "__none__";

type FilterKey =
  | `cf:${string}`
  | "name" | "assignee" | "sourcer" | "position" | "department" | "telegram"
  | "practice_start_date" | "manager" | "department_start_date"
  | "dept_done" | "w2" | "w2_done" | "m1" | "m1_done"
  | "m3" | "m3_done" | "y1" | "y1_done" | "dismissal_date" | "rejection_reason";

/** Ширины колонок с датами рассчитаны так, чтобы «дд.мм.гггг» помещалась
 *  целиком: в узких колонках дата обрезалась и год было не прочитать
 *  (Мария, 28.09.2026).
 *  Порядок и состав повторяют доску «Сотрудники» в ClickUp: после каждой
 *  вехи идёт колонка-отметка «пройдено» (в ClickUp она называлась так же,
 *  но в скобках). «2 недели» — наша дополнительная веха, в ClickUp её нет. */
/** Ширина в px задана у каждой колонки: без неё 19 колонок растягивались как
 *  попало, длинная должность раздувала свою, а даты сжимались до переноса.
 *  Суммарно таблица шире экрана — прокрутка есть, но имя закреплено слева. */
const COLUMNS: { key: FilterKey | "offer"; label: string; filter: boolean; narrow?: boolean; width: number }[] = [
  { key: "name",                  label: "ФИО",               filter: true, width: 250 },
  { key: "assignee",              label: "HR",                filter: true, width: 130 },
  { key: "sourcer",               label: "Сорсер",            filter: true, width: 150 },
  { key: "position",              label: "Должность",         filter: true, width: 160 },
  { key: "department",            label: "Отдел",             filter: true, width: 190 },
  { key: "telegram",              label: "Telegram",          filter: true, width: 140 },
  { key: "practice_start_date",   label: "Выход на практику", filter: true, width: 120 },
  { key: "manager",               label: "Рук-ль",            filter: true, width: 110 },
  { key: "offer",                 label: "Оффер",             filter: false, narrow: true, width: 64 },
  { key: "department_start_date", label: "Выход в отдел",     filter: true, width: 120 },
  { key: "dept_done",             label: "✓",                 filter: true, narrow: true, width: 124 },
  { key: "w2",                    label: "2 недели",          filter: true, width: 116 },
  { key: "w2_done",               label: "✓",                 filter: true, narrow: true, width: 124 },
  { key: "m1",                    label: "1 мес",             filter: true, width: 116 },
  { key: "m1_done",               label: "✓",                 filter: true, narrow: true, width: 124 },
  { key: "m3",                    label: "3 мес",             filter: true, width: 116 },
  { key: "m3_done",               label: "✓",                 filter: true, narrow: true, width: 124 },
  { key: "y1",                    label: "1 год",             filter: true, width: 116 },
  { key: "y1_done",               label: "✓",                 filter: true, narrow: true, width: 124 },
  { key: "dismissal_date",        label: "Дата увольнения",   filter: true, width: 124 },
  // То же поле, что «Причина отказа» в карточке кандидата: заполняется из
  // комментария при переводе в «Отказ», правится и здесь (владелец,
  // 10.11.2026). Колонку «Сумма» в тот же день убрали с доски целиком.
  { key: "rejection_reason",      label: "Причина отказа",    filter: true, width: 220 },
];

type Column = (typeof COLUMNS)[number];

/** Свои поля организации (11.11.2026) — колонки «cf:<id>» после встроенных.
 *  Реестр на уровне модуля, как FIELD_LABELS: подписи, значения ячеек и
 *  фильтры — чистые функции, страница обновляет реестр при загрузке. */
let CUSTOM_FIELDS: CustomField[] = [];
export const setCustomFields = (list: CustomField[]) => { CUSTOM_FIELDS = list; };
export const customFieldOf = (key: string) =>
  key.startsWith("cf:") ? CUSTOM_FIELDS.find((f) => `cf:${f.id}` === key) : undefined;
const CUSTOM_WIDTH: Record<CustomFieldType, number> = { text: 180, number: 110, date: 120, select: 150, checkbox: 90 };

/** Цвета и порядок пунктов выпадающих списков — общие (11.11.2026). Реестр
 *  на уровне модуля: ячейки читают его напрямую, страница держит копию в
 *  стейте (для перерисовки) и регистрирует функцию сохранения. */
let DROPDOWN_META: DropdownMeta = {};
type MetaPatch = { order?: string[]; colors?: Record<string, string | null> };
let metaSaver: (kind: string, patch: MetaPatch) => Promise<void> = async () => {};
// Сохранения идут строго по очереди: и порядок, и цвета, и переименование
// пишут в одни настройки организации, и два запроса разом затирали друг друга
// (перетащил и сразу перекрасил — порядок пропадал; 11.11.2026).
let metaQueue: Promise<void> = Promise.resolve();
const saveMeta = (kind: string, patch: MetaPatch): Promise<void> => {
  metaQueue = metaQueue.then(() => metaSaver(kind, patch)).catch(() => {});
  return metaQueue;
};
export const setDropdownMetaRegistry = (m: DropdownMeta) => { DROPDOWN_META = m; };
const setMetaSaver = (fn: typeof metaSaver) => { metaSaver = fn; };
let metaReloader: () => Promise<void> = async () => {};
/** У должностей, «Рук-ль», отметок и пунктов своих полей ключ — само
 *  название. После переименования сервер переносит цвет и место в порядке на
 *  новое имя; перечитываем, иначе на экране пункт терял цвет и уезжал в конец
 *  до F5 (11.11.2026). */
const reloadMetaAfterRename = () => {
  metaQueue = metaQueue.then(() => metaReloader()).catch(() => {});
  return metaQueue;
};
export const metaColor = (kind: string, key: string): string | undefined => DROPDOWN_META[kind]?.colors?.[key];

/** Пункты в порядке, который выставили перетаскиванием; новые — в конце, в
 *  своём исходном порядке. */
export function orderByMeta<T>(kind: string, items: T[], keyOf: (t: T) => string): T[] {
  const idx = new Map((DROPDOWN_META[kind]?.order ?? []).map((k, i) => [k, i]));
  return items
    .map((t, i) => ({ t, i }))
    .sort((a, b) => (idx.get(keyOf(a.t)) ?? 1e6 + a.i) - (idx.get(keyOf(b.t)) ?? 1e6 + b.i))
    .map((x) => x.t);
}

/** Обработчики «Цвет» и перетаскивания для окна-списка. Перетаскивание
 *  меняет порядок внутри группы; остальное в сохранённом порядке остаётся. */
const metaHandlers = (kind: string) => ({
  onRecolor: (key: string, color: string | null) => saveMeta(kind, { colors: { [key]: color } }),
  onReorder: (_group: string, keys: string[]) => {
    const rest = (DROPDOWN_META[kind]?.order ?? []).filter((k) => !keys.includes(k));
    return saveMeta(kind, { order: [...keys, ...rest] });
  },
});

/** Пилюля значения: свой цвет пункта, иначе цвет по названию. */
const valuePill = (kind: string, key: string, label: string): React.CSSProperties => {
  const c = metaColor(kind, key);
  if (c) return colorPill(c);
  const hue = pillHue(label);
  return { background: `hsl(${hue} 70% 94%)`, color: `hsl(${hue} 55% 32%)`, borderColor: `hsl(${hue} 60% 84%)` };
};

/** Все колонки: встроенные и свои. */
export function allColumns(): Column[] {
  return [
    ...COLUMNS,
    ...CUSTOM_FIELDS.map((f) => ({
      key: `cf:${f.id}` as FilterKey, label: f.name, filter: true, width: CUSTOM_WIDTH[f.type],
    })),
  ];
}

/** Колонки, которые можно спрятать: все, кроме «ФИО» — без имени строка
 *  бессмысленна (просьба Марии 08.10.2026 про лист-вью по столбцам). */
const hideableColumns = () => allColumns().filter((c) => c.key !== "name");

/** Колонки по общему виду (11.11.2026): «ФИО» первым, дальше в порядке,
 *  который выставили перетаскиванием (новые колонки — в конце), с общими
 *  ширинами; скрытые выброшены, если не просили всех. */
export function arrangeColumns(
  view: Partial<Pick<BoardView, "hidden" | "order" | "widths">>,
  withHidden = false,
): typeof COLUMNS {
  const cols = allColumns();
  const known = new Set(cols.map((c) => c.key as string));
  const order = (view.order ?? []).filter((k) => k !== "name" && known.has(k));
  const rest = cols.map((c) => c.key as string).filter((k) => k !== "name" && !order.includes(k));
  const hidden = view.hidden ?? [];
  return ["name", ...order, ...rest]
    .filter((k) => withHidden || k === "name" || !hidden.includes(k))
    .map((k) => {
      const c = cols.find((x) => x.key === k)!;
      const w = view.widths?.[k];
      return w ? { ...c, width: w } : c;
    });
}

/** Колонки из выбора (выгрузка): «ФИО» всегда, порядок — как у base. */
export function pickColumns(chosen?: string[] | null, base: Column[] = allColumns()): Column[] {
  if (!chosen?.length) return base;
  return base.filter((c) => c.key === "name" || chosen.includes(c.key));
}

/** Подписи для списка «Фильтры»: там «✓» ничего не сказало бы. */
const FILTER_LABELS: Partial<Record<FilterKey, string>> = {
  dept_done: "Выход в отдел ✓",
  w2_done: "2 недели ✓",
  m1_done: "1 мес ✓",
  m3_done: "3 мес ✓",
  y1_done: "1 год ✓",
};

/** Свои названия полей — карандаш в «Полях» (общий вид, 11.11.2026: «тоже
 *  добавьте, чтобы мы сами могли гибко менять»). Карта на уровне модуля:
 *  подписи читают и чистые функции (фразы фильтров, выгрузка), страница
 *  обновляет её при загрузке вида и при каждой правке. */
let FIELD_LABELS: Record<string, string> = {};
export const setFieldLabels = (map: Record<string, string>) => { FIELD_LABELS = { ...map }; };

/** Название поля в списках, фильтрах и выгрузке (у отметок — с «✓»). */
export const fieldLabel = (key: string) =>
  FIELD_LABELS[key] || customFieldOf(key)?.name || FILTER_LABELS[key as FilterKey]
  || COLUMNS.find((c) => c.key === key)?.label || key;

/** Подпись в шапке таблицы: у отметок по умолчанию короткая «✓». */
const headerLabel = (c: { key: string; label: string }) =>
  FIELD_LABELS[c.key] || customFieldOf(c.key)?.name || c.label;

/** Имя колонки для фразы в панели и для чипов. */
const filterLabel = (key: FilterKey) => fieldLabel(key);

/** Дата в ячейке таблицы — коротко, как в ClickUp: «9/11/26» (день/месяц/год).
 *  В фильтрах, чипах и выгрузке остаётся полная «09.11.2026». */
const fmtShort = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : `${d.getDate()}/${d.getMonth() + 1}/${String(d.getFullYear()).slice(2)}`;
};

const fmt = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString("ru-RU");
};

/** Колонки, по которым можно фильтровать. */
const filterableColumns = () => allColumns().filter((c) => c.filter) as { key: FilterKey; label: string }[];

// v3 (11.11.2026): снова правила «поле → условие → значение», как в ClickUp
// (клиент: «открывается окно, в нём выбираешь поле, потом его значение…
// кнопка AND/OR»). v2 (24.09–11.11) — галочки по колонкам; читаем его один
// раз и переводим, чтобы сохранённый отбор у людей не слетел.
const FILTERS_STORAGE_KEY = "hf-statuses-filters-v3";
const FILTERS_STORAGE_KEY_V2 = "hf-statuses-filters-v2";

/** Колонки, по которым можно сортировать кликом по заголовку: даты выходов.
 *  Мария смотрит, кто вышел последним, — без сортировки приходилось искать
 *  глазами (встреча 23.09.2026). */
type SortKey = "practice_start_date" | "department_start_date" | "dismissal_date";
const SORTABLE: SortKey[] = ["practice_start_date", "department_start_date", "dismissal_date"];
type SortDir = "asc" | "desc";

/** Колонки с датами: у них «с … по …» вместо выбора значений.
 *  «Выгрузить всех, кто вышел в отдел в сентябре» иначе невозможно. */
const DATE_KEYS: FilterKey[] = [
  "practice_start_date", "department_start_date", "w2", "m1", "m3", "y1", "dismissal_date",
];
const isDateKey = (k: FilterKey) => DATE_KEYS.includes(k) || customFieldOf(k)?.type === "date";

/** Колонки-галочки: у них всего два варианта. */
const DONE_KEYS: FilterKey[] = ["dept_done", "w2_done", "m1_done", "m3_done", "y1_done"];
const isDoneKey = (k: FilterKey) => DONE_KEYS.includes(k);

/** Подпись значения: у отметок вместо «✓» — «Отмечено». */
const valueLabel = (key: FilterKey, v: string) =>
  isDoneKey(key) ? (v === "✓" ? "Отмечено" : v) : v;

/** Текстовые поля: у них «содержит», а не выбор из списка. */
const TEXT_KEYS: FilterKey[] = ["name", "telegram", "rejection_reason"];

/** Условие фильтра — как в ClickUp: «является / не является / пусто / не
 *  пусто», у дат — «в периоде», у текста — «содержит». */
export type FilterOp = "is" | "is_not" | "contains" | "between" | "empty" | "not_empty";

export const OP_LABELS: Record<FilterOp, string> = {
  is: "является",
  is_not: "не является",
  contains: "содержит",
  between: "в периоде",
  empty: "пусто",
  not_empty: "не пусто",
};

/** Какие условия есть у поля. */
export function opsFor(key: FilterKey): FilterOp[] {
  if (isDateKey(key)) return ["between", "empty", "not_empty"];
  const cf = customFieldOf(key);
  if (cf?.type === "checkbox") return ["not_empty", "empty"];
  if (TEXT_KEYS.includes(key) || cf?.type === "text") return ["contains", "is", "empty", "not_empty"];
  return ["is", "is_not", "empty", "not_empty"];
}

/** Одна строка фильтра. Незаполненная (поле не выбрано, значения нет) ничего
 *  не отбирает — как в ClickUp, где пустая строка просто висит в окне. */
export interface FilterRule {
  id: string;
  key: FilterKey | "";
  op: FilterOp;
  values: string[];
  from?: string;
  to?: string;
  text?: string;
}

/** Фильтры доски: строки-правила и одна связка между ними. По умолчанию —
 *  «ИЛИ» (Мария, 26.10.2026: «нужно, чтобы всегда было ИЛИ»: доску
 *  фильтруют, чтобы массово отобрать людей — «из SEO или из Push»). */
export interface BoardFilters {
  join: "and" | "or";
  rules: FilterRule[];
}

export const EMPTY_FILTERS: BoardFilters = { join: "or", rules: [] };

let ruleSeq = 0;
export const newRule = (key: FilterKey | "" = ""): FilterRule => ({
  id: `r${Date.now().toString(36)}${(ruleSeq++).toString(36)}`,
  key,
  op: key ? opsFor(key)[0] : "is",
  values: [],
});

/** Строка заполнена настолько, что уже отбирает. */
export function ruleComplete(r: FilterRule): boolean {
  if (!r.key) return false;
  if (r.op === "empty" || r.op === "not_empty") return true;
  if (r.op === "between") return !!(r.from || r.to);
  if (r.op === "contains") return !!r.text?.trim();
  return r.values.length > 0;
}

/** Значения ячейки для сравнения: у HR и сорсеров — каждый человек отдельно,
 *  у остальных — текст ячейки. Пустая ячейка — пустой список. */
export function cellValues(row: BoardRow, key: FilterKey): string[] {
  if (key === "assignee") return rowAssignees(row).map((a) => a.name || "").filter(Boolean);
  if (key === "sourcer") return (row.sourcers ?? []).map((t) => t.name).filter(Boolean);
  const v = cellText(row, key).trim();
  return isBlank(v) ? [] : [v];
}

function ruleMatches(row: BoardRow, r: FilterRule): boolean {
  const key = r.key as FilterKey;
  if (isDateKey(key)) {
    // Сравниваем «сырую» дату (ГГГГ-ММ-ДД), а не видимую «дд.мм.гггг».
    const iso = rawDate(row, key);
    if (r.op === "empty") return !iso;
    if (r.op === "not_empty") return !!iso;
    return !!iso && (!r.from || iso >= r.from) && (!r.to || iso <= r.to);
  }
  const vals = cellValues(row, key);
  switch (r.op) {
    case "empty": return vals.length === 0;
    case "not_empty": return vals.length > 0;
    case "contains": {
      const needle = (r.text || "").trim().toLowerCase();
      return vals.some((v) => v.toLowerCase().includes(needle));
    }
    case "is_not": return !vals.some((v) => r.values.includes(v));
    default: return vals.some((v) => r.values.includes(v));
  }
}

/** Проходит ли строка. Учитываются только заполненные правила; их нет —
 *  проходит всё. «И» — все правила, «ИЛИ» — хотя бы одно. Значения внутри
 *  одного правила всегда по «или»: «Отдел является SEO, Push». */
export function rowMatchesFilters(row: BoardRow, filters: BoardFilters): boolean {
  const rules = filters.rules.filter(ruleComplete);
  if (!rules.length) return true;
  return filters.join === "and"
    ? rules.every((r) => ruleMatches(row, r))
    : rules.some((r) => ruleMatches(row, r));
}

/** Правило словами — для чипа над таблицей. */
export function ruleText(r: FilterRule): string {
  const key = r.key as FilterKey;
  const name = filterLabel(key);
  if (r.op === "empty" || r.op === "not_empty") return `${name} ${OP_LABELS[r.op]}`;
  if (r.op === "between") {
    const when = [r.from ? `с ${fmt(r.from)}` : "", r.to ? `по ${fmt(r.to)}` : ""].filter(Boolean).join(" ");
    return `${name}: ${when}`;
  }
  if (r.op === "contains") return `${name} содержит «${(r.text || "").trim()}»`;
  const vals = r.values.map((v) => valueLabel(key, v)).join(", ");
  return r.op === "is_not" ? `${name} — не ${vals}` : `${name}: ${vals}`;
}

/** Фильтр словами целиком. */
export function describeFilters(filters: BoardFilters): string {
  const parts = filters.rules.filter(ruleComplete).map(ruleText);
  if (!parts.length) return "Ничего не выбрано — показываем всех.";
  return `Показываем: ${parts.join(filters.join === "and" ? " и " : " или ")}.`;
}

/** Сохранённый в браузере фильтр → текущий формат.
 *
 *  v3 читаем как есть. v2 (галочки по колонкам, 24.09–11.11.2026): выбранные
 *  значения — правило «является», «Пусто» — «пусто», даты — «в периоде».
 *  Связка: если все условия были обязательными («и») — «И», иначе «ИЛИ».
 */
export function readSavedFilters(raw: unknown): BoardFilters {
  if (!raw || typeof raw !== "object") return EMPTY_FILTERS;
  const o = raw as Record<string, any>;
  const known = new Set(filterableColumns().map((c) => c.key as string));
  if (Array.isArray(o.rules)) {
    const rules: FilterRule[] = o.rules
      .filter((r: any) => r && typeof r === "object" && (!r.key || known.has(r.key)))
      .map((r: any) => ({
        id: String(r.id || newRule().id),
        key: r.key || "",
        op: (Object.keys(OP_LABELS) as FilterOp[]).includes(r.op) ? r.op : "is",
        values: Array.isArray(r.values) ? r.values.map(String) : [],
        from: r.from || undefined,
        to: r.to || undefined,
        text: r.text || undefined,
      }));
    return { join: o.join === "and" ? "and" : "or", rules };
  }
  // v2
  const OLD_BLANK = "\u0000blank";
  const rules: FilterRule[] = [];
  for (const [key, chosen] of Object.entries(o.values || {}) as [FilterKey, string[]][]) {
    if (!known.has(key) || !Array.isArray(chosen) || !chosen.length) continue;
    const vals = chosen.filter((v) => v !== OLD_BLANK);
    if (TEXT_KEYS.includes(key)) {
      if (vals.length) rules.push({ ...newRule(key), op: "is", values: vals });
      else rules.push({ ...newRule(key), op: "empty" });
    } else if (vals.length) {
      rules.push({ ...newRule(key), op: "is", values: vals });
    } else {
      rules.push({ ...newRule(key), op: "empty" });
    }
  }
  for (const [key, range] of Object.entries(o.dates || {}) as [FilterKey, { from: string; to: string }][]) {
    if (!known.has(key) || !range || (!range.from && !range.to)) continue;
    rules.push({ ...newRule(key), op: "between", from: range.from || undefined, to: range.to || undefined });
  }
  const andKeys: string[] = Array.isArray(o.andKeys) ? o.andKeys : [];
  const allAnd = o.mode === "all" || (rules.length > 0 && rules.every((r) => andKeys.includes(r.key)));
  return { join: allAnd && rules.length > 1 ? "and" : "or", rules };
}

/** Границы месяца в формате ГГГГ-ММ-ДД. */
function monthRange(year: number, month: number): { from: string; to: string } {
  const pad = (n: number) => String(n).padStart(2, "0");
  const last = new Date(year, month + 1, 0).getDate();
  return { from: `${year}-${pad(month + 1)}-01`, to: `${year}-${pad(month + 1)}-${pad(last)}` };
}

/** Последние 12 месяцев для выбора одним кликом: «Сентябрь 2026».
 *  Мария набирала «01.09.2026 — 01.10.2026» руками и промахивалась в цифрах
 *  (встреча 29.09.2026), а выгрузка за месяц нужна каждый месяц. */
function recentMonths(now = new Date()): { label: string; from: string; to: string }[] {
  const out: { label: string; from: string; to: string }[] = [];
  for (let i = 0; i < 12; i += 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const { from, to } = monthRange(d.getFullYear(), d.getMonth());
    const name = d.toLocaleDateString("ru-RU", { month: "long" });
    out.push({ label: `${name[0].toUpperCase()}${name.slice(1)} ${d.getFullYear()}`, from, to });
  }
  return out;
}

/** Вехи стажа для выгрузки: «месяц работы», «испытательный срок», «год». */
const MILESTONES = [
  { key: "m1", label: "1 месяц работы", sheet: "1 месяц" },
  { key: "m3", label: "Испытательный срок (3 мес)", sheet: "Испытательный срок" },
  { key: "y1", label: "Год работы", sheet: "Год работы" },
] as const;
type MilestoneKey = (typeof MILESTONES)[number]["key"];

export type ExportPlan = { months: string[]; marks: MilestoneKey[] };

/** Что класть в файл: секции и колонки — тот же выбор, что в «Виде»
 *  (владелец, 11.11.2026: «такой же выбор сделаем для выгрузки»). */
export type ExportPick = { sections: string[]; columns: string[] };

/** Колонки файла: «Сотрудник» всегда, порядок табличный. Пусто — все.
 *  «Оффер» в файле — имя приложенного файла. */
export function exportColumns(chosen?: string[] | null, base: Column[] = allColumns()): Column[] {
  return pickColumns(chosen, base);
}

/** Строки выбранных секций, в порядке секций доски. Пусто — все секции. */
export function rowsOfSections(rows: BoardRow[], sections?: string[] | null): BoardRow[] {
  return STATUSES
    .filter((st) => !sections?.length || sections.includes(st.key))
    .flatMap((st) => rows.filter((r) => (st.members as readonly string[]).includes(r.status)));
}

/** Какие листы попадут в книгу и кто в каждом.
 *
 *  Ничего не отмечено — один лист с тем, что на экране (так кнопка работала
 *  раньше). Иначе лист на каждый выбранный месяц — по дате ВЫХОДА В ОТДЕЛ — и
 *  лист на каждую веху стажа: «выгрузка за сентябрь, за октябрь и за декабрь…
 *  как месяц работы сотрудника, как закрытие испытательного срока и как год
 *  работы» (Мария, 07.10.2026). Вехи считаются внутри выбранных месяцев, а
 *  если месяцы не отмечены — за всё время.
 */
export function buildExportSheets(
  rows: BoardRow[],
  months: { label: string; from: string; to: string }[],
  plan?: ExportPlan,
): { title: string; items: BoardRow[] }[] {
  const inRange = (iso: string | null | undefined, from: string, to: string) =>
    !!iso && iso.slice(0, 10) >= from && iso.slice(0, 10) <= to;

  const picked = plan ? months.filter((m) => plan.months.includes(m.label)) : [];
  const marks = plan?.marks ?? [];
  if (!picked.length && !marks.length) return [{ title: "Статусы", items: rows }];

  const sheets: { title: string; items: BoardRow[] }[] = [];
  for (const m of picked) {
    sheets.push({
      title: m.label,
      items: rows.filter((r) => inRange(r.department_start_date, m.from, m.to)),
    });
  }
  // Месяцы идут от свежего к старому, поэтому границы берём с краёв списка.
  const from = picked.length ? picked[picked.length - 1].from : "0000-01-01";
  const to = picked.length ? picked[0].to : "9999-12-31";
  for (const key of marks) {
    const mark = MILESTONES.find((x) => x.key === key)!;
    sheets.push({
      title: mark.sheet,
      items: rows.filter((r) => inRange(r[mark.key] as string | null, from, to)),
    });
  }
  return sheets;
}

const countActive = (f: BoardFilters) => f.rules.filter(ruleComplete).length;

/** Пустая ячейка рисуется как «—», поэтому прочерк тоже считаем пустотой. */
const isBlank = (v: string) => !v.trim() || v.trim() === "—";

const cellText = (r: BoardRow, key: FilterKey): string => {
  switch (key) {
    case "name": return r.name || "";
    case "assignee": return rowAssignees(r).map((a) => a.name || "").filter(Boolean).join(", ");
    case "sourcer": return (r.sourcers ?? []).map((t) => t.name).filter(Boolean).join(", ");
    case "position": return r.position || "";
    case "department": return r.department_name || "";
    case "telegram": return r.telegram || "";
    case "rejection_reason": return r.rejection_reason || "";
    case "manager": return r.manager || "";
    // Отметки — «заполнено» значит «отмечено», чтобы фильтр по колонке
    // отвечал на вопрос «у кого веха пройдена».
    case "dept_done": return r.dept_done || "";
    case "w2_done": return r.w2_done || "";
    case "m1_done": return r.m1_done || "";
    case "m3_done": return r.m3_done || "";
    case "y1_done": return r.y1_done || "";
    default: {
      const cf = customFieldOf(key);
      if (cf) {
        const v = r.custom?.[cf.id];
        if (v === undefined || v === null || v === "") return "";
        if (cf.type === "checkbox") return v ? "✓" : "";
        if (cf.type === "date") return fmt(String(v));
        if (cf.type === "number") return Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 4 });
        return String(v);
      }
      return fmt(r[key as keyof BoardRow] as string | null);
    }
  }
};

/** Дата ячейки как ГГГГ-ММ-ДД — для фильтра «в периоде». */
const rawDate = (r: BoardRow, key: FilterKey): string => {
  const cf = customFieldOf(key);
  const v = cf ? r.custom?.[cf.id] : r[key as keyof BoardRow];
  return typeof v === "string" ? v.slice(0, 10) : "";
};

/** Ключ строки доски: назначение, а у тех, кто ещё не в отделе, — человек. */
const rowKey = (r: BoardRow) =>
  r.placement_id != null ? `p${r.placement_id}` : `e${r.entity_id}`;

export default function StatusesPage() {
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [departments, setDepartments] = useState<BoardDepartment[]>([]);
  // Справочники окон выбора: должности, «Рук-ль», отметки (11.11.2026).
  // Выгрузка — только владельцу организации (Анастасия) и суперадмину.
  // Анастасия, 11.11.2026: «нужно убрать кнопку „выгрузить“ у всех кроме
  // меня… это же слив базы. Если кому-то нужно будет — ко мне будут
  // обращаться». Привязано к роли owner, а не к имени (как раньше «Сумма»).
  const canExport = useAuthStore(
    (st) => st.user?.role === "superadmin" || st.user?.org_role === "owner",
  );
  const [catalogs, setCatalogs] = useState<Record<CatalogKind, CatalogItem[]>>(
    { positions: [], managers: [], marks: [] },
  );
  const setCatalog = useCallback(
    (kind: CatalogKind, list: CatalogItem[]) => setCatalogs((cur) => ({ ...cur, [kind]: list })),
    [],
  );
  // Справочники для выпадающих списков: должности и руководители собираются
  // из уже существующих значений, HR — из участников организации.
  const [people, setPeople] = useState<{ user_id: number; user_name: string | null }[]>([]);
  // Справочник сорсеров (те же метки кандидата) — для «+» в колонке «Сорсер».
  const [sourcerTags, setSourcerTags] = useState<Tag[]>([]);
  const [orgHr, setOrgHr] = useState<{ user_id: number; user_name: string | null }[]>([]);
  const [loading, setLoading] = useState(true);
  // Отдел слева живёт в URL (?dept=) — работают браузерные «Назад/Вперёд».
  // Раньше тут были «направления» — отдельный список папок, но это те же
  // отделы (решение владельца 21.09.2026), так что панель строится по отделам.
  const [dept, setDept] = useUrlTab<string>("dept", "all");
  // Вкладки — только «Все» и песочницы. Старая ссылка на команду или на
  // «Без отдела» (?dept=…) открывает «Все», а не пустую доску без вкладки.
  useEffect(() => {
    if (!departments.length || dept === "all") return;
    if (!sandboxTabs(departments).some((d) => String(d.id) === dept)) setDept("all", { push: false });
  }, [departments, dept, setDept]);
  const [q, setQ] = useState("");
  // Быстрых фильтров «HR: все» и «Сорсер: все» больше нет (клиент,
  // 11.11.2026: «эти поля можно удалить — они есть в фильтрах»). Выбор,
  // запомненный в браузере раньше, тоже не применяем — чистим его разово.
  useEffect(() => {
    try {
      localStorage.removeItem("hf-statuses-hr");
      localStorage.removeItem("hf-statuses-sourcer");
    } catch { /* без хранилища нечего чистить */ }
  }, []);

  const [filters, setFilters] = useState<BoardFilters>(() => {
    try {
      const raw = localStorage.getItem(FILTERS_STORAGE_KEY) ?? localStorage.getItem(FILTERS_STORAGE_KEY_V2);
      if (raw) {
        return readSavedFilters(JSON.parse(raw));
      }
    } catch { /* повреждённое значение — начинаем без фильтров */ }
    return EMPTY_FILTERS;
  });

  useEffect(() => {
    try {
      localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(filters));
    } catch { /* приватный режим — переживём без сохранения */ }
  }, [filters]);

  /** Строки фильтра: добавить, поправить, убрать. */
  const addRule = () => setFilters((f) => ({ ...f, rules: [...f.rules, newRule()] }));
  const updateRule = (id: string, patch: Partial<FilterRule>) =>
    setFilters((f) => ({ ...f, rules: f.rules.map((r) => (r.id === id ? { ...r, ...patch } : r)) }));
  const removeRule = (id: string) =>
    setFilters((f) => ({ ...f, rules: f.rules.filter((r) => r.id !== id) }));

  const [pickerOpen, setPickerOpen] = useState(false);
  // Открыли панель фильтров — пустую строку ставим сразу, как ClickUp
  // («Select filter»): человеку не нужно сначала искать «Добавить».
  useEffect(() => {
    if (pickerOpen && filters.rules.length === 0) addRule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickerOpen]);
  // Сортировка по дате: клик по заголовку — сначала новые, второй — старые,
  // третий возвращает обычный порядок.
  // По умолчанию сортируем по выходу в отдел: сверху те, кто вышел недавно,
  // ниже — давние (Мария, 28.09.2026). Заголовок колонки переключает порядок.
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir } | null>(
    { key: "department_start_date", dir: "desc" }
  );
  const toggleSort = (key: SortKey) =>
    setSort((cur) =>
      cur?.key !== key ? { key, dir: "desc" } : cur.dir === "desc" ? { key, dir: "asc" } : null
    );

  const months = useMemo(() => recentMonths(), []);
  // Вид доски — ОБЩИЙ для всех HR и всех вкладок (клиент, 11.11.2026: «если
  // Маша уберёт столбец „2 недели“, он уберётся у всех»). Секций в виде больше
  // нет — видны все. До 11.11 у каждого был свой набор секций и колонок на
  // каждой вкладке (мит 07.10.2026).
  const [view, setView] = useState<BoardView>(EMPTY_BOARD_VIEW);
  // Свои поля организации (11.11.2026). Реестр модуля обновляем вместе со
  // стейтом — по стейту перерисовываемся.
  const [customFields, setCustomFieldsState] = useState<CustomField[]>([]);
  // Цвета и порядок пунктов списков — общие; реестр модуля + стейт.
  const [, setMetaState] = useState<DropdownMeta>({});
  const applyMeta = useCallback((m: DropdownMeta) => {
    setDropdownMetaRegistry(m);
    setMetaState(m);
  }, []);
  useEffect(() => {
    metaReloader = () => getDropdownMeta().then(applyMeta);
    setMetaSaver(async (kind, patch) => {
      // Сразу на экране, потом на сервере; не вышло — перечитать.
      const before = DROPDOWN_META;
      const cur = before[kind] ?? { order: [], colors: {} };
      const colors = { ...cur.colors };
      for (const [k, v] of Object.entries(patch.colors ?? {})) {
        if (v) colors[k] = v; else delete colors[k];
      }
      applyMeta({ ...before, [kind]: { order: patch.order ?? cur.order, colors } });
      try {
        applyMeta(await saveDropdownMeta(kind, patch));
      } catch (e: any) {
        applyMeta(before);
        toast.error(e?.response?.data?.detail || "Не удалось сохранить");
      }
    });
  }, [applyMeta]);
  const applyCustomFields = useCallback((list: CustomField[]) => {
    setCustomFields(list);
    setCustomFieldsState(list);
  }, []);
  const hiddenColumns = view.hidden;
  // Ширина, которую тянут прямо сейчас: на экране сразу, на сервер — по
  // отпусканию мыши, чтобы не слать запрос на каждый пиксель.
  const [liveWidths, setLiveWidths] = useState<Record<string, number>>({});
  const [showFields, setShowFields] = useState(false);
  // Окно выгрузки: месяцы и вехи стажа выбирают галочками, книга собирается
  // листами (Мария, 07.10.2026 — «выгрузка за сентябрь, октябрь и декабрь»).
  const [showExport, setShowExport] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  // Строка = назначение (человек в отделе), поэтому у одного человека их может
  // быть несколько: в песочнице и в команде. Ключ — назначение, иначе правка
  // даты в отделе подсвечивала и перерисовывала бы строку практики.
  const [savingId, setSavingId] = useState<string | null>(null);

  /** Смена статуса. Перевод в «Уволен»/«Уволился» на бэкенде запускает
   *  оффбординг: гасит аккаунт, отзывает сессии и отвязывает Telegram.
   *  Молча это делать нельзя — сообщаем, что именно произошло. */
  const changeStatus = async (row: BoardRow, status: string) => {
    const label = STATUSES.find((s2) => s2.key === status)?.label || status;
    await patch(row, { status });
    if (status === "dismissed" || status === "quit") {
      toast(
        `${row.name} → ${label}. Аккаунт отключён, сессии сброшены, Telegram отвязан.`,
        { icon: "⚠️", duration: 6000 }
      );
    }
  };

  // Крутилка — только при первой загрузке. Раньше её показывал каждый
  // onReload (поставили сорсера, сменили отдел): таблица пропадала и
  // рисовалась заново — открытое окно выбора закрывалось посреди работы,
  // прокрутка прыгала наверх (11.11.2026).
  const loadedOnce = useRef(false);
  const load = useCallback(async () => {
    if (!loadedOnce.current) setLoading(true);
    try {
      setRows(await getBoardRows());
    } catch {
      toast.error("Не удалось загрузить доску");
    } finally {
      loadedOnce.current = true;
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    getBoardDepartments().then(setDepartments).catch(() => setDepartments([]));
    for (const kind of ["positions", "managers", "marks"] as CatalogKind[]) {
      getCatalog(kind).then((list) => setCatalog(kind, list)).catch(() => setCatalog(kind, []));
    }
    getBoardView()
      .then((v) => { setFieldLabels(v.labels); setView(v); })
      .catch(() => setView(EMPTY_BOARD_VIEW));
    getCustomFields().then(applyCustomFields).catch(() => applyCustomFields([]));
    getDropdownMeta().then(applyMeta).catch(() => applyMeta({}));
    getTags().then(setSourcerTags).catch(() => setSourcerTags([]));
    // Вести сотрудника может только HR. В организации числятся все
    // работники, и без фильтра в список попадали бы полсотни человек,
    // среди которых нужного не найти.
    getOrgMembers()
      .then((m) =>
        setPeople(
          m
            .filter((x) => x.role === "owner" || x.role === "admin" || x.role === "hr")
            .filter((x) => isBoardHr(x.user_name))
            .map((x) => ({ user_id: x.user_id, user_name: x.user_name }))
            .sort((a, b) => (a.user_name || "").localeCompare(b.user_name || "", "ru"))
        )
      )
      .catch(() => setPeople([]));
    // Кому показывать отдел — выбирают из всех, кто вообще работает в HR, а не
    // из двух ведущих доску: юнит Марии может быть нужен и рекрутёру.
    getOrgMembers()
      .then((m) =>
        setOrgHr(
          m
            .filter((x) => x.role === "owner" || x.role === "admin" || x.role === "hr")
            .map((x) => ({ user_id: x.user_id, user_name: x.user_name }))
            .sort((a, b) => (a.user_name || "").localeCompare(b.user_name || "", "ru"))
        )
      )
      .catch(() => setOrgHr([]));
  }, []);

  /** Патч строки: оптимистично + откат при ошибке.
   *
   *  Даты отдела и вехи принадлежат НАЗНАЧЕНИЮ, поэтому всегда говорим серверу,
   *  какое правим: без этого правка «выхода в отдел» в команде переписала бы
   *  даты практики в песочнице. Статус — у человека, он один на все строки,
   *  поэтому его правка обновляет их все.
   */
  const patch = async (row: BoardRow, body: BoardRowUpdate) => {
    const prev = rows;
    const personWide = "status" in body;
    const mine = (x: BoardRow) =>
      personWide ? x.entity_id === row.entity_id : rowKey(x) === rowKey(row);
    setSavingId(rowKey(row));
    setRows((cur) => cur.map((x) => (mine(x) ? { ...x, ...body } as BoardRow : x)));
    try {
      const fresh = await updateBoardRow(row.entity_id, { ...body, placement_id: row.placement_id });
      setRows((cur) => cur.map((x) => {
        if (!mine(x)) return x;
        // Строке, которую правили, отдаём ответ сервера целиком; остальным
        // строкам того же человека — только то, что у них общее.
        return rowKey(x) === rowKey(row) ? fresh : { ...x, status: fresh.status } as BoardRow;
      }));
    } catch (e: any) {
      setRows(prev);
      toast.error(e?.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setSavingId(null);
    }
  };

  /** Поставить человека в отдел.
   *
   *  ДОБАВЛЯЕМ только в одном случае: из песочницы в команду — человек
   *  остаётся на практике, а в команде появляется ещё одна строка на ту же
   *  карточку (решение владельца 30.09.2026). Во всех остальных случаях —
   *  ПЕРЕНОС: песочница у человека одна, поэтому выбор другой песочницы
   *  переводит его туда (владелец 06.10.2026: «нельзя выбрать другой сендбокс,
   *  если человек уже в сендбоксе — это неверно»), а смена команды на команду
   *  всегда была переездом. Список перезагружаем: строк становится больше или
   *  меньше.
   */
  const placeInDept = async (row: BoardRow, deptId: number) => {
    const target = departments.find((d) => d.id === deptId);
    // Из песочницы в команду не передаём «что заменить»: сервер сам переносит
    // человека из прежнего РАБОЧЕГО отдела, если он там был, и оставляет
    // песочницу. Иначе отделы копились (Мария, 07.10.2026).
    const addition = row.department_is_sandbox && target?.kind === "team";
    setSavingId(rowKey(row));
    try {
      await addBoardPlacement(
        row.entity_id, deptId,
        addition ? null : row.placement_id,
      );
      setRows(await getBoardRows());
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось поставить в отдел");
    } finally {
      setSavingId(null);
    }
  };

  /** Убрать человека из отдела (× у пилюли). Строку практики так не снять —
   *  сервер разрешает это только админу. */
  const removeFromDept = async (row: BoardRow) => {
    if (row.placement_id == null) return;
    setSavingId(rowKey(row));
    try {
      await removeBoardPlacement(row.placement_id);
      setRows(await getBoardRows());
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось убрать из отдела");
    } finally {
      setSavingId(null);
    }
  };

  const searched = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let out = rows;
    if (needle) {
      out = out.filter((r) =>
        [r.name, r.position, r.department_name, r.telegram, r.manager]
          .filter(Boolean).some((v) => String(v).toLowerCase().includes(needle))
      );
    }

    // Условия панели складываются по правилу filters.mode: «любое» (по
    // умолчанию) или «все сразу». Значения внутри одной колонки — всегда «или».
    out = out.filter((r) => rowMatchesFilters(r, filters));
    return out;
  }, [rows, q, filters]);

  const visibleColumns = useMemo(
    () => arrangeColumns({ ...view, widths: { ...view.widths, ...liveWidths } }),
    // customFields — колонки своих полей зависят от реестра
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [view, liveWidths, customFields],
  );
  /** Поменять часть общего вида: сразу на экране, потом на сервере; не
   *  вышло — вернуть как было. */
  const saveView = async (patch: Partial<BoardView>) => {
    const before = view;
    const next = { ...view, ...patch };
    if (patch.labels) setFieldLabels(next.labels);
    setView(next);
    try {
      const saved = await saveBoardView(patch);
      setFieldLabels(saved.labels);
      setView(saved);
    } catch (e: any) {
      setFieldLabels(before.labels);
      setView(before);
      toast.error(e?.response?.data?.detail || "Не удалось сохранить вид");
    }
  };
  const setColumnHidden = (key: string, hide: boolean) =>
    saveView({ hidden: hide ? [...view.hidden, key] : view.hidden.filter((k) => k !== key) });

  /** Ширина колонки: тянут край заголовка (клиент, 11.11.2026 — «как в
   *  ClickUp, сами меняем ширину столбцов»). Общая для всех. */
  const startResize = (key: string, startWidth: number) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const x0 = e.clientX;
    let w = startWidth;
    const move = (ev: MouseEvent) => {
      w = Math.max(60, Math.min(600, Math.round(startWidth + ev.clientX - x0)));
      setLiveWidths((cur) => ({ ...cur, [key]: w }));
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
      setLiveWidths((cur) => { const { [key]: _drop, ...rest } = cur; return rest; });
      if (w !== startWidth) saveView({ widths: { ...view.widths, [key]: w } });
    };
    document.body.style.cursor = "col-resize";
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  };

  const counts = useMemo(() => {
    // У отдела — сколько в нём строк, у «Все» — сколько ЛЮДЕЙ: человек в
    // песочнице и в команде занимает две строки, но человек-то один, и бейдж
    // не должен расходиться со списком. Скрытые секции не считаем — иначе
    // бейдж покажет больше, чем видно (правило «бейдж и список не расходятся»).
    const c: Record<string, number> = { [UNASSIGNED]: 0 };
    const people = new Set<number>();
    for (const r of searched) {
      people.add(r.entity_id);
      const key = r.department_id != null ? String(r.department_id) : UNASSIGNED;
      c[key] = (c[key] || 0) + 1;
    }
    c.all = people.size;
    return c;
  }, [searched]);

  const visible = useMemo(() => {
    // В отделе — только его строки. «Без отдела» — те, кого ещё никуда не
    // поставили.
    if (dept === UNASSIGNED) return searched.filter((r) => r.department_id == null);
    if (dept !== "all") return searched.filter((r) => String(r.department_id) === dept);
    // «Все» — каждый человек ОДИН раз (решение владельца 30.09.2026): у того,
    // кто вышел с практики в команду, строк две, и обе здесь — это путаница.
    // Оставляем строку команды: она свежее и в ней вехи, по которым и смотрят.
    const best = new Map<number, BoardRow>();
    for (const r of searched) {
      const cur = best.get(r.entity_id);
      if (!cur || (cur.department_is_sandbox && !r.department_is_sandbox) ||
          (cur.department_id == null && r.department_id != null)) {
        best.set(r.entity_id, r);
      }
    }
    return searched.filter((r) => best.get(r.entity_id) === r);
  }, [searched, dept]);

  /** Значения для выбора в правиле — те, что реально есть в таблице.
   *  Считаем по строкам текущей папки и поиска, но БЕЗ учёта самих правил:
   *  иначе, выбрав значение, человек терял бы возможность сменить его. */
  const valuesFor = useCallback(
    (key: FilterKey): { value: string; count: number }[] => {
      const needle = q.trim().toLowerCase();
      const map = new Map<string, number>();
      for (const r of rows) {
        if (needle && ![r.name, r.position, r.department_name, r.telegram, r.manager]
          .filter(Boolean).some((v) => String(v).toLowerCase().includes(needle))) continue;
        const vals = cellValues(r, key);
        if (!vals.length) continue;
        for (const v of vals) map.set(v, (map.get(v) || 0) + 1);
      }
      let entries = [...map.entries()];
      // «Отдел» — только песочницы и отделы из списка, как в переводе
      // (владелец, 11.11.2026: «в фильтрах забыл убрать»). Старое значение,
      // уже отмеченное в фильтре, не прячем — иначе его нельзя было бы снять.
      if (key === "department") {
        const allowed = new Set(departmentFilterNames(departments));
        const chosen = filters.rules.filter((r) => r.key === "department").flatMap((r) => r.values);
        entries = entries.filter(([v]) => allowed.has(v) || chosen.includes(v));
      }
      const list = entries
        .map(([value, count]) => ({ value, count }))
        .sort((a, b) => a.value.localeCompare(b.value, "ru"));
      // Незаполненные ищут условием «пусто», а не значением в списке.
      return list;
    },
    [rows, q, departments, filters.rules]
  );

  const activeCount = countActive(filters);

  /** Выгрузка в Excel того, что сейчас отобрано.
   *
   *  «А мы можем эти фильтры в табличку выгружать?» (Мария, 29.09.2026): она
   *  отбирает людей за месяц или по сорсеру и дальше считает выплаты в
   *  таблице. Выгружаем РОВНО видимое — с учётом поиска, фильтров, выбранного
   *  отдела и сортировки, плюс колонку статуса: в файле групп нет. */
  /** Строки → лист: шапка как в таблице, плюс колонка со статусом. */
  const sheetFrom = (items: BoardRow[], cols: typeof COLUMNS) => {
    const header = ["Статус", ...cols.map((c) => fieldLabel(c.key))];
    const body: (string | number)[][] = items.map((r) => [
      STATUSES.find((s2) => (s2.members as readonly string[]).includes(r.status))?.label || r.status,
      ...cols.map((c) => {
        if (c.key === "sourcer") return (r.sourcers ?? []).map((t) => t.name).join(", ");
        if (c.key === "offer") return r.offer_file_name || "";
        return cellText(r, c.key as FilterKey);
      }),
    ]);
    const ws = XLSX.utils.aoa_to_sheet([header, ...body]);
    ws["!cols"] = header.map((h, i) => ({
      wch: Math.min(40, Math.max(h.length + 2, ...body.map((row) => String(row[i] ?? "").length + 2))),
    }));
    return { ws, count: body.length };
  };

  /** Выгрузка в Excel.
   *
   *  Простой клик отдаёт то, что на экране. Окно «Выгрузить» собирает КНИГУ:
   *  лист на каждый выбранный месяц и лист на каждую веху стажа — «выгрузку за
   *  сентябрь, за октябрь и за декабрь… как месяц работы сотрудника, как
   *  закрытие испытательного срока и как год работы» (Мария, 07.10.2026).
   *  Период считается по дате ВЫХОДА В ОТДЕЛ, веха — по её собственной дате.
   */
  /** Без выбора — ровно экран: секции и колонки из «Вида» этой вкладки. */
  const exportToExcel = (plan?: ExportPlan, pick?: ExportPick) => {
    const wb = XLSX.utils.book_new();
    let total = 0;
    const items = pick ? rowsOfSections(visible, pick.sections) : grouped.flatMap((g) => g.items);
    const cols = pick ? exportColumns(pick.columns, arrangeColumns(view, true)) : visibleColumns;
    for (const sheet of buildExportSheets(items, months, plan)) {
      if (!sheet.items.length) continue;
      const { ws, count } = sheetFrom(sheet.items, cols);
      // Excel не принимает в имени листа : \ / ? * [ ] и больше 31 символа.
      XLSX.utils.book_append_sheet(wb, ws, sheet.title.replace(/[:\\/?*[\]]/g, " ").slice(0, 31));
      total += count;
    }

    
    if (!total) {
      toast(plan
        ? "Выгружать нечего — под выбранные периоды никто не подошёл"
        : "Выгружать нечего — на экране никого нет. Проверьте фильтры и поиск");
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    XLSX.writeFile(wb, `statuses-${today}.xlsx`);
    toast.success(`Выгружено строк: ${total}`);
  };

  const grouped = useMemo(
    () => STATUSES.map((s) => {
      const items = visible.filter((r) => (s.members as readonly string[]).includes(r.status));
      if (!sort) return { ...s, items };
      // Пустая дата — всегда в конце, в любую сторону: строка без даты не
      // «самая старая», про неё просто ничего не известно.
      const val = (r: BoardRow) => r[sort.key] || "";
      return {
        ...s,
        items: [...items].sort((a, b) => {
          const x = val(a), y = val(b);
          if (!x || !y) return x ? -1 : y ? 1 : 0;
          return sort.dir === "asc" ? x.localeCompare(y) : y.localeCompare(x);
        }),
      };
    }),
    [visible, sort]
  );

  return (
    <div className="hf-statuses-page">
      <div className="hf-statuses-header">
        <div>
          {/* Раздел называется «Штат» (владелец, 09.10.2026). Адрес остался
              /statuses: по нему уже ходят закладки и ссылки. */}
          <h1 className="hf-statuses-title">Штат</h1>
        </div>
        <DeptTabs
          departments={departments}
          orgHr={orgHr}
          counts={counts}
          active={dept}
          onSelect={setDept}
          onSaved={(d) => setDepartments((cur) => cur.map((x) => (x.id === d.id ? d : x)))}
          onRows={load}
        />
        <div className="hf-statuses-tools">
          <div className="hf-statuses-search">
            <Search className="hf-statuses-search-icon" size={15} />
            <input
              className="hf-statuses-search-input"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Поиск"
            />
          </div>


          {/* Шестерёнка вместо «Вида» (клиент, 11.11.2026 — как в ClickUp):
              боковая панель «Поля» с бегунками, вид общий для всех. */}
          <button
            className={clsx("hf-statuses-gear", hiddenColumns.length > 0 && "hf-statuses-filters-btn-on")}
            onClick={() => setShowFields((v) => !v)}
            title="Поля: какие колонки показывать — у всех"
            aria-label="Поля"
          >
            <Settings size={16} />
          </button>

          {/* «Выгрузить» сразу отдаёт в Excel тех, кто на экране после
              фильтров (владелец, 26.10.2026: «кнопка должна выгружать всех
              кандидатов по фильтрам, а не открывать модалку»). Раньше она
              открывала окно периодов, где главная чёрная кнопка была
              неактивна, пока не отмечен месяц, — Мария жала её и думала, что
              выгрузка сломана. Книга по месяцам и вехам — за стрелкой рядом. */}
          {canExport && <div className="hf-statuses-export-split">
            <button
              className="hf-statuses-export-btn hf-statuses-export-main"
              onClick={() => exportToExcel()}
              title="Выгрузить в Excel то, что сейчас на экране — с учётом фильтров, поиска, вкладки и «Вида»"
            >
              <Download size={15} />
              Выгрузить
            </button>
            <button
              className="hf-statuses-export-btn hf-statuses-export-more"
              onClick={() => setShowExport(true)}
              title="Выгрузка с выбором: секции, колонки, листы по месяцам и вехам стажа"
              aria-label="Выгрузка с выбором"
            >
              <ChevronDown size={14} />
            </button>
          </div>}

          <div className="hf-statuses-filters-picker">
            <button
              className={clsx(
                "hf-statuses-filters-btn",
                activeCount > 0 && "hf-statuses-filters-btn-on"
              )}
              onClick={() => setPickerOpen((v) => !v)}
            >
              <SlidersHorizontal size={15} />
              Фильтры
              {activeCount > 0 && (
                <span className="hf-statuses-filters-badge">{activeCount}</span>
              )}
            </button>

            {pickerOpen && (
              <>
                <div
                  className="hf-statuses-picker-backdrop"
                  onClick={() => setPickerOpen(false)}
                />
                <FilterBuilder
                  filters={filters}
                  valuesFor={valuesFor}
                  onJoin={(join) => setFilters((f) => ({ ...f, join }))}
                  onAdd={addRule}
                  onUpdate={updateRule}
                  onRemove={removeRule}
                  onClearAll={() => setFilters({ ...EMPTY_FILTERS, rules: [newRule()] })}
                />
              </>
            )}
          </div>
        </div>
      </div>

      {activeCount > 0 && (
        // Чипы — заполненные строки фильтра, между ними «и»/«или» — та же
        // связка, что в окне. Клик по чипу открывает окно фильтров, крестик
        // убирает строку.
        <div className="hf-statuses-fchips">
          {filters.rules.filter(ruleComplete).map((r, i) => (
            <Fragment key={r.id}>
              {i > 0 && (
                <span className="hf-statuses-fchip-join">{filters.join === "and" ? "и" : "или"}</span>
              )}
              <span className="hf-statuses-fchip">
                <button
                  type="button"
                  className="hf-statuses-fchip-body"
                  onClick={() => setPickerOpen(true)}
                  title="Изменить фильтры"
                >
                  {ruleText(r)}
                </button>
                <button
                  type="button"
                  className="hf-statuses-fchip-x"
                  onClick={() => removeRule(r.id)}
                  title="Убрать условие"
                  aria-label={`Убрать условие «${ruleText(r)}»`}
                >
                  <X size={12} />
                </button>
              </span>
            </Fragment>
          ))}
        </div>
      )}

      {loading ? (
        <div className="hf-statuses-loading">
          <Loader2 className="animate-spin" size={26} />
        </div>
      ) : (
        <div className="hf-statuses-body">
          {showFields && (
            <FieldsPanel
              view={view}
              onToggle={setColumnHidden}
              onSave={saveView}
              onShowAll={() => saveView({ hidden: [] })}
              onClose={() => setShowFields(false)}
              onCustomFields={applyCustomFields}
            />
          )}

          {showExport && canExport && (
            <ExportModal
              months={months}
              hideable={hideableColumns()}
              sections={STATUSES.map((s) => s.key)}
              columns={visibleColumns.filter((c) => c.key !== "name").map((c) => c.key)}
              order={arrangeColumns(view, true)}
              onClose={() => setShowExport(false)}
              onExport={(plan, pick) => { exportToExcel(plan, pick); setShowExport(false); }}
            />
          )}

          <div className="hf-statuses-table-wrap">
            <table className="hf-statuses-table">
              <colgroup>
                {visibleColumns.map((c) => <col key={c.key} style={{ width: c.width }} />)}
              </colgroup>
              <thead>
                <tr>
                  {visibleColumns.map((c) => {
                    const sortable = SORTABLE.includes(c.key as SortKey);
                    const on = sort?.key === c.key;
                    return (
                      <th
                        key={c.key}
                        className={clsx(
                          "hf-statuses-th",
                          c.key === "name" && "hf-statuses-sticky",
                          sortable && "hf-statuses-th-sortable",
                          on && "hf-statuses-th-sorted"
                        )}
                        title={
                          sortable
                            ? `${fieldLabel(c.key)} — сортировать по дате`
                            : fieldLabel(c.key)
                        }
                        onClick={sortable ? () => toggleSort(c.key as SortKey) : undefined}
                      >
                        {headerLabel(c)}
                        {sortable && (
                          <span className="hf-statuses-th-arrow">
                            {on ? (sort!.dir === "desc" ? "↓" : "↑") : "↕"}
                          </span>
                        )}
                        <span
                          className="hf-statuses-th-resize"
                          title="Потяните, чтобы изменить ширину (у всех)"
                          onMouseDown={startResize(c.key, c.width)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </th>
                    );
                  })}
                </tr>
              </thead>

              <tbody>
                {grouped.map((g) => {
                  const isCollapsed = collapsed[g.key];
                  return (
                    <Fragment key={g.key}>
                      <tr
                        className="hf-statuses-group"
                        onClick={() => setCollapsed((c) => ({ ...c, [g.key]: !c[g.key] }))}
                      >
                        <td className="hf-statuses-group-cell" colSpan={visibleColumns.length}>
                          <div className="hf-statuses-group-inner">
                            {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                            <span className={clsx("hf-statuses-chip", `hf-statuses-chip-${g.key}`)}>
                              {g.label}
                            </span>
                            <span className="hf-statuses-group-count">{g.items.length}</span>
                          </div>
                        </td>
                      </tr>

                      {!isCollapsed && g.items.map((r) => (
                        <Row
                          key={rowKey(r)}
                          row={r}
                          columns={visibleColumns}
                          departments={departments}
                          onDepartments={setDepartments}
                          onCustomFields={applyCustomFields}
                          catalogs={catalogs}
                          onCatalog={setCatalog}
                          people={people}
                          sourcerTags={sourcerTags}
                          onSourcerTags={setSourcerTags}
                          saving={savingId === rowKey(r)}
                          onPatch={patch}
                          onStatus={changeStatus}
                          onPlace={placeInDept}
                          onUnplace={removeFromDept}
                          onReload={load}
                        />
                      ))}

                      {!isCollapsed && g.items.length === 0 && (
                        <tr>
                          <td className="hf-statuses-empty" colSpan={visibleColumns.length}>Пусто</td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>

            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// SIDEBAR
// ============================================================

/** Окно фильтров «как в ClickUp» (клиент, 11.11.2026: «открывается окно — в
 *  нём выбираешь поле, потом его значение; если нужно „И“ или „ИЛИ“ и ещё
 *  фильтры — кнопка „Добавить фильтр“ и „AND/OR“… всё на русском»).
 *  Строка: поле ▾ → условие ▾ → значение. Слева первой строки «Где», у второй —
 *  выбор связки «И / ИЛИ», дальше она же. Незаполненная строка не отбирает.
 *  До 11.11 здесь были галочки по колонкам (с 24.09: Мария нашла правила
 *  сложными); клиент попросил вернуть правила, как в ClickUp. */
function FilterBuilder({
  filters, valuesFor, onJoin, onAdd, onUpdate, onRemove, onClearAll,
}: {
  filters: BoardFilters;
  valuesFor: (key: FilterKey) => { value: string; count: number }[];
  onJoin: (join: "and" | "or") => void;
  onAdd: () => void;
  onUpdate: (id: string, patch: Partial<FilterRule>) => void;
  onRemove: (id: string) => void;
  onClearAll: () => void;
}) {
  const joinText = filters.join === "and" ? "И" : "ИЛИ";
  return (
    <div className="hf-statuses-picker hf-fb">
      <div className="hf-fb-head">Фильтры</div>
      <div className="hf-fb-rules">
        {filters.rules.map((r, i) => (
          <div key={r.id} className="hf-fb-rule">
            <div className="hf-fb-join">
              {i === 0 ? "Где" : i === 1 ? (
                <select
                  className="hf-fb-select hf-fb-join-select"
                  value={filters.join}
                  onChange={(e) => onJoin(e.target.value as "and" | "or")}
                  title="«И» — все условия сразу, «ИЛИ» — хотя бы одно"
                >
                  <option value="and">И</option>
                  <option value="or">ИЛИ</option>
                </select>
              ) : <span className="hf-fb-join-text">{joinText}</span>}
            </div>
            <div className="hf-fb-body">
              <FbFieldSelect
                value={r.key}
                onChange={(key) => onUpdate(r.id, { key, op: opsFor(key)[0], values: [], from: undefined, to: undefined, text: undefined })}
              />
              <select
                className="hf-fb-select"
                value={r.op}
                disabled={!r.key}
                onChange={(e) => onUpdate(r.id, { op: e.target.value as FilterOp })}
              >
                {(r.key ? opsFor(r.key) : (["is"] as FilterOp[])).map((op) => (
                  <option key={op} value={op}>{OP_LABELS[op]}</option>
                ))}
              </select>
              {r.key && (r.op === "is" || r.op === "is_not") && (
                <FbValueSelect
                  column={r.key}
                  options={valuesFor(r.key)}
                  values={r.values}
                  onChange={(values) => onUpdate(r.id, { values })}
                />
              )}
              {r.key && r.op === "between" && (
                <FbDateRange
                  from={r.from}
                  to={r.to}
                  onChange={(from, to) => onUpdate(r.id, { from, to })}
                />
              )}
              {r.key && r.op === "contains" && (
                <input
                  className="hf-fb-input"
                  placeholder="Текст…"
                  value={r.text || ""}
                  onChange={(e) => onUpdate(r.id, { text: e.target.value })}
                />
              )}
            </div>
            <button
              type="button"
              className="hf-fb-trash"
              title="Убрать условие"
              onClick={() => onRemove(r.id)}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
      <div className="hf-fb-foot">
        <button type="button" className="hf-fb-add" onClick={onAdd}>
          <Plus size={14} /> Добавить фильтр
        </button>
        {filters.rules.some(ruleComplete) && (
          <button type="button" className="hf-fb-clear" onClick={onClearAll}>Очистить всё</button>
        )}
      </div>
    </div>
  );
}

/** Выпадашка внутри окна фильтров: кнопка + список под ней, закрывается
 *  кликом мимо и Escape. */
function useFbDropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key, true);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key, true);
    };
  }, [open]);
  return { open, setOpen, ref };
}

/** «Выбрать поле ▾» — список полей с поиском и значком типа, как в ClickUp. */
function FbFieldSelect({ value, onChange }: { value: FilterKey | ""; onChange: (key: FilterKey) => void }) {
  const dd = useFbDropdown();
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const fields = filterableColumns().filter((c) => !needle || fieldLabel(c.key).toLowerCase().includes(needle));
  return (
    <div className="hf-fb-dd" ref={dd.ref}>
      <button type="button" className={clsx("hf-fb-select hf-fb-dd-btn", !value && "is-empty")}
              onClick={() => { setQ(""); dd.setOpen(!dd.open); }}>
        {value ? fieldLabel(value) : "Выбрать поле"}
        <ChevronDown size={14} />
      </button>
      {dd.open && (
        <div className="hf-fb-dd-list">
          <input autoFocus className="hf-statuses-picker-search" placeholder="Поиск…" value={q}
                 onChange={(e) => setQ(e.target.value)} />
          {fields.map((c) => (
            <button key={c.key} type="button" className={clsx("hf-fb-dd-item", c.key === value && "is-on")}
                    onClick={() => { dd.setOpen(false); onChange(c.key); }}>
              <span className="hf-fields-ico"><FieldTypeIcon k={c.key} /></span>
              {fieldLabel(c.key)}
            </button>
          ))}
          {!fields.length && <div className="hf-statuses-hr-menu-hint">Ничего не найдено</div>}
        </div>
      )}
    </div>
  );
}

/** Значения поля галочками с поиском и количеством людей. */
function FbValueSelect({
  column, options, values, onChange,
}: {
  column: FilterKey;
  options: { value: string; count: number }[];
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const dd = useFbDropdown();
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  // Выбранное, которого уже нет на доске, не прячем — его нужно уметь снять.
  const all = [...options, ...values.filter((v) => !options.some((o) => o.value === v)).map((v) => ({ value: v, count: 0 }))];
  const shown = all.filter((o) => !needle || valueLabel(column, o.value).toLowerCase().includes(needle));
  const toggle = (v: string) => onChange(values.includes(v) ? values.filter((x) => x !== v) : [...values, v]);
  return (
    <div className="hf-fb-dd hf-fb-dd-grow" ref={dd.ref}>
      <button type="button" className={clsx("hf-fb-select hf-fb-dd-btn", !values.length && "is-empty")}
              onClick={() => { setQ(""); dd.setOpen(!dd.open); }}>
        <span className="hf-fb-dd-text">
          {values.length ? values.map((v) => valueLabel(column, v)).join(", ") : "Выбрать значение"}
        </span>
        <ChevronDown size={14} />
      </button>
      {dd.open && (
        <div className="hf-fb-dd-list">
          <input autoFocus className="hf-statuses-picker-search" placeholder="Поиск…" value={q}
                 onChange={(e) => setQ(e.target.value)} />
          {shown.map((o) => (
            <label key={o.value} className="hf-fb-dd-item">
              <input type="checkbox" checked={values.includes(o.value)} onChange={() => toggle(o.value)} />
              <span className="hf-fb-dd-text">{valueLabel(column, o.value)}</span>
              <span className="hf-statuses-picker-hint">{o.count || ""}</span>
            </label>
          ))}
          {!shown.length && <div className="hf-statuses-hr-menu-hint">Нет значений</div>}
        </div>
      )}
    </div>
  );
}

/** Период для дат: «с» и «по» плюс месяц одним кликом — Мария набирала даты
 *  руками и промахивалась в цифрах (встреча 29.09.2026). */
function FbDateRange({
  from, to, onChange,
}: { from?: string; to?: string; onChange: (from?: string, to?: string) => void }) {
  const months = useMemo(() => recentMonths(), []);
  return (
    <div className="hf-fb-dates">
      <input type="date" className="hf-fb-input" value={from || ""} title="с"
             onChange={(e) => onChange(e.target.value || undefined, to)} />
      <span>—</span>
      <input type="date" className="hf-fb-input" value={to || ""} title="по"
             onChange={(e) => onChange(from, e.target.value || undefined)} />
      <select
        className="hf-fb-select"
        value={months.find((m) => m.from === from && m.to === to)?.label || ""}
        onChange={(e) => {
          const m = months.find((x) => x.label === e.target.value);
          if (m) onChange(m.from, m.to);
        }}
      >
        <option value="">Месяц…</option>
        {months.map((m) => <option key={m.label} value={m.label}>{m.label}</option>)}
      </select>
    </div>
  );
}

/** Вкладки над доской: «Все» и песочницы (владелец, 10.11.2026 — «убираем
 *  [колонку отделов] и оставляем сверху кнопки: все и 3 сендбокса»). Команды
 *  вкладками больше не показываются: отделы теперь из фиксированного списка, и
 *  смотреть людей отдела удобнее фильтром «Отдел». До 10.11.2026 слева была
 *  колонка всех отделов с «Без отдела», перетаскиванием, скрытием и «+ Отдел».
 *  Карандаш у песочницы открывает её настройки: кому видна, по умолчанию ли
 *  в неё попадают с практики. */
function DeptTabs({
  departments, orgHr, counts, active, onSelect, onSaved, onRows,
}: {
  departments: BoardDepartment[];
  orgHr: { user_id: number; user_name: string | null }[];
  counts: Record<string, number>;
  active: string;
  onSelect: (id: string) => void;
  onSaved: (d: BoardDepartment) => void;
  /** Перечитать строки доски: включение песочницы «по умолчанию» ставит в неё
   *  тех, кто уже на практике, — таблица должна это показать сразу. */
  onRows: () => void;
}) {
  const [editing, setEditing] = useState<BoardDepartment | null>(null);
  const sandboxes = sandboxTabs(departments);

  const tab = (id: string, text: string, d?: BoardDepartment) => (
    <div key={id} className={clsx("hf-statuses-tab", active === id && "hf-statuses-tab-active")}>
      <button className="hf-statuses-tab-btn" onClick={() => onSelect(id)} title={text}>
        <span>{text}</span>
        <span className="hf-statuses-tab-count">{counts[id] ?? 0}</span>
      </button>
      {d && (
        <button
          className="hf-statuses-tab-edit"
          title="Настройки песочницы: кому видна, по умолчанию"
          onClick={() => setEditing(d)}
        >
          <Pencil size={11} />
        </button>
      )}
    </div>
  );

  return (
    <div className="hf-statuses-tabs">
      {tab("all", "Все")}
      {sandboxes.map((d) => tab(String(d.id), d.name, d))}
      {editing && (
        <DepartmentModal
          dept={editing}
          departments={departments}
          orgHr={orgHr}
          onClose={() => setEditing(null)}
          onSaved={(d) => {
            onSaved(d);
            if (d.placed_now) {
              toast.success(`Практиканты без отдела переехали в «${d.name}»: ${d.placed_now}`);
              onRows();
            }
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

/** Какие отделы предлагать в фильтре «Отдел»: песочницы и отделы из списка
 *  владельца — те же, что в переводе. Старые отделы вне списка не
 *  предлагаются (решение владельца 09.11.2026). */
export function departmentFilterNames(departments: BoardDepartment[]): string[] {
  return departments
    .filter((d) => d.kind === "sandbox" || d.offered)
    .map((d) => d.name);
}

/** Песочницы для вкладок — в порядке, в котором их отдаёт сервер; скрытые
 *  не показываем. */
export function sandboxTabs(departments: BoardDepartment[]): BoardDepartment[] {
  return departments.filter((d) => d.kind === "sandbox" && !d.hidden);
}

/** Тип поля — значок слева в панели «Поля», как в ClickUp (клиент, 11.11.2026:
 *  «значки показывают тип сущности: дропдаун, дата, текст»). */
const FIELD_TYPE: Record<string, "name" | "person" | "dropdown" | "text" | "date" | "file"> = {
  name: "name", assignee: "person", sourcer: "dropdown", position: "dropdown",
  department: "dropdown", telegram: "text", practice_start_date: "date", manager: "dropdown",
  offer: "file", department_start_date: "date", dept_done: "dropdown", w2: "date",
  w2_done: "dropdown", m1: "date", m1_done: "dropdown", m3: "date", m3_done: "dropdown",
  y1: "date", y1_done: "dropdown", dismissal_date: "date", rejection_reason: "text",
};

function FieldTypeIcon({ k }: { k: string }) {
  const cf = customFieldOf(k);
  if (cf?.type === "number") return <Hash size={16} className="hf-fields-ico-text" />;
  if (cf?.type === "checkbox") return <CheckSquare size={16} className="hf-fields-ico-drop" />;
  const t = cf ? ({ text: "text", date: "date", select: "dropdown" } as const)[cf.type as "text" | "date" | "select"]
    : (FIELD_TYPE[k] ?? "text");
  if (t === "name") return <span className="hf-fields-aa">Aa</span>;
  if (t === "person") return <UserIcon size={16} />;
  if (t === "dropdown") return <ChevronDownSquare size={16} className="hf-fields-ico-drop" />;
  if (t === "date") return <Calendar size={16} className="hf-fields-ico-date" />;
  if (t === "file") return <Paperclip size={16} className="hf-fields-ico-file" />;
  return <Type size={16} className="hf-fields-ico-text" />;
}

/** Панель «Поля» по шестерёнке — как в ClickUp (клиент, 11.11.2026): справа,
 *  поиск, «Показаны» и «Скрыты», бегунки. По наведению на строку — ручка
 *  (перетащить: порядок колонок) и карандаш (своё название). Вид общий для
 *  всех HR: выключил колонку — она пропала у всех. «ФИО» не выключается и не
 *  двигается — по нему читается строка, но переименовать его можно. Секций
 *  здесь больше нет: на доске видны все. */
function FieldsPanel({
  view, onToggle, onSave, onShowAll, onClose, onCustomFields,
}: {
  view: BoardView;
  onToggle: (key: string, hide: boolean) => void;
  onSave: (patch: Partial<BoardView>) => void;
  onShowAll: () => void;
  onClose: () => void;
  onCustomFields: (list: CustomField[]) => void;
}) {
  // Вкладки как в ClickUp: «Добавить существующее» (список полей) и «Создать
  // новое» — своё поле (клиент, 11.11.2026).
  const [tab, setTab] = useState<"existing" | "new">("existing");
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<CustomFieldType>("text");
  const [busy, setBusy] = useState(false);
  const fail = (e: any, msg: string) => toast.error(e?.response?.data?.detail || msg);
  const create = async () => {
    const name = newName.trim();
    if (!name || busy) return;
    setBusy(true);
    try {
      onCustomFields(await createCustomField(name, newType));
      setNewName("");
      setTab("existing");
      toast.success(`Поле «${name}» добавлено — оно уже в таблице`);
    } catch (e) { fail(e, "Не удалось создать поле"); } finally { setBusy(false); }
  };
  const removeCustom = async (key: string) => {
    const cf = customFieldOf(key);
    if (!cf) return;
    try {
      onCustomFields(await deleteCustomField(cf.id));
      toast.success(`Поле «${cf.name}» удалено`);
    } catch (e) { fail(e, "Не удалось удалить поле"); }
  };
  const [q, setQ] = useState("");
  const [renaming, setRenaming] = useState<{ key: string; text: string } | null>(null);
  const [dragKey, setDragKey] = useState<string | null>(null);
  const [overKey, setOverKey] = useState<string | null>(null);
  const needle = q.trim().toLowerCase();
  const all = arrangeColumns(view, true);
  const match = (c: (typeof COLUMNS)[number]) => !needle || fieldLabel(c.key).toLowerCase().includes(needle);
  const shown = all.filter((c) => (c.key === "name" || !view.hidden.includes(c.key)) && match(c));
  const off = all.filter((c) => c.key !== "name" && view.hidden.includes(c.key) && match(c));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !renaming) onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, renaming]);

  const saveRename = () => {
    if (!renaming) return;
    const text = renaming.text.trim().replace(/\s+/g, " ");
    // Своё поле переименовываем в нём самом, а не подписью вида.
    const cf = customFieldOf(renaming.key);
    if (cf) {
      setRenaming(null);
      if (text && text !== cf.name) {
        updateCustomField(cf.id, { name: text }).then(onCustomFields)
          .catch((e) => fail(e, "Не удалось переименовать поле"));
      }
      return;
    }
    const labels = { ...view.labels };
    const base = COLUMNS.find((c) => c.key === renaming.key);
    const deflt = FILTER_LABELS[renaming.key as FilterKey] || base?.label || "";
    if (!text || text === deflt) delete labels[renaming.key]; else labels[renaming.key] = text;
    setRenaming(null);
    onSave({ labels });
  };

  /** Перетащили строку на другую — ставим перед ней. Порядок общий. */
  const drop = (target: string) => {
    const from = dragKey;
    setDragKey(null);
    setOverKey(null);
    if (!from || from === target || target === "name") return;
    const keys = all.map((c) => c.key as string).filter((k) => k !== "name" && k !== from);
    keys.splice(keys.indexOf(target), 0, from);
    onSave({ order: keys });
  };

  const row = (c: (typeof COLUMNS)[number], on: boolean) => {
    const locked = c.key === "name";
    const custom = !!view.labels[c.key];
    return (
      <div
        key={c.key}
        className={clsx(
          "hf-fields-row",
          locked && "is-locked",
          dragKey === c.key && "is-dragging",
          overKey === c.key && dragKey !== c.key && "is-over",
        )}
        draggable={!locked && on && !renaming}
        onDragStart={() => setDragKey(c.key)}
        onDragEnd={() => { setDragKey(null); setOverKey(null); }}
        onDragOver={(e) => { if (dragKey && on && !locked) { e.preventDefault(); setOverKey(c.key); } }}
        onDrop={(e) => { e.preventDefault(); drop(c.key); }}
      >
        <span className="hf-fields-grip">{!locked && on && <GripVertical size={14} />}</span>
        <span className="hf-fields-ico"><FieldTypeIcon k={c.key} /></span>
        {renaming?.key === c.key ? (
          <input
            autoFocus
            className="hf-fields-rename"
            value={renaming.text}
            onChange={(e) => setRenaming({ key: c.key, text: e.target.value })}
            onBlur={saveRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") saveRename();
              if (e.key === "Escape") setRenaming(null);
            }}
          />
        ) : (
          <span className="hf-fields-name" title={custom ? `Своё название. Было: ${COLUMNS.find((x) => x.key === c.key)?.label}` : undefined}>
            {fieldLabel(c.key)}
            {customFieldOf(c.key) && <span className="hf-fields-own">своё</span>}
          </span>
        )}
        {renaming?.key !== c.key && (
          <button
            type="button"
            className="hf-fields-edit"
            title="Переименовать поле (у всех)"
            onClick={() => setRenaming({ key: c.key, text: fieldLabel(c.key) })}
          >
            <Pencil size={13} />
          </button>
        )}
        {customFieldOf(c.key) && renaming?.key !== c.key && (
          <button
            type="button"
            className="hf-fields-edit"
            title="Удалить своё поле"
            onClick={() => removeCustom(c.key)}
          >
            <Trash2 size={13} />
          </button>
        )}
        <input
          type="checkbox"
          role="switch"
          className="hf-fields-switch"
          checked={on}
          disabled={locked}
          title={locked ? "ФИО видно всегда" : on ? "Скрыть у всех" : "Показать у всех"}
          onChange={() => onToggle(c.key, on)}
        />
      </div>
    );
  };

  return (
    <aside className="hf-fields-panel" aria-label="Поля">
      <div className="hf-fields-head">
        <h3>Поля</h3>
        <button className="hf-statuses-folder-action" onClick={onClose} title="Закрыть">
          <X size={16} />
        </button>
      </div>
      <div className="hf-fields-tabs">
        <button type="button" className={clsx(tab === "new" && "is-on")} onClick={() => setTab("new")}>
          Создать новое
        </button>
        <button type="button" className={clsx(tab === "existing" && "is-on")} onClick={() => setTab("existing")}>
          Добавить существующее
        </button>
      </div>
      {tab === "new" ? (
        <div className="hf-fields-create">
          <label>
            Название
            <input
              autoFocus
              className="hf-fields-search"
              placeholder="Например, «Грейд»"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") create(); }}
            />
          </label>
          <div className="hf-fields-types">
            {([
              ["select", "Выпадающий список"], ["text", "Текст"], ["date", "Дата"],
              ["number", "Число"], ["checkbox", "Флажок"],
            ] as [CustomFieldType, string][]).map(([t, label]) => (
              <button
                key={t}
                type="button"
                className={clsx("hf-fields-row", newType === t && "is-on")}
                onClick={() => setNewType(t)}
              >
                <span className="hf-fields-ico">
                  {t === "select" ? <ChevronDownSquare size={16} className="hf-fields-ico-drop" />
                    : t === "date" ? <Calendar size={16} className="hf-fields-ico-date" />
                      : t === "number" ? <Hash size={16} className="hf-fields-ico-text" />
                        : t === "checkbox" ? <CheckSquare size={16} className="hf-fields-ico-drop" />
                          : <Type size={16} className="hf-fields-ico-text" />}
                </span>
                <span className="hf-fields-name">{label}</span>
              </button>
            ))}
          </div>
          <button type="button" className="hf-fields-reset hf-fields-create-btn" disabled={!newName.trim() || busy} onClick={create}>
            Создать поле
          </button>
          <div className="hf-fields-note">Поле появится у всех HR. Значения заполняются прямо в таблице.</div>
        </div>
      ) : (<>
      <input
        autoFocus
        className="hf-fields-search"
        placeholder="Найти поле"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="hf-fields-note">
        Вид общий: что выключите, переставите или переименуете — изменится у всех HR.
      </div>
      <div className="hf-fields-list">
        <div className="hf-fields-group">
          <span>Показаны</span><span>{shown.length}</span>
        </div>
        {shown.map((c) => row(c, true))}
        <div className="hf-fields-group">
          <span>Скрыты</span><span>{off.length}</span>
        </div>
        {off.length === 0 && <div className="hf-fields-empty">Скрытых полей нет</div>}
        {off.map((c) => row(c, false))}
      </div>
      {(view.hidden.length > 0 || view.order.length > 0 || Object.keys(view.labels).length > 0
        || Object.keys(view.widths).length > 0) && (
        <div className="hf-fields-foot">
          {view.hidden.length > 0 && (
            <button className="hf-fields-reset" onClick={onShowAll}>Показать все поля</button>
          )}
          <button
            className="hf-fields-reset"
            title="Вернуть исходные порядок, названия и ширины (у всех)"
            onClick={() => onSave({ order: [], labels: {}, widths: {} })}
          >
            Порядок и названия как было
          </button>
        </div>
      )}
      </>)}
    </aside>
  );
}

/** Окно выгрузки: кого и что класть в книгу.
 *
 *  Секции и колонки — тот же выбор, что в «Виде» (владелец, 11.11.2026), по
 *  умолчанию отмечено то, что сейчас на экране. Месяцы и вехи — по листу на
 *  каждый: «мне бы хотелось за месяц, за два месяца, за три месяца работы, за
 *  год работы» (Мария, 07.10.2026); не отмечены — один лист. Выбор в окне
 *  разовый: «Вид» вкладки он не меняет. */
function ExportModal({
  months, hideable, order, sections, columns, onClose, onExport,
}: {
  months: { label: string; from: string; to: string }[];
  hideable: typeof COLUMNS;
  /** Колонки в порядке общего вида — в окне идут так же, как на доске. */
  order: typeof COLUMNS;
  sections: string[];
  columns: string[];
  onClose: () => void;
  onExport: (plan: ExportPlan, pick: ExportPick) => void;
}) {
  const [keys, setKeys] = useState<string[]>(sections);
  const [cols, setCols] = useState<string[]>(columns);
  const [picked, setPicked] = useState<string[]>([]);
  const [marks, setMarks] = useState<MilestoneKey[]>([]);
  const toggle = <T,>(list: T[], v: T) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  return (
    <div className="hf-statuses-modal-back" onClick={onClose}>
      <div className="hf-statuses-modal hf-statuses-modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="hf-statuses-modal-head">
          <h3>Выгрузка</h3>
          <button className="hf-statuses-folder-action" onClick={onClose} title="Закрыть">
            <X size={16} />
          </button>
        </div>

        <div className="hf-statuses-modal-label">
          Секции
          <span className="hf-statuses-modal-note">
            Только для этой выгрузки — «Вид» вкладки не меняется.
          </span>
          {STATUSES.map((st) => (
            <label key={st.key} className="hf-statuses-modal-check">
              <input
                type="checkbox"
                checked={keys.includes(st.key)}
                onChange={() => setKeys((cur) => toggle(cur, st.key))}
              />
              {st.label}
            </label>
          ))}
        </div>

        <div className="hf-statuses-modal-label">
          Колонки
          <span className="hf-statuses-modal-note">
            «ФИО» и «Статус» попадают в файл всегда.
          </span>
          <div className="hf-statuses-view-cols">
            {order.filter((c) => hideable.some((h) => h.key === c.key)).map((c) => (
              <label key={c.key} className="hf-statuses-modal-check">
                <input
                  type="checkbox"
                  checked={cols.includes(c.key)}
                  onChange={() => setCols((cur) => toggle(cur, c.key))}
                />
                {fieldLabel(c.key)}
              </label>
            ))}
          </div>
        </div>

        <div className="hf-statuses-modal-label">
          Месяцы выхода в отдел
          <span className="hf-statuses-modal-note">
            Необязательно. Каждый — отдельным листом книги.
          </span>
          <div className="hf-statuses-export-months">
            {months.map((m) => (
              <button
                key={m.label}
                type="button"
                className={clsx("hf-statuses-preset", picked.includes(m.label) && "is-on")}
                onClick={() => setPicked((cur) => toggle(cur, m.label))}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        <div className="hf-statuses-modal-label">
          Вехи стажа
          <span className="hf-statuses-modal-note">
            Необязательно. Кто доходит до вехи в выбранные месяцы; месяцы не отмечены — за всё время.
          </span>
          {MILESTONES.map((m) => (
            <label key={m.key} className="hf-statuses-modal-check">
              <input
                type="checkbox"
                checked={marks.includes(m.key)}
                onChange={() => setMarks((cur) => toggle(cur, m.key))}
              />
              {m.label}
            </label>
          ))}
        </div>

        <div className="hf-statuses-modal-foot">
          <span className="hf-statuses-modal-note">
            {picked.length || marks.length
              ? "Листы по периодам — из тех, кто сейчас на экране: фильтры учитываются."
              : "Один лист — те, кто сейчас на экране: фильтры и поиск учитываются."}
          </span>
          <button
            className="hf-statuses-modal-save"
            onClick={() => onExport({ months: picked, marks }, { sections: keys, columns: cols })}
            disabled={!keys.length}
            title={keys.length ? "" : "Отметьте хотя бы одну секцию"}
          >
            <Download size={14} />
            Выгрузить
          </button>
        </div>
      </div>
    </div>
  );
}

/** Окно отдела: название, роль и кому он виден.
 *
 *  Роль — песочница или команда внутри неё (решение владельца 30.09.2026):
 *  песочницы (SANDBOX, SANDBOX MOBILE, SANDBOX R&D) — это практика, команды
 *  (Facebook, Google, SEO…) живут внутри них. Видимость: админы видят все
 *  отделы всегда, рекрутёрам — только «виден всем» и те, где их назвали. */
function DepartmentModal({
  dept, departments, orgHr, onClose, onSaved,
}: {
  dept: BoardDepartment | null;
  departments: BoardDepartment[];
  orgHr: { user_id: number; user_name: string | null }[];
  onClose: () => void;
  onSaved: (d: BoardDepartment, created: boolean) => void;
}) {
  const [name, setName] = useState(dept?.name ?? "");
  const [kind, setKind] = useState<"sandbox" | "team">(dept?.kind ?? "team");
  const [parentId, setParentId] = useState<number | null>(dept?.parent_id ?? null);
  const [visibility, setVisibility] = useState<"all" | "admins" | "custom">(dept?.visibility ?? "all");
  const [visibleTo, setVisibleTo] = useState<number[]>(dept?.visible_to ?? []);
  // Песочница по умолчанию: куда вести с практики, если у воронки своя не
  // выбрана. Без этого отдел не проставлялся никому, пока HR не пройдёт по
  // всем воронкам (владелец, 01.10.2026).
  const [isDefault, setIsDefault] = useState(dept?.is_default ?? false);
  const [busy, setBusy] = useState(false);

  const sandboxes = departments.filter((d) => d.kind === "sandbox" && d.id !== dept?.id);
  const defaultName = departments.find((d) => d.is_default && d.id !== dept?.id)?.name;

  const toggle = (id: number) =>
    setVisibleTo((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  const save = async () => {
    const clean = name.trim().replace(/\s+/g, " ");
    if (!clean || busy) return;
    const same = departments.find(
      (d) => d.id !== dept?.id && d.name.trim().toLowerCase() === clean.toLowerCase()
    );
    if (same) {
      toast(`Отдел «${same.name}» уже есть`);
      return;
    }
    const body = {
      kind,
      parent_id: kind === "sandbox" ? null : parentId,
      visibility,
      visible_to: visibility === "custom" ? visibleTo : [],
      is_default: kind === "sandbox" ? isDefault : false,
    };
    setBusy(true);
    try {
      if (dept) {
        onSaved(await updateBoardDepartment(dept.id, { name: clean, ...body }), false);
        toast.success(`Отдел «${clean}» сохранён`);
      } else {
        onSaved(await createBoardDepartment(clean, body), true);
        toast.success(`Отдел «${clean}» создан`);
      }
    } catch (e: any) {
      toast.error(
        e?.response?.status === 403
          ? "Менять отделы может только владелец организации"
          : e?.response?.data?.detail || "Не удалось сохранить отдел"
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="hf-statuses-modal-back" onClick={onClose}>
      <div className="hf-statuses-modal" onClick={(e) => e.stopPropagation()}>
        <div className="hf-statuses-modal-head">
          <h3>{dept ? "Отдел" : "Новый отдел"}</h3>
          <button className="hf-statuses-folder-action" onClick={onClose} title="Закрыть">
            <X size={16} />
          </button>
        </div>

        <label className="hf-statuses-modal-label">
          Название
          <input
            autoFocus
            className="hf-statuses-modal-input"
            value={name}
            maxLength={100}
            placeholder="Например, Facebook или SANDBOX MOBILE"
            disabled={busy}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") save(); }}
          />
        </label>

        <div className="hf-statuses-modal-label">
          Роль
          <label className="hf-statuses-modal-radio">
            <input
              type="radio"
              checked={kind === "sandbox"}
              disabled={busy}
              onChange={() => setKind("sandbox")}
            />
            <span>
              Песочница — практика
              <em>Сюда попадают с практики; из неё людей добавляют в команды.</em>
            </span>
          </label>
          <label className="hf-statuses-modal-radio">
            <input
              type="radio"
              checked={kind === "team"}
              disabled={busy}
              onChange={() => setKind("team")}
            />
            <span>
              Отдел внутри песочницы
              <em>Facebook, Google, SEO — команда, куда выходят с практики.</em>
            </span>
          </label>
          {kind === "team" && (
            <select
              className="hf-statuses-modal-input"
              value={parentId ?? ""}
              disabled={busy}
              onChange={(e) => setParentId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Песочница не выбрана</option>
              {sandboxes.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          )}
          {kind === "sandbox" && (
            <label className="hf-statuses-modal-check">
              <input
                type="checkbox"
                checked={isDefault}
                disabled={busy}
                onChange={() => setIsDefault((v) => !v)}
              />
              Сюда ведёт практика по умолчанию
              {defaultName && !isDefault && (
                <em className="hf-statuses-modal-note">сейчас это «{defaultName}»</em>
              )}
            </label>
          )}
        </div>

        <div className="hf-statuses-modal-label">
          Кому виден
          <label className="hf-statuses-modal-radio">
            <input
              type="radio"
              checked={visibility === "all"}
              disabled={busy}
              onChange={() => setVisibility("all")}
            />
            <span>Всем HR</span>
          </label>
          {/* Выбор из двух: списка людей больше нет (Мария, 07.10.2026 — «не
              будет всего этого списка, а будет либо всем, либо только вам»).
              Третий вариант показываем, только если он уже стоял у отдела. */}
          <label className="hf-statuses-modal-radio">
            <input
              type="radio"
              checked={visibility === "admins"}
              disabled={busy}
              onChange={() => setVisibility("admins")}
            />
            <span>
              Только администраторам
              <em>Настя и Мария видят все отделы всегда.</em>
            </span>
          </label>
          {dept?.visibility === "custom" && (
            <label className="hf-statuses-modal-radio">
              <input
                type="radio"
                checked={visibility === "custom"}
                disabled={busy}
                onChange={() => setVisibility("custom")}
              />
              <span>
                Выбранным сотрудникам
                <em>Старая настройка этого отдела.</em>
              </span>
            </label>
          )}
          {visibility === "custom" && (
            <div className="hf-statuses-modal-people">
              {orgHr.length === 0 && <span className="hf-statuses-empty-cell">Список HR не загрузился</span>}
              {orgHr.map((p) => (
                <label key={p.user_id} className="hf-statuses-modal-check">
                  <input
                    type="checkbox"
                    checked={visibleTo.includes(p.user_id)}
                    disabled={busy}
                    onChange={() => toggle(p.user_id)}
                  />
                  {p.user_name || `#${p.user_id}`}
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="hf-statuses-modal-foot">
          <button className="hf-statuses-modal-cancel" onClick={onClose} disabled={busy}>Отмена</button>
          <button className="hf-statuses-modal-save" onClick={save} disabled={busy || !name.trim()}>
            {busy ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
            {dept ? "Сохранить" : "Создать"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// ROW
// ============================================================

function Row({
  row, columns, departments, onDepartments, onCustomFields, catalogs, onCatalog,
  people, sourcerTags, onSourcerTags, saving,
  onPatch, onStatus, onPlace, onUnplace, onReload,
}: {
  row: BoardRow;
  /** Колонки, которые показывает ЭТОТ пользователь на этой вкладке. */
  columns: typeof COLUMNS;
  departments: BoardDepartment[];
  onDepartments: (update: (cur: BoardDepartment[]) => BoardDepartment[]) => void;
  onCustomFields: (list: CustomField[]) => void;
  catalogs: Record<CatalogKind, CatalogItem[]>;
  onCatalog: (kind: CatalogKind, list: CatalogItem[]) => void;
  people: { user_id: number; user_name: string | null }[];
  sourcerTags: Tag[];
  onSourcerTags: (update: (list: Tag[]) => Tag[]) => void;
  saving: boolean;
  onPatch: (row: BoardRow, body: BoardRowUpdate) => Promise<void>;
  onStatus: (row: BoardRow, status: string) => Promise<void>;
  onPlace: (row: BoardRow, deptId: number) => Promise<void>;
  onUnplace: (row: BoardRow) => Promise<void>;
  onReload: () => void;
}) {
  const date = (key: "practice_start_date" | "department_start_date" | "w2" | "m1" | "m3" | "y1" | "dismissal_date",
                auto?: boolean) => (
    <DateCell value={row[key]} auto={auto} onSave={(v) => onPatch(row, { [key]: v } as BoardRowUpdate)} />
  );
  const choice = (kind: CatalogKind, value: string | null, save: (v: string | null) => void,
                  look: "pill" | "mark" = "pill") => (
    <ChoiceCell
      kind={kind}
      value={value}
      look={look}
      catalog={catalogs[kind]}
      onCatalog={(list) => onCatalog(kind, list)}
      onSave={save}
      onReload={onReload}
    />
  );
  const mark = (key: "dept_done" | "w2_done" | "m1_done" | "m3_done" | "y1_done") =>
    choice("marks", row[key], (v) => onPatch(row, { [key]: v } as BoardRowUpdate), "mark");

  // Ячейки заведены по ключу колонки, а рисуются по списку видимых: колонки
  // прячутся лично и по вкладкам (просьба Марии 08.10.2026 — «лист-вью не
  // только по статусам, но и по столбцам»), и порядок задаёт один COLUMNS.
  const cells: Partial<Record<(typeof COLUMNS)[number]["key"], ReactNode>> = {
    name: (
      // Всё в одну строку: раньше имя, статус и направление шли друг под
      // другом, строка вырастала втрое и таблицу «трясло» при листании.
      <div className="hf-statuses-name-controls">
        {/* Имя — ссылка на карточку в «Все кандидаты»: кандидат и сотрудник —
            одна запись, вся история (резюме, воронки, комментарии) там. */}
        {/* Статус — цветной кружок перед именем, как в ClickUp (этап 6,
            11.11.2026): строка в одну линию. Клик — прежний выбор статуса
            (прозрачный select поверх кружка). Смена статуса прямо в строке:
            раньше перевести человека из «Практики» в «Уволен» через
            интерфейс было нельзя вообще. */}
        <span
          className={clsx("hf-statuses-dot", `hf-statuses-dot-${groupOf(row.status)}`)}
          // В «Уволен» лежат ещё «Отказ» и «Отозван» — точный статус
          // показываем подсказкой.
          title={`Статус: ${(STATUS_LABELS as Record<string, string>)[row.status] || row.status} — нажмите, чтобы сменить`}
        >
          <select
            className="hf-statuses-dot-select"
            value={groupOf(row.status)}
            aria-label="Статус"
            onChange={(e) => {
              // Уже в этой группе — повторный выбор ничего не меняет, иначе
              // «отказ» молча переписался бы в «уволен».
              if (e.target.value !== groupOf(row.status)) onStatus(row, e.target.value);
            }}
          >
            {STATUSES.map((st) => (
              <option key={st.key} value={st.key}>{st.label}</option>
            ))}
          </select>
        </span>
        <Link
          to={`/all-candidates?entity=${row.entity_id}`}
          className="hf-statuses-name hf-statuses-name-link"
          title={`${row.name} — открыть карточку в «Все кандидаты»`}
        >
          {row.name}
        </Link>
      </div>
    ),
    assignee: (
      <AssigneeCell
        row={row}
        people={people}
        onSave={(ids) => onPatch(row, { assignee_user_ids: ids })}
      />
    ),
    sourcer: <SourcerCell row={row} catalog={sourcerTags} onCatalog={onSourcerTags} onReload={onReload} />,
    // Должность — только из списка владельца (09.11.2026): должности отдела
    // человека, а без отдела — все, по отделам.
    position: choice("positions", row.position, (v) => onPatch(row, { position: v })),
    department: (
      <DepartmentCell
        row={row}
        departments={departments}
        onDepartments={onDepartments}
        onPlace={(id) => onPlace(row, id)}
        onUnplace={() => onUnplace(row)}
        onReload={onReload}
      />
    ),
    telegram: <TelegramCell value={row.telegram} onSave={(v) => onPatch(row, { telegram: v })} />,
    practice_start_date: date("practice_start_date"),
    manager: choice("managers", row.manager, (v) => onPatch(row, { manager: v })),
    offer: <OfferCell row={row} onReload={onReload} />,
    department_start_date: date("department_start_date"),
    dept_done: mark("dept_done"),
    w2: date("w2", row.w2_auto),
    w2_done: mark("w2_done"),
    m1: date("m1", row.m1_auto),
    m1_done: mark("m1_done"),
    m3: date("m3", row.m3_auto),
    m3_done: mark("m3_done"),
    y1: date("y1", row.y1_auto),
    y1_done: mark("y1_done"),
    dismissal_date: date("dismissal_date"),
    rejection_reason: (
      <ReasonCell
        value={row.rejection_reason ?? null}
        onSave={(v) => onPatch(row, { rejection_reason: v })}
      />
    ),
  };

  return (
    <tr className={clsx("hf-statuses-row", saving && "hf-statuses-row-saving")}>
      {columns.map((c) => (
        <td
          key={c.key}
          className={clsx(
            "hf-statuses-td",
            c.key === "name" && "hf-statuses-sticky",
            c.key === "assignee" && "hf-statuses-td-assignee",
            c.narrow && "hf-statuses-td-narrow",
          )}
        >
          {cells[c.key as keyof typeof cells] ?? (customFieldOf(c.key) && (
            <CustomCell
              field={customFieldOf(c.key)!}
              value={row.custom?.[customFieldOf(c.key)!.id]}
              onSave={(v) => onPatch(row, { custom: { [customFieldOf(c.key)!.id]: v } })}
              onFields={onCustomFields}
            />
          ))}
        </td>
      ))}
    </tr>
  );
}


// ============================================================
// CELLS
// ============================================================

/** Ячейка своего поля — по его типу (11.11.2026). Выпадающий список — то же
 *  окно «как в ClickUp», варианты добавляются, переименовываются и удаляются
 *  прямо в нём; остальные типы — обычные ячейки доски. */
function CustomCell({
  field, value, onSave, onFields,
}: {
  field: CustomField;
  value: string | number | boolean | undefined;
  onSave: (v: string | number | boolean | null) => void;
  onFields: (list: CustomField[]) => void;
}) {
  const menu = useCellMenu();
  const fail = (e: any, msg: string) => toast.error(e?.response?.data?.detail || msg);
  if (field.type === "checkbox") {
    return (
      <button
        type="button"
        className={clsx("hf-statuses-cf-check", value && "is-on")}
        title={value ? "Снять" : "Отметить"}
        onClick={() => onSave(value ? null : true)}
      >
        {value ? <Check size={14} /> : null}
      </button>
    );
  }
  if (field.type === "date") {
    return <DateCell value={value ? String(value) : null} onSave={(v) => onSave(v)} />;
  }
  if (field.type === "number") {
    return <TextCell value={value === undefined ? null : String(value)} onSave={(v) => onSave(v)} />;
  }
  if (field.type === "text") {
    return <TextCell value={value ? String(value) : null} onSave={(v) => onSave(v)} />;
  }
  const v = value ? String(value) : null;
  return (
    <>
      <button
        ref={menu.plusRef}
        className={v ? "hf-statuses-pill" : "hf-statuses-empty-cell"}
        onClick={menu.toggle}
        style={v ? valuePill(`cf:${field.id}`, v, v) : undefined}
        title={v || `Выбрать: ${field.name}`}
      >
        {v || "—"}
      </button>
      {menu.open && menu.pos && (
        <CatalogPicker
          menuRef={menu.menuRef}
          pos={menu.pos}
          placeholder={`Найти или добавить вариант…`}
          groups={[{
            label: field.name,
            options: orderByMeta(`cf:${field.id}`, field.options, (o) => o)
              .map((o) => ({ key: o, label: o, editable: true, color: metaColor(`cf:${field.id}`, o) })),
          }]}
          {...metaHandlers(`cf:${field.id}`)}
          taken={field.options}
          current={v}
          onClear={v ? () => { menu.close(); onSave(null); } : undefined}
          onPick={(key) => { menu.close(); if (key !== v) onSave(key); }}
          onAdd={async (name) => {
            menu.close();
            try {
              onFields(await updateCustomField(field.id, { options: [...field.options, name] }));
              onSave(name);
            } catch (e) { fail(e, `Не удалось добавить «${name}»`); }
          }}
          onRename={async (key, name) => {
            try {
              onFields(await updateCustomField(field.id, { rename_option: { from: key, to: name } }));
              await reloadMetaAfterRename();
              if (key === v) onSave(name);
            } catch (e) { fail(e, "Не удалось переименовать"); }
          }}
          onDelete={async (key) => {
            try {
              onFields(await updateCustomField(field.id, { options: field.options.filter((o) => o !== key) }));
            } catch (e) { fail(e, `Не удалось удалить «${key}»`); }
          }}
        />
      )}
    </>
  );
}

function TextCell({
  value, onSave, prefix,
}: { value: string | null; onSave: (v: string | null) => void; prefix?: string }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");

  useEffect(() => { setDraft(value || ""); }, [value]);

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (next !== (value || "")) onSave(next || null);
  };

  if (editing) {
    return (
      <input
        autoFocus
        className="hf-statuses-cell-input"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") { setDraft(value || ""); setEditing(false); }
        }}
      />
    );
  }

  return (
    <button className="hf-statuses-cell-btn" onClick={() => setEditing(true)} title={value || ""}>
      {value
        ? `${prefix || ""}${value}`
        : <span className="hf-statuses-cell-placeholder">—</span>}
    </button>
  );
}

/** «Причина отказа» — текст в несколько строк: правится многострочным полем
 *  (однострочное склеило бы строки при первом же клике). Сохраняется по уходу
 *  из поля или ⌘/Ctrl+Enter, Escape — отмена. */
function ReasonCell({
  value, onSave,
}: { value: string | null; onSave: (v: string | null) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");

  useEffect(() => { setDraft(value || ""); }, [value]);

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (next !== (value || "")) onSave(next || null);
  };

  if (editing) {
    return (
      <textarea
        autoFocus
        rows={3}
        className="hf-statuses-cell-input hf-statuses-cell-textarea"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) commit();
          if (e.key === "Escape") { setDraft(value || ""); setEditing(false); }
        }}
      />
    );
  }

  return (
    <button className="hf-statuses-cell-btn" onClick={() => setEditing(true)} title={value || ""}>
      {value || <span className="hf-statuses-cell-placeholder">—</span>}
    </button>
  );
}

function DateCell({
  value, onSave, auto,
}: { value: string | null; onSave: (v: string | null) => void; auto?: boolean }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <input
        autoFocus
        type="date"
        className="hf-statuses-cell-input"
        defaultValue={value || ""}
        onBlur={(e) => {
          setEditing(false);
          const next = e.target.value || null;
          if (next !== value) onSave(next);
        }}
        onKeyDown={(e) => { if (e.key === "Escape") setEditing(false); }}
      />
    );
  }

  return (
    <button
      className={clsx("hf-statuses-cell-btn", auto && value && "hf-statuses-cell-auto")}
      onClick={() => setEditing(true)}
      title={auto && value ? "Посчитано от даты выхода в отдел — нажми, чтобы задать вручную" : ""}
    >
      {value ? fmtShort(value) : <span className="hf-statuses-cell-placeholder">—</span>}
    </button>
  );
}

function OfferCell({ row, onReload }: { row: BoardRow; onReload: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (file: File) => {
    setBusy(true);
    try {
      await uploadEntityFile(row.entity_id, file, "offer");
      toast.success("Оффер загружен");
      onReload();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось загрузить");
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    if (!row.offer_file_id) return;
    try {
      const blob = await downloadEntityFile(row.entity_id, row.offer_file_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = row.offer_file_name || "offer";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Не удалось скачать");
    }
  };

  const remove = async () => {
    if (!row.offer_file_id) return;
    if (!confirm("Удалить файл оффера?")) return;
    setBusy(true);
    try {
      await deleteEntityFile(row.entity_id, row.offer_file_id);
      onReload();
    } catch {
      toast.error("Не удалось удалить");
    } finally {
      setBusy(false);
    }
  };

  if (busy) return <Loader2 className="animate-spin" size={14} />;

  return (
    <div className="hf-statuses-offer">
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }}
      />
      {row.offer_file_id ? (
        <>
          <button className="hf-statuses-offer-link" onClick={download} title={row.offer_file_name || ""}>
            <Paperclip size={12} />
            <span className="hf-statuses-offer-name">{row.offer_file_name || "файл"}</span>
          </button>
          <button className="hf-statuses-offer-remove" onClick={remove} title="Удалить">
            <X size={12} />
          </button>
        </>
      ) : (
        <button className="hf-statuses-offer-upload" onClick={() => inputRef.current?.click()}>
          <Upload size={12} /> файл
        </button>
      )}
    </div>
  );
}


// ============================================================
// Ячейки, перенесённые из ClickUp
// ============================================================

/** Цвет пилюли выводим из самого текста: одинаковое значение всегда одного
 *  цвета, а новые должности/отделы получают свой без ручной настройки. */

/** Ведущие HR строки; старый ответ бэка без assignees — из одиночного поля. */
const rowAssignees = (r: BoardRow) =>
  r.assignees ?? (r.assignee_user_id != null
    ? [{ user_id: r.assignee_user_id, name: r.assignee_name, auto: !!r.assignee_auto }]
    : []);


/** Кого можно добавить в колонку HR через «+». Решение владельца 21.09.2026:
 *  доску ведут не все HR, остальные в списке мешали. С 15.10.2026 их трое —
 *  «добавь плиз сюда Владу, она есть в базе, у нас 3 HR» (Мария). Сверяем по
 *  первому слову имени (кириллица или латиница), без учёта регистра: «Влада»
 *  и «Влад» (наставник практики) — разные люди и не путаются. Уже назначенных
 *  других HR это не снимает — их кружки остаются. */
const BOARD_HR_FIRST_NAMES = ["мария", "maria", "эльвира", "elvira", "влада", "vlada"];
/** Ротации человека для ячейки «Отдел»: короткая подпись «↻ Продукт» (последний
 *  прежний отдел, «+N» — если их было больше) и вся история подсказкой.
 *  Мария, 05.11.2026: «Виктор сначала был в продукте, а теперь он байер фб —
 *  отметить на борде, но чтобы не было перегруженности». Поэтому не колонка и
 *  не вторая строка, а та же тихая подпись, что и «из SANDBOX». */
export function rotationNote(
  history: BoardTeamStint[] | undefined,
  current: string,
): { short: string; title: string } | null {
  const past = (history ?? []).filter((h) => h.name);
  // Вернулся туда же, где был, — это не ротация. Так бывает после ошибки:
  // SEO → «Тестеровшики QA» (завели по ошибке) → снова SEO; отдел QA удалили,
  // сервер его запись больше не отдаёт, и без этого осталось бы «↻ SEO team»
  // у человека, который в SEO team и сидит (владелец, 11.11.2026).
  while (past.length && current && past[past.length - 1].name === current) past.pop();
  if (!past.length) return null;
  const last = past[past.length - 1];
  const more = past.length > 1 ? ` +${past.length - 1}` : "";
  const lines = past.map((h) => {
    const when = [fmt(h.date_from), fmt(h.date_to)].filter(Boolean).join(" – ");
    return when ? `${h.name} · ${when}` : h.name;
  });
  if (current) lines.push(`Сейчас: ${current}`);
  return { short: `↻ ${last.name}${more}`, title: `Ротации:\n${lines.join("\n")}` };
}

/** Отделы для окна выбора: сначала из списка владельца в его порядке, потом
 *  добавленные HR — по алфавиту. Старые отделы вне списка не предлагаются. */
export function offeredTeams(departments: BoardDepartment[]): BoardDepartment[] {
  return departments
    .filter((d) => d.kind === "team" && d.offered)
    .sort((a, b) =>
      (a.canon_order ?? 99) - (b.canon_order ?? 99) || a.name.localeCompare(b.name, "ru"));
}

export const isBoardHr = (name: string | null | undefined) =>
  BOARD_HR_FIRST_NAMES.includes((name || "").trim().split(/\s+/)[0].toLowerCase());

/** Сколько HR можно закрепить за человеком — как на бэке (MAX_ASSIGNEES). */
const MAX_HR = 5;

const initialsOf = (name: string | null | undefined) =>
  (name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";

/** Отдел — цветная пилюля, как должность: так строки читаются глазами, а не
 *  вычитываются (Мария, 28.09.2026). Под пилюлей прозрачный select — правка
 *  осталась в один клик, а длинное название видно целиком в подсказке.
 *
 *  В строке ПЕСОЧНИЦЫ выбор отдела ДОБАВЛЯЕТ человека в команду: на практике
 *  он остаётся, в команде появляется ещё одна строка (решение владельца
 *  30.09.2026 — «песочница родительский отдел, Facebook дочерний, а человек
 *  один объект»). В строке команды выбор переносит её в другой отдел, а «×»
 *  убирает человека из отдела; из песочницы «×» не предлагаем. */
/** Можно ли убрать человека из отдела этой строки строкой «— убрать из …» в
 *  окне. Из песочницы — только админ (так же проверяет сервер): её ставят по
 *  ошибке, и снять было нечем — «SANDBOX выставлен ошибочно, как убрать?»
 *  (владелец, 11.11.2026). Крестик на ячейке у песочницы по-прежнему не
 *  рисуем: в строке песочницы главной показана команда, и «×» на ней
 *  читался бы как «убрать из команды». */
export const canLeaveDepartment = (
  row: Pick<BoardRow, "placement_id" | "department_is_sandbox">,
  isAdmin: boolean,
) => row.placement_id != null && (!row.department_is_sandbox || isAdmin);

function DepartmentCell({
  row, departments, onDepartments, onPlace, onUnplace, onReload,
}: {
  row: BoardRow;
  departments: BoardDepartment[];
  onDepartments: (update: (cur: BoardDepartment[]) => BoardDepartment[]) => void;
  onPlace: (id: number) => void;
  onUnplace: () => void;
  onReload: () => void;
}) {
  const menu = useCellMenu();
  const isAdmin = useAuthStore((st) =>
    st.user?.role === "superadmin" || st.user?.org_role === "owner" || st.user?.org_role === "admin");
  // Главным в ячейке всегда рабочий отдел — даже в строке песочницы: «нужно
  // видеть отделы везде, даже на сендбоксе» (Мария, 07.10.2026). Под ним —
  // подпись «из <песочницы>»: её убирали 09.10.2026 вместе с вложенностью
  // отделов, но она нужна — «разве мы не должны видеть, из какого санбокса
  // кандидат пришёл?» (Мария, 13.10.2026). Вложенность в сайдбаре при этом
  // осталась убранной: просили вернуть пометку именно в столбце «Отдел».
  const own = row.department_name || "";
  const name = (row.department_is_sandbox ? row.team_name : null) || own;
  const from = row.department_is_sandbox
    ? (row.team_name ? own : null)   // в строке песочницы подпись — она сама
    : row.sandbox_name;
  const rotation = rotationNote(row.team_history, name);
  // Текущий отдел строки в окне ЕСТЬ — с галочкой, как в ClickUp: иначе его
  // нельзя было переименовать или перекрасить из этой строки (11.11.2026).
  // Сравниваем с отделом САМОЙ строки, а не с тем, что показано главным.
  const options = departments.filter((d) => !d.hidden || d.id === row.department_id);
  // Песочница у человека одна: выбрал другую — переехал. Команда из песочницы —
  // наоборот, добавление: практика остаётся.
  const sandboxes = options.filter((d) => d.kind === "sandbox");
  // Перевести можно в отдел из списка владельца или в добавленный HR через
  // это же окно (11.11.2026). Старые отделы вне списка не предлагаются.
  const teams = offeredTeams(options);
  const teamsAdd = row.department_is_sandbox;
  const hint = row.department_id ? "Перевести или добавить в отдел" : "Поставить в отдел";

  return (
    <div className="hf-statuses-dept">
      {name ? (
        /* Главный — рабочий отдел, песочница под ним вторым планом: «видно,
           что он ещё из sandbox» (Мария, 07.10.2026). */
        <span className="hf-statuses-dept-stack">
          <span
            className="hf-statuses-pill"
            title={from ? `${name} · пришёл из ${from}` : name}
            style={valuePill("departments", String(departments.find((d) => d.name === name)?.id ?? ""), name)}
          >
            {name}
          </span>
          {(from || rotation) && (
            /* Одна тихая подпись на всё: «из SANDBOX · ↻ Продукт». */
            <span
              className="hf-statuses-dept-from"
              title={[from && `Остаётся в песочнице ${from}`, rotation?.title].filter(Boolean).join("\n\n")}
            >
              {[from && `из ${from}`, rotation?.short].filter(Boolean).join(" · ")}
            </span>
          )}
        </span>
      ) : (
        <span className="hf-statuses-empty-cell">—</span>
      )}
      {/* Окно «как в ClickUp»: найти, выбрать или добавить свой отдел
          (клиент, 11.11.2026). Кнопка прозрачная и лежит на всей ячейке. */}
      <button
        ref={menu.plusRef}
        type="button"
        className="hf-statuses-dept-select"
        title={hint}
        aria-label={hint}
        onClick={menu.toggle}
      />
      {menu.open && menu.pos && (
        <CatalogPicker
          menuRef={menu.menuRef}
          pos={menu.pos}
          placeholder="Найти или добавить отдел…"
          groups={[
            {
              label: row.department_is_sandbox ? "Песочницы — перевести" : "Песочницы — вернуть на практику",
              options: orderByMeta("departments", sandboxes, (d) => String(d.id)).map((d) => ({
                key: String(d.id), label: d.name, editable: true, noDelete: true,
                color: metaColor("departments", String(d.id)),
              })),
            },
            {
              label: teamsAdd ? "Отделы — добавить (практика останется)" : "Отделы — перевести",
              options: orderByMeta("departments", teams, (d) => String(d.id)).map((d) => ({
                key: String(d.id), label: d.name, editable: true,
                color: metaColor("departments", String(d.id)),
              })),
            },
          ]}
          {...metaHandlers("departments")}
          taken={departments.map((d) => d.name)}
          current={row.department_id != null ? String(row.department_id) : null}
          // Строка «— убрать» сверху, как «–» в ClickUp (клиент, 11.11.2026):
          // то же, что крестик на ячейке, — человек уходит из этого отдела.
          onClear={canLeaveDepartment(row, isAdmin) ? () => { menu.close(); onUnplace(); } : undefined}
          clearLabel={`— убрать из «${row.department_name}»`}
          onPick={(key) => { menu.close(); if (key !== String(row.department_id)) onPlace(Number(key)); }}
          onAdd={async (text) => {
            menu.close();
            try {
              const d = await createBoardDepartment(text, { kind: "team" });
              onDepartments((cur) => (cur.some((x) => x.id === d.id)
                ? cur.map((x) => (x.id === d.id ? d : x)) : [...cur, d]));
              onPlace(d.id);
            } catch (e: any) {
              toast.error(e?.response?.data?.detail || `Не удалось добавить отдел «${text}»`);
            }
          }}
          onRename={async (key, text) => {
            try {
              const d = await updateBoardDepartment(Number(key), { name: text });
              onDepartments((cur) => cur.map((x) => (x.id === d.id ? d : x)));
              onReload();
            } catch (e: any) {
              toast.error(e?.response?.data?.detail || "Не удалось переименовать отдел");
            }
          }}
          onDelete={async (key, label) => {
            try {
              await deleteBoardDepartment(Number(key));
              onDepartments((cur) => cur.filter((x) => String(x.id) !== key));
              toast.success(`Отдел «${label}» удалён`);
            } catch (e: any) {
              toast.error(e?.response?.data?.detail || `Не удалось удалить «${label}»`);
            }
          }}
        />
      )}
      {canLeaveDepartment(row, false) && (
        <button
          type="button"
          className="hf-statuses-dept-remove"
          title={`Убрать из отдела «${name}»`}
          onClick={(e) => { e.stopPropagation(); onUnplace(); }}
        >
          <X size={11} />
        </button>
      )}
    </div>
  );
}

/** Telegram с кнопкой «скопировать»: ник выделяли мышкой вручную, а он ещё и
 *  обрезан в узкой колонке (Мария, 28.09.2026). */
function TelegramCell({
  value, onSave,
}: { value: string | null; onSave: (v: string | null) => void }) {
  const [copied, setCopied] = useState(false);

  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const handle = `@${(value || "").replace(/^@/, "")}`;
    try {
      await navigator.clipboard.writeText(handle);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Браузер не дал скопировать");
    }
  };

  return (
    <div className="hf-statuses-tg">
      <TextCell value={value} prefix="@" onSave={onSave} />
      {value && (
        <button
          className="hf-statuses-tg-copy"
          onClick={copy}
          title={copied ? "Скопировано" : `Скопировать @${value.replace(/^@/, "")}`}
          aria-label="Скопировать ник"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </button>
      )}
    </div>
  );
}

function pillHue(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i += 1) h = (h * 31 + value.charCodeAt(i)) % 360;
  return h;
}


/** Ячейка с выпадающим списком «как в ClickUp» — одна на должность, «Рук-ль»
 *  и отметки у вех (клиент, 11.11.2026: «логика у всех дропдаунов одна, а мы
 *  уже будем наполнять их так, как нам нужно»). В окне — справочник этого
 *  списка: основа + дописанное HR, поиск, «+ Добавить». Своё можно
 *  переименовать (новое имя появится у всех, у кого стоит) и удалить, если
 *  оно ни у кого не стоит. Старое значение не из списка показывается как было. */
const CHOICE_TEXT: Record<CatalogKind, { placeholder: string; group: string; empty: string }> = {
  positions: { placeholder: "Найти или добавить должность…", group: "Должности", empty: "Выбрать должность" },
  managers: { placeholder: "Найти или добавить руководителя…", group: "Руководители", empty: "Выбрать руководителя" },
  marks: { placeholder: "Найти или добавить отметку…", group: "Отметки", empty: "Поставить отметку" },
};

function ChoiceCell({
  kind, value, look, catalog, onCatalog, onSave, onReload,
}: {
  kind: CatalogKind;
  value: string | null;
  look: "pill" | "mark";
  catalog: CatalogItem[];
  onCatalog: (list: CatalogItem[]) => void;
  onSave: (v: string | null) => void;
  onReload: () => void;
}) {
  const menu = useCellMenu();
  const text = CHOICE_TEXT[kind];
  const known = catalog.some((p) => p.name === value);
  const fail = (e: any, msg: string) => toast.error(e?.response?.data?.detail || msg);

  const picker = menu.open && menu.pos && (
    <CatalogPicker
      menuRef={menu.menuRef}
      pos={menu.pos}
      placeholder={text.placeholder}
      groups={[{
        label: text.group,
        options: orderByMeta(kind, catalog, (p) => p.name).map((p) => ({
          key: p.name, label: p.name, editable: !p.locked,
          hint: p.count ? `${p.count} чел.` : undefined,
          color: metaColor(kind, p.name),
          style: look === "mark" ? markStyle(p.name) : undefined,
        })),
      }]}
      {...metaHandlers(kind)}
      taken={catalog.map((p) => p.name)}
      current={value}
      onClear={value ? () => { menu.close(); onSave(null); } : undefined}
      onPick={(key) => { menu.close(); if (key !== value) onSave(key); }}
      onAdd={async (name) => {
        menu.close();
        try {
          onCatalog(await addCatalogItem(kind, name));
          onSave(name);
        } catch (e) { fail(e, `Не удалось добавить «${name}»`); }
      }}
      onRename={async (key, name) => {
        try {
          onCatalog(await renameCatalogItem(kind, key, name));
          await reloadMetaAfterRename();
          onReload();
        } catch (e) { fail(e, "Не удалось переименовать"); }
      }}
      onDelete={async (key) => {
        try {
          onCatalog(await deleteCatalogItem(kind, key));
          toast.success(`«${key}» удалено из списка`);
        } catch (e) { fail(e, `Не удалось удалить «${key}»`); }
      }}
    />
  );

  if (!value) {
    return (
      <>
        <button ref={menu.plusRef} className="hf-statuses-empty-cell" onClick={menu.toggle} title={text.empty}>—</button>
        {picker}
      </>
    );
  }

  return (
    <>
      <button
        ref={menu.plusRef}
        className={look === "mark" ? "hf-statuses-mark-pill hf-statuses-mark-btn" : "hf-statuses-pill"}
        onClick={menu.toggle}
        style={metaColor(kind, value) ? colorPill(metaColor(kind, value)!)
          : look === "mark" ? markStyle(value) : valuePill(kind, value, value)}
        title={known ? value : `${value} — не из списка`}
      >
        {value}
      </button>
      {picker}
    </>
  );
}

type PickerOption = {
  key: string; label: string; editable?: boolean; hint?: string;
  /** Цвет пункта (свой из «…» → «Цвет» или по умолчанию). */
  color?: string;
  /** Готовый стиль пилюли (отметки: зелёная галочка, красный крестик…). */
  style?: React.CSSProperties;
  /** Можно переименовать и перекрасить, но не удалить (песочница). */
  noDelete?: boolean;
};

/** Палитра «Цвет» в «…» — как у выпадающих списков ClickUp. */
const PICKER_COLORS = [
  "#7c3aed", "#2563eb", "#0891b2", "#059669", "#65a30d", "#ca8a04",
  "#ea580c", "#dc2626", "#db2777", "#9333ea", "#475569", "#a16207",
];

/** Стиль пилюли по цвету пункта: светлая заливка, цветной текст. */
export const colorPill = (color: string): React.CSSProperties => ({
  background: `color-mix(in srgb, ${color} 14%, white)`,
  color,
  borderColor: `color-mix(in srgb, ${color} 30%, white)`,
});

/** Одно окно-список «как в ClickUp» на ВСЕ выпадающие списки доски (клиент,
 *  11.11.2026: «у дропдауна должны быть определённые функции, как в ClickUp, и
 *  любой дропдаун будет таким»): поиск, «+ Добавить», «— убрать», у каждого
 *  пункта ручка (перетащить — порядок у всех) и «…» — «Переименовать»,
 *  «Цвет», «Удалить». С selected — несколько значений сразу (сорсеры): сверху
 *  «Выбраны» (клик снимает), ниже остальные (клик ставит). Открывается под
 *  ячейкой поверх доски (useCellMenu: закрытие по клику мимо, Escape и
 *  прокрутке доски). */
export function CatalogPicker({
  menuRef, pos, placeholder, groups, taken, current, selected,
  onPick, onAdd, onRename, onDelete, onClear, clearLabel, onRecolor, onReorder,
}: {
  menuRef: React.RefObject<HTMLDivElement>;
  pos: MenuPos;
  placeholder: string;
  groups: { label: string; options: PickerOption[] }[];
  /** Все существующие названия — «Добавить» не предлагаем, если такое уже есть. */
  taken: string[];
  current?: string | null;
  /** Несколько значений: ключи выбранных. Клик по выбранному — снять. */
  selected?: string[];
  onPick: (key: string) => void;
  onAdd: (text: string) => void;
  onRename: (key: string, text: string) => void;
  onDelete: (key: string, label: string) => void;
  onClear?: () => void;
  /** Подпись строки очистки, если «— убрать» мало (отдел: откуда именно). */
  clearLabel?: string;
  onRecolor?: (key: string, color: string | null) => void;
  /** Новый порядок ключей группы — после перетаскивания. */
  onReorder?: (groupLabel: string, keys: string[]) => void | Promise<void>;
}) {
  const [q, setQ] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  // Меню «…» висит поверх окна (fixed), а не внутри прокручиваемого списка:
  // у нижних пунктов оно уходило под край списка и было не видно (11.11.2026).
  const [menuAt, setMenuAt] = useState<React.CSSProperties>({});
  const [colorFor, setColorFor] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{ key: string; text: string } | null>(null);
  const [drag, setDrag] = useState<{ group: string; key: string } | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const needle = q.trim().toLowerCase();
  const text = q.trim().replace(/\s+/g, " ");
  const canAdd = !!text && !taken.some((t) => t.trim().toLowerCase() === text.toLowerCase());
  const multi = !!selected;
  const chosen = new Set(selected ?? []);
  const all = groups.flatMap((g) => g.options);
  const match = (o: PickerOption) => !needle || o.label.toLowerCase().includes(needle);
  const shown = groups
    .map((g) => ({ ...g, options: g.options.filter((o) => match(o) && !chosen.has(o.key)) }))
    .filter((g) => g.options.length);
  const picked = all.filter((o) => chosen.has(o.key) && match(o));
  // Окно с несколькими значениями после выбора не закрывается, поэтому поиск
  // чистим сами: иначе набранное «Вера» оставалось в поле и прятало весь
  // остальной список — казалось, что прежние сорсеры пропали (11.11.2026).
  const pick = (key: string) => { setQ(""); onPick(key); };
  const add = (name: string) => { setQ(""); onAdd(name); };

  const saveRename = () => {
    if (!renaming) return;
    const next = renaming.text.trim().replace(/\s+/g, " ");
    const opt = all.find((o) => o.key === renaming.key);
    setRenaming(null);
    if (!next || !opt || next === opt.label) return;
    // Порядок по умолчанию считается от названия (список владельца, алфавит),
    // поэтому переименованный пункт уезжал в конец. Перед переименованием
    // запоминаем порядок, который человек сейчас видит (11.11.2026).
    const group = groups.find((g) => g.options.some((o) => o.key === renaming.key));
    // Переименование — только ПОСЛЕ сохранения порядка: оба пишут в одни
    // настройки, и параллельно второй затирал первого.
    const key = renaming.key;
    Promise.resolve(group && onReorder ? onReorder(group.label, group.options.map((o) => o.key)) : undefined)
      .then(() => onRename(key, next));
  };

  const dropOn = (group: string, target: string) => {
    const from = drag;
    setDrag(null);
    setOver(null);
    if (!from || from.group !== group || from.key === target || !onReorder) return;
    const keys = (groups.find((g) => g.label === group)?.options ?? []).map((o) => o.key).filter((k) => k !== from.key);
    keys.splice(keys.indexOf(target), 0, from.key);
    onReorder(group, keys);
  };

  const pill = (o: PickerOption) => (
    <span
      className="hf-statuses-picker-pill"
      style={o.color ? colorPill(o.color) : o.style ?? {
        background: `hsl(${pillHue(o.label)} 70% 94%)`,
        color: `hsl(${pillHue(o.label)} 55% 32%)`,
      }}
    >
      {o.label}
    </span>
  );

  const row = (o: PickerOption, group: string | null, isOn: boolean) => (
    <div
      key={`${group ?? "on"}-${o.key}`}
      className={clsx(
        "hf-statuses-picker-row",
        drag?.key === o.key && "is-dragging",
        over === o.key && drag && drag.key !== o.key && "is-over",
      )}
      draggable={!!group && !!onReorder && !needle && !renaming}
      onDragStart={() => group && setDrag({ group, key: o.key })}
      onDragEnd={() => { setDrag(null); setOver(null); }}
      onDragOver={(e) => { if (drag && group && drag.group === group) { e.preventDefault(); setOver(o.key); } }}
      onDrop={(e) => { e.preventDefault(); if (group) dropOn(group, o.key); }}
    >
      {group && onReorder && !needle && (
        <span className="hf-statuses-picker-grip" title="Потяните, чтобы поменять порядок (у всех)">
          <GripVertical size={13} />
        </span>
      )}
      {renaming?.key === o.key ? (
        <input
          autoFocus
          className="hf-statuses-picker-search"
          value={renaming.text}
          onChange={(e) => setRenaming({ key: o.key, text: e.target.value })}
          onBlur={saveRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") saveRename();
            if (e.key === "Escape") { e.stopPropagation(); setRenaming(null); }
          }}
        />
      ) : (
        <button
          type="button"
          className={clsx("hf-statuses-hr-option", (o.key === current || isOn) && "is-current")}
          title={isOn ? "Нажмите, чтобы снять" : undefined}
          onClick={() => pick(o.key)}
        >
          {pill(o)}
          {o.hint && <span className="hf-statuses-picker-hint">{o.hint}</span>}
          {(isOn || (o.key === current && !multi)) && <Check size={13} className="hf-statuses-picker-hint" />}
        </button>
      )}
      {o.editable && renaming?.key !== o.key && (
        <button
          type="button"
          className="hf-statuses-picker-more"
          title="Переименовать, цвет, удалить"
          onClick={(e) => {
            setColorFor(null);
            if (menuFor === o.key) { setMenuFor(null); return; }
            const r = e.currentTarget.getBoundingClientRect();
            const right = Math.max(8, window.innerWidth - r.right);
            // Снизу места мало (с палитрой меню ~240px) — открываем вверх.
            setMenuAt(r.bottom + 248 > window.innerHeight
              ? { position: "fixed", bottom: window.innerHeight - r.top + 2, right, top: "auto" }
              : { position: "fixed", top: r.bottom + 2, right });
            setMenuFor(o.key);
          }}
        >
          <MoreHorizontal size={14} />
        </button>
      )}
      {menuFor === o.key && (
        <div className="hf-statuses-picker-actions" style={menuAt}>
          <button
            type="button"
            onClick={() => { setMenuFor(null); setRenaming({ key: o.key, text: o.label }); }}
          >
            <Pencil size={12} /> Переименовать
          </button>
          {onRecolor && (
            <button type="button" onClick={() => setColorFor(colorFor === o.key ? null : o.key)}>
              <span className="hf-statuses-picker-swatch" style={{ background: o.color || "#cbd5e1" }} /> Цвет
            </button>
          )}
          {colorFor === o.key && onRecolor && (
            <div className="hf-statuses-picker-palette">
              {PICKER_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={clsx(o.color === c && "is-on")}
                  style={{ background: c }}
                  title={c}
                  onClick={() => { setMenuFor(null); setColorFor(null); onRecolor(o.key, c); }}
                />
              ))}
              <button
                type="button"
                className="is-reset"
                title="Цвет по умолчанию"
                onClick={() => { setMenuFor(null); setColorFor(null); onRecolor(o.key, null); }}
              >
                <X size={11} />
              </button>
            </div>
          )}
          {!o.noDelete && (
            <button
              type="button"
              className="is-danger"
              onClick={() => { setMenuFor(null); onDelete(o.key, o.label); }}
            >
              <Trash2 size={12} /> Удалить
            </button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div
      ref={menuRef}
      className="hf-statuses-hr-menu hf-catalog-picker"
      style={menuBox(pos)}
      onScroll={() => { if (menuFor) { setMenuFor(null); setColorFor(null); } }}
    >
      <input
        ref={searchRef}
        autoFocus
        className="hf-statuses-picker-search"
        placeholder={placeholder}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Enter") return;
          // Точное имя ищем среди ВСЕХ, включая уже выбранные: раньше Enter на
          // имени выбранного сорсера ставил ПЕРВОГО из остальных.
          const exact = all.find((o) => o.label.trim().toLowerCase() === needle);
          const first = shown[0]?.options[0] ?? picked[0];
          if (exact) pick(exact.key);
          else if (canAdd) add(text);
          else if (first) pick(first.key);
        }}
      />
      {/* «Добавить» — сразу под поиском, а не в конце списка: у длинного
          списка она пряталась внизу, и «как добавить отдел — непонятно»
          (владелец, 11.11.2026). */}
      {canAdd && (
        <button type="button" className="hf-statuses-hr-option hf-statuses-picker-add" onClick={() => add(text)}>
          <Plus size={13} /> Добавить «{text}»
        </button>
      )}
      {onClear && !needle && (
        <button type="button" className="hf-statuses-hr-option hf-statuses-picker-clear" onClick={onClear}>
          {clearLabel || "— убрать"}
        </button>
      )}
      {multi && picked.length > 0 && (
        <div>
          <div className="hf-statuses-hr-menu-hint">Выбраны</div>
          {picked.map((o) => row(o, null, true))}
        </div>
      )}
      {shown.map((g) => (
        <div key={g.label}>
          <div className="hf-statuses-hr-menu-hint">{g.label}</div>
          {g.options.map((o) => row(o, g.label, false))}
        </div>
      ))}
      {/* Пока ничего не ввели — видимая подсказка, что новое добавляется
          отсюда же: клик ставит курсор в поиск. */}
      {!needle && (shown.length > 0 || picked.length > 0) && (
        <button
          type="button"
          className="hf-statuses-hr-option hf-statuses-picker-add is-hint"
          onClick={() => searchRef.current?.focus()}
        >
          <Plus size={13} /> Добавить — введите название в поиске
        </button>
      )}
      {!shown.length && !picked.length && !canAdd && (
        <div className="hf-statuses-hr-menu-hint">
          {needle ? "Ничего не найдено" : "Список пуст — начните вводить, чтобы добавить"}
        </div>
      )}
    </div>
  );
}

/** HR и сорсеры человека — кружками с инициалами.
 *
 * Подтягиваются из меток кандидата: «HR: …» (их считает воронка) и метки-
 * сорсеры (кто привёл). Кандидат и сотрудник — одна запись, так что заново
 * вбивать их не нужно.
 *
 * Наведение на кружок меняет инициалы на «×» — снять этого человека. «+»
 * справа — добавить HR. HR после правки хранятся на доске (метки воронки их
 * больше не перебивают); сорсер снимается с самой карточки — это та же метка.
 */
/** Сорсеры человека — СВОЯ колонка, а не довесок к HR.
 *
 *  «Это же не HR, это sourcing»: Мария считает по сорсерам выплаты и хочет
 *  нажать на имя и увидеть всех, кого он вывел (встреча 29.09.2026). Сорсер —
 *  это метка на кандидате, поэтому крестик снимает её с карточки.
 */
/** Выпадашка у «+» в ячейке: меню fixed, закрытие по клику мимо, Escape и
 *  прокрутке. Одна на HR и сорсеров — колонки разные, повадки кнопки одни. */
/** Где открыть окно-список у ячейки. Снизу места мало (нижние строки доски)
 *  — открываем ВВЕРХ, как ClickUp; раньше окно уходило за нижний край экрана
 *  и нижние пункты было не достать (11.11.2026). Высота — по свободному месту. */
type MenuPos = { top?: number; bottom?: number; left: number; maxHeight: number };
const MENU_MAX_H = 360;
export function menuPosFor(r: { top: number; bottom: number; left: number }, vh = window.innerHeight): MenuPos {
  const left = r.left;
  const below = vh - r.bottom - 12;
  const above = r.top - 12;
  if (below >= MENU_MAX_H || below >= above) {
    return { top: r.bottom + 4, left, maxHeight: Math.max(160, Math.min(MENU_MAX_H, below)) };
  }
  return { bottom: vh - r.top + 4, left, maxHeight: Math.max(160, Math.min(MENU_MAX_H, above)) };
}
const menuBox = (pos: MenuPos): React.CSSProperties => ({
  top: pos.top,
  bottom: pos.bottom,
  left: Math.max(8, Math.min(pos.left, window.innerWidth - 288)),
  maxHeight: pos.maxHeight,
});

function useCellMenu() {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<MenuPos | null>(null);
  const plusRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      const t = e.target as Node;
      if (menuRef.current?.contains(t) || plusRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    // Меню fixed — при прокрутке доски оно бы «отстало» от ячейки
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
    };
  }, [open]);

  /** Открыть/закрыть, посчитав место под кнопкой. */
  const toggle = () => {
    if (open) { setOpen(false); return; }
    const r = plusRef.current?.getBoundingClientRect();
    if (r) setPos(menuPosFor(r));
    setOpen(true);
  };

  return { open, pos, plusRef, menuRef, toggle, close: () => setOpen(false) };
}

/** Сорсеры человека — как HR и «Assignees» в ClickUp (клиент, 11.11.2026):
 *  чипы в ячейке, клик по ячейке открывает окно — сверху стоящие (клик снимает),
 *  ниже справочник (клик ставит), поиск и «+ Добавить» нового сорсера. Сорсер —
 *  это метка карточки (getTags), тот же справочник, что в «Все кандидаты».
 *  Раньше клик по чипу сразу снимал сорсера, а рядом стоял «+». */
const SOURCER_COLORS = ["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#64748b"];

function SourcerCell({
  row, catalog, onCatalog, onReload,
}: {
  row: BoardRow;
  catalog: Tag[];
  onCatalog: (update: (list: Tag[]) => Tag[]) => void;
  onReload: () => void;
}) {
  const sourcers = row.sourcers ?? [];
  const menu = useCellMenu();
  const fail = (e: any, msg: string) => toast.error(e?.response?.data?.detail || msg);
  const ids = sourcers.map((t) => String(t.id));

  const toggle = async (key: string) => {
    const tag = catalog.find((t) => String(t.id) === key) || sourcers.find((t) => String(t.id) === key);
    if (!tag) return;
    try {
      if (ids.includes(key)) await removeTagFromEntity(row.entity_id, tag.id);
      else await addTagToEntity(row.entity_id, tag.id);
      onReload();
    } catch (e) { fail(e, `Не удалось изменить «${tag.name}»`); }
  };
  // Справочник меняем от СВЕЖЕГО списка: два быстрых действия подряд по
  // снимку из замыкания затирали друг друга — новый сорсер пропадал из окна.
  const replaceTag = (tag: Tag) => onCatalog((list) => list.map((t) => (t.id === tag.id ? tag : t)));

  // Список — справочник меток (без убранных в архив), стоящие у человека —
  // сверху «Выбраны».
  const options = orderByMeta("sourcers", catalog.filter((t) => !t.archived_at || ids.includes(String(t.id))), (t) => String(t.id))
    .map((t) => ({ key: String(t.id), label: t.name, editable: true, color: t.color }));

  return (
    <div className="hf-statuses-sourcers">
      <button
        ref={menu.plusRef}
        type="button"
        className="hf-statuses-assignee-open"
        title={sourcers.length ? `Сорсер: ${sourcers.map((t) => t.name).join(", ")}` : "Поставить сорсера"}
        aria-label="Выбрать сорсера"
        onClick={menu.toggle}
      >
        {sourcers.map((t) => (
          <span key={t.id} className="hf-statuses-pill hf-statuses-sourcer-pill" style={colorPill(t.color)}>{t.name}</span>
        ))}
        {!sourcers.length && <UserIcon size={16} className="hf-statuses-person-empty" />}
      </button>
      {menu.open && menu.pos && (
        <CatalogPicker
          menuRef={menu.menuRef}
          pos={menu.pos}
          placeholder="Найти или добавить сорсера…"
          groups={[{ label: "Сорсеры", options }]}
          taken={catalog.map((t) => t.name)}
          selected={ids}
          onPick={toggle}
          onAdd={async (name) => {
            try {
              const tag = await createTag({ name, color: SOURCER_COLORS[catalog.length % SOURCER_COLORS.length] });
              onCatalog((list) => [...list.filter((t) => t.id !== tag.id), tag]);
              await addTagToEntity(row.entity_id, tag.id);
              onReload();
            } catch (e) { fail(e, `Не удалось добавить «${name}»`); }
          }}
          onRename={async (key, name) => {
            try { replaceTag(await updateTag(Number(key), { name })); onReload(); }
            catch (e) { fail(e, "Не удалось переименовать"); }
          }}
          onRecolor={async (key, color) => {
            try { replaceTag(await updateTag(Number(key), { color: color || SOURCER_COLORS[0] })); onReload(); }
            catch (e) { fail(e, "Не удалось поменять цвет"); }
          }}
          onReorder={metaHandlers("sourcers").onReorder}
          onDelete={async (key, label) => {
            // «Удалить» = убрать из списка выбора: у кого уже стоит — остаётся
            // (настоящее удаление сорвало бы метку со всех карточек).
            try { replaceTag(await archiveTag(Number(key))); toast.success(`«${label}» убран из списка`); }
            catch (e) { fail(e, `Не удалось удалить «${label}»`); }
          }}
        />
      )}
    </div>
  );
}

/** HR человека — как «Assignees» в ClickUp (клиент, 11.11.2026): клик по
 *  кружкам или «+» открывает окно — сверху назначенные (клик снимает), ниже
 *  все люди (клик добавляет), поиск по имени. Раньше клик по кружку сразу
 *  снимал HR — «это не совсем удобно». */
function AssigneeCell({
  row, people, onSave,
}: {
  row: BoardRow;
  people: { user_id: number; user_name: string | null }[];
  onSave: (ids: number[]) => void;
}) {
  const { open, pos, plusRef, menuRef, toggle } = useCellMenu();
  const [q, setQ] = useState("");

  const assignees = rowAssignees(row);
  const ids = assignees.map((a) => a.user_id);
  const needle = q.trim().toLowerCase();
  const match = (name: string | null | undefined) => !needle || (name || "").toLowerCase().includes(needle);

  const openMenu = () => { setQ(""); toggle(); };
  const add = (uid: number) => {
    // Предел — как на бэке: говорим сразу, а не ошибкой на сохранении.
    if (ids.length >= MAX_HR) { toast.error(`Не больше ${MAX_HR} HR на человека`); return; }
    onSave([...ids, uid]);
  };
  const remove = (uid: number) => onSave(ids.filter((x) => x !== uid));

  const avatar = (name: string | null | undefined, small = false) => (
    <span
      className={clsx("hf-statuses-avatar", small && "hf-statuses-avatar-sm")}
      style={{ background: `hsl(${pillHue(name || "")} 60% 45%)` }}
    >
      {initialsOf(name)}
    </span>
  );

  const others = people.filter((p) => !ids.includes(p.user_id) && match(p.user_name));
  const mine = assignees.filter((a) => match(a.name));

  return (
    <div className="hf-statuses-assignee" data-many={assignees.length > 2}>
      <button
        ref={plusRef}
        type="button"
        className="hf-statuses-assignee-open"
        title={assignees.length ? `HR: ${assignees.map((a) => a.name).join(", ")}` : "Назначить HR"}
        aria-label="Выбрать HR"
        onClick={openMenu}
      >
        {assignees.map((a) => (
          <span key={`hr-${a.user_id}`}>{avatar(a.name)}</span>
        ))}
        {!assignees.length && (
          /* Пусто — бледный значок человека, как в ClickUp: плюсики
             занимали место (клиент, 11.11.2026). */
          <UserIcon size={16} className="hf-statuses-person-empty" />
        )}
      </button>
      {open && pos && (
        <div
          ref={menuRef}
          className="hf-statuses-hr-menu hf-catalog-picker"
          style={menuBox(pos)}
        >
          <input
            autoFocus
            className="hf-statuses-picker-search"
            placeholder="Поиск…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== "Enter") return;
              if (others[0]) add(others[0].user_id);
              else if (mine[0]) remove(mine[0].user_id);
            }}
          />
          {mine.length > 0 && (
            <>
              <div className="hf-statuses-hr-menu-hint">Назначены</div>
              {mine.map((a) => (
                <button
                  key={`on-${a.user_id}`}
                  type="button"
                  className="hf-statuses-hr-option is-current"
                  title="Нажмите, чтобы снять"
                  onClick={() => remove(a.user_id)}
                >
                  {avatar(a.name, true)}
                  {a.name || `#${a.user_id}`}
                  <X size={13} className="hf-statuses-picker-hint" />
                </button>
              ))}
            </>
          )}
          <div className="hf-statuses-hr-menu-hint">Люди</div>
          {others.length === 0 && <div className="hf-statuses-hr-menu-hint">Никого не нашли</div>}
          {others.map((p) => (
            <button key={p.user_id} type="button" className="hf-statuses-hr-option" onClick={() => add(p.user_id)}>
              {avatar(p.user_name, true)}
              {p.user_name || `#${p.user_id}`}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Отметка «веха пройдена» — в ClickUp это колонки в скобках. */
/** Отметка у вехи. В ClickUp это не просто галочка: там ставили ✓, ✗, месяц
 *  («Сентябрь») или «Бонус сотруднику» — Мария попросила так же (28.09.2026). */
const BONUS_MARK = "Бонус сотруднику";

/** Цвет отметки: галочка зелёная, крестик красный, месяц синий, бонус тёмный. */
function markStyle(value: string): React.CSSProperties {
  if (value === "✓") return { background: "#dcfce7", color: "#166534", borderColor: "#bbf7d0" };
  if (value === "✗") return { background: "#fee2e2", color: "#991b1b", borderColor: "#fecaca" };
  if (value === BONUS_MARK) return { background: "#166534", color: "#fff", borderColor: "#166534" };
  return { background: "#e0e7ff", color: "#3730a3", borderColor: "#c7d2fe" };
}

