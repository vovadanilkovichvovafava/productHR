/**
 * Транслитерация RU↔EN для клиентского поиска (например, чтобы «Simonberg»
 * находил «Симонберг»). Схема упрощённая — покрывает типовые ФИО без строгого
 * следования ISO/BGN. Всё в нижнем регистре — вызывающая сторона нормализует.
 */

const RU_TO_EN: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh',
  з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o',
  п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'ts',
  ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
};

// Многосимвольные последовательности идут первыми, чтобы «sch» не разбирался как «s+ch».
const EN_MULTI: Array<[string, string]> = [
  ['sch', 'щ'], ['sh', 'ш'], ['ch', 'ч'], ['zh', 'ж'],
  ['ts', 'ц'], ['yu', 'ю'], ['ya', 'я'], ['yo', 'ё'],
  ['kh', 'х'],
];
const EN_SINGLE: Record<string, string> = {
  a: 'а', b: 'б', v: 'в', g: 'г', d: 'д', e: 'е', z: 'з', i: 'и',
  y: 'й', k: 'к', l: 'л', m: 'м', n: 'н', o: 'о', p: 'п', r: 'р',
  s: 'с', t: 'т', u: 'у', f: 'ф', h: 'х',
};

export function toLatin(s: string): string {
  let out = '';
  for (const ch of s.toLowerCase()) {
    out += RU_TO_EN[ch] ?? ch;
  }
  return out;
}

export function toCyrillic(s: string): string {
  let i = 0;
  let out = '';
  const lower = s.toLowerCase();
  while (i < lower.length) {
    let matched = false;
    for (const [en, ru] of EN_MULTI) {
      if (lower.startsWith(en, i)) {
        out += ru;
        i += en.length;
        matched = true;
        break;
      }
    }
    if (!matched) {
      const ch = lower[i];
      out += EN_SINGLE[ch] ?? ch;
      i += 1;
    }
  }
  return out;
}

/** Ё → Е. Точки над Ё в русском письме факультативны: в базе «Дёмин», ищут
 *  «Демин» — для поиска это одна буква. Зеркало серверного fold_yo
 *  (search_index.py). Свернуть надо ОБЕ стороны сравнения. */
export function foldYo(s: string): string {
  return (s || '').replace(/ё/g, 'е').replace(/Ё/g, 'Е');
}

/** Одновременно проверяет haystack на подстроку needle с учётом обеих транслитераций. */
export function matchesTranslit(haystack: string, needle: string): boolean {
  if (!needle) return true;
  const h = foldYo(haystack.toLowerCase());
  const n = foldYo(needle.toLowerCase());
  if (h.includes(n)) return true;
  const hLat = toLatin(h);
  const nLat = toLatin(n);
  if (hLat.includes(nLat)) return true;
  // toCyrillic умеет породить ё обратно («yo»→«ё») — сворачиваем ПОСЛЕ неё.
  const hCyr = foldYo(toCyrillic(h));
  const nCyr = foldYo(toCyrillic(n));
  if (hCyr.includes(nCyr)) return true;
  return false;
}

/** Расстояние Левенштейна (итеративно, две строки-буфера). Строки короткие (слова
 *  ФИО), поэтому O(n·m) дёшев. */
export function editDistance(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = new Array<number>(n + 1);
  for (let j = 0; j <= n; j++) prev[j] = j;
  for (let i = 1; i <= m; i++) {
    const cur = new Array<number>(n + 1);
    cur[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
    }
    prev = cur;
  }
  return prev[n];
}

// Порог опечаток по длине слова: короткие слова не прощаем (иначе шум).
function typoThreshold(len: number): number {
  if (len <= 3) return 0;
  if (len <= 5) return 1;
  return 2;
}

// Слово во всех формах (как есть + латиница + кириллица) — для fuzzy-сравнения.
function wordForms(w: string): string[] {
  const f = foldYo(w); // Ё≡Е: иначе Левенштейн тратит бюджет опечаток на точки над Ё
  const set = new Set([f, toLatin(f), foldYo(toCyrillic(f))]);
  set.delete('');
  return [...set];
}

// Раскладка клавиатуры ЙЦУКЕН(RU) ↔ QWERTY(EN): один и тот же ФИЗИЧЕСКИЙ клавиш.
// «bdfy» — это «иван», набранное в EN-раскладке (забыли переключить язык). Это
// НЕ транслитерация (та фонетическая: ivan→иван) — тут соответствие клавиш.
const RU_TO_EN_LAYOUT: Record<string, string> = {
  й: 'q', ц: 'w', у: 'e', к: 'r', е: 't', н: 'y', г: 'u', ш: 'i', щ: 'o', з: 'p', х: '[', ъ: ']',
  ф: 'a', ы: 's', в: 'd', а: 'f', п: 'g', р: 'h', о: 'j', л: 'k', д: 'l', ж: ';', э: "'",
  я: 'z', ч: 'x', с: 'c', м: 'v', и: 'b', т: 'n', ь: 'm', б: ',', ю: '.', ё: '`',
};
const EN_TO_RU_LAYOUT: Record<string, string> = Object.fromEntries(
  Object.entries(RU_TO_EN_LAYOUT).map(([ru, en]) => [en, ru]),
);

