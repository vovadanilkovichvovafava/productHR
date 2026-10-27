/**
 * Публичная анкета: черновик ответов, понятная ошибка отправки и отчёт о сбое.
 *
 * Случай 17.10.2026 (кандидат Vladislav Antoseac, «Анкета для кандидатов в
 * отдел маркетинга»): кандидат пять раз подряд жал «Отправить», видел «Произошла
 * ошибка при отправке» и перезагружал страницу, а при каждой перезагрузке 23
 * ответа стирались. По логам бэкенда и nginx запрос отправки до нас НЕ ДОШЁЛ ни
 * разу — оборвался в браузере или сети кандидата, следов у нас не осталось.
 * Отсюда три вещи:
 *  1. ответы хранятся на устройстве кандидата и переживают перезагрузку;
 *  2. ошибка говорит, ЧТО случилось и что делать, а не «произошла ошибка»;
 *  3. браузер сам сообщает нам о сбое — в обход того пути, который сломался.
 */

const DRAFT_PREFIX = 'hf-public-form-draft:';

/** Ключ черновика: личная ссылка и общая анкета не пересекаются. */
export function draftKey(link: { token?: string; slug?: string }): string | null {
  if (link.token) return `${DRAFT_PREFIX}t:${link.token}`;
  if (link.slug) return `${DRAFT_PREFIX}s:${link.slug}`;
  return null;
}

/** Хранилище может быть недоступно (приватный режим, запрет на данные сайта). */
export function loadDraft(key: string | null): Record<string, unknown> | null {
  if (!key) return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveDraft(key: string | null, values: Record<string, unknown>): void {
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(values));
  } catch {
    /* нет места или запрещено — анкета работает и без черновика */
  }
}

export function clearDraft(key: string | null): void {
  if (!key) return;
  try {
    localStorage.removeItem(key);
  } catch {
    /* ничего */
  }
}

/** Есть ли в черновике хоть один заполненный ответ (пустые строки и [] не в счёт). */
export function hasAnswers(values: Record<string, unknown> | null): boolean {
  if (!values) return false;
  return Object.values(values).some((v) =>
    Array.isArray(v) ? v.length > 0 : v !== '' && v !== null && v !== undefined,
  );
}

/**
 * Черновик поверх пустой анкеты — только по полям, которые в ней ЕСТЬ: если
 * рекрутёр поменял анкету, ответы на удалённые вопросы не воскресают.
 */
export function mergeDraft(
  defaults: Record<string, unknown>,
  draft: Record<string, unknown> | null,
  fileFieldIds: Iterable<string> = [],
): Record<string, unknown> {
  if (!draft) return defaults;
  // Сам файл после F5 не вернуть (браузер его не хранит), а имя в черновике
  // осталось бы: обязательный «Файл» считался заполненным, и анкета уходила без
  // файла (20.10.2026). Поэтому файловые поля всегда начинаются пустыми.
  const skip = new Set(fileFieldIds);
  const out = { ...defaults };
  for (const id of Object.keys(defaults)) {
    if (id in draft && !skip.has(id)) out[id] = draft[id];
  }
  return out;
}

export type SubmitErrorKind = 'server_detail' | 'server_status' | 'network' | 'client';

export interface SubmitErrorInfo {
  kind: SubmitErrorKind;
  /** Что показать кандидату. */
  message: string;
  status?: number;
  /** Техническое описание — уходит нам в отчёт, кандидату не показывается. */
  technical: string;
}

const SAVED = 'Ваши ответы сохранены на этом устройстве.';

export function describeSubmitError(err: unknown): SubmitErrorInfo {
  const e = err as {
    response?: { status?: number; data?: { detail?: unknown } };
    code?: string;
    message?: string;
    name?: string;
    isAxiosError?: boolean;
  };
  const technical = `${e?.name || 'Error'}: ${e?.code || ''} ${e?.message || String(err)}`.trim();
  const response = e?.response;

  if (response) {
    const detail = response.data?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return { kind: 'server_detail', message: detail, status: response.status, technical };
    }
    // FastAPI 422: detail — список {msg}. Раньше такой ответ превращался в
    // «Произошла ошибка при отправке» без объяснения.
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
        .filter(Boolean);
      if (msgs.length) {
        return {
          kind: 'server_detail',
          message: `Проверьте ответы: ${msgs.join('; ')}`,
          status: response.status,
          technical,
        };
      }
    }
    return {
      kind: 'server_status',
      message: `Сервер не смог принять анкету (ошибка ${response.status ?? '—'}). ${SAVED} Попробуйте отправить ещё раз через минуту.`,
      status: response.status,
      technical,
    };
  }

  // Ответа нет. Если это сетевой сбой axios — запрос не дошёл до сервера.
  if (e?.isAxiosError || e?.code === 'ERR_NETWORK' || e?.code === 'ECONNABORTED' || e?.message === 'Network Error') {
    return {
      kind: 'network',
      message: `Не удалось связаться с сервером. Проверьте интернет или выключите VPN и нажмите «Отправить» ещё раз. ${SAVED}`,
      technical,
    };
  }

  // Ошибка в самом браузере, до сети.
  return {
    kind: 'client',
    message: `Не получилось отправить анкету из-за сбоя в браузере. ${SAVED} Обновите страницу и попробуйте ещё раз; если не выйдет — откройте ссылку в другом браузере.`,
    technical,
  };
}

/**
 * Сообщить нам о сбое. НЕ через axios: если сломался именно он (или его
 * перехватчики), отчёт не должен сломаться вместе с ним. sendBeacon доходит даже
 * при уходе со страницы; fetch с keepalive — запасной путь.
 */
export function reportSubmitError(link: { token?: string; slug?: string }, info: SubmitErrorInfo): void {
  const payload = JSON.stringify({
    // Ссылка — секрет кандидата: целиком её в лог не пишем, хватит начала.
    link: (link.token || link.slug || '').slice(0, 6),
    kind: info.kind,
    status: info.status ?? null,
    message: info.technical.slice(0, 500),
    online: typeof navigator !== 'undefined' ? navigator.onLine : null,
  });
  const url = '/api/forms/public/client-error';
  try {
    if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      const ok = navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }));
      if (ok) return;
    }
  } catch {
    /* падаем на fetch */
  }
  try {
    void fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
      credentials: 'omit',
    }).catch(() => {});
  } catch {
    /* отчёт — не повод ломать страницу */
  }
}
