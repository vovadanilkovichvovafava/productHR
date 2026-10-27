/**
 * Ссылки в тексте (05.10.2026, просьба Марии: «вставлять ссылки без доп
 * действий, чтобы они были кликабельны»).
 *
 * Главное, за чем тут следим, — чтобы «умное» распознавание не начало лепить
 * ссылки из обычных слов с точками: «и.т.д», «2.5», «ООО «Ромашка»».
 */
import { describe, it, expect } from 'vitest';

import {
  autoLinkify,
  extractUrl,
  extractUrls,
  isUrl,
  linkifyToHtml,
  toHref,
  trimTrailingPunctuation,
} from '../linkify';

describe('isUrl — что считаем адресом', () => {
  it.each([
    'https://hh.ru/resume/123',
    'http://example.com',
    'www.rabota.by',
    'hh.ru/resume/123',
    't.me/ivanov',
    'docs.google.com/document/d/1x/edit?usp=sharing',
  ])('адрес: %s', (value) => {
    expect(isUrl(value)).toBe(true);
  });

  it.each([
    'и.т.д',
    '2.5',
    'Иванов',
    'ivan@example.com',
    'файл.docx',
    '',
    'две ссылки hh.ru hh.ru',
  ])('не адрес: %s', (value) => {
    expect(isUrl(value)).toBe(false);
  });
});

describe('Хвостовая пунктуация', () => {
  it('точка в конце предложения в ссылку не входит', () => {
    expect(trimTrailingPunctuation('https://hh.ru/resume/1.')).toEqual({
      url: 'https://hh.ru/resume/1',
      tail: '.',
    });
  });

  it('парная скобка внутри адреса остаётся', () => {
    const { url } = trimTrailingPunctuation('https://ru.wikipedia.org/wiki/C_(язык)');
    expect(url).toBe('https://ru.wikipedia.org/wiki/C_(язык)');
  });
});

describe('linkifyToHtml', () => {
  it('адрес становится ссылкой, остальной текст сохраняется', () => {
    expect(linkifyToHtml('смотри https://hh.ru/resume/1 там всё')).toBe(
      'смотри <a href="https://hh.ru/resume/1">https://hh.ru/resume/1</a> там всё',
    );
  });

  it('без схемы подставляется https, а показывается как набрали', () => {
    expect(linkifyToHtml('hh.ru/resume/1')).toBe(
      '<a href="https://hh.ru/resume/1">hh.ru/resume/1</a>',
    );
  });

  it('текст экранируется — чужой HTML не исполняется', () => {
    expect(linkifyToHtml('<img src=x onerror=alert(1)>')).not.toContain('<img');
  });

  it('точка в конце не съедается ссылкой', () => {
    expect(linkifyToHtml('тут https://hh.ru.')).toBe(
      'тут <a href="https://hh.ru">https://hh.ru</a>.',
    );
  });

  it('обычный текст не трогаем', () => {
    expect(linkifyToHtml('и.т.д, версия 2.5')).toBe('и.т.д, версия 2.5');
  });
});

describe('toHref', () => {
  it('схему добавляем только когда её нет', () => {
    expect(toHref('hh.ru')).toBe('https://hh.ru');
    expect(toHref('http://hh.ru')).toBe('http://hh.ru');
    expect(toHref('https://hh.ru')).toBe('https://hh.ru');
  });
});

describe('autoLinkify (старые описания вакансий)', () => {
  it('готовый HTML не трогает', () => {
    const html = '<p>Уже <a href="https://hh.ru">ссылка</a></p>';
    expect(autoLinkify(html)).toBe(html);
  });

  it('простой текст превращает в HTML со ссылкой', () => {
    expect(autoLinkify('тут https://hh.ru')).toContain('<a href="https://hh.ru"');
  });
});

describe('extractUrl — адрес из буфера обмена для кнопки «Ссылка»', () => {
  it('адрес среди слов находится («ссылка с ещё одним словом»)', () => {
    expect(extractUrl('вот ссылка https://hh.ru/resume/1 посмотри')).toBe('https://hh.ru/resume/1');
  });

  it('хвостовая точка и пробелы не мешают', () => {
    expect(extractUrl('  hh.ru/resume/1.  ')).toBe('hh.ru/resume/1');
  });

  it('в буфере не адрес — null, спросим в окне', () => {
    expect(extractUrl('Иванов Иван, 2.5 года опыта')).toBeNull();
    expect(extractUrl('')).toBeNull();
  });

  it('несколько адресов — null: гадать, какой из них имели в виду, нельзя', () => {
    expect(extractUrl('hh.ru/1 и rabota.by/2')).toBeNull();
    expect(extractUrls('hh.ru/1 и rabota.by/2')).toEqual(['hh.ru/1', 'rabota.by/2']);
  });
});
