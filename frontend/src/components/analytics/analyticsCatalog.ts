import {
  Clock, Users, UserPlus, Filter, FileDown, XCircle, ArrowRight, BarChart3,
} from 'lucide-react';
import type { ReportId } from './analyticsTypes';

// Меню «Аналитики»: категории, отчёты, периоды, статусы вакансий и цвета
// полос (вынесено из DashboardPage, 20.10.2026, без изменений).

export const REPORT_CATEGORIES = [
  {
    id: 'vacancy',
    label: 'Вакансии',
    icon: BarChart3,
    reports: [
      { id: 'ttf', label: 'Время закрытия позиций', icon: Clock },
      { id: 'funnel', label: 'Воронка подбора', icon: Filter },
      { id: 'sources', label: 'Источники резюме', icon: FileDown },
      { id: 'rejections', label: 'Причины отказов', icon: XCircle },
      { id: 'movement', label: 'Движение по этапам', icon: ArrowRight },
    ],
  },
  {
    id: 'recruiter',
    label: 'Рекрутеры',
    icon: Users,
    reports: [
      { id: 'funnel-recruiter', label: 'Воронка по рекрутерам', icon: Users },
    ],
  },
  {
    id: 'sourcer',
    label: 'Сорсеры',
    icon: UserPlus,
    reports: [
      { id: 'sourcers', label: 'Кого привели сорсеры', icon: UserPlus },
    ],
  },
] as const;

export const PERIOD_TABS = [
  { id: 'current', label: 'Текущая' },
  { id: 'month', label: 'Месяц' },
  { id: 'quarter', label: 'Квартал' },
  { id: 'half_year', label: 'Полгода' },
  { id: 'year', label: 'Год' },
] as const;

export const VACANCY_STATUS_OPTIONS = [
  { id: 'open', label: 'В работе' },
  { id: 'all', label: 'Все вакансии' },
  { id: 'closed', label: 'Закрытые' },
] as const;

export const BAR_COLORS = {
  primary: 'var(--hf-report-candidate)',
  green: 'var(--hf-report-source-green)',
  red: 'var(--hf-report-source-red)',
  gray_light: 'var(--hf-report-rejection-light)',
  gray_medium: 'var(--hf-report-rejection-medium)',
  gray_dark: 'var(--hf-report-rejection-dark)',
  blue: 'var(--hf-report-source-blue)',
  purple: 'var(--hf-report-source-purple)',
  orange: 'var(--hf-report-source-orange)',
};

/** Откуда грузится каждый отчёт. */
export const REPORT_ENDPOINTS: Record<ReportId, string> = {
  ttf: '/analytics/reports/time-to-fill',
  funnel: '/analytics/reports/funnel',
  'funnel-recruiter': '/analytics/reports/funnel-by-recruiter',
  sourcers: '/analytics/reports/sourcers',
  rejections: '/analytics/reports/rejections',
  sources: '/analytics/reports/sources',
  movement: '/analytics/reports/movement',
};
