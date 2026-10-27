/**
 * Выгрузка доски «Статусы» в несколько периодов.
 *
 * Мария (мит 07.10.2026): «нужно сделать фильтр для выгрузки за несколько
 * слотов: за сентябрь, за октябрь и за декабрь… выделить как месяц работы
 * сотрудника, как закрытие испытательного срока и как год работы — общим
 * слотом в одной табличке». Раньше кнопка отдавала ровно то, что на экране.
 */
import { describe, it, expect } from "vitest";
import { buildExportSheets, type ExportPlan } from "../StatusesPage";
import type { BoardRow } from "@/services/api/staffBoard";

const MONTHS = [
  { label: "Октябрь 2026", from: "2026-10-01", to: "2026-10-31" },
  { label: "Сентябрь 2026", from: "2026-09-01", to: "2026-09-30" },
  { label: "Август 2026", from: "2026-08-01", to: "2026-08-31" },
];

const row = (name: string, deptStart: string, extra: Partial<BoardRow> = {}): BoardRow =>
  ({
    entity_id: name.length,
    placement_id: null,
    name,
    status: "transferred",
    department_start_date: deptStart,
    m1: null, m3: null, y1: null,
  } as unknown as BoardRow);

const rows = [
  row("Августовский", "2026-08-15", {}),
  row("Сентябрьский", "2026-09-10", {}),
  row("Октябрьский", "2026-10-02", {}),
  row("Прошлогодний", "2025-12-01", {}),
];

describe("buildExportSheets", () => {
  it("без выбора отдаёт один лист — то, что на экране", () => {
    expect(buildExportSheets(rows, MONTHS)).toEqual([{ title: "Статусы", items: rows }]);
    const empty: ExportPlan = { months: [], marks: [] };
    expect(buildExportSheets(rows, MONTHS, empty)).toEqual([{ title: "Статусы", items: rows }]);
  });

  it("каждый выбранный месяц — свой лист, по дате выхода в отдел", () => {
    const sheets = buildExportSheets(rows, MONTHS, {
      months: ["Сентябрь 2026", "Август 2026"],
      marks: [],
    });
    expect(sheets.map((s) => s.title)).toEqual(["Сентябрь 2026", "Август 2026"]);
    expect(sheets[0].items.map((r) => r.name)).toEqual(["Сентябрьский"]);
    expect(sheets[1].items.map((r) => r.name)).toEqual(["Августовский"]);
    // Человек вне выбранных месяцев в книгу не попадает.
    expect(sheets.flatMap((s) => s.items).map((r) => r.name)).not.toContain("Прошлогодний");
  });

  it("вехи стажа — отдельными листами и только внутри выбранных месяцев", () => {
    const withMarks = [
      { ...rows[0], m1: "2026-09-15", m3: "2026-11-15", y1: "2027-08-15" },
      { ...rows[1], m1: "2026-10-10", m3: "2026-12-10", y1: "2027-09-10" },
    ] as BoardRow[];

    const sheets = buildExportSheets(withMarks, MONTHS, {
      months: ["Октябрь 2026", "Сентябрь 2026"],
      marks: ["m1", "m3"],
    });
    const titles = sheets.map((s) => s.title);
    expect(titles).toEqual(["Октябрь 2026", "Сентябрь 2026", "1 месяц", "Испытательный срок"]);

    const m1 = sheets.find((s) => s.title === "1 месяц")!;
    expect(m1.items.map((r) => r.name)).toEqual(["Августовский", "Сентябрьский"]);
    // Испыталка у обоих выпадает на ноябрь-декабрь — в выбранные месяцы не попала.
    expect(sheets.find((s) => s.title === "Испытательный срок")!.items).toEqual([]);
  });

  it("веха без выбранных месяцев берётся за всё время", () => {
    const withMarks = [{ ...rows[3], y1: "2026-12-01" }] as BoardRow[];
    const sheets = buildExportSheets(withMarks, MONTHS, { months: [], marks: ["y1"] });
    expect(sheets.map((s) => s.title)).toEqual(["Год работы"]);
    expect(sheets[0].items.map((r) => r.name)).toEqual(["Прошлогодний"]);
  });
});
