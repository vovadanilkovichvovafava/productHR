/**
 * Ссылки в тексте — одно место на всё приложение.
 *
 * Просьба Марии (05.10.2026): «вставлять ссылки без доп действий, чтобы они
 * были кликабельны». Раньше ссылка становилась ссылкой только через кнопку
 * «Ссылка» в тулбаре, которая спрашивала адрес в браузерном окне; вставленный
 * или набранный адрес так и оставался текстом.
 *
 * Отсюда два применения:
 *  - ПОКАЗ: `sanitizeHtml` прогоняет текстовые узлы через `replaceUrls`, поэтому
 *    кликабельными становятся и уже сохранённые комментарии;
 *  - ВВОД: редактор (`HuntflowRichInput`) при вставке и при наборе превращает
 *    адрес в настоящий `<a>` — чтобы человек сразу видел результат.
 */

/** Домены верхнего уровня для адресов БЕЗ схемы («hh.ru/resume/1»).
 *  Список закрытый намеренно: иначе «и.т.д» и «2.5» превращались бы в ссылки. */
const BARE_TLDS = [
  'ru', 'by', 'ua', 'kz', 'com', 'org', 'net', 'io', 'me', 'co', 'ai', 'dev',
  'app', 'site', 'online', 'pro', 'info', 'biz', 'tech', 'team', 'work', 'life',
  'store', 'space', 'website', 'cloud', 'digital', 'agency', 'studio', 'group',
];

const URL_SOURCE =
  '(?:https?:\\/\\/[^\\s<>"\']+)' +
  '|(?:www\\.[^\\s<>"\']+)' +
  `|(?:(?:[a-zA-Z0-9][a-zA-Z0-9-]*\\.)+(?:${BARE_TLDS.join('|')})(?![a-zA-Z0-9-])(?:\\/[^\\s<>"']*)?)`;

/** Новый объект на каждый вызов: у глобального regex есть lastIndex. */
export const urlPattern = (): RegExp => new RegExp(URL_SOURCE, 'gi');

/** Хвостовая пунктуация в ссылку не входит: «смотри https://hh.ru/x.» */
const TRAILING = /[.,;:!?)\]}»"'…]+$/;

export function trimTrailingPunctuation(url: string): { url: string; tail: string } {
  const m = url.match(TRAILING);
  if (!m) return { url, tail: '' };
  // Закрывающую скобку оставляем, если она парная: «(см. https://ru.wikipedia.org/wiki/C_(язык))»
  let cut = m[0];
  if (cut.endsWith(')') && (url.match(/\(/g) || []).length > (url.match(/\)/g) || []).length - 1) {
    cut = cut.slice(0, -1);
  }
  if (!cut) return { url, tail: '' };
  return { url: url.slice(0, url.length - cut.length), tail: cut };
}

/** Адрес → href: без схемы подставляем https. */
export function toHref(url: string): string {
  return /^https?:\/\//i.test(url) ? url : `https://${url}`;
}

export function isUrl(text: string): boolean {
  const t = (text || '').trim();
  if (!t || /\s/.test(t)) return false;
  const re = urlPattern();
  const m = re.exec(t);
  return !!m && m[0] === t;
}

/**
 * Пройти по тексту и заменить каждый адрес результатом `render`.
 * Остальной текст отдаётся как есть — вызывающий решает, экранировать его или нет.
 */
export function replaceUrls(
  text: string,
  render: (url: string, href: string) => string,
  renderPlain: (chunk: string) => string = (chunk) => chunk,
): string {
  const re = urlPattern();
  let out = '';
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const { url, tail } = trimTrailingPunctuation(m[0]);
    if (!url) continue;
    out += renderPlain(text.slice(last, m.index));
    out += render(url, toHref(url));
    out += renderPlain(tail);
    last = m.index + m[0].length;
  }
  out += renderPlain(text.slice(last));
  return out;
}

/** Все адреса, которые нашлись в тексте (буфер обмена, вставленная строка). */
export function extractUrls(text: string): string[] {
  const found: string[] = [];
  replaceUrls(text || '', (url) => {
    found.push(url);
    return '';
  });
  return found;
}

/**
 * Единственный адрес в тексте — или null.
 *
 * Нужно кнопке «Ссылка»: в буфере у рекрутёра обычно не голый адрес, а
 * «вот ссылка https://hh.ru/resume/1» или адрес с хвостовым пробелом и точкой
 * (владелец 05.10.2026: «а если ссылка с ещё одним словом или буквой»). Один
 * адрес среди слов — понятно, что имели в виду; несколько — уже гадание, такой
 * текст уходит в окно, где человек выбирает сам.
 */
export function extractUrl(text: string): string | null {
  const urls = extractUrls(text);
  return urls.length === 1 ? urls[0] : null;
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Простой текст → HTML, в котором адреса стали ссылками. */
export function linkifyToHtml(text: string): string {
  return replaceUrls(
    text,
    (url, href) => `<a href="${escapeHtml(href)}">${escapeHtml(url)}</a>`,
    escapeHtml,
  );
}

function looksLikeHtml(s: string): boolean {
  return /<\/?[a-z][\s\S]*>/i.test(s);
}

/**
 * Старые анкеты хранят description обычным текстом со вставленными ссылками,
 * новые (после DescriptionRichText) — уже HTML с настоящими <a>: такую строку
 * трогать не нужно, её санитайзит sanitizeHtml при рендере.
 */
export function autoLinkify(text: string | null | undefined): string {
  if (!text) return '';
  if (looksLikeHtml(text)) return text;
  return linkifyToHtml(text);
}
