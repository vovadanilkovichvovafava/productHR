import type { CatalogSection } from '@/factorial/templates/CatalogTemplate';

export const settingsCatalog: CatalogSection[] = [
  { heading: 'Общее', items: [
    { title: 'Внешние пользователи', description: 'Пользователи, не имеющие контракта с компанией, но имеющие доступ к Factorial.', href: '/settings/externals' },
    { title: 'Данные компании', description: 'Просмотрите и обновите данные вашей Компании.', href: '/settings/details' },
    { title: 'Данные о трудоустройстве', description: 'Определите условия труда и группы утверждения соглашений.', href: '/settings/contracts-settings' },
    { title: 'Документы', description: 'Организуйте папки с документами.', href: '/settings/folders' },
    { title: 'История импорта', description: 'Просматривайте и управляйте импортированными в Factorial данными.', href: '/settings/import-history' },
    { title: 'Места работы', description: 'Настройте и назначьте рабочие места и праздничные дни компании.', href: '/settings/locations' },
    { title: 'Настройки', description: 'Персонализируйте рабочее пространство вашей Компании.', href: '/settings/customizations' },
    { title: 'Настройки безопасности', description: 'Настройте, как сотрудники входят в Factorial и другие параметры безопасности.', href: '/settings/security' },
    { title: 'Подписка', description: 'Управляйте деталями вашей подписки.', href: '/settings/plans' },
    { title: 'Разрешения', description: 'Управляйте, какие сотрудники могут что видеть и делать.', href: '/settings/permissions' },
    { title: 'Страница компании', description: 'Опубликуйте и настройте публичную страницу для распространения информации.', href: '/settings/company-page' },
  ]},
  { heading: 'Время', items: [
    { title: 'Категории времени', description: 'Категоризируйте рабочие часы и установите для них значения.', href: '/settings/time-categories-settings' },
    { title: 'Отпуска', description: 'Настройте и назначьте Политику отпуска вашей Компании.', href: '/settings/timeoff-policies' },
    { title: 'Рабочие расписания', description: 'Настройте и назначьте рабочие расписания вашей Компании.', href: '/settings/work-schedule' },
  ]},
  { heading: 'Люди', items: [
    { title: 'Онбординг сотрудников', description: 'Управляйте пространством для онбординга.', href: '/settings/employee-onboarding' },
  ]},
  { heading: 'IT', items: [
    { title: 'Обращения', description: 'Управляйте командами обработки тикетов, категориями тикетов, приоритетами и целями SLA.', href: '/settings/ticketing' },
  ]},
  { heading: 'Финансы', items: [
    { title: 'Компенсация', description: 'Управление настройками вашей Компенсации.', href: '/settings/compensations' },
  ]},
  { heading: 'Расширенные настройки', items: [
    { title: 'Журнал аудита', description: 'Просматривайте записи событий и действий.', href: '/settings/audit-log' },
    { title: 'Настраиваемые уведомления', description: 'Настраивайте автоматические рутинные задачи в Factorial.', href: '/settings/automations' },
    { title: 'API-ключи', description: 'Генерируйте ключи доступа к вашему аккаунту.', href: '/settings/api-keys' },
  ]},
];
