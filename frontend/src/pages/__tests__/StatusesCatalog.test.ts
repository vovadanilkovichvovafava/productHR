import { describe, expect, it } from "vitest";
import { offeredTeams } from "../StatusesPage";
import type { BoardDepartment } from "../../services/api/staffBoard";

// Отделы в окне выбора: список владельца + добавленные HR (11.11.2026).
const dept = (id: number, name: string, extra: Partial<BoardDepartment> = {}): BoardDepartment => ({
  id, name, hidden: false, kind: "team", parent_id: null, visibility: "all",
  visible_to: [], is_default: false, ...extra,
});

describe("offeredTeams", () => {
  it("сначала список владельца в его порядке, потом свои по алфавиту (русская сортировка: кириллица первой); старые и песочницы — нет", () => {
    const list = offeredTeams([
      dept(1, "SANDBOX", { kind: "sandbox" }),
      dept(2, "Push team", { canonical: true, offered: true, canon_order: 1 }),
      dept(3, "SEO team", { canonical: true, offered: true, canon_order: 0 }),
      dept(4, "Фин отдел", { offered: true }),
      dept(5, "Support отдел", { offered: true }),
      dept(6, "Фарм отдел"),
    ]);
    expect(list.map((d) => d.name)).toEqual(["SEO team", "Push team", "Фин отдел", "Support отдел"]);
  });
});

describe("порядок пунктов из общего хранилища (11.11.2026)", () => {
  it("перетащенные — в своём порядке, новые — в конце в исходном", async () => {
    const { orderByMeta, setDropdownMetaRegistry, metaColor } = await import("../StatusesPage");
    setDropdownMetaRegistry({ positions: { order: ["C", "A"], colors: { A: "#dc2626" } } });
    expect(orderByMeta("positions", ["A", "B", "C", "D"], (x) => x)).toEqual(["C", "A", "B", "D"]);
    expect(metaColor("positions", "A")).toBe("#dc2626");
    expect(orderByMeta("nope", ["B", "A"], (x) => x)).toEqual(["B", "A"]);
    setDropdownMetaRegistry({});
  });
});
