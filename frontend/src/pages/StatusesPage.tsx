import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Search, Loader2, Plus, Pencil, Eye, EyeOff, Check, Copy, Download, X,
  ChevronRight, ChevronDown, Paperclip, Upload, SlidersHorizontal, ListChecks,
} from "lucide-react";
import clsx from "clsx";
import * as XLSX from "xlsx";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  getBoardRows, updateBoardRow, addBoardPlacement, removeBoardPlacement,
  getBoardDepartments, createBoardDepartment, updateBoardDepartment, setBoardDepartmentHidden,
  saveBoardDepartmentOrder,
  type BoardDepartment, type BoardRow, type BoardRowUpdate,
} from "@/services/api/staffBoard";
import { uploadEntityFile, deleteEntityFile, downloadEntityFile } from "@/services/api/entities";
import {
  getBoardPositions, getBoardManagers,
  getBoardStatusViews, saveBoardStatusView,
} from "@/services/api/staffBoard";
import { getOrgMembers } from "@/services/api/accessHub";
import { addTagToEntity, getTags, removeTagFromEntity, type Tag } from "@/services/api/tags";
import { useUrlTab } from "@/hooks/useUrlTab";
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
  // «Уволен» и «Уволился» — одна группа: HR неважно, кто инициатор, а две
  // полупустые секции только удлиняли доску. В базе различие остаётся
  // (dismissed / quit) — объединяем только показ, данные не трогаем.
  // Сюда же — «Отказ» и «Отозван» у тех, кто уже был в отделе: для доски это
  // уход, а не работа воронки (владелец, 06.10.2026: «поменял статус на
  // отозван — он просто исчез из статусов, это неверно»). Кандидата без отдела
  // с такими статусами сервер на доску не отдаёт вовсе.
  { key: "dismissed",   label: "УВОЛЕН / УВОЛИЛСЯ",
    members: ["dismissed", "quit", "rejected", "withdrawn"] },
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
  | "name" | "assignee" | "sourcer" | "position" | "department" | "telegram"
  | "practice_start_date" | "manager" | "department_start_date"
  | "dept_done" | "w2" | "w2_done" | "m1" | "m1_done"
  | "m3" | "m3_done" | "y1" | "y1_done" | "dismissal_date";

/** Ширины колонок с датами рассчитаны так, чтобы «дд.мм.гггг» помещалась
 *  целиком: в узких колонках дата обрезалась и год было не прочитать
 *  (Мария, 28.09.2026).
 *  Порядок и состав повторяют доску «Сотрудники» в ClickUp: после каждой
 *  вехи идёт колонка-отметка «пройдено» (в ClickUp она называлась так же,
 *  но в скобках). «2 недели» — наша дополнительная веха, в ClickUp её нет. */
/** Ширина в px задана у каждой колонки: без неё 19 колонок растягивались как
 *  попало, длинная должность раздувала свою, а даты сжимались до переноса.
 *  Суммарно таблица шире экрана — прокрутка есть, но имя закреплено слева. */
const COLUMNS: { key: FilterKey | "offer" | "salary"; label: string; filter: boolean; narrow?: boolean; width: number }[] = [
  { key: "name",                  label: "Сотрудник",         filter: true, width: 250 },
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
  // «Сумма» видна только владельцам организации (Настя). У остальных сервер
  // не присылает значение, и колонка в таблицу не попадает.
  { key: "salary",                label: "Сумма",             filter: false, width: 120 },
];

/** Колонки, которые можно спрятать: все, кроме «Сотрудника» — без имени
 *  строка бессмысленна (просьба Марии 08.10.2026 про лист-вью по столбцам). */
const HIDEABLE_COLUMNS = COLUMNS.filter((c) => c.key !== "name");

/** Колонки вкладки: пусто — показываем все, иначе только отмеченные, и
 *  «Сотрудник» всегда первым (его прятать нельзя). Порядок всегда из COLUMNS,
 *  чтобы таблица не переставлялась от порядка галочек. */
export function pickColumns(
  chosen?: string[] | null,
  withSalary = false,
): typeof COLUMNS {
  // «Сумма» — только владельцам организации: сервер не присылает значение,
  // и колонку мы даже не рисуем (владелец, 09.10.2026).
  const base = withSalary ? COLUMNS : COLUMNS.filter((c) => c.key !== "salary");
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

/** Имя колонки для фразы в панели и для чипов. */
const filterLabel = (key: FilterKey) =>
  FILTER_LABELS[key] || COLUMNS.find((c) => c.key === key)?.label || String(key);

const fmt = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString("ru-RU");
};

/** Колонки, по которым можно фильтровать. */
const FILTERABLE = COLUMNS.filter((c) => c.filter) as { key: FilterKey; label: string }[];

// v2: вместо правил «поле/оператор/значение» — выбор значений галочками
const FILTERS_STORAGE_KEY = "hf-statuses-filters-v2";

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
const isDateKey = (k: FilterKey) => DATE_KEYS.includes(k);

/** Колонки-галочки: у них всего два варианта. */
const DONE_KEYS: FilterKey[] = ["dept_done", "w2_done", "m1_done", "m3_done", "y1_done"];
const isDoneKey = (k: FilterKey) => DONE_KEYS.includes(k);

/** «Пусто» — такой же вариант выбора, как остальные значения колонки. */
const BLANK = "\u0000blank";
const valueLabel = (key: FilterKey, v: string) =>
  v === BLANK ? "Пусто" : isDoneKey(key) ? (v === "✓" ? "Отмечено" : "Не отмечено") : v;

/** Фильтры доски. Никаких «равно/не равно»: у обычных колонок отмечают
 *  галочками нужные значения (как автофильтр в таблицах), у дат — «с» и «по»
 *  (Мария: «как-то всё очень сложно», встреча 24.09.2026). */
interface BoardFilters {
  /** колонка → выбранные значения; пусто = колонка не фильтрует */
  values: Partial<Record<FilterKey, string[]>>;
  /** колонка-дата → границы «с» и «по» */
  dates: Partial<Record<FilterKey, { from: string; to: string }>>;
  /** Условия, помеченные «и» — обязательные. Остальные — «или».
   *  Правило: все «и» должны совпасть, а из «или» достаточно ОДНОГО.
   *
   *  ПО УМОЛЧАНИЮ — «ИЛИ» (Мария, 26.10.2026: «нужно, чтобы всегда было
   *  ИЛИ»): доску фильтруют, чтобы массово отобрать людей под выгрузку —
   *  «из SEO или из Push», «уволенные или перевёдшиеся». «И» ставят руками
   *  там, где условие обязательное, например «И вышел в октябре».
   *
   *  История: до 21.10 был один режим на всю панель («любое / все сразу»),
   *  с 21.10 по 26.10 — пометка у каждого условия, но по умолчанию «и». */
  andKeys?: FilterKey[];
  /** Старые поля — только для чтения сохранённого фильтра, см. readSavedFilters. */
  orKeys?: FilterKey[];
  mode?: "any" | "all";
}

const EMPTY_FILTERS: BoardFilters = { values: {}, dates: {}, andKeys: [] };

/** Сохранённый в браузере фильтр → текущий формат.
 *
 *  Старые сохранения переводятся так, чтобы у человека не осталось «и»,
 *  которого он сам не ставил: с 21.10 по 26.10 «и» стояло само по умолчанию —
 *  такие условия становятся «или». Явный старый режим «все сразу» был выбором
 *  человека — он остаётся «и» у всех условий.
 */
export function readSavedFilters(raw: unknown): BoardFilters {
  if (!raw || typeof raw !== "object") return EMPTY_FILTERS;
  const parsed = raw as BoardFilters;
  const base: BoardFilters = {
    values: parsed.values || {},
    dates: parsed.dates || {},
    andKeys: [],
  };
  if (Array.isArray(parsed.andKeys)) base.andKeys = parsed.andKeys;
  else if (parsed.mode === "all") base.andKeys = activeFilterKeys(base);
  return base;
}

/** Условие обязательное («и»)? По умолчанию — нет, «или». */
const isAndKey = (filters: BoardFilters, key: FilterKey) =>
  (filters.andKeys || []).includes(key);

/** Проходит ли строка под фильтры панели. Условий нет — проходит всё.
 *
 *  Обязательные условия должны совпасть ВСЕ, из помеченных «или» — хотя бы
 *  одно. Значения внутри одной колонки всегда по «или»: «Отдел: SEO, Push» —
 *  это «SEO или Push».
 */
export function rowMatchesFilters(row: BoardRow, filters: BoardFilters): boolean {
  const andKeys = new Set(filters.andKeys || []);
  const must: boolean[] = [];
  const some: boolean[] = [];
  const put = (key: FilterKey, ok: boolean) => (andKeys.has(key) ? must : some).push(ok);

  for (const [key, chosen] of Object.entries(filters.values) as [FilterKey, string[]][]) {
    if (!chosen?.length) continue;
    const cell = cellText(row, key).trim();
    put(key, chosen.includes(isBlank(cell) ? BLANK : cell));
  }

  for (const [key, range] of Object.entries(filters.dates) as
      [FilterKey, { from: string; to: string }][]) {
    if (!range || (!range.from && !range.to)) continue;
    // Сравниваем «сырую» дату (ГГГГ-ММ-ДД), а не видимую «дд.мм.гггг».
    const iso = ((row[key as keyof BoardRow] as string | null) || "").slice(0, 10);
    put(key, !!iso && (!range.from || iso >= range.from) && (!range.to || iso <= range.to));
  }

  if (!must.length && !some.length) return true;
  return must.every(Boolean) && (some.length === 0 || some.some(Boolean));
}

