import { describe, expect, it } from 'vitest';
import { inviteErrorText } from '../inviteError';

const err = (status: number, detail: unknown) => ({ response: { status, data: { detail } } });

describe('inviteErrorText', () => {
  it('валидация email — по-русски, без текста Pydantic', () => {
    expect(inviteErrorText(err(422, [{ msg: 'value is not a valid email address' }]), 'x')).toMatch(/Проверьте email/);
  });
  it('уже в организации — понятная подсказка', () => {
    expect(inviteErrorText(err(400, 'Этот человек уже состоит в организации'), 'x')).toMatch(/уже зарегистрирован/);
  });
  it('прочие ошибки — текст сервера или запасной', () => {
    expect(inviteErrorText(err(403, 'Роль рекрутёра выдаёт только администратор'), 'x')).toBe('Роль рекрутёра выдаёт только администратор');
    expect(inviteErrorText(new Error(''), 'запасной')).toBe('запасной');
  });
});
