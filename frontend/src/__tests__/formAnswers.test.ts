import { describe, expect, it } from 'vitest';
import { openKey, parseAnswerFilters, sendErrorText, statusChip } from '@/utils/formAnswers';

describe('parseAnswerFilters — F5 на «Анкеты → Ответы» оставляет на месте', () => {
  it('читает вкладку, анкету, отправителя, период и открытый ответ', () => {
    const f = parseAnswerFilters(new URLSearchParams('status=orphan&form=12&sender=3&days=30&open=s9'));
    expect(f).toEqual({ status: 'orphan', formId: 12, sentBy: 3, days: 30, open: { kind: 'orphan', id: 9 } });
    expect(parseAnswerFilters(new URLSearchParams('open=d41')).open).toEqual({ kind: 'dispatch', id: 41 });
  });

  it('мусор в адресе — значения по умолчанию', () => {
    const f = parseAnswerFilters(new URLSearchParams('status=xxx&form=abc&sender=-1&days=13&open=q5'));
    expect(f).toEqual({ status: 'all', formId: null, sentBy: null, days: null, open: null });
  });

  it('ключ строки совпадает с тем, что пишется в адрес', () => {
    expect(openKey({ kind: 'dispatch', id: 41 })).toBe('d41');
    expect(openKey({ kind: 'orphan', id: 9 })).toBe('s9');
  });
});

describe('statusChip', () => {
  const base = { opened_at: null, submitted_at: null, entity_name: null };
  it('у каждого статуса свой цвет', () => {
    expect(statusChip({ ...base, status: 'sent' })).toEqual({ label: 'Не открыта', tone: 'muted' });
    expect(statusChip({ ...base, status: 'opened' })).toEqual({ label: 'Открыта, не отправлена', tone: 'warn' });
    expect(statusChip({ ...base, status: 'submitted', submitted_at: '2026-11-05T11:20:00' }).tone).toBe('ok');
  });
  it('ответ без карточки и ответ, не видный в карточке, — разные слова', () => {
    expect(statusChip({ ...base, status: 'orphan' }).label).toBe('Без кандидата');
    expect(statusChip({ ...base, status: 'orphan', entity_name: 'Анна' }).label).toBe('Нет в карточке');
  });
});

describe('sendErrorText — что случилось у кандидата', () => {
  const err = { at: null, status: null, message: null, online: null };
  it('по виду сбоя', () => {
    expect(sendErrorText({ ...err, kind: 'network' })).toBe('Не отправилось: не дошло до сервера (интернет или VPN)');
    expect(sendErrorText({ ...err, kind: 'server_status', status: 502 })).toBe('Не отправилось: сервер ответил ошибкой 502');
    expect(sendErrorText({ ...err, kind: 'server_detail', message: 'Анкета закрыта' }))
      .toBe('Не отправилось: сервер отказал: Анкета закрыта');
    expect(sendErrorText({ ...err, kind: 'client', count: 5 })).toBe('Не отправилось: сбой в браузере кандидата (попыток: 5)');
  });
});