/** Ключи колонок, по которым сейчас что-то отобрано. */
export function activeFilterKeys(filters: BoardFilters): FilterKey[] {
  const keys: FilterKey[] = [];
  for (const [key, chosen] of Object.entries(filters.values) as [FilterKey, string[]][]) {
    if (chosen?.length) keys.push(key);
  }
  for (const [key, range] of Object.entries(filters.dates) as
      [FilterKey, { from: string; to: string }][]) {
    if (range && (range.from || range.to)) keys.push(key);
  }
  return keys;
}

/** Фильтр словами — панель пишет вслух, кого покажет.
 *
 *  «Говорят, что не понимают смысла кнопок» (владелец, 21.10.2026): вместо
 *  режима «любое / все сразу» человек читает готовую фразу и видит, что
 *  получилось из его галочек. */
export function describeFilters(filters: BoardFilters): string {
  const andKeys = new Set(filters.andKeys || []);
  const must: string[] = [];
  const some: string[] = [];
  const add = (key: FilterKey, text: string) => (andKeys.has(key) ? must : some).push(text);

  for (const [key, chosen] of Object.entries(filters.values) as [FilterKey, string[]][]) {
    if (!chosen?.length) continue;
    add(key, `${filterLabel(key)} — ${chosen.map((v) => valueLabel(key, v)).join(" или ")}`);
  }
  for (const [key, range] of Object.entries(filters.dates) as
      [FilterKey, { from: string; to: string }][]) {
    if (!range || (!range.from && !range.to)) continue;
    const when = [range.from ? `с ${fmt(range.from)}` : "", range.to ? `по ${fmt(range.to)}` : ""]
      .filter(Boolean).join(" ");
    add(key, `${filterLabel(key)} — ${when}`);
  }

  if (!must.length && !some.length) return "Ничего не отмечено — показываем всех.";
  // Одни «или» — без скобок: «у кого Отдел — SEO или Выход в отдел — октябрь».
  if (!must.length) return `Показываем тех, у кого ${some.join(" или ")}.`;
  const parts = [...must];
  if (some.length) parts.push(some.length > 1 ? `(${some.join(" или ")})` : some[0]);
  return `Показываем тех, у кого ${parts.join(" и ")}.`;
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

const countActive = (f: BoardFilters) =>
  Object.values(f.values).filter((v) => v && v.length).length +
  Object.values(f.dates).filter((d) => d && (d.from || d.to)).length;

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
    case "manager": return r.manager || "";
    // Отметки — «заполнено» значит «отмечено», чтобы фильтр по колонке
    // отвечал на вопрос «у кого веха пройдена».
    case "dept_done": return r.dept_done || "";
    case "w2_done": return r.w2_done || "";
    case "m1_done": return r.m1_done || "";
    case "m3_done": return r.m3_done || "";
    case "y1_done": return r.y1_done || "";
    default: return fmt(r[key] as string | null);
  }
};

/** Ключ строки доски: назначение, а у тех, кто ещё не в отделе, — человек. */
const rowKey = (r: BoardRow) =>
  r.placement_id != null ? `p${r.placement_id}` : `e${r.entity_id}`;

