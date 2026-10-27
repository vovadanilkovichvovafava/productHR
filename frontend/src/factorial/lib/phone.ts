// Маска телефона РФ: фиксированный шаблон +7 (XXX) XXX-XX-XX.
// Нельзя ввести лишние цифры (обрезается до 11) и формат всегда один.
export function formatPhone(raw: string): string {
  let d = (raw || '').replace(/\D/g, '');
  if (d.startsWith('8')) d = '7' + d.slice(1);
  if (d && !d.startsWith('7')) d = '7' + d;
  d = d.slice(0, 11);
  if (!d) return '';
  const r = d.slice(1); // до 10 цифр после «7»
  let s = '+7';
  if (r.length > 0) s += ' (' + r.slice(0, 3);
  if (r.length >= 3) s += ') ' + r.slice(3, 6);
  if (r.length >= 6) s += '-' + r.slice(6, 8);
  if (r.length >= 8) s += '-' + r.slice(8, 10);
  return s;
}

// Полностью ли заполнен номер (11 цифр) — для подсказки/валидации.
export function isPhoneComplete(formatted: string): boolean {
  return (formatted || '').replace(/\D/g, '').length === 11;
}
