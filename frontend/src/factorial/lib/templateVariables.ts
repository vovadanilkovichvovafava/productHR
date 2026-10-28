// Переменные шаблонов документов — те же, что подставляет сервер
// (routes/documents.py, _render_template). Добавили переменную там — добавьте здесь.
export const TEMPLATE_VARIABLES = [
  'full_name', 'last_name', 'first_name', 'middle_name', 'name', 'email', 'phone', 'telegram',
  'position', 'department', 'date', 'birth_date', 'passport_number', 'passport_issued',
  'passport_issued_by', 'address', 'inn', 'snils', 'signature',
] as const as readonly string[];