export default function StatusesPage() {
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [departments, setDepartments] = useState<BoardDepartment[]>([]);
  // Справочники для выпадающих списков: должности и руководители собираются
  // из уже существующих значений, HR — из участников организации.
  const [positions, setPositions] = useState<string[]>([]);
  const [managers, setManagers] = useState<string[]>([]);
  const [people, setPeople] = useState<{ user_id: number; user_name: string | null }[]>([]);
  // Справочник сорсеров (те же метки кандидата) — для «+» в колонке «Сорсер».
  const [sourcerTags, setSourcerTags] = useState<Tag[]>([]);
  const [orgHr, setOrgHr] = useState<{ user_id: number; user_name: string | null }[]>([]);
  const [loading, setLoading] = useState(true);
  // Отдел слева живёт в URL (?dept=) — работают браузерные «Назад/Вперёд».
  // Раньше тут были «направления» — отдельный список папок, но это те же
  // отделы (решение владельца 21.09.2026), так что панель строится по отделам.
  const [dept, setDept] = useUrlTab<string>("dept", "all");
  const [q, setQ] = useState("");
  // Быстрый фильтр по HR — запоминаем: Лиза открывает доску и сразу видит своих
  const [hrFilter, setHrFilter] = useState<string>(() => {
    try { return localStorage.getItem(HR_FILTER_STORAGE_KEY) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try {
      if (hrFilter) localStorage.setItem(HR_FILTER_STORAGE_KEY, hrFilter);
      else localStorage.removeItem(HR_FILTER_STORAGE_KEY);
    } catch { /* без хранилища просто не запоминаем */ }
  }, [hrFilter]);

  // Сорсер: «нажать Лиза и увидеть, скольких она вывела» (Мария, 29.09.2026)
  const [sourcerFilter, setSourcerFilter] = useState<string>(() => {
    try { return localStorage.getItem(SOURCER_FILTER_STORAGE_KEY) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try {
      if (sourcerFilter) localStorage.setItem(SOURCER_FILTER_STORAGE_KEY, sourcerFilter);
      else localStorage.removeItem(SOURCER_FILTER_STORAGE_KEY);
    } catch { /* без хранилища просто не запоминаем */ }
  }, [sourcerFilter]);

  const [filters, setFilters] = useState<BoardFilters>(() => {
    try {
      const raw = localStorage.getItem(FILTERS_STORAGE_KEY);
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

  /** «или» ↔ «и» у условия. Кнопка стоит у самого условия: один общий режим
   *  на панель человек не находил и не понимал (владелец, 21.10.2026). */
  const toggleJoin = (key: FilterKey) =>
    setFilters((f) => {
      const cur = new Set(f.andKeys || []);
      if (cur.has(key)) cur.delete(key);
      else cur.add(key);
      return { ...f, andKeys: [...cur] };
    });

  /** Отметить/снять значение колонки. */
  const toggleValue = (key: FilterKey, value: string) =>
    setFilters((f) => {
      const cur = f.values[key] || [];
      const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
      const values = { ...f.values };
      if (next.length) values[key] = next;
      else delete values[key];
      return { ...f, values };
    });

  const setDateBound = (key: FilterKey, side: "from" | "to", value: string) =>
    setFilters((f) => {
      const cur = f.dates[key] || { from: "", to: "" };
      const next = { ...cur, [side]: value };
      const dates = { ...f.dates };
      if (next.from || next.to) dates[key] = next;
      else delete dates[key];
      return { ...f, dates };
    });

  /** Поставить обе границы разом — кнопки «Этот месяц» и список месяцев. */
  const setDateRange = (key: FilterKey, from: string, to: string) =>
    setFilters((f) => ({ ...f, dates: { ...f.dates, [key]: { from, to } } }));

  const clearKey = (key: FilterKey) =>
    setFilters((f) => {
      const values = { ...f.values };
      const dates = { ...f.dates };
      delete values[key];
      delete dates[key];
      // Пометка «или» без самого условия ничего не значит — снимаем вместе.
      return { values, dates, andKeys: (f.andKeys || []).filter((k) => k !== key) };
    });

  const [pickerOpen, setPickerOpen] = useState(false);
  // Условие, которое правят прямо на доске — окошко под его чипом.
  const [chipEdit, setChipEdit] = useState<FilterKey | null>(null);
  // Сняли в окошке последнее значение — условия больше нет, и окошко тоже
  // закрываем: иначе оно само выскочило бы, когда условие заведут заново.
  useEffect(() => {
    if (chipEdit && !activeFilterKeys(filters).includes(chipEdit)) setChipEdit(null);
  }, [filters, chipEdit]);
  useEffect(() => {
    if (!chipEdit) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setChipEdit(null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [chipEdit]);
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
  // Какие секции показывать: СВОЙ набор у каждого и на каждой вкладке (мит
  // 07.10.2026 — «у Маши в SANDBOX видны „Перевёлся“ и „Практика“, а у Насти
  // только „Уволился“»). Ключ — та же строка, что у вкладки: «all», «__none__»
  // или id отдела. Нет записи — показываем все секции.
  const [statusViews, setStatusViews] = useState<Record<string, string[]>>({});
  const [columnViews, setColumnViews] = useState<Record<string, string[]>>({});
  const [showSections, setShowSections] = useState(false);
  /** Ответ сервера → два словаря: наборы секций и наборы колонок по вкладкам. */
  const applyViews = useCallback((list: { scope_key: string; statuses: string[]; columns: string[] }[]) => {
    setStatusViews(Object.fromEntries(list.map((v) => [v.scope_key, v.statuses])));
    setColumnViews(Object.fromEntries(list.map((v) => [v.scope_key, v.columns || []])));
  }, []);
  const [savingSections, setSavingSections] = useState(false);
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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await getBoardRows());
    } catch {
      toast.error("Не удалось загрузить доску");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    getBoardDepartments().then(setDepartments).catch(() => setDepartments([]));
    getBoardPositions().then(setPositions).catch(() => setPositions([]));
    getBoardStatusViews()
      .then(applyViews)
      .catch(() => { setStatusViews({}); setColumnViews({}); });
    getBoardManagers().then(setManagers).catch(() => setManagers([]));
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
    // HR из воронки тоже считается: «кандидаты Лизы» — все, кого она ведёт,
    // а не только те, за кем её закрепили руками.
    if (hrFilter === HR_NONE) {
      out = out.filter((r) => rowAssignees(r).length === 0);
    } else if (hrFilter) {
      const uid = Number(hrFilter);
      out = out.filter((r) => rowAssignees(r).some((a) => a.user_id === uid));
    }
    if (sourcerFilter === SOURCER_NONE) {
      out = out.filter((r) => (r.sourcers ?? []).length === 0);
    } else if (sourcerFilter) {
      out = out.filter((r) => (r.sourcers ?? []).some((t) => String(t.id) === sourcerFilter));
    }

    // Условия панели складываются по правилу filters.mode: «любое» (по
    // умолчанию) или «все сразу». Значения внутри одной колонки — всегда «или».
    out = out.filter((r) => rowMatchesFilters(r, filters));
    return out;
  }, [rows, q, filters, hrFilter, sourcerFilter]);

  /** Сорсеры для быстрого фильтра — с количеством выведённых людей. */
  const sourcerOptions = useMemo(() => {
    const map = new Map<number, { name: string; color: string; count: number }>();
    let none = 0;
    for (const r of rows) {
      const list = r.sourcers ?? [];
      if (!list.length) none += 1;
      for (const t of list) {
        const cur = map.get(t.id);
        map.set(t.id, { name: t.name, color: t.color, count: (cur?.count || 0) + 1 });
      }
    }
    const list = [...map.entries()]
      .map(([id, v]) => ({ id, ...v }))
      .sort((a, b) => a.name.localeCompare(b.name, "ru"));
    return { list, none };
  }, [rows]);

  /** HR для быстрого фильтра — только те, у кого на доске кто-то есть. */
  const hrOptions = useMemo(() => {
    const map = new Map<number, { name: string; count: number }>();
    let none = 0;
    for (const r of rows) {
      const list = rowAssignees(r);
      if (list.length === 0) none += 1;
      for (const a of list) {
        const cur = map.get(a.user_id);
        map.set(a.user_id, { name: cur?.name || a.name || `#${a.user_id}`, count: (cur?.count || 0) + 1 });
      }
    }
    const list = [...map.entries()]
      .map(([id, v]) => ({ id, ...v }))
      .sort((a, b) => a.name.localeCompare(b.name, "ru"));
    return { list, none };
  }, [rows]);

  /** Видны ли секции этой вкладки у ЭТОГО пользователя. Нет записи — все. */
  const sectionsOf = useCallback(
    (scope: string) => statusViews[scope],
    [statusViews],
  );
  const sectionShown = useCallback(
    (scope: string, row: BoardRow) => {
      const set = sectionsOf(scope);
      return !set || !set.length || set.includes(groupOf(row.status));
    },
    [sectionsOf],
  );
  const mySections = statusViews[dept];
  // Колонки тоже настраиваются лично и по вкладкам («лист-вью не только по
  // статусам, но и по столбцам» — Мария, 08.10.2026). Имя не прячем: без него
  // строка бессмысленна, поэтому в наборе его нет и он всегда первый.
  const myColumns = columnViews[dept];
  // Право на «Сумму» приходит со строками: сервер ставит его всем строкам
  // одинаково, поэтому достаточно посмотреть первую.
  const canSeeSalary = rows.some((r) => r.salary_visible);
  const visibleColumns = useMemo(
    () => pickColumns(myColumns, canSeeSalary),
    [myColumns, canSeeSalary],
  );

  const counts = useMemo(() => {
    // У отдела — сколько в нём строк, у «Все» — сколько ЛЮДЕЙ: человек в
    // песочнице и в команде занимает две строки, но человек-то один, и бейдж
    // не должен расходиться со списком. Скрытые секции не считаем — иначе
    // бейдж покажет больше, чем видно (правило «бейдж и список не расходятся»).
    const c: Record<string, number> = { [UNASSIGNED]: 0 };
    const people = new Set<number>();
    for (const r of searched) {
      if (sectionShown("all", r)) people.add(r.entity_id);
      const key = r.department_id != null ? String(r.department_id) : UNASSIGNED;
      if (sectionShown(key, r)) c[key] = (c[key] || 0) + 1;
    }
    c.all = people.size;
    return c;
  }, [searched, sectionShown]);

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
      let blank = 0;
      for (const r of rows) {
        if (needle && ![r.name, r.position, r.department_name, r.telegram, r.manager]
          .filter(Boolean).some((v) => String(v).toLowerCase().includes(needle))) continue;
        const v = cellText(r, key).trim();
        if (isBlank(v)) { blank += 1; continue; }
        map.set(v, (map.get(v) || 0) + 1);
      }
      const list = [...map.entries()]
        .map(([value, count]) => ({ value, count }))
        .sort((a, b) => a.value.localeCompare(b.value, "ru"));
      // «Пусто» — внизу: по нему находят незаполненные ячейки
      if (blank) list.push({ value: BLANK, count: blank });
      return list;
    },
    [rows, q]
  );

  const activeCount = countActive(filters);

  /** Выгрузка в Excel того, что сейчас отобрано.
   *
   *  «А мы можем эти фильтры в табличку выгружать?» (Мария, 29.09.2026): она
   *  отбирает людей за месяц или по сорсеру и дальше считает выплаты в
   *  таблице. Выгружаем РОВНО видимое — с учётом поиска, фильтров, выбранного
   *  отдела и сортировки, плюс колонку статуса: в файле групп нет. */
  /** Строки → лист: шапка как в таблице, плюс колонка со статусом. */
  const sheetFrom = (items: BoardRow[]) => {
    // «Сумма» — только владельцу: остальным сервер её не присылает, и в файле
    // висела бы пустая колонка, по которой непонятно, что сломалось.
    const cols = COLUMNS.filter((c) => c.key !== "offer" && (c.key !== "salary" || canSeeSalary));
    const header = ["Статус", ...cols.map((c) => FILTER_LABELS[c.key as FilterKey] || c.label)];
    const body: (string | number)[][] = items.map((r) => [
      STATUSES.find((s2) => (s2.members as readonly string[]).includes(r.status))?.label || r.status,
      ...cols.map((c) => {
        if (c.key === "sourcer") return (r.sourcers ?? []).map((t) => t.name).join(", ");
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
  const exportToExcel = (plan?: ExportPlan) => {
    const wb = XLSX.utils.book_new();
    let total = 0;
    for (const sheet of buildExportSheets(grouped.flatMap((g) => g.items), months, plan)) {
      if (!sheet.items.length) continue;
      const { ws, count } = sheetFrom(sheet.items);
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

  /** Итог по колонке «Сумма»: считаем по ЛЮДЯМ, а не по строкам — человек в
   *  песочнице и в отделе занимает две строки, но деньги у него одни. Берём
   *  ровно то, что сейчас на экране после фильтров (владелец, 09.10.2026:
   *  «когда фильтры применялись, этот столбец в конце писал сумму всех»). */
  const salaryTotal = useMemo(() => {
    if (!canSeeSalary) return null;
    // Люди, а не строки: человек в песочнице и в отделе — две строки.
    const people = new Set<number>();
    const seen = new Map<number, number>();
    for (const r of visible) {
      people.add(r.entity_id);
      if (r.salary != null) seen.set(r.entity_id, r.salary);
    }
    let sum = 0;
    seen.forEach((v) => { sum += v; });
    return { sum, people: people.size, withSalary: seen.size };
  }, [visible, canSeeSalary]);

  const grouped = useMemo(
    () => STATUSES.filter((s) => !mySections || !mySections.length || mySections.includes(s.key)).map((s) => {
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
    [visible, sort, mySections]
  );

  return (
    <div className="hf-statuses-page">
      <div className="hf-statuses-header">
        <div>
          {/* Раздел называется «Штат» (владелец, 09.10.2026). Адрес остался
              /statuses: по нему уже ходят закладки и ссылки. */}
          <h1 className="hf-statuses-title">Штат</h1>
          <p className="hf-statuses-subtitle">Жизненный цикл сотрудника по отделам</p>
        </div>
        <div className="hf-statuses-tools">
          <div className="hf-statuses-search">
            <Search className="hf-statuses-search-icon" size={15} />
            <input
              className="hf-statuses-search-input"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Поиск по имени, должности, отделу…"
            />
          </div>

          <select
            className={clsx("hf-statuses-hr-filter", hrFilter && "hf-statuses-hr-filter-on")}
            value={hrFilter}
            onChange={(e) => setHrFilter(e.target.value)}
            title="Показать людей конкретного HR"
          >
            <option value="">HR: все</option>
            {hrOptions.list.map((h) => (
              <option key={h.id} value={String(h.id)}>{h.name} · {h.count}</option>
            ))}
            {/* выбранный HR мог пропасть с доски — не сбрасываем выбор молча */}
            {hrFilter && hrFilter !== HR_NONE && !hrOptions.list.some((h) => String(h.id) === hrFilter) && (
              <option value={hrFilter}>HR #{hrFilter} · 0</option>
            )}
            {hrOptions.none > 0 && <option value={HR_NONE}>Без HR · {hrOptions.none}</option>}
          </select>

          <select
            className={clsx("hf-statuses-hr-filter", sourcerFilter && "hf-statuses-hr-filter-on")}
            value={sourcerFilter}
            onChange={(e) => setSourcerFilter(e.target.value)}
            title="Показать, кого вывел конкретный сорсер"
          >
            <option value="">Сорсер: все</option>
            {sourcerOptions.list.map((t) => (
              <option key={t.id} value={String(t.id)}>{t.name} · {t.count}</option>
            ))}
            {/* выбранный сорсер мог исчезнуть с доски — выбор не сбрасываем молча */}
            {sourcerFilter && sourcerFilter !== SOURCER_NONE
              && !sourcerOptions.list.some((t) => String(t.id) === sourcerFilter) && (
              <option value={sourcerFilter}>Сорсер #{sourcerFilter} · 0</option>
            )}
            {sourcerOptions.none > 0 && (
              <option value={SOURCER_NONE}>Без сорсера · {sourcerOptions.none}</option>
            )}
          </select>

          <button
            className={clsx(
              "hf-statuses-export-btn",
              (mySections?.length || myColumns?.length) && "hf-statuses-filters-btn-on",
            )}
            onClick={() => setShowSections(true)}
            title="Какие секции и колонки показывать на этой вкладке — только у вас"
          >
            <ListChecks size={15} />
            Вид
            {!!(mySections?.length || myColumns?.length) && (
              <span className="hf-statuses-filters-badge">
                {(mySections?.length ? 1 : 0) + (myColumns?.length ? 1 : 0)}
              </span>
            )}
          </button>

          {/* «Выгрузить» сразу отдаёт в Excel тех, кто на экране после
              фильтров (владелец, 26.10.2026: «кнопка должна выгружать всех
              кандидатов по фильтрам, а не открывать модалку»). Раньше она
              открывала окно периодов, где главная чёрная кнопка была
              неактивна, пока не отмечен месяц, — Мария жала её и думала, что
              выгрузка сломана. Книга по месяцам и вехам — за стрелкой рядом. */}
          <div className="hf-statuses-export-split">
            <button
              className="hf-statuses-export-btn hf-statuses-export-main"
              onClick={() => exportToExcel()}
              title="Выгрузить в Excel всех, кто сейчас на экране — с учётом фильтров, поиска и вкладки"
            >
              <Download size={15} />
              Выгрузить
            </button>
            <button
              className="hf-statuses-export-btn hf-statuses-export-more"
              onClick={() => setShowExport(true)}
              title="Выгрузить по периодам: лист на каждый месяц выхода в отдел и на вехи стажа"
              aria-label="Выгрузить по периодам"
            >
              <ChevronDown size={14} />
            </button>
          </div>

          <div className="hf-statuses-filters-picker">
            <button
              className={clsx(
                "hf-statuses-filters-btn",
                activeCount > 0 && "hf-statuses-filters-btn-on"
              )}
              onClick={() => { setPickerOpen((v) => !v); setChipEdit(null); }}
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
                <div className="hf-statuses-picker">
                  <div className="hf-statuses-picker-head">
                    <span>Фильтры</span>
                    {activeCount > 0 && (
                      <div className="hf-statuses-picker-actions">
                        <button onClick={() => setFilters(EMPTY_FILTERS)}>очистить всё</button>
                      </div>
                    )}
                  </div>

                  {/* Панель говорит вслух, кого покажет: «говорят, что не
                      понимают смысла кнопок» (владелец, 21.10.2026). Раньше
                      тут были два режима на всю панель — «любое из условий» /
                      «все условия сразу», — и Мария, отметив четыре отдела и
                      октябрь, получила всех подряд. */}
                  <div className="hf-statuses-filter-formula">
                    {describeFilters(filters)}
                  </div>
                  <div className="hf-statuses-filter-hint">
                    Отметьте, что показывать. Условия складываются через «или» —
                    достаточно совпасть с любым. Нажмите «или» у условия, чтобы
                    оно стало «и» — обязательным.
                  </div>

                  {FILTERABLE.map((c) => (
                    <FilterSection
                      key={c.key}
                      label={FILTER_LABELS[c.key] || c.label}
                      column={c.key}
                      values={filters.values[c.key] || []}
                      range={filters.dates[c.key]}
                      options={isDateKey(c.key) ? [] : valuesFor(c.key)}
                      isOr={!isAndKey(filters, c.key)}
                      onToggleJoin={() => toggleJoin(c.key)}
                      onToggle={(v) => toggleValue(c.key, v)}
                      onDate={(side, v) => setDateBound(c.key, side, v)}
                      onRange={(from, to) => setDateRange(c.key, from, to)}
                      onClear={() => clearKey(c.key)}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {activeCount > 0 && (
        // Чипы читаются как фраза: между ними стоит «и» или «или» — то же
        // самое, что панель пишет словами. Обязательные идут первыми, чтобы
        // «или»-условия стояли рядом и читались группой.
        <div className="hf-statuses-fchips">
          {activeFilterKeys(filters)
            .slice()
            .sort((a, b) => Number(!isAndKey(filters, a)) - Number(!isAndKey(filters, b)))
            .map((key, i, all) => {
              // «или» имеет смысл, только когда таких условий ДВА и больше:
              // одно-единственное «или» — то же самое, что обязательное, и
              // слово «или» между чипами сбивало бы с толку.
              const orCount = all.filter((k) => !isAndKey(filters, k)).length;
              const isOr = orCount > 1 && !isAndKey(filters, key);
              const vals = filters.values[key];
              const r = filters.dates[key];
              const text = vals?.length
                ? vals.map((v) => valueLabel(key, v)).join(" или ")
                : `${r?.from ? `с ${fmt(r.from)}` : ""}${r?.to ? ` по ${fmt(r.to)}` : ""}`.trim();
              return (
                <Fragment key={key}>
                  {i > 0 && (
                    <span className="hf-statuses-fchip-join">{isOr ? "или" : "и"}</span>
                  )}
                  {/* Клик по чипу открывает правку ПРЯМО НА ДОСКЕ — окошко
                      под чипом с этим же условием: значения, даты, «и/или»
                      (Мария, 26.10.2026: «когда фильтр уже выбран — была
                      возможность его редактировать на борде»). До этого чип
                      открывал боковую панель со всеми колонками, и нужное
                      место там приходилось искать. Снимает только крестик. */}
                  <span className="hf-statuses-fchip-wrap">
                    <span
                      className={clsx(
                        "hf-statuses-fchip",
                        isOr && "is-or",
                        chipEdit === key && "is-editing",
                      )}
                    >
                      <button
                        type="button"
                        className="hf-statuses-fchip-body"
                        onClick={() => { setPickerOpen(false); setChipEdit(chipEdit === key ? null : key); }}
                        title="Изменить условие"
                        aria-expanded={chipEdit === key}
                      >
                        <b>{filterLabel(key)}:</b> {text}
                        <ChevronDown size={12} className="hf-statuses-fchip-caret" />
                      </button>
                      <button
                        type="button"
                        className="hf-statuses-fchip-x"
                        onClick={() => { clearKey(key); setChipEdit(null); }}
                        title="Снять фильтр"
                        aria-label={`Снять фильтр «${filterLabel(key)}»`}
                      >
                        <X size={12} />
                      </button>
                    </span>
                    {chipEdit === key && (
                      <>
                        <div className="hf-statuses-picker-backdrop" onClick={() => setChipEdit(null)} />
                        <div className="hf-statuses-fchip-pop" role="dialog" aria-label={`Условие «${filterLabel(key)}»`}>
                          <FilterSection
                            label={filterLabel(key)}
                            column={key}
                            values={filters.values[key] || []}
                            range={filters.dates[key]}
                            options={isDateKey(key) ? [] : valuesFor(key)}
                            isOr={!isAndKey(filters, key)}
                            openNow
                            pinned
                            onToggleJoin={() => toggleJoin(key)}
                            onToggle={(v) => toggleValue(key, v)}
                            onDate={(side, v) => setDateBound(key, side, v)}
                            onRange={(from, to) => setDateRange(key, from, to)}
                            onClear={() => { clearKey(key); setChipEdit(null); }}
                          />
                          {/* Без фразы «Показываем тех, у кого…»: в маленьком
                              окошке она растягивалась на пол-экрана и мешала
                              (владелец, 26.10.2026: «вот это убери»). Фраза
                              осталась в большой панели «Фильтры». */}
                          <div className="hf-statuses-fchip-pop-foot">
                            <button type="button" onClick={() => setChipEdit(null)}>Готово</button>
                          </div>
                        </div>
                      </>
                    )}
                  </span>
                </Fragment>
              );
            })}
        </div>
      )}

      {loading ? (
        <div className="hf-statuses-loading">
          <Loader2 className="animate-spin" size={26} />
        </div>
      ) : (
        <div className="hf-statuses-body">
          {showSections && (
            <ViewModal
              hideable={HIDEABLE_COLUMNS.filter((c) => c.key !== "salary" || canSeeSalary)}
              scopeLabel={
                dept === "all" ? "Все"
                  : dept === UNASSIGNED ? "Без отдела"
                    : (departments.find((d) => String(d.id) === dept)?.name || "вкладке")
              }
              sections={mySections?.length ? mySections : STATUSES.map((s) => s.key)}
              columns={myColumns?.length ? myColumns : HIDEABLE_COLUMNS.map((c) => c.key)}
              
              busy={savingSections}
              onClose={() => setShowSections(false)}
              onSave={async (view) => {
                setSavingSections(true);
                try {
                  applyViews(await saveBoardStatusView(dept, view));
                  setShowSections(false);
                } catch (e: any) {
                  toast.error(e?.response?.data?.detail || "Не удалось сохранить вид");
                } finally {
                  setSavingSections(false);
                }
              }}
            />
          )}

          {showExport && (
            <ExportModal
              months={months}
              onClose={() => setShowExport(false)}
              onExport={(plan) => { exportToExcel(plan); setShowExport(false); }}
            />
          )}

          <DepartmentSidebar
            departments={departments}
            orgHr={orgHr}
            counts={counts}
            active={dept}
            onSelect={setDept}
            onCreated={(d) => setDepartments((cur) => [...cur, d])}
            onRenamed={(d) => setDepartments((cur) => cur.map((x) => (x.id === d.id ? d : x)))}
            onHidden={(d) => setDepartments((cur) => cur.map((x) => (x.id === d.id ? d : x)))}
            onReorder={setDepartments}
            onRows={load}
          />

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
                            ? `${c.label} — сортировать по дате`
                            : FILTER_LABELS[c.key as FilterKey] || c.label
                        }
                        onClick={sortable ? () => toggleSort(c.key as SortKey) : undefined}
                      >
                        {c.label}
                        {sortable && (
                          <span className="hf-statuses-th-arrow">
                            {on ? (sort!.dir === "desc" ? "↓" : "↑") : "↕"}
                          </span>
                        )}
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
                          positions={positions}
                          managers={managers}
                          people={people}
                          sourcerTags={sourcerTags}
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

              {/* Колонку «Сумма» спрятали в «Виде» — итог без суммы ничего не
                  говорит («Итого · 0 чел.» читалось как «никого не нашли»). */}
              {salaryTotal && visibleColumns.some((c) => c.key === "salary") && (
                <tfoot className="hf-statuses-foot">
                  <tr>
                    {visibleColumns.map((c, i) => (
                      <td
                        key={c.key}
                        className={clsx(
                          "hf-statuses-td",
                          c.key === "name" && "hf-statuses-sticky",
                        )}
                      >
                        {c.key === "salary"
                          ? <strong>{formatMoney(salaryTotal.sum)}</strong>
                          : i === 0
                            ? `Итого по отбору · ${salaryTotal.people} чел.` +
                              (salaryTotal.withSalary < salaryTotal.people
                                ? ` (сумма указана у ${salaryTotal.withSalary})`
                                : "")
                            : null}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              )}
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

/** Одна колонка в панели фильтров: раскрывается, внутри — галочки со
 *  значениями и их количеством, у дат — «с» и «по». Ни операторов, ни
 *  «равно/содержит»: отмечаешь то, что хочешь видеть. */
function FilterSection({
  label, column, values, range, options, isOr, openNow, pinned, onToggleJoin,
  onToggle, onDate, onRange, onClear,
}: {
  label: string;
  column: FilterKey;
  values: string[];
  range?: { from: string; to: string };
  options: { value: string; count: number }[];
  /** Условие помечено «или» — достаточно совпасть с ним ИЛИ с другим таким. */
  isOr: boolean;
  /** Раскрыть сразу — пришли сюда кликом по чипу под шапкой. */
  openNow?: boolean;
  /** Всегда раскрыто (окошко под чипом): сворачивать там нечего. */
  pinned?: boolean;
  onToggleJoin: () => void;
  onToggle: (v: string) => void;
  onDate: (side: "from" | "to", v: string) => void;
  onRange: (from: string, to: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const months = useMemo(() => recentMonths(), []);
  const headRef = useRef<HTMLButtonElement>(null);
  // Пришли по клику на чип — раскрываем это условие и подкручиваем к нему
  // панель: иначе нужное место приходится искать в длинном списке колонок.
  useEffect(() => {
    if (!openNow) return;
    setOpen(true);
    headRef.current?.scrollIntoView({ block: "nearest" });
  }, [openNow]);
  const isDate = isDateKey(column);
  const active = isDate ? !!(range && (range.from || range.to)) : values.length > 0;
  const shown = q
    ? options.filter((o) => valueLabel(column, o.value).toLowerCase().includes(q.toLowerCase()))
    : options;

  const summary = isDate
    ? `${range?.from ? `с ${fmt(range.from)}` : ""}${range?.to ? ` по ${fmt(range.to)}` : ""}`.trim()
    : values.map((v) => valueLabel(column, v)).join(", ");

  return (
    <div className={clsx("hf-statuses-filter-section", active && "is-active")}>
      <button
        ref={headRef}
        className="hf-statuses-filter-head"
        onClick={() => { if (!pinned) setOpen((v) => !v); }}
      >
        {!pinned && (
          <ChevronRight
            size={13}
            className={clsx("hf-statuses-filter-caret", open && "is-open")}
          />
        )}
        <span className="hf-statuses-filter-name">{label}</span>
        {active && <span className="hf-statuses-filter-summary">{summary}</span>}
        {active && (
          <span
            className={clsx("hf-statuses-filter-join", isOr && "is-or")}
            title={isOr
              ? "Сейчас «или»: достаточно совпасть с этим условием ИЛИ с другим таким же. Нажмите, чтобы стало «и» — обязательным"
              : "Сейчас «и»: условие обязательно. Нажмите, чтобы стало «или»"}
            onClick={(e) => { e.stopPropagation(); onToggleJoin(); }}
          >
            {isOr ? "или" : "и"}
          </span>
        )}
        {active && (
          <span
            className="hf-statuses-filter-clear"
            title="Снять фильтр"
            onClick={(e) => { e.stopPropagation(); onClear(); }}
          >
            <X size={12} />
          </span>
        )}
      </button>

      {open && (isDate ? (
        <div className="hf-statuses-filter-daterange">
          <div className="hf-statuses-filter-dates">
            <label>с<input type="date" value={range?.from || ""} onChange={(e) => onDate("from", e.target.value)} /></label>
            <label>по<input type="date" value={range?.to || ""} onChange={(e) => onDate("to", e.target.value)} /></label>
          </div>
          <div className="hf-statuses-filter-presets">
            {months.slice(0, 2).map((m, i) => {
              const on = range?.from === m.from && range?.to === m.to;
              return (
                <button
                  key={m.label}
                  type="button"
                  className={clsx("hf-statuses-preset", on && "is-on")}
                  // Повторный клик по выбранному месяцу снимает фильтр — как у
                  // чипов наставников в «Все кандидаты»: нажал — отобрал,
                  // нажал ещё раз — вернул всех.
                  onClick={() => (on ? onClear() : onRange(m.from, m.to))}
                >
                  {i === 0 ? "Этот месяц" : "Прошлый месяц"}
                </button>
              );
            })}
            <select
              className="hf-statuses-preset hf-statuses-preset-select"
              value={months.find((m) => m.from === range?.from && m.to === range?.to)?.label || ""}
              onChange={(e) => {
                const m = months.find((x) => x.label === e.target.value);
                if (m) onRange(m.from, m.to);
              }}
            >
              <option value="">Месяц…</option>
              {months.map((m) => (
                <option key={m.label} value={m.label}>{m.label}</option>
              ))}
            </select>
          </div>
        </div>
      ) : (
        <div className="hf-statuses-filter-values">
          {options.length > 8 && (
            <input
              className="hf-statuses-filter-search"
              value={q}
              placeholder="найти значение…"
              onChange={(e) => setQ(e.target.value)}
            />
          )}
          {shown.length === 0 && <div className="hf-statuses-filter-empty">Нет значений</div>}
          {shown.map((o) => (
            <label key={o.value} className="hf-statuses-filter-option">
              <input
                type="checkbox"
                checked={values.includes(o.value)}
                onChange={() => onToggle(o.value)}
              />
              <span className="hf-statuses-filter-option-name">{valueLabel(column, o.value)}</span>
              <span className="hf-statuses-filter-option-count">{o.count}</span>
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

/** Отделы слева — вместо прежних «направлений» (это были те же отделы).
 *  Сначала отделы, где кто-то есть, потом пустые: пустых в оргструктуре
 *  много, и за ними терялись нужные. «+ Отдел» заводит отдел прямо здесь; это
 *  СВОЙ справочник доски, оргструктуру Enceladus он не трогает. */
function DepartmentSidebar({
  departments, orgHr, counts, active, onSelect, onCreated, onRenamed, onHidden, onReorder,
  onRows,
}: {
  departments: BoardDepartment[];
  orgHr: { user_id: number; user_name: string | null }[];
  counts: Record<string, number>;
  active: string;
  onSelect: (id: string) => void;
  onCreated: (d: BoardDepartment) => void;
  onRenamed: (d: BoardDepartment) => void;
  onHidden: (d: BoardDepartment) => void;
  onReorder: (list: BoardDepartment[]) => void;
  /** Перечитать строки доски: включение песочницы «по умолчанию» ставит в неё
   *  тех, кто уже на практике, — таблица должна это показать сразу. */
  onRows: () => void;
}) {
  // Перетаскивание отделов: порядок личный и сохраняется в базе.
  const [dragId, setDragId] = useState<number | null>(null);
  const [overId, setOverId] = useState<number | null>(null);
  // Скрытые не выбрасываем из списка совсем: их можно раскрыть и вернуть.
  const [showHidden, setShowHidden] = useState(false);
  // Отдел заводят и правят в окне: у него есть не только название, но и роль
  // (песочница или команда внутри неё) и видимость (решение владельца
  // 30.09.2026). В строке сайдбара это уже не поместилось бы.
  const [modal, setModal] = useState<{ dept: BoardDepartment | null } | null>(null);
  const [busy, setBusy] = useState(false);

  const label = (d: BoardDepartment) => d.name;
  const hiddenCount = departments.filter((d) => d.hidden).length;
  // Порядок задаёт сам пользователь перетаскиванием — сервер отдаёт список уже
  // в его порядке, поэтому здесь только отодвигаем скрытые в конец.
  const sorted = departments
    .filter((d) => showHidden || !d.hidden || String(d.id) === active)
    .slice()
    .sort((a, b) => (a.hidden === b.hidden ? 0 : a.hidden ? 1 : -1));

  // Список отделов плоский: вложенность под песочницу убрана (владелец,
  // 09.10.2026 — «убрать визуальную привязку к родительскому отделу»). Связь
  // parent_id осталась в данных и в окне отдела, просто её больше не рисуем.
  const tree = sorted.map((d) => ({ d, child: false }));

  const drop = async (target: BoardDepartment) => {
    setOverId(null);
    const from = departments.findIndex((d) => d.id === dragId);
    const to = departments.findIndex((d) => d.id === target.id);
    setDragId(null);
    if (from < 0 || to < 0 || from === to) return;
    const next = [...departments];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onReorder(next);  // сразу показываем новый порядок, не дожидаясь сервера
    try {
      onReorder(await saveBoardDepartmentOrder(next.map((d) => d.id)));
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось сохранить порядок отделов");
      onReorder(departments);
    }
  };

  const toggleHidden = async (d: BoardDepartment) => {
    if (busy) return;
    setBusy(true);
    try {
      const next = await setBoardDepartmentHidden(d.id, !d.hidden);
      onHidden(next);
      if (next.hidden && active === String(d.id)) onSelect("all");
      toast.success(next.hidden ? `Отдел «${d.name}» скрыт` : `Отдел «${d.name}» снова виден`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Не удалось изменить отдел");
    } finally {
      setBusy(false);
    }
  };

  const item = (id: string, text: string) => (
    <button
      key={id}
      onClick={() => onSelect(id)}
      className={clsx(
        "hf-statuses-folder",
        id === "all" && "hf-statuses-folder-all",
        active === id && "hf-statuses-folder-active"
      )}
      title={text}
    >
      <span className="hf-statuses-folder-name">{text}</span>
      <span className="hf-statuses-folder-count">{counts[id] ?? 0}</span>
    </button>
  );

  return (
    <div className="hf-statuses-sidebar">
      {item("all", "Все")}

      {tree.map(({ d, child }) => (
          <div
            key={d.id}
            className={clsx(
              "hf-statuses-folder-row",
              child && "hf-statuses-folder-child",
              d.hidden && "hf-statuses-folder-hidden",
              dragId === d.id && "hf-statuses-folder-dragging",
              overId === d.id && dragId !== d.id && "hf-statuses-folder-over"
            )}
            draggable
            onDragStart={() => setDragId(d.id)}
            onDragEnd={() => { setDragId(null); setOverId(null); }}
            onDragOver={(e) => { e.preventDefault(); setOverId(d.id); }}
            onDrop={(e) => { e.preventDefault(); drop(d); }}
            title="Потяните, чтобы переставить отдел"
          >
            {item(String(d.id), label(d))}
            <div className="hf-statuses-folder-actions">
              <button
                className="hf-statuses-folder-action"
                title="Название, роль, кому виден"
                onClick={(e) => { e.stopPropagation(); setModal({ dept: d }); }}
              >
                <Pencil size={12} />
              </button>
              <button
                className="hf-statuses-folder-action"
                title={d.hidden ? "Показывать отдел" : "Скрыть отдел (останется у людей)"}
                onClick={(e) => { e.stopPropagation(); toggleHidden(d); }}
              >
                {d.hidden ? <Eye size={12} /> : <EyeOff size={12} />}
              </button>
            </div>
          </div>
      ))}

      {item(UNASSIGNED, "Без отдела")}

      {hiddenCount > 0 && (
        <button className="hf-statuses-folder-add" onClick={() => setShowHidden((v) => !v)}>
          {showHidden ? <EyeOff size={14} /> : <Eye size={14} />}
          {showHidden ? "Спрятать скрытые" : `Показать скрытые · ${hiddenCount}`}
        </button>
      )}

      <button className="hf-statuses-folder-add" onClick={() => setModal({ dept: null })}>
        <Plus size={14} /> Отдел
      </button>

      {modal && (
        <DepartmentModal
          dept={modal.dept}
          departments={departments}
          orgHr={orgHr}
          onClose={() => setModal(null)}
          onSaved={(d, created) => {
            if (created) {
              onCreated(d);
              onSelect(String(d.id));
            } else {
              onRenamed(d);
            }
            if (d.placed_now) {
              toast.success(`Практиканты без отдела переехали в «${d.name}»: ${d.placed_now}`);
              onRows();
            }
            setModal(null);
          }}
        />
      )}
    </div>
  );
}

/** Окно «Вид»: какие секции И какие колонки показывать на этой вкладке.
 *
 *  Мит 07.10.2026: «разные лист-вью под каждого пользователя и под каждый
 *  отдел — у Маши в SANDBOX видны „Перевёлся“ и „Практика“, а у Насти только
 *  „Уволился“»; 08.10.2026 Мария попросила то же и по столбцам. Набор привязан
 *  к паре «человек + вкладка»: у соседа и на другой вкладке он свой. Снял все
 *  галочки — показывается всё. Колонку «Сотрудник» не прячем: без имени строка
 *  бессмысленна. */
function ViewModal({
  scopeLabel, sections, columns, hideable, busy, onClose, onSave,
}: {
  scopeLabel: string;
  hideable: typeof COLUMNS;
  sections: string[];
  columns: string[];
  busy: boolean;
  onClose: () => void;
  onSave: (view: { statuses: string[]; columns: string[] }) => void;
}) {
  const [keys, setKeys] = useState<string[]>(sections);
  const [cols, setCols] = useState<string[]>(columns);
  const flip = (list: string[], k: string) =>
    list.includes(k) ? list.filter((x) => x !== k) : [...list, k];

  return (
    <div className="hf-statuses-modal-back" onClick={onClose}>
      <div className="hf-statuses-modal" onClick={(e) => e.stopPropagation()}>
        <div className="hf-statuses-modal-head">
          <h3>Вид вкладки «{scopeLabel}»</h3>
          <button className="hf-statuses-folder-action" onClick={onClose} title="Закрыть">
            <X size={16} />
          </button>
        </div>

        <div className="hf-statuses-modal-label">
          Секции
          <span className="hf-statuses-modal-note">
            Набор только ваш и только для этой вкладки: у коллег и в других отделах — свой.
          </span>
          {STATUSES.map((st) => (
            <label key={st.key} className="hf-statuses-modal-check">
              <input
                type="checkbox"
                checked={keys.includes(st.key)}
                disabled={busy}
                onChange={() => setKeys((cur) => flip(cur, st.key))}
              />
              {st.label}
            </label>
          ))}
        </div>

        <div className="hf-statuses-modal-label">
          Колонки
          <span className="hf-statuses-modal-note">
            «Сотрудник» остаётся всегда — по нему и читается строка.
          </span>
          <div className="hf-statuses-view-cols">
            {hideable.map((c) => (
              <label key={c.key} className="hf-statuses-modal-check">
                <input
                  type="checkbox"
                  checked={cols.includes(c.key)}
                  disabled={busy}
                  onChange={() => setCols((cur) => flip(cur, c.key))}
                />
                {FILTER_LABELS[c.key as FilterKey] || c.label}
              </label>
            ))}
          </div>
        </div>

        <div className="hf-statuses-modal-foot">
          <button
            className="hf-statuses-modal-cancel"
            onClick={() => onSave({ statuses: [], columns: [] })}
            disabled={busy}
            title="Показывать все секции и все колонки"
          >
            Показать всё
          </button>
          <button
            className="hf-statuses-modal-save"
            onClick={() => onSave({ statuses: keys, columns: cols })}
            disabled={busy}
          >
            {busy ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}

/** Окно выгрузки: что именно класть в книгу.
 *
 *  «Как на экране» — один лист с текущим отбором (так работала кнопка раньше).
 *  Месяцы и вехи — по листу на каждый: «мне бы хотелось за месяц, за два
 *  месяца, за три месяца работы, за год работы» (Мария, 07.10.2026). */
function ExportModal({
  months, onClose, onExport,
}: {
  months: { label: string; from: string; to: string }[];
  onClose: () => void;
  onExport: (plan: ExportPlan) => void;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const [marks, setMarks] = useState<MilestoneKey[]>([]);
  const toggle = <T,>(list: T[], v: T) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  return (
    <div className="hf-statuses-modal-back" onClick={onClose}>
      <div className="hf-statuses-modal" onClick={(e) => e.stopPropagation()}>
        <div className="hf-statuses-modal-head">
          <h3>Выгрузка по периодам</h3>
          <button className="hf-statuses-folder-action" onClick={onClose} title="Закрыть">
            <X size={16} />
          </button>
        </div>

        <div className="hf-statuses-modal-label">
          Месяцы выхода в отдел
          <span className="hf-statuses-modal-note">Каждый — отдельным листом книги.</span>
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
            Кто доходит до вехи в выбранные месяцы; месяцы не отмечены — за всё время.
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
              ? "Листы соберутся из тех, кто сейчас на экране, — фильтры учитываются."
              : "Отметьте месяцы или вехи. Просто выгрузить экран — кнопка «Выгрузить»."}
          </span>
          <button
            className="hf-statuses-modal-save"
            onClick={() => onExport({ months: picked, marks })}
            disabled={!picked.length && !marks.length}
          >
            <Download size={14} />
            Выгрузить по периодам
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
  row, columns, departments, positions, managers, people, sourcerTags, saving,
  onPatch, onStatus, onPlace, onUnplace, onReload,
}: {
  row: BoardRow;
  /** Колонки, которые показывает ЭТОТ пользователь на этой вкладке. */
  columns: typeof COLUMNS;
  departments: BoardDepartment[];
  positions: string[];
  managers: string[];
  people: { user_id: number; user_name: string | null }[];
  sourcerTags: Tag[];
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
  const mark = (key: "dept_done" | "w2_done" | "m1_done" | "m3_done" | "y1_done") => (
    <MarkCell value={row[key]} onSave={(v) => onPatch(row, { [key]: v } as BoardRowUpdate)} />
  );

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
        <Link
          to={`/all-candidates?entity=${row.entity_id}`}
          className="hf-statuses-name hf-statuses-name-link"
          title="Открыть карточку в «Все кандидаты»"
        >
          {row.name}
        </Link>
        {/* Смена статуса прямо в строке: раньше перевести человека из
            «Практики» в «Уволен» через интерфейс было нельзя вообще. */}
        <select
          className={clsx("hf-statuses-status", `hf-statuses-status-${groupOf(row.status)}`)}
          value={groupOf(row.status)}
          // Группа «Уволен / Уволился» объединяет увольнение, уход, отказ и
          // «отозван» — точный статус показываем подсказкой.
          title={(STATUS_LABELS as Record<string, string>)[row.status] || ""}
          onChange={(e) => {
            // Уже в объединённой группе — повторный выбор ничего не меняет,
            // иначе «уволился» молча переписался бы в «уволен».
            if (e.target.value !== groupOf(row.status)) onStatus(row, e.target.value);
          }}
        >
          {STATUSES.map((st) => (
            <option key={st.key} value={st.key}>{st.label}</option>
          ))}
        </select>
      </div>
    ),
    assignee: (
      <AssigneeCell
        row={row}
        people={people}
        onSave={(ids) => onPatch(row, { assignee_user_ids: ids })}
      />
    ),
    sourcer: <SourcerCell row={row} catalog={sourcerTags} onReload={onReload} />,
    // Должность вписывает HR — и на практике тоже: раньше здесь стояла
    // несъёмная подпись «Сандбокс», а песочница теперь настоящий отдел.
    position: (
      <PillCell
        value={row.position}
        options={positions}
        onSave={(v) => onPatch(row, { position: v })}
      />
    ),
    department: (
      <DepartmentCell
        row={row}
        departments={departments}
        onPlace={(id) => onPlace(row, id)}
        onUnplace={() => onUnplace(row)}
      />
    ),
    telegram: <TelegramCell value={row.telegram} onSave={(v) => onPatch(row, { telegram: v })} />,
    practice_start_date: date("practice_start_date"),
    manager: (
      <PillCell
        value={row.manager}
        options={managers}
        onSave={(v) => onPatch(row, { manager: v })}
      />
    ),
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
    salary: (
      <MoneyCell value={row.salary} onSave={(v) => onPatch(row, { salary: v })} />
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
          {cells[c.key]}
        </td>
      ))}
    </tr>
  );
}


// ============================================================
// CELLS
// ============================================================

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

/** «Сумма» — число, которое вписывает владелец. Показываем с разделителями
 *  тысяч, правим как обычную ячейку. */
function MoneyCell({
  value, onSave,
}: { value: number | null; onSave: (v: number | null) => void }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <input
        autoFocus
        type="number"
        inputMode="decimal"
        className="hf-statuses-cell-input"
        defaultValue={value ?? ""}
        onBlur={(e) => {
          setEditing(false);
          const raw = e.target.value.trim();
          const next = raw === "" ? null : Number(raw);
          if (next !== value && (next === null || Number.isFinite(next))) onSave(next);
        }}
        onKeyDown={(e) => { if (e.key === "Escape") setEditing(false); }}
      />
    );
  }

  return (
    <button className="hf-statuses-cell-btn" onClick={() => setEditing(true)}>
      {value == null
        ? <span className="hf-statuses-cell-placeholder">—</span>
        : formatMoney(value)}
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
      {value ? fmt(value) : <span className="hf-statuses-cell-placeholder">—</span>}
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

/** Быстрый фильтр «кандидаты Лизы»: id HR или «без HR». */
const HR_NONE = "none";
const HR_FILTER_STORAGE_KEY = "hf-statuses-hr";
/** Быстрый фильтр «кого вывела Катя»: сорсеров считают отдельно от HR. */
const SOURCER_NONE = "none";
const SOURCER_FILTER_STORAGE_KEY = "hf-statuses-sourcer";

/** Кого можно добавить в колонку HR через «+». Решение владельца 21.09.2026:
 *  доску ведут не все HR, остальные в списке мешали. С 15.10.2026 их трое —
 *  «добавь плиз сюда Владу, она есть в базе, у нас 3 HR» (Мария). Сверяем по
 *  первому слову имени (кириллица или латиница), без учёта регистра: «Влада»
 *  и «Влад» (наставник практики) — разные люди и не путаются. Уже назначенных
 *  других HR это не снимает — их кружки остаются. */
const BOARD_HR_FIRST_NAMES = ["мария", "maria", "эльвира", "elvira", "влада", "vlada"];
export const isBoardHr = (name: string | null | undefined) =>
  BOARD_HR_FIRST_NAMES.includes((name || "").trim().split(/\s+/)[0].toLowerCase());

/** Сколько HR можно закрепить за человеком — как на бэке (MAX_ASSIGNEES). */
const MAX_HR = 5;

/** 2500.5 → «2 500,5»: длинные суммы без разделителей не читаются. */
const formatMoney = (v: number) =>
  v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });

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
function DepartmentCell({
  row, departments, onPlace, onUnplace,
}: {
  row: BoardRow;
  departments: BoardDepartment[];
  onPlace: (id: number) => void;
  onUnplace: () => void;
}) {
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
  const hue = pillHue(name);
  const options = departments.filter(
    (d) => (!d.hidden || d.id === row.department_id) && d.id !== row.department_id
  );   // сравниваем с отделом САМОЙ строки, а не с тем, что показано главным
  // Песочница у человека одна: выбрал другую — переехал. Команда из песочницы —
  // наоборот, добавление: практика остаётся.
  const sandboxes = options.filter((d) => d.kind === "sandbox");
  const teams = options.filter((d) => d.kind === "team");
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
            style={{
              background: `hsl(${hue} 70% 94%)`,
              color: `hsl(${hue} 55% 32%)`,
              borderColor: `hsl(${hue} 60% 84%)`,
            }}
          >
            {name}
          </span>
          {from && (
            <span className="hf-statuses-dept-from" title={`Остаётся в песочнице ${from}`}>
              из {from}
            </span>
          )}
        </span>
      ) : (
        <span className="hf-statuses-empty-cell">—</span>
      )}
      <select
        className="hf-statuses-dept-select"
        value=""
        title={hint}
        onChange={(e) => { if (e.target.value) onPlace(Number(e.target.value)); }}
      >
        <option value="">{hint}</option>
        {sandboxes.length > 0 && (
          <optgroup label={row.department_is_sandbox ? "Песочницы — перевести" : "Песочницы — вернуть на практику"}>
            {sandboxes.map((d) => (
              <option key={d.id} value={d.id}>{d.name}{d.hidden ? " (скрыт)" : ""}</option>
            ))}
          </optgroup>
        )}
        {teams.length > 0 && (
          <optgroup label={teamsAdd ? "Отделы — добавить (практика останется)" : "Отделы — перевести"}>
            {teams.map((d) => (
              <option key={d.id} value={d.id}>{d.name}{d.hidden ? " (скрыт)" : ""}</option>
            ))}
          </optgroup>
        )}
      </select>
      {row.placement_id != null && !row.department_is_sandbox && (
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

/** Значение из списка с цветной пилюлей — как «Должность» и «Рук-ль» в ClickUp.
 *
 *  Ввод свободный намеренно: в ClickUp список пополняется на лету, и жёсткий
 *  выбор не дал бы завести новую должность, не трогая справочник. */
function PillCell({
  value, options, onSave,
}: { value: string | null; options: string[]; onSave: (v: string | null) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  const listId = useRef(`pill-${Math.random().toString(36).slice(2)}`).current;

  useEffect(() => { setDraft(value || ""); }, [value]);

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (next !== (value || "")) onSave(next || null);
  };

  if (editing) {
    return (
      <>
        <input
          className="hf-statuses-input"
          autoFocus
          list={listId}
          placeholder="впишите или выберите"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") { setDraft(value || ""); setEditing(false); }
          }}
        />
        <datalist id={listId}>
          {options.map((o) => <option key={o} value={o} />)}
        </datalist>
      </>
    );
  }

  if (!value) {
    return (
      <button className="hf-statuses-empty-cell" onClick={() => setEditing(true)}>—</button>
    );
  }

  const hue = pillHue(value);
  return (
    <button
      className="hf-statuses-pill"
      onClick={() => setEditing(true)}
      style={{
        background: `hsl(${hue} 70% 94%)`,
        color: `hsl(${hue} 55% 32%)`,
        borderColor: `hsl(${hue} 60% 84%)`,
      }}
      title={value}
    >
      {value}
    </button>
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
function useCellMenu() {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
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
    if (r) setPos({ top: r.bottom + 4, left: Math.max(8, Math.min(r.left, window.innerWidth - 232)) });
    setOpen(true);
  };

  return { open, pos, plusRef, menuRef, toggle, close: () => setOpen(false) };
}

/**
 *  Сорсера можно не только снять, но и ПОСТАВИТЬ прямо из доски — «пусть будет
 *  аналогичная кнопка, что и для HR» (владелец, 15.10.2026). Раньше в пустой
 *  ячейке стоял прочерк, и чтобы вписать сорсера, приходилось открывать
 *  карточку кандидата. Список в «+» — тот же справочник меток, что и на
 *  карточке (`getTags`), поэтому новых сущностей не заводим: сорсер — это
 *  метка, крестик на чипе снимает её с кандидата.
 */
function SourcerCell({ row, catalog, onReload }: { row: BoardRow; catalog: Tag[]; onReload: () => void }) {
  const sourcers = row.sourcers ?? [];
  const menu = useCellMenu();
  const [busy, setBusy] = useState(false);

  const remove = async (tagId: number, name: string) => {
    try {
      await removeTagFromEntity(row.entity_id, tagId);
      onReload();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || `Не удалось снять «${name}»`);
    }
  };

  const add = async (tag: Tag) => {
    menu.close();
    setBusy(true);
    try {
      await addTagToEntity(row.entity_id, tag.id);
      onReload();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || `Не удалось поставить «${tag.name}»`);
    } finally {
      setBusy(false);
    }
  };

  // В меню — всё из справочника, чего на человеке ещё нет.
  const options = catalog.filter((t) => !sourcers.some((s) => s.id === t.id));

  return (
    <div className="hf-statuses-sourcers">
      {sourcers.map((t) => (
        <button
          key={t.id}
          type="button"
          className="hf-statuses-pill hf-statuses-sourcer-pill"
          style={{
            backgroundColor: `color-mix(in srgb, ${t.color} 14%, transparent)`,
            color: t.color,
            borderColor: `color-mix(in srgb, ${t.color} 30%, transparent)`,
          }}
          title={`Сорсер: ${t.name} — нажмите, чтобы снять`}
          onClick={() => remove(t.id, t.name)}
        >
          {t.name}
        </button>
      ))}
      <button
        ref={menu.plusRef}
        type="button"
        className="hf-statuses-avatar-add hf-statuses-avatar-add-sm"
        title="Добавить сорсера"
        aria-label="Добавить сорсера"
        onClick={menu.toggle}
        disabled={busy}
      >
        <Plus size={12} />
      </button>
      {menu.open && menu.pos && (
        <div ref={menu.menuRef} className="hf-statuses-hr-menu" style={{ top: menu.pos.top, left: menu.pos.left }}>
          <div className="hf-statuses-hr-menu-hint">Добавить сорсера</div>
          {options.length === 0 && (
            <div className="hf-statuses-hr-menu-hint">
              {catalog.length
                ? "Все сорсеры уже стоят"
                : "Список пуст — заведите метку в карточке кандидата"}
            </div>
          )}
          {options.map((t) => (
            <button
              key={t.id}
              type="button"
              className="hf-statuses-hr-option"
              onClick={() => add(t)}
            >
              <span className="hf-statuses-sourcer-dot" style={{ background: t.color }} />
              {t.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function AssigneeCell({
  row, people, onSave,
}: {
  row: BoardRow;
  people: { user_id: number; user_name: string | null }[];
  onSave: (ids: number[]) => void;
}) {
  const { open, pos, plusRef, menuRef, toggle, close } = useCellMenu();

  const assignees = rowAssignees(row);
  const ids = assignees.map((a) => a.user_id);

  const openMenu = () => {
    // Предел — как на бэке; говорим о нём ДО открытия, иначе человек выбрал бы
    // имя из списка и получил ошибку уже на сохранении.
    if (!open && ids.length >= MAX_HR) { toast.error(`Не больше ${MAX_HR} HR на человека`); return; }
    toggle();
  };

  const add = (uid: number) => {
    close();
    onSave([...ids, uid]);
  };

  const options = people.filter((p) => !ids.includes(p.user_id));

  return (
    <div className="hf-statuses-assignee" data-many={assignees.length > 2}>
      {assignees.map((a) => {
        const name = a.name || `#${a.user_id}`;
        return (
          <button
            key={`hr-${a.user_id}`}
            type="button"
            className="hf-statuses-avatar hf-statuses-avatar-removable"
            style={{ background: `hsl(${pillHue(a.name || "")} 60% 45%)` }}
            title={`HR: ${name} — убрать`}
            aria-label={`Убрать HR ${name}`}
            onClick={() => onSave(ids.filter((x) => x !== a.user_id))}
          >
            <span className="hf-statuses-avatar-text">{initialsOf(a.name)}</span>
            <X className="hf-statuses-avatar-x" size={13} />
          </button>
        );
      })}
      <button
        ref={plusRef}
        type="button"
        className="hf-statuses-avatar-add"
        title="Добавить HR"
        aria-label="Добавить HR"
        onClick={openMenu}
      >
        <Plus size={13} />
      </button>
      {open && pos && (
        <div ref={menuRef} className="hf-statuses-hr-menu" style={{ top: pos.top, left: pos.left }}>
          <div className="hf-statuses-hr-menu-hint">Добавить HR</div>
          {options.length === 0 && <div className="hf-statuses-hr-menu-hint">Все HR уже добавлены</div>}
          {options.map((p) => (
            <button key={p.user_id} type="button" className="hf-statuses-hr-option" onClick={() => add(p.user_id)}>
              <span
                className="hf-statuses-avatar hf-statuses-avatar-sm"
                style={{ background: `hsl(${pillHue(p.user_name || "")} 60% 45%)` }}
              >
                {initialsOf(p.user_name)}
              </span>
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
const MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];
const BONUS_MARK = "Бонус сотруднику";
const MARK_OPTIONS = ["✓", "✗", ...MONTHS, BONUS_MARK];

/** Цвет отметки: галочка зелёная, крестик красный, месяц синий, бонус тёмный. */
function markStyle(value: string): React.CSSProperties {
  if (value === "✓") return { background: "#dcfce7", color: "#166534", borderColor: "#bbf7d0" };
  if (value === "✗") return { background: "#fee2e2", color: "#991b1b", borderColor: "#fecaca" };
  if (value === BONUS_MARK) return { background: "#166534", color: "#fff", borderColor: "#166534" };
  return { background: "#e0e7ff", color: "#3730a3", borderColor: "#c7d2fe" };
}

function MarkCell({
  value, onSave,
}: { value: string | null; onSave: (v: string | null) => void }) {
  return (
    <div className="hf-statuses-mark">
      {value ? (
        <span className="hf-statuses-mark-pill" style={markStyle(value)} title={value}>
          {value}
        </span>
      ) : (
        <span className="hf-statuses-empty-cell">—</span>
      )}
      <select
        className="hf-statuses-mark-select"
        value={value || ""}
        title={value || "Поставить отметку"}
        onChange={(e) => onSave(e.target.value || null)}
      >
        <option value="">—</option>
        {MARK_OPTIONS.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}
