/**
 * Где мы в «Аналитике» — в адресе, чтобы F5 возвращал к тому же отчёту.
 *
 * Мария, 14.10.2026: «можно, чтобы при обновлении страницы мы оставались на той
 * же странице?». Отчёт, период, даты, статус вакансий и подразделение жили
 * только в памяти страницы — после F5 всё сбрасывалось на «Вакансии → Время
 * закрытия позиций, текущий период».
 *
 * Адрес — ввод снаружи (старая ссылка, ручная правка, ссылка от коллеги), поэтому
 * каждое значение проверяется: чего нет в списке — берём значение по умолчанию.
 * В частности, рекрутёру не откроется категория, которой у него нет в меню.
 */

export interface AnalyticsCategoryLike {
  id: string;
  reports: ReadonlyArray<{ id: string }>;
}

export interface AnalyticsUrlState {
  category: string;
  report: string;
  period: string;
  from: string;
  to: string;
  status: string;
  department: number | null;
}

export const ANALYTICS_DEFAULTS = {
  category: 'vacancy',
  period: 'current',
  status: 'open',
} as const;

/** Ключи в адресе. Значение по умолчанию в адрес не пишем — ссылка короче. */
export const ANALYTICS_PARAM = {
  category: 'cat',
  report: 'report',
  period: 'period',
  from: 'from',
  to: 'to',
  status: 'status',
  department: 'dept',
} as const;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function readAnalyticsState(
  params: URLSearchParams,
  categories: ReadonlyArray<AnalyticsCategoryLike>,
  periodIds: ReadonlyArray<string>,
  statusIds: ReadonlyArray<string>,
): AnalyticsUrlState {
  const catParam = params.get(ANALYTICS_PARAM.category);
  const category =
    categories.find((c) => c.id === catParam) ??
    categories.find((c) => c.id === ANALYTICS_DEFAULTS.category) ??
    categories[0];

  const reportParam = params.get(ANALYTICS_PARAM.report);
  const report =
    category?.reports.find((r) => r.id === reportParam)?.id ??
    category?.reports[0]?.id ??
    '';

  const periodParam = params.get(ANALYTICS_PARAM.period) ?? '';
  const period =
    periodParam === 'custom' || periodIds.includes(periodParam)
      ? periodParam
      : ANALYTICS_DEFAULTS.period;

  const statusParam = params.get(ANALYTICS_PARAM.status) ?? '';
  const status = statusIds.includes(statusParam) ? statusParam : ANALYTICS_DEFAULTS.status;

  const deptRaw = params.get(ANALYTICS_PARAM.department);
  const deptNum = deptRaw && /^\d+$/.test(deptRaw) ? Number(deptRaw) : null;

  const from = params.get(ANALYTICS_PARAM.from) ?? '';
  const to = params.get(ANALYTICS_PARAM.to) ?? '';

  return {
    category: category?.id ?? ANALYTICS_DEFAULTS.category,
    report,
    period,
    from: ISO_DATE.test(from) ? from : '',
    to: ISO_DATE.test(to) ? to : '',
    status,
    department: deptNum,
  };
}

/**
 * Применить правки к адресу. `null`/пустая строка/значение по умолчанию —
 * убираем ключ. Возвращает НОВЫЙ объект, исходный не трогает.
 */
export function writeAnalyticsParams(
  current: URLSearchParams,
  patch: Partial<Record<keyof typeof ANALYTICS_PARAM, string | number | null>>,
): URLSearchParams {
  const next = new URLSearchParams(current);
  const defaults: Partial<Record<keyof typeof ANALYTICS_PARAM, string>> = ANALYTICS_DEFAULTS;
  for (const [field, raw] of Object.entries(patch) as Array<
    [keyof typeof ANALYTICS_PARAM, string | number | null | undefined]
  >) {
    const key = ANALYTICS_PARAM[field];
    const value = raw == null ? '' : String(raw);
    if (!value || value === defaults[field]) next.delete(key);
    else next.set(key, value);
  }
  return next;
}
