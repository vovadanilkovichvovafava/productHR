/**
 * Браузерный сплиттер больших ClickUp CSV-выгрузок на части по границам людей.
 *
 * ПОЧЕМУ ЭТО ВООБЩЕ НУЖНО: один кандидат в ClickUp-выгрузке лежит в НЕСКОЛЬКИХ
 * строках (разные воронки/вакансии). Бэкенд группирует строки в людей через
 * union-find по сильным ключам (email/телефон/hh-ссылка/telegram) — см.
 * `backend/api/services/clickup_import.py` (`row_strong_keys`,
 * `group_rows_by_person`). Если наивно резать файл по строкам, можно раскидать
 * строки ОДНОГО человека по РАЗНЫМ частям — бэкенд увидит их как разных людей
 * (каждая часть импортируется отдельным запросом) и создаст дубликат карточки.
 *
 * Поэтому здесь ЗЕРКАЛИМ бэкенд-логику группировки (насколько возможно без
 * официального column_mapping, который выбирает пользователь на шаге импорта —
 * при авто-сплите он ещё не выбран) и режем файл ТОЛЬКО по границам групп.
 *
 * ПРИНЦИП ПЕРЕСТРАХОВКИ: over-grouping (слепить в одну часть чуть больше строк,
 * чем строго нужно) БЕЗОПАСНО — это просто чуть более крупная часть файла,
 * бэкенд всё равно сам передоказывает группировку при импорте. Under-grouping
 * (раскидать одного человека по разным частям) — БАГ, приводит к дублям.
 * Поэтому все эвристики намеренно СНИСХОДИТЕЛЬНЫ (permissive): где бэкенд для
 * настоящего импорта полагается на явный column_mapping пользователя, здесь мы
 * используем более широкие эвристики по имени колонки (substring hints) —
 * это может объединить в одну часть чуть больше строк, чем нужно, но никогда
 * не разъединит одного человека.
 */

// ────────────────────────── RFC4180 CSV parse/serialize ──────────────────────────

/** Строгий RFC4180-парсер: кавычки, экранирование `""`, запятые/переводы строк
 * внутри кавычек, CRLF и LF, BOM. Построчный сплит здесь НЕЛЬЗЯ — в реальном
 * ClickUp-экспорте есть многострочные quoted-поля (комментарии/описания). */
