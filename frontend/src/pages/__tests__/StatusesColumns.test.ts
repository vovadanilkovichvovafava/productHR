/**
 * Колонки доски «Статусы» настраиваются лично и по вкладкам.
 *
 * Мария 08.10.2026: «лист-вью не только по статусам, но и по столбцам».
 * «Сотрудник» спрятать нельзя — по имени и читается строка.
 */
import { describe, it, expect } from "vitest";
import { pickColumns } from "../StatusesPage";

describe("pickColumns", () => {
  it("ничего не выбрано — показываем все колонки", () => {
    const all = pickColumns();
    expect(all.length).toBeGreaterThan(10);
    expect(pickColumns([])).toEqual(all);
    expect(pickColumns(null)).toEqual(all);
  });

  it("«Сумма» появляется только у тех, кому её отдаёт сервер", () => {
    // Владелец 09.10.2026: столбец видит только Настя (owner организации).
    expect(pickColumns().map((c) => c.key)).not.toContain("salary");
    expect(pickColumns(null, true).map((c) => c.key)).toContain("salary");
    // Отмечена в наборе, но права нет — всё равно не показываем.
    expect(pickColumns(["salary", "position"]).map((c) => c.key)).toEqual(["name", "position"]);
    expect(pickColumns(["salary", "position"], true).map((c) => c.key))
      .toEqual(["name", "position", "salary"]);
  });

  it("оставляем отмеченные и всегда «Сотрудника»", () => {
    const keys = pickColumns(["position", "department"]).map((c) => c.key);
    expect(keys).toEqual(["name", "position", "department"]);
  });

  it("порядок всегда табличный, а не порядок галочек", () => {
    const keys = pickColumns(["dismissal_date", "assignee", "m1"]).map((c) => c.key);
    expect(keys).toEqual(["name", "assignee", "m1", "dismissal_date"]);
  });

  it("неизвестные ключи игнорируются", () => {
    expect(pickColumns(["мусор"]).map((c) => c.key)).toEqual(["name"]);
  });
});
