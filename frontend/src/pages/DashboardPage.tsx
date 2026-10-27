import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronDown, FileSpreadsheet, FileDown, XCircle, CalendarRange } from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import * as XLSX from 'xlsx';
import api from '@/services/api/client';
import { useAuthStore } from '@/stores/authStore';
import { ANALYTICS_PARAM, readAnalyticsState, writeAnalyticsParams } from '@/utils/analyticsUrl';

import {
  REPORT_CATEGORIES, PERIOD_TABS, VACANCY_STATUS_OPTIONS,
} from '@/components/analytics/analyticsCatalog';
import type { DepartmentSummary, ReportId } from '@/components/analytics/analyticsTypes';
import { buildReportSheets, safeSheetName } from '@/components/analytics/analyticsExcel';
import { useAnalyticsReport } from '@/components/analytics/useAnalyticsReport';
import {
  FilterSelect, TTFContent, FunnelContent, FunnelByRecruiterContent, SourcersContent,
  RejectionsContent, SourcesContent, MovementContent,
} from '@/components/analytics/AnalyticsReports';

// «Аналитика» (/analytics): фильтры в адресе, загрузка — useAnalyticsReport,
// содержимое отчётов — components/analytics/AnalyticsReports.tsx, Excel —
// analyticsExcel.ts (разобрано на части 20.10.2026).

