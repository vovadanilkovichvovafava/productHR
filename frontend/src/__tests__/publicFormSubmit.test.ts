/**
 * Публичная анкета: черновик и понятная ошибка отправки (19.10.2026).
 * Случай 17.10: кандидат пять раз видел «Произошла ошибка при отправке», а при
 * каждой перезагрузке 23 ответа стирались; запрос до сервера не дошёл ни разу.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  draftKey,
  loadDraft,
  saveDraft,
  clearDraft,
  hasAnswers,
  mergeDraft,
  describeSubmitError,
  reportSubmitError,
} from '@/utils/publicFormSubmit';

beforeEach(() => {
  try {
    localStorage.clear();
  } catch {
    /* jsdom без хранилища */
  }
});

describe('черновик анкеты', () => {
  it('личная ссылка и общая анкета — разные ключи', () => {
    expect(draftKey({ token: 'abc' })).not.toBe(draftKey({ slug: 'abc' }));
    expect(draftKey({})).toBeNull();
  });

  it('переживает перезагрузку и стирается после отправки', () => {
    const key = draftKey({ token: 'tok' });
    saveDraft(key, { q1: 'Владислав', q2: ['a'] });
    expect(loadDraft(key)).toEqual({ q1: 'Владислав', q2: ['a'] });
    clearDraft(key);
    expect(loadDraft(key)).toBeNull();
  });

  it('битый черновик не ломает анкету', () => {
    localStorage.setItem('hf-public-form-draft:t:x', '{не json');
    expect(loadDraft('hf-public-form-draft:t:x')).toBeNull();
    localStorage.setItem('hf-public-form-draft:t:y', '[1,2]');
    expect(loadDraft('hf-public-form-draft:t:y')).toBeNull();
  });

  it('ответы на удалённые вопросы не воскресают', () => {
    const merged = mergeDraft({ q1: '', q2: [] }, { q1: 'да', gone: 'старый вопрос' });
    expect(merged).toEqual({ q1: 'да', q2: [] });
  });

  it('файл после F5 не вернуть — имя из черновика не засчитывается', () => {
    const merged = mergeDraft({ q1: '', cv: '' }, { q1: 'да', cv: 'резюме.pdf' }, ['cv']);
    expect(merged).toEqual({ q1: 'да', cv: '' });
  });

  it('пустой черновик — не повод показывать «восстановили»', () => {
    expect(hasAnswers({ q1: '', q2: [], q3: null })).toBe(false);
    expect(hasAnswers({ q1: '', q2: ['x'] })).toBe(true);
    expect(hasAnswers(null)).toBe(false);
  });
});

describe('ошибка отправки', () => {
  it('текст от сервера показываем как есть', () => {
    const info = describeSubmitError({ response: { status: 400, data: { detail: 'Анкета закрыта' } } });
    expect(info).toMatchObject({ kind: 'server_detail', message: 'Анкета закрыта' });
  });

  it('422 от FastAPI — список причин, а не «произошла ошибка»', () => {
    const info = describeSubmitError({
      response: { status: 422, data: { detail: [{ msg: 'field required' }, { msg: 'bad url' }] } },
    });
    expect(info.kind).toBe('server_detail');
    expect(info.message).toContain('field required; bad url');
  });

  it('сервер упал — номер ошибки и «ответы сохранены»', () => {
    const info = describeSubmitError({ response: { status: 502, data: '<html>' } });
    expect(info.kind).toBe('server_status');
    expect(info.message).toContain('502');
    expect(info.message).toContain('сохранены');
  });

  it('запрос не дошёл — про интернет и VPN', () => {
    const info = describeSubmitError({ isAxiosError: true, code: 'ERR_NETWORK', message: 'Network Error' });
    expect(info.kind).toBe('network');
    expect(info.message).toContain('VPN');
    expect(info.technical).toContain('ERR_NETWORK');
  });

  it('сбой в браузере — совет открыть в другом браузере', () => {
    const info = describeSubmitError(new TypeError('x is undefined'));
    expect(info.kind).toBe('client');
    expect(info.message).toContain('другом браузере');
    expect(info.technical).toContain('TypeError');
  });
});

describe('отчёт о сбое', () => {
  it('уходит мимо axios и не несёт ссылку целиком', async () => {
    const beacon = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, 'sendBeacon', { value: beacon, configurable: true });
    reportSubmitError({ token: 'hsG6UFTG111hsQtk' }, describeSubmitError({ isAxiosError: true, code: 'ERR_NETWORK' }));
    expect(beacon).toHaveBeenCalledTimes(1);
    const [url, blob] = beacon.mock.calls[0];
    expect(url).toBe('/api/forms/public/client-error');
    const text = await new Promise<string>((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result));
      r.readAsText(blob as Blob);
    });
    const body = JSON.parse(text);
    expect(body).toMatchObject({ link: 'hsG6UF', kind: 'network' });
  });
});