export function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  let s = text;
  if (s.charCodeAt(0) === 0xfeff) s = s.slice(1); // strip UTF-8 BOM

  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;
  const n = s.length;
  let i = 0;

  const pushField = () => {
    row.push(field);
    field = '';
  };
  const pushRow = () => {
    pushField();
    rows.push(row);
    row = [];
  };

  while (i < n) {
    const c = s[i];
    if (inQuotes) {
      if (c === '"') {
        if (s[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i += 1;
        continue;
      }
      field += c;
      i += 1;
      continue;
    }
    if (c === '"') {
      inQuotes = true;
      i += 1;
      continue;
    }
    if (c === ',') {
      pushField();
      i += 1;
      continue;
    }
    if (c === '\r') {
      if (s[i + 1] === '\n') {
        pushRow();
        i += 2;
        continue;
      }
      pushRow();
      i += 1;
      continue;
    }
    if (c === '\n') {
      pushRow();
      i += 1;
      continue;
    }
    field += c;
    i += 1;
  }
  // Последнее поле/строка, если файл не заканчивается переводом строки.
  if (field.length > 0 || row.length > 0) {
    pushRow();
  }
  // Одна финальная пустая строка (двойной перевод строки в конце файла) — не
  // настоящая запись, убираем, иначе появится фантомная строка данных.
  while (rows.length && rows[rows.length - 1].length === 1 && rows[rows.length - 1][0] === '') {
    rows.pop();
  }

  const headers = rows.shift() || [];
  return { headers, rows };
}

function csvField(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return '"' + value.replace(/"/g, '""') + '"';
  }
  return value;
}

function serializeRow(row: string[]): string {
  return row.map(csvField).join(',') + '\r\n';
}

/** Сериализация назад в CSV-текст. Должна round-trip'иться через parseCsv. */
export function serializeCsv(headers: string[], rows: string[][]): string {
  return serializeRow(headers) + rows.map(serializeRow).join('');
}

function byteLength(s: string): number {
  return new TextEncoder().encode(s).length;
}

// ────────────────────────── Зеркала backend-нормализаций ──────────────────────────
// Источник правды: backend/api/services/similarity.py и clickup_import.py.

/** Зеркало `normalize_phone` (clickup_import.py ~22): последние 10 цифр,
 * короче — пусто (не годится как ключ). */
export function normalizePhone(value: string): string {
  const digits = (value || '').replace(/\D/g, '');
  return digits.length >= 10 ? digits.slice(-10) : '';
}

/** Зеркало `normalize_telegram` (similarity.py): без @ (может быть несколько
 * ведущих), нижний регистр, обрезка пробелов. */
export function normalizeTelegram(value: string): string {
  return (value || '').trim().replace(/^@+/, '').toLowerCase();
}

const HH_RE = /(hh\.ru|rabota\.by)\/resume\/([0-9a-z]+)/i;

/** Зеркало `normalize_hh_url` (clickup_import.py ~31): hh/rabota резюме-URL →
 * канонический 'host/resume/id' (без query, lowercase). */
export function normalizeHhUrl(value: string): string | null {
  if (!value) return null;
  const m = HH_RE.exec(value);
  if (!m) return null;
  return `${m[1].toLowerCase()}/resume/${m[2].toLowerCase()}`;
}

/** Зеркало `JUNK_TELEGRAM_USERNAMES` (similarity.py ~501): значения-ярлыки
 * источника/площадки, а не личные хэндлы — по ним матчить дубли нельзя. */
export const JUNK_TELEGRAM_USERNAMES = new Set([
  'telegram', 'tg', 'telega', 'hh', 'hh_b2b', 'hh_news', 'hh_news_hr', 'hhnews',
  'headhunter', 'hhru', 'vk', 'vkontakte', 'avito', 'superjob', 'habr', 'linkedin',
  'email', 'mail', 'phone', 'tel', 'resume', 'cv', 'source', 'none', 'no',
  'n/a', 'na', 'null', '-', '—',
]);

/** Зеркало `TG_COMMON_THRESHOLD` (similarity.py ~510): один и тот же telegram
 * у стольких РАЗНЫХ имён и более — заведомо мусорный тег (не личный хэндл). */
export const TG_COMMON_THRESHOLD = 3;

/** Зеркало `is_matchable_telegram` (similarity.py ~533). `freqCount`, если
 * передан, — сколько РАЗНЫХ людей делят этот хэндл (частотный гвард). */
export function isMatchableTelegram(value: string, freqCount?: number): boolean {
  const k = normalizeTelegram(value);
  if (!k || JUNK_TELEGRAM_USERNAMES.has(k)) return false;
  if (freqCount !== undefined && freqCount >= TG_COMMON_THRESHOLD) return false;
  return true;
}

// ────────────────────────── Column-hint эвристики (зеркало clickup_import.py) ──────

function normalizeHeader(h: string): string {
  let n = (h || '').trim().toLowerCase();
  if (n.startsWith('cf:')) n = n.slice(3).trim();
  return n;
}

// Зеркало COLUMN_ALIASES["name"] (csv_import.py ~35) — точное совпадение имени
// колонки (после strip/lower, без cf:-префикса). Точность здесь важна для
// частотного гварда telegram (см. ниже), поэтому — точное совпадение, не substring.
const NAME_ALIASES = new Set(['name', 'имя', 'фио', 'кандидат', 'full name', 'fullname']);

function extractNameFromRow(row: Record<string, string>): string {
  for (const [col, val] of Object.entries(row)) {
    if (NAME_ALIASES.has(normalizeHeader(col)) && val && val.trim()) {
      return val.trim();
    }
  }
  return '';
}

const EMAIL_RE = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i;
// Зеркало _EMAIL_COL_HINTS (clickup_import.py ~388).
const EMAIL_COL_HINTS = ['почт', 'email', 'e-mail', 'mail'];

/** Зеркало `extract_email_from_row` (clickup_import.py ~391). */
function extractEmailFromRow(row: Record<string, string>): string | null {
  for (const [col, val] of Object.entries(row)) {
    const cl = col.toLowerCase();
    if (EMAIL_COL_HINTS.some((h) => cl.includes(h)) && typeof val === 'string') {
      const m = EMAIL_RE.exec(val);
      if (m) return m[0].toLowerCase();
    }
  }
  const m = EMAIL_RE.exec(row.description || '');
  return m ? m[0].toLowerCase() : null;
}

// Зеркало _TG_COL_HINTS (clickup_import.py ~402).
const TG_COL_HINTS = ['telegram', 'телеграм', 'телеграмм', 'tg'];

/** Зеркало `extract_telegram_from_row` (clickup_import.py ~405). */
function extractTelegramFromRow(row: Record<string, string>): string | null {
  for (const [col, val] of Object.entries(row)) {
    const cl = col.toLowerCase();
    if (TG_COL_HINTS.some((h) => cl.includes(h)) && typeof val === 'string' && val.trim()) {
      return val.trim();
    }
  }
  return null;
}

// Зеркало _HH_COL_HINTS (clickup_import.py ~373).
const HH_COL_HINTS = ['резюме hh', 'ссылку на свое резюме', 'резюме из hh'];

/** Зеркало `extract_hh_from_row` (clickup_import.py ~376). */
function extractHhFromRow(row: Record<string, string>): string | null {
  for (const [col, val] of Object.entries(row)) {
    const cl = col.toLowerCase();
    if ((HH_COL_HINTS.some((h) => cl.includes(h)) || cl === 'cf:резюме') && val) {
      const got = normalizeHhUrl(val);
      if (got) return got;
    }
  }
  return normalizeHhUrl(row.description || '');
}

// ЭТО МЕСТО — единственное намеренное отклонение от бэкенда: на реальном
// импорте телефон берётся из ТОЧНОГО column_mapping (COLUMN_ALIASES["phone"]),
// который на этапе авто-сплита ещё не выбран пользователем. Поэтому здесь
// матчим по substring-эвристике (тот же список алиасов, что и в
// csv_import.py COLUMN_ALIASES["phone"], но как подстроку). Это делает
// группировку ЧУТЬ более снисходительной (может объединить в одну часть чуть
// больше строк, чем строго нужно) — безопасно по правилу "over-grouping ok".
const PHONE_COL_HINTS = [
  'phone', 'телефон', 'тел', 'mobile', 'мобильный',
  'контактный номер', 'контактный телефон', 'номер телефона',
];

function extractPhoneFromRow(row: Record<string, string>): string {
  for (const [col, val] of Object.entries(row)) {
    const cl = col.toLowerCase();
    if (PHONE_COL_HINTS.some((h) => cl.includes(h)) && val && val.trim()) {
      return val.trim();
    }
  }
  return '';
}

// ────────────────────────── Сильные ключи + группировка (union-find) ──────────────

/** Зеркало `row_strong_keys` (clickup_import.py ~138): `email:<v>` /
 * `phone:<v>` / `hh:<v>` / `tg:<v>`. `tg:` добавляется только для годного
 * личного хэндла (денилист-проверка `isMatchableTelegram`, БЕЗ частотного
 * гварда — тот применяет вызывающий, как и в бэкенде). */
export function rowStrongKeys(row: Record<string, string>): string[] {
  const keys: string[] = [];

  const email = (extractEmailFromRow(row) || '').trim().toLowerCase();
  if (email) keys.push(`email:${email}`);

  const phone = normalizePhone(extractPhoneFromRow(row));
  if (phone) keys.push(`phone:${phone}`);

  const hh = extractHhFromRow(row);
  if (hh) keys.push(`hh:${hh}`);

  const rawTg = extractTelegramFromRow(row);
  if (rawTg) {
    const tg = normalizeTelegram(rawTg);
    if (tg && isMatchableTelegram(tg)) keys.push(`tg:${tg}`);
  }

  return keys;
}

/** Зеркало `group_rows_by_person` (clickup_import.py ~164): union-find по
 * ключам из `keyFn`. Строки без ключей → каждая своей группой (singleton). */
export function groupRowsByPerson<T>(rows: T[], keyFn: (row: T) => string[]): T[][] {
  const parent = new Map<string, string>();

  const find = (k: string): string => {
    if (!parent.has(k)) parent.set(k, k);
    while (parent.get(k) !== k) {
      const gp = parent.get(parent.get(k) as string) as string;
      parent.set(k, gp);
      k = gp;
    }
    return k;
  };
  const union = (a: string, b: string) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  };

  const rowKeys = rows.map((r) => keyFn(r));
  for (const keys of rowKeys) {
    for (let i = 1; i < keys.length; i++) {
      union(keys[0], keys[i]);
    }
  }

  const groups = new Map<string, T[]>();
  let singleton = 0;
  rows.forEach((row, idx) => {
    const keys = rowKeys[idx];
    let gid: string;
    if (keys.length) {
      const sorted = [...keys].sort();
      gid = find(sorted[0]);
    } else {
      gid = `__single_${singleton}`;
      singleton += 1;
    }
    if (!groups.has(gid)) groups.set(gid, []);
    (groups.get(gid) as T[]).push(row);
  });
  return Array.from(groups.values());
}

