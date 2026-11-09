import { describe, expect, it } from "vitest";
import { canonicalTeams, positionChoices } from "../StatusesPage";
import type { BoardDepartment } from "../../services/api/staffBoard";

// Отделы и должности — только из списка владельца (09.11.2026).
const dept = (id: number, name: string, extra: Partial<BoardDepartment> = {}): BoardDepartment => ({
  id, name, hidden: false, kind: "team", parent_id: null, visibility: "all",
  visible_to: [], is_default: false, ...extra,
});

const DEPTS = [
  dept(1, "SANDBOX", { kind: "sandbox" }),
  dept(2, "Push team", { canonical: true, canon_order: 1, positions: ["Push Media Buyer Team Lead", "Push Media Buyer"] }),
  dept(3, "SEO team", { canonical: true, canon_order: 0, positions: ["SEO Buyer"] }),
  dept(4, "iOS Product"),
];

describe("canonicalTeams", () => {
  it("только отделы из списка и в его порядке — без песочниц и старых", () => {
    expect(canonicalTeams(DEPTS).map((d) => d.name)).toEqual(["SEO team", "Push team"]);
  });
});

describe("positionChoices", () => {
  it("человек в отделе из списка — должности его отдела", () => {
    const g = positionChoices({ department_id: 2, department_is_sandbox: false, team_name: null }, DEPTS);
    expect(g).toEqual([{ label: "Push team", options: ["Push Media Buyer Team Lead", "Push Media Buyer"] }]);
  });

  it("строка песочницы — должности рабочей команды человека", () => {
    const g = positionChoices({ department_id: 1, department_is_sandbox: true, team_name: "SEO team" }, DEPTS);
    expect(g.map((x) => x.label)).toEqual(["SEO team"]);
  });

  it("без отдела или в старом отделе — все должности, по отделам", () => {
    for (const row of [
      { department_id: null, department_is_sandbox: false, team_name: null },
      { department_id: 4, department_is_sandbox: false, team_name: null },
      { department_id: 1, department_is_sandbox: true, team_name: null },
    ]) {
      expect(positionChoices(row, DEPTS).map((x) => x.label)).toEqual(["SEO team", "Push team"]);
    }
  });
});
