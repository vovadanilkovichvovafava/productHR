import { replaceUrls, escapeHtml } from "./linkify";

// Минимальный санитайзер для rich-text (WYSIWYG из contentEditable).
// Разрешаем только безопасные теги форматирования и ссылки (http/https).
// Без внешних зависимостей — DOMPurify в проекте нет.

const ALLOWED_TAGS = new Set([
  "B", "STRONG", "I", "EM", "U", "UL", "OL", "LI", "A", "BR", "P", "DIV", "SPAN",
]);

const DANGEROUS_TAGS = new Set([
  "SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "LINK", "META", "FORM", "INPUT",
]);

/**
 * Чистит HTML перед рендером через dangerouslySetInnerHTML:
 * - опасные теги (script/iframe/…) удаляются вместе с содержимым;
 * - прочие неразрешённые теги заменяются своим содержимым (текст сохраняется);
 * - у разрешённых тегов срезаются все атрибуты, кроме href (только http/https) у <a>.
 *
 * ВАЖНО про порядок обхода: поддерево неразрешённого тега чистится ДО того, как
 * его содержимое поднимут на место самого тега. Иначе поднятые узлы не проходят
 * очистку вообще — обход идёт по снимку `parent.children`, снятому до мутации, и
 * новые дети в него не попадают. Ровно на этом строился обход санитайзера:
 * `<img src=x onerror=…>` срезался, а `<section><img src=x onerror=…></section>`
 * выживал целиком, вместе с onerror, и исполнялся при вставке через innerHTML.
 * Так же протекали `<a href="javascript:…">` внутри любого чужого тега.
 */
export function sanitizeHtml(html: string | null | undefined): string {
  if (!html) return "";
  if (typeof window === "undefined" || typeof DOMParser === "undefined") {
    return String(html).replace(/<[^>]*>/g, "");
  }
  const doc = new DOMParser().parseFromString(html, "text/html");
  const clean = (parent: Element) => {
    Array.from(parent.children).forEach((el) => {
      const tag = el.tagName;
      if (DANGEROUS_TAGS.has(tag)) {
        el.remove();
        return;
      }
      if (!ALLOWED_TAGS.has(tag)) {
        // Сначала вычищаем то, что лежит внутри, и только потом поднимаем.
        clean(el);
        el.replaceWith(...Array.from(el.childNodes));
        return;
      }
      Array.from(el.attributes).forEach((attr) => {
        const keepHref =
          tag === "A" && attr.name === "href" && /^https?:\/\//i.test(attr.value);
        // Сохраняем class="hf-mention" — чип @-упоминания (стилизуется в CSS).
        // Остальные классы/атрибуты (data-uid и т.п.) срезаем: для показа не нужны.
        const keepMention =
          attr.name === "class" && attr.value.trim() === "hf-mention";
        if (!keepHref && !keepMention) el.removeAttribute(attr.name);
      });
      if (tag === "A") {
        el.setAttribute("target", "_blank");
        el.setAttribute("rel", "noopener noreferrer");
      }
      clean(el);
    });
  };
  clean(doc.body);
  linkifyTextNodes(doc.body);
  return doc.body.innerHTML;
}

/**
 * Голый адрес в тексте → кликабельная ссылка (просьба Марии 05.10.2026:
 * «вставлять ссылки без доп действий»). Делаем это ПРИ ПОКАЗЕ, поэтому
 * кликабельными становятся и уже сохранённые комментарии, где ссылка осталась
 * простым текстом. Внутрь существующих <a> не лезем — там адрес уже оформлен.
 */
function linkifyTextNodes(root: HTMLElement): void {
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    texts.push(node as Text);
    node = walker.nextNode();
  }
  texts.forEach((textNode) => {
    const value = textNode.nodeValue || "";
    if (!value.trim()) return;
    if (textNode.parentElement?.closest("a")) return;
    const html = replaceUrls(
      value,
      (url, href) =>
        `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>`,
      escapeHtml,
    );
    // Ничего не нашли — узел не трогаем (иначе зря плодим элементы).
    if (!html.includes("<a ")) return;
    const holder = root.ownerDocument.createElement("span");
    holder.innerHTML = html;
    textNode.replaceWith(...Array.from(holder.childNodes));
  });
}
