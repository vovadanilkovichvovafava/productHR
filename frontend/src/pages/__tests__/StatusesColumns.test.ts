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

  it("«Суммы» нет нигде, «Причина отказа» — есть (владелец, 10.11.2026)", () => {
    expect(pickColumns().map((c) => c.key)).not.toContain("salary");
    expect(pickColumns(["salary", "position"]).map((c) => c.key)).toEqual(["name", "position"]);
    expect(pickColumns().map((c) => c.key)).toContain("rejection_reason");
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

describe("arrangeColumns — общий вид (11.11.2026)", () => {
  it("скрытые убраны, «ФИО» — всегда первым, новые колонки видны", async () => {
    const { arrangeColumns } = await import("../StatusesPage");
    const keys = arrangeColumns({ hidden: ["w2", "w2_done", "name"] }).map((c) => c.key);
    expect(keys[0]).toBe("name");
    expect(keys).not.toContain("w2");
    expect(keys).not.toContain("w2_done");
    expect(keys).toContain("rejection_reason");
  });

  it("порядок из перетаскивания, остальные — следом в исходном порядке; ширины свои", async () => {
    const { arrangeColumns } = await import("../StatusesPage");
    const cols = arrangeColumns({ order: ["telegram", "name", "position", "мусор"], widths: { telegram: 90 } });
    expect(cols.map((c) => c.key).slice(0, 4)).toEqual(["name", "telegram", "position", "assignee"]);
    expect(cols.find((c) => c.key === "telegram")!.width).toBe(90);
    // скрытые в withHidden остаются — для панели «Поля»
    expect(arrangeColumns({ hidden: ["w2"] }, true).map((c) => c.key)).toContain("w2");
  });

  it("свои названия видны в подписях", async () => {
    const { setFieldLabels, fieldLabel } = await import("../StatusesPage");
    setFieldLabels({ position: "Роль" });
    expect(fieldLabel("position")).toBe("Роль");
    expect(fieldLabel("m1_done")).toBe("1 мес ✓");
    setFieldLabels({});
    expect(fieldLabel("position")).toBe("Должность");
  });
});
