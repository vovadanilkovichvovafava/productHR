import { getCurrencySymbol, SALARY_INPUT_CURRENCIES } from "@/utils/currency";
import { parseServerDate } from "@/utils/date";
import type { KanbanCard } from "@/services/api/candidates";

// Форматтеры карточки и списка «Все кандидаты» (вынесены из AllCandidatesPage, 20.10.2026).

export function getInitials(name: string): string {
  const p = name.trim().split(/\s+/);
  if (p.length >= 2) return (p[0][0] + p[1][0]).toUpperCase();
  return (p[0]?.[0] || "?").toUpperCase();
}

export function formatDateShort(dateStr: string): string {
  return parseServerDate(dateStr).toLocaleDateString("ru");
}

export function formatDateFull(dateStr: string): string {
  return parseServerDate(dateStr).toLocaleString("ru", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatInputDateRu(dateStr: string): string {
  if (!dateStr) return "";
  const [year, month, day] = dateStr.split("-");
  if (!year || !month || !day) return dateStr;
  return `${day}.${month}.${year}`;
}

export function parseRuDateInput(value: string): string {
  const match = value.trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (!match) return "";
  const [, day, month, year] = match;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

export function formatResumeSaved(dateStr: string): string {
  const date = new Date(dateStr);
  const months = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
  ];
  const day = date.getDate();
  const month = months[date.getMonth()];
  const year = date.getFullYear();
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${day} ${month} ${year} в ${hours}:${minutes}`;
}

export function formatPhoneDisplay(phone?: string): string {
  if (!phone) return "";
  const digits = phone.replace(/\D/g, "");
  const match = digits.match(/^7(\d{3})(\d{3})(\d{4})$/);
  if (match) return `+7 ${match[1]} ${match[2]} ${match[3]}`;
  return phone;
}

// «Зарплатные ожидания» хранится как СВОБОДНЫЙ ТЕКСТ (Entity.salary), без
// отдельных числовых полей — в отличие от VacancyForm/ParsedDataPreview/
// ContactForm. Чтобы валюта была видна и здесь, дописываем символ выбранной
// валюты в конец строки при сохранении и разбираем его обратно при
// открытии на редактирование (иначе повторное сохранение задваивало бы символ).
export function splitSalaryCurrency(raw: string): { amount: string; currency: string } {
  const trimmed = (raw || "").trim();
  for (const { value } of SALARY_INPUT_CURRENCIES) {
    const symbol = getCurrencySymbol(value);
    if (trimmed.endsWith(` ${symbol}`)) {
      return { amount: trimmed.slice(0, -(symbol.length + 1)).trim(), currency: value };
    }
  }
  return { amount: trimmed, currency: "RUB" };
}

export function joinSalaryCurrency(amount: string, currency: string): string {
  const trimmed = amount.trim();
  if (!trimmed) return "";
  return `${trimmed} ${getCurrencySymbol(currency)}`;
}

export function formatPhoneForEdit(phone?: string): string {
  if (!phone) return "";
  let digits = phone.replace(/\D/g, "");
  if (digits.length === 10) digits = `7${digits}`;
  if (digits.length === 11 && digits.startsWith("8")) {
    digits = `7${digits.slice(1)}`;
  }
  const match = digits.match(/^7(\d{3})(\d{3})(\d{4})$/);
  if (match) return `+7 (${match[1]}) ${match[2]}${match[3]}`;
  return phone;
}

export function getVacancyStageLabel(card: KanbanCard): string | undefined {
  if (!card.vacancy_name) return undefined;
  const department =
    typeof card.extra_data?.vacancy_department === "string"
      ? card.extra_data.vacancy_department.trim()
      : "";
  return department
    ? `${card.vacancy_name} (${department})`
    : card.vacancy_name;
}

export function getInterviewVacancyLabel(card: KanbanCard): string {
  const vacancyName = card.vacancy_name || card.position || "Вакансия";
  const department =
    typeof card.extra_data?.vacancy_department === "string"
      ? card.extra_data.vacancy_department.trim()
      : "";
  return department ? `${vacancyName} / ${department}` : vacancyName;
}