/** Частотный гвард (зеркало `_groupable_tg` в csv_import.py `_run_clickup_combine`
 * ~299): telegram-хэндл, встречающийся у ≥ TG_COMMON_THRESHOLD РАЗНЫХ `name`,
 * — не личный хэндл, а тег-источник. Считаем РАЗНЫЕ имена (не строки — один
 * человек законно лежит в нескольких строках с тем же tg). */
function buildTelegramNameFreq(rows: Record<string, string>[]): Map<string, Set<string>> {
  const freq = new Map<string, Set<string>>();
  for (const row of rows) {
    const raw = extractTelegramFromRow(row);
    if (!raw) continue;
    const tg = normalizeTelegram(raw);
    if (!tg) continue;
    const name = extractNameFromRow(row).trim().toLowerCase();
    if (!freq.has(tg)) freq.set(tg, new Set());
    (freq.get(tg) as Set<string>).add(name);
  }
  return freq;
}

function buildGroupableKeyFn(rows: Record<string, string>[]): (row: Record<string, string>) => string[] {
  const freq = buildTelegramNameFreq(rows);
  return (row: Record<string, string>) =>
    rowStrongKeys(row).filter((k) => {
      if (!k.startsWith('tg:')) return true;
      const handle = k.slice(3);
      const names = freq.get(handle);
      return !names || names.size < TG_COMMON_THRESHOLD;
    });
}

