// Пути модуля «Управление» — под /factorial (модуль смонтирован как /factorial/*).
// Таблица ROUTES со ссылками на демо-экраны удалена 27.10.2026 вместе с ними.

// Вкладки профиля (6 шт.). base = '/factorial/profile' (свой ЛК) или '/factorial/employees/:id' (HR-вид).
export function buildProfileTabs(base: string) {
  return [
    { label: 'Обзор', href: base, end: true },
    { label: 'Детали работы', href: `${base}/work-details` },
    { label: 'Личные данные', href: `${base}/personal` },
    { label: 'Соглашения', href: base === '/factorial/profile' ? '/factorial/my-documents' : `${base}/agreements` },
    { label: 'Документы', href: `${base}/documents` },
    { label: 'Отпуска', href: `${base}/time-off` },
  ];
}
export const CABINET_TABS = buildProfileTabs('/factorial/profile');
