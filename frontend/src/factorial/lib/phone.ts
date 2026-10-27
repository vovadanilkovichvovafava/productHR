// Ввод телефона сотрудника.
//
// Российский/казахстанский номер (+7, 7…, 8 9…) собирается в шаблон
// +7 (XXX) XXX-XX-XX по мере набора. Всё остальное (+375, +998, «80 29…» —
// белорусский местный, и т.п.) НЕ переписывается: цифры не теряются, номер не
// обрезается, из текста убираются только посторонние символы. До 27.10.2026
// любой номер превращался в «+7 (…)» с обрезкой до 11 цифр, причём уже при
// ОТКРЫТИИ окна — сохранение тихо портило номера сотрудников из других стран.
//
// Функция для поля ввода (onChange). Значение из базы при открытии окна через
// неё не пропускаем — показываем как есть.

const RU_MAX_DIGITS = 11;

// Цифры после «7», если номер похож на российский (+7 / 7 / 8 + не-ноль),
// иначе null. «8» без второй цифры ещё не российский: это может быть начало
// «80 29…» (Беларусь), и превращать его в «+7» рано.
function russianTail(raw: string): string | null {
  const plus = raw.trimStart().startsWith('+');
  const d = raw.replace(/\D/g, '');
  if (!d || d.length > RU_MAX_DIGITS) return null;
  let tail: string | null = null;
  if (d[0] === '7') tail = d.slice(1);
  else if (!plus && d[0] === '8' && d.length >= 2) tail = d.slice(1);
  if (tail === null) return null;
  // Код после +7 не начинается с нуля: «+70…»/«80…» — это не российский номер.
  if (tail.length > 0 && tail[0] === '0') return null;
  return tail;
}

function formatRussian(r: string): string {
  let s = '+7';
  if (r.length > 0) s += ' (' + r.slice(0, 3);
  if (r.length >= 3) s += ') ' + r.slice(3, 6);
  if (r.length >= 6) s += '-' + r.slice(6, 8);
  if (r.length >= 8) s += '-' + r.slice(8, 10);
  return s;
}

// Международный/неизвестный формат: оставляем цифры и привычные разделители
// так, как их ввёл человек; «+» — только первым символом.
function cleanInternational(raw: string): string {
  const trimmed = raw.trim();
  const plus = trimmed.startsWith('+');
  const body = trimmed
    .replace(/[^\d\s()\-]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return (plus ? '+' : '') + body;
}

export function formatPhone(raw: string): string {
  const s = raw || '';
  if (!s.trim()) return '';
  const tail = russianTail(s);
  if (tail !== null) return formatRussian(tail);
  return cleanInternational(s);
}

// Похож ли номер на полный: российский — 11 цифр, прочие — от 8 до 15 (E.164).
export function isPhoneComplete(value: string): boolean {
  const d = (value || '').replace(/\D/g, '');
  if (russianTail(value || '') !== null) return d.length === RU_MAX_DIGITS;
  return d.length >= 8 && d.length <= 15;
}
