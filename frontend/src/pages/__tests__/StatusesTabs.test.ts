import { describe, expect, it } from "vitest";
import { sandboxTabs } from "../StatusesPage";
import type { BoardDepartment } from "../../services/api/staffBoard";

// Вкладки над доской — «Все» и песочницы (владелец, 10.11.2026).
const dept = (id: number, name: string, extra: Partial<BoardDepartment> = {}): BoardDepartment => ({
  id, name, hidden: false, kind: "team", parent_id: null, visibility: "all",
  visible_to: [], is_default: false, ...extra,
});

describe("sandboxTabs", () => {
  it("только песочницы, в порядке сервера, без скрытых и без команд", () => {
    const tabs = sandboxTabs([
      dept(1, "SANDBOX", { kind: "sandbox" }),
      dept(2, "SEO team", { canonical: true }),
      dept(3, "SANDBOX mobile", { kind: "sandbox" }),
      dept(4, "Старая песочница", { kind: "sandbox", hidden: true }),
      dept(5, "SANDBOX R&D", { kind: "sandbox" }),
    ]);
    expect(tabs.map((d) => d.name)).toEqual(["SANDBOX", "SANDBOX mobile", "SANDBOX R&D"]);
  });
});

describe("departmentFilterNames", () => {
  it("в фильтре «Отдел» — песочницы и отделы из списка, без старых", async () => {
    const { departmentFilterNames } = await import("../StatusesPage");
    expect(departmentFilterNames([
      dept(1, "SANDBOX", { kind: "sandbox" }),
      dept(2, "Product Studio (Марк)", { canonical: true }),
      dept(3, "Мобильная разработка"),
      dept(4, "Фарм отдел"),
    ])).toEqual(["SANDBOX", "Product Studio (Марк)"]);
  });
});
