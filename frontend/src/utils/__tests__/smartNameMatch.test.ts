import { describe, it, expect } from 'vitest';
import { smartNameMatch, editDistance, switchLayout, contactMatch } from '@/utils/translit';

describe('editDistance', () => {
  it('handles empty strings', () => {
    expect(editDistance('', '')).toBe(0);
    expect(editDistance('abc', '')).toBe(3);
    expect(editDistance('', 'abc')).toBe(3);
  });
  it('counts single edits', () => {
    expect(editDistance('иванов', 'иваноф')).toBe(1); // 1 замена
    expect(editDistance('petyhov', 'pituhov')).toBe(2); // 2 замены
    expect(editDistance('kitten', 'sitting')).toBe(3);
  });
});

describe('smartNameMatch — умный поиск имени (клиент)', () => {
  it('пустой запрос — матчит всё', () => {
    expect(smartNameMatch('Иванов Иван', '')).toBe(true);
    expect(smartNameMatch('Иванов Иван', '   ')).toBe(true);
  });

  it('прямое вхождение', () => {
    expect(smartNameMatch('Иванов Иван', 'иван')).toBe(true);
    expect(smartNameMatch('Шобанов', 'шобанов')).toBe(true);
  });

  it('транслитерация EN→RU и RU→EN', () => {
    expect(smartNameMatch('Иванов Иван', 'ivanov ivan')).toBe(true);
    expect(smartNameMatch('Bogdan Petrov', 'богдан')).toBe(true);
  });

  it('независимость от порядка слов', () => {
    expect(smartNameMatch('Иванов Иван', 'иван иванов')).toBe(true);
    expect(smartNameMatch('Иванов Иван', 'иванов иван')).toBe(true);
  });

  it('терпимость к опечаткам (Левенштейн)', () => {
    expect(smartNameMatch('Иванов Иван', 'иваноф')).toBe(true); // опечатка в→ф
    expect(smartNameMatch('Питухов Богдан', 'petyhov')).toBe(true); // транслит+2 опечатки
    expect(smartNameMatch('Иван Тестовый', 'ivan testoviy')).toBe(true); // транслит+опечатка
  });

  it('не матчит чужое имя', () => {
    expect(smartNameMatch('Иванов Иван', 'сидоров')).toBe(false);
    expect(smartNameMatch('Иванов Иван', 'петров')).toBe(false);
  });

  it('флип раскладки клавиатуры (EN-раскладка, русское слово)', () => {
    // «иван», набранное в английской раскладке = «bdfy»
    expect(switchLayout('bdfy')).toBe('иван');
    expect(switchLayout('иван')).toBe('bdfy');
    expect(smartNameMatch('Петухов Иван Андреевич', 'bdfy')).toBe(true);
    expect(smartNameMatch('Иван', 'bdfy')).toBe(true);
    // латиница-транслит по-прежнему работает (не регресс)
    expect(smartNameMatch('Иван', 'ivan')).toBe(true);
  });

  it('Ё≡Е в обе стороны', () => {
    // Жалоба из прода: «Дёмин» не находился без Ё — приходилось гадать написание.
    expect(smartNameMatch('Дёмин Артём', 'демин')).toBe(true);
    expect(smartNameMatch('Дёмин Артём', 'артем')).toBe(true);
    expect(smartNameMatch('Демин Артем', 'дёмин')).toBe(true);
    expect(smartNameMatch('Демин Артем', 'артём')).toBe(true);
    expect(smartNameMatch('Королёв Пётр', 'королев петр')).toBe(true);
    expect(smartNameMatch('Королев Петр', 'королёв пётр')).toBe(true);
    // свёртка не расширяет поиск на чужих
    expect(smartNameMatch('Дёмин Артём', 'иванов')).toBe(false);
  });

  it('Ё≡Е вместе с транслитерацией', () => {
    // у «Дёмин» и «Демин» разный транслит (dyomin / demin) — ищем по обоим
    expect(smartNameMatch('Дёмин', 'demin')).toBe(true);
    expect(smartNameMatch('Дёмин', 'dyomin')).toBe(true);
  });

  it('короткие токены не прощают опечаток (нет шума)', () => {
    // «оле» (3 буквы) не должно фаззи-матчить «оля» — только точное/транслит
    expect(smartNameMatch('Ольга', 'оль')).toBe(true); // подстрока
    expect(smartNameMatch('Абв', 'xyz')).toBe(false);
  });
});

describe('contactMatch — поиск по контактам (клиент)', () => {
  it('почта — подстрока', () => {
    expect(contactMatch('mail.ru', { email: 'ivan@mail.ru' })).toBe(true);
    expect(contactMatch('IVAN', { email: 'ivan@mail.ru' })).toBe(true);
  });

  it('телефон — сырое вхождение и по одним цифрам', () => {
    expect(contactMatch('123-45', { phone: '+7 (999) 123-45-67' })).toBe(true);
    // цифрами без форматирования находит форматированный номер
    expect(contactMatch('9991234567', { phone: '+7 (999) 123-45-67' })).toBe(true);
    expect(contactMatch('1234567', { phone: '+7 (999) 123-45-67' })).toBe(true);
  });

  it('telegram — «@» необязателен', () => {
    expect(contactMatch('@ivan_hr', { telegram: 'ivan_hr' })).toBe(true);
    expect(contactMatch('ivan_hr', { telegram: 'ivan_hr' })).toBe(true);
    expect(contactMatch('ivan', { telegram: 'ivan_hr' })).toBe(true); // подстрока
  });

  it('пустой запрос и промах', () => {
    expect(contactMatch('', { email: 'a@b.ru' })).toBe(false);
    expect(contactMatch('xyz', { email: 'a@b.ru', phone: '123', telegram: 'joe' })).toBe(false);
  });
});