type FilterMenu = 'category' | 'report' | 'period' | 'department' | 'status';

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const isAdminAnalytics =
    user?.role === 'superadmin' ||
    user?.org_role === 'owner' ||
    user?.org_role === 'admin';
  // Не-админ (hr-рекрутёр, member) видит только категорию "Вакансии" — все цифры
  // backend отскейпит на его recruiter_id. Категория "Рекрутеры" скрыта, т.к.
  // там воронка по всем рекрутерам — для не-админа смысла нет.
  const visibleCategories = isAdminAnalytics
    ? REPORT_CATEGORIES
    : REPORT_CATEGORIES.filter(c => c.id !== 'recruiter');

  // Выбранный отчёт и фильтры живут в АДРЕСЕ (?cat=&report=&period=&from=&to=
  // &status=&dept=), а не в памяти страницы: F5 возвращает туда же (Мария,
  // 14.10.2026: «при обновлении страницы остаёмся на той же странице»). Разбор
  // с проверкой — utils/analyticsUrl.ts.
  const [searchParams, setSearchParams] = useSearchParams();
  const urlState = useMemo(
    () =>
      readAnalyticsState(
        searchParams,
        visibleCategories,
        PERIOD_TABS.map((p) => p.id),
        VACANCY_STATUS_OPTIONS.map((o) => o.id),
      ),
    [searchParams, visibleCategories],
  );
  const activeCategory = urlState.category;
  const activeReport = urlState.report;
  const period = urlState.period;
  const customFrom = urlState.from;
  const customTo = urlState.to;
  const vacancyStatus = urlState.status;
  const selectedDepartment = urlState.department;
  // Правки из одного обработчика (категория + её первый отчёт) копим и пишем
  // ОДНОЙ навигацией: два setSearchParams подряд затирали бы друг друга —
  // функциональная форма отдаёт адрес с прошлой отрисовки.
  const pendingParamsRef = useRef<Parameters<typeof writeAnalyticsParams>[1]>({});
  const writeParam = useCallback(
    (field: keyof typeof ANALYTICS_PARAM, value: string | number | null) => {
      const flushNeeded = Object.keys(pendingParamsRef.current).length === 0;
      pendingParamsRef.current = { ...pendingParamsRef.current, [field]: value };
      if (!flushNeeded) return;
      queueMicrotask(() => {
        const patch = pendingParamsRef.current;
        pendingParamsRef.current = {};
        setSearchParams(
          () => writeAnalyticsParams(new URLSearchParams(window.location.search), patch),
          { replace: true },
        );
      });
    },
    [setSearchParams],
  );
  const setActiveCategory = useCallback((v: string) => writeParam('category', v), [writeParam]);
  const setActiveReport = useCallback((v: string) => writeParam('report', v), [writeParam]);
  const setPeriod = useCallback((v: string) => writeParam('period', v), [writeParam]);
  const setCustomFrom = useCallback((v: string) => writeParam('from', v), [writeParam]);
  const setCustomTo = useCallback((v: string) => writeParam('to', v), [writeParam]);
  const setVacancyStatus = useCallback((v: string) => writeParam('status', v), [writeParam]);
  const setSelectedDepartment = useCallback(
    (v: number | null) => writeParam('department', v),
    [writeParam],
  );
  // Открыто не больше одного меню фильтров; раньше у каждого было своё
  // состояние, и каждое при открытии вручную закрывало остальные четыре.
  const [openMenu, setOpenMenu] = useState<FilterMenu | null>(null);
  const toggleMenu = (menu: FilterMenu) => setOpenMenu((m) => (m === menu ? null : menu));
  const closeMenu = () => setOpenMenu(null);

  const [departments, setDepartments] = useState<DepartmentSummary[]>([]);
  useEffect(() => {
    api.get<DepartmentSummary[]>('/analytics/dashboard/departments-summary')
      .then(res => setDepartments(Array.isArray(res.data) ? res.data : []))
      .catch(() => setDepartments([]));
  }, []);

  const { data: reportData, isLoading, error: reportError } = useAnalyticsReport({
    report: activeReport,
    period,
    from: customFrom,
    to: customTo,
    status: vacancyStatus,
    department: selectedDepartment,
  });

  // Find current category & report info — должно быть до handleExportExcel
  const currentCat = REPORT_CATEGORIES.find(c => c.id === activeCategory);
  const currentReport = currentCat?.reports.find(r => r.id === activeReport);
  const currentStatus = VACANCY_STATUS_OPTIONS.find(s => s.id === vacancyStatus);
  const currentDepartment = departments.find(d => d.id === selectedDepartment);

  // Экспорт текущего отчёта в Excel
  const handleExportExcel = useCallback(() => {
    const sheets = buildReportSheets(activeReport as ReportId, reportData[activeReport as ReportId]);
    if (sheets.length === 0) {
      toast.error('Нет данных для экспорта');
      return;
    }
    const wb = XLSX.utils.book_new();
    sheets.forEach((sh) => XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(sh.rows), sh.name));
    const reportLabel = currentReport?.label ? safeSheetName(currentReport.label) : 'report';
    const today = new Date().toISOString().slice(0, 10);
    XLSX.writeFile(wb, `${reportLabel}_${today}.xlsx`);
    toast.success('Excel экспортирован');
  }, [activeReport, reportData, currentReport]);

  return (
    <div className="hf-analytics-page">
      <div className="hf-analytics-header">
        <div className="hf-analytics-title-row">
          <div className="hf-analytics-title">
            <h1>Центр аналитики</h1>
          </div>
          <button
            type="button"
            onClick={handleExportExcel}
            className="hf-analytics-excel"
            title="Скачать Excel"
          >
            <FileSpreadsheet className="hf-analytics-excel-icon" />
            Скачать Excel
          </button>
        </div>

        <div className="hf-analytics-filter-row">
          <div className="hf-analytics-filter-group">
            <div className="hf-analytics-filter-dd">
              <FilterSelect
                label=""
                value={currentCat?.label ?? 'Вакансии'}
                open={openMenu === 'category'}
                onClick={() => toggleMenu('category')}
              />
              {openMenu === 'category' && (
                <>
                  <button
                    type="button"
                    aria-label="Закрыть меню категории отчётов"
                    className="hf-analytics-menu-backdrop"
                    onClick={() => closeMenu()}
                  />
                  <div className="hf-analytics-menu hf-analytics-menu-open">
                    {visibleCategories.map(cat => (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => {
                          setActiveCategory(cat.id);
                          setActiveReport(cat.reports[0].id);
                          closeMenu();
                        }}
                        className={clsx('hf-analytics-menu-item', activeCategory === cat.id && 'hf-analytics-menu-item-active')}
                      >
                        {cat.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="hf-analytics-filter-dd">
              <FilterSelect
                label=""
                value={currentReport?.label ?? 'Отчёт'}
                open={openMenu === 'report'}
                onClick={() => toggleMenu('report')}
              />
              {openMenu === 'report' && (
                <>
                  <button
                    type="button"
                    aria-label="Закрыть меню отчётов"
                    className="hf-analytics-menu-backdrop"
                    onClick={() => closeMenu()}
                  />
                  <div className="hf-analytics-report-menu hf-analytics-menu-open">
                    {currentCat ? (
                      <div className="hf-analytics-report-group">
                        {currentCat.reports.map(rep => {
                          const Icon = rep.icon;
                          const isActive = activeReport === rep.id;
                          return (
                            <button
                              key={rep.id}
                              type="button"
                              onClick={() => {
                                setActiveReport(rep.id);
                                closeMenu();
                              }}
                              className={clsx(
                                'hf-analytics-report-item',
                                isActive && 'hf-analytics-report-item-active',
                              )}
                            >
                              <Icon className="hf-analytics-report-item-icon" />
                              <span>{rep.label}</span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="hf-analytics-filter-group">
            <div className="hf-analytics-filter-dd">
              <FilterSelect
                label="За период:"
                value={PERIOD_TABS.find(p => p.id === period)?.label ?? 'Свой диапазон'}
                open={openMenu === 'period'}
                onClick={() => toggleMenu('period')}
              />
              {openMenu === 'period' && (
                <>
                  <button
                    type="button"
                    aria-label="Закрыть меню периода"
                    className="hf-analytics-menu-backdrop"
                    onClick={() => closeMenu()}
                  />
                  <div className="hf-analytics-menu hf-analytics-menu-open">
                    {PERIOD_TABS.map(p => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => { setPeriod(p.id); closeMenu(); }}
                        className={clsx('hf-analytics-menu-item', period === p.id && 'hf-analytics-menu-item-active')}
                      >
                        {p.label}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => { setPeriod('custom'); closeMenu(); }}
                      className={clsx('hf-analytics-menu-item', period === 'custom' && 'hf-analytics-menu-item-active')}
                    >
                      <CalendarRange className="hf-analytics-menu-icon" />
                      Свой диапазон
                    </button>
                  </div>
                </>
              )}
            </div>

            <div className="hf-analytics-filter-dd">
              <FilterSelect
                label="Подразделение:"
                value={currentDepartment?.name ?? 'Все'}
                open={openMenu === 'department'}
                onClick={() => toggleMenu('department')}
              />
              {openMenu === 'department' && (
                <>
                  <button
                    type="button"
                    aria-label="Закрыть меню подразделений"
                    className="hf-analytics-menu-backdrop"
                    onClick={() => closeMenu()}
                  />
                  <div className="hf-analytics-menu hf-analytics-menu-open">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedDepartment(null);
                        closeMenu();
                      }}
                      className={clsx('hf-analytics-menu-item', selectedDepartment === null && 'hf-analytics-menu-item-active')}
                    >
                      Все
                    </button>
                    {departments.map(dept => (
                      <button
                        key={dept.id}
                        type="button"
                        onClick={() => {
                          setSelectedDepartment(dept.id);
                          closeMenu();
                        }}
                        className={clsx('hf-analytics-menu-item', selectedDepartment === dept.id && 'hf-analytics-menu-item-active')}
                      >
                        {dept.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="hf-analytics-filter-dd">
              <button
                type="button"
                onClick={() => toggleMenu('status')}
                className="hf-analytics-filter"
              >
                <span>Вакансии:</span>
                <strong>{currentStatus?.label}</strong>
                <ChevronDown className="hf-analytics-filter-chevron" />
              </button>
              {openMenu === 'status' && (
                <>
                  <button
                    type="button"
                    aria-label="Закрыть меню статуса вакансий"
                    className="hf-analytics-menu-backdrop"
                    onClick={() => closeMenu()}
                  />
                  <div className="hf-analytics-menu hf-analytics-menu-open">
                    {VACANCY_STATUS_OPTIONS.map(s => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => { setVacancyStatus(s.id); closeMenu(); }}
                        className={clsx('hf-analytics-menu-item', vacancyStatus === s.id && 'hf-analytics-menu-item-active')}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {period === 'custom' && (
            <div className="hf-analytics-date-range">
              <input
                type="date"
                value={customFrom}
                onChange={e => setCustomFrom(e.target.value)}
                className="hf-analytics-date"
              />
              <span>—</span>
              <input
                type="date"
                value={customTo}
                onChange={e => setCustomTo(e.target.value)}
                className="hf-analytics-date"
              />
            </div>
          )}
        </div>
      </div>

      <main className="hf-analytics-main">
        <section className="hf-analytics-report-sheet">
          <div className="hf-analytics-report-heading">
            <h2>{currentCat?.label ?? 'Вакансии'} → {currentReport?.label ?? 'Отчёт'}</h2>
            <button
              type="button"
              onClick={() => window.print()}
              className="hf-analytics-print"
              title="Печать"
              aria-label="Печать отчёта"
            >
              <FileDown className="hf-analytics-print-icon" />
            </button>
          </div>

          {isLoading ? (
            <div className="hf-analytics-loading">
              <div className="hf-analytics-spinner" />
            </div>
          ) : reportError ? (
            <div className="hf-analytics-empty-state">
              <XCircle className="hf-analytics-empty-icon" />
              <div>
                <h3>{reportError}</h3>
                <p>Попробуйте другой фильтр или обновите отчёт позже.</p>
              </div>
            </div>
          ) : (
            <>
              {activeReport === 'ttf' && reportData['ttf'] && <TTFContent data={reportData['ttf']} />}
              {activeReport === 'funnel' && reportData['funnel'] && <FunnelContent data={reportData['funnel']} />}
              {activeReport === 'funnel-recruiter' && reportData['funnel-recruiter'] && <FunnelByRecruiterContent data={reportData['funnel-recruiter']} />}
              {activeReport === 'sourcers' && reportData['sourcers'] && <SourcersContent data={reportData['sourcers']} />}
              {activeReport === 'rejections' && reportData['rejections'] && <RejectionsContent data={reportData['rejections']} />}
              {activeReport === 'sources' && reportData['sources'] && <SourcesContent data={reportData['sources']} />}
              {activeReport === 'movement' && reportData['movement'] && <MovementContent data={reportData['movement']} />}
            </>
          )}
        </section>
      </main>
    </div>
  );
}
