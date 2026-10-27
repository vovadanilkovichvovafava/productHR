/**
 * «Аналитика» после разбора на части (20.10.2026): листы Excel, параметры
 * запроса и то, что опоздавший ответ не затирает более новый.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

const get = vi.fn();
vi.mock("@/services/api/client", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));
vi.mock("react-hot-toast", () => ({ default: { error: vi.fn(), success: vi.fn() } }));

import { buildReportSheets, safeSheetName } from "../analyticsExcel";
import { reportParams, useAnalyticsReport, type AnalyticsFilters } from "../useAnalyticsReport";
import type { ReportDataMap } from "../analyticsTypes";

describe("buildReportSheets", () => {
  it("время закрытия: три листа, пустые значения — пустые ячейки", () => {
    const sheets = buildReportSheets("ttf", {
      summary: { avg_days_to_close: 12, avg_delay_days: null, closed_positions: 3, total_positions: 5 },
      stage_timings: [{ stage: "screening", label: "Выполняет ТЗ", avg_days: 2 }],
      last_closings: [
        { candidate_name: "Иванов", vacancy_title: "Трафик", recruiter_name: null, closed_date: "2026-10-01", days_to_close: null, start_date: null },
      ],
    } as ReportDataMap["ttf"]);
    expect(sheets.map((s) => s.name)).toEqual(["Сводка", "Время на этапах", "Последние закрытия"]);
    expect(sheets[0].rows[2]).toEqual(["Средняя просрочка (дн)", ""]);
    expect(sheets[2].rows[1]).toEqual(["Иванов", "Трафик", "", "", "2026-10-01", ""]);
  });

  it("воронка по рекрутёрам: лист на рекрутёра, запрещённые символы в имени листа заменены", () => {
    const sheets = buildReportSheets("funnel-recruiter", {
      summary: { stages: [], total_candidates: 0, total_rejections: 0, sources: [], rejection_reasons: [] },
      by_recruiter: [
        { recruiter_id: 4, recruiter_name: "Мария / HR", stages: [{ stage: "applied", label: "Новый", candidate_count: 7, rejection_count: 1 }], total_candidates: 7, total_rejections: 1 },
        { recruiter_id: 9, recruiter_name: "", stages: [], total_candidates: 0, total_rejections: 0 },
      ],
    } as ReportDataMap["funnel-recruiter"]);
    expect(sheets.map((s) => s.name)).toEqual(["Сводка", "Мария _ HR", "Рекрутер 9"]);
    expect(sheets[1].rows).toEqual([["Рекрутер: Мария / HR"], ["Этап", "Кандидатов", "Отказов"], ["Новый", 7, 1]]);
  });

  it("нет данных или отчёт без выгрузки (сорсеры) — листов нет", () => {
    expect(buildReportSheets("funnel", null)).toEqual([]);
    expect(buildReportSheets("sourcers", { items: [], total_brought: 0, total_hired: 0 })).toEqual([]);
  });

  it("safeSheetName", () => {
    expect(safeSheetName("a/b\\c?d*e[f]g:h")).toBe("a_b_c_d_e_f_g_h");
  });
});

const base: AnalyticsFilters = { report: "funnel", period: "month", from: "", to: "", status: "open", department: null };

describe("reportParams", () => {
  it("даты уходят только для своего диапазона, отдел — только выбранный", () => {
    expect(reportParams({ ...base, from: "2026-01-01" })).toEqual({ period: "month", vacancy_status: "open" });
    expect(reportParams({ ...base, period: "custom", from: "2026-01-01", to: "2026-02-01", department: 3 })).toEqual({
      period: "custom", vacancy_status: "open", department_id: "3", date_from: "2026-01-01", date_to: "2026-02-01",
    });
  });
});

describe("useAnalyticsReport", () => {
  beforeEach(() => get.mockReset());

  it("опоздавший ответ старого периода не затирает новый", async () => {
    let resolveMonth: (v: unknown) => void = () => {};
    get.mockImplementation((_url: string, opts?: { params: Record<string, string> }) =>
      opts?.params.period === "month"
        ? new Promise((r) => (resolveMonth = r))
        : Promise.resolve({ data: { total_candidates: 365 } }),
    );
    const { result, rerender } = renderHook((f: AnalyticsFilters) => useAnalyticsReport(f), { initialProps: base });
    rerender({ ...base, period: "year" });
    await waitFor(() => expect(result.current.data.funnel).toEqual({ total_candidates: 365 }));
    expect(result.current.isLoading).toBe(false);
    await act(async () => resolveMonth({ data: { total_candidates: 30 } }));
    expect(result.current.data.funnel).toEqual({ total_candidates: 365 });
  });

  it("дата начала позже конца — запрос не уходит", async () => {
    renderHook(() => useAnalyticsReport({ ...base, period: "custom", from: "2026-05-01", to: "2026-01-01" }));
    await new Promise((r) => setTimeout(r, 0));
    expect(get).not.toHaveBeenCalled();
  });

  it("каждый отчёт ходит в свой адрес", async () => {
    get.mockResolvedValue({ data: {} });
    renderHook(() => useAnalyticsReport({ ...base, report: "movement" }));
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(get.mock.calls[0][0]).toBe("/analytics/reports/movement");
  });
});
