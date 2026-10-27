/**
 * Кнопка «Ссылка» без браузерного окна (владелец, 05.10.2026).
 *
 * Было: любое нажатие на «Ссылка» открывало `window.prompt` — серое системное
 * окно поверх страницы, в которое адрес надо было вставить руками. Просьба:
 * «выделил слово, нажал на ссылку и слово стало ссылкой», а если так нельзя —
 * «модальное окно браузера заменить на окно энцеладуса».
 *
 * Сделано и то, и другое — по порядку:
 *  1. выделен сам адрес — вешаем его, спрашивать нечего;
 *  2. в БУФЕРЕ ОБМЕНА ровно один адрес (хоть «вот ссылка https://hh.ru/1» —
 *     лишние слова отбрасываются) — вешаем его сразу, окна нет совсем;
 *  3. в буфере не адрес, их несколько или браузер не дал его прочитать —
 *     открывается наше окно: поле подставлено из буфера, Enter — вставить.
 *
 * Пункт 3 неизбежен: взять адрес из воздуха нельзя, а чтение буфера Chrome
 * разрешает не всегда (первый раз спрашивает, в iframe и без фокуса — молча
 * отказывает). Зато это окно наше, с нашими кнопками и подсказкой.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import toast from 'react-hot-toast';

import { extractUrl, extractUrls, isUrl, toHref } from '@/utils/linkify';

/**
 * Чтение буфера. Любая осечка — просто пустая строка, дальше спросим в окне.
 *
 * Прав на буфер может не быть (в Chrome разрешение «clipboard-read» бывает
 * выключено — проверено 05.10.2026, браузер отвечает `Read permission denied`),
 * а может быть «спросить»: тогда Chrome показывает свою кнопку «Вставить» и
 * ЖДЁТ ответа. Если человек её не замечает, обещание не разрешается никогда —
 * кнопка «Ссылка» выглядела бы сломанной. Поэтому ждём не дольше `timeoutMs`,
 * а опоздавший ответ ловит `onLate` (подставит адрес в уже открытое окно).
 */
const CLIPBOARD_WAIT_MS = 500;

function readClipboard(onLate?: (text: string) => void, timeoutMs = CLIPBOARD_WAIT_MS): Promise<string> {
  if (!navigator.clipboard?.readText) return Promise.resolve('');
  let settled = false;
  const read = navigator.clipboard
    .readText()
    .then((text) => text || '')
    .catch(() => '');
  read.then((text) => {
    if (settled && text) onLate?.(text);
  });
  return Promise.race([
    read,
    new Promise<string>((resolve) => setTimeout(() => resolve(''), timeoutMs)),
  ]).then((text) => {
    settled = true;
    return text;
  });
}

function shorten(url: string, max = 44): string {
  return url.length <= max ? url : `${url.slice(0, max - 1)}…`;
}

export interface LinkPromptState {
  /** Спросить адрес и отдать его в `apply`. Аргумент — выделенный текст. */
  requestLink: (selectedText: string) => Promise<void>;
  /** Окно (портал) — отрисовать рядом с редактором. */
  linkModal: React.ReactNode;
}

/**
 * @param apply получает готовый href. Выделение к этому моменту может быть
 *   потеряно (окно забирало фокус), поэтому восстанавливает его вызывающий —
 *   он один знает про своё поле.
 */
