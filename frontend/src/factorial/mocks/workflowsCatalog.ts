import type { CatalogSection } from '@/factorial/templates/CatalogTemplate';

export const workflowsCatalog: CatalogSection[] = [
  {
    items: [
      { title: 'Онбординг', description: 'Начните работу с вашим сотрудником за считанные секунды', href: '/workflows/onboarding' },
      { title: 'Офбординг', description: 'Streamline the leaving process to ensure clear communication on an employee\'s departure terms.', href: '/workflows/offboarding' },
      { title: 'Обучение', description: 'Отслеживайте все документы, связанные с вашими курсами, включая дипломы, списки посещаемости и другие.', href: '/workflows/training', locked: true },
      { title: 'Пользовательский рабочий процесс', description: 'Создайте рабочий процесс с нуля', href: '/workflows/custom' },
    ],
  },
];
