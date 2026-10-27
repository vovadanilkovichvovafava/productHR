import type { Vacancy, VacancyStatus } from '@/types';

// Проверка полей и данные для сохранения формы вакансии (вынесено из
// VacancyForm, 20.10.2026, без изменения поведения). Под тестами:
// __tests__/vacancyFormPayload.test.ts.

export interface VacancyFormData {
  title: string;
  description: string;
  requirements: string;
  responsibilities: string;
  salary_min: string | number;
  salary_max: string | number;
  salary_currency: string;
  location: string;
  employment_type: string;
  experience_level: string;
  status: VacancyStatus;
  priority: number;
  /** Через запятую. */
  tags: string;
  visible_to_all: boolean;
  closes_at: string;
}

/** Текст ошибки для тоста или null, если всё в порядке. */
export function validateVacancyForm(
  f: Pick<VacancyFormData, 'title' | 'salary_min' | 'salary_max'> & { positionsCount?: string },
): string | null {
  if (!f.title.trim()) return 'Введите название вакансии';
  // На бэке validate_title требует ≥3 символов — раньше падало 422 с общим
  // тостом «Ошибка при создании», и было непонятно, что не так.
  if (f.title.trim().length < 3) return 'Название должно содержать минимум 3 символа';
  const minNum = f.salary_min !== '' ? Number(f.salary_min) : null;
  const maxNum = f.salary_max !== '' ? Number(f.salary_max) : null;
  if ((minNum !== null && minNum < 0) || (maxNum !== null && maxNum < 0)) return 'Зарплата не может быть отрицательной';
  if (minNum !== null && maxNum !== null && minNum > maxNum) return '"Зарплата от" не может быть больше "Зарплата до"';
  if (f.positionsCount !== undefined && !(Number.isInteger(Number(f.positionsCount)) && Number(f.positionsCount) >= 1)) {
    return 'Сколько человек нужно нанять — целое число от 1';
  }
  return null;
}

export function buildVacancyPayload(
  f: VacancyFormData,
  {
    vacancy, customerText, sandboxId, positionsCount,
  }: { vacancy?: Vacancy; customerText: string; sandboxId: string; positionsCount?: string },
) {
  return {
    title: f.title.trim(),
    description: f.description.trim() || undefined,
    requirements: f.requirements.trim() || undefined,
    responsibilities: f.responsibilities.trim() || undefined,
    salary_min: f.salary_min ? parseInt(String(f.salary_min)) : undefined,
    salary_max: f.salary_max ? parseInt(String(f.salary_max)) : undefined,
    salary_currency: f.salary_currency,
    location: f.location.trim() || undefined,
    employment_type: f.employment_type || undefined,
    experience_level: f.experience_level || undefined,
    status: f.status,
    priority: f.priority,
    tags: f.tags.split(',').map((t) => t.trim()).filter(Boolean),
    visible_to_all: f.visible_to_all,
    // Заказчик — только текст: hiring_manager_id всегда null (легаси-значение
    // при первом же сохранении конвертируется в customer_name). Явный null, а
    // не undefined: бэк применяет exclude_unset, и пропущенный ключ старое
    // значение не очистил бы.
    hiring_manager_id: null,
    // По той же причине null: «Без дедлайна» должен реально снимать дедлайн.
    closes_at: f.closes_at || null,
    // extra_data ЗАМЕНЯЕТСЯ на бэке целиком (не мержится) — обязательно
    // спредим существующий, иначе стирается cloned_from_request_id и
    // прочие служебные ключи при первом же редактировании заявки.
    extra_data: {
      ...(vacancy?.extra_data || {}),
      customer_name: customerText.trim() || undefined,
      // Песочница воронки: с практики человек попадёт именно в неё.
      board_sandbox_id: sandboxId ? Number(sandboxId) : undefined,
      // Сколько человек нужно нанять (пишет и бот, показывает предпросмотр заявки).
      ...(positionsCount !== undefined ? { positions_count: Math.max(1, Number(positionsCount) || 1) } : {}),
    },
  };
}

/** Причина из ответа бэка (422 валидация / 403 и т.п.), иначе общий текст. */
export function apiErrorDetail(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0] && typeof detail[0] === 'object') {
    const first = detail[0] as { msg?: string };
    if (first.msg) return first.msg;
  }
  return fallback;
}
