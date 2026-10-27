import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import api from '@/services/api/client';
import { REPORT_ENDPOINTS } from './analyticsCatalog';
import type { ReportDataMap, ReportId } from './analyticsTypes';

// Загрузка открытого отчёта «Аналитики» (вынесено из DashboardPage, 20.10.2026).
// Раньше у каждого отчёта было своё состояние (7 штук) и switch на 7 веток.
//
// Исправлено попутно: ответ, который пришёл ПОСЛЕ более нового запроса,
// больше не перезаписывает экран. Раньше быстро переключил период «Месяц» →
// «Год» — если месячный ответ был медленнее, на экране оставались цифры за
// месяц под заголовком «Год», а спиннер гас по первому пришедшему ответу.

export interface AnalyticsFilters {
  report: string;
  period: string;
  from: string;
  to: string;
  status: string;
  department: number | null;
}

/** Параметры запроса отчёта — те же, что и раньше. */
export function reportParams(f: AnalyticsFilters): Record<string, string> {
  const params: Record<string, string> = { period: f.period, vacancy_status: f.status };
  if (f.department) params.department_id = String(f.department);
  if (f.period === 'custom') {
    if (f.from) params.date_from = f.from;
    if (f.to) params.date_to = f.to;
  }
  return params;
}

const isReportId = (id: string): id is ReportId => id in REPORT_ENDPOINTS;

export function useAnalyticsReport(filters: AnalyticsFilters) {
  const { report, period, from, to, status, department } = filters;
  const [data, setData] = useState<Partial<ReportDataMap>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    if (period === 'custom' && from && to && from > to) {
      toast.error('Дата начала не может быть позже даты окончания');
      return;
    }
    if (!isReportId(report)) return;
    const seq = ++requestSeq.current;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.get<ReportDataMap[typeof report]>(REPORT_ENDPOINTS[report], {
        params: reportParams({ report, period, from, to, status, department }),
      });
      if (seq !== requestSeq.current) return;
      setData((prev) => ({ ...prev, [report]: res.data }));
    } catch (err) {
      if (seq !== requestSeq.current) return;
      setError('Не удалось загрузить данные отчёта');
      toast.error('Ошибка загрузки отчёта');
      console.error(err);
    } finally {
      if (seq === requestSeq.current) setIsLoading(false);
    }
  }, [report, period, from, to, status, department]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, isLoading, error };
}
