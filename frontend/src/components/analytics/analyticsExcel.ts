import type { ReportDataMap, ReportId } from './analyticsTypes';

// Что попадает в Excel по каждому отчёту «Аналитики» (вынесено из
// DashboardPage, 20.10.2026, листы и колонки без изменений). Чистая функция:
// сам файл пишет страница (XLSX), здесь только листы — их и проверяют тесты.

export type SheetRow = (string | number)[];
export interface ReportSheet {
  name: string;
  rows: SheetRow[];
}

const fmt = (n: number | null | undefined): string | number => (n == null ? '' : n);

/** Excel не принимает в имени листа \ / ? * [ ] : */
export const safeSheetName = (name: string) => name.replace(/[\\/?*[\]:]/g, '_');

/** Листы для отчёта; пусто — данных нет (страница скажет «Нет данных для экспорта»). */
export function buildReportSheets<R extends ReportId>(
  report: R,
  data: ReportDataMap[R] | null | undefined,
): ReportSheet[] {
  if (!data) return [];
  switch (report) {
    case 'ttf': {
      const d = data as ReportDataMap['ttf'];
      return [
        {
          name: 'Сводка',
          rows: [
            ['Показатель', 'Значение'],
            ['Средний срок закрытия (дн)', fmt(d.summary.avg_days_to_close)],
            ['Средняя просрочка (дн)', fmt(d.summary.avg_delay_days)],
            ['Закрыто позиций', d.summary.closed_positions],
            ['Всего позиций', d.summary.total_positions],
          ],
        },
        { name: 'Время на этапах', rows: [['Этап', 'Среднее время (дн)'], ...d.stage_timings.map((s) => [s.label, s.avg_days])] },
        {
          name: 'Последние закрытия',
          rows: [
            ['Кандидат', 'Вакансия', 'Рекрутер', 'Дата старта', 'Дата закрытия', 'Дней до закрытия'],
            ...d.last_closings.map((c) => [
              c.candidate_name, c.vacancy_title, c.recruiter_name ?? '', c.start_date ?? '', c.closed_date ?? '', fmt(c.days_to_close),
            ]),
          ],
        },
      ];
    }
    case 'funnel': {
      const d = data as ReportDataMap['funnel'];
      return [
        { name: 'Воронка', rows: [['Этап', 'Кандидатов', 'Отказов'], ...d.stages.map((s) => [s.label, s.candidate_count, s.rejection_count])] },
        { name: 'Источники', rows: [['Источник', 'Кол-во'], ...d.sources.map((s) => [s.source, s.count])] },
        { name: 'Причины отказов', rows: [['Причина отказа', 'Кол-во'], ...d.rejection_reasons.map((r) => [r.reason, r.count])] },
      ];
    }
    case 'funnel-recruiter': {
      const d = data as ReportDataMap['funnel-recruiter'];
      return [
        {
          name: 'Сводка',
          rows: [['Этап', 'Кандидатов', 'Отказов'], ...d.summary.stages.map((s) => [s.label, s.candidate_count, s.rejection_count])],
        },
        ...d.by_recruiter.map((rec) => ({
          name: safeSheetName(rec.recruiter_name.slice(0, 28)) || `Рекрутер ${rec.recruiter_id}`,
          rows: [
            [`Рекрутер: ${rec.recruiter_name}`],
            ['Этап', 'Кандидатов', 'Отказов'],
            ...rec.stages.map((s) => [s.label, s.candidate_count, s.rejection_count]),
          ],
        })),
      ];
    }
    case 'rejections': {
      const d = data as ReportDataMap['rejections'];
      return [
        { name: 'Топ причин', rows: [['Причина', 'Кол-во'], ...d.top_reasons.map((r) => [r.reason, r.count])] },
        { name: 'По этапам', rows: [['Этап', 'Всего отказов'], ...d.by_stage.map((s) => [s.label, s.count])] },
      ];
    }
    case 'sources': {
      const d = data as ReportDataMap['sources'];
      return [{ name: 'Все источники', rows: [['Источник', 'Кол-во'], ...d.sources.map((s) => [s.source, s.count])] }];
    }
    case 'movement': {
      const d = data as ReportDataMap['movement'];
      return [{ name: 'Движение', rows: [['Из этапа', 'В этап', 'Кол-во'], ...d.movements.map((m) => [m.from_label, m.to_label, m.count])] }];
    }
    // «Кого привели сорсеры» в Excel не выгружался и раньше.
    default:
      return [];
  }
}
