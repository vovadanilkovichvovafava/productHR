import type { VacancyStatus } from '@/types';

export type HuntflowVacancyStatusFilter = {
  id: VacancyStatus | 'all' | 'deleted';
  label: string;
};

export const HUNTFLOW_VACANCY_STATUS_FILTERS: HuntflowVacancyStatusFilter[] = [
  { id: 'all', label: 'Все' },
  { id: 'pending_review', label: 'На рассмотрении' },
  { id: 'open', label: 'Открыта' },
  { id: 'paused', label: 'На паузе' },
  { id: 'closed', label: 'Закрыта' },
  { id: 'cancelled', label: 'Отменена' },
  { id: 'deleted', label: 'Удалённые' },
];

export function getHuntflowVacancyStatusFilterLabel(status: VacancyStatus | 'all' | 'deleted') {
  return HUNTFLOW_VACANCY_STATUS_FILTERS.find((item) => item.id === status)?.label || status;
}
