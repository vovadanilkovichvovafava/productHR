import type { FormField } from '@/services/api/forms';

// Проверка анкеты перед сохранением шаблона и перед отправкой кандидату
// (20.10.2026). Конструктор пропускал то, на чём кандидат потом застревал:
// вопрос «выбор одного» без вариантов, шкалу с минимумом больше максимума
// (кнопок нет — обязательную шкалу не заполнить, анкета не отправится никогда),
// одинаковые варианты (выбираются вместе), вопрос без текста.

export const SCALE_MAX_STEPS = 20;
const CHOICE_TYPES: FormField['type'][] = ['select', 'multiselect', 'radio'];

/** Варианты без пустых и повторов (сравнение без учёта регистра и пробелов). */
export function cleanOptions(options: string[] | undefined): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of options || []) {
    const opt = (raw || '').trim();
    const key = opt.toLowerCase();
    if (!opt || seen.has(key)) continue;
    seen.add(key);
    out.push(opt);
  }
  return out;
}

/** Поля, готовые к сохранению: варианты почищены, у шкалы целые границы. */
export function normalizeFields(fields: FormField[]): FormField[] {
  return fields.map((f) => {
    const next: FormField = { ...f, label: (f.label || '').trim() };
    if (CHOICE_TYPES.includes(f.type)) next.options = cleanOptions(f.options);
    if (f.type === 'scale') {
      next.min = Number.isFinite(f.min) ? Math.trunc(f.min as number) : 1;
      next.max = Number.isFinite(f.max) ? Math.trunc(f.max as number) : 10;
    }
    return next;
  });
}

/** Первая проблема анкеты текстом для человека или null. */
export function formProblem(title: string, fields: FormField[]): string | null {
  if (!title.trim()) return 'Введите название анкеты';
  if (fields.length === 0) return 'Добавьте хотя бы один вопрос';
  for (let i = 0; i < fields.length; i++) {
    const f = fields[i];
    const n = `Вопрос ${i + 1}`;
    if (!(f.label || '').trim()) return `${n}: впишите текст вопроса`;
    if (CHOICE_TYPES.includes(f.type) && cleanOptions(f.options).length < 2) {
      return `${n} «${f.label.trim()}»: нужно хотя бы два разных варианта ответа`;
    }
    if (f.type === 'scale') {
      const min = f.min ?? 1;
      const max = f.max ?? 10;
      if (!(min < max)) return `${n} «${f.label.trim()}»: минимум шкалы должен быть меньше максимума`;
      if (max - min + 1 > SCALE_MAX_STEPS) {
        return `${n} «${f.label.trim()}»: в шкале не больше ${SCALE_MAX_STEPS} делений`;
      }
    }
  }
  return null;
}
