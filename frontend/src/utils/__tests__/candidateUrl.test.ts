import { describe, it, expect } from 'vitest';
import { cardAfterSearchChange, computeEntityParamUpdate, shouldAdoptUrlEntity, urlLeadsSelection } from '../candidateUrl';

describe('computeEntityParamUpdate', () => {
  it('sets entity when a profile opens', () => {
    const next = computeEntityParamUpdate(new URLSearchParams(''), 123, null);
    expect(next?.get('entity')).toBe('123');
  });

  it('returns null when entity already matches the open id (loop guard)', () => {
    const next = computeEntityParamUpdate(new URLSearchParams('entity=123'), 123, 123);
    expect(next).toBeNull();
  });

  it('switches entity when a different profile opens', () => {
    const next = computeEntityParamUpdate(new URLSearchParams('entity=1'), 2, 1);
    expect(next?.get('entity')).toBe('2');
  });

  it('preserves other params when setting entity', () => {
    const next = computeEntityParamUpdate(new URLSearchParams('tab=anketa&q=ivan'), 5, null);
    expect(next?.get('entity')).toBe('5');
    expect(next?.get('tab')).toBe('anketa');
    expect(next?.get('q')).toBe('ivan');
  });

  it('clears entity/edit/tab on a genuine close (selected -> null)', () => {
    const next = computeEntityParamUpdate(new URLSearchParams('entity=9&edit=1&tab=anketa'), null, 9);
    expect(next?.has('entity')).toBe(false);
    expect(next?.has('edit')).toBe(false);
    expect(next?.has('tab')).toBe(false);
  });

  it('does NOT touch entity while a deep-link is pending (null -> null)', () => {
    // selectedCard is still null (board not yet refiltered) but entity is in the URL.
    const next = computeEntityParamUpdate(new URLSearchParams('entity=123'), null, null);
    expect(next).toBeNull();
  });

  it('returns null on close when there was nothing to clear', () => {
    const next = computeEntityParamUpdate(new URLSearchParams('q=ivan'), null, 9);
    expect(next).toBeNull();
  });
});

describe('shouldAdoptUrlEntity', () => {
  it('does NOT adopt when the selection just changed (fresh click, URL lagging)', () => {
    expect(shouldAdoptUrlEntity(2, 1, true)).toBe(false);
  });

  it('adopts a genuine URL change while a different card is shown (toast-navigate / back)', () => {
    expect(shouldAdoptUrlEntity(1, 5, false)).toBe(true);
  });

  it('adopts a deep-link when nothing is selected yet', () => {
    expect(shouldAdoptUrlEntity(null, 5, false)).toBe(true);
  });

  it('does not adopt when already showing the URL entity', () => {
    expect(shouldAdoptUrlEntity(5, 5, false)).toBe(false);
  });

  it('treats an already-synced URL as nothing-to-adopt even mid-click', () => {
    expect(shouldAdoptUrlEntity(5, 5, true)).toBe(false);
  });

  it('trusts the click when selection changed to a third value', () => {
    expect(shouldAdoptUrlEntity(3, 5, true)).toBe(false);
  });
});

// Мария, 09.10.2026: «когда ищешь кандидата, если такого нет, лишних cv не
// должно показывать» — слева «Нет кандидатов», справа висела чужая карточка.
describe('cardAfterSearchChange', () => {
  const row = (id: number) => ({ card: { id }, status: 'new' });

  it('поиск ничего не нашёл — профиль закрывается', () => {
    expect(cardAfterSearchChange([], 8, true)).toBeNull();
  });

  it('открытого нет в выдаче — открывается первый найденный', () => {
    expect(cardAfterSearchChange([row(5), row(6)], 8, true)).toEqual(row(5));
  });

  it('открытый в выдаче есть — его не трогаем', () => {
    expect(cardAfterSearchChange([row(5), row(8)], 8, true)).toBeUndefined();
  });

  it('поиск не менялся — не трогаем, даже если списка нет', () => {
    // Диплинк из расширения на кандидата не с доски и фоновое обновление во
    // время правки имени (кандидат перестал совпадать с запросом).
    expect(cardAfterSearchChange([], 8, false)).toBeUndefined();
    expect(cardAfterSearchChange([row(5)], 8, false)).toBeUndefined();
  });

  it('ничего не открыто — решает обычная логика выбора', () => {
    expect(cardAfterSearchChange([row(5)], null, true)).toBeUndefined();
  });
});

describe('urlLeadsSelection', () => {
  // Эльвира, 19.10.2026: после добавления из файла экран прыгал между новым
  // кандидатом и прежним. Окно добавления поставило ?entity=<новый>, а зеркало
  // «выбор → адрес» писало прежнего обратно — и так по кругу.
  it('адрес сменился сам при прежнем выборе — зеркалу молчать', () => {
    expect(urlLeadsSelection(new URLSearchParams('entity=17268'), 16673, 16673)).toBe(true);
  });

  it('клик по другой карточке — адрес догоняет выбор, как раньше', () => {
    expect(urlLeadsSelection(new URLSearchParams('entity=1'), 2, 1)).toBe(false);
  });

  it('адрес и выбор совпадают — спорить не о чем', () => {
    expect(urlLeadsSelection(new URLSearchParams('entity=5'), 5, 5)).toBe(false);
  });

  it('в адресе кандидата нет — зеркало вправе его вписать', () => {
    expect(urlLeadsSelection(new URLSearchParams('stage=new'), 5, 5)).toBe(false);
  });

  it('ничего не открыто — решает старая логика закрытия/диплинка', () => {
    expect(urlLeadsSelection(new URLSearchParams('entity=5'), null, null)).toBe(false);
  });

  it('прогон по кругу: с новым правилом цикл обрывается на первом шаге', () => {
    // Модель двух эффектов: «адрес → выбор» подхватывает адрес, если выбор не
    // менялся; зеркало пишет выбор в адрес, если его не остановили.
    let selected = 16673;
    let prevSelected = 16673;
    let url = new URLSearchParams('entity=17268'); // окно добавления открыло нового
    const writes: string[] = [];
    for (let i = 0; i < 6; i += 1) {
      const selChanged = selected !== prevSelected;
      const urlId = Number(url.get('entity'));
      const adopt = shouldAdoptUrlEntity(selected, urlId, selChanged);
      // зеркало в том же проходе видит СТАРЫЙ выбор
      if (!urlLeadsSelection(url, selected, prevSelected)) {
        const next = computeEntityParamUpdate(url, selected, prevSelected);
        if (next) { url = next; writes.push(next.get('entity')!); }
      }
      prevSelected = selected;
      if (adopt) selected = urlId;
    }
    expect(selected).toBe(17268);
    expect(url.get('entity')).toBe('17268');
    expect(writes).toEqual([]);
  });
});