export function useLinkPrompt(apply: (href: string) => void): LinkPromptState {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [hint, setHint] = useState('');
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const requestLink = useCallback(
    async (selectedText: string) => {
      const selected = (selectedText || '').trim();
      // 1. Выделен сам адрес.
      if (isUrl(selected)) {
        apply(toHref(selected));
        return;
      }
      // 2. Адрес в буфере обмена.
      const clip = (
        await readClipboard((late) => {
          // Буфер пришёл, когда окно уже открылось (человек всё-таки нажал
          // «Вставить» в запросе Chrome): подставляем в пустое поле, но НЕ
          // вешаем молча — он уже смотрит на окно и жмёт сам.
          const url = extractUrl(late.trim());
          if (url) {
            setDraft((prev) => (prev ? prev : url));
            setHint('Адрес из буфера подставлен — проверьте и нажмите «Вставить».');
          }
        })
      ).trim();
      const fromClip = extractUrl(clip);
      if (fromClip) {
        apply(toHref(fromClip));
        // Говорим, ЧТО повесили: в буфере мог лежать адрес позавчерашней
        // вкладки, и молча превращать слово в чужую ссылку нечестно.
        toast.success(`Ссылка: ${shorten(fromClip)}`);
        return;
      }
      // 3. Наше окно. Подставляем буфер, только если адреса в нём ДВА и больше:
      // человеку остаётся стереть лишний. Текст без адресов в поле не кладём —
      // его пришлось бы сначала удалять.
      setDraft(extractUrls(clip).length > 1 && clip.length <= 300 ? clip : '');
      setHint(
        clip
          ? 'В буфере обмена не нашли адрес — проверьте поле и поправьте.'
          : 'Скопируйте адрес — в следующий раз он подставится сам.',
      );
      setError('');
      setOpen(true);
    },
    [apply],
  );

  const close = useCallback(() => {
    setOpen(false);
    setDraft('');
    setError('');
  }, []);

  const submit = useCallback(() => {
    const raw = draft.trim();
    if (!raw) {
      setError('Впишите адрес.');
      return;
    }
    const urls = isUrl(raw) ? [raw] : extractUrls(raw);
    if (urls.length > 1) {
      setError('Здесь несколько адресов — оставьте один.');
      return;
    }
    if (urls.length === 0) {
      setError('Не похоже на адрес. Например: hh.ru/resume/1');
      return;
    }
    close();
    apply(toHref(urls[0]));
  }, [apply, close, draft]);

  // Фокус в поле — чтобы адрес можно было сразу вставить (Cmd+V) и нажать Enter.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
    return () => clearTimeout(t);
  }, [open]);

  const linkModal = open
    ? createPortal(
        <div
          className="hf-confirm-modal-backdrop"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) close();
          }}
        >
          <div
            className="hf-confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Вставить ссылку"
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation();
                close();
              }
            }}
          >
            <p className="hf-confirm-modal-title">Вставить ссылку</p>
            <p className="hf-confirm-modal-subtitle">{hint}</p>
            <input
              ref={inputRef}
              type="text"
              value={draft}
              placeholder="hh.ru/resume/1"
              onChange={(e) => {
                setDraft(e.target.value);
                if (error) setError('');
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  submit();
                }
              }}
              className="mt-[var(--hf-space-m)] h-[33px] w-full rounded-[var(--hf-radius-s)] border border-[color:var(--hf-black-alpha-16)] bg-transparent px-[var(--hf-space-m)] text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-primary)] text-[var(--hf-main-900)] placeholder:text-[var(--hf-main-600)] focus:border-[var(--hf-cyan-500)] focus:outline-none"
            />
            {error && <p className="hf-confirm-modal-danger-text">{error}</p>}
            <div className="hf-confirm-modal-actions">
              <button type="button" className="hf-confirm-modal-cancel" onClick={close}>
                Отмена
              </button>
              <button
                type="button"
                onClick={submit}
                className="inline-flex h-[33px] min-w-[74px] items-center justify-center rounded-[var(--hf-radius-s)] border border-[var(--hf-main-900)] bg-[var(--hf-main-900)] px-[11px] text-[length:var(--hf-fs-xxs)] font-medium leading-[var(--hf-lh-secondary)] !text-[var(--hf-white)] transition-colors hover:bg-[var(--hf-main-800)]"
              >
                Вставить
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )
    : null;

  return { requestLink, linkModal };
}

/**
 * Повесить ссылку на выделение РУКАМИ, без execCommand.
 *
 * `document.execCommand('createLink')` на выделении, восстановленном из кода
 * (а после нашего окна оно всегда восстановленное — фокус уходил в поле), в
 * Chrome молча не срабатывает: та же грабля, что и у подсветки адреса при
 * наборе в HuntflowRichInput.
 */
export function wrapRangeWithLink(range: Range, href: string): boolean {
  const anchor = range.commonAncestorContainer.ownerDocument?.createElement('a')
    ?? document.createElement('a');
  anchor.setAttribute('href', href);
  try {
    range.surroundContents(anchor);
    return true;
  } catch {
    // Выделение задело границы тегов («жир<b>ное</b> слово») — собираем узел сами.
    try {
      anchor.appendChild(range.extractContents());
      range.insertNode(anchor);
      // От разрезанного <b> остаётся пустой огрызок — он невидим, но мусорит в
      // сохранённом HTML комментария. «Пустой» — это и <b></b>, и <b> с пустым
      // текстовым узлом внутри (именно так его оставляет extractContents).
      for (const side of [anchor.previousSibling, anchor.nextSibling]) {
        if (side?.nodeType !== Node.ELEMENT_NODE) continue;
        const el = side as Element;
        if (!el.textContent?.trim() && !el.querySelector('br, img')) {
          el.remove();
        }
      }
      return true;
    } catch {
      return false;
    }
  }
}