// ────────────────────────── Публичное API: сплит по людям ──────────────────────────

export interface CsvSplitResult {
  parts: string[];
  groups: number;
  records: number;
}

/** Разбивает CSV-текст на части ≤ maxBytes КАЖДАЯ, режа ТОЛЬКО по границам
 * групп-людей (union-find по сильным ключам — см. rowStrongKeys/groupRowsByPerson).
 * Одна группа крупнее maxBytes — становится собственной частью (не режется).
 * Каждая часть начинается со строки заголовков. Строки без сильных ключей
 * (singleton-группы) распределяются свободно по частям в порядке заполнения. */
export function splitCsvByPerson(text: string, maxBytes: number): CsvSplitResult {
  const { headers, rows } = parseCsv(text);

  const rowObjects: Record<string, string>[] = rows.map((r) => {
    const obj: Record<string, string> = {};
    headers.forEach((h, i) => {
      obj[h] = r[i] ?? '';
    });
    return obj;
  });

  const keyFn = buildGroupableKeyFn(rowObjects);
  const indices = rowObjects.map((_, i) => i);
  const idxGroups = groupRowsByPerson(indices, (i) => keyFn(rowObjects[i]));
  const groups = idxGroups.map((idxs) => idxs.map((i) => rows[i]));

  const headerLine = serializeRow(headers);
  const headerBytes = byteLength(headerLine);

  const parts: string[] = [];
  let currentLines: string[] = [];
  let currentBytes = headerBytes;

  const flush = () => {
    if (currentLines.length) {
      parts.push(headerLine + currentLines.join(''));
      currentLines = [];
      currentBytes = headerBytes;
    }
  };

  for (const group of groups) {
    const groupLines = group.map(serializeRow);
    const groupBytes = groupLines.reduce((sum, l) => sum + byteLength(l), 0);

    if (headerBytes + groupBytes > maxBytes) {
      // Одна группа крупнее лимита сама по себе — своя часть, не режем.
      flush();
      parts.push(headerLine + groupLines.join(''));
      continue;
    }
    if (currentLines.length && currentBytes + groupBytes > maxBytes) {
      flush();
    }
    currentLines.push(...groupLines);
    currentBytes += groupBytes;
  }
  flush();
  if (parts.length === 0) parts.push(headerLine);

  return { parts, groups: groups.length, records: rows.length };
}