/** Флип раскладки RU↔EN по физическим клавишам («bdfy»→«иван»). Латиница →
 *  кириллица, кириллица → латиница. Мусор («ivan»→«шмфт») безвреден — не найдёт. */
export function switchLayout(s: string): string {
  const str = (s || '').toLowerCase();
  if (!str) return '';
  const map = /[а-яё]/.test(str) ? RU_TO_EN_LAYOUT : EN_TO_RU_LAYOUT;
  let out = '';
  for (const ch of str) out += map[ch] ?? ch;
  return out;
}

// Матч слов запроса против стога: КАЖДОЕ слово должно найтись (AND по словам,
// порядок не важен) — прямо/транслитом или с опечаткой (Левенштейн).
function matchQueryTokens(hay: string, q: string): boolean {
  const tokens = q
    .split(/\s+/)
    .map((t) => t.replace(/^[-_.,]+|[-_.,]+$/g, ''))
    .filter((t) => t.length >= 2);
  if (tokens.length === 0) return matchesTranslit(hay, q);

  // Слова стога сена во всех формах — для fuzzy-сравнения по опечаткам.
  const hayWordForms = hay.split(/\s+/).filter(Boolean).flatMap(wordForms);

  return tokens.every((tok) => {
    if (matchesTranslit(hay, tok)) return true; // прямое/транслит вхождение
    const thr = typoThreshold(tok.length);
    if (thr === 0) return false;
    const tokForms = wordForms(tok);
    return tokForms.some((tf) =>
      hayWordForms.some(
        (hf) => Math.abs(hf.length - tf.length) <= thr && editDistance(tf, hf) <= thr,
      ),
    );
  });
}

/**
 * Умный матч имени для КЛИЕНТСКОГО поиска (воронка и т.п.), где список уже
 * загружен и невелик: транслитерация RU↔EN + независимость от порядка слов +
 * терпимость к опечаткам (Левенштейн) + флип РАСКЛАДКИ клавиатуры («bdfy»→«иван»).
 * Функциональный аналог серверного pg_trgm-поиска (search_index.py), но в JS.
 */
export function smartNameMatch(haystack: string, query: string): boolean {
  const raw = (query || '').trim().toLowerCase();
  if (!raw) return true;
  const hay = (haystack || '').toLowerCase();
  if (!hay) return false;

  // Пробуем запрос как есть И с перевёрнутой раскладкой («bdfy» → «иван»).
  const queries = new Set([raw]);
  const sw = switchLayout(raw);
  if (sw && sw !== raw) queries.add(sw);
  return [...queries].some((q) => matchQueryTokens(hay, q));
}

/**
 * Матч кандидата по КОНТАКТАМ для клиентского поиска (воронка/рабочее
 * пространство): почта, телефон (в т.ч. по одним цифрам «9991234567» ↔
 * «+7 (999) 123-45-67»), telegram («@» необязателен). Substring, регистр не важен.
 * Аналог серверного contact_search_conditions, но по уже загруженному списку.
 */
export function contactMatch(
  query: string,
  fields: { email?: string | null; phone?: string | null; telegram?: string | null },
): boolean {
  const q = (query || '').trim().toLowerCase();
  if (!q) return false;
  const { email, phone, telegram } = fields;
  if (email && email.toLowerCase().includes(q)) return true;
  if (phone && phone.toLowerCase().includes(q)) return true;
  const qDigits = q.replace(/\D/g, '');
  if (qDigits.length >= 4 && phone && phone.replace(/\D/g, '').includes(qDigits)) return true;
  const qTg = q.replace(/^@+/, ''); // telegram хранится/показывается без «@»
  if (qTg && telegram && telegram.toLowerCase().includes(qTg)) return true;
  return false;
}

/** Поиск кандидата в ВОРОНКЕ: имя (нечётко) + все контакты + все telegram + текст
 *  комментариев. Запрос с «@» — СТРОГО по telegram/комментам, без нечёткого имени. */
export function funnelSearchMatch(
  query: string,
  c: {
    entity_name?: string | null; entity_email?: string | null; entity_phone?: string | null;
    entity_telegram?: string | null; entity_telegrams?: string[] | null; entity_notes_text?: string | null;
  },
): boolean {
  const raw = (query || '').trim().toLowerCase();
  if (!raw) return true;
  const tgQ = raw.replace(/^@+/, '');
  const tgs = [c.entity_telegram, ...(c.entity_telegrams || [])].filter(Boolean).map(s => (s as string).toLowerCase());
  const tgHit = !!tgQ && tgs.some(t => t.includes(tgQ));
  const notesHit = !!tgQ && !!c.entity_notes_text && c.entity_notes_text.toLowerCase().includes(tgQ);
  // Строгий режим: запрос-ник (с «@») — только telegram/комменты, без имени.
  if (raw.startsWith('@')) return tgHit || notesHit;
  return (
    smartNameMatch(c.entity_name || '', query) ||
    contactMatch(query, { email: c.entity_email, phone: c.entity_phone, telegram: c.entity_telegram }) ||
    tgHit || notesHit
  );
}
