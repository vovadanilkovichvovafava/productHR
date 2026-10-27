import { useCallback, useEffect, useState } from "react";

/**
 * Черновики комментариев: ключ — «кандидат:заявка».
 *
 * Держим и в памяти, и в localStorage: память переживает переключение карточек
 * внутри вкладки, localStorage — случайную перезагрузку. Любая осечка хранилища
 * (приватное окно, запрет на данные сайта) не должна ронять редактор, поэтому
 * обе операции в try/catch, а память — источник правды.
 */
const COMMENT_DRAFT_PREFIX = "hf-comment-draft:";
const commentDrafts = new Map<string, string>();

export function readCommentDraft(key: string): string {
  const inMemory = commentDrafts.get(key);
  if (inMemory !== undefined) return inMemory;
  try {
    return localStorage.getItem(COMMENT_DRAFT_PREFIX + key) || "";
  } catch {
    return "";
  }
}

export function writeCommentDraft(key: string, value: string): void {
  if (value) commentDrafts.set(key, value);
  else commentDrafts.delete(key);
  try {
    if (value) localStorage.setItem(COMMENT_DRAFT_PREFIX + key, value);
    else localStorage.removeItem(COMMENT_DRAFT_PREFIX + key);
  } catch {
    /* приватное окно — хватит памяти */
  }
}

/**
 * Текст комментария карточки, переживающий переключение карточек и
 * перезагрузку вкладки. Пишем черновик при каждом изменении; пустая строка —
 * стереть (после успешного сохранения или «Отмена»).
 */
export function useCommentDraft(draftKey: string): [string, (next: string) => void] {
  const [comment, setCommentState] = useState(() => readCommentDraft(draftKey));
  const setComment = useCallback(
    (next: string) => {
      setCommentState(next);
      writeCommentDraft(draftKey, next);
    },
    [draftKey],
  );
  // Открытая карточка сменилась (тот же компонент, другой кандидат) — показываем
  // черновик нового, а не текст предыдущего.
  useEffect(() => {
    setCommentState(readCommentDraft(draftKey));
  }, [draftKey]);
  return [comment, setComment];
}
