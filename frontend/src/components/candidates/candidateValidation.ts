// Проверка полей кандидата для окон «Новый кандидат» и «Редактировать»
// (вынесена из AllCandidatesPage, 20.10.2026).

export const NAME_REGEX = /^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'\- ]{1,}$/;
// E.164: опциональный +, затем 7–15 цифр (после удаления пробелов/дефисов/скобок)
export const PHONE_DIGITS_REGEX = /^\+?\d{7,15}$/;
export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
// Telegram: 5–32 символа, буквы/цифры/подчёркивания, не может начинаться с цифры или подчёркивания
export const TELEGRAM_REGEX = /^[a-zA-Z][a-zA-Z0-9_]{4,31}$/;

export function normalizePhone(raw: string): string {
  return raw.replace(/[\s\-()]/g, "");
}

export function validateName(value: string): string | null {
  const v = value.trim();
  if (!v) return "Обязательное поле";
  if (v.length < 2) return "Минимум 2 символа";
  if (v.length > 200) return "Максимум 200 символов";
  if (!NAME_REGEX.test(v)) return "Только буквы, пробелы, дефис и апостроф";
  return null;
}

export function validatePhone(value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  const normalized = normalizePhone(v);
  if (!PHONE_DIGITS_REGEX.test(normalized)) {
    return "Формат: +7 999 123 4567 (7–15 цифр)";
  }
  return null;
}

export function validateEmail(value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  if (v.length > 254) return "Слишком длинный email";
  if (!EMAIL_REGEX.test(v)) return "Некорректный email";
  return null;
}

export function validateTelegram(value: string): string | null {
  const v = value.trim().replace(/^@/, "");
  if (!v) return null;
  if (!TELEGRAM_REGEX.test(v)) {
    return "5–32 символа, буквы/цифры/_, начинается с буквы";
  }
  return null;
}

export function validateFreeText(value: string, maxLen = 200): string | null {
  const v = value.trim();
  if (v.length > maxLen) return `Максимум ${maxLen} символов`;
  return null;
}

export const CANDIDATE_SOURCE_OPTIONS = [
  "Агентство",
  "Зарплата.ру",
  "Отклик с Хабр Карьеры",
  "Отклик с Avito",
  "Отклик с Farpost.ru",
  "Отклик с HeadHunter",
  "Отклик с Rabota.by",
  "Отклик с Rabota.ru",
  "Отклик с SuperJob",
  "Рекомендация",
  "Хабр Карьера",
  "AmazingHiring",
  "Artstation",
  "Avito",
  "Другой источник",
];

